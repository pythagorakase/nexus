"""Read-only place tag rewrite manifest builder for Orrery backfills."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping as MappingABC
from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Sequence


PLACE_MANIFEST_SCHEMA_VERSION = "orrery_place_manifest.v1"

TARGET_PLACE_CATEGORIES = frozenset(
    {
        "place_function",
        "place_visibility",
        "place_access",
        "place_environment",
        "place_threat",
    }
)
LEGACY_PLACE_CATEGORIES: Sequence[str] = ("place_affordance",)

LEGACY_PLACE_AFFORDANCE_MAP: Mapping[str, tuple[str, ...]] = {
    "home": ("dwelling",),
    "lodgings": ("dwelling", "commerce"),
    "safe_house": ("dwelling", "haven", "place_hidden", "place_restricted"),
    "tavern": ("commerce", "meeting", "entertainment"),
    "teahouse": ("commerce", "meeting"),
    "cafe": ("commerce", "meeting"),
    "restaurant": ("commerce", "meeting"),
    "cookshop": ("commerce",),
    "market": ("commerce", "meeting", "place_open"),
    "public_water": ("water_source",),
    "wilderness": ("wilderness",),
    "street": ("transit",),
    "transit_hub": ("transit",),
    "the_roots": ("subterranean", "transit"),
    "the_glow": ("urban_dense", "place_known", "place_open"),
    "town_square": ("meeting", "place_open"),
    "public_space": ("meeting", "place_open"),
    "general_social_venue": ("meeting",),
    "neutral_ground": ("meeting",),
    "intimate_social_venue": ("meeting", "entertainment"),
    "intimate_services_establishment": ("meeting", "entertainment"),
    "private_quarters": ("dwelling", "place_restricted"),
    "workplace": ("production",),
    "worksite": ("production",),
    "administrative_office": ("administration", "place_restricted"),
    "place_of_remembrance": ("tomb", "sacred"),
}


@dataclass(frozen=True, slots=True)
class PlaceKeywordRule:
    """A keyword-to-tag suggestion for read-only place review manifests."""

    tag: str
    category: str
    keywords: tuple[str, ...]
    reason: str


KEYWORD_RULES: tuple[PlaceKeywordRule, ...] = (
    PlaceKeywordRule(
        tag="commerce",
        category="place_function",
        keywords=(
            "shop",
            "store",
            "market",
            "bar",
            "cafe",
            "restaurant",
            "vendor",
            "trade",
            "retail",
            "outfitter",
        ),
        reason="Prose suggests ordinary buying, selling, services, or trade.",
    ),
    PlaceKeywordRule(
        tag="dwelling",
        category="place_function",
        keywords=(
            "home",
            "apartment",
            "quarters",
            "residence",
            "lodging",
            "bunk",
            "dorm",
            "loft",
            "safehouse",
            "safe house",
        ),
        reason="Prose suggests shelter or domestic routines.",
    ),
    PlaceKeywordRule(
        tag="place_medical",
        category="place_function",
        keywords=("clinic", "hospital", "medical", "triage", "healing"),
        reason="Prose suggests care, triage, or healing.",
    ),
    PlaceKeywordRule(
        tag="transit",
        category="place_function",
        keywords=(
            "road",
            "street",
            "tunnel",
            "station",
            "hub",
            "route",
            "maglev",
            "rail",
            "shipping",
            "yard",
            "convoy",
            "vehicle",
        ),
        reason="Prose suggests route movement, traffic, or transfers.",
    ),
    PlaceKeywordRule(
        tag="archive",
        category="place_function",
        keywords=("archive", "records", "library", "database", "data vault"),
        reason="Prose suggests records, memory, data, or evidence storage.",
    ),
    PlaceKeywordRule(
        tag="fortification",
        category="place_function",
        keywords=(
            "fortified",
            "bunker",
            "barricade",
            "checkpoint",
            "turret",
            "turrets",
            "defensible",
            "blast door",
        ),
        reason="Prose suggests defensible, fortified, or guarded structure.",
    ),
    PlaceKeywordRule(
        tag="haven",
        category="place_function",
        keywords=("safehouse", "safe house", "shelter", "sanctuary", "refuge"),
        reason="Prose suggests shelter or hiding safety.",
    ),
    PlaceKeywordRule(
        tag="sacred",
        category="place_function",
        keywords=("temple", "shrine", "sacred", "ritual", "pilgrim"),
        reason="Prose suggests ritual, taboo, or worship.",
    ),
    PlaceKeywordRule(
        tag="meeting",
        category="place_function",
        keywords=(
            "meeting",
            "lounge",
            "bar",
            "tavern",
            "square",
            "rendezvous",
            "meetup",
            "negotiation",
        ),
        reason="Prose suggests gathering, negotiation, or social meeting.",
    ),
    PlaceKeywordRule(
        tag="tomb",
        category="place_function",
        keywords=("tomb", "grave", "crypt", "mortuary", "burial"),
        reason="Prose suggests burial or remembrance.",
    ),
    PlaceKeywordRule(
        tag="confinement",
        category="place_function",
        keywords=("prison", "jail", "holding cell", "cage", "detention"),
        reason="Prose suggests restraint or confinement.",
    ),
    PlaceKeywordRule(
        tag="learning",
        category="place_function",
        keywords=("school", "academy", "classroom", "instruction", "study"),
        reason="Prose suggests instruction or study.",
    ),
    PlaceKeywordRule(
        tag="craft",
        category="place_function",
        keywords=("workshop", "repair", "fabrication", "forge", "loom", "tailor"),
        reason="Prose suggests making, repair, or workshop labor.",
    ),
    PlaceKeywordRule(
        tag="military",
        category="place_function",
        keywords=("armory", "weapons", "soldiers", "military", "guards"),
        reason="Prose suggests armed, policing, or command work.",
    ),
    PlaceKeywordRule(
        tag="production",
        category="place_function",
        keywords=("factory", "plant", "farm", "generator", "industrial"),
        reason="Prose suggests extraction, production, or throughput.",
    ),
    PlaceKeywordRule(
        tag="administration",
        category="place_function",
        keywords=("office", "administrative", "bureau", "permits", "records"),
        reason="Prose suggests bureaucratic or institutional paperwork.",
    ),
    PlaceKeywordRule(
        tag="water_source",
        category="place_function",
        keywords=("well", "water source", "fountain", "spring", "drinking water"),
        reason="Prose suggests routine or urgent water access.",
    ),
    PlaceKeywordRule(
        tag="entertainment",
        category="place_function",
        keywords=("club", "theater", "performance", "lounge", "bar", "show"),
        reason="Prose suggests leisure or performance.",
    ),
    PlaceKeywordRule(
        tag="place_hidden",
        category="place_visibility",
        keywords=("hidden", "secret", "concealed", "off-grid", "unmarked"),
        reason="Prose suggests the place is secret, concealed, or hard to find.",
    ),
    PlaceKeywordRule(
        tag="place_known",
        category="place_visibility",
        keywords=("public", "iconic", "well-known", "known landmark"),
        reason="Prose suggests broad discoverability.",
    ),
    PlaceKeywordRule(
        tag="place_open",
        category="place_access",
        keywords=("public", "open to public", "open access", "public traffic"),
        reason="Prose suggests ordinary access without special permission.",
    ),
    PlaceKeywordRule(
        tag="place_restricted",
        category="place_access",
        keywords=(
            "locked",
            "restricted",
            "private",
            "security",
            "biometric",
            "clients must know",
            "no street signage",
            "permission",
        ),
        reason="Prose suggests permission, cover, force, or a key is needed.",
    ),
    PlaceKeywordRule(
        tag="urban_dense",
        category="place_environment",
        keywords=("city", "district", "arcology", "tower", "megatower", "urban"),
        reason="Prose suggests dense built environment.",
    ),
    PlaceKeywordRule(
        tag="urban_sparse",
        category="place_environment",
        keywords=("suburb", "outskirts", "low-density"),
        reason="Prose suggests low-density built environment.",
    ),
    PlaceKeywordRule(
        tag="rural",
        category="place_environment",
        keywords=("farm", "village", "countryside", "rural"),
        reason="Prose suggests settled countryside.",
    ),
    PlaceKeywordRule(
        tag="wilderness",
        category="place_environment",
        keywords=("wilderness", "wilds", "untamed", "badlands"),
        reason="Prose suggests minimally settled terrain.",
    ),
    PlaceKeywordRule(
        tag="subterranean",
        category="place_environment",
        keywords=("underground", "tunnel", "basement", "bunker", "sewer"),
        reason="Prose suggests underground or buried environment.",
    ),
    PlaceKeywordRule(
        tag="underwater",
        category="place_environment",
        keywords=("underwater", "submerged", "aquatic"),
        reason="Prose suggests submerged or aquatic environment.",
    ),
    PlaceKeywordRule(
        tag="aerial",
        category="place_environment",
        keywords=("aerial", "sky", "airborne", "elevated"),
        reason="Prose suggests airborne, elevated, or height-dominant place.",
    ),
    PlaceKeywordRule(
        tag="mountainous",
        category="place_environment",
        keywords=("mountain", "cliff", "high-altitude"),
        reason="Prose suggests steep or high-altitude terrain.",
    ),
    PlaceKeywordRule(
        tag="forest",
        category="place_environment",
        keywords=("forest", "woods", "tree cover"),
        reason="Prose suggests dense tree or vegetation cover.",
    ),
    PlaceKeywordRule(
        tag="desert",
        category="place_environment",
        keywords=("desert", "mojave", "dune", "badlands"),
        reason="Prose suggests arid terrain.",
    ),
    PlaceKeywordRule(
        tag="polar",
        category="place_environment",
        keywords=("ice", "snow", "polar", "frozen"),
        reason="Prose suggests extreme cold, ice, or snow.",
    ),
    PlaceKeywordRule(
        tag="marshland",
        category="place_environment",
        keywords=("swamp", "marsh", "bog", "wetland"),
        reason="Prose suggests wetland or unstable wet ground.",
    ),
    PlaceKeywordRule(
        tag="coastal",
        category="place_environment",
        keywords=("coast", "shore", "bay", "port", "beach"),
        reason="Prose suggests shore, tide, port, beach, or sea access.",
    ),
    PlaceKeywordRule(
        tag="place_contested",
        category="place_threat",
        keywords=("contested", "rival", "turf war", "dispute", "occupation"),
        reason="Prose suggests active dispute, occupation, or factional pressure.",
    ),
    PlaceKeywordRule(
        tag="place_dangerous",
        category="place_threat",
        keywords=(
            "danger",
            "hazard",
            "gunfire",
            "gang",
            "hostile",
            "trap",
            "toxic",
            "mine",
            "ambush",
        ),
        reason="Prose suggests immediate or predictable harm.",
    ),
)

TYPE_RULES: Mapping[str, tuple[tuple[str, str, str], ...]] = {
    "vehicle": (
        (
            "transit",
            "place_function",
            "Place type is vehicle, suggesting route movement or transfers.",
        ),
    ),
    "virtual": (
        (
            "archive",
            "place_function",
            "Place type is virtual; review for data, memory, or evidence storage.",
        ),
    ),
}

PROSE_FIELDS: tuple[str, ...] = (
    "name",
    "type",
    "summary",
    "history",
    "current_status",
    "secrets",
    "extra_data",
)


def build_place_migration_manifest(
    cur: Any,
    *,
    slot: int,
    dbname: str,
) -> dict[str, Any]:
    """Build a read-only manifest for place tag backfill review."""

    registered_tags = _load_registered_place_tags(cur)
    place_rows = _load_place_rows(cur)
    legacy_tag_rows = _load_legacy_place_tag_rows(cur)
    return build_place_migration_manifest_from_rows(
        place_rows,
        legacy_tag_rows,
        registered_tags=registered_tags,
        slot=slot,
        dbname=dbname,
    )


def build_place_migration_manifest_from_rows(
    place_rows: Sequence[Mapping[str, Any]],
    legacy_tag_rows: Sequence[Mapping[str, Any]],
    *,
    registered_tags: Mapping[str, Mapping[str, Any]],
    slot: int,
    dbname: str,
) -> dict[str, Any]:
    """Build a manifest from preloaded rows for tests and callers."""

    counters: Counter[str] = Counter()
    operations: list[dict[str, Any]] = []
    places: dict[int, dict[str, Any]] = {}
    seen_operations: set[tuple[int, str, str, str]] = set()

    for row in place_rows:
        counters["places_scanned"] += 1
        _ensure_place_summary(places, row)
        for tag, category, reason in _type_candidates(row):
            _append_operation(
                operations,
                counters,
                places,
                seen_operations,
                _review_entity_tag_operation(
                    row,
                    operation_index=len(operations) + 1,
                    source={
                        "kind": "place_type",
                        "field": "type",
                        "value": str(row.get("type") or ""),
                    },
                    target_tag=tag,
                    target_category=category,
                    target_registered=tag in registered_tags,
                    reason=reason,
                ),
            )

        for rule, matches in _keyword_candidates(row):
            _append_operation(
                operations,
                counters,
                places,
                seen_operations,
                _review_entity_tag_operation(
                    row,
                    operation_index=len(operations) + 1,
                    source={
                        "kind": "prose_keyword",
                        "fields": [match["field"] for match in matches],
                        "matches": matches,
                    },
                    target_tag=rule.tag,
                    target_category=rule.category,
                    target_registered=rule.tag in registered_tags,
                    reason=rule.reason,
                ),
            )

    for row in legacy_tag_rows:
        counters["legacy_place_tag_rows"] += 1
        counters[f"legacy_category:{row['category']}"] += 1
        _ensure_place_summary(places, row)
        source_tag = str(row["tag"])
        mapped_tags = LEGACY_PLACE_AFFORDANCE_MAP.get(source_tag)
        if not mapped_tags:
            operation = _operation(
                row,
                operation_index=len(operations) + 1,
                operation_type="structured_remainder",
                source={
                    "kind": "legacy_entity_tag",
                    "tag_id": int(row["tag_id"]),
                    "tag": source_tag,
                    "category": str(row["category"]),
                },
                target={"entity_kind": "place", "entity_id": int(row["entity_id"])},
                reason=(
                    "Legacy place_affordance tag has no deterministic mapping; "
                    "review as prose, pair-tag, or future vocabulary."
                ),
            )
            _append_operation(operations, counters, places, seen_operations, operation)
            continue
        for target_tag in mapped_tags:
            target_row = registered_tags.get(target_tag)
            operation = _review_entity_tag_operation(
                row,
                operation_index=len(operations) + 1,
                source={
                    "kind": "legacy_entity_tag",
                    "tag_id": int(row["tag_id"]),
                    "tag": source_tag,
                    "category": str(row["category"]),
                },
                target_tag=target_tag,
                target_category=(str(target_row["category"]) if target_row else None),
                target_registered=target_row is not None,
                reason=(
                    f"Legacy place_affordance:{source_tag} maps to "
                    f"{target_tag}; review before inserting replacement tag."
                ),
            )
            _append_operation(operations, counters, places, seen_operations, operation)

    counters["operation_items"] = len(operations)
    return {
        "schema_version": PLACE_MANIFEST_SCHEMA_VERSION,
        "dry_run": True,
        "source": {
            "slot": slot,
            "dbname": dbname,
            "target_categories": sorted(TARGET_PLACE_CATEGORIES),
            "legacy_categories": list(LEGACY_PLACE_CATEGORIES),
            "source_fields": list(PROSE_FIELDS),
        },
        "counters": dict(sorted(counters.items())),
        "places": sorted(
            places.values(),
            key=lambda item: (str(item["place_name"]).lower(), item["place_id"]),
        ),
        "operations": operations,
        "review_policy": {
            "ready": "No place manifest operations are auto-ready.",
            "review_required": (
                "Place tags are compositional; prose-derived candidates require "
                "human review before any future apply path consumes them."
            ),
            "destructive_mutations": (
                "This manifest performs no writes and does not authorize "
                "clearing legacy tags or removing resolver shims."
            ),
        },
    }


def _append_operation(
    operations: list[dict[str, Any]],
    counters: Counter[str],
    places: dict[int, dict[str, Any]],
    seen_operations: set[tuple[int, str, str, str]],
    operation: dict[str, Any],
) -> None:
    place_id = int(operation["place_id"])
    target = operation.get("target", {})
    source = operation.get("source", {})
    dedupe_key = (
        place_id,
        str(operation["operation_type"]),
        str(target.get("category") or source.get("category")),
        str(target.get("tag") or source.get("tag")),
    )
    if dedupe_key in seen_operations:
        counters["duplicate_candidate_operations"] += 1
        return
    seen_operations.add(dedupe_key)
    operations.append(operation)
    counters[f"{operation['operation_type']}_operations"] += 1
    if operation.get("review_required"):
        counters["review_required_operations"] += 1
    if target.get("target_registered") is False:
        counters["missing_target_tag_operations"] += 1
    if operation["operation_type"] == "review_entity_tag":
        counters["candidate_entity_tags"] += 1
    place = places[place_id]
    place["operations"].append(operation["operation_id"])
    if operation.get("review_required"):
        place["review_required_operations"] += 1


def _review_entity_tag_operation(
    row: Mapping[str, Any],
    *,
    operation_index: int,
    source: Mapping[str, Any],
    target_tag: str,
    target_category: str | None,
    target_registered: bool,
    reason: str,
) -> dict[str, Any]:
    return _operation(
        row,
        operation_index=operation_index,
        operation_type="review_entity_tag",
        source=source,
        target={
            "entity_kind": "place",
            "entity_id": int(row["entity_id"]),
            "category": target_category,
            "tag": target_tag,
            "target_registered": target_registered,
        },
        reason=reason,
    )


def _operation(
    row: Mapping[str, Any],
    *,
    operation_index: int,
    operation_type: str,
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    reason: str,
) -> dict[str, Any]:
    place_id = int(row["place_id"])
    place_name = str(row["place_name"])
    target_tag = str(target.get("tag") or "remainder")
    return {
        "operation_id": f"place-{operation_index:04d}-{place_id}-{target_tag}",
        "operation_type": operation_type,
        "status": "review_required",
        "review_required": True,
        "place_id": place_id,
        "place_name": place_name,
        "entity_id": int(row["entity_id"]),
        "source": dict(source),
        "target": dict(target),
        "confidence": "suggested",
        "reason": reason,
    }


def _ensure_place_summary(
    places: dict[int, dict[str, Any]],
    row: Mapping[str, Any],
) -> None:
    place_id = int(row["place_id"])
    places.setdefault(
        place_id,
        {
            "place_id": place_id,
            "place_name": str(row["place_name"]),
            "entity_id": int(row["entity_id"]),
            "type": str(row.get("type") or ""),
            "operations": [],
            "review_required_operations": 0,
        },
    )


def _type_candidates(row: Mapping[str, Any]) -> Iterable[tuple[str, str, str]]:
    place_type = str(row.get("type") or "")
    return TYPE_RULES.get(place_type, ())


def _keyword_candidates(
    row: Mapping[str, Any],
) -> Iterable[tuple[PlaceKeywordRule, list[dict[str, Any]]]]:
    field_text = _place_field_text(row)
    for rule in KEYWORD_RULES:
        matches = _matches_for_rule(rule, field_text)
        if matches:
            yield rule, matches


def _matches_for_rule(
    rule: PlaceKeywordRule,
    field_text: Mapping[str, str],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for field, text in field_text.items():
        matched_keywords = [
            keyword for keyword in rule.keywords if _keyword_hit(keyword, text)
        ]
        if not matched_keywords:
            continue
        matches.append(
            {
                "field": field,
                "keywords": sorted(set(matched_keywords)),
                "excerpt": _excerpt(text, matched_keywords[0]),
            }
        )
    return matches


def _keyword_hit(keyword: str, text: str) -> bool:
    return _keyword_match(keyword, text) is not None


def _keyword_match(keyword: str, text: str) -> re.Match[str] | None:
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(keyword.lower())}(?![A-Za-z0-9_])"
    return re.search(pattern, text.lower())


def _place_field_text(row: Mapping[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {
        "name": str(row.get("place_name") or ""),
        "type": str(row.get("type") or ""),
    }
    for field in ("summary", "history", "current_status", "secrets"):
        values[field] = str(row.get(field) or "")
    values["extra_data"] = _stringify_extra_data(row.get("extra_data"))
    return {key: value for key, value in values.items() if value.strip()}


def _stringify_extra_data(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return str(value)


def _excerpt(text: str, keyword: str, *, radius: int = 80) -> str:
    match = _keyword_match(keyword, text)
    if match is None:
        return text[: radius * 2].strip()
    index = match.start()
    start = max(0, index - radius)
    end = min(len(text), index + len(keyword) + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def _load_registered_place_tags(cur: Any) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT t.tag,
               t.category,
               t.deprecated,
               t.synonym_for
        FROM tags t
        JOIN tag_category_registry r
          ON r.category = t.category
        WHERE r.entity_kind = 'place'::entity_kind
          AND r.deprecated = FALSE
          AND t.deprecated = FALSE
          AND t.synonym_for IS NULL
          AND t.category = ANY(%s)
        """,
        (list(TARGET_PLACE_CATEGORIES),),
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


def _load_place_rows(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT p.id AS place_id,
               p.name AS place_name,
               e.id AS entity_id,
               p.type::text AS type,
               p.summary,
               p.history,
               p.current_status,
               p.secrets,
               p.extra_data
        FROM places p
        JOIN entities e ON e.id = p.entity_id
        WHERE e.kind = 'place'::entity_kind
        ORDER BY lower(p.name), p.id
        """
    )
    return [_normalize_place_row(row) for row in cur.fetchall()]


def _load_legacy_place_tag_rows(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT p.id AS place_id,
               p.name AS place_name,
               e.id AS entity_id,
               p.type::text AS type,
               t.id AS tag_id,
               t.tag,
               t.category
        FROM entity_tags et
        JOIN tags t ON t.id = et.tag_id
        JOIN entities e ON e.id = et.entity_id
        JOIN places p ON p.entity_id = e.id
        WHERE et.cleared_at IS NULL
          AND e.kind = 'place'::entity_kind
          AND t.category = ANY(%s)
        ORDER BY lower(p.name), p.id, t.category, t.tag
        """,
        (list(LEGACY_PLACE_CATEGORIES),),
    )
    return [_normalize_place_row(row) for row in cur.fetchall()]


def _normalize_place_row(row: Any) -> dict[str, Any]:
    if isinstance(row, MappingABC):
        getter = row.get
    else:

        def getter(key: str, default: Any = None) -> Any:
            return getattr(row, key, default)

    return {
        "place_id": int(getter("place_id")),
        "place_name": str(getter("place_name")),
        "entity_id": int(getter("entity_id")),
        "type": str(getter("type", "")),
        "summary": getter("summary"),
        "history": getter("history"),
        "current_status": getter("current_status"),
        "secrets": getter("secrets"),
        "extra_data": getter("extra_data"),
        "tag_id": getter("tag_id"),
        "tag": getter("tag"),
        "category": getter("category"),
    }
