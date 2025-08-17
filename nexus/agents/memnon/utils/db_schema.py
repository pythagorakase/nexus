"""
Database Schema for MEMNON Agent

Defines the database models and schema for MEMNON's PostgreSQL database.
"""

import logging
from typing import Dict, Any, Optional
import sqlalchemy as sa
from sqlalchemy import create_engine, Column, Table, MetaData, text, inspect
from sqlalchemy.dialects.postgresql import UUID, BYTEA, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("nexus.memnon.db_schema")

# Define SQL Alchemy Base
Base = declarative_base()

# Define ORM models based on the PostgreSQL schema
class NarrativeChunk(Base):
    __tablename__ = 'narrative_chunks'
    
    id = Column(sa.BigInteger, primary_key=True)
    raw_text = Column(sa.Text, nullable=False)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())

# Define the dimension-specific embedding tables
# DEPRECATED: ChunkEmbedding384D removed - no longer using 384-dimension embeddings

class ChunkEmbedding1024D(Base):
    __tablename__ = 'chunk_embeddings_1024d'
    
    id = Column(sa.Integer, primary_key=True)
    chunk_id = Column(sa.BigInteger, sa.ForeignKey('narrative_chunks.id'), nullable=False)
    model = Column(sa.String(255), nullable=False)
    # Note: This is a proper vector type with 1024 dimensions
    embedding = Column(sa.String, nullable=False)  # Will be treated as vector by PostgreSQL
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())

class ChunkEmbedding1536D(Base):
    __tablename__ = 'chunk_embeddings_1536d'
    
    id = Column(sa.Integer, primary_key=True)
    chunk_id = Column(sa.BigInteger, sa.ForeignKey('narrative_chunks.id'), nullable=False)
    model = Column(sa.String(255), nullable=False)
    # Note: This is a proper vector type with 1536 dimensions
    embedding = Column(sa.String, nullable=False)  # Will be treated as vector by PostgreSQL
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())

class ChunkMetadata(Base):
    __tablename__ = 'chunk_metadata'
    
    id = Column(sa.BigInteger, primary_key=True)
    chunk_id = Column(sa.BigInteger, sa.ForeignKey('narrative_chunks.id'), nullable=False)
    season = Column(sa.Integer, nullable=False)
    episode = Column(sa.Integer, nullable=False)
    scene = Column(sa.Integer)
    world_layer = Column(sa.String(50))
    perspective = Column(sa.String(50))
    time_code = Column(sa.String(50))
    location = Column(sa.String(150))
    summary = Column(sa.Text)
    keywords = Column(ARRAY(sa.String))
    characters = Column(ARRAY(sa.String))

class Character(Base):
    __tablename__ = 'characters'
    
    id = Column(sa.BigInteger, primary_key=True)
    name = Column(sa.String(50), nullable=False)
    description = Column(sa.Text)
    role = Column(sa.String(50))
    faction = Column(sa.String(50))
    relationships = Column(sa.JSON)
    status = Column(sa.String(50))
    backstory = Column(sa.Text)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())

class Place(Base):
    __tablename__ = 'places'
    
    id = Column(sa.BigInteger, primary_key=True)
    name = Column(sa.String(50), nullable=False)
    type = Column(sa.Enum('fixed_location', 'vehicle', 'other', name='place_type'), nullable=False)
    zone = Column(sa.BigInteger, nullable=False)
    summary = Column(sa.String(1000))
    inhabitants = Column(ARRAY(sa.String))
    historical_significance = Column(sa.Text)
    current_status = Column(sa.String(500))
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())

class DatabaseManager:
    """
    Manages database connections and operations for MEMNON agent.
    """
    
    def __init__(self, db_url: str, settings: Optional[Dict[str, Any]] = None):
        """
        Initialize the DatabaseManager.
        
        Args:
            db_url: PostgreSQL database URL
            settings: Optional settings dictionary
        """
        self.db_url = db_url
        self.settings = settings or {}
        self.engine = self._initialize_database_connection()
        self.Session = sessionmaker(bind=self.engine)
        
        logger.info("DatabaseManager initialized")
    
    def _initialize_database_connection(self) -> sa.engine.Engine:
        """
        Initialize connection to PostgreSQL database.
        
        Returns:
            SQLAlchemy engine instance
        """
        try:
            engine = create_engine(self.db_url)
            
            # Verify connection
            connection = engine.connect()
            connection.close()
            
            # Create tables if they don't exist
            Base.metadata.create_all(engine)
            
            # Check for vector extension
            from .db_access import check_vector_extension, setup_database_indexes
            
            if check_vector_extension(self.db_url):
                logger.info("Vector extension available")
                
                # Set up necessary database indexes for efficient search
                if setup_database_indexes(self.db_url):
                    logger.info("Database indexes setup complete")
                else:
                    logger.warning("Database indexes setup failed - vector search may not work correctly")
                
                # Set up hybrid search if enabled in settings
                hybrid_search_enabled = self.settings.get("retrieval", {}).get("hybrid_search", {}).get("enabled", False)
                if hybrid_search_enabled:
                    logger.info("Setting up hybrid search capabilities")
                    self._setup_hybrid_search(engine)
            else:
                logger.warning("Vector extension not found - vector search will not work")
                logger.warning("Please run scripts/install_pgvector_custom.sh first")
            
            logger.info(f"Successfully connected to database at {self.db_url}")
            return engine
        
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise ConnectionError(f"Database connection failed: {e}")
    
    def _setup_hybrid_search(self, engine):
        """
        Set up the database for hybrid search capabilities.
        Creates a GIN index for text search and a hybrid_search SQL function.
        
        Args:
            engine: SQLAlchemy engine
        """
        try:
            # Use our database access utilities to set up necessary indexes and functions
            from .db_access import setup_database_indexes
            
            logger.info("Setting up hybrid search capabilities using db_access utility")
            if setup_database_indexes(self.db_url):
                logger.info("Hybrid search database setup completed successfully")
                return True
            else:
                logger.warning("Hybrid search setup failed")
                return False
                
        except Exception as e:
            logger.error(f"Error setting up hybrid search: {e}")
            import traceback
            logger.error(traceback.format_exc())
            logger.warning("Disabling hybrid search due to setup failure")
            return False
    
    def create_session(self) -> Session:
        """
        Create a new database session.
        
        Returns:
            SQLAlchemy session
        """
        return self.Session()
    
    def get_model_classes(self) -> Dict[str, Any]:
        """
        Get dictionary of model classes defined in this module.
        
        Returns:
            Dictionary mapping table names to model classes
        """
        return {
            "narrative_chunks": NarrativeChunk,
            "chunk_metadata": ChunkMetadata,
            "characters": Character,
            "places": Place,
            # "chunk_embeddings_0384d": ChunkEmbedding384D,  # Deprecated - removed
            "chunk_embeddings_1024d": ChunkEmbedding1024D,
            "chunk_embeddings_1536d": ChunkEmbedding1536D
        } 