"""Pre-hydration reconciliation for prose-named character mentions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import os
import re
from typing import Any, Collection, List, Literal, Mapping, Optional, Sequence

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
from nexus.memory.entity_detector import EntityMatch, HighSpecificityEntityDetector
from nexus.util.log_safety import quote_log_value


logger = logging.getLogger("nexus.api.presence_reconciliation")


@dataclass(frozen=True)
class CharacterRosterRows:
    """Prefetched character and alias rows for one turn."""

    characters: List[Any]
    aliases: List[Any]


@dataclass(frozen=True)
class _DeclaredNameCollision:
    """One canonical or alias owner conflicting with a declared name."""

    declared_id: int
    declared_name: str
    conflict_id: int
    conflict_name: str
    conflict_kind: Literal["canonical", "alias_of"]


@dataclass(frozen=True)
class _CharacterMatchSpan:
    """One canonical-name or alias match in public prose."""

    lookup_key: str
    start: int
    end: int


class _LongestMatchCharacterDetector(HighSpecificityEntityDetector):
    """Character detector that suppresses strictly contained shorter spans."""

    def detect_entities(self, text: str) -> EntityMatch:
        """Detect characters using longest-match-wins full containment."""

        if not text:
            return EntityMatch(characters=[], places=[], factions=[])

        text_lower = text.lower()
        candidates: List[_CharacterMatchSpan] = []
        for lookup_key in self.character_lookup:
            pattern = rf"\b{re.escape(lookup_key)}\b"
            candidates.extend(
                _CharacterMatchSpan(
                    lookup_key=lookup_key,
                    start=match.start(),
                    end=match.end(),
                )
                for match in re.finditer(pattern, text_lower)
            )

        accepted_indices: set[int] = set()
        by_descending_length = sorted(
            range(len(candidates)),
            key=lambda index: (
                -(candidates[index].end - candidates[index].start),
                candidates[index].start,
                candidates[index].end,
                candidates[index].lookup_key,
            ),
        )
        for candidate_index in by_descending_length:
            candidate = candidates[candidate_index]
            if any(
                candidates[accepted_index].start <= candidate.start
                and candidate.end <= candidates[accepted_index].end
                and (
                    candidates[accepted_index].end - candidates[accepted_index].start
                    > candidate.end - candidate.start
                )
                for accepted_index in accepted_indices
            ):
                continue
            accepted_indices.add(candidate_index)

        found_characters: dict[int, Any] = {}
        for index, candidate in enumerate(candidates):
            if index not in accepted_indices:
                continue
            character = self.character_lookup[candidate.lookup_key]
            found_characters[int(character["id"])] = character

        return EntityMatch(
            characters=list(found_characters.values()),
            places=[],
            factions=[],
        )


def build_character_presence_detector(
    character_rows: Sequence[Any],
    alias_rows: Sequence[Any],
) -> HighSpecificityEntityDetector:
    """Build the shared longest-match character detector for presence paths."""

    detector = _LongestMatchCharacterDetector(db_connection=None)
    characters: dict[int, Any] = {}
    for row in character_rows:
        character_id = int(row["id"])
        record = {
            "id": character_id,
            "name": row["name"],
            "summary": (row["summary"] or "")[:100] or None,
        }
        characters[character_id] = record
        detector.character_lookup[str(record["name"]).lower()] = record
    for row in alias_rows:
        character_id = int(row["character_id"])
        if character_id in characters:
            detector.character_lookup[str(row["alias"]).lower()] = characters[
                character_id
            ]
    return detector


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

    detector = build_character_presence_detector(
        roster_rows.characters,
        roster_rows.aliases,
    )
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


def reconcile_public_prose_mentions_by_character_ids(
    prose_parts: Sequence[str],
    *,
    accounted_character_ids: Collection[int],
    roster_rows: CharacterRosterRows,
) -> List[PresenceRef]:
    """Return prose mentions not already accounted for by character ID."""

    accounted_ids = set(accounted_character_ids)
    accounted_references = [
        PresenceRef(
            kind="character",
            name=str(character["name"]),
            id=int(character["id"]),
        )
        for character in roster_rows.characters
        if int(character["id"]) in accounted_ids
    ]
    return reconcile_public_prose_mentions(
        prose_parts,
        accounted_references=accounted_references,
        roster_rows=roster_rows,
    )


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
    collisions = _declared_name_collisions(declared_rows, roster_rows)
    colliding_ids = set(collisions)
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
        candidate_character_ids=declared_ids - colliding_ids,
    )
    for canonical in reconciled:
        logger.warning(
            "presence declared mention normalized: %s",
            quote_log_value(canonical.name),
        )

    for declared_row in declared_rows:
        declared_id = int(declared_row["id"])
        if declared_id not in colliding_ids:
            continue
        declared_roster = CharacterRosterRows(
            characters=[declared_row],
            aliases=[],
        )
        detected = _unaccounted_public_prose_mentions(
            prose_parts,
            accounted_references=[],
            roster_rows=declared_roster,
            candidate_character_ids={declared_id},
        )
        if not detected:
            continue
        for collision in collisions[declared_id]:
            logger.warning(
                "presence declared mention collision: declared=%s id=%s "
                "conflicts %s=%s id=%s",
                quote_log_value(collision.declared_name),
                collision.declared_id,
                collision.conflict_kind,
                quote_log_value(collision.conflict_name),
                collision.conflict_id,
            )
        reconciled.extend(
            _unaccounted_public_prose_mentions(
                prose_parts,
                accounted_references=accounted_references,
                roster_rows=declared_roster,
                candidate_character_ids={declared_id},
            )
        )
    return reconciled


def _declared_name_collisions(
    declared_rows: Sequence[Any],
    roster_rows: CharacterRosterRows,
) -> dict[int, List[_DeclaredNameCollision]]:
    """Return case-insensitive canonical/alias conflicts for declared names."""

    characters_by_id = {
        int(character["id"]): character for character in roster_rows.characters
    }
    result: dict[int, List[_DeclaredNameCollision]] = {}

    for declared in declared_rows:
        declared_id = int(declared["id"])
        declared_name = str(declared["name"])
        declared_key = declared_name.casefold()
        conflicts_by_id: dict[int, _DeclaredNameCollision] = {}

        for character_id, character in characters_by_id.items():
            if character_id == declared_id:
                continue
            conflict_name = str(character["name"])
            if conflict_name.casefold() != declared_key:
                continue
            conflicts_by_id[character_id] = _DeclaredNameCollision(
                declared_id=declared_id,
                declared_name=declared_name,
                conflict_id=character_id,
                conflict_name=conflict_name,
                conflict_kind="canonical",
            )

        for alias in roster_rows.aliases:
            character_id = int(alias["character_id"])
            if (
                character_id == declared_id
                or character_id in conflicts_by_id
                or str(alias["alias"]).casefold() != declared_key
            ):
                continue
            character = characters_by_id.get(character_id)
            if character is None:
                continue
            conflicts_by_id[character_id] = _DeclaredNameCollision(
                declared_id=declared_id,
                declared_name=declared_name,
                conflict_id=character_id,
                conflict_name=str(character["name"]),
                conflict_kind="alias_of",
            )

        if conflicts_by_id:
            result[declared_id] = [
                conflicts_by_id[character_id]
                for character_id in sorted(conflicts_by_id)
            ]

    return result


def reconcile_declared_character_mentions(
    conn: Any,
    prose_parts: Sequence[str],
    *,
    declarations: Sequence[Mapping[str, Any]],
    accounted_character_ids: Collection[int],
    roster_rows: Optional[CharacterRosterRows] = None,
) -> List[PresenceRef]:
    """Reconcile same-turn declarations inside a psycopg2 commit transaction."""

    declared_names = _declared_character_names(declarations)
    if not declared_names:
        return []
    return _reconcile_declared_character_mentions(
        prose_parts,
        declared_names=declared_names,
        accounted_character_ids=accounted_character_ids,
        roster_rows=roster_rows or read_character_roster_from_connection(conn),
    )


async def reconcile_declared_character_mentions_async(
    conn: Any,
    prose_parts: Sequence[str],
    *,
    declarations: Sequence[Mapping[str, Any]],
    accounted_character_ids: Collection[int],
    roster_rows: Optional[CharacterRosterRows] = None,
) -> List[PresenceRef]:
    """Reconcile same-turn declarations inside an asyncpg commit transaction."""

    declared_names = _declared_character_names(declarations)
    if not declared_names:
        return []
    active_roster = roster_rows
    if active_roster is None:
        active_roster = await read_character_roster_from_async_connection(conn)
    return _reconcile_declared_character_mentions(
        prose_parts,
        declared_names=declared_names,
        accounted_character_ids=accounted_character_ids,
        roster_rows=active_roster,
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
