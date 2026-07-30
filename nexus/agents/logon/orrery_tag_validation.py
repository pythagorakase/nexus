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
from difflib import get_close_matches
import logging
from typing import Any, FrozenSet, List, Mapping, Optional, Tuple

from nexus.agents.orrery.declaration_validation import (
    collect_new_entity_declaration_vocabulary_issues,
)
from nexus.agents.orrery.tag_library import (
    read_event_types,
    read_pair_tag_library,
    read_tag_library,
)
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.agents.orrery.tag_writer import validate_tag_bestowal

logger = logging.getLogger("nexus.logon.orrery_tag_validation")


@dataclass(frozen=True)
class StorytellerVocabulary:
    """One validation pass's immutable snapshot of live storyteller catalogs."""

    tag_names_by_kind: Mapping[str, FrozenSet[str]]
    pair_tag_names: FrozenSet[str]
    event_types: FrozenSet[str]
    tag_reapplication_policies_by_kind: Mapping[str, Mapping[str, str]] = field(
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
    for entry in read_tag_library(dbname):
        if entry.entity_kind in tags_by_kind:
            tags_by_kind[entry.entity_kind].add(entry.tag)
            if entry.reapplication_policy is not None:
                policies_by_kind[entry.entity_kind][
                    entry.tag
                ] = entry.reapplication_policy
    return StorytellerVocabulary(
        tag_names_by_kind={
            kind: frozenset(tag_names) for kind, tag_names in tags_by_kind.items()
        },
        pair_tag_names=frozenset(read_pair_tag_library(dbname)),
        event_types=frozenset(read_event_types(dbname)),
        tag_reapplication_policies_by_kind={
            kind: dict(policies) for kind, policies in policies_by_kind.items()
        },
    )


def _bestowal_sites(response: Any) -> List[Tuple[str, str, OrreryTagBestowal]]:
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

    return sites


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
    ids_by_name: dict[str, List[int]] = {}
    for catalog_id, catalog_name in names_by_id.items():
        ids_by_name.setdefault(catalog_name, []).append(catalog_id)

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
        matching_ids = ids_by_name.get(faction_name, [])
        if len(matching_ids) == 1:
            continue
        if len(matching_ids) > 1:
            issues.append(
                f"{path}: Canonical faction name {faction_name!r} is ambiguous; "
                "supply its exact id"
            )
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
    entity_kind: str,
    bestowal: OrreryTagBestowal,
    vocabulary: StorytellerVocabulary,
    suggestion_limit: int,
) -> List[str]:
    """Return field-qualified issues from the cached per-kind tag catalog."""

    allowed_tags = vocabulary.tag_names_by_kind.get(entity_kind, frozenset())
    issues: List[str] = []
    for field_name in ("applied_tags", "tags_to_clear"):
        for tag_name in getattr(bestowal, field_name):
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
) -> List[str]:
    """Validate every bestowal and declaration against the live registry."""

    issues: List[str] = []
    for path, entity_kind, bestowal in _bestowal_sites(response):
        if vocabulary is None:
            bestowal_issues = validate_tag_bestowal(
                cur,
                entity_kind=entity_kind,
                bestowal=bestowal,
            )
        else:
            bestowal_issues = _validate_bestowal_against_vocabulary(
                entity_kind=entity_kind,
                bestowal=bestowal,
                vocabulary=vocabulary,
                suggestion_limit=suggestion_limit,
            )
        for issue in bestowal_issues:
            issues.append(f"{path}: {issue}")
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

        vocabulary = read_storyteller_vocabulary(dbname)
        with get_connection(dbname) as conn:
            with conn.cursor() as cur:
                issues = collect_orrery_tag_issues(
                    output,
                    cur,
                    vocabulary=vocabulary,
                    suggestion_limit=suggestion_limit,
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
                "(%s issues); requesting model retry",
                len(issues),
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
                "any value with no registered equivalent. A tags_add issue that "
                "requires duration_override is not expressible on the storyteller "
                "wire; omit that tag. Fix every listed "
                f"path and resubmit the complete response:\n{formatted}"
            )
        return output

    return _validate
