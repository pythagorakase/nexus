#!/usr/bin/env python3
"""
Simple Query Utility for NEXUS

Provides a simple way to search for narrative chunks by keyword.
"""

import sys
import argparse
import sqlalchemy as sa

def main():
    parser = argparse.ArgumentParser(description="Simple query utility for NEXUS")
    parser.add_argument("query", help="Text to search for")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of results")
    args = parser.parse_args()
    
    # Connect to the database
    engine = sa.create_engine("postgresql://pythagor@localhost/NEXUS")
    
    try:
        # Simple text search using ILIKE
        with engine.connect() as conn:
            query = sa.text("""
                SELECT 
                    n.id, 
                    substring(n.raw_text, 1, 300) as text_preview,
                    m.season,
                    m.episode,
                    m.world_layer,
                    m.narrative_vector->>'scene_number' as scene_number
                FROM 
                    narrative_chunks n
                JOIN 
                    chunk_metadata m ON n.id = m.chunk_id
                WHERE 
                    n.raw_text ILIKE :search
                ORDER BY 
                    m.season, m.episode, (m.narrative_vector->>'scene_number')::int
                LIMIT :limit
            """)
            
            result = conn.execute(query, {"search": f"%{args.query}%", "limit": args.limit})
            rows = result.fetchall()
            
            if not rows:
                print(f"No matches found for '{args.query}'")
                return
            
            print(f"Found {len(rows)} matches for '{args.query}':\n")
            
            for i, row in enumerate(rows, 1):
                print(f"Result {i}:")
                print(f"  Season {row.season}, Episode {row.episode}, Scene {row.scene_number}")
                print(f"  World Layer: {row.world_layer}")
                print(f"  Preview: {row.text_preview}...")
                print()
    
    except Exception as e:
        print(f"Error querying database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()