-- Migration 133: Name the IDF Rebuild Command in the Analyzer Mismatch (issue #1013)
--
-- Migration 114 keys each IDF corpus on the exact PostgreSQL server version,
-- so a patch release (Postgres.app updates itself) makes every narrative and
-- summary write fail in sync_memory_idf_document until the corpus is rebuilt
-- under the live analyzer. The key and the fail-loud check stay as they are:
-- a patch release can change lexing. This migration only re-creates the
-- function so its error names both keys and the rebuild command,
-- scripts/rebuild_memory_idf.py. The body is migration 114's, with the
-- canonical playable-narrative predicate inlined, except for the RAISE text.

CREATE OR REPLACE FUNCTION sync_memory_idf_document(kind text, doc_id bigint)
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
        RAISE EXCEPTION 'IDF analyzer mismatch for corpus %: expected %, found %; run python scripts/rebuild_memory_idf.py --slot N (or --template / --all)', kind, expected_analyzer, actual_analyzer;
    END IF;
    SELECT * INTO old_doc FROM memory_idf_documents
    WHERE corpus_kind = kind AND document_id = doc_id;
    had_doc := FOUND;
    IF kind = 'narrative' THEN
        SELECT nc.raw_text INTO source_text
        FROM narrative_chunks nc
        JOIN chunk_metadata cm ON cm.chunk_id = nc.id
        WHERE nc.id = doc_id AND NOT (COALESCE(nc.authorial_directives, '[]'::jsonb) @> '["orrery:retrograde_prologue_anchor"]'::jsonb);
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

COMMENT ON FUNCTION sync_memory_idf_document(text, bigint) IS
    'Serialize per-corpus deltas under the corpus row lock, then reread canonical membership and text. A source write and all IDF accounting share one transaction. An analyzer-key mismatch raises with both keys and names python scripts/rebuild_memory_idf.py, which recomputes every document through this function.';

COMMENT ON COLUMN memory_idf_corpora.analyzer_version IS
    'PostgreSQL pg_catalog.english analyzer contract and exact server version (pg_catalog.english/v1/<server_version_num>). Analyzer or membership-contract changes, including any server version change (a patch release is enough), require the explicit transactional rebuild python scripts/rebuild_memory_idf.py; source writes and readers reject a version mismatch until it runs.';
