"""
Tests for new story structured output schemas and database mapping.

These tests verify that:
1. Our Pydantic schemas are valid
2. Structured output works with our schemas
3. Database mapping correctly transforms schemas to table format
"""

import os
import pytest
import json
from datetime import datetime, timezone
from typing import Dict, Any

from pydantic import ValidationError

from nexus.api.new_story_schemas import (
    SettingCard,
    CharacterSheet,
    CharacterTrait,
    StorySeed,
    StoryTimestamp,
    LayerDefinition,
    LayerType,
    ZoneDefinition,
    PlaceProfile,
    TransitionData,
    Genre,
    TechLevel,
    StorySeedType,
    PlaceExtraData,
)
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.api.new_story_generator import StoryComponentGenerator

RUN_LIVE_LLM = os.environ.get("NEXUS_RUN_LIVE_LLM") == "1"


class TestNewStorySchemas:
    """Test the Pydantic schemas for new story initialization."""

    def test_setting_card_creation(self):
        """Test creating a valid SettingCard."""
        setting = SettingCard(
            genre=Genre.FANTASY,
            secondary_genres=[Genre.MYSTERY],
            world_name="Aethermoor",
            time_period="Age of Twilight",
            tech_level=TechLevel.MEDIEVAL,
            magic_exists=True,
            magic_description="Elemental magic drawn from ley lines",
            political_structure="Feudal kingdoms with mage councils",
            major_conflict="The Shadow Plague spreading from the north",
            tone="balanced",
            themes=["redemption", "sacrifice", "corruption"],
            cultural_notes="Honor-based society with strict magical laws",
            geographic_scope="regional",
            diegetic_artifact="From the Chronicles of the Twilight Age: In the realm of Aethermoor, "
                             "where ley lines pulse with elemental power, the great kingdoms stand vigilant "
                             "against the creeping Shadow Plague from the frozen north...",
        )

        assert setting.world_name == "Aethermoor"
        assert setting.genre == Genre.FANTASY
        assert setting.magic_exists is True
        assert len(setting.themes) == 3

        # Test JSON serialization
        json_data = setting.model_dump_json()
        assert "Aethermoor" in json_data

    def test_character_sheet_creation(self):
        """Test creating a valid CharacterSheet with Mind's Eye Theatre traits."""
        character = CharacterSheet(
            name="Lyra Shadowheart",
            summary="A half-elf arcane investigator searching for her missing parents",
            appearance="Tall half-elf with silver hair and violet eyes, bearing arcane tattoos that glow faintly",
            background="Orphaned at a young age when her parents vanished during a magical experiment. "
                       "Raised by the Order of the Silver Eye, she now investigates arcane crimes.",
            personality="Cautious and analytical, with a dry sense of humor. She keeps people at arm's length "
                       "but fiercely protects those she allows into her circle.",
            trait_1=CharacterTrait(
                name="allies",
                description="Master Aldric, her mentor and father figure within the Order",
            ),
            trait_2=CharacterTrait(
                name="reputation",
                description="Known as the 'Shadow Seer' for solving impossible cases",
            ),
            trait_3=CharacterTrait(
                name="enemies",
                description="The Crimson Hand cult who may know what happened to her parents",
            ),
            # Required wildcard trait
            wildcard_name="Arcane Tattoos",
            wildcard_description="Mystical tattoos that glow when magic is near, granting her "
                                "supernatural perception but marking her as unusual",
        )

        assert character.name == "Lyra Shadowheart"
        assert "half-elf" in character.summary
        assert {"allies", "reputation", "enemies"} == {
            character.trait_1.name,
            character.trait_2.name,
            character.trait_3.name,
        }

    def test_story_seed_creation(self):
        """Test creating a valid StorySeed with atomized timestamp."""
        seed = StorySeed(
            seed_type=StorySeedType.MYSTERY,
            title="The Vanishing Merchants",
            situation="Three merchant caravans have disappeared on the road to Westmarch in the past moon. "
                     "You've been hired to investigate the latest disappearance.",
            hook="The merchants were carrying rare magical artifacts that could be dangerous if misused",
            immediate_goal="Find clues at the last known campsite",
            stakes="More disappearances could cripple trade and starve the region",
            tension_source="Time pressure - another caravan departs tomorrow",
            base_timestamp=StoryTimestamp(year=1347, month=9, day=15, hour=16, minute=30),
            weather="Gathering storm clouds",
            key_npcs=["Innkeeper Gareth", "Caravan guard survivor", "Local ranger"],
            secrets="The blue flames are caused by a rogue fire elemental bound to a cursed artifact. "
                   "The innkeeper's brother was the first to disappear and secretly joined the bandits. "
                   "The 'survivor' is actually the bandit leader's spy, feeding false information."
        )

        assert seed.seed_type == StorySeedType.MYSTERY
        assert len(seed.secrets) >= 50
        assert len(seed.key_npcs) >= 2
        # Test timestamp conversion
        dt = seed.get_base_datetime()
        assert dt.year == 1347
        assert dt.month == 9
        assert dt.hour == 16
        assert dt.second == 0  # Seconds always 0

    def test_story_timestamp_year_bounds(self):
        """Year must fit within Python datetime bounds to avoid runtime errors."""
        with pytest.raises(ValidationError):
            StoryTimestamp(year=10000, month=1, day=1, hour=0, minute=0)

    def test_story_timestamp_year_zero(self):
        """Year 0 should fail (ge=1 constraint)."""
        with pytest.raises(ValidationError):
            StoryTimestamp(year=0, month=1, day=1, hour=0, minute=0)

    def test_story_timestamp_feb_29_leap_year(self):
        """February 29 on a leap year should pass."""
        ts = StoryTimestamp(year=2024, month=2, day=29, hour=12, minute=0)
        assert ts.day == 29
        dt = ts.to_datetime()
        assert dt.month == 2
        assert dt.day == 29

    def test_story_timestamp_feb_29_non_leap_year(self):
        """February 29 on a non-leap year should fail."""
        with pytest.raises(ValidationError):
            StoryTimestamp(year=2023, month=2, day=29, hour=12, minute=0)

    def test_place_profile_creation(self):
        """Test creating a valid PlaceProfile."""
        place = PlaceProfile(
            name="The Last Light Inn",
            place_type="fixed_location",
            summary="A sturdy stone inn at the edge of civilization, serving as the final bastion "
                   "of safety before the treacherous mountain passes.",
            history="Built fifty years ago by a retired soldier who wanted a quiet life",
            current_status="Busy with travelers fleeing the troubles to the north",
            secrets="A hidden cellar contains evidence of smuggling operations",
            inhabitants=["Innkeeper Gareth", "Serving staff", "Regular patrons"],
            latitude=45.5231,
            longitude=-122.6765,
            extra_data=PlaceExtraData(
                atmosphere="Tense and watchful, with an undercurrent of fear",
                nearby_landmarks=["Old Watch Tower", "Merchant's Rest Cemetery"],
                resources=["Food stores", "Basic weapons", "Healing herbs"],
                dangers=["Occasional bandit raids", "Wild beast attacks"],
                ruler="Innkeeper Gareth",
                factions=["Merchant's Guild", "Local militia"],
                culture="Frontier hospitality mixed with survival pragmatism",
                economy="Trade waystation and supply depot",
                rumors=["Strange lights in the mountains", "Old magic awakening"],
            ),
        )

        assert place.name == "The Last Light Inn"
        assert place.extra_data is not None
        assert len(place.extra_data.rumors) == 2

    def test_zone_definition_creation(self):
        """Test creating a valid ZoneDefinition."""
        zone = ZoneDefinition(
            name="Westmarch Frontier",
            summary="A lawless frontier region between civilization and the wild mountains"
        )

        assert zone.name == "Westmarch Frontier"
        assert "frontier" in zone.summary

    def test_layer_definition_creation(self):
        """Test creating a valid LayerDefinition."""
        layer = LayerDefinition(
            name="Aethermoor",
            type=LayerType.PLANET,
            description="A mirror-Earth world where magic flows through ley lines"
        )

        assert layer.name == "Aethermoor"
        assert layer.type == LayerType.PLANET

    def test_transition_data_validation(self):
        """Test TransitionData validation."""
        # Create minimal valid components
        setting = SettingCard(
            genre=Genre.FANTASY,
            world_name="Test World",
            time_period="Test Period",
            tech_level=TechLevel.MEDIEVAL,
            political_structure="Test political structure",
            major_conflict="Test major conflict",
            themes=["test"],
            cultural_notes="Test cultural notes",
            diegetic_artifact="A test diegetic artifact describing the world",
        )

        character = CharacterSheet(
            name="Test Character",
            summary="A test character for validation testing purposes",
            appearance="Test appearance with sufficient detail for validation",
            background="Test backstory of sufficient length to meet the minimum requirements for validation",
            personality="Test personality that is complex enough for validation",
            trait_1=CharacterTrait(
                name="allies",
                description="Test ally who helps the character",
            ),
            trait_2=CharacterTrait(
                name="contacts",
                description="Test contact for information",
            ),
            trait_3=CharacterTrait(
                name="resources",
                description="Test resources the character possesses",
            ),
            # Wildcard trait
            wildcard_name="Test Trait",
            wildcard_description="A unique trait that sets this test character apart from others",
        )

        seed = StorySeed(
            seed_type=StorySeedType.DISCOVERY,
            title="Test Seed",
            situation="Test situation that is long enough to meet the minimum length requirement",
            hook="Test hook that draws the player in",
            immediate_goal="Test goal",
            stakes="Test stakes",
            tension_source="Test tension",
            base_timestamp=StoryTimestamp(year=2024, month=6, day=15, hour=9, minute=0),
            secrets="Test secrets: hidden plot information that the user never sees - NPC agendas and twists"
        )

        place = PlaceProfile(
            name="Test Place",
            place_type="fixed_location",
            summary="Test description that meets the minimum length requirement for validation",
            history="Test history of the place with sufficient detail",
            current_status="Test current status of the location",
            secrets="Test secrets hidden within this place",
            inhabitants=["Test inhabitant"],
            latitude=40.7128,
            longitude=-74.0060,
            extra_data=PlaceExtraData(
                atmosphere="Test atmosphere",
                culture="Test culture",
                rumors=["Test rumor"],
            ),
        )

        layer = LayerDefinition(
            name="Test World",
            type=LayerType.PLANET,
            description="A test world for validation"
        )

        zone = ZoneDefinition(
            name="Test Zone",
            summary="A test zone region with sufficient description for validation"
        )

        # Create transition data
        transition = TransitionData(
            setting=setting,
            character=character,
            seed=seed,
            layer=layer,
            zone=zone,
            location=place,
            thread_id="test_thread_123",
            base_timestamp=datetime.now(timezone.utc)
        )

        # Validate
        assert transition.validate_completeness() is True
        assert transition.ready_for_transition is True
        assert transition.validated is True


class TestDatabaseMapper:
    """Test the database mapping functions."""

    @pytest.fixture
    def mapper(self):
        """Create a mapper for testing (using save_02)."""
        return NewStoryDatabaseMapper(dbname="save_02")

    @pytest.fixture
    def sample_character(self):
        """Create a sample character for testing."""
        return CharacterSheet(
            name="Test Hero",
            summary="A battle-hardened mercenary seeking redemption for past deeds",
            appearance="Battle-scarred warrior with piercing blue eyes and a commanding presence",
            background="A veteran of many wars, seeking redemption for past deeds in service of a tyrant. "
                       "Now he fights for the innocent.",
            personality="Stoic and honorable, with a fierce protective instinct",
            trait_1=CharacterTrait(
                name="allies",
                description="A brotherhood of former soldiers who served with him",
            ),
            trait_2=CharacterTrait(
                name="reputation",
                description="Known as the 'Iron Shield' for never abandoning a charge",
            ),
            trait_3=CharacterTrait(
                name="obligations",
                description="Sworn to protect the village that took him in after the war",
            ),
            # Wildcard
            wildcard_name="Battle Scars",
            wildcard_description="His scars tell stories - some recognize them and either fear or respect him",
        )

    @pytest.fixture
    def sample_place(self):
        """Create a sample place for testing."""
        return PlaceProfile(
            name="Test Town",
            place_type="fixed_location",
            summary="A small frontier town struggling to survive in harsh lands and harsh times",
            history="Founded by refugees fleeing the last war, built on hope and determination",
            current_status="Preparing for winter with tension high due to recent bandit activity",
            secrets="The town elder knows the location of an ancient cache of weapons",
            inhabitants=["Mayor Thompson", "Blacksmith Greta", "Local militia"],
            latitude=42.3601,
            longitude=-71.0589,
            extra_data=PlaceExtraData(
                atmosphere="Determined but weary",
                culture="Hardy frontier folk",
                economy="Agriculture and trade",
                rumors=["Bandits in the hills"],
            ),
        )

    @pytest.fixture
    def sample_zone(self):
        """Create a sample zone for testing."""
        return ZoneDefinition(
            name="Borderlands",
            summary="A lawless frontier region where civilization meets the wilderness"
        )

    def test_character_mapping(self, mapper, sample_character):
        """Test mapping CharacterSheet to database format."""
        db_record = mapper.map_character_to_db(sample_character)

        # Check core fields
        assert db_record["name"] == "Test Hero"
        assert "Battle-scarred warrior" in db_record["appearance"]
        assert "veteran of many wars" in db_record["background"]

        # Check extra_data contains traits
        extra = json.loads(db_record["extra_data"])
        assert "allies" in extra
        assert "reputation" in extra
        assert "obligations" in extra
        # Wildcard is stored as a nested object
        assert "wildcard" in extra
        assert extra["wildcard"]["name"] == "Battle Scars"

    def test_place_mapping(self, mapper, sample_place):
        """Test mapping PlaceProfile to database format."""
        db_record = mapper.map_place_to_db(sample_place, zone_id=1)

        # Check core fields
        assert db_record["name"] == "Test Town"
        assert db_record["type"] == "fixed_location"
        assert db_record["zone"] == 1
        assert "frontier town" in db_record["summary"]

        # Check inhabitants array
        assert len(db_record["inhabitants"]) > 0

        # Check extra_data
        extra = json.loads(db_record["extra_data"])
        assert extra["atmosphere"] == "Determined but weary"
        assert extra["economy"] == "Agriculture and trade"

    def test_zone_mapping(self, mapper, sample_zone):
        """Test mapping ZoneDefinition to database format."""
        db_record = mapper.map_zone_to_db(sample_zone, layer_id=1)

        assert db_record["name"] == "Borderlands"
        assert "frontier" in db_record["summary"]
        assert len(db_record["summary"]) <= 500  # Database constraint


class TestStructuredOutputIntegration:
    """Test integration with structured output APIs."""

    @pytest.mark.integration
    @pytest.mark.live_llm
    @pytest.mark.parametrize("model", ["gpt-5.1", "claude-sonnet-4-5"])
    @pytest.mark.skipif(
        not RUN_LIVE_LLM,
        reason="Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.",
    )
    def test_setting_generation(self, model):
        """Test generating a setting with a live LLM."""
        generator = StoryComponentGenerator(model=model)

        setting = generator.generate_setting_card(
            "Create a dark fantasy world with steampunk elements"
        )

        assert isinstance(setting, SettingCard)
        assert setting.genre in [Genre.FANTASY, Genre.STEAMPUNK]
        assert setting.magic_exists is not None

    @pytest.mark.integration
    @pytest.mark.live_llm
    @pytest.mark.parametrize("model", ["gpt-5.1", "claude-sonnet-4-5"])
    @pytest.mark.skipif(
        not RUN_LIVE_LLM,
        reason="Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.",
    )
    def test_character_generation(self, model):
        """Test generating a character with a live LLM."""
        generator = StoryComponentGenerator(model=model)

        # Create a setting first
        setting = SettingCard(
            genre=Genre.FANTASY,
            world_name="Test World",
            time_period="Medieval",
            tech_level=TechLevel.MEDIEVAL,
            political_structure="Kingdoms",
            major_conflict="War",
            themes=["heroism"],
            cultural_notes="Knights and honor",
            diegetic_artifact="A world of knights and honor where heroism defines the age.",
        )

        character = generator.generate_character_sheet(
            setting,
            "Create a young mage seeking knowledge"
        )

        assert isinstance(character, CharacterSheet)
        assert character.name
        assert character.summary
        assert len({character.trait_1.name, character.trait_2.name, character.trait_3.name}) == 3
        assert character.wildcard_name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
