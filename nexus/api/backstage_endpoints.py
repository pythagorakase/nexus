"""Dev-gated read-only endpoint for the IRIS Backstage drawer."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from nexus.agents.orrery.backstage import (
    BackstageHealthResponse,
    BackstagePayloadError,
    BackstageTurnResponse,
    build_backstage_turn,
)
from nexus.api.slot_utils import get_slot_db_url


router = APIRouter(prefix="/api/dev/backstage", tags=["backstage-dev"])


@router.get("/health", response_model=BackstageHealthResponse)
async def get_backstage_health() -> BackstageHealthResponse:
    """Confirm that the server-side Backstage gate registered this router."""

    return BackstageHealthResponse()


@contextmanager
def _slot_session(slot: int) -> Iterator[Session]:
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


@router.get("/{slot}/turn", response_model=BackstageTurnResponse)
async def get_backstage_turn(
    slot: int,
    chunk_id: Optional[int] = None,
) -> BackstageTurnResponse:
    """Return the latest or selected committed Backstage turn for one slot."""

    with _slot_session(slot) as session:
        try:
            return build_backstage_turn(session, slot=slot, chunk_id=chunk_id)
        except BackstagePayloadError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail)
