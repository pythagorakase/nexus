#!/usr/bin/env python3
"""
Test script for time-aware search functionality in MEMNON.

This script tests the temporal search capabilities by running a series
of temporal queries and comparing results with standard hybrid search.
"""

import os
import sys
import json
import logging
import argparse
import traceback
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("temporal_search_test")

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import settings and modules
from nexus.agents.memnon.utils import temporal_search
from nexus.agents.memnon.utils import db_access
from nexus.agents.memnon.memnon import MEMNON

def load_settings():
    """Load settings from settings.json"""
    with open("settings.json", "r") as f:
        return json.load(f)

def test_temporal_classification():
    """Test the temporal query classification functionality"""
    print("\n=== Testing Temporal Query Classification ===")
    
    early_queries = [
        "What was the first encounter between Alex and Emilia?",
        "How did the story begin?",
        "Tell me about the initial meeting with Dr. Nyati",
        "What are the origins of the cybernetics program?",
        "What happened at the start of the investigation?"
    ]
    
    recent_queries = [
        "What's the current status of the project?",
        "What has Alex been doing recently?",
        "Tell me about the latest developments with Emilia",
        "What's happening now with the cybernetics program?",
        "What were the most recent discoveries?"
    ]
    
    non_temporal_queries = [
        "Who is Dr. Nyati?",
        "What is the relationship between Alex and Emilia?",
        "Describe the cybernetics program",
        "Why did Alex decide to investigate?",
        "How does the neural implant work?"
    ]
    
    print("\nEarly Temporal Queries:")
    for query in early_queries:
        classification = temporal_search.classify_temporal_query(query)
        print(f"  Query: '{query}'")
        print(f"  Classification: {classification}")
        print()
    
    print("\nRecent Temporal Queries:")
    for query in recent_queries:
        classification = temporal_search.classify_temporal_query(query)
        print(f"  Query: '{query}'")
        print(f"  Classification: {classification}")
        print()
    
    print("\nNon-Temporal Queries:")
    for query in non_temporal_queries:
        classification = temporal_search.classify_temporal_query(query)
        print(f"  Query: '{query}'")
        print(f"  Classification: {classification}")
        print()

def test_temporal_boost():
    """Test the temporal boost calculation functionality"""
    print("\n=== Testing Temporal Boost Calculation ===")
    
    test_cases = [
        # base_score, temporal_position, classification, boost_factor
        (0.8, 0.1, "early", 0.5),      # Early query with early content
        (0.8, 0.9, "early", 0.5),      # Early query with recent content
        (0.8, 0.1, "recent", 0.5),     # Recent query with early content
        (0.8, 0.9, "recent", 0.5),     # Recent query with recent content
        (0.8, 0.5, "non_temporal", 0.5) # Non-temporal query
    ]
    
    for base_score, temporal_position, classification, boost_factor in test_cases:
        adjusted_score = temporal_search.apply_temporal_boost(
            base_score, temporal_position, classification, boost_factor
        )
        
        print(f"Base score: {base_score:.4f}, Temporal position: {temporal_position:.4f}")
        print(f"Query classification: {classification}, Boost factor: {boost_factor}")
        print(f"Adjusted score: {adjusted_score:.4f}")
        print(f"Difference: {adjusted_score - base_score:+.4f}")
        print()

def run_comparison_query(memnon, query, temporal_boost_factor=0.5):
    """
    Run both standard hybrid search and time-aware search with the same query
    
    Args:
        memnon: Initialized MEMNON instance
        query: Query text to execute
        temporal_boost_factor: Temporal boost factor to use
        
    Returns:
        Tuple of (hybrid_results, temporal_results)
    """
    # Get query embedding
    embedding = memnon.get_embedding(query)
    
    # Run standard hybrid search
    hybrid_results = db_access.execute_hybrid_search(
        memnon.settings["database"]["url"],
        query,
        embedding,
        "inf-retriever-v1-1.5b",  # Use the default model
        0.6,  # vector_weight
        0.4,  # text_weight
        None,  # filters
        10    # top_k
    )
    
    # Run time-aware search
    temporal_results = temporal_search.execute_time_aware_search(
        memnon.settings["database"]["url"],
        query,
        embedding,
        "inf-retriever-v1-1.5b",  # Use the default model
        0.6,  # vector_weight
        0.4,  # text_weight
        temporal_boost_factor,  # temporal_boost_factor
        None,  # filters
        10    # top_k
    )
    
    return hybrid_results, temporal_results

def display_results_comparison(hybrid_results, temporal_results, query, classification):
    """Display a comparison of results from both search methods"""
    print(f"\nQuery: '{query}'")
    print(f"Classification: {classification}")
    print("\n=== HYBRID SEARCH RESULTS ===")
    
    for i, result in enumerate(hybrid_results[:5], 1):
        print(f"{i}. ID: {result['id']}, Score: {result['score']:.4f}")
        print(f"   Text: {result['text'][:100]}...")
    
    print("\n=== TIME-AWARE SEARCH RESULTS ===")
    
    for i, result in enumerate(temporal_results[:5], 1):
        # Extract original score if available
        original_score = result.get('original_score', 'N/A')
        temporal_position = result.get('temporal_position', 'N/A')
        
        print(f"{i}. ID: {result['id']}, Score: {result['score']:.4f}")
        if original_score != 'N/A':
            print(f"   Original: {original_score:.4f}, Position: {temporal_position:.2f}, Change: {result['score'] - original_score:+.4f}")
        print(f"   Text: {result['text'][:100]}...")
    
    # Analyze differences in result sets
    hybrid_ids = [r['id'] for r in hybrid_results]
    temporal_ids = [r['id'] for r in temporal_results]
    
    # Find items that moved up in ranking
    moved_up = []
    moved_down = []
    for i, doc_id in enumerate(temporal_ids):
        if doc_id in hybrid_ids:
            hybrid_rank = hybrid_ids.index(doc_id)
            temporal_rank = i
            if temporal_rank < hybrid_rank:
                moved_up.append((doc_id, hybrid_rank, temporal_rank))
            elif temporal_rank > hybrid_rank:
                moved_down.append((doc_id, hybrid_rank, temporal_rank))
    
    if moved_up:
        print("\n=== ITEMS RANKED HIGHER IN TIME-AWARE SEARCH ===")
        for doc_id, old_rank, new_rank in moved_up:
            print(f"ID: {doc_id} moved from #{old_rank+1} to #{new_rank+1} (+{old_rank-new_rank})")
    
    if moved_down:
        print("\n=== ITEMS RANKED LOWER IN TIME-AWARE SEARCH ===")
        for doc_id, old_rank, new_rank in moved_down:
            print(f"ID: {doc_id} moved from #{old_rank+1} to #{new_rank+1} ({old_rank-new_rank})")
    
    # Find completely new items
    new_items = [doc_id for doc_id in temporal_ids[:5] if doc_id not in hybrid_ids[:5]]
    if new_items:
        print("\n=== NEW ITEMS IN TOP 5 FOR TIME-AWARE SEARCH ===")
        for doc_id in new_items:
            idx = temporal_ids.index(doc_id)
            result = temporal_results[idx]
            print(f"ID: {doc_id}, Rank: #{idx+1}, Score: {result['score']:.4f}")
            print(f"Text: {result['text'][:100]}...")

def test_live_queries(args):
    """Run real comparison searches with both methods"""
    print("\n=== Testing Live Query Comparisons ===")
    
    # Load settings for MEMNON
    settings = load_settings()
    memnon_settings = settings["Agent Settings"]["MEMNON"]
    
    # Initialize MEMNON
    memnon = MEMNON(memnon_settings)
    
    early_queries = [
        "Tell me about the first meeting between Alex and Emilia",
        "How did Alex get involved with the cybernetics program at the beginning?",
        "What were the initial goals of the project?",
        "What was the first major challenge Alex faced?",
        "Describe the earliest signs of the conspiracy"
    ]
    
    recent_queries = [
        "What is Alex's current situation?",
        "What was the most recent development with Emilia?",
        "Tell me about the latest discoveries in the story",
        "What challenges is Alex facing now?",
        "Describe the current state of the cybernetics program"
    ]
    
    # Test early temporal queries
    early_query = args.early_query if args.early_query else early_queries[0]
    classification = temporal_search.classify_temporal_query(early_query)
    hybrid_results, temporal_results = run_comparison_query(memnon, early_query, args.boost_factor)
    display_results_comparison(hybrid_results, temporal_results, early_query, classification)
    
    # Test recent temporal queries
    recent_query = args.recent_query if args.recent_query else recent_queries[0]
    classification = temporal_search.classify_temporal_query(recent_query)
    hybrid_results, temporal_results = run_comparison_query(memnon, recent_query, args.boost_factor)
    display_results_comparison(hybrid_results, temporal_results, recent_query, classification)

def main():
    parser = argparse.ArgumentParser(description="Test temporal search functionality")
    parser.add_argument("--classification-only", action="store_true", help="Only test query classification")
    parser.add_argument("--boost-factor", type=float, default=0.5, help="Temporal boost factor (0.0-1.0)")
    parser.add_argument("--early-query", type=str, help="Custom early temporal query")
    parser.add_argument("--recent-query", type=str, help="Custom recent temporal query")
    args = parser.parse_args()
    
    # Always run classification test
    test_temporal_classification()
    
    # Always run temporal boost test
    test_temporal_boost()
    
    # Run live query tests unless classification-only is specified
    if not args.classification_only:
        test_live_queries(args)
    else:
        print("\nSkipping live query tests (--classification-only specified)")

if __name__ == "__main__":
    main()