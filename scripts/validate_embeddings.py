#!/usr/bin/env python3
"""
Validate that both chunk_embeddings and chunk_embeddings_small tables are correctly
storing and retrieving embeddings for their respective models.

This script:
1. Connects to the database
2. Counts embeddings in each table by model
3. Performs a simple vector similarity search with each model
4. Validates that the appropriate table is being used for each model
"""

import os
import sys
import argparse
import logging
from sqlalchemy import create_engine, text, Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import numpy as np
from pgvector.sqlalchemy import Vector

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define SQLAlchemy base
Base = declarative_base()

def get_db_connection_string():
    """Get the database connection string from environment variables."""
    DB_USER = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME", "nexus")
    
    return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def validate_table_counts(connection):
    """Count records in each table by model."""
    logger.info("Validating embedding counts by model...")
    
    # Count embeddings in chunk_embeddings (1024D)
    large_counts_sql = """
    SELECT model, COUNT(*) as count 
    FROM chunk_embeddings 
    GROUP BY model 
    ORDER BY model;
    """
    
    # Count embeddings in chunk_embeddings_small (384D)
    small_counts_sql = """
    SELECT model, COUNT(*) as count 
    FROM chunk_embeddings_small 
    GROUP BY model 
    ORDER BY model;
    """
    
    large_results = connection.execute(text(large_counts_sql)).fetchall()
    small_results = connection.execute(text(small_counts_sql)).fetchall()
    
    logger.info("CHUNK_EMBEDDINGS (1024D) counts by model:")
    for model, count in large_results:
        logger.info(f"  {model}: {count} embeddings")
    
    logger.info("CHUNK_EMBEDDINGS_SMALL (384D) counts by model:")
    for model, count in small_results:
        logger.info(f"  {model}: {count} embeddings")
    
    # Validate that models are in the right tables
    small_models = [row[0] for row in small_results]
    large_models = [row[0] for row in large_results]
    
    # Check if any BGE-small models are in the large table
    for model in large_models:
        if "bge-small" in model.lower():
            logger.warning(f"WARNING: Small model '{model}' found in chunk_embeddings (1024D) table")
    
    # Check if any large models are in the small table
    for model in small_models:
        if "bge-small" not in model.lower() and "bge-base" not in model.lower():
            logger.warning(f"WARNING: Large model '{model}' found in chunk_embeddings_small (384D) table")
    
    return large_results, small_results

def validate_vector_search(connection):
    """Perform a simple vector similarity search with each model type."""
    logger.info("Validating vector similarity search...")
    
    # Get a random vector from each table to use as a query
    random_large_vector_sql = """
    SELECT id, chunk_id, model, embedding 
    FROM chunk_embeddings 
    ORDER BY RANDOM() 
    LIMIT 1;
    """
    
    random_small_vector_sql = """
    SELECT id, chunk_id, model, embedding 
    FROM chunk_embeddings_small 
    ORDER BY RANDOM() 
    LIMIT 1;
    """
    
    # Execute queries to get random vectors
    large_vector_row = connection.execute(text(random_large_vector_sql)).fetchone()
    small_vector_row = connection.execute(text(random_small_vector_sql)).fetchone()
    
    if large_vector_row:
        large_id, large_chunk_id, large_model, large_embedding = large_vector_row
        logger.info(f"Testing similarity search with 1024D model: {large_model}")
        
        # Perform similarity search with large model
        large_search_sql = f"""
        SELECT c.id, c.content, ce.model, 
               (ce.embedding <=> :query_vector) AS distance
        FROM chunk_embeddings ce
        JOIN narrative_chunks c ON ce.chunk_id = c.id
        WHERE ce.model = :model_name
        ORDER BY ce.embedding <=> :query_vector
        LIMIT 5;
        """
        
        large_results = connection.execute(
            text(large_search_sql),
            {"query_vector": large_embedding, "model_name": large_model}
        ).fetchall()
        
        logger.info(f"Search results for {large_model} (showing 5):")
        for i, (id, content, model, distance) in enumerate(large_results, 1):
            logger.info(f"  {i}. Distance: {distance:.4f} - Content: {content[:50]}...")
    else:
        logger.warning("No vectors found in chunk_embeddings table")
    
    if small_vector_row:
        small_id, small_chunk_id, small_model, small_embedding = small_vector_row
        logger.info(f"Testing similarity search with 384D model: {small_model}")
        
        # Perform similarity search with small model
        small_search_sql = f"""
        SELECT c.id, c.content, ces.model, 
               (ces.embedding <=> :query_vector) AS distance
        FROM chunk_embeddings_small ces
        JOIN narrative_chunks c ON ces.chunk_id = c.id
        WHERE ces.model = :model_name
        ORDER BY ces.embedding <=> :query_vector
        LIMIT 5;
        """
        
        small_results = connection.execute(
            text(small_search_sql),
            {"query_vector": small_embedding, "model_name": small_model}
        ).fetchall()
        
        logger.info(f"Search results for {small_model} (showing 5):")
        for i, (id, content, model, distance) in enumerate(small_results, 1):
            logger.info(f"  {i}. Distance: {distance:.4f} - Content: {content[:50]}...")
    else:
        logger.warning("No vectors found in chunk_embeddings_small table")

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Validate embedding tables and models.')
    parser.add_argument('--connection', '-c', help='Database connection string')
    args = parser.parse_args()
    
    # Get database connection
    conn_string = args.connection if args.connection else get_db_connection_string()
    logger.info(f"Connecting to database: {conn_string.split('@')[1]}")
    
    try:
        # Create engine and connect
        engine = create_engine(conn_string)
        with engine.connect() as connection:
            # Run validations
            validate_table_counts(connection)
            validate_vector_search(connection)
            
        logger.info("Validation complete!")
        
    except Exception as e:
        logger.error(f"Error during validation: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()