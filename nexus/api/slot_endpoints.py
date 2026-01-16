"""
FastAPI endpoints for slot management operations.

This module handles slot state queries and operations including:
- Slot state retrieval
- Model get/set
- Undo operations
- Lock/unlock operations
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException

from nexus.api.db_pool import get_connection
from nexus.api.narrative_schemas import (
    SlotStateResponse,
    SlotUndoResponse,
    SlotModelRequest,
    SlotModelResponse,
    SlotLockResponse,
    TraitMenuItemResponse,
)
from nexus.api.slot_utils import slot_dbname

logger = logging.getLogger("nexus.api.slot_endpoints")

router = APIRouter(prefix="/api/slot", tags=["slot"])


@router.get("/{slot}/state", response_model=SlotStateResponse)
async def get_slot_state_endpoint(slot: int):
    """
    Get complete state for a save slot.

    Returns everything needed to display current position and available actions:
    - Whether in wizard or narrative mode
    - Current wizard phase or narrative chunk
    - Available choices
    - Current model setting
    """
    from nexus.api.slot_state import get_slot_state

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        state = get_slot_state(slot)

        if state.is_empty:
            return SlotStateResponse(
                slot=slot,
                is_empty=True,
                is_wizard_mode=False,
                model=state.model,
            )

        if state.is_wizard_mode and state.wizard_state:
            response = SlotStateResponse(
                slot=slot,
                is_empty=False,
                is_wizard_mode=True,
                phase=state.wizard_state.phase,
                thread_id=state.wizard_state.thread_id,
                model=state.model,
            )

            # Add trait menu if in character phase, traits subphase
            ws = state.wizard_state
            if ws.phase == "character" and ws.has_concept and not ws.has_traits:
                from nexus.api.new_story_cache import get_trait_menu, get_selected_trait_count
                dbname = slot_dbname(slot)
                trait_menu = get_trait_menu(dbname)
                selected_count = get_selected_trait_count(dbname)
                response.subphase = "traits"
                response.trait_menu = [
                    TraitMenuItemResponse(
                        id=t.id,
                        name=t.name,
                        description=t.description,
                        is_selected=t.is_selected,
                        rationale=t.rationale,
                    )
                    for t in trait_menu
                ]
                response.can_confirm = selected_count == 3
            elif ws.phase == "character":
                if not ws.has_concept:
                    response.subphase = "concept"
                elif ws.has_traits and not ws.has_wildcard:
                    response.subphase = "wildcard"
                elif ws.has_wildcard:
                    response.subphase = "complete"

            return response

        if state.narrative_state:
            return SlotStateResponse(
                slot=slot,
                is_empty=False,
                is_wizard_mode=False,
                current_chunk_id=state.narrative_state.current_chunk_id,
                has_pending=state.narrative_state.has_pending,
                storyteller_text=state.narrative_state.storyteller_text,
                choices=state.narrative_state.choices,
                model=state.model,
            )

        # Fallback for edge cases
        return SlotStateResponse(
            slot=slot,
            is_empty=True,
            is_wizard_mode=False,
        )

    except Exception as e:
        logger.error(f"Error getting slot state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{slot}/undo", response_model=SlotUndoResponse)
async def slot_undo_endpoint(slot: int):
    """
    Undo the last action for a slot.

    Behavior depends on current mode:
    - Wizard mode: Clears the most recent draft, reverting to previous phase
    - Narrative mode (pending): Deletes incubator content without committing
    - Narrative mode (committed): Cannot undo committed chunks

    Single-depth undo only - no multi-step rewind.
    """
    from nexus.api.slot_state import get_slot_state
    from nexus.api.new_story_cache import clear_seed_phase, clear_character_phase, clear_setting_phase

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        state = get_slot_state(slot)
        dbname = slot_dbname(slot)

        if state.is_empty:
            return SlotUndoResponse(
                success=False,
                message="Slot is empty - nothing to undo",
            )

        if state.is_wizard_mode and state.wizard_state:
            wizard = state.wizard_state

            # Determine what to clear based on current phase
            if wizard.phase == "ready":
                # Clear seed columns to go back to seed phase
                clear_seed_phase(dbname)
                return SlotUndoResponse(
                    success=True,
                    message="Reverted to seed phase",
                    previous_state="seed",
                )

            elif wizard.phase == "seed":
                # Clear character columns to go back to character phase
                clear_character_phase(dbname)
                return SlotUndoResponse(
                    success=True,
                    message="Reverted to character phase",
                    previous_state="character",
                )

            elif wizard.phase == "character":
                # Clear setting columns to go back to setting phase
                clear_setting_phase(dbname)
                return SlotUndoResponse(
                    success=True,
                    message="Reverted to setting phase",
                    previous_state="setting",
                )

            else:
                # Already at setting phase - nothing to undo
                return SlotUndoResponse(
                    success=False,
                    message="Already at beginning of wizard - nothing to undo",
                )

        elif state.narrative_state:
            narrative = state.narrative_state

            if narrative.has_pending and narrative.session_id:
                # Delete pending incubator content
                with get_connection(dbname) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM incubator WHERE session_id = %s",
                            (narrative.session_id,),
                        )

                return SlotUndoResponse(
                    success=True,
                    message="Deleted pending content",
                    previous_state=str(narrative.current_chunk_id),
                )

            else:
                # No pending content - cannot undo committed chunks
                return SlotUndoResponse(
                    success=False,
                    message="Cannot undo committed chunks - only pending content can be undone",
                )

        return SlotUndoResponse(
            success=False,
            message="Unknown state - cannot undo",
        )

    except Exception as e:
        logger.error(f"Error in slot undo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{slot}/model", response_model=SlotModelResponse)
async def get_slot_model_endpoint(slot: int):
    """Get current model for a slot."""
    from nexus.config import load_settings_as_dict

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        dbname = slot_dbname(slot)

        # Get current model from global_variables
        with get_connection(dbname, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT model FROM global_variables WHERE id = TRUE")
                row = cur.fetchone()
                current_model = row.get("model") if row else None

        # Get available models from config
        settings = load_settings_as_dict()
        available = settings.get("global", {}).get("model", {}).get(
            "available_models", ["gpt-5.1", "TEST", "claude"]
        )

        return SlotModelResponse(
            slot=slot,
            model=current_model,
            available_models=available,
        )

    except Exception as e:
        logger.error(f"Error getting slot model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{slot}/model", response_model=SlotModelResponse)
async def set_slot_model_endpoint(slot: int, request: SlotModelRequest):
    """Set model for a slot."""
    from nexus.config import load_settings_as_dict

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        dbname = slot_dbname(slot)

        # Validate model against available models
        settings = load_settings_as_dict()
        available = settings.get("global", {}).get("model", {}).get(
            "available_models", ["gpt-5.1", "TEST", "claude"]
        )

        if request.model not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model '{request.model}'. Available: {', '.join(available)}",
            )

        # Update model in global_variables
        with get_connection(dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE global_variables SET model = %s WHERE id = TRUE",
                    (request.model,),
                )

        return SlotModelResponse(
            slot=slot,
            model=request.model,
            available_models=available,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting slot model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{slot}/lock", response_model=SlotLockResponse)
async def lock_slot_endpoint(slot: int):
    """Lock a slot to prevent modifications."""
    from nexus.api.save_slots import lock_slot

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        dbname = slot_dbname(slot)
        lock_slot(slot, dbname)
        return SlotLockResponse(
            slot=slot,
            is_locked=True,
            message=f"Slot {slot} is now locked",
        )
    except Exception as e:
        logger.error(f"Error locking slot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{slot}/unlock", response_model=SlotLockResponse)
async def unlock_slot_endpoint(slot: int):
    """Unlock a slot to allow modifications."""
    from nexus.api.save_slots import unlock_slot

    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")

    try:
        dbname = slot_dbname(slot)
        unlock_slot(slot, dbname)
        return SlotLockResponse(
            slot=slot,
            is_locked=False,
            message=f"Slot {slot} is now unlocked",
        )
    except Exception as e:
        logger.error(f"Error unlocking slot: {e}")
        raise HTTPException(status_code=500, detail=str(e))
