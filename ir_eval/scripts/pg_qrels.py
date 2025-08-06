#!/usr/bin/env python3
"""
QRELS Manager for NEXUS IR Evaluation System (PostgreSQL Version)

This module provides a class to manage relevance judgments (qrels) using the PostgreSQL
database. It replaces the SQLite version with direct PostgreSQL access.

Usage:
    from scripts.pg_qrels import PGQRELSManager
    
    # Initialize
    qrels = PGQRELSManager()
    
    # Add judgments
    qrels.add_judgment("Who is Sullivan?", 12345, 3, "sullivan")
    
    # Get judgments for a query
    judgments = qrels.get_judgments_for_query("Who is Sullivan?")
"""

import os
import sys
import logging
from typing import Dict, List, Optional, Set, Any

# Ensure we can import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import PostgreSQL database manager
from pg_db import IRDatabasePG

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.pg_qrels")

class PGQRELSManager:
    """
    Manager for Query Relevance Judgments (QRELS) using PostgreSQL.
    
    Handles storage, retrieval, and management of relevance judgments
    for query-document pairs on a 0-3 scale:
    
    0 = Irrelevant
    1 = Marginally relevant
    2 = Relevant
    3 = Highly relevant
    """
    
    def __init__(self):
        """Initialize the QRELS Manager with PostgreSQL database."""
        self.db = IRDatabasePG()
        logger.info("Initialized PGQRELSManager with PostgreSQL database")
    
    def save(self) -> bool:
        """
        Save judgments to disk.
        
        This is a no-op with PostgreSQL since changes are already committed.
        
        Returns:
            Boolean indicating success
        """
        return True
    
    def add_judgment(self, query: str, chunk_id: int, relevance: int, 
                   category: str, doc_text: Optional[str] = None, 
                   justification: Optional[str] = None) -> bool:
        """
        Add a judgment for a query-document pair.
        
        Args:
            query: The query text
            chunk_id: The chunk ID (narrative_chunks.id)
            relevance: Relevance score (0-3)
            category: Query category (e.g., "character", "event")
            doc_text: Optional snippet of document text for reference
            justification: Optional AI reasoning for the judgment
            
        Returns:
            Boolean indicating success
        """
        # Validate relevance score
        if relevance not in [0, 1, 2, 3]:
            logger.error(f"Invalid relevance score {relevance}. Must be 0-3.")
            return False
        
        return self.db.add_judgment(query, chunk_id, relevance, category, doc_text, justification)
    
    def get_judgment(self, query: str, chunk_id: int) -> Optional[int]:
        """
        Get the relevance judgment for a specific query-document pair.
        
        Args:
            query: The query text
            chunk_id: The chunk ID (narrative_chunks.id)
            
        Returns:
            Relevance score (0-3) or None if no judgment exists
        """
        judgments = self.db.get_judgments_for_query(query)
        # Convert chunk_id to string for dictionary lookup
        return judgments.get(str(chunk_id))
    
    def get_judgments_for_query(self, query: str) -> Dict[str, int]:
        """
        Get all relevance judgments for a query.
        
        Args:
            query: The query text
            
        Returns:
            Dictionary of chunk IDs (as strings) to relevance scores
        """
        return self.db.get_judgments_for_query(query)
    
    def get_judged_documents(self, query: str) -> Set[str]:
        """
        Get the set of documents that have been judged for a query.
        
        Args:
            query: The query text
            
        Returns:
            Set of chunk IDs (as strings) that have been judged
        """
        return self.db.get_judged_documents(query)
    
    def get_queries(self) -> List[str]:
        """
        Get all queries that have judgments.
        
        Returns:
            List of query strings
        """
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("""
                SELECT DISTINCT q.text 
                FROM ir_eval.queries q 
                JOIN ir_eval.judgments j ON q.id = j.query_id
            """)
            queries = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return queries
        except Exception as e:
            logger.error(f"Error getting queries: {e}")
            return []
    
    def get_query_categories(self) -> Dict[str, str]:
        """
        Get categories for all queries.
        
        Returns:
            Dictionary mapping query text to category
        """
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("""
                SELECT q.text, q.category 
                FROM ir_eval.queries q 
                JOIN ir_eval.judgments j ON q.id = j.query_id
                GROUP BY q.text, q.category
            """)
            categories = {row[0]: row[1] for row in cursor.fetchall()}
            cursor.close()
            return categories
        except Exception as e:
            logger.error(f"Error getting query categories: {e}")
            return {}
    
    def get_judgment_count(self) -> int:
        """
        Get total number of judgments across all queries.
        
        Returns:
            Total judgment count
        """
        return self.db.get_judgment_count()