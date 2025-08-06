#!/usr/bin/env python3
"""
Script to compare original queries with their variations using explicit relationships.

This script uses the comparison module to analyze performance differences
between original queries and their variations defined in the query_relationships table.

Usage:
    python compare_query_pairs.py [--judgments-only] [--run-id RUN_ID]
"""

import sys
import os
import argparse
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import IRDatabase
from scripts.comparison import (
    compare_aggregated_judgments, 
    print_aggregated_judgments_table,
    compare_query_variations,
    print_query_variations_table
)

def main():
    parser = argparse.ArgumentParser(description="Compare original queries with their variations")
    parser.add_argument("--judgments-only", action="store_true", help="Compare judgments only (no metrics)")
    parser.add_argument("--run-id", type=int, help="Run ID to use for metrics comparison")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database")
    
    args = parser.parse_args()
    
    # Use default database path if not specified
    db_path = args.db_path
    if not db_path:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ir_eval.db")
    
    # Initialize database connection
    db = IRDatabase(db_path)
    
    try:
        # Compare judgments
        if args.judgments_only:
            print("\nComparing judgment statistics between original queries and variations...")
            results = compare_aggregated_judgments(db)
            print_aggregated_judgments_table(results)
        # Compare metrics
        elif args.run_id:
            print(f"\nComparing metrics for run ID {args.run_id}...")
            results = compare_query_variations(args.run_id, db)
            print_query_variations_table(results)
        else:
            print("Error: Either --judgments-only or --run-id must be specified")
            return 1
    except RuntimeError as e:
        print(f"Error: {e}")
        print("\nMake sure you've run the add_query_relationships.py script first to create the relationships table.")
        return 1
    finally:
        # Close database connection
        db.close()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())