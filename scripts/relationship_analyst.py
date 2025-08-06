#!/usr/bin/env python
"""
relationship_analyst.py - Generate bidirectional character relationship data

This script generates detailed relationship data between two characters based on
narrative chunks where both characters appear together. The script retrieves relevant
chunks from the database, sends them to OpenAI's API, and writes the structured 
response back to the character_relationships table.

The script follows these steps:
1. Retrieve character data for the specified character IDs
2. Find all narrative chunks where both characters appear
3. Assemble context and format API messages with the system prompt
4. Count tokens to determine which model to use
5. Call the OpenAI API with structured output mode
6. Save the resulting relationship data to the database

Usage:
    python relationship_analyst.py --c 1,2 [options]
    
Options:
    --c, --characters CHAR_IDS   Comma-separated IDs of the two characters
    --force                      Skip confirmation if relationships already exist
    --test                       Print API payload instead of making the API call
    --debug                      Show additional debugging information
    --quiet                      Suppress non-essential output
    --save-context               Save the context to a file for debugging
    --no-color                   Disable colored terminal output
"""

import argparse
import json
import os
import sys
import time
from typing import List, Tuple, Dict, Union, Literal, Optional, Any

import tiktoken
from openai import OpenAI
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import create_engine, text, MetaData, Table, Column, select, bindparam
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, TEXT, BIGINT, JSONB
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import tenacity
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Constants
DATABASE_URL = "postgresql://pythagor@localhost:5432/NEXUS"
PROMPT_PATH = "/Users/pythagor/nexus/prompts/relationship_analyst.json"
API_RESPONSE_DIR = "/Users/pythagor/nexus/results"

# ------------------- Pydantic Models for Structured Output ------------------- #

class _Cfg(BaseModel):
    """Base configuration class for all models."""
    model_config = ConfigDict(extra="forbid")  # -> "additionalProperties": false in schema


# ---------- 1. extra_data schemas for different relationship types ----------- #

class BondQualities(_Cfg):
    """Bond qualities for interpersonal relationships."""
    closeness: str = Field(description="How emotionally close they are (intimate, close, moderate, distant)")
    stability: str = Field(description="How stable the relationship is (rock-solid, stable, fluctuating, fragile)")


class CommunicationStyle(_Cfg):
    """Communication patterns between characters."""
    openness: str = Field(description="Degree of honesty (transparent, selective, guarded, deceptive)")
    frequency: str = Field(description="How often they communicate (constant, regular, occasional, rare)")


class InterpersonalBond(_Cfg):
    """For close personal relationships built on emotional connection."""
    schema_type: Literal["interpersonal_bond"] = Field(description="Always 'interpersonal_bond'")
    bond_qualities: BondQualities
    shared_experiences: List[str] = Field(description="Key shared moments/memories that define the relationship")
    points_of_tension: List[str] = Field(description="Recurring conflicts or unresolved issues")
    communication_style: CommunicationStyle


class AllianceParameters(_Cfg):
    """Parameters defining a cooperative alliance."""
    reliability: str = Field(description="How dependable they are to each other (unwavering, dependable, conditional, unpredictable)")
    formality: str = Field(description="Level of formality in the relationship (sworn, explicit, informal, implied)")
    durability: str = Field(description="Expected longevity (permanent, long-term, situational, tenuous)")


class ResourceSharing(_Cfg):
    """How resources are shared in a cooperative alliance."""
    information: str = Field(description="How information flows (full access, selective, minimal, none)")
    material: str = Field(description="How physical resources are shared (generous, reciprocal, calculated, reluctant)")
    contacts: str = Field(description="How networking resources are shared (open network, selective, guarded)")


class CooperativeAlliance(_Cfg):
    """For relationships based on mutual benefit and cooperation."""
    schema_type: Literal["cooperative_alliance"] = Field(description="Always 'cooperative_alliance'")
    alliance_parameters: AllianceParameters
    shared_goals: List[str] = Field(description="Objectives they work toward together")
    areas_of_expertise: str = Field(description="What skills/knowledge each contributes to the relationship")
    resource_sharing: ResourceSharing
    crisis_behavior: str = Field(description="How they respond when the other is in danger or difficulty")


class InfluencePatterns(_Cfg):
    """Patterns of influence in a power dynamic."""
    direction: str = Field(description="Flow of influence (one-way, mostly one-way, bidirectional)")
    intensity: str = Field(description="Strength of influence (dominant, significant, moderate, mild)")
    domain: str = Field(description="Specific areas where power is exercised")


class GrowthTrajectory(_Cfg):
    """How the power relationship is changing over time."""
    direction: str = Field(description="How the power dynamic is changing (increasing equality, maintaining, increasing imbalance)")
    catalysts: List[str] = Field(description="Events that cause shifts in the dynamic")


class Boundaries(_Cfg):
    """Boundaries in a power relationship."""
    clarity: str = Field(description="How clear boundaries are (explicit, understood, ambiguous, violated)")
    respect: str = Field(description="How well boundaries are respected (consistent, variable, poor)")


class PowerDynamic(_Cfg):
    """For relationships with significant power or influence differentials."""
    schema_type: Literal["power_dynamic"] = Field(description="Always 'power_dynamic'")
    influence_patterns: InfluencePatterns
    compliance_pattern: str = Field(description="How the influenced party responds (eager, willing, reluctant, resistant)")
    growth_trajectory: GrowthTrajectory
    boundaries: Boundaries


class EngagementPattern(_Cfg):
    """Patterns of engagement in a strategic relationship."""
    initiation: str = Field(description="Who typically reaches out (character1, character2, balanced, third-party)")
    terms: str = Field(description="Whose terms dictate interactions (character1's, character2's, negotiated, circumstantial)")
    predictability: str = Field(description="Pattern consistency (consistent, variable, erratic, calculated)")


class LeveragePoints(_Cfg):
    """Leverage in a calculated engagement."""
    character1_leverage: str = Field(description="What character1 has over character2")
    character2_leverage: str = Field(description="What character2 has over character1")


class ThirdParties(_Cfg):
    """Third parties involved in the relationship."""
    mutual_contacts: List[str] = Field(description="People connected to both characters")
    mediators: List[str] = Field(description="Those who help manage their relationship")


class Intelligence(_Cfg):
    """Information management in a calculated engagement."""
    information_sought: str = Field(description="What each wants to learn about the other")
    information_protected: str = Field(description="What each wants to hide from the other")


class CalculatedEngagement(_Cfg):
    """For strategic, cautious, or adversarial relationships."""
    schema_type: Literal["calculated_engagement"] = Field(description="Always 'calculated_engagement'")
    engagement_pattern: EngagementPattern
    leverage_points: LeveragePoints
    conflict_areas: List[str] = Field(description="Specific points of contention or disagreement")
    mutual_interests: List[str] = Field(description="Areas where interests align despite relationship tension")
    third_parties: ThirdParties
    intelligence: Intelligence


class Impressions(_Cfg):
    """Impressions in a liminal relationship."""
    first_impression: str = Field(description="Initial reaction to the other character")
    current_assessment: str = Field(description="Current thoughts about the other character")
    points_of_interest: List[str] = Field(description="What draws attention or curiosity")


class InteractionHistory(_Cfg):
    """History of interactions in a liminal relationship."""
    contexts: List[str] = Field(description="Situations where they've met")
    quality: str = Field(description="Overall nature of interactions (positive, mixed, negative, insufficient)")


class LiminalRelationship(_Cfg):
    """For undefined, transitional, or evolving relationships."""
    schema_type: Literal["liminal_relationship"] = Field(description="Always 'liminal_relationship'")
    impressions: Impressions
    interaction_history: InteractionHistory
    potential_directions: List[str] = Field(description="Possible ways the relationship might evolve")
    information_gaps: List[str] = Field(description="What's unknown but relevant to the relationship")
    intuition_notes: str = Field(description="Gut feelings or instincts about the relationship")


# Union type for extra_data field
ExtraData = Union[
    InterpersonalBond,
    CooperativeAlliance,
    PowerDynamic,
    CalculatedEngagement,
    LiminalRelationship,
]


# ---------- 2. Relationship type and emotional valence enums ----------------- #

RelationshipTypeEnum = Literal[
    "family", "romantic", "friend", "companion", "ally", "contact", 
    "pedagogical", "professional", "authority", "rival", "enemy", 
    "acquaintance", "stranger", "complex"
]

EmotionalValenceEnum = Literal[
    "+5|devoted", "+4|admiring", "+3|trusting", "+2|friendly", "+1|favorable",
    "0|neutral", "-1|wary", "-2|disapproving", "-3|resentful", "-4|hostile", "-5|hateful"
]


# ---------- 3. One direction of relationship --------------------------------- #

class RelationshipDirection(_Cfg):
    """Represents one direction of a character relationship."""
    character1_id: int = Field(description="ID of the character perceiving the relationship")
    character2_id: int = Field(description="ID of the character being perceived")
    relationship_type: RelationshipTypeEnum
    emotional_valence: EmotionalValenceEnum
    dynamic: str = Field(description="Rich, nuanced description of the current relationship dynamic")
    recent_events: str = Field(description="Recent meaningful interactions or developments")
    history: str = Field(description="Detailed timeline of how this relationship has evolved")
    extra_data: ExtraData


# ---------- 4. Bidirectional wrapper ----------------------------------------- #

class CharacterRelationshipPair(_Cfg):
    """Holds both DB rows for the (A,B) pair."""
    rel_1_to_2: RelationshipDirection = Field(description="Relationship from character 1's perspective")
    rel_2_to_1: RelationshipDirection = Field(description="Relationship from character 2's perspective")


# ---------- Token counting and model selection functions --------------------- #

def count_tokens(text: str) -> int:
    """
    Count the number of tokens in the given text.
    
    Args:
        text: The text to count tokens for
        
    Returns:
        Token count as integer
    """
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(text)
        return len(tokens)
    except Exception as e:
        print(f"Error counting tokens: {e}")
        # Fallback to rough character-based estimate if tokenization fails
        return len(text) // 4  # Rough approximation, 1 token ≈ 4 chars


def select_model_params(token_count: int) -> Tuple[str, Dict[str, Any]]:
    """
    Select the appropriate model and parameters based on token count.
    
    Args:
        token_count: Estimated tokens in the API request
        
    Returns:
        Tuple of (model_name, model_params) 
    """
    # Only two options as per specification
    if token_count > 200000:
        return "gpt-4.1", {"temperature": 0.7}
    else:
        return "o3", {"reasoning_effort": "high"}


def load_system_prompt() -> Dict[str, Any]:
    """
    Load the system prompt from the JSON file.
    
    Returns:
        System prompt as a dictionary
    """
    try:
        with open(PROMPT_PATH, 'r') as f:
            prompt_data = json.load(f)
            
        # Get the system_prompt - this should maintain the proper JSON structure
        # for display in test mode
        system_prompt = prompt_data.get('system_prompt', {})
        return system_prompt
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error loading system prompt: {e}")
        sys.exit(1)


def format_api_messages(char1_data: Dict, char2_data: Dict, chunks: List[Dict], system_prompt: Dict, season_summaries: Optional[str] = None) -> List[Dict]:
    """
    Format the API messages with system prompt and context.
    
    Args:
        char1_data: Data for the first character
        char2_data: Data for the second character
        chunks: List of narrative chunks where both characters appear
        system_prompt: System prompt dictionary
        season_summaries: Optional string with season summaries
        
    Returns:
        List of messages for the API call
    """
    # Convert system prompt dictionary to a string - format with proper indentation for readability
    # but keep the raw JSON structure for use in the API call
    system_content = json.dumps(system_prompt, indent=2)
    
    # Create user prompt with context
    chunk_texts = []
    for chunk in chunks:
        # Add chunk metadata as a header
        metadata = chunk.get('metadata', {})
        header = f"--- CHUNK ID: {chunk['id']} ---\n"
        
        if metadata:
            season = metadata.get('season')
            episode = metadata.get('episode')
            scene = metadata.get('scene')
            if all(v is not None for v in [season, episode, scene]):
                header += f"Season {season}, Episode {episode}, Scene {scene}\n"
        
        # Add the chunk text
        chunk_texts.append(f"{header}\n{chunk['raw_text']}\n")
    
    # Join all chunks together
    all_chunks_text = "\n\n".join(chunk_texts)
    
    # Create the base user content with character info
    user_content = f"""
{system_content}

Please analyze the relationship between these two characters:

CHARACTER 1:
ID: {char1_data.get('id')}
Name: {char1_data.get('name')}
Aliases: {', '.join(char1_data.get('aliases', [])) if char1_data.get('aliases') else 'None'}
Summary: {char1_data.get('summary', 'No summary available')}

CHARACTER 2:
ID: {char2_data.get('id')}
Name: {char2_data.get('name')}
Aliases: {', '.join(char2_data.get('aliases', [])) if char2_data.get('aliases') else 'None'}
Summary: {char2_data.get('summary', 'No summary available')}
"""
    
    # Add season summaries if provided
    if season_summaries:
        user_content += f"""
SEASON SUMMARIES FOR CONTEXT:
{season_summaries}
"""
    
    # Add narrative chunks and closing
    user_content += f"""
Below are all narrative chunks where both characters appear together:

{all_chunks_text}

Based on these interactions, generate detailed bidirectional relationship data for these characters.

{system_content}
"""
    
    # Create the full message list
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    
    return messages


@retry(
    retry=retry_if_exception_type((
        ConnectionError, 
        TimeoutError,
        json.JSONDecodeError
    )),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60)
)
def call_openai_api(messages: List[Dict], model: str, model_params: Dict, char1_id: int, char2_id: int) -> CharacterRelationshipPair:
    """
    Call the OpenAI API with retry logic.
    
    Args:
        messages: List of messages for the API call
        model: Model name to use
        model_params: Additional parameters for the model
        char1_id: ID of the first character
        char2_id: ID of the second character
        
    Returns:
        Parsed CharacterRelationshipPair result
    """
    client = OpenAI()
    
    try:
        # Get the schema for the response
        schema = CharacterRelationshipPair.model_json_schema()
        
        # Helper function to clean up schema by removing description fields next to $ref
        def prune_refs(node: object) -> None:
            """
            Recursively delete any keys that sit next to a `$ref`
            (OpenAI's validator allows *only* the `$ref` itself).
            """
            if isinstance(node, dict):
                if "$ref" in node:
                    for extra in list(node.keys() - {"$ref"}):
                        node.pop(extra, None)
                for v in node.values():
                    prune_refs(v)
            elif isinstance(node, list):
                for item in node:
                    prune_refs(item)
        
        # Clean up the schema
        prune_refs(schema)

        params = {
            "model": model,  # Use the model parameter passed to the function
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name":   "character_relationship_pair",
                    "schema": schema,
                    "strict": True                            # Keeping the strict parameter
                },
            },
            **model_params,
        }
        
        response = client.chat.completions.create(**params)
        
        # Parse the response
        content = response.choices[0].message.content
        
        # Save the response for reference
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        os.makedirs(API_RESPONSE_DIR, exist_ok=True)
        
        response_path = os.path.join(
            API_RESPONSE_DIR, 
            f"relationship_response_{timestamp}.json"
        )
        
        with open(response_path, 'w') as f:
            f.write(content)
        
        # Parse the content as JSON
        response_json = json.loads(content)
        
        # Convert to Pydantic model and validate character IDs
        relationship_pair = CharacterRelationshipPair.model_validate(response_json)
        
        # Validate and fix character IDs if needed
        if relationship_pair.rel_1_to_2.character1_id != char1_id or relationship_pair.rel_1_to_2.character2_id != char2_id:
            # Fix the relationship from char1 to char2
            relationship_pair.rel_1_to_2.character1_id = char1_id
            relationship_pair.rel_1_to_2.character2_id = char2_id
            
        if relationship_pair.rel_2_to_1.character1_id != char2_id or relationship_pair.rel_2_to_1.character2_id != char1_id:
            # Fix the relationship from char2 to char1
            relationship_pair.rel_2_to_1.character1_id = char2_id
            relationship_pair.rel_2_to_1.character2_id = char1_id
        
        return relationship_pair
    
    except json.JSONDecodeError as e:
        print(f"Error parsing API response: {e}")
        raise
    except Exception as e:
        print(f"API call failed: {e}")
        raise


def save_relationship_data(
    engine, 
    relationship_data: CharacterRelationshipPair
) -> Tuple[int, int]:
    """
    Save relationship data to the database in a transaction.
    
    Args:
        engine: SQLAlchemy engine
        relationship_data: Relationship data from the API
        
    Returns:
        Tuple of (character1_id, character2_id) - the character IDs as confirmation
    """
    # Get the relationship table
    relationship_table = Table(
        'character_relationships', 
        MetaData(), 
        autoload_with=engine
    )
    
    # Extract data from the relationship pair
    rel_1_to_2 = relationship_data.rel_1_to_2.model_dump()
    rel_2_to_1 = relationship_data.rel_2_to_1.model_dump()
    
    # Convert to proper database format
    row_1_to_2 = {
        'character1_id': rel_1_to_2['character1_id'],
        'character2_id': rel_1_to_2['character2_id'],
        'relationship_type': rel_1_to_2['relationship_type'],
        'emotional_valence': rel_1_to_2['emotional_valence'],
        'dynamic': rel_1_to_2['dynamic'],
        'recent_events': rel_1_to_2['recent_events'],
        'history': rel_1_to_2['history'],
        'extra_data': rel_1_to_2['extra_data'],  # Store as native JSON, not a string
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    row_2_to_1 = {
        'character1_id': rel_2_to_1['character1_id'],
        'character2_id': rel_2_to_1['character2_id'],
        'relationship_type': rel_2_to_1['relationship_type'],
        'emotional_valence': rel_2_to_1['emotional_valence'],
        'dynamic': rel_2_to_1['dynamic'],
        'recent_events': rel_2_to_1['recent_events'],
        'history': rel_2_to_1['history'],
        'extra_data': rel_2_to_1['extra_data'],  # Store as native JSON, not a string
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Save to database in a transaction
    with Session(engine) as session:
        try:
            # Start transaction
            with session.begin():
                # Check if relationships already exist and delete them
                stmt1 = select(relationship_table).where(
                    relationship_table.c.character1_id == row_1_to_2['character1_id'],
                    relationship_table.c.character2_id == row_1_to_2['character2_id']
                )
                result1 = session.execute(stmt1).first()
                
                stmt2 = select(relationship_table).where(
                    relationship_table.c.character1_id == row_2_to_1['character1_id'],
                    relationship_table.c.character2_id == row_2_to_1['character2_id']
                )
                result2 = session.execute(stmt2).first()
                
                # If relationships exist, delete them
                if result1:
                    delete_stmt1 = relationship_table.delete().where(
                        relationship_table.c.character1_id == row_1_to_2['character1_id'],
                        relationship_table.c.character2_id == row_1_to_2['character2_id']
                    )
                    session.execute(delete_stmt1)
                
                if result2:
                    delete_stmt2 = relationship_table.delete().where(
                        relationship_table.c.character1_id == row_2_to_1['character1_id'],
                        relationship_table.c.character2_id == row_2_to_1['character2_id']
                    )
                    session.execute(delete_stmt2)
                
                # Insert new relationships
                insert_stmt1 = relationship_table.insert().values(**row_1_to_2)
                insert_stmt2 = relationship_table.insert().values(**row_2_to_1)
                
                session.execute(insert_stmt1)
                session.execute(insert_stmt2)
                
                # No more relationship IDs - just return the character IDs as confirmation
                char1_id = row_1_to_2['character1_id'] 
                char2_id = row_2_to_1['character1_id']
                
                # Commit transaction (should happen automatically with context manager)
            
            print(f"Successfully saved relationship data for characters {char1_id} and {char2_id}")
            return char1_id, char2_id
            
        except SQLAlchemyError as e:
            # Transaction will be rolled back automatically
            print(f"Error saving relationship data: {e}")
            raise


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Generate relationship data between characters',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Required arguments
    parser.add_argument('--c', '--characters', required=True, type=str, 
                        help='Comma-separated IDs of the two characters')
    
    # Main options
    parser.add_argument('--force', action='store_true',
                       help='Skip confirmation if relationships already exist')
    parser.add_argument('--test', action='store_true',
                       help='Print API payload instead of making the API call')
    parser.add_argument('--season-summaries', action='store_true',
                       help='Include season summaries in the context for more background')
    
    # Debug options
    debug_group = parser.add_argument_group('Debug Options')
    debug_group.add_argument('--debug', action='store_true',
                       help='Show additional debugging information')
    debug_group.add_argument('--quiet', action='store_true',
                       help='Suppress non-essential output')
    debug_group.add_argument('--save-context', action='store_true',
                       help='Save the context to a file for debugging')
    debug_group.add_argument('--no-color', action='store_true',
                       help='Disable colored terminal output')
    
    args = parser.parse_args()
    
    # Validate characters argument
    try:
        char_ids = [int(char_id.strip()) for char_id in args.c.split(',')]
        if len(char_ids) != 2:
            raise ValueError("Exactly two character IDs must be provided")
        args.character_ids = char_ids
    except ValueError as e:
        parser.error(f"Invalid character IDs: {e}")
    
    # Set up terminal colors (if supported and not disabled)
    # This modifies args in place to add color-related attributes
    setup_terminal_colors(args)
    
    return args


def setup_terminal_colors(args):
    """Set up terminal colors for output."""
    # Only set up colors if not disabled and terminal supports them
    if args.no_color or not sys.stdout.isatty():
        # No colors
        args.GREEN = args.RED = args.YELLOW = args.BLUE = args.RESET = ""
    else:
        # ANSI color codes
        args.GREEN = "\033[32m"
        args.RED = "\033[31m"
        args.YELLOW = "\033[33m"
        args.BLUE = "\033[34m"
        args.RESET = "\033[0m"


def create_db_connection():
    """Create connection to the PostgreSQL database."""
    try:
        engine = create_engine(DATABASE_URL)
        connection = engine.connect()
        
        # Test connection
        result = connection.execute(text("SELECT 1"))
        connection.close()
        
        return engine
    except SQLAlchemyError as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def get_db_tables(engine):
    """Reflect and return the database tables needed for the script."""
    metadata = MetaData()
    
    # Reflect tables from the database
    tables = {}
    
    try:
        # Character relationships table
        tables['character_relationships'] = Table(
            'character_relationships', 
            metadata, 
            autoload_with=engine
        )
        
        # Characters table
        tables['characters'] = Table(
            'characters', 
            metadata, 
            autoload_with=engine
        )
        
        # Narrative chunks table
        tables['narrative_chunks'] = Table(
            'narrative_chunks', 
            metadata, 
            autoload_with=engine
        )
        
        # Chunk metadata table
        tables['chunk_metadata'] = Table(
            'chunk_metadata', 
            metadata, 
            autoload_with=engine
        )
        
        return tables
    except SQLAlchemyError as e:
        print(f"Error reflecting database tables: {e}")
        sys.exit(1)


def check_existing_relationships(engine, char1_id: int, char2_id: int) -> bool:
    """Check if relationships already exist between the characters in either direction."""
    with Session(engine) as session:
        # Check for existing relationship in either direction
        relationships_table = MetaData().tables.get('character_relationships')
        if not relationships_table:
            relationships_table = Table('character_relationships', MetaData(), autoload_with=engine)
        
        # Check first direction (char1 -> char2)
        stmt1 = select(relationships_table).where(
            relationships_table.c.character1_id == char1_id,
            relationships_table.c.character2_id == char2_id
        )
        
        # Check second direction (char2 -> char1)
        stmt2 = select(relationships_table).where(
            relationships_table.c.character1_id == char2_id,
            relationships_table.c.character2_id == char1_id
        )
        
        result1 = session.execute(stmt1).first()
        result2 = session.execute(stmt2).first()
        
        return bool(result1 or result2)


def get_character_data(engine, char_id: int) -> Optional[Dict]:
    """Retrieve character data from the database."""
    with Session(engine) as session:
        # Get character data with aliases from normalized table
        result = session.execute(text("""
            SELECT c.*, 
                   COALESCE(ARRAY_AGG(DISTINCT ca.alias ORDER BY ca.alias) FILTER (WHERE ca.alias IS NOT NULL), ARRAY[]::text[]) AS aliases
            FROM characters c
            LEFT JOIN character_aliases ca ON c.id = ca.character_id
            WHERE c.id = :char_id
            GROUP BY c.id
        """), {"char_id": char_id}).first()
        
        if not result:
            print(f"Error: Character with ID {char_id} not found.")
            return None
        
        # Convert row to dictionary
        character = dict(result._mapping)
        return character


def get_season_summaries(engine) -> str:
    """
    Retrieve season summaries from the database.
    
    Args:
        engine: SQLAlchemy engine
        
    Returns:
        Formatted string with complete season summaries
    """
    with Session(engine) as session:
        # Query all seasons with summaries
        result = session.execute(text("""
            SELECT id, jsonb_pretty(summary) 
            FROM seasons 
            WHERE summary IS NOT NULL
            ORDER BY id
        """)).fetchall()
        
        if not result:
            return "No season summaries available."
        
        summaries = []
        for row in result:
            season_id = row[0]
            # The second column is already a formatted JSON string from jsonb_pretty
            pretty_summary = row[1]
            
            # Format the summary with a header
            formatted_summary = f"SEASON {season_id} SUMMARY:\n{pretty_summary}"
            summaries.append(formatted_summary)
        
        return "\n\n" + "\n\n".join(summaries)


def get_shared_narrative_chunks(engine, char1_id: int, char2_id: int, debug: bool = False) -> List[Dict]:
    """
    Retrieve narrative chunks where both characters appear.
    
    This function finds all narrative chunks where both characters are present
    using the character_reference_view which already has this information.
    """
    with Session(engine) as session:
        # Get character names to use in debug messages
        char1 = get_character_data(engine, char1_id)
        char2 = get_character_data(engine, char2_id)
        
        if not char1 or not char2:
            print("Error: One or both characters not found.")
            return []
            
        char1_name = char1.get('name')
        char2_name = char2.get('name')
        
        if debug:
            print(f"Finding chunks shared between {char1_name} and {char2_name}...")
        
        # Find shared chunks using the normalized chunk_character_references table
        shared_chunks_query = text("""
            SELECT ARRAY(
                SELECT ccr1.chunk_id
                FROM chunk_character_references ccr1
                INNER JOIN chunk_character_references ccr2 
                    ON ccr1.chunk_id = ccr2.chunk_id
                WHERE ccr1.character_id = :char1_id 
                    AND ccr2.character_id = :char2_id
                    AND ccr1.reference = 'present'
                    AND ccr2.reference = 'present'
                ORDER BY ccr1.chunk_id
            ) as shared_chunks
        """)
        
        result = session.execute(
            shared_chunks_query, 
            {"char1_id": char1_id, "char2_id": char2_id}
        ).scalar()
        
        # Convert array result to list of chunk IDs
        chunk_ids = result if result else []
        
        if debug:
            print(f"Found {len(chunk_ids)} shared narrative chunks")
        
        # No shared chunks found
        if not chunk_ids:
            print(f"No shared narrative chunks found for {char1_name} and {char2_name}.")
            return []
            
        # Load only the necessary tables
        chunks_table = Table('narrative_chunks', MetaData(), autoload_with=engine)
        metadata_table = Table('chunk_metadata', MetaData(), autoload_with=engine)
        
        # Get the actual chunk content
        chunks_stmt = select(
            chunks_table.c.id,
            chunks_table.c.raw_text,
            chunks_table.c.created_at
        ).where(chunks_table.c.id.in_(chunk_ids))
        
        results = session.execute(chunks_stmt).fetchall()
        
        # Convert to list of dictionaries
        chunks = []
        for row in results:
            chunk = {'id': row[0], 'raw_text': row[1], 'created_at': row[2]}
            
            # Get minimal metadata for this chunk using direct SQL to avoid geometry warnings
            metadata_sql = text("""
                SELECT chunk_id, season, episode, scene 
                FROM chunk_metadata 
                WHERE chunk_id = :chunk_id
            """)
            
            metadata_row = session.execute(
                metadata_sql, 
                {"chunk_id": row[0]}
            ).first()
            
            if metadata_row:
                # Convert row tuple to dict with only the columns we need
                metadata = {col: getattr(metadata_row, col) for col in metadata_row._mapping.keys()}
                chunk['metadata'] = metadata
            
            chunks.append(chunk)
        
        # Sort chunks by metadata season, episode, scene if available
        chunks.sort(key=lambda x: (
            x.get('metadata', {}).get('season', 999),
            x.get('metadata', {}).get('episode', 999),
            x.get('metadata', {}).get('scene', 999)
        ))
        
        return chunks


def test_mode_output(
    messages: List[Dict],
    model: str,
    model_params: Dict,
    token_count: int,
    char1_name: str,
    char2_name: str
):
    """
    Generate the test mode output.
    
    This function prints the API payload that would be sent, without making the actual API call.
    It's designed to run the exact same code path as normal execution and only diverge
    at the checkpoint right before the API call.
    
    Args:
        messages: The messages that would be sent to the API
        model: The selected model
        model_params: The model parameters
        token_count: The token count
        char1_name: Name of character 1
        char2_name: Name of character 2
    """
    print("\n" + "=" * 80)
    print("TEST MODE - API CALL DETAILS")
    print("=" * 80)
    
    print(f"\nCharacters: {char1_name} and {char2_name}")
    
    print(f"\nToken count: {token_count}")
    print(f"Selected model: {model}")
    print(f"Model parameters: {model_params}")
    
    # Get the user message content for processing
    user_message = messages[1]['content']
    
    # Pretty-print the system prompt JSON (from system message)
    try:
        system_content_json = json.loads(messages[0]['content'])
        print("\nSYSTEM PROMPT:")
        print("-" * 40)
        print(json.dumps(system_content_json, indent=2))
    except json.JSONDecodeError:
        # Fallback to unformatted if not valid JSON
        print("\nSYSTEM PROMPT:")
        print("-" * 40)
        print(messages[0]['content'])
    
    # Print user prompt introduction
    print("\nUSER PROMPT WITH CONTEXT:")
    print("-" * 40)
    
    # Find the intro section - after the system prompt JSON and before the chunks
    intro_start = user_message.find("Please analyze the relationship between these two characters:")
    chunks_start = user_message.find("Below are all narrative chunks")
    
    if intro_start != -1 and chunks_start != -1:
        intro_section = user_message[intro_start:chunks_start]
        print(intro_section)
    else:
        # Fallback if markers not found
        print("Please analyze the relationship between these two characters:")
    
    # Extract and print all chunks
    chunks_start = user_message.find("Below are all narrative chunks")
    ending_marker = "Based on these interactions,"
    ending_idx = user_message.find(ending_marker)
    
    if chunks_start != -1 and ending_idx != -1:
        # Get the chunks section including the header
        chunks_section = user_message[chunks_start:ending_idx]
        print(chunks_section)
    else:
        # Fallback if markers not found
        print("\n[Could not locate narrative chunks in the message]")
    
    # Print the ending section with system prompt encore
    if ending_idx != -1:
        ending_text = user_message[ending_idx:]
        print(f"{ending_text}")
    else:
        print("\n[Could not locate ending section with system prompt encore]")
    
    print("\n" + "=" * 80)
    print("TEST MODE COMPLETE - NO API CALL MADE")
    print("=" * 80 + "\n")


def save_context_to_file(
    char1_data: Dict, 
    char2_data: Dict,
    chunks: List[Dict],
    messages: List[Dict],
    token_count: int,
    model: str,
    model_params: Dict
) -> str:
    """
    Save the context data to a file for debugging.
    
    Args:
        char1_data: Data for character 1
        char2_data: Data for character 2
        chunks: Narrative chunks used for context
        messages: Formatted API messages
        token_count: Estimated token count
        model: Selected model
        model_params: Model parameters

    Returns:
        Path to the saved file
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"relationship_context_{char1_data['id']}_{char2_data['id']}_{timestamp}.json"
    filepath = os.path.join(API_RESPONSE_DIR, filename)
    
    os.makedirs(API_RESPONSE_DIR, exist_ok=True)
    
    # Create a dictionary with all context data
    context_data = {
        "character1": char1_data,
        "character2": char2_data,
        "chunks": chunks,
        "messages": messages,
        "token_count": token_count,
        "model": model,
        "model_params": model_params,
    }
    
    with open(filepath, 'w') as f:
        json.dump(context_data, f, indent=2, default=str)
    
    return filepath


def main():
    """Main entry point for the script."""
    args = parse_arguments()
    
    if not args.quiet:
        print(f"{args.BLUE}Generating relationship data for characters: {args.character_ids}{args.RESET}")
    
    # Create database connection
    engine = create_db_connection()
    
    # Extract character IDs
    char1_id, char2_id = args.character_ids
    
    # Get character data
    char1_data = get_character_data(engine, char1_id)
    char2_data = get_character_data(engine, char2_id)
    
    if not char1_data or not char2_data:
        print(f"{args.RED}Error: One or both characters not found. Exiting.{args.RESET}")
        return 1
    
    if not args.quiet:
        print(f"Analyzing relationship between {args.GREEN}{char1_data['name']}{args.RESET} and {args.GREEN}{char2_data['name']}{args.RESET}")
    
    # Check for existing relationships
    if check_existing_relationships(engine, char1_id, char2_id) and not args.force:
        confirm = input(f"{args.YELLOW}Relationships already exist between {char1_data['name']} and {char2_data['name']}. Overwrite? (y/n): {args.RESET}")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            return 0
    
    # Get narrative chunks where both characters appear
    chunks = get_shared_narrative_chunks(engine, char1_id, char2_id, args.debug)
    
    if not chunks:
        print(f"{args.RED}No shared narrative chunks found for {char1_data['name']} and {char2_data['name']}.{args.RESET}")
        if not args.quiet:
            print("Characters must appear together in at least one narrative chunk to generate relationship data.")
        return 1
    
    if not args.quiet:
        print(f"Found {args.GREEN}{len(chunks)}{args.RESET} shared narrative chunks")
    
    # We no longer truncate chunks in test mode as we want to see all chunks
    # This allows us to verify they're being fetched and sorted correctly
    
    # Load the system prompt
    system_prompt = load_system_prompt()
    
    # Get season summaries if requested
    season_summaries = None
    if args.season_summaries:
        if not args.quiet:
            print(f"Retrieving season summaries for additional context...")
        season_summaries = get_season_summaries(engine)
    
    # Format API messages
    messages = format_api_messages(char1_data, char2_data, chunks, system_prompt, season_summaries)
    
    # Count tokens for all messages combined
    combined_text = ''.join(msg['content'] for msg in messages)
    token_count = count_tokens(combined_text)
    
    # Select model and parameters based on token count
    model, model_params = select_model_params(token_count)
    
    if args.debug:
        print(f"Token count: {args.BLUE}{token_count}{args.RESET}")
        print(f"Selected model: {args.BLUE}{model}{args.RESET}")
        print(f"Model parameters: {model_params}")
    
    # Save context for debugging if requested
    if args.save_context:
        context_file = save_context_to_file(
            char1_data, 
            char2_data, 
            chunks, 
            messages, 
            token_count, 
            model, 
            model_params
        )
        print(f"{args.BLUE}Context saved to: {context_file}{args.RESET}")
    
    # At this point we have followed the full API preparation path
    # We have gathered all character data, found shared narrative chunks, formatted
    # everything into messages, and prepared the API call
    
    # This is our checkpoint where test mode diverges
    if args.test:
        # Test mode - print API payload instead of making the call
        test_mode_output(
            messages,
            model,
            model_params,
            token_count,
            char1_data['name'],
            char2_data['name']
        )
        return 0
    
    # Regular mode - proceed with API call
    try:
        if not args.quiet:
            print(f"Calling OpenAI API with model {args.GREEN}{model}{args.RESET}...")
        
        relationship_data = call_openai_api(messages, model, model_params, char1_id, char2_id)
        
        if not args.quiet:
            print(f"{args.GREEN}API call successful. Saving relationship data to database...{args.RESET}")
        
        char_ids = save_relationship_data(engine, relationship_data)
        
        print(f"{args.GREEN}Successfully saved bidirectional relationship data between {char1_data['name']} and {char2_data['name']}.{args.RESET}")
        
        return 0
        
    except Exception as e:
        print(f"{args.RED}Error: {e}{args.RESET}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)