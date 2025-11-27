#!/usr/bin/env python
"""
Script to extract scene numbers from narrative chunk slugs and update the database.
This provides a Python alternative to the SQL script for more complex processing.
"""

import os
import re
import sys
import psycopg2
from psycopg2.extras import execute_values
import logging
from typing import Optional, List, Dict, Tuple, Any
import json

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

# Load database configuration
def load_db_config() -> Dict[str, Any]:
    """Load database configuration from config file"""
    try:
        from nexus.config import load_settings_as_dict
        settings = load_settings_as_dict()
        # Extract from MEMNON agent settings
        if "Agent Settings" in settings and "MEMNON" in settings["Agent Settings"]:
            db_url = settings["Agent Settings"]["MEMNON"]["database"].get("url")
            if db_url:
                # Parse PostgreSQL URL
                # Format: postgresql://username:password@host:port/database
                # Remove postgresql:// prefix
                db_url = db_url.replace("postgresql://", "")
                # Split by @ to separate credentials and host/database
                if "@" in db_url:
                    creds, host_db = db_url.split("@", 1)
                    # Split credentials by : to get username and password
                    if ":" in creds:
                        username, password = creds.split(":", 1)
                    else:
                        username, password = creds, ""
                    # Split host/db by / to get host and database
                    if "/" in host_db:
                        host_part, database = host_db.split("/", 1)
                        # Check if port is specified
                        if ":" in host_part:
                            host, port = host_part.split(":", 1)
                            port = int(port)
                        else:
                            host, port = host_part, 5432

                        return {
                            "host": host,
                            "port": port,
                            "database": database,
                            "user": username,
                            "password": password
                        }
                logger.warning(f"Failed to parse database URL: {db_url}")

        logger.warning("Database configuration not found in MEMNON agent settings, using empty config")
        return {}
    except Exception as e:
        logger.error(f"Error loading database configuration: {e}")
        return {}

def connect_to_db(db_config: Dict[str, Any]) -> Optional[psycopg2.extensions.connection]:
    """Connect to PostgreSQL database using the provided configuration"""
    try:
        conn = psycopg2.connect(
            host=db_config.get("host", "localhost"),
            port=db_config.get("port", 5432),
            database=db_config.get("database", "nexus"),
            user=db_config.get("user", "postgres"),
            password=db_config.get("password", "")
        )
        logger.info("Successfully connected to the database")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to database: {e}")
        return None

def extract_scene_from_slug(slug: str) -> Optional[int]:
    """Extract scene number from a slug like S02E07_037"""
    if not slug:
        return None
    
    # Get the regex pattern from settings if possible
    pattern = r'S\d+E\d+_(\d+)'
    
    # Try to load pattern from settings
    try:
        from nexus.config import load_settings_as_dict
        settings = load_settings_as_dict()
        if "Agent Settings" in settings and "MEMNON" in settings["Agent Settings"]:
            if "import" in settings["Agent Settings"]["MEMNON"]:
                import_settings = settings["Agent Settings"]["MEMNON"]["import"]
                if "chunk_regex" in import_settings:
                    pattern = import_settings["chunk_regex"]
                    logger.info(f"Using regex pattern from settings: {pattern}")
    except Exception as e:
        logger.warning(f"Could not load regex pattern from config: {e}")
    
    # Define regex pattern to extract the scene number
    # Pattern should capture the scene number in group 4 based on settings
    # <!--\s*SCENE BREAK:\s*(S(\d+)E(\d+))_(\d+).*-->
    match = re.search(pattern, slug)
    
    if match:
        # If using the pattern from settings, scene number is in group 4
        if len(match.groups()) >= 4:
            scene_number = int(match.group(4))
        else:
            # Fallback to our simple pattern
            scene_number = int(match.group(1))
        
        logger.debug(f"Extracted scene number {scene_number} from slug {slug}")
        return scene_number
    
    logger.warning(f"Could not extract scene number from slug: {slug}")
    return None

def get_chunks_without_scene(conn: psycopg2.extensions.connection) -> List[Tuple[str, str]]:
    """Retrieve chunks that don't have a scene number set yet"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT chunk_id, slug
                FROM chunk_metadata
                WHERE scene IS NULL AND slug IS NOT NULL
                ORDER BY season, episode
            """)
            return cur.fetchall()
    except psycopg2.Error as e:
        logger.error(f"Error retrieving chunks: {e}")
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
                    COMMENT ON COLUMN chunk_metadata.scene IS 'Scene number extracted from the slug (e.g. 37 from S02E07_037)';
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

def main():
    """Main function to extract and update scene numbers"""
    # Load database configuration
    db_config = load_db_config()
    if not db_config:
        logger.error("Failed to load database configuration")
        sys.exit(1)
    
    # Connect to the database
    conn = connect_to_db(db_config)
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
        for chunk_id, slug in chunks:
            scene_number = extract_scene_from_slug(slug)
            if scene_number is not None:
                updates.append((scene_number, chunk_id))
        
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