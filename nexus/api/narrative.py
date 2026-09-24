"""
FastAPI endpoints for live narrative turns with incubator support
"""

from nexus.database import connection_kwargs

import asyncio
import frontmatter
import json
import logging
import os
from contextlib import asynccontextmanager
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Literal
from pathlib import Path

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    Query,
    WebSocket,
    WebSocketDisconnect,
    BackgroundTasks,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.lore import LORE
from nexus.agents.orrery.player_identity import (
    PlayerIdentityNotEstablishedError,
    canonical_player_character_id,
)
from nexus.api.lore_adapter import (
    response_to_incubator,
    validate_incubator_data,
    compute_raw_text,
)
from nexus.api.choice_handling import (
    normalize_choice_object,
    resolve_choice_response,
    validate_choice_index,
)
from nexus.api.chunk_workflow import (
    ChunkWorkflow,
    get_default_workflow,
)
from nexus.api.conversations import ConversationsClient
from nexus.api.new_story_flow import (
    start_setup,
    resume_setup,
    record_drafts,
    reset_setup,
    activate_slot,
)
from nexus.api.slot_mutations import require_writable_slot
from nexus.api.slot_utils import all_slots, slot_dbname, require_slot_dbname
from nexus.api.db_pool import get_connection
from nexus.api.narrative_generation import (
    generate_narrative_async,
    get_chunk_info,
    write_to_incubator,
    generate_bootstrap_narrative,
)
from nexus.api.narrative_lease import (
    abandon_generation,
    acquire_generation_lease,
    bind_generation_parent,
    claim_parent_embedding,
    discard_generation,
    read_generation_session,
)
from nexus.api.config_utils import (
    get_generation_lease_timeout_seconds,
    get_max_choice_text_length,
)
from nexus.api.asset_endpoints import router as asset_router
from nexus.api.reader_endpoints import router as reader_router
from nexus.api.local_models_endpoints import router as local_models_router
from nexus.api.secrets_endpoints import router as secrets_router
from nexus.api.settings_endpoints import router as settings_router
from nexus.api.preferences_endpoints import router as preferences_router
from nexus.api.slot_endpoints import router as slot_router
from nexus.api.setup_endpoints import router as setup_router
from nexus.api.runtime_status import register_runtime_status
from nexus.api.static_ui import mount_ui
from nexus.api.wizard_chat import router as wizard_chat_router
from nexus.config import get_gateway_cors_allowed_origins

logger = logging.getLogger("nexus.api.narrative")


async def recover_active_choice_on_startup() -> None:
    """Reconcile the active slot before accepting requests."""
    from nexus.api.choice_recovery import recover_active_slot_choice
    from nexus.api.slot_utils import get_active_slot

    if os.environ.get("NEXUS_SLOT") is not None:
        await asyncio.to_thread(recover_active_slot_choice, get_active_slot())


@asynccontextmanager
async def gateway_lifespan(app: FastAPI):
    """Recover the active slot and own its deferred-work loop until shutdown."""
    from nexus.api.choice_recovery import recover_active_slot_choice
    from nexus.api.slot_utils import get_active_slot
    from nexus.jobs.scheduler import SlotScheduler

    scheduler = None
    if os.environ.get("NEXUS_SLOT") is not None:
        slot = get_active_slot()
        await recover_active_choice_on_startup()
        scheduler = SlotScheduler(slot)
        await asyncio.to_thread(scheduler.start)
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            await asyncio.to_thread(scheduler.stop)
        app.state.scheduler = None


app = FastAPI(title="NEXUS Narrative API", version="1.0.0", lifespan=gateway_lifespan)


def wake_scheduler(slot: Optional[int]) -> None:
    """Wake the active slot owner; other gateways recover on their own clock."""
    from nexus.api.slot_utils import get_active_slot

    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None and scheduler.slot == (slot or get_active_slot()):
        scheduler.wakeup.set()


# Configure credentialed CORS from the validated gateway allowlist.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_gateway_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def _validation_error_without_echoed_input(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return validation errors without echoing the submitted value.

    FastAPI's default handler serializes the offending ``input`` (and any
    ``ctx``) back into the 422 body. For a body that carries a secret — e.g.
    a mistyped field on PUT /api/secrets/{provider} — that reflects the
    plaintext key straight into the HTTP response, shell scrollback, and
    client logs. Strip both keys from every error entry so no submitted value
    is ever mirrored back, on any endpoint.
    """
    sanitized = [
        {key: value for key, value in error.items() if key not in ("input", "ctx")}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": sanitized})


# Include modular routers
app.include_router(settings_router)
app.include_router(preferences_router)
app.include_router(secrets_router)
app.include_router(slot_router)
app.include_router(setup_router)
app.include_router(wizard_chat_router)
app.include_router(reader_router)
app.include_router(asset_router)
app.include_router(local_models_router)


def _include_orrery_dev_router(target_app: FastAPI, settings: Any = None) -> None:
    """Register the audit-dashboard router iff [orrery.dashboard] enabled.

    Server-side gate: the client bundle's import.meta.env.DEV check cannot
    protect the API once the gateway is exposed beyond localhost (issue
    #415). Evaluated once at import — flag changes need a gateway restart.
    ``settings`` is injectable so both arms of the gate are testable.
    """

    if settings is None:
        from nexus.config import load_settings as _load_typed_settings

        settings = _load_typed_settings()

    orrery_settings = settings.orrery
    if orrery_settings is not None and orrery_settings.dashboard.enabled:
        from nexus.api.orrery_dev_endpoints import router as orrery_dev_router

        target_app.include_router(orrery_dev_router)


_include_orrery_dev_router(app)


def _include_backstage_router(target_app: FastAPI, settings: Any = None) -> None:
    """Register Backstage iff the shared Orrery dashboard gate is enabled."""

    if settings is None:
        from nexus.config import load_settings as _load_typed_settings

        settings = _load_typed_settings()

    orrery_settings = settings.orrery
    if orrery_settings is not None and orrery_settings.dashboard.enabled:
        if any(
            str(getattr(route, "path", "")).startswith("/api/dev/backstage")
            for route in target_app.routes
        ):
            return
        from nexus.api.backstage_endpoints import router as backstage_router

        target_app.include_router(backstage_router)


_include_backstage_router(app)


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str, slot: int):
        for connection in tuple(self.active_connections):
            if connection.query_params.get("slot") != str(slot):
                continue
            try:
                await connection.send_text(message)
            except (RuntimeError, WebSocketDisconnect, OSError):
                logger.warning(
                    "Dropping disconnected narrative socket for slot %s", slot
                )
                self.disconnect(connection)

    async def send_progress(self, session_id: str, status: str, data: Dict = None):
        """Send progress update for a specific session"""
        progress = {
            "session_id": session_id,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "data": data or {},
        }
        slot = (data or {}).get("slot")
        if slot is None:
            raise ValueError("Narrative progress requires an explicit slot")
        progress["slot"] = slot
        await self.broadcast(json.dumps(progress), slot)


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
    return psycopg2.connect(**connection_kwargs(dbname))


def load_settings():
    """Load settings using centralized config loader."""
    from nexus.config import load_settings_as_dict

    return load_settings_as_dict()


# Import schemas from narrative_schemas.py
from nexus.api.narrative_schemas import (
    ContinueNarrativeRequest,
    ContinueNarrativeResponse,
    GenerationLeaseConflictResponse,
    RegenerateNarrativeRequest,
    ApproveNarrativeRequest,
    ApproveNarrativeByIdRequest,
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


def _has_player_response_input(request: ContinueNarrativeRequest) -> bool:
    """Return whether a continue request carries player response input."""
    return (
        bool(request.user_text.strip())
        or request.choice is not None
        or request.accept_fate
    )


def _persist_chunk_response(
    cur,
    *,
    is_incubator: bool,
    chunk_id: Optional[int],
    storyteller_text: str,
    choice_object: Optional[Dict[str, Any]],
    choice_text: str,
    incubator_session_id: Optional[str] = None,
) -> str:
    """Persist resolved player response fields for a chunk."""
    raw_text = compute_raw_text(storyteller_text, choice_object, choice_text)

    if is_incubator:
        cur.execute(
            """
            UPDATE incubator
            SET choice_object = %s,
                choice_text = %s
            WHERE session_id = %s
            """,
            (
                json.dumps(choice_object) if choice_object else None,
                choice_text,
                incubator_session_id,
            ),
        )
        if cur.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="Incubator session mismatch; concurrent generation may have replaced it.",
            )
    else:
        cur.execute(
            """
            UPDATE narrative_chunks
            SET choice_object = %s,
                choice_text = %s,
                raw_text = %s
            WHERE id = %s
            """,
            (
                json.dumps(choice_object) if choice_object else None,
                choice_text,
                raw_text,
                chunk_id,
            ),
        )
        if cur.rowcount != 1:
            raise HTTPException(
                status_code=404,
                detail=f"Chunk {chunk_id} not found",
            )

    return raw_text


def _record_player_response_for_chunk(
    *,
    slot: Optional[int],
    chunk_id: Optional[int],
    user_text: str,
    choice: Optional[int],
    accept_fate: bool,
    require_response: bool,
    connection: Any = None,
    incubator_session_id: Optional[str] = None,
) -> str:
    """
    Resolve and persist the player's response for an incubator/committed chunk.

    Returns:
        The response text that should be sent into the next generation.
    """
    owns_connection = connection is None
    if owns_connection:
        try:
            conn = get_db_connection(slot)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        conn = connection

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT chunk_id AS id, storyteller_text, choice_object,
                       choice_text, session_id
                FROM incubator
                WHERE (%s IS NOT NULL AND id = TRUE)
                   OR (%s IS NULL AND chunk_id = %s)
                FOR UPDATE
                """,
                (incubator_session_id, incubator_session_id, chunk_id),
            )
            chunk = cur.fetchone()
            if (
                chunk is not None
                and incubator_session_id is not None
                and str(chunk["session_id"]) != incubator_session_id
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": f"Incubator session mismatch for chunk {chunk_id}.",
                        "expected_session_id": incubator_session_id,
                        "actual_session_id": str(chunk["session_id"]),
                    },
                )
            is_incubator = chunk is not None
            if incubator_session_id is not None and not is_incubator:
                raise HTTPException(
                    status_code=409,
                    detail="Pending generation session no longer owns the incubator",
                )

            if not chunk:
                cur.execute(
                    """
                    SELECT id, storyteller_text, choice_object, choice_text
                    FROM narrative_chunks
                    WHERE id = %s
                    """,
                    (chunk_id,),
                )
                chunk = cur.fetchone()

            if not chunk:
                raise HTTPException(
                    status_code=404, detail=f"Chunk {chunk_id} not found"
                )

            existing_choice_text = (chunk.get("choice_text") or "").strip()
            try:
                choice_object = normalize_choice_object(chunk.get("choice_object"))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            has_new_input = bool(user_text.strip()) or choice is not None or accept_fate

            if existing_choice_text:
                if has_new_input:
                    try:
                        resolved = resolve_choice_response(
                            choice_object,
                            choice=choice,
                            user_text=user_text,
                            accept_fate=accept_fate,
                        )
                    except ValueError as exc:
                        raise HTTPException(status_code=400, detail=str(exc)) from exc
                    if resolved.choice_text != existing_choice_text:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Choice already selected for chunk {chunk_id}.",
                        )
                return existing_choice_text

            has_unresolved_choices = bool(choice_object and choice_object["presented"])
            if (
                not has_new_input
                and not require_response
                and not has_unresolved_choices
            ):
                return user_text

            if not has_new_input:
                if has_unresolved_choices:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Current chunk has unresolved choices; provide choice, "
                            "non-empty user_text, or accept_fate."
                        ),
                    )
                raise HTTPException(status_code=400, detail="No input provided")

            try:
                resolved = resolve_choice_response(
                    choice_object,
                    choice=choice,
                    user_text=user_text,
                    accept_fate=accept_fate,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            max_choice_text_length = get_max_choice_text_length()
            if len(resolved.choice_text) > max_choice_text_length:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Selection text too long ({len(resolved.choice_text)} "
                        f"chars). Max: {max_choice_text_length}"
                    ),
                )

            _persist_chunk_response(
                cur,
                is_incubator=is_incubator,
                chunk_id=chunk_id,
                storyteller_text=chunk.get("storyteller_text") or "",
                choice_object=resolved.choice_object,
                choice_text=resolved.choice_text,
                incubator_session_id=str(chunk["session_id"]) if is_incubator else None,
            )

        if owns_connection:
            conn.commit()
        return resolved.choice_text

    except HTTPException:
        if owns_connection:
            conn.rollback()
        raise
    except Exception as exc:
        if owns_connection:
            conn.rollback()
        logger.error("Error recording player response for chunk %s: %s", chunk_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if owns_connection:
            conn.close()


def _trigger_locked_chunk_embedding(
    *, slot: Optional[int], parent_chunk_id: int
) -> None:
    """
    Embed every locked chunk older than parent_chunk_id.

    Continuing from chunk N creates a provisional successor, leaving chunk N
    undoable while every committed chunk before it is locked and must be
    embedded ("embedded == ironman"). Chunk ids are NOT contiguous: failed commits
    historically consumed ids, and migration 078 preserves gaps left by retired
    Retrograde summary rows. The old single-id ``parent - 1`` arithmetic
    therefore silently skipped playable chunks across those gaps.
    This catch-up form embeds every unembedded locked chunk except the
    intentionally unembedded Retrograde prologue anchor, healing any
    previously skipped chunk on the next turn.
    """
    if parent_chunk_id <= 1:
        return

    try:
        dbname = require_slot_dbname(slot=slot)
    except Exception as exc:
        logger.warning(
            "Skipping locked chunk embedding before chunk %s: %s",
            parent_chunk_id,
            exc,
        )
        return

    try:
        from nexus.agents.orrery.retrograde_markers import (
            RETROGRADE_PROLOGUE_MARKER,
        )

        with get_connection(dbname, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id
                    FROM narrative_chunks
                    WHERE id < %s
                      AND embedding_generated_at IS NULL
                      AND NOT (
                          COALESCE(authorial_directives, '[]'::jsonb)
                          @> %s::jsonb
                      )
                    ORDER BY id
                    """,
                    (parent_chunk_id, json.dumps([RETROGRADE_PROLOGUE_MARKER])),
                )
                locked_chunk_ids = [row["id"] for row in cur.fetchall()]

        if not locked_chunk_ids:
            logger.info(
                "No locked chunks pending embedding before chunk %s in %s",
                parent_chunk_id,
                dbname,
            )
            return

        workflow = ChunkWorkflow(dbname)
        for locked_chunk_id in locked_chunk_ids:
            job_id = workflow.trigger_embedding_generation(locked_chunk_id)
            if job_id:
                logger.info(
                    "Generated embeddings for locked chunk %s in %s (%s)",
                    locked_chunk_id,
                    dbname,
                    job_id,
                )
            else:
                logger.warning(
                    "Embedding generation did not complete for locked chunk %s "
                    "in %s",
                    locked_chunk_id,
                    dbname,
                )
    except Exception as exc:
        logger.error(
            "Error embedding locked chunks before %s for slot %s: %s",
            parent_chunk_id,
            slot,
            exc,
        )


def _acquire_generation_owner(
    *, slot: Optional[int], session_id: str, operation: str
) -> None:
    """Acquire the durable slot lease or raise the documented 409."""
    conn = get_db_connection(slot)
    try:
        conflict = acquire_generation_lease(
            conn,
            session_id=session_id,
            operation=operation,
            stale_timeout_seconds=get_generation_lease_timeout_seconds(),
        )
    finally:
        conn.close()
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Another narrative generation owns this slot.",
                "active_session_id": conflict.active_session_id,
            },
        )


def _bind_generation_owner(
    *,
    slot: Optional[int],
    session_id: str,
    parent_chunk_id: int,
    claim_embedding: bool,
) -> bool:
    """Bind the resolved parent and optionally claim its embedding trigger."""
    conn = get_db_connection(slot)
    try:
        bind_generation_parent(
            conn,
            session_id=session_id,
            parent_chunk_id=parent_chunk_id,
        )
        if claim_embedding:
            return claim_parent_embedding(
                conn,
                session_id=session_id,
                parent_chunk_id=parent_chunk_id,
            )
        return False
    finally:
        conn.close()


def _abandon_generation_owner(
    *,
    slot: Optional[int],
    session_id: str,
    error: str,
    error_class: str = "GenerationError",
) -> None:
    """Release a route-owned lease after a pre-scheduling failure."""
    conn = get_db_connection(slot)
    try:
        abandon_generation(
            conn, session_id=session_id, error=error, error_class=error_class
        )
    finally:
        conn.close()


def _abandon_unscheduled_generation_owner(
    *,
    slot: Optional[int],
    session_id: str,
    error: str,
    error_class: str = "GenerationError",
) -> None:
    """Best-effort cleanup for a route that never scheduled its generator."""

    try:
        _abandon_generation_owner(
            slot=slot,
            session_id=session_id,
            error=error,
            error_class=error_class,
        )
    except Exception as release_exc:
        logger.error(
            "Failed to abandon generation lease %s: %s",
            session_id,
            release_exc,
        )


def _resolve_and_approve_pending_sync(
    *,
    slot: Optional[int],
    session_id: str,
    chunk_id: Optional[int],
    user_text: str,
    choice: Optional[int],
    accept_fate: bool,
    warning_sink: Optional[List[Dict[str, Any]]] = None,
) -> tuple[str, int]:
    """Resolve and approve a pending choice with worker-owned connection life."""

    from nexus.api.commit_handler_sync import commit_incubator_to_database_sync

    conn = get_db_connection(slot)
    resolved_user_text: str
    approved_chunk_id: int
    try:
        resolved_user_text = _record_player_response_for_chunk(
            slot=slot,
            chunk_id=chunk_id,
            user_text=user_text,
            choice=choice,
            accept_fate=accept_fate,
            require_response=True,
            connection=conn,
            incubator_session_id=session_id,
        )
        if warning_sink is None:
            approved_chunk_id = commit_incubator_to_database_sync(
                conn, session_id, slot
            )
        else:
            approved_chunk_id = commit_incubator_to_database_sync(
                conn,
                session_id,
                slot,
                warning_sink=warning_sink,
            )
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        logger.error("Failed to commit narrative: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to commit narrative: {str(exc)}",
        ) from exc
    finally:
        conn.close()

    wake_scheduler(slot)
    return resolved_user_text, approved_chunk_id


async def _resolve_and_approve_pending(
    *,
    slot: Optional[int],
    session_id: str,
    chunk_id: Optional[int],
    user_text: str,
    choice: Optional[int],
    accept_fate: bool,
    background_tasks: BackgroundTasks,
) -> tuple[str, int, List[Dict[str, Any]]]:
    """Resolve and approve without exposing the worker connection to cancellation."""

    commit_warnings: List[Dict[str, Any]] = []
    resolved_user_text, approved_chunk_id = await asyncio.to_thread(
        _resolve_and_approve_pending_sync,
        slot=slot,
        session_id=session_id,
        chunk_id=chunk_id,
        user_text=user_text,
        choice=choice,
        accept_fate=accept_fate,
        warning_sink=commit_warnings,
    )
    return resolved_user_text, approved_chunk_id, commit_warnings


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "narrative_api"}


@app.get("/api/config/models")
async def get_config_models():
    """Get UI-visible API models with provider info from nexus.toml.

    Providers flagged ``ui_visible = false`` in the api_models registry
    (the TEST mock server) are omitted here; backend and CLI callers use
    the unfiltered loader functions directly.
    """
    from nexus.config.loader import get_all_api_models, get_api_models_by_provider

    return {
        "models": get_all_api_models(ui_only=True),
        "by_provider": get_api_models_by_provider(ui_only=True),
    }


@app.post(
    "/api/narrative/continue",
    response_model=ContinueNarrativeResponse,
    responses={
        409: {
            "model": GenerationLeaseConflictResponse,
            "description": "Another generation currently owns the slot",
        }
    },
)
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
    require_writable_slot(request.slot)
    if request.choice is not None and request.accept_fate:
        raise HTTPException(
            status_code=400,
            detail="Cannot provide both choice and accept_fate",
        )
    if request.model is not None:
        from nexus.config.story_model import resolve_story_model

        try:
            resolve_story_model("skald", override=request.model)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if request.model and request.slot is None:
        raise HTTPException(
            status_code=400,
            detail="Model override requires a slot to persist the selection.",
        )

    resolved_user_text = request.user_text
    state = None
    if request.slot is not None:
        from nexus.api.slot_state import get_slot_state

        state = get_slot_state(request.slot)
        if state.is_wizard_mode:
            raise HTTPException(
                status_code=400,
                detail="Slot is in wizard mode. Use /api/story/new/chat for wizard.",
            )

    if request.session_id is not None:
        pending = state.narrative_state if state is not None else None
        if (
            request.chunk_id is not None
            or pending is None
            or not pending.has_pending
            or pending.session_id != request.session_id
        ):
            raise HTTPException(status_code=409, detail="Pending session changed")

    session_id = str(uuid.uuid4())
    _acquire_generation_owner(
        slot=request.slot,
        session_id=session_id,
        operation="continue",
    )
    scheduled = False
    accept_warnings: List[Dict[str, Any]] = []
    failure_class = "GenerationError"
    failure_reason = "Narrative request ended before generation was scheduled."
    try:
        if request.chunk_id is None and state is not None:
            if state.narrative_state is not None:
                narrative_state = state.narrative_state
                if narrative_state.has_pending:
                    if narrative_state.session_id is None:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                "Slot has pending incubator content that must be "
                                "approved before continuing."
                            ),
                        )
                    logger.info(
                        "Auto-approving pending incubator session %s for slot %s",
                        narrative_state.session_id,
                        request.slot,
                    )
                    resolved_user_text, approved_chunk_id, accept_warnings = (
                        await _resolve_and_approve_pending(
                            slot=request.slot,
                            session_id=narrative_state.session_id,
                            chunk_id=narrative_state.current_chunk_id,
                            user_text=request.user_text,
                            choice=request.choice,
                            accept_fate=request.accept_fate,
                            background_tasks=background_tasks,
                        )
                    )
                    request.chunk_id = approved_chunk_id
                else:
                    request.chunk_id = narrative_state.current_chunk_id
                    if (
                        request.choice is not None
                        or request.accept_fate
                        or narrative_state.choices
                    ):
                        resolved_user_text = _record_player_response_for_chunk(
                            slot=request.slot,
                            chunk_id=narrative_state.current_chunk_id,
                            user_text=request.user_text,
                            choice=request.choice,
                            accept_fate=request.accept_fate,
                            require_response=bool(narrative_state.choices),
                        )
                logger.info(
                    "Resolved chunk_id=%s from slot %s",
                    request.chunk_id,
                    request.slot,
                )
        elif request.chunk_id:
            resolved_user_text = _record_player_response_for_chunk(
                slot=request.slot,
                chunk_id=request.chunk_id,
                user_text=request.user_text,
                choice=request.choice,
                accept_fate=request.accept_fate,
                require_response=False,
            )

        parent_chunk_id = request.chunk_id if request.chunk_id else 0
        is_bootstrap = parent_chunk_id == 0
        embedding_claimed = _bind_generation_owner(
            slot=request.slot,
            session_id=session_id,
            parent_chunk_id=parent_chunk_id,
            claim_embedding=not is_bootstrap and request.slot is not None,
        )

        if is_bootstrap:
            logger.info("Starting narrative bootstrap (first chunk)")
        else:
            logger.info("Starting narrative continuation for chunk %s", parent_chunk_id)
        logger.info("Session ID: %s", session_id)
        logger.info("User text: %s...", resolved_user_text[:100])

        await manager.send_progress(
            session_id,
            "initiated",
            {
                "chunk_id": parent_chunk_id,
                "parent_chunk_id": parent_chunk_id,
                "is_bootstrap": is_bootstrap,
                "slot": request.slot,
            },
        )

        background_tasks.add_task(
            generate_narrative_async,
            session_id,
            parent_chunk_id,
            resolved_user_text,
            request.slot,
            get_db_connection=get_db_connection,
            load_settings=load_settings,
            manager=manager,
            manage_generation_lease=True,
            model_override=request.model,
        )
        if embedding_claimed:
            background_tasks.add_task(
                _trigger_locked_chunk_embedding,
                slot=request.slot,
                parent_chunk_id=parent_chunk_id,
            )
        scheduled = True

        message = (
            "Narrative bootstrap started"
            if is_bootstrap
            else f"Narrative generation started for chunk {parent_chunk_id}"
        )
        return ContinueNarrativeResponse(
            session_id=session_id,
            status="processing",
            message=message,
            warnings=accept_warnings,
        )
    except asyncio.CancelledError:
        failure_class = "CancelledError"
        failure_reason = "CancelledError"
        raise
    except Exception as exc:
        failure_class = type(exc).__name__
        failure_reason = str(exc) or type(exc).__name__
        raise
    finally:
        if not scheduled:
            _abandon_unscheduled_generation_owner(
                slot=request.slot,
                session_id=session_id,
                error=failure_reason,
                error_class=failure_class,
            )


@app.get("/api/narrative/active", response_model=Optional[NarrativeStatus])
async def get_active_narrative(
    slot: int = Query(..., ge=1, le=5)
) -> Optional[NarrativeStatus]:
    """Expose the lease owner or latest finished attempt for this explicit slot."""
    conn = get_db_connection(slot)
    try:
        row = read_generation_session(conn)
        return NarrativeStatus(slot=slot, **row) if row else None
    finally:
        conn.close()


@app.get("/api/narrative/status/{session_id}", response_model=NarrativeStatus)
async def get_narrative_status(
    session_id: str, slot: int = Query(..., ge=1, le=5)
) -> NarrativeStatus:
    """Return durable phase and outcome from the requested slot only."""
    conn = get_db_connection(slot)
    try:
        row = read_generation_session(conn, session_id=session_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )
        return NarrativeStatus(slot=slot, **row)
    finally:
        conn.close()


@app.post(
    "/api/narrative/regenerate",
    response_model=ContinueNarrativeResponse,
    responses={
        409: {
            "model": GenerationLeaseConflictResponse,
            "description": "Another generation currently owns the slot",
        }
    },
)
async def regenerate_narrative(
    request: RegenerateNarrativeRequest,
    background_tasks: BackgroundTasks,
):
    """
    Regenerate the storyteller turn currently in the incubator.

    Replaces the incubator's pending content with a fresh generation,
    reusing the same parent_chunk_id and user_text while assigning a new
    generation session. The CLI/UI polls
    /api/narrative/status/{session_id} for completion.
    """
    require_writable_slot(request.slot)
    conn = get_db_connection(request.slot)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT session_id, chunk_id, parent_chunk_id, user_text
                FROM incubator
                WHERE id = TRUE AND (%s IS NULL OR session_id = %s)
                """,
                (request.session_id, request.session_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "No live turn to regenerate. "
                        "Regenerate is only available while a turn is pending in the incubator."
                    ),
                )

            incumbent_session_id = str(row["session_id"])
            chunk_id = row["chunk_id"]
            parent_chunk_id = row["parent_chunk_id"]
            user_text = row["user_text"] or ""
            # Keep the incumbent until generation succeeds. The writer replaces
            # it only when this exact session/parent pair is still present, so a
            # failed re-roll preserves the draft without enabling last-writer-wins.
    finally:
        conn.close()

    session_id = str(uuid.uuid4())
    _acquire_generation_owner(
        slot=request.slot,
        session_id=session_id,
        operation="regenerate",
    )
    scheduled = False
    failure_class = "GenerationError"
    failure_reason = "Regeneration request ended before generation was scheduled."
    try:
        _bind_generation_owner(
            slot=request.slot,
            session_id=session_id,
            parent_chunk_id=parent_chunk_id,
            claim_embedding=False,
        )
        note = request.note.strip() if request.note else None
        logger.info(
            "Regenerating chunk %s (parent=%s) for session %s%s",
            chunk_id,
            parent_chunk_id,
            session_id,
            " [with note]" if note else "",
        )

        await manager.send_progress(
            session_id,
            "initiated",
            {
                "chunk_id": chunk_id,
                "parent_chunk_id": parent_chunk_id,
                "is_bootstrap": parent_chunk_id == 0,
                "regenerate": True,
                "slot": request.slot,
            },
        )

        background_tasks.add_task(
            generate_narrative_async,
            session_id,
            parent_chunk_id,
            user_text,
            request.slot,
            get_db_connection=get_db_connection,
            load_settings=load_settings,
            manager=manager,
            note=note,
            expected_incubator_session=incumbent_session_id,
            manage_generation_lease=True,
        )
        scheduled = True

        return ContinueNarrativeResponse(
            session_id=session_id,
            status="processing",
            message=f"Regenerating chunk {chunk_id}",
        )
    except asyncio.CancelledError:
        failure_class = "CancelledError"
        failure_reason = "CancelledError"
        raise
    except Exception as exc:
        failure_class = type(exc).__name__
        failure_reason = str(exc) or type(exc).__name__
        raise
    finally:
        if not scheduled:
            _abandon_unscheduled_generation_owner(
                slot=request.slot,
                session_id=session_id,
                error=failure_reason,
                error_class=failure_class,
            )


@app.post("/api/narrative/approve")
async def approve_narrative_unified(request: ApproveNarrativeRequest):
    """
    Approve narrative and optionally commit to database.

    If session_id is not provided, resolves from the most recent incubator entry for the slot.
    """
    require_writable_slot(request.slot)
    session_id = request.session_id
    slot = request.slot

    # Resolve session_id from incubator if not provided
    if session_id is None:
        if slot is None:
            raise HTTPException(
                status_code=400, detail="Either session_id or slot must be provided"
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
                        detail="No pending session to approve in incubator",
                    )
                session_id = row["session_id"]
                logger.info(
                    f"Resolved session_id={session_id} from slot {slot} incubator"
                )

    # Now call the implementation
    return await _approve_narrative_impl(session_id, request.commit, slot)


@app.post("/api/narrative/approve/{session_id}")
async def approve_narrative(
    session_id: str,
    request: Optional[ApproveNarrativeByIdRequest] = None,
    slot: Optional[int] = None,
):
    """
    Approve narrative and optionally commit to database (path-based for backward compatibility).
    """
    should_commit = request.commit if request else True
    if (
        request is not None
        and request.slot is not None
        and slot is not None
        and request.slot != slot
    ):
        raise HTTPException(status_code=422, detail="Body and query slots disagree")
    effective_slot = (
        request.slot if request is not None and request.slot is not None else slot
    )
    require_writable_slot(effective_slot)
    return await _approve_narrative_impl(session_id, should_commit, effective_slot)


def _approve_narrative_sync(
    session_id: str,
    commit: bool,
    slot: Optional[int],
) -> Dict[str, Any]:
    """Read or commit one incubator row with a worker-owned connection."""

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
                commit_warnings: List[Dict[str, Any]] = []
                chunk_id = commit_incubator_to_database_sync(
                    conn,
                    session_id,
                    slot,
                    warning_sink=commit_warnings,
                )
                result = {
                    "status": "committed",
                    "message": f"Narrative committed as chunk {chunk_id}",
                    "chunk_id": chunk_id,
                }
                if commit_warnings:
                    result["warnings"] = commit_warnings
            except Exception as e:
                logger.error(f"Failed to commit narrative: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to commit narrative: {str(e)}"
                )
        else:
            # Just mark as reviewed
            result = {
                "status": "reviewed",
                "message": "Narrative reviewed but not committed",
                "chunk_id": incubator_data["chunk_id"],
            }

    finally:
        conn.close()

    if commit:
        wake_scheduler(slot)
    return result


async def _approve_narrative_impl(
    session_id: str,
    commit: bool,
    slot: Optional[int],
):
    """Approve a narrative without exposing the worker connection to cancellation."""

    result = await asyncio.to_thread(
        _approve_narrative_sync,
        session_id,
        commit,
        slot,
    )
    return result


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
    require_writable_slot(request.slot)
    conn = get_db_connection(request.slot)
    is_incubator = False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if request.session_id is not None:
                cur.execute(
                    """
                    SELECT chunk_id AS id, storyteller_text, choice_object,
                           choice_text, session_id
                    FROM incubator WHERE session_id = %s FOR UPDATE
                    """,
                    (request.session_id,),
                )
                chunk = cur.fetchone()
                is_incubator = True
            else:
                cur.execute(
                    """
                    SELECT id, storyteller_text, choice_object, choice_text
                    FROM narrative_chunks WHERE id = %s FOR UPDATE
                    """,
                    (request.chunk_id,),
                )
                chunk = cur.fetchone()
                # Historical incubator rows may still have a reserved integer ID.
                if not chunk:
                    cur.execute(
                        """
                        SELECT chunk_id AS id, storyteller_text, choice_object,
                               choice_text, session_id
                        FROM incubator WHERE chunk_id = %s FOR UPDATE
                        """,
                        (request.chunk_id,),
                    )
                    chunk = cur.fetchone()
                    is_incubator = True

            if not chunk:
                raise HTTPException(
                    status_code=404,
                    detail=f"Draft or chunk {request.session_id or request.chunk_id} not found",
                )

            # Validate choice_object exists
            try:
                choice_object = normalize_choice_object(chunk.get("choice_object"))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            if not choice_object:
                raise HTTPException(
                    status_code=400,
                    detail=f"Chunk {request.chunk_id} has no choices to select from",
                )

            # P1: Check if choice already selected (prevent race condition)
            if choice_object.get("selected") or chunk.get("choice_text"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Choice already selected for chunk {request.chunk_id}. Cannot re-select.",
                )

            # P0: Validate selection label is valid
            presented = choice_object.get("presented", [])
            if request.selection.label != "freeform":
                if not isinstance(request.selection.label, int):
                    raise HTTPException(status_code=400, detail="Invalid label type")
                try:
                    selected_choice_text = validate_choice_index(
                        request.selection.label, presented
                    )
                except ValueError as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=str(exc),
                    ) from exc
                choice_text = (
                    request.selection.text
                    if request.selection.edited
                    else selected_choice_text
                )
                selected_index: Optional[int] = request.selection.label
            else:
                choice_text = request.selection.text
                selected_index = None

            # P0: Validate text length (prevent abuse)
            max_choice_text_length = get_max_choice_text_length()
            if len(choice_text) > max_choice_text_length:
                raise HTTPException(
                    status_code=400,
                    detail=f"Selection text too long ({len(choice_text)} chars). Max: {max_choice_text_length}",
                )

            # Update choice_object with selection
            choice_object["selected"] = selected_index
            storyteller_text = chunk.get("storyteller_text") or ""

            # Update the chunk in the appropriate table
            raw_text = _persist_chunk_response(
                cur,
                is_incubator=is_incubator,
                chunk_id=chunk["id"],
                storyteller_text=storyteller_text,
                choice_object=choice_object,
                choice_text=choice_text,
                incubator_session_id=str(chunk["session_id"]) if is_incubator else None,
            )
            if is_incubator:
                logger.info(
                    f"Recorded choice selection for incubator chunk {request.chunk_id}"
                )
            else:
                logger.info(f"Finalized choice selection for chunk {request.chunk_id}")

        conn.commit()

        return SelectChoiceResponse(
            status="pending" if is_incubator else "finalized",
            chunk_id=chunk["id"],
            session_id=str(chunk["session_id"]) if is_incubator else None,
            raw_text=raw_text,
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
async def websocket_endpoint(websocket: WebSocket, slot: int = Query(..., ge=1, le=5)):
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
async def get_incubator_contents(
    slot: Optional[int] = None, session_id: Optional[str] = None
):
    """Get current incubator contents"""
    conn = get_db_connection(slot)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM incubator_view WHERE (%s IS NULL OR session_id = %s)",
                (session_id, session_id),
            )
            result = cur.fetchone()

        if result:
            return dict(result)
        else:
            return {"message": "Incubator is empty"}
    finally:
        conn.close()


@app.delete("/api/narrative/incubator")
async def clear_incubator(
    slot: int = Query(..., ge=1, le=5), session_id: Optional[str] = None
):
    """Clear the incubator table"""
    require_writable_slot(slot)
    conn = get_db_connection(slot)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM incubator WHERE id = TRUE "
                "AND (%s IS NULL OR session_id = %s) RETURNING session_id",
                (session_id, session_id),
            )
            if session_id is not None and cur.rowcount != 1:
                raise HTTPException(status_code=404, detail="Pending session not found")
            removed = cur.fetchone()
            if removed is not None:
                discard_generation(cur, str(removed[0]))
        conn.commit()
        return {"message": "Incubator cleared"}
    finally:
        conn.close()


@app.get("/api/chunks/states")
async def get_chunk_states_endpoint(start: int, end: int, slot: Optional[int] = None):
    """Get states for a range of chunks"""
    try:
        return get_default_workflow().get_chunk_states(start, end, slot)
    except Exception as e:
        logger.error(f"Error fetching chunk states: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user-character")
async def get_user_character(slot: Optional[int] = None):
    """
    Get the user's character name for the active slot.

    Returns the character name resolved through the canonical player identity.

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
        conn = psycopg2.connect(**connection_kwargs(dbname))
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT setting IS NOT NULL,
                           base_timestamp IS NOT NULL,
                           EXISTS (SELECT 1 FROM narrative_chunks),
                           EXISTS (SELECT 1 FROM incubator)
                    FROM global_variables
                    WHERE id = true
                    """
                )
                lifecycle_row = cur.fetchone()
                try:
                    character_id = canonical_player_character_id(cur)
                except PlayerIdentityNotEstablishedError:
                    if lifecycle_row is None or any(lifecycle_row):
                        raise
                    # The UI polls this endpoint while an empty slot is still
                    # in the wizard, before any story marker or protagonist.
                    return {"name": None}
                cur.execute(
                    """
                    SELECT name
                    FROM characters
                    WHERE id = %s
                    """,
                    (character_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError(
                        "Canonical player character row "
                        f"{character_id} disappeared during load"
                    )
                return {"name": row[0]}
    except psycopg2.Error as e:
        logger.error(f"Database error fetching user character: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        if "conn" in locals():
            conn.close()


# Runtime status endpoint (issue #396): aggregate health beside /health.
# Must register BEFORE mount_ui below - the SPA mount is a catch-all.
register_runtime_status(app)

# Static serving for the built PWA and runtime uploads. Registered last:
# the dist mount at "/" is a catch-all and Starlette matches in order.
mount_ui(app)


if __name__ == "__main__":
    import uvicorn

    # NARRATIVE_API_PORT lets parallel checkouts (agent worktrees, the
    # golden-path gate) boot the gateway without contending for 8002.
    # #415/#458: loopback keeps the Cloudflare tunnel the sole default ingress.
    uvicorn.run(
        app,
        host=os.environ.get("NARRATIVE_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("NARRATIVE_API_PORT", "8002")),
    )
