"""Pre-hydration reconciliation for prose-named character mentions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import os
from typing import Any, List, Optional, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.logon.skald_wire import (
    CharacterRef,
    PresenceBaseline,
    PresenceDelta,
    PresenceRef,
    SkaldTurnWire,
    _deduplicate_presence,
    _presence_key,
)
from nexus.api.presence_audit import _character_only_detector


logger = logging.getLogger("nexus.api.presence_reconciliation")


@dataclass(frozen=True)
class CharacterRosterRows:
    """Prefetched character and alias rows for one turn."""

    characters: List[Any]
    aliases: List[Any]


def read_character_roster(dbname: str) -> CharacterRosterRows:
    """Read the known-character roster and aliases for one turn."""

    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, summary FROM characters WHERE name IS NOT NULL"
            )
            character_rows = cur.fetchall()
            cur.execute("SELECT character_id, alias FROM character_aliases")
            alias_rows = cur.fetchall()
    finally:
        conn.close()

    return CharacterRosterRows(
        characters=list(character_rows),
        aliases=list(alias_rows),
    )


async def read_character_roster_async(dbname: str) -> CharacterRosterRows:
    """Read the known-character roster without blocking the async turn loop."""

    return await asyncio.to_thread(read_character_roster, dbname)


def _matches_character(character: Any, reference: PresenceRef) -> bool:
    """Match canonical identity by id when possible, otherwise by name."""

    character_id = character["id"]
    if character_id is not None and reference.id is not None:
        return character_id == reference.id
    return str(character["name"]).casefold() == reference.name.casefold()


def _end_of_turn_roster(
    presence: Optional[PresenceDelta],
    baseline: Optional[PresenceBaseline],
) -> List[CharacterRef]:
    """Apply the same end-roster algebra used by Skald hydration."""

    if presence is not None and presence.scene_reset is not None:
        return _deduplicate_presence(presence.scene_reset.present)
    if baseline is None:
        return []

    enter = presence.enter if presence is not None else []
    exit_references = presence.exit if presence is not None else []
    roster = _deduplicate_presence([*baseline.present, *enter])
    exit_keys = {_presence_key(reference) for reference in exit_references}
    return [
        reference for reference in roster if _presence_key(reference) not in exit_keys
    ]


def _is_accounted(
    character: Any,
    references: Sequence[PresenceRef],
) -> bool:
    """Return whether any character reference accounts for the detection."""

    return any(
        reference.kind == "character" and _matches_character(character, reference)
        for reference in references
    )


def reconcile_prose_mentions(
    wire: SkaldTurnWire,
    *,
    presence_baseline: Optional[PresenceBaseline],
    roster_rows: CharacterRosterRows,
) -> SkaldTurnWire:
    """Append missing known-character mentions detected in final wire prose.

    Accounting mirrors the post-commit audit contract: the end-of-turn roster,
    explicit current mentions, and parent-present characters each exempt a
    detected identity. Parent-mentioned characters are absent from the
    baseline by design and therefore require their own child mention.
    """

    detector = _character_only_detector(roster_rows.characters, roster_rows.aliases)
    detected = detector.detect_entities(wire.narrative).characters
    presence = wire.presence
    end_roster = _end_of_turn_roster(presence, presence_baseline)
    mentions = presence.mentions if presence is not None else []
    parent_present = presence_baseline.present if presence_baseline is not None else []

    for character in detected:
        if any(
            _is_accounted(character, references)
            for references in (end_roster, mentions, parent_present)
        ):
            continue
        if wire.presence is None:
            wire.presence = PresenceDelta()
            mentions = wire.presence.mentions
        canonical = PresenceRef(
            kind="character",
            name=character["name"],
            id=character["id"],
        )
        wire.presence.mentions.append(canonical)
        logger.warning("presence prose mention normalized: %s", canonical.name)

    return wire
