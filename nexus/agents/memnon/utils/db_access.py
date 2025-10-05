"""
Database access utilities for MEMNON.

This module provides functions for database operations, focusing on vector search
and hybrid search capabilities with PostgreSQL.
"""

import logging
import json
import psycopg2
from typing import Dict, List, Tuple, Optional, Union, Any, Set
from urllib.parse import urlparse

from .embedding_tables import DIMENSION_TABLES, resolve_dimension_table

# Set up logging
logger = logging.getLogger("nexus.memnon.db_access")

def check_vector_extension(db_url: str) -> bool:
    """
    Check if the pgvector extension is installed and available.
    
    Args:
        db_url: PostgreSQL database URL
        
    Returns:
        Boolean indicating if pgvector is available
    """
    try:
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
        
        with conn.cursor() as cursor:
            # Check if vector extension exists
            cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            result = cursor.fetchone()
            
            if result:
                # Get extension version
                cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                version = cursor.fetchone()[0]
                logger.info(f"pgvector extension found (version {version})")
                return True
            else:
                logger.warning("pgvector extension not found")
                return False
                
    except Exception as e:
        logger.error(f"Error checking pgvector extension: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def execute_vector_search(db_url: str, query_embedding: list, model_key: str, 
                         filters: Dict[str, Any] = None, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Execute a vector similarity search against the database using dimension-specific tables.
    
    Args:
        db_url: PostgreSQL database URL
        query_embedding: Vector embedding for the query
        model_key: The embedding model key
        filters: Optional metadata filters
        top_k: Maximum number of results to return
        
    Returns:
        List of matching chunks with scores and metadata
    """
    try:
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
        
        results = {}
        
        try:
            with conn.cursor() as cursor:
                # Build filter conditions
                filter_conditions = []
                if filters:
                    if 'season' in filters:
                        filter_conditions.append(f"cm.season = {filters['season']}")
                    if 'episode' in filters:
                        filter_conditions.append(f"cm.episode = {filters['episode']}")
                    if 'world_layer' in filters:
                        filter_conditions.append(f"cm.world_layer = '{filters['world_layer']}'")
                
                filter_sql = " AND ".join(filter_conditions)
                if filter_sql:
                    filter_sql = " AND " + filter_sql
                
                # Get dimensions of the query embedding to determine which table to use
                dimensions = len(query_embedding)
                
                # Map dimensions to table names
                table_name = resolve_dimension_table(dimensions)
                if not table_name:
                    logger.error(f"No dimension-specific table for {dimensions}D vectors")
                    return []
                
                logger.info(f"Using {table_name} for vector search with {dimensions}D embeddings")
                
                # Build embedding array as a string - pgvector expects [x,y,z] format
                embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
                
                # Use proper vector similarity search with the <=> operator
                # This works now that we're using the correct vector type tables
                sql = f"""
                SELECT 
                    nc.id, 
                    nc.raw_text, 
                    cm.season, 
                    cm.episode, 
                    cm.scene as scene_number,
                    nv.world_time,
                    1 - (ce.embedding <=> %s::vector({dimensions})) as score  -- Cosine similarity (1 - distance)
                FROM 
                    narrative_chunks nc
                JOIN 
                    {table_name} ce ON nc.id = ce.chunk_id
                JOIN 
                    chunk_metadata cm ON nc.id = cm.chunk_id
                LEFT JOIN
                    narrative_view nv ON nc.id = nv.id
                WHERE 
                    ce.model = %s
                    {filter_sql}
                ORDER BY
                    score DESC
                LIMIT 
                    %s
                """
                
                # Execute the query with vector similarity search
                cursor.execute(sql, (embedding_str, model_key, top_k))
                query_results = cursor.fetchall()
                
                # Process results
                for result in query_results:
                    chunk_id, raw_text, season, episode, scene_number, world_time, score = result
                    chunk_id = str(chunk_id)
                    
                    if chunk_id not in results:
                        results[chunk_id] = {
                            'id': chunk_id,
                            'chunk_id': chunk_id,
                            'text': raw_text,
                            'content_type': 'narrative',
                            'metadata': {
                                'season': season,
                                'episode': episode,
                                'scene_number': scene_number,
                                'world_time': world_time
                            },
                            'model_scores': {},
                            'score': float(score) if score is not None else 0.0,
                            'source': 'vector_search'
                        }
                    
                    # Store score from this model
                    results[chunk_id]['model_scores'][model_key] = float(score) if score is not None else 0.0
                
        finally:
            conn.close()
        
        # Return as list of values
        return list(results.values())
    
    except Exception as e:
        logger.error(f"Error in vector search: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

def prepare_tsquery(query_text: str) -> str:
    """
    Prepare a query string for use in to_tsquery().
    - Escapes single quotes
    - Handles special operators
    - Creates a proper tsquery expression
    
    Args:
        query_text: Original query text
        
    Returns:
        Properly escaped and formatted tsquery expression
    """
    # Remove any existing quotes that might cause problems
    query_text = query_text.replace("'", " ")
    
    # Split by spaces and filter out stopwords
    stopwords = ['a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'of', 'and', 'or']
    query_words = [word for word in query_text.lower().split() if word not in stopwords]
    
    # Join with OR operator
    return ' | '.join(query_words)

def execute_hybrid_search(db_url: str, query_text: str, query_embedding: list, 
                         model_key: str, vector_weight: float = 0.6, text_weight: float = 0.4, 
                         filters: Dict[str, Any] = None, top_k: int = 10, idf_dict = None) -> List[Dict[str, Any]]:
    """
    Execute a hybrid search combining vector similarity and text search.
    
    Args:
        db_url: PostgreSQL database URL
        query_text: The text query for keyword search
        query_embedding: Vector embedding for semantic search
        model_key: The embedding model key
        vector_weight: Weight to give vector search (0-1)
        text_weight: Weight to give text search (0-1)
        filters: Optional metadata filters
        top_k: Maximum number of results to return
        idf_dict: Optional IDF dictionary for term weighting
        
    Returns:
        List of matching chunks with scores and metadata
    """
    try:
        # Parse database URL
        parsed_url = urlparse(db_url)
        username = parsed_url.username
        password = parsed_url.password
        database = parsed_url.path[1:]  # Remove leading slash
        hostname = parsed_url.hostname
        port = parsed_url.port or 5432
        
        # Validate weights
        if vector_weight + text_weight != 1.0:
            logger.warning(f"Vector weight ({vector_weight}) + text weight ({text_weight}) != 1.0. Normalizing.")
            total = vector_weight + text_weight
            vector_weight = vector_weight / total
            text_weight = text_weight / total
        
        logger.debug(f"Hybrid search weights: vector={vector_weight}, text={text_weight}")
        
        # Connect to the database
        conn = psycopg2.connect(
            host=hostname,
            port=port,
            user=username,
            password=password,
            database=database
        )
        
        results = []
        
        try:
            with conn.cursor() as cursor:
                # Build filter conditions
                filter_conditions = []
                if filters:
                    if 'season' in filters:
                        filter_conditions.append(f"cm.season = {filters['season']}")
                    if 'episode' in filters:
                        filter_conditions.append(f"cm.episode = {filters['episode']}")
                    if 'world_layer' in filters:
                        filter_conditions.append(f"cm.world_layer = '{filters['world_layer']}'")
                
                filter_sql = " AND ".join(filter_conditions)
                if filter_sql:
                    filter_sql = " AND " + filter_sql
                
                # Check if vector extension is installed
                cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                has_vector_extension = cursor.fetchone() is not None
                
                if not has_vector_extension:
                    logger.error("Vector extension not installed. Install pgvector first.")
                    return []
                
                # Check if tsvector functionality is available for text search
                cursor.execute("SELECT 1 FROM pg_proc WHERE proname = 'to_tsvector'")
                has_text_search = cursor.fetchone() is not None
                
                if not has_text_search:
                    logger.error("Text search functionality not available.")
                    return []
                
                # When building the text search SQL query, use weighted query if IDF is available
                if idf_dict and hasattr(idf_dict, 'generate_weighted_query'):
                    weighted_query = idf_dict.generate_weighted_query(query_text)
                    logger.debug(f"Using weighted query: {weighted_query}")
                    
                    text_search_sql = f"""
                    SELECT 
                        nc.id, 
                        nc.raw_text,
                        cm.season, 
                        cm.episode, 
                        cm.scene as scene_number,
                        nv.world_time,
                        ts_rank(to_tsvector('english', nc.raw_text), 
                                to_tsquery('english', %s)) AS text_score
                    FROM 
                        narrative_chunks nc
                    JOIN 
                        chunk_metadata cm ON nc.id = cm.chunk_id
                    LEFT JOIN
                        narrative_view nv ON nc.id = nv.id
                    WHERE 
                        to_tsvector('english', nc.raw_text) @@ to_tsquery('english', %s)
                        {filter_sql}
                    ORDER BY 
                        text_score DESC
                    LIMIT %s
                    """
                    
                    # Use weighted query for both parameters
                    cursor.execute(text_search_sql, (
                        weighted_query, 
                        weighted_query, 
                        top_k * 2  # Double for text search
                    ))
                else:
                    # Use our new prepare_tsquery function to safely process the query
                    ts_query = prepare_tsquery(query_text)
                    
                    # Log the processed query with OR operators
                    logger.info(f"Text search using OR-based query: '{ts_query}'")
                    
                    text_search_sql = f"""
                    SELECT 
                        nc.id, 
                        nc.raw_text,
                        cm.season, 
                        cm.episode, 
                        cm.scene as scene_number,
                        nv.world_time,
                        ts_rank(to_tsvector('english', nc.raw_text), 
                                to_tsquery('english', %s)) AS text_score
                    FROM 
                        narrative_chunks nc
                    JOIN 
                        chunk_metadata cm ON nc.id = cm.chunk_id
                    LEFT JOIN
                        narrative_view nv ON nc.id = nv.id
                    WHERE 
                        to_tsvector('english', nc.raw_text) @@ to_tsquery('english', %s)
                        {filter_sql}
                    ORDER BY 
                        text_score DESC
                    LIMIT %s
                    """
                    
                    # Execute text search
                    cursor.execute(text_search_sql, (
                        ts_query,  # Use the processed query with OR operators 
                        ts_query,  # Use the processed query with OR operators
                        top_k * 2  # Double for text search
                    ))
                
                text_results = {}
                all_text_scores = []
                
                # First pass: collect all text scores to find max for normalization
                for result in cursor.fetchall():
                    chunk_id, raw_text, season, episode, scene_number, world_time, text_score = result
                    text_score = float(text_score)
                    all_text_scores.append(text_score)
                    chunk_id = str(chunk_id)
                    text_results[chunk_id] = {
                        'id': chunk_id,
                        'text': raw_text,
                        'metadata': {
                            'season': season,
                            'episode': episode,
                            'scene_number': scene_number,
                            'world_time': world_time
                        },
                        'raw_text_score': text_score,  # Keep raw score temporarily
                        'vector_score': 0.0  # Default until we get vector scores
                    }
                
                # Find max text score for normalization (if any results)
                max_text_score = max(all_text_scores) if all_text_scores else 1.0
                logger.info(f"Normalizing text scores with max value: {max_text_score}")
                
                # Second pass: normalize text scores to 0-1 range
                for chunk_id, result in text_results.items():
                    # Normalize to 0-1 range
                    normalized_text_score = result['raw_text_score'] / max_text_score if max_text_score > 0 else 0.0
                    result['text_score'] = normalized_text_score
                    # Remove temporary raw score
                    del result['raw_text_score']
                
                logger.info(f"Text search found {len(text_results)} results with non-zero scores")
                
                # Next, run proper vector search with dimension-specific tables
                logger.info("Executing vector search portion of hybrid search")
                
                # Get dimensions of the query embedding to determine which table to use
                dimensions = len(query_embedding)
                
                # Map dimensions to table names
                table_name = resolve_dimension_table(dimensions)
                if not table_name:
                    logger.error(f"No dimension-specific table for {dimensions}D vectors")
                    # Continue with text search only results
                    return [text_results[id] for id in text_results]
                
                logger.info(f"Using {table_name} for vector portion of hybrid search with {dimensions}D embeddings")
                
                # Build embedding array as a string - pgvector expects [x,y,z] format
                embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
                
                # Use proper vector search with cosine similarity
                vector_sql = f"""
                SELECT 
                    nc.id, 
                    1 - (ce.embedding <=> %s::vector({dimensions})) as vector_score  -- Cosine similarity (1 - distance)
                FROM 
                    narrative_chunks nc
                JOIN 
                    {table_name} ce ON nc.id = ce.chunk_id
                JOIN 
                    chunk_metadata cm ON nc.id = cm.chunk_id
                WHERE 
                    ce.model = %s
                    {filter_sql}
                ORDER BY
                    vector_score DESC
                LIMIT %s
                """
                
                logger.debug(f"Vector search SQL: {vector_sql}")
                
                # Execute proper vector search
                cursor.execute(vector_sql, (embedding_str, model_key, top_k * 2))
                
                # Process vector results
                for result in cursor.fetchall():
                    chunk_id, vector_score = result
                    chunk_id = str(chunk_id)
                    
                    if chunk_id in text_results:
                        # If already in text results, update vector score
                        text_results[chunk_id]['vector_score'] = float(vector_score)
                    else:
                        # Get the full details for this chunk
                        cursor.execute(f"""
                        SELECT 
                            nc.raw_text, 
                            cm.season, 
                            cm.episode, 
                            cm.scene as scene_number
                        FROM 
                            narrative_chunks nc
                        JOIN 
                            chunk_metadata cm ON nc.id = cm.chunk_id
                        WHERE 
                            nc.id = %s
                        """, (chunk_id,))
                        
                        # There should be exactly one result
                        details = cursor.fetchone()
                        if details:
                            raw_text, season, episode, scene_number = details
                            
                            # Calculate a proper text score for this document
                            # Use the same ts_query we prepared for text search
                            if idf_dict and hasattr(idf_dict, 'generate_weighted_query'):
                                # Use the weighted query for better scoring
                                weighted_query = idf_dict.generate_weighted_query(query_text)
                                cursor.execute("""
                                SELECT ts_rank(to_tsvector('english', raw_text), 
                                        to_tsquery('english', %s)) AS text_score
                                FROM narrative_chunks
                                WHERE id = %s
                                """, (weighted_query, chunk_id))
                            else:
                                # Use our prepared ts_query
                                ts_query = prepare_tsquery(query_text)
                                cursor.execute("""
                                SELECT ts_rank(to_tsvector('english', raw_text), 
                                        to_tsquery('english', %s)) AS text_score
                                FROM narrative_chunks
                                WHERE id = %s
                                """, (ts_query, chunk_id))
                            
                            calculated_text_score = cursor.fetchone()[0] or 0.0
                            
                            # Normalize the calculated score using the same max_text_score
                            normalized_text_score = calculated_text_score / max_text_score if max_text_score > 0 else 0.0
                            
                            logger.debug(f"Vector-only match {chunk_id} got calculated text_score: {normalized_text_score:.4f}")
                            
                            text_results[chunk_id] = {
                                'id': chunk_id,
                                'text': raw_text,
                                'metadata': {
                                    'season': season,
                                    'episode': episode,
                                    'scene_number': scene_number
                                },
                                'text_score': float(normalized_text_score),
                                'vector_score': float(vector_score)
                            }
                
                # Count how many were originally vector-only matches (before we calculated text scores)
                low_text_score_count = sum(1 for result in text_results.values() if result.get('text_score', 0) < 0.01)
                logger.info(f"Combined search found {len(text_results)} total results ({low_text_score_count} with very low text scores)")
                
                # Calculate combined scores
                for chunk_id, result in text_results.items():
                    # Make sure vector_score and text_score exist and are proper floats
                    if 'vector_score' not in result or result['vector_score'] is None:
                        # This is important - logging this as it's likely a key issue
                        logger.warning(f"Missing vector_score for chunk {chunk_id} - using default 0.0")
                        result['vector_score'] = 0.0
                    
                    if 'text_score' not in result or result['text_score'] is None:
                        logger.warning(f"Missing text_score for chunk {chunk_id} - using default 0.0")
                        result['text_score'] = 0.0
                        
                    # Ensure they're floats
                    vector_score = float(result['vector_score'])
                    text_score = float(result['text_score'])
                    
                    # Calculate weighted average
                    combined_score = (vector_score * vector_weight) + (text_score * text_weight)
                    
                    # Add to results list with explicit scores
                    results.append({
                        'id': chunk_id,
                        'chunk_id': chunk_id,
                        'text': result['text'],
                        'content_type': 'narrative',
                        'metadata': result['metadata'],
                        'score': float(combined_score),
                        'vector_score': vector_score,  # Explicitly using our converted value
                        'text_score': text_score,      # Explicitly using our converted value
                        'source': 'hybrid_search'
                    })
                
                # Sort by combined score
                results.sort(key=lambda x: x['score'], reverse=True)
                
                # Limit to top_k
                results = results[:top_k]
                
        finally:
            conn.close()
        
        return results
    
    except Exception as e:
        logger.error(f"Error in hybrid search: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

def setup_database_indexes(db_url: str) -> bool:
    """
    Set up necessary database indexes for efficient search.
    
    Args:
        db_url: PostgreSQL database URL
        
    Returns:
        Boolean indicating success
    """
    try:
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
        
        conn.autocommit = True
        
        try:
            with conn.cursor() as cursor:
                # Check if vector extension is installed
                cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                has_vector_extension = cursor.fetchone() is not None
                
                if not has_vector_extension:
                    logger.info("Creating vector extension...")
                    try:
                        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                        logger.info("Vector extension created successfully")
                    except Exception as e:
                        logger.error(f"Failed to create vector extension: {e}")
                        logger.error("Please run scripts/install_pgvector_custom.sh first")
                        return False
                
                # Create GIN index for text search if it doesn't exist
                logger.info("Creating GIN index for text search...")
                cursor.execute("""
                CREATE INDEX IF NOT EXISTS narrative_chunks_text_idx 
                ON narrative_chunks USING GIN (to_tsvector('english', raw_text))
                """)
                
                # Create indexes on dimension-specific tables if they don't exist
                existing_dimension_tables: Set[str] = set()
                if DIMENSION_TABLES:
                    cursor.execute(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = ANY(%s)
                        """,
                        (tuple(DIMENSION_TABLES),),
                    )
                    existing_dimension_tables = {row[0] for row in cursor.fetchall()}

                for dim_table in sorted(existing_dimension_tables):
                    try:
                        logger.info(f"Creating model index on {dim_table}...")
                        cursor.execute(f"""
                        CREATE INDEX IF NOT EXISTS {dim_table}_model_idx 
                        ON {dim_table} (model)
                        """)
                    except Exception as e:
                        logger.warning(f"Error creating index on {dim_table}: {e}")
                        continue
                
                # Create vector indexes for dimension-specific tables
                for dim_table in sorted(existing_dimension_tables):
                    try:
                        # Check if table exists
                        cursor.execute(f"""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = '{dim_table}'
                        )
                        """)
                        table_exists = cursor.fetchone()[0]
                        
                        if not table_exists:
                            logger.warning(f"Table {dim_table} does not exist, skipping index creation")
                            continue
                            
                        # Check for existing HNSW index
                        cursor.execute(f"""
                        SELECT exists (
                            SELECT 1 FROM pg_indexes 
                            WHERE indexname = '{dim_table}_hnsw_idx'
                        )
                        """)
                        has_hnsw_index = cursor.fetchone()[0]
                        
                        if not has_hnsw_index:
                            logger.info(f"Creating HNSW index on {dim_table}...")
                            # Try to create an HNSW index with ivfflat fallback
                            try:
                                cursor.execute(f"""
                                CREATE INDEX {dim_table}_hnsw_idx ON {dim_table} 
                                USING hnsw (embedding vector_l2_ops) 
                                WITH (m = 16, ef_construction = 64)
                                """)
                                logger.info(f"HNSW index created successfully for {dim_table}")
                            except Exception as e:
                                logger.warning(f"Failed to create HNSW index for {dim_table}: {e}")
                                logger.info(f"Trying to create IVFFlat index for {dim_table} as fallback...")
                                
                                try:
                                    cursor.execute(f"""
                                    CREATE INDEX {dim_table}_ivfflat_idx ON {dim_table} 
                                    USING ivfflat (embedding vector_l2_ops) 
                                    WITH (lists = 100)
                                    """)
                                    logger.info(f"IVFFlat index created successfully for {dim_table}")
                                except Exception as e2:
                                    logger.error(f"Failed to create IVFFlat index for {dim_table}: {e2}")
                                    logger.info(f"Using default index for {dim_table}")
                        else:
                            logger.info(f"HNSW index already exists for {dim_table}")
                    except Exception as e:
                        logger.error(f"Error setting up indexes for {dim_table}: {e}")
                        continue
                
                logger.info("Database indexes setup completed")
                return True
                
        finally:
            conn.close()
    
    except Exception as e:
        logger.error(f"Error setting up database indexes: {e}")
        return False

def execute_multi_model_hybrid_search(
    db_url: str,
    query_text: str,
    query_embeddings: Dict[str, list],  # Dictionary of model_key -> embedding
    model_weights: Dict[str, float],    # Dictionary of model_key -> weight
    vector_weight: float = 0.6,
    text_weight: float = 0.4,
    filters: Dict[str, Any] = None,
    top_k: int = 10,
    idf_dict = None
) -> List[Dict[str, Any]]:
    """
    Execute a hybrid search using multiple embedding models simultaneously.
    
    Args:
        db_url: PostgreSQL database URL
        query_text: The text query for keyword search
        query_embeddings: Dictionary mapping model keys to their embeddings
        model_weights: Dictionary mapping model keys to their weights (0-1)
        vector_weight: Weight to give vector search overall (0-1)
        text_weight: Weight to give text search overall (0-1)
        filters: Optional metadata filters
        top_k: Maximum number of results to return
        idf_dict: Optional IDF dictionary for term weighting
        
    Returns:
        List of matching chunks with scores and metadata
    """
    try:
        # Parse database URL
        parsed_url = urlparse(db_url)
        username = parsed_url.username
        password = parsed_url.password
        database = parsed_url.path[1:]  # Remove leading slash
        hostname = parsed_url.hostname
        port = parsed_url.port or 5432
        
        # Validate weights
        if vector_weight + text_weight != 1.0:
            logger.warning(f"Vector weight ({vector_weight}) + text weight ({text_weight}) != 1.0. Normalizing.")
            total = vector_weight + text_weight
            vector_weight = vector_weight / total
            text_weight = text_weight / total
        
        # Ensure model weights are normalized
        total_weight = sum(model_weights.values())
        if total_weight != 1.0 and total_weight > 0:
            logger.warning(f"Model weights sum to {total_weight}, normalizing to 1.0")
            model_weights = {model: weight/total_weight for model, weight in model_weights.items()}
        
        logger.debug(f"Multi-model hybrid search weights: vector={vector_weight}, text={text_weight}")
        logger.debug(f"Model weights: {model_weights}")
        
        # Connect to the database
        conn = psycopg2.connect(
            host=hostname,
            port=port,
            user=username,
            password=password,
            database=database
        )
        
        results = {}  # Will hold all results by chunk_id
        
        try:
            with conn.cursor() as cursor:
                # Build filter conditions
                filter_conditions = []
                if filters:
                    if 'season' in filters:
                        filter_conditions.append(f"cm.season = {filters['season']}")
                    if 'episode' in filters:
                        filter_conditions.append(f"cm.episode = {filters['episode']}")
                    if 'world_layer' in filters:
                        filter_conditions.append(f"cm.world_layer = '{filters['world_layer']}'")
                
                filter_sql = " AND ".join(filter_conditions)
                if filter_sql:
                    filter_sql = " AND " + filter_sql
                
                # First, run text search to get initial text scores
                text_search_sql_tsquery = f"""
                SELECT
                    nc.id,
                    nc.raw_text,
                    cm.season,
                    cm.episode,
                    cm.scene as scene_number,
                    nv.world_time,
                    ts_rank(to_tsvector('english', nc.raw_text),
                            to_tsquery('english', %s)) AS text_score
                FROM
                    narrative_chunks nc
                JOIN
                    chunk_metadata cm ON nc.id = cm.chunk_id
                LEFT JOIN
                    narrative_view nv ON nc.id = nv.id
                WHERE
                    to_tsvector('english', nc.raw_text) @@ to_tsquery('english', %s)
                    {filter_sql}
                ORDER BY
                    text_score DESC
                LIMIT %s
                """

                text_search_sql_websearch = f"""
                SELECT
                    nc.id,
                    nc.raw_text,
                    cm.season,
                    cm.episode,
                    cm.scene as scene_number,
                    nv.world_time,
                    ts_rank(to_tsvector('english', nc.raw_text),
                            websearch_to_tsquery('english', %s)) AS text_score
                FROM
                    narrative_chunks nc
                JOIN
                    chunk_metadata cm ON nc.id = cm.chunk_id
                LEFT JOIN
                    narrative_view nv ON nc.id = nv.id
                WHERE
                    to_tsvector('english', nc.raw_text) @@ websearch_to_tsquery('english', %s)
                    {filter_sql}
                ORDER BY
                    text_score DESC
                LIMIT %s
                """

                text_rows = []
                text_query_kind = ""
                text_query_value = ""

                weighted_query = ""
                if idf_dict and hasattr(idf_dict, 'generate_weighted_query'):
                    weighted_query = idf_dict.generate_weighted_query(query_text)

                if weighted_query:
                    logger.info(f"Text search using weighted to_tsquery: '{weighted_query}'")
                    cursor.execute(text_search_sql_tsquery, (
                        weighted_query,
                        weighted_query,
                        top_k * 3
                    ))
                    text_rows = cursor.fetchall()
                    text_query_kind = "to_tsquery"
                    text_query_value = weighted_query

                if not text_rows:
                    prepared_query = prepare_tsquery(query_text)
                    if prepared_query:
                        logger.info(f"Text search using OR-based query: '{prepared_query}'")
                        cursor.execute(text_search_sql_tsquery, (
                            prepared_query,
                            prepared_query,
                            top_k * 3
                        ))
                        text_rows = cursor.fetchall()
                        text_query_kind = "to_tsquery"
                        text_query_value = prepared_query

                if not text_rows:
                    logger.info(f"Text search using websearch_to_tsquery fallback: '{query_text}'")
                    cursor.execute(text_search_sql_websearch, (
                        query_text,
                        query_text,
                        top_k * 3
                    ))
                    text_rows = cursor.fetchall()
                    text_query_kind = "websearch_to_tsquery"
                    text_query_value = query_text

                all_text_scores = []

                # First pass: collect all text scores to find max for normalization
                for result in text_rows:
                    chunk_id, raw_text, season, episode, scene_number, world_time, text_score = result
                    text_score = float(text_score)
                    all_text_scores.append(text_score)
                    chunk_id = str(chunk_id)
                    
                    if chunk_id not in results:
                        results[chunk_id] = {
                            'id': chunk_id,
                            'chunk_id': chunk_id,
                            'text': raw_text,
                            'content_type': 'narrative',
                            'metadata': {
                                'season': season,
                                'episode': episode,
                                'scene_number': scene_number,
                                'world_time': world_time
                            },
                            'model_scores': {},  # Will store scores for each model
                            'text_score': 0.0,   # Will be normalized
                            'vector_score': 0.0, # Will be calculated as weighted average of model scores
                            'raw_text_score': text_score  # Keep raw score temporarily
                        }
                    else:
                        results[chunk_id]['raw_text_score'] = text_score
                
                # Find max text score for normalization (if any results)
                max_text_score = max(all_text_scores) if all_text_scores else 1.0
                logger.info(f"Normalizing text scores with max value: {max_text_score}")
                
                # Normalize text scores
                for chunk_id, result in results.items():
                    if 'raw_text_score' in result:
                        # Normalize to 0-1 range
                        result['text_score'] = result['raw_text_score'] / max_text_score if max_text_score > 0 else 0.0
                        # Remove temporary raw score
                        del result['raw_text_score']
                
                logger.info(f"Text search found {len(results)} results with non-zero scores")

                # Fallback: if no text results and single-token query, try ILIKE
                if not results:
                    single = (query_text or "").strip()
                    if single and len(single.split()) == 1:
                        like_sql = f"""
                        SELECT 
                            nc.id, 
                            nc.raw_text,
                            cm.season, 
                            cm.episode, 
                            cm.scene as scene_number,
                            nv.world_time
                        FROM 
                            narrative_chunks nc
                        JOIN 
                            chunk_metadata cm ON nc.id = cm.chunk_id
                        LEFT JOIN
                            narrative_view nv ON nc.id = nv.id
                        WHERE 
                            nc.raw_text ILIKE '%%' || %s || '%%'
                            {filter_sql}
                        LIMIT %s
                        """
                        cursor.execute(like_sql, (single, top_k * 3))
                        for row in cursor.fetchall():
                            chunk_id, raw_text, season, episode, scene_number, world_time = row
                            chunk_id = str(chunk_id)
                            if chunk_id not in results:
                                results[chunk_id] = {
                                    'id': chunk_id,
                                    'chunk_id': chunk_id,
                                    'text': raw_text,
                                    'content_type': 'narrative',
                                    'metadata': {
                                        'season': season,
                                        'episode': episode,
                                        'scene_number': scene_number,
                                        'world_time': world_time
                                    },
                                    'model_scores': {},
                                    'text_score': 0.05,
                                    'vector_score': 0.0
                                }
                
                # Now run vector searches for each model
                for model_key, embedding in query_embeddings.items():
                    if model_key not in model_weights or model_weights[model_key] <= 0:
                        logger.debug(f"Skipping model {model_key} (zero or negative weight)")
                        continue

                    logger.info(f"Running vector search for model {model_key}")

                    # Get dimensions of the query embedding to determine which table to use
                    dimensions = len(embedding)

                    table_name = resolve_dimension_table(dimensions)
                    if not table_name:
                        logger.error(f"No dimension-specific table for {dimensions}D vectors")
                        continue  # Skip this model but continue with others
                    
                    logger.debug(f"Using {table_name} for model {model_key} with {dimensions}D embeddings")
                    
                    # Build embedding array as a string - pgvector expects [x,y,z] format
                    embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'
                    
                    # Use proper vector search with cosine similarity
                    vector_sql = f"""
                    SELECT 
                        nc.id, 
                        1 - (ce.embedding <=> %s::vector({dimensions})) as vector_score  -- Cosine similarity (1 - distance)
                    FROM 
                        narrative_chunks nc
                    JOIN 
                        {table_name} ce ON nc.id = ce.chunk_id
                    JOIN 
                        chunk_metadata cm ON nc.id = cm.chunk_id
                    WHERE 
                        ce.model = %s
                        {filter_sql}
                    ORDER BY
                        vector_score DESC
                    LIMIT %s
                    """
                    
                    # Execute vector search for this model
                    cursor.execute(vector_sql, (embedding_str, model_key, top_k * 3))
                    
                    # Process vector results
                    for result in cursor.fetchall():
                        chunk_id, vector_score = result
                        chunk_id = str(chunk_id)
                        vector_score = float(vector_score)
                        
                        if chunk_id in results:
                            # Store model-specific score
                            results[chunk_id]['model_scores'][model_key] = vector_score
                        else:
                            # For chunks not found in text search, get full details
                            cursor.execute(f"""
                            SELECT 
                                nc.raw_text, 
                                cm.season, 
                                cm.episode, 
                                cm.scene as scene_number
                            FROM 
                                narrative_chunks nc
                            JOIN 
                                chunk_metadata cm ON nc.id = cm.chunk_id
                            WHERE 
                                nc.id = %s
                            """, (chunk_id,))
                            
                            details = cursor.fetchone()
                            if details:
                                raw_text, season, episode, scene_number = details
                                
                                # Calculate text score for this vector-only result using the same query form
                                calculated_text_score = 0.0
                                if text_query_value:
                                    if text_query_kind == "websearch_to_tsquery":
                                        cursor.execute("""
                                        SELECT ts_rank(to_tsvector('english', raw_text),
                                                websearch_to_tsquery('english', %s)) AS text_score
                                        FROM narrative_chunks
                                        WHERE id = %s
                                        """, (text_query_value, chunk_id))
                                    else:
                                        cursor.execute("""
                                        SELECT ts_rank(to_tsvector('english', raw_text),
                                                to_tsquery('english', %s)) AS text_score
                                        FROM narrative_chunks
                                        WHERE id = %s
                                        """, (text_query_value, chunk_id))

                                    fetched = cursor.fetchone()
                                    calculated_text_score = (fetched[0] if fetched and fetched[0] is not None else 0.0)

                                normalized_text_score = calculated_text_score / max_text_score if max_text_score > 0 else 0.0
                                
                                # Add to results with this model's score
                                results[chunk_id] = {
                                    'id': chunk_id,
                                    'chunk_id': chunk_id,
                                    'text': raw_text,
                                    'content_type': 'narrative',
                                    'metadata': {
                                        'season': season,
                                        'episode': episode,
                                        'scene_number': scene_number
                                    },
                                    'model_scores': {model_key: vector_score},
                                    'text_score': float(normalized_text_score),
                                    'vector_score': 0.0  # Will be calculated next
                                }
                
                # Calculate weighted average vector score using model weights
                logger.debug(f"Calculating weighted average vector scores with weights: {model_weights}")
                
                for chunk_id, result in results.items():
                    # Calculate weighted vector score based on all models
                    weighted_score = 0.0
                    total_weight = 0.0
                    
                    for model, weight in model_weights.items():
                        if model in result.get('model_scores', {}):
                            model_score = result['model_scores'][model]
                            weighted_score += model_score * weight
                            total_weight += weight
                    
                    # Store the weighted average vector score
                    if total_weight > 0:
                        result['vector_score'] = weighted_score / total_weight
                    else:
                        # Keep default 0.0 if no models contributed
                        pass
                    
                    # Calculate combined score (weighted average of text and vector scores)
                    result['score'] = (result['vector_score'] * vector_weight) + (result['text_score'] * text_weight)
                    result['source'] = 'multi_model_hybrid_search'
                
                # Create a list from the results dictionary and sort by score
                sorted_results = sorted(results.values(), key=lambda x: x['score'], reverse=True)
                
                # Return only the top k results
                return sorted_results[:top_k]
                
        finally:
            conn.close()
        
    except Exception as e:
        logger.error(f"Error in multi-model hybrid search: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []