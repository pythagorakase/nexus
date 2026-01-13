"""
Slot state resolution for the simplified CLI.

This module provides functions to determine the current state of a save slot
from just the slot number. The backend resolves all state internally:

- Wizard vs Narrative mode: derived from data presence
- Current wizard phase: inferred from normalized column presence
- Thread ID: from new_story_creator.thread_id
- Current narrative chunk: MAX(id) from narrative_chunks or incubator
- Available choices: from last response's choice_object

Phase detection uses normalized columns (no JSON introspection):
- Setting complete: setting_genre IS NOT NULL
- Character complete: wildcard_name IS NOT NULL
- Seed complete: seed_type IS NOT NULL
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from nexus.api.db_pool import get_connection
from nexus.api.slot_utils import slot_dbname

logger = logging.getLogger("nexus.api.slot_state")


@dataclass
class WizardState:
    """State for a slot in wizard mode."""

    phase: str  # "setting", "character", "seed", or "ready"
    thread_id: Optional[str]
    # Character subphase tracking
    has_concept: bool = False
    has_traits: bool = False
    has_wildcard: bool = False


@dataclass
class NarrativeState:
    """State for a slot in narrative mode."""

    current_chunk_id: int
    has_pending: bool  # True if incubator has unapproved content
    storyteller_text: Optional[str]
    choices: List[str]  # Available choices from choice_object.presented
    session_id: Optional[str]  # Incubator session ID if pending


@dataclass
class SlotState:
    """
    Complete state for a save slot.

    Either wizard_state or narrative_state will be set, not both.
    If both are None, the slot is empty/uninitialized.
    """

    slot: int
    is_empty: bool
    is_wizard_mode: bool
    wizard_state: Optional[WizardState]
    narrative_state: Optional[NarrativeState]
    model: Optional[str]  # Current model for this slot


def get_slot_state(slot: int) -> SlotState:
    """
    Get the complete state for a save slot.

    Resolves all internal state from just the slot number:
    - Whether slot is empty or initialized
    - Whether in wizard or narrative mode
    - Current wizard phase or narrative position
    - Available choices

    Mode is derived from data presence (not from a flag):
    - Wizard mode: wizard cache exists in assets.new_story_creator
    - Narrative mode: narrative_chunks exist
    - Empty: neither exists

    Args:
        slot: Save slot number (1-5)

    Returns:
        SlotState containing all resolved state information
    """
    dbname = slot_dbname(slot)

    with get_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            # Get model from save_slots table
            cur.execute(
                "SELECT model FROM assets.save_slots WHERE slot_number = %s", (slot,)
            )
            slot_row = cur.fetchone()
            current_model = slot_row.get("model") if slot_row else None

            # Check for wizard cache (derives wizard mode)
            # Only select the columns we need for phase detection
            cur.execute(
                """
                SELECT thread_id,
                       setting_genre,
                       character_name, character_trait1, wildcard_name,
                       seed_type
                FROM assets.new_story_creator
                WHERE id = TRUE
                """
            )
            wizard_cache = cur.fetchone()

            # Check for narrative chunks (derives narrative mode)
            cur.execute("SELECT COUNT(*) as count FROM narrative_chunks")
            chunk_count = cur.fetchone().get("count", 0)

            # Also check incubator for pending bootstrap
            cur.execute("SELECT COUNT(*) as count FROM incubator")
            incubator_count = cur.fetchone().get("count", 0)

            has_wizard_data = wizard_cache is not None
            has_narrative_data = chunk_count > 0 or incubator_count > 0

            # Derive mode from data presence
            if has_wizard_data and not has_narrative_data:
                # Wizard mode: cache exists, no narrative yet
                wizard_state = _get_wizard_state_from_row(wizard_cache)
                return SlotState(
                    slot=slot,
                    is_empty=False,
                    is_wizard_mode=True,
                    wizard_state=wizard_state,
                    narrative_state=None,
                    model=current_model,
                )
            elif has_narrative_data:
                # Narrative mode: chunks or incubator exist
                narrative_state = _get_narrative_state(cur)
                return SlotState(
                    slot=slot,
                    is_empty=False,
                    is_wizard_mode=False,
                    wizard_state=None,
                    narrative_state=narrative_state,
                    model=current_model,
                )
            else:
                # Empty slot: no wizard cache and no narrative
                return SlotState(
                    slot=slot,
                    is_empty=True,
                    is_wizard_mode=False,
                    wizard_state=None,
                    narrative_state=None,
                    model=current_model,
                )


def _get_wizard_state_from_row(row: dict) -> WizardState:
    """
    Get wizard state from a new_story_creator row.

    Phase is inferred from normalized column nullability:
    - setting_genre IS NULL → "setting" phase
    - wildcard_name IS NULL → "character" phase (with subphase tracking)
    - seed_type IS NULL → "seed" phase
    - All non-null → "ready" for bootstrap
    """
    # Direct column checks - no JSON parsing needed!
    setting_complete = row.get("setting_genre") is not None

    # Character subphase tracking
    has_concept = row.get("character_name") is not None
    has_traits = row.get("character_trait1") is not None
    has_wildcard = row.get("wildcard_name") is not None
    character_complete = has_concept and has_traits and has_wildcard

    seed_complete = row.get("seed_type") is not None

    # Infer phase
    if not setting_complete:
        phase = "setting"
    elif not character_complete:
        phase = "character"
    elif not seed_complete:
        phase = "seed"
    else:
        phase = "ready"

    return WizardState(
        phase=phase,
        thread_id=row.get("thread_id"),
        has_concept=has_concept,
        has_traits=has_traits,
        has_wildcard=has_wildcard,
    )


def _get_wizard_state(cur) -> WizardState:
    """
    Get wizard state from new_story_creator cache.
    """
    cur.execute(
        """
        SELECT thread_id,
               setting_genre,
               character_name, character_trait1, wildcard_name,
               seed_type
        FROM assets.new_story_creator
        WHERE id = TRUE
        """
    )
    row = cur.fetchone()

    if row is None:
        return WizardState(
            phase="setting",
            thread_id=None,
            has_concept=False,
            has_traits=False,
            has_wildcard=False,
        )

    return _get_wizard_state_from_row(row)


def _get_narrative_state(cur) -> NarrativeState:
    """
    Get narrative state from incubator and narrative_chunks.

    Checks incubator first for pending content, then falls back
    to the latest committed chunk.
    """
    # Check for pending content in incubator
    cur.execute(
        """
        SELECT session_id, chunk_id, storyteller_text, choice_object
        FROM incubator
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    incubator_row = cur.fetchone()

    if incubator_row:
        choice_object = _parse_json(incubator_row.get("choice_object"))
        choices = choice_object.get("presented", []) if choice_object else []

        return NarrativeState(
            current_chunk_id=incubator_row.get("chunk_id") or 0,
            has_pending=True,
            storyteller_text=incubator_row.get("storyteller_text"),
            choices=choices,
            session_id=incubator_row.get("session_id"),
        )

    # No pending content - get latest committed chunk
    cur.execute(
        """
        SELECT nc.id, nc.raw_text
        FROM narrative_chunks nc
        ORDER BY nc.id DESC
        LIMIT 1
        """
    )
    chunk_row = cur.fetchone()

    if chunk_row:
        # Get choices from the last chunk's choice_object if stored
        # Note: committed chunks may not have choice_object preserved
        return NarrativeState(
            current_chunk_id=chunk_row.get("id"),
            has_pending=False,
            storyteller_text=chunk_row.get("raw_text"),
            choices=[],  # No pending choices for committed chunks
            session_id=None,
        )

    # No narrative content at all (bootstrap hasn't happened yet)
    return NarrativeState(
        current_chunk_id=0,
        has_pending=False,
        storyteller_text=None,
        choices=[],
        session_id=None,
    )


def _parse_json(value: Any) -> Optional[Dict[str, Any]]:
    """Parse a JSON value that may be a string, dict, or None."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON: %s", value[:100] if value else "")
            return None
    return None


def get_current_choices(slot: int) -> List[str]:
    """
    Get available choices for a slot.

    Returns the choice_object.presented list from the last response,
    or an empty list if no choices are available.

    Args:
        slot: Save slot number (1-5)

    Returns:
        List of choice strings
    """
    state = get_slot_state(slot)

    if state.is_empty:
        return []

    if state.is_wizard_mode:
        # Wizard doesn't have structured choices in the same way
        # Return empty - wizard uses freeform chat
        return []

    if state.narrative_state:
        return state.narrative_state.choices

    return []


def resolve_continue_action(
    slot: int,
    choice: Optional[int] = None,
    user_text: Optional[str] = None,
    accept_fate: bool = False,
) -> Dict[str, Any]:
    """
    Resolve which action to take for a continue request.

    Determines whether to route to wizard chat or narrative continuation,
    and builds the appropriate request parameters.

    Args:
        slot: Save slot number (1-5)
        choice: Structured choice number (1-indexed)
        user_text: Freeform user input
        accept_fate: Auto-advance flag

    Returns:
        Dictionary with action type and parameters:
        {
            "action": "wizard_chat" | "narrative_continue" | "initialize",
            "params": {...}
        }

    Raises:
        ValueError: If choice is invalid or state is inconsistent
    """
    state = get_slot_state(slot)

    if state.is_empty:
        # Slot needs initialization
        return {
            "action": "initialize",
            "params": {"slot": slot},
        }

    if state.is_wizard_mode:
        # Route to wizard chat
        wizard = state.wizard_state
        if wizard is None:
            raise ValueError(f"Slot {slot} is in wizard mode but has no wizard state")

        # Resolve input text
        input_text = user_text
        if accept_fate and not input_text:
            input_text = "Accept my fate"  # Triggers auto-advance in wizard

        return {
            "action": "wizard_chat",
            "params": {
                "slot": slot,
                "thread_id": wizard.thread_id,
                "phase": wizard.phase,
                "message": input_text or "",
                "accept_fate": accept_fate,
                "model": state.model,
            },
        }

    # Narrative mode
    narrative = state.narrative_state
    if narrative is None:
        raise ValueError(f"Slot {slot} is in narrative mode but has no narrative state")

    # Resolve input text from choice or user_text
    input_text = user_text
    if choice is not None:
        if not narrative.choices:
            raise ValueError(f"No choices available for slot {slot}")
        if choice < 1 or choice > len(narrative.choices):
            raise ValueError(
                f"Invalid choice {choice}. Available choices: 1-{len(narrative.choices)}"
            )
        input_text = narrative.choices[choice - 1]  # Convert to 0-indexed

    if accept_fate and not input_text:
        # Auto-select first choice
        if narrative.choices:
            input_text = narrative.choices[0]
        else:
            raise ValueError("Cannot accept fate: no choices available")

    return {
        "action": "narrative_continue",
        "params": {
            "slot": slot,
            "chunk_id": narrative.current_chunk_id,
            "user_text": input_text or "",
            "model": state.model,
            "session_id": narrative.session_id,  # For implicit approval
        },
    }
