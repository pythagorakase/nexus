"""Generation-time registry validation for storyteller output.

Skald freely invents tag names (often ``category:name`` composites) when
updating state or emitting ``new_entities`` declaration hints. The
closed-vocabulary tag writers hard-error on unknown names -- but they run
inside the chunk COMMIT transaction, where the only outcome is a dead player
turn (M9 gate finding).

Faction update names have the same failure mode: prose aliases can look valid
while failing the commit handler's exact canonical lookup. This module walks a
parsed storyteller response and validates both identity and vocabulary fields
against live registries, so LOGON's structured-output validator can hand issues
back to the model while it still owns the turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import get_close_matches
import logging
from typing import Any, Callable, FrozenSet, List, Mapping, MutableSet, Optional, Tuple

from nexus.agents.orrery.declaration_validation import (
    collect_new_entity_declaration_vocabulary_issues,
)
from nexus.agents.orrery.tag_activity import active_entity_tag_at_world_time_sql
from nexus.agents.orrery.tag_library import (
    read_event_types,
    read_pair_tag_library,
    read_tag_library,
)
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.agents.orrery.tag_writer import (
    validate_pair_tag_endpoint,
    validate_tag_bestowal,
)

logger = logging.getLogger("nexus.logon.orrery_tag_validation")

_REPLACEMENT_ACTOR_TAG_FIELDS = (
    ("entity_tags_add", "applied_tags"),
    ("entity_tags_remove", "tags_to_clear"),
)
_REPLACEMENT_TARGET_TAG_FIELDS = (
    ("entity_tags_target_add", "applied_tags"),
    ("entity_tags_target_remove", "tags_to_clear"),
)
_REPLACEMENT_PAIR_TAG_FIELD = "entity_pair_tags_target_clear_inbound"


def _quoted_log_text(value: str) -> str:
    """Return one quoted, single-token-safe value for structured logs."""

    return ascii(value).replace("=", r"\x3d")


@dataclass(frozen=True)
class StorytellerVocabulary:
    """One validation pass's immutable snapshot of live storyteller catalogs."""

    tag_names_by_kind: Mapping[str, FrozenSet[str]]
    pair_tag_names: FrozenSet[str]
    event_types: FrozenSet[str]
    tag_reapplication_policies_by_kind: Mapping[str, Mapping[str, str]] = field(
        default_factory=dict
    )
    tag_clearance_kinds_by_kind: Mapping[str, Mapping[str, str]] = field(
        default_factory=dict
    )
    tag_default_durations_by_kind: Mapping[str, Mapping[str, timedelta]] = field(
        default_factory=dict
    )


def read_storyteller_vocabulary(dbname: str) -> StorytellerVocabulary:
    """Load each live vocabulary catalog once for one validation attempt."""

    tags_by_kind: dict[str, set[str]] = {
        "character": set(),
        "place": set(),
        "faction": set(),
    }
    policies_by_kind: dict[str, dict[str, str]] = {
        "character": {},
        "place": {},
        "faction": {},
    }
    clearance_kinds_by_kind: dict[str, dict[str, str]] = {
        "character": {},
        "place": {},
        "faction": {},
    }
    default_durations_by_kind: dict[str, dict[str, timedelta]] = {
        "character": {},
        "place": {},
        "faction": {},
    }
    for entry in read_tag_library(dbname):
        if entry.entity_kind in tags_by_kind:
            tags_by_kind[entry.entity_kind].add(entry.tag)
            if entry.reapplication_policy is not None:
                policies_by_kind[entry.entity_kind][
                    entry.tag
                ] = entry.reapplication_policy
            if entry.clearance_kind is not None:
                clearance_kinds_by_kind[entry.entity_kind][
                    entry.tag
                ] = entry.clearance_kind
            if entry.default_duration is not None:
                default_durations_by_kind[entry.entity_kind][
                    entry.tag
                ] = entry.default_duration
    return StorytellerVocabulary(
        tag_names_by_kind={
            kind: frozenset(tag_names) for kind, tag_names in tags_by_kind.items()
        },
        pair_tag_names=frozenset(read_pair_tag_library(dbname)),
        event_types=frozenset(read_event_types(dbname)),
        tag_reapplication_policies_by_kind={
            kind: dict(policies) for kind, policies in policies_by_kind.items()
        },
        tag_clearance_kinds_by_kind={
            kind: dict(clearance_kinds)
            for kind, clearance_kinds in clearance_kinds_by_kind.items()
        },
        tag_default_durations_by_kind={
            kind: dict(default_durations)
            for kind, default_durations in default_durations_by_kind.items()
        },
    )


def _bestowal_sites(
    response: Any,
    *,
    replacement_entity_kinds: Optional[
        Mapping[int, Tuple[Optional[str], Optional[str]]]
    ] = None,
) -> List[Tuple[str, str, OrreryTagBestowal]]:
    """Yield (path, entity_kind, bestowal) triples from a parsed response."""

    sites: List[Tuple[str, str, OrreryTagBestowal]] = []

    updates = getattr(response, "updates", None)
    if updates is not None:
        for array_name in ("characters", "places", "factions", "relationships"):
            entity_kind = array_name.removesuffix("s")
            for index, update in enumerate(getattr(updates, array_name)):
                tags_add = getattr(update, "tags_add", None)
                tags_clear = getattr(update, "tags_clear", None)
                if tags_add is not None or tags_clear is not None:
                    sites.append(
                        (
                            f"updates.{array_name}[{index}]",
                            entity_kind,
                            OrreryTagBestowal(
                                applied_tags=tags_add or [],
                                tags_to_clear=tags_clear or [],
                            ),
                        )
                    )

    state_updates = getattr(response, "state_updates", None)
    if state_updates is not None:
        for index, update in enumerate(getattr(state_updates, "characters", []) or []):
            bestowal = getattr(update, "orrery_tags", None)
            if bestowal is not None:
                sites.append(
                    (f"state_updates.characters[{index}]", "character", bestowal)
                )
        for index, update in enumerate(getattr(state_updates, "locations", []) or []):
            bestowal = getattr(update, "orrery_tags", None)
            if bestowal is not None:
                sites.append((f"state_updates.locations[{index}]", "place", bestowal))
        for index, update in enumerate(getattr(state_updates, "factions", []) or []):
            bestowal = getattr(update, "orrery_tags", None)
            if bestowal is not None:
                sites.append((f"state_updates.factions[{index}]", "faction", bestowal))

    for index, adjudication in enumerate(
        getattr(response, "orrery_adjudications", None) or []
    ):
        delta = getattr(adjudication, "replacement_state_delta", None)
        if delta is None:
            continue
        actor_kind, target_kind = (replacement_entity_kinds or {}).get(
            index, (None, None)
        )
        for field_name, bestowal_field in _REPLACEMENT_ACTOR_TAG_FIELDS:
            values = list(getattr(delta, field_name, None) or [])
            if values and actor_kind is not None:
                sites.append(
                    (
                        "orrery_adjudications"
                        f"[{index}].replacement_state_delta.{field_name}",
                        actor_kind,
                        OrreryTagBestowal(
                            applied_tags=(
                                values if bestowal_field == "applied_tags" else []
                            ),
                            tags_to_clear=(
                                values if bestowal_field == "tags_to_clear" else []
                            ),
                        ),
                    )
                )
        for field_name, bestowal_field in _REPLACEMENT_TARGET_TAG_FIELDS:
            values = list(getattr(delta, field_name, None) or [])
            if values and target_kind is not None:
                sites.append(
                    (
                        "orrery_adjudications"
                        f"[{index}].replacement_state_delta.{field_name}",
                        target_kind,
                        OrreryTagBestowal(
                            applied_tags=(
                                values if bestowal_field == "applied_tags" else []
                            ),
                            tags_to_clear=(
                                values if bestowal_field == "tags_to_clear" else []
                            ),
                        ),
                    )
                )

    return sites


def _replacement_entity_kinds(
    response: Any,
    cur: Any,
    *,
    proposal_bindings: Optional[Mapping[str, Mapping[str, Any]]],
) -> Tuple[
    Mapping[int, Tuple[Optional[str], Optional[str]]],
    List[str],
]:
    """Resolve actor/target kinds for replacement tag fields."""

    requirements: List[Tuple[int, str, str, str]] = []
    for index, adjudication in enumerate(
        getattr(response, "orrery_adjudications", None) or []
    ):
        delta = getattr(adjudication, "replacement_state_delta", None)
        if delta is None:
            continue
        proposal_id = str(getattr(adjudication, "proposal_id", "") or "")
        for field_name, _bestowal_field in _REPLACEMENT_ACTOR_TAG_FIELDS:
            if getattr(delta, field_name, None):
                requirements.append((index, proposal_id, "actor", field_name))
        for field_name, _bestowal_field in _REPLACEMENT_TARGET_TAG_FIELDS:
            if getattr(delta, field_name, None):
                requirements.append((index, proposal_id, "target", field_name))
        if getattr(delta, _REPLACEMENT_PAIR_TAG_FIELD, None):
            requirements.append(
                (index, proposal_id, "target", _REPLACEMENT_PAIR_TAG_FIELD)
            )
    if not requirements:
        return {}, []

    entity_ids: dict[Tuple[int, str], int] = {}
    issues: List[str] = []
    for index, proposal_id, endpoint, field_name in requirements:
        path = f"orrery_adjudications[{index}].replacement_state_delta.{field_name}"
        bindings = (
            proposal_bindings.get(proposal_id)
            if proposal_bindings is not None
            else None
        )
        if bindings is None:
            issues.append(
                f"{path}: Cannot validate registry tags because current proposal "
                f"bindings are unavailable for {proposal_id!r}"
            )
            continue
        entity_id = bindings.get(endpoint)
        if isinstance(entity_id, bool) or not isinstance(entity_id, int):
            issues.append(
                f"{path}: Cannot validate registry tags because proposal "
                f"{proposal_id!r} has no scalar {endpoint} entity binding"
            )
            continue
        entity_ids[(index, endpoint)] = entity_id

    kind_by_id: dict[int, str] = {}
    unique_ids = sorted(set(entity_ids.values()))
    if unique_ids:
        cur.execute(
            """
            SELECT id, kind::text
            FROM entities
            WHERE id = ANY(%s::bigint[])
            ORDER BY id
            """,
            (unique_ids,),
        )
        kind_by_id = {
            int(_row_value(row, "id", 0)): str(_row_value(row, "kind", 1))
            for row in cur.fetchall()
        }

    resolved: dict[int, Tuple[Optional[str], Optional[str]]] = {}
    for index, proposal_id, endpoint, field_name in requirements:
        entity_id = entity_ids.get((index, endpoint))
        if entity_id is None:
            continue
        entity_kind = kind_by_id.get(entity_id)
        path = f"orrery_adjudications[{index}].replacement_state_delta.{field_name}"
        if entity_kind not in {"character", "place", "faction"}:
            issues.append(
                f"{path}: Cannot validate registry tags because {endpoint} "
                f"entity {entity_id!r} for proposal {proposal_id!r} has no "
                "registered entity kind"
            )
            continue
        actor_kind, target_kind = resolved.get(index, (None, None))
        if endpoint == "actor":
            actor_kind = entity_kind
        else:
            target_kind = entity_kind
        resolved[index] = (actor_kind, target_kind)
    return resolved, issues


def _replacement_pair_tag_issues(
    response: Any,
    cur: Any,
    *,
    replacement_entity_kinds: Mapping[int, Tuple[Optional[str], Optional[str]]],
    vocabulary: Optional[StorytellerVocabulary],
    suggestion_limit: int,
) -> List[str]:
    """Validate inbound-clear names and target kinds against the pair-tag registry."""

    issues: List[str] = []
    for index, adjudication in enumerate(
        getattr(response, "orrery_adjudications", None) or []
    ):
        delta = getattr(adjudication, "replacement_state_delta", None)
        if delta is None:
            continue
        path = (
            f"orrery_adjudications[{index}].replacement_state_delta."
            f"{_REPLACEMENT_PAIR_TAG_FIELD}"
        )
        _actor_kind, target_kind = replacement_entity_kinds.get(index, (None, None))
        for tag_name in getattr(delta, _REPLACEMENT_PAIR_TAG_FIELD, None) or []:
            if vocabulary is not None and tag_name not in vocabulary.pair_tag_names:
                issue = f"{path}: Unknown or deprecated pair_tag {tag_name!r}"
                issues.append(
                    _with_near_misses(
                        issue,
                        value=tag_name,
                        candidates=vocabulary.pair_tag_names,
                        suggestion_limit=suggestion_limit,
                    )
                )
                continue

            if target_kind is None:
                if vocabulary is not None:
                    continue
                cur.execute(
                    """
                    SELECT id
                    FROM pair_tags
                    WHERE tag = %s AND NOT deprecated
                    """,
                    (tag_name,),
                )
                if cur.fetchone() is not None:
                    continue
                issues.append(f"{path}: Unknown or deprecated pair_tag {tag_name!r}")
                continue

            try:
                validate_pair_tag_endpoint(
                    cur,
                    tag=tag_name,
                    entity_kind=target_kind,
                    role="object",
                )
            except ValueError as exc:
                issues.append(f"{path}: {exc}")
    return issues


def _faction_update_sites(
    response: Any,
) -> List[Tuple[str, Optional[int], Optional[str]]]:
    """Return faction update identities from wire or hydrated responses."""

    sites: List[Tuple[str, Optional[int], Optional[str]]] = []
    updates = getattr(response, "updates", None)
    if updates is not None:
        for index, update in enumerate(getattr(updates, "factions", []) or []):
            sites.append(
                (
                    f"updates.factions[{index}]",
                    getattr(update, "id", None),
                    getattr(update, "name", None),
                )
            )

    state_updates = getattr(response, "state_updates", None)
    if state_updates is not None:
        for index, update in enumerate(getattr(state_updates, "factions", []) or []):
            sites.append(
                (
                    f"state_updates.factions[{index}]",
                    getattr(update, "faction_id", None),
                    getattr(update, "faction_name", None),
                )
            )
    return sites


def collect_faction_identity_issues(
    response: Any,
    cur: Any,
    *,
    suggestion_limit: int = 3,
    allow_same_turn_faction_declarations: bool = False,
) -> List[str]:
    """Validate faction update identities before a draft reaches incubation.

    When runtime maturation is enabled, exact same-response faction declarations
    are allowed because the commit transaction creates their canonical stubs
    before resolving state updates. Every other update must resolve to an
    existing faction by exact name, and a supplied ID/name pair must identify
    the same canonical row.
    """

    sites = _faction_update_sites(response)
    if not sites:
        return []

    cur.execute("SELECT id, name FROM factions ORDER BY name, id")
    rows = cur.fetchall()
    names_by_id = {
        int(_row_value(row, "id", 0)): str(_row_value(row, "name", 1)) for row in rows
    }
    ids_by_name: dict[str, int] = {}
    for catalog_id, catalog_name in names_by_id.items():
        ids_by_name[catalog_name] = catalog_id

    declared_names = (
        {
            str(getattr(declaration, "name", ""))
            for declaration in (getattr(response, "new_entities", None) or [])
            if getattr(declaration, "kind", None) == "faction"
        }
        if allow_same_turn_faction_declarations
        else set()
    )
    canonical_names = frozenset(ids_by_name)
    issues: List[str] = []
    for path, faction_id, faction_name in sites:
        if faction_id is not None:
            matched_name = names_by_id.get(faction_id)
            if matched_name is None:
                issues.append(f"{path}: Unknown canonical faction id {faction_id!r}")
                continue
            if faction_name != matched_name:
                issues.append(
                    f"{path}: Faction id {faction_id!r} is canonically named "
                    f"{matched_name!r}, not {faction_name!r}"
                )
            continue

        if not faction_name:
            issues.append(f"{path}: Faction update requires an exact id or name")
            continue
        if faction_name in ids_by_name:
            continue
        if faction_name in declared_names:
            continue
        resolution = "use an exact persisted name"
        if allow_same_turn_faction_declarations:
            resolution += " or declare a genuinely new faction in new_entities"
        issue = f"{path}: Unknown canonical faction name {faction_name!r}; {resolution}"
        issues.append(
            _with_near_misses(
                issue,
                value=faction_name,
                candidates=canonical_names,
                suggestion_limit=suggestion_limit,
            )
        )
    return issues


def _validate_bestowal_against_vocabulary(
    *,
    path: str,
    entity_kind: str,
    bestowal: OrreryTagBestowal,
    vocabulary: StorytellerVocabulary,
    suggestion_limit: int,
    handled_extend_expiry_sites: FrozenSet[Tuple[str, int]],
) -> List[str]:
    """Return field-qualified issues from the cached per-kind tag catalog."""

    allowed_tags = vocabulary.tag_names_by_kind.get(entity_kind, frozenset())
    issues: List[str] = []
    for field_name in ("applied_tags", "tags_to_clear"):
        for tag_index, tag_name in enumerate(getattr(bestowal, field_name)):
            if tag_name not in allowed_tags:
                issue = (
                    f"{field_name}: Unknown or entity-kind-incompatible tag "
                    f"{tag_name!r} for {entity_kind!r}"
                )
                issues.append(
                    _with_near_misses(
                        issue,
                        value=tag_name,
                        candidates=allowed_tags,
                        suggestion_limit=suggestion_limit,
                    )
                )
            elif (
                field_name == "applied_tags"
                and vocabulary.tag_reapplication_policies_by_kind.get(
                    entity_kind, {}
                ).get(tag_name)
                == "extend_expiry"
                and (path, tag_index) not in handled_extend_expiry_sites
            ):
                issues.append(
                    f"{field_name}: Tag {tag_name!r} uses "
                    "reapplication_policy='extend_expiry', which requires "
                    "duration_override; storyteller tags_add cannot express "
                    "duration_override. If the tag is already active, leave it "
                    "unchanged; otherwise omit it."
                )
    return issues


def _with_near_misses(
    issue: str,
    *,
    value: str,
    candidates: FrozenSet[str],
    suggestion_limit: int,
) -> str:
    """Append bounded same-catalog spelling suggestions to one issue."""

    if suggestion_limit <= 0:
        return issue
    matches = get_close_matches(
        value,
        sorted(candidates),
        n=suggestion_limit,
    )
    if not matches:
        return issue
    return f"{issue}; did you mean: {', '.join(matches)}"


def _row_value(row: Any, key: str, index: int) -> Any:
    """Read one field from tuple- or mapping-shaped database rows."""

    if hasattr(row, "get"):
        return row[key]
    return row[index]


@dataclass(frozen=True)
class _ExtendExpiryCandidate:
    """One wire-list entry eligible for active-state normalization."""

    ordinal: int
    array_name: str
    update_index: int
    entity_kind: str
    update: Any
    tags_add: List[str]
    tag_index: int
    wire_id: Optional[int]
    wire_name: str
    tag: str

    @property
    def path(self) -> str:
        """Return the public wire path for this update."""

        return f"updates.{self.array_name}[{self.update_index}]"


_SUBSTANTIVE_UPDATE_PREDICATES: Mapping[str, Mapping[str, Callable[[Any], bool]]] = {
    "character": {
        "activity": lambda update: bool(update.activity),
        "location": lambda update: update.location is not None,
        "emotional_state": lambda update: bool(update.emotional_state),
        "tags_clear": lambda update: bool(update.tags_clear),
    },
    "place": {
        "condition": lambda update: bool(update.condition),
        "notable_change": lambda update: bool(update.notable_change),
        "tags_clear": lambda update: bool(update.tags_clear),
    },
    "faction": {
        "action": lambda update: bool(update.action),
        "stance_toward": lambda update: bool(update.stance_toward and update.stance),
        "stance": lambda update: bool(update.stance_toward and update.stance),
        "tags_clear": lambda update: bool(update.tags_clear),
    },
}


def _has_substantive_update(entity_kind: str, update: Any) -> bool:
    """Mirror the wire predicate after normalization strips ``tags_add``."""

    return any(
        predicate(update)
        for predicate in _SUBSTANTIVE_UPDATE_PREDICATES[entity_kind].values()
    )


def normalize_extend_expiry_reasserts(
    response: Any,
    cur: Any,
    *,
    vocabulary: StorytellerVocabulary,
    anchor_world_time: Optional[datetime] = None,
    allow_same_turn_declarations: bool = False,
    boundary_issues: Optional[List[str]] = None,
    handled_extend_expiry_sites: Optional[MutableSet[Tuple[str, int]]] = None,
) -> int:
    """Normalize or classify wire-level ``extend_expiry`` applications.

    Active occurrences are removed as no-ops. Inactive time-cleared
    occurrences are admitted only when the registry carries a default duration;
    semantic/event occurrences are admitted with no expiry. Identity failures
    are surfaced through ``boundary_issues`` when the production validator
    supplies it. Name-only updates for declarations that the commit path will
    materialize are deferred because no persistent identity exists yet.
    """

    updates = getattr(response, "updates", None)
    if updates is None:
        return 0

    candidates: List[_ExtendExpiryCandidate] = []
    update_lists_by_kind: dict[str, List[Any]] = {}
    for array_name, entity_kind in (
        ("characters", "character"),
        ("places", "place"),
        ("factions", "faction"),
    ):
        update_list = getattr(updates, array_name, None)
        if update_list is None:
            continue
        update_lists_by_kind[entity_kind] = update_list
        policies = vocabulary.tag_reapplication_policies_by_kind.get(entity_kind, {})
        for update_index, update in enumerate(update_list):
            tags_add = getattr(update, "tags_add", None)
            if not tags_add:
                continue
            for tag_index, tag in enumerate(tags_add):
                if policies.get(tag) != "extend_expiry":
                    continue
                candidates.append(
                    _ExtendExpiryCandidate(
                        ordinal=len(candidates),
                        array_name=array_name,
                        update_index=update_index,
                        entity_kind=entity_kind,
                        update=update,
                        tags_add=tags_add,
                        tag_index=tag_index,
                        wire_id=getattr(update, "id", None),
                        wire_name=str(getattr(update, "name", "")),
                        tag=tag,
                    )
                )

    if not candidates:
        return 0

    declared_entity_names = (
        frozenset(
            (
                str(getattr(declaration, "kind", "")),
                str(getattr(declaration, "name", "")),
            )
            for declaration in (getattr(response, "new_entities", None) or [])
        )
        if allow_same_turn_declarations
        else frozenset()
    )

    activity_predicate = active_entity_tag_at_world_time_sql(
        entity_tag_alias="current_tag",
        world_time_sql="anchor.world_time",
    )
    cur.execute(
        f"""
        WITH candidates AS (
            SELECT *
            FROM UNNEST(
                %s::integer[],
                %s::text[],
                %s::bigint[],
                %s::text[],
                %s::text[]
            ) AS candidate(ordinal, entity_kind, wire_id, wire_name, tag)
        ),
        anchor AS (
            SELECT %s::timestamptz AS world_time
        ),
        canonical_entities AS (
            SELECT
                'character'::text AS entity_kind,
                id AS wire_id,
                entity_id,
                name::text AS canonical_name
            FROM characters
            UNION ALL
            SELECT
                'place'::text AS entity_kind,
                id AS wire_id,
                entity_id,
                name::text AS canonical_name
            FROM places
            UNION ALL
            SELECT
                'faction'::text AS entity_kind,
                id AS wire_id,
                entity_id,
                name::text AS canonical_name
            FROM factions
        )
        SELECT
            candidate.ordinal,
            id_match.entity_id AS id_entity_id,
            id_match.canonical_name AS id_canonical_name,
            (name_match.entity_id IS NOT NULL) AS has_name_match,
            name_match.entity_id AS name_entity_id,
            name_match.canonical_name AS name_canonical_name,
            entity.id AS verified_entity_id,
            current_tag.id AS current_tag_id,
            current_tag.expires_at_world_time,
            (
                current_tag.id IS NOT NULL
                AND {activity_predicate}
            ) AS is_active
        FROM candidates candidate
        CROSS JOIN anchor
        LEFT JOIN canonical_entities id_match
          ON candidate.wire_id IS NOT NULL
         AND id_match.entity_kind = candidate.entity_kind
         AND id_match.wire_id = candidate.wire_id
        LEFT JOIN canonical_entities name_match
          ON name_match.entity_kind = candidate.entity_kind
         AND name_match.canonical_name = candidate.wire_name
        LEFT JOIN entities entity
          ON entity.id = COALESCE(
              id_match.entity_id,
              name_match.entity_id
          )
         AND entity.kind::text = candidate.entity_kind
        LEFT JOIN tags registry_tag
          ON registry_tag.tag = candidate.tag
         AND NOT registry_tag.deprecated
         AND registry_tag.synonym_for IS NULL
        LEFT JOIN entity_tags current_tag
          ON current_tag.entity_id = entity.id
         AND current_tag.tag_id = registry_tag.id
         AND current_tag.cleared_at IS NULL
        ORDER BY candidate.ordinal
        """,
        (
            [candidate.ordinal for candidate in candidates],
            [candidate.entity_kind for candidate in candidates],
            [candidate.wire_id for candidate in candidates],
            [candidate.wire_name for candidate in candidates],
            [candidate.tag for candidate in candidates],
            anchor_world_time,
        ),
    )
    matches_by_ordinal: dict[int, Tuple[Any, ...]] = {}
    for row in cur.fetchall():
        ordinal = int(_row_value(row, "ordinal", 0))
        matches_by_ordinal[ordinal] = (
            _row_value(row, "id_entity_id", 1),
            _row_value(row, "id_canonical_name", 2),
            bool(_row_value(row, "has_name_match", 3)),
            _row_value(row, "name_entity_id", 4),
            _row_value(row, "name_canonical_name", 5),
            _row_value(row, "verified_entity_id", 6),
            _row_value(row, "current_tag_id", 7),
            _row_value(row, "expires_at_world_time", 8),
            bool(_row_value(row, "is_active", 9)),
        )

    removals_by_update: dict[
        int,
        Tuple[str, Any, List[str], set[int], str],
    ] = {}
    normalized = 0
    for candidate in candidates:
        match = matches_by_ordinal.get(candidate.ordinal)
        if match is None:
            raise RuntimeError(
                "Extend-expiry boundary query omitted candidate "
                f"ordinal={candidate.ordinal}"
            )
        (
            id_entity_id,
            id_canonical_name,
            has_name_match,
            name_entity_id,
            name_canonical_name,
            verified_entity_id,
            current_tag_id,
            expires_at_world_time,
            is_active,
        ) = match

        rejection_reason: Optional[str] = None
        canonical_name: Optional[str] = None
        if candidate.wire_id is not None:
            if id_entity_id is None or verified_entity_id is None:
                rejection_reason = "identity-miss"
            elif str(id_canonical_name) != candidate.wire_name:
                rejection_reason = "id-name-conflict"
            else:
                canonical_name = str(id_canonical_name)
        elif not has_name_match or verified_entity_id is None:
            rejection_reason = "identity-miss"
        else:
            canonical_name = str(name_canonical_name)

        site = (candidate.path, candidate.tag_index)
        is_declared_entity = (
            candidate.wire_id is None
            and (candidate.entity_kind, candidate.wire_name) in declared_entity_names
        )
        if rejection_reason == "identity-miss" and is_declared_entity:
            clearance_kind = vocabulary.tag_clearance_kinds_by_kind.get(
                candidate.entity_kind, {}
            ).get(candidate.tag)
            default_duration = vocabulary.tag_default_durations_by_kind.get(
                candidate.entity_kind, {}
            ).get(candidate.tag)
            if clearance_kind in {"semantic", "event"} and default_duration is not None:
                raise RuntimeError(
                    "Semantic/event extend-expiry tag unexpectedly carries "
                    f"default_duration: kind={candidate.entity_kind!r} "
                    f"tag={candidate.tag!r}"
                )
            if (clearance_kind == "time" and default_duration is not None) or (
                clearance_kind in {"semantic", "event"}
            ):
                logger.warning(
                    "extend-expiry boundary deferred: "
                    "reason=first-application-deferred-declared-entity "
                    "kind=%s array=%s index=%s supplied_id=%r entity_name=%s "
                    "offending_tags=%r",
                    candidate.entity_kind,
                    candidate.array_name,
                    candidate.update_index,
                    candidate.wire_id,
                    _quoted_log_text(candidate.wire_name),
                    [candidate.tag],
                )
                if handled_extend_expiry_sites is not None:
                    handled_extend_expiry_sites.add(site)
                continue
            logger.warning(
                "extend-expiry boundary rejected: reason=no-default-rejected "
                "kind=%s array=%s index=%s supplied_id=%r supplied_name=%s "
                "offending_tags=%r clearance_kind=%r",
                candidate.entity_kind,
                candidate.array_name,
                candidate.update_index,
                candidate.wire_id,
                _quoted_log_text(candidate.wire_name),
                [candidate.tag],
                clearance_kind,
            )
            continue

        if rejection_reason is not None:
            if rejection_reason == "identity-miss":
                logger.warning(
                    "extend-expiry boundary rejected: reason=identity-miss "
                    "kind=%s array=%s index=%s supplied_id=%r supplied_name=%s "
                    "offending_tags=%r",
                    candidate.entity_kind,
                    candidate.array_name,
                    candidate.update_index,
                    candidate.wire_id,
                    _quoted_log_text(candidate.wire_name),
                    [candidate.tag],
                )
            elif rejection_reason == "id-name-conflict":
                logger.warning(
                    "extend-expiry boundary rejected: reason=id-name-conflict "
                    "kind=%s array=%s index=%s supplied_id=%r supplied_name=%s "
                    "offending_tags=%r",
                    candidate.entity_kind,
                    candidate.array_name,
                    candidate.update_index,
                    candidate.wire_id,
                    _quoted_log_text(candidate.wire_name),
                    [candidate.tag],
                )
            else:
                raise RuntimeError(
                    "Extend-expiry identity resolution produced an unknown reason: "
                    f"{rejection_reason!r}"
                )
            if boundary_issues is not None:
                boundary_issues.append(
                    f"{candidate.path}: Extend-expiry update identity rejected "
                    f"(reason={rejection_reason}, supplied_id={candidate.wire_id!r}, "
                    f"supplied_name={_quoted_log_text(candidate.wire_name)}, "
                    f"offending_tags={[candidate.tag]!r})"
                )
            if handled_extend_expiry_sites is not None:
                handled_extend_expiry_sites.add(site)
            continue

        if canonical_name is None or verified_entity_id not in {
            id_entity_id,
            name_entity_id,
        }:
            raise RuntimeError(
                "Extend-expiry identity resolution produced an inconsistent match"
            )

        if current_tag_id is not None and not is_active:
            logger.warning(
                "extend-expiry boundary activity disagreement: "
                "reason=expiry-disagreement kind=%s entity_name=%s tag=%s "
                "expires_at_world_time=%s anchor_world_time=%s",
                candidate.entity_kind,
                _quoted_log_text(canonical_name),
                candidate.tag,
                expires_at_world_time,
                anchor_world_time,
            )

        if not is_active:
            clearance_kind = vocabulary.tag_clearance_kinds_by_kind.get(
                candidate.entity_kind, {}
            ).get(candidate.tag)
            default_duration = vocabulary.tag_default_durations_by_kind.get(
                candidate.entity_kind, {}
            ).get(candidate.tag)
            if clearance_kind == "time" and default_duration is not None:
                if anchor_world_time is None:
                    logger.warning(
                        "extend-expiry boundary rejected: "
                        "reason=anchor-time-missing kind=%s array=%s index=%s "
                        "supplied_id=%r supplied_name=%s offending_tags=%r",
                        candidate.entity_kind,
                        candidate.array_name,
                        candidate.update_index,
                        candidate.wire_id,
                        _quoted_log_text(candidate.wire_name),
                        [candidate.tag],
                    )
                    continue
                logger.warning(
                    "extend-expiry first-application defaulted: "
                    "reason=first-application-time-defaulted kind=%s "
                    "entity_name=%s tag=%s duration=%s array=%s index=%s",
                    candidate.entity_kind,
                    _quoted_log_text(canonical_name),
                    candidate.tag,
                    default_duration,
                    candidate.array_name,
                    candidate.update_index,
                )
                if handled_extend_expiry_sites is not None:
                    handled_extend_expiry_sites.add(site)
                continue
            if clearance_kind in {"semantic", "event"}:
                if default_duration is not None:
                    raise RuntimeError(
                        "Semantic/event extend-expiry tag unexpectedly carries "
                        f"default_duration: kind={candidate.entity_kind!r} "
                        f"tag={candidate.tag!r}"
                    )
                logger.warning(
                    "extend-expiry first-application landed: "
                    "reason=first-application-landed-no-expiry kind=%s "
                    "entity_name=%s tag=%s clearance_kind=%s array=%s index=%s",
                    candidate.entity_kind,
                    _quoted_log_text(canonical_name),
                    candidate.tag,
                    clearance_kind,
                    candidate.array_name,
                    candidate.update_index,
                )
                if handled_extend_expiry_sites is not None:
                    handled_extend_expiry_sites.add(site)
                continue

            logger.warning(
                "extend-expiry boundary rejected: reason=no-default-rejected "
                "kind=%s array=%s index=%s supplied_id=%r supplied_name=%s "
                "offending_tags=%r clearance_kind=%r",
                candidate.entity_kind,
                candidate.array_name,
                candidate.update_index,
                candidate.wire_id,
                _quoted_log_text(candidate.wire_name),
                [candidate.tag],
                clearance_kind,
            )
            continue

        update_key = id(candidate.update)
        if update_key not in removals_by_update:
            removals_by_update[update_key] = (
                candidate.entity_kind,
                candidate.update,
                candidate.tags_add,
                set(),
                canonical_name,
            )
        removals_by_update[update_key][3].add(candidate.tag_index)
        logger.warning(
            "extend-expiry re-assert normalized "
            "entity_kind=%s entity_name=%s tag=%s",
            candidate.entity_kind,
            _quoted_log_text(canonical_name),
            candidate.tag,
        )
        logger.warning(
            "extend-expiry boundary classified: reason=normalized-active "
            "kind=%s entity_name=%s tag=%s array=%s index=%s",
            candidate.entity_kind,
            _quoted_log_text(canonical_name),
            candidate.tag,
            candidate.array_name,
            candidate.update_index,
        )
        normalized += 1

    handled_candidates: List[_ExtendExpiryCandidate] = []
    if handled_extend_expiry_sites is not None:
        handled_candidates = [
            candidate
            for candidate in candidates
            if (candidate.path, candidate.tag_index) in handled_extend_expiry_sites
        ]

    removed_update_ids_by_kind: dict[str, set[int]] = {}
    for (
        entity_kind,
        update,
        tags_add,
        removal_indexes,
        canonical_name,
    ) in removals_by_update.values():
        tags_add[:] = [
            tag for index, tag in enumerate(tags_add) if index not in removal_indexes
        ]
        if not tags_add:
            update.tags_add = None
            if not _has_substantive_update(entity_kind, update):
                removed_update_ids_by_kind.setdefault(entity_kind, set()).add(
                    id(update)
                )
                logger.warning(
                    "extend-expiry no-op update removed "
                    "entity_kind=%s entity_name=%s",
                    entity_kind,
                    _quoted_log_text(canonical_name),
                )

    for entity_kind, removed_update_ids in removed_update_ids_by_kind.items():
        update_list = update_lists_by_kind[entity_kind]
        update_list[:] = [
            update for update in update_list if id(update) not in removed_update_ids
        ]

    if handled_extend_expiry_sites is not None:
        for candidate in handled_candidates:
            handled_extend_expiry_sites.discard((candidate.path, candidate.tag_index))
            update_list = update_lists_by_kind[candidate.entity_kind]
            current_update_index = next(
                (
                    index
                    for index, update in enumerate(update_list)
                    if update is candidate.update
                ),
                None,
            )
            if current_update_index is None:
                raise RuntimeError(
                    "Handled extend-expiry application was removed from its "
                    f"wire update: kind={candidate.entity_kind!r} "
                    f"tag={candidate.tag!r}"
                )
            removal_entry = removals_by_update.get(id(candidate.update))
            removal_indexes = removal_entry[3] if removal_entry is not None else set()
            current_tag_index = candidate.tag_index - sum(
                index < candidate.tag_index for index in removal_indexes
            )
            handled_extend_expiry_sites.add(
                (
                    f"updates.{candidate.array_name}[{current_update_index}]",
                    current_tag_index,
                )
            )

    return normalized


def _annotate_declaration_issues(
    issues: List[str],
    declarations: Any,
    *,
    vocabulary: StorytellerVocabulary,
    suggestion_limit: int,
) -> List[str]:
    """Add kind-correct suggestions to declaration hint failures."""

    annotated = list(issues)
    for declaration_index, declaration in enumerate(declarations):
        entity_kind = getattr(declaration, "kind", "")
        allowed_tags = vocabulary.tag_names_by_kind.get(entity_kind, frozenset())
        for tag_name in getattr(declaration, "tag_hints", None) or []:
            if tag_name in allowed_tags:
                continue
            prefix = f"new_entities[{declaration_index}].tag_hints:"
            annotated = _annotate_matching_issue(
                annotated,
                prefix=prefix,
                value=tag_name,
                candidates=allowed_tags,
                suggestion_limit=suggestion_limit,
            )
        for hint_index, hint in enumerate(
            getattr(declaration, "pair_tag_hints", None) or []
        ):
            tag_name = getattr(hint, "tag", "")
            if tag_name in vocabulary.pair_tag_names:
                continue
            prefix = (
                f"new_entities[{declaration_index}].pair_tag_hints"
                f"[{hint_index}].tag:"
            )
            annotated = _annotate_matching_issue(
                annotated,
                prefix=prefix,
                value=tag_name,
                candidates=vocabulary.pair_tag_names,
                suggestion_limit=suggestion_limit,
            )
    return annotated


def _annotate_matching_issue(
    issues: List[str],
    *,
    prefix: str,
    value: str,
    candidates: FrozenSet[str],
    suggestion_limit: int,
) -> List[str]:
    """Annotate the exact issue emitted for one invalid declaration value."""

    annotated = list(issues)
    for index, issue in enumerate(annotated):
        if (
            issue.startswith(prefix)
            and repr(value) in issue
            and "; did you mean:" not in issue
        ):
            annotated[index] = _with_near_misses(
                issue,
                value=value,
                candidates=candidates,
                suggestion_limit=suggestion_limit,
            )
            break
    return annotated


def collect_orrery_tag_issues(
    response: Any,
    cur: Any,
    *,
    vocabulary: Optional[StorytellerVocabulary] = None,
    suggestion_limit: int = 3,
    proposal_bindings: Optional[Mapping[str, Mapping[str, Any]]] = None,
    handled_extend_expiry_sites: FrozenSet[Tuple[str, int]] = frozenset(),
) -> List[str]:
    """Validate every bestowal and declaration against the live registry."""

    replacement_kinds, issues = _replacement_entity_kinds(
        response,
        cur,
        proposal_bindings=proposal_bindings,
    )
    for path, entity_kind, bestowal in _bestowal_sites(
        response,
        replacement_entity_kinds=replacement_kinds,
    ):
        if vocabulary is None:
            bestowal_issues = validate_tag_bestowal(
                cur,
                entity_kind=entity_kind,
                bestowal=bestowal,
            )
        else:
            bestowal_issues = _validate_bestowal_against_vocabulary(
                path=path,
                entity_kind=entity_kind,
                bestowal=bestowal,
                vocabulary=vocabulary,
                suggestion_limit=suggestion_limit,
                handled_extend_expiry_sites=handled_extend_expiry_sites,
            )
        for issue in bestowal_issues:
            issues.append(f"{path}: {issue}")
    issues.extend(
        _replacement_pair_tag_issues(
            response,
            cur,
            replacement_entity_kinds=replacement_kinds,
            vocabulary=vocabulary,
            suggestion_limit=suggestion_limit,
        )
    )
    declarations = getattr(response, "new_entities", None) or []
    declaration_issues = collect_new_entity_declaration_vocabulary_issues(
        cur,
        declarations,
        tag_names_by_kind=(
            vocabulary.tag_names_by_kind if vocabulary is not None else None
        ),
        pair_tag_names=(vocabulary.pair_tag_names if vocabulary is not None else None),
    )
    if vocabulary is not None:
        declaration_issues = _annotate_declaration_issues(
            declaration_issues,
            declarations,
            vocabulary=vocabulary,
            suggestion_limit=suggestion_limit,
        )
    issues.extend(declaration_issues)
    for index, adjudication in enumerate(
        getattr(response, "orrery_adjudications", None) or []
    ):
        event_type = getattr(adjudication, "replacement_event_type", None)
        if (
            event_type is not None
            and vocabulary is not None
            and event_type not in vocabulary.event_types
        ):
            issue = (
                "orrery_adjudications"
                f"[{index}].replacement_event_type: Unknown or deprecated "
                f"event type {event_type!r}"
            )
            issues.append(
                _with_near_misses(
                    issue,
                    value=event_type,
                    candidates=vocabulary.event_types,
                    suggestion_limit=suggestion_limit,
                )
            )
    return issues


def build_storyteller_tag_validator(
    dbname: Optional[str],
    *,
    suggestion_limit: int = 3,
    allow_same_turn_faction_declarations: bool = False,
    proposal_bindings_provider: Optional[
        Callable[[], Mapping[str, Mapping[str, Any]]]
    ] = None,
    anchor_chunk_id_provider: Optional[Callable[[], Optional[int]]] = None,
) -> Optional[Any]:
    """Return an async registry output validator bound to ``dbname``.

    Returns ``None`` when no slot database is in scope (nothing to validate
    against). The validator opens a short-lived pooled connection per generation
    attempt and raises ``ModelRetry`` listing invalid vocabulary and faction
    identities so the model repairs them instead of killing the commit later.
    """

    if not dbname:
        return None
    if suggestion_limit < 0:
        raise ValueError("suggestion_limit must be non-negative")

    async def _validate(ctx: Any, output: Any) -> Any:
        from pydantic_ai import ModelRetry

        from nexus.api.db_pool import get_connection

        proposal_bindings = (
            proposal_bindings_provider()
            if proposal_bindings_provider is not None
            else None
        )
        if proposal_bindings is not None and not isinstance(proposal_bindings, Mapping):
            raise TypeError("proposal_bindings_provider must return a mapping")
        vocabulary = read_storyteller_vocabulary(dbname)
        with get_connection(dbname) as conn:
            with conn.cursor() as cur:
                anchor_world_time: Optional[datetime] = None
                if anchor_chunk_id_provider is not None:
                    anchor_chunk_id = anchor_chunk_id_provider()
                    if anchor_chunk_id is not None:
                        if isinstance(anchor_chunk_id, bool) or not isinstance(
                            anchor_chunk_id, int
                        ):
                            raise TypeError(
                                "anchor_chunk_id_provider must return a positive "
                                "integer or None"
                            )
                        if anchor_chunk_id <= 0:
                            raise ValueError(
                                "anchor_chunk_id_provider must return a positive "
                                "integer or None"
                            )
                        cur.execute(
                            """
                            SELECT world_time
                            FROM chunk_metadata
                            WHERE chunk_id = %s
                            """,
                            (anchor_chunk_id,),
                        )
                        anchor_row = cur.fetchone()
                        if anchor_row is None:
                            raise ValueError(
                                "Storyteller tag validation anchor chunk does not "
                                f"exist: chunk_id={anchor_chunk_id}"
                            )
                        anchor_world_time = _row_value(anchor_row, "world_time", 0)
                        if anchor_world_time is not None and not isinstance(
                            anchor_world_time, datetime
                        ):
                            raise TypeError(
                                "Storyteller tag validation anchor world_time has "
                                f"an unexpected type: chunk_id={anchor_chunk_id}"
                            )
                boundary_issues: List[str] = []
                handled_extend_expiry_sites: set[Tuple[str, int]] = set()
                normalize_extend_expiry_reasserts(
                    output,
                    cur,
                    vocabulary=vocabulary,
                    anchor_world_time=anchor_world_time,
                    allow_same_turn_declarations=(allow_same_turn_faction_declarations),
                    boundary_issues=boundary_issues,
                    handled_extend_expiry_sites=handled_extend_expiry_sites,
                )
                issues = boundary_issues + collect_orrery_tag_issues(
                    output,
                    cur,
                    vocabulary=vocabulary,
                    suggestion_limit=suggestion_limit,
                    proposal_bindings=proposal_bindings,
                    handled_extend_expiry_sites=frozenset(handled_extend_expiry_sites),
                )
                issues.extend(
                    collect_faction_identity_issues(
                        output,
                        cur,
                        suggestion_limit=suggestion_limit,
                        allow_same_turn_faction_declarations=(
                            allow_same_turn_faction_declarations
                        ),
                    )
                )
        if issues:
            formatted = "\n".join(f"- {issue}" for issue in issues)
            declaration_guidance = (
                "or declare a genuinely new faction in new_entities; "
                if allow_same_turn_faction_declarations
                else (
                    "same-turn declarations cannot back faction updates while "
                    "runtime maturation is disabled; "
                )
            )
            logger.info(
                "Storyteller output failed registry validation "
                "(%s issues); requesting model retry:\n%s",
                len(issues),
                formatted,
            )
            raise ModelRetry(
                "Your Orrery tags, new-entity declaration hints, replacement "
                "event types, or faction update identities failed closed-registry "
                "validation. For faction updates, use an exact persisted name "
                "shown in the ENTITY DOSSIER (and its matching canonical id when "
                f"supplying one), {declaration_guidance}drop an update with no "
                "canonical equivalent. "
                "For tags_add, tags_clear, and tag_hints, use bare registered tag "
                "names only (e.g. 'comfortable'), never 'category:name' "
                "composites. For pair_tag_hints, use the exact registered pair-tag "
                "name; pair tags may contain colons (e.g. 'contact:social'). For "
                "replacement_event_type, use an exact registered event type. Drop "
                "any value with no registered equivalent. Replacement-state "
                "entity tag lists follow the actor or target entity kind; "
                "entity_pair_tags_target_clear_inbound uses exact registered "
                "pair-tag names. A tags_add issue that requires duration_override "
                "is not expressible on the storyteller wire; omit that tag. Fix "
                "every listed "
                f"path and resubmit the complete response:\n{formatted}"
            )
        return output

    return _validate
