#!/usr/bin/env python3
"""
Display module for NEXUS IR Evaluation System

This module provides functions for displaying data and results from IR evaluations
in formatted tables and structured outputs.

Main functions:
- print_comparison_table: Print comparison of runs
- print_metrics_table: Print metrics in a formatted table
- print_configuration_details: Print configuration details
- print_current_parameters: Print current parameters in copy-paste friendly format
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Tuple, Optional, Set

# Make sure we can import from the parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.display")

def print_comparison_table(comparison: Dict[str, Any]) -> None:
    """
    Print a formatted comparison table for IR evaluation runs.
    
    Args:
        comparison: Dictionary with comparison data
    """
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

def print_metrics_table(metrics: Dict[str, float], title: str = "Metrics", include_header: bool = True) -> None:
    """
    Print metrics in a formatted table.
    
    Args:
        metrics: Dictionary of metrics
        title: Title for the table
        include_header: Whether to include a header
    """
    if include_header:
        print(f"\n{title}:")
        print("-"*50)
    
    # Metrics rows
    for metric_name, value in metrics.items():
        if isinstance(value, (int, float)):
            formatted_value = f"{value:.4f}" if isinstance(value, float) else str(value)
            print(f"{metric_name.ljust(15)}: {formatted_value}")
    
    if include_header:
        print("-"*50)

def print_configuration_details(control_settings: Dict[str, Any], experimental_settings: Dict[str, Any]) -> None:
    """
    Print details of control and experimental configurations.
    
    Args:
        control_settings: Control configuration settings
        experimental_settings: Experimental configuration settings
    """
    print("\n" + "="*80)
    print("Configuration details")
    print("="*80)
    
    # Display control configuration
    print("\nCONTROL Configuration (from settings.json):")
    print("-"*80)
    
    if control_settings:
        if "retrieval" in control_settings:
            retrieval = control_settings["retrieval"]
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
        if "models" in control_settings:
            print("\nModels:")
            for model, config in control_settings["models"].items():
                active = config.get("is_active", False)
                if active:
                    print(f"  {model}: dimensions={config.get('dimensions', 'N/A')}, weight={config.get('weight', 'N/A')}")
    else:
        print("No control settings found")
    
    # Display experimental configuration
    print("\nEXPERIMENTAL Configuration (from golden_queries.json):")
    print("-"*80)
    
    if experimental_settings:
        if "retrieval" in experimental_settings:
            retrieval = experimental_settings["retrieval"]
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
        if "models" in experimental_settings:
            print("\nModels:")
            for model, config in experimental_settings["models"].items():
                active = config.get("is_active", False)
                if active:
                    print(f"  {model}: dimensions={config.get('dimensions', 'N/A')}, weight={config.get('weight', 'N/A')}")
    else:
        print("No experimental settings found in golden_queries.json")

def print_current_parameters(settings_path: str, golden_queries_path: str) -> None:
    """
    Display current parameter values in a copy-paste friendly format.
    
    Args:
        settings_path: Path to settings.json
        golden_queries_path: Path to golden_queries.json
    """
    print("\n" + "="*80)
    print("Current Parameters (Copy-Paste Ready)")
    print("="*80)
    
    # Get settings.json
    settings_content = {}
    try:
        with open(settings_path, 'r') as f:
            settings_content = json.load(f)
    except Exception as e:
        logger.error(f"Error loading settings from {settings_path}: {e}")
    
    golden_queries_content = {}
    try:
        with open(golden_queries_path, 'r') as f:
            golden_queries_content = json.load(f)
    except Exception as e:
        logger.error(f"Error loading golden queries from {golden_queries_path}: {e}")
    
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