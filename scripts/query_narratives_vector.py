#!/usr/bin/env python3
"""
Query Narratives Script for NEXUS with vector search support

This script provides semantic search functionality across the stored narrative chunks
using pgvector for similarity search. It supports both 1024D (BGE-Large, E5-Large) 
and 384D (BGE-Small) embeddings stored in separate tables.

Usage:
    python query_narratives_vector.py "your search query" --model bge-large --limit 5

Example:
    python query_narratives_vector.py "Alex discovers the secret" --model bge-large
"""

import os
import sys
import argparse
import logging
import json
from typing import List, Dict, Any, Tuple, Optional

# Add parent directory to sys.path to import from nexus package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import embedding utilities
try:
    from scripts.utils.embedding_utils import (
        get_model_dimensions,
        get_table_for_model,
        construct_vector_search_sql,
        normalize_vector
    )
except ImportError:
    print("Embedding utilities not found. Please ensure scripts/utils/embedding_utils.py exists.")
    EMBEDDING_UTILS_AVAILABLE = False
else:
    EMBEDDING_UTILS_AVAILABLE = True

# Try to load settings
try:
    with open(os.path.join(os.path.dirname(__file__), '..', 'settings.json'), 'r') as f:
        SETTINGS = json.load(f)["Agent Settings"]["MEMNON"]
except Exception as e:
    print(f"Warning: Could not load settings from settings.json: {e}")
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
logger = logging.getLogger("nexus.query")

# Try to import sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    logger.error("sentence-transformers not found. Please install with: pip install sentence-transformers")
    sys.exit(1)

# Try to import SQLAlchemy
try:
    import sqlalchemy as sa
    from sqlalchemy import create_engine, text
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
    logger.error("pgvector not found. Please install with: pip install pgvector")
    sys.exit(1)

# Try to import numpy for vector operations
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    logger.error("numpy not found. Please install with: pip install numpy")
    HAS_NUMPY = False

class NarrativeSearcher:
    """
    Performs semantic search over narrative chunks using vector embeddings.
    """
    
    def __init__(self, db_url: str = None):
        """
        Initialize the searcher with database connection.
        
        Args:
            db_url: PostgreSQL database URL
        """
        # Set default database URL if not provided
        default_db_url = SETTINGS.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
        self.db_url = db_url or os.environ.get("NEXUS_DB_URL", default_db_url)
        
        # Initialize database connection
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
        
        # Initialize embedding models
        self.embedding_models = self._initialize_embedding_models()
        
        # Check pgvector extension
        self._check_pgvector()
        
        logger.info(f"Connected to database: {self.db_url}")
        logger.info(f"Available embedding models: {', '.join(self.embedding_models.keys())}")
    
    def _check_pgvector(self):
        """Check if pgvector extension is properly installed."""
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar()
                if not result:
                    logger.error("pgvector extension not found in database. Please install it first.")
                    sys.exit(1)
                logger.info("pgvector extension found in database.")
        except Exception as e:
            logger.error(f"Error checking pgvector extension: {e}")
            sys.exit(1)
    
    def _initialize_embedding_models(self) -> Dict[str, Any]:
        """Initialize embedding models for semantic retrieval."""
        embedding_models = {}
        
        # Define model paths from settings, falling back to defaults if not available
        settings_models = SETTINGS.get("models", {})
        
        model_paths = {
            "bge-large": [
                settings_models.get("bge-large", {}).get("local_path", os.path.expanduser("~/nexus/models/models--BAAI--bge-large-en")),
                settings_models.get("bge-large", {}).get("remote_path", "BAAI/bge-large-en")
            ],
            "e5-large": [
                settings_models.get("e5-large", {}).get("local_path", os.path.expanduser("~/nexus/models/models--intfloat--e5-large-v2")),
                settings_models.get("e5-large", {}).get("remote_path", "intfloat/e5-large-v2")
            ],
            "bge-small-custom": [
                settings_models.get("bge-small-custom", {}).get("local_path", os.path.expanduser("~/nexus/models/bge_small_finetuned_20250320_153654")),
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
                if local_path and os.path.exists(local_path):
                    try:
                        logger.info(f"Loading {model_key} from local path: {local_path}")
                        model = SentenceTransformer(local_path)
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

    def generate_embedding(self, query: str, model_key: str) -> List[float]:
        """
        Generate an embedding for the query using the specified model.
        
        Args:
            query: Search query to embed
            model_key: Key of the model to use
            
        Returns:
            Embedding as a list of floats
        """
        if model_key not in self.embedding_models:
            logger.error(f"Model {model_key} not found in available embedding models")
            raise ValueError(f"Model {model_key} not found in available embedding models")
        
        model = self.embedding_models[model_key]
        embedding = model.encode(query)
        
        return embedding.tolist()

    def semantic_search(self, query: str, model: str = "bge-large", limit: int = 5) -> List[Dict[str, Any]]:
        """
        Perform semantic search using vector similarity.
        
        Args:
            query: The search query
            model: The embedding model to use
            limit: Maximum number of results to return
            
        Returns:
            List of matching chunks with scores
        """
        # Generate embedding for the query
        try:
            query_embedding = self.generate_embedding(query, model)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return []
        
        # Create a session
        session = self.Session()
        
        try:
            # Use the embedding utilities if available
            if EMBEDDING_UTILS_AVAILABLE:
                # Normalize the embedding for better results
                if HAS_NUMPY:
                    query_embedding = normalize_vector(query_embedding).tolist()
                
                # Get the correct table for this model
                embedding_table = get_table_for_model(model)
                
                # Get the vector dimensions for this model
                dimensions = get_model_dimensions(model)
                
                # Construct the SQL query using our utility function
                sql_query, table_used = construct_vector_search_sql(
                    model_name=model,
                    filter_conditions=None,
                    limit=limit
                )
                
                logger.info(f"Using table {table_used} for model {model} ({dimensions}D)")
            else:
                # Fall back to the original logic if utilities aren't available
                logger.warning("Embedding utilities not available, using fallback table selection")
                
                # Determine the table and dimensions based on the model name
                if model.startswith("bge-small"):
                    embedding_table = "chunk_embeddings_small"
                    dimensions = 384
                else:
                    embedding_table = "chunk_embeddings"
                    dimensions = 1024
            
            # Create the query vector string representation directly in SQL
            query_vector_str = f"[{','.join(str(x) for x in query_embedding)}]"
            
            # Construct the SQL query
            raw_sql = f"""
                SELECT 
                    nc.id, 
                    nc.raw_text,
                    cm.season,
                    cm.episode,
                    cm.characters,
                    1 - (ce.embedding <=> '{query_vector_str}'::vector) AS similarity
                FROM 
                    narrative_chunks nc
                JOIN 
                    {embedding_table} ce ON nc.id = ce.chunk_id
                LEFT JOIN
                    chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE
                    ce.model = '{model}'
                ORDER BY 
                    ce.embedding <=> '{query_vector_str}'::vector
                LIMIT {limit}
            """
            
            # Execute the raw SQL query
            result = session.execute(text(raw_sql))
            
            # Process results
            search_results = []
            for row in result:
                # Extract context from the raw text (truncate if too long)
                raw_text = row.raw_text
                if len(raw_text) > 500:
                    raw_text = raw_text[:497] + "..."
                
                # Extract characters if available
                characters = []
                if row.characters:
                    try:
                        characters = list(set(eval(row.characters)))
                    except:
                        pass
                
                # Format the result
                search_results.append({
                    "id": str(row.id),
                    "similarity": float(row.similarity),
                    "season": row.season or 0,
                    "episode": row.episode or 0,
                    "characters": characters,
                    "text": raw_text
                })
            
            return search_results
        
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []
        
        finally:
            session.close()
    
    def text_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Perform text-based search using PostgreSQL ILIKE.
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            
        Returns:
            List of matching chunks
        """
        # Create a session
        session = self.Session()
        
        try:
            # Construct the SQL query with ILIKE for text matching
            sql_query = text("""
                SELECT 
                    nc.id, 
                    nc.raw_text,
                    cm.season,
                    cm.episode,
                    cm.characters
                FROM 
                    narrative_chunks nc
                LEFT JOIN
                    chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE
                    nc.raw_text ILIKE :query_pattern
                LIMIT :limit
            """)
            
            # Execute the query with parameters
            result = session.execute(
                sql_query,
                {
                    "query_pattern": f"%{query}%",
                    "limit": limit
                }
            )
            
            # Process results
            search_results = []
            for row in result:
                # Extract context from the raw text (truncate if too long)
                raw_text = row.raw_text
                if len(raw_text) > 500:
                    raw_text = raw_text[:497] + "..."
                
                # Extract characters if available
                characters = []
                if row.characters:
                    try:
                        characters = list(set(eval(row.characters)))
                    except:
                        pass
                
                # Format the result
                search_results.append({
                    "id": str(row.id),
                    "season": row.season or 0,
                    "episode": row.episode or 0,
                    "characters": characters,
                    "text": raw_text
                })
            
            return search_results
        
        except Exception as e:
            logger.error(f"Error in text search: {e}")
            return []
        
        finally:
            session.close()

def main():
    """
    Main entry point for the query script
    """
    parser = argparse.ArgumentParser(description="Query narrative chunks in NEXUS")
    parser.add_argument("query", help="Search query")
    
    # Get default values from settings
    default_model = SETTINGS.get("query", {}).get("default_model", "bge-large")
    default_limit = SETTINGS.get("query", {}).get("default_limit", 5)
    
    parser.add_argument("--model", choices=["bge-large", "e5-large", "bge-small-custom", "bge-small"], 
                        default=default_model, help="Embedding model to use for semantic search")
    parser.add_argument("--limit", type=int, default=default_limit, help="Maximum number of results to return")
    parser.add_argument("--text-only", action="store_true", help="Use text search instead of vector search")
    parser.add_argument("--db-url", dest="db_url", help="PostgreSQL database URL")
    args = parser.parse_args()
    
    # Initialize searcher
    searcher = NarrativeSearcher(db_url=args.db_url)
    
    # Perform search
    if args.text_only:
        print(f"Performing text search for: '{args.query}'")
        results = searcher.text_search(args.query, limit=args.limit)
    else:
        print(f"Performing semantic search for: '{args.query}' using model: {args.model}")
        results = searcher.semantic_search(args.query, model=args.model, limit=args.limit)
    
    # Print results
    if not results:
        print("No results found.")
    else:
        print(f"\nFound {len(results)} results:")
        print("-" * 80)
        
        for i, result in enumerate(results):
            print(f"Result {i+1}:")
            if "similarity" in result:
                print(f"Similarity: {result['similarity']:.4f}")
            print(f"S{result['season']:02d}E{result['episode']:02d}")
            
            if result["characters"]:
                print(f"Characters: {', '.join(result['characters'])}")
            
            print(f"\n{result['text']}\n")
            print("-" * 80)

if __name__ == "__main__":
    main()