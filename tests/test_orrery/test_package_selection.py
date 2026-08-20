"""Tests for seeded band-window package selection (issue #474)."""

from __future__ import annotations

from typing import Any

import pytest

import nexus.agents.orrery.substrate as substrate
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    BranchSelection,
    DriveBand,
    HabituationPolicy,
    PackageSelection,
    Slot,
    Template,
    WorldState,
    binding_hash,
    evaluate_stack,
    select_package,
)
from tests.test_orrery.test_resolver import FakeSession

BINDINGS = {Slot.ACTOR: 7}


def _template(template_id: str, priority: int, band: DriveBand) -> Template:
    return Template(
        id=template_id,
        priority=priority,
        drive_band=band,
        blurb="Synthetic package-selection surface.",
        required_slots=(Slot.ACTOR,),
        package_gate=ALWAYS,
        branches=(Branch("act", ALWAYS, "{actor} acts."),),
    )


def _stochastic(**overrides: object) -> PackageSelection:
    settings: dict[str, object] = {
        "mode": "stochastic",
        "window_points": 6.0,
        "temperature": 2.0,
        "exempt_bands": frozenset({DriveBand.CRISIS_CONSTRAINT.value}),
    }
    settings.update(overrides)
    return PackageSelection(**settings)  # type: ignore[arg-type]


def test_window_uses_habituation_adjusted_effective_priorities() -> None:
    high = _template("high", 50, DriveBand.PROJECT_IDENTITY)
    near = _template("near", 40, DriveBand.ANCHORED_ROUTINE)
    outside = _template("outside", 37, DriveBand.AFFILIATION)
    habituation = HabituationPolicy(
        enabled=True,
        penalty_per_win=3.0,
        max_penalty=10.0,
        window_ticks=40,
    )
    state = WorldState(current_tick=100, win_history={(7, "high"): 2})

    outcome = select_package(
        (outside, near, high),
        state,
        BINDINGS,
        habituation=habituation,
        package_selection=_stochastic(),
    )

    # Effective priorities are high=44, near=40, outside=37. Only the first
    # two sit inside the shipped six-point window.
    assert outcome.window_template_ids == ("high", "near")
    assert outcome.chosen_by_softmax is True
    assert outcome.reason == "window_softmax"


def test_crisis_candidate_forces_strict_argmax() -> None:
    crisis = _template("crisis", 60, DriveBand.CRISIS_CONSTRAINT)
    near = _template("near", 58, DriveBand.ANCHORED_ROUTINE)

    for tick in range(100):
        outcome = select_package(
            (near, crisis),
            WorldState(current_tick=tick),
            BINDINGS,
            package_selection=_stochastic(),
        )
        assert outcome.winner is not None
        assert outcome.winner.template_id == "crisis"
        assert outcome.chosen_by_softmax is False
        assert outcome.reason == "exempt_band_argmax"


def test_same_inputs_choose_same_package_across_evaluations() -> None:
    high = _template("high", 50, DriveBand.PROJECT_IDENTITY)
    near = _template("near", 46, DriveBand.ANCHORED_ROUTINE)
    state = WorldState(current_tick=4242)
    policy = _stochastic()

    first = evaluate_stack((near, high), state, BINDINGS, package_selection=policy)
    second = evaluate_stack((near, high), state, BINDINGS, package_selection=policy)

    assert first is not None
    assert second is not None
    assert second.template_id == first.template_id


def test_evaluate_stack_hashes_only_at_operation_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One stack operation hashes at its boundaries, never per template."""

    calls = 0
    original = substrate.binding_hash

    def counted(bindings: dict[Any, Any]) -> str:
        nonlocal calls
        calls += 1
        return original(bindings)

    monkeypatch.setattr(substrate, "binding_hash", counted)
    templates = tuple(
        _template(f"candidate_{index}", 50 - index, DriveBand.PROJECT_IDENTITY)
        for index in range(4)
    )

    winner = evaluate_stack(
        templates,
        WorldState(current_tick=722),
        BINDINGS,
        package_selection=_stochastic(window_points=6.0),
    )

    assert winner is not None
    assert calls == 2


@pytest.mark.parametrize("path", ("production", "explain"))
def test_mutating_package_gate_fails_loudly_at_stack_completion(path: str) -> None:
    """Production and explain reject predicates that mutate stack bindings."""

    from nexus.agents.orrery.explain import explain_stack

    def mutating_gate(state: WorldState, bindings: dict[Any, Any]) -> bool:
        bindings[Slot.TARGET] = 99
        return True

    mutating = Template(
        id="mutating_gate",
        priority=50,
        drive_band=DriveBand.PROJECT_IDENTITY,
        blurb="Deliberately violates the pure-predicate contract.",
        required_slots=(Slot.ACTOR,),
        package_gate=mutating_gate,
        branches=(Branch("mutate", ALWAYS, "{actor} mutates."),),
    )
    stable = _template("stable", 49, DriveBand.ANCHORED_ROUTINE)
    bindings = {Slot.ACTOR: 7}

    with pytest.raises(
        RuntimeError,
        match=(
            r"Bindings were mutated during stack evaluation for Orrery templates "
            r"\[mutating_gate, stable\].*pure-predicate contract"
        ),
    ):
        if path == "production":
            evaluate_stack(
                (stable, mutating),
                WorldState(current_tick=722),
                bindings,
                package_selection=_stochastic(),
            )
        else:
            explain_stack(
                (stable, mutating),
                WorldState(current_tick=722),
                bindings,
                package_selection=_stochastic(),
            )


def test_seeded_hash_reuse_keeps_production_and_explain_lockstep() -> None:
    """Pin the pre-#722 winner, audit reason/window, and production draft."""

    from nexus.agents.orrery.explain import explain_stack
    from nexus.agents.orrery.resolver import resolve_dry_run

    high = _template("high", 50, DriveBand.PROJECT_IDENTITY)
    near = _template("near", 46, DriveBand.ANCHORED_ROUTINE)
    templates = (near, high)
    branch_selection = BranchSelection(
        mode="stochastic",
        temperature=0.25,
        seed_salt="order-722",
    )
    package_selection = _stochastic()
    state = WorldState(
        current_tick=4242,
        win_history={(7, "high"): 1},
    )
    habituation = HabituationPolicy(
        enabled=True,
        penalty_per_win=1.0,
        max_penalty=10.0,
        window_ticks=40,
    )
    expected_digest = "495ac0c75eac17d5b3108287f5c354dda89553f1e667e19a3e3406e1e96393b5"

    direct = select_package(
        templates,
        state,
        BINDINGS,
        branch_selection,
        habituation,
        package_selection,
    )
    production = evaluate_stack(
        templates,
        state,
        BINDINGS,
        branch_selection,
        habituation,
        package_selection,
    )
    explained = explain_stack(
        templates,
        state,
        BINDINGS,
        branch_selection,
        habituation,
        package_selection,
    )
    proposal = resolve_dry_run(
        FakeSession(
            active_entity_rows=[{"id": 7}],
            chunk_ref_actor_rows=[{"entity_id": 7}],
            location_rows=[{"entity_id": 7, "current_location": 10}],
            activity_rows=[{"entity_id": 7, "current_activity": "idle"}],
            entity_name_rows=[{"id": 7, "name": "Seven"}],
            max_chunk_id=4242,
        ),
        templates,
        anchor_chunk_id=4242,
        window_chunks=30,
        selection_settings=branch_selection,
        package_selection_settings=package_selection,
        epistemics_settings={},
    )

    assert binding_hash(BINDINGS) == expected_digest
    assert direct.winner == production
    assert direct.reason == explained.selection_reason == "window_softmax"
    assert (
        direct.window_template_ids
        == explained.selection_window_ids
        == (
            "high",
            "near",
        )
    )
    assert direct.chosen_by_softmax is explained.chosen_by_softmax is True
    assert production is not None
    assert production.template_id == explained.winner_id == "high"
    assert production.binding_hash == expected_digest
    assert [
        (
            draft.template_id,
            draft.branch_label,
            draft.binding_hash,
            draft.bindings,
        )
        for draft in proposal.resolutions
    ] == [("high", "act", expected_digest, {"actor": 7})]


def test_configured_exempt_band_disables_randomization() -> None:
    high = _template("high", 50, DriveBand.PROJECT_IDENTITY)
    near = _template("near", 49, DriveBand.ANCHORED_ROUTINE)
    policy = _stochastic(exempt_bands=frozenset({DriveBand.ANCHORED_ROUTINE.value}))

    for tick in range(100):
        outcome = select_package(
            (near, high),
            WorldState(current_tick=tick),
            BINDINGS,
            package_selection=policy,
        )
        assert outcome.winner is not None
        assert outcome.winner.template_id == "high"
        assert outcome.reason == "exempt_band_argmax"


def test_argmax_mode_reproduces_legacy_stack_winner() -> None:
    high = _template("high", 50, DriveBand.PROJECT_IDENTITY)
    near = _template("near", 49, DriveBand.ANCHORED_ROUTINE)
    policy = PackageSelection(
        mode="argmax",
        window_points=6.0,
        temperature=2.0,
        exempt_bands=frozenset({DriveBand.CRISIS_CONSTRAINT.value}),
    )

    for tick in range(100):
        state = WorldState(current_tick=tick)
        legacy = evaluate_stack((near, high), state, BINDINGS)
        explicit = evaluate_stack(
            (near, high), state, BINDINGS, package_selection=policy
        )
        assert legacy is not None
        assert explicit is not None
        assert explicit.template_id == legacy.template_id == "high"


def test_explain_reports_window_and_softmax_choice() -> None:
    from nexus.agents.orrery.explain import explain_stack

    high = _template("high", 50, DriveBand.PROJECT_IDENTITY)
    near = _template("near", 46, DriveBand.ANCHORED_ROUTINE)
    state = WorldState(current_tick=42)

    explained = explain_stack(
        (near, high),
        state,
        BINDINGS,
        package_selection=_stochastic(),
    )

    assert explained.selection_window_ids == ("high", "near")
    assert explained.chosen_by_softmax is True
    assert explained.selection_reason == "window_softmax"
    assert explained.to_dict()["chosen_by_softmax"] is True


def test_argmax_short_circuits_shadowed_templates() -> None:
    """Legacy laziness is preserved: once a winner fires in argmax mode (or
    with no policy), shadowed templates' gates are never evaluated — and in
    stochastic mode, evaluation stops at the near-tie window's floor."""

    from nexus.agents.orrery.substrate import Condition, select_package

    evaluated: list[str] = []

    def _tracking_gate(name: str) -> Condition:
        def probe(state: WorldState, bindings: dict) -> bool:
            evaluated.append(name)
            return True

        probe.__name__ = f"tracking_{name}"
        return probe

    def _tracked(template_id: str, priority: int) -> Template:
        return Template(
            id=template_id,
            priority=priority,
            drive_band=DriveBand.ANCHORED_ROUTINE,
            blurb="Short-circuit probe.",
            required_slots=(Slot.ACTOR,),
            package_gate=_tracking_gate(template_id),
            branches=(Branch("act", ALWAYS, "{actor} acts."),),
        )

    top = _tracked("top", 50)
    shadowed = _tracked("shadowed", 40)
    state = WorldState(current_tick=7)

    evaluated.clear()
    outcome = select_package((shadowed, top), state, BINDINGS)
    assert outcome.winner is not None and outcome.winner.template_id == "top"
    assert evaluated == ["top"], "no-policy argmax must not evaluate shadowed gates"

    evaluated.clear()
    select_package((shadowed, top), state, BINDINGS, package_selection=_stochastic())
    assert evaluated == [
        "top"
    ], "stochastic evaluation must stop at the window floor (50 - 6 > 40)"

    evaluated.clear()
    near = _tracked("near", 46)
    select_package(
        (shadowed, near, top), state, BINDINGS, package_selection=_stochastic()
    )
    assert evaluated == [
        "top",
        "near",
    ], "in-window gates evaluate; below-floor gates never run"
