"""
Database access utilities for MEMNON.

This module provides functions for database operations, focusing on vector search
and hybrid search capabilities with PostgreSQL.
"""

import logging
import psycopg2
from typing import Dict, List, Tuple, Optional, Union, Any
from urllib.parse import urlparse

from nexus.agents.orrery.reconstruction import playable_narrative_predicate

from .embedding_tables import (
    PGVECTOR_ANN_INDEX_MAX_DIMENSIONS,
    parse_embedding_table_dimensions,
    retrograde_summary_table_name_for_dimensions,
    resolve_dimension_table,
    supports_pgvector_ann_index,
)

# Set up logging
logger = logging.getLogger("nexus.memnon.db_access")


def retrograde_summary_memory_id(summary_id: int) -> str:
    """Return the typed public identity for a Retrograde summary."""
    return f"retrograde_summary:{int(summary_id)}"


def _retrograde_summaries_exist(cursor) -> bool:
    """Return whether the dedicated Retrograde summary corpus exists."""
    return _embedding_table_exists(cursor, "retrograde_summaries")


def _retrograde_summaries_allowed(filters: Optional[Dict[str, Any]]) -> bool:
    """Keep narrative metadata filters scoped to narrative rows.

    Retrograde summaries do not own season, episode, or world-layer metadata.
    Excluding them when filters are supplied is safer than silently ignoring a
    caller's narrative constraint.
    """
    narrative_filter_keys = {"season", "episode", "world_layer"}
    return not any(key in narrative_filter_keys for key in (filters or {}))


def _retrograde_summary_result(
    summary_id: int,
    summary_text: str,
    world_event_id: int,
    recorded_at_chunk_id: Optional[int],
    chronology: Any,
    created_at: Any,
) -> Dict[str, Any]:
    """Build a retrieval result without inventing a narrative chunk id."""
    memory_id = retrograde_summary_memory_id(summary_id)
    serialized_created_at = (
        created_at.isoformat() if hasattr(created_at, "isoformat") else created_at
    )
    return {
        "id": memory_id,
        "memory_id": memory_id,
        "summary_id": int(summary_id),
        "world_event_id": int(world_event_id),
        "text": summary_text,
        "content_type": "retrograde_summary",
        "metadata": {
            "summary_id": int(summary_id),
            "world_event_id": int(world_event_id),
            "recorded_at_chunk_id": (
                int(recorded_at_chunk_id) if recorded_at_chunk_id is not None else None
            ),
            "chronology": chronology,
            "created_at": serialized_created_at,
        },
        "model_scores": {},
        "text_score": 0.0,
        "vector_score": 0.0,
    }


def _execute_retrograde_summary_vector_search(
    cursor,
    dimensions: int,
    embedding_value: str,
    model_key: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    """Return summary vector candidates for one model and dimension."""
    if not _retrograde_summaries_exist(cursor):
        return []
    table_name = retrograde_summary_table_name_for_dimensions(dimensions)
    if not _embedding_table_exists(cursor, table_name):
        return []

    cursor.execute(
        f"""
        SELECT
            rs.id,
            rs.summary_text,
            rs.world_event_id,
            rs.recorded_at_chunk_id,
            rs.chronology,
            rs.created_at,
            1 - (rse.embedding <=> %s::vector({dimensions})) AS score
        FROM retrograde_summaries rs
        JOIN {table_name} rse ON rs.id = rse.summary_id
        WHERE rse.model = %s
        ORDER BY score DESC
        LIMIT %s
        """,
        (embedding_value, model_key, top_k),
    )
    results: List[Dict[str, Any]] = []
    for row in cursor.fetchall():
        (
            summary_id,
            summary_text,
            world_event_id,
            recorded_at_chunk_id,
            chronology,
            created_at,
            score,
        ) = row
        result = _retrograde_summary_result(
            summary_id,
            summary_text,
            world_event_id,
            recorded_at_chunk_id,
            chronology,
            created_at,
        )
        numeric_score = float(score) if score is not None else 0.0
        result.update(
            {
                "model_scores": {model_key: numeric_score},
                "score": numeric_score,
                "source": "vector_search",
            }
        )
        results.append(result)
    return results


def _embedding_table_exists(cursor, table_name: str) -> bool:
    """Return whether an embedding table exists without creating it."""
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
        )
        """,
        (table_name,),
    )
    return bool(cursor.fetchone()[0])


def _list_existing_embedding_tables(cursor) -> List[str]:
    """List existing dimension-specific embedding tables."""
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name ~ '^chunk_embeddings_[0-9]+d$'
        ORDER BY table_name
        """
    )
    return [row[0] for row in cursor.fetchall()]


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
            database=database,
        )

        with conn.cursor() as cursor:
            # Check if vector extension exists
            cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            result = cursor.fetchone()

            if result:
                # Get extension version
                cursor.execute(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                )
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
        if "conn" in locals():
            conn.close()


def execute_vector_search(
    db_url: str,
    query_embedding: list,
    model_key: str,
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
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
            database=database,
        )

        results = {}

        try:
            with conn.cursor() as cursor:
                # Build filter conditions
                filter_conditions = []
                if filters:
                    if "season" in filters:
                        filter_conditions.append(f"cm.season = {filters['season']}")
                    if "episode" in filters:
                        filter_conditions.append(f"cm.episode = {filters['episode']}")
                    if "world_layer" in filters:
                        filter_conditions.append(
                            f"cm.world_layer = '{filters['world_layer']}'"
                        )

                filter_sql = " AND ".join(filter_conditions)
                if filter_sql:
                    filter_sql = " AND " + filter_sql

                # Get dimensions of the query embedding to determine which table to use
                dimensions = len(query_embedding)
                embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

                if _retrograde_summaries_allowed(filters):
                    for summary_result in _execute_retrograde_summary_vector_search(
                        cursor,
                        dimensions,
                        embedding_str,
                        model_key,
                        top_k,
                    ):
                        results[summary_result["id"]] = summary_result

                # Map dimensions to table names
                table_name = resolve_dimension_table(dimensions)
                if not _embedding_table_exists(cursor, table_name):
                    logger.warning(
                        "Narrative embedding table %s does not exist",
                        table_name,
                    )
                    return sorted(
                        results.values(),
                        key=lambda result: result.get("score", 0.0),
                        reverse=True,
                    )[:top_k]

                logger.info(
                    f"Using {table_name} for vector search with {dimensions}D embeddings"
                )

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
                    AND {playable_narrative_predicate()}
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
                    (
                        chunk_id,
                        raw_text,
                        season,
                        episode,
                        scene_number,
                        world_time,
                        score,
                    ) = result
                    chunk_id = str(chunk_id)

                    if chunk_id not in results:
                        results[chunk_id] = {
                            "id": chunk_id,
                            "chunk_id": chunk_id,
                            "text": raw_text,
                            "content_type": "narrative",
                            "metadata": {
                                "season": season,
                                "episode": episode,
                                "scene_number": scene_number,
                                "world_time": world_time,
                            },
                            "model_scores": {},
                            "score": float(score) if score is not None else 0.0,
                            "source": "vector_search",
                        }

                    # Store score from this model
                    results[chunk_id]["model_scores"][model_key] = (
                        float(score) if score is not None else 0.0
                    )

        finally:
            conn.close()

        # Rank both corpora together; neither corpus receives an implicit boost.
        return sorted(
            results.values(), key=lambda result: result.get("score", 0.0), reverse=True
        )[:top_k]

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
    stopwords = [
        "a",
        "an",
        "the",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "by",
        "of",
        "and",
        "or",
    ]
    query_words = [word for word in query_text.lower().split() if word not in stopwords]

    # Join with OR operator
    return " | ".join(query_words)


def execute_hybrid_search(
    db_url: str,
    query_text: str,
    query_embedding: list,
    model_key: str,
    vector_weight: float = 0.6,
    text_weight: float = 0.4,
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 10,
    idf_dict=None,
) -> List[Dict[str, Any]]:
    """Search narrative and Retrograde summary corpora with one model.

    The multi-model implementation is the canonical scorer. Supplying a
    single model with weight 1.0 keeps text/vector normalization and candidate
    ranking identical across both public paths, without a hidden corpus weight.
    """
    results = execute_multi_model_hybrid_search(
        db_url=db_url,
        query_text=query_text,
        query_embeddings={model_key: query_embedding},
        model_weights={model_key: 1.0},
        vector_weight=vector_weight,
        text_weight=text_weight,
        filters=filters,
        top_k=top_k,
        idf_dict=idf_dict,
    )
    for result in results:
        result["source"] = "hybrid_search"
    return results


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
            database=database,
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
                        logger.error(
                            "Please run scripts/install_pgvector_custom.sh first"
                        )
                        return False

                # Create GIN index for text search if it doesn't exist
                logger.info("Creating GIN index for text search...")
                cursor.execute(
                    """
                CREATE INDEX IF NOT EXISTS narrative_chunks_text_idx 
                ON narrative_chunks USING GIN (to_tsvector('english', raw_text))
                """
                )

                # Create indexes on existing dimension-specific tables only.
                for dim_table in _list_existing_embedding_tables(cursor):
                    try:
                        logger.info(f"Creating model index on {dim_table}...")
                        cursor.execute(
                            f"""
                        CREATE INDEX IF NOT EXISTS {dim_table}_model_idx 
                        ON {dim_table} (model)
                        """
                        )
                    except Exception as e:
                        logger.warning(f"Error creating index on {dim_table}: {e}")
                        continue

                # Create vector indexes for existing dimension-specific tables only.
                for dim_table in _list_existing_embedding_tables(cursor):
                    dimensions = parse_embedding_table_dimensions(dim_table)
                    if dimensions is None:
                        raise ValueError(
                            f"Cannot parse dimensions from table name: {dim_table!r}"
                        )
                    try:
                        if not supports_pgvector_ann_index(dimensions):
                            logger.info(
                                "Skipping ANN vector index for %s: pgvector "
                                "supports HNSW/IVFFlat indexes up to %sd "
                                "locally, and exact search remains available",
                                dim_table,
                                PGVECTOR_ANN_INDEX_MAX_DIMENSIONS,
                            )
                            continue

                        # Check for existing HNSW index
                        cursor.execute(
                            f"""
                        SELECT exists (
                            SELECT 1 FROM pg_indexes 
                            WHERE indexname = '{dim_table}_hnsw_idx'
                        )
                        """
                        )
                        has_hnsw_index = cursor.fetchone()[0]

                        if not has_hnsw_index:
                            logger.info(f"Creating HNSW index on {dim_table}...")
                            # Try to create an HNSW index with ivfflat fallback
                            try:
                                cursor.execute(
                                    f"""
                                CREATE INDEX {dim_table}_hnsw_idx ON {dim_table} 
                                USING hnsw (embedding vector_l2_ops) 
                                WITH (m = 16, ef_construction = 64)
                                """
                                )
                                logger.info(
                                    f"HNSW index created successfully for {dim_table}"
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to create HNSW index for {dim_table}: {e}"
                                )
                                logger.info(
                                    f"Trying to create IVFFlat index for {dim_table} as fallback..."
                                )

                                try:
                                    cursor.execute(
                                        f"""
                                    CREATE INDEX {dim_table}_ivfflat_idx ON {dim_table} 
                                    USING ivfflat (embedding vector_l2_ops) 
                                    WITH (lists = 100)
                                    """
                                    )
                                    logger.info(
                                        f"IVFFlat index created successfully for {dim_table}"
                                    )
                                except Exception as e2:
                                    logger.error(
                                        f"Failed to create IVFFlat index for {dim_table}: {e2}"
                                    )
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
    model_weights: Dict[str, float],  # Dictionary of model_key -> weight
    vector_weight: float = 0.6,
    text_weight: float = 0.4,
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 10,
    idf_dict=None,
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
            logger.warning(
                f"Vector weight ({vector_weight}) + text weight ({text_weight}) != 1.0. Normalizing."
            )
            total = vector_weight + text_weight
            vector_weight = vector_weight / total
            text_weight = text_weight / total

        # Ensure model weights are normalized
        total_weight = sum(model_weights.values())
        if total_weight != 1.0 and total_weight > 0:
            logger.warning(f"Model weights sum to {total_weight}, normalizing to 1.0")
            model_weights = {
                model: weight / total_weight for model, weight in model_weights.items()
            }

        logger.debug(
            f"Multi-model hybrid search weights: vector={vector_weight}, text={text_weight}"
        )
        logger.debug(f"Model weights: {model_weights}")

        # Connect to the database
        conn = psycopg2.connect(
            host=hostname,
            port=port,
            user=username,
            password=password,
            database=database,
        )

        results = {}  # Will hold all results by chunk_id

        try:
            with conn.cursor() as cursor:
                # Build filter conditions
                filter_conditions = []
                if filters:
                    if "season" in filters:
                        filter_conditions.append(f"cm.season = {filters['season']}")
                    if "episode" in filters:
                        filter_conditions.append(f"cm.episode = {filters['episode']}")
                    if "world_layer" in filters:
                        filter_conditions.append(
                            f"cm.world_layer = '{filters['world_layer']}'"
                        )

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
                    AND {playable_narrative_predicate()}
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
                    AND {playable_narrative_predicate()}
                    {filter_sql}
                ORDER BY
                    text_score DESC
                LIMIT %s
                """

                text_rows = []
                text_query_kind = ""
                text_query_value = ""

                weighted_query = ""
                if idf_dict and hasattr(idf_dict, "generate_weighted_query"):
                    weighted_query = idf_dict.generate_weighted_query(query_text)

                if weighted_query:
                    logger.info(
                        f"Text search using weighted to_tsquery: '{weighted_query}'"
                    )
                    cursor.execute(
                        text_search_sql_tsquery,
                        (weighted_query, weighted_query, top_k * 3),
                    )
                    text_rows = cursor.fetchall()
                    text_query_kind = "to_tsquery"
                    text_query_value = weighted_query

                if not text_rows:
                    prepared_query = prepare_tsquery(query_text)
                    if prepared_query:
                        logger.info(
                            f"Text search using OR-based query: '{prepared_query}'"
                        )
                        cursor.execute(
                            text_search_sql_tsquery,
                            (prepared_query, prepared_query, top_k * 3),
                        )
                        text_rows = cursor.fetchall()
                        text_query_kind = "to_tsquery"
                        text_query_value = prepared_query

                if not text_rows:
                    logger.info(
                        f"Text search using websearch_to_tsquery fallback: '{query_text}'"
                    )
                    cursor.execute(
                        text_search_sql_websearch, (query_text, query_text, top_k * 3)
                    )
                    text_rows = cursor.fetchall()
                    text_query_kind = "websearch_to_tsquery"
                    text_query_value = query_text

                all_text_scores = []

                # First pass: collect all text scores to find max for normalization
                for result in text_rows:
                    (
                        chunk_id,
                        raw_text,
                        season,
                        episode,
                        scene_number,
                        world_time,
                        text_score,
                    ) = result
                    text_score = float(text_score)
                    all_text_scores.append(text_score)
                    chunk_id = str(chunk_id)

                    if chunk_id not in results:
                        results[chunk_id] = {
                            "id": chunk_id,
                            "chunk_id": chunk_id,
                            "text": raw_text,
                            "content_type": "narrative",
                            "metadata": {
                                "season": season,
                                "episode": episode,
                                "scene_number": scene_number,
                                "world_time": world_time,
                            },
                            "model_scores": {},  # Will store scores for each model
                            "text_score": 0.0,  # Will be normalized
                            "vector_score": 0.0,  # Will be calculated as weighted average of model scores
                            "raw_text_score": text_score,  # Keep raw score temporarily
                        }
                    else:
                        results[chunk_id]["raw_text_score"] = text_score

                # Search the dedicated summary corpus with the same query form
                # and normalize it in the same score population. No corpus
                # multiplier is applied before ranking.
                if (
                    text_query_value
                    and _retrograde_summaries_allowed(filters)
                    and _retrograde_summaries_exist(cursor)
                ):
                    summary_query_function = (
                        "websearch_to_tsquery"
                        if text_query_kind == "websearch_to_tsquery"
                        else "to_tsquery"
                    )
                    cursor.execute(
                        f"""
                        SELECT
                            rs.id,
                            rs.summary_text,
                            rs.world_event_id,
                            rs.recorded_at_chunk_id,
                            rs.chronology,
                            rs.created_at,
                            ts_rank(
                                to_tsvector('english', rs.summary_text),
                                {summary_query_function}('english', %s)
                            ) AS text_score
                        FROM retrograde_summaries rs
                        WHERE to_tsvector('english', rs.summary_text)
                              @@ {summary_query_function}('english', %s)
                        ORDER BY text_score DESC
                        LIMIT %s
                        """,
                        (text_query_value, text_query_value, top_k * 3),
                    )
                    for row in cursor.fetchall():
                        (
                            summary_id,
                            summary_text,
                            world_event_id,
                            recorded_at_chunk_id,
                            chronology,
                            created_at,
                            text_score,
                        ) = row
                        text_score = float(text_score)
                        all_text_scores.append(text_score)
                        memory_id = retrograde_summary_memory_id(summary_id)
                        summary_result = _retrograde_summary_result(
                            summary_id,
                            summary_text,
                            world_event_id,
                            recorded_at_chunk_id,
                            chronology,
                            created_at,
                        )
                        summary_result["raw_text_score"] = text_score
                        results[memory_id] = summary_result

                # Find max text score for normalization (if any results)
                max_text_score = max(all_text_scores) if all_text_scores else 1.0
                logger.info(f"Normalizing text scores with max value: {max_text_score}")

                # Normalize text scores
                for chunk_id, result in results.items():
                    if "raw_text_score" in result:
                        # Normalize to 0-1 range
                        result["text_score"] = (
                            result["raw_text_score"] / max_text_score
                            if max_text_score > 0
                            else 0.0
                        )
                        # Remove temporary raw score
                        del result["raw_text_score"]

                logger.info(
                    f"Text search found {len(results)} results with non-zero scores"
                )

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
                            AND {playable_narrative_predicate()}
                            {filter_sql}
                        LIMIT %s
                        """
                        cursor.execute(like_sql, (single, top_k * 3))
                        for row in cursor.fetchall():
                            (
                                chunk_id,
                                raw_text,
                                season,
                                episode,
                                scene_number,
                                world_time,
                            ) = row
                            chunk_id = str(chunk_id)
                            if chunk_id not in results:
                                results[chunk_id] = {
                                    "id": chunk_id,
                                    "chunk_id": chunk_id,
                                    "text": raw_text,
                                    "content_type": "narrative",
                                    "metadata": {
                                        "season": season,
                                        "episode": episode,
                                        "scene_number": scene_number,
                                        "world_time": world_time,
                                    },
                                    "model_scores": {},
                                    "text_score": 0.05,
                                    "vector_score": 0.0,
                                }

                        if _retrograde_summaries_allowed(
                            filters
                        ) and _retrograde_summaries_exist(cursor):
                            cursor.execute(
                                """
                                SELECT
                                    id,
                                    summary_text,
                                    world_event_id,
                                    recorded_at_chunk_id,
                                    chronology,
                                    created_at
                                FROM retrograde_summaries
                                WHERE summary_text ILIKE '%%' || %s || '%%'
                                LIMIT %s
                                """,
                                (single, top_k * 3),
                            )
                            for row in cursor.fetchall():
                                summary_result = _retrograde_summary_result(*row)
                                summary_result["text_score"] = 0.05
                                results[summary_result["id"]] = summary_result

                # Now run vector searches for each model
                for model_key, embedding in query_embeddings.items():
                    if model_key not in model_weights or model_weights[model_key] <= 0:
                        logger.debug(
                            f"Skipping model {model_key} (zero or negative weight)"
                        )
                        continue

                    # Skip if embedding generation failed
                    if embedding is None:
                        logger.warning(
                            f"Skipping model {model_key} (embedding is None)"
                        )
                        continue

                    logger.info(f"Running vector search for model {model_key}")

                    # Get dimensions of the query embedding to determine which table to use
                    dimensions = len(embedding)

                    # Build embedding array as a string - pgvector expects
                    # [x,y,z] format for both independent corpora.
                    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

                    if _retrograde_summaries_allowed(
                        filters
                    ) and _retrograde_summaries_exist(cursor):
                        summary_table = retrograde_summary_table_name_for_dimensions(
                            dimensions
                        )
                        if _embedding_table_exists(cursor, summary_table):
                            cursor.execute(
                                f"""
                                SELECT
                                    rs.id,
                                    rs.summary_text,
                                    rs.world_event_id,
                                    rs.recorded_at_chunk_id,
                                    rs.chronology,
                                    rs.created_at,
                                    1 - (
                                        rse.embedding
                                        <=> %s::vector({dimensions})
                                    ) AS vector_score
                                FROM retrograde_summaries rs
                                JOIN {summary_table} rse
                                  ON rs.id = rse.summary_id
                                WHERE rse.model = %s
                                ORDER BY vector_score DESC
                                LIMIT %s
                                """,
                                (embedding_str, model_key, top_k * 3),
                            )
                            for row in cursor.fetchall():
                                (
                                    summary_id,
                                    summary_text,
                                    world_event_id,
                                    recorded_at_chunk_id,
                                    chronology,
                                    created_at,
                                    vector_score,
                                ) = row
                                vector_score = float(vector_score)
                                memory_id = retrograde_summary_memory_id(summary_id)
                                if memory_id in results:
                                    results[memory_id]["model_scores"][
                                        model_key
                                    ] = vector_score
                                    continue

                                calculated_text_score = 0.0
                                if text_query_value:
                                    summary_query_function = (
                                        "websearch_to_tsquery"
                                        if text_query_kind == "websearch_to_tsquery"
                                        else "to_tsquery"
                                    )
                                    cursor.execute(
                                        f"""
                                        SELECT ts_rank(
                                            to_tsvector('english', %s),
                                            {summary_query_function}('english', %s)
                                        )
                                        """,
                                        (summary_text, text_query_value),
                                    )
                                    fetched = cursor.fetchone()
                                    calculated_text_score = (
                                        fetched[0]
                                        if fetched and fetched[0] is not None
                                        else 0.0
                                    )

                                summary_result = _retrograde_summary_result(
                                    summary_id,
                                    summary_text,
                                    world_event_id,
                                    recorded_at_chunk_id,
                                    chronology,
                                    created_at,
                                )
                                summary_result.update(
                                    {
                                        "model_scores": {model_key: vector_score},
                                        "text_score": float(
                                            calculated_text_score / max_text_score
                                            if max_text_score > 0
                                            else 0.0
                                        ),
                                    }
                                )
                                results[memory_id] = summary_result

                    table_name = resolve_dimension_table(dimensions)
                    if not _embedding_table_exists(cursor, table_name):
                        logger.warning(
                            "Embedding table %s does not exist; skipping model %s",
                            table_name,
                            model_key,
                        )
                        continue  # Skip this model but continue with others

                    logger.debug(
                        f"Using {table_name} for model {model_key} with {dimensions}D embeddings"
                    )

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
                        AND {playable_narrative_predicate()}
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
                            results[chunk_id]["model_scores"][model_key] = vector_score
                        else:
                            # For chunks not found in text search, get full details
                            cursor.execute(
                                f"""
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
                            """,
                                (chunk_id,),
                            )

                            details = cursor.fetchone()
                            if details:
                                raw_text, season, episode, scene_number = details

                                # Calculate text score for this vector-only result using the same query form
                                calculated_text_score = 0.0
                                if text_query_value:
                                    if text_query_kind == "websearch_to_tsquery":
                                        cursor.execute(
                                            """
                                        SELECT ts_rank(to_tsvector('english', raw_text),
                                                websearch_to_tsquery('english', %s)) AS text_score
                                        FROM narrative_chunks
                                        WHERE id = %s
                                        """,
                                            (text_query_value, chunk_id),
                                        )
                                    else:
                                        cursor.execute(
                                            """
                                        SELECT ts_rank(to_tsvector('english', raw_text),
                                                to_tsquery('english', %s)) AS text_score
                                        FROM narrative_chunks
                                        WHERE id = %s
                                        """,
                                            (text_query_value, chunk_id),
                                        )

                                    fetched = cursor.fetchone()
                                    calculated_text_score = (
                                        fetched[0]
                                        if fetched and fetched[0] is not None
                                        else 0.0
                                    )

                                normalized_text_score = (
                                    calculated_text_score / max_text_score
                                    if max_text_score > 0
                                    else 0.0
                                )

                                # Add to results with this model's score
                                results[chunk_id] = {
                                    "id": chunk_id,
                                    "chunk_id": chunk_id,
                                    "text": raw_text,
                                    "content_type": "narrative",
                                    "metadata": {
                                        "season": season,
                                        "episode": episode,
                                        "scene_number": scene_number,
                                    },
                                    "model_scores": {model_key: vector_score},
                                    "text_score": float(normalized_text_score),
                                    "vector_score": 0.0,  # Will be calculated next
                                }

                # Calculate weighted average vector score using model weights
                logger.debug(
                    f"Calculating weighted average vector scores with weights: {model_weights}"
                )

                for chunk_id, result in results.items():
                    # Calculate weighted vector score based on all models
                    weighted_score = 0.0
                    total_weight = 0.0

                    for model, weight in model_weights.items():
                        if model in result.get("model_scores", {}):
                            model_score = result["model_scores"][model]
                            weighted_score += model_score * weight
                            total_weight += weight

                    # Store the weighted average vector score
                    if total_weight > 0:
                        result["vector_score"] = weighted_score / total_weight
                    else:
                        # Keep default 0.0 if no models contributed
                        pass

                    # Calculate combined score (weighted average of text and vector scores)
                    result["score"] = (result["vector_score"] * vector_weight) + (
                        result["text_score"] * text_weight
                    )
                    result["source"] = "multi_model_hybrid_search"

                # Create a list from the results dictionary and sort by score
                sorted_results = sorted(
                    results.values(), key=lambda x: x["score"], reverse=True
                )

                # Return only the top k results
                return sorted_results[:top_k]

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Error in multi-model hybrid search: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return []
