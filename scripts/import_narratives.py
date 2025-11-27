#!/usr/bin/env python3
"""
Import Narrative Script for NEXUS

Processes markdown files containing scene breaks and imports them into 
the PostgreSQL database with vector embeddings.

Usage:
    python import_narratives.py [file_pattern]

Example:
    python import_narratives.py ALEX_*_copy_notime.md
"""

import os
import sys
import re
import glob
import uuid
import json
from pathlib import Path
import argparse
import logging
from typing import Dict, Any, List, Optional, Union

# Add parent directory to sys.path to import from nexus package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Try to load settings using centralized config loader
try:
    from nexus.config import load_settings_as_dict
    _all_settings = load_settings_as_dict()
    SETTINGS = _all_settings.get("Agent Settings", {}).get("MEMNON", {})
except Exception as e:
    print(f"Warning: Could not load settings via config loader: {e}")
    SETTINGS = {}

# Configure logging from settings
log_file = SETTINGS.get("logging", {}).get("file", "memnon.log")
log_level_str = SETTINGS.get("logging", {}).get("level", "INFO")
log_console = SETTINGS.get("logging", {}).get("console", True)

# Convert string log level to logging constant
log_level = getattr(logging, log_level_str.upper(), logging.INFO)

# Set up handlers
handlers = []
if log_file:
    handlers.append(logging.FileHandler(log_file))
if log_console:
    handlers.append(logging.StreamHandler())

logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=handlers
)
logger = logging.getLogger("nexus.import")

# Try to import sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    logger.error("sentence-transformers not found. Please install with: pip install sentence-transformers")
    sys.exit(1)

# Try to import SQLAlchemy
try:
    import sqlalchemy as sa
    from sqlalchemy import create_engine, Column, ForeignKey, String, Text
    from sqlalchemy.dialects.postgresql import UUID, BYTEA
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker
except ImportError:
    logger.error("SQLAlchemy not found. Please install with: pip install sqlalchemy")
    sys.exit(1)

# Try to import pgvector
try:
    import pgvector
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    logger.warning("pgvector not found. Will use basic storage method.")
    HAS_PGVECTOR = False

# Define SQL Alchemy Base
Base = declarative_base()

# Define ORM models based on the PostgreSQL schema
class NarrativeChunk(Base):
    __tablename__ = 'narrative_chunks'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sequence = Column(sa.BigInteger, sa.Sequence('narrative_chunks_sequence_seq'), unique=True, nullable=False)
    raw_text = Column(Text, nullable=False)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())

try:
    # Try to import pgvector Vector type
    from pgvector.sqlalchemy import Vector as PgVector
    # Set global flag that we have pgvector available
    HAS_PGVECTOR_TYPE = True
except ImportError:
    # If pgvector is not available, create a dummy type
    PgVector = BYTEA
    HAS_PGVECTOR_TYPE = False

class ChunkEmbedding(Base):
    __tablename__ = 'chunk_embeddings'
    
    id = Column(sa.BigInteger, primary_key=True, autoincrement=True)
    chunk_id = Column(UUID(as_uuid=True), sa.ForeignKey('narrative_chunks.id', ondelete='CASCADE'), nullable=False)
    model = Column(String(100), nullable=False)
    # Store embeddings with flexible dimensions (automatically handled by pgvector)
    embedding = Column(Vector(1024), nullable=False)
    dimensions = Column(sa.Integer, default=1024, nullable=False)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    
    # Create a unique constraint to ensure we don't have duplicates
    __table_args__ = (sa.UniqueConstraint('chunk_id', 'model', name='uix_chunk_model'),)

# Legacy table definition maintained for reference
# This class is no longer actively used as all embeddings are now in chunk_embeddings
# with the dimensions column differentiating between 1024D and 384D vectors
class ChunkEmbeddingSmall(Base):
    __tablename__ = 'chunk_embeddings_small'
    
    id = Column(sa.BigInteger, primary_key=True, autoincrement=True)
    chunk_id = Column(UUID(as_uuid=True), sa.ForeignKey('narrative_chunks.id', ondelete='CASCADE'), nullable=False)
    model = Column(String(100), nullable=False)
    # Store embeddings for BGE-Small models (384 dimensions)
    embedding = Column(Vector(384), nullable=False)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    
    # Create a unique constraint to ensure we don't have duplicates
    __table_args__ = (sa.UniqueConstraint('chunk_id', 'model', name='uix_chunk_model_small'),)

class ChunkMetadata(Base):
    __tablename__ = 'chunk_metadata'
    
    chunk_id = Column(UUID(as_uuid=True), sa.ForeignKey('narrative_chunks.id', ondelete='CASCADE'), primary_key=True)
    world_layer = Column(sa.Enum('primary', 'flashback', 'dream', 'extradimensional', 'non_canonical', 
                               name='world_layer_type', create_type=False))
    setting = Column(sa.JSON)
    season = Column(sa.Integer)
    episode = Column(sa.Integer)
    time_delta = Column(sa.Interval, nullable=False, server_default='0 minutes')
    narrative_vector = Column(sa.JSON)
    characters = Column(sa.JSON)
    prose = Column(sa.JSON)
    causality = Column(sa.JSON)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())

class NarrativeImporter:
    """Standalone implementation of narrative importing functionality"""
    
    def __init__(self, db_url: str = None):
        """
        Initialize the importer with database connection.
        
        Args:
            db_url: PostgreSQL database URL
        """
        # Set default database URL if not provided
        default_db_url = SETTINGS.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
        self.db_url = db_url or os.environ.get("NEXUS_DB_URL", default_db_url)
        
        # Initialize database connection
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
        
        # First make sure pgvector extension is available
        with self.engine.connect() as connection:
            connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))
            connection.commit()
            logger.info("Created pgvector extension in database")
        
        # Check if we should drop and recreate tables
        create_tables = SETTINGS.get("database", {}).get("create_tables", True)
        drop_existing = SETTINGS.get("database", {}).get("drop_existing", False)
        
        if drop_existing:
            # Drop existing tables in reverse dependency order
            try:
                ChunkEmbedding.__table__.drop(self.engine, checkfirst=True)
                ChunkEmbeddingSmall.__table__.drop(self.engine, checkfirst=True)
                ChunkMetadata.__table__.drop(self.engine, checkfirst=True)
                NarrativeChunk.__table__.drop(self.engine, checkfirst=True)
                logger.info("Dropped existing tables")
            except Exception as e:
                logger.warning(f"Error dropping tables: {e}")
        
        if create_tables:
            # Create tables
            Base.metadata.create_all(self.engine)
            logger.info("Created tables with updated schema")
        
        # Initialize embedding models
        self.embedding_models = self._initialize_embedding_models()
        
        logger.info(f"Connected to database: {self.db_url}")
        logger.info(f"Initialized {len(self.embedding_models)} embedding models")
    
    def _initialize_embedding_models(self) -> Dict[str, Any]:
        """Initialize embedding models for semantic retrieval."""
        embedding_models = {}
        
        # Define model paths from settings, falling back to defaults if not available
        settings_models = SETTINGS.get("models", {})
        
        model_paths = {
            "bge-large": [
                Path(settings_models.get("bge-large", {}).get("local_path", "/Users/pythagor/nexus/models/models--BAAI--bge-large-en")),
                settings_models.get("bge-large", {}).get("remote_path", "BAAI/bge-large-en")
            ],
            "e5-large": [
                Path(settings_models.get("e5-large", {}).get("local_path", "/Users/pythagor/nexus/models/models--intfloat--e5-large-v2")),
                settings_models.get("e5-large", {}).get("remote_path", "intfloat/e5-large-v2")
            ],
            "bge-small-custom": [
                Path(settings_models.get("bge-small-custom", {}).get("local_path", "/Users/pythagor/nexus/models/bge_small_finetuned_20250320_153654")),
                settings_models.get("bge-small-custom", {}).get("remote_path")  # May be None
            ],
            "bge-small": [
                None,  # No local path for standard model
                "BAAI/bge-small-en"
            ]
        }
        
        try:
            # Try to load each model
            for model_key, paths in model_paths.items():
                local_path, remote_path = paths
                
                # Skip if this is the standard BGE-small and we already have the custom one
                if model_key == "bge-small" and "bge-small-custom" in embedding_models:
                    continue
                
                # Try local path first if it exists
                if local_path and local_path.exists():
                    try:
                        logger.info(f"Loading {model_key} from local path: {local_path}")
                        model = SentenceTransformer(str(local_path))
                        embedding_models[model_key] = model
                        logger.info(f"Successfully loaded {model_key} from local path")
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load {model_key} from local path: {e}")
                
                # Fall back to remote path if available
                if remote_path:
                    try:
                        logger.info(f"Loading {model_key} from HuggingFace: {remote_path}")
                        model = SentenceTransformer(remote_path)
                        embedding_models[model_key] = model
                        logger.info(f"Successfully loaded {model_key} from HuggingFace")
                    except Exception as e:
                        logger.warning(f"Failed to load {model_key} from HuggingFace: {e}")
            
            # Log summary of loaded models
            if embedding_models:
                logger.info(f"Loaded {len(embedding_models)} embedding models: {', '.join(embedding_models.keys())}")
            else:
                logger.error("Failed to load any embedding models")
            
            return embedding_models
        
        except Exception as e:
            logger.error(f"Error in embedding model initialization process: {e}")
            # Return any successfully loaded models rather than failing completely
            return embedding_models
    
    def generate_embedding(self, text: str, model_key: str) -> List[float]:
        """
        Generate an embedding for the given text using the specified model.
        
        Args:
            text: Text to embed
            model_key: Key of the model to use
            
        Returns:
            Embedding as a list of floats
        """
        if model_key not in self.embedding_models:
            logger.error(f"Model {model_key} not found in available embedding models")
            raise ValueError(f"Model {model_key} not found in available embedding models")
        
        model = self.embedding_models[model_key]
        embedding = model.encode(text)
        
        return embedding.tolist()
    
    def process_chunked_file(self, file_path: Union[str, Path]) -> int:
        """
        Process a chunked file containing scene breaks and narrative text.
        Extracts each chunk, generates embeddings, and stores in the database.
        
        Args:
            file_path: Path to the markdown file
            
        Returns:
            Number of chunks processed
        """
        # Convert to Path if string
        if isinstance(file_path, str):
            file_path = Path(file_path)
        
        # Ensure file exists
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return 0
        
        # Regex for scene breaks
        scene_break_regex = re.compile(r'<!--\s*SCENE BREAK:\s*(S(\d+)E(\d+))_(\d+).*-->')
        
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find all scene breaks
        scene_breaks = list(scene_break_regex.finditer(content))
        if not scene_breaks:
            logger.warning(f"No scene breaks found in {file_path}")
            return 0
        
        chunks_processed = 0
        
        # Process each chunk
        for i in range(len(scene_breaks)):
            start_match = scene_breaks[i]
            
            # Extract metadata from the scene break
            episode_str = start_match.group(1)  # e.g., "S01E05"
            season = int(start_match.group(2))
            episode = int(start_match.group(3))
            scene_number = int(start_match.group(4))
            
            # Construct the chunk tag (human-readable ID)
            chunk_tag = f"{episode_str}_{scene_number:03d}"
            
            # Generate a stable UUID based on the chunk tag
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_tag))
            
            # Determine chunk boundaries
            start_pos = start_match.start()
            if i < len(scene_breaks) - 1:
                end_pos = scene_breaks[i + 1].start()
            else:
                end_pos = len(content)
            
            # Extract chunk text
            chunk_text = content[start_pos:end_pos]
            
            # Store the chunk with metadata
            try:
                self.store_narrative_chunk(
                    chunk_text=chunk_text,
                    metadata={
                        "chunk_id": chunk_id,
                        "chunk_tag": chunk_tag,
                        "season": season,
                        "episode": episode,
                        "scene_number": scene_number,
                        "world_layer": "primary"  # Default to primary world layer
                    }
                )
                chunks_processed += 1
                logger.info(f"Processed chunk {chunk_id} from {file_path.name}")
            
            except Exception as e:
                logger.error(f"Error processing chunk {chunk_id} from {file_path.name}: {e}")
        
        logger.info(f"Completed processing {chunks_processed} chunks from {file_path}")
        return chunks_processed
    
    def store_narrative_chunk(self, chunk_text: str, metadata: Dict[str, Any]) -> str:
        """
        Store a narrative chunk with embeddings and metadata in PostgreSQL.
        
        Args:
            chunk_text: The text content of the chunk
            metadata: Associated metadata (season, episode, scene_number, etc.)
            
        Returns:
            ID of the stored chunk
        """
        # Create a session
        session = self.Session()
        
        try:
            # Extract or generate chunk ID
            if "chunk_id" in metadata:
                chunk_id_str = metadata["chunk_id"]
                # Convert string to UUID object
                chunk_id = uuid.UUID(chunk_id_str)
                
                # Remove any existing chunk with this ID
                existing = session.query(NarrativeChunk).filter_by(id=chunk_id).first()
                if existing:
                    logger.info(f"Replacing existing chunk {chunk_id_str}")
                    session.delete(existing)
                    session.commit()
            else:
                # Generate a UUID for the chunk
                chunk_id = uuid.uuid4()
            
            # Extract season, episode, and scene number
            season = metadata.get("season", 0)
            episode = metadata.get("episode", 0)
            scene_number = int(metadata.get("scene_number", 0))
            
            # Create tag for logging
            scene_tag = f"S{season:02d}E{episode:02d}_{scene_number:03d}"
            
            # Check if there's already a chunk with this narrative position by looking at the chunk tag
            # Use direct query with regex pattern to match scene markers
            scene_pattern = f"SCENE BREAK: S{season:02d}E{episode:02d}_{scene_number:03d}"
            existing_sequence = session.query(NarrativeChunk.sequence)\
                .filter(NarrativeChunk.raw_text.like(f"%{scene_pattern}%"))\
                .first()
            
            if existing_sequence:
                # Use the existing sequence number for this narrative position
                global_sequence = existing_sequence[0]
                logger.info(f"Using existing sequence {global_sequence} for {scene_tag}")
            else:
                # Find the highest sequence smaller than what we need to insert, to maintain order
                prev_highest_seq = session.query(sa.func.max(NarrativeChunk.sequence))\
                    .join(ChunkMetadata, NarrativeChunk.id == ChunkMetadata.chunk_id)\
                    .filter(
                        # If in same season/episode, get chunks with lower scene number
                        ((ChunkMetadata.season == season) & 
                         (ChunkMetadata.episode == episode) &
                         (sa.cast(sa.func.regexp_match(NarrativeChunk.raw_text, f'SCENE BREAK: S{season:02d}E{episode:02d}_0*([0-9]+)')[1], sa.Integer) < scene_number))
                        |
                        # OR if in earlier season/episode, get all chunks
                        ((ChunkMetadata.season < season) |
                         ((ChunkMetadata.season == season) & (ChunkMetadata.episode < episode)))
                    ).scalar() or 0
                
                # Get the lowest sequence higher than what we need to insert
                next_lowest_seq = session.query(sa.func.min(NarrativeChunk.sequence))\
                    .join(ChunkMetadata, NarrativeChunk.id == ChunkMetadata.chunk_id)\
                    .filter(
                        # If in same season/episode, get chunks with higher scene number
                        ((ChunkMetadata.season == season) & 
                         (ChunkMetadata.episode == episode) &
                         (sa.cast(sa.func.regexp_match(NarrativeChunk.raw_text, f'SCENE BREAK: S{season:02d}E{episode:02d}_0*([0-9]+)')[1], sa.Integer) > scene_number))
                        |
                        # OR if in later season/episode, get all chunks
                        ((ChunkMetadata.season > season) |
                         ((ChunkMetadata.season == season) & (ChunkMetadata.episode > episode)))
                    ).scalar()
                
                if next_lowest_seq:
                    # Insert between the previous and next chunks
                    # If there's not enough space, we'll need to resequence
                    if next_lowest_seq - prev_highest_seq > 1:
                        global_sequence = prev_highest_seq + 1
                    else:
                        # Not enough space, run resequencing
                        logger.warning(f"Not enough space to insert {scene_tag} between {prev_highest_seq} and {next_lowest_seq}, resequencing needed")
                        global_sequence = prev_highest_seq + 1  # Temporary, will need resequencing
                else:
                    # This is the highest sequence, just add to the end
                    global_sequence = prev_highest_seq + 1
                
                logger.info(f"Assigning new sequence {global_sequence} for {scene_tag}")
            
            # Create narrative chunk with calculated sequence
            narrative_chunk = NarrativeChunk(
                id=chunk_id,
                sequence=global_sequence,
                raw_text=chunk_text
            )
            session.add(narrative_chunk)
            session.flush()  # Flush to ensure the sequence is assigned
            
            # Extract metadata
            season = metadata.get("season")
            episode = metadata.get("episode")
            scene_number = metadata.get("scene_number")
            world_layer = metadata.get("world_layer", "primary")
            
            # Parse characters from chunk content (basic implementation)
            characters_data = self._extract_characters_from_text(chunk_text)
            
            # Create chunk metadata
            chunk_metadata = ChunkMetadata(
                chunk_id=chunk_id,
                world_layer=world_layer,
                season=season,
                episode=episode,
                narrative_vector=json.dumps({
                    "scene_number": scene_number,
                    "chunk_tag": metadata.get("chunk_tag", "")
                }),
                characters=json.dumps(characters_data),
                setting=json.dumps({"extracted": "auto"}),
                causality=json.dumps({"extracted": "auto"}),
                prose=json.dumps({"style": "default"})
            )
            session.add(chunk_metadata)
            
            # Generate embeddings with all available models
            for model_key in self.embedding_models:
                try:
                    # Generate embedding
                    embedding = self.generate_embedding(chunk_text, model_key)
                    
                    # We've already verified the pgvector extension is installed during initialization
                    
                    # Pass the embedding as a list directly to pgvector
                    # The Vector type will handle the conversion
                    embedding_data = embedding
                    embedding_dim = len(embedding)
                    logger.debug(f"Storing embedding with length {embedding_dim}")
                    
                    # Create chunk embedding with proper dimension
                    if model_key.startswith("bge-small"):
                        # BGE-Small models have 384 dimensions
                        dimensions = 384
                    else:
                        # BGE-Large and E5-Large models have 1024 dimensions
                        dimensions = 1024
                    
                    # Store all embeddings in the unified chunk_embeddings table
                    chunk_embedding = ChunkEmbedding(
                        chunk_id=chunk_id,
                        model=model_key,
                        embedding=embedding_data,
                        dimensions=dimensions
                    )
                    
                    session.add(chunk_embedding)
                    
                except Exception as e:
                    logger.error(f"Error generating embedding with model {model_key}: {e}")
                    logger.error(f"Exception type: {type(e).__name__}")
                    logger.error(f"Exception details: {str(e)}")
            
            # Commit the transaction
            session.commit()
            logger.info(f"Successfully stored chunk {chunk_id} with embeddings")
            
            return str(chunk_id)
        
        except Exception as e:
            session.rollback()
            logger.error(f"Error storing chunk: {e}")
            raise
        
        finally:
            session.close()
    
    def _extract_characters_from_text(self, text: str) -> List[str]:
        """
        Basic implementation to extract character names from text.
        A more sophisticated implementation would use NER or a custom model.
        
        Args:
            text: Chunk text to analyze
            
        Returns:
            List of extracted character names
        """
        # This is a very simplified implementation
        common_names = ["Alex", "Emilia", "Victor", "Zoe", "Max", "Raven"]
        found_names = []
        
        for name in common_names:
            if name in text:
                found_names.append(name)
        
        return found_names

def main():
    """
    Main entry point for the import script
    """
    parser = argparse.ArgumentParser(description="Import narrative files into NEXUS")
    
    # Get default file pattern from settings
    default_file_pattern = SETTINGS.get("import", {}).get("file_pattern", "ALEX_*_copy_notime.md")
    
    parser.add_argument("file_pattern", nargs="?", default=default_file_pattern,
                      help=f"File pattern to match (default: {default_file_pattern})")
    parser.add_argument("--db-url", dest="db_url", 
                      help="PostgreSQL database URL")
    args = parser.parse_args()
    
    # Find matching files
    files = glob.glob(args.file_pattern)
    if not files:
        logger.error(f"No files found matching pattern: {args.file_pattern}")
        sys.exit(1)
    
    logger.info(f"Found {len(files)} files to process")
    
    # Initialize standalone narrative importer
    importer = NarrativeImporter(db_url=args.db_url)
    
    # Process each file
    total_chunks = 0
    for file_path in files:
        logger.info(f"Processing file: {file_path}")
        try:
            chunks_processed = importer.process_chunked_file(file_path)
            total_chunks += chunks_processed
            print(f"Processed {chunks_processed} chunks from {file_path}")
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            print(f"Error processing {file_path}: {str(e)}")
    
    logger.info(f"Completed importing {total_chunks} chunks from {len(files)} files")
    print(f"Successfully imported {total_chunks} chunks from {len(files)} files")

if __name__ == "__main__":
    main()