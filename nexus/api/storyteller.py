"""
NEXUS Storyteller REST API

FastAPI application providing HTTP endpoints for interactive narrative generation
using the LORE agent. Supports session management, turn-based storytelling,
and real-time WebSocket streaming.

Usage:
    uvicorn nexus.api.storyteller:app --reload --port 8001
"""

import asyncio
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.api.session_manager import SessionManager, SessionMetadata, TurnRecord
from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_schemas import StoryTurnResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection parameters (matches apex_audition.py)
DB_PARAMS = {
    "dbname": "NEXUS",
    "user": "pythagor",
    "host": "localhost",
    "port": 5432,
}

# ============================================================================
# Pydantic Request/Response Models
# ============================================================================


class SessionCreateRequest(BaseModel):
    """Request to create a new story session"""

    session_name: Optional[str] = None
    initial_context: Optional[str] = None


class SessionCreateResponse(BaseModel):
    """Response from session creation"""

    session_id: str
    created_at: datetime
    status: str = "ready"


class StoryTurnRequest(BaseModel):
    """Request to generate a story turn"""

    session_id: str
    user_input: str
    options: Optional[Dict[str, Any]] = None


class RegenerateRequest(BaseModel):
    """Request to regenerate the last turn"""

    session_id: str
    options: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Standard error response format"""

    error: str
    detail: str
    session_id: Optional[str] = None


class SessionStateResponse(BaseModel):
    """Response containing full session state"""

    session_id: str
    session_name: Optional[str]
    created_at: datetime
    last_accessed: datetime
    turn_count: int
    current_phase: str
    initial_context: Optional[str]
    last_turn: Optional[Dict[str, Any]] = None


class TurnHistoryResponse(BaseModel):
    """Response containing turn history"""

    session_id: str
    turns: List[Dict[str, Any]]
    total_turns: int
    limit: int
    offset: int


class ContextResponse(BaseModel):
    """Response containing current context package"""

    session_id: str
    turn_id: Optional[str] = None
    context: Dict[str, Any]


class DeleteResponse(BaseModel):
    """Response from session deletion"""

    status: str
    session_id: str


class SessionListResponse(BaseModel):
    """Response containing list of sessions"""

    sessions: List[SessionMetadata]
    total: int


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="NEXUS Storyteller API",
    version="1.0.0",
    description="REST API for interactive narrative generation using the LORE agent",
)

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8080",  # Alternative frontend
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
session_manager: Optional[SessionManager] = None
lore_instances: Dict[str, LORE] = {}  # Session-specific LORE instances


# ============================================================================
# Startup/Shutdown Events
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    global session_manager

    logger.info("Starting NEXUS Storyteller API...")

    # Initialize session manager
    session_manager = SessionManager()
    logger.info(f"Session manager initialized: {session_manager.sessions_dir}")

    # Verify database connection
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        conn.close()
        logger.info("Database connection verified")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

    # Test 1Password CLI access (for API keys)
    try:
        result = subprocess.run(
            ["op", "whoami"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            logger.info("1Password CLI access verified")
        else:
            logger.warning("1Password CLI not authenticated. API key retrieval may fail.")
    except FileNotFoundError:
        logger.warning(
            "1Password CLI not found. Install from "
            "https://developer.1password.com/docs/cli/get-started/"
        )
    except Exception as e:
        logger.warning(f"Failed to verify 1Password CLI: {e}")

    # Create sessions directory if it doesn't exist
    sessions_dir = Path(__file__).parent.parent.parent / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Sessions directory: {sessions_dir}")

    # Add sessions directory to .gitignore if not already there
    gitignore_path = Path(__file__).parent.parent.parent / ".gitignore"
    try:
        if gitignore_path.exists():
            with open(gitignore_path, "r") as f:
                content = f.read()
            if "sessions/" not in content:
                with open(gitignore_path, "a") as f:
                    f.write("\n# Session data (REST API)\nsessions/\n")
                logger.info("Added sessions/ to .gitignore")
    except Exception as e:
        logger.warning(f"Failed to update .gitignore: {e}")

    logger.info("NEXUS Storyteller API ready!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down NEXUS Storyteller API...")

    # Cleanup LORE instances
    global lore_instances
    lore_instances.clear()

    logger.info("Shutdown complete")


# ============================================================================
# Helper Functions
# ============================================================================


def get_db():
    """Get database connection"""
    return psycopg2.connect(**DB_PARAMS, cursor_factory=RealDictCursor)


def get_or_create_lore(session_id: str) -> LORE:
    """
    Get or create a LORE instance for a session.

    Args:
        session_id: Session ID

    Returns:
        LORE instance for this session
    """
    if session_id not in lore_instances:
        logger.info(f"Creating new LORE instance for session {session_id}")
        lore_instances[session_id] = LORE(debug=False, enable_logon=True)

    return lore_instances[session_id]


async def run_turn_cycle(
    lore: LORE, user_input: str, options: Optional[Dict[str, Any]] = None
) -> StoryTurnResponse:
    """
    Run a complete turn cycle with the LORE agent.

    Args:
        lore: LORE instance
        user_input: User input for this turn
        options: Optional generation options

    Returns:
        StoryTurnResponse from LORE

    Raises:
        Exception: If turn cycle fails
    """
    try:
        # TODO: Implement actual LORE turn cycle integration
        # For now, this is a placeholder that needs to be connected to LORE's turn cycle

        logger.info(f"Running turn cycle with input: {user_input[:50]}...")

        # This would be the actual LORE turn cycle call
        # response = await lore.run_turn(user_input, options)

        # Placeholder response for now
        from nexus.agents.lore.logon_schemas import NarrativeChunk, create_minimal_response

        narrative_text = (
            f"[PLACEHOLDER] The story continues based on: {user_input}\n\n"
            "This is a placeholder response. The actual LORE integration will "
            "generate rich narrative content with metadata, entity tracking, and state updates."
        )

        response = create_minimal_response(narrative_text)

        return response

    except Exception as e:
        logger.error(f"Turn cycle failed: {e}")
        raise


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "NEXUS Storyteller API",
        "version": "1.0.0",
        "status": "ready",
        "endpoints": {
            "sessions": "/api/story/sessions",
            "create_session": "/api/story/session/create",
            "turn": "/api/story/turn",
            "regenerate": "/api/story/regenerate",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ----------------------------------------------------------------------------
# Session Management Endpoints
# ----------------------------------------------------------------------------


@app.post("/api/story/session/create", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest):
    """
    Create a new story session.

    Creates a new session with optional name and initial context.
    Session data is persisted to disk in sessions/{session_id}/ directory.
    """
    try:
        metadata = session_manager.create_session(
            session_name=request.session_name, initial_context=request.initial_context
        )

        return SessionCreateResponse(
            session_id=metadata.session_id,
            created_at=metadata.created_at,
            status="ready",
        )

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@app.get("/api/story/session/{session_id}", response_model=SessionStateResponse)
async def get_session(session_id: str):
    """
    Get current session state.

    Returns complete session metadata including creation time, turn count,
    and the last turn (if any).
    """
    try:
        state = session_manager.get_session(session_id)

        return SessionStateResponse(
            session_id=state.metadata.session_id,
            session_name=state.metadata.session_name,
            created_at=state.metadata.created_at,
            last_accessed=state.metadata.last_accessed,
            turn_count=state.metadata.turn_count,
            current_phase=state.metadata.current_phase,
            initial_context=state.metadata.initial_context,
            last_turn=state.last_turn.model_dump(mode="json") if state.last_turn else None,
        )

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    except Exception as e:
        logger.error(f"Failed to get session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")


@app.get("/api/story/sessions", response_model=SessionListResponse)
async def list_sessions():
    """
    List all sessions.

    Returns metadata for all sessions, sorted by most recently accessed.
    """
    try:
        sessions = session_manager.list_sessions()

        return SessionListResponse(sessions=sessions, total=len(sessions))

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")


@app.delete("/api/story/session/{session_id}", response_model=DeleteResponse)
async def delete_session(session_id: str):
    """
    Delete a session and all associated data.

    Removes the session directory and all files (metadata, turns, context snapshots).
    This operation cannot be undone.
    """
    try:
        deleted = session_manager.delete_session(session_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        # Remove LORE instance if it exists
        if session_id in lore_instances:
            del lore_instances[session_id]

        return DeleteResponse(status="deleted", session_id=session_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")


# ----------------------------------------------------------------------------
# Story Generation Endpoints
# ----------------------------------------------------------------------------


@app.post("/api/story/turn", response_model=StoryTurnResponse)
async def story_turn(request: StoryTurnRequest, background_tasks: BackgroundTasks):
    """
    Submit user input and generate narrative response.

    Runs a complete LORE turn cycle:
    1. Process user input
    2. Assemble context (warm slice, entities, memory)
    3. Generate narrative with Apex LLM
    4. Extract metadata and state updates
    5. Persist turn to session history

    The response includes the narrative text along with metadata, entity references,
    and state updates.
    """
    try:
        # Verify session exists
        try:
            session_manager.get_session(request.session_id)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"Session {request.session_id} not found"
            )

        # Get or create LORE instance for this session
        lore = get_or_create_lore(request.session_id)

        # Run turn cycle
        logger.info(f"Processing turn for session {request.session_id}")
        response = await run_turn_cycle(lore, request.user_input, request.options)

        # Save turn to session
        response_dict = response.model_dump(mode="json")
        turn_record = session_manager.add_turn(
            session_id=request.session_id,
            user_input=request.user_input,
            response=response_dict,
            options=request.options,
        )

        logger.info(
            f"Turn {turn_record.turn_number} completed for session {request.session_id}"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process turn: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process turn: {str(e)}")


@app.post("/api/story/regenerate", response_model=StoryTurnResponse)
async def regenerate_turn(request: RegenerateRequest):
    """
    Regenerate the last narrative turn with different parameters.

    Replaces the last turn in the session history with a new generation.
    Useful for trying different generation options or recovering from
    unsatisfactory outputs.
    """
    try:
        # Verify session exists
        try:
            state = session_manager.get_session(request.session_id)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"Session {request.session_id} not found"
            )

        # Verify session has turns
        if state.metadata.turn_count == 0:
            raise HTTPException(
                status_code=400, detail=f"Session {request.session_id} has no turns to regenerate"
            )

        # Get last turn to retrieve user input
        last_turn = state.last_turn
        if not last_turn:
            raise HTTPException(
                status_code=500, detail="Failed to retrieve last turn"
            )

        # Get LORE instance
        lore = get_or_create_lore(request.session_id)

        # Regenerate with same user input but potentially different options
        logger.info(f"Regenerating last turn for session {request.session_id}")
        response = await run_turn_cycle(lore, last_turn.user_input, request.options)

        # Update last turn in session
        response_dict = response.model_dump(mode="json")
        session_manager.update_last_turn(
            session_id=request.session_id, response=response_dict, options=request.options
        )

        logger.info(f"Turn regenerated for session {request.session_id}")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to regenerate turn: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to regenerate turn: {str(e)}")


# ----------------------------------------------------------------------------
# History & Context Endpoints
# ----------------------------------------------------------------------------


@app.get("/api/story/history/{session_id}", response_model=TurnHistoryResponse)
async def get_turn_history(
    session_id: str, limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)
):
    """
    Get turn history for a session.

    Returns paginated list of past turns with user input and AI responses.
    Most recent turns are returned first.
    """
    try:
        # Verify session exists
        try:
            state = session_manager.get_session(session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        # Get turn history
        turns = session_manager.get_turn_history(session_id, limit=limit, offset=offset)

        # Convert to dicts
        turns_data = [turn.model_dump(mode="json") for turn in turns]

        return TurnHistoryResponse(
            session_id=session_id,
            turns=turns_data,
            total_turns=state.metadata.turn_count,
            limit=limit,
            offset=offset,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get turn history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get turn history: {str(e)}")


@app.get("/api/story/context/{session_id}", response_model=ContextResponse)
async def get_current_context(session_id: str, turn_id: Optional[str] = Query(None)):
    """
    Get current context package (for debugging).

    If turn_id is provided, returns the context snapshot for that turn.
    Otherwise, returns the current context state.

    Note: Context snapshots are only available if they were saved during turn processing.
    """
    try:
        # Verify session exists
        try:
            state = session_manager.get_session(session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        # Get context snapshot if turn_id provided
        if turn_id:
            context = session_manager.get_context_snapshot(session_id, turn_id)
            if not context:
                raise HTTPException(
                    status_code=404,
                    detail=f"Context snapshot not found for turn {turn_id}",
                )
        else:
            # Return current session state as context
            context = {
                "session_id": session_id,
                "turn_count": state.metadata.turn_count,
                "last_accessed": state.metadata.last_accessed.isoformat(),
                "note": "Full context retrieval requires LORE integration",
            }

        return ContextResponse(session_id=session_id, turn_id=turn_id, context=context)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get context: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get context: {str(e)}")


# ----------------------------------------------------------------------------
# WebSocket Streaming Endpoint
# ----------------------------------------------------------------------------


@app.websocket("/api/story/stream/{session_id}")
async def websocket_stream(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time generation updates.

    Connects to a session and streams progress updates during turn processing:
    - Phase transitions (user_input → warm_slice → memory → generation → complete)
    - Narrative chunks as they're generated (if supported by LLM)
    - Error notifications

    Message format:
    {
        "type": "phase" | "chunk" | "complete" | "error",
        "phase": str (for type=phase),
        "content": str (for type=chunk),
        "response": dict (for type=complete),
        "error": str (for type=error)
    }
    """
    await websocket.accept()

    try:
        # Verify session exists
        try:
            session_manager.get_session(session_id)
        except FileNotFoundError:
            await websocket.send_json(
                {"type": "error", "error": f"Session {session_id} not found"}
            )
            await websocket.close()
            return

        logger.info(f"WebSocket connected for session {session_id}")

        # Send connection confirmation
        await websocket.send_json({"type": "connected", "session_id": session_id})

        # Listen for messages from client
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "turn":
                user_input = data.get("user_input")
                options = data.get("options")

                if not user_input:
                    await websocket.send_json(
                        {"type": "error", "error": "user_input is required"}
                    )
                    continue

                # Send phase updates
                await websocket.send_json({"type": "phase", "phase": "user_input"})

                # Get LORE instance
                lore = get_or_create_lore(session_id)

                # Run turn cycle with streaming updates
                # TODO: Implement streaming from LORE
                await websocket.send_json({"type": "phase", "phase": "warm_slice"})
                await websocket.send_json({"type": "phase", "phase": "memory"})
                await websocket.send_json({"type": "phase", "phase": "generation"})

                # Generate response
                response = await run_turn_cycle(lore, user_input, options)

                # Save turn
                response_dict = response.model_dump(mode="json")
                session_manager.add_turn(
                    session_id=session_id,
                    user_input=user_input,
                    response=response_dict,
                    options=options,
                )

                # Send completion
                await websocket.send_json(
                    {"type": "complete", "response": response_dict}
                )

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass


# ============================================================================
# Error Handlers
# ============================================================================


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return HTTPException(
        status_code=500,
        detail={"error": "Internal server error", "detail": str(exc)},
    )


# ============================================================================
# Main Entry Point (for testing)
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)
