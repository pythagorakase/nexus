"""
Database Conversion Utilities
==============================

Converts between Pydantic models (LLM-friendly) and PostgreSQL types.
Handles time conversion, episode/season calculation, and entity resolution.
"""

import logging
from datetime import timedelta
from typing import List, Mapping, Optional, Sequence, Tuple

import asyncpg  # type: ignore[import-untyped]
from nexus.agents.logon.apex_schema import (
    CharacterReference,
    ChronologyUpdate,
    FactionReference,
    NewEntityDeclaration,
    PlaceReference,
)
from nexus.agents.orrery.geo import (
    resolve_zone_for_point_async,
    story_active_zone_async,
)
from nexus.presence.roster import resolve_reference_async
from nexus.presence.identity import (
    require_character_identity_async,
    refresh_generated_aliases_async,
)


logger = logging.getLogger("nexus.api.db_converters")


# ============================================================================
# Time Conversion Functions
# ============================================================================


def time_fields_to_interval(
    minutes: Optional[int] = None,
    hours: Optional[int] = None,
    days: Optional[int] = None,
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

    return timedelta(days=days or 0, hours=hours or 0, minutes=minutes or 0)


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


def chronology_for_commit(
    chronology: ChronologyUpdate, *, parent_chunk_id: int
) -> ChronologyUpdate:
    """Keep bootstrap in its initial episode without closing an empty span.

    A parentless opening establishes S1E1; its transition does not advance an
    existing episode or season. Apply this same chronology to both numbering
    and summary planning, preserving elapsed time and the staged draft.
    """
    if parent_chunk_id == 0:
        return chronology.model_copy(update={"episode_transition": "continue"})
    return chronology


def chronology_to_db_values(
    chronology: ChronologyUpdate, current_season: int, current_episode: int
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
        days=chronology.time_delta_days,
    )

    return {"season": new_season, "episode": new_episode, "time_delta": time_delta}


async def resolve_place_references(
    place_references: List[PlaceReference], conn: asyncpg.Connection
) -> List[dict]:
    """
    Resolve existing place references to IDs.

    Args:
        place_references: List of PlaceReference objects from LLM
        conn: Database connection

    Returns:
        List of dicts ready for junction table insertion
    """
    resolved_refs = []
    for ref in place_references:
        entry = await resolve_reference_async(
            conn, kind="place", id=ref.place_id, name=ref.place_name
        )
        resolved_refs.append(
            {
                "place_id": entry.id,
                "name": entry.name,
                "reference_type": ref.reference_type.value,
                "evidence": ref.evidence,
            }
        )
    return resolved_refs


async def lookup_place_by_name(conn: asyncpg.Connection, name: str) -> Optional[int]:
    """Look up place ID by name"""
    result = await conn.fetchval("SELECT id FROM places WHERE name = $1", name)
    return result


# ============================================================================
# Declaration Stub Creation
# ============================================================================


async def create_declared_entity_stubs(
    declarations: Sequence[Mapping[str, object]],
    conn: asyncpg.Connection,
    *,
    scene_location: str | None = None,
) -> int:
    """Create missing async-commit entity stubs before resolving references."""

    parsed = [
        NewEntityDeclaration.model_validate(declaration) for declaration in declarations
    ]
    created = 0

    for declaration in parsed:
        if declaration.kind == "character":
            existing = await require_character_identity_async(
                conn,
                declaration.name,
                descriptors=declaration.summary,
                scene_location=scene_location,
                declared_location=declaration.scene_location,
            )
            if existing is not None:
                continue
        table = {
            "character": "characters",
            "place": "places",
            "faction": "factions",
        }[declaration.kind]
        rows = await conn.fetch(
            f"SELECT id FROM {table} WHERE name = $1 ORDER BY id",
            declaration.name,
        )
        if len(rows) > 1:
            raise ValueError(
                f"Declared {declaration.kind} name {declaration.name!r} is "
                f"ambiguous: {len(rows)} existing rows match"
            )
        if rows:
            continue

        if declaration.kind in {"character", "place"}:
            await conn.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    GREATEST((SELECT COALESCE(MAX(id), 0) FROM {table}), 1)
                )
                """
            )

        if declaration.kind == "character":
            await conn.execute(
                """
                INSERT INTO characters (name, summary)
                VALUES ($1, $2)
                """,
                declaration.name,
                declaration.summary,
            )
        elif declaration.kind == "place":
            coordinates = declaration.coordinates
            if coordinates is None:
                zone_id = await story_active_zone_async(conn)
            else:
                zone_id = await resolve_zone_for_point_async(
                    conn,
                    longitude=coordinates.lon,
                    latitude=coordinates.lat,
                )
            await conn.execute(
                """
                INSERT INTO places (name, type, summary, zone, coordinates)
                VALUES (
                    $1, 'fixed_location', $2, $3,
                    CASE
                        WHEN $4::double precision IS NULL THEN NULL
                        ELSE ST_SetSRID(
                            ST_MakePoint($4, $5, 0, 0), 4326
                        )::geography
                    END
                )
                """,
                declaration.name,
                declaration.summary,
                zone_id,
                coordinates.lon if coordinates else None,
                coordinates.lat if coordinates else None,
            )
        else:
            await conn.execute("LOCK TABLE factions IN SHARE ROW EXCLUSIVE MODE")
            next_id = await conn.fetchval(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM factions"
            )
            await conn.execute(
                """
                INSERT INTO factions (id, name, summary)
                VALUES ($1, $2, $3)
                """,
                next_id,
                declaration.name,
                declaration.summary,
            )
        created += 1

    if any(declaration.kind == "character" for declaration in parsed):
        await refresh_generated_aliases_async(conn)
    return created


# ============================================================================
# Character Reference Resolution
# ============================================================================


async def resolve_character_references(
    character_references: List[CharacterReference], conn: asyncpg.Connection
) -> List[dict]:
    """
    Resolve existing character references to IDs.
    """
    resolved_refs = []
    for ref in character_references:
        entry = await resolve_reference_async(
            conn, kind="character", id=ref.character_id, name=ref.character_name
        )
        resolved_refs.append(
            {
                "character_id": entry.id,
                "name": entry.name,
                "reference": ref.reference_type.value,
            }
        )
    return resolved_refs


async def lookup_character_by_name(
    conn: asyncpg.Connection, name: str
) -> Optional[int]:
    """Look up character ID by name"""
    result = await conn.fetchval("SELECT id FROM characters WHERE name = $1", name)
    return result


# ============================================================================
# Faction Reference Resolution
# ============================================================================


async def resolve_faction_references(
    faction_references: List[FactionReference], conn: asyncpg.Connection
) -> List[dict]:
    """
    Resolve existing faction references to IDs.
    """
    resolved_refs = []
    for ref in faction_references:
        entry = await resolve_reference_async(
            conn, kind="faction", id=ref.faction_id, name=ref.faction_name
        )
        resolved_refs.append({"faction_id": entry.id, "name": entry.name})
    return resolved_refs


async def lookup_faction_by_name(conn: asyncpg.Connection, name: str) -> Optional[int]:
    """Look up faction ID by name"""
    result = await conn.fetchval("SELECT id FROM factions WHERE name = $1", name)
    return result
