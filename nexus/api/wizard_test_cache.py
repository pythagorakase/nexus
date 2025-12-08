"""
Test cache loader for wizard mock server.

Loads from temp/test_cache_wizard.json (pre-parsed by user).
Provides instant cached responses for wizard phases to eliminate
API latency during UI debugging.

Usage: Select "TEST" model in the UI model picker. The backend
routes TEST model requests to the mock OpenAI server, which calls
these functions to return cached wizard data.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from nexus.api.new_story_schemas import CharacterCreationState

logger = logging.getLogger("nexus.api.wizard_test_cache")

CACHE_FILE = Path(__file__).parent.parent.parent / "temp" / "test_cache_wizard.json"

_cache: Optional[Dict[str, Any]] = None


def load_cache() -> Dict[str, Any]:
    """
    Load wizard cache from JSON file.

    The cache file contains JSON-encoded strings for each field
    (double-encoded from database export), so we parse each field.
    """
    global _cache
    if _cache is not None:
        return _cache

    if not CACHE_FILE.exists():
        raise FileNotFoundError(f"Test cache not found: {CACHE_FILE}")

    raw = json.loads(CACHE_FILE.read_text())

    # Parse JSON-encoded string fields into objects
    _cache = {}
    for key, value in raw.items():
        if isinstance(value, str) and value.startswith("{"):
            try:
                _cache[key] = json.loads(value)
            except json.JSONDecodeError:
                _cache[key] = value
        else:
            _cache[key] = value

    logger.info("[TEST MODE] Loaded wizard cache from %s", CACHE_FILE)
    return _cache


def get_cached_phase_response(phase: str, subphase: Optional[str] = None) -> Dict[str, Any]:
    """
    Get cached response for a wizard phase.

    Args:
        phase: Current wizard phase ("setting", "character", "seed")
        subphase: Character sub-phase ("concept", "traits", "wildcard")

    Returns:
        Response dict matching the format expected by InteractiveWizard.tsx
    """
    cache = load_cache()

    if phase == "setting":
        return {
            "phase_complete": True,
            "artifact_type": "submit_world_document",
            "data": cache["setting_draft"],
            "message": "[TEST MODE] World setting loaded from cache.",
            "choices": None,
        }

    elif phase == "character":
        char = cache["character_draft"]

        if subphase == "concept" or not subphase:
            return {
                "subphase_complete": True,
                "artifact_type": "submit_character_concept",
                "data": {"character_state": {"concept": char["concept"]}},
                "message": "[TEST MODE] Character concept loaded from cache.",
            }

        elif subphase == "traits":
            return {
                "subphase_complete": True,
                "artifact_type": "submit_trait_selection",
                "data": {"character_state": {"trait_selection": char["trait_selection"]}},
                "message": "[TEST MODE] Trait selection loaded from cache.",
            }

        elif subphase == "wildcard":
            creation_state = CharacterCreationState.model_validate(char)
            character_sheet = creation_state.to_character_sheet().model_dump()

            return {
                "phase_complete": True,
                "subphase_complete": True,
                "artifact_type": "submit_character_sheet",
                "data": {
                    "character_state": creation_state.model_dump(),
                    "character_sheet": character_sheet,
                },
                "message": "[TEST MODE] Character sheet loaded from cache.",
            }

    elif phase == "seed":
        return {
            "phase_complete": True,
            "artifact_type": "submit_starting_scenario",
            "data": {
                "seed": cache["selected_seed"],
                "layer": cache["layer_draft"],
                "zone": cache["zone_draft"],
                "location": cache["initial_location"],
            },
            "message": "[TEST MODE] Story seed loaded from cache.",
        }

    raise ValueError(f"Unknown phase/subphase: {phase}/{subphase}")
