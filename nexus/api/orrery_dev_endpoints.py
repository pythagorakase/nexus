"""Dev-only FastAPI endpoints backing the Orrery audit dashboard.

Registered on the gateway only when ``[orrery.dashboard] enabled`` is true in
nexus.toml (see the conditional ``include_router`` in
:mod:`nexus.api.narrative`). All endpoints are read-only against slot
databases; payload assembly lives in :mod:`nexus.agents.orrery.audit` so it
can be exercised directly in tests.

Unexpected failures are allowed to propagate (500 with the real traceback in
the server log) — this is a development surface and errors should be loud.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.audit import build_catalog, entity_context, explain_dry_run
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.api.slot_utils import get_slot_db_url

logger = logging.getLogger("nexus.api.orrery_dev_endpoints")

router = APIRouter(prefix="/api/dev/orrery", tags=["orrery-dev"])


class OrreryResolveRequest(BaseModel):
    """Parameters for one explained dry-run tick."""

    model_config = ConfigDict(extra="forbid")

    slot: Optional[int] = Field(
        default=None,
        description="Save slot (1-5); falls back to NEXUS_SLOT when omitted.",
    )
    anchor_chunk_id: Optional[int] = Field(
        default=None,
        description=(
            "Tick anchor chunk. Defaults to the slot's latest narrative chunk, "
            "matching the turn cycle's fallback."
        ),
    )
    window_chunks: Optional[int] = Field(
        default=None,
        description="Binding window; defaults to [orrery.binding] window_chunks.",
    )


class OrreryEntityContextRequest(BaseModel):
    """Parameters for the entity hover/context payload."""

    model_config = ConfigDict(extra="forbid")

    slot: Optional[int] = Field(default=None)
    entity_ids: List[int] = Field(min_length=1)
    anchor_chunk_id: Optional[int] = Field(
        default=None,
        description=(
            "Tick anchor for need-debt accrual and world-time readout. "
            "Defaults to the slot's latest narrative chunk."
        ),
    )
    recent_events_limit: int = Field(default=5, ge=1, le=50)


def _orrery_settings() -> dict[str, Any]:
    from nexus.config import load_settings_as_dict

    settings = load_settings_as_dict()
    orrery = settings.get("orrery")
    if not orrery:
        raise RuntimeError(
            "nexus.toml has no [orrery] section; the audit dashboard cannot "
            "resolve without binding/sunhelm configuration"
        )
    return orrery


@contextmanager
def _slot_session(slot: Optional[int]) -> Iterator[Session]:
    try:
        db_url = get_slot_db_url(slot=slot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    engine = create_engine(db_url)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def _default_anchor_chunk_id(session: Session) -> Optional[int]:
    # Same fallback the turn cycle uses when no target chunk is in play.
    row = (
        session.execute(text("SELECT max(id) AS max_id FROM narrative_chunks"))
        .mappings()
        .first()
    )
    return row["max_id"] if row else None


@router.get("/catalog")
async def get_catalog() -> dict[str, Any]:
    """Static template catalog: bands, pseudo-templates, families, event map."""

    orrery = _orrery_settings()
    return build_catalog(
        BUILTIN_TEMPLATES,
        sunhelm_settings=orrery.get("sunhelm"),
        promote_settings=orrery.get("promote"),
    )


@router.post("/resolve")
async def post_resolve(request: OrreryResolveRequest) -> dict[str, Any]:
    """Explained dry-run tick against a real slot. Read-only."""

    orrery = _orrery_settings()
    window_chunks = (
        request.window_chunks
        if request.window_chunks is not None
        else int(orrery["binding"]["window_chunks"])
    )
    with _slot_session(request.slot) as session:
        anchor_chunk_id = (
            request.anchor_chunk_id
            if request.anchor_chunk_id is not None
            else _default_anchor_chunk_id(session)
        )
        report = explain_dry_run(
            session,
            BUILTIN_TEMPLATES,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=window_chunks,
            sunhelm_settings=orrery.get("sunhelm"),
        )
    payload = report.to_dict()
    payload["mode"] = "current"
    return payload


@router.post("/context/entities")
async def post_entity_context(
    request: OrreryEntityContextRequest,
) -> dict[str, Any]:
    """Hover-audit payload for a set of entity ids. Read-only."""

    orrery = _orrery_settings()
    with _slot_session(request.slot) as session:
        anchor_chunk_id = (
            request.anchor_chunk_id
            if request.anchor_chunk_id is not None
            else _default_anchor_chunk_id(session)
        )
        return entity_context(
            session,
            request.entity_ids,
            anchor_chunk_id=anchor_chunk_id,
            recent_events_limit=request.recent_events_limit,
            sunhelm_settings=orrery.get("sunhelm"),
        )
