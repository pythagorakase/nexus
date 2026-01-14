#!/usr/bin/env python3
"""
Database migration runner for NEXUS.

Applies SQL migrations to all slot databases and the template database.
Tracks applied migrations in a per-database `schema_migrations` table.

Usage:
    python scripts/migrate.py --status          # Show pending migrations
    python scripts/migrate.py --all             # Apply to all unlocked DBs
    python scripts/migrate.py --slot 5          # Apply to specific slot
    python scripts/migrate.py --template        # Apply to NEXUS_template only
    python scripts/migrate.py --all --dry-run   # Show what would be applied
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import psycopg2

LOG = logging.getLogger("nexus.migrate")
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)

# Migration directory relative to this script
MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

# All target databases
TEMPLATE_DB = "NEXUS_template"
SLOT_DBS = [f"save_{i:02d}" for i in range(1, 6)]  # save_01 through save_05

# Migrations that existed before tracking - seed as "already applied"
BOOTSTRAP_MIGRATIONS = [
    ("001", "baseline"),
    ("002", "add_choice_columns"),
    ("003", "add_layer_zone_drafts"),
    ("004", "fix_global_variables_fk"),
    ("005", "add_incubator_choice_object"),
    ("006", "add_save_slots_model"),
    ("007", "normalize_new_story_creator"),
    # 008 is a Python seeding script, not a SQL migration
]


def get_connection(dbname: str):
    """Get a database connection."""
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


def is_db_locked(dbname: str) -> bool:
    """
    Check if a database is locked (read-only).

    Uses PostgreSQL's pg_db_role_setting to check for default_transaction_read_only.
    """
    try:
        conn = get_connection("postgres")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT setconfig
                    FROM pg_db_role_setting s
                    JOIN pg_database d ON d.oid = s.setdatabase
                    WHERE d.datname = %s AND s.setrole = 0
                    """,
                    (dbname,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return "default_transaction_read_only=on" in row[0]
                return False
        finally:
            conn.close()
    except psycopg2.Error:
        return False


def db_exists(dbname: str) -> bool:
    """Check if a database exists."""
    try:
        conn = get_connection("postgres")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
                )
                return cur.fetchone() is not None
        finally:
            conn.close()
    except psycopg2.Error:
        return False


def ensure_tracking_table(conn, dry_run: bool = False) -> bool:
    """
    Create schema_migrations table if it doesn't exist or has wrong schema.

    Returns True if table is ready, False if dry_run prevented setup.
    """
    with conn.cursor() as cur:
        # Check if table exists with correct schema
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'schema_migrations' AND table_schema = 'public'
            """
        )
        columns = {row[0] for row in cur.fetchall()}

        if columns and "version" not in columns:
            # Old schema exists - drop and recreate
            if dry_run:
                LOG.info("  [DRY-RUN] Would drop old schema_migrations table (incompatible schema)")
                return False
            LOG.info("  Dropping old schema_migrations table (incompatible schema)")
            cur.execute("DROP TABLE schema_migrations")
            columns = set()

        if not columns:
            if dry_run:
                LOG.info("  [DRY-RUN] Would create schema_migrations table")
                return False
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
    conn.commit()
    return True


def needs_bootstrap(conn) -> bool:
    """Check if we need to bootstrap existing migrations."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM schema_migrations")
        return cur.fetchone()[0] == 0


def bootstrap_migrations(conn, dry_run: bool = False) -> None:
    """Seed schema_migrations with pre-existing migrations."""
    if dry_run:
        LOG.info("  [DRY-RUN] Would bootstrap %d existing migrations", len(BOOTSTRAP_MIGRATIONS))
        return

    with conn.cursor() as cur:
        for version, name in BOOTSTRAP_MIGRATIONS:
            cur.execute(
                """
                INSERT INTO schema_migrations (version, name)
                VALUES (%s, %s)
                ON CONFLICT (version) DO NOTHING
                """,
                (version, name),
            )
    conn.commit()
    LOG.info("  Bootstrapped %d existing migrations", len(BOOTSTRAP_MIGRATIONS))


def get_applied_migrations(conn) -> set:
    """Get set of already-applied migration versions."""
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def discover_migrations() -> List[Tuple[str, str, Path]]:
    """
    Discover SQL migration files.

    Returns list of (version, name, path) tuples sorted by version.
    """
    migrations = []
    pattern = re.compile(r"^(\d{3})_(.+)\.sql$")

    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = pattern.match(path.name)
        if match:
            version, name = match.groups()
            migrations.append((version, name, path))

    return sorted(migrations, key=lambda x: x[0])


def apply_migration(conn, version: str, name: str, path: Path, dry_run: bool = False) -> bool:
    """
    Apply a single migration.

    Returns True if successful, False otherwise.
    """
    if dry_run:
        LOG.info("  [DRY-RUN] Would apply: %s_%s", version, name)
        return True

    try:
        sql = path.read_text()
        with conn.cursor() as cur:
            cur.execute(sql)
            # Record the migration
            cur.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                (version, name),
            )
        conn.commit()
        LOG.info("  Applied: %s_%s", version, name)
        return True
    except psycopg2.Error as e:
        conn.rollback()
        LOG.error("  FAILED: %s_%s - %s", version, name, e)
        return False


def migrate_database(dbname: str, dry_run: bool = False, skip_locked: bool = True) -> Tuple[int, int]:
    """
    Apply pending migrations to a single database.

    Returns (applied_count, skipped_count).
    """
    if not db_exists(dbname):
        LOG.warning("Database %s does not exist, skipping", dbname)
        return (0, 0)

    if skip_locked and is_db_locked(dbname):
        LOG.warning("Database %s is LOCKED (read-only), skipping", dbname)
        return (0, 0)

    LOG.info("Migrating %s...", dbname)

    try:
        conn = get_connection(dbname)
    except psycopg2.Error as e:
        LOG.error("Cannot connect to %s: %s", dbname, e)
        return (0, 0)

    try:
        table_ready = ensure_tracking_table(conn, dry_run)

        if not table_ready:
            # In dry-run mode and table doesn't exist - show all migrations as pending
            all_migrations = discover_migrations()
            LOG.info("  [DRY-RUN] Would bootstrap %d existing migrations", len(BOOTSTRAP_MIGRATIONS))
            pending = [m for m in all_migrations if m[0] not in {v for v, _ in BOOTSTRAP_MIGRATIONS}]
            for version, name, _ in pending:
                LOG.info("  [DRY-RUN] Would apply: %s_%s", version, name)
            return (len(pending), 0)

        # Bootstrap if this is a fresh tracking table
        bootstrap_needed = needs_bootstrap(conn)
        if bootstrap_needed:
            bootstrap_migrations(conn, dry_run)

        applied = get_applied_migrations(conn)

        # In dry-run mode with bootstrap, applied set is empty but we should
        # treat bootstrapped migrations as applied
        if dry_run and bootstrap_needed:
            applied = {v for v, _ in BOOTSTRAP_MIGRATIONS}

        all_migrations = discover_migrations()

        pending = [(v, n, p) for v, n, p in all_migrations if v not in applied]

        if not pending:
            LOG.info("  No pending migrations")
            return (0, 0)

        applied_count = 0
        for version, name, path in pending:
            if apply_migration(conn, version, name, path, dry_run):
                applied_count += 1
            else:
                # Stop on first failure
                break

        return (applied_count, len(pending) - applied_count)

    finally:
        conn.close()


def show_status() -> None:
    """Show migration status for all databases."""
    all_migrations = discover_migrations()
    print(f"Found {len(all_migrations)} SQL migrations in {MIGRATIONS_DIR}\n")

    databases = [TEMPLATE_DB] + SLOT_DBS

    for dbname in databases:
        if not db_exists(dbname):
            print(f"{dbname}: [does not exist]")
            continue

        locked = is_db_locked(dbname)
        status = " [LOCKED]" if locked else ""
        print(f"{dbname}:{status}")

        if locked:
            print("  (locked - unlock to view/apply migrations)")
            continue

        try:
            conn = get_connection(dbname)
            # Don't modify in status mode - just check if table exists with right schema
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'schema_migrations' AND table_schema = 'public'
                    """
                )
                columns = {row[0] for row in cur.fetchall()}

            if not columns or "version" not in columns:
                print("  (needs bootstrap - run migrate to initialize)")
                conn.close()
                continue

            if needs_bootstrap(conn):
                print("  (needs bootstrap - run migrate to initialize)")
                conn.close()
                continue

            applied = get_applied_migrations(conn)
            conn.close()

            for version, name, _ in all_migrations:
                marker = "[x]" if version in applied else "[ ]"
                print(f"  {marker} {version}_{name}")

        except psycopg2.Error as e:
            print(f"  Error: {e}")
        print()  # Blank line between databases


def main():
    parser = argparse.ArgumentParser(
        description="Apply database migrations to NEXUS slot databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    target_group = parser.add_mutually_exclusive_group()
    target_group.add_argument(
        "--all",
        action="store_true",
        help="Apply to all databases (template + all slots)",
    )
    target_group.add_argument(
        "--slot",
        type=int,
        choices=range(1, 6),
        metavar="N",
        help="Apply to specific slot (1-5)",
    )
    target_group.add_argument(
        "--template",
        action="store_true",
        help="Apply to NEXUS_template only",
    )
    target_group.add_argument(
        "--status",
        action="store_true",
        help="Show migration status for all databases",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be applied without making changes",
    )

    args = parser.parse_args()

    # Default to --status if no target specified
    if not any([args.all, args.slot, args.template, args.status]):
        args.status = True

    if args.status:
        show_status()
        return

    # Determine target databases
    if args.all:
        targets = [TEMPLATE_DB] + SLOT_DBS
    elif args.slot:
        targets = [f"save_{args.slot:02d}"]
    elif args.template:
        targets = [TEMPLATE_DB]
    else:
        targets = []

    if args.dry_run:
        LOG.info("[DRY-RUN MODE - no changes will be made]")

    total_applied = 0
    total_skipped = 0

    for dbname in targets:
        applied, skipped = migrate_database(dbname, dry_run=args.dry_run)
        total_applied += applied
        total_skipped += skipped

    LOG.info("")
    LOG.info("Summary: %d applied, %d skipped/failed", total_applied, total_skipped)

    sys.exit(0 if total_skipped == 0 else 1)


if __name__ == "__main__":
    main()
