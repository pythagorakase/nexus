#!/usr/bin/env python3
"""
Test script for IR Evaluation System - Direct Settings Modification

This script tests the IR evaluation system by directly modifying the MEMNON settings
and forcing a significant difference between control and experimental settings.
"""

import os
import sys
import json
import logging
import tempfile
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
)
logger = logging.getLogger("test_ir_eval_2")

# Add the project directory to path
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# Add the scripts directory to the path for imports
scripts_dir = os.path.join(project_dir, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# Import the MEMNON module to directly access settings
try:
    from nexus.agents.memnon.memnon import MEMNON, MEMNON_SETTINGS, GLOBAL_SETTINGS
    logger.info(f"Successfully imported MEMNON module")
except ImportError as e:
    logger.error(f"Error importing MEMNON module: {e}")
    sys.exit(1)

# Import the golden queries module
try:
    import golden_queries_module
    logger.info(f"Successfully imported golden_queries_module from {golden_queries_module.__file__}")
except ImportError as e:
    logger.error(f"Error importing golden_queries_module: {e}")
    sys.exit(1)

def load_golden_queries():
    """Load golden queries from golden_queries.json file."""
    golden_queries_path = os.path.join(project_dir, "ir_eval", "golden_queries.json")
    try:
        with open(golden_queries_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading golden queries: {e}")
        return None

def create_temp_settings(override_settings):
    """Create a temporary settings file with provided settings."""
    # Get the default settings
    settings_path = os.path.join(project_dir, "settings.json")
    try:
        with open(settings_path, 'r') as f:
            settings = json.load(f)
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return None
    
    # Create a deep copy to avoid modifying the original
    settings_copy = json.loads(json.dumps(settings))
    
    # Override MEMNON settings
    if "Agent Settings" in settings_copy and "MEMNON" in settings_copy["Agent Settings"]:
        settings_copy["Agent Settings"]["MEMNON"] = override_settings
    
    # Create temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.json', prefix='nexus_settings_')
    os.close(fd)
    
    # Write settings to temporary file
    with open(temp_path, 'w') as f:
        json.dump(settings_copy, f, indent=2)
    
    logger.info(f"Created temporary settings file: {temp_path}")
    return temp_path

def run_test():
    """Run the test with dramatically different settings."""
    # Load golden queries
    golden_queries = load_golden_queries()
    if not golden_queries:
        logger.error("Failed to load golden queries")
        return
    
    # Extract a simple query to test with
    test_query = None
    for category, queries in golden_queries.items():
        if category != "settings" and isinstance(queries, dict):
            for name, info in queries.items():
                if isinstance(info, dict) and "query" in info:
                    test_query = {
                        "category": category,
                        "name": name,
                        "query": info["query"]
                    }
                    break
            if test_query:
                break
    
    if not test_query:
        logger.error("Could not find a test query")
        return
    
    logger.info(f"\nUsing test query: '{test_query['query']}' from category '{test_query['category']}'")
    
    # Define control settings - text search focused
    control_settings = {
        "retrieval": {
            "max_results": 50,
            "relevance_threshold": 0.65,
            "entity_boost_factor": 1.2,
            "hybrid_search": {
                "enabled": True,
                "vector_weight_default": 0.2,  # Very low vector weight
                "text_weight_default": 0.8,    # Very high text weight
                "target_model": "inf-retriever-v1-1.5b",
                "temporal_boost_factor": 0.0
            }
        },
        "models": {
            "bge-large": {
                "is_active": True,
                "dimensions": 1024,
                "weight": 0.4
            },
            "inf-retriever-v1-1.5b": {
                "is_active": True,
                "dimensions": 1536,
                "weight": 0.6
            }
        }
    }
    
    # Define experimental settings - vector search focused
    experiment_settings = {
        "retrieval": {
            "max_results": 50,
            "relevance_threshold": 0.65,
            "entity_boost_factor": 1.2,
            "hybrid_search": {
                "enabled": True,
                "vector_weight_default": 0.9,  # Very high vector weight
                "text_weight_default": 0.1,    # Very low text weight
                "target_model": "inf-retriever-v1-1.5b",
                "temporal_boost_factor": 0.8,  # High temporal boost
                "use_query_type_temporal_factors": True
            }
        },
        "models": {
            "bge-large": {
                "is_active": True,
                "dimensions": 1024,
                "weight": 0.2
            },
            "inf-retriever-v1-1.5b": {
                "is_active": True,
                "dimensions": 1536,
                "weight": 0.8  # Different model weight
            }
        }
    }
    
    # Log the settings being tested
    logger.info("\nControl settings (text-focused):")
    logger.info(f"  Vector weight: {control_settings['retrieval']['hybrid_search']['vector_weight_default']}")
    logger.info(f"  Text weight: {control_settings['retrieval']['hybrid_search']['text_weight_default']}")
    logger.info(f"  Temporal boost: {control_settings['retrieval']['hybrid_search']['temporal_boost_factor']}")
    
    logger.info("\nExperimental settings (vector-focused):")
    logger.info(f"  Vector weight: {experiment_settings['retrieval']['hybrid_search']['vector_weight_default']}")
    logger.info(f"  Text weight: {experiment_settings['retrieval']['hybrid_search']['text_weight_default']}")
    logger.info(f"  Temporal boost: {experiment_settings['retrieval']['hybrid_search']['temporal_boost_factor']}")
    
    # Create settings files
    control_settings_path = create_temp_settings(control_settings)
    experiment_settings_path = create_temp_settings(experiment_settings)
    
    if not control_settings_path or not experiment_settings_path:
        logger.error("Failed to create settings files")
        return
    
    # Run query with control settings
    logger.info("\nRunning query with CONTROL settings (text-focused)...")
    control_results = golden_queries_module.run_queries(
        golden_queries_path=os.path.join(project_dir, "ir_eval", "golden_queries.json"),
        settings_path=control_settings_path,
        limit=1,
        k=10,
        category=test_query["category"]
    )
    
    # Run query with experimental settings
    logger.info("\nRunning query with EXPERIMENTAL settings (vector-focused)...")
    experiment_results = golden_queries_module.run_queries(
        golden_queries_path=os.path.join(project_dir, "ir_eval", "golden_queries.json"),
        settings_path=experiment_settings_path,
        limit=1,
        k=10,
        category=test_query["category"]
    )
    
    # Clean up temporary files
    os.remove(control_settings_path)
    os.remove(experiment_settings_path)
    
    # Compare results
    logger.info("\nComparing results...")
    
    # Extract settings that were actually used
    control_hybrid_settings = control_results.get("settings", {}).get("hybrid_search", {})
    experiment_hybrid_settings = experiment_results.get("settings", {}).get("hybrid_search", {})
    
    logger.info("\nACTUAL Control settings used:")
    logger.info(json.dumps(control_hybrid_settings, indent=2))
    
    logger.info("\nACTUAL Experimental settings used:")
    logger.info(json.dumps(experiment_hybrid_settings, indent=2))
    
    # Extract query results
    control_query_results = control_results.get("query_results", [])[0] if control_results.get("query_results") else {}
    experiment_query_results = experiment_results.get("query_results", [])[0] if experiment_results.get("query_results") else {}
    
    # Extract scores for comparison
    control_scores = []
    if control_query_results and "results" in control_query_results:
        for result in control_query_results["results"]:
            control_scores.append({
                "id": result.get("id"),
                "score": result.get("score"),
                "vector_score": result.get("vector_score"),
                "text_score": result.get("text_score")
            })
    
    experiment_scores = []
    if experiment_query_results and "results" in experiment_query_results:
        for result in experiment_query_results["results"]:
            experiment_scores.append({
                "id": result.get("id"),
                "score": result.get("score"),
                "vector_score": result.get("vector_score"),
                "text_score": result.get("text_score")
            })
    
    # Calculate how many results differ
    different_results = 0
    different_order = 0
    total_results = min(len(control_scores), len(experiment_scores))
    
    if total_results > 0:
        # Get IDs in order
        control_ids = [result["id"] for result in control_scores]
        experiment_ids = [result["id"] for result in experiment_scores]
        
        # Check for ordering differences
        for i in range(total_results):
            if i < len(control_ids) and i < len(experiment_ids):
                if control_ids[i] != experiment_ids[i]:
                    different_order += 1
        
        # Count how many IDs differ completely (not just order)
        for control_id in control_ids:
            if control_id not in experiment_ids:
                different_results += 1
        
        # Calculate percentages
        percent_different = (different_results / total_results) * 100
        percent_different_order = (different_order / total_results) * 100
        
        logger.info(f"Results comparison:")
        logger.info(f"  {different_results} out of {total_results} results completely different ({percent_different:.1f}%)")
        logger.info(f"  {different_order} out of {total_results} results in different order ({percent_different_order:.1f}%)")
        
        if different_results > 0 or different_order > 0:
            logger.info("✅ TEST PASSED: Control and experiment produced different results!")
            
            # Show a side-by-side comparison of results
            logger.info("\nSide-by-side comparison of first 3 results:")
            logger.info(f"{'CONTROL':<40} {'EXPERIMENT':<40}")
            logger.info("-" * 80)
            
            for i in range(min(3, total_results)):
                control = control_scores[i] if i < len(control_scores) else None
                experiment = experiment_scores[i] if i < len(experiment_scores) else None
                
                if control and experiment:
                    control_str = f"ID: {control['id']}, Score: {control['score']:.4f}"
                    experiment_str = f"ID: {experiment['id']}, Score: {experiment['score']:.4f}"
                    logger.info(f"{control_str:<40} {experiment_str:<40}")
        else:
            logger.info("❌ TEST FAILED: Control and experiment produced identical results!")
            
            # This suggests the settings aren't actually being applied
            logger.info("\nDEBUG: Even with dramatically different settings, the results are identical.")
            logger.info("This strongly suggests that the settings aren't actually being applied properly.")
            
    else:
        logger.info("❌ TEST FAILED: No results to compare")

if __name__ == "__main__":
    run_test()