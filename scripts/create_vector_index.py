#!/usr/bin/env python3
"""
Script to create vector indexes for existing embedding tables.
This should be run after data is loaded to avoid index maintenance overhead
during high-volume inserts.
"""

import os
import sys
import argparse
import json
import time
import logging
from sqlalchemy import create_engine, text

# Set up logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("nexus.embeddings")

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Try to load settings using centralized config loader
try:
    from nexus.config import load_settings_as_dict
    _all_settings = load_settings_as_dict()
    SETTINGS = _all_settings.get("Agent Settings", {}).get("MEMNON", {})
except Exception as e:
    logger.warning(f"Could not load settings via config loader: {e}")
    SETTINGS = {}

def get_model_dimensions(model_name: str) -> int:
    """Get the dimensions for a model name"""
    # First check settings
    if SETTINGS.get("models"):
        model_key = model_name.replace("/", "_")
        if model_key in SETTINGS["models"]:
            dimensions = SETTINGS["models"][model_key].get("dimensions")
            if dimensions:
                return dimensions
    
    # Hard-coded fallbacks
    model_dimensions = {
        "bge-small-custom": 384,
        "bge-small-en": 384,
        "bge-small-en-v1.5": 384,
        "infly/inf-retriever-v1-1.5b": 1536,
        "infly/inf-retriever-v1": 3584,
        "bge-large-en-v1.5": 1024,
        "bge-large-en": 1024,
        "e5-large-v2": 1024,
    }
    
    # Check for exact match
    if model_name in model_dimensions:
        return model_dimensions[model_name]
    
    # Check for partial match
    for name, dim in model_dimensions.items():
        if name in model_name:
            return dim
    
    # Default
    logger.warning(f"Could not determine dimensions for {model_name}, using default (1024)")
    return 1024

def get_table_name(model_name: str) -> str:
    """Get table name for a model"""
    dimensions = get_model_dimensions(model_name)
    dim_str = f"{dimensions:04d}"  # Format with leading zeros
    # PostgreSQL converts identifiers to lowercase by default
    return f"chunk_embeddings_{dim_str}d"

def create_vector_indexes(model_name: str, db_url: str = None):
    """
    Create optimized vector indexes for a model's embedding table
    
    Args:
        model_name: Name of the embedding model
        db_url: Database URL (optional)
    
    Returns:
        True if indexes were created successfully, False otherwise
    """
    # Set default db_url if not provided
    if not db_url:
        db_url = SETTINGS.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
    
    # Get dimensions and table name
    dimensions = get_model_dimensions(model_name)
    table_name = get_table_name(model_name)
    
    logger.info(f"Creating vector indexes for {model_name} ({dimensions}D)")
    logger.info(f"Table: {table_name}")
    
    # Connect to database
    engine = create_engine(db_url)
    
    # First check if table exists and has data
    with engine.connect() as conn:
        # Check if table exists
        check_sql = f"""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = '{table_name}'
        );
        """
        table_exists = conn.execute(text(check_sql)).scalar()
        
        if not table_exists:
            logger.error(f"Table {table_name} does not exist!")
            return False
        
        # Count embeddings
        count_sql = f"""
        SELECT COUNT(*) FROM {table_name} 
        WHERE model = :model_name;
        """
        count = conn.execute(text(count_sql), {"model_name": model_name}).scalar()
        
        logger.info(f"Found {count} embeddings for {model_name}")
        
        if count == 0:
            logger.warning("No embeddings found for this model!")
            return False
        
        # Check for existing vector indexes
        index_sql = f"""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = '{table_name.lower()}' 
        AND indexdef LIKE '%vector_cosine_ops%';
        """
        indexes = list(conn.execute(text(index_sql)))
        
        if indexes:
            logger.info("Vector indexes already exist:")
            for idx in indexes:
                logger.info(f"- {idx[0]}: {idx[1]}")
            
            # Ask for confirmation before recreating
            if input("Indexes already exist. Recreate? (y/n): ").lower() != 'y':
                logger.info("Keeping existing indexes")
                return True
            
            # Drop existing vector indexes
            for idx in indexes:
                drop_sql = f"DROP INDEX IF EXISTS {idx[0]};"
                conn.execute(text(drop_sql))
                logger.info(f"Dropped index: {idx[0]}")
            
            conn.commit()
    
    success = False
    
    # Now create the vector indexes based on dimensions
    with engine.begin() as conn:
        # Create specialized indexes based on dimensions
        if dimensions <= 2000:
            # For lower dimensions, create IVFFLAT index
            try:
                logger.info(f"Creating IVFFLAT index for {dimensions}D vectors...")
                start_time = time.time()
                
                ivf_sql = f"""
                CREATE INDEX {table_name}_ivf_idx 
                ON {table_name} USING ivfflat (embedding vector_cosine_ops)
                WITH (lists=100);
                """
                conn.execute(text(ivf_sql))
                
                elapsed_time = time.time() - start_time
                logger.info(f"✓ Created IVFFLAT index in {elapsed_time:.2f} seconds")
                success = True
            except Exception as e:
                logger.error(f"Failed to create IVFFLAT index: {e}")
                
                # Try plain index as fallback
                try:
                    logger.info("Creating plain index as fallback...")
                    plain_sql = f"""
                    CREATE INDEX {table_name}_plain_idx 
                    ON {table_name} (embedding vector_cosine_ops);
                    """
                    conn.execute(text(plain_sql))
                    logger.info("✓ Created plain vector index")
                    success = True
                except Exception as e2:
                    logger.error(f"Failed to create plain index: {e2}")
                
        else:
            # For super high dimensions, try but don't expect success
            logger.warning(f"Dimensions ({dimensions}) exceed 2000, vector indexes may not work")
            
            try:
                logger.info("Attempting to create plain vector index anyway...")
                plain_sql = f"""
                CREATE INDEX {table_name}_vector_idx 
                ON {table_name} (embedding vector_cosine_ops);
                """
                conn.execute(text(plain_sql))
                logger.info("✓ Successfully created plain vector index")
                success = True
            except Exception as e:
                logger.error(f"Failed to create vector index: {e}")
                logger.info("Will use sequential scan for searches")
    
    return success

def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(description="Create vector indexes for embedding tables")
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--db-url", help="Database URL")
    args = parser.parse_args()
    
    try:
        success = create_vector_indexes(args.model, args.db_url)
        if success:
            print("\nVector indexes created successfully!")
            return 0
        else:
            print("\nFailed to create vector indexes.")
            return 1
    except Exception as e:
        logger.error(f"Error creating vector indexes: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())