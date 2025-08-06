"""
Temporal Search Utilities for MEMNON

This module extends MEMNON's search capabilities with time-awareness.
It implements functions for normalizing temporal positions, detecting
temporal queries, and boosting search results based on temporal relevance.
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple, Union, Set

# Set up logging
logger = logging.getLogger("nexus.memnon.temporal_search")

# Define temporal query patterns
EARLY_PATTERNS = [
    r'\b(first|initial|earliest|beginning|start|origin|genesis|inception|commence|initiate)\b',
    r'\b(early|initially|originally|at first|in the beginning|at the start)\b',
    r'\b(how did .* begin|how .* start|what happened first|origin story)\b'
]

RECENT_PATTERNS = [
    r'\b(recent|latest|newest|current|last|most recent|now|ongoing|present|final)\b',
    r'\b(currently|these days|nowadays|at the moment|lately|now|recently)\b',
    r'\b(what.s happening now|current state|latest developments|present situation)\b'
]

# Temporal query classification enum values
QUERY_TEMPORAL_EARLY = "early"
QUERY_TEMPORAL_RECENT = "recent"
QUERY_NON_TEMPORAL = "non_temporal"

def calculate_temporal_position(chunk_id: int, total_chunks: int) -> float:
    """
    Calculate the normalized temporal position of a chunk.
    
    Args:
        chunk_id: The ID of the chunk (assumed to be sequential in temporal order)
        total_chunks: Total number of chunks in the corpus
        
    Returns:
        A float between 0.0 (earliest) and 1.0 (most recent)
    """
    # Ensure valid inputs
    if total_chunks <= 0:
        logger.warning("Invalid total_chunks value (must be > 0), defaulting to 1")
        total_chunks = 1
        
    # Ensure chunk_id is valid
    normalized_chunk_id = max(0, min(chunk_id, total_chunks))
    
    # Calculate normalized position (0.0 to 1.0)
    # 0.0 = earliest/first chunk, 1.0 = latest/most recent chunk
    return normalized_chunk_id / total_chunks

def classify_temporal_query(query_text: str) -> str:
    """
    Analyze a query to determine if it has temporal aspects.
    
    Args:
        query_text: The search query text
        
    Returns:
        One of: "early", "recent", or "non_temporal"
    """
    # Convert to lowercase for easier pattern matching
    query_lower = query_text.lower()
    
    # Check for early/beginning temporal patterns
    for pattern in EARLY_PATTERNS:
        if re.search(pattern, query_lower):
            logger.debug(f"Query classified as 'early' temporal query: {query_text}")
            return QUERY_TEMPORAL_EARLY
            
    # Check for recent/latest temporal patterns
    for pattern in RECENT_PATTERNS:
        if re.search(pattern, query_lower):
            logger.debug(f"Query classified as 'recent' temporal query: {query_text}")
            return QUERY_TEMPORAL_RECENT
    
    # If no patterns match, it's not a temporal query
    return QUERY_NON_TEMPORAL

def apply_temporal_boost(
    base_score: float, 
    temporal_position: float, 
    query_classification: str,
    temporal_boost_factor: float = 0.5
) -> float:
    """
    Apply temporal boosting to a search result score.
    
    Args:
        base_score: Original search score (0.0-1.0)
        temporal_position: Normalized position in temporal sequence (0.0-1.0)
        query_classification: Temporal classification of the query
        temporal_boost_factor: How strongly to apply temporal boosting (0.0-1.0)
        
    Returns:
        Adjusted score with temporal boosting applied
    """
    # If query isn't temporal, return original score
    if query_classification == QUERY_NON_TEMPORAL:
        return base_score
    
    # Calculate temporal relevance based on query classification
    if query_classification == QUERY_TEMPORAL_EARLY:
        # For "early" queries, lower temporal_position is better (earlier chunks)
        # Invert temporal position: 1.0 becomes 0.0, and 0.0 becomes 1.0
        temporal_relevance = 1.0 - temporal_position
    else:  # QUERY_TEMPORAL_RECENT
        # For "recent" queries, higher temporal_position is better (newer chunks)
        temporal_relevance = temporal_position
    
    # Blend the original score with temporal relevance
    # temporal_boost_factor controls how much influence temporal position has
    adjusted_score = (1.0 - temporal_boost_factor) * base_score + temporal_boost_factor * temporal_relevance
    
    # Ensure score remains in valid range
    adjusted_score = max(0.0, min(1.0, adjusted_score))
    
    # Log significant score adjustments for debugging
    if abs(adjusted_score - base_score) > 0.2:
        logger.debug(f"Significant temporal adjustment: {base_score:.4f} -> {adjusted_score:.4f} "
                    f"(classification: {query_classification}, position: {temporal_position:.4f})")
    
    return adjusted_score

def get_total_chunks(db_conn) -> int:
    """
    Get the total number of chunks in the database.
    
    Args:
        db_conn: Database connection
        
    Returns:
        Integer count of total chunks
    """
    try:
        with db_conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM narrative_chunks")
            result = cursor.fetchone()
            if result and result[0]:
                return result[0]
    except Exception as e:
        logger.error(f"Error getting total chunk count: {e}")
    
    # Default fallback
    return 10000  # Arbitrary high number if we can't get the actual count

def execute_time_aware_search(
    db_url: str, 
    query_text: str, 
    query_embedding: list, 
    model_key: str,
    vector_weight: float = 0.6, 
    text_weight: float = 0.4,
    temporal_boost_factor: float = 0.5,
    filters: Dict[str, Any] = None, 
    top_k: int = 10, 
    idf_dict = None
) -> List[Dict[str, Any]]:
    """
    Execute a time-aware search combining vector similarity, text search, and temporal relevance.
    
    Args:
        db_url: PostgreSQL database URL
        query_text: The text query for keyword search
        query_embedding: Vector embedding for semantic search
        model_key: The embedding model key
        vector_weight: Weight to give vector search (0-1)
        text_weight: Weight to give text search (0-1)
        temporal_boost_factor: How much influence temporal factors have (0-1)
        filters: Optional metadata filters
        top_k: Maximum number of results to return
        idf_dict: Optional IDF dictionary for term weighting
        
    Returns:
        List of matching chunks with scores and metadata
    """
    # Import required modules here to avoid circular imports
    from urllib.parse import urlparse
    import psycopg2
    from . import db_access
    
    try:
        # First, classify the query for temporal aspects
        temporal_classification = classify_temporal_query(query_text)
        
        # If query is non-temporal, use the standard hybrid search
        if temporal_classification == QUERY_NON_TEMPORAL:
            logger.debug(f"Query is non-temporal, using standard hybrid search: {query_text}")
            return db_access.execute_hybrid_search(
                db_url, query_text, query_embedding, model_key,
                vector_weight, text_weight, filters, top_k, idf_dict
            )
        
        # For temporal queries, perform hybrid search but apply temporal boosting
        logger.info(f"Performing time-aware search with classification: {temporal_classification}")
        
        # Parse database URL
        parsed_url = urlparse(db_url)
        username = parsed_url.username
        password = parsed_url.password
        database = parsed_url.path[1:]  # Remove leading slash
        hostname = parsed_url.hostname
        port = parsed_url.port or 5432
        
        # Connect to the database
        conn = psycopg2.connect(
            host=hostname,
            port=port,
            user=username,
            password=password,
            database=database
        )
        
        # Get total number of chunks for normalization
        total_chunks = get_total_chunks(conn)
        logger.debug(f"Total chunks for temporal normalization: {total_chunks}")
        
        # Execute standard hybrid search but with increased result count
        # We'll retrieve more results and rerank them with temporal boosting
        original_results = db_access.execute_hybrid_search(
            db_url, query_text, query_embedding, model_key,
            vector_weight, text_weight, filters, 
            top_k * 2,  # Get more results for reranking
            idf_dict
        )
        
        # Apply temporal boosting to each result
        time_boosted_results = []
        for result in original_results:
            # Get chunk ID and convert to int
            chunk_id = int(result['id'])
            
            # Calculate temporal position
            temporal_position = calculate_temporal_position(chunk_id, total_chunks)
            
            # Get original score
            original_score = result['score']
            
            # Apply temporal boosting
            adjusted_score = apply_temporal_boost(
                original_score, 
                temporal_position, 
                temporal_classification,
                temporal_boost_factor
            )
            
            # Create a copy of the result with adjusted score
            boosted_result = result.copy()
            boosted_result['score'] = adjusted_score
            boosted_result['original_score'] = original_score  # Keep original for reference
            boosted_result['temporal_position'] = temporal_position  # Store for debugging
            boosted_result['source'] = 'time_aware_search'  # Update source
            
            time_boosted_results.append(boosted_result)
        
        # Sort results by the new adjusted score
        time_boosted_results.sort(key=lambda x: x['score'], reverse=True)
        
        # Return only the requested number of results
        return time_boosted_results[:top_k]
        
    except Exception as e:
        logger.error(f"Error in time-aware search: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Fall back to standard hybrid search
        logger.info("Falling back to standard hybrid search after error")
        return db_access.execute_hybrid_search(
            db_url, query_text, query_embedding, model_key,
            vector_weight, text_weight, filters, top_k, idf_dict
        )