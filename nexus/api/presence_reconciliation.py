"""Pre-hydration reconciliation for prose-named character mentions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import os
from typing import Any, Collection, List, Mapping, Optional, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.logon.apex_schema import NewEntityDeclaration
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
from nexus.memory.entity_detector import HighSpecificityEntityDetector
from nexus.util.log_safety import quote_log_value


logger = logging.getLogger("nexus.api.presence_reconciliation")


@dataclass(frozen=True)
class CharacterRosterRows:
    """Prefetched character and alias rows for one turn."""

    characters: List[Any]
    aliases: List[Any]


def read_character_roster_from_connection(conn: Any) -> CharacterRosterRows:
    """Read the character roster through an existing psycopg2 transaction."""

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, name, summary FROM characters WHERE name IS NOT NULL")
        character_rows = cur.fetchall()
        cur.execute("SELECT character_id, alias FROM character_aliases")
        alias_rows = cur.fetchall()

    return CharacterRosterRows(
        characters=list(character_rows),
        aliases=list(alias_rows),
    )


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
        return read_character_roster_from_connection(conn)
    finally:
        conn.close()


async def read_character_roster_async(dbname: str) -> CharacterRosterRows:
    """Read the known-character roster without blocking the async turn loop."""

    return await asyncio.to_thread(read_character_roster, dbname)


async def read_character_roster_from_async_connection(
    conn: Any,
) -> CharacterRosterRows:
    """Read the character roster through an existing asyncpg transaction."""

    character_rows = await conn.fetch(
        "SELECT id, name, summary FROM characters WHERE name IS NOT NULL"
    )
    alias_rows = await conn.fetch("SELECT character_id, alias FROM character_aliases")
    return CharacterRosterRows(
        characters=list(character_rows),
        aliases=list(alias_rows),
    )


def _matches_character(character: Any, reference: PresenceRef) -> bool:
    """Match canonical identity by id when possible, otherwise by name."""

    character_id = character["id"]
    if character_id is not None and reference.id is not None:
        return character_id == reference.id
    return str(character["name"]) == reference.name


def _ambiguous_character_keys(
    roster_rows: CharacterRosterRows,
) -> dict[str, set[int]]:
    """Return casefolded lookup keys that identify multiple characters."""

    candidate_ids: dict[str, set[int]] = {}
    known_character_ids: set[int] = set()
    for character in roster_rows.characters:
        character_id = int(character["id"])
        known_character_ids.add(character_id)
        key = str(character["name"]).casefold()
        candidate_ids.setdefault(key, set()).add(character_id)
    for alias in roster_rows.aliases:
        character_id = int(alias["character_id"])
        if character_id not in known_character_ids:
            continue
        key = str(alias["alias"]).casefold()
        candidate_ids.setdefault(key, set()).add(character_id)
    return {key: ids for key, ids in candidate_ids.items() if len(ids) > 1}


def _reconciliation_detector(
    roster_rows: CharacterRosterRows,
) -> HighSpecificityEntityDetector:
    """Build the shared detector with ambiguous character keys excluded."""

    ambiguous = _ambiguous_character_keys(roster_rows)
    for key in sorted(ambiguous):
        logger.warning(
            "presence prose mention ambiguous: %s candidate_ids=%s",
            key,
            sorted(ambiguous[key]),
        )

    detector = _character_only_detector(roster_rows.characters, roster_rows.aliases)
    for lookup_key in list(detector.character_lookup):
        if lookup_key.casefold() in ambiguous:
            del detector.character_lookup[lookup_key]
    return detector


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


def _unaccounted_public_prose_mentions(
    prose_parts: Sequence[str],
    *,
    accounted_references: Sequence[PresenceRef],
    roster_rows: CharacterRosterRows,
    candidate_character_ids: Optional[Collection[int]] = None,
) -> List[PresenceRef]:
    """Return unaccounted canonical mentions from the shared detector core."""

    detector = _reconciliation_detector(roster_rows)
    detected = detector.detect_entities("\n".join(prose_parts)).characters
    accounted = list(accounted_references)
    reconciled: List[PresenceRef] = []

    for character in detected:
        character_id = int(character["id"])
        if (
            candidate_character_ids is not None
            and character_id not in candidate_character_ids
        ):
            continue
        if _is_accounted(character, accounted):
            continue
        canonical = PresenceRef(
            kind="character",
            name=character["name"],
            id=character_id,
        )
        reconciled.append(canonical)
        accounted.append(canonical)

    return reconciled


def reconcile_public_prose_mentions(
    prose_parts: Sequence[str],
    *,
    accounted_references: Sequence[PresenceRef],
    roster_rows: CharacterRosterRows,
) -> List[PresenceRef]:
    """Return missing canonical mentions detected in public narrative prose.

    This is the shared pre-hydration boundary for ordinary Skald turns and
    wizard-opening bootstrap turns. Callers supply the character references
    already accounted for by their route-specific presence representation.
    """

    reconciled = _unaccounted_public_prose_mentions(
        prose_parts,
        accounted_references=accounted_references,
        roster_rows=roster_rows,
    )
    for canonical in reconciled:
        logger.warning("presence prose mention normalized: %s", canonical.name)
    return reconciled


def _declared_character_names(
    declarations: Sequence[Mapping[str, Any]],
) -> List[str]:
    """Return unique character names from this committed wire's declarations."""

    parsed = [
        NewEntityDeclaration.model_validate(declaration) for declaration in declarations
    ]
    return list(
        dict.fromkeys(
            declaration.name
            for declaration in parsed
            if declaration.kind == "character"
        )
    )


def _reconcile_declared_character_mentions(
    prose_parts: Sequence[str],
    *,
    declared_names: Sequence[str],
    accounted_character_ids: Collection[int],
    roster_rows: CharacterRosterRows,
) -> List[PresenceRef]:
    """Detect only transaction-visible characters declared by this wire."""

    rows_by_name: dict[str, List[Any]] = {name: [] for name in declared_names}
    for character in roster_rows.characters:
        name = str(character["name"])
        if name in rows_by_name:
            rows_by_name[name].append(character)

    declared_rows: List[Any] = []
    for name in declared_names:
        matches = rows_by_name[name]
        if len(matches) != 1:
            raise ValueError(
                f"Declared character name {name!r} resolved to {len(matches)} "
                "roster rows after stub creation"
            )
        declared_rows.append(matches[0])

    declared_ids = {int(character["id"]) for character in declared_rows}
    accounted_ids = set(accounted_character_ids)
    accounted_references = [
        PresenceRef(
            kind="character",
            name=str(character["name"]),
            id=int(character["id"]),
        )
        for character in declared_rows
        if int(character["id"]) in accounted_ids
    ]
    reconciled = _unaccounted_public_prose_mentions(
        prose_parts,
        accounted_references=accounted_references,
        roster_rows=roster_rows,
        candidate_character_ids=declared_ids,
    )
    for canonical in reconciled:
        logger.warning(
            "presence declared mention normalized: %s",
            quote_log_value(canonical.name),
        )
    return reconciled


def reconcile_declared_character_mentions(
    conn: Any,
    prose_parts: Sequence[str],
    *,
    declarations: Sequence[Mapping[str, Any]],
    accounted_character_ids: Collection[int],
) -> List[PresenceRef]:
    """Reconcile same-turn declarations inside a psycopg2 commit transaction."""

    declared_names = _declared_character_names(declarations)
    if not declared_names:
        return []
    return _reconcile_declared_character_mentions(
        prose_parts,
        declared_names=declared_names,
        accounted_character_ids=accounted_character_ids,
        roster_rows=read_character_roster_from_connection(conn),
    )


async def reconcile_declared_character_mentions_async(
    conn: Any,
    prose_parts: Sequence[str],
    *,
    declarations: Sequence[Mapping[str, Any]],
    accounted_character_ids: Collection[int],
) -> List[PresenceRef]:
    """Reconcile same-turn declarations inside an asyncpg commit transaction."""

    declared_names = _declared_character_names(declarations)
    if not declared_names:
        return []
    return _reconcile_declared_character_mentions(
        prose_parts,
        declared_names=declared_names,
        accounted_character_ids=accounted_character_ids,
        roster_rows=await read_character_roster_from_async_connection(conn),
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

    presence = wire.presence
    end_roster = _end_of_turn_roster(presence, presence_baseline)
    mentions = presence.mentions if presence is not None else []
    parent_present = presence_baseline.present if presence_baseline is not None else []
    reconciled = reconcile_public_prose_mentions(
        [wire.narrative, *wire.choices],
        accounted_references=[*end_roster, *mentions, *parent_present],
        roster_rows=roster_rows,
    )

    if reconciled:
        if wire.presence is None:
            wire.presence = PresenceDelta()
        wire.presence.mentions.extend(reconciled)

    return wire
