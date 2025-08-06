"""
Search Manager for MEMNON Agent

Handles different search strategies and provides a unified interface for searching
across different data sources.
"""

import logging
import json
import re
from typing import Dict, List, Optional, Any, Set, Tuple, Union

# Import utility modules
from .db_access import execute_vector_search, execute_hybrid_search, execute_multi_model_hybrid_search, prepare_tsquery
from .continuous_temporal_search import execute_time_aware_search, execute_multi_model_time_aware_search, analyze_temporal_intent
from .idf_dictionary import IDFDictionary
from .embedding_manager import EmbeddingManager
from .query_analysis import QueryAnalyzer

logger = logging.getLogger("nexus.memnon.search")

class SearchManager:
    """
    Manages different search strategies for MEMNON
    """
    
    def __init__(self, 
                db_url: str, 
                embedding_manager: EmbeddingManager,
                idf_dictionary: IDFDictionary,
                settings: Dict[str, Any],
                retrieval_settings: Dict[str, Any]):
        """
        Initialize the SearchManager
        
        Args:
            db_url: PostgreSQL database URL
            embedding_manager: Instance of EmbeddingManager for generating embeddings
            idf_dictionary: IDF dictionary for term weighting
            settings: MEMNON agent settings
            retrieval_settings: Retrieval-specific settings
        """
        self.db_url = db_url
        self.embedding_manager = embedding_manager
        self.idf_dictionary = idf_dictionary
        self.settings = settings
        self.retrieval_settings = retrieval_settings
        
        # Initialize the query analyzer
        self.query_analyzer = QueryAnalyzer(settings)
        
        # Flag for testing
        self.force_text_first = False
        
        logger.info("SearchManager initialized")
    
    def perform_hybrid_search(self, query_text: str, filters: Dict[str, Any] = None, top_k: int = None) -> List[Dict[str, Any]]:
        """
        Perform hybrid search using both vector embeddings and text search.
        Uses all active embedding models with their configured weights.
        
        Args:
            query_text: The query text
            filters: Optional metadata filters to apply
            top_k: Maximum number of results to return
            
        Returns:
            List of matching chunks with scores and metadata
        """
        if top_k is None:
            top_k = self.retrieval_settings.get("default_top_k", 10)
        
        try:
            # Get hybrid search settings
            hybrid_config = self.settings.get("retrieval", {}).get("hybrid_search", {})
            if not hybrid_config.get("enabled", False):
                logger.warning("Hybrid search is disabled in settings")
                return []
            
            # Determine query type for weight adjustment using query analyzer
            query_info = self.query_analyzer.analyze_query(query_text)
            query_type = query_info.get("type", "general")
            logger.debug(f"Query classified as type: {query_type}")
            
            # Get weights based on query type or use defaults
            if hybrid_config.get("use_query_type_weights", False) and query_type in hybrid_config.get("weights_by_query_type", {}):
                weights = hybrid_config["weights_by_query_type"][query_type]
                vector_weight = weights.get("vector", 0.6)
                text_weight = weights.get("text", 0.4)
            else:
                vector_weight = hybrid_config.get("vector_weight_default", 0.6)
                text_weight = hybrid_config.get("text_weight_default", 0.4)
            
            # Normalize weights to ensure they sum to 1.0
            total_weight = vector_weight + text_weight
            if total_weight != 1.0:
                vector_weight = vector_weight / total_weight
                text_weight = text_weight / total_weight
            
            logger.debug(f"Using weights: vector={vector_weight}, text={text_weight}")
            
            # Gather all active models and their weights
            active_models = {}
            model_weights = {}
            
            for model_key in self.embedding_manager.get_available_models():
                if model_key in self.retrieval_settings["model_weights"]:
                    # Get the weight from the retrieval settings
                    model_weights[model_key] = self.retrieval_settings["model_weights"][model_key]
                    active_models[model_key] = True
            
            if not active_models:
                logger.error("No active embedding models found.")
                return []
            
            # Normalize model weights to sum to 1.0
            total_model_weight = sum(model_weights.values())
            if total_model_weight > 0:
                model_weights = {k: w/total_model_weight for k, w in model_weights.items()}
            
            logger.info(f"Using {len(active_models)} active models with weights: {model_weights}")
            
            # Generate embeddings for all active models
            query_embeddings = {}
            for model_key in active_models:
                try:
                    query_embeddings[model_key] = self.embedding_manager.generate_embedding(query_text, model_key)
                except Exception as e:
                    logger.error(f"Error generating embedding for model {model_key}: {e}")
            
            if not query_embeddings:
                logger.error("Failed to generate embeddings for any active model.")
                return []
            
            # Analyze the query's temporal intent on a continuous scale
            query_temporal_intent = analyze_temporal_intent(query_text)
            
            # Get default temporal boost factor from settings
            temporal_boost_factor = hybrid_config.get("temporal_boost_factor", 0.3)
            
            # Check if we should use query-type-specific temporal boost factors
            use_query_type_temporal_factors = hybrid_config.get("use_query_type_temporal_factors", False)
            
            # If enabled, get query-type-specific temporal boost factor
            if use_query_type_temporal_factors and query_type in hybrid_config.get("temporal_boost_factors", {}):
                query_temporal_factor = hybrid_config["temporal_boost_factors"][query_type]
                logger.debug(f"Using query-type-specific temporal boost factor for '{query_type}': {query_temporal_factor}")
                temporal_boost_factor = query_temporal_factor
            
            # Determine if this is a temporal query based on how far from neutral (0.5) the intent is
            is_temporal_query = abs(query_temporal_intent - 0.5) > 0.1
            
            # Determine if temporal boosting should be applied based on settings and query intent
            apply_temporal_boosting = temporal_boost_factor > 0.0 and is_temporal_query
            
            # If query has temporal aspects and boosting is enabled, use multi-model time-aware search
            if apply_temporal_boosting:
                logger.info(f"Using multi-model time-aware search for temporal query (intent: {query_temporal_intent:.2f}, boost factor: {temporal_boost_factor})")
                
                # Execute multi-model time-aware search
                results = execute_multi_model_time_aware_search(
                    db_url=self.db_url,
                    query_text=query_text,
                    query_embeddings=query_embeddings,
                    model_weights=model_weights,
                    vector_weight=vector_weight,
                    text_weight=text_weight,
                    temporal_boost_factor=temporal_boost_factor,
                    filters=filters,
                    top_k=top_k,
                    idf_dict=self.idf_dictionary
                )
            else:
                # Use standard multi-model hybrid search for non-temporal queries
                logger.debug("Using standard multi-model hybrid search for non-temporal query")
                
                # Execute multi-model hybrid search
                results = execute_multi_model_hybrid_search(
                    db_url=self.db_url,
                    query_text=query_text,
                    query_embeddings=query_embeddings,
                    model_weights=model_weights,
                    vector_weight=vector_weight,
                    text_weight=text_weight,
                    filters=filters,
                    top_k=top_k,
                    idf_dict=self.idf_dictionary
                )
            
            logger.info(f"Multi-model hybrid search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def query_vector_search(self, query_text: str, collections: List[str], filters: Dict[str, Any], top_k: int) -> List[Dict[str, Any]]:
        """
        Query the vector database for chunks similar to the query text.
        Uses all active embedding models with their configured weights.
        
        Args:
            query_text: The text to search for
            collections: Vector collection names to search in
            filters: Metadata filters to apply (season, episode, etc.)
            top_k: Maximum number of results to return
            
        Returns:
            List of matching chunks with scores and metadata
        """
        if top_k is None:
            top_k = self.retrieval_settings["default_top_k"]
        
        try:
            # Gather all active models and their weights
            active_models = {}
            model_weights = {}
            
            for model_key in self.embedding_manager.get_available_models():
                if model_key in self.retrieval_settings["model_weights"]:
                    # Get the weight from the retrieval settings
                    model_weights[model_key] = self.retrieval_settings["model_weights"][model_key]
                    active_models[model_key] = True
            
            if not active_models:
                logger.error("No active embedding models found.")
                return []
            
            # Normalize model weights to sum to 1.0
            total_model_weight = sum(model_weights.values())
            if total_model_weight > 0:
                model_weights = {k: w/total_model_weight for k, w in model_weights.items()}
            
            logger.info(f"Using {len(active_models)} active models with weights: {model_weights}")
            
            # Generate embeddings for all active models
            query_embeddings = {}
            for model_key in active_models:
                try:
                    query_embeddings[model_key] = self.embedding_manager.generate_embedding(query_text, model_key)
                except Exception as e:
                    logger.error(f"Error generating embedding for model {model_key}: {e}")
            
            if not query_embeddings:
                logger.error("Failed to generate embeddings for any active model.")
                return []

            # Use the multi-model hybrid search with 100% vector weight to effectively perform vector-only search
            results = execute_multi_model_hybrid_search(
                db_url=self.db_url,
                query_text=query_text,
                query_embeddings=query_embeddings,
                model_weights=model_weights,
                vector_weight=1.0,  # Use 100% vector weight for pure vector search
                text_weight=0.0,    # No text search weight
                filters=filters,
                top_k=top_k,
                idf_dict=self.idf_dictionary
            )
            
            logger.info(f"Multi-model vector search returned {len(results)} results")
            return results
        
        except Exception as e:
            logger.error(f"Error in vector search: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def query_text_search(self, query_text: str, session, filters: Dict[str, Any] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Perform a keyword-based text search on narrative chunks.
        
        Args:
            query_text: The text to search for
            session: SQLAlchemy session
            filters: Optional metadata filters
            limit: Maximum number of results to return
            
        Returns:
            List of matching chunks with scores and metadata
        """
        try:
            # Use prepare_tsquery for consistent processing
            processed_query = prepare_tsquery(query_text)
            
            # Build query with filters
            filter_conditions = []
            if filters:
                if 'season' in filters:
                    filter_conditions.append(f"cm.season = :season")
                if 'episode' in filters:
                    filter_conditions.append(f"cm.episode = :episode")
                if 'world_layer' in filters:
                    filter_conditions.append(f"cm.world_layer = :world_layer")
            
            filter_sql = " AND ".join(filter_conditions)
            if filter_sql:
                filter_sql = " AND " + filter_sql
            
            # Execute text search
            from sqlalchemy import text
            
            query_sql = f"""
            SELECT 
                nc.id, 
                nc.raw_text, 
                cm.season, 
                cm.episode, 
                cm.scene as scene_number,
                ts_rank(to_tsvector('english', nc.raw_text), to_tsquery('english', :query)) as score,
                ts_headline('english', nc.raw_text, to_tsquery('english', :query), 'MaxFragments=3, MinWords=15, MaxWords=35') as highlights
            FROM 
                narrative_chunks nc
            JOIN 
                chunk_metadata cm ON nc.id = cm.chunk_id
            WHERE 
                to_tsvector('english', nc.raw_text) @@ to_tsquery('english', :query)
                {filter_sql}
            ORDER BY 
                score DESC
            LIMIT 
                :limit
            """
            
            query_params = {"query": processed_query, "limit": limit}
            if filters:
                if 'season' in filters:
                    query_params["season"] = filters['season']
                if 'episode' in filters:
                    query_params["episode"] = filters['episode']
                if 'world_layer' in filters:
                    query_params["world_layer"] = filters['world_layer']
            
            result = session.execute(text(query_sql), query_params)
            
            # Process results
            text_results = []
            for row in result:
                chunk_id, raw_text, season, episode, scene_number, score, highlights = row
                
                text_results.append({
                    'id': str(chunk_id),
                    'chunk_id': str(chunk_id),
                    'text': raw_text,
                    'content_type': 'narrative',
                    'metadata': {
                        'season': season,
                        'episode': episode,
                        'scene_number': scene_number,
                        'highlights': highlights
                    },
                    'score': float(score),
                    'source': 'text_search'
                })
            
            return text_results
        
        except Exception as e:
            logger.error(f"Error in text search: {e}")
            return []
    
    def query_structured_data(self, query_text: str, session, table: str, filters: Dict[str, Any] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Query structured data tables.
        
        Args:
            query_text: The query text
            session: SQLAlchemy session
            table: The table to query
            filters: Optional metadata filters
            limit: Maximum number of results to return
            
        Returns:
            List of matching results
        """
        try:
            from sqlalchemy import text
            
            if table == "characters":
                # Query characters
                # First check for exact name matches
                name_match_query = text("""
                SELECT DISTINCT c.id, c.name, c.description, c.role, c.faction, c.status,
                       array_agg(DISTINCT ca.alias) as aliases
                FROM characters c
                LEFT JOIN character_aliases ca ON c.id = ca.character_id
                WHERE LOWER(c.name) = LOWER(:query)
                OR EXISTS (
                    SELECT 1 FROM character_aliases ca2 
                    WHERE ca2.character_id = c.id AND LOWER(ca2.alias) = LOWER(:query)
                )
                GROUP BY c.id, c.name, c.description, c.role, c.faction, c.status
                """)
                
                result = session.execute(name_match_query, {"query": query_text})
                exact_matches = []
                for row in result:
                    aliases = row.aliases if row.aliases and row.aliases[0] is not None else []
                    exact_matches.append({
                        "id": row.id,
                        "name": row.name,
                        "description": row.description,
                        "role": row.role,
                        "aliases": aliases,
                        "faction": row.faction,
                        "status": row.status,
                        "score": 1.0,  # Exact match gets top score
                        "content_type": "character",
                        "source": "structured_data"
                    })
                
                if exact_matches:
                    return exact_matches
                
                # Then look for partial matches
                partial_match_query = text("""
                SELECT DISTINCT c.id, c.name, c.description, c.role, c.faction, c.status,
                       array_agg(DISTINCT ca.alias) as aliases,
                       similarity(LOWER(c.name), LOWER(:query)) AS match_score
                FROM characters c
                LEFT JOIN character_aliases ca ON c.id = ca.character_id
                WHERE LOWER(c.name) LIKE '%' || LOWER(:query) || '%'
                OR LOWER(c.description) LIKE '%' || LOWER(:query) || '%'
                GROUP BY c.id, c.name, c.description, c.role, c.faction, c.status
                ORDER BY match_score DESC
                LIMIT :limit
                """)
                
                result = session.execute(partial_match_query, {"query": query_text, "limit": limit})
                partial_matches = []
                for row in result:
                    aliases = row.aliases if row.aliases and row.aliases[0] is not None else []
                    partial_matches.append({
                        "id": row.id,
                        "name": row.name,
                        "description": row.description,
                        "role": row.role,
                        "aliases": aliases,
                        "faction": row.faction,
                        "status": row.status,
                        "score": float(row.match_score),
                        "content_type": "character",
                        "source": "structured_data"
                    })
                
                return partial_matches
            
            elif table == "places":
                # Query places
                # First check for exact name matches
                name_match_query = text("""
                SELECT id, name, type, zone, summary, inhabitants, current_status
                FROM places
                WHERE LOWER(name) = LOWER(:query)
                """)
                
                result = session.execute(name_match_query, {"query": query_text})
                exact_matches = []
                for row in result:
                    exact_matches.append({
                        "id": row.id,
                        "name": row.name,
                        "type": row.type,
                        "zone": row.zone,
                        "summary": row.summary,
                        "inhabitants": row.inhabitants,
                        "current_status": row.current_status,
                        "score": 1.0,  # Exact match gets top score
                        "content_type": "place",
                        "source": "structured_data"
                    })
                
                if exact_matches:
                    return exact_matches
                
                # Then look for partial matches
                partial_match_query = text("""
                SELECT id, name, type, zone, summary, inhabitants, current_status,
                       similarity(LOWER(name), LOWER(:query)) AS match_score
                FROM places
                WHERE LOWER(name) LIKE '%' || LOWER(:query) || '%'
                OR LOWER(summary) LIKE '%' || LOWER(:query) || '%'
                ORDER BY match_score DESC
                LIMIT :limit
                """)
                
                result = session.execute(partial_match_query, {"query": query_text, "limit": limit})
                partial_matches = []
                for row in result:
                    partial_matches.append({
                        "id": row.id,
                        "name": row.name,
                        "type": row.type,
                        "zone": row.zone,
                        "summary": row.summary,
                        "inhabitants": row.inhabitants,
                        "current_status": row.current_status,
                        "score": float(row.match_score),
                        "content_type": "place",
                        "source": "structured_data"
                    })
                
                return partial_matches
            
            else:
                logger.warning(f"Unsupported table: {table}")
                return []
        
        except Exception as e:
            logger.error(f"Error querying structured data: {e}")
            return [] 