"""Tests for seeded stochastic branch selection (BranchSelection).

Real engine, no mocks: synthetic templates with always-passing branches give
a controlled multi-branch surface, and the demo presets pin legacy parity.
The properties that matter:

1. Legacy default (no policy / authored_order) is byte-identical to the old
   first-passing rule, short-circuit and all.
2. Stochastic selection is deterministic per (bindings, tick, template,
   salt) — reproducible dynamism, never a dice roll at replay time.
3. Across ticks the same state genuinely varies (the whole point), with
   frequencies ordered by magnitude.
4. explain_template stays in lockstep with evaluate under the same policy —
   the cross-check they share runs the same seeded selection.
"""

from __future__ import annotations

from collections import Counter

import pytest

from nexus.agents.orrery.demo import _all_preset_names, _resolve_preset
from nexus.agents.orrery.explain import explain_stack, explain_template
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    BranchSelection,
    DriveBand,
    Slot,
    Template,
    WorldState,
    coerce_branch_selection,
    evaluate,
    evaluate_stack,
    select_branch,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES

BINDINGS = {Slot.ACTOR: 1}

VARIED = Template(
    id="tend_craft",  # real id so catalog/prose lookups stay valid
    priority=10,
    drive_band=DriveBand.PROJECT_IDENTITY,
    blurb="Synthetic multi-branch surface for selection tests.",
    required_slots=(Slot.ACTOR,),
    package_gate=ALWAYS,
    branches=(
        Branch(
            label="deep work",
            conditions=ALWAYS,
            narrative_stub="{actor} loses hours to the bench.",
            magnitude=0.6,
        ),
        Branch(
            label="light touch",
            conditions=ALWAYS,
            narrative_stub="{actor} tidies the workspace.",
            magnitude=0.3,
        ),
        Branch(
            label="idle glance",
            conditions=ALWAYS,
            narrative_stub="{actor} glances at the unfinished work.",
            magnitude=0.1,
        ),
    ),
)

STOCHASTIC = BranchSelection(mode="stochastic", temperature=0.25)


def _state(tick: int) -> WorldState:
    return WorldState(current_tick=tick)


def test_default_selection_matches_legacy_first_passing() -> None:
    """No policy (and authored_order) keeps the old rule and short-circuit."""

    for preset_name in _all_preset_names():
        state, bindings = _resolve_preset(preset_name)
        legacy = evaluate_stack(BUILTIN_TEMPLATES, state, bindings)
        explicit = evaluate_stack(
            BUILTIN_TEMPLATES,
            state,
            bindings,
            BranchSelection(mode="authored_order"),
        )
        if legacy is None:
            assert explicit is None
            continue
        assert explicit is not None
        assert explicit.template_id == legacy.template_id
        assert explicit.branch_label == legacy.branch_label

    # Authored order picks the FIRST passing branch even when a later branch
    # has higher magnitude — the convention stochastic mode exists to relax.
    resolution = evaluate(VARIED, _state(100), BINDINGS)
    assert resolution.branch_label == "deep work"


def test_stochastic_selection_is_deterministic_per_seed() -> None:
    state = _state(4242)
    first = evaluate(VARIED, state, BINDINGS, STOCHASTIC)
    for _ in range(5):
        again = evaluate(VARIED, state, BINDINGS, STOCHASTIC)
        assert again.branch_label == first.branch_label


def test_stochastic_selection_varies_across_ticks_by_magnitude() -> None:
    """The same state at different ticks picks different branches, with
    frequency ordered by magnitude — variety without noise dominance."""

    counts: Counter[str] = Counter()
    for tick in range(400):
        resolution = evaluate(VARIED, _state(tick), BINDINGS, STOCHASTIC)
        assert resolution.passes
        assert resolution.branch_label is not None
        counts[resolution.branch_label] += 1

    assert len(counts) >= 2, "stochastic selection never varied"
    assert counts["deep work"] > counts["light touch"] > counts["idle glance"]


def test_temperature_zero_is_argmax_by_magnitude() -> None:
    argmax = BranchSelection(mode="stochastic", temperature=0.0)
    for tick in range(20):
        resolution = evaluate(VARIED, _state(tick), BINDINGS, argmax)
        assert resolution.branch_label == "deep work"


def test_seed_salt_rerolls_choices() -> None:
    salted = BranchSelection(mode="stochastic", temperature=0.25, seed_salt="alt")
    differing = sum(
        1
        for tick in range(200)
        if evaluate(VARIED, _state(tick), BINDINGS, STOCHASTIC).branch_label
        != evaluate(VARIED, _state(tick), BINDINGS, salted).branch_label
    )
    assert differing > 0, "seed_salt must be able to reroll selections"


def test_explain_matches_evaluate_under_stochastic_policy() -> None:
    """The shared select_branch authority keeps the cross-check green."""

    for tick in range(50):
        state = _state(tick)
        explanation = explain_template(VARIED, state, BINDINGS, STOCHASTIC)
        truth = evaluate(VARIED, state, BINDINGS, STOCHASTIC)
        assert explanation.chosen_branch == truth.branch_label
        # Stochastic mode evaluates every branch: traces are exhaustive.
        assert all(branch.considered for branch in explanation.branches)
        selected = [b for b in explanation.branches if b.selected]
        assert len(selected) == 1


def test_explain_stack_parity_on_presets_under_stochastic_policy() -> None:
    for preset_name in _all_preset_names():
        state, bindings = _resolve_preset(preset_name)
        truth = evaluate_stack(BUILTIN_TEMPLATES, state, bindings, STOCHASTIC)
        explanation = explain_stack(BUILTIN_TEMPLATES, state, bindings, STOCHASTIC)
        if truth is None:
            assert explanation.winner_id is None
            continue
        assert explanation.winner_id == truth.template_id
        winner = next(
            item
            for item in explanation.templates
            if item.template_id == truth.template_id
        )
        assert winner.chosen_branch == truth.branch_label


def test_select_branch_reports_considered_flags() -> None:
    state = _state(7)
    _, legacy_flags = select_branch(VARIED, state, BINDINGS, digest="d", selection=None)
    # Legacy short-circuits after the first passing branch.
    assert legacy_flags == (True, False, False)
    _, stochastic_flags = select_branch(
        VARIED, state, BINDINGS, digest="d", selection=STOCHASTIC
    )
    assert stochastic_flags == (True, True, True)


def test_coerce_branch_selection_shapes_and_errors() -> None:
    assert coerce_branch_selection(None) is None
    policy = coerce_branch_selection(
        {"mode": "stochastic", "temperature": 0.5, "seed_salt": "x"}
    )
    assert policy == BranchSelection("stochastic", 0.5, "x")
    assert coerce_branch_selection(policy) is policy

    with pytest.raises(ValueError, match="Unknown branch-selection mode"):
        BranchSelection(mode="chaotic")
    with pytest.raises(ValueError, match="temperature must be >= 0"):
        BranchSelection(mode="stochastic", temperature=-1)
