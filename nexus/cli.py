"""
NEXUS CLI - Simplified command-line interface for story management.

Commands:
    nexus load --slot N         Display current slot state
    nexus continue --slot N     Advance the story (wizard or narrative)
    nexus undo --slot N         Revert the last action
    nexus regenerate --slot N   Regenerate the last storyteller turn
    nexus model --slot N        Get or set the model for a slot
    nexus jobs --slot N         Show provider-capable durable Orrery jobs
    nexus trait-audit --slot N  Dry-run new-story trait compiler audit
    nexus retrograde-packet --slot N  Build dry-run Retrograde seed packet
    nexus retrograde-seed-candidates  Call Skald for non-mutating seed candidates
    nexus retrograde-expand-seeds  Call Skald for non-mutating R6 expansion
    nexus retrograde-apply-expansion --slot N  Dry-run Retrograde persistence
    nexus retrograde-embed-history --slot N  Sync Retrograde summary retrieval
    nexus record-revelation --slot N  Grant awareness of an existing claim
    nexus faction-audit --slot N  Dry-run legacy faction column migration audit
    nexus faction-manifest --slot N  Build reviewed faction migration manifest
    nexus faction-apply --slot N  Dry-run ready faction manifest operations
    nexus character-manifest --slot N  Build reviewed character tag manifest
    nexus character-apply --slot N  Dry-run ready character manifest operations
    nexus place-manifest --slot N  Build reviewed place tag manifest
    nexus place-apply --slot N  Dry-run ready place manifest operations
    nexus backfill-review-packet --slot N  Summarize manifest review queues
    nexus inspect slot --slot N  Read one slot's state as a JSON envelope
    nexus inspect chunks|chunk|incubator|characters|places|factions --slot N
                                 Read player-plane story records as JSON envelopes
    nexus tags audit --slot N|--all  Report active tags in deprecated categories

The CLI is slot-centric: only --slot N is required. The backend resolves
all other state (wizard phase, current chunk, thread ID) automatically.
Each command's transport, exit codes and JSON envelopes are declared in
nexus/cli_contract.py.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
import functools
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Mapping,
    NoReturn,
    Optional,
    Sequence,
)
import uuid

import requests  # type: ignore[import-untyped]
from urllib3.exceptions import ReadTimeoutError

from nexus.cli_contract import (
    API_URL_ENV,
    ENVELOPE_COMMANDS,
    RUNTIME_CONFIG_COMMANDS,
    SELF_DIAGNOSTIC_COMMANDS,
    ExitCode,
    RemoteRuntime,
    command_path,
    detect_remote_runtime,
    error_envelope,
    exit_code_for,
    partial_fields,
    success_envelope,
    transport_refusal,
)
from nexus.config import load_settings
from nexus.config.settings_models import (
    OrreryRetrogradeWizardSettings,
    RuntimeCliSettings,
    Settings,
)
from nexus.runtime.contract import HOME_ENV, RUNTIME_CONFIG_ENV
from nexus.runtime.home import RuntimeHomeError, locate_runtime_home
from nexus.runtime.remote_auth import (
    InsecureRuntimeTransportError,
    build_runtime_request_auth,
)
from nexus.util.secret_manager import MissingSecretError, SecretStoreAccessError

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
FACTION_APPLY_SOURCE_KIND_CHOICES = (
    "authored",
    "llm_generated",
    "system",
    "template",
    "skald_inline",
)


def _load_cli_settings(config_path: Optional[str] = None) -> Optional[Settings]:
    """Load the runtime home's active config, or None for a bare install.

    ``config_path`` is a runtime verb's explicit ``--config``. A config named
    by it, NEXUS_HOME or NEXUS_RUNTIME_CONFIG must exist; only the checkout
    default may be absent (an installed CLI outside any checkout).
    """
    location = locate_runtime_home(config_path)
    if not location.config_path.exists():
        if location.locator == "checkout":
            return None
        raise FileNotFoundError(f"Configuration file not found: {location.config_path}")
    return _load_cli_settings_file(location.config_path)


def _load_cli_settings_file(path: Path) -> Settings:
    """Load one config version once, invalidating when its file changes."""
    resolved = path.resolve()
    stat = resolved.stat()
    return _load_cli_settings_version(str(resolved), stat.st_mtime_ns, stat.st_size)


@functools.lru_cache(maxsize=8)
def _load_cli_settings_version(path: str, modified_ns: int, size: int) -> Settings:
    """Cache a validated settings tree for an exact on-disk file version."""
    del modified_ns, size
    return load_settings(path)


def get_api_url() -> str:
    """Get the API URL from an override, remote profile, or local default."""

    override = os.environ.get(API_URL_ENV)
    if override:
        return override.rstrip("/")

    settings = _load_cli_settings()
    runtime = settings.runtime if settings is not None else None
    if runtime is not None and runtime.profile == "remote":
        remote = runtime.remote
        if remote is None:  # guarded by RuntimeSettings validation
            raise ValueError("Remote runtime profile has no remote configuration")
        return remote.base_url.rstrip("/")
    return DEFAULT_API_URL


def _api_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Send a NEXUS API request with origin-scoped runtime authentication."""
    settings = _load_cli_settings()
    remote = (
        settings.runtime.remote
        if settings is not None and settings.runtime is not None
        else None
    )
    auth = build_runtime_request_auth(url, remote)

    supplied_headers = kwargs.pop("headers", None) or {}
    headers = dict(supplied_headers)
    headers.update(auth.headers)
    kwargs["headers"] = headers
    if not auth.allow_redirects:
        kwargs["allow_redirects"] = False
    return getattr(requests, method)(url, **kwargs)


def _api_get(url: str, **kwargs: Any) -> requests.Response:
    """Send an authenticated GET to the configured NEXUS API."""
    return _api_request("get", url, **kwargs)


def _api_post(url: str, **kwargs: Any) -> requests.Response:
    """Send an authenticated POST to the configured NEXUS API."""
    return _api_request("post", url, **kwargs)


def _is_terminal_generation_status(status: Optional[str]) -> bool:
    """Return whether narrative generation has produced a loadable result."""
    return status in TERMINAL_GENERATION_STATUSES


# The phase each accepted setup artifact enters, and the reverse lookup.
_WIZARD_PHASE_ENTERED_BY = {"setting": "character", "character": "seed"}
_WIZARD_PHASE_ACCEPTED_BEFORE = {
    entered: accepted for accepted, entered in _WIZARD_PHASE_ENTERED_BY.items()
}


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
        "reused_entities",
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

    def _endpoint_label(entity_id: Any, name: Any) -> str:
        if entity_id is not None:
            return str(entity_id)
        return f"(pending stub) {name or '?'}"

    pair_tags = audit.get("applied_pair_tags") or []
    if pair_tags:
        print()
        print("Applied pair tags:")
        for item in pair_tags:
            subject = _endpoint_label(
                item.get("subject_entity_id"), item.get("subject_name")
            )
            obj = _endpoint_label(item.get("object_entity_id"), item.get("object_name"))
            print(f"  - {item['trait']}: {item['tag']} {subject} -> {obj}")

    for key, heading in (
        ("created_entities", "Created Entities"),
        ("reused_entities", "Reused Entities"),
    ):
        entities = audit.get(key) or []
        if entities:
            print()
            print(f"{heading}:")
            for item in entities:
                name = f" ({item['name']})" if item.get("name") else ""
                entity_id = item.get("entity_id")
                entity_label = entity_id if entity_id is not None else "pending"
                print(
                    "  - "
                    f"{item['trait']}: {item['entity_kind']} "
                    f"entity {entity_label}{name}"
                )

    created_relationships = audit.get("created_relationships") or []
    if created_relationships:
        print()
        print("Created relationships:")
        for item in created_relationships:
            target = _endpoint_label(
                item.get("character2_id"), item.get("character2_name")
            )
            print(
                "  - "
                f"{item['trait']}: character {item['character1_id']} -> "
                f"{target} "
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
    deaths = response.get("death_plan") or []
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
    print(f"  deaths: {len(deaths)}")
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
        "deaths_would_deactivate",
        "deaths_deactivated",
        "deaths_already_inactive",
        "deaths_blocked",
        "summaries_would_insert",
        "summaries_inserted",
        "summaries_already_present",
        "summaries_stamped_missing_vectors",
        "summaries_blocked",
    ):
        print(f"  {key}: {counters.get(key, 0)}")
    retrieval = plan.get("retrieval") or {}
    if retrieval:
        print(f"  summaries_enabled: {retrieval.get('summaries_enabled')}")
        pending = retrieval.get("embedding_pending_summary_ids") or []
        print(f"  embedding_pending_summary_ids: {pending}")
    embedding_results = payload.get("retrograde_embedding") or []
    if embedding_results:
        print()
        print("Embedded Retrograde summaries:")
        for result in embedding_results:
            print(
                f"  - summary {result.get('summary_id')}: "
                f"models={result.get('models')}, "
                f"dimensions={result.get('dimensions')}, "
                f"embedded_at={result.get('embedding_generated_at')}"
            )
    if blockers:
        print()
        print("Execute blockers:")
        for blocker in blockers:
            print(f"  - {blocker.get('id')}: {blocker.get('reason')}")
    if payload.get("persistence_output"):
        print()
        print(f"Output: {payload['persistence_output']}")


def _print_retrograde_embed_history(payload: Dict[str, Any]) -> None:
    """Print a compact Retrograde history retrieval sync summary."""

    sync = payload.get("retrograde_embed_history") or {}
    rows = sync.get("summary_rows") or []
    pending = sync.get("embedding_pending_summary_ids") or []
    embedded = sync.get("embedding_results") or []

    print("Retrograde history retrieval sync:")
    print(f"  dry_run: {sync.get('dry_run')}")
    print(f"  summary_rows: {len(rows)}")
    for row in rows:
        summary_id = row.get("summary_id")
        summary_label = (
            f"summary {summary_id}" if summary_id is not None else "no summary"
        )
        print(
            f"  - {row.get('event_ref')}: {row.get('status')} ({summary_label}, "
            f"embedding_pending={row.get('embedding_pending')})"
        )
    print(f"  embedding_pending_summary_ids: {pending}")
    if embedded:
        print()
        print("Embedded Retrograde summaries:")
        for result in embedded:
            print(
                f"  - summary {result.get('summary_id')}: "
                f"models={result.get('models')}, "
                f"dimensions={result.get('dimensions')}, "
                f"embedded_at={result.get('embedding_generated_at')}"
            )


def _print_retrograde_transition(retrograde: Dict[str, Any]) -> None:
    """Print a compact wizard-transition Retrograde outcome summary."""

    print("Retrograde cold-start history:")
    if not retrograde.get("enabled"):
        print(f"  skipped ({retrograde.get('skip_reason')})")
        return
    weird = retrograde.get("weird") or {}
    surface = retrograde.get("surface") or {}
    visible = surface.get("visible") or {}
    hidden = surface.get("hidden_counts") or {}
    print(f"  model: {retrograde.get('model')}")
    print(f"  weird: {weird.get('level')} ({weird.get('genre')})")
    for entity in visible.get("entities") or []:
        print(
            f"  - {entity.get('kind')}: {entity.get('name')} "
            f"({entity.get('status')})"
        )
    for relationship in visible.get("relationships") or []:
        print(
            f"  - relationship: {relationship.get('subject')} "
            f"--{relationship.get('relationship_type')}--> "
            f"{relationship.get('object')}"
        )
    print(
        "  hidden: "
        f"{hidden.get('world_events', 0)} events, "
        f"{hidden.get('entity_tags', 0)} tags, "
        f"{hidden.get('pair_tags', 0)} pair tags, "
        f"{hidden.get('deferred_seeds', 0)} deferred seeds"
    )
    embedded = retrograde.get("embedded_summary_ids") or []
    print(f"  embedded summaries: {len(embedded)}")
    for timing in retrograde.get("timings") or []:
        print(f"  timing {timing.get('stage')}: {timing.get('seconds'):.1f}s")


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

    if "turn_inspection" in payload:
        _print_turn_inspection(payload["turn_inspection"])
        return
    if "manifests_pruned" in payload:
        print("Slot\tRetention Days\tManifests Pruned")
        print(
            f"{payload['slot']}\t{payload['retention_days']}\t{payload['manifests_pruned']}"
        )
        return

    if payload.get("usage"):
        _print_usage(payload)
        return

    if "window_replay" in payload:
        _print_window_replay(payload["window_replay"])
        return

    if payload.get("queues") is not None:
        _print_jobs(payload)
        return

    # Display message/storyteller text
    message = payload.get("message") or payload.get("storyteller_text")
    if message:
        print(message)
        print()

    recovery = payload.get("recovery")
    if recovery:
        # The recorded action above consumed the menu; its continuation failed.
        detail = (
            recovery["error"]
            or recovery["error_class"]
            or f"Narrative generation failed (session {recovery['session_id']})"
        )
        print(f"[Failed continuation: {detail}]")
        print(f"Retry with: {payload['retry_command']}")
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

    if payload.get("retrograde_embed_history"):
        _print_retrograde_embed_history(payload)
        print()

    if payload.get("retrograde"):
        _print_retrograde_transition(payload["retrograde"])
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


def emit_error(
    message: str,
    as_json: bool,
    *,
    code: str = "domain_failure",
    partial: Optional[Mapping[str, Any]] = None,
) -> None:
    """Emit error output to stderr: the JSON envelope, or one ``Error:`` line."""
    if as_json:
        envelope = error_envelope(code, message, partial or {})
        print(json.dumps(envelope, indent=2, sort_keys=True), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)


def _fail(
    args: argparse.Namespace,
    code: str,
    message: str,
    partial: Optional[Mapping[str, Any]] = None,
) -> int:
    """Report one failure and return its stable exit code."""
    emit_error(message, args.json, code=code, partial=partial)
    return int(exit_code_for(code))


def _api_unreachable() -> Dict[str, Any]:
    """The failed result of a request that could not reach the NEXUS API."""
    return {
        "success": False,
        "code": "api_unreachable",
        "error": f"Cannot connect to API server at {get_api_url()}",
    }


# Request failures main() classifies alike for every HTTP command: no
# connection or no answer in time (api_unreachable, exit 4), an API URL that
# requests cannot use, and a runtime credential that is missing or refused
# (config_error, exit 1).
_API_URL_ERRORS: tuple[type[BaseException], ...] = (
    requests.exceptions.InvalidURL,
    requests.exceptions.InvalidSchema,
    requests.exceptions.MissingSchema,
)
_CREDENTIAL_ERRORS: tuple[type[BaseException], ...] = (
    InsecureRuntimeTransportError,
    MissingSecretError,
    SecretStoreAccessError,
)
# A handler that turns some request errors of its own into a result (``up``)
# re-raises these first (``except _TRANSPORT_ERRORS: raise``), so they reach
# main(), which reports them as api_unreachable or config_error.
_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.Timeout,
    *_API_URL_ERRORS,
    *_CREDENTIAL_ERRORS,
)


class ApiAnswerFailure(Exception):
    """An API answer an HTTP handler cannot use; main() reports it by ``code``.

    ``code`` is ``api_error`` (a non-2xx answer), ``config_error`` (an access
    rejection, :func:`_is_access_rejection`), or ``invalid_response`` (a 2xx
    body that is not the JSON the handler reads). ``status_code`` is the
    answer's HTTP status when the status is the failure. Not a ValueError, so
    a handler's own ``except ValueError`` never absorbs it.
    """

    def __init__(
        self, code: str, message: str, *, status_code: Optional[int] = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _answer_url(response: requests.Response) -> str:
    """The URL a response answered, without its query string."""
    return str(response.url).split("?", 1)[0]


def _is_access_rejection(response: requests.Response) -> bool:
    """Whether an answer is an edge's rejection: a 401, a 403, or any 3xx.

    The NEXUS gateway answers no 401, 403 or redirect itself, so one of these
    comes from an edge in front of it, such as Cloudflare Access. Requests
    follows redirects unless the request carries a runtime credential
    (``_api_request``), so a 3xx reaches a handler only unfollowed.
    """
    status = response.status_code
    return status in (401, 403) or 300 <= status < 400


def _access_rejection_message(response: requests.Response) -> str:
    """Name the rejected URL, its status, any redirect target, and the remedy."""
    status = response.status_code
    message = f"{_answer_url(response)} returned HTTP {status}"
    if 300 <= status < 400:
        location = response.headers.get("Location")
        message += (
            f" redirecting to {location}"
            if location
            else " (a redirect with no Location header)"
        )
    return (
        f"{message}: an access rejection from in front of the NEXUS API, which "
        "answers no 401, 403 or redirect itself. Check the runtime credential: "
        "[runtime.remote.cloudflare_access] and its Access service token, or "
        "NEXUS_AUTH."
    )


def _answer_failure_code(response: requests.Response) -> str:
    """The CLI error code of a non-2xx answer: config_error or api_error."""
    return "config_error" if _is_access_rejection(response) else "api_error"


def _check_answer(response: requests.Response) -> None:
    """Return on a 2xx answer; raise :class:`ApiAnswerFailure` otherwise."""
    status = response.status_code
    if 200 <= status < 300:
        return
    if _is_access_rejection(response):
        raise ApiAnswerFailure(
            "config_error", _access_rejection_message(response), status_code=status
        )
    raise ApiAnswerFailure(
        "api_error", f"API error: {response.text}", status_code=status
    )


def _api_answer(response: requests.Response) -> Any:
    """Return a 2xx answer's JSON body; raise :class:`ApiAnswerFailure` otherwise."""
    _check_answer(response)
    try:
        return response.json()
    except ValueError as exc:
        raise ApiAnswerFailure(
            "invalid_response",
            f"{_answer_url(response)} returned a body that is not JSON: {exc}",
        ) from exc


def _api_object(response: requests.Response) -> Dict[str, Any]:
    """Return a 2xx answer's JSON object; raise :class:`ApiAnswerFailure` otherwise."""
    body = _api_answer(response)
    if not isinstance(body, dict):
        raise ApiAnswerFailure(
            "invalid_response",
            f"{_answer_url(response)} returned a body that is not a JSON object",
        )
    return body


def _runtime_cli_settings() -> RuntimeCliSettings:
    """Read the CLI's request budgets from [runtime.cli].

    A bare install with no nexus.toml (where get_api_url() targets
    DEFAULT_API_URL) and a config without [runtime] both use the
    RuntimeCliSettings defaults, the values the checkout's nexus.toml ships.
    """
    settings = _load_cli_settings()
    if settings is None or settings.runtime is None:
        return RuntimeCliSettings()
    return settings.runtime.cli


def _request_timeout_seconds() -> float:
    """The per-request budget of a play or slot command's short API request."""
    return _runtime_cli_settings().request_timeout_seconds


def _turn_request_timeout_seconds() -> float:
    """The per-request budget of a model-turn request (chat, scheduling POSTs)."""
    return _runtime_cli_settings().turn_request_timeout_seconds


def run_load(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Display current slot state.

    Calls GET /api/slot/{slot}/state to get the current state.
    If the slot is empty, offers to initialize it.
    """
    url = f"{get_api_url()}/api/slot/{args.slot}/state"

    response = _api_get(url, timeout=_request_timeout_seconds())
    data = _api_object(response)

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
            "choices": data.get("choices", []),
            "weird_level": data.get("weird_level"),
        }
        if data.get("pending_confirmation") in {"setting", "character"}:
            phase = data["pending_confirmation"]
            result.update(
                pending_confirmation=phase,
                artifact_token=data.get("artifact_token"),
                thread_id=data.get("thread_id"),
                message=(
                    f"The saved {phase} draft awaits confirmation. "
                    f"Use 'nexus continue --slot {args.slot}' to confirm, "
                    "or supply --user-text to revise it."
                ),
            )
        if data.get("awaiting_introduction") in _WIZARD_PHASE_ACCEPTED_BEFORE:
            phase = data["awaiting_introduction"]
            result.update(
                awaiting_introduction=phase,
                message=(
                    f"The {phase} phase was entered but never introduced. "
                    f"Run 'nexus continue --slot {args.slot}' to load its "
                    "introduction."
                ),
            )
        if data.get("character_revision_pending"):
            result.update(
                character_revision_pending=True,
                message=(
                    "Character revision is unfinished. Continue with --user-text "
                    "describing the replacement before confirming."
                ),
            )
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
        "recovery": data.get("recovery"),
        "retry_command": (
            f"nexus retry --slot {args.slot}" if data.get("recovery") else None
        ),
    }


def _inspect_timeout_seconds() -> float:
    """Read the per-request budget of ``nexus inspect`` from [runtime.cli]."""
    return _runtime_cli_settings().inspect_timeout_seconds


class InspectFailure(Exception):
    """An inspect read the API answered with something other than its record."""

    def __init__(
        self, code: str, message: str, *, status_code: Optional[int] = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# The body GET /api/narrative/incubator answers when no draft is pending.
_EMPTY_INCUBATOR = {"message": "Incubator is empty"}
# The detail GET /api/narrative/latest-chunk answers for a story with no chunks.
_NO_CHUNKS_DETAIL = "No chunks found"


def _inspect_response(
    path: str, *, params: Optional[Mapping[str, Any]] = None
) -> requests.Response:
    """Send one inspect GET; a request that cannot connect propagates to main()."""
    return _api_get(
        f"{get_api_url()}{path}", params=params, timeout=_inspect_timeout_seconds()
    )


def _inspect_body(response: requests.Response) -> Any:
    """Return a 2xx response's JSON body, or raise the matching InspectFailure.

    A 404 is ``not_found``; an access rejection (a 401, a 403 or an unfollowed
    redirect) is ``config_error``; any other non-2xx answer is ``api_error``.
    """
    url = response.url.split("?", 1)[0]
    status = response.status_code
    if status == 404:
        raise InspectFailure(
            "not_found", f"{url} returned 404: {response.text}", status_code=status
        )
    if _is_access_rejection(response):
        raise InspectFailure(
            "config_error", _access_rejection_message(response), status_code=status
        )
    if not 200 <= status < 300:
        raise InspectFailure(
            "api_error",
            f"{url} returned HTTP {status}: {response.text}",
            status_code=status,
        )
    try:
        return response.json()
    except ValueError as exc:
        raise InspectFailure(
            "invalid_response", f"{url} returned a body that is not JSON: {exc}"
        ) from exc


def _inspect_read(path: str, *, params: Optional[Mapping[str, Any]] = None) -> Any:
    """GET one player-plane route and return its JSON body unchanged."""
    return _inspect_body(_inspect_response(path, params=params))


def _require_shape(value: Any, kind: type, what: str) -> Any:
    """Raise invalid_response unless ``value`` is a ``kind`` (dict or list)."""
    if not isinstance(value, kind):
        raise InspectFailure(
            "invalid_response", f"{what} is not a JSON {kind.__name__}: {value!r}"
        )
    return value


def _require_records(value: Any, what: str) -> List[Dict[str, Any]]:
    """Raise invalid_response unless ``value`` is a list of objects with ids."""
    records = _require_shape(value, list, what)
    for record in records:
        if not isinstance(record, dict) or type(record.get("id")) is not int:
            raise InspectFailure(
                "invalid_response", f"{what} holds a record without an id: {record!r}"
            )
    return records


def _inspect_slot(args: argparse.Namespace) -> Any:
    """GET /api/slot/{slot}/state (player-plane ``slot.read``)."""
    state = _inspect_read(f"/api/slot/{args.slot}/state")
    return _require_shape(state, dict, f"Slot {args.slot} state")


def _adjacent_chunk(slot: int, chunk_id: int, side: str) -> Optional[Dict[str, Any]]:
    """The committed chunk before or after ``chunk_id`` (``previous``/``next``)."""
    adjacent = _require_shape(
        _inspect_read(
            f"/api/narrative/chunks/{chunk_id}/adjacent", params={"slot": slot}
        ),
        dict,
        f"Chunks adjacent to {chunk_id}",
    )
    if side not in adjacent:
        raise InspectFailure(
            "invalid_response", f"Chunks adjacent to {chunk_id} name no {side} chunk"
        )
    neighbour = adjacent[side]
    if neighbour is None:
        return None
    return _require_records([neighbour], f"The {side} chunk of {chunk_id}")[0]


def _inspect_chunks(args: argparse.Namespace) -> Any:
    """Committed chunks, oldest first: the last N, or those in an id range.

    ``--last N`` reads GET /api/narrative/latest-chunk, then walks
    GET /api/narrative/chunks/{id}/adjacent backwards. ``--from``/``--to``
    walk the same route forwards from the first committed chunk at or after
    ``--from`` (default: the first chunk) through ``--to``, which is required
    whenever ``--from`` is given, and stop at the chunk with id ``--to``.
    Each chunk costs one sequential request, so a wide range or a large N
    sends that many requests; a range sends one more when no committed chunk
    has id ``--to``, to find where it ends. Every chunk is the route's own
    payload.
    """
    slot = args.slot
    chunks: List[Dict[str, Any]] = []
    if args.last is not None:
        response = _inspect_response(
            "/api/narrative/latest-chunk", params={"slot": slot}
        )
        if response.status_code == 404:
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            if detail == _NO_CHUNKS_DETAIL:
                return chunks
        latest: Optional[Dict[str, Any]] = _require_records(
            [_inspect_body(response)], "The latest chunk"
        )[0]
        while latest is not None and len(chunks) < args.last:
            chunks.append(latest)
            if len(chunks) < args.last:
                latest = _adjacent_chunk(slot, latest["id"], "previous")
        chunks.reverse()
        return chunks
    first = 1 if args.from_id is None else args.from_id
    cursor = _adjacent_chunk(slot, first - 1, "next")
    while cursor is not None and cursor["id"] <= args.to_id:
        chunks.append(cursor)
        if cursor["id"] == args.to_id:
            break
        cursor = _adjacent_chunk(slot, cursor["id"], "next")
    return chunks


def _inspect_chunk(args: argparse.Namespace) -> Any:
    """GET /api/narrative/chunks/{id}: one committed chunk."""
    chunk = _inspect_read(
        f"/api/narrative/chunks/{args.chunk_id}", params={"slot": args.slot}
    )
    return _require_shape(chunk, dict, f"Chunk {args.chunk_id}")


def _inspect_incubator(args: argparse.Namespace) -> Any:
    """GET /api/narrative/incubator: the pending draft, or null when none waits."""
    body = _require_shape(
        _inspect_read("/api/narrative/incubator", params={"slot": args.slot}),
        dict,
        "The incubator",
    )
    if body == _EMPTY_INCUBATOR:
        return None
    if not isinstance(body.get("session_id"), str):
        raise InspectFailure(
            "invalid_response", f"The incubator draft names no session: {body!r}"
        )
    return body


def _entity_family(route: str, label: str) -> Callable[[argparse.Namespace], Any]:
    """Build the reader for one entity family's list route and ``<id>`` detail."""

    def read(args: argparse.Namespace) -> Any:
        params: Dict[str, Any] = {"slot": args.slot}
        if args.entity_id is not None and route == "/api/characters":
            # The characters route filters by id range itself.
            params.update(startId=args.entity_id, endId=args.entity_id)
        records = _require_records(
            _inspect_read(route, params=params), f"The {label} list"
        )
        if args.entity_id is None:
            return records
        matches = [record for record in records if record["id"] == args.entity_id]
        if not matches:
            raise InspectFailure(
                "not_found",
                f"{route} lists no {label} {args.entity_id} in slot {args.slot}",
            )
        return matches[0]

    return read


_INSPECT_READERS: Mapping[str, Callable[[argparse.Namespace], Any]] = {
    "slot": _inspect_slot,
    "chunks": _inspect_chunks,
    "chunk": _inspect_chunk,
    "incubator": _inspect_incubator,
    "characters": _entity_family("/api/characters", "character"),
    "places": _entity_family("/api/places", "place"),
    "factions": _entity_family("/api/factions", "faction"),
}

# What human output prints for an explicitly empty read.
_INSPECT_EMPTY: Mapping[str, str] = {
    "chunks": "No committed chunks.",
    "incubator": "Incubator is empty.",
    "characters": "No characters.",
    "places": "No places.",
    "factions": "No factions.",
}


def run_inspect(args: argparse.Namespace) -> Dict[str, Any]:
    """Run one read-only ``nexus inspect`` command over the player-plane API.

    Each verb reads GET routes nexus/api/route_capabilities.py declares on the
    player plane and puts what they answer under ``data``: each record is the
    route's own payload, unchanged. ``inspect chunks`` lists those payloads
    oldest first, and ``inspect incubator`` reports the route's empty answer
    as ``None`` (JSON ``null``). Nothing is written. A request that cannot
    connect, is dropped, or times out reaches main(), which reports it as
    ``api_unreachable`` (exit 4).
    """
    reader = _INSPECT_READERS.get(args.inspect_command)
    if reader is None:
        raise ValueError(f"Unknown inspect command: {args.inspect_command!r}")
    try:
        data = reader(args)
    except InspectFailure as failure:
        result: Dict[str, Any] = {
            "success": False,
            "slot": args.slot,
            "code": failure.code,
            "error": failure.message,
        }
        if failure.status_code is not None:
            result["status_code"] = failure.status_code
        return result
    return {"success": True, "data": data}


def _print_inspection(data: Any, truncate: bool, verb: str) -> None:
    """Print an inspected record's fields, or each record of a list, in turn.

    An empty read prints the verb's :data:`_INSPECT_EMPTY` line; only the
    list and incubator verbs can read nothing, so only they have one.
    """
    if data is None or data == []:
        print(_INSPECT_EMPTY[verb])
        return
    records = data if isinstance(data, list) else [data]
    for index, record in enumerate(records):
        if index:
            print()
        for key, value in record.items():
            _print_value(key, value, indent=0, truncate=truncate)


def _retrograde_wizard_settings(
    settings: Settings, purpose: str
) -> OrreryRetrogradeWizardSettings:
    """Return [orrery.retrograde.wizard], naming the CLI purpose if absent."""

    orrery_settings = settings.orrery
    if orrery_settings is None:
        raise ValueError(
            f"nexus.toml is missing the [orrery] section required for the {purpose}"
        )
    return orrery_settings.retrograde.wizard


def _transition_timeout_seconds() -> int:
    """Read the wizard transition HTTP timeout from nexus.toml.

    Retrograde cold-start generation (frontier seed + expansion calls plus
    persistence and embedding) runs inside the transition request, so the
    budget is minutes, not the seconds ordinary wizard turns need.
    """

    return _retrograde_wizard_settings(
        load_settings(), "wizard transition timeout"
    ).transition_timeout_seconds


def _retrograde_status_stage(status: Any) -> Optional[str]:
    """Validate a Retrograde status payload and name the stage it reports.

    Returns None while idle, the stage in progress, ``done``, or
    ``failed (<stage>)`` naming the stage that failed. The payload must name
    the run that owns it (``run``: an identity, or null before any run).
    """

    from nexus.agents.orrery.retrograde_orchestrator import RETROGRADE_WIZARD_STAGES

    if not isinstance(status, dict) or not (
        "run" in status and (status["run"] is None or isinstance(status["run"], str))
    ):
        raise ValueError(f"Unrecognized Retrograde status: {status!r}")
    stage = status.get("stage")
    if stage == "idle":
        return None
    if stage == "failed":
        detail = status.get("detail")
        failed = detail.get("stage") if isinstance(detail, dict) else None
        if failed not in RETROGRADE_WIZARD_STAGES or failed == "done":
            raise ValueError(f"Retrograde failure names no known stage: {status!r}")
        return f"failed ({failed})"
    if stage not in RETROGRADE_WIZARD_STAGES:
        raise ValueError(f"Unrecognized Retrograde status: {status!r}")
    return str(stage)


class _RetrogradeStageEcho:
    """Print each Retrograde stage change of one transition wait once."""

    def __init__(self, slot: int, read_timeout_seconds: float) -> None:
        self._url = f"{get_api_url()}/api/story/new/retrograde/status"
        self._slot = slot
        self._read_timeout_seconds = read_timeout_seconds
        self._printed: Optional[str] = None
        # The run owning the gateway's record before the transition was
        # posted (None: no run yet). The gateway keeps that record until this
        # run's flow replaces it under a new identity, so any record with
        # another identity is this run's, terminal or not.
        self._previous_run: Optional[str] = None
        # Set by a terminal stage or a failed read; no further reads follow.
        self.settled = False

    def _fetch(self) -> Optional[tuple[dict[str, Any], Optional[str]]]:
        """Read and validate the slot's status; a failed read settles the echo."""

        try:
            response = _api_get(
                self._url,
                params={"slot": self._slot},
                timeout=self._read_timeout_seconds,
            )
            response.raise_for_status()
            status = response.json()
            stage = _retrograde_status_stage(status)
        except (requests.RequestException, ValueError) as exc:
            print(f"Genesis stage unavailable: {exc}", file=sys.stderr, flush=True)
            self.settled = True
            return None
        return status, stage

    def snapshot(self) -> None:
        """Note which run owns the record; call before posting the transition."""

        read = self._fetch()
        if read is not None:
            self._previous_run = read[0]["run"]

    def read(self) -> None:
        """Read the slot's status once and print this run's stage if it changed."""

        read = self._fetch()
        if read is None:
            return
        status, stage = read
        if status["run"] == self._previous_run:
            return
        if stage is not None and stage != self._printed:
            print(f"Genesis stage: {stage}", flush=True)
            self._printed = stage
        self.settled = status["stage"] in {"done", "failed"}

    def poll(self, interval_seconds: float, stopped: threading.Event) -> None:
        """Read every interval until stopped or settled."""

        while not self.settled and not stopped.wait(interval_seconds):
            self.read()


@contextmanager
def _echo_retrograde_stages(slot: int, *, enabled: bool) -> Iterator[None]:
    """Print Retrograde stage changes while the wizard transition is in flight.

    A read before the transition is posted notes which run owns the gateway's
    record; only records of another run are printed. Once the transition
    answers, one more read reports the stage it finished or failed at; an
    interrupted or unanswered transition skips that read. Human output only:
    JSON callers receive the transition outcome alone.
    """

    if not enabled:
        yield
        return
    settings = load_settings()
    if settings.api is None:
        raise ValueError(
            "nexus.toml is missing the [api] section required for the wizard "
            "stage poll"
        )
    interval = _retrograde_wizard_settings(
        settings, "wizard stage poll"
    ).status_poll_interval_seconds
    # Each stage read gets the configured per-request budget of a status read.
    echo = _RetrogradeStageEcho(
        slot, settings.api.narrative_generation.request_timeout_seconds
    )
    echo.snapshot()
    stopped = threading.Event()
    reader = threading.Thread(
        target=echo.poll,
        args=(interval, stopped),
        name="retrograde-stage-echo",
        daemon=True,
    )
    reader.start()
    try:
        yield
    finally:
        stopped.set()
        reader.join()
    # The gateway records "done" or "failed" just before it answers, so the
    # interval-paced reader rarely sees it: read the outcome once more.
    if not echo.settled:
        echo.read()


def _generation_timeout_seconds() -> int:
    """Read the narrative-turn HTTP timeout from nexus.toml.

    Frontier storyteller generation runs inside the continue request and blocks
    the API worker, so a status poll is not answered until the turn completes;
    the client budget must exceed the slowest expected generation.
    """

    from nexus.config import load_settings

    return load_settings().apex.generation_timeout_seconds


def _poll_interval_seconds() -> float:
    """Read the delay between session status reads from [runtime.cli]."""
    return _runtime_cli_settings().poll_interval_seconds


class SessionWaitFailure(Exception):
    """A generation session wait that ended without a loadable result.

    ``status`` names what ended the wait (``error``: the API reports the
    generation failed; ``timeout``, ``interrupted``, ``unreachable``,
    ``http_error``, ``invalid_response``, ``result_unavailable``); ``code`` is
    the stable CLI error code the failure is reported under.
    """

    def __init__(
        self, status: str, detail: str, *, code: str = "domain_failure"
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.code = code


def _unreachable_failure(exc: BaseException) -> SessionWaitFailure:
    """A request mid-wait the gateway refused or dropped, as api_unreachable."""
    return SessionWaitFailure(
        "unreachable",
        f"Cannot connect to API server at {get_api_url()}: {exc}",
        code="api_unreachable",
    )


def _is_read_timeout(exc: BaseException) -> bool:
    """Whether a failed request ran out of time reading the gateway's answer.

    Requests raises ``ReadTimeout`` when the headers do not arrive in time, but
    wraps urllib3's ``ReadTimeoutError`` in a ``ConnectionError`` when the body
    stalls after them. Either means the gateway answered too slowly, not that
    it refused or dropped the connection. The walk follows the cause chain:
    what each exception wraps (an exception argument) or was raised from
    (``__cause__``). It never follows ``__context__``: an exception a caller
    was handling when the request failed is not a cause of the failure.
    """
    seen: set[int] = set()
    chain: List[BaseException] = [exc]
    while chain:
        link = chain.pop()
        if id(link) in seen:
            continue
        seen.add(id(link))
        if isinstance(link, (requests.exceptions.ReadTimeout, ReadTimeoutError)):
            return True
        chain.extend(arg for arg in link.args if isinstance(arg, BaseException))
        if link.__cause__ is not None:
            chain.append(link.__cause__)
    return False


def _failed_session_read(
    exc: requests.exceptions.RequestException, url: str, timeout_detail: str
) -> SessionWaitFailure:
    """Classify one failed request of a generation session.

    A status read, the state load, and the seed's transition and opening-turn
    POSTs map their failures here, so they cannot drift. A read that ran out
    of time, a body stalled after its headers included
    (:func:`_is_read_timeout`), is ``timeout`` with ``timeout_detail``. A
    refused or dropped connection, a body cut off mid-answer included, is
    ``unreachable`` (``api_unreachable``). Any other failed request is
    ``http_error``.
    """
    if _is_read_timeout(exc):
        return SessionWaitFailure("timeout", timeout_detail)
    if isinstance(
        exc,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
        ),
    ):
        return _unreachable_failure(exc)
    if isinstance(exc, requests.exceptions.Timeout):
        return SessionWaitFailure("timeout", timeout_detail)
    return SessionWaitFailure("http_error", f"Could not read {url}: {exc}")


def _session_status(payload: Any) -> Dict[str, Any]:
    """Validate one generation status payload from the status route."""
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("status"), str)
        or not payload["status"].strip()
    ):
        raise ValueError(
            "Generation status must be an object with a non-empty status string"
        )
    if payload.get("error") is not None and not isinstance(payload["error"], str):
        raise ValueError("Generation status error must be a string or null")
    chunk_id = payload.get("chunk_id")
    if chunk_id is not None and type(chunk_id) is not int:
        raise ValueError("Generation status chunk_id must be an integer or null")
    return payload


def wait_for_session(
    session_id: str, *, slot: int, timeout: float, interval: float
) -> Dict[str, Any]:
    """Poll one generation session until it finishes; return its terminal status.

    Reads ``GET /api/narrative/status/{session_id}?slot=N`` every ``interval``
    seconds within ``timeout`` seconds overall; each read may take the whole
    remaining budget, since a turn generating inside the gateway can hold a
    status read until it finishes. Returns the status payload once it reports
    a terminal status (:data:`TERMINAL_GENERATION_STATUSES`). Every other end
    raises :class:`SessionWaitFailure`: the API reporting the generation failed
    (``error``, with the API's own message), the budget spent while the
    session still runs or a status read stalls, before or after its headers
    (``timeout``), a gateway that refuses or drops the connection
    (``unreachable``, reported as ``api_unreachable``), a non-2xx answer
    (``http_error``, reported as ``api_error``, or as ``config_error`` for an
    access rejection: a 401, a 403 or an unfollowed redirect), any other
    failed request (``http_error``, a domain failure), an unusable payload
    (``invalid_response``, a domain failure), or Ctrl+C (``interrupted``). A
    failed read is never retried.
    """
    url = f"{get_api_url()}/api/narrative/status/{session_id}"
    deadline = time.monotonic() + timeout
    try:
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                response = _api_get(url, params={"slot": slot}, timeout=remaining)
            except requests.exceptions.RequestException as exc:
                raise _failed_session_read(
                    exc,
                    url,
                    f"Generation timed out: no status answer within {timeout}s",
                ) from exc
            if not 200 <= response.status_code < 300:
                raise SessionWaitFailure(
                    "http_error",
                    f"{url} returned HTTP {response.status_code}: {response.text}",
                    code=_answer_failure_code(response),
                )
            try:
                status = _session_status(response.json())
            except ValueError as exc:
                raise SessionWaitFailure(
                    "invalid_response",
                    f"Invalid narrative generation response: {exc}",
                ) from exc
            if status["status"] == "error":
                raise SessionWaitFailure(
                    "error", status.get("error") or "Generation failed"
                )
            if _is_terminal_generation_status(status["status"]):
                return status
            time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        raise SessionWaitFailure(
            "interrupted", "Waiting for narrative generation was interrupted"
        ) from None
    raise SessionWaitFailure("timeout", "Generation timed out")


def _load_session_result(
    slot: int, session_id: str, status: Mapping[str, Any]
) -> Dict[str, Any]:
    """Load the narrative a finished session produced from the slot's state.

    Raises :class:`SessionWaitFailure` when the state cannot be read or no
    longer shows this session's result: ``unreachable`` (``api_unreachable``)
    when the gateway refuses or drops the connection; ``http_error`` for a
    non-2xx answer, reported as ``api_error``, or as ``config_error`` for an
    access rejection (a 401, a 403 or an unfollowed redirect); a domain
    failure for a read that times out (a body stalled after its headers
    included) or fails otherwise, an unusable state, or a state that no longer
    shows the result. :func:`_failed_session_read` classifies the failed read.
    """
    url = f"{get_api_url()}/api/slot/{slot}/state"
    try:
        response = _api_get(url, timeout=_request_timeout_seconds())
    except requests.exceptions.RequestException as exc:
        raise _failed_session_read(
            exc, url, f"Timed out waiting for API server at {get_api_url()}: {exc}"
        ) from exc
    if not 200 <= response.status_code < 300:
        raise SessionWaitFailure(
            "http_error",
            f"{url} returned HTTP {response.status_code}: {response.text}",
            code=_answer_failure_code(response),
        )
    try:
        state = response.json()
        if not isinstance(state, dict):
            raise ValueError("Narrative slot state must be an object")
        for flag in ("is_empty", "is_wizard_mode", "has_pending"):
            if flag in state and not isinstance(state[flag], bool):
                raise ValueError(f"Narrative slot state {flag} must be a boolean")
        current_chunk_id = state.get("current_chunk_id")
        if current_chunk_id is not None and type(current_chunk_id) is not int:
            raise ValueError(
                "Narrative slot state current_chunk_id must be an integer or null"
            )
        choices = state.get("choices", [])
        if not isinstance(choices, list) or any(
            not isinstance(choice, str) for choice in choices
        ):
            raise ValueError("Narrative slot state choices must be a list of strings")
    except ValueError as exc:
        raise SessionWaitFailure(
            "invalid_response", f"Invalid narrative generation response: {exc}"
        ) from exc
    chunk_id = status.get("chunk_id")
    message = state.get("storyteller_text")
    if (
        (not state.get("has_pending") and not chunk_id)
        or (chunk_id is not None and current_chunk_id != chunk_id)
        or state.get("is_empty")
        or state.get("is_wizard_mode")
        or (state.get("has_pending") and state.get("session_id") != session_id)
    ):
        raise SessionWaitFailure(
            "result_unavailable",
            "Completed generation no longer matches the slot's narrative.",
        )
    if not isinstance(message, str) or not message.strip():
        raise SessionWaitFailure(
            "result_unavailable",
            "Completed generation has no narrative text available.",
        )
    return {
        "success": True,
        "message": message,
        "choices": choices,
        "chunk_id": chunk_id,
        "session_id": session_id,
    }


def _wait_for_narrative_result(slot: int, session_id: str) -> Dict[str, Any]:
    """Wait on one scheduled generation and load its matching narrative result.

    The one waiter of ``continue``, ``retry``, ``regenerate``, and the seed's
    opening turn. A failed wait keeps the scheduled session and its recovery
    command, reported under the failure's own code: ``api_unreachable``
    (exit 4) when the gateway is gone, ``api_error`` for a non-2xx answer,
    ``config_error`` for an access rejection (a 401, a 403 or an unfollowed
    redirect), ``domain_failure`` otherwise (all exit 1).
    """
    try:
        status = wait_for_session(
            session_id,
            slot=slot,
            timeout=_generation_timeout_seconds(),
            interval=_poll_interval_seconds(),
        )
        return _load_session_result(slot, session_id, status)
    except KeyboardInterrupt:
        failure = SessionWaitFailure(
            "interrupted", "Waiting for narrative generation was interrupted"
        )
    except SessionWaitFailure as exc:
        failure = exc
    return {
        "success": False,
        "code": failure.code,
        "error": failure.detail,
        "session_id": session_id,
        "generation_error": {"status": failure.status, "detail": failure.detail},
        "recovery_command": f"nexus load --slot {slot}",
    }


def _bootstrap_seed_narrative(
    *,
    result: Dict[str, Any],
    slot: int,
    model: Optional[str],
    schedule_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Preserve the saved seed while scheduling and awaiting its opening turn.

    ``schedule_timeout`` bounds the POST that schedules the turn, in seconds;
    None reads ``[runtime.cli].turn_request_timeout_seconds``. The wait on the
    scheduled session keeps its own budgets. A non-2xx scheduling answer is
    ``api_error``, or ``config_error`` for an access rejection; a 2xx answer
    without a session ID, a body that is not a JSON object included, is a
    domain failure. Either way the saved seed stays in the result.
    """

    result["phase"] = None  # The successful transition has left wizard mode.
    result["narrative_bootstrap"] = False
    payload: Dict[str, Any] = {"slot": slot, "user_text": ""}
    if model:
        payload["model"] = model
    url = f"{get_api_url()}/api/narrative/continue"
    if schedule_timeout is None:
        schedule_timeout = _turn_request_timeout_seconds()
    try:
        response = _api_post(url, json=payload, timeout=schedule_timeout)
        if not 200 <= response.status_code < 300:
            completion = {
                "success": False,
                "code": _answer_failure_code(response),
                "error": (
                    f"{url} returned HTTP {response.status_code}: {response.text}"
                ),
            }
        else:
            body = response.json()
            session_id = body.get("session_id") if isinstance(body, dict) else None
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("Opening generation returned no session ID")
            completion = _wait_for_narrative_result(slot, session_id)
    except KeyboardInterrupt:
        completion = {
            "success": False,
            "error": "Scheduling the opening narrative was interrupted",
        }
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.ChunkedEncodingError,
        requests.exceptions.Timeout,
    ) as exc:
        # The seed is saved and kept as partial work either way, classified as
        # the wait's reads are: a gateway that refused or dropped the
        # connection is the transport code (exit 4); one that accepted the
        # request but answered too late, a body stalled after its headers
        # included, is a domain failure, like any late read.
        failure = _failed_session_read(
            exc, url, f"Timed out waiting for API server at {get_api_url()}: {exc}"
        )
        completion = {"success": False, "code": failure.code, "error": failure.detail}
    except (requests.exceptions.RequestException, ValueError) as exc:
        completion = {"success": False, "error": str(exc)}

    if not completion["success"]:
        result.update(completion)
        result["bootstrap_error"] = {
            "detail": completion["error"],
            "session_id": completion.get("session_id"),
        }
        result["recovery_command"] = f"nexus load --slot {slot}"
        result["error"] = (
            "The seed was saved and the story initialized, but the opening "
            f"narrative could not be loaded: {completion['error']}. "
            f"Inspect with: {result['recovery_command']}"
        )
        return result

    result.update(
        narrative_bootstrap=True,
        next_phase_intro=completion["message"],
        choices=completion["choices"],
        chunk_id=completion["chunk_id"],
        session_id=completion["session_id"],
    )
    return result


def _seed_transition_failure(
    *,
    result: Dict[str, Any],
    slot: int,
    detail: str,
    status_code: Optional[int],
    status: str,
    code: str = "domain_failure",
) -> Dict[str, Any]:
    """Report a persisted seed whose narrative transition did not complete.

    ``code`` is the CLI error code: ``api_unreachable`` (exit 4) when the
    gateway refused or dropped the transition, ``api_error`` for a non-2xx
    answer, ``config_error`` for an access rejection (a 401, a 403 or an
    unfollowed redirect), ``invalid_response`` for a 2xx body that is not a
    JSON object, a domain failure otherwise. Either way the saved seed and its
    retry command stay in the result.
    """
    retry_command = f"nexus continue --slot {slot}"
    result.update(
        {
            "success": False,
            "code": code,
            "error": (
                "Seed artifact was saved, but the narrative transition failed. "
                f"Retry with: {retry_command}"
            ),
            "transition_error": {
                "status": status,
                "status_code": status_code,
                "detail": detail,
            },
            "retry_command": retry_command,
        }
    )
    return result


def _apply_traits_to_wildcard_transition(
    *,
    url: str,
    slot: int,
    data: Dict[str, Any],
    result: Dict[str, Any],
    model: Optional[str],
) -> None:
    """Fetch and attach the wildcard intro after trait confirmation."""
    if not (
        data.get("subphase_complete")
        and data.get("phase") == "character"
        and data.get("subphase") == "wildcard"
    ):
        return

    intro_payload = {
        "slot": slot,
        "message": (
            "[SYSTEM] Phase character subphase traits complete. "
            "Proceeding to wildcard. Please introduce the next subphase."
        ),
        "message_origin": "wizard_control",
        "current_phase": "character",
    }
    if model:
        intro_payload["model"] = model

    recovery_command = (
        f'nexus continue --slot {slot} --user-text "Continue to the wildcard step."'
    )

    def intro_failed(detail: str, status_code: Optional[int]) -> None:
        """Keep the saved traits a success and name the introduction's retry."""
        result["intro_error"] = {"detail": detail, "status_code": status_code}
        result["intro_recovery_command"] = recovery_command
        result["message"] = (
            f"{result.get('message') or 'Traits confirmed.'} Traits were saved, "
            "but the wildcard introduction could not be loaded. Retry with: "
            f"{recovery_command}"
        )

    try:
        intro_response = _api_post(
            url, json=intro_payload, timeout=_turn_request_timeout_seconds()
        )
    except requests.exceptions.RequestException as exc:
        intro_failed(str(exc), None)
        return

    if not 200 <= intro_response.status_code < 300:
        detail = intro_response.text.strip() or (
            f"Wildcard intro request failed with HTTP {intro_response.status_code}."
        )
        intro_failed(detail, intro_response.status_code)
        return

    try:
        intro_data = _api_object(intro_response)
    except ApiAnswerFailure as exc:
        intro_failed(exc.message, exc.status_code)
        return
    result["next_phase_intro"] = intro_data.get("message")
    result["choices"] = intro_data.get("choices", [])
    result["phase"] = intro_data.get("phase") or "character"
    result["subphase"] = "wildcard"


def _wizard_artifact_identity(data: Mapping[str, Any]) -> Dict[str, str]:
    """Read the exact persisted artifact the player is confirming or revising."""
    phase = data.get("pending_confirmation")
    thread_id = data.get("thread_id")
    artifact_token = data.get("artifact_token")
    if (
        phase not in {"setting", "character"}
        or data.get("phase") != phase
        or not isinstance(thread_id, str)
        or not thread_id.strip()
        or not isinstance(artifact_token, str)
        or not artifact_token.strip()
    ):
        raise ValueError(
            "Wizard artifact identity is missing. Reload the saved wizard."
        )
    return {
        "phase": phase,
        "thread_id": thread_id,
        "artifact_token": artifact_token,
    }


def _confirm_wizard_artifact_and_introduce(
    *,
    slot: int,
    data: Mapping[str, Any],
    result: Dict[str, Any],
    model: Optional[str],
) -> Dict[str, Any]:
    """Confirm the authoritative draft before requesting the next phase intro.

    A non-2xx confirmation answer keeps its code (``api_error``, or
    ``config_error`` for an access rejection) in the failed result.
    """
    failure_code: Optional[str] = None
    try:
        identity = _wizard_artifact_identity(data)
        response = _api_post(
            f"{get_api_url()}/api/story/new/setup/confirm",
            json={"slot": slot, **identity},
            timeout=_request_timeout_seconds(),
        )
        if not 200 <= response.status_code < 300:
            failure_code = _answer_failure_code(response)
            raise ValueError(f"Wizard confirmation failed: {response.text}")
        confirmed = response.json()
        next_phase = _WIZARD_PHASE_ENTERED_BY[identity["phase"]]
        if (
            not isinstance(confirmed, dict)
            or confirmed.get("status") != "confirmed"
            or confirmed.get("phase") != identity["phase"]
            or confirmed.get("next_phase") != next_phase
            or confirmed.get("thread_id") != identity["thread_id"]
        ):
            raise ValueError("Wizard confirmation returned an unexpected identity.")
    except (ValueError, requests.exceptions.RequestException) as exc:
        result.update(
            success=False,
            error=str(exc),
            recovery_command=f"nexus load --slot {slot}",
        )
        if failure_code is not None:
            result["code"] = failure_code
        return result

    # A failed or lost acknowledgement above never schedules another model turn.
    result.update(phase=next_phase, pending_confirmation=None, artifact_token=None)
    return _introduce_accepted_phase(
        slot=slot,
        thread_id=identity["thread_id"],
        accepted_phase=identity["phase"],
        next_phase=next_phase,
        result=result,
        model=model,
    )


def _introduce_accepted_phase(
    *,
    slot: int,
    thread_id: str,
    accepted_phase: str,
    next_phase: str,
    result: Dict[str, Any],
    model: Optional[str],
) -> Dict[str, Any]:
    """Request the introduction of a phase whose predecessor is already accepted.

    A non-2xx answer keeps its code (``api_error``, or ``config_error`` for an
    access rejection) in the failed result, beside its recovery command.
    """
    failure_code: Optional[str] = None
    payload = {
        "slot": slot,
        "thread_id": thread_id,
        "message": (
            f"[SYSTEM] Phase {accepted_phase} complete. "
            f"Proceeding to {next_phase}. Please introduce the next phase."
        ),
        "current_phase": next_phase,
        "message_origin": "wizard_control",
    }
    if model:
        payload["model"] = model
    try:
        response = _api_post(
            f"{get_api_url()}/api/story/new/chat",
            json=payload,
            timeout=_turn_request_timeout_seconds(),
        )
        if not 200 <= response.status_code < 300:
            failure_code = _answer_failure_code(response)
            raise ValueError(f"Next phase introduction failed: {response.text}")
        intro = response.json()
        if (
            not isinstance(intro, dict)
            or not isinstance(intro.get("message"), str)
            or not intro["message"].strip()
        ):
            raise ValueError("The next phase returned no introduction.")
        result.update(
            next_phase_intro=intro["message"], choices=intro.get("choices", [])
        )
    except (ValueError, requests.exceptions.RequestException) as exc:
        result.update(
            success=False,
            error=f"Artifact confirmed, but the next phase could not be loaded: {exc}",
            recovery_command=f"nexus load --slot {slot}",
        )
        if failure_code is not None:
            result["code"] = failure_code
    return result


def _start_wizard_character_revision(slot: int, state: Mapping[str, Any]) -> str:
    """Enter persisted concept revision before sending replacement player text.

    A non-2xx answer raises :class:`ApiAnswerFailure`; a missing or unexpected
    identity raises ValueError.
    """
    identity = _wizard_artifact_identity(state)
    response = _api_post(
        f"{get_api_url()}/api/story/new/setup/character/revise",
        json={
            "slot": slot,
            "thread_id": identity["thread_id"],
            "artifact_token": identity["artifact_token"],
        },
        timeout=_request_timeout_seconds(),
    )
    if not 200 <= response.status_code < 300:
        raise ApiAnswerFailure(
            _answer_failure_code(response),
            f"Character revision could not start: {response.text}",
            status_code=response.status_code,
        )
    revised = _api_answer(response)
    if (
        not isinstance(revised, dict)
        or revised.get("status") != "revision_started"
        or revised.get("phase") != "character"
        or revised.get("thread_id") != identity["thread_id"]
    ):
        raise ValueError("Character revision returned an unexpected identity.")
    return identity["thread_id"]


def _record_wizard_weird_level(slot: int, level: str) -> Optional[str]:
    """Save the new-story strangeness on the slot's wizard.

    Returns:
        None once the gateway saved ``level``, otherwise the failure detail.

    Raises:
        ApiAnswerFailure: The gateway answered a non-2xx status or a body that
            is not a JSON object.
    """
    response = _api_request(
        "put",
        f"{get_api_url()}/api/story/new/weird",
        json={"slot": slot, "weird_level": level},
        timeout=_request_timeout_seconds(),
    )
    if not 200 <= response.status_code < 300:
        detail = response.text.strip() or f"HTTP {response.status_code}"
        raise ApiAnswerFailure(
            _answer_failure_code(response),
            f"Failed to save --weird {level}: {detail}",
            status_code=response.status_code,
        )
    saved = _api_object(response).get("weird_level")
    if saved != level:
        return f"Failed to save --weird {level}: the wizard reports {saved!r}"
    return None


def run_continue(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Advance the story (wizard or narrative).

    Determines mode from slot state and calls the appropriate unified endpoint:
    - Wizard mode: /api/story/new/chat
    - Narrative mode: /api/narrative/continue
    """
    retrograde_info: Optional[Dict[str, Any]] = None
    # --weird belongs to the new-story wizard; direct callers may omit it.
    weird_level: Optional[str] = getattr(args, "weird", None)
    # First, get slot state to determine mode
    state_url = f"{get_api_url()}/api/slot/{args.slot}/state"
    state_response = _api_get(state_url, timeout=_request_timeout_seconds())
    state = _api_object(state_response)

    if weird_level is not None and not (
        state.get("is_empty") or state.get("is_wizard_mode")
    ):
        return {
            "success": False,
            "error": (
                f"--weird applies only to a new story; slot {args.slot} "
                "already holds a story in narrative mode."
            ),
        }

    if state.get("is_empty"):
        # Initialize via setup/start endpoint. Forward only an explicit
        # --model override; otherwise the backend preserves an
        # operator-set slot model or resolves the configured wizard
        # default for a fresh slot.
        setup_url = f"{get_api_url()}/api/story/new/setup/start"
        setup_payload = {"slot": args.slot}
        model_to_use = getattr(args, "model", None)
        if model_to_use:
            setup_payload["model"] = model_to_use
        setup_response = _api_post(
            setup_url, json=setup_payload, timeout=_request_timeout_seconds()
        )
        if not 200 <= setup_response.status_code < 300:
            return {
                "success": False,
                "code": _answer_failure_code(setup_response),
                "error": f"Failed to initialize wizard: {setup_response.text}",
            }

        # Use the actual response from the backend
        setup_data = _api_object(setup_response)
        if weird_level is not None:
            weird_error = _record_wizard_weird_level(args.slot, weird_level)
            if weird_error is not None:
                return {"success": False, "error": weird_error}
        return {
            "success": True,
            "message": setup_data.get("welcome_message")
            or f"Wizard initialized for slot {args.slot}.",
            "choices": setup_data.get("welcome_choices", []),
            "phase": "setting",
            "model": setup_data.get("model"),
        }

    if state.get("is_wizard_mode"):
        # Saved before any wizard step, so a call that does not reach the
        # transition still leaves the level for the one that does.
        if weird_level is not None:
            weird_error = _record_wizard_weird_level(args.slot, weird_level)
            if weird_error is not None:
                return {"success": False, "error": weird_error}
        transition_payload: Dict[str, Any] = {"slot": args.slot}
        if weird_level is not None:
            transition_payload["weird_level"] = weird_level
        revision_thread_id = None
        awaiting_introduction = state.get("awaiting_introduction")
        if (
            awaiting_introduction in _WIZARD_PHASE_ACCEPTED_BEFORE
            and not (args.user_text or "").strip()
            and args.choice is None
            and not args.accept_fate
            and not args.dev
        ):
            # The acceptance is durable; only its introduction is missing.
            thread_id = state.get("thread_id")
            if not isinstance(thread_id, str) or not thread_id.strip():
                return {
                    "success": False,
                    "error": "Wizard conversation identity is missing. "
                    "Reload the saved wizard.",
                }
            return _introduce_accepted_phase(
                slot=args.slot,
                thread_id=thread_id,
                accepted_phase=_WIZARD_PHASE_ACCEPTED_BEFORE[awaiting_introduction],
                next_phase=awaiting_introduction,
                result={
                    "success": True,
                    "phase": awaiting_introduction,
                    "pending_confirmation": None,
                },
                model=getattr(args, "model", None),
            )
        pending_confirmation = state.get("pending_confirmation")
        if pending_confirmation in {"setting", "character"}:
            if args.choice is not None:
                return {
                    "success": False,
                    "error": (
                        "A saved artifact awaits confirmation. Continue without "
                        "a choice to confirm it, or type a revision."
                    ),
                }
            if not (args.user_text or "").strip():
                if args.dev:
                    return {"success": False, "error": "Dev mode requires text."}
                return _confirm_wizard_artifact_and_introduce(
                    slot=args.slot,
                    data=state,
                    result={
                        "success": True,
                        "phase": pending_confirmation,
                        "phase_complete": True,
                        "pending_confirmation": pending_confirmation,
                        "artifact_token": state.get("artifact_token"),
                    },
                    model=getattr(args, "model", None),
                )
            if args.accept_fate:
                return {
                    "success": False,
                    "error": "Cannot combine a revision with --accept-fate.",
                }
            try:
                revision_thread_id = _wizard_artifact_identity(state)["thread_id"]
                if pending_confirmation == "character":
                    revision_thread_id = _start_wizard_character_revision(
                        args.slot, state
                    )
            except ValueError as exc:
                # A missing or unexpected artifact identity; a failed request
                # (ApiAnswerFailure) reaches main().
                return {"success": False, "error": str(exc)}
        # Check if wizard is ready for transition to narrative
        if state.get("phase") == "ready":
            # Call transition endpoint, then bootstrap. Retrograde
            # cold-start generation runs inside the transition, so the
            # timeout comes from orrery.retrograde.wizard settings.
            transition_url = f"{get_api_url()}/api/story/new/transition"
            with _echo_retrograde_stages(args.slot, enabled=not args.json):
                transition_response = _api_post(
                    transition_url,
                    json=transition_payload,
                    timeout=_transition_timeout_seconds(),
                )
            if not 200 <= transition_response.status_code < 300:
                return {
                    "success": False,
                    "code": _answer_failure_code(transition_response),
                    "error": f"Transition failed: {transition_response.text}",
                }
            retrograde_info = _api_object(transition_response).get("retrograde")

            # Transition complete - refresh state and continue to narrative
            state_response = _api_get(state_url, timeout=_request_timeout_seconds())
            state = _api_object(state_response)

            if state.get("is_wizard_mode"):
                return {
                    "success": False,
                    "error": "Transition completed but still in wizard mode",
                }

            # Continue to narrative mode handling below (don't return here)
        else:
            # A wizard choice is sent as its presented text; only narrative
            # mode records an edited choice. Refuse the mix rather than
            # silently dropping the typed text.
            if args.choice is not None and (args.user_text or "").strip():
                return {
                    "success": False,
                    "error": (
                        "Wizard mode takes --choice or --text, not both. "
                        "Send your own wording with --text alone."
                    ),
                }
            # Call wizard chat directly
            url = f"{get_api_url()}/api/story/new/chat"
            # Omission is meaningful: the backend resolves the slot's
            # locked model. Only forward an explicit CLI override.
            model_to_use = getattr(args, "model", None)

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
                            "Dev mode is not supported for trait selection toggles."
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

                response = _api_post(
                    url, json=payload, timeout=_turn_request_timeout_seconds()
                )
                data = _api_object(response)

                result = {
                    "success": True,
                    "message": data.get("message", ""),
                    "phase": data.get("phase"),
                    "subphase": data.get("subphase"),
                    "trait_menu": data.get("trait_menu"),
                    "can_confirm": data.get("can_confirm", False),
                    "subphase_complete": data.get("subphase_complete", False),
                }
                _apply_traits_to_wildcard_transition(
                    url=url,
                    slot=args.slot,
                    data=data,
                    result=result,
                    model=model_to_use,
                )
                return result

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
                            f"Choice {args.choice} out of range (1-{len(choices)})"
                        ),
                    }

            payload = {
                "slot": args.slot,
                "message": user_text,
                "accept_fate": args.accept_fate,
                # thread_id and current_phase resolved by backend
            }
            if revision_thread_id is not None:
                payload["thread_id"] = revision_thread_id
            if args.dev and args.accept_fate:
                return {
                    "success": False,
                    "error": "Cannot combine --dev with --accept-fate.",
                }
            if not user_text.strip() and not args.accept_fate:
                return {
                    "success": False,
                    "error": (
                        "Wizard continue requires non-empty text, --choice, "
                        "or --accept-fate."
                    ),
                }
            if args.dev:
                payload["dev"] = True
            if model_to_use:
                payload["model"] = model_to_use

            response = _api_post(
                url, json=payload, timeout=_turn_request_timeout_seconds()
            )
            data = _api_object(response)

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
                "subphase_complete": data.get("subphase_complete", False),
                "pending_confirmation": data.get("pending_confirmation"),
                "artifact_token": data.get("artifact_token"),
            }

            _apply_traits_to_wildcard_transition(
                url=url,
                slot=args.slot,
                data=data,
                result=result,
                model=model_to_use,
            )

            # Auto-transition: if phase completed, trigger next phase intro
            if data.get("phase_complete"):
                current_phase = data.get("phase")
                next_phase = (
                    _get_next_phase(current_phase)
                    if isinstance(current_phase, str)
                    else None
                )

                if next_phase and next_phase != "ready":
                    return _confirm_wizard_artifact_and_introduce(
                        slot=args.slot,
                        data=data,
                        result=result,
                        model=model_to_use,
                    )

                elif next_phase == "ready":
                    # Seed phase complete → transition to narrative mode
                    transition_url = f"{get_api_url()}/api/story/new/transition"
                    try:
                        with _echo_retrograde_stages(args.slot, enabled=not args.json):
                            transition_response = _api_post(
                                transition_url,
                                json=transition_payload,
                                timeout=_transition_timeout_seconds(),
                            )
                    except (
                        requests.exceptions.ConnectionError,
                        requests.exceptions.ChunkedEncodingError,
                        requests.exceptions.Timeout,
                    ) as exc:
                        # Classified as the wait's reads are, the saved
                        # seed kept either way: an answer that ran out of
                        # time, a body stalled after its headers included,
                        # is a domain failure (exit 1); a refused or
                        # dropped connection is api_unreachable (exit 4).
                        failure = _failed_session_read(
                            exc,
                            transition_url,
                            str(exc) or "Transition request timed out.",
                        )
                        return _seed_transition_failure(
                            result=result,
                            slot=args.slot,
                            detail=failure.detail,
                            status_code=None,
                            status=failure.status,
                            code=failure.code,
                        )
                    if not 200 <= transition_response.status_code < 300:
                        detail = transition_response.text.strip() or (
                            "Transition request failed with HTTP "
                            f"{transition_response.status_code}."
                        )
                        return _seed_transition_failure(
                            result=result,
                            slot=args.slot,
                            detail=detail,
                            status_code=transition_response.status_code,
                            status="http_error",
                            code=_answer_failure_code(transition_response),
                        )
                    try:
                        transition = _api_object(transition_response)
                    except ApiAnswerFailure as exc:
                        return _seed_transition_failure(
                            result=result,
                            slot=args.slot,
                            detail=exc.message,
                            status_code=transition_response.status_code,
                            status="invalid_response",
                            code="invalid_response",
                        )
                    result["retrograde"] = transition.get("retrograde")
                    return _bootstrap_seed_narrative(
                        result=result, slot=args.slot, model=model_to_use
                    )

            return result

    # Narrative mode - call continue directly
    # (Also reached after wizard transition above)
    if not state.get("is_wizard_mode"):
        # Narrative mode - call continue directly
        # The API already resolves the persisted slot model. Sending a
        # model is an explicit override and must remain opt-in.
        # --choice with --text is one edited-choice payload: the server
        # keeps the number and records the text when it differs.
        model_to_use = getattr(args, "model", None)
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

        response = _api_post(url, json=payload, timeout=_turn_request_timeout_seconds())
        data = _api_object(response)

        # Wait for generation to complete and fetch result
        session_id = data.get("session_id")
        if session_id:
            terminal_result = _wait_for_narrative_result(args.slot, session_id)
            if retrograde_info:
                terminal_result["retrograde"] = retrograde_info
            return terminal_result

        no_session_result = {
            "success": True,
            "message": data.get("message"),
            "session_id": session_id,
        }
        if retrograde_info:
            no_session_result["retrograde"] = retrograde_info
        return no_session_result

    return {
        "success": False,
        "error": "Slot state was neither wizard nor narrative mode",
    }


def run_retry(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Explicitly retry the failed continuation that slot state advertises.

    Reads GET /api/slot/{slot}/state, sends its ``recovery.session_id`` as
    ``expected_session_id`` to POST /api/narrative/retry (which resumes the
    recorded action without recording it again and fences a stale session),
    then waits for and loads the new turn exactly as ``nexus continue`` does.
    A recovery or retry answer without a session ID is ``invalid_response``.
    """
    state_url = f"{get_api_url()}/api/slot/{args.slot}/state"
    state_response = _api_get(state_url, timeout=_request_timeout_seconds())
    recovery = _api_object(state_response).get("recovery")
    if not recovery:
        return {
            "success": False,
            "error": f"Slot {args.slot} has no failed continuation to retry.",
        }
    if not isinstance(recovery, dict):
        raise ApiAnswerFailure(
            "invalid_response",
            f"{state_url} returned a recovery that is not a JSON object: "
            f"{recovery!r}",
        )
    expected_session_id = recovery.get("session_id")
    if not isinstance(expected_session_id, str) or not expected_session_id:
        raise ApiAnswerFailure(
            "invalid_response", f"{state_url} returned a recovery with no session ID"
        )

    retry_url = f"{get_api_url()}/api/narrative/retry"
    response = _api_post(
        retry_url,
        json={"slot": args.slot, "expected_session_id": expected_session_id},
        timeout=_turn_request_timeout_seconds(),
    )
    session_id = _api_object(response).get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ApiAnswerFailure(
            "invalid_response", f"{retry_url} returned no session ID"
        )
    return _wait_for_narrative_result(args.slot, session_id)


def run_undo(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Undo the last action.

    Calls POST /api/slot/{slot}/undo.
    """
    url = f"{get_api_url()}/api/slot/{args.slot}/undo"

    response = _api_post(url, timeout=_request_timeout_seconds())
    data = _api_object(response)

    success = data.get("success", True)
    message = data.get("message")
    if not success:
        # Surface the API's reason via "error" so main() prints something
        # informative instead of the generic "Unknown error" fallback.
        return {"success": False, "error": message or "Undo failed"}
    return {"success": True, "message": message}


def run_regenerate(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Regenerate the last storyteller turn for a slot.

    Calls POST /api/narrative/regenerate, then waits on the new session and
    loads the replacement draft exactly as ``nexus continue`` does.
    """
    url = f"{get_api_url()}/api/narrative/regenerate"
    payload: Dict[str, Any] = {"slot": args.slot}
    if args.note:
        payload["note"] = args.note

    response = _api_post(url, json=payload, timeout=_turn_request_timeout_seconds())
    data = _api_object(response)

    session_id = data.get("session_id")
    if not session_id:
        return {"success": False, "error": "No session ID returned from regenerate"}

    return _wait_for_narrative_result(args.slot, session_id)


def run_model(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Get or set the model for a slot.

    Read seat identities directly; change pins through PATCH /api/slot/{slot}/settings.
    A slot database the read cannot open or query is ``database_error``; a
    story pin naming a model no longer registered is a domain failure whose
    error names the remedy.
    """
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
    base_url = f"{get_api_url()}/api/slot/{args.slot}/settings"

    if args.set or getattr(args, "clear", False):
        # Set the model
        response = _api_request(
            "patch",
            base_url,
            json={"skald_model": args.set},
            timeout=_request_timeout_seconds(),
        )
        data = _api_object(response)
        return {
            "success": True,
            "message": f"Model changed to {data.get('skald_model')}",
            "model": data.get("skald_model"),
        }

    # Read-only diagnostics do not require a running gateway.
    from dataclasses import asdict

    from nexus.api.slot_utils import slot_dbname
    from nexus.config import load_settings
    from nexus.config.story_model import (
        AUXILIARY_SEATS,
        read_story_settings,
        resolve_seat,
    )

    import psycopg2

    settings = load_settings()
    try:
        story = read_story_settings(slot_dbname(args.slot))
    except psycopg2.Error as exc:
        return {"success": False, "code": "database_error", "error": str(exc)}
    story.slot = args.slot
    try:
        seats = [
            resolve_seat(seat, settings=settings, story=story)
            for seat in ("skald", "gaia", "wizard", *AUXILIARY_SEATS)
        ]
    except ValueError as exc:
        # A story pin naming an unregistered model; the error names the remedy.
        return {"success": False, "error": str(exc)}
    return {
        "success": True,
        "message": "\n".join(
            f"{item.seat} {item.policy} {item.model} {item.source}" for item in seats
        ),
        "model": story.skald_model,
        "seats": [asdict(item) for item in seats],
    }


def run_clear(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Clear a slot (reset wizard state).

    Calls POST /api/story/new/setup/reset.
    """
    url = f"{get_api_url()}/api/story/new/setup/reset"
    response = _api_post(
        url, json={"slot": args.slot}, timeout=_request_timeout_seconds()
    )
    _check_answer(response)
    return {
        "success": True,
        "message": f"Slot {args.slot} cleared",
    }


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

    from nexus.agents.orrery.retrograde_seed_candidates import run_seed_stage

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

    generation = run_seed_stage(
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

    from nexus.agents.orrery.retrograde_embedding import (
        embed_retrograde_summaries,
    )
    from nexus.agents.orrery.retrograde_persistence import (
        build_retrograde_persistence_plan,
        find_latest_playable_chunk_id,
    )
    from nexus.api.db_pool import get_connection
    from nexus.api.slot_utils import slot_dbname
    from nexus.config import load_settings

    try:
        packet = _load_retrograde_packet_file(args.packet)
        seed_candidates = _load_seed_candidate_file(args.seed_candidates)
        expansion_plan = _load_retrograde_expansion_file(args.expansion)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"success": False, "error": str(exc)}

    orrery_settings = load_settings().orrery
    if orrery_settings is None:
        return {
            "success": False,
            "error": (
                "nexus.toml is missing the [orrery] section required for "
                "Retrograde retrieval settings"
            ),
        }
    retrieval_settings = orrery_settings.retrograde.retrieval
    dbname = slot_dbname(args.slot)
    dry_run = not args.execute
    try:
        with get_connection(dbname, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                if dry_run:
                    cur.execute("SET TRANSACTION READ ONLY")
                recorded_at_chunk_id = find_latest_playable_chunk_id(cur)
                persistence = build_retrograde_persistence_plan(
                    cur,
                    packet=packet,
                    seed_candidate_response=seed_candidates,
                    expansion_plan_payload=expansion_plan,
                    slot=args.slot,
                    dbname=dbname,
                    dry_run=dry_run,
                    create_missing_entities=args.create_stubs,
                    summaries_enabled=retrieval_settings.summaries_enabled,
                    recorded_at_chunk_id=recorded_at_chunk_id,
                    epistemics_settings=orrery_settings.epistemics,
                )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    embedding_results: List[Dict[str, Any]] = []
    pending_summary_ids = list(
        persistence.get("retrieval", {}).get("embedding_pending_summary_ids", [])
    )
    if not dry_run and retrieval_settings.embed_after_apply and pending_summary_ids:
        try:
            embedding_results = embed_retrograde_summaries(dbname, pending_summary_ids)
        except RuntimeError as exc:
            return {
                "success": False,
                "error": str(exc),
                "retrograde_persistence": persistence,
            }

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
        "retrograde_embedding": embedding_results,
        "persistence_output": str(output_path) if output_path is not None else None,
    }


def run_retrograde_embed_history(args: argparse.Namespace) -> Dict[str, Any]:
    """Ensure and embed dedicated summaries for persisted Retrograde history."""

    from nexus.agents.orrery.retrograde_embedding import (
        embed_retrograde_summaries,
    )
    from nexus.agents.orrery.retrograde_persistence import (
        plan_retrograde_summaries,
    )
    from nexus.api.db_pool import get_connection
    from nexus.api.slot_utils import slot_dbname
    from nexus.config import load_settings

    orrery_settings = load_settings().orrery
    if orrery_settings is None:
        return {
            "success": False,
            "error": (
                "nexus.toml is missing the [orrery] section required for "
                "Retrograde retrieval settings"
            ),
        }
    retrieval_settings = orrery_settings.retrograde.retrieval
    if not retrieval_settings.summaries_enabled:
        return {
            "success": False,
            "error": (
                "orrery.retrograde.retrieval.summaries_enabled is disabled in "
                "nexus.toml; enable it before embedding Retrograde history"
            ),
        }

    dbname = slot_dbname(args.slot)
    dry_run = not args.execute
    try:
        with get_connection(dbname, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                if dry_run:
                    cur.execute("SET TRANSACTION READ ONLY")
                summary_rows = plan_retrograde_summaries(
                    cur,
                    dry_run=dry_run,
                )
    except (ValueError, RuntimeError) as exc:
        return {"success": False, "error": str(exc)}

    pending_summary_ids = [
        int(row["summary_id"])
        for row in summary_rows
        if row["embedding_pending"] and row["summary_id"] is not None
    ]
    embedding_results: List[Dict[str, Any]] = []
    if not dry_run and pending_summary_ids:
        try:
            embedding_results = embed_retrograde_summaries(dbname, pending_summary_ids)
        except RuntimeError as exc:
            return {
                "success": False,
                "error": str(exc),
                "summary_rows": summary_rows,
            }

    mode = "dry run" if dry_run else "executed"
    return {
        "success": True,
        "message": (
            f"Retrograde history retrieval sync for slot {args.slot} ({mode})."
        ),
        "slot": args.slot,
        "dbname": dbname,
        "retrograde_embed_history": {
            "dry_run": dry_run,
            "summary_rows": summary_rows,
            "embedding_pending_summary_ids": pending_summary_ids,
            "embedding_results": embedding_results,
        },
    }


def run_record_revelation(
    args: argparse.Namespace, *, connection: Optional[Any] = None
) -> Dict[str, Any]:
    """Record an explicit told or manual claim-awareness grant."""

    from nexus.agents.orrery.epistemics import (
        EpistemicsValidationError,
        current_world_time_sync,
        record_revelation,
    )
    from nexus.api.db_pool import get_connection
    from nexus.api.slot_utils import slot_dbname

    world_time = None
    if args.world_time is not None:
        world_time = parse_record_revelation_world_time(args.world_time)
    dbname = slot_dbname(args.slot)

    def apply(conn: Any) -> tuple[Optional[Any], Optional[str]]:
        with conn.cursor() as cur:
            resolved_world_time = world_time
            if resolved_world_time is None:
                resolved_world_time = current_world_time_sync(cur)
            try:
                revelation = record_revelation(
                    cur,
                    claim_id=args.claim_id,
                    knower_entity_id=args.knower,
                    source_entity_id=args.source_entity_id,
                    channel=args.channel,
                    world_time=resolved_world_time,
                    source_chunk_id=args.source_chunk_id,
                )
            except EpistemicsValidationError as exc:
                return None, str(exc)
            return revelation, None

    if connection is None:
        with get_connection(dbname, dict_cursor=True) as conn:
            revelation, validation_error = apply(conn)
    else:
        revelation, validation_error = apply(connection)
    if validation_error is not None:
        return {"success": False, "error": validation_error}
    if revelation is None:
        raise RuntimeError("Record-revelation validation produced no result")
    message = (
        f"Granted awareness for claim {args.claim_id} "
        f"(tier: {revelation.source_tier})."
        if revelation.inserted
        else (
            f"Claim {args.claim_id} is already known by entity "
            f"{args.knower}; unchanged."
        )
    )
    return {
        "success": True,
        "message": message,
        "slot": args.slot,
        "dbname": dbname,
        "claim_id": args.claim_id,
        "knower_entity_id": args.knower,
        "claim_awareness_id": revelation.awareness_id,
        "source_tier": revelation.source_tier,
        "inserted": revelation.inserted,
    }


def parse_record_revelation_world_time(value: str) -> datetime:
    """Parse one timezone-aware ISO-8601 revelation timestamp."""

    message = f"--world-time must be a timezone-aware ISO-8601 datetime, got {value!r}"
    try:
        world_time = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(message) from exc
    if world_time.tzinfo is None or world_time.utcoffset() is None:
        raise ValueError(message)
    return world_time


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
    url = f"{get_api_url()}/api/slot/{args.slot}/lock"
    response = _api_post(url, timeout=_request_timeout_seconds())
    _check_answer(response)
    return {
        "success": True,
        "message": f"Slot {args.slot} locked",
    }


def run_unlock(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Unlock a slot to allow modifications.

    Calls POST /api/slot/{slot}/unlock.
    """
    url = f"{get_api_url()}/api/slot/{args.slot}/unlock"
    response = _api_post(url, timeout=_request_timeout_seconds())
    _check_answer(response)
    return {
        "success": True,
        "message": f"Slot {args.slot} unlocked",
    }


# =============================================================================
# Managed runtime verbs (issue #396): up / down / restart / status / logs
# =============================================================================


def _runtime_supervisor(args: argparse.Namespace):
    from nexus.runtime import Supervisor

    return Supervisor.from_config(getattr(args, "config", None))


def run_up(args: argparse.Namespace) -> Dict[str, Any]:
    """Start the runtime per the configured profile."""
    from nexus.runtime import RuntimeError_

    try:
        supervisor = _runtime_supervisor(args)
        return supervisor.up(
            slot=args.slot,
            foreground=args.foreground,
            echo=not args.json,
        )
    except _TRANSPORT_ERRORS:
        # An unreachable remote runtime is api_unreachable (exit 4) and a
        # missing or refused credential config_error, reported by main().
        raise
    except (
        RuntimeError_,
        FileNotFoundError,
        ValueError,
        requests.RequestException,
    ) as exc:
        return {"success": False, "error": str(exc)}


def run_down(args: argparse.Namespace) -> Dict[str, Any]:
    """Stop managed services and remove pidfiles."""
    from nexus.runtime import RuntimeError_

    try:
        supervisor = _runtime_supervisor(args)
        result = supervisor.down(service=args.service)
        if not args.json:
            stopped = result.get("stopped", {})
            if stopped:
                for name, info in stopped.items():
                    print(f"stopped {name} (pid {info['pid']})")
            else:
                print("nothing running")
        return result
    except (RuntimeError_, FileNotFoundError) as exc:
        return {"success": False, "error": str(exc)}


def run_restart(args: argparse.Namespace) -> Dict[str, Any]:
    """Restart all managed services, or one by name."""
    from nexus.runtime import RuntimeError_

    try:
        supervisor = _runtime_supervisor(args)
        result = supervisor.restart(service=args.service, slot=args.slot)
        if not args.json:
            for name, record in result.get("services", {}).items():
                print(f"restarted {name} (pid {record['pid']})")
        return result
    except (RuntimeError_, FileNotFoundError, requests.RequestException) as exc:
        return {"success": False, "error": str(exc)}


def _format_uptime(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def _print_runtime_status(result: Dict[str, Any]) -> None:
    runtime = result.get("runtime") or {}
    print(f"NEXUS runtime - profile {result['profile']} - {result['gateway_url']}")
    rows = []
    health_by_service = runtime.get("services", {})
    for name, proc in (result.get("processes") or {}).items():
        health = health_by_service.get(name, {})
        rows.append(
            (
                name,
                proc.get("state", "-"),
                str(proc.get("pid", "-")),
                str(proc.get("port", "-")),
                (
                    _format_uptime(proc["uptime_seconds"])
                    if proc.get("uptime_seconds") is not None
                    else "-"
                ),
                "ok" if health.get("ok") else ("fail" if health else "-"),
                proc.get("log_writer", "-"),
            )
        )
    if not rows:
        # external/remote: render gateway health from the runtime endpoint
        for name, health in health_by_service.items():
            rows.append(
                (
                    name,
                    "-",
                    "-",
                    str(health.get("port", "-")),
                    "-",
                    "ok" if health.get("ok") else "fail",
                    "-",
                )
            )
    database = runtime.get("database") or {}
    rows.append(
        (
            "database",
            "-",
            "-",
            "-",
            "-",
            (
                f"ok ({database.get('dbname')})"
                if database.get("ok")
                else f"fail ({database.get('error', 'unknown')})"
            ),
            "-",
        )
    )
    header = ("SERVICE", "STATE", "PID", "PORT", "UPTIME", "HEALTH", "WRITER")
    widths = [
        max(len(str(row[i])) for row in [header] + rows) for i in range(len(header))
    ]
    for row in [header] + rows:
        print("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
    for client, target in database.get("targets", {}).items():
        host = target["host"] or "(default Unix socket)"
        print(
            f"database {client}: {target['user']}@{host}:{target['port']}/{target['dbname']}"
        )
    if runtime.get("error"):
        print(f"runtime endpoint: {runtime['error']}")
    else:
        auth = runtime.get("auth", {})
        print(
            f"version {runtime.get('version', '?')} - slot "
            f"{runtime.get('slot', '?')} - auth {auth.get('header', '?')}"
            f"{'' if auth.get('enforced') else ' (not enforced)'}"
        )

    if runtime.get("jobs"):
        _print_jobs({"slot": runtime.get("slot"), **runtime["jobs"]})


def run_status(args: argparse.Namespace) -> Dict[str, Any]:
    """Render supervisor process state plus the gateway's /runtime/status."""
    from nexus.runtime import RuntimeError_

    try:
        supervisor = _runtime_supervisor(args)
        result = supervisor.status()
        if not args.json:
            _print_runtime_status(result)
        return result
    except (
        RuntimeError_,
        FileNotFoundError,
        MissingSecretError,
        SecretStoreAccessError,
        ValueError,
    ) as exc:
        return {"success": False, "error": str(exc)}


def run_logs(args: argparse.Namespace) -> Dict[str, Any]:
    """Tail captured service logs; -f follows."""
    from nexus.runtime import RuntimeError_

    if args.json and args.follow:
        return {"success": False, "error": "--json cannot be combined with -f"}
    if args.mark or args.since is not None:
        return _run_log_mark(args)
    try:
        supervisor = _runtime_supervisor(args)
        stream = supervisor.logs(
            service=args.service, lines=args.lines, follow=args.follow
        )
        if args.json:
            return {"success": True, "service": args.service, "lines": list(stream)}
        try:
            for line in stream:
                print(line)
        except KeyboardInterrupt:
            pass
        return {"success": True}
    except (RuntimeError_, FileNotFoundError) as exc:
        return {"success": False, "error": str(exc)}


def _run_log_mark(args: argparse.Namespace) -> Dict[str, Any]:
    """``nexus logs --mark`` and ``--since MARK``: slice a capture by a mark."""
    from nexus.runtime import RuntimeError_

    flag = "--mark" if args.mark else "--since"
    if args.mark and args.since is not None:
        return {"success": False, "error": "--mark cannot be combined with --since"}
    if args.follow:
        return {"success": False, "error": f"{flag} cannot be combined with -f"}
    if args.lines is not None:
        return {"success": False, "error": f"{flag} cannot be combined with -n"}
    try:
        supervisor = _runtime_supervisor(args)
        if args.mark:
            mark = supervisor.log_mark(args.service)
            if args.json:
                return {"success": True, "service": args.service, "mark": mark}
            print(mark)
            return {"success": True}
        lines = supervisor.logs_since(args.service, args.since)
        if args.json:
            return {"success": True, "service": args.service, "lines": lines}
        for line in lines:
            print(line)
        return {"success": True}
    except (
        RuntimeError_,
        FileNotFoundError,
    ) as exc:  # nexus-exception-disposition: fail; reason=logs; safety=error result
        return {"success": False, "error": str(exc)}


def run_home(args: argparse.Namespace) -> Dict[str, Any]:
    """Dry-run the move of the checkout's runtime data into a runtime home."""
    from nexus.runtime.home import RuntimeHomeError
    from nexus.runtime.home_plan import HomePlanError, plan_home_move

    try:
        plan = plan_home_move(args.target)
    except (RuntimeHomeError, HomePlanError, FileNotFoundError) as exc:
        return {"success": False, "error": str(exc)}
    if not args.json:
        for line in plan.render():
            print(line)
    return {"success": True, "home_plan": plan.as_dict()}


def run_doctor(args: argparse.Namespace) -> int:
    """Run one role's read-only readiness checks; exit 1 if any check fails."""
    from nexus.runtime.readiness import (
        ReadinessContext,
        render_report,
        run_readiness,
    )

    config = Path(args.config) if args.config else None
    report = run_readiness(args.target, ReadinessContext(config_path=config))
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        for line in render_report(report):
            print(line)
    return 0 if report.ok else 1


def _receipt_detail_text(details: Mapping[str, Any]) -> str:
    """One line of ``key=value`` pairs; structured values as compact JSON."""
    return " ".join(
        (
            f"{key}={value}"
            if value is None or isinstance(value, (str, int))
            else f"{key}={json.dumps(value, separators=(',', ':'))}"
        )
        for key, value in details.items()
    )


def _render_receipt_group(group: Any) -> List[str]:
    """Text lines for one fingerprint group of failure receipts."""
    first = group.first
    lines = [
        f"{group.count}x {group.fingerprint[:12]} {first.surface} "
        f"{first.exception_module}.{first.exception_type} "
        f"first {group.first_seen.isoformat()} last {group.last_seen.isoformat()} "
        f"{','.join(group.roots)}"
    ]
    if first.config_path is not None:
        lines.append(f"  config_path={first.config_path}")
    if first.details is not None:
        details = first.details.model_dump(mode="json")
        lines.append(f"  {_receipt_detail_text(details)}")
    lines.extend(
        f"  {frame.file}:{frame.line} {frame.function}" for frame in first.frames
    )
    return lines


def run_receipts(args: argparse.Namespace) -> int:
    """Show this machine's failure receipts grouped by fingerprint (read-only).

    The home receipt directory is located first; when the locator fails, its
    own ``runtime.home`` receipt has just been appended to the fallback root,
    and the read (fallback only) includes it before ``config_error`` is
    reported.
    """
    from nexus.runtime.receipts import (
        ReceiptConfigurationError,
        ReceiptReadError,
        fallback_receipts_dir,
        home_receipts_dir,
        read_failure_groups,
    )

    home_dir: Optional[Path]
    home_error: Optional[str] = None
    try:
        try:
            home_dir = home_receipts_dir()
        # The fallback root is read, and the command exits with config_error.
        except (
            RuntimeHomeError
        ):  # nexus-exception-disposition: degrade-read-only; reason=home; safety=exit1
            home_dir = None
            home_error = str(sys.exc_info()[1])
        fallback_dir = fallback_receipts_dir()
    except (
        ReceiptConfigurationError
    ) as exc:  # nexus-exception-disposition: fail; reason=bad seam; safety=exit 1
        return _fail(args, "config_error", str(exc))
    roots = {"fallback": fallback_dir}
    # When NEXUS_HOME is the user's home, both labels name one directory;
    # reading it once keeps each receipt counted once.
    if home_dir is not None and home_dir.resolve() != fallback_dir.resolve():
        roots = {"home": home_dir, "fallback": fallback_dir}
    try:
        groups = read_failure_groups(roots)
    except (
        ReceiptReadError
    ) as exc:  # nexus-exception-disposition: fail; reason=bad line; safety=exit 1
        return _fail(args, "domain_failure", str(exc))

    document = {
        "home_dir": None if home_dir is None else str(home_dir),
        "fallback_dir": str(fallback_dir),
        "groups": [group.model_dump(mode="json") for group in groups],
    }
    if args.json:
        if home_error is None:
            print(json.dumps(document, indent=2, sort_keys=True))
    else:
        for group in groups:
            for line in _render_receipt_group(group):
                print(line)
    if home_error is not None:
        return _fail(
            args,
            "config_error",
            f"home receipts unavailable: {home_error}",
            partial=document,
        )
    return 0


def run_usage(args: argparse.Namespace) -> Dict[str, Any]:
    """Return provider usage and rendered blocks for one UTC day or run."""
    from nexus.telemetry.usage import read_prompt_windows, summarize_usage

    usage = summarize_usage(day=args.day, run_id=args.run)
    result = {"success": True, "usage": usage}
    windows = (
        [record.model_dump() for record in read_prompt_windows(args.run, usage["day"])]
        if args.run
        else []
    )
    if windows:
        result["windows"] = windows
    return result


def run_window_replay(args: argparse.Namespace) -> Dict[str, Any]:
    """Replay one run's recorded prompt windows under candidate settings."""
    from datetime import timezone

    from nexus.telemetry.usage import validate_usage_day
    from nexus.telemetry.window_replay import NoPromptWindowsError, replay_run

    day = args.day or datetime.now(timezone.utc).date().isoformat()
    try:
        validate_usage_day(day)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    # load_settings validates the candidate TOML against the Pydantic models.
    baseline = load_settings()
    settings = load_settings(args.config) if args.config else baseline
    try:
        rows = replay_run(
            args.run,
            day,
            settings,
            baseline=baseline,
            model=args.model,
            window=args.window,
        )
    except NoPromptWindowsError as exc:
        return {"success": False, "error": str(exc)}
    return {
        "success": True,
        "window_replay": {
            "run": args.run,
            "day": day,
            "config": args.config,
            "rows": [row.model_dump() for row in rows],
        },
    }


def _print_window_replay(replay: Dict[str, Any]) -> None:
    """Render one replayed attempt per line, in tokens."""
    header = (
        "SEAT",
        "ATTEMPT",
        "MODEL",
        "INPUT",
        "CEILING",
        "CANDIDATE",
        "CAPPED",
        "DELTA",
        "OVERFLOW",
        "TRIMMABLE",
        "FEASIBLE",
        "FREED",
        "REMOVED",
    )
    values = [
        (
            row["seat"],
            row["attempt"],
            row["candidate_model"],
            row["recorded_input_tokens"],
            row["recorded_ceiling"],
            row["candidate_ceiling"],
            "yes" if row["capped"] else "no",
            f"{row['headroom_delta']:+}",
            row["overflow_tokens"],
            row["trimmable_tokens"],
            "yes" if row["feasible"] else "no",
            row["freed_tokens"],
            (
                row["removed_tokens_total"]
                if row["removed_tokens_total"] is not None
                else "unknown"
            ),
        )
        for row in replay["rows"]
    ]
    widths = [
        max(len(str(row[index])) for row in [header] + values)
        for index in range(len(header))
    ]
    print(f"Run {replay['run']} (UTC day {replay['day']})")
    for index, row in enumerate([header] + values):
        cells = (str(cell).ljust(widths[i]) for i, cell in enumerate(row))
        print("  ".join(cells).rstrip())
        if index:
            _print_removed_tokens(replay["rows"][index - 1])


def run_inspect_turn(args: argparse.Namespace) -> Dict[str, Any]:
    """Inspect durable turn references; JSON and summary reads join the ledgers."""
    from contextlib import closing
    from nexus.api.slot_utils import get_slot_db_url
    from nexus.telemetry.attempt_manifest import inspect_turn
    import psycopg2

    with closing(psycopg2.connect(get_slot_db_url(slot=args.slot))) as conn:
        result = inspect_turn(conn, session=args.session, chunk=args.chunk)
    payload: Dict[str, Any] = {
        "success": True,
        "slot": args.slot,
        "turn_inspection": result,
    }
    # The table read never depends on the usage and prompt-window ledgers.
    if args.json or args.summary:
        from nexus.telemetry.turn_observation import observe_turn

        payload["observation"] = observe_turn(result, slot=args.slot)
    return payload


def run_prune_manifests(args: argparse.Namespace) -> Dict[str, Any]:
    """Explicitly apply configured manifest retention to one writable slot."""
    from contextlib import closing
    from nexus.api.slot_utils import get_slot_db_url
    from nexus.api.slot_mutations import require_writable_slot
    from nexus.config import load_settings
    from nexus.telemetry.attempt_manifest import prune_manifests
    import psycopg2

    require_writable_slot(args.slot)
    days = load_settings().usage.manifest_retention_days
    with closing(psycopg2.connect(get_slot_db_url(slot=args.slot))) as conn:
        count = prune_manifests(conn, days)
    return {
        "success": True,
        "slot": args.slot,
        "retention_days": days,
        "manifests_pruned": count,
    }


def run_tags_audit(args: argparse.Namespace) -> Dict[str, Any]:
    """Report active entity tags in deprecated registry categories, read-only.

    ``--slot N`` reads one slot; ``--all`` reads ``NEXUS_template`` and every
    slot, locked ones included. Each database is read in one read-only
    transaction and nothing is written. A database that lacks the registry
    schema, or cannot be reached, stops the audit as a domain failure that
    keeps the databases already read.
    """
    import psycopg2

    from nexus.api.deprecated_tag_audit import (
        DeprecatedTagAuditError,
        audit_database,
        audit_database_names,
    )

    databases: List[Dict[str, Any]] = []
    for dbname in audit_database_names(None if args.all else args.slot):
        try:
            databases.append(audit_database(dbname))
        except DeprecatedTagAuditError as exc:
            return {"success": False, "error": str(exc), "databases": databases}
        except psycopg2.OperationalError as exc:
            message = " ".join(str(exc).split())
            return {
                "success": False,
                "error": f"Cannot read {dbname}: {message}",
                "databases": databases,
            }
    return {
        "success": True,
        "data": {
            "active_rows": sum(entry["active_rows"] for entry in databases),
            "databases": databases,
        },
    }


def _print_tags_audit(data: Mapping[str, Any]) -> None:
    """Print each database's row count, then one line per category and tag."""
    databases = data["databases"]
    totals = [("DATABASE", "ROWS")] + [
        (entry["database"], str(entry["active_rows"])) for entry in databases
    ]
    _print_table(totals)
    groups = [
        (
            entry["database"],
            group["category"],
            group["tag"],
            str(group["row_count"]),
            ",".join(str(entity_id) for entity_id in group["entity_ids"]),
            ",".join(group["replacement_categories"]) or "-",
        )
        for entry in databases
        for group in entry["groups"]
    ]
    if groups:
        print()
        _print_table(
            [("DATABASE", "CATEGORY", "TAG", "ROWS", "ENTITIES", "REPLACEMENTS")]
            + groups
        )


def _print_table(rows: Sequence[Sequence[str]]) -> None:
    """Print rows as left-aligned columns separated by two spaces."""
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())


def _print_turn_inspection(turn: Dict[str, Any]) -> None:
    """Print compact metadata tables; --json retains complete blocks and hashes."""
    session = turn["session"]
    print("Session\tPhase\tOutcome\tAccepted Chunk\tReplacement")
    print(
        "\t".join(
            str(session[key] or "-")
            for key in (
                "session_id",
                "phase",
                "terminal_outcome",
                "accepted_chunk_id",
                "replaced_by_session_id",
            )
        )
    )
    print("Phase\tRecorded At")
    for row in turn["phases"]:
        print(f"{row['phase']}\t{row['recorded_at']}")
    print(
        "Seat\tAttempt\tModel\tTokens\tWindow\tBlocks\tValidation Notes\tRepair Codes\tProvider Outcome\tOutcome"
    )
    for row in turn["manifests"]:
        window = row["window_record"]
        print(
            "\t".join(
                map(
                    str,
                    (
                        row["seat"],
                        row["attempt"],
                        row["model_id"],
                        window["input_tokens"],
                        window["effective_ceiling"],
                        len(row["blocks"]),
                        len(row["validation"]),
                        ",".join(
                            note["repair"]
                            for note in row["validation"]
                            if "repair" in note
                        )
                        or "-",
                        row["provider_outcome"] or "-",
                        row["outcome"] or "-",
                    ),
                )
            )
        )
    print(
        "Seat\tAttempt\tSchema\tStory Pin\tConfig SHA-256/12\tWire SHA-256/12\tPrompt SHA-256/12\tResponse SHA-256/12"
    )
    for row in turn["manifests"]:
        print(
            "\t".join(
                map(
                    str,
                    (
                        row["seat"],
                        row["attempt"],
                        row["schema_version"],
                        json.dumps(row["story_pin"], sort_keys=True),
                        row["config_sha256"][:12],
                        row["wire_schema_sha256"][:12],
                        row["prompt_sha256"][:12],
                        (row["response_sha256"] or "-")[:12],
                    ),
                )
            )
        )
    print("Seat\tAttempt\tRetrieval IDs\tRecall IDs\tExposure IDs\tBlock Tokens")
    for row in turn["manifests"]:
        print(
            "\t".join(
                map(
                    str,
                    (
                        row["seat"],
                        row["attempt"],
                        row["retrieval_ids"],
                        row["recall_ids"],
                        row["exposure_ids"],
                        json.dumps(row["window_record"]["block_tokens"]),
                    ),
                )
            )
        )
    print("Queue\tJob ID\tState\tGeneration Session")
    for row in turn["jobs"]:
        print(
            f"{row['queue']}\t{row['id']}\t{row['state']}\t{row['generation_session_id']}"
        )


def run_jobs(args: argparse.Namespace) -> Dict[str, Any]:
    """Return every provider-capable durable Orrery queue for one slot."""

    from nexus.agents.orrery.job_queues import load_job_queues_for_slot_sync

    return {
        "success": True,
        "slot": args.slot,
        **load_job_queues_for_slot_sync(args.slot),
    }


def _run_with_cli_usage(
    args: argparse.Namespace,
    command: Callable[[argparse.Namespace], Dict[str, Any]],
) -> Dict[str, Any]:
    """Correlate all provider calls made by one in-process CLI invocation."""

    from nexus.telemetry.usage import usage_context

    with usage_context(
        slot=getattr(args, "slot", None),
        run_id=uuid.uuid4().hex[:12],
    ):
        return command(args)


def _print_usage(payload: Dict[str, Any]) -> None:
    """Render provider-reported usage without conflating prompt estimates."""

    usage = payload["usage"]
    day = usage["day"]
    openai = usage["openai_day_total"]
    print(f"OpenAI API-reported tokens (UTC day {day}): " f"{openai['total_tokens']:,}")
    if openai["unknown_usage_events"]:
        print(
            "OpenAI responses with unknown API usage: "
            f"{openai['unknown_usage_events']:,}"
        )

    allowance = usage.get("allowance") or {}
    for provider, values in sorted(allowance.items()):
        print(
            f"{provider} allowance: {values['used']:,} / "
            f"{values['allowance']:,} (remaining {values['remaining']:,}; "
            f"unknown events {values['unknown_usage_events']:,})"
        )

    for title, key in (("Providers", "providers"), ("Seats", "seats")):
        print()
        print(f"{title}:")
        rows = usage.get(key) or {}
        if not rows:
            print("  (none)")
            continue
        header = ("NAME", "INPUT", "OUTPUT", "TOTAL", "EVENTS", "UNKNOWN")
        values = [
            (
                name,
                totals["input"],
                totals["output"],
                totals["total"],
                totals["events"],
                totals["unknown_usage_events"],
            )
            for name, totals in sorted(rows.items())
        ]
        widths = [
            max(len(str(row[index])) for row in [header] + values)
            for index in range(len(header))
        ]
        for row in [header] + values:
            print(
                "  "
                + "  ".join(
                    str(cell).ljust(widths[index]) for index, cell in enumerate(row)
                )
            )

    for record in payload.get("windows", []):
        print(
            f"\n{record['seat']} attempt {record['attempt']}: {record['input_tokens']} / {record['effective_ceiling']} (headroom {record['headroom']})"
        )
        print(f"  {'BLOCK':36} TOKENS")
        for kind, tokens in record["block_tokens"].items():
            print(f"  {kind:36} {tokens}")
        _print_removed_tokens(record)


def _print_removed_tokens(record: Dict[str, Any]) -> None:
    """Print a recorded assembly removal snapshot separately from kept tokens."""
    removed = record.get("removed_block_tokens")
    if removed:
        print(f"  removed {sum(removed.values())}")
        for kind, tokens in removed.items():
            print(f"    {kind:36} {tokens}")
    else:
        print("  removed unknown")


def _print_jobs(payload: Dict[str, Any]) -> None:
    """Render every provider-capable durable Orrery queue."""

    scheduler = payload.get("scheduler")
    if scheduler:
        print(
            f"scheduler: state={scheduler.get('state', 'observer')} "
            f"owner={scheduler.get('owner_id', '-')} active={scheduler.get('active', False)} "
            f"heartbeat={scheduler.get('heartbeat_at', '-')} job={scheduler.get('current_job') or '-'}"
            + (f" reason={scheduler['reason']}" if scheduler.get("reason") else "")
            + (
                f" error={scheduler['last_error']}"
                if scheduler.get("last_error")
                else ""
            )
        )
    else:
        print("scheduler: no owner")
    for queue_kind, queue in payload["queues"].items():
        if any(queue["counts"].values()):
            counts = ", ".join(
                f"{state}={count}" for state, count in queue["counts"].items()
            )
            print(f"{queue_kind}: {counts}")
    print("Queue\tJob ID\tState\tGeneration Session")
    for job in payload.get("non_terminal_jobs", []):
        print(
            f"{job['queue']}\t{job['id']}\t{job['state']}\t{job.get('generation_session_id') or '-'}"
        )
    if payload.get("unembedded_accepted_chunks"):
        print(f"unembedded_accepted_chunks: {payload['unembedded_accepted_chunks']}")
    for field in ("unembedded_rendered_experiences", "stamped_without_vectors"):
        if field not in payload:
            raise RuntimeError(
                f"jobs payload lacks {field}: the gateway that answered "
                "predates this CLI, so restart it with nexus up and retry"
            )
    unembedded_experiences = payload["unembedded_rendered_experiences"]
    if unembedded_experiences:
        print(f"unembedded_rendered_experiences: {unembedded_experiences}")
    stamped_without_vectors = payload["stamped_without_vectors"]
    if any(stamped_without_vectors.values()):
        counts = ", ".join(
            f"{table}={count}" for table, count in stamped_without_vectors.items()
        )
        print(f"stamped_without_vectors: {counts}")


def _add_global_output_args(parser: argparse.ArgumentParser) -> None:
    """Accept global output flags after a subcommand without resetting them."""

    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit JSON output",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Truncate long text fields (accepted for global CLI consistency)",
    )


# Whether the command line main() is parsing asks for --json.
_JSON_COMMAND_LINE: ContextVar[bool] = ContextVar(
    "nexus_cli_json_command_line", default=False
)


class CliArgumentParser(argparse.ArgumentParser):
    """Argument parser whose rejections follow the ``--json`` failure contract.

    build_parser() creates the root parser with this class, and argparse gives
    every subparser the class of its parent. While main() parses a command line
    that asks for ``--json``, a rejection prints the one ``usage_error``
    envelope on stderr instead of argparse's usage text; either way the process
    exits 2.
    """

    def error(self, message: str) -> NoReturn:
        """Report a rejected command line and exit 2."""
        if _JSON_COMMAND_LINE.get():
            emit_error(message, True, code="usage_error")
            self.exit(int(ExitCode.USAGE))
        super().error(message)


def _asks_for_json(argv: Sequence[str]) -> bool:
    """Whether ``--json`` appears as an option anywhere before a ``--``."""
    for token in argv:
        if token == "--":
            return False
        if token == "--json":
            return True
    return False


def _parse_command_line(
    parser: argparse.ArgumentParser, argv: Sequence[str]
) -> argparse.Namespace:
    """Parse ``argv``, reporting a rejection as the envelope when it asks for JSON.

    ``--json`` is read from the whole command line because it may precede the
    subcommand (``nexus --json load``), where the subparser that rejects the
    arguments never sees it.
    """
    token = _JSON_COMMAND_LINE.set(_asks_for_json(argv))
    try:
        return parser.parse_args(argv)
    finally:
        _JSON_COMMAND_LINE.reset(token)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser with subcommands."""
    parser = CliArgumentParser(
        allow_abbrev=False,
        description="NEXUS CLI - Story management command-line interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nexus up                      Start the runtime (gateway + enabled services)
  nexus up --foreground         Stay attached; Ctrl+C tears down
  nexus status                  Runtime health, processes, slot, version
  nexus usage --day 2026-07-29 Show exact API-reported UTC-day token usage
  nexus window-replay --run SESSION --config candidate.toml  Replay prompt windows
  nexus jobs --slot 4           Show durable Retrograde maturation jobs
  nexus logs gateway -f         Follow the gateway log
  nexus down                    Stop the runtime
  nexus load --slot 5           Show current state of slot 5
  nexus inspect slot --slot 5 --json   Slot state as a JSON envelope
  nexus inspect chunks --slot 5 --last 2 --json   The newest two chunks
  nexus inspect chunks --slot 5 --from 10 --to 12   Chunks 10 through 12
  nexus inspect chunk 12 --slot 5  One committed chunk
  nexus inspect incubator --slot 5  The pending draft, or null
  nexus inspect characters --slot 5  Characters (also places, factions)
  nexus inspect characters 3 --slot 5  One character by id
  nexus tags audit --all --json   Active tags in deprecated categories
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
  nexus retrograde-embed-history --slot 5  Dry-run Retrograde retrieval sync
  nexus retrograde-embed-history --slot 5 --execute
  nexus record-revelation --slot 2 --claim-id 7 --knower 42
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

    # Managed runtime verbs (issue #396)
    def _add_config_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--config",
            help=(
                "Path to nexus.toml (default: $NEXUS_HOME/nexus.toml, else "
                "NEXUS_RUNTIME_CONFIG, else the checkout's nexus.toml)"
            ),
        )

    up_parser = subparsers.add_parser(
        "up", help="Start the NEXUS runtime (gateway + enabled services)"
    )
    up_parser.add_argument("--slot", type=int, help="Active slot (1-5)")
    up_parser.add_argument(
        "--foreground",
        action="store_true",
        help="Stay attached: stream logs, supervise, tear down on Ctrl+C",
    )
    _add_config_arg(up_parser)

    down_parser = subparsers.add_parser("down", help="Stop managed runtime services")
    down_parser.add_argument(
        "service", nargs="?", default=None, help="Stop a single service by name"
    )
    _add_config_arg(down_parser)

    restart_parser = subparsers.add_parser(
        "restart", help="Restart managed runtime services"
    )
    restart_parser.add_argument(
        "service", nargs="?", default=None, help="Restart a single service by name"
    )
    restart_parser.add_argument("--slot", type=int, help="Active slot (1-5)")
    _add_config_arg(restart_parser)

    status_parser = subparsers.add_parser(
        "status", help="Show runtime health, processes, slot, and version"
    )
    _add_config_arg(status_parser)

    logs_parser = subparsers.add_parser("logs", help="Tail captured service logs")
    logs_parser.add_argument(
        "service", nargs="?", default="gateway", help="Service name (default: gateway)"
    )
    logs_parser.add_argument(
        "-n",
        "--lines",
        type=int,
        default=None,
        help="Line count (default: runtime.logs.tail_lines)",
    )
    logs_parser.add_argument(
        "-f", "--follow", action="store_true", help="Follow the log"
    )
    logs_parser.add_argument(
        "--mark",
        action="store_true",
        help="Print a mark of the capture's current end (for --since)",
    )
    logs_parser.add_argument(
        "--since",
        metavar="MARK",
        default=None,
        help="Print every line written after MARK, across rotations",
    )
    _add_config_arg(logs_parser)

    home_parser = subparsers.add_parser(
        "home", help="Plan a move of runtime data into a runtime home (dry run)"
    )
    home_parser.add_argument(
        "action",
        choices=("plan",),
        help="plan: list, checksum and map every runtime file; moves nothing",
    )
    home_parser.add_argument(
        "--to",
        dest="target",
        help="Target runtime home directory (default: NEXUS_HOME)",
    )

    from nexus.runtime.readiness import TARGETS

    doctor_parser = subparsers.add_parser(
        "doctor", help="Check this machine's readiness for a role (read-only)"
    )
    doctor_parser.add_argument(
        "--target",
        choices=TARGETS,
        default="owner-host",
        help="Machine role whose checks run (default: owner-host)",
    )
    _add_config_arg(doctor_parser)

    usage_parser = subparsers.add_parser(
        "usage",
        help="Show exact provider-reported API token usage",
    )
    usage_parser.add_argument(
        "--day",
        help="UTC quota day in YYYY-MM-DD format (default: current UTC day)",
    )
    usage_parser.add_argument("--run", help="Filter events by correlation run id")

    subparsers.add_parser(
        "receipts", help="Show failure receipts grouped by fingerprint"
    )

    window_replay_parser = subparsers.add_parser(
        "window-replay",
        help="Replay a run's recorded prompt windows under candidate settings",
    )
    window_replay_parser.add_argument(
        "--run", required=True, help="Generation session id from the usage ledger"
    )
    window_replay_parser.add_argument(
        "--day",
        help="UTC ledger day in YYYY-MM-DD format (default: current UTC day)",
    )
    window_replay_parser.add_argument(
        "--config",
        help=(
            "Candidate nexus.toml (default: the runtime config); its window "
            "keys are not applied, so pass --window to replay a different spend"
        ),
    )
    window_replay_parser.add_argument(
        "--model", help="Registered model id replacing each recorded model"
    )
    window_replay_parser.add_argument(
        "--window",
        type=int,
        help=(
            "Prompt spend replacing each recorded spend; candidate window keys "
            "are not applied, so this is how to replay a different spend"
        ),
    )

    jobs_parser = subparsers.add_parser(
        "jobs",
        help="Show provider-capable durable Orrery job state for one slot",
    )
    jobs_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )

    inspect_parser = subparsers.add_parser(
        "inspect-turn", help="Inspect read-only turn references and hashes"
    )
    inspect_parser.add_argument("--slot", type=int, required=True, choices=range(1, 6))
    identity = inspect_parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--session", type=str)
    identity.add_argument("--chunk", type=int)
    inspect_parser.add_argument(
        "--summary",
        action="store_true",
        help="Print the concise joined turn observation instead of the tables",
    )
    prune_parser = subparsers.add_parser(
        "prune-manifests", help="Explicitly prune expired terminal attempt manifests"
    )
    prune_parser.add_argument("--slot", type=int, required=True, choices=range(1, 6))

    # inspect family (issue #815): read-only, JSON-first reads over the API.
    inspect_family = subparsers.add_parser(
        "inspect", help="Read-only JSON-first inspection over the NEXUS API"
    )
    inspect_verbs = inspect_family.add_subparsers(dest="inspect_command", required=True)
    inspect_slot_parser = inspect_verbs.add_parser(
        "slot", help="Read one slot's state through GET /api/slot/{slot}/state"
    )
    inspect_slot_parser.allow_abbrev = False
    inspect_slot_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    _add_global_output_args(inspect_slot_parser)

    def _add_inspect_verb(name: str, help_text: str) -> argparse.ArgumentParser:
        verb = inspect_verbs.add_parser(name, help=help_text)
        verb.allow_abbrev = False
        verb.add_argument("--slot", type=int, required=True, help="Slot number (1-5)")
        _add_global_output_args(verb)
        return verb

    inspect_chunks_parser = _add_inspect_verb(
        "chunks", "Read committed chunks: the last N, or an id range"
    )
    inspect_chunks_parser.add_argument(
        "--last",
        type=int,
        help="The newest N committed chunks (one request per chunk)",
    )
    inspect_chunks_parser.add_argument(
        "--from",
        dest="from_id",
        type=int,
        help=(
            "First chunk id of the range (default: the first chunk); needs --to."
            " One request per chunk in the range, one more if chunk --to does"
            " not exist"
        ),
    )
    inspect_chunks_parser.add_argument(
        "--to",
        dest="to_id",
        type=int,
        help=(
            "Last chunk id of the range; required with --from (alone, the range"
            " starts at the first chunk)"
        ),
    )
    inspect_chunk_parser = _add_inspect_verb("chunk", "Read one committed chunk")
    inspect_chunk_parser.add_argument("chunk_id", type=int, help="Chunk id")
    _add_inspect_verb("incubator", "Read the pending draft, or null when none waits")
    for family in ("characters", "places", "factions"):
        entity_parser = _add_inspect_verb(
            family, f"List the slot's {family}, or read one by id"
        )
        entity_parser.add_argument(
            "entity_id", type=int, nargs="?", help=f"One {family[:-1]}'s id"
        )

    # tags family (issue #811): read-only audits of the tag vocabulary.
    tags_family = subparsers.add_parser(
        "tags", help="Read-only audits of the Orrery tag vocabulary"
    )
    tags_verbs = tags_family.add_subparsers(dest="tags_command", required=True)
    tags_audit_parser = tags_verbs.add_parser(
        "audit",
        help="Report active entity tags in deprecated registry categories",
    )
    tags_audit_parser.allow_abbrev = False
    tags_audit_scope = tags_audit_parser.add_mutually_exclusive_group(required=True)
    tags_audit_scope.add_argument("--slot", type=int, help="Slot number (1-5)")
    tags_audit_scope.add_argument(
        "--all",
        action="store_true",
        help="NEXUS_template and every slot, locked slots included",
    )
    _add_global_output_args(tags_audit_parser)

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
        help=(
            "Select structured choice by number (1-indexed); in narrative mode, "
            "with --text, send your edited version of that choice"
        ),
    )
    continue_parser.add_argument(
        "--user-text",
        "--text",
        dest="user_text",
        help="Freeform user input, or with --choice the edited text of that choice",
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
    continue_parser.add_argument(
        "--weird",
        choices=("low", "medium", "high"),
        help=(
            "New-story strangeness, saved on the wizard and used by the "
            "narrative transition (wizard only)"
        ),
    )

    # retry command
    retry_parser = subparsers.add_parser(
        "retry", help="Retry the failed continuation of the recorded action"
    )
    retry_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
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
    model_choice = model_parser.add_mutually_exclusive_group()
    model_choice.add_argument(
        "--clear", action="store_true", help="Clear the story Skald pin"
    )
    model_choice.add_argument(
        "--set",
        help="Set the model (use a registry ID; run with --list to see options)",
    )
    model_parser.add_argument(
        "--list", action="store_true", help="List available models"
    )

    # models command (issue #812): lock or verify the local production
    # embedder and reranker artifacts; nothing is downloaded.
    models_parser = subparsers.add_parser(
        "models", help="Lock or verify the production model artifacts"
    )
    models_verbs = models_parser.add_subparsers(dest="models_command", required=True)
    for verb, verb_help in (
        ("lock", "Record repositories, revisions, file hashes and dimensions"),
        ("verify", "Check local artifacts against the lock (read-only)"),
    ):
        verb_parser = models_verbs.add_parser(verb, help=verb_help)
        verb_parser.allow_abbrev = False
        _add_config_arg(verb_parser)
        _add_global_output_args(verb_parser)

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
        "--create-stubs",
        action="store_true",
        help=(
            "Treat unresolved expansion refs as minimum viable entity stubs. "
            "Dry-run reports would-create rows; execute inserts them before "
            "canonical Retrograde rows."
        ),
    )
    retrograde_apply_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the raw persistence plan JSON.",
    )

    # retrograde-embed-history command
    retrograde_embed_parser = subparsers.add_parser(
        "retrograde-embed-history",
        help=(
            "Ensure and embed retrieval summaries for persisted "
            "Retrograde world events"
        ),
    )
    retrograde_embed_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    retrograde_embed_parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Write dedicated summaries and run their embedding lifecycle. "
            "Without this flag the command uses a read-only dry run."
        ),
    )

    revelation_parser = subparsers.add_parser(
        "record-revelation",
        help="Grant told or manual awareness of an existing claim",
    )
    revelation_parser.add_argument(
        "--slot", type=int, required=True, help="Slot number (1-5)"
    )
    revelation_parser.add_argument("--claim-id", type=int, required=True)
    revelation_parser.add_argument(
        "--knower",
        type=int,
        required=True,
        help="Entity spine id receiving awareness.",
    )
    revelation_parser.add_argument(
        "--source-entity-id",
        type=int,
        help="Immediate named source; omission records a manual granted tier.",
    )
    revelation_parser.add_argument(
        "--channel", help="Free-vocabulary acquisition channel."
    )
    revelation_parser.add_argument(
        "--world-time", help="Timezone-aware ISO-8601 in-world acquisition time."
    )
    revelation_parser.add_argument("--source-chunk-id", type=int)

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

    for subparser in subparsers.choices.values():
        subparser.allow_abbrev = False
        _add_global_output_args(subparser)

    return parser


# Commands whose --slot, when given, must name slot 1-5 (argparse decides
# whether it is required).
_SLOT_COMMANDS = frozenset(
    {
        "load",
        "continue",
        "retry",
        "undo",
        "regenerate",
        "clear",
        "trait-audit",
        "retrograde-packet",
        "retrograde-apply-expansion",
        "retrograde-embed-history",
        "record-revelation",
        "faction-audit",
        "faction-manifest",
        "faction-apply",
        "character-manifest",
        "character-apply",
        "place-manifest",
        "place-apply",
        "backfill-review-packet",
        "jobs",
        "lock",
        "unlock",
        "inspect slot",
        "inspect chunks",
        "inspect chunk",
        "inspect incubator",
        "inspect characters",
        "inspect places",
        "inspect factions",
        "tags audit",
        "model",
        "retrograde-seed-candidates",
        "up",
        "restart",
    }
)


def _inspect_chunks_usage_error(args: argparse.Namespace) -> Optional[str]:
    """Why ``inspect chunks`` arguments select no range, or None when they do."""
    ranged = args.from_id is not None or args.to_id is not None
    if args.last is not None and ranged:
        return "--last cannot be combined with --from or --to"
    if args.last is None and not ranged:
        return "Pass --last N or a --from/--to chunk id range"
    for flag, value in (
        ("--last", args.last),
        ("--from", args.from_id),
        ("--to", args.to_id),
    ):
        if value is not None and value < 1:
            return f"{flag} must be a positive integer"
    if args.from_id is not None and args.to_id is None:
        return "--from needs --to, so a range cannot walk the whole story"
    if (
        args.from_id is not None
        and args.to_id is not None
        and args.from_id > args.to_id
    ):
        return "--from must not exceed --to"
    return None


def _usage_error(args: argparse.Namespace, command: str) -> Optional[str]:
    """Return why the parsed arguments are unusable, or None when they are."""
    slot: Optional[int] = getattr(args, "slot", None)
    if command in _SLOT_COMMANDS and slot is not None and not 1 <= slot <= 5:
        return "Slot must be between 1 and 5"
    if command == "inspect chunks":
        chunk_error = _inspect_chunks_usage_error(args)
        if chunk_error is not None:
            return chunk_error
    if command == "model" and not args.list and slot is None:
        return "--slot is required unless using --list"
    if command == "usage" and args.day is not None:
        from nexus.telemetry.usage import validate_usage_day

        try:
            validate_usage_day(args.day)
        except ValueError as exc:
            return str(exc)
    if command == "logs" and args.lines is not None and args.lines < 1:
        return "Log line count must be a positive integer"
    if command == "record-revelation" and args.world_time is not None:
        try:
            parse_record_revelation_world_time(args.world_time)
        except ValueError as exc:
            return str(exc)
    return None


def _config_remedy(command: str) -> str:
    """Name the locators that select an active nexus.toml for ``command``."""
    config_flag = (
        "Pass --config with the path to nexus.toml, set "
        if command in RUNTIME_CONFIG_COMMANDS
        else "Set "
    )
    return (
        f"{config_flag}{HOME_ENV} to a home containing nexus.toml, or set "
        f"{RUNTIME_CONFIG_ENV} to an existing nexus.toml."
    )


def _active_remote_runtime(
    args: argparse.Namespace, command: str
) -> Optional[RemoteRuntime]:
    """Load the active nexus.toml and say whether the runtime it selects is remote.

    Runs for every command before dispatch, HTTP commands included, so a
    missing or invalid configuration or a malformed NEXUS_API_URL is reported
    once as ``config_error`` rather than surfacing mid-command. Only the
    active nexus.toml and NEXUS_API_URL are read; no database or network
    connection is opened.
    """
    explicit = (
        getattr(args, "config", None) if command in RUNTIME_CONFIG_COMMANDS else None
    )
    settings = _load_cli_settings(explicit)
    return detect_remote_runtime(
        settings.runtime if settings is not None else None,
        os.environ.get(API_URL_ENV),
    )


def _dispatch(args: argparse.Namespace) -> Dict[str, Any] | int:
    """Run the selected command; an int is an exit code already reported."""
    if args.command == "up":
        result = run_up(args)
    elif args.command == "down":
        result = run_down(args)
    elif args.command == "restart":
        result = run_restart(args)
    elif args.command == "status":
        result = run_status(args)
    elif args.command == "logs":
        result = run_logs(args)
    elif args.command == "home":
        result = run_home(args)
    elif args.command == "doctor":
        return run_doctor(args)
    elif args.command == "receipts":
        return run_receipts(args)
    elif args.command == "usage":
        result = run_usage(args)
    elif args.command == "window-replay":
        result = run_window_replay(args)
    elif args.command == "inspect-turn":
        from nexus.telemetry.attempt_manifest import NoGenerationSessionError

        try:
            result = run_inspect_turn(args)
        except NoGenerationSessionError as exc:
            if args.json:
                return _fail(args, "domain_failure", str(exc))
            print(str(exc))
            return 1
        if args.summary and not args.json:
            from nexus.telemetry.turn_observation import format_turn_summary

            print(format_turn_summary(result["observation"]))
            return 0
    elif args.command == "inspect":
        result = run_inspect(args)
    elif args.command == "tags":
        result = run_tags_audit(args)
    elif args.command == "prune-manifests":
        result = run_prune_manifests(args)
    elif args.command == "jobs":
        result = run_jobs(args)
    elif args.command == "load":
        result = run_load(args)
    elif args.command == "continue":
        result = run_continue(args)
    elif args.command == "retry":
        result = run_retry(args)
    elif args.command == "undo":
        result = run_undo(args)
    elif args.command == "regenerate":
        result = run_regenerate(args)
    elif args.command == "model":
        result = run_model(args)
    elif args.command == "models":
        from nexus.agents.memnon.utils.artifact_manifest import run_models_command

        result = run_models_command(args.models_command, args.config)
    elif args.command == "clear":
        result = run_clear(args)
    elif args.command == "trait-audit":
        result = _run_with_cli_usage(args, run_trait_audit)
    elif args.command == "retrograde-packet":
        result = run_retrograde_packet(args)
    elif args.command == "retrograde-seed-candidates":
        result = _run_with_cli_usage(args, run_retrograde_seed_candidates)
    elif args.command == "retrograde-expand-seeds":
        result = _run_with_cli_usage(args, run_retrograde_expand_seeds)
    elif args.command == "retrograde-apply-expansion":
        result = run_retrograde_apply_expansion(args)
    elif args.command == "retrograde-embed-history":
        result = run_retrograde_embed_history(args)
    elif args.command == "record-revelation":
        result = run_record_revelation(args)
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
        return _fail(args, "usage_error", f"Unknown command: {args.command}")
    return result


def main() -> int:
    """Entry point for the NEXUS CLI; exit codes follow nexus.cli_contract."""
    parser = build_parser()
    args = _parse_command_line(parser, sys.argv[1:])
    command = command_path(parser, args)

    usage_error = _usage_error(args, command)
    if usage_error is not None:
        return _fail(args, "usage_error", usage_error)

    # A self-diagnostic command (doctor, receipts) reports on the
    # configuration and this machine itself, so neither check below may
    # pre-empt its report.
    if command not in SELF_DIAGNOSTIC_COMMANDS:
        try:
            remote = _active_remote_runtime(args, command)
        except FileNotFoundError as exc:
            return _fail(args, "config_error", f"{exc}. {_config_remedy(command)}")
        except (RuntimeHomeError, ValueError) as exc:
            # load_settings reports an invalid config as ValueError (pydantic's
            # ValidationError, tomllib's TOMLDecodeError, an unsupported file
            # type); is_loopback_url reports an API URL without a host likewise.
            return _fail(args, "config_error", str(exc))

        # Refuse before dispatch, so a refused command opens no connection.
        refusal = transport_refusal(command, args, remote)
        if refusal is not None:
            return _fail(args, "transport_refused", refusal)

    try:
        outcome = _dispatch(args)
    except (
        requests.exceptions.ConnectionError,
        requests.exceptions.ChunkedEncodingError,
    ) as exc:
        outcome = {
            **_api_unreachable(),
            "error": f"Cannot connect to API server at {get_api_url()}: {exc}",
        }
    except requests.exceptions.Timeout as exc:
        outcome = {
            **_api_unreachable(),
            "error": f"Timed out waiting for API server at {get_api_url()}: {exc}",
        }
    except _API_URL_ERRORS as exc:
        return _fail(
            args,
            "config_error",
            f"{exc}. Set {API_URL_ENV} to an absolute http:// or https:// URL.",
        )
    except _CREDENTIAL_ERRORS as exc:
        return _fail(args, "config_error", str(exc))
    except ApiAnswerFailure as exc:
        return _fail(
            args,
            exc.code,
            exc.message,
            {} if exc.status_code is None else {"status_code": exc.status_code},
        )
    except requests.exceptions.RequestException as exc:
        # Any other failed request is not an answer (a followed redirect loop,
        # a body it cannot decode, a malformed header): a domain failure, as
        # the generation waiter classifies it.
        return _fail(args, "domain_failure", f"Could not read {get_api_url()}: {exc}")
    if isinstance(outcome, int):
        return outcome
    result = outcome

    # Failure: one envelope, preserving every non-empty field of the result.
    if not result.get("success", True) or result.get("error"):
        return _fail(
            args,
            result.get("code", "domain_failure"),
            result.get("error") or "Unknown error",
            partial_fields(result),
        )

    if command in ENVELOPE_COMMANDS:
        if args.json:
            envelope = success_envelope(result["data"])
            print(json.dumps(envelope, indent=2, sort_keys=True))
        elif command == "tags audit":
            _print_tags_audit(result["data"])
        else:
            _print_inspection(
                result["data"], truncate=args.truncate, verb=args.inspect_command
            )
        return int(ExitCode.OK)

    emit_output(result, args.json, truncate=args.truncate)
    if result.get("failed_policy"):
        return int(ExitCode.DOMAIN_FAILURE)
    return int(ExitCode.OK)


if __name__ == "__main__":
    raise SystemExit(main())
