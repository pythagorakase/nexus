#!/usr/bin/env python
"""
Map Illustrator - A tool for extracting and expanding location data.

This script extracts factual information from narrative chunks and/or
creates creative expansions of locations based on source material.
"""

import argparse
import json
import os
import sys
import re
from typing import Dict, List, Optional, Set, Union, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
import psycopg2.sql as sql
from pydantic import BaseModel, Field, ConfigDict

# Import tiktoken for token counting
try:
    import tiktoken
    TIKTOKEN_IMPORT_SUCCESS = True
except ImportError:
    TIKTOKEN_IMPORT_SUCCESS = False
    print("Warning: tiktoken not found. Token counting will be approximated.")

# Import OpenAI API helper if available
try:
    # Get script directory to handle imports correctly
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(script_dir)  # Add script directory to path
    
    # Try importing with script directory in path
    from api_openai import send_api_request, OpenAIProvider
    OPENAI_IMPORT_SUCCESS = True
    print("Successfully imported api_openai helper")
except ImportError as e:
    OPENAI_IMPORT_SUCCESS = False
    from openai import OpenAI
    print(f"Warning: Could not import api_openai helper: {e}")
    print("Creative mode requires the OpenAI client library for structured outputs.")
    print("The script will attempt to use the base OpenAI client for compatibility.")


# Function to count tokens in a string
def count_tokens(text: str, model_name: str = "gpt-4o") -> int:
    """Count the number of tokens in a string for a given model."""
    if not TIKTOKEN_IMPORT_SUCCESS:
        # If tiktoken is not available, use a rough approximation
        # GPT models use ~4 characters per token on average
        return len(text) // 4
    
    try:
        encoding = tiktoken.encoding_for_model(model_name)
        return len(encoding.encode(text))
    except Exception as e:
        # Fallback to general purpose encoder if model-specific one fails
        try:
            encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
            return len(encoding.encode(text))
        except Exception as e:
            # Last resort fallback
            return len(text) // 4


# Pydantic Models for Structured Outputs
class SensoryDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    sights: List[str] = Field(description="Visual details that can be observed")
    sounds: List[str] = Field(description="Auditory details that can be heard")
    smells: List[str] = Field(description="Olfactory details that can be smelled")
    textures: List[str] = Field(description="Tactile details that can be felt")


class PhysicalAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    appearance: str = Field(description="Description of the place's visual appearance")
    atmosphere: str = Field(description="The overall feel or ambiance of the place")
    notable_features: List[str] = Field(description="List of distinctive physical features")
    sensory_details: SensoryDetails = Field(description="Sensory information categorized by type")


class Area(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    description: str = Field(description="Description of this specific area within the location")
    purpose: str = Field(description="The function or purpose of this area")
    notable_features: List[str] = Field(description="Distinctive features of this area")


class Surroundings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    environment: str = Field(description="Description of the surrounding environment")
    approach: str = Field(description="How one typically approaches or accesses this location")
    nearby_features: List[str] = Field(description="Notable features in the vicinity")
    weather_patterns: str = Field(description="Typical weather conditions, if relevant")
    accessibility: str = Field(description="How easy or difficult it is to access this location")


class Technology(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    systems: List[str] = Field(description="Technical systems present at the location")
    capabilities: List[str] = Field(description="What the technology can do")
    limitations: List[str] = Field(description="Limitations of the technology")
    unique_aspects: str = Field(description="What makes the technology special or unique")


class SocialAspects(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    customs: List[str] = Field(description="Social customs or norms associated with this place")
    power_structure: str = Field(description="Who holds authority and how power is distributed")
    common_activities: List[str] = Field(description="Activities typically performed here")
    reputation: str = Field(description="How this place is viewed by others")


class Secrets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    mysteries: List[str] = Field(description="Unexplained or mysterious aspects")
    tensions: List[str] = Field(description="Points of conflict or tension")
    narrative_hooks: List[str] = Field(description="Potential storylines related to this location")
    hidden_elements: List[str] = Field(description="Things that are deliberately concealed")


class AreaBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(description="Name of this area")
    area_data: Area = Field(description="Area details")

class ExtraData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    areas: List[AreaBlock] = Field(description="Named areas within the location")
    physical_attributes: PhysicalAttributes = Field(description="Physical characteristics")
    surroundings: Surroundings = Field(description="The location's surroundings")
    technology: Technology = Field(description="Technological aspects")
    social_aspects: SocialAspects = Field(description="Social elements")
    secrets: Secrets = Field(description="Hidden or secretive elements")


class CreativeExpansion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    summary: str = Field(description="Brief 2-3 sentence overview of the location")
    inhabitants: List[str] = Field(description="Who lives, works, or visits this location")
    history: str = Field(description="The location's backstory and significant past events")
    current_status: str = Field(description="The location's present condition and function")
    secrets: str = Field(description="Hidden aspects with narrative potential")
    extra_data: Optional[ExtraData] = Field(None, description="Detailed structured information")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Extract or expand location data from narrative chunks")
    
    # Place ID - required for normal mode, not for input mode
    parser.add_argument("--place", type=int, help="Place ID to process")
    
    # Input mode - mutually exclusive with normal operation modes
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--input", help="Use a custom API package JSON file instead of building one")
    
    # Normal operation modes when not using --input
    normal_mode_group = input_group.add_argument_group()
    
    # Mode arguments (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--fact", action="store_true", help="Extract factual information only")
    mode_group.add_argument("--creative", action="store_true", help="Create creative expansion")
    
    # Source arguments (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--chunk", action="store_true", help="Use directly referenced chunks")
    source_group.add_argument("--episode", action="store_true", help="Use all chunks from relevant episodes")
    
    # Optional arguments
    parser.add_argument("--debug", action="store_true", help="Show output without updating database")
    parser.add_argument("--test", action="store_true", help="Show API payload without making the call")
    parser.add_argument("--temperature", type=float, help="Set the temperature for the API call")
    parser.add_argument("--effort", choices=["low", "medium", "high"], default="medium", 
                       help="Set reasoning effort for compatible models (default: medium)")
    parser.add_argument("--model", default="gpt-4o", 
                       help="Specify model to use (default: gpt-4o)")
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.input:
        # When not using input mode, both place ID and mode+source arguments are required
        if not args.place:
            parser.error("--place is required when not using --input")
        if not (args.fact or args.creative):
            parser.error("One of --fact or --creative is required when not using --input")
        if not (args.chunk or args.episode):
            parser.error("One of --chunk or --episode is required when not using --input")
    
    return args


def connect_to_db():
    """Connect to the NEXUS database."""
    try:
        conn = psycopg2.connect(
            "dbname=NEXUS user=pythagor host=localhost port=5432",
            cursor_factory=RealDictCursor
        )
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def get_place_by_id(conn, place_id: int) -> Dict:
    """Get place information by ID, including zone data."""
    cursor = conn.cursor()
    
    query = """
    SELECT p.*, z.name as zone_name, z.summary as zone_summary
    FROM places p
    JOIN zones z ON p.zone = z.id
    WHERE p.id = %s
    """
    
    cursor.execute(query, (place_id,))
    place = cursor.fetchone()
    
    if not place:
        print(f"Error: No place found with ID {place_id}")
        sys.exit(1)
        
    cursor.close()
    return place


def get_chunks_for_place(conn, place_id: int) -> List[Dict]:
    """Get all chunks that reference the specified place."""
    cursor = conn.cursor()
    
    query = """
    SELECT 
        nc.id as chunk_id,
        nc.raw_text,
        pcr.reference_type,
        pcr.evidence,
        cm.season,
        cm.episode,
        cm.scene,
        cm.slug
    FROM place_chunk_references pcr
    JOIN narrative_chunks nc ON pcr.chunk_id = nc.id
    LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
    WHERE pcr.place_id = %s
    ORDER BY cm.season, cm.episode, cm.scene, nc.id
    """
    
    cursor.execute(query, (place_id,))
    chunks = cursor.fetchall()
    cursor.close()
    
    # For each chunk, get all places referenced in it
    for chunk in chunks:
        places = get_places_for_chunk(conn, chunk['chunk_id'])
        if places:
            chunk['places'] = places
        else:
            # Ensure there's always a places key
            chunk['places'] = []
    
    return chunks


def get_episodes_containing_place(conn, place_id: int) -> List[Dict]:
    """Get all episodes that contain chunks referencing the specified place."""
    cursor = conn.cursor()
    
    query = """
    SELECT DISTINCT e.*
    FROM episodes e
    JOIN chunk_metadata cm ON cm.season = e.season AND cm.episode = e.episode
    JOIN place_chunk_references pcr ON pcr.chunk_id = cm.chunk_id
    WHERE pcr.place_id = %s
    ORDER BY e.season, e.episode
    """
    
    cursor.execute(query, (place_id,))
    episodes = cursor.fetchall()
    cursor.close()
    
    return episodes


def get_chunks_for_episodes(conn, episodes: List[Dict]) -> List[Dict]:
    """Get all chunks from the specified episodes."""
    if not episodes:
        return []
    
    cursor = conn.cursor()
    chunks = []
    
    for episode in episodes:
        # Handle chunk_span as a NumericRange object
        if episode['chunk_span'] is not None:
            # NumericRange objects have lower and upper properties
            try:
                # First try direct access to properties (psycopg2 with appropriate extension)
                lower_bound = episode['chunk_span'].lower
                upper_bound = episode['chunk_span'].upper
            except AttributeError:
                # Fallback if it's a string representation
                range_str = str(episode['chunk_span'])
                # Format is typically something like "[1,10)" or "[1,10]"
                lower_bound = int(range_str.split(',')[0].lstrip('['))
                upper_bound = int(range_str.split(',')[1].rstrip(')').rstrip(']'))
            
            # Ensure upper_bound is not None
            if upper_bound is None:
                # If no upper bound, use a large number
                upper_bound = 999999
                
            query = """
            SELECT 
                nc.id as chunk_id,
                nc.raw_text,
                cm.season,
                cm.episode,
                cm.scene,
                cm.slug
            FROM narrative_chunks nc
            JOIN chunk_metadata cm ON nc.id = cm.chunk_id
            WHERE nc.id >= %s AND nc.id <= %s
            ORDER BY nc.id
            """
            
            cursor.execute(query, (lower_bound, upper_bound))
            episode_chunks = cursor.fetchall()
            
            # For each chunk, get all places referenced in it
            for chunk in episode_chunks:
                places = get_places_for_chunk(conn, chunk['chunk_id'])
                if places:
                    chunk['places'] = places
                else:
                    # Ensure there's always a places key
                    chunk['places'] = []
                chunks.append(chunk)
    
    cursor.close()
    return chunks


def get_places_for_chunk(conn, chunk_id: int) -> List[Dict]:
    """Get all places referenced in a specific chunk."""
    cursor = conn.cursor()
    
    query = """
    SELECT 
        p.id as place_id,
        p.name as place_name,
        p.type as place_type,
        p.summary,
        z.id as zone_id,
        z.name as zone_name,
        pcr.reference_type,
        pcr.evidence
    FROM place_chunk_references pcr
    JOIN places p ON pcr.place_id = p.id
    JOIN zones z ON p.zone = z.id
    WHERE pcr.chunk_id = %s
    ORDER BY z.id, p.id
    """
    
    cursor.execute(query, (chunk_id,))
    places = cursor.fetchall()
    cursor.close()
    
    # Make sure we return an empty list, not None
    return places if places else []


def format_chunk_place_references(chunk: Dict, target_place_id: int) -> str:
    """Format place references for a single chunk by zone."""
    result = [f"PLACE REFERENCES IN CHUNK {chunk['chunk_id']}:"]
    
    # Add metadata if available
    if 'season' in chunk and 'episode' in chunk:
        season = chunk.get('season')
        episode = chunk.get('episode')
        scene = chunk.get('scene')
        
        metadata = f"Season {season}, Episode {episode}"
        if scene is not None:
            metadata += f", Scene {scene}"
        result.append(metadata)
    
    # Organize places by zone with zone_id for sorting
    zones = {}
    
    # Get places from this chunk
    places = chunk.get('places', [])
    
    # Handle when there are no places
    if not places:
        result.append("None")
        return "\n".join(result)
    
    # Check if the target place is in this chunk
    has_target = any(place['place_id'] == target_place_id for place in places)
    if has_target:
        result.append("TARGET PLACE IS REFERENCED IN THIS CHUNK ✓")
    
    # Collect places by zone
    for place in places:
        zone_name = place['zone_name']
        zone_id = place['zone_id']
        place_name = place['place_name']
        place_id = place['place_id']
        reference_type = place['reference_type']
        
        # Add zone if it doesn't exist
        if zone_id not in zones:
            zones[zone_id] = {
                'name': zone_name,
                'places': []
            }
        
        # Add place to this zone
        zones[zone_id]['places'].append({
            'id': place_id,
            'name': place_name,
            'reference_type': reference_type,
            'is_target': place_id == target_place_id
        })
    
    # Format by zone, sorting zones by ID
    for zone_id in sorted(zones.keys()):
        zone = zones[zone_id]
        result.append(f"{zone['name']}")
        
        # Sort places by ID
        places = sorted(zone['places'], key=lambda p: p['id'])
        
        # Format places
        for i, place in enumerate(places):
            # Use different prefixes for last vs. non-last items
            is_last = i == len(places) - 1
            prefix = "└─" if is_last else "├─"
                
            # Add target marker if this is the target place
            target_marker = "→ " if place['is_target'] else ""
            
            # Format place ID with 3 digits
            place_id_str = f"{place['id']:03d}"
            
            # Make target place more visible with asterisks if it's the target
            place_name = place['name']
            if place['is_target']:
                place_name = f"*{place_name}*"
            
            result.append(f"  {prefix}{target_marker}{place_id_str}: {place_name} ({place['reference_type']})")
    
    return "\n".join(result)


def load_system_prompt():
    """Load system prompts from external file."""
    try:
        # Get absolute path relative to the script's location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        prompt_path = os.path.join(project_root, "prompts", "map_illustrator.json")
        
        with open(prompt_path, "r") as f:
            prompts = json.load(f)
        return prompts
    except Exception as e:
        print(f"Error loading system prompt: {e}")
        sys.exit(1)


def prepare_fact_prompt(place: Dict, chunks: List[Dict], formatted_tags: str = None) -> Dict:
    """Prepare the fact-extraction prompt."""
    # Create a section for each chunk with its own place references and content
    chunk_sections = []
    
    for i, chunk in enumerate(chunks):
        # Format place references for this chunk
        chunk_refs = format_chunk_place_references(chunk, place['id'])
        
        # Create chunk header with ID and metadata if available
        chunk_header = f"CHUNK {chunk['chunk_id']}"
        if 'season' in chunk and 'episode' in chunk:
            chunk_header += f" (Season {chunk['season']}, Episode {chunk['episode']}"
            if 'scene' in chunk and chunk['scene'] is not None:
                chunk_header += f", Scene {chunk['scene']}"
            chunk_header += ")"
        
        # Add the chunk header, references followed by the chunk text
        chunk_section = f"{'=' * 60}\n{chunk_header}\n{'=' * 60}\n{chunk_refs}\n\n{chunk['raw_text']}"
        chunk_sections.append(chunk_section)
    
    # Join all chunk sections with clear separators
    all_chunks = "\n\n".join(chunk_sections)
    
    prompt = f"""
I need a factual summary of the location "{place['name']}" (ID: {place['id']}) in the zone "{place['zone_name']}".

{all_chunks}
"""
    
    return {
        "role": "user",
        "content": prompt.strip()
    }


def prepare_creative_prompt(place: Dict, chunks: List[Dict], formatted_tags: str = None) -> Dict:
    """Prepare the creative expansion prompt."""
    
    # Include the factual summary as a foundation
    fact_foundation = place.get('summary', 'No factual summary available.')
    
    # Create a section for each chunk with its own place references and content
    chunk_sections = []
    
    for i, chunk in enumerate(chunks):
        # Format place references for this chunk
        chunk_refs = format_chunk_place_references(chunk, place['id'])
        
        # Create chunk header with ID and metadata if available
        chunk_header = f"CHUNK {chunk['chunk_id']}"
        if 'season' in chunk and 'episode' in chunk:
            chunk_header += f" (Season {chunk['season']}, Episode {chunk['episode']}"
            if 'scene' in chunk and chunk['scene'] is not None:
                chunk_header += f", Scene {chunk['scene']}"
            chunk_header += ")"
        
        # Add the chunk header, references followed by the chunk text
        chunk_section = f"{'=' * 60}\n{chunk_header}\n{'=' * 60}\n{chunk_refs}\n\n{chunk['raw_text']}"
        chunk_sections.append(chunk_section)
    
    # Join all chunk sections with clear separators
    all_chunks = "\n\n".join(chunk_sections)
    
    prompt = f"""
I need a creative expansion of the location "{place['name']}" (ID: {place['id']}) in the zone "{place['zone_name']}".

FACTUAL FOUNDATION (treat this as canonical truth):
{fact_foundation}

{all_chunks}
"""
    
    return {
        "role": "user",
        "content": prompt.strip()
    }


def extract_facts_with_openai(place: Dict, chunks: List[Dict], temperature: Optional[float] = None, test_mode: bool = False, effort: str = "medium", model: str = "gpt-4o"):
    """Extract factual information using OpenAI API."""
    system_prompts = load_system_prompt()
    system_prompt = system_prompts["fact_mode"]
    
    # Create messages with system prompt
    messages = [
        {"role": "system", "content": json.dumps(system_prompt)},
        prepare_fact_prompt(place, chunks)
    ]
    
    # Add final message with repeated system prompt and target place reminder for redundancy
    messages.append({
        "role": "user", 
        "content": f"IMPORTANT: Remember your task. {json.dumps(system_prompt)}\n\nFOCUS ONLY ON PLACE ID: {place['id']}, NAME: \"{place['name']}\". DO NOT create content for any other places mentioned in the context."
    })
    
    # Count tokens for each message
    system_tokens = count_tokens(messages[0]["content"])
    user_tokens = count_tokens(messages[1]["content"])
    reminder_tokens = count_tokens(messages[2]["content"])
    total_input_tokens = system_tokens + user_tokens + reminder_tokens
    
    # Determine if we should use reasoning parameter
    use_reasoning = model.startswith("o")
    
    # Prepare API payload
    payload = {
        "model": model,
        "messages": messages,
    }
    
    if temperature is not None and not use_reasoning:
        payload["temperature"] = temperature
    
    # Test mode - show payload and exit
    if test_mode:
        print("\n===== TEST MODE: API PAYLOAD =====")
        print(f"\nModel: {model}")
        
        if use_reasoning:
            print(f"Reasoning effort: {effort}")
        else:
            print(f"Temperature: {temperature if temperature is not None else 'Not specified'}")
        
        print("\n----- System Prompt -----")
        print(json.dumps(system_prompt, indent=2))
        
        print("\n----- User Prompts -----")
        print(messages[1]["content"])
        print("\n----- Final Reminder -----")
        print(messages[2]["content"])
        
        # Print token information
        print("\n----- Token Information -----")
        print(f"System prompt tokens: {system_tokens}")
        print(f"User prompt tokens: {user_tokens}")
        print(f"Reminder tokens: {reminder_tokens}")
        print(f"Total input tokens: {total_input_tokens}")
        
        print("\n=================================\n")
        return "TEST MODE - No API call made"
    
    # Make API call
    try:
        if OPENAI_IMPORT_SUCCESS:
            # Use the imported function if available
            if use_reasoning:
                # Add reasoning parameter for o-prefix models
                payload["reasoning_effort"] = effort
                if temperature is not None:
                    payload["temperature"] = temperature
            response = send_api_request(payload)
            return response['choices'][0]['message']['content']
        else:
            # Fall back to direct OpenAI client usage
            client = OpenAI()
            if use_reasoning:
                # Use reasoning parameter with client
                if model.startswith("o"):
                    # For o-series models with chat completions
                    kwargs = {
                        "model": model,
                        "messages": messages,
                        "reasoning": {"effort": effort}  # New format for chat completions
                    }
                    if temperature is not None:
                        kwargs["temperature"] = temperature
                else:
                    # For other models that might use different format
                    kwargs = {
                        "model": model,
                        "messages": messages,
                        "reasoning_effort": effort  # Old format for some models
                    }
                    if temperature is not None:
                        kwargs["temperature"] = temperature
                response = client.chat.completions.create(**kwargs)
            else:
                response = client.chat.completions.create(**payload)
            return response.choices[0].message.content
            
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        sys.exit(1)


def expand_creatively_with_openai(place: Dict, chunks: List[Dict], temperature: Optional[float] = None, test_mode: bool = False, effort: str = "medium", model: str = "gpt-4o"):
    """Create a creative expansion using OpenAI API with structured output."""
    system_prompts = load_system_prompt()
    system_prompt = system_prompts["creative_mode"]
    
    messages = [
        {"role": "system", "content": json.dumps(system_prompt)},
        prepare_creative_prompt(place, chunks)
    ]
    
    # Add final message with repeated system prompt and target place reminder for redundancy
    messages.append({
        "role": "user", 
        "content": f"IMPORTANT: Remember your task. {json.dumps(system_prompt)}\n\nFOCUS ONLY ON PLACE ID: {place['id']}, NAME: \"{place['name']}\". DO NOT create content for any other places mentioned in the context."
    })
    
    # Count tokens for each message
    system_tokens = count_tokens(messages[0]["content"])
    user_tokens = count_tokens(messages[1]["content"])
    reminder_tokens = count_tokens(messages[2]["content"])
    total_input_tokens = system_tokens + user_tokens + reminder_tokens
    
    # Determine if we should use reasoning parameter
    use_reasoning = model.startswith("o")
    
    if test_mode:
        print("\n===== TEST MODE: API PAYLOAD =====")
        print(f"\nModel: {model}")
        
        if use_reasoning:
            print(f"Reasoning effort: {effort}")
        else:
            print(f"Temperature: {temperature if temperature is not None else 'Not specified'}")
        
        print("\n----- System Prompt -----")
        print(json.dumps(system_prompt, indent=2))
        
        print("\n----- User Prompts -----")
        print(messages[1]["content"])
        print("\n----- Final Reminder -----")
        print(messages[2]["content"])
        
        # Print token information
        print("\n----- Token Information -----")
        print(f"System prompt tokens: {system_tokens}")
        print(f"User prompt tokens: {user_tokens}")
        print(f"Reminder tokens: {reminder_tokens}")
        print(f"Total input tokens: {total_input_tokens}")
        
        print("\n=================================\n")
        return None
    
    try:
        # Use OpenAI API with structured output
        client = OpenAI()
        
        # Configure parameters
        kwargs = {
            "model": model,
            "input": messages
        }
        
        # Add appropriate parameters based on model type
        if use_reasoning:
            kwargs["reasoning"] = {"effort": effort}
            if temperature is not None:
                kwargs["temperature"] = temperature
        elif temperature is not None:
            kwargs["temperature"] = temperature
        
        # Use the responses.parse method to get structured output
        print("Calling OpenAI API to generate creative expansion...")
        print(f"Input tokens: {total_input_tokens}")
        if use_reasoning:
            print(f"Using reasoning effort: {effort}")
            
        response = client.responses.parse(
            text_format=CreativeExpansion,
            **kwargs
        )
        
        parsed_response = response.output_parsed
        print("Successfully received structured response from API")
        
        return parsed_response
            
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        print(f"Exception details: {str(e)}")
        sys.exit(1)


def update_place_summary(conn, place_id: int, summary: str) -> bool:
    """Update the summary field for a place."""
    cursor = conn.cursor()
    
    query = """
    UPDATE places
    SET summary = %s
    WHERE id = %s
    RETURNING id
    """
    
    try:
        cursor.execute(query, (summary, place_id))
        conn.commit()
        result = cursor.fetchone()
        cursor.close()
        return result is not None
    except Exception as e:
        conn.rollback()
        cursor.close()
        print(f"Error updating place summary: {e}")
        return False


def update_place_creative(conn, place_id: int, expansion: CreativeExpansion) -> bool:
    """Update all fields for a creative expansion."""
    cursor = conn.cursor()
    
    query = """
    UPDATE places
    SET 
        summary = %s,
        inhabitants = %s,
        history = %s,
        current_status = %s,
        secrets = %s,
        extra_data = %s
    WHERE id = %s
    RETURNING id
    """
    
    try:
        # Convert inhabitants list to PostgreSQL array
        inhabitants_array = expansion.inhabitants
        
        # Convert extra_data to JSON string if it exists
        extra_data_json = json.loads(expansion.extra_data.json()) if expansion.extra_data else {}
        
        cursor.execute(query, (
            expansion.summary,
            inhabitants_array,
            expansion.history,
            expansion.current_status,
            expansion.secrets,
            json.dumps(extra_data_json),
            place_id
        ))
        
        conn.commit()
        result = cursor.fetchone()
        cursor.close()
        return result is not None
    except Exception as e:
        conn.rollback()
        cursor.close()
        print(f"Error updating place with creative expansion: {e}")
        return False


def process_place_fact_mode(conn, place_id: int, use_chunks: bool, use_episodes: bool, debug: bool, test: bool, temperature: Optional[float] = None, effort: str = "medium", model: str = "gpt-4o"):
    """Process a place in fact mode."""
    # Get place data
    place = get_place_by_id(conn, place_id)
    
    # Get appropriate chunks based on flags
    chunks = []
    if use_chunks:
        chunks = get_chunks_for_place(conn, place_id)
    elif use_episodes:
        episodes = get_episodes_containing_place(conn, place_id)
        chunks = get_chunks_for_episodes(conn, episodes)
    
    if not chunks:
        print(f"No chunks found for place ID {place_id}")
        return False
    
    # Count total tokens in all chunks (for information)
    total_chunk_text = ""
    for chunk in chunks:
        total_chunk_text += chunk.get('raw_text', '')
    chunk_tokens = count_tokens(total_chunk_text)
    
    # Extract factual information
    print(f"Extracting factual information for place: {place['name']} (ID: {place_id})")
    print(f"Processing {len(chunks)} chunks with approximately {chunk_tokens} tokens of raw text")
    print(f"Model: {model}, {'Reasoning effort: ' + effort if model.startswith('o') else 'Temperature: ' + str(temperature) if temperature is not None else ''}")
    
    summary = extract_facts_with_openai(place, chunks, temperature, test, effort, model)
    
    if test:
        print("Test mode - stopping before API call")
        return True
    
    # Print the result
    print("\n===== FACTUAL SUMMARY =====")
    print(summary)
    summary_tokens = count_tokens(summary)
    print(f"Summary tokens: {summary_tokens}")
    print("===========================\n")
    
    # Update database unless in debug mode
    if not debug:
        # Confirm with user before updating
        print("\nReady to update the database with the factual summary for:")
        print(f"Place ID: {place_id}, Name: {place['name']}")
        print(f"First 200 characters of summary: {summary[:200]}...")
        confirm = input("\nDoes this look correct? Update database? (y/n): ").strip().lower()
        
        if confirm == 'y':
            print("Updating database...")
            success = update_place_summary(conn, place_id, summary)
            if success:
                print("Database updated successfully")
            else:
                print("Failed to update database")
            return success
        else:
            print("Update cancelled by user")
            return False
    else:
        print("Debug mode - database not updated")
        return True


def process_place_creative_mode(conn, place_id: int, use_chunks: bool, use_episodes: bool, debug: bool, test: bool, temperature: Optional[float] = None, effort: str = "medium", model: str = "gpt-4o"):
    """Process a place in creative mode."""
    # Get place data
    place = get_place_by_id(conn, place_id)
    
    # Verify factual summary exists
    if not place.get('summary'):
        print(f"Error: No factual summary exists for place ID {place_id}. Run fact mode first.")
        return False
    
    # Get appropriate chunks based on flags
    chunks = []
    if use_chunks:
        chunks = get_chunks_for_place(conn, place_id)
    elif use_episodes:
        episodes = get_episodes_containing_place(conn, place_id)
        chunks = get_chunks_for_episodes(conn, episodes)
    
    if not chunks:
        print(f"No chunks found for place ID {place_id}")
        return False
    
    # Count total tokens in all chunks (for information)
    total_chunk_text = ""
    for chunk in chunks:
        total_chunk_text += chunk.get('raw_text', '')
    chunk_tokens = count_tokens(total_chunk_text)
    summary_tokens = count_tokens(place.get('summary', ''))
    
    # Create creative expansion
    print(f"Creating creative expansion for place: {place['name']} (ID: {place_id})")
    print(f"Processing {len(chunks)} chunks with approximately {chunk_tokens} tokens of raw text")
    print(f"Factual summary: {summary_tokens} tokens")
    print(f"Model: {model}, {'Reasoning effort: ' + effort if model.startswith('o') else 'Temperature: ' + str(temperature) if temperature is not None else ''}")
    
    # Make the API call
    expansion = expand_creatively_with_openai(place, chunks, temperature, test, effort, model)
    
    if test:
        print("Test mode - stopping before API call")
        return True
    
    # Print the result
    print("\n===== CREATIVE EXPANSION =====")
    print(f"Summary: {expansion.summary}")
    print(f"Inhabitants: {', '.join(expansion.inhabitants)}")
    print(f"History: {expansion.history}")
    print(f"Current Status: {expansion.current_status}")
    print(f"Secrets: {expansion.secrets}")
    
    # Count tokens in the response
    expansion_json = expansion.json()
    expansion_tokens = count_tokens(expansion_json)
    print(f"Total expansion tokens: {expansion_tokens}")
    
    # Print the extra_data in a structured format
    if expansion.extra_data:
        print("\nExtra Data:")
        extra_data_dict = json.loads(expansion.extra_data.json())
        print(json.dumps(extra_data_dict, indent=2))
    else:
        print("\nNo Extra Data provided")
    print("=============================\n")
    
    # Update database unless in debug mode
    if not debug:
        # Confirm with user before updating
        confirm = input("\nDoes this creative expansion look correct? Update database? (y/n): ").strip().lower()
        
        if confirm == 'y':
            print("Updating database...")
            success = update_place_creative(conn, place_id, expansion)
            if success:
                print("Database updated successfully")
            else:
                print("Failed to update database")
            return success
        else:
            print("Update cancelled by user")
            return False
    else:
        print("Debug mode - database not updated")
        return True


def process_input_package(conn, input_file: str, debug: bool, test: bool, temperature: Optional[float] = None, effort: str = "medium", model: str = "gpt-4o"):
    """Process a custom API package from a JSON file."""
    try:
        # Load the API package
        with open(input_file, 'r') as f:
            package = json.load(f)
        
        # Extract place_id for database write
        place_id = package.get("place_id")
        if not place_id:
            # Ask for the place ID if not in the package
            place_id_input = input("\nNo place ID found in the package. Please enter the place ID: ").strip()
            try:
                place_id = int(place_id_input)
            except ValueError:
                print("Invalid place ID. Must be an integer.")
                return False
        
        # Extract messages - using directly as provided
        messages = package.get("messages", [])
        
        # If test mode, just show what we loaded and exit
        if test:
            print("\n===== TEST MODE: LOADED PACKAGE =====")
            print(f"Place ID: {place_id}")
            print(f"Using model: {model}")
            print(f"Number of message objects: {len(messages)}")
            for i, msg in enumerate(messages):
                role = msg.get("role", "unknown")
                content_preview = msg.get("content", "")[:100] + "..." if len(msg.get("content", "")) > 100 else msg.get("content", "")
                print(f"Message {i+1}: {role} - {content_preview}")
            print("====================================\n")
            return True
        
        # Call OpenAI API with the loaded messages
        print(f"Processing input package for place ID: {place_id}")
        print(f"Using model: {model}")
        
        # Use the existing creative expansion function to get structured output
        client = openai.OpenAI()
        
        # Configure parameters
        kwargs = {
            "model": model,
            "input": messages
        }
        
        # Add appropriate parameters based on model type
        if model.startswith('o'):
            kwargs["reasoning"] = {"effort": effort}
            if temperature is not None:
                kwargs["temperature"] = temperature
        elif temperature is not None:
            kwargs["temperature"] = temperature
        
        # Use the responses.parse method to get structured output
        print("Calling OpenAI API to generate creative expansion...")
        if model.startswith('o'):
            print(f"Using reasoning effort: {effort}")
            
        response = client.responses.parse(
            text_format=CreativeExpansion,
            **kwargs
        )
        
        parsed_response = response.output_parsed
        print("Successfully received structured response from API")
        
        # Print the result
        print("\n===== CREATIVE EXPANSION =====")
        print(f"Summary: {parsed_response.summary}")
        print(f"Inhabitants: {', '.join(parsed_response.inhabitants)}")
        print(f"History: {parsed_response.history}")
        print(f"Current Status: {parsed_response.current_status}")
        print(f"Secrets: {parsed_response.secrets}")
        
        # Print the extra_data in a structured format
        if parsed_response.extra_data:
            print("\nExtra Data:")
            extra_data_dict = json.loads(parsed_response.extra_data.json())
            print(json.dumps(extra_data_dict, indent=2))
        else:
            print("\nNo Extra Data provided")
        print("=============================\n")
        
        # Update database unless in debug mode
        if not debug:
            # Get place name for confirmation
            place_name = "Unknown Place"
            try:
                query = "SELECT name FROM places WHERE id = %s"
                cursor = conn.cursor()
                cursor.execute(query, (place_id,))
                result = cursor.fetchone()
                if result:
                    place_name = result["name"]
                cursor.close()
            except Exception as e:
                print(f"Warning: Could not get place name: {e}")
                
            # Confirm with user before updating
            confirm = input(f"\nReady to update place ID {place_id} ({place_name}) with this creative expansion? (y/n): ").strip().lower()
            
            if confirm == 'y':
                print("Updating database...")
                success = update_place_creative(conn, place_id, parsed_response)
                if success:
                    print("Database updated successfully")
                else:
                    print("Failed to update database")
                return success
            else:
                print("Update cancelled by user")
                return False
        else:
            print("Debug mode - database not updated")
            return True
            
    except Exception as e:
        print(f"Error processing input package: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function."""
    args = parse_arguments()
    
    # No need for separate warning as it's already handled in the import section
    
    # Connect to database
    conn = connect_to_db()
    
    try:
        # Process based on arguments
        if args.input:
            # Process input package mode
            result = process_input_package(conn, args.input, args.debug, args.test, args.temperature, args.effort, args.model)
        elif args.fact:
            result = process_place_fact_mode(conn, args.place, args.chunk, args.episode, args.debug, args.test, args.temperature, args.effort, args.model)
        elif args.creative:
            result = process_place_creative_mode(conn, args.place, args.chunk, args.episode, args.debug, args.test, args.temperature, args.effort, args.model)
        
        if result:
            print("Process completed successfully")
        else:
            print("Process failed")
            sys.exit(1)
    finally:
        # Close database connection
        conn.close()


if __name__ == "__main__":
    main()