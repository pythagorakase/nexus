"""Real-PostgreSQL contract coverage for migration 077."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import psycopg2  # type: ignore[import-untyped]
import pytest

from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def migration_074_schema() -> Iterator[Any]:
    """Build the exact pre-077 project surface in a rollback-only schema."""

    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA migration_077_test")
            cur.execute("SET LOCAL search_path = migration_077_test, public")
            cur.execute("CREATE TABLE entities (id bigint PRIMARY KEY)")
            cur.execute("CREATE TABLE places (id bigint PRIMARY KEY)")
            cur.execute("CREATE TABLE narrative_chunks (id bigint PRIMARY KEY)")
            cur.execute(
                """
                CREATE TABLE event_types (
                    type text PRIMARY KEY,
                    category text NOT NULL,
                    severity text NOT NULL,
                    description text NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE character_project_states (
                    id bigserial PRIMARY KEY,
                    character_entity_id bigint NOT NULL REFERENCES entities(id),
                    project_type text NOT NULL
                        CHECK (project_type IN ('plan_relocation')),
                    status text NOT NULL
                        CHECK (status IN (
                            'active', 'paused', 'stalled',
                            'abandoned', 'completed'
                        )),
                    stage text NOT NULL
                        CHECK (stage IN ('saving', 'scouting', 'committing')),
                    target_place_id bigint REFERENCES places(id),
                    progress numeric(5,4) NOT NULL DEFAULT 0,
                    stall_count integer NOT NULL DEFAULT 0,
                    next_eligible_at_world_time timestamptz,
                    source_chunk_id bigint REFERENCES narrative_chunks(id),
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    CHECK (progress >= 0 AND progress <= 1),
                    CHECK (stall_count >= 0),
                    CHECK (status <> 'completed' OR target_place_id IS NOT NULL)
                )
                """
            )
            cur.execute("INSERT INTO entities (id) VALUES (1), (2)")
            cur.execute("INSERT INTO places (id) VALUES (1)")
            cur.execute("INSERT INTO narrative_chunks (id) VALUES (1)")
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_migration_077_preserves_progress_and_replaces_completed_target_guard(
    migration_074_schema: Any,
) -> None:
    """Apply 077 to a 074-only table and exercise both affected invariants."""

    migration_sql = (
        Path(__file__).parents[2] / "migrations" / "077_recruit_ally_projects.sql"
    ).read_text()
    conn = migration_074_schema
    with conn.cursor() as cur:
        cur.execute(migration_sql)
        cur.execute(
            """
            SELECT conname, pg_get_constraintdef(oid, true)
            FROM pg_constraint
            WHERE conrelid = 'character_project_states'::regclass
              AND contype = 'c'
            ORDER BY conname
            """
        )
        constraints = dict(cur.fetchall())

        assert any(
            "progress >=" in definition and "progress <=" in definition
            for definition in constraints.values()
        )
        assert "character_project_states_completed_target_check" in constraints
        assert "character_project_states_target_by_type_check" in constraints
        assert not any(
            "status <> 'completed'" in definition and "project_type" not in definition
            for definition in constraints.values()
        )

        cur.execute(
            """
            INSERT INTO character_project_states (
                character_entity_id, project_type, status, stage,
                target_character_entity_id, progress, stall_count,
                source_chunk_id
            ) VALUES (
                1, 'recruit_ally', 'completed', 'sealing_commitment',
                2, 1, 0, 1
            )
            """
        )

        cur.execute("SAVEPOINT invalid_progress")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO character_project_states (
                    character_entity_id, project_type, status, stage,
                    target_place_id, progress, stall_count, source_chunk_id
                ) VALUES (
                    2, 'plan_relocation', 'active', 'saving',
                    NULL, 1.1, 0, 1
                )
                """
            )
        cur.execute("ROLLBACK TO SAVEPOINT invalid_progress")
