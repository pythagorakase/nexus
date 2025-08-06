#!/usr/bin/env python3
"""
db_chroma.py: ChromaDB Vector Database Access Module for Night City Stories

This module provides a consolidated interface for all vector database operations,
including multi-model embedding generation, semantic search, and metadata filtering.
It implements the triple-embedding approach (BGE-Large, E5-Large, BGE-Small) for
improved semantic retrieval quality.

Usage:
    import db_chroma as vdb
    results = vdb.query_by_text("What happened with Alex in the Neon Bay?")
    
    # Or run standalone with --test flag to validate functionality
    python db_chroma.py --test
"""

import os
import re
import json
import time
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any, Set

import chromadb
from sentence_transformers import SentenceTransformer

# Import configuration manager
try:
    import config_manager as config
except ImportError:
    # Fallback if config_manager is not available
    config = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("db_chroma.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("db_chroma")

# Default settings (can be overridden by config_manager or settings.json)
DEFAULT_SETTINGS = {
    "chroma_path": "./chroma_db",
    "collections": {
        "primary": "transcripts",
        "bge_large": "transcripts_bge_large",
        "e5_large": "transcripts_e5_large", 
        "bge_small": "transcripts_bge_small"
    },
    "embedding_models": {
        "bge_large": {
            "name": "BAAI/bge-large-en",
            "weight": 0.4
        },
        "e5_large": {
            "name": "intfloat/e5-large-v2",
            "weight": 0.4
        },
        "bge_small": {
            "name": "BAAI/bge-small-en",
            "weight": 0.2
        }
    },
    "query_options": {
        "top_k": 10,
        "min_score_threshold": 0.25,
        "multi_model": True,
        "use_weights": True,
        "similarity_boost": 0.1  # Boost for chunks found by multiple models
    },
    "chunk_marker_regex": r'<!--\s*SCENE BREAK:\s*(S\d+E\d+)_([\d]{3})',
    "verbose_logging": False
}

# Global variables
settings = {}
collections = {}
embedding_models = {}
chroma_client = None

class ChromaDBError(Exception):
    """Base exception for ChromaDB-related errors"""
    pass

class ConnectionError(ChromaDBError):
    """Exception for database connection errors"""
    pass

class QueryError(ChromaDBError):
    """Exception for query execution errors"""
    pass

class ModelLoadError(ChromaDBError):
    """Exception for model loading errors"""
    pass

def load_settings() -> Dict[str, Any]:
    """
    Load settings from config_manager, with fallback to default settings
    
    Returns:
        Dictionary containing settings
    """
    global settings
    
    # Start with default settings
    settings = DEFAULT_SETTINGS.copy()
    
    try:
        # Try to load from config_manager if available
        if config:
            chromadb_config = config.get_section("chromadb")
            if chromadb_config:
                # Update settings with config_manager values
                if "path" in chromadb_config:
                    settings["chroma_path"] = chromadb_config["path"]
                
                if "collection_name" in chromadb_config:
                    settings["collections"]["primary"] = chromadb_config["collection_name"]
                
                if "embedding_models" in chromadb_config:
                    settings["embedding_models"].update(chromadb_config["embedding_models"])
                
                if "chunk_marker_regex" in chromadb_config:
                    settings["chunk_marker_regex"] = chromadb_config["chunk_marker_regex"]
                
            settings["verbose_logging"] = config.get("database.verbose_logging", 
                                                 settings["verbose_logging"])
            
            logger.info("Loaded settings from config_manager")
        else:
            # Fallback to settings.json if config_manager is not available
            settings_path = Path("settings.json")
            if settings_path.exists():
                with open(settings_path, "r") as f:
                    file_settings = json.load(f)
                
                # Extract ChromaDB settings if available
                if "chromadb" in file_settings:
                    chromadb_settings = file_settings["chromadb"]
                    
                    # Update settings with file values
                    if "path" in chromadb_settings:
                        settings["chroma_path"] = chromadb_settings["path"]
                    
                    if "collection_name" in chromadb_settings:
                        settings["collections"]["primary"] = chromadb_settings["collection_name"]
                    
                    if "embedding_models" in chromadb_settings:
                        settings["embedding_models"].update(chromadb_settings["embedding_models"])
                    
                    if "chunk_marker_regex" in chromadb_settings:
                        settings["chunk_marker_regex"] = chromadb_settings["chunk_marker_regex"]
                
                logger.info(f"Loaded settings from {settings_path}")
    
    except Exception as e:
        logger.error(f"Error loading settings: {e}. Using default settings.")
    
    return settings

def initialize_client() -> chromadb.PersistentClient:
    """
    Initialize ChromaDB client
    
    Returns:
        ChromaDB PersistentClient instance
        
    Raises:
        ConnectionError: If the ChromaDB client initialization fails
    """
    global chroma_client
    
    if chroma_client:
        return chroma_client
    
    try:
        chroma_path = Path(settings["chroma_path"])
        
        # Create the directory if it doesn't exist
        chroma_path.mkdir(parents=True, exist_ok=True)
        
        chroma_client = chromadb.PersistentClient(path=str(chroma_path))
        logger.info(f"Initialized ChromaDB client at {chroma_path}")
        
        return chroma_client
    
    except Exception as e:
        error_msg = f"Failed to initialize ChromaDB client: {e}"
        logger.error(error_msg)
        raise ConnectionError(error_msg)

def get_collection(collection_name: str, create_if_missing: bool = True) -> chromadb.Collection:
    """
    Get a ChromaDB collection by name
    
    Args:
        collection_name: Name of the collection
        create_if_missing: Whether to create the collection if it doesn't exist
        
    Returns:
        ChromaDB Collection instance
        
    Raises:
        ConnectionError: If the collection cannot be accessed
    """
    global collections
    
    # Return cached collection if available
    if collection_name in collections:
        return collections[collection_name]
    
    # Ensure client is initialized
    client = initialize_client()
    
    try:
        # Get or create the collection
        if create_if_missing:
            collection = client.get_or_create_collection(name=collection_name)
        else:
            collection = client.get_collection(name=collection_name)
        
        # Cache the collection
        collections[collection_name] = collection
        
        return collection
    
    except Exception as e:
        error_msg = f"Failed to access collection {collection_name}: {e}"
        logger.error(error_msg)
        raise ConnectionError(error_msg)

def load_embedding_model(model_key: str) -> SentenceTransformer:
    """
    Load an embedding model by key
    
    Args:
        model_key: Key of the model in settings["embedding_models"]
        
    Returns:
        SentenceTransformer model
        
    Raises:
        ModelLoadError: If the model fails to load
    """
    global embedding_models
    
    # Return cached model if available
    if model_key in embedding_models:
        return embedding_models[model_key]
    
    try:
        # Get model name from settings
        model_name = settings["embedding_models"][model_key]["name"]
        
        logger.info(f"Loading embedding model: {model_name}")
        model = SentenceTransformer(model_name)
        
        # Cache the model
        embedding_models[model_key] = model
        
        return model
    
    except Exception as e:
        error_msg = f"Failed to load embedding model {model_key}: {e}"
        logger.error(error_msg)
        raise ModelLoadError(error_msg)

def generate_embedding(text: str, model_key: str = "bge_large") -> List[float]:
    """
    Generate an embedding for the given text
    
    Args:
        text: Text to embed
        model_key: Key of the model to use
        
    Returns:
        Embedding as a list of floats
        
    Raises:
        ModelLoadError: If the model fails to load
    """
    # Load the model
    model = load_embedding_model(model_key)
    
    # Generate the embedding
    embedding = model.encode(text).tolist()
    
    return embedding

def add_chunk(chunk_id: str, chunk_text: str, metadata: Dict[str, Any] = None) -> bool:
    """
    Add a chunk to all embedding collections
    
    Args:
        chunk_id: ID of the chunk
        chunk_text: Text content of the chunk
        metadata: Optional metadata for the chunk
        
    Returns:
        True if the chunk was added successfully, False otherwise
    """
    if not metadata:
        metadata = {}
    
    # Extract episode and chunk number from chunk_id
    parts = chunk_id.split('_')
    if len(parts) >= 2:
        metadata["episode"] = parts[0]
        metadata["chunk_number"] = int(parts[1]) if parts[1].isdigit() else None
    
    # Add character count to metadata
    metadata["char_count"] = len(chunk_text)
    
    # Ensure chunk_id and text are in metadata
    metadata["chunk_id"] = chunk_id
    metadata["text"] = chunk_text  # Redundant storage for easier debugging
    
    # Generate embeddings for each model
    try:
        embeddings = {}
        for model_key in settings["embedding_models"].keys():
            embeddings[model_key] = generate_embedding(chunk_text, model_key)
        
        # Add to each collection
        for model_key, embedding in embeddings.items():
            collection_name = settings["collections"].get(model_key, f"transcripts_{model_key}")
            collection = get_collection(collection_name)
            
            collection.add(
                ids=[chunk_id],
                embeddings=[embedding],
                metadatas=[metadata],
                documents=[chunk_text]
            )
        
        logger.info(f"Added chunk {chunk_id} to all collections")
        return True
    
    except Exception as e:
        logger.error(f"Error adding chunk {chunk_id}: {e}")
        return False

def update_chunk_metadata(chunk_id: str, metadata: Dict[str, Any]) -> bool:
    """
    Update metadata for a chunk across all collections
    
    Args:
        chunk_id: ID of the chunk
        metadata: New metadata for the chunk
        
    Returns:
        True if the metadata was updated successfully, False otherwise
    """
    try:
        # Update in each collection
        for model_key in settings["embedding_models"].keys():
            collection_name = settings["collections"].get(model_key, f"transcripts_{model_key}")
            collection = get_collection(collection_name)
            
            # Get current metadata first
            result = collection.get(ids=[chunk_id], include=["metadatas"])
            
            if result and result["ids"] and len(result["ids"]) > 0:
                current_metadata = result["metadatas"][0]
                
                # Merge with new metadata
                merged_metadata = {**current_metadata, **metadata}
                
                # Update the metadata
                collection.update(
                    ids=[chunk_id],
                    metadatas=[merged_metadata]
                )
        
        logger.info(f"Updated metadata for chunk {chunk_id}")
        return True
    
    except Exception as e:
        logger.error(f"Error updating metadata for chunk {chunk_id}: {e}")
        return False

def query_by_text(query_text: str, 
                 filters: Dict[str, Any] = None,
                 top_k: int = None,
                 multi_model: bool = None,
                 model_weights: Dict[str, float] = None) -> List[Dict[str, Any]]:
    """
    Query collections by text using multi-model approach
    
    Args:
        query_text: Query text
        filters: Optional metadata filters
        top_k: Maximum number of results to return
        multi_model: Whether to use multiple embedding models
        model_weights: Custom weights for each model
        
    Returns:
        List of result dictionaries with keys:
        chunk_id, text, score, metadata, model_scores
    """
    # Set default values from settings if not provided
    if top_k is None:
        top_k = settings["query_options"]["top_k"]
    
    if multi_model is None:
        multi_model = settings["query_options"]["multi_model"]
    
    if not model_weights and settings["query_options"]["use_weights"]:
        model_weights = {model: config["weight"] 
                        for model, config in settings["embedding_models"].items()}
    
    # If multi_model is False, use just the primary model (bge_large by default)
    if not multi_model:
        return _query_single_model("bge_large", query_text, filters, top_k)
    
    # Use multi-model approach
    return _query_multi_model(query_text, filters, top_k, model_weights)

def _query_single_model(model_key: str, 
                       query_text: str,
                       filters: Dict[str, Any] = None,
                       top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Query a single embedding collection
    
    Args:
        model_key: Key of the model to use
        query_text: Query text
        filters: Optional metadata filters
        top_k: Maximum number of results to return
        
    Returns:
        List of result dictionaries
    """
    try:
        # Generate query embedding
        query_embedding = generate_embedding(query_text, model_key)
        
        # Get collection
        collection_name = settings["collections"].get(model_key, f"transcripts_{model_key}")
        collection = get_collection(collection_name)
        
        # Prepare filter structure for ChromaDB
        where = {}
        if filters:
            for key, value in filters.items():
                where[key] = value
        
        # Execute query
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where if where else None,
            include=["documents", "metadatas", "distances"]
        )
        
        # Process results
        processed_results = []
        if results["ids"] and len(results["ids"][0]) > 0:
            for i in range(len(results["ids"][0])):
                chunk_id = results["ids"][0][i]
                document = results["documents"][0][i]
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i]
                
                # Convert distance to similarity score (1.0 is perfect match)
                score = 1.0 - min(distance, 1.0)
                
                # Skip results below threshold
                if score < settings["query_options"]["min_score_threshold"]:
                    continue
                
                processed_results.append({
                    "chunk_id": chunk_id,
                    "text": document,
                    "score": score,
                    "metadata": metadata,
                    "model_scores": {model_key: score}
                })
        
        return processed_results
    
    except Exception as e:
        logger.error(f"Error querying with model {model_key}: {e}")
        return []

def _query_multi_model(query_text: str,
                      filters: Dict[str, Any] = None,
                      top_k: int = 10,
                      model_weights: Dict[str, float] = None) -> List[Dict[str, Any]]:
    """
    Query multiple embedding collections and combine results
    
    Args:
        query_text: Query text
        filters: Optional metadata filters
        top_k: Maximum number of results to return
        model_weights: Weights for each model
        
    Returns:
        List of result dictionaries
    """
    if not model_weights:
        model_weights = {model: config["weight"] 
                        for model, config in settings["embedding_models"].items()}
    
    # Query each model
    all_results = {}
    for model_key in model_weights.keys():
        model_results = _query_single_model(
            model_key,
            query_text,
            filters,
            top_k * 2  # Get more results to improve diversity
        )
        
        # Store results by chunk_id
        for result in model_results:
            chunk_id = result["chunk_id"]
            if chunk_id not in all_results:
                all_results[chunk_id] = result
                all_results[chunk_id]["model_scores"] = {}
                all_results[chunk_id]["seen_in"] = []
            
            # Store the score from this model
            all_results[chunk_id]["model_scores"][model_key] = result["score"]
            all_results[chunk_id]["seen_in"].append(model_key)
    
    # Calculate weighted scores
    for chunk_id, result in all_results.items():
        weighted_score = 0.0
        score_count = 0
        
        for model_key, weight in model_weights.items():
            if model_key in result["model_scores"]:
                weighted_score += result["model_scores"][model_key] * weight
                score_count += 1
        
        # Apply consensus bonus for results found by multiple models
        consensus_bonus = (len(result["seen_in"]) / len(model_weights)) * settings["query_options"]["similarity_boost"]
        
        # Calculate final score
        if score_count > 0:
            result["score"] = (weighted_score / sum(weight for model_key, weight in model_weights.items() 
                                                  if model_key in result["model_scores"])) + consensus_bonus
        else:
            result["score"] = 0.0
    
    # Sort by score and limit to top_k
    sorted_results = sorted(all_results.values(), key=lambda x: x["score"], reverse=True)
    return sorted_results[:top_k]

def query_by_chunk_id(chunk_id: str,
                     find_similar: bool = True,
                     top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Query by chunk ID, optionally finding similar chunks
    
    Args:
        chunk_id: ID of the chunk
        find_similar: Whether to find similar chunks
        top_k: Maximum number of similar chunks to return
        
    Returns:
        List of result dictionaries
    """
    try:
        # Get the primary collection
        collection_name = settings["collections"].get("bge_large", "transcripts_bge_large")
        collection = get_collection(collection_name)
        
        # Get the chunk
        result = collection.get(ids=[chunk_id], include=["documents", "metadatas", "embeddings"])
        
        if not result or not result["ids"] or len(result["ids"]) == 0:
            logger.warning(f"Chunk {chunk_id} not found")
            return []
        
        # Create a result for the requested chunk
        chunk_result = {
            "chunk_id": chunk_id,
            "text": result["documents"][0],
            "score": 1.0,  # Perfect match
            "metadata": result["metadatas"][0],
            "model_scores": {"exact_match": 1.0}
        }
        
        if not find_similar:
            return [chunk_result]
        
        # Find similar chunks using the embedding
        embedding = result["embeddings"][0]
        
        similar_results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k + 1,  # +1 to account for the query chunk itself
            include=["documents", "metadatas", "distances"]
        )
        
        # Process results
        processed_results = [chunk_result]  # Start with the requested chunk
        
        if similar_results["ids"] and len(similar_results["ids"][0]) > 0:
            for i in range(len(similar_results["ids"][0])):
                similar_id = similar_results["ids"][0][i]
                
                # Skip the original chunk
                if similar_id == chunk_id:
                    continue
                
                document = similar_results["documents"][0][i]
                metadata = similar_results["metadatas"][0][i]
                distance = similar_results["distances"][0][i]
                
                # Convert distance to similarity score
                score = 1.0 - min(distance, 1.0)
                
                processed_results.append({
                    "chunk_id": similar_id,
                    "text": document,
                    "score": score,
                    "metadata": metadata,
                    "model_scores": {"similarity": score}
                })
            
            # Limit to top_k similar chunks (plus the original)
            if len(processed_results) > top_k + 1:
                processed_results = processed_results[:top_k + 1]
        
        return processed_results
    
    except Exception as e:
        logger.error(f"Error querying by chunk ID {chunk_id}: {e}")
        return []

def get_all_chunk_ids(collection_name: str = None) -> List[str]:
    """
    Get all chunk IDs from a collection
    
    Args:
        collection_name: Name of the collection (defaults to primary collection)
        
    Returns:
        List of chunk IDs
    """
    if not collection_name:
        collection_name = settings["collections"].get("bge_large", "transcripts_bge_large")
    
    try:
        collection = get_collection(collection_name)
        
        # Get all IDs
        result = collection.get(include=[])
        
        if result and result["ids"]:
            return result["ids"]
        
        return []
    
    except Exception as e:
        logger.error(f"Error getting chunk IDs from collection {collection_name}: {e}")
        return []

def extract_episode_from_chunk_id(chunk_id: str) -> Optional[str]:
    """
    Extract episode from chunk ID (e.g., 'S01E05_123' -> 'S01E05')
    
    Args:
        chunk_id: ID of the chunk
        
    Returns:
        Episode string or None if not extractable
    """
    parts = chunk_id.split('_')
    if len(parts) >= 1:
        episode_pattern = r'S\d+E\d+'
        if re.match(episode_pattern, parts[0]):
            return parts[0]
    
    return None

def extract_chunk_id_from_text(text: str) -> Optional[str]:
    """
    Extract chunk ID from text using the configured regex pattern
    
    Args:
        text: Text to extract from
        
    Returns:
        Chunk ID or None if not found
    """
    pattern = settings["chunk_marker_regex"]
    match = re.search(pattern, text)
    
    if match:
        episode = match.group(1)  # e.g., "S03E11"
        chunk_number = match.group(2)  # e.g., "037"
        return f"{episode}_{chunk_number}"
    
    return None

def get_chunks_by_episode(episode: str) -> List[Dict[str, Any]]:
    """
    Get all chunks for a specific episode
    
    Args:
        episode: Episode identifier (e.g., "S01E05")
        
    Returns:
        List of chunks ordered by chunk number
    """
    try:
        # Query with episode filter
        filters = {"episode": episode}
        
        # Get primary collection
        collection_name = settings["collections"].get("bge_large", "transcripts_bge_large")
        collection = get_collection(collection_name)
        
        # Query collection
        results = collection.get(
            where=filters,
            include=["documents", "metadatas"]
        )
        
        if not results or not results["ids"] or len(results["ids"]) == 0:
            return []
        
        # Process results
        processed_results = []
        for i in range(len(results["ids"])):
            chunk_id = results["ids"][i]
            document = results["documents"][i]
            metadata = results["metadatas"][i]
            
            chunk_number = metadata.get("chunk_number", 0)
            if not chunk_number and "_" in chunk_id:
                # Try to extract from chunk_id
                parts = chunk_id.split("_")
                if len(parts) >= 2 and parts[1].isdigit():
                    chunk_number = int(parts[1])
            
            processed_results.append({
                "chunk_id": chunk_id,
                "text": document,
                "metadata": metadata,
                "chunk_number": chunk_number
            })
        
        # Sort by chunk number
        processed_results.sort(key=lambda x: x["chunk_number"])
        
        return processed_results
    
    except Exception as e:
        logger.error(f"Error getting chunks for episode {episode}: {e}")
        return []

def get_chunk_count() -> Dict[str, int]:
    """
    Get the number of chunks in each collection
    
    Returns:
        Dictionary with collection names and counts
    """
    counts = {}
    
    try:
        for model_key in settings["embedding_models"].keys():
            collection_name = settings["collections"].get(model_key, f"transcripts_{model_key}")
            collection = get_collection(collection_name, create_if_missing=False)
            
            if collection:
                result = collection.get(include=[])
                counts[collection_name] = len(result["ids"]) if result and "ids" in result else 0
            else:
                counts[collection_name] = 0
        
        return counts
    
    except Exception as e:
        logger.error(f"Error getting chunk count: {e}")
        return {}

def run_test(test_data_path: str = None) -> bool:
    """
    Run tests on the ChromaDB module
    
    Args:
        test_data_path: Path to test data directory
        
    Returns:
        True if all tests pass, False otherwise
    """
    # Use a temporary database for testing
    global settings
    
    # Save original settings
    original_settings = settings.copy()
    
    # Set up test settings
    test_settings = settings.copy()
    test_settings["chroma_path"] = "./test_chroma_db"
    test_settings["verbose_logging"] = True
    
    # Use test settings
    settings = test_settings
    
    # Clear global variables for testing
    global collections, embedding_models, chroma_client
    collections = {}
    embedding_models = {}
    chroma_client = None
    
    logger.info("=== Running db_chroma tests ===")
    
    try:
        # Test embedding generation
        logger.info("Testing embedding generation...")
        test_text = "This is a test document about Alex and Night City."
        embedding = generate_embedding(test_text, "bge_large")
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        logger.info(f"✓ Generated embedding with {len(embedding)} dimensions")
        
        # Test adding a chunk
        logger.info("Testing adding chunks...")
        test_chunk_id = "S01E01_001"
        test_chunk_text = """<!-- SCENE BREAK: S01E01_001 (Introduction) -->
        Welcome to Night City. The year is 2097, and you find yourself standing amidst the neon-lit streets,
        the acrid smell of synthetic fuel and street food filling your nostrils. Your name is Alex,
        and this is where your story begins.
        """
        
        success = add_chunk(test_chunk_id, test_chunk_text, {"importance": "high"})
        assert success
        logger.info("✓ Added test chunk successfully")
        
        # Test adding another chunk for similarity testing
        test_chunk_id2 = "S01E01_002"
        test_chunk_text2 = """<!-- SCENE BREAK: S01E01_002 (Meeting Emilia) -->
        As you navigate through the crowded market district, a figure bumps into you.
        "Sorry about that," says a woman with striking blue cybernetic eyes.
        "Name's Emilia. You look lost. First time in Night City?"
        """
        
        success = add_chunk(test_chunk_id2, test_chunk_text2)
        assert success
        logger.info("✓ Added second test chunk successfully")
        
        # Test querying by text
        logger.info("Testing query by text...")
        results = query_by_text("Who is Alex in Night City?", top_k=1)
        assert len(results) > 0
        assert results[0]["chunk_id"] == test_chunk_id
        logger.info(f"✓ Query returned expected chunk with score {results[0]['score']:.4f}")
        
        # Test multi-model querying
        logger.info("Testing multi-model query...")
        multi_results = query_by_text(
            "Who is Emilia with the cybernetic eyes?",
            multi_model=True,
            top_k=1
        )
        assert len(multi_results) > 0
        assert multi_results[0]["chunk_id"] == test_chunk_id2
        assert len(multi_results[0]["model_scores"]) > 0
        logger.info(f"✓ Multi-model query returned expected chunk with model scores: {multi_results[0]['model_scores']}")
        
        # Test querying by chunk ID
        logger.info("Testing query by chunk ID...")
        chunk_results = query_by_chunk_id(test_chunk_id, find_similar=True)
        assert len(chunk_results) > 0
        assert chunk_results[0]["chunk_id"] == test_chunk_id
        similar_count = len(chunk_results) - 1
        logger.info(f"✓ Found original chunk and {similar_count} similar chunks")
        
        # Test updating metadata
        logger.info("Testing metadata update...")
        new_metadata = {"importance": "very high", "theme": "introduction"}
        success = update_chunk_metadata(test_chunk_id, new_metadata)
        assert success
        
        # Verify metadata update
        updated_results = query_by_chunk_id(test_chunk_id, find_similar=False)
        assert len(updated_results) > 0
        assert updated_results[0]["metadata"]["importance"] == "very high"
        assert updated_results[0]["metadata"]["theme"] == "introduction"
        logger.info("✓ Updated and verified metadata")
        
        # Test getting chunks by episode
        logger.info("Testing get chunks by episode...")
        episode_chunks = get_chunks_by_episode("S01E01")
        assert len(episode_chunks) == 2
        episode_chunks.sort(key=lambda x: x["chunk_number"])
        assert episode_chunks[0]["chunk_id"] == test_chunk_id
        assert episode_chunks[1]["chunk_id"] == test_chunk_id2
        logger.info(f"✓ Got {len(episode_chunks)} chunks for episode S01E01")
        
        # Test chunk count
        logger.info("Testing get chunk count...")
        counts = get_chunk_count()
        assert len(counts) > 0
        for collection, count in counts.items():
            if "bge_large" in collection:
                assert count >= 2
            logger.info(f"✓ Collection {collection} has {count} chunks")
        
        logger.info("=== All tests passed! ===")
        return True
        
    except AssertionError as e:
        logger.error(f"Test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
        
    except Exception as e:
        logger.error(f"Error during tests: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
        
    finally:
        # Clean up test database
        try:
            if chroma_client:
                import shutil
                shutil.rmtree(settings["chroma_path"], ignore_errors=True)
        except Exception:
            pass
        
        # Restore original settings
        settings = original_settings
        
        # Reset global variables
        collections = {}
        embedding_models = {}
        chroma_client = None

def main():
    """
    Main entry point for the script when run directly.
    Handles command-line arguments and executes the appropriate functionality.
    """
    parser = argparse.ArgumentParser(description="ChromaDB Vector Database Access Module")
    parser.add_argument("--test", action="store_true", help="Run tests")
    parser.add_argument("--query", help="Query text to search for")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return")
    parser.add_argument("--chunk-id", help="Get a specific chunk by ID")
    parser.add_argument("--episode", help="Get all chunks for a specific episode")
    parser.add_argument("--count", action="store_true", help="Get number of chunks in each collection")
    parser.add_argument("--recent", type=int, default=50, help="Fetch the most recent chunks")
    args = parser.parse_args()
    
    # Load settings
    load_settings()
    
    try:
        if args.test:
            # Run tests
            success = run_test()
            if not success:
                logger.error("Tests failed!")
                return 1
        
        elif args.query:
            # Query by text
            results = query_by_text(args.query, top_k=args.top_k)
            print(f"Found {len(results)} results for query: '{args.query}'")
            for i, result in enumerate(results):
                print(f"\n--- Result {i+1}/{len(results)} (Score: {result['score']:.4f}) ---")
                print(f"Chunk ID: {result['chunk_id']}")
                print(f"Episode: {result['metadata'].get('episode', 'Unknown')}")
                if 'model_scores' in result:
                    print(f"Model Scores: {result['model_scores']}")
                print("\nContent:")
                print(result['text'])
                print("-" * 80)
        
        elif args.chunk_id:
            # Get chunk by ID
            find_similar = True
            results = query_by_chunk_id(args.chunk_id, find_similar=find_similar, top_k=args.top_k)
            
            if not results:
                print(f"Chunk with ID '{args.chunk_id}' not found")
            else:
                print(f"Found chunk and {len(results)-1} similar chunks:")
                for i, result in enumerate(results):
                    if i == 0:
                        print(f"\n--- Requested Chunk (ID: {result['chunk_id']}) ---")
                    else:
                        print(f"\n--- Similar Chunk {i}/{len(results)-1} (Score: {result['score']:.4f}) ---")
                    
                    print(f"Chunk ID: {result['chunk_id']}")
                    print(f"Episode: {result['metadata'].get('episode', 'Unknown')}")
                    print("\nContent:")
                    print(result['text'])
                    print("-" * 80)
        
        elif args.episode:
            # Get chunks by episode
            chunks = get_chunks_by_episode(args.episode)
            print(f"Found {len(chunks)} chunks for episode {args.episode}")
            chunks.sort(key=lambda x: x["chunk_number"])
            
            for i, chunk in enumerate(chunks):
                print(f"\n--- Chunk {i+1}/{len(chunks)} (ID: {chunk['chunk_id']}) ---")
                print(f"Chunk Number: {chunk['chunk_number']}")
                print("\nContent:")
                print(chunk['text'])
                print("-" * 80)
        
        elif args.count:
            # Get chunk count
            counts = get_chunk_count()
            print("Chunk counts by collection:")
            for collection, count in counts.items():
                print(f"  {collection}: {count} chunks")
        
        elif args.recent:
            collection_name = 'transcripts'
            collection = get_collection(collection_name)
            results = collection.get(include=["documents", "metadatas"])

            chunks = []
            for chunk_id, document, metadata in zip(results["ids"], results["documents"], results["metadatas"]):
                chunk_number = metadata.get("chunk_number", 0)
                chunks.append({"chunk_id": chunk_id, "text": document, "metadata": metadata, "chunk_number": chunk_number})

            chunks.sort(key=lambda x: x["chunk_number"], reverse=True)
            recent_chunks = chunks[:args.recent]

            print(json.dumps(recent_chunks, indent=2))
        
        else:
            # No arguments provided, show help
            parser.print_help()
    
    finally:
        # Clean up
        for model in embedding_models.values():
            del model
        
        if chroma_client:
            # ChromaDB has no explicit close method
            pass

if __name__ == "__main__":
    main()
