"""Tests for seeded band-window package selection (issue #474)."""

from __future__ import annotations

from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    DriveBand,
    HabituationPolicy,
    PackageSelection,
    Slot,
    Template,
    WorldState,
    evaluate_stack,
    select_package,
)

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
