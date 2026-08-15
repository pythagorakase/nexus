"""
Entity Query Methods for LORE

Provides hierarchical entity queries with universal baseline + featured tracking.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from nexus.agents.orrery.player_identity import canonical_player_character_id

logger = logging.getLogger("nexus.lore.entity_queries")

FACTION_TAG_CONTEXT_CATEGORIES = (
    "ideology",
    "resource_base",
    "legitimacy",
    "operational_mode",
    "power_status",
    "agenda",
)
FACTION_TAG_CONTEXT_CATEGORY_SQL = ", ".join(
    f"'{category}'" for category in FACTION_TAG_CONTEXT_CATEGORIES
)


def fetch_present_character_ids(session: Session, chunk_id: int) -> List[int]:
    """Return the exact present-character roster recorded for one chunk."""

    if chunk_id <= 0:
        raise ValueError("chunk_id must be positive")
    rows = session.execute(
        text(
            """
            SELECT character_id
            FROM chunk_character_references
            WHERE chunk_id = :chunk_id
              AND reference::text = 'present'
            ORDER BY character_id
            """
        ),
        {"chunk_id": chunk_id},
    ).fetchall()
    return sorted({int(row.character_id) for row in rows})


def fetch_all_characters_with_references(
    session: Session,
    featured_chunk_ids: List[int],
    *,
    max_featured_characters: int,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch ALL characters with baseline tracking fields, plus referenced details.

    Args:
        session: SQLAlchemy session
        featured_chunk_ids: Chunk IDs to check for character references
        max_featured_characters: Maximum non-user warm-slice characters to feature

    Returns:
        Dict with:
        - baseline: All characters with activity and location fields
        - featured: Referenced characters with full details + reference_type
    """
    # Get ALL characters with baseline fields
    baseline_query = text(
        """
        SELECT
            id, name, summary,
            current_activity, current_location
        FROM characters
        ORDER BY name
    """
    )
    baseline_rows = session.execute(baseline_query).fetchall()

    user_char_id = canonical_player_character_id(session)
    logger.debug("Canonical user character ID: %d", user_char_id)

    # Get character IDs referenced in chunks
    featured_ids = {}
    if featured_chunk_ids:
        ref_query = text(
            """
            SELECT character_id, reference
            FROM (
                SELECT DISTINCT ON (character_id)
                    character_id, reference, chunk_id
                FROM chunk_character_references
                WHERE chunk_id = ANY(:chunk_ids)
                  AND character_id IS DISTINCT FROM :user_character_id
                ORDER BY character_id, chunk_id DESC
            ) AS latest_character_references
            ORDER BY chunk_id DESC, character_id
            LIMIT :max_featured_characters
        """
        )
        ref_rows = session.execute(
            ref_query,
            {
                "chunk_ids": featured_chunk_ids,
                "max_featured_characters": max_featured_characters,
                "user_character_id": user_char_id,
            },
        ).fetchall()
        featured_ids = {row.character_id: str(row.reference) for row in ref_rows}

    # ALWAYS feature the user character, regardless of chunk references
    if user_char_id not in featured_ids:
        featured_ids[user_char_id] = "user_character"
        logger.debug(f"Added user character (ID {user_char_id}) to featured list")

    # Get full details for featured characters
    featured_rows: Sequence[Any] = []
    if featured_ids:
        featured_query = text(
            """
            SELECT
                id, name, summary, appearance, background,
                personality, emotional_state, current_activity,
                current_location, extra_data
            FROM characters
            WHERE id = ANY(:ids)
        """
        )
        featured_rows = session.execute(
            featured_query, {"ids": list(featured_ids.keys())}
        ).fetchall()

    return {
        "baseline": [dict(row._mapping) for row in baseline_rows],
        "featured": [
            {**dict(row._mapping), "reference_type": featured_ids.get(row.id)}
            for row in featured_rows
        ],
    }


def fetch_place_ids_by_names(
    session: Session,
    place_names: Set[str],
) -> Set[int]:
    """Resolve canonical place names to unique place IDs.

    Missing or ambiguous names are data errors because callers use these IDs to
    guarantee that featured-character locations receive full place dossiers.
    """
    if not place_names:
        return set()

    rows = session.execute(
        text(
            """
            SELECT id, name
            FROM places
            WHERE name = ANY(:place_names)
            ORDER BY name, id
            """
        ),
        {"place_names": sorted(place_names)},
    ).fetchall()

    ids_by_name: Dict[str, List[int]] = {}
    for row in rows:
        ids_by_name.setdefault(str(row.name), []).append(int(row.id))

    missing_names = place_names - set(ids_by_name)
    if missing_names:
        raise ValueError(
            "Featured-character locations did not resolve to places: "
            f"{sorted(missing_names)}"
        )

    ambiguous_names = {name: ids for name, ids in ids_by_name.items() if len(ids) != 1}
    if ambiguous_names:
        raise ValueError(
            f"Featured-character location names are ambiguous: {ambiguous_names}"
        )

    return {ids[0] for ids in ids_by_name.values()}


def fetch_all_places_with_references(
    session: Session,
    featured_chunk_ids: List[int],
    featured_place_ids: Optional[Set[int]] = None,
    *,
    max_featured_places: int,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch ALL places with baseline tracking fields, plus referenced details.

    Args:
        session: SQLAlchemy session
        featured_chunk_ids: Chunk IDs to check for place references
        featured_place_ids: Additional place IDs to include (e.g., character locations)
        max_featured_places: Maximum warm-slice places to feature

    Returns:
        Dict with:
        - baseline: All places (id, name, type, summary, current_status, coordinates)
        - featured: Referenced places with full details + reference_type
    """
    # Get ALL places with baseline fields
    baseline_query = text(
        """
        SELECT
            id, name, type, summary, current_status,
            ST_X(coordinates::geometry) as longitude,
            ST_Y(coordinates::geometry) as latitude
        FROM places
        ORDER BY name
    """
    )
    baseline_rows = session.execute(baseline_query).fetchall()

    # Get place IDs referenced in chunks
    featured_ids = {}
    if featured_chunk_ids:
        ref_query = text(
            """
            SELECT place_id, reference_type
            FROM (
                SELECT DISTINCT ON (place_id)
                    place_id, reference_type, chunk_id
                FROM place_chunk_references
                WHERE chunk_id = ANY(:chunk_ids)
                -- place_reference_type is setting, transit, mentioned.
                -- Transit is the place-level present/passing-through tier.
                ORDER BY
                    place_id,
                    chunk_id DESC,
                    CASE reference_type::text
                        WHEN 'setting' THEN 0
                        WHEN 'transit' THEN 1
                        WHEN 'mentioned' THEN 2
                        ELSE 3
                    END,
                    reference_type::text
            ) AS latest_place_references
            ORDER BY chunk_id DESC, place_id
            LIMIT :max_featured_places
        """
        )
        ref_rows = session.execute(
            ref_query,
            {
                "chunk_ids": featured_chunk_ids,
                "max_featured_places": max_featured_places,
            },
        ).fetchall()
        featured_ids = {row.place_id: str(row.reference_type) for row in ref_rows}

    # Add additional featured place IDs (e.g., from character current_location)
    if featured_place_ids:
        for pid in featured_place_ids:
            featured_ids.setdefault(pid, "character_location")

    # Get full details for featured places
    featured_rows: Sequence[Any] = []
    if featured_ids:
        featured_query = text(
            """
            SELECT
                id, name, type, zone, summary, inhabitants,
                history, current_status, secrets, extra_data,
                ST_X(coordinates::geometry) as longitude,
                ST_Y(coordinates::geometry) as latitude
            FROM places
            WHERE id = ANY(:ids)
        """
        )
        featured_rows = session.execute(
            featured_query, {"ids": list(featured_ids.keys())}
        ).fetchall()

    return {
        "baseline": [dict(row._mapping) for row in baseline_rows],
        "featured": [
            {**dict(row._mapping), "reference_type": featured_ids.get(row.id)}
            for row in featured_rows
        ],
    }


def fetch_all_factions_with_references(
    session: Session,
    featured_chunk_ids: List[int],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch ALL factions with baseline tracking fields, plus referenced details.

    Args:
        session: SQLAlchemy session
        featured_chunk_ids: Chunk IDs to check for faction references

    Returns:
        Dict with:
        - baseline: All factions (id, name, summary, orrery_tag_summary)
        - featured: Referenced factions with details and current Orrery tags
    """
    # Get ALL factions with baseline fields
    baseline_query = text(
        f"""
        SELECT
            f.id,
            f.name,
            f.summary,
            COALESCE(
                string_agg(
                    etc.category || ':' || etc.tag,
                    ', '
                    ORDER BY etc.category, etc.tag
                ) FILTER (WHERE etc.tag IS NOT NULL),
                ''
            ) AS orrery_tag_summary
        FROM factions f
        LEFT JOIN entity_tags_current etc
               ON etc.entity_id = f.entity_id
              AND etc.entity_kind = 'faction'
              AND etc.category IN ({FACTION_TAG_CONTEXT_CATEGORY_SQL})
              AND EXISTS (
                    SELECT 1 FROM entity_tags et
                    WHERE et.id = etc.entity_tag_id
                      AND (
                            (SELECT max(world_time) FROM chunk_metadata) IS NULL
                            OR et.expires_at_world_time IS NULL
                            OR et.expires_at_world_time > (
                                SELECT max(world_time) FROM chunk_metadata
                            )
                          )
                  )
        GROUP BY f.id
        ORDER BY f.name
    """
    )
    baseline_rows = session.execute(baseline_query).fetchall()

    # Get faction IDs referenced in chunks
    featured_ids = set()
    if featured_chunk_ids:
        ref_query = text(
            """
            SELECT DISTINCT faction_id
            FROM chunk_faction_references
            WHERE chunk_id = ANY(:chunk_ids)
        """
        )
        ref_rows = session.execute(
            ref_query, {"chunk_ids": featured_chunk_ids}
        ).fetchall()
        featured_ids = {row.faction_id for row in ref_rows}

    # Get full details for featured factions
    featured_rows: Sequence[Any] = []
    if featured_ids:
        featured_query = text(
            f"""
            SELECT
                f.id,
                f.name,
                f.summary,
                f.primary_location,
                f.extra_data,
                COALESCE(
                    string_agg(
                        etc.category || ':' || etc.tag,
                        ', '
                        ORDER BY etc.category, etc.tag
                    ) FILTER (WHERE etc.tag IS NOT NULL),
                    ''
                ) AS orrery_tag_summary
            FROM factions f
            LEFT JOIN entity_tags_current etc
                   ON etc.entity_id = f.entity_id
                  AND etc.entity_kind = 'faction'
                  AND etc.category IN ({FACTION_TAG_CONTEXT_CATEGORY_SQL})
                  AND EXISTS (
                        SELECT 1 FROM entity_tags et
                        WHERE et.id = etc.entity_tag_id
                          AND (
                                (SELECT max(world_time) FROM chunk_metadata) IS NULL
                                OR et.expires_at_world_time IS NULL
                                OR et.expires_at_world_time > (
                                    SELECT max(world_time) FROM chunk_metadata
                                )
                              )
                      )
            WHERE f.id = ANY(:ids)
            GROUP BY f.id
            ORDER BY f.name
        """
        )
        featured_rows = session.execute(
            featured_query, {"ids": list(featured_ids)}
        ).fetchall()

    return {
        "baseline": [dict(row._mapping) for row in baseline_rows],
        "featured": [dict(row._mapping) for row in featured_rows],
    }
