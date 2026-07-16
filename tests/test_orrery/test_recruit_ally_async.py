"""Async writer parity for character-targeted RECRUIT_ALLY projects."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from nexus.agents.orrery.events import _apply_state_delta_async
from nexus.agents.orrery.needs import NeedTuning
from nexus.agents.orrery.resolver import OrreryResolutionDraft
from nexus.agents.orrery.substrate import ProjectPolicy


ACTOR = 10
TARGET = 20
SOURCE_CHUNK = 100
WORLD_TIME = datetime(2073, 8, 2, 12, tzinfo=timezone.utc)
POLICY = ProjectPolicy(enabled=True, advance_interval_hours=24.0)


class AsyncProjectConn:
    """Stateful asyncpg stand-in for the project and pair-tag write paths."""

    def __init__(self) -> None:
        self.project: dict[str, Any] | None = None
        self.resolution_ledgers: dict[int, dict[str, Any]] = {}
        self.project_inserts: list[tuple[Any, ...]] = []
        self.pair_tag_inserts: list[tuple[Any, ...]] = []
        self.travel_write_seen = False

    async def fetch(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        normalized = " ".join(sql.split())
        if "FROM character_project_states" in normalized:
            if self.project and self.project["status"] in {
                "active",
                "paused",
                "stalled",
            }:
                return [dict(self.project)]
            return []
        raise AssertionError(f"Unexpected fetch SQL: {normalized}; params={params!r}")

    async def fetchval(self, sql: str, *params: Any) -> Any:
        normalized = " ".join(sql.split())
        if "SELECT world_time FROM chunk_metadata" in normalized:
            assert params == (SOURCE_CHUNK,)
            return WORLD_TIME
        raise AssertionError(
            f"Unexpected fetchval SQL: {normalized}; params={params!r}"
        )

    async def fetchrow(self, sql: str, *params: Any) -> dict[str, Any] | None:
        normalized = " ".join(sql.split())
        if "SELECT id FROM pair_tags" in normalized:
            assert params == ("ally",)
            return {"id": 77}
        if "INSERT INTO entity_pair_tags" in normalized:
            self.pair_tag_inserts.append(params)
            return {"id": 88}
        raise AssertionError(
            f"Unexpected fetchrow SQL: {normalized}; params={params!r}"
        )

    async def execute(self, sql: str, *params: Any) -> str:
        normalized = " ".join(sql.split())
        if "INSERT INTO character_project_states" in normalized:
            self.project_inserts.append(params)
            (
                actor_entity_id,
                project_type,
                stage,
                target_place_id,
                target_character_entity_id,
                progress,
                next_eligible_at_world_time,
                source_chunk_id,
            ) = params
            self.project = {
                "id": 7,
                "character_entity_id": actor_entity_id,
                "project_type": project_type,
                "status": "active",
                "stage": stage,
                "target_place_id": target_place_id,
                "target_character_entity_id": target_character_entity_id,
                "progress": progress,
                "stall_count": 0,
                "next_eligible_at_world_time": next_eligible_at_world_time,
                "source_chunk_id": source_chunk_id,
            }
            return "INSERT 0 1"
        if "UPDATE character_project_states" in normalized:
            assert self.project is not None
            self.project["status"] = "completed"
            self.project["next_eligible_at_world_time"] = None
            self.project["source_chunk_id"] = params[0]
            return "UPDATE 1"
        if "UPDATE orrery_resolutions SET state_delta" in normalized:
            self.resolution_ledgers[int(params[1])] = json.loads(params[0])
            return "UPDATE 1"
        if "character_travel_states" in normalized:
            self.travel_write_seen = True
            return "UPDATE 1"
        raise AssertionError(f"Unexpected execute SQL: {normalized}; params={params!r}")


@pytest.mark.asyncio
async def test_async_recruit_ally_start_and_completion_match_sync_applier() -> None:
    """Persist the recruit, complete it, add ally, and ledger exact writes."""

    conn = AsyncProjectConn()
    start = OrreryResolutionDraft(
        template_id="start_recruit_ally",
        priority=17,
        binding_hash="async-recruit-start",
        bindings={"actor": ACTOR, "target": TARGET},
        branch_label="Sound out the candidate",
        narrative_stub="start",
        state_delta={
            "project.start": {
                "project_type": "recruit_ally",
                "stage": "sounding_out",
                "target_character_entity_id": TARGET,
                "milestone": True,
            }
        },
        magnitude=0.4,
    )

    start_mutations = await _apply_state_delta_async(
        conn,
        start,
        resolution_id=101,
        actor_entity_id=ACTOR,
        target_entity_id=TARGET,
        source_chunk_id=SOURCE_CHUNK,
        need_tuning=NeedTuning.default(),
        project_policy=POLICY,
    )

    assert start_mutations == 0
    assert conn.project_inserts == [
        (
            ACTOR,
            "recruit_ally",
            "sounding_out",
            None,
            TARGET,
            0.0,
            WORLD_TIME.replace(day=3),
            SOURCE_CHUNK,
        )
    ]
    start_applied = conn.resolution_ledgers[101]["project.start"]["applied"]
    assert start_applied["target_place_id"] is None
    assert start_applied["target_character_entity_id"] == TARGET

    assert conn.project is not None
    conn.project.update(stage="sealing_commitment", progress=1.0)
    complete = OrreryResolutionDraft(
        template_id="advance_recruit_ally",
        priority=17,
        binding_hash="async-recruit-complete",
        bindings={"actor": ACTOR, "target": TARGET},
        branch_label="Seal the alliance",
        narrative_stub="complete",
        state_delta={
            "entity_pair_tags.add_outbound": ["ally"],
            "project.complete": {"milestone": True},
        },
        magnitude=0.4,
    )

    completion_mutations = await _apply_state_delta_async(
        conn,
        complete,
        resolution_id=102,
        actor_entity_id=ACTOR,
        target_entity_id=TARGET,
        source_chunk_id=SOURCE_CHUNK,
        need_tuning=NeedTuning.default(),
        project_policy=POLICY,
    )

    assert completion_mutations == 1
    assert conn.project["status"] == "completed"
    assert conn.pair_tag_inserts == [
        (ACTOR, TARGET, 77, WORLD_TIME, "advance_recruit_ally", SOURCE_CHUNK)
    ]
    complete_applied = conn.resolution_ledgers[102]["project.complete"]["applied"]
    assert complete_applied["status"] == "completed"
    assert complete_applied["target_character_entity_id"] == TARGET
    assert complete_applied["pair_tag_mutations"] == [
        {
            "operation": "add_outbound",
            "tag": "ally",
            "subject_entity_id": ACTOR,
            "object_entity_id": TARGET,
            "changed": True,
        }
    ]
    assert conn.travel_write_seen is False
