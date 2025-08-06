#!/usr/bin/env python3
"""
Query Narrative Script for NEXUS

Queries the PostgreSQL database for narrative chunks using vector similarity search.

Usage:
    python query_narratives.py "query text" [--season SEASON] [--episode EPISODE] [--top-k TOP_K]

Example:
    python query_narratives.py "What happened with Alex in Night City?" --season 1 --top-k 5
"""

import os
import sys
from pathlib import Path
import argparse
import logging
import json

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
from letta.agent import Agent
from letta.schemas.agent import AgentState
from letta.schemas.memory import Memory
from letta.interfaces.utils import create_cli_interface

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
    
    # Create a simplified agent state for MEMNON
    agent_state = AgentState(
        id="memnon-query",
        name="MEMNON",
        memory=Memory(blocks=[]),
        system="MEMNON is a unified memory access system for the NEXUS narrative intelligence system.",
        tools=[],
        llm_config=None
    )
    
    # Initialize MEMNON agent
    # Using None for interface since we're using it directly, not through Letta's messaging
    memnon = MEMNON(
        interface=create_cli_interface(),
        agent_state=agent_state,
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
    results = memnon.query_by_text(args.query, filters, args.top_k)
    
    # Output results
    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print("No results found.")
            return
        
        print(f"Found {len(results)} results:\n")
        
        for i, result in enumerate(results):
            print(f"Result {i+1} (Score: {result['score']:.4f}):")
            print(f"Chunk ID: {result['chunk_id']}")
            print(f"Season: {result['metadata']['season']}, Episode: {result['metadata']['episode']}")
            print(f"Scene: {result['metadata'].get('scene_number', 'Unknown')}")
            print(f"Model scores: {result['model_scores']}")
            print("\nContent:")
            print("=" * 80)
            print(result['text'])
            print("=" * 80)
            print("\n")

if __name__ == "__main__":
    main()