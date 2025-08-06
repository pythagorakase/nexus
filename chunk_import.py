#!/usr/bin/env python3
"""
chunk_import.py - Import markdown files with scene breaks into a PostgreSQL database.
"""

import argparse
import glob
import os
import re
import sys
import uuid
from typing import List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session

# Create the SQLAlchemy ORM base
Base = declarative_base()

# Define the ORM models
class NarrativeChunk(Base):
    __tablename__ = 'narrative_chunks'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_text = Column(Text, nullable=False)
    
    # Relationship to metadata
    metadata = relationship("ChunkMetadata", back_populates="chunk", uselist=False)
    
    def __repr__(self):
        return f"<NarrativeChunk(id={self.id})>"


class ChunkMetadata(Base):
    __tablename__ = 'chunk_metadata'
    
    chunk_id = Column(UUID(as_uuid=True), ForeignKey('narrative_chunks.id'), primary_key=True)
    season = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)
    scene_number = Column(Integer, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    
    # Relationship to narrative chunk
    chunk = relationship("NarrativeChunk", back_populates="metadata")
    
    def __repr__(self):
        return f"<ChunkMetadata(slug={self.slug}, season={self.season}, episode={self.episode}, scene_number={self.scene_number})>"


class Chunk:
    """Class representing a chunk of text from a markdown file."""
    
    def __init__(self, slug: str, season: int, episode: int, scene_number: int, raw_text: str):
        self.slug = slug
        self.season = season
        self.episode = episode
        self.scene_number = scene_number
        self.raw_text = raw_text
    
    def __repr__(self):
        return f"<Chunk(slug={self.slug})>"


def parse_scene_break(line: str) -> Optional[Tuple[str, int, int, int]]:
    """
    Parse a scene break line and extract the slug and metadata.
    Returns (slug, season, episode, scene_number) or None if the line isn't a scene break.
    """
    scene_break_pattern = r'<!-- SCENE BREAK: (S(\d+)E(\d+)_(\d+)).*-->'
    match = re.match(scene_break_pattern, line)
    
    if match:
        slug = match.group(1)
        season = int(match.group(2))
        episode = int(match.group(3))
        scene_number = int(match.group(4))
        return slug, season, episode, scene_number
    
    return None


def parse_markdown_file(file_path: str) -> List[Chunk]:
    """
    Parse a markdown file and extract chunks based on scene breaks.
    """
    chunks = []
    current_slug = None
    current_season = None
    current_episode = None
    current_scene_number = None
    current_text = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Check if line is a scene break
            scene_break_info = parse_scene_break(line)
            
            if scene_break_info:
                # If we have an existing chunk, save it
                if current_slug:
                    chunk = Chunk(
                        slug=current_slug,
                        season=current_season,
                        episode=current_episode,
                        scene_number=current_scene_number,
                        raw_text=''.join(current_text)
                    )
                    chunks.append(chunk)
                
                # Start a new chunk
                current_slug, current_season, current_episode, current_scene_number = scene_break_info
                current_text = [line]  # Include the scene break line
            elif current_slug:  # Only add text if we're inside a chunk
                current_text.append(line)
    
    # Add the last chunk if there is one
    if current_slug:
        chunk = Chunk(
            slug=current_slug,
            season=current_season,
            episode=current_episode,
            scene_number=current_scene_number,
            raw_text=''.join(current_text)
        )
        chunks.append(chunk)
    
    return chunks


def save_chunks_to_db(chunks: List[Chunk], session: Session):
    """
    Save chunks to the database.
    """
    for chunk in chunks:
        # Create a new NarrativeChunk
        narrative_chunk = NarrativeChunk(raw_text=chunk.raw_text)
        
        # Create the associated metadata
        chunk_metadata = ChunkMetadata(
            chunk=narrative_chunk,
            season=chunk.season,
            episode=chunk.episode,
            scene_number=chunk.scene_number,
            slug=chunk.slug
        )
        
        # Add both to the session
        session.add(narrative_chunk)
        session.add(chunk_metadata)
    
    # Commit the session
    session.commit()


def main():
    parser = argparse.ArgumentParser(description='Import markdown files with scene breaks into a PostgreSQL database.')
    parser.add_argument('files', nargs='*', help='Markdown files to process')
    parser.add_argument('--db-url', help='Database URL', default='postgresql://postgres:postgres@localhost/nexus')
    args = parser.parse_args()
    
    # Get the list of files to process
    files_to_process = args.files
    if not files_to_process:
        # If no files specified, use all markdown files in the current directory
        files_to_process = glob.glob('*.md')
    
    if not files_to_process:
        print("No files to process.")
        sys.exit(1)
    
    # Connect to the database
    engine = create_engine(args.db_url)
    
    # Create tables if they don't exist
    Base.metadata.create_all(engine)
    
    # Create a session
    Session = sa.orm.sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Process each file
        for file_path in files_to_process:
            print(f"Processing {file_path}...")
            chunks = parse_markdown_file(file_path)
            print(f"Found {len(chunks)} chunks.")
            
            # Save chunks to the database
            save_chunks_to_db(chunks, session)
            
            print(f"Successfully imported {len(chunks)} chunks from {file_path}.")
        
        print("All files processed successfully.")
    
    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
        sys.exit(1)
    
    finally:
        session.close()


if __name__ == "__main__":
    main()

# Future enhancement: Add pgvector support
# To extend this script to support pgvector for embeddings:
# 1. Install the pgvector extension in PostgreSQL
# 2. Add the following imports:
#    from sqlalchemy.dialects.postgresql import VECTOR
# 3. Add embedding column to NarrativeChunk model:
#    embedding = Column(VECTOR(1536))  # Assuming 1536-dimensional embeddings
# 4. Add function to generate embeddings from text
# 5. Update save_chunks_to_db to include embedding generation 