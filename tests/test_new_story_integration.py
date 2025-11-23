#!/usr/bin/env python3
"""
Integration tests for new story generation with live OpenAI API.

This test validates the complete flow of generating story components
using structured outputs with the OpenAI API.
"""

import os
import json
import logging
from datetime import datetime, timezone

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import our modules
from nexus.api.new_story_generator import StoryComponentGenerator, InteractiveSetupFlow
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.api.new_story_schemas import Genre, TechLevel


def test_complete_story_generation_flow():
    """Test the complete story generation flow with live API calls."""

    print("\n" + "="*60)
    print("TESTING NEW STORY GENERATION WITH LIVE OPENAI API")
    print("="*60 + "\n")

    # Initialize the generator with resilient client
    print("1. Initializing story generator...")
    generator = StoryComponentGenerator(model="gpt-4.1", use_resilient=True)
    flow = InteractiveSetupFlow(generator)

    # Phase 1: Generate Setting
    print("\n2. PHASE 1: Generating setting...")
    setting_prompt = """
    I want a dark fantasy setting with gothic horror elements.
    The world should feel like medieval Eastern Europe with supernatural threats.
    Magic exists but is dangerous and corrupting.
    """

    try:
        setting = flow.phase1_generate_setting(setting_prompt)
        print(f"   ✓ Generated setting: {setting.world_name}")
        print(f"     - Genre: {setting.genre} with {', '.join([g.value for g in setting.secondary_genres])}")
        print(f"     - Time Period: {setting.time_period}")
        print(f"     - Tech Level: {setting.tech_level}")
        print(f"     - Major Conflict: {setting.major_conflict}")
        print(f"     - Themes: {', '.join(setting.themes)}")
    except Exception as e:
        print(f"   ✗ Failed to generate setting: {e}")
        return False

    # Phase 2: Generate Character
    print("\n3. PHASE 2: Generating character...")
    character_prompt = """
    Create a young witch hunter who secretly has magical abilities they must hide.
    They're conflicted between their duty and their nature.
    Give them a tragic backstory involving the loss of family.
    """

    try:
        character = flow.phase2_generate_character(character_prompt)
        print(f"   ✓ Generated character: {character.name}")
        print(f"     - Age: {character.age}, {character.gender} {character.species}")
        print(f"     - Background: {character.background}, {character.occupation}")
        print(f"     - Primary Motivation: {character.motivations[0]}")
        print(f"     - Primary Fear: {character.fears[0]}")
        print(f"     - Skills: {', '.join(character.skills[:3])}...")
    except Exception as e:
        print(f"   ✗ Failed to generate character: {e}")
        return False

    # Phase 3: Generate Story Seeds
    print("\n4. PHASE 3: Generating story seeds...")

    try:
        seeds = flow.phase3_generate_seeds()
        print(f"   ✓ Generated {len(seeds)} story seeds:")
        for i, seed in enumerate(seeds):
            print(f"     {i+1}. {seed.title} ({seed.seed_type})")
            print(f"        - {seed.hook[:80]}...")
    except Exception as e:
        print(f"   ✗ Failed to generate seeds: {e}")
        return False

    # Choose first seed
    print("\n5. Selecting first story seed...")
    chosen_seed = flow.phase3_choose_seed(0)
    print(f"   ✓ Selected: {chosen_seed.title}")
    print(f"     - Situation: {chosen_seed.situation[:100]}...")
    print(f"     - Immediate Goal: {chosen_seed.immediate_goal}")
    print(f"     - Stakes: {chosen_seed.stakes}")

    # Phase 4: Generate Location Hierarchy
    print("\n6. PHASE 4: Generating location hierarchy...")

    try:
        layer, zone, place = flow.phase4_generate_location()
        print(f"   ✓ Generated location hierarchy:")
        print(f"     - Layer: {layer.name} ({layer.type})")
        print(f"       {layer.description}")
        print(f"     - Zone: {zone.name}")
        print(f"       {zone.summary}")
        print(f"     - Place: {place.name} ({place.category})")
        print(f"       Coordinates: {place.coordinates}")
        print(f"       {place.description[:100]}...")
        print(f"       Population: {place.population or 'Unknown'}")
        print(f"       Notable Features: {', '.join(place.notable_features[:3]) if place.notable_features else 'None'}")
    except Exception as e:
        print(f"   ✗ Failed to generate location: {e}")
        return False

    # Validate coordinates
    print("\n7. Validating coordinates...")
    lat, lon = place.coordinates
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        print(f"   ✓ Valid coordinates: ({lat}, {lon})")

        # Determine rough Earth location
        if 45 <= lat <= 55 and 20 <= lon <= 40:
            earth_region = "Eastern Europe area"
        elif 35 <= lat <= 45 and -10 <= lon <= 10:
            earth_region = "Mediterranean area"
        elif 50 <= lat <= 60 and -10 <= lon <= 5:
            earth_region = "British Isles area"
        else:
            earth_region = "Valid Earth location"
        print(f"     Mapped to: {earth_region}")
    else:
        print(f"   ✗ Invalid coordinates: ({lat}, {lon})")
        return False

    # Test database mapping (without actual insertion)
    print("\n8. Testing database mapping...")
    mapper = NewStoryDatabaseMapper(dbname="save_02")

    try:
        # Test character mapping
        char_db = mapper.map_character_to_db(character)
        print(f"   ✓ Character maps to DB format")
        print(f"     - Core fields: name, appearance, background, personality")
        print(f"     - Extra data fields: {len(char_db['extra_data'])} attributes")

        # Test layer mapping
        layer_db = mapper.map_layer_to_db(layer)
        print(f"   ✓ Layer maps to DB format")

        # Test zone mapping (would need layer_id in real scenario)
        zone_db = mapper.map_zone_to_db(zone, layer_id=1)
        print(f"   ✓ Zone maps to DB format")

        # Test place mapping (would need zone_id in real scenario)
        place_db = mapper.map_place_to_db(place, zone_id=1)
        print(f"   ✓ Place maps to DB format")
        print(f"     - Type: {place_db['type']}")
        print(f"     - Inhabitants: {len(place_db['inhabitants'])} entries")

    except Exception as e:
        print(f"   ✗ Failed to map to database format: {e}")
        return False

    # Final validation
    print("\n9. Final validation...")
    transition = flow.finalize_transition(thread_id="test_thread_integration")

    if transition.validate_completeness():
        print("   ✓ All components valid and ready for transition!")
        print(f"     - Setup duration: {transition.setup_duration_minutes} minutes")
        print(f"     - Ready for narrative: {transition.ready_for_transition}")
    else:
        print("   ✗ Transition data incomplete")
        return False

    print("\n" + "="*60)
    print("INTEGRATION TEST COMPLETED SUCCESSFULLY!")
    print("="*60 + "\n")

    # Save test results for inspection
    test_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "setting": setting.model_dump(),
        "character": character.model_dump(),
        "seed": chosen_seed.model_dump(),
        "layer": layer.model_dump(),
        "zone": zone.model_dump(),
        "place": place.model_dump(),
        "coordinates": place.coordinates,
        "validation": {
            "coordinates_valid": -90 <= lat <= 90 and -180 <= lon <= 180,
            "transition_ready": transition.ready_for_transition,
            "all_fields_complete": transition.validated
        }
    }

    output_file = "/tmp/new_story_test_results.json"
    with open(output_file, "w") as f:
        json.dump(test_results, f, indent=2, default=str)
    print(f"\nTest results saved to: {output_file}")

    return True


if __name__ == "__main__":
    # The OpenAIProvider handles cached API keys automatically
    # No need to check environment variables

    # Run the test
    success = test_complete_story_generation_flow()

    if success:
        print("\n✅ All integration tests passed!")
        exit(0)
    else:
        print("\n❌ Integration tests failed")
        exit(1)