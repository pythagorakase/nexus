#!/usr/bin/env python
"""
One-time script to update PostgreSQL range notation in the episodes table.
Converts exclusive upper bounds (parenthesis) to inclusive upper bounds (brackets).
"""

import psycopg2
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
    conn.autocommit = True
    cur = conn.cursor()
    
    # First, let's get the current values to show before/after
    cur.execute("SELECT season, episode, chunk_span FROM episodes ORDER BY season, episode")
    original_ranges = cur.fetchall()
    
    # Print the current ranges
    print("\nCurrent ranges (exclusive upper bounds):")
    print("Season | Episode | Chunk Span")
    print("-------+---------+-----------")
    for row in original_ranges:
        print(f"{row[0]:6d} | {row[1]:7d} | {row[2]}")
    
    # Skip confirmation in non-interactive mode
    print("\nThis will update all episode chunk_span upper bounds from exclusive to inclusive.")
    print("Proceeding with update...")
    
    try:
        # For each range, extract the bounds, adjust the upper bound, and update
        print("\nUpdating ranges...")
        
        # PostgreSQL 14+ has a native replace() function to change ')' to ']'
        # First, let's check if our version supports it
        cur.execute("SELECT version()")
        version_info = cur.fetchone()[0]
        pg_version = int(re.search(r'PostgreSQL (\d+)', version_info).group(1))
        
        if pg_version >= 14:
            # Use the built-in replace function for all records
            cur.execute("""
                UPDATE episodes 
                SET chunk_span = REPLACE(CAST(chunk_span AS TEXT), ')', ']')::int8range
                WHERE CAST(chunk_span AS TEXT) LIKE '%)'
            """)
            updated_count = cur.rowcount
        else:
            # Pre-14 approach: update each range individually
            updated_count = 0
            for row in original_ranges:
                season, episode, chunk_span = row
                
                # Convert the range to text
                range_text = str(chunk_span)
                
                # Only update if it ends with ')'
                if range_text.endswith(')'):
                    # Replace the closing parenthesis with a bracket
                    new_range_text = range_text.replace(')', ']')
                    
                    # Update the database
                    cur.execute("""
                        UPDATE episodes 
                        SET chunk_span = %s::int8range
                        WHERE season = %s AND episode = %s
                    """, (new_range_text, season, episode))
                    
                    updated_count += 1
        
        print(f"Updated {updated_count} ranges.")
        
        # Get the updated values
        cur.execute("SELECT season, episode, chunk_span FROM episodes ORDER BY season, episode")
        updated_ranges = cur.fetchall()
        
        # Print the updated ranges
        print("\nUpdated ranges (inclusive upper bounds):")
        print("Season | Episode | Chunk Span")
        print("-------+---------+-----------")
        for row in updated_ranges:
            print(f"{row[0]:6d} | {row[1]:7d} | {row[2]}")
        
        print("\nUpdate complete!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Close the connection
        conn.close()

if __name__ == "__main__":
    main()