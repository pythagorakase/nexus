#!/usr/bin/env python3
"""
MEMNON Debug Tester

This script tests the MEMNON agent's LLM-directed search capabilities
with a focus on ensuring the Sullivan search issue is fixed.
"""

import logging
import json
import time
from pathlib import Path

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("memnon_debug")

# Path to settings file
settings_path = Path("/Users/pythagor/nexus/settings.json")

# Load settings
with open(settings_path, 'r') as f:
    settings = json.load(f)

# Mock interface for testing
class MockInterface:
    def __init__(self):
        self.messages = []
    
    def assistant_message(self, message):
        logger.info(f"ASSISTANT: {message}")
        self.messages.append({"role": "assistant", "content": message})
    
    def user_message(self, message):
        logger.info(f"USER: {message}")
        self.messages.append({"role": "user", "content": message})

# Import the MEMNON agent
try:
    from nexus.agents.memnon.memnon import MEMNON
except ImportError:
    logger.error("Failed to import MEMNON. Make sure the module is available in the Python path.")
    exit(1)

def run_test(query, description=None):
    """Run a test query on MEMNON and print results."""
    logger.info("=" * 80)
    if description:
        logger.info(f"TEST: {description}")
    logger.info(f"QUERY: {query}")
    logger.info("-" * 80)
    
    try:
        # Create a new mock interface for this test
        interface = MockInterface()
        
        # Create a fresh MEMNON instance in direct mode
        start_time = time.time()
        logger.info("Initializing MEMNON agent...")
        agent = MEMNON(interface=interface, debug=True)
        init_time = time.time() - start_time
        logger.info(f"Initialization took {init_time:.2f}s")
        
        # Run the query
        start_time = time.time()
        logger.info("Executing query...")
        query_results = agent.query_memory(query=query, k=10)
        query_time = time.time() - start_time
        logger.info(f"Query execution took {query_time:.2f}s")
        
        # Print search plan
        search_plan = query_results.get("metadata", {}).get("search_plan", "No search plan")
        logger.info(f"Search plan: {search_plan}")
        
        # Print strategies used
        strategies = query_results.get("metadata", {}).get("strategies_executed", [])
        logger.info(f"Strategies used: {', '.join(strategies)}")
        
        # Print result stats
        results = query_results.get("results", [])
        logger.info(f"Found {len(results)} results")
        
        # Check for Sullivan presence
        sullivan_count = 0
        for result in results:
            text = result.get("text", "").lower()
            if "sullivan" in text:
                sullivan_count += 1
        
        logger.info(f"Results containing 'Sullivan': {sullivan_count}")
        
        # Print top 3 results
        logger.info("Top results:")
        for i, result in enumerate(results[:3]):
            logger.info(f"[{i+1}] Score: {result.get('score', 0):.3f}, Source: {result.get('source', 'unknown')}")
            
            # Print snippets (truncated)
            text = result.get("text", "")
            if len(text) > 200:
                text = text[:200] + "..."
            logger.info(f"    {text}")
            
            # Print relevance info if available
            if "relevance" in result:
                matches = result["relevance"].get("matches", [])
                logger.info(f"    Matches: {', '.join(matches)}")
        
        return query_results
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return None

def main():
    """Run all tests."""
    logger.info("Starting MEMNON debug tests")
    
    # Test 1: Basic Sullivan query
    run_test("Tell me about Sullivan", "Basic Sullivan Query")
    
    # Test 2: Sullivan relationship query
    run_test("What is the relationship between Alex and Sullivan?", "Sullivan Relationship Query")
    
    # Test 3: Sullivan characteristics query
    run_test("What does Sullivan look like?", "Sullivan Characteristics Query")
    
    # Test 4: Query with the word cat
    run_test("Tell me about Sullivan the cat", "Sullivan Cat Query")
    
    logger.info("All tests completed.")

if __name__ == "__main__":
    main()