"""
Helpers for persisting new-story setup state in assets.new_story_creator.
"""

from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("nexus.api.new_story_cache")


def _connect(dbname: Optional[str] = None):
    return psycopg2.connect(
        dbname=dbname or os.environ.get("PGDATABASE", "NEXUS"),
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


def read_cache(dbname: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with _connect(dbname) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM assets.new_story_creator WHERE id = TRUE")
        row = cur.fetchone()
        return dict(row) if row else None


def write_cache(
    thread_id: Optional[str] = None,
    setting_draft: Optional[Dict[str, Any]] = None,
    character_draft: Optional[Dict[str, Any]] = None,
    selected_seed: Optional[Dict[str, Any]] = None,
    initial_location: Optional[Dict[str, Any]] = None,
    base_timestamp: Optional[str] = None,
    target_slot: Optional[int] = None,
    dbname: Optional[str] = None,
) -> None:
    with _connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM assets.new_story_creator WHERE id = TRUE")
        cur.execute(
            """
            INSERT INTO assets.new_story_creator (
                id, thread_id, setting_draft, character_draft, selected_seed,
                initial_location, base_timestamp, target_slot
            ) VALUES (
                TRUE, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                thread_id,
                json.dumps(setting_draft) if setting_draft else None,
                json.dumps(character_draft) if character_draft else None,
                json.dumps(selected_seed) if selected_seed else None,
                json.dumps(initial_location) if initial_location else None,
                base_timestamp,
                target_slot,
            ),
        )
    logger.info("Updated new_story_creator cache in %s", dbname or os.environ.get("PGDATABASE", "NEXUS"))


def clear_cache(dbname: Optional[str] = None) -> None:
    with _connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM assets.new_story_creator WHERE id = TRUE")
    logger.info("Cleared new_story_creator cache in %s", dbname or os.environ.get("PGDATABASE", "NEXUS"))
