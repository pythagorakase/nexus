#!/usr/bin/env python3
"""
Regenerate Embeddings Script for NEXUS

This script regenerates embeddings for all narrative chunks in the database
using a specified model. It's designed to support multiple embedding models
with different dimensions, creating appropriate tables based on vector size.

USAGE EXAMPLES:
---------------
# Generate embeddings for a specific model with indexes:
python scripts/regenerate_embeddings.py --model infly/inf-retriever-v1-1.5b --create-indexes

# Generate embeddings for all active models defined in settings.json:
python scripts/regenerate_embeddings.py --all-models --create-indexes

# Only create vector indexes for an existing embedding table:
python scripts/regenerate_embeddings.py --model infly/inf-retriever-v1-1.5b --only-indexes

# Resume embedding generation from a missing chunks file:
python scripts/regenerate_embeddings.py --model infly/inf-retriever-v1-1.5b --resume-from missing_chunks.txt

# Do a dry run without making changes:
python scripts/regenerate_embeddings.py --model infly/inf-retriever-v1-1.5b --dry-run

ARGUMENTS:
---------
--model MODEL             Embedding model to use (e.g., infly/inf-retriever-v1-1.5b)
--all-models              Process all active models from settings.json
--batch-size SIZE         Number of chunks to process in each batch (default: 10)
--db-url URL              PostgreSQL database URL (default: from settings.json)
--dry-run                 Perform a dry run without making changes
--create-indexes          Create vector indexes after data loading
--only-indexes            Only create indexes, skip embedding generation
--resume-from FILE        Resume from a file of missing chunk IDs

Dependencies:
    - pgvector 
    - sentence-transformers 
    - sqlalchemy
    - tqdm (for progress bars)
"""

import os
import sys
import json
import logging
import time
from typing import Dict, List, Tuple, Any, Optional, Union
import tqdm
import argparse
import numpy as np

# Add parent directory to sys.path to import from nexus package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import utils package
try:
    from scripts.utils.embedding_utils import get_model_dimensions
except ImportError:
    # Define locally if can't import
    MODEL_DIMENSIONS = {
        # Small models (384D)
        "bge-small-custom": 384,
        "bge-small-en": 384,
        "bge-small-en-v1.5": 384,
        "bge-small": 384,
        
        # Large models (1024D)
        "bge-large-en-v1.5": 1024,
        "bge-large-en": 1024,
        "bge-large": 1024,
        "e5-large-v2": 1024,
        "e5-large": 1024,
        
        # High-dimensional models
        "infly/inf-retriever-v1-1.5b": 1536,
    }
    
    def get_model_dimensions(model_name: str) -> int:
        """Get the vector dimensions for a given model name."""
        # Check for exact matches
        if model_name in MODEL_DIMENSIONS:
            return MODEL_DIMENSIONS[model_name]
        
        # Check for partial matches
        for key, value in MODEL_DIMENSIONS.items():
            if key in model_name:
                return value
        
        # Default to 1024 for unknown models
        return 1024

# Try to load settings using centralized config loader
try:
    from nexus.config import load_settings_as_dict
    _all_settings = load_settings_as_dict()
    SETTINGS = _all_settings.get("Agent Settings", {}).get("MEMNON", {})
except Exception as e:
    print(f"Warning: Could not load settings via config loader: {e}")
    SETTINGS = {}

# Configure logging from settings
log_file = SETTINGS.get("logging", {}).get("file", "embeddings.log")
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
logger = logging.getLogger("nexus.embeddings")

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

class ModelLoader:
    """Handles loading different types of embedding models"""
    
    @staticmethod
    def load_model(model_name: str) -> Any:
        """
        Load a model based on its name/type
        
        Args:
            model_name: Name of the model to load
            
        Returns:
            Loaded model
        
        Raises:
            ImportError: If required libraries aren't installed
            ValueError: If model can't be loaded
        """
        logger.info(f"Loading model: {model_name}")
        
        # Check for settings that might provide local paths
        model_local_path = None
        try:
            if SETTINGS.get("models") and SETTINGS["models"].get(model_name.replace("/", "_")):
                model_local_path = SETTINGS["models"][model_name.replace("/", "_")].get("local_path")
                if model_local_path:
                    logger.info(f"Found local path for {model_name}: {model_local_path}")
        except Exception as e:
            logger.warning(f"Error checking settings for local path: {e}")

        # Default local path for infly/inf-retriever models
        if "infly/inf-retriever" in model_name and not model_local_path:
            # Extract model name to use as directory name
            model_dir = model_name.split("/")[-1]  # Just get the part after the slash
            model_local_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models', model_dir))
            if os.path.exists(model_local_path):
                logger.info(f"Using default local path for {model_name}: {model_local_path}")
        
        # Load using sentence-transformers for all models
        try:
            from sentence_transformers import SentenceTransformer
            
            # Special handling for inf-retriever models which may use a snapshot structure
            if "infly/inf-retriever" in model_name and model_local_path and os.path.exists(model_local_path):
                snapshot_dir = os.path.join(model_local_path, 'snapshots')
                if os.path.exists(snapshot_dir):
                    snapshot_candidates = os.listdir(snapshot_dir)
                    if snapshot_candidates:
                        # Get first snapshot directory
                        snapshot_path = os.path.join(snapshot_dir, snapshot_candidates[0])
                        logger.info(f"Loading model from snapshot path: {snapshot_path}")
                        
                        try:
                            return SentenceTransformer(snapshot_path)
                        except Exception as e:
                            logger.warning(f"Failed to load from snapshot: {e}")
            
            # For other models or fallback
            if model_local_path and os.path.exists(model_local_path):
                logger.info(f"Loading model from local path: {model_local_path}")
                return SentenceTransformer(model_local_path)
            else:
                logger.info(f"Loading model from Hugging Face hub: {model_name}")
                return SentenceTransformer(model_name)
                
        except ImportError:
            logger.error("sentence-transformers not found. Install with: pip install sentence-transformers")
            raise ImportError("sentence-transformers library required")
        except Exception as e:
            logger.error(f"Error loading model {model_name}: {e}")
            raise ValueError(f"Failed to load model: {e}")

    @staticmethod
    def get_embedding(model: Any, text: str, model_name: str) -> np.ndarray:
        """
        Generate an embedding using the appropriate method for the model
        
        Args:
            model: Loaded SentenceTransformer model
            text: Text to embed
            model_name: Name of the model
            
        Returns:
            Embedding as numpy array
        """
        # Use SentenceTransformer's encode method
        try:
            # SentenceTransformer has a simple encode method
            embedding = model.encode(text)
            
            # If the result is already a numpy array, return it directly
            if isinstance(embedding, np.ndarray):
                return embedding
                
            # If it's a list, convert to numpy array
            if isinstance(embedding, list):
                return np.array(embedding)
                
            # Otherwise, try to convert to numpy array
            return np.array(embedding)
                
        except Exception as e:
            logger.error(f"Error generating embedding with {model_name}: {e}")
            raise

class EmbeddingRegenerator:
    """Regenerates embeddings for all narrative chunks"""
    
    def __init__(self, model_name: str, batch_size: int = 10, db_url: str = None, dry_run: bool = False,
                 create_indexes: bool = False, truncate_table: bool = False):
        """
        Initialize the regenerator with database connection and model.
        
        Args:
            model_name: Name of the embedding model to use
            batch_size: Number of chunks to process at once
            db_url: PostgreSQL database URL
            dry_run: If True, don't actually write to the database
            create_indexes: If True, create vector indexes after data is loaded
                           If False, only create basic indexes (faster for data loading)
            truncate_table: If True, completely truncate the table before starting (clean slate)
        """
        self.model_name = model_name
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.create_indexes = create_indexes
        self.truncate_table = truncate_table
        self.dimensions = get_model_dimensions(model_name)
        self.sequence_reset_done = False  # Track if we've reset the sequence
        self.force_id_for_first_insert = False  # Will be set to True if needed
        
        # Set database URL using slot-aware resolution
        if db_url:
            self.db_url = db_url
        else:
            # Try slot-aware resolution first, fall back to env var or error
            try:
                from nexus.api.slot_utils import get_slot_db_url
                self.db_url = get_slot_db_url()
            except (ImportError, RuntimeError) as e:
                # If slot_utils not available or NEXUS_SLOT not set, require explicit URL
                explicit_url = os.environ.get("NEXUS_DB_URL")
                if not explicit_url:
                    raise RuntimeError(
                        "No database URL provided. Set NEXUS_SLOT (1-5) or NEXUS_DB_URL "
                        "environment variable, or pass --db-url explicitly."
                    ) from e
                self.db_url = explicit_url
        
        # Initialize database connection
        self.engine = create_engine(self.db_url)
        self.Session = sessionmaker(bind=self.engine)
        
        # First make sure pgvector extension is available and dimension-specific table exists
        with self.engine.connect() as connection:
            # Create pgvector extension if needed
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            
            # Ensure the dimension-specific table exists (without vector indexes initially)
            self._ensure_dimension_table_exists(connection, create_vector_indexes=False)
            
            # If truncate table option is specified, drop and recreate the table
            if self.truncate_table and not self.dry_run:
                table_name = self.get_table_name()
                try:
                    # Check if table is shared with other models
                    check_other_models_sql = f"""
                    SELECT model, COUNT(*) 
                    FROM {table_name} 
                    WHERE model != :model_name
                    GROUP BY model;
                    """
                    
                    other_models = []
                    try:
                        # Table might not exist yet
                        other_models = connection.execute(text(check_other_models_sql), 
                                                        {"model_name": self.model_name}).fetchall()
                        connection.commit()
                    except:
                        # Table doesn't exist yet, so no other models to worry about
                        pass
                    
                    if other_models:
                        # Table is shared with other models, just delete entries for this model
                        logger.warning(f"⚠️ Table {table_name} is shared with other models:")
                        for model, count in other_models:
                            logger.warning(f"  - {model}: {count} entries")
                        logger.warning(f"⚠️ Will NOT truncate table to preserve other models")
                        
                        # Delete only entries for this model
                        delete_sql = f"DELETE FROM {table_name} WHERE model = :model_name;"
                        connection.execute(text(delete_sql), {"model_name": self.model_name})
                        logger.info(f"✅ Deleted all entries for {self.model_name} from {table_name}")
                        connection.commit()
                        
                        # Don't force ID=1 since other models are using the table
                        self.force_id_for_first_insert = False
                        self.sequence_reset_done = True
                    else:
                        # Table is not shared or doesn't exist, safe to drop/recreate
                        drop_sql = f"DROP TABLE IF EXISTS {table_name} CASCADE;"
                        connection.execute(text(drop_sql))
                        logger.info(f"✅ Dropped table {table_name} completely")
                        
                        # Force the table to be recreated with a fresh sequence
                        self._ensure_dimension_table_exists(connection, force_recreate=True)
                        logger.info(f"✅ Recreated table {table_name} with fresh identity sequence")
                        self.sequence_reset_done = True  # Mark sequence as already reset
                        self.force_id_for_first_insert = True
                except Exception as e:
                    logger.error(f"Failed to handle table {table_name}: {e}")
            
            connection.commit()
            logger.info(f"Verified pgvector extension and {self.get_table_name()} table in database")
        
        # Load the model
        try:
            self.model = ModelLoader.load_model(model_name)
            logger.info(f"Successfully loaded {model_name} model")
        except Exception as e:
            logger.error(f"Failed to load {model_name} model: {e}")
            sys.exit(1)
        
        logger.info(f"Connected to database: {self.db_url}")
    
    def _ensure_dimension_table_exists(self, connection, create_vector_indexes: bool = False, force_recreate: bool = False):
        """
        Ensure the dimension-specific embedding table exists
        
        Args:
            connection: SQLAlchemy connection object
            create_vector_indexes: If True, create vector-specific indexes. If False, only create basic indexes.
            force_recreate: If True, force recreate the table even if it exists
        """
        dimensions = self.dimensions
        table_name = self.get_table_name()
        
        # Check if table exists (case-insensitive)
        try:
            check_table_sql = f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE LOWER(table_name) = LOWER('{table_name}')
            );
            """
            table_exists = connection.execute(text(check_table_sql)).scalar()
            connection.commit()  # Commit this query to avoid transaction issues
            
            # If we're about to recreate a table, also check if there are entries for any other models
            # to avoid accidentally dropping embeddings for other models with the same dimensions
            if force_recreate and table_exists:
                check_models_sql = f"""
                SELECT model, COUNT(*) 
                FROM {table_name} 
                WHERE model != :this_model
                GROUP BY model;
                """
                other_models = connection.execute(text(check_models_sql), 
                                                 {"this_model": self.model_name}).fetchall()
                connection.commit()
                
                if other_models:
                    # There are other models using this table, so don't recreate the table
                    logger.warning(f"⚠️ Table {table_name} has entries for other models:")
                    for model, count in other_models:
                        logger.warning(f"  - {model}: {count} entries")
                    logger.warning(f"⚠️ Will NOT drop and recreate table to preserve other models")
                    logger.warning(f"⚠️ Will delete only entries for {self.model_name} instead")
                    force_recreate = False
                    
                    # Since we're not recreating the table, delete entries for this model
                    delete_sql = f"""
                    DELETE FROM {table_name} WHERE model = :model_name;
                    """
                    connection.execute(text(delete_sql), {"model_name": self.model_name})
                    logger.info(f"✅ Deleted all entries for {self.model_name} from {table_name}")
                    connection.commit()
            
            if not table_exists or force_recreate:
                logger.info(f"Creating dimension-specific table: {table_name}")
                
                # For all dimensions, create the table with basic indexes first
                with self.engine.begin() as separate_connection:
                    # First create the table without any vector indexes
                    create_table_sql = f"""
                    CREATE TABLE {table_name} (
                        id SERIAL PRIMARY KEY,
                        chunk_id BIGINT NOT NULL,
                        model VARCHAR(255) NOT NULL,
                        embedding vector({dimensions}) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        CONSTRAINT unique_{table_name}_chunk_model UNIQUE(chunk_id, model),
                        CONSTRAINT fk_{table_name}_chunk_id FOREIGN KEY (chunk_id) REFERENCES narrative_chunks(id) ON DELETE CASCADE
                    );
                    """
                    separate_connection.execute(text(create_table_sql))
                    logger.info(f"Created table {table_name}")
                    
                    # Create basic indexes (these are fast and help with lookups)
                    try:
                        separate_connection.execute(text(f"CREATE INDEX {table_name}_chunk_id_idx ON {table_name} (chunk_id);"))
                        logger.info(f"Created chunk_id index on {table_name}")
                    except Exception as e:
                        logger.warning(f"Error creating chunk_id index: {e}")
                        
                    try:
                        separate_connection.execute(text(f"CREATE INDEX {table_name}_model_idx ON {table_name} (model);"))
                        logger.info(f"Created model index on {table_name}")
                    except Exception as e:
                        logger.warning(f"Error creating model index: {e}")
                
                # Only create vector indexes if specifically requested
                # These are expensive to build and maintain during data loading
                if create_vector_indexes:
                    self.create_vector_indexes()
            
            # Legacy migration code removed since old chunk_embeddings table has been dropped
                
        except Exception as e:
            logger.error(f"Error checking/creating table {table_name}: {e}")
            # Don't re-raise the exception, allow the code to continue and try other models
            connection.rollback()  # Explicitly rollback so we can continue
    
    def get_table_name(self) -> str:
        """
        Get the appropriate table name for the current model dimension
        
        Returns:
            Table name to use for embeddings
        """
        dim_str = f"{self.dimensions:04d}"  # Format with leading zeros
        # PostgreSQL converts identifiers to lowercase by default
        return f"chunk_embeddings_{dim_str}d"
    
    def get_all_chunks(self) -> List[Dict[str, Any]]:
        """
        Retrieve all narrative chunks from the database.
        
        Returns:
            List of dicts containing chunk_id and raw_text
        """
        session = self.Session()
        try:
            # Query for all chunks
            query = text("""
                SELECT id, raw_text 
                FROM narrative_chunks 
                ORDER BY id
            """)
            
            result = session.execute(query).fetchall()
            
            # Convert to list of dicts
            chunks = [{"chunk_id": str(row[0]), "raw_text": row[1]} for row in result]
            
            logger.info(f"Retrieved {len(chunks)} narrative chunks from database")
            return chunks
        
        except Exception as e:
            logger.error(f"Error retrieving chunks: {e}")
            return []
        
        finally:
            session.close()
    
    def delete_existing_embeddings(self) -> int:
        """
        Delete any existing embeddings for the current model.
        
        Returns:
            Number of embeddings deleted
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete existing {self.model_name} embeddings")
            return 0
        
        table_name = self.get_table_name()
        session = self.Session()
        deleted_count = 0
        
        try:
            # Check if the table exists first
            with self.engine.connect() as check_conn:
                table_exists_query = text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE LOWER(table_name) = LOWER('{table_name}')
                    );
                """)
                table_exists = check_conn.execute(table_exists_query).scalar()
                
                if not table_exists:
                    logger.info(f"Table {table_name} doesn't exist yet, no need to delete anything")
                    return 0
            
            # Delete from the dimension-specific table
            delete_query = text(f"""
                DELETE FROM {table_name} 
                WHERE model = :model_name
            """)
            
            result = session.execute(delete_query, {"model_name": self.model_name})
            dimension_deleted = result.rowcount
            session.commit()
            
            deleted_count += dimension_deleted
            logger.info(f"Deleted {dimension_deleted} existing {self.model_name} embeddings from {table_name}")
            
            # Legacy code for old chunk_embeddings table removed since table has been dropped
            
            # Truncate the table and reset sequence if requested to fully reset IDs
            if deleted_count > 0:
                try:
                    with self.engine.begin() as conn:
                        # Option 1: Reset sequence directly (if there are remaining rows, this will prevent ID clashes)
                        reset_seq_sql = f"""
                        SELECT setval('{table_name}_id_seq', 
                           (SELECT COALESCE(MIN(id), 1) - 1 FROM {table_name}), 
                           true);
                        """
                        conn.execute(text(reset_seq_sql))
                        logger.info(f"Reset ID sequence for {table_name} to restart from the beginning")
                except Exception as e:
                    logger.warning(f"Could not reset table sequence: {e}")
            
            return deleted_count
        
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting existing embeddings: {e}")
            return 0
        
        finally:
            session.close()
    
    def store_embedding_batch(self, batch: List[Tuple[str, List[float]]]) -> int:
        """
        Store a batch of embeddings
        
        Args:
            batch: List of (chunk_id, embedding) tuples
            
        Returns:
            Number of embeddings successfully stored
        """
        if not batch:
            return 0
            
        if self.dry_run:
            return len(batch)
        
        table_name = self.get_table_name()
        success_count = 0
        
        # Only reset the sequence once at the beginning of the process
        if not self.sequence_reset_done:
            with self.engine.begin() as conn:
                try:
                    # First ensure there are no existing rows for this model (belt and suspenders)
                    delete_query = f"DELETE FROM {table_name} WHERE model = :model_name;"
                    conn.execute(text(delete_query), {"model_name": self.model_name})
                    logger.info(f"✅ Removed any existing rows for model {self.model_name}")
                    
                    # Check if other models are using this table
                    other_models_sql = f"""
                    SELECT model, COUNT(*) 
                    FROM {table_name} 
                    WHERE model != :this_model 
                    GROUP BY model;
                    """
                    other_models = conn.execute(text(other_models_sql), 
                                              {"this_model": self.model_name}).fetchall()
                    
                    has_other_models = len(other_models) > 0
                    
                    # Next get minimum and maximum existing IDs
                    count_sql = f"SELECT COUNT(*), MIN(id), MAX(id) FROM {table_name};"
                    count_row = conn.execute(text(count_sql)).fetchone()
                    remaining_count, min_id, max_id = count_row[0] or 0, count_row[1] or 0, count_row[2] or 0
                    
                    if remaining_count > 0:
                        logger.info(f"Still {remaining_count} rows in table from other models (ID range: {min_id}-{max_id})")
                        
                        # Log the other models using this table
                        if has_other_models:
                            logger.info(f"Table {table_name} is shared with other models:")
                            for model, count in other_models:
                                logger.info(f"  - {model}: {count} entries")
                    
                    # Reset sequence differently depending on whether there are other models
                    if has_other_models:
                        # For tables with other models, we need to get next available ID
                        # to avoid conflicts with existing rows
                        reset_sql = f"""
                        SELECT setval('{table_name}_id_seq', 
                                     (SELECT COALESCE(MAX(id), 0) FROM {table_name}),
                                     true);
                        """
                        conn.execute(text(reset_sql))
                        logger.info(f"✅ Set ID sequence for {table_name} to continue after existing rows")
                        
                        # Don't force ID since other models are using the table
                        self.force_id_for_first_insert = False
                    elif self.truncate_table:
                        # For truncated tables with no other models, we can restart from 1
                        reset_sql = f"ALTER SEQUENCE {table_name}_id_seq RESTART WITH 1;"
                        conn.execute(text(reset_sql))
                        logger.info(f"✅ Reset ID sequence for {table_name} to start from 1")
                        
                        # Force ID=1 for first insert
                        self.force_id_for_first_insert = True
                        logger.info("✅ Will force ID=1 for first insertion")
                    else:
                        # No other models but not truncating - just reset to next available ID
                        reset_sql = f"""
                        SELECT setval('{table_name}_id_seq', 
                                     (SELECT COALESCE(MAX(id), 0) FROM {table_name}),
                                     true);
                        """
                        conn.execute(text(reset_sql))
                        logger.info(f"✅ Set ID sequence for {table_name} to next available ID")
                        self.force_id_for_first_insert = False
                        
                    # Mark sequence handling as done
                    self.sequence_reset_done = True
                        
                    # Verify the sequence setting
                    try:
                        next_sql = f"SELECT nextval('{table_name}_id_seq');"
                        next_val = conn.execute(text(next_sql)).scalar()
                        logger.info(f"Next ID will be: {next_val}")
                        
                        # Revert the nextval operation to keep sequence in sync
                        if next_val > 1:
                            revert_sql = f"""
                            SELECT setval('{table_name}_id_seq', 
                                        (SELECT COALESCE(currval('{table_name}_id_seq'), 1) - 1),
                                        true);
                            """
                            conn.execute(text(revert_sql))
                    except Exception:
                        # If there are no existing sequence values, this might fail
                        logger.info("Sequence hasn't been used yet")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Could not properly setup sequence: {e}")
        
        # For high-dimensional vectors, process one at a time to avoid SQL issues
        # with extremely long statements
        if self.dimensions > 2000:
            logger.info(f"Using per-row insert strategy for high-dimensional vectors ({self.dimensions}D)")
            
            # Keep track if we need to force ID=1 for first insert
            is_first_insert = True
            
            for chunk_id, embedding in batch:
                session = self.Session()
                try:
                    # Format embedding string without using Python string concatenation
                    # to avoid memory issues with huge vectors
                    
                    # Convert embedding to string format for pgvector
                    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                    
                    # For the very first insert on a truncated table, force ID=1
                    if is_first_insert and self.force_id_for_first_insert:
                        insert_sql = text(f"""
                            INSERT INTO {table_name} 
                            (id, chunk_id, model, embedding, created_at) 
                            VALUES (1, :chunk_id, :model_name, '{embedding_str}'::vector({self.dimensions}), NOW())
                            ON CONFLICT (chunk_id, model) DO UPDATE
                            SET embedding = '{embedding_str}'::vector({self.dimensions}),
                                created_at = NOW();
                        """)
                        logger.info(f"👉 Forcing ID=1 for first row")
                        is_first_insert = False  # No longer the first insert
                        self.force_id_for_first_insert = False  # Only force once
                    else:
                        # Normal insert without forcing ID - explicit casting to vector with dimensions
                        # Add explicit RETURNING clause to ensure we get feedback that the update worked
                        insert_sql = text(f"""
                            INSERT INTO {table_name} 
                            (chunk_id, model, embedding, created_at) 
                            VALUES (:chunk_id, :model_name, '{embedding_str}'::vector({self.dimensions}), NOW())
                            ON CONFLICT (chunk_id, model) DO UPDATE
                            SET embedding = '{embedding_str}'::vector({self.dimensions}),
                                created_at = NOW()
                            RETURNING id;
                        """)
                    
                    # Execute the statement with just the standard parameters
                    session.execute(insert_sql, {
                        "chunk_id": int(chunk_id), 
                        "model_name": self.model_name
                    })
                    session.commit()
                    success_count += 1
                    
                except Exception as e:
                    session.rollback()
                    logger.error(f"Error storing embedding for chunk {chunk_id}: {e}")
                    
                finally:
                    session.close()
            
            if success_count > 0:
                logger.info(f"Stored {success_count}/{len(batch)} embeddings in {table_name}")
            
            return success_count
        
        # For normal-sized vectors, use batch insert
        session = self.Session()
        try:
            # If this is a truncated table and we need to force ID=1 for the first insert,
            # we need to handle the first row separately
            if self.force_id_for_first_insert and len(batch) > 0:
                # Handle the first row separately to force ID=1
                chunk_id, embedding = batch[0]
                embedding_str = f"[{','.join(str(x) for x in embedding)}]"
                
                # Force ID=1 for the first row - explicit casting to vector with dimensions
                force_first_sql = text(f"""
                    INSERT INTO {table_name} 
                    (id, chunk_id, model, embedding, created_at) 
                    VALUES (1, :chunk_id, :model_name, '{embedding_str}'::vector({self.dimensions}), NOW())
                    ON CONFLICT (chunk_id, model) DO UPDATE
                    SET embedding = '{embedding_str}'::vector({self.dimensions}),
                        created_at = NOW()
                    RETURNING id;
                """)
                
                session.execute(force_first_sql, {
                    "chunk_id": int(chunk_id), 
                    "model_name": self.model_name
                })
                session.commit()
                logger.info(f"👉 Forced ID=1 for first row with chunk_id={chunk_id}")
                
                # Remove the first row from the batch since we've handled it
                batch = batch[1:]
                success_count += 1
                
                # Turn off forcing for future inserts
                self.force_id_for_first_insert = False
                
                # If the batch is now empty, we're done
                if not batch:
                    return success_count
            
            # For multi-row insert, we need to format each vector directly in the SQL
            values_parts = []
            params = {}
            
            for i, (chunk_id, embedding) in enumerate(batch):
                # Format embedding string directly in SQL with the :: cast to vector with explicit dimensions
                embedding_str = f"[{','.join(str(x) for x in embedding)}]"
                values_parts.append(f"(:chunk_id_{i}, :model_name, '{embedding_str}'::vector({self.dimensions}), NOW())")
                params[f"chunk_id_{i}"] = int(chunk_id)
            
            params["model_name"] = self.model_name
            
            # Skip empty batches (could happen if we removed the first row)
            if not values_parts:
                return success_count
                
            # Create multi-row insert statement
            values_sql = ",".join(values_parts)
            insert_sql = text(f"""
                INSERT INTO {table_name} 
                (chunk_id, model, embedding, created_at) 
                VALUES {values_sql}
                ON CONFLICT (chunk_id, model) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    created_at = EXCLUDED.created_at;
            """)
            
            session.execute(insert_sql, params)
            session.commit()
            success_count = len(batch)
            
            logger.info(f"Stored {len(batch)} embeddings in {table_name}")
        
        except Exception as e:
            session.rollback()
            logger.error(f"Error storing batch of embeddings: {e}")
            
            # Try individual inserts if batch insert fails
            for chunk_id, embedding in batch:
                try:
                    # Format embedding string
                    embedding_str = f"[{','.join(str(x) for x in embedding)}]"
                    
                    # Insert single row - explicitly cast to vector with dimensions
                    single_insert_sql = text(f"""
                        INSERT INTO {table_name} 
                        (chunk_id, model, embedding, created_at) 
                        VALUES (:chunk_id, :model_name, '{embedding_str}'::vector({self.dimensions}), NOW())
                        ON CONFLICT (chunk_id, model) DO UPDATE
                        SET embedding = '{embedding_str}'::vector({self.dimensions}),
                            created_at = NOW()
                        RETURNING id;
                    """)
                    
                    session.execute(single_insert_sql, {
                        "chunk_id": int(chunk_id), 
                        "model_name": self.model_name
                    })
                    session.commit()
                    success_count += 1
                
                except Exception as e2:
                    session.rollback()
                    logger.error(f"Error storing individual embedding for chunk {chunk_id}: {e2}")
        
        finally:
            session.close()
            return success_count
    
    def create_vector_indexes(self) -> bool:
        """
        Create vector indexes for the current model's table.
        This should be called after all data is loaded to avoid index maintenance overhead.
        
        Returns:
            True if at least one index was created successfully, False otherwise
        """
        table_name = self.get_table_name()
        dimensions = self.dimensions
        success = False
        
        logger.info(f"Creating vector indexes for {table_name} table ({dimensions}D)")
        
        # Now create specialized vector indexes in a separate transaction
        with self.engine.begin() as idx_conn:
            # First try HNSW index (preferred for performance)
            try:
                logger.info(f"Creating HNSW index for {table_name}...")
                start_time = time.time()
                
                # HNSW index with optimized parameters
                hnsw_sql = f"""
                CREATE INDEX {table_name}_hnsw_idx 
                ON {table_name} USING hnsw (embedding vector_cosine_ops)
                WITH (ef_construction=64, m=16);
                """
                idx_conn.execute(text(hnsw_sql))
                
                elapsed_time = time.time() - start_time
                logger.info(f"✅ Successfully created HNSW index for {dimensions}D vectors in {elapsed_time:.2f}s")
                success = True
            except Exception as e:
                logger.warning(f"⚠️ Could not create HNSW index: {e}")
                
                # If HNSW fails, try IVFFLAT as backup
                try:
                    logger.info(f"Creating IVFFLAT index for {table_name} as fallback...")
                    start_time = time.time()
                    
                    # IVFFLAT index with optimized parameters
                    ivf_sql = f"""
                    CREATE INDEX {table_name}_ivf_idx 
                    ON {table_name} USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists=100);
                    """
                    idx_conn.execute(text(ivf_sql))
                    
                    elapsed_time = time.time() - start_time
                    logger.info(f"✅ Created IVFFLAT index for {dimensions}D vectors in {elapsed_time:.2f}s")
                    success = True
                except Exception as e2:
                    logger.warning(f"⚠️ Could not create IVFFLAT index: {e2}")
                    logger.warning(f"Table will remain without specialized vector index, searches will be slower")
        
        return success
    
    def regenerate_all_embeddings(self) -> Dict[str, int]:
        """
        Regenerate all embeddings for the current model.
        
        Returns:
            Dict with counts of processed, successful, and failed embeddings
        """
        # Get all chunks
        chunks = self.get_all_chunks()
        if not chunks:
            logger.error("No chunks found to process")
            return {"total": 0, "success": 0, "failed": 0}
        
        # Count existing embeddings before deleting
        with self.engine.connect() as conn:
            table_name = self.get_table_name()
            count_sql = f"""
            SELECT COUNT(*) FROM {table_name} 
            WHERE model = :model_name;
            """
            existing_count = conn.execute(text(count_sql), {"model_name": self.model_name}).scalar() or 0
            
            # Get current sequence value to show the problem
            try:
                seq_val_sql = f"SELECT last_value FROM {table_name}_id_seq;"
                seq_value = conn.execute(text(seq_val_sql)).scalar() or 0
                if seq_value > 1:
                    logger.info(f"⚠️ Current sequence value for {table_name}_id_seq is {seq_value}")
                    logger.info(f"✅ This will be reset to 1 during embedding generation")
            except Exception as e:
                logger.warning(f"Could not check current sequence value: {e}")
            
            if existing_count > 0:
                logger.info(f"Found {existing_count} existing embeddings for {self.model_name}")
                # Ask for confirmation if not running in headless mode
                if not self.dry_run and os.isatty(sys.stdout.fileno()):
                    confirm = input(f"Delete {existing_count} existing embeddings for {self.model_name}? (y/n): ")
                    if confirm.lower() != 'y':
                        logger.info("Aborting embedding regeneration")
                        return {"total": 0, "success": 0, "failed": 0}
        
        # Delete existing embeddings
        self.delete_existing_embeddings()
        
        # Mark sequence as not reset yet to ensure it happens during first batch
        self.sequence_reset_done = False
        logger.info("✅ ID sequence will be reset during the first batch insertion")
        
        # Counters
        total = len(chunks)
        success = 0
        failed = 0
        batch = []
        last_save_point = 0
        checkpoint_interval = 50  # Save progress every 50 chunks
        
        # Process each chunk in batches
        logger.info(f"Starting embedding generation for {total} chunks with {self.model_name}")
        
        # Use tqdm for progress bar
        start_time = time.time()
        progress_bar = tqdm.tqdm(chunks, desc=f"Generating {self.model_name} embeddings")
        
        for i, chunk in enumerate(progress_bar):
            try:
                # Skip chunks that already have embeddings (should be none after deletion)
                chunk_id = chunk["chunk_id"]
                
                # Generate embedding
                embedding = ModelLoader.get_embedding(self.model, chunk["raw_text"], self.model_name)
                
                # Convert to list
                embedding_list = embedding.tolist()
                
                # Add to batch
                batch.append((chunk_id, embedding_list))
                
                # Process batch if reached batch size
                if len(batch) >= self.batch_size:
                    success_count = self.store_embedding_batch(batch)
                    success += success_count
                    failed += len(batch) - success_count
                    batch = []
                    
                # Log progress at checkpoints
                if i - last_save_point >= checkpoint_interval:
                    elapsed = time.time() - start_time
                    rate = i / elapsed if elapsed > 0 else 0
                    remaining = (total - i) / rate if rate > 0 else 0
                    
                    logger.info(f"Progress: {i}/{total} chunks ({i/total*100:.1f}%) - " +
                               f"Success: {success}, Failed: {failed} - " +
                               f"Est. remaining time: {remaining/60:.1f} minutes")
                    last_save_point = i
            
            except Exception as e:
                logger.error(f"Error processing chunk {chunk['chunk_id']}: {e}")
                failed += 1
        
        # Process final batch
        if batch:
            success_count = self.store_embedding_batch(batch)
            success += success_count
            failed += len(batch) - success_count
        
        elapsed_time = time.time() - start_time
        logger.info(f"Completed embedding generation in {elapsed_time:.2f}s: {success} successful, {failed} failed out of {total} total")
        
        # Double-check we have all embeddings
        with self.engine.connect() as conn:
            table_name = self.get_table_name()
            count_sql = f"""
            SELECT COUNT(*) FROM {table_name} 
            WHERE model = :model_name;
            """
            final_count = conn.execute(text(count_sql), {"model_name": self.model_name}).scalar() or 0
            
            if final_count < total:
                logger.warning(f"⚠️ Expected {total} embeddings but found only {final_count}")
                logger.warning(f"⚠️ {total - final_count} chunks were not processed correctly.")
                
                # Save missing chunks to file for resuming later
                missing_sql = f"""
                SELECT c.id FROM narrative_chunks c
                LEFT JOIN {table_name} e ON c.id = e.chunk_id AND e.model = :model_name
                WHERE e.id IS NULL;
                """
                missing_ids = [row[0] for row in conn.execute(text(missing_sql), {"model_name": self.model_name}).fetchall()]
                
                if missing_ids:
                    missing_file = f"missing_{self.model_name.replace('/', '_')}_{int(time.time())}.txt"
                    with open(missing_file, 'w') as f:
                        f.write('\n'.join(str(id) for id in missing_ids))
                    logger.warning(f"⚠️ Saved {len(missing_ids)} missing chunk IDs to {missing_file}")
                    logger.warning(f"⚠️ You can resume embedding generation for these chunks later.")
            else:
                logger.info(f"✅ Successfully generated embeddings for all {final_count} chunks")
        
        # Create vector indexes if requested
        if self.create_indexes and success > 0:
            logger.info("Creating vector indexes now that data is loaded...")
            index_success = self.create_vector_indexes()
            if index_success:
                logger.info("✅ Successfully created vector indexes")
            else:
                logger.warning("⚠️ Failed to create vector indexes")
                logger.info("You can create indexes later with: python scripts/create_vector_index.py --model " + self.model_name)
        elif success > 0:
            logger.info("Skipping vector index creation (use --create-indexes flag to create them)")
            logger.info("You can create indexes later with: python scripts/create_vector_index.py --model " + self.model_name)
        
        return {"total": total, "success": success, "failed": failed}

def regenerate_all_models(db_url: str = None, batch_size: int = 10, dry_run: bool = False, 
                     create_indexes: bool = False, truncate_table: bool = False):
    """
    Regenerate embeddings for all active models in settings.json
    
    Args:
        db_url: Database URL
        batch_size: Number of chunks to process in each batch
        dry_run: If True, don't make actual changes
        create_indexes: If True, create vector indexes after data is loaded
        truncate_table: If True, completely truncate the table before starting (clean slate)
    """
    # Get active models from settings
    active_models = []
    
    # Print header
    print("\n========== Regenerating Embeddings for Active Models ==========")
    
    try:
        models_config = SETTINGS.get("models", {})
        for model_key, config in models_config.items():
            if config.get("is_active", False):
                # Convert internal name format to proper model name
                if "_" in model_key:
                    model_name = model_key.replace("_", "/")
                else:
                    model_name = model_key
                    
                # Get local path if available
                local_path = config.get("local_path")
                remote_path = config.get("remote_path")
                
                # Check if local path exists
                local_path_exists = local_path and os.path.exists(local_path)
                
                # If remote_path is provided, use that as the model name
                if remote_path:
                    model_name = remote_path
                
                active_models.append(model_name)
                
                if local_path:
                    status = "✅ Found" if local_path_exists else "❌ Not found"
                    logger.info(f"Found active model in settings: {model_name} (Local path: {status})")
                    print(f"- {model_name}: Active, Local path: {status}")
                else:
                    logger.info(f"Found active model in settings (remote only): {model_name}")
                    print(f"- {model_name}: Active, Using HuggingFace remote")
    except Exception as e:
        logger.error(f"Error processing models from settings: {e}")
        print(f"Error loading models from settings: {e}")
        
    if not active_models:
        logger.warning("No active models found in settings.json")
        print("No active models found in settings.json, defaulting to infly/inf-retriever-v1")
        # Default to infly/inf-retriever-v1 if no active models
        active_models = ["infly/inf-retriever-v1"]
    
    total_results = {"total": 0, "success": 0, "failed": 0}
    
    # Process each active model
    for model_name in active_models:
        logger.info(f"Processing model: {model_name}")
        
        try:
            # Initialize the regenerator
            regenerator = EmbeddingRegenerator(
                model_name=model_name,
                batch_size=batch_size,
                db_url=db_url, 
                dry_run=dry_run,
                create_indexes=create_indexes,
                truncate_table=truncate_table
            )
            
            # Regenerate embeddings for this model
            results = regenerator.regenerate_all_embeddings()
            
            # Add to total results
            total_results["total"] += results["total"]
            total_results["success"] += results["success"]
            total_results["failed"] += results["failed"]
            
            # Print model summary
            print(f"\nCompleted model: {model_name}")
            print(f"Dimensions: {regenerator.dimensions}")
            print(f"Successful: {results['success']}/{results['total']}")
            
        except Exception as e:
            logger.error(f"Error processing model {model_name}: {e}")
            total_results["failed"] += 1
    
    return total_results

def regenerate_missing_chunks(model_name: str, missing_file: str, batch_size: int = 10, 
                         db_url: str = None, dry_run: bool = False, create_indexes: bool = False,
                         truncate_table: bool = False):
    """
    Regenerate embeddings for missing chunks specified in a file.
    
    Args:
        model_name: Embedding model to use
        missing_file: File containing IDs of chunks to process
        batch_size: Batch size for processing
        db_url: Database URL
        dry_run: If True, don't make actual changes
        create_indexes: If True, create vector indexes after data loading
        truncate_table: If True, completely truncate the table before starting (clean slate)
        
    Returns:
        Dict with results
    """
    logger.info(f"Reading missing chunk IDs from {missing_file}")
    try:
        with open(missing_file, 'r') as f:
            chunk_ids = [line.strip() for line in f if line.strip()]
        
        missing_count = len(chunk_ids)
        logger.info(f"Found {missing_count} missing chunk IDs to process")
        
        if not missing_count:
            logger.warning("No missing chunk IDs found, nothing to do")
            return {"total": 0, "success": 0, "failed": 0}
        
        # Connect to database using slot-aware resolution
        if not db_url:
            try:
                from nexus.api.slot_utils import get_slot_db_url
                db_url = get_slot_db_url()
            except (ImportError, RuntimeError):
                db_url = os.environ.get("NEXUS_DB_URL")
                if not db_url:
                    raise RuntimeError(
                        "No database URL provided. Set NEXUS_SLOT (1-5) or NEXUS_DB_URL."
                    )
        engine = create_engine(db_url)
        
        # Get the chunks for these IDs
        chunks = []
        with engine.connect() as conn:
            # Query in batches to avoid too many parameters
            for i in range(0, len(chunk_ids), 100):
                batch_ids = chunk_ids[i:i+100]
                placeholders = ', '.join(f':id{j}' for j in range(len(batch_ids)))
                params = {f'id{j}': int(id) for j, id in enumerate(batch_ids)}
                
                query = text(f"""
                    SELECT id, raw_text 
                    FROM narrative_chunks 
                    WHERE id IN ({placeholders})
                    ORDER BY id
                """)
                
                result = conn.execute(query, params).fetchall()
                chunks.extend([{"chunk_id": str(row[0]), "raw_text": row[1]} for row in result])
        
        if not chunks:
            logger.error("No chunks found for the provided IDs")
            return {"total": 0, "success": 0, "failed": 0}
        
        logger.info(f"Retrieved {len(chunks)} chunks from database")
        
        # Create regenerator and process these chunks
        regenerator = EmbeddingRegenerator(
            model_name=model_name,
            batch_size=batch_size,
            db_url=db_url, 
            dry_run=dry_run,
            create_indexes=create_indexes,
            truncate_table=truncate_table
        )
        
        # Process each chunk in batches
        total = len(chunks)
        success = 0
        failed = 0
        batch = []
        
        # Use tqdm for progress bar
        start_time = time.time()
        progress_bar = tqdm.tqdm(chunks, desc=f"Generating {model_name} embeddings (resume)")
        
        for chunk in progress_bar:
            try:
                # Generate embedding
                embedding = ModelLoader.get_embedding(regenerator.model, chunk["raw_text"], model_name)
                
                # Convert to list
                embedding_list = embedding.tolist()
                
                # Add to batch
                batch.append((chunk["chunk_id"], embedding_list))
                
                # Process batch if reached batch size
                if len(batch) >= batch_size:
                    success_count = regenerator.store_embedding_batch(batch)
                    success += success_count
                    failed += len(batch) - success_count
                    batch = []
            
            except Exception as e:
                logger.error(f"Error processing chunk {chunk['chunk_id']}: {e}")
                failed += 1
        
        # Process final batch
        if batch:
            success_count = regenerator.store_embedding_batch(batch)
            success += success_count
            failed += len(batch) - success_count
        
        elapsed_time = time.time() - start_time
        logger.info(f"Completed resume embedding generation in {elapsed_time:.2f}s: {success} successful, {failed} failed out of {total} total")
        
        return {"total": total, "success": success, "failed": failed}
    
    except Exception as e:
        logger.error(f"Error processing missing chunks: {e}")
        return {"total": 0, "success": 0, "failed": 0}

def main():
    """Main function to run the regeneration process"""
    parser = argparse.ArgumentParser(description="Regenerate embeddings for narrative chunks")
    parser.add_argument("--model", help="Embedding model to use (e.g., infly/inf-retriever-v1)")
    parser.add_argument("--all-models", action="store_true", help="Process all active models from settings.json")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of chunks to process in each batch")
    parser.add_argument("--db-url", dest="db_url", help="PostgreSQL database URL")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without making changes")
    parser.add_argument("--create-indexes", action="store_true", 
                       help="Create vector indexes after data loading (can be slow but improves query performance)")
    parser.add_argument("--only-indexes", action="store_true",
                       help="Only create indexes, skip embedding generation (use after running without indexes)")
    parser.add_argument("--resume-from", help="Resume from a file of missing chunk IDs")
    parser.add_argument("--truncate-table", action="store_true", 
                       help="Completely truncate the table and reset sequence before starting (clean slate approach)")
    args = parser.parse_args()
    
    # Check input validity
    if not args.model and not args.all_models and not args.only_indexes and not args.resume_from:
        print("Error: Either --model, --all-models, --only-indexes, or --resume-from must be specified")
        parser.print_help()
        sys.exit(1)
    
    try:
        # If resuming from missing chunks, handle that separately
        if args.resume_from:
            if not args.model:
                print("Error: --model must be specified when using --resume-from")
                sys.exit(1)
                
            logger.info(f"Resuming embedding generation for {args.model} from {args.resume_from}")
            results = regenerate_missing_chunks(
                model_name=args.model,
                missing_file=args.resume_from,
                batch_size=args.batch_size,
                db_url=args.db_url,
                dry_run=args.dry_run,
                create_indexes=args.create_indexes,
                truncate_table=args.truncate_table
            )
            
            # Print summary
            print("\nResume Embedding Generation Complete:")
            print(f"Model: {args.model}")
            print(f"Missing file: {args.resume_from}")
            print(f"Total chunks processed: {results['total']}")
            print(f"Successful embeddings: {results['success']}")
            print(f"Failed embeddings: {results['failed']}")
            
            if args.dry_run:
                print("\nThis was a dry run, no changes were made to the database.")
            
            if results['failed'] > 0:
                print("\nSome embeddings failed to generate. Check the log for details.")
                sys.exit(1)
                
            return
            
        # If only creating indexes, handle that separately
        if args.only_indexes:
            if not args.model:
                print("Error: --model must be specified when using --only-indexes")
                sys.exit(1)
                
            logger.info(f"Creating vector indexes for model: {args.model}")
            
            # Initialize the regenerator just for index creation
            regenerator = EmbeddingRegenerator(
                model_name=args.model,
                batch_size=args.batch_size,
                db_url=args.db_url, 
                dry_run=args.dry_run,
                create_indexes=True,  # Always true for this mode
                truncate_table=args.truncate_table
            )
            
            # Create indexes
            success = regenerator.create_vector_indexes()
            
            if success:
                print(f"\nSuccessfully created vector indexes for {regenerator.get_table_name()}")
                print(f"Vector similarity queries should now be much faster")
            else:
                print(f"\nFailed to create vector indexes for {regenerator.get_table_name()}")
                print(f"Check the log for details")
                sys.exit(1)
                
            return
        
        # Normal embedding generation
        if args.all_models:
            logger.info("Starting embedding generation for all active models")
            results = regenerate_all_models(
                db_url=args.db_url,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                create_indexes=args.create_indexes,
                truncate_table=args.truncate_table
            )
            
            # Print overall summary
            print("\nAll Models Embedding Generation Complete:")
            print(f"Total chunks processed: {results['total']}")
            print(f"Total successful embeddings: {results['success']}")
            print(f"Total failed operations: {results['failed']}")
        else:
            logger.info(f"Starting embedding generation with model: {args.model}")
            
            # Initialize the regenerator for single model
            regenerator = EmbeddingRegenerator(
                model_name=args.model,
                batch_size=args.batch_size,
                db_url=args.db_url, 
                dry_run=args.dry_run,
                create_indexes=args.create_indexes,
                truncate_table=args.truncate_table
            )
            
            # Regenerate embeddings for this model
            results = regenerator.regenerate_all_embeddings()
            
            # Print summary
            print("\nEmbedding Generation Complete:")
            print(f"Model: {args.model}")
            print(f"Dimensions: {regenerator.dimensions}")
            print(f"Total chunks processed: {results['total']}")
            print(f"Successful embeddings: {results['success']}")
            print(f"Failed embeddings: {results['failed']}")
            
            if not args.create_indexes and results['success'] > 0:
                print("\nNote: Vector indexes were not created.")
                print("You can create them later with: python scripts/regenerate_embeddings.py --model " +
                      f"{args.model} --only-indexes")
        
        if args.dry_run:
            print("\nThis was a dry run, no changes were made to the database.")
        
        if results['failed'] > 0:
            print("\nSome embeddings failed to generate. Check the log for details.")
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"Error during embedding generation: {e}")
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()