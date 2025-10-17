"""
Structured Output Schemas for LOGON

Defines Pydantic models for structured responses from Apex AI providers.
These schemas enable the Apex AI to return:
1. Narrative prose
2. Chunk metadata (chronology, continuity, etc.)
3. Entity state updates (for GAIA/PSYCHE)
4. Operations (episode/season transitions, summaries)
5. Referenced entities

All models use Pydantic v2 for validation and serialization.
"""

import logging
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger("nexus.lore.logon_schemas")


# ============================================================================
# Entity References
# ============================================================================

class ReferencedEntity(BaseModel):
    """
    A single entity (character, location, event, etc.) referenced in the narrative.
    """
    entity_type: Literal["character", "location", "event", "threat", "faction", "item"] = Field(
        description="Type of entity referenced"
    )
    entity_id: Optional[int] = Field(
        default=None,
        description="Database ID of the entity, if known"
    )
    entity_name: str = Field(
        description="Name of the entity"
    )
    prominence: Literal["primary", "secondary", "mentioned"] = Field(
        default="mentioned",
        description="How prominently the entity appears in this narrative chunk"
    )

    class Config:
        extra = "forbid"


class ReferencedEntities(BaseModel):
    """
    Collection of all entities referenced in the narrative chunk.
    This helps LORE understand what was actually present/mentioned for context tracking.
    """
    characters: List[ReferencedEntity] = Field(
        default_factory=list,
        description="Characters present or mentioned in this chunk"
    )
    locations: List[ReferencedEntity] = Field(
        default_factory=list,
        description="Locations present or mentioned in this chunk"
    )
    events: List[ReferencedEntity] = Field(
        default_factory=list,
        description="Events referenced or occurring in this chunk"
    )
    threats: List[ReferencedEntity] = Field(
        default_factory=list,
        description="Threats present or mentioned in this chunk"
    )
    other: List[ReferencedEntity] = Field(
        default_factory=list,
        description="Other entities (factions, items, etc.)"
    )

    class Config:
        extra = "forbid"


# ============================================================================
# Chunk Metadata
# ============================================================================

class ChronologyUpdate(BaseModel):
    """
    Updates to narrative chronology (episode, season, date, time).
    """
    episode_increment: bool = Field(
        default=False,
        description="Whether this chunk marks a new episode"
    )
    season_increment: bool = Field(
        default=False,
        description="Whether this chunk marks a new season"
    )
    in_world_date: Optional[str] = Field(
        default=None,
        description="In-world date for this chunk (format: DDMMMYYYY, e.g., 18OCT2073)"
    )
    in_world_time: Optional[str] = Field(
        default=None,
        description="In-world time for this chunk (format: HH:MM, e.g., 19:45)"
    )
    time_elapsed_description: Optional[str] = Field(
        default=None,
        description="Human-readable description of time elapsed since last chunk"
    )

    class Config:
        extra = "forbid"


class NarrativeVectorUpdate(BaseModel):
    """
    Updates to narrative arc position and momentum.
    """
    arc_position: Optional[Literal[
        "exposition",
        "rising_action",
        "complication",
        "climax",
        "falling_action",
        "resolution"
    ]] = Field(
        default=None,
        description="Current position in narrative arc"
    )
    tension_level: Optional[int] = Field(
        default=None,
        ge=1,
        le=10,
        description="Current tension level (1-10)"
    )
    pacing: Optional[Literal["fast", "medium", "slow", "reflective"]] = Field(
        default=None,
        description="Pacing of this narrative chunk"
    )

    class Config:
        extra = "forbid"


class ContinuityMarker(BaseModel):
    """
    A single continuity marker linking to past events or narrative threads.
    """
    marker_type: Literal["callback", "setup", "payoff", "parallel", "contradiction"] = Field(
        description="Type of continuity marker"
    )
    description: str = Field(
        description="Description of what is being referenced or set up"
    )
    chunk_id_reference: Optional[int] = Field(
        default=None,
        description="ID of chunk being referenced, if applicable"
    )

    class Config:
        extra = "forbid"


class ChunkMetadataUpdate(BaseModel):
    """
    Metadata updates for the narrative chunk.
    These fields map to the narrative metadata schema.
    """
    chronology: Optional[ChronologyUpdate] = Field(
        default=None,
        description="Updates to narrative chronology"
    )
    narrative_vector: Optional[NarrativeVectorUpdate] = Field(
        default=None,
        description="Updates to narrative arc and momentum"
    )
    perspective: Optional[str] = Field(
        default=None,
        description="POV perspective for this chunk (usually 'Alex - 2nd person')"
    )
    continuity_markers: List[ContinuityMarker] = Field(
        default_factory=list,
        description="Continuity markers for this chunk"
    )
    thematic_elements: List[str] = Field(
        default_factory=list,
        description="Thematic elements present in this chunk"
    )
    tone: Optional[Literal[
        "action",
        "dialogue",
        "introspection",
        "suspense",
        "revelation",
        "transition"
    ]] = Field(
        default=None,
        description="Dominant tone of this chunk"
    )

    class Config:
        extra = "forbid"


# ============================================================================
# Entity State Updates
# ============================================================================

class CharacterStateUpdate(BaseModel):
    """
    Update to a single character's state.
    """
    character_id: Optional[int] = Field(
        default=None,
        description="Database ID of character, if known"
    )
    character_name: str = Field(
        description="Name of character"
    )
    current_location: Optional[str] = Field(
        default=None,
        description="Character's current location"
    )
    emotional_state: Optional[str] = Field(
        default=None,
        description="Character's current emotional state"
    )
    physical_condition: Optional[str] = Field(
        default=None,
        description="Character's physical condition/injuries"
    )
    goals: Optional[List[str]] = Field(
        default=None,
        description="Character's current goals or motivations"
    )
    knowledge_gained: Optional[List[str]] = Field(
        default=None,
        description="New information the character learned"
    )

    class Config:
        extra = "forbid"


class RelationshipUpdate(BaseModel):
    """
    Update to a relationship between two characters.
    """
    character1_name: str = Field(description="First character name")
    character2_name: str = Field(description="Second character name")
    relationship_type: Optional[str] = Field(
        default=None,
        description="Type of relationship (ally, friend, enemy, etc.)"
    )
    trust_level: Optional[int] = Field(
        default=None,
        ge=1,
        le=10,
        description="Trust level (1-10)"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Notes about relationship change"
    )

    class Config:
        extra = "forbid"


class StateUpdates(BaseModel):
    """
    Collection of all state updates for GAIA and PSYCHE.
    """
    characters: List[CharacterStateUpdate] = Field(
        default_factory=list,
        description="Character state updates"
    )
    relationships: List[RelationshipUpdate] = Field(
        default_factory=list,
        description="Relationship updates"
    )
    world_state_notes: Optional[str] = Field(
        default=None,
        description="General notes about world state changes"
    )

    class Config:
        extra = "forbid"


# ============================================================================
# Operations
# ============================================================================

class SummaryRequest(BaseModel):
    """
    Request for an episode or season summary.
    """
    summary_type: Literal["episode", "season"] = Field(
        description="Type of summary needed"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Reason for requesting summary"
    )

    class Config:
        extra = "forbid"


class RegenerationRequest(BaseModel):
    """
    Request to regenerate this narrative chunk.
    """
    reason: str = Field(
        description="Reason for requesting regeneration"
    )
    issues: List[Literal[
        "continuity_error",
        "out_of_character",
        "pacing_issue",
        "tone_mismatch",
        "other"
    ]] = Field(
        default_factory=list,
        description="Specific issues detected"
    )

    class Config:
        extra = "forbid"


class Operations(BaseModel):
    """
    Special operations or requests from the Apex AI.
    """
    request_summary: Optional[SummaryRequest] = Field(
        default=None,
        description="Request for episode/season summary"
    )
    request_regeneration: Optional[RegenerationRequest] = Field(
        default=None,
        description="Request to regenerate this chunk"
    )
    spawn_side_task: Optional[str] = Field(
        default=None,
        description="Description of side task to spawn"
    )

    class Config:
        extra = "forbid"


# ============================================================================
# Main Response Schema
# ============================================================================

class NarrativeChunk(BaseModel):
    """
    The narrative prose itself.
    """
    text: str = Field(
        description="The narrative prose for this turn"
    )
    suggested_slug: Optional[str] = Field(
        default=None,
        description="Suggested slug/title for this chunk"
    )
    estimated_tokens: Optional[int] = Field(
        default=None,
        description="Estimated token count of the narrative"
    )

    class Config:
        extra = "forbid"


class StoryTurnResponse(BaseModel):
    """
    Complete structured response from Apex AI for a single story turn.

    This is the top-level schema that combines:
    - Narrative prose
    - Chunk metadata
    - Entity references
    - State updates
    - Operations
    """
    narrative: NarrativeChunk = Field(
        description="The narrative prose for this turn"
    )
    metadata: Optional[ChunkMetadataUpdate] = Field(
        default=None,
        description="Metadata updates for this chunk"
    )
    referenced_entities: Optional[ReferencedEntities] = Field(
        default=None,
        description="Entities referenced in this narrative"
    )
    state_updates: Optional[StateUpdates] = Field(
        default=None,
        description="Updates to character and world state"
    )
    operations: Optional[Operations] = Field(
        default=None,
        description="Special operations or requests"
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="AI's reasoning about narrative choices (for debugging)"
    )

    class Config:
        extra = "forbid"


# ============================================================================
# Helper Functions
# ============================================================================

def validate_story_turn_response(data: Dict[str, Any]) -> StoryTurnResponse:
    """
    Validate and parse a story turn response from raw data.

    Args:
        data: Raw dictionary from API response

    Returns:
        Validated StoryTurnResponse

    Raises:
        ValidationError: If data doesn't match schema
    """
    return StoryTurnResponse(**data)


def create_minimal_response(narrative_text: str) -> StoryTurnResponse:
    """
    Create a minimal StoryTurnResponse with just narrative text.
    Useful for fallback scenarios.

    Args:
        narrative_text: The narrative prose

    Returns:
        StoryTurnResponse with minimal data
    """
    return StoryTurnResponse(
        narrative=NarrativeChunk(text=narrative_text)
    )


def extract_narrative_text(response: StoryTurnResponse) -> str:
    """
    Extract just the narrative text from a structured response.

    Args:
        response: Structured story turn response

    Returns:
        The narrative text
    """
    return response.narrative.text
