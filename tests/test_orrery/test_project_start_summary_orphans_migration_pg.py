"""PostgreSQL regression for project-start Retrograde summary hygiene."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator
import uuid

import psycopg2
import pytest

from nexus.agents.orrery.retrograde_persistence import PROJECT_STARTED_EVENT_TYPES
from scripts import migrate
from tests.pg_fixtures import disposable_slot_database


pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).parents[2]
MIGRATION_PATH = ROOT / "migrations" / "101_delete_project_start_summary_orphans.sql"


def _connect(dbname: str) -> Any:
    """Open a direct PostgreSQL connection to a disposable clone."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


@pytest.fixture()
def disposable_retrograde_hygiene_db() -> Iterator[str]:
    """Yield an initialized pre-101 test state and remove it afterward."""

    source_db = os.environ.get("NEXUS_TEST_TEMPLATE_DB", "NEXUS_template")
    assert source_db == "NEXUS_template" or source_db.startswith("qa672_")
    with disposable_slot_database("qa672", source_db=source_db) as dbname:
        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM schema_migrations WHERE version = '101'")
                assert cur.rowcount == 1
        yield dbname


def _insert_summary(
    cur: Any,
    chunk_id: int,
    event_type: str,
    *,
    stamped: bool = True,
) -> tuple[int, int]:
    """Insert one Retrograde summary and return event and summary IDs."""

    event_ref = f"qa672_{uuid.uuid4().hex}"
    payload = {
        "retrograde_event_ref": event_ref,
        "summary": f"Legacy summary for {event_type}.",
        "chronology": "deep_past",
    }
    cur.execute(
        """
        INSERT INTO world_events (
            event_type,
            tick_chunk_id,
            world_layer,
            source,
            changed_fields,
            payload
        ) VALUES (%s, %s, 'primary', 'retrograde', '{}', %s::jsonb)
        RETURNING id
        """,
        (event_type, chunk_id, json.dumps(payload)),
    )
    world_event_id = int(cur.fetchone()[0])
    cur.execute(
        """
        INSERT INTO retrograde_summaries (
            world_event_id,
            recorded_at_chunk_id,
            chronology,
            summary_text,
            embedding_generated_at
        ) VALUES (
            %s,
            %s,
            'deep_past',
            %s,
            CASE WHEN %s
                THEN '2000-01-01T00:00:00+00:00'::timestamptz
                ELSE NULL
            END
        )
        RETURNING id
        """,
        (world_event_id, chunk_id, payload["summary"], stamped),
    )
    return world_event_id, int(cur.fetchone()[0])


def _apply_migration_101(dbname: str) -> tuple[str, ...]:
    """Apply migration 101 through the production migration entry point."""

    assert (
        "101",
        "delete_project_start_summary_orphans",
        MIGRATION_PATH,
    ) in migrate.discover_migrations()
    conn = _connect(dbname)
    try:
        assert migrate.apply_migration(
            conn,
            "101",
            "delete_project_start_summary_orphans",
            MIGRATION_PATH,
        )
        return tuple(conn.notices)
    finally:
        conn.close()


def _rerun_migration_101(dbname: str) -> tuple[str, ...]:
    """Re-run the SQL after migration tracking has recorded version 101."""

    conn = _connect(dbname)
    try:
        conn.notices.clear()
        with conn.cursor() as cur:
            cur.execute(MIGRATION_PATH.read_text())
        conn.commit()
        return tuple(conn.notices)
    finally:
        conn.close()


def test_migration_101_deletes_only_stamped_vectorless_project_starts(
    disposable_retrograde_hygiene_db: str,
) -> None:
    """Delete every excluded orphan while preserving all protected controls."""

    dbname = disposable_retrograde_hygiene_db
    conn = _connect(dbname)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO narrative_chunks (raw_text) VALUES (%s) RETURNING id",
                    ("Issue 672 disposable recording boundary",),
                )
                chunk_id = int(cur.fetchone()[0])
                project_rows = [
                    _insert_summary(cur, chunk_id, event_type)
                    for event_type in PROJECT_STARTED_EVENT_TYPES.values()
                ]
                vector_event_id, vector_summary_id = _insert_summary(
                    cur,
                    chunk_id,
                    PROJECT_STARTED_EVENT_TYPES["plan_relocation"],
                )
                nonproject_event_id, nonproject_summary_id = _insert_summary(
                    cur,
                    chunk_id,
                    "relocation_plan_progressed",
                )
                unstamped_event_id, unstamped_summary_id = _insert_summary(
                    cur,
                    chunk_id,
                    PROJECT_STARTED_EVENT_TYPES["recruit_ally"],
                    stamped=False,
                )
                cur.execute(
                    """
                    CREATE TABLE retrograde_summary_embeddings_0001d (
                        summary_id bigint NOT NULL
                            REFERENCES retrograde_summaries(id) ON DELETE CASCADE,
                        model text NOT NULL,
                        embedding vector(1) NOT NULL,
                        created_at timestamptz NOT NULL DEFAULT now(),
                        PRIMARY KEY (summary_id, model)
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO retrograde_summary_embeddings_0001d (
                        summary_id,
                        model,
                        embedding
                    ) VALUES (%s, 'migration-101-test', '[0]')
                    """,
                    (vector_summary_id,),
                )
    finally:
        conn.close()

    first_notices = _apply_migration_101(dbname)

    assert (
        "migration 101 deleted 6 project-start Retrograde summary orphan(s)"
        in "".join(first_notices)
    )
    project_event_ids = [event_id for event_id, _summary_id in project_rows]
    project_summary_ids = [summary_id for _event_id, summary_id in project_rows]
    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM retrograde_summaries WHERE id = ANY(%s) ORDER BY id",
                (
                    project_summary_ids
                    + [vector_summary_id, nonproject_summary_id, unstamped_summary_id],
                ),
            )
            assert [row[0] for row in cur.fetchall()] == sorted(
                [vector_summary_id, nonproject_summary_id, unstamped_summary_id]
            )
            cur.execute(
                "SELECT id FROM world_events WHERE id = ANY(%s) ORDER BY id",
                (
                    project_event_ids
                    + [vector_event_id, nonproject_event_id, unstamped_event_id],
                ),
            )
            assert [row[0] for row in cur.fetchall()] == sorted(
                project_event_ids
                + [vector_event_id, nonproject_event_id, unstamped_event_id]
            )
            cur.execute("SELECT summary_id FROM retrograde_summary_embeddings_0001d")
            assert cur.fetchall() == [(vector_summary_id,)]
    finally:
        conn.close()

    rerun_notices = _rerun_migration_101(dbname)

    assert (
        "migration 101 deleted 0 project-start Retrograde summary orphan(s)"
        in "".join(rerun_notices)
    )
    conn = _connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM retrograde_summaries WHERE id = ANY(%s) ORDER BY id",
                ([vector_summary_id, nonproject_summary_id, unstamped_summary_id],),
            )
            assert [row[0] for row in cur.fetchall()] == sorted(
                [vector_summary_id, nonproject_summary_id, unstamped_summary_id]
            )
    finally:
        conn.close()
