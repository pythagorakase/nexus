#!/usr/bin/env python3
"""
Faction Extraction Script for NEXUS

This script processes narrative chunks to identify which factions are referenced
in each chunk. It populates the chunk_faction_references table using OpenAI's
structured output mode.

Usage Examples:
    # Test mode - print API payload without making the call
    python process_factions.py --test --start 1

    # Process a single chunk
    python process_factions.py --start 5

    # Process a range of chunks
    python process_factions.py --start 10 --end 20

    # Process with custom reasoning effort
    python process_factions.py --start 1 --end 100 --effort high
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple, Annotated

import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI
from pydantic import BaseModel, Field, ConfigDict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ────── Pydantic Models for Structured Output ─────────────────────────────────

class FactionReference(BaseModel):
    """A single faction reference found in a chunk"""
    
    model_config = ConfigDict(extra="forbid")
    
    faction_id: int = Field(description="The ID of the faction from the roster")
    faction_name: str = Field(description="The name of the faction as found in text")
    confidence: float = Field(
        ge=0.0, 
        le=1.0,
        description="Confidence that this is a true faction reference (0.0-1.0)"
    )
    context: str = Field(description="Brief excerpt showing the faction reference in context")


class ChunkFactionAnalysis(BaseModel):
    """Complete analysis of factions referenced in a chunk"""
    
    model_config = ConfigDict(extra="forbid")
    
    chunk_id: int = Field(description="The ID of the analyzed chunk")
    faction_references: List[FactionReference] = Field(
        description="List of all faction references found in this chunk (empty array if none found)"
    )


# ────── Database Functions ────────────────────────────────────────────────────

def get_db_connection():
    """Connect to the PostgreSQL database"""
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


def get_faction_roster(conn) -> List[Dict[str, Any]]:
    """Get all factions except NEXUS (id=1) for the roster"""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, name, ideology, territory, power_level, summary
                FROM factions 
                WHERE id != 1
                ORDER BY id
            """)
            factions = cur.fetchall()
            logger.info(f"Loaded {len(factions)} factions for roster")
            return [dict(f) for f in factions]
    except Exception as e:
        logger.error(f"Error loading faction roster: {e}")
        return []


def get_chunks_to_process(conn, start_id: int, end_id: int) -> List[Dict[str, Any]]:
    """Get chunks in the specified range"""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT nc.id, nc.raw_text,
                       cm.season, cm.episode, cm.scene
                FROM narrative_chunks nc
                LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE nc.id BETWEEN %s AND %s
                ORDER BY nc.id
            """, (start_id, end_id))
            chunks = cur.fetchall()
            logger.info(f"Found {len(chunks)} chunks to process")
            return [dict(c) for c in chunks]
    except Exception as e:
        logger.error(f"Error fetching chunks: {e}")
        return []


def get_chunk_with_context(conn, chunk_id: int) -> Tuple[Dict, Optional[Dict], Optional[Dict]]:
    """Get a chunk with its leading and trailing context chunks"""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get the target chunk
            cur.execute("""
                SELECT nc.id, nc.raw_text,
                       cm.season, cm.episode, cm.scene
                FROM narrative_chunks nc
                LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE nc.id = %s
            """, (chunk_id,))
            target = cur.fetchone()
            
            if not target:
                return None, None, None
            
            # Get leading context (previous chunk)
            leading = None
            if chunk_id > 1:
                cur.execute("""
                    SELECT nc.id, nc.raw_text,
                           cm.season, cm.episode, cm.scene
                    FROM narrative_chunks nc
                    LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                    WHERE nc.id = %s
                """, (chunk_id - 1,))
                leading = cur.fetchone()
            
            # Get trailing context (next chunk)
            trailing = None
            cur.execute("""
                SELECT nc.id, nc.raw_text,
                       cm.season, cm.episode, cm.scene
                FROM narrative_chunks nc
                LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE nc.id = %s
            """, (chunk_id + 1,))
            trailing = cur.fetchone()
            
            return dict(target) if target else None, \
                   dict(leading) if leading else None, \
                   dict(trailing) if trailing else None
    except Exception as e:
        logger.error(f"Error fetching chunk with context: {e}")
        return None, None, None


def save_faction_references(conn, chunk_id: int, references: List[FactionReference], dry_run: bool = False):
    """Save faction references to the database"""
    if dry_run:
        logger.info(f"[DRY RUN] Would save {len(references)} faction references for chunk {chunk_id}")
        for ref in references:
            logger.info(f"  - Faction {ref.faction_id} ({ref.faction_name}), confidence: {ref.confidence}")
        return
    
    try:
        with conn.cursor() as cur:
            # Delete existing references for this chunk
            cur.execute("""
                DELETE FROM chunk_faction_references 
                WHERE chunk_id = %s
            """, (chunk_id,))
            
            # Insert new references
            for ref in references:
                cur.execute("""
                    INSERT INTO chunk_faction_references (chunk_id, faction_id)
                    VALUES (%s, %s)
                """, (chunk_id, ref.faction_id))
            
            conn.commit()
            logger.info(f"Saved {len(references)} faction references for chunk {chunk_id}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving faction references: {e}")
        raise


# ────── LLM Functions ─────────────────────────────────────────────────────────

def create_system_prompt(faction_roster: List[Dict[str, Any]]) -> str:
    """Create the system prompt with faction roster"""
    roster_text = "FACTION ROSTER:\n"
    for faction in faction_roster:
        roster_text += f"ID {faction['id']}: {faction['name']}"
        
        # Add summary if available
        if faction.get('summary'):
            roster_text += f" - {faction['summary']}"
        # Otherwise fall back to ideology if available
        elif faction.get('ideology'):
            # Truncate ideology to first 100 chars for brevity
            ideology = faction['ideology'][:100] + "..." if len(faction['ideology']) > 100 else faction['ideology']
            roster_text += f" - {ideology}"
        
        roster_text += "\n"
    
    system_prompt = f"""You are a faction identification specialist for a narrative intelligence system.

Your task is to identify which factions from the roster are referenced in narrative chunks.

{roster_text}

Guidelines:
1. ONLY identify factions that are explicitly mentioned or clearly referenced in the text
2. Do NOT infer faction presence from character affiliations unless the faction is named
3. Look for faction names, aliases, or clear descriptions that match roster entries
4. Provide confidence scores:
   - 1.0: Faction is explicitly named
   - 0.8-0.9: Clear reference but using alternate name/description
   - 0.6-0.7: Probable reference based on context
   - Below 0.6: Do not include
5. Include brief context excerpts showing where each faction is referenced
6. A faction may be referenced multiple times - report only the clearest reference
7. If NO factions are referenced in the chunk, return an empty array for faction_references
"""
    
    return system_prompt


def create_user_message(target_chunk: Dict, leading_chunk: Optional[Dict], trailing_chunk: Optional[Dict]) -> str:
    """Create the user message with chunk context"""
    message = "Analyze the TARGET CHUNK to identify which factions from the roster are referenced.\n\n"
    
    if leading_chunk:
        message += f"LEADING CONTEXT (Chunk {leading_chunk['id']}):\n"
        message += f"{leading_chunk['raw_text']}\n\n"
    
    message += f"TARGET CHUNK (Chunk {target_chunk['id']}):\n"
    message += f"{target_chunk['raw_text']}\n\n"
    
    if trailing_chunk:
        message += f"TRAILING CONTEXT (Chunk {trailing_chunk['id']}):\n"
        message += f"{trailing_chunk['raw_text']}\n\n"
    
    message += "Identify all factions referenced in the TARGET CHUNK ONLY. The context chunks are provided for reference but should not be analyzed for faction presence."
    
    return message


def call_openai_api(
    system_prompt: str, 
    user_message: str, 
    model: str = "o3",
    reasoning_effort: Optional[str] = None,
    test_mode: bool = False
) -> Optional[ChunkFactionAnalysis]:
    """Call OpenAI API with structured output"""
    
    if test_mode:
        print("\n" + "="*80)
        print("TEST MODE - API Request Details")
        print("="*80)
        print(f"\nModel: {model}")
        if reasoning_effort:
            print(f"Reasoning effort: {reasoning_effort}")
        print("\nMessages:")
        print("-"*40)
        print("System Message:")
        print(system_prompt)
        print("-"*40)
        print("User Message:")
        print(user_message)
        print("-"*40)
        print("\nResponse Format:")
        print(json.dumps(ChunkFactionAnalysis.model_json_schema(), indent=2))
        print("\n" + "="*80)
        print("TEST MODE COMPLETE - NO API CALL MADE")
        print("="*80)
        return None
    
    client = OpenAI()
    
    try:
        # Build the parameters
        params = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "response_format": ChunkFactionAnalysis
        }
        
        # Only add reasoning_effort if specified
        if reasoning_effort:
            params["reasoning_effort"] = reasoning_effort
        
        logger.info(f"Calling OpenAI API with model {model}...")
        
        # Use the parse method for structured output
        completion = client.beta.chat.completions.parse(**params)
        
        result = completion.choices[0].message.parsed
        logger.info(f"Successfully received API response for chunk {result.chunk_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"API call failed: {e}")
        raise


# ────── Main Processing Function ──────────────────────────────────────────────

def process_chunks(
    conn,
    start_id: int,
    end_id: int,
    model: str = "o3",
    reasoning_effort: Optional[str] = None,
    test_mode: bool = False,
    dry_run: bool = False
):
    """Process chunks in the specified range"""
    
    # Get faction roster
    faction_roster = get_faction_roster(conn)
    if not faction_roster:
        logger.error("No factions found in roster")
        return
    
    system_prompt = create_system_prompt(faction_roster)
    
    # Process each chunk
    for chunk_id in range(start_id, end_id + 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing chunk {chunk_id}")
        
        # Get chunk with context
        target, leading, trailing = get_chunk_with_context(conn, chunk_id)
        
        if not target:
            logger.warning(f"Chunk {chunk_id} not found, skipping")
            continue
        
        # Create user message
        user_message = create_user_message(target, leading, trailing)
        
        # Call API
        try:
            result = call_openai_api(
                system_prompt=system_prompt,
                user_message=user_message,
                model=model,
                reasoning_effort=reasoning_effort,
                test_mode=test_mode
            )
            
            if test_mode:
                # In test mode, only process the first chunk
                break
            
            if result:
                # Save results
                save_faction_references(
                    conn=conn,
                    chunk_id=chunk_id,
                    references=result.faction_references,
                    dry_run=dry_run
                )
                
                # Log summary
                if result.faction_references:
                    logger.info(f"Found {len(result.faction_references)} faction references:")
                    for ref in result.faction_references:
                        logger.info(f"  - {ref.faction_name} (ID: {ref.faction_id}, confidence: {ref.confidence})")
                else:
                    logger.info("No faction references found in this chunk")
            
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_id}: {e}")
            continue
        
        # Small delay between API calls to avoid rate limits
        if not test_mode and chunk_id < end_id:
            time.sleep(1)


# ────── Main Entry Point ──────────────────────────────────────────────────────

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Extract faction references from narrative chunks"
    )
    
    # Required arguments
    parser.add_argument(
        "--start",
        type=int,
        required=True,
        help="Starting chunk ID"
    )
    
    # Optional arguments
    parser.add_argument(
        "--end",
        type=int,
        help="Ending chunk ID (defaults to start if not specified)"
    )
    parser.add_argument(
        "--model",
        default="o3",
        help="OpenAI model to use (default: o3)"
    )
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high"],
        help="Reasoning effort level (only for reasoning models)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode - print API payload without making the call"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process chunks but don't write to database"
    )
    
    args = parser.parse_args()
    
    # Default end to start if not specified
    if args.end is None:
        args.end = args.start
    
    # Validate range
    if args.start > args.end:
        logger.error("Start ID must be less than or equal to end ID")
        sys.exit(1)
    
    # Connect to database
    conn = get_db_connection()
    
    try:
        # Process chunks
        process_chunks(
            conn=conn,
            start_id=args.start,
            end_id=args.end,
            model=args.model,
            reasoning_effort=args.effort,
            test_mode=args.test,
            dry_run=args.dry_run
        )
        
        logger.info("\nProcessing complete!")
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()