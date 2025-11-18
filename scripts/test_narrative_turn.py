#!/usr/bin/env python3
"""
Test script for live narrative turns - completes chunk 1425 with "Continue."
Tests the full flow: LORE context building → GPT-5.1 call → incubator write
"""

import json
import logging
import sys
import uuid
import os
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from nexus.agents.lore.lore import LORE
from nexus.agents.logon.apex_schema import (
    StorytellerResponseStandard,
    ChronologyUpdate,
    ChunkMetadataUpdate,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_settings():
    """Load settings from settings.json"""
    settings_path = Path(__file__).parent.parent / "settings.json"
    with open(settings_path, "r") as f:
        return json.load(f)


class NarrativeTurnTester:
    """Test harness for live narrative turns"""

    def __init__(self, dry_run: bool = False):
        """
        Initialize the test harness

        Args:
            dry_run: If True, don't write to database, just log what would happen
        """
        self.dry_run = dry_run
        self.session_id = str(uuid.uuid4())

        # Load settings
        settings = load_settings()
        self.settings = settings

        # Get test mode settings
        narrative_settings = settings.get("Agent Settings", {}).get("global", {}).get("narrative", {})
        self.test_mode = narrative_settings.get("test_mode", False)
        self.test_suffix = narrative_settings.get("test_database_suffix", "_test")

        # Set up database connection
        self.conn = psycopg2.connect(
            host="localhost",
            database="NEXUS",
            user="pythagor"
        )
        self.conn.autocommit = False

        logger.info(f"Initialized NarrativeTurnTester (test_mode={self.test_mode}, dry_run={self.dry_run})")
        logger.info(f"Session ID: {self.session_id}")

    def get_chunk_info(self, chunk_id: int) -> Dict[str, Any]:
        """Get information about a chunk"""
        query = """
        SELECT
            nv.id,
            nv.raw_text,
            nv.season,
            nv.episode,
            nv.world_time,
            cm.place,
            p.name as place_name
        FROM narrative_view nv
        JOIN chunk_metadata cm ON cm.chunk_id = nv.id
        LEFT JOIN places p ON p.id = cm.place
        WHERE nv.id = %s
        """

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (chunk_id,))
            result = cur.fetchone()

        if not result:
            raise ValueError(f"Chunk {chunk_id} not found")

        return dict(result)

    async def continue_narrative(
        self,
        parent_chunk_id: int = 1425,
        user_text: str = "Continue."
    ) -> Dict[str, Any]:
        """
        Continue the narrative from a given chunk

        Args:
            parent_chunk_id: The chunk to continue from
            user_text: User's completion text

        Returns:
            Dict with incubator data and diagnostics
        """
        logger.info(f"Starting narrative continuation from chunk {parent_chunk_id}")
        logger.info(f"User text: '{user_text}'")

        # Get parent chunk info
        parent_info = self.get_chunk_info(parent_chunk_id)
        logger.info(f"Parent chunk: S{parent_info['season']}E{parent_info['episode']}, "
                   f"Location: {parent_info['place_name']}, Time: {parent_info['world_time']}")

        # Step 1: Initialize LORE
        logger.info("Step 1: Initializing LORE agent...")
        lore = LORE(
            enable_logon=True,  # Use LOGON for generation
            debug=True
        )

        # Step 2: Process the turn (builds context and generates narrative)
        logger.info("Step 2: Processing turn with LORE (context + generation)...")
        start_time = datetime.now()

        # Call LORE's process_turn method which handles the complete pipeline
        try:
            response = await lore.process_turn(user_text)
            logger.info(f"LORE returned response type: {type(response)}")

            # Print the response to see what we're working with
            if response:
                print("\n" + "="*80)
                print("LORE RESPONSE:")
                print("="*80)
                if hasattr(response, 'model_dump'):
                    print(json.dumps(response.model_dump(), indent=2, default=str))
                else:
                    print(f"Response: {response}")
                print("="*80 + "\n")
        except Exception as e:
            logger.error(f"LORE process_turn failed: {e}")
            raise

        total_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Turn processed in {total_time:.2f} seconds")

        # Step 3: Parse response and prepare incubator data
        logger.info("Step 3: Parsing response and preparing incubator data...")

        # Extract narrative text from the response
        storyteller_text = response.narrative.text if hasattr(response, 'narrative') else None

        if not storyteller_text:
            raise ValueError("No narrative text in response")

        incubator_data = {
            "chunk_id": parent_chunk_id + 1,
            "parent_chunk_id": parent_chunk_id,
            "user_text": user_text,
            "storyteller_text": storyteller_text,
            "metadata_updates": {},
            "entity_updates": {},
            "reference_updates": {},
            "session_id": self.session_id,
            "llm_response_id": getattr(response, 'response_id', None),
            "status": "provisional"
        }

        # Extract metadata updates
        if hasattr(response, 'metadata') and response.metadata:
            metadata = response.metadata

            # Handle chronology updates using new time fields
            if hasattr(metadata, 'chronology') and metadata.chronology:
                chron = metadata.chronology

                # Handle both old boolean format and new enum format
                if hasattr(chron, 'episode_transition'):
                    # New format with enum
                    episode_transition = chron.episode_transition.value if hasattr(chron.episode_transition, 'value') else chron.episode_transition or "continue"
                else:
                    # Old format with boolean flags
                    if getattr(chron, 'season_increment', False):
                        episode_transition = "new_season"
                    elif getattr(chron, 'episode_increment', False):
                        episode_transition = "new_episode"
                    else:
                        episode_transition = "continue"

                incubator_data["metadata_updates"]["chronology"] = {
                    "episode_transition": episode_transition,
                    "time_delta_minutes": getattr(chron, 'time_delta_minutes', None),
                    "time_delta_hours": getattr(chron, 'time_delta_hours', None),
                    "time_delta_days": getattr(chron, 'time_delta_days', None),
                    "time_delta_description": getattr(chron, 'time_delta_description', None) or getattr(chron, 'time_elapsed_description', None)
                }

            if hasattr(metadata, 'world_layer'):
                incubator_data["metadata_updates"]["world_layer"] = metadata.world_layer.value if hasattr(metadata.world_layer, 'value') else metadata.world_layer

        # Extract entity state updates
        if hasattr(response, 'state_updates') and response.state_updates:
            entity_updates = {
                "characters": [],
                "locations": [],
                "factions": []
            }

            # Fix: Use 'characters' not 'character_updates'
            if hasattr(response.state_updates, 'characters'):
                for char in response.state_updates.characters:
                    entity_updates["characters"].append({
                        "character_id": char.character_id,
                        "character_name": getattr(char, 'character_name', None),
                        "emotional_state": char.emotional_state,
                        "current_activity": getattr(char, 'current_activity', None),
                        "current_location": getattr(char, 'current_location', None)
                    })

            if hasattr(response.state_updates, 'locations'):
                for loc in response.state_updates.locations:
                    entity_updates["locations"].append({
                        "place_id": loc.place_id,
                        "place_name": getattr(loc, 'place_name', None),
                        "current_status": loc.current_status
                    })

            if hasattr(response.state_updates, 'factions'):
                for faction in response.state_updates.factions:
                    entity_updates["factions"].append({
                        "faction_id": faction.faction_id,
                        "faction_name": getattr(faction, 'faction_name', None),
                        "current_activity": faction.current_activity
                    })

            incubator_data["entity_updates"] = entity_updates

        # Extract entity references
        if hasattr(response, 'referenced_entities') and response.referenced_entities:
            refs = response.referenced_entities
            reference_updates = {
                "characters": [],
                "places": [],
                "factions": []
            }

            if hasattr(refs, 'characters'):
                for char in refs.characters:
                    reference_updates["characters"].append({
                        "character_id": char.character_id,
                        "character_name": getattr(char, 'character_name', None),
                        "reference_type": char.reference_type.value if hasattr(char.reference_type, 'value') else char.reference_type
                    })

            if hasattr(refs, 'places'):
                for place in refs.places:
                    reference_updates["places"].append({
                        "place_id": place.place_id,
                        "place_name": getattr(place, 'place_name', None),
                        "reference_type": place.reference_type.value if hasattr(place.reference_type, 'value') else place.reference_type,
                        "evidence": getattr(place, 'evidence', None)
                    })

            if hasattr(refs, 'factions'):
                for faction in refs.factions:
                    reference_updates["factions"].append({
                        "faction_id": faction.faction_id,
                        "faction_name": getattr(faction, 'faction_name', None)
                    })

            incubator_data["reference_updates"] = reference_updates

        # Step 4: Write to incubator (or log in dry run)
        if self.dry_run:
            logger.info("DRY RUN - Would write to incubator:")
            logger.info(json.dumps(incubator_data, indent=2, default=str))
        else:
            logger.info("Step 4: Writing to incubator table...")
            self._write_to_incubator(incubator_data)
            logger.info("Successfully written to incubator")

        # Return results
        result = {
            "success": True,
            "session_id": self.session_id,
            "incubator_data": incubator_data,
            "diagnostics": {
                "total_time": total_time,
                "response_length": len(incubator_data["storyteller_text"]) if incubator_data["storyteller_text"] else 0
            }
        }

        logger.info("=" * 80)
        logger.info("NARRATIVE GENERATION COMPLETE")
        logger.info(f"New chunk {parent_chunk_id + 1} is provisional in incubator")
        logger.info(f"Session ID: {self.session_id}")
        logger.info(f"Total time: {result['diagnostics']['total_time']:.2f} seconds")
        logger.info("=" * 80)

        return result

    def _write_to_incubator(self, data: Dict[str, Any]) -> None:
        """Write data to the incubator table"""
        with self.conn.cursor() as cur:
            # Clear any existing incubator entry (singleton table)
            cur.execute("DELETE FROM incubator WHERE id = TRUE")

            # Insert new incubator entry
            query = """
            INSERT INTO incubator (
                id, chunk_id, parent_chunk_id, user_text, storyteller_text,
                metadata_updates, entity_updates, reference_updates,
                session_id, llm_response_id, status
            ) VALUES (
                TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """

            cur.execute(query, (
                data["chunk_id"],
                data["parent_chunk_id"],
                data["user_text"],
                data["storyteller_text"],
                json.dumps(data["metadata_updates"]),
                json.dumps(data["entity_updates"]),
                json.dumps(data["reference_updates"]),
                data["session_id"],
                data["llm_response_id"],
                data["status"]
            ))

        self.conn.commit()

    def view_incubator(self) -> None:
        """Display the current incubator contents"""
        query = "SELECT * FROM incubator_view"

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            result = cur.fetchone()

        if not result:
            logger.info("Incubator is empty")
            return

        print("\n" + "=" * 80)
        print("INCUBATOR CONTENTS")
        print("=" * 80)

        for key, value in dict(result).items():
            if isinstance(value, (dict, list)):
                print(f"{key}:")
                print(json.dumps(value, indent=2))
            else:
                print(f"{key}: {value}")

        print("=" * 80)

    def __del__(self):
        """Clean up database connection"""
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()


async def main():
    """Main test function"""
    import argparse

    parser = argparse.ArgumentParser(description="Test live narrative turns")
    parser.add_argument("--dry-run", action="store_true",
                       help="Don't write to database, just show what would happen")
    parser.add_argument("--chunk-id", type=int, default=1425,
                       help="Parent chunk ID to continue from (default: 1425)")
    parser.add_argument("--user-text", type=str, default="Continue.",
                       help="User text to complete the chunk with (default: 'Continue.')")
    parser.add_argument("--view", action="store_true",
                       help="View current incubator contents")

    args = parser.parse_args()

    try:
        tester = NarrativeTurnTester(dry_run=args.dry_run)

        if args.view:
            tester.view_incubator()
        else:
            result = await tester.continue_narrative(
                parent_chunk_id=args.chunk_id,
                user_text=args.user_text
            )

            if result["success"]:
                print("\n✅ Test completed successfully!")
                print(f"📝 Generated text length: {result['diagnostics']['response_length']} characters")
                print(f"⏱️  Total time: {result['diagnostics']['total_time']:.2f} seconds")
                print(f"🔑 Session ID: {result['session_id']}")

                if not args.dry_run:
                    print("\n💡 Run with --view to see incubator contents")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())