"""Real-PostgreSQL contract coverage for migration 084."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
import pytest

from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def migration_083_schema() -> Iterator[Any]:
    """Build the exact project/tag surface migration 084 must widen."""

    conn = psycopg2.connect(get_slot_db_url(slot=2))
    schema = f"migration_084_{uuid4().hex[:12]}"
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(
                """
                CREATE TABLE event_types (
                    type text PRIMARY KEY,
                    category text NOT NULL,
                    severity text NOT NULL,
                    description text
                );
                CREATE TABLE tag_category_registry (
                    category text NOT NULL,
                    entity_kind entity_kind NOT NULL,
                    prompt_order integer NOT NULL,
                    description text,
                    deprecated boolean NOT NULL DEFAULT false,
                    replacement_categories text[],
                    PRIMARY KEY (category, entity_kind)
                );
                CREATE TABLE tags (
                    id bigserial PRIMARY KEY,
                    tag text UNIQUE NOT NULL,
                    category text NOT NULL,
                    is_ephemeral boolean NOT NULL DEFAULT false,
                    clearance_kind entity_tag_clearance_kind,
                    reapplication_policy entity_tag_reapplication_policy,
                    clear_on jsonb,
                    synonym_for bigint,
                    deprecated boolean NOT NULL DEFAULT false,
                    description text,
                    CHECK (is_ephemeral = (clearance_kind IS NOT NULL))
                );
                CREATE TABLE character_project_states (
                    id bigserial PRIMARY KEY,
                    character_entity_id bigint NOT NULL,
                    project_type text NOT NULL,
                    status text NOT NULL,
                    stage text NOT NULL,
                    target_place_id bigint,
                    target_character_entity_id bigint,
                    target_faction_entity_id bigint,
                    progress numeric(5,4) NOT NULL DEFAULT 0,
                    stall_count integer NOT NULL DEFAULT 0,
                    next_eligible_at_world_time timestamptz,
                    source_chunk_id bigint,
                    CONSTRAINT character_project_states_project_type_check
                        CHECK (project_type IN ('plan_relocation', 'recruit_ally')),
                    CONSTRAINT character_project_states_stage_by_type_check CHECK (
                        (project_type = 'plan_relocation'
                            AND stage IN ('saving', 'scouting', 'committing'))
                        OR
                        (project_type = 'recruit_ally'
                            AND stage IN (
                                'sounding_out', 'earning_trust',
                                'sealing_commitment'
                            ))
                    ),
                    CONSTRAINT character_project_states_target_by_type_check CHECK (
                        (project_type = 'plan_relocation'
                            AND target_character_entity_id IS NULL)
                        OR
                        (project_type = 'recruit_ally'
                            AND target_place_id IS NULL
                            AND target_character_entity_id IS NOT NULL)
                    ),
                    CONSTRAINT character_project_states_completed_target_check CHECK (
                        status <> 'completed'
                        OR (project_type = 'plan_relocation'
                            AND target_place_id IS NOT NULL)
                        OR (project_type = 'recruit_ally'
                            AND target_character_entity_id IS NOT NULL)
                    )
                )
                """
            )
            cur.execute(
                """
                INSERT INTO character_project_states (
                    character_entity_id, project_type, status, stage,
                    target_place_id, progress
                ) VALUES (1, 'plan_relocation', 'active', 'saving', NULL, 0.25);
                INSERT INTO character_project_states (
                    character_entity_id, project_type, status, stage,
                    target_character_entity_id, progress
                ) VALUES (2, 'recruit_ally', 'active', 'earning_trust', 3, 0.5)
                """
            )
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_migration_084_widens_projects_and_registers_vocabulary(
    migration_083_schema: Any,
) -> None:
    migration_sql = (
        Path(__file__).parents[2] / "migrations" / "084_build_venture_projects.sql"
    ).read_text()
    conn = migration_083_schema
    with conn.cursor() as cur:
        cur.execute(migration_sql)
        cur.execute(
            """
            SELECT conname, pg_get_constraintdef(oid, true), obj_description(oid)
            FROM pg_constraint
            WHERE conrelid = 'character_project_states'::regclass
              AND conname = ANY(%s)
            ORDER BY conname
            """,
            (
                [
                    "character_project_states_project_type_check",
                    "character_project_states_stage_by_type_check",
                    "character_project_states_target_by_type_check",
                    "character_project_states_completed_target_check",
                ],
            ),
        )
        constraints = {name: (definition, comment) for name, definition, comment in cur}
        assert len(constraints) == 4
        assert all(comment for _definition, comment in constraints.values())
        assert all(
            "build_venture" in definition
            for definition, _comment in constraints.values()
        )

        cur.execute(
            """
            INSERT INTO character_project_states (
                character_entity_id, project_type, status, stage, progress
            ) VALUES (4, 'build_venture', 'completed', 'opening_doors', 1)
            """
        )
        cur.execute("SAVEPOINT build_target")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO character_project_states (
                    character_entity_id, project_type, status, stage,
                    target_faction_entity_id
                ) VALUES (5, 'build_venture', 'active', 'laying_groundwork', 9)
                """
            )
        cur.execute("ROLLBACK TO SAVEPOINT build_target")

        cur.execute(
            "SELECT project_type, stage FROM character_project_states "
            "WHERE character_entity_id IN (1, 2) ORDER BY character_entity_id"
        )
        assert cur.fetchall() == [
            ("plan_relocation", "saving"),
            ("recruit_ally", "earning_trust"),
        ]
        cur.execute(
            "SELECT type FROM event_types WHERE type LIKE 'build_venture_%' "
            "ORDER BY type"
        )
        assert [row[0] for row in cur] == [
            "build_venture_abandoned",
            "build_venture_completed",
            "build_venture_milestone",
            "build_venture_progressed",
            "build_venture_stalled",
            "build_venture_started",
        ]
        cur.execute(
            """
            SELECT t.category, t.is_ephemeral, t.deprecated, t.description,
                   r.entity_kind::text, r.deprecated
            FROM tags t
            JOIN tag_category_registry r ON r.category = t.category
            WHERE t.tag = 'proprietor'
              AND r.entity_kind = 'character'::entity_kind
            """
        )
        category, ephemeral, deprecated, description, kind, registry_deprecated = (
            cur.fetchone()
        )
        assert category == "role.function"
        assert ephemeral is False
        assert deprecated is False
        assert "BUILD_VENTURE" in description
        assert kind == "character"
        assert registry_deprecated is False
