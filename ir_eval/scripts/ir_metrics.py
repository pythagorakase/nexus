#!/usr/bin/env python3
"""
IR Metrics Module for NEXUS IR Evaluation System

This module provides functions for calculating standard IR metrics:
- Precision at k (P@k)
- Mean Reciprocal Rank (MRR)
- Binary Preference (BPREF)
- Normalized Discounted Cumulative Gain (NDCG)

These metrics are used to evaluate the performance of the MEMNON retrieval system.
"""

import math
from typing import Dict, List, Any, Set, Optional, Tuple

def precision_at_k(results: List[Dict[str, Any]], judgments: Dict[str, int], k: int, 
                  relevance_threshold: int = 1) -> Tuple[float, int]:
    """
    Calculate precision at k (P@k) based on relevance judgments.
    
    Args:
        results: List of result items with "id" field
        judgments: Dictionary mapping doc_id to relevance score (0-3)
        k: The k value for P@k calculation
        relevance_threshold: Minimum relevance score to consider relevant (default: 1)
    
    Returns:
        Tuple of (precision_value, num_judged_in_k)
    """
    if not results or k <= 0:
        return 0.0, 0
        
    # Consider only the top k results
    top_k = results[:k]
    
    # Count relevant documents in top k
    relevant_count = 0
    judged_count = 0
    
    for item in top_k:
        doc_id = str(item.get("id", ""))
        
        # Check if document has been judged
        if doc_id in judgments:
            judged_count += 1
            
            # Check if it's relevant
            if judgments[doc_id] >= relevance_threshold:
                relevant_count += 1
    
    # Calculate precision
    precision = relevant_count / k if k > 0 else 0.0
    
    return precision, judged_count

def mean_reciprocal_rank(results: List[Dict[str, Any]], judgments: Dict[str, int], 
                        relevance_threshold: int = 1) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR) based on relevance judgments.
    
    Args:
        results: List of result items with "id" field
        judgments: Dictionary mapping doc_id to relevance score (0-3)
        relevance_threshold: Minimum relevance score to consider relevant (default: 1)
    
    Returns:
        MRR value
    """
    if not results or not judgments:
        return 0.0
    
    # Find the first relevant document
    for i, item in enumerate(results):
        doc_id = str(item.get("id", ""))
        
        # Check if document is judged and relevant
        if doc_id in judgments and judgments[doc_id] >= relevance_threshold:
            # Return reciprocal rank (1-based)
            return 1.0 / (i + 1)
    
    # No relevant documents found
    return 0.0

def binary_preference(results: List[Dict[str, Any]], judgments: Dict[str, int], 
                     relevance_threshold: int = 1) -> float:
    """
    Calculate Binary Preference (BPREF) based on relevance judgments.
    
    BPREF measures the effectiveness of a system at retrieving judged relevant documents
    before judged non-relevant documents, while ignoring unjudged documents.
    
    Args:
        results: List of result items with "id" field
        judgments: Dictionary mapping doc_id to relevance score (0-3)
        relevance_threshold: Minimum relevance score to consider relevant (default: 1)
    
    Returns:
        BPREF value
    """
    if not results or not judgments:
        return 0.0
    
    # Split judgments into relevant and non-relevant
    relevant_docs = {doc_id for doc_id, score in judgments.items() if score >= relevance_threshold}
    nonrelevant_docs = {doc_id for doc_id, score in judgments.items() if score < relevance_threshold}
    
    # Count total number of relevant documents
    R = len(relevant_docs)
    
    if R == 0:
        return 0.0  # No relevant documents
    
    # Initialize running sum
    bpref_sum = 0.0
    
    # List to track rank of retrieved relevant documents
    retrieved_relevant_ranks = []
    
    # Track number of non-relevant documents seen before each relevant document
    for rank, item in enumerate(results):
        doc_id = str(item.get("id", ""))
        
        # Skip unjudged documents
        if doc_id not in judgments:
            continue
            
        # If document is relevant, count how many non-relevant docs came before it
        if doc_id in relevant_docs:
            # Count non-relevant docs seen so far
            nonrel_before = len([r for r in range(rank) if 
                              str(results[r].get("id", "")) in nonrelevant_docs])
            
            # Add to sum using BPREF formula
            bpref_sum += 1.0 - min(nonrel_before, R) / max(R, 1)
    
    # Normalize by number of relevant documents
    return bpref_sum / R if R > 0 else 0.0

def ndcg_at_k(results: List[Dict[str, Any]], judgments: Dict[str, int], k: int) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain (NDCG) at k.
    
    Args:
        results: List of result items with "id" field
        judgments: Dictionary mapping doc_id to relevance score (0-3)
        k: The k value for NDCG@k calculation
    
    Returns:
        NDCG@k value
    """
    if not results or k <= 0:
        return 0.0
    
    # Consider only the top k results
    top_k = results[:k]
    
    # Calculate DCG
    dcg = 0.0
    for i, item in enumerate(top_k):
        doc_id = str(item.get("id", ""))
        
        # Get relevance score
        rel = judgments.get(doc_id, 0)
        
        # Using standard formula: rel / log2(i+2)
        # We use i+2 because log2(1) = 0, and we want the first position to count
        dcg += rel / math.log2(i + 2)
    
    # Calculate ideal DCG (IDCG)
    # Get all relevance scores and sort in descending order
    rel_scores = sorted([score for doc_id, score in judgments.items()], reverse=True)
    
    # Take only top k scores
    rel_scores = rel_scores[:k]
    
    # Calculate IDCG
    idcg = 0.0
    for i, rel in enumerate(rel_scores):
        idcg += rel / math.log2(i + 2)
    
    # Calculate NDCG
    return dcg / idcg if idcg > 0 else 0.0

def calculate_all_metrics(results: List[Dict[str, Any]], judgments: Dict[str, int]) -> Dict[str, Any]:
    """
    Calculate all IR metrics for a single query-results pair.
    
    Args:
        results: List of result items with "id" field
        judgments: Dictionary mapping doc_id to relevance score (0-3)
    
    Returns:
        Dictionary with calculated metrics
    """
    # Calculate P@5 and P@10
    p_at_5, judged_5 = precision_at_k(results, judgments, 5)
    p_at_10, judged_10 = precision_at_k(results, judgments, 10)
    
    # Calculate MRR
    mrr = mean_reciprocal_rank(results, judgments)
    
    # Calculate BPREF
    bpref = binary_preference(results, judgments)
    
    # Calculate NDCG@10
    ndcg_10 = ndcg_at_k(results, judgments, 10)
    
    # Count judged and unjudged documents
    judged_doc_ids = set(judgments.keys())
    result_doc_ids = {str(r.get("id", "")) for r in results}
    
    judged_total = len(judged_doc_ids.intersection(result_doc_ids))
    unjudged_count = len(result_doc_ids) - judged_total
    
    # Relevance counts
    relevant_count = sum(1 for doc_id, score in judgments.items() 
                       if doc_id in result_doc_ids and score >= 1)
    highly_relevant_count = sum(1 for doc_id, score in judgments.items() 
                              if doc_id in result_doc_ids and score >= 3)
    
    return {
        "p@5": p_at_5,
        "p@10": p_at_10,
        "mrr": mrr,
        "bpref": bpref,
        "ndcg@10": ndcg_10,
        "judged_counts": {
            "p@5": judged_5,
            "p@10": judged_10,
            "total": judged_total
        },
        "unjudged_count": unjudged_count,
        "relevant_count": relevant_count,
        "highly_relevant_count": highly_relevant_count
    }

def average_metrics_by_category(query_metrics: Dict[str, Dict[str, Any]], 
                              query_categories: Dict[str, str]) -> Dict[str, Dict[str, float]]:
    """
    Calculate average metrics grouped by query category.
    
    Args:
        query_metrics: Dictionary mapping query text to metrics
        query_categories: Dictionary mapping query text to category
    
    Returns:
        Dictionary with aggregated metrics by category, plus overall averages
    """
    # Initialize result structure
    result = {
        "overall": {},
        "by_category": {}
    }
    
    # Initialize counters for each metric
    metric_sums = {
        "p@5": 0.0,
        "p@10": 0.0,
        "mrr": 0.0,
        "bpref": 0.0,
        "ndcg@10": 0.0,
        "unjudged_count": 0,
        "judged_counts": {
            "p@5": 0,
            "p@10": 0,
            "total": 0
        }
    }
    
    # Initialize category counters
    category_counts = {}
    category_sums = {}
    
    # Sum metrics across all queries
    for query_text, metrics in query_metrics.items():
        # Add to overall counts
        for metric in ["p@5", "p@10", "mrr", "bpref", "ndcg@10"]:
            metric_sums[metric] += metrics.get(metric, 0.0)
        
        # Add to unjudged count
        metric_sums["unjudged_count"] += metrics.get("unjudged_count", 0)
        
        # Add to judged counts
        judged_counts = metrics.get("judged_counts", {})
        for count_name in ["p@5", "p@10", "total"]:
            metric_sums["judged_counts"][count_name] += judged_counts.get(count_name, 0)
        
        # Get category and add to category sums
        category = query_categories.get(query_text, "unknown")
        
        if category not in category_counts:
            category_counts[category] = 0
            category_sums[category] = {
                "p@5": 0.0,
                "p@10": 0.0,
                "mrr": 0.0,
                "bpref": 0.0,
                "ndcg@10": 0.0,
                "unjudged_count": 0,
                "judged_counts": {
                    "p@5": 0,
                    "p@10": 0,
                    "total": 0
                }
            }
        
        category_counts[category] += 1
        
        # Add to category sums
        for metric in ["p@5", "p@10", "mrr", "bpref", "ndcg@10"]:
            category_sums[category][metric] += metrics.get(metric, 0.0)
        
        category_sums[category]["unjudged_count"] += metrics.get("unjudged_count", 0)
        
        for count_name in ["p@5", "p@10", "total"]:
            category_sums[category]["judged_counts"][count_name] += judged_counts.get(count_name, 0)
    
    # Calculate overall averages
    query_count = len(query_metrics)
    
    if query_count > 0:
        for metric in ["p@5", "p@10", "mrr", "bpref", "ndcg@10"]:
            result["overall"][metric] = metric_sums[metric] / query_count
        
        result["overall"]["unjudged_count"] = metric_sums["unjudged_count"]
        result["overall"]["judged_counts"] = metric_sums["judged_counts"]
    
    # Calculate category averages
    for category, count in category_counts.items():
        result["by_category"][category] = {}
        
        if count > 0:
            for metric in ["p@5", "p@10", "mrr", "bpref", "ndcg@10"]:
                result["by_category"][category][metric] = category_sums[category][metric] / count
            
            result["by_category"][category]["unjudged_count"] = category_sums[category]["unjudged_count"]
            result["by_category"][category]["judged_counts"] = category_sums[category]["judged_counts"]
    
    return result