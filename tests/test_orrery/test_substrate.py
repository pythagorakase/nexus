"""Tests for the Orrery pure-Python behavior substrate."""

from datetime import datetime, timezone
import re
from typing import Any

import pytest

from nexus.agents.orrery.demo import run_preset
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    CompoundCondition,
    DriveBand,
    PresentTargetPolicy,
    RoutineAnchor,
    Slot,
    Template,
    TravelState,
    WorldState,
    at_routine_anchor,
    binding_hash,
    away_from_routine_anchor,
    can_move_publicly,
    co_located,
    count_co_located,
    count_recent_events_at_least,
    contact_pair_tag_for_kind,
    direct_contact_is_dramatic,
    evaluate_stack,
    has_any_pair_tag,
    has_any_intimacy_suppressor,
    has_contact_of_kind,
    has_established_partner_co_located,
    has_inbound_pair_tag,
    has_location_class_destination,
    has_minimal_context,
    has_need_debt_at_or_above,
    has_pair_tag,
    has_pair_tag_to_current_location,
    has_routine_anchor,
    has_severity_tag_at_or_above,
    has_symmetric_relationship_of_type,
    in_location,
    in_location_class,
    is_constrained,
    is_hidden,
    lacks_pair_tag,
    recent_event,
    relationship_is_asymmetric,
    relationship_is_mutual_warm,
    routine_anchor_due,
    routine_anchor_has_destination,
    since_last_event_at_least,
    travel_purpose_is,
    validate_always_fallbacks,
)
from nexus.agents.orrery.templates import (
    ADVANCE_BUILD_VENTURE,
    ADVANCE_COURT_PATRON,
    ADVANCE_PURSUE_ROMANCE,
    ADVANCE_SEEK_REDEMPTION,
    BUILTIN_TEMPLATES,
    EXTRACT_VENGEANCE,
    RECREATE,
)


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


def test_builtin_mood_affinity_consumers_cover_requested_read_channels() -> None:
    """Mood reads bias vengeance, aspiration progress, romance, and recreation."""

    def branch(template: Template, label: str) -> Branch:
        return next(item for item in template.branches if item.label == label)

    assert branch(
        EXTRACT_VENGEANCE, "Strike directly when opportunity opens"
    ).mood_affinities == {"restless": 2.0, "grim": 1.5}
    # The rebuffed arm stays preemptive with NO affinity: a rebuff is a
    # deterministic guard (the recruit_ally withdraw-arm contract), never
    # a stochastic lean.
    rebuffed = branch(ADVANCE_PURSUE_ROMANCE, "Withdraw after being rebuffed")
    assert rebuffed.mood_affinities == {}
    assert rebuffed.preemptive is True
    assert branch(RECREATE, "Find games and company").mood_affinities == {"elated": 1.5}
    for template in (
        ADVANCE_PURSUE_ROMANCE,
        ADVANCE_COURT_PATRON,
        ADVANCE_SEEK_REDEMPTION,
        ADVANCE_BUILD_VENTURE,
    ):
        assert template.branches[-1].mood_affinities == {"elated": 1.5}


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
        drive_band=DriveBand.PROJECT_IDENTITY,
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
            drive_band=DriveBand.PROJECT_IDENTITY,
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
        ("fragment", "uncover_past", "Revisit a place their body remembers"),
        ("debt", "honor_debt", "Fulfill obligation through a dead-drop"),
        ("quiet", "maintain_cover", "Run a low-level courier job"),
        ("hiding", "hide", "Go dark and reduce signal exposure"),
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
        (
            "surveillance",
            "surveil",
            "Intercept signal traffic",
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
            "reach_out",
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


def test_pair_tag_predicates_are_direction_sensitive() -> None:
    """Directed pair-tag helpers read WorldState pair tags without symmetrizing."""

    state = WorldState(pair_tags={(1, 2): frozenset({"mentors", "protects"})})
    bindings = {Slot.ACTOR: 1, Slot.TARGET: 2}
    reversed_bindings = {Slot.ACTOR: 2, Slot.TARGET: 1}

    assert has_pair_tag("mentors")(state, bindings)
    assert has_any_pair_tag("claims", "protects")(state, bindings)
    assert not has_pair_tag("mentors")(state, reversed_bindings)
    assert not has_pair_tag("hunting")(state, bindings)


def test_inbound_pair_tag_predicate_matches_any_subject() -> None:
    """Inbound pair-tag gates ask who points a relation at a slot entity."""

    state = WorldState(
        pair_tags={
            (1, 2): frozenset({"hunting"}),
            (3, 2): frozenset({"hunting"}),
            (2, 4): frozenset({"hunting"}),
        }
    )

    assert has_inbound_pair_tag("hunting")(state, {Slot.ACTOR: 2})
    assert not has_inbound_pair_tag("hunting")(state, {Slot.ACTOR: 1})
    assert has_inbound_pair_tag("hunting", slot=Slot.TARGET)(
        state,
        {Slot.ACTOR: 99, Slot.TARGET: 4},
    )


def test_contact_kind_predicate_reads_outbound_kind_specific_edges() -> None:
    """Contact-kind gates match outbound contact:<kind> pair-tags only."""

    state = WorldState(
        pair_tags={
            (1, 2): frozenset({"contact:social"}),
            (2, 1): frozenset({"contact:lodging"}),
            (1, 3): frozenset({"ally"}),
        }
    )

    assert has_contact_of_kind("social")(state, {Slot.ACTOR: 1})
    assert not has_contact_of_kind("lodging")(state, {Slot.ACTOR: 1})
    assert has_contact_of_kind("lodging")(state, {Slot.ACTOR: 2})
    assert not has_contact_of_kind("intimate")(state, {Slot.ACTOR: 1})
    assert not has_contact_of_kind("social")(state, {Slot.TARGET: 1})


def test_contact_pair_tag_for_kind_rejects_unknown_kind() -> None:
    """Contact-kind helpers fail loudly instead of inventing vocabulary."""

    with pytest.raises(ValueError, match="Unsupported contact kind"):
        contact_pair_tag_for_kind("medical")  # type: ignore[arg-type]


def test_lacks_pair_tag_is_inverse_for_bound_slots() -> None:
    """lacks_pair_tag is true for wrong direction, wrong tag, or missing slots."""

    state = WorldState(pair_tags={(1, 2): frozenset({"mentors"})})

    assert not lacks_pair_tag("mentors")(state, {Slot.ACTOR: 1, Slot.TARGET: 2})
    assert lacks_pair_tag("mentors")(state, {Slot.ACTOR: 2, Slot.TARGET: 1})
    assert lacks_pair_tag("protects")(state, {Slot.ACTOR: 1, Slot.TARGET: 2})
    assert lacks_pair_tag("mentors")(state, {Slot.ACTOR: 1})


def test_pair_tag_to_current_location_uses_place_entity_id() -> None:
    """Current-location pair checks bridge places.id to place entity ids."""

    state = WorldState(
        locations={1: 10},
        location_entity_ids={10: 1000},
        pair_tags={(1, 1000): frozenset({"resides_at"})},
    )

    assert has_pair_tag_to_current_location("resides_at")(state, {Slot.ACTOR: 1})
    assert not has_pair_tag_to_current_location("operates_from")(state, {Slot.ACTOR: 1})
    assert not has_pair_tag_to_current_location("resides_at")(
        WorldState(locations={1: 10}), {Slot.ACTOR: 1}
    )


def test_routine_anchor_predicates_use_schedule_and_place() -> None:
    """Routine anchors are explicit actor facts with clock windows."""

    state = WorldState(
        locations={1: 10},
        routine_anchors={
            (1, "work"): RoutineAnchor(
                anchor_type="work",
                place_id=10,
                schedule={
                    "weekdays": [0, 1, 2, 3, 4],
                    "start": "09:00",
                    "end": "17:00",
                },
            )
        },
        world_time=datetime(2073, 10, 30, 10, 30, tzinfo=timezone.utc),
    )

    assert has_routine_anchor("work")(state, {Slot.ACTOR: 1})
    assert routine_anchor_due("work")(state, {Slot.ACTOR: 1})
    assert at_routine_anchor("work")(state, {Slot.ACTOR: 1})
    assert not away_from_routine_anchor("work")(state, {Slot.ACTOR: 1})


def test_routine_anchor_predicates_support_overnight_home_windows() -> None:
    """Home schedules can cross midnight without special-case templates."""

    state = WorldState(
        locations={1: 10},
        routine_anchors={
            (1, "home"): RoutineAnchor(
                anchor_type="home",
                place_id=10,
                schedule={"start": "17:00", "end": "08:30"},
            )
        },
        world_time=datetime(2073, 10, 31, 0, 15, tzinfo=timezone.utc),
    )

    assert routine_anchor_due("home")(state, {Slot.ACTOR: 1})
    assert at_routine_anchor("home")(state, {Slot.ACTOR: 1})


def test_work_from_home_anchor_resolves_against_home_anchor() -> None:
    """A work anchor can intentionally collapse onto the home place."""

    state = WorldState(
        locations={1: 10},
        routine_anchors={
            (1, "home"): RoutineAnchor(anchor_type="home", place_id=10),
            (1, "work"): RoutineAnchor(
                anchor_type="work",
                mobility_policy="works_from_home",
            ),
        },
    )

    assert at_routine_anchor("work")(state, {Slot.ACTOR: 1})
    assert routine_anchor_has_destination("work")(state, {Slot.ACTOR: 1})


def test_malformed_home_work_from_home_anchor_does_not_recurse() -> None:
    """In-memory fixtures fail closed if home is accidentally work-from-home."""

    state = WorldState(
        locations={1: 10},
        routine_anchors={
            (1, "home"): RoutineAnchor(
                anchor_type="home",
                mobility_policy="works_from_home",
            ),
        },
    )

    assert not at_routine_anchor("home")(state, {Slot.ACTOR: 1})
    assert not routine_anchor_has_destination("home")(state, {Slot.ACTOR: 1})


def test_routine_schedule_reports_non_numeric_times_cleanly() -> None:
    """Malformed schedule times raise the same actionable HH:MM error."""

    state = WorldState(
        routine_anchors={
            (1, "home"): RoutineAnchor(
                anchor_type="home",
                place_id=10,
                schedule={"start": "HH:MM", "end": "08:30"},
            ),
        },
        world_time=datetime(2073, 10, 31, 0, 15, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="must be HH:MM"):
        routine_anchor_due("home")(state, {Slot.ACTOR: 1})


def test_context_and_constraint_predicates_read_current_tags() -> None:
    """Package guards can distinguish hydrated actors from constrained ones."""

    assert has_minimal_context()(
        WorldState(tags={1: frozenset({"off_grid"})}), {Slot.ACTOR: 1}
    )
    assert has_minimal_context()(WorldState(locations={1: 10}), {Slot.ACTOR: 1})
    assert not has_minimal_context()(WorldState(), {Slot.ACTOR: 1})
    assert is_constrained()(
        WorldState(ephemeral_tags={1: frozenset({"sandboxed"})}), {Slot.ACTOR: 1}
    )
    assert not is_constrained()(
        WorldState(ephemeral_tags={1: frozenset({"wounded"})}), {Slot.ACTOR: 1}
    )
    assert is_hidden()(
        WorldState(tags={1: frozenset({"presumed_dead"})}), {Slot.ACTOR: 1}
    )
    assert is_hidden()(WorldState(tags={1: frozenset({"deep_cover"})}), {Slot.ACTOR: 1})


def test_public_mobility_requires_public_context_and_freedom() -> None:
    """Public-flow package branches should not fire inside blacksites."""

    public_state = WorldState(
        locations={1: 10},
        location_classes={10: frozenset({"commerce"})},
    )
    private_state = WorldState(
        locations={1: 11},
        location_classes={11: frozenset({"blacksite"})},
    )
    captive_state = WorldState(
        tags={1: frozenset({"route_familiar"})},
        ephemeral_tags={1: frozenset({"captive"})},
        locations={1: 10},
        location_classes={10: frozenset({"commerce"})},
    )

    assert can_move_publicly()(public_state, {Slot.ACTOR: 1})
    assert not can_move_publicly()(private_state, {Slot.ACTOR: 1})
    assert not can_move_publicly()(captive_state, {Slot.ACTOR: 1})


def test_public_mobility_can_use_social_contact_channel() -> None:
    """A social contact preserves the old contacts_available mobility affordance."""

    state = WorldState(pair_tags={(1, 2): frozenset({"contact:social"})})

    assert can_move_publicly()(state, {Slot.ACTOR: 1})
    assert not can_move_publicly()(state, {Slot.ACTOR: 2})


def test_relationship_contact_predicates_capture_asymmetry() -> None:
    """Kin/contact templates can distinguish warmth from loaded contact."""

    warm_state = WorldState(trust={(1, 2): 3, (2, 1): 2})
    estranged_state = WorldState(trust={(1, 2): 5, (2, 1): -3})
    hidden_state = WorldState(
        tags={1: frozenset({"presumed_dead"})},
        trust={(1, 2): 3, (2, 1): 2},
    )
    bindings = {Slot.ACTOR: 1, Slot.TARGET: 2}

    assert relationship_is_mutual_warm()(warm_state, bindings)
    assert not relationship_is_mutual_warm()(estranged_state, bindings)
    assert relationship_is_asymmetric()(estranged_state, bindings)
    assert direct_contact_is_dramatic()(estranged_state, bindings)
    assert direct_contact_is_dramatic()(hidden_state, bindings)


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


def test_in_transit_entities_are_not_treated_as_at_anchor_location() -> None:
    """Travel state keeps legacy current_location readable but non-physical."""

    state = WorldState(
        locations={1: 10, 2: 10},
        location_class={10: "home"},
        relationship_types={(1, 2): frozenset({"romantic"})},
        travel_states={
            1: TravelState(
                status="in_transit",
                anchor_place_id=10,
                origin_place_id=10,
                destination_place_id=20,
                progress_ratio=0.5,
            )
        },
    )
    bindings = {Slot.ACTOR: 1, Slot.TARGET: 2}

    assert not in_location(10)(state, bindings)
    assert not in_location_class("home")(state, bindings)
    assert not co_located()(state, bindings)
    assert not count_co_located(1)(state, {Slot.ACTOR: 1})
    assert not count_co_located(1)(state, {Slot.ACTOR: 2})
    assert not has_established_partner_co_located()(state, {Slot.ACTOR: 1})
    assert not has_established_partner_co_located()(state, {Slot.ACTOR: 2})


def test_targeted_events_fire_builtin_package_gates() -> None:
    """Built-ins that react to incoming events use target-role matching."""

    from nexus.agents.orrery.substrate import EventRecord

    state = WorldState(
        locations={1: 10},
        location_classes={10: frozenset({"subterranean", "transit"})},
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


def test_mealtime_at_home_beats_routine_thirst() -> None:
    """Moderate thirst yields to dinner when a home meal is otherwise due."""

    state = WorldState(
        locations={1: 10},
        location_classes={10: frozenset({"dwelling"})},
        location_entity_ids={10: 100},
        pair_tags={(1, 100): frozenset({"resides_at"})},
        need_debt_scores={
            (1, "hunger"): 8.0,
            (1, "thirst"): 8.0,
        },
        time_of_day="evening",
        current_tick=100,
    )

    result = evaluate_stack(BUILTIN_TEMPLATES, state, {Slot.ACTOR: 1})

    assert result is not None
    assert result.template_id == "eat"
    assert result.branch_label == "Eat at home alone"


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


def test_established_partner_co_location_uses_relationships() -> None:
    """Partner co-location does not treat arbitrary co-presence as intimacy."""

    predicate = has_established_partner_co_located()
    partnered_state = WorldState(
        relationship_types={(1, 2): frozenset({"romantic"})},
        locations={1: 10, 2: 10, 3: 10},
    )
    bystander_state = WorldState(
        relationship_types={(1, 2): frozenset({"romantic"})},
        locations={1: 10, 2: 11, 3: 10},
    )
    reverse_partnered_state = WorldState(
        relationship_types={(2, 1): frozenset({"romantic"})},
        locations={1: 10, 2: 10},
    )

    assert predicate(partnered_state, {Slot.ACTOR: 1})
    assert predicate(reverse_partnered_state, {Slot.ACTOR: 1})
    assert not predicate(bystander_state, {Slot.ACTOR: 1})


def test_need_debt_condition_reads_world_state_scores() -> None:
    """Sunhelm gates read effective need debt from hydrated world state."""

    state = WorldState(need_debt_scores={(1, "sleep"): 12.5})

    assert has_need_debt_at_or_above("sleep", 8)(state, {Slot.ACTOR: 1})
    assert not has_need_debt_at_or_above("sleep", 16)(state, {Slot.ACTOR: 1})


def test_location_class_condition_reads_semantic_place_classes() -> None:
    """Location predicates can match one of several semantic place tags."""

    state = WorldState(
        locations={1: 10},
        location_classes={10: frozenset({"fixed_location", "dwelling", "haven"})},
    )

    assert in_location_class("dwelling")(state, {Slot.ACTOR: 1})
    assert in_location_class("haven")(state, {Slot.ACTOR: 1})
    assert not in_location_class("wilderness")(state, {Slot.ACTOR: 1})


def test_location_class_condition_preserves_single_value_fallback() -> None:
    """Older harnesses using location_class keep working."""

    state = WorldState(locations={1: 10}, location_class={10: "the_roots"})

    assert in_location_class("the_roots")(state, {Slot.ACTOR: 1})


def test_location_class_destination_condition_finds_other_places() -> None:
    """Movement packages can ask whether a class-resolved destination exists."""

    state = WorldState(
        locations={1: 10},
        location_classes={
            10: frozenset({"dwelling"}),
            20: frozenset({"meeting", "commerce"}),
        },
    )
    current_only = WorldState(
        locations={1: 10},
        location_classes={10: frozenset({"meeting"})},
    )

    assert has_location_class_destination("meeting")(state, {Slot.ACTOR: 1})
    assert has_location_class_destination("commerce")(state, {Slot.ACTOR: 1})
    assert not has_location_class_destination("meeting")(current_only, {Slot.ACTOR: 1})


def test_location_class_destination_condition_supports_legacy_single_class() -> None:
    """The destination check also covers the pre-multi-class location mapping."""

    state = WorldState(
        locations={1: 10},
        location_class={
            10: "dwelling",
            20: "meeting",
        },
    )

    assert has_location_class_destination("meeting")(state, {Slot.ACTOR: 1})


def test_travel_purpose_condition_reads_route_metadata() -> None:
    """Travel branches can distinguish why an actor is currently moving."""

    state = WorldState(
        travel_states={
            1: TravelState(status="in_transit", route_purpose="Socialize"),
        }
    )

    assert travel_purpose_is("SOCIALIZE")(state, {Slot.ACTOR: 1})
    assert not travel_purpose_is("socialize")(
        WorldState(travel_states={1: TravelState(status="in_transit")}),
        {Slot.ACTOR: 1},
    )


def test_travel_purpose_condition_rejects_unknown_purposes() -> None:
    """Typos in travel-purpose predicates fail at construction time."""

    with pytest.raises(ValueError, match="Unsupported Orrery travel purpose"):
        travel_purpose_is("work")


def test_need_debt_condition_rejects_unknown_need_type() -> None:
    """Typos in authored need predicates fail at construction time."""

    with pytest.raises(ValueError, match="Unsupported Orrery need type"):
        has_need_debt_at_or_above("hungr", 8)


def test_severity_tag_threshold_parses_level_prefix() -> None:
    """Severity predicates compare the numeric segment of graduated tags."""

    state = WorldState(tags={1: frozenset({"sleep_deprived_3_severe"})})

    assert has_severity_tag_at_or_above("sleep_deprived", 2)(state, {Slot.ACTOR: 1})
    assert not has_severity_tag_at_or_above("sleep_deprived", 4)(state, {Slot.ACTOR: 1})


def test_intimacy_suppressor_reads_durable_and_ephemeral_tags() -> None:
    """Intimacy gates can honor named suppressors without generic tags."""

    predicate = has_any_intimacy_suppressor()

    assert predicate(
        WorldState(tags={1: frozenset({"closeted"})}),
        {Slot.ACTOR: 1},
    )
    assert predicate(
        WorldState(ephemeral_tags={1: frozenset({"grieving"})}),
        {Slot.ACTOR: 1},
    )
    assert predicate(
        WorldState(ephemeral_tags={1: frozenset({"focus_committed"})}),
        {Slot.ACTOR: 1},
    )
    assert predicate(
        WorldState(tags={1: frozenset({"libido_absent"})}),
        {Slot.ACTOR: 1},
    )
    assert not predicate(
        WorldState(tags={1: frozenset({"libido_moderate"})}),
        {Slot.ACTOR: 1},
    )


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


def test_count_recent_events_at_least_thresholds_and_scope() -> None:
    """The counting predicate honors min_count, window, actor role, and target scope."""

    from nexus.agents.orrery.substrate import EventRecord

    def act(tick: int, target: int = 2) -> EventRecord:
        return EventRecord(
            event_type="mourning_act",
            tick=tick,
            actor_entity_id=1,
            target_entity_id=target,
        )

    state = WorldState(
        recent_events=(act(4), act(7), act(10, target=3), act(13)),
        current_tick=15,
    )

    assert count_recent_events_at_least("mourning_act", within_ticks=15, min_count=4)(
        state, {Slot.ACTOR: 1}
    )
    assert not count_recent_events_at_least(
        "mourning_act", within_ticks=15, min_count=5
    )(state, {Slot.ACTOR: 1})
    # Window cutoff drops the tick-4 event.
    assert not count_recent_events_at_least(
        "mourning_act", within_ticks=10, min_count=4
    )(state, {Slot.ACTOR: 1})
    # Actor role is strict: entity 2 was only ever a target.
    assert not count_recent_events_at_least(
        "mourning_act", within_ticks=15, min_count=1
    )(state, {Slot.ACTOR: 2})
    # Target scoping counts only the pair's events.
    assert count_recent_events_at_least(
        "mourning_act", within_ticks=15, min_count=3, target_slot=Slot.TARGET
    )(state, {Slot.ACTOR: 1, Slot.TARGET: 2})
    assert not count_recent_events_at_least(
        "mourning_act", within_ticks=15, min_count=4, target_slot=Slot.TARGET
    )(state, {Slot.ACTOR: 1, Slot.TARGET: 2})


def test_mourn_loss_completes_after_sustained_mourning() -> None:
    """Enough mourning acts trigger the terminal branch that clears grief.

    The terminal branch emits mourning_completed — the event the `grieving`
    tag's clear_on rule digests. Without it grief is an absorbing state.
    """

    from nexus.agents.orrery.substrate import EventRecord, evaluate
    from nexus.agents.orrery.templates import MOURN_LOSS

    def acts(*ticks: int) -> tuple[EventRecord, ...]:
        return tuple(
            EventRecord(event_type="mourning_act", tick=t, actor_entity_id=1)
            for t in ticks
        )

    fresh_grief = WorldState(
        ephemeral_tags={1: frozenset({"grieving"})},
        recent_events=acts(20),
        current_tick=25,
    )
    ongoing = evaluate(MOURN_LOSS, fresh_grief, {Slot.ACTOR: 1})
    assert ongoing.passes is True
    assert ongoing.event_type == "mourning_act"

    worked_grief = WorldState(
        ephemeral_tags={1: frozenset({"grieving"})},
        recent_events=acts(8, 12, 16, 20),
        current_tick=25,
    )
    completed = evaluate(MOURN_LOSS, worked_grief, {Slot.ACTOR: 1})
    assert completed.passes is True
    assert completed.branch_label == "Lay the grief down"
    assert completed.event_type == "mourning_completed"


def test_evaluate_stack_returns_none_when_no_template_passes() -> None:
    """The resolver stack can represent no-op ticks explicitly."""

    template = Template(
        id="never",
        priority=1,
        drive_band=DriveBand.PROJECT_IDENTITY,
        blurb="Never fires.",
        required_slots=(Slot.ACTOR,),
        package_gate=lambda _state, _bindings: False,
        branches=(Branch("fallback", ALWAYS, "{actor} idles."),),
    )

    assert evaluate_stack((template,), WorldState(), {Slot.ACTOR: 1}) is None
