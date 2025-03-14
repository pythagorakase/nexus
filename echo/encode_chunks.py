#!/usr/bin/env python3
"""
Triple-Embedding ChromaDB Transcript Chunk Encoder with Enhanced Error Handling

This script reads chunked Markdown transcript files, extracts narrative chunks,
and processes each chunk through THREE different embedding models with improved
error handling and fallback mechanisms.
"""

import os
import re
import glob
from pathlib import Path
import chromadb
import logging
import time
import json

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("encoder.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("triple_encoder")

# Fallback import with error handling
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    logger.error("sentence_transformers library not found. Please install it with: pip install sentence-transformers")
    SentenceTransformer = None

# Version tracking for reprocessing capabilities
PROCESSING_VERSION = "1.1.0-triple-robust"

# Embedding model configurations with fallback options
EMBEDDING_MODELS = [
    {
        "name": "BAAI/bge-large-en",
        "fallback": "BAAI/bge-base-en",
        "description": "Primary general-purpose embedding model"
    },
    {
        "name": "intfloat/e5-large-v2",
        "fallback": "intfloat/e5-base-v2",
        "description": "Secondary complementary embedding model"
    },
    {
        "name": "BAAI/bge-small-en",
        "fallback": "BAAI/bge-small-en-v1.5",
        "description": "Foundation model for potential future fine-tuning"
    }
]

def safe_load_model(model_config):
    """
    Safely load an embedding model with fallback mechanism
    
    Args:
        model_config (dict): Configuration for the embedding model
    
    Returns:
        SentenceTransformer or None: Loaded model or None if loading fails
    """
    if SentenceTransformer is None:
        logger.error("SentenceTransformer is not available")
        return None
    
    def attempt_model_load(model_name):
        try:
            logger.info(f"Attempting to load model: {model_name}")
            model = SentenceTransformer(model_name)
            logger.info(f"Successfully loaded model: {model_name}")
            return model
        except Exception as e:
            logger.warning(f"Failed to load model {model_name}: {e}")
            return None
    
    # Try primary model
    model = attempt_model_load(model_config["name"])
    
    # If primary fails, try fallback
    if model is None:
        model = attempt_model_load(model_config["fallback"])
    
    return model

def main():
    """
    Main encoding process with enhanced error handling
    """
    # Initialize ChromaDB client and collections
    try:
        chroma_client = chromadb.PersistentClient(path="./chroma_db")
    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB: {e}")
        return
    
    # Create or get collections for each embedding model
    collections = {}
    try:
        for model_config in EMBEDDING_MODELS:
            collection_name = f"transcripts_{model_config['name'].replace('/', '_')}"
            collections[model_config['name']] = chroma_client.get_or_create_collection(name=collection_name)
        
        # Legacy collection for backward compatibility
        legacy_collection = chroma_client.get_or_create_collection(name="transcripts")
    except Exception as e:
        logger.error(f"Failed to create ChromaDB collections: {e}")
        return
    
    # Load embedding models
    embedding_models = {}
    for model_config in EMBEDDING_MODELS:
        model = safe_load_model(model_config)
        if model:
            embedding_models[model_config['name']] = model
        else:
            logger.warning(f"Skipping model {model_config['name']} due to loading failure")
    
    # Validate we have at least one model
    if not embedding_models:
        logger.error("No embedding models could be loaded. Aborting.")
        return
    
    # Find chunked files
    chunked_files = glob.glob("*_chunked.md")
    if not chunked_files:
        logger.info("No chunked transcript files found.")
        return
    
    # Process each file
    total_chunks_processed = 0
    for file in chunked_files:
        file_path = Path(file)
        logger.info(f"Processing file: {file_path}")
        
        try:
            total_chunks_processed += process_chunked_file(
                file_path, 
                embedding_models, 
                collections, 
                legacy_collection
            )
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
    
    logger.info(f"\n✅ Encoding complete! {total_chunks_processed} chunks stored with triple embeddings.")

def process_chunked_file(file_path, embedding_models, collections, legacy_collection):
    """
    Process a single chunked file with all available embedding models
    
    Args:
        file_path (Path): Path to the chunked markdown file
        embedding_models (dict): Dictionary of loaded embedding models
        collections (dict): Dictionary of ChromaDB collections for each model
        legacy_collection (ChromaDB Collection): Backward compatibility collection
    
    Returns:
        int: Number of chunks processed
    """
    # Regex to match chunk markers
    chunk_marker_regex = re.compile(r'<!--\s*SCENE BREAK:\s*(S\d+E\d+)_([\d]{3})')
    
    with file_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    
    current_chunk_id = None
    chunk_lines = []
    chunks_processed = 0
    
    for line in lines:
        match = chunk_marker_regex.match(line.strip())
        if match:
            # If a chunk is in progress, process it
            if current_chunk_id is not None and chunk_lines:
                chunk_text = "\n".join(chunk_lines).strip()
                if chunk_text:
                    store_chunk_with_embeddings(
                        current_chunk_id, 
                        chunk_text, 
                        embedding_models, 
                        collections, 
                        legacy_collection
                    )
                    chunks_processed += 1
                chunk_lines = []  # Reset for new chunk
            
            # Extract new chunk id
            episode = match.group(1)  # e.g., "S03E11"
            chunk_number_str = match.group(2)  # e.g., "037"
            current_chunk_id = f"{episode}_{chunk_number_str}"
            continue
        
        # Append line to current chunk content
        chunk_lines.append(line.strip())
    
    # Process final chunk if exists
    if current_chunk_id is not None and chunk_lines:
        chunk_text = "\n".join(chunk_lines).strip()
        if chunk_text:
            store_chunk_with_embeddings(
                current_chunk_id, 
                chunk_text, 
                embedding_models, 
                collections, 
                legacy_collection
            )
            chunks_processed += 1
    
    logger.info(f"Processed {chunks_processed} chunks from {file_path}")
    return chunks_processed

def store_chunk_with_embeddings(chunk_id, chunk_text, embedding_models, collections, legacy_collection):
    """
    Store a chunk with embeddings from all available models
    
    Args:
        chunk_id (str): Unique identifier for the chunk
        chunk_text (str): Text content of the chunk
        embedding_models (dict): Dictionary of loaded embedding models
        collections (dict): Dictionary of ChromaDB collections for each model
        legacy_collection (ChromaDB Collection): Backward compatibility collection
    """
    start_time = time.time()
    
    # Prepare metadata
    parts = chunk_id.split("_")
    episode = parts[0] if len(parts) > 0 else "UNKNOWN"
    try:
        chunk_number = int(parts[1]) if len(parts) > 1 else None
    except ValueError:
        chunk_number = None
    
    char_count = len(chunk_text)
    
    metadata = {
        "chunk_id": chunk_id,
        "chunk_tag": chunk_id,
        "episode": episode,
        "chunk_number": chunk_number,
        "char_count": char_count,
        "processing_version": PROCESSING_VERSION,
        "text": chunk_text
    }
    
    # Generate embeddings with available models
    for model_name, model in embedding_models.items():
        try:
            embedding = model.encode(chunk_text).tolist()
            
            # Store in model-specific collection
            collections[model_name].add(
                ids=[chunk_id],
                documents=[chunk_text],
                embeddings=[embedding],
                metadatas=[metadata]
            )
            
            logger.info(f"Stored chunk in {model_name} collection: {chunk_id}")
        except Exception as e:
            logger.error(f"Failed to process chunk {chunk_id} with model {model_name}: {e}")
    
    # Store in legacy collection (using BGE Large)
    try:
        legacy_embedding = embedding_models["BAAI/bge-large-en"].encode(chunk_text).tolist()
        legacy_collection.add(
            ids=[chunk_id],
            documents=[chunk_text],
            embeddings=[legacy_embedding],
            metadatas=[metadata]
        )
    except Exception as e:
        logger.error(f"Failed to store chunk in legacy collection: {e}")
    
    processing_time = time.time() - start_time
    logger.info(f"Processed chunk {chunk_id} in {processing_time:.2f}s")

if __name__ == "__main__":
    main()
