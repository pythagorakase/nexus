"""
Save slot metadata helpers (assets.save_slots).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional

from nexus.api.db_pool import get_connection

logger = logging.getLogger("nexus.api.save_slots")


def list_slots(dbname: Optional[str] = None) -> List[Dict]:
    """
    Retrieve all save slots from the database.

    Args:
        dbname: Optional database name (defaults to PGDATABASE env var)

    Returns:
        List of dictionaries containing slot metadata
    """
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM assets.save_slots ORDER BY slot_number")
            return [dict(row) for row in cur.fetchall()]


def upsert_slot(
    slot_number: int,
    character_name: Optional[str] = None,
    is_active: Optional[bool] = None,
    dbname: Optional[str] = None,
) -> None:
    """
    Insert or update a save slot's metadata.

    Args:
        slot_number: Slot number (1-5)
        character_name: Optional character name (max 50 chars, alphanumeric with spaces/hyphens/apostrophes/periods)
        is_active: Optional flag to mark slot as active
        dbname: Optional database name (defaults to PGDATABASE env var)

    Raises:
        ValueError: If slot_number is not between 1 and 5, or character_name is invalid
    """
    if slot_number < 1 or slot_number > 5:
        raise ValueError("slot_number must be between 1 and 5")

    # Validate character_name to prevent injection attacks
    if character_name is not None:
        if not re.match(r'^[a-zA-Z0-9\s\-\'\.]{1,50}$', character_name):
            raise ValueError("Character name must be alphanumeric with spaces, hyphens, apostrophes, and periods only (max 50 chars)")

    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO assets.save_slots (slot_number, character_name, last_played, is_active)
                VALUES (%s, %s, now(), COALESCE(%s, FALSE))
                ON CONFLICT (slot_number) DO UPDATE
                SET character_name = EXCLUDED.character_name,
                    last_played = now(),
                    is_active = COALESCE(%s, assets.save_slots.is_active)
                """,
                (slot_number, character_name, is_active, is_active),
            )
    logger.info("Updated save slot %s in %s", slot_number, dbname or "(default slot)")


def clear_active(dbname: Optional[str] = None) -> None:
    """
    Clear the active flag on all save slots.

    Args:
        dbname: Optional database name (defaults to PGDATABASE env var)
    """
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE assets.save_slots SET is_active = FALSE")
    logger.info("Cleared active flag on all slots in %s", dbname or "(default slot)")


def is_slot_locked(slot_number: int, dbname: Optional[str] = None) -> bool:
    """
    Check if a slot is locked.

    Args:
        slot_number: Slot number (1-5)
        dbname: Optional database name (defaults to PGDATABASE env var)

    Returns:
        True if the slot is locked, False otherwise
    """
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_locked FROM assets.save_slots WHERE slot_number = %s",
                (slot_number,),
            )
            row = cur.fetchone()
            return bool(row and row.get("is_locked"))


def lock_slot(slot_number: int, dbname: Optional[str] = None) -> None:
    """
    Lock a save slot to prevent modifications.

    Args:
        slot_number: Slot number (1-5)
        dbname: Optional database name (defaults to PGDATABASE env var)
    """
    if slot_number < 1 or slot_number > 5:
        raise ValueError("slot_number must be between 1 and 5")

    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO assets.save_slots (slot_number, is_locked)
                VALUES (%s, TRUE)
                ON CONFLICT (slot_number) DO UPDATE
                SET is_locked = TRUE
                """,
                (slot_number,),
            )
    logger.info("Locked slot %s in %s", slot_number, dbname or "(default slot)")


def unlock_slot(slot_number: int, dbname: Optional[str] = None) -> None:
    """
    Unlock a save slot to allow modifications.

    Args:
        slot_number: Slot number (1-5)
        dbname: Optional database name (defaults to PGDATABASE env var)
    """
    if slot_number < 1 or slot_number > 5:
        raise ValueError("slot_number must be between 1 and 5")

    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE assets.save_slots
                SET is_locked = FALSE
                WHERE slot_number = %s
                """,
                (slot_number,),
            )
    logger.info("Unlocked slot %s in %s", slot_number, dbname or "(default slot)")
