#!/usr/bin/env python3
"""
PostgreSQL Database Manager for NEXUS IR Evaluation System

This module provides a PostgreSQL database manager for the IR evaluation system,
replacing the SQLite implementation with direct PostgreSQL access.
"""

import os
import json
import logging
import psycopg2
import psycopg2.extras
import datetime
from typing import Dict, List, Any, Optional, Tuple, Set

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.ir_eval.pg_db")

class IRDatabasePG:
    """PostgreSQL database manager for IR evaluation data"""
    
    def __init__(self, dbname: str = "NEXUS", user: str = "pythagor", host: str = "localhost"):
        """
        Initialize the database connection.
        
        Args:
            dbname: PostgreSQL database name
            user: PostgreSQL user name
            host: PostgreSQL server hostname
        """
        self.connection_params = {
            "dbname": dbname,
            "user": user,
            "host": host
        }
        self.conn = None
        self._connect()
        self._ensure_schema()
    
    def _connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(**self.connection_params)
            psycopg2.extras.register_uuid()
            # Enable auto-conversion of arrays
            psycopg2.extensions.register_adapter(list, psycopg2.extras.Json)
            # Register JSONB adapter
            psycopg2.extensions.register_adapter(dict, psycopg2.extras.Json)
            logger.info(f"Connected to database: {self.connection_params['dbname']}")
        except psycopg2.Error as e:
            logger.error(f"Error connecting to database: {e}")
            raise
    
    def _ensure_schema(self):
        """Ensure the ir_eval schema exists"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'ir_eval'")
            if not cursor.fetchone():
                # Schema doesn't exist, create from schema file
                schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pg_schema.sql")
                with open(schema_path, 'r') as f:
                    schema_sql = f.read()
                cursor.execute(schema_sql)
                self.conn.commit()
                logger.info("Created ir_eval schema")
            cursor.close()
        except psycopg2.Error as e:
            logger.error(f"Error checking/creating schema: {e}")
            self.conn.rollback()
            raise
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def get_query_id(self, query_text: str) -> Optional[int]:
        """Get query ID from text, creating if it doesn't exist"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM ir_eval.queries WHERE text = %s", (query_text,))
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                return result[0]
            return None
        except psycopg2.Error as e:
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
                        updates.append("category = %s")
                        params.append(category)
                    
                    if name:
                        updates.append("name = %s")
                        params.append(name)
                    
                    if updates:
                        params.append(existing_id)
                        cursor.execute(f"UPDATE ir_eval.queries SET {', '.join(updates)} WHERE id = %s", params)
                        self.conn.commit()
                
                cursor.close()
                return existing_id
            
            # Add new query
            cursor.execute(
                "INSERT INTO ir_eval.queries (text, category, name) VALUES (%s, %s, %s) RETURNING id",
                (text, category, name)
            )
            query_id = cursor.fetchone()[0]
            self.conn.commit()
            cursor.close()
            return query_id
        except psycopg2.Error as e:
            logger.error(f"Error adding query: {e}")
            self.conn.rollback()
            return None
    
    def add_judgment(self, query_text: str, chunk_id: int, relevance: int, 
                    category: str = None, doc_text: str = None, justification: str = None) -> bool:
        """
        Add a relevance judgment
        
        Args:
            query_text: The query text
            chunk_id: The chunk ID
            relevance: Relevance score (0-3)
            category: Optional query category
            doc_text: Optional document text
            justification: Reasoning for the judgment from the AI
        """
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
                "SELECT id FROM ir_eval.judgments WHERE query_id = %s AND chunk_id = %s",
                (query_id, chunk_id)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Update existing judgment
                cursor.execute(
                    "UPDATE ir_eval.judgments SET relevance = %s, doc_text = %s, justification = %s WHERE id = %s",
                    (relevance, doc_text, justification, existing[0])
                )
            else:
                # Add new judgment
                cursor.execute(
                    "INSERT INTO ir_eval.judgments (query_id, chunk_id, relevance, doc_text, justification) VALUES (%s, %s, %s, %s, %s)",
                    (query_id, chunk_id, relevance, doc_text, justification)
                )
            
            self.conn.commit()
            cursor.close()
            return True
        except psycopg2.Error as e:
            logger.error(f"Error adding judgment: {e}")
            self.conn.rollback()
            return False
            
    def remove_judgment(self, query_text: str, chunk_id: int) -> bool:
        """Remove a specific judgment"""
        try:
            query_id = self.get_query_id(query_text)
            if not query_id:
                return False
                
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM ir_eval.judgments WHERE query_id = %s AND chunk_id = %s",
                (query_id, chunk_id)
            )
            
            self.conn.commit()
            cursor.close()
            return True
        except psycopg2.Error as e:
            logger.error(f"Error removing judgment: {e}")
            self.conn.rollback()
            return False
    
    def get_judgments_for_query(self, query_text: str) -> Dict[str, int]:
        """Get all judgments for a query"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
            SELECT j.chunk_id, j.relevance 
            FROM ir_eval.judgments j
            JOIN ir_eval.queries q ON j.query_id = q.id
            WHERE q.text = %s
            ''', (query_text,))
            
            judgments = {}
            for row in cursor.fetchall():
                # Convert chunk_id to string for consistent comparison
                judgments[str(row[0])] = row[1]
            
            cursor.close()
            return judgments
        except psycopg2.Error as e:
            logger.error(f"Error getting judgments: {e}")
            return {}
    
    def get_judged_documents(self, query_text: str) -> Set[str]:
        """Get set of chunk IDs that have been judged for a query"""
        return set(self.get_judgments_for_query(query_text).keys())
    
    def get_judgment_count(self) -> int:
        """Get total number of judgments in the database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ir_eval.judgments")
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else 0
        except psycopg2.Error as e:
            logger.error(f"Error getting judgment count: {e}")
            return 0
    
    def add_run(self, name: str, settings: Dict[str, Any], config_type: str, 
                description: str = None) -> Optional[int]:
        """Add a new run to the database"""
        try:
            cursor = self.conn.cursor()
            # Ensure settings is properly serialized to JSONB
            settings_json = psycopg2.extras.Json(settings) if settings else None
            
            cursor.execute(
                """
                INSERT INTO ir_eval.runs (name, settings, description, config_type) 
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (name, settings_json, description, config_type)
            )
            
            run_id = cursor.fetchone()[0]
            self.conn.commit()
            cursor.close()
            return run_id
        except psycopg2.Error as e:
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
                    chunk_id = result.get("id")
                    if not chunk_id:
                        logger.warning(f"Missing chunk_id in result for query: {query_text}")
                        continue
                        
                    score = result.get("score", 0)
                    
                    # Handle vector_score
                    vector_score = result.get("vector_score")
                    if vector_score is not None:
                        try:
                            vector_score = float(vector_score)
                        except (ValueError, TypeError):
                            logger.warning(f"Could not convert vector_score {vector_score} to float")
                            vector_score = 0.0
                    
                    # Handle text_score
                    text_score = result.get("text_score")
                    if text_score is not None:
                        try:
                            text_score = float(text_score)
                        except (ValueError, TypeError):
                            logger.warning(f"Could not convert text_score {text_score} to float")
                            text_score = 0.0
                    
                    text = result.get("text", "")
                    source = result.get("source", "unknown")
                    
                    # Extract timing data and metadata if available
                    elapsed_time = query_data.get("elapsed_time")
                    metadata = query_data.get("metadata")
                    
                    # Insert or update result
                    cursor.execute(
                        """
                        INSERT INTO ir_eval.results 
                        (run_id, query_id, chunk_id, rank, score, vector_score, text_score, text, source, elapsed_time, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (run_id, query_id, chunk_id) DO UPDATE 
                        SET rank = EXCLUDED.rank, 
                            score = EXCLUDED.score,
                            vector_score = EXCLUDED.vector_score,
                            text_score = EXCLUDED.text_score,
                            text = EXCLUDED.text,
                            source = EXCLUDED.source,
                            elapsed_time = EXCLUDED.elapsed_time,
                            metadata = EXCLUDED.metadata
                        """,
                        (run_id, query_id, chunk_id, rank, score, vector_score, text_score, text, source, 
                         elapsed_time, json.dumps(metadata) if metadata else None)
                    )
            
            self.conn.commit()
            cursor.close()
            return True
        except psycopg2.Error as e:
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
                INSERT INTO ir_eval.metrics 
                (run_id, query_id, p_at_5, p_at_10, mrr, bpref, 
                judged_p_at_5, judged_p_at_10, judged_total, unjudged_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, query_id) DO UPDATE
                SET p_at_5 = EXCLUDED.p_at_5,
                    p_at_10 = EXCLUDED.p_at_10,
                    mrr = EXCLUDED.mrr,
                    bpref = EXCLUDED.bpref,
                    judged_p_at_5 = EXCLUDED.judged_p_at_5,
                    judged_p_at_10 = EXCLUDED.judged_p_at_10,
                    judged_total = EXCLUDED.judged_total,
                    unjudged_count = EXCLUDED.unjudged_count
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
            cursor.close()
            return True
        except psycopg2.Error as e:
            logger.error(f"Error saving metrics: {e}")
            self.conn.rollback()
            return False
    
    def save_comparison(self, run_ids: List[int], run_names: List[str], 
                       comparison_data: Dict[str, Any], best_run_id: int) -> Optional[int]:
        """Save a comparison between multiple runs"""
        try:
            cursor = self.conn.cursor()
            
            # Convert lists to PostgreSQL arrays
            run_ids_array = psycopg2.extensions.AsIs(
                'ARRAY[' + ','.join(str(id) for id in run_ids) + ']::integer[]'
            )
            run_names_array = psycopg2.extensions.AsIs(
                'ARRAY[' + ','.join(f"'{name}'" for name in run_names) + ']::text[]'
            )
            
            cursor.execute(
                """
                INSERT INTO ir_eval.comparisons 
                (run_ids, run_names, best_run_id, comparison_data)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    run_ids_array,
                    run_names_array,
                    best_run_id,
                    psycopg2.extras.Json(comparison_data)
                )
            )
            
            comparison_id = cursor.fetchone()[0]
            self.conn.commit()
            cursor.close()
            return comparison_id
        except psycopg2.Error as e:
            logger.error(f"Error saving comparison: {e}")
            self.conn.rollback()
            return None
    
    def get_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent runs, sorted by timestamp (newest first)"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(
                "SELECT * FROM ir_eval.runs ORDER BY timestamp DESC LIMIT %s",
                (limit,)
            )
            runs = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return runs
        except psycopg2.Error as e:
            logger.error(f"Error getting runs: {e}")
            return []
    
    def get_run_results(self, run_id: int) -> List[Dict[str, Any]]:
        """Get all results for a run, grouped by query"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Get queries for this run
            cursor.execute(
                """
                SELECT DISTINCT q.* FROM ir_eval.queries q
                JOIN ir_eval.results r ON q.id = r.query_id
                WHERE r.run_id = %s
                """,
                (run_id,)
            )
            
            queries = [dict(row) for row in cursor.fetchall()]
            
            # For each query, get its results
            query_results = []
            for query in queries:
                cursor.execute(
                    """
                    SELECT * FROM ir_eval.results 
                    WHERE run_id = %s AND query_id = %s
                    ORDER BY rank
                    """,
                    (run_id, query['id'])
                )
                
                # Fetch all results
                result_rows = cursor.fetchall()
                
                # Debug the first result to see data format
                if result_rows and len(result_rows) > 0:
                    first_row = result_rows[0]
                    logger.debug(f"First result for query {query['text'][:20]}...")
                    logger.debug(f"  chunk_id: {first_row['chunk_id']}")
                    logger.debug(f"  score: {first_row['score']}")
                    logger.debug(f"  vector_score: {first_row['vector_score']}")
                    logger.debug(f"  text_score: {first_row['text_score']}")
                
                results = []
                for row in result_rows:
                    # Convert numeric values to float explicitly
                    vector_score = float(row['vector_score']) if row['vector_score'] is not None else None
                    text_score = float(row['text_score']) if row['text_score'] is not None else None
                    
                    results.append({
                        "id": row['chunk_id'],  # Use chunk_id as id
                        "score": float(row['score']) if row['score'] is not None else 0.0,
                        "vector_score": vector_score,
                        "text_score": text_score,
                        "text": row['text'],
                        "source": row['source']
                    })
                
                # Aggregate query-level data
                results_with_metadata = {
                    "query": query['text'],
                    "category": query['category'],
                    "name": query['name'],
                    "results": results
                }
                
                # Get timing information if available from first result
                first_result = result_rows[0] if result_rows else None
                if first_result and 'elapsed_time' in first_result and first_result['elapsed_time'] is not None:
                    results_with_metadata["elapsed_time"] = float(first_result['elapsed_time'])
                
                # Get metadata if available from first result
                if first_result and 'metadata' in first_result and first_result['metadata'] is not None:
                    try:
                        if isinstance(first_result['metadata'], str):
                            results_with_metadata["metadata"] = json.loads(first_result['metadata'])
                        else:
                            results_with_metadata["metadata"] = first_result['metadata']
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse metadata JSON for query: {query['text']}")
                
                query_results.append(results_with_metadata)
            
            cursor.close()
            return query_results
        except psycopg2.Error as e:
            logger.error(f"Error getting run results: {e}")
            return []
    
    def get_run_metrics(self, run_id: int) -> Dict[str, Any]:
        """Get all metrics for a run, with aggregation"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Get all metrics for this run
            cursor.execute(
                """
                SELECT m.*, q.text as query_text, q.category 
                FROM ir_eval.metrics m
                JOIN ir_eval.queries q ON m.query_id = q.id
                WHERE m.run_id = %s
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
            cursor.execute("SELECT * FROM ir_eval.runs WHERE id = %s", (run_id,))
            run = cursor.fetchone()
            
            if run:
                metadata = {
                    "timestamp": run['timestamp'].isoformat() if run['timestamp'] else None,
                    "settings": run['settings']
                }
            else:
                metadata = {"timestamp": "unknown", "settings": {}}
            
            cursor.close()
            
            # Local import of average_metrics_by_category
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
                    SELECT id FROM ir_eval.runs 
                    WHERE config_type = %s 
                    ORDER BY timestamp DESC 
                    LIMIT 1
                    """,
                    (config_type,)
                )
                
                run = cursor.fetchone()
                if run:
                    result[config_type] = run[0]
            
            cursor.close()
            return result
        except psycopg2.Error as e:
            logger.error(f"Error getting latest run IDs: {e}")
            return result
            
    def get_run_metadata(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific run"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT * FROM ir_eval.runs WHERE id = %s", (run_id,))
            run = cursor.fetchone()
            
            if run:
                # Convert to dict and handle timestamp
                run_dict = dict(run)
                if run_dict['timestamp']:
                    run_dict['timestamp'] = run_dict['timestamp'].isoformat()
                return run_dict
            
            cursor.close()
            return None
        except psycopg2.Error as e:
            logger.error(f"Error getting run metadata: {e}")
            return None
            
    def link_run_pair(self, control_run_id: int, experiment_run_id: int, description: str) -> bool:
        """Link control and experiment runs as a pair"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute(
                """
                INSERT INTO ir_eval.run_pair_links 
                (control_run_id, experiment_run_id, description)
                VALUES (%s, %s, %s)
                ON CONFLICT (control_run_id, experiment_run_id) 
                DO UPDATE SET description = EXCLUDED.description,
                              timestamp = CURRENT_TIMESTAMP
                """,
                (control_run_id, experiment_run_id, description)
            )
            
            self.conn.commit()
            cursor.close()
            logger.info(f"Linked runs {control_run_id} and {experiment_run_id} as a pair")
            return True
        except psycopg2.Error as e:
            logger.error(f"Error linking run pair: {e}")
            self.conn.rollback()
            return False
            
    def get_run_pairs(self) -> List[Dict[str, Any]]:
        """Get all run pairs with their descriptions"""
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
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
                    ir_eval.run_pair_links p
                JOIN 
                    ir_eval.runs c ON p.control_run_id = c.id
                JOIN 
                    ir_eval.runs e ON p.experiment_run_id = e.id
                ORDER BY 
                    p.timestamp DESC
                """
            )
            pairs = [dict(row) for row in cursor.fetchall()]
            
            # Convert timestamps to ISO format
            for pair in pairs:
                if pair['timestamp']:
                    pair['timestamp'] = pair['timestamp'].isoformat()
            
            cursor.close()
            return pairs
        except psycopg2.Error as e:
            logger.error(f"Error getting run pairs: {e}")
            return []
            
    def get_unjudged_counts(self, run_ids: List[int], qrels) -> Dict[int, int]:
        """
        Get the count of unjudged documents for each run.
        
        Args:
            run_ids: List of run IDs to check
            qrels: QRELSManager instance
            
        Returns:
            Dictionary mapping run_id to number of unjudged documents
        """
        try:
            # Create a fresh dictionary to store counts
            unjudged_counts = {}
            
            # Process each run ID separately
            for run_id in run_ids:
                # Get results for this run
                run_results = self.get_run_results(run_id)
                
                # Count unjudged documents
                total_unjudged = 0
                
                for query_data in run_results:
                    query_text = query_data.get("query", "")
                    judged_docs = qrels.get_judged_documents(query_text)
                    
                    # Count unjudged documents for this query
                    for result_item in query_data.get("results", []):
                        doc_id = str(result_item.get("id", ""))
                        if doc_id not in judged_docs:
                            total_unjudged += 1
                
                # Store count for this run using explicit integer key
                run_id_int = int(run_id)
                unjudged_counts[run_id_int] = total_unjudged
                logger.info(f"Run {run_id} has {total_unjudged} unjudged documents")
            
            return unjudged_counts
        except Exception as e:
            logger.error(f"Error getting unjudged counts: {e}")
            return {int(run_id): 0 for run_id in run_ids}
    
    def get_queries_by_category(self) -> Dict[str, List[Tuple[str, str, Dict[str, Any]]]]:
        """
        Get all queries from the database, grouped by category.
        
        Returns:
            Dictionary mapping category names to lists of (name, query_text, query_info) tuples
        """
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Get all queries with categories
            cursor.execute(
                """
                SELECT id, text, category, name 
                FROM ir_eval.queries 
                WHERE category IS NOT NULL
                ORDER BY category, name
                """
            )
            
            queries_by_category = {}
            
            for row in cursor.fetchall():
                category = row['category'] or 'uncategorized'
                name = row['name'] or f"query_{row['id']}"
                query_text = row['text']
                
                if category not in queries_by_category:
                    queries_by_category[category] = []
                
                # Create query info dict similar to what would be in golden_queries.json
                query_info = {
                    "query": query_text,
                    "id": row['id'],
                    "name": name,
                    "category": category
                }
                
                queries_by_category[category].append((name, query_text, query_info))
            
            cursor.close()
            return queries_by_category
            
        except psycopg2.Error as e:
            logger.error(f"Error getting queries by category: {e}")
            return {}
    
    def get_runs_with_unjudged_results(self, qrels) -> List[Dict[str, Any]]:
        """Get all runs that have unjudged results"""
        try:
            # Get all runs
            runs = self.get_runs(limit=20)  # Get up to 20 most recent runs
            runs_with_unjudged = []
            
            logger.info(f"Checking {len(runs)} runs for unjudged documents")
            
            for run in runs:
                run_id = run['id']
                # Get results for this run
                results = self.get_run_results(run_id)
                
                # Check if any results are unjudged
                has_unjudged = False
                unjudged_counts = {}
                
                for query_data in results:
                    query_text = query_data.get("query", "")
                    judged_docs = qrels.get_judged_documents(query_text)
                    
                    # Debug first few results and judgments to verify ID formats
                    if run_id in [1, 2]:  # Only for first couple of runs
                        doc_ids = [str(result.get("id", "")) for result in query_data.get("results", [])][:3]
                        judged_list = list(judged_docs)[:3] if judged_docs else []
                        logger.info(f"Run {run_id}, Query '{query_text}' - first doc IDs: {doc_ids}")
                        logger.info(f"First judged: {judged_list}")
                    
                    unjudged_count = 0
                    for result in query_data.get("results", []):
                        doc_id = str(result.get("id", ""))
                        if doc_id not in judged_docs:
                            has_unjudged = True
                            unjudged_count += 1
                    
                    if unjudged_count > 0:
                        unjudged_counts[query_text] = unjudged_count
                
                # If this run has unjudged results, add it to the list
                if has_unjudged:
                    logger.info(f"Run {run_id} ({run.get('name', '')}) has unjudged results: {unjudged_counts}")
                    runs_with_unjudged.append(run)
                else:
                    logger.info(f"Run {run_id} ({run.get('name', '')}) has NO unjudged results")
            
            return runs_with_unjudged
        except Exception as e:
            logger.error(f"Error getting runs with unjudged results: {e}")
            return []

# Import fix for ir_metrics
import sys
if __name__ == "__main__":
    # Add scripts directory to path
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))