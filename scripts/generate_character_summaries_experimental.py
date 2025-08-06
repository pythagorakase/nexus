#!/usr/bin/env python3
"""
Character Summary Generator

This script generates concise character summaries for the NEXUS database
by analyzing season and episode summaries. It uses OpenAI's API to generate
summaries of appropriate length based on character importance.

The script utilizes OpenAI's structured output capabilities via the responses.parse() API,
which allows for reliable generation of structured character summary data. It supports
processing multiple characters at once through an array-based schema approach.

Usage:
    python generate_character_summaries_experimental.py [OPTIONS]

Options:
    --character ID/IDS Character ID(s) to process. Can be:
                       - A single ID number (e.g., "42")
                       - A comma-separated list (e.g., "1,5,9")
                       - A range using hyphen (e.g., "1-5")
                       - 'all' to process all characters missing summaries
                       (Required)
    
    --model MODEL      OpenAI model to use. (Default: o3)
                       - Examples: o3, gpt-4o, gpt-4.1, gpt-3.5-turbo
                       - For reasoning models (starting with 'o'), the --effort parameter applies
    
    --temperature VAL  Temperature for standard models (0.0-1.0). (Default: 0.2)
                       Only used for non-reasoning models (not starting with 'o')
    
    --effort LEVEL     Reasoning effort for o-prefixed models. (Default: high)
                       Options: 'low', 'medium', 'high'
                       Only used with reasoning models (starting with 'o')
    
    --chunk IDS        Process using specific narrative chunks. Can be:
                       - A single chunk ID (e.g., "123")
                       - A comma-separated list (e.g., "100,101,102")
                       - A range (e.g., "100-110")
                       - 'all' for all chunks
                       If not specified, uses season and episode summaries instead.
    
    --dry-run          Don't save results to the database. Just show what would be generated.
    
    --test             Test mode: Build API payload but don't make the API call.
                       Prints the prompt that would be sent.
    
    --force            Force overwrite existing summaries without confirmation prompt.
                       By default, you'll be asked for confirmation (y/n) before 
                       overwriting an existing summary.
    
    --update           Update mode: Improve existing summaries by adding details and
                       correcting inaccuracies. Only processes characters WITH existing
                       summaries. Adds the current summary to the prompt for improvement.
    
    --db-url URL       Database connection URL (optional, defaults to environment variables)

Examples:
    # Generate summary for character with ID 42
    python generate_character_summaries_experimental.py --character 42
    
    # Generate summaries for characters 1, 5, and 9
    python generate_character_summaries_experimental.py --character 1,5,9
    
    # Generate summaries for characters 10 through 20
    python generate_character_summaries_experimental.py --character 10-20
    
    # Generate summaries for all characters without summaries
    python generate_character_summaries_experimental.py --character all
    
    # Update existing summary for character 42
    python generate_character_summaries_experimental.py --character 42 --update
    
    # Update summaries for all characters that have existing summaries
    python generate_character_summaries_experimental.py --character all --update
    
    # Update a character summary using auto-detected chunks from episodes where they appear
    python generate_character_summaries_experimental.py --character 13 --update --chunk auto
    
    # Force update without confirmation prompts
    python generate_character_summaries_experimental.py --character 1,2,3 --update --force
    
    # Test mode - show what would be sent to API (works with update mode too)
    python generate_character_summaries_experimental.py --character 42 --update --test
    
    # Generate summaries based on narrative chunks 100-110
    python generate_character_summaries_experimental.py --character all --chunk 100-110
    
    # Dry run - show what would be generated but don't save to database
    python generate_character_summaries_experimental.py --character 1-5 --dry-run
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
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "character_summaries.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.character_summaries")

# Schema for structured output
class CharacterSummary(BaseModel):
    """Schema for an individual character summary."""
    character_id: int = Field(
        description="ID corresponding to the character whose summary you are generating"
    )
    summary: str = Field(
        description="Summary of the target character"
    )
    
    class Config:
        """Configure schema generation for OpenAI compatibility."""
        extra = "forbid"  # Equivalent to additionalProperties: false

class CharacterSummaries(BaseModel):
    """Schema for a collection of character summaries (array-based approach)."""
    characters: List[CharacterSummary] = Field(
        description="List of character summaries"
    )
    
    class Config:
        """Configure schema generation for OpenAI compatibility."""
        extra = "forbid"  # Equivalent to additionalProperties: false

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate character summaries for NEXUS database",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Character selection
    parser.add_argument("--character", required=True,
                        help="Character ID(s) to process. Can be: a single ID, comma-separated list (e.g., '1,5,9'), "
                             "a range using hyphen (e.g., '1-5'), or 'all' for all characters")
    
    # LLM options
    parser.add_argument("--model", default="o3",
                        help="Model to use (default: o3)")
    parser.add_argument("--temperature", type=float, default=0.2,
                        help="Temperature for standard models (default: 0.2)")
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
    
    # Test mode
    parser.add_argument("--test", action="store_true",
                        help="Test mode: Build API payload but don't make the API call")
    
    # Force overwrite without prompting
    parser.add_argument("--force", action="store_true",
                        help="Force overwrite existing summaries without confirmation prompt")
    
    # Update mode
    parser.add_argument("--update", action="store_true",
                        help="Update mode: Improve existing summaries by adding details and correcting inaccuracies")

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

def get_characters(engine: sa.engine.Engine, character_id_param: Optional[str] = None, update_mode: bool = False) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Get character information from the database.
    
    Args:
        engine: Database connection engine
        character_id_param: Optional character ID(s) to filter by.
                           Can be a single ID, comma-separated list, range with hyphen, or 'all'
        update_mode: If True, only select characters WITH existing summaries (for update mode)
        
    Returns:
        Tuple of (target_characters, all_characters)
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
    
    # Get target characters (specific or those with/without summaries based on mode)
    target_query = """
    SELECT c.id, c.name, 
           COALESCE(ARRAY_AGG(DISTINCT ca.alias ORDER BY ca.alias) FILTER (WHERE ca.alias IS NOT NULL), ARRAY[]::text[]) AS aliases,
           c.summary
    FROM characters c
    LEFT JOIN character_aliases ca ON c.id = ca.character_id
    """
    
    # Process character_id_param to handle various formats
    if character_id_param:
        if character_id_param.lower() == "all":
            if update_mode:
                # In update mode, get all characters WITH summaries
                target_query += " WHERE c.summary IS NOT NULL AND c.summary != ''"
            else:
                # In normal mode, get all characters WITHOUT summaries
                target_query += " WHERE c.summary IS NULL OR c.summary = ''"
        elif "," in character_id_param:
            # Comma-separated list of IDs
            id_list = [id.strip() for id in character_id_param.split(",")]
            base_condition = f"c.id IN ({','.join(id_list)})"
            
            if update_mode:
                # In update mode, only select those with summaries
                target_query += f" WHERE {base_condition} AND c.summary IS NOT NULL AND c.summary != ''"
            else:
                target_query += f" WHERE {base_condition}"
        elif "-" in character_id_param:
            # Range of IDs (like 1-5)
            start, end = map(str.strip, character_id_param.split("-"))
            base_condition = f"c.id >= {start} AND c.id <= {end}"
            
            if update_mode:
                # In update mode, only select those with summaries
                target_query += f" WHERE {base_condition} AND c.summary IS NOT NULL AND c.summary != ''"
            else:
                target_query += f" WHERE {base_condition}"
        else:
            # Single ID
            base_condition = f"c.id = {character_id_param.strip()}"
            
            if update_mode:
                # In update mode, only select if it has a summary
                target_query += f" WHERE {base_condition} AND c.summary IS NOT NULL AND c.summary != ''"
            else:
                target_query += f" WHERE {base_condition}"
    
    target_query += " GROUP BY c.id, c.name, c.summary ORDER BY c.id"
    
    # Execute queries
    with engine.connect() as conn:
        # Get all characters
        all_result = conn.execute(text(all_query))
        all_characters = [dict(row._mapping) for row in all_result]
        
        # Get target characters
        target_result = conn.execute(text(target_query))
        target_characters = [dict(row._mapping) for row in target_result]
    
    logger.info(f"Retrieved {len(all_characters)} total characters in roster")
    
    mode_desc = "update" if update_mode else "generation"
    if update_mode and len(target_characters) == 0:
        logger.warning(f"No characters with existing summaries found for {mode_desc}")
    else:
        logger.info(f"Found {len(target_characters)} characters matching criteria for {mode_desc}")
    
    return target_characters, all_characters

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
        logger.info(f"S{span['season']:02d}E{span['episode']:02d}: chunks {span['start_chunk']}-{span['end_chunk']}")
    
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

def update_character_summary(engine: sa.engine.Engine, character_id: int, summary: str) -> bool:
    """
    Update a character's summary in the database.
    
    Args:
        engine: Database connection engine
        character_id: Character ID to update
        summary: New summary text
        
    Returns:
        True if successful, False otherwise
    """
    query = """
    UPDATE characters
    SET summary = :summary, updated_at = NOW()
    WHERE id = :id
    """
    
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(query),
                {"id": character_id, "summary": summary}
            )
            conn.commit()
            
        logger.info(f"Updated summary for character ID {character_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to update summary for character {character_id}: {e}")
        return False

def prepare_character_roster(all_characters: List[Dict[str, Any]], 
                             target_characters: List[Dict[str, Any]], 
                             update_mode: bool = False) -> Tuple[str, str]:
    """
    Format the character roster and target characters sections.
    
    Args:
        all_characters: List of all character dictionaries for the roster
        target_characters: List of character dictionaries targeted for summary generation
        update_mode: If True, include existing summaries for update mode
        
    Returns:
        Tuple of (character_roster, target_characters_section)
    """
    # Build full character roster
    roster = "## Character Roster\n\n"
    for char in all_characters:
        if char.get('aliases') and char['aliases']:
            aliases = ', '.join(char['aliases'])
        else:
            aliases = "N/A"
        roster += f"ID: {char['id']}, Name: {char['name']}, Aliases: {aliases}\n"
    
    # Create the target character identifiers as a separate section
    if update_mode:
        target_section = "## Target Characters for Update\n\n"
        
        # For update mode, include the existing summaries
        for char in target_characters:
            target_section += f"### Character ID: {char['id']} ({char['name']})\n\n"
            target_section += "Current summary:\n```\n"
            if char['summary']:
                target_section += f"{char['summary'].strip()}\n"
            else:
                target_section += "No existing summary found.\n"
            target_section += "```\n\n"
    else:
        target_section = "## Target Characters\n\n"
        if len(target_characters) == 1:
            target_section += f"{target_characters[0]['id']}\n\n"
        else:
            target_ids = [str(char['id']) for char in target_characters]
            target_section += f"{', '.join(target_ids)}\n\n"
    
    return roster, target_section

def prepare_summaries_context(season_summaries: List[Dict[str, Any]], 
                             episode_summaries: List[Dict[str, Any]]) -> str:
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
        context += f"### Season {season_id:02d}\n\n"
        
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
                context += f"#### S{season_id:02d}E{episode['episode']:02d}\n\n"
                
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
            context += f"### Chunk ID: {chunk['id']} (S{season_num:02d}E{episode_num:02d})\n\n"
        else:
            context += f"### Chunk ID: {chunk['id']}\n\n"
            
        context += f"{chunk['raw_text']}\n\n"
    
    return context

def load_prompt_from_json(prompt_file: str, update_mode: bool = False) -> Dict[str, Any]:
    """
    Load the prompt from a JSON file, selecting the appropriate section based on mode.
    
    Args:
        prompt_file: Path to the JSON file
        update_mode: If True, use the "update_existing" section; otherwise "generate_new"
        
    Returns:
        Dictionary with prompt components for the specified mode
    """
    # Load from project root's prompts directory
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Go up one level to root
        "prompts",
        prompt_file
    )
    
    try:
        with open(prompt_path, 'r') as f:
            full_prompt_data = json.load(f)
        
        # Select the appropriate prompt section based on mode
        section_key = "update_existing" if update_mode else "generate_new"
        prompt_data = full_prompt_data.get(section_key, {})
        
        if not prompt_data:
            logger.warning(f"No {section_key} section found in prompt file. Using available data.")
            # Use whatever data is available in the file
            prompt_data = full_prompt_data
        
        logger.info(f"Loaded {section_key} prompt from {prompt_path}")
        return prompt_data
    except Exception as e:
        logger.error(f"Failed to load prompt from {prompt_path}: {e}")
        raise

def build_prompt(prompt_data: Dict[str, Any], 
                character_roster: str,
                target_characters: str,
                context: str,
                update_mode: bool = False) -> str:
    """
    Build the complete prompt for the API.
    
    Args:
        prompt_data: Dictionary with prompt components
        character_roster: Formatted character roster
        target_characters: Formatted target characters section
        context: Formatted context text
        update_mode: Whether we're in update mode
        
    Returns:
        Complete prompt text
    """
    # Combine prompt components
    system_prompt = prompt_data.get("system_prompt", "")
    
    # Handle main_instructions which might be a list in update mode
    main_instructions = prompt_data.get("main_instructions", "")
    if isinstance(main_instructions, list):
        main_instructions = "\n".join(main_instructions)
    
    # Get other prompt components
    output_format = prompt_data.get("output_format", "")
    style_guidance = prompt_data.get("style_guidance", "")
    special_instructions = prompt_data.get("special_instructions", "")
    
    # Handle examples differently depending on mode
    examples_text = ""
    
    if update_mode:
        # In update mode, example is a before/after comparison
        example = prompt_data.get("example", {})
        if example:
            examples_text = "## Example\n\n"
            examples_text += f"### Before:\n{example.get('before', '')}\n\n"
            examples_text += f"### After:\n{example.get('after', '')}\n\n"
    else:
        # In generation mode, examples is a dictionary
        examples = prompt_data.get("examples", {})
        if examples:
            examples_text = "## Examples\n\n"
            for example_type, example_text in examples.items():
                examples_text += f"### {example_type}\n{example_text}\n\n"
    
    # Build the title based on mode
    title = "Character Summary Update Task" if update_mode else "Character Summary Generation Task"
    
    # Store target characters original content for repeating in update mode
    target_summaries = ""
    if update_mode:
        # Extract just the summaries part from target_characters for repeating at the end
        lines = target_characters.split("\n")
        capturing = False
        current_char = ""
        
        for line in lines:
            if line.startswith("### Character ID:"):
                capturing = True
                current_char = line
                target_summaries += f"{line}\n\n"
            elif capturing and line.startswith("Current summary:"):
                target_summaries += "Current summary to update:\n"
            elif capturing and line.startswith("```"):
                if "```\n\n" in target_summaries:
                    # This is the end of a summary block
                    target_summaries += "```\n\n"
                else:
                    # This is the beginning of a summary block
                    target_summaries += "```\n"
            elif capturing and not line.startswith("```"):
                # Inside a summary block
                target_summaries += f"{line}\n"
    
    # Build the first part of the prompt
    first_part = f"""# {title}

System: {system_prompt}

## Instructions
{main_instructions}

"""
    
    # Add optional sections if they exist
    if output_format:
        first_part += f"## Output Format\n{output_format}\n\n"
    
    if style_guidance:
        first_part += f"## Style Guidelines\n{style_guidance}\n\n"
    
    if special_instructions:
        first_part += f"## Special Notes\n{special_instructions}\n\n"
    
    # Add examples, character roster, target characters, and context
    first_part += f"""{examples_text}
{character_roster}
{target_characters}
{context}
"""

    # Build the repeated part (identical to ensure consistency)
    repeated_part = f"""# {title} (REPEATED)

System: {system_prompt}

## Instructions
{main_instructions}

"""
    
    # Add optional sections if they exist in the repeated part too
    if output_format:
        repeated_part += f"## Output Format\n{output_format}\n\n"
    
    if style_guidance:
        repeated_part += f"## Style Guidelines\n{style_guidance}\n\n"
    
    if special_instructions:
        repeated_part += f"## Special Notes\n{special_instructions}\n\n"
    
    # Add examples to repeated part
    repeated_part += f"{examples_text}\n"
    
    # For update mode, add target summaries at the very end for emphasis
    if update_mode and target_summaries:
        repeated_part += f"## Target Summaries to Update (REMINDER)\n\n{target_summaries}\n"
    
    # Combine both parts
    prompt = first_part + repeated_part
    
    return prompt

def process_api_response(response_data: CharacterSummaries, 
                         characters: List[Dict[str, Any]],
                         engine: sa.engine.Engine,
                         dry_run: bool = False,
                         force: bool = False) -> int:
    """
    Process the API response and update the database.
    
    Args:
        response_data: Parsed API response with multiple characters
        characters: List of character dictionaries
        engine: Database connection engine
        dry_run: If True, don't update the database
        force: If True, overwrite existing summaries without asking
        
    Returns:
        Number of characters successfully updated
    """
    # Map character IDs to their dictionary entries for lookup
    char_id_map = {char['id']: char for char in characters}
    updated_count = 0
    
    # Loop through all characters in the response
    for char_summary in response_data.characters:
        char_id = char_summary.character_id
        summary = char_summary.summary
        
        # Verify the character ID exists in our list
        if char_id not in char_id_map:
            logger.warning(f"Unknown character ID in response: {char_id}")
            continue
            
        char_data = char_id_map[char_id]
        char_name = char_data['name']
        existing_summary = char_data.get('summary')
        
        # Log the summary
        logger.info(f"Summary for character {char_id} ({char_name}):")
        logger.info("---")
        logger.info(summary.strip())
        logger.info("---")
        
        # Check if character already has a summary
        if existing_summary and existing_summary.strip() and not force and not dry_run:
            # Ask for confirmation before overwriting
            print(f"\nCharacter {char_id} ({char_name}) already has a summary:")
            print("---")
            print(existing_summary.strip())
            print("---")
            print("New summary:")
            print("---")
            print(summary.strip())
            print("---")
            
            response = input(f"Overwrite existing summary for {char_name}? (y/n): ").strip().lower()
            if response != 'y':
                logger.info(f"Skipping update for character {char_id} ({char_name})")
                continue
        
        # Update the database
        if not dry_run:
            success = update_character_summary(engine, char_id, summary)
            if success:
                updated_count += 1
                logger.info(f"Successfully updated summary for character {char_id} ({char_name})")
        else:
            logger.info(f"DRY RUN: Would update character {char_id} ({char_name})")
            updated_count += 1
    
    return updated_count

def generate_summaries(
    api_provider: OpenAIProvider,
    target_characters: List[Dict[str, Any]],
    all_characters: List[Dict[str, Any]],
    engine: sa.engine.Engine,
    args: argparse.Namespace
) -> Tuple[int, int]:
    """
    Generate summaries for multiple characters using the API and update the database.
    
    Args:
        api_provider: OpenAI API provider
        target_characters: Characters to generate summaries for
        all_characters: All characters in the database for context
        engine: Database connection engine
        args: Command line arguments
        
    Returns:
        Tuple of (success_count, total_characters)
    """
    if not target_characters:
        logger.warning("No target characters to process")
        return 0, 0
    
    # Set a limit on how many characters to process at once
    max_chars_per_batch = 5
    if len(target_characters) > max_chars_per_batch:
        logger.info(f"Found {len(target_characters)} characters, but limiting to {max_chars_per_batch} for API efficiency")
        target_characters = target_characters[:max_chars_per_batch]
    
    # Load the prompt template with update mode flag
    prompt_data = load_prompt_from_json("populate_character_summaries.json", args.update)
    
    # Prepare character roster and target character section - pass update mode
    character_roster, target_characters_section = prepare_character_roster(
        all_characters, 
        target_characters,
        args.update
    )
    
    # Prepare context based on arguments
    if args.chunk:
        # Special handling for auto mode in single character case
        if args.chunk.lower() == "auto" and len(target_characters) == 1:
            # Auto mode only works for a single character
            chunks = get_narrative_chunks(engine, "auto", target_characters[0]["id"])
            context = prepare_chunks_context(chunks)
        elif args.chunk.lower() == "auto" and len(target_characters) > 1:
            # Can't use auto mode with multiple characters - fall back to summaries
            logger.warning("Auto mode can only be used with a single character. Falling back to summary mode.")
            season_summaries = get_season_summaries(engine)
            episode_summaries = get_episode_summaries(engine)
            context = prepare_summaries_context(season_summaries, episode_summaries)
        else:
            # Regular chunk mode
            chunks = get_narrative_chunks(engine, args.chunk)
            context = prepare_chunks_context(chunks)
    else:
        # Use summaries (default behavior)
        season_summaries = get_season_summaries(engine)
        episode_summaries = get_episode_summaries(engine)
        context = prepare_summaries_context(season_summaries, episode_summaries)
    
    # Build complete prompt - pass update mode
    prompt = build_prompt(
        prompt_data, 
        character_roster, 
        target_characters_section, 
        context,
        args.update
    )
    
    # For test mode, print the prompt and exit
    if args.test:
        logger.info("TEST MODE: Printing prompt that would be sent to API")
        print("\n" + "="*80 + "\n")
        print(prompt)
        print("\n" + "="*80 + "\n")
        return 0, len(target_characters)
    
    # Token count and performance metrics
    prompt_tokens = api_provider.count_tokens(prompt)
    logger.info(f"Prompt size: {prompt_tokens} tokens")
    
    # Make API call for structured output
    start_time = time.time()
    
    try:
        # Format the messages for the API call
        messages = []
        if api_provider.system_prompt:
            messages.append({"role": "system", "content": api_provider.system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        logger.info(f"Using OpenAI with model {args.model}")
        
        # Using responses.parse() with our Pydantic model as recommended by gpt-o3
        if args.model.startswith("o"):
            # For reasoning models, include reasoning parameter
            response = api_provider.client.responses.parse(
                model=args.model,
                input=messages,
                reasoning={"effort": args.effort} if args.effort else None,
                text_format=CharacterSummaries  # Pass the Pydantic model directly
            )
        else:
            # For standard models, include temperature
            response = api_provider.client.responses.parse(
                model=args.model,
                input=messages,
                temperature=args.temperature,
                text_format=CharacterSummaries  # Pass the Pydantic model directly
            )
        
        # Get the parsed Pydantic object directly
        result = response.output_parsed
        
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
        logger.info(f"Generated summaries for {len(result.characters)} characters")
        
        # Process results
        updated_count = process_api_response(
            result, 
            target_characters, 
            engine, 
            args.dry_run,
            args.force
        )
        
        return updated_count, len(target_characters)
    
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return 0, len(target_characters)

def main():
    """Main function."""
    # Parse arguments
    args = parse_arguments()
    
    # Set up abort handler
    setup_abort_handler("Abort requested! Will finish current operation and stop.")
    
    try:
        # Connect to database
        engine = connect_to_database(args.db_url)
        
        # Check for conflicting options
        if args.update and args.character.lower() == "all" and not args.force:
            logger.info("Update mode with 'all' could affect many characters.")
            response = input("Do you want to update ALL characters with existing summaries? (y/n): ").strip().lower()
            if response != 'y':
                logger.info("Operation canceled by user")
                return 0
        
        # Retrieve characters - use update_mode flag if --update was specified
        target_characters, all_characters = get_characters(engine, args.character, args.update)
        
        if not target_characters:
            if args.update:
                logger.warning("No characters with existing summaries found to update")
            else:
                logger.warning("No target characters found to process")
            return 1
        
        # This version supports multiple characters
        operation = "update" if args.update else "generate summaries for"
        logger.info(f"Found {len(target_characters)} character(s) to {operation}")
        
        if len(target_characters) == 1:
            logger.info(f"Processing character ID: {target_characters[0]['id']}, Name: {target_characters[0]['name']}")
        else:
            character_ids = ", ".join(str(char["id"]) for char in target_characters[:5])
            if len(target_characters) > 5:
                character_ids += f", ... (and {len(target_characters) - 5} more)"
            logger.info(f"Processing multiple characters IDs: {character_ids}")
        
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
        
        # Generate or update summaries for multiple characters at once
        success_count, total_count = generate_summaries(
            api_provider, 
            target_characters,
            all_characters,
            engine, 
            args
        )
        
        # Log results
        action = "updated" if args.update else "generated"
        logger.info(f"Successfully {action} {success_count} of {total_count} character summaries")
        
        return 0 if success_count > 0 else 1
    
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())