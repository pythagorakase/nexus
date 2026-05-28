"""Build human review packets for Orrery backfill manifests."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any


BACKFILL_REVIEW_PACKET_SCHEMA_VERSION = "orrery_backfill_review_packet.v1"
BACKFILL_MANIFEST_FAMILIES = ("faction", "character", "place")


def build_backfill_review_packet(
    manifests: Mapping[str, Mapping[str, Any]],
    *,
    slot: int,
    examples_per_queue: int = 5,
) -> dict[str, Any]:
    """Summarize review-required backfill manifests without changing readiness."""

    if examples_per_queue < 1:
        raise ValueError("examples_per_queue must be at least 1")

    family_packets: dict[str, Any] = {}
    overall_counters: Counter[str] = Counter()
    for family in BACKFILL_MANIFEST_FAMILIES:
        manifest = manifests.get(family)
        if manifest is None:
            raise ValueError(f"Missing {family} manifest")
        _validate_manifest_slot(manifest, slot=slot, family=family)
        family_packet = _build_family_packet(
            family,
            manifest,
            examples_per_queue=examples_per_queue,
        )
        family_packets[family] = family_packet
        for key, value in family_packet["counters"].items():
            if isinstance(value, int):
                overall_counters[key] += value

    return {
        "schema_version": BACKFILL_REVIEW_PACKET_SCHEMA_VERSION,
        "slot": slot,
        "policy": {
            "mutates_data": False,
            "promotes_ready_rows": False,
            "ready_contract": (
                "Rows become apply-eligible only after a reviewer edits the source "
                "manifest to status=ready and review_required=false."
            ),
        },
        "counters": dict(overall_counters),
        "families": family_packets,
        "review_order": [
            {
                "queue": "registered_single_entity",
                "reason": (
                    "Registered single-entity candidates are the narrowest "
                    "non-destructive review surface."
                ),
            },
            {
                "queue": "pair_target_resolution",
                "reason": (
                    "Pair-tag rows need endpoint decisions before any apply path."
                ),
            },
            {
                "queue": "missing_target_tag",
                "reason": (
                    "Missing target tags require vocabulary, prose, or pair-tag "
                    "decisions before promotion."
                ),
            },
            {
                "queue": "prose_or_event",
                "reason": "Prose/world-event rows are outside entity_tags apply.",
            },
            {
                "queue": "structured_remainder",
                "reason": "Remainders need a substrate decision before mutation.",
            },
            {
                "queue": "drop_after_review",
                "reason": "Drops are destructive and belong to a later reviewed slice.",
            },
        ],
    }


def render_backfill_review_packet_markdown(packet: Mapping[str, Any]) -> str:
    """Render a packet as a compact Markdown review aid."""

    lines = [
        f"# Slot {packet.get('slot')} Orrery Backfill Review Packet",
        "",
        "This packet is read-only. It does not mark any manifest row ready and "
        "does not authorize data mutation.",
        "",
        "## Summary",
        "",
        "| Family | Operations | Ready | Review-required | Registered entity "
        "candidates | Missing target tags | Pair target rows | Prose/event rows | "
        "Remainders | Drops |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    families = packet.get("families") or {}
    for family in BACKFILL_MANIFEST_FAMILIES:
        family_packet = families.get(family) or {}
        counters = family_packet.get("counters") or {}
        lines.append(
            "| {family} | {operation_items} | {ready_operations} | "
            "{review_required_operations} | {registered_single_entity} | "
            "{missing_target_tag} | {pair_target_resolution} | "
            "{prose_or_event} | {structured_remainder} | {drop_after_review} |".format(
                family=family,
                operation_items=counters.get("operation_items", 0),
                ready_operations=counters.get("ready_operations", 0),
                review_required_operations=counters.get(
                    "review_required_operations", 0
                ),
                registered_single_entity=counters.get(
                    "queue:registered_single_entity", 0
                ),
                missing_target_tag=counters.get("queue:missing_target_tag", 0),
                pair_target_resolution=counters.get("queue:pair_target_resolution", 0),
                prose_or_event=counters.get("queue:prose_or_event", 0),
                structured_remainder=counters.get("queue:structured_remainder", 0),
                drop_after_review=counters.get("queue:drop_after_review", 0),
            )
        )

    lines.extend(
        [
            "",
            "## Suggested Review Order",
            "",
        ]
    )
    for item in packet.get("review_order") or []:
        lines.append(f"- `{item['queue']}`: {item['reason']}")

    for family in BACKFILL_MANIFEST_FAMILIES:
        family_packet = families.get(family) or {}
        lines.extend(_render_family_markdown(family, family_packet))

    lines.append("")
    return "\n".join(lines)


def _build_family_packet(
    family: str,
    manifest: Mapping[str, Any],
    *,
    examples_per_queue: int,
) -> dict[str, Any]:
    operations = list(manifest.get("operations") or [])
    counters: Counter[str] = Counter()
    counters["operation_items"] = len(operations)
    queue_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    target_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    operation_type_counts: Counter[str] = Counter()

    for operation in operations:
        status = str(operation.get("status") or "")
        operation_type = str(operation.get("operation_type") or "")
        queue = _review_queue(operation)
        counters[f"queue:{queue}"] += 1
        counters[f"status:{status}"] += 1
        counters[f"operation_type:{operation_type}"] += 1
        operation_type_counts[operation_type] += 1
        if status == "ready":
            counters["ready_operations"] += 1
        if bool(operation.get("review_required", False)):
            counters["review_required_operations"] += 1

        target_label = _target_label(operation)
        source_label = _source_label(operation)
        if target_label:
            target_counts[target_label] += 1
        if source_label:
            source_counts[source_label] += 1
        if len(queue_examples[queue]) < examples_per_queue:
            queue_examples[queue].append(_operation_example(operation, queue=queue))

    for queue in (
        "registered_single_entity",
        "missing_target_tag",
        "pair_target_resolution",
        "prose_or_event",
        "structured_remainder",
        "drop_after_review",
        "other_review",
    ):
        counters.setdefault(f"queue:{queue}", 0)
    counters.setdefault("ready_operations", 0)
    counters.setdefault("review_required_operations", 0)

    return {
        "schema_version": manifest.get("schema_version"),
        "source": manifest.get("source") or {},
        "counters": dict(counters),
        "operation_types": dict(operation_type_counts.most_common()),
        "top_targets": dict(target_counts.most_common(20)),
        "top_sources": dict(source_counts.most_common(20)),
        "queue_examples": dict(queue_examples),
    }


def _validate_manifest_slot(
    manifest: Mapping[str, Any],
    *,
    slot: int,
    family: str,
) -> None:
    source = manifest.get("source") or {}
    manifest_slot = source.get("slot")
    if manifest_slot is not None and int(manifest_slot) != slot:
        raise ValueError(
            f"{family} manifest slot {manifest_slot} does not match --slot {slot}"
        )


def _review_queue(operation: Mapping[str, Any]) -> str:
    operation_type = str(operation.get("operation_type") or "")
    target = operation.get("target") or {}
    if operation_type == "review_entity_tag":
        if target.get("target_registered") is False:
            return "missing_target_tag"
        if target.get("category") and target.get("tag"):
            return "registered_single_entity"
        return "other_review"
    if operation_type == "resolve_pair_tag_target":
        return "pair_target_resolution"
    if operation_type in {"preserve_prose", "world_event_or_prose"}:
        return "prose_or_event"
    if operation_type in {
        "structured_remainder",
        "classify_structured_remainder",
    }:
        return "structured_remainder"
    if operation_type == "drop_legacy_tag_after_review":
        return "drop_after_review"
    return "other_review"


def _operation_example(operation: Mapping[str, Any], *, queue: str) -> dict[str, Any]:
    return {
        "queue": queue,
        "operation_id": operation.get("operation_id"),
        "operation_type": operation.get("operation_type"),
        "status": operation.get("status"),
        "review_required": operation.get("review_required"),
        "entity": _entity_label(operation),
        "source": _source_label(operation),
        "target": _target_label(operation),
        "reason": operation.get("reason"),
    }


def _entity_label(operation: Mapping[str, Any]) -> str:
    for name_key, id_key, label in (
        ("faction_name", "faction_id", "faction"),
        ("character_name", "character_id", "character"),
        ("place_name", "place_id", "place"),
    ):
        name = operation.get(name_key)
        entity_id = operation.get(id_key)
        if name is not None or entity_id is not None:
            return f"{name or label} ({label} {entity_id})"
    entity_id = operation.get("entity_id")
    return f"entity {entity_id}" if entity_id is not None else "unknown entity"


def _source_label(operation: Mapping[str, Any]) -> str:
    source = operation.get("source") or {}
    category = source.get("category")
    tag = source.get("tag")
    if category or tag:
        return f"{category or '?'}:{tag or '?'}"
    column = source.get("column")
    if column:
        value = str(source.get("value", ""))
        return f"{column}={_compact(value)}"
    kind = source.get("kind")
    matches = source.get("matches") or []
    if kind and matches:
        keywords = []
        for match in matches[:3]:
            keywords.extend(str(item) for item in match.get("keywords") or [])
        keyword_text = ", ".join(keywords[:5])
        return f"{kind}: {keyword_text}" if keyword_text else str(kind)
    return str(kind or "")


def _target_label(operation: Mapping[str, Any]) -> str:
    target = operation.get("target") or {}
    category = target.get("category") or target.get("target_category")
    tag = target.get("tag")
    if category and tag:
        return f"{category}:{tag}"
    pair_tag = target.get("pair_tag")
    if pair_tag:
        subject = target.get("subject_entity_id")
        obj = target.get("object_entity_id")
        return f"{pair_tag}({subject or '?'} -> {obj or '?'})"
    destination = target.get("destination")
    if destination:
        return str(destination)
    if category:
        return str(category)
    return ""


def _compact(value: str, limit: int = 80) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _render_family_markdown(
    family: str,
    family_packet: Mapping[str, Any],
) -> list[str]:
    counters = family_packet.get("counters") or {}
    lines = [
        "",
        f"## {family.title()}",
        "",
        f"- Manifest schema: `{family_packet.get('schema_version')}`",
        f"- Operations: {counters.get('operation_items', 0)}",
        f"- Ready rows: {counters.get('ready_operations', 0)}",
        f"- Review-required rows: {counters.get('review_required_operations', 0)}",
        "",
        "### Queue Counts",
        "",
    ]
    for queue in (
        "registered_single_entity",
        "missing_target_tag",
        "pair_target_resolution",
        "prose_or_event",
        "structured_remainder",
        "drop_after_review",
        "other_review",
    ):
        lines.append(f"- `{queue}`: {counters.get(f'queue:{queue}', 0)}")

    top_targets = family_packet.get("top_targets") or {}
    if top_targets:
        lines.extend(["", "### Top Targets", ""])
        for target, count in list(top_targets.items())[:10]:
            lines.append(f"- `{target}`: {count}")

    top_sources = family_packet.get("top_sources") or {}
    if top_sources:
        lines.extend(["", "### Top Sources", ""])
        for source, count in list(top_sources.items())[:10]:
            lines.append(f"- `{source}`: {count}")

    queue_examples = family_packet.get("queue_examples") or {}
    if queue_examples:
        lines.extend(["", "### Review Examples", ""])
        for queue, examples in queue_examples.items():
            lines.extend(["", f"#### `{queue}`", ""])
            lines.append("| Operation | Entity | Source | Target | Reason |")
            lines.append("|---|---|---|---|---|")
            for item in examples:
                lines.append(
                    (
                        "| `{operation}` | {entity} | `{source}` | `{target}` | "
                        "{reason} |"
                    ).format(
                        operation=item.get("operation_id"),
                        entity=_escape_table(str(item.get("entity") or "")),
                        source=_escape_table(str(item.get("source") or "")),
                        target=_escape_table(str(item.get("target") or "")),
                        reason=_escape_table(str(item.get("reason") or "")),
                    )
                )
    return lines


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
