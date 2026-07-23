"""
APEX Structured Output Schema for Live Narrative Turns
=======================================================

Production schema for NEXUS narrative generation, based on refactored version.

Key improvements over legacy schema:
1. Full database column alignment (all required fields present)
2. Declaration-driven creation of persistent entities
3. Proper database ENUM types
4. Fixed episode/season transition handling
5. Interval-based timekeeping
6. Entity state updates with proper FK relationships

All models use Pydantic v2 for validation and serialization.
"""

import json
import logging
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

# Import all database ENUMs
from nexus.agents.logon.apex_enums import (
    EmotionalValence,
    PlaceReferenceType,
    ReferenceType,
    RelationshipType,
    WorldLayerType,
)
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal

logger = logging.getLogger("nexus.logon.apex_schema")


# ============================================================================
# Structured Data Models (for OpenAI strict mode compatibility)
# ============================================================================
# These replace bare Dict[str, Any] fields which cause schema validation errors.
# OpenAI strict mode requires additionalProperties: false, but bare Dicts emit
# additionalProperties: true, causing a mismatch when the field is in 'required'.


class Coordinates(BaseModel):
    """
    Earth-based lat/lon coordinates.

    All worlds in NEXUS share Earth's physical geography—same size, same
    continental shapes, same coastlines. Choose coordinates that make sense
    for the location's described characteristics (climate, terrain, proximity
    to water).
    """

    lat: float = Field(ge=-90, le=90, description="Latitude (-90 to 90)")
    lon: float = Field(ge=-180, le=180, description="Longitude (-180 to 180)")

    model_config = ConfigDict(extra="forbid")


class NamedObservation(BaseModel):
    """Strict key/value observation entry for JSONB-style side notes."""

    key: str = Field(min_length=1, description="Observation key or label")
    value: str = Field(description="Observation value as concise prose")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class FactionStanceChange(BaseModel):
    """Strict faction stance change entry."""

    target: str = Field(min_length=1, description="Faction, group, or entity target")
    stance: str = Field(description="Updated stance toward the target")

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _stringify_structured_value(value: Any) -> str:
    """Render arbitrary legacy observation values into strict-schema prose."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


# ============================================================================
# New Entity Declarations (Retrograde Stub Maturation, spec decision 9)
# ============================================================================


class NewEntityPairTagHint(BaseModel):
    """
    Optional registered pair-tag hint attached to a new-entity declaration.

    The declared entity is one endpoint; ``other_entity_name`` names the other.
    Hints are validated against the live ``pair_tags`` registry during
    generation, where unregistered or kind-incompatible tags trigger a retry.
    The commit path revalidates the complete declaration batch as a backstop.
    Valid hints are applied when the declaration is accepted and also feed the
    background maturation pass as prompt material.
    """

    tag: str = Field(
        min_length=1,
        description="Registered pair-tag name (e.g., protects, obligation).",
    )
    other_entity_name: str = Field(
        min_length=1,
        description="Name of the other endpoint entity (existing or declared).",
    )
    declared_entity_role: Literal["subject", "object"] = Field(
        default="subject",
        description=(
            "Whether the declared entity is the subject or object of the "
            "directed pair tag."
        ),
    )

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class NewEntityDeclaration(BaseModel):
    """
    Skald's declaration that this chunk introduces a new persistent entity.

    Declarations drive the two-tier promotion pipeline (Retrograde Stub
    Maturation): the commit path instantiates a stub row when the entity does
    not already exist, and — when the declared name appears in the committed
    chunk — enqueues an asynchronous maturation job that generates the
    entity's shallow connected backstory.

    Declare SPARINGLY: only entities likely to recur or matter. Background
    crowds and genuinely mundane passersby exist in prose only and must not
    be declared. Tag hints use registered vocabulary only; invalid hints
    trigger generation-time repair, with whole-batch commit-time validation as
    a mutation-safety backstop.
    """

    kind: Literal["character", "place", "faction"] = Field(
        description="Entity kind for the new declaration."
    )
    name: str = Field(
        min_length=1,
        max_length=200,
        description="Entity name exactly as introduced in the prose.",
    )
    summary: str = Field(
        min_length=1,
        max_length=500,
        description="One-line summary used for the entity's stub row.",
    )
    coordinates: Optional[Coordinates] = Field(
        default=None,
        description="Optional real-Earth coordinates for a declared place.",
    )
    tag_hints: List[str] = Field(
        default_factory=list,
        description="Registered single-entity tag names for the new stub.",
    )
    pair_tag_hints: List[NewEntityPairTagHint] = Field(
        default_factory=list,
        description="Registered pair-tag hints connecting the declared entity.",
    )

    @model_validator(mode="after")
    def coordinates_are_place_only(self) -> "NewEntityDeclaration":
        """Reject GIS data on non-place declarations instead of dropping it."""

        if self.coordinates is not None and self.kind != "place":
            raise ValueError("coordinates are only valid for place declarations")
        return self

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


# ============================================================================
# Entity References
# ============================================================================


class CharacterReference(BaseModel):
    """Reference to an existing character by ID or name."""

    # For existing character
    character_id: Optional[int] = Field(
        default=None, description="Database ID for existing character"
    )
    character_name: Optional[str] = Field(
        default=None, description="Name for lookup if ID unknown"
    )
    # How they appear in this chunk
    reference_type: ReferenceType = Field(
        default=ReferenceType.MENTIONED, description="How the character is referenced"
    )

    @model_validator(mode="after")
    def validate_character_reference(self):
        """Ensure the reference supplies an ID or name."""
        if not any([self.character_id, self.character_name]):
            raise ValueError("Must provide either character_id or character_name")
        return self

    model_config = ConfigDict(extra="forbid")


class PlaceReference(BaseModel):
    """Reference to an existing place by ID or name."""

    # For existing place
    place_id: Optional[int] = Field(
        default=None, description="Database ID for existing place"
    )
    place_name: Optional[str] = Field(
        default=None, description="Name for lookup if ID unknown"
    )
    # How it appears in this chunk (REQUIRED for junction table)
    reference_type: PlaceReferenceType = Field(
        description="Place role: setting, mentioned, or transit."
    )
    # Optional evidence field (matches junction table)
    evidence: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional evidence supporting this place reference.",
    )

    @model_validator(mode="after")
    def validate_place_reference(self):
        """Ensure the reference supplies an ID or name."""
        if not any([self.place_id, self.place_name]):
            raise ValueError("Must provide either place_id or place_name")
        return self

    model_config = ConfigDict(extra="forbid")


class FactionReference(BaseModel):
    """Reference to an existing faction by ID or name."""

    # For existing faction
    faction_id: Optional[int] = Field(
        default=None, description="Database ID for existing faction"
    )
    faction_name: Optional[str] = Field(
        default=None, description="Name for lookup if ID unknown"
    )
    # How it appears
    reference_type: ReferenceType = Field(
        default=ReferenceType.MENTIONED, description="How the faction is referenced"
    )

    @model_validator(mode="after")
    def validate_faction_reference(self):
        """Ensure the reference supplies an ID or name."""
        if not any([self.faction_id, self.faction_name]):
            raise ValueError("Must provide either faction_id or faction_name")
        return self

    model_config = ConfigDict(extra="forbid")


class ReferencedEntities(BaseModel):
    """
    Collection of existing entities referenced in the narrative chunk.
    """

    characters: List[CharacterReference] = Field(
        default_factory=list,
        description="Existing characters present or mentioned",
    )
    places: List[PlaceReference] = Field(
        default_factory=list,
        description="Existing places present or mentioned",
    )
    factions: List[FactionReference] = Field(
        default_factory=list,
        description="Existing factions present or mentioned",
    )
    # Note: items and threats tables exist but are empty
    # events table doesn't exist

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Chunk Metadata (Minimal, removing deprecated fields)
# ============================================================================


class ChronologyUpdate(BaseModel):
    """
    Updates to narrative chronology using LLM-friendly time units.

    Time representation uses separate fields for minutes, hours, and days
    to help LLMs think more naturally about time passage. Based on analysis
    of 1425 existing chunks: 98% are under 1 hour, 1.5% are 1-24 hours,
    only 0.2% exceed 24 hours.

    Fixed: episode_transition replaces the problematic dual boolean flags
    to prevent invalid state (season increment without episode increment).
    """

    episode_transition: Literal["continue", "new_episode", "new_season"] = Field(
        default="continue",
        description="Continue, start a new episode, or start a new season.",
    )

    # LLM-friendly time fields (more natural than seconds)
    time_delta_minutes: Optional[int] = Field(
        default=None,
        ge=0,
        lt=60,
        description="Minutes elapsed (0-59). Most chunks are in this range.",
    )
    time_delta_hours: Optional[int] = Field(
        default=None,
        ge=0,
        lt=24,
        description="Hours elapsed (0-23). Use for longer time passages.",
    )
    time_delta_days: Optional[int] = Field(
        default=None,
        ge=0,
        description="Days elapsed (0+). Rarely used - most narrative is continuous.",
    )

    time_delta_description: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Human-readable description of the elapsed time.",
    )

    @model_validator(mode="after")
    def validate_time_fields(self):
        """At least one time field should be set if any are set"""
        time_fields = [
            self.time_delta_minutes,
            self.time_delta_hours,
            self.time_delta_days,
        ]
        if any(f is not None for f in time_fields):
            # Valid - at least one field set
            return self
        # All None is also valid (no time passage)
        return self

    model_config = ConfigDict(extra="forbid")


class ChunkMetadataUpdate(BaseModel):
    """
    Minimal metadata for chunk (removed 15 deprecated JSONB fields).
    Focused on essential chronology and reference tracking.
    """

    chronology: Optional[ChronologyUpdate] = Field(
        default=None, description="Time progression updates"
    )
    world_layer: WorldLayerType = Field(
        default=WorldLayerType.PRIMARY,
        description="Narrative clock layer; use primary for normal scenes.",
    )
    scene_weather: Optional[Literal["clear", "rain", "fog", "snow", "warm"]] = Field(
        default=None,
        description="Optional anchor-scene weather override.",
    )

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Entity State Updates (Aligned with database)
# ============================================================================


class CharacterStateUpdate(BaseModel):
    """
    Update to a character's state (aligned with database schema).
    """

    character_id: Optional[int] = Field(
        default=None, description="Database ID of character"
    )
    character_name: str = Field(description="Character name (for lookup if ID unknown)")
    current_location: Optional[int] = Field(default=None, description="FK to places.id")
    current_activity: Optional[str] = Field(
        default=None, description="What the character is currently doing"
    )
    emotional_state: Optional[str] = Field(
        default=None, description="Character's emotional state"
    )
    extra_observations: List[NamedObservation] = Field(
        default_factory=list,
        description="Strict key/value observations for extra_data JSONB.",
    )
    orrery_tags: Optional[OrreryTagBestowal] = Field(
        default=None,
        description="Registered tag deltas for this character.",
    )

    @field_validator("extra_observations", mode="before")
    @classmethod
    def normalize_extra_observations(cls, value: Any) -> Any:
        """Accept legacy dict observations while emitting strict list schema."""

        if value is None or isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [
                {"key": str(key), "value": _stringify_structured_value(item)}
                for key, item in value.items()
            ]
        return value

    model_config = ConfigDict(extra="forbid")


class RelationshipUpdate(BaseModel):
    """
    Update to a relationship (aligned with character_relationships table).
    """

    character1_id: Optional[int] = Field(default=None, description="First character ID")
    character1_name: Optional[str] = Field(
        default=None, description="First character name (if ID unknown)"
    )
    character2_id: Optional[int] = Field(
        default=None, description="Second character ID"
    )
    character2_name: Optional[str] = Field(
        default=None, description="Second character name (if ID unknown)"
    )
    relationship_type: Optional[RelationshipType] = Field(
        default=None, description="Type of relationship"
    )
    emotional_valence: Optional[EmotionalValence] = Field(
        default=None, description="Emotional valence of relationship"
    )
    dynamic: Optional[str] = Field(
        default=None, max_length=500, description="Current relationship dynamic"
    )
    recent_events: Optional[str] = Field(
        default=None, description="Recent events affecting relationship"
    )

    model_config = ConfigDict(extra="forbid")


class LocationStateUpdate(BaseModel):
    """
    Update to a location's state (replaces vague world_state_notes).
    """

    place_id: Optional[int] = Field(default=None, description="Database ID of place")
    place_name: Optional[str] = Field(
        default=None, description="Place name (if ID unknown)"
    )
    current_conditions: Optional[str] = Field(
        default=None, description="Current conditions at location"
    )
    notable_changes: Optional[List[str]] = Field(
        default_factory=list,  # type: ignore[arg-type]
        description="Notable changes since last visit",
    )
    orrery_tags: Optional[OrreryTagBestowal] = Field(
        default=None,
        description="Registered tag deltas for this place.",
    )


class FactionStateUpdate(BaseModel):
    """
    Update to a faction's Orrery state.
    """

    faction_id: Optional[int] = Field(
        default=None, description="Database ID of faction"
    )
    faction_name: Optional[str] = Field(
        default=None, description="Faction name (if ID unknown)"
    )
    recent_actions: Optional[List[str]] = Field(
        default_factory=list,  # type: ignore[arg-type]
        description="Recent faction actions for narrative context.",
    )
    stance_changes: List[FactionStanceChange] = Field(
        default_factory=list,
        description="Changes in stance toward other entities as strict entries",
    )
    orrery_tags: Optional[OrreryTagBestowal] = Field(
        default=None,
        description="Registered tag deltas for this faction.",
    )

    @field_validator("stance_changes", mode="before")
    @classmethod
    def normalize_stance_changes(cls, value: Any) -> Any:
        """Accept legacy stance-change dicts while emitting strict list schema."""

        if value is None or isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [
                {"target": str(target), "stance": _stringify_structured_value(stance)}
                for target, stance in value.items()
            ]
        return value

    model_config = ConfigDict(extra="forbid")


class StateUpdates(BaseModel):
    """
    Collection of all state updates (structured, not vague).
    """

    characters: List[CharacterStateUpdate] = Field(
        default_factory=list, description="Character state updates"
    )
    relationships: List[RelationshipUpdate] = Field(
        default_factory=list, description="Relationship updates"
    )
    locations: List[LocationStateUpdate] = Field(
        default_factory=list, description="Location state updates"
    )
    factions: List[FactionStateUpdate] = Field(
        default_factory=list, description="Faction state updates"
    )

    model_config = ConfigDict(extra="forbid")


class OrreryMoodSet(BaseModel):
    """Closed mechanical mood write used by Orrery replacement deltas."""

    mood: Literal["elated", "sour", "restless", "grim"]
    hours: Optional[float] = Field(default=None, gt=0)

    model_config = ConfigDict(extra="forbid")


class OrreryReplacementStateDelta(BaseModel):
    """
    Limited Orrery state delta Skald may substitute for a proposed resolution.

    Field names are Skald-facing aliases. The commit layer maps them to the
    canonical dotted Orrery keys after schema validation.
    """

    character_current_activity: Optional[str] = Field(
        default=None,
        description="Replacement for the actor's character.current_activity delta",
    )
    entity_tags_add: List[str] = Field(
        default_factory=list,
        description="Replacement actor tags to add",
    )
    entity_tags_remove: List[str] = Field(
        default_factory=list,
        description="Replacement actor tags to clear",
    )
    entity_tags_target_add: List[str] = Field(
        default_factory=list,
        description="Replacement target tags to add",
    )
    entity_tags_target_remove: List[str] = Field(
        default_factory=list,
        description="Replacement target tags to clear",
    )
    entity_pair_tags_target_clear_inbound: List[str] = Field(
        default_factory=list,
        description="Replacement inbound target pair-tags to clear",
    )
    mood_set: Optional[OrreryMoodSet] = Field(
        default=None,
        description="Replacement actor mood with optional world-hour duration",
    )

    model_config = ConfigDict(extra="forbid")


class OrreryAdjudication(BaseModel):
    """
    Skald's optional ruling for one current-tick Orrery proposal.

    Omit an adjudication to ratify the proposal at commit time. Use defer to
    leave the pressure unresolved for a later tick, void when the proposal is
    definitively false, and replace when Skald has supplied a story-truer
    state update or replacement delta.
    """

    proposal_id: str = Field(
        min_length=1,
        description="Exact proposal_id from orrery_imminent_activity",
    )
    action: Literal["defer", "replace", "void"] = Field(
        description="Structured authority decision for this proposal"
    )
    note: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Brief reason or replacement summary for audit/debugging",
    )
    replacement_state_delta: Optional[OrreryReplacementStateDelta] = Field(
        default=None,
        description="Limited Orrery delta replacing the proposal.",
    )
    replacement_event_type: Optional[str] = Field(
        default=None,
        description=(
            "Optional registered event type for a replacement_state_delta. "
            "Leave unset unless the replacement should emit a canonical world_event."
        ),
    )

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Operations
# ============================================================================


class SummaryRequest(BaseModel):
    """Request for an episode or season summary."""

    summary_type: Literal["episode", "season"] = Field(
        description="Type of summary needed"
    )
    reason: Optional[str] = Field(
        default=None, max_length=200, description="Reason for requesting summary"
    )

    model_config = ConfigDict(extra="forbid")


class RegenerationRequest(BaseModel):
    """Request to regenerate this narrative chunk."""

    reason: str = Field(
        max_length=500, description="Reason for requesting regeneration"
    )
    issues: List[
        Literal[
            "continuity_error",
            "out_of_character",
            "pacing_issue",
            "tone_mismatch",
            "world_inconsistency",
            "other",
        ]
    ] = Field(default_factory=list, description="Specific issues detected")

    model_config = ConfigDict(extra="forbid")


class Operations(BaseModel):
    """Special operations or requests from the Storyteller AI."""

    request_summary: Optional[SummaryRequest] = Field(
        default=None, description="Request for episode/season summary"
    )
    request_regeneration: Optional[RegenerationRequest] = Field(
        default=None, description="Request to regenerate this chunk"
    )

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Main Response Schema with Hierarchical Options
# ============================================================================


class StorytellerResponseBase(BaseModel):
    """Provider-enriched response fields excluded from the storyteller wire schema."""

    generation_model: SkipJsonSchema[Optional[str]] = Field(
        default=None,
        exclude=True,
        description=(
            "Concrete registry model id used for the successful generation call"
        ),
    )

    model_config = ConfigDict(extra="forbid")


class StorytellerResponseBootstrap(StorytellerResponseBase):
    """Bootstrap response for first-chunk narrative generation."""

    narrative: str = Field(description="The opening narrative prose")
    choices: List[str] = Field(
        min_length=2,
        max_length=4,
        description=(
            "Player choices (2-4 options). Each should be a complete, "
            "actionable option written from player perspective."
        ),
    )

    model_config = ConfigDict(extra="forbid")


class StorytellerResponseMinimal(StorytellerResponseBase):
    """Minimal response for quick narrative generation."""

    narrative: str = Field(description="The narrative prose (500-1500 words)")
    choices: List[str] = Field(
        min_length=2,
        max_length=4,
        description=(
            "Player choices (2-4 options). Each should be a complete, "
            "actionable option written from player perspective."
        ),
    )
    referenced_entities: Optional[ReferencedEntities] = Field(
        default=None, description="Entities referenced in narrative"
    )
    orrery_adjudications: List[OrreryAdjudication] = Field(
        default_factory=list,
        description="Optional defer/replace/void rulings for Orrery proposals",
    )
    new_entities: List[NewEntityDeclaration] = Field(
        default_factory=list,
        description=(
            "Sparingly declared new persistent entities introduced this "
            "chunk (likely-to-recur only); drives background backstory "
            "maturation."
        ),
    )

    model_config = ConfigDict(extra="forbid")


class StorytellerResponseStandard(StorytellerResponseBase):
    """Standard response with narrative and essential metadata."""

    narrative: str = Field(description="The narrative prose (500-1500 words)")
    choices: List[str] = Field(
        min_length=2,
        max_length=4,
        description=(
            "Player choices (2-4 options). Each should be a complete, "
            "actionable option written from player perspective."
        ),
    )
    chunk_metadata: ChunkMetadataUpdate = Field(description="Essential chunk metadata")
    referenced_entities: ReferencedEntities = Field(
        description="All entities referenced"
    )
    state_updates: Optional[StateUpdates] = Field(
        default=None, description="State changes for entities"
    )
    orrery_adjudications: List[OrreryAdjudication] = Field(
        default_factory=list,
        description="Optional defer/replace/void rulings for Orrery proposals",
    )
    new_entities: List[NewEntityDeclaration] = Field(
        default_factory=list,
        description=(
            "Sparingly declared new persistent entities introduced this "
            "chunk (likely-to-recur only); drives background backstory "
            "maturation."
        ),
    )

    model_config = ConfigDict(extra="forbid")


class StorytellerResponseExtended(StorytellerResponseBase):
    """Extended response with all features including operations."""

    narrative: str = Field(description="The narrative prose (500-1500 words)")
    choices: List[str] = Field(
        min_length=2,
        max_length=4,
        description=(
            "Player choices (2-4 options). Each should be a complete, "
            "actionable option written from player perspective."
        ),
    )
    chunk_metadata: ChunkMetadataUpdate = Field(description="Essential chunk metadata")
    referenced_entities: ReferencedEntities = Field(
        description="All existing entities referenced"
    )
    state_updates: StateUpdates = Field(description="Comprehensive state updates")
    operations: Optional[Operations] = Field(
        default=None, description="Special operations or requests"
    )
    orrery_adjudications: List[OrreryAdjudication] = Field(
        default_factory=list,
        description="Optional defer/replace/void rulings for Orrery proposals",
    )
    new_entities: List[NewEntityDeclaration] = Field(
        default_factory=list,
        description=(
            "Sparingly declared new persistent entities introduced this "
            "chunk (likely-to-recur only); drives background backstory "
            "maturation."
        ),
    )
    reasoning: Optional[str] = Field(
        default=None, description="Storyteller's reasoning (debug mode only)"
    )

    model_config = ConfigDict(extra="forbid")


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


# ============================================================================
# Type Aliases for Compatibility
# ============================================================================

# Union type for backward compatibility with old logon_schemas
# Accepts any of the three response types
StoryTurnResponse = Union[
    StorytellerResponseExtended,
    StorytellerResponseStandard,
    StorytellerResponseMinimal,
    StorytellerResponseBootstrap,
]


# ============================================================================
# Helper Functions for Compatibility
# ============================================================================


def validate_story_turn_response(data: Dict[str, Any]) -> StoryTurnResponse:
    """
    Validate and parse a story turn response from raw data.
    Attempts to parse as Extended first, falls back to Standard, then Minimal,
    then Bootstrap.

    Args:
        data: Raw dictionary from API response

    Returns:
        Validated StoryTurnResponse (one of Bootstrap/Minimal/Standard/Extended)

    Raises:
        ValidationError: If data doesn't match any schema
    """
    # Try Extended first (most complete)
    try:
        return StorytellerResponseExtended(**data)
    except Exception:
        pass

    # Try Standard
    try:
        return StorytellerResponseStandard(**data)
    except Exception:
        pass

    # Try Minimal
    try:
        return StorytellerResponseMinimal(**data)
    except Exception:
        pass

    # Fall back to Bootstrap
    return StorytellerResponseBootstrap(**data)


def create_minimal_response(narrative_text: str) -> StorytellerResponseMinimal:
    """
    Create a minimal response from narrative text.
    Useful for fallback scenarios.

    Args:
        narrative_text: The narrative prose

    Returns:
        StorytellerResponseMinimal with generic choices
    """
    return StorytellerResponseMinimal(
        narrative=narrative_text,
        choices=[
            "Continue.",
            "Wait and observe.",
        ],
    )


def extract_narrative_text(response: StoryTurnResponse) -> str:
    """
    Extract just the narrative text from a structured response.

    Args:
        response: Structured storyteller response

    Returns:
        The narrative text
    """
    return response.narrative
