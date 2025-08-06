#!/usr/bin/env python3
"""
NEXUS IR Evaluation System

This integrated tool provides an interactive interface for evaluating and comparing
the performance of different retrieval configurations for the NEXUS retrieval system.

Main features:
- Run golden queries with different configurations (control vs experimental)
- Score search results interactively
- Compare performance metrics across configurations
- Analyze results by query category

Usage:
    python ir_eval.py

This launches an interactive menu-driven interface.
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
import sqlite3
from typing import Dict, List, Any, Tuple, Optional, Set
from pathlib import Path

# Ensure we can import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import local modules if they exist, otherwise use paths
try:
    from ir_eval.scripts.qrels import QRELSManager
    from ir_eval.scripts.ir_metrics import calculate_all_metrics, average_metrics_by_category
    from ir_eval.db import IRDatabase, DEFAULT_DB_PATH
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
    from qrels import QRELSManager
    from ir_metrics import calculate_all_metrics, average_metrics_by_category
    from db import IRDatabase, DEFAULT_DB_PATH

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ir_eval.log")),
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
    k: int = 10,
    db: Optional[IRDatabase] = None,
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
        db: IRDatabase instance
        
    Returns:
        ID of the run in the database
    """
    # Use provided database or create one
    if db is None:
        db = IRDatabase()
    
    # Set default run name if not provided
    if run_name is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_name = f"{config_type}_{timestamp}"
    
    # Import the golden queries module directly
    try:
        # Add the scripts directory to the Python path
        nexus_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        scripts_dir = os.path.join(nexus_root, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        
        from golden_queries_module import run_queries
        
        logger.info(f"Imported golden_queries_module - running queries directly")
        
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
                run_description = f"Generated by ir_eval.py with {config_type} configuration"
                
            run_id = db.add_run(
                name=run_name, 
                settings=settings, 
                config_type=config_type, 
                description=run_description
            )
            
            if not run_id:
                logger.error("Failed to add run to database")
                return None
            
            # Save query results to database - this is where we'll focus debugging
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

def extract_query_variations(golden_queries_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract query variations from golden_queries.json.
    
    Looks for fields named "query_variation" alongside "query" fields.
    
    Returns:
        Dictionary mapping category names to lists of variation dictionaries
    """
    query_variations = {}
    
    for category, queries in golden_queries_data.items():
        if category != "settings" and isinstance(queries, dict):
            variations = []
            
            for name, info in queries.items():
                if isinstance(info, dict) and "query" in info and "query_variation" in info:
                    # Create a variation entry with original query info but using the variation text
                    variation = {
                        "original_name": name,
                        "original_query": info["query"],
                        "variation_query": info["query_variation"],
                        "category": category,
                        "positives": info.get("positives", []),
                        "negatives": info.get("negatives", [])
                    }
                    variations.append(variation)
            
            if variations:
                query_variations[category] = variations
    
    return query_variations

def create_variations_file(original_data: Dict[str, Any], category: str, variations: List[Dict[str, Any]]) -> str:
    """
    Create a temporary golden queries file with both original queries and variations for a single category.
    
    Args:
        original_data: The original golden_queries.json data
        category: The category to update with variations
        variations: The list of variation dictionaries
        
    Returns:
        Path to the temporary file
    """
    # Create a deep copy of the original data
    data_copy = json.loads(json.dumps(original_data))
    
    # Get existing queries for this category
    existing_queries = {}
    if category in data_copy:
        existing_queries = data_copy[category]
    
    # Add variations to the existing queries
    for i, variation in enumerate(variations):
        # Create a variation entry with a unique name
        original_name = variation["original_name"]
        variation_name = f"{original_name} - Variation"
        
        # Create the query data structure
        existing_queries[variation_name] = {
            "query": variation["variation_query"],
            "original_query": variation["original_query"],
            "positives": variation["positives"],
            "negatives": variation["negatives"]
        }
    
    # Update the category in the copied data with both originals and variations
    if category in data_copy:
        data_copy[category] = existing_queries
    
    # Write to a temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.json', prefix='nexus_variations_')
    os.close(fd)
    
    with open(temp_path, 'w') as f:
        json.dump(data_copy, f, indent=2)
    
    logger.info(f"Created temporary variations file: {temp_path}")
    return temp_path

def create_variations_file_all_categories(original_data: Dict[str, Any], all_variations: List[Dict[str, Any]]) -> str:
    """
    Create a temporary golden queries file with BOTH original queries AND their variations.
    
    Args:
        original_data: The original golden_queries.json data
        all_variations: List of all variation dictionaries from all categories
        
    Returns:
        Path to the temporary file
    """
    # Create a deep copy of the original data
    data_copy = json.loads(json.dumps(original_data))
    
    # Group variations by category
    variations_by_category = {}
    for variation in all_variations:
        category = variation["category"]
        if category not in variations_by_category:
            variations_by_category[category] = []
        variations_by_category[category].append(variation)
    
    # Process each category
    for category, variations in variations_by_category.items():
        # Get existing queries for this category
        existing_queries = {}
        if category in data_copy:
            existing_queries = data_copy[category]
        
        # Add variation queries to existing queries
        for i, variation in enumerate(variations):
            # Create a variation entry with a unique name
            original_name = variation["original_name"]
            variation_name = f"{original_name} - Variation"
            
            # Create the query data structure
            existing_queries[variation_name] = {
                "query": variation["variation_query"],
                "original_query": variation["original_query"],
                "positives": variation["positives"],
                "negatives": variation["negatives"]
            }
        
        # Update the category in the copied data
        if category in data_copy:
            data_copy[category] = existing_queries
    
    # Write to a temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.json', prefix='nexus_variations_all_')
    os.close(fd)
    
    with open(temp_path, 'w') as f:
        json.dump(data_copy, f, indent=2)
    
    logger.info(f"Created temporary variations file with all categories: {temp_path}")
    return temp_path

def judge_all_unjudged_results(
    run_ids: List[int],
    qrels: QRELSManager,
    golden_queries_data: Dict[str, Any],
    db: Optional[IRDatabase] = None
) -> int:
    """
    Interactive tool for judging all unjudged search results across multiple runs.
    
    Args:
        run_ids: List of database IDs of runs to judge
        qrels: QRELSManager instance
        golden_queries_data: Golden queries data
        db: IRDatabase instance
        
    Returns:
        Number of judgments added
    """
    # Use provided database or create one
    if db is None:
        db = IRDatabase()
    
    # Track judgments added in this session
    judgments_added = 0
    
    # Track the last judgment for undo functionality
    last_judgment = None
    
    # Keep track of queries we've seen to avoid duplicates
    processed_queries = set()
    
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
                doc_id = str(result.get("id", ""))
                
                # Skip already judged documents
                if doc_id in judged_docs:
                    i += 1
                    continue
                
                text = result.get("text", "")
                score = result.get("score", 0)
                vector_score = result.get("vector_score", None)
                text_score = result.get("text_score", None)
                source = result.get("source", "unknown")
                
                # Format scores for display
                score_display = f"Score: {score:.4f}"
                
                # Always show vector and text scores when they exist
                # regardless of the source
                
                # Explicitly convert vector_score to float if it exists
                if vector_score is not None:
                    try:
                        vector_score = float(vector_score)
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert vector_score {vector_score} to float")
                        vector_score = 0.0
                else:
                    vector_score = 0.0
                    
                # Explicitly convert text_score to float if it exists
                if text_score is not None:
                    try:
                        text_score = float(text_score)
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert text_score {text_score} to float")
                        text_score = 0.0
                else:
                    text_score = 0.0
                
                # Always include both scores in the display
                score_display += f" (Vector: {vector_score:.4f}, Text: {text_score:.4f})"
                
                # Display the document
                print("\n" + "="*80)
                print(f"Document {i+1}/{len(results)} (ID: {doc_id}, {score_display})")
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
                        undo_query, undo_doc_id = last_judgment
                        # Remove the judgment by setting it to None
                        print(f"Undoing judgment for document {undo_doc_id}...")
                        
                        # Remove from judged_docs set for the current query
                        if undo_query == query_text and undo_doc_id in judged_docs:
                            judged_docs.remove(undo_doc_id)
                        
                        # Remove judgment from database
                        db.remove_judgment(undo_query, undo_doc_id)
                        
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
                        break
                    
                    # Handle numeric rating
                    try:
                        relevance = int(relevance_input)
                        if 0 <= relevance <= 3:
                            # Add judgment
                            qrels.add_judgment(
                                query_text,
                                doc_id,
                                relevance,
                                category,
                                text
                            )
                            
                            # ENHANCEMENT: Auto-copy judgments between original queries and variations
                            # First, check if this is a variation query
                            is_variation = " - Variation" in query_data.get("name", "")
                            original_query = None
                            variation_query = None
                            
                            if is_variation:
                                # This is a variation, find the original query
                                variation_query = query_text
                                original_name = query_data.get("name", "").replace(" - Variation", "")
                                
                                # Find the original query in golden_queries
                                for cat in self.golden_queries:
                                    if cat != "settings" and isinstance(self.golden_queries[cat], dict):
                                        if original_name in self.golden_queries[cat]:
                                            original_query = self.golden_queries[cat][original_name].get("query", "")
                                            break
                                            
                            else:
                                # This is an original, find if it has a variation
                                original_query = query_text
                                query_name = query_data.get("name", "")
                                
                                # Check if a variation exists for this query
                                variation_name = f"{query_name} - Variation"
                                for q_data in query_results:
                                    if q_data.get("name", "") == variation_name:
                                        variation_query = q_data.get("query", "")
                                        break
                            
                            # If we found a matching query, copy the judgment
                            if original_query and variation_query and original_query != variation_query:
                                # Determine which one to copy to
                                target_query = original_query if is_variation else variation_query
                                print(f"\n📋 Auto-copying judgment to paired query: {target_query}")
                                
                                # Add the same judgment to the paired query
                                qrels.add_judgment(
                                    target_query,
                                    doc_id,
                                    relevance,
                                    category,
                                    text
                                )
                                
                                # Note the additional judgment in our counts
                                judgments_added += 1
                            
                            # Update tracking variables
                            judged_docs.add(doc_id)
                            judgments_added += 1
                            last_judgment = (query_text, doc_id)
                            
                            # Move to next document
                            i += 1
                            break
                        else:
                            print("Please enter a number between 0 and 3, or Q to quit, U to undo, S to skip")
                    except ValueError:
                        print("Please enter a number between 0 and 3, or Q to quit, U to undo, S to skip")
    
    print("\n" + "="*80)
    print(f"Judging complete! Added {judgments_added} new relevance judgments")
    print(f"Total judgments in file: {qrels.get_judgment_count()}")
    
    return judgments_added

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

def compare_runs(
    run_ids: List[int],
    run_names: List[str],
    db: Optional[IRDatabase] = None
) -> Dict[str, Any]:
    """
    Compare multiple runs and identify the best performer.
    
    Args:
        run_ids: List of database IDs for runs to compare
        run_names: List of names for each run
        db: IRDatabase instance
        
    Returns:
        Dictionary with comparison results and ID
    """
    # Use provided database or create one
    if db is None:
        db = IRDatabase()
    
    # Ensure we have names for all runs
    if len(run_names) < len(run_ids):
        for i in range(len(run_names), len(run_ids)):
            run_names.append(f"Run {chr(65 + i)}")
    
    # Get metrics for each run
    run_results = []
    for run_id in run_ids:
        metrics = db.get_run_metrics(run_id)
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

class IREvalCLI:
    """Interactive CLI for NEXUS IR Evaluation System."""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize the IR Evaluation CLI.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.golden_queries_path = DEFAULT_GOLDEN_QUERIES_PATH
        self.settings_path = DEFAULT_SETTINGS_PATH
        self.db_path = db_path
        
        # Initialize database and QRELS manager
        self.db = IRDatabase(db_path)
        self.qrels = QRELSManager(db_path)
        
        # Track the latest run IDs for each configuration
        self.latest_run_ids = self.db.get_latest_run_ids([CONTROL_CONFIG_NAME, EXPERIMENT_CONFIG_NAME])
        
        # Load settings and queries on startup
        self.reload_settings()
    
    def reload_settings(self):
        """Reload settings and golden queries from their respective files."""
        logger.info(f"Loading golden queries from {self.golden_queries_path}")
        logger.info(f"Loading settings from {self.settings_path}")
        
        # Load golden queries and settings
        self.golden_queries = load_json(self.golden_queries_path)
        self.settings = load_json(self.settings_path)
        
        # Load control and experimental settings
        self.control_settings = extract_memnon_settings(self.settings)
        self.experimental_settings = None
        if "settings" in self.golden_queries:
            if "retrieval" in self.golden_queries["settings"]:
                self.experimental_settings = {
                    "retrieval": self.golden_queries["settings"]["retrieval"]
                }
            if "models" in self.golden_queries["settings"]:
                if not self.experimental_settings:
                    self.experimental_settings = {}
                self.experimental_settings["models"] = self.golden_queries["settings"]["models"]
                
        logger.info("Settings and golden queries loaded successfully")
    
    def show_main_menu(self):
        """Display the main menu and handle user input."""
        while True:
            print("\n" + "="*80)
            print("NEXUS IR Evaluation System")
            print("="*80)
            print("1. Run all golden queries (control vs experiment)")
            print("2. Run query subset")
            print("3. Judge results")
            print("4. Compare results")
            print("5. View configuration details")
            print("6. Display current parameters")
            print("7. Reload settings")
            print("8. Delete runs")
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
                self.view_configurations()
            elif choice == "6":
                self.display_current_parameters()
            elif choice == "7":
                self.reload_settings()
                print("Settings and queries reloaded successfully")
            elif choice == "8":
                self.delete_runs()
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
        control_run_name = f"Control {timestamp}"
        
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
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            exp_run_name = f"Experiment {timestamp}"
            
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
            else:
                print("Failed to run experimental queries")
        else:
            print("\nNo experimental settings found in golden_queries.json")
    
    def run_category_queries(self):
        """Run queries for a specific category or compare query variations."""
        # Get queries by category
        queries_by_category = get_query_data_by_category(self.golden_queries)
        
        if not queries_by_category:
            print("No categories found in golden_queries.json")
            return
        
        # Display available options
        print("\n" + "="*80)
        print("Query Subset Options")
        print("="*80)
        print("1. Run queries for specific category")
        print("2. Compare query variations")
        print("3. Return to main menu")
        
        # Get user choice for mode
        choice = input("\nSelect option (1-3): ")
        
        if choice == "3":
            return
        elif choice == "2":
            self.run_query_variations()
            return
        elif choice != "1":
            print("Invalid choice. Please try again.")
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
        
        # TODO: Implement running specific queries once run_golden_queries.py supports it
        # For now, just run all queries
        
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
            category=category,  # This is valid here - category is defined in run_category_queries
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
                category=category,  # This is valid here - category is defined in run_category_queries
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
            else:
                print("Failed to run experimental queries")
        else:
            print("\nNo experimental settings found in golden_queries.json")
            
    def run_query_variations(self):
        """Run query variations using control settings only."""
        # Get queries and their variations
        query_variations = extract_query_variations(self.golden_queries)
        
        if not query_variations:
            print("\nNo query variations found in golden_queries.json.")
            print("To use this feature, add a 'query_variation' field next to 'query' fields.")
            return
            
        # Display available categories with variations
        print("\n" + "="*80)
        print("Available categories with query variations")
        print("="*80)
        
        # Count total variations across all categories
        total_variations = sum(len(variations) for variations in query_variations.values())
        
        print("0. Run ALL query variations across ALL categories")
        
        categories_with_variations = {}
        i = 1
        
        for category, variations in query_variations.items():
            if len(variations) > 0:
                categories_with_variations[i] = category
                print(f"{i}. {category} ({len(variations)} variations)")
                i += 1
        
        if not categories_with_variations:
            print("No categories with query variations found.")
            return
            
        print(f"{len(categories_with_variations) + 1}. Return to main menu")
        
        # Get user choice
        while True:
            try:
                choice = int(input(f"\nSelect option (0-{len(categories_with_variations) + 1}): "))
                if 0 <= choice <= len(categories_with_variations) + 1:
                    break
                else:
                    print("Invalid choice. Please try again.")
            except ValueError:
                print("Invalid input. Please enter a number.")
        
        # Return to main menu if last option selected
        if choice == len(categories_with_variations) + 1:
            return
            
        # Run all variations across all categories
        if choice == 0:
            # Flatten all variations into a single list
            all_variations = []
            for category, variations in query_variations.items():
                for var in variations:
                    var["category"] = category  # Ensure category is set
                    all_variations.append(var)
                    
            print(f"\nPreparing to run ALL query variations ({total_variations} total)...")
            
            # Get experiment description
            print("\nEnter a brief description for this query variation comparison:")
            experiment_description = input("> ").strip()
            if not experiment_description:
                experiment_description = f"All query variations comparison"
            
            # Create temp golden queries file with all variations as regular queries
            variations_file = create_variations_file_all_categories(self.golden_queries, all_variations)
            
            print(f"\nRunning {total_variations} query variations with control settings...")
            
            # Run with control settings only
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = f"All Query Variations {timestamp}"
            
            run_id = run_golden_queries(
                self.settings_path,
                variations_file,
                "query_variations",
                run_name,
                db=self.db,
                description=f"Query variation comparison: {experiment_description} - ALL categories"
            )
            
            # Clean up temporary file
            if os.path.exists(variations_file):
                os.remove(variations_file)
            
            if run_id:
                print(f"\nQuery variations run completed and saved with ID: {run_id}")
                print("Use 'Compare results' to view metrics for this run.")
            else:
                print("Failed to run query variations.")
            
            return
        
        # Get selected category and variations
        category = categories_with_variations[choice]
        variations = query_variations[category]
        
        print(f"\nSelected category: {category} ({len(variations)} variations)")
        
        # Get experiment description
        print("\nEnter a brief description for this query variation comparison:")
        experiment_description = input("> ").strip()
        if not experiment_description:
            experiment_description = f"Query variation comparison - {category} category"
        
        # Create temp golden queries file with variations as regular queries
        variations_file = create_variations_file(self.golden_queries, category, variations)
        
        print(f"\nRunning {len(variations)} query variations with control settings...")
        
        # Run with control settings only
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_name = f"Query Variations {category} {timestamp}"
        
        run_id = run_golden_queries(
            self.settings_path,
            variations_file,
            "query_variations",
            run_name,
            db=self.db,
            category=category,
            description=f"Query variation comparison: {experiment_description} - {category} category"
        )
        
        # Clean up temporary file
        if os.path.exists(variations_file):
            os.remove(variations_file)
        
        if run_id:
            print(f"\nQuery variations run completed and saved with ID: {run_id}")
            print("Use 'Compare results' to view metrics for this run.")
        else:
            print("Failed to run query variations.")
    
    def judge_results(self):
        """Judge results interactively using a unified review pipeline."""
        # Get all runs with unjudged results
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
        
        # Get all runs for manual comparison
        all_runs = self.db.get_runs(limit=20)  # Get up to 20 most recent runs
        
        # Check if we have any query variation runs
        query_variation_runs = []
        for run in all_runs:
            if run.get('config_type') == 'query_variations':
                query_variation_runs.append(run)
        
        if not pairs and not query_variation_runs:
            print("\nNo experiment pairs or query variation runs found. Please run queries with control/experiment settings first.")
            return
        
        # Display options menu
        print("\n" + "="*80)
        print("Available Comparisons")
        print("="*80)
        print("1. Compare control vs experiment runs")
        print("2. Compare query variations")
        print("3. Return to main menu")
        
        choice = input("\nSelect comparison type (1-3): ")
        
        if choice == "3":
            return
        elif choice == "2":
            self._compare_query_variations(query_variation_runs)
            return
        elif choice != "1":
            print("Invalid choice. Please try again.")
            return
            
        # Continue with control vs experiment comparison
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
                run_names = [pair.get("control_name", "Control"), pair.get("experiment_name", "Experiment")]
            else:
                print("Invalid choice. Please try again.")
                return
        except ValueError:
            print("Invalid input. Please enter a number.")
            return
        
        # Evaluate each run
        for run_id in run_ids:
            evaluate_run(run_id, self.qrels, self.db)
        
        # Generate comparison
        comparison = compare_runs(run_ids, run_names, self.db)
        
        # Print comparison table
        print_comparison_table(comparison)
        
        print(f"\nComparison saved to database with ID: {comparison.get('id')}")
        
    def _compare_query_variations(self, query_variation_runs):
        """Compare results from query variation runs."""
        if not query_variation_runs:
            print("\nNo query variation runs found.")
            return
            
        # Display available variation runs
        print("\n" + "="*80)
        print("Available Query Variation Runs")
        print("="*80)
        
        for i, run in enumerate(query_variation_runs, 1):
            run_id = run.get('id', 'N/A')
            name = run.get('name', 'Unknown')
            timestamp = run.get('timestamp', 'Unknown')
            description = run.get('description', 'No description')
            print(f"{i}. {name} (ID: {run_id})")
            print(f"   Description: {description}")
            print(f"   Time: {timestamp}")
            print()
            
        print(f"{len(query_variation_runs) + 1}. Return to main menu")
        
        # Get user choice
        try:
            run_choice = int(input(f"\nSelect run to analyze (1-{len(query_variation_runs) + 1}): "))
            if run_choice == len(query_variation_runs) + 1:
                return
                
            if 1 <= run_choice <= len(query_variation_runs):
                selected_run = query_variation_runs[run_choice - 1]
                run_id = selected_run['id']
            else:
                print("Invalid choice. Please try again.")
                return
        except ValueError:
            print("Invalid input. Please enter a number.")
            return
        
        # Evaluate the run
        evaluate_run(run_id, self.qrels, self.db)
        
        # Get query results to analyze variations
        query_results = self.db.get_run_results(run_id)
        
        # Group results by original query
        variations_by_original = {}
        
        for query_data in query_results:
            # Check if this is a variation query
            original_query = None
            query_name = query_data.get("name", "")
            
            # If name ends with " - Variation", extract the original name
            if " - Variation" in query_name:
                original_name = query_name.replace(" - Variation", "")
                
                # Find original query in golden queries
                for category in self.golden_queries:
                    if category != "settings" and isinstance(self.golden_queries[category], dict):
                        if original_name in self.golden_queries[category]:
                            original_query = self.golden_queries[category][original_name].get("query", "")
                            break
            
            if original_query:
                # This is a variation query
                variation_query = query_data.get("query", "")
                
                if original_query not in variations_by_original:
                    variations_by_original[original_query] = {
                        "original": {
                            "query": original_query,
                            "metrics": None
                        },
                        "variation": {
                            "query": variation_query,
                            "metrics": None
                        }
                    }
        
        # Process metrics for all variations
        metrics_data = self.db.get_run_metrics(run_id)
        if "by_query" in metrics_data:
            query_metrics = metrics_data["by_query"]
            
            # Assign metrics to variations
            for query_text, metrics in query_metrics.items():
                # Find if this is an original or variation query
                for original_query, data in variations_by_original.items():
                    if query_text == original_query:
                        data["original"]["metrics"] = metrics
                    elif query_text == data["variation"]["query"]:
                        data["variation"]["metrics"] = metrics
        
        # Display comparison of original vs variation
        print("\n" + "="*80)
        print("Query Variation Analysis")
        print("="*80)
        
        # Check if we found any valid pairs
        if not variations_by_original:
            print("\nNo valid query variation pairs found in this run.")
            return
        
        # Create a simple results table
        print("\nMetrics comparison: Original Queries vs Variations")
        print("-"*80)
        
        # Header
        header = "Query Type".ljust(15)
        header += "p@5".ljust(10)
        header += "p@10".ljust(10)
        header += "MRR".ljust(10)
        header += "bpref".ljust(10)
        print(header)
        print("-"*80)
        
        # Summary metrics
        original_metrics = {"p@5": 0, "p@10": 0, "mrr": 0, "bpref": 0, "count": 0}
        variation_metrics = {"p@5": 0, "p@10": 0, "mrr": 0, "bpref": 0, "count": 0}
        
        # Process each variation pair
        for original_query, data in variations_by_original.items():
            # Skip if missing metrics
            if not data["original"]["metrics"] or not data["variation"]["metrics"]:
                continue
                
            # Display individual query comparison
            print(f"\nOriginal: {original_query}")
            print(f"Variation: {data['variation']['query']}")
            print("-"*80)
            
            # Original metrics
            orig_metrics = data["original"]["metrics"]
            row = "Original".ljust(15)
            row += f"{orig_metrics.get('p@5', 0):.4f}".ljust(10)
            row += f"{orig_metrics.get('p@10', 0):.4f}".ljust(10)
            row += f"{orig_metrics.get('mrr', 0):.4f}".ljust(10)
            row += f"{orig_metrics.get('bpref', 0):.4f}".ljust(10)
            print(row)
            
            # Update summary metrics
            original_metrics["p@5"] += orig_metrics.get("p@5", 0)
            original_metrics["p@10"] += orig_metrics.get("p@10", 0)
            original_metrics["mrr"] += orig_metrics.get("mrr", 0)
            original_metrics["bpref"] += orig_metrics.get("bpref", 0)
            original_metrics["count"] += 1
            
            # Variation metrics
            var_metrics = data["variation"]["metrics"]
            row = "Variation".ljust(15)
            row += f"{var_metrics.get('p@5', 0):.4f}".ljust(10)
            row += f"{var_metrics.get('p@10', 0):.4f}".ljust(10)
            row += f"{var_metrics.get('mrr', 0):.4f}".ljust(10)
            row += f"{var_metrics.get('bpref', 0):.4f}".ljust(10)
            print(row)
            
            # Update summary metrics
            variation_metrics["p@5"] += var_metrics.get("p@5", 0)
            variation_metrics["p@10"] += var_metrics.get("p@10", 0)
            variation_metrics["mrr"] += var_metrics.get("mrr", 0)
            variation_metrics["bpref"] += var_metrics.get("bpref", 0)
            variation_metrics["count"] += 1
            
            # Calculate and show differences
            diff_p5 = var_metrics.get("p@5", 0) - orig_metrics.get("p@5", 0)
            diff_p10 = var_metrics.get("p@10", 0) - orig_metrics.get("p@10", 0)
            diff_mrr = var_metrics.get("mrr", 0) - orig_metrics.get("mrr", 0)
            diff_bpref = var_metrics.get("bpref", 0) - orig_metrics.get("bpref", 0)
            
            row = "Difference".ljust(15)
            row += f"{diff_p5:.4f}{' (+)' if diff_p5 > 0 else ''}".ljust(10)
            row += f"{diff_p10:.4f}{' (+)' if diff_p10 > 0 else ''}".ljust(10)
            row += f"{diff_mrr:.4f}{' (+)' if diff_mrr > 0 else ''}".ljust(10)
            row += f"{diff_bpref:.4f}{' (+)' if diff_bpref > 0 else ''}".ljust(10)
            print(row)
        
        # Display summary metrics
        if original_metrics["count"] > 0 and variation_metrics["count"] > 0:
            # Calculate averages
            orig_avg_p5 = original_metrics["p@5"] / original_metrics["count"]
            orig_avg_p10 = original_metrics["p@10"] / original_metrics["count"]
            orig_avg_mrr = original_metrics["mrr"] / original_metrics["count"]
            orig_avg_bpref = original_metrics["bpref"] / original_metrics["count"]
            
            var_avg_p5 = variation_metrics["p@5"] / variation_metrics["count"]
            var_avg_p10 = variation_metrics["p@10"] / variation_metrics["count"]
            var_avg_mrr = variation_metrics["mrr"] / variation_metrics["count"]
            var_avg_bpref = variation_metrics["bpref"] / variation_metrics["count"]
            
            # Display summary table
            print("\n" + "="*80)
            print(f"SUMMARY METRICS (Averaged across {original_metrics['count']} query pairs)")
            print("="*80)
            
            # Header
            header = "Query Type".ljust(15)
            header += "p@5".ljust(10)
            header += "p@10".ljust(10)
            header += "MRR".ljust(10)
            header += "bpref".ljust(10)
            print(header)
            print("-"*80)
            
            # Original metrics
            row = "Original".ljust(15)
            row += f"{orig_avg_p5:.4f}".ljust(10)
            row += f"{orig_avg_p10:.4f}".ljust(10)
            row += f"{orig_avg_mrr:.4f}".ljust(10)
            row += f"{orig_avg_bpref:.4f}".ljust(10)
            print(row)
            
            # Variation metrics
            row = "Variation".ljust(15)
            row += f"{var_avg_p5:.4f}".ljust(10)
            row += f"{var_avg_p10:.4f}".ljust(10)
            row += f"{var_avg_mrr:.4f}".ljust(10)
            row += f"{var_avg_bpref:.4f}".ljust(10)
            print(row)
            
            # Calculate and show differences
            diff_p5 = var_avg_p5 - orig_avg_p5
            diff_p10 = var_avg_p10 - orig_avg_p10
            diff_mrr = var_avg_mrr - orig_avg_mrr
            diff_bpref = var_avg_bpref - orig_avg_bpref
            
            row = "Difference".ljust(15)
            row += f"{diff_p5:.4f}{' (+)' if diff_p5 > 0 else ''}".ljust(10)
            row += f"{diff_p10:.4f}{' (+)' if diff_p10 > 0 else ''}".ljust(10)
            row += f"{diff_mrr:.4f}{' (+)' if diff_mrr > 0 else ''}".ljust(10)
            row += f"{diff_bpref:.4f}{' (+)' if diff_bpref > 0 else ''}".ljust(10)
            print(row)
            
            # Winner
            print("\nWINNER: ", end="")
            metrics_diff_sum = diff_p5 + diff_p10 + diff_mrr + diff_bpref
            if metrics_diff_sum > 0:
                print("VARIATIONS (Vector-optimized keyword queries)")
            elif metrics_diff_sum < 0:
                print("ORIGINALS (Natural language queries)")
            else:
                print("TIE")
    
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
        """Display current parameter values from settings.json and golden_queries.json in a copy-paste friendly format."""
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
        
        input("\nPress Enter to continue...")
        
    def delete_runs(self):
        """Delete runs from the database."""
        # Get runs from database
        runs = self.db.get_runs(limit=20)  # Show up to 20 most recent runs
        
        if not runs:
            print("No runs found in database")
            return
        
        # Display available runs
        print("\n" + "="*80)
        print("Delete Runs")
        print("="*80)
        
        print("\nAvailable runs:")
        print(f"{'ID':<5} {'Name':<30} {'Type':<15} {'Timestamp':<25}")
        print("-"*80)
        
        for run in runs:
            run_id = run.get('id', 'N/A')
            run_name = run.get('name', 'Unknown')[:28]
            config_type = run.get('config_type', 'Unknown')[:13]
            timestamp = run.get('timestamp', 'Unknown')[:23]
            
            print(f"{run_id:<5} {run_name:<30} {config_type:<15} {timestamp:<25}")
        
        print("\nOptions:")
        print("  - Enter specific run ID(s) to delete (comma-separated)")
        print("  - Enter 'A' to delete all runs")
        print("  - Enter 'C' to cancel")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice.upper() == 'C':
            print("Deletion cancelled")
            return
            
        if choice.upper() == 'A':
            # Confirm deletion of all runs
            confirm = input("Are you sure you want to delete ALL runs? This cannot be undone. (y/n): ")
            if confirm.lower() != 'y':
                print("Deletion cancelled")
                return
                
            # Delete all runs
            deleted = self._delete_all_runs()
            if deleted:
                print("All runs deleted successfully")
            else:
                print("Failed to delete runs")
            return
            
        # Process specific run IDs
        try:
            run_ids = [int(id.strip()) for id in choice.split(',')]
            if not run_ids:
                print("No valid run IDs provided")
                return
                
            # Confirm deletion
            id_list = ', '.join(str(id) for id in run_ids)
            confirm = input(f"Are you sure you want to delete run(s) {id_list}? This cannot be undone. (y/n): ")
            if confirm.lower() != 'y':
                print("Deletion cancelled")
                return
                
            # Delete specific runs
            deleted = self._delete_specific_runs(run_ids)
            if deleted:
                print(f"Run(s) {id_list} deleted successfully")
            else:
                print("Failed to delete runs")
                
        except ValueError:
            print("Invalid input. Please enter comma-separated run IDs or 'A' for all runs")
    
    def _delete_all_runs(self):
        """Delete all runs from the database."""
        try:
            conn = self.db.conn
            cursor = conn.cursor()
            
            # Start a transaction
            conn.execute("BEGIN TRANSACTION")
            
            # Delete records from all related tables
            cursor.execute("DELETE FROM comparisons")
            cursor.execute("DELETE FROM metrics")
            cursor.execute("DELETE FROM results")
            cursor.execute("DELETE FROM runs")
            
            # Commit the transaction
            conn.commit()
            
            # Update latest run IDs
            self.latest_run_ids = {k: None for k in self.latest_run_ids.keys()}
            
            return True
        except sqlite3.Error as e:
            print(f"Error deleting runs: {e}")
            conn.rollback()
            return False
    
    def _compare_query_pairs(self, run_id, query_pairs):
        """
        Compare metrics between original queries and their variations
        using pre-defined query ID pairs.
        
        Args:
            run_id: ID of the run to analyze
            query_pairs: Dictionary mapping original query IDs to variation query IDs
        """
        # Get metrics for the run
        metrics_data = self.db.get_run_metrics(run_id)
        if not metrics_data or "by_query" not in metrics_data:
            print("\nNo metrics found for this run.")
            return
            
        # Get all query data from database
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT id, text, category, name FROM queries ORDER BY id")
        queries = {row['id']: row for row in cursor.fetchall()}
        
        # Set up metrics containers
        original_metrics = {"p@5": 0, "p@10": 0, "mrr": 0, "bpref": 0, "count": 0}
        variation_metrics = {"p@5": 0, "p@10": 0, "mrr": 0, "bpref": 0, "count": 0}
        comparison_data = []
        
        # Create a lookup table for query text to metrics
        query_text_to_metrics = {}
        for query_text, metrics in metrics_data.get("by_query", {}).items():
            query_text_to_metrics[query_text] = metrics
        
        # Process each query pair
        pairs_with_metrics = []
        
        for orig_id, var_id in query_pairs.items():
            # Skip if either query doesn't exist
            if orig_id not in queries or var_id not in queries:
                logger.warning(f"Missing query in pair {orig_id}/{var_id}")
                continue
                
            orig_query = queries[orig_id]
            var_query = queries[var_id]
            
            # Get metrics for both queries
            orig_text = orig_query.get('text', '')
            var_text = var_query.get('text', '')
            
            orig_metrics = query_text_to_metrics.get(orig_text, None)
            var_metrics = query_text_to_metrics.get(var_text, None)
            
            # Skip if either lacks metrics
            if not orig_metrics or not var_metrics:
                logger.warning(f"Missing metrics for query pair {orig_id}/{var_id}")
                continue
                
            # Store pair data
            pair_data = {
                'original_id': orig_id,
                'variation_id': var_id,
                'original_text': orig_text,
                'variation_text': var_text,
                'original_metrics': orig_metrics,
                'variation_metrics': var_metrics,
                'change': {
                    key: var_metrics.get(key, 0.0) - orig_metrics.get(key, 0.0) 
                    for key in ['p@5', 'p@10', 'mrr', 'bpref']
                }
            }
            
            pairs_with_metrics.append(pair_data)
            
            # Update aggregated metrics
            for key in ['p@5', 'p@10', 'mrr', 'bpref']:
                original_metrics[key] += orig_metrics.get(key, 0.0)
                variation_metrics[key] += var_metrics.get(key, 0.0)
            
            original_metrics["count"] += 1
            variation_metrics["count"] += 1
        
        # Calculate averages
        if original_metrics["count"] > 0:
            for key in ['p@5', 'p@10', 'mrr', 'bpref']:
                original_metrics[key] /= original_metrics["count"]
                variation_metrics[key] /= variation_metrics["count"]
        
        # Display comparison
        print("\n" + "="*80)
        print("Query Variation Analysis - Predefined Pairs")
        print("="*80)
        
        # Check if we found any valid pairs
        if not pairs_with_metrics:
            print("\nNo valid query pairs found with metrics.")
            return
        
        # Display summary table first
        print("\nMetrics comparison: Original Queries vs Variations")
        print("-"*80)
        
        # Header
        header = "Query Type".ljust(15)
        header += "p@5".ljust(10)
        header += "p@10".ljust(10)
        header += "MRR".ljust(10)
        header += "bpref".ljust(10)
        print(header)
        print("-"*80)
        
        # Original aggregated metrics
        row = "Original".ljust(15)
        row += f"{original_metrics['p@5']:.4f}".ljust(10)
        row += f"{original_metrics['p@10']:.4f}".ljust(10)
        row += f"{original_metrics['mrr']:.4f}".ljust(10)
        row += f"{original_metrics['bpref']:.4f}".ljust(10)
        print(row)
        
        # Variation aggregated metrics
        row = "Variation".ljust(15)
        row += f"{variation_metrics['p@5']:.4f}".ljust(10)
        row += f"{variation_metrics['p@10']:.4f}".ljust(10)
        row += f"{variation_metrics['mrr']:.4f}".ljust(10)
        row += f"{variation_metrics['bpref']:.4f}".ljust(10)
        print(row)
        
        # Calculate and show differences
        diff_p5 = variation_metrics['p@5'] - original_metrics['p@5']
        diff_p10 = variation_metrics['p@10'] - original_metrics['p@10']
        diff_mrr = variation_metrics['mrr'] - original_metrics['mrr']
        diff_bpref = variation_metrics['bpref'] - original_metrics['bpref']
        
        row = "Difference".ljust(15)
        row += f"{diff_p5:+.4f}".ljust(10)
        row += f"{diff_p10:+.4f}".ljust(10)
        row += f"{diff_mrr:+.4f}".ljust(10)
        row += f"{diff_bpref:+.4f}".ljust(10)
        print(row)
        
        # Display individual pair comparisons
        print("\nComparison by Query Pair:")
        print("-"*100)
        print("Orig ID  Var ID   p@5 Δ      p@10 Δ     MRR Δ      bpref Δ    ")
        print("-"*100)
        
        for pair in pairs_with_metrics:
            orig_id = pair['original_id']
            var_id = pair['variation_id']
            changes = pair['change']
            
            fmt_pair = f"{orig_id:<8} {var_id:<8}"
            
            for metric in ['p@5', 'p@10', 'mrr', 'bpref']:
                change = changes[metric]
                if change > 0:
                    fmt_pair += f"+{change:.4f}    "  # Positive change
                else:
                    fmt_pair += f"{change:.4f}    "   # Negative or no change
            
            print(fmt_pair)
        
        print("-"*100)
        
        # Winner
        print("\nWINNER: ", end="")
        metrics_diff_sum = diff_p5 + diff_p10 + diff_mrr + diff_bpref
        if metrics_diff_sum > 0:
            print("VARIATIONS (Vector-optimized keyword queries)")
        elif metrics_diff_sum < 0:
            print("ORIGINALS (Natural language queries)")
        else:
            print("TIE")
    
    def _delete_specific_runs(self, run_ids):
        """Delete specific runs from the database."""
        try:
            conn = self.db.conn
            cursor = conn.cursor()
            
            # Start a transaction
            conn.execute("BEGIN TRANSACTION")
            
            # Format IDs for SQL
            ids_str = ','.join('?' for _ in run_ids)
            
            # Delete from comparisons
            cursor.execute(f"DELETE FROM comparisons WHERE best_run_id IN ({ids_str})", run_ids)
            
            # Delete from metrics
            cursor.execute(f"DELETE FROM metrics WHERE run_id IN ({ids_str})", run_ids)
            
            # Delete from results
            cursor.execute(f"DELETE FROM results WHERE run_id IN ({ids_str})", run_ids)
            
            # Delete from runs
            cursor.execute(f"DELETE FROM runs WHERE id IN ({ids_str})", run_ids)
            
            # Commit the transaction
            conn.commit()
            
            # Update latest run IDs if any were deleted
            for config_type, run_id in self.latest_run_ids.items():
                if run_id in run_ids:
                    self.latest_run_ids[config_type] = None
            
            return True
        except sqlite3.Error as e:
            print(f"Error deleting runs: {e}")
            conn.rollback()
            return False

def main():
    """Main entry point."""
    cli = IREvalCLI()
    cli.show_main_menu()

if __name__ == "__main__":
    main()