"""Tests for the Orrery pure-Python behavior substrate."""

import re
from typing import Any

import pytest

from nexus.agents.orrery.demo import run_preset
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    CompoundCondition,
    PresentTargetPolicy,
    Slot,
    Template,
    WorldState,
    binding_hash,
    count_co_located,
    evaluate_stack,
    has_symmetric_relationship_of_type,
    recent_event,
    since_last_event_at_least,
    validate_always_fallbacks,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES


_SINCE_LAST_EVENT_RE = re.compile(r"since_last_event_at_least\(([^,()]+),")


def _collect_since_last_event_types(condition: Any) -> set[str]:
    """Walk a condition tree and collect package-gate cooldown event types."""

    if isinstance(condition, CompoundCondition):
        event_types: set[str] = set()
        for child in condition.children:
            event_types.update(_collect_since_last_event_types(child))
        return event_types

    match = _SINCE_LAST_EVENT_RE.search(getattr(condition, "__name__", ""))
    if not match:
        return set()
    return {match.group(1)}


def test_builtin_templates_have_always_fallbacks() -> None:
    """Built-in templates must end in a deterministic fallback branch."""

    validate_always_fallbacks(BUILTIN_TEMPLATES)


def test_gate_cooldown_chain_covers_branch_events() -> None:
    """Template-level cooldown gates must cover every branch event type."""

    for template in BUILTIN_TEMPLATES:
        branch_event_types = {
            branch.event_type for branch in template.branches if branch.event_type
        }
        gate_cooldown_event_types = _collect_since_last_event_types(
            template.package_gate
        )
        if not gate_cooldown_event_types:
            continue

        missing = branch_event_types - gate_cooldown_event_types

        assert not missing, (
            f"Template {template.id}: branches emit {sorted(missing)} but "
            "the gate doesn't include them in any "
            "since_last_event_at_least(...) cooldown. This lets those "
            "branches bypass the template's pacing intent."
        )


def test_missing_always_fallback_is_rejected() -> None:
    """Template authors get a loud error when a fallback branch is missing."""

    template = Template(
        id="bad_template",
        priority=1,
        blurb="No terminal fallback.",
        required_slots=(Slot.ACTOR,),
        package_gate=ALWAYS,
        branches=(
            Branch(
                "non-fallback",
                lambda _state, _bindings: True,
                "{actor} does a thing.",
            ),
        ),
    )

    with pytest.raises(ValueError, match="bad_template"):
        validate_always_fallbacks((template,))


def test_storyteller_pressure_templates_require_pressure_stubs() -> None:
    """Template authors must provide prompt text for every pressure branch."""

    with pytest.raises(ValueError, match="scene_pressure_stub.*missing"):
        Template(
            id="bad_pressure_template",
            priority=1,
            blurb="Missing prompt-only pressure text.",
            required_slots=(Slot.ACTOR, Slot.TARGET),
            package_gate=ALWAYS,
            branches=(
                Branch(
                    "missing pressure",
                    ALWAYS,
                    "{actor} affects {target}.",
                ),
            ),
            present_target_policy=PresentTargetPolicy.STORYTELLER_PRESSURE,
        )


@pytest.mark.parametrize(
    ("preset", "template_id", "branch_label"),
    [
        ("hunted", "evade_pursuers", "Go to ground in flooded tunnels"),
        ("fragment", "pursue_ghost_lead", "Recon a hideout their body remembers"),
        ("debt", "honor_debt", "Fulfill obligation through a dead-drop"),
        ("quiet", "maintain_cover", "Run a low-level courier job"),
        (
            "vengeance",
            "extract_vengeance",
            "Strike directly when opportunity opens",
        ),
        (
            "kin_danger",
            "protect_kin",
            "Physically intervene at the target's location",
        ),
        (
            "informant",
            "cultivate_informant",
            "Routine contact to maintain the relationship",
        ),
        # Round-2 templates
        (
            "mourning",
            "mourn_loss",
            "Visit the place of remembrance",
        ),
        (
            "craft_soldier",
            "tend_craft",
            "Make the weapon ready for what comes next",
        ),
        (
            "wounded_healing",
            "tend_wounded",
            "Channel restorative power through hands and voice",
        ),
        (
            "vigil_devout",
            "keep_vigil",
            "Maintain prayerful or meditative presence",
        ),
        (
            "warning",
            "warn_ally",
            "Reach the ally face-to-face before the word gets out",
        ),
        (
            "welfare_check",
            "check_on_dependent",
            "Drop by in person when the moment allows",
        ),
        (
            "kin_visit",
            "reach_out_to_kin",
            "Find the moment for a real face-to-face conversation",
        ),
        (
            "rival_truce",
            "consult_rival",
            "Meet face-to-face on neutral ground",
        ),
    ],
)
def test_demo_presets_fire_expected_package(
    preset: str, template_id: str, branch_label: str
) -> None:
    """The offline harness mirrors the original simulator's key presets."""

    result = run_preset(preset)

    assert result["fired"] is True
    assert result["template_id"] == template_id
    assert result["branch_label"] == branch_label


def test_has_symmetric_relationship_of_type_matches_either_direction() -> None:
    """Symmetric helper finds a typed relationship regardless of stored order."""

    forward_state = WorldState(
        relationship_types={(1, 2): frozenset({"family"})},
    )
    reverse_state = WorldState(
        relationship_types={(2, 1): frozenset({"family"})},
    )
    empty_state = WorldState()
    predicate = has_symmetric_relationship_of_type("family")
    bindings = {Slot.ACTOR: 1, Slot.TARGET: 2}

    assert predicate(forward_state, bindings)
    assert predicate(reverse_state, bindings)
    assert not predicate(empty_state, bindings)


def test_since_last_event_at_least_target_slot_scopes_cooldown() -> None:
    """When target_slot is given, the cooldown is per-(actor, target) pair.

    Models the CULTIVATE_INFORMANT case: handler A contacting informant B
    must not block A from contacting informant C in the same window.
    """

    from nexus.agents.orrery.substrate import EventRecord

    state = WorldState(
        recent_events=(
            EventRecord(
                event_type="informant_contact",
                tick=9,
                actor_entity_id=1,
                target_entity_id=2,
            ),
        ),
        current_tick=10,
    )

    actor_global = since_last_event_at_least("informant_contact", 5)
    per_target = since_last_event_at_least(
        "informant_contact",
        5,
        target_slot=Slot.TARGET,
    )

    # Actor-global: the recent contact resets the cooldown regardless of
    # which target the binding names.
    assert not actor_global(state, {Slot.ACTOR: 1, Slot.TARGET: 2})
    assert not actor_global(state, {Slot.ACTOR: 1, Slot.TARGET: 3})

    # Per-target: only the same (actor, target) pair sees the cooldown.
    assert not per_target(state, {Slot.ACTOR: 1, Slot.TARGET: 2})
    assert per_target(state, {Slot.ACTOR: 1, Slot.TARGET: 3})


def test_targeted_events_fire_builtin_package_gates() -> None:
    """Built-ins that react to incoming events use target-role matching."""

    from nexus.agents.orrery.substrate import EventRecord

    state = WorldState(
        locations={1: 10},
        location_class={10: "the_roots"},
        recent_events=(
            EventRecord(
                event_type="compliance_alert",
                tick=99,
                target_entity_id=1,
            ),
        ),
        weather="rain",
        current_tick=100,
    )

    result = evaluate_stack(BUILTIN_TEMPLATES, state, {Slot.ACTOR: 1})

    assert result is not None
    assert result.template_id == "evade_pursuers"


def test_count_co_located_condition_filters_by_tag() -> None:
    """Co-location can be counted with a tag filter for crowd-like gates."""

    state = WorldState(
        tags={
            2: frozenset({"pursuer"}),
            3: frozenset({"bystander"}),
            4: frozenset({"pursuer"}),
        },
        locations={1: 10, 2: 10, 3: 10, 4: 11},
    )

    assert count_co_located(1, with_tag="pursuer")(state, {Slot.ACTOR: 1})
    assert not count_co_located(2, with_tag="pursuer")(state, {Slot.ACTOR: 1})


def test_recent_event_can_filter_by_changed_fields() -> None:
    """Recent-event predicates can use the controlled changed_fields surface."""

    from nexus.agents.orrery.substrate import EventRecord

    state = WorldState(
        recent_events=(
            EventRecord(
                event_type="state_update",
                tick=9,
                actor_entity_id=1,
                changed_fields=("character.current_location",),
            ),
        ),
        current_tick=10,
    )

    assert recent_event(
        changed_fields_any_of=("character.current_location",),
        actor_slot=Slot.ACTOR,
    )(state, {Slot.ACTOR: 1})
    assert not recent_event(
        changed_fields_any_of=("character.emotional_state",),
        actor_slot=Slot.ACTOR,
    )(state, {Slot.ACTOR: 1})


def test_recent_event_preserves_actor_target_roles() -> None:
    """Actor and target filters match their corresponding event fields only."""

    from nexus.agents.orrery.substrate import EventRecord

    state = WorldState(
        recent_events=(
            EventRecord(
                event_type="warning",
                tick=9,
                actor_entity_id=1,
                target_entity_id=2,
            ),
        ),
        current_tick=10,
    )

    assert recent_event("warning", actor_slot=Slot.ACTOR)(state, {Slot.ACTOR: 1})
    assert recent_event("warning", target_slot=Slot.ACTOR)(state, {Slot.ACTOR: 2})
    assert not recent_event("warning", actor_slot=Slot.ACTOR)(state, {Slot.ACTOR: 2})
    assert not recent_event("warning", target_slot=Slot.ACTOR)(state, {Slot.ACTOR: 1})
    assert recent_event(
        "warning",
        actor_slot=Slot.ACTOR,
        target_slot=Slot.TARGET,
    )(state, {Slot.ACTOR: 1, Slot.TARGET: 2})
    assert not recent_event(
        "warning",
        actor_slot=Slot.ACTOR,
        target_slot=Slot.TARGET,
    )(state, {Slot.ACTOR: 2, Slot.TARGET: 1})


def test_since_last_event_at_least_preserves_actor_role() -> None:
    """Cooldown predicates do not treat target-only events as actor matches."""

    from nexus.agents.orrery.substrate import EventRecord

    state = WorldState(
        recent_events=(
            EventRecord(
                event_type="warning",
                tick=9,
                actor_entity_id=2,
                target_entity_id=1,
            ),
        ),
        current_tick=10,
    )

    assert since_last_event_at_least("warning", 5)(state, {Slot.ACTOR: 1})
    assert not since_last_event_at_least("warning", 5)(state, {Slot.ACTOR: 2})


def test_binding_hash_handles_runtime_non_slot_keys() -> None:
    """Runtime callers that pass non-Slot keys get a deterministic hash."""

    assert binding_hash({Slot.ACTOR: 1, "custom": 2}) == binding_hash(
        {"custom": 2, Slot.ACTOR: 1}
    )


def test_evaluate_stack_returns_none_when_no_template_passes() -> None:
    """The resolver stack can represent no-op ticks explicitly."""

    template = Template(
        id="never",
        priority=1,
        blurb="Never fires.",
        required_slots=(Slot.ACTOR,),
        package_gate=lambda _state, _bindings: False,
        branches=(Branch("fallback", ALWAYS, "{actor} idles."),),
    )

    assert evaluate_stack((template,), WorldState(), {Slot.ACTOR: 1}) is None
