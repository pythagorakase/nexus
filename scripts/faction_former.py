#!/usr/bin/env python
"""
Faction Former - Expands faction context packages into rich database entries

Takes manually curated faction context packages and uses OpenAI's o3 model
to expand them into detailed faction entries for the NEXUS database.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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


# ────── Pydantic Models for Faction Data ─────────────────────────────────────


class OrganizationalStructure(BaseModel):
    """Describes how the faction is organized internally"""
    
    model_config = ConfigDict(extra="forbid")
    
    hierarchy: str
    leadership_style: str
    ranks: List[str]
    subgroups: str
    recruitment: str
    size_estimate: str


class CulturalIdentity(BaseModel):
    """Defines the faction's culture and identity markers"""
    
    model_config = ConfigDict(extra="forbid")
    
    taboos: List[str]
    symbolism: str
    rituals: str
    slang: List[str]
    dress_code: str
    reputation: str


class OperationalPatterns(BaseModel):
    """How the faction operates in practice"""
    
    model_config = ConfigDict(extra="forbid")
    
    signature_tactics: str
    typical_operations: List[str]
    preferred_tech: str
    known_capabilities: List[str]
    known_weaknesses: List[str]


class ResourceNetwork(BaseModel):
    """The faction's economic and material resources"""
    
    model_config = ConfigDict(extra="forbid")
    
    income_sources: List[str]
    supply_chains: str
    safe_locations: List[str]
    information_network: str
    key_assets: List[str]
    economic_activities: List[str]


class RelationshipDynamics(BaseModel):
    """Internal and external relationship patterns"""
    
    model_config = ConfigDict(extra="forbid")
    
    internal_tensions: List[str]
    succession_plan: str
    loyalty_mechanisms: str
    corporate_view: str
    street_view: str
    rival_view: str


class NarrativeHooks(BaseModel):
    """Story potential and future development"""
    
    model_config = ConfigDict(extra="forbid")
    
    ongoing_plots: List[str]
    potential_conflicts: List[str]
    useful_services: List[str]
    dangerous_knowledge: List[str]
    future_trajectory: str


class HistoricalMarkers(BaseModel):
    """Key moments in the faction's history"""
    
    model_config = ConfigDict(extra="forbid")
    
    founding_myth: str
    greatest_victory: str
    worst_defeat: str
    turning_points: List[str]
    legendary_members: List[str]
    lost_resources: List[str]


class ExtraData(BaseModel):
    """Container for all detailed faction information"""
    
    model_config = ConfigDict(extra="forbid")
    
    organizational_structure: OrganizationalStructure
    cultural_identity: CulturalIdentity
    operational_patterns: OperationalPatterns
    resource_network: ResourceNetwork
    relationship_dynamics: RelationshipDynamics
    narrative_hooks: NarrativeHooks
    historical_markers: HistoricalMarkers


class FactionExpansion(BaseModel):
    """Complete faction data for database insertion"""
    
    model_config = ConfigDict(extra="forbid")
    
    summary: str
    ideology: str
    history: str
    current_activity: str
    hidden_agenda: str
    territory: str
    power_level: float = Field(..., ge=0.0, le=1.0)
    resources: str
    extra_data: ExtraData
    suggested_primary_location: Optional[str] = Field(
        None, 
        description="Suggested location name for primary_location field"
    )


# ────── Main Script Functions ─────────────────────────────────────────────────


def load_context_file(filepath: str) -> dict:
    """Load and validate the context JSON file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            context = json.load(f)
        logger.info(f"Loaded context file: {filepath}")
        return context
    except Exception as e:
        logger.error(f"Failed to load context file: {e}")
        sys.exit(1)


def load_system_prompt() -> dict:
    """Load the faction former prompt from prompts directory"""
    prompt_path = Path(__file__).parent.parent / "prompts" / "faction_former.json"
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_data = json.load(f)
        logger.info("Loaded faction former prompt")
        return prompt_data
    except Exception as e:
        logger.error(f"Failed to load prompt file: {e}")
        sys.exit(1)


def get_faction_info(faction_id: int) -> tuple:
    """Get faction ID and name from the database"""
    try:
        conn = psycopg2.connect(
            dbname="NEXUS",
            user="pythagor",
            host="localhost",
            port=5432
        )
        cur = conn.cursor()
        
        cur.execute("SELECT id, name FROM factions WHERE id = %s", (faction_id,))
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if result:
            return result[0], result[1]
        else:
            logger.error(f"Faction with ID {faction_id} not found in database")
            return None, None
            
    except Exception as e:
        logger.error(f"Database error: {e}")
        return None, None


def create_api_messages(context: dict, faction_id: int, faction_name: str, prompt_data: dict) -> list:
    """Create the messages array for the API call"""
    system_message = {
        "role": "system",
        "content": (
            f"{prompt_data['system_prompt']}\n\n"
            f"Main Instructions:\n" + 
            "\n".join(prompt_data['main_instructions']) + "\n\n" +
            f"Field Guidance:\n" + 
            json.dumps(prompt_data['field_guidance'], indent=2) + "\n\n" +
            f"Extra Data Structure:\n" +
            json.dumps(prompt_data['extra_data_structure'], indent=2)
        )
    }
    
    user_message = {
        "role": "user",
        "content": (
            f"Expand the faction '{faction_name}' (ID: {faction_id}) based on this context:\n\n"
            f"{json.dumps(context, indent=2)}\n\n"
            f"IMPORTANT: You are generating content specifically for '{faction_name}' (ID: {faction_id}). "
            f"While the context may mention other factions, focus exclusively on expanding '{faction_name}'. "
            f"Create a rich, detailed faction expansion that honors all narrative seeds "
            f"in the context while expanding them into a living, breathing organization."
        )
    }
    
    return [system_message, user_message]


def call_openai_api(messages: list, test_mode: bool = False) -> Optional[FactionExpansion]:
    """Call OpenAI API with structured output"""
    if test_mode:
        # In test mode, pretty-print the messages with properly formatted JSON
        print("TEST MODE - API Request Payload:")
        print("-" * 80)
        
        # Pretty-print each message
        for i, msg in enumerate(messages):
            if i > 0:
                print()  # Add blank line between messages
            
            print(f"Message {i + 1} - Role: {msg['role']}")
            print("-" * 40)
            
            # For user messages that contain embedded JSON (context), we need to parse and pretty-print
            if msg['role'] == 'user' and 'based on this context:' in msg['content']:
                # Split the content to extract the JSON part
                parts = msg['content'].split('\n\n')
                
                # Find the JSON part (between "based on this context:" and "Create a rich")
                json_start = -1
                json_end = -1
                for idx, part in enumerate(parts):
                    if part.strip().startswith('{'):
                        json_start = idx
                    if json_start >= 0 and part.strip().startswith('Create a rich'):
                        json_end = idx
                        break
                
                # Print the parts before JSON
                for idx in range(json_start):
                    print(parts[idx])
                    if idx < json_start - 1:
                        print()
                
                # Pretty-print the JSON context
                if json_start >= 0:
                    try:
                        context_json = json.loads(parts[json_start])
                        print(json.dumps(context_json, indent=2, ensure_ascii=False))
                    except json.JSONDecodeError:
                        # If parsing fails, just print as-is
                        print(parts[json_start])
                
                # Print the parts after JSON
                if json_end >= 0:
                    print()
                    for idx in range(json_end, len(parts)):
                        print(parts[idx])
            else:
                # For system messages or other content, just print as-is
                print(msg['content'])
        
        print("\n" + "-" * 80)
        print("TEST MODE COMPLETE - NO API CALL MADE")
        return None
    
    # Initialize OpenAI client (will use OPENAI_API_KEY environment variable)
    client = OpenAI()
    
    # Retry logic with exponential backoff
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.info(f"Calling OpenAI API (attempt {attempt + 1}/{max_retries})...")
            
            # Using the parse method for structured output
            completion = client.beta.chat.completions.parse(
                model="o3",
                messages=messages,
                reasoning_effort="high",
                response_format=FactionExpansion
            )
            
            faction_data = completion.choices[0].message.parsed
            logger.info("Successfully received and parsed API response")
            return faction_data
            
        except Exception as e:
            logger.error(f"API call failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                logger.info(f"Waiting {wait_time} seconds before retry...")
                import time
                time.sleep(wait_time)
            else:
                logger.error("Max retries exceeded")
                raise


def save_response(faction_name: str, faction_data: FactionExpansion):
    """Save the API response to a file"""
    output_dir = Path(__file__).parent.parent / "output" / "factions"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = faction_name.lower().replace(" ", "_")
    filename = output_dir / f"{safe_name}_{timestamp}.json"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(faction_data.model_dump(), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved response to: {filename}")
    except Exception as e:
        logger.error(f"Failed to save response: {e}")


def insert_faction_to_db(faction_name: str, faction_data: FactionExpansion):
    """Insert or update faction data in the PostgreSQL database"""
    try:
        # Connect to database
        conn = psycopg2.connect(
            dbname="NEXUS",
            user="pythagor",
            host="localhost",
            port=5432
        )
        cur = conn.cursor()
        
        # Check if faction already exists
        cur.execute("""
            SELECT id, summary, ideology, history, current_activity, 
                   hidden_agenda, territory, power_level, resources, extra_data
            FROM factions 
            WHERE name = %s
        """, (faction_name,))
        existing = cur.fetchone()
        
        if existing:
            faction_id = existing[0]
            # Check if any important fields have data
            has_data = any([
                existing[1],  # summary
                existing[2],  # ideology
                existing[3],  # history
                existing[4],  # current_activity
                existing[5],  # hidden_agenda
                existing[6],  # territory
                existing[8],  # resources
                existing[9]   # extra_data
            ])
            
            if has_data:
                # Prompt for confirmation
                logger.warning(f"Faction '{faction_name}' already has data in the database.")
                response = input("Do you want to overwrite the existing data? (y/n): ")
                if response.lower() != 'y':
                    logger.info("Skipping faction update.")
                    cur.close()
                    conn.close()
                    return
            
            # Update existing faction
            update_query = """
                UPDATE factions SET
                    summary = %s,
                    ideology = %s,
                    history = %s,
                    current_activity = %s,
                    hidden_agenda = %s,
                    territory = %s,
                    power_level = %s,
                    resources = %s,
                    extra_data = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """
            
            cur.execute(update_query, (
                faction_data.summary,
                faction_data.ideology,
                faction_data.history,
                faction_data.current_activity,
                faction_data.hidden_agenda,
                faction_data.territory,
                faction_data.power_level,
                faction_data.resources,
                Json(faction_data.extra_data.model_dump()),
                faction_id
            ))
            
            conn.commit()
            logger.info(f"Successfully updated faction '{faction_name}' (ID: {faction_id})")
        else:
            # Get the next available faction ID for new faction
            cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM factions")
            faction_id = cur.fetchone()[0]
            
            # Insert new faction
            insert_query = """
                INSERT INTO factions (
                    id, name, summary, ideology, history, current_activity,
                    hidden_agenda, territory, primary_location, power_level,
                    resources, extra_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """
            
            cur.execute(insert_query, (
                faction_id,
                faction_name,
                faction_data.summary,
                faction_data.ideology,
                faction_data.history,
                faction_data.current_activity,
                faction_data.hidden_agenda,
                faction_data.territory,
                None,  # primary_location set to null as specified
                faction_data.power_level,
                faction_data.resources,
                Json(faction_data.extra_data.model_dump())
            ))
            
            conn.commit()
            logger.info(f"Successfully inserted faction '{faction_name}' with ID {faction_id}")
        
        if faction_data.suggested_primary_location:
            logger.info(f"Suggested primary location: {faction_data.suggested_primary_location}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Database error: {e}")
        if conn:
            conn.rollback()
        raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Expand faction context packages into detailed database entries"
    )
    parser.add_argument(
        "context_file",
        help="Path to the context JSON file (e.g., context_sable_rats.json)"
    )
    parser.add_argument(
        "--faction",
        type=int,
        required=True,
        help="Faction ID to generate content for (e.g., 3 for Halcyon)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode - print API request without making the call"
    )
    
    args = parser.parse_args()
    
    # Load context and prompt
    context = load_context_file(args.context_file)
    prompt_data = load_system_prompt()
    
    # Get faction info from database
    faction_id, faction_name = get_faction_info(args.faction)
    
    if not faction_name:
        logger.error(f"Could not find faction with ID {args.faction} in database")
        sys.exit(1)
    
    logger.info(f"\nProcessing faction: {faction_name} (ID: {faction_id})")
    
    # Create API messages
    messages = create_api_messages(context, faction_id, faction_name, prompt_data)
    
    # Call API or print test payload
    faction_data = call_openai_api(messages, test_mode=args.test)
    
    if args.test:
        return
    
    if faction_data:
        # Save response
        save_response(faction_name, faction_data)
        
        # Insert to database
        insert_faction_to_db(faction_name, faction_data)
    else:
        logger.error(f"Failed to process faction: {faction_name}")


if __name__ == "__main__":
    main()