#!/usr/bin/env python3
"""
Freestyle API Query Script

A lightweight utility-knife script for sending flexible queries to OpenAI API with 
database context from the NEXUS system.

Usage:
    python freestyle_api_query.py --prompt "Your prompt text here" [OPTIONS]
    
Features:
    - Directly accepts a prompt via command line argument
    - No database writes - just prints the response to the console
    - Context fetching from season/episode summaries or narrative chunks
    - Automatic episode span detection for characters using --character and --chunk auto
    - Episode slug parsing (s03e07) for easy episode selection
    - Save API query packages to JSON for verification and later use

Options:
    --prompt TEXT        Your prompt text to send to the API (required unless using --input)
    
    --model MODEL        OpenAI model to use (default: gpt-4.1)
    --temperature FLOAT  Temperature setting (0.0-1.0, default: 0.6)
    --effort LEVEL       Reasoning effort for o-prefixed models (default: medium)
                         Options: 'low', 'medium', 'high'
                         Only applicable for reasoning models like o3
    
    --context OPTIONS:
    
    --character ID       Character ID to fetch context for. Use with --chunk auto
                         to automatically include episodes where character appears

    --place ID           Place ID to include complete place data as context
                         Shows all fields/columns for the specified place
    
    --chunk ID/MODE      Narrative chunks to include as context. Can be:
                         - A single chunk ID (e.g., "123")
                         - A comma-separated list (e.g., "100,101,102")
                         - A range using hyphen (e.g., "100-110")
                         - 'all' for all chunks (use with caution)
                         - 'auto' to automatically include episodes where the
                           specified character appears (requires --character)
    
    --episode SLUG       Episode to include as context using a slug format (e.g., "s01e05")
                         Can also provide a range with two slugs (e.g., "s01e05 s01e07")
    
    --db-url URL         Database connection URL (optional, defaults to environment)
    
    Output Options (mutually exclusive):
    --save-response FILE Save API response to a file in addition to printing
    --output [FILE]      Save API query package to a JSON file instead of making the API call
                         Defaults to custom_query.json if no filename provided
    --input FILE         Load API query package from a JSON file and send it to the API

Examples:
    # Basic query using summaries as context
    python freestyle_api_query.py --prompt "What are the key conflicts in the story?"
    
    # Query with specific episode as context
    python freestyle_api_query.py --prompt "Analyze Alex's emotional state" --episode s01e05
    
    # Query using auto-detected chunks for a character
    python freestyle_api_query.py --prompt "Describe Bishop's role in the story" --character 13 --chunk auto
    
    # Use a specific model with custom temperature
    python freestyle_api_query.py --prompt "Generate dialogue for Emilia" --model gpt-4o --temperature 0.8
    
    # Query with place data as context
    python freestyle_api_query.py --prompt "Describe the atmosphere and details of" --place 1
    
    # Save API query package for verification before sending
    python freestyle_api_query.py --prompt "Complex analysis of Character X" --chunk 100-120 --output query.json
    
    # Load and send a previously saved query package
    python freestyle_api_query.py --input query.json
"""

import os
import sys
import re
import json
import argparse
import logging
import time
from typing import Dict, List, Any, Optional, Tuple, Union
import sqlalchemy as sa
from sqlalchemy import create_engine, text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("freestyle_query.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.freestyle")

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

def get_db_connection_string():
    """Get the database connection string from environment variables or defaults."""
    DB_USER = os.environ.get("DB_USER", "pythagor")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME", "NEXUS")
    
    # Build connection string (with password if provided)
    if DB_PASSWORD:
        return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        return f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

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

def get_character_episode_spans(engine: sa.engine.Engine, character_id: int) -> List[Dict[str, Any]]:
    """
    Get episode spans for a character based on their appearances.
    
    This function:
    1. Gets the chunks where a character appears from character_present_view
    2. Identifies the episodes containing those chunks
    3. Returns complete episode spans for all episodes where the character appears
    
    Args:
        engine: Database connection engine
        character_id: Character ID to find episodes for
        
    Returns:
        List of dictionaries with season, episode, start_chunk, end_chunk
    """
    # First, get the chunks where the character appears
    chunks_query = """
    SELECT chunks_in
    FROM character_present_view
    WHERE character_id = :character_id
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

def get_episode_chunks(engine: sa.engine.Engine, season: int, episode: int) -> List[Dict[str, Any]]:
    """
    Get all chunks for a specific episode.
    
    Args:
        engine: Database connection engine
        season: Season number
        episode: Episode number
        
    Returns:
        List of narrative chunk dictionaries
    """
    query = """
    SELECT nc.id, nc.raw_text, cm.season, cm.episode
    FROM narrative_chunks nc
    JOIN chunk_metadata cm ON nc.id = cm.chunk_id
    WHERE cm.season = :season AND cm.episode = :episode
    ORDER BY nc.id
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query), {"season": season, "episode": episode})
        chunks = [dict(row._mapping) for row in result]
    
    logger.info(f"Retrieved {len(chunks)} chunks for S{season:02d}E{episode:02d}")
    return chunks

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

def get_place_data(engine: sa.engine.Engine, place_id: int) -> Optional[Dict[str, Any]]:
    """
    Get all data for a specific place by ID.
    
    Args:
        engine: Database connection engine
        place_id: Place ID to fetch
        
    Returns:
        Dictionary with all place data, or None if not found
    """
    query = """
    SELECT p.*, z.name as zone_name 
    FROM places p
    JOIN zones z ON p.zone = z.id
    WHERE p.id = :place_id
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query), {"place_id": place_id})
        place = result.fetchone()
        
    if not place:
        logger.warning(f"No place found with ID {place_id}")
        return None
        
    # Convert to dict if found
    place_dict = dict(place._mapping)
    
    # Pretty format any JSON fields
    for key, value in place_dict.items():
        if isinstance(value, (dict, list)):
            place_dict[key] = json.dumps(value, indent=2)
    
    logger.info(f"Retrieved data for place ID {place_id}: {place_dict['name']}")
    return place_dict

def prepare_place_context(place: Dict[str, Any]) -> str:
    """
    Prepare context from place data.
    
    Args:
        place: Place data dictionary
        
    Returns:
        Formatted context text
    """
    context = f"## Place Data (ID: {place['id']})\n\n"
    context += f"### Name: {place['name']}\n"
    context += f"### Zone: {place['zone_name']}\n\n"
    
    # Format each field
    context += "### Details:\n\n"
    for key, value in place.items():
        if key in ('id', 'name', 'zone', 'zone_name'):
            continue  # Skip already displayed fields
            
        if value is not None and value != '':
            # Format the output based on the field type
            if isinstance(value, str) and len(value) > 100 and '\\n' in value:
                # Large text field with newlines
                context += f"#### {key}:\n```\n{value}\n```\n\n"
            else:
                context += f"#### {key}:\n{value}\n\n"
    
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
        
        if season_num is not None and episode_num is not None:
            context += f"### Chunk ID: {chunk['id']} (S{season_num:02d}E{episode_num:02d})\n\n"
        else:
            context += f"### Chunk ID: {chunk['id']}\n\n"
            
        context += f"{chunk['raw_text']}\n\n"
    
    return context

def save_api_package(system_prompt: str, user_prompt: str, content: str, filename: str) -> None:
    """
    Save the API query package to a JSON file.
    
    Args:
        system_prompt: The system prompt text
        user_prompt: The user prompt text
        content: The context content
        filename: The filename to save to
    """
    package = {
        "system_prompt": {
            "role": "system",
            "content": system_prompt
        },
        "user_prompt": {
            "role": "user",
            "content": user_prompt
        },
        "content": content
    }
    
    try:
        with open(filename, 'w') as f:
            json.dump(package, f, indent=2)
        logger.info(f"API query package saved to {filename}")
        print(f"API query package saved to {filename}")
    except Exception as e:
        logger.error(f"Failed to save API query package: {e}")
        print(f"Failed to save API query package: {e}")
        
def load_api_package(filename: str) -> Tuple[str, str, str, str, float, str]:
    """
    Load the API query package from a JSON file.
    
    Args:
        filename: The filename to load from
        
    Returns:
        Tuple of (full_prompt, model, temperature, effort)
    """
    try:
        with open(filename, 'r') as f:
            package = json.load(f)
            
        # Extract components
        system_prompt = package.get("system_prompt", {}).get("content", "")
        user_prompt = package.get("user_prompt", {}).get("content", "")
        content = package.get("content", "")
        
        # Rebuild the full prompt
        full_prompt = f"{user_prompt}\n\n{content}"
        
        # Get model parameters (if included)
        model = package.get("model", "gpt-4.1")
        temperature = package.get("temperature", 0.6)
        effort = package.get("effort", "medium")
        
        logger.info(f"API query package loaded from {filename}")
        return full_prompt, model, temperature, effort
        
    except Exception as e:
        logger.error(f"Failed to load API query package: {e}")
        print(f"Failed to load API query package: {e}")
        sys.exit(1)

def call_openai_api(prompt: str, model: str, temperature: float, effort: str) -> str:
    """
    Call the OpenAI API with the given prompt.
    
    Args:
        prompt: The prompt text to send
        model: The model to use
        temperature: Temperature setting (0-1)
        effort: Reasoning effort for reasoning models ('low', 'medium', 'high')
        
    Returns:
        API response content
    """
    # Import OpenAI here to avoid dependency issues if not installed
    try:
        import openai
    except ImportError:
        logger.error("OpenAI package not installed. Install with 'pip install openai'")
        sys.exit(1)
    
    # Get API key from environment
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    # Initialize client
    client = openai.OpenAI(api_key=api_key)
    
    # Prepare messages
    messages = [{"role": "user", "content": prompt}]
    
    # Check if we're using a reasoning model (starts with 'o')
    is_reasoning_model = model.startswith('o')
    
    logger.info(f"Calling OpenAI API with model {model}")
    logger.info(f"Input length: {len(prompt.split())} words")
    
    start_time = time.time()
    
    try:
        # Different call for reasoning vs. standard models
        if is_reasoning_model:
            logger.info(f"Using reasoning model with effort: {effort}")
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                reasoning_effort=effort,
            )
        else:
            logger.info(f"Using standard model with temperature: {temperature}")
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            )
        
        # Extract content
        content = response.choices[0].message.content
        
        # Log performance
        elapsed_time = time.time() - start_time
        logger.info(f"API call completed in {elapsed_time:.2f} seconds")
        logger.info(f"Generated {len(content.split())} words")
        
        return content
        
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return f"API call failed: {e}"

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Freestyle API Query with NEXUS database context",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Prompt - required unless using --input
    parser.add_argument("--prompt", help="Prompt text to send to the API (required unless using --input)")
    
    # LLM options
    parser.add_argument("--model", default="gpt-4.1", help="Model to use (default: gpt-4.1)")
    parser.add_argument("--temperature", type=float, default=0.6,
                       help="Temperature for standard models (default: 0.6)")
    parser.add_argument("--effort", choices=["low", "medium", "high"], default="medium",
                       help="Reasoning effort for o-prefixed models (default: medium)")
    
    # Context options (mutually exclusive group)
    context_group = parser.add_mutually_exclusive_group()
    
    # Character option - works with chunk auto
    parser.add_argument("--character", type=int, 
                        help="Character ID to use when fetching context with --chunk auto")
    
    # Place option
    parser.add_argument("--place", type=int,
                        help="Place ID to include place data as context")
    
    # Chunk options
    context_group.add_argument("--chunk", 
                              help="Process specific chunks (chunk IDs comma-separated, or range using hyphen, "
                                   "or 'all', or 'auto' to get chunks where character appears)")
    
    # Episode options
    context_group.add_argument("--episode", nargs='+',
                              help="Episode(s) to get context from (e.g., s03e01 or s03e01 s03e13 for range)")
    
    # Output options
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--save-response", dest="output", metavar="FILE", 
                        help="Save API response to a file in addition to printing")
    output_group.add_argument("--output", dest="output_package", metavar="FILE", nargs="?", const="custom_query.json",
                        help="Save API query package to a JSON file instead of making the API call. "
                             "Defaults to custom_query.json if no filename provided")
    output_group.add_argument("--input", dest="input_package", metavar="FILE",
                        help="Load API query package from a JSON file and send it to the API")
    
    # Database options
    parser.add_argument("--db-url", help="Database connection URL (optional)")
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.input_package and not args.prompt:
        parser.error("--prompt is required unless --input is specified")
    
    # Check if we're loading from an existing package
    if args.input_package:
        # Load the API query package
        full_prompt, model, temperature, effort = load_api_package(args.input_package)
        
        # Call the OpenAI API with the loaded package
        response = call_openai_api(full_prompt, model, temperature, effort)
        
        # Output the response
        print("\n" + "=" * 80)
        print("API RESPONSE (from loaded package):")
        print("=" * 80)
        print(response)
        print("=" * 80 + "\n")
        
        # Save response to file if requested
        if args.output:
            with open(args.output, 'w') as f:
                f.write(response)
            print(f"Response saved to {args.output}")
        
        return 0
    
    # Validate when using auto chunks
    if args.chunk == "auto" and not args.character:
        parser.error("--chunk auto requires --character to be specified")
        
    # Connect to database
    engine = connect_to_database(args.db_url)
    
    # Fetch appropriate context
    
    # Base context and place data context (if requested)
    base_context = ""
    place_context = ""
    
    # Get place data if specified
    if args.place:
        place_data = get_place_data(engine, args.place)
        if place_data:
            place_context = prepare_place_context(place_data)
        else:
            logger.error(f"Place with ID {args.place} not found")
            sys.exit(1)
    
    # Get base context from episodes, chunks, or summaries
    if args.episode:
        # Episode context
        if len(args.episode) == 1:
            # Single episode
            try:
                season, episode = EpisodeSlugParser.parse(args.episode[0])
                chunks = get_episode_chunks(engine, season, episode)
                base_context = prepare_chunks_context(chunks)
            except ValueError as e:
                logger.error(f"Error parsing episode slug: {e}")
                sys.exit(1)
        elif len(args.episode) == 2:
            # Episode range
            try:
                start_slug = args.episode[0]
                end_slug = args.episode[1]
                
                if not EpisodeSlugParser.validate_range(start_slug, end_slug):
                    logger.error(f"Invalid episode range: {start_slug} to {end_slug}")
                    sys.exit(1)
                    
                start_season, start_episode = EpisodeSlugParser.parse(start_slug)
                end_season, end_episode = EpisodeSlugParser.parse(end_slug)
                
                # Get all episodes in the range
                all_chunks = []
                
                # For each season in the range
                for season in range(start_season, end_season + 1):
                    # Determine episode range for this season
                    if season == start_season:
                        first_ep = start_episode
                    else:
                        first_ep = 1
                        
                    if season == end_season:
                        last_ep = end_episode
                    else:
                        # Get last episode in this season
                        query = """
                        SELECT MAX(episode) FROM chunk_metadata WHERE season = :season
                        """
                        with engine.connect() as conn:
                            result = conn.execute(text(query), {"season": season})
                            last_ep = result.scalar() or 1
                    
                    # Get chunks for each episode
                    for episode in range(first_ep, last_ep + 1):
                        chunks = get_episode_chunks(engine, season, episode)
                        all_chunks.extend(chunks)
                
                base_context = prepare_chunks_context(all_chunks)
            except ValueError as e:
                logger.error(f"Error parsing episode slugs: {e}")
                sys.exit(1)
        else:
            logger.error("Invalid number of episode arguments. Use one slug for a single episode, or two for a range.")
            sys.exit(1)
    elif args.chunk:
        # Chunk context
        chunks = get_narrative_chunks(engine, args.chunk, args.character)
        base_context = prepare_chunks_context(chunks)
    else:
        # Default - use summaries for context only if no other context provided
        if not place_context:
            season_summaries = get_season_summaries(engine)
            episode_summaries = get_episode_summaries(engine)
            base_context = prepare_summaries_context(season_summaries, episode_summaries)
    
    # Combine contexts - place data first (if any), then base context
    context = ""
    if place_context:
        context += place_context + "\n\n"
    if base_context:
        context += base_context
    
    # Define the system prompt
    system_prompt = """You are a helpful assistant analyzing narrative data from the NEXUS database.
Your task is to provide thorough, thoughtful analysis based on the prompt and context provided.
Focus on providing accurate information derived from the context."""
    
    # Define the user prompt without context
    user_prompt = f"""# NEXUS Freestyle Query

## Your Task:
{args.prompt}"""
    
    # Build the full prompt (user prompt + context)
    full_prompt = f"""{user_prompt}

## CONTEXT:
{context}
"""
    
    # If we're saving the package instead of making the API call
    if args.output_package:
        # Save the API query package
        # Include model parameters in the package
        package = {
            "system_prompt": {
                "role": "system",
                "content": system_prompt
            },
            "user_prompt": {
                "role": "user",
                "content": user_prompt
            },
            "content": context,
            "model": args.model,
            "temperature": args.temperature,
            "effort": args.effort
        }
        
        try:
            with open(args.output_package, 'w') as f:
                json.dump(package, f, indent=2)
            logger.info(f"API query package saved to {args.output_package}")
            print(f"API query package saved to {args.output_package}")
        except Exception as e:
            logger.error(f"Failed to save API query package: {e}")
            print(f"Failed to save API query package: {e}")
        
        return 0
    
    # Otherwise, make the API call
    response = call_openai_api(full_prompt, args.model, args.temperature, args.effort)
    
    # Output the response
    print("\n" + "=" * 80)
    print("API RESPONSE:")
    print("=" * 80)
    print(response)
    print("=" * 80 + "\n")
    
    # Save response to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            f.write(response)
        print(f"Response saved to {args.output}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())