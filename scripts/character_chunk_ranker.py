#!/usr/bin/env python3
"""
Character Chunk Prioritizer

This script:
1. Uses GPT-4.1 to analyze all chunks where a character appears/is mentioned
2. Scores chunks by importance for character development
3. Creates an optimally-sized context package for o3
4. Includes "new canon" backstory and essential character information

Usage:
    python character_chunk_ranker.py --character <id> [options]
"""

import os
import sys
import json
import logging
import argparse
import time
from typing import Dict, List, Any, Optional, Tuple, Union
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from pydantic import BaseModel, Field

# Import the OpenAI API utility
from api_openai import OpenAIProvider, LLMResponse, get_db_connection_string, setup_abort_handler, is_abort_requested

# Configure logging
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "character_chunk_ranker.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.character_chunk_ranker")

# Define Pydantic models for the structured output
class ChunkScore(BaseModel):
    """Schema for an individual chunk score."""
    chunk_id: int = Field(
        description="The ID of the narrative chunk"
    )
    score: float = Field(
        description="Importance score from 0.00 (irrelevant) to 1.00 (essential) with two decimal precision"
        # Removed min/max constraints as they're not supported by the API
    )

class ChunkScoringResult(BaseModel):
    """Schema for the chunk scoring results."""
    scored_chunks: List[ChunkScore] = Field(
        description="Array of scored chunks with their importance ratings"
    )
    
    class Config:
        """Configure schema generation for OpenAI compatibility."""
        extra = "forbid"  # Equivalent to additionalProperties: false

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Optimize character context package by scoring narrative chunks",
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
        "character_chunk_ranker.json"
    )
    
    try:
        with open(prompt_path, 'r') as f:
            prompt_data = json.load(f)
        
        logger.info(f"Loaded prompt template from {prompt_path}")
        return prompt_data
    except Exception as e:
        logger.error(f"Failed to load prompt from {prompt_path}: {e}")
        raise

def build_scoring_prompt(character: Dict[str, Any], chunks: List[Dict[str, Any]], prompt_template: Dict[str, Any]) -> str:
    """
    Build the complete prompt for the GPT-4.1 API to score chunks.
    
    Args:
        character: Character information dictionary
        chunks: List of narrative chunk dictionaries
        prompt_template: Prompt template loaded from JSON
        
    Returns:
        Complete prompt text
    """
    # Extract character info for template
    character_name = character["name"]
    
    # Format narrative chunks for the template
    chunks_text = []
    for chunk in chunks:
        chunk_id = chunk["id"]
        season = chunk.get("season")
        episode = chunk.get("episode")
        scene = chunk.get("scene")
        raw_text = chunk.get("raw_text", "")
        
        # Format ID and episode info
        header = f"CHUNK ID: {chunk_id}"
        if season and episode:
            header += f" (S{season:02d}E{episode:02d}"
            if scene:
                header += f" Scene {scene:02d}"
            header += ")"
        
        chunks_text.append(f"{header}\n\n{raw_text}\n")
    
    narrative_chunks = "\n---\n".join(chunks_text)
    
    # Replace placeholders in the template
    template_str = json.dumps(prompt_template, indent=2)
    template_str = template_str.replace('"{{character}}"', f'"{character_name}"')
    template_str = template_str.replace('"{{narrative_chunks}}"', f'"<narrative_chunks>"')
    
    # Create first instance of the prompt
    first_prompt = f"""# Character Chunk Scoring Task

## Prompt Template
{template_str}
"""
    
    # Create second instance of the prompt (after the chunks)
    second_prompt = f"""# Character Chunk Scoring Task (REPEATED)

## Prompt Template
{template_str}
"""
    
    # Build final prompt with template repeated before and after the chunks
    prompt = f"{first_prompt}\n\n## Narrative Chunks to Analyze\n<narrative_chunks>\n{narrative_chunks}\n</narrative_chunks>\n\n{second_prompt}"
    
    return prompt

def score_chunks_with_gpt4(provider: OpenAIProvider, character: Dict[str, Any], chunks: List[Dict[str, Any]], 
                        dry_run: bool = False) -> Optional[List[Dict[str, Union[int, float]]]]:
    """
    Use GPT-4.1 to score chunks by importance for character development.
    
    Args:
        provider: OpenAI API provider
        character: Character information dictionary
        chunks: List of narrative chunks
        dry_run: If True, don't make the API call
        
    Returns:
        List of dictionaries with chunk_id and score
    """
    # Load prompt template
    prompt_template = load_prompt_template()
    
    # Build the prompt
    prompt = build_scoring_prompt(character, chunks, prompt_template)
    
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
            temperature=0.2,  # Low temperature for consistent scoring
            text_format=ChunkScoringResult
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
        
        # Validate and clean scores (ensuring they're in the 0.0-1.0 range)
        cleaned_scores = []
        for item in result.scored_chunks:
            score = item.score
            # Ensure score is in valid range
            if score < 0.0:
                logger.warning(f"Score for chunk {item.chunk_id} was negative ({score}), clamping to 0.0")
                score = 0.0
            elif score > 1.0:
                logger.warning(f"Score for chunk {item.chunk_id} was greater than 1.0 ({score}), clamping to 1.0")
                score = 1.0
                
            cleaned_scores.append({"chunk_id": item.chunk_id, "score": score})
            
        return cleaned_scores
    
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return None

def build_context_package(character: Dict[str, Any], scored_chunks: List[Dict[str, Union[int, float]]], 
                        all_chunks: List[Dict[str, Any]], token_limit: int) -> Dict[str, Any]:
    """
    Build the context package with optimally-sized chunks.
    
    Args:
        character: Character information dictionary
        scored_chunks: List of dictionaries with chunk_id and score
        all_chunks: List of all chunk dictionaries
        token_limit: Maximum token size for the package
        
    Returns:
        Context package dictionary
    """
    # Create a map of chunk ID to chunk for quick lookup
    chunk_map = {chunk["id"]: chunk for chunk in all_chunks}
    
    # Sort scored chunks by score (highest first)
    sorted_chunks = sorted(scored_chunks, key=lambda x: x["score"], reverse=True)
    
    # Extract just the IDs in sorted order
    sorted_chunk_ids = [item["chunk_id"] for item in sorted_chunks]
    
    # Initialize the context package with character info
    context_package = {
        "character_id": character["id"],
        "character_name": character["name"],
        "character_aliases": character["aliases"],
        "character_summary": character["summary"],
        "prioritized_chunks": [],
        "token_estimate": 0,
        "creation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Estimate initial token count (character info)
    provider = OpenAIProvider(model="gpt-4.1")
    initial_token_count = provider.count_tokens(json.dumps(context_package))
    context_package["token_estimate"] = initial_token_count
    
    logger.info(f"Initial token count (character info only): {initial_token_count}")
    
    # Add chunks one by one until we reach the token limit
    added_chunks = []
    for chunk_id in sorted_chunk_ids:
        if chunk_id not in chunk_map:
            logger.warning(f"Chunk ID {chunk_id} not found in chunk map, skipping")
            continue
        
        chunk = chunk_map[chunk_id]
        chunk_text = chunk["raw_text"]
        chunk_info = {
            "id": chunk["id"],
            "text": chunk_text,
            "season": chunk.get("season"),
            "episode": chunk.get("episode"),
            "scene": chunk.get("scene"),
            "importance_score": next(item["score"] for item in sorted_chunks if item["chunk_id"] == chunk_id)
        }
        
        # Add chunk to package temporarily
        context_package["prioritized_chunks"].append(chunk_info)
        
        # Recalculate token count
        new_token_count = provider.count_tokens(json.dumps(context_package))
        context_package["token_estimate"] = new_token_count
        
        # Check if we've exceeded the token limit
        if new_token_count >= token_limit:
            # If we're over the limit, remove the chunk we just added
            context_package["prioritized_chunks"].pop()
            context_package["token_estimate"] = provider.count_tokens(json.dumps(context_package))
            logger.info(f"Reached token limit at {len(context_package['prioritized_chunks'])} chunks")
            break
        # If we're very close to the limit (within 5K tokens), also stop
        elif new_token_count >= (token_limit - 5000):
            logger.info(f"Within 5K of token limit at {len(context_package['prioritized_chunks'])} chunks")
            break
        
        # Keep track of added chunks for logging
        added_chunks.append(chunk_id)
    
    # Sort chunks by chronological order (season, episode, scene)
    context_package["prioritized_chunks"] = sorted(
        context_package["prioritized_chunks"],
        key=lambda x: (x.get("season", 0), x.get("episode", 0), x.get("scene", 0))
    )
    
    # Final token count
    final_token_count = provider.count_tokens(json.dumps(context_package))
    context_package["token_estimate"] = final_token_count
    
    logger.info(f"Final context package contains {len(context_package['prioritized_chunks'])} chunks")
    logger.info(f"Final token count: {final_token_count} tokens")
    
    # Print top 20 scores for debugging
    print("\nTop 20 highest-scored chunks:")
    for i, chunk_id in enumerate(added_chunks[:20]):
        score = next(item["score"] for item in sorted_chunks if item["chunk_id"] == chunk_id)
        print(f"#{i+1}: Chunk {chunk_id} (Score: {score:.2f})")
    
    # Calculate and log score distribution
    if scored_chunks:
        score_ranges = {
            "0.90-1.00": 0, 
            "0.80-0.89": 0,
            "0.70-0.79": 0,
            "0.60-0.69": 0,
            "0.50-0.59": 0,
            "0.30-0.49": 0,
            "0.10-0.29": 0,
            "0.00-0.09": 0
        }
        
        for chunk in sorted_chunks:
            score = chunk["score"]
            if score >= 0.90:
                score_ranges["0.90-1.00"] += 1
            elif score >= 0.80:
                score_ranges["0.80-0.89"] += 1
            elif score >= 0.70:
                score_ranges["0.70-0.79"] += 1
            elif score >= 0.60:
                score_ranges["0.60-0.69"] += 1
            elif score >= 0.50:
                score_ranges["0.50-0.59"] += 1
            elif score >= 0.30:
                score_ranges["0.30-0.49"] += 1
            elif score >= 0.10:
                score_ranges["0.10-0.29"] += 1
            else:
                score_ranges["0.00-0.09"] += 1
        
        total_chunks = len(sorted_chunks)
        print("\nScore distribution:")
        for range_name, count in score_ranges.items():
            percentage = (count / total_chunks) * 100
            print(f"{range_name}: {count} chunks ({percentage:.1f}%)")
    
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
        
        logger.info(f"Retrieved {len(all_chunks)} chunks for character {character['name']}")
        
        # Initialize OpenAI provider
        provider = OpenAIProvider(
            model=args.model,
            api_key=args.api_key
        )
        
        # Score chunks with GPT-4.1
        scored_chunks = score_chunks_with_gpt4(
            provider,
            character,
            all_chunks,
            args.dry_run
        )
        
        # If dry run, exit here
        if args.dry_run or not scored_chunks:
            return 0
        
        # Build context package
        context_package = build_context_package(
            character,
            scored_chunks,
            all_chunks,
            args.token_limit
        )
        
        # Save context package
        save_path = save_context_package(context_package, args.output)
        
        print(f"\nSuccessfully created optimized context package for {character['name']}")
        print(f"Package contains {len(context_package['prioritized_chunks'])} prioritized chunks")
        print(f"Estimated token count: {context_package['token_estimate']}")
        print(f"Saved to: {save_path}")
        
        return 0
    
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())