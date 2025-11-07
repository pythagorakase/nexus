"""FastAPI application exposing the LORE storyteller agent over HTTP."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from nexus.api.session_manager import (
    SessionManager,
    SessionMetadata,
    SessionNotFoundError,
    TurnRecord,
)
from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_schemas import (
    StoryTurnResponse,
    create_minimal_response,
    validate_story_turn_response,
)
from nexus.agents.lore.utils.turn_context import TurnContext, TurnPhase


LOGGER = logging.getLogger("nexus.api.storyteller")

SESSIONS_DIR = Path(__file__).resolve().parents[2] / "sessions"
session_manager = SessionManager(SESSIONS_DIR)

app = FastAPI(title="NEXUS Storyteller API", version="0.1.0")

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SessionLocks:
    """Ensure sequential processing per session."""

    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

    async def for_session(self, session_id: str) -> asyncio.Lock:
        async with self._lock:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]


class SessionEventDispatcher:
    """Dispatch progress updates to WebSocket subscribers."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(session_id, []).append(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(session_id, [])
            if queue in subscribers:
                subscribers.remove(queue)
            if not subscribers:
                self._subscribers.pop(session_id, None)

    def publish(self, session_id: str, payload: Dict[str, Any]) -> None:
        payload.setdefault("timestamp", datetime.utcnow().isoformat())
        queues = self._subscribers.get(session_id, [])
        for queue in list(queues):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                LOGGER.warning("Dropping event for session %s: queue full", session_id)


session_locks = SessionLocks()
event_dispatcher = SessionEventDispatcher()

_lore_agent: Optional[LORE] = None
_lore_lock = asyncio.Lock()


async def get_lore_agent() -> LORE:
    """Lazily initialize and return a shared LORE agent."""

    global _lore_agent
    if _lore_agent is None:
        async with _lore_lock:
            if _lore_agent is None:
                LOGGER.info("Initializing LORE agent for Storyteller API")
                _lore_agent = await asyncio.to_thread(LORE)
    return _lore_agent


def _error_response(
    status_code: int,
    error: str,
    detail: str,
    session_id: Optional[str] = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": error,
            "detail": detail,
            "session_id": session_id,
        },
    )


def _serialize_metadata(metadata: SessionMetadata) -> Dict[str, Any]:
    return metadata.to_dict()


def _serialize_turn(record: TurnRecord) -> Dict[str, Any]:
    return {
        "turn_id": record.turn_id,
        "user_input": record.user_input,
        "response": record.response,
        "created_at": record.created_at.isoformat(),
        "options": record.options,
    }


def _parse_story_response(raw_response: str) -> StoryTurnResponse:
    if not raw_response:
        return create_minimal_response("")

    try:
        data = json.loads(raw_response)
        return validate_story_turn_response(data)
    except (json.JSONDecodeError, ValidationError, ValueError):
        LOGGER.debug("Falling back to minimal StoryTurnResponse", exc_info=True)
        return create_minimal_response(raw_response)


async def _run_turn(
    lore: LORE,
    session_id: str,
    user_input: str,
    options: Optional[Dict[str, Any]] = None,
) -> Tuple[StoryTurnResponse, Dict[str, Any]]:
    """Execute a turn with progress notifications."""

    options = options or {}
    turn_id = f"turn-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    lore.turn_context = TurnContext(
        turn_id=turn_id,
        user_input=user_input,
        start_time=datetime.utcnow().timestamp(),
    )

    if lore.llm_manager:
        lore.llm_manager.ensure_model_loaded()

    phases = [
        (TurnPhase.USER_INPUT, lore.turn_manager.process_user_input),
        (TurnPhase.WARM_ANALYSIS, lore.turn_manager.perform_warm_analysis),
        (TurnPhase.ENTITY_STATE, lore.turn_manager.query_entity_states),
        (TurnPhase.DEEP_QUERIES, lore.turn_manager.execute_deep_queries),
        (TurnPhase.PAYLOAD_ASSEMBLY, lore.turn_manager.assemble_context_payload),
    ]

    for phase, handler in phases:
        lore.current_phase = phase
        event_dispatcher.publish(
            session_id,
            {
                "type": "phase",
                "phase": phase.value,
                "status": "started",
                "turn_id": turn_id,
            },
        )
        try:
            await handler(lore.turn_context)
            event_dispatcher.publish(
                session_id,
                {
                    "type": "phase",
                    "phase": phase.value,
                    "status": "completed",
                    "turn_id": turn_id,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Phase %s failed", phase.value)
            lore.current_phase = TurnPhase.IDLE
            event_dispatcher.publish(
                session_id,
                {
                    "type": "phase",
                    "phase": phase.value,
                    "status": "error",
                    "detail": str(exc),
                    "turn_id": turn_id,
                },
            )
            raise

    lore.current_phase = TurnPhase.APEX_GENERATION
    event_dispatcher.publish(
        session_id,
        {
            "type": "phase",
            "phase": TurnPhase.APEX_GENERATION.value,
            "status": "started",
            "turn_id": turn_id,
        },
    )
    response_text = await lore.turn_manager.call_apex_ai(lore.turn_context)
    event_dispatcher.publish(
        session_id,
        {
            "type": "phase",
            "phase": TurnPhase.APEX_GENERATION.value,
            "status": "completed",
            "turn_id": turn_id,
        },
    )

    lore.current_phase = TurnPhase.INTEGRATION
    event_dispatcher.publish(
        session_id,
        {
            "type": "phase",
            "phase": TurnPhase.INTEGRATION.value,
            "status": "started",
            "turn_id": turn_id,
        },
    )
    await lore.turn_manager.integrate_response(lore.turn_context, response_text)
    event_dispatcher.publish(
        session_id,
        {
            "type": "phase",
            "phase": TurnPhase.INTEGRATION.value,
            "status": "completed",
            "turn_id": turn_id,
        },
    )

    lore.current_phase = TurnPhase.IDLE

    unload_flag = (
        lore.llm_manager
        and lore.llm_manager.unload_on_exit
        and lore.settings.get("Agent Settings", {})
        .get("LORE", {})
        .get("llm", {})
        .get("unload_after_turn", True)
    )
    if unload_flag:
        lore.llm_manager.unload_model()

    story_response = _parse_story_response(response_text)
    event_dispatcher.publish(
        session_id,
        {
            "type": "complete",
            "turn_id": turn_id,
            "summary": story_response.narrative.text[:120],
        },
    )

    context_snapshot = {
        "turn_id": turn_id,
        "user_input": user_input,
        "options": options,
        "phase_states": lore.turn_context.phase_states,
        "context_payload": lore.turn_context.context_payload,
        "memory_state": lore.turn_context.memory_state,
        "apex_response": lore.turn_context.apex_response,
        "response": story_response.model_dump(),
    }

    return story_response, context_snapshot


@app.post("/api/story/session/create")
async def create_session(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new story session and persist its metadata."""

    session_name = payload.get("session_name")
    initial_context = payload.get("initial_context")
    metadata = session_manager.create_session(
        session_name=session_name,
        initial_context=initial_context,
    )
    return {
        "session_id": metadata.session_id,
        "created_at": metadata.created_at.isoformat(),
        "status": "ready",
    }


@app.post("/api/story/turn", response_model=StoryTurnResponse)
async def story_turn(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
) -> StoryTurnResponse:
    """Process a user turn through the LORE agent and persist the results."""

    session_id = request.get("session_id")
    user_input = request.get("user_input")
    options = request.get("options", {})

    if not session_id or not user_input:
        raise _error_response(
            400,
            "invalid_request",
            "session_id and user_input are required",
            session_id,
        )

    if not session_manager.session_exists(session_id):
        raise _error_response(
            404,
            "session_not_found",
            "Session does not exist",
            session_id,
        )

    session_lock = await session_locks.for_session(session_id)
    async with session_lock:
        lore = await get_lore_agent()
        try:
            session_manager.update_phase(session_id, "processing")
        except SessionNotFoundError as exc:  # pragma: no cover - defensive guard
            raise _error_response(
                404,
                "session_not_found",
                str(exc),
                session_id,
            ) from exc

        try:
            story_response, context_snapshot = await _run_turn(
                lore,
                session_id,
                user_input,
                options,
            )
        except Exception as exc:
            LOGGER.exception("Turn processing failed for session %s", session_id)
            session_manager.update_phase(session_id, "error")
            raise _error_response(500, "turn_failed", str(exc), session_id) from exc

        turn_record = TurnRecord(
            turn_id=context_snapshot["turn_id"],
            user_input=user_input,
            response=story_response.model_dump(),
            created_at=datetime.utcnow(),
            options=options,
        )

        session_manager.append_turn(session_id, turn_record)
        background_tasks.add_task(
            session_manager.save_turn_context,
            session_id,
            context_snapshot["turn_id"],
            context_snapshot,
        )

        return story_response


@app.get("/api/story/session/{session_id}")
async def get_session_state(session_id: str) -> Dict[str, Any]:
    """Return metadata, last turn, and context snapshot for a session."""

    if not session_manager.session_exists(session_id):
        raise _error_response(
            404,
            "session_not_found",
            "Session does not exist",
            session_id,
        )

    metadata = session_manager.load_metadata(session_id)
    last_turn = session_manager.get_last_turn(session_id)
    context = session_manager.load_turn_context(session_id)

    return {
        "metadata": _serialize_metadata(metadata),
        "last_turn": _serialize_turn(last_turn) if last_turn else None,
        "context": context,
    }


@app.get("/api/story/context/{session_id}")
async def get_session_context(
    session_id: str,
    turn_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch a stored context payload for the latest or specified turn."""

    if not session_manager.session_exists(session_id):
        raise _error_response(
            404,
            "session_not_found",
            "Session does not exist",
            session_id,
        )

    context = session_manager.load_turn_context(session_id, turn_id=turn_id)
    if context is None:
        raise _error_response(
            404,
            "context_not_found",
            "No context available for session",
            session_id,
        )

    return context


@app.get("/api/story/history/{session_id}")
async def get_turn_history(
    session_id: str,
    limit: int = 10,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Return a paginated slice of session turn history."""

    if not session_manager.session_exists(session_id):
        raise _error_response(
            404,
            "session_not_found",
            "Session does not exist",
            session_id,
        )

    history = session_manager.get_turn_history_slice(
        session_id,
        limit=limit,
        offset=offset,
    )
    return [_serialize_turn(record) for record in history]


@app.post("/api/story/regenerate", response_model=StoryTurnResponse)
async def regenerate_turn(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
) -> StoryTurnResponse:
    """Regenerate the most recent turn for a session with optional overrides."""

    session_id = request.get("session_id")
    options = request.get("options", {})

    if not session_id:
        raise _error_response(400, "invalid_request", "session_id is required")

    if not session_manager.session_exists(session_id):
        raise _error_response(
            404,
            "session_not_found",
            "Session does not exist",
            session_id,
        )

    last_turn = session_manager.get_last_turn(session_id)
    if not last_turn:
        raise _error_response(
            400,
            "no_turns",
            "Cannot regenerate without an existing turn",
            session_id,
        )

    session_lock = await session_locks.for_session(session_id)
    async with session_lock:
        lore = await get_lore_agent()
        session_manager.update_phase(session_id, "regenerating")

        try:
            story_response, context_snapshot = await _run_turn(
                lore,
                session_id,
                last_turn.user_input,
                options or last_turn.options,
            )
        except Exception as exc:
            LOGGER.exception("Regeneration failed for session %s", session_id)
            session_manager.update_phase(session_id, "error")
            raise _error_response(
                500,
                "regenerate_failed",
                str(exc),
                session_id,
            ) from exc

        new_record = TurnRecord(
            turn_id=context_snapshot["turn_id"],
            user_input=last_turn.user_input,
            response=story_response.model_dump(),
            created_at=datetime.utcnow(),
            options=options or last_turn.options,
        )

        session_manager.replace_last_turn(session_id, new_record)
        background_tasks.add_task(
            session_manager.save_turn_context,
            session_id,
            context_snapshot["turn_id"],
            context_snapshot,
        )

        return story_response


@app.delete("/api/story/session/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    """Delete a session and all associated persisted data."""

    if not session_manager.session_exists(session_id):
        raise _error_response(
            404,
            "session_not_found",
            "Session does not exist",
            session_id,
        )

    session_manager.delete_session(session_id)
    return {"status": "deleted"}


@app.get("/api/story/sessions")
async def list_sessions() -> List[Dict[str, Any]]:
    """List all sessions ordered by most recent activity."""

    sessions = session_manager.list_sessions()
    return [_serialize_metadata(metadata) for metadata in sessions]


@app.websocket("/api/story/stream/{session_id}")
async def session_stream(websocket: WebSocket, session_id: str) -> None:
    """Stream live phase updates for the requested session."""

    if not session_manager.session_exists(session_id):
        await websocket.close(code=4404)
        return

    await websocket.accept()
    queue = await event_dispatcher.subscribe(session_id)
    await websocket.send_json({"type": "connected", "session_id": session_id})

    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        LOGGER.info("WebSocket disconnected for session %s", session_id)
    finally:
        await event_dispatcher.unsubscribe(session_id, queue)


@app.on_event("startup")
async def startup_tasks() -> None:
    """Perform API startup initialization tasks."""

    LOGGER.info("Storyteller API starting up")
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    await get_lore_agent()


@app.on_event("shutdown")
async def shutdown_tasks() -> None:
    """Log API shutdown for observability."""

    LOGGER.info("Storyteller API shutting down")
