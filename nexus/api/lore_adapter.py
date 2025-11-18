"""
LORE Adapter for Narrative API
===============================

Transforms LORE's StoryTurnResponse into incubator table format.
Handles conversion between structured Pydantic models and database JSONB fields.
"""

import logging
from typing import Dict, Any, Optional
from nexus.agents.logon.apex_schema import StorytellerResponseStandard

logger = logging.getLogger("nexus.api.lore_adapter")


def response_to_incubator(
    response: StorytellerResponseStandard,
    parent_chunk_id: int,
    user_text: str,
    session_id: str
) -> Dict[str, Any]:
    """
    Transform a LORE StorytellerResponseStandard into incubator table format.

    Args:
        response: The structured response from LORE.process_turn()
        parent_chunk_id: The parent chunk being continued from
        user_text: The user's input text
        session_id: Session ID for tracking

    Returns:
        Dictionary formatted for incubator table insertion
    """
    # Extract narrative text
    storyteller_text = response.narrative.text if hasattr(response, 'narrative') else None

    if not storyteller_text:
        raise ValueError("No narrative text in LORE response")

    # Build incubator data structure
    incubator_data = {
        "chunk_id": parent_chunk_id + 1,
        "parent_chunk_id": parent_chunk_id,
        "user_text": user_text,
        "storyteller_text": storyteller_text,
        "metadata_updates": extract_metadata_updates(response),
        "entity_updates": extract_entity_updates(response),
        "reference_updates": extract_reference_updates(response),
        "session_id": session_id,
        "llm_response_id": getattr(response, 'response_id', None),
        "status": "provisional"
    }

    return incubator_data


def extract_metadata_updates(response: StorytellerResponseStandard) -> Dict[str, Any]:
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


def extract_entity_updates(response: StorytellerResponseStandard) -> Dict[str, Any]:
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


def extract_reference_updates(response: StorytellerResponseStandard) -> Dict[str, Any]:
    """
    Extract entity references from the response.

    Tracks which characters, places, and factions are referenced or present.
    """
    reference_updates = {
        "characters": [],
        "places": [],
        "factions": []
    }

    if hasattr(response, 'referenced_entities') and response.referenced_entities:
        refs = response.referenced_entities

        # Extract character references
        if hasattr(refs, 'characters'):
            for char in refs.characters:
                ref_data = {}

                # Handle both new_character creation and existing references
                if hasattr(char, 'new_character') and char.new_character:
                    # New character to be created
                    ref_data["new_character"] = {
                        "name": char.new_character.name,
                        "summary": char.new_character.summary,
                        "appearance": char.new_character.appearance,
                        "background": char.new_character.background,
                        "personality": char.new_character.personality,
                        "emotional_state": char.new_character.emotional_state,
                        "current_activity": char.new_character.current_activity,
                        "current_location": char.new_character.current_location,
                        "extra_data": getattr(char.new_character, 'extra_data', None)
                    }
                elif char.character_id:
                    ref_data["character_id"] = char.character_id
                elif char.character_name:
                    ref_data["character_name"] = char.character_name

                ref_data["reference_type"] = (
                    char.reference_type.value
                    if hasattr(char.reference_type, 'value')
                    else char.reference_type
                )

                reference_updates["characters"].append(ref_data)

        # Extract place references
        if hasattr(refs, 'places'):
            for place in refs.places:
                ref_data = {}

                # Handle both new_place creation and existing references
                if hasattr(place, 'new_place') and place.new_place:
                    # New place to be created
                    ref_data["new_place"] = {
                        "name": place.new_place.name,
                        "summary": place.new_place.summary,
                        "history": place.new_place.history,
                        "current_status": place.new_place.current_status,
                        "secrets": place.new_place.secrets,
                        "zone": place.new_place.zone,
                        "place_type": (
                            place.new_place.place_type.value
                            if hasattr(place.new_place.place_type, 'value')
                            else place.new_place.place_type
                        ),
                        "extra_data": getattr(place.new_place, 'extra_data', None)
                    }
                elif place.place_id:
                    ref_data["place_id"] = place.place_id
                elif place.place_name:
                    ref_data["place_name"] = place.place_name

                ref_data["reference_type"] = (
                    place.reference_type.value
                    if hasattr(place.reference_type, 'value')
                    else place.reference_type
                )

                if hasattr(place, 'evidence') and place.evidence:
                    ref_data["evidence"] = place.evidence

                reference_updates["places"].append(ref_data)

        # Extract faction references
        if hasattr(refs, 'factions'):
            for faction in refs.factions:
                ref_data = {}

                # Handle both new_faction creation and existing references
                if hasattr(faction, 'new_faction') and faction.new_faction:
                    # New faction to be created
                    ref_data["new_faction"] = {
                        "name": faction.new_faction.name,
                        "summary": faction.new_faction.summary,
                        "ideology": faction.new_faction.ideology,
                        "history": faction.new_faction.history,
                        "current_activity": faction.new_faction.current_activity,
                        "hidden_agenda": faction.new_faction.hidden_agenda,
                        "territory": faction.new_faction.territory,
                        "power_level": faction.new_faction.power_level,
                        "resources": faction.new_faction.resources,
                        "primary_location": faction.new_faction.primary_location,
                        "extra_data": getattr(faction.new_faction, 'extra_data', None)
                    }
                elif faction.faction_id:
                    ref_data["faction_id"] = faction.faction_id
                elif faction.faction_name:
                    ref_data["faction_name"] = faction.faction_name

                reference_updates["factions"].append(ref_data)

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