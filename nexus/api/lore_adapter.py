"""
LORE Adapter for Narrative API
===============================

Transforms LORE's StoryTurnResponse into incubator table format.
Handles conversion between structured Pydantic models and database JSONB fields.
"""

import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from nexus.agents.logon.apex_schema import StateUpdates, StoryTurnResponse
from nexus.api.choice_handling import (
    ChoiceObject,
    normalize_choice_object,
    selected_text_from_choice_object,
)
from nexus.memory.correspondence import GeneratedCorrespondence
from nexus.memory.context_state import Pass2BaselineV1, validate_staged_pass2_baseline

logger = logging.getLogger("nexus.api.lore_adapter")

_BLEED_OFFER_MANIFEST_KEY = "_bleed_offer_resolution_ids"


def _model_to_json_dict(model: Any) -> Dict[str, Any]:
    """Serialize Pydantic models into JSON-compatible dictionaries."""

    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json", exclude_none=True)
    if isinstance(model, dict):
        return {key: value for key, value in model.items() if value is not None}
    return {}


# =============================================================================
# Choice Handling Functions
# =============================================================================


def extract_choice_object(response: StoryTurnResponse) -> Optional[ChoiceObject]:
    """
    Extract structured choice object from the response.

    Returns:
        ChoiceObject with presented choices and selected=None, or None if no choices
    """
    choices = getattr(response, "choices", None)
    if not choices or not isinstance(choices, list) or len(choices) < 2:
        return None

    return ChoiceObject(presented=choices, selected=None)


def format_choice_text(
    choice_object: Dict[str, Any], include_selection: bool = True
) -> str:
    """
    Resolve the selected user's response text from a choice object.

    Args:
        choice_object: The structured choice data
        include_selection: Whether to return the user's selection

    Returns:
        Selected response text, or an empty string if no selection is present
    """
    if not include_selection or not choice_object:
        return ""

    selected_text = selected_text_from_choice_object(choice_object)
    return selected_text or ""


def compute_raw_text(
    storyteller_text: str,
    choice_object: Optional[Dict[str, Any]],
    choice_text: Optional[str] = None,
) -> str:
    """
    Compute full raw_text by combining storyteller prose with choice text.

    This is what gets embedded and searched.

    Args:
        storyteller_text: The narrative prose from the storyteller
        choice_object: The structured choice data (may be None for legacy/freeform)
        choice_text: Resolved user response text, if already persisted

    Returns:
        Combined text for embeddings and search
    """
    resolved_choice_text = (choice_text or "").strip()
    if not resolved_choice_text and choice_object:
        resolved_choice_text = format_choice_text(choice_object, include_selection=True)

    if not resolved_choice_text:
        return storyteller_text

    return f"{storyteller_text.rstrip()}\n\n{resolved_choice_text}"


def extract_orrery_adjudications(response: StoryTurnResponse) -> List[Dict[str, Any]]:
    """Extract optional Skald rulings for current-tick Orrery proposals."""

    adjudications = getattr(response, "orrery_adjudications", None) or []
    serialized = []
    for adjudication in adjudications:
        data = _model_to_json_dict(adjudication)
        if data:
            serialized.append(data)
    return serialized


def extract_new_entities(response: StoryTurnResponse) -> List[Dict[str, Any]]:
    """Extract Skald new-entity declarations for Retrograde stub maturation."""

    declarations = getattr(response, "new_entities", None) or []
    serialized = []
    for declaration in declarations:
        data = _model_to_json_dict(declaration)
        if data:
            serialized.append(data)
    return serialized


def response_to_incubator(
    response: StoryTurnResponse,
    parent_chunk_id: int,
    user_text: str,
    session_id: str,
    lore_pass_baseline: Pass2BaselineV1,
    orrery_proposal: Optional[Any] = None,
    bleed_offer_resolution_ids: Iterable[int] = (),
    correspondence: Optional[GeneratedCorrespondence] = None,
) -> Dict[str, Any]:
    """
    Transform a LORE StoryTurnResponse into incubator table format.

    Args:
        response: The structured response from LORE.process_turn()
        parent_chunk_id: The parent chunk being continued from
        user_text: The user's input text
        session_id: Session ID for tracking
        lore_pass_baseline: Unbound durable Pass-1 state for the generated prose
        orrery_proposal: Optional no-write Orrery proposal from TurnContext
        bleed_offer_resolution_ids: Resolutions offered to this exact draft

    Returns:
        Dictionary formatted for incubator table insertion
    """
    # Extract narrative text
    storyteller_text = response.narrative if hasattr(response, "narrative") else None

    if not storyteller_text:
        raise ValueError("No narrative text in LORE response")

    generation_model = getattr(response, "generation_model", None)
    staged_baseline = validate_staged_pass2_baseline(lore_pass_baseline)

    # Extract choice object (presented choices, no selection yet)
    choice_obj = extract_choice_object(response)
    # Convert to dict for database JSONB storage (None if no choices)
    choice_object_dict = (
        normalize_choice_object(choice_obj.model_dump()) if choice_obj else None
    )

    # Build incubator data structure
    incubator_data = {
        "chunk_id": parent_chunk_id + 1,
        "parent_chunk_id": parent_chunk_id,
        "user_text": user_text,
        "storyteller_text": storyteller_text,
        "generation_model": generation_model,
        "choice_object": choice_object_dict,  # Structured choices data
        "choice_text": None,  # Generated when user makes selection
        "metadata_updates": extract_metadata_updates(response),
        "entity_updates": extract_entity_updates(response),
        "reference_updates": extract_reference_updates(response),
        "orrery_proposal": _serialize_orrery_staging(
            orrery_proposal,
            bleed_offer_resolution_ids=bleed_offer_resolution_ids,
        ),
        "orrery_adjudications": extract_orrery_adjudications(response),
        "new_entities": extract_new_entities(response),
        "correspondence_writer_letter": (
            correspondence.writer_letter if correspondence is not None else None
        ),
        "correspondence_gaia_letter": (
            correspondence.gaia_letter if correspondence is not None else None
        ),
        "lore_pass_baseline": staged_baseline.model_dump(mode="json"),
        "session_id": session_id,
        "llm_response_id": getattr(response, "response_id", None),
        "status": "provisional",
    }

    return incubator_data


def _serialize_orrery_proposal(proposal: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Serialize an optional Orrery proposal for incubator JSONB storage."""

    if proposal is None:
        return None
    if hasattr(proposal, "to_dict"):
        return proposal.to_dict()
    if isinstance(proposal, dict):
        return proposal
    raise TypeError(f"Unsupported Orrery proposal type: {type(proposal).__name__}")


def _serialize_orrery_staging(
    proposal: Optional[Any],
    *,
    bleed_offer_resolution_ids: Iterable[int],
) -> Dict[str, Any]:
    """Stage an Orrery proposal and exact-draft Bleed manifest in one JSONB value."""

    payload = _serialize_orrery_proposal(proposal) or {}
    raw_resolution_ids = tuple(bleed_offer_resolution_ids)
    if any(
        isinstance(resolution_id, bool) or not isinstance(resolution_id, int)
        for resolution_id in raw_resolution_ids
    ):
        raise ValueError("Bleed offer resolution ids must be integers")
    resolution_ids = tuple(raw_resolution_ids)
    if any(resolution_id <= 0 for resolution_id in resolution_ids):
        raise ValueError("Bleed offer resolution ids must be positive integers")
    if len(set(resolution_ids)) != len(resolution_ids):
        raise ValueError("Bleed offer resolution ids must be unique")
    return {
        **payload,
        _BLEED_OFFER_MANIFEST_KEY: list(resolution_ids),
    }


def split_staged_orrery_payload(
    value: Optional[Mapping[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Tuple[int, ...]]:
    """Separate the canonical proposal from its exact-draft Bleed manifest."""

    if value is None:
        return None, ()
    payload = dict(value)
    raw_resolution_ids = payload.pop(_BLEED_OFFER_MANIFEST_KEY, None)
    if raw_resolution_ids is None:
        return payload or None, ()
    if not isinstance(raw_resolution_ids, list):
        raise ValueError("Staged Bleed offer manifest must be a JSON array")
    if any(
        isinstance(resolution_id, bool) or not isinstance(resolution_id, int)
        for resolution_id in raw_resolution_ids
    ):
        raise ValueError("Staged Bleed offer manifest ids must be integers")
    resolution_ids = tuple(raw_resolution_ids)
    if any(resolution_id <= 0 for resolution_id in resolution_ids):
        raise ValueError("Staged Bleed offer manifest ids must be positive")
    if len(set(resolution_ids)) != len(resolution_ids):
        raise ValueError("Staged Bleed offer manifest ids must be unique")
    return payload or None, resolution_ids


def extract_metadata_updates(response: StoryTurnResponse) -> Dict[str, Any]:
    """
    Extract metadata updates from the response.

    Includes chronology (time changes), world layer, and episode transitions.
    """
    metadata_updates: Dict[str, Any] = {}

    metadata = getattr(response, "chunk_metadata", None) or getattr(
        response, "metadata", None
    )

    if metadata:

        # Extract chronology updates with new time field structure
        if hasattr(metadata, "chronology") and metadata.chronology:
            chron = metadata.chronology

            # Handle both old boolean format and new enum format
            if hasattr(chron, "episode_transition"):
                # New format with enum
                episode_transition = (
                    chron.episode_transition.value
                    if hasattr(chron.episode_transition, "value")
                    else chron.episode_transition or "continue"
                )
            else:
                # Old format with boolean flags
                if getattr(chron, "season_increment", False):
                    episode_transition = "new_season"
                elif getattr(chron, "episode_increment", False):
                    episode_transition = "new_episode"
                else:
                    episode_transition = "continue"

            metadata_updates["chronology"] = {
                "episode_transition": episode_transition,
                "time_delta_minutes": getattr(chron, "time_delta_minutes", None),
                "time_delta_hours": getattr(chron, "time_delta_hours", None),
                "time_delta_days": getattr(chron, "time_delta_days", None),
                "time_delta_description": getattr(chron, "time_delta_description", None)
                or getattr(chron, "time_elapsed_description", None),
            }

        # Extract world layer
        if hasattr(metadata, "world_layer"):
            metadata_updates["world_layer"] = (
                metadata.world_layer.value
                if hasattr(metadata.world_layer, "value")
                else metadata.world_layer or "primary"
            )

        # The Skald's in-scene weather override must survive extraction or
        # the chunk_metadata.scene_weather column is write-only-NULL in
        # production (every response field that skips this function is
        # silently dropped before commit).
        scene_weather = getattr(metadata, "scene_weather", None)
        if scene_weather is not None:
            metadata_updates["scene_weather"] = scene_weather

    return metadata_updates


def extract_entity_updates(response: StoryTurnResponse) -> Dict[str, Any]:
    """Serialize the complete canonical state-update contract for commit."""

    state_updates = getattr(response, "state_updates", None) or StateUpdates()
    return state_updates.model_dump(mode="json", exclude_none=True)


def extract_reference_updates(response: StoryTurnResponse) -> Dict[str, Any]:
    """
    Extract entity references from the response.

    Tracks which characters, places, and factions are referenced or present.
    """
    reference_updates: Dict[str, List[Dict[str, Any]]] = {
        "characters": [],
        "places": [],
        "factions": [],
    }

    refs = getattr(response, "referenced_entities", None)
    if not refs:
        return reference_updates

    for char in getattr(refs, "characters", []):
        ref_data = _model_to_json_dict(char)
        if ref_data:
            reference_updates["characters"].append(ref_data)

    for place in getattr(refs, "places", []):
        ref_data = _model_to_json_dict(place)
        if ref_data:
            reference_updates["places"].append(ref_data)

    for faction in getattr(refs, "factions", []):
        ref_data = _model_to_json_dict(faction)
        if ref_data:
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
        "lore_pass_baseline",
        "session_id",
        "status",
    ]

    for field in required_fields:
        if field not in incubator_data:
            raise ValueError(f"Missing required field: {field}")

    if not incubator_data["storyteller_text"]:
        raise ValueError("Storyteller text cannot be empty")

    validate_staged_pass2_baseline(incubator_data["lore_pass_baseline"])

    if incubator_data["chunk_id"] <= incubator_data["parent_chunk_id"]:
        raise ValueError("Chunk ID must be greater than parent chunk ID")

    return True
