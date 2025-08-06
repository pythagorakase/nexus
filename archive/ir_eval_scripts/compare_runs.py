#!/usr/bin/env python3
"""
Compare Runs - Tool for NEXUS IR Evaluation System

This tool compares multiple search result runs to identify which
configuration performs better according to standard IR metrics.

Usage:
    python compare_runs.py --runs [RESULTS_FILE1] [RESULTS_FILE2] ... --qrels [QRELS_FILE]
    
    Optional arguments:
    --names               Names for each run (default: Run A, Run B, etc.)
    --golden-queries      Path to golden queries file (default: golden_queries.json)
    --output              Output file for comparison results (default: comparison_results.json)
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict
import datetime

# Make sure we can import from the parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import QRELS manager and metrics
from scripts.qrels import QRELSManager
from scripts.ir_metrics import calculate_all_metrics, average_metrics_by_category

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.compare")

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

def extract_run_metadata(results_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata about the run.
    
    Args:
        results_data: Results data dictionary
        
    Returns:
        Dictionary with run metadata
    """
    metadata = {
        "timestamp": results_data.get("timestamp", "unknown"),
        "settings": results_data.get("settings_text", "")
    }
    
    # Extract hybrid search info
    if "settings" in results_data and "hybrid_search" in results_data["settings"]:
        hybrid = results_data["settings"]["hybrid_search"]
        metadata["hybrid_search"] = hybrid.get("enabled", False)
        if hybrid.get("enabled", False):
            metadata["vector_weight"] = hybrid.get("vector_weight_default", 0)
            metadata["text_weight"] = hybrid.get("text_weight_default", 0)
            metadata["target_model"] = hybrid.get("target_model", "unknown")
    
    return metadata

def evaluate_run(
    results_data: Dict[str, Any],
    qrels: QRELSManager
) -> Dict[str, Any]:
    """
    Evaluate a run against relevance judgments.
    
    Args:
        results_data: Results data dictionary
        qrels: QRELSManager instance with relevance judgments
        
    Returns:
        Dictionary with evaluation results
    """
    # Extract query results
    query_results = results_data.get("query_results", [])
    if not query_results:
        logger.error("No query results found in results data")
        return {}
    
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
            metrics = calculate_all_metrics(results, judgments)
            query_metrics[query_text] = metrics
    
    # Calculate aggregate metrics
    aggregated = average_metrics_by_category(query_metrics, query_categories)
    
    # Add metadata
    metadata = extract_run_metadata(results_data)
    
    return {
        "metadata": metadata,
        "by_query": query_metrics,
        "aggregated": aggregated
    }

def compare_runs(
    run_results: List[Dict[str, Any]],
    run_names: List[str],
    output_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compare multiple runs and identify the best performer.
    
    Args:
        run_results: List of evaluation results for each run
        run_names: List of names for each run
        output_file: Optional path to save comparison results
        
    Returns:
        Dictionary with comparison results
    """
    # Ensure we have names for all runs
    if len(run_names) < len(run_results):
        for i in range(len(run_names), len(run_results)):
            run_names.append(f"Run {chr(65 + i)}")
    
    # Structure for comparison results
    comparison = {
        "timestamp": datetime.datetime.now().isoformat(),
        "runs": [{"name": name, "results": results} for name, results in zip(run_names, run_results)],
        "comparison": {
            "overall": {},
            "by_category": {},
            "by_query": {}
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
        best_run = run_names[best_index]
    else:
        best_index = -1
        best_run = "None"
    
    comparison["best_run"] = {
        "name": best_run,
        "index": best_index,
        "scores": run_scores
    }
    
    # Save to file if requested
    if output_file:
        try:
            with open(output_file, "w") as f:
                json.dump(comparison, f, indent=2)
            logger.info(f"Comparison results saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving comparison results: {e}")
    
    return comparison

def print_comparison_table(comparison: Dict[str, Any]) -> None:
    """
    Print a formatted comparison table.
    
    Args:
        comparison: Comparison results dictionary
    """
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

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Compare NEXUS search result runs")
    parser.add_argument("--runs", nargs="+", required=True, 
                      help="Paths to result JSON files to compare")
    parser.add_argument("--qrels", default="qrels.json",
                      help="Path to QRELS file with relevance judgments")
    parser.add_argument("--names", nargs="+", default=[],
                      help="Names for each run (default: Run A, Run B, etc.)")
    parser.add_argument("--output", default=None,
                      help="Output file for comparison results (JSON)")
    
    args = parser.parse_args()
    
    # Validate runs count
    if len(args.runs) < 1:
        logger.error("At least one run file must be provided")
        return 1
    
    # Load QRELS
    qrels = QRELSManager(args.qrels)
    logger.info(f"Loaded {qrels.get_judgment_count()} judgments from {args.qrels}")
    
    # Generate default run names if not provided
    run_names = args.names
    if not run_names:
        run_names = [f"Run {chr(65+i)}" for i in range(len(args.runs))]
    elif len(run_names) < len(args.runs):
        for i in range(len(run_names), len(args.runs)):
            run_names.append(f"Run {chr(65+i)}")
    
    # Evaluate each run
    run_results = []
    for i, run_file in enumerate(args.runs):
        run_name = run_names[i] if i < len(run_names) else f"Run {chr(65+i)}"
        logger.info(f"Evaluating {run_name}: {run_file}")
        
        # Load results
        results_data = load_results(run_file)
        if not results_data:
            logger.error(f"Could not load results from {run_file}")
            continue
            
        # Evaluate
        evaluation = evaluate_run(results_data, qrels)
        if evaluation:
            run_results.append(evaluation)
        else:
            logger.error(f"Failed to evaluate {run_file}")
            run_results.append({})
    
    # Generate comparison output filename if not provided
    if not args.output and len(args.runs) > 0:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"comparison_results_{timestamp}.json"
    
    # Compare runs
    comparison = compare_runs(run_results, run_names, args.output)
    
    # Print comparison table
    print_comparison_table(comparison)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())