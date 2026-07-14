"""PLAN_RELOCATION project policy, cadence, and explain parity tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path

import pytest

from nexus.agents.orrery.coverage import analyze_coverage, sample_anchor_ids
from nexus.agents.orrery.events import _insert_resolution_sync
from nexus.agents.orrery.explain import explain_stack
from nexus.agents.orrery.resolver import OrreryResolutionDraft
from nexus.agents.orrery.substrate import (
    BranchSelection,
    EventRecord,
    ProjectPolicy,
    ProjectState,
    RoutineAnchor,
    Slot,
    TravelState,
    WorldState,
    configure_project_magnitudes,
    evaluate,
    evaluate_stack,
)
from nexus.agents.orrery.templates import (
    ADVANCE_RELOCATION_PLAN,
    BUILTIN_TEMPLATES,
    EVADE_PURSUERS,
    START_RELOCATION_PLAN,
)


ACTOR = 10
HUNTER = 20
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
BINDINGS = {Slot.ACTOR: ACTOR}


def _project(
    *,
    due_at: datetime,
    stall_count: int = 0,
    stage: str = "saving",
    progress: float = 0.25,
    target_place_id: int | None = None,
) -> ProjectState:
    return ProjectState(
        id=7,
        project_type="plan_relocation",
        status="active",
        stage=stage,
        target_place_id=target_place_id,
        progress=progress,
        stall_count=stall_count,
        next_eligible_at_world_time=due_at,
        source_chunk_id=100,
    )


def _state(
    *,
    world_time: datetime,
    due_at: datetime,
    hunted: bool = False,
    stall_count: int = 0,
    travel_status: str = "at_place",
    constrained: bool = False,
    stage: str = "saving",
    progress: float = 0.25,
    target_place_id: int | None = None,
    current_tick: int = 101,
) -> WorldState:
    return WorldState(
        tags={
            ACTOR: frozenset(
                {"public_role", "captive"} if constrained else {"public_role"}
            )
        },
        locations={ACTOR: 1},
        location_classes={
            1: frozenset({"meeting", "urban_dense"}),
            2: frozenset({"dwelling"}),
        },
        pair_tags=({(HUNTER, ACTOR): frozenset({"hunting"})} if hunted else {}),
        travel_states={ACTOR: TravelState(status=travel_status)},
        project_states={
            ACTOR: _project(
                due_at=due_at,
                stall_count=stall_count,
                stage=stage,
                progress=progress,
                target_place_id=target_place_id,
            )
        },
        project_policy=POLICY,
        world_time=world_time,
        current_tick=current_tick,
    )


def test_project_cadence_blocks_consecutive_ticks() -> None:
    """A 24-hour cadence cannot fire across adjacent one-hour ticks."""

    first = _state(world_time=NOW, due_at=NOW)
    assert evaluate(ADVANCE_RELOCATION_PLAN, first, BINDINGS).passes is True

    next_eligible = NOW + timedelta(hours=POLICY.advance_interval_hours)
    adjacent = _state(world_time=NOW + timedelta(hours=1), due_at=next_eligible)
    assert evaluate(ADVANCE_RELOCATION_PLAN, adjacent, BINDINGS).passes is False

    next_due = _state(world_time=next_eligible, due_at=next_eligible)
    assert evaluate(ADVANCE_RELOCATION_PLAN, next_due, BINDINGS).passes is True


def test_due_project_waits_for_arrival_and_constraint_release() -> None:
    """A due project cannot overwrite transit and remains due after arrival."""

    in_transit = _state(
        world_time=NOW,
        due_at=NOW,
        travel_status="in_transit",
    )
    assert evaluate(ADVANCE_RELOCATION_PLAN, in_transit, BINDINGS).passes is False

    arrived = _state(
        world_time=NOW + timedelta(hours=1),
        due_at=NOW,
        travel_status="at_place",
        current_tick=102,
    )
    assert evaluate(ADVANCE_RELOCATION_PLAN, arrived, BINDINGS).passes is True

    constrained = _state(world_time=NOW, due_at=NOW, constrained=True)
    assert evaluate(ADVANCE_RELOCATION_PLAN, constrained, BINDINGS).passes is False


def test_relocation_entry_requires_repeated_routine_and_negative_signal() -> None:
    """The pilot starts only from the authored sustained-discontent signal."""

    state = WorldState(
        tags={ACTOR: frozenset({"public_role"})},
        locations={ACTOR: 1},
        location_classes={1: frozenset({"dwelling"})},
        routine_anchors={
            (ACTOR, "home"): RoutineAnchor(anchor_type="home", place_id=1)
        },
        recent_events=(
            EventRecord(
                event_type="upkeep_done",
                tick=100,
                actor_entity_id=ACTOR,
                location_id=1,
            ),
            EventRecord(
                event_type="upkeep_done",
                tick=95,
                actor_entity_id=ACTOR,
                location_id=1,
            ),
            EventRecord(
                event_type="threat_issued",
                tick=99,
                target_entity_id=ACTOR,
                location_id=1,
            ),
        ),
        project_policy=POLICY,
        world_time=NOW,
        current_tick=101,
    )

    resolution = evaluate(START_RELOCATION_PLAN, state, BINDINGS)
    assert resolution.passes is True
    assert "project.start" in resolution.state_delta


def test_crisis_interrupt_survives_resumes_or_ages_deterministically() -> None:
    """Crisis wins leave project state untouched; due policy decides the next beat."""

    hunted = _state(world_time=NOW, due_at=NOW, hunted=True)
    original_project = hunted.project_states[ACTOR]
    crisis = evaluate_stack(
        (EVADE_PURSUERS, ADVANCE_RELOCATION_PLAN),
        hunted,
        BINDINGS,
        BranchSelection(mode="authored_order"),
    )
    assert crisis is not None
    assert crisis.template_id == "evade_pursuers"
    assert hunted.project_states[ACTOR] == original_project

    resumed = _state(world_time=NOW, due_at=NOW)
    resume = evaluate_stack(
        (EVADE_PURSUERS, ADVANCE_RELOCATION_PLAN),
        resumed,
        BINDINGS,
        BranchSelection(mode="authored_order"),
    )
    assert resume is not None
    assert resume.template_id == "advance_relocation_plan"
    assert resume.state_delta.keys() <= {"project.advance", "project.stall"}

    aged = _state(
        world_time=NOW,
        due_at=NOW - timedelta(hours=POLICY.abandon_after_stalled_world_hours + 1),
    )
    outcomes = [
        evaluate(
            ADVANCE_RELOCATION_PLAN,
            aged,
            BINDINGS,
            BranchSelection(mode="stochastic", temperature=0.25),
        )
        for _ in range(2)
    ]
    assert [outcome.branch_label for outcome in outcomes] == [
        "Let the plan go rather than live in limbo",
        "Let the plan go rather than live in limbo",
    ]
    assert all("project.abandon" in outcome.state_delta for outcome in outcomes)


def test_project_due_evidence_is_visible_in_explain_payload() -> None:
    state = _state(world_time=NOW, due_at=NOW - timedelta(hours=2))
    payload = explain_stack(
        (ADVANCE_RELOCATION_PLAN,),
        state,
        BINDINGS,
        BranchSelection(mode="authored_order"),
    ).to_dict()

    template = payload["templates"][0]

    def leaves(node: dict):
        if "children" in node:
            for child in node["children"]:
                yield from leaves(child)
        else:
            yield node

    evidence = next(
        leaf["evidence"]
        for leaf in leaves(template["gate_trace"])
        if leaf["evidence"]["kind"] == "project_due"
    )
    assert evidence["kind"] == "project_due"
    assert evidence["params"]["mode"] == "ready"
    assert evidence["observed"]["overdue_hours"] == 2.0
    assert evidence["observed"]["project"]["stage"] == "saving"
    assert evidence["result"] is True


def test_routine_promotability_is_visible_in_explain_and_coverage_shape() -> None:
    routine = explain_stack(
        (ADVANCE_RELOCATION_PLAN,),
        _state(world_time=NOW, due_at=NOW),
        BINDINGS,
        BranchSelection(mode="authored_order"),
    ).to_dict()["templates"][0]
    assert routine["chosen_branch"] == "Put another share aside"
    assert routine["promotable"] is False
    selected = next(branch for branch in routine["branches"] if branch["selected"])
    assert selected["promotable"] is False

    milestone = explain_stack(
        (ADVANCE_RELOCATION_PLAN,),
        _state(world_time=NOW, due_at=NOW, progress=1.0),
        BINDINGS,
        BranchSelection(mode="authored_order"),
    ).to_dict()["templates"][0]
    assert milestone["chosen_branch"] == "Turn the savings into a search"
    assert milestone["promotable"] is True


def test_seeded_softmax_can_complete_arc_with_bounded_stall_economics() -> None:
    """Some deterministic seeds finish, and no stage's doom counter dominates."""

    selection_temperature = 0.25
    completed_seeds: list[int] = []
    for seed in range(32):
        project = _project(due_at=NOW, progress=0.0)
        for tick in range(1, 61):
            state = _state(
                world_time=NOW + timedelta(hours=24 * tick),
                due_at=NOW + timedelta(hours=24 * tick),
                stall_count=project.stall_count,
                stage=project.stage,
                progress=project.progress,
                target_place_id=project.target_place_id,
                current_tick=tick,
            )
            outcome = evaluate(
                ADVANCE_RELOCATION_PLAN,
                state,
                BINDINGS,
                BranchSelection(
                    mode="stochastic",
                    temperature=selection_temperature,
                    seed_salt=str(seed),
                ),
            )
            if "project.complete" in outcome.state_delta:
                completed_seeds.append(seed)
                break
            if "project.abandon" in outcome.state_delta:
                break
            if "project.stall" in outcome.state_delta:
                project = replace(
                    project,
                    status="stalled",
                    stall_count=project.stall_count + 1,
                )
                continue
            advance = outcome.state_delta["project.advance"]
            next_stage = str(advance.get("stage") or project.stage)
            next_progress = (
                float(advance["set_progress"])
                if "set_progress" in advance
                else min(
                    1.0,
                    project.progress + float(advance.get("progress_delta", 0.25)),
                )
            )
            project = replace(
                project,
                status="active",
                stage=next_stage,
                progress=next_progress,
                target_place_id=(
                    2 if advance.get("select_target") else project.target_place_id
                ),
                stall_count=(
                    0
                    if advance.get("milestone") and next_stage != project.stage
                    else project.stall_count
                ),
            )

    assert completed_seeds

    # The committing stage is the worst routine pair: four 0.25 press-on wins
    # race the threshold of three stalls. Compute the exact expected terminal
    # doom counter for that absorbing race from the authored softmax weights.
    stall_weight = math.exp(0.10 / selection_temperature)
    press_weight = math.exp(0.16 / selection_temperature)
    stall_probability = stall_weight / (stall_weight + press_weight)

    memo: dict[tuple[int, int], float] = {}

    def expected_terminal_stalls(progress_wins: int, stalls: int) -> float:
        if progress_wins == 4 or stalls == POLICY.stall_abandon_threshold:
            return float(stalls)
        key = (progress_wins, stalls)
        if key not in memo:
            memo[key] = stall_probability * expected_terminal_stalls(
                progress_wins, stalls + 1
            ) + (1.0 - stall_probability) * expected_terminal_stalls(
                progress_wins + 1, stalls
            )
        return memo[key]

    assert expected_terminal_stalls(0, 0) < POLICY.stall_abandon_threshold


def test_authored_order_completes_arc_without_setbacks() -> None:
    """Deterministic selection must never stall a promptly-advanced project.

    PR #494 review: the setback arm's old tautological condition made
    authored_order stall every due tick in scouting-with-target and
    committing, so relocation could never complete under a supported
    selection mode. With project_due("neglected") a prompt actor never
    triggers it, and the full arc completes deterministically.
    """

    project = _project(due_at=NOW, progress=0.0)
    stalls = 0
    completed = False
    for tick in range(1, 41):
        state = _state(
            world_time=NOW + timedelta(hours=24 * tick),
            due_at=NOW + timedelta(hours=24 * tick),
            stall_count=project.stall_count,
            stage=project.stage,
            progress=project.progress,
            target_place_id=project.target_place_id,
            current_tick=tick,
        )
        outcome = evaluate(
            ADVANCE_RELOCATION_PLAN,
            state,
            BINDINGS,
            BranchSelection(mode="authored_order"),
        )
        if "project.complete" in outcome.state_delta:
            completed = True
            break
        assert "project.abandon" not in outcome.state_delta
        if "project.stall" in outcome.state_delta:
            stalls += 1
            continue
        advance = outcome.state_delta["project.advance"]
        next_stage = str(advance.get("stage") or project.stage)
        next_progress = (
            float(advance["set_progress"])
            if "set_progress" in advance
            else min(
                1.0,
                project.progress + float(advance.get("progress_delta", 0.25)),
            )
        )
        project = replace(
            project,
            status="active",
            stage=next_stage,
            progress=next_progress,
            target_place_id=(
                2 if advance.get("select_target") else project.target_place_id
            ),
            stall_count=0 if advance.get("milestone") else project.stall_count,
        )

    assert completed, "authored_order must complete the arc"
    assert stalls == 0, "a promptly-advanced project never triggers a setback"


def test_neglected_setback_requires_a_full_missed_interval() -> None:
    """Setbacks are diegetic: due-but-prompt is not neglected; a project
    overdue by a full cadence interval is."""

    from nexus.agents.orrery.substrate import project_due

    prompt = _state(
        world_time=NOW,
        due_at=NOW,
        stall_count=0,
        stage="committing",
        progress=0.5,
        target_place_id=2,
        current_tick=5,
    )
    assert project_due("ready")(prompt, BINDINGS) is True
    assert project_due("neglected")(prompt, BINDINGS) is False

    neglected = _state(
        world_time=NOW + timedelta(hours=POLICY.advance_interval_hours),
        due_at=NOW,
        stall_count=0,
        stage="committing",
        progress=0.5,
        target_place_id=2,
        current_tick=6,
    )
    assert project_due("neglected")(neglected, BINDINGS) is True


def test_completion_preempts_abandon_when_both_are_due() -> None:
    state = _state(
        world_time=NOW,
        due_at=NOW,
        stall_count=POLICY.stall_abandon_threshold,
        stage="committing",
        progress=1.0,
        target_place_id=2,
    )
    outcome = evaluate(
        ADVANCE_RELOCATION_PLAN,
        state,
        BINDINGS,
        BranchSelection(mode="stochastic", temperature=0.25),
    )
    assert outcome.branch_label == "Commit to the road"
    assert "project.complete" in outcome.state_delta


def test_configured_milestones_promote_while_routine_progress_stays_below_floor() -> (
    None
):
    policy = ProjectPolicy(enabled=True, milestone_magnitude=0.55)
    start, advance = configure_project_magnitudes(
        (START_RELOCATION_PLAN, ADVANCE_RELOCATION_PLAN), policy
    )

    assert start.branches[0].magnitude == 0.55
    milestone_branches = [
        branch
        for branch in advance.branches
        if any(
            isinstance(branch.state_delta.get(key), dict)
            and branch.state_delta[key].get("milestone")
            for key in (
                "project.advance",
                "project.abandon",
                "project.complete",
            )
        )
    ]
    assert milestone_branches
    assert all(branch.magnitude == 0.55 for branch in milestone_branches)
    routine = [
        branch
        for branch in advance.branches
        if "project.advance" in branch.state_delta
        and not branch.state_delta["project.advance"].get("milestone")
    ]
    assert routine
    assert all(branch.magnitude < 0.35 for branch in routine)


@pytest.mark.requires_postgres
def test_resolution_insert_skips_routine_promotion_but_queues_milestone() -> None:
    """The branch opt-out reaches the persisted promotion status directly."""

    import psycopg2

    from nexus.api.slot_utils import get_slot_db_url

    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(id) FROM narrative_chunks")
            chunk_id = cur.fetchone()[0]
            cur.execute(
                "SELECT entity_id FROM characters "
                "WHERE entity_id IS NOT NULL ORDER BY id LIMIT 1"
            )
            actor_entity_id = cur.fetchone()[0]
            statuses: dict[str, str] = {}
            for label, promotable in (("routine", False), ("milestone", True)):
                draft = OrreryResolutionDraft(
                    template_id=f"project_promotion_{label}",
                    priority=47,
                    binding_hash=f"project-promotion-{label}-{chunk_id}",
                    bindings={"actor": actor_entity_id},
                    branch_label=label,
                    narrative_stub="probe",
                    promotable=promotable,
                )
                resolution_id = _insert_resolution_sync(
                    cur,
                    draft,
                    tick_chunk_id=chunk_id,
                    actor_entity_id=actor_entity_id,
                    brief="probe",
                )
                assert resolution_id is not None
                cur.execute(
                    "SELECT promotion_status::text FROM orrery_resolutions "
                    "WHERE id = %s",
                    (resolution_id,),
                )
                statuses[label] = cur.fetchone()[0]

            assert statuses == {"routine": "skipped", "milestone": "pending"}
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.requires_postgres
def test_slot2_coverage_distribution_and_project_gate_payload() -> None:
    """One due project displaces surveillance without distorting routine shares."""

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from nexus.api.slot_utils import get_slot_db_url
    from nexus.config import load_settings_as_dict

    orrery = load_settings_as_dict()["orrery"]
    engine = create_engine(get_slot_db_url(slot=2))
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        connection.exec_driver_sql(
            Path("migrations/074_plan_relocation_projects.sql").read_text()
        )
        anchors = sample_anchor_ids(session, count=35, stride=1)
        assert anchors, "save_02 must provide coverage anchors"
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
            "fanout_settings": orrery.get("fanout"),
        }
        baseline = analyze_coverage(session, BUILTIN_TEMPLATES, **kwargs)
        surveil_rows = [
            winner
            for anchor in baseline["anchors"]
            for winner in anchor["resolution_winners"]
            if winner["template_id"] == "surveil"
        ]
        assert surveil_rows, "slot_2 pilot anchors must include surveillance idling"
        actor = surveil_rows[0]["actor_entity_id"]
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
                    progress, stall_count, next_eligible_at_world_time,
                    source_chunk_id
                ) VALUES (
                    :actor, 'plan_relocation', 'active', 'saving',
                    0.25, 0, :due_at, :source_chunk_id
                )
                """
            ),
            {
                "actor": actor,
                "due_at": earliest_world_time - timedelta(hours=1),
                "source_chunk_id": anchors[0],
            },
        )
        active = analyze_coverage(session, BUILTIN_TEMPLATES, **kwargs)

        advance_gates = [
            gate
            for anchor in active["anchors"]
            for gate in anchor["project_gates"]
            if gate["actor_entity_id"] == actor
            and gate["template_id"] == "advance_relocation_plan"
        ]
        assert advance_gates
        assert any(gate["gate_passed"] for gate in advance_gates)

        def leaves(node: dict):
            if "children" in node:
                for child in node["children"]:
                    yield from leaves(child)
            else:
                yield node

        due_evidence = [
            leaf["evidence"]
            for gate in advance_gates
            for leaf in leaves(gate["gate_trace"])
            if leaf["evidence"]["kind"] == "project_due"
        ]
        assert due_evidence
        assert all(evidence["result"] is True for evidence in due_evidence)

        assert active["templates"]["advance_relocation_plan"]["won"] > 0
        promotability = active["templates"]["advance_relocation_plan"][
            "branch_promotable"
        ]
        assert promotability["Put another share aside"] is False
        assert promotability["Turn the savings into a search"] is True
        advance_winners = [
            winner
            for anchor in active["anchors"]
            for winner in anchor["resolution_winners"]
            if winner["template_id"] == "advance_relocation_plan"
        ]
        assert advance_winners
        assert all(winner["promotable"] is False for winner in advance_winners)
        assert (
            active["templates"]["surveil"]["won"]
            < baseline["templates"]["surveil"]["won"]
        )
        for need_template in ("sleep", "drink", "eat"):
            assert (
                active["templates"][need_template]["won"]
                == baseline["templates"][need_template]["won"]
            )

        routine_ids = {
            template.id
            for template in BUILTIN_TEMPLATES
            if template.drive_band.value in {"embodied_maintenance", "anchored_routine"}
        }

        def winner_shares(report: dict) -> dict[str, float]:
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
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
