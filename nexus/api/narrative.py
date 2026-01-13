"""
FastAPI endpoints for live narrative turns with incubator support
"""

import asyncio
import frontmatter
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Literal
from pathlib import Path

from fastapi import (
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    BackgroundTasks,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.lore import LORE
from nexus.api.lore_adapter import (
    response_to_incubator,
    validate_incubator_data,
    format_choice_text,
    compute_raw_text,
)
from nexus.api.chunk_workflow import (
    ChunkWorkflow,
    ChunkAcceptRequest,
    ChunkRejectRequest,
    EditPreviousRequest,
    default_workflow,
)
from nexus.api.conversations import ConversationsClient
from nexus.api.new_story_flow import (
    start_setup,
    resume_setup,
    record_drafts,
    reset_setup,
    activate_slot,
)
from nexus.api.slot_utils import all_slots, slot_dbname, require_slot_dbname
from nexus.api.db_pool import get_connection

logger = logging.getLogger("nexus.api.narrative")

app = FastAPI(title="NEXUS Narrative API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.session_progress: Dict[str, Dict] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    async def send_progress(self, session_id: str, status: str, data: Dict = None):
        """Send progress update for a specific session"""
        progress = {
            "session_id": session_id,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "data": data or {},
        }
        self.session_progress[session_id] = progress
        await self.broadcast(json.dumps(progress))


manager = ConnectionManager()


# Database connection
def get_db_connection(slot: Optional[int] = None):
    """
    Get database connection for a save slot.

    Args:
        slot: Save slot number (1-5). If not provided, uses NEXUS_SLOT env var.

    Returns:
        psycopg2 connection to the slot database

    Raises:
        RuntimeError: If no slot specified and NEXUS_SLOT not set
        ValueError: If slot is not valid (1-5)
    """
    # Resolve database name - requires explicit slot or NEXUS_SLOT env var
    dbname = require_slot_dbname(slot=slot)

    # Respect environment variables for connection settings (like db_pool.py)
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432")
    )


def load_settings():
    """Load settings using centralized config loader."""
    from nexus.config import load_settings_as_dict
    return load_settings_as_dict()


def get_new_story_model() -> str:
    """Get the configured model for new story workflow."""
    settings = load_settings()
    return settings.get("API Settings", {}).get("new_story", {}).get("model", "gpt-5.1")


# Request/Response models
class ContinueNarrativeRequest(BaseModel):
    """Request to continue narrative from a chunk, or bootstrap a new story"""

    chunk_id: Optional[int] = Field(
        default=None,
        description="Parent chunk ID to continue from. None or 0 for bootstrap (first chunk)."
    )
    user_text: str = Field(description="User's completion text")
    test_mode: Optional[bool] = Field(
        default=None, description="Override test mode setting"
    )
    slot: Optional[int] = Field(default=None, description="Active save slot")


class ContinueNarrativeResponse(BaseModel):
    """Response from narrative continuation"""

    session_id: str = Field(description="Session ID for tracking this generation")
    status: str = Field(description="Status of the operation")
    message: str = Field(description="Status message")


class ApproveNarrativeRequest(BaseModel):
    """Request to approve and commit narrative"""

    # session_id is optional - resolved from incubator if not provided (requires slot)
    session_id: Optional[str] = Field(default=None, description="Session ID of the narrative to approve")
    slot: Optional[int] = Field(default=None, description="Slot to resolve session from")
    commit: bool = Field(default=True, description="Whether to commit to database")


class NarrativeStatus(BaseModel):
    """Status of a narrative generation session"""

    session_id: str
    status: str  # provisional, approved, committed, error
    chunk_id: Optional[int]
    parent_chunk_id: Optional[int]
    created_at: Optional[datetime]
    error: Optional[str]


class ChoiceSelection(BaseModel):
    """User's selection from presented choices"""

    label: int | Literal["freeform"] = Field(
        description="Choice number (1-4) or 'freeform' for custom input"
    )
    text: str = Field(description="The text of the selection (original or edited)")
    edited: bool = Field(
        default=False,
        description="True if user edited the choice before submitting"
    )


class SelectChoiceRequest(BaseModel):
    """Request to record user's choice selection for a chunk"""

    chunk_id: int = Field(description="The narrative chunk ID")
    selection: ChoiceSelection = Field(description="The user's choice selection")
    slot: Optional[int] = Field(default=None, description="Active save slot")


class SelectChoiceResponse(BaseModel):
    """Response after recording choice selection"""

    status: str = Field(description="Status of the operation")
    chunk_id: int = Field(description="The updated chunk ID")
    raw_text: str = Field(description="The finalized raw_text for embeddings")


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "narrative_api"}


@app.post("/api/narrative/continue", response_model=ContinueNarrativeResponse)
async def continue_narrative(
    request: ContinueNarrativeRequest, background_tasks: BackgroundTasks
):
    """
    Continue narrative from a given chunk, or bootstrap a new story.

    Bootstrap mode: When chunk_id is None or 0, generates the first chunk
    using the story seed and setting from global_variables.

    If chunk_id is not provided but slot is, resolves current chunk from slot state.

    Initiates async generation and returns session_id for tracking.
    """
    # Resolve chunk_id from slot state if not provided
    if request.chunk_id is None and request.slot is not None:
        from nexus.api.slot_state import get_slot_state

        state = get_slot_state(request.slot)
        if state.is_wizard_mode:
            raise HTTPException(
                status_code=400,
                detail="Slot is in wizard mode. Use /api/story/new/chat for wizard."
            )
        if state.narrative_state is not None:
            narrative_state = state.narrative_state
            if narrative_state.has_pending:
                if narrative_state.session_id is None:
                    raise HTTPException(
                        status_code=409,
                        detail="Slot has pending incubator content that must be approved before continuing."
                    )
                logger.info(
                    "Auto-approving pending incubator session %s for slot %s",
                    narrative_state.session_id,
                    request.slot,
                )
                approval = await approve_narrative(
                    session_id=narrative_state.session_id,
                    request=ApproveNarrativeRequest(
                        session_id=narrative_state.session_id, commit=True
                    ),
                    slot=request.slot,
                )
                approved_chunk_id = approval.get("chunk_id") if approval else None
                if not approved_chunk_id:
                    raise HTTPException(
                        status_code=409,
                        detail="Pending incubator content must be approved before continuing."
                    )
                request.chunk_id = approved_chunk_id
            else:
                request.chunk_id = narrative_state.current_chunk_id
            logger.info(f"Resolved chunk_id={request.chunk_id} from slot {request.slot}")

    session_id = str(uuid.uuid4())

    # Normalize chunk_id: None and 0 both mean bootstrap
    parent_chunk_id = request.chunk_id if request.chunk_id else 0
    is_bootstrap = parent_chunk_id == 0

    if is_bootstrap:
        logger.info("Starting narrative bootstrap (first chunk)")
    else:
        logger.info(f"Starting narrative continuation for chunk {parent_chunk_id}")
    logger.info(f"Session ID: {session_id}")
    logger.info(f"User text: {request.user_text[:100]}...")

    # Send initial progress
    await manager.send_progress(
        session_id,
        "initiated",
        {"chunk_id": parent_chunk_id, "parent_chunk_id": parent_chunk_id, "is_bootstrap": is_bootstrap},
    )

    # Start async generation in background
    background_tasks.add_task(
        generate_narrative_async,
        session_id,
        parent_chunk_id,
        request.user_text,
        request.test_mode,
        request.slot,
    )

    message = "Narrative bootstrap started" if is_bootstrap else f"Narrative generation started for chunk {parent_chunk_id}"
    return ContinueNarrativeResponse(
        session_id=session_id,
        status="processing",
        message=message,
    )


async def generate_narrative_async(
    session_id: str,
    parent_chunk_id: int,
    user_text: str,
    test_mode: Optional[bool] = None,
    slot: Optional[int] = None,
):
    """
    Async function to generate narrative.
    Sends progress updates via WebSocket.

    For bootstrap (parent_chunk_id=0), generates the first chunk using
    story seed and setting from global_variables.
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

        # Check if we should use mock mode (for testing without LLM)
        use_mock = test_mode is True  # Explicit True means use mock

        if use_mock and is_bootstrap:
            # Mock bootstrap mode for TEST model
            logger.info("Using mock mode for bootstrap narrative generation")
            await asyncio.sleep(1)  # Simulate processing

            # Send progress: calling LLM
            await manager.send_progress(session_id, "calling_llm")
            await asyncio.sleep(2)  # Simulate LLM call

            # Generate mock bootstrap narrative using cached story seed
            storyteller_text = generate_mock_bootstrap_narrative(conn, slot)

            # Prepare mock incubator data for bootstrap
            incubator_data = {
                "chunk_id": 1,  # First chunk
                "parent_chunk_id": 0,
                "user_text": user_text,
                "storyteller_text": storyteller_text,
                "choice_object": {
                    "presented": [
                        "Examine the satchel more closely",
                        "Check the tram's route display",
                        "Study the other passengers",
                    ],
                    "selected": None,
                },
                "metadata_updates": {
                    "chronology": {
                        "episode_transition": "begin",
                        "time_delta_minutes": 0,
                        "time_delta_hours": None,
                        "time_delta_days": None,
                        "time_delta_description": "Story begins",
                    },
                    "world_layer": "primary",
                },
                "entity_updates": {},
                "reference_updates": {
                    "characters": [{"character_id": 1, "reference_type": "present"}],
                    "places": [{"place_id": 1, "reference_type": "setting", "evidence": None}],
                    "factions": [],
                },
                "session_id": session_id,
                "llm_response_id": f"mock_bootstrap_{uuid.uuid4().hex[:8]}",
                "status": "provisional",
            }

        elif use_mock:
            # Mock mode for testing continuation without real LLM calls
            logger.info("Using mock mode for narrative continuation")
            await asyncio.sleep(2)  # Simulate processing

            # Send progress: calling LLM
            await manager.send_progress(session_id, "calling_llm")
            await asyncio.sleep(3)  # Simulate LLM call

            storyteller_text = generate_mock_narrative(chunk_info, user_text)

            # Prepare mock incubator data
            incubator_data = {
                "chunk_id": parent_chunk_id + 1,
                "parent_chunk_id": parent_chunk_id,
                "user_text": user_text,
                "storyteller_text": storyteller_text,
                "metadata_updates": {
                    "chronology": {
                        "episode_transition": "continue",
                        "time_delta_minutes": 3,
                        "time_delta_hours": None,
                        "time_delta_days": None,
                        "time_delta_description": "A few minutes later",
                    },
                    "world_layer": "primary",
                },
                "entity_updates": {},
                "reference_updates": {
                    "characters": [{"character_id": 1, "reference_type": "present"}],
                    "places": [
                        {
                            "place_id": chunk_info.get("place", 1),
                            "reference_type": "setting",
                            "evidence": None,
                        }
                    ],
                    "factions": [],
                },
                "session_id": session_id,
                "llm_response_id": f"mock_{uuid.uuid4().hex[:8]}",
                "status": "provisional",
            }

        elif is_bootstrap:
            # Bootstrap mode: Generate first chunk using story seed directly
            # Skip LORE entirely (requires warm slice and local LLM)
            logger.info("Bootstrap mode: calling apex AI directly with story seed context")

            # Send progress: calling LLM
            await manager.send_progress(session_id, "calling_llm")

            try:
                incubator_data = await generate_bootstrap_narrative(
                    conn, session_id, user_text, slot=slot
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
    """Get information about a chunk"""
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
    """Write data to the incubator table"""
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


def generate_mock_narrative(chunk_info: Dict, user_text: str) -> str:
    """Generate mock narrative for testing"""
    return f"""The scene continues from {chunk_info['place_name']}.

{user_text}

The morning stretches on, and with it comes a growing sense of purpose. The team's focus sharpens
as they review the data streams flowing across their screens. Each piece of information adds another
layer to the complex puzzle they're trying to solve.

Sullivan, now officially part of the crew, watches from his perch with an air of feline wisdom,
as if he too understands the gravity of what's about to unfold."""


def generate_mock_bootstrap_narrative(conn, slot: Optional[int] = None) -> str:
    """
    Generate mock bootstrap narrative for TEST mode.

    Uses data from the wizard test cache or generates generic opening.
    """
    try:
        # Try to load from wizard test cache
        from nexus.api.wizard_test_cache import load_cache
        import json

        cache = load_cache()
        seed_data = cache.get("selected_seed", {})
        if isinstance(seed_data, str):
            seed_data = json.loads(seed_data)

        location_data = cache.get("initial_location", {})
        if isinstance(location_data, str):
            location_data = json.loads(location_data)

        character_data = cache.get("character_draft", {})
        if isinstance(character_data, str):
            character_data = json.loads(character_data)

        # Extract key elements
        situation = seed_data.get("situation", "The story begins.")
        atmosphere = location_data.get("atmosphere", "The air is thick with tension.")
        char_name = character_data.get("concept", {}).get("name", "the protagonist")

        return f"""[TEST MODE - Mock Bootstrap Narrative]

{situation}

{atmosphere}

{char_name} takes a moment to assess the situation, mind racing through possibilities. The weight of unknown history presses down, fragments of memories that might be real or might be implanted flickering at the edges of consciousness.

What happens next is up to you.

---
*This is a mock narrative generated for TEST mode. In production, this would be a rich, immersive opening scene generated by the AI storyteller.*"""

    except Exception as e:
        logger.warning(f"Failed to load wizard test cache for mock bootstrap: {e}")
        return """[TEST MODE - Mock Bootstrap Narrative]

The story begins in a moment of uncertainty. The protagonist finds themselves at a crossroads, the weight of decisions yet to be made hanging in the air.

Around them, the world waits. Every shadow could hide a threat or an opportunity. Every face could belong to friend or foe.

What happens next is up to you.

---
*This is a mock narrative generated for TEST mode. In production, this would be a rich, immersive opening scene generated by the AI storyteller.*"""


async def generate_bootstrap_narrative(
    conn, session_id: str, user_text: str, slot: Optional[int] = None
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
                "episode_transition": "begin",
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


@app.get("/api/narrative/status/{session_id}", response_model=NarrativeStatus)
async def get_narrative_status(session_id: str, slot: Optional[int] = None):
    """Get status of a narrative generation session"""

    # Check WebSocket manager for active sessions
    if session_id in manager.session_progress:
        progress = manager.session_progress[session_id]
        return NarrativeStatus(
            session_id=session_id,
            status=progress["status"],
            chunk_id=progress.get("data", {}).get("chunk_id"),
            parent_chunk_id=progress.get("data", {}).get("parent_chunk_id"),
            created_at=datetime.fromisoformat(progress["timestamp"]),
            error=progress.get("data", {}).get("error"),
        )

    # Check incubator for completed sessions
    conn = get_db_connection(slot)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM incubator WHERE session_id = %s", (session_id,))
            result = cur.fetchone()

        if result:
            return NarrativeStatus(
                session_id=session_id,
                status=result["status"],
                chunk_id=result["chunk_id"],
                parent_chunk_id=result["parent_chunk_id"],
                created_at=result["created_at"],
                error=None,
            )

        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    finally:
        conn.close()


@app.post("/api/narrative/approve")
async def approve_narrative_unified(request: ApproveNarrativeRequest):
    """
    Approve narrative and optionally commit to database.

    If session_id is not provided, resolves from the most recent incubator entry for the slot.
    """
    session_id = request.session_id
    slot = request.slot

    # Resolve session_id from incubator if not provided
    if session_id is None:
        if slot is None:
            raise HTTPException(
                status_code=400,
                detail="Either session_id or slot must be provided"
            )
        from nexus.api.slot_utils import slot_dbname

        dbname = slot_dbname(slot)
        with get_connection(dbname, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT session_id FROM incubator ORDER BY created_at DESC LIMIT 1"
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(
                        status_code=404,
                        detail="No pending session to approve in incubator"
                    )
                session_id = row["session_id"]
                logger.info(f"Resolved session_id={session_id} from slot {slot} incubator")

    # Now call the implementation
    return await _approve_narrative_impl(session_id, request.commit, slot)


@app.post("/api/narrative/approve/{session_id}")
async def approve_narrative(session_id: str, request: Optional[ApproveNarrativeRequest] = None, slot: Optional[int] = None):
    """
    Approve narrative and optionally commit to database (path-based for backward compatibility).
    """
    should_commit = request.commit if request else True
    effective_slot = request.slot if request and request.slot else slot
    return await _approve_narrative_impl(session_id, should_commit, effective_slot)


async def _approve_narrative_impl(session_id: str, commit: bool, slot: Optional[int]):
    """Internal implementation for approve narrative."""
    conn = get_db_connection(slot)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get incubator data
            cur.execute("SELECT * FROM incubator WHERE session_id = %s", (session_id,))
            incubator_data = cur.fetchone()

        if not incubator_data:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )

        if commit:
            # Import synchronous commit function
            from nexus.api.commit_handler_sync import commit_incubator_to_database_sync

            try:
                # Commit to database
                chunk_id = commit_incubator_to_database_sync(conn, session_id, slot)

                return {
                    "status": "committed",
                    "message": f"Narrative committed as chunk {chunk_id}",
                    "chunk_id": chunk_id,
                }
            except Exception as e:
                logger.error(f"Failed to commit narrative: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to commit narrative: {str(e)}"
                )
        else:
            # Just mark as reviewed
            return {
                "status": "reviewed",
                "message": "Narrative reviewed but not committed",
                "chunk_id": incubator_data["chunk_id"],
            }

    finally:
        conn.close()


@app.post("/api/narrative/select-choice", response_model=SelectChoiceResponse)
async def select_choice(request: SelectChoiceRequest):
    """
    Record user's choice selection and finalize the chunk's raw_text.

    This is Phase 2 of the two-phase storage flow:
    1. Storyteller generates narrative with choices → stored with choice_object
    2. User selects a choice → this endpoint updates choice_object.selected,
       generates choice_text, and computes final raw_text for embeddings

    Supports both committed chunks (narrative_chunks) and incubator chunks.
    """
    conn = get_db_connection(request.slot)
    is_incubator = False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # First try narrative_chunks
            cur.execute("""
                SELECT id, storyteller_text, choice_object
                FROM narrative_chunks
                WHERE id = %s
            """, (request.chunk_id,))
            chunk = cur.fetchone()

            # Fall back to incubator if not found in narrative_chunks
            if not chunk:
                cur.execute("""
                    SELECT chunk_id as id, storyteller_text, choice_object
                    FROM incubator
                    WHERE chunk_id = %s
                """, (request.chunk_id,))
                chunk = cur.fetchone()
                is_incubator = True

            if not chunk:
                raise HTTPException(
                    status_code=404,
                    detail=f"Chunk {request.chunk_id} not found"
                )

            # Validate choice_object exists
            choice_object = chunk.get("choice_object")
            if not choice_object:
                raise HTTPException(
                    status_code=400,
                    detail=f"Chunk {request.chunk_id} has no choices to select from"
                )

            # P1: Check if choice already selected (prevent race condition)
            if choice_object.get("selected"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Choice already selected for chunk {request.chunk_id}. Cannot re-select."
                )

            # P0: Validate selection label is valid
            presented = choice_object.get("presented", [])
            if request.selection.label != "freeform":
                if not isinstance(request.selection.label, int):
                    raise HTTPException(status_code=400, detail="Invalid label type")
                if not (1 <= request.selection.label <= len(presented)):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid choice label: {request.selection.label}. Must be 1-{len(presented)} or 'freeform'"
                    )

            # P0: Validate text length (prevent abuse)
            MAX_CHOICE_TEXT_LENGTH = 1000
            if len(request.selection.text) > MAX_CHOICE_TEXT_LENGTH:
                raise HTTPException(
                    status_code=400,
                    detail=f"Selection text too long ({len(request.selection.text)} chars). Max: {MAX_CHOICE_TEXT_LENGTH}"
                )

            # Update choice_object with selection
            choice_object["selected"] = {
                "label": request.selection.label,
                "text": request.selection.text,
                "edited": request.selection.edited,
            }

            # Generate choice_text markdown
            choice_text = format_choice_text(choice_object, include_selection=True)

            # Compute final raw_text for embeddings
            storyteller_text = chunk.get("storyteller_text") or ""
            raw_text = compute_raw_text(storyteller_text, choice_object)

            # Update the chunk in the appropriate table
            if is_incubator:
                # For incubator, only update choice_object (raw_text computed at commit)
                cur.execute("""
                    UPDATE incubator
                    SET choice_object = %s
                    WHERE chunk_id = %s
                """, (
                    json.dumps(choice_object),
                    request.chunk_id
                ))
                logger.info(f"Recorded choice selection for incubator chunk {request.chunk_id}")
            else:
                # For committed chunks, update all fields
                cur.execute("""
                    UPDATE narrative_chunks
                    SET choice_object = %s,
                        choice_text = %s,
                        raw_text = %s
                    WHERE id = %s
                """, (
                    json.dumps(choice_object),
                    choice_text,
                    raw_text,
                    request.chunk_id
                ))
                logger.info(f"Finalized choice selection for chunk {request.chunk_id}")

        conn.commit()

        return SelectChoiceResponse(
            status="pending" if is_incubator else "finalized",
            chunk_id=request.chunk_id,
            raw_text=raw_text
        )

    except HTTPException:
        conn.rollback()  # P2: Explicit rollback on validation errors
        raise
    except Exception as e:
        conn.rollback()  # P2: Explicit rollback on unexpected errors
        logger.error(f"Error selecting choice: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.websocket("/ws/narrative")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time progress updates"""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, wait for messages
            data = await websocket.receive_text()
            # Could handle client messages here if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Utility endpoints
@app.get("/api/narrative/incubator")
async def get_incubator_contents(slot: Optional[int] = None):
    """Get current incubator contents"""
    conn = get_db_connection(slot)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM incubator_view")
            result = cur.fetchone()

        if result:
            return dict(result)
        else:
            return {"message": "Incubator is empty"}
    finally:
        conn.close()


@app.delete("/api/narrative/incubator")
async def clear_incubator(slot: Optional[int] = None):
    """Clear the incubator table"""
    conn = get_db_connection(slot)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM incubator WHERE id = TRUE")
        conn.commit()
        return {"message": "Incubator cleared"}
    finally:
        conn.close()


# New Story Request Models
class StartSetupRequest(BaseModel):
    slot: int
    model: Optional[str] = None


class RecordDraftRequest(BaseModel):
    slot: int
    setting: Optional[Dict] = None
    character: Optional[Dict] = None
    seed: Optional[Dict] = None
    location: Optional[Dict] = None
    base_timestamp: Optional[str] = None


class ResetSetupRequest(BaseModel):
    slot: int


class SelectSlotRequest(BaseModel):
    slot: int


# Chunk Workflow Endpoints
@app.post("/api/chunks/accept")
async def accept_chunk_endpoint(request: ChunkAcceptRequest):
    """Accept a chunk and trigger embedding generation"""
    try:
        # Assuming ChunkAcceptRequest needs to be updated or we pass slot via query param?
        # The request model is imported. We might need to update it or check if it has slot.
        # For now, let's assume we can pass slot if it's in the request, or we need to add it.
        # Let's check ChunkAcceptRequest definition in chunk_workflow.py.
        # If not present, we can't pass it easily without updating the model.
        # But wait, default_workflow.accept_chunk might need slot.
        # Let's assume for now we pass it if available.
        # Actually, let's just pass it if the method accepts it.
        # I'll check chunk_workflow.py later. For now, I'll leave this as is or update if I know the signature.
        # Wait, I need to update the signature here to accept slot query param if the request body doesn't have it.
        # But accept_chunk_endpoint takes a body.
        return default_workflow.accept_chunk(request.chunk_id, request.session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error accepting chunk: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chunks/reject")
async def reject_chunk_endpoint(request: ChunkRejectRequest):
    """Reject a chunk and either regenerate or edit previous"""
    try:
        return default_workflow.reject_chunk(
            request.chunk_id, request.session_id, request.action
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error rejecting chunk: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chunks/{chunk_id}/edit-user-input")
async def edit_chunk_input_endpoint(chunk_id: int, request: EditPreviousRequest):
    """Edit previous user input"""
    if chunk_id != request.chunk_id:
        raise HTTPException(status_code=400, detail="Chunk ID mismatch")
    try:
        return default_workflow.edit_previous_input(
            request.chunk_id, request.new_user_input, request.session_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error editing chunk input: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chunks/states")
async def get_chunk_states_endpoint(start: int, end: int, slot: Optional[int] = None):
    """Get states for a range of chunks"""
    try:
        return default_workflow.get_chunk_states(start, end, slot)
    except Exception as e:
        logger.error(f"Error fetching chunk states: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# New Story Wizard Endpoints
@app.post("/api/story/new/setup/start")
async def start_setup_endpoint(request: StartSetupRequest) -> Dict[str, Any]:
    """Start a new setup conversation"""
    try:
        thread_id = start_setup(request.slot, request.model)

        # Load welcome message and choices from frontmatter
        prompt_path = (
            Path(__file__).parent.parent.parent / "prompts" / "storyteller_new.md"
        )
        welcome_message = ""
        welcome_choices: List[str] = []
        if prompt_path.exists():
            with prompt_path.open() as f:
                doc = frontmatter.load(f)
                welcome_message = doc.get("welcome_message", "")
                welcome_choices = doc.get("welcome_choices", [])

        # Seed welcome message if exists (without choices - UI renders those)
        if welcome_message:
            # Use request model (enables TEST mode) or fall back to settings
            model_to_use = request.model or get_new_story_model()
            client = ConversationsClient(model=model_to_use)
            client.add_message(thread_id, "assistant", welcome_message)

        return {
            "status": "started",
            "thread_id": thread_id,
            "slot": request.slot,
            "welcome_message": welcome_message,
            "welcome_choices": welcome_choices,
        }
    except Exception as e:
        logger.error(f"Error starting setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/story/new/setup/resume")
async def resume_setup_endpoint(slot: int):
    """Resume setup for a slot"""
    try:
        data = resume_setup(slot)
        if not data:
            raise HTTPException(
                status_code=404, detail=f"No active setup found for slot {slot}"
            )
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/story/new/setup/record")
async def record_drafts_endpoint(request: RecordDraftRequest):
    """Record draft data for a slot"""
    try:
        record_drafts(
            request.slot,
            setting=request.setting,
            character=request.character,
            seed=request.seed,
            location=request.location,
            base_timestamp=request.base_timestamp,
        )
        return {"status": "recorded", "slot": request.slot}
    except Exception as e:
        logger.error(f"Error recording drafts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/story/new/setup/reset")
async def reset_setup_endpoint(request: ResetSetupRequest):
    """Reset setup for a slot"""
    try:
        reset_setup(request.slot)
        return {"status": "reset", "slot": request.slot}
    except Exception as e:
        logger.error(f"Error resetting setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/story/new/slot/select")
async def select_slot_endpoint(request: SelectSlotRequest):
    """Activate a slot"""
    try:
        results = activate_slot(request.slot)
        return {"status": "activated", "results": results}
    except Exception as e:
        logger.error(f"Error activating slot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/story/new/slots")
async def get_slots_status_endpoint():
    """Get status of all save slots with wizard state"""
    from nexus.api.slot_utils import all_slots, slot_dbname
    from nexus.api.save_slots import list_slots
    from nexus.api.new_story_cache import read_cache

    results = []
    for slot in all_slots():
        dbname = slot_dbname(slot)
        try:
            # Try to list slots from this DB
            slots_data = list_slots(dbname=dbname)
            # Find the row for this slot
            slot_data = next((s for s in slots_data if s["slot_number"] == slot), None)

            if slot_data:
                # Check if wizard is in progress
                cache = read_cache(dbname)
                if cache:
                    slot_data["wizard_in_progress"] = True
                    slot_data["wizard_thread_id"] = cache.thread_id
                    slot_data["wizard_phase"] = cache.current_phase()
                else:
                    slot_data["wizard_in_progress"] = False
                results.append(slot_data)
            else:
                results.append({"slot_number": slot, "is_active": False, "wizard_in_progress": False})
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            # Expected: DB doesn't exist or connection failed
            logger.warning(f"Could not connect to slot {slot} database: {e}")
            results.append({"slot_number": slot, "is_active": False, "wizard_in_progress": False})
        except Exception as e:
            # Unexpected errors should surface during development
            logger.error(f"Unexpected error fetching slot {slot}: {e}")
            raise

    return results


# ============================================================================
# Simplified Slot State Endpoints (for CLI)
# ============================================================================


class SlotStateResponse(BaseModel):
    """Response model for slot state endpoint."""

    slot: int
    is_empty: bool
    is_wizard_mode: bool
    phase: Optional[str] = None  # Wizard phase if in wizard mode
    thread_id: Optional[str] = None  # Wizard thread ID
    current_chunk_id: Optional[int] = None  # Narrative chunk ID
    has_pending: bool = False  # True if incubator has pending content
    storyteller_text: Optional[str] = None
    choices: List[str] = []
    model: Optional[str] = None


@app.get("/api/slot/{slot}/state", response_model=SlotStateResponse)
async def get_slot_state_endpoint(slot: int):
    """
    Get complete state for a save slot.

    Returns everything needed to display current position and available actions:
    - Whether in wizard or narrative mode
    - Current wizard phase or narrative chunk
    - Available choices
    - Current model setting
    """
    from nexus.api.slot_state import get_slot_state

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        state = get_slot_state(slot)

        if state.is_empty:
            return SlotStateResponse(
                slot=slot,
                is_empty=True,
                is_wizard_mode=False,
                model=state.model,
            )

        if state.is_wizard_mode and state.wizard_state:
            return SlotStateResponse(
                slot=slot,
                is_empty=False,
                is_wizard_mode=True,
                phase=state.wizard_state.phase,
                thread_id=state.wizard_state.thread_id,
                model=state.model,
            )

        if state.narrative_state:
            return SlotStateResponse(
                slot=slot,
                is_empty=False,
                is_wizard_mode=False,
                current_chunk_id=state.narrative_state.current_chunk_id,
                has_pending=state.narrative_state.has_pending,
                storyteller_text=state.narrative_state.storyteller_text,
                choices=state.narrative_state.choices,
                model=state.model,
            )

        # Fallback for edge cases
        return SlotStateResponse(
            slot=slot,
            is_empty=True,
            is_wizard_mode=False,
        )

    except Exception as e:
        logger.error(f"Error getting slot state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SlotContinueRequest(BaseModel):
    """Request model for unified continue endpoint."""

    choice: Optional[int] = Field(
        default=None, description="Structured choice number (1-indexed)"
    )
    user_text: Optional[str] = Field(
        default=None, description="Freeform user input"
    )
    accept_fate: bool = Field(
        default=False, description="Auto-advance (select first choice or trigger auto-generate)"
    )
    model: Optional[str] = Field(
        default=None, description="Override model for this request"
    )


class SlotContinueResponse(BaseModel):
    """Response from unified continue endpoint."""

    success: bool
    action: str  # "wizard_chat", "narrative_continue", "initialize"
    session_id: Optional[str] = None
    message: Optional[str] = None  # Assistant response or status
    choices: List[str] = []  # Available choices for next turn
    phase: Optional[str] = None  # Wizard phase if applicable
    chunk_id: Optional[int] = None  # Narrative chunk ID if applicable
    error: Optional[str] = None


@app.post("/api/slot/{slot}/continue", response_model=SlotContinueResponse, deprecated=True)
async def slot_continue_endpoint(slot: int, request: SlotContinueRequest):
    """
    Unified continue endpoint for wizard or narrative mode.

    DEPRECATED: Use /api/story/new/chat (wizard) or /api/narrative/continue (narrative) directly.
    These endpoints now accept slot-only parameters and resolve state internally.

    Routes to wizard chat or narrative continuation based on current slot state.
    Handles choice selection, freeform input, and accept-fate auto-advance.

    The slot's current state determines the action:
    - Empty slot: Initialize wizard
    - Wizard mode: Route to wizard chat
    - Narrative mode: Generate next chunk

    If a previous incubator session exists, submitting a continue request
    implicitly approves that pending content.
    """
    from nexus.api.slot_state import resolve_continue_action, get_slot_state

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        # Resolve what action to take
        resolution = resolve_continue_action(
            slot=slot,
            choice=request.choice,
            user_text=request.user_text,
            accept_fate=request.accept_fate,
        )

        action = resolution["action"]
        params = resolution["params"]

        # Override model if specified in request
        if request.model:
            params["model"] = request.model

        if action == "initialize":
            # Initialize new wizard session for empty slot
            from nexus.api.new_story_flow import start_setup

            # start_setup returns thread_id string, not a dict
            thread_id = start_setup(params["slot"])
            return SlotContinueResponse(
                success=True,
                action="initialize",
                message=f"Wizard initialized for slot {slot}. Ready to begin story creation.",
                phase="setting",
            )

        elif action == "wizard_chat":
            # Route to wizard chat flow
            # Load character state from cache for character phase sub-tracking
            context_data = None
            current_phase = params.get("phase") or "setting"
            if current_phase == "character":
                from nexus.api.new_story_cache import read_cache
                from nexus.api.slot_utils import slot_dbname

                cache = read_cache(slot_dbname(slot))
                if cache:
                    # Build character_state from normalized columns
                    char_state = {}
                    if cache.character.has_concept():
                        # Build concept dict with suggestions from ephemeral table
                        concept_dict = {
                            "name": cache.character.name,
                            "archetype": cache.character.archetype,
                            "background": cache.character.background,
                            "appearance": cache.character.appearance,
                        }
                        # Add suggestions if available (from suggested_traits table)
                        if cache.character.suggested_traits:
                            concept_dict["suggested_traits"] = [
                                s.trait for s in cache.character.suggested_traits
                            ]
                            concept_dict["trait_rationales"] = {
                                s.trait: s.rationale for s in cache.character.suggested_traits
                            }
                        char_state["concept"] = concept_dict
                    if cache.character.has_traits():
                        char_state["trait_selection"] = {
                            "selected_traits": [
                                cache.character.trait1,
                                cache.character.trait2,
                                cache.character.trait3,
                            ]
                        }
                    if cache.character.has_wildcard():
                        char_state["wildcard"] = {
                            "wildcard_name": cache.character.wildcard_name,
                            "wildcard_description": cache.character.wildcard_description,
                        }
                    if char_state:
                        context_data = {"character_state": char_state}

            chat_request = ChatRequest(
                slot=params["slot"],
                thread_id=params.get("thread_id") or "",
                message=params.get("message") or "",
                model=params.get("model") or "gpt-5.1",
                current_phase=current_phase,
                context_data=context_data,
                accept_fate=params.get("accept_fate", False),
            )

            # Handle empty thread_id - need to start a new session
            if not chat_request.thread_id:
                from nexus.api.new_story_flow import start_setup

                # start_setup returns thread_id string, not a dict
                thread_id = start_setup(slot)
                return SlotContinueResponse(
                    success=True,
                    action="wizard_chat",
                    message=f"Wizard session started. Thread ID: {thread_id}",
                    phase="setting",
                )

            # Call the existing chat endpoint logic
            response = await new_story_chat_endpoint(chat_request)

            return SlotContinueResponse(
                success=True,
                action="wizard_chat",
                message=response.get("message"),
                choices=response.get("choices", []),
                phase=response.get("phase"),
            )

        elif action == "narrative_continue":
            # Implicitly approve pending incubator if exists
            pending_session = params.get("session_id")
            if pending_session:
                try:
                    await approve_narrative(
                        session_id=pending_session,
                        request=ApproveNarrativeRequest(
                            session_id=pending_session, commit=True
                        ),
                        slot=slot,
                    )
                except Exception as e:
                    logger.warning(f"Failed to approve pending session: {e}")

            # Generate next narrative chunk
            session_id = str(uuid.uuid4())
            # Note: model override not implemented for narrative continuation
            # ContinueNarrativeRequest only has: chunk_id, user_text, test_mode, slot
            continue_request = ContinueNarrativeRequest(
                chunk_id=params.get("chunk_id"),
                user_text=params.get("user_text") or "",
                slot=slot,
            )

            await generate_narrative_async(
                session_id=session_id,
                parent_chunk_id=continue_request.chunk_id or 0,
                user_text=continue_request.user_text,
                slot=slot,
            )

            # Get the result
            status = await get_narrative_status(session_id, slot=slot)

            # Fetch incubator data for choices
            from nexus.api.slot_utils import slot_dbname

            dbname = slot_dbname(slot)
            with get_connection(dbname, dict_cursor=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT storyteller_text, choice_object FROM incubator WHERE session_id = %s",
                        (session_id,),
                    )
                    incubator_row = cur.fetchone()

            storyteller_text = None
            choices = []
            if incubator_row:
                storyteller_text = incubator_row.get("storyteller_text")
                choice_obj = incubator_row.get("choice_object")
                if choice_obj:
                    if isinstance(choice_obj, str):
                        import json

                        choice_obj = json.loads(choice_obj)
                    choices = choice_obj.get("presented", [])

            return SlotContinueResponse(
                success=status.status == "completed",
                action="narrative_continue",
                session_id=session_id,
                message=storyteller_text,
                choices=choices,
                chunk_id=status.chunk_id,
                error=status.error,
            )

        else:
            raise HTTPException(status_code=500, detail=f"Unknown action: {action}")

    except ValueError as e:
        return SlotContinueResponse(
            success=False,
            action="error",
            error=str(e),
        )
    except Exception as e:
        logger.error(f"Error in slot continue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SlotUndoResponse(BaseModel):
    """Response from undo endpoint."""

    success: bool
    message: str
    previous_state: Optional[str] = None  # "setting", "character", "seed", or chunk ID


@app.post("/api/slot/{slot}/undo", response_model=SlotUndoResponse)
async def slot_undo_endpoint(slot: int):
    """
    Undo the last action for a slot.

    Behavior depends on current mode:
    - Wizard mode: Clears the most recent draft, reverting to previous phase
    - Narrative mode (pending): Deletes incubator content without committing
    - Narrative mode (committed): Cannot undo committed chunks

    Single-depth undo only - no multi-step rewind.
    """
    from nexus.api.slot_state import get_slot_state
    from nexus.api.new_story_cache import clear_seed_phase, clear_character_phase, clear_setting_phase

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        state = get_slot_state(slot)
        dbname = slot_dbname(slot)

        if state.is_empty:
            return SlotUndoResponse(
                success=False,
                message="Slot is empty - nothing to undo",
            )

        if state.is_wizard_mode and state.wizard_state:
            wizard = state.wizard_state

            # Determine what to clear based on current phase
            if wizard.phase == "ready":
                # Clear seed columns to go back to seed phase
                clear_seed_phase(dbname)
                return SlotUndoResponse(
                    success=True,
                    message="Reverted to seed phase",
                    previous_state="seed",
                )

            elif wizard.phase == "seed":
                # Clear character columns to go back to character phase
                clear_character_phase(dbname)
                return SlotUndoResponse(
                    success=True,
                    message="Reverted to character phase",
                    previous_state="character",
                )

            elif wizard.phase == "character":
                # Clear setting columns to go back to setting phase
                clear_setting_phase(dbname)
                return SlotUndoResponse(
                    success=True,
                    message="Reverted to setting phase",
                    previous_state="setting",
                )

            else:
                # Already at setting phase - nothing to undo
                return SlotUndoResponse(
                    success=False,
                    message="Already at beginning of wizard - nothing to undo",
                )

        elif state.narrative_state:
            narrative = state.narrative_state

            if narrative.has_pending and narrative.session_id:
                # Delete pending incubator content
                with get_connection(dbname) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM incubator WHERE session_id = %s",
                            (narrative.session_id,),
                        )

                return SlotUndoResponse(
                    success=True,
                    message="Deleted pending content",
                    previous_state=str(narrative.current_chunk_id),
                )

            else:
                # No pending content - cannot undo committed chunks
                return SlotUndoResponse(
                    success=False,
                    message="Cannot undo committed chunks - only pending content can be undone",
                )

        return SlotUndoResponse(
            success=False,
            message="Unknown state - cannot undo",
        )

    except Exception as e:
        logger.error(f"Error in slot undo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SlotModelRequest(BaseModel):
    """Request model for setting slot model."""

    model: str = Field(description="Model to set (e.g., gpt-5.1, TEST, claude)")


class SlotModelResponse(BaseModel):
    """Response from model endpoints."""

    slot: int
    model: Optional[str]
    available_models: List[str] = []


@app.get("/api/slot/{slot}/model", response_model=SlotModelResponse)
async def get_slot_model_endpoint(slot: int):
    """Get current model for a slot."""
    from nexus.config import load_settings_as_dict

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        dbname = slot_dbname(slot)

        # Get current model from save_slots
        with get_connection(dbname, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT model FROM assets.save_slots WHERE slot_number = %s",
                    (slot,),
                )
                row = cur.fetchone()
                current_model = row.get("model") if row else None

        # Get available models from config
        settings = load_settings_as_dict()
        available = settings.get("global", {}).get("model", {}).get(
            "available_models", ["gpt-5.1", "TEST", "claude"]
        )

        return SlotModelResponse(
            slot=slot,
            model=current_model,
            available_models=available,
        )

    except Exception as e:
        logger.error(f"Error getting slot model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/slot/{slot}/model", response_model=SlotModelResponse)
async def set_slot_model_endpoint(slot: int, request: SlotModelRequest):
    """Set model for a slot."""
    from nexus.config import load_settings_as_dict

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        dbname = slot_dbname(slot)

        # Validate model against available models
        settings = load_settings_as_dict()
        available = settings.get("global", {}).get("model", {}).get(
            "available_models", ["gpt-5.1", "TEST", "claude"]
        )

        if request.model not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model '{request.model}'. Available: {', '.join(available)}",
            )

        # Update model in save_slots
        with get_connection(dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO assets.save_slots (slot_number, model)
                    VALUES (%s, %s)
                    ON CONFLICT (slot_number) DO UPDATE
                    SET model = EXCLUDED.model
                    """,
                    (slot, request.model),
                )

        return SlotModelResponse(
            slot=slot,
            model=request.model,
            available_models=available,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting slot model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SlotLockResponse(BaseModel):
    """Response for slot lock/unlock operations."""

    slot: int
    is_locked: bool
    message: str


@app.post("/api/slot/{slot}/lock", response_model=SlotLockResponse)
async def lock_slot_endpoint(slot: int):
    """Lock a slot to prevent modifications."""
    from nexus.api.save_slots import lock_slot

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        dbname = slot_dbname(slot)
        lock_slot(slot, dbname)
        return SlotLockResponse(
            slot=slot,
            is_locked=True,
            message=f"Slot {slot} is now locked",
        )
    except Exception as e:
        logger.error(f"Error locking slot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/slot/{slot}/unlock", response_model=SlotLockResponse)
async def unlock_slot_endpoint(slot: int):
    """Unlock a slot to allow modifications."""
    from nexus.api.save_slots import unlock_slot

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        dbname = slot_dbname(slot)
        unlock_slot(slot, dbname)
        return SlotLockResponse(
            slot=slot,
            is_locked=False,
            message=f"Slot {slot} is now unlocked",
        )
    except Exception as e:
        logger.error(f"Error unlocking slot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


from nexus.api.new_story_schemas import (
    SettingCard,
    CharacterSheet,
    StorySeed,
    LayerDefinition,
    ZoneDefinition,
    PlaceProfile,
    StartingScenario,
    CharacterConcept,
    TraitSelection,
    WildcardTrait,
    CharacterCreationState,
    TransitionData,
    WizardResponse,
    make_openai_strict_schema,
)
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.api.new_story_cache import read_cache


class ChatRequest(BaseModel):
    slot: int
    message: str
    # thread_id and current_phase are optional - resolved from slot state if not provided
    thread_id: Optional[str] = None
    current_phase: Optional[Literal["setting", "character", "seed"]] = None
    model: Literal["gpt-5.1", "TEST", "claude"] = "gpt-5.1"  # Model selection
    context_data: Optional[Dict[str, Any]] = None  # Accumulated wizard state
    accept_fate: bool = False  # Force tool call without adding user message


def get_base_url_for_model(model: str) -> Optional[str]:
    """Get API base URL based on model selection.

    Args:
        model: Model identifier (gpt-5.1, TEST, claude)

    Returns:
        Base URL for the model's API, or None to use default OpenAI
    """
    if model == "TEST":
        return "http://localhost:5102/v1"
    # Future: route Claude models to Anthropic API
    return None  # Use default OpenAI


def validate_subphase_tool(function_name: str, arguments: dict) -> dict:
    """Validate subphase tool arguments against Pydantic schemas.

    This ensures required fields (like trait_rationales) are present.
    Returns validated and normalized data, or raises HTTPException on failure.
    """
    schema_map = {
        "submit_character_concept": CharacterConcept,
        "submit_trait_selection": TraitSelection,
        "submit_wildcard_trait": WildcardTrait,
    }
    if schema := schema_map.get(function_name):
        try:
            return schema.model_validate(arguments).model_dump()
        except Exception as e:
            logger.error(f"{schema.__name__} validation failed: {e}")
            raise HTTPException(
                status_code=422,
                detail=f"LLM returned invalid {schema.__name__}: {str(e)}",
            )
    return arguments


@app.post("/api/story/new/chat")
async def new_story_chat_endpoint(request: ChatRequest):
    """Handle chat for new story wizard with tool calling"""
    try:
        from nexus.api.conversations import ConversationsClient
        from scripts.api_openai import OpenAIProvider
        import openai
        from pathlib import Path
        import json

        # Resolve thread_id and current_phase from slot state if not provided
        if request.thread_id is None or request.current_phase is None:
            from nexus.api.slot_state import get_slot_state

            state = get_slot_state(request.slot)
            if not state.is_wizard_mode:
                raise HTTPException(
                    status_code=400,
                    detail="Slot is not in wizard mode. Use /api/narrative/continue for narrative mode."
                )
            if state.wizard_state is None:
                raise HTTPException(
                    status_code=400,
                    detail="No wizard state found. Initialize with /api/story/new/setup first."
                )

            if request.thread_id is None:
                request.thread_id = state.wizard_state.thread_id
            if request.current_phase is None:
                request.current_phase = state.wizard_state.phase

        # Load character_state from cache if in character phase (always, not just when resolving)
        if request.current_phase == "character" and request.context_data is None:
            from nexus.api.slot_utils import slot_dbname

            cache = read_cache(slot_dbname(request.slot))
            if cache:
                # Build character_state from normalized columns
                char_state = {}
                if cache.character.has_concept():
                    # Build concept dict with suggestions from ephemeral table
                    concept_dict = {
                        "name": cache.character.name,
                        "archetype": cache.character.archetype,
                        "background": cache.character.background,
                        "appearance": cache.character.appearance,
                    }
                    # Add suggestions if available, or placeholders if cleared
                    # (suggestions are ephemeral - cleared after trait selection)
                    if cache.character.suggested_traits:
                        concept_dict["suggested_traits"] = [
                            s.trait for s in cache.character.suggested_traits
                        ]
                        concept_dict["trait_rationales"] = {
                            s.trait: s.rationale for s in cache.character.suggested_traits
                        }
                    elif cache.character.has_traits():
                        # Suggestions cleared after trait selection - use selected traits as placeholders
                        selected = [cache.character.trait1, cache.character.trait2, cache.character.trait3]
                        concept_dict["suggested_traits"] = selected
                        concept_dict["trait_rationales"] = {t: "Selected trait" for t in selected}
                    char_state["concept"] = concept_dict
                if cache.character.has_traits():
                    selected = [cache.character.trait1, cache.character.trait2, cache.character.trait3]
                    char_state["trait_selection"] = {
                        "selected_traits": selected,
                        # Provide placeholder rationales for validation
                        "trait_rationales": {t: "Selected trait" for t in selected},
                    }
                if cache.character.has_wildcard():
                    char_state["wildcard"] = {
                        "wildcard_name": cache.character.wildcard_name,
                        "wildcard_description": cache.character.wildcard_description,
                    }
                if char_state:
                    request.context_data = {"character_state": char_state}

        # Load settings for new story workflow
        settings_model = get_new_story_model()
        settings = load_settings()
        history_limit = (
            settings.get("API Settings", {})
            .get("new_story", {})
            .get("message_history_limit", 20)
        )

        # Use request model if specified (enables TEST mode), otherwise fall back to settings
        selected_model = request.model if request.model else settings_model

        # Initialize client with user's selected model
        # TEST mode uses in-memory storage, avoiding 1Password biometric auth
        client = ConversationsClient(model=selected_model)

        # Load prompt and extract welcome message from frontmatter
        prompt_path = (
            Path(__file__).parent.parent.parent / "prompts" / "storyteller_new.md"
        )
        with prompt_path.open() as f:
            doc = frontmatter.load(f)
            system_prompt = doc.content  # The markdown content without frontmatter
            welcome_message = doc.get("welcome_message", "")

        # Conditionally append trait menu for character creation phase
        if request.current_phase == "character":
            trait_menu_path = (
                Path(__file__).parent.parent.parent / "docs" / "trait_menu.md"
            )
            if trait_menu_path.exists():
                trait_menu = trait_menu_path.read_text()
                system_prompt += f"\n\n---\n\n# Trait Reference\n\n{trait_menu}"

        # Check if this is the first message (thread is empty)
        # If so, prepend the welcome message as an assistant message
        # Check if this is the first message (thread is empty)
        # If so, prepend the welcome message as an assistant message
        history = client.list_messages(request.thread_id, limit=history_limit)
        
        # Log history state for debugging
        logger.info(f"Thread {request.thread_id} history length: {len(history)}")
        
        if len(history) == 0 and welcome_message:
            # Thread is empty, prepend welcome message
            logger.info(f"Prepending welcome message to thread {request.thread_id}")
            client.add_message(request.thread_id, "assistant", welcome_message)
            # Re-fetch history to include the new message
            history = client.list_messages(request.thread_id, limit=history_limit)
        elif len(history) > 0 and welcome_message:
            # Check if the first message is already the welcome message to avoid duplication
            # (In case of race conditions or retries)
            first_msg = history[-1] if history else None # history is reversed later, so -1 is oldest? 
            # Wait, list_messages returns newest first. So history[-1] is the oldest.
            # Let's verify list_messages behavior. 
            # Assuming newest first:
            # history[0] is newest. history[-1] is oldest.
            pass

        # Add user message (skip when accept_fate to avoid polluting thread)
        if not request.accept_fate:
            client.add_message(request.thread_id, "user", request.message)

        # Define tools based on current phase
        tools = []
        primary_tool_name: Optional[str] = None
        if request.current_phase == "setting":
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "submit_world_document",
                        "description": "Submit the finalized world setting/genre document when the user agrees.",
                        "parameters": SettingCard.model_json_schema(),
                    },
                }
            )
            primary_tool_name = "submit_world_document"
        elif request.current_phase == "character":
            # Determine sub-phase based on character_state in context_data
            char_state = (request.context_data or {}).get("character_state", {})
            has_concept = char_state.get("concept") is not None
            has_traits = char_state.get("trait_selection") is not None
            has_wildcard = char_state.get("wildcard") is not None

            if not has_concept:
                # Sub-phase 1: Gather archetype, background, name, appearance
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_character_concept",
                            "strict": True,
                            "description": "Submit the character's core concept (archetype, background, name, appearance) when established.",
                            "parameters": make_openai_strict_schema(CharacterConcept.model_json_schema()),
                        },
                    }
                )
                primary_tool_name = "submit_character_concept"
            elif not has_traits:
                # Sub-phase 2: Select 3 traits from the 10 optional traits
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_trait_selection",
                            "strict": True,
                            "description": "Submit the 3 selected traits with rationales when the user confirms their choices.",
                            "parameters": make_openai_strict_schema(TraitSelection.model_json_schema()),
                        },
                    }
                )
                primary_tool_name = "submit_trait_selection"
            elif not has_wildcard:
                # Sub-phase 3: Define the custom wildcard trait
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_wildcard_trait",
                            "strict": True,
                            "description": "Submit the unique wildcard trait when defined.",
                            "parameters": make_openai_strict_schema(WildcardTrait.model_json_schema()),
                        },
                    }
                )
                primary_tool_name = "submit_wildcard_trait"
            # else: All sub-phases complete - character phase is done, no tool needed.
            # The CharacterSheet is assembled from accumulated state via to_character_sheet().
        elif request.current_phase == "seed":
            # Use unified StartingScenario model - Pydantic hoists all $defs to root level
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "submit_starting_scenario",
                        "strict": True,
                        "description": "Submit the chosen story seed and starting location details.",
                        "parameters": make_openai_strict_schema(StartingScenario.model_json_schema()),
                    },
                }
            )
            primary_tool_name = "submit_starting_scenario"

        # Fetch updated history (now includes welcome + user message if first interaction)
        # Note: list_messages returns newest first, so we reverse it
        history = client.list_messages(request.thread_id, limit=history_limit)
        history.reverse()

        # Filter out the message we just added (it's in history now) to avoid duplication if we append it manually
        # Actually, list_messages might not include the one we just added immediately if there's lag,
        # but usually it does. Let's rely on history and NOT append request.message manually if it's there.
        # To be safe, let's just use the history + system prompt.

        # Construct dynamic system instruction
        phase_instruction = f"Current Phase: {request.current_phase.upper()}.\n"

        if request.current_phase == "character":
            phase_instruction += "The world setting is established. Do NOT ask about genre. Focus on creating the protagonist.\n"
            if request.context_data and "setting" in request.context_data:
                phase_instruction += f"\n[WORLD SUMMARY]\n{json.dumps(request.context_data['setting'], indent=2)}\n[/WORLD SUMMARY]\n"

        elif request.current_phase == "seed":
            phase_instruction += "World and Character are established. Focus on generating the starting scenario.\n"
            if request.context_data:
                if "setting" in request.context_data:
                    phase_instruction += f"\n[WORLD SUMMARY]\n{json.dumps(request.context_data['setting'], indent=2)}\n[/WORLD SUMMARY]\n"
                if "character" in request.context_data:
                    phase_instruction += f"\n[CHARACTER SHEET]\n{json.dumps(request.context_data['character'], indent=2)}\n[/CHARACTER SHEET]\n"

        phase_instruction += (
            "Use the available tool to submit the artifact when the user confirms."
        )

        structured_choices_instruction = (
            "Use tools for every reply. Call `respond_with_choices` to deliver your "
            "narrative message plus 2-4 actionable choice strings (no numbering/markdown). "
            "Call a submission tool only when you are ready to commit that artifact. "
            "Do not send freeform text outside tool calls. Do not repeat the choices inside "
            "your message body; keep options only in the choices array."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": phase_instruction},
            {"role": "system", "content": structured_choices_instruction},
        ] + history

        # selected_model already defined at top of function from request.model
        base_url = get_base_url_for_model(selected_model)

        # For TEST mode, use dummy API key to avoid 1Password biometric auth
        if selected_model == "TEST":
            client_kwargs = {"api_key": "test-dummy-key", "base_url": base_url}
            logger.info(f"TEST mode: routing to mock server at {base_url}")
        else:
            provider = OpenAIProvider(model=selected_model)
            client_kwargs = {"api_key": provider.api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
                logger.info(f"Routing to: {base_url}")
        openai_client = openai.OpenAI(**client_kwargs)

        # Build WizardResponse schema for structured output
        wizard_schema = WizardResponse.model_json_schema()
        wizard_response_tool = {
            "type": "function",
            "function": {
                "name": "respond_with_choices",
                "strict": True,  # Enforce schema constraints including maxItems on choices
                "description": (
                    "Respond to the user with a narrative message and 2-4 short choice "
                    "strings (no numbering/markdown) to guide the next step. Do NOT list the "
                    "choices inside the message; only in the choices array."
                ),
                "parameters": wizard_schema,
            },
        }

        # Inject Accept Fate signal as system message if active
        if request.accept_fate:
            logger.info(f"Accept Fate active for phase {request.current_phase}")
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "[ACCEPT FATE ACTIVE] Follow the '### Accept Fate Protocol' in your instructions. "
                        "Make bold, concrete choices immediately."
                    ),
                }
            )

        # Build final toolset. When not forcing Accept Fate, require a tool call and
        # expose the respond_with_choices helper to keep outputs structured while
        # still allowing spontaneous submission calls.
        tools_for_llm = tools + [wizard_response_tool]
        tool_choice_mode: Any = "required"

        # Use Accept Fate to force artifact generation via the phase tool
        if request.accept_fate and primary_tool_name:
            logger.info(f"Forcing tool choice: {primary_tool_name}")
            tools_for_llm = tools  # Keep the response helper out of the path
            tool_choice_mode = {
                "type": "function",
                "function": {"name": primary_tool_name},
            }

        # Use response_format to enforce structured WizardResponse on normal runs.
        # When Accept Fate forces a tool call, drop the schema so the model isn't
        # forced to emit both a JSON payload and the required function call.
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "wizard_response",
                "strict": True,
                "schema": wizard_schema,
            },
        }

        if request.accept_fate and primary_tool_name:
            response_format = None

        logger.info(f"Calling LLM with tool_choice_mode: {tool_choice_mode}")
        response = openai_client.chat.completions.create(
            model=selected_model,
            messages=messages,
            tools=tools_for_llm if tools_for_llm else None,
            tool_choice=tool_choice_mode,
            response_format=response_format,
        )

        message = response.choices[0].message

        tool_calls = message.tool_calls or []

        # Prioritize submission tools; fall back to structured response helper
        submission_call = next(
            (tc for tc in tool_calls if tc.function.name != "respond_with_choices"),
            None,
        )
        response_call = next(
            (tc for tc in tool_calls if tc.function.name == "respond_with_choices"),
            None,
        )

        def parse_tool_arguments(raw_args: str) -> Dict[str, Any]:
            try:
                return json.loads(raw_args)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool call arguments: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Invalid tool call arguments from LLM: {str(e)}",
                )

        # Handle artifact submissions
        if submission_call:
            function_name = submission_call.function.name
            arguments = parse_tool_arguments(submission_call.function.arguments)

            # Persist the artifact to the setup cache
            try:
                if function_name == "submit_world_document":
                    record_drafts(request.slot, setting=arguments)
                elif function_name == "submit_character_sheet":
                    record_drafts(request.slot, character=arguments)
                elif function_name == "submit_starting_scenario":
                    # The tool returns a composite object with seed, layer, zone, and location
                    record_drafts(
                        request.slot,
                        seed=arguments.get("seed"),
                        layer=arguments.get("layer"),
                        zone=arguments.get("zone"),
                        location=arguments.get("location"),
                    )
                # Character creation sub-phase tools don't persist to DB cache
                # They return to frontend to update local state
            except Exception as e:
                logger.error(f"Failed to persist artifact for {function_name}: {e}")
                # We continue anyway to show the UI, but log the error

            # Determine if this completes the entire phase or just a sub-phase
            is_subphase_tool = function_name in [
                "submit_character_concept",
                "submit_trait_selection",
                "submit_wildcard_trait",
            ]

            # First validation: check individual sub-phase data against its Pydantic schema
            validated_data = validate_subphase_tool(function_name, arguments)

            # Track character creation progress and assemble final sheet when complete
            phase_complete = not is_subphase_tool
            response_data: Dict[str, Any] = validated_data

            if is_subphase_tool:
                # Merge the newly submitted sub-phase data with the accumulated state
                char_state_data = (request.context_data or {}).get("character_state", {})

                if function_name == "submit_character_concept":
                    char_state_updates = {"concept": validated_data}
                    # Persist suggested traits to ephemeral table
                    if "suggested_traits" in validated_data and "trait_rationales" in validated_data:
                        from nexus.api.new_story_cache import write_suggested_traits
                        from nexus.api.slot_utils import slot_dbname
                        suggestions = [
                            {"trait": trait, "rationale": validated_data["trait_rationales"].get(trait, "")}
                            for trait in validated_data["suggested_traits"]
                        ]
                        write_suggested_traits(slot_dbname(request.slot), suggestions)
                elif function_name == "submit_trait_selection":
                    char_state_updates = {"trait_selection": validated_data}
                    # Clear suggestions now that traits are selected
                    from nexus.api.new_story_cache import clear_suggested_traits
                    from nexus.api.slot_utils import slot_dbname
                    clear_suggested_traits(slot_dbname(request.slot))
                else:
                    char_state_updates = {"wildcard": validated_data}

                # Second validation: merge into accumulated state and validate cross-field constraints
                logger.debug("Merging char_state_data keys: %s", list(char_state_data.keys()))
                logger.debug("Merging char_state_updates keys: %s", list(char_state_updates.keys()))
                creation_state = CharacterCreationState.model_validate(
                    {**char_state_data, **char_state_updates}
                )

                response_data = {"character_state": creation_state.model_dump()}
                phase_complete = creation_state.is_complete()

                # Always save character state to cache (for CLI sub-phase continuity)
                # This persists intermediate state so CLI can resume across requests
                record_drafts(request.slot, character=creation_state.model_dump())
                logger.debug("Saved character state to cache: %s", list(creation_state.model_dump().keys()))

                if phase_complete:
                    # Character sheet is built when all sub-phases are complete
                    logger.info("Character phase complete - building sheet")
                    # Then build the character sheet (fail loudly per user directive)
                    character_sheet = creation_state.to_character_sheet().model_dump()
                    response_data.update({"character_sheet": character_sheet})
                    logger.info("Character sheet built successfully")

            # Return the structured data to frontend
            # phase_complete: True when entire phase (world/character/seed) is done
            # subphase_complete: True for character sub-phases (concept/traits/wildcard)
            #                    Frontend uses this to update character_state and
            #                    trigger next sub-phase tool availability
            return {
                "message": "Generating artifact...",
                "phase_complete": phase_complete,
                "subphase_complete": is_subphase_tool,
                "phase": request.current_phase,
                "artifact_type": function_name,
                "data": response_data,
            }

        # Handle structured conversational responses via helper tool
        def prepare_choices_for_ui(raw_choices: List[str]) -> List[str]:
            return [c.strip() for c in raw_choices if isinstance(c, str) and c.strip()]

        if response_call:
            try:
                wizard_response = WizardResponse.model_validate(
                    parse_tool_arguments(response_call.function.arguments)
                )
            except Exception as e:
                logger.error(f"Failed to parse respond_with_choices payload: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"LLM returned invalid WizardResponse via tool call: {str(e)}",
                )
            client.add_message(request.thread_id, "assistant", wizard_response.message)
            logger.info(
                "respond_with_choices: message_len=%d choices=%s",
                len(wizard_response.message or ""),
                prepare_choices_for_ui(wizard_response.choices),
            )

            return {
                "message": wizard_response.message,
                "choices": prepare_choices_for_ui(wizard_response.choices),
                "phase_complete": False,
                "thread_id": request.thread_id,
            }

        # Parse structured WizardResponse (guaranteed valid by response_format)
        try:
            wizard_response = WizardResponse.model_validate_json(message.content)
        except Exception as e:
            logger.error(f"Failed to parse WizardResponse: {e}")
            logger.error(f"Raw content: {message.content[:500] if message.content else 'None'}")
            raise HTTPException(
                status_code=500,
                detail=f"LLM returned invalid WizardResponse: {str(e)}",
            )

        # Save assistant message to thread (just the narrative text, not JSON)
        client.add_message(request.thread_id, "assistant", wizard_response.message)
        logger.info(
            "respond_with_choices (content path): message_len=%d choices=%s",
            len(wizard_response.message or ""),
            prepare_choices_for_ui(wizard_response.choices),
        )

        return {
            "message": wizard_response.message,
            "choices": prepare_choices_for_ui(wizard_response.choices),
            "phase_complete": False,
            "thread_id": request.thread_id,
        }

    except HTTPException:
        # Preserve explicit HTTP errors such as validation failures
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TransitionRequest(BaseModel):
    """Request to transition from wizard setup to narrative mode."""
    slot: int = Field(..., ge=1, le=5, description="Save slot number (1-5)")


class TransitionResponse(BaseModel):
    """Response from successful transition."""
    status: str
    character_id: int
    place_id: int
    layer_id: int
    zone_id: int
    message: str


@app.post("/api/story/new/transition", response_model=TransitionResponse)
async def transition_to_narrative_endpoint(request: TransitionRequest):
    """
    Transition from wizard setup to narrative mode.

    Reads from assets.new_story_creator cache, validates completeness,
    and calls perform_transition() to populate public schema atomically.

    This is the final step that:
    1. Moves all wizard data to the game database
    2. Creates the character, location hierarchy
    3. Sets new_story=false to enable narrative mode
    4. Clears the setup cache
    """
    from datetime import datetime, timezone
    from pydantic import ValidationError

    dbname = slot_dbname(request.slot)

    # Read the setup cache
    cache = read_cache(dbname)
    if not cache:
        raise HTTPException(
            status_code=400,
            detail=f"No setup data found for slot {request.slot}. Complete the wizard first."
        )

    # Validate all phases are complete
    if not cache.setting_complete():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: setting"
        )
    if not cache.character_complete():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: character"
        )
    if not cache.seed_complete():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: seed"
        )
    if not cache.get_layer_dict():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: layer"
        )
    if not cache.get_zone_dict():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: zone"
        )
    if not cache.get_initial_location():
        raise HTTPException(
            status_code=422,
            detail="Incomplete setup data. Missing: initial_location"
        )

    # Build TransitionData from cache
    try:
        # Get base_timestamp from cache
        base_timestamp = cache.base_timestamp or datetime.now(timezone.utc)

        # Get character dict and assemble CharacterSheet from CharacterCreationState
        char_draft = cache.get_character_dict()
        state = CharacterCreationState(**char_draft)
        char_sheet = state.to_character_sheet().model_dump()

        transition_data = TransitionData(
            setting=SettingCard(**cache.get_setting_dict()),
            character=CharacterSheet(**char_sheet),
            seed=StorySeed(**cache.get_seed_dict()),
            layer=LayerDefinition(**cache.get_layer_dict()),
            zone=ZoneDefinition(**cache.get_zone_dict()),
            location=PlaceProfile(**cache.get_initial_location()),
            base_timestamp=base_timestamp,
            thread_id=cache.thread_id or "",
        )
    except ValidationError as e:
        # Fail loudly per user directive
        logger.error(f"Validation error building TransitionData: {e}")
        raise HTTPException(
            status_code=422,
            detail=f"Setup data validation failed: {e.errors()}"
        )

    # Perform atomic transition
    mapper = NewStoryDatabaseMapper(dbname=dbname)
    try:
        result = mapper.perform_transition(transition_data)
        logger.info(f"Transition complete for slot {request.slot}: {result}")

        return TransitionResponse(
            status="transitioned",
            character_id=result["character_id"],
            place_id=result["place_id"],
            layer_id=result["layer_id"],
            zone_id=result["zone_id"],
            message=f"Welcome to {transition_data.setting.world_name}. Your story begins."
        )
    except ValueError as e:
        logger.error(f"Transition validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Transition failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transition failed: {str(e)}")


@app.get("/api/user-character")
async def get_user_character(slot: Optional[int] = None):
    """
    Get the user's character name for the active slot.

    Returns the character name from global_variables.user_character joined with characters.name.

    Args:
        slot: Save slot number (1-5). If not provided, uses NEXUS_SLOT env var.

    Returns:
        {"name": character_name} or null if no user character is set
    """
    try:
        dbname = require_slot_dbname(slot=slot)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        conn = psycopg2.connect(
            host=os.environ.get("PGHOST", "localhost"),
            database=dbname,
            user=os.environ.get("PGUSER", "pythagor"),
            port=os.environ.get("PGPORT", "5432"),
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.name
                    FROM global_variables gv
                    JOIN characters c ON c.id = gv.user_character
                    WHERE gv.id = TRUE
                """)
                row = cur.fetchone()
                if row:
                    return {"name": row[0]}
                return {"name": None}
    except psycopg2.Error as e:
        logger.error(f"Database error fetching user character: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
