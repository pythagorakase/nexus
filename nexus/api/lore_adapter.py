"""
LORE Adapter for Narrative API
===============================

Transforms LORE's StoryTurnResponse into incubator table format.
Handles conversion between structured Pydantic models and database JSONB fields.
"""

import logging
from typing import Dict, Any, Optional, List
from nexus.agents.logon.apex_schema import StoryTurnResponse

logger = logging.getLogger("nexus.api.lore_adapter")


# =============================================================================
# Choice Handling Functions
# =============================================================================

def extract_choice_object(response: StoryTurnResponse) -> Optional[Dict[str, Any]]:
    """
    Extract structured choice object from the response.

    Returns:
        Dictionary with {presented: [...], selected: null} or None if no choices
    """
    choices = getattr(response, 'choices', None)
    if not choices or not isinstance(choices, list) or len(choices) < 2:
        return None

    return {
        "presented": choices,
        "selected": None  # Will be populated when user makes selection
    }


def format_choice_text(
    choice_object: Dict[str, Any],
    include_selection: bool = True
) -> str:
    """
    Generate markdown-formatted text from choice object.

    Args:
        choice_object: The structured choice data
        include_selection: Whether to include the user's selection

    Returns:
        Markdown-formatted string representing choices and selection
    """
    if not choice_object or not choice_object.get("presented"):
        return ""

    lines = ["", "**Your options were:**"]

    # List all presented choices
    for i, choice in enumerate(choice_object["presented"], 1):
        lines.append(f"{i}. {choice}")

    # Add user selection if present
    if include_selection and choice_object.get("selected"):
        selected = choice_object["selected"]
        label = selected.get("label")
        text = selected.get("text", "")
        edited = selected.get("edited", False)

        lines.append("")

        if label == "freeform":
            lines.append(f'**You chose:** "{text}"')
        elif edited:
            lines.append(f'**You chose:** "{text}" (edited from option {label})')
        else:
            lines.append(f"**You chose:** Option {label}")

    return "\n".join(lines)


def compute_raw_text(
    storyteller_text: str,
    choice_object: Optional[Dict[str, Any]]
) -> str:
    """
    Compute full raw_text by combining storyteller prose with choice text.

    This is what gets embedded and searched.

    Args:
        storyteller_text: The narrative prose from the storyteller
        choice_object: The structured choice data (may be None for legacy/freeform)

    Returns:
        Combined text for embeddings and search
    """
    if not choice_object or not choice_object.get("selected"):
        # No choices or selection not yet made - just use storyteller text
        return storyteller_text

    choice_text = format_choice_text(choice_object, include_selection=True)
    if choice_text:
        return storyteller_text + "\n" + choice_text

    return storyteller_text


def response_to_incubator(
    response: StoryTurnResponse,
    parent_chunk_id: int,
    user_text: str,
    session_id: str
) -> Dict[str, Any]:
    """
    Transform a LORE StoryTurnResponse into incubator table format.

    Args:
        response: The structured response from LORE.process_turn()
        parent_chunk_id: The parent chunk being continued from
        user_text: The user's input text
        session_id: Session ID for tracking

    Returns:
        Dictionary formatted for incubator table insertion
    """
    # Extract narrative text
    storyteller_text = response.narrative if hasattr(response, 'narrative') else None

    if not storyteller_text:
        raise ValueError("No narrative text in LORE response")

    # Extract choice object (presented choices, no selection yet)
    choice_object = extract_choice_object(response)

    # Build incubator data structure
    incubator_data = {
        "chunk_id": parent_chunk_id + 1,
        "parent_chunk_id": parent_chunk_id,
        "user_text": user_text,
        "storyteller_text": storyteller_text,
        "choice_object": choice_object,  # Structured choices data
        "choice_text": None,  # Generated when user makes selection
        "metadata_updates": extract_metadata_updates(response),
        "entity_updates": extract_entity_updates(response),
        "reference_updates": extract_reference_updates(response),
        "session_id": session_id,
        "llm_response_id": getattr(response, 'response_id', None),
        "status": "provisional"
    }

    return incubator_data


def extract_metadata_updates(response: StoryTurnResponse) -> Dict[str, Any]:
    """
    Extract metadata updates from the response.

    Includes chronology (time changes), world layer, and episode transitions.
    """
    metadata_updates = {}

    if hasattr(response, 'metadata') and response.metadata:
        metadata = response.metadata

        # Extract chronology updates with new time field structure
        if hasattr(metadata, 'chronology') and metadata.chronology:
            chron = metadata.chronology

            # Handle both old boolean format and new enum format
            if hasattr(chron, 'episode_transition'):
                # New format with enum
                episode_transition = (
                    chron.episode_transition.value
                    if hasattr(chron.episode_transition, 'value')
                    else chron.episode_transition or "continue"
                )
            else:
                # Old format with boolean flags
                if getattr(chron, 'season_increment', False):
                    episode_transition = "new_season"
                elif getattr(chron, 'episode_increment', False):
                    episode_transition = "new_episode"
                else:
                    episode_transition = "continue"

            metadata_updates["chronology"] = {
                "episode_transition": episode_transition,
                "time_delta_minutes": getattr(chron, 'time_delta_minutes', None),
                "time_delta_hours": getattr(chron, 'time_delta_hours', None),
                "time_delta_days": getattr(chron, 'time_delta_days', None),
                "time_delta_description": getattr(chron, 'time_delta_description', None) or getattr(chron, 'time_elapsed_description', None)
            }

        # Extract world layer
        if hasattr(metadata, 'world_layer'):
            metadata_updates["world_layer"] = (
                metadata.world_layer.value
                if hasattr(metadata.world_layer, 'value')
                else metadata.world_layer or "primary"
            )

    return metadata_updates


def extract_entity_updates(response: StoryTurnResponse) -> Dict[str, Any]:
    """
    Extract entity state updates from the response.

    Includes character emotional states, location statuses, and faction activities.
    """
    entity_updates = {
        "characters": [],
        "locations": [],
        "factions": []
    }

    if hasattr(response, 'state_updates') and response.state_updates:
        # Extract character updates
        if hasattr(response.state_updates, 'characters'):
            for char in response.state_updates.characters:
                update = {
                    "character_id": char.character_id
                }

                # Only include fields that are actually set
                if hasattr(char, 'character_name') and char.character_name:
                    update["character_name"] = char.character_name
                if hasattr(char, 'emotional_state') and char.emotional_state:
                    update["emotional_state"] = char.emotional_state
                if hasattr(char, 'current_activity') and char.current_activity:
                    update["current_activity"] = char.current_activity
                if hasattr(char, 'current_location') and char.current_location:
                    update["current_location"] = char.current_location

                entity_updates["characters"].append(update)

        # Extract location updates
        if hasattr(response.state_updates, 'locations'):
            for loc in response.state_updates.locations:
                update = {
                    "place_id": loc.place_id
                }

                if hasattr(loc, 'place_name') and loc.place_name:
                    update["place_name"] = loc.place_name
                if hasattr(loc, 'current_status') and loc.current_status:
                    update["current_status"] = loc.current_status

                entity_updates["locations"].append(update)

        # Extract faction updates
        if hasattr(response.state_updates, 'factions'):
            for faction in response.state_updates.factions:
                update = {
                    "faction_id": faction.faction_id
                }

                if hasattr(faction, 'faction_name') and faction.faction_name:
                    update["faction_name"] = faction.faction_name
                if hasattr(faction, 'current_activity') and faction.current_activity:
                    update["current_activity"] = faction.current_activity

                entity_updates["factions"].append(update)

    return entity_updates


def extract_reference_updates(response: StoryTurnResponse) -> Dict[str, Any]:
    """
    Extract entity references from the response.

    Tracks which characters, places, and factions are referenced or present.
    """
    reference_updates = {
        "characters": [],
        "places": [],
        "factions": []
    }

    refs = getattr(response, "referenced_entities", None)
    if not refs:
        return reference_updates

    def _append_reference(
        entity: Any,
        id_key: str,
        name_key: str,
        target_list: list
    ) -> None:
        ref_data: Dict[str, Any] = {}
        entity_id = getattr(entity, "entity_id", None)
        if entity_id is not None:
            ref_data[id_key] = entity_id
        entity_name = getattr(entity, "entity_name", None)
        if entity_name:
            ref_data[name_key] = entity_name
        prominence = getattr(entity, "prominence", None)
        if prominence:
            ref_data["reference_type"] = prominence
        target_list.append(ref_data)

    for char in getattr(refs, "characters", []):
        _append_reference(char, "character_id", "character_name", reference_updates["characters"])

    for location in getattr(refs, "locations", []):
        _append_reference(location, "place_id", "place_name", reference_updates["places"])

    # Factions are reported through the generic "other" list in StoryTurnResponse
    for entity in getattr(refs, "other", []):
        if getattr(entity, "entity_type", None) == "faction":
            _append_reference(entity, "faction_id", "faction_name", reference_updates["factions"])

    return reference_updates


def validate_incubator_data(incubator_data: Dict[str, Any]) -> bool:
    """
    Validate that incubator data has all required fields.

    Args:
        incubator_data: The data to validate

    Returns:
        True if valid

    Raises:
        ValueError: If validation fails
    """
    required_fields = [
        "chunk_id",
        "parent_chunk_id",
        "user_text",
        "storyteller_text",
        "metadata_updates",
        "entity_updates",
        "reference_updates",
        "session_id",
        "status"
    ]

    for field in required_fields:
        if field not in incubator_data:
            raise ValueError(f"Missing required field: {field}")

    if not incubator_data["storyteller_text"]:
        raise ValueError("Storyteller text cannot be empty")

    if incubator_data["chunk_id"] <= incubator_data["parent_chunk_id"]:
        raise ValueError("Chunk ID must be greater than parent chunk ID")

    return True