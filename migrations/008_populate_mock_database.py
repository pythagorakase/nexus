#!/usr/bin/env python3
"""
Populate the mock database with test data for TEST model.

This script loads data from temp/test_cache_wizard.json and inserts it into
the mock database using the normalized schema. It also creates post-transition
data (characters, places, etc.) and a bootstrap narrative chunk.

Usage:
    poetry run python migrations/008_populate_mock_database.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

MOCK_DB = "mock"
CACHE_FILE = Path(__file__).parent.parent / "temp" / "test_cache_wizard.json"


def load_wizard_cache() -> dict:
    """Load and parse the wizard test cache."""
    raw = json.loads(CACHE_FILE.read_text())

    # Parse double-encoded JSON fields
    parsed = {}
    for key, value in raw.items():
        if isinstance(value, str) and value.strip().startswith("{"):
            try:
                parsed[key] = json.loads(value)
            except json.JSONDecodeError:
                parsed[key] = value
        else:
            parsed[key] = value

    return parsed


def populate_wizard_cache(conn, cache: dict):
    """Populate assets.new_story_creator with wizard phase data."""
    setting = cache.get("setting_draft", {})
    character = cache.get("character_draft", {})
    seed = cache.get("selected_seed", {})
    layer = cache.get("layer_draft", {})
    zone = cache.get("zone_draft", {})
    location = cache.get("initial_location", {})

    # Extract character data
    concept = character.get("concept", {})
    trait_selection = character.get("trait_selection", {})
    wildcard = character.get("wildcard", {})
    selected_traits = trait_selection.get("selected_traits", [])

    with conn.cursor() as cur:
        # Clear existing data
        cur.execute("DELETE FROM assets.new_story_creator WHERE id = TRUE")
        cur.execute("DELETE FROM assets.suggested_traits")

        # Insert wizard cache row
        # Note: Array columns need explicit casting to enum types
        cur.execute("""
            INSERT INTO assets.new_story_creator (
                id, thread_id, target_slot,
                -- Setting phase
                setting_genre, setting_secondary_genres, setting_world_name,
                setting_time_period, setting_tech_level, setting_magic_exists,
                setting_magic_description, setting_political_structure,
                setting_major_conflict, setting_tone, setting_themes,
                setting_cultural_notes, setting_language_notes,
                setting_geographic_scope, setting_diegetic_artifact,
                -- Character phase
                character_name, character_archetype, character_background,
                character_appearance, character_trait1, character_trait2,
                character_trait3, wildcard_name, wildcard_description,
                -- Seed phase
                seed_type, seed_title, seed_situation, seed_hook,
                seed_immediate_goal, seed_stakes, seed_tension_source,
                seed_starting_location, seed_weather, seed_key_npcs,
                seed_initial_mystery, seed_potential_allies,
                seed_potential_obstacles, seed_secrets,
                -- Layer/Zone
                layer_name, layer_type, layer_description,
                zone_name, zone_summary, zone_boundary_description,
                zone_approximate_area,
                -- Location
                initial_location,
                -- Temporal
                base_timestamp
            ) VALUES (
                TRUE, %s, %s,
                -- Setting (with casts for enum arrays)
                %s::genre, %s::genre[], %s, %s, %s::tech_level, %s, %s, %s, %s, %s::tone, %s, %s, %s, %s::geographic_scope, %s,
                -- Character (with casts for trait enums)
                %s, %s, %s, %s, %s::trait, %s::trait, %s::trait, %s, %s,
                -- Seed (with cast for seed_type enum)
                %s::seed_type, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                -- Layer/Zone (with cast for layer_type)
                %s, %s::layer_type, %s, %s, %s, %s, %s,
                -- Location
                %s,
                -- Temporal
                %s
            )
        """, (
            cache.get("thread_id", "test_thread_mock"),
            cache.get("target_slot", 5),
            # Setting
            setting.get("genre"),
            setting.get("secondary_genres"),
            setting.get("world_name"),
            setting.get("time_period"),
            setting.get("tech_level"),
            setting.get("magic_exists", False),
            setting.get("magic_description"),
            setting.get("political_structure"),
            setting.get("major_conflict"),
            setting.get("tone"),
            setting.get("themes"),
            setting.get("cultural_notes"),
            setting.get("language_notes"),
            setting.get("geographic_scope"),
            setting.get("diegetic_artifact"),
            # Character
            concept.get("name"),
            concept.get("archetype"),
            concept.get("background"),
            concept.get("appearance"),
            selected_traits[0] if len(selected_traits) > 0 else None,
            selected_traits[1] if len(selected_traits) > 1 else None,
            selected_traits[2] if len(selected_traits) > 2 else None,
            wildcard.get("wildcard_name"),
            wildcard.get("wildcard_description"),
            # Seed
            seed.get("seed_type"),
            seed.get("title"),
            seed.get("situation"),
            seed.get("hook"),
            seed.get("immediate_goal"),
            seed.get("stakes"),
            seed.get("tension_source"),
            seed.get("starting_location"),
            seed.get("weather"),
            seed.get("key_npcs"),
            seed.get("initial_mystery"),
            seed.get("potential_allies"),
            seed.get("potential_obstacles"),
            seed.get("secrets"),
            # Layer/Zone
            layer.get("name"),
            layer.get("layer_type"),
            layer.get("description"),
            zone.get("name"),
            zone.get("summary"),
            zone.get("boundary_description"),
            zone.get("approximate_area"),
            # Location
            Json(location) if location else None,
            # Temporal
            cache.get("base_timestamp") or datetime.now(timezone.utc),
        ))

    print("✓ Populated assets.new_story_creator")


def populate_post_transition_data(conn, cache: dict):
    """Populate post-transition tables: characters, layers, zones, places, global_variables."""
    setting = cache.get("setting_draft", {})
    character = cache.get("character_draft", {})
    seed = cache.get("selected_seed", {})
    layer = cache.get("layer_draft", {})
    zone = cache.get("zone_draft", {})
    location = cache.get("initial_location", {})

    concept = character.get("concept", {})

    with conn.cursor() as cur:
        # Clear existing data (CASCADE handles FKs)
        cur.execute("TRUNCATE layers CASCADE")
        cur.execute("TRUNCATE characters CASCADE")

        # Insert layer (column is 'type' not 'layer_type')
        cur.execute("""
            INSERT INTO layers (id, name, type, description)
            VALUES (1, %s, %s::layer_type, %s)
        """, (
            layer.get("name", "Neon Palimpsest Earth"),
            layer.get("layer_type", "planet"),
            layer.get("description"),
        ))

        # Insert zone (FK column is 'layer' not 'layer_id')
        # Note: boundary_description and approximate_area not in base schema
        cur.execute("""
            INSERT INTO zones (id, name, summary, layer)
            VALUES (1, %s, %s, 1)
        """, (
            zone.get("name", "Rhine-Ruhr Arcology Belt"),
            zone.get("summary"),
        ))

        # Insert place (type is required, FK column is 'zone' not 'zone_id')
        # Tram car is a 'vehicle' type
        cur.execute("""
            INSERT INTO places (id, name, type, summary, zone, extra_data)
            VALUES (1, %s, 'vehicle'::place_type, %s, 1, %s)
        """, (
            location.get("name", "Spine-9 Rootline Tram 3B"),
            location.get("summary"),
            Json({
                "atmosphere": location.get("atmosphere"),
                "notable_features": location.get("notable_features", []),
                "boundary_description": zone.get("boundary_description"),
                "approximate_area": zone.get("approximate_area"),
            }),
        ))

        # Insert character
        cur.execute("""
            INSERT INTO characters (id, name, appearance, background, current_location, extra_data)
            VALUES (1, %s, %s, %s, 1, %s)
        """, (
            concept.get("name", "Kade Imani"),
            concept.get("appearance"),
            concept.get("background"),
            Json({
                "archetype": concept.get("archetype"),
                "wildcard_name": character.get("wildcard", {}).get("wildcard_name"),
                "wildcard_description": character.get("wildcard", {}).get("wildcard_description"),
            }),
        ))

        # Update global_variables
        cur.execute("DELETE FROM global_variables WHERE id = TRUE")
        cur.execute("""
            INSERT INTO global_variables (id, setting, user_character, base_timestamp)
            VALUES (TRUE, %s, 1, %s)
        """, (
            Json({
                "world_name": setting.get("world_name"),
                "genre": setting.get("genre"),
                "tone": setting.get("tone"),
                "themes": setting.get("themes"),
                "magic_exists": setting.get("magic_exists", False),
                "magic_description": setting.get("magic_description"),
                "story_seed": seed,
                "content": setting.get("diegetic_artifact"),
                "title": f"Welcome to {setting.get('world_name', 'the World')}",
            }),
            cache.get("base_timestamp") or datetime.now(timezone.utc),
        ))

    print("✓ Populated layers, zones, places, characters, global_variables")


def populate_bootstrap_narrative(conn):
    """Populate incubator with the bootstrap narrative chunk."""

    narrative_text = """The tram shudders as it descends into the Roots, emergency lights flickering amber through condensation-streaked windows. You're aware of the satchel before you're aware of anything else—its weight against your wrist, the cold bite of the handcuff's metal edge where it meets skin. The notification in your retinal HUD pulses insistently: DELIVERY CONFIRMED. PAYMENT PENDING. INCIDENT UNDER REVIEW.

Three months. Three months since you woke in a capsule hotel with no memory of how you got there, a warning scrawled on the mirror in your own handwriting: TRUST NOTHING THEY SHOW YOU. Since then you've been Kade Imani, freelance courier, carefully anonymous, deliberately forgettable. You've built a life from careful routines and strategic silences.

And now this. A job you don't remember taking. A satchel you don't remember receiving. And somewhere in the Syndicate's vast ledger systems, your name flagged for review.

The tram car is sparsely populated at this hour—maintenance workers heading home, a few Roots dwellers with the hollow look of those who've lived too long below the Glow. Two cars back, you caught a glimpse of a figure in a gray coat, AR rig glinting cheap and obvious. Syndicate auditor, almost certainly. They're not even trying to be subtle.

Closer, slumped in the seat across the aisle, someone in a medic's scrubs is pretending to sleep. Their AR halo fuzzes with intentional static—a Ghost tell, or a very good imitation of one. Their breathing is too controlled for genuine sleep.

The tram's ancient AI conductor announces the next stop in a voice that skips and glitches, fragments of old advertisements bleeding through: "Next—pleasure—Spine Junction Nine—optimal pricing—please mind the gap."

Rain hammers against the hull above. Somewhere in the distance, the city's heartbeat of data transactions and identity verifications pulses on, indifferent to your small crisis. But you feel the weight of the satchel, and you know: whatever's inside, it's already changed everything."""

    choices = [
        "Examine the satchel more closely, testing the seals for signs of tampering",
        "Study the auditor two cars back—their posture, their equipment, their probable threat level",
        "Make contact with the sleeping medic, a calculated risk to gauge their intentions"
    ]

    import uuid

    with conn.cursor() as cur:
        # Clear incubator (singleton table with id=true)
        cur.execute("DELETE FROM incubator WHERE id = TRUE")

        # Insert bootstrap narrative
        # Note: incubator uses singleton pattern (id=true)
        cur.execute("""
            INSERT INTO incubator (
                id, chunk_id, parent_chunk_id,
                user_text, storyteller_text, choice_object,
                metadata_updates, entity_updates, reference_updates,
                session_id, llm_response_id, status
            ) VALUES (
                TRUE, 1, 0,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, 'provisional'
            )
        """, (
            "Begin the story.",
            narrative_text,
            Json({
                "presented": choices,
                "selected": None,
            }),
            Json({
                "chronology": {
                    "episode_transition": "new_episode",  # Valid: continue, new_episode, new_season
                    "time_delta_minutes": 0,
                    "time_delta_description": "Story begins",
                },
                "world_layer": "primary",
            }),
            Json([]),  # entity_updates is an array
            Json({
                "characters": [{"character_id": 1, "reference_type": "present"}],
                "places": [{"place_id": 1, "reference_type": "setting"}],
                "factions": [],
            }),
            str(uuid.uuid4()),  # Generate real UUID
            "mock_bootstrap_response",
        ))

    print("✓ Populated incubator with bootstrap narrative")


def populate_save_slot(conn):
    """Ensure save_slots has a mock slot entry."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM assets.save_slots WHERE slot_number = 0")
        cur.execute("""
            INSERT INTO assets.save_slots (slot_number, model, created_at)
            VALUES (0, 'TEST', NOW())
            ON CONFLICT (slot_number) DO UPDATE SET model = 'TEST'
        """)
    print("✓ Configured mock save slot (slot 0)")


def main():
    print(f"Loading wizard cache from {CACHE_FILE}...")
    cache = load_wizard_cache()

    print(f"Connecting to {MOCK_DB} database...")
    conn = psycopg2.connect(host="localhost", database=MOCK_DB, user="pythagor")

    try:
        populate_wizard_cache(conn, cache)
        populate_post_transition_data(conn, cache)
        populate_bootstrap_narrative(conn)
        populate_save_slot(conn)

        conn.commit()
        print("\n✅ Mock database populated successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
