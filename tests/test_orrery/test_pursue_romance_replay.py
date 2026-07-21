"""Checkpoint replay coverage for the PURSUE_ROMANCE project lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Optional
from uuid import uuid4

import psycopg2
import pytest

from nexus.agents.orrery.events import (
    _apply_state_delta_sync,
    _insert_resolution_sync,
)
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.reconstruction import (
    capture_state_checkpoint_sync,
    set_commit_chunk_attribution_sync,
)
from nexus.agents.orrery.replay import (
    reconstruct_state_at_sync,
    verify_checkpoints_sync,
)
from nexus.agents.orrery.resolver import OrreryResolutionDraft
from nexus.agents.orrery.substrate import ProjectPolicy
from nexus.api.slot_utils import get_slot_db_url

pytestmark = pytest.mark.requires_postgres

POLICY = ProjectPolicy(
    enabled=True,
    advance_interval_hours=24.0,
    max_active_per_character=1,
    stall_abandon_threshold=3,
    abandon_after_stalled_world_hours=168.0,
    milestone_magnitude=0.40,
    coverage_distribution_tolerance=0.05,
)


@pytest.fixture
def replay_project_db() -> Iterator[dict[str, Any]]:
    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        with conn.cursor() as cur:
            schema = f"pursue_romance_replay_{uuid4().hex[:12]}"
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
                    next_eligible_at_world_time timestamptz,
                    source_chunk_id bigint,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
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
                CREATE UNIQUE INDEX ux_character_project_states_open_budget
                    ON character_project_states(character_entity_id)
                    WHERE status IN ('active','paused','stalled');
                """
            )
            cur.execute(
                (
                    Path(__file__).parents[2]
                    / "migrations/085_pursue_romance_projects.sql"
                ).read_text()
            )
            cur.execute(
                "SELECT entity_id FROM characters "
                "WHERE entity_id IS NOT NULL ORDER BY id LIMIT 2"
            )
            entities = [int(row[0]) for row in cur.fetchall()]
            if len(entities) < 2:
                pytest.skip("save_02 needs two character entities")
            actor, target = entities
            cur.execute(
                "DELETE FROM character_project_states "
                "WHERE character_entity_id = %s",
                (actor,),
            )
            cur.execute(
                """
                UPDATE entity_pair_tags ept
                SET cleared_at = now()
                FROM pair_tags pt
                WHERE ept.pair_tag_id = pt.id
                  AND ept.subject_entity_id = %s
                  AND ept.object_entity_id = %s
                  AND pt.tag = 'contact:intimate'
                  AND ept.cleared_at IS NULL
                """,
                (actor, target),
            )
        yield {"conn": conn, "actor": actor, "target": target}
    finally:
        conn.rollback()
        conn.close()


def _next_world_time(cur: Any) -> datetime:
    cur.execute("SELECT max(world_time) FROM chunk_metadata")
    latest = cur.fetchone()[0]
    base = latest or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(hours=6)


def _fabricate_chunk(
    cur: Any,
    world_time: datetime,
    *,
    created_offset_minutes: int,
) -> int:
    cur.execute(
        """
        INSERT INTO narrative_chunks (id, raw_text, created_at)
        SELECT max(id) + 1, 'PURSUE_ROMANCE replay probe',
               now() + make_interval(mins => %s)
        FROM narrative_chunks
        RETURNING id
        """,
        (created_offset_minutes,),
    )
    chunk_id = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO chunk_metadata (chunk_id, world_time) VALUES (%s, %s)",
        (chunk_id, world_time),
    )
    cur.execute(
        "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
        (world_time, chunk_id),
    )
    return chunk_id


def _apply_transition(
    cur: Any,
    *,
    chunk_id: int,
    actor_entity_id: int,
    target_entity_id: int,
    state_delta: dict[str, Any],
) -> None:
    set_commit_chunk_attribution_sync(cur, chunk_id)
    draft = OrreryResolutionDraft(
        template_id="pursue_romance_replay_probe",
        priority=47,
        binding_hash=f"recruit-ally-replay-{chunk_id}",
        bindings={"actor": actor_entity_id, "target": target_entity_id},
        branch_label="PURSUE_ROMANCE replay probe",
        narrative_stub="probe",
        state_delta=state_delta,
        magnitude=0.4,
    )
    resolution_id = _insert_resolution_sync(
        cur,
        draft,
        tick_chunk_id=chunk_id,
        actor_entity_id=actor_entity_id,
        brief="PURSUE_ROMANCE checkpoint replay probe",
    )
    assert resolution_id is not None
    _apply_state_delta_sync(
        cur,
        draft,
        resolution_id=int(resolution_id),
        actor_entity_id=actor_entity_id,
        target_entity_id=target_entity_id,
        source_chunk_id=chunk_id,
        need_tuning=load_need_tuning(),
        project_policy=POLICY,
    )


def _project_row(
    rows: list[dict[str, Any]], actor_entity_id: int
) -> Optional[dict[str, Any]]:
    matching = [
        row
        for row in rows
        if row["character_entity_id"] == actor_entity_id
        and row["project_type"] == "pursue_romance"
    ]
    assert len(matching) == 1
    return matching[0]


def test_pursue_romance_lifecycle_replays_between_checkpoints_without_drift(
    replay_project_db: dict[str, Any],
) -> None:
    db = replay_project_db
    actor = int(db["actor"])
    target = int(db["target"])

    with db["conn"].cursor() as cur:
        base_time = _next_world_time(cur)
        cur.execute(
            """
            SELECT actor.id, target.id, relationship.relationship_type
            FROM characters actor
            JOIN characters target ON target.entity_id = %s
            LEFT JOIN character_relationships relationship
              ON relationship.character1_id = actor.id
             AND relationship.character2_id = target.id
            WHERE actor.entity_id = %s
            """,
            (target, actor),
        )
        actor_character_id, target_character_id, prior_relationship_type = (
            cur.fetchone()
        )
        base_chunk = _fabricate_chunk(
            cur,
            base_time,
            created_offset_minutes=-4,
        )
        base_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=base_chunk,
            label="manual",
        )
        assert base_id is not None

        transitions: tuple[dict[str, Any], ...] = (
            {
                "project.start": {
                    "project_type": "pursue_romance",
                    "stage": "testing_waters",
                    "target_character_entity_id": target,
                    "milestone": True,
                }
            },
            {
                "project.advance": {
                    "stage": "growing_closer",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            {
                "project.advance": {
                    "stage": "declaring_intentions",
                    "set_progress": 1.0,
                    "milestone": True,
                }
            },
            {
                "project.complete": {"milestone": True},
                "entity_pair_tags.add_outbound": ["contact:intimate"],
            },
        )
        transition_chunks: list[int] = []
        for step, state_delta in enumerate(transitions, start=1):
            chunk_id = _fabricate_chunk(
                cur,
                base_time + timedelta(hours=24 * step),
                created_offset_minutes=step - len(transitions),
            )
            _apply_transition(
                cur,
                chunk_id=chunk_id,
                actor_entity_id=actor,
                target_entity_id=target,
                state_delta=state_delta,
            )
            transition_chunks.append(chunk_id)

        complete_chunk = transition_chunks[-1]
        target_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=complete_chunk,
            label="manual",
        )
        assert target_id is not None

        reconstructed = reconstruct_state_at_sync(
            cur,
            complete_chunk,
            base_checkpoint_id=int(base_id),
        )
        project = _project_row(reconstructed.state["character_project_states"], actor)
        assert project is not None
        assert project["status"] == "completed"
        assert project["stage"] == "declaring_intentions"
        assert project["target_place_id"] is None
        assert project["target_character_entity_id"] == target
        assert float(project["progress"]) == 1.0
        assert project["source_chunk_id"] == complete_chunk

        before_completion = reconstruct_state_at_sync(
            cur,
            transition_chunks[-2],
            base_checkpoint_id=int(base_id),
        )
        prior_rows = [
            row
            for row in before_completion.state["character_relationships"]
            if row["character1_id"] == actor_character_id
            and row["character2_id"] == target_character_id
        ]
        if prior_relationship_type is None:
            assert prior_rows == []
        else:
            assert len(prior_rows) == 1
            assert prior_rows[0]["relationship_type"] == prior_relationship_type

        cur.execute("SELECT id FROM pair_tags WHERE tag = 'contact:intimate'")
        ally_tag_id = int(cur.fetchone()[0])
        assert any(
            row["subject_entity_id"] == actor
            and row["object_entity_id"] == target
            and row["pair_tag_id"] == ally_tag_id
            for row in reconstructed.state["entity_pair_tags"]
        )
        assert any(
            row["character1_id"] == actor_character_id
            and row["character2_id"] == target_character_id
            and row["relationship_type"] == "romantic"
            for row in reconstructed.state["character_relationships"]
        )

        pair = next(
            verdict
            for verdict in verify_checkpoints_sync(cur)
            if verdict.base_checkpoint_id == base_id
            and verdict.target_checkpoint_id == target_id
        )
        assert pair.drifts == []
