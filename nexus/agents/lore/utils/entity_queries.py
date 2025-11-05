"""
Entity Query Methods for LORE

Provides hierarchical entity queries with universal baseline + featured tracking.
"""

import logging
from typing import Dict, List, Any, Set, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("nexus.lore.entity_queries")


def fetch_all_characters_with_references(
    session: Session,
    featured_chunk_ids: List[int],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch ALL characters with baseline tracking fields, plus full details for referenced characters.

    Args:
        session: SQLAlchemy session
        featured_chunk_ids: Chunk IDs to check for character references

    Returns:
        Dict with:
        - baseline: All characters (id, name, summary, current_activity, current_location)
        - featured: Referenced characters with full details + reference_type
    """
    # Get ALL characters with baseline fields
    baseline_query = text("""
        SELECT
            id, name, summary,
            current_activity, current_location
        FROM characters
        ORDER BY name
    """)
    baseline_rows = session.execute(baseline_query).fetchall()

    # Get user character ID from global_variables
    user_char_id = None
    try:
        user_char_query = text("""
            SELECT user_character
            FROM global_variables
            WHERE id = true
            LIMIT 1
        """)
        user_char_row = session.execute(user_char_query).fetchone()
        if user_char_row and user_char_row.user_character:
            user_char_id = user_char_row.user_character
            logger.debug(f"User character ID from global_variables: {user_char_id}")
    except Exception as e:
        logger.warning(f"Could not query user_character from global_variables: {e}")

    # Get character IDs referenced in chunks
    featured_ids = {}
    if featured_chunk_ids:
        ref_query = text("""
            SELECT DISTINCT character_id, reference
            FROM chunk_character_references
            WHERE chunk_id = ANY(:chunk_ids)
        """)
        ref_rows = session.execute(ref_query, {"chunk_ids": featured_chunk_ids}).fetchall()
        featured_ids = {row.character_id: str(row.reference) for row in ref_rows}

    # ALWAYS feature the user character, regardless of chunk references
    if user_char_id and user_char_id not in featured_ids:
        featured_ids[user_char_id] = "user_character"
        logger.debug(f"Added user character (ID {user_char_id}) to featured list")

    # Get full details for featured characters
    featured_rows = []
    if featured_ids:
        featured_query = text("""
            SELECT
                id, name, summary, appearance, background,
                personality, emotional_state, current_activity,
                current_location, extra_data
            FROM characters
            WHERE id = ANY(:ids)
        """)
        featured_rows = session.execute(featured_query, {"ids": list(featured_ids.keys())}).fetchall()

    return {
        "baseline": [dict(row._mapping) for row in baseline_rows],
        "featured": [
            {**dict(row._mapping), "reference_type": featured_ids.get(row.id)}
            for row in featured_rows
        ]
    }


def fetch_all_places_with_references(
    session: Session,
    featured_chunk_ids: List[int],
    featured_place_ids: Optional[Set[int]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch ALL places with baseline tracking fields, plus full details for referenced places.

    Args:
        session: SQLAlchemy session
        featured_chunk_ids: Chunk IDs to check for place references
        featured_place_ids: Additional place IDs to include (e.g., character locations)

    Returns:
        Dict with:
        - baseline: All places (id, name, type, summary, current_status, coordinates)
        - featured: Referenced places with full details + reference_type
    """
    # Get ALL places with baseline fields
    baseline_query = text("""
        SELECT
            id, name, type, summary, current_status,
            ST_X(coordinates::geometry) as longitude,
            ST_Y(coordinates::geometry) as latitude
        FROM places
        ORDER BY name
    """)
    baseline_rows = session.execute(baseline_query).fetchall()

    # Get place IDs referenced in chunks
    featured_ids = {}
    if featured_chunk_ids:
        ref_query = text("""
            SELECT DISTINCT place_id, reference_type
            FROM place_chunk_references
            WHERE chunk_id = ANY(:chunk_ids)
        """)
        ref_rows = session.execute(ref_query, {"chunk_ids": featured_chunk_ids}).fetchall()
        featured_ids = {row.place_id: str(row.reference_type) for row in ref_rows}

    # Add additional featured place IDs (e.g., from character current_location)
    if featured_place_ids:
        for pid in featured_place_ids:
            featured_ids.setdefault(pid, "character_location")

    # Get full details for featured places
    featured_rows = []
    if featured_ids:
        featured_query = text("""
            SELECT
                id, name, type, zone, summary, inhabitants,
                history, current_status, secrets, extra_data,
                ST_X(coordinates::geometry) as longitude,
                ST_Y(coordinates::geometry) as latitude
            FROM places
            WHERE id = ANY(:ids)
        """)
        featured_rows = session.execute(featured_query, {"ids": list(featured_ids.keys())}).fetchall()

    return {
        "baseline": [dict(row._mapping) for row in baseline_rows],
        "featured": [
            {**dict(row._mapping), "reference_type": featured_ids.get(row.id)}
            for row in featured_rows
        ]
    }


def fetch_all_factions_with_references(
    session: Session,
    featured_chunk_ids: List[int],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch ALL factions with baseline tracking fields, plus full details for referenced factions.

    Args:
        session: SQLAlchemy session
        featured_chunk_ids: Chunk IDs to check for faction references

    Returns:
        Dict with:
        - baseline: All factions (id, name, summary, current_activity)
        - featured: Referenced factions with full details
    """
    # Get ALL factions with baseline fields
    baseline_query = text("""
        SELECT
            id, name, summary, current_activity
        FROM factions
        ORDER BY name
    """)
    baseline_rows = session.execute(baseline_query).fetchall()

    # Get faction IDs referenced in chunks
    featured_ids = set()
    if featured_chunk_ids:
        ref_query = text("""
            SELECT DISTINCT faction_id
            FROM chunk_faction_references
            WHERE chunk_id = ANY(:chunk_ids)
        """)
        ref_rows = session.execute(ref_query, {"chunk_ids": featured_chunk_ids}).fetchall()
        featured_ids = {row.faction_id for row in ref_rows}

    # Get full details for featured factions
    featured_rows = []
    if featured_ids:
        featured_query = text("""
            SELECT
                id, name, summary, ideology, history,
                current_activity, hidden_agenda, territory,
                primary_location, power_level, resources, extra_data
            FROM factions
            WHERE id = ANY(:ids)
        """)
        featured_rows = session.execute(featured_query, {"ids": list(featured_ids)}).fetchall()

    return {
        "baseline": [dict(row._mapping) for row in baseline_rows],
        "featured": [dict(row._mapping) for row in featured_rows]
    }
