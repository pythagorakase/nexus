#!/usr/bin/env python3
"""
Simplified test script for live narrative turns
Tests writing to incubator table with mock data
"""

import json
import logging
import sys
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

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


class SimpleNarrativeTester:
    """Simplified test harness for narrative turns"""

    def __init__(self, dry_run: bool = False):
        """Initialize the test harness"""
        self.dry_run = dry_run
        self.session_id = str(uuid.uuid4())

        # Load settings
        settings = load_settings()
        self.settings = settings

        # Get test mode settings
        narrative_settings = settings.get("Agent Settings", {}).get("global", {}).get("narrative", {})
        self.test_mode = narrative_settings.get("test_mode", False)

        # Set up database connection
        self.conn = psycopg2.connect(
            host="localhost",
            database="NEXUS",
            user="pythagor"
        )
        self.conn.autocommit = False

        logger.info(f"Initialized SimpleNarrativeTester (test_mode={self.test_mode}, dry_run={self.dry_run})")
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

    def continue_narrative_simple(
        self,
        parent_chunk_id: int = 1425,
        user_text: str = "Continue."
    ) -> Dict[str, Any]:
        """
        Simplified narrative continuation - creates mock data for testing incubator

        Args:
            parent_chunk_id: The chunk to continue from
            user_text: User's completion text

        Returns:
            Dict with incubator data
        """
        logger.info(f"Starting simplified narrative continuation from chunk {parent_chunk_id}")
        logger.info(f"User text: '{user_text}'")

        # Get parent chunk info
        parent_info = self.get_chunk_info(parent_chunk_id)
        logger.info(f"Parent chunk: S{parent_info['season']}E{parent_info['episode']}, "
                   f"Location: {parent_info['place_name']}, Time: {parent_info['world_time']}")

        # Create mock generated narrative
        mock_storyteller_text = """The morning light filters through the rain-streaked windows of Le Chat Noir,
casting long shadows across the worn floorboards. You can hear the distant hum of the city awakening -
the whir of delivery drones, the occasional siren, the muffled conversations of early risers passing by.

The coffee maker behind the counter hisses to life, filling the air with the rich aroma of synthetic beans.
It's going to be another long day in Night City, but for now, in this moment, there's a strange peace."""

        # Prepare incubator data with mock values
        incubator_data = {
            "chunk_id": parent_chunk_id + 1,
            "parent_chunk_id": parent_chunk_id,
            "user_text": user_text,
            "storyteller_text": mock_storyteller_text,
            "metadata_updates": {
                "episode_transition": "continue",
                "time_delta_seconds": 180,  # 3 minutes later
                "time_delta_description": "A few minutes later",
                "world_layer": "primary",
                "pacing": "moderate"
            },
            "entity_updates": [
                {
                    "type": "character",
                    "id": 1,  # Alex
                    "field": "emotional_state",
                    "old_value": "anxious",
                    "new_value": "contemplative"
                }
            ],
            "reference_updates": {
                "character_present": [1],  # Alex
                "character_referenced": [],
                "place_referenced": []
            },
            "session_id": self.session_id,
            "llm_response_id": f"mock_response_{uuid.uuid4().hex[:8]}",
            "status": "provisional"
        }

        # Write to incubator or log in dry run
        if self.dry_run:
            logger.info("DRY RUN - Would write to incubator:")
            logger.info(json.dumps(incubator_data, indent=2, default=str))
        else:
            logger.info("Writing to incubator table...")
            self._write_to_incubator(incubator_data)
            logger.info("Successfully written to incubator")

        # Return results
        result = {
            "success": True,
            "session_id": self.session_id,
            "incubator_data": incubator_data
        }

        logger.info("=" * 80)
        logger.info("SIMPLIFIED TEST COMPLETE")
        logger.info(f"Mock narrative for chunk {parent_chunk_id + 1} is provisional in incubator")
        logger.info(f"Session ID: {self.session_id}")
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
                print(json.dumps(value, indent=2, default=str))
            else:
                print(f"{key}: {value}")

        print("=" * 80)

    def clear_incubator(self) -> None:
        """Clear the incubator table"""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM incubator WHERE id = TRUE")
        self.conn.commit()
        logger.info("Incubator cleared")

    def __del__(self):
        """Clean up database connection"""
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()


def main():
    """Main test function"""
    import argparse

    parser = argparse.ArgumentParser(description="Simple test for narrative turns")
    parser.add_argument("--dry-run", action="store_true",
                       help="Don't write to database, just show what would happen")
    parser.add_argument("--chunk-id", type=int, default=1425,
                       help="Parent chunk ID to continue from (default: 1425)")
    parser.add_argument("--user-text", type=str, default="Continue.",
                       help="User text to complete the chunk with (default: 'Continue.')")
    parser.add_argument("--view", action="store_true",
                       help="View current incubator contents")
    parser.add_argument("--clear", action="store_true",
                       help="Clear the incubator table")

    args = parser.parse_args()

    try:
        tester = SimpleNarrativeTester(dry_run=args.dry_run)

        if args.clear:
            tester.clear_incubator()
        elif args.view:
            tester.view_incubator()
        else:
            result = tester.continue_narrative_simple(
                parent_chunk_id=args.chunk_id,
                user_text=args.user_text
            )

            if result["success"]:
                print("\n✅ Simple test completed successfully!")
                print(f"🔑 Session ID: {result['session_id']}")

                if not args.dry_run:
                    print("\n💡 Run with --view to see incubator contents")
                    print("💡 Run with --clear to clear the incubator")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()