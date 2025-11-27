#!/usr/bin/env python3
"""
Utilities for new-story save slots.

Actions:
  - Create assets tables (`assets.new_story_creator`, `assets.save_slots`)
  - Clone the public schema into a save slot schema (save_02 ... save_05) using pg_dump-based rewrite
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import tempfile
from typing import Optional

import psycopg2

LOG = logging.getLogger("nexus.new_story_setup")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# Try to use connection pool if available (when running within NEXUS)
try:
    from nexus.api.db_pool import get_connection
    USE_POOL = True
except ImportError:
    USE_POOL = False


def _connect(dbname: Optional[str] = None):
    """
    Get database connection, using pool if available.

    Args:
        dbname: Explicit database name. For slot databases, use save_01 through save_05.
                If not provided, uses PGDATABASE env var (no automatic fallback to NEXUS).
    """
    if USE_POOL:
        # This is a context manager that returns the connection
        # Note: callers must be updated to handle this properly
        return get_connection(dbname)
    else:
        # Fallback for standalone script execution
        # Note: dbname must be explicitly provided or set via PGDATABASE
        resolved_dbname = dbname or os.environ.get("PGDATABASE")
        if not resolved_dbname:
            raise RuntimeError(
                "No database specified. Set PGDATABASE environment variable "
                "or pass dbname explicitly. Valid slot databases: save_01 through save_05."
            )
        user = os.environ.get("PGUSER", "pythagor")
        host = os.environ.get("PGHOST", "localhost")
        port = os.environ.get("PGPORT", "5432")
        return psycopg2.connect(dbname=resolved_dbname, user=user, host=host, port=port)


def create_assets_tables(dbname: Optional[str] = None) -> None:
    """Create cache/metadata tables in assets schema for the given database."""
    ddl_creator = """
    CREATE SCHEMA IF NOT EXISTS assets;
    CREATE TABLE IF NOT EXISTS assets.new_story_creator (
        id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
        thread_id TEXT,
        setting_draft JSONB,
        character_draft JSONB,
        selected_seed JSONB,
        initial_location JSONB,
        base_timestamp TIMESTAMPTZ,
        target_slot INTEGER,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    ddl_slots = """
    CREATE TABLE IF NOT EXISTS assets.save_slots (
        slot_number INTEGER PRIMARY KEY,
        character_name TEXT,
        last_played TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        is_active BOOLEAN DEFAULT FALSE
    );
    """
    with _connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(ddl_creator)
        cur.execute(ddl_slots)
    LOG.info("Ensured assets tables exist in %s", dbname or os.environ.get("PGDATABASE", "(unspecified)"))


def ensure_global_variables(dbname: str) -> None:
    """Ensure singleton row exists with new_story defaulted to true."""
    with _connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM public.global_variables WHERE id = TRUE")
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute("INSERT INTO public.global_variables (id, new_story) VALUES (TRUE, TRUE)")
            LOG.info("Inserted default global_variables row in %s", dbname)


def create_slot_schema_only(slot: int, source_db: Optional[str] = None, force: bool = False) -> None:
    """
    Create a per-slot database with schema only (no data).

    Args:
        slot: Slot number (1-5)
        source_db: Source database to clone schema from.
                   Defaults to "NEXUS" which is the schema template database.
                   This is intentional - NEXUS serves as the empty schema template.
        force: If True, drop and recreate the target database.
    """
    if slot < 1 or slot > 5:
        raise ValueError("Slot must be between 1 and 5 (inclusive)")
    # NEXUS is the schema template database - intentional default for cloning
    source_db = source_db or "NEXUS"
    target_db = f"save_{slot:02d}"

    if force:
        # Use parameterized query to avoid SQL injection
        with _connect("postgres") as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (target_db,)
            )
        subprocess.run(["dropdb", "--if-exists", target_db], check=False)
        LOG.warning("Dropped database %s if it existed", target_db)

    subprocess.run(["createdb", target_db], check=True)
    LOG.info("Created database %s", target_db)

    dump_cmd = ["pg_dump", "-s", "-n", "public", source_db]
    LOG.info("Dumping schema from %s", source_db)
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".sql") as tmp:
        subprocess.run(dump_cmd, check=True, stdout=tmp)
        tmp_path = tmp.name

    try:
        # Ensure required extensions exist in the new DB
        subprocess.run(
            ["psql", target_db, "-c", "CREATE EXTENSION IF NOT EXISTS vector;"], check=True
        )
        subprocess.run(
            ["psql", target_db, "-c", "CREATE EXTENSION IF NOT EXISTS postgis;"], check=True
        )

        # Strip CREATE/ALTER SCHEMA public lines to avoid noisy errors
        with open(tmp_path, "r", encoding="utf-8") as f:
            sql_lines = [
                line
                for line in f
                if not line.strip().startswith("CREATE SCHEMA public")
                and not line.strip().startswith("ALTER SCHEMA public")
            ]
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.writelines(sql_lines)

        LOG.info("Restoring schema into %s", target_db)
        subprocess.run(["psql", target_db, "-f", tmp_path], check=True)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # Create assets tables inside the slot DB
    create_assets_tables(target_db)
    ensure_global_variables(target_db)
    LOG.info("Slot %s ready (schema-only)", target_db)


def clone_slot_with_data(slot: int, source_db: str, force: bool = False) -> None:
    """
    Clone a slot by copying all data from source_db into save_XX.
    Uses pg_dump/pg_restore to avoid template locks on the source DB.
    """
    if slot < 1 or slot > 5:
        raise ValueError("Slot must be between 1 and 5 (inclusive)")
    target_db = f"save_{slot:02d}"

    if force:
        subprocess.run(["dropdb", "--if-exists", target_db], check=False)
        LOG.warning("Dropped database %s if it existed", target_db)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".sql") as tmp:
        dump_path = tmp.name

    try:
        # Plain text dump for easy filtering
        subprocess.run(
            ["pg_dump", "-Fp", "-d", source_db, "-f", dump_path, "-n", "public", "-n", "assets"],
            check=True,
        )
        subprocess.run(["createdb", target_db], check=True)

        # Ensure extensions before replaying functions/tables
        subprocess.run(
            ["psql", target_db, "-c", "CREATE EXTENSION IF NOT EXISTS vector;"], check=True
        )
        subprocess.run(
            ["psql", target_db, "-c", "CREATE EXTENSION IF NOT EXISTS postgis;"], check=True
        )

        # Strip CREATE/ALTER SCHEMA public lines to avoid conflicts
        with open(dump_path, "r", encoding="utf-8") as f:
            filtered = [
                line
                for line in f
                if not line.strip().startswith("CREATE SCHEMA public")
                and not line.strip().startswith("ALTER SCHEMA public")
            ]
        with open(dump_path, "w", encoding="utf-8") as f:
            f.writelines(filtered)

        subprocess.run(["psql", target_db, "-f", dump_path], check=True)
        _post_clone_cleanup(target_db)
        LOG.info("Cloned %s into %s (with data)", source_db, target_db)
    finally:
        try:
            os.remove(dump_path)
        except OSError:
            pass


def _post_clone_cleanup(target_db: str) -> None:
    """Normalize cloned DB: ensure new_story is true."""
    with _connect(target_db) as conn, conn.cursor() as cur:
        cur.execute("UPDATE public.global_variables SET new_story = TRUE WHERE id = TRUE;")
    ensure_global_variables(target_db)
    LOG.info("Post-clone cleanup completed for %s", target_db)


def main():
    parser = argparse.ArgumentParser(description="Set up new-story infrastructure")
    parser.add_argument("--create-assets", action="store_true", help="Create assets tables in the primary DB")
    parser.add_argument("--slot", type=int, help="Target slot number (2-5)")
    parser.add_argument(
        "--mode",
        choices=["schema", "clone"],
        default="schema",
        help="schema: create empty schema-only DB; clone: copy data from --source DB",
    )
    parser.add_argument(
        "--source",
        help="Source database for cloning (required when --mode=clone). Defaults to PGDATABASE when --mode=schema.",
    )
    parser.add_argument("--force", action="store_true", help="Drop and recreate the target slot database if it exists")
    args = parser.parse_args()

    if not args.create_assets and not args.slot:
        parser.error("Specify --create-assets and/or --slot")

    if args.create_assets:
        create_assets_tables()

    if args.slot:
        if args.mode == "clone":
            if not args.source:
                parser.error("--source is required when --mode=clone")
            clone_slot_with_data(args.slot, source_db=args.source, force=args.force)
        else:
            create_slot_schema_only(args.slot, source_db=args.source, force=args.force)


if __name__ == "__main__":
    main()
