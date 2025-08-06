#!/usr/bin/env python3
"""
SQLite Database Module for NEXUS IR Evaluation System

This module provides database functions for storing and retrieving IR evaluation data.
"""

import os
import json
import sqlite3
import logging
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.ir_eval.db")

# Default database path
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ir_eval.db")

def dict_factory(cursor, row):
    """Factory to return rows as dictionaries"""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

class IRDatabase:
    """SQLite database manager for IR evaluation data"""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize the database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_tables()
    
    def _connect(self):
        """Establish database connection"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = dict_factory
            logger.info(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database: {e}")
            raise
    
    def _create_tables(self):
        """Create database tables if they don't exist"""
        try:
            cursor = self.conn.cursor()
            
            # Create Queries table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                category TEXT,
                name TEXT,
                UNIQUE(text)
            )
            ''')
            
            # Create Judgments table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS judgments (
                id INTEGER PRIMARY KEY,
                query_id INTEGER,
                doc_id TEXT NOT NULL,
                relevance INTEGER,
                doc_text TEXT,
                FOREIGN KEY (query_id) REFERENCES queries(id),
                UNIQUE(query_id, doc_id)
            )
            ''')
            
            # Create Runs table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                settings TEXT,
                description TEXT,
                config_type TEXT
            )
            ''')
            
            # Create Results table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY,
                run_id INTEGER,
                query_id INTEGER,
                doc_id TEXT NOT NULL,
                rank INTEGER,
                score REAL,
                vector_score REAL,
                text_score REAL,
                text TEXT,
                source TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id),
                FOREIGN KEY (query_id) REFERENCES queries(id)
            )
            ''')
            
            # Create Metrics table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY,
                run_id INTEGER,
                query_id INTEGER,
                p_at_5 REAL,
                p_at_10 REAL,
                mrr REAL,
                bpref REAL,
                judged_p_at_5 INTEGER,
                judged_p_at_10 INTEGER,
                judged_total INTEGER,
                unjudged_count INTEGER,
                FOREIGN KEY (run_id) REFERENCES runs(id),
                FOREIGN KEY (query_id) REFERENCES queries(id),
                UNIQUE(run_id, query_id)
            )
            ''')
            
            # Create Comparisons table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS comparisons (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                run_ids TEXT NOT NULL,
                run_names TEXT NOT NULL,
                best_run_id INTEGER,
                comparison_data TEXT,
                FOREIGN KEY (best_run_id) REFERENCES runs(id)
            )
            ''')
            
            # Create Run Pair Links table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS run_pair_links (
                id INTEGER PRIMARY KEY,
                control_run_id INTEGER NOT NULL,
                experiment_run_id INTEGER NOT NULL,
                description TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (control_run_id) REFERENCES runs(id),
                FOREIGN KEY (experiment_run_id) REFERENCES runs(id),
                UNIQUE(control_run_id, experiment_run_id)
            )
            ''')
            
            self.conn.commit()
            logger.info("Database tables created successfully")
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def get_query_id(self, query_text: str) -> Optional[int]:
        """Get query ID from text, creating if doesn't exist"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM queries WHERE text = ?", (query_text,))
            result = cursor.fetchone()
            
            if result:
                return result['id']
            return None
        except sqlite3.Error as e:
            logger.error(f"Error getting query ID: {e}")
            return None
    
    def add_query(self, text: str, category: str = None, name: str = None) -> Optional[int]:
        """Add a query to the database"""
        try:
            cursor = self.conn.cursor()
            
            # Check if query already exists
            existing_id = self.get_query_id(text)
            if existing_id:
                # Update category and name if provided
                if category or name:
                    updates = []
                    params = []
                    
                    if category:
                        updates.append("category = ?")
                        params.append(category)
                    
                    if name:
                        updates.append("name = ?")
                        params.append(name)
                    
                    if updates:
                        params.append(existing_id)
                        cursor.execute(f"UPDATE queries SET {', '.join(updates)} WHERE id = ?", params)
                        self.conn.commit()
                
                return existing_id
            
            # Add new query
            cursor.execute(
                "INSERT INTO queries (text, category, name) VALUES (?, ?, ?)",
                (text, category, name)
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error adding query: {e}")
            self.conn.rollback()
            return None
    
    def add_judgment(self, query_text: str, doc_id: str, relevance: int, 
                    category: str = None, doc_text: str = None) -> bool:
        """Add a relevance judgment"""
        try:
            # Get or create query
            query_id = self.get_query_id(query_text)
            if not query_id:
                query_id = self.add_query(query_text, category)
                if not query_id:
                    return False
            
            cursor = self.conn.cursor()
            
            # Check if judgment already exists
            cursor.execute(
                "SELECT id FROM judgments WHERE query_id = ? AND doc_id = ?",
                (query_id, doc_id)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Update existing judgment
                cursor.execute(
                    "UPDATE judgments SET relevance = ?, doc_text = ? WHERE id = ?",
                    (relevance, doc_text, existing['id'])
                )
            else:
                # Add new judgment
                cursor.execute(
                    "INSERT INTO judgments (query_id, doc_id, relevance, doc_text) VALUES (?, ?, ?, ?)",
                    (query_id, doc_id, relevance, doc_text)
                )
            
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding judgment: {e}")
            self.conn.rollback()
            return False
            
    def remove_judgment(self, query_text: str, doc_id: str) -> bool:
        """Remove a specific judgment"""
        try:
            query_id = self.get_query_id(query_text)
            if not query_id:
                return False
                
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM judgments WHERE query_id = ? AND doc_id = ?",
                (query_id, doc_id)
            )
            
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error removing judgment: {e}")
            self.conn.rollback()
            return False
    
    def get_judgments_for_query(self, query_text: str) -> Dict[str, int]:
        """Get all judgments for a query"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
            SELECT j.doc_id, j.relevance 
            FROM judgments j
            JOIN queries q ON j.query_id = q.id
            WHERE q.text = ?
            ''', (query_text,))
            
            judgments = {}
            for row in cursor.fetchall():
                judgments[row['doc_id']] = row['relevance']
            
            return judgments
        except sqlite3.Error as e:
            logger.error(f"Error getting judgments: {e}")
            return {}
    
    def get_judged_documents(self, query_text: str) -> Set[str]:
        """Get set of document IDs that have been judged for a query"""
        return set(self.get_judgments_for_query(query_text).keys())
    
    def get_judgment_count(self) -> int:
        """Get total number of judgments in the database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM judgments")
            result = cursor.fetchone()
            return result['count'] if result else 0
        except sqlite3.Error as e:
            logger.error(f"Error getting judgment count: {e}")
            return 0
    
    def add_run(self, name: str, settings: Dict[str, Any], config_type: str, 
                description: str = None) -> Optional[int]:
        """Add a new run to the database"""
        try:
            cursor = self.conn.cursor()
            timestamp = datetime.now().isoformat()
            settings_json = json.dumps(settings) if settings else None
            
            cursor.execute(
                "INSERT INTO runs (name, timestamp, settings, description, config_type) VALUES (?, ?, ?, ?, ?)",
                (name, timestamp, settings_json, description, config_type)
            )
            
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error adding run: {e}")
            self.conn.rollback()
            return None
    
    def save_results(self, run_id: int, query_results: List[Dict[str, Any]]) -> bool:
        """Save query results for a run"""
        try:
            cursor = self.conn.cursor()
            
            for query_data in query_results:
                query_text = query_data.get("query", "")
                category = query_data.get("category", "unknown")
                name = query_data.get("name", "unknown")
                
                # Get or create query
                query_id = self.get_query_id(query_text)
                if not query_id:
                    query_id = self.add_query(query_text, category, name)
                    if not query_id:
                        continue
                
                # Add results
                results = query_data.get("results", [])
                for rank, result in enumerate(results, 1):
                    doc_id = str(result.get("id", ""))
                    score = result.get("score", 0)
                    
                    # Explicitly convert vector_score to float
                    vector_score = result.get("vector_score")
                    if vector_score is not None:
                        try:
                            vector_score = float(vector_score)
                        except (ValueError, TypeError):
                            logger.warning(f"Could not convert vector_score {vector_score} to float")
                            vector_score = 0.0
                    
                    # Explicitly convert text_score to float
                    text_score = result.get("text_score")
                    if text_score is not None:
                        try:
                            text_score = float(text_score)
                            logger.debug(f"Text score for doc {doc_id}: {text_score}")
                        except (ValueError, TypeError):
                            logger.warning(f"Could not convert text_score {text_score} to float")
                            text_score = 0.0
                    else:
                        logger.warning(f"Text score missing for doc {doc_id}")
                    
                    # Log exact value and type for debugging
                    logger.info(f"TEXT SCORE DEBUG - doc_id={doc_id}, text_score={text_score}, type={type(text_score).__name__}")
                    
                    text = result.get("text", "")
                    source = result.get("source", "unknown")
                    
                    # Create a separate parameter for debugging
                    text_score_param = text_score
                    
                    # Debug the parameter that will be passed to the database
                    logger.info(f"SQL PARAM DEBUG - text_score_param={text_score_param}, type={type(text_score_param).__name__}")
                    
                    # Check the parameter list that will be passed to SQLite
                    params = (run_id, query_id, doc_id, rank, score, vector_score, text_score_param, text, source)
                    logger.info(f"SQL PARAM LIST - {[type(p).__name__ for p in params]}")
                    
                    # Simplified insertion that properly maintains float values
                    cursor.execute(
                        """
                        INSERT INTO results 
                        (run_id, query_id, doc_id, rank, score, vector_score, text_score, text, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (run_id, query_id, doc_id, rank, score, vector_score, text_score, text, source)
                    )
            
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error saving results: {e}")
            self.conn.rollback()
            return False
    
    def save_metrics(self, run_id: int, query_id: int, metrics: Dict[str, Any]) -> bool:
        """Save metrics for a query in a run"""
        try:
            cursor = self.conn.cursor()
            
            judged_counts = metrics.get("judged_counts", {})
            
            cursor.execute(
                """
                INSERT INTO metrics 
                (run_id, query_id, p_at_5, p_at_10, mrr, bpref, 
                judged_p_at_5, judged_p_at_10, judged_total, unjudged_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id, 
                    query_id, 
                    metrics.get("p@5", 0), 
                    metrics.get("p@10", 0),
                    metrics.get("mrr", 0), 
                    metrics.get("bpref", 0),
                    judged_counts.get("p@5", 0),
                    judged_counts.get("p@10", 0),
                    judged_counts.get("total", 0),
                    metrics.get("unjudged_count", 0)
                )
            )
            
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error saving metrics: {e}")
            self.conn.rollback()
            return False
    
    def save_comparison(self, run_ids: List[int], run_names: List[str], 
                       comparison_data: Dict[str, Any], best_run_id: int) -> Optional[int]:
        """Save a comparison between multiple runs"""
        try:
            cursor = self.conn.cursor()
            timestamp = datetime.now().isoformat()
            
            cursor.execute(
                """
                INSERT INTO comparisons 
                (timestamp, run_ids, run_names, best_run_id, comparison_data)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    json.dumps(run_ids),
                    json.dumps(run_names),
                    best_run_id,
                    json.dumps(comparison_data)
                )
            )
            
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Error saving comparison: {e}")
            self.conn.rollback()
            return None
    
    def get_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent runs, sorted by timestamp (newest first)"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM runs ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error getting runs: {e}")
            return []
    
    def get_run_results(self, run_id: int) -> List[Dict[str, Any]]:
        """Get all results for a run, grouped by query"""
        try:
            cursor = self.conn.cursor()
            
            # Get queries for this run
            cursor.execute(
                """
                SELECT DISTINCT q.* FROM queries q
                JOIN results r ON q.id = r.query_id
                WHERE r.run_id = ?
                """,
                (run_id,)
            )
            
            queries = cursor.fetchall()
            
            # For each query, get its results
            query_results = []
            for query in queries:
                cursor.execute(
                    """
                    SELECT * FROM results 
                    WHERE run_id = ? AND query_id = ?
                    ORDER BY rank
                    """,
                    (run_id, query['id'])
                )
                
                # Fetch all results
                all_rows = cursor.fetchall()
                
                # Debug the first few results to see what's coming from the database
                if len(all_rows) > 0:
                    first_row = all_rows[0]
                    print(f"DEBUG - First result for query {query['text'][:20]}...")
                    print(f"  vector_score: {first_row.get('vector_score')}")
                    print(f"  vector_score type: {type(first_row.get('vector_score')).__name__}")
                    print(f"  text_score: {first_row.get('text_score')}")
                    print(f"  text_score type: {type(first_row.get('text_score')).__name__}")
                    print(f"  score: {first_row.get('score')}")
                    print(f"  source: {first_row.get('source')}")
                    
                    # Print some raw SQL to see if the scores are there
                    cursor.execute(
                        """
                        SELECT vector_score, text_score FROM results 
                        WHERE run_id = ? AND query_id = ? 
                        LIMIT 1
                        """,
                        (run_id, query['id'])
                    )
                    raw_row = cursor.fetchone()
                    if raw_row:
                        print(f"  RAW SQL vector_score: {raw_row['vector_score']}")
                        print(f"  RAW SQL text_score: {raw_row['text_score']}")
                        print(f"  RAW SQL vector_score type: {type(raw_row['vector_score']).__name__}")
                        print(f"  RAW SQL text_score type: {type(raw_row['text_score']).__name__}")
                    
                    # Debug SQLite schema to understand column types
                    cursor.execute("PRAGMA table_info(results)")
                    columns = cursor.fetchall()
                    for col in columns:
                        if col['name'] in ['vector_score', 'text_score']:
                            print(f"  Column {col['name']} type in SQLite schema: {col['type']}")
                    
                results = []
                for r in all_rows:
                    # Convert vector_score to float explicitly
                    vector_score = r.get('vector_score')
                    if vector_score is not None:
                        try:
                            vector_score = float(vector_score)
                            # Check if it's a reasonable value (sanity check)
                            if vector_score < 0 or vector_score > 1:
                                print(f"WARNING: Vector score {vector_score} outside expected range [0,1]")
                        except (ValueError, TypeError):
                            print(f"WARNING: Could not convert vector_score '{vector_score}' (type: {type(vector_score).__name__}) to float")
                            vector_score = 0.0
                    else:
                        vector_score = 0.0
                        
                    # Convert text_score to float explicitly
                    text_score = r.get('text_score')
                    if text_score is not None:
                        try:
                            text_score = float(text_score)
                            # Check if it's a reasonable value (sanity check)
                            if text_score < 0 or text_score > 1:
                                print(f"WARNING: Text score {text_score} outside expected range [0,1]")
                        except (ValueError, TypeError):
                            print(f"WARNING: Could not convert text_score '{text_score}' (type: {type(text_score).__name__}) to float")
                            text_score = 0.0
                    else:
                        text_score = 0.0
                        
                    # Verify the value before adding to results
                    print(f"  Processed text_score for doc {r.get('doc_id')}: {text_score}")
                    
                    # Check if we can get the raw value and do a direct extraction
                    try:
                        cursor.execute(
                            """
                            SELECT text_score FROM results 
                            WHERE run_id = ? AND query_id = ? AND doc_id = ?
                            """,
                            (run_id, query['id'], r['doc_id'])
                        )
                        raw_result = cursor.fetchone()
                        if raw_result:
                            raw_text_score = raw_result['text_score']
                            print(f"  DIRECT DB text_score for doc {r.get('doc_id')}: {raw_text_score} (type: {type(raw_text_score).__name__})")
                            
                            # Override with the direct value if it exists and isn't zero
                            if raw_text_score is not None and raw_text_score != 0.0:
                                text_score = float(raw_text_score)
                                print(f"  USING DIRECT DB text_score: {text_score}")
                    except Exception as text_score_err:
                        print(f"  ERROR extracting direct text_score: {text_score_err}")
                        
                    results.append({
                        "id": r['doc_id'],
                        "score": float(r['score']) if r['score'] is not None else 0.0,
                        "vector_score": vector_score,
                        "text_score": text_score,
                        "text": r['text'],
                        "source": r['source']
                    })
                
                query_results.append({
                    "query": query['text'],
                    "category": query['category'],
                    "name": query['name'],
                    "results": results
                })
            
            return query_results
        except sqlite3.Error as e:
            logger.error(f"Error getting run results: {e}")
            return []
    
    def get_run_metrics(self, run_id: int) -> Dict[str, Any]:
        """Get all metrics for a run, with aggregation"""
        try:
            cursor = self.conn.cursor()
            
            # Get all metrics for this run
            cursor.execute(
                """
                SELECT m.*, q.text as query_text, q.category 
                FROM metrics m
                JOIN queries q ON m.query_id = q.id
                WHERE m.run_id = ?
                """,
                (run_id,)
            )
            
            metrics_rows = cursor.fetchall()
            
            # Structure metrics by query
            query_metrics = {}
            query_categories = {}
            
            for m in metrics_rows:
                query_text = m['query_text']
                query_metrics[query_text] = {
                    "p@5": m['p_at_5'],
                    "p@10": m['p_at_10'],
                    "mrr": m['mrr'],
                    "bpref": m['bpref'],
                    "judged_counts": {
                        "p@5": m['judged_p_at_5'],
                        "p@10": m['judged_p_at_10'],
                        "total": m['judged_total']
                    },
                    "unjudged_count": m['unjudged_count']
                }
                query_categories[query_text] = m['category']
            
            # Get run metadata
            cursor.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
            run = cursor.fetchone()
            
            if run:
                settings = json.loads(run['settings']) if run['settings'] else {}
                metadata = {
                    "timestamp": run['timestamp'],
                    "settings": settings
                }
            else:
                metadata = {"timestamp": "unknown", "settings": {}}
            
            # Calculate aggregated metrics
            try:
                # Try relative imports first 
                from scripts.ir_metrics import average_metrics_by_category
            except ImportError:
                # Try absolute imports as fallback
                import sys
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
                from ir_metrics import average_metrics_by_category
            
            # Calculate aggregated metrics
            aggregated = average_metrics_by_category(query_metrics, query_categories)
            
            return {
                "metadata": metadata,
                "by_query": query_metrics,
                "aggregated": aggregated,
                "query_categories": query_categories
            }
        except Exception as e:
            logger.error(f"Error getting run metrics: {e}")
            return {}
    
            
    def get_latest_run_ids(self, config_types: List[str]) -> Dict[str, Optional[int]]:
        """Get latest run ID for each config type"""
        result = {config_type: None for config_type in config_types}
        
        try:
            cursor = self.conn.cursor()
            
            for config_type in config_types:
                cursor.execute(
                    """
                    SELECT id FROM runs 
                    WHERE config_type = ? 
                    ORDER BY timestamp DESC 
                    LIMIT 1
                    """,
                    (config_type,)
                )
                
                run = cursor.fetchone()
                if run:
                    result[config_type] = run['id']
            
            return result
        except sqlite3.Error as e:
            logger.error(f"Error getting latest run IDs: {e}")
            return result
            
    def get_run_metadata(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific run"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
            run = cursor.fetchone()
            
            if run:
                # Parse settings JSON
                if run['settings']:
                    try:
                        run['settings'] = json.loads(run['settings'])
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in settings for run {run_id}")
                        run['settings'] = {}
                else:
                    run['settings'] = {}
                    
                return run
            return None
        except sqlite3.Error as e:
            logger.error(f"Error getting run metadata: {e}")
            return None
            
    def link_run_pair(self, control_run_id: int, experiment_run_id: int, description: str) -> bool:
        """Link control and experiment runs as a pair"""
        try:
            cursor = self.conn.cursor()
            timestamp = datetime.now().isoformat()
            
            cursor.execute(
                """
                INSERT OR REPLACE INTO run_pair_links 
                (control_run_id, experiment_run_id, description, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (control_run_id, experiment_run_id, description, timestamp)
            )
            
            self.conn.commit()
            logger.info(f"Linked runs {control_run_id} and {experiment_run_id} as a pair")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error linking run pair: {e}")
            self.conn.rollback()
            return False
            
    def get_run_pairs(self) -> List[Dict[str, Any]]:
        """Get all run pairs with their descriptions"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT 
                    p.id, 
                    p.control_run_id, 
                    p.experiment_run_id, 
                    p.description,
                    p.timestamp,
                    c.name as control_name,
                    e.name as experiment_name
                FROM 
                    run_pair_links p
                JOIN 
                    runs c ON p.control_run_id = c.id
                JOIN 
                    runs e ON p.experiment_run_id = e.id
                ORDER BY 
                    p.timestamp DESC
                """
            )
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error getting run pairs: {e}")
            return []
            
    def get_runs_with_unjudged_results(self, qrels) -> List[Dict[str, Any]]:
        """Get all runs that have unjudged results"""
        try:
            # Get all runs
            runs = self.get_runs()
            runs_with_unjudged = []
            
            for run in runs:
                # Get results for this run
                results = self.get_run_results(run['id'])
                
                # Check if any results are unjudged
                has_unjudged = False
                for query_data in results:
                    query_text = query_data.get("query", "")
                    judged_docs = qrels.get_judged_documents(query_text)
                    
                    for result in query_data.get("results", []):
                        doc_id = str(result.get("id", ""))
                        if doc_id not in judged_docs:
                            has_unjudged = True
                            break
                    
                    if has_unjudged:
                        break
                
                # If this run has unjudged results, add it to the list
                if has_unjudged:
                    runs_with_unjudged.append(run)
            
            return runs_with_unjudged
        except sqlite3.Error as e:
            logger.error(f"Error getting runs with unjudged results: {e}")
            return []