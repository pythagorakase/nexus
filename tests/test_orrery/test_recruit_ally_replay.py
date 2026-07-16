"""Checkpoint replay coverage for the RECRUIT_ALLY project lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional

import psycopg2
import pytest

from nexus.agents.orrery.events import (
    _apply_state_delta_sync,
    _insert_resolution_sync,
)
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
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
                  AND pt.tag = 'ally'
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
        SELECT max(id) + 1, 'RECRUIT_ALLY replay probe',
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
    draft = OrreryResolutionDraft(
        template_id="recruit_ally_replay_probe",
        priority=47,
        binding_hash=f"recruit-ally-replay-{chunk_id}",
        bindings={"actor": actor_entity_id, "target": target_entity_id},
        branch_label="RECRUIT_ALLY replay probe",
        narrative_stub="probe",
        state_delta=state_delta,
        magnitude=0.4,
    )
    resolution_id = _insert_resolution_sync(
        cur,
        draft,
        tick_chunk_id=chunk_id,
        actor_entity_id=actor_entity_id,
        brief="RECRUIT_ALLY checkpoint replay probe",
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
        and row["project_type"] == "recruit_ally"
    ]
    assert len(matching) == 1
    return matching[0]


def test_recruit_ally_lifecycle_replays_between_checkpoints_without_drift(
    replay_project_db: dict[str, Any],
) -> None:
    db = replay_project_db
    actor = int(db["actor"])
    target = int(db["target"])

    with db["conn"].cursor() as cur:
        base_time = _next_world_time(cur)
        base_chunk = _fabricate_chunk(
            cur,
            base_time,
            created_offset_minutes=1,
        )
        base_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=base_chunk,
            label="manual",
        )
        assert base_id is not None

        transitions = (
            {
                "project.start": {
                    "project_type": "recruit_ally",
                    "stage": "sounding_out",
                    "target_character_entity_id": target,
                    "milestone": True,
                }
            },
            {
                "project.advance": {
                    "stage": "earning_trust",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            {
                "project.advance": {
                    "stage": "sealing_commitment",
                    "set_progress": 1.0,
                    "milestone": True,
                }
            },
            {
                "project.complete": {"milestone": True},
                "entity_pair_tags.add_outbound": ["ally"],
            },
        )
        transition_chunks: list[int] = []
        for offset, state_delta in enumerate(transitions, start=2):
            chunk_id = _fabricate_chunk(
                cur,
                base_time + timedelta(hours=24 * (offset - 1)),
                created_offset_minutes=offset,
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
        assert project["stage"] == "sealing_commitment"
        assert project["target_place_id"] is None
        assert project["target_character_entity_id"] == target
        assert float(project["progress"]) == 1.0
        assert project["source_chunk_id"] == complete_chunk

        cur.execute("SELECT id FROM pair_tags WHERE tag = 'ally'")
        ally_tag_id = int(cur.fetchone()[0])
        assert any(
            row["subject_entity_id"] == actor
            and row["object_entity_id"] == target
            and row["pair_tag_id"] == ally_tag_id
            for row in reconstructed.state["entity_pair_tags"]
        )

        pair = next(
            verdict
            for verdict in verify_checkpoints_sync(cur)
            if verdict.base_checkpoint_id == base_id
            and verdict.target_checkpoint_id == target_id
        )
        assert pair.drifts == []
