"""FastAPI application exposing the NEXUS storyteller interface."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexus.api.session_manager import (
    SessionManager,
    SessionManagerError,
    SessionNotFoundError,
    TurnRecord,
)
from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_schemas import StoryTurnResponse, create_minimal_response


LOGGER = logging.getLogger("nexus.api.storyteller")


class SessionCreateRequest(BaseModel):
    """Payload for creating a new story session."""

    session_name: Optional[str] = Field(default=None)
    initial_context: Optional[str] = Field(default=None)


class SessionCreateResponse(BaseModel):
    """Response returned when a session is created."""

    session_id: str
    created_at: str
    status: str = Field(default="ready")


class StoryTurnRequest(BaseModel):
    """Payload for generating a new story turn."""

    session_id: str
    user_input: str
    options: Dict[str, Any] = Field(default_factory=dict)


class RegenerateRequest(BaseModel):
    """Payload for regenerating the last turn."""

    session_id: str
    options: Dict[str, Any] = Field(default_factory=dict)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_response(
    status_code: int,
    message: str,
    detail: str,
    session_id: Optional[str] = None,
):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": message,
            "detail": detail,
            "session_id": session_id,
        },
    )


class StreamBroker:
    """Fan-out message broker for session WebSocket streams."""

    def __init__(self) -> None:
        self._queues: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._queues.setdefault(session_id, []).append(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            queues = self._queues.get(session_id)
            if not queues:
                return
            if queue in queues:
                queues.remove(queue)
            if not queues:
                self._queues.pop(session_id, None)

    async def publish(self, session_id: str, message: Dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._queues.get(session_id, []))
        if not subscribers:
            return
        for queue in subscribers:
            await queue.put(message)


session_manager = SessionManager()

try:
    lore_agent = LORE()
except Exception:  # pragma: no cover - defensive logging
    LOGGER.exception("Failed to initialize LORE for storyteller API")
    lore_agent = None

lore_lock = asyncio.Lock()
session_locks: Dict[str, asyncio.Lock] = {}
stream_broker = StreamBroker()


def _get_session_lock(session_id: str) -> asyncio.Lock:
    lock = session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        session_locks[session_id] = lock
    return lock


def _ensure_lore_available() -> None:
    if lore_agent is None:
        raise HTTPException(status_code=503, detail="LORE agent unavailable")


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


@app.on_event("startup")
async def startup_event() -> None:
    """Perform lightweight health checks when the API starts."""

    if lore_agent is None:
        LOGGER.warning("Storyteller API running without an active LORE agent")
    session_manager.base_path.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Storyteller API ready. Session directory: %s", session_manager.base_path)


@app.post("/api/story/session/create", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
    metadata = session_manager.create_session(
        session_name=request.session_name,
        initial_context=request.initial_context,
    )
    LOGGER.info("Created story session %s", metadata.session_id)
    return SessionCreateResponse(
        session_id=metadata.session_id,
        created_at=metadata.created_at,
    )


@app.get("/api/story/sessions")
async def list_sessions() -> List[Dict[str, Any]]:
    return session_manager.list_sessions()


@app.get("/api/story/session/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    try:
        return session_manager.get_session_state(session_id)
    except SessionNotFoundError:
        return _error_response(404, "session_not_found", "Session does not exist", session_id)


def _build_context_snapshot(turn_context: Any) -> Dict[str, Any]:
    return {
        "warm_slice": getattr(turn_context, "warm_slice", []),
        "entity_data": getattr(turn_context, "entity_data", {}),
        "retrieved_passages": getattr(turn_context, "retrieved_passages", []),
        "context_payload": getattr(turn_context, "context_payload", {}),
        "token_counts": getattr(turn_context, "token_counts", {}),
        "memory_state": getattr(turn_context, "memory_state", {}),
        "phase_states": getattr(turn_context, "phase_states", {}),
    }


async def _run_turn(
    session_id: str,
    user_input: str,
    options: Dict[str, Any],
    *,
    reuse_turn_id: Optional[str] = None,
) -> StoryTurnResponse:
    _ensure_lore_available()

    await stream_broker.publish(
        session_id,
        {
            "event": "status",
            "status": "processing",
            "timestamp": _utc_now(),
        },
    )

    async with lore_lock:
        response_text = await lore_agent.process_turn(user_input)
        turn_context = getattr(lore_agent, "turn_context", None)

    if turn_context is None:
        raise SessionManagerError("Turn context unavailable after processing")

    story_response = create_minimal_response(response_text)

    turn_id = reuse_turn_id or turn_context.turn_id
    turn_record = TurnRecord(
        turn_id=turn_id,
        timestamp=_utc_now(),
        user_input=user_input,
        response=story_response.model_dump(mode="json"),
        options=options,
        phase_states=turn_context.phase_states,
        memory_state=turn_context.memory_state,
    )

    context_snapshot = _build_context_snapshot(turn_context)

    session_manager.append_turn(session_id, turn_record, context_snapshot=context_snapshot)

    await stream_broker.publish(
        session_id,
        {
            "event": "complete",
            "turn": {
                **story_response.model_dump(mode="json"),
                "turn_id": turn_id,
                "user_input": user_input,
            },
            "timestamp": _utc_now(),
        },
    )

    return story_response


@app.post("/api/story/turn", response_model=StoryTurnResponse)
async def story_turn(request: StoryTurnRequest) -> Any:
    try:
        session_manager.touch_session(request.session_id, phase="processing")
    except SessionNotFoundError:
        return _error_response(404, "session_not_found", "Session does not exist", request.session_id)

    session_lock = _get_session_lock(request.session_id)
    async with session_lock:
        try:
            response = await _run_turn(request.session_id, request.user_input, request.options)
            return response
        except SessionManagerError as exc:
            LOGGER.error("Failed to process turn: %s", exc)
            return _error_response(500, "turn_failed", str(exc), request.session_id)
        except HTTPException as exc:
            return _error_response(
                exc.status_code,
                "service_unavailable",
                str(exc.detail),
                request.session_id,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Unexpected error during turn processing")
            return _error_response(500, "turn_failed", str(exc), request.session_id)


@app.get("/api/story/history/{session_id}")
async def get_history(
    session_id: str,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Any:
    try:
        history = session_manager.get_history(session_id, limit=limit, offset=offset)
        return history
    except SessionNotFoundError:
        return _error_response(404, "session_not_found", "Session does not exist", session_id)
    except SessionManagerError as exc:
        return _error_response(400, "invalid_request", str(exc), session_id)


@app.get("/api/story/context/{session_id}")
async def get_context(session_id: str) -> Any:
    try:
        return session_manager.load_latest_context(session_id)
    except SessionNotFoundError:
        return _error_response(404, "session_not_found", "Session does not exist", session_id)
    except SessionManagerError as exc:
        return _error_response(404, "context_missing", str(exc), session_id)


@app.post("/api/story/regenerate", response_model=StoryTurnResponse)
async def regenerate_turn(request: RegenerateRequest) -> Any:
    try:
        session_manager.touch_session(request.session_id, phase="regenerating")
    except SessionNotFoundError:
        return _error_response(404, "session_not_found", "Session does not exist", request.session_id)

    history = session_manager.get_history(request.session_id, limit=1, offset=0)
    if not history:
        return _error_response(400, "no_history", "No turns available to regenerate", request.session_id)

    last_turn = history[0]
    user_input = last_turn.get("user_input", "")
    previous_turn_id = last_turn.get("turn_id")

    if not user_input:
        return _error_response(400, "invalid_history", "Last turn is missing user input", request.session_id)

    session_lock = _get_session_lock(request.session_id)
    async with session_lock:
        _ensure_lore_available()

        await stream_broker.publish(
            request.session_id,
            {
                "event": "status",
                "status": "regenerating",
                "timestamp": _utc_now(),
            },
        )

        try:
            async with lore_lock:
                response_text = await lore_agent.process_turn(user_input)
                turn_context = getattr(lore_agent, "turn_context", None)
        except HTTPException as exc:
            return _error_response(
                exc.status_code,
                "service_unavailable",
                str(exc.detail),
                request.session_id,
            )

        if turn_context is None:
            return _error_response(500, "turn_failed", "Turn context unavailable after regeneration", request.session_id)

        story_response = create_minimal_response(response_text)
        turn_id = previous_turn_id or turn_context.turn_id
        turn_record = TurnRecord(
            turn_id=turn_id,
            timestamp=_utc_now(),
            user_input=user_input,
            response=story_response.model_dump(mode="json"),
            options=request.options,
            phase_states=turn_context.phase_states,
            memory_state=turn_context.memory_state,
        )
        context_snapshot = _build_context_snapshot(turn_context)

        session_manager.replace_last_turn(
            request.session_id,
            turn_record,
            context_snapshot=context_snapshot,
        )

        await stream_broker.publish(
            request.session_id,
            {
                "event": "complete",
                "turn": {
                    **story_response.model_dump(mode="json"),
                    "turn_id": turn_id,
                    "user_input": user_input,
                },
                "timestamp": _utc_now(),
                "regenerated": True,
            },
        )

        return story_response


@app.delete("/api/story/session/{session_id}")
async def delete_session(session_id: str) -> Any:
    try:
        session_manager.delete_session(session_id)
        LOGGER.info("Deleted story session %s", session_id)
        return {"status": "deleted"}
    except SessionNotFoundError:
        return _error_response(404, "session_not_found", "Session does not exist", session_id)


@app.websocket("/api/story/stream/{session_id}")
async def stream_session(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        _ = session_manager.load_metadata(session_id)
    except SessionNotFoundError:
        await websocket.send_json(
            {"event": "error", "detail": "Session does not exist", "session_id": session_id}
        )
        await websocket.close(code=4404)
        return

    queue = await stream_broker.subscribe(session_id)
    await websocket.send_json({"event": "connected", "session_id": session_id, "timestamp": _utc_now()})

    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        LOGGER.info("Stream disconnected for session %s", session_id)
    finally:
        await stream_broker.unsubscribe(session_id, queue)


__all__ = ["app"]

