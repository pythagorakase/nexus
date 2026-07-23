"""Generation-time registry validation for storyteller Orrery vocabulary.

Skald freely invents tag names (often ``category:name`` composites) when
updating state or emitting ``new_entities`` declaration hints. The
closed-vocabulary tag writers hard-error on unknown names -- but they run
inside the chunk COMMIT transaction, where the only outcome is a dead player
turn (M9 gate finding).

This module walks a parsed storyteller response and validates every
``orrery_tags`` bestowal and declaration hint against the live registry, so
LOGON's structured output validator can hand the issues back to the model as a
retry while the model still owns the turn.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def read_storyteller_vocabulary(dbname: str) -> StorytellerVocabulary:
    """Load each live vocabulary catalog once for one validation attempt."""

    tags_by_kind: dict[str, set[str]] = {
        "character": set(),
        "place": set(),
        "faction": set(),
    }
    for entry in read_tag_library(dbname):
        if entry.entity_kind in tags_by_kind:
            tags_by_kind[entry.entity_kind].add(entry.tag)
    return StorytellerVocabulary(
        tag_names_by_kind={
            kind: frozenset(tag_names) for kind, tag_names in tags_by_kind.items()
        },
        pair_tag_names=frozenset(read_pair_tag_library(dbname)),
        event_types=frozenset(read_event_types(dbname)),
    )


def _bestowal_sites(response: Any) -> List[Tuple[str, str, OrreryTagBestowal]]:
    """Yield (path, entity_kind, bestowal) triples from a parsed response."""

    sites: List[Tuple[str, str, OrreryTagBestowal]] = []

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


def _validate_bestowal_against_vocabulary(
    *,
    entity_kind: str,
    bestowal: OrreryTagBestowal,
    vocabulary: StorytellerVocabulary,
) -> List[str]:
    """Return field-qualified issues from the cached per-kind tag catalog."""

    allowed_tags = vocabulary.tag_names_by_kind.get(entity_kind, frozenset())
    issues: List[str] = []
    for field_name in ("applied_tags", "tags_to_clear"):
        for tag_name in getattr(bestowal, field_name):
            if tag_name not in allowed_tags:
                issues.append(
                    f"{field_name}: Unknown or entity-kind-incompatible tag "
                    f"{tag_name!r} for {entity_kind!r}"
                )
    return issues


def collect_orrery_tag_issues(
    response: Any,
    cur: Any,
    *,
    vocabulary: Optional[StorytellerVocabulary] = None,
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
            )
        for issue in bestowal_issues:
            issues.append(f"{path}: {issue}")
    issues.extend(
        collect_new_entity_declaration_vocabulary_issues(
            cur,
            getattr(response, "new_entities", None) or [],
            tag_names_by_kind=(
                vocabulary.tag_names_by_kind if vocabulary is not None else None
            ),
            pair_tag_names=(
                vocabulary.pair_tag_names if vocabulary is not None else None
            ),
        )
    )
    for index, adjudication in enumerate(
        getattr(response, "orrery_adjudications", None) or []
    ):
        event_type = getattr(adjudication, "replacement_event_type", None)
        if (
            event_type is not None
            and vocabulary is not None
            and event_type not in vocabulary.event_types
        ):
            issues.append(
                "orrery_adjudications"
                f"[{index}].replacement_event_type: Unknown or deprecated "
                f"event type {event_type!r}"
            )
    return issues


def build_storyteller_tag_validator(dbname: Optional[str]) -> Optional[Any]:
    """Return an async pydantic_ai output validator bound to ``dbname``.

    Returns ``None`` when no slot database is in scope (nothing to validate
    against). The validator opens a short-lived pooled connection per
    generation attempt and raises ``ModelRetry`` listing every invalid tag so
    the model repairs the bestowal instead of killing the commit later.
    """

    if not dbname:
        return None

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
                )
        if issues:
            formatted = "\n".join(f"- {issue}" for issue in issues)
            logger.info(
                "Storyteller Orrery vocabulary failed registry validation "
                "(%s issues); requesting model retry",
                len(issues),
            )
            raise ModelRetry(
                "Your Orrery tags, new-entity declaration hints, or replacement "
                "event types failed closed-registry validation. For applied_tags, "
                "tags_to_clear, and tag_hints, use bare registered tag names only "
                "(e.g. 'comfortable'), never 'category:name' composites. For "
                "pair_tag_hints, use the exact registered pair-tag name; pair tags "
                "may contain colons (e.g. 'contact:social'). For "
                "replacement_event_type, use an exact registered event type. Drop "
                "any value with no registered equivalent. Fix every listed "
                f"path and resubmit the complete response:\n{formatted}"
            )
        return output

    return _validate
