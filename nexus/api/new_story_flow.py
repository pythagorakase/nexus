"""
Headless helpers to manage new-story setup per slot.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

import psycopg2

from nexus.api.conversations import ConversationsClient
from nexus.api.new_story_cache import read_cache, write_cache, clear_cache
from nexus.api.save_slots import upsert_slot, clear_active
from nexus.api.slot_utils import slot_dbname, all_slots
from scripts.new_story_setup import create_slot_schema_only

logger = logging.getLogger("nexus.api.new_story_flow")

# Load settings
settings_path = Path(__file__).parent.parent.parent / "settings.json"
with settings_path.open() as f:
    SETTINGS = json.load(f)
NEW_STORY_MODEL = SETTINGS.get("API Settings", {}).get("new_story", {}).get("model", "gpt-5.1")


def start_setup(slot_number: int, model: Optional[str] = None) -> str:
    """
    Start a new setup conversation for a slot.

    - Clears cache in the slot DB
    - Creates a conversations thread and stores thread_id
    - Marks slot as active (and clears other actives)

    Args:
        slot_number: Target save slot (1-5)
        model: Optional model name (defaults to settings.json new_story.model)

    Returns:
        Thread ID for the new conversation
    """
    dbname = slot_dbname(slot_number)
    
    # Ensure database exists
    try:
        conn = psycopg2.connect(database=dbname)
        conn.close()
    except psycopg2.OperationalError:
        logger.info("Database %s does not exist. Creating...", dbname)
        # NEXUS is the schema template database (not for gameplay data).
        # New slot databases are created by cloning the NEXUS schema structure.
        create_slot_schema_only(slot_number, source_db="NEXUS")

    clear_cache(dbname)
    # Use provided model or fall back to settings
    model_to_use = model or NEW_STORY_MODEL
    client = ConversationsClient(model=model_to_use)
    thread_id = client.create_thread()
    write_cache(thread_id=thread_id, target_slot=slot_number, dbname=dbname)
    clear_active(dbname)
    upsert_slot(slot_number, is_active=True, dbname=dbname)
    logger.info("Started setup for slot %s with thread %s", slot_number, thread_id)
    return thread_id


def resume_setup(slot_number: int) -> Optional[Dict]:
    """
    Resume setup by returning cache contents for the slot.

    Args:
        slot_number: Target save slot (1-5)

    Returns:
        Dictionary containing cached setup data, or None if no cache exists
    """
    dbname = slot_dbname(slot_number)
    cache = read_cache(dbname)
    if cache:
        logger.info("Resuming setup for slot %s", slot_number)
    else:
        logger.info("No setup cache found for slot %s", slot_number)
    return cache


def record_drafts(
    slot_number: int,
    *,
    setting: Optional[Dict] = None,
    character: Optional[Dict] = None,
    seed: Optional[Dict] = None,
    layer: Optional[Dict] = None,
    zone: Optional[Dict] = None,
    location: Optional[Dict] = None,
    base_timestamp: Optional[str] = None,
) -> None:
    """
    Persist current drafts to the slot cache.

    Args:
        slot_number: Target save slot (1-5)
        setting: Optional setting draft dictionary
        character: Optional character draft dictionary
        seed: Optional seed selection dictionary
        layer: Optional layer definition dictionary
        zone: Optional zone definition dictionary
        location: Optional initial location dictionary
        base_timestamp: Optional ISO timestamp string
    """
    dbname = slot_dbname(slot_number)
    cache = read_cache(dbname) or {}
    write_cache(
        thread_id=cache.get("thread_id"),
        setting_draft=setting or cache.get("setting_draft"),
        character_draft=character or cache.get("character_draft"),
        selected_seed=seed or cache.get("selected_seed"),
        layer_draft=layer or cache.get("layer_draft"),
        zone_draft=zone or cache.get("zone_draft"),
        initial_location=location or cache.get("initial_location"),
        base_timestamp=base_timestamp or cache.get("base_timestamp"),
        target_slot=slot_number,
        dbname=dbname,
    )
    logger.info("Updated drafts for slot %s", slot_number)


def reset_setup(slot_number: int) -> None:
    """
    Clear cache and deactivate slot.

    Args:
        slot_number: Target save slot (1-5)
    """
    dbname = slot_dbname(slot_number)
    clear_cache(dbname)
    upsert_slot(slot_number, is_active=False, dbname=dbname)
    logger.info("Reset setup for slot %s", slot_number)


def activate_slot(target_slot: int) -> Dict[str, str]:
    """
    Mark a slot as active and clear active flags in other slots.

    Skips slots whose databases do not exist.

    Args:
        target_slot: Slot number to activate (1-5)

    Returns:
        Dictionary mapping slot numbers to status strings ("active", "cleared", "unavailable")
    """
    results = {}
    for slot in all_slots():
        dbname = slot_dbname(slot)
        try:
            if slot == target_slot:
                upsert_slot(slot, is_active=True, dbname=dbname)
                results[slot] = "active"
            else:
                clear_active(dbname)
                results[slot] = "cleared"
        except (psycopg2.Error, OSError) as exc:  # pragma: no cover - defensive cross-db handling
            logger.warning("Slot %s DB not available: %s", slot, exc)
            results[slot] = "unavailable"
    return results
