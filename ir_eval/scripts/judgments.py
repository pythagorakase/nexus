#!/usr/bin/env python3
"""
IR Evaluation Judgment Module - Interactive tools for NEXUS IR Evaluation System

This module provides tools for judging search results from the NEXUS system.
It can either work with results directly from the database or from JSON files.

Main functions:
- judge_all_unjudged_results: Judge results from database runs
- judge_results_interactive: Judge results from a JSON file

Usage:
    As a module: Import and use the functions directly
    As a script: python judgments.py [args]
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, List, Set, Any, Optional, Tuple

# Make sure we can import from the parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import local modules
try:
    from ir_eval.scripts.qrels import QRELSManager
    from ir_eval.db import IRDatabase, DEFAULT_DB_PATH
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    from qrels import QRELSManager
    from db import IRDatabase, DEFAULT_DB_PATH

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.judge")

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

def load_results(filename: str) -> Dict[str, Any]:
    """
    Load search results from a file.
    
    Args:
        filename: Path to the results JSON file
        
    Returns:
        Dictionary containing the results data
    """
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading results from {filename}: {e}")
        return {}
        
def load_golden_queries(filename: str) -> Dict[str, Any]:
    """
    Load golden queries definition file.
    
    Args:
        filename: Path to the golden queries JSON file
        
    Returns:
        Dictionary containing the golden queries data
    """
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading golden queries from {filename}: {e}")
        return {}

def get_guidelines(golden_queries: Dict[str, Any], query_name: str, 
                 query_category: str) -> Tuple[List[str], List[str]]:
    """
    Extract positive and negative guidelines for a query.
    
    Args:
        golden_queries: Golden queries data
        query_name: Name of the query
        query_category: Category of the query
        
    Returns:
        Tuple of (positive guidelines, negative guidelines)
    """
    positives = []
    negatives = []
    
    # Look for category and query name in golden queries
    if query_category in golden_queries and query_name in golden_queries[query_category]:
        query_info = golden_queries[query_category][query_name]
        positives = query_info.get("positives", [])
        negatives = query_info.get("negatives", [])
    
    return positives, negatives
    
def get_query_info(golden_queries: Dict[str, Any], query_text: str) -> Tuple[str, str]:
    """
    Find category and name for a query based on its text.
    
    Args:
        golden_queries: Golden queries data
        query_text: The text of the query to look up
        
    Returns:
        Tuple of (query_name, query_category)
    """
    for category, queries in golden_queries.items():
        if category == "settings":
            continue
            
        for name, data in queries.items():
            if isinstance(data, dict) and data.get("query") == query_text:
                return name, category
                
    return "unknown", "unknown"

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

def judge_results_interactive(
    results_file: str,
    qrels_file: str = "qrels.json",
    golden_queries_file: str = "golden_queries.json",
    skip_judged: bool = True
) -> None:
    """
    Interactively judge search results from a JSON file.
    
    Args:
        results_file: Path to the results JSON file
        qrels_file: Path to the QRELS JSON file
        golden_queries_file: Path to the golden queries JSON file
        skip_judged: Whether to skip already judged documents
    """
    # Load QRELS
    qrels = QRELSManager(qrels_file)
    
    # Load results
    results_data = load_results(results_file)
    if not results_data:
        logger.error(f"No valid results found in {results_file}")
        return
        
    # Load golden queries for guidelines
    golden_queries = load_golden_queries(golden_queries_file)
    if not golden_queries:
        logger.warning(f"No golden queries found in {golden_queries_file}, continuing without guidelines")
    
    # Extract query results
    query_results = results_data.get("query_results", [])
    if not query_results:
        logger.error(f"No query results found in {results_file}")
        return
        
    logger.info(f"Loaded {len(query_results)} queries from {results_file}")
    
    # Track judgments added in this session
    judgments_added = 0
    
    # Process each query
    for query_data in query_results:
        query_text = query_data.get("query", "")
        category = query_data.get("category", "unknown")
        name = query_data.get("name", "unknown")
        
        # Find guidelines for this query
        positives, negatives = get_guidelines(golden_queries, name, category)
        
        # Get results for this query
        results = query_data.get("results", [])
        if not results:
            logger.info(f"No results for query: {query_text}")
            continue
            
        # Get already judged documents for this query
        judged_docs = qrels.get_judged_documents(query_text)
        
        # Count how many documents need judging
        unjudged_count = sum(1 for r in results if str(r.get("id")) not in judged_docs)
        
        print("\n" + "="*80)
        print(f"QUERY: {query_text}")
        print(f"CATEGORY: {category} / NAME: {name}")
        print(f"Found {len(results)} results, {unjudged_count} need judging")
        
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
        
        # Process each result
        for i, result in enumerate(results, 1):
            doc_id = str(result.get("id", ""))
            text = result.get("text", "")
            score = result.get("score", 0)
            
            # Skip already judged documents if requested
            if skip_judged and doc_id in judged_docs:
                continue
                
            # Display the document
            print("\n" + "-"*80)
            print(f"Document {i}/{len(results)} (ID: {doc_id}, Score: {score:.4f})")
            print("-"*80)
            print(format_result_text(text, truncate=True, max_length=2000))
            print("-"*80)
            
            # Get relevance judgment
            relevance = None
            while relevance not in [0, 1, 2, 3, -1]:
                try:
                    relevance_input = input("Relevance (0-3) or -1 to skip: ")
                    relevance = int(relevance_input)
                except ValueError:
                    print("Please enter a number between 0 and 3, or -1 to skip")
            
            # Skip if requested
            if relevance == -1:
                print("Skipped")
                continue
                
            # Add judgment
            qrels.add_judgment(
                query_text,
                doc_id,
                relevance,
                category,
                text
            )
            judgments_added += 1
            
            # Save after each judgment (in case of interruption)
            if judgments_added % 5 == 0:
                qrels.save()
                print(f"Saved {judgments_added} judgments so far")
    
    # Final save
    qrels.save()
    print("\n" + "="*80)
    print(f"Judging complete! Added {judgments_added} new relevance judgments")
    print(f"Total judgments in file: {qrels.get_judgment_count()}")

def judge_run_from_db(run_id: int, qrels_file: str = None, golden_queries_file: str = None, db_path: str = None):
    """
    Judge results for a specific run stored in the database.
    
    Args:
        run_id: Database ID of the run to judge
        qrels_file: Path to the QRELS file (default: the database's default)
        golden_queries_file: Path to the golden queries file
        db_path: Path to the database file (default: DEFAULT_DB_PATH)
    """
    # Initialize database
    db = IRDatabase(db_path) if db_path else IRDatabase()
    
    # Initialize QRELSManager
    qrels = QRELSManager(qrels_file) if qrels_file else QRELSManager()
    
    # Load golden queries
    golden_queries = {}
    if golden_queries_file:
        golden_queries = load_golden_queries(golden_queries_file)
    
    # Get run metadata
    run_data = db.get_run_metadata(run_id)
    if not run_data:
        logger.error(f"No run found with ID {run_id}")
        return
    
    print(f"Judging run: {run_data.get('name', f'Run {run_id}')} (ID: {run_id})")
    print(f"Description: {run_data.get('description', 'No description')}")
    print(f"Run type: {run_data.get('config_type', 'Unknown type')}")
    
    # Judge results
    judgments_added = judge_all_unjudged_results([run_id], qrels, golden_queries, db)
    
    print(f"\nJudging complete! Added {judgments_added} new relevance judgments")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Judge NEXUS search results from files or database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Judge results from a file:
  python judgments.py --file /path/to/results.json --qrels /path/to/qrels.json
  
  # Judge results from the database for a specific run:
  python judgments.py --run-id 5 --db /path/to/ir_eval.db
  
  # Judge results from multiple runs in the database:
  python judgments.py --run-ids 5,7,9 --db /path/to/ir_eval.db
"""
    )
    
    # Create mutually exclusive group for file vs. database judging
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--file", help="Path to the results JSON file")
    source_group.add_argument("--run-id", type=int, help="Database ID of the run to judge")
    source_group.add_argument("--run-ids", help="Comma-separated list of run IDs to judge")
    
    # Other arguments
    parser.add_argument("--qrels", help="Path to the QRELS JSON file (default: database default)")
    parser.add_argument("--golden-queries", help="Path to the golden queries JSON file")
    parser.add_argument("--db", help="Path to the database file (default: ir_eval.db)")
    parser.add_argument("--skip-judged", action="store_true", help="Skip already judged documents (for file judging)")
    
    args = parser.parse_args()
    
    # Determine judging mode
    if args.file:
        # File-based judging
        judge_results_interactive(
            args.file,
            args.qrels or "qrels.json",
            args.golden_queries or "golden_queries.json",
            args.skip_judged
        )
    elif args.run_id:
        # Single run judging
        judge_run_from_db(
            args.run_id,
            args.qrels,
            args.golden_queries,
            args.db
        )
    elif args.run_ids:
        # Multiple runs judging
        try:
            run_ids = [int(run_id.strip()) for run_id in args.run_ids.split(',')]
            if not run_ids:
                logger.error("No valid run IDs provided")
                return
            
            # Initialize database
            db = IRDatabase(args.db) if args.db else IRDatabase()
            
            # Initialize QRELSManager
            qrels = QRELSManager(args.qrels) if args.qrels else QRELSManager()
            
            # Load golden queries
            golden_queries = {}
            if args.golden_queries:
                golden_queries = load_golden_queries(args.golden_queries)
            
            # Judge results
            judge_all_unjudged_results(run_ids, qrels, golden_queries, db)
            
        except ValueError:
            logger.error("Invalid run IDs format. Please use comma-separated integers.")
    
if __name__ == "__main__":
    main()