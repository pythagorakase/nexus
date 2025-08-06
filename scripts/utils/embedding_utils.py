#!/usr/bin/env python3
"""
Utility functions for working with embeddings from multiple tables based on model dimensions.
This helps maintain backward compatibility with the separate table approach.
"""

import os
import logging
from typing import Dict, List, Tuple, Any, Optional, Union
import numpy as np

# Set up logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Model dimension mapping
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
    "infly/inf-retriever-v1": 3584,  # Original model - too high for efficient indexing
    "infly/inf-retriever-v1-1.5b": 1536,  # Lightweight version with 1536 dimensions
}

def get_model_dimensions(model_name: str) -> int:
    """
    Get the vector dimensions for a given model name.
    
    Args:
        model_name (str): The name of the embedding model
        
    Returns:
        int: The number of dimensions (384, 1024, etc.)
    """
    # Check for exact matches
    if model_name in MODEL_DIMENSIONS:
        return MODEL_DIMENSIONS[model_name]
    
    # Check for partial matches
    for key, value in MODEL_DIMENSIONS.items():
        if key in model_name:
            return value
    
    # Default to 1024 for unknown models
    logger.warning(f"Unknown model '{model_name}', defaulting to 1024 dimensions")
    return 1024

def get_table_for_model(model_name: str) -> str:
    """
    Get the appropriate database table for a given model.
    
    Args:
        model_name (str): The name of the embedding model
        
    Returns:
        str: Table name for embeddings
    """
    # Use the new standardized naming convention
    dimensions = get_model_dimensions(model_name)
    dim_str = f"{dimensions:04d}"  # Format dimensions with leading zeros (e.g., 0384)
    # PostgreSQL converts identifiers to lowercase by default
    return f"chunk_embeddings_{dim_str}d"

def construct_vector_search_sql(
    model_name: str, 
    filter_conditions: Optional[str] = None,
    limit: int = 10
) -> Tuple[str, str]:
    """
    Construct SQL for vector similarity search based on model dimensions.
    
    Args:
        model_name (str): The name of the embedding model
        filter_conditions (str, optional): Additional WHERE clauses for filtering results
        limit (int): Maximum number of results to return
        
    Returns:
        Tuple[str, str]: (SQL query string, table name used)
    """
    table_name = get_table_for_model(model_name)
    dimensions = get_model_dimensions(model_name)
    
    # Alias for the embeddings table
    table_alias = "ce"  # Use consistent alias
    
    # For very high dimensions, PostgreSQL cannot efficiently use cosine operators directly in ORDER BY
    # For those cases, we need a different approach or a workaround
    if dimensions > 2000:
        # Warning about potential inefficiency
        logger.warning(f"Using high-dimensional vector ({dimensions}D) which may be slow without index")
        
    # Base SQL with proper table
    sql = f"""
    SELECT c.id, c.raw_text, {table_alias}.model, 
           ({table_alias}.embedding <=> :query_vector) AS distance,
           m.scene_number, m.scene_name, m.characters, m.location, m.time
    FROM {table_name} {table_alias}
    JOIN narrative_chunks c ON {table_alias}.chunk_id = c.id
    LEFT JOIN chunk_metadata m ON c.id = m.chunk_id
    WHERE {table_alias}.model = :model_name
    """
    
    # Add any additional filter conditions
    if filter_conditions:
        sql += f" AND {filter_conditions}"
    
    # Add order by and limit
    sql += f"""
    ORDER BY {table_alias}.embedding <=> :query_vector
    LIMIT {limit};
    """
    
    return sql, table_name
    
def construct_hybrid_search_sql(
    model_name: str,
    text_keywords: str,
    vector_weight: float = 0.6,
    text_weight: float = 0.4,
    filter_conditions: Optional[str] = None,
    limit: int = 10
) -> Tuple[str, str]:
    """
    Construct SQL for hybrid search combining vector similarity and text search.
    
    Args:
        model_name (str): The name of the embedding model
        text_keywords (str): Keywords for text search
        vector_weight (float): Weight for vector search score (0.0 to 1.0)
        text_weight (float): Weight for text search score (0.0 to 1.0)
        filter_conditions (str, optional): Additional WHERE clauses
        limit (int): Maximum number of results
        
    Returns:
        Tuple[str, str]: (SQL query string, table name used)
    """
    table_name = get_table_for_model(model_name)
    
    # Construct the SQL for hybrid search
    sql = f"""
    WITH vector_search AS (
        SELECT 
            c.id,
            ({table_name}.embedding <=> :query_vector) AS vector_distance
        FROM {table_name}
        JOIN narrative_chunks c ON {table_name}.chunk_id = c.id
        WHERE {table_name}.model = :model_name
    ),
    text_search AS (
        SELECT 
            id,
            ts_rank_cd(to_tsvector('english', raw_text), to_tsquery('english', :text_query)) AS text_score
        FROM narrative_chunks
        WHERE to_tsvector('english', raw_text) @@ to_tsquery('english', :text_query)
    )
    SELECT 
        c.id, 
        c.raw_text,
        :model_name AS model,
        vs.vector_distance,
        COALESCE(ts.text_score, 0) AS text_score,
        (vs.vector_distance * :vector_weight) + 
        (1 - COALESCE(ts.text_score, 0)) * :text_weight AS hybrid_score,
        m.scene_number, m.scene_name, m.characters, m.location, m.time
    FROM narrative_chunks c
    JOIN vector_search vs ON c.id = vs.id
    LEFT JOIN text_search ts ON c.id = ts.id
    LEFT JOIN chunk_metadata m ON c.id = m.chunk_id
    """
    
    # Add any additional filter conditions
    if filter_conditions:
        sql += f" WHERE {filter_conditions}"
    
    # Add order by and limit
    sql += """
    ORDER BY hybrid_score ASC
    LIMIT :limit;
    """
    
    return sql, table_name
    
def get_all_model_tables() -> List[str]:
    """
    Get a list of all embedding table names that use the new naming convention
    
    Returns:
        List of table names
    """
    tables = []
    
    for dim in [384, 1024, 1536]:
        dim_str = f"{dim:04d}"
        tables.append(f"chunk_embeddings_{dim_str}d")
    
    return tables

def normalize_vector(vector: Union[List[float], np.ndarray]) -> np.ndarray:
    """
    Normalize a vector to unit length.
    
    Args:
        vector (Union[List[float], np.ndarray]): Input vector
        
    Returns:
        np.ndarray: Normalized vector
    """
    if isinstance(vector, list):
        vector = np.array(vector, dtype=np.float32)
    
    norm = np.linalg.norm(vector)
    if norm > 0:
        return vector / norm
    return vector