"""
Commit Handler for Narrative Chunks
====================================

Handles the complete flow of committing narrative chunks from incubator
to production tables. Includes entity creation, reference resolution,
and transaction management.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncpg

from nexus.agents.logon.apex_schema import (
    ChronologyUpdate,
    ReferencedEntities,
    StateUpdates
)
from nexus.api.db_converters import (
    chronology_to_db_values,
    resolve_character_references,
    resolve_place_references,
    resolve_faction_references
)
from nexus.api.summary_triggers import (
    SummaryTask,
    plan_summary_tasks,
    schedule_summary_generation
)

logger = logging.getLogger("nexus.api.commit_handler")


# ============================================================================
# Database Query Functions
# ============================================================================

async def fetch_incubator_data(
    conn: asyncpg.Connection,
    session_id: str
) -> Dict[str, Any]:
    """
    Fetch data from incubator table for a given session.
    """
    row = await conn.fetchrow(
        """
        SELECT chunk_id, parent_chunk_id, user_text, storyteller_text,
               metadata_updates, entity_updates, reference_updates,
               llm_response_id, status
        FROM incubator
        WHERE session_id = $1
        """,
        session_id
    )

    if not row:
        raise ValueError(f"No incubator data found for session {session_id}")

    return dict(row)


async def fetch_chunk_metadata(
    conn: asyncpg.Connection,
    chunk_id: int
) -> Dict[str, Any]:
    """
    Fetch metadata for an existing chunk.
    """
    row = await conn.fetchrow(
        """
        SELECT season, episode, scene, world_layer, time_delta
        FROM chunk_metadata
        WHERE chunk_id = $1
        """,
        chunk_id
    )

    if not row:
        raise ValueError(f"No metadata found for chunk {chunk_id}")

    return dict(row)


# ============================================================================
# Insert Functions
# ============================================================================

async def insert_narrative_chunk(
    conn: asyncpg.Connection,
    raw_text: str,
    season: int,
    episode: int
) -> int:
    """
    Insert a new narrative chunk and return its ID.
    """
    chunk_id = await conn.fetchval(
        """
        INSERT INTO narrative_chunks (raw_text, season, episode)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        raw_text,
        season,
        episode
    )
    logger.info(f"Created narrative chunk {chunk_id}")
    return chunk_id


async def insert_chunk_metadata(
    conn: asyncpg.Connection,
    chunk_id: int,
    season: int,
    episode: int,
    scene: int,
    world_layer: str,
    time_delta: Optional[Any],
    generation_date: Optional[datetime] = None
) -> None:
    """
    Insert metadata for a chunk.
    """
    # Generate slug (e.g., "S05E06_001")
    slug = f"S{season:02d}E{episode:02d}_{scene:03d}"
    generation_timestamp = generation_date or datetime.utcnow()

    await conn.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer,
            time_delta, generation_date, slug
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        chunk_id,
        season,
        episode,
        scene,
        world_layer,
        time_delta,
        generation_timestamp,
        slug,
    )
    logger.info(f"Created metadata for chunk {chunk_id}: {slug}")


async def insert_place_references(
    conn: asyncpg.Connection,
    chunk_id: int,
    place_refs: list
) -> None:
    """
    Insert place-chunk references into junction table.
    """
    if not place_refs:
        return

    for ref in place_refs:
        await conn.execute(
            """
            INSERT INTO place_chunk_references (place_id, chunk_id, reference_type, evidence)
            VALUES ($1, $2, $3, $4)
            """,
            ref["place_id"],
            chunk_id,
            ref["reference_type"],
            ref.get("evidence")
        )
    logger.info(f"Inserted {len(place_refs)} place references for chunk {chunk_id}")


async def insert_character_references(
    conn: asyncpg.Connection,
    chunk_id: int,
    char_refs: list
) -> None:
    """
    Insert character-chunk references into junction table.
    """
    if not char_refs:
        return

    for ref in char_refs:
        await conn.execute(
            """
            INSERT INTO chunk_character_references (chunk_id, character_id, reference)
            VALUES ($1, $2, $3)
            """,
            chunk_id,
            ref["character_id"],
            ref["reference"]
        )
    logger.info(f"Inserted {len(char_refs)} character references for chunk {chunk_id}")


async def insert_faction_references(
    conn: asyncpg.Connection,
    chunk_id: int,
    faction_refs: list
) -> None:
    """
    Insert faction-chunk references into junction table.
    """
    if not faction_refs:
        return

    for ref in faction_refs:
        await conn.execute(
            """
            INSERT INTO chunk_faction_references (chunk_id, faction_id)
            VALUES ($1, $2)
            """,
            chunk_id,
            ref["faction_id"]
        )
    logger.info(f"Inserted {len(faction_refs)} faction references for chunk {chunk_id}")


# ============================================================================
# State Update Functions
# ============================================================================

async def apply_state_updates(
    conn: asyncpg.Connection,
    state_updates: StateUpdates
) -> None:
    """
    Apply entity state updates from the LLM response.

    This updates current_activity, emotional_state, etc. for characters,
    and similar fields for places and factions.
    """
    # Update character states
    for char_update in state_updates.characters:
        if char_update.character_id:
            updates = []
            params = []
            param_count = 1

            if char_update.emotional_state:
                updates.append(f"emotional_state = ${param_count}")
                params.append(char_update.emotional_state)
                param_count += 1

            if char_update.current_activity:
                updates.append(f"current_activity = ${param_count}")
                params.append(char_update.current_activity)
                param_count += 1

            if char_update.current_location:
                updates.append(f"current_location = ${param_count}")
                params.append(char_update.current_location)
                param_count += 1

            if updates:
                params.append(char_update.character_id)
                await conn.execute(
                    f"""
                    UPDATE characters
                    SET {', '.join(updates)}
                    WHERE id = ${param_count}
                    """,
                    *params
                )
                logger.info(f"Updated character {char_update.character_id}")

    # Update place states
    for place_update in state_updates.locations:
        if place_update.place_id and place_update.current_status:
            await conn.execute(
                """
                UPDATE places
                SET current_status = $1
                WHERE id = $2
                """,
                place_update.current_status,
                place_update.place_id
            )
            logger.info(f"Updated place {place_update.place_id}")

    # Update faction states
    for faction_update in state_updates.factions:
        if faction_update.faction_id and faction_update.current_activity:
            await conn.execute(
                """
                UPDATE factions
                SET current_activity = $1
                WHERE id = $2
                """,
                faction_update.current_activity,
                faction_update.faction_id
            )
            logger.info(f"Updated faction {faction_update.faction_id}")


async def clear_incubator(
    conn: asyncpg.Connection,
    session_id: str = None
) -> None:
    """
    Clear incubator after successful commit.
    If session_id is provided, only clear that session.
    Otherwise, clear all (for singleton incubator).
    """
    if session_id:
        await conn.execute(
            "DELETE FROM incubator WHERE session_id = $1",
            session_id
        )
        logger.info(f"Cleared incubator for session {session_id}")
    else:
        await conn.execute("DELETE FROM incubator")
        logger.info("Cleared all incubator data")


# ============================================================================
# Main Commit Function
# ============================================================================

async def commit_incubator_to_database(
    conn: asyncpg.Connection,
    session_id: str
) -> int:
    """
    Complete commit flow from incubator to production tables.

    Transaction steps:
    1. Read and validate incubator data
    2. Get parent chunk context (season/episode/scene)
    3. Resolve and create entities (characters, places, factions)
    4. Convert metadata (time, episode transitions)
    5. Insert narrative chunk
    6. Insert chunk metadata
    7. Insert junction table references
    8. Update entity states
    9. Clear incubator

    Returns:
        New chunk ID

    Raises:
        ValueError: If data is missing or invalid
        asyncpg.PostgresError: If database operation fails
    """
    summary_tasks: List[SummaryTask] = []
    chunk_id: Optional[int] = None

    async with conn.transaction():
        try:
            # Step 1: Get incubator data
            incubator = await fetch_incubator_data(conn, session_id)
            logger.info("Processing incubator session %s", session_id)

            # Step 2: Get parent context
            parent_meta = await fetch_chunk_metadata(conn, incubator["parent_chunk_id"])
            logger.info(
                "Parent chunk %s: S%sE%s scene %s",
                incubator["parent_chunk_id"],
                parent_meta["season"],
                parent_meta["episode"],
                parent_meta["scene"],
            )

            # Step 3: Resolve entity references
            # Parse referenced entities from JSONB
            ref_entities = ReferencedEntities(**incubator["reference_updates"])

            # Create new entities and resolve all to IDs
            character_refs = await resolve_character_references(ref_entities.characters, conn)
            place_refs = await resolve_place_references(ref_entities.places, conn)
            faction_refs = await resolve_faction_references(ref_entities.factions, conn)

            # Step 4: Convert metadata
            chronology_data = incubator["metadata_updates"].get("chronology", {})
            chronology = ChronologyUpdate(**chronology_data)
            db_meta = chronology_to_db_values(
                chronology,
                current_season=parent_meta["season"],
                current_episode=parent_meta["episode"]
            )
            summary_tasks = plan_summary_tasks(
                chronology.episode_transition,
                parent_meta["season"],
                parent_meta["episode"],
            )

            # Increment scene number
            db_meta["scene"] = parent_meta["scene"] + 1

            # Get world_layer
            world_layer = incubator["metadata_updates"].get("world_layer", "primary")

            # Step 5: Insert narrative chunk
            chunk_id = await insert_narrative_chunk(
                conn,
                raw_text=incubator["storyteller_text"],
                season=db_meta["season"],
                episode=db_meta["episode"]
            )
            if chunk_id is None:
                raise ValueError("Failed to obtain chunk_id after insert")

            # Step 6: Insert chunk metadata
            await insert_chunk_metadata(
                conn,
                chunk_id=chunk_id,
                season=db_meta["season"],
                episode=db_meta["episode"],
                scene=db_meta["scene"],
                world_layer=world_layer,
                time_delta=db_meta["time_delta"]
            )

            # Step 7: Insert junction table references
            await insert_place_references(conn, chunk_id, place_refs)
            await insert_character_references(conn, chunk_id, character_refs)
            await insert_faction_references(conn, chunk_id, faction_refs)

            # Step 8: Update entity states (if provided)
            if incubator.get("entity_updates"):
                state_updates = StateUpdates(**incubator["entity_updates"])
                await apply_state_updates(conn, state_updates)

            # Step 9: Clear incubator
            await clear_incubator(conn, session_id)

        except Exception as e:
            logger.error("Failed to commit incubator session %s: %s", session_id, e)
            raise

    if summary_tasks:
        try:
            schedule_summary_generation(summary_tasks)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to schedule summaries for session %s: %s", session_id, exc)

    logger.info("Successfully committed chunk %s from session %s", chunk_id, session_id)
    return chunk_id
