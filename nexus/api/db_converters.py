"""
Database Conversion Utilities
==============================

Converts between Pydantic models (LLM-friendly) and PostgreSQL types.
Handles time conversion, episode/season calculation, and entity resolution.
"""

import json
import logging
from datetime import timedelta
from typing import Optional, Tuple, List, Dict, Any
import asyncpg
from nexus.agents.logon.apex_schema import (
    ChronologyUpdate,
    PlaceReference,
    CharacterReference,
    FactionReference,
    NewCharacter,
    NewPlace,
    NewFaction,
    PlaceReferenceType,
    ReferenceType,
    ReferencedEntities
)
from nexus.agents.orrery.tag_writer import apply_tag_bestowal_async

logger = logging.getLogger("nexus.api.db_converters")


def _json_dumps_model(value: Any) -> Optional[str]:
    """Serialize dicts or Pydantic models for JSONB columns."""

    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", exclude_none=True)
    return json.dumps(value)


# ============================================================================
# Time Conversion Functions
# ============================================================================

def time_fields_to_interval(
    minutes: Optional[int] = None,
    hours: Optional[int] = None,
    days: Optional[int] = None
) -> Optional[timedelta]:
    """
    Convert LLM-friendly time fields to PostgreSQL interval.

    Args:
        minutes: Minutes component (0-59)
        hours: Hours component (0-23)
        days: Days component (0+)

    Returns:
        timedelta object or None if all inputs are None
    """
    if all(f is None for f in [minutes, hours, days]):
        return None

    return timedelta(
        days=days or 0,
        hours=hours or 0,
        minutes=minutes or 0
    )


def interval_to_time_fields(interval: timedelta) -> Tuple[int, int, int]:
    """
    Convert PostgreSQL interval to LLM-friendly time fields.

    Args:
        interval: timedelta from database

    Returns:
        Tuple of (minutes, hours, days)
    """
    total_seconds = int(interval.total_seconds())

    days = total_seconds // 86400
    remaining = total_seconds % 86400

    hours = remaining // 3600
    remaining = remaining % 3600

    minutes = remaining // 60

    return (minutes, hours, days)


# ============================================================================
# Episode/Season Conversion
# ============================================================================

def chronology_to_db_values(
    chronology: ChronologyUpdate,
    current_season: int,
    current_episode: int
) -> dict:
    """
    Convert ChronologyUpdate (transitions) to absolute DB values.

    Args:
        chronology: Pydantic chronology update with transitions
        current_season: Current season number from parent chunk
        current_episode: Current episode number from parent chunk

    Returns:
        Dict with season, episode, time_delta for database insertion
    """
    # Calculate new season/episode based on transition
    if chronology.episode_transition == "new_season":
        new_season = current_season + 1
        new_episode = 1  # Seasons always start at episode 1
    elif chronology.episode_transition == "new_episode":
        new_season = current_season
        new_episode = current_episode + 1
    else:  # continue
        new_season = current_season
        new_episode = current_episode

    # Convert time fields to interval
    time_delta = time_fields_to_interval(
        minutes=chronology.time_delta_minutes,
        hours=chronology.time_delta_hours,
        days=chronology.time_delta_days
    )

    return {
        "season": new_season,
        "episode": new_episode,
        "time_delta": time_delta
    }


async def resolve_place_references(
    place_references: List[PlaceReference],
    conn: asyncpg.Connection
) -> List[dict]:
    """
    Resolve place references to place IDs, creating new places as needed.

    Two-step process:
    1. Create any new places and get their IDs
    2. Build list of (place_id, reference_type, evidence) tuples for junction table

    Args:
        place_references: List of PlaceReference objects from LLM
        conn: Database connection

    Returns:
        List of dicts ready for junction table insertion
    """
    resolved_refs = []

    for ref in place_references:
        place_id = None

        # Step 1: Get or create place ID
        if ref.place_id:
            place_id = ref.place_id
        elif ref.place_name:
            # Look up existing place by name
            place_id = await lookup_place_by_name(conn, ref.place_name)
            if not place_id and ref.new_place:
                place_id = await create_new_place(conn, ref.new_place)
            elif not place_id:
                logger.warning(
                    "Skipping unresolved place reference %r; provide place_id "
                    "or new_place to persist place_chunk_references",
                    ref.place_name,
                )
                continue
        elif ref.new_place:
            # Create new place and get ID
            place_id = await create_new_place(conn, ref.new_place)

        # Step 2: Build junction table entry
        resolved_refs.append({
            "place_id": place_id,
            "reference_type": ref.reference_type.value,
            "evidence": ref.evidence
        })

    return resolved_refs


async def lookup_place_by_name(conn: asyncpg.Connection, name: str) -> Optional[int]:
    """Look up place ID by name"""
    result = await conn.fetchval(
        "SELECT id FROM places WHERE name = $1",
        name
    )
    return result


async def create_new_place(conn: asyncpg.Connection, new_place: NewPlace) -> int:
    """
    Create a new place in the database.

    Returns:
        ID of newly created place
    """
    # Insert place
    place_id = await conn.fetchval("""
        INSERT INTO places (
            name, type, summary, history, current_status, secrets,
            extra_data
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
    """,
        new_place.name,
        new_place.type.value if new_place.type else None,
        new_place.summary,
        new_place.history,
        new_place.current_status,
        new_place.secrets,
        _json_dumps_model(new_place.extra_data),
    )

    return place_id


# ============================================================================
# Character Reference Resolution
# ============================================================================

async def resolve_character_references(
    character_references: List[CharacterReference],
    conn: asyncpg.Connection
) -> List[dict]:
    """
    Resolve character references, creating new characters as needed.

    Two-step process:
    1. Create new characters and get their IDs
    2. Build list of (character_id, reference_type) for junction table
    """
    resolved_refs = []

    for ref in character_references:
        char_id = None

        # Get or create character ID
        if ref.character_id:
            char_id = ref.character_id
        elif ref.character_name:
            char_id = await lookup_character_by_name(conn, ref.character_name)
            if not char_id and ref.new_character:
                char_id = await create_new_character(conn, ref.new_character)
            elif not char_id:
                logger.warning(
                    "Skipping unresolved character reference %r; provide "
                    "character_id or new_character to persist "
                    "chunk_character_references",
                    ref.character_name,
                )
                continue
        elif ref.new_character:
            # Create new character
            char_id = await create_new_character(conn, ref.new_character)

        # Build junction table entry
        resolved_refs.append({
            "character_id": char_id,
            "reference": ref.reference_type.value
        })

    return resolved_refs


async def lookup_character_by_name(conn: asyncpg.Connection, name: str) -> Optional[int]:
    """Look up character ID by name"""
    result = await conn.fetchval(
        "SELECT id FROM characters WHERE name = $1",
        name
    )
    return result


async def create_new_character(conn: asyncpg.Connection, new_char: NewCharacter) -> int:
    """
    Create a new character in the database.

    Validates that current_location (place_id) exists before insertion.
    """
    # Validate location exists
    if new_char.current_location:
        location_exists = await conn.fetchval(
            "SELECT id FROM places WHERE id = $1",
            new_char.current_location
        )
        if not location_exists:
            raise ValueError(f"Place ID {new_char.current_location} not found for character location")

    # Insert character
    char_id = await conn.fetchval("""
        INSERT INTO characters (
            name, summary, appearance, background, personality,
            emotional_state, current_activity, current_location, extra_data
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
    """,
        new_char.name,
        new_char.summary,
        new_char.appearance,
        new_char.background,
        new_char.personality,
        new_char.emotional_state,
        new_char.current_activity,
        new_char.current_location,
        _json_dumps_model(new_char.extra_data),
    )

    return char_id


# ============================================================================
# Faction Reference Resolution
# ============================================================================

async def resolve_faction_references(
    faction_references: List[FactionReference],
    conn: asyncpg.Connection
) -> List[dict]:
    """
    Resolve faction references, creating new factions as needed.

    Two-step process:
    1. Create new factions and get their IDs
    2. Build list of faction_ids for junction table
    """
    resolved_refs = []

    for ref in faction_references:
        faction_id = None

        # Get or create faction ID
        if ref.faction_id:
            faction_id = ref.faction_id
        elif ref.faction_name:
            faction_id = await lookup_faction_by_name(conn, ref.faction_name)
            if not faction_id and ref.new_faction:
                faction_id = await create_new_faction(conn, ref.new_faction)
            elif not faction_id:
                logger.warning(
                    "Skipping unresolved faction reference %r; provide faction_id "
                    "or new_faction to persist chunk_faction_references",
                    ref.faction_name,
                )
                continue
        elif ref.new_faction:
            # Create new faction
            faction_id = await create_new_faction(conn, ref.new_faction)

        # Build junction table entry
        resolved_refs.append({
            "faction_id": faction_id
        })

    return resolved_refs


async def lookup_faction_by_name(conn: asyncpg.Connection, name: str) -> Optional[int]:
    """Look up faction ID by name"""
    result = await conn.fetchval(
        "SELECT id FROM factions WHERE name = $1",
        name
    )
    return result


async def create_new_faction(conn: asyncpg.Connection, new_faction: NewFaction) -> int:
    """Create a new faction in the database."""
    # Validate primary_location exists
    if new_faction.primary_location:
        location_exists = await conn.fetchval(
            "SELECT id FROM places WHERE id = $1",
            new_faction.primary_location
        )
        if not location_exists:
            raise ValueError(f"Place ID {new_faction.primary_location} not found for faction location")

    await conn.execute("LOCK TABLE factions IN SHARE ROW EXCLUSIVE MODE")
    faction_id = await conn.fetchval("SELECT COALESCE(MAX(id), 0) + 1 FROM factions")

    # Insert faction
    faction_id = await conn.fetchval("""
        INSERT INTO factions (
            id, name, summary, primary_location, extra_data
        ) VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """,
        faction_id,
        new_faction.name,
        new_faction.summary,
        new_faction.primary_location,
        _json_dumps_model(new_faction.extra_data),
    )

    await apply_new_faction_tags(conn, faction_id, new_faction)
    return faction_id


async def apply_new_faction_tags(
    conn: asyncpg.Connection, faction_id: int, new_faction: NewFaction
) -> None:
    """Apply inline Orrery tags for async-created factions."""

    bestowal = getattr(new_faction, "orrery_tags", None)
    if bestowal is None:
        return

    entity_id = await conn.fetchval(
        "SELECT entity_id FROM factions WHERE id = $1",
        faction_id,
    )
    if entity_id is None:
        raise ValueError(f"Faction ID {faction_id} not found for tag bestowal")

    counters = await apply_tag_bestowal_async(
        conn,
        entity_id=entity_id,
        entity_kind="faction",
        bestowal=bestowal,
        source_kind="skald_inline",
    )
    if any(counters.values()):
        logger.info(f"Tag bestowal faction/{faction_id}: {counters}")
