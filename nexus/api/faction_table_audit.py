"""Read-only audit for migrating legacy faction columns into Orrery substrate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
import re
from typing import Any, Mapping, Optional


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
LEGACY_TAG_CATEGORIES = ("operational_secrecy", "state")
RUNTIME_WRITE_SURFACES = (
    "nexus/api/db_converters.py::create_new_faction",
    "nexus/api/commit_handler_sync.py::create_new_faction_sync",
    "nexus/api/commit_handler.py::commit_state_updates",
    "nexus/api/commit_handler_sync.py::commit_state_updates_sync",
    "nexus/agents/logon/apex_schema.py::NewFaction",
    "nexus/agents/logon/apex_schema.py::FactionStateUpdate",
    "nexus/api/lore_adapter.py::extract_state_updates",
)

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

    faction_rows = _fetch_faction_rows(cur)
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
        "keep_columns": list(KEEP_FACTION_COLUMNS),
        "runtime_write_surfaces": list(RUNTIME_WRITE_SURFACES),
        "counters": counters,
        "non_null_counts": non_null_counts,
        "legacy_tag_rows": [asdict(row) for row in legacy_tags],
        "factions": [_entry_to_dict(entry) for entry in entries],
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


def _fetch_faction_rows(cur: Any) -> list[Mapping[str, Any]]:
    cur.execute(
        """
        SELECT
            id,
            name,
            entity_id,
            ideology,
            history,
            current_activity,
            hidden_agenda,
            territory,
            primary_location,
            power_level,
            resources
        FROM factions
        ORDER BY id
        """
    )
    return list(cur.fetchall())


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
        "manual_review_items": manual_review_items,
        "ambiguous_resource_values": ambiguous_resource_values,
        "active_claim_edges": sum(
            entry.existing_pair_tags.get("claims", 0) for entry in entries
        ),
        "active_operates_from_edges": sum(
            entry.existing_pair_tags.get("operates_from", 0) for entry in entries
        ),
        "legacy_operational_secrecy_tags": sum(
            1 for row in legacy_tags if row.category == "operational_secrecy"
        ),
        "legacy_faction_state_tags": sum(
            1 for row in legacy_tags if row.category == "state"
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
    elif numeric > 0.10:
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
    if "network" in _tokens(text):
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
    if row.category == "operational_secrecy":
        normalized = _normalize_token(row.tag)
        tag = OPERATIONAL_MODE_ALIASES.get(normalized, normalized)
        if tag in OPERATIONAL_MODE_TAGS:
            return [
                FactionMappingCandidate(
                    source_column="entity_tags_current.operational_secrecy",
                    source_value=row.tag,
                    target_kind="entity_tag",
                    target_category="operational_mode",
                    target_tag=tag,
                    confidence="deterministic" if normalized == tag else "suggested",
                    review_required=normalized != tag,
                    reason=(
                        "Legacy operational_secrecy tag maps to " "operational_mode."
                    ),
                )
            ]
        return [
            FactionMappingCandidate(
                source_column="entity_tags_current.operational_secrecy",
                source_value=row.tag,
                target_kind="structured_remainder",
                target_category="operational_mode",
                confidence="manual_review",
                review_required=True,
                reason="Unknown operational_secrecy value needs manual mapping.",
            )
        ]
    if row.category == "state":
        return [
            FactionMappingCandidate(
                source_column="entity_tags_current.state",
                source_value=row.tag,
                target_kind="structured_remainder",
                confidence="manual_review",
                review_required=True,
                reason=(
                    "Faction-only state has no canonical replacement; "
                    "decompose into power_status, agenda, pair-tags, events, "
                    "or prose."
                ),
            )
        ]
    return []


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


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", value.lower()))


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9_])" + re.escape(phrase.lower()) + r"(?![a-z0-9_])"
    return re.search(pattern, text.lower()) is not None


def _match_controlled_values(text: str, allowed: frozenset[str]) -> list[str]:
    normalized = _normalize_token(text)
    if normalized in allowed:
        return [normalized]
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
