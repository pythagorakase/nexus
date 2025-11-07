"""FastAPI application exposing the NEXUS Storyteller interface."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

from nexus.api.session_manager import SessionManager
from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_schemas import (
    StoryTurnResponse,
    create_minimal_response,
    validate_story_turn_response,
)


LOGGER = logging.getLogger("nexus.api.storyteller")

ROOT_DIR = Path(__file__).resolve().parents[2]
SESSIONS_DIR = ROOT_DIR / "sessions"

session_manager = SessionManager(SESSIONS_DIR)

app = FastAPI(title="NEXUS Storyteller API", version="0.1.0")

# Configure CORS for local development clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global LORE instance and synchronization primitives
_lore_instance: Optional[LORE] = None
_lore_init_lock = asyncio.Lock()
_turn_lock = asyncio.Lock()


class SessionCreateRequest(BaseModel):
    """Request payload for creating a storytelling session."""

    session_name: Optional[str] = Field(default=None)
    initial_context: Optional[str] = Field(default=None)


class SessionCreateResponse(BaseModel):
    """Response payload returned after creating a session."""

    session_id: str
    created_at: datetime
    status: str = Field(default="ready")


class StoryTurnRequest(BaseModel):
    """Request payload for processing a story turn."""

    session_id: str
    user_input: str
    options: Optional[Dict[str, Any]] = Field(default=None)


class RegenerateTurnRequest(BaseModel):
    """Request payload for regenerating the most recent turn."""

    session_id: str
    options: Optional[Dict[str, Any]] = Field(default=None)


def story_error(
    status_code: int,
    *,
    error: str,
    detail: str,
    session_id: Optional[str] = None,
) -> None:
    """Raise an HTTPException with the standardized error payload."""

    payload = {"error": error, "detail": detail, "session_id": session_id}
    LOGGER.error("Story API error %s: %s", status_code, payload)
    raise HTTPException(status_code=status_code, detail=payload)


async def get_lore() -> LORE:
    """Return a shared LORE instance, creating it on demand."""
    global _lore_instance

    if _lore_instance is not None:
        return _lore_instance

    async with _lore_init_lock:
        if _lore_instance is None:
            LOGGER.info("Initializing LORE agent for Storyteller API")
            _lore_instance = LORE()
    return _lore_instance


def _apply_turn_options(lore: LORE, options: Optional[Dict[str, Any]]) -> None:
    """Apply caller-provided options to the LORE runtime."""
    if not options or not lore.llm_manager:
        return

    keep_model = options.get("keep_model")
    if keep_model is not None:
        lore.llm_manager.unload_on_exit = not bool(keep_model)


def _build_story_response(raw: Any, lore: LORE) -> StoryTurnResponse:
    """Convert raw LORE output into a StoryTurnResponse schema."""
    candidate = raw
    turn_context = getattr(lore, "turn_context", None)
    if turn_context and turn_context.apex_response:
        candidate = turn_context.apex_response

    if isinstance(candidate, dict):
        try:
            return validate_story_turn_response(candidate)
        except ValidationError:
            pass

    if isinstance(candidate, str):
        text = candidate.strip()
        if text:
            try:
                data = json.loads(text)
                return validate_story_turn_response(data)
            except (json.JSONDecodeError, ValidationError):
                return create_minimal_response(text)
        return create_minimal_response("")

    return create_minimal_response(str(candidate))


def _prepare_turn_record(
    session_id: str,
    lore: LORE,
    response: StoryTurnResponse,
    user_input: str,
    options: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble the persistence payload for a completed turn."""
    turn_context = getattr(lore, "turn_context", None)
    timestamp = datetime.utcnow().isoformat()
    turn_id = (
        turn_context.turn_id
        if turn_context and getattr(turn_context, "turn_id", None)
        else f"turn_{int(time.time())}"
    )

    context_file: Optional[str] = None
    if turn_context and turn_context.context_payload:
        context_path = session_manager.save_context(session_id, turn_id, turn_context.context_payload)
        try:
            context_file = str(context_path.relative_to(session_manager.base_path))
        except ValueError:
            context_file = str(context_path)

    record: Dict[str, Any] = {
        "turn_id": turn_id,
        "timestamp": timestamp,
        "user_input": user_input,
        "response": response.model_dump(),
        "options": options or {},
        "context_file": context_file,
    }

    if turn_context:
        record.update(
            {
                "phase_states": turn_context.phase_states,
                "warm_slice": turn_context.warm_slice,
                "entity_data": turn_context.entity_data,
                "retrieved_passages": turn_context.retrieved_passages,
                "memory_state": turn_context.memory_state,
                "token_counts": turn_context.token_counts,
                "errors": turn_context.error_log,
            }
        )

    return record


def _ensure_session_exists(session_id: str) -> None:
    if not session_manager.session_exists(session_id):
        story_error(
            status.HTTP_404_NOT_FOUND,
            error="session_not_found",
            detail="Session does not exist",
            session_id=session_id,
        )


@app.post("/api/story/session/create", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
    """Create a new storytelling session."""
    metadata = session_manager.create_session(
        session_name=request.session_name,
        initial_context=request.initial_context,
    )
    return SessionCreateResponse(
        session_id=metadata.session_id,
        created_at=datetime.fromisoformat(metadata.created_at),
    )


@app.get("/api/story/sessions")
async def list_sessions() -> Dict[str, Any]:
    """List all available sessions sorted by recent activity."""
    sessions = session_manager.list_sessions()
    return {"sessions": sessions}


@app.get("/api/story/session/{session_id}")
async def get_session_state(session_id: str) -> Dict[str, Any]:
    """Return metadata, latest turn, and current context for a session."""
    _ensure_session_exists(session_id)
    session_manager.touch_session(session_id)
    return session_manager.get_session_state(session_id)


@app.get("/api/story/context/{session_id}")
async def get_session_context(session_id: str) -> Dict[str, Any]:
    """Return the most recent context package for debugging."""
    _ensure_session_exists(session_id)
    session_manager.touch_session(session_id)
    context = session_manager.get_latest_context(session_id)
    return {"context": context}


@app.get("/api/story/history/{session_id}")
async def get_turn_history(
    session_id: str,
    limit: int = Query(default=10, ge=0),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """Return a paginated view of turn history."""
    _ensure_session_exists(session_id)
    session_manager.touch_session(session_id)
    history = session_manager.get_history_slice(session_id, limit=limit, offset=offset)
    return {"turns": history, "total": len(session_manager.load_history(session_id))}


@app.post("/api/story/turn", response_model=StoryTurnResponse)
async def process_story_turn(
    request: StoryTurnRequest,
    background_tasks: BackgroundTasks,
) -> StoryTurnResponse:
    """Submit user input and generate the next narrative turn."""
    session_id = request.session_id
    _ensure_session_exists(session_id)

    lore = await get_lore()

    async with _turn_lock:
        session_manager.update_phase(session_id, "starting")
        _apply_turn_options(lore, request.options)

        response_text = await lore.process_turn(request.user_input)
        story_response = _build_story_response(response_text, lore)
        record = _prepare_turn_record(session_id, lore, story_response, request.user_input, request.options)
        session_manager.record_turn(session_id, record)

    background_tasks.add_task(session_manager.prune_session_context, session_id)
    return story_response


@app.post("/api/story/regenerate", response_model=StoryTurnResponse)
async def regenerate_last_turn(
    request: RegenerateTurnRequest,
    background_tasks: BackgroundTasks,
) -> StoryTurnResponse:
    """Regenerate the most recent turn and replace it in history."""
    session_id = request.session_id
    _ensure_session_exists(session_id)

    history = session_manager.load_history(session_id)
    if not history:
        story_error(
            status.HTTP_400_BAD_REQUEST,
            error="no_turns",
            detail="Cannot regenerate without prior turns",
            session_id=session_id,
        )

    last_turn = history[-1]
    user_input = last_turn.get("user_input")
    if not user_input:
        story_error(
            status.HTTP_400_BAD_REQUEST,
            error="missing_user_input",
            detail="Last turn is missing user input",
            session_id=session_id,
        )

    lore = await get_lore()

    async with _turn_lock:
        session_manager.update_phase(session_id, "regenerating")
        _apply_turn_options(lore, request.options)

        response_text = await lore.process_turn(user_input)
        story_response = _build_story_response(response_text, lore)
        record = _prepare_turn_record(session_id, lore, story_response, user_input, request.options)
        session_manager.record_turn(session_id, record, replace_last=True)

    background_tasks.add_task(session_manager.prune_session_context, session_id)
    return story_response


@app.delete("/api/story/session/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    """Delete a session and all associated artifacts."""
    if session_manager.session_exists(session_id):
        session_manager.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@app.websocket("/api/story/stream/{session_id}")
async def stream_story_turn(websocket: WebSocket, session_id: str) -> None:
    """Provide real-time updates for a narrative turn via WebSocket."""
    await websocket.accept()

    if not session_manager.session_exists(session_id):
        await websocket.send_json(
            {
                "event": "error",
                "error": "session_not_found",
                "detail": "Session does not exist",
                "session_id": session_id,
            }
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    except ValueError:
        await websocket.send_json(
            {
                "event": "error",
                "error": "invalid_payload",
                "detail": "Expected JSON payload with user_input",
                "session_id": session_id,
            }
        )
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return

    user_input = payload.get("user_input")
    options = payload.get("options")
    if not user_input:
        await websocket.send_json(
            {
                "event": "error",
                "error": "missing_user_input",
                "detail": "user_input is required",
                "session_id": session_id,
            }
        )
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return

    lore = await get_lore()

    async with _turn_lock:
        session_manager.update_phase(session_id, "starting")
        _apply_turn_options(lore, options)

        turn_task = asyncio.create_task(lore.process_turn(user_input))
        last_phase: Optional[str] = None

        try:
            while True:
                done, _ = await asyncio.wait({turn_task}, timeout=0.2)
                phase = lore.current_phase.value
                if phase != last_phase:
                    await websocket.send_json({"event": "phase_update", "phase": phase})
                    session_manager.update_phase(session_id, phase)
                    last_phase = phase

                if done:
                    response_text = turn_task.result()
                    break

            story_response = _build_story_response(response_text, lore)
            record = _prepare_turn_record(session_id, lore, story_response, user_input, options)
            session_manager.record_turn(session_id, record)

            await websocket.send_json(
                {
                    "event": "turn_complete",
                    "response": story_response.model_dump(),
                    "metadata": session_manager.get_metadata(session_id).to_dict(),
                }
            )
        except Exception as exc:  # pragma: no cover - defensive runtime handling
            LOGGER.exception("WebSocket streaming error: %s", exc)
            session_manager.update_phase(session_id, "error")
            await websocket.send_json(
                {
                    "event": "error",
                    "error": "turn_failed",
                    "detail": str(exc),
                    "session_id": session_id,
                }
            )
        finally:
            if not turn_task.done():
                turn_task.cancel()
            await websocket.close()


__all__ = ["app"]
