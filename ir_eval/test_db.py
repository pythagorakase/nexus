#!/usr/bin/env python3
"""
Test script for the SQLite database implementation of the IR evaluation system.
"""

import os
import json
import logging
from db import IRDatabase
from scripts.qrels import QRELSManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_db")

def main():
    """Run tests for the database implementation."""
    # Use a test database file
    test_db_path = "test_ir_eval.db"
    
    # Remove test database if it exists
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        logger.info(f"Removed existing test database: {test_db_path}")
    
    # Initialize database
    db = IRDatabase(test_db_path)
    logger.info("Initialized test database")
    
    # Initialize QRELS manager
    qrels = QRELSManager(test_db_path)
    logger.info("Initialized QRELS manager")
    
    # Test adding queries
    query1_id = db.add_query("Who is Johnny Silverhand?", "character", "silverhand_query")
    query2_id = db.add_query("What happened at Arasaka Tower?", "event", "arasaka_event")
    logger.info(f"Added queries: {query1_id}, {query2_id}")
    
    # Test adding judgments
    qrels.add_judgment("Who is Johnny Silverhand?", "doc1", 3, "character", "Johnny Silverhand was a rockerboy...")
    qrels.add_judgment("Who is Johnny Silverhand?", "doc2", 2, "character", "The infamous terrorist...")
    qrels.add_judgment("Who is Johnny Silverhand?", "doc3", 1, "character", "Some tangential reference...")
    qrels.add_judgment("Who is Johnny Silverhand?", "doc4", 0, "character", "Unrelated document...")
    
    qrels.add_judgment("What happened at Arasaka Tower?", "doc5", 3, "event", "The bombing of Arasaka Tower...")
    qrels.add_judgment("What happened at Arasaka Tower?", "doc6", 2, "event", "The incident at Arasaka...")
    logger.info(f"Added judgments, total count: {qrels.get_judgment_count()}")
    
    # Test retrieving judgments
    judgments1 = qrels.get_judgments_for_query("Who is Johnny Silverhand?")
    logger.info(f"Retrieved judgments for query 1: {judgments1}")
    
    # Test adding a run
    run_settings = {
        "retrieval": {
            "hybrid_search": {
                "enabled": True,
                "vector_weight_default": 0.8,
                "text_weight_default": 0.2
            }
        }
    }
    
    run_id = db.add_run("Test Run", run_settings, "test", "Test run for database")
    logger.info(f"Added run with ID: {run_id}")
    
    # Test adding results
    query_results = [
        {
            "query": "Who is Johnny Silverhand?",
            "category": "character",
            "name": "silverhand_query",
            "results": [
                {"id": "doc1", "score": 0.95, "vector_score": 0.92, "text_score": 0.98, "text": "Johnny Silverhand was a rockerboy...", "source": "lore"},
                {"id": "doc2", "score": 0.85, "vector_score": 0.82, "text_score": 0.88, "text": "The infamous terrorist...", "source": "lore"},
                {"id": "doc3", "score": 0.65, "vector_score": 0.62, "text_score": 0.68, "text": "Some tangential reference...", "source": "lore"},
                {"id": "doc4", "score": 0.45, "vector_score": 0.42, "text_score": 0.48, "text": "Unrelated document...", "source": "lore"}
            ]
        },
        {
            "query": "What happened at Arasaka Tower?",
            "category": "event",
            "name": "arasaka_event",
            "results": [
                {"id": "doc5", "score": 0.92, "vector_score": 0.90, "text_score": 0.94, "text": "The bombing of Arasaka Tower...", "source": "lore"},
                {"id": "doc6", "score": 0.82, "vector_score": 0.80, "text_score": 0.84, "text": "The incident at Arasaka...", "source": "lore"}
            ]
        }
    ]
    
    success = db.save_results(run_id, query_results)
    logger.info(f"Saved results: {success}")
    
    # Test retrieving results
    results = db.get_run_results(run_id)
    logger.info(f"Retrieved {len(results)} queries with results")
    
    # Test calculating metrics
    try:
        # Import from local module
        from scripts.ir_metrics import calculate_all_metrics
        
        # Calculate metrics for first query
        metrics1 = calculate_all_metrics(query_results[0]["results"], judgments1)
        logger.info(f"Calculated metrics for query 1: {json.dumps(metrics1, indent=2)}")
        
        # Save metrics
        query1_id = db.get_query_id("Who is Johnny Silverhand?")
        db.save_metrics(run_id, query1_id, metrics1)
        logger.info("Saved metrics to database")
    except ImportError:
        logger.warning("Could not import ir_metrics module, skipping metrics calculation")
    
    # Test getting latest run IDs
    latest_runs = db.get_latest_run_ids(["test", "control", "experiment"])
    logger.info(f"Latest run IDs: {latest_runs}")
    
    # Close database connection
    db.close()
    logger.info("Database connection closed")
    
    # Cleanup
    os.remove(test_db_path)
    logger.info("Cleanup complete, test database removed")

if __name__ == "__main__":
    main()