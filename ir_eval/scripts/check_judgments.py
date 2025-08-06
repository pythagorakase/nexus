#!/usr/bin/env python3
"""
Check judgment counts for each query in the IR evaluation database.
"""

import os
import sys
import sqlite3

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import IRDatabase

def main():
    db = IRDatabase()
    cursor = db.conn.cursor()
    
    # Check judgments by query
    cursor.execute('''
        SELECT q.id, q.text, COUNT(j.id) as judgment_count 
        FROM queries q 
        LEFT JOIN judgments j ON q.id = j.query_id 
        GROUP BY q.id, q.text
        ORDER BY q.id
    ''')
    
    print("\nJudgments per query:")
    print("-" * 80)
    print("Query ID | Judgment Count | Query Text")
    print("-" * 80)
    
    for row in cursor.fetchall():
        query_id = row['id']
        judgment_count = row['judgment_count']
        query_text = row['text']
        truncated_text = query_text[:50] + "..." if len(query_text) > 50 else query_text
        print(f"{query_id:<8} | {judgment_count:<14} | {truncated_text}")
    
    # Check if we have metrics
    cursor.execute('''
        SELECT DISTINCT query_id 
        FROM metrics
        ORDER BY query_id
    ''')
    
    metrics_queries = [row['query_id'] for row in cursor.fetchall()]
    
    print("\nQueries with metrics calculated:", metrics_queries)
    
    # Check runs
    cursor.execute('''
        SELECT id, name, timestamp 
        FROM runs
        ORDER BY timestamp DESC
    ''')
    
    print("\nRuns in the database:")
    print("-" * 80)
    print("Run ID | Name | Timestamp")
    print("-" * 80)
    
    for row in cursor.fetchall():
        print(f"{row['id']:<6} | {row['name']:<25} | {row['timestamp']}")
    
    # Close the database connection
    db.close()

if __name__ == "__main__":
    main()