#!/usr/bin/env python3
"""
QRELS Manager for NEXUS IR Evaluation System (SQLite Version)

This module provides a class to manage relevance judgments (qrels) for the NEXUS
information retrieval evaluation system. It stores query-document relevance judgments,
allows adding new judgments, and retrieving judgments for analysis.

Usage:
    from scripts.qrels import QRELSManager
    
    # Initialize
    qrels = QRELSManager()
    
    # Add judgments
    qrels.add_judgment("Who is Sullivan?", "12345", 3, "sullivan")
    
    # Get judgments for a query
    judgments = qrels.get_judgments_for_query("Who is Sullivan?")
"""

import os
import logging
from typing import Dict, List, Optional, Set, Any
import sys

# Ensure we can import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import SQLite database manager
from db import IRDatabase, DEFAULT_DB_PATH

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.qrels")

class QRELSManager:
    """
    Manager for Query Relevance Judgments (QRELS).
    
    Handles storage, retrieval, and management of relevance judgments
    for query-document pairs on a 0-3 scale:
    
    0 = Irrelevant
    1 = Marginally relevant
    2 = Relevant
    3 = Highly relevant
    """
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize the QRELS Manager.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db = IRDatabase(db_path)
        logger.info(f"Initialized QRELSManager with database: {db_path}")
    
    def save(self) -> bool:
        """
        Save judgments to disk.
        
        Returns:
            Boolean indicating success
        """
        # SQLite automatically saves changes, so this is just a placeholder for compatibility
        return True
    
    def add_judgment(self, query: str, doc_id: str, relevance: int, 
                   category: str, doc_text: Optional[str] = None) -> bool:
        """
        Add a judgment for a query-document pair.
        
        Args:
            query: The query text
            doc_id: The document identifier
            relevance: Relevance score (0-3)
            category: Query category (e.g., "character", "event")
            doc_text: Optional snippet of document text for reference
            
        Returns:
            Boolean indicating success
        """
        # Validate relevance score
        if relevance not in [0, 1, 2, 3]:
            logger.error(f"Invalid relevance score {relevance}. Must be 0-3.")
            return False
        
        return self.db.add_judgment(query, doc_id, relevance, category, doc_text)
    
    def get_judgment(self, query: str, doc_id: str) -> Optional[int]:
        """
        Get the relevance judgment for a specific query-document pair.
        
        Args:
            query: The query text
            doc_id: The document identifier
            
        Returns:
            Relevance score (0-3) or None if no judgment exists
        """
        judgments = self.db.get_judgments_for_query(query)
        return judgments.get(doc_id)
    
    def get_judgments_for_query(self, query: str) -> Dict[str, int]:
        """
        Get all relevance judgments for a query.
        
        Args:
            query: The query text
            
        Returns:
            Dictionary of document IDs to relevance scores
        """
        return self.db.get_judgments_for_query(query)
    
    def get_judged_documents(self, query: str) -> Set[str]:
        """
        Get the set of documents that have been judged for a query.
        
        Args:
            query: The query text
            
        Returns:
            Set of document IDs that have been judged
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
                FROM queries q 
                JOIN judgments j ON q.id = j.query_id
            """)
            return [row['text'] for row in cursor.fetchall()]
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
                FROM queries q 
                JOIN judgments j ON q.id = j.query_id
                GROUP BY q.text
            """)
            return {row['text']: row['category'] for row in cursor.fetchall()}
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