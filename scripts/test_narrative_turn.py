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
    StorytellerResponseMinimal,
    ChronologyUpdate,
    ChunkMetadataUpdate,
)
from nexus.agents.lore.logon_utility import LogonUtility

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

    def continue_narrative(
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

        # Step 2: Build context package
        logger.info("Step 2: Building context package...")
        start_time = datetime.now()

        # Simulate the narrative flow with user text completing the parent chunk
        completed_text = parent_info['raw_text'] + "\n\n" + user_text

        # Use LORE's turn cycle to build context
        context_package = lore.turn_manager.build_context_package(
            chunk_id=parent_chunk_id,
            user_input=user_text
        )

        context_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Context package built in {context_time:.2f} seconds")
        logger.info(f"Context size: {len(json.dumps(context_package))//1024}KB")

        # Step 3: Call LOGON (GPT-5.1)
        logger.info("Step 3: Calling LOGON for narrative generation...")
        start_time = datetime.now()

        # Initialize LOGON if not already done
        if not lore.logon:
            lore._initialize_logon()

        # Generate narrative
        response = lore.logon.generate_narrative(
            context_payload=context_package,
            chunk_id=parent_chunk_id + 1,  # New chunk ID
            user_turn=user_text
        )

        generation_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Narrative generated in {generation_time:.2f} seconds")

        # Step 4: Parse response and prepare incubator data
        logger.info("Step 4: Parsing response and preparing incubator data...")

        incubator_data = {
            "chunk_id": parent_chunk_id + 1,
            "parent_chunk_id": parent_chunk_id,
            "user_text": user_text,
            "storyteller_text": response.narrative if hasattr(response, 'narrative') else response.get('narrative'),
            "metadata_updates": {},
            "entity_updates": [],
            "reference_updates": {},
            "session_id": self.session_id,
            "llm_response_id": getattr(response, 'response_id', None),
            "status": "provisional"
        }

        # Extract metadata updates if present
        if hasattr(response, 'chunk_metadata') and response.chunk_metadata:
            metadata = response.chunk_metadata
            if hasattr(metadata, 'chronology') and metadata.chronology:
                incubator_data["metadata_updates"]["episode_transition"] = metadata.chronology.episode_transition
                incubator_data["metadata_updates"]["time_delta_seconds"] = metadata.chronology.time_delta_seconds
                incubator_data["metadata_updates"]["time_delta_description"] = metadata.chronology.time_delta_description

            if hasattr(metadata, 'world_layer'):
                incubator_data["metadata_updates"]["world_layer"] = metadata.world_layer

            if hasattr(metadata, 'pacing'):
                incubator_data["metadata_updates"]["pacing"] = metadata.pacing

        # Extract entity updates if present
        if hasattr(response, 'state_updates') and response.state_updates:
            for update in response.state_updates.character_updates or []:
                incubator_data["entity_updates"].append({
                    "type": "character",
                    "id": update.character_id,
                    "name": update.character_name,
                    "field": "emotional_state",
                    "new_value": update.emotional_state
                })

        # Extract entity references if present
        if hasattr(response, 'referenced_entities') and response.referenced_entities:
            refs = response.referenced_entities
            incubator_data["reference_updates"] = {
                "character_present": [c.character_id for c in refs.characters if c.reference_type == "present"],
                "character_referenced": [c.character_id for c in refs.characters if c.reference_type == "mentioned"],
                "place_referenced": [p.place_id for p in refs.places if p.place_id]
            }

        # Step 5: Write to incubator (or log in dry run)
        if self.dry_run:
            logger.info("DRY RUN - Would write to incubator:")
            logger.info(json.dumps(incubator_data, indent=2, default=str))
        else:
            logger.info("Step 5: Writing to incubator table...")
            self._write_to_incubator(incubator_data)
            logger.info("Successfully written to incubator")

        # Return results
        result = {
            "success": True,
            "session_id": self.session_id,
            "incubator_data": incubator_data,
            "diagnostics": {
                "context_build_time": context_time,
                "generation_time": generation_time,
                "total_time": context_time + generation_time,
                "context_size_kb": len(json.dumps(context_package))//1024,
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


def main():
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
            result = tester.continue_narrative(
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
    main()