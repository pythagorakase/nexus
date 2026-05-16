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


def build_presets() -> Dict[str, WorldState]:
    """Return deterministic demo states that mirror the original JSX simulator."""

    common_locations = {
        ACTOR_ID: ROOTS_PLACE_ID,
        2: ROOTS_PLACE_ID,
        3: GLOW_PLACE_ID,
    }
    location_classes = {
        ROOTS_PLACE_ID: "the_roots",
        GLOW_PLACE_ID: "the_glow",
        STACKS_PLACE_ID: "the_stacks",
    }
    return {
        "hunted": WorldState(
            tags={ACTOR_ID: frozenset({"seeking_identity", "contacts_available"})},
            ephemeral_tags={ACTOR_ID: frozenset({"under_active_pursuit"})},
            locations=common_locations,
            location_class=location_classes,
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
        ),
        "fragment": WorldState(
            tags={
                ACTOR_ID: frozenset(
                    {"seeking_identity", "contacts_available", "ghostprint_active"}
                )
            },
            locations=common_locations,
            location_class=location_classes,
            time_of_day="evening",
            weather="rain",
            current_tick=100,
        ),
        "debt": WorldState(
            tags={ACTOR_ID: frozenset({"seeking_identity", "contacts_available"})},
            ephemeral_tags={ACTOR_ID: frozenset({"debt_pulse_active"})},
            locations={ACTOR_ID: STACKS_PLACE_ID},
            location_class=location_classes,
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
            location_class=location_classes,
            time_of_day="midday",
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

    location_classes = {
        ROOTS_PLACE_ID: "the_roots",
        GLOW_PLACE_ID: "the_glow",
        STACKS_PLACE_ID: "the_stacks",
    }
    return {
        "vengeance": {
            "state": WorldState(
                tags={ACTOR_ID: frozenset({"vendetta_holder"})},
                ephemeral_tags={ACTOR_ID: frozenset({"grudge_active"})},
                relationship_types={(ACTOR_ID, TARGET_ID): frozenset({"enemy"})},
                locations={ACTOR_ID: ROOTS_PLACE_ID, TARGET_ID: ROOTS_PLACE_ID},
                location_class=location_classes,
                time_of_day="night",
                weather="clear",
                current_tick=100,
            ),
            "bindings": {Slot.ACTOR: ACTOR_ID, Slot.TARGET: TARGET_ID},
        },
        "kin_danger": {
            "state": WorldState(
                ephemeral_tags={TARGET_ID: frozenset({"under_active_pursuit"})},
                relationship_types={(ACTOR_ID, TARGET_ID): frozenset({"family"})},
                locations={ACTOR_ID: GLOW_PLACE_ID, TARGET_ID: GLOW_PLACE_ID},
                location_class=location_classes,
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
                location_class=location_classes,
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
