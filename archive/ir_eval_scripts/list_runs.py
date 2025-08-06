#!/usr/bin/env python3
"""
List runs in the IR evaluation database
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import IRDatabase

def main():
    db = IRDatabase()
    cursor = db.conn.cursor()
    
    # Get all runs
    cursor.execute('''
    SELECT id, name, timestamp, config_type
    FROM runs
    ORDER BY timestamp DESC
    ''')
    
    print("\nRecent runs in database:")
    print("-" * 80)
    print(f"{'ID':<4} {'Name':<30} {'Type':<15} {'Timestamp':<25}")
    print("-" * 80)
    
    for row in cursor.fetchall():
        print(f"{row['id']:<4} {row['name']:<30} {row.get('config_type', 'N/A'):<15} {row['timestamp']:<25}")
    
    db.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())