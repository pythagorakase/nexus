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
    has_symmetric_relationship_of_type,
    project_due,
    project_target_is,
    project_target_is_active,
)
from nexus.agents.orrery.templates import (
    ADVANCE_RECRUIT_ALLY,
    START_RECRUIT_ALLY,
)
from nexus.api.trait_compiler import reconcile_trait_relationship_pair_tags
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
        target_character_is_active=True,
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


def test_inactive_project_target_preemptively_abandons_without_mutation() -> None:
    """A dead or retired recruit releases the budget without other writes."""

    project = replace(_project(), target_character_is_active=False)
    state = _advance_state(project)

    resolution = evaluate(ADVANCE_RECRUIT_ALLY, state, BINDINGS)
    trace = explain_stack((ADVANCE_RECRUIT_ALLY,), state, BINDINGS).to_dict()[
        "templates"
    ][0]
    evidence = next(
        leaf["evidence"]
        for leaf in _leaves(trace["gate_trace"])
        if leaf["raw"] == "project_target_is(target)"
    )

    active_evidence = next(
        leaf["evidence"]
        for leaf in _leaves(trace["branches"][0]["trace"])
        if leaf["raw"] == "project_target_is_active(target)"
    )

    assert project_target_is(Slot.TARGET)(state, BINDINGS) is True
    assert project_target_is_active(Slot.TARGET)(state, BINDINGS) is False
    assert resolution.passes is True
    assert resolution.branch_label == (
        "End a recruitment whose candidate is no longer available"
    )
    assert resolution.state_delta == {
        "project.abandon": {
            "reason": "target_inactive_or_non_character",
            "milestone": True,
        }
    }
    assert "entity_pair_tags.add_outbound" not in resolution.state_delta
    assert "project.advance" not in resolution.state_delta
    assert state.project_states[ACTOR] is project
    assert project.status == "active"
    assert evidence["result"] is True
    assert active_evidence["observed"]["project_target_is_active"] is False
    assert active_evidence["observed"]["explanation"] == (
        "project's recruit is inactive or not a character"
    )


@pytest.mark.parametrize(
    ("mode", "project_type"),
    [
        ("saving", "recruit_ally"),
        ("sounding_out", "plan_relocation"),
    ],
)
def test_project_due_rejects_modes_from_another_project_ladder(
    mode: str, project_type: str
) -> None:
    with pytest.raises(ValueError, match="is not valid for project type"):
        project_due(mode, project_type=project_type)


@pytest.mark.parametrize(
    "stage", ("sounding_out", "earning_trust", "sealing_commitment")
)
@pytest.mark.parametrize(
    "selection",
    (
        BranchSelection(mode="authored_order"),
        BranchSelection(mode="stochastic", temperature=0.25, seed_salt=""),
        BranchSelection(mode="stochastic", temperature=0.25, seed_salt="alpha"),
        BranchSelection(mode="stochastic", temperature=0.25, seed_salt="omega"),
    ),
    ids=(
        "authored-order",
        "configured-stochastic",
        "stochastic-alpha",
        "stochastic-omega",
    ),
)
def test_neglect_preempts_routine_progress_at_every_stage(
    stage: str, selection: BranchSelection
) -> None:
    neglected = _advance_state(
        _project(
            stage=stage,
            progress=0.5,
            due_at=NOW - timedelta(hours=POLICY.advance_interval_hours),
        )
    )
    setback = evaluate(
        ADVANCE_RECRUIT_ALLY,
        neglected,
        BINDINGS,
        selection,
    )
    assert setback.branch_label == "Lose ground through neglect"
    assert setback.state_delta == {"project.stall": {"increment": 1}}


def test_hostile_turn_chooses_abandonment_path() -> None:
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


def test_canonical_ally_relationship_satisfies_existing_ally_gate() -> None:
    """Recruitment's durable relationship unlocks ally-typed packages."""

    state = WorldState(relationship_types={(ACTOR, TARGET): frozenset({"ally"})})
    predicate = has_symmetric_relationship_of_type("ally")

    assert predicate(state, BINDINGS) is True


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
            SELECT cps.id, cps.project_type, cps.status, cps.stage,
                   cps.target_place_id, cps.target_character_entity_id,
                   COALESCE(target_entity.is_active, false), cps.progress,
                   cps.stall_count, cps.next_eligible_at_world_time,
                   cps.source_chunk_id
            FROM character_project_states cps
            LEFT JOIN entities target_entity
              ON target_entity.id = cps.target_character_entity_id
             AND target_entity.kind = 'character'
            WHERE cps.character_entity_id = %s
            ORDER BY cps.id DESC LIMIT 1
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
        target_character_is_active=bool(row[6]),
        progress=float(row[7]),
        stall_count=int(row[8]),
        next_eligible_at_world_time=row[9],
        source_chunk_id=row[10],
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
    with db["conn"].cursor() as cur:
        cur.execute(
            """
            INSERT INTO character_relationships (
                character1_id, character2_id, relationship_type,
                emotional_valence, dynamic, recent_events, history, extra_data
            )
            SELECT actor.id, target.id, 'friend', '+2|friendly',
                   'Preserved recruitment-test dynamic.',
                   'Preserved recruitment-test recent events.',
                   'Preserved recruitment-test history.',
                   '{"test_fixture": true}'::jsonb
            FROM characters actor
            JOIN characters target ON target.entity_id = %s
            WHERE actor.entity_id = %s
            ON CONFLICT (character1_id, character2_id) DO UPDATE SET
                relationship_type = 'friend'
            RETURNING emotional_valence, dynamic, recent_events, history
            """,
            (target, actor),
        )
        preserved_relationship_fields = cur.fetchone()
    assert preserved_relationship_fields is not None
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
            """
            SELECT cr.relationship_type, cr.extra_data
            FROM character_relationships cr
            JOIN characters actor ON actor.id = cr.character1_id
            JOIN characters target ON target.id = cr.character2_id
            WHERE actor.entity_id = %s
              AND target.entity_id = %s
            """,
            (actor, target),
        )
        relationship_type, extra_data = cur.fetchone()
        assert relationship_type == "ally"
        assert extra_data["orrery_recruit_ally"]["template_id"] == (
            "advance_recruit_ally"
        )
        assert extra_data["orrery_recruit_ally"]["source_chunk_id"] == db["chunk_id"]
        cur.execute(
            """
            SELECT cr.emotional_valence, cr.dynamic, cr.recent_events, cr.history
            FROM character_relationships cr
            JOIN characters actor ON actor.id = cr.character1_id
            JOIN characters target ON target.id = cr.character2_id
            WHERE actor.entity_id = %s
              AND target.entity_id = %s
            """,
            (actor, target),
        )
        assert cur.fetchone() == preserved_relationship_fields
        relevant_drift = [
            item
            for item in reconcile_trait_relationship_pair_tags(cur)
            if item.subject_entity_id == actor
            and item.object_entity_id == target
            and item.pair_tag == "ally"
        ]
        assert relevant_drift == []
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
    assert applied["relationship_mutation"]["subject_entity_id"] == actor
    assert applied["relationship_mutation"]["object_entity_id"] == target
    assert applied["relationship_mutation"]["previous_relationship_type"] == "friend"
    assert applied["relationship_mutation"]["relationship_type"] == "ally"
    assert applied["relationship_mutation"]["relationship_type_changed"] is True


@pytest.mark.requires_postgres
def test_live_neglect_applies_recruitment_setback(
    live_project_db: dict[str, Any],
) -> None:
    """A neglected recruitment persists its stalled projection and ledger."""

    db = live_project_db
    actor = int(db["actor"])
    target = int(db["target"])
    with db["conn"].cursor() as cur:
        cur.execute(
            """
            INSERT INTO character_project_states (
                character_entity_id, project_type, status, stage,
                target_character_entity_id, progress, stall_count,
                next_eligible_at_world_time, source_chunk_id
            ) VALUES (
                %s, 'recruit_ally', 'active', 'sealing_commitment',
                %s, 0.5, 0, %s, %s
            )
            """,
            (
                actor,
                target,
                NOW - timedelta(hours=POLICY.advance_interval_hours),
                int(db["chunk_id"]),
            ),
        )
    project = _live_project_row(db)
    state = _advance_state(project, actor=actor, world_time=NOW)
    setback = evaluate(
        ADVANCE_RECRUIT_ALLY,
        state,
        {Slot.ACTOR: actor, Slot.TARGET: target},
        BranchSelection(mode="authored_order"),
    )
    assert setback.branch_label == "Lose ground through neglect"
    resolution_id = _apply_draft(db, _draft_from_resolution(setback, state=state))

    stalled = _live_project_row(db)
    assert stalled.status == "stalled"
    assert stalled.stall_count == 1
    with db["conn"].cursor() as cur:
        cur.execute(
            "SELECT state_delta FROM orrery_resolutions WHERE id = %s",
            (resolution_id,),
        )
        applied = cur.fetchone()[0]["project.stall"]["applied"]
    assert applied["status"] == "stalled"
    assert applied["stall_count"] == 1
    assert applied["target_character_entity_id"] == target


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


@pytest.mark.requires_postgres
def test_slot2_recruitment_routes_persisted_target_without_routine_drift() -> None:
    """A 35-anchor run keeps recruitment routable after its contact clears."""

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from nexus.agents.orrery.coverage import analyze_coverage, sample_anchor_ids
    from nexus.agents.orrery.resolver import resolve_dry_run
    from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
    from nexus.config import load_settings_as_dict

    orrery = load_settings_as_dict()["orrery"]
    engine = create_engine(get_slot_db_url(slot=2))
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        anchors = sample_anchor_ids(session, count=35, stride=1)
        assert len(anchors) == 35, "save_02 must provide 35 coverage anchors"
        kwargs = {
            "anchor_chunk_ids": anchors,
            "window_chunks": int(orrery["binding"]["window_chunks"]),
            "sunhelm_settings": orrery.get("sunhelm"),
            "epoch_min_world_times": int(
                orrery["dashboard"]["coverage_epoch_min_world_times"]
            ),
            "selection_settings": orrery.get("selection"),
            "habituation_settings": orrery.get("habituation"),
            "package_selection_settings": orrery.get("package_selection"),
            "project_settings": orrery.get("projects"),
            "epistemics_settings": orrery.get("epistemics"),
            "fanout_settings": orrery.get("fanout"),
        }
        baseline = analyze_coverage(session, BUILTIN_TEMPLATES, **kwargs)
        surveil_rows = [
            winner
            for anchor in baseline["anchors"]
            for winner in anchor["resolution_winners"]
            if winner["template_id"] == "surveil"
            and winner["target_entity_id"] is not None
        ]
        open_project_actor_ids = set(
            session.execute(
                text(
                    """
                    SELECT character_entity_id
                    FROM character_project_states
                    WHERE status IN ('active', 'paused', 'stalled')
                    """
                )
            ).scalars()
        )
        surveil_rows = [
            winner
            for winner in surveil_rows
            if int(winner["actor_entity_id"]) not in open_project_actor_ids
        ]
        assert surveil_rows, (
            "slot 2 anchors must include a surveillance actor without an "
            "open project"
        )
        actor = int(surveil_rows[0]["actor_entity_id"])
        assert actor not in open_project_actor_ids
        target = session.execute(
            text(
                """
                SELECT e.id
                FROM entities e
                WHERE e.kind = 'character'
                  AND e.is_active = true
                  AND e.id <> :actor
                  AND NOT EXISTS (
                      SELECT 1
                      FROM entity_relationships_v er
                      WHERE er.relationship_scope = 'character'
                        AND (
                            (er.source_entity_id = :actor
                             AND er.target_entity_id = e.id)
                            OR
                            (er.source_entity_id = e.id
                             AND er.target_entity_id = :actor)
                        )
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM chunk_character_references ccr
                      JOIN characters c ON c.id = ccr.character_id
                      WHERE c.entity_id = e.id
                        AND ccr.chunk_id = :anchor
                        AND ccr.reference = 'present'
                  )
                ORDER BY e.id
                LIMIT 1
                """
            ),
            {"actor": actor, "anchor": anchors[0]},
        ).scalar_one_or_none()
        if target is None:
            pytest.skip("slot 2 needs an unrelated off-screen recruit target")
        target = int(target)
        earliest_world_time = session.execute(
            text(
                """
                SELECT min(cm.world_time)
                FROM chunk_metadata cm
                WHERE cm.chunk_id = ANY(:anchors)
                """
            ),
            {"anchors": anchors},
        ).scalar_one()
        assert earliest_world_time is not None
        session.execute(
            text(
                """
                INSERT INTO character_project_states (
                    character_entity_id, project_type, status, stage,
                    target_character_entity_id, progress, stall_count,
                    next_eligible_at_world_time, source_chunk_id
                ) VALUES (
                    :actor, 'recruit_ally', 'active', 'sounding_out',
                    :target, 0.25, 0, :due_at, :source_chunk_id
                )
                """
            ),
            {
                "actor": actor,
                "target": target,
                "due_at": earliest_world_time - timedelta(hours=1),
                "source_chunk_id": anchors[0],
            },
        )
        session.execute(
            text(
                """
                UPDATE entity_pair_tags ept
                SET cleared_at = now()
                FROM pair_tags pt
                WHERE ept.pair_tag_id = pt.id
                  AND ept.subject_entity_id = :actor
                  AND ept.object_entity_id = :target
                  AND pt.tag = 'contact:social'
                  AND ept.cleared_at IS NULL
                """
            ),
            {"actor": actor, "target": target},
        )
        active = analyze_coverage(session, BUILTIN_TEMPLATES, **kwargs)

        advance_gates = [
            gate
            for anchor in active["anchors"]
            for gate in anchor["project_gates"]
            if gate["actor_entity_id"] == actor
            and gate["target_entity_id"] == target
            and gate["template_id"] == "advance_recruit_ally"
        ]
        assert advance_gates
        assert any(gate["gate_passed"] for gate in advance_gates)
        assert active["templates"]["advance_recruit_ally"]["won"] > 0

        proposal = resolve_dry_run(
            session,
            BUILTIN_TEMPLATES,
            anchor_chunk_id=anchors[0],
            window_chunks=kwargs["window_chunks"],
            sunhelm_settings=kwargs["sunhelm_settings"],
            selection_settings=kwargs["selection_settings"],
            habituation_settings=kwargs["habituation_settings"],
            package_selection_settings=kwargs["package_selection_settings"],
            project_settings=kwargs["project_settings"],
            epistemics_settings=kwargs["epistemics_settings"],
            fanout_settings=kwargs["fanout_settings"],
        )
        assert any(
            resolution.template_id == "advance_recruit_ally"
            and resolution.bindings.get("actor") == actor
            and resolution.bindings.get("target") == target
            for resolution in proposal.resolutions
        )

        routine_ids = {
            template.id
            for template in BUILTIN_TEMPLATES
            if template.drive_band.value in {"embodied_maintenance", "anchored_routine"}
        }

        def winner_shares(report: dict[str, Any]) -> dict[str, float]:
            total = sum(payload["won"] for payload in report["templates"].values())
            assert total > 0
            return {
                template_id: report["templates"][template_id]["won"] / total
                for template_id in routine_ids
            }

        baseline_shares = winner_shares(baseline)
        active_shares = winner_shares(active)
        max_shift = max(
            abs(active_shares[key] - baseline_shares[key]) for key in routine_ids
        )
        tolerance = float(orrery["projects"]["coverage_distribution_tolerance"])
        assert max_shift < tolerance, (max_shift, tolerance)

        session.execute(
            text("UPDATE entities SET is_active = false WHERE id = :target"),
            {"target": target},
        )
        inactive_target = resolve_dry_run(
            session,
            BUILTIN_TEMPLATES,
            anchor_chunk_id=anchors[0],
            window_chunks=kwargs["window_chunks"],
            sunhelm_settings=kwargs["sunhelm_settings"],
            selection_settings=kwargs["selection_settings"],
            habituation_settings=kwargs["habituation_settings"],
            package_selection_settings=kwargs["package_selection_settings"],
            project_settings=kwargs["project_settings"],
            epistemics_settings=kwargs["epistemics_settings"],
            fanout_settings=kwargs["fanout_settings"],
        )
        abandonment = next(
            resolution
            for resolution in inactive_target.resolutions
            if resolution.template_id == "advance_recruit_ally"
            and resolution.bindings.get("actor") == actor
            and resolution.bindings.get("target") == target
        )
        assert abandonment.branch_label == (
            "End a recruitment whose candidate is no longer available"
        )
        assert abandonment.state_delta == {
            "project.abandon": {
                "reason": "target_inactive_or_non_character",
                "milestone": True,
            }
        }
        assert "entity_pair_tags.add_outbound" not in abandonment.state_delta
        assert "project.advance" not in abandonment.state_delta
        project_status = session.execute(
            text(
                """
                SELECT status
                FROM character_project_states
                WHERE character_entity_id = :actor
                  AND project_type = 'recruit_ally'
                  AND status IN ('active', 'paused', 'stalled')
                """
            ),
            {"actor": actor},
        ).scalar_one()
        assert project_status == "active"
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
