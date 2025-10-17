#!/usr/bin/env python3
"""
Golden Query Benchmark Script for MEMNON

This script runs a collection of "golden queries" through MEMNON and records the results
in a structured JSON file for evaluation. It enables rapid testing and evaluation
of different parameters and combinations of models for the MEMNON retrieval system.

USAGE:
    python scripts/run_golden_queries.py [options]

ARGUMENTS:
    --input PATH      Path to the golden queries JSON file
                      Default: golden_queries.json

    --limit N         Limit the number of queries to run (useful for quick tests)
                      Default: Run all queries

    --k N             Number of results to return for each query
                      Default: 10

    --hybrid          Force enable hybrid search (vector + text)
                      Default: Use the setting from settings.json

    --no-hybrid       Force disable hybrid search
                      Default: Use the setting from settings.json

EXAMPLES:
    # Run all queries with default settings
    python scripts/run_golden_queries.py

    # Run only the first 3 queries
    python scripts/run_golden_queries.py --limit 3

    # Run all queries with hybrid search enabled and return 5 results each
    python scripts/run_golden_queries.py --hybrid --k 5

    # Run queries from a custom file
    python scripts/run_golden_queries.py --input my_queries.json

OUTPUT:
    The script generates a JSON file with timestamp, e.g.:
    golden_query_results_20250421_190000.json

    This file contains:
    - MEMNON settings used for the run
    - Evaluation prompt from the golden queries file
    - Results for each query with timing information
"""

import os
import sys
import json
import time
import logging
import argparse
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[logging.FileHandler("golden_queries.log"), logging.StreamHandler()]
)
logger = logging.getLogger("golden-query-runner")

class SilentInterface:
    """Silent interface for MEMNON that doesn't print messages."""
    def assistant_message(self, message):
        pass

def extract_all_queries(golden_queries_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract all queries from the golden_queries.json file, ignoring hierarchy.
    
    Args:
        golden_queries_data: The parsed golden_queries.json data
        
    Returns:
        List of dictionaries with query info (query text, positives, negatives, category, name)
    """
    all_queries = []
    
    def process_category(category_name: str, category_data: Dict[str, Any]):
        for query_name, query_info in category_data.items():
            if isinstance(query_info, dict) and "query" in query_info:
                all_queries.append({
                    "category": category_name,
                    "name": query_name,
                    "query": query_info["query"],
                    "positives": query_info.get("positives", []),
                    "negatives": query_info.get("negatives", [])
                })
    
    # Process all top-level categories, skipping 'settings'
    for category, data in golden_queries_data.items():
        if category != "settings" and isinstance(data, dict):
            process_category(category, data)
    
    return all_queries

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

def run_golden_queries():
    """Run all golden queries and save results to a file."""
    parser = argparse.ArgumentParser(description="Run golden queries through MEMNON")
    parser.add_argument('--input', type=str, default='golden_queries.json',
                      help='Path to the golden queries JSON file')
    parser.add_argument('--limit', type=int, default=None,
                      help='Limit number of queries to run (for testing)')
    parser.add_argument('--k', type=int, default=10,
                      help='Number of results to return for each query')
    parser.add_argument('--hybrid', action='store_true', default=None,
                      help='Force enable hybrid search')
    parser.add_argument('--no-hybrid', dest='hybrid', action='store_false',
                      help='Force disable hybrid search')
    parser.add_argument('--output', type=str, choices=['file', 'json'], default='file',
                      help='Output mode: "file" to save to disk, "json" to print to stdout')
    parser.add_argument('--category', type=str, default=None,
                      help='Only run queries from the specified category')
    
    args = parser.parse_args()
    
    # Load golden queries
    try:
        with open(args.input, 'r') as f:
            golden_queries_data = json.load(f)
        logger.info(f"Loaded golden queries from {args.input}")
    except Exception as e:
        logger.error(f"Error loading golden queries: {e}")
        return 1
    
    # Extract all queries
    all_queries = extract_all_queries(golden_queries_data)
    
    # Filter by category if specified
    if args.category:
        logger.info(f"Filtering queries by category: {args.category}")
        all_queries = [q for q in all_queries if q["category"] == args.category]
        if not all_queries:
            logger.error(f"No queries found for category: {args.category}")
            return 1
    
    # Apply query limit if specified
    if args.limit:
        all_queries = all_queries[:args.limit]
        
    logger.info(f"Found {len(all_queries)} queries to process")
    
    # Get the settings and evaluation prompt from the JSON file
    settings = golden_queries_data.get("settings", {})
    evaluation_prompt = settings.get("prompt", golden_queries_data.get("prompt", ""))
    structured_data_enabled = settings.get("structured_data", True)
    logger.info(f"Loaded evaluation prompt from golden_queries.json")
    logger.info(f"Structured data search is {'enabled' if structured_data_enabled else 'disabled'}")
    
    # Import MEMNON and initialize
    try:
        from nexus.agents.memnon.memnon import MEMNON, MEMNON_SETTINGS, GLOBAL_SETTINGS
        logger.info("Successfully imported MEMNON")
    except ImportError as e:
        logger.error(f"Error importing MEMNON: {e}")
        return 1
    
    # Get database URL from settings
    db_url = MEMNON_SETTINGS.get("database", {}).get("url", "postgresql://pythagor@localhost/NEXUS")
    
    # Get model from global settings
    model_id = GLOBAL_SETTINGS.get("model", {}).get("default_model", "llama-3.3-70b-instruct@q6_k")
    
    # If hybrid search flag is set, modify settings
    if args.hybrid is not None:
        if "retrieval" not in MEMNON_SETTINGS:
            MEMNON_SETTINGS["retrieval"] = {}
        if "hybrid_search" not in MEMNON_SETTINGS["retrieval"]:
            MEMNON_SETTINGS["retrieval"]["hybrid_search"] = {}
        MEMNON_SETTINGS["retrieval"]["hybrid_search"]["enabled"] = args.hybrid
        logger.info(f"Hybrid search {'enabled' if args.hybrid else 'disabled'} by command line flag")
    
    # Apply structured data setting from golden_queries.json
    if "retrieval" not in MEMNON_SETTINGS:
        MEMNON_SETTINGS["retrieval"] = {}
    MEMNON_SETTINGS["retrieval"]["structured_data_enabled"] = structured_data_enabled
    logger.info(f"Structured data search {'enabled' if structured_data_enabled else 'disabled'} from settings")
    
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
        return 1
    
    # Get formatted settings summary
    settings_summary = get_memnon_settings_summary(MEMNON_SETTINGS)
    settings_text = format_settings_summary_text(settings_summary)
    
    # Prepare results structure
    results = {
        "timestamp": datetime.datetime.now().isoformat(),
        "settings": settings_summary,
        "settings_text": settings_text,
        "global_settings": {
            "model": GLOBAL_SETTINGS.get("model", {})
        },
        "evaluation_prompt": evaluation_prompt,
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
            query_analysis = memnon._analyze_query(query_text)
            query_type = query_analysis["type"]
            logger.info(f"Query type: {query_type}")
            
            # Get results
            query_result = memnon.query_memory(
                query=query_text,
                query_type=query_type,
                k=args.k
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
                "metadata": query_result.get("metadata", {})
            }
            
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
    
    # Handle output based on mode
    if args.output == 'file':
        # Generate output filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        hybrid_str = ""
        if args.hybrid is not None:
            hybrid_str = "_hybrid" if args.hybrid else "_nohybrid"
        output_filename = f"golden_query_results{hybrid_str}_{timestamp}.json"
        
        # Save results to file
        try:
            with open(output_filename, 'w') as f:
                json.dump(results, f, indent=2)
            logger.info(f"Results saved to {output_filename}")
        except Exception as e:
            logger.error(f"Error saving results: {e}")
            return 1
        
        return 0
    else:  # output == 'json'
        # Print JSON directly to stdout for capturing by other scripts
        try:
            print(json.dumps(results))
            return 0
        except Exception as e:
            logger.error(f"Error serializing results to JSON: {e}")
            return 1

if __name__ == "__main__":
    sys.exit(run_golden_queries())