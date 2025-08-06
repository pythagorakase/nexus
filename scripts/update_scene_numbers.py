#!/usr/bin/env python
"""
Script to extract scene numbers from narrative chunk raw_text and update the scene column.
"""

import re
import sys
import psycopg2
from psycopg2.extras import execute_values
import logging
from typing import Optional, List, Tuple, Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scene_extraction.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Database connection string from the settings
DB_CONNECTION = "postgresql://pythagor@localhost/NEXUS"

def connect_to_db() -> Optional[psycopg2.extensions.connection]:
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(DB_CONNECTION)
        logger.info("Successfully connected to the database")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to database: {e}")
        return None

def extract_scene_from_raw_text(raw_text: str) -> Optional[int]:
    """Extract scene number from raw_text containing <!-- SCENE BREAK: S02E03_007 -->"""
    if not raw_text:
        return None
    
    # Define regex pattern to extract the scene number
    pattern = r'<!--\s*SCENE BREAK:\s*S\d+E\d+_(\d+)'
    match = re.search(pattern, raw_text)
    
    if match:
        # Convert the matched scene number to integer
        scene_number = int(match.group(1))
        return scene_number
    
    return None

def add_scene_column_if_not_exists(conn: psycopg2.extensions.connection) -> bool:
    """Add the scene column to the chunk_metadata table if it doesn't exist"""
    try:
        with conn.cursor() as cur:
            # Check if the column exists
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'chunk_metadata' AND column_name = 'scene'
            """)
            if not cur.fetchone():
                logger.info("Adding scene column to chunk_metadata table")
                
                # Add the column
                cur.execute("""
                    ALTER TABLE chunk_metadata ADD COLUMN scene int4;
                    COMMENT ON COLUMN chunk_metadata.scene IS 'Scene number extracted from the raw_text (e.g. 37 from S02E07_037)';
                """)
                
                # Add indexes
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chunk_metadata_scene 
                    ON chunk_metadata (scene);
                    
                    CREATE INDEX IF NOT EXISTS idx_chunk_metadata_season_episode_scene 
                    ON chunk_metadata (season, episode, scene);
                """)
                
                conn.commit()
                logger.info("Added scene column and indexes successfully")
                return True
            else:
                logger.info("Scene column already exists")
                return True
    except psycopg2.Error as e:
        logger.error(f"Error adding scene column: {e}")
        conn.rollback()
        return False

def get_chunks_without_scene(conn: psycopg2.extensions.connection) -> List[Tuple[str, str]]:
    """Retrieve chunks that don't have a scene number set yet"""
    try:
        with conn.cursor() as cur:
            # Get all chunks that have NULL scene values, join with narrative_chunks to get raw_text
            cur.execute("""
                SELECT cm.chunk_id, nc.raw_text
                FROM chunk_metadata cm
                JOIN narrative_chunks nc ON cm.chunk_id = nc.id
                WHERE cm.scene IS NULL
                ORDER BY cm.season, cm.episode
            """)
            return cur.fetchall()
    except psycopg2.Error as e:
        logger.error(f"Error retrieving chunks: {e}")
        conn.rollback()
        return []

def update_scene_numbers(conn: psycopg2.extensions.connection, updates: List[Tuple[int, str]]) -> bool:
    """Update scene numbers in the database"""
    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                UPDATE chunk_metadata
                SET scene = data.scene
                FROM (VALUES %s) AS data(scene, chunk_id)
                WHERE chunk_metadata.chunk_id = data.chunk_id::uuid
                """,
                updates
            )
            conn.commit()
            return True
    except psycopg2.Error as e:
        logger.error(f"Error updating scene numbers: {e}")
        conn.rollback()
        return False

def main():
    """Main function to extract and update scene numbers"""
    # Connect to the database
    conn = connect_to_db()
    if not conn:
        logger.error("Failed to connect to the database")
        sys.exit(1)
    
    try:
        # Ensure scene column exists
        if not add_scene_column_if_not_exists(conn):
            logger.error("Failed to add scene column")
            sys.exit(1)
        
        # Get chunks without scene numbers
        chunks = get_chunks_without_scene(conn)
        logger.info(f"Found {len(chunks)} chunks without scene numbers")
        
        # Extract scene numbers
        updates = []
        for chunk_id, raw_text in chunks:
            scene_number = extract_scene_from_raw_text(raw_text)
            if scene_number is not None:
                updates.append((scene_number, chunk_id))
                logger.debug(f"Extracted scene {scene_number} from chunk {chunk_id}")
            else:
                logger.warning(f"Could not extract scene number from chunk {chunk_id}")
        
        # Update database
        if updates:
            logger.info(f"Updating {len(updates)} scene numbers")
            success = update_scene_numbers(conn, updates)
            if success:
                logger.info(f"Successfully updated {len(updates)} scene numbers")
            else:
                logger.error("Failed to update scene numbers")
        else:
            logger.info("No scene numbers to update")
        
        # Count updated rows
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunk_metadata WHERE scene IS NOT NULL")
            count = cur.fetchone()[0]
            logger.info(f"Total chunks with scene numbers: {count}")
    
    finally:
        # Close database connection
        if conn:
            conn.close()
            logger.info("Database connection closed")

if __name__ == "__main__":
    main()