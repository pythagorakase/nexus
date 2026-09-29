"""The IDF rebuild behind a stale analyzer key (issue #1013).

A PostgreSQL patch release changes ``server_version_num`` and so the analyzer
key every IDF corpus row carries; writes then fail in the trigger until
``scripts/rebuild_memory_idf.py`` recomputes the corpus. The PostgreSQL tests
write only to disposable ``qa640_1013_*`` template clones, which the shared
fixture drops. The migration-parity test is offline.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
import json
import logging
from pathlib import Path
import re
from typing import Any, Iterator
import uuid

import psycopg2
import pytest
from psycopg2 import sql

from nexus.agents.memnon.utils.idf_dictionary import (
    ANALYZER_KEY_SQL,
    REBUILD_COMMAND,
    IDFDictionary,
    IDFStateError,
    analyzer_mismatch_message,
)
from nexus.agents.orrery.reconstruction import playable_narrative_predicate
from nexus.database import (
    AmbiguousCommit,
    commit_transaction,
    database_url,
    is_connection_failure,
    maintenance_connection,
)
from scripts import rebuild_memory_idf as rebuild
from scripts.migrate import is_db_locked
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_committed_chunk,
    seed_protagonist,
)

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"

# A key no real server produces, so the test never depends on which PostgreSQL
# release the owner's machine runs.
STALE_KEY = "pg_catalog.english/v1/0"

_SYNC_BODY = re.compile(
    r"sync_memory_idf_document\(kind text, doc_id bigint\)\s*"
    r"RETURNS void LANGUAGE plpgsql AS \$body\$(.*?)\$body\$;",
    re.DOTALL,
)
_MISMATCH_RAISE = re.compile(
    r"RAISE EXCEPTION '(IDF analyzer mismatch[^']*)'"
    r"(, kind(?:, expected_analyzer, actual_analyzer)?);"
)


def _sync_body(path: Path) -> str:
    match = _SYNC_BODY.search(path.read_text(encoding="utf-8"))
    assert match is not None, f"{path.name} does not define sync_memory_idf_document"
    return match.group(1)


def test_migration_133_changes_only_the_mismatch_text() -> None:
    """133's function is 114's, predicate inlined, except the RAISE text."""
    original = _sync_body(MIGRATIONS / "114_slot_scoped_idf.py").replace(
        "__PLAYABLE__", playable_narrative_predicate()
    )
    replacement = _sync_body(MIGRATIONS / "133_idf_rebuild_command.sql")

    old_raise = _MISMATCH_RAISE.search(original)
    new_raise = _MISMATCH_RAISE.search(replacement)
    assert old_raise is not None and new_raise is not None
    assert old_raise.group(2) == ", kind"
    assert new_raise.group(2) == ", kind, expected_analyzer, actual_analyzer"
    # The trigger and the reader raise one text, with the same three values.
    assert new_raise.group(1) == analyzer_mismatch_message("%", "%", "%")
    assert REBUILD_COMMAND in new_raise.group(1)

    def normalized(body: str) -> str:
        return " ".join(_MISMATCH_RAISE.sub("RAISE_MISMATCH;", body).split())

    assert normalized(replacement) == normalized(original)


def test_differing_lexemes_counts_each_lexeme_once() -> None:
    """A changed frequency, an addition, and a removal each count one lexeme."""
    before = {"harbor": 2, "keeper": 1, "lantern": 1}
    after = {"harbor": 2, "keeper": 2, "ship": 1}
    assert rebuild.differing_lexemes(before, after) == 3
    assert rebuild.differing_lexemes(before, dict(before)) == 0
    assert rebuild.differing_lexemes({}, {"ship": 1}) == 1


pg = pytest.mark.requires_postgres


def _seed_summary(dbname: str, anchor_chunk: int, text: str) -> int:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO world_events
                (event_type, tick_chunk_id, world_layer, source,
                 changed_fields, payload)
            SELECT type, %s, 'primary', 'retrograde', '{}', '{}'::jsonb
            FROM event_types ORDER BY type LIMIT 1 RETURNING id
            """,
            (anchor_chunk,),
        )
        event = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO retrograde_summaries
                (world_event_id, recorded_at_chunk_id, chronology, summary_text)
            VALUES (%s, %s, 'deep_past', %s) RETURNING id
            """,
            (event, anchor_chunk, text),
        )
        return int(cur.fetchone()[0])


@pytest.fixture()
def seeded_clone() -> Iterator[str]:
    """A fresh template clone with a player, two committed chunks, one summary."""
    with disposable_slot_database("qa640_1013_idf") as dbname:
        seed_protagonist(dbname)
        first = seed_committed_chunk(
            dbname, raw_text="The lighthouse keeper counts ships at dusk.", scene=1
        )
        seed_committed_chunk(
            dbname, raw_text="Ships drift past the drowned lighthouse.", scene=2
        )
        _seed_summary(dbname, first, "The harbor burned in the deep past.")
        yield dbname


def _server_key(dbname: str) -> str:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {ANALYZER_KEY_SQL}")
        return str(cur.fetchone()[0])


def _idf_state(dbname: str) -> dict[str, Any]:
    """Every row of the three IDF tables, including epochs and digests."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT corpus_kind, analyzer_version, document_count, corpus_epoch "
            "FROM memory_idf_corpora ORDER BY corpus_kind"
        )
        corpora = cur.fetchall()
        cur.execute(
            "SELECT corpus_kind, document_id, content_digest, lexemes "
            "FROM memory_idf_documents ORDER BY 1, 2"
        )
        documents = cur.fetchall()
        cur.execute(
            "SELECT corpus_kind, lexeme, document_frequency "
            "FROM memory_idf_lexemes ORDER BY 1, 2"
        )
        lexemes = cur.fetchall()
    return {"corpora": corpora, "documents": documents, "lexemes": lexemes}


def _set_keys(dbname: str, key: str) -> None:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("UPDATE memory_idf_corpora SET analyzer_version = %s", (key,))
        assert cur.rowcount == 2


def _fresh_recompute(dbname: str) -> list[tuple[str, str, int]]:
    """Recompute every document through the trigger function, then roll back."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM memory_idf_lexemes")
        cur.execute("DELETE FROM memory_idf_documents")
        cur.execute("UPDATE memory_idf_corpora SET document_count = 0")
        cur.execute(
            "SELECT count(sync_memory_idf_document('narrative', id)) "
            "FROM narrative_chunks"
        )
        cur.execute(
            "SELECT count(sync_memory_idf_document('retrograde_summary', id)) "
            "FROM retrograde_summaries"
        )
        cur.execute(
            "SELECT corpus_kind, lexeme, document_frequency "
            "FROM memory_idf_lexemes ORDER BY 1, 2"
        )
        recomputed = cur.fetchall()
        conn.rollback()
    return recomputed


def _ts_stat(dbname: str) -> list[tuple[str, str, int]]:
    """An independent recount from PostgreSQL's own ts_stat over each corpus."""
    narrative = (
        "SELECT to_tsvector('pg_catalog.english', nc.raw_text) FROM narrative_chunks "
        "nc WHERE EXISTS (SELECT 1 FROM chunk_metadata cm WHERE cm.chunk_id = nc.id) "
        "AND " + playable_narrative_predicate()
    )
    summaries = (
        "SELECT to_tsvector('pg_catalog.english', summary_text) "
        "FROM retrograde_summaries"
    )
    rows: list[tuple[str, str, int]] = []
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        for kind, source in (
            ("narrative", narrative),
            ("retrograde_summary", summaries),
        ):
            cur.execute("SELECT word, ndoc FROM ts_stat(%s)", (source,))
            rows.extend((kind, word, ndoc) for word, ndoc in cur.fetchall())
    return sorted(rows)


def _insert_chunk(dbname: str, text: str) -> None:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
            "VALUES (%s, %s) RETURNING id",
            (text, text),
        )


def _drop_corpus_rows(dbname: str, *kinds: str) -> None:
    """Delete corpus rows and the projection rows that reference them."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        for table in (
            "memory_idf_lexemes",
            "memory_idf_documents",
            "memory_idf_corpora",
        ):
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE corpus_kind = ANY(%s)").format(
                    sql.Identifier(table)
                ),
                (list(kinds),),
            )


@pg
def test_stale_key_blocks_writes_until_the_rebuild_recomputes(
    seeded_clone: str,
) -> None:
    """Stale key: writes and reads fail naming the command; the rebuild heals it."""
    dbname = seeded_clone
    server = _server_key(dbname)

    # A fresh clone is seeded with the live server's key (new_story_setup).
    fresh = _idf_state(dbname)
    assert [(row[0], row[1], row[2]) for row in fresh["corpora"]] == [
        ("narrative", server, 2),
        ("retrograde_summary", server, 1),
    ]
    assert fresh["lexemes"] == _ts_stat(dbname)

    _set_keys(dbname, STALE_KEY)
    stale = _idf_state(dbname)
    expected_message = analyzer_mismatch_message("narrative", server, STALE_KEY)
    with pytest.raises(psycopg2.errors.RaiseException) as raised:
        _insert_chunk(dbname, "A write the stale key must refuse.")
    assert raised.value.diag.message_primary == expected_message
    assert f"{REBUILD_COMMAND} --slot N (or --template / --all)" in expected_message
    with pytest.raises(IDFStateError) as reader_error:
        IDFDictionary(database_url(dbname)).get_idf("lighthouse")
    assert str(reader_error.value) == expected_message
    assert _idf_state(dbname) == stale

    # --dry-run reports the stale keys and counts and changes nothing.
    dry = rebuild.rebuild_database(dbname, dry_run=True)
    assert (dry.status, dry.server_key, dry.error) == ("dry_run", server, None)
    assert [
        (c.corpus_kind, c.key_before, c.stale, c.documents_before, c.source_documents)
        for c in dry.corpora
    ] == [
        ("narrative", STALE_KEY, True, 2, 2),
        ("retrograde_summary", STALE_KEY, True, 1, 1),
    ]
    assert all(c.key_after is None for c in dry.corpora)
    assert _idf_state(dbname) == stale

    report = rebuild.rebuild_database(dbname)
    assert (report.status, report.server_key, report.error) == (
        "rebuilt",
        server,
        None,
    )
    assert [
        (
            c.corpus_kind,
            c.key_before,
            c.key_after,
            c.documents_before,
            c.documents_after,
            c.lexeme_rows_differing,
        )
        for c in report.corpora
    ] == [
        ("narrative", STALE_KEY, server, 2, 2, 0),
        ("retrograde_summary", STALE_KEY, server, 1, 1, 0),
    ]
    rebuilt = _idf_state(dbname)
    assert [row[:3] for row in rebuilt["corpora"]] == [
        ("narrative", server, 2),
        ("retrograde_summary", server, 1),
    ]
    # Each epoch advanced past its pre-rebuild value.
    assert all(
        after[3] > before[3]
        for after, before in zip(rebuilt["corpora"], stale["corpora"])
    )
    assert rebuilt["documents"] == stale["documents"]
    assert rebuilt["lexemes"] == _fresh_recompute(dbname) == _ts_stat(dbname)

    # Writes and reads succeed again.
    seed_committed_chunk(dbname, raw_text="A lantern answers the lighthouse.", scene=3)
    assert IDFDictionary(database_url(dbname)).get_idf("lantern") > 0
    final = _idf_state(dbname)
    assert final["corpora"][0][2] == 3
    assert final["lexemes"] == _ts_stat(dbname)


@pg
def test_rebuild_counts_each_corrupted_lexeme_once(seeded_clone: str) -> None:
    """A wrong frequency and a stray lexeme are each one differing row, then healed."""
    dbname = seeded_clone
    _set_keys(dbname, STALE_KEY)
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE memory_idf_lexemes SET document_frequency = 2 "
            "WHERE corpus_kind = 'narrative' AND lexeme = 'keeper' "
            "AND document_frequency = 1"
        )
        assert cur.rowcount == 1
        cur.execute(
            "INSERT INTO memory_idf_lexemes (corpus_kind, lexeme, document_frequency) "
            "VALUES ('retrograde_summary', 'qa1013bogus', 1)"
        )
    assert _idf_state(dbname)["lexemes"] != _ts_stat(dbname)

    report = rebuild.rebuild_database(dbname)
    assert (report.status, report.error) == ("rebuilt", None)
    assert [(c.corpus_kind, c.lexeme_rows_differing) for c in report.corpora] == [
        ("narrative", 1),
        ("retrograde_summary", 1),
    ]
    assert _idf_state(dbname)["lexemes"] == _ts_stat(dbname)


@pg
def test_rebuild_seeds_a_missing_corpus_row(
    seeded_clone: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing corpus row blocks its writes until the tool seeds it at the live key.

    With no rows at all both are seeded; without the table the tool fails.
    """
    dbname = seeded_clone
    server = _server_key(dbname)
    before = _idf_state(dbname)
    first_chunk = before["documents"][0][1]
    _drop_corpus_rows(dbname, "retrograde_summary")
    missing = _idf_state(dbname)
    assert [row[0] for row in missing["corpora"]] == ["narrative"]

    # The trigger's SELECT ... INTO STRICT finds no corpus row.
    with pytest.raises(psycopg2.errors.NoDataFound):
        _seed_summary(dbname, first_chunk, "A write the missing row must refuse.")
    assert _idf_state(dbname) == missing

    # --dry-run names the missing row and changes nothing.
    dry = rebuild.rebuild_database(dbname, dry_run=True)
    assert (dry.status, dry.error) == ("dry_run", None)
    assert [
        (c.corpus_kind, c.key_before, c.documents_before, c.source_documents)
        for c in dry.corpora
    ] == [("narrative", server, 2, 2), ("retrograde_summary", None, 0, 1)]
    assert not any(c.seeded for c in dry.corpora)
    assert _idf_state(dbname) == missing

    assert rebuild.main(["--dbname", dbname, "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True
    (database,) = printed["databases"]
    assert database["status"] == "rebuilt"
    summary_lexemes = sum(1 for row in _ts_stat(dbname) if row[0] != "narrative")
    assert [
        (
            c["corpus_kind"],
            c["seeded"],
            c["key_before"],
            c["key_after"],
            c["documents_before"],
            c["documents_after"],
            c["lexeme_rows_differing"],
        )
        for c in database["corpora"]
    ] == [
        ("narrative", False, server, server, 2, 2, 0),
        ("retrograde_summary", True, None, server, 0, 1, summary_lexemes),
    ]
    rebuilt = _idf_state(dbname)
    assert [row[:3] for row in rebuilt["corpora"]] == [
        ("narrative", server, 2),
        ("retrograde_summary", server, 1),
    ]
    assert rebuilt["documents"] == before["documents"]
    assert rebuilt["lexemes"] == before["lexemes"] == _ts_stat(dbname)

    _seed_summary(dbname, first_chunk, "The harbor lights return.")
    assert _idf_state(dbname)["corpora"][1][2] == 2

    # With no corpus rows at all, the rebuild seeds both.
    _drop_corpus_rows(dbname, *rebuild.CORPORA)
    report = rebuild.rebuild_database(dbname)
    assert (report.status, report.error) == ("rebuilt", None)
    assert [
        (c.corpus_kind, c.seeded, c.documents_before, c.documents_after)
        for c in report.corpora
    ] == [("narrative", True, 0, 2), ("retrograde_summary", True, 0, 2)]
    assert _idf_state(dbname)["lexemes"] == _ts_stat(dbname)

    # Without the table there is nothing to seed; it fails naming the runner.
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("DROP TABLE memory_idf_corpora CASCADE")
    report = rebuild.rebuild_database(dbname)
    assert report.status == "failed"
    assert "lacks memory_idf_corpora" in (report.error or "")
    assert "(python scripts/migrate.py)" in (report.error or "")


@pg
def test_guard_rejects_document_count_drift_and_the_rollback_keeps_state(
    seeded_clone: str,
) -> None:
    """The guard refuses a count change; rolling back restores every row."""
    dbname = seeded_clone
    _set_keys(dbname, STALE_KEY)
    before_state = _idf_state(dbname)
    server = _server_key(dbname)
    conn = maintenance_connection(dbname, operation="idf_rebuild_guard_test")
    with closing(conn):
        with conn.cursor() as cur:
            rebuild.require_schema(cur, dbname)
            cur.execute(
                "LOCK TABLE narrative_chunks, chunk_metadata, retrograde_summaries "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
            before = rebuild.corpus_states(cur, lock=True)
            cur.execute(rebuild.RECOMPUTE_SQL)
            # The genuine counts pass the guard.
            rebuild.verify_rebuild(cur, before, server)
            drifted = dict(before)
            drifted["narrative"] = replace(before["narrative"], document_count=3)
            with pytest.raises(
                rebuild.IDFRebuildError, match="narrative document_count 3 -> 2"
            ):
                rebuild.verify_rebuild(cur, drifted, server)
            with pytest.raises(rebuild.IDFRebuildError, match="differs from server"):
                rebuild.verify_rebuild(cur, before, STALE_KEY)
            # A seeded corpus starts at 0 and must end at the documents the
            # trigger admits, counted before the recompute.
            rebuild.verify_rebuild(cur, before, server, seeded={"narrative": 2})
            with pytest.raises(
                rebuild.IDFRebuildError,
                match="narrative seeded: document_count 2, expected 3",
            ):
                rebuild.verify_rebuild(cur, before, server, seeded={"narrative": 3})
        conn.rollback()
    assert _idf_state(dbname) == before_state


@pg
def test_failures_roll_back_and_exit_nonzero(
    seeded_clone: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fault mid-recompute or a missing source table leaves the database as it was."""
    dbname = seeded_clone
    _set_keys(dbname, STALE_KEY)
    before = _idf_state(dbname)
    second_chunk = before["documents"][1][1]

    # A real database-side fault after the projections were cleared.
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE FUNCTION qa1013_refuse_document() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.corpus_kind = 'narrative'
                    AND NEW.document_id = {int(second_chunk)} THEN
                    RAISE EXCEPTION 'qa1013 injected recompute fault';
                END IF;
                RETURN NEW;
            END $$;
            CREATE TRIGGER qa1013_refuse_document BEFORE INSERT
            ON memory_idf_documents FOR EACH ROW
            EXECUTE FUNCTION qa1013_refuse_document();
            """
        )
    report = rebuild.rebuild_database(dbname)
    assert report.status == "failed"
    assert "qa1013 injected recompute fault" in (report.error or "")
    assert _idf_state(dbname) == before

    assert rebuild.main(["--dbname", dbname, "--json"]) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is False
    assert printed["databases"][0]["status"] == "failed"
    assert _idf_state(dbname) == before

    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("DROP TRIGGER qa1013_refuse_document ON memory_idf_documents")
        cur.execute("ALTER TABLE retrograde_summaries RENAME TO qa1013_summaries")
    report = rebuild.rebuild_database(dbname)
    assert report.status == "failed"
    assert "lacks retrograde_summaries" in (report.error or "")
    assert _idf_state(dbname) == before

    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("ALTER TABLE qa1013_summaries RENAME TO retrograde_summaries")
    assert rebuild.main(["--dbname", dbname]) == 0
    assert f"{dbname}: rebuilt" in capsys.readouterr().out
    assert [row[1] for row in _idf_state(dbname)["corpora"]] == [
        _server_key(dbname)
    ] * 2


def _drop_connection_at_commit(dbname: str) -> None:
    """Make every commit that wrote memory_idf_corpora lose its connection.

    A deferred constraint trigger fires inside COMMIT and terminates its own
    backend, so the driver itself raises a connection-loss OperationalError
    from ``conn.commit()``. Nothing in the client is replaced.
    """
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE FUNCTION qa1013_drop_connection() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_terminate_backend(pg_backend_pid());
                RETURN NULL;
            END $$;
            CREATE CONSTRAINT TRIGGER qa1013_drop_connection
            AFTER INSERT OR UPDATE ON memory_idf_corpora
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION qa1013_drop_connection();
            """
        )


@pg
def test_connection_lost_at_commit_is_commit_unknown_not_a_rollback(
    seeded_clone: str,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A connection lost during COMMIT reports an unknown outcome, never a rollback."""
    dbname = seeded_clone
    _set_keys(dbname, STALE_KEY)
    before = _idf_state(dbname)
    _drop_connection_at_commit(dbname)

    # The injected fault is a real driver connection loss during COMMIT, the
    # shape commit_transaction turns into AmbiguousCommit.
    probe = maintenance_connection(dbname, operation="idf_rebuild_fault_probe")
    with closing(probe):
        with probe.cursor() as cur:
            cur.execute("UPDATE memory_idf_corpora SET corpus_epoch = corpus_epoch")
        with pytest.raises(AmbiguousCommit, match=dbname) as caught:
            commit_transaction(probe)
    assert isinstance(caught.value.__cause__, psycopg2.OperationalError)
    assert is_connection_failure(caught.value.__cause__)

    report = rebuild.rebuild_database(dbname)
    assert (report.status, report.corpora) == ("commit_unknown", [])
    error = report.error or ""
    assert error.startswith(
        f"commit outcome unknown (Ambiguous commit for database {dbname}: "
    )
    assert "--dry-run shows the database's current keys and counts" in error
    assert "Re-running the rebuild is safe: it recomputes" in error
    assert "connection already closed" not in error
    assert "rolled back" not in error

    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="nexus.rebuild_memory_idf"):
        assert rebuild.main(["--dbname", dbname, "--json"]) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is False
    (database,) = printed["databases"]
    assert database["status"] == "commit_unknown"
    assert database["error"].startswith("commit outcome unknown (Ambiguous commit")
    logged = [record.getMessage() for record in caplog.records]
    assert any("commit outcome unknown" in message for message in logged)
    assert not any(
        "rolled back" in message or "connection already closed" in message
        for message in logged
    )

    # This fault ends the backend before the commit record, so --dry-run
    # still shows the stale keys; re-running the rebuild is safe and heals it.
    dry = rebuild.rebuild_database(dbname, dry_run=True)
    assert [c.key_before for c in dry.corpora] == [STALE_KEY, STALE_KEY]
    assert _idf_state(dbname) == before
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("DROP TRIGGER qa1013_drop_connection ON memory_idf_corpora")
    healed = rebuild.rebuild_database(dbname)
    assert (healed.status, healed.error) == ("rebuilt", None)
    assert [row[1] for row in _idf_state(dbname)["corpora"]] == [
        _server_key(dbname)
    ] * 2


def _set_read_only(dbname: str, on: bool) -> None:
    admin = connect("postgres")
    admin.autocommit = True
    with closing(admin), admin.cursor() as cur:
        if on:
            cur.execute(
                sql.SQL(
                    "ALTER DATABASE {} SET default_transaction_read_only = on"
                ).format(sql.Identifier(dbname))
            )
        else:
            cur.execute(
                sql.SQL("ALTER DATABASE {} RESET default_transaction_read_only").format(
                    sql.Identifier(dbname)
                )
            )


@pg
def test_locked_database_needs_the_write_locked_slot_override(
    seeded_clone: str,
) -> None:
    """A locked database is skipped, even by --dry-run, until given the override."""
    dbname = seeded_clone
    _set_keys(dbname, STALE_KEY)
    before = _idf_state(dbname)
    _set_read_only(dbname, True)
    try:
        assert is_db_locked(dbname)
        skipped = rebuild.rebuild_database(dbname)
        assert (skipped.status, skipped.locked, skipped.corpora) == (
            "skipped_locked",
            True,
            [],
        )
        assert _idf_state(dbname) == before

        dry_skipped = rebuild.rebuild_database(dbname, dry_run=True)
        assert (dry_skipped.status, dry_skipped.locked, dry_skipped.corpora) == (
            "skipped_locked",
            True,
            [],
        )

        # An explicitly named locked database fails loudly, as migrate.py does.
        with pytest.raises(SystemExit) as refused:
            rebuild.main(["--dbname", dbname, "--dry-run"])
        assert refused.value.code == 2
        with pytest.raises(SystemExit) as refused:
            rebuild.main(["--dbname", dbname])
        assert refused.value.code == 2
        assert _idf_state(dbname) == before

        dry = rebuild.rebuild_database(dbname, dry_run=True, write_locked_slot=True)
        assert (dry.status, dry.locked) == ("dry_run", True)
        assert (
            rebuild.main(["--dbname", dbname, "--write-locked-slot", "--dry-run"]) == 0
        )
        assert all(corpus.stale for corpus in dry.corpora)
        assert _idf_state(dbname) == before
        assert is_db_locked(dbname)

        report = rebuild.rebuild_database(dbname, write_locked_slot=True)
        assert (report.status, report.locked) == ("rebuilt", True)
        assert [row[1] for row in _idf_state(dbname)["corpora"]] == [
            _server_key(dbname)
        ] * 2
        # The override lasted one session; the database stays locked.
        assert is_db_locked(dbname)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SHOW default_transaction_read_only")
            assert cur.fetchone()[0] == "on"
    finally:
        _set_read_only(dbname, False)
    assert not is_db_locked(dbname)


@pg
def test_absent_database_is_reported_and_untouched() -> None:
    """A missing target is skipped in a fleet run and refused when named."""
    dbname = f"qa640_1013_absent_{uuid.uuid4().hex[:12]}"
    report = rebuild.rebuild_database(dbname)
    assert (report.status, report.corpora, report.error) == ("absent", [], None)
    # Named explicitly, a missing database fails loudly, as migrate.py does.
    with pytest.raises(psycopg2.OperationalError, match=dbname):
        rebuild.main(["--dbname", dbname, "--dry-run"])
    with closing(connect("postgres")) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        assert cur.fetchone() is None
