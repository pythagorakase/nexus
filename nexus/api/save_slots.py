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
    logger.info("Updated save slot %s in %s", slot_number, dbname or os.environ.get("PGDATABASE", "NEXUS"))


def clear_active(dbname: Optional[str] = None) -> None:
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE assets.save_slots SET is_active = FALSE")
    logger.info("Cleared active flag on all slots in %s", dbname or os.environ.get("PGDATABASE", "NEXUS"))
