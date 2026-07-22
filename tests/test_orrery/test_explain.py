"""Real-state tests for the Orrery explain (audit) layer.

These exercise the production templates against the deterministic demo presets —
no mocks. The central invariant is that :func:`explain_stack` selects exactly the
same winner and branch as the production :func:`evaluate_stack`, while also
retaining the shadowed packages and gate traces the audit dashboard needs.
"""

from __future__ import annotations

import json

import pytest

from nexus.agents.orrery.demo import _all_preset_names, _resolve_preset
from nexus.agents.orrery.explain import (
    ConditionTrace,
    StackExplanation,
    explain_stack,
    explain_template,
)
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    BranchSelection,
    DriveBand,
    Slot,
    Template,
    WorldState,
    evaluate_stack,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES


def _leaves(node: ConditionTrace):
    if node.is_leaf:
        yield node
    for child in node.children:
        yield from _leaves(child)


@pytest.mark.parametrize("preset_name", _all_preset_names())
def test_explain_stack_matches_evaluate_stack(preset_name: str) -> None:
    """The audit layer must pick the same winner/branch as the resolver."""

    state, bindings = _resolve_preset(preset_name)
    truth = evaluate_stack(BUILTIN_TEMPLATES, state, bindings)
    explanation = explain_stack(BUILTIN_TEMPLATES, state, bindings)

    if truth is None:
        assert explanation.winner_id is None
        return

    assert explanation.winner_id == truth.template_id
    winner = next(
        item for item in explanation.templates if item.template_id == truth.template_id
    )
    assert winner.fired is True
    assert winner.chosen_branch == truth.branch_label
    assert winner.magnitude == truth.magnitude
    assert winner.event_type == truth.event_type
    assert winner.binding_hash == truth.binding_hash
    assert winner.changed_fields == truth.changed_fields
    assert winner.scene_pressure_stub == truth.scene_pressure_stub


def test_every_template_is_explained_in_priority_order() -> None:
    """The stack explanation covers all templates, highest priority first."""

    state, bindings = _resolve_preset("hunted")
    explanation = explain_stack(BUILTIN_TEMPLATES, state, bindings)

    assert len(explanation.templates) == len(BUILTIN_TEMPLATES)
    priorities = [item.priority for item in explanation.templates]
    assert priorities == sorted(priorities, reverse=True)


def test_winner_gate_and_branch_traces_are_coherent() -> None:
    """For the winner, the gate passes and only the chosen branch is selected."""

    state, bindings = _resolve_preset("hunted")
    explanation = explain_stack(BUILTIN_TEMPLATES, state, bindings)
    winner = next(
        item
        for item in explanation.templates
        if item.template_id == explanation.winner_id
    )

    assert winner.template_id == "evade_pursuers"
    assert winner.gate_passed is True
    assert winner.gate_trace.result is True

    selected = [b for b in winner.branches if b.selected]
    assert len(selected) == 1
    assert selected[0].trace is not None
    assert selected[0].trace.result is True

    # Branches after the selected one are never reached by the resolver.
    selected_index = winner.branches.index(selected[0])
    for branch in winner.branches[selected_index + 1 :]:
        assert branch.considered is False
        assert branch.trace is None


def test_shadowed_packages_surface() -> None:
    """A lower-priority package that also fires shows up as shadowed."""

    state, bindings = _resolve_preset("informant")
    explanation = explain_stack(BUILTIN_TEMPLATES, state, bindings)

    assert explanation.winner_id == "cultivate_informant"
    assert "surveil" in explanation.shadowed_ids

    surveil = next(
        item for item in explanation.templates if item.template_id == "surveil"
    )
    assert surveil.fired is True


def test_leaf_prose_matches_catalog_rendering() -> None:
    """Leaf labels reuse the catalog renderer, so prose matches the docs."""

    state, bindings = _resolve_preset("hunted")
    explanation = explain_stack(BUILTIN_TEMPLATES, state, bindings)
    winner = next(
        item for item in explanation.templates if item.template_id == "evade_pursuers"
    )

    prose = {leaf.prose for leaf in _leaves(winner.gate_trace)}
    assert "actor has inbound `hunting` pair tag" in prose


def test_explanation_is_json_serializable() -> None:
    """The dashboard consumes to_dict(); it must round-trip through JSON."""

    state, bindings = _resolve_preset("kin_danger")
    explanation: StackExplanation = explain_stack(BUILTIN_TEMPLATES, state, bindings)
    payload = json.loads(json.dumps(explanation.to_dict()))

    assert payload["winner_id"] == "protect_kin"
    assert payload["templates"]
    winner = next(t for t in payload["templates"] if t["is_winner"])
    assert winner["gate_trace"]["result"] is True
    assert winner["binding_hash"]
    assert isinstance(winner["changed_fields"], list)
    assert "scene_pressure_stub" in winner


def test_non_fired_templates_null_magnitude_and_event_in_payload() -> None:
    """Resolution defaults on non-fired templates must not look like data."""

    state, bindings = _resolve_preset("kin_danger")
    explanation = explain_stack(BUILTIN_TEMPLATES, state, bindings)
    payload = explanation.to_dict()

    non_fired = [t for t in payload["templates"] if not t["fired"]]
    assert non_fired, "preset expected to leave some templates un-fired"
    for template in non_fired:
        assert template["magnitude"] is None
        assert template["event_type"] is None

    fired = [t for t in payload["templates"] if t["fired"]]
    assert fired
    for template in fired:
        assert template["magnitude"] is not None


def test_single_passing_branch_does_not_claim_mood_affinity_weighting() -> None:
    """Explain records affinity only when stochastic weighting actually runs."""

    template = Template(
        id="single_passing_affinity",
        priority=1,
        drive_band=DriveBand.ANCHORED_ROUTINE,
        blurb="One eligible branch.",
        required_slots=(Slot.ACTOR,),
        package_gate=ALWAYS,
        branches=(
            Branch(
                "only",
                ALWAYS,
                "{actor} acts.",
                mood_affinities={"elated": 2.0},
            ),
        ),
    )
    explanation = explain_template(
        template,
        WorldState(
            ephemeral_tags={1: frozenset({"elated"})},
            mood_enabled=True,
        ),
        {Slot.ACTOR: 1},
        BranchSelection(mode="stochastic", temperature=1.0),
    )

    assert explanation.chosen_branch == "only"
    assert explanation.branches[0].applied_mood_affinity is None


@pytest.mark.parametrize(
    ("required_slots", "bindings", "expected_target"),
    (
        (
            (Slot.ACTOR, Slot.TARGET),
            {Slot.ACTOR: 1, Slot.TARGET: 2},
            {"target_character_entity_id": 2},
        ),
        (
            (Slot.ACTOR, Slot.FACTION),
            {Slot.ACTOR: 1, Slot.FACTION: 3},
            {"target_faction_entity_id": 3},
        ),
    ),
)
def test_explain_materializes_polymorphic_patron_target(
    required_slots: tuple[Slot, ...],
    bindings: dict[Slot, int],
    expected_target: dict[str, int],
) -> None:
    """Dashboard explanations expose the same commit-ready target shape."""

    template = Template(
        id="explain_polymorphic_patron",
        priority=1,
        drive_band=DriveBand.PROJECT_IDENTITY,
        blurb="Explain polymorphic patron materialization.",
        required_slots=required_slots,
        package_gate=ALWAYS,
        branches=(
            Branch(
                "start",
                ALWAYS,
                "{actor} courts a patron.",
                state_delta={
                    "project.start": {
                        "project_type": "court_patron",
                        "stage": "gaining_notice",
                    }
                },
            ),
        ),
        binds_project_faction=Slot.FACTION in required_slots,
    )

    explanation = explain_template(template, WorldState(), bindings)

    assert explanation.state_delta["project.start"] == {
        "project_type": "court_patron",
        "stage": "gaining_notice",
        **expected_target,
    }
