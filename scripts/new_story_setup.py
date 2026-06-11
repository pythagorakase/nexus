#!/usr/bin/env python3
"""
Utilities for new-story save slots.

Actions:
  - Create assets tables (`assets.new_story_creator`)
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

# Import migration runner for post-creation migration
try:
    from scripts.migrate import migrate_database

    HAS_MIGRATE = True
except ImportError:
    HAS_MIGRATE = False


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
    with _connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(ddl_creator)
    LOG.info(
        "Ensured assets tables exist in %s",
        dbname or os.environ.get("PGDATABASE", "(unspecified)"),
    )


def _get_default_slot_model() -> str:
    """Get default model for new slots from config."""
    try:
        from nexus.config.loader import load_settings

        settings = load_settings()
        return settings.global_.model.default_slot_model
    except Exception:
        # Fallback if config not available
        return "TEST"


def ensure_global_variables(dbname: str) -> None:
    """Ensure singleton row exists with new_story and default model."""
    default_model = _get_default_slot_model()
    with _connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM public.global_variables WHERE id = TRUE")
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute(
                "INSERT INTO public.global_variables (id, new_story, model) VALUES (TRUE, TRUE, %s)",
                (default_model,),
            )
            LOG.info(
                "Inserted default global_variables row in %s (model=%s)",
                dbname,
                default_model,
            )


def create_slot_schema_only(
    slot: int, source_db: Optional[str] = None, force: bool = False
) -> None:
    """
    Create a per-slot database from the template (no narrative data).

    Args:
        slot: Slot number (1-5)
        source_db: Source database to clone from. Defaults to "NEXUS_template",
                   which carries the latest schema plus seed/vocab rows and a
                   fully stamped schema_migrations table.
        force: If True, drop and recreate the target database.
    """
    if slot < 1 or slot > 5:
        raise ValueError("Slot must be between 1 and 5 (inclusive)")
    target_db = f"save_{slot:02d}"
    initialize_slot_database(target_db, source_db=source_db, force=force)


def initialize_slot_database(
    target_db: str, source_db: Optional[str] = None, force: bool = False
) -> None:
    """
    Create ``target_db`` as a fresh story database cloned from the template.

    Copies the template schema, then the template's data (seed/vocab tables
    such as tags and event_types, plus the schema_migrations stamps). The
    stamps baseline the new database so the migration runner only applies
    migrations the template has not seen — without them, migrate.py replays
    already-applied migrations against the post-migration schema and fails
    (e.g. 053 alters factions.power_level, which 058 already dropped).
    """
    # NEXUS_template is the canonical fresh-slot image (schema + seed data)
    source_db = source_db or "NEXUS_template"

    if force:
        # Terminate active connections before dropping
        # Use raw psycopg2 for postgres admin DB (not in slot pool)
        admin_conn = psycopg2.connect(
            dbname="postgres",
            user=os.environ.get("PGUSER", "pythagor"),
            host=os.environ.get("PGHOST", "localhost"),
            port=os.environ.get("PGPORT", "5432"),
        )
        try:
            admin_conn.autocommit = True  # Required for pg_terminate_backend
            with admin_conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                    (target_db,),
                )
        finally:
            admin_conn.close()
        subprocess.run(["dropdb", "--if-exists", target_db], check=False)
        LOG.warning("Dropped database %s if it existed", target_db)

    subprocess.run(["createdb", target_db], check=True)
    LOG.info("Created database %s", target_db)

    # Dump both public and assets schemas from template
    dump_cmd = ["pg_dump", "-s", "-n", "public", "-n", "assets", source_db]
    LOG.info("Dumping schema (public + assets) from %s", source_db)
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".sql") as tmp:
        subprocess.run(dump_cmd, check=True, stdout=tmp)
        tmp_path = tmp.name

    try:
        # Ensure required extensions exist in the new DB
        subprocess.run(
            ["psql", target_db, "-c", "CREATE EXTENSION IF NOT EXISTS vector;"],
            check=True,
        )
        subprocess.run(
            ["psql", target_db, "-c", "CREATE EXTENSION IF NOT EXISTS postgis;"],
            check=True,
        )

        # Strip CREATE/ALTER SCHEMA lines to avoid noisy errors
        with open(tmp_path, "r", encoding="utf-8") as f:
            sql_lines = [
                line
                for line in f
                if not line.strip().startswith("CREATE SCHEMA public")
                and not line.strip().startswith("ALTER SCHEMA public")
                and not line.strip().startswith("CREATE SCHEMA assets")
                and not line.strip().startswith("ALTER SCHEMA assets")
            ]
        # Add CREATE SCHEMA assets (since we filter it out but need it)
        sql_lines.insert(0, "CREATE SCHEMA IF NOT EXISTS assets;\n")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.writelines(sql_lines)

        LOG.info("Restoring schema into %s", target_db)
        subprocess.run(["psql", target_db, "-f", tmp_path], check=True)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # Copy template data: seed/vocab rows plus schema_migrations stamps.
    _copy_template_data(source_db, target_db)
    _require_migration_stamps(source_db, target_db)

    # Ensure global_variables row exists
    ensure_global_variables(target_db)

    # Apply only migrations newer than the template's stamped baseline
    if HAS_MIGRATE:
        LOG.info("Running migrations on %s...", target_db)
        applied, failed = migrate_database(target_db, skip_locked=False)
        if failed:
            LOG.warning("Some migrations failed on %s", target_db)
        else:
            LOG.info("Applied %d migrations to %s", applied, target_db)
    else:
        LOG.warning(
            "Migration runner not available - run 'python scripts/migrate.py' manually"
        )

    LOG.info("Database %s ready", target_db)


# The template's canonical seed image: the only tables whose ROWS are copied
# into a fresh story database. Keep in sync with the "Refreshing the Template"
# section of CLAUDE.md. Everything else arrives schema-only, so pointing
# --mode schema at a populated source can never leak narrative or cache rows
# into a fresh slot.
TEMPLATE_SEED_TABLES = (
    "public.schema_migrations",
    "public.tags",
    "public.event_types",
    "public.pair_tags",
    "public.tag_category_registry",
    "assets.traits",
)


def _copy_template_data(source_db: str, target_db: str) -> None:
    """Copy the seed image from the template into the freshly restored schema.

    Transfers exactly the seed/vocab tables and the schema_migrations
    baseline (TEMPLATE_SEED_TABLES) — never narrative or cache rows, even if
    the source database carries them. ON_ERROR_STOP keeps failures loud.
    """
    LOG.info("Copying template data (seed rows + migration stamps) from %s", source_db)
    dump_cmd = ["pg_dump", "--data-only", source_db]
    for table in TEMPLATE_SEED_TABLES:
        dump_cmd.extend(["-t", table])
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".sql") as tmp:
        subprocess.run(
            dump_cmd,
            check=True,
            stdout=tmp,
        )
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=1", target_db, "-f", tmp_path],
            check=True,
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _require_migration_stamps(source_db: str, target_db: str) -> None:
    """Fail loudly if the new database has no schema_migrations baseline.

    Without stamps, the next migrate.py run would replay every migration
    against a schema that already contains their effects. That means the
    template itself lacks stamps - refresh it so schema_migrations rows and
    seed data survive (see CLAUDE.md, Refreshing the Template).
    """
    with _connect(target_db) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM public.schema_migrations")
        count = cur.fetchone()[0]
    if count == 0:
        raise RuntimeError(
            f"{target_db} has an empty schema_migrations table after cloning "
            f"{source_db}. The template must carry migration stamps (and seed "
            "data); refresh it per CLAUDE.md before creating slots."
        )


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
            [
                "pg_dump",
                "-Fp",
                "-d",
                source_db,
                "-f",
                dump_path,
                "-n",
                "public",
                "-n",
                "assets",
            ],
            check=True,
        )
        subprocess.run(["createdb", target_db], check=True)

        # Ensure extensions before replaying functions/tables
        subprocess.run(
            ["psql", target_db, "-c", "CREATE EXTENSION IF NOT EXISTS vector;"],
            check=True,
        )
        subprocess.run(
            ["psql", target_db, "-c", "CREATE EXTENSION IF NOT EXISTS postgis;"],
            check=True,
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
        cur.execute(
            "UPDATE public.global_variables SET new_story = TRUE WHERE id = TRUE;"
        )
    ensure_global_variables(target_db)
    LOG.info("Post-clone cleanup completed for %s", target_db)


def main():
    parser = argparse.ArgumentParser(description="Set up new-story infrastructure")
    parser.add_argument(
        "--create-assets",
        action="store_true",
        help="Create assets tables in the primary DB",
    )
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Drop and recreate the target slot database if it exists",
    )
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
