"""Generation-time registry validation for storyteller Orrery tag bestowals.

Skald freely invents tag names (often ``category:name`` composites) when
introducing entities or updating state. The closed-vocabulary tag writers
hard-error on unknown names -- but they run inside the chunk COMMIT
transaction, where the only outcome is a dead player turn (M9 gate finding).

This module walks a parsed storyteller response and validates every
``orrery_tags`` bestowal against the live registry, so LOGON's structured
output validator can hand the issues back to the model as a retry while the
model still owns the turn.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.agents.orrery.tag_writer import validate_tag_bestowal

logger = logging.getLogger("nexus.logon.orrery_tag_validation")


def _bestowal_sites(response: Any) -> List[Tuple[str, str, OrreryTagBestowal]]:
    """Yield (path, entity_kind, bestowal) triples from a parsed response."""

    sites: List[Tuple[str, str, OrreryTagBestowal]] = []

    referenced = getattr(response, "referenced_entities", None)
    if referenced is not None:
        for index, ref in enumerate(getattr(referenced, "characters", []) or []):
            new_entity = getattr(ref, "new_character", None)
            bestowal = getattr(new_entity, "orrery_tags", None)
            if bestowal is not None:
                sites.append(
                    (
                        f"referenced_entities.characters[{index}].new_character",
                        "character",
                        bestowal,
                    )
                )
        for index, ref in enumerate(getattr(referenced, "places", []) or []):
            new_entity = getattr(ref, "new_place", None)
            bestowal = getattr(new_entity, "orrery_tags", None)
            if bestowal is not None:
                sites.append(
                    (
                        f"referenced_entities.places[{index}].new_place",
                        "place",
                        bestowal,
                    )
                )
        for index, ref in enumerate(getattr(referenced, "factions", []) or []):
            new_entity = getattr(ref, "new_faction", None)
            bestowal = getattr(new_entity, "orrery_tags", None)
            if bestowal is not None:
                sites.append(
                    (
                        f"referenced_entities.factions[{index}].new_faction",
                        "faction",
                        bestowal,
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


def collect_orrery_tag_issues(response: Any, cur: Any) -> List[str]:
    """Validate every bestowal in the response against the live registry."""

    issues: List[str] = []
    for path, entity_kind, bestowal in _bestowal_sites(response):
        for issue in validate_tag_bestowal(
            cur, entity_kind=entity_kind, bestowal=bestowal
        ):
            issues.append(f"{path}: {issue}")
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

        with get_connection(dbname) as conn:
            with conn.cursor() as cur:
                issues = collect_orrery_tag_issues(output, cur)
        if issues:
            formatted = "\n".join(f"- {issue}" for issue in issues)
            logger.info(
                "Storyteller orrery_tags failed registry validation (%s issues); "
                "requesting model retry",
                len(issues),
            )
            raise ModelRetry(
                "Your orrery_tags failed closed-registry validation. Use bare "
                "registered tag names only (e.g. 'comfortable'), never "
                "'category:name' composites; drop any tag with no registered "
                f"equivalent. Fix these and resubmit:\n{formatted}"
            )
        return output

    return _validate
