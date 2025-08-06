#!/usr/bin/env python
"""
Context Assembler

Interactive tool for assembling context packages from different database components.
Maintains a hierarchical structure and tracks token count while building context.
"""

import argparse
import json
import os
import sys
import re
import psycopg2
from psycopg2.extras import RealDictCursor
import tiktoken
import logging
from typing import Dict, List, Any, Tuple, Optional, Union
from decimal import Decimal


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert Decimal to float for JSON serialization
            return float(obj)
        return super().default(obj)


class ContextAssembler:
    """
    Interactive tool for assembling context packages from database components.
    Maintains a JSON structure and tracks token size during assembly.
    """

    def __init__(self, filename: str, new: bool = False):
        """
        Initialize the context assembler.
        
        Args:
            filename: Path to the JSON file
            new: If True, create a new file; otherwise load existing file
        """
        self.filename = filename
        self.data = {
            "characters": {},
            "places": {},
            "seasons": {},
            "episodes": {},
            "factions": {}
        }
        self.conn = self._connect_to_db()
        self.encoder = tiktoken.get_encoding("cl100k_base")  # Default for GPT models
        
        if not new and os.path.exists(filename):
            self._load_file()
        else:
            self._save_file()
            
        self.token_size = self._calculate_tokens()
        logger.info(f"Starting token size: {self.token_size:,}")

    def _connect_to_db(self) -> psycopg2.extensions.connection:
        """Connect to the PostgreSQL database."""
        try:
            # Connection details from CLAUDE.md
            conn = psycopg2.connect(
                dbname="NEXUS",
                user="pythagor",
                host="localhost",
                port=5432
            )
            return conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            sys.exit(1)

    def _load_file(self):
        """Load the context data from the JSON file."""
        try:
            with open(self.filename, 'r') as f:
                self.data = json.load(f)
            logger.info(f"Loaded context from {self.filename}")
            # Calculate and display token count
            tokens = self._calculate_tokens()
            logger.info(f"Loaded context size: {tokens:,} tokens")
        except Exception as e:
            logger.error(f"Error loading file: {e}")
            sys.exit(1)

    def _save_file(self):
        """Save the context data to the JSON file."""
        try:
            # Sort episodes by key before saving
            if "episodes" in self.data and self.data["episodes"]:
                sorted_episodes = dict(sorted(self.data["episodes"].items()))
                self.data["episodes"] = sorted_episodes
            
            # Sort characters by numeric ID before saving
            if "characters" in self.data and self.data["characters"]:
                # Define the column order from the database
                column_order = [
                    "name", "summary", "appearance", "background", "personality",
                    "emotional_state", "current_activity", "current_location",
                    "extra_data", "created_at", "updated_at", "entity_type"
                ]
                
                sorted_characters = {}
                for char_id, char_data in sorted(self.data["characters"].items(), key=lambda x: int(x[0])):
                    # Create ordered character data
                    ordered_char_data = {}
                    # First add fields in the database column order
                    for field in column_order:
                        if field in char_data:
                            ordered_char_data[field] = char_data[field]
                    # Then add any remaining fields not in the column order (shouldn't happen, but just in case)
                    for field, value in char_data.items():
                        if field not in ordered_char_data:
                            ordered_char_data[field] = value
                    
                    sorted_characters[char_id] = ordered_char_data
                
                self.data["characters"] = sorted_characters
            
            with open(self.filename, 'w') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False, sort_keys=False, cls=DecimalEncoder)
            logger.info(f"Saved context to {self.filename}")
        except Exception as e:
            logger.error(f"Error saving file: {e}")

    def _calculate_tokens(self) -> int:
        """Calculate the token count of the current data."""
        json_str = json.dumps(self.data, cls=DecimalEncoder)
        tokens = len(self.encoder.encode(json_str))
        return tokens

    def _update_and_save(self):
        """Calculate new token size and save file."""
        old_size = self.token_size
        self.token_size = self._calculate_tokens()
        self._save_file()
        logger.info(f"new token size: {self.token_size:,}")
        
        # Calculate difference
        diff = self.token_size - old_size
        sign = "+" if diff > 0 else ""
        logger.info(f"change: {sign}{diff:,} tokens")

    def _parse_episode_range(self, range_str: str) -> List[str]:
        """
        Parse episode range expressions like s01e01-s01e06 or s01e01,s01e03
        
        Args:
            range_str: Range expression for episodes
            
        Returns:
            List of episode identifiers
        """
        if range_str.lower() == "all":
            # Get all episodes from the database
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT DISTINCT season, episode FROM episodes ORDER BY season, episode"
                )
                episodes = [f"s{row['season']:02d}e{row['episode']:02d}" for row in cur.fetchall()]
            return episodes
            
        if "," in range_str:
            # Handle comma-separated list
            return [item.strip() for item in range_str.split(",")]
            
        if "-" in range_str:
            # Handle range
            start, end = range_str.split("-")
            
            # Extract season and episode numbers
            start_match = re.match(r"s(\d+)e(\d+)", start.lower())
            end_match = re.match(r"s(\d+)e(\d+)", end.lower())
            
            if not (start_match and end_match):
                logger.error(f"Invalid episode range format: {range_str}")
                return []
                
            start_season = int(start_match.group(1))
            start_episode = int(start_match.group(2))
            end_season = int(end_match.group(1))
            end_episode = int(end_match.group(2))
            
            # Query the database for all episodes in this range
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT DISTINCT season, episode FROM episodes 
                    WHERE (season > %s OR (season = %s AND episode >= %s))
                    AND (season < %s OR (season = %s AND episode <= %s))
                    ORDER BY season, episode
                    """,
                    (
                        start_season, start_season, start_episode,
                        end_season, end_season, end_episode
                    )
                )
                episodes = [f"s{row['season']:02d}e{row['episode']:02d}" for row in cur.fetchall()]
            return episodes
        
        # Single episode
        return [range_str]

    def add_character_field(self, character_id: int, field: str):
        """
        Add a character field to the context.
        
        Args:
            character_id: ID of the character
            field: Field to add (e.g., 'summary', 'background')
        """
        logger.info(f"Adding character {character_id} {field}...")
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # First check if the character exists
            cur.execute(
                "SELECT id, name FROM characters WHERE id = %s",
                (character_id,)
            )
            char_data = cur.fetchone()
            
            if not char_data:
                logger.error(f"Character with ID {character_id} not found")
                return
            
            # Check if the requested field exists
            cur.execute(
                f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'characters' AND column_name = %s
                """,
                (field,)
            )
            
            if not cur.fetchone():
                logger.error(f"Field '{field}' not found in characters table")
                return
            
            # Get the field value
            cur.execute(
                f"SELECT {field} FROM characters WHERE id = %s",
                (character_id,)
            )
            result = cur.fetchone()
            
            if not result or result[field] is None:
                logger.error(f"No data found for character {character_id} {field}")
                return
            
            # Create the character entry if it doesn't exist
            if str(character_id) not in self.data["characters"]:
                # Get the character name
                self.data["characters"][str(character_id)] = {
                    "name": char_data["name"]
                }
            
            # Add the field
            self.data["characters"][str(character_id)][field] = result[field]
            
            self._update_and_save()

    def remove_character_field(self, character_id: int, field: str):
        """
        Remove a character field from the context.
        
        Args:
            character_id: ID of the character
            field: Field to remove
        """
        char_id_str = str(character_id)
        
        if char_id_str not in self.data["characters"]:
            logger.error(f"Character {character_id} not found in context")
            return
            
        if field not in self.data["characters"][char_id_str]:
            logger.error(f"Field '{field}' not found for character {character_id}")
            return
            
        logger.info(f"Removing character {character_id} {field}...")
        
        # Remove the field
        del self.data["characters"][char_id_str][field]
        
        # Remove empty character entry
        if len(self.data["characters"][char_id_str]) <= 1:  # Only name remains
            del self.data["characters"][char_id_str]
            
        self._update_and_save()

    def add_place_field(self, place_id: int, field: str):
        """
        Add a place field to the context.
        
        Args:
            place_id: ID of the place
            field: Field to add
        """
        logger.info(f"Adding place {place_id} {field}...")
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # First check if the place exists
            cur.execute(
                "SELECT id, name, type FROM places WHERE id = %s",
                (place_id,)
            )
            place_data = cur.fetchone()
            
            if not place_data:
                logger.error(f"Place with ID {place_id} not found")
                return
            
            # Check if the requested field exists
            cur.execute(
                f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'places' AND column_name = %s
                """,
                (field,)
            )
            
            if not cur.fetchone():
                logger.error(f"Field '{field}' not found in places table")
                return
            
            # Get the field value
            cur.execute(
                f"SELECT {field} FROM places WHERE id = %s",
                (place_id,)
            )
            result = cur.fetchone()
            
            if not result or result[field] is None:
                logger.error(f"No data found for place {place_id} {field}")
                return
            
            # Create the place entry if it doesn't exist
            if str(place_id) not in self.data["places"]:
                self.data["places"][str(place_id)] = {
                    "name": place_data["name"],
                    "type": place_data["type"]
                }
            
            # Add the field (special handling for geographic types)
            if field == "coordinates":
                # Query the coordinates as text representation (lat, lon)
                with self.conn.cursor(cursor_factory=RealDictCursor) as coord_cur:
                    coord_cur.execute(
                        """
                        SELECT 
                            ST_Y(coordinates::geometry) as latitude,
                            ST_X(coordinates::geometry) as longitude
                        FROM places WHERE id = %s
                        """,
                        (place_id,)
                    )
                    coord_result = coord_cur.fetchone()
                    
                    if coord_result:
                        self.data["places"][str(place_id)][field] = {
                            "latitude": coord_result["latitude"],
                            "longitude": coord_result["longitude"]
                        }
                    else:
                        # Fallback to raw value if ST functions fail
                        self.data["places"][str(place_id)][field] = result[field]
            else:
                self.data["places"][str(place_id)][field] = result[field]
            
            self._update_and_save()

    def remove_place_field(self, place_id: int, field: str):
        """
        Remove a place field from the context.
        
        Args:
            place_id: ID of the place
            field: Field to remove
        """
        place_id_str = str(place_id)
        
        if place_id_str not in self.data["places"]:
            logger.error(f"Place {place_id} not found in context")
            return
            
        if field not in self.data["places"][place_id_str]:
            logger.error(f"Field '{field}' not found for place {place_id}")
            return
            
        logger.info(f"Removing place {place_id} {field}...")
        
        # Remove the field
        del self.data["places"][place_id_str][field]
        
        # Remove empty place entry
        if len(self.data["places"][place_id_str]) <= 2:  # Only name and type remain
            del self.data["places"][place_id_str]
            
        self._update_and_save()

    def add_season_field(self, season_id: int, field: str):
        """
        Add a season field to the context.
        
        Args:
            season_id: ID of the season
            field: Field to add
        """
        logger.info(f"Adding season {season_id} {field}...")
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # First check if the season exists
            cur.execute(
                "SELECT id FROM seasons WHERE id = %s",
                (season_id,)
            )
            
            if not cur.fetchone():
                logger.error(f"Season with ID {season_id} not found")
                return
            
            # Check if the requested field exists
            cur.execute(
                f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'seasons' AND column_name = %s
                """,
                (field,)
            )
            
            if not cur.fetchone():
                logger.error(f"Field '{field}' not found in seasons table")
                return
            
            # Get the field value
            cur.execute(
                f"SELECT {field} FROM seasons WHERE id = %s",
                (season_id,)
            )
            result = cur.fetchone()
            
            if not result or result[field] is None:
                logger.error(f"No data found for season {season_id} {field}")
                return
            
            # Create the season entry if it doesn't exist
            if str(season_id) not in self.data["seasons"]:
                self.data["seasons"][str(season_id)] = {}
            
            # Add the field
            self.data["seasons"][str(season_id)][field] = result[field]
            
            self._update_and_save()

    def remove_season_field(self, season_id: int, field: str):
        """
        Remove a season field from the context.
        
        Args:
            season_id: ID of the season
            field: Field to remove
        """
        season_id_str = str(season_id)
        
        if season_id_str not in self.data["seasons"]:
            logger.error(f"Season {season_id} not found in context")
            return
            
        if field not in self.data["seasons"][season_id_str]:
            logger.error(f"Field '{field}' not found for season {season_id}")
            return
            
        logger.info(f"Removing season {season_id} {field}...")
        
        # Remove the field
        del self.data["seasons"][season_id_str][field]
        
        # Remove empty season entry
        if not self.data["seasons"][season_id_str]:
            del self.data["seasons"][season_id_str]
            
        self._update_and_save()

    def add_faction_field(self, faction_id: int, field: str):
        """
        Add a faction field to the context.
        
        Args:
            faction_id: ID of the faction
            field: Field to add
        """
        logger.info(f"Adding faction {faction_id} {field}...")
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # First check if the faction exists
            cur.execute(
                "SELECT id, name FROM factions WHERE id = %s",
                (faction_id,)
            )
            faction_data = cur.fetchone()
            
            if not faction_data:
                logger.error(f"Faction with ID {faction_id} not found")
                return
            
            # Check if the requested field exists
            cur.execute(
                f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'factions' AND column_name = %s
                """,
                (field,)
            )
            
            if not cur.fetchone():
                logger.error(f"Field '{field}' not found in factions table")
                return
            
            # Get the field value
            cur.execute(
                f"SELECT {field} FROM factions WHERE id = %s",
                (faction_id,)
            )
            result = cur.fetchone()
            
            if not result or result[field] is None:
                logger.error(f"No data found for faction {faction_id} {field}")
                return
            
            # Create factions key if it doesn't exist
            if "factions" not in self.data:
                self.data["factions"] = {}
            
            # Create the faction entry if it doesn't exist
            if str(faction_id) not in self.data["factions"]:
                self.data["factions"][str(faction_id)] = {
                    "name": faction_data["name"]
                }
            
            # Add the field
            self.data["factions"][str(faction_id)][field] = result[field]
            
            self._update_and_save()

    def remove_faction_field(self, faction_id: int, field: str):
        """
        Remove a faction field from the context.
        
        Args:
            faction_id: ID of the faction
            field: Field to remove
        """
        faction_id_str = str(faction_id)
        
        # Check if factions key exists
        if "factions" not in self.data:
            logger.error(f"No factions in context")
            return
        
        if faction_id_str not in self.data["factions"]:
            logger.error(f"Faction {faction_id} not found in context")
            return
            
        if field not in self.data["factions"][faction_id_str]:
            logger.error(f"Field '{field}' not found for faction {faction_id}")
            return
            
        logger.info(f"Removing faction {faction_id} {field}...")
        
        # Remove the field
        del self.data["factions"][faction_id_str][field]
        
        # Remove empty faction entry
        if len(self.data["factions"][faction_id_str]) <= 1:  # Only name remains
            del self.data["factions"][faction_id_str]
            
        self._update_and_save()

    def add_episode_summary(self, episode_identifiers: Union[str, List[str]]):
        """
        Add episode summaries to the context.
        
        Args:
            episode_identifiers: Episode identifier(s) (e.g., 's01e01', 's01e01-s01e06')
        """
        if isinstance(episode_identifiers, str):
            episode_identifiers = self._parse_episode_range(episode_identifiers)
            
        logger.info(f"Adding episode summaries for {len(episode_identifiers)} episodes...")
        
        for episode_id in episode_identifiers:
            # Parse season and episode numbers
            match = re.match(r"s(\d+)e(\d+)", episode_id.lower())
            
            if not match:
                logger.error(f"Invalid episode identifier format: {episode_id}")
                continue
                
            season = int(match.group(1))
            episode = int(match.group(2))
            
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check if the episode exists
                cur.execute(
                    "SELECT summary FROM episodes WHERE season = %s AND episode = %s",
                    (season, episode)
                )
                result = cur.fetchone()
                
                if not result or result["summary"] is None:
                    logger.error(f"No summary found for episode {episode_id}")
                    continue
                
                # Create the episode entry if it doesn't exist
                if episode_id not in self.data["episodes"]:
                    self.data["episodes"][episode_id] = {}
                
                # Add the summary
                self.data["episodes"][episode_id]["summary"] = result["summary"]
        
        self._update_and_save()

    def add_episode_raw(self, episode_identifiers: Union[str, List[str]]):
        """
        Add raw episode content to the context.
        
        Args:
            episode_identifiers: Episode identifier(s) (e.g., 's01e01', 's01e01-s01e06')
        """
        if isinstance(episode_identifiers, str):
            episode_identifiers = self._parse_episode_range(episode_identifiers)
            
        logger.info(f"Adding raw content for {len(episode_identifiers)} episodes...")
        
        for episode_id in episode_identifiers:
            # Parse season and episode numbers
            match = re.match(r"s(\d+)e(\d+)", episode_id.lower())
            
            if not match:
                logger.error(f"Invalid episode identifier format: {episode_id}")
                continue
                
            season = int(match.group(1))
            episode = int(match.group(2))
            
            # No need to replace summary - we'll keep both summary and raw_text
            
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get the chunk span for this episode
                cur.execute(
                    """
                    SELECT chunk_span FROM episodes 
                    WHERE season = %s AND episode = %s
                    """,
                    (season, episode)
                )
                result = cur.fetchone()
                
                if not result or not result["chunk_span"]:
                    logger.error(f"No chunk span found for episode {episode_id}")
                    continue
                
                # Parse the chunk span - PostgreSQL range type [lower,upper)
                try:
                    # Extract the lower and upper bounds from the range string
                    chunk_span_str = str(result["chunk_span"])
                    # Format is typically like "[1,32)" or "[452,466)"
                    if chunk_span_str.startswith('[') and chunk_span_str.endswith(')'):
                        # Remove brackets and split
                        range_part = chunk_span_str[1:-1]  # Remove [ and )
                        start_chunk, end_chunk = map(int, range_part.split(','))

                        # The upper bound is exclusive in PostgreSQL ranges
                        # For [144,168), we want chunks 144 through 167 (not including 168)
                        # We need to subtract 1 from end_chunk for the BETWEEN query
                        end_chunk = end_chunk - 1
                    else:
                        logger.error(f"Unexpected chunk_span format for episode {episode_id}: {chunk_span_str}")
                        continue
                except Exception as e:
                    logger.error(f"Error parsing chunk span for episode {episode_id}: {result['chunk_span']} - {str(e)}")
                    continue
                
                # Get the raw text for all chunks in this span
                cur.execute(
                    """
                    SELECT id, raw_text FROM narrative_chunks 
                    WHERE id BETWEEN %s AND %s
                    ORDER BY id
                    """,
                    (start_chunk, end_chunk)
                )
                chunks = cur.fetchall()
                
                if not chunks:
                    logger.error(f"No chunks found for episode {episode_id}")
                    continue
                
                # Create the episode entry if it doesn't exist
                if episode_id not in self.data["episodes"]:
                    self.data["episodes"][episode_id] = {}

                # Create or get the raw_text container
                if "raw_text" not in self.data["episodes"][episode_id]:
                    self.data["episodes"][episode_id]["raw_text"] = {}

                # Add the raw text for each chunk, using the original chunk ID as the key
                for chunk in chunks:
                    chunk_id = str(chunk["id"])
                    self.data["episodes"][episode_id]["raw_text"][chunk_id] = chunk["raw_text"]
        
        self._update_and_save()

    def _parse_chunk_slug(self, chunk_slug: str) -> Optional[int]:
        """
        Parse a chunk slug like "s01e03c24" into the corresponding chunk ID.

        Args:
            chunk_slug: The chunk slug (e.g., 's01e03c24')

        Returns:
            The corresponding chunk ID, or None if not found
        """
        # Match the pattern s<season>e<episode>c<scene>
        match = re.match(r"s(\d+)e(\d+)c(\d+)", chunk_slug.lower())

        if not match:
            return None

        season = int(match.group(1))
        episode = int(match.group(2))
        scene = int(match.group(3))

        # Query chunk_metadata to find the chunk ID
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT chunk_id FROM chunk_metadata
                WHERE season = %s AND episode = %s AND scene = %s
                """,
                (season, episode, scene)
            )
            result = cur.fetchone()

            if result:
                return result["chunk_id"]
            else:
                logger.error(f"No chunk found for slug {chunk_slug}")
                return None

    def add_chunks_auto_character(self, character_id: int):
        """
        Automatically add all chunks that reference a specific character.
        
        Args:
            character_id: ID of the character
        """
        logger.info(f"Finding all chunks referencing character {character_id}...")
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all chunk IDs that reference this character
            cur.execute(
                """
                SELECT DISTINCT chunk_id 
                FROM chunk_character_references 
                WHERE character_id = %s
                ORDER BY chunk_id
                """,
                (character_id,)
            )
            
            chunk_ids = [row['chunk_id'] for row in cur.fetchall()]
            
            if not chunk_ids:
                logger.error(f"No chunks found referencing character {character_id}")
                return
                
            logger.info(f"Found {len(chunk_ids)} chunks referencing character {character_id}")
            self.add_chunks(chunk_ids)
    
    def add_chunks_auto_faction(self, faction_id: int):
        """
        Automatically add all chunks that reference a specific faction.
        
        Args:
            faction_id: ID of the faction
        """
        logger.info(f"Finding all chunks referencing faction {faction_id}...")
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all chunk IDs that reference this faction
            cur.execute(
                """
                SELECT DISTINCT chunk_id 
                FROM chunk_faction_references 
                WHERE faction_id = %s
                ORDER BY chunk_id
                """,
                (faction_id,)
            )
            
            chunk_ids = [row['chunk_id'] for row in cur.fetchall()]
            
            if not chunk_ids:
                logger.error(f"No chunks found referencing faction {faction_id}")
                return
                
            logger.info(f"Found {len(chunk_ids)} chunks referencing faction {faction_id}")
            self.add_chunks(chunk_ids)
    
    def add_episodes_auto_character(self, character_id: int, content_type: str = "raw"):
        """
        Automatically add all episodes that contain chunks referencing a specific character.
        
        Args:
            character_id: ID of the character
            content_type: Type of content to add ("raw" or "summary")
        """
        logger.info(f"Finding all episodes containing references to character {character_id}...")
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all chunk IDs that reference this character
            cur.execute(
                """
                SELECT DISTINCT chunk_id 
                FROM chunk_character_references 
                WHERE character_id = %s
                """,
                (character_id,)
            )
            
            chunk_ids = [row['chunk_id'] for row in cur.fetchall()]
            
            if not chunk_ids:
                logger.error(f"No chunks found referencing character {character_id}")
                return
            
            # Find all episodes that contain these chunks
            # We'll use the chunk_span range to find which episodes contain these chunks
            cur.execute(
                """
                SELECT DISTINCT season, episode, chunk_span
                FROM episodes
                WHERE chunk_span IS NOT NULL
                ORDER BY season, episode
                """
            )
            
            matching_episodes = []
            for row in cur.fetchall():
                chunk_span_str = str(row['chunk_span'])
                # Parse the range
                if chunk_span_str.startswith('[') and chunk_span_str.endswith(')'):
                    range_part = chunk_span_str[1:-1]
                    start_chunk, end_chunk = map(int, range_part.split(','))
                    
                    # Check if any of our chunk_ids fall within this range
                    for chunk_id in chunk_ids:
                        if start_chunk <= chunk_id < end_chunk:
                            episode_id = f"s{row['season']:02d}e{row['episode']:02d}"
                            if episode_id not in matching_episodes:
                                matching_episodes.append(episode_id)
                            break
            
            if not matching_episodes:
                logger.error(f"No episodes found containing references to character {character_id}")
                return
                
            logger.info(f"Found {len(matching_episodes)} episodes containing references to character {character_id}")
            # Add content for all matching episodes
            for episode_id in matching_episodes:
                if content_type == "raw":
                    self.add_episode_raw(episode_id)
                elif content_type == "summary":
                    self.add_episode_summary(episode_id)
    
    def add_episodes_auto_faction(self, faction_id: int, content_type: str = "raw"):
        """
        Automatically add all episodes that contain chunks referencing a specific faction.
        
        Args:
            faction_id: ID of the faction
            content_type: Type of content to add ("raw" or "summary")
        """
        logger.info(f"Finding all episodes containing references to faction {faction_id}...")
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all chunk IDs that reference this faction
            cur.execute(
                """
                SELECT DISTINCT chunk_id 
                FROM chunk_faction_references 
                WHERE faction_id = %s
                """,
                (faction_id,)
            )
            
            chunk_ids = [row['chunk_id'] for row in cur.fetchall()]
            
            if not chunk_ids:
                logger.error(f"No chunks found referencing faction {faction_id}")
                return
            
            # Find all episodes that contain these chunks
            cur.execute(
                """
                SELECT DISTINCT season, episode, chunk_span
                FROM episodes
                WHERE chunk_span IS NOT NULL
                ORDER BY season, episode
                """
            )
            
            matching_episodes = []
            for row in cur.fetchall():
                chunk_span_str = str(row['chunk_span'])
                # Parse the range
                if chunk_span_str.startswith('[') and chunk_span_str.endswith(')'):
                    range_part = chunk_span_str[1:-1]
                    start_chunk, end_chunk = map(int, range_part.split(','))
                    
                    # Check if any of our chunk_ids fall within this range
                    for chunk_id in chunk_ids:
                        if start_chunk <= chunk_id < end_chunk:
                            episode_id = f"s{row['season']:02d}e{row['episode']:02d}"
                            if episode_id not in matching_episodes:
                                matching_episodes.append(episode_id)
                            break
            
            if not matching_episodes:
                logger.error(f"No episodes found containing references to faction {faction_id}")
                return
                
            logger.info(f"Found {len(matching_episodes)} episodes containing references to faction {faction_id}")
            # Add content for all matching episodes
            for episode_id in matching_episodes:
                if content_type == "raw":
                    self.add_episode_raw(episode_id)
                elif content_type == "summary":
                    self.add_episode_summary(episode_id)

    def add_chunks(self, chunk_ids: Union[str, List[int]]):
        """
        Add specific chunks to their parent episodes.

        Args:
            chunk_ids: Chunk ID(s) (e.g., '33-34', '33,35,37', 's01e03c24', 's01e03c24-27')
        """
        # Parse chunk IDs
        chunk_id_list = []
        if isinstance(chunk_ids, str):
            # Handle slug format like "s01e03c24"
            if re.match(r"s\d+e\d+c\d+$", chunk_ids.lower()):
                chunk_id = self._parse_chunk_slug(chunk_ids)
                if chunk_id:
                    chunk_id_list = [chunk_id]
                else:
                    return
            # Handle slug range like "s01e03c24-27" (shorthand) or numeric range like "33-34"
            elif "-" in chunk_ids:
                parts = chunk_ids.split("-")
                if len(parts) == 2:
                    start_part, end_part = parts
                    
                    # Check if first part is a slug
                    start_match = re.match(r"s(\d+)e(\d+)c(\d+)", start_part.lower())
                    
                    if start_match:
                        # First part is a slug (shorthand range like "s01e03c24-27")
                        season = int(start_match.group(1))
                        episode = int(start_match.group(2))
                        
                        try:
                            # Second part should be just a chunk number
                            end_chunk_num = int(end_part)
                            # Construct the full end slug
                            full_end_slug = f"s{season:02d}e{episode:02d}c{end_chunk_num}"
                            start_id = self._parse_chunk_slug(start_part)
                            end_id = self._parse_chunk_slug(full_end_slug)
                            
                            if start_id and end_id:
                                if start_id <= end_id:
                                    chunk_id_list = list(range(start_id, end_id + 1))
                                    logger.debug(f"Shorthand range '{start_part}-{end_part}' resolved to chunk IDs: {chunk_id_list}")
                                else:
                                    logger.error(f"Invalid range: {start_part} (ID: {start_id}) is after c{end_chunk_num} (ID: {end_id})")
                                    return
                            else:
                                return
                        except ValueError:
                            logger.error(f"Invalid chunk range format: {chunk_ids}. For slug ranges, use format 's03e03c26-27'")
                            return
                    else:
                        # Try to parse as numeric range (e.g., "33-34")
                        try:
                            start, end = map(int, chunk_ids.split("-"))
                            chunk_id_list = list(range(start, end + 1))
                        except ValueError:
                            logger.error(f"Invalid chunk ID range format: {chunk_ids}")
                            return
            # Handle comma-separated list like "33,35,37" or "s01e03c24,s01e03c26"
            elif "," in chunk_ids:
                chunk_id_list = []
                for item in chunk_ids.split(","):
                    item = item.strip()
                    if re.match(r"s\d+e\d+c\d+$", item.lower()):
                        chunk_id = self._parse_chunk_slug(item)
                        if chunk_id:
                            chunk_id_list.append(chunk_id)
                    else:
                        try:
                            chunk_id_list.append(int(item))
                        except ValueError:
                            logger.error(f"Invalid chunk ID format: {item}")
                            return
            # Handle single chunk ID
            else:
                try:
                    chunk_id_list = [int(chunk_ids)]
                except ValueError:
                    logger.error(f"Invalid chunk ID format: {chunk_ids}")
                    return
        else:
            chunk_id_list = chunk_ids

        logger.debug(f"Final chunk_id_list: {chunk_id_list}")
        logger.info(f"Adding {len(chunk_id_list)} chunks...")

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get episodes for these chunks
            for chunk_id in chunk_id_list:
                # Get the chunk's parent episode by using a similar approach to what works in add_episode_raw
                # We'll directly query the database to find which episode's chunk_span contains this chunk ID
                # Use the chunk_metadata table to get season and episode directly
                cur.execute(
                    """
                    SELECT season, episode
                    FROM chunk_metadata
                    WHERE id = %s OR chunk_id = %s
                    """,
                    (chunk_id, chunk_id)
                )

                episode_data = cur.fetchone()

                if not episode_data:
                    logger.error(f"No parent episode found for chunk {chunk_id}")
                    continue

                season = episode_data["season"]
                episode = episode_data["episode"]
                episode_id = f"s{season:02d}e{episode:02d}"

                # Get the chunk's raw text
                cur.execute(
                    """
                    SELECT id, raw_text FROM narrative_chunks
                    WHERE id = %s
                    """,
                    (chunk_id,)
                )
                chunk = cur.fetchone()

                if not chunk:
                    logger.error(f"Chunk {chunk_id} not found")
                    continue

                # Create the episode entry if it doesn't exist
                if episode_id not in self.data["episodes"]:
                    self.data["episodes"][episode_id] = {}

                # Create or get the raw_text container
                if "raw_text" not in self.data["episodes"][episode_id]:
                    self.data["episodes"][episode_id]["raw_text"] = {}

                # Add the raw text for the chunk, using the chunk ID as the key
                chunk_id_str = str(chunk["id"])
                self.data["episodes"][episode_id]["raw_text"][chunk_id_str] = chunk["raw_text"]

                logger.info(f"Added chunk {chunk_id} to episode {episode_id}")

        self._update_and_save()

    def remove_chunks(self, chunk_ids: Union[str, List[int]]):
        """
        Remove specific chunks from their parent episodes.

        Args:
            chunk_ids: Chunk ID(s) (e.g., '33-34', '33,35,37', 's01e03c24', 's01e03c24-27')
        """
        # Parse chunk IDs from the string
        chunk_id_list = []
        if isinstance(chunk_ids, str):
            # Handle slug format like "s01e03c24"
            if re.match(r"s\d+e\d+c\d+$", chunk_ids.lower()):
                chunk_id = self._parse_chunk_slug(chunk_ids)
                if chunk_id:
                    chunk_id_list = [chunk_id]
                else:
                    return
            # Handle slug range like "s01e03c24-27" (shorthand) or numeric range like "33-34"
            elif "-" in chunk_ids:
                parts = chunk_ids.split("-")
                if len(parts) == 2:
                    start_part, end_part = parts
                    
                    # Check if first part is a slug
                    start_match = re.match(r"s(\d+)e(\d+)c(\d+)", start_part.lower())
                    
                    if start_match:
                        # First part is a slug (shorthand range like "s01e03c24-27")
                        season = int(start_match.group(1))
                        episode = int(start_match.group(2))
                        
                        try:
                            # Second part should be just a chunk number
                            end_chunk_num = int(end_part)
                            # Construct the full end slug
                            full_end_slug = f"s{season:02d}e{episode:02d}c{end_chunk_num}"
                            start_id = self._parse_chunk_slug(start_part)
                            end_id = self._parse_chunk_slug(full_end_slug)
                            
                            if start_id and end_id:
                                if start_id <= end_id:
                                    chunk_id_list = list(range(start_id, end_id + 1))
                                    logger.debug(f"Shorthand range '{start_part}-{end_part}' resolved to chunk IDs: {chunk_id_list}")
                                else:
                                    logger.error(f"Invalid range: {start_part} (ID: {start_id}) is after c{end_chunk_num} (ID: {end_id})")
                                    return
                            else:
                                return
                        except ValueError:
                            logger.error(f"Invalid chunk range format: {chunk_ids}. For slug ranges, use format 's03e03c26-27'")
                            return
                    else:
                        # Try to parse as numeric range (e.g., "33-34")
                        try:
                            start, end = map(int, chunk_ids.split("-"))
                            chunk_id_list = list(range(start, end + 1))
                        except ValueError:
                            logger.error(f"Invalid chunk ID range format: {chunk_ids}")
                            return
            # Handle comma-separated list like "33,35,37" or "s01e03c24,s01e03c26"
            elif "," in chunk_ids:
                chunk_id_list = []
                for item in chunk_ids.split(","):
                    item = item.strip()
                    if re.match(r"s\d+e\d+c\d+$", item.lower()):
                        chunk_id = self._parse_chunk_slug(item)
                        if chunk_id:
                            chunk_id_list.append(chunk_id)
                    else:
                        try:
                            chunk_id_list.append(int(item))
                        except ValueError:
                            logger.error(f"Invalid chunk ID format: {item}")
                            return
            # Handle single chunk ID
            else:
                try:
                    chunk_id_list = [int(chunk_ids)]
                except ValueError:
                    logger.error(f"Invalid chunk ID format: {chunk_ids}")
                    return
        else:
            chunk_id_list = chunk_ids

        logger.info(f"Removing {len(chunk_id_list)} chunks...")

        removed_count = 0

        # Go through every episode's raw_text to find and remove the chunks
        for episode_id, episode_data in list(self.data["episodes"].items()):
            if "raw_text" in episode_data:
                # Check if any chunks to remove are in this episode
                for chunk_id in chunk_id_list:
                    chunk_id_str = str(chunk_id)
                    if chunk_id_str in episode_data["raw_text"]:
                        logger.info(f"Removing chunk {chunk_id} from episode {episode_id}")
                        del episode_data["raw_text"][chunk_id_str]
                        removed_count += 1

                # If raw_text is now empty, remove it
                if not episode_data["raw_text"]:
                    del episode_data["raw_text"]

                # If episode is now empty, remove it
                if not episode_data:
                    del self.data["episodes"][episode_id]

        if removed_count > 0:
            self._update_and_save()
        else:
            logger.info("No chunks found to remove")

    def handle_command(self, command: str):
        """
        Handle a command from the user.
        
        Args:
            command: Command string
        """
        # Parse the command
        if command.lower() in ["exit", "quit"]:
            logger.info("Exiting...")
            sys.exit(0)
            
        parts = command.split()
        
        if not parts:
            return
            
        action = parts[0].lower()
        
        if action == "add":
            if len(parts) < 2:
                logger.error("Invalid add command. Format: add <type> [<id>] [<field>]")
                return

            obj_type = parts[1].lower()

            # Special handling for chunk command which needs fewer parameters
            if obj_type == "chunk" or obj_type == "chunks":
                if len(parts) < 3:
                    logger.error("Invalid add chunk command. Format: add chunk <id/range> or add chunk auto <character/faction> <id>")
                    return
                
                # Check if this is an auto command
                if parts[2].lower() == "auto":
                    if len(parts) < 5:
                        logger.error("Invalid add chunk auto command. Format: add chunk auto <character/faction> <id>")
                        return
                    
                    entity_type = parts[3].lower()
                    try:
                        entity_id = int(parts[4])
                        
                        if entity_type == "character":
                            self.add_chunks_auto_character(entity_id)
                        elif entity_type == "faction":
                            self.add_chunks_auto_faction(entity_id)
                        else:
                            logger.error(f"Invalid entity type for auto chunk: {entity_type}. Use 'character' or 'faction'.")
                    except ValueError:
                        logger.error(f"Invalid entity ID: {parts[4]}")
                else:
                    # Regular chunk add
                    chunk_ids = parts[2]
                    self.add_chunks(chunk_ids)
                return

            # For other commands, require 4 parts
            if len(parts) < 4:
                logger.error("Invalid add command. Format: add <type> <id> <field>")
                return

            obj_ids_str = parts[2]
            fields_str = parts[3]
            
            # Parse comma-separated IDs
            obj_ids = []
            for id_str in obj_ids_str.split(','):
                id_str = id_str.strip()
                if obj_type in ["character", "place", "season", "faction"]:
                    try:
                        obj_ids.append(int(id_str))
                    except ValueError:
                        logger.error(f"Invalid {obj_type} ID: {id_str}")
                        return
                else:
                    obj_ids.append(id_str)
            
            # Parse comma-separated fields
            fields = [f.strip() for f in fields_str.split(',')]
            
            if obj_type == "character":
                for char_id in obj_ids:
                    for field in fields:
                        self.add_character_field(char_id, field)
                    
            elif obj_type == "place":
                for place_id in obj_ids:
                    for field in fields:
                        self.add_place_field(place_id, field)
                    
            elif obj_type == "season":
                # Check if this is "add season summary all"
                if len(obj_ids) == 1 and obj_ids_str.lower() == "summary" and fields_str.lower() == "all":
                    # Get all seasons from database
                    with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute("SELECT id FROM seasons ORDER BY id")
                        seasons = cur.fetchall()
                    
                    if not seasons:
                        logger.error("No seasons found in database")
                        return
                    
                    logger.info(f"Adding summaries for {len(seasons)} seasons...")
                    for season in seasons:
                        self.add_season_field(season['id'], 'summary')
                else:
                    for season_id in obj_ids:
                        for field in fields:
                            self.add_season_field(season_id, field)
                    
            elif obj_type == "faction":
                for faction_id in obj_ids:
                    for field in fields:
                        self.add_faction_field(faction_id, field)
                    
            elif obj_type == "episode":
                if len(parts) < 3:
                    logger.error("Invalid add episode command. Format: add episode <summary/raw> <id>")
                    return

                field = parts[2].lower()

                if field == "summary":
                    # Check if this is an auto command
                    if len(parts) > 3 and parts[3].lower() == "auto":
                        if len(parts) < 6:
                            logger.error("Invalid add episode summary auto command. Format: add episode summary auto <character/faction> <id>")
                            return
                        
                        entity_type = parts[4].lower()
                        try:
                            entity_id = int(parts[5])
                            
                            if entity_type == "character":
                                self.add_episodes_auto_character(entity_id, "summary")
                            elif entity_type == "faction":
                                self.add_episodes_auto_faction(entity_id, "summary")
                            else:
                                logger.error(f"Invalid entity type for auto episode: {entity_type}. Use 'character' or 'faction'.")
                        except ValueError:
                            logger.error(f"Invalid entity ID: {parts[5]}")
                    else:
                        # The remaining arguments form the episode range
                        if len(parts) > 3:
                            episode_range = " ".join(parts[3:])
                            self.add_episode_summary(episode_range)
                        else:
                            logger.error("Missing episode identifier. Format: add episode summary <id/range/all>")
                elif field == "raw":
                    # Check if this is an auto command
                    if len(parts) > 3 and parts[3].lower() == "auto":
                        if len(parts) < 6:
                            logger.error("Invalid add episode raw auto command. Format: add episode raw auto <character/faction> <id>")
                            return
                        
                        entity_type = parts[4].lower()
                        try:
                            entity_id = int(parts[5])
                            
                            if entity_type == "character":
                                self.add_episodes_auto_character(entity_id, "raw")
                            elif entity_type == "faction":
                                self.add_episodes_auto_faction(entity_id, "raw")
                            else:
                                logger.error(f"Invalid entity type for auto episode: {entity_type}. Use 'character' or 'faction'.")
                        except ValueError:
                            logger.error(f"Invalid entity ID: {parts[5]}")
                    else:
                        # The remaining arguments form the episode range
                        if len(parts) > 3:
                            episode_range = " ".join(parts[3:])
                            self.add_episode_raw(episode_range)
                        else:
                            logger.error("Missing episode identifier. Format: add episode raw <id/range/all>")
                else:
                    logger.error(f"Invalid episode field: {field}. Use 'summary' or 'raw'.")
                    
            else:
                logger.error(f"Unknown object type: {obj_type}")
                
        elif action == "rm" or action == "remove":
            if len(parts) < 2:
                logger.error("Invalid remove command. Format: rm <type> <id> [<field>]")
                return

            obj_type = parts[1].lower()

            # Special handling for chunk command which needs fewer parameters
            if obj_type == "chunk" or obj_type == "chunks":
                if len(parts) < 3:
                    logger.error("Invalid remove chunk command. Format: rm chunk <id/range>")
                    return
                # The third argument is the chunk ID or range
                chunk_ids = parts[2]
                self.remove_chunks(chunk_ids)
                return

            # For other commands, require at least 3 parts
            if len(parts) < 4:
                logger.error("Invalid remove command. Format: rm <type> <id> <field>")
                return

            obj_ids_str = parts[2]
            fields_str = parts[3]
            
            # Parse comma-separated IDs
            obj_ids = []
            for id_str in obj_ids_str.split(','):
                id_str = id_str.strip()
                if obj_type in ["character", "place", "season", "faction"]:
                    try:
                        obj_ids.append(int(id_str))
                    except ValueError:
                        logger.error(f"Invalid {obj_type} ID: {id_str}")
                        return
                else:
                    obj_ids.append(id_str)
            
            # Parse comma-separated fields
            fields = [f.strip() for f in fields_str.split(',')]
            
            if obj_type == "character":
                for char_id in obj_ids:
                    for field in fields:
                        self.remove_character_field(char_id, field)
                    
            elif obj_type == "place":
                for place_id in obj_ids:
                    for field in fields:
                        self.remove_place_field(place_id, field)
                    
            elif obj_type == "season":
                for season_id in obj_ids:
                    for field in fields:
                        self.remove_season_field(season_id, field)
                    
            elif obj_type == "faction":
                for faction_id in obj_ids:
                    for field in fields:
                        self.remove_faction_field(faction_id, field)
                    
            elif obj_type == "episode":
                if len(parts) < 4:
                    logger.error("Invalid remove episode command. Format: rm episode <summary/raw> <id>")
                    return

                content_type = parts[2].lower()
                episode_id = parts[3]

                # Format check for episode ID
                if not re.match(r"s\d+e\d+", episode_id.lower()):
                    logger.error(f"Invalid episode identifier format: {episode_id}")
                    return

                # Check if episode exists in the context
                if episode_id not in self.data["episodes"]:
                    logger.error(f"Episode {episode_id} not found in context")
                    return

                if content_type == "summary":
                    # Remove summary if it exists
                    if "summary" in self.data["episodes"][episode_id]:
                        logger.info(f"Removing summary for episode {episode_id}")
                        del self.data["episodes"][episode_id]["summary"]

                        # If episode is now empty, remove it entirely
                        if not self.data["episodes"][episode_id]:
                            del self.data["episodes"][episode_id]

                        self._update_and_save()
                    else:
                        logger.error(f"No summary found for episode {episode_id}")

                elif content_type == "raw":
                    # Remove raw text if it exists
                    if "raw_text" in self.data["episodes"][episode_id]:
                        logger.info(f"Removing raw text for episode {episode_id}")
                        del self.data["episodes"][episode_id]["raw_text"]

                        # If episode is now empty, remove it entirely
                        if not self.data["episodes"][episode_id]:
                            del self.data["episodes"][episode_id]

                        self._update_and_save()
                    else:
                        logger.error(f"No raw text found for episode {episode_id}")

                else:
                    logger.error(f"Invalid episode content type: {content_type}. Use 'summary' or 'raw'.")
                
            else:
                logger.error(f"Unknown object type: {obj_type}")
                
        elif action == "tokens":
            # Display current token count
            tokens = self._calculate_tokens()
            logger.info(f"Current token count: {tokens:,}")
            
        elif action == "help":
            print_help()
            
        else:
            logger.error(f"Unknown command: {action}")


def print_help():
    """Print help information."""
    help_text = """
Context Assembler Commands:

Adding Content:
  add character <id> <field>        Add a character field
  add character <id,id,...> <field> Add a field to multiple characters
  add character <id> <field,field,...> Add multiple fields to a character
  add place <id> <field>            Add a place field
  add place <id,id,...> <field,field,...> Add multiple fields to multiple places
  add season <id> <field>           Add a season field
  add season <id,id,...> <field,field,...> Add multiple fields to multiple seasons
  add season summary all            Add summaries for all seasons
  add faction <id> <field>          Add a faction field
  add faction <id,id,...> <field,field,...> Add multiple fields to multiple factions
  add episode summary <id>          Add episode summary
  add episode summary <range>       Add episode summaries (range format: s01e01-s01e06)
  add episode summary <list>        Add episode summaries (list format: s01e01,s01e03)
  add episode summary all           Add all episode summaries
  add episode raw <id>              Add raw episode content
  add episode raw all               Add all raw episode content
  add episode summary auto character <id>   Add summaries of episodes referencing character
  add episode summary auto faction <id>     Add summaries of episodes referencing faction
  add episode raw auto character <id>      Add raw text of episodes referencing character
  add episode raw auto faction <id>        Add raw text of episodes referencing faction
  add chunk <id/range>              Add specific chunks by ID (e.g., 33-34)
  add chunk <slug>                  Add specific chunk by slug (e.g., s01e03c24)
  add chunk <slug-range>            Add chunk range using shorthand (e.g., s01e03c24-27)
  add chunk auto character <id>     Add all chunks that reference a character
  add chunk auto faction <id>       Add all chunks that reference a faction

Removing Content:
  rm character <id> <field>         Remove a character field
  rm character <id,id,...> <field,field,...> Remove multiple fields from multiple characters
  rm place <id> <field>             Remove a place field
  rm place <id,id,...> <field,field,...> Remove multiple fields from multiple places
  rm season <id> <field>            Remove a season field
  rm season <id,id,...> <field,field,...> Remove multiple fields from multiple seasons
  rm faction <id> <field>           Remove a faction field
  rm faction <id,id,...> <field,field,...> Remove multiple fields from multiple factions
  rm episode summary <id>           Remove an episode's summary
  rm episode raw <id>               Remove an episode's raw text
  rm chunk <id/range>               Remove specific chunks by ID (e.g., 33-34)
  rm chunk <slug>                   Remove specific chunk by slug (e.g., s01e03c24)
  rm chunk <slug-range>             Remove chunk range using shorthand (e.g., s01e03c24-27)

Other Commands:
  tokens                            Show current token count
  help                              Show this help
  exit                              Exit the program
"""
    print(help_text)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Context Assembler")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--new", help="Create a new context package with this name")
    group.add_argument("--load", help="Load an existing context package")
    
    args = parser.parse_args()
    
    if args.new:
        # Check if file already exists
        if os.path.exists(args.new):
            overwrite = input(f"File {args.new} already exists. Overwrite? (y/n): ")
            if overwrite.lower() != 'y':
                logger.info("Operation canceled")
                sys.exit(0)
        assembler = ContextAssembler(args.new, new=True)
    else:
        assembler = ContextAssembler(args.load, new=False)
    
    print_help()
    
    try:
        while True:
            try:
                command = input("\n> ")
                assembler.handle_command(command)
            except KeyboardInterrupt:
                print("\nUse 'exit' to quit")
    except EOFError:
        logger.info("\nExiting...")


if __name__ == "__main__":
    main()