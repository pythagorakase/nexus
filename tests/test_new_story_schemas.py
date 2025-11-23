"""
Tests for new story structured output schemas and database mapping.

These tests verify that:
1. Our Pydantic schemas are valid
2. The OpenAI structured output works with our schemas
3. Database mapping correctly transforms schemas to table format
"""

import pytest
import json
from datetime import datetime, timezone
from typing import Dict, Any

from nexus.api.new_story_schemas import (
    SettingCard,
    CharacterSheet,
    StorySeed,
    LayerDefinition,
    LayerType,
    ZoneDefinition,
    PlaceProfile,
    SpecificLocation,
    TransitionData,
    Genre,
    TechLevel,
    CharacterBackground,
    StorySeedType,
    PlaceCategory,
    ZoneType,
)
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.api.new_story_generator import StoryComponentGenerator


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
            geographic_scope="regional"
        )

        assert setting.world_name == "Aethermoor"
        assert setting.genre == Genre.FANTASY
        assert setting.magic_exists is True
        assert len(setting.themes) == 3

        # Test JSON serialization
        json_data = setting.model_dump_json()
        assert "Aethermoor" in json_data

    def test_character_sheet_creation(self):
        """Test creating a valid CharacterSheet."""
        character = CharacterSheet(
            name="Lyra Shadowheart",
            age=27,
            gender="female",
            species="half-elf",
            background=CharacterBackground.SCHOLAR,
            occupation="Arcane Investigator",
            faction="Order of the Silver Eye",
            height="5 feet 8 inches",
            build="athletic",
            appearance="Tall half-elf with silver hair and violet eyes, bearing arcane tattoos",
            distinguishing_features=["Glowing tattoos", "Heterochromia"],
            personality="Cautious and analytical, with a dry sense of humor",
            motivations=["Uncover the truth about her parents", "Master forbidden magic"],
            fears=["Losing control of her power", "Being abandoned"],
            skills=["Arcane investigation", "Ancient languages", "Swordplay", "Alchemy"],
            weaknesses=["Overconfident", "Haunted by visions"],
            special_abilities=["Shadow manipulation", "Detect magic"],
            backstory="Orphaned at a young age when her parents vanished during a magical experiment. "
                     "Raised by the Order, she now investigates arcane crimes while searching for answers.",
            family="Parents missing, presumed dead",
            possessions=["Enchanted sword", "Spellbook", "Investigation kit"],
            wealth_level="modest",
            allies=["Master Aldric"],
            enemies=["The Crimson Hand cult"],
            growth_areas=["Learning to trust others", "Accepting her heritage"]
        )

        assert character.name == "Lyra Shadowheart"
        assert character.age == 27
        assert len(character.skills) == 4
        assert character.wealth_level == "modest"

    def test_story_seed_creation(self):
        """Test creating a valid StorySeed."""
        seed = StorySeed(
            seed_type=StorySeedType.MYSTERY,
            title="The Vanishing Merchants",
            situation="Three merchant caravans have disappeared on the road to Westmarch in the past moon. "
                     "You've been hired to investigate the latest disappearance.",
            hook="The merchants were carrying rare magical artifacts that could be dangerous if misused",
            immediate_goal="Find clues at the last known campsite",
            stakes="More disappearances could cripple trade and starve the region",
            tension_source="Time pressure - another caravan departs tomorrow",
            starting_location="The Last Light Inn, final stop before the dangerous road",
            time_of_day="Late afternoon",
            weather="Gathering storm clouds",
            key_npcs=["Innkeeper Gareth", "Caravan guard survivor"],
            initial_mystery="Strange blue flames were seen the night of each disappearance",
            immediate_choices=["Investigate the campsite", "Question the survivor",
                              "Research blue flame phenomena", "Warn tomorrow's caravan"],
            potential_allies=["Local ranger", "Traveling wizard"],
            potential_obstacles=["Hostile wilderness", "Uncooperative witnesses", "Magical interference"]
        )

        assert seed.seed_type == StorySeedType.MYSTERY
        assert len(seed.immediate_choices) == 4
        assert seed.initial_mystery is not None

    def test_place_profile_creation(self):
        """Test creating a valid PlaceProfile."""
        place = PlaceProfile(
            name="The Last Light Inn",
            category=PlaceCategory.BUILDING,
            description="A sturdy stone inn at the edge of civilization, serving as the final bastion "
                       "of safety before the treacherous mountain passes.",
            atmosphere="Tense and watchful, with an undercurrent of fear",
            size="medium",
            population=30,
            region="Westmarch Frontier",
            coordinates=(45.5231, -122.6765),  # Example coordinates (Portland, OR area)
            nearby_landmarks=["Old Watch Tower", "Merchant's Rest Cemetery"],
            notable_features=["Reinforced walls", "Hidden cellar", "Crow's nest lookout"],
            resources=["Food stores", "Basic weapons", "Healing herbs"],
            dangers=["Occasional bandit raids", "Wild beast attacks"],
            ruler="Innkeeper Gareth",
            factions=["Merchant's Guild", "Local militia"],
            culture="Frontier hospitality mixed with survival pragmatism",
            economy="Trade waystation and supply depot",
            trade_goods=["Provisions", "Mountain gear", "Local ale"],
            current_events=["Merchant disappearances", "Increased guard patrols"],
            rumors=["Strange lights in the mountains", "Old magic awakening"]
        )

        assert place.name == "The Last Light Inn"
        assert place.population == 30
        assert len(place.notable_features) == 3

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
            political_structure="Test",
            major_conflict="Test",
            themes=["test"],
            cultural_notes="Test"
        )

        character = CharacterSheet(
            name="Test Character",
            age=25,
            gender="other",
            background=CharacterBackground.COMMONER,
            occupation="Test",
            height="Average",
            build="Average",
            appearance="Test appearance with sufficient detail",
            personality="Test personality that is complex enough",
            motivations=["Test"],
            fears=["Test"],
            skills=["Test skill"],
            weaknesses=["Test"],
            backstory="Test backstory of sufficient length to meet requirements",
            possessions=["Test item"],
            growth_areas=["Test"]
        )

        seed = StorySeed(
            seed_type=StorySeedType.DISCOVERY,
            title="Test Seed",
            situation="Test situation that is long enough to meet the minimum length requirement",
            hook="Test hook that draws the player in",
            immediate_goal="Test goal",
            stakes="Test stakes",
            tension_source="Test tension",
            starting_location="Test location",
            time_of_day="Morning",
            immediate_choices=["Choice 1", "Choice 2"],
            potential_obstacles=["Test obstacle"]
        )

        place = PlaceProfile(
            name="Test Place",
            category=PlaceCategory.SETTLEMENT,
            description="Test description that meets the minimum length requirement for validation",
            atmosphere="Test atmosphere",
            region="Test region",
            coordinates=(40.7128, -74.0060),  # NYC coordinates for testing
            notable_features=["Test feature"],
            culture="Test culture"
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
            age=30,
            gender="male",
            species="human",
            background=CharacterBackground.SOLDIER,
            occupation="Mercenary",
            height="6 feet",
            build="muscular",
            appearance="Battle-scarred warrior with piercing blue eyes",
            personality="Stoic and honorable",
            motivations=["Protect the innocent"],
            fears=["Failing those who depend on him"],
            skills=["Swordsmanship", "Tactics", "Leadership"],
            weaknesses=["Too trusting"],
            backstory="A veteran of many wars, seeking redemption for past deeds in service of a tyrant",
            possessions=["Sword", "Armor", "War medallion"],
            growth_areas=["Learning to trust again"]
        )

    @pytest.fixture
    def sample_place(self):
        """Create a sample place for testing."""
        return PlaceProfile(
            name="Test Town",
            category=PlaceCategory.SETTLEMENT,
            description="A small frontier town struggling to survive in harsh lands",
            atmosphere="Determined but weary",
            size="small",
            population=500,
            region="Borderlands",
            notable_features=["Wooden palisade", "Market square"],
            culture="Hardy frontier folk",
            economy="Agriculture and trade",
            trade_goods=["Grain", "Furs"],
            current_events=["Preparing for winter"],
            rumors=["Bandits in the hills"]
        )

    @pytest.fixture
    def sample_zone(self):
        """Create a sample zone for testing."""
        return ZoneDefinition(
            name="Town Square",
            zone_type=ZoneType.PUBLIC,
            parent_place="Test Town",
            description="The heart of the town where people gather",
            purpose="Commerce and social gathering",
            layout="Open square with market stalls",
            sights="Market stalls, town well, bulletin board",
            sounds="Merchant calls, conversations",
            entrances=["Main street", "Side alleys"],
            objects=["Market stalls", "Well", "Bulletin board"],
            typical_activities=["Trading", "Socializing"]
        )

    def test_character_mapping(self, mapper, sample_character):
        """Test mapping CharacterSheet to database format."""
        db_record = mapper.map_character_to_db(sample_character)

        # Check core fields
        assert db_record["name"] == "Test Hero"
        assert "Battle-scarred warrior" in db_record["appearance"]
        assert "veteran of many wars" in db_record["background"]

        # Check extra_data
        extra = db_record["extra_data"]
        assert extra["age"] == 30
        assert extra["gender"] == "male"
        assert len(extra["skills"]) == 3
        assert extra["wealth_level"] == "modest"

    def test_place_mapping(self, mapper, sample_place):
        """Test mapping PlaceProfile to database format."""
        db_record = mapper.map_place_to_db(sample_place, zone_id=1)

        # Check core fields
        assert db_record["name"] == "Test Town"
        assert db_record["type"] == "fixed_location"  # Mapped from settlement
        assert db_record["zone"] == 1
        assert "frontier town" in db_record["summary"]

        # Check inhabitants array
        assert any("Population: 500" in i for i in db_record["inhabitants"])

        # Check extra_data
        extra = db_record["extra_data"]
        assert extra["category"] == "settlement"
        assert extra["size"] == "small"

    def test_zone_mapping(self, mapper, sample_zone):
        """Test mapping ZoneDefinition to database format."""
        db_record = mapper.map_zone_to_db(sample_zone)

        assert db_record["name"] == "Town Square"
        assert "heart of the town" in db_record["summary"]
        assert len(db_record["summary"]) <= 500  # Database constraint


class TestStructuredOutputIntegration:
    """Test integration with OpenAI structured output API."""

    @pytest.mark.integration
    def test_setting_generation(self):
        """Test generating a setting with OpenAI API."""
        generator = StoryComponentGenerator(model="gpt-4.1", use_resilient=True)

        setting = generator.generate_setting_card(
            "Create a dark fantasy world with steampunk elements"
        )

        assert isinstance(setting, SettingCard)
        assert setting.genre in [Genre.FANTASY, Genre.STEAMPUNK]
        assert setting.magic_exists is not None

    @pytest.mark.integration
    def test_character_generation(self):
        """Test generating a character with OpenAI API."""
        generator = StoryComponentGenerator(model="gpt-4.1", use_resilient=True)

        # Create a setting first
        setting = SettingCard(
            genre=Genre.FANTASY,
            world_name="Test World",
            time_period="Medieval",
            tech_level=TechLevel.MEDIEVAL,
            political_structure="Kingdoms",
            major_conflict="War",
            themes=["heroism"],
            cultural_notes="Knights and honor"
        )

        character = generator.generate_character_sheet(
            setting,
            "Create a young mage seeking knowledge"
        )

        assert isinstance(character, CharacterSheet)
        assert character.name
        assert character.age > 0
        assert len(character.skills) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])