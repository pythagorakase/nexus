"""Dev-gated read-only endpoint for the IRIS Backstage drawer."""

from __future__ import annotations

from contextlib import closing, contextmanager
from typing import Iterator, Optional

from fastapi import APIRouter, HTTPException
import psycopg2
from sqlalchemy.orm import Session

from nexus.agents.orrery.backstage import (
    BackstageHealthResponse,
    BackstagePayloadError,
    BackstageTurnResponse,
    build_backstage_turn,
    read_backstage_economics,
)
from nexus.api.slot_utils import get_slot_db_url
from nexus.database import create_slot_engine


router = APIRouter(prefix="/api/dev/backstage", tags=["backstage-dev"])


@router.get("/health", response_model=BackstageHealthResponse)
async def get_backstage_health() -> BackstageHealthResponse:
    """Confirm that the server-side Backstage gate registered this router."""

    return BackstageHealthResponse()


def _slot_db_url(slot: int) -> str:
    try:
        return get_slot_db_url(slot=slot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@contextmanager
def _slot_session(db_url: str) -> Iterator[Session]:
    engine = create_slot_engine(db_url)
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

    db_url = _slot_db_url(slot)
    with _slot_session(db_url) as session:
        try:
            turn = build_backstage_turn(session, slot=slot, chunk_id=chunk_id)
        except BackstagePayloadError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail)
        with closing(psycopg2.connect(db_url)) as conn:
            return BackstageTurnResponse(
                header=turn.header,
                correspondence=turn.correspondence,
                state_writes=turn.state_writes,
                orrery=turn.orrery,
                economics=read_backstage_economics(
                    conn, slot=slot, chunk_id=turn.header.chunk_id
                ),
            )
