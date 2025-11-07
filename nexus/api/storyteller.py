"""FastAPI application exposing the NEXUS Storyteller interface."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from nexus.api.session_manager import SessionManager, SessionNotFoundError, SessionTurn
from nexus.agents.lore.lore import LORE
from nexus.agents.lore.logon_schemas import (
    StoryTurnResponse,
    create_minimal_response,
    validate_story_turn_response,
)

logger = logging.getLogger("nexus.api.storyteller")

ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
]


class CreateSessionRequest(BaseModel):
    """Request body for creating a new story session."""

    session_name: Optional[str] = Field(default=None)
    initial_context: Optional[str] = Field(default=None)


class CreateSessionResponse(BaseModel):
    """Response payload for session creation."""

    session_id: str
    created_at: datetime
    status: str = "ready"


class StoryTurnRequest(BaseModel):
    """Request payload for executing a story turn."""

    session_id: str
    user_input: str
    options: Optional[Dict[str, Any]] = None


class SessionMetadataResponse(BaseModel):
    """Serializable view of session metadata."""

    session_id: str
    session_name: Optional[str]
    created_at: datetime
    last_accessed: datetime
    turn_count: int
    current_phase: str
    initial_context: Optional[str] = None


class TurnRecord(BaseModel):
    """Serializable representation of a stored turn."""

    turn_id: str
    user_input: str
    response: Dict[str, Any]
    created_at: datetime
    options: Dict[str, Any] = Field(default_factory=dict)
    context_path: Optional[str] = None


class SessionStateResponse(BaseModel):
    """Full session state response."""

    metadata: SessionMetadataResponse
    last_turn: Optional[TurnRecord] = None


class TurnHistoryResponse(BaseModel):
    """Response for history requests."""

    turns: List[TurnRecord]
    total: int


class RegenerateRequest(BaseModel):
    """Request payload for regenerating the last narrative."""

    session_id: str
    options: Optional[Dict[str, Any]] = None


class DeleteSessionResponse(BaseModel):
    """Response payload for session deletion."""

    status: str = "deleted"


def _format_error(error: str, detail: str, session_id: Optional[str]) -> Dict[str, Any]:
    """Build the standard error response shape."""

    return {"error": error, "detail": detail, "session_id": session_id}


def _coerce_story_response(payload: Any) -> StoryTurnResponse:
    """Coerce arbitrary payloads into a StoryTurnResponse."""

    if isinstance(payload, StoryTurnResponse):
        return payload
    if isinstance(payload, dict):
        try:
            return validate_story_turn_response(payload)
        except Exception:  # pragma: no cover - fallback path
            logger.debug("Payload validation failed; using minimal response")
            narrative = payload.get("narrative") or payload.get("text") or str(payload)
            return create_minimal_response(str(narrative))
    return create_minimal_response(str(payload))


def _to_turn_record(turn: SessionTurn) -> TurnRecord:
    """Convert a stored session turn into an API record."""

    return TurnRecord(
        turn_id=turn.turn_id,
        user_input=turn.user_input,
        response=turn.response,
        created_at=turn.created_at,
        options=turn.options or {},
        context_path=turn.context_path,
    )


class LoreProvider:
    """Lazily instantiate the LORE agent for request handling."""

    def __init__(self) -> None:
        self._instance: Optional[LORE] = None
        self._lock = asyncio.Lock()

    async def get(self) -> LORE:
        """Return a cached LORE instance, creating it if necessary."""

        if self._instance is not None:
            return self._instance

        async with self._lock:
            if self._instance is None:
                loop = asyncio.get_running_loop()
                self._instance = await loop.run_in_executor(None, LORE)
        return self._instance


class SessionStreamManager:
    """Manage websocket connections for session streaming."""

    def __init__(self) -> None:
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Register a websocket connection for a session."""

        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(session_id, []).append(websocket)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove a websocket from the active connection list."""

        async with self._lock:
            connections = self._connections.get(session_id)
            if not connections:
                return
            if websocket in connections:
                connections.remove(websocket)
            if not connections:
                self._connections.pop(session_id, None)

    async def broadcast(self, session_id: str, payload: Dict[str, Any]) -> None:
        """Send an event to all websocket listeners for a session."""

        async with self._lock:
            connections = list(self._connections.get(session_id, []))

        for connection in connections:
            try:
                await connection.send_json(payload)
            except Exception as exc:  # pragma: no cover - network variability
                logger.debug("Websocket broadcast failed: %s", exc)


session_manager = SessionManager()
lore_provider = LoreProvider()
stream_manager = SessionStreamManager()

app = FastAPI(title="NEXUS Storyteller API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_session_manager() -> SessionManager:
    """FastAPI dependency returning the session manager."""

    return session_manager


async def get_lore() -> LORE:
    """FastAPI dependency returning the LORE agent."""

    return await lore_provider.get()


@app.on_event("startup")
async def _startup_tasks() -> None:
    """Perform startup diagnostics before serving requests."""

    logger.info("Storyteller API starting - verifying session storage")
    for metadata in await session_manager.list_sessions():
        if metadata.current_phase not in {"idle", "error"}:
            await session_manager.update_metadata(
                metadata.session_id, current_phase="idle", last_accessed=metadata.last_accessed
            )
    logger.info("Session store ready (%s sessions)", len(await session_manager.list_sessions()))


@app.post("/api/story/session/create", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> CreateSessionResponse:
    """Create a new story session and persist metadata."""

    state = await manager.create_session(
        session_name=request.session_name,
        initial_context=request.initial_context,
    )
    metadata = state.metadata
    return CreateSessionResponse(
        session_id=metadata.session_id,
        created_at=metadata.created_at,
        status="ready",
    )


@app.get("/api/story/sessions", response_model=List[SessionMetadataResponse])
async def list_sessions(
    manager: SessionManager = Depends(get_session_manager),
) -> List[SessionMetadataResponse]:
    """List all available sessions."""

    sessions = await manager.list_sessions()
    return [
        SessionMetadataResponse(
            session_id=item.session_id,
            session_name=item.session_name,
            created_at=item.created_at,
            last_accessed=item.last_accessed,
            turn_count=item.turn_count,
            current_phase=item.current_phase,
            initial_context=item.initial_context,
        )
        for item in sessions
    ]


@app.get("/api/story/session/{session_id}", response_model=SessionStateResponse)
async def get_session_state(
    session_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionStateResponse:
    """Retrieve the full session state including latest turn."""

    try:
        state = await manager.load_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_format_error("not_found", str(exc), session_id)) from exc

    metadata = state.metadata
    metadata_response = SessionMetadataResponse(
        session_id=metadata.session_id,
        session_name=metadata.session_name,
        created_at=metadata.created_at,
        last_accessed=metadata.last_accessed,
        turn_count=metadata.turn_count,
        current_phase=metadata.current_phase,
        initial_context=metadata.initial_context,
    )

    last_turn = _to_turn_record(state.turns[-1]) if state.turns else None

    return SessionStateResponse(metadata=metadata_response, last_turn=last_turn)


@app.get("/api/story/history/{session_id}", response_model=TurnHistoryResponse)
async def get_history(
    session_id: str,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    manager: SessionManager = Depends(get_session_manager),
) -> TurnHistoryResponse:
    """Return paginated turn history for a session."""

    try:
        turns = await manager.load_turn_history(session_id, limit=limit, offset=offset)
        state = await manager.load_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_format_error("not_found", str(exc), session_id)) from exc

    return TurnHistoryResponse(
        turns=[_to_turn_record(turn) for turn in turns],
        total=state.metadata.turn_count,
    )


@app.get("/api/story/context/{session_id}")
async def get_context(
    session_id: str,
    turn_id: Optional[str] = None,
    manager: SessionManager = Depends(get_session_manager),
) -> Dict[str, Any]:
    """Return the stored context payload for debugging."""

    try:
        context = await manager.load_context(session_id, turn_id=turn_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_format_error("not_found", str(exc), session_id)) from exc

    return context


@app.post("/api/story/turn", response_model=StoryTurnResponse)
async def story_turn(
    request: StoryTurnRequest,
    background_tasks: BackgroundTasks,
    manager: SessionManager = Depends(get_session_manager),
    lore: LORE = Depends(get_lore),
) -> StoryTurnResponse:
    """Execute a full story turn and persist the results."""

    try:
        await manager.update_metadata(request.session_id, current_phase="processing", last_accessed=datetime.now(timezone.utc))
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_format_error("not_found", str(exc), request.session_id)) from exc

    await stream_manager.broadcast(
        request.session_id,
        {"event": "phase", "phase": "processing", "timestamp": datetime.now(timezone.utc).isoformat()},
    )

    try:
        result = await lore.process_turn(request.user_input)
    except Exception as exc:
        await manager.update_metadata(request.session_id, current_phase="error")
        await stream_manager.broadcast(
            request.session_id,
            {
                "event": "error",
                "detail": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        raise HTTPException(
            status_code=500,
            detail=_format_error("turn_failed", str(exc), request.session_id),
        ) from exc

    story_response = _coerce_story_response(result)

    context_payload: Dict[str, Any] = {}
    turn_context = getattr(lore, "turn_context", None)
    if turn_context is not None:
        context_payload = {
            "phase_states": turn_context.phase_states,
            "warm_slice": turn_context.warm_slice,
            "entity_data": turn_context.entity_data,
            "retrieved_passages": turn_context.retrieved_passages,
            "context_payload": turn_context.context_payload,
            "memory_state": turn_context.memory_state,
            "token_counts": turn_context.token_counts,
            "authorial_directives": turn_context.authorial_directives,
        }

    await manager.append_turn(
        request.session_id,
        user_input=request.user_input,
        response=story_response.model_dump(),
        options=request.options,
        context_payload=context_payload,
    )

    background_tasks.add_task(manager.finalize_turn, request.session_id)

    await stream_manager.broadcast(
        request.session_id,
        {
            "event": "complete",
            "turn": story_response.model_dump(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return story_response


@app.post("/api/story/regenerate", response_model=StoryTurnResponse)
async def regenerate_turn(
    request: RegenerateRequest,
    background_tasks: BackgroundTasks,
    manager: SessionManager = Depends(get_session_manager),
    lore: LORE = Depends(get_lore),
) -> StoryTurnResponse:
    """Regenerate the last turn with updated options."""

    try:
        last_turn = await manager.get_last_turn(request.session_id)
    except (SessionNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=_format_error("not_found", str(exc), request.session_id)) from exc

    await manager.update_metadata(request.session_id, current_phase="regenerating")
    await stream_manager.broadcast(
        request.session_id,
        {"event": "phase", "phase": "regenerating", "timestamp": datetime.now(timezone.utc).isoformat()},
    )

    try:
        result = await lore.process_turn(last_turn.user_input)
    except Exception as exc:
        await manager.update_metadata(request.session_id, current_phase="error")
        raise HTTPException(
            status_code=500,
            detail=_format_error("regenerate_failed", str(exc), request.session_id),
        ) from exc

    story_response = _coerce_story_response(result)

    context_payload: Dict[str, Any] = {}
    turn_context = getattr(lore, "turn_context", None)
    if turn_context is not None:
        context_payload = {
            "phase_states": turn_context.phase_states,
            "warm_slice": turn_context.warm_slice,
            "entity_data": turn_context.entity_data,
            "retrieved_passages": turn_context.retrieved_passages,
            "context_payload": turn_context.context_payload,
            "memory_state": turn_context.memory_state,
            "token_counts": turn_context.token_counts,
            "authorial_directives": turn_context.authorial_directives,
        }

    await manager.replace_last_turn(
        request.session_id,
        user_input=last_turn.user_input,
        response=story_response.model_dump(),
        options=request.options or last_turn.options,
        context_payload=context_payload,
    )

    background_tasks.add_task(manager.finalize_turn, request.session_id)

    await stream_manager.broadcast(
        request.session_id,
        {
            "event": "complete",
            "turn": story_response.model_dump(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return story_response


@app.delete("/api/story/session/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(
    session_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> DeleteSessionResponse:
    """Delete a session and all persisted data."""

    try:
        await manager.delete_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_format_error("not_found", str(exc), session_id)) from exc
    return DeleteSessionResponse()


@app.websocket("/api/story/stream/{session_id}")
async def stream_turns(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for session event streaming."""

    await stream_manager.connect(session_id, websocket)
    await websocket.send_json({"event": "connected", "session_id": session_id})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await stream_manager.disconnect(session_id, websocket)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.debug("Websocket error: %s", exc)
        await stream_manager.disconnect(session_id, websocket)

