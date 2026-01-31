#!/usr/bin/env python3
"""
Live test for Set Designer (Phase 2) against real LLMs.

Tests the translation of location_sketch into structured LayerDefinition,
ZoneDefinition, and PlaceProfile with lat/lon coordinates.

Usage:
    python tests/live_set_designer_test.py
"""

import asyncio
import logging
import sys
from typing import Any, Dict

# Configure logging BEFORE imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("live_set_designer_test")

# Reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

from nexus.api.new_story_generator import generate_set_design
from nexus.api.new_story_schemas import (
    SettingCard,
    StorySeed,
    StorySeedType,
    StoryTimestamp,
    Genre,
    TechLevel,
)


# Test setting (cyberpunk Neon Palimpsest)
TEST_SETTING = SettingCard(
    genre=Genre.CYBERPUNK,
    secondary_genres=[Genre.NOIR],
    world_name="Neon Palimpsest",
    time_period="Late 21st century",
    tech_level=TechLevel.NEAR_FUTURE,
    magic_exists=False,
    political_structure="Corporate syndicates under hollowed-out international council",
    major_conflict="War between surveillance states and ghost networks fighting over identity data",
    tone="dark",
    themes=["memory and identity", "surveillance vs secrecy", "corporate feudalism"],
    cultural_notes="Multiple overlapping identities, reputation scores matter more than currency",
    geographic_scope="continental",
    diegetic_artifact="[Orientation packet for Neon Palimpsest provisional citizens]",
)

# Test seed
TEST_SEED = StorySeed(
    seed_type=StorySeedType.IN_MEDIAS_RES,
    title="Ghost Transit",
    situation="Kade sprints along a flickering maglev maintenance catwalk, corporate drones closing in behind.",
    hook="A stolen data core that may contain Kade's erased memories—or a trap.",
    immediate_goal="Escape the pursuit and find somewhere safe to examine the data core.",
    stakes="If caught, Kade loses any chance of recovering their past.",
    tension_source="Corporate drones tracking from above, unknown allies signaling from below.",
    base_timestamp=StoryTimestamp(year=2087, month=11, day=3, hour=0, minute=15),
    weather="Hard sideways rain, visibility near zero",
    key_npcs=["Pursuing corporate security team", "Mysterious figure signaling from below"],
    secrets="The data core is bait planted by a Ghost faction testing if Kade can be reactivated as an asset.",
)

# Location sketches to test (from our previous live test + a fantasy one for contrast)
TEST_SKETCHES = [
    {
        "name": "Cyberpunk Hong Kong/Yokohama",
        "sketch": """The story opens on the Vertigo Trussway, an elevated maglev maintenance spine
that threads between decaying transit towers over Neon Palimpsest's eastern industrial belt—think
a denser, more vertical, rain-battered fusion of Hong Kong's mid-levels and the port districts of
Yokohama. It is well past midnight, and a hard, sideways rain turns every surface slick and reflective.
The Trussway itself is a narrow lattice of rusting steel and composite, patched with mismatched plates
scavenged from older infrastructure. Below, through gaps in the grating, the glow of street-level neon
bleeds upward in smeared ribbons. The air smells of ozone, rust, and the faint chemical tang of
coolant from the maglev lines.""",
    },
    {
        "name": "Cyberpunk Kowloon/Manchester",
        "sketch": """The Undercroft: a multi-level subterranean district carved into the bedrock beneath
the city's gleaming corporate towers, think the layered density of Kowloon Walled City crossed with
the industrial grit of Manchester's canal districts. Originally maintenance tunnels and transit
infrastructure, it's been colonized by squatters, gray-market traders, and those who need to stay
off the grid. Narrow catwalks span chasms where old subway lines still run; neon signs in six languages
advertise memory clinics, data brokers, and unlicensed body mods. The walls sweat condensation,
the air thick with cooking smoke, solder fumes, and the hum of a thousand jury-rigged power taps.""",
    },
    {
        "name": "Cyberpunk Rhine-Ruhr",
        "sketch": """A maintenance-warped tram car grinding through the deepest layer of the Roots beneath
the Rhine-Ruhr arcology belt, like the industrial tunnels under Duisburg or Essen but extended into
a vast underground network. Half-passenger transport, half smuggler's corridor. The tram's hull is
scarred composite sweating condensation, emergency lighting flickering amber. Outside the fogged windows,
other tunnel branches flash past—some lit, some dark, some showing Ghost Network tags in UV-reactive paint.
The air tastes of rust, recycled coolant, and the ozone snap of failing electronics.""",
    },
]

# Models to test (testing defaults per CLAUDE.md)
TEST_MODELS = ["gpt-5.1", "claude-sonnet-4-5"]


async def test_set_designer(model: str, sketch_info: Dict[str, str]) -> Dict[str, Any]:
    """Test set designer with a single model and sketch."""
    sketch_name = sketch_info["name"]
    sketch = sketch_info["sketch"]

    logger.info(f"\n--- Testing {model} with '{sketch_name}' ---")

    result = {
        "model": model,
        "sketch": sketch_name,
        "success": False,
        "error": None,
        "layer": None,
        "zone": None,
        "place": None,
        "coordinates": None,
    }

    try:
        layer, zone, place = await generate_set_design(
            location_sketch=sketch,
            setting=TEST_SETTING,
            seed=TEST_SEED,
            model=model,
        )

        result["success"] = True
        result["layer"] = {"name": layer.name, "type": layer.type.value, "description": layer.description[:100]}
        result["zone"] = {"name": zone.name, "summary": zone.summary[:100]}
        result["place"] = {
            "name": place.name,
            "type": place.place_type,
            "summary": place.summary[:150],
            "has_secrets": bool(place.secrets),
            "has_extra_data": place.extra_data is not None,
        }
        result["coordinates"] = {"lat": place.latitude, "lon": place.longitude}

        logger.info(f"  Layer: {layer.name} ({layer.type.value})")
        logger.info(f"  Zone: {zone.name}")
        logger.info(f"  Place: {place.name} ({place.place_type})")
        logger.info(f"  Coordinates: ({place.latitude:.4f}, {place.longitude:.4f})")

        # Validate coordinates make sense for the Earth analog
        if "Hong Kong" in sketch or "Yokohama" in sketch:
            # Should be East Asia region (lat 20-40, lon 100-145)
            if not (15 < place.latitude < 45 and 100 < place.longitude < 150):
                logger.warning(f"  ⚠ Coordinates don't match Hong Kong/Yokohama region!")
        elif "Kowloon" in sketch or "Manchester" in sketch:
            # Could be either HK or UK depending on interpretation
            pass
        elif "Rhine" in sketch or "Duisburg" in sketch or "Essen" in sketch:
            # Should be Germany region (lat 50-52, lon 6-8)
            if not (48 < place.latitude < 54 and 4 < place.longitude < 12):
                logger.warning(f"  ⚠ Coordinates don't match Rhine-Ruhr region!")

        logger.info(f"  ✓ PASS")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"  ✗ FAIL: {e}")

    return result


async def main():
    logger.info("=" * 70)
    logger.info("LIVE SET DESIGNER TEST")
    logger.info("Testing location_sketch → structured location data translation")
    logger.info("=" * 70)

    results = []

    for model in TEST_MODELS:
        logger.info(f"\n{'='*70}")
        logger.info(f"MODEL: {model}")
        logger.info(f"{'='*70}")

        for sketch_info in TEST_SKETCHES:
            result = await test_set_designer(model, sketch_info)
            results.append(result)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)

    # Group by model
    for model in TEST_MODELS:
        model_results = [r for r in results if r["model"] == model]
        passed = sum(1 for r in model_results if r["success"])
        logger.info(f"\n{model}: {passed}/{len(model_results)} passed")

        for r in model_results:
            status = "✓" if r["success"] else "✗"
            if r["success"]:
                coords = r["coordinates"]
                logger.info(f"  {status} {r['sketch']}: {r['place']['name']} @ ({coords['lat']:.2f}, {coords['lon']:.2f})")
            else:
                logger.info(f"  {status} {r['sketch']}: {r['error'][:50]}...")

    total_passed = sum(1 for r in results if r["success"])
    logger.info(f"\nTotal: {total_passed}/{len(results)} passed")

    return results


if __name__ == "__main__":
    asyncio.run(main())
