"""Real-PostgreSQL contract coverage for migration 085."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
import pytest

from nexus.api.slot_utils import get_slot_db_url

pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def migration_084_schema() -> Iterator[Any]:
    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        with conn.cursor() as cur:
            schema = f"migration_085_{uuid4().hex[:12]}"
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(
                """
                CREATE TABLE event_types (
                    type text PRIMARY KEY, category text NOT NULL,
                    severity text NOT NULL, description text
                );
                CREATE TABLE character_project_states (
                    id bigserial PRIMARY KEY, character_entity_id bigint NOT NULL,
                    project_type text NOT NULL, status text NOT NULL,
                    stage text NOT NULL, target_place_id bigint,
                    target_character_entity_id bigint,
                    target_faction_entity_id bigint,
                    progress numeric(5,4) NOT NULL DEFAULT 0,
                    stall_count integer NOT NULL DEFAULT 0,
                    next_eligible_at_world_time timestamptz, source_chunk_id bigint,
                    CONSTRAINT character_project_states_project_type_check CHECK (
                        project_type IN (
                            'plan_relocation', 'recruit_ally', 'build_venture'
                        )),
                    CONSTRAINT character_project_states_stage_by_type_check CHECK (
                        (project_type = 'plan_relocation'
                            AND stage IN ('saving', 'scouting', 'committing')) OR
                        (project_type = 'recruit_ally'
                            AND stage IN (
                                'sounding_out', 'earning_trust',
                                'sealing_commitment'
                            )) OR
                        (project_type = 'build_venture'
                            AND stage IN (
                                'laying_groundwork', 'securing_backing',
                                'opening_doors'
                            ))),
                    CONSTRAINT character_project_states_target_by_type_check CHECK (
                        (project_type = 'plan_relocation'
                            AND target_character_entity_id IS NULL) OR
                        (project_type = 'recruit_ally'
                            AND target_place_id IS NULL
                            AND target_character_entity_id IS NOT NULL) OR
                        (project_type = 'build_venture'
                            AND target_place_id IS NULL
                            AND target_character_entity_id IS NULL
                            AND target_faction_entity_id IS NULL)),
                    CONSTRAINT character_project_states_completed_target_check CHECK (
                        status <> 'completed' OR
                        (project_type = 'plan_relocation'
                            AND target_place_id IS NOT NULL) OR
                        (project_type = 'recruit_ally'
                            AND target_character_entity_id IS NOT NULL) OR
                        project_type='build_venture')
                );
                INSERT INTO character_project_states
                    (character_entity_id, project_type, status, stage,
                     target_character_entity_id, target_faction_entity_id)
                    VALUES (1,'recruit_ally','active','sounding_out',2,9);
                INSERT INTO character_project_states
                    (character_entity_id,project_type,status,stage)
                    VALUES (3,'build_venture','active','laying_groundwork');
                """
            )
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_migration_085_widens_constraints_and_seeds_events(
    migration_084_schema: Any,
) -> None:
    sql = (
        Path(__file__).parents[2] / "migrations/085_pursue_romance_projects.sql"
    ).read_text()
    with migration_084_schema.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "SELECT conname,pg_get_constraintdef(oid,true),obj_description(oid) "
            "FROM pg_constraint WHERE conrelid='character_project_states'::regclass "
            "AND conname LIKE 'character_project_states_%_check'"
        )
        constraints = {name: (definition, comment) for name, definition, comment in cur}
        assert len(constraints) == 4
        assert all(
            "pursue_romance" in definition for definition, _ in constraints.values()
        )
        assert all(comment for _, comment in constraints.values())
        cur.execute(
            "INSERT INTO character_project_states "
            "(character_entity_id,project_type,status,stage,"
            "target_character_entity_id) "
            "VALUES (4,'pursue_romance','completed','declaring_intentions',5)"
        )
        for columns, values in (
            ("target_place_id,target_character_entity_id", "7,5"),
            ("target_character_entity_id,target_faction_entity_id", "5,8"),
        ):
            cur.execute("SAVEPOINT invalid_romance")
            with pytest.raises(psycopg2.errors.CheckViolation):
                cur.execute(
                    "INSERT INTO character_project_states "
                    f"(character_entity_id,project_type,status,stage,{columns}) "
                    "VALUES (6,'pursue_romance','active','testing_waters',"
                    f"{values})"
                )
            cur.execute("ROLLBACK TO SAVEPOINT invalid_romance")
        cur.execute(
            "SELECT project_type,target_faction_entity_id "
            "FROM character_project_states "
            "WHERE character_entity_id IN (1,3) ORDER BY character_entity_id"
        )
        assert cur.fetchall() == [("recruit_ally", 9), ("build_venture", None)]
        cur.execute(
            "SELECT type,severity FROM event_types WHERE type LIKE 'pursue_romance_%' "
            "ORDER BY type"
        )
        assert cur.fetchall() == [
            ("pursue_romance_abandoned", "moderate"),
            ("pursue_romance_completed", "moderate"),
            ("pursue_romance_milestone", "moderate"),
            ("pursue_romance_progressed", "minor"),
            ("pursue_romance_stalled", "minor"),
            ("pursue_romance_started", "moderate"),
        ]
