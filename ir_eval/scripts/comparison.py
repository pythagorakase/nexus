#!/usr/bin/env python3
"""
Comparison Module for NEXUS IR Evaluation System

This module provides functions for comparing IR metrics between different runs.
"""

import os
import sys
import json
import datetime
import logging
from typing import Dict, List, Any, Optional, Set, Tuple

# Add parent directory to path to import other modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pg_db import IRDatabasePG

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("nexus.ir_eval.comparison")

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
                if "metadata" in query_data:
                    metadata = query_data["metadata"]
                    if "reranking_time" in metadata:
                        total_reranking_time += metadata["reranking_time"]
                        has_reranking_stats = True
                    # Also check for rerank_time (alternative field name)
                    elif "rerank_time" in metadata:
                        total_reranking_time += metadata["rerank_time"]
                        has_reranking_stats = True
            
            # Create runtime stats dictionary
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
    
    return comparison

def calculate_judgment_stats(judgments: Dict[str, int]) -> Dict[str, Any]:
    """
    Calculate statistics for a set of relevance judgments.
    
    Args:
        judgments: Dictionary mapping document IDs to relevance levels
        
    Returns:
        Dictionary with judgment statistics
    """
    if not judgments:
        return {
            "count": 0,
            "avg_relevance": 0,
            "relevant_count": 0,
            "nonrelevant_count": 0,
            "highly_relevant_count": 0,
            "relevant_ratio": 0,
            "relevance_distribution": {i: {"count": 0, "percentage": 0} for i in range(4)}
        }
    
    # Calculate statistics
    count = len(judgments)
    relevance_sum = sum(judgments.values())
    avg_relevance = relevance_sum / count if count > 0 else 0
    
    # Count by relevance level
    relevance_counts = {i: 0 for i in range(4)}
    for relevance in judgments.values():
        if 0 <= relevance <= 3:
            relevance_counts[relevance] += 1
    
    # Calculate derived statistics
    relevant_count = sum(relevance_counts[i] for i in range(1, 4))
    nonrelevant_count = relevance_counts[0]
    highly_relevant_count = relevance_counts[3]
    relevant_ratio = relevant_count / count if count > 0 else 0
    
    # Calculate distribution percentages
    relevance_distribution = {}
    for level, count in relevance_counts.items():
        percentage = count / len(judgments) if judgments else 0
        relevance_distribution[level] = {
            "count": count,
            "percentage": percentage
        }
    
    return {
        "count": count,
        "avg_relevance": avg_relevance,
        "relevant_count": relevant_count,
        "nonrelevant_count": nonrelevant_count,
        "highly_relevant_count": highly_relevant_count,
        "relevant_ratio": relevant_ratio,
        "relevance_distribution": relevance_distribution
    }