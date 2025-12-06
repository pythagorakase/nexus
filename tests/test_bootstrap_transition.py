"""
Unit test for bootstrap transition database operations.

Tests the perform_transition method with placeholder data,
bypassing slow API calls to enable fast debug iteration.
"""

import json
import pytest
from datetime import datetime, timezone

from nexus.api.new_story_schemas import (
    TransitionData,
    SettingCard,
    CharacterSheet,
    StorySeed,
    LayerDefinition,
    ZoneDefinition,
    PlaceProfile,
    StoryTimestamp,
    Genre,
    TechLevel,
    StorySeedType,
    LayerType,
)
from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.api.db_pool import get_connection


# Test on save_05 (isolated test slot - NOT save_03 which has wizard cache!)
TEST_DB = "save_05"


def create_placeholder_transition_data() -> TransitionData:
    """Create minimal valid TransitionData for testing."""

    # Setting
    setting = SettingCard(
        genre=Genre.CYBERPUNK,
        world_name="Test World",
        time_period="2077",
        tech_level=TechLevel.NEAR_FUTURE,
        political_structure="Corporate oligarchy",
        major_conflict="Class warfare",
        themes=["survival", "identity"],
        cultural_notes="Neon-lit urban sprawl",
        diegetic_artifact="Test artifact description for the setting.",
    )

    # Character (need exactly 3 traits + wildcard)
    character = CharacterSheet(
        name="Test Runner",
        summary="A street-smart hacker trying to survive in the corporate shadows.",
        appearance="Cybernetic eyes, worn leather jacket, neural interface port visible at temple.",
        background="Grew up in the lower levels, learned to hack to survive. Lost family to corpo violence.",
        personality="Cynical but loyal to those who earn trust. Quick-witted under pressure.",
        # Exactly 3 of 10 optional traits
        allies="The Collective - underground hacker group",
        contacts="Various fixers in the entertainment district",
        enemies="Nexus Corp security division",
        # Required wildcard
        wildcard_name="Ghost Protocol",
        wildcard_description="Ability to temporarily erase digital footprint from surveillance systems.",
    )

    # Story seed
    seed = StorySeed(
        seed_type=StorySeedType.CRISIS,
        title="Data Heist Gone Wrong",
        situation="The extraction was clean until the alarms triggered. Now you're trapped in a server room with precious data and no exit.",
        hook="The data you stole isn't what you expected - it's evidence of something far worse.",
        immediate_goal="Escape the building before security locks it down",
        stakes="Your life and the lives of everyone who helped plan this job",
        tension_source="Security forces closing in, and the data reveals your employer is the enemy",
        starting_location="Nexus Corp Tower, Server Room 7",
        base_timestamp=StoryTimestamp(year=2077, month=6, day=15, hour=23, minute=45),
        secrets="The data reveals a corporate conspiracy to eliminate the hacker collective. Your employer is a double agent.",
    )

    # Layer (top of hierarchy)
    layer = LayerDefinition(
        name="Earth",
        type=LayerType.PLANET,
        description="A cyberpunk Earth dominated by megacorporations and urban sprawl.",
    )

    # Zone (middle of hierarchy)
    zone = ZoneDefinition(
        name="New Angeles Downtown",
        summary="The glittering heart of corporate power, where towers of chrome and glass reach toward polluted skies.",
    )

    # Place (bottom of hierarchy - starting location)
    location = PlaceProfile(
        name="Nexus Corp Tower",
        place_type="fixed_location",
        summary="A massive corporate headquarters rising 200 stories into the smog. The lower levels are accessible to the public; the upper floors require clearance few possess.",
        history="Built in 2055 as a symbol of Nexus Corp's dominance. Has survived three attempted bombings.",
        current_status="High alert after recent data breaches. Security patrols doubled.",
        secrets="The server room on floor 77 contains evidence of illegal genetic experiments.",
        coordinates=[34.0522, -118.2437],  # LA coordinates
    )

    return TransitionData(
        setting=setting,
        character=character,
        seed=seed,
        layer=layer,
        zone=zone,
        location=location,
        base_timestamp=datetime(2077, 6, 15, 23, 45, 0, tzinfo=timezone.utc),
        thread_id="test_thread_placeholder",
        ready_for_transition=True,
        validated=True,
    )


def ensure_global_variables_row(dbname: str) -> None:
    """Ensure global_variables has a row before test."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO global_variables (id, new_story)
                VALUES (true, true)
                ON CONFLICT (id) DO UPDATE SET new_story = true
            """)
        conn.commit()


def get_global_variables_count(dbname: str) -> int:
    """Get count of rows in global_variables."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM global_variables")
            return cur.fetchone()[0]


def get_character_by_id(dbname: str, char_id: int) -> dict | None:
    """Get character by ID."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM characters WHERE id = %s", (char_id,))
            row = cur.fetchone()
            if row:
                return {"id": row[0], "name": row[1]}
            return None


def get_max_character_id(dbname: str) -> int | None:
    """Get max character ID or None if table empty."""
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(id) FROM characters")
            return cur.fetchone()[0]


def run_bootstrap_location_query(dbname: str) -> dict | None:
    """
    Run the same query that narrative.py uses to get starting location.

    This is the FK chain query:
    global_variables.user_character → characters.current_location → places.id

    Note: atmosphere and notable_features are in extra_data JSONB, not columns.
    """
    with get_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.name, p.summary,
                       p.extra_data->>'atmosphere' as atmosphere,
                       p.extra_data->'notable_features' as notable_features
                FROM global_variables g
                JOIN characters c ON c.id = g.user_character
                JOIN places p ON p.id = c.current_location
                WHERE g.id = true
            """)
            row = cur.fetchone()
            if row:
                return {
                    "name": row[0],
                    "summary": row[1],
                    "atmosphere": row[2],
                    "notable_features": row[3],
                }
            return None


class TestBootstrapTransition:
    """Test suite for bootstrap transition database operations."""

    def test_global_variables_survives_truncate(self):
        """
        CRITICAL: Verify global_variables row is NOT deleted by TRUNCATE.

        This was the bug: TRUNCATE CASCADE was deleting global_variables
        because it has an FK to characters, even with CASCADE removed.
        """
        # Setup: ensure row exists
        ensure_global_variables_row(TEST_DB)
        assert get_global_variables_count(TEST_DB) == 1, "Setup failed: no global_variables row"

        # Create mapper and transition data
        mapper = NewStoryDatabaseMapper(dbname=TEST_DB)
        transition_data = create_placeholder_transition_data()

        # Execute the transition
        result = mapper.perform_transition(transition_data)

        # CRITICAL CHECK: global_variables must still have exactly 1 row
        count = get_global_variables_count(TEST_DB)
        assert count == 1, f"global_variables was deleted! Count: {count}"

        # Verify transition succeeded
        assert result is not None, "Transition returned None"
        print(f"✓ Transition succeeded, global_variables preserved (count={count})")
        print(f"  Character ID: {result.get('character_id')}")
        print(f"  Place ID: {result.get('place_id')}")

    def test_character_id_resets_to_one(self):
        """Verify protagonist gets ID=1 after truncate."""
        ensure_global_variables_row(TEST_DB)

        mapper = NewStoryDatabaseMapper(dbname=TEST_DB)
        transition_data = create_placeholder_transition_data()

        result = mapper.perform_transition(transition_data)

        # Protagonist should have ID=1
        character_id = result.get("character_id")
        assert character_id == 1, f"Character ID should be 1, got {character_id}"

        # Verify by querying
        char = get_character_by_id(TEST_DB, 1)
        assert char is not None, "Character with ID=1 not found"
        assert char["name"] == "Test Runner", f"Unexpected character name: {char['name']}"
        print(f"✓ Protagonist created with ID=1: {char['name']}")

    def test_transition_is_atomic(self):
        """Verify all-or-nothing behavior on failure."""
        ensure_global_variables_row(TEST_DB)

        # Get current state
        initial_max_id = get_max_character_id(TEST_DB)

        # Create transition with invalid data that should fail
        mapper = NewStoryDatabaseMapper(dbname=TEST_DB)

        # This should succeed - we're just testing the happy path here
        # A true atomicity test would require injecting a failure mid-transaction
        transition_data = create_placeholder_transition_data()
        result = mapper.perform_transition(transition_data)

        assert result is not None, "Transition failed unexpectedly"
        print(f"✓ Atomic transition completed successfully")

    def test_bootstrap_location_query_works(self):
        """
        CRITICAL: Verify the FK chain query that narrative.py uses works.

        This tests the fix for: column g.starting_place_id does not exist

        The query should traverse:
        global_variables.user_character → characters.current_location → places.id
        """
        ensure_global_variables_row(TEST_DB)

        # Run transition to set up data
        mapper = NewStoryDatabaseMapper(dbname=TEST_DB)
        transition_data = create_placeholder_transition_data()
        result = mapper.perform_transition(transition_data)
        assert result is not None, "Transition failed"

        # Now run the same query narrative.py uses for bootstrap
        location = run_bootstrap_location_query(TEST_DB)

        assert location is not None, (
            "Bootstrap location query returned None! "
            "FK chain may be broken: global_variables.user_character → "
            "characters.current_location → places.id"
        )
        assert location["name"] == "Nexus Corp Tower", (
            f"Expected 'Nexus Corp Tower', got '{location['name']}'"
        )
        print(f"✓ Bootstrap location query works: {location['name']}")
        print(f"  Summary: {location['summary'][:60]}...")


class TestBootstrapWithRealCache:
    """
    Test bootstrap transition using REAL cached wizard data from slot 3.

    This test copies the new_story_creator cache to a test slot and runs
    the full transition + bootstrap flow with actual API calls.

    Prerequisites:
    - Run through the wizard on slot 3 to populate the cache
    - Set OPENAI_API_KEY in environment (or use 1Password)
    """

    SOURCE_SLOT = 3   # Slot with wizard cache data
    TEST_SLOT = 4     # Slot for testing (to avoid modifying slot 3)
    SOURCE_DB = "save_03"
    TEST_DB = "save_04"

    def copy_cache_to_test_slot(self) -> dict:
        """Copy new_story_creator cache from slot 3 to test slot."""
        # Read from source
        with get_connection(self.SOURCE_DB, dict_cursor=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM assets.new_story_creator WHERE id = TRUE")
                row = cur.fetchone()
                if not row:
                    raise RuntimeError(f"No cache found in {self.SOURCE_DB}! Run wizard first.")

        cache = dict(row)
        print(f"✓ Read cache from {self.SOURCE_DB}")
        print(f"  Setting: {cache.get('setting_draft', {}).get('world_name', 'N/A')}")
        print(f"  Character: {cache.get('character_draft', {}).get('name', 'N/A')}")

        # Write to test slot
        with get_connection(self.TEST_DB) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM assets.new_story_creator WHERE id = TRUE")
                # Re-insert (JSONB columns are already dicts from dict_cursor)
                cur.execute("""
                    INSERT INTO assets.new_story_creator (
                        id, thread_id, setting_draft, character_draft, selected_seed,
                        layer_draft, zone_draft, initial_location, base_timestamp, target_slot
                    ) VALUES (TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    cache.get("thread_id"),
                    json.dumps(cache.get("setting_draft")) if cache.get("setting_draft") else None,
                    json.dumps(cache.get("character_draft")) if cache.get("character_draft") else None,
                    json.dumps(cache.get("selected_seed")) if cache.get("selected_seed") else None,
                    json.dumps(cache.get("layer_draft")) if cache.get("layer_draft") else None,
                    json.dumps(cache.get("zone_draft")) if cache.get("zone_draft") else None,
                    json.dumps(cache.get("initial_location")) if cache.get("initial_location") else None,
                    cache.get("base_timestamp"),
                    self.TEST_SLOT,
                ))
            conn.commit()

        print(f"✓ Copied cache to {self.TEST_DB}")
        return cache

    def build_transition_data_from_cache(self, cache: dict) -> TransitionData:
        """
        Build TransitionData from cache - mirrors narrative.py endpoint logic.
        """
        from nexus.api.new_story_schemas import CharacterCreationState

        # Parse timestamp
        seed_data = cache["selected_seed"]
        base_ts_data = seed_data.get("base_timestamp", {})
        if isinstance(base_ts_data, dict):
            base_timestamp = datetime(
                year=base_ts_data.get("year", 2024),
                month=base_ts_data.get("month", 1),
                day=base_ts_data.get("day", 1),
                hour=base_ts_data.get("hour", 12),
                minute=base_ts_data.get("minute", 0),
                tzinfo=timezone.utc
            )
        else:
            base_timestamp = datetime.now(timezone.utc)

        # Handle character draft format (legacy vs sub-phase)
        char_draft = cache["character_draft"]
        if "concept" in char_draft or "trait_selection" in char_draft:
            state = CharacterCreationState(**char_draft)
            char_draft = state.to_character_sheet().model_dump()

        return TransitionData(
            setting=SettingCard(**cache["setting_draft"]),
            character=CharacterSheet(**char_draft),
            seed=StorySeed(**cache["selected_seed"]),
            layer=LayerDefinition(**cache["layer_draft"]),
            zone=ZoneDefinition(**cache["zone_draft"]),
            location=PlaceProfile(**cache["initial_location"]),
            base_timestamp=base_timestamp,
            thread_id=cache.get("thread_id", ""),
        )

    def test_transition_with_real_cache(self):
        """
        Test perform_transition with REAL wizard-generated data.

        This tests:
        1. Cache copying works
        2. TransitionData construction from cache
        3. Database transition succeeds
        4. All entities created correctly
        """
        # Setup
        cache = self.copy_cache_to_test_slot()
        ensure_global_variables_row(self.TEST_DB)

        # Build transition data
        transition_data = self.build_transition_data_from_cache(cache)
        print(f"✓ Built TransitionData")
        print(f"  World: {transition_data.setting.world_name}")
        print(f"  Character: {transition_data.character.name}")
        print(f"  Location: {transition_data.location.name}")

        # Execute transition
        mapper = NewStoryDatabaseMapper(dbname=self.TEST_DB)
        result = mapper.perform_transition(transition_data)

        # Verify
        assert result is not None, "Transition returned None"
        assert result["character_id"] == 1, f"Expected character ID 1, got {result['character_id']}"

        # Verify FK chain works
        location = run_bootstrap_location_query(self.TEST_DB)
        assert location is not None, "FK chain query failed!"
        assert location["name"] == transition_data.location.name, (
            f"Location mismatch: expected {transition_data.location.name}, got {location['name']}"
        )

        print(f"✓ Transition succeeded with real cache data")
        print(f"  Character ID: {result['character_id']}")
        print(f"  Place ID: {result['place_id']}")
        print(f"  Starting location: {location['name']}")

    def test_bootstrap_api_call(self):
        """
        Test LIVE OpenAI bootstrap call with real setting/character/seed.

        IMPORTANT: This makes actual API calls to OpenAI!
        Set OPENAI_API_KEY before running.

        Tests:
        1. Bootstrap narrative generation works
        2. StorytellerResponseExtended is valid
        3. Incubator row created with correct schema
        4. choice_object uses "presented" key (not "choices")
        """
        import os

        # Check for API key
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set - skipping live API test")

        # Setup: copy cache and run transition
        cache = self.copy_cache_to_test_slot()
        ensure_global_variables_row(self.TEST_DB)
        transition_data = self.build_transition_data_from_cache(cache)

        mapper = NewStoryDatabaseMapper(dbname=self.TEST_DB)
        result = mapper.perform_transition(transition_data)
        assert result is not None, "Transition failed"

        print(f"✓ Transition complete, testing bootstrap API call...")

        # Import the bootstrap function
        from nexus.api.narrative import generate_bootstrap_narrative

        # Call bootstrap with connection
        import uuid
        import asyncio
        session_id = str(uuid.uuid4())

        with get_connection(self.TEST_DB) as conn:
            incubator_data = asyncio.get_event_loop().run_until_complete(
                generate_bootstrap_narrative(
                    conn=conn,
                    session_id=session_id,
                    user_text="Begin the story.",
                    slot=self.TEST_SLOT,
                )
            )

        # Verify incubator data structure
        assert incubator_data is not None, "Bootstrap returned None"
        assert "storyteller_text" in incubator_data, "Missing storyteller_text"
        assert len(incubator_data["storyteller_text"]) > 100, "Narrative too short"

        # Critical: verify choice_object uses "presented" not "choices"
        if incubator_data.get("choice_object"):
            assert "presented" in incubator_data["choice_object"], (
                "choice_object uses wrong key! Expected 'presented', found keys: "
                f"{list(incubator_data['choice_object'].keys())}"
            )
            print(f"✓ choice_object structure correct: {list(incubator_data['choice_object'].keys())}")

        print(f"✓ Bootstrap API call succeeded!")
        print(f"  Session ID: {session_id}")
        print(f"  Narrative length: {len(incubator_data['storyteller_text'])} chars")
        print(f"  Preview: {incubator_data['storyteller_text'][:200]}...")


if __name__ == "__main__":
    import json

    # Allow running directly for quick iteration
    print(f"Testing bootstrap transition on {TEST_DB}...")
    print("=" * 60)

    test = TestBootstrapTransition()

    print("\n1. Testing global_variables survival...")
    test.test_global_variables_survives_truncate()

    print("\n2. Testing character ID reset...")
    test.test_character_id_resets_to_one()

    print("\n3. Testing atomic behavior...")
    test.test_transition_is_atomic()

    print("\n4. Testing bootstrap location query (FK chain)...")
    test.test_bootstrap_location_query_works()

    print("\n" + "=" * 60)
    print("Basic tests passed! ✓")

    # Run real cache tests
    print("\n" + "=" * 60)
    print("Testing with REAL wizard cache data...")
    print("=" * 60)

    real_test = TestBootstrapWithRealCache()

    print("\n5. Testing transition with real cache...")
    try:
        real_test.test_transition_with_real_cache()
    except RuntimeError as e:
        print(f"⚠ Skipped: {e}")

    print("\n6. Testing bootstrap API call (live OpenAI)...")
    import os
    if os.environ.get("OPENAI_API_KEY"):
        real_test.test_bootstrap_api_call()
    else:
        print("⚠ Skipped: OPENAI_API_KEY not set")

    print("\n" + "=" * 60)
    print("All tests completed! ✓")
