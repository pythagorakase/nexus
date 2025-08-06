#!/usr/bin/env python3
"""
Basic test script for refactored MEMNON

This script tests the basic functionality of the refactored MEMNON to verify
that it still works as expected after the modularization.
"""

import sys
import logging
import json
import time
from typing import Dict, List, Any, Optional

# Update this path if necessary to point to the MEMNON module
sys.path.append('/Users/pythagor/nexus')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("memnon_test")

# Import MEMNON
try:
    from nexus.agents.memnon.memnon import MEMNON
    logger.info("Successfully imported MEMNON")
except ImportError as e:
    logger.error(f"Failed to import MEMNON: {e}")
    sys.exit(1)

class DummyInterface:
    """
    A dummy interface for MEMNON to use during testing.
    Simply logs messages that would normally be sent to the user.
    """
    
    def __init__(self):
        self.messages = []
    
    def assistant_message(self, message: str):
        """Log a message that would be sent to the user."""
        logger.info(f"MEMNON message: {message}")
        self.messages.append(message)
        
    def get_messages(self):
        """Get all messages that have been sent."""
        return self.messages

def test_database_connection(db_url: str) -> bool:
    """Test that MEMNON can connect to the database."""
    logger.info("Testing database connection...")
    try:
        interface = DummyInterface()
        memnon = MEMNON(interface=interface, db_url=db_url)
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False

def test_query_analysis(memnon: MEMNON):
    """Test the query analysis functionality."""
    logger.info("Testing query analysis...")
    test_queries = [
        ("Who is Alex?", "character"),
        ("Where is the Night City Laboratory?", "location"),
        ("What happened at the meeting with Dr. Nyati?", "event"),
        ("How do Alex and Emilia feel about each other?", "relationship"),
        ("What are the major themes in Season 2?", "theme"),
        ("Tell me about the AI consciousness debate.", "general")
    ]
    
    results = []
    for query, expected_type in test_queries:
        logger.info(f"Analyzing query: '{query}', expected type: {expected_type}")
        query_info = memnon.query_analyzer.analyze_query(query)
        actual_type = query_info.get("type", "unknown")
        
        result = {
            "query": query,
            "expected_type": expected_type,
            "actual_type": actual_type,
            "correct": actual_type == expected_type
        }
        results.append(result)
        
        if actual_type == expected_type:
            logger.info(f"✓ Correctly identified as {actual_type}")
        else:
            logger.warning(f"✗ Incorrectly identified as {actual_type}, expected {expected_type}")
    
    correct_count = sum(1 for r in results if r["correct"])
    logger.info(f"Query analysis results: {correct_count}/{len(results)} correct")
    
    return results

def test_embedding_manager(memnon: MEMNON):
    """Test the embedding manager functionality."""
    logger.info("Testing embedding manager...")
    
    # Check available models
    available_models = memnon.embedding_manager.get_available_models()
    logger.info(f"Available models: {available_models}")
    
    if not available_models:
        logger.error("No embedding models available")
        return False
    
    # Test embedding generation with first available model
    test_model = available_models[0]
    test_text = "This is a test sentence for embedding generation."
    
    logger.info(f"Generating embedding with model '{test_model}'...")
    start_time = time.time()
    embedding = memnon.embedding_manager.generate_embedding(test_text, test_model)
    elapsed = time.time() - start_time
    
    if embedding is None:
        logger.error(f"Failed to generate embedding with model '{test_model}'")
        return False
    
    logger.info(f"Successfully generated {len(embedding)}D embedding in {elapsed:.3f}s")
    return True

def test_search_functionality(memnon: MEMNON):
    """Test search functionality with different strategies."""
    logger.info("Testing search functionality...")
    
    test_query = "Who is Alex?"
    
    # Test search with default settings
    logger.info(f"Testing default search with query: '{test_query}'")
    start_time = time.time()
    result = memnon.query_memory(test_query)
    elapsed = time.time() - start_time
    
    result_count = len(result.get("results", []))
    query_type = result.get("query_type", "unknown")
    strategies = result.get("metadata", {}).get("search_strategies", [])
    
    logger.info(f"Search completed in {elapsed:.3f}s")
    logger.info(f"Found {result_count} results")
    logger.info(f"Query classified as: {query_type}")
    logger.info(f"Search strategies used: {strategies}")
    
    # Test vector-only search
    logger.info(f"Testing vector-only search with query: '{test_query}'")
    start_time = time.time()
    vector_result = memnon.query_memory(test_query, use_hybrid=False)
    vector_elapsed = time.time() - start_time
    
    vector_result_count = len(vector_result.get("results", []))
    logger.info(f"Vector search completed in {vector_elapsed:.3f}s")
    logger.info(f"Found {vector_result_count} results")
    
    return {
        "default_search": {
            "time": elapsed,
            "result_count": result_count,
            "query_type": query_type,
            "strategies": strategies
        },
        "vector_search": {
            "time": vector_elapsed,
            "result_count": vector_result_count
        }
    }

def test_status_reporting(memnon: MEMNON):
    """Test status reporting functionality."""
    logger.info("Testing status reporting...")
    
    status = memnon._get_status()
    
    # Log some key parts of the status
    logger.info("Status report generated")
    
    # Find database info in status
    if "Database:" in status:
        db_line = next((line for line in status.split("\n") if line.startswith("Database:")), "")
        logger.info(db_line)
    
    # Find chunk counts
    if "Narrative chunks:" in status:
        chunks_line = next((line for line in status.split("\n") if line.startswith("Narrative chunks:")), "")
        logger.info(chunks_line)
    
    # Find embedding counts
    if "Embeddings:" in status:
        embeddings_line = next((line for line in status.split("\n") if line.startswith("Embeddings:")), "")
        logger.info(embeddings_line)
    
    return status

def run_all_tests(db_url: str = "postgresql://pythagor@localhost/NEXUS"):
    """Run all tests."""
    logger.info("Starting MEMNON refactoring tests...")
    
    test_results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "database_connection": None,
        "query_analysis": None,
        "embedding_manager": None,
        "search_functionality": None,
        "status_reporting": None
    }
    
    # Test database connection
    db_connection_result = test_database_connection(db_url)
    test_results["database_connection"] = db_connection_result
    
    if not db_connection_result:
        logger.error("Database connection failed, cannot continue testing")
        return test_results
    
    # Initialize MEMNON for further tests
    interface = DummyInterface()
    memnon = MEMNON(interface=interface, db_url=db_url)
    
    # Test query analysis
    test_results["query_analysis"] = test_query_analysis(memnon)
    
    # Test embedding manager
    test_results["embedding_manager"] = test_embedding_manager(memnon)
    
    # Test search functionality
    test_results["search_functionality"] = test_search_functionality(memnon)
    
    # Test status reporting
    test_results["status_reporting"] = test_status_reporting(memnon)
    
    logger.info("All tests completed")
    
    return test_results

if __name__ == "__main__":
    # Parse command line arguments for database URL
    import argparse
    parser = argparse.ArgumentParser(description="Test MEMNON refactored functionality")
    parser.add_argument("--db-url", default="postgresql://pythagor@localhost/NEXUS",
                        help="PostgreSQL database URL")
    parser.add_argument("--output", default=f"memnon_test_results_{time.strftime('%Y%m%d_%H%M%S')}.json",
                        help="Output file for test results")
    
    args = parser.parse_args()
    
    # Run tests
    results = run_all_tests(args.db_url)
    
    # Save results to file
    try:
        with open(args.output, "w") as f:
            # Convert non-serializable objects to strings
            serializable_results = json.dumps(results, default=str, indent=2)
            f.write(serializable_results)
        logger.info(f"Test results saved to {args.output}")
    except Exception as e:
        logger.error(f"Failed to save test results: {e}")
        # Print results to console as fallback
        print(json.dumps(results, default=str, indent=2))