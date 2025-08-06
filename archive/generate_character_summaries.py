#!/usr/bin/env python3
"""
Character Summary Generator

This script generates concise character summaries for the NEXUS database
by analyzing season and episode summaries. It uses OpenAI's API to generate
summaries of appropriate length based on character importance.
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
    """Schema for character summary returned by OpenAI."""
    character_id: int = Field(
        description="ID corresponding to the character whose summary you are generating"
    )
    summary: str = Field(
        description="Summary of the target character"
    )
    
    class Config:
        """Configure schema generation for OpenAI compatibility."""
        extra = "forbid"  # Equivalent to additionalProperties: false
        
    @classmethod
    def get_json_schema(cls):
        """
        Generate a JSON schema compatible with OpenAI's structured output format.
        Required when working with reasoning models (o-prefix).
        """
        return {
            "type": "object",
            "properties": {
                "character_id": {
                    "type": "integer",
                    "description": "ID corresponding to the character whose summary you are generating"
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of the target character"
                }
            },
            "required": ["character_id", "summary"],
            "additionalProperties": False
        }

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate character summaries for NEXUS database",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Character selection
    parser.add_argument("--character", required=True,
                        help="Character ID to process (a specific ID number or 'all' for all characters)")
    
    # LLM options
    parser.add_argument("--model", default="gpt-4.1",
                        help="Model to use (default: gpt-4.1)")
    parser.add_argument("--temperature", type=float, default=0.2,
                        help="Temperature for standard models (default: 0.2)")
    parser.add_argument("--effort", choices=["low", "medium", "high"], default="medium",
                        help="Reasoning effort for o-prefixed models (default: medium)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't save results to database")
    parser.add_argument("--db-url", 
                        help="Database connection URL (optional, defaults to environment variables)")
    
    # Context options
    context_group = parser.add_mutually_exclusive_group()
    context_group.add_argument("--chunk", 
                              help="Process specific chunks (chunk IDs comma-separated, or range using hyphen, or 'all')")
    
    # Test mode
    parser.add_argument("--test", action="store_true",
                        help="Test mode: Build API payload but don't make the API call")

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

def get_characters(engine: sa.engine.Engine, character_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Get character information from the database.
    
    Args:
        engine: Database connection engine
        character_id: Optional character ID to filter by (None for all)
        
    Returns:
        Tuple of (target_characters, all_characters)
    """
    # Get all characters for the roster
    all_query = """
    SELECT id, name, aliases, summary
    FROM characters
    ORDER BY id
    """
    
    # Get target characters (specific or those without summaries)
    target_query = """
    SELECT id, name, aliases, summary
    FROM characters
    """
    
    if character_id and character_id != "all":
        # Filter by specific character ID
        target_query += f" WHERE id = {character_id}"
    elif character_id == "all":
        # Get all characters without summaries
        target_query += " WHERE summary IS NULL OR summary = ''"
    
    target_query += " ORDER BY id"
    
    # Execute queries
    with engine.connect() as conn:
        # Get all characters
        all_result = conn.execute(text(all_query))
        all_characters = [dict(row._mapping) for row in all_result]
        
        # Get target characters
        target_result = conn.execute(text(target_query))
        target_characters = [dict(row._mapping) for row in target_result]
    
    logger.info(f"Retrieved {len(all_characters)} total characters")
    logger.info(f"Targeting {len(target_characters)} characters for summary generation")
    
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

def get_narrative_chunks(engine: sa.engine.Engine, chunk_ids: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get narrative chunks from the database.
    
    Args:
        engine: Database connection engine
        chunk_ids: Optional chunk IDs to filter by (comma-separated, range, or 'all')
        
    Returns:
        List of narrative chunk dictionaries
    """
    query = """
    SELECT nc.id, nc.raw_text, cm.season, cm.episode
    FROM narrative_chunks nc
    LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
    """
    
    # Process chunk_ids argument
    if chunk_ids:
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

def prepare_character_roster(all_characters: List[Dict[str, Any]], target_characters: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Format the character roster and target characters sections.
    
    Args:
        all_characters: List of all character dictionaries for the roster
        target_characters: List of character dictionaries targeted for summary generation
        
    Returns:
        Tuple of (character_roster, target_characters_section)
    """
    # Build full character roster
    roster = "## Character Roster\n\n"
    for char in all_characters:
        aliases = char['aliases'] if char['aliases'] else "N/A"
        roster += f"ID: {char['id']}, Name: {char['name']}, Aliases: {aliases}\n"
    
    # Create the target character identifiers as a separate section
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

def load_prompt_from_json(prompt_file: str) -> Dict[str, Any]:
    """
    Load the prompt from a JSON file.
    
    Args:
        prompt_file: Path to the JSON file
        
    Returns:
        Dictionary with prompt components
    """
    # Load from project root's prompts directory
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Go up one level to root
        "prompts",
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

def build_prompt(prompt_data: Dict[str, Any], 
                character_roster: str,
                target_characters: str,
                context: str) -> str:
    """
    Build the complete prompt for the API.
    
    Args:
        prompt_data: Dictionary with prompt components
        character_roster: Formatted character roster
        target_characters: Formatted target characters section
        context: Formatted context text
        
    Returns:
        Complete prompt text
    """
    # Combine prompt components
    system_prompt = prompt_data.get("system_prompt", "")
    main_instructions = prompt_data.get("main_instructions", "")
    output_format = prompt_data.get("output_format", "")
    style_guidance = prompt_data.get("style_guidance", "")
    special_instructions = prompt_data.get("special_instructions", "")
    examples = prompt_data.get("examples", {})
    
    # Format examples if available
    examples_text = ""
    if examples:
        examples_text = "## Examples\n\n"
        for example_type, example_text in examples.items():
            examples_text += f"### {example_type}\n{example_text}\n\n"
    
    # Build the first part of the prompt
    first_part = f"""# Character Summary Generation Task

System: {system_prompt}

## Instructions
{main_instructions}

## Output Format
{output_format}

## Style Guidelines
{style_guidance}

## Special Notes
{special_instructions}

{examples_text}
{character_roster}
{target_characters}
{context}
"""

    # Build the repeated part (identical to ensure consistency)
    repeated_part = f"""# Character Summary Generation Task (REPEATED)

System: {system_prompt}

## Instructions
{main_instructions}

## Output Format
{output_format}

## Style Guidelines
{style_guidance}

## Special Notes
{special_instructions}

{examples_text}
"""
    
    # Combine both parts
    prompt = first_part + repeated_part
    
    return prompt

def process_api_response(response_data: CharacterSummary, 
                         characters: List[Dict[str, Any]],
                         engine: sa.engine.Engine,
                         dry_run: bool = False) -> int:
    """
    Process the API response and update the database.
    
    Args:
        response_data: Parsed API response
        characters: List of character dictionaries
        engine: Database connection engine
        dry_run: If True, don't update the database
        
    Returns:
        Number of characters successfully updated (0 or 1)
    """
    # Get character ID and summary from response
    char_id = response_data.character_id
    summary = response_data.summary
    
    # Verify the character ID exists in our list
    char_exists = any(char['id'] == char_id for char in characters)
    if not char_exists:
        logger.warning(f"Unknown character ID in response: {char_id}")
        return 0
    
    # Log the summary
    logger.info(f"Summary for character {char_id}:")
    logger.info("---")
    logger.info(summary.strip())
    logger.info("---")
    
    # Update the database
    if not dry_run:
        success = update_character_summary(engine, char_id, summary)
        return 1 if success else 0
    else:
        logger.info("DRY RUN: Would update database")
        return 1

def generate_summaries(
    api_provider: OpenAIProvider,
    target_characters: List[Dict[str, Any]],
    all_characters: List[Dict[str, Any]],
    engine: sa.engine.Engine,
    args: argparse.Namespace
) -> Tuple[int, int]:
    """
    Generate summary for a single character using the API and update the database.
    
    Args:
        api_provider: OpenAI API provider
        target_characters: Characters to generate summaries for (we'll only use the first one)
        all_characters: All characters in the database for context
        engine: Database connection engine
        args: Command line arguments
        
    Returns:
        Tuple of (success_count, total_characters)
    """
    # We'll only process the first character in the target list
    if not target_characters:
        logger.warning("No target characters to process")
        return 0, 0
    
    # Get the target character
    target_character = target_characters[0]
    
    # Load the prompt template
    prompt_data = load_prompt_from_json("populate_character_summaries.json")
    
    # Prepare character roster and target character section
    character_roster, target_characters_section = prepare_character_roster(all_characters, [target_character])
    
    # Prepare context based on arguments
    if args.chunk:
        # Use narrative chunks
        chunks = get_narrative_chunks(engine, args.chunk)
        context = prepare_chunks_context(chunks)
    else:
        # Use summaries (default behavior)
        season_summaries = get_season_summaries(engine)
        episode_summaries = get_episode_summaries(engine)
        context = prepare_summaries_context(season_summaries, episode_summaries)
    
    # Build complete prompt
    prompt = build_prompt(prompt_data, character_roster, target_characters_section, context)
    
    # For test mode, print the prompt and exit
    if args.test:
        logger.info("TEST MODE: Printing prompt that would be sent to API")
        print("\n" + "="*80 + "\n")
        print(prompt)
        print("\n" + "="*80 + "\n")
        return 0, 1
    
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
        
        # Make the API call using different methods based on model type
        if args.model.startswith("o"):
            # For reasoning models (o-prefixed), use the responses API directly with JSON schema
            # Using the schema directly inline, exactly like the OpenAI documentation example
            logger.info(f"Using OpenAI Responses API with model {args.model}")
            
            response = api_provider.client.responses.create(
                model=args.model,
                input=messages,
                reasoning={"effort": args.effort} if args.effort else None,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "character_summary",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "character_id": {
                                    "type": "integer",
                                    "description": "ID corresponding to the character whose summary you are generating"
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "summary of the target character"
                                }
                            },
                            "required": [
                                "character_id",
                                "summary"
                            ],
                            "additionalProperties": False
                        },
                        "strict": True
                    }
                }
            )
            
            # Parse the response
            parsed_response = json.loads(response.output_text)
            result = CharacterSummary(
                character_id=parsed_response["character_id"],
                summary=parsed_response["summary"]
            )
            
            # Create a compatible response object
            llm_response = LLMResponse(
                content=response.output_text,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                model=args.model,
                raw_response=response
            )
            
        else:
            # For standard models, use the get_structured_completion method
            result, llm_response = api_provider.get_structured_completion(prompt, CharacterSummary)
        
        # Log performance metrics
        elapsed_time = time.time() - start_time
        logger.info(f"API call completed in {elapsed_time:.2f} seconds")
        logger.info(f"Input tokens: {llm_response.input_tokens}, Output tokens: {llm_response.output_tokens}")
        
        # Process results
        updated_count = process_api_response(result, target_characters, engine, args.dry_run)
        
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
        
        # Retrieve characters
        target_characters, all_characters = get_characters(engine, args.character)
        
        if not target_characters:
            logger.warning("No target characters found to process")
            return 1
        
        # This script now processes only one character at a time for simplicity
        if len(target_characters) > 1:
            logger.info(f"Found {len(target_characters)} characters, but will only process the first one")
            target_characters = [target_characters[0]]
        
        logger.info(f"Processing character ID: {target_characters[0]['id']}, Name: {target_characters[0]['name']}")
        
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
        
        # Generate summary for a single character
        success_count, total_count = generate_summaries(
            api_provider, 
            target_characters,
            all_characters,
            engine, 
            args
        )
        
        # Log results
        logger.info(f"Successfully processed {success_count} of {total_count} characters")
        
        return 0 if success_count > 0 else 1
    
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())