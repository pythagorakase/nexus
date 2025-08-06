#!/usr/bin/env python3
"""
Script to populate the character_aliases table from the characters.aliases array.

This script:
- Connects to PostgreSQL database
- Reads all characters with non-empty aliases arrays
- Inserts each alias into the normalized character_aliases table
- Skips duplicates and aliases that match the character's name
- Is idempotent (safe to run multiple times)
"""

import os
import psycopg2
from psycopg2.extras import execute_values
from typing import List, Tuple
import sys

# Database configuration
DB_CONFIG = {
    'host': os.environ.get('NEXUS_DB_HOST', 'localhost'),
    'port': os.environ.get('NEXUS_DB_PORT', '5432'),
    'database': os.environ.get('NEXUS_DB_NAME', 'NEXUS'),
    'user': os.environ.get('NEXUS_DB_USER', 'pythagor'),
    'password': os.environ.get('NEXUS_DB_PASSWORD', None)
}

# Build connection string
conn_parts = [f"host={DB_CONFIG['host']}", f"port={DB_CONFIG['port']}", 
              f"dbname={DB_CONFIG['database']}", f"user={DB_CONFIG['user']}"]
if DB_CONFIG['password']:
    conn_parts.append(f"password={DB_CONFIG['password']}")
CONNECTION_STRING = ' '.join(conn_parts)


def get_characters_with_aliases(cursor) -> List[Tuple[int, str, List[str]]]:
    """Fetch all characters that have non-empty aliases arrays."""
    query = """
        SELECT id, name, aliases
        FROM characters
        WHERE aliases IS NOT NULL 
        AND array_length(aliases, 1) > 0
        ORDER BY id
    """
    cursor.execute(query)
    return cursor.fetchall()


def insert_aliases(cursor, character_id: int, character_name: str, aliases: List[str]) -> int:
    """
    Insert aliases for a character into the character_aliases table.
    
    Returns the number of aliases inserted.
    """
    # Filter out aliases that match the character's name
    unique_aliases = [alias for alias in aliases if alias != character_name]
    
    if not unique_aliases:
        return 0
    
    # Prepare data for bulk insert
    data = [(character_id, alias) for alias in unique_aliases]
    
    # Use ON CONFLICT DO NOTHING to handle duplicates gracefully
    insert_query = """
        INSERT INTO character_aliases (character_id, alias)
        VALUES %s
        ON CONFLICT (character_id, alias) DO NOTHING
    """
    
    # Execute bulk insert and get number of rows inserted
    execute_values(cursor, insert_query, data)
    return cursor.rowcount


def main():
    """Main function to populate character_aliases table."""
    print(f"Connecting to database: {DB_CONFIG['database']} @ {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    
    try:
        # Connect to database
        conn = psycopg2.connect(CONNECTION_STRING)
        cursor = conn.cursor()
        
        # Get all characters with aliases
        print("\nFetching characters with aliases...")
        characters = get_characters_with_aliases(cursor)
        print(f"Found {len(characters)} characters with aliases")
        
        # Process each character
        total_inserted = 0
        characters_processed = 0
        
        for char_id, char_name, aliases in characters:
            if aliases:  # Double-check aliases exist
                inserted = insert_aliases(cursor, char_id, char_name, aliases)
                if inserted > 0:
                    print(f"Character {char_id} ({char_name}): inserted {inserted} aliases")
                    total_inserted += inserted
                    characters_processed += 1
                else:
                    # Check if aliases were skipped due to matching name or already existing
                    cursor.execute("""
                        SELECT COUNT(*) FROM character_aliases 
                        WHERE character_id = %s
                    """, (char_id,))
                    existing_count = cursor.fetchone()[0]
                    if existing_count > 0:
                        print(f"Character {char_id} ({char_name}): all {len(aliases)} aliases already exist")
                    else:
                        print(f"Character {char_id} ({char_name}): all aliases matched character name (skipped)")
        
        # Commit the transaction
        conn.commit()
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  Total characters processed: {len(characters)}")
        print(f"  Characters with new aliases: {characters_processed}")
        print(f"  Total aliases inserted: {total_inserted}")
        
        # Get final count
        cursor.execute("SELECT COUNT(*) FROM character_aliases")
        final_count = cursor.fetchone()[0]
        print(f"  Total aliases in table: {final_count}")
        print(f"{'='*60}\n")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()