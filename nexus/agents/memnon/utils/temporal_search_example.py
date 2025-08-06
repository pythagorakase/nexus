#!/usr/bin/env python3
"""
Simple example demonstrating the use of the time-aware search functionality.
"""

import sys
import json
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("temporal_search_example")

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parents[3]))

# Import the relevant modules
from nexus.agents.memnon.utils.temporal_search import (
    classify_temporal_query, 
    execute_time_aware_search
)

# Load settings
def load_settings():
    """Load database settings from settings.json"""
    try:
        with open(Path.cwd() / "settings.json", "r") as f:
            data = json.load(f)
            return data.get("Agent Settings", {}).get("MEMNON", {})
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return {}

def main():
    """Run a simple example of time-aware search"""
    # Load settings
    settings = load_settings()
    if not settings:
        logger.error("Failed to load settings")
        return
    
    # Get database URL
    db_url = settings.get("database", {}).get("url")
    if not db_url:
        logger.error("Database URL not found in settings")
        return
    
    # Example queries
    early_query = "What was the first encounter between Alex and Emilia?"
    recent_query = "What are the latest developments with the neural implant?"
    
    # Process each query
    for query in [early_query, recent_query]:
        # Classify the query
        classification = classify_temporal_query(query)
        print(f"\nQuery: '{query}'")
        print(f"Classification: {classification}")
        
        # Only proceed with temporal queries
        if classification == "non_temporal":
            print("This is not a temporal query, skipping search")
            continue
        
        # In a real application, you would get the query embedding here
        # For this example, we'll skip the actual search execution
        print(f"Would execute time-aware search with classification: {classification}")
        print("Parameters would include:")
        print(f"  - Database URL: {db_url}")
        print(f"  - Temporal classification: {classification}")
        print(f"  - Temporal boost factor: 0.5 (default)")
        
        # The actual search would be:
        # 
        # # Generate embedding
        # query_embedding = generate_embedding(query)
        # 
        # # Execute time-aware search
        # results = execute_time_aware_search(
        #     db_url=db_url,
        #     query_text=query,
        #     query_embedding=query_embedding,
        #     model_key="your-model-key",
        #     temporal_boost_factor=0.5
        # )
        # 
        # # Process results
        # for result in results:
        #     print(f"ID: {result['id']}, Score: {result['score']}")
        #     print(f"Text: {result['text'][:100]}...")

if __name__ == "__main__":
    main()