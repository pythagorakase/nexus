#!/usr/bin/env python3
"""
NEXUS Character Psychology Profile Generator

This script generates comprehensive psychological profiles for characters in the narrative,
utilizing OpenAI's Structured Output mode with a detailed Pydantic schema.

Features:
- Analyzes narrative chunks with flexible filtering options
- Generates structured psychological profiles following a detailed template
- Uses OpenAI's Structured Output mode for reliable, schema-conformant responses
- Focuses on one character at a time for depth
- Stores results in PostgreSQL as JSONB
- Built on the api_openai.py library

Usage:
    python generate_psychology.py --character 1
    python generate_psychology.py --character 1 --model gpt-4o --overwrite
    python generate_psychology.py --character 1 --dry-run  # Shows prompt without making API call
    python generate_psychology.py --character 1 --import profile.json  # Import from file
    
    # Chunk filtering options
    python generate_psychology.py --character 1 --chunk last-200  # Only analyze the last 200 chunks
    python generate_psychology.py --character 1 --chunk 800-1000  # Only analyze chunks 800 through 1000
    python generate_psychology.py --character 1 --chunk all  # Explicitly analyze all chunks (default behavior)
"""

import os
import sys
import json
import time
import argparse
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import JSONB

try:
    from pydantic import BaseModel, Field
except ImportError:
    print("Error: Pydantic package is required. Please install with: pip install pydantic")
    sys.exit(1)

# Import OpenAI API utilities from api_openai.py
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from scripts.api_openai import (
    OpenAIProvider,
    get_default_llm_argument_parser,
    get_db_connection_string,
    setup_abort_handler,
    is_abort_requested,
    get_token_count,
    TPM_LIMITS
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("character_psychology.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.character_psychology")

# Define Pydantic model for the psychology profile
# Define Pydantic models for structured output
class SelfConceptModel(BaseModel):
    """Self-concept section of the psychology profile."""
    self_image: str = Field(description="How the character sees themselves")
    identity_evolution: str = Field(description="How their sense of identity has evolved through the narrative")
    public_persona: str = Field(description="How they present themselves to others")
    blind_spots: str = Field(description="Aspects of self they fail to recognize")

class BehaviorModel(BaseModel):
    """Behavior section of the psychology profile."""
    consistent_traits: str = Field(description="Reliable behavioral patterns visible across different contexts")
    contextual_variations: str = Field(description="How behavior shifts based on situation or company")
    stress_responses: str = Field(description="Typical reactions when under pressure")
    behavioral_contradictions: str = Field(description="Notable inconsistencies between stated values and actions")

class CognitiveFrameworkModel(BaseModel):
    """Cognitive framework section of the psychology profile."""
    decision_making_style: str = Field(description="Characteristic approach to making decisions")
    cognitive_biases: str = Field(description="Systematic errors in thinking that affect judgment")
    problem_solving_approach: str = Field(description="How they tackle obstacles")
    belief_systems: str = Field(description="Core convictions about self, others, and the world")

class TemperamentModel(BaseModel):
    """Temperament section of the psychology profile."""
    emotional_range: str = Field(description="Breadth and depth of emotional experience")
    regulation_strategies: str = Field(description="How they manage difficult emotions")
    emotional_triggers: str = Field(description="Specific stimuli that provoke strong emotional responses")
    expression_patterns: str = Field(description="How emotions are expressed or concealed")

class RelationalStyleModel(BaseModel):
    """Relational style section of the psychology profile."""
    attachment_pattern: str = Field(description="How they form and maintain relationships")
    trust_dynamics: str = Field(description="What determines who they trust and how deeply")
    power_orientation: str = Field(description="How they navigate authority and influence")
    conflict_responses: str = Field(description="Characteristic responses to interpersonal tension")

class DefenseMechanismsModel(BaseModel):
    """Defense mechanisms section of the psychology profile."""
    mature_defenses: str = Field(description="Higher-functioning protective strategies")
    neurotic_patterns: str = Field(description="Intermediate defenses")
    immature_reactions: str = Field(description="Primitive defenses used under severe stress")
    self_protection_strategies: str = Field(description="Overall approaches to psychological protection")

class CharacterArcModel(BaseModel):
    """Character arc section of the psychology profile."""
    psychological_journey: str = Field(description="Overall psychological development path")
    growth_patterns: str = Field(description="Areas of psychological growth")
    unresolved_tensions: str = Field(description="Ongoing internal conflicts")
    development_potential: str = Field(description="Future psychological development possibilities")

class SecretsModel(BaseModel):
    """Secrets section of the psychology profile."""
    internal_conflicts: str = Field(description="Competing drives, values, or desires")
    unspoken_desires: str = Field(description="What they want but don't articulate")
    concealed_information: str = Field(description="Facts the character knows but conceals")
    hidden_motivations: str = Field(description="Underlying drivers of behavior")

class ValidationEvidenceModel(BaseModel):
    """Validation evidence section of the psychology profile."""
    textual_support: str = Field(description="Direct evidence from narrative for psychological features")
    inferential_reasoning: str = Field(description="Logical connections supporting psychological analysis")
    contradictory_evidence: str = Field(description="Information that challenges psychological portrait")
    assessment_confidence: str = Field(description="Overall confidence in psychological assessment")

class PsychologyProfile(BaseModel):
    """Structured output model for character psychology profiles."""
    self_concept: SelfConceptModel = Field(
        description="Core identity and self-perception, including how they see themselves vs. how others see them"
    )
    behavior: BehaviorModel = Field(
        description="Observable patterns and actions, including consistent traits and contextual variations"
    )
    cognitive_framework: CognitiveFrameworkModel = Field(
        description="Thinking and decision-making patterns, including biases and problem-solving approaches"
    )
    temperament: TemperamentModel = Field(
        description="Emotional landscape, including range, regulation, triggers, and expression"
    )
    relational_style: RelationalStyleModel = Field(
        description="How they interact with others, including attachment patterns and trust dynamics"
    )
    defense_mechanisms: DefenseMechanismsModel = Field(
        description="How they protect themselves, including mature, neurotic, and immature defenses"
    )
    character_arc: CharacterArcModel = Field(
        description="Developmental trajectory, including psychological tensions and growth potential"
    )
    secrets: SecretsModel = Field(
        description="Withheld information and hidden dimensions, including internal conflicts and unspoken desires"
    )
    validation_evidence: ValidationEvidenceModel = Field(
        description="Supporting evidence and reasoning for the psychological assessment"
    )
    
    class Config:
        extra = "forbid"  # Equivalent to additionalProperties: false

def parse_arguments():
    """Parse command line arguments."""
    # Start with the default LLM parser from api_openai
    parser = get_default_llm_argument_parser()
    
    # Add script-specific arguments
    parser.add_argument("--character", type=int, required=True,
                       help="Character ID to analyze")
    parser.add_argument("--overwrite", action="store_true",
                       help="Overwrite existing profile if it exists")
    parser.add_argument("--output", type=str,
                       help="Output file path for the generated profile (for preview)")
    parser.add_argument("--import", dest="import_file", type=str,
                       help="Import profile from a JSON file instead of generating")
    parser.add_argument("--chunk", type=str,
                       help="Limit analysis to specific chunks. Format: 'start-end' (e.g., '800-1000'), 'last-N' (e.g., 'last-200'), or 'all'")
    
    args = parser.parse_args()
    return args

def create_database_tables(engine):
    """Create necessary database tables if they don't exist."""
    metadata = MetaData()
    
    # Define character_psychology table
    character_psychology = Table(
        'character_psychology',
        metadata,
        Column('character_id', Integer, ForeignKey('characters.id'), primary_key=True),
        Column('self_concept', JSONB),
        Column('behavior', JSONB),
        Column('cognitive_framework', JSONB),
        Column('temperament', JSONB),
        Column('relational_style', JSONB),
        Column('defense_mechanisms', JSONB),
        Column('character_arc', JSONB),
        Column('secrets', JSONB),
        Column('validation_evidence', JSONB),
        Column('created_at', TIMESTAMP, server_default=text('NOW()')),
        Column('updated_at', TIMESTAMP, server_default=text('NOW()'))
    )
    
    # Create tables if they don't exist
    metadata.create_all(engine)
    logger.info("Database tables verified/created.")
    return character_psychology

def fetch_character_info(engine, character_id: int) -> Optional[Dict[str, Any]]:
    """Fetch basic information for the specified character."""
    with engine.connect() as connection:
        # Query the specified character and check if it exists
        character_query = text("""
            SELECT c.id, c.name, 
                   COALESCE(ARRAY_AGG(DISTINCT ca.alias ORDER BY ca.alias) FILTER (WHERE ca.alias IS NOT NULL), ARRAY[]::text[]) AS aliases,
                   c.summary
            FROM characters c
            LEFT JOIN character_aliases ca ON c.id = ca.character_id
            WHERE c.id = :character_id
            GROUP BY c.id, c.name, c.summary
        """)
        character_result = connection.execute(character_query, {"character_id": character_id}).fetchone()
        
        if not character_result:
            return None
        
        # Convert to dictionary
        character_info = {
            "id": character_result[0],
            "name": character_result[1],
            "aliases": character_result[2] if character_result[2] else [],
            "summary": character_result[3] if len(character_result) > 3 and character_result[3] else ""
        }
        
        return character_info

def fetch_all_characters(engine) -> List[Dict[str, Any]]:
    """Fetch all characters from the database."""
    with engine.connect() as connection:
        # Query all characters
        character_query = text("""
            SELECT c.id, c.name, 
                   COALESCE(ARRAY_AGG(DISTINCT ca.alias ORDER BY ca.alias) FILTER (WHERE ca.alias IS NOT NULL), ARRAY[]::text[]) AS aliases,
                   c.summary
            FROM characters c
            LEFT JOIN character_aliases ca ON c.id = ca.character_id
            GROUP BY c.id, c.name, c.summary
            ORDER BY c.id
        """)
        character_results = connection.execute(character_query).fetchall()
        
        # Convert to list of dictionaries
        characters = []
        for row in character_results:
            characters.append({
                "id": row[0],
                "name": row[1],
                "aliases": row[2] if row[2] else [],
                "summary": row[3] if len(row) > 3 and row[3] else ""
            })
        
        return characters

def fetch_character_roster(engine) -> List[Dict[str, Any]]:
    """Fetch a roster of main characters (ids 1-10)."""
    with engine.connect() as connection:
        # Query main characters
        roster_query = text("""
            SELECT c.id, c.name, 
                   COALESCE(ARRAY_AGG(DISTINCT ca.alias ORDER BY ca.alias) FILTER (WHERE ca.alias IS NOT NULL), ARRAY[]::text[]) AS aliases,
                   c.summary
            FROM characters c
            LEFT JOIN character_aliases ca ON c.id = ca.character_id
            WHERE c.id BETWEEN 1 AND 10
            GROUP BY c.id, c.name, c.summary
            ORDER BY c.id
        """)
        roster_results = connection.execute(roster_query).fetchall()
        
        # Convert to list of dictionaries
        roster = []
        for row in roster_results:
            roster.append({
                "id": row[0],
                "name": row[1],
                "aliases": row[2] if row[2] else [],
                "summary": row[3] if len(row) > 3 and row[3] else ""
            })
        
        return roster

def update_character_summary(engine, character_id: int, summary: str) -> bool:
    """Update the summary field for a character in the database."""
    try:
        with engine.connect() as connection:
            update_query = text("""
                UPDATE characters
                SET summary = :summary, updated_at = NOW()
                WHERE id = :character_id
            """)
            connection.execute(update_query, {
                "character_id": character_id,
                "summary": summary
            })
            connection.commit()
            logger.info(f"Updated summary for character ID {character_id}")
            return True
    except Exception as e:
        logger.error(f"Error updating summary for character ID {character_id}: {str(e)}")
        return False

def fetch_narrative_corpus(engine, chunk_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch narrative chunks with metadata, optionally filtered by chunk range.
    
    Args:
        engine: SQLAlchemy engine
        chunk_filter: Optional filter string in format 'start-end', 'last-N', or 'all'
    
    Returns:
        List of dictionaries containing chunk data
    """
    with engine.connect() as connection:
        # Base query with joins
        base_query = """
            SELECT 
                nc.id, 
                nc.raw_text, 
                cm.season,
                cm.episode,
                wc.world_clock
            FROM 
                narrative_chunks nc
            LEFT JOIN 
                chunk_metadata cm ON nc.id = cm.chunk_id
            LEFT JOIN 
                world_clock_mv wc ON nc.id = wc.chunk_id
        """
        
        # Apply chunk filtering if specified
        where_clause = ""
        params = {}
        
        if chunk_filter:
            logger.info(f"Applying chunk filter: {chunk_filter}")
            
            # Check for 'last-N' pattern
            if chunk_filter.lower().startswith('last-'):
                try:
                    n = int(chunk_filter.split('-')[1])
                    # Subquery to get the last N chunk IDs by sequence
                    where_clause = """
                        WHERE nc.id IN (
                            SELECT id FROM narrative_chunks
                            ORDER BY id DESC
                            LIMIT :limit
                        )
                    """
                    params = {"limit": n}
                    logger.info(f"Filtering to last {n} chunks")
                except (ValueError, IndexError):
                    logger.warning(f"Invalid 'last-N' format: {chunk_filter}. Using all chunks.")
            
            # Check for 'start-end' pattern
            elif '-' in chunk_filter and not chunk_filter.lower() == 'all':
                try:
                    start, end = map(int, chunk_filter.split('-'))
                    where_clause = "WHERE nc.id BETWEEN :start AND :end"
                    params = {"start": start, "end": end}
                    logger.info(f"Filtering to chunks {start} through {end}")
                except (ValueError, IndexError):
                    logger.warning(f"Invalid range format: {chunk_filter}. Using all chunks.")
            
            # 'all' is explicit but doesn't need filtering
            elif chunk_filter.lower() == 'all':
                logger.info("Using all chunks as explicitly specified")
            
            else:
                logger.warning(f"Unrecognized chunk filter format: {chunk_filter}. Using all chunks.")
        
        # Complete the query with ordering
        order_clause = "ORDER BY cm.season, cm.episode, nc.id"
        
        # Assemble the full query
        full_query = f"{base_query} {where_clause} {order_clause}"
        
        # Execute query with parameters if any
        corpus_results = connection.execute(text(full_query), params).fetchall()
        
        # Convert to list of dictionaries
        corpus = []
        for row in corpus_results:
            corpus.append({
                "id": row[0],
                "raw_text": row[1],
                "season": row[2],
                "episode": row[3],
                "in_world_date": row[4] if row[4] else None  # Keep the dictionary key the same for compatibility
            })
        
        logger.info(f"Retrieved {len(corpus)} chunks after filtering")
        return corpus

def check_existing_profile(engine, character_id: int) -> bool:
    """Check if a psychological profile already exists for the character."""
    with engine.connect() as connection:
        query = text("""
            SELECT 1 FROM character_psychology
            WHERE character_id = :character_id
        """)
        result = connection.execute(query, {"character_id": character_id}).fetchone()
        return result is not None

def delete_existing_profile(engine, character_id: int) -> None:
    """Delete an existing psychological profile for the character."""
    with engine.connect() as connection:
        query = text("""
            DELETE FROM character_psychology
            WHERE character_id = :character_id
        """)
        connection.execute(query, {"character_id": character_id})
        connection.commit()
        logger.info(f"Deleted existing profile for character ID {character_id}")

def save_profile_to_database(engine, character_id: int, profile: Dict[str, Any]) -> None:
    """Save the psychological profile to the database."""
    with engine.connect() as connection:
        # SQL query for inserting the profile
        insert_query = text("""
            INSERT INTO character_psychology 
            (character_id, self_concept, behavior, cognitive_framework, temperament, 
             relational_style, defense_mechanisms, character_arc, secrets, validation_evidence, 
             created_at, updated_at)
            VALUES 
            (:character_id, :self_concept, :behavior, :cognitive_framework, :temperament, 
             :relational_style, :defense_mechanisms, :character_arc, :secrets, :validation_evidence, 
             NOW(), NOW())
        """)
        
        # Execute the query - ensure all sections are properly serialized to JSON
        connection.execute(insert_query, {
            "character_id": character_id,
            # Convert all sections to JSON strings
            "self_concept": json.dumps(profile["self_concept"]),
            "behavior": json.dumps(profile["behavior"]),
            "cognitive_framework": json.dumps(profile["cognitive_framework"]),
            "temperament": json.dumps(profile["temperament"]),
            "relational_style": json.dumps(profile["relational_style"]),
            "defense_mechanisms": json.dumps(profile["defense_mechanisms"]),
            "character_arc": json.dumps(profile["character_arc"]),
            "secrets": json.dumps(profile["secrets"]),
            "validation_evidence": json.dumps(profile["validation_evidence"])
        })
        connection.commit()
        logger.info(f"Saved psychological profile for character ID {character_id}")

def prepare_prompt(character_info: Dict[str, Any], 
                 character_roster: List[Dict[str, Any]], 
                 narrative_corpus: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    """Prepare the prompt for the OpenAI API."""
    # Load the prompt template using absolute path
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    prompt_path = os.path.join(script_dir, "prompts", "generate_psychology.json")
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"Prompt template not found at {prompt_path}")
    
    with open(prompt_path, "r") as f:
        prompt_template = json.load(f)
    
    # Format the main prompt with character name
    character_name = character_info["name"]
    main_instructions = prompt_template["main_instructions"].format(character_name=character_name)
    
    # Prepare the corpus context
    corpus_text = []
    
    # Mark the target character in the roster (without summaries to prevent bias)
    corpus_text.append("# MAIN CHARACTERS\n")
    for char in character_roster:
        marker = "→ TARGET CHARACTER ←" if char["id"] == character_info["id"] else ""
        alias_text = f", also known as: {', '.join(char['aliases'])}" if char["aliases"] else ""
        corpus_text.append(f"Character ID {char['id']}: {char['name']}{alias_text} {marker}")
    
    # Add the narrative chunks
    corpus_text.append("\n# FULL NARRATIVE\n")
    for chunk in narrative_corpus:
        season_ep = f"S{chunk['season']}E{chunk['episode']}" if chunk['season'] and chunk['episode'] else "Unknown"
        date_text = f" | Date: {chunk['in_world_date']}" if chunk['in_world_date'] else ""
        corpus_text.append(f"--- Chunk ID: {chunk['id']} | {season_ep}{date_text} ---\n{chunk['raw_text']}\n\n")
    
    # Combine the corpus text
    corpus_context = "\n".join(corpus_text)
    
    # Create the full prompt content to be repeated at beginning and end
    # This includes all sections from generate_psychology.json
    full_instructions = [
        f"SYSTEM PROMPT: {prompt_template['system_prompt']}",
        f"INSTRUCTION: {main_instructions}",
        f"OUTPUT STRUCTURE: {prompt_template['output_structure']}",
        f"SPECIAL INSTRUCTIONS: {prompt_template['special_instructions']}",
        f"FORMATTING GUIDELINES: {prompt_template['formatting_instructions']}",
        f"PROFILE SECTIONS:\n{json.dumps(prompt_template['profile_sections'], indent=2)}",
        f"EXAMPLE FORMAT:\n{json.dumps(prompt_template['examples'], indent=2)}"
    ]
    
    full_instructions_text = "\n\n".join(full_instructions)
    
    # Create the complete prompt with full instructions at beginning and end
    prompt_parts = [
        "=" * 80,
        "INSTRUCTIONS (CRITICAL - READ CAREFULLY)",
        "=" * 80,
        full_instructions_text,  # Full instructions at the beginning
        "\n\n" + "=" * 80 + "\n",
        "# CONTEXT AND DATA FOR ANALYSIS",
        corpus_context,          # Corpus data in the middle
        "\n\n" + "=" * 80 + "\n",
        "INSTRUCTIONS REPEATED (CRITICAL - READ CAREFULLY BEFORE RESPONDING)",  
        "=" * 80,
        full_instructions_text   # Full instructions repeated at the end
    ]
    
    full_prompt = "\n\n".join(prompt_parts)
    
    return full_prompt, prompt_template

def validate_profile(profile: Dict[str, Any], template: Dict[str, Any]) -> bool:
    """
    Validate the generated profile against the expected template structure.
    
    Note: This function is less critical now with the Pydantic model enforcing the schema,
    but we keep it for backward compatibility with imported profiles and as a double-check.
    """
    try:
        # Check that all required sections exist
        for section in template['profile_sections'].keys():
            if section not in profile:
                logger.error(f"Missing required section: {section}")
                return False
                
            # Check that all required subsections exist
            required_subsections = template['profile_sections'][section]['required_subsections']
            for subsection in required_subsections:
                if subsection not in profile[section]:
                    logger.error(f"Missing required subsection: {section}.{subsection}")
                    return False
        
        # If we're using imported JSON, try to validate it with our Pydantic model
        try:
            # This will raise ValidationError if the structure doesn't match
            PsychologyProfile(**profile)
            logger.info("Profile successfully validated against Pydantic schema")
        except Exception as e:
            logger.warning(f"Profile doesn't match Pydantic schema: {str(e)}")
            # We don't fail here, as the profile might be from an older format
        
        return True
    except Exception as e:
        logger.error(f"Error validating profile: {str(e)}")
        return False

def main():
    """Main entry point for the script."""
    # Parse command line arguments
    args = parse_arguments()
    
    # Set up abort handler
    setup_abort_handler()
    
    # Connect to database
    db_url = args.db_url or get_db_connection_string()
    engine = create_engine(db_url)
    
    try:
        # Create tables if they don't exist
        character_psychology_table = create_database_tables(engine)
        
        # We're in psychology profile generation mode
        # Check if profile exists and how to handle it
        if check_existing_profile(engine, args.character):
            if args.overwrite:
                logger.info(f"Overwriting existing profile for character ID {args.character}")
                delete_existing_profile(engine, args.character)
            else:
                logger.error(f"Profile already exists for character ID {args.character}. Use --overwrite to replace it.")
                return 1
        
        # If importing from file, skip the generation process
        if args.import_file:
            with open(args.import_file, "r") as f:
                profile = json.load(f)
                
            # Fetch character info for validation
            character_info = fetch_character_info(engine, args.character)
            if not character_info:
                logger.error(f"Character with ID {args.character} not found.")
                return 1
                
            # Validate the profile against the template
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            prompt_path = os.path.join(script_dir, "prompts", "generate_psychology.json")
            if os.path.exists(prompt_path):
                with open(prompt_path, "r") as f:
                    prompt_template = json.load(f)
                    
                if not validate_profile(profile, prompt_template):
                    logger.error("Imported profile is invalid. Please check the structure.")
                    return 1
            
            # Save to database if not a dry run
            if not args.dry_run:
                save_profile_to_database(engine, args.character, profile)
                logger.info(f"Imported profile saved for character ID {args.character}")
            else:
                logger.info("Dry run - profile not saved to database.")
                
            return 0
        
        # Fetch character information
        character_info = fetch_character_info(engine, args.character)
        if not character_info:
            logger.error(f"Character with ID {args.character} not found.")
            return 1
        
        logger.info(f"Generating psychological profile for character: {character_info['name']} (ID: {args.character})")
        
        # Fetch data for context
        logger.info("Fetching character roster...")
        character_roster = fetch_character_roster(engine)
        
        logger.info("Fetching narrative corpus...")
        if args.chunk:
            logger.info(f"Using chunk filter: {args.chunk}")
            narrative_corpus = fetch_narrative_corpus(engine, args.chunk)
        else:
            logger.info("No chunk filter specified, using all chunks")
            narrative_corpus = fetch_narrative_corpus(engine)
        
        logger.info(f"Retrieved {len(narrative_corpus)} narrative chunks for analysis.")
        
        # Prepare the prompt
        logger.info("Preparing prompt with context...")
        full_prompt, prompt_template = prepare_prompt(
            character_info, 
            character_roster, 
            narrative_corpus
        )
        
        # Count tokens
        prompt_tokens = get_token_count(full_prompt, args.model)
        logger.info(f"Prompt prepared with {prompt_tokens} tokens.")
        
        # Initialize the OpenAI provider
        provider = OpenAIProvider(
            api_key=args.api_key,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            system_prompt=None,  # System prompt is included in our full prompt
            reasoning_effort=args.effort if args.model.startswith("o") else None
        )
        
        # Check if prompt exceeds token limits from settings.json
        provider_name = "openai"
        max_input_tokens = TPM_LIMITS.get(provider_name, 128000)  # Use the limit from settings.json
        
        if prompt_tokens > max_input_tokens:
            logger.error(f"Prompt exceeds model's token limit ({prompt_tokens} tokens > {max_input_tokens}).")
            logger.error("Consider reducing context or using a different approach for very large narratives.")
            return 1
            
        # Create a sample of the full prompt for display in dry run mode
        # The code path is the same, we're just printing a sample
        if args.dry_run:
            # Split the prompt into lines
            prompt_lines = full_prompt.split('\n')
            total_lines = len(prompt_lines)
            
            # Find the start and end of the narrative chunk section
            narrative_start_idx = -1
            narrative_end_idx = -1
            
            for i, line in enumerate(prompt_lines):
                if "# FULL NARRATIVE" in line:
                    narrative_start_idx = i
                elif narrative_start_idx > 0 and "=" * 20 in line and i > narrative_start_idx + 10:  # Some separator after narrative section
                    narrative_end_idx = i
                    break
            
            # Create a sampled version for display
            if narrative_start_idx >= 0 and narrative_end_idx >= 0:
                # Show beginning (before narrative chunks)
                beginning = prompt_lines[:narrative_start_idx + 1]
                
                # Identify and show both first and last chunks
                chunk_count = 0
                chunk_start_indices = []
                chunk_end_indices = []
                
                # First identify all chunk boundaries
                for i in range(narrative_start_idx + 1, narrative_end_idx):
                    line = prompt_lines[i]
                    if "---" in line and ("Chunk ID:" in line or "S" in line and "E" in line):
                        chunk_start_indices.append(i)
                        chunk_count += 1
                        # If this is not the first chunk, mark the previous line as end of previous chunk
                        if chunk_count > 1:
                            # Look for previous blank line
                            for j in range(i-1, narrative_start_idx, -1):
                                if not prompt_lines[j].strip():
                                    chunk_end_indices.append(j)
                                    break
                
                # Mark the end of the last chunk
                if chunk_count > 0 and len(chunk_end_indices) < len(chunk_start_indices):
                    for j in range(narrative_end_idx-1, chunk_start_indices[-1], -1):
                        if not prompt_lines[j].strip():
                            chunk_end_indices.append(j)
                            break
                    if len(chunk_end_indices) < len(chunk_start_indices):
                        chunk_end_indices.append(narrative_end_idx-1)  # Use section end if no blank line found
                
                # Extract first chunk
                first_chunk_lines = []
                if chunk_count > 0:
                    first_start = chunk_start_indices[0]
                    first_end = chunk_end_indices[0] if chunk_count > 1 else narrative_end_idx
                    first_chunk_lines = prompt_lines[first_start:first_end+1]
                
                # Extract last chunk
                last_chunk_lines = []
                if chunk_count > 1:
                    last_start = chunk_start_indices[-1]
                    last_end = chunk_end_indices[-1] if len(chunk_end_indices) == len(chunk_start_indices) else narrative_end_idx
                    last_chunk_lines = prompt_lines[last_start:last_end+1]
                
                # Create a sample showing first chunk, omitted count, and last chunk
                omitted_count = max(0, chunk_count - 2)
                chunk_sample = first_chunk_lines + [f"\n[...{omitted_count} chunks omitted from preview...]\n"] + (last_chunk_lines if chunk_count > 1 else [])
                
                # Show ending (after narrative chunks)
                ending = prompt_lines[narrative_end_idx:]
                
                # Combine for preview
                sampled_prompt = beginning + chunk_sample + ending
                
                # Join back into text
                preview_text = '\n'.join(sampled_prompt)
            else:
                # Fallback if we can't find narrative section
                # Show first 20 and last 20 lines
                preview_text = "\n".join(prompt_lines[:20]) + "\n\n[...]\n\n" + "\n".join(prompt_lines[-20:])
            
            # Print the preview
            logger.info(f"DRY RUN - Would send prompt for {character_info['name']} ({prompt_tokens} tokens):")
            print("\n" + "=" * 80)
            print(f"PROMPT PREVIEW FOR {character_info['name'].upper()} (ID: {args.character})")
            print("=" * 80)
            print(preview_text)
            print("=" * 80 + "\n")
            
            logger.info("Dry run - no API call made, no profile saved to database.")
            return 0
            
        # Make the API call using structured output
        logger.info(f"Calling OpenAI API with model {args.model} using structured output...")
        start_time = time.time()
        try:
            # Use the structured completion method with our Pydantic model
            profile_structured, response = provider.get_structured_completion(full_prompt, PsychologyProfile)
            
            logger.info(f"API call completed in {time.time() - start_time:.2f} seconds.")
            logger.info(f"Response tokens: {response.input_tokens} input, {response.output_tokens} output")
            
            # Convert the Pydantic model to a dictionary for database storage
            profile = profile_structured.dict()
            
            # Log success with structured output
            logger.info("Successfully received and parsed structured output response")
            
            # No need to validate the profile structure as the Pydantic model enforces it
            # The API will fail with a clear error if the response doesn't match our schema
            
            # Output to file if requested
            if args.output:
                with open(args.output, "w") as f:
                    json.dump(profile, f, indent=2)
                logger.info(f"Profile saved to {args.output}")
            
            # Save to database
            save_profile_to_database(engine, args.character, profile)
            logger.info(f"Psychological profile saved for character ID {args.character}")
            
        except Exception as e:
            logger.error(f"Error during API call: {str(e)}")
            return 1
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 