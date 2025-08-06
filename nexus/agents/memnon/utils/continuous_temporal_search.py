"""
Continuous Temporal Search Utilities for MEMNON

This module extends MEMNON's search capabilities with more nuanced time-awareness.
It implements a continuous approach to analyzing temporal intent in queries and
applies scaled boosting based on how well a document's temporal position matches the query.
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple, Union, Set

# Set up logging
logger = logging.getLogger("nexus.memnon.continuous_temporal_search")

def analyze_temporal_intent(query_text: str) -> float:
    """
    Analyze the temporal intent of a query on a continuous scale from 0.0 to 1.0
    where 0.0 = strongly favors early content, 0.5 = temporally neutral, 1.0 = strongly favors recent content
    
    Args:
        query_text: The search query text
        
    Returns:
        Float from 0.0 to 1.0 representing the temporal intent
    """
    # Convert to lowercase for pattern matching
    query_lower = query_text.lower()
    
    # Define temporal signal words with weights
    early_signals = {
        'first': 0.1, 'initial': 0.1, 'earliest': 0.0, 'beginning': 0.1, 'start': 0.1,
        'origin': 0.0, 'genesis': 0.0, 'inception': 0.0, 'original': 0.1,
        'early on': 0.1, 'at first': 0.1, 'in the beginning': 0.0,
        'initially': 0.1, 'long ago': 0.1, 'originally': 0.1, 'before': 0.2
    }
    
    recent_signals = {
        'recent': 0.9, 'latest': 1.0, 'newest': 1.0, 'current': 0.9, 'last': 0.9,
        'now': 0.9, 'ongoing': 0.8, 'present': 0.9, 'final': 0.9, 'most recent': 1.0,
        'currently': 0.9, 'these days': 0.9, 'nowadays': 0.9, 'at the moment': 0.9,
        'recently': 0.9, 'later': 0.8, 'after': 0.7, 'eventually': 0.8
    }
    
    # Mid-narrative signals
    mid_signals = {
        'during': 0.5, 'middle': 0.5, 'midst': 0.5, 'meanwhile': 0.5, 'while': 0.5,
        'throughout': 0.5, 'subsequently': 0.6, 'then': 0.6, 'next': 0.6,
        'following': 0.6, 'after that': 0.6, 'afterwards': 0.6, 'ensuing': 0.6
    }
    
    # Look for temporal signals in the query
    temporal_score = 0.5  # Default neutral
    signals_found = 0
    
    # Check for early signals
    for signal, weight in early_signals.items():
        if signal in query_lower or re.search(r'\b' + re.escape(signal) + r'\b', query_lower):
            temporal_score = min(temporal_score, weight)  # Take the earliest signal found
            signals_found += 1
    
    # Check for recent signals
    for signal, weight in recent_signals.items():
        if signal in query_lower or re.search(r'\b' + re.escape(signal) + r'\b', query_lower):
            temporal_score = max(temporal_score, weight)  # Take the most recent signal found
            signals_found += 1
    
    # Check for mid-narrative signals - only apply if no strong early/recent signals
    if signals_found == 0:
        for signal, weight in mid_signals.items():
            if signal in query_lower or re.search(r'\b' + re.escape(signal) + r'\b', query_lower):
                temporal_score = weight
                signals_found += 1
    
    # If multiple conflicting signals are found, move slightly toward neutral
    if signals_found > 1:
        temporal_score = 0.5 + (temporal_score - 0.5) * 0.8
    
    # Check for event terms that might influence temporal positioning
    event_terms = {
        'begin': 0.2, 'start': 0.2, 'commence': 0.2, 'initiate': 0.2,
        'conclude': 0.8, 'end': 0.8, 'finish': 0.8, 'complete': 0.8,
        'happen': 0.5, 'occur': 0.5, 'take place': 0.5, 'event': 0.5,
        'change': 0.6, 'turn': 0.6, 'shift': 0.6, 'evolve': 0.7,
        'cause': 0.4, 'lead to': 0.6, 'result in': 0.7, 'aftermath': 0.8
    }
    
    for term, bias in event_terms.items():
        if term in query_lower or re.search(r'\b' + re.escape(term) + r'\b', query_lower):
            # Apply a more subtle influence for event terms
            temporal_score = temporal_score * 0.8 + bias * 0.2
    
    # Ensure score stays within 0-1 range
    return max(0.0, min(1.0, temporal_score))

def apply_continuous_temporal_boost(
    base_score: float, 
    temporal_position: float,  # 0.0 = earliest chunk, 1.0 = latest chunk
    query_temporal_intent: float,  # 0.0 = favors early, 1.0 = favors recent
    temporal_boost_factor: float = 0.3
) -> float:
    """
    Apply a continuous temporal boost based on how well the chunk's temporal position
    matches the query's temporal intent.
    
    Args:
        base_score: Original search score (0.0-1.0)
        temporal_position: Normalized position in temporal sequence (0.0-1.0)
        query_temporal_intent: Query's temporal intent on continuous scale (0.0-1.0)
        temporal_boost_factor: How strongly to apply temporal boosting (0.0-1.0)
        
    Returns:
        Adjusted score with temporal boosting applied
    """
    # Calculate how well this chunk's position matches the query's temporal intent
    # When intent is 0.0 (early), we want earlier chunks (lower temporal_position)
    # When intent is 1.0 (recent), we want recent chunks (higher temporal_position)
    
    # This creates a bell curve centered at the query's preferred temporal position
    match_score = 1.0 - abs(query_temporal_intent - temporal_position)
    
    # For strong early/recent intents, use a more aggressive curve
    intent_strength = abs(query_temporal_intent - 0.5) * 2  # 0 at neutral, 1 at extremes
    if intent_strength > 0.5:
        # For strong temporal intents, use a sharper falloff
        match_score = match_score ** 1.5
    
    # Apply the temporal boost weighted by the boost factor
    adjusted_score = base_score * (1.0 - temporal_boost_factor) + match_score * temporal_boost_factor
    
    # Ensure score remains in valid range
    adjusted_score = max(0.0, min(1.0, adjusted_score))
    
    # Log significant score adjustments for debugging
    if abs(adjusted_score - base_score) > 0.2:
        logger.debug(f"Significant temporal adjustment: {base_score:.4f} -> {adjusted_score:.4f} "
                   f"(intent: {query_temporal_intent:.2f}, position: {temporal_position:.4f})")
    
    return adjusted_score

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
    temporal_boost_factor: float = 0.3,
    filters: Dict[str, Any] = None, 
    top_k: int = 10, 
    idf_dict = None
) -> List[Dict[str, Any]]:
    """
    Execute a time-aware search using continuous temporal scaling.
    
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
        # Use continuous temporal intent analysis instead of categorical classification
        query_temporal_intent = analyze_temporal_intent(query_text)
        
        # Log the query's temporal intent
        logger.info(f"Query temporal intent: {query_temporal_intent:.2f} (0=early, 0.5=neutral, 1=recent)")
        
        # If query is temporally neutral (close to 0.5), apply minimal boosting
        is_temporal_query = abs(query_temporal_intent - 0.5) > 0.1
        effective_boost_factor = temporal_boost_factor if is_temporal_query else temporal_boost_factor * 0.5
        
        # If the query is essentially non-temporal, use standard search
        if abs(query_temporal_intent - 0.5) < 0.05 or effective_boost_factor < 0.01:
            logger.debug(f"Query is temporally neutral, using standard hybrid search: {query_text}")
            return db_access.execute_hybrid_search(
                db_url, query_text, query_embedding, model_key,
                vector_weight, text_weight, filters, top_k, idf_dict
            )
        
        # For temporal queries, perform hybrid search but apply temporal boosting
        logger.info(f"Performing time-aware search with intent score: {query_temporal_intent:.2f}")
        
        # Parse database URL
        parsed_url = urlparse(db_url)
        username = parsed_url.username
        password = parsed_url.password
        database = parsed_url.path[1:]  # Remove leading slash
        hostname = parsed_url.hostname
        port = parsed_url.port or 5432
        
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
        original_results = db_access.execute_hybrid_search(
            db_url, query_text, query_embedding, model_key,
            vector_weight, text_weight, filters, 
            top_k * 2,  # Get more results for reranking
            idf_dict
        )
        
        # Apply temporal boosting to each result using the continuous approach
        time_boosted_results = []
        for result in original_results:
            # Get chunk ID and convert to int
            chunk_id = int(result['id'])
            
            # Calculate temporal position
            temporal_position = calculate_temporal_position(chunk_id, total_chunks)
            
            # Get original score
            original_score = result['score']
            
            # Apply continuous temporal boosting
            adjusted_score = apply_continuous_temporal_boost(
                original_score, 
                temporal_position, 
                query_temporal_intent,
                effective_boost_factor
            )
            
            # Create a copy of the result with adjusted score
            boosted_result = result.copy()
            boosted_result['score'] = adjusted_score
            boosted_result['original_score'] = original_score  # Keep original for reference
            boosted_result['temporal_position'] = temporal_position  # Store for debugging
            boosted_result['temporal_intent'] = query_temporal_intent  # Store for debugging
            boosted_result['source'] = 'continuous_time_aware_search'  # Update source
            
            time_boosted_results.append(boosted_result)
        
        # Sort results by the new adjusted score
        time_boosted_results.sort(key=lambda x: x['score'], reverse=True)
        
        # Return only the requested number of results
        return time_boosted_results[:top_k]
        
    except Exception as e:
        logger.error(f"Error in continuous time-aware search: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Fall back to standard hybrid search
        logger.info("Falling back to standard hybrid search after error")
        return db_access.execute_hybrid_search(
            db_url, query_text, query_embedding, model_key,
            vector_weight, text_weight, filters, top_k, idf_dict
        )

def execute_multi_model_time_aware_search(
    db_url: str, 
    query_text: str, 
    query_embeddings: Dict[str, list],  # Dictionary of model_key -> embedding
    model_weights: Dict[str, float],    # Dictionary of model_key -> weight
    vector_weight: float = 0.6, 
    text_weight: float = 0.4,
    temporal_boost_factor: float = 0.3,
    filters: Dict[str, Any] = None, 
    top_k: int = 10, 
    idf_dict = None
) -> List[Dict[str, Any]]:
    """
    Execute a time-aware search using multiple embedding models simultaneously.
    
    Args:
        db_url: PostgreSQL database URL
        query_text: The text query for keyword search
        query_embeddings: Dictionary mapping model keys to their embeddings
        model_weights: Dictionary mapping model keys to their weights (0-1)
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
        # Use continuous temporal intent analysis instead of categorical classification
        query_temporal_intent = analyze_temporal_intent(query_text)
        
        # Log the query's temporal intent
        logger.info(f"Query temporal intent: {query_temporal_intent:.2f} (0=early, 0.5=neutral, 1=recent)")
        
        # If query is temporally neutral (close to 0.5), apply minimal boosting
        is_temporal_query = abs(query_temporal_intent - 0.5) > 0.1
        effective_boost_factor = temporal_boost_factor if is_temporal_query else temporal_boost_factor * 0.5
        
        # If the query is essentially non-temporal, use standard multi-model search
        if abs(query_temporal_intent - 0.5) < 0.05 or effective_boost_factor < 0.01:
            logger.debug(f"Query is temporally neutral, using standard multi-model hybrid search: {query_text}")
            return db_access.execute_multi_model_hybrid_search(
                db_url, query_text, query_embeddings, model_weights,
                vector_weight, text_weight, filters, top_k, idf_dict
            )
        
        # For temporal queries, perform multi-model hybrid search but apply temporal boosting
        logger.info(f"Performing multi-model time-aware search with intent score: {query_temporal_intent:.2f}")
        
        # Parse database URL
        parsed_url = urlparse(db_url)
        username = parsed_url.username
        password = parsed_url.password
        database = parsed_url.path[1:]  # Remove leading slash
        hostname = parsed_url.hostname
        port = parsed_url.port or 5432
        
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
        
        # Execute standard multi-model hybrid search but with increased result count
        original_results = db_access.execute_multi_model_hybrid_search(
            db_url, query_text, query_embeddings, model_weights,
            vector_weight, text_weight, filters, 
            top_k * 2,  # Get more results for reranking
            idf_dict
        )
        
        # Apply temporal boosting to each result using the continuous approach
        time_boosted_results = []
        for result in original_results:
            # Get chunk ID and convert to int
            chunk_id = int(result['id'])
            
            # Calculate temporal position
            temporal_position = calculate_temporal_position(chunk_id, total_chunks)
            
            # Get original score
            original_score = result['score']
            
            # Apply continuous temporal boosting
            adjusted_score = apply_continuous_temporal_boost(
                original_score, 
                temporal_position, 
                query_temporal_intent,
                effective_boost_factor
            )
            
            # Create a copy of the result with adjusted score
            boosted_result = result.copy()
            boosted_result['score'] = adjusted_score
            boosted_result['original_score'] = original_score  # Keep original for reference
            boosted_result['temporal_position'] = temporal_position  # Store for debugging
            boosted_result['temporal_intent'] = query_temporal_intent  # Store for debugging
            boosted_result['source'] = 'multi_model_time_aware_search'  # Update source
            
            time_boosted_results.append(boosted_result)
        
        # Sort results by the new adjusted score
        time_boosted_results.sort(key=lambda x: x['score'], reverse=True)
        
        # Return only the requested number of results
        return time_boosted_results[:top_k]
        
    except Exception as e:
        logger.error(f"Error in multi-model time-aware search: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Fall back to standard multi-model hybrid search
        logger.info("Falling back to standard multi-model hybrid search after error")
        return db_access.execute_multi_model_hybrid_search(
            db_url, query_text, query_embeddings, model_weights,
            vector_weight, text_weight, filters, top_k, idf_dict
        )