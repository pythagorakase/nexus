#!/usr/bin/env python3
"""
NEXUS IR Evaluation System - PostgreSQL Version

This is the main entry point for the PostgreSQL-based IR evaluation system.
It provides an interactive interface for evaluating and comparing the performance
of different retrieval configurations for the NEXUS retrieval system.

Usage:
    python ir_eval/ir_eval.py
"""

import os
import sys
import json
import time
import datetime
import logging
import tempfile
import subprocess
import argparse
from typing import Dict, List, Any, Tuple, Optional, Set
from pathlib import Path

# Add parent directory to path
parent_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, parent_dir)

# Import IR evaluation modules
from pg_db import IRDatabasePG
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
from pg_qrels import PGQRELSManager
from ir_metrics import calculate_all_metrics, average_metrics_by_category
from scripts.auto_judge import AIJudge

# Set up logging
# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(logs_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(logs_dir, "ir_eval.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.ir_eval")

# Constants
DEFAULT_GOLDEN_QUERIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_queries.json")
DEFAULT_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
CONTROL_CONFIG_NAME = "control"
EXPERIMENT_CONFIG_NAME = "experiment"

# Ensure results directory exists
os.makedirs(RESULTS_DIR, exist_ok=True)

def load_json(path: str) -> Dict[str, Any]:
    """Load JSON data from file."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading JSON from {path}: {e}")
        return {}

def save_json(data: Dict[str, Any], path: str) -> bool:
    """Save JSON data to file."""
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved data to {path}")
        return True
    except Exception as e:
        logger.error(f"Error saving JSON to {path}: {e}")
        return False

def extract_memnon_settings(settings_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract MEMNON settings from settings.json."""
    if "Agent Settings" in settings_data and "MEMNON" in settings_data["Agent Settings"]:
        return settings_data["Agent Settings"]["MEMNON"]
    return {}

def create_temp_settings_file(settings_data: Dict[str, Any], memnon_override: Dict[str, Any]) -> str:
    """
    Create a temporary settings file with modified MEMNON settings.
    
    Args:
        settings_data: The original settings data
        memnon_override: The MEMNON settings to override
    
    Returns:
        Path to the temporary settings file
    """
    # Create a deep copy to avoid modifying the original
    settings_copy = json.loads(json.dumps(settings_data))
    
    # Override MEMNON settings
    if "Agent Settings" in settings_copy and "MEMNON" in settings_copy["Agent Settings"]:
        # Apply selective overrides
        for key, value in memnon_override.items():
            if key in settings_copy["Agent Settings"]["MEMNON"]:
                if isinstance(value, dict) and isinstance(settings_copy["Agent Settings"]["MEMNON"][key], dict):
                    # Special handling for models to preserve local_path settings
                    if key == "models":
                        for model_name, model_config in value.items():
                            if model_name in settings_copy["Agent Settings"]["MEMNON"]["models"]:
                                # Preserve local_path from original settings
                                local_path = settings_copy["Agent Settings"]["MEMNON"]["models"][model_name].get("local_path")
                                if local_path:
                                    if model_name not in settings_copy["Agent Settings"]["MEMNON"]["models"]:
                                        settings_copy["Agent Settings"]["MEMNON"]["models"][model_name] = {}
                                    settings_copy["Agent Settings"]["MEMNON"]["models"][model_name].update(model_config)
                                    settings_copy["Agent Settings"]["MEMNON"]["models"][model_name]["local_path"] = local_path
                            else:
                                settings_copy["Agent Settings"]["MEMNON"]["models"][model_name] = model_config
                    # Special handling for retrieval settings which has nested dictionaries
                    elif key == "retrieval":
                        for subkey, subvalue in value.items():
                            if (subkey in settings_copy["Agent Settings"]["MEMNON"]["retrieval"] and 
                                isinstance(subvalue, dict) and 
                                isinstance(settings_copy["Agent Settings"]["MEMNON"]["retrieval"][subkey], dict)):
                                # Deep update for nested dictionaries like cross_encoder_reranking
                                settings_copy["Agent Settings"]["MEMNON"]["retrieval"][subkey].update(subvalue)
                            else:
                                # For non-dict values or keys not in settings, simply set them
                                settings_copy["Agent Settings"]["MEMNON"]["retrieval"][subkey] = subvalue
                    else:
                        # For non-model dictionaries, regular update
                        settings_copy["Agent Settings"]["MEMNON"][key].update(value)
                else:
                    # Replace value
                    settings_copy["Agent Settings"]["MEMNON"][key] = value
        
        # Debug log the settings for troubleshooting
        logger.info(f"Created experimental settings with hybrid_search config: " +
                   f"{json.dumps(settings_copy['Agent Settings']['MEMNON'].get('retrieval', {}).get('hybrid_search', {}), indent=2)}")
        
        # Log cross encoder settings for debugging
        cross_encoder_config = settings_copy['Agent Settings']['MEMNON'].get('retrieval', {}).get('cross_encoder_reranking', {})
        logger.info(f"Cross encoder config in experiment: {json.dumps(cross_encoder_config, indent=2)}")
    
    # Create temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.json', prefix='nexus_settings_')
    os.close(fd)
    
    # Write settings to temporary file
    with open(temp_path, 'w') as f:
        json.dump(settings_copy, f, indent=2)
    
    logger.info(f"Created temporary settings file at {temp_path}")
    return temp_path

def get_query_data_by_category(golden_queries_data: Dict[str, Any]) -> Dict[str, List[Tuple[str, str, Dict[str, Any]]]]:
    """
    Extract queries grouped by category from golden_queries.json.
    
    Returns:
        Dictionary mapping category names to lists of (name, query_text, query_info) tuples
    """
    queries_by_category = {}
    
    for category, queries in golden_queries_data.items():
        if category != "settings" and isinstance(queries, dict):
            if category not in queries_by_category:
                queries_by_category[category] = []
                
            for name, info in queries.items():
                if isinstance(info, dict) and "query" in info:
                    queries_by_category[category].append((name, info["query"], info))
    
    return queries_by_category

def run_golden_queries(
    settings_path: str,
    golden_queries_path: str,
    config_type: str,
    run_name: str = None,
    queries: Optional[List[str]] = None,
    hybrid: Optional[bool] = None,
    k: Optional[int] = None,  # Changed from 10 to None to use config from settings
    db: Optional[IRDatabasePG] = None,
    category: Optional[str] = None,
    description: Optional[str] = None
) -> Optional[int]:
    """
    Run golden queries using the golden_queries_module and save results directly to database.
    
    Args:
        settings_path: Path to settings.json
        golden_queries_path: Path to golden_queries.json
        config_type: Type of configuration ('control' or 'experiment')
        run_name: Name for this run
        queries: Optional list of specific queries to run
        hybrid: Whether to enable hybrid search
        k: Number of results to return for each query
        db: IRDatabasePG instance
        
    Returns:
        ID of the run in the database
    """
    # Use provided database or create one
    if db is None:
        db = IRDatabasePG()
    
    # Set default run name if not provided
    if run_name is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_name = f"{config_type}_{timestamp}"
    
    # Import the golden queries module directly
    try:
        # Add the local scripts directory to the Python path
        local_scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
        if local_scripts_dir not in sys.path:
            # Make sure it's FIRST in path to ensure our version is loaded
            sys.path.insert(0, local_scripts_dir)
        
        # Clean any existing modules to avoid cached imports
        if 'golden_queries_module' in sys.modules:
            import importlib
            importlib.reload(sys.modules['golden_queries_module'])
            logger.info("Reloaded existing golden_queries_module")
        
        # Import the module properly
        logger.info(f"Attempting to import golden_queries_module from: {local_scripts_dir}")
        import golden_queries_module
        
        # Verify we got the right module
        module_path = os.path.abspath(golden_queries_module.__file__)
        expected_path = os.path.join(local_scripts_dir, "golden_queries_module.py")
        
        if module_path != expected_path:
            logger.warning(f"WARNING: Imported golden_queries_module from unexpected location: {module_path}")
            logger.warning(f"Expected: {expected_path}")
        else:
            logger.info(f"Successfully imported from expected path: {module_path}")
            
        run_queries = golden_queries_module.run_queries
        
        logger.info(f"Successfully imported golden_queries_module from {golden_queries_module.__file__}")
        
        # Run queries directly through the module
        try:
            limit = len(queries) if queries else None
            
            # Get results directly as Python objects
            results_data = run_queries(
                golden_queries_path=golden_queries_path,
                settings_path=settings_path,
                limit=limit,
                k=k,
                hybrid=hybrid,
                category=category,
            )
            
            logger.info(f"Successfully retrieved results from golden_queries_module")
            
            # Log the first result to verify scores are present
            if results_data and "query_results" in results_data and results_data["query_results"]:
                first_query = results_data["query_results"][0]
                if "results" in first_query and first_query["results"]:
                    first_result = first_query["results"][0]
                    logger.info(f"DEBUG - First result: "
                               f"id={first_result.get('id')}, "
                               f"score={first_result.get('score')}, "
                               f"vector_score={first_result.get('vector_score')} "
                               f"({type(first_result.get('vector_score')).__name__}), "
                               f"text_score={first_result.get('text_score')} "
                               f"({type(first_result.get('text_score')).__name__})")
            
            # Extract settings from results data
            settings = results_data.get("settings", {})
            
            # Create run in database
            run_description = description
            if not run_description:
                run_description = f"Generated by ir_eval_pg.py with {config_type} configuration"
                
            run_id = db.add_run(
                name=run_name, 
                settings=settings, 
                config_type=config_type, 
                description=run_description
            )
            
            if not run_id:
                logger.error("Failed to add run to database")
                return None
            
            # Save query results to database
            query_results = results_data.get("query_results", [])
            
            # Debug: look at text scores before saving to database
            if query_results and query_results[0]["results"]:
                sample_results = query_results[0]["results"][:3]
                logger.info("DEBUG - Text scores before database insertion:")
                for i, res in enumerate(sample_results):
                    logger.info(f"  Result {i}: id={res.get('id')}, "
                               f"text_score={res.get('text_score')} "
                               f"({type(res.get('text_score')).__name__})")
            
            if not db.save_results(run_id, query_results):
                logger.error("Failed to save results to database")
                return None
            
            logger.info(f"Saved run {run_id} to database")
            return run_id
            
        except Exception as e:
            logger.error(f"Error in golden_queries_module.run_queries: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    except ImportError as e:
        logger.error(f"Error importing golden_queries_module: {e}")
        logger.error("This indicates the refactoring is incomplete - you need to create scripts/golden_queries_module.py")
        return None

def format_result_text(text: str, truncate: bool = False, max_length: int = 500) -> str:
    """
    Format result text for display, optionally with truncation and newlines.
    
    Args:
        text: The text to format
        truncate: Whether to truncate the text (default: False)
        max_length: Maximum length if truncating (default: 500)
        
    Returns:
        Formatted text
    """
    if not text:
        return ""
    
    # Replace literal newlines with actual newlines
    formatted = text.replace("\\n", "\n")
    
    # Truncate if requested and if too long
    if truncate and len(formatted) > max_length:
        truncated = formatted[:max_length]
        # Try to truncate at a sensible point
        last_period = truncated.rfind(".")
        last_newline = truncated.rfind("\n")
        
        cutoff = max(last_period, last_newline)
        if cutoff > max_length * 0.7:  # Only use cutoff if it's reasonably far along
            truncated = truncated[:cutoff+1]
        
        formatted = truncated + "..."
    
    return formatted

def judge_all_unjudged_results(
    run_ids: List[int],
    qrels: PGQRELSManager,
    golden_queries_data: Dict[str, Any],
    db: Optional[IRDatabasePG] = None
) -> int:
    """
    Interactive tool for judging all unjudged search results across multiple runs.
    
    Args:
        run_ids: List of database IDs of runs to judge
        qrels: PGQRELSManager instance
        golden_queries_data: Golden queries data
        db: IRDatabasePG instance
        
    Returns:
        Number of judgments added
    """
    # Use provided database or create one
    if db is None:
        db = IRDatabasePG()
    
    # Track judgments added in this session
    judgments_added = 0
    
    # Track the last judgment for undo functionality
    last_judgment = None
    
    # Keep track of queries we've seen to avoid duplicates
    processed_queries = set()
    
    # Calculate total unjudged documents across all runs
    total_unjudged_count = 0
    total_results_count = 0
    
    # First pass to count all unjudged documents
    for run_id in run_ids:
        # Load results from database
        query_results = db.get_run_results(run_id)
        if not query_results:
            logger.warning(f"No query results found for run_id {run_id}")
            continue
            
        for query_data in query_results:
            results = query_data.get("results", [])
            query_text = query_data.get("query", "")
            if not results or not query_text:
                continue
                
            # Get already judged documents for this query
            judged_docs = qrels.get_judged_documents(query_text)
            
            # Count unjudged documents
            unjudged_count = sum(1 for r in results if str(r.get("id")) not in judged_docs)
            total_unjudged_count += unjudged_count
            total_results_count += len(results)
            
    logger.info(f"Found {total_unjudged_count} total unjudged documents out of {total_results_count}")
    
    # Process each run
    for run_id in run_ids:
        # Load results from database
        query_results = db.get_run_results(run_id)
        if not query_results:
            logger.warning(f"No query results found for run_id {run_id}")
            continue
        
        logger.info(f"Loaded {len(query_results)} queries from database for run_id {run_id}")
        
        # Get run metadata
        run_data = db.get_run_metadata(run_id)
        run_name = run_data.get('name', f"Run {run_id}") if run_data else f"Run {run_id}"
        
        # Process each query
        for query_data in query_results:
            query_text = query_data.get("query", "")
            
            # Skip already processed queries
            if query_text in processed_queries:
                continue
            
            processed_queries.add(query_text)
            
            category = query_data.get("category", "unknown")
            name = query_data.get("name", "unknown")
            
            # Find query info in golden queries data
            query_info = None
            if category in golden_queries_data and name in golden_queries_data[category]:
                query_info = golden_queries_data[category][name]
            
            # Extract positives and negatives
            positives = []
            negatives = []
            if query_info:
                positives = query_info.get("positives", [])
                negatives = query_info.get("negatives", [])
            
            # Get results for this query
            results = query_data.get("results", [])
            if not results:
                print(f"No results for query: {query_text}")
                continue
                
            # Get already judged documents for this query
            judged_docs = qrels.get_judged_documents(query_text)
            
            # Count how many documents need judging
            unjudged_count = sum(1 for r in results if str(r.get("id")) not in judged_docs)
            
            if not unjudged_count:
                # All results already judged, skip this query
                continue
            
            # Clear the screen for a fresh start with each query
            os.system('clear' if os.name == 'posix' else 'cls')
            
            # Print query information with enhanced visibility
            print("\n\n" + "★"*100)
            print("★"*100)
            print(f"NEW QUERY: {query_text}")
            print(f"CATEGORY: {category} / NAME: {name}")
            print(f"RUN: {run_name} (ID: {run_id})")
            print(f"Found {len(results)} results, {unjudged_count} need judging")
            print(f"TOTAL REMAINING: {total_unjudged_count} documents left to judge across all queries")
            print("★"*100)
            
            # Show guidelines if available
            if positives:
                print("\nPOSITIVE guidelines (what makes a good result):")
                for i, pos in enumerate(positives, 1):
                    print(f"  {i}. {pos}")
            
            if negatives:
                print("\nNEGATIVE guidelines (what makes a bad result):")
                for i, neg in enumerate(negatives, 1):
                    print(f"  {i}. {neg}")
            
            print("\nRelevance scale:")
            print("  0: Irrelevant - Does not match the query at all")
            print("  1: Marginally relevant - Mentions the topic but not very helpful")
            print("  2: Relevant - Contains useful information about the query")
            print("  3: Highly relevant - Perfect match for the query")
            print("  Q: Quit the review process")
            print("  U: Undo last judgment")
            print("  S: Skip this document")
            
            # Process each result
            i = 0
            while i < len(results):
                result = results[i]
                chunk_id = result.get("id")
                
                # Skip already judged documents
                if str(chunk_id) in judged_docs:
                    i += 1
                    continue
                
                text = result.get("text", "")
                score = result.get("score", 0)
                vector_score = result.get("vector_score", None)
                text_score = result.get("text_score", None)
                source = result.get("source", "unknown")
                
                # Format scores for display
                score_display = f"Score: {score:.4f}"
                
                # Show vector and text scores when available
                if vector_score is not None:
                    score_display += f" (Vector: {vector_score:.4f}"
                if text_score is not None:
                    if vector_score is not None:
                        score_display += f", Text: {text_score:.4f})"
                    else:
                        score_display += f" (Text: {text_score:.4f})"
                elif vector_score is not None:
                    score_display += ")"
                
                # Display the document
                print("\n" + "="*80)
                print(f"Document {i+1}/{len(results)} (Chunk ID: {chunk_id}, {score_display})")
                print(f"Source: {source}")
                print("="*80)
                print(format_result_text(text, truncate=False))
                print("="*80)
                
                # Get relevance judgment
                while True:
                    relevance_input = input("Relevance (0-3), S to skip, U to undo, or Q to quit: ").strip().upper()
                    
                    # Handle quit request
                    if relevance_input in ["Q", "QUIT", "EXIT"]:
                        print("Exiting judgment session...")
                        # Save and return
                        return judgments_added
                    
                    # Handle undo request
                    if relevance_input == "U" and last_judgment:
                        undo_query, undo_chunk_id = last_judgment
                        # Remove the judgment
                        print(f"Undoing judgment for chunk {undo_chunk_id}...")
                        
                        # Remove from judged_docs set for the current query
                        if undo_query == query_text and str(undo_chunk_id) in judged_docs:
                            judged_docs.remove(str(undo_chunk_id))
                        
                        # Remove judgment from database
                        db.remove_judgment(undo_query, undo_chunk_id)
                        
                        judgments_added -= 1
                        last_judgment = None
                        
                        # If we're undoing the current query, go back one document
                        if undo_query == query_text and i > 0:
                            i -= 1
                        
                        print("Judgment undone.")
                        break
                    
                    # Handle skip request
                    if relevance_input == "S":
                        print("Skipped")
                        i += 1
                        
                        # Calculate remaining judgments in queue
                        remaining_in_current_query = len(results) - len(judged_docs)
                        
                        # Clear screen and show query again for better readability
                        os.system('clear' if os.name == 'posix' else 'cls')
                        print("\n\n" + "★"*100)
                        print(f"QUERY: {query_text}")
                        print(f"CATEGORY: {category} / NAME: {name}")
                        print(f"RUN: {run_name} (ID: {run_id})")
                        print(f"Reviewing document {i+1}/{len(results)}")
                        print(f"PROGRESS: {len(judged_docs)}/{len(results)} judged | {remaining_in_current_query} remaining for this query")
                        print(f"TOTAL REMAINING: {total_unjudged_count} documents left to judge across all queries")
                        print("★"*100)
                        
                        # Re-display guidelines if available
                        if positives:
                            print("\nPOSITIVE guidelines (what makes a good result):")
                            for idx, pos in enumerate(positives, 1):
                                print(f"  {idx}. {pos}")
                        
                        if negatives:
                            print("\nNEGATIVE guidelines (what makes a bad result):")
                            for idx, neg in enumerate(negatives, 1):
                                print(f"  {idx}. {neg}")
                        
                        print("\nRelevance scale:")
                        print("  0: Irrelevant - Does not match the query at all")
                        print("  1: Marginally relevant - Mentions the topic but not very helpful")
                        print("  2: Relevant - Contains useful information about the query")
                        print("  3: Highly relevant - Perfect match for the query")
                        print("  Q: Quit the review process")
                        print("  U: Undo last judgment")
                        print("  S: Skip this document")
                        
                        break
                    
                    # Handle numeric rating
                    try:
                        relevance = int(relevance_input)
                        if 0 <= relevance <= 3:
                            # Add judgment
                            qrels.add_judgment(
                                query_text,
                                chunk_id,
                                relevance,
                                category,
                                text
                            )
                            
                            # Update tracking variables
                            judged_docs.add(str(chunk_id))
                            judgments_added += 1
                            last_judgment = (query_text, chunk_id)
                            
                            # Calculate remaining judgments in queue
                            remaining_in_current_query = len(results) - len(judged_docs)
                            
                            # Update total unjudged count
                            total_unjudged_count -= 1
                            
                            # Clear screen and show query again for better readability
                            os.system('clear' if os.name == 'posix' else 'cls')
                            print("\n\n" + "★"*100)
                            print(f"QUERY: {query_text}")
                            print(f"CATEGORY: {category} / NAME: {name}")
                            print(f"RUN: {run_name} (ID: {run_id})")
                            print(f"Reviewing document {i+1}/{len(results)}")
                            print(f"PROGRESS: {len(judged_docs)}/{len(results)} judged | {remaining_in_current_query} remaining for this query")
                            print(f"TOTAL REMAINING: {total_unjudged_count} documents left to judge across all queries")
                            print("★"*100)
                            
                            # Re-display guidelines if available
                            if positives:
                                print("\nPOSITIVE guidelines (what makes a good result):")
                                for idx, pos in enumerate(positives, 1):
                                    print(f"  {idx}. {pos}")
                            
                            if negatives:
                                print("\nNEGATIVE guidelines (what makes a bad result):")
                                for idx, neg in enumerate(negatives, 1):
                                    print(f"  {idx}. {neg}")
                            
                            print("\nRelevance scale:")
                            print("  0: Irrelevant - Does not match the query at all")
                            print("  1: Marginally relevant - Mentions the topic but not very helpful")
                            print("  2: Relevant - Contains useful information about the query")
                            print("  3: Highly relevant - Perfect match for the query")
                            print("  Q: Quit the review process")
                            print("  U: Undo last judgment")
                            print("  S: Skip this document")
                            
                            # Move to next document
                            i += 1
                            break
                        else:
                            print("Please enter a number between 0 and 3, or Q to quit, U to undo, S to skip")
                    except ValueError:
                        print("Please enter a number between 0 and 3, or Q to quit, U to undo, S to skip")
    
    print("\n" + "="*80)
    print(f"Judging complete! Added {judgments_added} new relevance judgments")
    print(f"Total judgments in database: {qrels.get_judgment_count()}")
    
    return judgments_added

def evaluate_run(
    run_id: int,
    qrels: PGQRELSManager,
    db: Optional[IRDatabasePG] = None
) -> Dict[str, Any]:
    """
    Evaluate a run against relevance judgments and save metrics to database.
    
    Args:
        run_id: Database ID of the run to evaluate
        qrels: PGQRELSManager instance
        db: IRDatabasePG instance
        
    Returns:
        Dictionary with evaluation results
    """
    # Use provided database or create one
    if db is None:
        db = IRDatabasePG()
    
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

def compare_runs(
    run_ids: List[int],
    run_names: List[str],
    db: Optional[IRDatabasePG] = None
) -> Dict[str, Any]:
    """
    Compare multiple runs and identify the best performer.
    
    Args:
        run_ids: List of database IDs for runs to compare
        run_names: List of names for each run
        db: IRDatabasePG instance
        
    Returns:
        Dictionary with comparison results and ID
    """
    # Use provided database or create one
    if db is None:
        db = IRDatabasePG()
    
    # Ensure we have names for all runs
    if len(run_names) < len(run_ids):
        for i in range(len(run_names), len(run_ids)):
            run_names.append(f"Run {chr(65 + i)}")
    
    # Get metrics for each run
    run_results = []
    for run_id in run_ids:
        metrics = db.get_run_metrics(run_id)
        
        # Get query results to extract runtime stats
        query_results = db.get_run_results(run_id)
        
        # Process runtime statistics if we have them
        if query_results:
            total_query_time = 0
            total_reranking_time = 0
            query_count = 0
            has_reranking_stats = False
            
            for query_data in query_results:
                if "elapsed_time" in query_data:
                    total_query_time += query_data["elapsed_time"]
                    query_count += 1
                
                # Check for reranking time in metadata
                if "metadata" in query_data and "reranking_time" in query_data["metadata"]:
                    total_reranking_time += query_data["metadata"]["reranking_time"]
                    has_reranking_stats = True
            
            # Calculate averages
            runtime_stats = {}
            if query_count > 0:
                runtime_stats["avg_query_time"] = total_query_time / query_count
                runtime_stats["total_query_time"] = total_query_time
                runtime_stats["query_count"] = query_count
                
                if has_reranking_stats:
                    runtime_stats["avg_reranking_time"] = total_reranking_time / query_count
                    runtime_stats["total_reranking_time"] = total_reranking_time
            
            # Add runtime stats to metrics
            if runtime_stats and metrics:
                metrics["runtime_stats"] = runtime_stats
        
        run_results.append(metrics)
    
    # Structure for comparison results
    comparison = {
        "timestamp": datetime.datetime.now().isoformat(),
        "runs": [{"name": name, "results": results} for name, results in zip(run_names, run_results)],
        "comparison": {
            "overall": {},
            "by_category": {}
        },
        "best_run": {}
    }
    
    # Compare overall metrics
    overall_comparison = {}
    for metric in ["p@5", "p@10", "mrr", "bpref"]:
        values = []
        for run in run_results:
            if run and "aggregated" in run and "overall" in run["aggregated"]:
                values.append(run["aggregated"]["overall"].get(metric, 0))
            else:
                values.append(0)
        
        # Identify best run for this metric
        if values:
            best_index = values.index(max(values))
            best_run = run_names[best_index]
        else:
            best_index = -1
            best_run = "None"
        
        # Calculate changes relative to first run
        changes = []
        if values and len(values) > 1:
            baseline = values[0]
            for value in values:
                changes.append(value - baseline)
        
        overall_comparison[metric] = {
            "values": values,
            "changes": changes,
            "best_run": best_run,
            "best_index": best_index
        }
    
    comparison["comparison"]["overall"] = overall_comparison
    
    # Compare by category
    category_comparison = {}
    all_categories = set()
    
    # Collect all categories
    for run in run_results:
        if run and "aggregated" in run and "by_category" in run["aggregated"]:
            all_categories.update(run["aggregated"]["by_category"].keys())
    
    # Compare each category
    for category in all_categories:
        category_comparison[category] = {}
        
        for metric in ["p@5", "p@10", "mrr", "bpref"]:
            values = []
            for run in run_results:
                if (run and "aggregated" in run and "by_category" in run["aggregated"] and
                    category in run["aggregated"]["by_category"]):
                    values.append(run["aggregated"]["by_category"][category].get(metric, 0))
                else:
                    values.append(0)
            
            # Identify best run for this metric
            if values:
                best_index = values.index(max(values))
                best_run = run_names[best_index]
            else:
                best_index = -1
                best_run = "None"
            
            # Calculate changes relative to first run
            changes = []
            if values and len(values) > 1:
                baseline = values[0]
                for value in values:
                    changes.append(value - baseline)
            
            category_comparison[category][metric] = {
                "values": values,
                "changes": changes,
                "best_run": best_run,
                "best_index": best_index
            }
    
    comparison["comparison"]["by_category"] = category_comparison
    
    # Compare runtime statistics if available
    runtime_comparison = {}
    
    # Check if any runs have runtime stats
    has_runtime_stats = False
    for run in run_results:
        if run and "runtime_stats" in run:
            has_runtime_stats = True
            break
    
    if has_runtime_stats:
        # Compare query times
        query_times = []
        for run in run_results:
            if run and "runtime_stats" in run:
                query_times.append(run["runtime_stats"].get("avg_query_time", 0))
            else:
                query_times.append(0)
        
        # Calculate changes relative to first run
        query_time_changes = []
        if query_times and len(query_times) > 1 and query_times[0] > 0:
            baseline = query_times[0]
            for value in query_times:
                query_time_changes.append(value - baseline)
        
        runtime_comparison["avg_query_time"] = {
            "values": query_times,
            "changes": query_time_changes
        }
        
        # Compare reranking times if available
        has_reranking_times = False
        for run in run_results:
            if run and "runtime_stats" in run and "avg_reranking_time" in run["runtime_stats"]:
                has_reranking_times = True
                break
        
        if has_reranking_times:
            reranking_times = []
            for run in run_results:
                if run and "runtime_stats" in run and "avg_reranking_time" in run["runtime_stats"]:
                    reranking_times.append(run["runtime_stats"].get("avg_reranking_time", 0))
                else:
                    reranking_times.append(0)
            
            # Calculate changes relative to first run
            reranking_time_changes = []
            if reranking_times and len(reranking_times) > 1 and reranking_times[0] > 0:
                baseline = reranking_times[0]
                for value in reranking_times:
                    reranking_time_changes.append(value - baseline)
            
            runtime_comparison["avg_reranking_time"] = {
                "values": reranking_times,
                "changes": reranking_time_changes
            }
        
        comparison["comparison"]["runtime"] = runtime_comparison
    
    # Determine best run overall using average of normalized metric performance
    run_scores = [0] * len(run_results)
    
    for metric, data in overall_comparison.items():
        if data["values"]:
            max_val = max(data["values"])
            if max_val > 0:  # Avoid division by zero
                for i, val in enumerate(data["values"]):
                    # Normalize each score and add to total
                    run_scores[i] += val / max_val
    
    # Best run is the one with highest total score
    if run_scores:
        best_index = run_scores.index(max(run_scores))
        best_run_id = run_ids[best_index]
        best_run_name = run_names[best_index]
    else:
        best_index = -1
        best_run_id = None
        best_run_name = "None"
    
    comparison["best_run"] = {
        "name": best_run_name,
        "id": best_run_id,
        "index": best_index,
        "scores": run_scores
    }
    
    # Save comparison to database
    comparison_id = db.save_comparison(run_ids, run_names, comparison, best_run_id)
    if comparison_id:
        comparison["id"] = comparison_id
    
    return comparison

def print_comparison_table(comparison: Dict[str, Any]) -> None:
    """Print a formatted comparison table."""
    run_names = [run["name"] for run in comparison["runs"]]
    
    # Print header
    print("\n" + "="*80)
    print("NEXUS IR Evaluation - Run Comparison")
    print("="*80)
    
    # Print runtime statistics if available
    print("\nRuntime Statistics:")
    print("-"*80)
    
    # Check if any runs have timing data
    has_timing_data = False
    for run in comparison["runs"]:
        if run["results"] and "runtime_stats" in run["results"]:
            has_timing_data = True
            break
    
    if has_timing_data:
        # Header row for timing
        header = "Statistic".ljust(20)
        for name in run_names:
            header += name.ljust(20)
        if len(run_names) > 1:
            header += "Difference".ljust(15)
        print(header)
        print("-"*80)
        
        # Average query time
        row = "Avg Query Time (s)".ljust(20)
        avg_times = []
        
        for run in comparison["runs"]:
            if run["results"] and "runtime_stats" in run["results"]:
                avg_time = run["results"]["runtime_stats"].get("avg_query_time", 0)
                avg_times.append(avg_time)
                row += f"{avg_time:.4f}".ljust(20)
            else:
                row += "N/A".ljust(20)
                avg_times.append(None)
        
        # Calculate difference if we have two valid times
        if len(avg_times) == 2 and avg_times[0] is not None and avg_times[1] is not None:
            diff = avg_times[1] - avg_times[0]
            percent = (diff / avg_times[0] * 100) if avg_times[0] > 0 else 0
            diff_str = f"{diff:.4f} ({percent:+.1f}%)"
            row += diff_str.ljust(15)
        
        print(row)
        
        # Cross-encoder reranking time (if available)
        has_reranking_time = False
        for run in comparison["runs"]:
            if run["results"] and "runtime_stats" in run["results"] and "avg_reranking_time" in run["results"]["runtime_stats"]:
                has_reranking_time = True
                break
        
        if has_reranking_time:
            row = "Reranking Time (s)".ljust(20)
            rerank_times = []
            
            for run in comparison["runs"]:
                if run["results"] and "runtime_stats" in run["results"] and "avg_reranking_time" in run["results"]["runtime_stats"]:
                    rerank_time = run["results"]["runtime_stats"].get("avg_reranking_time", 0)
                    rerank_times.append(rerank_time)
                    row += f"{rerank_time:.4f}".ljust(20)
                else:
                    row += "N/A".ljust(20)
                    rerank_times.append(None)
            
            # Calculate difference if we have two valid times
            if len(rerank_times) == 2 and rerank_times[0] is not None and rerank_times[1] is not None:
                diff = rerank_times[1] - rerank_times[0]
                percent = (diff / rerank_times[0] * 100) if rerank_times[0] > 0 else 0
                diff_str = f"{diff:.4f} ({percent:+.1f}%)"
                row += diff_str.ljust(15)
            
            print(row)
        
        # Percentage of time spent on reranking
        if has_reranking_time:
            row = "Reranking % of Total".ljust(20)
            percentages = []
            
            for run in comparison["runs"]:
                if run["results"] and "runtime_stats" in run["results"]:
                    avg_time = run["results"]["runtime_stats"].get("avg_query_time", 0)
                    rerank_time = run["results"]["runtime_stats"].get("avg_reranking_time", 0)
                    if avg_time > 0:
                        percentage = (rerank_time / avg_time) * 100
                        percentages.append(percentage)
                        row += f"{percentage:.1f}%".ljust(20)
                    else:
                        row += "N/A".ljust(20)
                        percentages.append(None)
                else:
                    row += "N/A".ljust(20)
                    percentages.append(None)
            
            # Calculate difference if we have two valid percentages
            if len(percentages) == 2 and percentages[0] is not None and percentages[1] is not None:
                diff = percentages[1] - percentages[0]
                diff_str = f"{diff:+.1f}%"
                row += diff_str.ljust(15)
            
            print(row)
    else:
        print("No runtime statistics available")
    
    # Print overall metrics
    print("\nOverall Metrics:")
    print("-"*80)
    
    # Header row
    header = "Metric".ljust(10)
    for name in run_names:
        header += name.ljust(15)
    if len(run_names) > 1:
        header += "Best Run".ljust(15)
    print(header)
    print("-"*80)
    
    # Metrics rows
    for metric in ["p@5", "p@10", "mrr", "bpref"]:
        metric_data = comparison["comparison"]["overall"][metric]
        row = metric.ljust(10)
        
        for i, value in enumerate(metric_data["values"]):
            cell = f"{value:.4f}"
            if len(run_names) > 1 and i > 0:
                change = metric_data["changes"][i]
                if change > 0:
                    cell += f" (+{change:.4f})"
                elif change < 0:
                    cell += f" ({change:.4f})"
                else:
                    cell += " (±0.0000)"
            row += cell.ljust(15)
        
        if len(run_names) > 1:
            row += metric_data["best_run"].ljust(15)
        
        print(row)
    
    # Print category metrics if available
    if comparison["comparison"]["by_category"]:
        for category, metrics in comparison["comparison"]["by_category"].items():
            print(f"\n{category.capitalize()} Category Metrics:")
            print("-"*80)
            
            # Header row
            header = "Metric".ljust(10)
            for name in run_names:
                header += name.ljust(15)
            if len(run_names) > 1:
                header += "Best Run".ljust(15)
            print(header)
            print("-"*80)
            
            # Metrics rows
            for metric in ["p@5", "p@10", "mrr", "bpref"]:
                if metric in metrics:
                    metric_data = metrics[metric]
                    row = metric.ljust(10)
                    
                    for i, value in enumerate(metric_data["values"]):
                        cell = f"{value:.4f}"
                        if len(run_names) > 1 and i > 0:
                            change = metric_data["changes"][i]
                            if change > 0:
                                cell += f" (+{change:.4f})"
                            elif change < 0:
                                cell += f" ({change:.4f})"
                            else:
                                cell += " (±0.0000)"
                        row += cell.ljust(15)
                    
                    if len(run_names) > 1:
                        row += metric_data["best_run"].ljust(15)
                    
                    print(row)
    
    # Print unjudged document counts
    print("\nUnjudged Documents:")
    row = "Count".ljust(10)
    for run in comparison["runs"]:
        if run["results"] and "aggregated" in run["results"] and "overall" in run["results"]["aggregated"]:
            count = run["results"]["aggregated"]["overall"].get("unjudged_count", 0)
            row += str(count).ljust(15)
        else:
            row += "N/A".ljust(15)
    print(row)
    
    # Print best run overall
    print("\n" + "="*80)
    best_run = comparison["best_run"]["name"]
    print(f"BEST OVERALL PERFORMER: {best_run}")
    print("="*80)

class IREvalPGCLI:
    """Interactive CLI for NEXUS IR Evaluation System with PostgreSQL."""
    
    def __init__(self):
        """Initialize the IR Evaluation CLI."""
        self.golden_queries_path = DEFAULT_GOLDEN_QUERIES_PATH
        self.settings_path = DEFAULT_SETTINGS_PATH
        
        # Initialize database and QRELS manager
        self.db = IRDatabasePG()
        self.qrels = PGQRELSManager()
        
        # Track the latest run IDs for each configuration
        self.latest_run_ids = self.db.get_latest_run_ids([CONTROL_CONFIG_NAME, EXPERIMENT_CONFIG_NAME])
        
        # Load settings and queries on startup
        self.reload_settings()
    
    def reload_settings(self):
        """Reload settings from settings.json and experimental settings from golden_queries.json."""
        logger.info(f"Loading settings from {self.settings_path}")
        logger.info(f"Loading experimental settings from {self.golden_queries_path}")
        
        # Load settings
        self.settings = load_json(self.settings_path)
        self.golden_queries = load_json(self.golden_queries_path)
        
        # Load control and experimental settings
        self.control_settings = extract_memnon_settings(self.settings)
        self.experimental_settings = None
        
        # Extract experimental settings
        if "settings" in self.golden_queries:
            if "retrieval" in self.golden_queries["settings"]:
                self.experimental_settings = {
                    "retrieval": self.golden_queries["settings"]["retrieval"]
                }
            if "models" in self.golden_queries["settings"]:
                if not self.experimental_settings:
                    self.experimental_settings = {}
                self.experimental_settings["models"] = self.golden_queries["settings"]["models"]
                
        logger.info("Settings loaded successfully")
    
    def show_main_menu(self):
        """Display the main menu and handle user input."""
        while True:
            print("\n" + "="*80)
            print("NEXUS IR Evaluation System (PostgreSQL)")
            print("="*80)
            print("1. Run all golden queries (control vs experiment)")
            print("2. Run query subset")
            print("3. Judge results")
            print("4. Compare results")
            print("5. Display current parameters")
            print("6. Delete runs")
            print("7. Reload settings")
            print("8. AI-assisted judging")
            print("9. Exit")
            
            choice = input("\nEnter choice (1-9): ")
            
            if choice == "1":
                self.run_all_queries()
            elif choice == "2":
                self.run_category_queries()
            elif choice == "3":
                self.judge_results()
            elif choice == "4":
                self.compare_results()
            elif choice == "5":
                self.display_current_parameters()
            elif choice == "6":
                self.delete_runs()
            elif choice == "7":
                self.reload_settings()
                print("Settings and queries reloaded successfully")
            elif choice == "8":
                self.ai_judge_results()
            elif choice == "9":
                print("Exiting NEXUS IR Evaluation System")
                self.db.close()
                break
            else:
                print("Invalid choice. Please try again.")
    
    def run_all_queries(self):
        """Run all golden queries with both control and experimental settings."""
        print("\n" + "="*80)
        print("Running all golden queries")
        print("="*80)
        
        # Get experiment description
        print("\nEnter a brief description of the experimental condition (e.g., 'adding cross-encoder'):")
        experiment_description = input("> ").strip()
        if not experiment_description:
            experiment_description = "Unnamed experiment"
        
        # Run with control settings (from settings.json)
        print("\nRunning with CONTROL settings (from settings.json)...")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        control_run_name = f"Control"  # Keep names short for better display
        
        control_run_id = run_golden_queries(
            self.settings_path,
            self.golden_queries_path,
            CONTROL_CONFIG_NAME,
            control_run_name,
            db=self.db,
            description=f"Control run for: {experiment_description}"
        )
        
        if control_run_id:
            self.latest_run_ids[CONTROL_CONFIG_NAME] = control_run_id
            print(f"Control run saved with ID: {control_run_id}")
        else:
            print("Failed to run control queries")
            return
        
        # Run with experimental settings (from golden_queries.json)
        if self.experimental_settings:
            print("\nRunning with EXPERIMENTAL settings (from golden_queries.json)...")
            
            # Create temporary settings file with experimental settings
            temp_settings_path = create_temp_settings_file(self.settings, self.experimental_settings)
            
            exp_run_name = f"Experiment"  # Keep names short for better display
            
            exp_run_id = run_golden_queries(
                temp_settings_path,
                self.golden_queries_path,
                EXPERIMENT_CONFIG_NAME,
                exp_run_name,
                db=self.db,
                description=f"Experimental run for: {experiment_description}"
            )
            
            # Clean up temporary file
            if os.path.exists(temp_settings_path):
                os.remove(temp_settings_path)
            
            if exp_run_id:
                self.latest_run_ids[EXPERIMENT_CONFIG_NAME] = exp_run_id
                print(f"Experimental run saved with ID: {exp_run_id}")
                
                # Link the runs as a pair in the database
                self.db.link_run_pair(control_run_id, exp_run_id, experiment_description)
                print(f"Control run {control_run_id} and Experimental run {exp_run_id} linked as a pair.")
                
                # Store run IDs as latest for this session
                self.latest_run_ids[CONTROL_CONFIG_NAME] = control_run_id
                self.latest_run_ids[EXPERIMENT_CONFIG_NAME] = exp_run_id
                
                # Just inform the user of next steps instead of triggering the review pipeline
                print("\n" + "="*80)
                print("Run completed successfully!")
                print("You can now:")
                print("1. Judge results using option 3 from the main menu")
                print("2. Compare results using option 4 from the main menu")
                print("="*80)
            else:
                print("Failed to run experimental queries")
        else:
            print("\nNo experimental settings found in golden_queries.json")
    
    def run_category_queries(self):
        """Run queries for a specific category."""
        # Get queries by category from database
        queries_by_category = self.db.get_queries_by_category()
        
        if not queries_by_category:
            print("No categories found in the database. Import queries first.")
            return
                
        # Display available categories
        print("\n" + "="*80)
        print("Available query categories")
        print("="*80)
        
        for i, category in enumerate(queries_by_category.keys(), 1):
            print(f"{i}. {category} ({len(queries_by_category[category])} queries)")
        
        print(f"{len(queries_by_category) + 1}. Return to main menu")
        
        # Get user choice
        while True:
            try:
                choice = int(input("\nSelect category (1-{0}): ".format(len(queries_by_category) + 1)))
                if 1 <= choice <= len(queries_by_category) + 1:
                    break
                else:
                    print("Invalid choice. Please try again.")
            except ValueError:
                print("Invalid input. Please enter a number.")
        
        # Return to main menu if last option selected
        if choice == len(queries_by_category) + 1:
            return
        
        # Get selected category and queries
        category = list(queries_by_category.keys())[choice - 1]
        category_queries = queries_by_category[category]
        
        print(f"\nSelected category: {category} ({len(category_queries)} queries)")
        
        # Get experiment description
        print("\nEnter a brief description of the experimental condition (e.g., 'adding cross-encoder'):")
        experiment_description = input("> ").strip()
        if not experiment_description:
            experiment_description = f"Unnamed experiment - {category} category"
        
        print(f"Running queries for category: {category}")
        
        # Run with control settings (from settings.json)
        print("\nRunning with CONTROL settings (from settings.json)...")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        control_run_name = f"Control {category} {timestamp}"
        
        control_run_id = run_golden_queries(
            self.settings_path,
            self.golden_queries_path,
            CONTROL_CONFIG_NAME,
            control_run_name,
            db=self.db,
            category=category,
            description=f"Control run for: {experiment_description} - {category} category"
        )
        
        if control_run_id:
            self.latest_run_ids[CONTROL_CONFIG_NAME] = control_run_id
            print(f"Control run saved with ID: {control_run_id}")
        else:
            print("Failed to run control queries")
            return
        
        # Run with experimental settings (from golden_queries.json)
        if self.experimental_settings:
            print("\nRunning with EXPERIMENTAL settings (from golden_queries.json)...")
            
            # Create temporary settings file with experimental settings
            temp_settings_path = create_temp_settings_file(self.settings, self.experimental_settings)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            exp_run_name = f"Experiment {category} {timestamp}"
            
            exp_run_id = run_golden_queries(
                temp_settings_path,
                self.golden_queries_path,
                EXPERIMENT_CONFIG_NAME,
                exp_run_name,
                db=self.db,
                category=category,
                description=f"Experimental run for: {experiment_description} - {category} category"
            )
            
            # Clean up temporary file
            if os.path.exists(temp_settings_path):
                os.remove(temp_settings_path)
            
            if exp_run_id:
                self.latest_run_ids[EXPERIMENT_CONFIG_NAME] = exp_run_id
                print(f"Experimental run saved with ID: {exp_run_id}")
                
                # Link the runs as a pair in the database
                self.db.link_run_pair(control_run_id, exp_run_id, f"{experiment_description} - {category} category")
                print(f"Control run {control_run_id} and Experimental run {exp_run_id} linked as a pair.")
                
                print("\n" + "="*80)
                print("Run completed successfully. You can now:")
                print("- Use option 3 to judge any new results")
                print("- Use option 4 to compare control vs experimental results")
                print("="*80)
            else:
                print("Failed to run experimental queries")
        else:
            print("\nNo experimental settings found in golden_queries.json")
    
    def judge_results(self):
        """Judge results interactively using a unified review pipeline."""
        # Refresh the QRELS to ensure we have latest data
        self.qrels = PGQRELSManager()
        
        # Get all runs with unjudged results
        print("\nScanning for all unjudged documents...")
        runs = self.db.get_runs_with_unjudged_results(self.qrels)
        
        if not runs:
            print("\nNo unjudged results found in any runs.")
            return
        
        print("\n" + "="*80)
        print("Unified Review Pipeline")
        print("="*80)
        print("Starting interactive judgment process for all unjudged results.")
        print("Press 'Q' to exit at any time.")
        
        # Create a list of run IDs
        run_ids = [run['id'] for run in runs]
        
        # Judge all unjudged results across all runs
        judgments_added = judge_all_unjudged_results(
            run_ids,
            self.qrels,
            self.golden_queries,
            self.db
        )
        
        print(f"\nAdded {judgments_added} new judgments")
    
    def compare_results(self):
        """Compare results from different experimental runs."""
        # Get paired runs
        pairs = self.db.get_run_pairs()
        
        if not pairs:
            print("\nNo experiment pairs found. Please run queries with control/experiment settings first.")
            return
            
        # Display pairs
        print("\n" + "="*80)
        print("Available experimental runs")
        print("="*80)
        
        for i, pair in enumerate(pairs, 1):
            description = pair.get("description", "No description")
            control_name = pair.get("control_name", f"Control {pair['control_run_id']}")
            experiment_name = pair.get("experiment_name", f"Experiment {pair['experiment_run_id']}")
            timestamp = pair.get("timestamp", "unknown")
            print(f"{i}. {description}")
            print(f"   Control: {control_name} (ID: {pair['control_run_id']})")
            print(f"   Experiment: {experiment_name} (ID: {pair['experiment_run_id']})")
            print(f"   Time: {timestamp}")
            print()
            
        print(f"{len(pairs) + 1}. Return to main menu")
            
        # Get user choice
        try:
            pair_choice = int(input(f"\nSelect experiment to view metrics (1-{len(pairs) + 1}): "))
            if pair_choice == len(pairs) + 1:
                return
                
            if 1 <= pair_choice <= len(pairs):
                pair = pairs[pair_choice - 1]
                run_ids = [pair['control_run_id'], pair['experiment_run_id']]
                # Always use simple names for better table formatting
                run_names = ["Control", "Experiment"]
            else:
                print("Invalid choice. Please try again.")
                return
        except ValueError:
            print("Invalid input. Please enter a number.")
            return
            
        # Force a complete scan for unjudged documents by refreshing from DB
        print("\nScanning for all unjudged documents...")
        
        # Refresh the QRELS to ensure we have latest data
        self.qrels = PGQRELSManager()
        
        # Get updated unjudged counts
        unjudged_counts = self.db.get_unjudged_counts(run_ids, self.qrels)
        
        # Calculate total unjudged
        total_unjudged = sum(unjudged_counts.values())
        if total_unjudged > 0:
            print("\n" + "="*80)
            print(f"IMPORTANT: Found {total_unjudged} unjudged results")
            for run_id, count in unjudged_counts.items():
                if count > 0:
                    run_info = self.db.get_run_metadata(run_id)
                    run_name = run_info.get('name', f'Run {run_id}') if run_info else f'Run {run_id}'
                    print(f"  {run_name}: {count} unjudged documents")
            print("="*80)
            
            # Ask if the user wants to judge new documents
            judge_now = input("\nJudge new results now? (y/n): ").lower().strip()
            if judge_now == 'y':
                # Use the judge_all_unjudged_results function
                added = judge_all_unjudged_results(run_ids, self.qrels, self.golden_queries, self.db)
                print(f"\nAdded {added} new judgments. Ready to compare results.")
        
        # Evaluate each run
        for run_id in run_ids:
            evaluate_run(run_id, self.qrels, self.db)
        
        # Generate comparison
        comparison = compare_runs(run_ids, run_names, self.db)
        
        # Print comparison table
        print_comparison_table(comparison)
        
        print(f"\nComparison saved to database with ID: {comparison.get('id')}")
    
    def view_configurations(self):
        """View details of control and experimental configurations."""
        print("\n" + "="*80)
        print("Configuration details")
        print("="*80)
        
        # Display control configuration
        print("\nCONTROL Configuration (from settings.json):")
        print("-"*80)
        
        if self.control_settings:
            if "retrieval" in self.control_settings:
                retrieval = self.control_settings["retrieval"]
                print("\nRetrieval settings:")
                print(f"  Max results: {retrieval.get('max_results', 'N/A')}")
                print(f"  Relevance threshold: {retrieval.get('relevance_threshold', 'N/A')}")
                print(f"  Entity boost factor: {retrieval.get('entity_boost_factor', 'N/A')}")
                
                # Hybrid search
                if "hybrid_search" in retrieval:
                    hybrid = retrieval["hybrid_search"]
                    print("\nHybrid search:")
                    print(f"  Enabled: {hybrid.get('enabled', False)}")
                    print(f"  Vector weight: {hybrid.get('vector_weight_default', 'N/A')}")
                    print(f"  Text weight: {hybrid.get('text_weight_default', 'N/A')}")
                    print(f"  Target model: {hybrid.get('target_model', 'N/A')}")
                    print(f"  Temporal boost factor: {hybrid.get('temporal_boost_factor', 'N/A')}")
                    print(f"  Query-specific temporal factors: {hybrid.get('use_query_type_temporal_factors', False)}")
                
                # User character focus boost
                if "user_character_focus_boost" in retrieval:
                    focus = retrieval["user_character_focus_boost"]
                    print("\nUser character focus boost:")
                    print(f"  Enabled: {focus.get('enabled', False)}")
            
            # Models
            if "models" in self.control_settings:
                print("\nModels:")
                for model, config in self.control_settings["models"].items():
                    active = config.get("is_active", False)
                    if active:
                        print(f"  {model}: dimensions={config.get('dimensions', 'N/A')}, weight={config.get('weight', 'N/A')}")
        else:
            print("No control settings found")
        
        # Display experimental configuration
        print("\nEXPERIMENTAL Configuration (from golden_queries.json):")
        print("-"*80)
        
        if self.experimental_settings:
            if "retrieval" in self.experimental_settings:
                retrieval = self.experimental_settings["retrieval"]
                print("\nRetrieval settings:")
                print(f"  Max results: {retrieval.get('max_results', 'N/A')}")
                print(f"  Relevance threshold: {retrieval.get('relevance_threshold', 'N/A')}")
                print(f"  Entity boost factor: {retrieval.get('entity_boost_factor', 'N/A')}")
                
                # Hybrid search
                if "hybrid_search" in retrieval:
                    hybrid = retrieval["hybrid_search"]
                    print("\nHybrid search:")
                    print(f"  Enabled: {hybrid.get('enabled', False)}")
                    print(f"  Vector weight: {hybrid.get('vector_weight_default', 'N/A')}")
                    print(f"  Text weight: {hybrid.get('text_weight_default', 'N/A')}")
                    print(f"  Target model: {hybrid.get('target_model', 'N/A')}")
                    print(f"  Temporal boost factor: {hybrid.get('temporal_boost_factor', 'N/A')}")
                    print(f"  Query-specific temporal factors: {hybrid.get('use_query_type_temporal_factors', False)}")
                
                # User character focus boost
                if "user_character_focus_boost" in retrieval:
                    focus = retrieval["user_character_focus_boost"]
                    print("\nUser character focus boost:")
                    print(f"  Enabled: {focus.get('enabled', False)}")
            
            # Models
            if "models" in self.experimental_settings:
                print("\nModels:")
                for model, config in self.experimental_settings["models"].items():
                    active = config.get("is_active", False)
                    if active:
                        print(f"  {model}: dimensions={config.get('dimensions', 'N/A')}, weight={config.get('weight', 'N/A')}")
        else:
            print("No experimental settings found in golden_queries.json")
        
        input("\nPress Enter to continue...")
    
    def display_current_parameters(self):
        """
        Display side-by-side comparison of control and experimental settings 
        and provide options to synchronize them.
        """
        try:
            # Import settings comparison module
            import sys
            import os
            scripts_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
            if scripts_path not in sys.path:
                sys.path.insert(0, scripts_path)
                
            # Try to import the settings_compare module
            try:
                import settings_compare
                
                # Show settings management menu
                settings_compare.show_settings_management_menu(self.settings_path, self.golden_queries_path)
                
            except ImportError:
                logger.error("Could not import settings_compare module, using basic display instead")
                # Fall back to basic display if module is not found
                self._display_current_parameters_basic()
        except Exception as e:
            logger.error(f"Error in settings comparison: {e}")
            print(f"Error comparing settings: {e}")
            # Fall back to basic display
            self._display_current_parameters_basic()
            
        input("\nPress Enter to continue...")
    
    def _display_current_parameters_basic(self):
        """Display current parameter values in a simple copy-paste friendly format."""
        print("\n" + "="*80)
        print("Current Parameters (Copy-Paste Ready)")
        print("="*80)
        
        # Get settings.json
        settings_content = load_json(self.settings_path)
        golden_queries_content = load_json(self.golden_queries_path)
        
        # Extract MEMNON settings
        memnon_settings = {}
        if "Agent Settings" in settings_content and "MEMNON" in settings_content["Agent Settings"]:
            memnon_settings = settings_content["Agent Settings"]["MEMNON"]
        
        # Extract experimental settings
        experimental_settings = {}
        if "settings" in golden_queries_content:
            experimental_settings = golden_queries_content["settings"]
        
        # Format settings.json relevant parts
        print("\n```json")
        print("// Current settings.json MEMNON configuration")
        if memnon_settings:
            memnon_formatted = json.dumps(memnon_settings, indent=2)
            print(memnon_formatted)
        else:
            print("{}")
        print("```\n")
        
        # Format golden_queries.json settings
        print("\n```json")
        print("// Current golden_queries.json settings configuration")
        if experimental_settings:
            experimental_formatted = json.dumps(experimental_settings, indent=2)
            print(experimental_formatted)
        else:
            print("{}")
        print("```\n")
        
        # Print helpful note
        print("The above JSON blocks can be copied and pasted directly for use in discussions about parameter tuning.")
        print("To modify settings:")
        print("1. Edit settings.json to update control configuration")
        print("2. Edit golden_queries.json to update experimental configuration")
        
    def delete_runs(self):
        """Delete one or more runs from the database."""
        # Get available runs
        runs = self.db.get_runs(limit=20)  # Get up to 20 most recent runs
        
        if not runs:
            print("\nNo runs found in the database.")
            return
            
        print("\n" + "="*80)
        print("Delete Runs")
        print("="*80)
        print("WARNING: Deleting runs will permanently remove the run data and all associated results!")
        print("This action cannot be undone. Proceed with caution.")
        
        # Display runs for selection
        print("\nAvailable runs:")
        for i, run in enumerate(runs, 1):
            run_time = run.get('timestamp', 'Unknown time')
            if isinstance(run_time, str):
                run_time_display = run_time[:19]  # Truncate timestamp for display
            else:
                run_time_display = str(run_time)[:19]
                
            print(f"{i}. {run.get('name', 'Unnamed')} (ID: {run.get('id')}) - {run_time_display}")
            print(f"   Config: {run.get('config_type', 'Unknown')}")
            if run.get('description'):
                print(f"   Description: {run.get('description')}")
            print()
            
        print(f"{len(runs) + 1}. Delete multiple runs")
        print(f"{len(runs) + 2}. Return to main menu")
        
        # Get user selection
        try:
            choice = int(input(f"\nSelect run to delete (1-{len(runs) + 2}): "))
            
            # Return to main menu
            if choice == len(runs) + 2:
                return
                
            # Delete a single run
            if 1 <= choice <= len(runs):
                selected_run = runs[choice - 1]
                run_id = selected_run.get('id')
                run_name = selected_run.get('name', f"Run {run_id}")
                
                # Confirm deletion
                confirm = input(f"\nAre you sure you want to delete run {run_name} (ID: {run_id})? (y/n): ").lower()
                if confirm == 'y':
                    # Attempt to delete run
                    if self._delete_run(run_id):
                        print(f"Run {run_name} (ID: {run_id}) has been deleted successfully.")
                    else:
                        print(f"Failed to delete run {run_name} (ID: {run_id}).")
                else:
                    print("Deletion cancelled.")
            
            # Delete multiple runs
            elif choice == len(runs) + 1:
                self._delete_multiple_runs(runs)
                
            else:
                print("Invalid choice. Please try again.")
                
        except ValueError:
            print("Invalid input. Please enter a number.")
            
    def _delete_run(self, run_id: int) -> bool:
        """
        Delete a single run from the database.
        
        Args:
            run_id: ID of the run to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create a cursor
            cursor = self.db.conn.cursor()
            
            # Delete all related records first (cascade should handle this, but just to be safe)
            cursor.execute("DELETE FROM ir_eval.metrics WHERE run_id = %s", (run_id,))
            cursor.execute("DELETE FROM ir_eval.results WHERE run_id = %s", (run_id,))
            cursor.execute("DELETE FROM ir_eval.run_pair_links WHERE control_run_id = %s OR experiment_run_id = %s", 
                         (run_id, run_id))
            
            # Finally delete the run itself
            cursor.execute("DELETE FROM ir_eval.runs WHERE id = %s", (run_id,))
            
            # Commit the transaction
            self.db.conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error deleting run {run_id}: {e}")
            self.db.conn.rollback()
            return False
            
    def ai_judge_results(self):
        """Use AI to assist with judging results."""
        # Refresh the QRELS to ensure we have latest data
        self.qrels = PGQRELSManager()
        
        # Get runs with unjudged results
        print("\nScanning for runs with unjudged documents...")
        runs = self.db.get_runs_with_unjudged_results(self.qrels)
        
        if not runs:
            print("\nNo runs with unjudged results found.")
            return
            
        # Display runs for selection
        print("\n" + "="*80)
        print("AI-Assisted Judging")
        print("="*80)
        print("This will use OpenAI API to automatically judge unjudged search results.")
        print("The following runs have unjudged results:")
        
        for i, run in enumerate(runs, 1):
            run_time = run.get('timestamp', 'Unknown time')
            if isinstance(run_time, str):
                run_time_display = run_time[:19]  # Truncate timestamp
            else:
                run_time_display = str(run_time)[:19]
                
            print(f"{i}. {run.get('name', 'Unnamed')} (ID: {run.get('id')}) - {run_time_display}")
            print(f"   {run.get('description', 'No description')}")
            print()
            
        print(f"{len(runs) + 1}. Judge multiple runs")
        print(f"{len(runs) + 2}. Return to main menu")
        
        # Get user selection
        try:
            choice = int(input(f"\nSelect run to judge (1-{len(runs) + 2}): "))
            
            # Return to main menu
            if choice == len(runs) + 2:
                return
                
            # Get model and configuration
            model = input("\nEnter OpenAI model to use (default: gpt-4.1): ").strip() or "gpt-4.1"
            temp_input = input("Enter temperature (0.0-1.0, default: 0.2): ").strip()
            temperature = float(temp_input) if temp_input else 0.2
            
            dry_run = input("Dry run (don't save judgments)? (y/n, default: n): ").strip().lower() == 'y'
            debug = input("Debug mode (verbose output)? (y/n, default: n): ").strip().lower() == 'y'
            
            # Initialize AI Judge
            ai_judge = AIJudge(
                model=model,
                temperature=temperature,
                dry_run=dry_run,
                debug=debug
            )
            
            # Judge a single run
            if 1 <= choice <= len(runs):
                selected_run = runs[choice - 1]
                run_id = selected_run.get('id')
                run_name = selected_run.get('name', f"Run {run_id}")
                
                print(f"\nJudging run {run_name} (ID: {run_id}) with model {model}...")
                
                # Import the judge_run function dynamically
                from scripts.auto_judge import judge_run
                
                # Run the judging process
                judgments = judge_run(
                    run_id=run_id,
                    ai_judge=ai_judge,
                    db=self.db,
                    qrels=self.qrels
                )
                
                print(f"\nCompleted AI-assisted judging for run {run_name}")
                print(f"Added {judgments} new judgments")
                input("\nPress Enter to continue...")
                
            # Judge multiple runs
            elif choice == len(runs) + 1:
                self._judge_multiple_runs(runs, ai_judge)
                
            else:
                print("Invalid choice. Please try again.")
                
        except ValueError:
            print("Invalid input. Please enter a number.")
    
    def _judge_multiple_runs(self, available_runs: List[Dict[str, Any]], ai_judge: AIJudge) -> None:
        """
        Judge multiple runs at once.
        
        Args:
            available_runs: List of run dictionaries to choose from
            ai_judge: Initialized AIJudge instance
        """
        print("\n" + "="*80)
        print("Judge Multiple Runs")
        print("="*80)
        print("Enter the numbers of the runs to judge, separated by commas.")
        print("Example: 1,3,5 will judge runs 1, 3, and 5 from the list.")
        print("Enter 'all' to judge all runs with unjudged results.")
        print("Enter 'cancel' to return to the main menu.")
        
        # Get user selection
        selection = input("\nEnter run numbers to judge: ").strip().lower()
        
        if selection == 'cancel':
            print("Judging cancelled.")
            return
            
        run_ids = []
        
        # Handle 'all' option
        if selection == 'all':
            run_ids = [run.get('id') for run in available_runs]
        
        # Handle comma-separated list
        else:
            try:
                # Parse the comma-separated numbers
                selected_indices = [int(idx.strip()) for idx in selection.split(',') if idx.strip()]
                
                # Validate the indices
                valid_indices = [idx for idx in selected_indices if 1 <= idx <= len(available_runs)]
                
                if not valid_indices:
                    print("No valid run numbers provided. Judging cancelled.")
                    return
                    
                # Extract run IDs for the valid indices
                for idx in valid_indices:
                    run_ids.append(available_runs[idx - 1].get('id'))
                    
            except ValueError:
                print("Invalid input. Please enter comma-separated numbers.")
                return
        
        # Confirm judging
        if run_ids:
            run_names = ', '.join([f"{run.get('name', 'Unnamed')} (ID: {run.get('id')})" 
                                 for run in available_runs if run.get('id') in run_ids])
            
            confirm = input(f"\nAre you sure you want to judge these runs?\n{run_names}\n(y/n): ").lower()
            
            if confirm == 'y':
                # Import the judge_run function dynamically
                from scripts.auto_judge import judge_run
                
                # Judge each run
                total_judgments = 0
                for run_id in run_ids:
                    # Get run info for display
                    run_info = next((run for run in available_runs if run.get('id') == run_id), None)
                    run_name = run_info.get('name', f"Run {run_id}") if run_info else f"Run {run_id}"
                    
                    print(f"\nJudging run {run_name} (ID: {run_id})...")
                    
                    # Run the judging process
                    judgments = judge_run(
                        run_id=run_id,
                        ai_judge=ai_judge,
                        db=self.db,
                        qrels=self.qrels
                    )
                    
                    total_judgments += judgments
                    print(f"Added {judgments} new judgments")
                    
                print(f"\nCompleted AI-assisted judging for all runs")
                print(f"Total judgments added: {total_judgments}")
                input("\nPress Enter to continue...")
            else:
                print("Judging cancelled.")
                
    def _delete_multiple_runs(self, available_runs: List[Dict[str, Any]]) -> None:
        """
        Delete multiple runs at once.
        
        Args:
            available_runs: List of run dictionaries to choose from
        """
        print("\n" + "="*80)
        print("Delete Multiple Runs")
        print("="*80)
        print("Enter the numbers of the runs to delete, separated by commas.")
        print("Example: 1,3,5 will delete runs 1, 3, and 5 from the list.")
        print("Enter 'all' to delete all runs (will reset IDs to start from 1).")
        print("Enter 'cancel' to return to the main menu.")
        
        # Get user selection
        selection = input("\nEnter run numbers to delete: ").strip().lower()
        
        if selection == 'cancel':
            print("Deletion cancelled.")
            return
            
        run_ids_to_delete = []
        is_deleting_all = False
        
        # Handle 'all' option
        if selection == 'all':
            confirm = input("\nWARNING: This will delete ALL runs in the database and reset IDs to start from 1. Are you ABSOLUTELY sure? (type 'yes' to confirm): ")
            if confirm.lower() != 'yes':
                print("Deletion cancelled.")
                return
                
            run_ids_to_delete = [run.get('id') for run in available_runs]
            is_deleting_all = True
            
        # Handle comma-separated list
        else:
            try:
                # Parse the comma-separated numbers
                selected_indices = [int(idx.strip()) for idx in selection.split(',') if idx.strip()]
                
                # Validate the indices
                valid_indices = [idx for idx in selected_indices if 1 <= idx <= len(available_runs)]
                
                if not valid_indices:
                    print("No valid run numbers provided. Deletion cancelled.")
                    return
                    
                # Extract run IDs for the valid indices
                for idx in valid_indices:
                    run_ids_to_delete.append(available_runs[idx - 1].get('id'))
                    
            except ValueError:
                print("Invalid input. Please enter comma-separated numbers.")
                return
        
        # Confirm deletion
        if run_ids_to_delete:
            run_names = ', '.join([f"{run.get('name', 'Unnamed')} (ID: {run.get('id')})" 
                                 for run in available_runs if run.get('id') in run_ids_to_delete])
            
            confirm = input(f"\nAre you sure you want to delete these runs?\n{run_names}\n(y/n): ").lower()
            
            if confirm == 'y':
                # Delete each run
                success_count = 0
                for run_id in run_ids_to_delete:
                    if self._delete_run(run_id):
                        success_count += 1
                
                # If we deleted all runs, reset the sequence
                if is_deleting_all and success_count == len(run_ids_to_delete) and success_count > 0:
                    try:
                        cursor = self.db.conn.cursor()
                        cursor.execute("SELECT ir_eval.reset_run_id_sequence()")
                        self.db.conn.commit()
                        print("\nAll runs deleted. ID sequence has been reset to start from 1.")
                    except Exception as e:
                        logger.error(f"Error resetting run ID sequence: {e}")
                        print("\nAll runs deleted, but failed to reset ID sequence. New runs will continue from the previous sequence.")
                else:
                    print(f"\nDeleted {success_count} out of {len(run_ids_to_delete)} runs.")
            else:
                print("Deletion cancelled.")

def main():
    """Main entry point."""
    cli = IREvalPGCLI()
    cli.show_main_menu()

if __name__ == "__main__":
    main()