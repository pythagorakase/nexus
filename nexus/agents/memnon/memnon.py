"""
MEMNON Agent - Unified Memory Access System for Narrative Intelligence

This agent is responsible for all memory operations, including:
- Managing embeddings across multiple models
- Storing and retrieving narrative chunks
- Cross-referencing structured data with vector embeddings
- Implementing specialized query patterns for different memory tiers
- Synthesizing responses using local LLM capabilities

The architecture has been refactored to use modular utility classes:
- EmbeddingManager: Handles embedding model lifecycle and vector generation
- SearchManager: Coordinates different search strategies across data sources
- QueryAnalyzer: Analyzes user queries to determine optimal search approach
- DatabaseManager: Provides database connection and schema management 
- ContentProcessor: Manages content chunking, processing, and storage
"""

import os
import re
import uuid
import logging
import json
import time
import requests
from typing import Dict, List, Tuple, Optional, Union, Any, Set
from datetime import datetime, date
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, Column, Table, MetaData, text, inspect, func, or_
from sqlalchemy.dialects.postgresql import UUID, BYTEA, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# Register PostGIS types with SQLAlchemy to avoid warnings
try:
    import geoalchemy2  # noqa: F401
except ImportError:
    logger = logging.getLogger("nexus.memnon")
    logger.debug("GeoAlchemy2 not installed, PostGIS types may show warnings")

# Import utility modules
from .utils.db_access import check_vector_extension, execute_vector_search, execute_hybrid_search, setup_database_indexes, prepare_tsquery
from .utils.continuous_temporal_search import execute_time_aware_search, analyze_temporal_intent
from .utils.idf_dictionary import IDFDictionary
from .utils.embedding_manager import EmbeddingManager
from .utils.search import SearchManager
from .utils.query_analysis import QueryAnalyzer
from .utils.db_schema import DatabaseManager
from .utils.content_processor import ContentProcessor

# Sentence transformers for embedding
from sentence_transformers import SentenceTransformer

# Letta framework types (for type hints)
from letta.schemas.agent import AgentState 
from letta.schemas.memory import Memory
from letta.schemas.block import Block, CreateBlock
from letta.schemas.message import Message
from letta.embeddings import EmbeddingEndpoint

# Import alias search utilities
from .utils.alias_search import load_aliases_from_db, ALIAS_LOOKUP
from .utils.cross_encoder import rerank_results

# Set up a basic console logger for initial settings loading
settings_logger = logging.getLogger("nexus.memnon.settings")
settings_logger.setLevel(logging.INFO)
if not settings_logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    settings_logger.addHandler(console_handler)

# Load settings
def load_settings() -> Dict[str, Any]:
    """Load settings from settings.json file."""
    try:
        # Check for environment variable first
        settings_path_env = os.environ.get("NEXUS_SETTINGS_PATH")
        if settings_path_env:
            settings_path = Path(settings_path_env)
            settings_logger.info(f"Using settings path from environment: {settings_path}")
        else:
            settings_path = Path("settings.json")
            
        if settings_path.exists():
            with open(settings_path, "r") as f:
                settings = json.load(f)
                settings_logger.info(f"Loaded settings from {settings_path}")
                
                # Debug temporal boosting settings
                if ("Agent Settings" in settings and "MEMNON" in settings["Agent Settings"] and
                    "retrieval" in settings["Agent Settings"]["MEMNON"] and 
                    "hybrid_search" in settings["Agent Settings"]["MEMNON"]["retrieval"]):
                    hybrid = settings["Agent Settings"]["MEMNON"]["retrieval"]["hybrid_search"]
                    temporal_factor = hybrid.get("temporal_boost_factor", "not set")
                    query_specific = hybrid.get("use_query_type_temporal_factors", "not set")
                    # settings_logger.info(f"SETTINGS DEBUG - temporal_boost_factor: {temporal_factor}")
                    # settings_logger.info(f"SETTINGS DEBUG - use_query_type_temporal_factors: {query_specific}")
                
                return settings
        else:
            settings_logger.warning(f"Warning: settings.json not found at {settings_path.absolute()}")
            return {}
    except Exception as e:
        settings_logger.error(f"Error loading settings: {e}")
        return {}

# Global settings
SETTINGS = load_settings()
MEMNON_SETTINGS = SETTINGS.get("Agent Settings", {}).get("MEMNON", {})
GLOBAL_SETTINGS = SETTINGS.get("Agent Settings", {}).get("global", {})

# Configure logging
log_config = MEMNON_SETTINGS.get("logging", {})
log_level = getattr(logging, log_config.get("level", "DEBUG"))
log_file = log_config.get("file", "memnon.log")
log_console = log_config.get("console", True)

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
logger = logging.getLogger("nexus.memnon")

# LLM settings
MODEL_CONFIG = GLOBAL_SETTINGS.get("model", {})
DEFAULT_MODEL_ID = MODEL_CONFIG.get("default_model", "llama-3.3-70b-instruct@q6_k")

# Database settings
DEFAULT_DB_URL = MEMNON_SETTINGS.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")

# Define SQL Alchemy Base
Base = declarative_base()

# Define ORM models based on the PostgreSQL schema
class NarrativeChunk(Base):
    __tablename__ = 'narrative_chunks'
    
    id = Column(sa.BigInteger, primary_key=True)
    raw_text = Column(sa.Text, nullable=False)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())

# ChunkEmbedding class and table removed since we've migrated to dimension-specific tables

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

class MEMNON:
    """
    MEMNON Agent - Unified Memory Access System for Narrative Intelligence
    
    This is a standalone version that works without the full Letta framework.
    """
    
    def __init__(self,
                 interface,
                 agent_state: Optional[AgentState] = None,
                 user = None,
                 db_url: str = None,
                 model_id: str = None, # This is now only for embedding models
                 model_path: str = None,
                 debug: bool = None,
                 **kwargs):
        """
        Initialize the MEMNON Agent
        
        Args:
            interface: The interface to use for communication
            agent_state: Agent state from Letta framework (optional in direct mode)
            user: User information (optional in direct mode)
            db_url: PostgreSQL database URL
            model_id: DEPRECATED - LLM model ID is no longer used
            model_path: DEPRECATED - LLM model path is no longer used
            debug: Enable debug logging
            **kwargs: Additional arguments
        """
        # Store references
        self.interface = interface
        self.agent_state = agent_state
        self.user = user
        
        # Store debug setting
        self.debug = debug
        if debug is None:
            self.debug = MEMNON_SETTINGS.get("debug", False)
            
        # Set up logging if debug is enabled
        if self.debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Debug logging enabled")
        
        # Set up database connection using DatabaseManager
        self.db_url = db_url or DEFAULT_DB_URL
        logger.info(f"Using database URL: {self.db_url}")
        self.db_manager = DatabaseManager(self.db_url, settings=MEMNON_SETTINGS)
        self.Session = self.db_manager.Session
        
        # Set up embedding models using EmbeddingManager
        logger.info("Initializing embedding models through EmbeddingManager")
        self.embedding_manager = EmbeddingManager(settings=MEMNON_SETTINGS)
        
        # Initialize IDF dictionary
        logger.info("Initializing IDF dictionary for term weighting...")
        self.idf_dictionary = IDFDictionary(self.db_url)
        result = self.idf_dictionary.build_dictionary()  # Build/load on startup
        if result:
            logger.info(f"IDF dictionary initialized with {len(result)} terms")
        else:
            logger.warning("IDF dictionary initialization failed or returned empty dictionary")
        
        # Get model weights from settings
        model_weights = {}
        for model_name, model_config in MEMNON_SETTINGS.get("models", {}).items():
            weight = model_config.get("weight", 0.33)  # Default equal weight
            model_weights[model_name] = weight
        
        # Use default weights if none defined in settings
        if not model_weights:
            model_weights = {
                "bge-large": 0.4,
                "e5-large": 0.4,
                "bge-small-custom": 0.2
            }
            
        # Flag to prioritize text search for testing
        self.force_text_first = False
        
        # Get query and retrieval settings from configuration
        query_config = MEMNON_SETTINGS.get("query", {})
        retrieval_config = MEMNON_SETTINGS.get("retrieval", {})
        
        # Configure retrieval settings using values from settings.json
        self.retrieval_settings = {
            "default_top_k": query_config.get("default_limit", 10),
            "max_query_results": retrieval_config.get("max_results", 50),
            "relevance_threshold": query_config.get("min_similarity", 0.7),
            "entity_boost_factor": retrieval_config.get("entity_boost_factor", 1.2),
            "recency_boost_factor": retrieval_config.get("recency_boost_factor", 1.1),
            "db_vector_balance": retrieval_config.get("db_vector_balance", 0.6),  # 60% weight to database, 40% to vector
            "model_weights": model_weights,
            "highlight_matches": query_config.get("highlight_matches", True)
        }
        
        # Initialize SearchManager with required dependencies
        logger.info("Initializing SearchManager...")
        self.search_manager = SearchManager(
            db_url=self.db_url,
            embedding_manager=self.embedding_manager,
            idf_dictionary=self.idf_dictionary,
            settings=MEMNON_SETTINGS,
            retrieval_settings=self.retrieval_settings
        )
        
        # Initialize QueryAnalyzer
        logger.info("Initializing QueryAnalyzer...")
        self.query_analyzer = QueryAnalyzer(settings=MEMNON_SETTINGS)
        
        # Initialize ContentProcessor
        logger.info("Initializing ContentProcessor...")
        self.content_processor = ContentProcessor(
            db_manager=self.db_manager,
            embedding_manager=self.embedding_manager,
            settings=MEMNON_SETTINGS,
            load_aliases_func=self._load_aliases
        )
        
        # Log the retrieval settings
        logger.debug(f"Retrieval settings: {json.dumps(self.retrieval_settings, indent=2)}")
        
        # Memory type registry - maps virtual memory tier to actual storage
        self.memory_tiers = {
            "strategic": {"type": "database", "tables": ["events", "threats", "ai_notebook"]},
            "entity": {"type": "database", "tables": ["characters", "places", "factions", "items"]},
            "narrative": {"type": "vector", "collections": ["narrative_chunks"]},
        }
        
        # Query type registry - Simplified, used for rule-based planning
        self.query_types = {
            "character": {
                "primary_tier": "entity",
                "primary_tables": ["characters"],
                "secondary_tier": "narrative",
                "secondary_search": "hybrid_search" # Default to hybrid
            },
            "location": {
                "primary_tier": "entity",
                "primary_tables": ["places"],
                "secondary_tier": "narrative",
                "secondary_search": "hybrid_search"
            },
            "event": {
                "primary_tier": "narrative", # Events likely in narrative text
                "primary_tables": [], # Assuming no dedicated event table for now
                "secondary_tier": "entity", # Related characters/places
                "secondary_search": "hybrid_search"
            },
            "theme": {
                "primary_tier": "narrative",
                "primary_search": "hybrid_search"
            },
            "relationship": {
                "primary_tier": "entity",
                "primary_tables": ["characters"], # Primarily search characters
                "secondary_tier": "narrative",
                "secondary_search": "hybrid_search"
            },
            "narrative": {
                "primary_tier": "narrative",
                "primary_search": "hybrid_search"
            },
            "general": { # Default fallback
                "primary_tier": "narrative",
                "primary_search": "hybrid_search"
            }
        }
        
        logger.info("MEMNON agent initialized (Headless Mode - No LLM)")

    def get_schema_summary(self, tables: Optional[List[str]] = None) -> str:
        """
        Return a concise schema summary for non-empty, relevant tables.
        Excludes embedding tables and includes table/column comments.
        """
        try:
            from sqlalchemy import text
            inspector = inspect(self.db_manager.engine)
            
            # If no specific tables requested, get all tables dynamically
            if tables:
                allowed = tables
            else:
                # Get all tables from the database
                all_tables = inspector.get_table_names()
                # Exclude embedding tables and other irrelevant tables
                allowed = [
                    t for t in all_tables 
                    if not t.startswith('chunk_embeddings_')
                    and t != 'alembic_version'  # Skip Alembic migration table
                ]
            
            lines: List[str] = []
            
            for table_name in allowed:
                try:
                    # Check if table exists
                    if not inspector.has_table(table_name):
                        continue
                    
                    # Use a single connection for all queries for this table
                    with self.db_manager.engine.connect() as conn:
                        # Check if table has any rows (skip empty tables)
                        count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                        row_count = count_result.scalar()
                        if row_count == 0:
                            continue
                        
                        # Get table comment if available
                        table_comment = ""
                        try:
                            comment_result = conn.execute(
                                text("SELECT obj_description(c.oid) FROM pg_class c WHERE c.relname = :table"),
                                {"table": table_name}
                            )
                            comment = comment_result.scalar()
                            if comment:
                                table_comment = f" -- {comment}"
                        except Exception as e:
                            logger.debug(f"Could not get table comment for {table_name}: {e}")
                        
                        # Get columns with comments
                        cols = inspector.get_columns(table_name)
                        col_descriptions = []
                        
                        for col in cols:
                            col_name = col.get("name", "?")
                            col_type = str(col.get("type", ""))[:30]  # Truncate long types
                            
                            # Try to get column comment
                            col_comment = ""
                            try:
                                comment_result = conn.execute(
                                    text("""
                                    SELECT col_description(c.oid, a.attnum) 
                                    FROM pg_class c 
                                    JOIN pg_attribute a ON a.attrelid = c.oid 
                                    WHERE c.relname = :table AND a.attname = :column
                                    """),
                                    {"table": table_name, "column": col_name}
                                )
                                comment = comment_result.scalar()
                                if comment:
                                    col_comment = f":{comment}"
                            except Exception as e:
                                logger.debug(f"Could not get column comment for {table_name}.{col_name}: {e}")
                            
                            # Include type information for geography/geometry columns
                            if 'geography' in col_type.lower() or 'geometry' in col_type.lower():
                                col_descriptions.append(f"{col_name}[{col_type}]{col_comment}")
                            else:
                                col_descriptions.append(f"{col_name}{col_comment}")
                        
                        col_list = ", ".join(col_descriptions)
                        lines.append(f"- {table_name}({col_list}){table_comment}")
                    
                except Exception as e:
                    # Skip tables with errors
                    logger.debug(f"Skipping table {table_name}: {e}")
                    continue
            
            if not lines:
                return "No populated tables found in database."
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Error generating schema summary: {e}")
            return "Error retrieving schema information."

    def execute_readonly_sql(self, sql: str, max_rows: int = 50, timeout_ms: int = 3000) -> Dict[str, Any]:
        """
        Execute a read-only, whitelisted SELECT statement safely.
        - Only allows single-statement SELECT queries
        - Enforces allowed table list and LIMIT
        - Applies a short statement timeout
        Returns { columns: [...], rows: [{...}, ...], row_count: int } or { error: str }
        """
        try:
            if not sql or not isinstance(sql, str):
                return {"error": "Empty SQL"}
            original_sql = sql
            sql_str = sql.strip().rstrip(";")
            lowered = sql_str.lower()
            # Must be a single SELECT
            if not lowered.startswith("select "):
                return {"error": "Only SELECT statements are allowed"}
            forbidden = [";", " update ", " insert ", " delete ", " alter ", " create ", " drop ", " grant ", " revoke ", " truncate ", " vacuum ", " copy "]
            for kw in forbidden:
                if kw in f" {lowered} ":
                    return {"error": f"Forbidden keyword in SQL: {kw.strip()}"}
            # Blacklist sensitive tables from being accessed
            import re
            forbidden_table_prefixes = {
                "alembic_",  # Migration tracking
                "pg_",  # PostgreSQL system tables
                "information_schema",  # System schema
                "chunk_embeddings_",  # Embedding tables (large binary data)
            }
            referenced: List[str] = []
            for pattern in [r"\\bfrom\\s+([a-zA-Z_\\.\"]+)", r"\\bjoin\\s+([a-zA-Z_\\.\"]+)"]:
                for m in re.finditer(pattern, lowered):
                    name = m.group(1).strip().strip('"')
                    # remove optional schema prefix like public.
                    if "." in name:
                        name = name.split(".")[-1]
                    referenced.append(name)
            for tbl in referenced:
                if tbl:
                    # Check if table name starts with any forbidden prefix
                    for forbidden_prefix in forbidden_table_prefixes:
                        if tbl.startswith(forbidden_prefix):
                            return {"error": f"Table not allowed: {tbl} (blacklisted prefix)"}
            # Enforce LIMIT if absent (check more carefully to avoid double LIMIT)
            # Use regex to check if LIMIT is already present as a separate word
            if not re.search(r'\blimit\s+\d+', lowered):
                sql_str = f"{sql_str} LIMIT {max_rows}"
            # Execute
            with self.db_manager.engine.connect() as conn:
                # Apply a short statement timeout
                try:
                    conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
                except Exception:
                    pass
                result = conn.execute(text(sql_str))
                rows = result.fetchall()
                columns = list(result.keys())
            # Truncate long text fields
            formatted_rows: List[Dict[str, Any]] = []
            for row in rows[:max_rows]:
                row_dict = {}
                for col, val in zip(columns, row):
                    if isinstance(val, str) and len(val) > 2000:
                        row_dict[col] = val[:2000] + "..."
                    else:
                        row_dict[col] = val
                formatted_rows.append(row_dict)
            return {
                "columns": columns,
                "rows": formatted_rows,
                "row_count": len(formatted_rows),
                "sql": original_sql.strip(),
            }
        except Exception as e:
            logger.error(f"Error executing read-only SQL: {e}")
            return {"error": str(e)}
    
    def _initialize_memory_blocks(self):
        """Initialize specialized memory blocks if not present."""
        # Check if memory blocks exist and create if needed
        required_blocks = ["memory_index", "query_templates", "retrieval_stats", "db_schema"]
        
        for block_name in required_blocks:
            if block_name not in self.agent_state.memory.list_block_labels():
                # Create block with default empty content
                block = CreateBlock(
                    label=block_name,
                    value="",
                    limit=50000,  # Generous limit for memory data
                    description=f"Memory {block_name} block"
                )
                # Add block to memory
                self.block_manager.create_block(block=block, agent_id=self.agent_state.id, actor=self.user)
    
    def _initialize_database_connection(self) -> sa.engine.Engine:
        """Initialize connection to PostgreSQL database."""
        try:
            engine = create_engine(self.db_url)
            
            # Verify connection
            connection = engine.connect()
            connection.close()
            
            # Create tables if they don't exist
            Base.metadata.create_all(engine)
            
            # Check for vector extension via utility function
            if check_vector_extension(self.db_url):
                logger.info("Vector extension available")
                
                # Set up necessary database indexes for efficient search
                if setup_database_indexes(self.db_url):
                    logger.info("Database indexes setup complete")
                else:
                    logger.warning("Database indexes setup failed - vector search may not work correctly")
                
                # Set up hybrid search if enabled in settings
                hybrid_search_enabled = MEMNON_SETTINGS.get("retrieval", {}).get("hybrid_search", {}).get("enabled", False)
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
            logger.info("Setting up hybrid search capabilities using db_access utility")
            if setup_database_indexes(self.db_url):
                logger.info("Hybrid search database setup completed successfully")
                return True
            else:
                logger.warning("Hybrid search setup failed")
                # Update settings in memory to reflect disabled status
                if 'retrieval' in MEMNON_SETTINGS and 'hybrid_search' in MEMNON_SETTINGS['retrieval']:
                    MEMNON_SETTINGS['retrieval']['hybrid_search']['enabled'] = False
                return False
                
        except Exception as e:
            logger.error(f"Error setting up hybrid search: {e}")
            import traceback
            logger.error(traceback.format_exc())
            logger.warning("Disabling hybrid search due to setup failure")
            # Update settings to reflect disabled status
            if 'retrieval' in MEMNON_SETTINGS and 'hybrid_search' in MEMNON_SETTINGS['retrieval']:
                MEMNON_SETTINGS['retrieval']['hybrid_search']['enabled'] = False
            return False
    
    def _load_aliases(self) -> Dict[str, List[str]]:
        """Load character aliases from the database."""
        try:
            with self.Session() as session:
                return load_aliases_from_db(session)
        except Exception as e:
            logger.error(f"Error loading aliases: {e}")
            return ALIAS_LOOKUP  # Use default if loading fails
    
    def perform_hybrid_search(self, query_text: str, filters: Dict[str, Any] = None, top_k: int = None) -> List[Dict[str, Any]]:
        """
        Perform hybrid search using both vector embeddings and text search.
        Now supports multi-model search using all active embedding models with their weights.
        
        Args:
            query_text: The query text
            filters: Optional metadata filters to apply
            top_k: Maximum number of results to return
            
        Returns:
            List of matching chunks with scores and metadata
        """
        if top_k is None:
            top_k = self.retrieval_settings.get("default_top_k", 10)
        
        try:
            # Get hybrid search settings
            hybrid_config = MEMNON_SETTINGS.get("retrieval", {}).get("hybrid_search", {})
            if not hybrid_config.get("enabled", False):
                logger.warning("Hybrid search is disabled in settings")
                return []
            
            # Determine query type for weight adjustment
            query_info = self.query_analyzer.analyze_query(query_text)
            query_type = query_info.get("type", "general")
            logger.debug(f"Query classified as type: {query_type}")
            
            # Get weights based on query type or use defaults
            if hybrid_config.get("use_query_type_weights", False) and query_type in hybrid_config.get("weights_by_query_type", {}):
                weights = hybrid_config["weights_by_query_type"][query_type]
                vector_weight = weights.get("vector", 0.6)
                text_weight = weights.get("text", 0.4)
            else:
                vector_weight = hybrid_config.get("vector_weight_default", 0.6)
                text_weight = hybrid_config.get("text_weight_default", 0.4)
            
            # Normalize weights to ensure they sum to 1.0
            total_weight = vector_weight + text_weight
            if total_weight != 1.0:
                vector_weight = vector_weight / total_weight
                text_weight = text_weight / total_weight
            
            logger.debug(f"Using weights: vector={vector_weight}, text={text_weight}")
            
            # Gather all active models and their weights
            active_models = {}
            model_weights = {}
            
            for model_key, model_config in self.embedding_manager.models.items():
                if model_key in self.retrieval_settings["model_weights"]:
                    # Get the weight from the retrieval settings
                    model_weights[model_key] = self.retrieval_settings["model_weights"][model_key]
                    active_models[model_key] = self.embedding_manager.models[model_key]
            
            if not active_models:
                logger.error("No active embedding models found.")
                return []
            
            # Normalize model weights to sum to 1.0
            total_model_weight = sum(model_weights.values())
            if total_model_weight > 0:
                model_weights = {k: w/total_model_weight for k, w in model_weights.items()}
            
            logger.info(f"Using {len(active_models)} active models with weights: {model_weights}")
            
            # Generate embeddings for all active models
            query_embeddings = {}
            for model_key in active_models:
                try:
                    query_embeddings[model_key] = self.embedding_manager.generate_embedding(query_text, model_key)
                except Exception as e:
                    logger.error(f"Error generating embedding for model {model_key}: {e}")
            
            if not query_embeddings:
                logger.error("Failed to generate embeddings for any active model.")
                return []
            
            # Analyze the query's temporal intent on a continuous scale
            query_temporal_intent = analyze_temporal_intent(query_text)
            
            # Get default temporal boost factor from settings
            temporal_boost_factor = hybrid_config.get("temporal_boost_factor", 0.3)
            
            # Check if we should use query-type-specific temporal boost factors
            use_query_type_temporal_factors = hybrid_config.get("use_query_type_temporal_factors", False)
            
            # If enabled, get query-type-specific temporal boost factor
            if use_query_type_temporal_factors and query_type in hybrid_config.get("temporal_boost_factors", {}):
                query_temporal_factor = hybrid_config["temporal_boost_factors"][query_type]
                logger.debug(f"Using query-type-specific temporal boost factor for '{query_type}': {query_temporal_factor}")
                temporal_boost_factor = query_temporal_factor
            
            # Determine if this is a temporal query based on how far from neutral (0.5) the intent is
            is_temporal_query = abs(query_temporal_intent - 0.5) > 0.1
            
            # Determine if temporal boosting should be applied based on settings and query intent
            apply_temporal_boosting = temporal_boost_factor > 0.0 and is_temporal_query
            
            # If query has temporal aspects and boosting is enabled, use multi-model time-aware search
            if apply_temporal_boosting:
                logger.info(f"Using multi-model time-aware search for temporal query (intent: {query_temporal_intent:.2f}, boost factor: {temporal_boost_factor})")
                
                # Import multi-model time-aware search
                from .utils.continuous_temporal_search import execute_multi_model_time_aware_search
                
                # Execute multi-model time-aware search
                results = execute_multi_model_time_aware_search(
                    db_url=self.db_url,
                    query_text=query_text,
                    query_embeddings=query_embeddings,
                    model_weights=model_weights,
                    vector_weight=vector_weight,
                    text_weight=text_weight,
                    temporal_boost_factor=temporal_boost_factor,
                    filters=filters,
                    top_k=top_k,
                    idf_dict=self.idf_dictionary
                )
            else:
                # Use standard multi-model hybrid search for non-temporal queries
                logger.debug("Using standard multi-model hybrid search for non-temporal query")
                
                # Import multi-model hybrid search
                from .utils.db_access import execute_multi_model_hybrid_search
                
                # Execute multi-model hybrid search
                results = execute_multi_model_hybrid_search(
                    db_url=self.db_url,
                    query_text=query_text,
                    query_embeddings=query_embeddings,
                    model_weights=model_weights,
                    vector_weight=vector_weight,
                    text_weight=text_weight,
                    filters=filters,
                    top_k=top_k,
                    idf_dict=self.idf_dictionary
                )
            
            logger.info(f"Multi-model hybrid search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _query_vector_search(self, query_text: str, collections: List[str], filters: Dict[str, Any], top_k: int) -> List[Dict[str, Any]]:
        """
        Query the vector database for chunks similar to the query text.
        Uses all active embedding models with their configured weights.
        
        Args:
            query_text: The text to search for
            collections: Vector collection names to search in
            filters: Metadata filters to apply (season, episode, etc.)
            top_k: Maximum number of results to return
            
        Returns:
            List of matching chunks with scores and metadata
        """
        if top_k is None:
            top_k = self.retrieval_settings["default_top_k"]
        
        try:
            # Gather all active models and their weights
            active_models = {}
            model_weights = {}
            
            for model_key, model in self.embedding_manager.models.items():
                if model_key in self.retrieval_settings["model_weights"]:
                    # Get the weight from the retrieval settings
                    model_weights[model_key] = self.retrieval_settings["model_weights"][model_key]
                    active_models[model_key] = model
            
            if not active_models:
                logger.error("No active embedding models found.")
                return []
            
            # Normalize model weights to sum to 1.0
            total_model_weight = sum(model_weights.values())
            if total_model_weight > 0:
                model_weights = {k: w/total_model_weight for k, w in model_weights.items()}
            
            logger.info(f"Using {len(active_models)} active models with weights: {model_weights}")
            
            # Generate embeddings for all active models
            query_embeddings = {}
            for model_key in active_models:
                try:
                    query_embeddings[model_key] = self.embedding_manager.generate_embedding(query_text, model_key)
                except Exception as e:
                    logger.error(f"Error generating embedding for model {model_key}: {e}")
            
            if not query_embeddings:
                logger.error("Failed to generate embeddings for any active model.")
                return []

            # Use the multi-model hybrid search with 100% vector weight to effectively perform vector-only search
            from .utils.db_access import execute_multi_model_hybrid_search
            
            results = execute_multi_model_hybrid_search(
                db_url=self.db_url,
                query_text=query_text,
                query_embeddings=query_embeddings,
                model_weights=model_weights,
                vector_weight=1.0,  # Use 100% vector weight for pure vector search
                text_weight=0.0,    # No text search weight
                filters=filters,
                top_k=top_k,
                idf_dict=self.idf_dictionary
            )
            
            logger.info(f"Multi-model vector search returned {len(results)} results")
            return results
        
        except Exception as e:
            logger.error(f"Error in vector search: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _query_structured_data(self, query_text: str, table: str, filters: Dict[str, Any] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Query structured data tables.
        
        Args:
            query_text: The query text
            table: The table to query
            filters: Optional metadata filters
            limit: Maximum number of results to return
            
        Returns:
            List of matching results
        """
        try:
            with self.Session() as session:
                if table == "characters":
                    # Query characters (schema: id, name, summary, background, personality, emotional_state, current_activity, current_location, extra_data)
                    # Exact name or alias match
                    name_match_query = text("""
                    SELECT DISTINCT c.id, c.name, c.summary, c.current_activity, c.current_location,
                           array_agg(DISTINCT ca.alias) as aliases
                    FROM characters c
                    LEFT JOIN character_aliases ca ON c.id = ca.character_id
                    WHERE LOWER(c.name) = LOWER(:query)
                    OR EXISTS (
                        SELECT 1 FROM character_aliases ca2 
                        WHERE ca2.character_id = c.id AND LOWER(ca2.alias) = LOWER(:query)
                    )
                    GROUP BY c.id, c.name, c.summary, c.current_activity, c.current_location
                    """)
                    result = session.execute(name_match_query, {"query": query_text})
                    exact_matches = []
                    for row in result:
                        aliases = row.aliases if row.aliases and row.aliases[0] is not None else []
                        exact_matches.append({
                            "id": row.id,
                            "name": row.name,
                            "summary": row.summary,
                            "current_activity": row.current_activity,
                            "current_location": row.current_location,
                            "aliases": aliases,
                            "score": 1.0,
                            "content_type": "character",
                            "source": "structured_data"
                        })
                    if exact_matches:
                        return exact_matches
                    # Partial match by name or summary text
                    partial_match_query = text("""
                    SELECT DISTINCT c.id, c.name, c.summary, c.current_activity, c.current_location,
                           array_agg(DISTINCT ca.alias) as aliases
                    FROM characters c
                    LEFT JOIN character_aliases ca ON c.id = ca.character_id
                    WHERE c.name ILIKE '%' || :query || '%' OR c.summary ILIKE '%' || :query || '%'
                    GROUP BY c.id, c.name, c.summary, c.current_activity, c.current_location
                    LIMIT :limit
                    """)
                    result = session.execute(partial_match_query, {"query": query_text, "limit": limit})
                    partial_matches = []
                    for row in result:
                        aliases = row.aliases if row.aliases and row.aliases[0] is not None else []
                        partial_matches.append({
                            "id": row.id,
                            "name": row.name,
                            "summary": row.summary,
                            "current_activity": row.current_activity,
                            "current_location": row.current_location,
                            "aliases": aliases,
                            "score": 0.75,
                            "content_type": "character",
                            "source": "structured_data"
                        })
                    return partial_matches
                
                elif table == "places":
                    # Query places
                    # First check for exact name matches
                    name_match_query = text("""
                    SELECT id, name, type, zone, summary, inhabitants, current_status
                    FROM places
                    WHERE LOWER(name) = LOWER(:query)
                    """)
                    
                    result = session.execute(name_match_query, {"query": query_text})
                    exact_matches = []
                    for row in result:
                        exact_matches.append({
                            "id": row.id,
                            "name": row.name,
                            "type": row.type,
                            "zone": row.zone,
                            "summary": row.summary,
                            "inhabitants": row.inhabitants,
                            "current_status": row.current_status,
                            "score": 1.0,  # Exact match gets top score
                            "content_type": "place",
                            "source": "structured_data"
                        })
                    
                    if exact_matches:
                        return exact_matches
                    
                    # Then look for partial matches
                    partial_match_query = text("""
                    SELECT id, name, type, zone, summary, inhabitants, current_status,
                           similarity(LOWER(name), LOWER(:query)) AS match_score
                    FROM places
                    WHERE LOWER(name) LIKE '%' || LOWER(:query) || '%'
                    OR LOWER(summary) LIKE '%' || LOWER(:query) || '%'
                    ORDER BY match_score DESC
                    LIMIT :limit
                    """)
                    
                    result = session.execute(partial_match_query, {"query": query_text, "limit": limit})
                    partial_matches = []
                    for row in result:
                        partial_matches.append({
                            "id": row.id,
                            "name": row.name,
                            "type": row.type,
                            "zone": row.zone,
                            "summary": row.summary,
                            "inhabitants": row.inhabitants,
                            "current_status": row.current_status,
                            "score": float(row.match_score),
                            "content_type": "place",
                            "source": "structured_data"
                        })
                    
                    return partial_matches
                
                else:
                    logger.warning(f"Unsupported table: {table}")
                    return []
        
        except Exception as e:
            logger.error(f"Error querying structured data: {e}")
            return []

    def _query_text_search(self, query_text: str, filters: Dict[str, Any] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Perform a keyword-based text search on narrative chunks.
        
        Args:
            query_text: The text to search for
            filters: Optional metadata filters
            limit: Maximum number of results to return
            
        Returns:
            List of matching chunks with scores and metadata
        """
        try:
            # Use prepare_tsquery from db_access for consistent processing
            processed_query = prepare_tsquery(query_text)
            
            with self.Session() as session:
                # Build query with filters
                filter_conditions = []
                if filters:
                    if 'season' in filters:
                        filter_conditions.append(f"cm.season = :season")
                    if 'episode' in filters:
                        filter_conditions.append(f"cm.episode = :episode")
                    if 'world_layer' in filters:
                        filter_conditions.append(f"cm.world_layer = :world_layer")
                
                filter_sql = " AND ".join(filter_conditions)
                if filter_sql:
                    filter_sql = " AND " + filter_sql
                
                # Execute text search
                query_sql = f"""
                SELECT 
                    nc.id, 
                    nc.raw_text, 
                    cm.season, 
                    cm.episode, 
                    cm.scene as scene_number,
                    ts_rank(to_tsvector('english', nc.raw_text), to_tsquery('english', :query)) as score,
                    ts_headline('english', nc.raw_text, to_tsquery('english', :query), 'MaxFragments=3, MinWords=15, MaxWords=35') as highlights
                FROM 
                    narrative_chunks nc
                JOIN 
                    chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE 
                    to_tsvector('english', nc.raw_text) @@ to_tsquery('english', :query)
                    {filter_sql}
                ORDER BY 
                    score DESC
                LIMIT 
                    :limit
                """
                
                query_params = {"query": processed_query, "limit": limit}
                if filters:
                    if 'season' in filters:
                        query_params["season"] = filters['season']
                    if 'episode' in filters:
                        query_params["episode"] = filters['episode']
                    if 'world_layer' in filters:
                        query_params["world_layer"] = filters['world_layer']
                
                result = session.execute(text(query_sql), query_params)
                
                # Process results
                text_results = []
                for row in result:
                    chunk_id, raw_text, season, episode, scene_number, score, highlights = row
                    
                    text_results.append({
                        'id': str(chunk_id),
                        'chunk_id': str(chunk_id),
                        'text': raw_text,
                        'content_type': 'narrative',
                        'metadata': {
                            'season': season,
                            'episode': episode,
                            'scene_number': scene_number,
                            'highlights': highlights
                        },
                        'score': float(score),
                        'source': 'text_search'
                    })
                
                return text_results
        
        except Exception as e:
            logger.error(f"Error in text search: {e}")
            return []
    
    def process_all_narrative_files(self, glob_pattern: str = None) -> int:
        """
        Process all narrative files matching the glob pattern.
        
        Args:
            glob_pattern: Pattern to match files to process. 
                          If None, uses the pattern from settings.json
            
        Returns:
            Total number of chunks processed
        """
        # Delegate to ContentProcessor but handle reporting through interface
        try:
            # Get verbosity setting to determine if we should report progress
            verbose = MEMNON_SETTINGS.get("import", {}).get("verbose", True)
            
            # Use ContentProcessor for the actual processing
            total_chunks = self.content_processor.process_all_narrative_files(glob_pattern)
            
            # Report completion via interface if available
            if verbose and hasattr(self, 'interface') and self.interface:
                self.interface.assistant_message(f"Completed processing {total_chunks} total chunks")
                
            return total_chunks
            
        except Exception as e:
            logger.error(f"Error in process_all_narrative_files: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Report error via interface if available
            if hasattr(self, 'interface') and self.interface:
                self.interface.assistant_message(f"Error processing files: {str(e)}")
                
            raise
    
    def step(self, messages: List[Message]) -> Any:
        """
        Process incoming messages and perform MEMNON functions.
        This is the main entry point required by Letta Agent framework.
        Returns raw search results without LLM synthesis.
        
        Args:
            messages: Incoming messages to process
            
        Returns:
            Agent response (search results)
        """
        # Extract the last user message
        if not messages:
            return "No messages to process."
        
        user_message = messages[-1]
        if user_message.role != "user":
            return "Expected a user message."
        
        # Extract text from message
        message_text = ""
        for content_item in user_message.content:
            if hasattr(content_item, "text") and content_item.text:
                message_text += content_item.text
        
        if not message_text.strip():
            return "I couldn't understand your message. Please provide a query or command."
        
        # Check for special commands first
        command = self._parse_command(user_message)
        
        # Handle special commands
        if command.get("action") == "process_files":
            # Process narrative files
            glob_pattern = command.get("pattern", "*_copy_notime.md")
            
            # Execute file processing
            try:
                total_chunks = self.process_all_narrative_files(glob_pattern)
                return f"Processed {total_chunks} total chunks from files matching '{glob_pattern}'"
            except Exception as e:
                logger.error(f"Error processing files: {e}")
                return f"Error processing files: {str(e)}"
        
        elif command.get("action") == "status":
            # Return status information
            return self._get_status()
        
        elif command.get("action") == "test_hybrid_search":
            # Test hybrid search with provided query
            test_queries = command.get("queries", ["What happened to Alex?", "Who is Emilia?"])
            return self._test_hybrid_search(test_queries)
        
        # Default action: Memory query
        try:
            # Perform search using query parameters
            filters = command.get("filters", {})
            limit = command.get("limit", self.retrieval_settings["default_top_k"])
            
            # Check hybrid search flag
            use_hybrid = True  # Default
            if command.get("search_type") == "vector_only":
                use_hybrid = False
            
            # Execute search
            search_results = self.query_memory(message_text, filters=filters, k=limit, use_hybrid=use_hybrid)
            
            # Return raw results as JSON
            return search_results
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"Error: {str(e)}"
    
    def _parse_command(self, message: Message) -> Dict[str, Any]:
        """
        Parse a user message to extract commands and parameters.
        
        Args:
            message: The user message to parse
            
        Returns:
            Dictionary containing command details
        """
        # Extract text from message
        message_text = ""
        for content_item in message.content:
            if hasattr(content_item, "text") and content_item.text:
                message_text += content_item.text
        
        message_text = message_text.strip()
        
        # Default: assume it's a query
        command = {
            "action": "query",
            "text": message_text,
            "filters": {}
        }
        
        # Check for special command patterns
        if message_text.startswith("process files"):
            command["action"] = "process_files"
            # Look for pattern: parameter
            pattern_match = re.search(r"pattern:\s*[\"']?([^\"']+)[\"']?", message_text)
            if pattern_match:
                command["pattern"] = pattern_match.group(1)
            else:
                # Default pattern from settings
                command["pattern"] = MEMNON_SETTINGS.get("import", {}).get("file_pattern", "ALEX_*.md")
        
        elif message_text.startswith("status"):
            command["action"] = "status"
        
        elif message_text.startswith("test hybrid search"):
            command["action"] = "test_hybrid_search"
            
            # Look for custom queries
            queries_match = re.search(r"queries:\s*(\[.*\])", message_text)
            if queries_match:
                try:
                    # Extract the JSON array of queries
                    queries_str = queries_match.group(1)
                    import json
                    queries = json.loads(queries_str)
                    if isinstance(queries, list):
                        command["queries"] = queries
                except:
                    # If parsing fails, use default queries
                    command["queries"] = ["What happened to Alex?", "Who is Emilia?"]
        
        elif message_text.startswith("raw"):
            command["action"] = "toggle_raw"
        
        elif message_text.startswith("vector"):
            command["search_type"] = "vector_only"
            command["text"] = message_text[7:].strip()  # Remove "vector " prefix
            
        # Extract filters if present
        filters_match = re.search(r"filters:\s*(\{.*\})", message_text)
        if filters_match:
            try:
                # Extract the JSON object for filters
                filters_str = filters_match.group(1)
                import json
                filters = json.loads(filters_str)
                if isinstance(filters, dict):
                    command["filters"] = filters
            except:
                # If parsing fails, use empty filters
                pass
        
        # Extract limit if present
        limit_match = re.search(r"limit:\s*(\d+)", message_text)
        if limit_match:
            try:
                limit = int(limit_match.group(1))
                command["limit"] = limit
            except:
                # If parsing fails, use default limit
                pass
        
        return command
    
    def _get_status(self) -> str:
        """Get MEMNON status information."""
        try:
            # Collect database stats
            with self.Session() as session:
                # Count narrative chunks
                chunk_count = session.query(func.count(NarrativeChunk.id)).scalar() or 0
                
                # Count embeddings across dimension-specific tables
                embedding_count = 0
                model_counts = {}
                
                # Check each dimension table
                dimension_tables = [
                    # 'chunk_embeddings_0384d',  # Deprecated - removed
                    'chunk_embeddings_1024d',
                    'chunk_embeddings_1536d'
                ]
                
                for table_name in dimension_tables:
                    try:
                        # Count total embeddings in this table
                        count_query = text(f"SELECT COUNT(*) FROM {table_name}")
                        table_count = session.execute(count_query).scalar() or 0
                        embedding_count += table_count
                        
                        # Count by model
                        model_query = text(f"""
                        SELECT model, COUNT(*) 
                        FROM {table_name} 
                        GROUP BY model
                        """)
                        
                        for row in session.execute(model_query):
                            model, count = row
                            if model in model_counts:
                                model_counts[model] += count
                            else:
                                model_counts[model] = count
                    except Exception as e:
                        logger.warning(f"Error counting embeddings in {table_name}: {e}")
                        continue
                
                # Model counts are now populated from dimension tables
                
                # Count characters
                character_count = session.query(func.count(Character.id)).scalar() or 0
                
                # Count places
                place_count = session.query(func.count(Place.id)).scalar() or 0
                
            # Format status message
            status = f"MEMNON Status\n"
            status += f"=============\n\n"
            status += f"Database: {self.db_url}\n"
            status += f"Narrative chunks: {chunk_count}\n"
            status += f"Embeddings: {embedding_count}\n"
            
            # Add embedding distribution
            status += f"\nEmbeddings by model:\n"
            for model, count in model_counts.items():
                status += f"  - {model}: {count}\n"
            
            # Add entity counts
            status += f"\nStructured data:\n"
            status += f"  - Characters: {character_count}\n"
            status += f"  - Places: {place_count}\n"
            
            # Add search configuration
            status += f"\nSearch configuration:\n"
            
            hybrid_config = MEMNON_SETTINGS.get("retrieval", {}).get("hybrid_search", {})
            hybrid_enabled = hybrid_config.get("enabled", False)
            status += f"  - Hybrid search: {'Enabled' if hybrid_enabled else 'Disabled'}\n"
            
            if hybrid_enabled:
                status += f"  - Default weights: Vector = {hybrid_config.get('vector_weight_default', 0.6)}, "
                status += f"Text = {hybrid_config.get('text_weight_default', 0.4)}\n"
                
                if hybrid_config.get("use_query_type_weights", False):
                    status += f"  - Query-specific weights enabled\n"
            
            # Add model information
            status += f"\nActive embedding models:\n"
            for model_name in self.embedding_manager.get_available_models():
                weight = self.retrieval_settings["model_weights"].get(model_name, "unknown")
                status += f"  - {model_name} (weight: {weight})\n"
            
            return status
        
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return f"Error getting status: {str(e)}"
    
    def _test_hybrid_search(self, test_queries: List[str]) -> str:
        """
        Run a test of the hybrid search functionality.
        
        Args:
            test_queries: List of queries to test
            
        Returns:
            String containing test results
        """
        results = "Hybrid Search Test Results\n"
        results += "=======================\n\n"
        
        # Check if hybrid search is enabled
        hybrid_config = MEMNON_SETTINGS.get("retrieval", {}).get("hybrid_search", {})
        if not hybrid_config.get("enabled", False):
            results += "ERROR: Hybrid search is disabled in settings.\n"
            return results
        
        # Run each test query
        for i, query in enumerate(test_queries):
            results += f"Query {i+1}: {query}\n"
            results += f"------------------\n"
            
            try:
                # Run hybrid search
                start_time = time.time()
                search_results = self.perform_hybrid_search(query, top_k=5)
                elapsed = time.time() - start_time
                
                results += f"Found {len(search_results)} results in {elapsed:.3f} seconds\n\n"
                
                # Show top results
                for j, result in enumerate(search_results[:3]):
                    results += f"Result {j+1} (Score: {result.get('score', 0):.4f})\n"
                    
                    if 'vector_score' in result and 'text_score' in result:
                        results += f"  Vector score: {result.get('vector_score', 0):.4f}, "
                        results += f"Text score: {result.get('text_score', 0):.4f}\n"
                    
                    # Get text with truncation
                    text = result.get("text", "")
                    if len(text) > 200:
                        text = text[:197] + "..."
                    
                    results += f"  {text}\n\n"
                
                results += "\n"
                
            except Exception as e:
                results += f"Error running query: {str(e)}\n\n"
        
        return results
    
    def get_chunk_by_id(self, chunk_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific chunk by ID with minimal scene metadata.
        
        Args:
            chunk_id: The ID of the chunk to retrieve
            
        Returns:
            Dictionary containing the chunk text and scene header info
        """
        try:
            with self.Session() as session:
                query = text("""
                    SELECT 
                        nc.id,
                        nc.raw_text,
                        cm.season,
                        cm.episode,
                        cm.scene,
                        cm.place,
                        nv.world_time,
                        p.name as place_name
                    FROM narrative_chunks nc
                    LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                    LEFT JOIN narrative_view nv ON nc.id = nv.id
                    LEFT JOIN places p ON cm.place = p.id
                    WHERE nc.id = :chunk_id
                """)
                
                result = session.execute(query, {"chunk_id": chunk_id}).fetchone()
                
                if result:
                    # Format the scene header
                    header = f"Season {result.season}, Episode {result.episode}, Scene {result.scene}\n"
                    header += f"(chunk {chunk_id})\n"
                    if result.world_time:
                        header += f"{result.world_time}\n"
                    if result.place_name:
                        header += f"{result.place_name}\n"
                    
                    return {
                        "id": result.id,
                        "text": result.raw_text,
                        "header": header,
                        "full_text": header + "\n" + result.raw_text
                    }
                return None
                
        except Exception as e:
            self.logger.error(f"Error fetching chunk {chunk_id}: {str(e)}")
            return None
    
    def get_recent_chunks(self, limit: int = 10) -> Dict[str, Any]:
        """
        Retrieve the most recent narrative chunks.
        
        Args:
            limit: Maximum number of chunks to retrieve
            
        Returns:
            Dictionary containing the recent chunks and metadata
        """
        try:
            with self.Session() as session:
                query = text("""
                    SELECT nc.id, nc.raw_text, cm.season, cm.episode, cm.scene AS scene_number,
                           cm.world_layer, cm.perspective
                    FROM narrative_chunks nc
                    LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                    ORDER BY nc.id DESC
                    LIMIT :limit
                """)
                
                results = session.execute(query, {"limit": limit}).fetchall()
                
                chunks = []
                for result in results:
                    chunks.append({
                        "id": result.id,
                        "text": result.raw_text,
                        "metadata": {
                            "season": result.season,
                            "episode": result.episode,
                            "scene_number": result.scene_number,
                            "world_layer": result.world_layer,
                            "perspective": result.perspective
                        },
                        "score": 1.0,  # Recent chunks have perfect relevance
                        "source": "recent_chunks"
                    })
                
                return {
                    "query": "recent_chunks",
                    "query_type": "recent",
                    "results": chunks,
                    "metadata": {
                        "search_strategies": ["recent_chunks"],
                        "result_count": len(chunks)
                    }
                }
        except Exception as e:
            logger.error(f"Error retrieving recent chunks: {e}")
            raise RuntimeError(f"FATAL: Failed to retrieve recent chunks from database: {e}")
    
    def _get_chunk_by_id(self, chunk_id: int) -> Dict[str, Any]:
        """
        Retrieve a specific chunk by its ID.
        
        Args:
            chunk_id: The ID of the chunk to retrieve
            
        Returns:
            Dictionary containing the chunk data and metadata
        """
        try:
            with self.Session() as session:
                query = text("""
                    SELECT nc.id, nc.raw_text, cm.season, cm.episode, cm.scene AS scene_number,
                           cm.world_layer, cm.perspective
                    FROM narrative_chunks nc
                    LEFT JOIN chunk_metadata cm ON nc.id = cm.chunk_id
                    WHERE nc.id = :chunk_id
                """)
                
                result = session.execute(query, {"chunk_id": chunk_id}).fetchone()
                
                if result:
                    return {
                        "query": f"chunk_id:{chunk_id}",
                        "query_type": "direct_id",
                        "results": [{
                            "id": result.id,
                            "text": result.raw_text,
                            "metadata": {
                                "season": result.season,
                                "episode": result.episode,
                                "scene_number": result.scene_number,
                                "world_layer": result.world_layer,
                                "perspective": result.perspective
                            },
                            "score": 1.0,  # Perfect match for ID query
                            "source": "direct_id_lookup"
                        }],
                        "metadata": {
                            "search_strategies": ["direct_id_lookup"],
                            "result_count": 1
                        }
                    }
                else:
                    return {
                        "query": f"chunk_id:{chunk_id}",
                        "query_type": "direct_id",
                        "results": [],
                        "metadata": {
                            "search_strategies": ["direct_id_lookup"],
                            "result_count": 0,
                            "error": f"Chunk with ID {chunk_id} not found"
                        }
                    }
        except Exception as e:
            logger.error(f"Error retrieving chunk by ID {chunk_id}: {e}")
            return {
                "query": f"chunk_id:{chunk_id}",
                "query_type": "direct_id",
                "results": [],
                "metadata": {
                    "search_strategies": ["direct_id_lookup"],
                    "result_count": 0,
                    "error": str(e)
                }
            }
    
    def query_memory(self, query: str, query_type: Optional[str] = None, 
                   filters: Optional[Dict[str, Any]] = None, 
                   k: Optional[int] = None, use_hybrid: bool = True) -> Dict[str, Any]:
        """
        Execute a query against memory and return matching results.
        
        Args:
            query: The query text
            query_type: Optional query type (character, location, etc.)
            filters: Optional metadata filters
            k: Maximum number of results to return
            use_hybrid: Whether to use hybrid search
            
        Returns:
            Dictionary containing query results and metadata
        """
        # Log the query
        logger.info(f"Querying memory: {query}")
        
        # Check if this is a direct chunk ID query
        if query.startswith("chunk_id:"):
            try:
                chunk_id = int(query.replace("chunk_id:", "").strip())
                return self._get_chunk_by_id(chunk_id)
            except ValueError:
                logger.error(f"Invalid chunk_id format in query: {query}")
                # Fall through to regular query processing
        
        # Use default limit if not specified
        if k is None:
            k = self.retrieval_settings["default_top_k"]
        
        search_start_time = time.time()
        
        # Get query type from SearchManager if not specified
        if not query_type:
            query_info = self.query_analyzer.analyze_query(query)
            query_type = query_info.get("type", "general")
        
        logger.info(f"Query type: {query_type}")
        
        # Initialize search metadata
        search_metadata = {
            "query_time": 0,
            "total_candidate_results": 0,
            "final_result_count": 0,
            "strategies_used": []
        }
        
        # Determine search strategy based on query type
        strategies = []
        
        hybrid_enabled = MEMNON_SETTINGS.get("retrieval", {}).get("hybrid_search", {}).get("enabled", False)
        
        if use_hybrid and hybrid_enabled:
            # Add hybrid search strategy
            strategies.append({
                "type": "hybrid_search",
                "query": query,
                "filters": filters,
                "limit": k
            })
            
            # Log strategy
            logger.debug("Using hybrid search strategy")
            search_metadata["strategies_used"].append("hybrid_search")
        else:
            # Fallback to vector search
            strategies.append({
                "type": "vector_search",
                "query": query,
                "filters": filters,
                "limit": k
            })
            
            # Log strategy
            logger.debug("Using vector search strategy")
            search_metadata["strategies_used"].append("vector_search")
        
        # Execute search strategies
        all_results = []
        
        for strategy in strategies:
            strategy_type = strategy["type"]
            
            try:
                if strategy_type == "hybrid_search":
                    # Execute hybrid search using SearchManager
                    results = self.search_manager.perform_hybrid_search(
                        query_text=strategy["query"],
                        filters=strategy.get("filters"),
                        top_k=strategy.get("limit", k)
                    )
                    all_results.extend(results)
                    
                elif strategy_type == "vector_search":
                    # Execute vector search using SearchManager
                    results = self.search_manager.query_vector_search(
                        query_text=strategy["query"],
                        collections=["narrative_chunks"],
                        filters=strategy.get("filters"),
                        top_k=strategy.get("limit", k)
                    )
                    all_results.extend(results)
                    
                else:
                    logger.warning(f"Unknown search strategy: {strategy_type}")
            
            except Exception as e:
                logger.error(f"Error in {strategy_type}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Final results selection - Deduplicate by ID and sort by score
        seen_ids = set()
        final_results = []
        
        for result in all_results:
            result_id = result.get("id", None)
            if result_id and result_id not in seen_ids:
                seen_ids.add(result_id)
                final_results.append(result)
        
        # Sort by score, descending
        final_results = sorted(final_results, key=lambda x: x.get("score", 0), reverse=True)
        
        # Truncate to requested limit
        search_results_initial = final_results[:k]
        
        # Apply cross-encoder reranking if enabled
        cross_encoder_config = MEMNON_SETTINGS.get("retrieval", {}).get("cross_encoder_reranking", {})
        if cross_encoder_config.get("enabled", False) and len(search_results_initial) > 0:
            try:
                logger.info("Applying cross-encoder reranking")
                search_metadata["strategies_used"].append("cross_encoder_reranking")
                
                # Get query type specific weight if available
                alpha = cross_encoder_config.get("blend_weight", 0.3)
                if cross_encoder_config.get("use_query_type_weights", False):
                    if query_type in cross_encoder_config.get("weights_by_query_type", {}):
                        alpha = cross_encoder_config["weights_by_query_type"][query_type]
                        logger.debug(f"Using query-type-specific weight for '{query_type}': {alpha}")
                
                # Determine other parameters
                top_k_rerank = min(cross_encoder_config.get("top_k", 10), len(search_results_initial))
                batch_size = cross_encoder_config.get("batch_size", 8)
                use_sliding_window = cross_encoder_config.get("use_sliding_window", True)
                model_path = cross_encoder_config.get("model_path", "naver-trecdl22-crossencoder-debertav3")
                
                rerank_start_time = time.time()
                
                # Apply reranking
                # Get use_8bit parameter from settings
                use_8bit = cross_encoder_config.get("use_8bit", False)
                logger.info(f"Using 8-bit quantization for cross-encoder: {use_8bit}")
                final_results = rerank_results(
                    query=query,
                    results=search_results_initial,
                    top_k=top_k_rerank,
                    alpha=alpha,
                    batch_size=batch_size,
                    use_sliding_window=use_sliding_window,
                    model_path=model_path,
                    use_8bit=use_8bit
                )
                
                rerank_time = time.time() - rerank_start_time
                search_metadata["rerank_time"] = rerank_time
                logger.info(f"Cross-encoder reranking completed in {rerank_time:.3f} seconds")
                
            except Exception as e:
                logger.error(f"Error in cross-encoder reranking: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Fall back to initial results if reranking fails
                final_results = search_results_initial
                logger.warning("Using initial search results due to reranking failure")
        else:
            # Use initial results if reranking is disabled
            final_results = search_results_initial
        
        # Complete search metadata
        search_metadata["query_time"] = time.time() - search_start_time
        search_metadata["total_candidate_results"] = len(all_results)
        search_metadata["final_result_count"] = len(final_results)
        
        # Print results to console if debug mode
        if self.debug:
            print("\n--- Search results for query ---")
            print(f"Query: {query}")
            print(f"Type: {query_type}")
            print(f"Found {len(final_results)} results in {search_metadata['query_time']:.3f} seconds")
            
            # Print raw results for inspection
            for i, result in enumerate(all_results):
                score = result.get("score", 0.0)
                vector_score = result.get("vector_score", None)
                text_score = result.get("text_score", None)
                
                score_info = f"Score: {score:.4f}"
                if vector_score is not None and text_score is not None:
                    score_info += f" (V: {vector_score:.4f}, T: {text_score:.4f})"
                    
                text = result.get("text", "")
                if len(text) > 200:
                    text = text[:197] + "..."
                print(f"Result {i+1} ({score_info}): {text}")
            else:
                print("No results found")
            
            print("\n--- Final results ---")
            for i, result in enumerate(final_results):
                source = result.get("source", "unknown")
                score = result.get("score", 0.0)
                
                # Add reranker score if available
                reranker_score = result.get("reranker_score", None)
                original_score = result.get("original_score", None)
                score_info = f"Score: {score:.4f}"
                if reranker_score is not None and original_score is not None:
                    score_info = f"Score: {score:.4f} (Orig: {original_score:.4f}, Rerank: {reranker_score:.4f})"
                
                # Extract metadata for display
                metadata_str = ""
                if "metadata" in result:
                    metadata = result.get("metadata", {})
                    meta_items = []
                    if "season" in metadata and "episode" in metadata:
                        meta_items.append(f"S{metadata['season']}E{metadata['episode']}")
                    if "scene_number" in metadata:
                        meta_items.append(f"Scene {metadata['scene_number']}")
                    if "matched_keyword" in metadata:
                        meta_items.append(f"Matched '{metadata['matched_keyword']}'")
                    if "perspective" in metadata:
                        meta_items.append(f"Perspective: {metadata['perspective']}")
                    
                    if meta_items:
                        metadata_str = f" [{', '.join(meta_items)}]"
                
                # Get text with truncation
                text = result.get("text", "")
                if len(text) > 200:
                    text = text[:197] + "..."
                
                print(f"Result {i+1} ({score_info}){metadata_str}: {text}")
            print("=============================\n")
            
        # Format final response
        response = {
            "query": query,
            "query_type": query_type,
            "results": final_results,
            "metadata": {
                "search_strategies": search_metadata["strategies_used"],
                "search_stats": search_metadata,
                "result_count": len(final_results),
                "filters_applied": filters
            }
        }
        
        return response
    
    def process_chunked_file(self, file_path: str) -> int:
        """
        Process a file containing chunked narrative text.
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            Number of chunks processed
        """
        # Delegate to ContentProcessor
        return self.content_processor.process_chunked_file(file_path)
    
    def store_narrative_chunk(self, text: str, metadata: Dict[str, Any]) -> int:
        """
        Store a narrative chunk in the database and generate embeddings.
        
        Args:
            text: The chunk text
            metadata: Metadata dictionary with season, episode, etc.
            
        Returns:
            The ID of the stored chunk
        """
        # Delegate to ContentProcessor
        return self.content_processor.store_narrative_chunk(text, metadata)
    
    def _generate_chunk_embeddings(self, session, chunk_id: int, text: str):
        """
        Generate embeddings for a chunk using all active models.
        Stores embeddings in dimension-specific tables with proper vector types.
        
        Args:
            session: The active database session
            chunk_id: The ID of the chunk
            text: The text to encode
        """
        # Delegate to ContentProcessor
        return self.content_processor._generate_chunk_embeddings(session, chunk_id, text)