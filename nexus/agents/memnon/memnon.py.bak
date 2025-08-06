"""
MEMNON Agent - Unified Memory Access System for Narrative Intelligence

This agent is responsible for all memory operations, including:
- Managing embeddings across multiple models
- Storing and retrieving narrative chunks
- Cross-referencing structured data with vector embeddings
- Implementing specialized query patterns for different memory tiers
- Synthesizing responses using local LLM capabilities
"""

import os
import re
import uuid
import logging
import json
import time
import requests
from typing import Dict, List, Tuple, Optional, Union, Any, Set
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, Column, Table, MetaData, text
from sqlalchemy.dialects.postgresql import UUID, BYTEA, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# Sentence transformers for embedding
from sentence_transformers import SentenceTransformer

# Letta framework
from letta.agent import Agent
from letta.schemas.agent import AgentState 
from letta.schemas.memory import Memory
from letta.schemas.block import Block, CreateBlock
from letta.schemas.message import Message
from letta.embeddings import EmbeddingEndpoint

# Load settings
def load_settings():
    """Load settings from settings.json file"""
    try:
        settings_path = Path("/Users/pythagor/nexus/settings.json")
        if settings_path.exists():
            with open(settings_path, 'r') as f:
                return json.load(f)
        else:
            print(f"Warning: settings.json not found at {settings_path}")
            return {}
    except Exception as e:
        print(f"Error loading settings: {e}")
        return {}

# Global settings
SETTINGS = load_settings()
MEMNON_SETTINGS = SETTINGS.get("Agent Settings", {}).get("MEMNON", {})
GLOBAL_SETTINGS = SETTINGS.get("Agent Settings", {}).get("global", {})

# Configure logging
log_config = MEMNON_SETTINGS.get("logging", {})
log_level = getattr(logging, log_config.get("level", "INFO"))
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

class ChunkEmbedding(Base):
    __tablename__ = 'chunk_embeddings'
    
    id = Column(sa.BigInteger, primary_key=True)
    chunk_id = Column(sa.BigInteger, sa.ForeignKey('narrative_chunks.id', ondelete='CASCADE'), nullable=False)
    model = Column(sa.String(100), nullable=False)
    embedding = Column(sa.LargeBinary, nullable=False)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    dimensions = Column(sa.Integer, default=1024)
    
    __table_args__ = (
        sa.UniqueConstraint('chunk_id', 'model', name='uix_chunk_model'),
    )

class ChunkMetadata(Base):
    __tablename__ = 'chunk_metadata'
    
    id = Column(sa.BigInteger, primary_key=True)
    chunk_id = Column(sa.BigInteger, sa.ForeignKey('narrative_chunks.id', ondelete='CASCADE'), nullable=False)
    season = Column(sa.Integer)
    episode = Column(sa.Integer)
    scene = Column(sa.Integer)
    world_layer = Column(sa.String(50))
    time_delta = Column(sa.String(100))
    location = Column(sa.String(255))
    atmosphere = Column(sa.String(255))
    characters = Column(sa.JSON)
    arc_position = Column(sa.String(50))
    direction = Column(sa.JSON)
    magnitude = Column(sa.String(50))
    character_elements = Column(sa.JSON)
    perspective = Column(sa.JSON)
    interactions = Column(sa.JSON)
    dialogue_analysis = Column(sa.JSON)
    emotional_tone = Column(sa.JSON)
    narrative_function = Column(sa.JSON)
    narrative_techniques = Column(sa.JSON)
    thematic_elements = Column(sa.JSON)
    causality = Column(sa.JSON)
    continuity_markers = Column(sa.JSON)
    metadata_version = Column(sa.String(20))
    generation_date = Column(sa.DateTime)

class Character(Base):
    __tablename__ = 'characters'
    
    id = Column(sa.BigInteger, primary_key=True)
    name = Column(sa.String(50), nullable=False)
    aliases = Column(ARRAY(sa.String))
    summary = Column(sa.String(500), nullable=False)
    appearance = Column(sa.Text, nullable=False)
    background = Column(sa.Text, nullable=False)
    personality = Column(sa.Text, nullable=False)
    conflicts = Column(sa.Text)
    emotional_state = Column(sa.String(500), nullable=False)
    undisclosed_internal = Column(sa.Text)
    current_activity = Column(sa.String(500))
    current_location = Column(sa.String(500))
    extra_data = Column(sa.JSON)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())

class Place(Base):
    __tablename__ = 'places'
    
    id = Column(sa.BigInteger, primary_key=True)
    name = Column(sa.String(50), nullable=False)
    type = Column(sa.String, nullable=False)
    location = Column(sa.String(250), nullable=False)
    summary = Column(sa.String(1000), nullable=False)
    inhabitants = Column(ARRAY(sa.String))
    historical_significance = Column(sa.Text)
    current_status = Column(sa.String(500))
    undiscovered = Column(sa.Text)
    extra_data = Column(sa.JSON)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())


class MEMNON(Agent):
    """
    MEMNON (Unified Memory Access System) agent responsible for accessing and 
    retrieving narrative information across all memory types.
    """
    
    def __init__(self, 
                 interface, 
                 agent_state: Optional[AgentState] = None,
                 user = None,
                 db_url: str = None,
                 model_id: str = None,
                 model_path: str = None,
                 debug: bool = None,
                 **kwargs):
        """
        Initialize MEMNON agent with unified memory access capabilities.
        
        Args:
            interface: Interface for agent communication
            agent_state: Agent state from Letta framework (optional in direct mode)
            user: User information (optional in direct mode)
            db_url: PostgreSQL database URL
            model_id: LM Studio model ID to use
            model_path: Path to local model file (fallback)
            debug: Enable debug logging
            **kwargs: Additional arguments
        """
        # Handle direct mode (when agent_state is None)
        self.direct_mode = agent_state is None
        
        if self.direct_mode:
            # In direct mode, we skip the parent Agent initialization
            # and just set up the bare minimum we need
            self.interface = interface
            self.agent_state = None  # We don't use this in direct mode
            self.user = user
            self.block_manager = None  # Not used in direct mode
        else:
            # Normal Letta framework mode, initialize parent Agent class
            super().__init__(interface, agent_state, user, **kwargs)
            
            # Initialize specialized memory blocks if not present
            self._initialize_memory_blocks()
        
        # Configure logging level based on settings or parameter
        if debug is None:
            debug = MEMNON_SETTINGS.get("debug", False)
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Debug logging enabled")
        
        # Store LLM settings
        self.model_id = model_id or DEFAULT_MODEL_ID
        self.model_path = model_path
        logger.info(f"Using LLM model: {self.model_id}")
        
        # Set up database connection
        self.db_url = db_url or DEFAULT_DB_URL
        logger.info(f"Using database URL: {self.db_url}")
        self.db_engine = self._initialize_database_connection()
        self.Session = sessionmaker(bind=self.db_engine)
        
        # Set up embedding models
        self.embedding_models = self._initialize_embedding_models()
        
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
            
        # Set debug flag for LLM-directed search
        self.use_llm_search_planning = MEMNON_SETTINGS.get("query", {}).get("use_llm_planning", False)
        
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
        
        # Log the retrieval settings
        logger.debug(f"Retrieval settings: {json.dumps(self.retrieval_settings, indent=2)}")
        
        # Memory type registry - maps virtual memory tier to actual storage
        self.memory_tiers = {
            "strategic": {"type": "database", "tables": ["events", "threats", "ai_notebook"]},
            "entity": {"type": "database", "tables": ["characters", "places", "factions", "items"]},
            "narrative": {"type": "vector", "collections": ["narrative_chunks"]},
        }
        
        # Query type registry - maps query types to appropriate tables and search methods
        self.query_types = {
            "character": {
                "primary_tier": "entity",
                "primary_tables": ["characters"],
                "secondary_tier": "narrative",
                "secondary_search": "vector_search",
                "extraction_focus": ["character relationships", "character development", "character actions"]
            },
            "location": {
                "primary_tier": "entity",
                "primary_tables": ["places"],
                "secondary_tier": "narrative",
                "secondary_search": "vector_search",
                "extraction_focus": ["location descriptions", "events at locations"]
            },
            "event": {
                "primary_tier": "narrative",
                "primary_tables": ["events"],
                "secondary_tier": "strategic",
                "secondary_search": "vector_search",
                "extraction_focus": ["event details", "event consequences", "event timeline"]
            },
            "theme": {
                "primary_tier": "narrative",
                "primary_search": "vector_search",
                "extraction_focus": ["thematic elements", "symbolic patterns", "motifs"]
            },
            "relationship": {
                "primary_tier": "entity",
                "primary_tables": ["character_relationships"],
                "secondary_tier": "narrative",
                "secondary_search": "vector_search",
                "extraction_focus": ["character interactions", "relationship dynamics", "emotional connections"]
            },
            "narrative": {
                "primary_tier": "narrative",
                "primary_search": "vector_search",
                "extraction_focus": ["plot points", "story progression", "scene setting"]
            }
        }
        
        logger.info("MEMNON agent initialized")
    
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
            
            logger.info(f"Successfully connected to database at {self.db_url}")
            return engine
        
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise ConnectionError(f"Database connection failed: {e}")
    
    def _initialize_embedding_models(self) -> Dict[str, Any]:
        """Initialize embedding models for semantic retrieval."""
        embedding_models = {}
        
        try:
            # Get model configurations from settings
            model_configs = MEMNON_SETTINGS.get("models", {})
            
            # Load each model defined in settings
            for model_name, model_config in model_configs.items():
                logger.info(f"Loading {model_name} embedding model...")
                
                # Get model paths
                local_path = model_config.get("local_path")
                remote_path = model_config.get("remote_path")
                dimensions = model_config.get("dimensions")
                
                # Try loading from local path first
                if local_path and Path(local_path).exists():
                    try:
                        model = SentenceTransformer(local_path)
                        embedding_models[model_name] = model
                        logger.info(f"Loaded {model_name} from local path: {local_path}")
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to load {model_name} from local path: {e}")
                
                # Fall back to remote path if available
                if remote_path:
                    try:
                        model = SentenceTransformer(remote_path)
                        embedding_models[model_name] = model
                        logger.info(f"Loaded {model_name} from remote path: {remote_path}")
                    except Exception as e:
                        logger.warning(f"Failed to load {model_name} from remote path: {e}")
            
            # If no models were loaded from settings, try default paths as fallback
            if not embedding_models:
                logger.warning("No models loaded from settings, trying defaults...")
                
                try:
                    bge_large = SentenceTransformer("BAAI/bge-large-en")
                    embedding_models["bge-large"] = bge_large
                    logger.info("Loaded default BGE-large embedding model")
                except Exception as e:
                    logger.warning(f"Failed to load default BGE-large: {e}")
                
                try:
                    e5_large = SentenceTransformer("intfloat/e5-large-v2")
                    embedding_models["e5-large"] = e5_large
                    logger.info("Loaded default E5-large embedding model")
                except Exception as e:
                    logger.warning(f"Failed to load default E5-large: {e}")
                
                # Try to load fine-tuned BGE-small model from default local path
                default_bge_small_path = Path("/Users/pythagor/nexus/models/bge_small_finetuned_20250320_153654")
                if default_bge_small_path.exists():
                    try:
                        bge_small = SentenceTransformer(str(default_bge_small_path))
                        embedding_models["bge-small-custom"] = bge_small
                        logger.info("Loaded default BGE-small-custom embedding model")
                    except Exception as e:
                        logger.warning(f"Failed to load default BGE-small-custom: {e}")
            
            if not embedding_models:
                logger.error("No embedding models could be loaded. Vector search will not be available.")
            else:
                logger.info(f"Loaded {len(embedding_models)} embedding models: {', '.join(embedding_models.keys())}")
            
            return embedding_models
        
        except Exception as e:
            logger.error(f"Error initializing embedding models: {e}")
            # Return any successfully loaded models rather than failing completely
            return embedding_models

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
        
        # Get regex pattern from settings or use default
        chunk_regex_pattern = MEMNON_SETTINGS.get("import", {}).get(
            "chunk_regex", r'<!--\s*SCENE BREAK:\s*(S(\d+)E(\d+))_(\d+).*-->'
        )
        
        # Compile regex for scene breaks
        try:
            scene_break_regex = re.compile(chunk_regex_pattern)
        except re.error as e:
            logger.error(f"Invalid regex pattern in settings: {e}")
            # Fall back to default regex
            scene_break_regex = re.compile(r'<!--\s*SCENE BREAK:\s*(S(\d+)E(\d+))_(\d+).*-->')
        
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find all scene breaks
        scene_breaks = list(scene_break_regex.finditer(content))
        if not scene_breaks:
            logger.warning(f"No scene breaks found in {file_path} using pattern: {chunk_regex_pattern}")
            return 0
        
        chunks_processed = 0
        
        # Process each chunk
        for i in range(len(scene_breaks)):
            start_match = scene_breaks[i]
            
            try:
                # Extract metadata from the scene break
                episode_str = start_match.group(1)  # e.g., "S01E05"
                season = int(start_match.group(2))
                episode = int(start_match.group(3))
                scene_number = int(start_match.group(4))
                
                # Construct the chunk ID
                chunk_id = f"{episode_str}_{scene_number:03d}"
                
                # Determine chunk boundaries
                start_pos = start_match.start()
                if i < len(scene_breaks) - 1:
                    end_pos = scene_breaks[i + 1].start()
                else:
                    end_pos = len(content)
                
                # Extract chunk text
                chunk_text = content[start_pos:end_pos]
                
                # Store the chunk with metadata
                self.store_narrative_chunk(
                    chunk_text=chunk_text,
                    metadata={
                        "chunk_id": chunk_id,
                        "season": season,
                        "episode": episode,
                        "scene_number": scene_number,
                        "world_layer": "primary"  # Default to primary world layer
                    }
                )
                chunks_processed += 1
                logger.info(f"Processed chunk {chunk_id} from {file_path.name}")
                
            except Exception as e:
                chunk_num = i + 1
                logger.error(f"Error processing chunk #{chunk_num} from {file_path.name}: {e}")
        
        logger.info(f"Completed processing {chunks_processed} chunks from {file_path}")
        return chunks_processed
    
    def generate_embedding(self, text: str, model_key: str = "bge-large") -> List[float]:
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
                # Remove any existing chunk with this ID
                existing = session.query(NarrativeChunk).filter(NarrativeChunk.id == chunk_id_str).first()
                if existing:
                    logger.info(f"Replacing existing chunk {chunk_id_str}")
                    session.delete(existing)
                    session.commit()
            else:
                # Generate a UUID for the chunk
                chunk_id_str = str(uuid.uuid4())
            
            # Convert to UUID
            chunk_id = uuid.UUID(chunk_id_str) if not isinstance(chunk_id_str, uuid.UUID) else chunk_id_str
            
            # Create narrative chunk
            narrative_chunk = NarrativeChunk(
                id=chunk_id,
                raw_text=chunk_text
            )
            session.add(narrative_chunk)
            session.flush()  # Flush to get the sequence number
            
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
                    
                    # Convert embedding to bytes for storage
                    try:
                        # First try using pgvector's native array conversion if available
                        try:
                            from pgvector.sqlalchemy import Vector
                            embedding_obj = Vector(embedding)
                            embedding_bytes = embedding_obj.to_bytes()
                        except (ImportError, AttributeError):
                            # Fall back to standard SQLAlchemy array conversion
                            import numpy as np
                            embedding_arr = np.array(embedding, dtype=np.float32)
                            embedding_bytes = embedding_arr.tobytes()
                    except Exception as e:
                        # If all else fails, use basic SQLAlchemy conversion
                        embedding_bytes = sa.dialects.postgresql.ARRAY(sa.Float).bind_processor(None)(embedding)
                    
                    # Create chunk embedding
                    chunk_embedding = ChunkEmbedding(
                        chunk_id=chunk_id,
                        model=model_key,
                        embedding=embedding_bytes
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
    
    def query_memory(self, 
                 query: str, 
                 query_type: Optional[str] = None, 
                 memory_tiers: Optional[List[str]] = None, 
                 filters: Optional[Dict[str, Any]] = None, 
                 k: int = 10) -> Dict[str, Any]:
        """
        Unified memory query interface for retrieving narrative information.
        Uses LLM-directed search to dynamically select appropriate search strategies.
        
        Args:
            query: The narrative query
            query_type: Optional type of query (character, event, theme, relationship)
            memory_tiers: Optional specific memory tiers to query
            filters: Optional filters to apply (time, characters, locations, etc.)
            k: Number of results to return
            
        Returns:
            Dict containing query results and metadata
        """
        if filters is None:
            filters = {}
            
        # Process query to understand information need
        query_info = self._analyze_query(query, query_type)
        search_start_time = time.time()
        
        # Always use LLM search planning - no fallback
        search_plan = self._generate_search_plan(query, query_info)
        logger.info(f"Using LLM-generated search plan: {search_plan['explanation']}")
        
        # Determine which memory tiers to access if not specified
        if not memory_tiers:
            memory_tiers = self._determine_relevant_memory_tiers(query_info)
        
        # Execute each search strategy in priority order
        all_results = {}
        combined_results = []
        search_metadata = {
            "strategies_executed": [],
            "strategy_stats": {},
            "total_results": 0
        }
        
        # Sort strategies by priority
        strategies = sorted(search_plan["strategies"], key=lambda s: s["priority"])
        
        # Execute each strategy
        for strategy in strategies:
            strategy_type = strategy["type"]
            strategy_start = time.time()
            
            try:
                if strategy_type == "structured_data":
                    # Query structured database tables
                    tables = strategy.get("tables", [])
                    tier_results = self._query_structured_data(query_info, tables, filters, k)
                    logger.info(f"Structured data search found {len(tier_results)} results from {len(tables)} tables")
                    
                elif strategy_type == "vector_search":
                    # Query vector store
                    collections = strategy.get("collections", ["narrative_chunks"])
                    tier_results = self._query_vector_search(query, collections, filters, k)
                    logger.info(f"Vector search found {len(tier_results)} results")
                    
                elif strategy_type == "text_search":
                    # Direct text search using SQL
                    keywords = strategy.get("keywords", [query])
                    tier_results = self._query_text_search(query_info, keywords, filters, k)
                    logger.info(f"Text search found {len(tier_results)} results using {len(keywords)} keywords")
                    
                else:
                    logger.warning(f"Unknown search strategy type: {strategy_type}")
                    continue
                
                # Record strategy results and stats
                strategy_time = time.time() - strategy_start
                search_metadata["strategies_executed"].append(strategy_type)
                search_metadata["strategy_stats"][strategy_type] = {
                    "execution_time": strategy_time,
                    "results_count": len(tier_results)
                }
                
                # Store and extend results
                all_results[strategy_type] = tier_results
                combined_results.extend(tier_results)
                
                # Always run all search strategies, no matter how many results were found
                # Let the LLM determine what's relevant from all available data
                pass
                    
            except Exception as e:
                logger.error(f"Error executing search strategy {strategy_type}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # No complex deduplication logic - simply collect all results
        # Make sure to normalize content/text fields for consistency
        all_collected_results = []
        for result in combined_results:
            self._normalize_result_fields([result])
            all_collected_results.append(result)
            
        # We still need basic deduplication by ID to avoid showing the same content twice
        # But we don't use any score-based filtering or query parsing
        deduplicated_results = {}
        for result in all_collected_results:
            result_id = result.get("id") or result.get("chunk_id")
            if result_id:
                # To avoid scoring bias, we just keep the first occurrence of each ID
                if result_id not in deduplicated_results:
                    deduplicated_results[result_id] = result
        
        # Convert back to list and sort by score
        synthesized_results = list(deduplicated_results.values())
        synthesized_results.sort(key=lambda x: x["score"], reverse=True)
        synthesized_results = synthesized_results[:k]  # Limit to requested number
        
        # Validate results for query term presence
        self._validate_search_results(query, query_info, synthesized_results)
        
        # Record overall search metadata
        search_metadata["total_time"] = time.time() - search_start_time
        search_metadata["total_results"] = len(synthesized_results)
        
        # Format final response
        response = {
            "query": query,
            "query_type": query_info["type"],
            "results": synthesized_results,
            "metadata": {
                "search_plan": search_plan["explanation"],
                "search_stats": search_metadata,
                "result_count": len(synthesized_results),
                "filters_applied": filters
            }
        }
        
        return response
    
    def _query_vector_search(self, query_text: str, collections: List[str], filters: Dict[str, Any], top_k: int) -> List[Dict[str, Any]]:
        """
        Query the vector database for chunks similar to the query text.
        
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
            # Generate embeddings for each model
            embeddings = {}
            for model_key in self.embedding_models:
                try:
                    embeddings[model_key] = self.generate_embedding(query_text, model_key)
                except Exception as e:
                    logger.error(f"Error generating {model_key} embedding: {e}")
            
            if not embeddings:
                logger.error("No embeddings generated for query")
                return []
            
            results = {}
            
            # Use direct raw SQL to avoid SQLAlchemy complexities with pgvector
            # Process each model separately
            for model_key, embedding in embeddings.items():
                # Connect directly using psycopg2
                import psycopg2
                from urllib.parse import urlparse
                
                # Parse database URL
                parsed_url = urlparse(self.db_url)
                username = parsed_url.username
                password = parsed_url.password
                database = parsed_url.path[1:]  # Remove leading slash
                hostname = parsed_url.hostname
                port = parsed_url.port or 5432
                
                # Connect to the database
                conn = psycopg2.connect(
                    host=hostname,
                    port=port,
                    user=username,
                    password=password,
                    database=database
                )
                
                try:
                    with conn.cursor() as cursor:
                        # Build filter conditions
                        filter_conditions = []
                        if filters:
                            if 'season' in filters:
                                filter_conditions.append(f"cm.season = {filters['season']}")
                            if 'episode' in filters:
                                filter_conditions.append(f"cm.episode = {filters['episode']}")
                            if 'world_layer' in filters:
                                filter_conditions.append(f"cm.world_layer = '{filters['world_layer']}'")
                        
                        filter_sql = " AND ".join(filter_conditions)
                        if filter_sql:
                            filter_sql = " AND " + filter_sql
                        
                        # Build embedding array as a string - pgvector expects [x,y,z] format
                        embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'
                        
                        # Execute raw SQL query with pgvector's <=> operator
                        sql = f"""
                        SELECT 
                            nc.id, 
                            nc.raw_text, 
                            cm.season, 
                            cm.episode, 
                            cm.scene as scene_number,
                            1 - (ce.embedding <=> %s::vector) as score
                        FROM 
                            narrative_chunks nc
                        JOIN 
                            chunk_embeddings ce ON nc.id = ce.chunk_id
                        JOIN 
                            chunk_metadata cm ON nc.id = cm.chunk_id
                        WHERE 
                            ce.model = %s
                            {filter_sql}
                        ORDER BY 
                            score DESC
                        LIMIT 
                            %s
                        """
                        
                        # Execute the query
                        cursor.execute(sql, (embedding_str, model_key, top_k))
                        query_results = cursor.fetchall()
                        
                        # Process results
                        for result in query_results:
                            chunk_id, raw_text, season, episode, scene_number, score = result
                            chunk_id = str(chunk_id)
                            
                            if chunk_id not in results:
                                results[chunk_id] = {
                                    'id': chunk_id,
                                    'chunk_id': chunk_id,
                                    'text': raw_text,
                                    'content_type': 'narrative',
                                    'metadata': {
                                        'season': season,
                                        'episode': episode,
                                        'scene_number': scene_number
                                    },
                                    'model_scores': {},
                                    'score': 0.0,
                                    'source': 'vector_search'
                                }
                            
                            # Store score from this model
                            results[chunk_id]['model_scores'][model_key] = score
                finally:
                    conn.close()
            
            # Calculate weighted average scores
            model_weights = self.retrieval_settings['model_weights']
            for chunk_id, result in results.items():
                weighted_score = 0.0
                total_weight = 0.0
                
                for model_key, weight in model_weights.items():
                    if model_key in result['model_scores']:
                        weighted_score += result['model_scores'][model_key] * weight
                        total_weight += weight
                
                if total_weight > 0:
                    result['score'] = weighted_score / total_weight
            
            # Sort by final score and return top_k
            sorted_results = sorted(results.values(), key=lambda x: x['score'], reverse=True)
            return sorted_results[:top_k]
        
        except Exception as e:
            logger.error(f"Error in vector search: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
        # Use pattern from settings if not provided
        if glob_pattern is None:
            glob_pattern = MEMNON_SETTINGS.get("import", {}).get("file_pattern", "ALEX_*.md")
        
        # Get batch size from settings
        batch_size = MEMNON_SETTINGS.get("import", {}).get("batch_size", 10)
        verbose = MEMNON_SETTINGS.get("import", {}).get("verbose", True)
        
        # Find all files matching the pattern
        import glob as glob_module
        files = glob_module.glob(glob_pattern)
        
        if not files:
            logger.warning(f"No files found matching pattern: {glob_pattern}")
            return 0
        
        # Log settings used
        logger.info(f"Processing files with pattern: {glob_pattern}")
        logger.info(f"Batch size: {batch_size}")
        
        total_chunks = 0
        for i, file_path in enumerate(files):
            logger.info(f"Processing file {i+1}/{len(files)}: {file_path}")
            try:
                chunks_processed = self.process_chunked_file(file_path)
                total_chunks += chunks_processed
                
                # Report progress
                if verbose:
                    self.interface.assistant_message(f"Processed {chunks_processed} chunks from {file_path}")
                
                # Process in batches to avoid overloading the system
                if batch_size > 0 and (i + 1) % batch_size == 0 and i < len(files) - 1:
                    logger.info(f"Completed batch of {batch_size} files. Taking a short break...")
                    time.sleep(2)  # Brief pause between batches
            
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                self.interface.assistant_message(f"Error processing {file_path}: {str(e)}")
        
        logger.info(f"Completed processing {total_chunks} total chunks from {len(files)} files")
        return total_chunks
    
    def step(self, messages: List[Message]) -> Any:
        """
        Process incoming messages and perform MEMNON functions.
        This is the main entry point required by Letta Agent framework.
        
        Args:
            messages: Incoming messages to process
            
        Returns:
            Agent response
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
            total_chunks = self.process_all_narrative_files(glob_pattern)
            return f"Processed {total_chunks} chunks from narrative files matching {glob_pattern}"
        
        elif command.get("action") == "status":
            # Return agent status
            return self._get_status()
            
        # Handle interactive mode with natural language queries
        elif "query" in command.get("action", "") or "search" in message_text.lower() or "?" in message_text:
            # Treat as natural language query
            logger.info(f"Processing natural language query: {message_text}")
            
            # Extract filters from command if present
            filters = command.get("filters", {})
            
            # Use unified query interface
            query_results = self.query_memory(
                query=message_text,
                query_type=None,  # Let the analysis determine the type
                filters=filters,
                k=10
            )
            
            # Log search statistics
            strategies = query_results.get("metadata", {}).get("strategies_executed", [])
            result_count = query_results.get("metadata", {}).get("result_count", 0)
            logger.info(f"Query used strategies: {', '.join(strategies)} and found {result_count} results")
            
            # Generate synthesized response
            response = self._synthesize_response(
                query=message_text,
                results=query_results["results"],
                query_type=query_results["query_type"]
            )
            
            return response
            
        # Treat everything else as a natural language query
        else:
            logger.info(f"Treating message as natural language query: {message_text}")
            
            # Use unified query interface with LLM-directed search
            query_results = self.query_memory(
                query=message_text,
                query_type=None,  # Let the analysis determine the type
                filters={},
                k=10
            )
            
            # Log search plan and statistics
            search_plan = query_results.get("metadata", {}).get("search_plan", "No search plan generated")
            logger.info(f"Search plan: {search_plan}")
            
            # Generate synthesized response
            response = self._synthesize_response(
                query=message_text,
                results=query_results["results"],
                query_type=query_results["query_type"]
            )
            
            # Add search metadata to response for debugging
            if "debug_info" not in response:
                response["debug_info"] = {}
            response["debug_info"]["search_plan"] = search_plan
            response["debug_info"]["query_type"] = query_results["query_type"]
            
            return response
    
    def _generate_search_plan(self, query: str, query_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a dynamic search plan for a given query using LLM reasoning.
        
        Args:
            query: The original query string
            query_info: Analyzed query information
            
        Returns:
            Search plan with strategies in priority order
        """
        import json
        import json
        
        # Prepare information about available data sources
        structured_tables = {
            "characters": "detailed information about characters including name, background, appearance, etc.",
            "places": "locations and settings with descriptions",
            "events": "significant narrative events",
            "character_relationships": "information about relationships between characters",
            "threats": "potential threats and dangers in the narrative",
            "factions": "groups and organizations"
        }
        
        vector_collections = {
            "narrative_chunks": "raw text passages from the narrative with embedded semantic meaning"
        }
        
        # Construct the prompt without f-strings for the JSON template
        prompt = """You are MEMNON, a sophisticated narrative intelligence system. 
Given a user query, your task is to create the optimal search strategy across multiple data sources.

QUERY: \"""" + query + """\"
QUERY TYPE: """ + query_info["type"] + """
ENTITIES MENTIONED: """ + json.dumps(query_info.get("entities", [])) + """
KEYWORDS: """ + json.dumps(query_info.get("keywords", [])) + """

AVAILABLE DATA SOURCES:
1. Structured tables (exact data lookup):
""" + json.dumps(structured_tables, indent=2) + """

2. Vector database (semantic search by meaning):
""" + json.dumps(vector_collections, indent=2) + """

3. Text search (direct keyword matching): 
Can perform fuzzy or exact matches on raw text.

Consider the following when creating your search plan:
- Which data source is most likely to contain the information needed?
- What order of operations would be most efficient?
- Could simpler searches be tried before more complex ones?
- How would you combine results from different sources?

YOUR RESPONSE MUST BE A SINGLE JSON OBJECT with this structure:

{
  "strategies": [
    {
      "type": "structured_data",
      "priority": 1, 
      "tables": ["characters", "places"]
    },
    {
      "type": "vector_search", 
      "priority": 2,
      "collections": ["narrative_chunks"]
    },
    {
      "type": "text_search",
      "priority": 3,
      "keywords": ["example", "keywords"]
    }
  ],
  "explanation": "Brief explanation of this search strategy"
}

IMPORTANT: Return only the JSON with no code block formatting, additional text, or commentary.
"""
        
        # Query LLM for search plan
        llm_response = self._query_llm(prompt)  # Use default timeout from settings
        logger.info(f"LLM response for search plan: {llm_response[:500]}...")
        
        # Extract JSON from response
        import re
        import json
        logger.debug(f"Extracting JSON from LLM response of length {len(llm_response)}")
        
        # Try multiple patterns to extract JSON
        # First try to find JSON in code blocks (most reliable)
        json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', llm_response)
        
        # Second, try to find JSON between header tags (common in some models)
        if not json_match:
            json_match = re.search(r'<json>\s*(\{[\s\S]*?\})\s*</json>', llm_response)
            
        # Third, look for the first complete JSON object with a strategies field (most specific)
        if not json_match:
            all_json_objects = re.finditer(r'\{[\s\S]*?\}', llm_response)
            for match in all_json_objects:
                try:
                    obj = json.loads(match.group(0))
                    if "strategies" in obj:
                        json_match = match
                        break
                except:
                    continue
        
        # Finally, fall back to any JSON-like structure
        if not json_match:
            json_match = re.search(r'(\{[\s\S]*?\})', llm_response)
        
        if not json_match:
            # Log the LLM response for debugging
            logger.warning(f"Could not extract JSON from LLM response. First 100 chars: {llm_response[:100]}...")
            
            # If response is too short or empty, create a default search plan
            if len(llm_response.strip()) < 20:
                logger.warning("LLM returned very short response, constructing default search plan")
                
                # Construct a basic search plan based on the query type
                search_plan = {
                    "strategies": [
                        {"type": "structured_data", "priority": 1, "tables": self._get_relevant_tables(query_info)},
                        {"type": "vector_search", "priority": 2, "collections": ["narrative_chunks"]},
                        {"type": "text_search", "priority": 3, "keywords": self._extract_search_keywords(query_info)}
                    ],
                    "explanation": f"Default search strategy for query type '{query_info['type']}'"
                }
                
                return search_plan
            else:
                raise ValueError(f"Could not extract JSON from LLM response. Try simplifying the search plan format.")
            
        json_str = json_match.group(1)
        
        # Add extra error handling for JSON parsing
        try:
            # Try to load the JSON directly
            search_plan = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing error: {e}. Attempting to fix JSON before parsing...")
            
            try:
                # Sometimes the issue is with line breaks in the JSON - try removing them
                cleaned_json = json_str.replace('\n', ' ').replace('\r', '')
                search_plan = json.loads(cleaned_json)
                logger.info("Successfully parsed JSON after cleaning")
            except json.JSONDecodeError:
                try:
                    # If LLM outputs malformed JSON, we might need to extract the JSON more carefully
                    # Look for a complete, proper JSON object in the response
                    import re
                    better_json_match = re.search(r'(\{.*?"strategies".*?"explanation".*?\})', llm_response.replace('\n', ' '))
                    if better_json_match:
                        better_json = better_json_match.group(1)
                        search_plan = json.loads(better_json)
                        logger.info("Successfully parsed JSON with more careful extraction")
                    else:
                        # If we can't find a valid JSON, create a default one
                        logger.warning("Couldn't extract valid JSON. Creating default search plan.")
                        search_plan = {
                            "strategies": [
                                {"type": "structured_data", "priority": 1, "tables": self._get_relevant_tables(query_info)},
                                {"type": "vector_search", "priority": 2, "collections": ["narrative_chunks"]},
                                {"type": "text_search", "priority": 3, "keywords": self._extract_search_keywords(query_info)}
                            ],
                            "explanation": f"Default search strategy for '{query}'"
                        }
                except Exception as final_error:
                    logger.error(f"All JSON parsing attempts failed: {final_error}")
                    raise
        
        # Validate search plan structure
        if "strategies" not in search_plan or "explanation" not in search_plan:
            raise ValueError(f"Search plan missing required fields: {search_plan}")
        
        for strategy in search_plan["strategies"]:
            if "type" not in strategy or "priority" not in strategy:
                raise ValueError(f"Search strategy missing required fields: {strategy}")
            
            # Ensure each strategy has the right parameters
            if strategy["type"] == "structured_data" and "tables" not in strategy:
                strategy["tables"] = self._get_relevant_tables(query_info)
            elif strategy["type"] == "vector_search" and "collections" not in strategy:
                strategy["collections"] = ["narrative_chunks"]
            elif strategy["type"] == "text_search" and "keywords" not in strategy:
                strategy["keywords"] = self._extract_search_keywords(query_info)
        
        return search_plan
    
    def _parse_command(self, message: Message) -> Dict[str, Any]:
        """
        Parse a command from a user message.
        
        Args:
            message: User message
            
        Returns:
            Dictionary containing parsed command
        """
        # Extract text content from message
        if not message.content or len(message.content) == 0:
            return {}
        
        text = ""
        for content_item in message.content:
            if hasattr(content_item, "text") and content_item.text:
                text += content_item.text
        
        # Parse command (simple implementation)
        if "process" in text.lower() and "file" in text.lower():
            # Extract pattern if specified
            pattern = "*_copy_notime.md"  # Default
            pattern_match = re.search(r"pattern[:\s]+([^\s]+)", text)
            if pattern_match:
                pattern = pattern_match.group(1)
            
            return {"action": "process_files", "pattern": pattern}
        
        elif "query" in text.lower() or "search" in text.lower():
            # Extract query text
            query = text
            
    def _analyze_query(self, query: str, query_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze a query to understand the information need and query type.
        Uses pattern matching and LLM processing to extract entities and determine query type.
        
        Args:
            query: The query string
            query_type: Optional explicit query type
            
        Returns:
            Dict with query analysis
        """
        # Start with basic analysis
        query_info = {
            "raw_query": query,
            "type": query_type if query_type else "general",
            "entities": [],
            "keywords": [],
            "focus": "narrative"
        }
        
        # Extract entities using basic pattern matching
        # This is a simple implementation that could be enhanced with NER
        entity_patterns = [
            (r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', 'person'),  # Capitalized words as names
            (r'\b(Night City|The Wastes|Neon Bay|The Underbelly|The Combat Zone|Corporate Spires)\b', 'location'),
            (r'\b(Arasaka|NetWatch|Militech|Trauma Team|MaxTac|NightCorp)\b', 'organization')
        ]
        
        for pattern, entity_type in entity_patterns:
            matches = re.finditer(pattern, query)
            for match in matches:
                entity = match.group(1)
                if entity not in query_info["entities"]:
                    query_info["entities"].append({
                        "text": entity,
                        "type": entity_type
                    })
        
        # Extract keywords using simple techniques
        keywords = []
        
        # Remove common words and extract important terms
        common_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "about", "from"}
        words = re.findall(r'\b\w+\b', query.lower())
        for word in words:
            if len(word) > 3 and word not in common_words:
                keywords.append(word)
        
        query_info["keywords"] = keywords
        
        # If query type wasn't provided, try to determine it
        if not query_type:
            # Use pattern matching first
            type_patterns = {
                "character": r'\b(who|person|character|about|background)\b',
                "location": r'\b(where|location|place|setting)\b',
                "event": r'\b(what happened|when|event|incident|occurrence)\b',
                "relationship": r'\b(relationship|connection|feel about|interaction)\b',
                "theme": r'\b(theme|symbolism|represent|meaning|significance)\b'
            }
            
            for qtype, pattern in type_patterns.items():
                if re.search(pattern, query.lower()):
                    query_info["type"] = qtype
                    break
            
            # If pattern matching didn't work, use LLM
            if query_info["type"] == "general":
                try:
                    # Use a structured prompt that limits the LLM's response options
                    structured_prompt = """You are analyzing a narrative query. 
Determine the primary type of information being requested.

Query: "{query}"

Which ONE type best describes this query?
A) character - information about a specific character
B) location - information about a place
C) event - information about something that happened
D) theme - information about narrative themes or motifs
E) relationship - information about connections between characters
F) general - general information that doesn't fit the above categories

Answer with ONLY the single best category name (e.g., "character").
""".format(query=query)
                    
                    # Query LLM for classification
                    response = self._query_llm(structured_prompt, temperature=0.1, max_tokens=10)
                    
                    # Extract type from response (focusing on just the first word)
                    response = response.lower().strip().split()[0]
                    valid_types = {"character", "location", "event", "theme", "relationship", "general"}
                    
                    if response in valid_types:
                        query_info["type"] = response
                    
                    logger.info(f"LLM classified query as {query_info['type']}")
                    
                except Exception as e:
                    logger.warning(f"Failed to classify query with LLM: {e}")
                    
                # If we still have a general type, fallback to defaults
                if query_info["type"] == "general" and any(entity.get("type") == "person" for entity in query_info["entities"]):
                    query_info["type"] = "character"
            
        return query_info
    
    def _query_llm(self, prompt: str, temperature: float = None, max_tokens: int = None) -> str:
        """
        Query the local LLM with a prompt.
        
        Args:
            prompt: The prompt to send to the LLM
            temperature: Optional temperature parameter
            max_tokens: Optional max tokens parameter
            
        Returns:
            LLM response as string
        """
        # Get LLM settings from configuration
        llm_settings = MEMNON_SETTINGS.get("llm", {})
        api_base = llm_settings.get("api_base", "http://localhost:1234")
        
        # Use provided parameters or fall back to defaults
        if temperature is None:
            temperature = llm_settings.get("temperature", 0.2)
        
        if max_tokens is None:
            max_tokens = llm_settings.get("max_tokens", 1024)
        
        # Get timeout from settings (with default fallback)
        timeout = llm_settings.get("timeout", 300)
        
        logger.debug(f"Querying LLM with timeout {timeout}s")
        
        # Try query as completion first, then fallback to chat completion
        try:
            # Format as completions request
            payload = {
                "prompt": prompt,
                "model": self.model_id,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            # Set the request timeout (default 30s, but this can be too short for larger models)
            response = requests.post(
                f"{api_base}/completions",
                json=payload,
                timeout=timeout
            )
            
            if response.status_code == 200:
                response_json = response.json()
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    return response_json["choices"][0]["text"].strip()
                else:
                    logger.warning("Unexpected response format from LLM completions API")
            else:
                logger.warning(f"Completions API returned status code {response.status_code}, trying chat completions API")
                
            # Try chat completions API as fallback
            chat_payload = {
                "messages": [
                    {"role": "system", "content": llm_settings.get("system_prompt", "You are MEMNON, a narrative intelligence system that has perfect recall of story elements.")},
                    {"role": "user", "content": prompt}
                ],
                "model": self.model_id,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            response = requests.post(
                f"{api_base}/chat/completions",
                json=chat_payload,
                timeout=timeout
            )
            
            if response.status_code == 200:
                response_json = response.json()
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    return response_json["choices"][0]["message"]["content"].strip()
                else:
                    logger.warning("Unexpected response format from LLM chat completions API")
                    raise ValueError("Invalid response format from LLM API")
            else:
                error_msg = f"LLM API returned status code {response.status_code}"
                logger.error(error_msg)
                raise ValueError(error_msg)
                
        except requests.Timeout:
            error_msg = f"LLM request timed out after {timeout}s"
            logger.error(error_msg)
            raise TimeoutError(error_msg)
            
        except Exception as e:
            logger.error(f"Error querying LLM: {e}")
            raise
    
    def _determine_relevant_memory_tiers(self, query_info: Dict[str, Any]) -> List[str]:
        """
        Determine which memory tiers are most relevant to a query.
        
        Args:
            query_info: Analyzed query information
            
        Returns:
            List of memory tier names in priority order
        """
        query_type = query_info.get("type", "general")
        
        # Get memory tier mapping from query types
        if query_type in self.query_types:
            tier_info = self.query_types[query_type]
            primary_tier = tier_info.get("primary_tier")
            secondary_tier = tier_info.get("secondary_tier")
            
            tiers = []
            if primary_tier:
                tiers.append(primary_tier)
            if secondary_tier:
                tiers.append(secondary_tier)
                
            # Always include narrative tier if not already included
            if "narrative" not in tiers:
                tiers.append("narrative")
                
            return tiers
        
        # Default to all memory tiers
        return list(self.memory_tiers.keys())
    
    def _get_relevant_tables(self, query_info: Dict[str, Any]) -> List[str]:
        """
        Determine which database tables are most relevant to a query.
        
        Args:
            query_info: Analyzed query information
            
        Returns:
            List of table names
        """
        query_type = query_info.get("type", "general")
        entities = query_info.get("entities", [])
        
        # Start with an empty list
        tables = []
        
        # Add tables based on query type
        if query_type in self.query_types:
            tier_info = self.query_types[query_type]
            if "primary_tables" in tier_info:
                tables.extend(tier_info["primary_tables"])
        
        # Add tables based on entity types
        entity_table_mapping = {
            "person": "characters",
            "location": "places",
            "organization": "factions"
        }
        
        for entity in entities:
            entity_type = entity.get("type") if isinstance(entity, dict) else "person"
            if entity_type in entity_table_mapping and entity_table_mapping[entity_type] not in tables:
                tables.append(entity_table_mapping[entity_type])
        
        # Ensure we have at least some tables to query
        if not tables:
            if query_type == "character":
                tables = ["characters"]
            elif query_type == "location":
                tables = ["places"]
            elif query_type == "relationship":
                tables = ["characters", "character_relationships"]
            elif query_type == "event":
                tables = ["events"]
            else:
                tables = ["characters", "places", "events"]
        
        return tables
    
    def _extract_search_keywords(self, query_info: Dict[str, Any]) -> List[str]:
        """
        Extract keywords for text search from query info.
        
        Args:
            query_info: Analyzed query information
            
        Returns:
            List of keywords to search for
        """
        keywords = []
        
        # Add raw query
        raw_query = query_info.get("raw_query", "")
        if raw_query:
            keywords.append(raw_query)
        
        # Add entity names
        for entity in query_info.get("entities", []):
            if isinstance(entity, dict) and "text" in entity:
                keywords.append(entity["text"])
            elif isinstance(entity, str):
                keywords.append(entity)
        
        # Add extracted keywords
        keywords.extend(query_info.get("keywords", []))
        
        # Remove duplicates and empty strings
        unique_keywords = []
        for keyword in keywords:
            if keyword and keyword not in unique_keywords:
                unique_keywords.append(keyword)
        
        return unique_keywords
    
    def _query_structured_data(self, query_info: Dict[str, Any], tables: List[str], filters: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        Query structured database tables for exact data lookups.
        
        Args:
            query_info: Analyzed query information
            tables: Tables to query
            filters: Additional filters to apply
            limit: Maximum number of results
            
        Returns:
            List of matching structured data items
        """
        results = []
        
        try:
            session = self.Session()
            
            # Process each table
            for table in tables:
                table_results = []
                
                if table == "characters":
                    # Query the characters table
                    character_query = session.query(Character)
                    
                    # Apply filters for character name
                    name_filters = []
                    for entity in query_info.get("entities", []):
                        entity_text = entity.get("text", "") if isinstance(entity, dict) else entity
                        if entity_text:
                            name_filters.append(Character.name.ilike(f"%{entity_text}%"))
                            # Also check aliases column which is an array
                            name_filters.append(Character.aliases.any(entity_text))
                    
                    if name_filters:
                        character_query = character_query.filter(sa.or_(*name_filters))
                    
                    # Execute query and process results
                    characters = character_query.limit(limit).all()
                    for character in characters:
                        char_data = {
                            "id": str(character.id),
                            "name": character.name,
                            "content_type": "character",
                            "text": character.summary,
                            "metadata": {
                                "name": character.name,
                                "aliases": character.aliases,
                                "background": character.background[:100] + "..." if len(character.background) > 100 else character.background,
                                "personality": character.personality[:100] + "..." if len(character.personality) > 100 else character.personality,
                                "appearance": character.appearance[:100] + "..." if len(character.appearance) > 100 else character.appearance,
                                "current_location": character.current_location
                            },
                            "score": 0.95,  # High confidence score for exact matches
                            "source": "structured_data"
                        }
                        table_results.append(char_data)
                
                elif table == "places":
                    # Query the places table
                    place_query = session.query(Place)
                    
                    # Apply filters for place name
                    name_filters = []
                    for entity in query_info.get("entities", []):
                        entity_text = entity.get("text", "") if isinstance(entity, dict) else entity
                        if entity_text:
                            name_filters.append(Place.name.ilike(f"%{entity_text}%"))
                            name_filters.append(Place.location.ilike(f"%{entity_text}%"))
                    
                    if name_filters:
                        place_query = place_query.filter(sa.or_(*name_filters))
                    
                    # Execute query and process results
                    places = place_query.limit(limit).all()
                    for place in places:
                        place_data = {
                            "id": str(place.id),
                            "name": place.name,
                            "content_type": "place",
                            "text": place.summary,
                            "metadata": {
                                "name": place.name,
                                "type": place.type,
                                "location": place.location,
                                "inhabitants": place.inhabitants,
                                "current_status": place.current_status
                            },
                            "score": 0.9,  # High confidence score for exact matches
                            "source": "structured_data"
                        }
                        table_results.append(place_data)
                
                # Add more tables as needed...
                
                # Add results from this table
                results.extend(table_results)
            
            return results
            
        except Exception as e:
            logger.error(f"Error querying structured data: {e}")
            return []
        
        finally:
            session.close()
    
    def _query_text_search(self, query_info: Dict[str, Any], keywords: List[str], filters: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        Perform direct text search using SQL.
        
        Args:
            query_info: Analyzed query information
            keywords: Keywords to search for
            filters: Additional filters to apply
            limit: Maximum number of results
            
        Returns:
            List of matching text results
        """
        if not keywords:
            return []
        
        try:
            # Connect directly using psycopg2
            import psycopg2
            from urllib.parse import urlparse
            
            # Parse database URL
            parsed_url = urlparse(self.db_url)
            username = parsed_url.username
            password = parsed_url.password
            database = parsed_url.path[1:]  # Remove leading slash
            hostname = parsed_url.hostname
            port = parsed_url.port or 5432
            
            # Connect to the database
            conn = psycopg2.connect(
                host=hostname,
                port=port,
                user=username,
                password=password,
                database=database
            )
            
            results = []
            
            try:
                with conn.cursor() as cursor:
                    # Build filter conditions
                    filter_conditions = []
                    if filters:
                        if 'season' in filters:
                            filter_conditions.append(f"cm.season = {filters['season']}")
                        if 'episode' in filters:
                            filter_conditions.append(f"cm.episode = {filters['episode']}")
                        if 'world_layer' in filters:
                            filter_conditions.append(f"cm.world_layer = '{filters['world_layer']}'")
                    
                    filter_sql = " AND ".join(filter_conditions)
                    if filter_sql:
                        filter_sql = " AND " + filter_sql
                    
                    # Search for each keyword
                    for keyword in keywords:
                        # Escape single quotes in keyword
                        escaped_keyword = keyword.replace("'", "''")
                        
                        # SQL query with enhanced relevance scoring
                        sql = f"""
                        SELECT 
                            nc.id, 
                            nc.raw_text, 
                            cm.season, 
                            cm.episode, 
                            cm.scene as scene_number,
                            CASE 
                                WHEN nc.raw_text ~* '\\m{escaped_keyword}\\M' THEN 0.95  -- Exact word match
                                WHEN nc.raw_text ILIKE '%{escaped_keyword}%' THEN 0.8    -- Contains keyword
                                ELSE 0.5
                            END AS score
                        FROM 
                            narrative_chunks nc
                        JOIN 
                            chunk_metadata cm ON nc.id = cm.chunk_id
                        WHERE 
                            nc.raw_text ILIKE '%{escaped_keyword}%'
                            {filter_sql}
                        ORDER BY 
                            score DESC
                        LIMIT 
                            {limit}
                        """
                        
                        # Execute the query
                        cursor.execute(sql)
                        query_results = cursor.fetchall()
                        
                        # Process results
                        for result in query_results:
                            chunk_id, raw_text, season, episode, scene_number, score = result
                            chunk_id = str(chunk_id)
                            
                            # Calculate a confidence score based on keyword frequency
                            keyword_count = raw_text.lower().count(keyword.lower())
                            confidence = min(0.9, 0.5 + (keyword_count * 0.05))  # Boost score based on occurrences
                            
                            result_data = {
                                "id": chunk_id,
                                "chunk_id": chunk_id,
                                "text": raw_text,
                                "content_type": "narrative",
                                "metadata": {
                                    "season": season,
                                    "episode": episode,
                                    "scene_number": scene_number,
                                    "keyword_match": keyword,
                                    "keyword_count": keyword_count
                                },
                                "score": confidence,
                                "source": "text_search"
                            }
                            
                            # Check if this ID is already in results
                            existing_ids = [r["id"] for r in results]
                            if chunk_id not in existing_ids:
                                results.append(result_data)
                
                return results
                
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Error in text search: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _normalize_result_fields(self, results: List[Dict[str, Any]]) -> None:
        """
        Ensure all results have consistent field names by copying 'content' to 'text'
        when needed.
        
        Args:
            results: List of search results to normalize
            
        Returns:
            None (modifies results in place)
        """
        for result in results:
            # If result has 'content' but no 'text', copy content to text
            if "content" in result and "text" not in result:
                # Handle different content types
                if isinstance(result["content"], str):
                    result["text"] = result["content"]
                else:
                    # For structured data, convert content dict to string
                    result["text"] = str(result["content"])
                
                logger.debug(f"Normalized result: copied 'content' to 'text' field for result {result.get('id', 'unknown')}")
                
    def _validate_search_results(self, query: str, query_info: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
        """
        Simply record any relevant terms found in the results without judging their relevance.
        No filtering or scoring adjustments - let the LLM do all relevance assessment.
        
        Args:
            query: Original query string
            query_info: Analyzed query information
            results: Results to validate (modified in place)
        """
        # Just record all query terms as metadata without any scoring or filtering
        query_terms = query.lower().split()
        
        # Process each result to add minimal metadata about query terms
        for result in results:
            # No relevance assessment - just record query for reference
            result["relevance"] = {
                "query": query.lower(),
                "query_terms": query_terms
            }
            
            # No score adjustments or filtering of any kind
            # The LLM will see and judge all results based on content
    
    def query_memory(self, 
                   query: str, 
                   query_type: Optional[str] = None, 
                   memory_tiers: Optional[List[str]] = None, 
                   filters: Optional[Dict[str, Any]] = None, 
                   k: int = 10) -> Dict[str, Any]:
        """
        Unified memory query interface for retrieving narrative information.
        Uses LLM-directed search to dynamically select appropriate search strategies.
        
        Args:
            query: The narrative query
            query_type: Optional type of query (character, event, theme, relationship)
            memory_tiers: Optional specific memory tiers to query
            filters: Optional filters to apply (time, characters, locations, etc.)
            k: Number of results to return
            
        Returns:
            Dict containing query results and metadata
        """
        # Process query to understand information need
        query_info = self._analyze_query(query, query_type)
        search_start_time = time.time()
        
        # Generate search plan using LLM
        # No fallback - we want to force using the LLM for search planning
        search_plan = self._generate_search_plan(query, query_info)
        logger.info(f"Using LLM-generated search plan: {search_plan['explanation']}")
        
        # Determine which memory tiers to access if not specified
        if not memory_tiers:
            memory_tiers = self._determine_relevant_memory_tiers(query_info)
        
        # Execute each search strategy in priority order
        all_results = {}
        combined_results = []
        search_metadata = {
            "strategies_executed": [],
            "strategy_stats": {},
            "total_results": 0
        }
        
        # Sort strategies by priority
        strategies = sorted(search_plan["strategies"], key=lambda s: s["priority"])
        
        # Execute each strategy
        for strategy in strategies:
            strategy_type = strategy["type"]
            strategy_start = time.time()
            
            try:
                if strategy_type == "structured_data":
                    # Query structured database tables
                    tables = strategy.get("tables", [])
                    tier_results = self._query_structured_data(query_info, tables, filters, k)
                    logger.info(f"Structured data search found {len(tier_results)} results from {len(tables)} tables")
                    
                elif strategy_type == "vector_search":
                    # Query vector store
                    collections = strategy.get("collections", ["narrative_chunks"])
                    tier_results = self._query_vector_search(query, collections, filters, k)
                    logger.info(f"Vector search found {len(tier_results)} results")
                    
                elif strategy_type == "text_search":
                    # Direct text search using SQL
                    keywords = strategy.get("keywords", [query])
                    tier_results = self._query_text_search(query_info, keywords, filters, k)
                    logger.info(f"Text search found {len(tier_results)} results using {len(keywords)} keywords")
                    
                else:
                    logger.warning(f"Unknown search strategy type: {strategy_type}")
                    continue
                
                # Record strategy results and stats
                strategy_time = time.time() - strategy_start
                search_metadata["strategies_executed"].append(strategy_type)
                search_metadata["strategy_stats"][strategy_type] = {
                    "execution_time": strategy_time,
                    "results_count": len(tier_results)
                }
                
                # Store and extend results
                all_results[strategy_type] = tier_results
                combined_results.extend(tier_results)
                
                # Always run all search strategies, no matter how many results were found
                # Let the LLM determine what's relevant from all available data
                pass
                    
            except Exception as e:
                logger.error(f"Error executing search strategy {strategy_type}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # We'll use all results, but still deduplicate by ID to avoid showing duplicates
        seen_ids = set()
        synthesized_results = []
        
        for result in combined_results:
            # Normalize content/text fields
            self._normalize_result_fields([result])
            
            # Basic deduplication by ID only
            result_id = result.get("id") or result.get("chunk_id")
            if result_id and result_id not in seen_ids:
                seen_ids.add(result_id)
                synthesized_results.append(result)
        synthesized_results.sort(key=lambda x: x["score"], reverse=True)
        synthesized_results = synthesized_results[:k]  # Limit to requested number
        
        # Validate results for query term presence
        self._validate_search_results(query, query_info, synthesized_results)
        
        # Record overall search metadata
        search_metadata["total_time"] = time.time() - search_start_time
        search_metadata["total_results"] = len(synthesized_results)
        
        # Format final response
        response = {
            "query": query,
            "query_type": query_info["type"],
            "results": synthesized_results,
            "metadata": {
                "search_plan": search_plan["explanation"],
                "search_stats": search_metadata,
                "result_count": len(synthesized_results),
                "filters_applied": filters
            }
        }
        
        return response
    
    def _analyze_query(self, query: str, query_type: Optional[str]) -> Dict[str, Any]:
        """
        Analyze query to understand information need and type.
        Uses LLM to determine query type instead of algorithmic pattern matching.
        
        Args:
            query: The query string
            query_type: Optional explicit query type
            
        Returns:
            Dict containing query analysis information
        """
        # Initialize query info with basic data
        query_info = {
            "query_text": query,
            "type": query_type if query_type else "general",
            "entities": {
                "characters": [],
                "places": [],
                "events": [],
                "themes": []
            },
            "keywords": [],
            "time_references": []
        }
        
        # If query_type is provided, use it directly
        if query_type:
            # No further processing needed if already specified
            pass
        else:
            # Always use the LLM to determine query type - no algorithmic pattern matching
            llm_query_type = self._determine_query_type_with_llm(query)
            if llm_query_type:
                query_info["type"] = llm_query_type
            else:
                # Default to general if LLM fails
                query_info["type"] = "general"
        
        # Extract simple keywords for search purposes
        # Just use basic word splitting without complicated logic
        words = query.lower().split()
        # Remove very common words
        stopwords = {"a", "an", "the", "is", "are", "was", "were", "in", "on", "at", "to", "for", "with"}
        query_info["keywords"] = [word for word in words if word not in stopwords and len(word) > 2]
        
        # Add the entire query as a special term to ensure it's considered
        query_info["special_terms"] = [query.lower()]
        
        return query_info
    
    def _determine_query_type_with_llm(self, query: str) -> Optional[str]:
        """
        Use local LLM to determine the type of query.
        
        Args:
            query: The query string
            
        Returns:
            Detected query type or None if detection failed
        """
        # Get the prompt from settings if available
        query_type_prompt = MEMNON_SETTINGS.get("llm", {}).get(
            "analyze_query_prompt", 
            "Analyze the following narrative query and determine its primary type. Choose one of: character, location, event, theme, relationship, general."
        )
        
        prompt = f"""{query_type_prompt}

QUERY: "{query}"

Query types:
- 'character': Focused on a specific character, their actions, traits, development, etc.
- 'location': Focused on a place, setting, venue, etc.
- 'event': Focused on something that happened, a key moment, incident, etc.
- 'theme': Focused on ideas, motifs, recurring elements, or abstract concepts
- 'relationship': Focused on dynamics between two or more characters
- 'general': Does not fit clearly into any of the above categories

Output ONLY ONE WORD (the query type), with no explanation or additional text.
"""
        
        try:
            # Record start time
            start_time = time.time()
            
            # Call LM Studio API
            response = self._query_llm(prompt)
            
            # Calculate elapsed time
            elapsed = time.time() - start_time
            
            # Clean and validate the response
            response = response.strip().lower()
            valid_types = ["character", "location", "event", "theme", "relationship", "general"]
            
            if response in valid_types:
                logger.info(f"LLM classified query as type: {response} (determined in {elapsed:.2f}s)")
                return response
            else:
                logger.warning(f"LLM returned invalid query type: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error determining query type with LLM: {e}")
            return None
    
    def _query_llm(self, prompt: str) -> str:
        """
        Query the local LLM with a prompt.
        
        Args:
            prompt: The prompt to send to the LLM
            
        Returns:
            LLM response as a string
        """
        # Get API endpoint from settings or use default
        api_base = MEMNON_SETTINGS.get("llm", {}).get("api_base", "http://localhost:1234")
        completions_endpoint = f"{api_base}/v1/completions"
        chat_endpoint = f"{api_base}/v1/chat/completions"
        
        # Get parameters from settings or use defaults
        temperature = MEMNON_SETTINGS.get("llm", {}).get("temperature", 0.2)
        top_p = MEMNON_SETTINGS.get("llm", {}).get("top_p", 0.9)
        max_tokens = MEMNON_SETTINGS.get("llm", {}).get("max_tokens", 1024)
        timeout = MEMNON_SETTINGS.get("llm", {}).get("timeout", 300)  # Increased to 5 minutes
        
        try:
            # Use LM Studio API completions endpoint first
            payload = {
                "model": self.model_id,
                "prompt": prompt,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
                "stream": False
            }
            
            logger.info(f"Sending request to LLM ({self.model_id}) for query analysis (timeout: {timeout}s)")
            logger.debug(f"API endpoint: {completions_endpoint}")
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(completions_endpoint, json=payload, headers=headers, timeout=timeout)
            
            if response.status_code == 200:
                response_data = response.json()
                
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    if "text" in response_data["choices"][0]:
                        return response_data["choices"][0]["text"]
                
                # Try alternate response format
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    if "message" in response_data["choices"][0]:
                        return response_data["choices"][0]["message"]["content"]
                
                logger.warning(f"Unexpected LLM response format: {response_data}")
                raise ValueError("Unexpected LLM response format")
            
            # Try fallback to chat completions if normal completions fail
            if response.status_code != 200:
                logger.warning(f"Completions endpoint failed with status {response.status_code}, trying chat completions")
                
                # Get system prompt from settings
                system_prompt = MEMNON_SETTINGS.get("llm", {}).get(
                    "system_prompt", "You are a narrative analysis assistant."
                )
                
                chat_payload = {
                    "model": self.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": temperature,
                    "top_p": top_p,
                    "max_tokens": max_tokens
                }
                
                logger.debug(f"Trying chat endpoint: {chat_endpoint}")
                response = requests.post(chat_endpoint, json=chat_payload, headers=headers, timeout=timeout)
                
                if response.status_code == 200:
                    response_data = response.json()
                    
                    if "choices" in response_data and len(response_data["choices"]) > 0:
                        if "message" in response_data["choices"][0]:
                            return response_data["choices"][0]["message"]["content"]
                
                logger.warning(f"Chat completions endpoint also failed: {response.status_code}, {response.text}")
        
        except Exception as e:
            logger.error(f"Error in LLM query: {e}")
            logger.error(f"Error details: {str(e)}")
        
        # Return a default response if all attempts fail
        logger.warning("All LLM query attempts failed, returning empty response")
        return ""
    
    def _contains_character_reference(self, text: str) -> bool:
        """Check if the text contains references to characters."""
        # Get all character names from the database
        session = self.Session()
        try:
            characters = session.query(Character.name).all()
            character_names = [c[0].lower() for c in characters]
            
            # Check if any character name is in the text
            text_lower = text.lower()
            for name in character_names:
                if name in text_lower:
                    return True
            
            # Check for common character-related terms
            character_terms = ["character", "person", "who", "she", "he", "they"]
            for term in character_terms:
                if f" {term} " in f" {text_lower} ":
                    return True
                    
            return False
            
        except Exception as e:
            logger.error(f"Error checking for character references: {e}")
            # Fall back to simple pattern matching
            patterns = ["who", "character", "person", "she", "he", "they"]
            return any(pattern in text.lower() for pattern in patterns)
            
        finally:
            session.close()
    
    def _contains_location_reference(self, text: str) -> bool:
        """Check if the text contains references to locations."""
        # Get all place names from the database
        session = self.Session()
        try:
            places = session.query(Place.name).all()
            place_names = [p[0].lower() for p in places]
            
            # Check if any place name is in the text
            text_lower = text.lower()
            for name in place_names:
                if name in text_lower:
                    return True
            
            # Check for common location-related terms
            location_terms = ["where", "place", "location", "building", "room", "area"]
            for term in location_terms:
                if f" {term} " in f" {text_lower} ":
                    return True
                    
            return False
            
        except Exception as e:
            logger.error(f"Error checking for location references: {e}")
            # Fall back to simple pattern matching
            patterns = ["where", "place", "location", "area"]
            return any(pattern in text.lower() for pattern in patterns)
            
        finally:
            session.close()
    
    def _contains_event_reference(self, text: str) -> bool:
        """Check if the text contains references to events."""
        # Check for common event-related terms
        event_terms = ["event", "happen", "happened", "incident", "occurred", "when", "scene"]
        text_lower = f" {text.lower()} "
        
        for term in event_terms:
            if f" {term} " in text_lower:
                return True
                
        return False
    
    def _contains_theme_reference(self, text: str) -> bool:
        """Check if the text contains references to themes."""
        # Check for common theme-related terms
        theme_terms = ["theme", "idea", "concept", "motif", "symbolism", "meaning", "represent"]
        text_lower = f" {text.lower()} "
        
        for term in theme_terms:
            if f" {term} " in text_lower:
                return True
                
        return False
    
    def _contains_relationship_reference(self, text: str) -> bool:
        """Check if the text contains references to relationships."""
        # Check for common relationship-related terms
        relationship_terms = ["relationship", "between", "connect", "friend", "enemy", "ally", 
                              "partner", "together", "interaction", "relate"]
        text_lower = f" {text.lower()} "
        
        for term in relationship_terms:
            if f" {term} " in text_lower:
                return True
                
        return False
    
    def _enrich_query_info(self, query_info: Dict[str, Any], query: str) -> Dict[str, Any]:
        """
        Extract entities and enrich query information.
        
        Args:
            query_info: Current query information
            query: Original query string
            
        Returns:
            Enriched query information
        """
        # Extract character references
        if query_info["type"] in ["character", "relationship"]:
            session = self.Session()
            try:
                characters = session.query(Character.name, Character.aliases).all()
                
                for name, aliases in characters:
                    if name.lower() in query.lower():
                        if name not in query_info["entities"]["characters"]:
                            query_info["entities"]["characters"].append(name)
                    
                    if aliases:
                        for alias in aliases:
                            if alias.lower() in query.lower():
                                if name not in query_info["entities"]["characters"]:
                                    query_info["entities"]["characters"].append(name)
            except Exception as e:
                logger.error(f"Error extracting character references: {e}")
            finally:
                session.close()
        
        # Extract place references for location queries
        if query_info["type"] == "location":
            session = self.Session()
            try:
                places = session.query(Place.name).all()
                place_names = [p[0] for p in places]
                
                for name in place_names:
                    if name.lower() in query.lower():
                        if name not in query_info["entities"]["places"]:
                            query_info["entities"]["places"].append(name)
            except Exception as e:
                logger.error(f"Error extracting place references: {e}")
            finally:
                session.close()
        
        # Extract time references (season/episode)
        season_pattern = re.compile(r"season\s*(\d+)", re.IGNORECASE)
        episode_pattern = re.compile(r"episode\s*(\d+)", re.IGNORECASE)
        
        season_match = season_pattern.search(query)
        if season_match:
            query_info["time_references"].append({"type": "season", "value": int(season_match.group(1))})
        
        episode_match = episode_pattern.search(query)
        if episode_match:
            query_info["time_references"].append({"type": "episode", "value": int(episode_match.group(1))})
        
        # Extract keywords using basic tokenization
        # Remove stop words and keep meaningful terms
        stop_words = ["the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "about", "is", "are"]
        tokens = [token.strip().lower() for token in re.findall(r'\b\w+\b', query)]
        keywords = [token for token in tokens if token not in stop_words and len(token) > 2]
        
        query_info["keywords"] = list(set(keywords))  # Deduplicate
        
        return query_info
    
    def _determine_relevant_memory_tiers(self, query_info: Dict[str, Any]) -> List[str]:
        """
        Determine which memory tiers are most relevant for a query.
        
        Args:
            query_info: Query analysis information
            
        Returns:
            List of relevant tier names
        """
        # Get query type information
        query_type = query_info["type"]
        
        # If query type is in our registry, use its tier info
        if query_type in self.query_types:
            type_info = self.query_types[query_type]
            tiers = [type_info["primary_tier"]]
            
            # Add secondary tier if present
            if "secondary_tier" in type_info:
                tiers.append(type_info["secondary_tier"])
                
            return tiers
        
        # Default tiers by query type
        type_to_tiers = {
            "character": ["entity", "narrative"],
            "location": ["entity", "narrative"],
            "event": ["narrative", "strategic"],
            "theme": ["narrative"],
            "relationship": ["entity", "narrative"],
            "general": ["narrative", "entity", "strategic"]
        }
        
        # Return mapped tiers or all tiers as fallback
        return type_to_tiers.get(query_type, list(self.memory_tiers.keys()))
    
    def _query_database(self, 
                      query_info: Dict[str, Any], 
                      tables: List[str],
                      filters: Optional[Dict[str, Any]],
                      k: int) -> List[Dict[str, Any]]:
        """
        Query structured database for narrative information.
        
        Args:
            query_info: Query analysis information
            tables: List of tables to query
            filters: Optional filters to apply
            k: Number of results to return
            
        Returns:
            List of database query results
        """
        session = self.Session()
        try:
            results = []
            
            # Process each table
            for table_name in tables:
                table_results = []
                
                # Handle character queries
                if table_name == "characters" and ("character" in query_info["type"] or query_info["entities"]["characters"]):
                    char_query = session.query(Character)
                    
                    # Apply character name filter
                    if query_info["entities"]["characters"]:
                        char_names = query_info["entities"]["characters"]
                        char_query = char_query.filter(Character.name.in_(char_names))
                    
                    # Apply any additional filters
                    if filters and "character_name" in filters:
                        char_query = char_query.filter(Character.name == filters["character_name"])
                    
                    # Get results
                    char_results = char_query.limit(k).all()
                    
                    # Transform to dict format
                    for char in char_results:
                        table_results.append({
                            "id": str(char.id),
                            "type": "character",
                            "name": char.name,
                            "content": {
                                "name": char.name,
                                "aliases": char.aliases,
                                "summary": char.summary,
                                "appearance": char.appearance,
                                "personality": char.personality,
                                "background": char.background,
                                "current_location": char.current_location
                            },
                            "score": 1.0,  # Direct DB matches get full score
                            "metadata": {
                                "source": "characters"
                            }
                        })
                
                # Handle place queries
                elif table_name == "places" and ("location" in query_info["type"] or query_info["entities"]["places"]):
                    place_query = session.query(Place)
                    
                    # Apply place name filter
                    if query_info["entities"]["places"]:
                        place_names = query_info["entities"]["places"]
                        place_query = place_query.filter(Place.name.in_(place_names))
                    
                    # Apply any additional filters
                    if filters and "place_name" in filters:
                        place_query = place_query.filter(Place.name == filters["place_name"])
                    
                    # Get results
                    place_results = place_query.limit(k).all()
                    
                    # Transform to dict format
                    for place in place_results:
                        table_results.append({
                            "id": str(place.id),
                            "type": "place",
                            "name": place.name,
                            "content": {
                                "name": place.name,
                                "type": place.type,
                                "location": place.location,
                                "summary": place.summary,
                                "inhabitants": place.inhabitants,
                                "historical_significance": place.historical_significance
                            },
                            "score": 1.0,  # Direct DB matches get full score
                            "metadata": {
                                "source": "places"
                            }
                        })
                
                # Handle other tables - add more specialized handlers as needed
                # This is where you would implement handlers for events, factions, etc.
                
                # Add results from this table
                results.extend(table_results)
            
            # Sort by score and limit results
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:k]
            
        except Exception as e:
            logger.error(f"Error querying database: {e}")
            return []
            
        finally:
            session.close()
    
    def _query_vector_store(self, 
                          query_info: Dict[str, Any], 
                          collections: List[str],
                          filters: Optional[Dict[str, Any]],
                          k: int) -> List[Dict[str, Any]]:
        """
        Query vector store for semantically relevant information.
        
        Args:
            query_info: Query analysis information
            collections: Collections to search
            filters: Optional filters
            k: Number of results to return
            
        Returns:
            List of vector search results
        """
        # Extract the raw query text
        query_text = query_info.get("raw_query", "")
        
        # Transform filters from query_info to format expected by _query_vector_search
        vector_filters = {}
        
        # Add season/episode filters from time references
        if "time_references" in query_info:
            for time_ref in query_info["time_references"]:
                if isinstance(time_ref, dict):
                    if time_ref.get("type") == "season":
                        vector_filters["season"] = time_ref.get("value")
                    elif time_ref.get("type") == "episode":
                        vector_filters["episode"] = time_ref.get("value")
        
        # Add any explicit filters passed in
        if filters:
            vector_filters.update(filters)
        
        # Perform vector search
        vector_results = self._query_vector_search(query_text, collections, vector_filters, k)
        
        # Transform to standard format
        transformed_results = []
        for result in vector_results:
            transformed_results.append({
                "id": result["chunk_id"],
                "type": "narrative_chunk",
                "content": result["text"],
                "score": result["score"],
                "metadata": {
                    "season": result["metadata"]["season"],
                    "episode": result["metadata"]["episode"],
                    "scene_number": result["metadata"]["scene_number"],
                    "source": "narrative_chunks"
                }
            })
        
        return transformed_results
    
    def _generate_search_plan(self, query: str, query_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a dynamic search plan for a given query using LLM reasoning.
        
        Args:
            query: The original query string
            query_info: Analyzed query information
            
        Returns:
            Search plan with strategies in priority order
        """
        import json
        import json
        
        # Prepare information about available data sources
        structured_tables = {
            "characters": "detailed information about characters including name, background, appearance, etc.",
            "places": "locations and settings with descriptions",
            "events": "significant narrative events",
            "character_relationships": "information about relationships between characters",
            "threats": "potential threats and dangers in the narrative",
            "factions": "groups and organizations"
        }
        
        vector_collections = {
            "narrative_chunks": "raw text passages from the narrative with embedded semantic meaning"
        }
        
        # Construct the prompt differently to avoid f-string issues
        prompt_parts = [
            "You are MEMNON, a sophisticated narrative intelligence system.",
            "Given a user query, your task is to create the optimal search strategy across multiple data sources.",
            "",
            f'QUERY: "{query}"',
            f'QUERY TYPE: {query_info["type"]}',
            f'ENTITIES MENTIONED: {json.dumps(query_info["entities"])}',
            f'KEYWORDS: {json.dumps(query_info["keywords"])}',
            '',
            'AVAILABLE DATA SOURCES:',
            '1. Structured tables (exact data lookup):',
            json.dumps(structured_tables, indent=2),
            '',
            '2. Vector database (semantic search by meaning):',
            json.dumps(vector_collections, indent=2),
            '',
            '3. Text search (direct keyword matching):',
            'Can perform fuzzy or exact matches on raw text.',
            '',
            'Consider the following when creating your search plan:',
            '- Which data source is most likely to contain the information needed?',
            '- What order of operations would be most efficient?',
            '- Could simpler searches be tried before more complex ones?',
            '- How would you combine results from different sources?',
            '',
            'YOUR RESPONSE MUST BE A SINGLE JSON OBJECT with this structure:',
            '',
            '{"strategies": [{"type": "structured_data", "priority": 1, "tables": ["characters", "places"]}, {"type": "vector_search", "priority": 2, "collections": ["narrative_chunks"]}, {"type": "text_search", "priority": 3, "keywords": ["example", "keywords"]}], "explanation": "Brief explanation of this search strategy"}',
            '',
            'IMPORTANT: Return only the JSON with no code block formatting, additional text, or commentary.'
        ]
        
        # Join the prompt parts into a single string
        prompt = "\n".join(prompt_parts)
        
        # Query LLM for search plan
        llm_response = self._query_llm(prompt)  # Use default timeout from settings
        logger.info(f"LLM response for search plan: {llm_response[:500]}...")
        
        # Extract JSON from response
        import re
        import json
        logger.debug(f"Extracting JSON from LLM response of length {len(llm_response)}")
        
        # Try multiple patterns to extract JSON
        # First try to find JSON in code blocks (most reliable)
        json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', llm_response)
        
        # Second, try to find JSON between header tags (common in some models)
        if not json_match:
            json_match = re.search(r'<json>\s*(\{[\s\S]*?\})\s*</json>', llm_response)
            
        # Third, look for the first complete JSON object with a strategies field (most specific)
        if not json_match:
            all_json_objects = re.finditer(r'\{[\s\S]*?\}', llm_response)
            for match in all_json_objects:
                try:
                    obj = json.loads(match.group(0))
                    if "strategies" in obj:
                        json_match = match
                        break
                except:
                    continue
        
        # Finally, fall back to any JSON-like structure
        if not json_match:
            json_match = re.search(r'(\{[\s\S]*?\})', llm_response)
        
        if not json_match:
            # Log the LLM response for debugging
            logger.warning(f"Could not extract JSON from LLM response. First 100 chars: {llm_response[:100]}...")
            
            # If response is too short or empty, create a default search plan
            if len(llm_response.strip()) < 20:
                logger.warning("LLM returned very short response, constructing default search plan")
                
                # Construct a basic search plan based on the query type
                search_plan = {
                    "strategies": [
                        {"type": "structured_data", "priority": 1, "tables": self._get_relevant_tables(query_info)},
                        {"type": "vector_search", "priority": 2, "collections": ["narrative_chunks"]},
                        {"type": "text_search", "priority": 3, "keywords": self._extract_search_keywords(query_info)}
                    ],
                    "explanation": f"Default search strategy for query type '{query_info['type']}'"
                }
                
                return search_plan
            else:
                raise ValueError(f"Could not extract JSON from LLM response. Try simplifying the search plan format.")
            
        json_str = json_match.group(1)
        
        # Add extra error handling for JSON parsing
        try:
            # Try to load the JSON directly
            search_plan = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing error: {e}. Attempting to fix JSON before parsing...")
            
            try:
                # Sometimes the issue is with line breaks in the JSON - try removing them
                cleaned_json = json_str.replace('\n', ' ').replace('\r', '')
                search_plan = json.loads(cleaned_json)
                logger.info("Successfully parsed JSON after cleaning")
            except json.JSONDecodeError:
                try:
                    # If LLM outputs malformed JSON, we might need to extract the JSON more carefully
                    # Look for a complete, proper JSON object in the response
                    import re
                    better_json_match = re.search(r'(\{.*?"strategies".*?"explanation".*?\})', llm_response.replace('\n', ' '))
                    if better_json_match:
                        better_json = better_json_match.group(1)
                        search_plan = json.loads(better_json)
                        logger.info("Successfully parsed JSON with more careful extraction")
                    else:
                        # If we can't find a valid JSON, create a default one
                        logger.warning("Couldn't extract valid JSON. Creating default search plan.")
                        search_plan = {
                            "strategies": [
                                {"type": "structured_data", "priority": 1, "tables": self._get_relevant_tables(query_info)},
                                {"type": "vector_search", "priority": 2, "collections": ["narrative_chunks"]},
                                {"type": "text_search", "priority": 3, "keywords": self._extract_search_keywords(query_info)}
                            ],
                            "explanation": f"Default search strategy for '{query}'"
                        }
                except Exception as final_error:
                    logger.error(f"All JSON parsing attempts failed: {final_error}")
                    raise
        
        # Validate search plan structure
        if "strategies" not in search_plan or "explanation" not in search_plan:
            raise ValueError(f"Search plan missing required fields: {search_plan}")
        
        for strategy in search_plan["strategies"]:
            if "type" not in strategy or "priority" not in strategy:
                raise ValueError(f"Search strategy missing required fields: {strategy}")
            
            # Ensure each strategy has the right parameters
            if strategy["type"] == "structured_data" and "tables" not in strategy:
                strategy["tables"] = self._get_relevant_tables(query_info)
            elif strategy["type"] == "vector_search" and "collections" not in strategy:
                strategy["collections"] = ["narrative_chunks"]
            elif strategy["type"] == "text_search" and "keywords" not in strategy:
                strategy["keywords"] = self._extract_search_keywords(query_info)
        
        return search_plan
    
    def _get_relevant_tables(self, query_info: Dict[str, Any]) -> List[str]:
        """
        Determine which database tables are most relevant to this query.
        
        Args:
            query_info: Analyzed query information
            
        Returns:
            List of relevant table names
        """
        query_type = query_info["type"]
        tables = []
        
        # Map query types to relevant tables
        if query_type == "character":
            tables = ["characters", "character_relationships"]
        elif query_type == "location":
            tables = ["places"]
        elif query_type == "event":
            tables = ["events", "threats"]
        elif query_type == "relationship":
            tables = ["character_relationships", "characters"]
        elif query_type == "theme":
            tables = []  # Themes are best searched in narratives, not structured data
        else:  # general or unknown
            tables = ["characters", "places", "events"]
        
        # Check if we have any explicit entities to lookup
        if query_info["entities"]["characters"]:
            if "characters" not in tables:
                tables.append("characters")
        if query_info["entities"]["places"]:
            if "places" not in tables:
                tables.append("places")
        
        return tables
    
    def _get_relevant_collections(self, query_info: Dict[str, Any]) -> List[str]:
        """
        Determine which vector collections are most relevant to this query.
        
        Args:
            query_info: Analyzed query information
            
        Returns:
            List of relevant collection names
        """
        # Currently we only have one collection, but this will be useful
        # when more specialized collections are added
        return ["narrative_chunks"]
    
    def _extract_search_keywords(self, query_info: Dict[str, Any]) -> List[str]:
        """
        Extract keywords for text search from query info.
        
        Args:
            query_info: Analyzed query information
            
        Returns:
            List of keywords for text search
        """
        keywords = []
        
        # Add entity names
        for char in query_info["entities"]["characters"]:
            keywords.append(char)
        for place in query_info["entities"]["places"]:
            keywords.append(place)
        
        # Add query keywords if we have them
        if query_info["keywords"]:
            keywords.extend(query_info["keywords"])
        
        # If no keywords extracted, use full query
        if not keywords:
            keywords.append(query_info["query_text"])
        
        return keywords
    
    def _query_structured_data(self, query_info: Dict[str, Any], tables: List[str], 
                             filters: Optional[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
        """
        Query structured database tables for exact data lookup.
        
        Args:
            query_info: Query analysis information
            tables: List of tables to query
            filters: Optional filters to apply
            k: Number of results to return
            
        Returns:
            List of database query results
        """
        session = self.Session()
        results = []
        
        try:
            # Process each table
            for table_name in tables:
                if table_name == "characters" and query_info["entities"]["characters"]:
                    # Query character table
                    char_query = session.query(Character)
                    
                    # Check if we are looking for a specific character
                    if query_info["entities"]["characters"]:
                        char_names = query_info["entities"]["characters"]
                        char_query = char_query.filter(Character.name.in_(char_names))
                    
                    # Apply any additional filters
                    if filters and "character_name" in filters:
                        char_query = char_query.filter(Character.name == filters["character_name"])
                    
                    # Get results
                    char_results = char_query.limit(k).all()
                    
                    # Transform to dict format
                    for char in char_results:
                        results.append({
                            "id": str(char.id),
                            "type": "character",
                            "name": char.name,
                            "content": {
                                "name": char.name,
                                "aliases": char.aliases,
                                "summary": char.summary,
                                "appearance": char.appearance,
                                "personality": char.personality,
                                "background": char.background,
                                "current_location": char.current_location
                            },
                            "score": 1.2,  # Give structured data a boost
                            "metadata": {
                                "source": "characters"
                            }
                        })
                
                elif table_name == "places" and (query_info["type"] == "location" or query_info["entities"]["places"]):
                    # Query places table
                    place_query = session.query(Place)
                    
                    # Check if we're looking for a specific place
                    if query_info["entities"]["places"]:
                        place_names = query_info["entities"]["places"]
                        place_query = place_query.filter(Place.name.in_(place_names))
                    
                    # Apply any additional filters
                    if filters and "place_name" in filters:
                        place_query = place_query.filter(Place.name == filters["place_name"])
                    
                    # Get results
                    place_results = place_query.limit(k).all()
                    
                    # Transform to dict format
                    for place in place_results:
                        results.append({
                            "id": str(place.id),
                            "type": "place",
                            "name": place.name,
                            "content": {
                                "name": place.name,
                                "type": place.type,
                                "location": place.location,
                                "summary": place.summary,
                                "inhabitants": place.inhabitants,
                                "historical_significance": place.historical_significance
                            },
                            "score": 1.2,  # Give structured data a boost
                            "metadata": {
                                "source": "places"
                            }
                        })
                
                # Add additional table handlers here as needed
            
            return results
            
        except Exception as e:
            logger.error(f"Error querying structured data: {e}")
            return []
            
        finally:
            session.close()
    
    def _query_text_search(self, query_info: Dict[str, Any], keywords: List[str], 
                         filters: Optional[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
        """
        Perform direct text search using SQL LIKE.
        
        Args:
            query_info: Query analysis information
            keywords: Terms to search for
            filters: Optional filters to apply
            k: Number of results to return
            
        Returns:
            List of text search results
        """
        session = self.Session()
        results = []
        
        try:
            # Build SQL query using text expressions
            for keyword in keywords:
                # Skip very short keywords
                if len(keyword) < 3:
                    continue
                    
                # Create pattern with SQL LIKE
                pattern = f"%{keyword}%"
                
                # Query for chunks containing this keyword
                query = session.query(
                    NarrativeChunk.id,
                    NarrativeChunk.raw_text,
                    ChunkMetadata.season,
                    ChunkMetadata.episode,
                    ChunkMetadata.scene.label('scene_number')
                ).join(
                    ChunkMetadata, NarrativeChunk.id == ChunkMetadata.chunk_id, isouter=True
                ).filter(
                    NarrativeChunk.raw_text.ilike(pattern)
                )
                
                # Apply filters if provided
                if filters:
                    if 'season' in filters:
                        query = query.filter(ChunkMetadata.season == filters['season'])
                    if 'episode' in filters:
                        query = query.filter(ChunkMetadata.episode == filters['episode'])
                    if 'world_layer' in filters:
                        query = query.filter(ChunkMetadata.world_layer == filters['world_layer'])
                
                # Limit results and execute
                chunks = query.limit(k).all()
                
                # Calculate naive relevance score based on number of occurrences
                for chunk in chunks:
                    chunk_id = chunk.id
                    chunk_text = chunk.raw_text
                    
                    # Count occurrences
                    occurrence_count = chunk_text.lower().count(keyword.lower())
                    
                    # Basic score based on occurrences
                    base_score = min(0.9 + (occurrence_count * 0.02), 0.99)
                    
                    # Get or create result entry
                    existing = next((r for r in results if r["id"] == str(chunk_id)), None)
                    if existing:
                        # Update score if this keyword has higher relevance
                        if base_score > existing["score"]:
                            existing["score"] = base_score
                            existing["matched_term"] = keyword
                    else:
                        # Create new result
                        results.append({
                            "id": str(chunk_id),
                            "type": "narrative_chunk",
                            "content": chunk_text,
                            "score": base_score,
                            "matched_term": keyword,
                            "metadata": {
                                "season": chunk.season,
                                "episode": chunk.episode,
                                "scene_number": chunk.scene_number,
                                "search_method": "text_search"
                            }
                        })
            
            # Sort by score and limit results
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:k]
            
        except Exception as e:
            logger.error(f"Error in text search: {e}")
            return []
            
        finally:
            session.close()
    
    def _validate_search_results(self, query: str, query_info: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
        """
        Validate search results to ensure they actually contain relevant information.
        Also adds relevance indicators to results.
        
        Args:
            query: Original query string
            query_info: Analyzed query information
            results: Search results to validate
            
        Returns:
            None (modifies results list in place)
        """
        # Create a set of terms to look for in results
        validation_terms = set()
        query_lower = query.lower()
        
        # Add entity names
        for char in query_info["entities"]["characters"]:
            validation_terms.add(char.lower())
        for place in query_info["entities"]["places"]:
            validation_terms.add(place.lower())
        
        # Add additional terms from keywords
        for keyword in query_info["keywords"]:
            if len(keyword) >= 4:  # Only use meaningful keywords
                validation_terms.add(keyword.lower())
        
        # Add any explicit search terms from the query
        special_terms = set()
        for term in query_lower.split():
            if term.startswith('"') and term.endswith('"'):
                clean_term = term.strip('"\'').lower()
                if clean_term:
                    special_terms.add(clean_term)
                    validation_terms.add(clean_term)
        
        # Validate each result and add relevance information
        for result in results:
            # Get content to check
            if "text" in result:
                content = result.get("text", "").lower()
            elif "content" in result:
                if isinstance(result["content"], str):
                    content = result["content"].lower()
                else:
                    # For structured data, convert content dict to string
                    content = str(result.get("content", {})).lower()
            else:
                # If no content or text field, use the whole result as a string
                content = str(result).lower()
            
            # Check for term presence
            result["relevant_terms"] = []
            for term in validation_terms:
                if term in content:
                    result["relevant_terms"].append(term)
            
            # Check for special terms (exact match requirements)
            special_matched = len(special_terms) == 0  # True if no special terms to match
            for term in special_terms:
                if term in content:
                    special_matched = True
                    break
            
            # Always mark as relevant for LLM evaluation
            # This ensures the LLM sees all results and can do its own relevance evaluation
            result["has_relevant_terms"] = True
            result["matches_special_terms"] = True
            
            # Store the actual match info for debugging but don't use it for filtering
            result["debug_has_exact_term_matches"] = len(result["relevant_terms"]) > 0
    
    def _cross_reference_results(self, 
                              all_results: Dict[str, List[Dict[str, Any]]], 
                              query_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Cross-reference and synthesize results from multiple sources.
        
        Args:
            all_results: Results from each memory tier
            query_info: Query analysis information
            
        Returns:
            Synthesized list of results
        """
        # Flatten and combine all results
        combined_results = []
        for tier, results in all_results.items():
            for result in results:
                # Add tier information to result
                result["memory_tier"] = tier
                combined_results.append(result)
        
        # Find connections between results
        for i, result1 in enumerate(combined_results):
            # Skip if not narrative chunk
            if result1["type"] != "narrative_chunk":
                continue
                
            # Find entities mentioned in this chunk
            chunk_text = result1["content"].lower()
            
            # Look for character mentions
            for j, result2 in enumerate(combined_results):
                if result2["type"] == "character":
                    char_name = result2["name"].lower()
                    if char_name in chunk_text:
                        # Character is mentioned in chunk
                        if "referenced_entities" not in result1:
                            result1["referenced_entities"] = []
                        result1["referenced_entities"].append({
                            "type": "character",
                            "id": result2["id"],
                            "name": result2["name"]
                        })
                        
                        # Also update character result to reference this chunk
                        if "referencing_chunks" not in result2:
                            result2["referencing_chunks"] = []
                        result2["referencing_chunks"].append({
                            "id": result1["id"],
                            "score": result1["score"]
                        })
            
            # Look for place mentions
            for j, result2 in enumerate(combined_results):
                if result2["type"] == "place":
                    place_name = result2["name"].lower()
                    if place_name in chunk_text:
                        # Place is mentioned in chunk
                        if "referenced_entities" not in result1:
                            result1["referenced_entities"] = []
                        result1["referenced_entities"].append({
                            "type": "place",
                            "id": result2["id"],
                            "name": result2["name"]
                        })
                        
                        # Also update place result to reference this chunk
                        if "referencing_chunks" not in result2:
                            result2["referencing_chunks"] = []
                        result2["referencing_chunks"].append({
                            "id": result1["id"],
                            "score": result1["score"]
                        })
        
        # Apply boosts based on query type
        query_type = query_info["type"]
        for result in combined_results:
            # Boost directly matching entity types
            if query_type == "character" and result["type"] == "character":
                result["score"] *= self.retrieval_settings["entity_boost_factor"]
            elif query_type == "location" and result["type"] == "place":
                result["score"] *= self.retrieval_settings["entity_boost_factor"]
            
            # Boost narrative chunks that reference relevant entities
            if query_type in ["character", "relationship"] and result["type"] == "narrative_chunk":
                if "referenced_entities" in result:
                    for entity in result["referenced_entities"]:
                        if entity["type"] == "character" and entity["name"] in query_info["entities"]["characters"]:
                            result["score"] *= self.retrieval_settings["entity_boost_factor"]
            
            # Boost chunks matching time references
            if result["type"] == "narrative_chunk" and "season" in result["metadata"]:
                for time_ref in query_info["time_references"]:
                    if time_ref["type"] == "season" and result["metadata"]["season"] == time_ref["value"]:
                        result["score"] *= 1.2
                    elif time_ref["type"] == "episode" and result["metadata"]["episode"] == time_ref["value"]:
                        result["score"] *= 1.2
            
            # Check if result has relevant terms and boost if needed
            if "has_relevant_terms" in result and result["has_relevant_terms"]:
                term_boost = 1.0 + (0.05 * len(result.get("relevant_terms", [])))
                result["score"] *= min(term_boost, 1.3)  # Cap boost at 30%
            
            # Extra boost for special term matches
            if "matches_special_terms" in result and result["matches_special_terms"]:
                result["score"] *= 1.2
        
        # Sort by score
        combined_results.sort(key=lambda x: x["score"], reverse=True)
        
        # Normalize result fields to ensure all results have consistent field names
        self._normalize_result_fields(combined_results)
        
        return combined_results
    
    def _synthesize_response(self, query: str, results: List[Dict[str, Any]], query_type: str) -> str:
        """
        Generate a synthesized narrative response using LLM.
        
        Args:
            query: The original query
            results: Synthesized results
            query_type: Type of query
            
        Returns:
            Synthesized response as a string
        """
        if not results:
            return "I don't have any information about that in my memory."
        
        # Build LLM prompt
        prompt = f"""You are MEMNON, an advanced narrative intelligence system with perfect recall of story elements. 
Answer the following query based only on the provided context and evidence.

QUERY: "{query}"
QUERY TYPE: {query_type}

RELEVANT CONTEXT:
"""
        
        # Add top results as context
        for i, result in enumerate(results[:5]):  # Use up to 5 top results
            source_type = result.get("source", "unknown")
            score = result.get("score", 0)
            prompt += f"\n--- Source {i+1} ({source_type}, Score: {score:.2f}) ---\n"
            
            # Check for text field (main content)
            if "text" in result:
                prompt += f"TEXT: {result['text']}\n"
            
            # Add metadata if available
            if "metadata" in result:
                meta_str = ", ".join([f"{k}: {v}" for k, v in result["metadata"].items() 
                                    if k in ["season", "episode", "scene_number"]])
                if meta_str:
                    prompt += f"METADATA: {meta_str}\n"
            
            # Add relevance info if available
            if "relevance" in result and "matches" in result["relevance"]:
                matches = result["relevance"]["matches"]
                if matches:
                    prompt += f"RELEVANT TERMS: {', '.join(matches[:5])}\n"
        
        # Special handling for entity queries like "Who is Sullivan?"
        if query.lower().startswith("who is ") or query.lower().startswith("what is "):
            entity = query.lower().replace("who is ", "").replace("what is ", "").strip().rstrip("?")
            
            # Check if this is a specific entity query
            if entity:
                prompt += f"\n\nThis query is specifically asking about '{entity}'. Looking at the sources above, focus specifically on information that mentions or describes {entity}."
        
        prompt += "\n\nBased only on the information above, provide a concise answer to the query. Start your answer with 'ANSWER:' followed by a summary of relevant information. If the information isn't sufficient to answer the query, state what's missing. Focus on being accurate and relevant to the query. Keep your answer brief but informative, about 3-5 sentences."
        
        try:
            # Query LLM for synthesized response
            response = self._query_llm(prompt)
            
            # Clean up response
            response = response.strip()
            
            # If response is empty or couldn't be generated, create a simple summary
            if not response:
                response = self._generate_basic_summary(query, results, query_type)
            
            return response
        
        except Exception as e:
            logger.error(f"Error synthesizing response: {e}")
            return self._generate_basic_summary(query, results, query_type)
    
    def _generate_basic_summary(self, query: str, results: List[Dict[str, Any]], query_type: str) -> str:
        """
        Generate a basic summary if LLM synthesis fails.
        
        Args:
            query: The original query
            results: Results from search
            query_type: Type of query
            
        Returns:
            Basic summary as a string
        """
        summary = f"Here's what I found about your query:\n\n"
        
        for i, result in enumerate(results[:3]):  # Include top 3 results
            source_type = result.get("source", "unknown")
            score = result.get("score", 0)
            summary += f"- Result {i+1} ({source_type}, Score: {score:.2f}):\n"
            
            # Add text content
            if "text" in result:
                # Truncate text if needed
                content = result["text"]
                if len(content) > 200:
                    content = content[:197] + "..."
                
                # Add metadata if available
                if "metadata" in result and "season" in result["metadata"] and "episode" in result["metadata"]:
                    summary += f"  Scene (S{result['metadata']['season']}E{result['metadata']['episode']}): {content}\n"
                else:
                    summary += f"  {content}\n"
            
            else:
                summary += f"- {result['type']}: {str(result['content'])[:100]}...\n"
        
        return summary
    
    def _format_query_results(self, results: List[Dict[str, Any]]) -> str:
        """
        Format query results for display.
        
        Args:
            results: List of result dictionaries
            
        Returns:
            Formatted results as a string
        """
        if not results:
            return "No results found."
        
        output = f"Found {len(results)} results:\n\n"
        
        for i, result in enumerate(results):
            output += f"Result {i+1} (Score: {result['score']:.4f}):\n"
            output += f"Chunk ID: {result['chunk_id']}\n"
            output += f"Season: {result['metadata']['season']}, Episode: {result['metadata']['episode']}\n"
            output += f"Scene: {result['metadata']['scene_number']}\n"
            
            # Truncate text if too long
            text = result['text']
            if len(text) > 500:
                text = text[:497] + "..."
            output += f"Content: {text}\n\n"
        
        return output
    
    def _get_status(self) -> str:
        """
        Get the current status of the MEMNON agent.
        
        Returns:
            Status information as a string
        """
        session = self.Session()
        try:
            # Get counts from database
            chunk_count = session.query(sa.func.count(NarrativeChunk.id)).scalar()
            embedding_count = session.query(sa.func.count(ChunkEmbedding.chunk_id)).scalar()
            
            # Count by model
            model_counts = {}
            for model_key in self.embedding_models.keys():
                count = session.query(sa.func.count(ChunkEmbedding.chunk_id)) \
                    .filter(ChunkEmbedding.model == model_key) \
                    .scalar()
                model_counts[model_key] = count
            
            # Get embedding models info
            embedding_models_info = [f"{model}: {type(model_obj).__name__}" 
                                   for model, model_obj in self.embedding_models.items()]
            
            status = f"MEMNON Status:\n"
            status += f"- Database: {self.db_url}\n"
            status += f"- Total chunks: {chunk_count}\n"
            status += f"- Total embeddings: {embedding_count}\n"
            status += f"- Embeddings by model: {json.dumps(model_counts, indent=2)}\n"
            status += f"- Loaded embedding models: {', '.join(embedding_models_info)}\n"
            
            return status
        
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return f"Error getting status: {e}"
        
        finally:
            session.close()