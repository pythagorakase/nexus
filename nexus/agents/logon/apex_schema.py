"""
APEX Structured Output Schema for Live Narrative Turns
=======================================================

Production schema for NEXUS narrative generation, based on refactored version.

Key improvements over legacy schema:
1. Full database column alignment (all required fields present)
2. Support for creating new entities (characters, places, factions)
3. Proper database ENUM types
4. Fixed episode/season transition handling
5. Interval-based timekeeping
6. Entity state updates with proper FK relationships

All models use Pydantic v2 for validation and serialization.
"""

import logging
from typing import List, Optional, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime

# Import all database ENUMs
from nexus.agents.logon.apex_enums import (
    AgentType,
    EmotionalValence,
    EntityType,
    FactionMemberRole,
    FactionRelationshipType,
    ItemType,
    LogLevel,
    ModelName,
    PlaceReferenceType,
    PlaceType,
    Provider,
    QueryCategory,
    ReasoningEffort,
    ReferenceType,
    RelationshipType,
    ThreatDomain,
    ThreatLifecycle,
    WorldLayerType,
    get_active_entity_types,
)

logger = logging.getLogger("nexus.logon.apex_schema")


# ============================================================================
# New Entity Creation
# ============================================================================

class NewCharacter(BaseModel):
    """
    Schema for introducing a new character - aligned with DB schema.
    All fields required except where DB dictates otherwise.
    """
    name: str = Field(description="Character's name")
    appearance: str = Field(
        description="Physical description - how the character looks"
    )
    background: str = Field(
        description="Character backstory and history"
    )
    personality: str = Field(
        description="Personality traits and quirks (prose format, e.g., 'Methodical problem-solver. Paranoid about digital traces.')"
    )
    emotional_state: str = Field(
        description="Current emotional state"
    )
    current_activity: str = Field(
        description="What the character is currently doing"
    )
    current_location: int = Field(
        description="Place ID where character is located (FK to places.id)"
    )
    summary: str = Field(
        max_length=500,
        description="Brief character description (max 500 chars)"
    )
    extra_data: Dict[str, Any] = Field(
        description="Additional character details (structured data, can be {} if nothing additional)"
    )


class NewPlace(BaseModel):
    """
    Schema for introducing a new place - aligned with DB schema.
    Zone is calculated from coordinates post-creation (not an input field).
    """
    name: str = Field(description="Place name")
    type: PlaceType = Field(
        description="Type of place (fixed_location, vehicle, virtual, other)"
    )
    summary: str = Field(
        max_length=500,
        description="Brief place description (max 500 chars)"
    )
    history: str = Field(
        description="Place history and past events"
    )
    current_status: str = Field(
        description="Current state, conditions, and activity at this location"
    )
    secrets: str = Field(
        description="Hidden information, plot hooks, and narrative opportunities (REQUIRED - invaluable for storytelling)"
    )
    coordinates: Dict[str, float] = Field(
        description="Geographic coordinates {lat, lon} for real-world or {x, y, z} for virtual locations. Zone calculated from this."
    )
    inhabitants: Optional[List[int]] = Field(
        default_factory=list,
        description="Character IDs of inhabitants (usually empty for newly introduced places)"
    )
    extra_data: Dict[str, Any] = Field(
        description="Additional structured data (can be {} if nothing additional)"
    )


class NewFaction(BaseModel):
    """
    Schema for introducing a new faction - aligned with DB schema.
    All fields required. Leader info goes in extra_data or character relationships.
    """
    name: str = Field(description="Faction name")
    summary: str = Field(
        max_length=500,
        description="Brief faction description (max 500 chars)"
    )
    ideology: str = Field(
        description="Faction's core ideology or purpose"
    )
    history: str = Field(
        description="Faction origins, past events, and evolution"
    )
    current_activity: str = Field(
        description="What the faction is currently doing"
    )
    hidden_agenda: str = Field(
        description="Secret goals, plots, and agendas (like place secrets - narrative gold!)"
    )
    territory: str = Field(
        description="Controlled areas, zones of influence, or operational reach"
    )
    power_level: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Faction influence/power rating (0.0-1.0, default 0.5 for new factions)"
    )
    resources: str = Field(
        description="Assets, capabilities, personnel, and resources"
    )
    primary_location: int = Field(
        description="Place ID of faction headquarters/primary base (FK to places.id)"
    )
    extra_data: Dict[str, Any] = Field(
        description="Additional structured data including leader info: {'leader': 'Name'} (can be {} if nothing additional)"
    )


# ============================================================================
# Entity References (Supporting both existing and new)
# ============================================================================

class CharacterReference(BaseModel):
    """Reference to a character - either existing or new"""
    # For existing character
    character_id: Optional[int] = Field(
        default=None,
        description="Database ID for existing character"
    )
    character_name: Optional[str] = Field(
        default=None,
        description="Name for lookup if ID unknown"
    )
    # For new character
    new_character: Optional[NewCharacter] = Field(
        default=None,
        description="Details for creating new character"
    )
    # How they appear in this chunk
    reference_type: ReferenceType = Field(
        default=ReferenceType.MENTIONED,
        description="How the character is referenced"
    )

    @model_validator(mode='after')
    def validate_character_reference(self):
        """Ensure we have either existing ref or new character"""
        if not any([self.character_id, self.character_name, self.new_character]):
            raise ValueError("Must provide either character_id, character_name, or new_character")
        return self


class PlaceReference(BaseModel):
    """Reference to a place - either existing or new"""
    # For existing place
    place_id: Optional[int] = Field(
        default=None,
        description="Database ID for existing place"
    )
    place_name: Optional[str] = Field(
        default=None,
        description="Name for lookup if ID unknown"
    )
    # For new place
    new_place: Optional[NewPlace] = Field(
        default=None,
        description="Details for creating new place"
    )
    # How it appears in this chunk
    reference_type: PlaceReferenceType = Field(
        default=PlaceReferenceType.MENTIONED,
        description="How the place is referenced"
    )


class FactionReference(BaseModel):
    """Reference to a faction - either existing or new"""
    # For existing faction
    faction_id: Optional[int] = Field(
        default=None,
        description="Database ID for existing faction"
    )
    faction_name: Optional[str] = Field(
        default=None,
        description="Name for lookup if ID unknown"
    )
    # For new faction
    new_faction: Optional[NewFaction] = Field(
        default=None,
        description="Details for creating new faction"
    )
    # How it appears
    reference_type: ReferenceType = Field(
        default=ReferenceType.MENTIONED,
        description="How the faction is referenced"
    )


class ReferencedEntities(BaseModel):
    """
    Collection of all entities referenced in the narrative chunk.
    Supports both existing entities and introduction of new ones.
    """
    characters: List[CharacterReference] = Field(
        default_factory=list,
        description="Characters present or mentioned (existing or new)"
    )
    places: List[PlaceReference] = Field(
        default_factory=list,
        description="Places present or mentioned (existing or new)"
    )
    factions: List[FactionReference] = Field(
        default_factory=list,
        description="Factions present or mentioned (existing or new)"
    )
    # Note: items and threats tables exist but are empty
    # events table doesn't exist

    class Config:
        extra = "forbid"


# ============================================================================
# Chunk Metadata (Minimal, removing deprecated fields)
# ============================================================================

class ChronologyUpdate(BaseModel):
    """
    Updates to narrative chronology using interval-based timekeeping.

    Fixed: episode_transition replaces the problematic dual boolean flags
    to prevent invalid state (season increment without episode increment).
    """
    episode_transition: Literal["continue", "new_episode", "new_season"] = Field(
        default="continue",
        description="Episode/season transition: continue current, new episode, or new season (which also starts new episode)"
    )
    time_delta_seconds: Optional[int] = Field(
        default=None,
        ge=0,
        description="Seconds elapsed since previous chunk"
    )
    time_delta_description: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Human-readable time passage (e.g., 'two hours later')"
    )

    class Config:
        extra = "forbid"


class ChunkMetadataUpdate(BaseModel):
    """
    Minimal metadata for chunk (removed 15 deprecated JSONB fields).
    Focused on essential chronology and reference tracking.
    """
    chronology: Optional[ChronologyUpdate] = Field(
        default=None,
        description="Time progression updates"
    )
    world_layer: WorldLayerType = Field(
        default=WorldLayerType.PRIMARY,
        description="Narrative layer (primary, flashback, dream, etc.)"
    )

    class Config:
        extra = "forbid"


# ============================================================================
# Entity State Updates (Aligned with database)
# ============================================================================

class CharacterStateUpdate(BaseModel):
    """
    Update to a character's state (aligned with database schema).
    """
    character_id: Optional[int] = Field(
        default=None,
        description="Database ID of character"
    )
    character_name: str = Field(
        description="Character name (for lookup if ID unknown)"
    )
    current_location: Optional[int] = Field(
        default=None,
        description="FK to places.id"
    )
    current_activity: Optional[str] = Field(
        default=None,
        description="What the character is currently doing"
    )
    emotional_state: Optional[str] = Field(
        default=None,
        description="Character's emotional state"
    )
    extra_observations: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional observations stored in extra_data JSONB"
    )

    class Config:
        extra = "forbid"


class RelationshipUpdate(BaseModel):
    """
    Update to a relationship (aligned with character_relationships table).
    """
    character1_id: Optional[int] = Field(
        default=None,
        description="First character ID"
    )
    character1_name: Optional[str] = Field(
        default=None,
        description="First character name (if ID unknown)"
    )
    character2_id: Optional[int] = Field(
        default=None,
        description="Second character ID"
    )
    character2_name: Optional[str] = Field(
        default=None,
        description="Second character name (if ID unknown)"
    )
    relationship_type: Optional[RelationshipType] = Field(
        default=None,
        description="Type of relationship"
    )
    emotional_valence: Optional[EmotionalValence] = Field(
        default=None,
        description="Emotional valence of relationship"
    )
    dynamic: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Current relationship dynamic"
    )
    recent_events: Optional[str] = Field(
        default=None,
        description="Recent events affecting relationship"
    )

    class Config:
        extra = "forbid"


class LocationStateUpdate(BaseModel):
    """
    Update to a location's state (replaces vague world_state_notes).
    """
    place_id: Optional[int] = Field(
        default=None,
        description="Database ID of place"
    )
    place_name: Optional[str] = Field(
        default=None,
        description="Place name (if ID unknown)"
    )
    current_conditions: Optional[str] = Field(
        default=None,
        description="Current conditions at location"
    )
    notable_changes: Optional[List[str]] = Field(
        default_factory=list,
        description="Notable changes since last visit"
    )


class FactionStateUpdate(BaseModel):
    """
    Update to a faction's state.
    """
    faction_id: Optional[int] = Field(
        default=None,
        description="Database ID of faction"
    )
    faction_name: Optional[str] = Field(
        default=None,
        description="Faction name (if ID unknown)"
    )
    recent_actions: Optional[List[str]] = Field(
        default_factory=list,
        description="Recent faction actions"
    )
    stance_changes: Optional[Dict[str, str]] = Field(
        default=None,
        description="Changes in stance toward other entities"
    )


class StateUpdates(BaseModel):
    """
    Collection of all state updates (structured, not vague).
    """
    characters: List[CharacterStateUpdate] = Field(
        default_factory=list,
        description="Character state updates"
    )
    relationships: List[RelationshipUpdate] = Field(
        default_factory=list,
        description="Relationship updates"
    )
    locations: List[LocationStateUpdate] = Field(
        default_factory=list,
        description="Location state updates"
    )
    factions: List[FactionStateUpdate] = Field(
        default_factory=list,
        description="Faction state updates"
    )

    class Config:
        extra = "forbid"


# ============================================================================
# Operations
# ============================================================================

class SummaryRequest(BaseModel):
    """Request for an episode or season summary."""
    summary_type: Literal["episode", "season"] = Field(
        description="Type of summary needed"
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Reason for requesting summary"
    )

    class Config:
        extra = "forbid"


class RegenerationRequest(BaseModel):
    """Request to regenerate this narrative chunk."""
    reason: str = Field(
        max_length=500,
        description="Reason for requesting regeneration"
    )
    issues: List[Literal[
        "continuity_error",
        "out_of_character",
        "pacing_issue",
        "tone_mismatch",
        "world_inconsistency",
        "other"
    ]] = Field(
        default_factory=list,
        description="Specific issues detected"
    )

    class Config:
        extra = "forbid"


class Operations(BaseModel):
    """Special operations or requests from the Storyteller AI."""
    request_summary: Optional[SummaryRequest] = Field(
        default=None,
        description="Request for episode/season summary"
    )
    request_regeneration: Optional[RegenerationRequest] = Field(
        default=None,
        description="Request to regenerate this chunk"
    )

    class Config:
        extra = "forbid"


# ============================================================================
# Main Response Schema with Hierarchical Options
# ============================================================================

class StorytellerResponseMinimal(BaseModel):
    """Minimal response for quick narrative generation."""
    narrative: str = Field(
        description="The narrative prose (500-1500 words)"
    )
    referenced_entities: Optional[ReferencedEntities] = Field(
        default=None,
        description="Entities referenced in narrative"
    )

    class Config:
        extra = "forbid"


class StorytellerResponseStandard(BaseModel):
    """Standard response with narrative and essential metadata."""
    narrative: str = Field(
        description="The narrative prose (500-1500 words)"
    )
    chunk_metadata: ChunkMetadataUpdate = Field(
        description="Essential chunk metadata"
    )
    referenced_entities: ReferencedEntities = Field(
        description="All entities referenced"
    )
    state_updates: Optional[StateUpdates] = Field(
        default=None,
        description="State changes for entities"
    )

    class Config:
        extra = "forbid"


class StorytellerResponseExtended(BaseModel):
    """Extended response with all features including operations."""
    narrative: str = Field(
        description="The narrative prose (500-1500 words)"
    )
    chunk_metadata: ChunkMetadataUpdate = Field(
        description="Essential chunk metadata"
    )
    referenced_entities: ReferencedEntities = Field(
        description="All entities referenced (existing or new)"
    )
    state_updates: StateUpdates = Field(
        description="Comprehensive state updates"
    )
    operations: Optional[Operations] = Field(
        default=None,
        description="Special operations or requests"
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Storyteller's reasoning (debug mode only)"
    )

    class Config:
        extra = "forbid"


# ============================================================================
# Utility Functions
# ============================================================================

def calculate_token_count(text: str) -> int:
    """
    Calculate precise token count using tiktoken.
    Uses the proper encoding based on the target model.
    """
    # Import here to avoid circular dependencies
    from nexus.agents.lore.utils.chunk_operations import calculate_chunk_tokens
    return calculate_chunk_tokens(text)


def validate_entity_references(entities: ReferencedEntities) -> List[str]:
    """
    Validate that entity references are well-formed.
    Returns list of validation warnings.
    """
    warnings = []

    # Check for duplicate characters
    char_names = [c.character_name or c.new_character.name
                  for c in entities.characters
                  if c.character_name or c.new_character]
    if len(char_names) != len(set(char_names)):
        warnings.append("Duplicate character references detected")

    # Check for duplicate places
    place_names = [p.place_name or p.new_place.name
                   for p in entities.places
                   if p.place_name or p.new_place]
    if len(place_names) != len(set(place_names)):
        warnings.append("Duplicate place references detected")

    return warnings