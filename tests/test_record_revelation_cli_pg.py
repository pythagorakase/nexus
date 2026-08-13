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

    dbname = f"qa664_{uuid.uuid4().hex[:12]}"
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
