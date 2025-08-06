#!/usr/bin/env python3
"""
Location Mapping Script for NEXUS

This script analyzes narrative chunks and identifies all location references,
categorizing them as 'setting', 'mentioned', or 'transit'. It stores these
references in a database table to enable richer location-based narrative
retrieval.

Usage Examples:
    # Test mode to show prompt and predicted API call for first chunk in episode 1
    python map_builder.py --test --episode s01e01
    
    # Process episode 5 of season 1
    python map_builder.py --episode s01e05
    
    # Process a range of episodes
    python map_builder.py --episode s01e05 s01e07
    
    # Process specific chunks (comma-separated or range)
    python map_builder.py --chunk 100,101,102
    python map_builder.py --chunk 100-110
    
    # Process all chunks
    python map_builder.py --all
    
    # Process with overwrite option (even if references already exist)
    python map_builder.py --episode s02e03 --overwrite

Features:
    - Creates a new 'place_chunk_references' table if it doesn't exist
    - Processes by episodes to provide better context for location identification
    - Identifies multiple location references per chunk with evidence
    - Allows manual confirmation for new location suggestions
    - Uses OpenAI API with structured outputs
"""

import os
import sys
import re
import json
import argparse
import logging
from typing import List, Dict, Any, Tuple, Optional, Set, Union
from enum import Enum
import time
from pathlib import Path
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from pydantic import BaseModel, Field

# Import from api_openai.py
try:
    from api_openai import OpenAIProvider, get_db_connection_string
except ImportError as e:
    print(f"Error importing from api_openai.py: {e}")
    print("Make sure api_openai.py is in the same directory.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("map_builder.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("map_builder")

# Default model to use
DEFAULT_MODEL = "gpt-4.1"

# Note: place_reference_type enum and place_chunk_references table 
# were created directly in the database

# Database table names
NARRATIVE_CHUNKS_TABLE = "narrative_chunks"
CHUNK_METADATA_TABLE = "chunk_metadata"
PLACES_TABLE = "places"
ZONES_TABLE = "zones"
REFERENCES_TABLE = "place_chunk_references"


class ReferenceType(str, Enum):
    """Enum for types of place references in narrative chunks.
    Must match the database enum 'place_reference_type'."""
    SETTING = "setting"     # Location serves as the primary setting for action
    MENTIONED = "mentioned" # Location is referenced but not where action occurs
    TRANSIT = "transit"     # Location is passed through but not stopped at


class PlaceType(str, Enum):
    """Enum for types of places in the database."""
    FIXED_LOCATION = "fixed_location"
    VEHICLE = "vehicle"
    OTHER = "other"


class NarrativeChunk:
    """Represents a narrative chunk."""
    def __init__(self, id: int, raw_text: str, season: Optional[int] = None, 
                 episode: Optional[int] = None, scene: Optional[int] = None):
        self.id = id
        self.raw_text = raw_text
        self.season = season
        self.episode = episode
        self.scene = scene
        
    def __str__(self) -> str:
        if self.season is not None and self.episode is not None:
            return f"Chunk {self.id} (S{self.season:02d}E{self.episode:02d})"
        return f"Chunk {self.id}"


class Place:
    """Represents a place from the database."""
    def __init__(self, id: int, name: str, type: str, zone: int, 
                 zone_name: str, summary: Optional[str] = None):
        self.id = id
        self.name = name
        self.type = type
        self.zone = zone
        self.zone_name = zone_name
        self.summary = summary
    
    def __str__(self) -> str:
        return f"{self.name} (ID: {self.id}, Zone: {self.zone_name})"


class Zone:
    """Represents a zone from the database."""
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name
    
    def __str__(self) -> str:
        return f"{self.name} (ID: {self.id})"


class EpisodeSlugParser:
    """Parse and validate episode slugs like 's01e05'."""
    
    @staticmethod
    def parse(slug: str) -> Tuple[int, int]:
        """
        Parse an episode slug string into season and episode numbers.
        
        Args:
            slug: Episode slug string like 's01e05'
            
        Returns:
            Tuple of (season_number, episode_number)
            
        Raises:
            ValueError: If the slug format is invalid
        """
        pattern = r'^s(\d{1,2})e(\d{1,2})$'
        match = re.match(pattern, slug.lower())
        
        if not match:
            raise ValueError(f"Invalid episode slug format: {slug}. Expected format: s01e05")
            
        season = int(match.group(1))
        episode = int(match.group(2))
        
        return season, episode
    
    @staticmethod
    def format(season: int, episode: int) -> str:
        """
        Format season and episode numbers into a slug.
        
        Args:
            season: Season number
            episode: Episode number
            
        Returns:
            Formatted slug like 's01e05'
        """
        return f"s{season:02d}e{episode:02d}"
    
    @staticmethod
    def validate_range(start_slug: str, end_slug: str) -> bool:
        """
        Validate that end_slug comes after start_slug.
        
        Args:
            start_slug: Starting episode slug
            end_slug: Ending episode slug
            
        Returns:
            True if valid range, False otherwise
        """
        start_season, start_episode = EpisodeSlugParser.parse(start_slug)
        end_season, end_episode = EpisodeSlugParser.parse(end_slug)
        
        if start_season > end_season:
            return False
        
        if start_season == end_season and start_episode > end_episode:
            return False
            
        return True


# Pydantic models for structured output
class PlaceReference(BaseModel):
    """A reference to a place in the narrative."""
    place_id: int = Field(description="ID of the existing place being referenced")
    reference_type: ReferenceType = Field(description="Type of reference")
    evidence: str = Field(description="Text excerpt from the chunk that supports this reference identification")


class NewPlaceSuggestion(BaseModel):
    """A suggestion for a new place to add to the database."""
    name: str = Field(description="Name of the proposed new place")
    type: PlaceType = Field(description="Type of place")
    zone_id: int = Field(description="ID of the zone this place belongs to")
    summary: str = Field(description="Brief description of the place")
    reference_type: ReferenceType = Field(description="How this place is referenced")
    evidence: str = Field(description="Text excerpt from the chunk that supports this place identification")


class LocationAnalysisResult(BaseModel):
    """The complete result of analyzing locations in narrative chunks."""
    known_places: List[PlaceReference] = Field(description="References to places already in the database")
    new_places: List[NewPlaceSuggestion] = Field(description="Suggestions for new places to add to the database")
    
    class Config:
        extra = "forbid"  # No additional properties allowed


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract and associate location information with narrative chunks.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # OpenAI API options
    api_group = parser.add_argument_group("OpenAI API Options")
    api_group.add_argument("--model", default=DEFAULT_MODEL,
                          help=f"Model to use (default: {DEFAULT_MODEL})")
    api_group.add_argument("--api-key", help="OpenAI API key (optional, defaults to environment variable)")
    api_group.add_argument("--temperature", type=float, default=0.1,
                          help="Temperature setting (0.0-1.0, default: 0.1)")
    api_group.add_argument("--effort", choices=["low", "medium", "high"], default="medium",
                         help="Reasoning effort for o-prefixed models (default: medium)")
    
    # Database options
    db_group = parser.add_argument_group("Database Options")
    db_group.add_argument("--db-url", help="Database connection URL (optional)")
    
    # Processing options
    process_group = parser.add_argument_group("Processing Options")
    process_group.add_argument("--test", action="store_true",
                              help="Test mode - show prompt and predict API call without making the actual call")
    process_group.add_argument("--dry-run", action="store_true",
                              help="Process chunks but don't write results to database")
    process_group.add_argument("--overwrite", action="store_true",
                              help="Process chunks that already have place references")
    
    # Chunk selection options (mutually exclusive)
    chunk_group = parser.add_argument_group("Chunk Selection")
    selection = chunk_group.add_mutually_exclusive_group(required=True)
    selection.add_argument("--chunk", help="Process specific chunks (ID, comma-separated list, or range with hyphen)")
    selection.add_argument("--episode", nargs='+', help="Process an episode (e.g., s01e05) or range (e.g., s01e01 s01e03)")
    selection.add_argument("--all", action="store_true", help="Process all chunks in the database")
    
    args = parser.parse_args()
    
    # Set log level
    logger.setLevel(logging.DEBUG if args.test else logging.INFO)
    
    return args


def connect_to_database(db_url: Optional[str] = None) -> Engine:
    """
    Connect to the NEXUS database.
    
    Args:
        db_url: Optional database URL override
        
    Returns:
        SQLAlchemy engine for database connection
    """
    # Get connection string if not provided
    if not db_url:
        db_url = get_db_connection_string()
    
    try:
        engine = create_engine(db_url)
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            logger.debug(f"Connected to PostgreSQL: {version}")
        return engine
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise


def check_place_references_table_exists(engine: Engine) -> bool:
    """
    Check if the place_chunk_references table and place_reference_type enum exist.
    
    Args:
        engine: Database connection engine
        
    Returns:
        True if table and enum exist, False otherwise
    """
    try:
        # Check if the enum type exists
        with engine.connect() as conn:
            enum_exists = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'place_reference_type')"
            )).scalar()
            
            if not enum_exists:
                logger.error("place_reference_type enum does not exist. Run the database setup script first.")
                return False
            
            # Check if the table exists
            table_exists = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'place_chunk_references')"
            )).scalar()
            
            if not table_exists:
                logger.error("place_chunk_references table does not exist. Run the database setup script first.")
                return False
                
        return True
    except Exception as e:
        logger.error(f"Error checking if place_chunk_references table exists: {e}")
        return False


def get_chunks_to_process(
    engine: Engine, 
    args: argparse.Namespace
) -> List[NarrativeChunk]:
    """
    Get the narrative chunks to process based on command line arguments.
    
    Args:
        engine: Database connection engine
        args: Command line arguments
        
    Returns:
        List of NarrativeChunk objects to process
    """
    chunks = []
    
    # Process by episode
    if args.episode:
        if len(args.episode) == 1:
            # Single episode
            season, episode = EpisodeSlugParser.parse(args.episode[0])
            chunks = get_episode_chunks(engine, season, episode, args.overwrite)
        elif len(args.episode) == 2:
            # Episode range
            start_slug, end_slug = args.episode
            if not EpisodeSlugParser.validate_range(start_slug, end_slug):
                logger.error(f"Invalid episode range: {start_slug} to {end_slug}")
                return []
                
            # Process all episodes in the range
            season_start, episode_start = EpisodeSlugParser.parse(start_slug)
            season_end, episode_end = EpisodeSlugParser.parse(end_slug)
            chunks = get_episode_range_chunks(
                engine, 
                season_start, episode_start, 
                season_end, episode_end,
                args.overwrite
            )
        else:
            logger.error("When using --episode, provide either one episode or a range of two episodes")
            return []
    
    # Process by chunk IDs
    elif args.chunk:
        chunks = get_specific_chunks(engine, args.chunk, args.overwrite)
    
    # Process all chunks
    elif args.all:
        chunks = get_all_chunks(engine, args.overwrite)
    
    logger.info(f"Retrieved {len(chunks)} chunks to process")
    return chunks


def get_episode_chunks(
    engine: Engine, 
    season: int, 
    episode: int, 
    include_processed: bool = False,
    surrounding_context: bool = False
) -> List[NarrativeChunk]:
    """
    Get all chunks for a specific episode, optionally including context chunks from surrounding episodes.
    
    Args:
        engine: Database connection engine
        season: Season number
        episode: Episode number
        include_processed: Whether to include chunks that already have place references
        surrounding_context: Whether to include chunks from adjacent episodes for context
        
    Returns:
        List of NarrativeChunk objects
    """
    # Base query for the current episode
    episode_query = """
    SELECT nc.id, nc.raw_text, cm.season, cm.episode, cm.scene
    FROM narrative_chunks nc
    JOIN chunk_metadata cm ON nc.id = cm.chunk_id
    WHERE cm.season = :season AND cm.episode = :episode
    """
    
    # If not including already processed chunks, add a WHERE clause
    if not include_processed:
        episode_query += """
        AND NOT EXISTS (
            SELECT 1 FROM place_chunk_references pcr 
            WHERE pcr.chunk_id = nc.id
        )
        """
    
    episode_query += " ORDER BY nc.id"
    
    # Log the query for debugging purposes
    logger.debug(f"Episode chunks query: {episode_query}")
    
    # Get chunks for the current episode
    chunks = []
    with engine.connect() as conn:
        result = conn.execute(text(episode_query), {"season": season, "episode": episode})
        for row in result:
            chunks.append(NarrativeChunk(
                id=row.id,
                raw_text=row.raw_text,
                season=row.season,
                episode=row.episode,
                scene=row.scene
            ))
    
    # Log the chunk IDs for the episode
    chunk_ids = [str(chunk.id) for chunk in chunks]
    logger.debug(f"Retrieved chunks for S{season:02d}E{episode:02d}: {', '.join(chunk_ids)}")
    logger.info(f"Retrieved {len(chunks)} chunks for S{season:02d}E{episode:02d}")
    
    # If surrounding context is requested, add previous and next episode chunks for context
    if surrounding_context and chunks:
        # Get previous episode context
        prev_season = season
        prev_episode = episode - 1
        if prev_episode < 1:
            prev_episode = 1  # Ensure we don't go below episode 1
            prev_season = max(1, season - 1)  # May go to previous season
        
        # Get next episode context
        next_season = season
        next_episode = episode + 1
        
        # Add one chunk from previous episode as context if available
        prev_query = """
        SELECT nc.id, nc.raw_text, cm.season, cm.episode, cm.scene
        FROM narrative_chunks nc
        JOIN chunk_metadata cm ON nc.id = cm.chunk_id
        WHERE (cm.season = :prev_season AND cm.episode = :prev_episode)
        ORDER BY nc.id DESC
        LIMIT 1
        """
        
        # Add one chunk from next episode as context if available
        next_query = """
        SELECT nc.id, nc.raw_text, cm.season, cm.episode, cm.scene
        FROM narrative_chunks nc
        JOIN chunk_metadata cm ON nc.id = cm.chunk_id
        WHERE (cm.season = :next_season AND cm.episode = :next_episode)
        ORDER BY nc.id ASC
        LIMIT 1
        """
        
        logger.debug(f"Fetching context: Prev S{prev_season:02d}E{prev_episode:02d}, Next S{next_season:02d}E{next_episode:02d}")
        
        # Get previous episode context chunk
        with engine.connect() as conn:
            prev_result = conn.execute(text(prev_query), {
                "prev_season": prev_season, 
                "prev_episode": prev_episode
            })
            for row in prev_result:
                leading_chunk = NarrativeChunk(
                    id=row.id,
                    raw_text=row.raw_text,
                    season=row.season,
                    episode=row.episode,
                    scene=row.scene
                )
                logger.debug(f"Added leading context chunk {leading_chunk.id} from S{leading_chunk.season:02d}E{leading_chunk.episode:02d}")
                chunks.insert(0, leading_chunk)  # Add at beginning
            
        # Get next episode context chunk
        with engine.connect() as conn:
            next_result = conn.execute(text(next_query), {
                "next_season": next_season, 
                "next_episode": next_episode
            })
            for row in next_result:
                trailing_chunk = NarrativeChunk(
                    id=row.id,
                    raw_text=row.raw_text,
                    season=row.season,
                    episode=row.episode,
                    scene=row.scene
                )
                logger.debug(f"Added trailing context chunk {trailing_chunk.id} from S{trailing_chunk.season:02d}E{trailing_chunk.episode:02d}")
                chunks.append(trailing_chunk)  # Add at end
    
    return chunks


def get_episode_range_chunks(
    engine: Engine,
    season_start: int,
    episode_start: int,
    season_end: int,
    episode_end: int,
    include_processed: bool = False
) -> List[NarrativeChunk]:
    """
    Get all chunks in a range of episodes.
    
    Args:
        engine: Database connection engine
        season_start: Starting season number
        episode_start: Starting episode number
        season_end: Ending season number
        episode_end: Ending episode number
        include_processed: Whether to include chunks that already have place references
        
    Returns:
        List of NarrativeChunk objects
    """
    chunks = []
    
    # Process each season
    for season in range(season_start, season_end + 1):
        # Determine episode range for this season
        if season == season_start:
            ep_start = episode_start
        else:
            ep_start = 1
            
        if season == season_end:
            ep_end = episode_end
        else:
            # Get the highest episode number for this season
            with engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT MAX(episode) FROM chunk_metadata WHERE season = :season"
                ), {"season": season})
                ep_end = result.scalar() or 1
        
        # Process each episode in this season
        for episode in range(ep_start, ep_end + 1):
            episode_chunks = get_episode_chunks(engine, season, episode, include_processed)
            chunks.extend(episode_chunks)
    
    return chunks


def get_specific_chunks(
    engine: Engine, 
    chunk_ids: str, 
    include_processed: bool = False
) -> List[NarrativeChunk]:
    """
    Get specific chunks based on a chunk ID string.
    
    Args:
        engine: Database connection engine
        chunk_ids: String with comma-separated chunk IDs, a range (e.g., "100-110"), or "all"
        include_processed: Whether to include chunks that already have place references
        
    Returns:
        List of NarrativeChunk objects
    """
    base_query = """
    SELECT nc.id, nc.raw_text, cm.season, cm.episode, cm.scene
    FROM narrative_chunks nc
    LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
    """
    
    # Process filtering
    if not include_processed:
        filter_condition = """
        AND NOT EXISTS (
            SELECT 1 FROM place_chunk_references pcr 
            WHERE pcr.chunk_id = nc.id
        )
        """
    else:
        filter_condition = ""
    
    # Process chunk ID specification
    if chunk_ids.lower() == "all":
        # All chunks
        query = base_query + filter_condition + " ORDER BY nc.id"
        params = {}
    elif "," in chunk_ids:
        # Comma-separated list
        id_list = [id.strip() for id in chunk_ids.split(",")]
        query = base_query + f" WHERE nc.id IN :id_list" + filter_condition + " ORDER BY nc.id"
        params = {"id_list": tuple(id_list)}
    elif "-" in chunk_ids:
        # Range
        start, end = map(int, chunk_ids.split("-"))
        query = base_query + f" WHERE nc.id >= :start AND nc.id <= :end" + filter_condition + " ORDER BY nc.id"
        params = {"start": start, "end": end}
    else:
        # Single ID
        query = base_query + f" WHERE nc.id = :id" + filter_condition + " ORDER BY nc.id"
        params = {"id": int(chunk_ids.strip())}
    
    chunks = []
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        for row in result:
            chunks.append(NarrativeChunk(
                id=row.id,
                raw_text=row.raw_text,
                season=row.season if hasattr(row, 'season') else None,
                episode=row.episode if hasattr(row, 'episode') else None,
                scene=row.scene if hasattr(row, 'scene') else None
            ))
    
    return chunks


def get_all_chunks(engine: Engine, include_processed: bool = False) -> List[NarrativeChunk]:
    """
    Get all narrative chunks, optionally filtering already processed chunks.
    
    Args:
        engine: Database connection engine
        include_processed: Whether to include chunks that already have place references
        
    Returns:
        List of NarrativeChunk objects
    """
    return get_specific_chunks(engine, "all", include_processed)


def get_places_grouped_by_zone(engine: Engine) -> Dict[Zone, List[Place]]:
    """
    Get all places from the database, grouped by zone.
    
    Args:
        engine: Database connection engine
        
    Returns:
        Dictionary mapping Zone objects to lists of Place objects
    """
    query = """
    SELECT p.id, p.name, p.type, p.summary, p.zone, z.name as zone_name
    FROM places p
    JOIN zones z ON p.zone = z.id
    ORDER BY z.name, p.name
    """
    
    places_by_zone = {}
    zones = {}
    
    with engine.connect() as conn:
        result = conn.execute(text(query))
        for row in result:
            # Create or retrieve Zone object
            if row.zone not in zones:
                zones[row.zone] = Zone(id=row.zone, name=row.zone_name)
                places_by_zone[zones[row.zone]] = []
            
            # Create Place object and add to the appropriate zone's list
            place = Place(
                id=row.id,
                name=row.name,
                type=row.type,
                zone=row.zone,
                zone_name=row.zone_name,
                summary=row.summary
            )
            places_by_zone[zones[row.zone]].append(place)
    
    logger.info(f"Retrieved {sum(len(places) for places in places_by_zone.values())} places in {len(places_by_zone)} zones")
    return places_by_zone


def get_place_references_for_chunk(engine: Engine, chunk_id: int) -> List[Dict[str, Any]]:
    """
    Get existing place references for a chunk.
    
    Args:
        engine: Database connection engine
        chunk_id: ID of the chunk
        
    Returns:
        List of place reference dictionaries
    """
    query = """
    SELECT pcr.place_id, p.name as place_name, pcr.reference_type, pcr.evidence,
           z.id as zone_id, z.name as zone_name
    FROM place_chunk_references pcr
    JOIN places p ON pcr.place_id = p.id
    JOIN zones z ON p.zone = z.id
    WHERE pcr.chunk_id = :chunk_id
    """
    
    references = []
    with engine.connect() as conn:
        result = conn.execute(text(query), {"chunk_id": chunk_id})
        for row in result:
            references.append(dict(row._mapping))
    
    return references


def create_new_place(
    engine: Engine, 
    suggestion: NewPlaceSuggestion,
    manual_id: Optional[int] = None
) -> Optional[Place]:
    """
    Create a new place in the database based on a suggestion.
    
    Args:
        engine: Database connection engine
        suggestion: The new place suggestion
        manual_id: Optional manually assigned ID for the place
        
    Returns:
        The newly created Place object, or None if creation failed
    """
    if manual_id is not None:
        # Use the manually provided ID
        query = """
        INSERT INTO places (id, name, type, zone, summary)
        VALUES (:id, :name, :type, :zone, :summary)
        RETURNING id
        """
        params = {
            "id": manual_id,
            "name": suggestion.name,
            "type": suggestion.type.value,  # Use the enum value
            "zone": suggestion.zone_id,
            "summary": suggestion.summary
        }
    else:
        # Let the database assign an ID using the sequence
        query = """
        INSERT INTO places (name, type, zone, summary)
        VALUES (:name, :type, :zone, :summary)
        RETURNING id
        """
        params = {
            "name": suggestion.name,
            "type": suggestion.type.value,  # Use the enum value
            "zone": suggestion.zone_id,
            "summary": suggestion.summary
        }
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            conn.commit()
            place_id = result.scalar()
            
            # Get zone name for the new Place object
            zone_query = "SELECT name FROM zones WHERE id = :zone_id"
            zone_result = conn.execute(text(zone_query), {"zone_id": suggestion.zone_id})
            zone_name = zone_result.scalar() or "Unknown Zone"
            
            return Place(
                id=place_id,
                name=suggestion.name,
                type=suggestion.type.value,
                zone=suggestion.zone_id,
                zone_name=zone_name,
                summary=suggestion.summary
            )
    except Exception as e:
        logger.error(f"Error creating new place: {e}")
        return None


def add_place_references(
    engine: Engine, 
    chunk_id: int,
    references: List[Tuple[int, str, str]]
) -> bool:
    """
    Add references between places and a chunk to the database.
    
    Args:
        engine: Database connection engine
        chunk_id: ID of the chunk
        references: List of tuples (place_id, reference_type, evidence)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with engine.connect() as conn:
            for place_id, reference_type, evidence in references:
                # Use a safer approach without f-strings in SQL
                query = """
                INSERT INTO place_chunk_references (place_id, chunk_id, reference_type, evidence)
                VALUES (:place_id, :chunk_id, :reference_type, :evidence)
                ON CONFLICT (place_id, chunk_id, reference_type) DO UPDATE
                SET evidence = :evidence
                """
                
                # Note: PostgreSQL will automatically convert the string to the enum type if it's valid
                conn.execute(text(query), {
                    "place_id": place_id,
                    "chunk_id": chunk_id,
                    "reference_type": reference_type,
                    "evidence": evidence
                })
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding place references for chunk {chunk_id}: {e}")
        return False


def load_prompt_data() -> Dict[str, Any]:
    """
    Load prompt data from prompts/map_builder.json.
    
    Returns:
        Dictionary containing prompt data
        
    Raises:
        FileNotFoundError: If the prompt file is not found
        json.JSONDecodeError: If the prompt file is not valid JSON
    """
    prompt_path = Path(__file__).parent.parent / "prompts" / "map_builder.json"
    
    if not prompt_path.exists():
        logger.error(f"Required prompt file not found: {prompt_path}")
        raise FileNotFoundError(f"Cannot find required prompt file: {prompt_path}")
    
    with open(prompt_path, 'r') as f:
        prompt_data = json.load(f)
        logger.debug(f"Loaded prompt data from {prompt_path}")
        return prompt_data




def format_places_by_zone(places_by_zone: Dict[Zone, List[Place]]) -> str:
    """
    Format places by zone in a hierarchical structure.
    
    Args:
        places_by_zone: Dictionary mapping Zone objects to lists of Place objects
        
    Returns:
        Formatted string with places grouped by zone
    """
    result = ""
    
    # Sort zones by id
    sorted_zones = sorted(places_by_zone.keys(), key=lambda zone: zone.id)
    
    for zone in sorted_zones:
        # Add zone heading
        result += f"{zone.id}: {zone.name}\n"
        
        # Sort places within zone by id
        sorted_places = sorted(places_by_zone[zone], key=lambda place: place.id)
        
        # Add places with indentation
        for i, place in enumerate(sorted_places):
            # Use box-drawing characters for last vs. non-last items
            if i == len(sorted_places) - 1:
                prefix = "└─"  # Last item
            else:
                prefix = "├─"  # Non-last item
                
            result += f"{prefix}{place.id}: {place.name}"
            
            # Add type and summary if available
            if place.summary:
                result += f" - {place.summary}"
            result += "\n"
        
        # Add separator between zones
        result += "\n"
        
    return result




def log_api_response(response, episode_id: str, model: str) -> None:
    """Log API response statistics."""
    result = response.output_parsed
    
    # Create usage stats
    usage_stats = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        "model": model
    }
    
    # Log stats
    logger.info(f"API response received for {episode_id}: {len(result.known_places)} known places, "
               f"{len(result.new_places)} new places")
    logger.info(f"API tokens used: {usage_stats['input_tokens']} input, "
               f"{usage_stats['output_tokens']} output, "
               f"{usage_stats['total_tokens']} total")




def process_chunks(
    engine: Engine,
    chunks: List[NarrativeChunk],
    places_by_zone: Dict[Zone, List[Place]],
    args: argparse.Namespace
) -> None:
    """
    Process chunks one-by-one to identify and store place references.
    
    Args:
        engine: Database connection engine
        chunks: List of chunks to process
        places_by_zone: Dictionary of places grouped by zone
        args: Command line arguments
    """
    # Load prompt data from file
    prompt_data = load_prompt_data()
    
    # Filter chunks that have already been processed unless overwrite is specified
    chunks_to_process = []
    for chunk in chunks:
        if not args.overwrite:
            existing_refs = get_place_references_for_chunk(engine, chunk.id)
            if existing_refs:
                logger.info(f"Chunk {chunk.id} already has {len(existing_refs)} place references, skipping")
                continue
        chunks_to_process.append(chunk)
    
    if not chunks_to_process:
        logger.info("No chunks left to process after filtering")
        return
        
    logger.info(f"Processing {len(chunks_to_process)} chunks")
    
    # Sort chunks by ID to ensure sequential processing
    chunks_to_process.sort(key=lambda c: c.id)
    
    # Initialize OpenAI provider
    provider = OpenAIProvider(
        api_key=args.api_key,
        model=args.model,
        temperature=args.temperature,
        reasoning_effort=args.effort
    )
    
    # Process each chunk individually
    for i, target_chunk in enumerate(chunks_to_process):
        # Get chunk identifier for logging
        chunk_id = f"Chunk {target_chunk.id}"
        if target_chunk.season is not None and target_chunk.episode is not None:
            chunk_id += f" (S{target_chunk.season:02d}E{target_chunk.episode:02d})"
            if target_chunk.scene is not None:
                chunk_id += f", Scene {target_chunk.scene}"
        
        logger.info(f"Processing {chunk_id} ({i+1}/{len(chunks_to_process)})")
        
        # Find context chunks (previous and next chunks)
        context_chunks = get_context_for_chunk(engine, target_chunk)
        
        # Create prompt for this single chunk
        single_chunk_prompt = create_single_chunk_prompt(
            target_chunk, 
            context_chunks, 
            places_by_zone, 
            prompt_data, 
            engine
        )
        
        # Test mode - show what would be sent to the API, then skip the API call
        if args.test:
            print_test_info_single_chunk(chunk_id, target_chunk, context_chunks, single_chunk_prompt, args.model)
            continue
            
        # For the API call, we don't need a separate system message since it's already in the prompt
        messages = [{"role": "user", "content": single_chunk_prompt}]
        
        try:
            # Call API with structured output
            response = provider.client.responses.parse(
                model=args.model,
                input=messages,
                temperature=args.temperature,
                text_format=LocationAnalysisResult
            )
            
            # Log usage stats
            log_api_response(response, chunk_id, args.model)
            
            # Process results for this single chunk
            result = response.output_parsed
            
            # Handle place suggestions and references for this chunk
            handle_api_result_single_chunk(engine, result, target_chunk, places_by_zone, args.dry_run)
        
        except Exception as e:
            logger.error(f"Error processing {chunk_id}: {e}")
            continue


def get_context_for_chunk(engine: Engine, target_chunk: NarrativeChunk) -> Dict[str, NarrativeChunk]:
    """
    Get context chunks (previous and next) for a target chunk.
    
    Args:
        engine: Database connection engine
        target_chunk: The chunk being processed
        
    Returns:
        Dictionary with 'previous' and 'next' chunks if available, or None
    """
    context = {}
    
    # If we have season/episode info, use that for context
    if target_chunk.season is not None and target_chunk.episode is not None:
        # Get previous chunk
        prev_query = """
        SELECT nc.id, nc.raw_text, cm.season, cm.episode, cm.scene
        FROM narrative_chunks nc
        JOIN chunk_metadata cm ON nc.id = cm.chunk_id
        WHERE nc.id < :target_id
        ORDER BY nc.id DESC
        LIMIT 1
        """
        
        # Get next chunk
        next_query = """
        SELECT nc.id, nc.raw_text, cm.season, cm.episode, cm.scene
        FROM narrative_chunks nc
        JOIN chunk_metadata cm ON nc.id = cm.chunk_id
        WHERE nc.id > :target_id
        ORDER BY nc.id ASC
        LIMIT 1
        """
        
        with engine.connect() as conn:
            # Get previous chunk if available
            prev_result = conn.execute(text(prev_query), {"target_id": target_chunk.id})
            prev_row = prev_result.fetchone()
            if prev_row:
                context['previous'] = NarrativeChunk(
                    id=prev_row.id,
                    raw_text=prev_row.raw_text,
                    season=prev_row.season,
                    episode=prev_row.episode,
                    scene=prev_row.scene
                )
                logger.debug(f"Added previous context chunk {context['previous'].id}")
            
            # Get next chunk if available
            next_result = conn.execute(text(next_query), {"target_id": target_chunk.id})
            next_row = next_result.fetchone()
            if next_row:
                context['next'] = NarrativeChunk(
                    id=next_row.id,
                    raw_text=next_row.raw_text,
                    season=next_row.season,
                    episode=next_row.episode,
                    scene=next_row.scene
                )
                logger.debug(f"Added next context chunk {context['next'].id}")
    
    return context


def create_single_chunk_prompt(
    target_chunk: NarrativeChunk,
    context_chunks: Dict[str, NarrativeChunk],
    places_by_zone: Dict[Zone, List[Place]],
    prompt_data: Dict[str, Any],
    engine: Engine
) -> str:
    """
    Create a prompt for processing a single chunk with context.
    
    Args:
        target_chunk: The target chunk to analyze
        context_chunks: Dictionary with 'previous' and 'next' context chunks
        places_by_zone: Dictionary mapping Zone objects to lists of Place objects
        prompt_data: Data from the prompt file
        engine: Database connection engine for fetching place references
        
    Returns:
        Formatted prompt string
    """
    # Format the prompt data as pretty JSON
    prompt_instructions = json.dumps(prompt_data, indent=2)
    
    # Format places section
    places_section = format_places_by_zone(places_by_zone)
    
    # Start with prompt instructions and places
    prompt = f"{prompt_instructions}\n\n"
    prompt += f"# Known Places\n\n{places_section}\n\n"
    
    # Add previous chunk as context if available
    if 'previous' in context_chunks:
        prev_chunk = context_chunks['previous']
        prompt += f"\n# CONTEXT: PREVIOUS CHUNK\n"
        prompt += f"Chunk ID: {prev_chunk.id}\n"
        if prev_chunk.season is not None and prev_chunk.episode is not None:
            prompt += f"From: Season {prev_chunk.season}, Episode {prev_chunk.episode}"
            if prev_chunk.scene is not None:
                prompt += f", Scene {prev_chunk.scene}"
            prompt += "\n"
        prompt += f"\n{prev_chunk.raw_text}\n"
        
        # Add place references for the previous chunk
        prev_refs = get_place_references_for_chunk(engine, prev_chunk.id)
        if prev_refs:
            prompt += "\nPlaces in this chunk:\n"
            for ref in prev_refs:
                prompt += f"- {ref['place_name']} ({ref['reference_type']})\n"
    
    # Add the target chunk
    prompt += f"\n# TARGET CHUNK TO ANALYZE\n"
    prompt += f"Chunk ID: {target_chunk.id}\n"
    if target_chunk.season is not None and target_chunk.episode is not None:
        prompt += f"From: Season {target_chunk.season}, Episode {target_chunk.episode}"
        if target_chunk.scene is not None:
            prompt += f", Scene {target_chunk.scene}"
        prompt += "\n"
    prompt += f"\n{target_chunk.raw_text}\n"
    
    # Add next chunk as context if available
    if 'next' in context_chunks:
        next_chunk = context_chunks['next']
        prompt += f"\n# CONTEXT: NEXT CHUNK\n"
        prompt += f"Chunk ID: {next_chunk.id}\n"
        if next_chunk.season is not None and next_chunk.episode is not None:
            prompt += f"From: Season {next_chunk.season}, Episode {next_chunk.episode}"
            if next_chunk.scene is not None:
                prompt += f", Scene {next_chunk.scene}"
            prompt += "\n"
        prompt += f"\n{next_chunk.raw_text}\n"
        
        # Add place references for the next chunk if it's already been processed
        next_refs = get_place_references_for_chunk(engine, next_chunk.id)
        if next_refs:
            prompt += "\nPlaces in this chunk:\n"
            for ref in next_refs:
                prompt += f"- {ref['place_name']} ({ref['reference_type']})\n"
    
    # End with repeating the prompt and places
    prompt += f"\n\n{prompt_instructions}\n\n"
    prompt += f"# Known Places\n\n{places_section}\n"
    
    return prompt


def print_test_info_single_chunk(
    chunk_id: str,
    target_chunk: NarrativeChunk,
    context_chunks: Dict[str, NarrativeChunk],
    prompt: str,
    model: str
) -> None:
    """Print test information for a single chunk without making API calls."""
    logger.info(f"TEST MODE - Would send the following to {model}:")
    
    # Print batch summary
    print("\n" + "=" * 80)
    print(f"PROCESSING: {chunk_id}")
    print("=" * 80)
    
    print("Context chunks:")
    if 'previous' in context_chunks:
        prev = context_chunks['previous']
        print(f"- Previous: Chunk {prev.id}", end="")
        if prev.season is not None and prev.episode is not None:
            print(f" (S{prev.season:02d}E{prev.episode:02d}", end="")
            if prev.scene is not None:
                print(f", Scene {prev.scene}", end="")
            print(")")
        else:
            print()
    else:
        print("- No previous chunk available")
        
    if 'next' in context_chunks:
        next_chunk = context_chunks['next']
        print(f"- Next: Chunk {next_chunk.id}", end="")
        if next_chunk.season is not None and next_chunk.episode is not None:
            print(f" (S{next_chunk.season:02d}E{next_chunk.episode:02d}", end="")
            if next_chunk.scene is not None:
                print(f", Scene {next_chunk.scene}", end="")
            print(")")
        else:
            print()
    else:
        print("- No next chunk available")
    
    # Print the complete prompt
    print("\n" + "=" * 80)
    print("COMPLETE PROMPT:")
    print("=" * 80)
    print(prompt)
    print("=" * 80)


def handle_api_result_single_chunk(
    engine: Engine,
    result: LocationAnalysisResult,
    target_chunk: NarrativeChunk,
    places_by_zone: Dict[Zone, List[Place]],
    dry_run: bool
) -> None:
    """
    Process API results for a single chunk, handle new place suggestions, and add references to database.
    
    Args:
        engine: Database connection engine
        result: Parsed API result
        target_chunk: The chunk being processed
        places_by_zone: Dictionary of places by zone
        dry_run: Whether to skip database writes
    """
    # Handle new place suggestions
    new_places = []
    for suggestion in result.new_places:
        print(f"\nNew place suggestion: {suggestion.name}")
        print(f"Type: {suggestion.type.value}")
        print(f"Zone: {suggestion.zone_id}")
        print(f"Summary: {suggestion.summary}")
        print(f"Reference Type: {suggestion.reference_type.value}")
        print(f"Evidence: {suggestion.evidence}")
        
        # Ask for confirmation with extra option to associate with existing place
        confirm = input("\nOptions: (y)es to add new place, (e)dit, (s)kip, or (a)ssociate with existing place? ")
        
        if confirm.lower() == 'y':
            if not dry_run:
                # Get zone information for reference
                zone_id = suggestion.zone_id
                zone_name = None
                for zone in places_by_zone.keys():
                    if zone.id == zone_id:
                        zone_name = zone.name
                        break
                        
                # Show the zone and existing places for reference
                print(f"\nZone ID: {zone_id} ({zone_name or 'Unknown zone'})")
                print("Existing places in this zone:")
                for zone, places_list in places_by_zone.items():
                    if zone.id == zone_id:
                        for place in sorted(places_list, key=lambda p: p.id):
                            print(f"  ID: {place.id} - {place.name}")
                
                # Ask for manual ID
                manual_id_input = input("\nEnter ID for new place: ")
                manual_id = int(manual_id_input) if manual_id_input.strip() else None
                
                # Create the place with manual ID
                created_place = create_new_place(engine, suggestion, manual_id)
                if created_place:
                    print(f"Created new place: {created_place}")
                    # Add to places_by_zone for future reference
                    for zone, places in places_by_zone.items():
                        if zone.id == suggestion.zone_id:
                            places.append(created_place)
                            break
                    new_places.append((
                        created_place.id,
                        suggestion.reference_type.value,
                        suggestion.evidence
                    ))
            else:
                print("DRY RUN - Would create new place")
                # Use a dummy ID for the reference in dry run mode
                new_places.append((
                    -1,  # Dummy ID
                    suggestion.reference_type.value,
                    suggestion.evidence
                ))
        
        elif confirm.lower() == 'e':
            # Allow editing the suggestion
            print("\nEditing place:")
            new_name = input(f"Name [{suggestion.name}]: ") or suggestion.name
            
            # Show valid types
            print("Valid types: fixed_location, vehicle, other")
            new_type_str = input(f"Type [{suggestion.type.value}]: ") or suggestion.type.value
            new_type = PlaceType(new_type_str)  # Convert string to enum
            
            # Show zones
            print("\nAvailable zones:")
            for zone in places_by_zone.keys():
                print(f"ID: {zone.id} - {zone.name}")
            new_zone_id = int(input(f"Zone ID [{suggestion.zone_id}]: ") or suggestion.zone_id)
            
            new_summary = input(f"Summary [{suggestion.summary}]: ") or suggestion.summary
            
            # Create a modified suggestion
            edited_suggestion = NewPlaceSuggestion(
                name=new_name,
                type=new_type,
                zone_id=new_zone_id,
                summary=new_summary,
                reference_type=suggestion.reference_type,
                evidence=suggestion.evidence
            )
            
            if not dry_run:
                # Show the zone and existing places for reference
                print(f"\nZone ID: {new_zone_id}")
                print("Existing places in this zone:")
                for zone, places_list in places_by_zone.items():
                    if zone.id == new_zone_id:
                        for place in sorted(places_list, key=lambda p: p.id):
                            print(f"  ID: {place.id} - {place.name}")
                
                # Ask for manual ID
                manual_id_input = input("\nEnter ID for new place: ")
                manual_id = int(manual_id_input) if manual_id_input.strip() else None
                
                created_place = create_new_place(engine, edited_suggestion, manual_id)
                if created_place:
                    print(f"Created edited place: {created_place}")
                    # Add to places_by_zone for future reference
                    for zone, places in places_by_zone.items():
                        if zone.id == edited_suggestion.zone_id:
                            places.append(created_place)
                            break
                    new_places.append((
                        created_place.id,
                        edited_suggestion.reference_type.value,
                        edited_suggestion.evidence
                    ))
            else:
                print("DRY RUN - Would create edited place")
                # Use a dummy ID for the reference in dry run mode
                new_places.append((
                    -1,  # Dummy ID
                    edited_suggestion.reference_type.value,
                    edited_suggestion.evidence
                ))
        
        elif confirm.lower() == 'a':
            # Associate with an existing place
            print("\nAssociate with existing place:")
            
            # Show all zones and places for reference
            print("\nAvailable places by zone:")
            for zone, places_list in places_by_zone.items():
                print(f"\nZone {zone.id}: {zone.name}")
                for place in sorted(places_list, key=lambda p: p.id):
                    print(f"  ID: {place.id} - {place.name}")
                    if place.summary:
                        print(f"     {place.summary}")
            
            # Ask for place ID
            place_id_input = input("\nEnter ID of existing place to associate with: ")
            if place_id_input.strip():
                place_id = int(place_id_input)
                
                # Find the place in our data
                found_place = None
                for places in places_by_zone.values():
                    for place in places:
                        if place.id == place_id:
                            found_place = place
                            break
                    if found_place:
                        break
                
                if found_place:
                    print(f"Associating with: {found_place}")
                    new_places.append((
                        place_id,
                        suggestion.reference_type.value,
                        suggestion.evidence
                    ))
                else:
                    print(f"Place ID {place_id} not found. Skipping this suggestion.")
            else:
                print("No ID entered. Skipping this suggestion.")
        
        else:
            print("Skipped adding this place")
            
    # Handle known place references
    place_refs = []
    for ref in result.known_places:
        place_refs.append((ref.place_id, ref.reference_type.value, ref.evidence))
    
    # Show all known place references
    print("\nKnown place references:")
    for place_id, ref_type, evidence in place_refs:
        # Find place name
        place_name = None
        for places in places_by_zone.values():
            for place in places:
                if place.id == place_id:
                    place_name = place.name
                    break
            if place_name:
                break
        print(f"- {place_name or f'Unknown Place (ID: {place_id})'} in chunk {target_chunk.id}: {ref_type}")
        print(f"  Evidence: {evidence}")
    
    # Show all new place references
    if new_places:
        print("\nNew place references:")
        for place_id, ref_type, evidence in new_places:
            if place_id == -1:  # Dummy ID from dry run
                place_name = "[NEW PLACE - dry run]"
            else:
                # Find place name
                place_name = None
                for places in places_by_zone.values():
                    for place in places:
                        if place.id == place_id:
                            place_name = place.name
                            break
                    if place_name:
                        break
            print(f"- {place_name or f'Unknown Place (ID: {place_id})'} in chunk {target_chunk.id}: {ref_type}")
            print(f"  Evidence: {evidence}")
    
    # Store references in database
    if not dry_run:
        refs_added = 0
        # Add known place references
        for place_id, ref_type, evidence in place_refs:
            success = add_place_references(engine, target_chunk.id, [(place_id, ref_type, evidence)])
            if success:
                refs_added += 1
                logger.info(f"Added reference for place {place_id} to chunk {target_chunk.id}")
            else:
                logger.error(f"Failed to add reference for place {place_id} to chunk {target_chunk.id}")
        
        # Add new place references (except dummy IDs from dry run)
        for place_id, ref_type, evidence in new_places:
            if place_id != -1:  # Skip dummy IDs
                success = add_place_references(engine, target_chunk.id, [(place_id, ref_type, evidence)])
                if success:
                    refs_added += 1
                    logger.info(f"Added reference for new place {place_id} to chunk {target_chunk.id}")
                else:
                    logger.error(f"Failed to add reference for new place {place_id} to chunk {target_chunk.id}")
        
        logger.info(f"Added {refs_added} total place references to the database")
    else:
        logger.info(f"DRY RUN - Would add place references for {len(place_refs) + len(new_places)} references")


def main():
    """Main entry point for the script."""
    args = parse_arguments()
    
    # Connect to database
    engine = connect_to_database(args.db_url)
    
    # Check that the place_chunk_references table exists
    if not args.test:
        if not check_place_references_table_exists(engine):
            logger.error("Required database tables not found, exiting")
            return 1
    
    # Get places grouped by zone
    places_by_zone = get_places_grouped_by_zone(engine)
    
    # Get chunks to process
    chunks = get_chunks_to_process(engine, args)
    if not chunks:
        logger.info("No chunks to process, exiting")
        return 0
    
    # Process chunks
    process_chunks(engine, chunks, places_by_zone, args)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())