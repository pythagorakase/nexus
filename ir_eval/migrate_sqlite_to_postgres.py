#!/usr/bin/env python3
"""
Migrate IR Evaluation data from SQLite to PostgreSQL.

This script imports existing judgments, runs, and metrics from
the SQLite database into the PostgreSQL database.
"""

import os
import sys
import json
import sqlite3
import logging
from pg_db import IRDatabasePG
from typing import Dict, List, Any, Optional, Tuple

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("ir_eval.migrate")

# Default SQLite database path
DEFAULT_SQLITE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ir_eval.db")

def dict_factory(cursor, row):
    """Factory to return rows as dictionaries"""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

def connect_sqlite(db_path: str) -> sqlite3.Connection:
    """Connect to SQLite database."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = dict_factory
        logger.info(f"Connected to SQLite database: {db_path}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to SQLite database: {e}")
        raise

def migrate_queries(sqlite_conn: sqlite3.Connection, pg_db: IRDatabasePG) -> Dict[int, int]:
    """
    Migrate queries from SQLite to PostgreSQL.
    
    Returns:
        Dictionary mapping SQLite query IDs to PostgreSQL query IDs
    """
    query_id_map = {}
    
    try:
        # Get all queries from SQLite
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute("SELECT id, text, category, name FROM queries")
        queries = sqlite_cursor.fetchall()
        
        logger.info(f"Found {len(queries)} queries in SQLite database")
        
        # Insert each query into PostgreSQL
        for query in queries:
            pg_query_id = pg_db.add_query(query['text'], query['category'], query['name'])
            if pg_query_id:
                query_id_map[query['id']] = pg_query_id
                logger.debug(f"Migrated query {query['id']} -> {pg_query_id}: {query['text'][:30]}")
        
        logger.info(f"Migrated {len(query_id_map)} queries to PostgreSQL")
        return query_id_map
    except Exception as e:
        logger.error(f"Error migrating queries: {e}")
        return {}

def migrate_judgments(sqlite_conn: sqlite3.Connection, pg_db: IRDatabasePG, query_id_map: Dict[int, int]) -> int:
    """
    Migrate judgments from SQLite to PostgreSQL.
    
    Args:
        sqlite_conn: SQLite connection
        pg_db: PostgreSQL database manager
        query_id_map: Mapping from SQLite to PostgreSQL query IDs
        
    Returns:
        Number of judgments migrated
    """
    try:
        # Get all judgments from SQLite
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute("""
        SELECT j.id, j.query_id, j.doc_id, j.relevance, j.doc_text, q.text as query_text, q.category 
        FROM judgments j
        JOIN queries q ON j.query_id = q.id
        """)
        judgments = sqlite_cursor.fetchall()
        
        logger.info(f"Found {len(judgments)} judgments in SQLite database")
        
        # Create a PostgreSQL cursor for batch inserts
        pg_cursor = pg_db.conn.cursor()
        
        # Insert each judgment into PostgreSQL with chunk_id (handles string conversion)
        migrated_count = 0
        for judgment in judgments:
            sqlite_query_id = judgment['query_id']
            if sqlite_query_id not in query_id_map:
                logger.warning(f"Skipping judgment with unknown query ID: {sqlite_query_id}")
                continue
                
            pg_query_id = query_id_map[sqlite_query_id]
            doc_id = judgment['doc_id']
            
            # Convert doc_id to int if it's a string
            try:
                chunk_id = int(doc_id)
            except (ValueError, TypeError):
                logger.warning(f"Skipping judgment with invalid chunk_id: {doc_id}")
                continue
            
            # Insert judgment into PostgreSQL
            pg_cursor.execute(
                """
                INSERT INTO ir_eval.judgments (query_id, chunk_id, relevance, doc_text)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (query_id, chunk_id) DO UPDATE 
                SET relevance = EXCLUDED.relevance,
                    doc_text = EXCLUDED.doc_text
                """,
                (pg_query_id, chunk_id, judgment['relevance'], judgment['doc_text'])
            )
            migrated_count += 1
        
        # Commit the transaction
        pg_db.conn.commit()
        logger.info(f"Migrated {migrated_count} judgments to PostgreSQL")
        return migrated_count
    except Exception as e:
        logger.error(f"Error migrating judgments: {e}")
        pg_db.conn.rollback()
        return 0

def migrate_runs(sqlite_conn: sqlite3.Connection, pg_db: IRDatabasePG, query_id_map: Dict[int, int]) -> Dict[int, int]:
    """
    Migrate runs and their results from SQLite to PostgreSQL.
    
    Args:
        sqlite_conn: SQLite connection
        pg_db: PostgreSQL database manager
        query_id_map: Mapping from SQLite to PostgreSQL query IDs
        
    Returns:
        Dictionary mapping SQLite run IDs to PostgreSQL run IDs
    """
    run_id_map = {}
    
    try:
        # Get all runs from SQLite
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute("SELECT id, name, timestamp, settings, description, config_type FROM runs")
        runs = sqlite_cursor.fetchall()
        
        logger.info(f"Found {len(runs)} runs in SQLite database")
        
        # Process each run
        for run in runs:
            # Parse settings JSON
            settings = json.loads(run['settings']) if run['settings'] else {}
            
            # Add run to PostgreSQL
            pg_run_id = pg_db.add_run(
                run['name'],
                settings,
                run['config_type'],
                run['description']
            )
            
            if not pg_run_id:
                logger.warning(f"Failed to migrate run {run['id']}: {run['name']}")
                continue
                
            run_id_map[run['id']] = pg_run_id
            logger.debug(f"Migrated run {run['id']} -> {pg_run_id}: {run['name']}")
            
            # Get results for this run
            sqlite_cursor.execute(
                """
                SELECT * FROM results 
                WHERE run_id = ?
                ORDER BY query_id, rank
                """, 
                (run['id'],)
            )
            results = sqlite_cursor.fetchall()
            
            # Group results by query
            query_results = {}
            for result in results:
                sqlite_query_id = result['query_id']
                if sqlite_query_id not in query_id_map:
                    logger.warning(f"Skipping result with unknown query ID: {sqlite_query_id}")
                    continue
                    
                if sqlite_query_id not in query_results:
                    # Get query info
                    sqlite_cursor.execute("SELECT text, category, name FROM queries WHERE id = ?", (sqlite_query_id,))
                    query_info = sqlite_cursor.fetchone()
                    
                    if not query_info:
                        logger.warning(f"Could not find query info for ID: {sqlite_query_id}")
                        continue
                    
                    query_results[sqlite_query_id] = {
                        "query": query_info['text'],
                        "category": query_info['category'],
                        "name": query_info['name'],
                        "results": []
                    }
                
                # Convert doc_id to int if it's a string
                try:
                    chunk_id = int(result['doc_id'])
                except (ValueError, TypeError):
                    logger.warning(f"Skipping result with invalid chunk_id: {result['doc_id']}")
                    continue
                
                # Add result to the appropriate query group
                query_results[sqlite_query_id]["results"].append({
                    "id": chunk_id,  # Use as int
                    "score": result['score'],
                    "vector_score": result['vector_score'],
                    "text_score": result['text_score'],
                    "text": result['text'],
                    "source": result['source']
                })
            
            # Save results for this run
            if query_results:
                success = pg_db.save_results(pg_run_id, list(query_results.values()))
                if success:
                    logger.info(f"Migrated {sum(len(q['results']) for q in query_results.values())} results for run {pg_run_id}")
                else:
                    logger.warning(f"Failed to migrate results for run {pg_run_id}")
        
        # Migrate run pairs
        sqlite_cursor.execute("""
        SELECT id, control_run_id, experiment_run_id, description, timestamp 
        FROM run_pair_links
        """)
        run_pairs = sqlite_cursor.fetchall()
        
        for pair in run_pairs:
            if pair['control_run_id'] in run_id_map and pair['experiment_run_id'] in run_id_map:
                pg_control_id = run_id_map[pair['control_run_id']]
                pg_experiment_id = run_id_map[pair['experiment_run_id']]
                
                pg_db.link_run_pair(pg_control_id, pg_experiment_id, pair['description'])
                logger.debug(f"Migrated run pair: {pg_control_id} - {pg_experiment_id}")
        
        # Migrate metrics
        for sqlite_run_id, pg_run_id in run_id_map.items():
            # Get metrics for this run
            sqlite_cursor.execute("""
            SELECT * FROM metrics WHERE run_id = ?
            """, (sqlite_run_id,))
            metrics_rows = sqlite_cursor.fetchall()
            
            for metrics in metrics_rows:
                sqlite_query_id = metrics['query_id']
                if sqlite_query_id not in query_id_map:
                    logger.warning(f"Skipping metrics with unknown query ID: {sqlite_query_id}")
                    continue
                    
                pg_query_id = query_id_map[sqlite_query_id]
                
                metrics_dict = {
                    "p@5": metrics['p_at_5'],
                    "p@10": metrics['p_at_10'],
                    "mrr": metrics['mrr'],
                    "bpref": metrics['bpref'],
                    "judged_counts": {
                        "p@5": metrics['judged_p_at_5'],
                        "p@10": metrics['judged_p_at_10'],
                        "total": metrics['judged_total']
                    },
                    "unjudged_count": metrics['unjudged_count']
                }
                
                pg_db.save_metrics(pg_run_id, pg_query_id, metrics_dict)
        
        logger.info(f"Migrated {len(run_id_map)} runs to PostgreSQL")
        return run_id_map
    except Exception as e:
        logger.error(f"Error migrating runs: {e}")
        return {}

def migrate_comparisons(sqlite_conn: sqlite3.Connection, pg_db: IRDatabasePG, run_id_map: Dict[int, int]) -> int:
    """
    Migrate comparisons from SQLite to PostgreSQL.
    
    Args:
        sqlite_conn: SQLite connection
        pg_db: PostgreSQL database manager
        run_id_map: Mapping from SQLite to PostgreSQL run IDs
        
    Returns:
        Number of comparisons migrated
    """
    try:
        # Get all comparisons from SQLite
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute("""
        SELECT id, timestamp, run_ids, run_names, best_run_id, comparison_data 
        FROM comparisons
        """)
        comparisons = sqlite_cursor.fetchall()
        
        logger.info(f"Found {len(comparisons)} comparisons in SQLite database")
        
        # Process each comparison
        migrated_count = 0
        for comp in comparisons:
            # Parse JSONs
            run_ids = json.loads(comp['run_ids'])
            run_names = json.loads(comp['run_names'])
            comparison_data = json.loads(comp['comparison_data']) if comp['comparison_data'] else {}
            
            # Map SQLite run IDs to PostgreSQL run IDs
            pg_run_ids = [run_id_map.get(rid) for rid in run_ids]
            
            # Skip if any run ID cannot be mapped
            if None in pg_run_ids:
                logger.warning(f"Skipping comparison {comp['id']} due to unmapped run IDs")
                continue
            
            # Map best run ID
            pg_best_run_id = run_id_map.get(comp['best_run_id']) if comp['best_run_id'] else None
            
            # Save comparison to PostgreSQL
            pg_comp_id = pg_db.save_comparison(pg_run_ids, run_names, comparison_data, pg_best_run_id)
            
            if pg_comp_id:
                migrated_count += 1
                logger.debug(f"Migrated comparison {comp['id']} -> {pg_comp_id}")
            else:
                logger.warning(f"Failed to migrate comparison {comp['id']}")
        
        logger.info(f"Migrated {migrated_count} comparisons to PostgreSQL")
        return migrated_count
    except Exception as e:
        logger.error(f"Error migrating comparisons: {e}")
        return 0

def main(sqlite_db_path: str = DEFAULT_SQLITE_DB_PATH):
    """Main entry point of the script."""
    try:
        # Check if SQLite database exists
        if not os.path.exists(sqlite_db_path):
            logger.error(f"SQLite database not found: {sqlite_db_path}")
            return 1
        
        # Connect to both databases
        sqlite_conn = connect_sqlite(sqlite_db_path)
        pg_db = IRDatabasePG()
        
        # Migrate all data
        print("\n=== Starting migration from SQLite to PostgreSQL ===")
        print(f"Source: {sqlite_db_path}")
        print(f"Destination: PostgreSQL database 'NEXUS', schema 'ir_eval'")
        print("="*60)
        
        # Execute migration steps
        print("\nStep 1: Migrating queries...")
        query_id_map = migrate_queries(sqlite_conn, pg_db)
        
        print("\nStep 2: Migrating judgments...")
        judgments_count = migrate_judgments(sqlite_conn, pg_db, query_id_map)
        
        print("\nStep 3: Migrating runs and results...")
        run_id_map = migrate_runs(sqlite_conn, pg_db, query_id_map)
        
        print("\nStep 4: Migrating comparisons...")
        comparisons_count = migrate_comparisons(sqlite_conn, pg_db, run_id_map)
        
        # Close connections
        sqlite_conn.close()
        pg_db.close()
        
        # Summary
        print("\n=== Migration Summary ===")
        print(f"Queries: {len(query_id_map)}")
        print(f"Judgments: {judgments_count}")
        print(f"Runs: {len(run_id_map)}")
        print(f"Comparisons: {comparisons_count}")
        print("="*60)
        print("Migration completed successfully!")
        
        return 0
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    # Allow custom SQLite database path
    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SQLITE_DB_PATH
    sys.exit(main(sqlite_path))