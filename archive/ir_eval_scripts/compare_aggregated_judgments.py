#!/usr/bin/env python3
"""
Compare Aggregated Judgments between Original Queries and Variations.

This script analyzes and compares the pooled relevance judgments for
original queries (1-9) versus variation queries (10-19).

Usage:
    python compare_aggregated_judgments.py
"""

import os
import sys
import logging
import statistics
from typing import Dict, List, Any, Set, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import IRDatabase

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("compare_aggregated")

# Define query groups
ORIGINAL_QUERIES = list(range(1, 10))  # 1-9
VARIATION_QUERIES = list(range(10, 20))  # 10-19

def get_judgments_for_query_group(db, query_ids: List[int]) -> Dict[str, int]:
    """Get all judgments for a group of queries"""
    all_judgments = {}
    
    for query_id in query_ids:
        cursor = db.conn.cursor()
        cursor.execute("SELECT doc_id, relevance FROM judgments WHERE query_id = ?", (query_id,))
        
        for row in cursor.fetchall():
            doc_id = row['doc_id']
            relevance = row['relevance']
            all_judgments[doc_id] = relevance
    
    return all_judgments

def calculate_judgment_stats(judgments: Dict[str, int]) -> Dict[str, Any]:
    """Calculate statistics about a set of judgments"""
    if not judgments:
        return {
            "count": 0,
            "avg_relevance": 0.0,
            "relevant_count": 0,
            "nonrelevant_count": 0,
            "highly_relevant_count": 0,
            "relevant_ratio": 0.0,
            "relevance_distribution": {}
        }
    
    relevance_values = list(judgments.values())
    
    # Count by relevance level
    relevant_count = sum(1 for v in relevance_values if v >= 1)
    nonrelevant_count = sum(1 for v in relevance_values if v == 0)
    highly_relevant_count = sum(1 for v in relevance_values if v >= 3)
    
    # Calculate average relevance
    avg_relevance = sum(relevance_values) / len(relevance_values) if relevance_values else 0
    
    # Calculate ratio of relevant documents
    relevant_ratio = relevant_count / len(relevance_values) if relevance_values else 0
    
    # Get distribution by relevance level
    relevance_distribution = {}
    for level in range(4):  # Relevance levels 0-3
        count = sum(1 for v in relevance_values if v == level)
        relevance_distribution[level] = {
            "count": count,
            "percentage": (count / len(relevance_values)) * 100 if relevance_values else 0
        }
    
    return {
        "count": len(judgments),
        "avg_relevance": avg_relevance,
        "relevant_count": relevant_count,
        "nonrelevant_count": nonrelevant_count,
        "highly_relevant_count": highly_relevant_count,
        "relevant_ratio": relevant_ratio,
        "relevance_distribution": relevance_distribution
    }

def main():
    db = IRDatabase()
    
    # Get all judgments for original queries (1-9)
    original_judgments = get_judgments_for_query_group(db, ORIGINAL_QUERIES)
    logger.info(f"Found {len(original_judgments)} total judgments for original queries")
    
    # Get all judgments for variation queries (10-19)
    variation_judgments = get_judgments_for_query_group(db, VARIATION_QUERIES)
    logger.info(f"Found {len(variation_judgments)} total judgments for variation queries")
    
    # Calculate statistics for each group
    original_stats = calculate_judgment_stats(original_judgments)
    variation_stats = calculate_judgment_stats(variation_judgments)
    
    # Find common documents
    original_docs = set(original_judgments.keys())
    variation_docs = set(variation_judgments.keys())
    common_docs = original_docs & variation_docs
    
    # Calculate agreement on common documents
    if common_docs:
        agreement_count = sum(1 for doc in common_docs 
                            if original_judgments[doc] == variation_judgments[doc])
        agreement_ratio = agreement_count / len(common_docs)
    else:
        agreement_count = 0
        agreement_ratio = 0
    
    # Print results
    print("\nAggregated Judgment Comparison: Original Queries vs Variations")
    print("=" * 80)
    
    print(f"\nOriginal Queries (IDs {ORIGINAL_QUERIES}):")
    print(f"  Total documents judged: {original_stats['count']}")
    print(f"  Average relevance: {original_stats['avg_relevance']:.2f}")
    print(f"  Relevant documents: {original_stats['relevant_count']} ({original_stats['relevant_ratio'] * 100:.1f}%)")
    print(f"  Non-relevant documents: {original_stats['nonrelevant_count']}")
    print(f"  Highly relevant documents: {original_stats['highly_relevant_count']}")
    
    print("\nRelevance distribution for Original Queries:")
    for level, data in original_stats['relevance_distribution'].items():
        print(f"  Level {level}: {data['count']} documents ({data['percentage']:.1f}%)")
    
    print(f"\nVariation Queries (IDs {VARIATION_QUERIES}):")
    print(f"  Total documents judged: {variation_stats['count']}")
    print(f"  Average relevance: {variation_stats['avg_relevance']:.2f}")
    print(f"  Relevant documents: {variation_stats['relevant_count']} ({variation_stats['relevant_ratio'] * 100:.1f}%)")
    print(f"  Non-relevant documents: {variation_stats['nonrelevant_count']}")
    print(f"  Highly relevant documents: {variation_stats['highly_relevant_count']}")
    
    print("\nRelevance distribution for Variation Queries:")
    for level, data in variation_stats['relevance_distribution'].items():
        print(f"  Level {level}: {data['count']} documents ({data['percentage']:.1f}%)")
    
    print("\nComparison:")
    print(f"  Common documents: {len(common_docs)}")
    print(f"  Agreement on common documents: {agreement_count} ({agreement_ratio * 100:.1f}%)")
    
    # Calculate differences
    avg_relevance_diff = variation_stats['avg_relevance'] - original_stats['avg_relevance']
    relevant_ratio_diff = variation_stats['relevant_ratio'] - original_stats['relevant_ratio']
    
    print("\nDifferences (Variation - Original):")
    print(f"  Average relevance: {avg_relevance_diff:+.2f}")
    print(f"  Relevant ratio: {relevant_ratio_diff:+.2f} ({relevant_ratio_diff * 100:+.1f}%)")
    
    print("\nDistribution difference:")
    for level in range(4):
        orig_pct = original_stats['relevance_distribution'][level]['percentage']
        var_pct = variation_stats['relevance_distribution'][level]['percentage']
        diff = var_pct - orig_pct
        print(f"  Level {level}: {diff:+.1f}%")
    
    print("=" * 80)
    
    # Close the database connection
    db.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())