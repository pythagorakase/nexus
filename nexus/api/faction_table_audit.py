"""Read-only audit for migrating legacy faction columns into Orrery substrate."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping as MappingABC
from dataclasses import asdict, dataclass, field
from decimal import Decimal
import hashlib
import importlib
import re
from typing import Any, Mapping, Optional, Sequence


FACTION_MANIFEST_SCHEMA_VERSION = "faction-migration-manifest.v1"
FACTION_APPLY_SCHEMA_VERSION = "faction-migration-apply.v1"
FACTION_MIGRATION_SOURCE_KIND = "system"
FACTION_CATEGORY_CARDINALITY = {
    "ideology": "multi",
    "resource_base": "multi",
    "legitimacy": "exclusive",
    "operational_mode": "exclusive",
    "power_status": "exclusive",
    "agenda": "multi",
}
EXCLUSIVE_FACTION_CATEGORIES = frozenset(
    category
    for category, cardinality in FACTION_CATEGORY_CARDINALITY.items()
    if cardinality == "exclusive"
)
_CATEGORY_REFACTOR = importlib.import_module(
    "migrations.043_orrery_category_refactor_phase1"
)
LEGACY_CATEGORY_REPLACEMENTS: dict[str, tuple[str, ...]] = {
    legacy_category: tuple(replacement_categories or ())
    for (
        legacy_category,
        entity_kind,
        replacement_categories,
    ) in _CATEGORY_REFACTOR.DEPRECATED_CATEGORY_REPLACEMENTS
    if entity_kind == "faction"
}
LEGACY_TAG_CATEGORIES = tuple(LEGACY_CATEGORY_REPLACEMENTS)

LEGACY_FACTION_COLUMNS = (
    "ideology",
    "history",
    "current_activity",
    "hidden_agenda",
    "territory",
    "power_level",
    "resources",
)
KEEP_FACTION_COLUMNS = (
    "id",
    "name",
    "entity_id",
    "summary",
    "primary_location",
    "created_at",
    "updated_at",
    "extra_data",
)

# Tag values mirror docs/orrery_faction_vocabulary.md. Migration 043 owns the
# category registry, but the faction tag-value bank is still a design document.
IDEOLOGY_TAGS = frozenset(
    {
        "authoritarian",
        "egalitarian",
        "traditionalist",
        "progressive",
        "theocratic",
        "secularist",
        "nationalist",
        "cosmopolitan",
        "imperial",
        "communalist",
        "mercantilist",
        "technocratic",
        "revolutionary",
        "restorationist",
        "isolationist",
    }
)
RESOURCE_BASE_TAGS = frozenset(
    {
        "capital",
        "force",
        "information",
        "faith",
        "industry",
        "labor",
        "territory",
        "patronage",
        "bureaucracy",
        "technology",
        "specialized_knowledge",
        "criminal_network",
        "supply_lines",
        "mobility",
    }
)
OPERATIONAL_MODE_TAGS = frozenset({"overt", "covert", "hybrid"})
LEGITIMACY_TAGS = frozenset(
    {
        "state_recognized",
        "customary",
        "tolerated",
        "shadow_legal",
        "underground",
        "outlaw",
        "contested",
    }
)
POWER_STATUS_TAGS = frozenset(
    {
        "dominant",
        "ascending",
        "stable",
        "pressured",
        "declining",
        "fragile",
        "collapsed",
    }
)
AGENDA_TAGS = frozenset(
    {
        "expand_control",
        "consolidate_control",
        "infiltrate",
        "seize_leadership",
        "settle_succession",
        "recover_losses",
        "negotiate",
        "mobilize",
        "investigate",
        "recruit",
        "extract_resources",
        "sabotage",
        "suppress_dissent",
        "conceal_exposure",
        "reform_internal",
        "secure_alliance",
        "enforce_claim",
        "protect_asset",
        "retaliate",
    }
)
# Hand-curated from docs/orrery_faction_vocabulary.md plus the observed slot-2
# legacy scan on 2026-05-26. Aliases stay reviewable unless already canonical.
LEGACY_IDEOLOGY_ALIASES = {
    "anarchist_collective": ("egalitarian", "communalist"),
    "esoteric_metaphysical": ("theocratic",),
    "mutual_aid_norms": ("communalist", "egalitarian"),
    "transhumanist_program": ("technocratic", "progressive"),
}
LEGACY_LEGITIMACY_ALIASES = {
    "recognized": ("state_recognized",),
    "sanctioned": ("state_recognized",),
    "chartered": ("state_recognized",),
    "legal": ("state_recognized",),
    "custom": ("customary",),
    "customary": ("customary",),
    "tolerated": ("tolerated",),
    "gray_legal": ("shadow_legal",),
    "grey_legal": ("shadow_legal",),
    "shadow": ("shadow_legal",),
    "shadow_legal": ("shadow_legal",),
    "criminal_underground": ("outlaw",),
    "proscribed": ("outlaw",),
    "outlawed": ("outlaw",),
    "outlaw": ("outlaw",),
    "underground": ("underground",),
    "contested": ("contested",),
}
LEGACY_RESOURCE_ALIASES = {
    "barter_economy": ("capital",),
    "information_intensive": ("information",),
    "materiel_stockpile": ("force", "supply_lines"),
    "patron_dependent": ("patronage",),
    "salvage_economy": ("industry", "supply_lines"),
}
LEGACY_HIDDEN_AGENDA_ALIASES = {
    "covert_loyalty_play": ("infiltrate", "secure_alliance"),
    "expansionist_ambition": ("expand_control",),
    "schismatic_internal_threat": ("suppress_dissent", "settle_succession"),
}
LEGACY_AGENDA_ALIASES = {
    "revanchist": "recover_losses",
    "infiltration": "infiltrate",
    "coup": "seize_leadership",
    "succession": "settle_succession",
    "expansion": "expand_control",
    "consolidation": "consolidate_control",
}
OPERATIONAL_MODE_ALIASES = {
    "hidden": "covert",
    "secretive": "covert",
    "secret": "covert",
    "underground": "covert",
    "compartmented": "covert",
    "cellular_clandestine": "covert",
    "public": "overt",
    "open": "overt",
}
RESOURCE_KEYWORDS = {
    "capital": (
        "capital",
        "money",
        "credit",
        "wealth",
        "finance",
        "cash",
        "funding",
    ),
    "force": (
        "force",
        "fighters",
        "guards",
        "troops",
        "enforcers",
        "weapons",
        "military",
        "soldiers",
    ),
    "information": (
        "information",
        "intelligence",
        "intel",
        "archives",
        "surveillance",
        "secrets",
        "informants",
    ),
    "faith": ("faith", "religious", "ritual", "sacred", "pilgrim", "donor"),
    "industry": (
        "industry",
        "workshops",
        "factories",
        "production",
        "craft",
        "manufacturing",
    ),
    "labor": ("labor", "workers", "volunteers", "conscripts", "members"),
    "territory": (
        "territory",
        "land",
        "estate",
        "district",
        "region",
        "holdings",
    ),
    "patronage": ("patronage", "sponsors", "donors", "backers", "subsidy"),
    "bureaucracy": ("bureaucracy", "records", "offices", "permits"),
    "technology": ("technology", "machines", "infrastructure", "engineered"),
    "specialized_knowledge": (
        "knowledge",
        "scholarship",
        "lore",
        "expertise",
        "doctrine",
        "trade secrets",
    ),
    "criminal_network": (
        "criminal",
        "smuggling",
        "black market",
        "fences",
        "racket",
        "illicit",
    ),
    "supply_lines": (
        "supply",
        "logistics",
        "warehousing",
        "transport",
        "food",
        "fuel",
    ),
    "mobility": (
        "ships",
        "vehicles",
        "mounts",
        "portals",
        "couriers",
        "roads",
        "fleet",
    ),
}
NETWORK_AMBIGUOUS_RESOURCE_TAGS = (
    "criminal_network",
    "information",
    "patronage",
)


@dataclass(frozen=True, slots=True)
class FactionMappingCandidate:
    """One proposed destination for a legacy faction datum."""

    source_column: str
    source_value: Optional[str]
    target_kind: str
    target_category: Optional[str] = None
    target_tag: Optional[str] = None
    target_pair_tag: Optional[str] = None
    confidence: str = "manual_review"
    review_required: bool = True
    reason: str = ""


@dataclass(frozen=True, slots=True)
class LegacyTagRow:
    """Existing legacy tag row relevant to faction migration."""

    faction_id: int
    faction_name: str
    entity_id: int
    category: str
    tag: str


@dataclass(slots=True)
class FactionAuditEntry:
    """Audit result for one faction row."""

    faction_id: int
    faction_name: str
    entity_id: Optional[int]
    obsolete_columns: dict[str, Any]
    existing_pair_tags: dict[str, int] = field(default_factory=dict)
    legacy_tags: list[LegacyTagRow] = field(default_factory=list)
    mapping_candidates: list[FactionMappingCandidate] = field(default_factory=list)

    @property
    def review_required(self) -> bool:
        """Return True when any candidate must be inspected by a human."""

        return any(candidate.review_required for candidate in self.mapping_candidates)


def build_faction_table_audit(cur: Any) -> dict[str, Any]:
    """Build a read-only dry-run audit for legacy faction table cleanup."""

    existing_columns = _fetch_existing_faction_columns(cur)
    faction_rows = _fetch_faction_rows(cur, existing_columns=existing_columns)
    pair_counts = _fetch_pair_tag_counts(cur)
    legacy_tags = _fetch_legacy_tag_rows(cur)
    legacy_tags_by_entity = _group_legacy_tags_by_entity(legacy_tags)

    entries: list[FactionAuditEntry] = []
    non_null_counts = {column: 0 for column in LEGACY_FACTION_COLUMNS}
    for row in faction_rows:
        obsolete_values = _obsolete_values(row)
        for column, value in obsolete_values.items():
            if _has_value(value):
                non_null_counts[column] += 1
        entity_id = _coerce_optional_int(_row_value(row, "entity_id"))
        entry = audit_faction_row(
            row,
            existing_pair_tags=pair_counts.get(entity_id or -1, {}),
            legacy_tags=legacy_tags_by_entity.get(entity_id or -1, []),
        )
        entries.append(entry)

    counters = _build_counters(entries, non_null_counts, legacy_tags)
    return {
        "dry_run": True,
        "source_columns": list(LEGACY_FACTION_COLUMNS),
        "available_source_columns": [
            column for column in LEGACY_FACTION_COLUMNS if column in existing_columns
        ],
        "retired_source_columns": [
            column
            for column in LEGACY_FACTION_COLUMNS
            if column not in existing_columns
        ],
        "keep_columns": list(KEEP_FACTION_COLUMNS),
        "counters": counters,
        "non_null_counts": non_null_counts,
        "factions": [_entry_to_dict(entry) for entry in entries],
    }


def build_faction_migration_manifest(
    audit: Mapping[str, Any],
    *,
    slot: Optional[int] = None,
    dbname: Optional[str] = None,
) -> dict[str, Any]:
    """Convert a faction audit into explicit review/apply operations.

    The manifest is intentionally read-only: it names what a later migration
    could do, but never mutates tags, pair-tags, prose, or legacy columns.
    """

    operations: list[dict[str, Any]] = []
    factions: list[dict[str, Any]] = []
    for faction in audit.get("factions", []):
        faction_operations: list[dict[str, Any]] = []
        for candidate in faction.get("mapping_candidates", []):
            operation = _manifest_operation(faction, candidate)
            operations.append(operation)
            faction_operations.append(operation)

        factions.append(
            {
                "faction_id": faction.get("faction_id"),
                "faction_name": faction.get("faction_name"),
                "entity_id": faction.get("entity_id"),
                "operation_ids": [
                    operation["operation_id"] for operation in faction_operations
                ],
                "ready_operations": sum(
                    1
                    for operation in faction_operations
                    if operation["status"] == "ready"
                ),
                "review_required_operations": sum(
                    1
                    for operation in faction_operations
                    if operation["status"] != "ready"
                ),
            }
        )

    counters = _build_manifest_counters(operations)
    return {
        "schema_version": FACTION_MANIFEST_SCHEMA_VERSION,
        "dry_run": True,
        "source": {
            "slot": slot,
            "dbname": dbname,
            "audit_counters": dict(audit.get("counters") or {}),
            "source_columns": list(audit.get("source_columns") or []),
            "keep_columns": list(audit.get("keep_columns") or []),
        },
        "review_policy": {
            "ready": (
                "Only deterministic entity-tag candidates that require no review "
                "are apply-ready."
            ),
            "review_required": (
                "Suggested, ambiguous, prose, pair-tag, structured remainder, "
                "and no-replacement operations need human review before any "
                "apply script consumes them."
            ),
            "destructive_mutations": (
                "This manifest performs no writes and does not authorize column "
                "drops; destructive work needs a later migration with backup or "
                "test-slot scoping."
            ),
        },
        "counters": counters,
        "factions": factions,
        "operations": operations,
    }


def apply_faction_migration_manifest(
    cur: Any,
    manifest: Mapping[str, Any],
    *,
    dry_run: bool = True,
    source_kind: str = FACTION_MIGRATION_SOURCE_KIND,
) -> dict[str, Any]:
    """Apply deterministic faction manifest operations to ``entity_tags``.

    The apply phase intentionally consumes only ready ``insert_entity_tag``
    operations. Pair-tags, prose preservation, legacy tag drops, structured
    remainders, and any operation that still needs review are reported as
    skipped. Destructive faction-column cleanup remains out of scope.
    """

    if manifest.get("schema_version") != FACTION_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            "Faction apply requires "
            f"{FACTION_MANIFEST_SCHEMA_VERSION}; got "
            f"{manifest.get('schema_version')!r}"
        )

    operations = list(manifest.get("operations") or [])
    counters: Counter[str] = Counter()
    counters["operation_items"] = len(operations)
    applied_operations: list[dict[str, Any]] = []

    _validate_entity_tag_source_kind(cur, source_kind)
    allowed_categories = _load_faction_allowed_categories(cur)
    if not allowed_categories:
        raise ValueError("No Orrery tag categories registered for factions")
    world_time = _load_current_world_time(cur)
    planned_entity_tags: set[tuple[int, int]] = set()

    for operation in operations:
        operation_type = str(operation.get("operation_type") or "")
        status = str(operation.get("status") or "")
        if status != "ready" or bool(operation.get("review_required", True)):
            counters["review_required_operations_skipped"] += 1
            applied_operations.append(
                _apply_operation_result(
                    operation,
                    status="skipped_review_required",
                )
            )
            continue
        if operation_type != "insert_entity_tag":
            counters["non_entity_tag_operations_skipped"] += 1
            applied_operations.append(
                _apply_operation_result(
                    operation,
                    status="skipped_non_entity_tag_operation",
                )
            )
            continue

        counters["ready_entity_tag_operations"] += 1
        target = _coerce_entity_tag_target(operation)
        tag_row = _lookup_apply_tag(
            cur,
            tag=target["tag"],
            category=target["category"],
        )
        tag_id = int(_row_value(tag_row, "id"))
        category = str(_row_value(tag_row, "category"))
        entity_id = int(target["entity_id"])

        if category not in allowed_categories:
            raise ValueError(
                f"Orrery tag {target['tag']!r} has category {category!r}, "
                "which is not registered for factions"
            )
        _validate_faction_entity(cur, entity_id)

        entity_tag_key = (entity_id, tag_id)
        base_result = _apply_operation_result(
            operation,
            entity_id=entity_id,
            tag_id=tag_id,
            category=category,
            tag=target["tag"],
        )
        if entity_tag_key in planned_entity_tags:
            counters["duplicate_ready_operations_skipped"] += 1
            applied_operations.append(
                {
                    **base_result,
                    "status": "skipped_duplicate_ready_operation",
                }
            )
            continue

        existing_entity_tag_id = _active_entity_tag_id(
            cur,
            entity_id=entity_id,
            tag_id=tag_id,
        )
        if existing_entity_tag_id is not None:
            counters["entity_tags_already_present"] += 1
            planned_entity_tags.add(entity_tag_key)
            applied_operations.append(
                {
                    **base_result,
                    "status": "already_present",
                    "entity_tag_id": existing_entity_tag_id,
                }
            )
            continue

        sibling_tags = _active_exclusive_sibling_tags(
            cur,
            entity_id=entity_id,
            category=category,
            tag_id=tag_id,
        )
        if sibling_tags:
            counters["blocked_existing_sibling_operations"] += 1
            applied_operations.append(
                {
                    **base_result,
                    "status": "blocked_existing_sibling",
                    "existing_sibling_tags": sibling_tags,
                }
            )
            continue

        planned_entity_tags.add(entity_tag_key)
        if dry_run:
            counters["entity_tags_would_insert"] += 1
            applied_operations.append(
                {
                    **base_result,
                    "status": "would_insert",
                }
            )
            continue

        inserted_id = _insert_entity_tag_operation(
            cur,
            entity_id=entity_id,
            tag_id=tag_id,
            world_time=world_time,
            source_kind=source_kind,
        )
        if inserted_id is None:
            counters["entity_tags_already_present"] += 1
            applied_operations.append(
                {
                    **base_result,
                    "status": "already_present",
                }
            )
            continue
        counters["entity_tags_inserted"] += 1
        applied_operations.append(
            {
                **base_result,
                "status": "inserted",
                "entity_tag_id": inserted_id,
            }
        )

    for key in (
        "ready_entity_tag_operations",
        "entity_tags_would_insert",
        "entity_tags_inserted",
        "entity_tags_already_present",
        "duplicate_ready_operations_skipped",
        "blocked_existing_sibling_operations",
        "review_required_operations_skipped",
        "non_entity_tag_operations_skipped",
    ):
        counters.setdefault(key, 0)

    return {
        "schema_version": FACTION_APPLY_SCHEMA_VERSION,
        "manifest_schema_version": manifest.get("schema_version"),
        "dry_run": dry_run,
        "source_kind": source_kind,
        "source": manifest.get("source") or {},
        "policy": {
            "scope": (
                "Only deterministic ready insert_entity_tag operations are "
                "eligible for writes."
            ),
            "exclusive_categories": sorted(EXCLUSIVE_FACTION_CATEGORIES),
            "destructive_mutations": (
                "This command never clears legacy tags, rewrites pair-tags, "
                "edits faction prose columns, or drops schema columns."
            ),
        },
        "counters": dict(counters),
        "operations": applied_operations,
    }


def audit_faction_row(
    row: Mapping[str, Any],
    *,
    existing_pair_tags: Mapping[str, int],
    legacy_tags: list[LegacyTagRow],
) -> FactionAuditEntry:
    """Map one faction row into reviewable migration candidates."""

    obsolete_values = _obsolete_values(row)
    entry = FactionAuditEntry(
        faction_id=int(_row_value(row, "id")),
        faction_name=str(_row_value(row, "name") or ""),
        entity_id=_coerce_optional_int(_row_value(row, "entity_id")),
        obsolete_columns={
            key: _json_safe(value) for key, value in obsolete_values.items()
        },
        existing_pair_tags=dict(existing_pair_tags),
        legacy_tags=legacy_tags,
    )
    entry.mapping_candidates.extend(_map_ideology(obsolete_values["ideology"]))
    entry.mapping_candidates.extend(_map_history(obsolete_values["history"]))
    entry.mapping_candidates.extend(
        _map_agenda_text(
            "current_activity",
            obsolete_values["current_activity"],
            fallback_reason=(
                "Current activity is free prose. It may become agenda when it "
                "names an active campaign; otherwise preserve it as prose."
            ),
        )
    )
    entry.mapping_candidates.extend(
        _map_agenda_text(
            "hidden_agenda",
            obsolete_values["hidden_agenda"],
            fallback_reason=(
                "Hidden agenda is narrative prose unless it matches an accepted "
                "agenda anchor."
            ),
        )
    )
    entry.mapping_candidates.extend(
        _map_territory(obsolete_values["territory"], existing_pair_tags)
    )
    entry.mapping_candidates.extend(_map_power_level(obsolete_values["power_level"]))
    entry.mapping_candidates.extend(_map_resources(obsolete_values["resources"]))
    for tag_row in legacy_tags:
        entry.mapping_candidates.extend(_map_legacy_tag_row(tag_row))
    return entry


def _fetch_existing_faction_columns(cur: Any) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'factions'
          AND column_name = ANY(%s)
        """,
        (list(KEEP_FACTION_COLUMNS + LEGACY_FACTION_COLUMNS),),
    )
    return {str(_row_value(row, "column_name")) for row in cur.fetchall()}


def _fetch_faction_rows(
    cur: Any, *, existing_columns: set[str]
) -> list[Mapping[str, Any]]:
    select_columns = [
        _faction_column_select_expr(column, existing_columns=existing_columns)
        for column in (
            "id",
            "name",
            "entity_id",
            "ideology",
            "history",
            "current_activity",
            "hidden_agenda",
            "territory",
            "primary_location",
            "power_level",
            "resources",
        )
    ]
    cur.execute(
        f"""
        SELECT
            {', '.join(select_columns)}
        FROM factions
        ORDER BY id
        """
    )
    return list(cur.fetchall())


def _faction_column_select_expr(column: str, *, existing_columns: set[str]) -> str:
    if column in existing_columns:
        return column
    if column == "power_level":
        return "NULL::numeric AS power_level"
    return f"NULL::text AS {column}"


def _fetch_pair_tag_counts(cur: Any) -> dict[int, dict[str, int]]:
    cur.execute(
        """
        SELECT
            ept.subject_entity_id AS entity_id,
            pt.tag,
            COUNT(*)::int AS active_count
        FROM entity_pair_tags ept
        JOIN pair_tags pt ON pt.id = ept.pair_tag_id
        WHERE ept.cleared_at IS NULL
          AND pt.tag = ANY(%s)
          AND NOT pt.deprecated
        GROUP BY ept.subject_entity_id, pt.tag
        """,
        (["claims", "operates_from"],),
    )
    counts: dict[int, dict[str, int]] = {}
    for row in cur.fetchall():
        entity_id = int(_row_value(row, "entity_id"))
        tag = str(_row_value(row, "tag"))
        active_count = int(_row_value(row, "active_count"))
        counts.setdefault(entity_id, {})[tag] = active_count
    return counts


def _fetch_legacy_tag_rows(cur: Any) -> list[LegacyTagRow]:
    cur.execute(
        """
        SELECT
            f.id AS faction_id,
            f.name AS faction_name,
            f.entity_id,
            etc.category,
            etc.tag
        FROM entity_tags_current etc
        JOIN factions f ON f.entity_id = etc.entity_id
        WHERE etc.entity_kind = 'faction'
          AND etc.category = ANY(%s)
        ORDER BY f.id, etc.category, etc.tag
        """,
        (list(LEGACY_TAG_CATEGORIES),),
    )
    return [
        LegacyTagRow(
            faction_id=int(_row_value(row, "faction_id")),
            faction_name=str(_row_value(row, "faction_name")),
            entity_id=int(_row_value(row, "entity_id")),
            category=str(_row_value(row, "category")),
            tag=str(_row_value(row, "tag")),
        )
        for row in cur.fetchall()
    ]


def _group_legacy_tags_by_entity(
    rows: list[LegacyTagRow],
) -> dict[int, list[LegacyTagRow]]:
    grouped: dict[int, list[LegacyTagRow]] = {}
    for row in rows:
        grouped.setdefault(row.entity_id, []).append(row)
    return grouped


def _build_counters(
    entries: list[FactionAuditEntry],
    non_null_counts: Mapping[str, int],
    legacy_tags: list[LegacyTagRow],
) -> dict[str, int]:
    manual_review_items = 0
    ambiguous_resource_values = 0
    entity_tag_candidates = 0
    pair_tag_candidates = 0
    prose_remainders = 0
    no_replacement_items = 0
    for entry in entries:
        for candidate in entry.mapping_candidates:
            if candidate.review_required:
                manual_review_items += 1
            if candidate.target_kind == "entity_tag":
                entity_tag_candidates += 1
            elif candidate.target_kind == "pair_tag":
                pair_tag_candidates += 1
            elif candidate.target_kind in {
                "world_event_or_prose",
                "structured_remainder",
            }:
                prose_remainders += 1
            elif candidate.target_kind == "no_replacement":
                no_replacement_items += 1
        if any(
            candidate.source_column == "resources"
            and candidate.confidence == "ambiguous"
            for candidate in entry.mapping_candidates
        ):
            ambiguous_resource_values += 1

    return {
        "factions_scanned": len(entries),
        "factions_with_legacy_values": sum(
            1
            for entry in entries
            if any(_has_value(value) for value in entry.obsolete_columns.values())
        ),
        "non_null_legacy_values": sum(non_null_counts.values()),
        "candidate_entity_tags": entity_tag_candidates,
        "candidate_pair_tags": pair_tag_candidates,
        "prose_or_remainder_items": prose_remainders,
        "no_replacement_items": no_replacement_items,
        "manual_review_items": manual_review_items,
        "ambiguous_resource_values": ambiguous_resource_values,
        "active_claim_edges": sum(
            entry.existing_pair_tags.get("claims", 0) for entry in entries
        ),
        "active_operates_from_edges": sum(
            entry.existing_pair_tags.get("operates_from", 0) for entry in entries
        ),
        "legacy_tag_rows": len(legacy_tags),
        "legacy_ideology_axis_tags": sum(
            1 for row in legacy_tags if row.category == "ideology_axis"
        ),
        "legacy_power_posture_tags": sum(
            1 for row in legacy_tags if row.category == "power_posture"
        ),
        "legacy_legitimacy_status_tags": sum(
            1 for row in legacy_tags if row.category == "legitimacy_status"
        ),
        "legacy_operational_secrecy_tags": sum(
            1 for row in legacy_tags if row.category == "operational_secrecy"
        ),
        "legacy_resource_class_tags": sum(
            1 for row in legacy_tags if row.category == "resource_class"
        ),
        "legacy_hidden_agenda_class_tags": sum(
            1 for row in legacy_tags if row.category == "hidden_agenda_class"
        ),
        "legacy_history_class_tags": sum(
            1 for row in legacy_tags if row.category == "history_class"
        ),
    }


def _map_ideology(value: Any) -> list[FactionMappingCandidate]:
    text = _clean_text(value)
    if text is None:
        return []
    matched = _match_controlled_values(text, IDEOLOGY_TAGS)
    if matched:
        return [
            FactionMappingCandidate(
                source_column="ideology",
                source_value=text,
                target_kind="entity_tag",
                target_category="ideology",
                target_tag=tag,
                confidence=(
                    "deterministic" if _normalize_token(text) == tag else "suggested"
                ),
                review_required=_normalize_token(text) != tag,
                reason="Legacy ideology matches accepted faction ideology vocabulary.",
            )
            for tag in matched
        ]
    return [
        FactionMappingCandidate(
            source_column="ideology",
            source_value=text,
            target_kind="structured_remainder",
            target_category="ideology",
            confidence="manual_review",
            review_required=True,
            reason="Legacy ideology is free text and needs vocabulary review.",
        )
    ]


def _map_history(value: Any) -> list[FactionMappingCandidate]:
    text = _clean_text(value)
    if text is None:
        return []
    return [
        FactionMappingCandidate(
            source_column="history",
            source_value=text,
            target_kind="world_event_or_prose",
            confidence="manual_review",
            review_required=True,
            reason=(
                "Faction history should become world_events or summary prose, "
                "not tags."
            ),
        )
    ]


def _map_agenda_text(
    source_column: str,
    value: Any,
    *,
    fallback_reason: str,
) -> list[FactionMappingCandidate]:
    text = _clean_text(value)
    if text is None:
        return []
    normalized = _normalize_token(text)
    tag = LEGACY_AGENDA_ALIASES.get(normalized, normalized)
    if tag in AGENDA_TAGS:
        return [
            FactionMappingCandidate(
                source_column=source_column,
                source_value=text,
                target_kind="entity_tag",
                target_category="agenda",
                target_tag=tag,
                confidence="deterministic" if normalized == tag else "suggested",
                review_required=normalized != tag,
                reason="Legacy value matches an accepted agenda anchor.",
            )
        ]

    matched = _match_controlled_values(text, AGENDA_TAGS)
    if matched:
        return [
            FactionMappingCandidate(
                source_column=source_column,
                source_value=text,
                target_kind="entity_tag",
                target_category="agenda",
                target_tag=tag,
                confidence="suggested",
                review_required=True,
                reason="Legacy prose contains an accepted agenda anchor.",
            )
            for tag in matched
        ]

    return [
        FactionMappingCandidate(
            source_column=source_column,
            source_value=text,
            target_kind="structured_remainder",
            target_category="agenda",
            confidence="manual_review",
            review_required=True,
            reason=fallback_reason,
        )
    ]


def _map_territory(
    value: Any, existing_pair_tags: Mapping[str, int]
) -> list[FactionMappingCandidate]:
    text = _clean_text(value)
    candidates: list[FactionMappingCandidate] = []
    claim_count = int(existing_pair_tags.get("claims", 0))
    if claim_count:
        candidates.append(
            FactionMappingCandidate(
                source_column="territory",
                source_value=text,
                target_kind="entity_tag",
                target_category="resource_base",
                target_tag="territory",
                confidence="deterministic",
                review_required=False,
                reason=(
                    "Faction already has active claims(...) edges; "
                    "resource_base:territory can be seeded from substrate."
                ),
            )
        )
    if text is None:
        return candidates

    candidates.append(
        FactionMappingCandidate(
            source_column="territory",
            source_value=text,
            target_kind="pair_tag",
            target_pair_tag="claims",
            confidence="manual_review",
            review_required=True,
            reason=(
                "Territory prose must be resolved to concrete place targets "
                "before claims(faction -> place) can be written."
            ),
        )
    )
    candidates.append(
        FactionMappingCandidate(
            source_column="territory",
            source_value=text,
            target_kind="pair_tag",
            target_pair_tag="operates_from",
            confidence="manual_review",
            review_required=True,
            reason=(
                "Territory prose may describe bases or reach; review before "
                "writing operates_from(faction -> place)."
            ),
        )
    )
    if _mentions_territorial_capacity(text) and claim_count == 0:
        candidates.append(
            FactionMappingCandidate(
                source_column="territory",
                source_value=text,
                target_kind="entity_tag",
                target_category="resource_base",
                target_tag="territory",
                confidence="suggested",
                review_required=True,
                reason=(
                    "Legacy column explicitly names territorial control, but "
                    "no active claims(...) edge exists yet."
                ),
            )
        )
    return candidates


def _map_power_level(value: Any) -> list[FactionMappingCandidate]:
    if value is None:
        return []
    numeric = float(value)
    if numeric >= 0.85:
        tag = "dominant"
    elif numeric >= 0.70:
        tag = "ascending"
    elif numeric >= 0.45:
        tag = "stable"
    elif numeric >= 0.30:
        tag = "pressured"
    elif numeric >= 0.10:
        tag = "declining"
    elif numeric > 0.0:
        tag = "fragile"
    else:
        tag = "collapsed"
    return [
        FactionMappingCandidate(
            source_column="power_level",
            source_value=str(value),
            target_kind="entity_tag",
            target_category="power_status",
            target_tag=tag,
            confidence="suggested",
            review_required=True,
            reason=(
                "Numeric power_level lacks trajectory; suggested power_status "
                "is rank-only and should be reviewed before migration."
            ),
        )
    ]


def _map_resources(value: Any) -> list[FactionMappingCandidate]:
    text = _clean_text(value)
    if text is None:
        return []
    normalized = _normalize_token(text)
    if normalized in RESOURCE_BASE_TAGS:
        return [
            FactionMappingCandidate(
                source_column="resources",
                source_value=text,
                target_kind="entity_tag",
                target_category="resource_base",
                target_tag=normalized,
                confidence="deterministic",
                review_required=False,
                reason=(
                    "Legacy resources value matches accepted resource_base "
                    "vocabulary."
                ),
            )
        ]
    matched = [
        tag
        for tag, keywords in RESOURCE_KEYWORDS.items()
        if any(_contains_phrase(text, keyword) for keyword in keywords)
    ]
    if matched:
        return [
            FactionMappingCandidate(
                source_column="resources",
                source_value=text,
                target_kind="entity_tag",
                target_category="resource_base",
                target_tag=tag,
                confidence="suggested",
                review_required=True,
                reason="Legacy resources prose contains resource_base keywords.",
            )
            for tag in sorted(set(matched))
        ]
    if normalized == "network":
        return [
            FactionMappingCandidate(
                source_column="resources",
                source_value=text,
                target_kind="entity_tag",
                target_category="resource_base",
                target_tag=tag,
                confidence="ambiguous",
                review_required=True,
                reason=(
                    "Legacy 'network' is overloaded; choose the specific "
                    "resource_base reading manually."
                ),
            )
            for tag in NETWORK_AMBIGUOUS_RESOURCE_TAGS
        ]
    return [
        FactionMappingCandidate(
            source_column="resources",
            source_value=text,
            target_kind="structured_remainder",
            target_category="resource_base",
            confidence="manual_review",
            review_required=True,
            reason="Legacy resources are free text and need vocabulary review.",
        )
    ]


def _map_legacy_tag_row(row: LegacyTagRow) -> list[FactionMappingCandidate]:
    if row.category == "ideology_axis":
        return _map_controlled_legacy_tag_row(
            row,
            target_category="ideology",
            allowed_tags=IDEOLOGY_TAGS,
            aliases=LEGACY_IDEOLOGY_ALIASES,
            unknown_reason=(
                "Legacy ideology_axis tag has no direct canonical ideology "
                "reading; review before migration."
            ),
        )
    if row.category == "power_posture":
        return _map_controlled_legacy_tag_row(
            row,
            target_category="power_status",
            allowed_tags=POWER_STATUS_TAGS,
            aliases={},
            unknown_reason=(
                "Legacy power_posture tag is not an accepted power_status "
                "value; review trajectory and capacity before migration."
            ),
        )
    if row.category == "legitimacy_status":
        return _map_controlled_legacy_tag_row(
            row,
            target_category="legitimacy",
            allowed_tags=LEGITIMACY_TAGS,
            aliases=LEGACY_LEGITIMACY_ALIASES,
            unknown_reason=(
                "Legacy legitimacy_status tag needs manual legitimacy review."
            ),
        )
    if row.category == "operational_secrecy":
        return _map_controlled_legacy_tag_row(
            row,
            target_category="operational_mode",
            allowed_tags=OPERATIONAL_MODE_TAGS,
            aliases=OPERATIONAL_MODE_ALIASES,
            unknown_reason="Unknown operational_secrecy value needs manual mapping.",
        )
    if row.category == "resource_class":
        return _map_controlled_legacy_tag_row(
            row,
            target_category="resource_base",
            allowed_tags=RESOURCE_BASE_TAGS,
            aliases=LEGACY_RESOURCE_ALIASES,
            unknown_reason=(
                "Legacy resource_class tag needs manual resource_base review."
            ),
        )
    if row.category == "hidden_agenda_class":
        return _map_controlled_legacy_tag_row(
            row,
            target_category="agenda",
            allowed_tags=AGENDA_TAGS,
            aliases=LEGACY_HIDDEN_AGENDA_ALIASES,
            unknown_reason="Legacy hidden_agenda_class tag needs agenda review.",
        )
    if row.category == "history_class":
        return [
            FactionMappingCandidate(
                source_column="entity_tags_current.history_class",
                source_value=row.tag,
                target_kind="no_replacement",
                confidence="manual_review",
                review_required=True,
                reason=(
                    "Migration 043 marks history_class with no replacement; "
                    "preserve useful detail as world_events or prose before "
                    "dropping the legacy tag."
                ),
            )
        ]
    return [
        FactionMappingCandidate(
            source_column=f"entity_tags_current.{row.category}",
            source_value=row.tag,
            target_kind="structured_remainder",
            confidence="manual_review",
            review_required=True,
            reason="Unrecognized legacy faction tag category needs manual review.",
        )
    ]


def _map_controlled_legacy_tag_row(
    row: LegacyTagRow,
    *,
    target_category: str,
    allowed_tags: frozenset[str],
    aliases: Mapping[str, str | tuple[str, ...]],
    unknown_reason: str,
) -> list[FactionMappingCandidate]:
    source_column = f"entity_tags_current.{row.category}"
    normalized = _normalize_token(row.tag)
    alias = aliases.get(normalized)
    alias_tags: tuple[str, ...]
    if isinstance(alias, str):
        alias_tags = (alias,)
    else:
        alias_tags = alias or ()

    valid_alias_tags = tuple(tag for tag in alias_tags if tag in allowed_tags)
    if valid_alias_tags:
        return [
            FactionMappingCandidate(
                source_column=source_column,
                source_value=row.tag,
                target_kind="entity_tag",
                target_category=target_category,
                target_tag=tag,
                confidence="deterministic" if normalized == tag else "suggested",
                review_required=normalized != tag,
                reason=(
                    f"Legacy {row.category} tag maps to {target_category}; "
                    "review alias-derived readings before migration."
                ),
            )
            for tag in valid_alias_tags
        ]

    if normalized in allowed_tags:
        return [
            FactionMappingCandidate(
                source_column=source_column,
                source_value=row.tag,
                target_kind="entity_tag",
                target_category=target_category,
                target_tag=normalized,
                confidence="deterministic",
                review_required=False,
                reason=(
                    f"Legacy {row.category} tag already matches accepted "
                    f"{target_category} vocabulary."
                ),
            )
        ]

    matched = _match_controlled_values(row.tag, allowed_tags)
    if matched:
        return [
            FactionMappingCandidate(
                source_column=source_column,
                source_value=row.tag,
                target_kind="entity_tag",
                target_category=target_category,
                target_tag=tag,
                confidence="suggested",
                review_required=True,
                reason=(
                    f"Legacy {row.category} text contains accepted "
                    f"{target_category} vocabulary."
                ),
            )
            for tag in matched
        ]

    return [
        FactionMappingCandidate(
            source_column=source_column,
            source_value=row.tag,
            target_kind="structured_remainder",
            target_category=target_category,
            confidence="manual_review",
            review_required=True,
            reason=unknown_reason,
        )
    ]


def _manifest_operation(
    faction: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    target_kind = str(candidate.get("target_kind") or "manual_review")
    if target_kind == "entity_tag":
        apply_ready = _candidate_is_apply_ready(candidate) and (
            faction.get("entity_id") is not None
        )
        operation_type = "insert_entity_tag" if apply_ready else "review_entity_tag"
        status = "ready" if apply_ready else "review_required"
        target = {
            "entity_kind": "faction",
            "entity_id": faction.get("entity_id"),
            "category": candidate.get("target_category"),
            "tag": candidate.get("target_tag"),
        }
    elif target_kind == "pair_tag":
        operation_type = "resolve_pair_tag_target"
        status = "review_required"
        target = {
            "subject_entity_kind": "faction",
            "subject_entity_id": faction.get("entity_id"),
            "pair_tag": candidate.get("target_pair_tag"),
            "object_entity_id": None,
        }
    elif target_kind == "world_event_or_prose":
        operation_type = "preserve_prose"
        status = "review_required"
        target = {"destination": "world_event_or_summary_prose"}
    elif target_kind == "no_replacement":
        operation_type = "drop_legacy_tag_after_review"
        status = "review_required"
        target = {"replacement": None}
    elif target_kind == "structured_remainder":
        operation_type = "classify_structured_remainder"
        status = "review_required"
        target = {"target_category": candidate.get("target_category")}
    else:
        operation_type = "manual_review"
        status = "review_required"
        target = {}

    operation = {
        "operation_id": _manifest_operation_id(faction, candidate),
        "operation_type": operation_type,
        "status": status,
        "faction_id": faction.get("faction_id"),
        "faction_name": faction.get("faction_name"),
        "entity_id": faction.get("entity_id"),
        "source": {
            "column": candidate.get("source_column"),
            "value": candidate.get("source_value"),
        },
        "target": target,
        "confidence": candidate.get("confidence"),
        "review_required": status != "ready",
        "reason": _manifest_operation_reason(faction, candidate, status=status),
    }
    return operation


def _candidate_is_apply_ready(candidate: Mapping[str, Any]) -> bool:
    return (
        candidate.get("target_kind") == "entity_tag"
        and candidate.get("confidence") == "deterministic"
        and not bool(candidate.get("review_required", True))
        and bool(candidate.get("target_category"))
        and bool(candidate.get("target_tag"))
    )


def _manifest_operation_id(
    faction: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> str:
    parts = (
        str(faction.get("faction_id") or ""),
        str(faction.get("entity_id") or ""),
        str(candidate.get("source_column") or ""),
        str(candidate.get("source_value") or ""),
        str(candidate.get("target_kind") or ""),
        str(candidate.get("target_category") or ""),
        str(candidate.get("target_tag") or ""),
        str(candidate.get("target_pair_tag") or ""),
    )
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"faction-migration-{digest}"


def _build_manifest_counters(
    operations: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    counters = {
        "operation_items": len(operations),
        "ready_operations": 0,
        "review_required_operations": 0,
    }
    for operation in operations:
        operation_type = str(operation["operation_type"])
        counters[f"{operation_type}_operations"] = (
            counters.get(f"{operation_type}_operations", 0) + 1
        )
        if operation["status"] == "ready":
            counters["ready_operations"] += 1
        else:
            counters["review_required_operations"] += 1
    return counters


def _manifest_operation_reason(
    faction: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    status: str,
) -> str:
    reason = str(candidate.get("reason") or "")
    if (
        status != "ready"
        and candidate.get("target_kind") == "entity_tag"
        and faction.get("entity_id") is None
    ):
        suffix = "Faction row has no entity_id, so an entity_tag cannot be written."
        return f"{reason} {suffix}".strip()
    return reason


def _apply_operation_result(
    operation: Mapping[str, Any],
    *,
    status: str = "",
    entity_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
) -> dict[str, Any]:
    result = {
        "operation_id": operation.get("operation_id"),
        "operation_type": operation.get("operation_type"),
        "status": status,
        "faction_id": operation.get("faction_id"),
        "faction_name": operation.get("faction_name"),
        "source": operation.get("source") or {},
        "target": operation.get("target") or {},
    }
    if entity_id is not None:
        result["entity_id"] = entity_id
    if tag_id is not None:
        result["tag_id"] = tag_id
    if category is not None:
        result["category"] = category
    if tag is not None:
        result["tag"] = tag
    return result


def _coerce_entity_tag_target(operation: Mapping[str, Any]) -> dict[str, Any]:
    target = operation.get("target")
    if not isinstance(target, MappingABC):
        raise ValueError(
            f"Operation {operation.get('operation_id')!r} has no target mapping"
        )
    if target.get("entity_kind") != "faction":
        raise ValueError(
            f"Operation {operation.get('operation_id')!r} targets "
            f"entity_kind={target.get('entity_kind')!r}, expected 'faction'"
        )

    entity_id = target.get("entity_id")
    category = target.get("category")
    tag = target.get("tag")
    if entity_id is None:
        raise ValueError(
            f"Operation {operation.get('operation_id')!r} has no target entity_id"
        )
    if not category or not tag:
        raise ValueError(
            f"Operation {operation.get('operation_id')!r} must name category and tag"
        )
    return {
        "entity_id": int(entity_id),
        "category": str(category),
        "tag": str(tag),
    }


def _validate_entity_tag_source_kind(cur: Any, source_kind: str) -> None:
    cur.execute(
        """
        SELECT 1
        FROM pg_enum
        JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
        WHERE pg_type.typname = 'entity_tag_source_kind'
          AND pg_enum.enumlabel = %s
        """,
        (source_kind,),
    )
    if cur.fetchone() is None:
        raise ValueError(f"Unknown entity_tag_source_kind {source_kind!r}")


def _load_faction_allowed_categories(cur: Any) -> set[str]:
    cur.execute(
        """
        SELECT category
        FROM tag_category_registry
        WHERE entity_kind = 'faction'::entity_kind
        """
    )
    return {str(_row_value(row, "category")) for row in cur.fetchall()}


def _load_current_world_time(cur: Any) -> Any:
    cur.execute("SELECT max(world_time) AS world_time FROM chunk_metadata")
    row = cur.fetchone()
    if row is None:
        return None
    world_time = _row_value(row, "world_time")
    if world_time is None:
        return None
    return world_time


def _lookup_apply_tag(cur: Any, *, tag: str, category: str) -> Mapping[str, Any]:
    cur.execute(
        """
        SELECT id, tag, category
        FROM tags
        WHERE tag = %s
          AND category = %s
          AND NOT deprecated
          AND synonym_for IS NULL
        """,
        (tag, category),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(
            f"Unknown or deprecated faction tag {category}:{tag} in manifest"
        )
    return row


def _validate_faction_entity(cur: Any, entity_id: int) -> None:
    cur.execute(
        """
        SELECT id, kind::text AS kind
        FROM entities
        WHERE id = %s
        """,
        (entity_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Manifest targets missing entity_id={entity_id}")
    entity_kind = str(_row_value(row, "kind"))
    if entity_kind != "faction":
        raise ValueError(
            f"Manifest targets entity_id={entity_id} with kind={entity_kind!r}; "
            "expected 'faction'"
        )


def _active_entity_tag_id(cur: Any, *, entity_id: int, tag_id: int) -> Optional[int]:
    cur.execute(
        """
        SELECT id
        FROM entity_tags
        WHERE entity_id = %s
          AND tag_id = %s
          AND cleared_at IS NULL
        """,
        (entity_id, tag_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id"))


def _active_exclusive_sibling_tags(
    cur: Any,
    *,
    entity_id: int,
    category: str,
    tag_id: int,
) -> list[str]:
    if category not in EXCLUSIVE_FACTION_CATEGORIES:
        return []
    cur.execute(
        """
        SELECT t.tag
        FROM entity_tags et
        JOIN tags t ON t.id = et.tag_id
        WHERE et.entity_id = %s
          AND et.cleared_at IS NULL
          AND t.category = %s
          AND t.id <> %s
          AND NOT t.deprecated
        ORDER BY t.tag
        """,
        (entity_id, category, tag_id),
    )
    return [str(_row_value(row, "tag")) for row in cur.fetchall()]


def _insert_entity_tag_operation(
    cur: Any,
    *,
    entity_id: int,
    tag_id: int,
    world_time: Any,
    source_kind: str,
) -> Optional[int]:
    cur.execute(
        """
        INSERT INTO entity_tags (
            entity_id,
            tag_id,
            applied_at_world_time,
            source_kind
        )
        VALUES (
            %s,
            %s,
            %s,
            %s::entity_tag_source_kind
        )
        ON CONFLICT (entity_id, tag_id)
          WHERE cleared_at IS NULL
          DO NOTHING
        RETURNING id
        """,
        (entity_id, tag_id, world_time, source_kind),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(_row_value(row, "id"))


def _obsolete_values(row: Mapping[str, Any]) -> dict[str, Any]:
    return {column: _row_value(row, column) for column in LEGACY_FACTION_COLUMNS}


def _entry_to_dict(entry: FactionAuditEntry) -> dict[str, Any]:
    payload = asdict(entry)
    payload["review_required"] = entry.review_required
    payload["manual_review_items"] = sum(
        1 for candidate in entry.mapping_candidates if candidate.review_required
    )
    return payload


def _row_value(row: Mapping[str, Any], key: str) -> Any:
    return row[key]


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9_])" + re.escape(phrase.lower()) + r"(?![a-z0-9_])"
    return re.search(pattern, text.lower()) is not None


def _match_controlled_values(text: str, allowed: frozenset[str]) -> list[str]:
    normalized = _normalize_token(text)
    if normalized in allowed:
        return [normalized]
    # Match both prose spelling ("criminal network") and canonical spelling
    # ("criminal_network") so old free text can still point at tag anchors.
    matches = [tag for tag in allowed if _contains_phrase(text, tag.replace("_", " "))]
    matches.extend(tag for tag in allowed if _contains_phrase(text, tag))
    return sorted(set(matches))


def _mentions_territorial_capacity(text: str) -> bool:
    terms = (
        "controls",
        "controlled",
        "claims",
        "claimed",
        "holds",
        "held",
        "rules",
        "territory",
        "land",
        "district",
        "estate",
        "region",
        "zone",
    )
    return any(_contains_phrase(text, term) for term in terms)
