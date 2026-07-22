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

import json
import logging
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

# Import all database ENUMs
from nexus.agents.logon.apex_enums import (
    EmotionalValence,
    PlaceReferenceType,
    PlaceType,
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


class CharacterTraits(BaseModel):
    """
    Character traits following Mind's Eye Theatre philosophy.

    Exactly 3 of the 10 optional traits must be provided, plus the required
    wildcard. Traits signal narrative focus - what aspects of the character
    should be foregrounded in the story.
    """

    # Social Network (choose if narratively significant)
    allies: Optional[str] = Field(
        default=None, description="Who will actively help and take risks for you"
    )
    contacts: Optional[str] = Field(
        default=None, description="Information/favor sources - limited risk-taking"
    )
    patron: Optional[str] = Field(
        default=None, description="Powerful mentor/sponsor with their own agenda"
    )
    dependents: Optional[str] = Field(
        default=None, description="Those who rely on you for support or protection"
    )

    # Power & Position
    status: Optional[str] = Field(
        default=None, description="Formal standing recognized by an institution"
    )
    reputation: Optional[str] = Field(
        default=None, description="How widely known you are, what for"
    )

    # Assets & Territory
    resources: Optional[str] = Field(
        default=None, description="Material wealth, equipment, supplies"
    )
    domain: Optional[str] = Field(
        default=None, description="Place or area you control or claim"
    )
    role: Optional[str] = Field(
        default=None,
        description="Legacy freeform role note for partially introduced characters",
    )
    asset: Optional[str] = Field(
        default=None,
        description="Legacy freeform asset note for partially introduced characters",
    )

    # Liabilities
    enemies: Optional[str] = Field(
        default=None,
        description="Those actively opposed who will expend energy to thwart you",
    )
    obligations: Optional[str] = Field(
        default=None, description="Debts, oaths, or duties you must honor"
    )

    # Optional wildcard - unique trait that sets this character apart
    wildcard_name: Optional[str] = Field(
        default=None, description="Name of the unique custom trait"
    )
    wildcard_description: Optional[str] = Field(
        default=None,
        description=(
            "What this trait means - capability, possession, relationship, " "or curse"
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_extra_trait_keys(cls, data: Any) -> Any:
        """Fold legacy arbitrary extra_data keys into strict wildcard prose."""

        if not isinstance(data, dict):
            return data
        field_names = set(cls.model_fields)
        extras = {key: value for key, value in data.items() if key not in field_names}
        if not extras:
            return data

        normalized = {key: value for key, value in data.items() if key in field_names}
        normalized.setdefault("wildcard_name", "legacy_extra_data")
        normalized.setdefault(
            "wildcard_description",
            json.dumps(extras, ensure_ascii=False, sort_keys=True),
        )
        return normalized

    model_config = ConfigDict(extra="forbid")


class PlaceDetails(BaseModel):
    """
    Additional place attributes stored in extra_data JSONB.

    These provide rich world-building details beyond the core place fields.
    """

    category: Optional[str] = Field(
        default=None,
        description=(
            "Narrative category: settlement, wilderness, dungeon, building, "
            "district, landmark, road, border"
        ),
    )
    size: Optional[str] = Field(
        default=None,
        description="Relative size: tiny, small, medium, large, huge, massive",
    )
    population: Optional[int] = Field(
        default=None, ge=0, description="Population if applicable"
    )
    atmosphere: Optional[str] = Field(
        default=None, description="Mood and feeling of the place"
    )
    notable_features: List[str] = Field(
        default_factory=list, description="Distinctive physical features (max 8)"
    )
    resources: List[str] = Field(
        default_factory=list, description="Available resources (max 5)"
    )
    dangers: List[str] = Field(
        default_factory=list, description="Known threats or hazards (max 5)"
    )
    ruler: Optional[str] = Field(
        default=None, description="Who controls or governs this place"
    )
    factions: List[str] = Field(
        default_factory=list, description="Active factions or groups (max 5)"
    )
    culture: Optional[str] = Field(
        default=None, description="Cultural characteristics and customs"
    )
    economy: Optional[str] = Field(
        default=None, description="Economic base and activities"
    )
    trade_goods: List[str] = Field(
        default_factory=list, description="Goods produced or traded (max 5)"
    )
    nearby_landmarks: List[str] = Field(
        default_factory=list, description="Nearby notable locations (max 5)"
    )
    current_events: List[str] = Field(
        default_factory=list, description="Ongoing events (max 3)"
    )
    rumors: List[str] = Field(
        default_factory=list, description="Current rumors or gossip (max 3)"
    )

    model_config = ConfigDict(extra="forbid")


class FactionDetails(BaseModel):
    """
    Additional faction attributes stored in extra_data JSONB.
    """

    leader: Optional[str] = Field(default=None, description="Name of faction leader")
    notable_members: List[str] = Field(
        default_factory=list, description="Other notable members"
    )
    allies: List[str] = Field(
        default_factory=list, description="Allied factions or groups"
    )
    rivals: List[str] = Field(
        default_factory=list, description="Rival factions or groups"
    )
    symbols: Optional[str] = Field(
        default=None, description="Faction symbols, colors, or identifying marks"
    )
    traditions: Optional[str] = Field(
        default=None, description="Key traditions or rituals"
    )

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
# New Entity Creation
# ============================================================================


class NewCharacter(BaseModel):
    """
    Schema for introducing a new character - aligned with DB schema.
    """

    name: str = Field(description="Character's name")
    appearance: Optional[str] = Field(
        default=None, description="Physical description - how the character looks"
    )
    background: Optional[str] = Field(
        default=None, description="Character backstory and history"
    )
    personality: Optional[str] = Field(
        default=None,
        description=(
            "Personality traits and quirks (prose format, e.g., 'Methodical "
            "problem-solver. Paranoid about digital traces.')"
        ),
    )
    emotional_state: Optional[str] = Field(
        default=None, description="Current emotional state"
    )
    current_activity: Optional[str] = Field(
        default=None, description="What the character is currently doing"
    )
    current_location: Optional[int] = Field(
        default=None,
        description="Place ID where character is located (FK to places.id)",
    )
    summary: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Brief character description (max 500 chars)",
    )
    extra_data: Optional[CharacterTraits] = Field(
        default=None,
        description="Character traits (3 of 10 optional traits + required wildcard)",
    )
    orrery_tags: Optional[OrreryTagBestowal] = Field(
        default=None,
        description=(
            "Semantic Orrery tags for this character (bodyform, capacity, "
            "disposition, role, state, etc.). This is an OBJECT whose "
            '"applied_tags" key holds the list of registered tag names — '
            "never a bare list of strings. Omit tags when the closed "
            "registry has no exact fit. See the Orrery Awareness section of "
            "your system prompt for category guidance."
        ),
    )


class NewPlace(BaseModel):
    """
    Schema for introducing a new place - aligned with DB schema.
    Zone is resolved from coordinates or inherited from the story-active place.
    """

    name: str = Field(description="Place name")
    type: PlaceType = Field(
        default=PlaceType.FIXED_LOCATION,
        description="Type of place (fixed_location, vehicle, virtual, other)",
    )
    summary: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Brief place description (max 500 chars)",
    )
    history: Optional[str] = Field(
        default=None, description="Place history and past events"
    )
    current_status: Optional[str] = Field(
        default=None,
        description="Current state, conditions, and activity at this location",
    )
    secrets: Optional[str] = Field(
        default=None,
        description="Hidden information, plot hooks, and narrative opportunities",
    )
    coordinates: Optional[Coordinates] = Field(
        default=None,
        description=(
            "Geographic coordinates (lat/lon on Earth-shaped planet). Zone "
            "calculated from this."
        ),
    )
    inhabitants: Optional[List[int]] = Field(
        default_factory=list,
        description=(
            "Character IDs of inhabitants (usually empty for newly "
            "introduced places)"
        ),
    )
    extra_data: Optional[PlaceDetails] = Field(
        default=None,
        description="Additional place attributes (atmosphere, features, dangers, etc.)",
    )
    orrery_tags: Optional[OrreryTagBestowal] = Field(
        default=None,
        description=(
            "Semantic place tags for this location (e.g., commerce, dwelling, "
            "haven, transit, place_hidden, place_open, wilderness). This is "
            'an OBJECT whose "applied_tags" key holds the list of registered '
            "tag names — never a bare list of strings. Omit tags when the "
            "closed registry has no exact fit."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_place_type(cls, data: Any) -> Any:
        """Coerce descriptive place categories into the database enum."""

        if not isinstance(data, dict):
            return data

        raw_type = data.get("type")
        if not isinstance(raw_type, str):
            return data

        data = dict(data)
        normalized_type = raw_type.strip().lower().replace("-", "_").replace(" ", "_")
        try:
            data["type"] = PlaceType(normalized_type).value
            return data
        except ValueError:
            pass

        vehicle_terms = {"vehicle", "train", "car", "bus", "tram", "ship", "boat"}
        virtual_terms = {"virtual", "digital", "online", "network", "simulation"}
        if normalized_type in vehicle_terms:
            data["type"] = PlaceType.VEHICLE.value
        elif normalized_type in virtual_terms:
            data["type"] = PlaceType.VIRTUAL.value
        else:
            data["type"] = PlaceType.FIXED_LOCATION.value

        extra_data = data.get("extra_data")
        if isinstance(extra_data, dict):
            extra_data = dict(extra_data)
            extra_data.setdefault("category", raw_type)
            data["extra_data"] = extra_data
        elif extra_data is None:
            data["extra_data"] = {"category": raw_type}

        return data


class NewFaction(BaseModel):
    """
    Schema for introducing a new faction.

    Faction semantics live in Orrery tags and pair-tags, not legacy prose
    columns. Leader/member/color detail goes in extra_data or relationships.
    """

    name: str = Field(description="Faction name")
    summary: Optional[str] = Field(
        default=None,
        max_length=500,
        description=(
            "Brief faction description (max 500 chars). Put narrative prose "
            "here when no accepted Orrery tag applies."
        ),
    )
    primary_location: Optional[int] = Field(
        default=None,
        description="Place ID of faction headquarters/primary base (FK to places.id)",
    )
    extra_data: Optional[FactionDetails] = Field(
        default=None,
        description=(
            "Additional faction attributes (leader, members, allies, " "rivals, etc.)"
        ),
    )
    orrery_tags: Optional[OrreryTagBestowal] = Field(
        default=None,
        description=(
            "Closed-vocabulary Orrery tags for this faction. This is an "
            'OBJECT whose "applied_tags" key holds the list of registered '
            "tag names — never a bare list of strings. Use registered tags "
            "from ideology, resource_base, legitimacy, operational_mode, "
            "power_status, and agenda; omit tags when prose is more accurate."
        ),
    )

    model_config = ConfigDict(extra="forbid")


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
        description=(
            "One-line summary of who/what this entity is (becomes the stub "
            "row summary)."
        ),
    )
    coordinates: Optional[Coordinates] = Field(
        default=None,
        description=(
            "Optional real-Earth coordinates for a declared place. Ignored "
            "for character and faction declarations."
        ),
    )
    tag_hints: List[str] = Field(
        default_factory=list,
        description=(
            "Optional registered single-entity tag names for the stub's "
            "minimum viable tag set. Validated against the live tags "
            "registry; unregistered names are hard errors."
        ),
    )
    pair_tag_hints: List[NewEntityPairTagHint] = Field(
        default_factory=list,
        description=(
            "Optional registered pair-tag hints connecting the declared "
            "entity to another named entity."
        ),
    )

    @model_validator(mode="after")
    def coordinates_are_place_only(self) -> "NewEntityDeclaration":
        """Reject GIS data on non-place declarations instead of dropping it."""

        if self.coordinates is not None and self.kind != "place":
            raise ValueError("coordinates are only valid for place declarations")
        return self

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


# ============================================================================
# Entity References (Supporting both existing and new)
# ============================================================================


class CharacterReference(BaseModel):
    """Reference to a character - either existing or new"""

    # For existing character
    character_id: Optional[int] = Field(
        default=None, description="Database ID for existing character"
    )
    character_name: Optional[str] = Field(
        default=None, description="Name for lookup if ID unknown"
    )
    # For new character
    new_character: Optional[NewCharacter] = Field(
        default=None, description="Details for creating new character"
    )
    # How they appear in this chunk
    reference_type: ReferenceType = Field(
        default=ReferenceType.MENTIONED, description="How the character is referenced"
    )

    @model_validator(mode="after")
    def validate_character_reference(self):
        """Ensure we have either existing ref or new character"""
        if not any([self.character_id, self.character_name, self.new_character]):
            raise ValueError(
                "Must provide either character_id, character_name, or new_character"
            )
        return self


class PlaceReference(BaseModel):
    """Reference to a place - either existing or new"""

    # For existing place
    place_id: Optional[int] = Field(
        default=None, description="Database ID for existing place"
    )
    place_name: Optional[str] = Field(
        default=None, description="Name for lookup if ID unknown"
    )
    # For new place
    new_place: Optional[NewPlace] = Field(
        default=None, description="Details for creating new place"
    )
    # How it appears in this chunk (REQUIRED for junction table)
    reference_type: PlaceReferenceType = Field(
        description=(
            "How the place is referenced: setting (primary location), "
            "mentioned (referenced but not visited), or transit (passed through)"
        )
    )
    # Optional evidence field (matches junction table)
    evidence: Optional[str] = Field(
        default=None,
        max_length=500,
        description=(
            "Optional text evidence for this place reference (e.g., specific "
            "quote or context)"
        ),
    )

    @model_validator(mode="after")
    def validate_place_reference(self):
        """Ensure we have either existing ref or new place"""
        if not any([self.place_id, self.place_name, self.new_place]):
            raise ValueError("Must provide either place_id, place_name, or new_place")
        return self


class FactionReference(BaseModel):
    """Reference to a faction - either existing or new"""

    # For existing faction
    faction_id: Optional[int] = Field(
        default=None, description="Database ID for existing faction"
    )
    faction_name: Optional[str] = Field(
        default=None, description="Name for lookup if ID unknown"
    )
    # For new faction
    new_faction: Optional[NewFaction] = Field(
        default=None, description="Details for creating new faction"
    )
    # How it appears
    reference_type: ReferenceType = Field(
        default=ReferenceType.MENTIONED, description="How the faction is referenced"
    )


class ReferencedEntities(BaseModel):
    """
    Collection of all entities referenced in the narrative chunk.
    Supports both existing entities and introduction of new ones.
    """

    characters: List[CharacterReference] = Field(
        default_factory=list,
        description="Characters present or mentioned (existing or new)",
    )
    places: List[PlaceReference] = Field(
        default_factory=list,
        description="Places present or mentioned (existing or new)",
    )
    factions: List[FactionReference] = Field(
        default_factory=list,
        description="Factions present or mentioned (existing or new)",
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
        description=(
            "Episode/season transition: continue current, new episode, or "
            "new season (which also starts new episode)"
        ),
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
        description=(
            "Human-readable time passage (e.g., 'two hours later', 'the next "
            "morning')"
        ),
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
        description=(
            "Whether the in-world clock advances normally this chunk - almost "
            "always 'primary'. Default to 'primary' for any normal in-world "
            "scene where time moves forward with the chunk's time_delta. Only "
            "deviate for: 'flashback' (a scene set in the past - the clock is "
            "not advancing forward), 'atemporal' (the in-world clock does not "
            "apply - dream/hallucination sequences, or realms where time "
            "doesn't behave normally such as strange or alien dimensions), "
            "'extradiegetic' (the user is addressing you out-of-game - no "
            "in-world time passes)."
        ),
    )
    scene_weather: Optional[Literal["clear", "rain", "fog", "snow", "warm"]] = Field(
        default=None,
        description=(
            "Optional anchor-scene weather override for deliberate dramatic "
            "effect; omit to keep derived local weather."
        ),
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
        description=(
            "Additional observations for extra_data JSONB as strict key/value "
            "entries."
        ),
    )
    orrery_tags: Optional[OrreryTagBestowal] = Field(
        default=None,
        description=(
            "Tag deltas for this character. Use applied_tags to apply registered tags "
            "(e.g., they were just cursed → cursed), tags_to_clear to retire "
            "ephemerals that no longer apply (e.g., the geas was lifted). "
            "Use only registered tag names."
        ),
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
        default_factory=list, description="Notable changes since last visit"
    )
    orrery_tags: Optional[OrreryTagBestowal] = Field(
        default=None,
        description=(
            "Tag deltas for this place. Use applied_tags to add registered "
            "semantic place tags, and tags_to_clear to retire ones that no "
            "longer apply (e.g., a haven is now compromised)."
        ),
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
        default_factory=list,
        description=(
            "Recent faction actions for narrative context. Persist durable "
            "facts through world_events or accepted Orrery tags."
        ),
    )
    stance_changes: List[FactionStanceChange] = Field(
        default_factory=list,
        description="Changes in stance toward other entities as strict entries",
    )
    orrery_tags: Optional[OrreryTagBestowal] = Field(
        default=None,
        description=(
            "Tag deltas for this faction. Use applied_tags to add registered "
            "faction tags such as ideology, resource_base, legitimacy, "
            "operational_mode, power_status, or agenda values; use "
            "tags_to_clear to retire active tags that no longer apply."
        ),
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

    @model_validator(mode="before")
    @classmethod
    def expand_compact_updates(cls, data: Any) -> Any:
        """Accept Anthropic's compact scalar wire shape for state updates."""

        if not isinstance(data, dict) or "updates" not in data:
            return data

        expanded = {
            "characters": list(data.get("characters") or []),
            "relationships": list(data.get("relationships") or []),
            "locations": list(data.get("locations") or []),
            "factions": list(data.get("factions") or []),
        }
        for raw_update in data.get("updates") or []:
            if not isinstance(raw_update, dict):
                continue
            kind = raw_update.get("kind")
            if kind == "character":
                update = _compact_character_state_update(raw_update)
                if update:
                    expanded["characters"].append(update)
            elif kind == "place":
                update = _compact_location_state_update(raw_update)
                if update:
                    expanded["locations"].append(update)
            elif kind == "faction":
                update = _compact_faction_state_update(raw_update)
                if update:
                    expanded["factions"].append(update)
            elif kind == "relationship":
                update = _compact_relationship_update(raw_update)
                if update:
                    expanded["relationships"].append(update)
        return expanded

    model_config = ConfigDict(extra="forbid")


def _compact_character_state_update(row: Dict[str, Any]) -> Dict[str, Any]:
    update: Dict[str, Any] = {}
    _copy_if_present(row, update, "entity_id", "character_id")
    name = row.get("name") or row.get("character_name")
    if name:
        update["character_name"] = str(name)
    status = row.get("status")
    if status and "current_activity" not in row:
        update["current_activity"] = str(status)
    _copy_if_present(row, update, "current_location")
    _copy_if_present(row, update, "current_activity")
    _copy_if_present(row, update, "emotional_state")
    _apply_compact_orrery_tags(row, update)
    return update


def _compact_location_state_update(row: Dict[str, Any]) -> Dict[str, Any]:
    update: Dict[str, Any] = {}
    _copy_if_present(row, update, "entity_id", "place_id")
    name = row.get("name") or row.get("place_name")
    if name:
        update["place_name"] = str(name)
    status = row.get("status")
    if status and "current_conditions" not in row:
        update["current_conditions"] = str(status)
    _copy_if_present(row, update, "current_conditions")
    notable_change = row.get("notable_change") or row.get("status")
    if notable_change:
        update["notable_changes"] = [str(notable_change)]
    _apply_compact_orrery_tags(row, update)
    return update


def _compact_faction_state_update(row: Dict[str, Any]) -> Dict[str, Any]:
    update: Dict[str, Any] = {}
    _copy_if_present(row, update, "entity_id", "faction_id")
    name = row.get("name") or row.get("faction_name")
    if name:
        update["faction_name"] = str(name)
    recent_action = row.get("recent_action") or row.get("status")
    if recent_action:
        update["recent_actions"] = [str(recent_action)]
    target = row.get("stance_target")
    stance = row.get("stance")
    if target and stance:
        update["stance_changes"] = [{"target": str(target), "stance": str(stance)}]
    _apply_compact_orrery_tags(row, update)
    return update


def _compact_relationship_update(row: Dict[str, Any]) -> Dict[str, Any]:
    update: Dict[str, Any] = {}
    _copy_if_present(row, update, "entity_id", "character1_id")
    _copy_if_present(row, update, "other_entity_id", "character2_id")
    name = row.get("name") or row.get("character1_name")
    other_name = row.get("other_name") or row.get("character2_name")
    if name:
        update["character1_name"] = str(name)
    if other_name:
        update["character2_name"] = str(other_name)
    _copy_if_present(row, update, "relationship_type")
    _copy_if_present(row, update, "emotional_valence")
    _copy_if_present(row, update, "dynamic")
    _copy_if_present(row, update, "recent_events")
    return update


def _apply_compact_orrery_tags(
    row: Dict[str, Any],
    update: Dict[str, Any],
) -> None:
    tag_add = row.get("tag_add")
    tag_clear = row.get("tag_clear")
    if not tag_add and not tag_clear:
        return
    update["orrery_tags"] = {
        "applied_tags": [str(tag_add)] if tag_add else [],
        "tags_to_clear": [str(tag_clear)] if tag_clear else [],
    }


def _copy_if_present(
    source: Dict[str, Any],
    target: Dict[str, Any],
    key: str,
    target_key: Optional[str] = None,
) -> None:
    value = source.get(key)
    if value is not None and value != "":
        target[target_key or key] = value


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
        description=(
            "Optional limited Orrery delta to commit instead of the proposal. "
            "If omitted for replace, commit assumes Skald handled the replacement "
            "through normal state_updates or prose."
        ),
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
        description="All entities referenced (existing or new)"
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


def validate_entity_references(entities: ReferencedEntities) -> List[str]:
    """
    Validate that entity references are well-formed.
    Returns list of validation warnings.
    """
    warnings = []

    # Check for duplicate characters
    char_names = [
        c.character_name or c.new_character.name
        for c in entities.characters
        if c.character_name or c.new_character
    ]
    if len(char_names) != len(set(char_names)):
        warnings.append("Duplicate character references detected")

    # Check for duplicate places
    place_names = [
        p.place_name or p.new_place.name
        for p in entities.places
        if p.place_name or p.new_place
    ]
    if len(place_names) != len(set(place_names)):
        warnings.append("Duplicate place references detected")

    return warnings


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
