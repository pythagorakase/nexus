#!/usr/bin/env python3
"""
Vector Migration Script for NEXUS

This script migrates the 384-dimension vectors from chunk_embeddings_small
to the main chunk_embeddings table with a new dimensions column.

Usage:
    python vector_migration.py
"""

import os
import sys
import logging
import json
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
import uuid
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("vector_migration.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.vector_migration")

def get_db_connection():
    """Get a database connection with pgvector extension."""
    conn = psycopg2.connect(
        dbname="NEXUS",
        user="pythagor",
        host="localhost"
    )
    # Register the vector extension
    register_vector(conn)
    return conn

def add_dimensions_column():
    """Add dimensions column to chunk_embeddings if it doesn't exist."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Check if column exists
            cur.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'chunk_embeddings' AND column_name = 'dimensions'
            """)
            
            if cur.fetchone() is None:
                # Add the column
                cur.execute("""
                ALTER TABLE chunk_embeddings ADD COLUMN dimensions INTEGER DEFAULT 1024;
                """)
                
                # Set default value for existing records
                cur.execute("""
                UPDATE chunk_embeddings SET dimensions = 1024;
                """)
                
                logger.info("Added dimensions column to chunk_embeddings table")
            else:
                logger.info("Dimensions column already exists")
            
            conn.commit()

def migrate_small_embeddings():
    """Migrate embeddings from chunk_embeddings_small to chunk_embeddings."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # First check if any small embeddings are already in the main table
            cur.execute("""
            SELECT COUNT(*) FROM chunk_embeddings 
            WHERE model = 'bge-small-custom' AND dimensions = 384
            """)
            count = cur.fetchone()[0]
            
            if count > 0:
                logger.info(f"Found {count} small embeddings already in chunk_embeddings")
                return
            
            # Get all embeddings from the small table
            cur.execute("""
            SELECT chunk_id, model, embedding, created_at
            FROM chunk_embeddings_small
            """)
            
            small_embeddings = cur.fetchall()
            logger.info(f"Found {len(small_embeddings)} embeddings to migrate")
            
            # Track progress
            processed = 0
            batch_size = 100
            
            # Process in batches
            for i in range(0, len(small_embeddings), batch_size):
                batch = small_embeddings[i:i+batch_size]
                
                for chunk_id, model, embedding, created_at in batch:
                    try:
                        # Get embedding as numpy array
                        embedding_array = np.array(embedding)
                        
                        # Pad with zeros to 1024 dimensions
                        padded_embedding = np.zeros(1024)
                        padded_embedding[:384] = embedding_array
                        
                        # Insert into the main table
                        cur.execute("""
                        INSERT INTO chunk_embeddings 
                        (chunk_id, model, embedding, dimensions, created_at) 
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (chunk_id, model) DO UPDATE
                        SET dimensions = EXCLUDED.dimensions,
                            embedding = EXCLUDED.embedding,
                            created_at = EXCLUDED.created_at
                        """, (chunk_id, model, padded_embedding, 384, created_at))
                        
                        processed += 1
                        
                        if processed % 100 == 0:
                            logger.info(f"Processed {processed}/{len(small_embeddings)} embeddings")
                    
                    except Exception as e:
                        logger.error(f"Error migrating embedding for chunk {chunk_id}: {e}")
                
                # Commit the batch
                conn.commit()
            
            logger.info(f"Successfully migrated {processed} out of {len(small_embeddings)} embeddings")

def verify_migration():
    """Verify that the migration was successful."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Count embeddings with dimensions=384
            cur.execute("""
            SELECT COUNT(*) FROM chunk_embeddings 
            WHERE dimensions = 384
            """)
            
            count_384 = cur.fetchone()[0]
            
            # Count total in small table
            cur.execute("""
            SELECT COUNT(*) FROM chunk_embeddings_small
            """)
            
            count_small = cur.fetchone()[0]
            
            logger.info(f"Verification: Found {count_384} embeddings with dimensions=384 in main table")
            logger.info(f"Original table has {count_small} embeddings")
            
            return count_384, count_small

def create_index():
    """Create an index on dimensions to speed up queries."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_dimensions 
                ON chunk_embeddings(dimensions)
                """)
                conn.commit()
                logger.info("Created index on dimensions column")
            except Exception as e:
                logger.warning(f"Error creating index: {e}")

def main():
    """Main entry point for the script."""
    print("Starting vector migration...")
    
    # Step 1: Add dimensions column
    add_dimensions_column()
    
    # Step 2: Migrate small embeddings
    migrate_small_embeddings()
    
    # Step 3: Verify the migration
    count_384, count_small = verify_migration()
    
    # Step 4: Create index
    create_index()
    
    print(f"Migration completed. Found {count_384} migrated embeddings out of {count_small} in source table.")
    
    if count_384 == count_small:
        print("All embeddings successfully migrated.")
        print("You can safely drop the old table with: DROP TABLE chunk_embeddings_small;")
    else:
        print(f"Warning: {count_small - count_384} embeddings were not migrated.")

if __name__ == "__main__":
    main()