#!/usr/bin/env python3
"""
Character Episode Ranker

This script:
1. Uses GPT-4.1 to rank episodes by importance for character development
2. Takes all narrative chunks where a character appears/is mentioned
3. Has the model rank episodes instead of individual chunks
4. Creates an optimally-sized context package for o3

Usage:
    python character_episode_ranker.py --character <id> [options]
"""

import os
import sys
import json
import logging
import argparse
import time
import re
from typing import Dict, List, Any, Optional, Tuple, Union
from collections import defaultdict
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from pydantic import BaseModel, Field

# Import the OpenAI API utility
from api_openai import OpenAIProvider, LLMResponse, get_db_connection_string, setup_abort_handler, is_abort_requested

# Configure logging
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "character_episode_ranker.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.character_episode_ranker")

# Define Pydantic models for the structured output
class EpisodeRankingResult(BaseModel):
    """Schema for the episode ranking results."""
    ranked_episodes: List[str] = Field(
        description="Ordered array of episode identifiers from most to least important for character understanding"
    )
    
    class Config:
        """Configure schema generation for OpenAI compatibility."""
        extra = "forbid"  # Equivalent to additionalProperties: false

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Optimize character context package by ranking episodes",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Required: Character ID
    parser.add_argument("--character", required=True, type=int,
                      help="Character ID to process")
    
    # Optional: LLM options
    parser.add_argument("--model", default="gpt-4.1",
                      help="Model to use (default: gpt-4.1)")
    parser.add_argument("--output", 
                      help="Path to save the output package (default: character_context_<id>.json)")
    parser.add_argument("--token-limit", type=int, default=200000,
                      help="Maximum token size for context package (default: 200k)")
    parser.add_argument("--api-key", 
                      help="OpenAI API key (optional, defaults to environment variables)")
    
    # Test/Debug options
    parser.add_argument("--dry-run", action="store_true",
                      help="Don't make actual API calls, just prepare and show what would be sent")
    parser.add_argument("--debug", action="store_true",
                      help="Enable debug logging")
    parser.add_argument("--db-url", 
                      help="Database connection URL (optional, defaults to environment variables)")
    
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

def get_character_info(engine: sa.engine.Engine, character_id: int) -> Dict[str, Any]:
    """
    Get character information from the database.
    
    Args:
        engine: Database connection engine
        character_id: Character ID to retrieve
        
    Returns:
        Character information dictionary
    """
    query = """
    SELECT id, name, aliases, summary
    FROM characters
    WHERE id = :character_id
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query), {"character_id": character_id})
        character = result.fetchone()
        
    if not character:
        raise ValueError(f"Character with ID {character_id} not found")
    
    # Convert to dictionary
    character_dict = dict(character._mapping)
    logger.info(f"Retrieved character info for {character_dict['name']} (ID: {character_id})")
    
    return character_dict

def get_character_chunks(engine: sa.engine.Engine, character_id: int) -> List[Dict[str, Any]]:
    """
    Get all narrative chunks where a character appears or is mentioned.
    
    Args:
        engine: Database connection engine
        character_id: Character ID to find chunks for
        
    Returns:
        List of narrative chunk dictionaries
    """
    # First get the chunk IDs from character_reference_view
    ref_query = """
    SELECT chunks_in
    FROM character_reference_view
    WHERE character_id = :character_id
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(ref_query), {"character_id": character_id})
        row = result.fetchone()
        
    if not row or not row[0]:
        logger.warning(f"No chunks found for character ID {character_id}")
        return []
    
    chunk_ids = row[0]  # This is a PostgreSQL array of chunk IDs
    logger.info(f"Found {len(chunk_ids)} chunks where character ID {character_id} appears or is mentioned")
    
    # Then get the narrative chunks with their metadata
    chunks_query = """
    SELECT 
        nc.id,
        nc.raw_text,
        cm.season,
        cm.episode,
        cm.scene,
        cm.characters,
        cm.world_layer
    FROM 
        narrative_chunks nc
    JOIN 
        chunk_metadata cm ON nc.id = cm.chunk_id
    WHERE 
        nc.id = ANY(:chunk_ids)
    ORDER BY 
        cm.season, cm.episode, cm.scene
    """
    
    chunks = []
    with engine.connect() as conn:
        result = conn.execute(text(chunks_query), {"chunk_ids": chunk_ids})
        for row in result:
            chunks.append(dict(row._mapping))
    
    logger.info(f"Retrieved {len(chunks)} narrative chunks for character ID {character_id}")
    return chunks

def group_chunks_by_episode(chunks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group narrative chunks by episode.
    
    Args:
        chunks: List of narrative chunk dictionaries
        
    Returns:
        Dictionary mapping episode IDs to lists of chunks
    """
    episode_chunks = defaultdict(list)
    
    for chunk in chunks:
        season = chunk.get("season")
        episode = chunk.get("episode")
        
        if season is not None and episode is not None:
            episode_id = f"S{season:02d}E{episode:02d}"
            episode_chunks[episode_id].append(chunk)
    
    # Log some stats about the distribution
    episode_count = len(episode_chunks)
    min_chunks = min(len(c) for c in episode_chunks.values()) if episode_chunks else 0
    max_chunks = max(len(c) for c in episode_chunks.values()) if episode_chunks else 0
    
    logger.info(f"Character appears in {episode_count} episodes")
    logger.info(f"Min chunks per episode: {min_chunks}, Max chunks per episode: {max_chunks}")
    
    return episode_chunks

def load_prompt_template() -> Dict[str, Any]:
    """
    Load the prompt template from JSON file.
    
    Returns:
        Dictionary with prompt components
    """
    # Load from project root's prompts directory
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Go up one level to root
        "prompts",
        "character_episode_ranker.json"
    )
    
    try:
        with open(prompt_path, 'r') as f:
            prompt_data = json.load(f)
        
        logger.info(f"Loaded prompt template from {prompt_path}")
        return prompt_data
    except Exception as e:
        logger.error(f"Failed to load prompt from {prompt_path}: {e}")
        raise

def build_episode_ranking_prompt(character: Dict[str, Any], episode_chunks: Dict[str, List[Dict[str, Any]]], 
                             prompt_template: Dict[str, Any]) -> str:
    """
    Build the prompt for the episode ranking API call.
    
    Args:
        character: Character information dictionary
        episode_chunks: Dictionary mapping episode IDs to lists of chunks
        prompt_template: Prompt template loaded from JSON
        
    Returns:
        Complete prompt text
    """
    # Extract character info for template
    character_name = character["name"]
    
    # Format episode content
    episode_text = []
    for episode_id, chunks in episode_chunks.items():
        # Sort chunks by scene number
        sorted_chunks = sorted(chunks, key=lambda x: x.get("scene", 0))
        
        # Extract season and episode numbers for header
        season_match = re.search(r'S(\d+)', episode_id)
        episode_match = re.search(r'E(\d+)', episode_id)
        
        if season_match and episode_match:
            season_num = int(season_match.group(1))
            episode_num = int(episode_match.group(1))
        else:
            # Fallback to the first chunk's metadata
            season_num = sorted_chunks[0].get("season", 0)
            episode_num = sorted_chunks[0].get("episode", 0)
        
        # Prepare episode header
        header = f"EPISODE {episode_id}"
        
        # Prepare chunk texts
        chunk_texts = []
        for chunk in sorted_chunks:
            scene = chunk.get("scene")
            scene_text = f"Scene {scene:02d}: " if scene is not None else ""
            chunk_texts.append(f"{scene_text}{chunk['raw_text']}")
        
        # Join all chunks for this episode
        episode_content = "\n\n".join(chunk_texts)
        
        # Add the full episode entry
        episode_text.append(f"{header}\n\n{episode_content}")
    
    formatted_episodes = "\n\n" + "="*40 + "\n\n".join(episode_text)
    
    # Replace placeholders in the template
    template_str = json.dumps(prompt_template, indent=2)
    template_str = template_str.replace('"{{character}}"', f'"{character_name}"')
    template_str = template_str.replace('"{{episode_summaries}}"', f'"<episode_content>"')
    
    # Build final prompt
    prompt = f"""# Episode Ranking Task for Character Importance

## Character Information
Name: {character_name}
Summary: {character["summary"]}

## Prompt Template
{template_str}

## Episode Content (Character's Scenes)
<episode_content>
{formatted_episodes}
</episode_content>
"""
    
    return prompt

def rank_episodes_with_gpt4(provider: OpenAIProvider, character: Dict[str, Any], 
                           episode_chunks: Dict[str, List[Dict[str, Any]]],
                           dry_run: bool = False) -> Optional[List[str]]:
    """
    Use GPT-4.1 to rank episodes by importance for character development.
    
    Args:
        provider: OpenAI API provider
        character: Character information dictionary
        episode_chunks: Dictionary mapping episode IDs to lists of chunks
        dry_run: If True, don't make the API call
        
    Returns:
        List of episode identifiers (S##E##) ranked by importance
    """
    # Load prompt template
    prompt_template = load_prompt_template()
    
    # Build the prompt
    prompt = build_episode_ranking_prompt(character, episode_chunks, prompt_template)
    
    # If dry run, just print the prompt and return
    if dry_run:
        logger.info("DRY RUN: Prompt that would be sent to API:")
        print("\n" + "="*80 + "\n")
        print(prompt)
        print("\n" + "="*80 + "\n")
        return None
    
    # Make API call for structured output
    prompt_tokens = provider.count_tokens(prompt)
    logger.info(f"Prompt size: {prompt_tokens} tokens")
    
    start_time = time.time()
    
    try:
        # Format the messages for the API call
        messages = [{"role": "user", "content": prompt}]
        
        # Using responses.parse() with our Pydantic model
        response = provider.client.responses.parse(
            model=provider.model,
            input=messages,
            temperature=0.2,  # Low temperature for consistent ranking
            text_format=EpisodeRankingResult
        )
        
        # Get the parsed result
        result = response.output_parsed
        
        # Create a compatible response object for metrics
        llm_response = LLMResponse(
            content=response.output_text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=provider.model,
            raw_response=response
        )
        
        # Log performance metrics
        elapsed_time = time.time() - start_time
        logger.info(f"API call completed in {elapsed_time:.2f} seconds")
        logger.info(f"Input tokens: {llm_response.input_tokens}, Output tokens: {llm_response.output_tokens}")
        
        # Return the ranked episodes
        return result.ranked_episodes
    
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return None

def build_context_package(character: Dict[str, Any], ranked_episodes: List[str], 
                        episode_chunks: Dict[str, List[Dict[str, Any]]],
                        token_limit: int) -> Dict[str, Any]:
    """
    Build the context package with chunks ordered by episode importance.
    
    Args:
        character: Character information dictionary
        ranked_episodes: List of episode identifiers ranked by importance
        episode_chunks: Dictionary mapping episode IDs to lists of chunks
        token_limit: Maximum token size for the package
        
    Returns:
        Context package dictionary
    """
    # Initialize the context package with character info
    context_package = {
        "character_id": character["id"],
        "character_name": character["name"],
        "character_aliases": character["aliases"],
        "character_summary": character["summary"],
        "episodes": [],
        "token_estimate": 0,
        "creation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Estimate initial token count (character info only)
    provider = OpenAIProvider(model="gpt-4.1")
    initial_token_count = provider.count_tokens(json.dumps(context_package))
    context_package["token_estimate"] = initial_token_count
    
    logger.info(f"Initial token count (character info only): {initial_token_count}")
    
    # Calculate available token budget
    available_tokens = token_limit - initial_token_count
    logger.info(f"Available token budget for chunks: {available_tokens}")
    
    # Track included episodes
    included_episodes = []
    
    # Process episodes in order of importance
    for episode_id in ranked_episodes:
        # Skip if episode not in our data
        if episode_id not in episode_chunks:
            logger.warning(f"Episode {episode_id} not found in episode chunks, skipping")
            continue
        
        # Get chunks for this episode
        chunks = episode_chunks[episode_id]
        
        # Sort chunks by scene
        sorted_chunks = sorted(chunks, key=lambda x: x.get("scene", 0))
        
        # Format episode data
        episode_data = {
            "id": episode_id,
            "season": sorted_chunks[0].get("season"),
            "episode": sorted_chunks[0].get("episode"),
            "chunks": []
        }
        
        # Add chunk info
        for chunk in sorted_chunks:
            chunk_info = {
                "id": chunk["id"],
                "text": chunk["raw_text"],
                "scene": chunk.get("scene")
            }
            episode_data["chunks"].append(chunk_info)
        
        # Create a temporary copy of the context package
        temp_package = json.loads(json.dumps(context_package))
        temp_package["episodes"].append(episode_data)
        
        # Calculate new token count
        new_token_count = provider.count_tokens(json.dumps(temp_package))
        tokens_needed = new_token_count - context_package["token_estimate"]
        
        # If we have enough tokens, update the real package
        if tokens_needed <= available_tokens:
            context_package = temp_package
            context_package["token_estimate"] = new_token_count
            available_tokens -= tokens_needed
            included_episodes.append(episode_id)
            logger.info(f"Added episode {episode_id} - Used {tokens_needed} tokens")
            logger.info(f"Remaining token budget: {available_tokens}")
        else:
            logger.info(f"Not enough tokens for {episode_id} - Would need {tokens_needed} tokens")
            logger.info(f"Skipping episode {episode_id}")
            break  # Stop processing episodes since we're out of tokens
    
    # Final token count
    final_token_count = provider.count_tokens(json.dumps(context_package))
    context_package["token_estimate"] = final_token_count
    
    # Add metadata about included episodes
    context_package["included_episodes"] = included_episodes
    
    logger.info(f"Final context package contains chunks from {len(included_episodes)} episodes")
    logger.info(f"Final token count: {final_token_count} tokens")
    logger.info(f"Included episodes (in priority order): {', '.join(included_episodes)}")
    
    return context_package

def save_context_package(context_package: Dict[str, Any], output_path: Optional[str] = None) -> str:
    """
    Save the context package to a file.
    
    Args:
        context_package: Context package dictionary
        output_path: Optional output file path
        
    Returns:
        Path where the file was saved
    """
    # Generate default filename if not provided
    if not output_path:
        character_id = context_package["character_id"]
        output_path = f"character_context_{character_id}.json"
    
    # Make sure the path is absolute
    if not os.path.isabs(output_path):
        output_path = os.path.join(os.getcwd(), output_path)
    
    # Save the file
    with open(output_path, 'w') as f:
        json.dump(context_package, f, indent=2)
    
    logger.info(f"Saved context package to {output_path}")
    return output_path

def main():
    """Main function."""
    # Parse arguments
    args = parse_arguments()
    
    # Set up logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logging.getLogger("nexus").setLevel(logging.DEBUG)
    
    # Set up abort handler
    setup_abort_handler("Abort requested! Will finish current operation and stop.")
    
    try:
        # Connect to database
        engine = connect_to_database(args.db_url)
        
        # Get character info
        character = get_character_info(engine, args.character)
        
        # Get all chunks where the character appears or is mentioned
        all_chunks = get_character_chunks(engine, args.character)
        
        if not all_chunks:
            logger.error(f"No chunks found for character {args.character} ({character['name']})")
            return 1
        
        # Group chunks by episode
        episode_chunks = group_chunks_by_episode(all_chunks)
        
        if not episode_chunks:
            logger.error("Failed to group chunks by episode")
            return 1
            
        # Initialize OpenAI provider
        provider = OpenAIProvider(
            model=args.model,
            api_key=args.api_key
        )
        
        # Rank episodes with GPT-4.1
        ranked_episodes = rank_episodes_with_gpt4(
            provider,
            character,
            episode_chunks,
            args.dry_run
        )
        
        # If dry run, exit here
        if args.dry_run or not ranked_episodes:
            return 0
        
        # Build context package
        context_package = build_context_package(
            character,
            ranked_episodes,
            episode_chunks,
            args.token_limit
        )
        
        # Save context package
        save_path = save_context_package(context_package, args.output)
        
        print(f"\nSuccessfully created optimized context package for {character['name']}")
        print(f"Package includes chunks from {len(context_package['included_episodes'])} episodes")
        print(f"Episodes included (in priority order): {', '.join(context_package['included_episodes'])}")
        print(f"Estimated token count: {context_package['token_estimate']}")
        print(f"Saved to: {save_path}")
        
        return 0
    
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())