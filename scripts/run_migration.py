#!/usr/bin/env python3
"""Run a SQL migration file."""

import sys
from pathlib import Path
from sqlalchemy import create_engine, text

# Database connection
DB_URL = "postgresql://pythagor@localhost:5432/NEXUS"

def run_migration(migration_file: Path):
    """Execute a SQL migration file."""
    if not migration_file.exists():
        print(f"Error: Migration file not found: {migration_file}")
        sys.exit(1)

    print(f"Running migration: {migration_file.name}")

    # Read the migration SQL
    sql = migration_file.read_text()

    # Create engine and execute
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text(sql))

    print("Migration completed successfully!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_migration.py <migration_file>")
        sys.exit(1)

    migration_path = Path(sys.argv[1])
    run_migration(migration_path)
