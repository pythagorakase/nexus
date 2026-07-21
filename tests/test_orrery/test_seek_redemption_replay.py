"""Checkpoint replay coverage for SEEK_REDEMPTION reconciliation."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from nexus.agents.orrery.events import _apply_state_delta_sync, _insert_resolution_sync
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.reconstruction import (
    capture_state_checkpoint_sync,
    set_commit_chunk_attribution_sync,
)
from nexus.agents.orrery.replay import (
    TAG_DELTA_KEYS,
    reconstruct_state_at_sync,
    verify_checkpoints_sync,
)
from nexus.agents.orrery.resolver import OrreryResolutionDraft
from tests.test_orrery.test_seek_redemption_projects import POLICY
from tests.test_orrery.test_pursue_romance_replay import (
    _fabricate_chunk,
    _next_world_time,
)

pytestmark = pytest.mark.requires_postgres
pytest_plugins = ("tests.test_orrery.test_seek_redemption_projects",)


def _apply_transition(
    cur: Any,
    *,
    chunk_id: int,
    actor: int,
    target: int,
    state_delta: dict[str, Any],
) -> None:
    set_commit_chunk_attribution_sync(cur, chunk_id)
    draft = OrreryResolutionDraft(
        template_id="seek_redemption_replay_probe",
        priority=47,
        binding_hash=f"seek-redemption-replay-{chunk_id}",
        bindings={"actor": actor, "target": target},
        branch_label="SEEK_REDEMPTION replay probe",
        narrative_stub="probe",
        state_delta=state_delta,
        magnitude=0.4,
    )
    resolution_id = _insert_resolution_sync(
        cur,
        draft,
        tick_chunk_id=chunk_id,
        actor_entity_id=actor,
        brief="SEEK_REDEMPTION checkpoint replay probe",
    )
    assert resolution_id is not None
    _apply_state_delta_sync(
        cur,
        draft,
        resolution_id=int(resolution_id),
        actor_entity_id=actor,
        target_entity_id=target,
        source_chunk_id=chunk_id,
        need_tuning=load_need_tuning(),
        project_policy=POLICY,
    )


def test_target_remove_is_a_replay_accepted_tag_delta() -> None:
    assert "entity_tags_target.remove" in TAG_DELTA_KEYS


def test_seek_redemption_completion_replays_without_drift(
    live_redemption_db: dict[str, Any],
) -> None:
    db = live_redemption_db
    actor = int(db["actor"])
    target = int(db["target"])
    with db["conn"].cursor() as cur:
        # The shared fixture's minimal writer table is useful for direct-applier
        # tests; replay needs the full public resolution ledger instead.
        cur.execute("DROP TABLE orrery_resolutions")
        base_time = _next_world_time(cur)
        base_chunk = _fabricate_chunk(cur, base_time, created_offset_minutes=-4)
        base_id = capture_state_checkpoint_sync(
            cur, chunk_id=base_chunk, label="manual"
        )
        assert base_id is not None
        transitions = (
            {
                "project.start": {
                    "project_type": "seek_redemption",
                    "stage": "owning_the_wrong",
                    "target_character_entity_id": target,
                    "milestone": True,
                }
            },
            {
                "project.advance": {
                    "stage": "making_amends",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
            {
                "project.advance": {
                    "stage": "earning_forgiveness",
                    "set_progress": 1.0,
                    "milestone": True,
                }
            },
            {
                "project.complete": {"milestone": True},
                "entity_tags_target.remove": ["grudge_active"],
            },
        )
        chunks: list[int] = []
        for step, delta in enumerate(transitions, start=1):
            chunk = _fabricate_chunk(
                cur,
                base_time + timedelta(hours=24 * step),
                created_offset_minutes=step - len(transitions),
            )
            _apply_transition(
                cur,
                chunk_id=chunk,
                actor=actor,
                target=target,
                state_delta=delta,
            )
            chunks.append(chunk)
        target_id = capture_state_checkpoint_sync(
            cur, chunk_id=chunks[-1], label="manual"
        )
        assert target_id is not None
        reconstructed = reconstruct_state_at_sync(
            cur, chunks[-1], base_checkpoint_id=int(base_id)
        )
        project = next(
            row
            for row in reconstructed.state["character_project_states"]
            if row["character_entity_id"] == actor
            and row["project_type"] == "seek_redemption"
        )
        assert project["status"] == "completed"
        assert project["target_character_entity_id"] == target
        pair = next(
            verdict
            for verdict in verify_checkpoints_sync(cur)
            if verdict.base_checkpoint_id == base_id
            and verdict.target_checkpoint_id == target_id
        )
        assert pair.drifts == []
