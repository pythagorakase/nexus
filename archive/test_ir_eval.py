#!/usr/bin/env python3
"""
Test script for IR Evaluation System

This script tests the IR evaluation system by running a single query with both control
and experimental settings, and then comparing the results to verify that they are different.
"""

import os
import sys
import json
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
)
logger = logging.getLogger("test_ir_eval")

# Add the project directory to path
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# Add the scripts directory to the path for imports
scripts_dir = os.path.join(project_dir, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

try:
    # Import the golden_queries_module directly
    import golden_queries_module
    logger.info(f"Successfully imported golden_queries_module from {golden_queries_module.__file__}")
except ImportError as e:
    logger.error(f"Error importing golden_queries_module: {e}")
    sys.exit(1)

def load_settings():
    """Load settings from settings.json file."""
    settings_path = os.path.join(project_dir, "settings.json")
    try:
        with open(settings_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return None

def load_golden_queries():
    """Load golden queries from golden_queries.json file."""
    golden_queries_path = os.path.join(project_dir, "ir_eval", "golden_queries.json")
    try:
        with open(golden_queries_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading golden queries: {e}")
        return None

def create_temp_settings(base_settings, override_settings):
    """Create a temporary settings file with overrides."""
    import tempfile
    
    # Create a deep copy to avoid modifying the original
    settings_copy = json.loads(json.dumps(base_settings))
    
    # Override MEMNON settings
    if "Agent Settings" in settings_copy and "MEMNON" in settings_copy["Agent Settings"]:
        # Apply selective overrides
        for key, value in override_settings.items():
            if key in settings_copy["Agent Settings"]["MEMNON"]:
                if isinstance(value, dict) and isinstance(settings_copy["Agent Settings"]["MEMNON"][key], dict):
                    # Merge dictionaries
                    settings_copy["Agent Settings"]["MEMNON"][key].update(value)
                else:
                    # Replace value
                    settings_copy["Agent Settings"]["MEMNON"][key] = value
    
    # Create temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.json', prefix='nexus_settings_')
    os.close(fd)
    
    # Write settings to temporary file
    with open(temp_path, 'w') as f:
        json.dump(settings_copy, f, indent=2)
    
    return temp_path

def extract_experimental_settings(golden_queries_data):
    """Extract experimental settings from golden_queries.json."""
    experimental_settings = None
    if "settings" in golden_queries_data:
        experimental_settings = {}
        if "retrieval" in golden_queries_data["settings"]:
            experimental_settings["retrieval"] = golden_queries_data["settings"]["retrieval"]
        if "models" in golden_queries_data["settings"]:
            experimental_settings["models"] = golden_queries_data["settings"]["models"]
    return experimental_settings

def run_test():
    """Run the test."""
    # Load settings and golden queries
    settings = load_settings()
    golden_queries = load_golden_queries()
    
    if not settings or not golden_queries:
        logger.error("Failed to load settings or golden queries")
        return
    
    # Extract settings
    if "Agent Settings" in settings and "MEMNON" in settings["Agent Settings"]:
        control_settings = settings["Agent Settings"]["MEMNON"]
    else:
        logger.error("MEMNON settings not found in settings.json")
        return
    
    experimental_settings = extract_experimental_settings(golden_queries)
    if not experimental_settings:
        logger.error("Experimental settings not found in golden_queries.json")
        return
    
    # Log settings
    logger.info("Control settings:")
    logger.info(f"  Hybrid search enabled: {control_settings.get('retrieval', {}).get('hybrid_search', {}).get('enabled', False)}")
    if "retrieval" in control_settings and "hybrid_search" in control_settings["retrieval"]:
        hybrid = control_settings["retrieval"]["hybrid_search"]
        logger.info(f"  Vector weight: {hybrid.get('vector_weight_default', 'N/A')}")
        logger.info(f"  Text weight: {hybrid.get('text_weight_default', 'N/A')}")
        logger.info(f"  Temporal boost factor: {hybrid.get('temporal_boost_factor', 'N/A')}")
    
    logger.info("\nExperimental settings:")
    logger.info(f"  Hybrid search enabled: {experimental_settings.get('retrieval', {}).get('hybrid_search', {}).get('enabled', False)}")
    if "retrieval" in experimental_settings and "hybrid_search" in experimental_settings["retrieval"]:
        hybrid = experimental_settings["retrieval"]["hybrid_search"]
        logger.info(f"  Vector weight: {hybrid.get('vector_weight_default', 'N/A')}")
        logger.info(f"  Text weight: {hybrid.get('text_weight_default', 'N/A')}")
        logger.info(f"  Temporal boost factor: {hybrid.get('temporal_boost_factor', 'N/A')}")
    
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
    
    # Run with control settings
    settings_path = os.path.join(project_dir, "settings.json")
    logger.info("\nRunning query with CONTROL settings...")
    control_results = golden_queries_module.run_queries(
        golden_queries_path=os.path.join(project_dir, "ir_eval", "golden_queries.json"),
        settings_path=settings_path,
        limit=1,
        k=5,
        hybrid=None,
        category=test_query["category"]
    )
    
    # Create temp settings file for experimental settings
    temp_settings_path = create_temp_settings(settings, experimental_settings)
    logger.info(f"\nCreated temporary settings file for experiment: {temp_settings_path}")
    
    # Run with experimental settings
    logger.info("\nRunning query with EXPERIMENTAL settings...")
    experiment_results = golden_queries_module.run_queries(
        golden_queries_path=os.path.join(project_dir, "ir_eval", "golden_queries.json"),
        settings_path=temp_settings_path,
        limit=1,
        k=5,
        hybrid=None,
        category=test_query["category"]
    )
    
    # Clean up temporary file
    os.remove(temp_settings_path)
    
    # Compare results
    logger.info("\nComparing results...")
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
    total_results = min(len(control_scores), len(experiment_scores))
    
    if total_results > 0:
        # Check if the result sets are different
        control_ids = [result["id"] for result in control_scores]
        experiment_ids = [result["id"] for result in experiment_scores]
        
        # Count how many IDs differ
        for control_id in control_ids:
            if control_id not in experiment_ids:
                different_results += 1
        
        # Also check scores for IDs that are in both sets
        common_ids = set(control_ids) & set(experiment_ids)
        for common_id in common_ids:
            control_result = next((r for r in control_scores if r["id"] == common_id), None)
            experiment_result = next((r for r in experiment_scores if r["id"] == common_id), None)
            
            if control_result and experiment_result:
                # Check if scores are significantly different
                if abs(control_result["score"] - experiment_result["score"]) > 0.01:
                    different_results += 1
        
        # Calculate percentage of differing results
        percent_different = (different_results / total_results) * 100
        
        logger.info(f"Results comparison: {different_results} out of {total_results} results differ ({percent_different:.1f}%)")
        
        if different_results > 0:
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
                
            # Print detailed control settings actually used
            logger.info("\nDetailed control settings used:")
            logger.info(json.dumps(control_results.get("settings", {}).get("hybrid_search", {}), indent=2))
            
            # Print detailed experimental settings actually used
            logger.info("\nDetailed experimental settings used:")
            logger.info(json.dumps(experiment_results.get("settings", {}).get("hybrid_search", {}), indent=2))
            
        else:
            logger.info("❌ TEST FAILED: Control and experiment produced identical results!")
    else:
        logger.info("❌ TEST FAILED: No results to compare")

if __name__ == "__main__":
    run_test()