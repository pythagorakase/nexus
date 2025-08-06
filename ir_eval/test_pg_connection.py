#!/usr/bin/env python3
"""
Test PostgreSQL connection and schema for IR Evaluation System.

This script tests the connection to PostgreSQL and verifies that
the ir_eval schema and tables are accessible.
"""

import os
import sys
import logging
from pg_db import IRDatabasePG

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("ir_eval.test_connection")

def main():
    """Test PostgreSQL connection and schema."""
    try:
        # Connect to database
        logger.info("Connecting to PostgreSQL...")
        db = IRDatabasePG()
        
        # Test query functionality
        logger.info("Testing query functionality...")
        query_id = db.add_query("Test connection query", "test", "connection_test")
        logger.info(f"Added test query with ID: {query_id}")
        
        # Get it back to verify
        retrieved_id = db.get_query_id("Test connection query")
        logger.info(f"Retrieved query ID: {retrieved_id}")
        
        if retrieved_id == query_id:
            logger.info("Query retrieval successful!")
        else:
            logger.error(f"Query retrieval failed. Expected {query_id}, got {retrieved_id}")
            
        # Count tables in ir_eval schema
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'ir_eval'
        """)
        table_count = cursor.fetchone()[0]
        logger.info(f"IR Evaluation schema contains {table_count} tables")
        
        # List all tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'ir_eval'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Tables in ir_eval schema: {', '.join(tables)}")
        
        # Delete test query
        cursor.execute("DELETE FROM ir_eval.queries WHERE text = 'Test connection query'")
        db.conn.commit()
        logger.info("Deleted test query")
        
        # Verify deletion
        retrieved_id = db.get_query_id("Test connection query")
        if retrieved_id is None:
            logger.info("Delete verification successful!")
        else:
            logger.error(f"Delete failed. Query still exists with ID: {retrieved_id}")
        
        # Close connection
        cursor.close()
        db.close()
        logger.info("Database connection test completed successfully")
        
        return 0
    except Exception as e:
        logger.error(f"Error testing database connection: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    sys.exit(main())