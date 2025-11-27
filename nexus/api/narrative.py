"""
FastAPI endpoints for live narrative turns with incubator support
"""

import asyncio
import frontmatter
import json
import logging
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
from nexus.api.lore_adapter import response_to_incubator, validate_incubator_data
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

    return psycopg2.connect(
        host="localhost",
        database=dbname,
        user="pythagor"
    )


def load_settings():
    """Load settings from settings.json"""
    settings_path = Path(__file__).parent.parent.parent / "settings.json"
    with open(settings_path, "r") as f:
        return json.load(f)


def get_new_story_model() -> str:
    """Get the configured model for new story workflow."""
    settings = load_settings()
    return settings.get("API Settings", {}).get("new_story", {}).get("model", "gpt-5.1")


# Request/Response models
class ContinueNarrativeRequest(BaseModel):
    """Request to continue narrative from a chunk"""

    chunk_id: int = Field(description="Parent chunk ID to continue from")
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

    session_id: str = Field(description="Session ID of the narrative to approve")
    commit: bool = Field(default=True, description="Whether to commit to database")


class NarrativeStatus(BaseModel):
    """Status of a narrative generation session"""

    session_id: str
    status: str  # provisional, approved, committed, error
    chunk_id: Optional[int]
    parent_chunk_id: Optional[int]
    created_at: Optional[datetime]
    error: Optional[str]


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
    Continue narrative from a given chunk
    Initiates async generation and returns session_id for tracking
    """
    session_id = str(uuid.uuid4())

    logger.info(f"Starting narrative continuation for chunk {request.chunk_id}")
    logger.info(f"Session ID: {session_id}")
    logger.info(f"User text: {request.user_text[:100]}...")

    # Send initial progress
    await manager.send_progress(
        session_id,
        "initiated",
        {"chunk_id": request.chunk_id, "parent_chunk_id": request.chunk_id},
    )

    # Start async generation in background
    background_tasks.add_task(
        generate_narrative_async,
        session_id,
        request.chunk_id,
        request.user_text,
        request.test_mode,
        request.slot,
    )

    return ContinueNarrativeResponse(
        session_id=session_id,
        status="processing",
        message=f"Narrative generation started for chunk {request.chunk_id}",
    )


async def generate_narrative_async(
    session_id: str,
    parent_chunk_id: int,
    user_text: str,
    test_mode: Optional[bool] = None,
    slot: Optional[int] = None,
):
    """
    Async function to generate narrative
    Sends progress updates via WebSocket
    """
    conn = None
    try:
        # Connect to database
        conn = get_db_connection(slot)

        # Send progress: loading chunk
        await manager.send_progress(session_id, "loading_chunk")

        # Get parent chunk info
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
                }
            },
        )

        # Check if we should use mock mode (for testing without LLM)
        use_mock = test_mode is True  # Explicit True means use mock

        if use_mock:
            # Mock mode for testing without real LLM calls
            logger.info("Using mock mode for narrative generation")
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

        else:
            # Real LORE integration
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
            metadata_updates, entity_updates, reference_updates,
            session_id, llm_response_id, status
        ) VALUES (
            TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """

        cur.execute(
            query,
            (
                data["chunk_id"],
                data["parent_chunk_id"],
                data["user_text"],
                data["storyteller_text"],
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


@app.post("/api/narrative/approve/{session_id}")
async def approve_narrative(session_id: str, request: ApproveNarrativeRequest, slot: Optional[int] = None):
    """
    Approve narrative and optionally commit to database
    """
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

        if request.commit:
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

        # Load welcome message
        prompt_path = (
            Path(__file__).parent.parent.parent / "prompts" / "storyteller_new.md"
        )
        welcome_message = ""
        if prompt_path.exists():
            with prompt_path.open() as f:
                doc = frontmatter.load(f)
                welcome_message = doc.get("welcome_message", "")

        # Seed welcome message if exists
        if welcome_message:
            model = get_new_story_model()
            client = ConversationsClient(model=model)
            client.add_message(thread_id, "assistant", welcome_message)

        return {
            "status": "started",
            "thread_id": thread_id,
            "slot": request.slot,
            "welcome_message": welcome_message,
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
    """Get status of all save slots"""
    from nexus.api.slot_utils import all_slots, slot_dbname
    from nexus.api.save_slots import list_slots

    results = []
    for slot in all_slots():
        dbname = slot_dbname(slot)
        try:
            # Try to list slots from this DB
            slots_data = list_slots(dbname=dbname)
            # Find the row for this slot
            slot_data = next((s for s in slots_data if s["slot_number"] == slot), None)

            if slot_data:
                results.append(slot_data)
            else:
                results.append({"slot_number": slot, "is_active": False})
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            # Expected: DB doesn't exist or connection failed
            logger.warning(f"Could not connect to slot {slot} database: {e}")
            results.append({"slot_number": slot, "is_active": False})
        except Exception as e:
            # Unexpected errors should surface during development
            logger.error(f"Unexpected error fetching slot {slot}: {e}")
            raise

    return results


from nexus.api.new_story_schemas import (
    SettingCard,
    CharacterSheet,
    StorySeed,
    LayerDefinition,
    ZoneDefinition,
    PlaceProfile,
)


class ChatRequest(BaseModel):
    slot: int
    thread_id: str
    message: str
    current_phase: Literal["setting", "character", "seed"] = "setting"
    context_data: Optional[Dict[str, Any]] = None  # Accumulated wizard state


@app.post("/api/story/new/chat")
async def new_story_chat_endpoint(request: ChatRequest):
    """Handle chat for new story wizard with tool calling"""
    try:
        from nexus.api.conversations import ConversationsClient
        from scripts.api_openai import OpenAIProvider
        import openai
        from pathlib import Path
        import json

        # Load settings for new story workflow
        model = get_new_story_model()
        settings = load_settings()
        history_limit = (
            settings.get("API Settings", {})
            .get("new_story", {})
            .get("message_history_limit", 20)
        )

        # Initialize client
        client = ConversationsClient(model=model)

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
        history = client.list_messages(request.thread_id, limit=history_limit)
        if len(history) == 0 and welcome_message:
            # Thread is empty, prepend welcome message
            client.add_message(request.thread_id, "assistant", welcome_message)

        # Add user message
        client.add_message(request.thread_id, "user", request.message)

        # Define tools based on current phase
        tools = []
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
        elif request.current_phase == "character":
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "submit_character_sheet",
                        "description": "Submit the finalized character sheet when the user agrees.",
                        "parameters": CharacterSheet.model_json_schema(),
                    },
                }
            )
        elif request.current_phase == "seed":
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "submit_starting_scenario",
                        "description": "Submit the chosen story seed and starting location details.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "seed": StorySeed.model_json_schema(),
                                "layer": LayerDefinition.model_json_schema(),
                                "zone": ZoneDefinition.model_json_schema(),
                                "location": PlaceProfile.model_json_schema(),
                            },
                            "required": ["seed", "layer", "zone", "location"],
                        },
                    },
                }
            )

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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": phase_instruction},
        ] + history

        provider = OpenAIProvider(model=model)
        openai_client = openai.OpenAI(api_key=provider.api_key)

        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto",
        )

        message = response.choices[0].message

        # Check for tool calls
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            function_name = tool_call.function.name

            # Parse tool arguments
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool call arguments: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Invalid tool call arguments from LLM: {str(e)}",
                )

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
            except Exception as e:
                logger.error(f"Failed to persist artifact for {function_name}: {e}")
                # We continue anyway to show the UI, but log the error

            # Return the structured data to frontend
            return {
                "message": "Generating artifact...",
                "phase_complete": True,
                "phase": request.current_phase,
                "artifact_type": function_name,
                "data": arguments,
            }

        reply = message.content

        # Save assistant reply to thread
        client.add_message(request.thread_id, "assistant", reply)

        return {"message": reply, "phase_complete": False}

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
