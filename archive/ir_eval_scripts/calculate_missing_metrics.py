#!/usr/bin/env python3
"""
Calculate metrics for queries that have judgments but no metrics.

This script identifies queries that have relevance judgments but no
calculated metrics, then calculates and stores the metrics for them
using the most recent run.
"""

import os
import sys
import json
import sqlite3
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

def get_queries_with_judgments(db):
    """Get queries that have at least one judgment"""
    cursor = db.conn.cursor()
    cursor.execute('''
        SELECT DISTINCT q.id, q.text
        FROM queries q
        JOIN judgments j ON q.id = j.query_id
        WHERE (
            SELECT COUNT(*)
            FROM judgments
            WHERE query_id = q.id
        ) > 0
        ORDER BY q.id
    ''')
    return cursor.fetchall()

def get_queries_with_metrics(db):
    """Get queries that already have metrics calculated"""
    cursor = db.conn.cursor()
    cursor.execute('''
        SELECT DISTINCT query_id
        FROM metrics
        ORDER BY query_id
    ''')
    return [row['query_id'] for row in cursor.fetchall()]

def get_latest_run(db):
    """Get the most recent run from the database"""
    cursor = db.conn.cursor()
    cursor.execute('''
        SELECT id, name, timestamp
        FROM runs
        ORDER BY timestamp DESC
        LIMIT 1
    ''')
    return cursor.fetchone()

def get_results_for_query(db, run_id, query_id):
    """Get search results for a specific query from a run"""
    cursor = db.conn.cursor()
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
    
    return results

def get_judgments_for_query(db, query_id):
    """Get all judgments for a query"""
    cursor = db.conn.cursor()
    cursor.execute('''
        SELECT doc_id, relevance
        FROM judgments
        WHERE query_id = ?
    ''', (query_id,))
    
    judgments = {}
    for row in cursor.fetchall():
        judgments[row['doc_id']] = row['relevance']
    
    return judgments

def calculate_metrics_for_query(db, run_id, query_id):
    """Calculate and store metrics for a query"""
    # Get results and judgments
    results = get_results_for_query(db, run_id, query_id)
    judgments = get_judgments_for_query(db, query_id)
    
    if not results:
        logger.warning(f"No results found for query ID {query_id} in run {run_id}")
        return False
    
    if not judgments:
        logger.warning(f"No judgments found for query ID {query_id}")
        return False
    
    # Calculate metrics
    metrics = calculate_all_metrics(results, judgments)
    
    # Save metrics to database
    success = db.save_metrics(run_id, query_id, metrics)
    
    if success:
        logger.info(f"Saved metrics for query ID {query_id}")
    else:
        logger.error(f"Failed to save metrics for query ID {query_id}")
    
    return success

def main():
    db = IRDatabase()
    
    # Get queries with judgments
    queries_with_judgments = get_queries_with_judgments(db)
    logger.info(f"Found {len(queries_with_judgments)} queries with judgments")
    
    # Get queries that already have metrics
    queries_with_metrics = get_queries_with_metrics(db)
    logger.info(f"Found {len(queries_with_metrics)} queries with metrics: {queries_with_metrics}")
    
    # Find queries that need metrics calculated
    queries_needing_metrics = [q for q in queries_with_judgments 
                              if q['id'] not in queries_with_metrics]
    
    if not queries_needing_metrics:
        logger.info("No queries need metrics calculated")
        db.close()
        return 0
    
    logger.info(f"Found {len(queries_needing_metrics)} queries needing metrics calculated:")
    for q in queries_needing_metrics:
        logger.info(f"  Query {q['id']}: {q['text'][:50]}...")
    
    # Get the latest run
    latest_run = get_latest_run(db)
    if not latest_run:
        logger.error("No runs found in the database")
        db.close()
        return 1
    
    logger.info(f"Using latest run: ID {latest_run['id']}, Name: {latest_run['name']}")
    
    # Calculate metrics for each query
    success_count = 0
    for query in queries_needing_metrics:
        logger.info(f"Calculating metrics for query {query['id']}: {query['text'][:50]}...")
        success = calculate_metrics_for_query(db, latest_run['id'], query['id'])
        if success:
            success_count += 1
    
    logger.info(f"Successfully calculated metrics for {success_count}/{len(queries_needing_metrics)} queries")
    
    # Close the database connection
    db.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())