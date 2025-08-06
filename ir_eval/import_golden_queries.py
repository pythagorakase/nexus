#!/usr/bin/env python3
"""
Import golden queries from golden_queries.json into PostgreSQL database.

This script reads the golden_queries.json file and imports all valid queries
into the ir_eval.queries table in the PostgreSQL database.
"""

import os
import sys
import json
import psycopg2
import logging
from typing import Dict, List, Any, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("ir_eval.import")

# Default paths
GOLDEN_QUERIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_queries.json")
if not os.path.exists(GOLDEN_QUERIES_PATH):
    # Try parent directory
    GOLDEN_QUERIES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "golden_queries.json")

def get_db_connection(db_name: str = "NEXUS", user: str = "pythagor") -> psycopg2.extensions.connection:
    """Connect to PostgreSQL database."""
    return psycopg2.connect(
        dbname=db_name,
        user=user,
        host="localhost"
    )

def extract_queries(golden_queries_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract all queries from the golden_queries.json file, ignoring query variations.
    
    Args:
        golden_queries_data: The parsed golden_queries.json data
        
    Returns:
        List of dictionaries with query info (query text, positives, negatives, category, name)
    """
    all_queries = []
    
    # Process each category of queries
    for category, queries in golden_queries_data.items():
        # Skip the settings section
        if category == "settings":
            continue
            
        # Skip non-dictionary entries
        if not isinstance(queries, dict):
            continue
            
        # Process each query in this category
        for name, info in queries.items():
            # Skip entries without a query field
            if not isinstance(info, dict) or "query" not in info:
                continue
                
            # Only use the main query (not variations)
            query_text = info["query"]
            
            # Skip empty queries
            if not query_text:
                continue
                
            # Extract other useful fields
            positives = info.get("positives", [])
            negatives = info.get("negatives", [])
            
            # Add to results
            all_queries.append({
                "category": category,
                "name": name,
                "query": query_text,
                "positives": positives,
                "negatives": negatives
            })
    
    return all_queries

def main() -> None:
    """Main entry point of the script."""
    # Load golden queries from JSON file
    try:
        with open(GOLDEN_QUERIES_PATH, 'r') as f:
            golden_queries_data = json.load(f)
        logger.info(f"Loaded golden queries from {GOLDEN_QUERIES_PATH}")
    except Exception as e:
        logger.error(f"Error loading golden queries: {e}")
        sys.exit(1)
    
    # Extract all valid queries
    queries = extract_queries(golden_queries_data)
    logger.info(f"Extracted {len(queries)} queries")
    
    # Connect to database
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info("Connected to database")
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        sys.exit(1)
    
    # Check if ir_eval schema exists, create tables if not
    try:
        # Check if schema exists
        cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'ir_eval'")
        if not cursor.fetchone():
            logger.info("ir_eval schema does not exist, creating from schema.sql")
            
            # Read schema definition
            schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pg_schema.sql")
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
                
            # Execute schema creation
            cursor.execute(schema_sql)
            conn.commit()
            logger.info("Created ir_eval schema and tables")
        else:
            logger.info("ir_eval schema already exists")
    except Exception as e:
        logger.error(f"Error creating schema: {e}")
        conn.close()
        sys.exit(1)
    
    # Import queries
    try:
        # Use upsert (INSERT ... ON CONFLICT) to handle existing queries
        for query in queries:
            # JSON serialize positives and negatives as text arrays
            positives_json = json.dumps(query.get("positives", []))
            negatives_json = json.dumps(query.get("negatives", []))
            
            cursor.execute(
                """
                INSERT INTO ir_eval.queries (text, category, name) 
                VALUES (%s, %s, %s)
                ON CONFLICT (text) DO UPDATE 
                SET category = EXCLUDED.category, name = EXCLUDED.name
                RETURNING id
                """,
                (query["query"], query["category"], query["name"])
            )
            
            query_id = cursor.fetchone()[0]
            
            # Store positives and negatives as metadata in a separate table if needed
            # This example just logs the ID
            logger.info(f"Imported query '{query['query']}' (ID: {query_id})")
            
        conn.commit()
        logger.info(f"Successfully imported {len(queries)} queries")
    except Exception as e:
        logger.error(f"Error importing queries: {e}")
        conn.rollback()
        conn.close()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()