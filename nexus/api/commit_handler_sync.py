"""
Synchronous Commit Handler for Narrative Chunks
================================================

Synchronous version of commit_handler.py using psycopg2 for compatibility
with the existing narrative API.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.logon.apex_schema import (
    ChronologyUpdate,
    ReferencedEntities,
    PlaceReference,
    CharacterReference,
    FactionReference,
    StateUpdates
)
from nexus.api.db_converters import (
    chronology_to_db_values,
    get_primary_place_id,
    time_fields_to_interval
)

logger = logging.getLogger("nexus.api.commit_handler_sync")


# ============================================================================
# Entity Resolution Functions (Synchronous)
# ============================================================================

def resolve_place_references_sync(
    place_references: List[PlaceReference],
    conn
) -> List[dict]:
    """Synchronous version of resolve_place_references"""
    resolved_refs = []

    for ref in place_references:
        place_id = None

        with conn.cursor() as cur:
            if ref.place_id:
                place_id = ref.place_id
            elif ref.place_name:
                # Look up existing place by name
                cur.execute("SELECT id FROM places WHERE name = %s", (ref.place_name,))
                result = cur.fetchone()
                if result:
                    place_id = result[0]
                else:
                    raise ValueError(f"Place '{ref.place_name}' not found in database")
            elif ref.new_place:
                # Create new place and get ID
                place_id = create_new_place_sync(cur, ref.new_place)

        # Build junction table entry
        resolved_refs.append({
            "place_id": place_id,
            "reference_type": ref.reference_type.value,
            "evidence": ref.evidence
        })

    return resolved_refs


def create_new_place_sync(cur, new_place):
    """Create a new place synchronously"""
    # Validate zone exists if provided
    if new_place.zone:
        cur.execute("SELECT id FROM zones WHERE id = %s", (new_place.zone,))
        if not cur.fetchone():
            raise ValueError(f"Zone ID {new_place.zone} not found")

    # Insert place
    cur.execute("""
        INSERT INTO places (
            name, summary, history, current_status, secrets,
            extra_data, zone, place_type
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        new_place.name,
        new_place.summary,
        new_place.history,
        new_place.current_status,
        new_place.secrets,
        json.dumps(new_place.extra_data) if new_place.extra_data else None,
        new_place.zone,
        new_place.place_type.value if new_place.place_type else None
    ))

    return cur.fetchone()[0]


def resolve_character_references_sync(
    character_references: List[CharacterReference],
    conn
) -> List[dict]:
    """Synchronous version of resolve_character_references"""
    resolved_refs = []

    for ref in character_references:
        char_id = None

        with conn.cursor() as cur:
            if ref.character_id:
                char_id = ref.character_id
            elif ref.character_name:
                cur.execute("SELECT id FROM characters WHERE name = %s", (ref.character_name,))
                result = cur.fetchone()
                if result:
                    char_id = result[0]
                else:
                    raise ValueError(f"Character '{ref.character_name}' not found")
            elif ref.new_character:
                char_id = create_new_character_sync(cur, ref.new_character)

        # Build junction table entry
        resolved_refs.append({
            "character_id": char_id,
            "reference": ref.reference_type.value
        })

    return resolved_refs


def create_new_character_sync(cur, new_char):
    """Create a new character synchronously"""
    # Validate location exists
    if new_char.current_location:
        cur.execute("SELECT id FROM places WHERE id = %s", (new_char.current_location,))
        if not cur.fetchone():
            raise ValueError(f"Place ID {new_char.current_location} not found for character location")

    # Insert character
    cur.execute("""
        INSERT INTO characters (
            name, summary, appearance, background, personality,
            emotional_state, current_activity, current_location, extra_data
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        new_char.name,
        new_char.summary,
        new_char.appearance,
        new_char.background,
        new_char.personality,
        new_char.emotional_state,
        new_char.current_activity,
        new_char.current_location,
        json.dumps(new_char.extra_data) if new_char.extra_data else None
    ))

    return cur.fetchone()[0]


def resolve_faction_references_sync(
    faction_references: List[FactionReference],
    conn
) -> List[dict]:
    """Synchronous version of resolve_faction_references"""
    resolved_refs = []

    for ref in faction_references:
        faction_id = None

        with conn.cursor() as cur:
            if ref.faction_id:
                faction_id = ref.faction_id
            elif ref.faction_name:
                cur.execute("SELECT id FROM factions WHERE name = %s", (ref.faction_name,))
                result = cur.fetchone()
                if result:
                    faction_id = result[0]
                else:
                    raise ValueError(f"Faction '{ref.faction_name}' not found")
            elif ref.new_faction:
                faction_id = create_new_faction_sync(cur, ref.new_faction)

        # Build junction table entry
        resolved_refs.append({
            "faction_id": faction_id
        })

    return resolved_refs


def create_new_faction_sync(cur, new_faction):
    """Create a new faction synchronously"""
    # Validate primary_location exists
    if new_faction.primary_location:
        cur.execute("SELECT id FROM places WHERE id = %s", (new_faction.primary_location,))
        if not cur.fetchone():
            raise ValueError(f"Place ID {new_faction.primary_location} not found for faction location")

    # Insert faction
    cur.execute("""
        INSERT INTO factions (
            name, summary, ideology, history, current_activity,
            hidden_agenda, territory, power_level, resources,
            primary_location, extra_data
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        new_faction.name,
        new_faction.summary,
        new_faction.ideology,
        new_faction.history,
        new_faction.current_activity,
        new_faction.hidden_agenda,
        new_faction.territory,
        new_faction.power_level,
        new_faction.resources,
        new_faction.primary_location,
        json.dumps(new_faction.extra_data) if new_faction.extra_data else None
    ))

    return cur.fetchone()[0]


# ============================================================================
# Main Synchronous Commit Function
# ============================================================================

def commit_incubator_to_database_sync(conn, session_id: str) -> int:
    """
    Synchronous version of commit flow from incubator to production tables.

    Uses psycopg2 connection with transaction management.

    Returns:
        New chunk ID
    """
    try:
        # Start transaction
        with conn:  # This creates a transaction context
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Step 1: Get incubator data
                cur.execute("""
                    SELECT chunk_id, parent_chunk_id, user_text, storyteller_text,
                           metadata_updates, entity_updates, reference_updates,
                           llm_response_id, status
                    FROM incubator
                    WHERE session_id = %s
                """, (session_id,))
                incubator = cur.fetchone()

                if not incubator:
                    raise ValueError(f"No incubator data found for session {session_id}")

                logger.info(f"Processing incubator session {session_id}")

            # Step 2: Get parent context
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT season, episode, scene, world_layer, time_delta, place
                    FROM chunk_metadata
                    WHERE chunk_id = %s
                """, (incubator["parent_chunk_id"],))
                parent_meta = cur.fetchone()

                if not parent_meta:
                    raise ValueError(f"No metadata found for parent chunk {incubator['parent_chunk_id']}")

                logger.info(f"Parent chunk {incubator['parent_chunk_id']}: S{parent_meta['season']}E{parent_meta['episode']} scene {parent_meta['scene']}")

            # Step 3: Resolve entity references
            # Parse referenced entities from JSONB
            ref_entities = ReferencedEntities(**incubator["reference_updates"])

            # Create new entities and resolve all to IDs
            character_refs = resolve_character_references_sync(ref_entities.characters, conn)
            place_refs = resolve_place_references_sync(ref_entities.places, conn)
            faction_refs = resolve_faction_references_sync(ref_entities.factions, conn)

            # Step 4: Convert metadata
            chronology_data = incubator["metadata_updates"].get("chronology", {})
            chronology = ChronologyUpdate(**chronology_data)
            db_meta = chronology_to_db_values(
                chronology,
                current_season=parent_meta["season"],
                current_episode=parent_meta["episode"]
            )

            # Increment scene number
            db_meta["scene"] = parent_meta["scene"] + 1

            # Get world_layer
            world_layer = incubator["metadata_updates"].get("world_layer", "primary")

            # Get primary place for legacy field
            primary_place_id = get_primary_place_id(ref_entities.places)

            # Step 5: Insert narrative chunk
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO narrative_chunks (raw_text, season, episode)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (
                    incubator["storyteller_text"],
                    db_meta["season"],
                    db_meta["episode"]
                ))
                chunk_id = cur.fetchone()[0]
                logger.info(f"Created narrative chunk {chunk_id}")

            # Step 6: Insert chunk metadata
            with conn.cursor() as cur:
                # Generate slug (e.g., "S05E06_001")
                slug = f"S{db_meta['season']:02d}E{db_meta['episode']:02d}_{db_meta['scene']:03d}"

                cur.execute("""
                    INSERT INTO chunk_metadata (
                        chunk_id, season, episode, scene, world_layer,
                        time_delta, place, slug, metadata_version, generation_date
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    chunk_id,
                    db_meta["season"],
                    db_meta["episode"],
                    db_meta["scene"],
                    world_layer,
                    db_meta["time_delta"],
                    primary_place_id,
                    slug,
                    "2.0",  # metadata version
                    datetime.utcnow()
                ))
                logger.info(f"Created metadata for chunk {chunk_id}: {slug}")

            # Step 7: Insert junction table references
            # Insert place references
            if place_refs:
                with conn.cursor() as cur:
                    for ref in place_refs:
                        cur.execute("""
                            INSERT INTO place_chunk_references (place_id, chunk_id, reference_type, evidence)
                            VALUES (%s, %s, %s, %s)
                        """, (ref["place_id"], chunk_id, ref["reference_type"], ref.get("evidence")))
                    logger.info(f"Inserted {len(place_refs)} place references for chunk {chunk_id}")

            # Insert character references
            if character_refs:
                with conn.cursor() as cur:
                    for ref in character_refs:
                        cur.execute("""
                            INSERT INTO chunk_character_references (chunk_id, character_id, reference)
                            VALUES (%s, %s, %s)
                        """, (chunk_id, ref["character_id"], ref["reference"]))
                    logger.info(f"Inserted {len(character_refs)} character references for chunk {chunk_id}")

            # Insert faction references
            if faction_refs:
                with conn.cursor() as cur:
                    for ref in faction_refs:
                        cur.execute("""
                            INSERT INTO chunk_faction_references (chunk_id, faction_id)
                            VALUES (%s, %s)
                        """, (chunk_id, ref["faction_id"]))
                    logger.info(f"Inserted {len(faction_refs)} faction references for chunk {chunk_id}")

            # Step 8: Update entity states (if provided)
            if incubator.get("entity_updates"):
                state_updates = StateUpdates(**incubator["entity_updates"])
                apply_state_updates_sync(conn, state_updates)

            # Step 9: Clear incubator
            with conn.cursor() as cur:
                cur.execute("DELETE FROM incubator WHERE session_id = %s", (session_id,))
                logger.info(f"Cleared incubator for session {session_id}")

            logger.info(f"Successfully committed chunk {chunk_id} from session {session_id}")
            return chunk_id

    except Exception as e:
        logger.error(f"Failed to commit incubator session {session_id}: {e}")
        conn.rollback()  # Explicit rollback on error
        raise


def apply_state_updates_sync(conn, state_updates: StateUpdates):
    """Apply entity state updates synchronously"""
    with conn.cursor() as cur:
        # Update character states
        for char_update in state_updates.characters:
            if char_update.character_id:
                updates = []
                params = []

                if char_update.emotional_state:
                    updates.append("emotional_state = %s")
                    params.append(char_update.emotional_state)

                if char_update.current_activity:
                    updates.append("current_activity = %s")
                    params.append(char_update.current_activity)

                if char_update.current_location:
                    updates.append("current_location = %s")
                    params.append(char_update.current_location)

                if updates:
                    params.append(char_update.character_id)
                    cur.execute(
                        f"UPDATE characters SET {', '.join(updates)} WHERE id = %s",
                        params
                    )
                    logger.info(f"Updated character {char_update.character_id}")

        # Update place states
        for place_update in state_updates.locations:
            if place_update.place_id and place_update.current_status:
                cur.execute(
                    "UPDATE places SET current_status = %s WHERE id = %s",
                    (place_update.current_status, place_update.place_id)
                )
                logger.info(f"Updated place {place_update.place_id}")

        # Update faction states
        for faction_update in state_updates.factions:
            if faction_update.faction_id and faction_update.current_activity:
                cur.execute(
                    "UPDATE factions SET current_activity = %s WHERE id = %s",
                    (faction_update.current_activity, faction_update.faction_id)
                )
                logger.info(f"Updated faction {faction_update.faction_id}")