"""
Helpers for persisting new-story setup state in assets.new_story_creator.
"""

from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, Optional

from nexus.api.db_pool import get_connection

logger = logging.getLogger("nexus.api.new_story_cache")


def read_cache(dbname: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Read the current new-story setup cache.

    Args:
        dbname: Optional database name (defaults to PGDATABASE env var)

    Returns:
        Dictionary containing cache data, or None if no cache exists
    """
    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
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
    """
    Write new-story setup state to the cache.

    Replaces the existing cache row with new data. Uses UPSERT pattern
    to ensure a single cache row exists without race conditions.

    Args:
        thread_id: Conversations thread ID
        setting_draft: JSON-serializable setting data
        character_draft: JSON-serializable character data
        selected_seed: JSON-serializable seed data
        initial_location: JSON-serializable location data
        base_timestamp: ISO timestamp string
        target_slot: Target save slot number
        dbname: Optional database name (defaults to PGDATABASE env var)
    """
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO assets.new_story_creator (
                    id, thread_id, setting_draft, character_draft, selected_seed,
                    initial_location, base_timestamp, target_slot
                ) VALUES (
                    TRUE, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (id) DO UPDATE SET
                    thread_id = EXCLUDED.thread_id,
                    setting_draft = EXCLUDED.setting_draft,
                    character_draft = EXCLUDED.character_draft,
                    selected_seed = EXCLUDED.selected_seed,
                    initial_location = EXCLUDED.initial_location,
                    base_timestamp = EXCLUDED.base_timestamp,
                    target_slot = EXCLUDED.target_slot,
                    updated_at = NOW()
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
    """
    Clear the new-story setup cache.

    Args:
        dbname: Optional database name (defaults to PGDATABASE env var)
    """
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM assets.new_story_creator WHERE id = TRUE")
    logger.info("Cleared new_story_creator cache in %s", dbname or os.environ.get("PGDATABASE", "NEXUS"))
