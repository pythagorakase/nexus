"""
FastAPI endpoints for new story setup wizard.

This module handles the setup phase of story creation including:
- Starting and resuming setup sessions
- Recording draft data (setting, character, seed, location)
- Slot management and status queries
"""

import logging
from pathlib import Path
from typing import Dict, Any, List

import frontmatter
import psycopg2
from fastapi import APIRouter, HTTPException

from nexus.api.conversations import ConversationsClient
from nexus.api.narrative_schemas import (
    StartSetupRequest,
    RecordDraftRequest,
    ResetSetupRequest,
    SelectSlotRequest,
)
from nexus.api.new_story_flow import (
    start_setup,
    resume_setup,
    record_drafts,
    reset_setup,
    activate_slot,
)
from nexus.api.new_story_cache import write_wizard_choices
from nexus.api.slot_utils import slot_dbname
from nexus.api.config_utils import get_new_story_model

logger = logging.getLogger("nexus.api.setup_endpoints")

router = APIRouter(prefix="/api/story/new", tags=["setup"])


@router.post("/setup/start")
async def start_setup_endpoint(request: StartSetupRequest) -> Dict[str, Any]:
    """Start a new setup conversation"""
    try:
        thread_id = start_setup(request.slot, request.model)

        # Load welcome message and choices from frontmatter
        prompt_path = (
            Path(__file__).parent.parent.parent / "prompts" / "storyteller_new.md"
        )
        welcome_message = ""
        welcome_choices: List[str] = []
        if prompt_path.exists():
            with prompt_path.open() as f:
                doc = frontmatter.load(f)
                welcome_message = doc.get("welcome_message", "")
                welcome_choices = doc.get("welcome_choices", [])

        # Seed welcome message if exists (without choices - UI renders those)
        if welcome_message:
            # Use request model (enables TEST mode) or fall back to settings
            model_to_use = request.model or get_new_story_model()
            client = ConversationsClient(model=model_to_use)
            client.add_message(thread_id, "assistant", welcome_message)

        # Store welcome choices for CLI --choice resolution
        if welcome_choices:
            write_wizard_choices(welcome_choices, slot_dbname(request.slot))

        return {
            "status": "started",
            "thread_id": thread_id,
            "slot": request.slot,
            "welcome_message": welcome_message,
            "welcome_choices": welcome_choices,
        }
    except Exception as e:
        logger.error(f"Error starting setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/setup/resume")
async def resume_setup_endpoint(slot: int):
    """Resume setup for a slot"""
    try:
        data = resume_setup(slot)
        if not data:
            raise HTTPException(
                status_code=404, detail=f"No active setup found for slot {slot}"
            )
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/setup/record")
async def record_drafts_endpoint(request: RecordDraftRequest):
    """Record draft data for a slot"""
    try:
        record_drafts(
            request.slot,
            setting=request.setting,
            character=request.character,
            seed=request.seed,
            location=request.location,
            base_timestamp=request.base_timestamp,
        )
        return {"status": "recorded", "slot": request.slot}
    except Exception as e:
        logger.error(f"Error recording drafts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/setup/reset")
async def reset_setup_endpoint(request: ResetSetupRequest):
    """Reset setup for a slot"""
    try:
        reset_setup(request.slot)
        return {"status": "reset", "slot": request.slot}
    except Exception as e:
        logger.error(f"Error resetting setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/slot/select")
async def select_slot_endpoint(request: SelectSlotRequest):
    """Activate a slot"""
    try:
        results = activate_slot(request.slot)
        return {"status": "activated", "results": results}
    except Exception as e:
        logger.error(f"Error activating slot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/slots")
async def get_slots_status_endpoint():
    """Get status of all save slots with wizard state"""
    from nexus.api.slot_utils import all_slots, slot_dbname
    from nexus.api.save_slots import list_slots
    from nexus.api.new_story_cache import read_cache

    results = []
    for slot in all_slots():
        dbname = slot_dbname(slot)
        try:
            # Try to list slots from this DB
            slots_data = list_slots(dbname=dbname)
            # Find the row for this slot
            slot_data = next((s for s in slots_data if s["slot_number"] == slot), None)

            if slot_data:
                # Check if wizard is in progress
                cache = read_cache(dbname)
                if cache:
                    slot_data["wizard_in_progress"] = True
                    slot_data["wizard_thread_id"] = cache.thread_id
                    slot_data["wizard_phase"] = cache.current_phase()
                else:
                    slot_data["wizard_in_progress"] = False
                results.append(slot_data)
            else:
                results.append({"slot_number": slot, "is_active": False, "wizard_in_progress": False})
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            # Expected: DB doesn't exist or connection failed
            logger.warning(f"Could not connect to slot {slot} database: {e}")
            results.append({"slot_number": slot, "is_active": False, "wizard_in_progress": False})
        except Exception as e:
            # Unexpected errors should surface during development
            logger.error(f"Unexpected error fetching slot {slot}: {e}")
            raise

    return results
