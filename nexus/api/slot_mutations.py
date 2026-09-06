"""Validate the explicit database target before a slot mutation starts."""

from fastapi import HTTPException

from nexus.api.save_slots import is_slot_locked
from nexus.api.slot_utils import slot_dbname


def require_writable_slot(slot: int | None) -> str:
    """Reject implicit targets and locked slots before any external side effect."""
    if isinstance(slot, bool) or not isinstance(slot, int) or not 1 <= slot <= 5:
        raise HTTPException(
            status_code=422, detail="An explicit slot from 1 to 5 is required"
        )
    dbname = slot_dbname(slot)
    if is_slot_locked(slot, dbname=dbname):
        raise HTTPException(status_code=423, detail=f"Slot {slot} is locked")
    return dbname
