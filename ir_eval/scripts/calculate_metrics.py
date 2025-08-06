#!/usr/bin/env python3
"""
Calculate metrics for all queries in a run.

This script calculates IR metrics for all queries in a run using the relevance judgments.

Usage:
    python calculate_metrics.py --run-id RUN_ID
"""

import os
import sys
import argparse
import logging
from typing import Dict, List, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import IRDatabase
from scripts.ir_metrics import calculate_all_metrics

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("calculate_metrics")

def get_query_ids_without_metrics(db: IRDatabase, run_id: int) -> List[int]:
    """
    Get query IDs that don't have metrics for the specified run.
    
    Args:
        db: IRDatabase instance
        run_id: Run ID to check
        
    Returns:
        List of query IDs without metrics
    """
    cursor = db.conn.cursor()
    
    # Get all query IDs for this run
    cursor.execute('''
    SELECT DISTINCT query_id
    FROM results
    WHERE run_id = ?
    ''', (run_id,))
    
    all_query_ids = [row['query_id'] for row in cursor.fetchall()]
    
    # Get query IDs that already have metrics
    cursor.execute('''
    SELECT DISTINCT query_id
    FROM metrics
    WHERE run_id = ?
    ''', (run_id,))
    
    metrics_query_ids = [row['query_id'] for row in cursor.fetchall()]
    
    # Get query IDs without metrics
    missing_metrics = [qid for qid in all_query_ids if qid not in metrics_query_ids]
    
    return missing_metrics

def calculate_metrics_for_query(db: IRDatabase, run_id: int, query_id: int) -> bool:
    """
    Calculate and store metrics for a specific query in a run.
    
    Args:
        db: IRDatabase instance
        run_id: Run ID
        query_id: Query ID
        
    Returns:
        True if successful, False otherwise
    """
    cursor = db.conn.cursor()
    
    # Get query text
    cursor.execute("SELECT text FROM queries WHERE id = ?", (query_id,))
    query_row = cursor.fetchone()
    if not query_row:
        logger.warning(f"Query with ID {query_id} not found")
        return False
    
    query_text = query_row['text']
    
    # Get results for this query
    cursor.execute('''
    SELECT doc_id, rank, score, vector_score, text_score, text, source
    FROM results
    WHERE run_id = ? AND query_id = ?
    ORDER BY rank
    ''', (run_id, query_id))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            "id": row['doc_id'],
            "score": float(row['score']) if row['score'] is not None else 0.0,
            "vector_score": float(row['vector_score']) if row['vector_score'] is not None else 0.0,
            "text_score": float(row['text_score']) if row['text_score'] is not None else 0.0,
            "text": row['text'],
            "source": row['source']
        })
    
    if not results:
        logger.warning(f"No results found for query ID {query_id} in run {run_id}")
        return False
    
    # Get judgments for this query
    cursor.execute('''
    SELECT doc_id, relevance
    FROM judgments
    WHERE query_id = ?
    ''', (query_id,))
    
    judgments = {}
    for row in cursor.fetchall():
        judgments[row['doc_id']] = row['relevance']
    
    if not judgments:
        logger.warning(f"No judgments found for query ID {query_id}")
        return False
    
    # Calculate metrics
    metrics = calculate_all_metrics(results, judgments)
    
    # Save metrics to database
    success = db.save_metrics(run_id, query_id, metrics)
    
    if success:
        logger.info(f"Saved metrics for query ID {query_id} ({query_text})")
    else:
        logger.error(f"Failed to save metrics for query ID {query_id}")
    
    return success

def main():
    parser = argparse.ArgumentParser(description="Calculate metrics for all queries in a run")
    parser.add_argument("--run-id", type=int, required=True, help="Run ID to calculate metrics for")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database")
    
    args = parser.parse_args()
    
    # Use default database path if not specified
    db_path = args.db_path
    if not db_path:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ir_eval.db")
    
    # Initialize database connection
    db = IRDatabase(db_path)
    
    # Get query IDs without metrics
    missing_query_ids = get_query_ids_without_metrics(db, args.run_id)
    
    if not missing_query_ids:
        logger.info(f"No queries missing metrics for run ID {args.run_id}")
        db.close()
        return 0
    
    logger.info(f"Found {len(missing_query_ids)} queries missing metrics for run ID {args.run_id}")
    
    # Calculate metrics for each query
    success_count = 0
    for query_id in missing_query_ids:
        if calculate_metrics_for_query(db, args.run_id, query_id):
            success_count += 1
    
    logger.info(f"Successfully calculated metrics for {success_count}/{len(missing_query_ids)} queries")
    
    # Close database connection
    db.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())