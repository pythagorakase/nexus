"""
FastAPI endpoints for new story setup wizard.

This module handles the setup phase of story creation including:
- Starting and resuming setup sessions
- Recording draft data (setting, character, seed, location)
- Slot management and status queries
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import frontmatter
import psycopg2
from fastapi import APIRouter, HTTPException, Query

from nexus.api.conversations import ConversationsClient
from nexus.api.narrative_schemas import (
    RecordDraftRequest,
    ResetSetupRequest,
    ResumeSetupResponse,
    SelectSlotRequest,
    StartSetupRequest,
)
from nexus.api.new_story_cache import write_wizard_choices
from nexus.api.new_story_flow import (
    activate_slot,
    record_drafts,
    reset_setup,
    resume_setup,
    start_setup,
)
from nexus.api.save_slots import get_slot_model
from nexus.api.slot_mutations import require_writable_slot
from nexus.api.slot_utils import slot_dbname

logger = logging.getLogger("nexus.api.setup_endpoints")

router = APIRouter(prefix="/api/story/new", tags=["setup"])


@router.post("/setup/start")
async def start_setup_endpoint(request: StartSetupRequest) -> Dict[str, Any]:
    """Start a new setup conversation"""
    require_writable_slot(request.slot)
    try:
        # The core resolves and persists the setup model. Passing the raw
        # request keeps omitted client values distinct from explicit
        # overrides so an operator-set slot model can be preserved.
        thread_id = start_setup(request.slot, request.model)
        model_to_use = get_slot_model(request.slot, dbname=slot_dbname(request.slot))
        if not model_to_use:
            raise RuntimeError(
                f"Setup for slot {request.slot} started without a persisted model"
            )

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
            client = ConversationsClient(model=model_to_use)
            client.add_message(thread_id, "assistant", welcome_message)

        # Store welcome choices for CLI --choice resolution
        if welcome_choices:
            write_wizard_choices(welcome_choices, slot_dbname(request.slot))

        return {
            "status": "started",
            "thread_id": thread_id,
            "slot": request.slot,
            "model": model_to_use,
            "welcome_message": welcome_message,
            "welcome_choices": welcome_choices,
        }
    except Exception as e:
        logger.error(f"Error starting setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/setup/resume", response_model=ResumeSetupResponse)
def resume_setup_endpoint(slot: int = Query(..., ge=1, le=5)) -> ResumeSetupResponse:
    """Restore saved drafts, all conversation messages, and current choices."""
    try:
        data = resume_setup(slot)
        if not data:
            raise HTTPException(
                status_code=404, detail=f"No active setup found for slot {slot}"
            )
        if not data.thread_id:
            raise RuntimeError("The saved wizard is missing its conversation ID")
        model = get_slot_model(slot, dbname=slot_dbname(slot))
        if not model:
            raise RuntimeError("The saved wizard is missing its model")
        client = ConversationsClient(model=model)
        try:
            # The model's context window limit must not truncate the UI transcript.
            messages = client.list_messages(data.thread_id, limit=0)
        finally:
            if client.client is not None:
                client.client.close()
        return ResumeSetupResponse(
            thread_id=data.thread_id,
            target_slot=slot,
            current_phase=data.current_phase(),
            messages=[
                message
                for message in reversed(messages)
                if message["role"] in {"user", "assistant"}
            ],
            choices=data.choices,
            setting_draft=data.get_setting_dict(),
            character_draft=data.get_character_dict(),
            character_state=data.get_character_state_dict(),
            selected_seed=data.get_seed_dict(),
            layer_draft=data.get_layer_dict(),
            zone_draft=data.get_zone_dict(),
            initial_location=data.get_initial_location(),
            base_timestamp=data.base_timestamp,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/setup/record")
async def record_drafts_endpoint(request: RecordDraftRequest):
    """Record draft data for a slot"""
    require_writable_slot(request.slot)
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
    require_writable_slot(request.slot)
    try:
        reset_setup(request.slot)
        return {"status": "reset", "slot": request.slot}
    except Exception as e:
        logger.error(f"Error resetting setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/slot/select")
async def select_slot_endpoint(request: SelectSlotRequest):
    """Select a slot through the nonmutating compatibility activation path."""
    # activate_slot only calls clear_active and upsert_slot(is_active=...),
    # both no-ops. Locked stories remain selectable; setup writes are guarded
    # by their own endpoints before starting any work.
    try:
        results = activate_slot(request.slot)
        return {"status": "activated", "results": results}
    except Exception as e:
        logger.error(f"Error activating slot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/slots")
async def get_slots_status_endpoint():
    """Get status of all save slots with wizard state.

    Uses data-presence detection from slot_state.py rather than the
    potentially stale new_story flag for robust is_active detection.
    """
    from nexus.api.slot_utils import all_slots
    from nexus.api.slot_state import get_slot_state
    from nexus.api.save_slots import is_slot_locked

    results = []
    for slot in all_slots():
        try:
            state = get_slot_state(slot)

            # Build response from slot_state data
            slot_data = {
                "slot_number": slot,
                "is_active": not state.is_empty,  # Data presence, not flag
                "is_locked": is_slot_locked(slot),
                "model": state.model,
                "wizard_in_progress": state.is_wizard_mode,
            }

            if state.is_wizard_mode and state.wizard_state:
                slot_data["wizard_phase"] = state.wizard_state.phase
                slot_data["wizard_thread_id"] = state.wizard_state.thread_id

            if state.narrative_state:
                # For narrative mode, include chunk info
                slot_data["current_chunk_id"] = state.narrative_state.current_chunk_id
                slot_data["has_pending"] = state.narrative_state.has_pending

            results.append(slot_data)
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            # Expected: DB doesn't exist or connection failed
            logger.warning(f"Could not connect to slot {slot} database: {e}")
            results.append(
                {"slot_number": slot, "is_active": False, "wizard_in_progress": False}
            )
        except Exception as e:
            # Unexpected errors should surface during development
            logger.error(f"Unexpected error fetching slot {slot}: {e}")
            raise

    return results
