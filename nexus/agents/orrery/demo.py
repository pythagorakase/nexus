"""Offline harness for exercising Orrery behavior packages."""

from __future__ import annotations

import argparse
import json
from typing import Dict

from nexus.agents.orrery.substrate import (
    Bindings,
    EventRecord,
    Slot,
    WorldState,
    evaluate_stack,
    validate_always_fallbacks,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES

ACTOR_ID = 1
TARGET_ID = 2
ROOTS_PLACE_ID = 101
GLOW_PLACE_ID = 102
STACKS_PLACE_ID = 103
REMEMBRANCE_PLACE_ID = 104
NEUTRAL_PLACE_ID = 105


def build_presets() -> Dict[str, WorldState]:
    """Return deterministic demo states that mirror the original JSX simulator."""

    common_locations = {
        ACTOR_ID: ROOTS_PLACE_ID,
        2: ROOTS_PLACE_ID,
        3: GLOW_PLACE_ID,
    }
    legacy_location_class = {
        ROOTS_PLACE_ID: "fixed_location",
        GLOW_PLACE_ID: "fixed_location",
        STACKS_PLACE_ID: "fixed_location",
        REMEMBRANCE_PLACE_ID: "fixed_location",
        NEUTRAL_PLACE_ID: "fixed_location",
    }
    semantic_location_classes = {
        ROOTS_PLACE_ID: frozenset({"subterranean", "transit"}),
        GLOW_PLACE_ID: frozenset({"commerce", "meeting", "place_open", "urban_dense"}),
        STACKS_PLACE_ID: frozenset({"craft", "place_restricted", "production"}),
        REMEMBRANCE_PLACE_ID: frozenset({"sacred", "tomb"}),
        NEUTRAL_PLACE_ID: frozenset({"meeting", "place_open"}),
    }
    return {
        "hunted": WorldState(
            tags={ACTOR_ID: frozenset({"seeking_identity"})},
            pair_tags={
                (ACTOR_ID, TARGET_ID): frozenset({"contact:lodging"}),
                (TARGET_ID, ACTOR_ID): frozenset({"hunting"}),
            },
            locations=common_locations,
            recent_events=(
                EventRecord(
                    event_type="compliance_alert",
                    tick=98,
                    target_entity_id=ACTOR_ID,
                ),
            ),
            time_of_day="night",
            weather="rain",
            current_tick=100,
            location_class=legacy_location_class,
            location_classes=semantic_location_classes,
        ),
        "fragment": WorldState(
            tags={ACTOR_ID: frozenset({"seeking_identity", "ghostprint_active"})},
            pair_tags={(ACTOR_ID, TARGET_ID): frozenset({"contact:social"})},
            locations=common_locations,
            location_class=legacy_location_class,
            location_classes=semantic_location_classes,
            time_of_day="evening",
            weather="rain",
            current_tick=100,
        ),
        "debt": WorldState(
            tags={ACTOR_ID: frozenset({"seeking_identity"})},
            ephemeral_tags={ACTOR_ID: frozenset({"debt_pulse_active"})},
            pair_tags={(ACTOR_ID, TARGET_ID): frozenset({"contact:social"})},
            locations={ACTOR_ID: STACKS_PLACE_ID},
            location_class=legacy_location_class,
            location_classes=semantic_location_classes,
            recent_events=(
                EventRecord(
                    event_type="encoded_message",
                    tick=99,
                    target_entity_id=ACTOR_ID,
                ),
            ),
            time_of_day="midday",
            weather="clear",
            current_tick=100,
        ),
        "quiet": WorldState(
            tags={ACTOR_ID: frozenset({"seeking_identity"})},
            locations={ACTOR_ID: GLOW_PLACE_ID},
            location_class=legacy_location_class,
            location_classes=semantic_location_classes,
            time_of_day="midday",
            weather="clear",
            current_tick=100,
        ),
        "hiding": WorldState(
            tags={ACTOR_ID: frozenset({"off_grid"})},
            locations={ACTOR_ID: ROOTS_PLACE_ID},
            location_class=legacy_location_class,
            location_classes=semantic_location_classes,
            time_of_day="night",
            weather="clear",
            current_tick=100,
        ),
        # Round-2 solo presets
        "mourning": WorldState(
            ephemeral_tags={ACTOR_ID: frozenset({"grieving"})},
            locations={ACTOR_ID: REMEMBRANCE_PLACE_ID},
            location_class=legacy_location_class,
            location_classes=semantic_location_classes,
            time_of_day="evening",
            weather="clear",
            current_tick=100,
        ),
        "craft_soldier": WorldState(
            tags={ACTOR_ID: frozenset({"soldier"})},
            locations={ACTOR_ID: STACKS_PLACE_ID},
            location_class=legacy_location_class,
            location_classes=semantic_location_classes,
            time_of_day="evening",
            weather="clear",
            current_tick=100,
        ),
    }


def build_multi_slot_presets() -> Dict[str, dict]:
    """Multi-slot demo states for the package-library expansion templates.

    Each entry carries both a WorldState and an explicit (ACTOR, TARGET)
    binding, matching how the multi-slot binding composer would yield pairs
    against real database state.
    """

    legacy_location_class = {
        ROOTS_PLACE_ID: "fixed_location",
        GLOW_PLACE_ID: "fixed_location",
        STACKS_PLACE_ID: "fixed_location",
        REMEMBRANCE_PLACE_ID: "fixed_location",
        NEUTRAL_PLACE_ID: "fixed_location",
    }
    semantic_location_classes = {
        ROOTS_PLACE_ID: frozenset({"subterranean", "transit"}),
        GLOW_PLACE_ID: frozenset({"commerce", "meeting", "place_open", "urban_dense"}),
        STACKS_PLACE_ID: frozenset({"craft", "place_restricted", "production"}),
        REMEMBRANCE_PLACE_ID: frozenset({"sacred", "tomb"}),
        NEUTRAL_PLACE_ID: frozenset({"meeting", "place_open"}),
    }
    return {
        "vengeance": {
            "state": WorldState(
                tags={ACTOR_ID: frozenset({"vendetta_holder"})},
                ephemeral_tags={ACTOR_ID: frozenset({"grudge_active"})},
                relationship_types={(ACTOR_ID, TARGET_ID): frozenset({"enemy"})},
                locations={ACTOR_ID: ROOTS_PLACE_ID, TARGET_ID: ROOTS_PLACE_ID},
                location_class=legacy_location_class,
                location_classes=semantic_location_classes,
                time_of_day="night",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
        "kin_danger": {
            "state": WorldState(
                pair_tags={(3, TARGET_ID): frozenset({"hunting"})},
                relationship_types={(ACTOR_ID, TARGET_ID): frozenset({"family"})},
                locations={ACTOR_ID: GLOW_PLACE_ID, TARGET_ID: GLOW_PLACE_ID},
                location_class=legacy_location_class,
                location_classes=semantic_location_classes,
                time_of_day="evening",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
        "informant": {
            "state": WorldState(
                tags={ACTOR_ID: frozenset({"informant_handler"})},
                relationship_types={(ACTOR_ID, TARGET_ID): frozenset({"handler"})},
                locations={ACTOR_ID: GLOW_PLACE_ID, TARGET_ID: GLOW_PLACE_ID},
                location_class=legacy_location_class,
                location_classes=semantic_location_classes,
                time_of_day="evening",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
        "surveillance": {
            "state": WorldState(
                tags={ACTOR_ID: frozenset({"signal_operator"})},
                locations={ACTOR_ID: GLOW_PLACE_ID, TARGET_ID: ROOTS_PLACE_ID},
                location_class=legacy_location_class,
                location_classes=semantic_location_classes,
                time_of_day="night",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
        # Round-2 multi-slot presets
        "wounded_healing": {
            "state": WorldState(
                tags={ACTOR_ID: frozenset({"magical_healing"})},
                ephemeral_tags={TARGET_ID: frozenset({"wounded"})},
                locations={ACTOR_ID: STACKS_PLACE_ID, TARGET_ID: STACKS_PLACE_ID},
                location_class=legacy_location_class,
                location_classes=semantic_location_classes,
                time_of_day="evening",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
        "vigil_devout": {
            "state": WorldState(
                tags={ACTOR_ID: frozenset({"devout"})},
                ephemeral_tags={TARGET_ID: frozenset({"dying"})},
                relationship_types={(ACTOR_ID, TARGET_ID): frozenset({"family"})},
                locations={ACTOR_ID: STACKS_PLACE_ID, TARGET_ID: STACKS_PLACE_ID},
                location_class=legacy_location_class,
                location_classes=semantic_location_classes,
                time_of_day="night",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
        "warning": {
            "state": WorldState(
                relationship_types={(ACTOR_ID, TARGET_ID): frozenset({"ally"})},
                locations={ACTOR_ID: GLOW_PLACE_ID, TARGET_ID: GLOW_PLACE_ID},
                location_class=legacy_location_class,
                location_classes=semantic_location_classes,
                recent_events=(
                    EventRecord(
                        event_type="threat_issued",
                        tick=99,
                        target_entity_id=TARGET_ID,
                    ),
                ),
                time_of_day="evening",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
        "welfare_check": {
            "state": WorldState(
                relationship_types={(ACTOR_ID, TARGET_ID): frozenset({"mentor"})},
                locations={ACTOR_ID: GLOW_PLACE_ID, TARGET_ID: GLOW_PLACE_ID},
                location_class=legacy_location_class,
                location_classes=semantic_location_classes,
                time_of_day="afternoon",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
        "kin_visit": {
            "state": WorldState(
                relationship_types={(ACTOR_ID, TARGET_ID): frozenset({"family"})},
                trust={(ACTOR_ID, TARGET_ID): 3, (TARGET_ID, ACTOR_ID): 2},
                locations={ACTOR_ID: GLOW_PLACE_ID, TARGET_ID: GLOW_PLACE_ID},
                location_class=legacy_location_class,
                location_classes=semantic_location_classes,
                time_of_day="afternoon",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
        "rival_truce": {
            "state": WorldState(
                relationship_types={(ACTOR_ID, TARGET_ID): frozenset({"rival"})},
                locations={ACTOR_ID: NEUTRAL_PLACE_ID, TARGET_ID: NEUTRAL_PLACE_ID},
                location_class=legacy_location_class,
                location_classes=semantic_location_classes,
                recent_events=(
                    EventRecord(
                        event_type="compliance_alert",
                        tick=95,
                    ),
                ),
                time_of_day="evening",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
    }


def run_preset(name: str) -> dict:
    """Evaluate the built-in template stack against one preset."""

    actor_only_presets = build_presets()
    multi_slot_presets = build_multi_slot_presets()
    validate_always_fallbacks(BUILTIN_TEMPLATES)

    if name in actor_only_presets:
        state = actor_only_presets[name]
        bindings: Bindings = {Slot.ACTOR: ACTOR_ID}
    elif name in multi_slot_presets:
        preset = multi_slot_presets[name]
        state = preset["state"]
        bindings = preset["bindings"]
    else:
        raise ValueError(f"Unknown Orrery demo preset: {name}")

    result = evaluate_stack(BUILTIN_TEMPLATES, state, bindings)
    if result is None:
        return {"preset": name, "fired": False}
    return {
        "preset": name,
        "fired": True,
        "template_id": result.template_id,
        "branch_label": result.branch_label,
        "state_delta": dict(result.state_delta),
        "event_type": result.event_type,
        "magnitude": result.magnitude,
    }


def _all_preset_names() -> list[str]:
    """All known preset names across actor-only and multi-slot harnesses."""

    return sorted(set(build_presets()) | set(build_multi_slot_presets()))


def main() -> None:
    """Run the offline Orrery package harness."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        choices=_all_preset_names(),
        default="hunted",
        help="Demo preset to evaluate",
    )
    args = parser.parse_args()
    print(json.dumps(run_preset(args.preset), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
