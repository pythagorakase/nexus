#!/usr/bin/env python3
"""
Creative Character Expansion Generator

This script generates creative, expanded character profiles for characters with minimal
narrative presence. It uses OpenAI's API to generate rich, detailed character expansions
that are consistent with the existing world and narrative.

Usage:
    python creative_character_expansion.py [OPTIONS]

Options:
    --character ID     Character ID to process (e.g., "42")
                       (Required)
    
    --manual FILE      Use a manually curated context file (JSON) instead of querying
                       the database. This is useful for characters with extensive
                       narrative presence that would exceed API token limits.
    
    --model MODEL      OpenAI model to use. (Default: o3)
                       - Examples: o3, gpt-4o, gpt-4.1, gpt-3.5-turbo
                       - For reasoning models (starting with 'o'), the --effort parameter applies
    
    --temperature VAL  Temperature for standard models (0.0-1.0). (Default: 0.7)
                       Only used for non-reasoning models (not starting with 'o')
                       Higher values (e.g. 0.7) recommended for creative expansion
    
    --effort LEVEL     Reasoning effort for o-prefixed models. (Default: high)
                       Options: 'low', 'medium', 'high'
                       Only used with reasoning models (starting with 'o')
    
    --chunk IDS        Process using specific narrative chunks. Can be:
                       - A single chunk ID (e.g., "123")
                       - A comma-separated list (e.g., "100,101,102")
                       - A range (e.g., "100-110")
                       - 'all' for all chunks
                       - 'auto' to automatically get chunks where character appears
                       If not specified, uses season and episode summaries instead.
    
    --dry-run          Don't save results to the database. Just show what would be generated.
    
    --test             Test mode: Build API payload but don't make the API call.
                       Prints the prompt that would be sent.
    
    --force            Force overwrite existing character details without confirmation prompt.
                       By default, you'll be asked for confirmation (y/n) before 
                       overwriting any existing character details.
    
    --output [FILE]    Save API response to file (still writes to database).
                       If no filename is provided, auto-generates as 
                       'creative_character_expansion_id_XXX.json'
                       
    --input FILE       Take JSON from specified file and write contents to database.
                       Use this to apply previously saved character expansions.
    
    --db-url URL       Database connection URL (optional, defaults to environment variables)

Examples:
    # Generate creative expansion for character with ID 42
    python creative_character_expansion.py --character 42
    
    # Generate creative expansion for the first character out of specified list/range
    python creative_character_expansion.py --character 1,5,9
    python creative_character_expansion.py --character 10-20
    
    # Force update without confirmation prompts
    python creative_character_expansion.py --character 42 --force
    
    # Test mode - show what would be sent to API
    python creative_character_expansion.py --character 42 --test
    
    # Generate expansion based on narrative chunks 100-110
    python creative_character_expansion.py --character 42 --chunk 100-110
    
    # Generate expansion using auto-detected chunks from episodes where the character appears
    python creative_character_expansion.py --character 13 --chunk auto
    
    # Use a manually curated context file with DB character lookup
    python creative_character_expansion.py --character 42 --manual context_alex.json
    
    # Use a manually curated context file instead of auto-generating context
    python creative_character_expansion.py --character 1 --manual context_alex.json
    
    # Dry run - show what would be generated but don't save to database
    python creative_character_expansion.py --character 42 --dry-run
    
    # Save API response to file (with auto-generated filename) while updating database
    python creative_character_expansion.py --character 42 --output
    
    # Save API response to specific file while updating database
    python creative_character_expansion.py --character 42 --output char42_gpt4o.json
    
    # Load character expansion from file and write to database
    python creative_character_expansion.py --input creative_character_expansion_id_042.json
"""

import os
import sys
import json
import time
import argparse
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from pydantic import BaseModel, Field
from datetime import datetime

# Import the OpenAI API utility - we're already in the scripts directory
from api_openai import OpenAIProvider, LLMResponse, get_db_connection_string, setup_abort_handler, is_abort_requested

# Configure logging
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "character_expansion.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.character_expansion")

# Schema for structured output
class CharacterSkill(BaseModel):
    """A character skill or ability."""
    name: str = Field(description="Name of the skill")
    description: Optional[str] = Field(description="Optional description of the skill")

class CharacterConnection(BaseModel):
    """A connection to another character, group, or plot element."""
    name: str = Field(description="Name of the connection (character, group, etc.)")
    relationship: str = Field(description="Description of the relationship")

class ExtraData(BaseModel):
    """Additional character details as structured data."""
    skills: Optional[List[str]] = Field(None, description="Special abilities")
    allies: Optional[List[str]] = Field(None, description="Trusted allies")
    enemies: Optional[List[str]] = Field(None, description="Known adversaries")
    signature_tech: Optional[List[str]] = Field(None, description="Unique tech items")
    connection_points: Optional[List[str]] = Field(None, description="Story hooks")

    class Config:
        """Configure schema generation for OpenAI compatibility."""
        extra = "forbid"  # Equivalent to additionalProperties: false

class CharacterExpansion(BaseModel):
    """Schema for an expanded character profile returned by OpenAI."""
    character_id: int = Field(
        description="ID corresponding to the character being expanded"
    )
    summary: str = Field(
        description="A concise, comprehensive character summary that captures their essence, role, and key characteristics"
    )
    additional_aliases: List[str] = Field(
        default_factory=list,
        description="Additional aliases/nicknames for this character (will be added to existing aliases, not replace them)"
    )
    appearance: str = Field(
        description="Detailed physical description of the character's appearance"
    )
    background: str = Field(
        description="Character's history and backstory"
    )
    personality: str = Field(
        description="Character's personality traits, behaviors, and psychological profile"
    )
    emotional_state: str = Field(
        description="Character's current emotional and psychological state (max 500 chars)"
    )
    current_activity: str = Field(
        description="What the character is currently doing (max 500 chars)"
    )
    current_location: str = Field(
        description="Where the character is currently located (max 500 chars)"
    )
    extra_data: Optional[ExtraData] = Field(None,
        description="Additional character details as structured data (skills, allies, enemies, etc.)"
    )
    
    class Config:
        """Configure schema generation for OpenAI compatibility."""
        extra = "forbid"  # Equivalent to additionalProperties: false

# Single character response is all we need
# Removed CharacterExpansions class for simplification

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate creative character expansions for NEXUS database",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Character selection
    parser.add_argument("--character", required=True, type=int,
                        help="Character ID to process (e.g., 42)")
    
    # LLM options
    parser.add_argument("--model", default="o3",
                        help="Model to use (default: o3)")
    parser.add_argument("--temperature", type=float, default=0.7,
                        help="Temperature for standard models (default: 0.7, higher for creative output)")
    parser.add_argument("--effort", choices=["low", "medium", "high"], default="high",
                        help="Reasoning effort for o-prefixed models (default: high)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't save results to database")
    parser.add_argument("--db-url", 
                        help="Database connection URL (optional, defaults to environment variables)")
    
    # Context options
    context_group = parser.add_mutually_exclusive_group()
    context_group.add_argument("--chunk", 
                              help="Process specific chunks (chunk IDs comma-separated, or range using hyphen, or 'all'). "
                                   "Use 'auto' to automatically get chunks for the character's appearances.")
    context_group.add_argument("--manual", metavar="CONTEXT_FILE",
                              help="Use a manually curated context file (JSON) instead of querying the database.")
    
    # Test mode
    parser.add_argument("--test", action="store_true",
                        help="Test mode: Build API payload but don't make the API call")
    
    # Force overwrite without prompting
    parser.add_argument("--force", action="store_true",
                        help="Force overwrite existing character details without confirmation prompt")
                        
    # Output to file
    parser.add_argument("--output", nargs="?", const="auto", metavar="FILENAME",
                        help="Save API response to file (still writes to database). "
                             "If no filename is provided, auto-generates as 'creative_character_expansion_id_XXX'")
                        
    # Input from file
    parser.add_argument("--input", metavar="FILENAME", 
                        help="Take JSON from specified file and write the contents to database")

    return parser.parse_args()

def connect_to_database(db_url: Optional[str] = None) -> sa.engine.Engine:
    """
    Connect to the NEXUS database using SQLAlchemy.
    
    Args:
        db_url: Optional database URL. If not provided, uses environment variables.
        
    Returns:
        SQLAlchemy engine connected to the database
    """
    # Get connection string
    if not db_url:
        db_url = get_db_connection_string()
    
    # Create engine
    engine = create_engine(db_url)
    
    # Test connection
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            logger.info(f"Connected to PostgreSQL: {version}")
        return engine
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def get_character(engine: sa.engine.Engine, character_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Get character information from the database.
    
    Args:
        engine: Database connection engine
        character_id: Character ID to fetch
        
    Returns:
        Tuple of (target_character, all_characters)
    """
    # Get all characters for the roster
    all_query = """
    SELECT c.id, c.name, 
           COALESCE(ARRAY_AGG(DISTINCT ca.alias ORDER BY ca.alias) FILTER (WHERE ca.alias IS NOT NULL), ARRAY[]::text[]) AS aliases,
           c.summary
    FROM characters c
    LEFT JOIN character_aliases ca ON c.id = ca.character_id
    GROUP BY c.id, c.name, c.summary
    ORDER BY c.id
    """
    
    # Get the specific target character
    target_query = """
    SELECT c.id, c.name, 
           COALESCE(ARRAY_AGG(DISTINCT ca.alias ORDER BY ca.alias) FILTER (WHERE ca.alias IS NOT NULL), ARRAY[]::text[]) AS aliases,
           c.summary, c.appearance, c.background, c.personality, 
           c.emotional_state, c.current_activity, c.current_location, 
           c.extra_data
    FROM characters c
    LEFT JOIN character_aliases ca ON c.id = ca.character_id
    WHERE c.id = :character_id
    GROUP BY c.id, c.name, c.summary, c.appearance, c.background, 
             c.personality, c.emotional_state, c.current_activity, 
             c.current_location, c.extra_data
    """
    
    # Execute queries
    with engine.connect() as conn:
        # Get all characters
        all_result = conn.execute(text(all_query))
        all_characters = [dict(row._mapping) for row in all_result]
        
        # Get target character
        target_result = conn.execute(text(target_query), {"character_id": character_id})
        target_character_row = target_result.fetchone()
        
        if target_character_row:
            target_character = dict(target_character_row._mapping)
            logger.info(f"Retrieved character ID: {target_character['id']}, Name: {target_character['name']}")
        else:
            target_character = None
            logger.warning(f"No character found for ID {character_id}")
    
    logger.info(f"Retrieved {len(all_characters)} total characters in roster")
    
    return target_character, all_characters

def get_season_summaries(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """
    Get all season summaries from the database.
    
    Args:
        engine: Database connection engine
        
    Returns:
        List of season summary dictionaries with extracted info from JSONB
    """
    query = """
    SELECT id, 
           summary->'OVERVIEW' as overview,
           summary
    FROM seasons
    WHERE summary IS NOT NULL AND summary != '{}'
    ORDER BY id
    """
    
    # Execute query
    with engine.connect() as conn:
        result = conn.execute(text(query))
        summaries = [dict(row._mapping) for row in result]
    
    logger.info(f"Retrieved {len(summaries)} season summaries from database")
    return summaries

def get_episode_summaries(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """
    Get all episode summaries from the database.
    
    Args:
        engine: Database connection engine
        
    Returns:
        List of episode summary dictionaries
    """
    query = """
    SELECT season, 
           episode, 
           summary->'OVERVIEW' as overview,
           summary
    FROM episodes
    WHERE summary IS NOT NULL AND summary != '{}'
    ORDER BY season, episode
    """
    
    # Execute query
    with engine.connect() as conn:
        result = conn.execute(text(query))
        summaries = [dict(row._mapping) for row in result]
    
    logger.info(f"Retrieved {len(summaries)} episode summaries from database")
    return summaries

def get_character_episode_spans(engine: sa.engine.Engine, character_id: int) -> List[Dict[str, Any]]:
    """
    Get episode spans for a character based on their appearances.
    
    This function:
    1. Gets the chunks where a character appears from chunk_character_references
    2. Identifies the episodes containing those chunks
    3. Returns complete episode spans for all episodes where the character appears
    
    Args:
        engine: Database connection engine
        character_id: Character ID to find episodes for
        
    Returns:
        List of dictionaries with season, episode, start_chunk, end_chunk
    """
    # First, get the chunks where the character appears (present only)
    chunks_query = """
    SELECT ARRAY_AGG(chunk_id ORDER BY chunk_id) as chunks_in
    FROM chunk_character_references
    WHERE character_id = :character_id AND reference = 'present'
    """
    
    chunks_in = []
    with engine.connect() as conn:
        result = conn.execute(text(chunks_query), {"character_id": character_id})
        row = result.fetchone()
        if row and row[0]:
            chunks_in = row[0]  # This is a PostgreSQL array
    
    if not chunks_in:
        logger.warning(f"No chunks found where character {character_id} appears")
        return []
    
    # Get the episodes for these chunks
    episodes_query = """
    SELECT DISTINCT season, episode
    FROM chunk_metadata
    WHERE chunk_id IN :chunks
    ORDER BY season, episode
    """
    
    episodes = []
    with engine.connect() as conn:
        result = conn.execute(text(episodes_query), {"chunks": tuple(chunks_in)})
        episodes = [dict(row._mapping) for row in result]
    
    if not episodes:
        logger.warning(f"No episodes found for chunks {chunks_in}")
        return []
    
    # For each episode, get the full span of chunks
    episode_spans = []
    for ep in episodes:
        span_query = """
        SELECT 
            MIN(chunk_id) as start_chunk,
            MAX(chunk_id) as end_chunk
        FROM chunk_metadata
        WHERE season = :season AND episode = :episode
        """
        
        with engine.connect() as conn:
            result = conn.execute(
                text(span_query), 
                {"season": ep['season'], "episode": ep['episode']}
            )
            span = result.fetchone()
            if span:
                episode_spans.append({
                    "season": ep['season'],
                    "episode": ep['episode'],
                    "start_chunk": span[0],
                    "end_chunk": span[1]
                })
    
    logger.info(f"Found {len(episode_spans)} episode spans for character {character_id}")
    for span in episode_spans:
        # Convert to int if these are strings from the database
        season = int(span['season']) if isinstance(span['season'], (str, float)) else span['season']
        episode = int(span['episode']) if isinstance(span['episode'], (str, float)) else span['episode']
        logger.info(f"S{season:02d}E{episode:02d}: chunks {span['start_chunk']}-{span['end_chunk']}")
    
    return episode_spans

def get_narrative_chunks(engine: sa.engine.Engine, chunk_ids: Optional[str] = None, character_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get narrative chunks from the database.
    
    Args:
        engine: Database connection engine
        chunk_ids: Optional chunk IDs to filter by (comma-separated, range, 'all', or 'auto')
        character_id: Optional character ID when using 'auto' mode
        
    Returns:
        List of narrative chunk dictionaries
    """
    query = """
    SELECT nc.id, nc.raw_text, cm.season, cm.episode
    FROM narrative_chunks nc
    LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
    """
    
    # Handle auto mode - get episode spans for character
    if chunk_ids and chunk_ids.lower() == "auto" and character_id:
        logger.info(f"Using auto mode to get episode spans for character {character_id}")
        episode_spans = get_character_episode_spans(engine, character_id)
        
        if not episode_spans:
            logger.warning(f"No episode spans found for character {character_id}")
            return []
        
        # Combine all episode spans into a complex WHERE clause
        span_conditions = []
        for span in episode_spans:
            span_conditions.append(
                f"(nc.id >= {span['start_chunk']} AND nc.id <= {span['end_chunk']})"
            )
        
        if span_conditions:
            query += " WHERE " + " OR ".join(span_conditions)
    
    # Process normal chunk_ids argument
    elif chunk_ids:
        if chunk_ids.lower() == "all":
            # All chunks, no filtering needed
            pass
        elif "," in chunk_ids:
            # Comma-separated list of IDs
            id_list = [id.strip() for id in chunk_ids.split(",")]
            query += f" WHERE nc.id IN ({','.join(id_list)})"
        elif "-" in chunk_ids:
            # Range of IDs
            start, end = map(str.strip, chunk_ids.split("-"))
            query += f" WHERE nc.id >= {start} AND nc.id <= {end}"
        else:
            # Single ID
            query += f" WHERE nc.id = {chunk_ids.strip()}"
    
    query += " ORDER BY cm.season, cm.episode, nc.id"
    
    # Execute query
    with engine.connect() as conn:
        result = conn.execute(text(query))
        chunks = [dict(row._mapping) for row in result]
    
    logger.info(f"Retrieved {len(chunks)} narrative chunks from database")
    return chunks

def update_character_expansion(engine: sa.engine.Engine, character_expansion: CharacterExpansion) -> bool:
    """
    Update a character's expanded profile in the database.
    
    Args:
        engine: Database connection engine
        character_expansion: Character expansion data to update
        
    Returns:
        True if successful, False otherwise
    """
    # First get existing aliases if we need to update them
    existing_aliases = []
    if character_expansion.additional_aliases:
        # Query to get existing aliases from normalized table
        alias_query = """
        SELECT ARRAY_AGG(alias ORDER BY alias) as aliases
        FROM character_aliases 
        WHERE character_id = :id
        """
        try:
            with engine.connect() as conn:
                result = conn.execute(text(alias_query), {"id": character_expansion.character_id})
                row = result.fetchone()
                if row and row[0]:
                    existing_aliases = row[0]  # PostgreSQL array
        except Exception as e:
            logger.warning(f"Failed to retrieve existing aliases: {e}")
    
    # Handle new aliases if any were specified
    if character_expansion.additional_aliases:
        # Insert new aliases that don't already exist
        for alias in character_expansion.additional_aliases:
            if alias not in existing_aliases:
                insert_alias_query = """
                INSERT INTO character_aliases (character_id, alias)
                VALUES (:character_id, :alias)
                ON CONFLICT (character_id, alias) DO NOTHING
                """
                try:
                    with engine.connect() as conn:
                        conn.execute(text(insert_alias_query), 
                                   {"character_id": character_expansion.character_id, "alias": alias})
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to insert alias '{alias}': {e}")
    
    # Update query (no aliases column anymore)
    query = """
    UPDATE characters
    SET summary = :summary,
        appearance = :appearance,
        background = :background,
        personality = :personality,
        emotional_state = :emotional_state,
        current_activity = :current_activity,
        current_location = :current_location,
        extra_data = cast(:extra_data as jsonb),
        updated_at = NOW()
    WHERE id = :id
    """
    
    # Convert extra_data to JSON string
    extra_data_dict = character_expansion.extra_data.model_dump(exclude_none=True) if character_expansion.extra_data else {}
    extra_data_json = json.dumps(extra_data_dict)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(query),
                {
                    "id": character_expansion.character_id,
                    "summary": character_expansion.summary,
                    "appearance": character_expansion.appearance,
                    "background": character_expansion.background,
                    "personality": character_expansion.personality,
                    "emotional_state": character_expansion.emotional_state[:500] if character_expansion.emotional_state else None,
                    "current_activity": character_expansion.current_activity[:500] if character_expansion.current_activity else None,
                    "current_location": character_expansion.current_location[:500] if character_expansion.current_location else None,
                    "extra_data": extra_data_json
                }
            )
            conn.commit()
            
        logger.info(f"Updated expansion for character ID {character_expansion.character_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to update expansion for character {character_expansion.character_id}: {e}")
        return False

def prepare_target_character_section(target_character: Dict[str, Any]) -> str:
    """
    Prepare the target character section for non-manual modes.
    
    Args:
        target_character: Dictionary with character data from database
        
    Returns:
        Target character section formatted for the prompt
    """
    target_section = "## Target Character for Creative Expansion\n\n"
    
    # Include what we know about the target character
    target_section += f"### Character ID: {target_character['id']} ({target_character['name']})\n\n"
    
    # Include aliases if available
    if target_character.get('aliases') and target_character['aliases']:
        target_section += f"Aliases: {', '.join(target_character['aliases'])}\n\n"
    
    # Include summary if available
    if target_character['summary']:
        target_section += f"Existing Summary:\n{target_character['summary']}\n\n"
    else:
        target_section += "This character has no existing summary.\n\n"
    
    return target_section

def prepare_character_from_json(context_data: Dict[str, Any], target_character_id: int) -> str:
    """
    Prepare character data directly from the JSON file, including only the target character.
    
    Args:
        context_data: Dictionary from the manual context JSON file
        target_character_id: ID of the character to expand
        
    Returns:
        Character data formatted for the prompt
    """
    target_section = "## Target Character for Creative Expansion\n\n"
    
    # Get character data from the JSON (as string ID)
    char_id_str = str(target_character_id)
    if "characters" in context_data and char_id_str in context_data["characters"]:
        char_data = context_data["characters"][char_id_str]
        target_section += json.dumps({char_id_str: char_data}, indent=2) + "\n\n"
    else:
        logger.warning(f"Character ID {target_character_id} not found in manual context file")
        target_section += f"Character ID {target_character_id} not found in context file.\n\n"
    
    return target_section

def prepare_manual_context(context_data: Dict[str, Any]) -> str:
    """
    Prepare context text from a manually curated context file.
    Simply extracts the characters, seasons, and episodes objects as JSON.
    
    Args:
        context_data: Dictionary with context data from a manual context file
        
    Returns:
        Formatted context text ready for the prompt
    """
    context = "## Manual Context\n\n"
    
    # Characters object
    if "characters" in context_data:
        context += "### Characters\n\n"
        context += json.dumps(context_data["characters"], indent=2) + "\n\n"
    
    # Seasons object
    if "seasons" in context_data:
        context += "### Seasons\n\n"
        context += json.dumps(context_data["seasons"], indent=2) + "\n\n"
    
    # Episodes object
    if "episodes" in context_data:
        context += "### Episodes\n\n"
        context += json.dumps(context_data["episodes"], indent=2) + "\n\n"
    
    return context

def prepare_summaries_context(season_summaries: List[Dict[str, Any]], episode_summaries: List[Dict[str, Any]]) -> str:
    """
    Prepare the context from season and episode summaries.
    
    Args:
        season_summaries: List of season summary dictionaries
        episode_summaries: List of episode summary dictionaries
        
    Returns:
        Formatted context text
    """
    context = "## Season and Episode Summaries\n\n"
    
    # Group episodes by season
    episodes_by_season = {}
    for episode in episode_summaries:
        season_id = episode['season']
        if season_id not in episodes_by_season:
            episodes_by_season[season_id] = []
        episodes_by_season[season_id].append(episode)
    
    # Add summaries in proper order
    for season in sorted(season_summaries, key=lambda x: x['id']):
        season_id = season['id']
        
        # Use the full JSONB summary
        # Convert to int if string from database
        season_num = int(season_id) if isinstance(season_id, (str, float)) else season_id
        context += f"### Season {season_num:02d}\n\n"
        
        # Format the full JSON summary for better readability
        if season['summary'] is not None:
            if isinstance(season['summary'], (dict, list)):
                # Transform the summary into a more readable format
                season_summary_str = json.dumps(season['summary'], indent=2)
                # Replace outer {} to look nicer in prompt
                season_summary_str = season_summary_str.replace("{\n", "").replace("\n}", "")
                context += f"{season_summary_str}\n\n"
            else:
                context += f"{season['summary']}\n\n"
        
        # Add episodes for this season
        if season_id in episodes_by_season:
            for episode in sorted(episodes_by_season[season_id], key=lambda x: x['episode']):
                # Convert to int if string from database
                season_num = int(season_id) if isinstance(season_id, (str, float)) else season_id
                episode_num = int(episode['episode']) if isinstance(episode['episode'], (str, float)) else episode['episode']
                context += f"#### S{season_num:02d}E{episode_num:02d}\n\n"
                
                # Format the full JSON episode summary
                if episode['summary'] is not None:
                    if isinstance(episode['summary'], (dict, list)):
                        # Transform the summary into a more readable format
                        episode_summary_str = json.dumps(episode['summary'], indent=2)
                        # Replace outer {} to look nicer in prompt
                        episode_summary_str = episode_summary_str.replace("{\n", "").replace("\n}", "")
                        context += f"{episode_summary_str}\n\n"
                    else:
                        context += f"{episode['summary']}\n\n"
    
    return context

def prepare_chunks_context(chunks: List[Dict[str, Any]]) -> str:
    """
    Prepare the context from narrative chunks.
    
    Args:
        chunks: List of narrative chunk dictionaries
        
    Returns:
        Formatted context text
    """
    context = "## Narrative Chunks\n\n"
    
    for chunk in chunks:
        season_num = chunk.get('season')
        episode_num = chunk.get('episode')
        
        if season_num and episode_num:
            # Convert to int if string
            if isinstance(season_num, str):
                season_num = int(season_num) if season_num.isdigit() else 0
            if isinstance(episode_num, str):
                episode_num = int(episode_num) if episode_num.isdigit() else 0
            context += f"### Chunk ID: {chunk['id']} (S{season_num:02d}E{episode_num:02d})\n\n"
        else:
            context += f"### Chunk ID: {chunk['id']}\n\n"
            
        context += f"{chunk['raw_text']}\n\n"
    
    return context

def load_prompt_from_json(prompt_file: str) -> Dict[str, Any]:
    """
    Load the prompt from a JSON file.
    
    Args:
        prompt_file: Path to the JSON file
        
    Returns:
        Dictionary with prompt components
    """
    # Load from scripts directory
    prompt_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        prompt_file
    )
    
    try:
        with open(prompt_path, 'r') as f:
            prompt_data = json.load(f)
        logger.info(f"Loaded prompt from {prompt_path}")
        return prompt_data
    except Exception as e:
        logger.error(f"Failed to load prompt from {prompt_path}: {e}")
        raise

def load_manual_context(context_file: str) -> Dict[str, Any]:
    """
    Load a manually curated context file for character expansion.
    
    Args:
        context_file: Path to the context JSON file
        
    Returns:
        Dictionary with context data including characters, places, seasons, etc.
    """
    # Handle both absolute paths and relative paths from current directory
    if os.path.isabs(context_file):
        context_path = context_file
    else:
        context_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            context_file
        )
    
    try:
        with open(context_path, 'r') as f:
            context_data = json.load(f)
        logger.info(f"Loaded manual context from {context_path}")
        
        # Validate that the file contains expected sections
        required_sections = ["characters"]
        for section in required_sections:
            if section not in context_data:
                logger.warning(f"Manual context file is missing required section: {section}")
        
        return context_data
    except Exception as e:
        logger.error(f"Failed to load manual context from {context_path}: {e}")
        raise

def build_prompt(prompt_data: Dict[str, Any], 
                target_characters: str,
                context: str) -> str:
    """
    Build the complete prompt for the API.
    
    Args:
        prompt_data: Dictionary with prompt components
        target_characters: Formatted target characters section (from JSON)
        context: Formatted context text
        
    Returns:
        Complete prompt text
    """
    # Combine prompt components
    system_prompt = prompt_data.get("system_prompt", "")
    
    # Handle main_instructions which might be a list
    main_instructions = prompt_data.get("main_instructions", "")
    if isinstance(main_instructions, list):
        main_instructions = "\n".join(main_instructions)
    
    # Get other prompt components
    special_instructions = prompt_data.get("special_instructions", "")
    
    # Handle example which is a before/after comparison
    examples_text = ""
    example = prompt_data.get("example", {})
    if example:
        examples_text = "## Example\n\n"
        examples_text += f"### Before:\n{example.get('before', '')}\n\n"
        examples_text += f"### After:\n"
        
        # Format the after example to match our expected output structure
        after = example.get('after', {})
        if after:
            for field, value in after.items():
                if field == 'extra_data' and isinstance(value, dict):
                    examples_text += f"#### {field}:\n```json\n{json.dumps(value, indent=2)}\n```\n\n"
                else:
                    examples_text += f"#### {field}:\n{value}\n\n"
    
    # Build the title 
    title = "Character Creative Expansion Task"
    
    # Store target characters original content for repeating at the end
    target_summaries = ""
    # Extract just the summaries part from target_characters for repeating at the end
    lines = target_characters.split("\n")
    capturing = False
    current_char = ""
    
    for line in lines:
        if line.startswith("### Character ID:"):
            capturing = True
            current_char = line
            target_summaries += f"{line}\n\n"
        elif capturing and line.startswith("Existing Summary:"):
            target_summaries += "Existing Summary:\n"
        elif capturing and line.startswith("```"):
            if "```\n\n" in target_summaries:
                # This is the end of a summary block
                target_summaries += "```\n\n"
            else:
                # This is the beginning of a summary block
                target_summaries += "```\n"
        elif capturing and not line.startswith("```") and not line.strip() == "":
            # Inside a summary block
            target_summaries += f"{line}\n"
    
    # Build the first part of the prompt
    first_part = f"""# {title}

System: {system_prompt}

## Instructions
{main_instructions}

"""
    
    # Add special instructions if they exist
    if special_instructions:
        first_part += f"## Special Notes\n{special_instructions}\n\n"
    
    # Add examples, target characters, and context (no roster)
    first_part += f"""{examples_text}
{target_characters}
{context}
"""

    # Build the repeated part (entire prompt structure again)
    repeated_part = f"""# {title} (REPEATED)

System: {system_prompt}

## Instructions
{main_instructions}

"""
    
    # Add special instructions if they exist in the repeated part too
    if special_instructions:
        repeated_part += f"## Special Notes\n{special_instructions}\n\n"
    
    # Add examples to repeated part
    repeated_part += f"{examples_text}\n"
    
    # Add the target characters section again for manual mode
    repeated_part += f"{target_characters}"
    
    # Combine both parts
    prompt = first_part + repeated_part
    
    return prompt

def save_expansion_to_file(character_expansion: CharacterExpansion, filename: Optional[str] = None) -> str:
    """
    Save the character expansion to a file.
    
    Args:
        character_expansion: The parsed API response for a single character
        filename: Optional filename to save to. If not provided, auto-generates based on character ID
        
    Returns:
        Path to the saved file
    """
    # If filename is "auto" or None, generate a filename based on character ID
    if not filename or filename == "auto":
        # Get character ID and format for filename
        char_id = str(character_expansion.character_id).zfill(3)
        filename = f"creative_character_expansion_id_{char_id}.json"
    
    # Make sure filename has .json extension
    if not filename.endswith('.json'):
        filename += '.json'
    
    # Convert to dict for JSON serialization
    response_dict = character_expansion.model_dump()
    
    # Save to file
    with open(filename, 'w') as f:
        json.dump(response_dict, f, indent=2)
    
    logger.info(f"Saved character expansion to {filename}")
    return filename

def load_expansion_from_file(filename: str) -> CharacterExpansion:
    """
    Load a character expansion from a file.
    
    Args:
        filename: Path to the file to load
        
    Returns:
        Parsed character expansion data
    """
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        
        # Check if this is an old format file (with 'characters' list)
        if 'characters' in data and isinstance(data['characters'], list) and len(data['characters']) > 0:
            # Extract the first character from the old format
            character_data = data['characters'][0]
            logger.info(f"Converting legacy format from {filename} (multiple characters) to single character")
        else:
            # Assume this is already a single character expansion
            character_data = data
            
        # Parse the data using Pydantic
        character_expansion = CharacterExpansion.model_validate(character_data)
        logger.info(f"Loaded character expansion from {filename} for character ID {character_expansion.character_id}")
        return character_expansion
    except Exception as e:
        logger.error(f"Failed to load character expansion from {filename}: {e}")
        raise

def process_character_expansion(character_expansion: CharacterExpansion, 
                               character_data: Dict[str, Any],
                               engine: sa.engine.Engine,
                               dry_run: bool = False,
                               force: bool = False,
                               output_file: Optional[str] = None) -> bool:
    """
    Process a single character expansion and update the database.
    
    Args:
        character_expansion: Parsed API response for a single character
        character_data: Dictionary with character data
        engine: Database connection engine
        dry_run: If True, don't update the database
        force: If True, overwrite existing character details without asking
        output_file: If provided, save the response to file
        
    Returns:
        True if successfully updated, False otherwise
    """
    # If output_file is provided, save the response to file
    if output_file:
        save_expansion_to_file(character_expansion, output_file)
    
    char_id = character_expansion.character_id
    char_name = character_data['name']
    
    # Check if any expansion fields already exist
    has_existing_data = (
        (character_data.get('appearance') and character_data['appearance'].strip()) or
        (character_data.get('background') and character_data['background'].strip() and character_data['background'] != 'unknown') or
        (character_data.get('personality') and character_data['personality'].strip()) or
        (character_data.get('emotional_state') and character_data['emotional_state'].strip()) or
        (character_data.get('current_activity') and character_data['current_activity'].strip()) or
        (character_data.get('current_location') and character_data['current_location'].strip()) or
        (character_data.get('extra_data') and character_data['extra_data'])
    )
    
    # Print the expansion we've generated
    logger.info(f"Expansion for character {char_id} ({char_name}):")
    logger.info("---")
    
    # Show summary first since it's the main addition
    logger.info(f"Summary: {character_expansion.summary[:200]}...")
    
    # Show additional aliases if provided
    if character_expansion.additional_aliases:
        logger.info(f"Additional Aliases: {', '.join(character_expansion.additional_aliases)}")
        
    logger.info(f"Appearance: {character_expansion.appearance[:100]}...")
    logger.info(f"Background: {character_expansion.background[:100]}...")
    logger.info(f"Personality: {character_expansion.personality[:100]}...")
    logger.info(f"Emotional State: {character_expansion.emotional_state}")
    logger.info(f"Current Activity: {character_expansion.current_activity}")
    logger.info(f"Current Location: {character_expansion.current_location}")
    
    # Format extra_data logging
    if character_expansion.extra_data:
        extra_data_dict = character_expansion.extra_data.model_dump(exclude_none=True)
        if extra_data_dict:
            logger.info("Extra Data:")
            for key, values in extra_data_dict.items():
                if values:
                    logger.info(f"  {key.title()}:")
                    for item in values:
                        logger.info(f"    - {item}")
    logger.info("---")
    
    # Check if we need to confirm before overwriting
    if has_existing_data and not force and not dry_run:
        # Ask for confirmation before overwriting
        print(f"\nCharacter {char_id} ({char_name}) already has some expansion data. Overwrite?")
        print("---")
        
        if character_data.get('appearance'):
            print(f"Current Appearance: {character_data['appearance'][:100]}...")
        if character_data.get('background') and character_data['background'] != 'unknown':
            print(f"Current Background: {character_data['background'][:100]}...")
        if character_data.get('personality'):
            print(f"Current Personality: {character_data['personality'][:100]}...")
        
        print("---")
        print("New Expansion Excerpt:")
        # Show summary first since it's the main addition
        print(f"Summary: {character_expansion.summary[:200]}...")
        
        # Show additional aliases if provided
        if character_expansion.additional_aliases:
            print(f"Additional Aliases: {', '.join(character_expansion.additional_aliases)}")
            
        print(f"Appearance: {character_expansion.appearance[:100]}...")
        print(f"Background: {character_expansion.background[:100]}...")
        print(f"Personality: {character_expansion.personality[:100]}...")
        if character_expansion.extra_data:
            extra_data_dict = character_expansion.extra_data.model_dump(exclude_none=True)
            if extra_data_dict:
                print("Extra Data:")
                for key, values in extra_data_dict.items():
                    if values:
                        print(f"  {key.title()}:")
                        for item in values:
                            print(f"    - {item}")
        print("---")
        
        response = input(f"Overwrite existing data for {char_name}? (y/n): ").strip().lower()
        if response != 'y':
            logger.info(f"Skipping update for character {char_id} ({char_name})")
            return False
    
    # Update the database
    if not dry_run:
        success = update_character_expansion(engine, character_expansion)
        if success:
            logger.info(f"Successfully updated expansion for character {char_id} ({char_name})")
            return True
        else:
            logger.warning(f"Failed to update expansion for character {char_id} ({char_name})")
            return False
    else:
        logger.info(f"DRY RUN: Would update character {char_id} ({char_name})")
        return True

def generate_expansions(
    api_provider: OpenAIProvider,
    target_character: Dict[str, Any],
    all_characters: List[Dict[str, Any]],
    engine: sa.engine.Engine,
    args: argparse.Namespace
) -> Tuple[int, int]:
    """
    Generate creative expansion for a single character using the API and update the database.
    
    Args:
        api_provider: OpenAI API provider
        target_character: Character to generate expansion for
        all_characters: All characters in the database for context
        engine: Database connection engine
        args: Command line arguments
        
    Returns:
        Tuple of (success_count, total_characters: always 1)
    """
    if not target_character:
        logger.warning("No target character to process")
        return 0, 0
    
    # Load the prompt template
    prompt_data = load_prompt_from_json("creative_character_expansion.json")
    
    # Prepare context based on arguments
    if args.manual:
        # Load the manual context
        manual_context_data = load_manual_context(args.manual)
        
        # Get character data directly from the JSON for manual mode
        target_character_section = prepare_character_from_json(manual_context_data, target_character["id"])
        
        # Prepare context from the JSON
        context = prepare_manual_context(manual_context_data)
        logger.info(f"Using manual context from {args.manual}")
    else:
        # For non-manual modes, prepare character from database (no roster)
        target_character_section = prepare_target_character_section(target_character)
        
        # Handle chunk/summary context
        if args.chunk:
            # Special handling for auto mode
            if args.chunk.lower() == "auto":
                # Auto mode for a single character
                chunks = get_narrative_chunks(engine, "auto", target_character["id"])
                context = prepare_chunks_context(chunks)
            else:
                # Regular chunk mode
                chunks = get_narrative_chunks(engine, args.chunk)
                context = prepare_chunks_context(chunks)
        else:
            # Use summaries (default behavior)
            season_summaries = get_season_summaries(engine)
            episode_summaries = get_episode_summaries(engine)
            context = prepare_summaries_context(season_summaries, episode_summaries)
    
    # Build complete prompt (no roster)
    prompt = build_prompt(
        prompt_data, 
        target_character_section, 
        context
    )
    
    # Token count and performance metrics
    prompt_tokens = api_provider.count_tokens(prompt)
    logger.info(f"Prompt size: {prompt_tokens} tokens")
    
    # For test mode, print the prompt and exit
    if args.test:
        logger.info("TEST MODE: Printing prompt that would be sent to API")
        print("\n" + "="*80 + "\n")
        print(prompt)
        print("\n" + "="*80 + "\n")
        print(f"Total tokens in prompt: {prompt_tokens}")
        print("="*80 + "\n")
        return 0, 1
    
    # Make API call for structured output
    start_time = time.time()
    
    try:
        # Format the messages for the API call
        messages = []
        if api_provider.system_prompt:
            messages.append({"role": "system", "content": api_provider.system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        logger.info(f"Using OpenAI with model {args.model}")
        
        # Using responses.parse() with our Pydantic model
        if args.model.startswith("o"):
            # For reasoning models, include reasoning parameter
            response = api_provider.client.responses.parse(
                model=args.model,
                input=messages,
                reasoning={"effort": args.effort} if args.effort else None,
                text_format=CharacterExpansion  # Use the CharacterExpansion model directly
            )
        else:
            # For standard models, include temperature
            response = api_provider.client.responses.parse(
                model=args.model,
                input=messages,
                temperature=args.temperature,
                text_format=CharacterExpansion  # Use the CharacterExpansion model directly
            )
        
        # Get the parsed Pydantic object directly
        result = response.output_parsed
        
        # Check if the result is None
        if result is None:
            logger.error("API response parsing failed - output_parsed is None")
            logger.error(f"Raw response output_text: {response.output_text[:500]}...")
            logger.error(f"Response status: {response}")
            return 0, 1
        
        # Create a compatible response object for metrics
        llm_response = LLMResponse(
            content=response.output_text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=args.model,
            raw_response=response
        )
        
        # Log performance metrics
        elapsed_time = time.time() - start_time
        logger.info(f"API call completed in {elapsed_time:.2f} seconds")
        logger.info(f"Input tokens: {llm_response.input_tokens}, Output tokens: {llm_response.output_tokens}")
        logger.info(f"Generated expansion for character ID {result.character_id}")
        
        # Process the result
        updated = process_character_expansion(
            result, 
            target_character, 
            engine, 
            args.dry_run,
            args.force,
            args.output
        )
        updated_count = 1 if updated else 0
        
        return updated_count, 1
    
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return 0, 1

def main():
    """Main function."""
    # Parse arguments
    args = parse_arguments()
    
    # Set up abort handler
    setup_abort_handler("Abort requested! Will finish current operation and stop.")
    
    try:
        # Connect to database
        engine = connect_to_database(args.db_url)
        
        # Check for --input parameter (load from file)
        if args.input:
            logger.info(f"Loading character expansion from file: {args.input}")
            
            # Load the expansion from file
            character_expansion = load_expansion_from_file(args.input)
            
            # Get character ID from the file
            char_id = character_expansion.character_id
            
            # Retrieve character data for this ID
            target_character, all_characters = get_character(engine, char_id)
            if not target_character:
                logger.warning(f"No matching character found in database for ID {char_id}")
                return 1
            
            
            # Process the loaded character expansion
            success = process_character_expansion(
                character_expansion,
                target_character,
                engine,
                args.dry_run,
                args.force
            )
            
            logger.info(f"Successfully imported and updated character ID {char_id}" if success else 
                       f"Failed to update character ID {char_id}")
            return 0 if success else 1
        
        # Initialize target character and all characters
        target_character = None
        all_characters = []
        
        # Normal flow (generate expansions using DB query)
        # Retrieve character from database
        target_character, all_characters = get_character(engine, args.character)
        
        if not target_character:
            logger.warning(f"No character found for ID {args.character}")
            return 1
        
        # Display character info
        logger.info(f"Processing character ID: {target_character['id']}, Name: {target_character['name']}")
        
        # Initialize OpenAI provider with appropriate parameters
        # For reasoning models (those starting with 'o'), don't pass temperature
        if args.model.startswith("o"):
            logger.info(f"Using reasoning model: {args.model} with effort: {args.effort}")
            # Use reasoning_effort parameter instead of temperature
            api_provider = OpenAIProvider(
                model=args.model,
                reasoning_effort=args.effort
            )
        else:
            logger.info(f"Using standard model: {args.model} with temperature: {args.temperature}")
            api_provider = OpenAIProvider(
                model=args.model,
                temperature=args.temperature
            )
        
        # Generate creative expansion for the target character
        success_count, total_count = generate_expansions(
            api_provider, 
            target_character,
            all_characters,
            engine, 
            args
        )
        
        # Log results
        logger.info(f"Successfully expanded character: {success_count > 0}")
        
        return 0 if success_count > 0 else 1
    
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())