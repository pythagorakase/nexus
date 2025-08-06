#!/usr/bin/env python3
"""
Script to copy judgments between query pairs in IR evaluation database.

Usage:
    python copy_judgments.py [--source-to-target] [--target-to-source]

By default, copies from source to target if no flags are specified.
"""

import os
import sys
import argparse
import sqlite3
import logging
from typing import Dict, List, Tuple

# Add parent directory to path so we can import from ir_eval
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import IRDatabase, dict_factory

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("copy_judgments")

# Query pairs mapping (source_id: target_id)
QUERY_PAIRS = {
    1: 10,
    2: 11,
    3: 12,
    4: 13,
    5: 14,
    6: 15,
    7: 16,
    8: 17,
    9: 18,
    10: 19
}

def get_judgments_by_query_id(db_conn, query_id: int) -> Dict[str, int]:
    """Get all judgments for a query by its ID"""
    cursor = db_conn.cursor()
    cursor.execute(
        "SELECT doc_id, relevance, doc_text FROM judgments WHERE query_id = ?",
        (query_id,)
    )
    judgments = {row['doc_id']: (row['relevance'], row['doc_text']) for row in cursor.fetchall()}
    return judgments

def copy_judgments(db_path: str, source_to_target: bool = True) -> Tuple[int, int]:
    """
    Copy judgments between paired queries.
    
    Args:
        db_path: Path to the SQLite database
        source_to_target: If True, copy from source to target; if False, copy from target to source
        
    Returns:
        Tuple of (total copied, total errors)
    """
    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = dict_factory
    
    pairs = QUERY_PAIRS.items()
    if not source_to_target:
        # Reverse the mapping for target to source direction
        pairs = [(v, k) for k, v in QUERY_PAIRS.items()]
    
    total_copied = 0
    total_errors = 0
    
    for source_id, target_id in pairs:
        logger.info(f"Processing pair: {source_id} -> {target_id}")
        
        # Get all judgments for source query
        source_judgments = get_judgments_by_query_id(conn, source_id)
        if not source_judgments:
            logger.warning(f"No judgments found for query ID {source_id}")
            continue
            
        logger.info(f"Found {len(source_judgments)} judgments for query ID {source_id}")
        
        # Copy each judgment to target query
        cursor = conn.cursor()
        for doc_id, (relevance, doc_text) in source_judgments.items():
            try:
                # Check if judgment already exists
                cursor.execute(
                    "SELECT id FROM judgments WHERE query_id = ? AND doc_id = ?",
                    (target_id, doc_id)
                )
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing judgment
                    cursor.execute(
                        "UPDATE judgments SET relevance = ?, doc_text = ? WHERE id = ?",
                        (relevance, doc_text, existing['id'])
                    )
                    logger.info(f"Updated judgment for query {target_id}, doc {doc_id}, relevance {relevance}")
                else:
                    # Add new judgment
                    cursor.execute(
                        "INSERT INTO judgments (query_id, doc_id, relevance, doc_text) VALUES (?, ?, ?, ?)",
                        (target_id, doc_id, relevance, doc_text)
                    )
                    logger.info(f"Added judgment for query {target_id}, doc {doc_id}, relevance {relevance}")
                
                total_copied += 1
            except sqlite3.Error as e:
                logger.error(f"Error copying judgment for doc {doc_id}: {e}")
                total_errors += 1
    
    # Commit all changes
    conn.commit()
    conn.close()
    
    return total_copied, total_errors

def main():
    parser = argparse.ArgumentParser(description="Copy judgments between query pairs")
    parser.add_argument("--source-to-target", action="store_true", help="Copy from source to target")
    parser.add_argument("--target-to-source", action="store_true", help="Copy from target to source")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database")
    
    args = parser.parse_args()
    
    # Default direction is source to target
    direction = True
    if args.target_to_source:
        direction = False
    
    # Use default database path if not specified
    db_path = args.db_path
    if not db_path:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ir_eval.db")
    
    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}")
        return 1
    
    logger.info(f"Using database: {db_path}")
    logger.info(f"Direction: {'source -> target' if direction else 'target -> source'}")
    
    total_copied, total_errors = copy_judgments(db_path, direction)
    
    logger.info(f"Finished copying judgments. Total copied: {total_copied}, Errors: {total_errors}")
    return 0

if __name__ == "__main__":
    sys.exit(main())