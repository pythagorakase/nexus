#!/usr/bin/env python3
"""
Extract Season and Episode Information Script for NEXUS

This script extracts season and episode information from the narrative chunks
based on their raw text, and updates the chunk_metadata table with these values.
No API calls are required since this is entirely based on parsing the text.

Usage:
    python extract_season_episode.py --all
    python extract_season_episode.py --missing
    python extract_season_episode.py --range 1 100
    python extract_season_episode.py --dry-run
"""

import os
import sys
import argparse
import logging
import re
import json
import uuid
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, Text, DateTime, inspect
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("season_episode_extraction.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.season_episode")

# Initialize database connection
Base = declarative_base()

def get_db_connection_string():
    """Get the database connection string from environment variables or defaults."""
    DB_USER = os.environ.get("DB_USER", "pythagor")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME", "NEXUS")
    
    # Build connection string (with password if provided)
    if DB_PASSWORD:
        return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        return f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Define ORM models
class NarrativeChunk(Base):
    __tablename__ = 'narrative_chunks'
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    sequence = Column(Integer, unique=True, nullable=False)
    raw_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    # Relationship to metadata (will set up after defining ChunkMetadata)

class ChunkMetadata(Base):
    __tablename__ = 'chunk_metadata'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey('narrative_chunks.id', ondelete='CASCADE'), nullable=False, unique=True)
    
    # We only care about season and episode for this script
    world_layer = Column(String(50))
    season = Column(Integer)
    episode = Column(Integer)
    
    # All other fields are defined here to match the table structure
    location = Column(String(255))
    atmosphere = Column(String(255))
    time_delta = Column(String(100))
    characters = Column(JSONB)
    arc_position = Column(String(50))
    direction = Column(JSONB)
    magnitude = Column(String(50))
    character_elements = Column(JSONB)
    perspective = Column(JSONB)
    interactions = Column(JSONB)
    dialogue_analysis = Column(JSONB)
    emotional_tone = Column(JSONB)
    narrative_function = Column(JSONB)
    narrative_techniques = Column(JSONB)
    thematic_elements = Column(JSONB)
    causality = Column(JSONB)
    continuity_markers = Column(JSONB)
    metadata_version = Column(String(20))
    generation_date = Column(DateTime, default=func.now())
    
    # Relationship to parent chunk
    chunk = relationship("NarrativeChunk", backref="metadata")

# Set up relationship now that both models are defined
NarrativeChunk.metadata_relationship = relationship("ChunkMetadata", backref="narrative_chunk", uselist=False)

class SeasonEpisodeExtractor:
    """Extracts season and episode information from narrative chunks and updates the database."""
    
    def __init__(self, db_url: str, dry_run: bool = False):
        """
        Initialize the extractor.
        
        Args:
            db_url: PostgreSQL database URL
            dry_run: If True, don't actually save results to the database
        """
        self.db_url = db_url
        self.dry_run = dry_run
        
        # Initialize database connection
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
        
        # Initialize the database schema if needed
        self.initialize_database()
        
        # Statistics
        self.stats = {
            "total_chunks": 0,
            "extracted_values": 0,
            "created_metadata": 0,
            "updated_metadata": 0,
            "failed_extractions": 0
        }
    
    def initialize_database(self):
        """Initialize database tables if they don't exist."""
        # Create chunk_metadata table if it doesn't exist
        inspector = inspect(self.engine)
        
        if 'chunk_metadata' not in inspector.get_table_names():
            ChunkMetadata.__table__.create(self.engine)
            logger.info("Created chunk_metadata table")
    
    def extract_season_episode(self, raw_text: str) -> Tuple[int, int, str]:
        """
        Extract season and episode information from raw text.
        
        Args:
            raw_text: The raw text of a chunk
            
        Returns:
            Tuple of (season, episode, scene_id)
        """
        # Look for scene break marker with S00E00_000 format
        scene_break_pattern = r'<!-- SCENE BREAK: (S(\d+)E(\d+)_(\d+)).*?-->'
        match = re.search(scene_break_pattern, raw_text)
        
        if match:
            scene_id = match.group(1)  # Full ID like S01E01_001
            season = int(match.group(2))  # Season number
            episode = int(match.group(3))  # Episode number
            return season, episode, scene_id
        
        # Secondary pattern - look for # S00E00: Title format
        title_pattern = r'# S(\d+)E(\d+):'
        match = re.search(title_pattern, raw_text)
        
        if match:
            season = int(match.group(1))
            episode = int(match.group(2))
            return season, episode, f"S{season:02d}E{episode:02d}"
        
        # If no match found, return defaults
        self.stats["failed_extractions"] += 1
        return 1, 1, "S01E01"
    
    def get_chunks_by_sequence_range(self, start: int, end: int) -> List[NarrativeChunk]:
        """Get chunks within a sequence range."""
        session = self.Session()
        try:
            chunks = session.query(NarrativeChunk)\
                .filter(NarrativeChunk.sequence >= start)\
                .filter(NarrativeChunk.sequence <= end)\
                .order_by(NarrativeChunk.sequence).all()
            return chunks
        finally:
            session.close()
    
    def get_all_chunks(self) -> List[NarrativeChunk]:
        """Get all narrative chunks ordered by sequence."""
        session = self.Session()
        try:
            chunks = session.query(NarrativeChunk).order_by(NarrativeChunk.sequence).all()
            return chunks
        finally:
            session.close()
    
    def get_chunks_without_metadata(self) -> List[NarrativeChunk]:
        """Get all chunks that don't have metadata yet."""
        session = self.Session()
        try:
            # Query for chunks that don't have a related metadata record
            chunks = session.query(NarrativeChunk)\
                .outerjoin(ChunkMetadata, NarrativeChunk.id == ChunkMetadata.chunk_id)\
                .filter(ChunkMetadata.id == None)\
                .order_by(NarrativeChunk.sequence).all()
            return chunks
        finally:
            session.close()
    
    def process_chunks(self, chunks: List[NarrativeChunk]) -> Dict[str, Any]:
        """
        Process narrative chunks to extract season and episode.
        
        Args:
            chunks: List of narrative chunks to process
            
        Returns:
            Statistics dictionary
        """
        self.stats["total_chunks"] = len(chunks)
        
        if self.stats["total_chunks"] == 0:
            logger.info("No chunks to process")
            return self.stats
        
        logger.info(f"Processing {self.stats['total_chunks']} chunks")
        
        # Process each chunk
        session = self.Session()
        try:
            for chunk in chunks:
                # Extract season and episode from text
                season, episode, scene_id = self.extract_season_episode(chunk.raw_text)
                self.stats["extracted_values"] += 1
                
                logger.info(f"Chunk {chunk.sequence}: Extracted S{season:02d}E{episode:02d} ({scene_id})")
                
                if not self.dry_run:
                    # Check if metadata already exists for this chunk
                    metadata = session.query(ChunkMetadata).filter(ChunkMetadata.chunk_id == chunk.id).first()
                    
                    if metadata:
                        # Update existing metadata
                        metadata.season = season
                        metadata.episode = episode
                        metadata.generation_date = datetime.now()
                        self.stats["updated_metadata"] += 1
                    else:
                        # Create new metadata
                        new_metadata = ChunkMetadata(
                            chunk_id=chunk.id,
                            season=season,
                            episode=episode,
                            world_layer="primary",  # Default value
                            metadata_version="1.0.0",
                            generation_date=datetime.now()
                        )
                        session.add(new_metadata)
                        self.stats["created_metadata"] += 1
            
            # Commit changes if not dry run
            if not self.dry_run:
                session.commit()
                logger.info(f"Committed {self.stats['updated_metadata']} updates and " 
                          f"{self.stats['created_metadata']} new metadata records")
        
        except Exception as e:
            if not self.dry_run:
                session.rollback()
            logger.error(f"Error processing chunks: {str(e)}")
        finally:
            session.close()
        
        return self.stats

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Extract season and episode information from narrative chunks")
    
    # Target chunk selection arguments
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Process all chunks")
    group.add_argument("--missing", action="store_true", help="Process only chunks without metadata")
    group.add_argument("--range", nargs=2, type=int, metavar=("START", "END"),
                     help="Process chunks in a sequence range (inclusive)")
    
    # Processing options
    parser.add_argument("--dry-run", action="store_true", 
                      help="Don't actually save results to the database")
    parser.add_argument("--db-url", help="Database connection URL (optional)")
    
    args = parser.parse_args()
    
    # Get database connection string
    db_url = args.db_url or get_db_connection_string()
    
    # Initialize extractor
    extractor = SeasonEpisodeExtractor(db_url=db_url, dry_run=args.dry_run)
    
    # Get chunks to process
    if args.all:
        logger.info("Processing all chunks")
        chunks = extractor.get_all_chunks()
    elif args.missing:
        logger.info("Processing chunks without metadata")
        chunks = extractor.get_chunks_without_metadata()
    elif args.range:
        start, end = args.range
        logger.info(f"Processing chunks in sequence range {start}-{end}")
        chunks = extractor.get_chunks_by_sequence_range(start, end)
    
    # Process chunks
    stats = extractor.process_chunks(chunks)
    
    # Print summary
    logger.info("\nProcessing Summary:")
    logger.info(f"Total chunks processed: {stats['total_chunks']}")
    logger.info(f"Successfully extracted values: {stats['extracted_values']}")
    if args.dry_run:
        logger.info("DRY RUN: No changes were made to the database")
    else:
        logger.info(f"Created new metadata records: {stats['created_metadata']}")
        logger.info(f"Updated existing metadata records: {stats['updated_metadata']}")
    if stats["failed_extractions"] > 0:
        logger.warning(f"Failed extractions (using defaults): {stats['failed_extractions']}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())