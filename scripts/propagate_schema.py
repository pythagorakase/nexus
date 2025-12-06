#!/usr/bin/env python3
"""
Propagate schema migrations from NEXUS_template to all databases.

The template database contains:
  - The canonical schema (all tables empty)
  - schema_migrations table tracking what's applied where

Usage:
    python scripts/propagate_schema.py           # Apply pending to all
    python scripts/propagate_schema.py --status  # Show migration status
    python scripts/propagate_schema.py --dry-run # Preview without applying
    python scripts/propagate_schema.py --db save_01  # Target specific database
"""

import argparse
import sys
import tomllib
from pathlib import Path

import psycopg2
from psycopg2.extensions import connection as PGConnection

# Load database settings from nexus.toml
SETTINGS_PATH = Path(__file__).parent.parent / "nexus.toml"
with SETTINGS_PATH.open("rb") as f:
    _settings = tomllib.load(f)
_db_settings = _settings.get("database", {})
DB_USER = _db_settings.get("user", "pythagor")
DB_HOST = _db_settings.get("host", "localhost")

TEMPLATE_DB = "NEXUS_template"
# Note: NEXUS database intentionally excluded - kept as backup
TARGET_DBS = ["save_01", "save_02", "save_03", "save_04", "save_05"]
MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def get_template_connection() -> PGConnection:
    """Get connection to the template database."""
    return psycopg2.connect(dbname=TEMPLATE_DB, user=DB_USER, host=DB_HOST)


def get_target_connection(db_name: str) -> PGConnection:
    """Get connection to a target database."""
    return psycopg2.connect(dbname=db_name, user=DB_USER, host=DB_HOST)


def ensure_schema_migrations_table(conn: PGConnection) -> None:
    """Create schema_migrations table in template if missing."""

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name TEXT NOT NULL,
                database_name TEXT NOT NULL,
                applied_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (migration_name, database_name)
            )
            """
        )
    conn.commit()


def get_applied_migrations(db_name: str) -> set[str]:
    """Query template for migrations already applied to this database."""
    conn = get_template_connection()
    try:
        ensure_schema_migrations_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT migration_name FROM schema_migrations WHERE database_name = %s",
                (db_name,),
            )
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def get_all_migrations() -> list[Path]:
    """Get all migration files in order."""
    if not MIGRATIONS_DIR.exists():
        return []
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def get_pending_migrations(db_name: str) -> list[Path]:
    """Get migrations not yet applied to this database."""
    applied = get_applied_migrations(db_name)
    return [m for m in get_all_migrations() if m.name not in applied]


def apply_migration(db_name: str, migration_path: Path, dry_run: bool = False) -> bool:
    """
    Apply a migration to a target database and record in template.

    Returns True on success, False on failure.
    """
    sql = migration_path.read_text()

    if dry_run:
        print(f"  [DRY RUN] Would apply {migration_path.name}")
        return True

    # Apply to target database
    try:
        target_conn = get_target_connection(db_name)
        try:
            with target_conn.cursor() as cur:
                cur.execute(sql)
            target_conn.commit()
        finally:
            target_conn.close()
    except Exception as e:
        print(f"  \u2717 {migration_path.name}: {e}")
        return False

    # Record in template
    try:
        template_conn = get_template_connection()
        try:
            ensure_schema_migrations_table(template_conn)
            with template_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO schema_migrations (migration_name, database_name) VALUES (%s, %s)",
                    (migration_path.name, db_name),
                )
            template_conn.commit()
        finally:
            template_conn.close()
    except Exception as e:
        print(f"  \u2717 Failed to record migration: {e}")
        return False

    print(f"  \u2713 {migration_path.name}")
    return True


def apply_migration_to_template(migration_path: Path, dry_run: bool = False) -> bool:
    """
    Apply migration to template database itself (for future clones).

    This ensures new slots created via `createdb -T NEXUS_template` have the schema.
    """
    sql = migration_path.read_text()

    if dry_run:
        print(f"  [DRY RUN] Would apply to template: {migration_path.name}")
        return True

    try:
        conn = get_template_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"  [TEMPLATE] ✓ {migration_path.name}")
        finally:
            conn.close()
    except Exception as e:
        # Surface errors visibly per CLAUDE.md - don't silently continue
        print(f"  [TEMPLATE] ✗ {migration_path.name}: {e}")
        return False

    return True


def show_status():
    """Display migration status for all databases."""
    all_migrations = [m.name for m in get_all_migrations()]

    if not all_migrations:
        print("\nNo migrations found in migrations/ directory.")
        return

    # Include template in status display
    all_dbs = [TEMPLATE_DB] + TARGET_DBS

    # Header
    print(f"\n{'Migration':<35} |", end="")
    for db in all_dbs:
        # Abbreviate database names for display
        short_name = db.replace("NEXUS_", "").replace("save_", "s")[:8]
        print(f" {short_name:<8} |", end="")
    print()
    print("-" * (37 + len(all_dbs) * 11))

    # Each migration row
    for migration in all_migrations:
        print(f"{migration:<35} |", end="")
        for db in all_dbs:
            applied = migration in get_applied_migrations(db)
            status = "\u2713" if applied else "\u2717"
            print(f" {status:<8} |", end="")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Propagate schema migrations to all databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                  Apply pending migrations to all databases
  %(prog)s --status         Show migration status matrix
  %(prog)s --dry-run        Preview what would be applied
  %(prog)s --db save_01     Apply only to save_01
        """,
    )
    parser.add_argument(
        "--status", action="store_true", help="Show migration status for all databases"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migrations without applying",
    )
    parser.add_argument(
        "--db",
        help="Target specific database only (e.g., save_01)",
    )
    args = parser.parse_args()

    # Check template database exists
    try:
        conn = get_template_connection()
        ensure_schema_migrations_table(conn)
        conn.close()
    except psycopg2.OperationalError as e:
        print(f"Error: Cannot connect to {TEMPLATE_DB}: {e}")
        print("Run the bootstrap commands first to create the template database.")
        sys.exit(1)

    if args.status:
        show_status()
        return

    targets = [args.db] if args.db else TARGET_DBS

    # Validate target database
    if args.db and args.db not in TARGET_DBS and args.db != TEMPLATE_DB:
        print(f"Warning: {args.db} is not in the standard target list.")
        print(f"Standard targets: {', '.join(TARGET_DBS)}")

    any_applied = False
    for db in targets:
        print(f"\n=== {db} ===")
        pending = get_pending_migrations(db)
        if not pending:
            print("  (up to date)")
            continue

        for migration in pending:
            success = apply_migration(db, migration, dry_run=args.dry_run)
            if success:
                any_applied = True
                # Also apply to template (for future clones)
                template_success = apply_migration_to_template(migration, dry_run=args.dry_run)
                if not template_success:
                    print(f"  ⚠ Template migration failed - target DB was updated but template may be out of sync")
                    sys.exit(1)
            else:
                print(f"  Stopping due to error.")
                sys.exit(1)

    if any_applied and not args.dry_run:
        print("\n\u2705 Migrations applied successfully!")
    elif not any_applied:
        print("\n\u2705 All databases up to date!")


if __name__ == "__main__":
    main()
