#!/usr/bin/env python
"""
Faction Relationship Analyst - Generates faction relationship data using OpenAI's o3 model

This script processes faction relationships by taking JSON context files as input
and generating structured relationship data for faction-to-faction and 
faction-to-character relationships in the NEXUS database.

Usage Examples:
    # Process faction-to-faction relationship
    python faction_relationship_analyst.py context_file.json --faction 2,3
    
    # Process faction-to-character relationship  
    python faction_relationship_analyst.py context_file.json --faction 2 --character 1
    
    # Test mode - show request without making API call
    python faction_relationship_analyst.py context_file.json --faction 2,3 --test
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from enum import Enum

import psycopg2
from psycopg2.extras import Json
from openai import OpenAI
from pydantic import BaseModel, Field, ConfigDict


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ────── Enums from DDL ─────────────────────────────────────────────────

class FactionRelationshipType(str, Enum):
    alliance = "alliance"
    trade_partners = "trade_partners"
    truce = "truce"
    vassalage = "vassalage"
    coalition = "coalition"
    war = "war"
    rivalry = "rivalry"
    ideological_enemy = "ideological_enemy"
    competitor = "competitor"
    splinter = "splinter"
    unknown = "unknown"
    shadow_partner = "shadow_partner"


class FactionMemberRole(str, Enum):
    leader = "leader"
    employee = "employee"
    member = "member"
    target = "target"
    informant = "informant"
    sympathizer = "sympathizer"
    defector = "defector"
    exile = "exile"
    insider_threat = "insider_threat"


# ────── Pydantic Models for Faction-to-Faction Relationships ─────────────

class RelationshipDynamics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    power_balance: str
    interaction: str
    trust_level: float = Field(..., ge=0.0, le=1.0)
    volatility: str
    public_perception: str


class ConflictSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    disputes: str
    grievances: str
    flashpoints: str
    economic_friction: str
    espionage: str


class CooperationSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    shared_interests: str
    joint_activities: str
    mutual_threats: str
    economic_exchange: str


class FutureScenarios(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    likely_evolution: str
    breaking_points: str
    narrative_potential: str


class HiddenLayers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    secrets: str
    contingencies: str


class ExtraDataFactionToFaction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    relationship_dynamics: RelationshipDynamics
    conflict: ConflictSection
    cooperation: CooperationSection
    future_scenarios: FutureScenarios
    hidden_layers: HiddenLayers


# ────── Pydantic Models for Faction-to-Character Relationships ───────────

class ConnectionNature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    origin_story: str
    current_dynamics: str
    key_events: str
    interaction_frequency: str


class FactionPerspective(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    value_assessment: str
    strategic_importance: str
    handling_approach: str
    known_intelligence: str
    desired_outcome: str


class CharacterPerspective(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    attitude: str
    personal_stakes: str
    constraints: str
    options: str


class OperationalDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    resources_involved: str
    active_operations: str
    contingency_plans: str
    success_metrics: str


class NarrativeThreads(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    unresolved_tensions: str
    potential_developments: str
    connected_relationships: str
    secrets: str


class ExtraDataFactionToCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    connection_nature: ConnectionNature
    faction_perspective: FactionPerspective
    character_perspective: CharacterPerspective
    operational_details: OperationalDetails
    narrative_threads: NarrativeThreads


# ────── Top-Level Response Models ─────────────────────────────────────────

class FactionRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    relationship_type: FactionRelationshipType
    current_status: str
    history: str
    extra_data: ExtraDataFactionToFaction


class FactionCharacterRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    role: FactionMemberRole
    current_status: str
    history: str
    public_knowledge: bool
    extra_data: ExtraDataFactionToCharacter


# ────── Database Functions ─────────────────────────────────────────────────

def get_db_connection():
    """Get database connection"""
    try:
        conn = psycopg2.connect(
            dbname="NEXUS",
            user="pythagor",
            host="localhost",
            port=5432
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        sys.exit(1)


def get_faction_roster(exclude_id: int = 1) -> List[Tuple[int, str]]:
    """Get all factions except the excluded one (default: NEXUS with id=1)"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, name 
            FROM factions 
            WHERE id != %s 
            ORDER BY id
        """, (exclude_id,))
        
        roster = cur.fetchall()
        cur.close()
        conn.close()
        
        return roster
    except Exception as e:
        logger.error(f"Error fetching faction roster: {e}")
        return []


def get_faction_data(faction_id: int) -> Optional[Dict[str, Any]]:
    """Get faction data excluding specified columns"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, name, summary, ideology, history, current_activity, 
                   hidden_agenda, territory, power_level, resources, extra_data
            FROM factions 
            WHERE id = %s
        """, (faction_id,))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            return {
                "id": result[0],
                "name": result[1],
                "summary": result[2],
                "ideology": result[3],
                "history": result[4],
                "current_activity": result[5],
                "hidden_agenda": result[6],
                "territory": result[7],
                "power_level": result[8],
                "resources": result[9],
                "extra_data": result[10]
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching faction data: {e}")
        return None


def get_character_data(character_id: int) -> Optional[Dict[str, Any]]:
    """Get character data excluding specified columns"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, name, aliases, backstory, current_status, personality, 
                   skills, goals, fears, psychology, extra_data
            FROM characters 
            WHERE id = %s
        """, (character_id,))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            return {
                "id": result[0],
                "name": result[1],
                "aliases": result[2],
                "backstory": result[3],
                "current_status": result[4],
                "personality": result[5],
                "skills": result[6],
                "goals": result[7],
                "fears": result[8],
                "psychology": result[9],
                "extra_data": result[10]
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching character data: {e}")
        return None


def format_faction_roster(roster: List[Tuple[int, str]]) -> str:
    """Format faction roster for inclusion in prompts"""
    if not roster:
        return "No factions available."
    
    formatted = ["FACTION ROSTER:"]
    for faction_id, faction_name in roster:
        formatted.append(f"- ID {faction_id}: {faction_name}")
    
    return "\n".join(formatted)


# ────── Prompt Building Functions ─────────────────────────────────────────

def load_prompt_template(filename: str) -> Dict[str, Any]:
    """Load prompt template from prompts directory"""
    prompt_path = Path(__file__).parent.parent / "prompts" / filename
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load prompt template {filename}: {e}")
        # Return a basic template if file not found
        return {
            "system_prompt": "You are an expert narrative designer creating faction relationships.",
            "main_instructions": []
        }


def create_faction_to_faction_messages(
    context: dict,
    faction1_data: dict,
    faction2_data: dict,
    roster: List[Tuple[int, str]]
) -> list:
    """Create messages for faction-to-faction relationship generation"""
    roster_text = format_faction_roster(roster)
    
    system_message = {
        "role": "system",
        "content": (
            "You are an expert narrative designer creating rich, nuanced faction relationships "
            "for the Night City Stories universe. Your task is to generate a detailed relationship "
            "analysis between two factions based on their characteristics and the provided context.\n\n"
            f"{roster_text}\n\n"
            "Generate a comprehensive faction-to-faction relationship that:\n"
            "1. Reflects the power dynamics and ideological tensions\n"
            "2. Includes specific historical events and conflicts\n"
            "3. Details both public and hidden aspects of the relationship\n"
            "4. Provides narrative hooks for future story development\n"
            "5. Considers economic, territorial, and strategic factors"
        )
    }
    
    user_message = {
        "role": "user",
        "content": (
            f"Generate the relationship between:\n\n"
            f"FACTION 1: {faction1_data['name']} (ID: {faction1_data['id']})\n"
            f"{json.dumps(faction1_data, indent=2)}\n\n"
            f"FACTION 2: {faction2_data['name']} (ID: {faction2_data['id']})\n"
            f"{json.dumps(faction2_data, indent=2)}\n\n"
            f"CONTEXT:\n{json.dumps(context, indent=2)}\n\n"
            f"Create a detailed relationship analysis focusing on how these two factions "
            f"interact, compete, cooperate, or conflict with each other."
        )
    }
    
    return [system_message, user_message]


def create_faction_to_character_messages(
    context: dict,
    faction_data: dict,
    character_data: dict,
    roster: List[Tuple[int, str]]
) -> list:
    """Create messages for faction-to-character relationship generation"""
    roster_text = format_faction_roster(roster)
    
    system_message = {
        "role": "system",
        "content": (
            "You are an expert narrative designer creating rich character-faction relationships "
            "for the Night City Stories universe. Your task is to generate a detailed relationship "
            "between a faction and a character based on their characteristics and the provided context.\n\n"
            f"{roster_text}\n\n"
            "Generate a comprehensive faction-character relationship that:\n"
            "1. Defines the character's role and standing within or against the faction\n"
            "2. Details the history of their involvement\n"
            "3. Explores both the faction's and character's perspectives\n"
            "4. Includes operational details and active plots\n"
            "5. Provides narrative potential for future developments"
        )
    }
    
    user_message = {
        "role": "user",
        "content": (
            f"Generate the relationship between:\n\n"
            f"FACTION: {faction_data['name']} (ID: {faction_data['id']})\n"
            f"{json.dumps(faction_data, indent=2)}\n\n"
            f"CHARACTER: {character_data['name']} (ID: {character_data['id']})\n"
            f"{json.dumps(character_data, indent=2)}\n\n"
            f"CONTEXT:\n{json.dumps(context, indent=2)}\n\n"
            f"Create a detailed relationship analysis focusing on how this character "
            f"relates to, works with, or opposes this faction."
        )
    }
    
    return [system_message, user_message]


# ────── API Call Functions ─────────────────────────────────────────────────

def call_openai_api_faction_to_faction(
    messages: list,
    test_mode: bool = False
) -> Optional[FactionRelationship]:
    """Call OpenAI API for faction-to-faction relationships"""
    if test_mode:
        print("TEST MODE - API Request for Faction-to-Faction:")
        print("-" * 80)
        for i, msg in enumerate(messages):
            print(f"\nMessage {i + 1} - Role: {msg['role']}")
            print("-" * 40)
            print(msg['content'])
        print("\n" + "-" * 80)
        print("TEST MODE COMPLETE - NO API CALL MADE")
        return None
    
    client = OpenAI()
    
    try:
        logger.info("Calling OpenAI API for faction-to-faction relationship...")
        
        completion = client.beta.chat.completions.parse(
            model="o3",
            messages=messages,
            reasoning_effort="high",
            response_format=FactionRelationship
        )
        
        result = completion.choices[0].message.parsed
        logger.info("Successfully received and parsed faction-to-faction response")
        return result
        
    except Exception as e:
        logger.error(f"API call failed: {e}")
        raise


def call_openai_api_faction_to_character(
    messages: list,
    test_mode: bool = False
) -> Optional[FactionCharacterRelationship]:
    """Call OpenAI API for faction-to-character relationships"""
    if test_mode:
        print("TEST MODE - API Request for Faction-to-Character:")
        print("-" * 80)
        for i, msg in enumerate(messages):
            print(f"\nMessage {i + 1} - Role: {msg['role']}")
            print("-" * 40)
            print(msg['content'])
        print("\n" + "-" * 80)
        print("TEST MODE COMPLETE - NO API CALL MADE")
        return None
    
    client = OpenAI()
    
    try:
        logger.info("Calling OpenAI API for faction-to-character relationship...")
        
        completion = client.beta.chat.completions.parse(
            model="o3",
            messages=messages,
            reasoning_effort="high",
            response_format=FactionCharacterRelationship
        )
        
        result = completion.choices[0].message.parsed
        logger.info("Successfully received and parsed faction-to-character response")
        return result
        
    except Exception as e:
        logger.error(f"API call failed: {e}")
        raise


# ────── Database Insert/Update Functions ───────────────────────────────────

def save_faction_to_faction_relationship(
    faction1_id: int,
    faction2_id: int,
    relationship_data: FactionRelationship,
    dry_run: bool = False
) -> bool:
    """Save faction-to-faction relationship to database"""
    # Ensure faction1_id < faction2_id per the check constraint
    if faction1_id > faction2_id:
        faction1_id, faction2_id = faction2_id, faction1_id
    
    if dry_run:
        logger.info(f"[DRY RUN] Would save faction relationship {faction1_id} <-> {faction2_id}")
        logger.info(f"Relationship type: {relationship_data.relationship_type}")
        return True
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if relationship already exists
        cur.execute("""
            SELECT 1 FROM faction_relationships 
            WHERE faction1_id = %s AND faction2_id = %s
        """, (faction1_id, faction2_id))
        
        exists = cur.fetchone() is not None
        
        if exists:
            # Update existing relationship
            cur.execute("""
                UPDATE faction_relationships SET
                    relationship_type = %s,
                    current_status = %s,
                    history = %s,
                    extra_data = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE faction1_id = %s AND faction2_id = %s
            """, (
                relationship_data.relationship_type.value,
                relationship_data.current_status,
                relationship_data.history,
                Json(relationship_data.extra_data.model_dump()),
                faction1_id,
                faction2_id
            ))
            logger.info(f"Updated existing faction relationship {faction1_id} <-> {faction2_id}")
        else:
            # Insert new relationship
            cur.execute("""
                INSERT INTO faction_relationships (
                    faction1_id, faction2_id, relationship_type, 
                    current_status, history, extra_data
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                faction1_id,
                faction2_id,
                relationship_data.relationship_type.value,
                relationship_data.current_status,
                relationship_data.history,
                Json(relationship_data.extra_data.model_dump())
            ))
            logger.info(f"Inserted new faction relationship {faction1_id} <-> {faction2_id}")
        
        conn.commit()
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Database error saving faction relationship: {e}")
        if conn:
            conn.rollback()
        return False


def save_faction_to_character_relationship(
    faction_id: int,
    character_id: int,
    relationship_data: FactionCharacterRelationship,
    dry_run: bool = False
) -> bool:
    """Save faction-to-character relationship to database"""
    if dry_run:
        logger.info(f"[DRY RUN] Would save faction-character relationship: "
                   f"Faction {faction_id} -> Character {character_id}")
        logger.info(f"Role: {relationship_data.role}")
        return True
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if relationship already exists
        cur.execute("""
            SELECT 1 FROM faction_character_relationships 
            WHERE faction_id = %s AND character_id = %s
        """, (faction_id, character_id))
        
        exists = cur.fetchone() is not None
        
        if exists:
            # Update existing relationship
            cur.execute("""
                UPDATE faction_character_relationships SET
                    role = %s,
                    current_status = %s,
                    history = %s,
                    public_knowledge = %s,
                    extra_data = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE faction_id = %s AND character_id = %s
            """, (
                relationship_data.role.value,
                relationship_data.current_status,
                relationship_data.history,
                relationship_data.public_knowledge,
                Json(relationship_data.extra_data.model_dump()),
                faction_id,
                character_id
            ))
            logger.info(f"Updated existing faction-character relationship: "
                       f"Faction {faction_id} -> Character {character_id}")
        else:
            # Insert new relationship
            cur.execute("""
                INSERT INTO faction_character_relationships (
                    faction_id, character_id, role, current_status, 
                    history, public_knowledge, extra_data
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                faction_id,
                character_id,
                relationship_data.role.value,
                relationship_data.current_status,
                relationship_data.history,
                relationship_data.public_knowledge,
                Json(relationship_data.extra_data.model_dump())
            ))
            logger.info(f"Inserted new faction-character relationship: "
                       f"Faction {faction_id} -> Character {character_id}")
        
        conn.commit()
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Database error saving faction-character relationship: {e}")
        if conn:
            conn.rollback()
        return False


# ────── Main Function ─────────────────────────────────────────────────────

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Generate faction relationship data using OpenAI o3"
    )
    parser.add_argument(
        "context_file",
        help="Path to the context JSON file"
    )
    parser.add_argument(
        "--faction",
        required=True,
        help="Faction ID(s). For faction-to-faction use comma-separated (e.g., 2,3)"
    )
    parser.add_argument(
        "--character",
        type=int,
        help="Character ID for faction-to-character relationships"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode - print API request without making the call"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform processing without writing to database"
    )
    
    args = parser.parse_args()
    
    # Load context file
    try:
        with open(args.context_file, 'r', encoding='utf-8') as f:
            context = json.load(f)
        logger.info(f"Loaded context from {args.context_file}")
    except Exception as e:
        logger.error(f"Failed to load context file: {e}")
        sys.exit(1)
    
    # Get faction roster
    roster = get_faction_roster()
    logger.info(f"Loaded faction roster with {len(roster)} factions")
    
    # Parse faction argument
    if args.character is not None:
        # Faction-to-character mode
        if ',' in args.faction:
            logger.error("Only single faction ID allowed when using --character")
            sys.exit(1)
        
        faction_id = int(args.faction)
        character_id = args.character
        
        # Get faction and character data
        faction_data = get_faction_data(faction_id)
        character_data = get_character_data(character_id)
        
        if not faction_data:
            logger.error(f"Faction with ID {faction_id} not found")
            sys.exit(1)
        
        if not character_data:
            logger.error(f"Character with ID {character_id} not found")
            sys.exit(1)
        
        logger.info(f"Processing faction-to-character relationship: "
                   f"{faction_data['name']} -> {character_data['name']}")
        
        # Create messages and call API
        messages = create_faction_to_character_messages(
            context, faction_data, character_data, roster
        )
        
        relationship_data = call_openai_api_faction_to_character(
            messages, test_mode=args.test
        )
        
        if not args.test and relationship_data:
            # Save to database
            success = save_faction_to_character_relationship(
                faction_id, character_id, relationship_data, dry_run=args.dry_run
            )
            
            if success:
                logger.info("Successfully processed faction-to-character relationship")
            else:
                logger.error("Failed to save faction-to-character relationship")
                sys.exit(1)
    
    else:
        # Faction-to-faction mode
        faction_ids = [int(fid.strip()) for fid in args.faction.split(',')]
        
        if len(faction_ids) != 2:
            logger.error("Exactly 2 faction IDs required for faction-to-faction relationships")
            sys.exit(1)
        
        faction1_id, faction2_id = faction_ids
        
        # Get faction data
        faction1_data = get_faction_data(faction1_id)
        faction2_data = get_faction_data(faction2_id)
        
        if not faction1_data:
            logger.error(f"Faction with ID {faction1_id} not found")
            sys.exit(1)
        
        if not faction2_data:
            logger.error(f"Faction with ID {faction2_id} not found")
            sys.exit(1)
        
        logger.info(f"Processing faction-to-faction relationship: "
                   f"{faction1_data['name']} <-> {faction2_data['name']}")
        
        # Create messages and call API
        messages = create_faction_to_faction_messages(
            context, faction1_data, faction2_data, roster
        )
        
        relationship_data = call_openai_api_faction_to_faction(
            messages, test_mode=args.test
        )
        
        if not args.test and relationship_data:
            # Save to database
            success = save_faction_to_faction_relationship(
                faction1_id, faction2_id, relationship_data, dry_run=args.dry_run
            )
            
            if success:
                logger.info("Successfully processed faction-to-faction relationship")
            else:
                logger.error("Failed to save faction-to-faction relationship")
                sys.exit(1)


if __name__ == "__main__":
    main()