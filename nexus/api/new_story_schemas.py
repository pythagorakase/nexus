"""
Pydantic schemas for structured outputs during new story initialization.

These schemas are used when new_story=true to receive structured data
from the OpenAI API during the setup conversation phase.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Literal
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, field_validator


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
    secondary_genres: List[Genre] = Field(default_factory=list, description="Additional genre elements")

    world_name: str = Field(..., min_length=1, max_length=100, description="Name of the world/setting")
    time_period: str = Field(..., description="Historical period or future date (e.g., '1920s', '2185 CE')")
    tech_level: TechLevel = Field(..., description="General technology level")

    # World details
    magic_exists: bool = Field(False, description="Whether magic/supernatural elements exist")
    magic_description: Optional[str] = Field(None, description="How magic works if it exists")

    political_structure: str = Field(..., description="Type of government/political system")
    major_conflict: str = Field(..., description="Primary tension or conflict in the world")

    # Atmosphere and tone
    tone: Literal["light", "balanced", "dark", "grimdark"] = Field("balanced", description="Overall tone")
    themes: List[str] = Field(..., min_items=1, max_items=5, description="Major thematic elements")

    # Cultural notes
    cultural_notes: str = Field(..., description="Key cultural elements, customs, or social norms")
    language_notes: Optional[str] = Field(None, description="Language quirks or naming conventions")

    # Geographic scope
    geographic_scope: Literal["local", "regional", "continental", "global", "interplanetary"] = Field(
        "regional",
        description="Scale of the story world"
    )

    @field_validator('themes')
    @classmethod
    def validate_themes(cls, v: List[str]) -> List[str]:
        """Ensure themes are non-empty strings."""
        return [theme.strip() for theme in v if theme.strip()]

    # Diegetic artifact
    diegetic_artifact: str = Field(..., description="The full in-world document (e.g., guide entry, dossier, chronicle) describing the setting in a rich, immersive style.")


class CharacterBackground(str, Enum):
    """Common character background types."""
    NOBLE = "noble"
    COMMONER = "commoner"
    MERCHANT = "merchant"
    SCHOLAR = "scholar"
    SOLDIER = "soldier"
    CRIMINAL = "criminal"
    ARTISAN = "artisan"
    CLERGY = "clergy"
    WANDERER = "wanderer"
    OUTCAST = "outcast"
    OTHER = "other"


class CharacterSheet(BaseModel):
    """
    Complete character definition for the protagonist.

    This aligns with the characters table schema in the database.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    # Basic information (required fields from characters table)
    name: str = Field(..., min_length=1, max_length=100, description="Character's full name")
    age: int = Field(..., ge=0, le=500, description="Character's age in years")
    gender: Literal["male", "female", "non-binary", "other"] = Field(..., description="Character's gender")
    species: str = Field("human", description="Character's species/race")

    # Background and role
    background: CharacterBackground = Field(..., description="Character's social background")
    occupation: str = Field(..., description="Current occupation or role")
    faction: Optional[str] = Field(None, description="Affiliated faction or organization")

    # Physical description
    height: str = Field(..., description="Height description (e.g., 'tall', '5 feet 8 inches')")
    build: str = Field(..., description="Body build (e.g., 'athletic', 'slender', 'stocky')")
    appearance: str = Field(..., min_length=20, description="Physical appearance description")
    distinguishing_features: List[str] = Field(default_factory=list, max_items=5, description="Notable physical features")

    # Personality and traits
    personality: str = Field(..., min_length=20, description="Personality description")
    motivations: List[str] = Field(..., min_items=1, max_items=3, description="Core motivations")
    fears: List[str] = Field(..., min_items=1, max_items=3, description="Major fears or anxieties")

    # Abilities and skills
    skills: List[str] = Field(..., min_items=1, max_items=10, description="Notable skills and abilities")
    weaknesses: List[str] = Field(..., min_items=1, max_items=3, description="Character weaknesses or limitations")
    special_abilities: Optional[List[str]] = Field(None, description="Magical or special abilities if any")

    # Background story
    backstory: str = Field(..., min_length=50, description="Character's history and background")
    family: Optional[str] = Field(None, description="Family situation and relationships")

    # Starting conditions
    possessions: List[str] = Field(..., min_items=1, description="Starting equipment and possessions")
    wealth_level: Literal["destitute", "poor", "modest", "comfortable", "wealthy", "rich"] = Field(
        "modest",
        description="Economic status"
    )

    # Relationships
    allies: Optional[List[str]] = Field(default_factory=list, description="Initial allies or friends")
    enemies: Optional[List[str]] = Field(default_factory=list, description="Initial enemies or rivals")

    # Character arc potential
    growth_areas: List[str] = Field(..., min_items=1, max_items=3, description="Areas for character development")

    @field_validator('skills', 'motivations', 'fears', 'weaknesses', 'growth_areas')
    @classmethod
    def validate_string_lists(cls, v: List[str]) -> List[str]:
        """Ensure list items are non-empty strings."""
        return [item.strip() for item in v if item.strip()]

    # Diegetic artifact
    diegetic_artifact: str = Field(..., description="A rich narrative portrait or dossier of the character, written in a style appropriate for the setting.")


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
    title: str = Field(..., min_length=1, max_length=100, description="Short, evocative title")

    # Opening scenario
    situation: str = Field(..., min_length=50, description="The opening situation")
    hook: str = Field(..., min_length=20, description="What makes this compelling")
    immediate_goal: str = Field(..., description="Character's immediate objective")

    # Stakes and tension
    stakes: str = Field(..., description="What's at risk")
    tension_source: str = Field(..., description="Source of narrative tension")

    # Setting details
    starting_location: str = Field(..., description="Where the story begins")
    time_of_day: str = Field(..., description="When the scene takes place")
    weather: Optional[str] = Field(None, description="Weather conditions if relevant")

    # Initial elements
    key_npcs: List[str] = Field(default_factory=list, max_items=3, description="Important NPCs in opening")
    initial_mystery: Optional[str] = Field(None, description="Mystery or question to explore")

    # Player agency
    immediate_choices: List[str] = Field(..., min_items=2, max_items=4, description="Initial choices available")
    potential_allies: List[str] = Field(default_factory=list, description="Potential allies nearby")
    potential_obstacles: List[str] = Field(..., min_items=1, description="Initial challenges")


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

    name: str = Field(..., min_length=1, max_length=50, description="Layer name (e.g., 'Earth', 'Aethermoor')")
    type: LayerType = Field(..., description="Type of layer (planet or dimension)")
    description: str = Field(..., min_length=20, description="Description of this world/realm")


class PlaceCategory(str, Enum):
    """Categories of locations."""
    SETTLEMENT = "settlement"
    WILDERNESS = "wilderness"
    DUNGEON = "dungeon"
    BUILDING = "building"
    DISTRICT = "district"
    LANDMARK = "landmark"
    ROAD = "road"
    BORDER = "border"


class PlaceProfile(BaseModel):
    """
    Detailed information about a location.

    Aligns with the places table in the database.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100, description="Place name")
    category: PlaceCategory = Field(..., description="Type of location")

    # Description
    description: str = Field(..., min_length=50, description="Detailed description")
    atmosphere: str = Field(..., description="Mood and feeling of the place")

    # Physical characteristics
    size: Literal["tiny", "small", "medium", "large", "huge", "massive"] = Field("medium")
    population: Optional[int] = Field(None, description="Population if applicable")

    # Geographic information
    region: str = Field(..., description="Broader region this place belongs to")
    coordinates: List[float] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Latitude and longitude coordinates [lat, lon] for the place"
    )
    nearby_landmarks: List[str] = Field(default_factory=list, max_items=5, description="Nearby notable locations")

    # Features
    notable_features: List[str] = Field(..., min_items=1, max_items=5, description="Distinctive features")
    resources: List[str] = Field(default_factory=list, description="Available resources")
    dangers: List[str] = Field(default_factory=list, description="Potential threats")

    # Social aspects
    ruler: Optional[str] = Field(None, description="Who controls this place")
    factions: List[str] = Field(default_factory=list, description="Active factions")
    culture: str = Field(..., description="Cultural characteristics")

    # Economic aspects
    economy: Optional[str] = Field(None, description="Economic base if applicable")
    trade_goods: List[str] = Field(default_factory=list, description="Goods traded here")

    # Current state
    current_events: List[str] = Field(default_factory=list, max_items=3, description="Ongoing events")
    rumors: List[str] = Field(default_factory=list, max_items=3, description="Current rumors")


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
    summary: str = Field(..., min_length=20, max_length=500, description="Zone description")

    # Geographic shape (will be converted to PostGIS MultiPolygon)
    boundary_description: Optional[str] = Field(
        None,
        description="Textual description of zone boundaries (e.g., 'Northern mountains to eastern river')"
    )
    approximate_area: Optional[str] = Field(
        None,
        description="Rough size estimate (e.g., '100 square miles', 'size of France')"
    )

    # Note: actual PostGIS boundary polygon will be added later if needed
    # For now, we just need the zone to exist in the hierarchy


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
    connected_areas: List[str] = Field(default_factory=list, description="Adjacent areas")
    accessibility: Literal["public", "restricted", "private", "secret"] = Field("public")

    # Current state
    occupants: List[str] = Field(default_factory=list, description="Who's typically here")
    objects: List[str] = Field(..., min_items=1, description="Notable objects or furniture")
    lighting: Literal["dark", "dim", "normal", "bright", "variable"] = Field("normal")

    # Activity
    typical_activities: List[str] = Field(..., min_items=1, description="What happens here")
    busy_times: Optional[str] = Field(None, description="When this location is most active")


class TransitionData(BaseModel):
    """
    Complete data package for transitioning from setup to narrative mode.

    This contains all the structured data collected during new story initialization.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    # Core components
    setting: SettingCard = Field(..., description="World and setting information")
    character: CharacterSheet = Field(..., description="Complete protagonist definition")
    seed: StorySeed = Field(..., description="Selected story opening")

    # Location hierarchy: layer -> zone -> place
    layer: LayerDefinition = Field(..., description="World layer (planet/dimension)")
    zone: ZoneDefinition = Field(..., description="Geographic zone")
    location: PlaceProfile = Field(..., description="Starting place with exact coordinates")

    # Timing
    base_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="In-game starting time"
    )

    # Session metadata
    thread_id: str = Field(..., description="OpenAI conversation thread ID")
    setup_duration_minutes: Optional[int] = Field(None, description="How long setup took")

    # Validation flags
    ready_for_transition: bool = Field(False, description="All required fields complete")
    validated: bool = Field(False, description="Data has been validated")

    def validate_completeness(self) -> bool:
        """
        Check if all required data is present for transition.

        Returns:
            True if ready to transition to narrative mode
        """
        required_complete = all([
            self.setting,
            self.character,
            self.seed,
            self.layer,
            self.zone,
            self.location,
            self.base_timestamp,
            self.thread_id
        ])

        if required_complete:
            # Additional validation
            character_ready = (
                self.character.name and
                self.character.backstory and
                len(self.character.skills) > 0
            )

            location_ready = (
                self.location.name and
                self.location.description and
                self.zone.name
            )

            self.validated = character_ready and location_ready
            self.ready_for_transition = self.validated

        return self.ready_for_transition


class NewStoryValidation(BaseModel):
    """
    Validation response for checking transition readiness.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    is_valid: bool = Field(..., description="Whether data is valid")
    ready_for_transition: bool = Field(..., description="Ready to start narrative")

    missing_fields: List[str] = Field(default_factory=list, description="Required fields that are missing")
    validation_errors: List[str] = Field(default_factory=list, description="Validation error messages")

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
Create a complete CharacterSheet for the protagonist based on the setting and user input.
The character should be compelling, with clear motivations and room for growth. The output
must be valid JSON conforming to the CharacterSheet schema.
"""

STORY_SEEDS_SCHEMA_PROMPT = """
Generate 3 unique StorySeed options based on the setting and character. Each should offer
a different type of opening with clear player agency. Return a JSON array of 3 StorySeed objects.
"""