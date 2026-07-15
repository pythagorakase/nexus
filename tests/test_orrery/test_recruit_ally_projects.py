"""RECRUIT_ALLY character-targeted project acceptance coverage."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import count
from typing import Any, Iterator

import psycopg2
import pytest

from nexus.agents.orrery.events import (
    _apply_state_delta_sync,
    _insert_resolution_sync,
)
from nexus.agents.orrery.explain import explain_stack
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    _draft_from_resolution,
)
from nexus.agents.orrery.substrate import (
    BranchSelection,
    ProjectPolicy,
    ProjectState,
    RoutineAnchor,
    Slot,
    TravelState,
    WorldState,
    evaluate,
    project_target_is,
)
from nexus.agents.orrery.templates import (
    ADVANCE_RECRUIT_ALLY,
    START_RECRUIT_ALLY,
)
from nexus.api.slot_utils import get_slot_db_url


ACTOR = 10
TARGET = 20
OTHER = 30
NOW = datetime(2073, 8, 2, 12, tzinfo=timezone.utc)
POLICY = ProjectPolicy(
    enabled=True,
    advance_interval_hours=24.0,
    max_active_per_character=1,
    stall_abandon_threshold=3,
    abandon_after_stalled_world_hours=168.0,
    milestone_magnitude=0.40,
    coverage_distribution_tolerance=0.05,
)
BINDINGS = {Slot.ACTOR: ACTOR, Slot.TARGET: TARGET}


def _start_state(
    *, pair_tags: frozenset[str] = frozenset({"contact:social"})
) -> WorldState:
    return WorldState(
        locations={ACTOR: 1},
        relationship_types={(ACTOR, TARGET): frozenset({"friend"})},
        pair_tags={(ACTOR, TARGET): pair_tags} if pair_tags else {},
        travel_states={ACTOR: TravelState(status="at_place")},
        project_policy=POLICY,
        routine_anchors={
            (ACTOR, "home"): RoutineAnchor(
                anchor_type="home",
                place_id=1,
                mobility_policy="fixed_place",
            )
        },
        world_time=NOW,
    )


def _project(
    *,
    target: int = TARGET,
    stage: str = "sounding_out",
    progress: float = 0.0,
    stall_count: int = 0,
    due_at: datetime = NOW,
) -> ProjectState:
    return ProjectState(
        id=7,
        project_type="recruit_ally",
        status="active",
        stage=stage,
        target_character_entity_id=target,
        progress=progress,
        stall_count=stall_count,
        next_eligible_at_world_time=due_at,
        source_chunk_id=100,
    )


def _advance_state(
    project: ProjectState, *, actor: int = ACTOR, world_time: datetime = NOW
) -> WorldState:
    return WorldState(
        project_states={actor: project},
        project_policy=POLICY,
        travel_states={actor: TravelState(status="at_place")},
        world_time=world_time,
    )


def _leaves(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if "children" in node:
        for child in node["children"]:
            yield from _leaves(child)
    else:
        yield node


def test_start_gate_explains_allied_and_hostile_rejections() -> None:
    eligible = evaluate(START_RECRUIT_ALLY, _start_state(), BINDINGS)
    assert eligible.passes is True

    allied = explain_stack(
        (START_RECRUIT_ALLY,),
        _start_state(pair_tags=frozenset({"contact:social", "ally"})),
        BINDINGS,
    ).to_dict()["templates"][0]
    allied_leaf = next(
        leaf
        for leaf in _leaves(allied["gate_trace"])
        if leaf["raw"] == "lacks_pair_tag(ally@actor->target)"
    )
    assert allied["gate_passed"] is False
    assert allied_leaf["result"] is False

    hostile_state = replace(
        _start_state(),
        pair_tags={
            (ACTOR, TARGET): frozenset({"contact:social"}),
            (TARGET, ACTOR): frozenset({"hostile_to"}),
        },
    )
    hostile = explain_stack((START_RECRUIT_ALLY,), hostile_state, BINDINGS).to_dict()[
        "templates"
    ][0]
    hostile_leaf = next(
        leaf
        for leaf in _leaves(hostile["gate_trace"])
        if leaf["raw"] == "has_any_pair_tag(hostile_to,hunting@target->actor)"
    )
    assert hostile["gate_passed"] is False
    assert hostile_leaf["result"] is True


def test_project_target_predicate_and_explain_enforce_continuity() -> None:
    state = _advance_state(_project())
    assert project_target_is(Slot.TARGET)(state, BINDINGS) is True
    assert evaluate(ADVANCE_RECRUIT_ALLY, state, BINDINGS).passes is True

    wrong = {Slot.ACTOR: ACTOR, Slot.TARGET: OTHER}
    assert project_target_is(Slot.TARGET)(state, wrong) is False
    trace = explain_stack((ADVANCE_RECRUIT_ALLY,), state, wrong).to_dict()["templates"][
        0
    ]
    evidence = next(
        leaf["evidence"]
        for leaf in _leaves(trace["gate_trace"])
        if leaf["raw"] == "project_target_is(target)"
    )
    assert trace["gate_passed"] is False
    assert evidence["observed"]["explanation"] == (
        "blocked: bound target is not the project's recruit"
    )


def test_neglect_and_hostile_turn_choose_abandonment_paths() -> None:
    neglected = _advance_state(
        _project(
            stage="sealing_commitment",
            progress=0.5,
            due_at=NOW - timedelta(hours=POLICY.advance_interval_hours),
        )
    )
    setback = evaluate(
        ADVANCE_RECRUIT_ALLY,
        neglected,
        BINDINGS,
        BranchSelection(mode="authored_order"),
    )
    assert setback.branch_label == "Lose ground through neglect"
    assert setback.state_delta == {"project.stall": {"increment": 1}}

    hostile = replace(
        _advance_state(_project(stage="earning_trust", progress=0.5)),
        pair_tags={(TARGET, ACTOR): frozenset({"hostile_to"})},
    )
    abandoned = evaluate(
        ADVANCE_RECRUIT_ALLY,
        hostile,
        BINDINGS,
        BranchSelection(mode="authored_order"),
    )
    assert abandoned.branch_label == "Withdraw after a hostile turn"
    assert "project.abandon" in abandoned.state_delta


@pytest.fixture
def live_project_db() -> Iterator[dict[str, Any]]:
    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(id) FROM narrative_chunks")
            chunk_id = int(cur.fetchone()[0])
            cur.execute(
                "SELECT entity_id FROM characters "
                "WHERE entity_id IS NOT NULL ORDER BY id LIMIT 3"
            )
            entities = [int(row[0]) for row in cur.fetchall()]
            if len(entities) < 3:
                pytest.skip("save_02 needs three character entities")
            actor, target, other = entities
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
            cur.execute("SELECT id FROM places ORDER BY id LIMIT 1")
            place_id = int(cur.fetchone()[0])
        yield {
            "conn": conn,
            "chunk_id": chunk_id,
            "actor": actor,
            "target": target,
            "other": other,
            "place_id": place_id,
            "sequence": count(1),
        }
    finally:
        conn.rollback()
        conn.close()


def _apply_draft(db: dict[str, Any], draft: OrreryResolutionDraft) -> int:
    actor = int(db["actor"])
    target = int(db["target"])
    sequence = next(db["sequence"])
    draft = replace(draft, binding_hash=f"recruit-ally-{sequence}")
    with db["conn"].cursor() as cur:
        resolution_id = _insert_resolution_sync(
            cur,
            draft,
            tick_chunk_id=int(db["chunk_id"]),
            actor_entity_id=actor,
            brief="RECRUIT_ALLY acceptance probe",
        )
        assert resolution_id is not None
        _apply_state_delta_sync(
            cur,
            draft,
            resolution_id=resolution_id,
            actor_entity_id=actor,
            target_entity_id=target,
            source_chunk_id=int(db["chunk_id"]),
            need_tuning=load_need_tuning(),
            project_policy=POLICY,
        )
    return int(resolution_id)


def _live_project_row(db: dict[str, Any]) -> ProjectState:
    with db["conn"].cursor() as cur:
        cur.execute(
            """
            SELECT id, project_type, status, stage, target_place_id,
                   target_character_entity_id, progress, stall_count,
                   next_eligible_at_world_time, source_chunk_id
            FROM character_project_states
            WHERE character_entity_id = %s
            ORDER BY id DESC LIMIT 1
            """,
            (db["actor"],),
        )
        row = cur.fetchone()
    assert row is not None
    return ProjectState(
        id=int(row[0]),
        project_type=str(row[1]),
        status=str(row[2]),
        stage=str(row[3]),
        target_place_id=row[4],
        target_character_entity_id=row[5],
        progress=float(row[6]),
        stall_count=int(row[7]),
        next_eligible_at_world_time=row[8],
        source_chunk_id=row[9],
    )


@pytest.mark.requires_postgres
def test_live_start_persists_bound_character_target(
    live_project_db: dict[str, Any],
) -> None:
    db = live_project_db
    actor = int(db["actor"])
    target = int(db["target"])
    state = replace(
        _start_state(),
        locations={actor: 1},
        relationship_types={(actor, target): frozenset({"friend"})},
        pair_tags={(actor, target): frozenset({"contact:social"})},
        routine_anchors={
            (actor, "home"): RoutineAnchor(
                anchor_type="home", place_id=1, mobility_policy="fixed_place"
            )
        },
    )
    bindings = {Slot.ACTOR: actor, Slot.TARGET: target}
    resolution = evaluate(START_RECRUIT_ALLY, state, bindings)
    assert resolution.passes is True
    draft = _draft_from_resolution(resolution, state=state)
    assert draft.state_delta["project.start"]["target_character_entity_id"] == target
    _apply_draft(db, draft)

    project = _live_project_row(db)
    assert project.project_type == "recruit_ally"
    assert project.stage == "sounding_out"
    assert project.target_place_id is None
    assert project.target_character_entity_id == target


@pytest.mark.requires_postgres
def test_live_stage_ladder_completion_and_applied_ledger(
    live_project_db: dict[str, Any],
) -> None:
    db = live_project_db
    actor = int(db["actor"])
    target = int(db["target"])
    start = OrreryResolutionDraft(
        template_id="start_recruit_ally",
        priority=17,
        binding_hash="start",
        bindings={"actor": actor, "target": target},
        branch_label="start",
        narrative_stub="start",
        state_delta={
            "project.start": {
                "project_type": "recruit_ally",
                "stage": "sounding_out",
                "target_character_entity_id": target,
                "milestone": True,
            }
        },
        magnitude=0.40,
    )
    _apply_draft(db, start)

    project = _live_project_row(db)
    routine_state = _advance_state(
        replace(project, next_eligible_at_world_time=NOW), actor=actor, world_time=NOW
    )
    routine = evaluate(
        ADVANCE_RECRUIT_ALLY,
        routine_state,
        {Slot.ACTOR: actor, Slot.TARGET: target},
        BranchSelection(mode="authored_order"),
    )
    assert routine.branch_label == "Learn what the candidate actually wants"
    assert routine.promotable is False
    routine_id = _apply_draft(db, _draft_from_resolution(routine, state=routine_state))
    with db["conn"].cursor() as cur:
        cur.execute(
            "SELECT promotion_status::text FROM orrery_resolutions WHERE id = %s",
            (routine_id,),
        )
        assert cur.fetchone()[0] == "skipped"

    for current_stage, next_stage in (
        ("sounding_out", "earning_trust"),
        ("earning_trust", "sealing_commitment"),
    ):
        with db["conn"].cursor() as cur:
            cur.execute(
                """
                UPDATE character_project_states
                SET stage = %s, progress = 1, stall_count = 2,
                    next_eligible_at_world_time = %s
                WHERE character_entity_id = %s
                  AND status IN ('active', 'paused', 'stalled')
                """,
                (current_stage, NOW, actor),
            )
        project = _live_project_row(db)
        milestone_state = _advance_state(project, actor=actor, world_time=NOW)
        milestone = evaluate(
            ADVANCE_RECRUIT_ALLY,
            milestone_state,
            {Slot.ACTOR: actor, Slot.TARGET: target},
            BranchSelection(mode="authored_order"),
        )
        assert milestone.promotable is True
        _apply_draft(db, _draft_from_resolution(milestone, state=milestone_state))
        advanced = _live_project_row(db)
        assert advanced.stage == next_stage
        assert advanced.progress == 0.0
        assert advanced.stall_count == 0

    with db["conn"].cursor() as cur:
        cur.execute(
            """
            UPDATE character_project_states
            SET progress = 1, next_eligible_at_world_time = %s
            WHERE character_entity_id = %s AND status = 'active'
            """,
            (NOW, actor),
        )
    project = _live_project_row(db)
    completion_state = _advance_state(project, actor=actor, world_time=NOW)
    completion = evaluate(
        ADVANCE_RECRUIT_ALLY,
        completion_state,
        {Slot.ACTOR: actor, Slot.TARGET: target},
        BranchSelection(mode="authored_order"),
    )
    assert completion.branch_label == "Seal the alliance"
    resolution_id = _apply_draft(
        db, _draft_from_resolution(completion, state=completion_state)
    )

    with db["conn"].cursor() as cur:
        cur.execute(
            "SELECT status FROM character_project_states WHERE id = %s",
            (project.id,),
        )
        assert cur.fetchone()[0] == "completed"
        cur.execute(
            """
            SELECT count(*)
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            WHERE ept.subject_entity_id = %s
              AND ept.object_entity_id = %s
              AND pt.tag = 'ally'
              AND ept.cleared_at IS NULL
            """,
            (actor, target),
        )
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT state_delta FROM orrery_resolutions WHERE id = %s",
            (resolution_id,),
        )
        delta = cur.fetchone()[0]
    applied = delta["project.complete"]["applied"]
    assert applied["status"] == "completed"
    assert applied["target_character_entity_id"] == target
    assert applied["pair_tag_mutations"] == [
        {
            "operation": "add_outbound",
            "tag": "ally",
            "subject_entity_id": actor,
            "object_entity_id": target,
            "changed": True,
        }
    ]


@pytest.mark.requires_postgres
def test_live_schema_target_discipline_and_one_project_budget(
    live_project_db: dict[str, Any],
) -> None:
    db = live_project_db
    actor = int(db["actor"])
    target = int(db["target"])
    place_id = int(db["place_id"])
    with db["conn"].cursor() as cur:
        cur.execute("SAVEPOINT invalid_recruit")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO character_project_states (
                    character_entity_id, project_type, status, stage,
                    target_place_id, target_character_entity_id
                ) VALUES (%s, 'recruit_ally', 'active', 'sounding_out', %s, %s)
                """,
                (actor, place_id, target),
            )
        cur.execute("ROLLBACK TO SAVEPOINT invalid_recruit")

        cur.execute("SAVEPOINT invalid_relocation")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO character_project_states (
                    character_entity_id, project_type, status, stage,
                    target_character_entity_id
                ) VALUES (%s, 'plan_relocation', 'active', 'saving', %s)
                """,
                (actor, target),
            )
        cur.execute("ROLLBACK TO SAVEPOINT invalid_relocation")

        cur.execute(
            """
            INSERT INTO character_project_states (
                character_entity_id, project_type, status, stage
            ) VALUES (%s, 'plan_relocation', 'active', 'saving')
            """,
            (actor,),
        )
        cur.execute("SAVEPOINT project_budget")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                """
                INSERT INTO character_project_states (
                    character_entity_id, project_type, status, stage,
                    target_character_entity_id
                ) VALUES (%s, 'recruit_ally', 'active', 'sounding_out', %s)
                """,
                (actor, target),
            )
        cur.execute("ROLLBACK TO SAVEPOINT project_budget")

    blocked = replace(
        _start_state(),
        project_states={
            ACTOR: ProjectState(
                id=99,
                project_type="plan_relocation",
                status="active",
                stage="saving",
                next_eligible_at_world_time=NOW,
            )
        },
    )
    assert evaluate(START_RECRUIT_ALLY, blocked, BINDINGS).passes is False
