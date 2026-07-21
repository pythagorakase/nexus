"""Live async-writer parity for SEEK_REDEMPTION projects."""

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


async def _create_schema(conn: asyncpg.Connection) -> None:
    schema = f"seek_redemption_async_{uuid4().hex[:12]}"
    await conn.execute(f'CREATE SCHEMA "{schema}"')
    await conn.execute(f'SET LOCAL search_path = "{schema}", public')
    await conn.execute(
        """
        CREATE TABLE event_types (
            type text PRIMARY KEY, category text NOT NULL,
            severity text NOT NULL, description text
        );
        CREATE TABLE orrery_resolutions (
            id bigint PRIMARY KEY, state_delta jsonb NOT NULL
        );
        CREATE TABLE character_project_states (
            id bigserial PRIMARY KEY, character_entity_id bigint NOT NULL,
            project_type text NOT NULL, status text NOT NULL, stage text NOT NULL,
            target_place_id bigint, target_character_entity_id bigint,
            target_faction_entity_id bigint, progress numeric(5,4) NOT NULL DEFAULT 0,
            stall_count integer NOT NULL DEFAULT 0,
            next_eligible_at_world_time timestamptz, source_chunk_id bigint,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT character_project_states_project_type_check CHECK (
                project_type IN (
                    'plan_relocation', 'recruit_ally', 'build_venture',
                    'pursue_romance'
                )),
            CONSTRAINT character_project_states_stage_by_type_check CHECK (
                (project_type='plan_relocation'
                    AND stage IN ('saving','scouting','committing')) OR
                (project_type='recruit_ally'
                    AND stage IN (
                        'sounding_out','earning_trust','sealing_commitment'
                    )) OR
                (project_type='build_venture'
                    AND stage IN (
                        'laying_groundwork','securing_backing','opening_doors'
                    )) OR
                (project_type='pursue_romance'
                    AND stage IN (
                        'testing_waters','growing_closer','declaring_intentions'
                    ))),
            CONSTRAINT character_project_states_target_by_type_check CHECK (
                (project_type='plan_relocation'
                    AND target_character_entity_id IS NULL) OR
                (project_type='recruit_ally'
                    AND target_place_id IS NULL
                    AND target_character_entity_id IS NOT NULL) OR
                (project_type='build_venture'
                    AND target_place_id IS NULL
                    AND target_character_entity_id IS NULL
                    AND target_faction_entity_id IS NULL) OR
                (project_type='pursue_romance'
                    AND target_place_id IS NULL
                    AND target_character_entity_id IS NOT NULL
                    AND target_faction_entity_id IS NULL)),
            CONSTRAINT character_project_states_completed_target_check CHECK (
                status <> 'completed' OR
                (project_type='plan_relocation' AND target_place_id IS NOT NULL) OR
                (project_type='recruit_ally'
                    AND target_character_entity_id IS NOT NULL) OR
                project_type='build_venture' OR
                (project_type='pursue_romance'
                    AND target_character_entity_id IS NOT NULL))
        );
        CREATE UNIQUE INDEX ux_character_project_states_open_budget
            ON character_project_states(character_entity_id)
            WHERE status IN ('active','paused','stalled');
        """
    )
    await conn.execute(
        (
            Path(__file__).parents[2] / "migrations/087_seek_redemption_projects.sql"
        ).read_text()
    )


@pytest.mark.asyncio
async def test_async_seek_redemption_three_write_completion() -> None:
    conn = await asyncpg.connect(get_slot_db_url(slot=2))
    transaction = conn.transaction()
    await transaction.start()
    try:
        await _create_schema(conn)
        entities = await conn.fetch(
            "SELECT entity_id FROM characters WHERE entity_id IS NOT NULL "
            "ORDER BY id LIMIT 2"
        )
        actor, target = (int(row["entity_id"]) for row in entities)
        chunk = int(
            await conn.fetchval(
                "SELECT chunk_id FROM chunk_metadata WHERE world_time IS NOT NULL "
                "ORDER BY chunk_id DESC LIMIT 1"
            )
        )
        await conn.execute(
            "DELETE FROM character_relationships USING characters a,characters t "
            "WHERE character_relationships.character1_id=a.id "
            "AND character_relationships.character2_id=t.id "
            "AND a.entity_id=$1 AND t.entity_id=$2",
            actor,
            target,
        )
        await conn.execute(
            "UPDATE entity_tags et SET cleared_at=now() FROM tags t "
            "WHERE et.tag_id=t.id AND et.entity_id=$1 "
            "AND t.tag='grudge_active' AND et.cleared_at IS NULL",
            target,
        )
        await conn.execute(
            "INSERT INTO entity_tags (entity_id,tag_id,source_kind,template_id) "
            "SELECT $1,id,'template','test_seek_redemption_async' FROM tags "
            "WHERE tag='grudge_active'",
            target,
        )
        start = OrreryResolutionDraft(
            template_id="start_seek_redemption",
            priority=17,
            binding_hash="async-start",
            bindings={"actor": actor, "target": target},
            branch_label="start",
            narrative_stub="start",
            magnitude=0.4,
            state_delta={
                "project.start": {
                    "project_type": "seek_redemption",
                    "stage": "owning_the_wrong",
                    "target_character_entity_id": target,
                    "milestone": True,
                }
            },
        )
        await conn.execute("INSERT INTO orrery_resolutions VALUES (1,'{}'::jsonb)")
        assert (
            await _apply_state_delta_async(
                conn,
                start,
                resolution_id=1,
                actor_entity_id=actor,
                target_entity_id=target,
                source_chunk_id=chunk,
                need_tuning=NeedTuning.default(),
                project_policy=POLICY,
            )
            == 0
        )
        await conn.execute(
            "UPDATE character_project_states "
            "SET stage='earning_forgiveness',progress=1 "
            "WHERE character_entity_id=$1",
            actor,
        )
        complete = OrreryResolutionDraft(
            template_id="advance_seek_redemption",
            priority=47,
            binding_hash="async-complete",
            bindings={"actor": actor, "target": target},
            branch_label="complete",
            narrative_stub="complete",
            magnitude=0.4,
            state_delta={
                "project.complete": {"milestone": True},
                "entity_tags_target.remove": ["grudge_active"],
            },
        )
        await conn.execute("INSERT INTO orrery_resolutions VALUES (2,'{}'::jsonb)")
        assert (
            await _apply_state_delta_async(
                conn,
                complete,
                resolution_id=2,
                actor_entity_id=actor,
                target_entity_id=target,
                source_chunk_id=chunk,
                need_tuning=NeedTuning.default(),
                project_policy=POLICY,
            )
            == 1
        )
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM entity_tags et JOIN tags t ON t.id=et.tag_id "
                "WHERE et.entity_id=$1 AND t.tag='grudge_active' "
                "AND et.cleared_at IS NULL",
                target,
            )
            == 0
        )
        relationship = await conn.fetchrow(
            "SELECT cr.relationship_type,cr.emotional_valence,cr.extra_data "
            "FROM character_relationships cr "
            "JOIN characters a ON a.id=cr.character1_id "
            "JOIN characters t ON t.id=cr.character2_id "
            "WHERE a.entity_id=$1 AND t.entity_id=$2",
            actor,
            target,
        )
        assert relationship is not None
        assert (
            relationship["relationship_type"],
            relationship["emotional_valence"],
        ) == ("complex", "+1|favorable")
        assert (
            json.loads(relationship["extra_data"])["orrery_seek_redemption"][
                "template_id"
            ]
            == "advance_seek_redemption"
        )
    finally:
        await transaction.rollback()
        await conn.close()
