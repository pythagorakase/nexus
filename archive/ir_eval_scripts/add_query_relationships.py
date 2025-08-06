#!/usr/bin/env python3
"""
Add Query Relationships to IR Evaluation Database

This script adds a 'query_relationships' table to the IR evaluation database
and populates it with the existing query pairs (1→10, 2→11, etc.).

Usage:
    python add_query_relationships.py [--db-path PATH]
"""

import os
import sys
import sqlite3
import logging
import argparse
from typing import Dict, List, Tuple, Optional, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import IRDatabase, dict_factory

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("add_relationships")

# Initial query pairs to add
INITIAL_QUERY_PAIRS = [
    (1, 10, "variation"),
    (2, 11, "variation"),
    (3, 12, "variation"),
    (4, 13, "variation"),
    (5, 14, "variation"),
    (6, 15, "variation"),
    (7, 16, "variation"),
    (8, 17, "variation"),
    (9, 18, "variation"),
    (10, 19, "variation")
]

def add_relationship_table(db: IRDatabase) -> bool:
    """
    Add query_relationships table to the database.
    
    Args:
        db: IRDatabase instance
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cursor = db.conn.cursor()
        
        # Create the query_relationships table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS query_relationships (
            id INTEGER PRIMARY KEY,
            query1_id INTEGER NOT NULL,
            query2_id INTEGER NOT NULL,
            relationship_type TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY (query1_id) REFERENCES queries(id),
            FOREIGN KEY (query2_id) REFERENCES queries(id),
            UNIQUE(query1_id, query2_id, relationship_type)
        )
        ''')
        
        db.conn.commit()
        logger.info("Created query_relationships table")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error creating relationship table: {e}")
        db.conn.rollback()
        return False

def add_relationship(db: IRDatabase, query1_id: int, query2_id: int, 
                    relationship_type: str, description: Optional[str] = None) -> bool:
    """
    Add a relationship between two queries.
    
    Args:
        db: IRDatabase instance
        query1_id: ID of the first query
        query2_id: ID of the second query
        relationship_type: Type of relationship (e.g., 'variation')
        description: Optional description of the relationship
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if both queries exist
        cursor = db.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM queries WHERE id IN (?, ?)", 
                      (query1_id, query2_id))
        result = cursor.fetchone()
        
        if not result or result['count'] < 2:
            logger.warning(f"One or both queries not found: {query1_id}, {query2_id}")
            return False
        
        # Add relationship
        cursor.execute('''
        INSERT OR REPLACE INTO query_relationships
        (query1_id, query2_id, relationship_type, description)
        VALUES (?, ?, ?, ?)
        ''', (query1_id, query2_id, relationship_type, description))
        
        db.conn.commit()
        logger.info(f"Added relationship: {query1_id} → {query2_id} ({relationship_type})")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error adding relationship: {e}")
        db.conn.rollback()
        return False

def get_query_relationships(db: IRDatabase, query_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get all relationships or relationships for a specific query.
    
    Args:
        db: IRDatabase instance
        query_id: Optional ID of query to filter by
        
    Returns:
        List of relationship dictionaries
    """
    try:
        cursor = db.conn.cursor()
        
        if query_id is not None:
            # Get relationships for specific query
            cursor.execute('''
            SELECT r.*, 
                   q1.text as query1_text, 
                   q2.text as query2_text
            FROM query_relationships r
            JOIN queries q1 ON r.query1_id = q1.id
            JOIN queries q2 ON r.query2_id = q2.id
            WHERE r.query1_id = ? OR r.query2_id = ?
            ''', (query_id, query_id))
        else:
            # Get all relationships
            cursor.execute('''
            SELECT r.*, 
                   q1.text as query1_text, 
                   q2.text as query2_text
            FROM query_relationships r
            JOIN queries q1 ON r.query1_id = q1.id
            JOIN queries q2 ON r.query2_id = q2.id
            ''')
        
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error getting relationships: {e}")
        return []

def print_relationships(relationships: List[Dict[str, Any]]) -> None:
    """Print formatted relationships."""
    if not relationships:
        print("No relationships found")
        return
    
    print("\nQuery Relationships:")
    print("-" * 100)
    print(f"{'ID':<5} {'Query 1 ID':<10} {'Query 1 Text':<30} {'Query 2 ID':<10} {'Query 2 Text':<30} {'Type':<15}")
    print("-" * 100)
    
    for r in relationships:
        q1_text = r.get('query1_text', '')[:27] + '...' if len(r.get('query1_text', '')) > 30 else r.get('query1_text', '')
        q2_text = r.get('query2_text', '')[:27] + '...' if len(r.get('query2_text', '')) > 30 else r.get('query2_text', '')
        
        print(f"{r.get('id', ''):<5} {r.get('query1_id', ''):<10} {q1_text:<30} "
              f"{r.get('query2_id', ''):<10} {q2_text:<30} {r.get('relationship_type', ''):<15}")

def main():
    parser = argparse.ArgumentParser(description="Add query relationships to IR evaluation database")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database")
    parser.add_argument("--list-all", action="store_true", help="List all relationships")
    parser.add_argument("--add", nargs=3, metavar=('QUERY1_ID', 'QUERY2_ID', 'REL_TYPE'),
                        help="Add a single relationship (query1_id query2_id relationship_type)")
    
    args = parser.parse_args()
    
    # Use default database path if not specified
    db_path = args.db_path
    if not db_path:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ir_eval.db")
    
    # Initialize database connection
    db = IRDatabase(db_path)
    
    # Add relationship table if it doesn't exist
    if not add_relationship_table(db):
        db.close()
        return 1
    
    # Add a single relationship if specified
    if args.add:
        query1_id, query2_id, rel_type = args.add
        if add_relationship(db, int(query1_id), int(query2_id), rel_type):
            print(f"Added relationship: {query1_id} → {query2_id} ({rel_type})")
    # Otherwise add initial relationships
    else:
        # Add initial relationships
        success_count = 0
        for query1_id, query2_id, rel_type in INITIAL_QUERY_PAIRS:
            if add_relationship(db, query1_id, query2_id, rel_type):
                success_count += 1
        
        print(f"Added {success_count} of {len(INITIAL_QUERY_PAIRS)} relationships")
    
    # List all relationships if requested
    if args.list_all:
        relationships = get_query_relationships(db)
        print_relationships(relationships)
    
    # Close database connection
    db.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())