#!/usr/bin/env python3
"""
Migrate character references from chunk_metadata.characters array 
to the normalized chunk_character_references table.

This script:
1. Reads the characters array from chunk_metadata
2. Parses each reference (format: "CharacterName:reference_type")
3. Looks up character IDs using case-insensitive matching and aliases
4. Populates the chunk_character_references table
"""

import json
import psycopg2
from psycopg2.extras import execute_batch
from typing import List, Tuple, Optional, Dict
import logging
from collections import defaultdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load database settings
with open('settings.json', 'r') as f:
    settings = json.load(f)
    # Database config is under Agent Settings -> MEMNON -> database
    db_url = settings['Agent Settings']['MEMNON']['database']['url']

def get_db_connection():
    """Create and return a database connection."""
    # Parse the connection URL: postgresql://pythagor@localhost/NEXUS
    return psycopg2.connect(db_url)

def build_character_lookup(conn) -> Dict[str, int]:
    """
    Build a lookup dictionary for character names and aliases.
    Returns a dict mapping lowercase names/aliases to character IDs.
    """
    lookup = {}
    
    with conn.cursor() as cur:
        # Get all character names
        cur.execute("SELECT id, name FROM characters")
        for char_id, name in cur.fetchall():
            if name:
                lookup[name.lower()] = char_id
        
        # Get all character aliases
        cur.execute("""
            SELECT ca.character_id, ca.alias 
            FROM character_aliases ca
            JOIN characters c ON ca.character_id = c.id
        """)
        for char_id, alias in cur.fetchall():
            if alias:
                lookup[alias.lower()] = char_id
    
    logger.info(f"Built character lookup with {len(lookup)} entries")
    return lookup

def parse_character_reference(reference: str) -> Tuple[str, Optional[str]]:
    """
    Parse a character reference string.
    Format: "CharacterName:reference_type" or just "CharacterName"
    Returns: (character_name, reference_type)
    """
    if ':' in reference:
        parts = reference.split(':', 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else None
    return reference.strip(), None

def resolve_unknown_character(char_name: str, char_lookup: Dict[str, int], conn) -> Optional[int]:
    """
    Interactively resolve an unknown character name.
    Returns the character ID if resolved, None if skipped.
    """
    print(f"\nUnknown character: '{char_name}'")
    print("Options:")
    print("  1. Enter the correct character name")
    print("  2. Enter the character ID directly")
    print("  3. Skip this character (press Enter)")
    print("  4. Skip all occurrences of this character (type 'skip')")
    
    response = input("Your choice: ").strip()
    
    if not response or response.lower() == 'skip':
        return None
    
    # Try to parse as an ID first
    try:
        char_id = int(response)
        # Verify the ID exists
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM characters WHERE id = %s", (char_id,))
            result = cur.fetchone()
            if result:
                print(f"  -> Mapped to: {result[0]} (ID: {char_id})")
                return char_id
            else:
                print(f"  -> No character found with ID {char_id}")
                return None
    except ValueError:
        # Not a number, treat as character name
        char_id = char_lookup.get(response.lower())
        if char_id:
            # Get the actual name for confirmation
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM characters WHERE id = %s", (char_id,))
                actual_name = cur.fetchone()[0]
                print(f"  -> Mapped to: {actual_name} (ID: {char_id})")
                return char_id
        else:
            print(f"  -> Character name '{response}' not found")
            return None

def migrate_references(conn, batch_size: int = 1000, interactive: bool = True):
    """Migrate character references from chunk_metadata to chunk_character_references."""
    
    # Build character lookup
    char_lookup = build_character_lookup(conn)
    
    # Track resolved mappings for this session
    resolved_mappings = {}  # unknown_name -> character_id
    skip_characters = set()  # Characters to skip entirely
    
    # Track statistics
    stats = {
        'total_chunks': 0,
        'processed_chunks': 0,
        'total_references': 0,
        'inserted_references': 0,
        'unknown_characters': defaultdict(int),
        'resolved_characters': defaultdict(int),
        'skipped_characters': defaultdict(int),
        'errors': 0
    }
    
    with conn.cursor() as cur:
        # Get total count
        cur.execute("""
            SELECT COUNT(*) 
            FROM chunk_metadata 
            WHERE characters IS NOT NULL 
            AND array_length(characters, 1) > 0
        """)
        stats['total_chunks'] = cur.fetchone()[0]
        logger.info(f"Found {stats['total_chunks']} chunks with character references")
        
        # Process in batches
        offset = 0
        while True:
            cur.execute("""
                SELECT id, chunk_id, characters 
                FROM chunk_metadata 
                WHERE characters IS NOT NULL 
                AND array_length(characters, 1) > 0
                ORDER BY id
                LIMIT %s OFFSET %s
            """, (batch_size, offset))
            
            rows = cur.fetchall()
            if not rows:
                break
            
            # Prepare batch insert data
            insert_data = []
            
            for meta_id, chunk_id, characters in rows:
                stats['processed_chunks'] += 1
                
                for char_ref in characters:
                    stats['total_references'] += 1
                    
                    # Parse the reference
                    char_name, ref_type = parse_character_reference(char_ref)
                    
                    # Look up character ID
                    char_id = None
                    
                    # Check if we've already resolved this character
                    if char_name in resolved_mappings:
                        char_id = resolved_mappings[char_name]
                        stats['resolved_characters'][char_name] += 1
                    elif char_name in skip_characters:
                        stats['skipped_characters'][char_name] += 1
                        continue
                    else:
                        # Try normal lookup
                        char_id = char_lookup.get(char_name.lower())
                        
                        # If not found and interactive mode, ask user
                        if not char_id and interactive and char_name not in stats['unknown_characters']:
                            resolved_id = resolve_unknown_character(char_name, char_lookup, conn)
                            if resolved_id:
                                resolved_mappings[char_name] = resolved_id
                                char_id = resolved_id
                                # Update the lookup for future use
                                char_lookup[char_name.lower()] = char_id
                            else:
                                skip_characters.add(char_name)
                    
                    if char_id:
                        # Prepare insert data
                        insert_data.append((
                            chunk_id,
                            char_id,
                            ref_type if ref_type in ['present', 'mentioned'] else None
                        ))
                        stats['inserted_references'] += 1
                    else:
                        # Track unknown characters
                        stats['unknown_characters'][char_name] += 1
                        logger.debug(f"Unknown character: '{char_name}' in chunk {chunk_id}")
            
            # Batch insert
            if insert_data:
                try:
                    execute_batch(
                        cur,
                        """
                        INSERT INTO chunk_character_references (chunk_id, character_id, reference)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (chunk_id, character_id) DO UPDATE
                        SET reference = EXCLUDED.reference
                        """,
                        insert_data
                    )
                    conn.commit()
                    logger.info(f"Inserted {len(insert_data)} references (offset: {offset})")
                except Exception as e:
                    logger.error(f"Error inserting batch at offset {offset}: {e}")
                    conn.rollback()
                    stats['errors'] += 1
            
            offset += batch_size
            
            # Progress update
            if stats['processed_chunks'] % 100 == 0:
                pct = (stats['processed_chunks'] / stats['total_chunks']) * 100
                logger.info(f"Progress: {stats['processed_chunks']}/{stats['total_chunks']} ({pct:.1f}%)")
    
    return stats

def print_migration_report(stats: dict):
    """Print a summary report of the migration."""
    print("\n=== Migration Report ===")
    print(f"Total chunks processed: {stats['processed_chunks']}")
    print(f"Total character references: {stats['total_references']}")
    print(f"Successfully inserted: {stats['inserted_references']}")
    print(f"Failed references: {stats['total_references'] - stats['inserted_references']}")
    print(f"Errors encountered: {stats['errors']}")
    
    if stats['resolved_characters']:
        print("\n=== Manually Resolved Characters ===")
        for char_name, count in stats['resolved_characters'].items():
            print(f"  '{char_name}': {count} references resolved")
    
    if stats['skipped_characters']:
        print("\n=== Skipped Characters ===")
        for char_name, count in stats['skipped_characters'].items():
            print(f"  '{char_name}': {count} references skipped")
    
    if stats['unknown_characters']:
        print("\n=== Unknown Characters (Still Unresolved) ===")
        # Sort by frequency
        sorted_unknown = sorted(
            stats['unknown_characters'].items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        for char_name, count in sorted_unknown[:20]:  # Show top 20
            print(f"  '{char_name}': {count} occurrences")
        
        if len(sorted_unknown) > 20:
            print(f"  ... and {len(sorted_unknown) - 20} more unknown characters")

def main():
    """Main migration function."""
    logger.info("Starting character reference migration...")
    
    try:
        with get_db_connection() as conn:
            # Check if table is already populated
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM chunk_character_references")
                existing_count = cur.fetchone()[0]
                
                if existing_count > 0:
                    response = input(f"Table already contains {existing_count} references. Continue? (y/n): ")
                    if response.lower() != 'y':
                        logger.info("Migration cancelled")
                        return
            
            # Run migration
            stats = migrate_references(conn)
            
            # Print report
            print_migration_report(stats)
            
            logger.info("Migration completed successfully")
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    main()