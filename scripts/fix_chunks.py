#!/usr/bin/env python
"""
Script to update the chunk IDs in chunk_metadata to match the episodes table's chunk_span.
This ensures that the chunks are assigned to the correct episodes.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import re

def main():
    # Connect to the database
    print("Connecting to NEXUS database...")
    conn = psycopg2.connect(
        dbname="NEXUS",
        user="pythagor",
        host="localhost",
        port=5432
    )
    
    # Create a cursor and enable autocommit
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # First, get all episodes with their chunk spans
        cur.execute("SELECT season, episode, chunk_span FROM episodes ORDER BY season, episode")
        episodes = cur.fetchall()
        
        print("\nEpisode ranges:")
        for ep in episodes:
            season = ep['season']
            episode = ep['episode']
            chunk_span = ep['chunk_span']
            
            if chunk_span is None or chunk_span == 'empty':
                continue
                
            # Extract the bounds from the PostgreSQL range string
            span_str = str(chunk_span)
            match = re.match(r'\[(\d+),(\d+)\)', span_str)
            
            if match:
                start_chunk = int(match.group(1))
                end_chunk = int(match.group(2))
                
                print(f"S{season:02d}E{episode:02d}: Chunks {start_chunk}-{end_chunk-1}")
                
                # Update chunk_metadata for all chunks in this span
                # First, check if any of these chunks are incorrectly assigned
                cur.execute("""
                    SELECT id, chunk_id, season, episode 
                    FROM chunk_metadata 
                    WHERE id >= %s AND id < %s
                """, (start_chunk, end_chunk))
                
                chunks = cur.fetchall()
                
                incorrect_chunks = []
                for chunk in chunks:
                    if chunk['season'] != season or chunk['episode'] != episode:
                        incorrect_chunks.append(chunk)
                
                if incorrect_chunks:
                    print(f"  Found {len(incorrect_chunks)} incorrectly assigned chunks in S{season:02d}E{episode:02d} range:")
                    for chunk in incorrect_chunks:
                        print(f"  - Chunk {chunk['id']} assigned to S{chunk['season']:02d}E{chunk['episode']:02d}, should be S{season:02d}E{episode:02d}")
                        
                        # Update this chunk's episode assignment
                        cur.execute("""
                            UPDATE chunk_metadata 
                            SET season = %s, episode = %s 
                            WHERE id = %s
                        """, (season, episode, chunk['id']))
                        
                        print(f"    - Updated chunk {chunk['id']} to S{season:02d}E{episode:02d}")
        
        # Ask for confirmation before committing
        print("\nAre you sure you want to commit these changes? (y/n)")
        confirm = input("> ")
        
        if confirm.lower() == 'y':
            conn.commit()
            print("Changes committed.")
        else:
            conn.rollback()
            print("Changes rolled back.")
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        # Close the connection
        conn.close()

if __name__ == "__main__":
    main()