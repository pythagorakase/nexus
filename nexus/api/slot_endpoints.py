"""
FastAPI endpoints for slot management operations.

This module handles slot state queries and operations including:
- Slot state retrieval
- Model get/set
- Undo operations
- Lock/unlock operations
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from nexus.config.story_model import (
    StorySettings,
    read_story_settings,
    write_story_settings,
)

from nexus.api.db_pool import get_connection
from nexus.api.narrative_schemas import (
    SlotStateResponse,
    SlotUndoResponse,
    SlotLockResponse,
    TraitMenuItemResponse,
)
from nexus.api.slot_mutations import require_writable_slot
from nexus.api.narrative_lease import discard_generation
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
                choices=state.wizard_state.choices,
                model=state.model,
            )

            # Add trait menu if in character phase, traits subphase
            ws = state.wizard_state
            if ws.phase == "character" and ws.has_concept and not ws.has_traits:
                from nexus.api.new_story_cache import (
                    get_trait_menu,
                    get_selected_trait_count,
                )

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
                story_id=state.story_id,
                has_pending=state.narrative_state.has_pending,
                frontier_clock=state.narrative_state.frontier_clock,
                storyteller_text=state.narrative_state.storyteller_text,
                choices=state.narrative_state.choices,
                session_id=state.narrative_state.session_id,
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
    require_writable_slot(slot)
    from nexus.api.slot_state import get_slot_state
    from nexus.api.new_story_cache import (
        clear_seed_phase,
        clear_character_phase,
        clear_setting_phase,
    )

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
                # Single transaction spanning incubator delete + parent's
                # choice-reset, so either both succeed or both roll back.
                # (Codex P1 review on PR #205: a previously-split version
                # left state inconsistent if revert_pending_choice raised.)
                from nexus.api.choice_recovery import clear_parent_choice

                parent_chunk_id: Optional[int] = None
                reverted_parent = False
                with get_connection(dbname) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT parent_chunk_id FROM incubator WHERE session_id = %s FOR UPDATE",
                            (narrative.session_id,),
                        )
                        row = cur.fetchone()
                        if row:
                            parent_chunk_id = row[0]

                        cur.execute(
                            "DELETE FROM incubator WHERE session_id = %s",
                            (narrative.session_id,),
                        )

                        discard_generation(cur, narrative.session_id)

                        # Reset the parent chunk's choice fields within the
                        # same cursor/transaction. Skipped for bootstrap
                        # (parent_chunk_id == 0): chunk 1 has no preceding
                        # choice to revert.
                        if parent_chunk_id and parent_chunk_id > 0:
                            clear_parent_choice(cur, parent_chunk_id)
                            reverted_parent = True

                message = (
                    f"Deleted pending content and reverted choice on chunk {parent_chunk_id}"
                    if reverted_parent
                    else "Deleted pending content"
                )
                return SlotUndoResponse(
                    success=True,
                    message=message,
                    previous_state=str(narrative.current_chunk_id),
                )

            else:
                # No pending content - the grace window has closed (last chunk
                # is now ironman / embedded under the lifecycle invariant).
                return SlotUndoResponse(
                    success=False,
                    message=(
                        "Cannot undo: no live turn. The last response is already "
                        "committed (the parent chunk is ironman / embedded)."
                    ),
                )

        return SlotUndoResponse(
            success=False,
            message="Unknown state - cannot undo",
        )

    except Exception as e:
        logger.error(f"Error in slot undo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{slot}/settings", response_model=StorySettings)
def get_slot_settings_endpoint(slot: int) -> StorySettings:
    """Return the story pins, including retired IDs so they can be cleared."""
    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")
    return read_story_settings(slot_dbname(slot))


@router.patch("/{slot}/settings", response_model=StorySettings)
def patch_slot_settings_endpoint(slot: int, patch: StorySettings) -> StorySettings:
    """Validate registry selections and persist only explicitly supplied pins."""
    if slot < 1 or slot > 5:
        raise HTTPException(status_code=400, detail="Slot must be between 1 and 5")
    require_writable_slot(slot)
    updates = patch.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No story settings provided")
    dbname = slot_dbname(slot)
    with get_connection(dbname) as conn, conn.cursor() as cur:
        try:
            write_story_settings(cur, patch)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return read_story_settings(dbname)


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
