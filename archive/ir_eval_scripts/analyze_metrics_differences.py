#!/usr/bin/env python3
"""
Analyze detailed metrics differences between query pairs.

This script conducts a detailed analysis of the performance differences
between related query pairs (e.g., natural language vs. keyword versions).
It helps identify specific patterns in which metrics are improving or degrading.

Usage:
    python analyze_metrics_differences.py --run-id RUN_ID [--threshold THRESHOLD] [--min-diff MIN_DIFF]
"""

import os
import sys
import argparse
import logging
from typing import Dict, List, Any, Tuple, Set
import json
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import IRDatabase
from scripts.comparison import get_related_queries

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("analyze_metrics_differences")

def get_query_result_details(db: IRDatabase, run_id: int, query_id: int) -> Dict[str, Any]:
    """
    Get detailed results and metrics for a specific query.
    
    Args:
        db: IRDatabase instance
        run_id: Run ID
        query_id: Query ID
        
    Returns:
        Dictionary with query details, results, and metrics
    """
    cursor = db.conn.cursor()
    
    # Get query text
    cursor.execute("SELECT text FROM queries WHERE id = ?", (query_id,))
    query_row = cursor.fetchone()
    if not query_row:
        logger.warning(f"Query with ID {query_id} not found")
        return {}
    
    query_text = query_row['text']
    
    # Get results for this query
    cursor.execute('''
    SELECT doc_id, rank, score, vector_score, text_score, text, source
    FROM results
    WHERE run_id = ? AND query_id = ?
    ORDER BY rank
    ''', (run_id, query_id))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            "id": row['doc_id'],
            "rank": row['rank'],
            "score": float(row['score']) if row['score'] is not None else 0.0,
            "vector_score": float(row['vector_score']) if row['vector_score'] is not None else 0.0,
            "text_score": float(row['text_score']) if row['text_score'] is not None else 0.0,
            "text": row['text'],
            "source": row['source']
        })
    
    # Get metrics for this query
    cursor.execute('''
    SELECT p_at_5, p_at_10, mrr, bpref, 
           judged_p_at_5, judged_p_at_10, judged_total, unjudged_count
    FROM metrics
    WHERE run_id = ? AND query_id = ?
    ''', (run_id, query_id))
    
    row = cursor.fetchone()
    metrics = {}
    if row:
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
    
    # Get judgments for this query
    cursor.execute('''
    SELECT doc_id, relevance
    FROM judgments
    WHERE query_id = ?
    ''', (query_id,))
    
    judgments = {}
    for row in cursor.fetchall():
        judgments[row['doc_id']] = row['relevance']
    
    return {
        "id": query_id,
        "text": query_text,
        "results": results,
        "metrics": metrics,
        "judgments": judgments
    }

def analyze_result_list_differences(
    original_data: Dict[str, Any], 
    variation_data: Dict[str, Any], 
    threshold: float = 0.0,
    min_diff: float = 0.0
) -> Dict[str, Any]:
    """
    Analyze differences between original and variation result lists.
    
    Args:
        original_data: Original query data with results and metrics
        variation_data: Variation query data with results and metrics
        threshold: Relevance threshold (0-3) for considering a document relevant
        min_diff: Minimum difference in metrics to highlight
        
    Returns:
        Dictionary with analysis results
    """
    if not original_data or not variation_data:
        return {}
    
    # Extract metrics
    orig_metrics = original_data.get("metrics", {})
    var_metrics = variation_data.get("metrics", {})
    
    # Calculate metrics differences
    metric_diffs = {}
    for metric in ["p@5", "p@10", "mrr", "bpref"]:
        orig_val = orig_metrics.get(metric, 0)
        var_val = var_metrics.get(metric, 0)
        diff = var_val - orig_val
        metric_diffs[metric] = diff
    
    # Extract judgments
    orig_judgments = original_data.get("judgments", {})
    var_judgments = variation_data.get("judgments", {})
    
    # Get result lists
    orig_results = original_data.get("results", [])
    var_results = variation_data.get("results", [])
    
    # Get document IDs in each result set's top 10
    orig_top10 = [res["id"] for res in orig_results[:10]] if len(orig_results) >= 10 else [res["id"] for res in orig_results]
    var_top10 = [res["id"] for res in var_results[:10]] if len(var_results) >= 10 else [res["id"] for res in var_results]
    
    # Find documents unique to each list
    orig_unique = [doc_id for doc_id in orig_top10 if doc_id not in var_top10]
    var_unique = [doc_id for doc_id in var_top10 if doc_id not in orig_top10]
    
    # Find position changes for documents in both lists
    common_docs = [doc_id for doc_id in orig_top10 if doc_id in var_top10]
    position_changes = []
    
    for doc_id in common_docs:
        orig_pos = next((i+1 for i, res in enumerate(orig_results) if res["id"] == doc_id), 0)
        var_pos = next((i+1 for i, res in enumerate(var_results) if res["id"] == doc_id), 0)
        
        # Only include if we have judgments
        if doc_id in orig_judgments or doc_id in var_judgments:
            # Use max of judgments if doc appears in both judgment sets
            relevance = max(
                orig_judgments.get(doc_id, 0),
                var_judgments.get(doc_id, 0)
            )
            
            position_changes.append({
                "doc_id": doc_id,
                "original_rank": orig_pos,
                "variation_rank": var_pos,
                "change": orig_pos - var_pos,  # Positive means improvement (moved up)
                "relevance": relevance
            })
    
    # Calculate helpful/harmful changes
    helpful_changes = []
    harmful_changes = []
    
    # 1. Documents that moved up/down
    for change in position_changes:
        # Only consider relevant docs based on threshold
        if change["relevance"] >= threshold:
            if change["change"] > 0:  # Moved up (improvement)
                helpful_changes.append({
                    "type": "rank_improved",
                    "doc_id": change["doc_id"],
                    "relevance": change["relevance"],
                    "from_rank": change["original_rank"],
                    "to_rank": change["variation_rank"],
                    "change": change["change"]
                })
            elif change["change"] < 0:  # Moved down (regression)
                harmful_changes.append({
                    "type": "rank_degraded",
                    "doc_id": change["doc_id"],
                    "relevance": change["relevance"],
                    "from_rank": change["original_rank"],
                    "to_rank": change["variation_rank"],
                    "change": change["change"]
                })
    
    # 2. Relevant documents added/removed
    for doc_id in var_unique:
        if doc_id in var_judgments and var_judgments[doc_id] >= threshold:
            # Get actual rank
            var_pos = next((i+1 for i, res in enumerate(var_results) if res["id"] == doc_id), 0)
            
            helpful_changes.append({
                "type": "doc_added",
                "doc_id": doc_id,
                "relevance": var_judgments[doc_id],
                "rank": var_pos
            })
    
    for doc_id in orig_unique:
        if doc_id in orig_judgments and orig_judgments[doc_id] >= threshold:
            # Get actual rank
            orig_pos = next((i+1 for i, res in enumerate(orig_results) if res["id"] == doc_id), 0)
            
            harmful_changes.append({
                "type": "doc_removed",
                "doc_id": doc_id,
                "relevance": orig_judgments[doc_id],
                "rank": orig_pos
            })
    
    # Generate explanation based on changes
    explanation = ""
    
    # Only include metrics with significant differences
    significant_metrics = [m for m, diff in metric_diffs.items() if abs(diff) >= min_diff]
    
    if significant_metrics:
        explanation += "Significant metric changes:\n"
        for metric in significant_metrics:
            diff = metric_diffs[metric]
            direction = "improved" if diff > 0 else "degraded"
            explanation += f"- {metric}: {direction} by {abs(diff):.4f}\n"
    
    if helpful_changes:
        explanation += "\nHelpful changes:\n"
        for change in helpful_changes:
            if change["type"] == "rank_improved":
                explanation += (f"- Relevant document (rel={change['relevance']}) moved up "
                              f"from rank {change['from_rank']} to {change['to_rank']}\n")
            elif change["type"] == "doc_added":
                explanation += f"- New relevant document (rel={change['relevance']}) added at rank {change['rank']}\n"
    
    if harmful_changes:
        explanation += "\nHarmful changes:\n"
        for change in harmful_changes:
            if change["type"] == "rank_degraded":
                explanation += (f"- Relevant document (rel={change['relevance']}) moved down "
                              f"from rank {change['from_rank']} to {change['to_rank']}\n")
            elif change["type"] == "doc_removed":
                explanation += f"- Relevant document (rel={change['relevance']}) removed from rank {change['rank']}\n"
    
    # Calculate summary statistics
    summary = {
        "helpful_changes_count": len(helpful_changes),
        "harmful_changes_count": len(harmful_changes),
        "net_change": len(helpful_changes) - len(harmful_changes),
        "improved_metrics": [m for m, diff in metric_diffs.items() if diff > 0],
        "degraded_metrics": [m for m, diff in metric_diffs.items() if diff < 0]
    }
    
    # Determine overall impact
    if any(abs(diff) >= min_diff for diff in metric_diffs.values()):
        if sum(1 for diff in metric_diffs.values() if diff > 0) > sum(1 for diff in metric_diffs.values() if diff < 0):
            summary["overall_impact"] = "positive"
        elif sum(1 for diff in metric_diffs.values() if diff > 0) < sum(1 for diff in metric_diffs.values() if diff < 0):
            summary["overall_impact"] = "negative"
        else:
            summary["overall_impact"] = "mixed"
    else:
        summary["overall_impact"] = "neutral"
    
    return {
        "original_query": original_data["text"],
        "variation_query": variation_data["text"],
        "metrics": {
            "original": orig_metrics,
            "variation": var_metrics,
            "differences": metric_diffs
        },
        "rank_changes": position_changes,
        "helpful_changes": helpful_changes,
        "harmful_changes": harmful_changes,
        "summary": summary,
        "explanation": explanation
    }

def main():
    parser = argparse.ArgumentParser(description="Analyze metrics differences between query pairs")
    parser.add_argument("--run-id", type=int, required=True, help="Run ID to analyze")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database")
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
        # Get query relationships
        relationships = get_related_queries(db, "variation")
        
        # Get data for each query pair
        analyses = []
        overall_stats = defaultdict(int)
        
        for orig_id, var_id in relationships.items():
            # Get query data
            original_data = get_query_result_details(db, args.run_id, orig_id)
            variation_data = get_query_result_details(db, args.run_id, var_id)
            
            # Only analyze if both queries have metrics
            if (not original_data or not original_data.get("metrics") or 
                not variation_data or not variation_data.get("metrics")):
                logger.warning(f"Missing metrics for query pair {orig_id}/{var_id}")
                continue
            
            # Analyze differences
            analysis = analyze_result_list_differences(
                original_data, 
                variation_data,
                threshold=args.threshold,
                min_diff=args.min_diff
            )
            
            if analysis:
                analyses.append(analysis)
                overall_stats[analysis["summary"]["overall_impact"]] += 1
                
                # Print analysis for this pair
                print(f"\nAnalysis for query pair {orig_id}/{var_id}:")
                print(f"Original: {analysis['original_query']}")
                print(f"Variation: {analysis['variation_query']}")
                print("\nMetric Differences:")
                for metric, diff in analysis["metrics"]["differences"].items():
                    print(f"  {metric}: {diff:+.4f}")
                
                print("\n" + analysis["explanation"])
                print(f"Overall impact: {analysis['summary']['overall_impact'].upper()}")
                print("-" * 80)
        
        # Print overall statistics
        print("\n" + "=" * 80)
        print(f"OVERALL STATISTICS ({len(analyses)} query pairs analyzed)")
        print("=" * 80)
        print(f"Positive impact: {overall_stats['positive']} queries")
        print(f"Negative impact: {overall_stats['negative']} queries")
        print(f"Mixed impact: {overall_stats['mixed']} queries")
        print(f"Neutral impact: {overall_stats['neutral']} queries")
        
        # Calculate average metric differences
        avg_diffs = defaultdict(float)
        for analysis in analyses:
            for metric, diff in analysis["metrics"]["differences"].items():
                avg_diffs[metric] += diff
        
        if analyses:
            print("\nAverage metric differences (variation - original):")
            for metric, total_diff in avg_diffs.items():
                avg_diff = total_diff / len(analyses)
                print(f"  {metric}: {avg_diff:+.4f}")
        
        # Write JSON output if requested
        if args.output:
            output_data = {
                "run_id": args.run_id,
                "timestamp": db.get_timestamp(),
                "query_pair_analyses": analyses,
                "overall_statistics": dict(overall_stats),
                "average_metric_differences": {m: d/len(analyses) for m, d in avg_diffs.items()} if analyses else {}
            }
            
            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)
            
            print(f"\nDetailed analysis written to {args.output}")
            
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