"""
Narrative generation functions for NEXUS.

This module handles async narrative generation including:
- Main generation orchestrator (generate_narrative_async)
- Chunk info retrieval (get_chunk_info)
- Incubator storage (write_to_incubator)
- Bootstrap narrative generation (generate_bootstrap_narrative)
"""

import json
import logging
import uuid
from typing import Dict, Any, Optional, Protocol

from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

from nexus.agents.lore.lore import LORE
from nexus.api.lore_adapter import (
    response_to_incubator,
    validate_incubator_data,
)

logger = logging.getLogger("nexus.api.narrative_generation")


class ProgressManager(Protocol):
    """Protocol for progress notification manager."""
    async def send_progress(self, session_id: str, status: str, data: Dict = None) -> None:
        """Send progress update for a specific session."""
        ...


async def generate_narrative_async(
    session_id: str,
    parent_chunk_id: int,
    user_text: str,
    slot: Optional[int] = None,
    *,
    get_db_connection,
    load_settings,
    manager: ProgressManager,
):
    """
    Async function to generate narrative.
    Sends progress updates via WebSocket.

    For bootstrap (parent_chunk_id=0), generates the first chunk using
    story seed and setting from global_variables.

    Note: TEST model routing is handled automatically by LogonUtility,
    which checks the slot's configured model and routes to the mock server.

    Args:
        session_id: Unique session identifier for tracking
        parent_chunk_id: ID of parent chunk (0 for bootstrap)
        user_text: User's input text
        slot: Save slot number (1-5)
        get_db_connection: Database connection factory function
        load_settings: Settings loader function
        manager: Progress notification manager
    """
    conn = None
    is_bootstrap = parent_chunk_id == 0

    try:
        # Connect to database
        conn = get_db_connection(slot)

        # Send progress: loading chunk
        await manager.send_progress(session_id, "loading_chunk")

        # Get parent chunk info (or bootstrap info)
        if is_bootstrap:
            # For bootstrap, use placeholder info - LORE will build context from global state
            chunk_info = {
                "season": 1,
                "episode": 1,
                "place_name": "Starting Location",
            }
            logger.info("Bootstrap mode: skipping parent chunk load, using global state")
        else:
            chunk_info = await get_chunk_info(conn, parent_chunk_id)

        # Send progress: building context
        await manager.send_progress(
            session_id,
            "building_context",
            {
                "parent_info": {
                    "season": chunk_info["season"],
                    "episode": chunk_info["episode"],
                    "place": chunk_info["place_name"],
                },
                "is_bootstrap": is_bootstrap,
            },
        )

        if is_bootstrap:
            # Bootstrap mode: Generate first chunk using story seed directly
            # Skip LORE entirely (requires warm slice and local LLM)
            logger.info("Bootstrap mode: calling apex AI directly with story seed context")

            # Send progress: calling LLM
            await manager.send_progress(session_id, "calling_llm")

            try:
                incubator_data = await generate_bootstrap_narrative(
                    conn, session_id, user_text, slot=slot, load_settings=load_settings
                )
                logger.info(f"Bootstrap narrative generated for session {session_id}")
            except Exception as e:
                logger.error(f"Bootstrap generation failed: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to generate bootstrap narrative: {str(e)}"
                )
        else:
            # Real LORE integration for continuation
            logger.info("Initializing LORE for narrative generation")

            # Initialize LORE with LOGON enabled for API calls
            lore = LORE(enable_logon=True, debug=True)

            # Send progress: calling LLM
            await manager.send_progress(session_id, "calling_llm")

            # Process the turn with LORE (builds context and generates narrative)
            try:
                response = await lore.process_turn(
                    user_text, parent_chunk_id=parent_chunk_id
                )
                logger.info(f"LORE response received for session {session_id}")
            except Exception as e:
                logger.error(f"LORE process_turn failed: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to generate narrative: {str(e)}"
                )

            # Send progress: processing response
            await manager.send_progress(session_id, "processing_response")

            # Transform LORE response to incubator format
            incubator_data = response_to_incubator(
                response=response,
                parent_chunk_id=parent_chunk_id,
                user_text=user_text,
                session_id=session_id,
            )

            # Validate the data before writing
            validate_incubator_data(incubator_data)

        # Write to incubator
        await write_to_incubator(conn, incubator_data)

        # Send progress: complete
        await manager.send_progress(
            session_id,
            "complete",
            {
                "chunk_id": parent_chunk_id + 1,
                "preview": incubator_data["storyteller_text"][:200] + "...",
            },
        )

        logger.info(f"Narrative generation complete for session {session_id}")

    except Exception as e:
        logger.error(f"Error generating narrative: {e}")
        await manager.send_progress(session_id, "error", {"error": str(e)})
    finally:
        if conn:
            conn.close()


async def get_chunk_info(conn, chunk_id: int) -> Dict[str, Any]:
    """Get information about a chunk."""
    query = """
    SELECT
        nv.id,
        nv.raw_text,
        nv.season,
        nv.episode,
        nv.world_time,
        cm.scene,
        cm.slug,
        cm.world_layer,
        cm.time_delta,
        NULL::text as place_name
    FROM narrative_view nv
    JOIN chunk_metadata cm ON cm.chunk_id = nv.id
    WHERE nv.id = %s
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (chunk_id,))
        result = cur.fetchone()

    if not result:
        raise ValueError(f"Chunk {chunk_id} not found")

    return dict(result)


async def write_to_incubator(conn, data: Dict[str, Any]):
    """Write data to the incubator table."""
    with conn.cursor() as cur:
        # Clear any existing incubator entry (singleton table)
        cur.execute("DELETE FROM incubator WHERE id = TRUE")

        # Insert new incubator entry
        query = """
        INSERT INTO incubator (
            id, chunk_id, parent_chunk_id, user_text, storyteller_text,
            choice_object, metadata_updates, entity_updates, reference_updates,
            session_id, llm_response_id, status
        ) VALUES (
            TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """

        cur.execute(
            query,
            (
                data["chunk_id"],
                data["parent_chunk_id"],
                data["user_text"],
                data["storyteller_text"],
                json.dumps(data.get("choice_object")) if data.get("choice_object") else None,
                json.dumps(data["metadata_updates"]),
                json.dumps(data["entity_updates"]),
                json.dumps(data["reference_updates"]),
                data["session_id"],
                data["llm_response_id"],
                data["status"],
            ),
        )

    conn.commit()


async def generate_bootstrap_narrative(
    conn, session_id: str, user_text: str, slot: Optional[int] = None, *, load_settings
) -> Dict[str, Any]:
    """
    Generate the opening narrative for a new story.

    Bypasses LORE entirely - loads context from global_variables and calls
    apex AI directly with a bootstrap-specific prompt.

    Args:
        conn: Database connection
        session_id: Session ID for tracking
        user_text: User's bootstrap request (e.g., "Begin the story.")
        slot: Save slot number (1-5) for database name resolution
        load_settings: Settings loader function

    Returns:
        Incubator data ready for storage
    """
    from nexus.agents.lore.logon_utility import LogonUtility
    from nexus.api.slot_utils import require_slot_dbname
    from psycopg2.extras import RealDictCursor

    # Load story context from global_variables
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT setting, user_character FROM global_variables WHERE id = true")
        row = cur.fetchone()
        if not row or not row["setting"]:
            raise ValueError("No setting found in global_variables - transition may not have completed")

        setting_data = row["setting"]
        character_id = row["user_character"]

        # Get character details
        cur.execute(
            "SELECT name, appearance, background FROM characters WHERE id = %s",
            (character_id,)
        )
        char_row = cur.fetchone()
        character_name = char_row["name"] if char_row else "Unknown"
        character_appearance = char_row.get("appearance", "") if char_row else ""
        character_background = char_row.get("background", "") if char_row else ""

        # Get starting location via FK chain:
        # global_variables.user_character → characters.current_location → places.id
        # Note: atmosphere and notable_features are in extra_data JSONB
        cur.execute(
            """SELECT p.name, p.summary,
                      p.extra_data->>'atmosphere' as atmosphere,
                      p.extra_data->'notable_features' as notable_features
               FROM global_variables g
               JOIN characters c ON c.id = g.user_character
               JOIN places p ON p.id = c.current_location
               WHERE g.id = true"""
        )
        place_row = cur.fetchone()
        location_name = place_row["name"] if place_row else "Unknown Location"
        location_summary = place_row.get("summary", "") if place_row else ""
        location_atmosphere = place_row.get("atmosphere", "") if place_row else ""

    # Extract story seed from setting
    story_seed = setting_data.get("story_seed", {})

    # Build bootstrap context payload for LOGON
    bootstrap_context = {
        "user_input": user_text,
        "is_bootstrap": True,
        "warm_slice": {
            "chunks": [],  # No prior chunks for bootstrap
            "token_count": 0
        },
        "bootstrap_data": {
            "setting": {
                "world_name": setting_data.get("world_name", "Unknown World"),
                "tone": setting_data.get("tone", ""),
                "genre": setting_data.get("genre", ""),
                "themes": setting_data.get("themes", []),
                "magic_exists": setting_data.get("magic_exists", False),
                "magic_description": setting_data.get("magic_description", ""),
            },
            "story_seed": {
                "title": story_seed.get("title", ""),
                "seed_type": story_seed.get("seed_type", ""),
                "situation": story_seed.get("situation", ""),
                "hook": story_seed.get("hook", ""),
                "immediate_goal": story_seed.get("immediate_goal", ""),
                "stakes": story_seed.get("stakes", ""),
                "tension_source": story_seed.get("tension_source", ""),
                "weather": story_seed.get("weather", ""),
                "initial_mystery": story_seed.get("initial_mystery", ""),
                "key_npcs": story_seed.get("key_npcs", []),
            },
            "protagonist": {
                "name": character_name,
                "appearance": character_appearance,
                "background": character_background,
            },
            "location": {
                "name": location_name,
                "summary": location_summary,
                "atmosphere": location_atmosphere,
            },
        },
        "entity_data": {},  # No entity data for bootstrap
        "retrieved_passages": {"results": [], "token_count": 0},
        "metadata": {
            "is_bootstrap": True,
            "session_id": session_id,
        },
        "memory_state": {},
    }

    # Initialize LOGON and generate narrative
    settings = load_settings()
    dbname = require_slot_dbname(slot=slot)
    logon = LogonUtility(settings, dbname=dbname)
    story_response = logon.generate_narrative(bootstrap_context)

    # Extract narrative text
    narrative_text = story_response.narrative if hasattr(story_response, 'narrative') else str(story_response)

    # Build incubator data
    incubator_data = {
        "chunk_id": 1,  # First chunk
        "parent_chunk_id": 0,  # No parent
        "user_text": user_text,
        "storyteller_text": narrative_text,
        "choice_object": None,  # Will be populated if response includes choices
        "choice_text": None,
        "metadata_updates": {
            "chronology": {
                "episode_transition": "new_episode",  # Valid: continue, new_episode, new_season
                "time_delta_minutes": 0,
                "time_delta_hours": None,
                "time_delta_days": None,
                "time_delta_description": "Story begins",
            },
            "world_layer": "primary",
        },
        "entity_updates": {},
        "reference_updates": {
            "characters": [{"character_id": character_id, "reference_type": "present"}] if character_id else [],
            "places": [],
            "factions": [],
        },
        "session_id": session_id,
        "llm_response_id": f"bootstrap_{uuid.uuid4().hex[:8]}",
        "status": "provisional",
    }

    # Extract choices if present
    # NOTE: Key must be "presented" to match schema used by select_choice() and lore_adapter
    if hasattr(story_response, 'choices') and story_response.choices:
        incubator_data["choice_object"] = {
            "presented": story_response.choices,
            "selected": None,
        }

    return incubator_data
