"""
Shared choice handling primitives for wizard and narrative modes.

This module provides unified abstractions for:
- Parsing choice_object from database (handles str or dict)
- Validating choice indices against available options
- Resolving user input from choice number, freeform text, or accept-fate

Both wizard and narrative modes use identical choice_object structures:
    {
        "presented": ["Option 1", "Option 2", ...],
        "selected": null | {label: int|"freeform", text: str, edited: bool}
    }

This module eliminates the divergent implementations that led to:
- Wizard mode ignoring --choice validation
- Different accept-fate behavior (hardcoded string vs first choice)
- Duplicated JSON parsing logic

Note on accept-fate semantics:
    The `resolve_input_text()` function is designed for **narrative mode**, where
    accept-fate mechanically selects the first presented choice.

    **Wizard mode** handles accept-fate differently: it's a semantic signal passed
    to the LLM for autonomous generation, not a mechanical first-choice selection.
    This intentional difference exists because wizard is conversational (the LLM
    decides the outcome) while narrative requires explicit user input resolution.
"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("nexus.api.choice_handling")


# =============================================================================
# Models
# =============================================================================


class ChoiceSelection(BaseModel):
    """User's selection from presented choices."""

    label: int | Literal["freeform"] = Field(
        description="Choice number (1-indexed) or 'freeform' for custom input"
    )
    text: str = Field(description="The text of the selection (original or edited)")
    edited: bool = Field(
        default=False, description="True if user edited the choice before submitting"
    )


class ChoiceObject(BaseModel):
    """
    Structured choice data for wizard/narrative.

    This is the canonical format stored in:
    - incubator.choice_object
    - narrative_chunks.choice_object
    - assets.new_story_creator.choice_object (wizard)
    """

    presented: List[str] = Field(default_factory=list)
    selected: Optional[ChoiceSelection] = None


# =============================================================================
# Parsing Functions
# =============================================================================


def parse_choice_object(raw: Any) -> Optional[ChoiceObject]:
    """
    Parse choice_object from database (handles str, dict, or None).

    Args:
        raw: The raw value from database (may be JSON string, dict, or None)

    Returns:
        ChoiceObject if valid data present, None otherwise
    """
    if raw is None:
        return None

    # Handle JSON string (some DB drivers return strings)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse choice_object JSON: %s", raw[:100] if raw else ""
            )
            return None

    # Handle dict
    if isinstance(raw, dict):
        try:
            return ChoiceObject(
                presented=raw.get("presented", []),
                selected=_parse_selection(raw.get("selected")),
            )
        except Exception as e:
            logger.warning("Failed to construct ChoiceObject: %s", e)
            return None

    return None


def _parse_selection(raw: Any) -> Optional[ChoiceSelection]:
    """Parse the 'selected' field from choice_object."""
    if raw is None:
        return None

    if isinstance(raw, dict):
        label = raw.get("label")
        # Validate label is valid type before constructing
        if label is None:
            return None
        if not isinstance(label, int) and label != "freeform":
            return None
        try:
            return ChoiceSelection(
                label=label, text=raw.get("text", ""), edited=raw.get("edited", False)
            )
        except Exception:
            return None

    return None


def extract_presented_choices(raw: Any) -> List[str]:
    """
    Extract just the presented choices list from raw choice_object.

    Convenience function for when you only need the list, not the full object.

    Args:
        raw: The raw value from database

    Returns:
        List of presented choice strings (empty list if none)
    """
    choice_obj = parse_choice_object(raw)
    if choice_obj:
        return choice_obj.presented
    return []


# =============================================================================
# Validation Functions
# =============================================================================


def validate_choice_index(choice: int, available: List[str]) -> str:
    """
    Validate and resolve choice index to text.

    Args:
        choice: 1-indexed choice number from user
        available: List of available choice strings

    Returns:
        The choice text at the given index

    Raises:
        ValueError: If no choices available or choice out of range
    """
    if not available:
        raise ValueError("No choices available")
    if choice < 1 or choice > len(available):
        raise ValueError(f"Choice {choice} out of range (1-{len(available)})")
    return available[choice - 1]


# =============================================================================
# Resolution Functions
# =============================================================================


def resolve_input_text(
    choice: Optional[int],
    user_text: Optional[str],
    available_choices: List[str],
    accept_fate: bool = False,
) -> str:
    """
    Unified resolution: choice index → user_text → accept_fate → error.

    Priority order:
    1. If choice is provided, validate and return the choice text
    2. If user_text is provided, return it directly
    3. If accept_fate is True, return the first available choice
    4. Otherwise, raise an error

    Args:
        choice: Optional 1-indexed choice number
        user_text: Optional freeform user input
        available_choices: List of presented choices
        accept_fate: Whether to auto-select first choice

    Returns:
        The resolved input text

    Raises:
        ValueError: If no valid input can be resolved
    """
    # Priority 1: Explicit choice number
    if choice is not None:
        return validate_choice_index(choice, available_choices)

    # Priority 2: Freeform user text
    if user_text:
        return user_text

    # Priority 3: Accept fate (auto-select first choice)
    if accept_fate:
        if available_choices:
            return available_choices[0]
        raise ValueError("Cannot accept fate: no choices available")

    # No input provided
    raise ValueError("No input provided")
