#!/usr/bin/env python3
"""
NEXUS IR Evaluation System - Main Module

This module serves as the main entry point for the IR evaluation system.
It uses the modular components from the scripts directory to provide
a complete IR evaluation system.

This is a refactored version of the original ir_eval.py, with functionality
split into separate modules for better maintainability.
"""

import os
import sys
import argparse
import logging
from typing import Dict, List, Any, Optional

# Ensure we can import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import local modules
try:
    from ir_eval.scripts.query_runner import run_golden_queries
    from ir_eval.scripts.judgments import judge_all_unjudged_results
    from ir_eval.scripts.display import (
        print_comparison_table, 
        print_configuration_details,
        print_current_parameters
    )
    from ir_eval.scripts.utils import (
        load_json, 
        save_json, 
        extract_memnon_settings,
        get_query_data_by_category
    )
    from ir_eval.scripts.ir_metrics import calculate_all_metrics, average_metrics_by_category
    from ir_eval.scripts.comparison import compare_runs
    from ir_eval.scripts.qrels import QRELSManager
    from ir_eval.db import IRDatabase, DEFAULT_DB_PATH
except ImportError:
    # Try relative imports if the above fails
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    from query_runner import run_golden_queries
    from judgments import judge_all_unjudged_results
    from display import (
        print_comparison_table, 
        print_configuration_details,
        print_current_parameters
    )
    from utils import (
        load_json, 
        save_json, 
        extract_memnon_settings,
        get_query_data_by_category
    )
    from ir_metrics import calculate_all_metrics, average_metrics_by_category
    from comparison import compare_runs
    from qrels import QRELSManager
    from db import IRDatabase, DEFAULT_DB_PATH

# Constants
DEFAULT_GOLDEN_QUERIES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "golden_queries.json")
DEFAULT_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
CONTROL_CONFIG_NAME = "control"
EXPERIMENT_CONFIG_NAME = "experiment"

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ir_eval.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.ir_eval")

# Ensure results directory exists
os.makedirs(RESULTS_DIR, exist_ok=True)

def evaluate_run(
    run_id: int,
    qrels: QRELSManager,
    db: Optional[IRDatabase] = None
) -> Dict[str, Any]:
    """
    Evaluate a run against relevance judgments and save metrics to database.
    
    Args:
        run_id: Database ID of the run to evaluate
        qrels: QRELSManager instance
        db: IRDatabase instance
        
    Returns:
        Dictionary with evaluation results
    """
    # Use provided database or create one
    if db is None:
        db = IRDatabase()
    
    # Get run results from database
    query_results = db.get_run_results(run_id)
    if not query_results:
        logger.error(f"No query results found for run_id {run_id}")
        return {}
    
    # Get run metadata
    run_data = db.get_run_metadata(run_id)
    if not run_data:
        logger.error(f"No run metadata found for run_id {run_id}")
        return {}
    
    # Extract metadata
    metadata = {
        "timestamp": run_data.get("timestamp", "unknown"),
        "settings": run_data.get("settings", {})
    }
    
    # Collect metrics for each query
    query_metrics = {}
    query_categories = {}
    
    for query_data in query_results:
        query_text = query_data.get("query", "")
        if not query_text:
            continue
        
        # Get category
        category = query_data.get("category", "unknown")
        query_categories[query_text] = category
        
        # Get results for this query
        results = query_data.get("results", [])
        if not results:
            logger.info(f"No results for query: {query_text}")
            continue
        
        # Get judgments for this query
        judgments = qrels.get_judgments_for_query(query_text)
        
        # Calculate metrics if we have judgments
        if judgments:
            # Get query ID
            query_id = db.get_query_id(query_text)
            if not query_id:
                logger.warning(f"Could not find query ID for '{query_text}'")
                continue
            
            # Calculate metrics
            metrics = calculate_all_metrics(results, judgments)
            query_metrics[query_text] = metrics
            
            # Save metrics to database
            if not db.save_metrics(run_id, query_id, metrics):
                logger.warning(f"Failed to save metrics for query '{query_text}'")
    
    # Calculate aggregate metrics
    aggregated = average_metrics_by_category(query_metrics, query_categories)
    
    return {
        "metadata": metadata,
        "by_query": query_metrics,
        "aggregated": aggregated,
        "query_categories": query_categories
    }

def main():
    """
    Main entry point for command-line usage.
    
    This simply forwards to the CLI module which handles the interactive interface.
    """
    try:
        # Import the CLI module
        from ir_eval_cli import IREvalCLI
        
        # Create and run the CLI
        cli = IREvalCLI()
        cli.show_main_menu()
    except ImportError:
        print("Error: ir_eval_cli.py module not found.")
        print("Please run the refactoring script to create this module.")
        sys.exit(1)

if __name__ == "__main__":
    main()