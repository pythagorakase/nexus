#!/usr/bin/env python3
"""
Golden Query Module for MEMNON

This module provides functions to run golden queries through the MEMNON retrieval system 
and return structured results directly as Python objects, without JSON intermediates.

Functions:
    run_queries: Run a set of golden queries and return results
    extract_queries: Extract query information from golden_queries.json
    get_settings_summary: Extract MEMNON settings summary
"""

import os
import sys
import json
import time
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add the project directory to the Python path
# We're in ir_eval/scripts, so go up two levels to reach project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[logging.FileHandler("golden_queries.log"), logging.StreamHandler()]
)
logger = logging.getLogger("golden-query-module")

class SilentInterface:
    """Silent interface for MEMNON that doesn't print messages."""
    def assistant_message(self, message):
        pass

# Function removed as it's no longer needed when getting queries directly from the database

def get_memnon_settings_summary(memnon_settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a summary of relevant MEMNON settings for the output.
    
    Args:
        memnon_settings: The MEMNON settings dict
        
    Returns:
        Dict containing a summary of the important settings
    """
    summary = {
        "models": {},
        "retrieval": {},
        "hybrid_search": {},
        "cross_encoder_reranking": {},
        "query": {}
    }
    
    # Extract model settings
    if "models" in memnon_settings:
        for model_name, model_config in memnon_settings["models"].items():
            summary["models"][model_name] = {
                "is_active": model_config.get("is_active", False),
                "dimensions": model_config.get("dimensions", "unknown"),
                "weight": model_config.get("weight", 0.0)
            }
    
    # Extract retrieval settings
    if "retrieval" in memnon_settings:
        retrieval = memnon_settings["retrieval"]
        summary["retrieval"] = {
            "max_results": retrieval.get("max_results", 0),
            "relevance_threshold": retrieval.get("relevance_threshold", 0),
            "entity_boost_factor": retrieval.get("entity_boost_factor", 0),
            "source_weights": retrieval.get("source_weights", {}),
            "structured_data_enabled": retrieval.get("structured_data_enabled", True),
            "user_character_focus_boost": {
                "enabled": retrieval.get("user_character_focus_boost", {}).get("enabled", False)
            }
        }
        
        # Hybrid search settings
        if "hybrid_search" in retrieval:
            summary["hybrid_search"] = {
                "enabled": retrieval["hybrid_search"].get("enabled", False),
                "vector_weight_default": retrieval["hybrid_search"].get("vector_weight_default", 0),
                "text_weight_default": retrieval["hybrid_search"].get("text_weight_default", 0),
                "target_model": retrieval["hybrid_search"].get("target_model", "unknown")
            }
        
        # Cross-encoder reranking settings
        if "cross_encoder_reranking" in retrieval:
            summary["cross_encoder_reranking"] = {
                "enabled": retrieval["cross_encoder_reranking"].get("enabled", False),
                "model_path": retrieval["cross_encoder_reranking"].get("model_path", ""),
                "blend_weight": retrieval["cross_encoder_reranking"].get("blend_weight", 0),
                "top_k": retrieval["cross_encoder_reranking"].get("top_k", 0),
                "batch_size": retrieval["cross_encoder_reranking"].get("batch_size", 0),
                "use_sliding_window": retrieval["cross_encoder_reranking"].get("use_sliding_window", False),
                "window_size": retrieval["cross_encoder_reranking"].get("window_size", 0),
                "window_overlap": retrieval["cross_encoder_reranking"].get("window_overlap", 0),
                "use_query_type_weights": retrieval["cross_encoder_reranking"].get("use_query_type_weights", False),
                "weights_by_query_type": retrieval["cross_encoder_reranking"].get("weights_by_query_type", {})
            }
    
    # Query settings
    if "query" in memnon_settings:
        summary["query"] = memnon_settings["query"]
    
    return summary

def format_settings_summary_text(settings: Dict[str, Any]) -> str:
    """Format the settings summary as a human-readable text."""
    lines = []
    
    # Format model settings
    if "models" in settings:
        active_models = [f"{name} (weight={config.get('weight', 0.0)})" 
                        for name, config in settings["models"].items() 
                        if config.get("is_active", False)]
        lines.append(f"Active models: {', '.join(active_models)}")
    
    # Hybrid search settings
    if "hybrid_search" in settings:
        hybrid = settings["hybrid_search"]
        hybrid_status = "ENABLED" if hybrid.get("enabled", False) else "DISABLED"
        lines.append(f"Hybrid search: {hybrid_status}")
        if hybrid.get("enabled", False):
            lines.append(f"  Vector weight: {hybrid.get('vector_weight_default', 0)}")
            lines.append(f"  Text weight: {hybrid.get('text_weight_default', 0)}")
            lines.append(f"  Target model: {hybrid.get('target_model', 'unknown')}")
    
    # Cross-encoder reranking settings
    if "cross_encoder_reranking" in settings:
        ce = settings["cross_encoder_reranking"]
        ce_status = "ENABLED" if ce.get("enabled", False) else "DISABLED"
        lines.append(f"Cross-encoder reranking: {ce_status}")
        if ce.get("enabled", False):
            lines.append(f"  Model: {ce.get('model_path', '').split('/')[-1]}")
            lines.append(f"  Blend weight: {ce.get('blend_weight', 0)}")
            lines.append(f"  Top K: {ce.get('top_k', 0)}")
            lines.append(f"  Batch size: {ce.get('batch_size', 0)}")
            
            window_status = "ENABLED" if ce.get("use_sliding_window", False) else "DISABLED"
            lines.append(f"  Sliding window: {window_status}")
            if ce.get("use_sliding_window", False):
                lines.append(f"    Window size: {ce.get('window_size', 0)}")
                lines.append(f"    Window overlap: {ce.get('window_overlap', 0)}")
            
            query_weights_status = "ENABLED" if ce.get("use_query_type_weights", False) else "DISABLED" 
            lines.append(f"  Query-specific weights: {query_weights_status}")
            if ce.get("use_query_type_weights", False) and "weights_by_query_type" in ce:
                lines.append("    Weights by query type:")
                for qtype, weight in ce["weights_by_query_type"].items():
                    lines.append(f"      {qtype}: {weight}")
    
    # Retrieval settings
    if "retrieval" in settings:
        retrieval = settings["retrieval"]
        lines.append(f"Max results: {retrieval.get('max_results', 'N/A')}")
        lines.append(f"Relevance threshold: {retrieval.get('relevance_threshold', 'N/A')}")
        
        # Structured data search
        structured_status = "ENABLED" if retrieval.get("structured_data_enabled", True) else "DISABLED"
        lines.append(f"Structured data search: {structured_status}")
        
        # Source weights
        if "source_weights" in retrieval:
            weights = retrieval["source_weights"]
            lines.append("Source weights:")
            for source, weight in weights.items():
                lines.append(f"  {source}: {weight}")
        
        # User character focus boost
        user_focus = retrieval.get("user_character_focus_boost", {})
        if user_focus:
            status = "ENABLED" if user_focus.get("enabled", False) else "DISABLED"
            lines.append(f"User character focus boost: {status}")
    
    return "\n".join(lines)

def run_queries(
    golden_queries_path: str = 'golden_queries.json',
    settings_path: str = None,
    override_settings: Dict[str, Any] = None,
    limit: int = None,
    k: int = None,  # Default to None so we can use config value
    hybrid: Optional[bool] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run golden queries through MEMNON and return results directly as Python objects.
    
    Args:
        golden_queries_path: Path to the golden queries JSON file
        settings_path: Path to custom settings.json (uses env var if None)
        override_settings: Dict of settings to override
        limit: Maximum number of queries to run
        k: Number of results to return for each query
        hybrid: Whether to force enable/disable hybrid search
        category: Filter queries by category
        
    Returns:
        Dictionary with query results and metadata
    """
    # Load settings from golden queries file with better path handling
    try:
        # First try the path as provided
        try:
            with open(golden_queries_path, 'r') as f:
                golden_queries_data = json.load(f)
            logger.info(f"Loaded settings from {golden_queries_path}")
        except FileNotFoundError:
            # If that fails, try resolving as relative to current directory
            ir_eval_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            alternative_path = os.path.join(ir_eval_dir, "golden_queries.json")
            logger.info(f"Original path not found, trying alternative: {alternative_path}")
            
            with open(alternative_path, 'r') as f:
                golden_queries_data = json.load(f)
            logger.info(f"Loaded settings from alternative path: {alternative_path}")
    except Exception as e:
        logger.error(f"Error loading settings from golden queries file: {e}")
        raise
    
    # Get queries directly from database instead of using JSON file
    # This simplifies the process by skipping the step of copying queries from JSON to database
    try:
        # Import PostgreSQL database module 
        parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ir_eval_path = os.path.join(parent_dir, "ir_eval")
        if ir_eval_path not in sys.path:
            sys.path.insert(0, ir_eval_path)
        from pg_db import IRDatabasePG
        
        db = IRDatabasePG()
        cursor = db.conn.cursor()
        
        # Get queries from database
        if category:
            logger.info(f"Filtering queries by category: {category}")
            cursor.execute(
                "SELECT id, text, category, name FROM ir_eval.queries WHERE category = %s",
                (category,)
            )
        else:
            logger.info("Fetching ALL queries (no category filter)")
            # Make sure we're using parameterized query even without parameters
            cursor.execute("SELECT id, text, category, name FROM ir_eval.queries")
        
        # Fetch query records
        query_rows = cursor.fetchall()
        cursor.close()
        
        if not query_rows:
            logger.error("No queries found in database")
            # Check if database has any queries at all to diagnose the problem
            verify_cursor = db.conn.cursor()
            verify_cursor.execute("SELECT COUNT(*) FROM ir_eval.queries")
            total_count = verify_cursor.fetchone()[0]
            verify_cursor.close()
            
            if total_count > 0:
                logger.error(f"Database has {total_count} queries, but none were returned for this request")
                if category:
                    logger.error(f"Category filter '{category}' may be invalid or no queries match this category")
                else:
                    logger.error("Failed to retrieve ANY queries despite no category filter")
            else:
                logger.error("Database has NO queries at all")
                
            raise ValueError(f"No queries found in database (total queries: {total_count})")
        
        # Convert to the format expected by the rest of the module
        all_queries = []
        logger.info(f"Processing {len(query_rows)} queries from database")
        
        for row in query_rows:
            query_id = row[0]
            query_text = row[1]
            query_category = row[2] if row[2] else "uncategorized"
            query_name = row[3] if row[3] else f"query_{query_id}"
            
            all_queries.append({
                "query": query_text,
                "category": query_category,
                "name": query_name,
                "positives": [],  # Not stored in DB yet
                "negatives": []   # Not stored in DB yet
            })
            
            # Log a sample of queries for debugging
            if len(all_queries) <= 3:
                logger.info(f"Sample query {len(all_queries)}: id={query_id}, text='{query_text[:30]}...', category={query_category}")
        
        # Apply query limit if specified
        if limit:
            all_queries = all_queries[:limit]
            
        logger.info(f"Found {len(all_queries)} queries from database to process")
    except Exception as e:
        logger.error(f"Error fetching queries from database: {e}")
        raise
    
    # Get just the experimental settings from the JSON file
    settings = golden_queries_data.get("settings", {})
    structured_data_enabled = settings.get("structured_data", True)
    logger.info(f"Structured data search is {'enabled' if structured_data_enabled else 'disabled'}")
    
    # Set environment variable for settings path if provided
    # CRITICAL: This must come BEFORE importing MEMNON, so settings are loaded from the correct path
    if settings_path:
        os.environ["NEXUS_SETTINGS_PATH"] = settings_path
        logger.info(f"Using custom settings path: {settings_path}")
    
    # Import MEMNON module (not the actual MEMNON class or settings yet)
    try:
        import nexus.agents.memnon.memnon
        # Force reload of the module to get fresh settings
        import importlib
        importlib.reload(nexus.agents.memnon.memnon)
        # Now import the actual MEMNON class and settings
        from nexus.agents.memnon.memnon import MEMNON, MEMNON_SETTINGS, GLOBAL_SETTINGS
        logger.info("Successfully imported MEMNON")
    except ImportError as e:
        logger.error(f"Error importing MEMNON: {e}")
        raise
    
    # Get database URL from settings
    db_url = MEMNON_SETTINGS.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
    
    # Get model from global settings
    model_id = GLOBAL_SETTINGS.get("model", {}).get("default_model", "llama-3.3-70b-instruct@q6_k")
    
    # If hybrid search flag is set, modify settings
    if hybrid is not None:
        if "retrieval" not in MEMNON_SETTINGS:
            MEMNON_SETTINGS["retrieval"] = {}
        if "hybrid_search" not in MEMNON_SETTINGS["retrieval"]:
            MEMNON_SETTINGS["retrieval"]["hybrid_search"] = {}
        MEMNON_SETTINGS["retrieval"]["hybrid_search"]["enabled"] = hybrid
        logger.info(f"Hybrid search {'enabled' if hybrid else 'disabled'} by command line flag")
    
    # Apply structured data setting from golden_queries.json
    if "retrieval" not in MEMNON_SETTINGS:
        MEMNON_SETTINGS["retrieval"] = {}
    MEMNON_SETTINGS["retrieval"]["structured_data_enabled"] = structured_data_enabled
    logger.info(f"Structured data search {'enabled' if structured_data_enabled else 'disabled'} from settings")
    
    # Apply any custom settings overrides
    if override_settings:
        for key, value in override_settings.items():
            if key in MEMNON_SETTINGS and isinstance(MEMNON_SETTINGS[key], dict) and isinstance(value, dict):
                # For dict values, update rather than replace
                MEMNON_SETTINGS[key].update(value)
            else:
                MEMNON_SETTINGS[key] = value
        logger.info(f"Applied {len(override_settings)} setting overrides")
        
    # Use chunks_per_query from golden_queries.json if k is not explicitly provided
    if k is None:
        # First try to get from golden_queries.json directly
        if "chunks_per_query" in golden_queries_data:
            k = golden_queries_data.get("chunks_per_query", 50)
            logger.info(f"Using k={k} from golden_queries.json chunks_per_query")
        # Next try from experimental settings in golden_queries.json
        elif "settings" in golden_queries_data and "query" in golden_queries_data["settings"] and "chunks_per_query" in golden_queries_data["settings"]["query"]:
            k = golden_queries_data["settings"]["query"]["chunks_per_query"]
            logger.info(f"Using k={k} from golden_queries.json settings.query.chunks_per_query")
        # Next try from MEMNON settings default_limit
        elif "query" in MEMNON_SETTINGS and "default_limit" in MEMNON_SETTINGS["query"]:
            k = MEMNON_SETTINGS["query"]["default_limit"]
            logger.info(f"Using k={k} from MEMNON_SETTINGS.query.default_limit")
        else:
            k = 50  # Fallback default
            logger.info(f"Using fallback default k={k} since no configuration found")
    
    # Initialize MEMNON
    try:
        logger.info("Initializing MEMNON...")
        memnon = MEMNON(
            interface=SilentInterface(),
            agent_state=None,  # Direct mode - no legacy Letta framework needed
            user=None,
            db_url=db_url,
            model_id=model_id,
            debug=True
        )
        logger.info("MEMNON initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing MEMNON: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise
    
    # Get formatted settings summary
    settings_summary = get_memnon_settings_summary(MEMNON_SETTINGS)
    settings_text = format_settings_summary_text(settings_summary)
    
    # Prepare results structure
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "settings": settings_summary,
        "settings_text": settings_text,
        "global_settings": {
            "model": GLOBAL_SETTINGS.get("model", {})
        },
        "query_results": []
    }
    
    # Run each query
    for i, query_info in enumerate(all_queries):
        query_text = query_info["query"]
        logger.info(f"Processing query {i+1}/{len(all_queries)}: '{query_text}'")
        
        try:
            # Start timer
            start_time = time.time()
            
            # First determine query type
            query_analysis = memnon.query_analyzer.analyze_query(query_text)
            query_type = query_analysis["type"]
            logger.info(f"Query type: {query_type}")
            
            # Get results
            query_result = memnon.query_memory(
                query=query_text,
                query_type=query_type,
                k=k
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"Query completed in {elapsed_time:.2f}s with {len(query_result['results'])} results")
            
            # Ensure the results have proper vector_score and text_score values
            processed_results = []
            
            # Print some debug info for the first few results
            logger.info(f"DEBUG - First few raw results:")
            for i, res in enumerate(query_result["results"][:3]):
                has_vector = "vector_score" in res
                vector_val = res.get("vector_score", "MISSING")
                vector_type = type(vector_val).__name__ if has_vector else "N/A"
                
                has_text = "text_score" in res
                text_val = res.get("text_score", "MISSING")
                text_type = type(text_val).__name__ if has_text else "N/A"
                
                logger.info(f"Result {i}: id={res.get('id', 'unknown')}, "
                           f"score={res.get('score', 0.0)}, "
                           f"vector_score={vector_val} ({vector_type}), "
                           f"text_score={text_val} ({text_type}), "
                           f"source={res.get('source', 'unknown')}")
            
            for res in query_result["results"]:
                # Make a copy of the result
                processed = res.copy()
                
                # Ensure vector_score is present and is a float
                if "vector_score" not in processed or processed["vector_score"] is None:
                    processed["vector_score"] = 0.0
                    logger.info(f"Setting missing vector_score to 0.0 for chunk {processed.get('id', 'unknown')}")
                else:
                    try:
                        processed["vector_score"] = float(processed["vector_score"])
                    except (ValueError, TypeError) as e:
                        logger.error(f"Error converting vector_score to float: {e}")
                        processed["vector_score"] = 0.0
                    
                # Ensure text_score is present and is a float
                if "text_score" not in processed or processed["text_score"] is None:
                    processed["text_score"] = 0.0
                else:
                    try:
                        processed["text_score"] = float(processed["text_score"])
                    except (ValueError, TypeError) as e:
                        logger.error(f"Error converting text_score to float: {e}")
                        processed["text_score"] = 0.0
                    
                processed_results.append(processed)
            
            # Extract timing information if available
            metadata = query_result.get("metadata", {})
            
            # Record the result with processed scores
            query_data = {
                "category": query_info["category"],
                "name": query_info["name"],
                "query": query_text,
                "query_type": query_type,
                "positives": query_info["positives"],
                "negatives": query_info["negatives"],
                "elapsed_time": elapsed_time,
                "results_count": len(processed_results),
                "results": processed_results,
                "query_analysis": query_analysis,
                "metadata": metadata
            }
            
            # Store reranking time in metadata if available
            if "rerank_time" in metadata:
                logger.info(f"Cross-encoder reranking took {metadata['rerank_time']:.3f} seconds for query '{query_text}'")
            if "rerank_metadata" in metadata:
                logger.info(f"Reranking metadata: {metadata['rerank_metadata']}")
            
            results["query_results"].append(query_data)
            
        except Exception as e:
            logger.error(f"Error processing query '{query_text}': {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Record the error
            query_data = {
                "category": query_info["category"],
                "name": query_info["name"],
                "query": query_text,
                "error": str(e),
                "results": []
            }
            results["query_results"].append(query_data)
    
    # Clear environment variable if we set it
    if settings_path and "NEXUS_SETTINGS_PATH" in os.environ:
        del os.environ["NEXUS_SETTINGS_PATH"]
    
    return results

# Command line interface when script is executed directly
if __name__ == "__main__":
    import argparse
    
    # Get absolute path to default golden_queries.json
    default_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "golden_queries.json")
    
    parser = argparse.ArgumentParser(description="Run golden queries through MEMNON")
    parser.add_argument('--input', type=str, default=default_path,
                     help='Path to the golden queries JSON file')
    parser.add_argument('--limit', type=int, default=None,
                     help='Limit number of queries to run (for testing)')
    parser.add_argument('--k', type=int, default=None,
                     help='Number of results to return for each query (defaults to value from settings)')
    parser.add_argument('--hybrid', action='store_true', default=None,
                     help='Force enable hybrid search')
    parser.add_argument('--no-hybrid', dest='hybrid', action='store_false',
                     help='Force disable hybrid search')
    parser.add_argument('--output', type=str, choices=['file', 'json'], default='file',
                     help='Output mode: "file" to save to disk, "json" to print to stdout')
    parser.add_argument('--category', type=str, default=None,
                     help='Only run queries from the specified category')
    
    args = parser.parse_args()
    
    try:
        # Run queries
        results = run_queries(
            golden_queries_path=args.input,
            limit=args.limit,
            k=args.k,
            hybrid=args.hybrid,
            category=args.category
        )
        
        # Handle output based on mode
        if args.output == 'file':
            # Generate output filename with timestamp
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            hybrid_str = ""
            if args.hybrid is not None:
                hybrid_str = "_hybrid" if args.hybrid else "_nohybrid"
            output_filename = f"golden_query_results{hybrid_str}_{timestamp}.json"
            
            # Save results to file
            with open(output_filename, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"Results saved to {output_filename}")
            sys.exit(0)
        else:  # output == 'json'
            # Print JSON directly to stdout for capturing by other scripts
            print(json.dumps(results))
            sys.exit(0)
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)