"""Read-only character tag rewrite manifest builder for Orrery backfills."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from nexus.agents.orrery.tag_constants import CANONICAL_TAGS


CHARACTER_MANIFEST_SCHEMA_VERSION = "orrery_character_manifest.v1"

LEGACY_CHARACTER_CATEGORIES: Sequence[str] = (
    "bodyform",
    "profession_lite",
    "role",
    "orrery_signal",
    "orrery_state",
)

TARGET_CHARACTER_CATEGORIES = frozenset(
    {
        "bodyform.lineage",
        "bodyform.condition",
        "disposition",
        "capacity",
        "role.function",
        "role.fame",
        "role.resources",
        "state",
    }
)
CHARACTER_CATEGORY_CARDINALITY = {
    "bodyform.lineage": "multi",
    "bodyform.condition": "multi",
    "disposition": "multi",
    "capacity": "multi",
    "role.function": "multi",
    "role.fame": "exclusive",
    "role.resources": "exclusive",
    "state": "multi",
}
EXCLUSIVE_CHARACTER_CATEGORIES = frozenset(
    category
    for category, cardinality in CHARACTER_CATEGORY_CARDINALITY.items()
    if cardinality == "exclusive"
)

WATCHED_COLLISION_TAGS = frozenset(
    {
        "hunter",
        "traditionalist",
    }
)

CONTEXTUAL_CHARACTER_ALIASES: Mapping[str, str] = {
    **CANONICAL_TAGS,
    "traditionalist": "tradition_bound",
}

RELATIONAL_REMAINDERS: Mapping[str, tuple[str, str]] = {
    "under_active_pursuit": (
        "hunting",
        "Legacy single-entity pursuit signal is relational; resolve the hunter "
        "endpoint before writing an inbound hunting pair-tag.",
    ),
    "contacts_available": (
        "contact:<kind>",
        "Legacy contacts_available overloaded lodging, social, and intimate "
        "networks; decompose to kind-qualified contacts or relationship rows.",
    ),
}

STRUCTURED_REMAINDERS: Mapping[str, str] = {
    "debt_pulse_active": (
        "Skald sovereignty supersedes the old debt-pulse forcing model; review "
        "whether any structured state remains."
    ),
    "seeking_identity": (
        "Identity seeking is package-relevant context but not a canonical state "
        "anchor by default."
    ),
}

PROSE_REMAINDERS: Mapping[str, str] = {
    "bodyform:biologically_immortal": (
        "Biological immortality modulates needs/longevity but is not a canonical "
        "bodyform anchor."
    ),
    "uploaded_consciousness": (
        "Upload history is event/prose unless current embodiment evidence also "
        "supports virtual or inorganic."
    ),
    "off_grid": (
        "Off-grid status may be concealment, travel, or prose depending on the "
        "current actor/location context."
    ),
    "ghostprint_active": (
        "Ghostprint exposure is setting-specific concealment/prose unless a "
        "package names a sharper substrate."
    ),
}


def build_character_migration_manifest(
    cur: Any,
    *,
    slot: int,
    dbname: str,
) -> dict[str, Any]:
    """Build a read-only manifest for legacy character tag rewrite review."""

    registered_tags = _load_registered_tags(cur)
    rows = _load_legacy_character_rows(cur)
    return build_character_migration_manifest_from_rows(
        rows,
        registered_tags=registered_tags,
        slot=slot,
        dbname=dbname,
    )


def build_character_migration_manifest_from_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    registered_tags: Mapping[str, Mapping[str, Any]],
    slot: int,
    dbname: str,
) -> dict[str, Any]:
    """Build a manifest from preloaded legacy rows for tests and callers."""

    counters: Counter[str] = Counter()
    operations: list[dict[str, Any]] = []
    characters: dict[int, dict[str, Any]] = {}

    for row in rows:
        character_id = int(row["character_id"])
        character_name = str(row["character_name"])
        source_tag = str(row["tag"])
        source_category = str(row["category"])
        counters["legacy_character_tag_rows"] += 1
        counters[f"legacy_category:{source_category}"] += 1

        operation = _operation_for_row(
            row,
            registered_tags=registered_tags,
            operation_index=len(operations) + 1,
        )
        operations.append(operation)
        counters["operation_items"] += 1
        counters[f"{operation['operation_type']}_operations"] += 1
        counters[f"{operation['status']}_operations"] += 1
        if (
            operation.get("review_required")
            and operation["status"] != "review_required"
        ):
            counters["review_required_operations"] += 1
        if operation.get("target", {}).get("target_registered") is False:
            counters["missing_target_tag_operations"] += 1

        character = characters.setdefault(
            character_id,
            {
                "character_id": character_id,
                "character_name": character_name,
                "operations": [],
                "review_required_operations": 0,
            },
        )
        character["operations"].append(operation["operation_id"])
        if operation.get("review_required"):
            character["review_required_operations"] += 1

        if source_tag != operation.get("target", {}).get("tag", source_tag):
            counters["candidate_renames"] += 1

    return {
        "schema_version": CHARACTER_MANIFEST_SCHEMA_VERSION,
        "dry_run": True,
        "source": {
            "slot": slot,
            "dbname": dbname,
            "legacy_categories": list(LEGACY_CHARACTER_CATEGORIES),
            "watched_collision_tags": sorted(WATCHED_COLLISION_TAGS),
        },
        "counters": dict(sorted(counters.items())),
        "characters": sorted(
            characters.values(),
            key=lambda item: (
                str(item["character_name"]).lower(),
                item["character_id"],
            ),
        ),
        "operations": operations,
    }


def _operation_for_row(
    row: Mapping[str, Any],
    *,
    registered_tags: Mapping[str, Mapping[str, Any]],
    operation_index: int,
) -> dict[str, Any]:
    source_tag = str(row["tag"])
    source_category = str(row["category"])
    entity_id = int(row["entity_id"])

    if source_tag in RELATIONAL_REMAINDERS:
        pair_tag, reason = RELATIONAL_REMAINDERS[source_tag]
        return _operation(
            row,
            operation_index=operation_index,
            operation_type="resolve_pair_tag_target",
            target={
                "entity_kind": "character",
                "entity_id": entity_id,
                "pair_tag": pair_tag,
                "subject_entity_id": None,
                "object_entity_id": entity_id,
            },
            reason=reason,
        )

    if source_tag in STRUCTURED_REMAINDERS:
        return _operation(
            row,
            operation_index=operation_index,
            operation_type="structured_remainder",
            target={"entity_kind": "character", "entity_id": entity_id},
            reason=STRUCTURED_REMAINDERS[source_tag],
        )

    if source_tag in PROSE_REMAINDERS:
        return _operation(
            row,
            operation_index=operation_index,
            operation_type="preserve_prose",
            target={"entity_kind": "character", "entity_id": entity_id},
            reason=PROSE_REMAINDERS[source_tag],
        )

    target_tag = CONTEXTUAL_CHARACTER_ALIASES.get(source_tag, source_tag)
    target_row = registered_tags.get(target_tag)
    if target_row:
        target_category = str(target_row["category"])
        reason = _rewrite_reason(
            source_tag=source_tag,
            source_category=source_category,
            target_tag=target_tag,
            target_category=target_category,
        )
    else:
        target_category = None
        reason = (
            "No registered character target tag exists yet; review as prose, "
            "pair-tag, or future vocabulary."
        )

    return _operation(
        row,
        operation_index=operation_index,
        operation_type="review_entity_tag",
        target={
            "entity_kind": "character",
            "entity_id": entity_id,
            "category": target_category,
            "tag": target_tag,
            "target_registered": target_row is not None,
        },
        reason=reason,
    )


def _operation(
    row: Mapping[str, Any],
    *,
    operation_index: int,
    operation_type: str,
    target: Mapping[str, Any],
    reason: str,
) -> dict[str, Any]:
    character_id = int(row["character_id"])
    source_tag = str(row["tag"])
    return {
        "operation_id": f"character-{operation_index:04d}-{character_id}-{source_tag}",
        "operation_type": operation_type,
        "status": "review_required",
        "review_required": True,
        "character_id": character_id,
        "character_name": str(row["character_name"]),
        "entity_id": int(row["entity_id"]),
        "source": {
            "tag_id": int(row["tag_id"]),
            "tag": source_tag,
            "category": str(row["category"]),
        },
        "target": dict(target),
        "confidence": "review",
        "reason": reason,
    }


def _rewrite_reason(
    *,
    source_tag: str,
    source_category: str,
    target_tag: str,
    target_category: str,
) -> str:
    if source_tag != target_tag:
        return (
            f"Legacy tag {source_category}:{source_tag} canonicalizes to "
            f"{target_category}:{target_tag}; review before inserting."
        )
    if source_category != target_category:
        return (
            f"Legacy category {source_category} rewrites to {target_category} "
            "for the same physical tag name; review before inserting."
        )
    return "Registered target already matches; review whether the row should remain."


def _load_registered_tags(cur: Any) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT t.tag,
               t.category,
               t.deprecated,
               t.synonym_for
        FROM tags t
        WHERE t.deprecated = FALSE
          AND t.synonym_for IS NULL
          AND t.category = ANY(%s)
        """,
        (list(TARGET_CHARACTER_CATEGORIES),),
    )
    rows = cur.fetchall()
    return {
        str(row["tag"]): {
            "category": str(row["category"]),
            "deprecated": bool(row["deprecated"]),
            "synonym_for": row["synonym_for"],
        }
        for row in rows
    }


def _load_legacy_character_rows(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT c.id AS character_id,
               c.name AS character_name,
               e.id AS entity_id,
               t.id AS tag_id,
               t.tag,
               t.category
        FROM entity_tags et
        JOIN tags t ON t.id = et.tag_id
        JOIN entities e ON e.id = et.entity_id
        JOIN characters c ON c.entity_id = e.id
        WHERE et.cleared_at IS NULL
          AND e.kind = 'character'::entity_kind
          AND (
              t.category = ANY(%s)
              OR t.tag = ANY(%s)
          )
        ORDER BY lower(c.name), c.id, t.category, t.tag
        """,
        (list(LEGACY_CHARACTER_CATEGORIES), list(WATCHED_COLLISION_TAGS)),
    )
    grouped: dict[tuple[int, str], dict[str, Any]] = defaultdict(dict)
    result: list[dict[str, Any]] = []
    for row in cur.fetchall():
        key = (int(row["character_id"]), str(row["tag"]))
        if key in grouped:
            continue
        item = {
            "character_id": int(row["character_id"]),
            "character_name": str(row["character_name"]),
            "entity_id": int(row["entity_id"]),
            "tag_id": int(row["tag_id"]),
            "tag": str(row["tag"]),
            "category": str(row["category"]),
        }
        grouped[key] = item
        result.append(item)
    return result
