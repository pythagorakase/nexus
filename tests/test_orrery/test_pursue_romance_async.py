"""Live async-writer parity for PURSUE_ROMANCE projects."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import asyncpg
import pytest

from nexus.agents.orrery.events import _apply_state_delta_async
from nexus.agents.orrery.needs import NeedTuning
from nexus.agents.orrery.resolver import OrreryResolutionDraft
from nexus.agents.orrery.substrate import ProjectPolicy
from tests.pg_fixtures import (
    CharacterPairSeed,
    asyncpg_kwargs,
    disposable_slot_database,
    seed_character_pair,
)

pytestmark = pytest.mark.requires_postgres
POLICY = ProjectPolicy(enabled=True, advance_interval_hours=24.0)
WORLD_TIME = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)


async def _create_schema(conn: asyncpg.Connection) -> None:
    schema = f"pursue_romance_async_{uuid4().hex[:12]}"
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
                project_type IN ('plan_relocation','recruit_ally','build_venture')),
            CONSTRAINT character_project_states_stage_by_type_check CHECK (
                (project_type = 'plan_relocation'
                    AND stage IN ('saving', 'scouting', 'committing')) OR
                (project_type = 'recruit_ally'
                    AND stage IN (
                        'sounding_out', 'earning_trust', 'sealing_commitment'
                    )) OR
                (project_type = 'build_venture'
                    AND stage IN (
                        'laying_groundwork', 'securing_backing', 'opening_doors'
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
                (project_type='plan_relocation' AND target_place_id IS NOT NULL) OR
                (project_type = 'recruit_ally'
                    AND target_character_entity_id IS NOT NULL) OR
                project_type='build_venture')
        );
        CREATE UNIQUE INDEX ux_character_project_states_open_budget
            ON character_project_states(character_entity_id)
            WHERE status IN ('active','paused','stalled');
        """
    )
    await conn.execute(
        (
            Path(__file__).parents[2] / "migrations/085_pursue_romance_projects.sql"
        ).read_text()
    )


@pytest.fixture(scope="module")
def romance_async_clone() -> Iterator[tuple[str, CharacterPairSeed]]:
    """Seed a disposable clone with an actor/target pair and a story clock.

    Seeding is synchronous psycopg2, so it runs here, outside the event loop.
    """

    with disposable_slot_database("qa885_pursue_romance_async") as dbname:
        yield dbname, seed_character_pair(
            dbname,
            world_time=WORLD_TIME,
            actor_name="Romance Actor",
            target_name="Romance Target",
        )


@pytest.mark.asyncio
async def test_async_pursue_romance_start_and_completion(
    romance_async_clone: tuple[str, CharacterPairSeed],
) -> None:
    dbname, pair = romance_async_clone
    actor = pair.actor_entity_id
    target = pair.target_entity_id
    chunk_id = pair.chunk_id
    conn = await asyncpg.connect(**asyncpg_kwargs(dbname))
    transaction = conn.transaction()
    await transaction.start()
    await conn.execute("SET LOCAL nexus.write_producer = 'manual'")
    try:
        await _create_schema(conn)
        start = OrreryResolutionDraft(
            template_id="start_pursue_romance",
            priority=17,
            binding_hash="async-romance-start",
            bindings={"actor": actor, "target": target},
            branch_label="start",
            narrative_stub="start",
            state_delta={
                "project.start": {
                    "project_type": "pursue_romance",
                    "stage": "testing_waters",
                    "target_character_entity_id": target,
                    "milestone": True,
                }
            },
            magnitude=0.4,
        )
        await conn.execute("INSERT INTO orrery_resolutions VALUES (1,'{}'::jsonb)")
        assert (
            await _apply_state_delta_async(
                conn,
                start,
                resolution_id=1,
                actor_entity_id=actor,
                target_entity_id=target,
                source_chunk_id=chunk_id,
                need_tuning=NeedTuning.default(),
                project_policy=POLICY,
            )
            == 0
        )
        await conn.execute(
            "UPDATE character_project_states "
            "SET stage='declaring_intentions',progress=1 "
            "WHERE character_entity_id=$1",
            actor,
        )
        complete = OrreryResolutionDraft(
            template_id="advance_pursue_romance",
            priority=47,
            binding_hash="async-romance-complete",
            bindings={"actor": actor, "target": target},
            branch_label="complete",
            narrative_stub="complete",
            state_delta={
                "project.complete": {"milestone": True},
                "entity_pair_tags.add_outbound": ["contact:intimate"],
            },
            magnitude=0.4,
        )
        await conn.execute("INSERT INTO orrery_resolutions VALUES (2,'{}'::jsonb)")
        assert (
            await _apply_state_delta_async(
                conn,
                complete,
                resolution_id=2,
                actor_entity_id=actor,
                target_entity_id=target,
                source_chunk_id=chunk_id,
                need_tuning=NeedTuning.default(),
                project_policy=POLICY,
            )
            == 1
        )
        row = await conn.fetchrow(
            "SELECT cr.relationship_type,cr.emotional_valence,cr.extra_data "
            "FROM character_relationships cr "
            "JOIN characters a ON a.id=cr.character1_id "
            "JOIN characters t ON t.id=cr.character2_id "
            "WHERE a.entity_id=$1 AND t.entity_id=$2",
            actor,
            target,
        )
        assert row is not None
        assert (row["relationship_type"], row["emotional_valence"]) == (
            "romantic",
            "+4|admiring",
        )
        extra_data = json.loads(row["extra_data"])
        assert (
            extra_data["orrery_pursue_romance"]["template_id"]
            == "advance_pursue_romance"
        )
        applied = json.loads(
            await conn.fetchval(
                "SELECT state_delta::text FROM orrery_resolutions WHERE id=2"
            )
        )
        assert (
            applied["project.complete"]["applied"]["relationship_mutation"][
                "relationship_type"
            ]
            == "romantic"
        )
    finally:
        await transaction.rollback()
        await conn.close()
