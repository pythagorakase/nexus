"""
MEMNON Agent - Unified Memory Access System for Narrative Intelligence

This agent is responsible for high-quality retrieval operations, including:
- Managing embeddings across multiple models (via EmbeddingManager)
- Storing and retrieving narrative chunks
- Querying structured data (characters, places, etc.)
- Implementing multi-strategy retrieval (vector, text, structured)
- Normalizing scores and applying weights
"""

import os
import re
import uuid
import logging
import json
import time
# import requests # Removed: No longer making direct LLM calls
from typing import Dict, List, Tuple, Optional, Union, Any, Set
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, Column, Table, MetaData, text
from sqlalchemy.dialects.postgresql import UUID, BYTEA, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# Local utility imports
from .utils.embedding_manager import EmbeddingManager

# Letta framework
from letta.agent import Agent
from letta.schemas.agent import AgentState
from letta.schemas.memory import Memory
from letta.schemas.block import Block, CreateBlock
from letta.schemas.message import Message
# from letta.embeddings import EmbeddingEndpoint # Not directly used here

# Configure Memnon-specific logger
logger = logging.getLogger("nexus.memnon")

# Load settings FIRST to determine logging configuration
def load_settings():
    """Load settings from settings.json file"""
    try:
        script_dir = Path(__file__).parent.parent.parent.parent
        settings_path = script_dir / "settings.json"
        # Fallback if relative path fails (e.g., during testing)
        if not settings_path.exists():
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
# LLM_GLOBAL_SETTINGS = GLOBAL_SETTINGS.get("llm", {}) # Removed: MEMNON no longer uses global LLM settings directly

# Setup Logging based on loaded settings
log_config = MEMNON_SETTINGS.get("logging", {})
log_level_name = log_config.get("level", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)
log_file = log_config.get("file", "memnon.log") # Use path from settings
log_console = log_config.get("console", True)

# Clear existing handlers for this specific logger to avoid duplicates if reloaded
if logger.hasHandlers():
    logger.handlers.clear()

logger.setLevel(log_level) # Set the logger level itself

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

handlers = []
if log_file:
    try:
        # Ensure the log directory exists if specified in the path
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        # Set file handler level explicitly
        file_handler.setLevel(log_level)
        handlers.append(file_handler)
    except Exception as e:
        print(f"Warning: Could not configure file logging for {log_file}: {e}")

if log_console:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    # Set console handler level explicitly
    console_handler.setLevel(log_level)
    handlers.append(console_handler)

# Add handlers if any were created
if handlers:
     for handler in handlers:
         logger.addHandler(handler)
else:
    # If no handlers configured, add a basic NullHandler to prevent warnings
    logger.addHandler(logging.NullHandler())
    print("Warning: No logging handlers configured for MEMNON.")

# Prevent propagating to root logger if handlers are set
logger.propagate = not bool(handlers)

logger.info(f"MEMNON logger configured. Level: {log_level_name}, Console: {log_console}, File: {log_file}")

# Removed LLM Settings
# MODEL_CONFIG = GLOBAL_SETTINGS.get("model", {})
# DEFAULT_MODEL_ID = MODEL_CONFIG.get("default_model", "llama-3.3-70b-instruct@q6_k")

# Database settings from MEMNON config
DEFAULT_DB_URL = MEMNON_SETTINGS.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")

# Define SQL Alchemy Base
Base = declarative_base()

# Define ORM models based on the PostgreSQL schema
class NarrativeChunk(Base):
    __tablename__ = 'narrative_chunks'

    id = Column(sa.BigInteger, primary_key=True) # Assuming default sequence or manual ID assignment elsewhere
    # chunk_uuid = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")) # Changed: Use simple ID for now
    raw_text = Column(sa.Text, nullable=False)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())

class ChunkEmbedding(Base):
    __tablename__ = 'chunk_embeddings'

    id = Column(sa.BigInteger, primary_key=True) # Assuming default sequence
    # embedding_uuid = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")) # Changed: Use simple ID
    chunk_id = Column(sa.BigInteger, sa.ForeignKey('narrative_chunks.id', ondelete='CASCADE'), nullable=False) # Changed: Foreign key type
    model = Column(sa.String(100), nullable=False)
    embedding = Column(BYTEA, nullable=False) # Changed: Use BYTEA for generic binary data
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    dimensions = Column(sa.Integer, default=1024) # Store dimension for reference

    __table_args__ = (
        sa.UniqueConstraint('chunk_id', 'model', name='uix_chunk_model'), # Changed: Use chunk_id
    )

class ChunkMetadata(Base):
    __tablename__ = 'chunk_metadata'

    id = Column(sa.BigInteger, primary_key=True) # Assuming default sequence
    # metadata_uuid = Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")) # Changed: Use simple ID
    chunk_id = Column(sa.BigInteger, sa.ForeignKey('narrative_chunks.id', ondelete='CASCADE'), nullable=False) # Changed: Foreign key type
    season = Column(sa.Integer)
    episode = Column(sa.Integer)
    scene = Column(sa.Integer) # Renamed from 'scene_number' for consistency
    world_layer = Column(sa.String(50))
    # narrative_vector = Column(sa.JSON) # Removed, more detailed fields preferred
    time_delta = Column(sa.String(100)) # Added
    location = Column(sa.String(255)) # Added
    atmosphere = Column(sa.String(255)) # Added
    characters = Column(sa.JSON) # Keep as JSON for now
    # setting = Column(sa.JSON) # Removed, covered by location/atmosphere
    # causality = Column(sa.JSON) # Removed, potentially derived later
    # prose = Column(sa.JSON) # Removed, stylistic analysis likely for LORE
    arc_position = Column(sa.String(50)) # Added
    direction = Column(sa.JSON) # Added
    magnitude = Column(sa.String(50)) # Added
    character_elements = Column(sa.JSON) # Added
    perspective = Column(sa.JSON) # Added
    interactions = Column(sa.JSON) # Added
    dialogue_analysis = Column(sa.JSON) # Added
    emotional_tone = Column(sa.JSON) # Added
    narrative_function = Column(sa.JSON) # Added
    narrative_techniques = Column(sa.JSON) # Added
    thematic_elements = Column(sa.JSON) # Added
    causality = Column(sa.JSON) # Added back (as per original schema?)
    continuity_markers = Column(sa.JSON) # Added
    metadata_version = Column(sa.String(20)) # Added
    generation_date = Column(sa.DateTime) # Added

    __table_args__ = (
        sa.UniqueConstraint('chunk_id', name='uix_metadata_chunk'), # Changed: Use chunk_id
    )


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
    retrieving narrative information across all memory types. Focuses purely on retrieval.
    """

    def __init__(self,
                 interface,
                 agent_state: Optional[AgentState] = None,
                 user = None,
                 db_url: str = None,
                 # model_id: str = None, # Removed: No LLM model needed
                 # model_path: str = None, # Removed
                 debug: bool = None,
                 **kwargs):
        """
        Initialize MEMNON agent with unified memory access capabilities.

        Args:
            interface: Interface for agent communication
            agent_state: Agent state from Letta framework (optional in direct mode)
            user: User information (optional in direct mode)
            db_url: PostgreSQL database URL
            # model_id: LM Studio model ID to use (Removed)
            # model_path: Path to local model file (fallback) (Removed)
            debug: Enable debug logging
            **kwargs: Additional arguments
        """
        # Handle direct mode (when agent_state is None)
        self.direct_mode = agent_state is None

        if self.direct_mode:
            # In direct mode, we skip the parent Agent initialization
            # and just set up the bare minimum we need
            self.interface = interface
            self.agent_state = None  # We don\'t use this in direct mode
            self.user = user
            self.block_manager = None  # Not used in direct mode
        else:
            # Normal Letta framework mode, initialize parent Agent class
            super().__init__(interface, agent_state, user, **kwargs)

            # Initialize specialized memory blocks if not present
            self._initialize_memory_blocks()

        # Configure logging level based on settings or parameter
        self.debug = MEMNON_SETTINGS.get("debug", False) # Still store the flag

        # Store LLM settings - prioritize agent specific, then global, then hardcoded default (Removed)
        # self.model_id = model_id or MEMNON_SETTINGS.get("model_id", DEFAULT_MODEL_ID) # Allow override
        # self.model_path = model_path # Keep explicit path if provided
        # logger.info(f"Using LLM model: {self.model_id}")

        # Set up database connection - use loaded setting
        self.db_url = db_url or DEFAULT_DB_URL # Use loaded default
        logger.info(f"Using database URL: {self.db_url}")
        self.db_engine = self._initialize_database_connection()
        self.Session = sessionmaker(bind=self.db_engine)

        # Set up embedding models using the manager
        # Pass MEMNON_SETTINGS to the manager
        self.embedding_manager = EmbeddingManager(settings=MEMNON_SETTINGS)

        # Get model weights from settings
        model_weights = {}
        for model_name, model_config in MEMNON_SETTINGS.get("models", {}).items():
            weight = model_config.get("weight", 0.33)  # Default equal weight
            model_weights[model_name] = weight

        # Use default weights if none defined in settings
        if not model_weights:
            # Define fallbacks if absolutely necessary, but prefer settings
            model_weights = {
                "bge-large": 0.4,
                "e5-large": 0.4,
                "bge-small-custom": 0.2
            }
            logger.warning("Using hardcoded default model weights as none found in settings.")

        # Removed LLM related flags
        # self.use_llm_search_planning = MEMNON_SETTINGS.get("query", {}).get("use_llm_planning", False)
        # self.force_text_first = False # Keep if still relevant for non-LLM testing? Assume no for now.

        # Get query and retrieval settings from configuration
        query_config = MEMNON_SETTINGS.get("query", {})
        retrieval_config = MEMNON_SETTINGS.get("retrieval", {})

        # Configure retrieval settings using values from settings.json
        self.retrieval_settings = {
            "default_top_k": query_config.get("default_limit", 10),
            "max_query_results": retrieval_config.get("max_results", 50),
            "relevance_threshold": retrieval_config.get("relevance_threshold", 0.7), # Use retrieval setting
            "entity_boost_factor": retrieval_config.get("entity_boost_factor", 1.2),
            "recency_boost_factor": retrieval_config.get("recency_boost_factor", 1.1), # Keep for potential future use?
            "db_vector_balance": retrieval_config.get("db_vector_balance", 0.6), # Keep for potential future use?
            "model_weights": model_weights, # Use loaded weights
            # "highlight_matches": query_config.get("highlight_matches", True) # Likely not needed without synthesis
            "include_vector_results": retrieval_config.get("include_vector_results", 10), # New setting
            "include_text_results": retrieval_config.get("include_text_results", 10), # New setting
            "include_structured_results": retrieval_config.get("include_structured_results", 5), # New setting
        }

        # Log the retrieval settings
        logger.debug(f"Retrieval settings: {json.dumps(self.retrieval_settings, indent=2)}")

        # Memory type registry - maps virtual memory tier to actual storage (Keep?)
        # Might be simplified or handled differently in rule-based approach. Keeping for now.
        self.memory_tiers = {
            "strategic": {"type": "database", "tables": ["events", "threats", "ai_notebook"]}, # Example tables
            "entity": {"type": "database", "tables": ["characters", "places", "factions", "items"]}, # Example tables
            "narrative": {"type": "vector", "collections": ["narrative_chunks"]},
        }

        # Query type registry - maps query types to appropriate tables and search methods (Removed)
        # This logic is now in _determine_search_strategy
        # self.query_types = { ... }

        # Removed LLM initialization test
        # self.llm_initialized = False
        # try: ... except ...

        logger.info("MEMNON agent initialized (Retrieval-Focused)")

    def _initialize_memory_blocks(self):
        """Initialize specialized memory blocks if not present."""
        # Check if memory blocks exist and create if needed
        required_blocks = ["memory_index", "query_templates", "retrieval_stats", "db_schema"]

        for block_name in required_blocks:
            if not self.direct_mode and block_name not in self.agent_state.memory.list_block_labels():
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
            "chunk_regex", r'<!--\\s*SCENE BREAK:\\s*(S(\\d+)E(\\d+))_(\\d+).*-->'
        )

        # Compile regex for scene breaks
        try:
            scene_break_regex = re.compile(chunk_regex_pattern)
        except re.error as e:
            logger.error(f"Invalid regex pattern in settings: {e}")
            # Fall back to default regex
            scene_break_regex = re.compile(r'<!--\\s*SCENE BREAK:\\s*(S(\\d+)E(\\d+))_(\\d+).*-->')

        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find all scene breaks
        scene_breaks = list(scene_break_regex.finditer(content))
        if not scene_breaks:
            logger.warning(f"No scene breaks found in {file_path} using pattern: {chunk_regex_pattern}")
            # Consider processing the whole file as one chunk if no breaks? For now, return 0.
            return 0

        chunks_processed = 0

        # Process each chunk
        for i in range(len(scene_breaks)):
            start_match = scene_breaks[i]

            try:
                # Extract metadata from the scene break
                # episode_str = start_match.group(1) # e.g., "S01E05" # Not used directly
                season = int(start_match.group(2))
                episode = int(start_match.group(3))
                scene_number = int(start_match.group(4))

                # Determine chunk boundaries (Extract text *between* breaks)
                start_pos = start_match.end() # Start *after* the comment
                if i < len(scene_breaks) - 1:
                    end_pos = scene_breaks[i + 1].start() # End *before* the next comment
                else:
                    end_pos = len(content) # To the end of the file

                # Extract chunk text (trim whitespace)
                chunk_text = content[start_pos:end_pos].strip()

                # Skip empty chunks
                if not chunk_text:
                    continue

                # Store the chunk with metadata
                # Chunk ID will be generated inside store_narrative_chunk
                chunk_db_id = self.store_narrative_chunk(
                    chunk_text=chunk_text,
                    metadata={
                        # "chunk_id": chunk_id, # Let DB handle primary key ID
                        "season": season,
                        "episode": episode,
                        "scene": scene_number, # Match metadata schema field name
                        "world_layer": "primary" # Default to primary world layer, can be enhanced
                        # Add more metadata extraction here if possible from context
                    }
                )
                if chunk_db_id: # Check if storage was successful
                    chunks_processed += 1
                    logger.info(f"Processed chunk (DB ID: {chunk_db_id}) from {file_path.name} (S{season}E{episode}_Scene{scene_number})")
                else:
                     logger.warning(f"Failed to store chunk from {file_path.name} (S{season}E{episode}_Scene{scene_number})")


            except Exception as e:
                chunk_num = i + 1
                logger.error(f"Error processing content after scene break #{chunk_num} from {file_path.name}: {e}")
                import traceback
                logger.error(traceback.format_exc())


        logger.info(f"Completed processing {chunks_processed} chunks from {file_path}")
        return chunks_processed

    def store_narrative_chunk(self, chunk_text: str, metadata: Dict[str, Any]) -> Optional[int]:
        """
        Store a narrative chunk with embeddings and metadata in PostgreSQL.

        Args:
            chunk_text: The text content of the chunk
            metadata: Associated metadata (season, episode, scene_number, etc.)

        Returns:
            The generated ID (primary key) of the stored chunk, or None if failed.
        """
        session = self.Session()

        try:
            # 1. Create narrative chunk
            narrative_chunk = NarrativeChunk(raw_text=chunk_text)
            session.add(narrative_chunk)
            session.flush() # Flush to get the generated ID

            chunk_db_id = narrative_chunk.id # Get the auto-generated ID
            if not chunk_db_id:
                 raise ValueError("Failed to get generated chunk ID after flush.")

            # 2. Create chunk metadata
            # Extract relevant metadata, ensuring keys match the ChunkMetadata model
            chunk_metadata = ChunkMetadata(
                chunk_id=chunk_db_id,
                season=metadata.get("season"),
                episode=metadata.get("episode"),
                scene=metadata.get("scene"), # Ensure key matches model
                world_layer=metadata.get("world_layer", "primary"),
                time_delta=metadata.get("time_delta"), # Add other fields as available
                location=metadata.get("location"),
                atmosphere=metadata.get("atmosphere"),
                characters=json.dumps(metadata.get("characters", [])), # Basic character extraction?
                arc_position=metadata.get("arc_position"),
                direction=metadata.get("direction"),
                magnitude=metadata.get("magnitude"),
                character_elements=metadata.get("character_elements"),
                perspective=metadata.get("perspective"),
                interactions=metadata.get("interactions"),
                dialogue_analysis=metadata.get("dialogue_analysis"),
                emotional_tone=metadata.get("emotional_tone"),
                narrative_function=metadata.get("narrative_function"),
                narrative_techniques=metadata.get("narrative_techniques"),
                thematic_elements=metadata.get("thematic_elements"),
                causality=metadata.get("causality"),
                continuity_markers=metadata.get("continuity_markers"),
                metadata_version=metadata.get("metadata_version", "1.0"), # Example default version
                generation_date=metadata.get("generation_date", datetime.now()) # Example default date
            )
            session.add(chunk_metadata)

            # 3. Generate embeddings with all available models using the manager
            available_models = self.embedding_manager.get_available_models()
            if not available_models:
                 logger.warning(f"No embedding models available in manager for chunk ID {chunk_db_id}. Skipping embedding generation.")

            for model_key in available_models:
                try:
                    # Generate embedding using the manager
                    embedding = self.embedding_manager.generate_embedding(chunk_text, model_key)

                    if embedding is None:
                        logger.warning(f"Failed to generate embedding for chunk ID {chunk_db_id} with model {model_key}. Skipping.")
                        continue # Skip this model if embedding failed

                    # Convert embedding to bytes for storage (assuming numpy array output)
                    import numpy as np
                    if isinstance(embedding, list):
                        embedding_arr = np.array(embedding, dtype=np.float32)
                    elif isinstance(embedding, np.ndarray):
                         embedding_arr = embedding.astype(np.float32)
                    else:
                         logger.error(f"Unexpected embedding type {type(embedding)} for model {model_key}. Cannot convert to bytes.")
                         continue

                    embedding_bytes = embedding_arr.tobytes()
                    embedding_dim = len(embedding_arr)

                    # Create chunk embedding
                    chunk_embedding = ChunkEmbedding(
                        chunk_id=chunk_db_id,
                        model=model_key,
                        embedding=embedding_bytes,
                        dimensions=embedding_dim # Store dimension
                    )
                    session.add(chunk_embedding)

                except Exception as e:
                    logger.error(f"Error generating/storing embedding for chunk {chunk_db_id} with model {model_key}: {e}")
                    # import traceback # Uncomment for detailed debugging
                    # logger.error(traceback.format_exc())
                    # Continue to next model even if one fails

            # Commit the transaction
            session.commit()
            logger.info(f"Successfully stored chunk ID {chunk_db_id} with metadata and embeddings for models: {available_models}")

            return chunk_db_id

        except Exception as e:
            session.rollback()
            logger.error(f"Error storing chunk and metadata: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

        finally:
            session.close()

    def _analyze_query_basic(self, query: str, query_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Simple rule-based query classification without LLM.
        """
        # Start with default query info
        query_info = {
            "query_text": query,
            "type": query_type or "general",
            "keywords": [],
            "entities": {"characters": [], "places": []}
        }

        # Only classify if not provided
        if not query_type:
            # Simple pattern matching for query types
            patterns = {
                r'\\b(who|character|about|background)\\b': "character",
                r'\\b(where|location|place|setting)\\b': "location",
                r'\\b(what happened|when|event|incident)\\b': "event",
                r'\\b(relation|connect|feel about|between)\\b': "relationship",
                r'\\b(theme|symbol|represent|meaning)\\b': "theme"
            }

            for pattern, qtype in patterns.items():
                if re.search(pattern, query.lower()):
                    query_info["type"] = qtype
                    break

        # Extract keywords (exclude stop words)
        stop_words = {"a", "an", "the", "is", "are", "was", "were", "in", "on", "at", "to", "for", "with", "by", "of", "what", "who", "where", "when", "how", "tell", "me", "about"}
        words = re.findall(r'\\b\\w+\\b', query.lower())
        query_info["keywords"] = [w for w in words if len(w) > 2 and w not in stop_words] # Adjusted length threshold

        # Look for entities in database (Characters and Places)
        try:
            with self.Session() as session:
                # Check for character names
                characters = session.query(Character.name).all()
                for name_tuple in characters:
                    name = name_tuple[0]
                    # Use regex for whole word matching, case-insensitive
                    if re.search(r'\\b' + re.escape(name) + r'\\b', query, re.IGNORECASE):
                        query_info["entities"]["characters"].append(name)

                # Check for place names
                places = session.query(Place.name).all()
                for name_tuple in places:
                    name = name_tuple[0]
                    if re.search(r'\\b' + re.escape(name) + r'\\b', query, re.IGNORECASE):
                        query_info["entities"]["places"].append(name)
        except Exception as e:
            logger.error(f"Error extracting entities from DB: {e}")

        # Remove duplicates from entities
        query_info["entities"]["characters"] = list(set(query_info["entities"]["characters"]))
        query_info["entities"]["places"] = list(set(query_info["entities"]["places"]))


        return query_info

    def _determine_search_strategy(self, query_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Determine retrieval strategy based on query type using fixed rules.
        """
        query_type = query_info["type"]
        keywords = query_info.get("keywords", [])
        entities = query_info.get("entities", {})
        query_text = query_info.get("query_text", "")

        # Use extracted entities and keywords for more targeted search
        search_keywords = list(set(keywords + entities.get("characters", []) + entities.get("places", [])))
        # If few specific keywords/entities, use the original query text for broader search
        if not search_keywords and len(query_text.split()) < 10 :
             search_keywords = [query_text] # Use full short query if no keywords/entities
        elif not search_keywords:
             search_keywords = keywords # Fallback to basic keywords if query is long

        # Define default strategies by query type
        # Priorities can be added later if needed
        strategies = {
            "character": [
                {"type": "structured_data", "tables": ["characters"], "entities": entities.get("characters", [])},
                {"type": "vector_search", "collections": ["narrative_chunks"]},
                {"type": "text_search", "keywords": search_keywords}
            ],
            "location": [
                {"type": "structured_data", "tables": ["places"], "entities": entities.get("places", [])},
                {"type": "vector_search", "collections": ["narrative_chunks"]},
                {"type": "text_search", "keywords": search_keywords}
            ],
            "event": [
                {"type": "vector_search", "collections": ["narrative_chunks"]},
                {"type": "text_search", "keywords": search_keywords},
                {"type": "structured_data", "tables": ["events"]} # Assuming 'events' table exists
            ],
            "theme": [
                {"type": "vector_search", "collections": ["narrative_chunks"]},
                {"type": "text_search", "keywords": search_keywords}
            ],
            "relationship": [
                {"type": "structured_data", "tables": ["characters"], "entities": entities.get("characters", [])}, # Get info on involved characters
                {"type": "vector_search", "collections": ["narrative_chunks"]},
                {"type": "text_search", "keywords": search_keywords}
            ],
            "general": [
                {"type": "vector_search", "collections": ["narrative_chunks"]},
                {"type": "structured_data", "tables": ["characters", "places"], "entities": entities}, # Pass all entities
                {"type": "text_search", "keywords": search_keywords}
            ]
        }

        return strategies.get(query_type, strategies["general"])

    def query_memory(self,
                    query: str,
                    query_type: Optional[str] = None,
                    filters: Optional[Dict[str, Any]] = None,
                    k: int = 10) -> Dict[str, Any]:
        """
        Unified memory query interface for pure retrieval without LLM interpretation.

        Args:
            query: The narrative query
            query_type: Optional type of query (character, event, theme, relationship)
            filters: Optional filters to apply (time, characters, locations, etc.)
            k: Number of results to return per source type initially, final k applied after merging.

        Returns:
            Dict containing query results and metadata without synthesized response
        """
        start_time = time.time()
        if filters is None:
            filters = {}

        # Simple rule-based query analysis
        query_info = self._analyze_query_basic(query, query_type)
        logger.info(f"Query classified as '{query_info['type']}' with keywords: {query_info['keywords']}, Entities: {query_info['entities']}")

        # Determine search strategies using fixed rules
        strategies = self._determine_search_strategy(query_info)
        logger.info(f"Using search strategies: {[s['type'] for s in strategies]}")

        # Execute all retrieval strategies
        all_results = {}
        combined_results = []

        # Get limits per source from settings
        vector_limit = self.retrieval_settings.get("include_vector_results", 10)
        text_limit = self.retrieval_settings.get("include_text_results", 10)
        structured_limit = self.retrieval_settings.get("include_structured_results", 5)
        final_k = self.retrieval_settings.get("default_top_k", 10) # Final number of results to return


        # Execute strategies
        for strategy in strategies:
            strategy_type = strategy["type"]
            strategy_start = time.time()
            results = []

            try:
                if strategy_type == "structured_data":
                    tables = strategy.get("tables", [])
                    # Pass relevant entities for structured search if available
                    entities_for_query = strategy.get("entities", query_info["entities"])
                    # Special case: If entities is a list (e.g., ["Alex"]), convert to expected dict format
                    if isinstance(entities_for_query, list) and tables and "characters" in tables :
                         entities_for_query = {"characters": entities_for_query, "places": []}
                    elif isinstance(entities_for_query, list) and tables and "places" in tables:
                         entities_for_query = {"characters": [], "places": entities_for_query}
                    elif isinstance(entities_for_query, list): # Fallback if ambiguous
                         entities_for_query = {"characters": entities_for_query, "places": entities_for_query}


                    temp_query_info = query_info.copy() # Avoid modifying original query_info
                    temp_query_info["entities"] = entities_for_query # Use specific entities for this strategy

                    results = self._query_structured_data(temp_query_info, tables, filters, structured_limit)
                    logger.info(f"Structured data search found {len(results)} results from {len(tables)} tables ({time.time() - strategy_start:.2f}s)")

                elif strategy_type == "vector_search":
                    collections = strategy.get("collections", ["narrative_chunks"])
                    results = self._query_vector_search(query, collections, filters, vector_limit)
                    logger.info(f"Vector search found {len(results)} results ({time.time() - strategy_start:.2f}s)")

                elif strategy_type == "text_search":
                    keywords = strategy.get("keywords", query_info["keywords"])
                    results = self._query_text_search(query_info, keywords, filters, text_limit)
                    logger.info(f"Text search found {len(results)} results using {len(keywords)} keywords ({time.time() - strategy_start:.2f}s)")

                else:
                    logger.warning(f"Unknown search strategy type: {strategy_type}")
                    continue

                # Store results per strategy type and add to combined list
                all_results[strategy_type] = results
                combined_results.extend(results) # Add results from this strategy

            except Exception as e:
                logger.error(f"Error executing search strategy {strategy_type}: {e}")
                import traceback
                logger.error(traceback.format_exc())

        # Apply score normalization and weights to the combined list
        self._normalize_vector_scores(combined_results)
        self._apply_source_weights(combined_results)

        # Check for second-person content and mark player character references
        # Trigger if 'alex' is mentioned or it's a character query involving 'you'/'your' etc.
        # Be careful with overly broad triggers for player perspective.
        second_person_terms = {"you", "your", "yourself"}
        trigger_perspective_check = False
        if "alex" in query.lower():
             trigger_perspective_check = True
        # Check if query is about character AND contains second person terms
        elif query_info["type"] == "character" and any(term in query.lower() for term in second_person_terms):
             trigger_perspective_check = True
        # Optional: Always check if any result contains strong second-person language? Could be slow.

        if trigger_perspective_check:
            logger.info("Checking results for second-person perspective...")
            self._detect_player_perspective(combined_results)

        # Simple deduplication by ID (ensure 'id' field exists)
        seen_ids = set()
        deduplicated_results = []
        for result in combined_results:
            # Ensure consistent field names ('id' or 'chunk_id') and add 'id' if missing
            self._normalize_result_fields([result]) # Normalize fields first (adds 'id' if needed)

            result_id = result.get("id")
            if result_id and result_id not in seen_ids:
                seen_ids.add(result_id)
                deduplicated_results.append(result)
            elif result_id:
                 if self.debug: logger.debug(f"Duplicate result ID found and removed: {result_id}")


        # Sort by final score and limit results to overall k
        deduplicated_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        final_results = deduplicated_results[:final_k] # Apply final limit

        # --- Debug Log Final Results ---\
        if self.debug:
            logger.debug(f"--- Final Ranked Results (Top {final_k}) ---")
            if not final_results:
                 logger.debug("  (No results after deduplication and ranking)")
            for i, res in enumerate(final_results):
                 res_id = res.get('id', 'N/A')
                 score = res.get('score', 0.0)
                 source = res.get('source', 'unknown')
                 text_snip = res.get('text', '')[:80]
                 persp = res.get('metadata',{}).get('perspective', '')
                 persp_str = f" ({persp})" if persp else ""
                 logger.debug(f"  {i+1}. ID: {res_id}, Score: {score:.4f}, Src: {source}{persp_str}, Snip: '{text_snip}...'" )
            logger.debug(f"--- End Final Results ---")
        # ---\

        # Add metadata about results
        execution_time = time.time() - start_time
        source_counts = {}
        for src_type in ["structured_data", "vector_search", "text_search"]:
             count = len([r for r in final_results if r.get("source") == src_type])
             if count > 0:
                 source_counts[src_type] = count

        # Return results without LLM-generated response
        return {
            "query": query,
            "query_type": query_info["type"],
            "results": final_results,
            "metadata": {
                "query_analysis": query_info, # Include analysis details
                "strategies_used": [s['type'] for s in strategies],
                "source_counts": source_counts,
                "execution_time": execution_time,
                "total_results_returned": len(final_results),
                "total_results_found_before_dedup": len(combined_results),
                "filters_applied": filters
            }
        }


    def _normalize_vector_scores(self, results: List[Dict[str, Any]]) -> None:
        """
        Normalize vector scores based on the observed distribution.
        (Copied from memnon_refactor.md)
        """
        # Get normalization settings
        norm_config = MEMNON_SETTINGS.get("retrieval", {}).get("vector_normalization", {})
        enabled = norm_config.get("enabled", True)

        if not enabled:
            return

        # Define normalization tiers based on observed distribution
        tiers = [
            # (score_threshold, normalized_score)
            (0.997, 0.90),   # Ultra-high scores
            (0.99, 0.85),    # Very high scores
            (0.97, 0.80),    # High scores (top ~3% if dist ~0.91 median)
            (0.95, 0.75),    # Good scores (top ~5%)
            (0.93, 0.70),    # Above average scores (top ~18%)
            (0.91, 0.65),    # Average scores (median ~0.91)
            (0.89, 0.60)     # Below average scores
        ]

        for result in results:
            if result.get("source") == "vector_search":
                raw_score = result.get("score", 0.0)
                original_score = raw_score
                normalized = False

                # Ensure score is float before comparison
                try:
                    raw_score_float = float(raw_score)
                except (ValueError, TypeError):
                     logger.warning(f"Could not convert vector score '{raw_score}' to float for normalization. Skipping result {result.get('id', 'unknown')}.")
                     continue

                # Apply tiered normalization
                for threshold, norm_score in tiers:
                    if raw_score_float >= threshold:
                        result["score"] = norm_score
                        normalized = True
                        break

                # Handle scores below the lowest tier
                if not normalized:
                    # Map 0.85-0.89 range to 0.50-0.60 range linearly
                    if raw_score_float >= 0.85:
                        # Linear interpolation: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
                        result["score"] = 0.50 + (raw_score_float - 0.85) * (0.60 - 0.50) / (0.89 - 0.85)
                    else:
                        # Anything below 0.85 gets a score proportional to its value relative to 0.85, mapping to [0, 0.5]
                        # Simplified: Scale linearly from 0 to 0.5 as raw_score goes from 0 to 0.85
                        result["score"] = max(0.0, raw_score_float * (0.50 / 0.85))

                # Clamp score just in case calculation goes wrong
                result["score"] = max(0.0, min(1.0, result["score"]))

                if self.debug and abs(original_score - result['score']) > 1e-4: # Log if score changed significantly
                    logger.debug(f"Normalized vector score from {original_score:.4f} to {result['score']:.4f} for result {result.get('id', 'unknown')}")


    def _apply_source_weights(self, results: List[Dict[str, Any]]) -> None:
        """
        Apply configurable weights to results based on their source.
        (Copied from memnon_refactor.md)
        """
        # Get source weights from settings
        source_weights = MEMNON_SETTINGS.get("retrieval", {}).get("source_weights", {
            "structured_data": 1.5,  # Boost structured data
            "vector_search": 0.8,    # Reduce vector search
            "text_search": 1.0       # Baseline
        })

        for result in results:
            source = result.get("source", "unknown")
            weight = source_weights.get(source, 1.0)

            if weight != 1.0:
                original_score = result.get("score", 0.0)
                # Ensure score is float before multiplication
                try:
                     original_score_float = float(original_score)
                except (ValueError, TypeError):
                     logger.warning(f"Could not convert score '{original_score}' to float for weighting. Skipping result {result.get('id', 'unknown')}")
                     continue

                weighted_score = min(0.999, original_score_float * weight) # Cap slightly below 1.0
                result["score"] = weighted_score

                if self.debug and abs(original_score_float - weighted_score) > 1e-4 :
                    logger.debug(f"Applied {source} weight {weight:.2f} to result {result.get('id', 'unknown')}: {original_score_float:.4f} -> {weighted_score:.4f}")


    def _detect_player_perspective(self, results: List[Dict[str, Any]]) -> None:
        """
        Detect second-person perspective in results and mark as player character references.
        (Copied from memnon_refactor.md)
        """
        # Use regex for more reliable word boundary checking
        you_pattern = re.compile(r'\\b(you)\\b', re.IGNORECASE)
        your_pattern = re.compile(r'\\b(your)\\b', re.IGNORECASE)
        yourself_pattern = re.compile(r'\\b(yourself)\\b', re.IGNORECASE)

        # Define threshold from settings or use default
        retrieval_settings = MEMNON_SETTINGS.get("retrieval", {})
        threshold = retrieval_settings.get("perspective_detection_threshold", 3)
        boost = retrieval_settings.get("perspective_score_boost", 0.05)
        boost_threshold = retrieval_settings.get("perspective_boost_threshold", 5)


        for result in results:
            text = result.get("text", "")
            if not text or not isinstance(text, str): # Ensure text is a non-empty string
                continue

            # Count second-person pronouns using regex
            you_count = len(you_pattern.findall(text))
            your_count = len(your_pattern.findall(text))
            yourself_count = len(yourself_pattern.findall(text))
            total_count = you_count + your_count + yourself_count

            # Set metadata if significant second-person narrative
            if total_count >= threshold:
                # Add or update metadata
                if "metadata" not in result:
                    result["metadata"] = {}

                # Ensure metadata is a dict
                if not isinstance(result["metadata"], dict):
                     logger.warning(f"Result metadata is not a dict, cannot add perspective info. ID: {result.get('id')}")
                     continue # Skip if metadata is malformed

                result["metadata"]["perspective"] = "second_person"
                result["metadata"]["player_character_focus"] = True

                if self.debug: logger.debug(f"Detected second-person perspective (count={total_count}) in result ID: {result.get('id')}")

                # Add a small score boost if count exceeds boost threshold
                if total_count >= boost_threshold:
                    original_score = result.get("score", 0.0)
                    # Ensure score is float
                    try:
                        original_score_float = float(original_score)
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert score '{original_score}' to float for perspective boost. Skipping boost for result {result.get('id')}")
                        continue

                    new_score = min(0.99, original_score_float + boost) # Cap score
                    result["score"] = new_score
                    if self.debug and abs(new_score - original_score_float) > 1e-4:
                         logger.debug(f"Boosted score for high 2nd-person count: {original_score_float:.4f} -> {new_score:.4f}")

    def _query_vector_search(self, query_text: str, collections: List[str], filters: Dict[str, Any], top_k: int) -> List[Dict[str, Any]]:
        """
        Query the vector database for chunks similar to the query text.
        Uses raw SQL with pgvector and handles multiple embedding models.

        Args:
            query_text: The text to search for
            collections: Vector collection names to search in (currently ignored, searches all narrative_chunks)
            filters: Metadata filters to apply (season, episode, etc.)
            top_k: Maximum number of results to return *per model* before merging

        Returns:
            List of matching chunks with scores and metadata
        """
        # Use default k from settings if not provided
        if top_k is None or top_k <= 0:
            top_k = self.retrieval_settings.get("include_vector_results", 10)


        try:
            # Generate embeddings for the query using all available models
            query_embeddings = {}
            for model_key in self.embedding_manager.get_available_models():
                try:
                    embedding = self.embedding_manager.generate_embedding(query_text, model_key)
                    if embedding is not None:
                         query_embeddings[model_key] = embedding
                    else:
                         logger.warning(f"Could not generate query embedding using model {model_key}. It will be excluded from vector search.")
                except Exception as e:
                    logger.error(f"Error generating query embedding with {model_key}: {e}")

            if not query_embeddings:
                logger.error("No query embeddings generated, cannot perform vector search.")
                return []

            # Dictionary to store results, keyed by chunk_id to handle merging scores
            results_dict = {}

            # Use raw SQL with psycopg2 for pgvector operations
            import psycopg2
            import psycopg2.extras # For dict cursor
            from psycopg2.extensions import register_adapter, AsIs
            import numpy as np
            from urllib.parse import urlparse

            # Function to adapt numpy arrays to pgvector format
            def adapt_numpy_array(numpy_array):
                 # Ensure it's a list of floats for pgvector string representation
                 return AsIs(repr(numpy_array.astype(float).tolist()))
            register_adapter(np.ndarray, adapt_numpy_array)


            # Parse database URL
            parsed_url = urlparse(self.db_url)
            conn_params = {
                "host": parsed_url.hostname,
                "port": parsed_url.port or 5432,
                "user": parsed_url.username,
                "password": parsed_url.password,
                "database": parsed_url.path[1:] # Remove leading slash
            }

            # Connect to the database
            conn = psycopg2.connect(**conn_params)
            conn.autocommit = True # Use autocommit for read-only queries

            try:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    # Execute search for each model
                    for model_key, embedding in query_embeddings.items():
                        # Build filter conditions
                        filter_conditions_sql = []
                        filter_params = []
                        # Example filters (expand as needed based on common use cases)
                        if filters:
                            if 'season' in filters and filters['season'] is not None:
                                filter_conditions_sql.append("cm.season = %s")
                                filter_params.append(filters['season'])
                            if 'episode' in filters and filters['episode'] is not None:
                                filter_conditions_sql.append("cm.episode = %s")
                                filter_params.append(filters['episode'])
                            if 'scene' in filters and filters['scene'] is not None: # Check for scene number
                                filter_conditions_sql.append("cm.scene = %s")
                                filter_params.append(filters['scene'])
                            if 'world_layer' in filters and filters['world_layer']:
                                filter_conditions_sql.append("cm.world_layer = %s")
                                filter_params.append(filters['world_layer'])
                            # Add more filters here (e.g., characters, location - might require JSONB querying)

                        filter_sql = ""
                        if filter_conditions_sql:
                            filter_sql = " AND " + " AND ".join(filter_conditions_sql)

                        # Ensure embedding is a numpy array for adaptation
                        if isinstance(embedding, list):
                             embedding_np = np.array(embedding, dtype=np.float32)
                        elif isinstance(embedding, np.ndarray):
                             embedding_np = embedding.astype(np.float32)
                        else:
                             logger.error(f"Unsupported embedding type {type(embedding)} for model {model_key}")
                             continue


                        # Execute raw SQL query with pgvector's <=> (cosine distance) or <-> (L2 distance)
                        # Using cosine distance (1 - similarity)
                        # Note: Assumes embeddings are normalized for cosine similarity
                        # Include metadata fields directly in the SELECT
                        sql = f"""
                        SELECT
                            nc.id as chunk_id,
                            nc.raw_text,
                            cm.season,
                            cm.episode,
                            cm.scene
                            -- Add other relevant metadata fields here if needed e.g., cm.location
                            , 1 - (ce.embedding <=> %s::vector) AS score -- Cosine similarity (1 - distance)
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
                            score DESC -- Order by similarity DESC
                        LIMIT
                            %s
                        """

                        # Combine parameters
                        query_params = [embedding_np, model_key] + filter_params + [top_k]

                        # Execute the query
                        cursor.execute(sql, query_params)
                        model_query_results = cursor.fetchall()

                        # Process results for this model
                        for row in model_query_results:
                            chunk_id = row['chunk_id']
                            score = row['score']

                            # If chunk hasn't been seen yet, add its base info
                            if chunk_id not in results_dict:
                                results_dict[chunk_id] = {
                                    'id': chunk_id, # Use DB ID as the primary ID
                                    'chunk_id': chunk_id,
                                    'text': row['raw_text'] or "", # Ensure text is not None
                                    'content_type': 'narrative',
                                    'metadata': {
                                        'season': row['season'],
                                        'episode': row['episode'],
                                        'scene': row['scene']
                                        # Add other metadata from row here e.g. 'location': row['location']
                                    },
                                    'model_scores': {}, # Store individual model scores
                                    'score': 0.0, # Initialize final score
                                    'source': 'vector_search'
                                }

                            # Store score from this specific model
                            results_dict[chunk_id]['model_scores'][model_key] = score

            finally:
                conn.close() # Ensure connection is closed

            # Calculate final weighted average scores
            model_weights = self.retrieval_settings.get('model_weights', {})
            if not model_weights:
                 logger.warning("No model weights found in settings for vector search score aggregation.")
                 # Fallback: Simple average if no weights
                 num_models = len(self.embedding_manager.get_available_models())
                 if num_models > 0:
                     model_weights = {model: 1.0/num_models for model in self.embedding_manager.get_available_models()}


            final_results_list = []
            for chunk_id, result_data in results_dict.items():
                weighted_score_sum = 0.0
                total_weight = 0.0
                valid_scores_found = False

                for model_key, weight in model_weights.items():
                    if model_key in result_data['model_scores']:
                        model_score = result_data['model_scores'][model_key]
                        # Ensure score is float
                        try:
                            model_score_float = float(model_score)
                        except (TypeError, ValueError):
                             logger.warning(f"Invalid score type ({type(model_score)}) for model {model_key}, chunk {chunk_id}. Skipping.")
                             continue

                        weighted_score_sum += model_score_float * weight
                        total_weight += weight
                        valid_scores_found = True

                # Calculate final score if valid scores and weights exist
                if valid_scores_found and total_weight > 0:
                    result_data['score'] = weighted_score_sum / total_weight
                elif valid_scores_found: # No weights, use simple average
                     num_scores = len(result_data['model_scores'])
                     if num_scores > 0:
                          # Ensure scores are float before summing
                          valid_numeric_scores = [float(s) for s in result_data['model_scores'].values() if isinstance(s, (int, float)) or (isinstance(s, str) and s.replace('.', '', 1).isdigit())]
                          if valid_numeric_scores:
                               result_data['score'] = sum(valid_numeric_scores) / len(valid_numeric_scores)
                          else:
                               result_data['score'] = 0.0
                     else:
                          result_data['score'] = 0.0 # Should not happen if valid_scores_found is True
                else:
                     result_data['score'] = 0.0 # Assign 0 if no valid scores were found


                final_results_list.append(result_data)


            # Sort by final aggregated score and return (no final K here, applied in query_memory)
            final_results_list.sort(key=lambda x: x['score'], reverse=True)
            return final_results_list # Return all results for this strategy


        except ImportError as e:
             logger.error(f"Database library not found (psycopg2 or numpy?): {e}. Vector search requires these libraries.")
             return []
        except psycopg2.Error as e:
             logger.error(f"Database error during vector search: {e}")
             # Log specific PG code if available
             if hasattr(e, 'pgcode') and e.pgcode:
                  logger.error(f"PostgreSQL error code: {e.pgcode}")
             return []
        except Exception as e:
            logger.error(f"Unexpected error in vector search: {e}", exc_info=True) # Add exc_info
            return []

    def process_all_narrative_files(self, glob_pattern: str = None, limit: Optional[int] = None) -> int:
        """
        Process all narrative files matching the glob pattern.

        Args:
            glob_pattern: Pattern to match files to process.
                          If None, uses the pattern from settings.json
            limit: Maximum number of files to process (optional).

        Returns:
            Total number of chunks processed
        """
        # Use pattern from settings if not provided
        if glob_pattern is None:
            glob_pattern = MEMNON_SETTINGS.get("import", {}).get("file_pattern", "**/ALEX_S*.md") # Example pattern, might need adjustment
            logger.info(f"Using default file pattern from settings: {glob_pattern}")

        # Get other import settings
        import_config = MEMNON_SETTINGS.get("import", {})
        base_dir = import_config.get("base_directory", ".") # Allow specifying base directory relative to workspace
        batch_size = import_config.get("batch_size", 10)
        verbose = import_config.get("verbose", True)
        # Use provided limit or limit from settings
        file_limit = limit if limit is not None else import_config.get("file_limit", None) # Optional limit on number of files


        # Find all files matching the pattern within the base directory
        import glob as glob_module
        # Ensure base_dir is handled correctly whether absolute or relative
        base_path = Path(base_dir)
        if not base_path.is_absolute():
             # Assuming relative to workspace root if not absolute
             # This might need adjustment based on execution context
             # Get workspace root (safer way needed? Assume current dir is workspace for now)
             workspace_root = Path(os.getcwd())
             base_path = workspace_root / base_path

        search_path = str(base_path / glob_pattern) # Construct full search path
        logger.info(f"Searching for files matching: {search_path}")

        files_to_process = glob_module.glob(search_path, recursive=True) # Use recursive=True for ** pattern

        if not files_to_process:
            logger.warning(f"No files found matching pattern: {search_path}")
            # Try searching in current directory as fallback if base_dir was specified
            if base_dir != ".":
                 logger.info(f"Retrying search in current directory with pattern: {glob_pattern}")
                 files_to_process = glob_module.glob(glob_pattern, recursive=True)
                 if not files_to_process:
                      logger.warning(f"No files found in current directory either.")
                      return 0
            else:
                 return 0 # No files found even without base_dir

        # Apply file limit if specified
        if file_limit is not None and file_limit > 0:
             files_to_process = files_to_process[:file_limit]
             logger.info(f"Limiting processing to {len(files_to_process)} files.")


        # Log settings used
        logger.info(f"Processing {len(files_to_process)} files matching: {search_path}")
        logger.info(f"Batch size: {batch_size}, Verbose: {verbose}")

        total_chunks = 0
        total_files_processed = 0
        total_files_skipped = 0

        for i, file_path_str in enumerate(files_to_process):
            file_path = Path(file_path_str) # Convert to Path object
            logger.info(f"Processing file {i+1}/{len(files_to_process)}: {file_path}")

            try:
                chunks_processed = self.process_chunked_file(file_path)
                if chunks_processed > 0:
                    total_chunks += chunks_processed
                    total_files_processed += 1
                    # Report progress via interface if available and verbose
                    if verbose and hasattr(self, 'interface') and self.interface:
                        try:
                            # Ensure interface call is safe
                            if hasattr(self.interface, 'assistant_message') and callable(self.interface.assistant_message):
                                self.interface.assistant_message(f"Processed {chunks_processed} chunks from {file_path.name}")
                            else:
                                 logger.debug("Interface object lacks 'assistant_message' method.")
                        except Exception as ie:
                             logger.warning(f"Could not send progress message via interface: {ie}")
                else:
                     total_files_skipped +=1


                # Process in batches to avoid overloading the system
                if batch_size > 0 and (i + 1) % batch_size == 0 and i < len(files_to_process) - 1:
                    logger.info(f"Completed batch of {batch_size} files. Taking a short break...")
                    time.sleep(1) # Shorter pause between batches

            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}", exc_info=True) # Add exc_info for traceback
                total_files_skipped += 1
                # Report error via interface if available
                if hasattr(self, 'interface') and self.interface:
                    try:
                         if hasattr(self.interface, 'assistant_message') and callable(self.interface.assistant_message):
                             self.interface.assistant_message(f"ERROR processing {file_path.name}: {str(e)}")
                         else:
                              logger.debug("Interface object lacks 'assistant_message' method.")
                    except Exception as ie:
                        logger.warning(f"Could not send error message via interface: {ie}")

        summary_msg = f"Completed processing. Files processed: {total_files_processed}, Files skipped/failed: {total_files_skipped}. Total chunks stored: {total_chunks}"
        logger.info(summary_msg)
        # Final report via interface
        if hasattr(self, 'interface') and self.interface:
            try:
                 if hasattr(self.interface, 'assistant_message') and callable(self.interface.assistant_message):
                     self.interface.assistant_message(summary_msg)
                 else:
                      logger.debug("Interface object lacks 'assistant_message' method.")
            except Exception as ie:
                logger.warning(f"Could not send final summary message via interface: {ie}")

        return total_chunks

    def step(self, messages: List[Message]) -> Any:
        """
        Process incoming messages and return retrieval results.
        Other agents (like LORE) will handle response synthesis.
        (Refactored based on memnon_refactor.md)
        """
        # Extract the last user message
        if not messages:
            return {"error": "No messages to process."} # Return dict for consistency

        user_message = messages[-1]
        if user_message.role != "user":
            # Might be system message or assistant, ignore for now or handle specific cases
            logger.debug(f"Received non-user message, role: {user_message.role}. Ignoring.")
            return None # Indicate no action taken

        # Extract text from message content (handle list of content blocks)
        message_text = ""
        if isinstance(user_message.content, list):
            for content_item in user_message.content:
                # Handle different content types (e.g., TextBlock)
                if hasattr(content_item, 'text') and isinstance(content_item.text, str):
                    message_text += content_item.text + " " # Add space between parts
                # Add handling for other potential block types if needed
            message_text = message_text.strip()
        elif isinstance(user_message.content, str): # Handle plain string content
             message_text = user_message.content
        # Add handling for other content types if necessary

        if not message_text.strip():
            return {"error": "Message text is empty."}

        # Check for special commands first (simple implementation)
        # Consider a more robust command parsing mechanism if needed
        command = self._parse_command(message_text) # Pass text directly

        # Handle special commands
        if command and command.get("action") == "process_files":
            logger.info(f"Received process_files command with pattern: {command.get('pattern')}, limit: {command.get('limit')}")
            # Process narrative files
            glob_pattern = command.get("pattern") # Use parsed pattern or None for default
            limit = command.get("limit") # Use parsed limit or None
            try:
                 total_chunks = self.process_all_narrative_files(glob_pattern=glob_pattern, limit=limit)
                 return {"status": f"Processing initiated. Processed {total_chunks} chunks from narrative files."} # Return status dict
            except Exception as e:
                 logger.error(f"Error during process_files command: {e}", exc_info=True)
                 return {"error": f"Failed to process files: {e}"}

        elif command and command.get("action") == "status":
            logger.info("Received status command.")
            # Return agent status
            try:
                status_info = self._get_status()
                return {"status": status_info} # Return status dict
            except Exception as e:
                 logger.error(f"Error during status command: {e}", exc_info=True)
                 return {"error": f"Failed to get status: {e}"}

        # Handle all other messages as queries
        else:
            logger.info(f"Processing as query: {message_text}")

            # Extract filters if the command parser supports them (currently basic)
            filters = command.get("filters", {}) if command else {}

            # Get default limit from settings for the final result count
            default_limit = self.retrieval_settings.get("default_top_k", 10)

            try:
                # Use retrieval interface
                query_results = self.query_memory(
                    query=message_text,
                    query_type=None, # Let the analysis determine the type
                    filters=filters,
                    k=default_limit # Pass the *final* desired count
                )

                # Return only the retrieval results dictionary - LORE will handle synthesis
                return query_results

            except Exception as e:
                 logger.error(f"Error processing query: {e}", exc_info=True)
                 return {"error": f"Failed to process query: {e}"}

    def _parse_command(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Basic text-based command parser. Looks for keywords.

        Args:
            text: The user's message text.

        Returns:
            Dictionary with command action and parameters, or None if no command found.
        """
        text_lower = text.lower().strip()
        words = text_lower.split()

        # Check for "process files" command (more specific check)
        if len(words) >= 2 and words[0] == "process" and words[1] == "files":
            # Extract pattern if specified (example: process files pattern *.md limit 10)
            pattern = MEMNON_SETTINGS.get("import", {}).get("file_pattern", "**/ALEX_S*.md") # Default pattern
            limit = None

            # Look for 'pattern' keyword
            try:
                pattern_idx = words.index("pattern")
                if pattern_idx + 1 < len(words):
                    pattern = words[pattern_idx + 1] # Take the word after 'pattern'
                    # Simple check if pattern looks like a glob (contains * or ?)
                    if not ('*' in pattern or '?' in pattern):
                         logger.warning(f"Parsed pattern '{pattern}' doesn\'t look like a glob pattern.")
            except ValueError:
                pass # 'pattern' keyword not found

            # Look for 'limit' keyword
            try:
                limit_idx = words.index("limit")
                if limit_idx + 1 < len(words):
                    try:
                        limit = int(words[limit_idx + 1])
                    except ValueError:
                        logger.warning(f"Invalid limit value found: {words[limit_idx + 1]}")
            except ValueError:
                pass # 'limit' keyword not found


            return {"action": "process_files", "pattern": pattern, "limit": limit}

        # Check for "status" command (more specific check)
        elif text_lower == "status":
             return {"action": "status"}

        # Add more command checks here if needed
        # elif text_lower.startswith("command"):
        #     ... parse parameters ...
        #     return {"action": "command", ...}

        return None # No command detected


    def _query_structured_data(self, query_info: Dict[str, Any], tables: List[str], filters: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        Query structured database tables for exact data lookups based on entities.

        Args:
            query_info: Analyzed query information (contains entities)
            tables: Tables to query (e.g., ["characters", "places"])
            filters: Additional filters to apply (currently unused, add if needed)
            limit: Maximum number of results per table type

        Returns:
            List of matching structured data items
        """
        results = []
        if limit is None or limit <= 0: # Ensure limit is positive
            limit = self.retrieval_settings.get("include_structured_results", 5)

        entities = query_info.get("entities", {})
        character_names = entities.get("characters", [])
        place_names = entities.get("places", [])
        # Add other entity types if needed

        try:
            session = self.Session()

            # Process each table requested
            for table_name in tables:
                table_results = []

                if table_name == "characters" and character_names:
                    # Query the characters table based on identified character names
                    char_query = session.query(Character)

                    # Build filter for multiple names (case-insensitive exact or alias match)
                    name_filters = []
                    for name in character_names:
                        # Exact name match (case-insensitive)
                        name_filters.append(Character.name.ilike(name))
                        # Check aliases array (case-insensitive)
                        if hasattr(Character, 'aliases') and isinstance(Character.aliases.type, ARRAY):
                             # Use ANY and ILIKE for array searching
                             name_filters.append(Character.aliases.any(name, operator=sa.sql.operators.ilike_op))


                    if name_filters:
                        char_query = char_query.filter(sa.or_(*name_filters))
                    else:
                        continue # Skip querying characters if no names provided


                    # Execute query and process results
                    characters_found = char_query.limit(limit).all()
                    for character in characters_found:
                        # Adapt Character object to the standard result format
                        char_data = {
                            "id": f"char_{character.id}", # Create a unique ID prefix
                            "chunk_id": None, # Structured data might not have a direct chunk_id link initially
                            "name": character.name, # Include name for clarity
                            "content_type": "character",
                            "text": character.summary or "", # Use summary as primary text, ensure not None
                            "metadata": { # Include key character details
                                "name": character.name,
                                "aliases": character.aliases or [],
                                "background_snippet": (character.background[:150] + "..." if character.background and len(character.background) > 150 else character.background) or "",
                                "personality_snippet": (character.personality[:150] + "..." if character.personality and len(character.personality) > 150 else character.personality) or "",
                                "current_location": character.current_location or "",
                                "db_id": character.id # Include original DB id
                            },
                            "score": 0.95, # High confidence score for direct entity match
                            "source": "structured_data"
                        }
                        table_results.append(char_data)

                elif table_name == "places" and place_names:
                    # Query the places table based on identified place names
                    place_query = session.query(Place)

                    # Build filter for multiple names (case-insensitive exact match)
                    name_filters = []
                    for name in place_names:
                        # Exact name match (case-insensitive)
                        name_filters.append(Place.name.ilike(name))
                        # Optionally search other fields like location summary? Less precise.
                        # name_filters.append(Place.location.ilike(f'%{name}%'))

                    if name_filters:
                        place_query = place_query.filter(sa.or_(*name_filters))
                    else:
                         continue # Skip querying places if no names provided

                    # Execute query and process results
                    places_found = place_query.limit(limit).all()
                    for place in places_found:
                        # Adapt Place object to the standard result format
                        place_data = {
                            "id": f"place_{place.id}", # Create a unique ID prefix
                            "chunk_id": None,
                            "name": place.name,
                            "content_type": "place",
                            "text": place.summary or "", # Use summary, ensure not None
                            "metadata": {
                                "name": place.name,
                                "type": place.type or "",
                                "location": place.location or "",
                                "current_status": place.current_status or "",
                                "db_id": place.id
                            },
                            "score": 0.90, # Slightly lower than character match, still high
                            "source": "structured_data"
                        }
                        table_results.append(place_data)

                # Add logic for other tables (e.g., "events") if schemas exist and are needed
                # Example:
                # elif table_name == "events" and relevant_event_keywords:
                #      event_query = session.query(Event)
                #      ... apply filters based on keywords or time ...
                #      events_found = event_query.limit(limit).all()
                #      for event in events_found:
                #          event_data = { ... format ... }
                #          table_results.append(event_data)

                # Add results from this table to the main list
                results.extend(table_results)

            # --- Debug Logging for Structured Data ---\
            if self.debug and results:
                logger.debug(f"--- Structured Data Search Results (Tables: {', '.join(tables)}) ---")
                logger.debug(f"Found {len(results)} structured items matching entities {entities}:")
                for i, res in enumerate(results[:5]): # Log top 5
                    res_id = res.get('id', 'N/A')
                    name = res.get('name', 'N/A')
                    score = res.get('score', 0.0)
                    ctype = res.get('content_type', 'unknown')
                    text_snip = res.get('text', '')[:60]
                    logger.debug(f"  {i+1}. ID: {res_id}, Name: {name}, Type: {ctype}, Score: {score:.2f}, Snip: '{text_snip}...'")
                logger.debug(f"--- End Structured Data Results ---")
            elif self.debug:
                 logger.debug(f"--- Structured Data Search: No results found for entities {entities} in tables {tables} ---")


            return results

        except Exception as e:
            logger.error(f"Error querying structured data: {e}", exc_info=True) # Add exc_info
            return []

        finally:
            if 'session' in locals() and session.is_active:
                 session.close()


    def _query_text_search(self, query_info: Dict[str, Any], keywords: List[str], filters: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        Perform direct text search using SQL ILIKE on narrative chunks.

        Args:
            query_info: Analyzed query information (unused here, but kept for consistency)
            keywords: Keywords or phrases to search for
            filters: Additional filters to apply (season, episode, etc.)
            limit: Maximum number of results per keyword

        Returns:
            List of matching text results, scored based on match type.
        """
        if not keywords:
            logger.warning("Text search called with no keywords.")
            return []

        if limit is None or limit <= 0: # Ensure limit is positive
            limit = self.retrieval_settings.get("include_text_results", 10)

        results = {} # Use dict to store best result per chunk_id

        try:
            # Use raw SQL via SQLAlchemy for broader compatibility
            session = self.Session()

            # Base query joining chunks and metadata
            base_sql = """
            SELECT
                nc.id as chunk_id,
                nc.raw_text,
                cm.season,
                cm.episode,
                cm.scene
                -- Add other metadata if needed e.g., cm.location, cm.characters
            FROM
                narrative_chunks nc
            JOIN
                chunk_metadata cm ON nc.id = cm.chunk_id
            WHERE
                {where_clause}
                {filter_clause}
            LIMIT :limit
            """

            # Build filter conditions from the 'filters' argument
            filter_conditions_sql = []
            filter_params = {}
            if filters:
                if 'season' in filters and filters['season'] is not None:
                    filter_conditions_sql.append("cm.season = :f_season")
                    filter_params['f_season'] = filters['season']
                if 'episode' in filters and filters['episode'] is not None:
                    filter_conditions_sql.append("cm.episode = :f_episode")
                    filter_params['f_episode'] = filters['episode']
                if 'scene' in filters and filters['scene'] is not None:
                    filter_conditions_sql.append("cm.scene = :f_scene")
                    filter_params['f_scene'] = filters['scene']
                if 'world_layer' in filters and filters['world_layer']:
                    filter_conditions_sql.append("cm.world_layer = :f_world_layer")
                    filter_params['f_world_layer'] = filters['world_layer']
                # Add more filters as needed

            filter_sql_clause = ""
            if filter_conditions_sql:
                filter_sql_clause = " AND " + " AND ".join(filter_conditions_sql)

            # Search for each keyword/phrase separately
            processed_keywords = set() # Avoid processing same keyword multiple times if duplicated
            for i, keyword in enumerate(keywords):
                if not keyword or not isinstance(keyword, str) or keyword.lower() in processed_keywords:
                    continue # Skip empty, invalid, or duplicate keywords
                processed_keywords.add(keyword.lower())

                # Prepare parameters for this keyword
                keyword_param_name = f'kw_{i}'
                search_term = f'%{keyword}%' # Use % for ILIKE wildcard
                where_clause_sql = f"nc.raw_text ILIKE :{keyword_param_name}"

                # Combine params
                current_params = {keyword_param_name: search_term, 'limit': limit}
                current_params.update(filter_params)

                # Format final SQL
                final_sql = base_sql.format(where_clause=where_clause_sql, filter_clause=filter_sql_clause)

                # Execute query using SQLAlchemy text
                query_results = session.execute(text(final_sql), current_params).mappings().all()

                # Process results for this keyword
                for row_dict in query_results:
                    chunk_id = row_dict['chunk_id']
                    raw_text = row_dict['raw_text'] or "" # Ensure text is not None

                    # Calculate score based on match quality (simple version)
                    # Boost score slightly based on keyword frequency.
                    keyword_count = raw_text.lower().count(keyword.lower())
                    # Score: base + bonus for frequency, capped
                    score = min(0.85, 0.6 + (keyword_count * 0.05))

                    # If chunk already found by another keyword, only update if score is higher
                    # Also store all matching keywords
                    if chunk_id not in results or score > results[chunk_id]['score']:
                        results[chunk_id] = {
                            "id": chunk_id,
                            "chunk_id": chunk_id,
                            "text": raw_text,
                            "content_type": "narrative",
                            "metadata": {
                                "season": row_dict['season'],
                                "episode": row_dict['episode'],
                                "scene": row_dict['scene'],
                                "matched_keywords": [keyword], # Start list of matched keywords
                                "keyword_count": {keyword: keyword_count}
                            },
                            "score": score,
                            "source": "text_search"
                        }
                    elif chunk_id in results:
                         # Add keyword to existing list if not present
                         if keyword not in results[chunk_id]['metadata']['matched_keywords']:
                              results[chunk_id]['metadata']['matched_keywords'].append(keyword)
                         # Update keyword count if not present
                         if keyword not in results[chunk_id]['metadata']['keyword_count']:
                              results[chunk_id]['metadata']['keyword_count'][keyword] = keyword_count
                         # Optionally, slightly boost score for matching multiple keywords?
                         # results[chunk_id]['score'] = min(0.90, results[chunk_id]['score'] + 0.02 * len(results[chunk_id]['metadata']['matched_keywords']))


            # Convert dict back to list
            final_results_list = list(results.values())

            # Sort by score
            final_results_list.sort(key=lambda x: x['score'], reverse=True)

            # --- Debug Logging ---\
            if self.debug and final_results_list:
                 logger.debug(f"--- Text Search Results (Keywords: {keywords}) ---")
                 logger.debug(f"Found {len(final_results_list)} potential matches via text search:")
                 for i, res in enumerate(final_results_list[:5]): # Log top 5
                     res_id = res.get('id', 'N/A')
                     score = res.get('score', 0.0)
                     kw_list = res.get('metadata',{}).get('matched_keywords',[])
                     text_snip = res.get('text', '')[:60]
                     logger.debug(f"  {i+1}. ID: {res_id}, Score: {score:.2f}, KWs: {kw_list}, Snip: '{text_snip}...'")
                 logger.debug(f"--- End Text Search Results ---")
            elif self.debug:
                 logger.debug(f"--- Text Search: No results found for keywords {keywords} ---")


            return final_results_list # Return all found results, limit applied per keyword

        except Exception as e:
            logger.error(f"Error in text search: {e}", exc_info=True) # Add exc_info
            return []
        finally:
             if 'session' in locals() and session.is_active:
                 session.close()


    def _normalize_result_fields(self, results: List[Dict[str, Any]]) -> None:
        """
        Ensure all results have consistent field names, primarily 'text' for content
        and 'id' as a unique identifier.

        Args:
            results: List of search results to normalize (modified in place)
        """
        for result in results:
            # Ensure 'text' field exists, using 'raw_text', 'summary', or 'content' as fallback
            if 'text' not in result or not result['text']:
                if 'raw_text' in result and result['raw_text']:
                    result['text'] = result['raw_text']
                elif 'summary' in result and result['summary']:
                     result['text'] = result['summary']
                elif 'content' in result and result['content']:
                    # Handle potential dict content from older formats?
                    if isinstance(result['content'], str):
                        result['text'] = result['content']
                    else:
                        result['text'] = str(result['content']) # Basic string conversion
                else:
                    # If no suitable field, set empty string
                    result['text'] = ""
                    if self.debug: logger.debug(f"Could not find suitable text field for result {result.get('id', 'unknown')}, setting 'text' to empty.")

            # Ensure 'id' field exists, potentially using 'chunk_id' or generating one
            if 'id' not in result or not result['id']:
                 if 'chunk_id' in result and result['chunk_id']:
                     result['id'] = result['chunk_id']
                 else:
                     # Generate a fallback ID if none exists (e.g., for structured data)
                     import hashlib
                     # Use more fields for hashing to increase uniqueness
                     content_to_hash = (
                         result.get('text', "") +
                         result.get('name', "") +
                         str(result.get('metadata', {})) +
                         str(result.get('source', ""))
                     )
                     fallback_id = f"genid_{hashlib.md5(content_to_hash.encode()).hexdigest()[:10]}"
                     result['id'] = fallback_id
                     if self.debug: logger.debug(f"Generated fallback ID {fallback_id} for result missing 'id'.")


    def _get_status(self) -> str:
        """
        Get the current status of the MEMNON agent (database counts).

        Returns:
            Status information as a string
        """
        session = self.Session()
        try:
            status_parts = ["MEMNON Status:"]
            # Database Connection
            db_status = "Yes" if self.db_engine else "No"
            status_parts.append(f"- Database Connected: {db_status} ({self.db_url})")

            # Get counts from database safely
            def get_count(model):
                try:
                    return session.query(sa.func.count(model.id)).scalar() or 0
                except Exception as e:
                    logger.error(f"Error counting {model.__tablename__}: {e}")
                    return "Error"

            chunk_count = get_count(NarrativeChunk)
            embedding_count = get_count(ChunkEmbedding) # Count embeddings rows directly
            metadata_count = get_count(ChunkMetadata)
            character_count = get_count(Character)
            place_count = get_count(Place)

            status_parts.append(f"- Narrative Chunks: {chunk_count}")
            status_parts.append(f"- Chunk Metadata Entries: {metadata_count}")
            status_parts.append(f"- Total Embeddings Stored: {embedding_count}")

            # Count embeddings by model
            model_counts = {}
            if embedding_count != "Error" and embedding_count > 0:
                try:
                    counts_query = session.query(
                        ChunkEmbedding.model,
                        sa.func.count(ChunkEmbedding.id)
                    ).group_by(ChunkEmbedding.model).all()
                    model_counts = dict(counts_query)
                    status_parts.append(f"- Embeddings by model: {json.dumps(model_counts)}")
                except Exception as e:
                     logger.error(f"Error counting embeddings by model: {e}")
                     status_parts.append("- Embeddings by model: Error")


            # Get embedding models info from the manager
            try:
                 embedding_models_info = self.embedding_manager.get_available_models()
                 status_parts.append(f"- Configured Embedding Models: {', '.join(embedding_models_info)}")
            except Exception as e:
                 logger.error(f"Error getting available models from EmbeddingManager: {e}")
                 status_parts.append("- Configured Embedding Models: Error")


            status_parts.append(f"- Characters in DB: {character_count}")
            status_parts.append(f"- Places in DB: {place_count}")
            # Add other relevant counts or status checks

            return "\\n".join(status_parts)

        except Exception as e:
            logger.error(f"Error getting status: {e}", exc_info=True) # Add exc_info
            return f"Error getting status: {e}"

        finally:
            if session.is_active:
                session.close()