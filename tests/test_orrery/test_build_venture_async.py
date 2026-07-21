"""Live async-writer parity for actor-only BUILD_VENTURE projects."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from nexus.agents.orrery.events import _apply_state_delta_async
from nexus.agents.orrery.needs import NeedTuning
from nexus.agents.orrery.resolver import OrreryResolutionDraft
from nexus.agents.orrery.substrate import ProjectPolicy
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres

POLICY = ProjectPolicy(enabled=True, advance_interval_hours=24.0)


async def _create_runtime_schema(conn: asyncpg.Connection, schema: str) -> None:
    await conn.execute(f'CREATE SCHEMA "{schema}"')
    await conn.execute(f'SET LOCAL search_path = "{schema}", public')
    await conn.execute(
        """
        CREATE TABLE event_types (
            type text PRIMARY KEY, category text NOT NULL,
            severity text NOT NULL, description text
        );
        CREATE TABLE tag_category_registry (
            category text NOT NULL, entity_kind entity_kind NOT NULL,
            prompt_order integer NOT NULL, description text,
            deprecated boolean NOT NULL DEFAULT false,
            replacement_categories text[], PRIMARY KEY (category, entity_kind)
        );
        CREATE TABLE tags (
            id bigserial PRIMARY KEY, tag text UNIQUE NOT NULL,
            category text NOT NULL, is_ephemeral boolean NOT NULL DEFAULT false,
            clearance_kind entity_tag_clearance_kind,
            reapplication_policy entity_tag_reapplication_policy,
            clear_on jsonb, synonym_for bigint,
            deprecated boolean NOT NULL DEFAULT false, description text,
            CHECK (is_ephemeral = (clearance_kind IS NOT NULL))
        );
        CREATE TABLE entity_tags (
            id bigserial PRIMARY KEY, entity_id bigint NOT NULL,
            tag_id bigint NOT NULL, applied_at timestamptz NOT NULL DEFAULT now(),
            applied_at_world_time timestamptz, clear_on_override jsonb,
            cleared_at timestamptz, template_id text,
            source_kind entity_tag_source_kind NOT NULL, source_chunk_id bigint
        );
        CREATE UNIQUE INDEX ix_entity_tags_current
            ON entity_tags (entity_id, tag_id) WHERE cleared_at IS NULL;
        CREATE TABLE orrery_resolutions (
            id bigint PRIMARY KEY, state_delta jsonb NOT NULL
        );
        CREATE TABLE character_project_states (
            id bigserial PRIMARY KEY, character_entity_id bigint NOT NULL,
            project_type text NOT NULL, status text NOT NULL,
            stage text NOT NULL, target_place_id bigint,
            target_character_entity_id bigint, target_faction_entity_id bigint,
            progress numeric(5,4) NOT NULL DEFAULT 0,
            stall_count integer NOT NULL DEFAULT 0,
            next_eligible_at_world_time timestamptz, source_chunk_id bigint,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT character_project_states_project_type_check
                CHECK (project_type IN ('plan_relocation', 'recruit_ally')),
            CONSTRAINT character_project_states_stage_by_type_check CHECK (
                (project_type = 'plan_relocation'
                    AND stage IN ('saving', 'scouting', 'committing')) OR
                (project_type = 'recruit_ally'
                    AND stage IN (
                        'sounding_out', 'earning_trust', 'sealing_commitment'
                    ))
            ),
            CONSTRAINT character_project_states_target_by_type_check CHECK (
                (project_type = 'plan_relocation'
                    AND target_character_entity_id IS NULL) OR
                (project_type = 'recruit_ally'
                    AND target_place_id IS NULL
                    AND target_character_entity_id IS NOT NULL)
            ),
            CONSTRAINT character_project_states_completed_target_check CHECK (
                status <> 'completed' OR
                (project_type = 'plan_relocation' AND target_place_id IS NOT NULL) OR
                (project_type = 'recruit_ally'
                    AND target_character_entity_id IS NOT NULL)
            )
        );
        CREATE UNIQUE INDEX ux_character_project_states_open_budget
            ON character_project_states (character_entity_id)
            WHERE status IN ('active', 'paused', 'stalled')
        """
    )
    migration_sql = (
        Path(__file__).parents[2] / "migrations" / "084_build_venture_projects.sql"
    ).read_text()
    await conn.execute(migration_sql)


@pytest.mark.asyncio
async def test_async_build_venture_start_and_completion_match_sync() -> None:
    conn = await asyncpg.connect(get_slot_db_url(slot=2))
    transaction = conn.transaction()
    await transaction.start()
    try:
        await _create_runtime_schema(conn, f"build_venture_async_{uuid4().hex[:12]}")
        actor = int(
            await conn.fetchval(
                "SELECT entity_id FROM characters WHERE entity_id IS NOT NULL "
                "ORDER BY id LIMIT 1"
            )
        )
        chunk = await conn.fetchrow(
            "SELECT chunk_id, world_time FROM chunk_metadata "
            "WHERE world_time IS NOT NULL ORDER BY chunk_id DESC LIMIT 1"
        )
        assert chunk is not None
        chunk_id = int(chunk["chunk_id"])

        start = OrreryResolutionDraft(
            template_id="start_build_venture",
            priority=17,
            binding_hash="async-build-start",
            bindings={"actor": actor},
            branch_label="Lay the first groundwork",
            narrative_stub="start",
            state_delta={
                "project.start": {
                    "project_type": "build_venture",
                    "stage": "laying_groundwork",
                    "milestone": True,
                }
            },
            magnitude=0.4,
        )
        await conn.execute(
            "INSERT INTO orrery_resolutions (id, state_delta) VALUES (1, $1::jsonb)",
            "{}",
        )
        assert (
            await _apply_state_delta_async(
                conn,
                start,
                resolution_id=1,
                actor_entity_id=actor,
                target_entity_id=None,
                source_chunk_id=chunk_id,
                need_tuning=NeedTuning.default(),
                project_policy=POLICY,
            )
            == 0
        )
        project = await conn.fetchrow(
            "SELECT * FROM character_project_states WHERE character_entity_id = $1",
            actor,
        )
        assert project is not None
        assert project["project_type"] == "build_venture"
        assert project["stage"] == "laying_groundwork"
        assert project["target_place_id"] is None
        assert project["target_character_entity_id"] is None
        assert project["target_faction_entity_id"] is None

        await conn.execute(
            "UPDATE character_project_states SET stage = 'opening_doors', "
            "progress = 1 WHERE character_entity_id = $1",
            actor,
        )
        complete = OrreryResolutionDraft(
            template_id="advance_build_venture",
            priority=47,
            binding_hash="async-build-complete",
            bindings={"actor": actor},
            branch_label="Open the doors",
            narrative_stub="complete",
            state_delta={
                "project.complete": {"milestone": True},
                "entity_tags.add": ["proprietor"],
            },
            magnitude=0.4,
        )
        await conn.execute(
            "INSERT INTO orrery_resolutions (id, state_delta) VALUES (2, $1::jsonb)",
            "{}",
        )
        assert (
            await _apply_state_delta_async(
                conn,
                complete,
                resolution_id=2,
                actor_entity_id=actor,
                target_entity_id=None,
                source_chunk_id=chunk_id,
                need_tuning=NeedTuning.default(),
                project_policy=POLICY,
            )
            == 1
        )
        completed = await conn.fetchrow(
            "SELECT status, target_place_id, target_character_entity_id, "
            "target_faction_entity_id FROM character_project_states "
            "WHERE character_entity_id = $1",
            actor,
        )
        assert completed is not None
        assert tuple(completed.values()) == ("completed", None, None, None)
        tag = await conn.fetchrow(
            "SELECT t.tag, et.template_id FROM entity_tags et "
            "JOIN tags t ON t.id = et.tag_id WHERE et.entity_id = $1",
            actor,
        )
        assert tag is not None
        assert tuple(tag.values()) == ("proprietor", "advance_build_venture")
        applied = json.loads(
            await conn.fetchval(
                "SELECT state_delta::text FROM orrery_resolutions WHERE id = 2"
            )
        )
        assert applied["project.complete"]["applied"] == {
            "project_type": "build_venture",
            "status": "completed",
            "stage": "opening_doors",
            "target_place_id": None,
            "target_character_entity_id": None,
            "target_faction_entity_id": None,
            "progress": 1.0,
            "stall_count": 0,
            "next_eligible_at_world_time": None,
            "source_chunk_id": chunk_id,
        }
    finally:
        await transaction.rollback()
        await conn.close()
