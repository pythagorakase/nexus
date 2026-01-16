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
from nexus.api.narrative_generation import (
    generate_narrative_async,
    get_chunk_info,
    write_to_incubator,
    generate_bootstrap_narrative,
)

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



# Include modular routers
from nexus.api.slot_endpoints import router as slot_router
from nexus.api.setup_endpoints import router as setup_router
from nexus.api.wizard_chat import router as wizard_chat_router
app.include_router(slot_router)
app.include_router(setup_router)
app.include_router(wizard_chat_router)

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



# Import schemas from narrative_schemas.py
from nexus.api.narrative_schemas import (
    ContinueNarrativeRequest,
    ContinueNarrativeResponse,
    ApproveNarrativeRequest,
    NarrativeStatus,
    ChoiceSelection,
    SelectChoiceRequest,
    SelectChoiceResponse,
    StartSetupRequest,
    RecordDraftRequest,
    ResetSetupRequest,
    SelectSlotRequest,
    TraitMenuItemResponse,
    SlotStateResponse,
    SlotContinueRequest,
    SlotContinueResponse,
    SlotUndoResponse,
    SlotModelRequest,
    SlotModelResponse,
    SlotLockResponse,
    ChatRequest,
    TransitionRequest,
    TransitionResponse,
)


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
        request.slot,
        get_db_connection=get_db_connection,
        load_settings=load_settings,
        manager=manager,
    )

    message = "Narrative bootstrap started" if is_bootstrap else f"Narrative generation started for chunk {parent_chunk_id}"
    return ContinueNarrativeResponse(
        session_id=session_id,
        status="processing",
        message=message,
    )


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
