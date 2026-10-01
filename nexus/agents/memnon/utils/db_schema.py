"""
Database Schema for MEMNON Agent

Defines the database models and schema for MEMNON's PostgreSQL database.
"""

from nexus.database import create_slot_engine
from nexus.database import verify_database_url


import logging
from typing import Dict, Any, Optional
import sqlalchemy as sa
from sqlalchemy import Column, Table, MetaData, text, inspect
from sqlalchemy.dialects.postgresql import UUID, BYTEA, ARRAY, JSONB
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger("nexus.memnon.db_schema")

# Define SQL Alchemy Base
Base = declarative_base()


# Define ORM models based on the PostgreSQL schema
class NarrativeChunk(Base):
    __tablename__ = "narrative_chunks"

    id = Column(sa.BigInteger, primary_key=True)
    raw_text = Column(sa.Text, nullable=False)
    authorial_directives = Column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())


class ChunkMetadata(Base):
    __tablename__ = "chunk_metadata"

    id = Column(sa.BigInteger, primary_key=True)
    chunk_id = Column(
        sa.BigInteger, sa.ForeignKey("narrative_chunks.id"), nullable=False
    )
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
    __tablename__ = "characters"

    id = Column(sa.BigInteger, primary_key=True)
    name = Column(sa.String(50), nullable=False)
    description = Column(sa.Text)
    role = Column(sa.String(50))
    faction = Column(sa.String(50))
    relationships = Column(sa.JSON)
    status = Column(sa.String(50))
    backstory = Column(sa.Text)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at = Column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class Place(Base):
    __tablename__ = "places"

    id = Column(sa.BigInteger, primary_key=True)
    name = Column(sa.String(50), nullable=False)
    type = Column(
        sa.Enum("fixed_location", "vehicle", "other", name="place_type"), nullable=False
    )
    zone = Column(sa.BigInteger, nullable=False)
    summary = Column(sa.String(1000))
    inhabitants = Column(ARRAY(sa.String))
    historical_significance = Column(sa.Text)
    current_status = Column(sa.String(500))
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at = Column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


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
        self._closed = False
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
            self.db_url = verify_database_url(self.db_url)
            engine = create_slot_engine(self.db_url)

            # Verify connection
            connection = engine.connect()
            connection.close()

            # Check for vector extension
            from .db_access import check_vector_extension

            if not check_vector_extension(self.db_url):
                raise ConnectionError(
                    "Missing vector extension; migration 022 owns this prerequisite"
                )
            logger.info("Vector extension available")

            logger.info("Successfully connected to the configured database")
            return engine

        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise ConnectionError(f"Database connection failed: {e}")

    def create_session(self) -> Session:
        """
        Create a new database session.

        Returns:
            SQLAlchemy session
        """
        if self._closed:
            raise RuntimeError("DatabaseManager is closed")
        return self.Session()

    def close(self) -> None:
        """Dispose the engine, returning all pooled connections to Postgres.

        The narrative API builds a fresh MEMNON (and therefore a fresh
        engine) per turn; without explicit disposal those pools sit in
        reference-cycle garbage holding server-side connections until a full
        GC that rarely arrives (issue #401). Deterministic teardown instead.
        """
        self.engine.dispose()
        self._closed = True
        logger.info("DatabaseManager engine disposed")

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
        }
