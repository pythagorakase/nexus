#!/usr/bin/env python3
"""
Location Mapping Script for NEXUS

This script analyzes narrative chunks and identifies all location references,
categorizing them as 'setting', 'mentioned', or 'transit'. It stores these
references in a database table to enable richer location-based narrative
retrieval.

Usage Examples:
    # Test mode to show prompt and predicted API call for a specific chunk
    python map_builder.py --test --chunk 100
    
    # Process episode 5 of season 1
    python map_builder.py --episode s01e05
    
    # Process specific chunks (comma-separated list or range with hyphen)
    python map_builder.py --chunk 100,101,102
    python map_builder.py --chunk 100-110
    
    # Process all chunks
    python map_builder.py --all

    # Process with overwrite option (even if references already exist)
    python map_builder.py --episode s02e03 --overwrite
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
DEFAULT_MODEL = "o4-mini"

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
    selection.add_argument("--episode", help="Process an episode (e.g., s01e05)")
    selection.add_argument("--all", action="store_true", help="Process all chunks in the database")
    selection.add_argument("--validate", action="store_true", 
                          help="Validate that chunk_metadata.place and place_chunk_references are in sync (no API calls)")
    
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


def get_chunks_by_episode(
    engine: Engine, 
    season: int, 
    episode: int, 
    include_processed: bool = False
) -> List[NarrativeChunk]:
    """
    Get all chunks for a specific episode.
    
    Args:
        engine: Database connection engine
        season: Season number
        episode: Episode number
        include_processed: Whether to include chunks that already have place references
        
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
        chunk_ids: String with comma-separated chunk IDs or a range (e.g., "100-110")
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
    if "," in chunk_ids:
        # Comma-separated list
        id_list = [int(id.strip()) for id in chunk_ids.split(",")]
        query = base_query + f" WHERE nc.id IN :id_list" + filter_condition + " ORDER BY nc.id"
        params = {"id_list": tuple(id_list)}
    elif "-" in chunk_ids:
        # Range
        start, end = map(int, chunk_ids.split("-"))
        query = base_query + " WHERE nc.id >= :start AND nc.id <= :end" + filter_condition + " ORDER BY nc.id"
        params = {"start": start, "end": end}
    else:
        # Single ID
        query = base_query + " WHERE nc.id = :id" + filter_condition + " ORDER BY nc.id"
        params = {"id": int(chunk_ids.strip())}
    
    chunks = []
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        for row in result:
            chunks.append(NarrativeChunk(
                id=row.id,
                raw_text=row.raw_text,
                season=row.season if hasattr(row, 'season') and row.season is not None else None,
                episode=row.episode if hasattr(row, 'episode') and row.episode is not None else None,
                scene=row.scene if hasattr(row, 'scene') and row.scene is not None else None
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
    query = """
    SELECT nc.id, nc.raw_text, cm.season, cm.episode, cm.scene
    FROM narrative_chunks nc
    LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
    """
    
    if not include_processed:
        query += """
        WHERE NOT EXISTS (
            SELECT 1 FROM place_chunk_references pcr 
            WHERE pcr.chunk_id = nc.id
        )
        """
    
    query += " ORDER BY nc.id"
    
    chunks = []
    with engine.connect() as conn:
        result = conn.execute(text(query))
        for row in result:
            chunks.append(NarrativeChunk(
                id=row.id,
                raw_text=row.raw_text,
                season=row.season if hasattr(row, 'season') and row.season is not None else None,
                episode=row.episode if hasattr(row, 'episode') and row.episode is not None else None,
                scene=row.scene if hasattr(row, 'scene') and row.scene is not None else None
            ))
    
    return chunks


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
           p.zone as zone_id, z.name as zone_name
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
    name: str,
    type: str,
    zone_id: int,
    summary: str,
    manual_id: Optional[int] = None
) -> Optional[Place]:
    """
    Create a new place in the database.
    
    Args:
        engine: Database connection engine
        name: Name of the new place
        type: Type of place (fixed_location, vehicle, other)
        zone_id: ID of the zone this place belongs to
        summary: Brief description of the place
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
            "name": name,
            "type": type,
            "zone": zone_id,
            "summary": summary
        }
    else:
        # Let the database assign an ID using the sequence
        query = """
        INSERT INTO places (name, type, zone, summary)
        VALUES (:name, :type, :zone, :summary)
        RETURNING id
        """
        params = {
            "name": name,
            "type": type,
            "zone": zone_id,
            "summary": summary
        }
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            conn.commit()
            place_id = result.scalar()
            
            # Get zone name for the new Place object
            zone_query = "SELECT name FROM zones WHERE id = :zone_id"
            zone_result = conn.execute(text(zone_query), {"zone_id": zone_id})
            zone_name = zone_result.scalar() or "Unknown Zone"
            
            return Place(
                id=place_id,
                name=name,
                type=type,
                zone=zone_id,
                zone_name=zone_name,
                summary=summary
            )
    except Exception as e:
        logger.error(f"Error creating new place: {e}")
        return None


def update_chunk_metadata_place(
    engine: Engine,
    chunk_id: int,
    place_id: int
) -> bool:
    """
    Update the place field in chunk_metadata.
    
    Args:
        engine: Database connection engine
        chunk_id: ID of the chunk
        place_id: ID of the place to set as the main place
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with engine.connect() as conn:
            query = """
            UPDATE chunk_metadata
            SET place = :place_id
            WHERE chunk_id = :chunk_id
            """
            
            conn.execute(text(query), {
                "place_id": place_id,
                "chunk_id": chunk_id
            })
            conn.commit()
        logger.info(f"Updated chunk_metadata.place to {place_id} for chunk {chunk_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating chunk_metadata.place for chunk {chunk_id}: {e}")
        return False

def _alert_user():
    """Play a bell sound to alert user that input is needed."""
    try:
        # Terminal bell - quickest + lowest-overhead
        print("\a", end="", flush=True)
    except Exception:
        pass  # Silent fallback if stdout is redirected

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
                query = """
                INSERT INTO place_chunk_references (place_id, chunk_id, reference_type, evidence)
                VALUES (:place_id, :chunk_id, :reference_type, :evidence)
                ON CONFLICT (place_id, chunk_id, reference_type) DO UPDATE
                SET evidence = :evidence
                """
                
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
    
    # Sort zones by ID (ascending)
    sorted_zones = sorted(places_by_zone.keys(), key=lambda zone: zone.id)
    
    for zone in sorted_zones:
        # Add zone heading (without zone ID for AI to avoid confusion)
        result += f"{zone.name}\n"
        
        # Sort places within zone by ID
        sorted_places = sorted(places_by_zone[zone], key=lambda place: place.id)
        
        # Add places with indentation
        for i, place in enumerate(sorted_places):
            # Use box-drawing characters for last vs. non-last items
            if i == len(sorted_places) - 1:
                prefix = "└─"  # Last item
            else:
                prefix = "├─"  # Non-last item
                
            result += f"{prefix}{place.id}: {place.name}"
            
            # Add summary if available
            if place.summary:
                result += f" - {place.summary}"
            result += "\n"
        
        # Add separator between zones
        result += "\n"
        
    return result
        
def format_context_settings(setting_refs: List[Dict[str, Any]], places_by_zone: Dict[Zone, List[Place]]) -> str:
    """
    Format the places used as settings in the context chunk, grouped by zone.
    
    Args:
        setting_refs: List of setting references from the context chunk
        places_by_zone: Dictionary mapping Zone objects to lists of Place objects
        
    Returns:
        Formatted string with context settings grouped by zone
    """
    if not setting_refs:
        return ""
    
    # Group settings by zone
    settings_by_zone = {}
    
    # Find the corresponding Place objects and group by zone
    for ref in setting_refs:
        place_id = ref['place_id']
        place_name = ref['place_name']
        zone_id = ref.get('zone_id')
        zone_name = ref.get('zone_name', 'Unknown Zone')
        
        # Create a minimal Zone object
        zone = Zone(id=zone_id, name=zone_name)
        
        # Find the full Place object for more details
        place_obj = None
        for z in places_by_zone:
            if z.id == zone_id:
                for p in places_by_zone[z]:
                    if p.id == place_id:
                        place_obj = p
                        break
                if place_obj:
                    break
        
        # If we can't find the full object, create a minimal one
        if not place_obj:
            place_obj = Place(
                id=place_id,
                name=place_name,
                type="unknown",
                zone=zone_id,
                zone_name=zone_name,
                summary=ref.get('summary', '')
            )
        
        # Add to settings_by_zone
        if zone not in settings_by_zone:
            settings_by_zone[zone] = []
            
        settings_by_zone[zone].append(place_obj)
    
    # Format the result string
    result = "PLACES USED AS SETTINGS IN CONTEXT CHUNK:\n\n"
    
    # Sort zones by ID
    sorted_zones = sorted(settings_by_zone.keys(), key=lambda z: z.id)
    
    for zone in sorted_zones:
        # Add zone heading
        result += f"{zone.name}\n"
        
        # Sort places by ID
        sorted_places = sorted(settings_by_zone[zone], key=lambda p: p.id)
        
        # Add each place
        for i, place in enumerate(sorted_places):
            # Always use the last item prefix since we typically won't have many settings
            prefix = "└─"
                
            result += f"{prefix}{place.id}: {place.name}"
            
            # Add summary if available
            if place.summary:
                result += f" - {place.summary}"
            result += "\n"
        
        # Add separator between zones
        result += "\n"
    
    return result


def get_previous_chunk(engine: Engine, chunk_id: int) -> Optional[NarrativeChunk]:
    """
    Get the previous chunk for context.
    
    Args:
        engine: Database connection engine
        chunk_id: ID of the current chunk
        
    Returns:
        Previous NarrativeChunk or None if not found
    """
    query = """
    SELECT nc.id, nc.raw_text, cm.season, cm.episode, cm.scene
    FROM narrative_chunks nc
    LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
    WHERE nc.id < :chunk_id
    ORDER BY nc.id DESC
    LIMIT 1
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query), {"chunk_id": chunk_id})
        row = result.fetchone()
        
        if row is None:
            return None
            
        return NarrativeChunk(
            id=row.id,
            raw_text=row.raw_text,
            season=row.season if row.season is not None else None,
            episode=row.episode if row.episode is not None else None,
            scene=row.scene if row.scene is not None else None
        )


def create_prompt(
    target_chunk: NarrativeChunk,
    previous_chunk: Optional[NarrativeChunk],
    places_by_zone: Dict[Zone, List[Place]],
    prompt_data: Dict[str, Any],
    engine: Engine
) -> str:
    """
    Create a prompt for analyzing a single chunk with its previous chunk as context.
    
    Args:
        target_chunk: The chunk to analyze
        previous_chunk: The previous chunk for context
        places_by_zone: Dictionary of places grouped by zone
        prompt_data: Data from the prompt JSON file
        engine: Database connection engine
        
    Returns:
        Formatted prompt string
    """
    # Format the prompt data as pretty JSON without modifying it
    prompt_instructions = json.dumps(prompt_data, indent=2)
    
    # Format places section - exclude zone IDs for AI to avoid confusion
    places_section = format_places_by_zone(places_by_zone)
    
    # Start with system prompt and places
    prompt = f"{prompt_instructions}\n\n"
    prompt += f"# Known Places\n\n{places_section}\n\n"
    
    # Add previous chunk as context if available
    if previous_chunk:
        prompt += f"# PREVIOUS CHUNK (CONTEXT)\n"
        prompt += f"Chunk ID: {previous_chunk.id}\n"
        
        if previous_chunk.season is not None and previous_chunk.episode is not None:
            prompt += f"From: Season {previous_chunk.season}, Episode {previous_chunk.episode}"
            if previous_chunk.scene is not None:
                prompt += f", Scene {previous_chunk.scene}"
            prompt += "\n"
            
        prompt += f"\n{previous_chunk.raw_text}\n\n"
        
        # Add setting place references for the previous chunk
        prev_refs = get_place_references_for_chunk(engine, previous_chunk.id)
        if prev_refs:
            setting_refs = [ref for ref in prev_refs if ref['reference_type'] == 'setting']
            if setting_refs:
                # Format settings with zone and summary information
                formatted_settings = format_context_settings(setting_refs, places_by_zone)
                prompt += formatted_settings
    
    # Add the target chunk
    prompt += f"# TARGET CHUNK TO ANALYZE\n"
    prompt += f"Chunk ID: {target_chunk.id}\n"
    
    if target_chunk.season is not None and target_chunk.episode is not None:
        prompt += f"From: Season {target_chunk.season}, Episode {target_chunk.episode}"
        if target_chunk.scene is not None:
            prompt += f", Scene {target_chunk.scene}"
        prompt += "\n"
        
    prompt += f"\n{target_chunk.raw_text}\n"
    
    return prompt


def print_test_info(
    chunk_id: str,
    target_chunk: NarrativeChunk,
    previous_chunk: Optional[NarrativeChunk],
    prompt: str,
    model: str
) -> None:
    """Print test information without making API calls."""
    logger.info(f"TEST MODE - Would send the following to {model}:")
    
    # Print chunk summary
    print("\n" + "=" * 80)
    print(f"PROCESSING: {chunk_id}")
    print("=" * 80)
    
    # Print context info
    print("Context:")
    if previous_chunk:
        prev_id = f"Chunk {previous_chunk.id}"
        if previous_chunk.season is not None and previous_chunk.episode is not None:
            prev_id += f" (S{previous_chunk.season:02d}E{previous_chunk.episode:02d}"
            if previous_chunk.scene is not None:
                prev_id += f", Scene {previous_chunk.scene}"
            prev_id += ")"
        print(f"- Previous chunk: {prev_id}")
    else:
        print("- No previous chunk available")
    
    # Print the complete prompt
    print("\n" + "=" * 80)
    print("COMPLETE PROMPT:")
    print("=" * 80)
    print(prompt)
    print("=" * 80)


def get_previous_chunk_zone_ids(
    engine: Engine,
    target_chunk: NarrativeChunk
) -> List[int]:
    """
    Get zone IDs from the previous chunk's setting references.
    
    Args:
        engine: Database connection engine
        target_chunk: The current chunk being processed
        
    Returns:
        List of zone IDs from previous chunk's setting references
    """
    # Get the previous chunk
    previous_chunk = get_previous_chunk(engine, target_chunk.id)
    if not previous_chunk:
        return []
        
    # Get setting references from the previous chunk
    prev_refs = get_place_references_for_chunk(engine, previous_chunk.id)
    setting_refs = [ref for ref in prev_refs if ref['reference_type'] == 'setting']
    
    # Extract zone IDs
    zone_ids = []
    for ref in setting_refs:
        if 'zone_id' in ref and ref['zone_id'] not in zone_ids:
            zone_ids.append(ref['zone_id'])
    
    return zone_ids

def get_chunk_metadata_place(engine: Engine, chunk_id: int) -> Optional[int]:
    """
    Get the place ID from chunk_metadata for a chunk.
    
    Args:
        engine: Database connection engine
        chunk_id: ID of the chunk
        
    Returns:
        Place ID from chunk_metadata or None if not set
    """
    query = """
    SELECT place
    FROM chunk_metadata
    WHERE chunk_id = :chunk_id
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query), {"chunk_id": chunk_id})
        row = result.fetchone()
        
        if row and row.place is not None:
            return row.place
            
    return None

def get_previous_chunk_settings(engine: Engine, chunk_id: int) -> List[Dict[str, Any]]:
    """
    Get setting references from the previous chunk.
    
    Args:
        engine: Database connection engine
        chunk_id: ID of the current chunk
        
    Returns:
        List of setting references from previous chunk
    """
    # Get the previous chunk
    previous_chunk = get_previous_chunk(engine, chunk_id)
    if not previous_chunk:
        return []
        
    # Get references from previous chunk
    prev_refs = get_place_references_for_chunk(engine, previous_chunk.id)
    
    # Filter to just setting references
    return [ref for ref in prev_refs if ref['reference_type'] == 'setting']

def handle_api_result(
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
    # Initialize known_refs at the beginning
    known_refs = []
    
    # Get previous chunk setting references and metadata place
    prev_settings = get_previous_chunk_settings(engine, target_chunk.id) 
    metadata_place = get_chunk_metadata_place(engine, target_chunk.id)
    
    # Check if AI returned any setting references
    has_setting_reference = any(ref.reference_type == ReferenceType.SETTING for ref in result.known_places)
    
    # Get unique previous setting IDs
    unique_prev_ids = {s["place_id"] for s in prev_settings}
    num_prev_settings = len(unique_prev_ids)
    
    # Determine if we need to prompt for place selection
    needs_prompt = (
        not has_setting_reference and (
            num_prev_settings != 1 or  # 0 or 2+ settings in previous chunk
            (metadata_place is not None and metadata_place not in unique_prev_ids)  # metadata conflicts
        )
    )
    
    # Automatically add a setting reference only if there's just one previous setting
    # and it doesn't conflict with metadata place (or metadata is not set)
    auto_added_setting = None
    
    if needs_prompt:
        # Handle setting selection through interactive prompt
        # Get current and previous chunk details for context
        previous_chunk = get_previous_chunk(engine, target_chunk.id)
        prev_chunk_text = "Not available"
        if previous_chunk:
            prev_chunk_id = previous_chunk.id
            prev_chunk_text = previous_chunk.raw_text[:150] + "..." if len(previous_chunk.raw_text) > 150 else previous_chunk.raw_text
        else:
            prev_chunk_id = "Unknown"
        
        # Format current chunk text for context
        current_chunk_text = target_chunk.raw_text[:150] + "..." if len(target_chunk.raw_text) > 150 else target_chunk.raw_text
                
        # Get metadata place information if it exists
        metadata_place_name = "Unknown"
        metadata_place_summary = ""
        if metadata_place is not None:
            for place_list in places_by_zone.values():
                for place in place_list:
                    if place.id == metadata_place:
                        metadata_place_name = place.name
                        metadata_place_summary = place.summary or ""
                        break
                if metadata_place_name != "Unknown":
                    break
        
        # Display the conflict information
        if num_prev_settings == 0:
            print(f"\n⚠️  NO PREVIOUS SETTING DETECTED")
            if metadata_place is not None:
                print(f"Metadata place is set to: {metadata_place_name} (ID: {metadata_place})")
            else:
                print("No metadata place is set either.")
        elif num_prev_settings > 1:
            print(f"\n⚠️  MULTIPLE PREVIOUS SETTINGS DETECTED ({num_prev_settings}):")
            for prev_id in unique_prev_ids:
                # Find place name and summary
                prev_name = "Unknown"
                prev_summary = ""
                for place_list in places_by_zone.values():
                    for place in place_list:
                        if place.id == prev_id:
                            prev_name = place.name
                            prev_summary = place.summary or ""
                            break
                    if prev_name != "Unknown":
                        break
                print(f"  • {prev_name} (ID: {prev_id})")
                if prev_summary:
                    print(f"    Summary: {prev_summary}")
        else:  # num_prev_settings == 1 but metadata place conflicts
            prev_id = next(iter(unique_prev_ids))
            # Find place name and summary
            prev_name = "Unknown"
            prev_summary = ""
            for place_list in places_by_zone.values():
                for place in place_list:
                    if place.id == prev_id:
                        prev_name = place.name
                        prev_summary = place.summary or ""
                        break
                if prev_name != "Unknown":
                    break
                    
            print(f"\n⚠️  SETTING CONFLICT DETECTED:")
            print(f"  Previous chunk's setting: {prev_name} (ID: {prev_id})")
            print(f"  Metadata place: {metadata_place_name} (ID: {metadata_place})")

        # Get chunk slugs
        current_chunk_slug = None
        prev_chunk_slug = None
        with engine.connect() as conn:
            # Current chunk slug
            query = "SELECT slug FROM chunk_metadata WHERE chunk_id = :chunk_id"
            result_slug = conn.execute(text(query), {"chunk_id": target_chunk.id})
            row = result_slug.fetchone()
            if row and row.slug:
                current_chunk_slug = row.slug
                
            # Previous chunk slug (if exists)
            if previous_chunk:
                result_slug = conn.execute(text(query), {"chunk_id": previous_chunk.id})
                row = result_slug.fetchone()
                if row and row.slug:
                    prev_chunk_slug = row.slug
        
        # Display previous chunk with full context
        if previous_chunk:
            print("\nPREVIOUS CHUNK:")
            print(f"ID {previous_chunk.id}")
            print(f"{prev_chunk_slug or ''}")
            
            # Get all place references for previous chunk
            prev_all_refs = get_place_references_for_chunk(engine, previous_chunk.id)
            if prev_all_refs:
                setting_refs = [r for r in prev_all_refs if r['reference_type'] == 'setting']
                if setting_refs:
                    # Format settings in a more structured way
                    formatted_settings = format_context_settings(setting_refs, places_by_zone)
                    print(formatted_settings.rstrip())  # rstrip to remove trailing newlines
                else:
                    print("PLACE_CHUNK_REFERENCES: None")
            
            print("RAW_TEXT:")
            print(previous_chunk.raw_text)
            print("\n" + "=" * 40 + "\n")  # Add separator for readability
        
        # Display current chunk with full context
        print("CURRENT CHUNK:")
        print(f"ID {target_chunk.id}")
        print(f"{current_chunk_slug or ''}")
        
        if metadata_place is not None:
            print("CHUNK_METADATA.PLACE:")
            print(f"{metadata_place_name} (ID: {metadata_place})")
        
        print("RAW_TEXT:")
        print(target_chunk.raw_text)
        
        # Show options based on what's available
        options = []
        
        # Options for previous settings
        if num_prev_settings == 1:
            prev_id = next(iter(unique_prev_ids))
            prev_name = "Unknown"
            prev_summary = ""
            for place_list in places_by_zone.values():
                for place in place_list:
                    if place.id == prev_id:
                        prev_name = place.name
                        prev_summary = place.summary or ""
                        break
                if prev_name != "Unknown":
                    break
                    
            options.append({
                "number": 1,
                "place_id": prev_id,
                "place_name": prev_name,
                "summary": prev_summary,
                "description": "Use previous chunk's setting"
            })
        elif num_prev_settings > 1:
            option_number = 1
            prev_place_ids = []
            prev_place_names = []
            
            for prev_id in unique_prev_ids:
                prev_name = "Unknown"
                prev_summary = ""
                for place_list in places_by_zone.values():
                    for place in place_list:
                        if place.id == prev_id:
                            prev_name = place.name
                            prev_summary = place.summary or ""
                            break
                    if prev_name != "Unknown":
                        break
                        
                options.append({
                    "number": option_number,
                    "place_id": prev_id,
                    "place_name": prev_name,
                    "summary": prev_summary,
                    "description": f"Use previous setting {option_number}"
                })
                prev_place_ids.append(prev_id)
                prev_place_names.append(prev_name)
                option_number += 1
                
            # Add "USE BOTH" option for multiple previous settings
            both_option_number = len(options) + 1
            options.append({
                "number": both_option_number,
                "both_places": True,
                "place_ids": prev_place_ids,
                "place_names": prev_place_names,
                "description": "USE BOTH! 🚀"
            })
        
        # Option for metadata place if it exists and is different
        if metadata_place is not None and metadata_place not in unique_prev_ids:
            # Assign next option number
            option_number = len(options) + 1
            options.append({
                "number": option_number,
                "place_id": metadata_place,
                "place_name": metadata_place_name,
                "summary": metadata_place_summary,
                "description": "Use metadata place"
            })
            
            # Add "Use both" option if we have both previous setting and metadata place
            if num_prev_settings == 1:
                both_option_number = len(options) + 1
                prev_id = next(iter(unique_prev_ids))
                prev_name = "Unknown"
                for place_list in places_by_zone.values():
                    for place in place_list:
                        if place.id == prev_id:
                            prev_name = place.name
                            break
                    if prev_name != "Unknown":
                        break
                
                options.append({
                    "number": both_option_number,
                    "both_places": True,
                    "place_ids": [prev_id, metadata_place],
                    "place_names": [prev_name, metadata_place_name],
                    "description": "USE BOTH! 🚀"
                })
                
                # Add option to overwrite metadata place with previous chunk's setting
                overwrite_option_number = len(options) + 1
                options.append({
                    "number": overwrite_option_number,
                    "place_id": prev_id,
                    "place_name": prev_name,
                    "summary": "",
                    "description": "Overwrite metadata place with previous chunk's setting"
                })
        
        # Add options for manual place_chunk_references and chunk_metadata
        manual_refs_option_number = len(options) + 1
        options.append({
            "number": manual_refs_option_number,
            "description": "Manually set place_chunk_references"
        })
        
        manual_both_option_number = len(options) + 1
        options.append({
            "number": manual_both_option_number,
            "description": "Manually set place_chunk_references & chunk_metadata"
        })
        
        # Always add option to skip
        skip_option_number = 9
        options.append({
            "number": skip_option_number,
            "description": "Skip (leave unset)"
        })
        
        # Add quit option
        options.append({
            "number": "Q",
            "description": "Quit to Terminal"
        })
        
        # Display options
        print(f"\nOPTIONS:")
        for option in options:
            if "both_places" in option:
                print(f"  {option['number']}: {option['description']}")
                for i, place_name in enumerate(option['place_names']):
                    place_id = option['place_ids'][i]
                    print(f"     • {place_name} (ID: {place_id})")
            elif "place_id" in option:
                print(f"  {option['number']}: {option['description']}: {option['place_name']} (ID: {option['place_id']})")
                if "summary" in option and option["summary"]:
                    print(f"     Summary: {option['summary']}")
            else:
                print(f"  {option['number']}: {option['description']}")
        
        # Get user choice
        _alert_user()
        print("\n⚠️  AWAITING INPUT...")
        # Get the highest option number (excluding 9 and Q)
        max_option_num = max([opt["number"] for opt in options if isinstance(opt["number"], int) and opt["number"] != 9])
        choice = input(f"Choice [1-{max_option_num},9,Q]: ").strip()
        
        if choice.upper() == "Q":
            print("Quitting to terminal.")
            sys.exit(0)
        elif choice.isdigit():
            choice_num = int(choice)
            
            # Handle "Use both" option
            both_option = next((opt for opt in options if opt["number"] == choice_num and "both_places" in opt), None)
            if both_option:
                # Add both places as settings
                for i, place_id in enumerate(both_option["place_ids"]):
                    place_name = both_option["place_names"][i]
                    
                    ref_type = 'setting'
                    evidence = f"Manually selected both places after resolving conflict"
                    
                    known_refs.append((place_id, ref_type, evidence))
                    
                    print(f"Added setting reference to {place_name} (ID: {place_id})")
                
                # Update chunk_metadata.place field with the first place ID unless in dry run mode
                if not dry_run:
                    update_chunk_metadata_place(engine, target_chunk.id, both_option["place_ids"][0])
                    print(f"Updated chunk_metadata.place to {both_option['place_names'][0]} (ID: {both_option['place_ids'][0]})")
            
            # Handle regular place options
            place_option = next((opt for opt in options if opt["number"] == choice_num and "place_id" in opt), None)
            if place_option:
                # Use selected place
                auto_added_setting = {
                    'place_id': place_option["place_id"],
                    'place_name': place_option["place_name"],
                    'reference_type': 'setting',
                    'evidence': f"Manually selected after resolving conflict: {place_option['description']}"
                }
                logger.info(f"Using setting: {place_option['place_name']} (ID: {place_option['place_id']})")
                
                # Update chunk_metadata.place field unless in dry run mode
                if not dry_run:
                    update_chunk_metadata_place(engine, target_chunk.id, place_option["place_id"])
                    print(f"Updated chunk_metadata.place to {place_option['place_name']} (ID: {place_option['place_id']})")
            
            # Handle manual place references only
            elif choice_num == manual_refs_option_number:
                # Enter a different place ID
                while True:
                    print("\nAvailable places by zone:")
                    for zone in sorted(places_by_zone.keys(), key=lambda z: z.id):
                        print(f"\n{zone.name} (Zone ID: {zone.id}):")
                        for place in sorted(places_by_zone[zone], key=lambda p: p.id):
                            print(f"  {place.id}: {place.name}")
                            if place.summary:
                                print(f"     {place.summary}")
                    
                    _alert_user()
                    print("\n⚠️  AWAITING INPUT...")
                    custom_place_id = input("\nEnter place ID (or 'Q' to quit to terminal): ").strip()
                    if custom_place_id.upper() == 'Q':
                        print("Quitting to terminal.")
                        sys.exit(0)
                        
                    if custom_place_id:
                        try:
                            custom_place_id = int(custom_place_id)
                            # Find the place name
                            custom_place_name = "Unknown"
                            custom_place_summary = ""
                            for place_list in places_by_zone.values():
                                for place in place_list:
                                    if place.id == custom_place_id:
                                        custom_place_name = place.name
                                        custom_place_summary = place.summary or ""
                                        break
                                if custom_place_name != "Unknown":
                                    break
                                    
                            if custom_place_name != "Unknown":
                                # Automatically add as setting
                                ref_type = "setting"
                                evidence = "Manually selected as setting"
                                known_refs.append((custom_place_id, ref_type, evidence))
                                print(f"Added {custom_place_name} (ID: {custom_place_id}) as setting reference")
                                
                                # Ask if user wants to add additional references
                                print("\nAdd additional references?")
                                print("  1: Add an additional place::setting")
                                print("  2: Add a place::mentioned")
                                print("  3: Add a place::transit")
                                print("  [ENTER]: continue without adding more")
                                additional_ref = input("Choose option: ").strip()
                                
                                if additional_ref == "1":
                                    ref_type = "setting"
                                    evidence = "Manually selected as setting"
                                    known_refs.append((custom_place_id, ref_type, evidence))
                                    print(f"Added {custom_place_name} (ID: {custom_place_id}) as setting reference")
                                elif additional_ref == "2":
                                    ref_type = "mentioned"
                                    evidence = "Manually selected as mentioned"
                                    known_refs.append((custom_place_id, ref_type, evidence))
                                    print(f"Added {custom_place_name} (ID: {custom_place_id}) as mentioned reference")
                                elif additional_ref == "3":
                                    ref_type = "transit"
                                    evidence = "Manually selected as transit"
                                    known_refs.append((custom_place_id, ref_type, evidence))
                                    print(f"Added {custom_place_name} (ID: {custom_place_id}) as transit reference")
                                    
                                # Ask if they want to add more references
                                add_more = input("\nAdd another reference? (y/n): ").strip().lower()
                                if add_more != 'y':
                                    break
                            else:
                                print(f"Place ID {custom_place_id} not found. Please try again.")
                        except ValueError:
                            print("Invalid place ID. Please enter a valid integer.")
                    else:
                        print("No ID entered. Please try again.")
            
            # Handle manual place references AND update chunk_metadata
            elif choice_num == manual_both_option_number:
                # First handle the place_chunk_references
                selected_place_id = None
                selected_place_name = None
                
                while True:
                    print("\nAvailable places by zone:")
                    for zone in sorted(places_by_zone.keys(), key=lambda z: z.id):
                        print(f"\n{zone.name} (Zone ID: {zone.id}):")
                        for place in sorted(places_by_zone[zone], key=lambda p: p.id):
                            print(f"  {place.id}: {place.name}")
                            if place.summary:
                                print(f"     {place.summary}")
                    
                    _alert_user()
                    print("\n⚠️  AWAITING INPUT...")
                    custom_place_id = input("\nEnter place ID (or 'Q' to quit to terminal): ").strip()
                    if custom_place_id.upper() == 'Q':
                        print("Quitting to terminal.")
                        sys.exit(0)
                        
                    if custom_place_id:
                        try:
                            custom_place_id = int(custom_place_id)
                            # Find the place name
                            custom_place_name = "Unknown"
                            custom_place_summary = ""
                            for place_list in places_by_zone.values():
                                for place in place_list:
                                    if place.id == custom_place_id:
                                        custom_place_name = place.name
                                        custom_place_summary = place.summary or ""
                                        break
                                if custom_place_name != "Unknown":
                                    break
                                    
                            if custom_place_name != "Unknown":
                                # Automatically add as setting
                                ref_type = "setting"
                                evidence = "Manually selected as setting"
                                known_refs.append((custom_place_id, ref_type, evidence))
                                print(f"Added {custom_place_name} (ID: {custom_place_id}) as setting reference")
                                
                                # Store first setting for metadata update
                                if selected_place_id is None:
                                    selected_place_id = custom_place_id
                                    selected_place_name = custom_place_name
                                
                                # Ask if user wants to add additional references
                                print("\nAdd additional references?")
                                print("  1: Add an additional place::setting")
                                print("  2: Add a place::mentioned")
                                print("  3: Add a place::transit")
                                print("  [ENTER]: continue without adding more")
                                additional_ref = input("Choose option: ").strip()
                                
                                if additional_ref == "1":
                                    ref_type = "setting"
                                    evidence = "Manually selected as setting"
                                    known_refs.append((custom_place_id, ref_type, evidence))
                                    print(f"Added {custom_place_name} (ID: {custom_place_id}) as setting reference")
                                elif additional_ref == "2":
                                    ref_type = "mentioned"
                                    evidence = "Manually selected as mentioned"
                                    known_refs.append((custom_place_id, ref_type, evidence))
                                    print(f"Added {custom_place_name} (ID: {custom_place_id}) as mentioned reference")
                                elif additional_ref == "3":
                                    ref_type = "transit"
                                    evidence = "Manually selected as transit"
                                    known_refs.append((custom_place_id, ref_type, evidence))
                                    print(f"Added {custom_place_name} (ID: {custom_place_id}) as transit reference")
                                    
                                # Ask if they want to add more references
                                add_more = input("\nAdd another reference? (y/n): ").strip().lower()
                                if add_more != 'y':
                                    break
                            else:
                                print(f"Place ID {custom_place_id} not found. Please try again.")
                        except ValueError:
                            print("Invalid place ID. Please enter a valid integer.")
                    else:
                        print("No ID entered. Please try again.")
                
                # Now handle the chunk_metadata.place update
                if selected_place_id is not None:
                    # Use the first setting we added as the chunk_metadata.place
                    if not dry_run:
                        update_chunk_metadata_place(engine, target_chunk.id, selected_place_id)
                        print(f"Updated chunk_metadata.place to {selected_place_name} (ID: {selected_place_id})")
                else:
                    # If no setting was added, ask for a specific place to use for metadata
                    print("\nNo setting references were added. Do you want to set chunk_metadata.place separately?")
                    set_metadata = input("Set chunk_metadata.place? (y/n): ").strip().lower()
                    
                    if set_metadata == 'y':
                        while True:
                            metadata_place_id = input("\nEnter place ID for chunk_metadata.place (or 'Q' to quit to terminal): ").strip()
                            if metadata_place_id.upper() == 'Q':
                                print("Quitting to terminal.")
                                sys.exit(0)
                                
                            if metadata_place_id:
                                try:
                                    metadata_place_id = int(metadata_place_id)
                                    # Find the place name
                                    metadata_place_name = "Unknown"
                                    for place_list in places_by_zone.values():
                                        for place in place_list:
                                            if place.id == metadata_place_id:
                                                metadata_place_name = place.name
                                                break
                                        if metadata_place_name != "Unknown":
                                            break
                                            
                                    if metadata_place_name != "Unknown":
                                        if not dry_run:
                                            update_chunk_metadata_place(engine, target_chunk.id, metadata_place_id)
                                            print(f"Updated chunk_metadata.place to {metadata_place_name} (ID: {metadata_place_id})")
                                        break
                                    else:
                                        print(f"Place ID {metadata_place_id} not found. Please try again.")
                                except ValueError:
                                    print("Invalid place ID. Please enter a valid integer.")
                            else:
                                print("No ID entered. Please try again.")
            
            # Handle skip option
            elif choice_num == skip_option_number:
                print("Skipping setting assignment, leaving existing values unchanged.")
            
            # Invalid choice
            else:
                print("Invalid choice. Skipping setting assignment.")
                
        else:
            # Non-numeric choice
            print("Invalid choice. Skipping setting assignment.")
            
    elif not has_setting_reference and num_prev_settings == 1:
        # Auto-continue previous setting when there's exactly one and it doesn't conflict
        prev_place_id = next(iter(unique_prev_ids))
        
        # Find place name
        prev_place_name = "Unknown"
        for place_list in places_by_zone.values():
            for place in place_list:
                if place.id == prev_place_id:
                    prev_place_name = place.name
                    break
            if prev_place_name != "Unknown":
                break
        
        auto_added_setting = {
            'place_id': prev_place_id,
            'place_name': prev_place_name,
            'reference_type': 'setting',
            'evidence': 'Auto-continued from previous chunk (no transitions described)'
        }
        logger.info(f"Auto-adding setting reference to place {auto_added_setting['place_name']} (ID: {auto_added_setting['place_id']})")
        print(f"\nAUTO-SETTING: No setting detected, continuing with previous setting: {auto_added_setting['place_name']} (ID: {auto_added_setting['place_id']})")
        
        # Update chunk_metadata.place field if it's not already set and not in dry run mode
        if not dry_run and metadata_place is None:
            update_chunk_metadata_place(engine, target_chunk.id, prev_place_id)
            print(f"Updated chunk_metadata.place to {prev_place_name} (ID: {prev_place_id})")
    
    # Extract zone IDs from previous settings for default zone selection
    prev_zone_ids = [setting['zone_id'] for setting in prev_settings]
    
    # Fall back to any zone ID if we couldn't find previous chunk zones
    last_zone_id = None
    if prev_zone_ids:
        last_zone_id = prev_zone_ids[0]
    else:
        # Use the first zone with places as default if no previous chunk zones
        for zone in places_by_zone.keys():
            if len(places_by_zone[zone]) > 0:
                last_zone_id = zone.id
                break
                
    # Format previous chunk settings info for display
    prev_settings_info = ""
    if prev_settings:
        place_infos = []
        for setting in prev_settings:
            if setting['reference_type'] == 'setting':  # Only include actual settings
                place_infos.append(f"{setting['place_name']} (ID: {setting['place_id']})")
        if place_infos:
            prev_settings_info = f"Previous chunk setting: {', '.join(place_infos)}"
    
    # Handle known place references - auto-accept these
    if result.known_places or auto_added_setting:
        print("\nPlace references (auto-accepted):")
        
        # Process API-returned known places
        for ref in result.known_places:
            # Find place name
            place_name = None
            for places in places_by_zone.values():
                for place in places:
                    if place.id == ref.place_id:
                        place_name = place.name
                        break
                if place_name:
                    break
                    
            print(f"- {place_name or f'Place ID: {ref.place_id}'} ({ref.reference_type.value})")
            print(f"  Evidence: {ref.evidence}")
            
            known_refs.append((ref.place_id, ref.reference_type.value, ref.evidence))
            
        # Add the auto-added setting if present
        if auto_added_setting:
            place_id = auto_added_setting['place_id']
            ref_type = auto_added_setting['reference_type']
            evidence = auto_added_setting['evidence']
            
            print(f"- {auto_added_setting['place_name']} (ID: {place_id}) ({ref_type}) [AUTO-SETTING]")
            print(f"  Evidence: {evidence}")
            print(f"  Note: Auto-assigned because no setting was provided by the AI")
            
            known_refs.append((place_id, ref_type, evidence))
    
    # Handle new place suggestions
    new_refs = []
    for suggestion in result.new_places:
        # Get chunk metadata slug
        chunk_slug = None
        with engine.connect() as conn:
            query = """
            SELECT slug FROM chunk_metadata WHERE chunk_id = :chunk_id
            """
            result_slug = conn.execute(text(query), {"chunk_id": target_chunk.id})
            row = result_slug.fetchone()
            if row and row.slug:
                chunk_slug = row.slug
        
        # Get current chunk metadata place
        metadata_place_id = get_chunk_metadata_place(engine, target_chunk.id)
        metadata_place_name = "Unknown"
        if metadata_place_id is not None:
            for place_list in places_by_zone.values():
                for place in place_list:
                    if place.id == metadata_place_id:
                        metadata_place_name = place.name
                        break
                if metadata_place_name != "Unknown":
                    break
        
        print("\n" + "=" * 60)
        print(f"New Place Suggestion: {suggestion.name}")
        print(f"Type: {suggestion.type.value}")
        
        # Display previous chunk settings info if available
        if prev_settings_info:
            print(prev_settings_info)
        
        # Display current chunk information
        print(f"Current Chunk: {target_chunk.id}" + (f" ({chunk_slug})" if chunk_slug else ""))
        print(f"Current Chunk Metadata: {metadata_place_name} (ID: {metadata_place_id})" if metadata_place_id else "Current Chunk Metadata: None")
        
        print(f"Summary: {suggestion.summary}")
        print(f"Reference Type: {suggestion.reference_type.value}")
        print(f"Evidence: {suggestion.evidence}")
        print("=" * 60)
        print("Full Text:")
        print(target_chunk.raw_text)
        
        # Options menu
        print("\nOptions:")
        print("  1: Accept and edit details")
        print("  2: Link to existing place instead")
        print("  3: Reject this suggestion")
        print("  4: Reject and register as a negative example")
        print("  Q: Quit to Terminal")
        
        _alert_user()
        print("\n⚠️  AWAITING INPUT...")
        choice = input("\nEnter choice (1-4, Q): ").strip()
        
        if choice == "3":
            print("Rejected this suggestion.")
            
        elif choice == "4":
            print("\nRejecting and registering as a negative example.")
            explanation = input(f"Enter explanation for why '{suggestion.name}' is invalid: ").strip()
            
            if explanation:
                # Load the current prompt file
                prompt_path = Path(__file__).parent.parent / "prompts" / "map_builder.json"
                try:
                    with open(prompt_path, 'r') as f:
                        prompt_data = json.load(f)
                    
                    # Add the negative example to specific_examples.incorrect
                    if "entity_disambiguation" in prompt_data and "specific_examples" in prompt_data["entity_disambiguation"]:
                        if "incorrect" in prompt_data["entity_disambiguation"]["specific_examples"]:
                            # Add to existing incorrect examples
                            prompt_data["entity_disambiguation"]["specific_examples"]["incorrect"][f"'{suggestion.name}'"] = explanation
                        else:
                            # Create incorrect examples object if it doesn't exist
                            prompt_data["entity_disambiguation"]["specific_examples"]["incorrect"] = {
                                f"'{suggestion.name}'": explanation
                            }
                            
                        # Write back to the file
                        with open(prompt_path, 'w') as f:
                            json.dump(prompt_data, f, indent=2)
                            
                        print(f"Added negative example to {prompt_path}")
                    else:
                        print("Could not find the correct structure in the prompt file to add the example.")
                except Exception as e:
                    print(f"Error adding negative example: {e}")
            else:
                print("No explanation provided. Negative example not registered.")
            
        elif choice == "1":
            # Edit and accept the suggestion
            print("\nEditing suggestion (press Enter to keep current value):")
            
            # Reference type - numbered choices
            print("\nReference type:")
            print("  1: setting")
            print("  2: mentioned")
            print("  3: transit")
            print(f"Current: {suggestion.reference_type.value}")
            ref_type_choice = input(f"Select reference type (1-3) [Enter to keep current]: ").strip()
            
            if ref_type_choice == "1":
                new_ref_type = "setting"
            elif ref_type_choice == "2":
                new_ref_type = "mentioned"
            elif ref_type_choice == "3":
                new_ref_type = "transit"
            else:
                new_ref_type = suggestion.reference_type.value
            
            # Place type - numbered choices
            print("\nPlace type:")
            print("  1: fixed_location")
            print("  2: vehicle")
            print("  3: other")
            print(f"Current: {suggestion.type.value}")
            type_choice = input(f"Select type (1-3) [Enter to keep current]: ").strip()
            
            if type_choice == "1":
                new_type = "fixed_location"
            elif type_choice == "2":
                new_type = "vehicle"
            elif type_choice == "3":
                new_type = "other"
            else:
                new_type = suggestion.type.value
            
            # Zone selection
            print("\nAvailable zones:")
            # Display zones with IDs in a consistent format
            for zone in sorted(places_by_zone.keys(), key=lambda z: z.id):
                print(f"  {zone.id}: {zone.name}")
                
            # If there are multiple previous zones, don't set a default
            default_zone_id = None
            default_zone_prompt = ""
            
            # Use previous chunk's zone only if exactly one setting zone
            if len(prev_zone_ids) == 1:
                default_zone_id = prev_zone_ids[0]
                for zone in places_by_zone:
                    if zone.id == default_zone_id:
                        default_zone_prompt = f" [{default_zone_id} ({zone.name})]"
                        break
                        
            # Prompt for zone ID 
            zone_prompt = f"Zone ID{default_zone_prompt}: "
            new_zone_id_input = input(zone_prompt).strip()
            
            if new_zone_id_input:
                new_zone_id = int(new_zone_id_input)
            elif default_zone_id:
                new_zone_id = default_zone_id
            else:
                # No input and no default - must enter a zone ID
                print("You must enter a zone ID.")
                continue
                
            # Remember this for future defaults
            last_zone_id = new_zone_id
            
            # Place ID - manual input required
            print("\nExisting place IDs in this zone:")
            for zone in places_by_zone.keys():
                if zone.id == new_zone_id:
                    for place in sorted(places_by_zone[zone], key=lambda p: p.id):
                        print(f"  {place.id}: {place.name}")
                        if place.summary:
                            print(f"     {place.summary}")
                    break
                    
            new_place_id = input("Place ID (new ID for this place): ").strip()
            if new_place_id:
                new_place_id = int(new_place_id)
            else:
                print("ERROR: Must provide a place ID")
                continue
                
            # Place name
            new_name = input(f"Name [{suggestion.name}]: ").strip() or suggestion.name
            
            # Summary
            new_summary = input(f"Summary [{suggestion.summary}]: ").strip() or suggestion.summary
            
            if not dry_run:
                # Create new place
                new_place = create_new_place(
                    engine,
                    name=new_name,
                    type=new_type,  # Use the selected type
                    zone_id=new_zone_id,
                    summary=new_summary,
                    manual_id=new_place_id
                )
                
                if new_place:
                    print(f"Created new place: {new_place.name} (ID: {new_place.id})")
                    
                    # Add to places_by_zone for future reference
                    for zone in places_by_zone.keys():
                        if zone.id == new_zone_id:
                            places_by_zone[zone].append(new_place)
                            break
                            
                    # Add reference
                    new_refs.append((new_place.id, new_ref_type, suggestion.evidence))
                else:
                    print("Failed to create new place.")
            else:
                print("DRY RUN - Would create new place")
                # Use a dummy ID for the reference in dry run mode
                new_refs.append((-1, new_ref_type, suggestion.evidence))
                
        elif choice == "2":
            # Link to existing place
            print("\nChoose existing place to link to:")
            
            # Use the same formatting function used for the API to maintain consistency
            formatted_places = format_places_by_zone(places_by_zone)
            print(formatted_places)
            
            # Get place ID (no alert here since we're already in an interactive prompt)
            existing_id = input("\nEnter ID of existing place: ").strip()
            if existing_id:
                existing_id = int(existing_id)
                
                # Verify it exists
                place_exists = False
                for places in places_by_zone.values():
                    for place in places:
                        if place.id == existing_id:
                            place_exists = True
                            print(f"Linking to existing place: {place.name} (ID: {place.id})")
                            break
                    if place_exists:
                        break
                        
                if place_exists:
                    new_refs.append((existing_id, suggestion.reference_type.value, suggestion.evidence))
                else:
                    print(f"Place ID {existing_id} not found.")
            else:
                print("No ID entered. Skipping.")
                
        elif choice.upper() == "Q":
            print("Quitting to terminal.")
            sys.exit(0)
            
        else:
            print("Invalid choice. Skipping this suggestion.")
    
    # Write all references to database
    if not dry_run:
        all_refs = known_refs + new_refs
        if all_refs:
            # Filter out dummy IDs from dry run
            valid_refs = [(place_id, ref_type, evidence) for place_id, ref_type, evidence in all_refs if place_id != -1]
            
            if valid_refs:
                success = add_place_references(engine, target_chunk.id, valid_refs)
                if success:
                    logger.info(f"Added {len(valid_refs)} place references to chunk {target_chunk.id}")
                else:
                    logger.error(f"Failed to add place references to chunk {target_chunk.id}")
        else:
            logger.info(f"No place references to add for chunk {target_chunk.id}")
    else:
        logger.info(f"DRY RUN - Would add {len(known_refs) + len(new_refs)} place references")


def validate_chunks(
    engine: Engine,
    chunks: List[NarrativeChunk],
    places_by_zone: Dict[Zone, List[Place]],
    args: argparse.Namespace
) -> None:
    """
    Validate that chunk_metadata.place and place_chunk_references are in sync.
    
    Args:
        engine: Database connection engine
        chunks: List of chunks to validate
        places_by_zone: Dictionary of places grouped by zone
        args: Command line arguments
    """
    logger.info(f"Validating {len(chunks)} chunks")
    
    # Sort chunks by ID to ensure sequential processing
    chunks.sort(key=lambda c: c.id)
    
    for i, chunk in enumerate(chunks):
        # Get chunk identifier for logging
        chunk_id = f"Chunk {chunk.id}"
        if chunk.season is not None and chunk.episode is not None:
            chunk_id += f" (S{chunk.season:02d}E{chunk.episode:02d})"
            if chunk.scene is not None:
                chunk_id += f", Scene {chunk.scene}"
        
        logger.info(f"Validating {chunk_id} ({i+1}/{len(chunks)})")
        
        # Get metadata place
        metadata_place = get_chunk_metadata_place(engine, chunk.id)
        
        # Get setting references from place_chunk_references
        setting_refs = []
        with engine.connect() as conn:
            query = """
            SELECT pcr.place_id, p.name, p.summary, p.zone, z.name as zone_name
            FROM place_chunk_references pcr
            JOIN places p ON pcr.place_id = p.id
            JOIN zones z ON p.zone = z.id
            WHERE pcr.chunk_id = :chunk_id AND pcr.reference_type = 'setting'
            """
            result = conn.execute(text(query), {"chunk_id": chunk.id})
            for row in result:
                setting_refs.append({
                    'place_id': row.place_id,
                    'place_name': row.name,
                    'summary': row.summary,
                    'zone_id': row.zone,
                    'zone_name': row.zone_name,
                    'reference_type': 'setting'
                })
        
        # Get setting place IDs for easier comparison
        setting_ids = [ref['place_id'] for ref in setting_refs]
        
        # Previous chunk for context
        previous_chunk = get_previous_chunk(engine, chunk.id)
        
        # Check for validation issues
        needs_prompt = False
        validation_issue = ""
        
        if not setting_ids and metadata_place is None:
            # Case 1: Both are empty
            needs_prompt = True
            validation_issue = "VALIDATION ISSUE: Both chunk_metadata.place and place_chunk_references are empty"
        elif not setting_ids and metadata_place is not None:
            # Case 2: place_chunk_references is empty but metadata_place is set
            needs_prompt = True
            validation_issue = "VALIDATION ISSUE: place_chunk_references is empty but chunk_metadata.place is set"
        elif setting_ids and metadata_place is None:
            # Case 3: place_chunk_references has values but metadata_place is not set
            needs_prompt = True
            validation_issue = "VALIDATION ISSUE: place_chunk_references has values but chunk_metadata.place is empty"
        elif metadata_place not in setting_ids:
            # Case 4: metadata_place doesn't match any setting in place_chunk_references
            needs_prompt = True
            validation_issue = "VALIDATION ISSUE: chunk_metadata.place doesn't match any setting in place_chunk_references"
        
        if needs_prompt:
            # Get chunk slugs
            current_chunk_slug = None
            prev_chunk_slug = None
            with engine.connect() as conn:
                # Current chunk slug
                query = "SELECT slug FROM chunk_metadata WHERE chunk_id = :chunk_id"
                result_slug = conn.execute(text(query), {"chunk_id": chunk.id})
                row = result_slug.fetchone()
                if row and row.slug:
                    current_chunk_slug = row.slug
                    
                # Previous chunk slug (if exists)
                if previous_chunk:
                    result_slug = conn.execute(text(query), {"chunk_id": previous_chunk.id})
                    row = result_slug.fetchone()
                    if row and row.slug:
                        prev_chunk_slug = row.slug
            
            # Display validation issue
            print(f"\n⚠️  {validation_issue}")
            
            # Get metadata place name if it exists
            metadata_place_name = "None"
            metadata_place_summary = ""
            if metadata_place is not None:
                for place_list in places_by_zone.values():
                    for place in place_list:
                        if place.id == metadata_place:
                            metadata_place_name = place.name
                            metadata_place_summary = place.summary or ""
                            break
                    if metadata_place_name != "None":
                        break
                        
            print(f"  chunk_metadata.place: {metadata_place_name} (ID: {metadata_place if metadata_place is not None else 'None'})")
            print(f"  place_chunk_references (setting): {', '.join([ref['place_name'] + ' (ID: ' + str(ref['place_id']) + ')' for ref in setting_refs]) or 'None'}")
            
            # Display previous chunk with full context
            if previous_chunk:
                print("\nPREVIOUS CHUNK:")
                print(f"ID {previous_chunk.id}")
                print(f"{prev_chunk_slug or ''}")
                
                # Get all place references for previous chunk
                prev_all_refs = get_place_references_for_chunk(engine, previous_chunk.id)
                if prev_all_refs:
                    prev_setting_refs = [r for r in prev_all_refs if r['reference_type'] == 'setting']
                    if prev_setting_refs:
                        # Format settings in a more structured way
                        formatted_settings = format_context_settings(prev_setting_refs, places_by_zone)
                        print(formatted_settings.rstrip())  # rstrip to remove trailing newlines
                    else:
                        print("PLACE_CHUNK_REFERENCES: None")
                
                print("RAW_TEXT:")
                print(previous_chunk.raw_text)
                print("\n" + "=" * 40 + "\n")  # Add separator for readability
            
            # Display current chunk with full context
            print("CURRENT CHUNK:")
            print(f"ID {chunk.id}")
            print(f"{current_chunk_slug or ''}")
            
            if metadata_place is not None:
                print("CHUNK_METADATA.PLACE:")
                print(f"{metadata_place_name} (ID: {metadata_place})")
            
            print("RAW_TEXT:")
            print(chunk.raw_text)
            
            # Get previous chunk's settings for options
            prev_settings = []
            unique_prev_ids = set()
            if previous_chunk:
                prev_all_refs = get_place_references_for_chunk(engine, previous_chunk.id)
                prev_settings = [r for r in prev_all_refs if r['reference_type'] == 'setting']
                unique_prev_ids = {s["place_id"] for s in prev_settings}
            
            # Show options based on what's available
            options = []
            
            # Add existing settings from place_chunk_references as options
            for i, ref in enumerate(setting_refs):
                options.append({
                    "number": i + 1,
                    "place_id": ref['place_id'],
                    "place_name": ref['place_name'],
                    "summary": ref['summary'],
                    "description": f"Use setting {i + 1} from place_chunk_references"
                })
                
            # Add previous settings as options if not already included
            if unique_prev_ids:
                for prev_id in unique_prev_ids:
                    if prev_id not in setting_ids:
                        prev_name = "Unknown"
                        prev_summary = ""
                        for place_list in places_by_zone.values():
                            for place in place_list:
                                if place.id == prev_id:
                                    prev_name = place.name
                                    prev_summary = place.summary or ""
                                    break
                            if prev_name != "Unknown":
                                break
                                
                        options.append({
                            "number": len(options) + 1,
                            "place_id": prev_id,
                            "place_name": prev_name,
                            "summary": prev_summary,
                            "description": "Use previous chunk's setting"
                        })
            
            # Add metadata place as option if it exists and is not already included
            if metadata_place is not None and metadata_place not in setting_ids and metadata_place not in unique_prev_ids:
                options.append({
                    "number": len(options) + 1,
                    "place_id": metadata_place,
                    "place_name": metadata_place_name,
                    "summary": metadata_place_summary,
                    "description": "Use metadata place"
                })
            
            # Add "USE BOTH" options for various combinations
            if len(setting_ids) > 0 and metadata_place is not None and metadata_place not in setting_ids:
                # Both settings and metadata
                place_ids = setting_ids + [metadata_place]
                place_names = [ref['place_name'] for ref in setting_refs] + [metadata_place_name]
                
                options.append({
                    "number": len(options) + 1,
                    "both_places": True,
                    "place_ids": place_ids,
                    "place_names": place_names,
                    "description": "USE BOTH! 🚀"
                })
            
            # Add options for manual place_chunk_references and chunk_metadata
            manual_refs_option_number = len(options) + 1
            options.append({
                "number": manual_refs_option_number,
                "description": "Manually set place_chunk_references"
            })
            
            manual_both_option_number = len(options) + 1
            options.append({
                "number": manual_both_option_number,
                "description": "Manually set place_chunk_references & chunk_metadata"
            })
            
            # Always add option to skip
            skip_option_number = 9
            options.append({
                "number": skip_option_number,
                "description": "Skip (leave unset)"
            })
            
            # Add quit option
            options.append({
                "number": "Q",
                "description": "Quit to Terminal"
            })
            
            # Display options
            print(f"\nOPTIONS:")
            for option in options:
                if "both_places" in option:
                    print(f"  {option['number']}: {option['description']}")
                    for i, place_name in enumerate(option['place_names']):
                        place_id = option['place_ids'][i]
                        print(f"     • {place_name} (ID: {place_id})")
                elif "place_id" in option:
                    print(f"  {option['number']}: {option['description']}: {option['place_name']} (ID: {option['place_id']})")
                    if "summary" in option and option["summary"]:
                        print(f"     Summary: {option['summary']}")
                else:
                    print(f"  {option['number']}: {option['description']}")
            
            # Get user choice
            _alert_user()
            print("\n⚠️  AWAITING INPUT...")
            # Get the highest option number (excluding 9 and Q)
            max_option_num = max([opt["number"] for opt in options if isinstance(opt["number"], int) and opt["number"] != 9])
            choice = input(f"Choice [1-{max_option_num},9,Q]: ").strip()
            
            if choice.upper() == "Q":
                print("Quitting to terminal.")
                sys.exit(0)
            elif choice.isdigit():
                choice_num = int(choice)
                
                # Handle "Use both" option
                both_option = next((opt for opt in options if opt["number"] == choice_num and "both_places" in opt), None)
                if both_option:
                    # Clear existing references first
                    if not args.dry_run:
                        with engine.connect() as conn:
                            # Delete existing settings
                            delete_query = """
                            DELETE FROM place_chunk_references
                            WHERE chunk_id = :chunk_id AND reference_type = 'setting'
                            """
                            conn.execute(text(delete_query), {"chunk_id": chunk.id})
                            conn.commit()
                    
                    # Add all places as settings
                    references = []
                    for i, place_id in enumerate(both_option["place_ids"]):
                        place_name = both_option["place_names"][i]
                        references.append((place_id, 'setting', f"Manually selected during validation"))
                        print(f"Added setting reference to {place_name} (ID: {place_id})")
                    
                    # Update database
                    if not args.dry_run:
                        add_place_references(engine, chunk.id, references)
                        
                        # Update chunk_metadata.place field with the first place ID
                        update_chunk_metadata_place(engine, chunk.id, both_option["place_ids"][0])
                        print(f"Updated chunk_metadata.place to {both_option['place_names'][0]} (ID: {both_option['place_ids'][0]})")
                
                # Handle regular place options
                place_option = next((opt for opt in options if opt["number"] == choice_num and "place_id" in opt), None)
                if place_option:
                    # Clear existing references first
                    if not args.dry_run:
                        with engine.connect() as conn:
                            # Delete existing settings
                            delete_query = """
                            DELETE FROM place_chunk_references
                            WHERE chunk_id = :chunk_id AND reference_type = 'setting'
                            """
                            conn.execute(text(delete_query), {"chunk_id": chunk.id})
                            conn.commit()
                    
                    # Add the selected place as setting
                    references = [(place_option["place_id"], 'setting', f"Manually selected during validation")]
                    print(f"Added setting reference to {place_option['place_name']} (ID: {place_option['place_id']})")
                    
                    # Update database
                    if not args.dry_run:
                        add_place_references(engine, chunk.id, references)
                        
                        # Update chunk_metadata.place field
                        update_chunk_metadata_place(engine, chunk.id, place_option["place_id"])
                        print(f"Updated chunk_metadata.place to {place_option['place_name']} (ID: {place_option['place_id']})")
                
                # Handle manual place references only
                elif choice_num == manual_refs_option_number:
                    # Enter a different place ID
                    while True:
                        print("\nAvailable places by zone:")
                        for zone in sorted(places_by_zone.keys(), key=lambda z: z.id):
                            print(f"\n{zone.name} (Zone ID: {zone.id}):")
                            for place in sorted(places_by_zone[zone], key=lambda p: p.id):
                                print(f"  {place.id}: {place.name}")
                                if place.summary:
                                    print(f"     {place.summary}")
                        
                        _alert_user()
                        print("\n⚠️  AWAITING INPUT...")
                        custom_place_id = input("\nEnter place ID (or 'Q' to quit to terminal): ").strip()
                        if custom_place_id.upper() == 'Q':
                            print("Quitting to terminal.")
                            sys.exit(0)
                            
                        if custom_place_id:
                            try:
                                custom_place_id = int(custom_place_id)
                                # Find the place name
                                custom_place_name = "Unknown"
                                custom_place_summary = ""
                                for place_list in places_by_zone.values():
                                    for place in place_list:
                                        if place.id == custom_place_id:
                                            custom_place_name = place.name
                                            custom_place_summary = place.summary or ""
                                            break
                                    if custom_place_name != "Unknown":
                                        break
                                        
                                if custom_place_name != "Unknown":
                                    # Clear existing references first
                                    if not args.dry_run:
                                        with engine.connect() as conn:
                                            # Delete existing settings
                                            delete_query = """
                                            DELETE FROM place_chunk_references
                                            WHERE chunk_id = :chunk_id AND reference_type = 'setting'
                                            """
                                            conn.execute(text(delete_query), {"chunk_id": chunk.id})
                                            conn.commit()
                                    
                                    # Automatically add as setting
                                    references = [(custom_place_id, 'setting', "Manually selected during validation")]
                                    print(f"Added {custom_place_name} (ID: {custom_place_id}) as setting reference")
                                    
                                    # Update database
                                    if not args.dry_run:
                                        add_place_references(engine, chunk.id, references)
                                    
                                    # Ask if user wants to add additional references
                                    print("\nAdd additional references?")
                                    print("  1: Add an additional place::setting")
                                    print("  2: Add a place::mentioned")
                                    print("  3: Add a place::transit")
                                    print("  [ENTER]: continue without adding more")
                                    additional_ref = input("Choose option: ").strip()
                                    
                                    if additional_ref == "1":
                                        references.append((custom_place_id, 'setting', "Manually selected during validation"))
                                        print(f"Added {custom_place_name} (ID: {custom_place_id}) as setting reference")
                                        if not args.dry_run:
                                            add_place_references(engine, chunk.id, [(custom_place_id, 'setting', "Manually selected during validation")])
                                    elif additional_ref == "2":
                                        references.append((custom_place_id, 'mentioned', "Manually selected during validation"))
                                        print(f"Added {custom_place_name} (ID: {custom_place_id}) as mentioned reference")
                                        if not args.dry_run:
                                            add_place_references(engine, chunk.id, [(custom_place_id, 'mentioned', "Manually selected during validation")])
                                    elif additional_ref == "3":
                                        references.append((custom_place_id, 'transit', "Manually selected during validation"))
                                        print(f"Added {custom_place_name} (ID: {custom_place_id}) as transit reference")
                                        if not args.dry_run:
                                            add_place_references(engine, chunk.id, [(custom_place_id, 'transit', "Manually selected during validation")])
                                        
                                    # Ask if they want to add more references
                                    add_more = input("\nAdd another reference? (y/n): ").strip().lower()
                                    if add_more != 'y':
                                        break
                                else:
                                    print(f"Place ID {custom_place_id} not found. Please try again.")
                            except ValueError:
                                print("Invalid place ID. Please enter a valid integer.")
                        else:
                            print("No ID entered. Please try again.")
                
                # Handle manual place references AND update chunk_metadata
                elif choice_num == manual_both_option_number:
                    # First handle the place_chunk_references
                    selected_place_id = None
                    selected_place_name = None
                    references = []
                    
                    while True:
                        print("\nAvailable places by zone:")
                        for zone in sorted(places_by_zone.keys(), key=lambda z: z.id):
                            print(f"\n{zone.name} (Zone ID: {zone.id}):")
                            for place in sorted(places_by_zone[zone], key=lambda p: p.id):
                                print(f"  {place.id}: {place.name}")
                                if place.summary:
                                    print(f"     {place.summary}")
                        
                        _alert_user()
                        print("\n⚠️  AWAITING INPUT...")
                        custom_place_id = input("\nEnter place ID (or 'Q' to quit to terminal): ").strip()
                        if custom_place_id.upper() == 'Q':
                            print("Quitting to terminal.")
                            sys.exit(0)
                            
                        if custom_place_id:
                            try:
                                custom_place_id = int(custom_place_id)
                                # Find the place name
                                custom_place_name = "Unknown"
                                custom_place_summary = ""
                                for place_list in places_by_zone.values():
                                    for place in place_list:
                                        if place.id == custom_place_id:
                                            custom_place_name = place.name
                                            custom_place_summary = place.summary or ""
                                            break
                                    if custom_place_name != "Unknown":
                                        break
                                        
                                if custom_place_name != "Unknown":
                                    # Clear existing references first if this is the first one
                                    if not references and not args.dry_run:
                                        with engine.connect() as conn:
                                            # Delete existing settings
                                            delete_query = """
                                            DELETE FROM place_chunk_references
                                            WHERE chunk_id = :chunk_id AND reference_type = 'setting'
                                            """
                                            conn.execute(text(delete_query), {"chunk_id": chunk.id})
                                            conn.commit()
                                    
                                    # Automatically add as setting
                                    ref_type = "setting"
                                    evidence = "Manually selected during validation"
                                    references.append((custom_place_id, ref_type, evidence))
                                    print(f"Added {custom_place_name} (ID: {custom_place_id}) as setting reference")
                                    
                                    # Update database
                                    if not args.dry_run:
                                        add_place_references(engine, chunk.id, [(custom_place_id, ref_type, evidence)])
                                    
                                    # Store first setting for metadata update
                                    if selected_place_id is None:
                                        selected_place_id = custom_place_id
                                        selected_place_name = custom_place_name
                                    
                                    # Ask if user wants to add additional references
                                    print("\nAdd additional references?")
                                    print("  1: Add an additional place::setting")
                                    print("  2: Add a place::mentioned")
                                    print("  3: Add a place::transit")
                                    print("  [ENTER]: continue without adding more")
                                    additional_ref = input("Choose option: ").strip()
                                    
                                    if additional_ref == "1":
                                        ref_type = "setting"
                                        evidence = "Manually selected during validation"
                                        references.append((custom_place_id, ref_type, evidence))
                                        print(f"Added {custom_place_name} (ID: {custom_place_id}) as setting reference")
                                        if not args.dry_run:
                                            add_place_references(engine, chunk.id, [(custom_place_id, ref_type, evidence)])
                                    elif additional_ref == "2":
                                        ref_type = "mentioned"
                                        evidence = "Manually selected during validation"
                                        references.append((custom_place_id, ref_type, evidence))
                                        print(f"Added {custom_place_name} (ID: {custom_place_id}) as mentioned reference")
                                        if not args.dry_run:
                                            add_place_references(engine, chunk.id, [(custom_place_id, ref_type, evidence)])
                                    elif additional_ref == "3":
                                        ref_type = "transit"
                                        evidence = "Manually selected during validation"
                                        references.append((custom_place_id, ref_type, evidence))
                                        print(f"Added {custom_place_name} (ID: {custom_place_id}) as transit reference")
                                        if not args.dry_run:
                                            add_place_references(engine, chunk.id, [(custom_place_id, ref_type, evidence)])
                                        
                                    # Ask if they want to add more references
                                    add_more = input("\nAdd another reference? (y/n): ").strip().lower()
                                    if add_more != 'y':
                                        break
                                else:
                                    print(f"Place ID {custom_place_id} not found. Please try again.")
                            except ValueError:
                                print("Invalid place ID. Please enter a valid integer.")
                        else:
                            print("No ID entered. Please try again.")
                    
                    # Now update chunk_metadata.place with the first setting
                    if selected_place_id is not None and not args.dry_run:
                        update_chunk_metadata_place(engine, chunk.id, selected_place_id)
                        print(f"Updated chunk_metadata.place to {selected_place_name} (ID: {selected_place_id})")
                
                # Handle skip option
                elif choice_num == skip_option_number:
                    print("Skipping validation issue, leaving existing values unchanged.")
                
                # Invalid choice
                else:
                    print("Invalid choice. Skipping validation issue.")
                    
            else:
                # Non-numeric choice
                print("Invalid choice. Skipping validation issue.")

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
        places_by_zone: Dictionary of places grouped by zone (initial state, will be refreshed for each chunk)
        args: Command line arguments
    """
    # Load prompt data from file
    prompt_data = load_prompt_data()
    
    # Sort chunks by ID to ensure sequential processing
    chunks.sort(key=lambda c: c.id)
    
    logger.info(f"Processing {len(chunks)} chunks")
    
    # Initialize OpenAI provider
    provider = OpenAIProvider(
        api_key=args.api_key,
        model=args.model,
        temperature=args.temperature,
        reasoning_effort=args.effort
    )
    
    # Process each chunk individually
    for i, chunk in enumerate(chunks):
        # Refresh places_by_zone for each chunk to ensure we have the latest data
        places_by_zone = get_places_grouped_by_zone(engine)
        # Get chunk identifier for logging
        chunk_id = f"Chunk {chunk.id}"
        if chunk.season is not None and chunk.episode is not None:
            chunk_id += f" (S{chunk.season:02d}E{chunk.episode:02d})"
            if chunk.scene is not None:
                chunk_id += f", Scene {chunk.scene}"
        
        logger.info(f"Processing {chunk_id} ({i+1}/{len(chunks)})")
        
        # Get previous chunk for context
        previous_chunk = get_previous_chunk(engine, chunk.id)
        
        # Create prompt
        prompt = create_prompt(
            target_chunk=chunk,
            previous_chunk=previous_chunk,
            places_by_zone=places_by_zone,
            prompt_data=prompt_data,
            engine=engine
        )
        
        # Test mode - just show the prompt and exit
        if args.test:
            print_test_info(chunk_id, chunk, previous_chunk, prompt, args.model)
            return
        
        # Create message for API call
        messages = [{"role": "user", "content": prompt}]
        
        try:
            # Call API with structured output - handle reasoning models differently
            # Reasoning models (o-prefixed) don't accept temperature parameter
            if args.model.startswith("o"):
                response = provider.client.responses.parse(
                    model=args.model,
                    input=messages,
                    reasoning={"effort": args.effort},
                    text_format=LocationAnalysisResult
                )
            else:
                response = provider.client.responses.parse(
                    model=args.model,
                    input=messages,
                    temperature=args.temperature,
                    text_format=LocationAnalysisResult
                )
            
            # Log usage stats
            logger.info(f"API response received: {response.usage.input_tokens} input, "
                      f"{response.usage.output_tokens} output tokens")
            
            # Process results for this chunk
            result = response.output_parsed
            
            # Handle API result
            handle_api_result(engine, result, chunk, places_by_zone, args.dry_run)
            
        except Exception as e:
            logger.error(f"Error processing {chunk_id}: {e}")
            continue


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
    
    # Get chunks to process based on arguments
    chunks = []
    if args.episode:
        try:
            season, episode = EpisodeSlugParser.parse(args.episode)
            chunks = get_chunks_by_episode(engine, season, episode, args.overwrite)
        except ValueError as e:
            logger.error(str(e))
            return 1
    elif args.chunk:
        chunks = get_specific_chunks(engine, args.chunk, args.overwrite)
    elif args.all:
        chunks = get_all_chunks(engine, args.overwrite)
    elif args.validate:
        # For validation, we want to check all chunks
        chunks = get_all_chunks(engine, True)  # include_processed=True to check all chunks
    
    if not chunks:
        logger.info("No chunks to process, exiting")
        return 0
    
    # Process or validate chunks
    if args.validate:
        validate_chunks(engine, chunks, places_by_zone, args)
    else:
        process_chunks(engine, chunks, places_by_zone, args)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())