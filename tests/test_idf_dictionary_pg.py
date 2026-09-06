"""IDF proofs using disposable real PostgreSQL slots; never mutate live saves.

Required production tables: narrative_chunks, chunk_metadata and
retrograde_summaries. The shared factory clones NEXUS_template and cleans up.
"""

from __future__ import annotations

from contextlib import closing
from importlib import import_module
import math
from pathlib import Path
from typing import Any, Iterator

import pytest
from psycopg2.extensions import cursor as PostgreSQLCursor

from nexus.agents.memnon.utils.db_access import execute_multi_model_hybrid_search
from nexus.agents.memnon.utils.idf_dictionary import IDFDictionary, IDFStateError
from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER
from tests.pg_fixtures import connect, disposable_slot_database, sqlalchemy_url

pytestmark = pytest.mark.requires_postgres

migration = import_module("migrations.114_slot_scoped_idf")


def _url(dbname: str) -> str:
    return sqlalchemy_url(dbname).render_as_string(hide_password=False)


def _insert(cursor: Any, text: str, *, metadata: bool = True) -> int:
    cursor.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text, authorial_directives)
        VALUES (%s, %s, '[]'::jsonb) RETURNING id
        """,
        (text, text),
    )
    chunk_id = cursor.fetchone()[0]
    if metadata:
        _metadata(cursor, chunk_id)
    return chunk_id


def _metadata(cursor: Any, chunk_id: int) -> None:
    cursor.execute(
        """
        INSERT INTO chunk_metadata
            (chunk_id, season, episode, scene, world_layer, time_delta, generation_date)
        VALUES (%s, 1, 1, %s, 'primary', interval '0 seconds', now())
        """,
        (chunk_id, chunk_id),
    )


@pytest.fixture()
def idf_slot() -> Iterator[str]:
    with disposable_slot_database("qa762_idf") as dbname:
        yield dbname


def _assert_exact_counts(dbname: str, corpus: str = "narrative") -> None:
    """Compare trigger state against an independent production SQL recount."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        from nexus.agents.orrery.reconstruction import playable_narrative_predicate

        source = (
            "SELECT to_tsvector('pg_catalog.english', nc.raw_text) "
            "FROM narrative_chunks nc JOIN chunk_metadata cm ON cm.chunk_id=nc.id "
            "WHERE " + playable_narrative_predicate()
            if corpus == "narrative"
            else "SELECT to_tsvector('pg_catalog.english', summary_text) "
            "FROM retrograde_summaries"
        )
        cur.execute("SELECT word, ndoc FROM ts_stat(%s)", (source,))
        expected = dict(cur.fetchall())
        cur.execute(
            "SELECT lexeme, document_frequency FROM memory_idf_lexemes "
            "WHERE corpus_kind = %s",
            (corpus,),
        )
        assert dict(cur.fetchall()) == expected
        cur.execute(f"SELECT count(*) FROM ({source}) AS corpus")
        expected_count = cur.fetchone()[0]
        cur.execute(
            "SELECT document_count FROM memory_idf_corpora WHERE corpus_kind=%s",
            (corpus,),
        )
        assert cur.fetchone()[0] == expected_count


def test_slot_and_corpus_isolation(
    idf_slot: str, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    with disposable_slot_database("qa762_other") as other:
        with closing(connect(other)) as conn, conn:
            with conn.cursor() as cur:
                cur.execute("DROP FUNCTION maintain_memory_idf() CASCADE")
                cur.execute("DROP FUNCTION lock_memory_idf_corpora() CASCADE")
                cur.execute("DROP FUNCTION sync_memory_idf_document(text, bigint)")
                cur.execute(
                    "DROP TABLE memory_idf_lexemes, memory_idf_documents, memory_idf_corpora"
                )
                _insert(cur, "Dragon dragon dragon sleeps")
                _insert(cur, "Dragon flies")
            migration.run(conn)  # Prove backfill of preexisting accepted rows.
        with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
            _insert(cur, "Starship docks")
            _insert(cur, "Starship flies")
        first, second = IDFDictionary(_url(idf_slot)), IDFDictionary(_url(other))
        assert "dragon" not in first.build_dictionary()
        assert "starship" not in second.build_dictionary()
        assert second.get_idf("dragon") == 0.0
        assert first.get_idf("dragon") == math.log(3)
        with closing(connect(other)) as conn:
            with pytest.raises(IDFStateError, match="slot mismatch"):
                first.generate_weighted_query("dragon", connection=conn)
        with pytest.raises(IDFStateError, match="corpus mismatch"):
            first.generate_weighted_query("starship", corpus_kind="retrograde_summary")
        summary = first.for_corpus("retrograde_summary")
        assert summary.build_dictionary() == {}
        assert summary.total_docs == 0
        assert list(tmp_path.iterdir()) == []
        _assert_exact_counts(other)
        _assert_exact_counts(idf_slot)


def test_edits_deletes_rollback_and_membership(idf_slot: str) -> None:
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        first = _insert(cur, "Running running wolves")
        highest = _insert(cur, "Solar clouds")
        pending = _insert(cur, "Unready observatory", metadata=False)
        prologue = _insert(cur, "Synthetic quartz")
        cur.execute(
            "UPDATE narrative_chunks SET authorial_directives = jsonb_build_array(%s::text) WHERE id=%s",
            (RETROGRADE_PROLOGUE_MARKER, prologue),
        )
    reader = IDFDictionary(_url(idf_slot))
    weights = reader.build_dictionary()
    assert reader.total_docs == 2
    assert "synthet" not in weights and "observatori" not in weights
    epoch = reader.corpus_epoch
    # Same lexemes and same MAX(id); content edit must still advance the epoch.
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE narrative_chunks SET raw_text='Wolves running' WHERE id=%s",
            (first,),
        )
    assert reader.build_dictionary() == weights
    assert reader.corpus_epoch == epoch + 1
    epoch = reader.corpus_epoch
    with closing(connect(idf_slot)) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM narrative_chunks WHERE id=%s", (first,))
        conn.rollback()
    assert reader.build_dictionary() == weights
    assert reader.corpus_epoch == epoch
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        _metadata(cur, pending)
        cur.execute(
            "UPDATE narrative_chunks SET authorial_directives='[]' WHERE id=%s",
            (prologue,),
        )
        cur.execute("DELETE FROM chunk_metadata WHERE chunk_id=%s", (highest,))
        cur.execute("DELETE FROM narrative_chunks WHERE id=%s", (first,))
    weights = reader.build_dictionary()
    assert reader.total_docs == 2
    assert "observatori" in weights and "synthet" in weights
    assert "wolf" not in weights and "solar" not in weights
    _assert_exact_counts(idf_slot)


def test_reader_snapshot_and_next_commit(idf_slot: str) -> None:
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        chunk = _insert(cur, "Old observatory")
    reader = IDFDictionary(_url(idf_slot))
    with closing(connect(idf_slot)) as snapshot:
        snapshot.set_session(readonly=True, isolation_level="REPEATABLE READ")
        reader.generate_weighted_query("observatory", connection=snapshot)
        old_epoch = reader.corpus_epoch
        with closing(connect(idf_slot)) as writer, writer, writer.cursor() as cur:
            cur.execute(
                "UPDATE narrative_chunks SET raw_text='New zeppelin' WHERE id=%s",
                (chunk,),
            )
        reader.generate_weighted_query("observatory", connection=snapshot)
        assert reader.corpus_epoch == old_epoch
        assert "observatori" in reader.idf_dict and "zeppelin" not in reader.idf_dict
    reader.build_dictionary()
    assert reader.corpus_epoch == old_epoch + 1
    assert "zeppelin" in reader.idf_dict and "observatori" not in reader.idf_dict


def test_postgres_lexemes_and_query_quoting(idf_slot: str) -> None:
    phrase = "Children's co-operating foxes: café O'Brien + neutron & starship"
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        _insert(cur, phrase)
        cur.execute("SELECT tsvector_to_array(to_tsvector('english', %s))", (phrase,))
        expected = cur.fetchone()[0]
    reader = IDFDictionary(_url(idf_slot))
    query = reader.generate_weighted_query(phrase, max_terms=100)
    assert sorted(reader.build_dictionary()) == expected
    with closing(connect(idf_slot)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT to_tsvector('english', %s) @@ to_tsquery('english', %s)",
            (phrase, query),
        )
        assert cur.fetchone()[0]
    assert reader.generate_weighted_query("and the of") == ""
    assert reader.get_idf("the") == 0.0


def test_mismatched_state_fails_through_production_search(idf_slot: str) -> None:
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        _insert(cur, "Silver observatory")
        cur.execute(
            "UPDATE memory_idf_corpora SET analyzer_version='stale' WHERE corpus_kind='narrative'"
        )
    reader = IDFDictionary(_url(idf_slot))
    with pytest.raises(IDFStateError, match="analyzer mismatch"):
        execute_multi_model_hybrid_search(
            _url(idf_slot),
            "silver",
            {},
            {},
            vector_weight=0.0,
            text_weight=1.0,
            idf_dict=reader,
        )
    with closing(connect(idf_slot)) as conn, conn.cursor() as cur:
        with pytest.raises(Exception, match="analyzer mismatch"):
            cur.execute("UPDATE narrative_chunks SET raw_text='Stale writer'")
        conn.rollback()


def test_empty_and_unseen_inputs_still_require_valid_corpus_state(
    idf_slot: str,
) -> None:
    """A bounded lookup cannot mistake missing/versioned state for zero frequency."""
    reader = IDFDictionary(_url(idf_slot))
    for mutation, error in (
        (
            "UPDATE memory_idf_corpora SET analyzer_version='stale' "
            "WHERE corpus_kind='narrative'",
            "analyzer mismatch",
        ),
        (
            "DELETE FROM memory_idf_corpora WHERE corpus_kind='narrative'",
            "Missing IDF corpus state",
        ),
    ):
        with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
            cur.execute(mutation)
        for lookup in (
            lambda: reader.get_idfs([]),
            lambda: reader.get_idfs(["the", "quartz"]),
            lambda: reader.get_idf("the"),
            lambda: reader.generate_weighted_query(""),
        ):
            with pytest.raises(IDFStateError, match=error):
                lookup()


def test_truncation_clears_counts(idf_slot: str) -> None:
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        _insert(cur, "Truncatable aurora")
    reader = IDFDictionary(_url(idf_slot))
    reader.build_dictionary()
    epoch = reader.corpus_epoch
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        cur.execute("TRUNCATE chunk_metadata CASCADE")
    assert reader.build_dictionary() == {}
    assert reader.total_docs == 0 and reader.corpus_epoch > epoch
    _assert_exact_counts(idf_slot)


def _summary(cursor: Any, anchor: int, text: str) -> int:
    cursor.execute(
        """
        INSERT INTO world_events
            (event_type, tick_chunk_id, world_layer, source, changed_fields, payload)
        SELECT type, %s, 'primary', 'retrograde', '{}', '{}'::jsonb
        FROM event_types ORDER BY type LIMIT 1 RETURNING id
        """,
        (anchor,),
    )
    event = cursor.fetchone()[0]
    cursor.execute(
        """
        INSERT INTO retrograde_summaries
            (world_event_id, recorded_at_chunk_id, chronology, summary_text)
        VALUES (%s, %s, 'deep_past', %s) RETURNING id
        """,
        (event, anchor, text),
    )
    return cursor.fetchone()[0]


def test_summary_counts_and_production_search(idf_slot: str) -> None:
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        anchor = _insert(cur, "Silver launch")
        summary_id = _summary(cur, anchor, "Ancient zeppelin zeppelin")
        _summary(cur, anchor, "Ancient zeppelin")
    reader = IDFDictionary(_url(idf_slot))
    summary = reader.for_corpus("retrograde_summary")
    assert reader.get_idf("zeppelin") == math.log(2)
    assert summary.get_idf("zeppelin") == 0.0
    assert summary.total_docs == 2
    summary_epoch = summary.corpus_epoch
    reader.build_dictionary()
    narrative_epoch = reader.corpus_epoch
    results = execute_multi_model_hybrid_search(
        _url(idf_slot),
        "zeppelin",
        {},
        {},
        vector_weight=0.0,
        text_weight=1.0,
        idf_dict=reader,
    )
    assert {row["content_type"] for row in results} == {"retrograde_summary"}
    assert len(results) == 2
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE retrograde_summaries SET summary_text='Ancient dirigible' WHERE id=%s",
            (summary_id,),
        )
    summary.build_dictionary()
    assert summary.corpus_epoch == summary_epoch + 1
    _assert_exact_counts(idf_slot, "retrograde_summary")
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        cur.execute("DELETE FROM retrograde_summaries WHERE id=%s", (summary_id,))
    summary.build_dictionary()
    assert "dirig" not in summary.idf_dict and summary.total_docs == 1
    reader.build_dictionary()
    assert reader.corpus_epoch == narrative_epoch
    _assert_exact_counts(idf_slot, "retrograde_summary")


def test_concurrent_writers_preserve_document_frequencies(idf_slot: str) -> None:
    from concurrent.futures import ThreadPoolExecutor

    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        first = _insert(cur, "Shared starship")
        second = _insert(cur, "Shared starship")
    reader = IDFDictionary(_url(idf_slot))
    reader.build_dictionary()
    epoch = reader.corpus_epoch

    def update(chunk: int, text: str) -> None:
        with closing(connect(idf_slot)) as writer, writer, writer.cursor() as cur:
            cur.execute(
                "UPDATE narrative_chunks SET raw_text=%s WHERE id=%s", (text, chunk)
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(update, first, "Shared dragon"),
            pool.submit(update, second, "Shared dragon"),
        ]
        for future in futures:
            future.result(timeout=10)
    reader.build_dictionary()
    assert reader.corpus_epoch == epoch + 2
    assert reader.idf_dict == {"share": 0.0, "dragon": 0.0}
    assert reader.get_idfs(["dragons", "starship", "the"]) == {
        "dragons": 0.0,
        "starship": math.log(3),
        "the": 0.0,
    }
    _assert_exact_counts(idf_slot)


@pytest.mark.parametrize("corpus", ("narrative", "retrograde_summary"))
def test_query_reads_stay_bounded_when_unrelated_vocabulary_grows(
    idf_slot: str, monkeypatch: pytest.MonkeyPatch, corpus: str
) -> None:
    """Vocabulary growth cannot expand query transfers, weights, or examined rows."""
    import psycopg2

    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        if corpus == "narrative":
            first = _insert(cur, "Alpha")
            _insert(cur, "Beta")
            _insert(cur, "Beta")
        else:
            anchor = _insert(cur, "Summary anchor")
            first = _summary(cur, anchor, "Alpha")
            _summary(cur, anchor, "Beta")
            _summary(cur, anchor, "Beta")
    reader = IDFDictionary(_url(idf_slot), corpus_kind=corpus)
    original_connect = psycopg2.connect
    captured: list[tuple[bytes, dict[str, int]]] = []

    class CapturingCursor(PostgreSQLCursor):
        def fetchone(self) -> Any:
            row = super().fetchone()
            # Observe actual database output before the reader can trim it.
            captured.append((self.query, row[5]))
            return row

    def capture_connect(*args: Any, **kwargs: Any) -> Any:
        return original_connect(*args, **kwargs, cursor_factory=CapturingCursor)

    def check_lookups() -> list[tuple[bytes, set[str]]]:
        calls = [
            (
                lambda: reader.generate_weighted_query("ALPHAS beta quartz the"),
                "'quartz' | 'alpha' | 'beta'",
                {"alpha", "beta", "quartz"},
            ),
            (lambda: reader.get_idf("ALPHAS beta"), math.log(2), {"alpha", "beta"}),
            (
                lambda: reader.get_idfs(
                    ["ALPHAS", "beta", "quartz", "the", "ALPHAS beta", "ALPHAS"]
                ),
                {
                    "ALPHAS": math.log(2),
                    "beta": math.log(4 / 3),
                    "quartz": math.log(4),
                    "the": 0.0,
                    "ALPHAS beta": math.log(2),
                },
                {"alpha", "beta", "quartz"},
            ),
            (
                lambda: reader.get_high_idf_terms("ALPHAS beta quartz", threshold=0.5),
                ["alpha", "quartz"],
                {"alpha", "beta", "quartz"},
            ),
            (lambda: reader.get_weight_class("quartz"), "C", {"quartz"}),
            (lambda: reader.get_idfs([]), {}, set()),
        ]
        queries = []
        with monkeypatch.context() as patch:
            patch.setattr(psycopg2, "connect", capture_connect)
            for lookup, expected, lexemes in calls:
                captured.clear()
                assert lookup() == expected
                assert set(reader.idf_dict) <= lexemes
                assert captured
                for query, frequencies in captured:
                    assert set(frequencies) <= lexemes
                    queries.append((query, lexemes))
        return queries

    check_lookups()
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        # Preserve document count and alpha/beta frequencies while growing the
        # corpus through the actual source writer and its accounting triggers.
        text = "Alpha " + " ".join(f"unrelated{i:04d}" for i in range(4096))
        if corpus == "narrative":
            cur.execute(
                "UPDATE narrative_chunks SET raw_text=%s WHERE id=%s", (text, first)
            )
        else:
            cur.execute(
                "UPDATE retrograde_summaries SET summary_text=%s WHERE id=%s",
                (text, first),
            )
        cur.execute("ANALYZE memory_idf_lexemes")
    assert len(reader.build_dictionary()) > 4000
    assert reader.total_docs == 3
    queries = check_lookups()

    def examined_lexeme_rows(plan: dict[str, Any]) -> int:
        examined = 0
        if plan.get("Relation Name") == "memory_idf_lexemes":
            examined = (
                sum(
                    plan.get(field, 0)
                    for field in (
                        "Actual Rows",
                        "Rows Removed by Filter",
                        "Rows Removed by Index Recheck",
                    )
                )
                * plan["Actual Loops"]
            )
        return examined + sum(
            examined_lexeme_rows(child) for child in plan.get("Plans", [])
        )

    with closing(connect(idf_slot)) as conn, conn.cursor() as cur:
        for query, lexemes in queries:
            # Replay the actual lookup SQL: trimming a full read in Python or
            # filtering after a full database scan cannot satisfy this bound.
            cur.execute(b"EXPLAIN (ANALYZE, FORMAT JSON, TIMING OFF) " + query)
            plan = cur.fetchone()[0][0]["Plan"]
            assert examined_lexeme_rows(plan) <= 2 * len(lexemes), plan


def test_fresh_slot_from_migrated_source_has_empty_own_state(idf_slot: str) -> None:
    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        _insert(cur, "Source dragon vocabulary")
    with disposable_slot_database("qa762_fresh", source_db=idf_slot) as fresh:
        reader = IDFDictionary(_url(fresh))
        assert reader.build_dictionary() == {}
        assert reader.total_docs == 0
        assert reader.corpus_epoch == 0
        with closing(connect(fresh)) as conn, conn, conn.cursor() as cur:
            _insert(cur, "Fresh starship vocabulary")
        assert "dragon" not in reader.build_dictionary()
        assert reader.total_docs == 1
        _assert_exact_counts(fresh)
    source_reader = IDFDictionary(_url(idf_slot))
    assert "dragon" in source_reader.build_dictionary()
    assert "starship" not in source_reader.idf_dict


@pytest.mark.parametrize("lookup_kind", ("query", "batch", "single", "high_terms"))
def test_shared_reader_scores_its_own_snapshot(
    idf_slot: str, monkeypatch: pytest.MonkeyPatch, lookup_kind: str
) -> None:
    """A later lookup cannot replace an in-flight request's older weights."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, current_thread

    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        first = _insert(cur, "Alpha")
        second = _insert(cur, "Beta")
        third = _insert(cur, "Beta")
    reader = IDFDictionary(_url(idf_slot))
    original_read = reader._read
    owner = current_thread()
    read_complete = Event()
    release_read = Event()

    def pause_after_read(*args: Any, **kwargs: Any) -> Any:
        result = original_read(*args, **kwargs)
        if current_thread() is not owner:
            read_complete.set()
            if not release_read.wait(timeout=10):
                raise TimeoutError("Main thread did not release the first read")
        return result

    def lookup() -> Any:
        if lookup_kind == "query":
            return reader.generate_weighted_query("alpha beta", max_terms=1)
        if lookup_kind == "batch":
            return reader.get_idfs(["alpha", "beta"])
        if lookup_kind == "single":
            return reader.get_idf("alpha")
        return reader.get_high_idf_terms("alpha beta", threshold=0.5)

    monkeypatch.setattr(reader, "_read", pause_after_read)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lookup)
        try:
            assert read_complete.wait(timeout=10)
            with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE narrative_chunks SET raw_text='Beta' WHERE id=%s", (first,)
                )
                cur.execute(
                    "UPDATE narrative_chunks SET raw_text='Alpha' WHERE id=ANY(%s)",
                    ([second, third],),
                )
            later = lookup()
        finally:
            release_read.set()
        earlier = future.result(timeout=10)
    if lookup_kind == "query":
        assert earlier == "'alpha'" and later == "'beta'"
    elif lookup_kind == "batch":
        assert earlier == {"alpha": math.log(2), "beta": math.log(4 / 3)}
        assert later == {"alpha": math.log(4 / 3), "beta": math.log(2)}
    elif lookup_kind == "single":
        assert earlier == math.log(2) and later == math.log(4 / 3)
    else:
        assert earlier == ["alpha"] and later == ["beta"]


def test_idf_columns_carry_database_documentation(idf_slot: str) -> None:
    with closing(connect(idf_slot)) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, a.attname FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.oid
            WHERE n.nspname='public' AND c.relname = ANY(%s)
                AND a.attnum > 0 AND NOT a.attisdropped
                AND NULLIF(col_description(c.oid, a.attnum), '') IS NULL
            """,
            (["memory_idf_corpora", "memory_idf_documents", "memory_idf_lexemes"],),
        )
        assert cur.fetchall() == []


def test_source_lock_precedes_world_time_refresh(idf_slot: str) -> None:
    """A metadata writer must wait before holding a row needed by clock refresh."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from time import monotonic

    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        first = _insert(cur, "Clock source alpha")
        second = _insert(cur, "Clock source beta")
    with (
        closing(connect(idf_slot)) as owner,
        closing(connect(idf_slot)) as waiter,
        closing(connect(idf_slot)) as observer,
    ):
        owner_pid = owner.get_backend_pid()
        waiter_pid = waiter.get_backend_pid()
        with owner.cursor() as cur:
            cur.execute("SET lock_timeout='5s'")
            cur.execute(
                "UPDATE narrative_chunks SET raw_text='Changed clock alpha' WHERE id=%s",
                (first,),
            )

        def change_other_metadata() -> None:
            with waiter, waiter.cursor() as cur:
                cur.execute("SET lock_timeout='5s'")
                cur.execute(
                    "UPDATE chunk_metadata SET scene=scene+1 WHERE chunk_id=%s",
                    (second,),
                )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(change_other_metadata)
            try:
                deadline = monotonic() + 5
                while True:
                    with observer.cursor() as cur:
                        cur.execute("SELECT pg_blocking_pids(%s)", (waiter_pid,))
                        if owner_pid in cur.fetchone()[0]:
                            break
                    assert (
                        monotonic() < deadline
                    ), "Metadata writer did not reach corpus lock"
                    Event().wait(0.01)
                # This production trigger updates every chunk_metadata row.
                # If the waiter already owns B, owner->B->corpus->owner deadlocks.
                with owner.cursor() as cur:
                    cur.execute(
                        "UPDATE chunk_metadata SET time_delta=time_delta+interval '1 second' WHERE chunk_id=%s",
                        (first,),
                    )
                owner.commit()
                future.result(timeout=10)
            finally:
                owner.rollback()
    _assert_exact_counts(idf_slot)


def test_data_clone_migrates_without_unlocking_source(idf_slot: str) -> None:
    """A read-only pre-IDF corpus is migrated only in its new disposable clone."""
    from psycopg2 import sql

    with closing(connect(idf_slot)) as conn, conn, conn.cursor() as cur:
        chunk = _insert(cur, "Protected dragon corpus")
        cur.execute("DROP FUNCTION maintain_memory_idf() CASCADE")
        cur.execute("DROP FUNCTION lock_memory_idf_corpora() CASCADE")
        cur.execute("DROP FUNCTION sync_memory_idf_document(text, bigint)")
        cur.execute(
            "DROP TABLE memory_idf_lexemes, memory_idf_documents, memory_idf_corpora"
        )
        cur.execute("DELETE FROM schema_migrations WHERE version='114'")
    with closing(connect("postgres")) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "ALTER DATABASE {} SET default_transaction_read_only=on"
                ).format(sql.Identifier(idf_slot))
            )
    with disposable_slot_database(
        "qa762_corpus_copy", source_db=idf_slot, include_data=True
    ) as copied:
        reader = IDFDictionary(_url(copied))
        assert "dragon" in reader.build_dictionary()
        assert reader.total_docs == 1
        with closing(connect(copied)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE narrative_chunks SET raw_text='Independent starship' WHERE id=%s",
                (chunk,),
            )
        assert "dragon" not in reader.build_dictionary()
    with closing(connect(idf_slot)) as conn, conn.cursor() as cur:
        cur.execute("SHOW default_transaction_read_only")
        assert cur.fetchone()[0] == "on"
        cur.execute("SELECT to_regclass('public.memory_idf_corpora')")
        assert cur.fetchone()[0] is None
        cur.execute("SELECT raw_text FROM narrative_chunks WHERE id=%s", (chunk,))
        assert cur.fetchone()[0] == "Protected dragon corpus"
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version='114')"
        )
        assert not cur.fetchone()[0]
