"""
Pydantic schemas for structured outputs during new story initialization.

These schemas are used when new_story=true to receive structured data
from the OpenAI API during the setup conversation phase.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Literal
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


def make_openai_strict_schema(schema: dict) -> dict:
    """
    Transform a Pydantic JSON schema to be OpenAI strict-mode compatible.

    OpenAI strict mode requires:
    1. additionalProperties: false on ALL objects
    2. ALL properties listed in required array (optional = allows null, not missing from required)
    3. $ref cannot have sibling keywords (like description)

    This recursively processes the schema and any $defs.
    Returns a new dict to avoid mutating the input schema.
    """
    import copy
    schema = copy.deepcopy(schema)

    def process_object(obj: dict) -> dict:
        if obj.get("type") != "object":
            return obj

        # Ensure additionalProperties is false
        obj["additionalProperties"] = False

        # Add all properties to required
        if "properties" in obj:
            obj["required"] = list(obj["properties"].keys())

            # Clean $ref properties - remove sibling keywords
            for prop_name, prop_schema in obj["properties"].items():
                if "$ref" in prop_schema:
                    # Keep only the $ref, remove description and other siblings
                    obj["properties"][prop_name] = {"$ref": prop_schema["$ref"]}

        return obj

    # Process $defs (nested model definitions)
    if "$defs" in schema:
        for def_name, def_schema in schema["$defs"].items():
            schema["$defs"][def_name] = process_object(def_schema)

    # Process root object
    return process_object(schema)


class Genre(str, Enum):
    """Supported story genres."""

    FANTASY = "fantasy"
    SCIFI = "scifi"
    HORROR = "horror"
    MYSTERY = "mystery"
    HISTORICAL = "historical"
    CONTEMPORARY = "contemporary"
    POSTAPOC = "postapocalyptic"
    CYBERPUNK = "cyberpunk"
    STEAMPUNK = "steampunk"
    URBAN_FANTASY = "urban_fantasy"
    SPACE_OPERA = "space_opera"
    NOIR = "noir"
    THRILLER = "thriller"


class TechLevel(str, Enum):
    """Technology level for the setting."""

    STONE_AGE = "stone_age"
    BRONZE_AGE = "bronze_age"
    IRON_AGE = "iron_age"
    MEDIEVAL = "medieval"
    RENAISSANCE = "renaissance"
    INDUSTRIAL = "industrial"
    MODERN = "modern"
    NEAR_FUTURE = "near_future"
    FAR_FUTURE = "far_future"
    POST_SINGULARITY = "post_singularity"


class SettingCard(BaseModel):
    """
    Setting information for the story world.

    This defines the overall world, time period, and thematic elements
    that will shape the narrative.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    genre: Genre = Field(..., description="Primary genre of the story")
    secondary_genres: List[Genre] = Field(
        default_factory=list, description="Additional genre elements"
    )

    world_name: str = Field(
        ..., min_length=1, max_length=100, description="Name of the world/setting"
    )
    time_period: str = Field(
        ..., description="Historical period or future date (e.g., '1920s', '2185 CE')"
    )
    tech_level: TechLevel = Field(..., description="General technology level")

    # World details
    magic_exists: bool = Field(
        False, description="Whether magic/supernatural elements exist"
    )
    magic_description: Optional[str] = Field(
        None, description="How magic works if it exists"
    )

    political_structure: str = Field(
        ..., description="Type of government/political system"
    )
    major_conflict: str = Field(
        ..., description="Primary tension or conflict in the world"
    )

    # Atmosphere and tone
    tone: Literal["light", "balanced", "dark", "grimdark"] = Field(
        "balanced", description="Overall tone"
    )
    themes: List[str] = Field(
        ..., min_items=1, max_items=5, description="Major thematic elements"
    )

    # Cultural notes
    cultural_notes: str = Field(
        ..., description="Key cultural elements, customs, or social norms"
    )
    language_notes: Optional[str] = Field(
        None, description="Language quirks or naming conventions"
    )

    # Geographic scope
    geographic_scope: Literal[
        "local", "regional", "continental", "global", "interplanetary"
    ] = Field("regional", description="Scale of the story world")

    @field_validator("themes")
    @classmethod
    def validate_themes(cls, v: List[str]) -> List[str]:
        """Ensure themes are non-empty strings."""
        return [theme.strip() for theme in v if theme.strip()]

    # Diegetic artifact
    diegetic_artifact: str = Field(
        ...,
        description="The full in-world document (e.g., guide entry, dossier, chronicle) describing the setting in a rich, immersive style.",
    )


class CharacterSheet(BaseModel):
    """
    Character definition following Mind's Eye Theatre trait philosophy.

    This aligns with the characters table schema:
    - Core fields (name, summary, appearance, background, personality) map to table columns
    - Traits stored in extra_data JSONB field (exactly 3 of 10 optional + required wildcard)
    - Dynamic fields (emotional_state, current_activity, current_location) set during story seed

    Philosophy: Traits signal what aspects of the character should be narratively foregrounded -
    generating opportunities, complications, and story weight. Not choosing a trait doesn't mean
    absence - just that it won't be a guaranteed source of narrative focus.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    # Core database fields (map directly to characters table columns)
    name: str = Field(
        ..., min_length=1, max_length=50, description="Character's full name"
    )
    summary: str = Field(
        ..., min_length=20, description="Brief character overview capturing essence"
    )
    appearance: str = Field(
        ...,
        min_length=30,
        description="Physical description and how they present themselves",
    )
    background: str = Field(
        ...,
        min_length=50,
        description="Character's history, origin, and what shaped them",
    )
    personality: str = Field(
        ...,
        min_length=30,
        description="Personality traits, behavioral patterns, temperament",
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # TRAIT SYSTEM - Choose exactly 3 of these 10 optional traits
    # Each signals narrative focus, not mechanical capability
    # ═══════════════════════════════════════════════════════════════════════════

    # Social Network
    allies: Optional[str] = Field(
        None, description="Who will actively help and take risks for you"
    )
    contacts: Optional[str] = Field(
        None,
        description="Information/favor sources - limited risk-taking, may be transactional",
    )
    patron: Optional[str] = Field(
        None, description="Powerful mentor/sponsor with their own position and agenda"
    )
    dependents: Optional[str] = Field(
        None, description="Those who rely on you for support, protection, or guidance"
    )

    # Power & Position
    status: Optional[str] = Field(
        None,
        description="Formal standing recognized by an institution or social structure",
    )
    reputation: Optional[str] = Field(
        None, description="How widely known you are, what for, for better or worse"
    )

    # Assets & Territory
    resources: Optional[str] = Field(
        None, description="Material wealth, equipment, supplies, or reliable access"
    )
    domain: Optional[str] = Field(
        None, description="Place or area you control or claim"
    )

    # Liabilities
    enemies: Optional[str] = Field(
        None, description="Those actively opposed who will expend energy to thwart you"
    )
    obligations: Optional[str] = Field(
        None, description="Debts, oaths, or duties you must honor"
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # WILDCARD - Required custom trait that sets this character apart
    # ═══════════════════════════════════════════════════════════════════════════

    wildcard_name: str = Field(
        ..., min_length=1, max_length=50, description="Name of the unique custom trait"
    )
    wildcard_description: str = Field(
        ...,
        min_length=20,
        description="What this trait means for the character - capability, possession, relationship, or curse",
    )

    @model_validator(mode="after")
    def validate_trait_count(self) -> "CharacterSheet":
        """Ensure exactly 3 of 10 optional traits are selected."""
        trait_fields = [
            "allies",
            "contacts",
            "patron",
            "dependents",
            "status",
            "reputation",
            "resources",
            "domain",
            "enemies",
            "obligations",
        ]
        selected = sum(1 for f in trait_fields if getattr(self, f) is not None)
        if selected != 3:
            raise ValueError(
                f"Must select exactly 3 traits from the 10 optional traits. "
                f"Currently selected: {selected}. "
                f"Traits signal narrative focus - choose what matters most for this character."
            )
        return self

    def get_selected_traits(self) -> Dict[str, str]:
        """Return dict of selected trait names and their values."""
        trait_fields = [
            "allies",
            "contacts",
            "patron",
            "dependents",
            "status",
            "reputation",
            "resources",
            "domain",
            "enemies",
            "obligations",
        ]
        return {
            field: getattr(self, field)
            for field in trait_fields
            if getattr(self, field) is not None
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CHARACTER CREATION SUB-PHASE SCHEMAS
# These enable gated progression through character creation with separate tools
# ═══════════════════════════════════════════════════════════════════════════════

# Trait name type for schema validation
TraitName = Literal[
    "allies", "contacts", "patron", "dependents",
    "status", "reputation", "resources", "domain",
    "enemies", "obligations"
]

VALID_TRAIT_NAMES = {
    "allies",
    "contacts",
    "patron",
    "dependents",
    "status",
    "reputation",
    "resources",
    "domain",
    "enemies",
    "obligations",
}


class TraitRationales(BaseModel):
    """
    Rationales for suggested traits - explicit properties for OpenAI strict mode.

    Only the 3 suggested traits need rationales filled in; others remain None.
    Using extra="forbid" generates additionalProperties: false in JSON schema.
    """

    model_config = ConfigDict(extra="forbid")

    allies: Optional[str] = Field(None, description="Why allies trait fits this character")
    contacts: Optional[str] = Field(None, description="Why contacts trait fits this character")
    patron: Optional[str] = Field(None, description="Why patron trait fits this character")
    dependents: Optional[str] = Field(None, description="Why dependents trait fits this character")
    status: Optional[str] = Field(None, description="Why status trait fits this character")
    reputation: Optional[str] = Field(None, description="Why reputation trait fits this character")
    resources: Optional[str] = Field(None, description="Why resources trait fits this character")
    domain: Optional[str] = Field(None, description="Why domain trait fits this character")
    enemies: Optional[str] = Field(None, description="Why enemies trait fits this character")
    obligations: Optional[str] = Field(None, description="Why obligations trait fits this character")

    def to_dict(self) -> Dict[str, str]:
        """Convert to dict with only non-None values."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class TraitSuggestion(BaseModel):
    """Suggested trait with explicit rationale."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: TraitName = Field(..., description="Trait name to suggest")
    rationale: str = Field(
        ...,
        min_length=5,
        description="Why this trait fits the character concept",
    )


class CharacterConceptSubmission(BaseModel):
    """
    Tool submission schema for the character concept with explicit rationales.

    This schema ensures each suggested trait carries its own rationale.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    archetype: str = Field(
        ...,
        min_length=5,
        description="Character archetype/concept (e.g., 'reluctant hero', 'cunning merchant')",
    )
    background: str = Field(
        ...,
        min_length=30,
        description="Character's history, origin, and what shaped them",
    )
    name: str = Field(
        ..., min_length=1, max_length=50, description="Character's full name"
    )
    appearance: str = Field(
        ...,
        min_length=30,
        description="Physical description and how they present themselves",
    )
    suggested_traits: List[TraitSuggestion] = Field(
        default_factory=list,
        max_length=3,
        description="Up to 3 suggested traits with rationales",
    )

    @field_validator("suggested_traits")
    @classmethod
    def validate_unique_trait_names(cls, v: List[TraitSuggestion]) -> List[TraitSuggestion]:
        """Ensure suggested traits are unique."""
        names = [item.name for item in v]
        if names and len(set(names)) != len(names):
            raise ValueError("Suggested traits must be unique")
        return v

    def to_character_concept(self) -> "CharacterConcept":
        """Convert tool submission into the internal CharacterConcept schema."""
        suggested_names = [item.name for item in self.suggested_traits]
        rationales = {item.name: item.rationale for item in self.suggested_traits}
        return CharacterConcept(
            archetype=self.archetype,
            background=self.background,
            name=self.name,
            appearance=self.appearance,
            suggested_traits=suggested_names,
            trait_rationales=TraitRationales(**rationales),
        )


class CharacterConcept(BaseModel):
    """
    Sub-phase 1: Core character concept.

    Captures archetype, background, name, and appearance before moving to trait selection.
    This establishes the foundation that informs trait choices.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    archetype: str = Field(
        ...,
        min_length=5,
        description="Character archetype/concept (e.g., 'reluctant hero', 'cunning merchant')",
    )
    background: str = Field(
        ...,
        min_length=30,
        description="Character's history, origin, and what shaped them",
    )
    name: str = Field(
        ..., min_length=1, max_length=50, description="Character's full name"
    )
    appearance: str = Field(
        ...,
        min_length=30,
        description="Physical description and how they present themselves",
    )

    # Pre-selected trait suggestions for phase 2.2
    # Optional with defaults for intermediate state; validated when submitting via LLM
    suggested_traits: List[TraitName] = Field(
        default_factory=list,
        max_length=3,
        description="3 trait names that would create interesting story tensions for this character",
    )
    trait_rationales: TraitRationales = Field(
        default_factory=TraitRationales,
        description="Rationales for each suggested trait explaining why it fits this character",
    )

    @field_validator("suggested_traits")
    @classmethod
    def validate_unique_traits(cls, v: List[str]) -> List[str]:
        """Ensure unique traits (validation only applies when traits are present)."""
        if v and len(set(v)) != len(v):
            raise ValueError("Suggested traits must be unique")
        return v

    @model_validator(mode="after")
    def validate_rationales_match_traits(self) -> "CharacterConcept":
        """Ensure rationales exist for all suggested traits (when present)."""
        if not self.suggested_traits:
            return self  # Skip validation during early subphases
        rationales_dict = self.trait_rationales.to_dict()
        for trait in self.suggested_traits:
            if trait not in rationales_dict:
                raise ValueError(f"Missing rationale for suggested trait: {trait}")
        return self


class TraitSelection(BaseModel):
    """
    Sub-phase 2: Trait selection with rationale.

    Captures the 3 selected traits from the 10 optional traits,
    along with rationales explaining why each fits the character.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    selected_traits: List[str] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Exactly 3 trait names from: allies, contacts, patron, dependents, status, reputation, resources, domain, enemies, obligations",
    )
    trait_rationales: TraitRationales = Field(
        ...,
        description="Rationales for each selected trait explaining why it fits this character",
    )
    suggested_by_llm: List[str] = Field(
        default_factory=list,
        description="The 3 traits Skald pre-selected as fitting for this character",
    )

    @field_validator("selected_traits")
    @classmethod
    def validate_trait_names(cls, v: List[str]) -> List[str]:
        """Ensure all trait names are valid."""
        normalized = [t.lower().strip() for t in v]
        for trait in normalized:
            if trait not in VALID_TRAIT_NAMES:
                raise ValueError(
                    f"Invalid trait: '{trait}'. Must be one of: {', '.join(sorted(VALID_TRAIT_NAMES))}"
                )
        if len(set(normalized)) != 3:
            raise ValueError("Must select exactly 3 unique traits")
        return normalized


class WildcardTrait(BaseModel):
    """
    Sub-phase 3: Custom wildcard trait.

    The wildcard is a required custom trait that sets the character apart -
    something unique that can't be found in the standard trait menu.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    wildcard_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Name of the unique custom trait",
    )
    wildcard_description: str = Field(
        ...,
        min_length=20,
        description="What this trait means - capability, possession, relationship, blessing, or curse",
    )


class CharacterCreationState(BaseModel):
    """
    Accumulator for character creation sub-phases.

    Tracks progress through the three sub-phases and provides methods
    to assemble the complete CharacterSheet when all phases are done.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    concept: Optional[CharacterConcept] = None
    trait_selection: Optional[TraitSelection] = None
    wildcard: Optional[WildcardTrait] = None

    # Fleshed-out trait descriptions (filled in during trait development dialog)
    trait_details: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of trait name to fleshed-out description from dialog",
    )

    # Additional fields gathered during conversation
    summary: Optional[str] = Field(None, description="Brief character summary")
    personality: Optional[str] = Field(None, description="Personality description")

    def current_subphase(self) -> Literal["concept", "traits", "wildcard", "complete"]:
        """Determine which sub-phase we're currently in."""
        if self.concept is None:
            return "concept"
        if self.trait_selection is None:
            return "traits"
        if self.wildcard is None:
            return "wildcard"
        return "complete"

    def is_complete(self) -> bool:
        """Check if all sub-phases are complete."""
        return all([self.concept, self.trait_selection, self.wildcard])

    def to_character_sheet(self) -> "CharacterSheet":
        """
        Assemble complete CharacterSheet from sub-phase data.

        Raises:
            ValueError: If any required sub-phase data is missing
        """
        if not self.is_complete():
            missing = []
            if not self.concept:
                missing.append("concept")
            if not self.trait_selection:
                missing.append("trait_selection")
            if not self.wildcard:
                missing.append("wildcard")
            raise ValueError(f"Cannot assemble CharacterSheet - missing: {missing}")

        # Build trait kwargs
        trait_kwargs: Dict[str, Any] = {}
        rationales = self.trait_selection.trait_rationales.to_dict()
        for trait_name in self.trait_selection.selected_traits:
            # Use fleshed-out description if available, otherwise use rationale
            if trait_name in self.trait_details:
                trait_kwargs[trait_name] = self.trait_details[trait_name]
            elif trait_name in rationales:
                trait_kwargs[trait_name] = rationales[trait_name]
            else:
                trait_kwargs[trait_name] = f"Selected during character creation"

        return CharacterSheet(
            name=self.concept.name,
            summary=self.summary or f"A {self.concept.archetype}",
            appearance=self.concept.appearance,
            background=self.concept.background,
            personality=self.personality or "Personality to be revealed through play.",
            wildcard_name=self.wildcard.wildcard_name,
            wildcard_description=self.wildcard.wildcard_description,
            **trait_kwargs,
        )


class StoryTimestamp(BaseModel):
    """
    Atomized timestamp for story start - LLM-friendly integer fields.

    Instead of asking the LLM to generate a complex ISO 8601 string
    or parse natural language like "Late afternoon, spring equinox",
    we use constrained integer fields that are validated individually.

    Example:
        >>> ts = StoryTimestamp(year=1347, month=9, day=15, hour=16, minute=30)
        >>> ts.to_datetime()
        datetime(1347, 9, 15, 16, 30, 0, tzinfo=timezone.utc)
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    year: int = Field(..., ge=1, le=9999, description="Year (1-9999; clamp to datetime range)")
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    day: int = Field(..., ge=1, le=31, description="Day of month (1-31)")
    hour: int = Field(..., ge=0, le=23, description="Hour in 24h format (0-23)")
    minute: int = Field(..., ge=0, le=59, description="Minute (0-59)")

    @model_validator(mode="after")
    def validate_date(self) -> "StoryTimestamp":
        """Validate day is valid for the given month/year."""
        import calendar

        max_day = calendar.monthrange(self.year, self.month)[1]
        if self.day > max_day:
            raise ValueError(
                f"Day {self.day} is invalid for month {self.month} (max: {max_day})"
            )
        return self

    def to_datetime(self, tz: timezone = timezone.utc) -> datetime:
        """Convert to datetime object with seconds=0."""
        return datetime(
            year=self.year,
            month=self.month,
            day=self.day,
            hour=self.hour,
            minute=self.minute,
            second=0,
            tzinfo=tz,
        )


class StorySeedType(str, Enum):
    """Types of story openings."""

    IN_MEDIAS_RES = "in_medias_res"  # Start in the middle of action
    DISCOVERY = "discovery"  # Character discovers something
    ARRIVAL = "arrival"  # Character arrives somewhere new
    MEETING = "meeting"  # Character meets someone important
    CRISIS = "crisis"  # Immediate problem to solve
    MYSTERY = "mystery"  # Unexplained event or situation
    OPPORTUNITY = "opportunity"  # New chance or offer
    LOSS = "loss"  # Something/someone is lost
    THREAT = "threat"  # Danger approaches


class StorySeed(BaseModel):
    """
    A potential story starting point.

    The system generates 3 of these for the user to choose from.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    seed_type: StorySeedType = Field(..., description="Type of story opening")
    title: str = Field(
        ..., min_length=1, max_length=100, description="Short, evocative title"
    )

    # Opening scenario
    situation: str = Field(..., min_length=50, description="The opening situation")
    hook: str = Field(..., min_length=20, description="What makes this compelling")
    immediate_goal: str = Field(..., description="Character's immediate objective")

    # Stakes and tension
    stakes: str = Field(..., description="What's at risk")
    tension_source: str = Field(..., description="Source of narrative tension")

    # Setting details
    base_timestamp: StoryTimestamp = Field(
        ...,
        description="When the story begins - provide year, month, day, hour, minute",
    )
    weather: Optional[str] = Field(None, description="Weather conditions if relevant")

    # Initial elements
    key_npcs: List[str] = Field(
        default_factory=list,
        max_items=4,
        description="Key figures or allies present in the opening",
    )

    # Secret channel content (LLM-to-LLM, user never sees)
    secrets: str = Field(
        ...,
        min_length=50,
        description="Hidden plot information: NPC hidden agendas, twists, complications waiting to emerge. User never sees this - LLM-to-LLM channel for dramatic irony.",
    )

    def get_base_datetime(self, tz: timezone = timezone.utc) -> datetime:
        """Get base_timestamp as a datetime object."""
        return self.base_timestamp.to_datetime(tz)


class LayerType(str, Enum):
    """Types of world layers."""

    PLANET = "planet"
    DIMENSION = "dimension"


class LayerDefinition(BaseModel):
    """
    Definition of a world layer (planet/realm/dimension).

    This is the top level of the location hierarchy: layer -> zone -> place
    Maps directly to the layers table.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Layer name (e.g., 'Earth', 'Aethermoor')",
    )
    type: LayerType = Field(..., description="Type of layer (planet or dimension)")
    description: str = Field(
        ..., min_length=20, description="Description of this world/realm"
    )


class PlaceExtraData(BaseModel):
    """Optional location details stored in places.extra_data (JSONB)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    atmosphere: Optional[str] = Field(None, description="Mood and feeling of the place")
    resources: List[str] = Field(
        default_factory=list, max_items=5, description="Available resources"
    )
    dangers: List[str] = Field(
        default_factory=list, max_items=5, description="Known threats or hazards"
    )
    ruler: Optional[str] = Field(None, description="Who controls or governs this place")
    factions: List[str] = Field(
        default_factory=list, max_items=5, description="Active factions or groups"
    )
    culture: Optional[str] = Field(
        None, description="Cultural characteristics and customs"
    )
    economy: Optional[str] = Field(None, description="Economic base and activities")
    nearby_landmarks: List[str] = Field(
        default_factory=list, max_items=5, description="Nearby notable locations"
    )
    rumors: List[str] = Field(
        default_factory=list, max_items=3, description="Current rumors or gossip"
    )


class PlaceProfile(BaseModel):
    """
    Detailed information about a location.

    Aligns with the places table in the database:
    - Core fields map to columns (name, type, summary, inhabitants, history, current_status, secrets)
    - Coordinates stored as PostGIS geography type
    - Optional attributes stored in extra_data JSONB
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    # Core database fields
    name: str = Field(..., min_length=1, max_length=50, description="Place name")
    place_type: Literal["fixed_location", "vehicle", "virtual", "other"] = Field(
        "fixed_location", description="Type of place matching database enum"
    )

    # Description fields (map to database columns)
    summary: str = Field(
        ..., min_length=50, description="Detailed description of the location"
    )
    history: str = Field(
        ..., min_length=30, description="Historical background and significance"
    )
    current_status: str = Field(
        ...,
        min_length=20,
        description="Present condition, activity, and what's happening now",
    )
    secrets: str = Field(
        ...,
        description="Hidden information, dangers, or plot hooks - every location has secrets",
    )

    # Inhabitants (stored as text array in database)
    inhabitants: List[str] = Field(
        default_factory=list,
        max_items=10,
        description="Who lives, works, or frequents this location",
    )

    # Geographic information (required for database)
    coordinates: List[float] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Latitude and longitude coordinates [lat, lon] for the place",
    )

    # Optional attributes stored in extra_data JSONB
    extra_data: Optional[PlaceExtraData] = Field(
        None, description="Additional attributes stored in places.extra_data"
    )


class ZoneType(str, Enum):
    """Types of zones within a location."""

    PUBLIC = "public"
    PRIVATE = "private"
    COMMERCIAL = "commercial"
    RESIDENTIAL = "residential"
    INDUSTRIAL = "industrial"
    SACRED = "sacred"
    FORBIDDEN = "forbidden"
    WILDERNESS = "wilderness"


class ZoneDefinition(BaseModel):
    """
    A geographic zone that contains places.

    Zones are geographic regions with optional boundaries (PostGIS polygons).
    They form the middle tier: layer -> zone -> place
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=50, description="Zone name")
    summary: str = Field(
        ..., min_length=20, max_length=500, description="Zone description"
    )

    # Note: PostGIS boundary polygon will be generated later if needed


class StartingScenario(BaseModel):
    """
    Combined wrapper for seed phase submission.

    This model wraps all 4 components needed for starting a new story,
    ensuring Pydantic generates a unified JSON schema with all $defs
    hoisted to the root level (required for OpenAI strict mode).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    seed: StorySeed
    layer: LayerDefinition
    zone: ZoneDefinition
    location: PlaceProfile


class SpecificLocation(BaseModel):
    """
    A specific location within a place where scenes occur.

    This represents the exact spot where the story begins (e.g., "Common Room" within "The Inn").
    Not stored in database but used for narrative context.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100, description="Location name")
    zone_type: ZoneType = Field(..., description="Type of location")
    parent_place: str = Field(..., description="The place this location belongs to")

    # Description
    description: str = Field(..., min_length=30, description="Location description")
    purpose: str = Field(..., description="Primary function of this location")

    # Physical layout
    size: Literal["tiny", "small", "medium", "large", "huge"] = Field("medium")
    layout: str = Field(..., description="Physical layout and arrangement")

    # Sensory details
    sights: str = Field(..., description="What can be seen")
    sounds: str = Field(..., description="What can be heard")
    smells: Optional[str] = Field(None, description="What can be smelled")

    # Access and movement
    entrances: List[str] = Field(..., min_items=1, description="How to enter/exit")
    connected_areas: List[str] = Field(
        default_factory=list, description="Adjacent areas"
    )
    accessibility: Literal["public", "restricted", "private", "secret"] = Field(
        "public"
    )

    # Current state
    occupants: List[str] = Field(
        default_factory=list, description="Who's typically here"
    )
    objects: List[str] = Field(
        ..., min_items=1, description="Notable objects or furniture"
    )
    lighting: Literal["dark", "dim", "normal", "bright", "variable"] = Field("normal")

    # Activity
    typical_activities: List[str] = Field(
        ..., min_items=1, description="What happens here"
    )
    busy_times: Optional[str] = Field(
        None, description="When this location is most active"
    )


class TransitionData(BaseModel):
    """
    Complete data package for transitioning from setup to narrative mode.

    This contains all the structured data collected during new story initialization.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    # Core components
    setting: SettingCard = Field(..., description="World and setting information")
    character: CharacterSheet = Field(
        ..., description="Complete protagonist definition"
    )
    seed: StorySeed = Field(..., description="Selected story opening")

    # Location hierarchy: layer -> zone -> place
    layer: LayerDefinition = Field(..., description="World layer (planet/dimension)")
    zone: ZoneDefinition = Field(..., description="Geographic zone")
    location: PlaceProfile = Field(
        ..., description="Starting place with exact coordinates"
    )

    # Timing
    base_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="In-game starting time",
    )

    # Session metadata
    thread_id: str = Field(..., description="OpenAI conversation thread ID")
    setup_duration_minutes: Optional[int] = Field(
        None, description="How long setup took"
    )

    # Validation flags
    ready_for_transition: bool = Field(
        False, description="All required fields complete"
    )
    validated: bool = Field(False, description="Data has been validated")

    def validate_completeness(self) -> bool:
        """
        Check if all required data is present for transition.

        Returns:
            True if ready to transition to narrative mode
        """
        required_complete = all(
            [
                self.setting,
                self.character,
                self.seed,
                self.layer,
                self.zone,
                self.location,
                self.base_timestamp,
                self.thread_id,
            ]
        )

        if required_complete:
            # Additional validation
            character_ready = (
                self.character.name
                and self.character.summary
                and self.character.background
                and self.character.personality
                and self.character.appearance
            )

            location_ready = bool(
                self.location.name and self.location.summary and self.zone.name
            )

            self.validated = bool(character_ready and location_ready)
            self.ready_for_transition = self.validated

        return self.ready_for_transition


class NewStoryValidation(BaseModel):
    """
    Validation response for checking transition readiness.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    is_valid: bool = Field(..., description="Whether data is valid")
    ready_for_transition: bool = Field(..., description="Ready to start narrative")

    missing_fields: List[str] = Field(
        default_factory=list, description="Required fields that are missing"
    )
    validation_errors: List[str] = Field(
        default_factory=list, description="Validation error messages"
    )

    # Component status
    setting_complete: bool = Field(False)
    character_complete: bool = Field(False)
    seed_complete: bool = Field(False)
    location_complete: bool = Field(False)
    zone_complete: bool = Field(False)


# Example structured output request for OpenAI
SETTING_CARD_SCHEMA_PROMPT = """
Generate a SettingCard based on the user's preferences. The output must be valid JSON
that conforms to the SettingCard schema. Include rich detail while maintaining consistency
with the genre and tone selected.
"""

CHARACTER_SHEET_SCHEMA_PROMPT = """
Create a CharacterSheet with:
- Core identity fields: name, summary, appearance, background, personality
- Exactly 3 of 10 optional traits (see attached Trait Reference)
- Required wildcard trait (wildcard_name + wildcard_description)

The output must be valid JSON conforming to the CharacterSheet schema.
"""

STORY_SEEDS_SCHEMA_PROMPT = """
Generate 3 unique StorySeed options based on the setting and character. Each should offer
a different type of opening with clear player agency. Return a JSON array of 3 StorySeed objects.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# WIZARD RESPONSE ENVELOPE
# Enforces structured choices on every Skald response via OpenAI response_format
# ═══════════════════════════════════════════════════════════════════════════════


class WizardResponse(BaseModel):
    """
    Structured response envelope for all wizard interactions.

    Every Skald response MUST include 2-4 short choice strings.
    The backend/UI handles numbering/labeling. This schema is enforced
    via OpenAI response_format with strict=True.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    message: str = Field(
        ...,
        min_length=10,
        description="Skald's narrative response to the user. Should be engaging and "
        "guide the conversation forward.",
    )
    choices: List[str] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="2-4 concise choices for the user to select from. Do not include numbering or markdown formatting.",
    )

    @field_validator("choices")
    @classmethod
    def validate_choice_content(cls, v: List[str]) -> List[str]:
        """Ensure all choices are non-empty strings."""
        if not all(isinstance(c, str) and c.strip() for c in v):
            raise ValueError("All choices must be non-empty strings")
        return [c.strip() for c in v]
