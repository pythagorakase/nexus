"""Pre-hydration reconciliation for prose-named character mentions."""

from __future__ import annotations

from nexus.database import connection_kwargs

import asyncio
from dataclasses import dataclass
import logging
import os
import re
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
)
from nexus.memory.entity_detector import EntityMatch, HighSpecificityEntityDetector
from nexus.presence.roster import (
    RosterEntry,
    apply_delta,
    character_identity_index,
    roster_from_baseline,
)
from nexus.util.log_safety import quote_log_value


logger = logging.getLogger("nexus.api.presence_reconciliation")


@dataclass(frozen=True)
class CharacterRosterRows:
    """Prefetched character and alias rows for one turn."""

    characters: List[Any]
    aliases: List[Any]


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

        text_lower = text.casefold()
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
            ambiguous = getattr(self, "ambiguous_names", {})
            if candidate.lookup_key.casefold() in ambiguous:
                raise ValueError(
                    f"Ambiguous character name {candidate.lookup_key!r}: {sorted(ambiguous[candidate.lookup_key.casefold()])}"
                )
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
    index = character_identity_index(character_rows, alias_rows)
    records = {
        int(row["id"]): {
            "id": int(row["id"]),
            "name": row["name"],
            "summary": (row["summary"] or "")[:100] or None,
        }
        for row in character_rows
    }
    detector.ambiguous_names = {}
    for (_, name), keys in index.by_name.items():
        if len(keys) > 1:
            detector.ambiguous_names[name] = {int(key[1]) for key in keys}
            detector.character_lookup[name] = None
        else:
            detector.character_lookup[name] = records[int(next(iter(keys))[1])]
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

    conn = psycopg2.connect(**connection_kwargs(dbname))
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


def _reconciliation_detector(
    roster_rows: CharacterRosterRows,
) -> HighSpecificityEntityDetector:
    """Build the shared detector with fail-loud ambiguous identity handling."""

    return build_character_presence_detector(
        roster_rows.characters, roster_rows.aliases
    )


def _end_of_turn_roster(
    presence: Optional[PresenceDelta],
    baseline: Optional[PresenceBaseline],
) -> List[CharacterRef]:
    """Apply the same end-roster algebra used by Skald hydration."""

    if baseline is None:
        baseline = PresenceBaseline()
    roster = apply_delta(roster_from_baseline(baseline), presence)
    return [
        CharacterRef(kind="character", id=entry.id, name=entry.name)
        for entry in roster.present.values()
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

    index = character_identity_index(roster_rows.characters, roster_rows.aliases)
    if presence_baseline is not None:
        presence_baseline.present = [
            CharacterRef(kind="character", id=resolved.id, name=resolved.name)
            for ref in presence_baseline.present
            for resolved in [
                index.resolve(RosterEntry(kind="character", id=ref.id, name=ref.name))
            ]
        ]
    if wire.presence is not None:
        references = [
            *wire.presence.enter,
            *wire.presence.exit,
            *wire.presence.mentions,
        ]
        if wire.presence.scene_reset is not None:
            references.extend(wire.presence.scene_reset.present)
        for ref in references:
            if ref.kind == "character":
                resolved = index.resolve(
                    RosterEntry(kind="character", id=ref.id, name=ref.name)
                )
                ref.id, ref.name = resolved.id, resolved.name
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
