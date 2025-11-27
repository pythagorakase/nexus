#!/usr/bin/env python3
"""
Character Extraction Script for NEXUS

This script processes narrative chunks using an API-based LLM (defaulting to OpenAI)
to extract characters present or mentioned in each chunk. It updates the database
with character information and adds newly discovered characters.

Usage Examples:
    # Test connection and show prompt for the first processable chunk
    python process_characters.py --test

    # Process a single chunk (e.g., ID 5) and write to DB
    python process_characters.py --start 5

    # Process a range of chunks (e.g., IDs 10 to 20) and write to DB
    python process_characters.py --start 10 --end 20

    # Process all chunks that currently lack character data
    python process_characters.py --all

    # Process all chunks, overwriting existing character data
    python process_characters.py --all --overwrite

    # Process all chunks using a specific provider and model
    python process_characters.py --all --provider anthropic --model claude-3-5-sonnet-20240620

    # Process all chunks with a smaller batch size and without confirmation prompts
    python process_characters.py --all --batch-size 5 --auto

    # Run in dry-run mode (print actions but don't write to DB)
    python process_characters.py --start 1 --end 10 --dry-run

    # Show detailed logs during processing
    python process_characters.py --start 1 --verbose

Supported Arguments:
    --provider TEXT         LLM provider ('openai', 'anthropic', etc.) [default: openai]
    --model TEXT            LLM model name [default: gpt-4.1-mini]
    --api-key TEXT          API key (optional)
    --temperature FLOAT     Sampling temperature [default: 0.1]
    --max-tokens INTEGER    Maximum output tokens (optional)
    --reasoning-effort TEXT Reasoning effort for OpenAI models [default: medium]
    --system-prompt TEXT    System prompt string (optional)
    --db-url TEXT           Database connection string (optional, defaults from config)
    --batch-size INTEGER    Number of chunks to process per API batch [default: 10]
    --dry-run               Perform processing without writing to the database
    --verbose               Print detailed information including prompts and reasoning

    Chunk Selection (Required: Choose one method):
      --start INTEGER       Starting chunk ID number (use with --end or process single)
      --all                 Process all chunks needing character data (or all if --overwrite)
      --test                Test DB connection and print prompt for first chunk, then exit

    Chunk Selection Modifiers:
      --end INTEGER         Ending chunk ID number (used with --start)
      --overwrite           Process all chunks in range/all, including those with existing data

    Processing Control:
      --auto                Process automatically without prompting between batches

Database URL (from api_batch.py):
postgresql://pythagor@localhost/NEXUS
"""

import os
import sys
import argparse
import logging
import time
import json
from typing import List, Tuple, Optional, Dict, Any, Set

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy import create_engine, text

# Import necessary components from api_batch.py
# Assuming api_batch.py is in the same directory or Python path
try:
    from api_batch import (
        LLMProvider, OpenAIProvider, LLMResponse, get_token_count,
        get_db_connection_string, get_default_llm_argument_parser,
        validate_llm_requirements, SETTINGS, TPM_LIMITS, COOLDOWNS, logger
    )
except ImportError as e:
    print("Error: Could not import from api_batch.py. Make sure it's in the same directory or Python path.")
    print(e)
    sys.exit(1)

# Default model if not specified via CLI - use gpt-4.1-mini as a capable default for structured output
DEFAULT_MODEL_FOR_SCRIPT = "gpt-4.1-mini"

# --- Database Schema Constants ---
NARRATIVE_CHUNKS_TABLE = "narrative_chunks"
CHUNK_METADATA_TABLE = "chunk_metadata"
CHARACTERS_TABLE = "characters"


class NarrativeChunk:
    """Class to represent a narrative chunk for processing."""
    def __init__(self, id: int, raw_text: str, slug: Optional[str] = None):
        self.id = id
        self.raw_text = raw_text
        self.slug = slug

class KnownCharacter:
    """Class to represent a known character loaded from the database."""
    def __init__(self, id: int, name: str, aliases: List[str]):
        self.id = id
        self.name = name
        self.aliases = aliases if aliases else []

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments, extending the base parser from api_batch."""
    parser = get_default_llm_argument_parser()
    parser.description = "Extract characters from narrative chunks using an LLM."

    # Override default model specifically for this script
    # Find the --model argument and update its default
    for action in parser._actions:
        if action.dest == 'model':
            action.default = DEFAULT_MODEL_FOR_SCRIPT
            action.help = f"Model name to use (defaults to {DEFAULT_MODEL_FOR_SCRIPT} for this script)"
            break
            
    # Find the --reasoning-effort argument and update its default
    for action in parser._actions:
        if action.dest == 'reasoning_effort':
            action.default = "medium" # Default to medium for structured output consistency
            action.help = "Reasoning effort for OpenAI models (default: medium for structured output)"
            break

    # Add chunk selection arguments
    chunk_group = parser.add_argument_group("Chunk Selection Options")
    selection_method = chunk_group.add_mutually_exclusive_group(required=True)
    selection_method.add_argument("--start", type=int, help="Starting chunk id number")
    selection_method.add_argument("--all", action="store_true", help="Process all chunks needing character data")
    
    # Move --test outside the mutually exclusive group since it's a mode, not a chunk selection method
    parser.add_argument("--test", action="store_true", 
                       help="Test DB connection and print prompt for first processable chunk, then exit.")
    parser.add_argument("--overwrite", action="store_true", 
                       help="Process all chunks in range or all chunks in database, including those with existing character data.")

    chunk_group.add_argument("--end", type=int, help="Ending chunk id number (defaults to start if only start is provided)")

    # Add processing control arguments (reuse from api_batch)
    process_group = next((g for g in parser._action_groups if g.title == "Processing Options"), None)
    if process_group:
        process_group.add_argument("--auto", action="store_true", help="Process all chunks automatically without prompting between batches")
        process_group.add_argument("--verbose", action="store_true", help="Print detailed information including prompts")

    args = parser.parse_args()

    # Validate arguments
    if args.start is not None and args.end is None:
        args.end = args.start  # Default end to start

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

def load_known_characters(db: Engine) -> Dict[str, KnownCharacter]:
    """Load all existing characters and their aliases from the database."""
    characters = {}
    try:
        with db.connect() as conn:
            result = conn.execute(
                text(f"SELECT id, name, aliases FROM {CHARACTERS_TABLE}")
            ).fetchall()

            for row in result:
                char = KnownCharacter(id=row[0], name=row[1], aliases=row[2] or [])
                characters[char.name.lower()] = char # Store by lowercase name for easy lookup
                # Also add aliases to the lookup dict pointing to the same object
                for alias in char.aliases:
                    characters[alias.lower()] = char
            logger.info(f"Loaded {len(result)} known characters from the database.")
            return characters
    except Exception as e:
        logger.error(f"Error loading known characters: {str(e)}")
        return {}

def get_chunks_to_process(db: Engine, start_id: Optional[int] = None, end_id: Optional[int] = None, overwrite: bool = False) -> List[NarrativeChunk]:
    """Get chunks to process based on ID range or all needing character data.
    
    Args:
        db: Database engine
        start_id: Optional starting chunk ID
        end_id: Optional ending chunk ID
        overwrite: If True, process all chunks regardless of existing character data
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
                    # Get all chunks regardless of character data
                    query = text(f"""
                        SELECT nc.id, nc.raw_text, cm.slug
                        FROM {NARRATIVE_CHUNKS_TABLE} nc
                        LEFT JOIN {CHUNK_METADATA_TABLE} cm ON nc.id = cm.chunk_id
                        ORDER BY nc.id
                    """)
                    results = conn.execute(query).fetchall()
                    logger.info(f"Found {len(results)} total chunks for processing (overwrite=True).")
                else:
                    # Get only chunks where character data is missing or empty
                    query = text(f"""
                        SELECT nc.id, nc.raw_text, cm.slug
                        FROM {NARRATIVE_CHUNKS_TABLE} nc
                        LEFT JOIN {CHUNK_METADATA_TABLE} cm ON nc.id = cm.chunk_id
                        WHERE cm.characters IS NULL OR cm.characters = ARRAY[]::text[]
                        ORDER BY nc.id
                    """)
                    results = conn.execute(query).fetchall()
                    logger.info(f"Found {len(results)} chunks needing character processing.")

            return [NarrativeChunk(id=row[0], raw_text=row[1], slug=row[2]) for row in results]
    except Exception as e:
        logger.error(f"Error fetching chunks to process: {str(e)}")
        return []

def format_known_characters_for_prompt(known_characters: Dict[str, KnownCharacter]) -> str:
    """Format the known character list for the LLM prompt."""
    if not known_characters:
        return "None available."

    unique_chars = {char.id: char for char in known_characters.values()} # Get unique characters by ID
    formatted_list = []
    for char in sorted(unique_chars.values(), key=lambda c: c.name):
        alias_str = f" (Aliases: {', '.join(char.aliases)})" if char.aliases else ""
        formatted_list.append(f"- Canonical Name: \"{char.name}\"{alias_str}")

    return "\n".join(formatted_list)

def build_character_extraction_prompt(chunk: NarrativeChunk, known_characters_formatted: str) -> str:
    """Build the prompt for the LLM to extract characters."""
    # Using the template from process_characters.md
    prompt = f"""Extract ONLY true characters (sentient, independent entities) from this narrative chunk that are 
PRESENT
- actively in the scene
- virtually present and interacting with the characters (e.g., video/phone call, hologram)

or

MENTIONED
-referenced but not present

Definition of a Character:
- A distinct individual with independent agency who makes their own decisions
- Has their own motivations, thoughts, or consciousness
- Acts independently rather than being controlled directly by another character
- Must be an INDIVIDUAL, not a group or organization

NOT characters (DO NOT include these):
- Tools and devices that are extensions of a character's abilities:
  * Drones, robots, or cybernetic devices being directly controlled by a character
  * AI-enhanced tools that don't make independent decisions in the narrative
  * Example: A "cybernetic roach drone with onboard AI" that is directly controlled by a character is NOT a character
- Organizations, corporations, companies (e.g., Dynacorps, Arasaka)
- Projects or initiatives (e.g., "Echo", "Nexus", "Project Blackout")
- General groups of people (e.g., "the crowd", "soldiers", "the Sable Rats gang", "Vox Team")
- Character archetypes or roles mentioned abstractly
- Vehicles, weapons, or equipment (even those with basic AI assistance)
- Abstract concepts, places, or objects
- Factions or collectives

Definition of an Alias:
- A variation of a character's proper/canonical name (e.g., "Alex", "Alexander", "Alexander Ward")
- A unique nickname or title used for a character (e.g., "Baby Spice", "Deadhand")

NOT aliases (DO NOT include these):
- Generic titles or positions (e.g., "boss", "head of security")
- Pronouns (e.g., "he", "him", "she", "her", "they", "them")


KNOWN CHARACTERS REFERENCE LIST:
{known_characters_formatted}

Special Case: Alex is the user-controlled character, the story is told from her POV by default. Thus, she can be assumed to be present unless the narrative explicitly says otherwise.

CHUNK ID: {chunk.id}
CHUNK TEXT:
```
{chunk.raw_text}
```

Return ONLY a valid JSON object adhering strictly to the following schema:
```json
{{
  "chunk_id": "{chunk.id}",
  "present": [
    {{
      "name": "Character Name as in text",
      "status": "known OR new",
      "canonical_name": "Canonical Name if known, null if new",
      "aliases": ["alias1", "alias2"] // List any NEW aliases found in THIS chunk for known or new chars
    }}
    // ... more present characters
  ],
  "mentioned": [
    {{
      "name": "Character Name as in text",
      "status": "known OR new",
      "canonical_name": "Canonical Name if known, null if new",
      "aliases": ["alias1", "alias2"] // List any NEW aliases found in THIS chunk for known or new chars
    }}
    // ... more mentioned characters
  ]
}}
```

Guidelines:
- Analyze ONLY the CHUNK TEXT provided above.
- ONLY include true individual characters, not corporations, factions, roles, or groups.
- If a potential character is ambiguous, assess whether it's described with individual agency/thoughts/actions.
- Match names/titles/pronouns to the KNOWN CHARACTERS list where possible.
- If a character is NOT on the known list, mark status as "new" and provide entity_type.
- For "new" characters, list any names/nicknames/titles used for them in this chunk in their "aliases" field.
- Ensure the output is a single, valid JSON object and nothing else.
"""
    return prompt

def get_llm_structured_response(prompt: str, provider_instance: LLMProvider, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """Calls the LLM provider ensuring structured JSON output."""
    if not isinstance(provider_instance, OpenAIProvider):
        logger.warning(f"Attempting structured output with non-OpenAI provider ({provider_instance.provider_name}). This may be less reliable.")
        # Fallback: Just get standard completion and try parsing JSON later
        try:
            response = provider_instance.get_completion(prompt)
            try:
                # Attempt to parse the entire response content as JSON
                return json.loads(response.content.strip())
            except json.JSONDecodeError:
                logger.error(f"Failed to parse non-OpenAI response as JSON for chunk.")
                logger.debug(f"Raw response content: {response.content}")
                return None
        except Exception as e:
            logger.error(f"Error getting completion from {provider_instance.provider_name}: {e}")
            return None

    # --- OpenAI Specific Structured Output using 'responses' API ---
    oai_response = None # Initialize oai_response to handle potential errors
    structured_data = None
    try:
        # Identify reasoning models (heuristic)
        is_reasoning_model = provider_instance.model.startswith(("o1-", "o3-", "o4-"))

        # Check if the model supports the 'responses' API (heuristic: starts with 'o' or 'gpt-4')
        supports_responses_api = provider_instance.model.startswith("o") or provider_instance.model.startswith("gpt-4")

        if supports_responses_api:
            # Define the JSON schema for the expected output
            json_schema = {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string"},
                    "present": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "status": {"type": "string", "enum": ["known", "new"]},
                                "canonical_name": {"type": ["string", "null"]},
                                "aliases": {"type": "array", "items": {"type": "string"}}
                            },
                            "required": ["name", "status", "canonical_name", "aliases"],
                            "additionalProperties": False
                        }
                    },
                    "mentioned": {
                        "type": "array",
                        "items": {
                            # Same schema as 'present' items
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "status": {"type": "string", "enum": ["known", "new"]},
                                "canonical_name": {"type": ["string", "null"]},
                                "aliases": {"type": "array", "items": {"type": "string"}}
                            },
                            "required": ["name", "status", "canonical_name", "aliases"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["chunk_id", "present", "mentioned"],
                "additionalProperties": False
            }

            # Call the responses API for structured output
            input_messages = [{"role": "user", "content": prompt}]
            if provider_instance.system_prompt:
                input_messages.insert(0, {"role": "system", "content": provider_instance.system_prompt})

            structured_output_param = {
                "format": {
                    "type": "json_schema",
                    "name": "character_extraction",
                    "schema": json_schema,
                    "strict": True
                }
            }

            api_params = {
                "model": provider_instance.model,
                "input": input_messages,
                "text": structured_output_param
            }
            
            # Only add reasoning parameter for models that support it
            if is_reasoning_model:
                api_params["reasoning"] = {"effort": provider_instance.reasoning_effort or "medium"}
            
            # Only add temperature if it's NOT a reasoning model and temperature is set
            if not is_reasoning_model and provider_instance.temperature is not None:
                api_params["temperature"] = provider_instance.temperature

            if verbose:
                logger.debug(f"Sending structured request to OpenAI responses API. Params (excluding input): { {k:v for k,v in api_params.items() if k != 'input'} }")
            
            # Make the API call using the provider's client
            oai_response = provider_instance.client.responses.create(**api_params)

            # Check if the response contains structured data
            if hasattr(oai_response, 'output_text') and oai_response.output_text:
                try:
                    structured_data = json.loads(oai_response.output_text)
                    logger.info(f"Successfully received structured JSON output from OpenAI.")
                    # Optionally log reasoning if verbose and available
                    if verbose and hasattr(oai_response, 'reasoning') and oai_response.reasoning:
                        if hasattr(oai_response.reasoning, 'thinking') and oai_response.reasoning.thinking:
                            logger.debug(f"Reasoning/Thinking: {oai_response.reasoning.thinking[:500]}...")
                        elif hasattr(oai_response.reasoning, 'summary') and oai_response.reasoning.summary:
                            logger.debug(f"Reasoning Summary: {oai_response.reasoning.summary}")
                    return structured_data
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse structured JSON output from OpenAI: {e}")
                    logger.debug(f"Raw output_text: {oai_response.output_text}")
                    return None
            else:
                logger.error("OpenAI response did not contain expected output_text.")
                return None
        else:
            # Use standard chat completions with JSON mode for other models if available
            logger.info(f"Model {provider_instance.model} might not support responses API. Trying chat completions with JSON mode.")
            messages = [{"role": "user", "content": prompt}]
            if provider_instance.system_prompt:
                messages.insert(0, {"role": "system", "content": provider_instance.system_prompt})

            try:
                chat_response = provider_instance.client.chat.completions.create(
                    model=provider_instance.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=provider_instance.temperature if provider_instance.temperature is not None else 0.1,
                    max_tokens=provider_instance.max_tokens
                )
                response_content = chat_response.choices[0].message.content
                structured_data = json.loads(response_content)
                logger.info(f"Successfully received JSON object output via chat completions.")
                return structured_data
            except Exception as e:
                logger.error(f"Failed to get JSON object via chat completions: {e}")
                # Log response if possible
                if 'chat_response' in locals() and hasattr(chat_response, 'choices') and chat_response.choices:
                    logger.debug(f"Raw chat completion content: {chat_response.choices[0].message.content}")
                return None

    except Exception as e:
        logger.error(f"Error calling OpenAI API for structured response: {str(e)}")
        import traceback
        logger.debug(traceback.format_exc())
        return None
        
    # --- Token Usage Logging --- 
    # This now happens *after* the API call attempt and potential parsing
    if structured_data:
        try:
            # If it was a reasoning model AND we have the API response object with usage info
            if is_reasoning_model and oai_response and hasattr(oai_response, 'usage'):
                input_tokens = getattr(oai_response.usage, 'input_tokens', 0)
                output_tokens = getattr(oai_response.usage, 'output_tokens', 0)
                # Attempt to get reasoning tokens safely
                reasoning_tokens = getattr(oai_response.usage, 'reasoning_tokens', None) 
                if reasoning_tokens is not None:
                    logger.info(f"Token Usage (API): Input={input_tokens}, Output={output_tokens}, Reasoning={reasoning_tokens} for Chunk {structured_data.get('chunk_id', 'unknown')}")
                else:
                    # Fallback if reasoning_tokens attribute doesn't exist, log without it
                    logger.info(f"Token Usage (API): Input={input_tokens}, Output={output_tokens} for Chunk {structured_data.get('chunk_id', 'unknown')}")
                    logger.warning("Could not retrieve reasoning_tokens from API response usage.")
            else:
                # Otherwise, use estimation based on prompt and response content
                input_tokens_est = get_token_count(prompt, provider_instance.model)
                output_json_str = json.dumps(structured_data)
                output_tokens_est = get_token_count(output_json_str, provider_instance.model)
                logger.info(f"Token Usage (est.): Input={input_tokens_est}, Output={output_tokens_est} for Chunk {structured_data.get('chunk_id', 'unknown')}")
        except Exception as e:
            logger.warning(f"Could not log token count for chunk {structured_data.get('chunk_id', 'unknown')}: {e}")
            
    return structured_data # Return the parsed data

def add_new_character(db: Engine, character_data: Dict[str, Any], known_characters: Dict[str, KnownCharacter]) -> Optional[KnownCharacter]:
    """Adds a new character to the database and the known_characters dict."""
    char_name = character_data.get("name")
    if not char_name:
        logger.warning("Attempted to add new character with no name.")
        return None

    # Ensure minimal data
    aliases = character_data.get("aliases", [])
    if not isinstance(aliases, list): aliases = []
    # Ensure the main name is also in aliases if aliases list is empty, or add it if not present
    if not aliases:
        aliases = [char_name]
    elif char_name not in aliases:
        aliases.append(char_name)
        
    # Check if character (or alias) somehow already exists (e.g. race condition or LLM error)
    if char_name.lower() in known_characters or any(a.lower() in known_characters for a in aliases):
        logger.warning(f"Character '{char_name}' marked as new by LLM but already exists in known characters. Skipping add.")
        # Return the existing character object
        return known_characters.get(char_name.lower()) or \
               next((known_characters[a.lower()] for a in aliases if a.lower() in known_characters), None)

    logger.info(f"Adding new character to database: Name='{char_name}', Aliases={aliases}")
    try:
        with db.connect() as conn:
            trans = conn.begin()
            try:
                # Insert into characters table
                insert_query = text(f"""
                    INSERT INTO {CHARACTERS_TABLE} (name, aliases)
                    VALUES (:name, :aliases)
                    RETURNING id, name, aliases
                """)
                result = conn.execute(insert_query, {"name": char_name, "aliases": aliases}).fetchone()
                trans.commit()

                if result:
                    new_char = KnownCharacter(id=result[0], name=result[1], aliases=result[2] or [])
                    logger.info(f"Successfully added character '{new_char.name}' with ID {new_char.id}")
                    # Update the working dictionary
                    known_characters[new_char.name.lower()] = new_char
                    for alias in new_char.aliases:
                        known_characters[alias.lower()] = new_char
                    return new_char
                else:
                    logger.error(f"Failed to add character '{char_name}', INSERT returned no result.")
                    return None
            except Exception as inner_e:
                logger.error(f"Error during new character insertion transaction: {inner_e}")
                trans.rollback()
                return None
    except Exception as e:
        logger.error(f"Database connection error while adding new character '{char_name}': {str(e)}")
        return None

def add_aliases_to_character(db: Engine, character: KnownCharacter, new_aliases: List[str], known_characters: Dict[str, KnownCharacter]) -> bool:
    """Adds new aliases to an existing character in the database.
    
    Args:
        db: Database engine
        character: KnownCharacter object to update
        new_aliases: List of new aliases to add
        known_characters: Dictionary of known characters to update
        
    Returns:
        bool: Success or failure
    """
    if not new_aliases:
        return True  # Nothing to do
        
    # Get current aliases and add new ones
    current_aliases = list(character.aliases)  # Make a copy
    updated_aliases = current_aliases.copy()
    
    for alias in new_aliases:
        if alias not in updated_aliases:
            updated_aliases.append(alias)
    
    logger.info(f"Adding aliases {new_aliases} to character '{character.name}' (ID: {character.id})")
    
    try:
        with db.connect() as conn:
            trans = conn.begin()
            try:
                # Update character in database
                update_query = text(f"""
                    UPDATE {CHARACTERS_TABLE}
                    SET aliases = :aliases
                    WHERE id = :id
                    RETURNING id, name, aliases
                """)
                result = conn.execute(update_query, {
                    "aliases": updated_aliases,
                    "id": character.id
                }).fetchone()
                trans.commit()
                
                if result:
                    # Update the character object with new aliases
                    character.aliases = result[2] or []
                    
                    # Update the working dictionary - remove old entries first
                    for old_alias in current_aliases:
                        if old_alias.lower() in known_characters and known_characters[old_alias.lower()].id == character.id:
                            known_characters.pop(old_alias.lower(), None)
                    
                    # Add updated entries
                    known_characters[character.name.lower()] = character
                    for alias in character.aliases:
                        known_characters[alias.lower()] = character
                        
                    logger.info(f"Successfully updated aliases for '{character.name}'")
                    return True
                else:
                    logger.error(f"Failed to update aliases for character '{character.name}', UPDATE returned no result.")
                    return False
            except Exception as inner_e:
                logger.error(f"Error during character alias update transaction: {inner_e}")
                trans.rollback()
                return False
    except Exception as e:
        logger.error(f"Database connection error while updating aliases for character '{character.name}': {str(e)}")
        return False

def update_chunk_metadata(db: Engine, chunk_id: int, present_characters: List[Dict], mentioned_characters: List[Dict], dry_run: bool = False):
    """Updates the chunk_metadata.characters array for the given chunk."""
    all_characters_formatted = []
    processed_canonical_names = set() # Ensure canonical names aren't added twice if present AND mentioned

    for char_list, status_suffix in [(present_characters, "present"), (mentioned_characters, "mentioned")]:
        for char in char_list:
            # Use canonical name if available and valid, otherwise use the found name
            canonical_name = char.get("canonical_name")
            if not canonical_name or char.get("status") == "new":
                canonical_name = char.get("name") # Use the name found in text for new chars

            if not canonical_name:
                logger.warning(f"Character entry missing name and canonical_name in chunk {chunk_id}: {char}")
                continue

            formatted_entry = f"{canonical_name}:{status_suffix}"

            # Avoid adding the same canonical name twice with different statuses (prefer 'present')
            if canonical_name not in processed_canonical_names:
                all_characters_formatted.append(formatted_entry)
                processed_canonical_names.add(canonical_name)
            elif status_suffix == "present" and f"{canonical_name}:mentioned" in all_characters_formatted:
                # If already added as mentioned, upgrade to present
                all_characters_formatted.remove(f"{canonical_name}:mentioned")
                all_characters_formatted.append(formatted_entry)


    logger.info(f"Updating chunk {chunk_id} metadata with characters: {all_characters_formatted}")

    if dry_run:
        logger.info(f"[DRY RUN] Would update chunk {chunk_id} metadata characters to: {all_characters_formatted}")
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
                        SET characters = :characters
                        WHERE chunk_id = :chunk_id
                    """)
                    conn.execute(update_query, {"characters": all_characters_formatted, "chunk_id": chunk_id})
                else:
                    # Insert a new record if it doesn't exist
                    # We might need more default values depending on the table structure
                    logger.warning(f"No existing metadata found for chunk {chunk_id}. Inserting new record. Other fields might be default/null.")
                    insert_query = text(f"""
                        INSERT INTO {CHUNK_METADATA_TABLE} (chunk_id, characters)
                        VALUES (:chunk_id, :characters)
                        -- Add ON CONFLICT maybe? Depending on desired behavior if race condition
                    """)
                    conn.execute(insert_query, {"chunk_id": chunk_id, "characters": all_characters_formatted})

                trans.commit()
                logger.info(f"Successfully updated character metadata for chunk {chunk_id}.")
                return True
            except Exception as inner_e:
                logger.error(f"Error during chunk metadata update transaction for chunk {chunk_id}: {inner_e}")
                trans.rollback()
                return False
    except Exception as e:
        logger.error(f"Database connection error while updating metadata for chunk {chunk_id}: {str(e)}")
        return False

def process_chunk(
    db: Engine,
    chunk: NarrativeChunk,
    known_characters: Dict[str, KnownCharacter],
    provider_instance: LLMProvider,
    dry_run: bool = False,
    verbose: bool = False,
    auto: bool = False,
    blacklist: Set[str] = set()
) -> bool:
    """Processes a single narrative chunk to extract characters.
    
    Returns:
        bool: True if processing should continue, False if user requested stop.
    """
    slug_display = f" ({chunk.slug})" if chunk.slug else ""
    logger.info(f"--- Processing Chunk ID: {chunk.id}{slug_display} ---")
    user_requested_stop = False
    reviews_were_presented = False # Track if any review prompts happened

    # 1. Format known characters for the prompt
    known_chars_formatted = format_known_characters_for_prompt(known_characters)

    # 2. Build the prompt
    prompt = build_character_extraction_prompt(chunk, known_chars_formatted)
    if verbose:
        logger.debug(f"Prompt for chunk {chunk.id}:\n{prompt[:500]}...\n...\n{prompt[-500:]}")

    # 3. Call LLM for structured response
    try:
        llm_output = get_llm_structured_response(prompt, provider_instance, verbose)
    except Exception as e:
        logger.error(f"Unhandled exception during LLM call for chunk {chunk.id}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False # Indicate failure

    if not llm_output or not isinstance(llm_output, dict):
        logger.error(f"Failed to get valid structured response from LLM for chunk {chunk.id}.")
        return False # Indicate failure

    # Estimate token usage
    try:
        input_tokens = get_token_count(prompt, provider_instance.model)
        output_json_str = json.dumps(llm_output)
        output_tokens = get_token_count(output_json_str, provider_instance.model)
        logger.info(f"Token Usage (est.): Input={input_tokens}, Output={output_tokens} for Chunk {chunk.id}")
    except Exception as e:
        logger.warning(f"Could not estimate token count for chunk {chunk.id}: {e}")

    if verbose:
        logger.debug(f"Raw LLM Output (JSON): {json.dumps(llm_output, indent=2)}")

    # 4. Parse and Validate LLM Output
    present_chars = llm_output.get("present", [])
    mentioned_chars = llm_output.get("mentioned", [])

    if not isinstance(present_chars, list) or not isinstance(mentioned_chars, list):
        logger.error(f"LLM output for chunk {chunk.id} has invalid format (present/mentioned not lists).")
        return False

    # 5. Process Characters: Identify new, update known_characters dict
    all_extracted_chars = present_chars + mentioned_chars
    newly_added_chars = [] # Keep track of characters added in this chunk's processing
    potential_new_chars = [] # Collect new characters for user confirmation

    # First pass: process known characters and collect potential new ones
    for char_info in all_extracted_chars:
        if not isinstance(char_info, dict):
            logger.warning(f"Skipping invalid character entry in chunk {chunk.id}: {char_info}")
            continue
             
        status = char_info.get("status")
        char_name = char_info.get("name")

        if status == "new":
            # Check if it's *truly* new or if LLM missed an alias
            potential_match = known_characters.get(char_name.lower())
            if not potential_match and char_info.get("aliases"):
                potential_match = next((known_characters.get(a.lower()) for a in char_info["aliases"] if a.lower() in known_characters), None)

            if potential_match:
                logger.warning(f"LLM marked '{char_name}' as new, but matched existing character '{potential_match.name}'. Correcting.")
                char_info["status"] = "known"
                char_info["canonical_name"] = potential_match.name
                
                # Check for new aliases to add to existing character
                existing_aliases = set(alias.lower() for alias in potential_match.aliases)
                new_aliases = []
                
                # Add the name as a potential new alias if not in existing aliases
                if char_name.lower() not in existing_aliases:
                    new_aliases.append(char_name)
                
                # Check aliases from LLM
                for alias in char_info.get("aliases", []):
                    if alias.lower() not in existing_aliases:
                        new_aliases.append(alias)
                
                # Mark for alias confirmation if we found new aliases
                if new_aliases:
                    char_info["_new_aliases"] = new_aliases
                    char_info["_existing_character"] = potential_match
            else:
                # Collect potential new character for confirmation instead of adding immediately
                potential_new_chars.append(char_info)
                # Mark as pending confirmation
                char_info["_pending_confirmation"] = True

        elif status == "known":
            # Verify the canonical name provided by the LLM exists
            canonical_name = char_info.get("canonical_name")
            if not canonical_name or canonical_name.lower() not in known_characters:
                logger.warning(f"LLM provided unknown canonical_name '{canonical_name}' for known character '{char_name}' in chunk {chunk.id}. Attempting correction.")
                # Try to find match based on name found in text
                match = known_characters.get(char_name.lower())
                if match:
                    char_info["canonical_name"] = match.name
                    logger.info(f"Corrected canonical name to '{match.name}'.")
                else:
                    logger.error(f"Could not find match for 'known' character '{char_name}'. Treating as ambiguous.")
                    # Potentially skip this character entry? Or mark for review?
            else:
                # Get the character object for the canonical name
                character_obj = known_characters.get(canonical_name.lower())
                
                # Check for new aliases to add to existing character
                if character_obj:
                    existing_aliases = set(alias.lower() for alias in character_obj.aliases)
                    new_aliases = []
                    
                    # Add the name as a potential new alias if not already in existing aliases 
                    # and not the same as canonical name
                    if char_name.lower() != canonical_name.lower() and char_name.lower() not in existing_aliases:
                        new_aliases.append(char_name)
                    
                    # Check aliases from LLM
                    for alias in char_info.get("aliases", []):
                        if alias.lower() not in existing_aliases and alias.lower() != canonical_name.lower():
                            new_aliases.append(alias)
                    
                    # Mark for alias confirmation if we found new aliases
                    if new_aliases:
                        char_info["_new_aliases"] = new_aliases
                        char_info["_existing_character"] = character_obj

    # Collect characters that have new aliases
    chars_with_new_aliases = []
    for char_info in all_extracted_chars:
        if "_new_aliases" in char_info:
            chars_with_new_aliases.append(char_info)
    
    # User confirmation phase for new characters
    if potential_new_chars and not dry_run:
        logger.info(f"Found {len(potential_new_chars)} potential new characters in chunk {chunk.id}.")
        
        # Process each potential new character interactively
        for i in range(len(potential_new_chars) - 1, -1, -1): # Iterate backwards for safe removal
            char_info = potential_new_chars[i]
            char_name = char_info.get("name")

            # ---> Blacklist Check <--- 
            if char_name and char_name.lower() in blacklist:
                logger.info(f"Auto-rejecting blacklisted new character: '{char_name}'")
                if char_info in present_chars: present_chars.remove(char_info)
                if char_info in mentioned_chars: mentioned_chars.remove(char_info)
                potential_new_chars.pop(i) # Remove from review list
                continue # Skip to next potential new character
            
            # If we reach here, a review prompt will be needed (or auto-handled)
            reviews_were_presented = True
            
            aliases_str = ", ".join(char_info.get("aliases", []))
            aliases_display = f" (Aliases: {aliases_str})" if aliases_str else ""
            presence = "present in" if char_info in present_chars else "mentioned in"
            
            # Find context in the chunk text for this character
            context = "Context not found"
            search_name = char_name.lower()
            chunk_text = chunk.raw_text.lower()
            if search_name in chunk_text:
                name_pos = chunk_text.find(search_name)
                start_pos = max(0, name_pos - 150)
                end_pos = min(len(chunk_text), name_pos + len(search_name) + 150)
                # Try to start and end at word boundaries
                if start_pos > 0:
                    while start_pos > 0 and chunk_text[start_pos] != ' ' and chunk_text[start_pos] != '\n':
                        start_pos -= 1
                if end_pos < len(chunk_text):
                    while end_pos < len(chunk_text) and chunk_text[end_pos] != ' ' and chunk_text[end_pos] != '\n':
                        end_pos += 1
                
                context = "..." + chunk.raw_text[start_pos:end_pos].strip() + "..."
            
            try:
                # Display prompt with character info and context
                print(f"\nAdd new character '{char_name}'{aliases_display} {presence} chunk {chunk.id}?")
                print(f"Context: {context}")
                user_input = input("Confirm [1=Yes, 0=No]: ")
                
                if user_input == "0": # User rejected initial proposal
                    # Enhanced rejection flow with options
                    print("\nOptions:")
                    print("(1) discard")
                    print("(2) edit before adding as NEW")
                    print("(3) link to EXISTING character")
                    
                    action_choice = ""
                    while action_choice not in ["1", "2", "3"]:
                        action_choice = input("Choose option [1-3]: ")
                    
                    if action_choice == "1":
                        # Discard character
                        logger.info(f"Discarding character '{char_name}'.")
                        if char_info in present_chars: present_chars.remove(char_info)
                        if char_info in mentioned_chars: mentioned_chars.remove(char_info)
                    
                    elif action_choice == "2":
                        # Edit and potentially add as NEW
                        print("\nEditing character info...")
                        new_name = input(f"Character name [{char_name}]: ") or char_name
                        current_aliases = char_info.get("aliases", [])
                        print(f"Current aliases: {', '.join(current_aliases) if current_aliases else 'None'}")
                        new_aliases_input = input("New aliases (comma-separated) or enter to keep current: ")
                        if new_aliases_input.strip():
                            new_aliases = [a.strip() for a in new_aliases_input.split(",") if a.strip()]
                        else:
                            new_aliases = current_aliases
                            
                        # Retry confirmation (now runs regardless of alias input)
                        print(f"\nUpdated character: '{new_name}' with aliases: {', '.join(new_aliases) if new_aliases else 'None'}")
                        retry_confirm = input("Add this edited character as NEW? [1=Yes, 0=No]: ")
                        if retry_confirm != "0":
                            # User confirmed ADDITION of EDITED character
                            # Remove pending flag *before* attempting DB add
                            char_info.pop("_pending_confirmation", None)
                            
                            char_info["name"] = new_name # Update char_info with edits
                            char_info["aliases"] = new_aliases
                            new_char_obj = add_new_character(db, char_info, known_characters)
                            if new_char_obj:
                                char_info["canonical_name"] = new_char_obj.name # Update again with DB name
                                newly_added_chars.append(new_char_obj.name)
                            else:
                                logger.error(f"Failed to add edited new character '{new_name}'. Discarding entry.")
                                if char_info in present_chars: present_chars.remove(char_info)
                                if char_info in mentioned_chars: mentioned_chars.remove(char_info)
                        else:
                            # User did NOT confirm adding edited character -> discard
                            logger.info(f"Discarding edited character '{new_name}'.")
                            # Also remove pending flag if user explicitly discards here
                            char_info.pop("_pending_confirmation", None)
                            if char_info in present_chars: present_chars.remove(char_info)
                            if char_info in mentioned_chars: mentioned_chars.remove(char_info)

                    elif action_choice == "3":
                        # Link to EXISTING character
                        logger.info(f"Attempting to link '{char_name}' to an existing character.")
                        if not known_characters:
                             logger.warning("No known characters to link to. Discarding.")
                             if char_info in present_chars: present_chars.remove(char_info)
                             if char_info in mentioned_chars: mentioned_chars.remove(char_info)
                        else:
                             # Generate list sorted by ID for display and map ID to char
                             unique_chars_by_id = sorted(list(set(known_characters.values())), key=lambda c: c.id)
                             char_id_map = {char.id: char for char in unique_chars_by_id}
                             
                             print("\nLink to which existing character?")
                             for char in unique_chars_by_id:
                                 print(f"ID {char.id}: {char.name}")

                             link_choice_id = -1
                             valid_link = False
                             while True:
                                 try:
                                     link_choice_str = input(f"Enter character ID to link to: ")
                                     link_choice_id = int(link_choice_str)
                                     if link_choice_id in char_id_map:
                                         valid_link = True
                                         break
                                     else:
                                         print("Invalid character ID.")
                                 except ValueError:
                                     print("Invalid input. Please enter a number.")
                                 except EOFError: # Handle Ctrl+D etc.
                                     logger.warning("Input aborted during linking. Discarding.")
                                     break # Exit loop, valid_link remains False
                                     
                             if valid_link:
                                 selected_char = char_id_map[link_choice_id]
                                 logger.info(f"Linking '{char_name}' to existing character '{selected_char.name}' (ID: {selected_char.id}).")
                                 # Update char_info to represent the link
                                 char_info["status"] = "known"
                                 char_info["canonical_name"] = selected_char.name
                                 # Keep char_info["name"] as the name found in text
                                 char_info["aliases"] = [] # Clear aliases as they belonged to the rejected name
                                 char_info.pop("_pending_confirmation", None)
                             else:
                                 # Linking failed or was aborted
                                 logger.warning(f"Linking failed or aborted for '{char_name}'. Discarding entry.")
                                 if char_info in present_chars: present_chars.remove(char_info)
                                 if char_info in mentioned_chars: mentioned_chars.remove(char_info)
                                 
                elif user_input == "1": # User accepted initial proposal
                    # Add as NEW character
                    new_char_obj = add_new_character(db, char_info, known_characters)
                    if new_char_obj:
                        char_info["canonical_name"] = new_char_obj.name
                        newly_added_chars.append(new_char_obj.name)
                        char_info.pop("_pending_confirmation", None)
                    else:
                        logger.error(f"Failed to add new character '{char_name}'. Discarding entry.")
                        if char_info in present_chars: present_chars.remove(char_info)
                        if char_info in mentioned_chars: mentioned_chars.remove(char_info)
                else: # Invalid initial input
                    logger.warning("Invalid input. Discarding character proposal.")
                    if char_info in present_chars: present_chars.remove(char_info)
                    if char_info in mentioned_chars: mentioned_chars.remove(char_info)
                    
            except EOFError:
                logger.warning("EOF detected during character confirmation. Discarding character.")
                if char_info in present_chars: present_chars.remove(char_info)
                if char_info in mentioned_chars: mentioned_chars.remove(char_info)

    # User confirmation phase for new aliases
    if chars_with_new_aliases and not dry_run:
        logger.info(f"Found {len(chars_with_new_aliases)} characters with potential new aliases in chunk {chunk.id}.")
        
        # Process each potential new alias interactively
        for char_info in chars_with_new_aliases:
            # ---> Filter Aliases by Blacklist <--- 
            original_aliases = char_info.get("_new_aliases", [])
            valid_aliases = []
            for alias in original_aliases:
                if alias.lower() in blacklist:
                    logger.info(f"Auto-rejecting blacklisted alias '{alias}' for character '{char_info.get('_existing_character').name}'.")
                else:
                    valid_aliases.append(alias)
            
            # If no valid aliases remain after filtering, skip review for this character
            if not valid_aliases:
                logger.info(f"All proposed aliases for '{char_info.get('_existing_character').name}' were blacklisted. Skipping review.")
                # Clean up temporary flags even if skipped
                char_info.pop("_new_aliases", None)
                char_info.pop("_existing_character", None)
                continue # Skip to the next character with potential aliases
                
            # If we reach here, a review prompt will be needed (or auto-handled)
            reviews_were_presented = True
            
            # Update char_info with the filtered list for prompting
            char_info["_new_aliases"] = valid_aliases
            new_aliases = valid_aliases # Use the filtered list for processing below
            
            # Existing alias processing logic starts here, using the filtered `new_aliases`
            char_name = char_info.get("name")
            existing_character = char_info.get("_existing_character")
            
            if not existing_character or not new_aliases:
                continue
                
            existing_aliases_str = ", ".join(existing_character.aliases)
            new_aliases_str = ", ".join(new_aliases)
            
            # Find context for one of the new aliases
            context = "Context not found"
            for alias in new_aliases:
                search_alias = alias.lower()
                chunk_text = chunk.raw_text.lower()
                if search_alias in chunk_text:
                    alias_pos = chunk_text.find(search_alias)
                    start_pos = max(0, alias_pos - 50)
                    end_pos = min(len(chunk_text), alias_pos + len(search_alias) + 50)
                    # Try to start and end at word boundaries
                    if start_pos > 0:
                        while start_pos > 0 and chunk_text[start_pos] != ' ' and chunk_text[start_pos] != '\n':
                            start_pos -= 1
                    if end_pos < len(chunk_text):
                        while end_pos < len(chunk_text) and chunk_text[end_pos] != ' ' and chunk_text[end_pos] != '\n':
                            end_pos += 1
                    
                    context = "..." + chunk.raw_text[start_pos:end_pos].strip() + "..."
                    break
            
            presence = "present in" if char_info in present_chars else "mentioned in"
            
            try:
                # Display prompt with alias info and context
                print(f"\nAdd new aliases '{new_aliases_str}' to character '{existing_character.name}' {presence} chunk {chunk.id}?")
                print(f"Existing aliases: {existing_aliases_str}")
                print(f"Context: {context}")
                user_input = input("Confirm [1=Yes, 0=No]: ")
                
                if user_input == "0":
                    # Enhanced rejection flow with options
                    print("\nOptions:")
                    print("(1) discard")
                    print("(2) edit before processing")
                    
                    action_choice = ""
                    while action_choice not in ["1", "2"]:
                        action_choice = input("Choose option [1-2]: ")
                    
                    if action_choice == "1":
                        # Discard aliases
                        logger.info(f"Discarding aliases '{new_aliases_str}' for character '{existing_character.name}'.")
                        user_confirmed = False
                    else:  # action_choice == "2"
                        # Edit the aliases
                        print("\nEditing aliases:")
                        new_aliases_input = input(f"New aliases (comma-separated) [{new_aliases_str}]: ") or new_aliases_str
                        edited_aliases = [a.strip() for a in new_aliases_input.split(",") if a.strip()]
                        
                        # Retry confirmation
                        print(f"\nUpdated aliases: {', '.join(edited_aliases)}")
                        retry_confirm = input(f"Add these aliases to character '{existing_character.name}'? [1=Yes, 0=No]: ")
                        user_confirmed = retry_confirm != "0"
                        
                        if user_confirmed:
                            # Update the aliases list
                            new_aliases = edited_aliases
                else:
                    user_confirmed = True
            except EOFError:
                logger.warning("EOF detected during alias confirmation. Defaulting to not adding aliases.")
                user_confirmed = False
            
            if user_confirmed:
                # Add the confirmed new aliases
                success = add_aliases_to_character(db, existing_character, new_aliases, known_characters)
                if success:
                    logger.info(f"Successfully added aliases {new_aliases} to character '{existing_character.name}'")
                else:
                    logger.error(f"Failed to add aliases {new_aliases} to character '{existing_character.name}'")
            else:
                logger.info(f"Skipping addition of aliases {new_aliases} to character '{existing_character.name}' based on user input.")
                
            # Always remove the temporary flags
            char_info.pop("_new_aliases", None)
            char_info.pop("_existing_character", None)
    
    # Clean up any remaining _pending_confirmation flags and temporary fields
    for char_list in [present_chars, mentioned_chars]:
        # First pass: remove unconfirmed characters
        for i in range(len(char_list) - 1, -1, -1):
            if char_list[i].get("_pending_confirmation", False):
                logger.warning(f"Removing unconfirmed character '{char_list[i].get('name')}' from results.")
                char_list.pop(i)
        
        # Second pass: clean up remaining temporary fields (must be separate from the removal pass)
        for char_info in char_list:
            if "_new_aliases" in char_info:
                char_info.pop("_new_aliases", None)
            if "_existing_character" in char_info:
                char_info.pop("_existing_character", None)

    if newly_added_chars:
        logger.info(f"Added new characters in this chunk: {', '.join(newly_added_chars)}")

    # 6. Update Chunk Metadata in Database
    update_success = update_chunk_metadata(db, chunk.id, present_chars, mentioned_chars, dry_run)

    # 7. Ask user whether to continue AFTER reviews, if any reviews happened (and not dry_run)
    if reviews_were_presented: # Check if any reviews were actually shown
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
            
    # Return False if user requested stop, True otherwise (indicating continue)
    return not user_requested_stop


def main():
    """Main execution function."""
    args = parse_arguments()

    # Load blacklist from config
    blacklist = set()
    try:
        from nexus.config import load_settings_as_dict
        settings_data = load_settings_as_dict()
        raw_blacklist = settings_data.get("API Settings", {}).get("process_characters", {}).get("blacklist", [])
        if isinstance(raw_blacklist, list):
            blacklist = {item.lower() for item in raw_blacklist if isinstance(item, str)}
            logger.info(f"Loaded {len(blacklist)} items into character blacklist.")
        else:
            logger.warning("Blacklist in config is not a list. Using empty blacklist.")
    except Exception as e:
        logger.warning(f"Error loading character blacklist from config: {e}. Using empty blacklist.")

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
            logger.info("Loading known characters for prompt context...")
            known_characters_test = load_known_characters(db_engine_test)
            known_chars_formatted_test = format_known_characters_for_prompt(known_characters_test)
        except Exception as e:
            logger.error(f"Failed to load known characters: {e}")
            return 1

        try:
            logger.info("Fetching first processable chunk...")
            # Get the first chunk that would be processed by --all
            test_chunks = get_chunks_to_process(db_engine_test, overwrite=args.overwrite) 
            if not test_chunks:
                logger.info("No processable chunks found to generate test prompt.")
                return 0 # Exit normally, nothing to test prompt with
            
            first_chunk = test_chunks[0]
            logger.info(f"Using chunk {first_chunk.id} for test prompt.")

            logger.info("Building prompt...")
            test_prompt = build_character_extraction_prompt(first_chunk, known_chars_formatted_test)

            print("\n" + "="*20 + f" TEST PROMPT FOR CHUNK {first_chunk.id} " + "="*20)
            print(test_prompt)
            print("="* (40 + len(f" TEST PROMPT FOR CHUNK {first_chunk.id} ")) + "\n")
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

    # Load Known Characters
    known_characters = load_known_characters(db_engine)
    if not known_characters and not args.dry_run:
        logger.warning("No known characters loaded from the database. Processing will assume all characters are new initially.")
        # Allow continuing, first run might populate characters

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
        # Add reasoning effort only for OpenAI
        if args.provider.lower() == "openai":
            provider_kwargs["reasoning_effort"] = args.reasoning_effort or "medium" # Use arg or default medium

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

            # Perform TPM check before making the call
            # Estimate prompt size - requires building prompt first or estimating based on text + chars
            # Simple estimation: chunk text tokens + known chars tokens + template tokens
            temp_known_chars_str = format_known_characters_for_prompt(known_characters)
            temp_prompt = build_character_extraction_prompt(chunk, temp_known_chars_str)
            within_limit, input_tokens, total_tokens = llm_provider.check_tpm_limit(temp_prompt, estimated_output_tokens=500) # Estimate 500 output tokens for JSON

            if not within_limit:
                logger.error(f"TPM limit exceeded for chunk {chunk.id}. Estimated tokens: {total_tokens}. Skipping chunk.")
                error_count += 1
                # Potentially wait or break if limits are consistently hit
                rate_limit_wait = COOLDOWNS.get("rate_limit", 300)
                logger.warning(f"TPM Limit hit. Waiting {rate_limit_wait} seconds before trying next chunk...")
                time.sleep(rate_limit_wait)
                continue

            # Process the chunk
            try:
                should_continue = process_chunk(
                    db=db_engine,
                    chunk=chunk,
                    known_characters=known_characters, # Pass the mutable dict
                    provider_instance=llm_provider,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    auto=args.auto,
                    blacklist=blacklist # Pass the blacklist set
                )
                
                # Check if process_chunk returned False (user requested stop)
                if not should_continue:
                    logger.info(f"Stopping processing after chunk {chunk.id} as requested by user.")
                    processing_stopped = True # Signal to stop processing entirely
                    # The chunk was successfully processed up to the point of the stop request.
                    success_count += 1 
                    break # Exit the current batch loop
                else:
                    # If process_chunk returned True, assume DB update was successful (or dry run)
                    success_count += 1 
                    
            except Exception as e:
                logger.error(f"Unhandled exception processing chunk {chunk.id}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                error_count += 1

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

        # Prompt or delay before next batch (Restored, but only if not stopped and not auto)
        if i + batch_size < total_chunks and not args.dry_run and not processing_stopped:
            if not args.auto: # Only prompt between batches if NOT in auto mode
                try:
                    user_input = input("\nContinue with the next batch? [1=Yes, 0=No]: ")
                    if user_input == '0': # Check for '0' instead of 'n'
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
    logger.info("Character Extraction Complete")
    logger.info(f"Total Chunks Attempted: {processed_count}")
    logger.info(f"Successful Updates: {success_count}")
    logger.info(f"Errors Encountered: {error_count}")
    logger.info(f"Total Duration: {duration:.2f} seconds")
    logger.info(f"Mode: {'Dry Run' if args.dry_run else 'Database Write'}")
    logger.info("=" * 30)

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main()) 