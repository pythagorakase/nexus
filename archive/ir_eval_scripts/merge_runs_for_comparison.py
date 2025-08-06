#!/usr/bin/env python3
"""
Merge metrics from two runs to enable direct comparison of query pairs.

This script combines metrics from two runs into a virtual consolidated run,
which allows direct comparison of query pairs (e.g., 1 vs 10) when they
exist in separate runs. This is useful when original queries (1-9) and
their variations (10-19) were run separately.

Usage:
    python merge_runs_for_comparison.py --run1-id RUN1_ID --run2-id RUN2_ID
"""

import os
import sys
import argparse
import logging
import json
from typing import Dict, List, Any, Tuple, Set
import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import IRDatabase
from scripts.comparison import (
    get_related_queries,
    compare_query_variations,
    print_query_variations_table
)

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("merge_runs")

def merge_run_metrics(
    db: IRDatabase, 
    run1_id: int, 
    run2_id: int, 
    relationship_type: str = "variation"
) -> Dict[str, Any]:
    """
    Merge metrics from two runs into a consolidated view for comparison.
    
    Args:
        db: IRDatabase instance
        run1_id: ID of first run
        run2_id: ID of second run
        relationship_type: Type of relationship to use
        
    Returns:
        Dictionary with consolidated run metrics for comparison
    """
    # Get query relationships
    relationships = get_related_queries(db, relationship_type)
    
    # Track which run each query ID belongs to
    run1_query_ids = []
    run2_query_ids = []
    
    # Get query IDs that have metrics in each run
    cursor = db.conn.cursor()
    cursor.execute("SELECT DISTINCT query_id FROM metrics WHERE run_id = ?", (run1_id,))
    run1_query_ids = [row['query_id'] for row in cursor.fetchall()]
    
    cursor.execute("SELECT DISTINCT query_id FROM metrics WHERE run_id = ?", (run2_id,))
    run2_query_ids = [row['query_id'] for row in cursor.fetchall()]
    
    # Combine into a single consolidated view
    consolidated_metrics = {
        "by_query": {},
        "aggregated": None,
        "query_categories": {}
    }
    
    # Get query texts and categories
    cursor.execute("SELECT id, text, category FROM queries")
    query_info = {row['id']: {"text": row['text'], "category": row['category']} for row in cursor.fetchall()}
    
    # Process query pairs and add them to the consolidated view
    valid_pairs = []
    by_query = {}
    query_categories = {}
    
    # Extract metrics for each query ID across both runs
    for query_id in set(run1_query_ids + run2_query_ids):
        # Determine which run to get metrics from
        run_id = run1_id if query_id in run1_query_ids else run2_id
        
        # Get metrics for this query
        cursor.execute('''
        SELECT p_at_5, p_at_10, mrr, bpref, 
               judged_p_at_5, judged_p_at_10, judged_total, unjudged_count
        FROM metrics
        WHERE run_id = ? AND query_id = ?
        ''', (run_id, query_id))
        
        row = cursor.fetchone()
        if row and query_id in query_info:
            query_text = query_info[query_id]["text"]
            category = query_info[query_id]["category"] or "unknown"
            
            metrics = {
                "p@5": float(row['p_at_5']) if row['p_at_5'] is not None else 0.0,
                "p@10": float(row['p_at_10']) if row['p_at_10'] is not None else 0.0,
                "mrr": float(row['mrr']) if row['mrr'] is not None else 0.0,
                "bpref": float(row['bpref']) if row['bpref'] is not None else 0.0,
                "judged_counts": {
                    "p@5": row['judged_p_at_5'] if row['judged_p_at_5'] is not None else 0,
                    "p@10": row['judged_p_at_10'] if row['judged_p_at_10'] is not None else 0,
                    "total": row['judged_total'] if row['judged_total'] is not None else 0
                },
                "unjudged_count": row['unjudged_count'] if row['unjudged_count'] is not None else 0
            }
            
            by_query[query_text] = metrics
            query_categories[query_text] = category
    
    # Compile the consolidated metrics
    consolidated_metrics["by_query"] = by_query
    consolidated_metrics["query_categories"] = query_categories
    
    # Find all valid query pairs using relationships
    valid_pairs = []
    
    for orig_id, var_id in relationships.items():
        # Check if we have metrics for both queries
        orig_text = query_info.get(orig_id, {}).get("text", "")
        var_text = query_info.get(var_id, {}).get("text", "")
        
        if orig_text in by_query and var_text in by_query:
            valid_pairs.append({
                "original_id": orig_id,
                "variation_id": var_id,
                "original_text": orig_text,
                "variation_text": var_text
            })
    
    return {
        "run1_id": run1_id,
        "run2_id": run2_id,
        "metrics": consolidated_metrics,
        "valid_pairs": valid_pairs,
        "timestamp": datetime.datetime.now().isoformat()
    }

def run_merged_comparison(
    db: IRDatabase,
    run1_id: int,
    run2_id: int,
    relationship_type: str = "variation"
) -> Dict[str, Any]:
    """
    Run a comparison using metrics from two merged runs.
    
    Args:
        db: IRDatabase instance
        run1_id: ID of first run
        run2_id: ID of second run
        relationship_type: Type of relationship to use
        
    Returns:
        Dictionary with comparison results
    """
    # Merge metrics from both runs
    merged_data = merge_run_metrics(db, run1_id, run2_id, relationship_type)
    
    # Extract needed data for comparison
    metrics_data = merged_data["metrics"]
    query_metrics = metrics_data["by_query"]
    
    # Get query relationships
    relationships = get_related_queries(db, relationship_type)
    
    # Get text for all queries
    cursor = db.conn.cursor()
    cursor.execute("SELECT id, text FROM queries")
    query_texts = {row['id']: row['text'] for row in cursor.fetchall()}
    
    # Group queries by original/variation pairs
    variations_by_original = {}
    
    for orig_id, var_id in relationships.items():
        # Get query texts
        if orig_id not in query_texts or var_id not in query_texts:
            logger.warning(f"Missing query text for pair {orig_id}/{var_id}")
            continue
            
        original_query = query_texts[orig_id]
        variation_query = query_texts[var_id]
        
        # Check if metrics are available
        if original_query not in query_metrics or variation_query not in query_metrics:
            logger.warning(f"Missing metrics for pair {orig_id}/{var_id}")
            continue
        
        # Add to variations dictionary
        variations_by_original[original_query] = {
            "original": {
                "id": orig_id,
                "query": original_query,
                "metrics": query_metrics.get(original_query)
            },
            "variation": {
                "id": var_id,
                "query": variation_query,
                "metrics": query_metrics.get(variation_query)
            }
        }
    
    if not variations_by_original:
        raise RuntimeError("No valid query pairs found with metrics")
    
    # Calculate summary metrics
    original_metrics = {"p@5": 0, "p@10": 0, "mrr": 0, "bpref": 0, "count": 0}
    variation_metrics = {"p@5": 0, "p@10": 0, "mrr": 0, "bpref": 0, "count": 0}
    
    # Process each variation pair
    valid_pairs = []
    
    for original_query, data in variations_by_original.items():
        # Skip if missing metrics
        if not data["original"]["metrics"] or not data["variation"]["metrics"]:
            continue
        
        valid_pairs.append({
            "original_query": original_query,
            "variation_query": data["variation"]["query"],
            "original_metrics": data["original"]["metrics"],
            "variation_metrics": data["variation"]["metrics"],
            "changes": {
                key: data["variation"]["metrics"].get(key, 0) - data["original"]["metrics"].get(key, 0)
                for key in ["p@5", "p@10", "mrr", "bpref"]
            }
        })
        
        # Update summary metrics
        for key in ["p@5", "p@10", "mrr", "bpref"]:
            original_metrics[key] += data["original"]["metrics"].get(key, 0)
            variation_metrics[key] += data["variation"]["metrics"].get(key, 0)
        
        original_metrics["count"] += 1
        variation_metrics["count"] += 1
    
    # Calculate averages
    if original_metrics["count"] > 0:
        for key in ["p@5", "p@10", "mrr", "bpref"]:
            original_metrics[key] /= original_metrics["count"]
            variation_metrics[key] /= variation_metrics["count"]
    
    # Prepare results
    results = {
        "run1_id": run1_id,
        "run2_id": run2_id,
        "original_metrics": original_metrics,
        "variation_metrics": variation_metrics,
        "pairs": valid_pairs,
        "changes": {
            key: variation_metrics[key] - original_metrics[key]
            for key in ["p@5", "p@10", "mrr", "bpref"]
        }
    }
    
    return results

def main():
    parser = argparse.ArgumentParser(description="Merge and compare metrics from two runs")
    parser.add_argument("--run1-id", type=int, required=True, help="ID of first run")
    parser.add_argument("--run2-id", type=int, required=True, help="ID of second run")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database")
    parser.add_argument("--relationship-type", default="variation", help="Type of relationship to use")
    parser.add_argument("--detailed", action="store_true", help="Show detailed analysis of each pair")
    parser.add_argument("--threshold", type=float, default=1.0, 
                      help="Relevance threshold (0-3) for considering a document relevant")
    parser.add_argument("--min-diff", type=float, default=0.05,
                      help="Minimum difference in metrics to highlight")
    parser.add_argument("--output", default=None, help="Path to write JSON output")
    
    args = parser.parse_args()
    
    # Use default database path if not specified
    db_path = args.db_path
    if not db_path:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ir_eval.db")
    
    # Initialize database connection
    db = IRDatabase(db_path)
    
    try:
        # Run comparison
        print(f"Merging and comparing metrics from runs {args.run1_id} and {args.run2_id}...")
        results = run_merged_comparison(db, args.run1_id, args.run2_id, args.relationship_type)
        
        # Print results
        print_query_variations_table(results)
        
        # Run detailed analysis if requested
        if args.detailed:
            print("\n" + "="*80)
            print("DETAILED ANALYSIS OF QUERY PAIRS")
            print("="*80)
            
            # Import analyze_metrics_differences functionality
            from analyze_metrics_differences import (
                get_query_result_details,
                analyze_result_list_differences
            )
            
            # Get query relationships
            relationships = get_related_queries(db, args.relationship_type)
            
            for orig_id, var_id in relationships.items():
                # Get results from run 1 (typically has variation queries)
                var_data = get_query_result_details(db, args.run1_id, var_id)
                
                # If data is missing from run 1, try run 2
                if not var_data or not var_data.get("results"):
                    var_data = get_query_result_details(db, args.run2_id, var_id)
                
                # Get results from run 2 (typically has original queries)
                orig_data = get_query_result_details(db, args.run2_id, orig_id)
                
                # If data is missing from run 2, try run 1
                if not orig_data or not orig_data.get("results"):
                    orig_data = get_query_result_details(db, args.run1_id, orig_id)
                
                # Only analyze if both queries have data
                if (not orig_data or not orig_data.get("metrics") or not orig_data.get("results") or
                    not var_data or not var_data.get("metrics") or not var_data.get("results")):
                    logger.warning(f"Missing data for detailed analysis of query pair {orig_id}/{var_id}")
                    continue
                
                # Analyze differences
                analysis = analyze_result_list_differences(
                    orig_data, 
                    var_data,
                    threshold=args.threshold,
                    min_diff=args.min_diff
                )
                
                if analysis:
                    print(f"\nDetailed analysis for query pair {orig_id}/{var_id}:")
                    print(f"Original: {analysis['original_query']}")
                    print(f"Variation: {analysis['variation_query']}")
                    
                    print("\n" + analysis["explanation"])
                    print(f"Overall impact: {analysis['summary']['overall_impact'].upper()}")
                    print("-" * 80)
        
        # Write JSON output if requested
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\nResults written to {args.output}")
            
    except RuntimeError as e:
        print(f"Error: {e}")
        print("\nMake sure you've run the add_query_relationships.py script first to create the relationships table.")
        return 1
    finally:
        # Close database connection
        db.close()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())