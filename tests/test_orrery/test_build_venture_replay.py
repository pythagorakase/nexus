"""Checkpoint replay coverage for the BUILD_VENTURE lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
import psycopg2.extras
import pytest

from nexus.agents.orrery.events import _apply_state_delta_sync
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.agents.orrery.replay import reconstruct_state_at_sync
from nexus.agents.orrery.resolver import OrreryResolutionDraft
from nexus.agents.orrery.substrate import ProjectPolicy
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres
POLICY = ProjectPolicy(enabled=True, advance_interval_hours=24.0)


def _create_schema(cur: Any, schema: str) -> None:
    cur.execute(f'CREATE SCHEMA "{schema}"')
    cur.execute(f'SET LOCAL search_path = "{schema}", public')
    cur.execute(
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
            id bigserial PRIMARY KEY, tick_chunk_id bigint NOT NULL,
            actor_entity_id bigint, state_delta jsonb NOT NULL
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
    cur.execute(
        (
            Path(__file__).parents[2] / "migrations" / "084_build_venture_projects.sql"
        ).read_text()
    )


@pytest.fixture()
def replay_db() -> Iterator[dict[str, Any]]:
    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        with conn.cursor() as cur:
            _create_schema(cur, f"build_venture_replay_{uuid4().hex[:12]}")
            cur.execute(
                "SELECT entity_id FROM characters WHERE entity_id IS NOT NULL "
                "ORDER BY id LIMIT 1"
            )
            actor = int(cur.fetchone()[0])
            cur.execute("SELECT max(world_time) FROM chunk_metadata")
            base_time = cur.fetchone()[0] or datetime(2026, 1, 1, tzinfo=timezone.utc)
        yield {"conn": conn, "actor": actor, "base_time": base_time}
    finally:
        conn.rollback()
        conn.close()


def _chunk(cur: Any, world_time: datetime, offset: int) -> int:
    cur.execute(
        """
        INSERT INTO narrative_chunks (id, raw_text, created_at)
        SELECT max(id) + 1, 'BUILD_VENTURE replay probe',
               now() + make_interval(mins => %s)
        FROM narrative_chunks RETURNING id
        """,
        (offset,),
    )
    chunk_id = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO chunk_metadata (chunk_id, world_time) VALUES (%s, %s)",
        (chunk_id, world_time),
    )
    return chunk_id


def _apply(cur: Any, actor: int, chunk_id: int, delta: dict[str, Any]) -> None:
    cur.execute(
        "INSERT INTO orrery_resolutions (tick_chunk_id, actor_entity_id, state_delta) "
        "VALUES (%s, %s, %s::jsonb) RETURNING id",
        (chunk_id, actor, psycopg2.extras.Json(delta)),
    )
    resolution_id = int(cur.fetchone()[0])
    draft = OrreryResolutionDraft(
        template_id="build_venture_replay_probe",
        priority=47,
        binding_hash=f"build-replay-{chunk_id}",
        bindings={"actor": actor},
        branch_label="BUILD_VENTURE replay probe",
        narrative_stub="probe",
        state_delta=delta,
        magnitude=0.4,
    )
    _apply_state_delta_sync(
        cur,
        draft,
        resolution_id=resolution_id,
        actor_entity_id=actor,
        target_entity_id=None,
        source_chunk_id=chunk_id,
        need_tuning=load_need_tuning(),
        project_policy=POLICY,
    )


def test_build_venture_replays_applied_snapshots_through_completion(
    replay_db: dict[str, Any],
) -> None:
    conn = replay_db["conn"]
    actor = int(replay_db["actor"])
    base_time = replay_db["base_time"] + timedelta(hours=1)
    with conn.cursor() as cur:
        base_chunk = _chunk(cur, base_time, -4)
        base_id = capture_state_checkpoint_sync(
            cur, chunk_id=base_chunk, label="manual"
        )
        assert base_id is not None
        transitions = (
            {
                "project.start": {
                    "project_type": "build_venture",
                    "stage": "laying_groundwork",
                    "milestone": True,
                }
            },
            {
                "project.advance": {
                    "stage": "securing_backing",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            {
                "project.advance": {
                    "stage": "opening_doors",
                    "set_progress": 1.0,
                    "milestone": True,
                }
            },
            {
                "project.complete": {"milestone": True},
                "entity_tags.add": ["proprietor"],
            },
        )
        chunks = []
        for step, delta in enumerate(transitions, start=1):
            chunk_id = _chunk(cur, base_time + timedelta(hours=24 * step), step)
            _apply(cur, actor, chunk_id, delta)
            chunks.append(chunk_id)

        reconstructed = reconstruct_state_at_sync(
            cur, chunks[-1], base_checkpoint_id=int(base_id)
        )
        projects = [
            row
            for row in reconstructed.state["character_project_states"]
            if row["character_entity_id"] == actor
            and row["project_type"] == "build_venture"
        ]
        assert len(projects) == 1
        assert projects[0]["status"] == "completed"
        assert projects[0]["stage"] == "opening_doors"
        assert float(projects[0]["progress"]) == 1.0
        assert projects[0]["target_place_id"] is None
        assert projects[0]["target_character_entity_id"] is None
        assert projects[0]["target_faction_entity_id"] is None

        cur.execute("SELECT id FROM tags WHERE tag = 'proprietor'")
        proprietor_id = int(cur.fetchone()[0])
        assert any(
            row["entity_id"] == actor and row["tag_id"] == proprietor_id
            for row in reconstructed.state["entity_tags"]
        )
