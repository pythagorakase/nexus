"""Maintain committed, corpus-scoped PostgreSQL document frequencies.

The runner owns the transaction. Source-table locks keep initial population
and trigger installation atomic with respect to existing narrative writers.
"""

from __future__ import annotations

from typing import Any

from nexus.agents.orrery.reconstruction import playable_narrative_predicate


def run(conn: Any) -> None:
    """Install IDF accounting and backfill only production-searchable documents."""
    with conn.cursor() as cur:
        cur.execute(
            "LOCK TABLE narrative_chunks, chunk_metadata, retrograde_summaries "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
        cur.execute(
            """
            CREATE TABLE memory_idf_corpora (
                corpus_kind text PRIMARY KEY
                    CHECK (corpus_kind IN ('narrative', 'retrograde_summary')),
                analyzer_version text NOT NULL,
                corpus_epoch bigint NOT NULL DEFAULT 0 CHECK (corpus_epoch >= 0),
                document_count bigint NOT NULL DEFAULT 0 CHECK (document_count >= 0)
            );
            CREATE TABLE memory_idf_documents (
                corpus_kind text NOT NULL REFERENCES memory_idf_corpora,
                document_id bigint NOT NULL,
                content_digest text NOT NULL,
                lexemes text[] NOT NULL,
                PRIMARY KEY (corpus_kind, document_id)
            );
            CREATE TABLE memory_idf_lexemes (
                corpus_kind text NOT NULL REFERENCES memory_idf_corpora,
                lexeme text NOT NULL,
                document_frequency bigint NOT NULL CHECK (document_frequency > 0),
                PRIMARY KEY (corpus_kind, lexeme)
            );
            INSERT INTO memory_idf_corpora (corpus_kind, analyzer_version)
            SELECT kind, 'pg_catalog.english/v1/' || current_setting('server_version_num')
            FROM unnest(ARRAY['narrative', 'retrograde_summary']) AS kind;

            COMMENT ON TABLE memory_idf_corpora IS
                'Database-local IDF corpus identity and transactional watermark. Narrative membership uses the canonical playable predicate plus chunk_metadata presence; persisted Retrograde summaries are text-ready. No finalized-state filter applies.';
            COMMENT ON COLUMN memory_idf_corpora.corpus_kind IS
                'Canonical searchable corpus identity inside this save database: narrative or retrograde_summary. Frequencies never cross corpus kinds.';
            COMMENT ON COLUMN memory_idf_corpora.analyzer_version IS
                'PostgreSQL pg_catalog.english analyzer contract and exact server version. Analyzer or membership-contract changes require an explicit transactional rebuild; readers reject a version mismatch.';
            COMMENT ON COLUMN memory_idf_corpora.corpus_epoch IS
                'Transactional counter advanced on searchable text edits, insertions, removals, and truncation; rolled-back writes do not advance it. Never inferred from MAX(id).';
            COMMENT ON COLUMN memory_idf_corpora.document_count IS
                'Number of searchable documents, including documents whose text has no lexemes.';
            COMMENT ON TABLE memory_idf_documents IS
                'Trigger-owned projection used for reversible document-frequency deltas. Unique lexemes come from the same pg_catalog.english to_tsvector analyzer used in retrieval.';
            COMMENT ON COLUMN memory_idf_documents.corpus_kind IS
                'Owning corpus identity; paired with document_id so unrelated source-table IDs cannot collide.';
            COMMENT ON COLUMN memory_idf_documents.document_id IS
                'Source narrative_chunks.id or retrograde_summaries.id, selected by corpus_kind. Membership is maintained by source-table triggers.';
            COMMENT ON COLUMN memory_idf_documents.lexemes IS
                'Unique PostgreSQL English lexemes for this document, retained to subtract its exact contribution on edits and removal.';
            COMMENT ON COLUMN memory_idf_documents.content_digest IS
                'MD5 of source text detects edits even when the resulting lexeme set is unchanged; this is an invalidation marker, not a security hash.';
            COMMENT ON COLUMN memory_idf_lexemes.corpus_kind IS
                'Corpus whose searchable documents contribute to this lexeme frequency.';
            COMMENT ON COLUMN memory_idf_lexemes.lexeme IS
                'One PostgreSQL English full-text-search lexeme, never a client-side stem or tokenizer approximation.';
            COMMENT ON COLUMN memory_idf_lexemes.document_frequency IS
                'Number of searchable documents in this corpus containing this lexeme at least once; repeated occurrences within one document count once.';
            COMMENT ON TABLE memory_idf_lexemes IS
                'Trigger-owned document counts by corpus and PostgreSQL lexeme. Counts and corpus epoch commit atomically with source writes; no process or filesystem cache is authoritative.';
            """
        )
        cur.execute(
            """
            CREATE FUNCTION sync_memory_idf_document(kind text, doc_id bigint)
            RETURNS void LANGUAGE plpgsql AS $body$
            DECLARE
                source_text text;
                new_lexemes text[];
                old_doc memory_idf_documents%ROWTYPE;
                had_doc boolean;
                has_doc boolean;
                expected_analyzer text := 'pg_catalog.english/v1/' || current_setting('server_version_num');
                actual_analyzer text;
            BEGIN
                SELECT analyzer_version INTO STRICT actual_analyzer
                FROM memory_idf_corpora WHERE corpus_kind = kind FOR UPDATE;
                IF actual_analyzer <> expected_analyzer THEN
                    RAISE EXCEPTION 'IDF analyzer mismatch for corpus %: rebuild required', kind;
                END IF;
                SELECT * INTO old_doc FROM memory_idf_documents
                WHERE corpus_kind = kind AND document_id = doc_id;
                had_doc := FOUND;
                IF kind = 'narrative' THEN
                    SELECT nc.raw_text INTO source_text
                    FROM narrative_chunks nc
                    JOIN chunk_metadata cm ON cm.chunk_id = nc.id
                    WHERE nc.id = doc_id AND __PLAYABLE__;
                ELSIF kind = 'retrograde_summary' THEN
                    SELECT summary_text INTO source_text
                    FROM retrograde_summaries WHERE id = doc_id;
                ELSE
                    RAISE EXCEPTION 'Unsupported IDF corpus %', kind;
                END IF;
                has_doc := FOUND;
                IF NOT has_doc AND NOT had_doc THEN RETURN; END IF;
                IF has_doc THEN
                    source_text := COALESCE(source_text, '');
                    new_lexemes := tsvector_to_array(to_tsvector('pg_catalog.english', source_text));
                    IF had_doc AND old_doc.content_digest = md5(source_text)
                        AND old_doc.lexemes = new_lexemes THEN RETURN; END IF;
                END IF;
                IF had_doc THEN
                    DELETE FROM memory_idf_lexemes
                    WHERE corpus_kind = kind AND lexeme = ANY(old_doc.lexemes)
                        AND document_frequency = 1;
                    UPDATE memory_idf_lexemes SET document_frequency = document_frequency - 1
                    WHERE corpus_kind = kind AND lexeme = ANY(old_doc.lexemes);
                    DELETE FROM memory_idf_documents
                    WHERE corpus_kind = kind AND document_id = doc_id;
                END IF;
                IF has_doc THEN
                    INSERT INTO memory_idf_documents VALUES
                        (kind, doc_id, md5(source_text), new_lexemes);
                    INSERT INTO memory_idf_lexemes (corpus_kind, lexeme, document_frequency)
                    SELECT kind, lexeme, 1 FROM unnest(new_lexemes) AS lexeme
                    ON CONFLICT (corpus_kind, lexeme) DO UPDATE
                    SET document_frequency = memory_idf_lexemes.document_frequency + 1;
                END IF;
                UPDATE memory_idf_corpora SET
                    corpus_epoch = corpus_epoch + 1,
                    document_count = document_count + has_doc::integer - had_doc::integer
                WHERE corpus_kind = kind;
            END;
            $body$;

            CREATE FUNCTION maintain_memory_idf() RETURNS trigger
            LANGUAGE plpgsql AS $body$
            DECLARE
                kind text := TG_ARGV[0];
                old_id bigint;
                new_id bigint;
            BEGIN
                IF TG_OP = 'TRUNCATE' THEN
                    PERFORM 1 FROM memory_idf_corpora WHERE corpus_kind = kind FOR UPDATE;
                    DELETE FROM memory_idf_lexemes WHERE corpus_kind = kind;
                    DELETE FROM memory_idf_documents WHERE corpus_kind = kind;
                    UPDATE memory_idf_corpora SET document_count = 0,
                        corpus_epoch = corpus_epoch + 1 WHERE corpus_kind = kind;
                    RETURN NULL;
                END IF;
                IF TG_OP <> 'INSERT' THEN
                    old_id := (to_jsonb(OLD)->>TG_ARGV[1])::bigint;
                    PERFORM sync_memory_idf_document(kind, old_id);
                END IF;
                IF TG_OP <> 'DELETE' THEN
                    new_id := (to_jsonb(NEW)->>TG_ARGV[1])::bigint;
                    IF old_id IS DISTINCT FROM new_id THEN
                        PERFORM sync_memory_idf_document(kind, new_id);
                    END IF;
                END IF;
                RETURN NULL;
            END;
            $body$;
            COMMENT ON FUNCTION sync_memory_idf_document(text, bigint) IS
                'Serialize per-corpus deltas under the corpus row lock, then reread canonical membership and text. A source write and all IDF accounting share one transaction.';
            COMMENT ON FUNCTION maintain_memory_idf() IS
                'Account for source insert/update/delete/truncate, including metadata arrival/removal and changes to the synthetic prologue marker.';
            """.replace(
                "__PLAYABLE__", playable_narrative_predicate()
            )
        )
        for table, kind, id_column in (
            ("narrative_chunks", "narrative", "id"),
            ("chunk_metadata", "narrative", "chunk_id"),
            ("retrograde_summaries", "retrograde_summary", "id"),
        ):
            # All identifiers are migration-owned constants.
            cur.execute(
                f"""
                CREATE TRIGGER maintain_idf_row
                AFTER INSERT OR UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION maintain_memory_idf('{kind}', '{id_column}');
                CREATE TRIGGER maintain_idf_truncate
                AFTER TRUNCATE ON {table}
                FOR EACH STATEMENT EXECUTE FUNCTION maintain_memory_idf('{kind}', '{id_column}');
                """
            )
        cur.execute(
            """
            SELECT sync_memory_idf_document('narrative', id) FROM narrative_chunks;
            SELECT sync_memory_idf_document('retrograde_summary', id) FROM retrograde_summaries;
            """
        )
