"""
Save slot metadata helpers (assets.save_slots).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("nexus.api.save_slots")


def _connect(dbname: Optional[str] = None):
    return psycopg2.connect(
        dbname=dbname or os.environ.get("PGDATABASE", "NEXUS"),
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


def list_slots(dbname: Optional[str] = None) -> List[Dict]:
    with _connect(dbname) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM assets.save_slots ORDER BY slot_number")
        return [dict(row) for row in cur.fetchall()]


def upsert_slot(
    slot_number: int,
    character_name: Optional[str] = None,
    is_active: Optional[bool] = None,
    dbname: Optional[str] = None,
) -> None:
    if slot_number < 2 or slot_number > 5:
        raise ValueError("slot_number must be between 2 and 5")
    with _connect(dbname) as conn, conn.cursor() as cur:
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
    with _connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("UPDATE assets.save_slots SET is_active = FALSE")
    logger.info("Cleared active flag on all slots in %s", dbname or os.environ.get("PGDATABASE", "NEXUS"))
