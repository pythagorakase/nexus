"""Closed deterministic cues for commit-time physical-presence promotion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
import re
from typing import Any

from nexus.presence.roster import PresenceRoster, RosterEntry, character_identity_index

logger = logging.getLogger(__name__)

# Grammar, not tunable confidence thresholds. Unlisted constructions remain mentions.
DIALOGUE_VERBS = (
    "says",
    "said",
    "asks",
    "asked",
    "replies",
    "replied",
    "whispers",
    "whispered",
    "shouts",
    "shouted",
)
STAGE_ACTION_VERBS = (
    "stands",
    "stood",
    "sits",
    "sat",
    "waits",
    "waited",
    "nods",
    "nodded",
    "steps",
    "stepped",
    "enters",
    "entered",
    "walks",
    "walked",
    "lifts",
    "lifted",
    "turns",
    "turned",
)
DECLARATION_PLACEMENTS = (
    "present in the scene",
    "standing in the room",
    "seated in the room",
    "here in the room",
)
REMOTE_CUES = (
    "over the radio",
    "over the phone",
    "on the phone",
    "on the screen",
    "in the recording",
    "in the memory",
    "in a dream",
    "walks away",
    "walked away",
    "steps out",
    "stepped out",
)


def has_scene_cue(prose: str, name: str) -> bool:
    """Recognize named action clauses or explicit dialogue attribution."""
    escaped = re.escape(name)
    verbs = "|".join((*DIALOGUE_VERBS, *STAGE_ACTION_VERBS))
    speech = "|".join(DIALOGUE_VERBS)
    patterns = (
        rf"(?:^|[.!?]\s+|\n|\bwhile\s+|,\s*(?:and|but)\s+)\s*{escaped}\s+(?:{verbs})\b",
        rf'["”]\s*,?\s*{escaped}\s+(?:{speech})\b',
        rf'["”]\s*,?\s*(?:{speech})\s+{escaped}\b',
        rf'(?:^|\n)\s*{escaped}:\s*["“]',
    )
    for sentence in re.split(r"(?<=[.!?])\s+|\n", prose):
        if any(cue in sentence.casefold() for cue in REMOTE_CUES):
            continue
        if any(re.search(pattern, sentence, re.IGNORECASE) for pattern in patterns):
            return True
    return False


def promote_in_scene_characters(
    roster: PresenceRoster,
    *,
    prose: str,
    declarations: Sequence[Mapping[str, Any]],
    character_rows: Sequence[Mapping[str, Any]],
    alias_rows: Sequence[Mapping[str, Any]],
    parent: PresenceRoster | None,
) -> PresenceRoster:
    """Promote deterministic in-scene identities without undoing authored exits.

    A parent-present character absent from the end roster has an authored exit
    or reset; speech earlier in that turn must not put them back in the room.
    Only accepted public prose is considered, never unselected choices.
    """
    result = roster.model_copy(deep=True)
    index = character_identity_index(character_rows, alias_rows)
    declared = {
        str(declaration["name"])
        .casefold(): str(declaration.get("summary", ""))
        .casefold()
        for declaration in declarations
        if declaration.get("kind") == "character"
    }
    for (kind, name), keys in index.by_name.items():
        if kind != "character":
            continue
        declaration_cue = any(
            re.search(
                rf"(?:^|[.!?]\s+)(?:{re.escape(name)} is |is )?{re.escape(placement)}(?:[.!?]|$)",
                declared.get(name, ""),
            )
            for placement in DECLARATION_PLACEMENTS
        )
        if not has_scene_cue(prose, name) and not declaration_cue:
            continue
        entry = index.resolve(RosterEntry(kind="character", name=name))
        if entry.key in result.present or (
            parent is not None and entry.key in parent.present
        ):
            continue
        result.referenced.pop(entry.key, None)
        result.present[entry.key] = entry
        logger.warning(
            "presence promoted from deterministic scene cue: character_id=%s name=%r",
            entry.id,
            entry.name,
        )
    return result
