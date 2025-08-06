#!/usr/bin/env python3
"""
Location Mapping Script for NEXUS

This script processes narrative chunks using an API-based LLM to extract
location information for each chunk. It maps scenes to existing locations
when possible and identifies new locations to be added to the database.

Usage Examples:
    # Test connection and show prompt for the first processable chunk
    python map_builder.py --test
    
    # Test with a specific chunk (e.g., ID 2) to see how the prompt would look with context from chunk 1
    python map_builder.py --start 2 --test

    # Process a single chunk (e.g., ID 5) and write to DB
    python map_builder.py --start 5

    # Process a range of chunks (e.g., IDs 10 to 20) and write to DB
    python map_builder.py --start 10 --end 20

    # Process all chunks that currently lack location data
    python map_builder.py --all

    # Process all chunks, overwriting existing location data
    python map_builder.py --all --overwrite

    # Process all chunks using a specific provider and model
    python map_builder.py --all --provider anthropic --model claude-3-5-haiku-20241022

    # Process all chunks with a smaller batch size and without confirmation prompts
    python map_builder.py --all --batch-size 5 --auto

    # Run in dry-run mode (print actions but don't write to DB)
    python map_builder.py --start 1 --end 10 --dry-run

    # Show detailed logs during processing
    python map_builder.py --start 1 --verbose

Supported Arguments:
    --provider TEXT         LLM provider ('anthropic', 'openai') [default: anthropic]
    --model TEXT            LLM model name [default: claude-3-5-haiku-20241022]
    --api-key TEXT          API key (optional)
    --temperature FLOAT     Sampling temperature [default: 0.1]
    --max-tokens INTEGER    Maximum output tokens (optional)
    --system-prompt TEXT    System prompt string (optional)
    --db-url TEXT           Database connection string (optional, defaults from config)
    --batch-size INTEGER    Number of chunks to process per API batch [default: 10]
    --dry-run               Perform processing without writing to the database
    --verbose               Print detailed information including prompts and reasoning
    --thinking              Enable Claude's thinking mode (Anthropic only, temperature ignored)

    Chunk Selection (Required: Choose one method):
      --start INTEGER       Starting chunk ID number (use with --end or process single)
      --all                 Process all chunks needing location data (or all if --overwrite)
      --test                Test DB connection and print prompt for first chunk, then exit

    Chunk Selection Modifiers:
      --end INTEGER         Ending chunk ID number (used with --start)
      --overwrite           Process all chunks in range/all, including those with existing data

    Processing Control:
      --auto                Process automatically without prompting BETWEEN batches
                           (Note: New location submissions will ALWAYS prompt for verification)

Database URL (from api_batch.py):
postgresql://pythagor@localhost/NEXUS
"""

import os
import sys
import argparse
import logging
import time
import json
import re
from typing import List, Tuple, Optional, Dict, Any, Set

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy import create_engine, text

# Import necessary components from api_batch.py
try:
    from api_batch import (
        LLMProvider, AnthropicProvider, LLMResponse, get_token_count,
        get_db_connection_string, get_default_llm_argument_parser,
        validate_llm_requirements, SETTINGS, TPM_LIMITS, COOLDOWNS, logger
    )
except ImportError as e:
    print("Error: Could not import from api_batch.py. Make sure it's in the same directory or Python path.")
    print(e)
    sys.exit(1)

# Default model if not specified via CLI - use claude-3-5-haiku for structured output
DEFAULT_MODEL_FOR_SCRIPT = "claude-3-5-haiku-20241022"

# --- Database Schema Constants ---
NARRATIVE_CHUNKS_TABLE = "narrative_chunks"
CHUNK_METADATA_TABLE = "chunk_metadata"
PLACES_TABLE = "places"
ZONES_TABLE = "zones"

class NarrativeChunk:
    """Class to represent a narrative chunk for processing."""
    def __init__(self, id: int, raw_text: str, slug: Optional[str] = None):
        self.id = id
        self.raw_text = raw_text
        self.slug = slug

class KnownPlace:
    """Class to represent a known place loaded from the database."""
    def __init__(self, id: int, name: str, type: str, zone: int, summary: Optional[str] = None):
        self.id = id
        self.name = name
        self.type = type
        self.zone = zone
        self.summary = summary

class Zone:
    """Class to represent a zone loaded from the database."""
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments, extending the base parser from api_batch."""
    parser = get_default_llm_argument_parser()
    parser.description = "Extract location information from narrative chunks using an LLM."

    # Override default model specifically for this script
    for action in parser._actions:
        if action.dest == 'model':
            action.default = DEFAULT_MODEL_FOR_SCRIPT
            action.help = f"Model name to use (defaults to {DEFAULT_MODEL_FOR_SCRIPT} for this script)"
            break
            
    # Override default provider to be Anthropic
    for action in parser._actions:
        if action.dest == 'provider':
            action.default = "anthropic"  # Change default from "openai" to "anthropic"
            break

    # Add chunk selection arguments
    chunk_group = parser.add_argument_group("Chunk Selection Options")
    selection_method = chunk_group.add_mutually_exclusive_group(required=False)  # Changed to not required so --test can work alone
    selection_method.add_argument("--start", type=int, help="Starting chunk id number")
    selection_method.add_argument("--all", action="store_true", help="Process all chunks needing location data")
    
    # Move --test outside the mutually exclusive group since it's a mode, not a chunk selection method
    parser.add_argument("--test", action="store_true", 
                       help="Test mode: Show the prompt that would be used (can be combined with --start to test a specific chunk).")
    parser.add_argument("--overwrite", action="store_true", 
                       help="Process all chunks in range or all chunks in database, including those with existing location data.")

    chunk_group.add_argument("--end", type=int, help="Ending chunk id number (defaults to start if only start is provided)")

    # Add processing control arguments (reuse from api_batch)
    process_group = next((g for g in parser._action_groups if g.title == "Processing Options"), None)
    if process_group:
        process_group.add_argument("--auto", action="store_true", help="Process all chunks automatically without prompting between batches")
        process_group.add_argument("--verbose", action="store_true", help="Print detailed information including prompts")
        process_group.add_argument("--thinking", action="store_true", 
                                 help="Enable Claude's thinking mode (Anthropic provider only) to see detailed reasoning")

    args = parser.parse_args()

    # Validate arguments
    if args.start is not None and args.end is None:
        args.end = args.start  # Default end to start

    # Ensure that either --test is used or a chunk selection method is specified
    if not args.test and not (args.start is not None or args.all):
        parser.error("Either --test mode or a chunk selection method (--start or --all) is required")
        
    if not args.dry_run and not hasattr(args, 'db_url'):
        # If not dry run, ensure db_url is set (or default is used)
        args.db_url = args.db_url or get_db_connection_string()

    # Adjust logger level based on verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.info("Verbose mode enabled.")
    else:
        logger.setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(logging.WARNING) # Suppress HTTPX logs

    return args

def get_db_connection(db_url: str) -> Engine:
    """Get database connection using SQLAlchemy."""
    try:
        engine = create_engine(db_url)
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful.")
        return engine
    except Exception as e:
        logger.error(f"Database connection error to {db_url}: {str(e)}")
        raise

def check_database_schema(db: Engine) -> bool:
    """Check if the database schema is correct for this script to run."""
    try:
        with db.connect() as conn:
            # Simplified validation - check if tables exist and can be joined
            try:
                # Verify places table exists
                places_query = text("SELECT 1 FROM places LIMIT 1")
                conn.execute(places_query)
                
                # Verify chunk_metadata table with place column exists
                metadata_query = text("SELECT place FROM chunk_metadata LIMIT 1")
                conn.execute(metadata_query)
                
                # Verify we can join the tables (this confirms the relationship works properly)
                join_query = text("""
                    SELECT 1 
                    FROM chunk_metadata cm
                    LEFT JOIN places p ON cm.place = p.id
                    LIMIT 1
                """)
                conn.execute(join_query)
                
                # All checks passed
                logger.info("Database schema validation successful. Tables and relationships verified.")
                return True
            except Exception as e:
                logger.error(f"Database schema validation failed: {e}")
                return False
    except Exception as e:
        logger.error(f"Error checking database schema: {str(e)}")
        return False

def load_known_places(db: Engine) -> Dict[int, KnownPlace]:
    """Load all existing places from the database."""
    places = {}
    try:
        with db.connect() as conn:
            result = conn.execute(
                text(f"SELECT id, name, type, zone, summary FROM {PLACES_TABLE}")
            ).fetchall()

            for row in result:
                place = KnownPlace(
                    id=row[0], 
                    name=row[1], 
                    type=row[2], 
                    zone=row[3],
                    summary=row[4] if len(row) > 4 else None
                )
                places[place.id] = place # Store by ID for easy lookup
            logger.info(f"Loaded {len(result)} known places from the database.")
            return places
    except Exception as e:
        logger.error(f"Error loading known places: {str(e)}")
        return {}

def load_zones(db: Engine) -> Dict[int, Zone]:
    """Load all zones from the database."""
    zones = {}
    try:
        with db.connect() as conn:
            result = conn.execute(
                text(f"SELECT id, name FROM {ZONES_TABLE}")
            ).fetchall()

            for row in result:
                zone = Zone(id=row[0], name=row[1])
                zones[zone.id] = zone
            logger.info(f"Loaded {len(result)} zones from the database.")
            return zones
    except Exception as e:
        logger.error(f"Error loading zones: {str(e)}")
        return {}

def get_chunks_to_process(db: Engine, start_id: Optional[int] = None, end_id: Optional[int] = None, overwrite: bool = False) -> List[NarrativeChunk]:
    """Get chunks to process based on ID range or all needing location data.
    
    Args:
        db: Database engine
        start_id: Optional starting chunk ID
        end_id: Optional ending chunk ID
        overwrite: If True, process all chunks regardless of existing location data
    """
    chunks = []
    try:
        with db.connect() as conn:
            if start_id is not None and end_id is not None:
                # Get chunks in a specific range
                query = text(f"""
                    SELECT nc.id, nc.raw_text, cm.slug
                    FROM {NARRATIVE_CHUNKS_TABLE} nc
                    LEFT JOIN {CHUNK_METADATA_TABLE} cm ON nc.id = cm.chunk_id
                    WHERE nc.id BETWEEN :start AND :end
                    ORDER BY nc.id
                """)
                results = conn.execute(query, {"start": start_id, "end": end_id}).fetchall()
                logger.info(f"Found {len(results)} chunks in range {start_id}-{end_id}.")
            else:
                # Determine query based on overwrite flag
                if overwrite:
                    # Get all chunks regardless of location data
                    query = text(f"""
                        SELECT nc.id, nc.raw_text, cm.slug
                        FROM {NARRATIVE_CHUNKS_TABLE} nc
                        LEFT JOIN {CHUNK_METADATA_TABLE} cm ON nc.id = cm.chunk_id
                        ORDER BY nc.id
                    """)
                    results = conn.execute(query).fetchall()
                    logger.info(f"Found {len(results)} total chunks for processing (overwrite=True).")
                else:
                    # Get only chunks where location data is missing
                    query = text(f"""
                        SELECT nc.id, nc.raw_text, cm.slug
                        FROM {NARRATIVE_CHUNKS_TABLE} nc
                        LEFT JOIN {CHUNK_METADATA_TABLE} cm ON nc.id = cm.chunk_id
                        WHERE cm.place IS NULL
                        ORDER BY nc.id
                    """)
                    results = conn.execute(query).fetchall()
                    logger.info(f"Found {len(results)} chunks needing location processing.")

            return [NarrativeChunk(id=row[0], raw_text=row[1], slug=row[2]) for row in results]
    except Exception as e:
        logger.error(f"Error fetching chunks to process: {str(e)}")
        return []

def format_known_places_for_prompt(places: Dict[int, KnownPlace], zones: Dict[int, Zone]) -> str:
    """Format the known places for the LLM prompt, displaying a hierarchical tree structure based on zone relationships."""
    if not places or not zones:
        return "None available."
    
    # Group places by zone
    places_by_zone = {}
    for place_id, place in places.items():
        zone_id = place.zone
        if zone_id not in places_by_zone:
            places_by_zone[zone_id] = []
        places_by_zone[zone_id].append((place_id, place))
    
    # Format places header
    places_section = "KNOWN PLACES ORDERED BY ZONE:\n\n"
    
    # Process each zone and its places
    for zone_id, zone_places in sorted(places_by_zone.items()):
        # Get zone name
        zone_name = zones[zone_id].name if zone_id in zones else f"Unknown Zone (ID: {zone_id})"
        
        # Zone header
        places_section += f"Zone {zone_id} {zone_name}/\n"
        
        # Add places in this zone
        for place_id, place in sorted(zone_places):
            place_summary = f" - {place.summary}" if place.summary else ""
            places_section += f"├─── {place_id}: {place.name} ({place.type}){place_summary}\n"
    
    return places_section

def build_location_extraction_prompt(
    chunk: NarrativeChunk, 
    known_places_formatted: str, 
    prev_chunks_info: List[Tuple[NarrativeChunk, Optional[KnownPlace]]] = None
) -> str:
    """Build the prompt for the LLM to extract location information.
    
    Args:
        chunk: The current chunk to process
        known_places_formatted: Formatted string of known places and zones
        prev_chunks_info: List of tuples containing previous chunks and their places, ordered from most recent to oldest
    """
    # We'll combine context and text in the same section
    prev_chunks_context = ""
    prev_chunks_text = ""
    
    if prev_chunks_info:
        # Reverse the list to present older chunks first (chronological order)
        prev_chunks_list = list(reversed(prev_chunks_info))
        
        for i, (prev_chunk, prev_place) in enumerate(prev_chunks_list):
            # Create location info string
            location_info = ""
            if prev_place:
                location_info = f"Location: ID {prev_place.id} - {prev_place.name}"
            else:
                location_info = "Location: Not determined"
            
            # Add the chunk with integrated location info
            prev_chunks_text += f"""
CONTEXT CHUNK {prev_chunk.id} ({location_info})
```
{prev_chunk.raw_text}
```
"""

    # Main system prompt with all instructions merged together
    system_prompt = """Extract the PRIMARY PLACE where this scene takes place.

Definition of a place:
- A discrete, scene-scale space where characters can be present and narrative takes place
- Can be a fixed location (building, area, etc.), vehicle, or virtual space
- Should be specific enough to distinguish it from other settings
- Do not subdivide existing places by identifying new sub-locations within it, e.g.,
    * if known places contain "USS Narwhal", do not identify "USS Narwhal - Galley" as a new place
    * if known places contain a particular hotel, do not identify specific floors, rooms, or areas within it as a new location
- Place is often (but not always) indicated in a heading, usually with this kind of formatting: 📍 **Seaside Bar, Virginia Beach**

IMPORTANT: When choosing between known places, carefully consider:
1. The place summaries provided - these offer key information about each location
2. The specific context and setting details in the narrative
3. Character movements and environmental descriptions
4. Explicit location mentions in headings or dialogue
5. Previous chunk location context (when provided) - continuity between scenes is important

Guidelines:
- Analyze the TARGET CHUNK to identify its PRIMARY location.
- Context chunks are provided in chronological order (oldest first) with their locations to help determine continuity.
- If there are no explicit indicators of a location change between context chunks and target chunk, and the narrative seems continuous, prefer the most recent context chunk's location.
- Identify the PRIMARY place where the main action occurs.
- For KNOWN places, provide the ID from the KNOWN PLACES LIST.
- Carefully read place summaries to help select the correct known place.
- For NEW places (not in the list), provide name, type, and parent zone ID.
- For place type, use:
  * "fixed_location" for buildings, areas, cities, etc.
  * "vehicle" for cars, submarines, aircraft, etc.
  * "other" for virtual spaces, mental landscapes, etc.
- For vehicles, use zone ID to indicate current location.
- Assign a confidence score (0.0-1.0) for each identification.
- Lower the confidence score if a place match is uncertain.
- Only return a valid JSON object and nothing else.

Edge Cases:
- If the narrative moves between more than one place during the chunk, choose the place where most of the action occurs.
- If the user is discussing and deliberating choices with the AI and the narrative is not advancing, infer that the user's character is also deliberating in-game and select the last-used location.

"""

    # JSON schema specification
    # Use double curly braces {{ }} to escape literal JSON braces in the f-string
    json_schema = f"""
Return ONLY a valid JSON object adhering strictly to the following schema:
```json
{{
  "chunk_id": "{chunk.id}",
  "reasoning": "1-2 sentences explaining your decision process for selecting this location",
  "primary_location": {{
    "status": "known OR new",
    
    /* For known locations (status=\"known\"): */
    "id": 123, /* matching ID from the KNOWN LOCATIONS LIST */
    "confidence": 0.9,
    
    /* For new locations (status=\"new\"): */
    "name": "Location name",
    "type": "fixed_location|vehicle|other",
    "zone": 1, /* matching ID from the KNOWN LOCATIONS LIST */
    "confidence": 0.9
  }},
  "mentioned_locations": [
    /* Same structure as primary_location */
  ]
}}
```
"""

    # Target chunk section
    target_chunk = f"""
TARGET CHUNK {chunk.id} TEXT:
```
{chunk.raw_text}
```
"""

    # Assemble the prompt in the desired order
    prompt = f"""{system_prompt}

{known_places_formatted}

{json_schema}

{prev_chunks_text}
{target_chunk}
"""
    return prompt

def get_llm_structured_response(prompt: str, provider_instance: LLMProvider, chunk_id: int, verbose: bool = False, thinking_mode: bool = False) -> Optional[Dict[str, Any]]:
    """Calls the LLM provider ensuring structured JSON output.
    
    For Anthropic provider, uses the ephemeral cache control feature to optimize token usage.
    Handles caching of both current and previous chunk text for efficient token usage.
    
    Args:
        prompt: The prompt to send to the LLM
        provider_instance: The LLM provider instance
        chunk_id: The chunk ID being processed (for caching)
        verbose: Whether to log detailed debug information
        thinking_mode: Whether to enable Claude's thinking mode (Anthropic only)
    """
    try:
        # If this is an Anthropic provider, use the cache_control feature
        if isinstance(provider_instance, AnthropicProvider) and hasattr(provider_instance.client, 'messages'):
            # Check that the chunk_id is valid
            if not chunk_id or chunk_id <= 0:
                logger.warning("Invalid chunk_id for caching, falling back to standard completion")
                response = provider_instance.get_completion(prompt)
            else:
                if thinking_mode:
                    logger.info(f"Using Anthropic with ephemeral caching and thinking mode for chunk {chunk_id}")
                else:
                    logger.info(f"Using Anthropic with ephemeral caching for chunk {chunk_id}")
                
                # Initialize api_response variable
                api_response = None
                
                # If thinking mode is enabled
                if thinking_mode:
                    # Get thinking configuration from settings.json
                    thinking_config = SETTINGS.get("API Settings", {}).get("map_builder", {})
                    
                    if "max_tokens" in thinking_config and "budget_tokens" in thinking_config:
                        max_tokens_value = thinking_config["max_tokens"]
                        budget_tokens_value = thinking_config["budget_tokens"]
                        logger.info(f"Thinking mode requested with max_tokens={max_tokens_value}, budget_tokens={budget_tokens_value}")
                        
                        # Use direct API call for thinking mode
                        try:
                            # 1. Get API key from provider_instance
                            api_key = provider_instance.client.api_key
                            model_name = provider_instance.model
                            temp = provider_instance.temperature
                            
                            # 2. Import httpx for direct API call
                            import httpx
                            
                            # 3. Direct API call to Anthropic with thinking enabled
                            logger.info(f"Making direct API call to Anthropic with thinking mode enabled")
                            
                            # 4. Prepare headers and payload
                            headers = {
                                "x-api-key": api_key,
                                "anthropic-version": "2023-06-01",  # Stick with known working version
                                "content-type": "application/json",
                            }
                            
                            # Extract the system prompt part from the prompt if possible
                            system_prompt = ""
                            user_prompt = prompt
                            if "Extract the PRIMARY PLACE where this scene takes place." in prompt:
                                # Try to extract the system instruction part from the prompt
                                parts = prompt.split("KNOWN PLACES LIST:")
                                if len(parts) > 1:
                                    system_prompt = parts[0].strip()
                                    user_prompt = "KNOWN PLACES LIST:" + parts[1]
                            
                            # Prepare the payload with the correct structure
                            payload = {
                                "model": model_name,
                                "max_tokens": max_tokens_value,
                                # Omit temperature when using thinking mode (per documentation)
                                "messages": [
                                    {"role": "user", "content": user_prompt + "\n\nIMPORTANT: Your thinking is extremely helpful, but you MUST provide a valid JSON response after your thinking. The JSON response is required and must follow the schema exactly."}
                                ]
                            }
                            
                            # Log info about temperature being omitted
                            if temp != 0:
                                logger.info(f"Omitting temperature parameter (was {temp}) when using thinking mode")
                            
                            # Add system if available
                            if system_prompt:
                                payload["system"] = system_prompt
                                
                            # Add thinking parameter
                            payload["thinking"] = {
                                "type": "enabled",
                                "budget_tokens": budget_tokens_value
                            }
                            
                            # Log the API call details
                            logger.info(f"API request payload structure: {json.dumps({k: '...' for k in payload.keys()}, indent=2)}")
                            if 'system' in payload:
                                logger.info(f"System prompt length: {len(payload['system'])}")
                            
                            # If verbose, log even more details
                            if verbose:
                                # Log a truncated version of the full payload for debugging
                                payload_log = {}
                                for k, v in payload.items():
                                    if k == "messages":
                                        payload_log[k] = [
                                            {mk: (mv[:100] + "..." if isinstance(mv, str) and len(mv) > 100 else mv) 
                                             for mk, mv in msg.items()}
                                            for msg in v
                                        ]
                                    elif k == "system" and isinstance(v, str):
                                        payload_log[k] = v[:100] + "..." if len(v) > 100 else v
                                    else:
                                        payload_log[k] = v
                                
                                logger.debug(f"API request payload details: {json.dumps(payload_log, indent=2)}")
                            
                            # 5. Make the API call with detailed debug logging
                            with httpx.Client(timeout=120.0) as client:
                                logger.debug("Sending API request to Anthropic...")
                                response_data = client.post(
                                    "https://api.anthropic.com/v1/messages",
                                    headers=headers,
                                    json=payload
                                )
                                # Always log the API response status
                                logger.info(f"Received API response with status code: {response_data.status_code}")
                                
                                # Always log the raw response for debugging (truncated)
                                raw_response_text = response_data.text[:500] + "..." if len(response_data.text) > 500 else response_data.text
                                logger.info(f"Raw API response: {raw_response_text}")
                                
                                # 6. Check if request was successful
                                if response_data.status_code != 200:
                                    error_msg = f"API Error {response_data.status_code}: "
                                    try:
                                        error_json = response_data.json()
                                        error_msg += f"{json.dumps(error_json, indent=2)}"
                                        logger.error(f"Detailed API error: {error_msg}")
                                    except Exception:
                                        error_msg += response_data.text
                                        logger.error(f"Error response text: {response_data.text}")
                                    
                                    response_data.raise_for_status()  # This will still raise the exception
                                
                                result = response_data.json()
                                
                                # Add enhanced logging for thinking mode API responses
                                logger.info(f"API response content structure: content array length: {len(result.get('content', []))} items")
                                for i, content_item in enumerate(result.get('content', [])):
                                    if isinstance(content_item, dict):
                                        content_type = content_item.get('type', 'unknown')
                                        logger.info(f"Content item #{i}: type={content_type}")
                                    else:
                                        logger.info(f"Content item #{i}: not a dictionary, type={type(content_item)}")
                                
                                # 7. Create a LLMResponse compatible object, handling different response structures
                                try:
                                    # Print the response structure (keys only) for debugging
                                    if verbose:
                                        logger.debug(f"Response keys: {list(result.keys())}")
                                        if "content" in result:
                                            logger.debug(f"Content keys: {[c.get('type', type(c)) for c in result['content']]}")
                                            if result["content"] and isinstance(result["content"][0], dict):
                                                logger.debug(f"Content[0] keys: {list(result['content'][0].keys())}")
                                    
                                    # Extract content safely, looking for the 'text' block
                                    content_text = ""
                                    found_text_block = False # Flag to track if we found the text block
                                    if "content" in result and isinstance(result["content"], list):
                                        # Find the first block with type 'text'
                                        text_block = next((block for block in result["content"] if block.get("type") == "text"), None)
                                        if text_block and "text" in text_block:
                                            content_text = text_block["text"]
                                            found_text_block = True
                                        elif text_block and "value" in text_block: # Handle potential other key names
                                            content_text = text_block["value"]
                                            found_text_block = True
                                    
                                    # If no text block was found when using thinking mode, ensure content_text is empty
                                    if not found_text_block:
                                        logger.warning("No 'text' block found in API response content list (thinking mode). Setting content to empty.")
                                        content_text = "" # Ensure it's empty, prevent fallbacks below
                                    
                                    # Extract token counts safely
                                    input_tokens = result.get("usage", {}).get("input_tokens", 0)
                                    output_tokens = result.get("usage", {}).get("output_tokens", 0)
                                    
                                    # Create the response object
                                    response = LLMResponse(
                                        content=content_text,
                                        input_tokens=input_tokens,
                                        output_tokens=output_tokens,
                                        model=model_name,
                                        raw_response=result
                                    )
                                except Exception as parse_error:
                                    # Log the error and the raw result to help debug
                                    logger.error(f"Error parsing API response: {parse_error}")
                                    logger.debug(f"Raw API response: {json.dumps(result, indent=2)[:1000]}...")
                                    
                                    # Create a simplified response with whatever we have
                                    fallback_content = str(result) if result else "Error: Failed to parse API response"
                                    response = LLMResponse(
                                        content=fallback_content,
                                        input_tokens=0,
                                        output_tokens=0,
                                        model=model_name,
                                        raw_response=result
                                    )
                                
                                # 8. Log thinking if available and in verbose mode
                                if verbose and "thinking" in result:
                                    thinking_str = str(result["thinking"])
                                    # Truncate if too long for log
                                    if len(thinking_str) > 1000:
                                        thinking_str = thinking_str[:1000] + "... [truncated]"
                                    logger.debug(f"Thinking process: {thinking_str}")
                                
                                return response
                                
                        except Exception as thinking_error:
                            logger.warning(f"Error using direct API call for thinking mode: {thinking_error}. Falling back to standard completion.")
                            
                            # Add more detailed error information
                            import traceback
                            error_trace = traceback.format_exc()
                            logger.debug(f"Thinking error details: {str(thinking_error)}")
                            logger.debug(f"Error traceback:\n{error_trace}")
                            
                            # Fall back to standard completion without caching
                            response = provider_instance.get_completion(prompt)
                            return response
                    else:
                        logger.warning("Thinking mode requested but max_tokens or budget_tokens not found in settings.json. Falling back to standard completion.")
                        # Fall back to standard completion without caching
                        response = provider_instance.get_completion(prompt)
                        return response
                else:
                    # Standard mode with ephemeral caching
                    try:
                        # Check if the prompt contains both current and previous chunk
                        has_prev_chunk = "PREVIOUS CHUNK TEXT (FOR CONTEXT ONLY):" in prompt
                        
                        # Extract system prompt (everything until KNOWN PLACES LIST)
                        system_parts = prompt.split("KNOWN PLACES LIST:")
                        system_prompt = system_parts[0].strip() if system_parts else ""
                        
                        # Extract the KNOWN PLACES LIST and the JSON schema
                        places_and_schema = ""
                        if len(system_parts) > 1:
                            schema_parts = system_parts[1].split("PREVIOUS CHUNK")
                            if "PREVIOUS CHUNK" in system_parts[1]:
                                places_and_schema = schema_parts[0].strip() if schema_parts else ""
                            else:
                                # If no previous chunk, split at CHUNK ID
                                schema_parts = system_parts[1].split("CHUNK ID:")
                                places_and_schema = schema_parts[0].strip() if schema_parts else ""
                        
                        # Extract target chunk text
                        target_chunk_text = ""
                        target_id = None
                        
                        # Look for the new format first
                        target_matches = re.findall(r'TARGET CHUNK (\d+) TEXT:', prompt)
                        if target_matches:
                            target_id = target_matches[0]
                            target_marker = f"TARGET CHUNK {target_id} TEXT:"
                            target_parts = prompt.split(f"{target_marker}\n```")
                            if len(target_parts) > 1:
                                chunk_text_parts = target_parts[1].split("```")
                                target_chunk_text = chunk_text_parts[0].strip() if chunk_text_parts else ""
                        
                        # Fallback to the old format
                        elif "CHUNK ID:" in prompt:
                            target_parts = prompt.split("CHUNK ID:")
                            if len(target_parts) > 1:
                                id_parts = target_parts[1].split("\n")
                                if id_parts:
                                    target_id = id_parts[0].strip()
                                    
                                chunk_parts = target_parts[1].split("CHUNK TEXT:\n```")
                                if len(chunk_parts) > 1:
                                    chunk_text_parts = chunk_parts[1].split("```")
                                    target_chunk_text = chunk_text_parts[0].strip() if chunk_text_parts else ""
                        
                        # Extract previous chunk texts with integrated location info
                        prev_chunks_text = []
                        
                        # Look for context chunks in the new format
                        # Extract chunk IDs from the prompt using regex for flexible matching
                        context_chunk_matches = re.findall(r'CONTEXT CHUNK (\d+) \((.*?)\)', prompt)
                        
                        for chunk_id, location_info in context_chunk_matches:
                            # Find the text for this chunk
                            chunk_marker = f"CONTEXT CHUNK {chunk_id} ({location_info})"
                            if chunk_marker in prompt:
                                parts = prompt.split(f"{chunk_marker}\n```")
                                if len(parts) > 1:
                                    chunk_text_parts = parts[1].split("```")
                                    prev_chunks_text.append((chunk_id, chunk_text_parts[0].strip() if chunk_text_parts else ""))
                        
                        # Fallback for backwards compatibility
                        if not prev_chunks_text and has_prev_chunk:
                            old_markers = [
                                "PREVIOUS CHUNK TEXT (FOR CONTEXT ONLY):\n```",
                                "PREVIOUS CHUNK #1 TEXT (FOR CONTEXT ONLY):\n```"
                            ]
                            
                            for marker in old_markers:
                                if marker in prompt:
                                    prev_parts = prompt.split(marker)
                                    if len(prev_parts) > 1:
                                        prev_chunk_text_parts = prev_parts[1].split("```")
                                        prev_chunks_text.append((1, prev_chunk_text_parts[0].strip() if prev_chunk_text_parts else ""))
                                        break
                        
                        system_messages = [
                            {
                                "type": "text",
                                "text": system_prompt
                            },
                            {
                                "type": "text",
                                "text": f"KNOWN PLACES LIST:{places_and_schema}"
                            }
                        ]
                        
                        # Add context chunks first (with caching)
                        # Sort by chunk ID to ensure chronological order
                        for chunk_id, chunk_text in sorted(prev_chunks_text, key=lambda x: int(x[0])):
                            # We don't have location info here in the direct API call
                            context_header = f"CONTEXT CHUNK {chunk_id}"
                                
                            system_messages.append({
                                "type": "text",
                                "text": f"{context_header}\n```\n{chunk_text}```",
                                "cache_control": {"type": "ephemeral"}  # Cache context chunk
                            })
                        
                        # Add target chunk (with caching)
                        if target_chunk_text:
                            target_header = f"TARGET CHUNK {target_id} TEXT:" if target_id else "TARGET CHUNK TEXT:"
                            system_messages.append({
                                "type": "text",
                                "text": f"{target_header}\n```\n{target_chunk_text}```",
                                "cache_control": {"type": "ephemeral"}  # Cache target chunk
                            })
                        
                        # Make the API call with caching
                        api_response = provider_instance.client.messages.create(
                            model=provider_instance.model,
                            max_tokens=provider_instance.max_tokens,
                            temperature=provider_instance.temperature,
                            system=system_messages,
                            messages=[
                                {"role": "user", "content": "Identify the location for this chunk using the provided information."}
                            ]
                        )
                    except Exception as cache_error:
                        logger.warning(f"Error using ephemeral caching: {cache_error}. Falling back to standard completion.")
                        logger.debug(f"Cache error details: {str(cache_error)}")
                        response = provider_instance.get_completion(prompt)
                        return response
                
                # Create a LLMResponse compatible object from api_response
                response = LLMResponse(
                    content=api_response.content[0].text if api_response.content else "",
                    input_tokens=api_response.usage.input_tokens,
                    output_tokens=api_response.usage.output_tokens,
                    model=provider_instance.model,
                    raw_response=api_response
                )
                
                # Log detailed information if verbose mode is enabled
                if verbose:
                    if thinking_mode:
                        logger.debug(f"Thinking mode used. Token usage: {response.input_tokens} input, {response.output_tokens} output")
                        if hasattr(api_response, 'thinking') and api_response.thinking:
                            thinking_str = str(api_response.thinking)
                            # Truncate if too long for log
                            if len(thinking_str) > 1000:
                                thinking_str = thinking_str[:1000] + "... [truncated]"
                            logger.debug(f"Thinking process: {thinking_str}")
                    else:
                        logger.debug(f"Ephemeral caching used. Token usage: {response.input_tokens} input, {response.output_tokens} output")
        else:
            # For non-Anthropic providers or if cache feature not available
            if thinking_mode and not isinstance(provider_instance, AnthropicProvider):
                logger.warning("Thinking mode is only supported with Anthropic provider. Ignoring --thinking flag.")
            response = provider_instance.get_completion(prompt)
        
        # Try to parse JSON from response content
        try:
            # Always log a sample of the content for debugging
            content = response.content.strip()
            logger.info(f"Response content to parse (first 100 chars): {content[:100]}...")
            
            # Check if content is empty before attempting to parse
            if not content:
                logger.error("LLM response content is empty. Cannot parse JSON.")
                return None
            
            # Find JSON opening/closing braces if there's any text around the JSON
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                logger.debug(f"Extracted JSON string (first 100 chars): {json_str[:100]}...")
                
                try:
                    structured_data = json.loads(json_str)
                    logger.info(f"Successfully parsed JSON response from LLM.")
                    
                    # Always log the successful structured data keys
                    logger.info(f"Structured data keys: {list(structured_data.keys())}")
                    
                    if verbose:
                        logger.debug(f"Parsed structured data: {json.dumps(structured_data, indent=2)}")
                    
                    if not isinstance(structured_data, dict) or not structured_data.get("primary_location"):
                        logger.error(f"Parsed JSON but missing required 'primary_location' field: {json.dumps(structured_data, indent=2)[:200]}...")
                        return None
                    
                    return structured_data
                except json.JSONDecodeError as json_err:
                    logger.error(f"JSON parsing error: {json_err}")
                    logger.error(f"Invalid JSON string (first 100 chars): {json_str[:100]}...")
                    return None
            else:
                logger.error(f"No valid JSON object found in LLM response (length: {len(content)})")
                if '{' in content:
                    logger.error(f"First '{' at position {start_idx}, last '}' at position {end_idx-1}")
                else:
                    logger.error("No JSON braces found in content")
                    
                # Log more context around where JSON should be
                logger.error(f"Response content sample: {content[:200]}...")
                return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Raw response content (first 200 chars): {response.content[:200]}...")
            return None
        except Exception as ex:
            logger.error(f"Unexpected error parsing response: {ex}")
            logger.error(f"Response type: {type(response.content)}, length: {len(response.content)}")
            
            # Print even if the content is None or empty
            if not response.content:
                logger.error("Response content is empty or None")
            else:
                logger.error(f"Response content sample: {str(response.content)[:200]}...")
            return None
    except Exception as e:
        logger.error(f"Error getting completion from {provider_instance.provider_name}: {e}")
        return None

def add_new_place(db: Engine, place_data: Dict[str, Any], places: Dict[int, KnownPlace], zones: Dict[int, Zone]) -> Optional[KnownPlace]:
    """Adds a new place to the database and the places dict."""
    place_name = place_data.get("name")
    place_type = place_data.get("type")
    zone_id = place_data.get("zone")
    place_summary = place_data.get("summary", "")  # Optional summary
    
    if not place_name or not place_type or not zone_id:
        logger.warning(f"Missing required data for new place: {place_data}")
        return None
    
    # Validate place type
    valid_types = ["fixed_location", "vehicle", "other"]
    if place_type not in valid_types:
        logger.warning(f"Invalid place type '{place_type}'. Using 'fixed_location' as fallback.")
        place_type = "fixed_location"
    
    # Zone validation is now handled before calling this function
    # Just a double check to be safe
    if zone_id not in zones:
        logger.warning(f"Invalid zone ID '{zone_id}' passed to add_new_place. This should have been caught earlier.")
        return None
    
    # Check if place name already exists
    for place_id, place in places.items():
        if place.name.lower() == place_name.lower():
            logger.warning(f"Place '{place_name}' already exists with ID {place_id}. Returning existing record.")
            return place
    
    logger.info(f"Adding new place to database: Name='{place_name}', Type='{place_type}', Zone={zone_id}")
    try:
        with db.connect() as conn:
            trans = conn.begin()
            try:
                # Get all existing place IDs
                all_ids_query = text(f"SELECT id FROM {PLACES_TABLE} ORDER BY id")
                existing_ids = [row[0] for row in conn.execute(all_ids_query).fetchall()]
                
                # Find the lowest unoccupied ID
                next_id = 1  # Start from ID 1
                if existing_ids:
                    # Find gaps in the sequence
                    for i in range(len(existing_ids)):
                        if i+1 < len(existing_ids) and existing_ids[i] + 1 < existing_ids[i+1]:
                            # Found a gap
                            next_id = existing_ids[i] + 1
                            break
                    else:
                        # No gaps found, use next number after the highest
                        next_id = max(existing_ids) + 1
                
                logger.info(f"Attempting to insert new place with ID {next_id}")
                
                # Attempt to insert with retry logic
                max_attempts = 5
                attempt = 1
                result = None
                
                while attempt <= max_attempts:
                    try:
                        # Insert into places table with explicit ID and summary if available
                        insert_query = text(f"""
                            INSERT INTO {PLACES_TABLE} (id, name, type, zone, summary)
                            VALUES (:id, :name, :type, :zone, :summary)
                            RETURNING id, name, type, zone, summary
                        """)
                        result = conn.execute(insert_query, {
                            "id": next_id,
                            "name": place_name, 
                            "type": place_type,
                            "zone": zone_id,
                            "summary": place_summary if place_summary else None
                        }).fetchone()
                        
                        # If we get here, the insert succeeded
                        break
                    except Exception as insert_error:
                        # Check if it's a unique violation error
                        if "UniqueViolation" in str(insert_error) and "places_pkey" in str(insert_error):
                            # ID is already used, try the next one
                            next_id += 1
                            logger.warning(f"ID {next_id-1} already in use, trying ID {next_id} (attempt {attempt}/{max_attempts})")
                            attempt += 1
                        else:
                            # Different error, re-raise it
                            raise
                
                if attempt > max_attempts:
                    logger.error(f"Failed to find an available ID after {max_attempts} attempts")
                    raise Exception(f"Failed to find an available ID after {max_attempts} attempts")
                
                trans.commit()

                if result:
                    new_place = KnownPlace(
                        id=result[0], 
                        name=result[1], 
                        type=result[2], 
                        zone=result[3],
                        summary=result[4] if len(result) > 4 else None
                    )
                    logger.info(f"Successfully added place '{new_place.name}' with ID {new_place.id}")
                    # Update the working dictionary
                    places[new_place.id] = new_place
                    return new_place
                else:
                    logger.error(f"Failed to add place '{place_name}', INSERT returned no result.")
                    return None
            except Exception as inner_e:
                logger.error(f"Error during new place insertion transaction: {inner_e}")
                # Log the full error details for better debugging
                import traceback
                logger.debug(f"Transaction error details: {traceback.format_exc()}")
                trans.rollback()
                return None
    except Exception as e:
        logger.error(f"Database connection error while adding new place '{place_name}': {str(e)}")
        return None

def update_chunk_metadata(db: Engine, chunk_id: int, place_id: int, dry_run: bool = False) -> bool:
    """Updates the chunk_metadata.place field for the given chunk."""
    logger.info(f"Updating chunk {chunk_id} metadata with place ID: {place_id}")

    if dry_run:
        logger.info(f"[DRY RUN] Would update chunk {chunk_id} metadata place to: {place_id}")
        return True

    try:
        with db.connect() as conn:
            trans = conn.begin()
            try:
                # Check if metadata record exists
                check_query = text(f"SELECT 1 FROM {CHUNK_METADATA_TABLE} WHERE chunk_id = :chunk_id")
                exists = conn.execute(check_query, {"chunk_id": chunk_id}).scalar_one_or_none()

                if exists:
                    update_query = text(f"""
                        UPDATE {CHUNK_METADATA_TABLE}
                        SET place = :place
                        WHERE chunk_id = :chunk_id
                    """)
                    conn.execute(update_query, {"place": place_id, "chunk_id": chunk_id})
                else:
                    # Insert a new record if it doesn't exist
                    logger.warning(f"No existing metadata found for chunk {chunk_id}. Inserting new record. Other fields might be default/null.")
                    insert_query = text(f"""
                        INSERT INTO {CHUNK_METADATA_TABLE} (chunk_id, place)
                        VALUES (:chunk_id, :place)
                    """)
                    conn.execute(insert_query, {"chunk_id": chunk_id, "place": place_id})

                trans.commit()
                logger.info(f"Successfully updated place metadata for chunk {chunk_id}.")
                return True
            except Exception as inner_e:
                logger.error(f"Error during chunk metadata update transaction for chunk {chunk_id}: {inner_e}")
                trans.rollback()
                return False
    except Exception as e:
        logger.error(f"Database connection error while updating metadata for chunk {chunk_id}: {str(e)}")
        return False

def get_previous_chunks_info(db: Engine, current_chunk_id: int, num_chunks: int = 2) -> List[Tuple[NarrativeChunk, Optional[KnownPlace]]]:
    """Get multiple previous chunks and their associated place information.
    
    Args:
        db: Database engine
        current_chunk_id: The current chunk ID
        num_chunks: Number of previous chunks to fetch (default: 2)
        
    Returns:
        List of (chunk, place) tuples, ordered from most recent to oldest
    """
    chunks_info = []
    try:
        with db.connect() as conn:
            # Get the previous chunks (assuming chunks are numbered sequentially)
            prev_chunks_query = text(f"""
                SELECT nc.id, nc.raw_text, cm.slug, cm.place
                FROM {NARRATIVE_CHUNKS_TABLE} nc
                LEFT JOIN {CHUNK_METADATA_TABLE} cm ON nc.id = cm.chunk_id
                WHERE nc.id < :current_id
                ORDER BY nc.id DESC
                LIMIT :num_chunks
            """)
            prev_chunk_rows = conn.execute(prev_chunks_query, {"current_id": current_chunk_id, "num_chunks": num_chunks}).fetchall()
            
            if not prev_chunk_rows:
                logger.info(f"No previous chunks found for chunk {current_chunk_id}")
                return []
                
            for prev_chunk_row in prev_chunk_rows:
                prev_chunk = NarrativeChunk(id=prev_chunk_row[0], raw_text=prev_chunk_row[1], slug=prev_chunk_row[2])
                prev_place_id = prev_chunk_row[3]
                
                # Get the place information if available
                prev_place = None
                if prev_place_id:
                    place_query = text(f"""
                        SELECT id, name, type, zone, summary
                        FROM {PLACES_TABLE}
                        WHERE id = :place_id
                    """)
                    place_row = conn.execute(place_query, {"place_id": prev_place_id}).fetchone()
                    if place_row:
                        prev_place = KnownPlace(
                            id=place_row[0],
                            name=place_row[1],
                            type=place_row[2],
                            zone=place_row[3],
                            summary=place_row[4] if len(place_row) > 4 else None
                        )
                
                chunks_info.append((prev_chunk, prev_place))
            
            return chunks_info
    except Exception as e:
        logger.error(f"Error getting previous chunks info for chunk {current_chunk_id}: {e}")
        return None # Return None specifically on DB error

def get_previous_chunk_info(db: Engine, current_chunk_id: int) -> Optional[Tuple[NarrativeChunk, Optional[KnownPlace]]]:
    """Get the previous chunk and its associated place information (for backwards compatibility)."""
    chunks_info = get_previous_chunks_info(db, current_chunk_id, 1)
    return chunks_info[0] if chunks_info else None

def process_chunk(
    db: Engine,
    chunk: NarrativeChunk,
    places: Dict[int, KnownPlace],
    zones: Dict[int, Zone],
    provider_instance: LLMProvider,
    args: argparse.Namespace,
    dry_run: bool = False,
    verbose: bool = False,
    auto: bool = False
) -> int:
    """Processes a single narrative chunk to extract location information.
    
    Note on auto flag:
        - The auto flag ONLY affects confirmations between batches
        - New place submissions will ALWAYS prompt for user confirmation regardless of auto mode
        - This ensures human validation for all new location data
    
    Returns:
        int: Status code indicating result of processing:
            1: Success - processing completed successfully
            0: User requested stop
           -1: Error - processing failed due to LLM API error or other issue
    """
    slug_display = f" ({chunk.slug})" if chunk.slug else ""
    logger.info(f"--- Processing Chunk ID: {chunk.id}{slug_display} ---")
    user_requested_stop = False
    reviews_were_presented = False # Track if any review prompts happened

    # Get previous chunk information for context
    prev_chunks_info = get_previous_chunks_info(db, chunk.id)
    if prev_chunks_info is None:
        # Error occurred fetching previous chunks, stop the batch
        logger.error(f"Could not retrieve previous chunk info for chunk {chunk.id} due to database error. Stopping batch.")
        return -1 # Indicate critical error to stop the batch
        
    # Determine the most recent previous place for continuity checks
    prev_place = None
    if prev_chunks_info:
        # Find the most recent previous chunk that has a place assigned
        for _, place in prev_chunks_info:
            if place:
                prev_place = place
                logger.info(f"Most recent previous location found: '{prev_place.name}' (ID: {prev_place.id}) from chunk {prev_chunks_info[0][0].id if prev_chunks_info else 'N/A'}")
                break
        else:
            logger.info(f"No previous chunks found with a set location.")

    # 1. Format known places and zones for the prompt
    # Get hidden locations from settings
    hidden_locations = SETTINGS.get("API Settings", {}).get("map_builder", {}).get("hidden", [])
    # Convert all to integers to ensure consistent comparison
    hidden_locations_int = {int(loc_id) for loc_id in hidden_locations}
    logger.debug(f"Hidden locations from settings: {hidden_locations_int}")
    
    # Filter places before formatting
    visible_places = {place_id: place for place_id, place in places.items() 
                      if place_id not in hidden_locations_int}
                      
    known_places_formatted = format_known_places_for_prompt(visible_places, zones)

    # 2. Build the prompt with previous chunk context if available
    prompt = build_location_extraction_prompt(
        chunk, 
        known_places_formatted, 
        prev_chunks_info=prev_chunks_info
    )
    if verbose:
        logger.debug(f"Prompt for chunk {chunk.id}:\n{prompt[:500]}...\n...\n{prompt[-500:]}")

    # 3. Call LLM for structured response
    llm_output = None
    try:
        # Use thinking mode if enabled in args
        thinking_mode = args.thinking if hasattr(args, 'thinking') else False
        llm_output = get_llm_structured_response(prompt, provider_instance, chunk.id, verbose, thinking_mode)
    except Exception as e:
        logger.error(f"Unhandled exception during LLM call for chunk {chunk.id}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        llm_output = None # Ensure llm_output is None to trigger manual correction

    # === Manual Correction Loop ===
    if not llm_output or not isinstance(llm_output, dict):
        logger.error(f"Failed to get valid structured response from LLM for chunk {chunk.id}.")
        reviews_were_presented = True # This interaction counts as a review
        
        if dry_run:
            logger.warning("[DRY RUN] LLM failed. Would prompt for manual correction.")
            return -1 # Indicate error, stop batch in dry run if LLM fails
            
        while True: # Loop until valid input or user quits
            try:
                print(f"\n--- LLM Error: Manual Correction Needed for Chunk {chunk.id} --- ")
                print("The AI failed to provide a valid location response.")
                print("\nOptions:")
                print("(1) Link to EXISTING place")
                print("(2) Add NEW place")
                print("(3) Skip this chunk (leave location unset)")
                print("(q) Quit processing")
                
                action_choice = input("Choose option [1-3, q]: ").lower()
                
                if action_choice == 'q':
                    logger.warning(f"User chose to quit during manual correction for chunk {chunk.id}.")
                    return 0 # Return 0 to indicate user requested stop
                    
                elif action_choice == '1':
                    # Link to EXISTING place
                    if not places:
                         logger.warning("No known places to link to.")
                         print("No known places available.")
                         continue # Re-prompt
                    else:
                         visible_places_for_manual = {pid: p for pid, p in places.items() if pid not in hidden_locations_int}
                         sorted_places_manual = sorted(visible_places_for_manual.values(), key=lambda p: p.id)
                         if not sorted_places_manual:
                             logger.warning("All places are hidden! Showing all places instead.")
                             sorted_places_manual = sorted(places.values(), key=lambda p: p.id)
                             
                         print("\nLink to which existing place?")
                         for place in sorted_places_manual:
                             zone_name = zones.get(place.zone).name if place.zone in zones else "Unknown zone"
                             print(f"ID {place.id}: {place.name} (Type: {place.type}, Zone: {zone_name})")

                         link_choice_id = -1
                         valid_link = False
                         while True:
                             try:
                                 link_choice_str = input(f"Enter place ID to link to (or 'c' to cancel): ")
                                 if link_choice_str.lower() == 'c':
                                     break # Go back to main manual options
                                 link_choice_id = int(link_choice_str)
                                 # Check against all places, not just visible, in case user knows hidden ID
                                 if link_choice_id in places: 
                                     valid_link = True
                                     break
                                 else:
                                     print("Invalid place ID.")
                             except ValueError:
                                 print("Invalid input. Please enter a number or 'c'.")
                                 
                         if valid_link:
                             selected_place = places[link_choice_id]
                             logger.info(f"User manually linked chunk {chunk.id} to existing place '{selected_place.name}' (ID: {selected_place.id}).")
                             place_id = selected_place.id
                             # We have a valid place_id, exit manual correction loop
                             primary_location = {} # Reset AI's primary_location
                             reasoning = "Manually linked by user after LLM error." # Set reasoning
                             break 
                         else:
                             continue # Cancelled linking, re-prompt main options
                             
                elif action_choice == '2':
                    # Add NEW place manually
                    print("\nEnter details for the new place:")
                    new_name = input("Place name: ")
                    if not new_name:
                        print("Place name cannot be empty.")
                        continue # Re-prompt
                    
                    print(f"Place type options: fixed_location, vehicle, other")
                    new_type = input("Place type [fixed_location]: ") or "fixed_location"
                    if new_type not in ["fixed_location", "vehicle", "other"]:
                        print(f"Invalid type '{new_type}', using 'fixed_location'.")
                        new_type = "fixed_location"
                        
                    print("\nAvailable zones:")
                    for z_id, zone in sorted(zones.items()):
                        print(f"[{z_id}] {zone.name}")
                    
                    new_zone_id = -1
                    while True:
                        try:
                            zone_input_str = input(f"Zone ID: ")
                            new_zone_id = int(zone_input_str)
                            if new_zone_id in zones:
                                break
                            else:
                                print("Invalid zone ID.")
                        except ValueError:
                            print("Invalid input. Please enter a number.")
                            
                    new_summary = input("Brief summary/description (optional): ")
                    
                    # Confirm before adding
                    summary_display = f", Summary: '{new_summary}'" if new_summary else ""
                    print(f"\nAdd this place: '{new_name}' (Type: {new_type}, Zone: {zones[new_zone_id].name}{summary_display})?" )
                    confirm_add = input("Confirm [1=Yes, 0=No]: ")
                    
                    if confirm_add == '1':
                        manual_place_data = {
                            "name": new_name,
                            "type": new_type,
                            "zone": new_zone_id,
                            "summary": new_summary if new_summary else ""
                        }
                        new_place_obj = add_new_place(db, manual_place_data, places, zones)
                        if new_place_obj:
                            place_id = new_place_obj.id
                            logger.info(f"User manually added new place '{new_place_obj.name}' (ID: {place_id}) for chunk {chunk.id}.")
                            # We have a valid place_id, exit manual correction loop
                            primary_location = {} # Reset AI's primary_location
                            reasoning = "Manually added by user after LLM error." # Set reasoning
                            break
                        else:
                            logger.error(f"Failed to add manually entered place '{new_name}'.")
                            print("Error adding place to database. Please try again or choose another option.")
                            continue # Re-prompt main options
                    else:
                        print("Place addition cancelled.")
                        continue # Re-prompt main options
                        
                elif action_choice == '3':
                    logger.warning(f"User chose to skip chunk {chunk.id} due to LLM error.")
                    place_id = None # Ensure no place is set
                    primary_location = {} # Reset AI's primary_location
                    reasoning = "Skipped by user after LLM error." # Set reasoning
                    break # Exit manual correction loop
                
                else:
                    print("Invalid option. Please choose 1, 2, 3, or q.")
            
            except EOFError:
                logger.warning("EOF detected during manual correction. Stopping processing.")
                return 0 # Return 0 to indicate user requested stop
                
    else:
        # --- LLM Response was valid, proceed as normal ---
        primary_location = llm_output.get("primary_location", {})
        reasoning = llm_output.get("reasoning", "No reasoning provided.")
        status = primary_location.get("status")
        place_id = None
        place_name = None
        confidence = primary_location.get("confidence", 0.0) # Get confidence early

        print(f"\n[AI Reasoning] {reasoning}")
        logger.info(f"AI reasoning: {reasoning}")

        # Determine place_id and place_name based on status
        if status == "known":
            place_id = primary_location.get("id")
            # --- START EDIT ---
            # Validate the place_id against the known places
            if place_id not in places:
                logger.error(f"LLM provided invalid known place ID {place_id}. Triggering manual correction.")
                llm_output = None # Force manual correction
                place_id = None # Ensure place_id is None for the manual loop check below
            else:
                # Place ID is valid, get the name
                place_name = places[place_id].name
                logger.info(f"Identified known place '{place_name}' (ID: {place_id}) with confidence {confidence:.2f}")
            # --- END EDIT ---
        elif status == "new":
            place_name = primary_location.get("name", "Unknown")
            logger.info(f"LLM proposed new place: '{place_name}'")
            # place_id remains None until confirmed/added
        else:
            logger.error(f"Invalid status '{status}' in LLM output. Triggering manual correction.")
            llm_output = None # Force manual correction
            place_id = None # Ensure place_id is None

        # === Review Logic (only runs if llm_output is still valid) ===
        if llm_output:
            # *** EXCEPTION: Skip review ONLY if location is known and unchanged ***
            if status == "known" and prev_place and place_id == prev_place.id:
                logger.info("Location unchanged from previous chunk. Skipping review.")
                needs_review = False
            else:
                needs_review = True

            if needs_review and not dry_run:
                reviews_were_presented = True
                try:
                    if status == "known": # Review for known (changed or first location)
                        print(f"\nREVIEW LOCATION for chunk {chunk.id}:")
                        if prev_place: print(f"Previous location: '{prev_place.name}' (ID: {prev_place.id})")
                        else: print("Previous location: None")
                        print(f"Suggested location: '{place_name}' (ID: {place_id})")
                        print(f"Confidence: {confidence:.2f}")
                        print(f"Reasoning: {reasoning}")

                        context_length = 200
                        context = chunk.raw_text[:context_length] + "..." if len(chunk.raw_text) > context_length else chunk.raw_text
                        print(f"\nContext: {context}")

                        print("\nOptions:")
                        print("(1) Accept suggested location")
                        print("(2) Choose a different EXISTING location")
                        print("(3) Add a NEW location")
                        if prev_place: print("(4) Keep previous location")
                        print("(s) Skip this chunk")
                        print("(q) Quit processing")

                        valid_choices = ["1", "2", "3", "s", "q"]
                        if prev_place: valid_choices.append("4")
                        prompt_str = f"Choose option [{ ', '.join(valid_choices) }]: "
                        action_choice = ""
                        while action_choice not in valid_choices: action_choice = input(prompt_str).lower()

                        if action_choice == "1":
                            logger.info(f"User accepted suggested location '{place_name}' (ID: {place_id})")
                        elif action_choice == "2":
                            # Code to choose different existing (simplified, combines logic from previous state)
                            if not places:
                                logger.warning("No known places to choose from."); print("No known places available.")
                                place_id = None
                            else:
                                visible_places_review = {pid: p for pid, p in places.items() if pid not in hidden_locations_int}
                                sorted_places_review = sorted(visible_places_review.values(), key=lambda p: p.id)
                                if not sorted_places_review: sorted_places_review = sorted(places.values(), key=lambda p: p.id) # Show all if all hidden

                                print("\nChoose a different location:")
                                
                                # Group places by zone
                                places_by_zone = {}
                                for place in sorted_places_review:
                                    zone_id = place.zone
                                    if zone_id not in places_by_zone:
                                        places_by_zone[zone_id] = []
                                    places_by_zone[zone_id].append(place)
                                
                                # Display places organized by zone
                                for zone_id, zone_places in sorted(places_by_zone.items()):
                                    # Get zone name
                                    zone_name = zones[zone_id].name if zone_id in zones else f"Unknown Zone (ID: {zone_id})"
                                    
                                    # Zone header
                                    print(f"Zone {zone_id} {zone_name}/")
                                    
                                    # Add places in this zone
                                    for place in sorted(zone_places, key=lambda p: p.id):
                                        print(f"├─── {place.id}: {place.name} ({place.type})")

                                link_choice_id = -1
                                valid_link = False
                                while True:
                                    try:
                                        link_choice_str = input("Enter place ID to use (or 'c' to cancel): ")
                                        if link_choice_str.lower() == 'c': break
                                        link_choice_id = int(link_choice_str)
                                        if link_choice_id in places: valid_link = True; break
                                        else: print("Invalid place ID.")
                                    except ValueError: print("Invalid input.")

                                if valid_link:
                                    selected_place = places[link_choice_id]
                                    logger.info(f"User selected alternative location '{selected_place.name}' (ID: {selected_place.id}).")
                                    place_id = selected_place.id
                                else:
                                    logger.warning("Location selection cancelled by user. Skipping chunk.")
                                    place_id = None
                        elif action_choice == "3":
                            # Add NEW location manually
                            print("\nEnter details for the new place:")
                            new_name = input("Place name: ")
                            if not new_name:
                                print("Place name cannot be empty.")
                                logger.warning("Empty place name entered. Skipping chunk.")
                                place_id = None
                            else:
                                print(f"Place type options: fixed_location, vehicle, other")
                                new_type = input("Place type [fixed_location]: ") or "fixed_location"
                                if new_type not in ["fixed_location", "vehicle", "other"]:
                                    print(f"Invalid type '{new_type}', using 'fixed_location'.")
                                    new_type = "fixed_location"
                                    
                                print("\nAvailable zones:")
                                for z_id, zone in sorted(zones.items()):
                                    print(f"[{z_id}] {zone.name}")
                                
                                new_zone_id = -1
                                while True:
                                    try:
                                        zone_input_str = input(f"Zone ID: ")
                                        new_zone_id = int(zone_input_str)
                                        if new_zone_id in zones:
                                            break
                                        else:
                                            print("Invalid zone ID.")
                                    except ValueError:
                                        print("Invalid input. Please enter a number.")
                                        
                                new_summary = input("Brief summary/description (optional): ")
                                
                                # Confirm before adding
                                summary_display = f", Summary: '{new_summary}'" if new_summary else ""
                                print(f"\nAdd this place: '{new_name}' (Type: {new_type}, Zone: {zones[new_zone_id].name}{summary_display})?" )
                                confirm_add = input("Confirm [1=Yes, 0=No]: ")
                                
                                if confirm_add == '1':
                                    manual_place_data = {
                                        "name": new_name,
                                        "type": new_type,
                                        "zone": new_zone_id,
                                        "summary": new_summary if new_summary else ""
                                    }
                                    new_place_obj = add_new_place(db, manual_place_data, places, zones)
                                    if new_place_obj:
                                        place_id = new_place_obj.id
                                        logger.info(f"User added new place '{new_place_obj.name}' (ID: {place_id}) for chunk {chunk.id}.")
                                    else:
                                        logger.error(f"Failed to add manually entered place '{new_name}'.")
                                        print("Error adding place to database. Skipping chunk.")
                                        place_id = None
                                else:
                                    print("Place addition cancelled.")
                                    place_id = None
                        elif action_choice == "4" and prev_place:
                            logger.info(f"User chose to keep previous location '{prev_place.name}' (ID: {prev_place.id})")
                            place_id = prev_place.id
                        elif action_choice == "s":
                             logger.warning(f"User chose to skip chunk {chunk.id}.")
                             place_id = None
                        elif action_choice == "q":
                             logger.warning(f"User chose to quit during review for chunk {chunk.id}.")
                             return 0 # User requested stop

                    elif status == "new": # Review for new place
                        # Simplified New Place Review (integrates previous code)
                        place_name_new = primary_location.get("name", "Unknown")
                        place_type_new = primary_location.get("type", "fixed_location")
                        zone_id_new = primary_location.get("zone")
                        confidence_new = primary_location.get("confidence", 0.0)
                        zone_name_new = zones.get(zone_id_new).name if zone_id_new in zones else f"Unknown (ID: {zone_id_new})"

                        # Find context
                        context_new = "Context not found" # Default
                        search_name_new = place_name_new.lower()
                        chunk_text_new = chunk.raw_text.lower()
                        if search_name_new in chunk_text_new:
                            name_pos = chunk_text_new.find(search_name_new)
                            start_pos = max(0, name_pos - 150)
                            end_pos = min(len(chunk_text_new), name_pos + len(search_name_new) + 150)
                            if start_pos > 0:
                                while start_pos > 0 and chunk_text_new[start_pos] != ' ' and chunk_text_new[start_pos] != '\n': start_pos -= 1
                            if end_pos < len(chunk_text_new):
                                while end_pos < len(chunk_text_new) and chunk_text_new[end_pos] != ' ' and chunk_text_new[end_pos] != '\n': end_pos += 1
                            context_new = "..." + chunk.raw_text[start_pos:end_pos].strip() + "..."
                        else: # Try heading
                            heading_marker = "📍"
                            if heading_marker in chunk.raw_text:
                                heading_pos = chunk.raw_text.find(heading_marker)
                                end_line = chunk.raw_text.find("\n", heading_pos)
                                if end_line > heading_pos: context_new = chunk.raw_text[heading_pos:end_line].strip()

                        print(f"\nNEW PLACE SUGGESTED for chunk {chunk.id}:")
                        print(f"Name: '{place_name_new}', Type: {place_type_new}, Zone: {zone_name_new}")
                        print(f"Confidence: {confidence_new:.2f}")
                        print(f"Reasoning: {reasoning}")
                        print(f"Context: {context_new}")

                        print("\nOptions:")
                        print("(1) Add this new place")
                        print("(2) Edit before adding")
                        print("(3) Link to EXISTING place instead")
                        print("(4) Discard suggestion (skip chunk)")
                        print("(q) Quit processing")

                        action_choice_new = ""
                        while action_choice_new not in ["1", "2", "3", "4", "q"]: action_choice_new = input("Choose option [1-4, q]: ").lower()

                        if action_choice_new == "1": # Add new place
                             if zone_id_new not in zones: # Zone Validation
                                print(f"\nWARNING: Invalid zone ID '{zone_id_new}'. This zone doesn't exist.")
                                print("\nAvailable zones:")
                                for z_id, zone in sorted(zones.items()): print(f"[{z_id}] {zone.name}")
                                zone_input_str = input("Enter valid zone ID: ")
                                try:
                                    zone_input_new = int(zone_input_str)
                                    if zone_input_new in zones: primary_location["zone"] = zone_input_new
                                    else: logger.error(f"Invalid zone ID {zone_input_new}. Skipping add."); place_id = None
                                except ValueError: logger.error("Invalid zone ID format. Skipping add."); place_id = None
                             # Add if zone valid
                             if "zone" in primary_location and primary_location["zone"] in zones:
                                new_place_obj = add_new_place(db, primary_location, places, zones)
                                if new_place_obj: place_id = new_place_obj.id
                                else: return -1 # Critical error
                        elif action_choice_new == "2": # Edit before adding
                            # Edit Logic (simplified from previous state)
                            print("\nEditing place info...")
                            edit_name = input(f"Place name [{place_name_new}]: ") or place_name_new
                            edit_type = input(f"Place type [{place_type_new}]: ") or place_type_new
                            if edit_type not in ["fixed_location", "vehicle", "other"]: edit_type = place_type_new
                            print("\nAvailable zones:")
                            for z_id, zone in sorted(zones.items()): print(f"[{z_id}] {zone.name}")
                            edit_zone_id = -1
                            while True:
                                try:
                                    edit_zone_str = input(f"Zone ID [{zone_id_new}]: ") or str(zone_id_new)
                                    edit_zone_id = int(edit_zone_str)
                                    if edit_zone_id in zones: break
                                    else: print("Invalid zone ID.")
                                except ValueError: print("Invalid input.")
                            edit_summary = input("Brief summary/description (optional): ")
                            summary_display = f", Summary: '{edit_summary}'" if edit_summary else ""
                            print(f"\nAdd edited place: '{edit_name}' (Type: {edit_type}, Zone: {zones[edit_zone_id].name}{summary_display})?")
                            if input("Confirm [1=Yes, 0=No]: ") == "1":
                                edited_place_data = {"name": edit_name, "type": edit_type, "zone": edit_zone_id, "summary": edit_summary}
                                new_place_obj = add_new_place(db, edited_place_data, places, zones)
                                if new_place_obj: place_id = new_place_obj.id
                                else: return -1 # Critical error
                            else: place_id = None # Cancelled edit
                        elif action_choice_new == "3": # Link to existing
                            # Link Logic (simplified from previous state)
                            if not places: print("No known places to link to."); place_id = None
                            else:
                                visible_places_link = {pid: p for pid, p in places.items() if pid not in hidden_locations_int}
                                sorted_places_link = sorted(visible_places_link.values(), key=lambda p: p.id)
                                if not sorted_places_link: sorted_places_link = sorted(places.values(), key=lambda p: p.id)
                                print("\nLink to which existing place?")
                                
                                # Group places by zone
                                places_by_zone = {}
                                for place in sorted_places_link:
                                    zone_id = place.zone
                                    if zone_id not in places_by_zone:
                                        places_by_zone[zone_id] = []
                                    places_by_zone[zone_id].append(place)
                                
                                # Display places organized by zone
                                for zone_id, zone_places in sorted(places_by_zone.items()):
                                    # Get zone name
                                    zone_name = zones[zone_id].name if zone_id in zones else f"Unknown Zone (ID: {zone_id})"
                                    
                                    # Zone header
                                    print(f"Zone {zone_id} {zone_name}/")
                                    
                                    # Add places in this zone
                                    for place in sorted(zone_places, key=lambda p: p.id):
                                        print(f"├─── {place.id}: {place.name} ({place.type})")
                                link_id_new = -1; valid_link_new = False
                                while True:
                                    try:
                                        link_str_new = input("Enter place ID to link to (or 'c' to cancel): ")
                                        if link_str_new.lower() == 'c': break
                                        link_id_new = int(link_str_new)
                                        if link_id_new in places: valid_link_new = True; break
                                        else: print("Invalid ID.")
                                    except ValueError: print("Invalid input.")
                                if valid_link_new: place_id = link_id_new
                                else: place_id = None # Cancelled
                        elif action_choice_new == "4": # Discard
                             logger.info(f"User discarded new place suggestion '{place_name_new}'.")
                             place_id = None
                        elif action_choice_new == "q": # Quit
                             logger.warning(f"User chose to quit during new place review for chunk {chunk.id}.")
                             return 0 # User requested stop

                except EOFError:
                    logger.warning("EOF detected during review. Stopping processing.")
                    return 0 # User requested stop

    # --- End of Review Logic / Manual Correction ---

    # 6. Update chunk metadata if we have a valid place ID (determined either by LLM+Review or Manual Correction)
    if place_id is not None:
        update_success = update_chunk_metadata(db, chunk.id, place_id, dry_run)
        if not update_success:
            logger.error(f"Failed to update metadata for chunk {chunk.id}.")
            # Don't stop the whole batch for a single failed update, just log it.
            # If it was a critical DB error, it should have been caught earlier.
    else:
        logger.warning(f"No valid place ID determined or selected for chunk {chunk.id}. Skipping metadata update.")

    # 7. Ask user whether to continue AFTER reviews, if any reviews happened (and not dry_run and not auto)
    if reviews_were_presented and not auto and not dry_run: # Check if any reviews actually happened
        try:
            print(f"\nReviews complete for chunk {chunk.id}.")
            print("(1) End Session")
            print("(2) Continue Session")
            session_choice = ""
            while session_choice not in ["1", "2"]:
                session_choice = input("Choose option [1-2]: ")

            if session_choice == "1":
                logger.info("User chose to end the session.")
                user_requested_stop = True
        except EOFError:
            logger.info("EOF detected during post-review prompt, stopping processing.")
            user_requested_stop = True

    return 0 if user_requested_stop else 1 # 1 = Success/Continue, 0 = Stop, -1 = Error handled earlier

def main():
    """
    Main execution function.
    
    This function implements the core logic flow of the map_builder script:
    1. Parse arguments and validate environment
    2. Connect to the database and check schema
    3. Load reference data (places and zones)
    4. Process chunks in batches using the LLM
    5. Track success and error counts accurately
    
    The error handling has been improved to correctly differentiate between:
    - Successful processing (success_count)
    - User-requested stops (counted in success_count but stopping further processing)
    - Processing errors (error_count) including LLM API failures
    """
    args = parse_arguments()

    # --- Test Mode ---
    if args.test:
        logger.info("--- Running in Test Mode ---")
        db_engine_test = None
        try:
            logger.info("Testing database connection...")
            db_url_test = args.db_url or get_db_connection_string()
            db_engine_test = get_db_connection(db_url_test)
            logger.info("Database connection successful.")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return 1 # Exit indicating failure
        
        try:
            logger.info("Loading known places and zones for prompt context...")
            known_places_test = load_known_places(db_engine_test)
            zones_test = load_zones(db_engine_test)
            known_places_formatted_test = format_known_places_for_prompt(known_places_test, zones_test)
        except Exception as e:
            logger.error(f"Failed to load places/zones: {e}")
            return 1

        try:
            # Determine which chunk to use for testing
            if args.start:
                logger.info(f"Using specific chunk ID {args.start} for test prompt as specified by --start")
                # Get a specific chunk based on start parameter
                test_chunks = get_chunks_to_process(db_engine_test, args.start, args.start, overwrite=True)
                if not test_chunks:
                    logger.error(f"Could not find chunk with ID {args.start}. Please check the ID and try again.")
                    return 1
            else:
                logger.info("Fetching first processable chunk...")
                # Get the first chunk that would be processed by --all
                test_chunks = get_chunks_to_process(db_engine_test, overwrite=args.overwrite) 
                if not test_chunks:
                    logger.info("No processable chunks found to generate test prompt.")
                    return 0 # Exit normally, nothing to test prompt with
            
            test_chunk = test_chunks[0]
            logger.info(f"Using chunk {test_chunk.id} for test prompt.")
            
            # Get previous chunk info for context
            prev_chunk_info = get_previous_chunk_info(db_engine_test, test_chunk.id)
            prev_chunk = None
            prev_place = None
            
            if prev_chunk_info:
                prev_chunk, prev_place = prev_chunk_info
                if prev_place:
                    logger.info(f"Previous chunk {prev_chunk.id} had location: '{prev_place.name}' (ID: {prev_place.id})")
                else:
                    logger.info(f"Previous chunk {prev_chunk.id} had no location set")
            else:
                logger.info(f"No previous chunk found for chunk {test_chunk.id}")

            logger.info("Building prompt with previous chunk context...")
            test_prompt = build_location_extraction_prompt(
                test_chunk, 
                known_places_formatted_test,
                prev_chunks_info=get_previous_chunks_info(db_engine_test, test_chunk.id)
            )

            print("\n" + "="*20 + f" TEST PROMPT FOR CHUNK {test_chunk.id} " + "="*20)
            print(test_prompt)
            print("="* (40 + len(f" TEST PROMPT FOR CHUNK {test_chunk.id} ")) + "\n")
            logger.info("Test mode finished. Exiting.")
            return 0 # Exit successfully after printing prompt
        except Exception as e:
            logger.error(f"Error during test prompt generation: {e}")
            return 1
        
    # --- Normal Processing Mode ---
    try:
        validate_llm_requirements(args.provider)
    except (ImportError, ValueError) as e:
        logger.error(f"Requirement validation failed: {e}")
        return 1

    # Database Connection
    db_engine = None
    try:
        db_url = args.db_url or get_db_connection_string()
        db_engine = get_db_connection(db_url)
    except Exception as e:
        logger.error(f"Failed to establish database connection: {e}")
        return 1

    # Check database schema
    try:
        if not check_database_schema(db_engine):
            logger.error("Database schema validation failed. Please verify your database structure.")
            return 1
    except Exception as e:
        logger.error(f"Schema validation error: {e}")
        return 1

    # Load Known Places and Zones
    known_places = load_known_places(db_engine)
    zones = load_zones(db_engine)
    
    if not zones:
        logger.error("No zones loaded from the database. Cannot proceed without zone data.")
        return 1
        
    if not known_places:
        logger.warning("No known places loaded from the database. Processing will assume all locations are new initially.")
        # Allow continuing if no places exist yet

    # Get Chunks to Process
    chunks_to_process = get_chunks_to_process(
        db_engine, 
        args.start, 
        args.end if args.all is False else None,
        overwrite=args.overwrite
    )
    if not chunks_to_process:
        logger.info("No chunks found matching the specified criteria.")
        return 0

    logger.info(f"Found {len(chunks_to_process)} chunks to process.")

    # Setup LLM Provider
    try:
        provider_kwargs = {
            "api_key": args.api_key,
            "model": args.model or DEFAULT_MODEL_FOR_SCRIPT, # Ensure script default is used if arg not provided
            "temperature": args.temperature if args.temperature is not None else 0.1, # Default temp if not provided
            "max_tokens": args.max_tokens,
            "system_prompt": args.system_prompt,
        }
        
        llm_provider = LLMProvider.from_provider_name(args.provider, **provider_kwargs)
        logger.info(f"Using LLM provider: {args.provider}, Model: {llm_provider.model}")
    except Exception as e:
        logger.error(f"Failed to initialize LLM provider: {e}")
        return 1

    # --- Processing Loop ---
    total_chunks = len(chunks_to_process)
    processed_count = 0
    success_count = 0
    error_count = 0
    start_time = time.time()
    processing_stopped = False  # Flag to track user termination

    batch_size = args.batch_size

    for i in range(0, total_chunks, batch_size):
        batch = chunks_to_process[i:i + batch_size]
        logger.info(f"--- Starting Batch {i // batch_size + 1} / {(total_chunks + batch_size - 1) // batch_size} (Chunks {batch[0].id} to {batch[-1].id}) ---")

        for chunk in batch:
            processed_count += 1
            logger.info(f"Processing chunk {chunk.id} ({processed_count}/{total_chunks})...")

            # Process the chunk
            try:
                should_continue = process_chunk(
                    db=db_engine,
                    chunk=chunk,
                    places=known_places, 
                    zones=zones,
                    provider_instance=llm_provider,
                    args=args,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    auto=args.auto
                )
                
                # Check the return value from process_chunk:
                # - 1: Success - processing completed successfully
                # - 0: User requested stop
                # - -1: Error - processing failed due to LLM API error or other issue
                if should_continue == 1:
                    # Success case
                    success_count += 1
                elif should_continue == 0:
                    # User requested stop
                    logger.info(f"Stopping processing after chunk {chunk.id} as requested by user.")
                    success_count += 1  # The chunk was successfully processed up to the stop point
                    processing_stopped = True  # Signal to stop processing entirely
                    break  # Exit the current batch loop
                else:  # should_continue == -1 or other negative value
                    # Error case
                    logger.error(f"Processing failed for chunk {chunk.id}, counting as an error.")
                    error_count += 1
                    # Continue processing the next chunk
                    
            except Exception as e:
                logger.error(f"Unhandled exception processing chunk {chunk.id}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                error_count += 1
                # Stop processing this batch after an unhandled error
                logger.warning(f"Stopping current batch due to unhandled error in chunk {chunk.id}.")
                processing_stopped = True
                break # Exit the inner loop (processing chunks in the current batch)

            # Delay between individual calls (if not last in batch and not dry run)
            if not args.dry_run and chunk != batch[-1]:
                delay = COOLDOWNS.get("individual", 2)
                if delay > 0:
                    logger.debug(f"Waiting {delay}s before next API call...")
                    time.sleep(delay)

        logger.info(f"--- Batch {i // batch_size + 1} Complete ---")
        logger.info(f"Progress: {processed_count}/{total_chunks} chunks attempted.")
        logger.info(f"Successes: {success_count}, Errors: {error_count}")
        
        # Check if processing was stopped by user within the batch
        if processing_stopped:
            logger.info("Processing stopped by user during confirmation.")
            break

        # Prompt or delay before next batch (if not stopped and not auto)
        if i + batch_size < total_chunks and not args.dry_run and not processing_stopped:
            if not args.auto: # Only prompt between batches if NOT in auto mode
                try:
                    user_input = input("\nContinue with the next batch? [1=Yes, 0=No]: ")
                    if user_input == '0':
                        logger.info("Processing stopped by user between batches.")
                        processing_stopped = True # Set flag to prevent further batches
                        break # Exit outer batch loop
                except EOFError:
                    logger.info("EOF detected between batches, stopping processing.")
                    processing_stopped = True
                    break # Stop if input stream is closed
            else:
                # In auto mode, add delay between batches if configured
                batch_delay = COOLDOWNS.get("batch", 5)
                if batch_delay > 0:
                    logger.info(f"Auto mode: Waiting {batch_delay}s before next batch...")
                    time.sleep(batch_delay)

    # --- End of Processing ---
    end_time = time.time()
    duration = end_time - start_time
    logger.info("=" * 30)
    logger.info("Location Extraction Complete")
    logger.info(f"Total Chunks Attempted: {processed_count}")
    logger.info(f"Successful Updates: {success_count}")
    logger.info(f"Errors Encountered: {error_count}")
    logger.info(f"Total Duration: {duration:.2f} seconds")
    logger.info(f"Mode: {'Dry Run' if args.dry_run else 'Database Write'}")
    logger.info("=" * 30)

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())