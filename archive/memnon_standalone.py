#!/usr/bin/env python3
"""
MEMNON - Unified Memory Access System for Narrative Intelligence

This standalone agent provides a complete interface to query the narrative memory
system, using local LLM capabilities to process natural language and provide
rich responses.

Usage:
    python memnon.py --interactive    # Interactive mode with continuous queries
    python memnon.py --query "What happened to Alex in Season 2?"   # One-off query
    python memnon.py --status         # Show system status

Database URL:
postgresql://pythagor@localhost/NEXUS
"""

import os
import re
import sys
import uuid
import json
import logging
import time
import argparse
from typing import Dict, List, Tuple, Optional, Union, Any, Set
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, Column, text
from sqlalchemy.dialects.postgresql import UUID, BYTEA
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# For embedding generation
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("Error: sentence-transformers library not found.")
    print("Please install it with: pip install sentence-transformers")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("memnon.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.memnon")

# Define SQL Alchemy Base
Base = declarative_base()

# Default paths for LLM
DEFAULT_MODEL_ID = "deepseek-r1-distill-llama-70b@q8_0"  # Model ID for LM Studio
DEFAULT_MODEL_PATH_1 = "/Users/pythagor/.lmstudio/models/lmstudio-community/DeepSeek-R1-Distill-Llama-70B-GGUF/DeepSeek-R1-Distill-Llama-70B-Q8_0-00001-of-00002.gguf"
DEFAULT_MODEL_PATH_2 = "/Users/pythagor/.lmstudio/models/lmstudio-community/DeepSeek-R1-Distill-Llama-70B-GGUF/DeepSeek-R1-Distill-Llama-70B-Q8_0-00002-of-00002.gguf"
MODEL_PATHS = [DEFAULT_MODEL_PATH_1, DEFAULT_MODEL_PATH_2]

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
    embedding = Column("embedding", sa.types.LargeBinary)
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
    aliases = Column(sa.ARRAY(sa.String))
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
    inhabitants = Column(sa.ARRAY(sa.String))
    historical_significance = Column(sa.Text)
    current_status = Column(sa.String(500))
    undiscovered = Column(sa.Text)
    extra_data = Column(sa.JSON)
    created_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now())
    updated_at = Column(sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())

class MEMNON:
    """
    MEMNON (Unified Memory Access System) agent responsible for accessing and 
    retrieving narrative information across all memory types.
    """
    
    def __init__(self, 
                 db_url: str = None,
                 model_id: str = DEFAULT_MODEL_ID,
                 model_path: str = None,
                 debug: bool = False):
        """
        Initialize MEMNON agent with unified memory access capabilities.
        
        Args:
            db_url: PostgreSQL database URL
            model_id: LM Studio model ID to use
            model_path: Path to local model file (fallback)
            debug: Enable debug logging
        """
        # Configure logging level
        if debug:
            logger.setLevel(logging.DEBUG)
            
        # Set up database connection
        self.db_url = db_url or os.environ.get("NEXUS_DB_URL", "postgresql://pythagor@localhost/NEXUS")
        self.db_engine = self._initialize_database_connection()
        self.Session = sessionmaker(bind=self.db_engine)
        
        # Store LLM settings
        self.model_id = model_id 
        self.model_path = model_path
        
        # Set up embedding models
        self.embedding_models = self._initialize_embedding_models()
        
        # Configure retrieval settings
        self.retrieval_settings = {
            "default_top_k": 10,
            "max_query_results": 50,
            "relevance_threshold": 0.7,
            "entity_boost_factor": 1.2,
            "recency_boost_factor": 1.1,
            "db_vector_balance": 0.6,  # 60% weight to database, 40% to vector
            "model_weights": {
                "bge-large": 0.4,
                "e5-large": 0.4,
                "bge-small-custom": 0.2
            }
        }
        
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
    
    def _initialize_database_connection(self) -> sa.engine.Engine:
        """Initialize connection to PostgreSQL database."""
        try:
            engine = create_engine(self.db_url)
            
            # Verify connection
            connection = engine.connect()
            connection.close()
            
            logger.info(f"Successfully connected to database at {self.db_url}")
            return engine
        
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise ConnectionError(f"Database connection failed: {e}")
    
    def _initialize_embedding_models(self) -> Dict[str, Any]:
        """Initialize embedding models for semantic retrieval."""
        embedding_models = {}
        
        try:
            # Load BGE-large model
            logger.info("Loading BGE-large embedding model...")
            try:
                bge_large = SentenceTransformer("BAAI/bge-large-en")
                embedding_models["bge-large"] = bge_large
                logger.info("Loaded BGE-large embedding model")
            except Exception as e:
                logger.warning(f"Failed to load BGE-large: {e}")
            
            # Load E5-large model
            logger.info("Loading E5-large embedding model...")
            try:
                e5_large = SentenceTransformer("intfloat/e5-large-v2")
                embedding_models["e5-large"] = e5_large
                logger.info("Loaded E5-large embedding model")
            except Exception as e:
                logger.warning(f"Failed to load E5-large: {e}")
            
            # Try to load fine-tuned BGE-small model from local path
            logger.info("Loading custom BGE-small model...")
            bge_small_path = Path("/Users/pythagor/nexus/models/bge_small_finetuned_20250320_153654")
            if bge_small_path.exists():
                try:
                    bge_small = SentenceTransformer(str(bge_small_path))
                    embedding_models["bge-small-custom"] = bge_small
                    logger.info("Loaded custom fine-tuned BGE-small embedding model")
                except Exception as e:
                    logger.warning(f"Failed to load custom BGE-small: {e}")
            else:
                # Fall back to standard BGE-small
                try:
                    bge_small = SentenceTransformer("BAAI/bge-small-en")
                    embedding_models["bge-small"] = bge_small
                    logger.info("Loaded standard BGE-small embedding model (fine-tuned model not found)")
                except Exception as e:
                    logger.warning(f"Failed to load standard BGE-small: {e}")
            
            if not embedding_models:
                logger.error("No embedding models could be loaded. Vector search will not be available.")
            
            return embedding_models
        
        except Exception as e:
            logger.error(f"Error initializing embedding models: {e}")
            # Return any successfully loaded models rather than failing completely
            return embedding_models

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
            available_models = list(self.embedding_models.keys())
            if not available_models:
                raise ValueError("No embedding models available")
            
            # Fall back to first available model
            model_key = available_models[0]
            logger.warning(f"Model {model_key} not found, using {model_key} instead")
        
        model = self.embedding_models[model_key]
        embedding = model.encode(text)
        
        return embedding.tolist()
    
    def query_memory(self, 
                   query: str, 
                   query_type: Optional[str] = None,
                   memory_tiers: Optional[List[str]] = None,
                   filters: Optional[Dict[str, Any]] = None,
                   k: int = 10) -> Dict[str, Any]:
        """
        Unified memory query interface for retrieving narrative information.
        
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
        
        # Determine which memory tiers to access if not specified
        if not memory_tiers:
            memory_tiers = self._determine_relevant_memory_tiers(query_info)
        
        # Initialize results container
        all_results = {}
        
        # Query each relevant memory tier
        for tier in memory_tiers:
            tier_info = self.memory_tiers.get(tier)
            if not tier_info:
                logger.warning(f"Unknown memory tier: {tier}")
                continue
                
            if tier_info["type"] == "database":
                # Query structured database
                tier_results = self._query_database(
                    query_info, tier_info["tables"], filters, k)
            elif tier_info["type"] == "vector":
                # Query vector store
                tier_results = self._query_vector_store(
                    query_info, tier_info["collections"], filters, k)
            
            all_results[tier] = tier_results
        
        # Cross-reference and synthesize results
        synthesized_results = self._synthesize_results(all_results, query_info)
        
        # Format final response
        response = {
            "query": query,
            "query_type": query_info["type"],
            "results": synthesized_results,
            "metadata": {
                "sources": memory_tiers,
                "result_count": len(synthesized_results),
                "filters_applied": filters
            }
        }
        
        return response
    
    def _analyze_query(self, query: str, query_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze query to understand information need and type.
        Uses local LLM to determine the query type if not provided.
        
        Args:
            query: User's query string
            query_type: Optional predefined query type
            
        Returns:
            Dict with query analysis information
        """
        query_info = {
            "original_query": query,
            "query_text": query,  # May be modified for search
            "entities": [],       # Recognized entities
            "keywords": [],       # Important keywords
            "filters": {}         # Detected filter criteria
        }
        
        # Extract season and episode filters if present
        season_match = re.search(r"season\s+(\d+)", query, re.IGNORECASE)
        if season_match:
            query_info["filters"]["season"] = int(season_match.group(1))
            
        episode_match = re.search(r"episode\s+(\d+)", query, re.IGNORECASE)
        if episode_match:
            query_info["filters"]["episode"] = int(episode_match.group(1))
        
        # Handle character names
        character_names = self._extract_character_names_from_query(query)
        if character_names:
            query_info["entities"].extend(character_names)
            query_info["filters"]["characters"] = character_names
        
        # If query type not provided, try to determine it
        if not query_type:
            query_type = self._determine_query_type(query)
        
        query_info["type"] = query_type
            
        # Extract additional keywords based on query type
        if query_type == "character":
            # Look for character names not already found
            query_info["focus"] = "character"
            for entity in query_info["entities"]:
                if entity.lower() not in query.lower():
                    query_info["query_text"] += f" {entity}"
                    
        elif query_type == "location":
            query_info["focus"] = "location"
            # Look for location names
            place_names = self._extract_place_names_from_query(query)
            if place_names:
                query_info["entities"].extend(place_names)
                query_info["filters"]["places"] = place_names
                
        elif query_type == "theme":
            query_info["focus"] = "theme"
            # Add theme-related terms
            theme_keywords = self._extract_themes_from_query(query)
            if theme_keywords:
                query_info["keywords"].extend(theme_keywords)
                
        elif query_type == "relationship":
            query_info["focus"] = "relationship"
            # Check if we have at least two characters
            if len(character_names) >= 2:
                query_info["filters"]["relationship_pair"] = character_names[:2]
                
        elif query_type == "event":
            query_info["focus"] = "event"
            # Look for event identifiers
            event_keywords = self._extract_events_from_query(query)
            if event_keywords:
                query_info["keywords"].extend(event_keywords)
        
        logger.debug(f"Analyzed query: {query_info}")
        return query_info
    
    def _determine_query_type(self, query: str) -> str:
        """
        Determine the type of query using pattern matching or LLM assistance.
        
        Args:
            query: The user's query string
            
        Returns:
            Query type string (character, location, event, theme, relationship, narrative)
        """
        # Try simple pattern matching first
        query_lower = query.lower()
        
        # Character query patterns
        if any(pattern in query_lower for pattern in [
            "who is", "what is", "tell me about", "character", "person", 
            "background of", "personality", "motivation"
        ]) and not "where" in query_lower:
            return "character"
            
        # Location query patterns
        if any(pattern in query_lower for pattern in [
            "where is", "location", "place", "setting", "area",
            "district", "building", "region"
        ]):
            return "location"
            
        # Event query patterns
        if any(pattern in query_lower for pattern in [
            "what happened", "event", "incident", "occurrence",
            "battle", "meeting", "confrontation", "encounter",
            "when did", "during the"
        ]):
            return "event"
            
        # Relationship query patterns
        if any(pattern in query_lower for pattern in [
            "relationship", "connection", "interaction", "between",
            "feel about", "thinks of", "attitude toward", "alliance",
            "enemies", "friends", "lovers", "partners"
        ]):
            return "relationship"
            
        # Theme query patterns
        if any(pattern in query_lower for pattern in [
            "theme", "motif", "symbol", "meaning", "represents",
            "significance", "philosophy", "concept", "idea",
            "explore", "examination of"
        ]):
            return "theme"
            
        # If simple pattern matching didn't work, try LLM
        try:
            # Create prompt for query type classification
            prompt = f"""You are a narrative intelligence assistant. Your task is to classify a user query about a narrative into one of the following types:
- character: Questions about specific characters, their backgrounds, personalities, or actions
- location: Questions about places, settings, or environments
- event: Questions about specific events, incidents, or plot points
- relationship: Questions about connections or interactions between characters
- theme: Questions about themes, symbols, or deeper meanings
- narrative: General questions about the story or plot

User query: "{query}"

First, analyze the query carefully. Then, provide your classification as a single word from the list above.
"""
            # Query LLM
            response = self._query_llm(prompt)
            
            # Parse response - look for one of the valid query types
            valid_types = ["character", "location", "event", "relationship", "theme", "narrative"]
            for valid_type in valid_types:
                if valid_type in response.lower():
                    logger.debug(f"LLM classified query as: {valid_type}")
                    return valid_type
                    
        except Exception as e:
            logger.warning(f"LLM query type classification failed: {e}")
            
        # Default to narrative if all else fails
        return "narrative"
    
    def _determine_relevant_memory_tiers(self, query_info: Dict[str, Any]) -> List[str]:
        """
        Determine which memory tiers are most relevant for a query.
        
        Args:
            query_info: Information about the query
            
        Returns:
            List of relevant tier names
        """
        query_type = query_info.get("type", "narrative")
        
        # Get tier information from query type registry
        if query_type in self.query_types:
            type_info = self.query_types[query_type]
            tiers = []
            
            # Add primary tier
            if "primary_tier" in type_info:
                tiers.append(type_info["primary_tier"])
                
            # Add secondary tier if different
            if "secondary_tier" in type_info and type_info["secondary_tier"] not in tiers:
                tiers.append(type_info["secondary_tier"])
                
            if tiers:
                return tiers
                
        # Default tier selection
        if query_type == "character" or query_type == "location" or query_type == "relationship":
            return ["entity", "narrative"]
        elif query_type == "event":
            return ["strategic", "narrative"]
        elif query_type == "theme":
            return ["narrative"]
        else:
            # For general narrative queries, search all tiers
            return ["narrative", "entity", "strategic"]
    
    def _query_database(self, 
                      query_info: Dict[str, Any], 
                      tables: List[str],
                      filters: Optional[Dict[str, Any]] = None,
                      k: int = 10) -> List[Dict[str, Any]]:
        """
        Query structured database for narrative information.
        
        Args:
            query_info: Information about the query
            tables: List of tables to query
            filters: Additional filters to apply
            k: Maximum number of results to return
            
        Returns:
            List of database results
        """
        if not tables:
            return []
            
        # Combine filters from query_info and explicitly provided filters
        combined_filters = {}
        if filters:
            combined_filters.update(filters)
        if "filters" in query_info:
            combined_filters.update(query_info["filters"])
            
        results = []
        session = self.Session()
        
        try:
            # Process each table
            for table_name in tables:
                try:
                    # Get results based on table type
                    if table_name == "characters":
                        table_results = self._query_characters_table(session, query_info, combined_filters, k)
                        results.extend(table_results)
                        
                    elif table_name == "places":
                        table_results = self._query_places_table(session, query_info, combined_filters, k)
                        results.extend(table_results)
                        
                    # Add additional table handlers as needed
                    # elif table_name == "events": ...
                    # elif table_name == "items": ...
                    
                    else:
                        logger.warning(f"No specific handler for table: {table_name}")
                        
                except Exception as e:
                    logger.error(f"Error querying table {table_name}: {e}")
                    
            # Limit to k results
            return results[:k]
            
        finally:
            session.close()
            
    def _query_characters_table(self, session: Session, query_info: Dict[str, Any], 
                             filters: Dict[str, Any], k: int) -> List[Dict[str, Any]]:
        """Query the characters table with the given parameters."""
        character_results = []
        
        # Check if we have character names to search for
        character_names = filters.get("characters", [])
        if not character_names and "entities" in query_info:
            character_names = query_info["entities"]
            
        if character_names:
            # Search for specific character(s)
            for name in character_names:
                try:
                    # Try exact match first, then partial match
                    character = session.query(Character).filter(
                        sa.or_(
                            Character.name == name,
                            Character.name.ilike(f"%{name}%"),
                            sa.func.array_to_string(Character.aliases, ',').ilike(f"%{name}%")
                        )
                    ).first()
                    
                    if character:
                        # Convert to dictionary
                        character_dict = {
                            "id": character.id,
                            "name": character.name,
                            "aliases": character.aliases if character.aliases else [],
                            "summary": character.summary,
                            "appearance": character.appearance,
                            "personality": character.personality,
                            "emotional_state": character.emotional_state,
                            "current_location": character.current_location,
                            "source": "characters",
                            "score": 1.0  # Exact database match
                        }
                        character_results.append(character_dict)
                        
                except Exception as e:
                    logger.error(f"Error searching for character '{name}': {e}")
        else:
            # No specific names, do a general search
            try:
                query_text = query_info.get("query_text", "")
                if query_text:
                    # Search in name, summary, background, personality
                    characters = session.query(Character).filter(
                        sa.or_(
                            Character.name.ilike(f"%{query_text}%"),
                            Character.summary.ilike(f"%{query_text}%"),
                            Character.background.ilike(f"%{query_text}%"),
                            Character.personality.ilike(f"%{query_text}%")
                        )
                    ).limit(k).all()
                    
                    for character in characters:
                        # Convert to dictionary
                        character_dict = {
                            "id": character.id,
                            "name": character.name,
                            "aliases": character.aliases if character.aliases else [],
                            "summary": character.summary,
                            "appearance": character.appearance,
                            "personality": character.personality,
                            "emotional_state": character.emotional_state,
                            "current_location": character.current_location,
                            "source": "characters",
                            "score": 0.9  # Text match, not exact
                        }
                        character_results.append(character_dict)
                        
            except Exception as e:
                logger.error(f"Error doing general character search: {e}")
                
        return character_results
            
    def _query_places_table(self, session: Session, query_info: Dict[str, Any], 
                         filters: Dict[str, Any], k: int) -> List[Dict[str, Any]]:
        """Query the places table with the given parameters."""
        place_results = []
        
        # Check if we have place names to search for
        place_names = filters.get("places", [])
        if not place_names and "entities" in query_info:
            # Filter entities that might be places (this is very basic, could be improved)
            place_names = [entity for entity in query_info["entities"] 
                         if entity not in filters.get("characters", [])]
            
        if place_names:
            # Search for specific place(s)
            for name in place_names:
                try:
                    # Try exact match first, then partial match
                    place = session.query(Place).filter(
                        sa.or_(
                            Place.name == name,
                            Place.name.ilike(f"%{name}%"),
                            Place.location.ilike(f"%{name}%")
                        )
                    ).first()
                    
                    if place:
                        # Convert to dictionary
                        place_dict = {
                            "id": place.id,
                            "name": place.name,
                            "type": place.type,
                            "location": place.location,
                            "summary": place.summary,
                            "inhabitants": place.inhabitants if place.inhabitants else [],
                            "historical_significance": place.historical_significance,
                            "current_status": place.current_status,
                            "source": "places",
                            "score": 1.0  # Exact database match
                        }
                        place_results.append(place_dict)
                        
                except Exception as e:
                    logger.error(f"Error searching for place '{name}': {e}")
        else:
            # No specific names, do a general search
            try:
                query_text = query_info.get("query_text", "")
                if query_text:
                    # Search in name, location, summary, historical_significance
                    places = session.query(Place).filter(
                        sa.or_(
                            Place.name.ilike(f"%{query_text}%"),
                            Place.location.ilike(f"%{query_text}%"),
                            Place.summary.ilike(f"%{query_text}%"),
                            Place.historical_significance.ilike(f"%{query_text}%")
                        )
                    ).limit(k).all()
                    
                    for place in places:
                        # Convert to dictionary
                        place_dict = {
                            "id": place.id,
                            "name": place.name,
                            "type": place.type,
                            "location": place.location,
                            "summary": place.summary,
                            "inhabitants": place.inhabitants if place.inhabitants else [],
                            "historical_significance": place.historical_significance,
                            "current_status": place.current_status,
                            "source": "places",
                            "score": 0.9  # Text match, not exact
                        }
                        place_results.append(place_dict)
                        
            except Exception as e:
                logger.error(f"Error doing general place search: {e}")
                
        return place_results
    
    def _query_vector_store(self, 
                          query_info: Dict[str, Any], 
                          collections: List[str],
                          filters: Optional[Dict[str, Any]] = None,
                          k: int = 10) -> List[Dict[str, Any]]:
        """
        Query vector store for semantically relevant information.
        
        Args:
            query_info: Information about the query
            collections: Vector collections to search
            filters: Metadata filters to apply
            k: Maximum number of results to return
            
        Returns:
            List of vector search results
        """
        # Combine filters from query_info and explicitly provided filters
        combined_filters = {}
        if filters:
            combined_filters.update(filters)
        if "filters" in query_info:
            combined_filters.update(query_info["filters"])
            
        # Generate query embedding
        query_text = query_info.get("query_text", "")
        query_embeddings = {}
        for model_name in self.embedding_models.keys():
            try:
                query_embeddings[model_name] = self.generate_embedding(query_text, model_name)
            except Exception as e:
                logger.error(f"Error generating {model_name} embedding: {e}")
                
        if not query_embeddings:
            logger.error("No embeddings could be generated for the query")
            return []
            
        # Perform vector search with metadata filtering
        return self._vector_search(query_embeddings, combined_filters, k)
    
    def _vector_search(self,
                     query_embeddings: Dict[str, List[float]],
                     filters: Optional[Dict[str, Any]] = None,
                     k: int = 10) -> List[Dict[str, Any]]:
        """Perform vector search with metadata filtering."""
        if not query_embeddings:
            return []
            
        session = self.Session()
        try:
            # Initialize results
            results = {}
            
            # Process each model's query embeddings
            for model_name, query_embedding in query_embeddings.items():
                # For PostgreSQL, we need to convert the embedding to a list
                embedding_list = list(query_embedding)
                
                try:
                    # Construct SQL query using pgvector's <=> operator (cosine distance)
                    query = f"""
                    SELECT 
                        nc.id,
                        nc.raw_text,
                        cm.season,
                        cm.episode,
                        cm.scene,
                        1 - (chunk_embeddings.embedding <=> :embedding) AS score
                    FROM 
                        chunk_embeddings
                    JOIN 
                        narrative_chunks nc ON chunk_embeddings.chunk_id = nc.id
                    JOIN 
                        chunk_metadata cm ON nc.id = cm.chunk_id
                    WHERE 
                        chunk_embeddings.model = :model_name
                        AND chunk_embeddings.dimensions = :dimensions
                    """
                    
                    # Add filters
                    params = {
                        "embedding": embedding_list,
                        "model_name": model_name,
                        "dimensions": len(query_embedding)
                    }
                    
                    if filters:
                        if "season" in filters:
                            query += " AND cm.season = :season"
                            params["season"] = filters["season"]
                            
                        if "episode" in filters:
                            query += " AND cm.episode = :episode"
                            params["episode"] = filters["episode"]
                            
                        if "characters" in filters and filters["characters"]:
                            # For JSON array containment
                            characters_json = json.dumps(filters["characters"])
                            query += " AND cm.characters::jsonb ?| :characters"
                            params["characters"] = characters_json
                    
                    # Order by similarity score and limit
                    query += f" ORDER BY score DESC LIMIT {k}"
                    
                    # Execute query
                    result_proxy = session.execute(text(query), params)
                    model_results = [dict(row) for row in result_proxy]
                    
                    # Add to combined results
                    for row in model_results:
                        chunk_id = str(row["id"])
                        if chunk_id not in results:
                            results[chunk_id] = {
                                "chunk_id": chunk_id,
                                "text": row["raw_text"],
                                "metadata": {
                                    "season": row["season"],
                                    "episode": row["episode"],
                                    "scene": row["scene"]
                                },
                                "model_scores": {},
                                "score": 0.0
                            }
                        
                        # Store score from this model
                        results[chunk_id]["model_scores"][model_name] = float(row["score"])
                        
                except Exception as e:
                    logger.error(f"Error in vector search with model {model_name}: {e}")
            
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
            
            # Sort by final score and return top k
            sorted_results = sorted(results.values(), key=lambda x: x['score'], reverse=True)
            return sorted_results[:k]
            
        except Exception as e:
            logger.error(f"Error in vector search: {e}")
            return []
            
        finally:
            session.close()
    
    def _synthesize_results(self, 
                          all_results: Dict[str, List[Dict[str, Any]]], 
                          query_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Synthesize results from multiple sources into unified response.
        
        Args:
            all_results: Results from different memory tiers
            query_info: Information about the query
            
        Returns:
            Combined and ranked list of results
        """
        # Combine all results into a single list
        combined_results = []
        
        for tier, tier_results in all_results.items():
            # Add tier info to each result
            for result in tier_results:
                result["tier"] = tier
                combined_results.append(result)
                
        # Check if we need to do cross-referencing
        if len(all_results) > 1:
            # Do cross-referencing between structured data and narrative chunks
            self._cross_reference_results(combined_results, query_info)
            
        # Sort by score
        combined_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        # Apply any boosts based on query type
        query_type = query_info.get("type", "narrative")
        if query_type in self.query_types:
            boost_info = self.query_types[query_type]
            for result in combined_results:
                # Boost results from primary tier
                if "primary_tier" in boost_info and result.get("tier") == boost_info["primary_tier"]:
                    result["score"] = result.get("score", 0) * 1.2
                    
        # Re-sort after boosts
        combined_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return combined_results
    
    def _cross_reference_results(self, results: List[Dict[str, Any]], query_info: Dict[str, Any]]) -> None:
        """
        Cross-reference between entity data and narrative chunks.
        Modifies results list in place.
        
        Args:
            results: Combined results list
            query_info: Information about the query
        """
        # Extract entity names from results
        entities = set()
        entity_results = {}
        
        for result in results:
            # Extract entities from structured data results
            if result.get("source") == "characters":
                entities.add(result.get("name", ""))
                entity_results[result.get("name", "")] = result
                
            elif result.get("source") == "places":
                entities.add(result.get("name", ""))
                entity_results[result.get("name", "")] = result
                
            # Extract entities from narrative chunk metadata
            if "metadata" in result and "characters" in result["metadata"]:
                if isinstance(result["metadata"]["characters"], list):
                    for character in result["metadata"]["characters"]:
                        entities.add(character)
                elif isinstance(result["metadata"]["characters"], str):
                    try:
                        characters = json.loads(result["metadata"]["characters"])
                        if isinstance(characters, list):
                            for character in characters:
                                entities.add(character)
                    except:
                        pass
        
        # For each narrative chunk result, boost score if it mentions relevant entities
        for result in results:
            if "text" in result:
                # Check for entity mentions in text
                mentions = 0
                for entity in entities:
                    if entity and entity in result["text"]:
                        mentions += 1
                
                # Boost score based on mentions
                if mentions > 0:
                    result["score"] = result.get("score", 0) * (1 + (mentions * 0.05))
                    
                    # Add entity references if not already present
                    if "metadata" not in result:
                        result["metadata"] = {}
                    
                    if "referenced_entities" not in result["metadata"]:
                        result["metadata"]["referenced_entities"] = []
                        
                    for entity in entities:
                        if entity and entity in result["text"] and entity not in result["metadata"]["referenced_entities"]:
                            result["metadata"]["referenced_entities"].append(entity)
    
    def _extract_character_names_from_query(self, query: str) -> List[str]:
        """Extract character names from query string."""
        # This is a basic implementation - could be replaced with NER
        character_names = []
        
        # Basic list of known characters
        known_characters = ["Alex", "Emilia", "Victor", "Zoe", "Max", "Raven", "Dr. Nyati", "Alina", "Pete"]
        
        for char in known_characters:
            if char in query:
                character_names.append(char)
                
        # Try database lookup for completeness
        session = self.Session()
        try:
            # Get all character names
            db_characters = session.query(Character.name).all()
            for char in db_characters:
                if char[0] not in character_names and char[0] in query:
                    character_names.append(char[0])
        except Exception as e:
            logger.warning(f"Character database lookup failed: {e}")
        finally:
            session.close()
                
        return character_names
    
    def _extract_place_names_from_query(self, query: str) -> List[str]:
        """Extract place names from query string."""
        # This is a basic implementation - could be replaced with NER
        place_names = []
        
        # Basic list of known places
        known_places = ["Night City", "Corporate Spires", "The Underbelly", "Combat Zone", "Neon Bay", "The Wastes"]
        
        for place in known_places:
            if place in query:
                place_names.append(place)
                
        # Try database lookup for completeness
        session = self.Session()
        try:
            # Get all place names
            db_places = session.query(Place.name).all()
            for place in db_places:
                if place[0] not in place_names and place[0] in query:
                    place_names.append(place[0])
        except Exception as e:
            logger.warning(f"Place database lookup failed: {e}")
        finally:
            session.close()
                
        return place_names
    
    def _extract_themes_from_query(self, query: str) -> List[str]:
        """Extract themes from query string."""
        # This is a basic implementation
        themes = []
        
        # Check for common themes
        theme_keywords = {
            "transhumanism": ["transhuman", "posthuman", "augmentation", "cyborg", "enhancement", "evolution"],
            "identity": ["identity", "self", "personhood", "consciousness", "who am I", "who we are"],
            "power": ["power", "control", "authority", "dominance", "manipulation", "influence"],
            "corruption": ["corruption", "greed", "decay", "moral decay", "ethical failure"],
            "dystopia": ["dystopia", "dystopian", "oppression", "surveillance", "totalitarian"],
            "technology": ["technology", "tech", "ai", "artificial intelligence", "machine", "digital"]
        }
        
        for theme, keywords in theme_keywords.items():
            # Check if any keywords appear in the query
            if any(keyword in query.lower() for keyword in keywords):
                themes.append(theme)
                
        return themes
    
    def _extract_events_from_query(self, query: str) -> List[str]:
        """Extract event references from query string."""
        # This is a basic implementation
        events = []
        
        # Check for event patterns
        event_patterns = [
            r"(\w+)\s+incident",
            r"(\w+)\s+attack",
            r"(\w+)\s+heist",
            r"battle\s+of\s+(\w+)",
            r"war\s+of\s+(\w+)",
            r"(\w+)\s+revolution",
            r"(\w+)\s+uprising",
            r"(\w+)\s+mission",
            r"operation\s+(\w+)"
        ]
        
        for pattern in event_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            events.extend(matches)
                
        return events
    
    def process_deep_query(self, query: str, query_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a deep narrative query requiring synthesis across multiple sources.
        
        Args:
            query: The narrative query to process
            query_type: Type of query (character, event, theme, relationship)
            
        Returns:
            Dict containing synthesized response and supporting evidence
        """
        # Start by performing standard query to gather evidence
        query_results = self.query_memory(query, query_type)
        
        # Extract top results to use as evidence
        evidence = []
        for i, result in enumerate(query_results["results"][:5]):  # Use top 5 results
            if "text" in result:
                evidence.append(f"Evidence #{i+1}: {result['text']}")
            elif "summary" in result:
                evidence.append(f"Evidence #{i+1}: {result['name']} - {result['summary']}")
                
        # Use local LLM to synthesize a response
        synthesized_response = self._synthesize_response(query, evidence, query_type)
        
        return {
            "query": query,
            "query_type": query_results["query_type"],
            "response": synthesized_response,
            "supporting_evidence": query_results["results"][:5],  # Top 5 for brevity
            "metadata": query_results["metadata"]
        }
    
    def _synthesize_response(self, query: str, evidence: List[str], query_type: Optional[str] = None) -> str:
        """
        Generate synthesized narrative response using local LLM.
        
        Args:
            query: User's query
            evidence: List of evidence snippets to use
            query_type: Type of query
            
        Returns:
            Synthesized response
        """
        # Create prompt for response synthesis
        prompt = f"""You are a narrative intelligence assistant tasked with answering questions about a cyberpunk story world.

USER QUERY: {query}

Here is the evidence retrieved from the narrative database:

{chr(10).join(evidence)}

Based ONLY on the evidence provided above, craft a comprehensive, accurate response to the user's query.
Your response should:
1. Directly address the user's question
2. Draw only from the evidence provided (do not invent details not present in the evidence)
3. Synthesize information from multiple evidence points when relevant
4. Acknowledge any ambiguities or gaps in the evidence
5. Maintain the serious, noir-like tone of the cyberpunk narrative

IMPORTANT: If the evidence doesn't contain information needed to answer the query, simply state that there isn't enough information available rather than inventing details.

Your response:
"""
        
        # Query LLM for synthesis
        try:
            response = self._query_llm(prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"Response synthesis failed: {e}")
            # Create a simple fallback response
            return f"I've found some potentially relevant information, but couldn't synthesize a complete answer. Here's the raw evidence:\n\n{chr(10).join(evidence)}"
    
    def _query_llm(self, prompt: str) -> str:
        """Query the local LLM with the prompt."""
        try:
            import requests
            import json
            
            logger.info(f"Querying local LLM using model ID: {self.model_id}")
            
            # Try LM Studio API first
            try:
                # Try completions endpoint
                api_url = "http://localhost:1234/v1/completions"
                
                # Create completions payload
                payload = {
                    "model": self.model_id,
                    "prompt": prompt,
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "max_tokens": 1024,
                    "stream": False
                }
                
                logger.debug("Sending request to completions endpoint")
                headers = {"Content-Type": "application/json"}
                
                response = requests.post(api_url, json=payload, headers=headers, timeout=60)
                
                if response.status_code == 200:
                    logger.debug("Successful connection to completions endpoint")
                    response_data = response.json()
                    
                    # Process response from completions endpoint
                    if "choices" in response_data and len(response_data["choices"]) > 0:
                        if "text" in response_data["choices"][0]:
                            return response_data["choices"][0]["text"]
                    
                    # If we got here, we had a 200 but didn't recognize the format
                    logger.warning(f"Unexpected response format: {response_data}")
                else:
                    logger.warning(f"LLM endpoint returned status code: {response.status_code}")
                    
                    # Try chat completions endpoint as fallback
                    logger.debug("Trying chat completions endpoint")
                    api_url = "http://localhost:1234/v1/chat/completions"
                    
                    chat_payload = {
                        "model": self.model_id,
                        "messages": [
                            {"role": "system", "content": "You are a narrative intelligence assistant."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "max_tokens": 1024,
                        "stream": False
                    }
                    
                    response = requests.post(api_url, json=chat_payload, headers=headers, timeout=60)
                    
                    if response.status_code == 200:
                        logger.debug("Successful connection to chat completions endpoint")
                        response_data = response.json()
                        
                        if "choices" in response_data and len(response_data["choices"]) > 0:
                            if "message" in response_data["choices"][0]:
                                return response_data["choices"][0]["message"]["content"]
                        
                        logger.warning(f"Unexpected response format from chat endpoint: {response_data}")
                    else:
                        logger.warning(f"Chat completions endpoint returned status code: {response.status_code}")
                
            except Exception as api_error:
                logger.error(f"LLM API approach failed: {str(api_error)}")
            
            # Mock response for testing
            logger.warning("Using mock LLM response for testing")
            return f"This is a mock response. In a fully implemented system, I would analyze the evidence and provide a nuanced answer about the narrative."
            
        except Exception as e:
            logger.error(f"Error in LLM query: {str(e)}")
            return "Error: Unable to query local LLM."
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get status information about the MEMNON system.
        
        Returns:
            Dict with status information
        """
        try:
            session = self.Session()
            
            # Get database counts
            narrative_chunks_count = session.query(sa.func.count(NarrativeChunk.id)).scalar() or 0
            
            # Count embeddings by model
            embedding_counts = {}
            for model_key in self.embedding_models.keys():
                count = session.query(sa.func.count(ChunkEmbedding.id))\
                    .filter(ChunkEmbedding.model == model_key)\
                    .scalar() or 0
                embedding_counts[model_key] = count
                
            # Count total embeddings
            total_embeddings = session.query(sa.func.count(ChunkEmbedding.id)).scalar() or 0
            
            # Count entities
            character_count = session.query(sa.func.count(Character.id)).scalar() or 0
            place_count = session.query(sa.func.count(Place.id)).scalar() or 0
            
            # Get embedding models info
            embedding_models_info = {
                model_name: str(type(model_obj).__name__)
                for model_name, model_obj in self.embedding_models.items()
            }
            
            status = {
                "database": self.db_url,
                "narrative_chunks": narrative_chunks_count,
                "total_embeddings": total_embeddings,
                "embeddings_by_model": embedding_counts,
                "characters": character_count,
                "places": place_count,
                "embedding_models": embedding_models_info,
                "llm_model_id": self.model_id
            }
            
            session.close()
            return status
            
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {"error": str(e)}
            
    def interactive_mode(self):
        """
        Start interactive mode for continuous queries.
        """
        print("\n===== MEMNON Unified Memory Access System =====")
        print("Type 'quit', 'exit', or Ctrl+C to exit")
        print("Type 'status' to see system status")
        print("Type 'help' for more options")
        print("================================================\n")
        
        try:
            while True:
                query = input("\nQuery: ").strip()
                
                if query.lower() in ('quit', 'exit'):
                    break
                    
                elif query.lower() == 'status':
                    # Show status
                    status = self.get_status()
                    print("\n=== MEMNON Status ===")
                    for key, value in status.items():
                        if isinstance(value, dict):
                            print(f"{key}:")
                            for subkey, subvalue in value.items():
                                print(f"  {subkey}: {subvalue}")
                        else:
                            print(f"{key}: {value}")
                            
                elif query.lower() == 'help':
                    print("\n=== MEMNON Help ===")
                    print("Available commands:")
                    print("  status - Show system status")
                    print("  help - Show this help message")
                    print("  exit/quit - Exit interactive mode")
                    print("\nQuery examples:")
                    print("  What happened to Alex in Season 2?")
                    print("  Tell me about Emilia's personality")
                    print("  What are major events in Night City?")
                    print("  Where is Corporate Spires located?")
                    
                elif not query:
                    continue
                    
                else:
                    # Process query
                    print("\nProcessing query...")
                    start_time = time.time()
                    
                    # Use deep query processing for better responses
                    result = self.process_deep_query(query)
                    
                    # Print response
                    print("\n=== Response ===")
                    print(result["response"])
                    
                    # Print query time
                    elapsed = time.time() - start_time
                    print(f"\n[Query processed in {elapsed:.2f} seconds]")
                    
        except KeyboardInterrupt:
            print("\nExiting interactive mode.")
        
        print("MEMNON session ended.")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="MEMNON - Unified Memory Access System")
    
    # Query options
    query_group = parser.add_mutually_exclusive_group()
    query_group.add_argument("--interactive", action="store_true", help="Start interactive mode")
    query_group.add_argument("--query", type=str, help="One-off query to execute")
    query_group.add_argument("--status", action="store_true", help="Display system status")
    
    # Query parameters
    parser.add_argument("--query-type", type=str, choices=["character", "location", "event", "theme", "relationship", "narrative"],
                      help="Type of query to execute")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results to return")
    
    # Database and model settings
    parser.add_argument("--db-url", type=str, help="Database URL to connect to")
    parser.add_argument("--model-id", type=str, default=DEFAULT_MODEL_ID, help="LM Studio model ID to use")
    parser.add_argument("--model-path", type=str, help="Path to local model file (fallback)")
    
    # Debug flag
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    return parser.parse_args()


def main():
    """Main function."""
    args = parse_arguments()
    
    try:
        # Initialize MEMNON
        memnon = MEMNON(
            db_url=args.db_url,
            model_id=args.model_id,
            model_path=args.model_path,
            debug=args.debug
        )
        
        # Execute actions based on arguments
        if args.interactive:
            memnon.interactive_mode()
            
        elif args.query:
            # Process one-off query
            result = memnon.process_deep_query(args.query, args.query_type)
            print("\n=== Response ===")
            print(result["response"])
            print("\n=== Supporting Evidence ===")
            for i, evidence in enumerate(result["supporting_evidence"]):
                if "text" in evidence:
                    text = evidence["text"]
                    if len(text) > 200:
                        text = text[:197] + "..."
                    print(f"{i+1}. {text}")
                elif "name" in evidence:
                    print(f"{i+1}. {evidence['name']}: {evidence.get('summary', '')}")
            
        elif args.status:
            # Display system status
            status = memnon.get_status()
            print("\n=== MEMNON Status ===")
            for key, value in status.items():
                if isinstance(value, dict):
                    print(f"{key}:")
                    for subkey, subvalue in value.items():
                        print(f"  {subkey}: {subvalue}")
                else:
                    print(f"{key}: {value}")
            
        else:
            # No action specified, show help
            print("No action specified. Use --interactive, --query, or --status.")
            print("Run with --help for more information.")
            
    except Exception as e:
        print(f"Error: {e}")
        logger.error(f"Error in main function: {e}")
        return 1
        
    return 0


if __name__ == "__main__":
    sys.exit(main())