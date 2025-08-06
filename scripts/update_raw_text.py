#!/usr/bin/env python3
"""
Update Raw Text Script for NEXUS

Updates the raw_text field of existing narrative chunks without affecting metadata or embeddings.
Creates a backup table before making changes.

Usage:
    python update_raw_text.py [path_to_markdown_files] [--db-url DB_URL] [--backup] [--dry-run]

Example:
    python update_raw_text.py updated_narratives/*.md --backup
    python update_raw_text.py ALEX_*_revised.md --dry-run
"""

import os
import sys
import re
import glob
import logging
import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add parent directory to sys.path to import from nexus package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("update_raw_text.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.update_raw_text")

# Import SQLAlchemy
try:
    import sqlalchemy as sa
    from sqlalchemy import create_engine, Column, text, inspect
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker, Session
except ImportError:
    logger.error("SQLAlchemy not found. Please install with: pip install sqlalchemy")
    sys.exit(1)

# Try to load settings
try:
    with open(os.path.join(os.path.dirname(__file__), '..', 'settings.json'), 'r') as f:
        SETTINGS = json.load(f)["Agent Settings"]["MEMNON"]
except Exception as e:
    logger.warning(f"Warning: Could not load settings from settings.json: {e}")
    SETTINGS = {}

# Create SQL Alchemy Base
Base = declarative_base()

# Define ORM model for narrative_chunks
class NarrativeChunk(Base):
    __tablename__ = 'narrative_chunks'
    
    id = Column(sa.BigInteger, primary_key=True)
    raw_text = Column(sa.Text, nullable=False)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())

class ChunkUpdater:
    """Class for updating raw text in narrative chunks while preserving metadata."""
    
    def __init__(self, db_url: str = None, create_backup: bool = True, dry_run: bool = False):
        """
        Initialize the updater with database connection.
        
        Args:
            db_url: PostgreSQL database URL
            create_backup: Whether to create a backup table before updating
            dry_run: If True, don't actually change the database
        """
        # Set default database URL if not provided
        default_db_url = SETTINGS.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
        self.db_url = db_url or os.environ.get("NEXUS_DB_URL", default_db_url)
        self.create_backup = create_backup
        self.dry_run = dry_run
        
        # Initialize database connection
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
        
        # Statistics
        self.stats = {
            "files_processed": 0,
            "chunks_updated": 0,
            "chunks_not_found": 0,
            "errors": 0
        }
        
        logger.info(f"Connected to database: {self.db_url}")
        logger.info(f"Dry run mode: {self.dry_run}")
        logger.info(f"Create backup: {self.create_backup}")
        
    def create_backup_table(self) -> bool:
        """Create a backup of the narrative_chunks table."""
        if self.dry_run:
            logger.info("DRY RUN: Would create backup table narrative_chunks_backup")
            return True
            
        try:
            # Check if backup table already exists
            inspector = inspect(self.engine)
            if 'narrative_chunks_backup' in inspector.get_table_names():
                logger.warning("Backup table narrative_chunks_backup already exists")
                return True
                
            # Create backup table
            with self.engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE narrative_chunks_backup AS 
                    SELECT * FROM narrative_chunks
                """))
                
            logger.info("Successfully created backup table narrative_chunks_backup")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create backup table: {e}")
            return False
    
    def parse_scene_break(self, line: str) -> Optional[Tuple[str, int, int, int]]:
        """
        Parse a scene break line to extract season, episode, and scene number.
        Returns (scene_tag, season, episode, scene_number) or None if not a valid scene break.
        """
        # Match scene break format: <!-- SCENE BREAK: S01E05_001 -->
        scene_break_pattern = r'<!--\s*SCENE BREAK:\s*(S(\d+)E(\d+)_(\d+)).*-->'
        match = re.match(scene_break_pattern, line)
        
        if match:
            scene_tag = match.group(1)      # e.g., "S01E05_001"
            season = int(match.group(2))    # e.g., 1
            episode = int(match.group(3))   # e.g., 5
            scene_number = int(match.group(4))  # e.g., 1
            return scene_tag, season, episode, scene_number
        
        return None
    
    def parse_chunked_file(self, file_path: Path) -> Dict[str, str]:
        """
        Parse a markdown file with scene breaks and extract chunks.
        Returns a dictionary mapping scene tags to raw text.
        """
        chunks = {}
        current_tag = None
        current_text = []
        
        logger.info(f"Parsing file: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Check if line is a scene break
                scene_break_info = self.parse_scene_break(line)
                
                if scene_break_info:
                    # If we have an existing chunk, save it
                    if current_tag:
                        chunks[current_tag] = ''.join(current_text)
                    
                    # Start a new chunk
                    current_tag, _, _, _ = scene_break_info
                    current_text = [line]  # Include the scene break line
                elif current_tag:  # Only add text if we're inside a chunk
                    current_text.append(line)
            
            # Add the last chunk if there is one
            if current_tag:
                chunks[current_tag] = ''.join(current_text)
        
        logger.info(f"Found {len(chunks)} chunks in {file_path}")
        return chunks
    
    def find_chunk_by_scene_tag(self, session: Session, scene_tag: str) -> Optional[NarrativeChunk]:
        """
        Find a narrative chunk by its scene tag.
        
        Args:
            session: SQLAlchemy session
            scene_tag: Scene tag (e.g., "S01E05_001")
            
        Returns:
            NarrativeChunk or None if not found
        """
        # Extract components from scene tag
        match = re.match(r'S(\d+)E(\d+)_(\d+)', scene_tag)
        if not match:
            logger.warning(f"Invalid scene tag format: {scene_tag}")
            return None
            
        season = int(match.group(1))
        episode = int(match.group(2))
        scene = int(match.group(3))
        
        # First try to find the chunk using the metadata table (most reliable)
        query = sa.text("""
            SELECT nc.id, nc.raw_text, nc.created_at
            FROM narrative_chunks nc
            JOIN chunk_metadata cm ON nc.id = cm.chunk_id
            WHERE cm.season = :season AND cm.episode = :episode AND cm.scene = :scene
        """)
        
        result = session.execute(query, {"season": season, "episode": episode, "scene": scene}).first()
        
        if result:
            # Convert the result to a NarrativeChunk object
            chunk = NarrativeChunk(
                id=result[0],
                raw_text=result[1],
                created_at=result[2]
            )
            return chunk
        
        # If not found through metadata, try searching by text pattern
        # This is less reliable but can help in case metadata isn't fully populated
        pattern = f"SCENE BREAK: {scene_tag}"
        query = sa.text("""
            SELECT id, raw_text, created_at
            FROM narrative_chunks
            WHERE raw_text LIKE :pattern
            LIMIT 1
        """)
        
        result = session.execute(query, {"pattern": f"%{pattern}%"}).first()
        
        if result:
            chunk = NarrativeChunk(
                id=result[0],
                raw_text=result[1],
                created_at=result[2]
            )
            return chunk
            
        logger.warning(f"Could not find chunk for scene tag: {scene_tag}")
        return None
    
    def update_chunk_raw_text(self, session: Session, chunk: NarrativeChunk, new_text: str) -> bool:
        """
        Update the raw_text field of a narrative chunk.
        
        Args:
            session: SQLAlchemy session
            chunk: NarrativeChunk to update
            new_text: New raw_text value
            
        Returns:
            True if update was successful
        """
        if self.dry_run:
            logger.info(f"DRY RUN: Would update chunk {chunk.id} with new text ({len(new_text)} characters)")
            return True
            
        try:
            # Use direct SQL update for better control
            query = sa.text("""
                UPDATE narrative_chunks
                SET raw_text = :raw_text
                WHERE id = :id
            """)
            
            session.execute(query, {"id": chunk.id, "raw_text": new_text})
            logger.info(f"Updated chunk {chunk.id} with new text ({len(new_text)} characters)")
            return True
            
        except Exception as e:
            logger.error(f"Error updating chunk {chunk.id}: {e}")
            return False
    
    def count_new_chunks(self, scene_tags: List[str], season: int, episode: int) -> int:
        """
        Count how many new chunks need to be inserted for a given season and episode.
        
        Args:
            scene_tags: List of all scene tags in the file
            season: Season number
            episode: Episode number
            
        Returns:
            Number of chunks for the given season and episode
        """
        count = 0
        for tag in scene_tags:
            match = re.match(r'S(\d+)E(\d+)_(\d+)', tag)
            if match and int(match.group(1)) == season and int(match.group(2)) == episode:
                count += 1
        
        return count
    
    def find_insertion_point(self, session: Session, season: int, episode: int, scene: int, 
                           all_scene_tags: List[str]) -> Tuple[int, bool]:
        """
        Find the appropriate point to insert a new chunk maintaining chronological order.
        
        Args:
            session: SQLAlchemy session
            season: Season number
            episode: Episode number
            scene: Scene number
            all_scene_tags: All scene tags being processed
            
        Returns:
            Tuple of (ID to use for the new chunk, whether reorganization is needed)
        """
        # Check if this entire episode might be missing
        episode_chunks = session.execute(
            sa.text("""
                SELECT COUNT(*)
                FROM narrative_chunks nc
                JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE cm.season = :season AND cm.episode = :episode
            """),
            {"season": season, "episode": episode}
        ).scalar()
        
        if episode_chunks == 0:
            # This is the first chunk of a new episode, find where it should go
            logger.info(f"No existing chunks found for S{season:02d}E{episode:02d}")
            
            # Find ID of the last chunk of the previous episode
            prev_episode_last = session.execute(
                sa.text("""
                    SELECT MAX(nc.id)
                    FROM narrative_chunks nc
                    JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                    WHERE (cm.season < :season) 
                       OR (cm.season = :season AND cm.episode < :episode)
                """),
                {"season": season, "episode": episode}
            ).scalar()
            
            # Find ID of the first chunk of the next episode
            next_episode_first = session.execute(
                sa.text("""
                    SELECT MIN(nc.id)
                    FROM narrative_chunks nc
                    JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                    WHERE (cm.season > :season) 
                       OR (cm.season = :season AND cm.episode > :episode)
                """),
                {"season": season, "episode": episode}
            ).scalar()
            
            # Count how many chunks we need to insert for this episode
            needed_space = self.count_new_chunks(all_scene_tags, season, episode)
            
            if prev_episode_last is None:
                # This is the first episode, start from ID 1
                return 1, False
                
            if next_episode_first is None:
                # This is the last episode, append to the end
                return prev_episode_last + 1, False
                
            # Check if there's enough space between episodes
            available_space = next_episode_first - prev_episode_last - 1
            
            if available_space >= needed_space:
                # Enough space, return the first available ID
                return prev_episode_last + 1, False
            else:
                # Not enough space, need reorganization
                logger.warning(f"Not enough space for S{season:02d}E{episode:02d} (need {needed_space}, have {available_space})")
                return prev_episode_last + 1, True
        
        # For existing episodes, find where this scene should be inserted
        next_chunk = session.execute(
            sa.text("""
                SELECT MIN(nc.id)
                FROM narrative_chunks nc
                JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE cm.season = :season AND cm.episode = :episode AND cm.scene > :scene
            """),
            {"season": season, "episode": episode, "scene": scene}
        ).scalar()
        
        prev_chunk = session.execute(
            sa.text("""
                SELECT MAX(nc.id)
                FROM narrative_chunks nc
                JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE cm.season = :season AND cm.episode = :episode AND cm.scene < :scene
            """),
            {"season": season, "episode": episode, "scene": scene}
        ).scalar()
        
        if next_chunk is None:
            # No scenes after this one, append to the end of the episode
            next_episode_first = session.execute(
                sa.text("""
                    SELECT MIN(nc.id)
                    FROM narrative_chunks nc
                    JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                    WHERE (cm.season > :season) 
                       OR (cm.season = :season AND cm.episode > :episode)
                """),
                {"season": season, "episode": episode}
            ).scalar()
            
            if next_episode_first is None:
                # This is the last episode, append to the end
                max_id = session.execute(
                    sa.text("SELECT COALESCE(MAX(id), 0) FROM narrative_chunks")
                ).scalar()
                return max_id + 1, False
            
            # Check if there's space before the next episode
            if prev_chunk is None:
                # This is the first scene of the episode
                prev_episode_last = session.execute(
                    sa.text("""
                        SELECT MAX(nc.id)
                        FROM narrative_chunks nc
                        JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                        WHERE (cm.season < :season) 
                           OR (cm.season = :season AND cm.episode < :episode)
                    """),
                    {"season": season, "episode": episode}
                ).scalar() or 0
                
                insertion_point = prev_episode_last + 1
            else:
                insertion_point = prev_chunk + 1
            
            if insertion_point < next_episode_first:
                return insertion_point, False
            else:
                # Need reorganization
                return insertion_point, True
        
        if prev_chunk is None:
            # This is the first scene of the episode
            prev_episode_last = session.execute(
                sa.text("""
                    SELECT MAX(nc.id)
                    FROM narrative_chunks nc
                    JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                    WHERE (cm.season < :season) 
                       OR (cm.season = :season AND cm.episode < :episode)
                """),
                {"season": season, "episode": episode}
            ).scalar() or 0
            
            insertion_point = prev_episode_last + 1
        else:
            insertion_point = prev_chunk + 1
            
        if insertion_point < next_chunk:
            return insertion_point, False
        else:
            # Need reorganization
            return insertion_point, True
            
    def reorganize_chunk_ids(self, session: Session, season: int, episode: int, needed_space: int) -> bool:
        """
        Reorganize chunk IDs to make space for new chunks.
        
        Args:
            session: SQLAlchemy session
            season: Season number
            episode: Episode number
            needed_space: How many IDs we need to insert
            
        Returns:
            True if reorganization was successful
        """
        if self.dry_run:
            logger.info(f"DRY RUN: Would reorganize IDs to make space for {needed_space} chunks in S{season:02d}E{episode:02d}")
            return True
            
        try:
            # First, find the ID range we need to shift
            start_id = session.execute(
                sa.text("""
                    SELECT MIN(nc.id)
                    FROM narrative_chunks nc
                    JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                    WHERE (cm.season > :season) 
                       OR (cm.season = :season AND cm.episode > :episode)
                """),
                {"season": season, "episode": episode}
            ).scalar()
            
            if start_id is None:
                # No chunks after this episode, nothing to reorganize
                return True
                
            # Find the maximum ID to determine the shift size
            max_id = session.execute(
                sa.text("SELECT MAX(id) FROM narrative_chunks")
            ).scalar()
            
            # Calculate the shift amount (add some extra space for future insertions)
            shift_amount = needed_space + 100
            
            logger.info(f"Reorganizing IDs: shifting all IDs >= {start_id} by +{shift_amount}")
            
            # Since we have ON UPDATE CASCADE, we just need to update the narrative_chunks IDs
            # and all the related tables will be updated automatically
            
            # Use UPDATE with a CASE statement to shift the IDs
            logger.info(f"Using ON UPDATE CASCADE to shift IDs >= {start_id} by +{shift_amount}")
            
            # First create a gap so we don't have conflicts during the shift
            # This approach moves each ID in steps to prevent collisions when shifting
            
            # Create a temporary sequence to use for intermediate IDs
            temp_start_id = 10000000  # A high number unlikely to be used
            
            # Move all the affected IDs to temporary space
            session.execute(sa.text("""
                UPDATE narrative_chunks
                SET id = id + :temp_shift
                WHERE id >= :start_id
            """), {"temp_shift": temp_start_id, "start_id": start_id})
            
            # Move them to their final locations
            session.execute(sa.text("""
                UPDATE narrative_chunks
                SET id = id - :temp_shift + :shift_amount
                WHERE id >= :temp_start_id
            """), {"temp_shift": temp_start_id, "shift_amount": shift_amount, "temp_start_id": temp_start_id + start_id})
            
            # For tables that might not have ON UPDATE CASCADE but still need updating:
            
            # Update chunk_embeddings if it doesn't have CASCADE
            try:
                session.execute(sa.text("""
                    UPDATE chunk_embeddings
                    SET chunk_id = chunk_id + :shift_amount
                    WHERE chunk_id >= :start_id AND chunk_id < :temp_start_id
                """), {"shift_amount": shift_amount, "start_id": start_id, "temp_start_id": temp_start_id})
            except Exception as e:
                # This will likely fail as IDs have already been updated via CASCADE
                # or the table doesn't exist, which is fine
                logger.debug(f"Skipping manual update of chunk_embeddings: {e}")
            
            # The ON UPDATE CASCADE should handle the rest of the tables automatically
            
            logger.info(f"Successfully reorganized chunk IDs")
            return True
            
        except Exception as e:
            logger.error(f"Error reorganizing chunk IDs: {e}")
            session.rollback()
            return False
    
    def create_new_chunk(self, session: Session, scene_tag: str, raw_text: str, 
                       all_scene_tags: List[str]) -> Optional[NarrativeChunk]:
        """
        Create a new narrative chunk when one doesn't exist.
        
        Args:
            session: SQLAlchemy session
            scene_tag: Scene tag (e.g., "S01E05_001")
            raw_text: Raw text for the new chunk
            all_scene_tags: List of all scene tags being processed
            
        Returns:
            Newly created NarrativeChunk or None if creation failed
        """
        if self.dry_run:
            logger.info(f"DRY RUN: Would create new chunk for scene tag: {scene_tag}")
            # Return a dummy object for dry run
            return NarrativeChunk(id=-1, raw_text=raw_text)
            
        try:
            # Parse scene tag for metadata
            match = re.match(r'S(\d+)E(\d+)_(\d+)', scene_tag)
            if not match:
                logger.error(f"Invalid scene tag format: {scene_tag}")
                return None
                
            season = int(match.group(1))
            episode = int(match.group(2))
            scene = int(match.group(3))
            
            # Find where to insert this chunk to maintain chronological order
            insertion_id, needs_reorganization = self.find_insertion_point(
                session, season, episode, scene, all_scene_tags
            )
            
            logger.info(f"Determined insertion point {insertion_id} for {scene_tag}")
            
            # If reorganization is needed, do it before inserting
            if needs_reorganization:
                # Count how many chunks we need space for in this episode
                needed_space = self.count_new_chunks(all_scene_tags, season, episode)
                if not self.reorganize_chunk_ids(session, season, episode, needed_space):
                    logger.error(f"Failed to reorganize chunk IDs for S{season:02d}E{episode:02d}")
                    return None
                
                # Recalculate insertion point after reorganization
                insertion_id, _ = self.find_insertion_point(
                    session, season, episode, scene, all_scene_tags
                )
                logger.info(f"New insertion point after reorganization: {insertion_id}")
            
            # Insert the new narrative chunk with explicit ID
            result = session.execute(
                sa.text("""
                    INSERT INTO narrative_chunks (id, raw_text) 
                    VALUES (:id, :raw_text) 
                    RETURNING id, raw_text, created_at
                """),
                {"id": int(insertion_id), "raw_text": raw_text}
            ).first()
            
            if not result:
                logger.error(f"Failed to create new chunk for {scene_tag}")
                return None
                
            # Create a NarrativeChunk object
            chunk = NarrativeChunk(
                id=result[0],
                raw_text=result[1],
                created_at=result[2]
            )
            
            # Get the next available ID for chunk_metadata
            next_id_result = session.execute(
                sa.text("""
                    SELECT COALESCE(MAX(id), 0) + 1 FROM chunk_metadata
                """)
            ).scalar()
            
            # Insert metadata - use explicit VALUES instead of parameters for id
            insert_query = f"""
                INSERT INTO chunk_metadata (id, chunk_id, season, episode, scene, world_layer)
                VALUES ({next_id_result}, :chunk_id, :season, :episode, :scene, 'primary')
            """
            
            session.execute(
                sa.text(insert_query),
                {
                    "chunk_id": chunk.id,
                    "season": season,
                    "episode": episode,
                    "scene": scene
                }
            )
            
            # We don't need to manually set the slug - the trigger trg_chunk_metadata_slug will handle it
            # The trigger is defined in the database and will automatically populate the slug based on season and episode
            logger.info(f"Slug will be set automatically by database trigger for chunk {chunk.id}")
            
            logger.info(f"Created new chunk with ID {chunk.id} for scene tag {scene_tag}")
            return chunk
            
        except Exception as e:
            logger.error(f"Error creating new chunk for {scene_tag}: {e}")
            return None
        
    def process_files(self, file_pattern: str) -> Dict[str, int]:
        """
        Process files matching the pattern and update chunks in the database.
        If chunks don't exist, create them.
        
        Args:
            file_pattern: Glob pattern for markdown files
            
        Returns:
            Statistics dictionary
        """
        # Add new statistic for created chunks
        self.stats["chunks_created"] = 0
        
        # Find matching files
        files = glob.glob(file_pattern)
        if not files:
            logger.error(f"No files found matching pattern: {file_pattern}")
            return self.stats
            
        logger.info(f"Found {len(files)} files to process")
        
        # Create backup if requested
        if self.create_backup and not self.create_backup_table():
            logger.error("Failed to create backup table. Aborting.")
            return self.stats
            
        # Process each file
        for file_path in files:
            logger.info(f"Processing file: {file_path}")
            self.stats["files_processed"] += 1
            
            try:
                # Parse the file
                chunks = self.parse_chunked_file(Path(file_path))
                
                # Get all scene tags for use in insertion point logic
                all_scene_tags = list(chunks.keys())
                
                # Update each chunk in the database
                # Process chunks in individual transactions to prevent cascading failures
                for scene_tag, new_text in chunks.items():
                    # Create a new session for each chunk to isolate transactions
                    with self.Session() as session:
                        try:
                            # Find the chunk
                            chunk = self.find_chunk_by_scene_tag(session, scene_tag)
                            
                            if chunk:
                                # Update the chunk
                                if self.update_chunk_raw_text(session, chunk, new_text):
                                    self.stats["chunks_updated"] += 1
                            else:
                                # Create a new chunk if it doesn't exist
                                logger.info(f"Chunk for scene tag {scene_tag} not found, creating new chunk")
                                new_chunk = self.create_new_chunk(session, scene_tag, new_text, all_scene_tags)
                                if new_chunk:
                                    self.stats["chunks_created"] += 1
                                else:
                                    self.stats["chunks_not_found"] += 1
                            
                            # Commit this transaction
                            if not self.dry_run:
                                session.commit()
                                logger.info(f"Committed changes for chunk {scene_tag}")
                                
                        except Exception as e:
                            logger.error(f"Error processing chunk {scene_tag}: {e}")
                            self.stats["errors"] += 1
                            # Rollback transaction
                            session.rollback()
                
                logger.info(f"Finished processing file {file_path}")
                if self.dry_run:
                    logger.info(f"DRY RUN: Would have updated chunks in {file_path}")
                        
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                self.stats["errors"] += 1
                
        return self.stats
        
def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Update raw text in narrative chunks while preserving metadata.")
    
    parser.add_argument("file_pattern", nargs="?", default="*.md",
                        help="File pattern to match (default: *.md)")
    parser.add_argument("--db-url", dest="db_url", 
                        help="PostgreSQL database URL")
    parser.add_argument("--backup", action="store_true", default=True,
                        help="Create a backup of the narrative_chunks table before updating (default: True)")
    parser.add_argument("--no-backup", action="store_false", dest="backup",
                        help="Skip creating a backup table")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't actually update the database, just show what would be done")
    
    args = parser.parse_args()
    
    # Initialize chunk updater
    updater = ChunkUpdater(
        db_url=args.db_url,
        create_backup=args.backup,
        dry_run=args.dry_run
    )
    
    # Process files
    stats = updater.process_files(args.file_pattern)
    
    # Print summary
    print("\nUpdate Summary:")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Chunks updated: {stats['chunks_updated']}")
    print(f"Chunks created: {stats['chunks_created']}")
    print(f"Chunks not found: {stats['chunks_not_found']}")
    print(f"Errors: {stats['errors']}")
    
    if args.dry_run:
        print("\nDRY RUN: No changes were made to the database")

if __name__ == "__main__":
    main()