"""PostgreSQL coverage for the public ``record-revelation`` CLI path.

The test clones ``NEXUS_template`` into a disposable database and drops it
afterward. No save-slot or template database is mutated.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any, Iterator

import psycopg2  # type: ignore[import-untyped]
from psycopg2 import sql  # type: ignore[import-untyped]
import pytest

from nexus import cli
from nexus.api import db_pool, slot_utils
from scripts import new_story_setup


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    """Open a direct PostgreSQL connection to the disposable database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


@pytest.fixture(scope="module")
def disposable_db() -> Iterator[str]:
    """Yield a unique template clone and always drop it afterward."""

    dbname = f"qa_wt664_{uuid.uuid4().hex[:12]}"
    admin: Any = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        new_story_setup.initialize_slot_database(
            dbname,
            source_db="NEXUS_template",
        )
        yield dbname
    finally:
        new_story_setup.USE_POOL = original_use_pool
        pool = db_pool._pools.pop(dbname, None)
        if pool is not None:
            pool.closeall()
        if admin is not None:
            with admin.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (dbname,),
                )
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
            admin.close()


@pytest.fixture()
def route_disposable_db(
    disposable_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route the slot-only production entry point to the disposable clone."""

    def require_disposable_db(
        dbname: str | None = None,
        slot: int | None = None,
    ) -> str:
        if dbname is not None and dbname != disposable_db:
            raise AssertionError(f"unexpected database target: {dbname}")
        if slot is not None and slot != 4:
            raise AssertionError(f"unexpected slot target: {slot}")
        return disposable_db

    monkeypatch.setattr(db_pool, "require_slot_dbname", require_disposable_db)

    def slot_disposable_db(slot: int) -> str:
        if slot != 4:
            raise AssertionError(f"unexpected slot target: {slot}")
        return disposable_db

    monkeypatch.setattr(slot_utils, "slot_dbname", slot_disposable_db)


@pytest.fixture()
def revelation_case(disposable_db: str) -> dict[str, int]:
    """Create a bounded claim with one possessing and one unpossessing source."""

    conn = _connect(disposable_db)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO narrative_chunks (raw_text) VALUES (%s) "
                    "RETURNING id",
                    ("Issue 664 domain-validation fixture",),
                )
                chunk_id = int(cur.fetchone()[0])
                cur.execute(
                    "INSERT INTO entities (kind) "
                    "VALUES ('character'), ('character'), ('character') "
                    "RETURNING id"
                )
                source_entity_id, knower_entity_id, outsider_entity_id = (
                    int(row[0]) for row in cur.fetchall()
                )
                cur.execute(
                    """
                    INSERT INTO world_events (
                        event_type, tick_chunk_id, actor_entity_id,
                        world_layer, source, changed_fields, payload
                    ) VALUES (
                        'threat_issued', %s, %s, 'primary', 'resolver',
                        '{}', '{}'::jsonb
                    )
                    RETURNING id
                    """,
                    (chunk_id, source_entity_id),
                )
                world_event_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO claims (
                        world_event_id, summary, scope, source_chunk_id
                    ) VALUES (%s, %s, 'bounded', %s)
                    RETURNING id
                    """,
                    (world_event_id, "Issue 664 bounded claim", chunk_id),
                )
                claim_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO claim_awareness (
                        claim_id, knower_entity_id, source_tier,
                        source_chunk_id
                    ) VALUES (%s, %s, 'participant', %s)
                    """,
                    (claim_id, source_entity_id, chunk_id),
                )
    finally:
        conn.close()

    return {
        "claim_id": claim_id,
        "chunk_id": chunk_id,
        "source_entity_id": source_entity_id,
        "knower_entity_id": knower_entity_id,
        "outsider_entity_id": outsider_entity_id,
    }


def _missing_id(dbname: str, table: str) -> int:
    """Return an identifier absent from one disposable table."""

    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT COALESCE(max(id), 0) + 1 FROM {}").format(
                    sql.Identifier(table)
                )
            )
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def _run_record_revelation_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    claim_id: int,
    knower_entity_id: int,
    source_entity_id: int | None = None,
    source_chunk_id: int | None = None,
    as_json: bool = True,
) -> tuple[int, str, str]:
    """Run the genuine public CLI entry point and capture both streams."""

    argv = ["nexus"]
    if as_json:
        argv.append("--json")
    argv.extend(
        [
            "record-revelation",
            "--slot",
            "4",
            "--claim-id",
            str(claim_id),
            "--knower",
            str(knower_entity_id),
        ]
    )
    if source_entity_id is not None:
        argv.extend(("--source-entity-id", str(source_entity_id)))
    if source_chunk_id is not None:
        argv.extend(("--source-chunk-id", str(source_chunk_id)))
    monkeypatch.setattr(sys, "argv", argv)

    exit_code = cli.main()
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def _assert_json_error(output: str, error: str, message: str) -> None:
    """Require one structured error object and no traceback on either stream."""

    assert output == ""
    assert error == json.dumps({"error": message}) + "\n"
    assert json.loads(error) == {"error": message}
    assert "Traceback" not in output + error


def _assert_awareness_absent(
    dbname: str,
    *,
    claim_id: int,
    knower_entity_id: int,
) -> None:
    """Verify a rejected revelation did not persist target awareness."""

    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)
                FROM claim_awareness
                WHERE claim_id = %s AND knower_entity_id = %s
                """,
                (claim_id, knower_entity_id),
            )
            assert int(cur.fetchone()[0]) == 0
    finally:
        conn.close()


def test_record_revelation_valid_world_time_uses_real_cli_and_persistence(
    disposable_db: str,
    route_disposable_db: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An offset-aware timestamp retains the genuine CLI commit behavior."""

    del route_disposable_db
    world_time = "2189-10-17T18:24:00-04:00"
    conn = _connect(disposable_db)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO narrative_chunks (raw_text) VALUES (%s) "
                    "RETURNING id",
                    ("Issue 664 valid world-time control",),
                )
                chunk_id = int(cur.fetchone()[0])
                cur.execute(
                    "INSERT INTO entities (kind) "
                    "VALUES ('character'), ('character') RETURNING id"
                )
                source_entity_id, knower_entity_id = (
                    int(row[0]) for row in cur.fetchall()
                )
                cur.execute(
                    """
                    INSERT INTO world_events (
                        event_type, tick_chunk_id, actor_entity_id,
                        world_layer, source, changed_fields, payload
                    ) VALUES (
                        'threat_issued', %s, %s, 'primary', 'resolver',
                        '{}', '{}'::jsonb
                    )
                    RETURNING id
                    """,
                    (chunk_id, source_entity_id),
                )
                world_event_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO claims (
                        world_event_id, summary, scope, source_chunk_id
                    ) VALUES (%s, %s, 'bounded', %s)
                    RETURNING id
                    """,
                    (world_event_id, "Issue 664 bounded claim", chunk_id),
                )
                claim_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO claim_awareness (
                        claim_id, knower_entity_id, source_tier,
                        acquired_at_world_time, source_chunk_id
                    ) VALUES (%s, %s, 'participant', %s, %s)
                    """,
                    (
                        claim_id,
                        source_entity_id,
                        "2189-10-17T18:00:00-04:00",
                        chunk_id,
                    ),
                )
    finally:
        conn.close()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nexus",
            "--json",
            "record-revelation",
            "--slot",
            "4",
            "--claim-id",
            str(claim_id),
            "--knower",
            str(knower_entity_id),
            "--source-entity-id",
            str(source_entity_id),
            "--channel",
            "valid-offset-control",
            "--world-time",
            world_time,
            "--source-chunk-id",
            str(chunk_id),
        ],
    )

    assert cli.main() == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["success"] is True
    assert payload["slot"] == 4
    assert payload["dbname"] == disposable_db
    assert payload["claim_id"] == claim_id
    assert payload["knower_entity_id"] == knower_entity_id
    assert payload["source_tier"] == "told"
    assert payload["inserted"] is True

    conn = _connect(disposable_db)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT immediate_source_entity_id, channel,
                       acquired_at_world_time, source_chunk_id
                FROM claim_awareness
                WHERE id = %s
                """,
                (payload["claim_awareness_id"],),
            )
            awareness = cur.fetchone()
        assert awareness == (
            source_entity_id,
            "valid-offset-control",
            cli.parse_record_revelation_world_time(world_time),
            chunk_id,
        )
    finally:
        conn.close()

    assert cli.main() == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    duplicate = json.loads(captured.out)
    assert duplicate["success"] is True
    assert duplicate["claim_awareness_id"] == payload["claim_awareness_id"]
    assert duplicate["source_tier"] == "told"
    assert duplicate["inserted"] is False

    conn = _connect(disposable_db)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)
                FROM claim_awareness
                WHERE claim_id = %s AND knower_entity_id = %s
                """,
                (claim_id, knower_entity_id),
            )
            assert int(cur.fetchone()[0]) == 1
    finally:
        conn.close()


@pytest.mark.parametrize("as_json", [True, False], ids=["json", "human"])
def test_record_revelation_nonpossessing_teller_is_concise_domain_error(
    disposable_db: str,
    revelation_case: dict[str, int],
    route_disposable_db: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    as_json: bool,
) -> None:
    """A bounded claim cannot be told by an entity that does not possess it."""

    del route_disposable_db
    exit_code, output, error = _run_record_revelation_cli(
        monkeypatch,
        capsys,
        claim_id=revelation_case["claim_id"],
        knower_entity_id=revelation_case["knower_entity_id"],
        source_entity_id=revelation_case["outsider_entity_id"],
        as_json=as_json,
    )

    assert exit_code == 1
    message = (
        f"Entity {revelation_case['outsider_entity_id']} cannot reveal claim "
        f"{revelation_case['claim_id']}: the teller does not possess it"
    )
    if as_json:
        _assert_json_error(output, error, message)
    else:
        assert output == ""
        assert error == f"Error: {message}\n"
        assert "Traceback" not in output + error
    _assert_awareness_absent(
        disposable_db,
        claim_id=revelation_case["claim_id"],
        knower_entity_id=revelation_case["knower_entity_id"],
    )


@pytest.mark.parametrize("tier", ["told", "granted"])
def test_record_revelation_missing_claim_is_json_error_for_both_tiers(
    disposable_db: str,
    revelation_case: dict[str, int],
    route_disposable_db: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tier: str,
) -> None:
    """Both told and granted paths validate claim existence before insertion."""

    del route_disposable_db
    missing_claim_id = _missing_id(disposable_db, "claims")
    source_entity_id = revelation_case["source_entity_id"] if tier == "told" else None
    exit_code, output, error = _run_record_revelation_cli(
        monkeypatch,
        capsys,
        claim_id=missing_claim_id,
        knower_entity_id=revelation_case["knower_entity_id"],
        source_entity_id=source_entity_id,
    )

    assert exit_code == 1
    _assert_json_error(
        output,
        error,
        f"Claim {missing_claim_id} does not exist",
    )


def test_record_revelation_missing_knower_is_json_error(
    disposable_db: str,
    revelation_case: dict[str, int],
    route_disposable_db: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing recipient entity fails as a structured operator error."""

    del route_disposable_db
    missing_knower_id = _missing_id(disposable_db, "entities")
    exit_code, output, error = _run_record_revelation_cli(
        monkeypatch,
        capsys,
        claim_id=revelation_case["claim_id"],
        knower_entity_id=missing_knower_id,
    )

    assert exit_code == 1
    _assert_json_error(
        output,
        error,
        f"Knower entity {missing_knower_id} does not exist",
    )


def test_record_revelation_missing_source_entity_is_json_error(
    disposable_db: str,
    revelation_case: dict[str, int],
    route_disposable_db: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing teller entity fails before the source-chain insert."""

    del route_disposable_db
    missing_source_id = _missing_id(disposable_db, "entities")
    exit_code, output, error = _run_record_revelation_cli(
        monkeypatch,
        capsys,
        claim_id=revelation_case["claim_id"],
        knower_entity_id=revelation_case["knower_entity_id"],
        source_entity_id=missing_source_id,
    )

    assert exit_code == 1
    _assert_json_error(
        output,
        error,
        f"Source entity {missing_source_id} does not exist",
    )
    _assert_awareness_absent(
        disposable_db,
        claim_id=revelation_case["claim_id"],
        knower_entity_id=revelation_case["knower_entity_id"],
    )


def test_record_revelation_missing_source_chunk_is_json_error(
    disposable_db: str,
    revelation_case: dict[str, int],
    route_disposable_db: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing provenance chunk fails before the awareness insert."""

    del route_disposable_db
    missing_chunk_id = _missing_id(disposable_db, "narrative_chunks")
    exit_code, output, error = _run_record_revelation_cli(
        monkeypatch,
        capsys,
        claim_id=revelation_case["claim_id"],
        knower_entity_id=revelation_case["knower_entity_id"],
        source_chunk_id=missing_chunk_id,
    )

    assert exit_code == 1
    _assert_json_error(
        output,
        error,
        f"Source chunk {missing_chunk_id} does not exist",
    )
    _assert_awareness_absent(
        disposable_db,
        claim_id=revelation_case["claim_id"],
        knower_entity_id=revelation_case["knower_entity_id"],
    )
