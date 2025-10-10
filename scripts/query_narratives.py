#!/usr/bin/env python3
"""
Query Narrative Script for NEXUS

Queries the PostgreSQL database for narrative chunks using vector similarity search.

Usage:
    python query_narratives.py "query text" [--season SEASON] [--episode EPISODE] [--top-k TOP_K]

Example:
    python query_narratives.py "What happened with Alex in Night City?" --season 1 --top-k 5
"""

import argparse
import logging
import json
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("query_narratives.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("nexus.query")

# Add the project root to the path
sys.path.append(str(Path(__file__).parent.parent))

# Import MEMNON agent
from nexus.agents.memnon import MEMNON


class ConsoleInterface:
    """Minimal interface that mimics the subset of legacy CLI methods used by MEMNON."""

    def assistant_message(self, message: str) -> None:
        """Log assistant-style messages to stdout for compatibility."""

        logger.info(message)

def main():
    """
    Main entry point for the query script
    """
    parser = argparse.ArgumentParser(description="Query NEXUS narrative database")
    parser.add_argument("query", help="Text query to search for")
    parser.add_argument("--season", type=int, help="Filter by season number")
    parser.add_argument("--episode", type=int, help="Filter by episode number")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return (default: 5)")
    parser.add_argument("--db-url", dest="db_url", help="PostgreSQL database URL")
    parser.add_argument("--format", choices=["text", "json"], default="text", 
                        help="Output format (default: text)")
    args = parser.parse_args()
    
    # Initialize MEMNON agent in standalone mode
    memnon = MEMNON(
        interface=ConsoleInterface(),
        agent_state=None,
        user=None,
        db_url=args.db_url
    )
    
    # Prepare filters
    filters = {}
    if args.season is not None:
        filters["season"] = args.season
    if args.episode is not None:
        filters["episode"] = args.episode
    
    # Query the database
    logger.info(f"Querying with: {args.query}, filters: {filters}, top_k: {args.top_k}")
    response = memnon.query_memory(args.query, filters=filters or None, k=args.top_k)
    results = response.get("results", [])
    
    # Output results
    if args.format == "json":
        print(json.dumps(response, indent=2))
    else:
        if not results:
            print("No results found.")
            return
        
        print(f"Found {len(results)} results:\n")
        
        for i, result in enumerate(results):
            metadata = result.get('metadata', {})
            print(f"Result {i+1} (Score: {result.get('score', 0):.4f}):")
            print(f"Chunk ID: {result.get('chunk_id', 'unknown')}")
            print(f"Season: {metadata.get('season', 'Unknown')}, Episode: {metadata.get('episode', 'Unknown')}")
            print(f"Scene: {metadata.get('scene_number', 'Unknown')}")
            model_scores = result.get('model_scores') or result.get('model_weights')
            if model_scores:
                print(f"Model scores: {model_scores}")
            print("\nContent:")
            print("=" * 80)
            print(result.get('text', ''))
            print("=" * 80)
            print("\n")

if __name__ == "__main__":
    main()
