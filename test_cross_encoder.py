#!/usr/bin/env python3
"""
Test script for cross-encoder reranking in MEMNON

This script tests the cross-encoder reranking functionality by comparing
search results with and without reranking.
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_cross_encoder")

# Import MEMNON agent and settings
from nexus.agents.memnon.memnon import MEMNON, MEMNON_SETTINGS


class DummyInterface:
    """Simple interface for MEMNON agent testing."""
    
    def assistant_message(self, message):
        print(f"MEMNON: {message}")
    
    def user_message(self, message):
        print(f"User: {message}")


def run_test_queries(memnon, queries: List[str], with_reranking: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    Run a set of test queries against MEMNON
    
    Args:
        memnon: MEMNON agent instance
        queries: List of query strings to test
        with_reranking: Whether to use cross-encoder reranking
        
    Returns:
        Dictionary of query results
    """
    results = {}
    
    for query in queries:
        logger.info(f"Running query: '{query}'")
        
        start_time = time.time()
        
        # Set up cross-encoder for this run
        if 'retrieval' in MEMNON_SETTINGS and 'cross_encoder_reranking' in MEMNON_SETTINGS['retrieval']:
            MEMNON_SETTINGS['retrieval']['cross_encoder_reranking']['enabled'] = with_reranking
        
        # Run the query
        result = memnon.query_memory(query, k=10)
        
        query_time = time.time() - start_time
        
        # Store results
        results[query] = {
            "results": result,
            "query_time": query_time,
            "with_reranking": with_reranking
        }
        
        logger.info(f"Query completed in {query_time:.3f} seconds {'with' if with_reranking else 'without'} reranking")
    
    return results


def compare_results(baseline_results: Dict[str, Dict[str, Any]], 
                   reranked_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare baseline and reranked results to quantify differences
    
    Args:
        baseline_results: Results without reranking
        reranked_results: Results with reranking
        
    Returns:
        Comparison metrics
    """
    comparison = {
        "queries": {},
        "summary": {
            "total_queries": len(baseline_results),
            "total_position_changes": 0,
            "avg_position_change": 0.0,
            "avg_time_difference": 0.0,
            "rank_correlation": 0.0
        }
    }
    
    total_position_changes = 0
    total_time_diff = 0.0
    
    for query, baseline in baseline_results.items():
        if query not in reranked_results:
            continue
            
        reranked = reranked_results[query]
        
        # Track original IDs and positions
        baseline_ids = [r.get("id") for r in baseline["results"]["results"]]
        reranked_ids = [r.get("id") for r in reranked["results"]["results"]]
        
        # Calculate position changes
        position_changes = []
        
        for i, result_id in enumerate(reranked_ids):
            if result_id in baseline_ids:
                original_pos = baseline_ids.index(result_id)
                position_change = original_pos - i  # Positive means moved up, negative means moved down
                position_changes.append((result_id, i, original_pos, position_change))
                total_position_changes += abs(position_change)
        
        # Calculate timing difference
        time_diff = reranked["query_time"] - baseline["query_time"]
        total_time_diff += time_diff
        
        # Store query-specific comparison
        comparison["queries"][query] = {
            "position_changes": position_changes,
            "baseline_time": baseline["query_time"],
            "reranked_time": reranked["query_time"],
            "time_difference": time_diff,
            "reranking_time": reranked["results"]["metadata"]["search_stats"].get("rerank_time", 0.0),
            "new_results": [r_id for r_id in reranked_ids if r_id not in baseline_ids],
            "dropped_results": [b_id for b_id in baseline_ids if b_id not in reranked_ids]
        }
    
    # Calculate summary metrics
    num_queries = len(comparison["queries"])
    if num_queries > 0:
        comparison["summary"]["avg_position_change"] = total_position_changes / num_queries
        comparison["summary"]["avg_time_difference"] = total_time_diff / num_queries
        comparison["summary"]["total_position_changes"] = total_position_changes
    
    return comparison


def main():
    """Run cross-encoder reranking tests"""
    parser = argparse.ArgumentParser(description="Test cross-encoder reranking in MEMNON")
    parser.add_argument("--queries", type=str, nargs="+", 
                      default=["What happened to Alex?", 
                               "Tell me about Emilia",
                               "Who was at the meeting?",
                               "What happened in the hospital?",
                               "How did Alex escape from the facility?"],
                      help="Queries to test")
    parser.add_argument("--output", type=str, default="cross_encoder_test_results.json",
                      help="Output file for test results")
    args = parser.parse_args()
    
    logger.info("Initializing MEMNON agent...")
    interface = DummyInterface()
    memnon = MEMNON(interface=interface, debug=True)
    
    # Check if cross-encoder reranking is configured
    if 'retrieval' not in MEMNON_SETTINGS or 'cross_encoder_reranking' not in MEMNON_SETTINGS['retrieval']:
        logger.error("Cross-encoder reranking is not configured in settings")
        return
    
    logger.info("Running baseline queries without reranking...")
    baseline_results = run_test_queries(memnon, args.queries, with_reranking=False)
    
    logger.info("Running queries with cross-encoder reranking...")
    reranked_results = run_test_queries(memnon, args.queries, with_reranking=True)
    
    logger.info("Comparing results...")
    comparison = compare_results(baseline_results, reranked_results)
    
    # Print summary
    print("\n===== Cross-Encoder Reranking Test Results =====")
    print(f"Total queries: {comparison['summary']['total_queries']}")
    print(f"Average position change: {comparison['summary']['avg_position_change']:.2f}")
    print(f"Average time difference: {comparison['summary']['avg_time_difference']:.3f} seconds")
    
    # Print per-query results
    for query, query_comparison in comparison["queries"].items():
        print(f"\nQuery: {query}")
        print(f"  Baseline time: {query_comparison['baseline_time']:.3f}s, Reranked time: {query_comparison['reranked_time']:.3f}s")
        print(f"  Reranking time: {query_comparison['reranking_time']:.3f}s")
        print(f"  Position changes: {len(query_comparison['position_changes'])}")
        
        for result_id, new_pos, orig_pos, change in query_comparison['position_changes']:
            if change != 0:
                direction = "up" if change > 0 else "down"
                print(f"    ID {result_id}: Moved {direction} {abs(change)} positions (from {orig_pos+1} to {new_pos+1})")
        
        if query_comparison['new_results']:
            print(f"  New results: {len(query_comparison['new_results'])}")
        
        if query_comparison['dropped_results']:
            print(f"  Dropped results: {len(query_comparison['dropped_results'])}")
    
    # Save results to file
    test_results = {
        "baseline": baseline_results,
        "reranked": reranked_results,
        "comparison": comparison
    }
    
    with open(args.output, "w") as f:
        json.dump(test_results, f, indent=2)
    
    logger.info(f"Test results saved to {args.output}")


if __name__ == "__main__":
    main()