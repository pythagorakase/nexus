"""
Entity Query Methods for LORE

Provides hierarchical entity queries with universal baseline + featured tracking.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from nexus.agents.orrery.player_identity import canonical_player_character_id
from nexus.presence.roster import read_roster, read_rosters


logger = logging.getLogger("nexus.lore.entity_queries")

FACTION_TAG_CONTEXT_CATEGORIES = (
    "ideology",
    "resource_base",
    "legitimacy",
    "operational_mode",
    "power_status",
    "agenda",
)


def _attributed_tag_summary_join(*, table: str, kind: str) -> str:
    """Share the current-tag view and frontier expiry rule across dossiers.

    Table and kind are internal SQL identifiers, never caller-supplied values.
    The view owns soft clears, deprecated tags, and synonyms; world-time expiry
    stays separate from the wall-clock clearance timestamp.
    """
    category_filter = ""
    if kind == "faction":
        categories = ", ".join(
            f"'{category}'" for category in FACTION_TAG_CONTEXT_CATEGORIES
        )
        category_filter = f"AND etc.category IN ({categories})"
    return f"""
        LEFT JOIN LATERAL (
            SELECT COALESCE(
                string_agg(
                    etc.category || ':' || etc.tag,
                    ', ' ORDER BY etc.category, etc.tag
                ),
                ''
            ) AS orrery_tag_summary
            FROM entity_tags_current etc
            WHERE etc.entity_id = {table}.entity_id
              AND etc.entity_kind = '{kind}'
              {category_filter}
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
        ) AS attributed_tags ON true
    """


def fetch_present_character_ids(session: Session, chunk_id: int) -> List[int]:
    """Return the exact present-character roster recorded for one chunk."""

    return sorted(read_roster(session, chunk_id).present_character_ids)


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
        - baseline: All characters with activity, location, and current tags
        - featured: Referenced characters with full details, tags, and reference_type
    """
    # Keep character IDs and the canonical roster independent of entity IDs.
    tag_join = _attributed_tag_summary_join(table="characters", kind="character")
    baseline_query = text(
        f"""
        SELECT
            id, name, summary,
            current_activity, current_location, orrery_tag_summary
        FROM characters
        {tag_join}
        ORDER BY name
    """
    )
    baseline_rows = session.execute(baseline_query).fetchall()

    user_char_id = canonical_player_character_id(session)
    logger.debug("Canonical user character ID: %d", user_char_id)

    # Get character IDs referenced in chunks
    featured_ids = {}
    if featured_chunk_ids:
        rosters = read_rosters(session, featured_chunk_ids)
        anchor = rosters[max(featured_chunk_ids)]
        for chunk_id in sorted(rosters, reverse=True):
            for (kind, character_id), entry in rosters[chunk_id].all_references.items():
                if (
                    kind != "character"
                    or character_id == user_char_id
                    or character_id in featured_ids
                ):
                    continue
                key = (kind, character_id)
                featured_ids[character_id] = (
                    "present"
                    if key in anchor.present
                    else "mentioned" if key in anchor.referenced else "recent"
                )
                if len(featured_ids) >= max_featured_characters:
                    break
            if len(featured_ids) >= max_featured_characters:
                break

    # ALWAYS feature the user character, regardless of chunk references
    if user_char_id not in featured_ids:
        featured_ids[user_char_id] = "user_character"
        logger.debug(f"Added user character (ID {user_char_id}) to featured list")

    # Get full details for featured characters
    featured_rows: Sequence[Any] = []
    if featured_ids:
        featured_query = text(
            f"""
            SELECT
                id, name, summary, appearance, background,
                personality, emotional_state, current_activity,
                current_location, extra_data, orrery_tag_summary
            FROM characters
            {tag_join}
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
    tag_join = _attributed_tag_summary_join(table="f", kind="faction")
    baseline_query = text(
        f"""
        SELECT f.id, f.name, f.summary, orrery_tag_summary
        FROM factions f
        {tag_join}
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
                orrery_tag_summary
            FROM factions f
            {tag_join}
            WHERE f.id = ANY(:ids)
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
