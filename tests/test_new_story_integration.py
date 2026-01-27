"""
Integration tests for new story generation with live LLM API calls.

These tests are optional and require NEXUS_RUN_LIVE_LLM=1.
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone

import pytest

from nexus.api.new_story_generator import StoryComponentGenerator, InteractiveSetupFlow
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper

RUN_LIVE_LLM = os.environ.get("NEXUS_RUN_LIVE_LLM") == "1"


@pytest.mark.integration
@pytest.mark.live_llm
@pytest.mark.parametrize("model", ["gpt-5.1", "claude-haiku-4-5"])
@pytest.mark.skipif(
    not RUN_LIVE_LLM,
    reason="Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.",
)
def test_complete_story_generation_flow(model: str):
    generator = StoryComponentGenerator(model=model)
    flow = InteractiveSetupFlow(generator)

    setting_prompt = (
        "I want a dark fantasy setting with gothic horror elements. "
        "The world should feel like medieval Eastern Europe with supernatural threats. "
        "Magic exists but is dangerous and corrupting."
    )

    setting = flow.phase1_generate_setting(setting_prompt)
    assert setting.world_name
    assert setting.genre
    assert setting.major_conflict
    assert setting.diegetic_artifact

    character_prompt = (
        "Create a young witch hunter who secretly has magical abilities they must hide. "
        "They're conflicted between their duty and their nature. "
        "Give them a tragic backstory involving the loss of family."
    )

    character = flow.phase2_generate_character(character_prompt)
    assert character.name
    assert character.summary
    assert character.background
    assert character.personality
    assert {character.trait_1.name, character.trait_2.name, character.trait_3.name}
    assert character.wildcard_name

    seeds = flow.phase3_generate_seeds()
    assert len(seeds) >= 2

    chosen_seed = flow.phase3_choose_seed(0)
    assert chosen_seed.title
    assert chosen_seed.situation

    layer, zone, place = flow.phase4_generate_location()
    assert layer.name
    assert zone.name
    assert place.name
    assert -90 <= place.latitude <= 90
    assert -180 <= place.longitude <= 180

    mapper = NewStoryDatabaseMapper(dbname="save_02")

    char_db = mapper.map_character_to_db(character)
    assert char_db["name"] == character.name

    layer_db = mapper.map_layer_to_db(layer)
    assert layer_db["name"] == layer.name

    zone_db = mapper.map_zone_to_db(zone, layer_id=1)
    assert zone_db["name"] == zone.name

    place_db = mapper.map_place_to_db(place, zone_id=1)
    assert place_db["name"] == place.name

    transition = flow.finalize_transition(thread_id="test_thread_integration")
    assert transition.validate_completeness()
    assert transition.ready_for_transition

    test_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "setting": setting.model_dump(),
        "character": character.model_dump(),
        "seed": chosen_seed.model_dump(),
        "layer": layer.model_dump(),
        "zone": zone.model_dump(),
        "place": place.model_dump(),
        "coordinates": [place.latitude, place.longitude],
        "validation": {
            "coordinates_valid": -90 <= place.latitude <= 90 and -180 <= place.longitude <= 180,
            "transition_ready": transition.ready_for_transition,
            "all_fields_complete": transition.validated,
        },
    }

    output_file = "/tmp/new_story_test_results.json"
    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(test_results, handle, indent=2, default=str)
