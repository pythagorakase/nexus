"""
NEXUS CLI - Simplified command-line interface for story management.

Commands:
    nexus load --slot N         Display current slot state
    nexus continue --slot N     Advance the story (wizard or narrative)
    nexus undo --slot N         Revert the last action
    nexus regenerate --slot N   Regenerate the last storyteller turn
    nexus model --slot N        Get or set the model for a slot
    nexus trait-audit --slot N  Dry-run new-story trait compiler audit
    nexus retrograde-packet --slot N  Build dry-run Retrograde seed packet
    nexus retrograde-seed-candidates  Call Skald for non-mutating seed candidates
    nexus retrograde-expand-seeds  Call Skald for non-mutating R6 expansion
    nexus retrograde-apply-expansion --slot N  Dry-run Retrograde persistence
    nexus faction-audit --slot N  Dry-run legacy faction column migration audit
    nexus faction-manifest --slot N  Build reviewed faction migration manifest
    nexus faction-apply --slot N  Dry-run ready faction manifest operations
    nexus character-manifest --slot N  Build reviewed character tag manifest
    nexus character-apply --slot N  Dry-run ready character manifest operations
    nexus place-manifest --slot N  Build reviewed place tag manifest
    nexus place-apply --slot N  Dry-run ready place manifest operations
    nexus backfill-review-packet --slot N  Summarize manifest review queues

The CLI is slot-centric: only --slot N is required. The backend resolves
all other state (wizard phase, current chunk, thread ID) automatically.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, Mapping, Optional

import requests

logger = logging.getLogger("nexus.cli")

# Default API server URL (narrative API handles wizard + story endpoints)
DEFAULT_API_URL = "http://localhost:8002"
TERMINAL_GENERATION_STATUSES = {
    "complete",
    "completed",
    "provisional",
    "approved",
    "committed",
}
GENERATION_POLL_SECONDS = 240
FACTION_APPLY_SOURCE_KIND_CHOICES = (
    "authored",
    "llm_generated",
    "system",
    "template",
    "skald_inline",
)


def get_api_url() -> str:
    """Get the API server URL from environment or default."""
    import os

    return os.environ.get("NEXUS_API_URL", DEFAULT_API_URL)


def _is_terminal_generation_status(status: Optional[str]) -> bool:
    """Return whether narrative generation has produced a loadable result."""
    return status in TERMINAL_GENERATION_STATUSES


def _get_next_phase(current_phase: str) -> Optional[str]:
    """Get the next wizard phase after the current one."""
    phase_order = ["setting", "character", "seed", "ready"]
    try:
        idx = phase_order.index(current_phase)
        return phase_order[idx + 1] if idx + 1 < len(phase_order) else None
    except ValueError:
        return None


def _truncate_text(text: str, head: int = 10, tail: int = 10) -> str:
    """Truncate text to head + tail lines with indicator."""
    lines = text.split("\n")
    if len(lines) <= head + tail:
        return text
    return "\n".join(
        lines[:head]
        + [f"  [...{len(lines) - head - tail} lines omitted...]"]
        + lines[-tail:]
    )


def _print_value(key: str, value: Any, indent: int = 2, truncate: bool = False) -> None:
    """Print a single key-value pair with proper formatting."""
    prefix = " " * indent

    if value is None:
        return

    if isinstance(value, dict):
        print(f"{prefix}{key}:")
        for k, v in value.items():
            _print_value(k, v, indent + 2, truncate)
    elif isinstance(value, list):
        if not value:
            return
        if all(isinstance(item, str) for item in value):
            # Simple string list - show inline or multiline based on length
            joined = ", ".join(str(v) for v in value)
            if len(joined) < 80:
                print(f"{prefix}{key}: {joined}")
            else:
                print(f"{prefix}{key}:")
                for item in value:
                    print(f"{prefix}  - {item}")
        else:
            # Complex list - show each item
            print(f"{prefix}{key}:")
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    print(f"{prefix}  [{i}]:")
                    for k, v in item.items():
                        _print_value(k, v, indent + 4, truncate)
                else:
                    print(f"{prefix}  - {item}")
    elif isinstance(value, str):
        if "\n" in value or len(value) > 100:
            # Multi-line or long text
            text = _truncate_text(value) if truncate else value
            print(f"{prefix}{key}:")
            for line in text.split("\n"):
                print(f"{prefix}  {line}")
        else:
            print(f"{prefix}{key}: {value}")
    else:
        print(f"{prefix}{key}: {value}")


def _print_artifact(
    artifact_type: str, data: Dict[str, Any], truncate: bool = False
) -> None:
    """Print full artifact data. Use truncate=True for abbreviated output."""
    # Print all fields recursively
    for key, value in data.items():
        if not key.startswith("_"):
            _print_value(key, value, indent=2, truncate=truncate)


def _print_trait_audit(payload: Dict[str, Any]) -> None:
    """Print a dry-run trait compiler audit in a compact CLI format."""

    audit = payload.get("trait_audit") or {}
    counters = audit.get("counters") or {}
    traits = payload.get("traits") or []

    character_name = payload.get("character_name")
    if character_name:
        print(f"Character: {character_name}")
    if traits:
        print(f"Traits: {', '.join(traits)}")

    print()
    print("Counters:")
    for key in (
        "applied_single_entity_tags",
        "applied_pair_tags",
        "created_entities",
        "created_relationships",
        "prose_only_remainders",
    ):
        print(f"  {key}: {counters.get(key, 0)}")

    single_tags = audit.get("applied_single_entity_tags") or []
    if single_tags:
        print()
        print("Applied single-entity tags:")
        for item in single_tags:
            print(
                "  - "
                f"{item['trait']}: {item['category']}:{item['tag']} "
                f"on entity {item['entity_id']}"
            )

    pair_tags = audit.get("applied_pair_tags") or []
    if pair_tags:
        print()
        print("Applied pair tags:")
        for item in pair_tags:
            print(
                "  - "
                f"{item['trait']}: {item['tag']} "
                f"{item['subject_entity_id']} -> {item['object_entity_id']}"
            )

    created_entities = audit.get("created_entities") or []
    if created_entities:
        print()
        print("Created entities:")
        for item in created_entities:
            name = f" ({item['name']})" if item.get("name") else ""
            print(
                "  - "
                f"{item['trait']}: {item['entity_kind']} "
                f"entity {item['entity_id']}{name}"
            )

    created_relationships = audit.get("created_relationships") or []
    if created_relationships:
        print()
        print("Created relationships:")
        for item in created_relationships:
            print(
                "  - "
                f"{item['trait']}: character {item['character1_id']} -> "
                f"{item['character2_id']} "
                f"({item['relationship_type']}, {item['emotional_valence']})"
            )

    remainders = audit.get("prose_only_remainders") or []
    if remainders:
        print()
        print("Prose-only remainders:")
        for item in remainders:
            print(f"  - {item['trait']}: {item['reason_code']}")
            print(f"    {item['message']}")

    if payload.get("failed_policy"):
        print()
        print("Policy: failed because --fail-on-remainders was set.")


def _print_retrograde_packet(payload: Dict[str, Any]) -> None:
    """Print a Retrograde dry-run packet summary."""

    packet = payload.get("retrograde_packet") or {}
    weird = packet.get("weird") or {}
    summary = packet.get("vocabulary_summary") or {}
    scaffolds = packet.get("candidate_scaffolds") or {}
    seed_request = packet.get("seed_generation_request") or {}
    seed_budget = seed_request.get("budget") or {}

    print("Packet:")
    print(f"  schema_version: {packet.get('schema_version')}")
    print(f"  dry_run: {packet.get('dry_run')}")
    print(f"  mutation_policy: {packet.get('mutation_policy', {}).get('writes')}")
    print()
    print("Weird:")
    print(f"  level: {weird.get('level')}")
    print(f"  genre: {weird.get('genre')}")
    print(f"  source: {weird.get('source')}")
    if weird.get("raw") is not None:
        print(f"  raw: {weird.get('raw')}")
    else:
        print(f"  raw_band: {weird.get('raw_min')}..{weird.get('raw_max')}")
    print()
    print("Vocabulary counts:")
    for key in sorted(summary):
        print(f"  {key}: {summary[key]}")
    print()
    print("Scaffold counts:")
    print(f"  core_entities: {len(scaffolds.get('core_entities') or [])}")
    print(f"  named_seed_npcs: {len(scaffolds.get('named_seed_npcs') or [])}")
    print(f"  pressure_axes: {len(scaffolds.get('pressure_axes') or [])}")
    if seed_budget:
        print()
        print("Seed request:")
        print(f"  generate_candidates: {seed_budget.get('generate_candidates')}")
        print(f"  select_target: {seed_budget.get('select_target')}")
        print(f"  deferred_secret_cap: {seed_budget.get('deferred_secret_cap')}")
        print(
            "  response_schema: "
            f"{bool(seed_request.get('candidate_response_schema'))}"
        )
    if packet.get("seed_generation_prompt"):
        print(f"  prompt_chars: {len(packet['seed_generation_prompt'])}")
    if payload.get("packet_output"):
        print()
        print(f"Output: {payload['packet_output']}")


def _print_retrograde_seed_candidates(payload: Dict[str, Any]) -> None:
    """Print a compact Skald seed candidate generation summary."""

    generation = payload.get("seed_candidate_generation") or {}
    response = generation.get("seed_candidate_response") or {}
    candidates = response.get("candidates") or []
    selected_ids = response.get("selected_seed_ids") or []
    rejected_ids = response.get("rejected_seed_ids") or []

    print("Seed candidates:")
    print(f"  model: {generation.get('model')}")
    print(f"  prompt_chars: {generation.get('prompt_chars')}")
    print(f"  candidates: {len(candidates)}")
    print(f"  selected: {len(selected_ids)}")
    print(f"  rejected: {len(rejected_ids)}")
    if selected_ids:
        print(f"  selected_seed_ids: {', '.join(selected_ids)}")
    if payload.get("packet_input"):
        print(f"  packet_input: {payload['packet_input']}")
    if payload.get("candidate_output"):
        print()
        print(f"Output: {payload['candidate_output']}")


def _print_retrograde_expansion(payload: Dict[str, Any]) -> None:
    """Print a compact Retrograde R6 expansion summary."""

    generation = payload.get("retrograde_expansion_generation") or {}
    response = generation.get("retrograde_expansion_plan") or {}
    events = response.get("event_plan") or []
    tags = response.get("entity_tag_plan") or []
    pair_tags = response.get("pair_tag_plan") or []
    relationships = response.get("relationship_plan") or []
    threads = response.get("thread_plan") or []
    readiness = response.get("commit_readiness") or {}

    print("Expansion plan:")
    print(f"  model: {generation.get('model')}")
    print(f"  prompt_chars: {generation.get('prompt_chars')}")
    print(f"  selected_seed_ids: {', '.join(response.get('selected_seed_ids') or [])}")
    print(f"  events: {len(events)}")
    print(f"  entity_tags: {len(tags)}")
    print(f"  pair_tags: {len(pair_tags)}")
    print(f"  relationships: {len(relationships)}")
    print(f"  threads: {len(threads)}")
    print(f"  writes: {readiness.get('writes')}")
    if readiness.get("blocked_by"):
        print(f"  blocked_by: {', '.join(readiness['blocked_by'])}")
    if payload.get("packet_input"):
        print(f"  packet_input: {payload['packet_input']}")
    if payload.get("candidate_input"):
        print(f"  candidate_input: {payload['candidate_input']}")
    if payload.get("expansion_output"):
        print()
        print(f"Output: {payload['expansion_output']}")


def _print_retrograde_persistence(payload: Dict[str, Any]) -> None:
    """Print a compact Retrograde persistence manifest summary."""

    plan = payload.get("retrograde_persistence") or {}
    counters = plan.get("counters") or {}
    blockers = plan.get("execute_blockers") or []
    prologue = plan.get("prologue_anchor") or {}

    print("Persistence plan:")
    print(f"  dry_run: {plan.get('dry_run')}")
    print(f"  source_kind: {plan.get('source_kind')}")
    print(f"  prologue_anchor: {prologue.get('status')}")
    if prologue.get("chunk_id") is not None:
        print(f"  prologue_chunk_id: {prologue.get('chunk_id')}")
    for key in (
        "events_would_insert",
        "events_inserted",
        "events_already_present",
        "events_blocked",
        "entity_tags_would_insert",
        "entity_tags_inserted",
        "entity_tags_already_present",
        "entity_tags_blocked",
        "pair_tags_would_insert",
        "pair_tags_inserted",
        "pair_tags_already_present",
        "pair_tags_blocked",
        "relationships_planned_only",
    ):
        print(f"  {key}: {counters.get(key, 0)}")
    if blockers:
        print()
        print("Execute blockers:")
        for blocker in blockers:
            print(f"  - {blocker.get('id')}: {blocker.get('reason')}")
    if payload.get("persistence_output"):
        print()
        print(f"Output: {payload['persistence_output']}")


def _print_faction_audit(payload: Dict[str, Any]) -> None:
    """Print a dry-run faction table migration audit in a compact CLI format."""

    audit = payload.get("faction_audit") or {}
    counters = audit.get("counters") or {}
    non_null_counts = audit.get("non_null_counts") or {}
    factions = audit.get("factions") or []

    print("Counters:")
    for key in (
        "factions_scanned",
        "factions_with_legacy_values",
        "non_null_legacy_values",
        "candidate_entity_tags",
        "candidate_pair_tags",
        "prose_or_remainder_items",
        "no_replacement_items",
        "manual_review_items",
        "ambiguous_resource_values",
        "active_claim_edges",
        "active_operates_from_edges",
        "legacy_tag_rows",
        "legacy_ideology_axis_tags",
        "legacy_power_posture_tags",
        "legacy_legitimacy_status_tags",
        "legacy_operational_secrecy_tags",
        "legacy_resource_class_tags",
        "legacy_hidden_agenda_class_tags",
        "legacy_history_class_tags",
    ):
        print(f"  {key}: {counters.get(key, 0)}")

    if non_null_counts:
        print()
        print("Legacy column values:")
        for column, count in non_null_counts.items():
            print(f"  {column}: {count}")

    review_factions = [item for item in factions if item.get("review_required")]
    if review_factions:
        print()
        print("Manual review:")
        for item in review_factions[:10]:
            print(
                "  - "
                f"{item['faction_name']} "
                f"(id {item['faction_id']}): "
                f"{item.get('manual_review_items', 0)} item(s)"
            )
        if len(review_factions) > 10:
            print(f"  ...{len(review_factions) - 10} more")


def _print_faction_manifest(payload: Dict[str, Any]) -> None:
    """Print a faction migration manifest summary."""

    manifest = payload.get("faction_manifest") or {}
    counters = manifest.get("counters") or {}
    factions = manifest.get("factions") or []

    print("Manifest:")
    print(f"  schema_version: {manifest.get('schema_version')}")
    print(f"  dry_run: {manifest.get('dry_run')}")

    print()
    print("Counters:")
    printed_counters = set()
    for key in (
        "operation_items",
        "ready_operations",
        "review_required_operations",
        "insert_entity_tag_operations",
        "review_entity_tag_operations",
        "resolve_pair_tag_target_operations",
        "preserve_prose_operations",
        "classify_structured_remainder_operations",
        "drop_legacy_tag_after_review_operations",
    ):
        print(f"  {key}: {counters.get(key, 0)}")
        printed_counters.add(key)
    for key in sorted(key for key in counters if key not in printed_counters):
        print(f"  {key}: {counters[key]}")

    review_factions = [
        item for item in factions if item.get("review_required_operations", 0)
    ]
    if review_factions:
        print()
        print("Manual review:")
        for item in review_factions[:10]:
            print(
                "  - "
                f"{item['faction_name']} "
                f"(id {item['faction_id']}): "
                f"{item.get('review_required_operations', 0)} item(s)"
            )
        if len(review_factions) > 10:
            print(f"  ...{len(review_factions) - 10} more")


def _print_faction_apply(payload: Dict[str, Any]) -> None:
    """Print a faction migration apply summary."""

    apply_result = payload.get("faction_apply") or {}
    counters = apply_result.get("counters") or {}
    operations = apply_result.get("operations") or []

    print("Apply:")
    print(f"  schema_version: {apply_result.get('schema_version')}")
    print(f"  dry_run: {apply_result.get('dry_run')}")
    print(f"  source_kind: {apply_result.get('source_kind')}")

    print()
    print("Counters:")
    printed_counters = set()
    for key in (
        "operation_items",
        "ready_entity_tag_operations",
        "entity_tags_would_insert",
        "entity_tags_inserted",
        "entity_tags_already_present",
        "duplicate_ready_operations_skipped",
        "blocked_existing_sibling_operations",
        "review_required_operations_skipped",
        "non_entity_tag_operations_skipped",
    ):
        print(f"  {key}: {counters.get(key, 0)}")
        printed_counters.add(key)
    for key in sorted(key for key in counters if key not in printed_counters):
        print(f"  {key}: {counters[key]}")

    blocked = [
        item for item in operations if item.get("status") == "blocked_existing_sibling"
    ]
    if blocked:
        print()
        print("Blocked by existing exclusive-category tags:")
        for item in blocked[:10]:
            siblings = ", ".join(item.get("existing_sibling_tags") or [])
            print(
                "  - "
                f"{item.get('faction_name')} "
                f"(id {item.get('faction_id')}): "
                f"{item.get('category')}:{item.get('tag')} conflicts with "
                f"{siblings}"
            )
        if len(blocked) > 10:
            print(f"  ...{len(blocked) - 10} more")


def _print_character_manifest(payload: Dict[str, Any]) -> None:
    """Print a character tag migration manifest summary."""

    manifest = payload.get("character_manifest") or {}
    counters = manifest.get("counters") or {}
    characters = manifest.get("characters") or []

    print("Manifest:")
    print(f"  schema_version: {manifest.get('schema_version')}")
    print(f"  dry_run: {manifest.get('dry_run')}")

    print()
    print("Counters:")
    printed_counters = set()
    for key in (
        "legacy_character_tag_rows",
        "operation_items",
        "review_required_operations",
        "review_entity_tag_operations",
        "resolve_pair_tag_target_operations",
        "structured_remainder_operations",
        "preserve_prose_operations",
        "candidate_renames",
        "missing_target_tag_operations",
    ):
        print(f"  {key}: {counters.get(key, 0)}")
        printed_counters.add(key)
    for key in sorted(key for key in counters if key not in printed_counters):
        print(f"  {key}: {counters[key]}")

    review_characters = [
        item for item in characters if item.get("review_required_operations", 0)
    ]
    if review_characters:
        print()
        print("Manual review:")
        for item in review_characters[:10]:
            print(
                "  - "
                f"{item['character_name']} "
                f"(id {item['character_id']}): "
                f"{item.get('review_required_operations', 0)} item(s)"
            )
        if len(review_characters) > 10:
            print(f"  ...{len(review_characters) - 10} more")


def _print_place_manifest(payload: Dict[str, Any]) -> None:
    """Print a place tag migration manifest summary."""

    manifest = payload.get("place_manifest") or {}
    counters = manifest.get("counters") or {}
    places = manifest.get("places") or []

    print("Manifest:")
    print(f"  schema_version: {manifest.get('schema_version')}")
    print(f"  dry_run: {manifest.get('dry_run')}")

    print()
    print("Counters:")
    printed_counters = set()
    for key in (
        "places_scanned",
        "operation_items",
        "review_required_operations",
        "review_entity_tag_operations",
        "candidate_entity_tags",
        "missing_target_tag_operations",
        "duplicate_candidate_operations",
    ):
        print(f"  {key}: {counters.get(key, 0)}")
        printed_counters.add(key)
    for key in sorted(key for key in counters if key not in printed_counters):
        print(f"  {key}: {counters[key]}")

    review_places = [
        item for item in places if item.get("review_required_operations", 0)
    ]
    if review_places:
        print()
        print("Manual review:")
        for item in review_places[:10]:
            print(
                "  - "
                f"{item['place_name']} "
                f"(id {item['place_id']}): "
                f"{item.get('review_required_operations', 0)} item(s)"
            )
        if len(review_places) > 10:
            print(f"  ...{len(review_places) - 10} more")


def _print_entity_tag_apply(payload: Dict[str, Any], payload_key: str) -> None:
    """Print a reviewed entity-tag manifest apply summary."""

    apply_result = payload.get(payload_key) or {}
    counters = apply_result.get("counters") or {}
    operations = apply_result.get("operations") or []

    print("Apply:")
    print(f"  schema_version: {apply_result.get('schema_version')}")
    print(f"  entity_kind: {apply_result.get('entity_kind')}")
    print(f"  dry_run: {apply_result.get('dry_run')}")
    print(f"  source_kind: {apply_result.get('source_kind')}")

    print()
    print("Counters:")
    printed_counters = set()
    for key in (
        "operation_items",
        "ready_entity_tag_operations",
        "entity_tags_would_insert",
        "entity_tags_inserted",
        "entity_tags_already_present",
        "duplicate_ready_operations_skipped",
        "blocked_existing_sibling_operations",
        "review_required_operations_skipped",
        "non_entity_tag_operations_skipped",
    ):
        print(f"  {key}: {counters.get(key, 0)}")
        printed_counters.add(key)
    for key in sorted(key for key in counters if key not in printed_counters):
        print(f"  {key}: {counters[key]}")

    blocked = [
        item for item in operations if item.get("status") == "blocked_existing_sibling"
    ]
    if blocked:
        print()
        print("Blocked by existing exclusive-category tags:")
        for item in blocked[:10]:
            siblings = ", ".join(item.get("existing_sibling_tags") or [])
            label = item.get("character_name") or item.get("place_name") or "entity"
            print(
                "  - "
                f"{label} "
                f"(entity {item.get('entity_id')}): "
                f"{item.get('category')}:{item.get('tag')} conflicts with "
                f"{siblings}"
            )
        if len(blocked) > 10:
            print(f"  ...{len(blocked) - 10} more")


def _print_backfill_review_packet(payload: Dict[str, Any]) -> None:
    """Print a Slot backfill review packet summary."""

    packet = payload.get("backfill_review_packet") or {}
    counters = packet.get("counters") or {}
    families = packet.get("families") or {}
    print("Review packet:")
    print(f"  schema_version: {packet.get('schema_version')}")
    print(f"  slot: {packet.get('slot')}")
    if payload.get("packet_output"):
        print(f"  output: {payload.get('packet_output')}")

    print()
    print("Counters:")
    for key in (
        "operation_items",
        "ready_operations",
        "review_required_operations",
        "queue:registered_single_entity",
        "queue:missing_target_tag",
        "queue:pair_target_resolution",
        "queue:prose_or_event",
        "queue:structured_remainder",
        "queue:drop_after_review",
        "queue:other_review",
    ):
        print(f"  {key}: {counters.get(key, 0)}")
    if counters.get("queue:other_review", 0):
        print("  warning: other_review rows need manifest/tooling classification")

    print()
    print("Families:")
    for family in ("faction", "character", "place"):
        family_packet = families.get(family) or {}
        family_counters = family_packet.get("counters") or {}
        print(
            "  - "
            f"{family}: {family_counters.get('operation_items', 0)} ops, "
            f"{family_counters.get('ready_operations', 0)} ready, "
            f"{family_counters.get('review_required_operations', 0)} review-required"
        )


def emit_output(payload: Dict[str, Any], as_json: bool, truncate: bool = False) -> None:
    """Emit payload to stdout in JSON or human-readable format."""
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    # Human-readable output
    if payload.get("error"):
        print(f"Error: {payload['error']}")
        return

    # Display message/storyteller text
    message = payload.get("message") or payload.get("storyteller_text")
    if message:
        print(message)
        print()

    if payload.get("trait_audit"):
        _print_trait_audit(payload)
        print()

    if payload.get("retrograde_packet"):
        _print_retrograde_packet(payload)
        print()

    if payload.get("seed_candidate_generation"):
        _print_retrograde_seed_candidates(payload)
        print()

    if payload.get("retrograde_expansion_generation"):
        _print_retrograde_expansion(payload)
        print()

    if payload.get("retrograde_persistence"):
        _print_retrograde_persistence(payload)
        print()

    if payload.get("faction_audit"):
        _print_faction_audit(payload)
        print()

    if payload.get("faction_manifest"):
        _print_faction_manifest(payload)
        print()

    if payload.get("faction_apply"):
        _print_faction_apply(payload)
        print()

    if payload.get("character_manifest"):
        _print_character_manifest(payload)
        print()

    if payload.get("place_manifest"):
        _print_place_manifest(payload)
        print()

    if payload.get("character_apply"):
        _print_entity_tag_apply(payload, "character_apply")
        print()

    if payload.get("place_apply"):
        _print_entity_tag_apply(payload, "place_apply")
        print()

    if payload.get("backfill_review_packet"):
        _print_backfill_review_packet(payload)
        print()

    # Get display elements
    trait_menu = payload.get("trait_menu")
    choices = payload.get("choices", [])
    next_phase_intro = payload.get("next_phase_intro")

    # Display artifact data FIRST if present (what was just confirmed)
    artifact_type = payload.get("artifact_type")
    artifact_data = payload.get("artifact_data")
    if artifact_type and artifact_data:
        print(
            f"=== {artifact_type.replace('submit_', '').replace('_', ' ').title()} ==="
        )
        _print_artifact(artifact_type, artifact_data, truncate=truncate)
        print()

    # THEN display trait menu or choices (what's next)
    if trait_menu:
        # Render interactive trait selection menu
        can_confirm = payload.get("can_confirm", False)
        print("**Select Three Traits**")
        print()
        if can_confirm:
            print("0.  Confirm Current Selection")
            print()
        for trait in trait_menu:
            checkbox = "[X]" if trait["is_selected"] else "[ ]"
            print(f"{trait['id']:2d}. {checkbox} {trait['name'].title()}")
            # Print definition bullets
            for bullet in trait.get("description", []):
                print(f"      • {bullet}")
            # Print rationale if selected and present
            if trait["is_selected"] and trait.get("rationale"):
                print(f"      → {trait['rationale']}")
            print()
    elif choices and not next_phase_intro:
        # Display choices here only if no phase intro (otherwise after intro)
        print("Choices:")
        for idx, choice in enumerate(choices, start=1):
            print(f"  {idx}. {choice}")
        print()

    # Display next phase intro if present (after artifact)
    if next_phase_intro:
        print("---")
        print()
        print(next_phase_intro)
        print()
        # Display choices after the intro message (where they belong contextually)
        if choices:
            print("Choices:")
            for idx, choice in enumerate(choices, start=1):
                print(f"  {idx}. {choice}")
            print()

    # Display phase if in wizard mode
    phase = payload.get("phase")
    if phase:
        print(f"[Wizard Phase: {phase}]")

    # Display chunk ID if in narrative mode
    chunk_id = payload.get("chunk_id") or payload.get("current_chunk_id")
    if chunk_id:
        print(f"[Chunk: {chunk_id}]")


def emit_error(message: str, as_json: bool) -> None:
    """Emit error output to stderr."""
    if as_json:
        print(json.dumps({"error": message}), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)


def run_load(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Display current slot state.

    Calls GET /api/slot/{slot}/state to get the current state.
    If the slot is empty, offers to initialize it.
    """
    url = f"{get_api_url()}/api/slot/{args.slot}/state"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("is_empty"):
            return {
                "success": True,
                "message": (
                    f"Slot {args.slot} is empty. "
                    f"Use 'nexus continue --slot {args.slot}' to initialize."
                ),
                "is_empty": True,
            }

        if data.get("is_wizard_mode"):
            result = {
                "success": True,
                "message": f"Slot {args.slot} is in wizard mode.",
                "phase": data.get("phase"),
                "choices": [],
            }
            # Include trait menu if in traits subphase
            if data.get("trait_menu"):
                result["trait_menu"] = data.get("trait_menu")
                result["can_confirm"] = data.get("can_confirm", False)
                result["subphase"] = data.get("subphase")
            return result

        # Narrative mode
        return {
            "success": True,
            "message": data.get("storyteller_text") or "No narrative text available.",
            "choices": data.get("choices", []),
            "chunk_id": data.get("current_chunk_id"),
            "has_pending": data.get("has_pending"),
        }

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to API server at {get_api_url()}",
        }
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_continue(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Advance the story (wizard or narrative).

    Determines mode from slot state and calls the appropriate unified endpoint:
    - Wizard mode: /api/story/new/chat
    - Narrative mode: /api/narrative/continue
    """
    try:
        # First, get slot state to determine mode
        state_url = f"{get_api_url()}/api/slot/{args.slot}/state"
        state_response = requests.get(state_url, timeout=30)
        state_response.raise_for_status()
        state = state_response.json()

        if state.get("is_empty"):
            # Initialize via setup/start endpoint
            # Use CLI-provided model, slot's configured model, or backend default.
            setup_url = f"{get_api_url()}/api/story/new/setup/start"
            setup_payload = {"slot": args.slot}
            model_to_use = getattr(args, "model", None) or state.get("model")
            if model_to_use:
                setup_payload["model"] = model_to_use
            setup_response = requests.post(setup_url, json=setup_payload, timeout=30)
            if not setup_response.ok:
                return {
                    "success": False,
                    "error": f"Failed to initialize wizard: {setup_response.text}",
                }

            # Use the actual response from the backend
            setup_data = setup_response.json()
            return {
                "success": True,
                "message": setup_data.get("welcome_message")
                or f"Wizard initialized for slot {args.slot}.",
                "choices": setup_data.get("welcome_choices", []),
                "phase": "setting",
            }

        if state.get("is_wizard_mode"):
            # Check if wizard is ready for transition to narrative
            if state.get("phase") == "ready":
                # Call transition endpoint, then bootstrap
                transition_url = f"{get_api_url()}/api/story/new/transition"
                transition_response = requests.post(
                    transition_url, json={"slot": args.slot}, timeout=60
                )
                if not transition_response.ok:
                    return {
                        "success": False,
                        "error": f"Transition failed: {transition_response.text}",
                    }

                # Transition complete - refresh state and continue to narrative
                state_response = requests.get(state_url, timeout=30)
                state = state_response.json()

                if state.get("is_wizard_mode"):
                    return {
                        "success": False,
                        "error": "Transition completed but still in wizard mode",
                    }

                # Continue to narrative mode handling below (don't return here)
            else:
                # Call wizard chat directly
                url = f"{get_api_url()}/api/story/new/chat"
                # Use CLI override or slot's configured model (e.g., TEST mode)
                model_to_use = args.model or state.get("model")

                # Check if we're in trait selection mode
                trait_menu = state.get("trait_menu")

                # Map --accept-fate to --choice 0 when confirmation is available.
                if trait_menu and args.accept_fate and state.get("can_confirm"):
                    args.choice = 0  # Treat as confirm

                if trait_menu and args.choice is not None:
                    if args.dev:
                        return {
                            "success": False,
                            "error": (
                                "Dev mode is not supported for trait selection "
                                "toggles."
                            ),
                        }
                    # Trait toggle/confirm mode: choice 0 = confirm, 1-10 = toggle
                    if args.choice == 0:
                        if not state.get("can_confirm"):
                            return {
                                "success": False,
                                "error": "Cannot confirm: must select exactly 3 traits",
                            }
                    elif not (1 <= args.choice <= 10):
                        return {
                            "success": False,
                            "error": (
                                f"Choice {args.choice} out of range "
                                "(0-10 for trait selection)"
                            ),
                        }

                    payload = {
                        "slot": args.slot,
                        "message": "",
                        "trait_choice": args.choice,
                        # Required for trait toggle handler.
                        "current_phase": "character",
                    }
                    if model_to_use:
                        payload["model"] = model_to_use

                    response = requests.post(url, json=payload, timeout=120)
                    response.raise_for_status()
                    data = response.json()

                    # Check if confirmed traits need a wildcard intro.
                    if data.get("subphase_complete"):
                        next_subphase = data.get("subphase")  # Should be "wildcard"
                        if next_subphase:
                            # Request Skald intro for next subphase
                            intro_payload = {
                                "slot": args.slot,
                                "message": (
                                    "[SYSTEM] Phase character subphase traits "
                                    f"complete. Proceeding to {next_subphase}. "
                                    "Please introduce the next subphase."
                                ),
                                "current_phase": "character",
                            }
                            if model_to_use:
                                intro_payload["model"] = model_to_use

                            intro_response = requests.post(
                                url, json=intro_payload, timeout=120
                            )
                            if intro_response.ok:
                                intro_data = intro_response.json()
                                return {
                                    "success": True,
                                    "message": data.get("message", ""),
                                    "next_phase_intro": intro_data.get("message"),
                                    "choices": intro_data.get("choices", []),
                                    "phase": "character",
                                    "subphase": next_subphase,
                                }

                    # Return for toggles or if the intro request failed.
                    return {
                        "success": True,
                        "message": data.get("message", ""),
                        "phase": data.get("phase"),
                        "subphase": data.get("subphase"),
                        "trait_menu": data.get("trait_menu"),
                        "can_confirm": data.get("can_confirm", False),
                        "subphase_complete": data.get("subphase_complete", False),
                    }

                # Resolve --choice to user text if provided (non-trait mode)
                user_text = args.user_text or ""
                if args.choice is not None and state.get("choices"):
                    choices = state.get("choices", [])
                    if 1 <= args.choice <= len(choices):
                        user_text = choices[args.choice - 1]
                    else:
                        return {
                            "success": False,
                            "error": (
                                f"Choice {args.choice} out of range "
                                f"(1-{len(choices)})"
                            ),
                        }

                payload = {
                    "slot": args.slot,
                    "message": user_text,
                    "accept_fate": args.accept_fate,
                    # thread_id and current_phase resolved by backend
                }
                if args.dev and args.accept_fate:
                    return {
                        "success": False,
                        "error": "Cannot combine --dev with --accept-fate.",
                    }
                if args.dev:
                    payload["dev"] = True
                if model_to_use:
                    payload["model"] = model_to_use

                response = requests.post(url, json=payload, timeout=120)
                response.raise_for_status()
                data = response.json()

                result = {
                    "success": True,
                    "message": data.get("message"),
                    "choices": data.get("choices", []),
                    "phase": data.get("phase"),
                    "artifact_type": data.get("artifact_type"),
                    "artifact_data": data.get("data"),
                    "phase_complete": data.get("phase_complete"),
                    # Trait menu fields (character subphase)
                    "trait_menu": data.get("trait_menu"),
                    "can_confirm": data.get("can_confirm", False),
                    "subphase": data.get("subphase"),
                }

                # Auto-transition: if phase completed, trigger next phase intro
                if data.get("phase_complete"):
                    current_phase = data.get("phase")
                    next_phase = _get_next_phase(current_phase)

                    if next_phase and next_phase != "ready":
                        # Send transition message to get next phase intro
                        transition_payload = {
                            "slot": args.slot,
                            "message": (
                                f"[SYSTEM] Phase {current_phase} complete. "
                                f"Proceeding to {next_phase}. "
                                "Please introduce the next phase."
                            ),
                            "current_phase": next_phase,
                        }
                        if model_to_use:
                            transition_payload["model"] = model_to_use

                        intro_response = requests.post(
                            url, json=transition_payload, timeout=120
                        )
                        if intro_response.ok:
                            intro_data = intro_response.json()
                            # Append intro to result, preserving the artifact.
                            result["next_phase_intro"] = intro_data.get("message")
                            result["choices"] = intro_data.get("choices", [])
                            result["phase"] = intro_data.get("phase") or next_phase

                    elif next_phase == "ready":
                        # Seed phase complete → transition to narrative mode
                        transition_url = f"{get_api_url()}/api/story/new/transition"
                        transition_response = requests.post(
                            transition_url, json={"slot": args.slot}, timeout=60
                        )
                        if transition_response.ok:
                            # Bootstrap narrative by calling continue endpoint
                            continue_url = f"{get_api_url()}/api/narrative/continue"
                            continue_payload = {"slot": args.slot, "user_text": ""}
                            if model_to_use:
                                continue_payload["model"] = model_to_use
                            narrative_response = requests.post(
                                continue_url, json=continue_payload, timeout=120
                            )
                            if narrative_response.ok:
                                narrative_data = narrative_response.json()
                                result["narrative_bootstrap"] = True
                                result["next_phase_intro"] = narrative_data.get(
                                    "storyteller_text"
                                )
                                result["choices"] = narrative_data.get("choices", [])
                                result["chunk_id"] = narrative_data.get("chunk_id")
                                result["phase"] = None  # Clear wizard phase

                return result

        # Narrative mode - call continue directly
        # (Also reached after wizard transition above)
        if not state.get("is_wizard_mode"):
            # Narrative mode - call continue directly
            model_to_use = args.model or state.get("model")
            user_text = args.user_text or ""

            url = f"{get_api_url()}/api/narrative/continue"
            payload = {
                "slot": args.slot,
                "user_text": user_text,
                "choice": args.choice,
                "accept_fate": args.accept_fate,
                # chunk_id resolved by backend
            }
            if model_to_use:
                payload["model"] = model_to_use

            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()

            # Wait for generation to complete and fetch result
            session_id = data.get("session_id")
            if session_id:
                # Poll for completion; websocket is intentionally not used here.
                for _ in range(GENERATION_POLL_SECONDS):
                    status_url = f"{get_api_url()}/api/narrative/status/{session_id}"
                    status_response = requests.get(
                        status_url, params={"slot": args.slot}, timeout=30
                    )
                    if status_response.ok:
                        status = status_response.json()
                        if _is_terminal_generation_status(status.get("status")):
                            # Fetch incubator for result
                            load_result = run_load(args)
                            return {
                                "success": True,
                                "message": load_result.get("message"),
                                "choices": load_result.get("choices", []),
                                "chunk_id": status.get("chunk_id"),
                            }
                        elif status.get("status") == "error":
                            return {
                                "success": False,
                                "error": status.get("error", "Generation failed"),
                            }
                    time.sleep(1)
                return {"success": False, "error": "Generation timed out"}

            return {
                "success": True,
                "message": data.get("message"),
                "session_id": session_id,
            }

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to API server at {get_api_url()}",
        }
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_undo(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Undo the last action.

    Calls POST /api/slot/{slot}/undo.
    """
    url = f"{get_api_url()}/api/slot/{args.slot}/undo"

    try:
        response = requests.post(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        success = data.get("success", True)
        message = data.get("message")
        if not success:
            # Surface the API's reason via "error" so main() prints something
            # informative instead of the generic "Unknown error" fallback.
            return {"success": False, "error": message or "Undo failed"}
        return {"success": True, "message": message}

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to API server at {get_api_url()}",
        }
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_regenerate(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Regenerate the last storyteller turn for a slot.

    Calls POST /api/narrative/regenerate, then polls /api/narrative/status
    until generation completes, matching run_continue's pattern.
    """
    url = f"{get_api_url()}/api/narrative/regenerate"
    payload: Dict[str, Any] = {"slot": args.slot}
    if args.note:
        payload["note"] = args.note

    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()

        session_id = data.get("session_id")
        if not session_id:
            return {"success": False, "error": "No session ID returned from regenerate"}

        for _ in range(GENERATION_POLL_SECONDS):
            status_url = f"{get_api_url()}/api/narrative/status/{session_id}"
            try:
                status_response = requests.get(
                    status_url, params={"slot": args.slot}, timeout=30
                )
            except requests.exceptions.RequestException:
                # Transient hang on a single status GET (event loop briefly slammed
                # by sync work in generate_narrative_async). Sleep and retry rather
                # than aborting the whole polling loop.
                time.sleep(1)
                continue
            if status_response.ok:
                status = status_response.json()
                if _is_terminal_generation_status(status.get("status")):
                    load_result = run_load(args)
                    return {
                        "success": True,
                        "message": load_result.get("message"),
                        "choices": load_result.get("choices", []),
                        "chunk_id": status.get("chunk_id"),
                    }
                elif status.get("status") == "error":
                    return {
                        "success": False,
                        "error": status.get("error", "Regeneration failed"),
                    }
            time.sleep(1)
        return {"success": False, "error": "Regeneration timed out"}

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to API server at {get_api_url()}",
        }
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_model(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Get or set the model for a slot.

    Calls GET or POST /api/slot/{slot}/model.
    """
    try:
        if args.list:
            # List available models from config (no slot required)
            from nexus.config import get_available_api_models

            models = get_available_api_models()
            return {
                "success": True,
                "message": f"Available models: {', '.join(models)}",
                "available_models": models,
            }

        # Slot is required for get/set operations
        base_url = f"{get_api_url()}/api/slot/{args.slot}/model"

        if args.set:
            # Set the model
            response = requests.post(base_url, json={"model": args.set}, timeout=30)
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "message": f"Model changed to {data.get('model')}",
                "model": data.get("model"),
            }

        # Get current model
        response = requests.get(base_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        current = data.get("model") or "(default)"
        available = data.get("available_models", [])
        return {
            "success": True,
            "message": f"Current model: {current}\nAvailable: {', '.join(available)}",
            "model": data.get("model"),
            "available_models": available,
        }

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to API server at {get_api_url()}",
        }
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_clear(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Clear a slot (reset wizard state).

    Calls POST /api/story/new/setup/reset.
    """
    try:
        url = f"{get_api_url()}/api/story/new/setup/reset"
        response = requests.post(url, json={"slot": args.slot}, timeout=30)
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Slot {args.slot} cleared",
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to API server at {get_api_url()}",
        }
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _load_trait_inputs(raw_value: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse optional trait compiler input overrides from a JSON string."""

    if not raw_value:
        return None
    value = json.loads(raw_value)
    if not isinstance(value, dict):
        raise ValueError("--trait-inputs must be a JSON object")
    return value


def run_trait_audit(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Dry-run the trait compiler against the current new-story wizard cache.

    This command is intentionally opt-in: normal wizard and React UI flows keep
    minimizing confirmation screens, while test loops can inspect the mechanical
    fallout before bootstrap.
    """

    try:
        trait_inputs_payload = _load_trait_inputs(args.trait_inputs)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid --trait-inputs JSON: {e}"}
    except ValueError as e:
        return {"success": False, "error": str(e)}

    from nexus.api.db_pool import get_connection
    from nexus.api.new_story_cache import read_cache
    from nexus.api.new_story_schemas import CharacterCreationState
    from nexus.api.slot_utils import slot_dbname
    from nexus.api.trait_compiler import compile_character_traits
    from nexus.api.trait_compiler_schemas import TraitCompileInputs

    dbname = slot_dbname(args.slot)
    cache = read_cache(dbname)
    if cache is None:
        return {
            "success": False,
            "error": f"Slot {args.slot} has no new-story wizard cache.",
        }

    character_draft = cache.get_character_dict()
    if character_draft is None:
        return {
            "success": False,
            "error": (
                f"Slot {args.slot} does not have a complete character draft "
                "to audit."
            ),
        }

    trait_inputs = (
        TraitCompileInputs.model_validate(trait_inputs_payload)
        if trait_inputs_payload is not None
        else None
    )
    character_state = CharacterCreationState.model_validate(character_draft)
    character = character_state.to_character_sheet()

    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            result = compile_character_traits(
                cur,
                character=character,
                character_id=args.character_id,
                character_entity_id=args.character_entity_id,
                trait_compile_inputs=trait_inputs,
                dry_run=True,
            )

    audit = result.model_dump(mode="json")
    remainder_count = audit["counters"]["prose_only_remainders"]
    failed_policy = bool(args.fail_on_remainders and remainder_count)
    return {
        "success": True,
        "message": f"Trait compiler audit for slot {args.slot} (dry run).",
        "slot": args.slot,
        "dbname": dbname,
        "character_name": character.name,
        "traits": [trait.name for trait in character.get_trait_entries()],
        "trait_audit": audit,
        "failed_policy": failed_policy,
    }


def run_retrograde_packet(args: argparse.Namespace) -> Dict[str, Any]:
    """Build a non-mutating Retrograde dry-run packet from wizard cache."""

    from nexus.agents.orrery.retrograde_packet import build_retrograde_dry_run_packet
    from nexus.agents.orrery.retrograde_vocabulary import (
        enumerate_seed_eligible_vocabulary,
    )
    from nexus.api.new_story_cache import read_cache
    from nexus.api.slot_utils import slot_dbname
    from nexus.config import load_settings

    dbname = slot_dbname(args.slot)
    cache = read_cache(dbname)
    if cache is None:
        return {
            "success": False,
            "error": f"Slot {args.slot} has no new-story wizard cache.",
        }

    try:
        packet = build_retrograde_dry_run_packet(
            slot=args.slot,
            dbname=dbname,
            cache=cache,
            vocabulary=enumerate_seed_eligible_vocabulary(dbname=dbname),
            settings=load_settings(),
            weird_level=args.weird,
            weird_raw=args.weird_raw,
        )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    output_path = args.output
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(packet, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    return {
        "success": True,
        "message": f"Retrograde dry-run packet for slot {args.slot}.",
        "slot": args.slot,
        "dbname": dbname,
        "retrograde_packet": packet,
        "packet_output": str(output_path) if output_path is not None else None,
    }


def run_retrograde_seed_candidates(args: argparse.Namespace) -> Dict[str, Any]:
    """Call Skald for non-mutating Retrograde seed candidates."""

    from nexus.agents.orrery.retrograde_seed_candidates import (
        generate_seed_candidates_with_skald,
    )

    packet_input = None
    packet_output = None
    if args.packet is not None:
        try:
            packet = _load_retrograde_packet_file(args.packet)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"success": False, "error": str(exc)}
        packet_input = str(args.packet)
    else:
        packet_result = run_retrograde_packet(
            argparse.Namespace(
                slot=args.slot,
                weird=args.weird,
                weird_raw=args.weird_raw,
                output=args.packet_output,
            )
        )
        if not packet_result.get("success"):
            return packet_result
        packet = packet_result["retrograde_packet"]
        packet_output = packet_result.get("packet_output")

    generation = generate_seed_candidates_with_skald(
        packet=packet,
        model_name=args.model,
        max_tokens=args.max_tokens,
    )

    output_path = args.output
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(generation, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    return {
        "success": True,
        "message": "Retrograde Skald seed candidates generated.",
        "retrograde_packet": packet,
        "packet_input": packet_input,
        "packet_output": packet_output,
        "seed_candidate_generation": generation,
        "candidate_output": str(output_path) if output_path is not None else None,
    }


def run_retrograde_expand_seeds(args: argparse.Namespace) -> Dict[str, Any]:
    """Call Skald for a non-mutating Retrograde R6 expansion plan."""

    from nexus.agents.orrery.retrograde_expansion import (
        generate_expansion_with_skald,
    )

    try:
        packet = _load_retrograde_packet_file(args.packet)
        seed_candidates = _load_seed_candidate_file(args.seed_candidates)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"success": False, "error": str(exc)}

    generation = generate_expansion_with_skald(
        packet=packet,
        seed_candidate_response=seed_candidates,
        model_name=args.model,
        max_tokens=args.max_tokens,
    )

    output_path = args.output
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(generation, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    return {
        "success": True,
        "message": "Retrograde R6 expansion plan generated.",
        "packet_input": str(args.packet),
        "candidate_input": str(args.seed_candidates),
        "retrograde_expansion_generation": generation,
        "expansion_output": str(output_path) if output_path is not None else None,
    }


def run_retrograde_apply_expansion(args: argparse.Namespace) -> Dict[str, Any]:
    """Dry-run or execute a Retrograde R6 expansion persistence plan."""

    from nexus.agents.orrery.retrograde_persistence import (
        build_retrograde_persistence_plan,
    )
    from nexus.api.db_pool import get_connection
    from nexus.api.slot_utils import slot_dbname

    try:
        packet = _load_retrograde_packet_file(args.packet)
        seed_candidates = _load_seed_candidate_file(args.seed_candidates)
        expansion_plan = _load_retrograde_expansion_file(args.expansion)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"success": False, "error": str(exc)}

    dbname = slot_dbname(args.slot)
    dry_run = not args.execute
    try:
        with get_connection(dbname, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                if dry_run:
                    cur.execute("SET TRANSACTION READ ONLY")
                persistence = build_retrograde_persistence_plan(
                    cur,
                    packet=packet,
                    seed_candidate_response=seed_candidates,
                    expansion_plan_payload=expansion_plan,
                    slot=args.slot,
                    dbname=dbname,
                    dry_run=dry_run,
                )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    output_path = args.output
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(persistence, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    mode = "dry run" if dry_run else "executed"
    return {
        "success": True,
        "message": f"Retrograde persistence plan for slot {args.slot} ({mode}).",
        "slot": args.slot,
        "dbname": dbname,
        "packet_input": str(args.packet),
        "candidate_input": str(args.seed_candidates),
        "expansion_input": str(args.expansion),
        "retrograde_persistence": persistence,
        "persistence_output": str(output_path) if output_path is not None else None,
    }


def _load_retrograde_packet_file(path: Path) -> Dict[str, Any]:
    """Load a raw packet or CLI envelope containing a Retrograde packet."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    packet = payload.get("retrograde_packet") or payload
    if not isinstance(packet, dict):
        raise ValueError(f"{path} does not contain a Retrograde packet object")
    if "seed_generation_request" not in packet:
        raise ValueError(f"{path} is missing seed_generation_request")
    return packet


def _load_seed_candidate_file(path: Path) -> Dict[str, Any]:
    """Load a raw seed-candidate response or CLI generation envelope."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    response = payload.get("seed_candidate_response") or payload
    if not isinstance(response, dict):
        raise ValueError(f"{path} does not contain a seed candidate object")
    if "candidates" not in response or "selected_seed_ids" not in response:
        raise ValueError(f"{path} is missing seed candidate response fields")
    return response


def _load_retrograde_expansion_file(path: Path) -> Dict[str, Any]:
    """Load a raw R6 expansion plan or CLI generation envelope."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    generation = payload.get("retrograde_expansion_generation")
    if isinstance(generation, dict):
        response = generation.get("retrograde_expansion_plan")
    else:
        response = payload.get("retrograde_expansion_plan") or payload
    if not isinstance(response, dict):
        raise ValueError(f"{path} does not contain a Retrograde expansion object")
    if "event_plan" not in response or "thread_plan" not in response:
        raise ValueError(f"{path} is missing Retrograde expansion response fields")
    return response


def run_faction_audit(args: argparse.Namespace) -> Dict[str, Any]:
    """Dry-run the legacy faction table to Orrery substrate migration."""

    from nexus.api.db_pool import get_connection
    from nexus.api.faction_table_audit import build_faction_table_audit
    from nexus.api.slot_utils import slot_dbname

    dbname = slot_dbname(args.slot)
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            audit = build_faction_table_audit(cur)

    return {
        "success": True,
        "message": f"Faction table audit for slot {args.slot} (dry run).",
        "slot": args.slot,
        "dbname": dbname,
        "faction_audit": audit,
    }


def run_faction_manifest(args: argparse.Namespace) -> Dict[str, Any]:
    """Build a read-only faction migration manifest from the audit output."""

    from nexus.api.db_pool import get_connection
    from nexus.api.faction_table_audit import (
        build_faction_migration_manifest,
        build_faction_table_audit,
    )
    from nexus.api.slot_utils import slot_dbname

    dbname = slot_dbname(args.slot)
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            audit = build_faction_table_audit(cur)

    manifest = build_faction_migration_manifest(
        audit,
        slot=args.slot,
        dbname=dbname,
    )
    output_path = args.output
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return {
        "success": True,
        "message": f"Faction migration manifest for slot {args.slot} (dry run).",
        "slot": args.slot,
        "dbname": dbname,
        "faction_manifest": manifest,
        "manifest_output": str(output_path) if output_path is not None else None,
    }


def run_character_manifest(args: argparse.Namespace) -> Dict[str, Any]:
    """Build a read-only character tag migration manifest."""

    from nexus.api.character_tag_manifest import build_character_migration_manifest
    from nexus.api.db_pool import get_connection
    from nexus.api.slot_utils import slot_dbname

    dbname = slot_dbname(args.slot)
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            manifest = build_character_migration_manifest(
                cur,
                slot=args.slot,
                dbname=dbname,
            )

    output_path = getattr(args, "output", None)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return {
        "success": True,
        "message": f"Character tag migration manifest for slot {args.slot} (dry run).",
        "slot": args.slot,
        "dbname": dbname,
        "character_manifest": manifest,
        "manifest_output": str(output_path) if output_path is not None else None,
    }


def run_place_manifest(args: argparse.Namespace) -> Dict[str, Any]:
    """Build a read-only place tag migration manifest."""

    from nexus.api.db_pool import get_connection
    from nexus.api.place_tag_manifest import build_place_migration_manifest
    from nexus.api.slot_utils import slot_dbname

    dbname = slot_dbname(args.slot)
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            manifest = build_place_migration_manifest(
                cur,
                slot=args.slot,
                dbname=dbname,
            )

    output_path = getattr(args, "output", None)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return {
        "success": True,
        "message": f"Place tag migration manifest for slot {args.slot} (dry run).",
        "slot": args.slot,
        "dbname": dbname,
        "place_manifest": manifest,
        "manifest_output": str(output_path) if output_path is not None else None,
    }


def run_character_apply(args: argparse.Namespace) -> Dict[str, Any]:
    """Dry-run or execute ready character manifest operations."""

    from nexus.api.character_tag_manifest import (
        CHARACTER_MANIFEST_SCHEMA_VERSION,
        EXCLUSIVE_CHARACTER_CATEGORIES,
        TARGET_CHARACTER_CATEGORIES,
        build_character_migration_manifest,
    )
    from nexus.api.db_pool import get_connection
    from nexus.api.entity_tag_manifest_apply import apply_entity_tag_manifest
    from nexus.api.slot_utils import slot_dbname

    manifest = _load_optional_entity_manifest(
        args,
        payload_key="character_manifest",
        manifest_label="Character",
    )
    if manifest.get("success") is False:
        return manifest

    dbname = slot_dbname(args.slot)
    dry_run = not args.execute
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            if dry_run:
                cur.execute("SET TRANSACTION READ ONLY")
            raw_manifest = manifest.get("manifest")
            if raw_manifest is None:
                raw_manifest = build_character_migration_manifest(
                    cur,
                    slot=args.slot,
                    dbname=dbname,
                )
            apply_result = apply_entity_tag_manifest(
                cur,
                raw_manifest,
                manifest_schema_version=CHARACTER_MANIFEST_SCHEMA_VERSION,
                entity_kind="character",
                allowed_categories=sorted(TARGET_CHARACTER_CATEGORIES),
                exclusive_categories=sorted(EXCLUSIVE_CHARACTER_CATEGORIES),
                dry_run=dry_run,
                source_kind=args.source_kind,
            )

    mode = "dry run" if dry_run else "executed"
    return {
        "success": True,
        "message": f"Character tag manifest apply for slot {args.slot} ({mode}).",
        "slot": args.slot,
        "dbname": dbname,
        "character_apply": apply_result,
    }


def run_place_apply(args: argparse.Namespace) -> Dict[str, Any]:
    """Dry-run or execute ready place manifest operations."""

    from nexus.api.db_pool import get_connection
    from nexus.api.entity_tag_manifest_apply import apply_entity_tag_manifest
    from nexus.api.place_tag_manifest import (
        EXCLUSIVE_PLACE_CATEGORIES,
        PLACE_MANIFEST_SCHEMA_VERSION,
        TARGET_PLACE_CATEGORIES,
        build_place_migration_manifest,
    )
    from nexus.api.slot_utils import slot_dbname

    manifest = _load_optional_entity_manifest(
        args,
        payload_key="place_manifest",
        manifest_label="Place",
    )
    if manifest.get("success") is False:
        return manifest

    dbname = slot_dbname(args.slot)
    dry_run = not args.execute
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            if dry_run:
                cur.execute("SET TRANSACTION READ ONLY")
            raw_manifest = manifest.get("manifest")
            if raw_manifest is None:
                raw_manifest = build_place_migration_manifest(
                    cur,
                    slot=args.slot,
                    dbname=dbname,
                )
            apply_result = apply_entity_tag_manifest(
                cur,
                raw_manifest,
                manifest_schema_version=PLACE_MANIFEST_SCHEMA_VERSION,
                entity_kind="place",
                allowed_categories=sorted(TARGET_PLACE_CATEGORIES),
                exclusive_categories=sorted(EXCLUSIVE_PLACE_CATEGORIES),
                dry_run=dry_run,
                source_kind=args.source_kind,
            )

    mode = "dry run" if dry_run else "executed"
    return {
        "success": True,
        "message": f"Place tag manifest apply for slot {args.slot} ({mode}).",
        "slot": args.slot,
        "dbname": dbname,
        "place_apply": apply_result,
    }


def run_faction_apply(args: argparse.Namespace) -> Dict[str, Any]:
    """Dry-run or execute ready faction manifest operations."""

    from nexus.api.db_pool import get_connection
    from nexus.api.faction_table_audit import (
        apply_faction_migration_manifest,
        build_faction_migration_manifest,
        build_faction_table_audit,
    )
    from nexus.api.slot_utils import slot_dbname

    dbname = slot_dbname(args.slot)
    dry_run = not args.execute
    if args.source_kind not in FACTION_APPLY_SOURCE_KIND_CHOICES:
        return {
            "success": False,
            "error": (
                f"--source-kind must be one of "
                f"{', '.join(FACTION_APPLY_SOURCE_KIND_CHOICES)}"
            ),
        }

    manifest_path = getattr(args, "manifest", None)
    if args.execute and manifest_path is None:
        return {
            "success": False,
            "error": (
                "--manifest is required with --execute; first persist a reviewed "
                "manifest with `nexus faction-manifest --slot N --output PATH`."
            ),
        }

    manifest: Mapping[str, Any] | None = None
    if manifest_path is not None:
        manifest = _load_faction_manifest_file(manifest_path)
        manifest_slot = (manifest.get("source") or {}).get("slot")
        manifest_dbname = (manifest.get("source") or {}).get("dbname")
        if manifest_slot is not None and int(manifest_slot) != args.slot:
            return {
                "success": False,
                "error": (
                    f"Manifest slot {manifest_slot} does not match "
                    f"--slot {args.slot}"
                ),
            }
        if manifest_dbname is not None and manifest_dbname != dbname:
            return {
                "success": False,
                "error": (
                    f"Manifest dbname {manifest_dbname!r} does not match "
                    f"slot {args.slot} dbname {dbname!r}"
                ),
            }

    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            if dry_run:
                cur.execute("SET TRANSACTION READ ONLY")
            if manifest is None:
                audit = build_faction_table_audit(cur)
                manifest = build_faction_migration_manifest(
                    audit,
                    slot=args.slot,
                    dbname=dbname,
                )
            apply_result = apply_faction_migration_manifest(
                cur,
                manifest,
                dry_run=dry_run,
                source_kind=args.source_kind,
            )

    mode = "dry run" if dry_run else "executed"
    return {
        "success": True,
        "message": f"Faction migration apply for slot {args.slot} ({mode}).",
        "slot": args.slot,
        "dbname": dbname,
        "faction_apply": apply_result,
    }


def run_backfill_review_packet(args: argparse.Namespace) -> Dict[str, Any]:
    """Build a read-only review packet from Slot backfill manifests."""

    from nexus.api.backfill_review_packet import (
        build_backfill_review_packet,
        render_backfill_review_packet_markdown,
    )
    from nexus.api.character_tag_manifest import CHARACTER_MANIFEST_SCHEMA_VERSION
    from nexus.api.faction_table_audit import FACTION_MANIFEST_SCHEMA_VERSION
    from nexus.api.place_tag_manifest import PLACE_MANIFEST_SCHEMA_VERSION

    manifests = {
        "faction": _load_faction_manifest_file(
            args.faction_manifest,
            expected_schema_version=FACTION_MANIFEST_SCHEMA_VERSION,
        ),
        "character": _load_entity_manifest_file(
            args.character_manifest,
            payload_key="character_manifest",
            expected_schema_version=CHARACTER_MANIFEST_SCHEMA_VERSION,
        ),
        "place": _load_entity_manifest_file(
            args.place_manifest,
            payload_key="place_manifest",
            expected_schema_version=PLACE_MANIFEST_SCHEMA_VERSION,
        ),
    }
    packet = build_backfill_review_packet(
        manifests,
        slot=args.slot,
        examples_per_queue=args.examples_per_queue,
    )
    packet_markdown = render_backfill_review_packet_markdown(packet)

    output_path = getattr(args, "output", None)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(packet_markdown, encoding="utf-8")

    return {
        "success": True,
        "message": f"Backfill review packet for slot {args.slot}.",
        "slot": args.slot,
        "backfill_review_packet": packet,
        "packet_output": str(output_path) if output_path is not None else None,
        "packet_markdown": None if output_path is not None else packet_markdown,
    }


def _load_faction_manifest_file(
    path: Path,
    *,
    expected_schema_version: Optional[str] = None,
) -> Mapping[str, Any]:
    """Load a raw faction manifest or full CLI JSON payload from disk."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Faction manifest file must contain a JSON object")

    _reject_mismatched_manifest_payload(data, expected_key="faction_manifest")
    manifest = data.get("faction_manifest", data)
    if not isinstance(manifest, dict):
        raise ValueError("Faction manifest payload must be a JSON object")
    _validate_manifest_schema(
        manifest,
        expected_schema_version=expected_schema_version,
        manifest_label="Faction",
    )
    return manifest


def _load_entity_manifest_file(
    path: Path,
    *,
    payload_key: str,
    expected_schema_version: Optional[str] = None,
) -> Mapping[str, Any]:
    """Load a raw entity-tag manifest or full CLI JSON payload from disk."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Entity-tag manifest file must contain a JSON object")

    _reject_mismatched_manifest_payload(data, expected_key=payload_key)
    manifest = data.get(payload_key, data)
    if not isinstance(manifest, dict):
        raise ValueError("Entity-tag manifest payload must be a JSON object")
    _validate_manifest_schema(
        manifest,
        expected_schema_version=expected_schema_version,
        manifest_label=payload_key.removesuffix("_manifest").title(),
    )
    return manifest


def _reject_mismatched_manifest_payload(
    data: Mapping[str, Any],
    *,
    expected_key: str,
) -> None:
    manifest_keys = sorted(
        key for key in data if key.endswith("_manifest") and key != expected_key
    )
    if manifest_keys and expected_key not in data:
        raise ValueError(
            f"Expected {expected_key} payload; found {', '.join(manifest_keys)}"
        )


def _validate_manifest_schema(
    manifest: Mapping[str, Any],
    *,
    expected_schema_version: Optional[str],
    manifest_label: str,
) -> None:
    if expected_schema_version is None:
        return
    schema_version = manifest.get("schema_version")
    if schema_version != expected_schema_version:
        raise ValueError(
            f"{manifest_label} manifest requires {expected_schema_version}; "
            f"got {schema_version!r}"
        )


def _load_optional_entity_manifest(
    args: argparse.Namespace,
    *,
    payload_key: str,
    manifest_label: str,
) -> Dict[str, Any]:
    """Load and validate an optional reviewed entity manifest."""

    from nexus.api.slot_utils import slot_dbname

    if args.source_kind not in FACTION_APPLY_SOURCE_KIND_CHOICES:
        return {
            "success": False,
            "error": (
                f"--source-kind must be one of "
                f"{', '.join(FACTION_APPLY_SOURCE_KIND_CHOICES)}"
            ),
        }

    manifest_path = getattr(args, "manifest", None)
    if args.execute and manifest_path is None:
        return {
            "success": False,
            "error": (
                f"--manifest is required with --execute; first persist a reviewed "
                f"manifest with `nexus {manifest_label.lower()}-manifest "
                "--slot N --output PATH`."
            ),
        }

    if manifest_path is None:
        return {"success": True, "manifest": None}

    manifest = _load_entity_manifest_file(manifest_path, payload_key=payload_key)
    manifest_slot = (manifest.get("source") or {}).get("slot")
    dbname = slot_dbname(args.slot)
    manifest_dbname = (manifest.get("source") or {}).get("dbname")
    if manifest_slot is not None and int(manifest_slot) != args.slot:
        return {
            "success": False,
            "error": (
                f"Manifest slot {manifest_slot} does not match --slot {args.slot}"
            ),
        }
    if manifest_dbname is not None and manifest_dbname != dbname:
        return {
            "success": False,
            "error": (
                f"Manifest dbname {manifest_dbname!r} does not match "
                f"slot {args.slot} dbname {dbname!r}"
            ),
        }
    return {"success": True, "manifest": manifest}


def run_lock(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Lock a slot to prevent modifications.

    Calls POST /api/slot/{slot}/lock.
    """
    try:
        url = f"{get_api_url()}/api/slot/{args.slot}/lock"
        response = requests.post(url, timeout=30)
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Slot {args.slot} locked",
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to API server at {get_api_url()}",
        }
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_unlock(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Unlock a slot to allow modifications.

    Calls POST /api/slot/{slot}/unlock.
    """
    try:
        url = f"{get_api_url()}/api/slot/{args.slot}/unlock"
        response = requests.post(url, timeout=30)
        response.raise_for_status()
        return {
            "success": True,
            "message": f"Slot {args.slot} unlocked",
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": f"Cannot connect to API server at {get_api_url()}",
        }
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"API error: {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description="NEXUS CLI - Story management command-line interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nexus load --slot 5           Show current state of slot 5
  nexus continue --slot 5       Advance the story
  nexus continue --slot 5 --choice 1   Select choice #1
  nexus continue --slot 5 --user-text "I approach carefully"
  nexus continue --slot 5 --accept-fate   Auto-advance
  nexus undo --slot 5           Revert last action
  nexus model --slot 5          Show current model
  nexus model --slot 5 --set TEST   Change to TEST model
  nexus model --list            List available models
  nexus clear --slot 5          Clear slot (reset wizard state)
  nexus lock --slot 1           Lock slot to prevent modifications
  nexus unlock --slot 2         Unlock slot to allow modifications
  nexus trait-audit --slot 5    Dry-run trait compiler audit
  nexus retrograde-packet --slot 5 --output packet.json
  nexus retrograde-seed-candidates --packet packet.json --output seeds.json
  nexus retrograde-expand-seeds --packet packet.json --seed-candidates seeds.json
  nexus retrograde-apply-expansion --slot 5 --packet packet.json ...
  nexus faction-audit --slot 2  Dry-run faction column migration audit
  nexus faction-manifest --slot 2  Build faction migration manifest
  nexus faction-apply --slot 2  Dry-run ready faction manifest operations
  nexus faction-apply --slot 2 --manifest manifest.json --execute
  nexus character-manifest --slot 2  Build character tag manifest
  nexus character-apply --slot 2  Dry-run ready character manifest operations
  nexus place-manifest --slot 2  Build place tag manifest
  nexus place-apply --slot 2  Dry-run ready place manifest operations
  nexus backfill-review-packet --slot 2 --faction-manifest faction.json ...
        """,
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate long text fields (head 10 + tail 10 lines)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # load command
    load_parser = subparsers.add_parser("load", help="Display current slot state")
    load_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )

    # continue command
    continue_parser = subparsers.add_parser("continue", help="Advance the story")
    continue_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    continue_parser.add_argument(
        "--choice",
        type=int,
        help="Select structured choice by number (1-indexed)",
    )
    continue_parser.add_argument(
        "--user-text",
        help="Freeform user input",
    )
    continue_parser.add_argument(
        "--accept-fate",
        action="store_true",
        help="Auto-advance (select first choice or trigger auto-generate)",
    )
    continue_parser.add_argument(
        "--dev",
        action="store_true",
        help="Request a freeform response for this turn (wizard only)",
    )
    continue_parser.add_argument(
        "--model",
        help=(
            "Override model for this request "
            "(use a registry ID; see /api/config/models)"
        ),
    )

    # undo command
    undo_parser = subparsers.add_parser("undo", help="Revert last action")
    undo_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )

    # regenerate command
    regenerate_parser = subparsers.add_parser(
        "regenerate", help="Regenerate the last storyteller turn"
    )
    regenerate_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    regenerate_parser.add_argument(
        "--note",
        help=(
            "Optional out-of-character note to the storyteller — a soft suggestion "
            "for this regen (e.g., 'darker, plz', 'I want to win the fight despite "
            "my poor choices', 'continuity correction: artifact was found in Vienna')"
        ),
    )

    # model command
    model_parser = subparsers.add_parser("model", help="Get or set model for a slot")
    model_parser.add_argument("--slot", type=int, help="Slot number (1-5)")
    model_parser.add_argument(
        "--set",
        help="Set the model (use a registry ID; run with --list to see options)",
    )
    model_parser.add_argument(
        "--list", action="store_true", help="List available models"
    )

    # clear command
    clear_parser = subparsers.add_parser(
        "clear", help="Clear a slot (reset wizard state)"
    )
    clear_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )

    # trait-audit command
    trait_audit_parser = subparsers.add_parser(
        "trait-audit",
        help="Dry-run the new-story trait compiler against wizard cache",
    )
    trait_audit_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    trait_audit_parser.add_argument(
        "--trait-inputs",
        help=(
            "Optional TraitCompileInputs JSON object for this dry run "
            "(does not mutate wizard cache)"
        ),
    )
    trait_audit_parser.add_argument(
        "--character-id",
        type=int,
        default=0,
        help="Placeholder character id to use in dry-run relationship output",
    )
    trait_audit_parser.add_argument(
        "--character-entity-id",
        type=int,
        default=0,
        help="Placeholder entity id to use in dry-run tag output",
    )
    trait_audit_parser.add_argument(
        "--fail-on-remainders",
        action="store_true",
        help=(
            "Exit with status 1 if any trait falls back to prose-only storage; "
            "JSON callers should check the exit code or failed_policy"
        ),
    )

    # retrograde-packet command
    retrograde_packet_parser = subparsers.add_parser(
        "retrograde-packet",
        help="Build a non-mutating Retrograde seed review packet",
    )
    retrograde_packet_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    retrograde_packet_parser.add_argument(
        "--weird",
        choices=("low", "medium", "high"),
        help="Player-facing Retrograde weirdness level for this packet.",
    )
    retrograde_packet_parser.add_argument(
        "--weird-raw",
        type=float,
        help=(
            "Developer calibration override for raw weirdness. This does not "
            "write to wizard state."
        ),
    )
    retrograde_packet_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the raw Retrograde dry-run packet JSON.",
    )

    # retrograde-seed-candidates command
    retrograde_seed_parser = subparsers.add_parser(
        "retrograde-seed-candidates",
        help="Call Skald for non-mutating Retrograde seed candidates",
    )
    retrograde_seed_source = retrograde_seed_parser.add_mutually_exclusive_group(
        required=True
    )
    retrograde_seed_source.add_argument(
        "--slot",
        type=int,
        help="Slot number (1-5) with an active new-story wizard cache.",
    )
    retrograde_seed_source.add_argument(
        "--packet",
        type=Path,
        help="Existing Retrograde packet JSON from retrograde-packet.",
    )
    retrograde_seed_parser.add_argument(
        "--weird",
        choices=("low", "medium", "high"),
        help="Player-facing Retrograde weirdness level when building from --slot.",
    )
    retrograde_seed_parser.add_argument(
        "--weird-raw",
        type=float,
        help="Developer raw weirdness override when building from --slot.",
    )
    retrograde_seed_parser.add_argument(
        "--packet-output",
        type=Path,
        help="Optional packet JSON path when building from --slot.",
    )
    retrograde_seed_parser.add_argument(
        "--model",
        help="Concrete model id for Skald seed generation; defaults to wizard model.",
    )
    retrograde_seed_parser.add_argument(
        "--max-tokens",
        type=int,
        help="Optional max output tokens for the Skald seed structured response.",
    )
    retrograde_seed_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the Skald seed candidate response JSON.",
    )

    # retrograde-expand-seeds command
    retrograde_expand_parser = subparsers.add_parser(
        "retrograde-expand-seeds",
        help="Call Skald for a non-mutating Retrograde R6 expansion plan",
    )
    retrograde_expand_parser.add_argument(
        "--packet",
        type=Path,
        required=True,
        help="Existing Retrograde packet JSON from retrograde-packet.",
    )
    retrograde_expand_parser.add_argument(
        "--seed-candidates",
        type=Path,
        required=True,
        help="Seed candidate JSON from retrograde-seed-candidates.",
    )
    retrograde_expand_parser.add_argument(
        "--model",
        help="Concrete model id for Skald expansion; defaults to wizard model.",
    )
    retrograde_expand_parser.add_argument(
        "--max-tokens",
        type=int,
        help="Optional max output tokens for the Skald expansion response.",
    )
    retrograde_expand_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the Skald expansion response JSON.",
    )

    # retrograde-apply-expansion command
    retrograde_apply_parser = subparsers.add_parser(
        "retrograde-apply-expansion",
        help="Dry-run or execute a Retrograde R6 expansion persistence plan",
    )
    retrograde_apply_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    retrograde_apply_parser.add_argument(
        "--packet",
        type=Path,
        required=True,
        help="Existing Retrograde packet JSON from retrograde-packet.",
    )
    retrograde_apply_parser.add_argument(
        "--seed-candidates",
        type=Path,
        required=True,
        help="Seed candidate JSON from retrograde-seed-candidates.",
    )
    retrograde_apply_parser.add_argument(
        "--expansion",
        type=Path,
        required=True,
        help="Expansion JSON from retrograde-expand-seeds.",
    )
    retrograde_apply_parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Write canonical Retrograde rows. Without this flag the command "
            "uses a read-only dry run."
        ),
    )
    retrograde_apply_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the raw persistence plan JSON.",
    )

    # faction-audit command
    faction_audit_parser = subparsers.add_parser(
        "faction-audit",
        help="Dry-run legacy faction column migration into Orrery substrate",
    )
    faction_audit_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )

    # faction-manifest command
    faction_manifest_parser = subparsers.add_parser(
        "faction-manifest",
        help="Build read-only faction migration manifest from audit output",
    )
    faction_manifest_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    faction_manifest_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the raw faction migration manifest JSON.",
    )

    # faction-apply command
    faction_apply_parser = subparsers.add_parser(
        "faction-apply",
        help=(
            "Dry-run or execute ready faction manifest operations " "into entity_tags"
        ),
    )
    faction_apply_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    faction_apply_parser.add_argument(
        "--manifest",
        type=Path,
        help=(
            "Reviewed manifest JSON to apply. Required with --execute; "
            "without it, dry-run rebuilds the manifest from the live slot."
        ),
    )
    faction_apply_parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Write ready entity_tags from --manifest. Without this flag the "
            "command uses a read-only dry run."
        ),
    )
    faction_apply_parser.add_argument(
        "--source-kind",
        default="system",
        choices=FACTION_APPLY_SOURCE_KIND_CHOICES,
        help="entity_tag_source_kind stamped on inserted rows when --execute is set.",
    )

    # character-manifest command
    character_manifest_parser = subparsers.add_parser(
        "character-manifest",
        help="Build read-only character tag migration manifest",
    )
    character_manifest_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    character_manifest_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the raw character migration manifest JSON.",
    )

    # character-apply command
    character_apply_parser = subparsers.add_parser(
        "character-apply",
        help="Dry-run or execute ready character manifest operations into entity_tags",
    )
    character_apply_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    character_apply_parser.add_argument(
        "--manifest",
        type=Path,
        help=(
            "Reviewed manifest JSON to apply. Required with --execute; "
            "without it, dry-run rebuilds the manifest from the live slot."
        ),
    )
    character_apply_parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Write ready entity_tags from --manifest. Without this flag the "
            "command uses a read-only dry run."
        ),
    )
    character_apply_parser.add_argument(
        "--source-kind",
        default="system",
        choices=FACTION_APPLY_SOURCE_KIND_CHOICES,
        help="entity_tag_source_kind stamped on inserted rows when --execute is set.",
    )

    # place-manifest command
    place_manifest_parser = subparsers.add_parser(
        "place-manifest",
        help="Build read-only place tag migration manifest",
    )
    place_manifest_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    place_manifest_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the raw place migration manifest JSON.",
    )

    # place-apply command
    place_apply_parser = subparsers.add_parser(
        "place-apply",
        help="Dry-run or execute ready place manifest operations into entity_tags",
    )
    place_apply_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    place_apply_parser.add_argument(
        "--manifest",
        type=Path,
        help=(
            "Reviewed manifest JSON to apply. Required with --execute; "
            "without it, dry-run rebuilds the manifest from the live slot."
        ),
    )
    place_apply_parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Write ready entity_tags from --manifest. Without this flag the "
            "command uses a read-only dry run."
        ),
    )
    place_apply_parser.add_argument(
        "--source-kind",
        default="system",
        choices=FACTION_APPLY_SOURCE_KIND_CHOICES,
        help="entity_tag_source_kind stamped on inserted rows when --execute is set.",
    )

    # backfill-review-packet command
    review_packet_parser = subparsers.add_parser(
        "backfill-review-packet",
        help="Build a read-only review packet from backfill manifests",
    )
    review_packet_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    review_packet_parser.add_argument(
        "--faction-manifest",
        type=Path,
        required=True,
        help="Faction manifest JSON to summarize.",
    )
    review_packet_parser.add_argument(
        "--character-manifest",
        type=Path,
        required=True,
        help="Character manifest JSON to summarize.",
    )
    review_packet_parser.add_argument(
        "--place-manifest",
        type=Path,
        required=True,
        help="Place manifest JSON to summarize.",
    )
    review_packet_parser.add_argument(
        "--output",
        type=Path,
        help="Optional Markdown output path for the review packet.",
    )
    review_packet_parser.add_argument(
        "--examples-per-queue",
        type=int,
        default=5,
        help="Maximum example rows to show per family review queue.",
    )

    # lock command
    lock_parser = subparsers.add_parser(
        "lock", help="Lock a slot to prevent modifications"
    )
    lock_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )

    # unlock command
    unlock_parser = subparsers.add_parser(
        "unlock", help="Unlock a slot to allow modifications"
    )
    unlock_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )

    return parser


def main() -> int:
    """Entry point for the NEXUS CLI."""
    parser = build_parser()
    args = parser.parse_args()

    # Validate slot for commands that require it
    if args.command in (
        "load",
        "continue",
        "undo",
        "regenerate",
        "clear",
        "trait-audit",
        "retrograde-packet",
        "retrograde-apply-expansion",
        "faction-audit",
        "faction-manifest",
        "faction-apply",
        "character-manifest",
        "character-apply",
        "place-manifest",
        "place-apply",
        "backfill-review-packet",
        "lock",
        "unlock",
    ):
        if args.slot < 1 or args.slot > 5:
            emit_error("Slot must be between 1 and 5", args.json)
            return 1

    if args.command == "model":
        if args.slot is not None and (args.slot < 1 or args.slot > 5):
            emit_error("Slot must be between 1 and 5", args.json)
            return 1
        if not args.list and args.slot is None:
            emit_error("--slot is required unless using --list", args.json)
            return 1

    if args.command == "retrograde-seed-candidates" and args.slot is not None:
        if args.slot < 1 or args.slot > 5:
            emit_error("Slot must be between 1 and 5", args.json)
            return 1

    # Execute command
    if args.command == "load":
        result = run_load(args)
    elif args.command == "continue":
        result = run_continue(args)
    elif args.command == "undo":
        result = run_undo(args)
    elif args.command == "regenerate":
        result = run_regenerate(args)
    elif args.command == "model":
        result = run_model(args)
    elif args.command == "clear":
        result = run_clear(args)
    elif args.command == "trait-audit":
        result = run_trait_audit(args)
    elif args.command == "retrograde-packet":
        result = run_retrograde_packet(args)
    elif args.command == "retrograde-seed-candidates":
        result = run_retrograde_seed_candidates(args)
    elif args.command == "retrograde-expand-seeds":
        result = run_retrograde_expand_seeds(args)
    elif args.command == "retrograde-apply-expansion":
        result = run_retrograde_apply_expansion(args)
    elif args.command == "faction-audit":
        result = run_faction_audit(args)
    elif args.command == "faction-manifest":
        result = run_faction_manifest(args)
    elif args.command == "faction-apply":
        result = run_faction_apply(args)
    elif args.command == "character-manifest":
        result = run_character_manifest(args)
    elif args.command == "character-apply":
        result = run_character_apply(args)
    elif args.command == "place-manifest":
        result = run_place_manifest(args)
    elif args.command == "place-apply":
        result = run_place_apply(args)
    elif args.command == "backfill-review-packet":
        result = run_backfill_review_packet(args)
    elif args.command == "lock":
        result = run_lock(args)
    elif args.command == "unlock":
        result = run_unlock(args)
    else:
        emit_error(f"Unknown command: {args.command}", args.json)
        return 2

    # Check for errors (consistent format: success=False with error message)
    if not result.get("success", True) or result.get("error"):
        emit_error(result.get("error", "Unknown error"), args.json)
        return 1

    emit_output(result, args.json, truncate=args.truncate)
    if result.get("failed_policy"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
