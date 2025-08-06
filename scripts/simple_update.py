#!/usr/bin/env python3
"""
Simple Update Raw Text for NEXUS

A very straightforward script to update raw text of narrative chunks.
If a chunk doesn't exist, it adds it at the appropriate position to maintain chronological ordering.

Features:
- Updates existing chunks or creates new ones in the correct chronological position
- Fixes missing metadata entries for chunks
- Can resequence all chunk IDs and metadata IDs to maintain clean ordering
- Supports dry run mode to preview changes without modifying the database

Usage:
    python simple_update.py path/to/file.md [--db-url DB_URL] [--dry-run] [--fix-metadata] [--resequence]

Example:
    python simple_update.py transcripts/ALEX_4.md
    python simple_update.py "transcripts/*.md" --dry-run
    python simple_update.py transcripts/ALEX_4.md --fix-metadata --resequence
"""

import os
import sys
import re
import glob
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("nexus.simple_update")

# Import SQLAlchemy
try:
    import sqlalchemy as sa
    from sqlalchemy.sql import text
    from sqlalchemy.engine import Engine, create_engine
except ImportError:
    logger.error("SQLAlchemy not found. Please install it with: pip install sqlalchemy")
    sys.exit(1)

def parse_scene_break(line: str) -> Optional[Tuple[str, int, int, int]]:
    """
    Parse a scene break line to extract metadata.
    
    Args:
        line: Line from a markdown file
        
    Returns:
        Tuple of (scene_tag, season, episode, scene) or None
    """
    pattern = r'<!--\s*SCENE BREAK:\s*(S(\d+)E(\d+)_(\d+)).*-->'
    match = re.match(pattern, line)
    
    if match:
        tag = match.group(1)
        season = int(match.group(2))
        episode = int(match.group(3))
        scene = int(match.group(4))
        return tag, season, episode, scene
    
    return None

def parse_file(file_path: Path) -> Dict[str, dict]:
    """
    Parse a markdown file containing scene breaks.
    
    Args:
        file_path: Path to markdown file
        
    Returns:
        Dictionary mapping scene tags to chunk data
    """
    chunks = {}
    current_tag = None
    current_text = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Check for scene break
            scene_break = parse_scene_break(line)
            
            if scene_break:
                # Save previous chunk if there was one
                if current_tag:
                    tag, season, episode, scene = chunks[current_tag]['metadata']
                    chunks[current_tag]['text'] = ''.join(current_text)
                
                # Start new chunk
                current_tag, season, episode, scene = scene_break
                chunks[current_tag] = {
                    'metadata': (current_tag, season, episode, scene),
                    'text': None
                }
                current_text = [line]
            elif current_tag:
                current_text.append(line)
        
        # Save last chunk
        if current_tag:
            tag, season, episode, scene = chunks[current_tag]['metadata']
            chunks[current_tag]['text'] = ''.join(current_text)
    
    logger.info(f"Found {len(chunks)} chunks in {file_path}")
    return chunks

def find_chunk_id(engine: Engine, season: int, episode: int, scene: int) -> Optional[int]:
    """
    Find a chunk ID by its metadata.
    
    Args:
        engine: SQLAlchemy engine
        season: Season number
        episode: Episode number
        scene: Scene number
        
    Returns:
        Chunk ID or None if not found
    """
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT nc.id
            FROM narrative_chunks nc
            JOIN chunk_metadata cm ON nc.id = cm.chunk_id
            WHERE cm.season = :season
              AND cm.episode = :episode
              AND cm.scene = :scene
        """), {"season": season, "episode": episode, "scene": scene}).first()
        
    return result[0] if result else None

def find_insertion_point(engine: Engine, season: int, episode: int, scene: int) -> int:
    """
    Find the appropriate point to insert a new chunk to maintain chronological order.
    
    Args:
        engine: SQLAlchemy engine
        season: Season number
        episode: Episode number
        scene: Scene number
        
    Returns:
        ID to use for the new chunk
    """
    # First, check if the episode exists
    with engine.connect() as conn:
        episode_exists = conn.execute(text("""
            SELECT COUNT(*)
            FROM chunk_metadata
            WHERE season = :season AND episode = :episode
        """), {"season": season, "episode": episode}).scalar() > 0
        
        if episode_exists:
            # Find chunks within the same episode that should come after this one
            next_chunk = conn.execute(text("""
                SELECT MIN(nc.id)
                FROM narrative_chunks nc
                JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE cm.season = :season 
                  AND cm.episode = :episode 
                  AND cm.scene > :scene
            """), {"season": season, "episode": episode, "scene": scene}).scalar()
            
            if next_chunk:
                # Return ID right before the next chunk
                return next_chunk - 1
            
            # Find chunks from later episodes
            next_episode_chunk = conn.execute(text("""
                SELECT MIN(nc.id)
                FROM narrative_chunks nc
                JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE (cm.season > :season)
                   OR (cm.season = :season AND cm.episode > :episode)
            """), {"season": season, "episode": episode}).scalar()
            
            if next_episode_chunk:
                # Return ID right before the next episode's first chunk
                return next_episode_chunk - 1
        else:
            # This is a new episode
            # Find chunks from later episodes
            next_episode_chunk = conn.execute(text("""
                SELECT MIN(nc.id)
                FROM narrative_chunks nc
                JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE (cm.season > :season)
                   OR (cm.season = :season AND cm.episode > :episode)
            """), {"season": season, "episode": episode}).scalar()
            
            if next_episode_chunk:
                # Return ID right before the next episode's first chunk
                return next_episode_chunk - 1
            
            # Find chunks from the previous episode
            prev_episode_chunk = conn.execute(text("""
                SELECT MAX(nc.id)
                FROM narrative_chunks nc
                JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE (cm.season < :season)
                   OR (cm.season = :season AND cm.episode < :episode)
            """), {"season": season, "episode": episode}).scalar()
            
            if prev_episode_chunk:
                # Insert right after the previous episode's last chunk
                return prev_episode_chunk + 1
        
    # If we get here, just use the next available ID
    with engine.connect() as conn:
        # Check if the sequence exists
        seq_exists = conn.execute(text("""
            SELECT 1 FROM pg_sequences WHERE sequencename = 'narrative_chunks_id_seq'
        """)).scalar() is not None
        
        if seq_exists:
            next_id = conn.execute(text("""
                SELECT nextval('narrative_chunks_id_seq')
            """)).scalar()
        else:
            # If sequence doesn't exist, manually calculate next ID
            next_id = conn.execute(text("""
                SELECT COALESCE(MAX(id), 0) + 1 FROM narrative_chunks
            """)).scalar()
            logger.warning(f"Using calculated ID {next_id} because narrative_chunks_id_seq does not exist")
        
    return next_id

def update_chunk(engine: Engine, chunk_id: int, raw_text: str, dry_run: bool) -> bool:
    """
    Update a chunk's raw text.
    
    Args:
        engine: SQLAlchemy engine
        chunk_id: ID of the chunk to update
        raw_text: New text content
        dry_run: If True, don't actually make changes
        
    Returns:
        True if successful
    """
    if dry_run:
        logger.info(f"DRY RUN: Would update chunk {chunk_id} with {len(raw_text)} characters")
        return True
    
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE narrative_chunks
                SET raw_text = :text
                WHERE id = :id
            """), {"id": chunk_id, "text": raw_text})
        
        logger.info(f"Updated chunk {chunk_id} with {len(raw_text)} characters")
        return True
    except Exception as e:
        logger.error(f"Error updating chunk {chunk_id}: {e}")
        return False

def ensure_all_chunks_have_metadata(engine: Engine, dry_run: bool = False) -> bool:
    """
    Ensures all narrative chunks have corresponding metadata entries.
    
    Args:
        engine: SQLAlchemy engine
        dry_run: If True, only show what would be done
        
    Returns:
        True if successful
    """
    if dry_run:
        logger.info("DRY RUN: Would check for and create missing chunk metadata")
        return True
        
    try:
        with engine.begin() as conn:
            # Find chunks without metadata
            chunks_without_metadata = conn.execute(text("""
                SELECT nc.id, nc.raw_text 
                FROM narrative_chunks nc
                LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE cm.chunk_id IS NULL
            """)).fetchall()
            
            if not chunks_without_metadata:
                logger.info("All chunks have metadata entries")
                return True
                
            logger.info(f"Found {len(chunks_without_metadata)} chunks without metadata entries")
            
            # For each chunk without metadata, try to extract information from the text
            for chunk_id, raw_text in chunks_without_metadata:
                # Try to extract season, episode, scene from text
                scene_tag = None
                season = None
                episode = None
                scene = None
                
                # Look for scene break marker
                for line in raw_text.split('\n'):
                    scene_break_match = re.match(r'<!--\s*SCENE BREAK:\s*(S(\d+)E(\d+)_(\d+)).*-->', line)
                    if scene_break_match:
                        scene_tag = scene_break_match.group(1)
                        season = int(scene_break_match.group(2))
                        episode = int(scene_break_match.group(3))
                        scene = int(scene_break_match.group(4))
                        break
                
                if not scene_tag:
                    logger.error(f"Could not extract metadata from chunk {chunk_id}, raw text: {raw_text[:100]}...")
                    continue
                    
                logger.info(f"Extracted metadata for chunk {chunk_id}: {scene_tag} (S{season}E{episode}, scene {scene})")
                
                # Get next ID for metadata
                meta_id = conn.execute(text("""
                    SELECT COALESCE(MAX(id), 0) + 1 FROM chunk_metadata
                """)).scalar()
                
                # Insert metadata
                conn.execute(text(f"""
                    INSERT INTO chunk_metadata (id, chunk_id, season, episode, scene, world_layer)
                    VALUES ({meta_id}, {chunk_id}, {season}, {episode}, {scene}, 'primary')
                """))
                
                logger.info(f"Created metadata entry for chunk {chunk_id}")
                
            remaining_chunks = conn.execute(text("""
                SELECT COUNT(*)
                FROM narrative_chunks nc
                LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE cm.chunk_id IS NULL
            """)).scalar()
            
            if remaining_chunks > 0:
                logger.warning(f"There are still {remaining_chunks} chunks without metadata entries")
                return False
            else:
                logger.info("All chunks now have metadata entries")
                return True
                
    except Exception as e:
        logger.error(f"Error ensuring chunk metadata: {e}")
        return False

def resequence_all_chunks(engine: Engine, dry_run: bool = False, start_id: int = 1, increment: int = 1) -> bool:
    """
    Resequence all chunk IDs to be in correct chronological order.
    Also updates the chunk_metadata table to maintain referential integrity.
    
    Args:
        engine: SQLAlchemy engine
        dry_run: If True, only show what would be done
        start_id: First ID to use for resequencing
        increment: How much to increment each ID by
        
    Returns:
        True if successful
    """
    if dry_run:
        logger.info(f"DRY RUN: Would resequence all chunks starting at ID {start_id} with increment {increment}")
        return True
        
    try:
        with engine.begin() as conn:
            # First, create a temporary lookup table with ordered chunks
            logger.info("Creating temporary table with ordered chunk IDs")
            
            # Create the temp table
            conn.execute(text("""
                CREATE TEMPORARY TABLE temp_chunk_order AS
                SELECT 
                    ROW_NUMBER() OVER (
                        ORDER BY 
                            cm.season, 
                            cm.episode, 
                            cm.scene
                    ) * :increment + :start_id - :increment AS new_id,
                    nc.id AS old_id
                FROM 
                    narrative_chunks nc
                JOIN 
                    chunk_metadata cm ON nc.id = cm.chunk_id
                ORDER BY 
                    cm.season, 
                    cm.episode, 
                    cm.scene
            """), {"increment": increment, "start_id": start_id})
            
            # Count how many chunks need resequencing
            total_chunks = conn.execute(text("""
                SELECT COUNT(*) FROM temp_chunk_order
            """)).scalar()
            
            logger.info(f"Found {total_chunks} chunks to resequence")
            
            # If nothing to resequence, we're done
            if total_chunks == 0:
                logger.info("No chunks to resequence")
                return True
                
            # Verify we don't have duplicate new IDs (shouldn't happen but just to be safe)
            duplicates = conn.execute(text("""
                SELECT new_id, COUNT(*) 
                FROM temp_chunk_order 
                GROUP BY new_id 
                HAVING COUNT(*) > 1
            """)).fetchall()
            
            if duplicates:
                logger.error(f"Found duplicate new IDs: {duplicates}")
                return False
            
            # Create high temporary IDs (use 10M as base to avoid collisions)
            logger.info("Moving chunks to temporary high IDs")
            conn.execute(text("""
                UPDATE narrative_chunks
                SET id = id + 10000000
                WHERE id IN (SELECT old_id FROM temp_chunk_order)
            """))
            
            # Check that we moved everything correctly
            moved_count = conn.execute(text("""
                SELECT COUNT(*) FROM narrative_chunks WHERE id >= 10000000
            """)).scalar()
            
            if moved_count != total_chunks:
                logger.error(f"Moved {moved_count} chunks but expected {total_chunks}")
                # Don't proceed, this is a critical error
                return False
            
            # Now update with the new IDs
            logger.info("Assigning final sequential IDs")
            
            # For each chunk, update its ID based on the temp table
            result = conn.execute(text("""
                UPDATE narrative_chunks AS nc
                SET id = tco.new_id
                FROM temp_chunk_order AS tco
                WHERE nc.id = tco.old_id + 10000000
            """))
            
            updated_count = result.rowcount
            logger.info(f"Resequenced {updated_count} chunks")
            
            # Verify all rows were updated
            if updated_count != total_chunks:
                logger.error(f"Updated {updated_count} rows but expected {total_chunks}")
                return False
                
            # Drop the temp table
            conn.execute(text("DROP TABLE temp_chunk_order"))
            
            # Log the new sequence range
            highest_id = conn.execute(text("SELECT MAX(id) FROM narrative_chunks")).scalar()
            logger.info(f"Chunks now have IDs from {start_id} to {highest_id}")
            
            # Update the sequence value to be after our highest ID
            # First check if the sequence exists
            seq_exists = conn.execute(text("""
                SELECT 1 FROM pg_sequences WHERE sequencename = 'narrative_chunks_id_seq'
            """)).scalar() is not None
            
            if seq_exists:
                conn.execute(text(f"""
                    SELECT setval('narrative_chunks_id_seq', :value)
                """), {"value": highest_id + increment})
                logger.info(f"Reset sequence to {highest_id + increment}")
            else:
                logger.warning("narrative_chunks_id_seq does not exist, skipping sequence update")
            
            # Now resequence the chunk_metadata table's IDs in order
            logger.info("Resequencing chunk_metadata table IDs")
            
            # First check if there are any foreign key constraints on chunk_metadata.id
            logger.info("Checking for foreign key constraints on chunk_metadata.id")
            fk_constraints = conn.execute(text("""
                SELECT
                    tc.constraint_name,
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name,
                    rc.update_rule
                FROM
                    information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                      ON ccu.constraint_name = tc.constraint_name
                      AND ccu.table_schema = tc.table_schema
                    JOIN information_schema.referential_constraints AS rc
                      ON rc.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND ccu.table_name = 'chunk_metadata'
                  AND ccu.column_name = 'id';
            """)).fetchall()
            
            if fk_constraints:
                for constraint in fk_constraints:
                    table = constraint.table_name
                    column = constraint.column_name
                    update_rule = constraint.update_rule
                    logger.warning(f"Found FK constraint from {table}.{column} to chunk_metadata.id with update rule {update_rule}")
                    
                    if update_rule != 'CASCADE':
                        logger.error(f"Cannot safely resequence chunk_metadata IDs because {table}.{column} has a non-CASCADE update rule: {update_rule}")
                        logger.error("You may need to alter the constraint to add ON UPDATE CASCADE")
                        return False
                
                logger.info("All foreign key constraints have ON UPDATE CASCADE, proceeding with resequencing")
            
            # Create a temporary table for metadata ordering
            conn.execute(text("""
                CREATE TEMPORARY TABLE temp_metadata_order AS
                SELECT 
                    ROW_NUMBER() OVER (
                        ORDER BY 
                            cm.season, 
                            cm.episode, 
                            cm.scene
                    ) AS new_id,
                    cm.id AS old_id
                FROM 
                    chunk_metadata cm
                ORDER BY 
                    cm.season, 
                    cm.episode, 
                    cm.scene
            """))
            
            total_metadata = conn.execute(text("""
                SELECT COUNT(*) FROM temp_metadata_order
            """)).scalar()
            
            logger.info(f"Found {total_metadata} metadata records to resequence")
            
            # Move metadata to temporary high IDs
            conn.execute(text("""
                UPDATE chunk_metadata
                SET id = id + 10000000
                WHERE id IN (SELECT old_id FROM temp_metadata_order)
            """))
            
            # Update with new IDs
            result = conn.execute(text("""
                UPDATE chunk_metadata AS cm
                SET id = tmo.new_id
                FROM temp_metadata_order AS tmo
                WHERE cm.id = tmo.old_id + 10000000
            """))
            
            updated_metadata_count = result.rowcount
            logger.info(f"Resequenced {updated_metadata_count} metadata records")
            
            # Drop the temp table
            conn.execute(text("DROP TABLE temp_metadata_order"))
            
            # Update the metadata sequence
            highest_meta_id = conn.execute(text("SELECT MAX(id) FROM chunk_metadata")).scalar()
            
            # Check if sequence exists before updating it
            meta_seq_exists = conn.execute(text("""
                SELECT 1 FROM pg_sequences WHERE sequencename = 'chunk_metadata_id_seq'
            """)).scalar() is not None
            
            if meta_seq_exists:
                conn.execute(text(f"""
                    SELECT setval('chunk_metadata_id_seq', :value)
                """), {"value": highest_meta_id + 1})
                logger.info(f"Reset chunk_metadata sequence to {highest_meta_id + 1}")
            else:
                logger.warning("chunk_metadata_id_seq does not exist, skipping sequence update")
            
            return True
            
    except Exception as e:
        logger.error(f"Error resequencing chunks: {e}")
        return False

def reorganize_chunk_ids(engine: Engine, insertion_id: int, needed_gap: int = 1) -> bool:
    """
    Shift chunk IDs to make space for new chunks.
    
    Args:
        engine: SQLAlchemy engine
        insertion_id: ID where we want to insert
        needed_gap: How many consecutive IDs we need
        
    Returns:
        True if successful
    """
    try:
        with engine.begin() as conn:
            # Make sure we have enough room
            gap = needed_gap + 5  # Add some extra space
            
            # Check if there are chunks with IDs we'd overwrite
            count = conn.execute(text("""
                SELECT COUNT(*)
                FROM narrative_chunks
                WHERE id BETWEEN :start_id AND :end_id
            """), {"start_id": insertion_id, "end_id": insertion_id + gap - 1}).scalar()
            
            if count == 0:
                # Already have enough space!
                logger.info(f"Already have enough space at ID {insertion_id}")
                return True
            
            # Find the highest ID to shift by
            max_id = conn.execute(text("""
                SELECT MAX(id) FROM narrative_chunks
            """)).scalar()
            
            # Shift amount should be big enough to ensure no collisions
            shift = max(100, gap, max_id - insertion_id + 10)
            logger.info(f"Shifting IDs >= {insertion_id} by +{shift}")
            
            # Use a staging area to prevent collisions
            temp_id_base = 10000000
            
            # First shift to high temporary IDs
            conn.execute(text("""
                UPDATE narrative_chunks
                SET id = id + :temp_shift
                WHERE id >= :insertion_id
            """), {"temp_shift": temp_id_base, "insertion_id": insertion_id})
            
            # Then shift down to final position
            conn.execute(text("""
                UPDATE narrative_chunks
                SET id = (id - :temp_shift) + :shift
                WHERE id >= :temp_insertion_id
            """), {
                "temp_shift": temp_id_base,
                "shift": shift,
                "temp_insertion_id": temp_id_base + insertion_id
            })
            
            logger.info(f"Successfully shifted IDs to make room at {insertion_id}")
            return True
            
    except Exception as e:
        logger.error(f"Error reorganizing IDs: {e}")
        return False

def create_chunk(engine: Engine, tag: str, season: int, episode: int, scene: int, 
                raw_text: str, dry_run: bool) -> Optional[int]:
    """
    Create a new chunk in the proper chronological position.
    
    Args:
        engine: SQLAlchemy engine
        tag: Scene tag
        season: Season number
        episode: Episode number
        scene: Scene number
        raw_text: Text content
        dry_run: If True, don't actually make changes
        
    Returns:
        New chunk ID or None if failed
    """
    if dry_run:
        logger.info(f"DRY RUN: Would create new chunk for {tag}")
        return -1
    
    try:
        # Find the appropriate insertion point for chronological ordering
        insertion_id = find_insertion_point(engine, season, episode, scene)
        logger.info(f"Determined insertion point {insertion_id} for {tag}")
        
        # Make sure we have room at this location
        if not reorganize_chunk_ids(engine, insertion_id, 1):
            # If reorganization fails, fall back to using next sequence value
            with engine.connect() as conn:
                insertion_id = conn.execute(text("SELECT nextval('narrative_chunks_id_seq')")).scalar()
                logger.info(f"Using sequence value {insertion_id} for {tag} after reorganization failed")
            
        with engine.begin() as conn:
            # Insert the narrative chunk at the determined position
            conn.execute(text("""
                INSERT INTO narrative_chunks (id, raw_text)
                VALUES (:id, :text)
            """), {"id": insertion_id, "text": raw_text})
            
            # Get next ID for metadata
            meta_id = conn.execute(text("""
                SELECT COALESCE(MAX(id), 0) + 1 FROM chunk_metadata
            """)).scalar()
            
            # Insert metadata (using string interpolation to avoid sequence issues)
            conn.execute(text(f"""
                INSERT INTO chunk_metadata (id, chunk_id, season, episode, scene, world_layer)
                VALUES ({meta_id}, {insertion_id}, {season}, {episode}, {scene}, 'primary')
            """))
        
        logger.info(f"Created new chunk {insertion_id} for {tag}")
        return insertion_id
    except Exception as e:
        logger.error(f"Error creating chunk for {tag}: {e}")
        return None

def process_file(engine: Engine, file_path: Path, dry_run: bool, verbose: bool = False) -> Tuple[int, int, int]:
    """
    Process a single file.
    
    Args:
        engine: SQLAlchemy engine
        file_path: Path to markdown file
        dry_run: If True, don't actually make changes
        verbose: If True, print verbose debug information
        
    Returns:
        Tuple of (updated, created, errors)
    """
    updated, created, errors = 0, 0, 0
    skipped = []
    
    # Parse the file
    chunks = parse_file(file_path)
    
    # Print all chunk tags for debugging
    chunk_tags = sorted(chunks.keys())
    if verbose:
        logger.info(f"Found these chunks: {chunk_tags}")
    else:
        logger.info(f"Found {len(chunks)} chunks with tags from {chunk_tags[0]} to {chunk_tags[-1]}")
    
    # Process each chunk
    for tag, data in chunks.items():
        _, season, episode, scene = data['metadata']
        text = data['text']
        
        if verbose:
            logger.info(f"Processing chunk: {tag} (Season {season}, Episode {episode}, Scene {scene})")
            if len(text) > 100:
                logger.info(f"Text snippet: {text[:100]}...")
            else:
                logger.info(f"Text: {text}")
        
        # Try to find the chunk
        chunk_id = find_chunk_id(engine, season, episode, scene)
        
        if chunk_id:
            # Update existing chunk
            if verbose:
                logger.info(f"Found existing chunk with ID {chunk_id}")
            if update_chunk(engine, chunk_id, text, dry_run):
                updated += 1
                if verbose:
                    logger.info(f"Successfully updated chunk {tag}")
            else:
                errors += 1
                skipped.append(tag)
                logger.warning(f"Failed to update chunk {tag}")
        else:
            # Create new chunk
            if verbose:
                logger.info(f"No existing chunk found for {tag}, creating new chunk")
            new_id = create_chunk(engine, tag, season, episode, scene, text, dry_run)
            if new_id:
                created += 1
                if verbose:
                    logger.info(f"Successfully created chunk {tag} with ID {new_id}")
            else:
                errors += 1
                skipped.append(tag)
                logger.warning(f"Failed to create chunk {tag}")
    
    if skipped:
        logger.warning(f"Skipped chunks: {', '.join(skipped)}")
    
    return updated, created, errors

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Simple script to update raw text in narrative chunks")
    
    parser.add_argument("file_paths", nargs="+", help="Markdown files to process")
    parser.add_argument("--db-url", default="postgresql://pythagor@localhost/NEXUS",
                      help="Database URL (default: postgresql://pythagor@localhost/NEXUS)")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually update the database")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose debug information")
    parser.add_argument("--fix-metadata", action="store_true",
                      help="Find and fix missing metadata entries for chunks")
    parser.add_argument("--resequence", action="store_true", 
                      help="Resequence all chunk IDs in chronological order after updates")
    
    args = parser.parse_args()
    
    # Initialize database connection
    engine = create_engine(args.db_url)
    
    # Expand file patterns
    all_files = []
    for pattern in args.file_paths:
        if '*' in pattern:
            matching = glob.glob(pattern)
            all_files.extend(matching)
        else:
            all_files.append(pattern)
    
    if not all_files:
        logger.error(f"No files found matching patterns: {args.file_paths}")
        return 1
    
    # Process files
    total_updated = 0
    total_created = 0
    total_errors = 0
    
    for file_path in all_files:
        logger.info(f"Processing {file_path}")
        try:
            updated, created, errors = process_file(engine, Path(file_path), args.dry_run, args.verbose)
            total_updated += updated
            total_created += created
            total_errors += errors
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            total_errors += 1
    
    # Fix missing metadata if requested
    if args.fix_metadata:
        print("\nChecking for chunks without metadata entries...")
        
        # First count how many chunks are missing metadata
        with engine.connect() as conn:
            missing_count = conn.execute(text("""
                SELECT COUNT(*)
                FROM narrative_chunks nc
                LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE cm.chunk_id IS NULL
            """)).scalar()
        
        if missing_count == 0:
            print("All chunks already have metadata entries!")
        else:
            print(f"Found {missing_count} chunks without metadata entries")
            
            if ensure_all_chunks_have_metadata(engine, args.dry_run):
                if not args.dry_run:
                    print("All chunks now have metadata entries!")
                else:
                    print("DRY RUN: Would ensure all chunks have metadata entries")
            else:
                if not args.dry_run:
                    print("Some chunks still don't have metadata entries. See log for details.")
                    total_errors += 1
                else:
                    print("DRY RUN: Would attempt to fix missing metadata entries")
    
    # Resequence all chunks if requested
    if args.resequence and not args.dry_run:
        print("\nResequencing all chunks in chronological order...")
        if resequence_all_chunks(engine, args.dry_run, start_id=1, increment=1):
            print("Resequencing successful!")
        else:
            print("Resequencing failed. See log for details.")
            total_errors += 1
    elif args.resequence and args.dry_run:
        print("\nDRY RUN: Would resequence all chunks in chronological order")
    
    # Print summary
    print("\nUpdate Summary:")
    print(f"Files processed: {len(all_files)}")
    print(f"Chunks updated: {total_updated}")
    print(f"Chunks created: {total_created}")
    
    # Report metadata fixes if that option was used
    if args.fix_metadata:
        with engine.connect() as conn:
            missing_after = conn.execute(text("""
                SELECT COUNT(*)
                FROM narrative_chunks nc
                LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE cm.chunk_id IS NULL
            """)).scalar()
            
            if not args.dry_run:
                fixed_count = missing_count - missing_after
                if fixed_count > 0:
                    print(f"Metadata entries created: {fixed_count}")
                if missing_after > 0:
                    print(f"Chunks still missing metadata: {missing_after}")
            else:
                if missing_count > 0:
                    print(f"Would create metadata for {missing_count} chunks (dry run)")
    
    # Report resequencing if that option was used
    if args.resequence:
        if not args.dry_run:
            with engine.connect() as conn:
                chunk_count = conn.execute(text("SELECT COUNT(*) FROM narrative_chunks")).scalar()
                meta_count = conn.execute(text("SELECT COUNT(*) FROM chunk_metadata")).scalar()
                print(f"Chunks resequenced: {chunk_count}")
                print(f"Metadata records resequenced: {meta_count}")
        else:
            print("Would resequence all chunks and metadata records (dry run)")
    
    print(f"Errors: {total_errors}")
    
    if args.dry_run:
        print("\nDRY RUN: No changes were made to the database")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())