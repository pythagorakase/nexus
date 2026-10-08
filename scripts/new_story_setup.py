#!/usr/bin/env python3
"""
Utilities for new-story save slots.

Actions:
  - Create assets tables (`assets.new_story_creator`)
  - Clone the public schema into a save slot schema (save_02 ... save_05) using pg_dump-based rewrite
"""

from __future__ import annotations

from nexus.api.db_pool import dispose_database
from nexus.api.save_slots import is_slot_locked
from nexus.api.slot_utils import slot_dbname
from nexus.api.story_identity import record_fork, replace_story_identity

from nexus.database import subprocess_env

from nexus.database import connection_kwargs

import argparse
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Mapping, Optional

import psycopg2

from scripts.migrate import migrate_database

LOG = logging.getLogger("nexus.new_story_setup")

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
        return psycopg2.connect(**connection_kwargs(resolved_dbname))


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
    """Get default model for new slots from config.

    A configuration that fails to load or validate raises.
    """
    from nexus.config.loader import load_settings

    return load_settings().global_.model.default_slot_model


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
    target_db = slot_dbname(slot)
    dispose_database(target_db)
    initialize_slot_database(target_db, source_db=source_db, force=force)


def _postgres_tools(*names: str) -> dict[str, str]:
    """Resolve every required tool before changing an existing database."""
    resolved = {name: shutil.which(name) for name in names}
    if not all(resolved.values()):
        from nexus.config import load_settings

        settings = load_settings()
        search_paths = settings.api.database.tool_search_paths if settings.api else []
        extra_path = os.pathsep.join(
            str(Path(path).expanduser()) for path in search_paths
        )
        if extra_path:
            for name, executable in resolved.items():
                if executable is None:
                    resolved[name] = shutil.which(name, path=extra_path)

    missing = [name for name, executable in resolved.items() if executable is None]
    if missing:
        raise RuntimeError(
            f"PostgreSQL tools unavailable: {', '.join(missing)}. "
            "Add their directory to [api.database].tool_search_paths in nexus.toml."
        )
    return {name: str(executable) for name, executable in resolved.items()}


def _locked_target_message(target_db: str) -> str:
    """Return the refusal text for a locked ``target_db``.

    A slot database gets the text ``reset_setup`` raises, with its
    ``nexus unlock`` hint; any other database is named without that hint.
    The fixed production pattern decides, never ``slot_utils.VALID_DBNAMES``:
    the test routing contract narrows that set to its disposable clone names.
    """
    m = re.fullmatch(r"save_0([1-5])", target_db)
    if m:
        n = int(m.group(1))
        return f"Slot {n} is locked. Unlock it first with: nexus unlock --slot {n}"
    return (
        f"Database {target_db} is locked (default_transaction_read_only=on); "
        "refusing to replace it."
    )


def _refuse_locked_target(target_db: str) -> None:
    """Raise ``ValueError`` before any change when ``target_db`` is locked.

    The lock is ``default_transaction_read_only=on`` on the database. It does
    not stop ``dropdb``, which connects to another database, so setup reads it
    here. A database with no setting, or one that does not exist, is unlocked.
    """
    m = re.fullmatch(r"save_0([1-5])", target_db)
    # is_slot_locked reads only dbname when it is given; the slot number is unused.
    slot_number = int(m.group(1)) if m else 0
    if is_slot_locked(slot_number, dbname=target_db):
        raise ValueError(_locked_target_message(target_db))


def initialize_slot_database(
    target_db: str,
    source_db: Optional[str] = None,
    force: bool = False,
    *,
    migrations_dir: Optional[Path] = None,
) -> None:
    """
    Create ``target_db`` as a fresh story database cloned from the template.

    Copies the template schema, then the template's data (seed/vocab tables
    such as tags and event_types, plus the schema_migrations stamps). The
    stamps baseline the new database so the migration runner only applies
    migrations the template has not seen — without them, migrate.py replays
    already-applied migrations against the post-migration schema and fails
    (e.g. 053 alters factions.power_level, which 058 already dropped).

    The fresh-story ``global_variables`` row is written before the migrations
    run (a pending migration may expect it). Any restore or migration failure
    raises before the fresh-slot IDF corpora are seeded and before the
    database is logged ready, so a half-built database is never reported ready.
    ``migrations_dir`` overrides the runner's migration tree (tests only).

    Raises:
        ValueError: If ``target_db`` is locked (``default_transaction_read_only``
            is on); nothing is terminated or dropped.
    """
    dispose_database(target_db)
    # NEXUS_template is the canonical fresh-slot image (schema + seed data)
    source_db = source_db or "NEXUS_template"
    tools = _postgres_tools("dropdb", "createdb", "pg_dump", "psql")
    _refuse_locked_target(target_db)

    if force:
        # Terminate active connections before dropping
        # Use raw psycopg2 for postgres admin DB (not in slot pool)
        admin_conn = psycopg2.connect(**connection_kwargs("postgres"))
        try:
            admin_conn.autocommit = True  # Required for pg_terminate_backend
            with admin_conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                    (target_db,),
                )
        finally:
            admin_conn.close()
        subprocess.run(
            [tools["dropdb"], "--if-exists", target_db],
            check=True,
            env=subprocess_env(),
        )
        LOG.warning("Dropped database %s if it existed", target_db)

    subprocess.run([tools["createdb"], target_db], check=True, env=subprocess_env())
    LOG.info("Created database %s", target_db)

    # Dump both public and assets schemas from template
    dump_cmd = [tools["pg_dump"], "-s", "-n", "public", "-n", "assets", source_db]
    LOG.info("Dumping schema (public + assets) from %s", source_db)
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".sql") as tmp:
        subprocess.run(dump_cmd, check=True, stdout=tmp, env=subprocess_env())
        tmp_path = tmp.name

    try:
        # Ensure required extensions exist in the new DB
        subprocess.run(
            [tools["psql"], target_db, "-c", "CREATE EXTENSION IF NOT EXISTS vector;"],
            check=True,
            env=subprocess_env(),
        )
        subprocess.run(
            [tools["psql"], target_db, "-c", "CREATE EXTENSION IF NOT EXISTS postgis;"],
            check=True,
            env=subprocess_env(),
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
        subprocess.run(
            [tools["psql"], "-v", "ON_ERROR_STOP=1", target_db, "-f", tmp_path],
            check=True,
            env=subprocess_env(),
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # Copy template data: seed/vocab rows plus schema_migrations stamps.
    _copy_template_data(source_db, target_db, tools)
    _require_migration_stamps(source_db, target_db)

    # Ensure global_variables row exists
    ensure_global_variables(target_db)

    # Apply only migrations newer than the template's stamped baseline. The
    # runner logs which migration failed; this refuses to call the slot ready.
    LOG.info("Running migrations on %s...", target_db)
    applied, unapplied = migrate_database(
        target_db, skip_locked=False, migrations_dir=migrations_dir
    )
    if unapplied:
        raise RuntimeError(
            f"Migrations failed on {target_db}: {applied} applied, "
            f"{unapplied} unapplied. The partial database was left in place; "
            "after fixing the failing migration, recreate it with --force "
            "(force=True)."
        )
    LOG.info("Applied %d migrations to %s", applied, target_db)

    _initialize_empty_idf_corpora(target_db)
    # Initialization mints the story identity (822-Q13); a reset recreates
    # the database and so mints a new one.
    connection = _connect(target_db)
    try:
        with connection as conn, conn.cursor() as cur:
            replace_story_identity(cur, origin="wizard")
    finally:
        if not USE_POOL:
            # A direct connection's context manager commits or rolls back but
            # never closes; a failed write must not hold target_db open.
            connection.close()
    dispose_database(target_db)
    LOG.info("Database %s ready", target_db)


def _initialize_empty_idf_corpora(dbname: str) -> None:
    """Seed fresh corpus identities without copying a source story's counters."""
    with _connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM narrative_chunks) "
            "OR EXISTS(SELECT 1 FROM retrograde_summaries)"
        )
        if cur.fetchone()[0]:
            raise RuntimeError("Fresh-slot IDF initialization requires empty corpora")
        cur.execute(
            """
            INSERT INTO memory_idf_corpora (corpus_kind, analyzer_version)
            SELECT kind, 'pg_catalog.english/v1/' || current_setting('server_version_num')
            FROM unnest(ARRAY['narrative', 'retrograde_summary']) AS kind
            ON CONFLICT (corpus_kind) DO NOTHING
            """
        )
        cur.execute(
            """
            SELECT count(*) FROM memory_idf_corpora
            WHERE document_count <> 0 OR analyzer_version <>
                'pg_catalog.english/v1/' || current_setting('server_version_num')
            """
        )
        if cur.fetchone()[0]:
            raise RuntimeError(
                "Fresh-slot IDF state has nonempty or mismatched corpora"
            )


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
    "public.natural_earth_features",
)


def _copy_template_data(source_db: str, target_db: str, tools: dict[str, str]) -> None:
    """Copy the seed image from the template into the freshly restored schema.

    Transfers exactly the seed/vocab tables and the schema_migrations
    baseline (TEMPLATE_SEED_TABLES) — never narrative or cache rows, even if
    the source database carries them. ON_ERROR_STOP keeps failures loud.
    """
    LOG.info("Copying template data (seed rows + migration stamps) from %s", source_db)
    dump_cmd = [tools["pg_dump"], "--data-only", source_db]
    for table in TEMPLATE_SEED_TABLES:
        dump_cmd.extend(["-t", table])
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".sql") as tmp:
        subprocess.run(dump_cmd, check=True, stdout=tmp, env=subprocess_env())
        tmp_path = tmp.name
    try:
        subprocess.run(
            [tools["psql"], "-v", "ON_ERROR_STOP=1", target_db, "-f", tmp_path],
            check=True,
            env=subprocess_env(),
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


def _restore_plain_dump(
    target_db: str, dump_path: str, tools: Mapping[str, str]
) -> None:
    """Replay a plain-text dump into ``target_db``, stopping at the first error.

    ``ON_ERROR_STOP`` makes psql exit non-zero on the first failing statement,
    and ``check=True`` turns that into ``subprocess.CalledProcessError``, so a
    half-restored database never reports success.
    """
    LOG.info("Restoring %s into %s", dump_path, target_db)
    subprocess.run(
        [tools["psql"], "-v", "ON_ERROR_STOP=1", target_db, "-f", dump_path],
        check=True,
        env=subprocess_env(),
    )


def clone_slot_with_data(
    slot: int,
    source_db: str,
    force: bool = False,
    *,
    target_db: Optional[str] = None,
) -> None:
    """
    Clone a slot by copying all data from source_db into save_XX.

    Uses a plain pg_dump replayed through psql to avoid template locks on the
    source DB. Every PostgreSQL tool is resolved before any change, and any
    failing step (including one statement of the dump) raises.
    ``target_db`` defaults to the slot's database; tests pass a disposable name.

    A clone is a fork (822-Q4): the copy gets a new ``story_uuid`` with origin
    ``clone``, and when the source held an identity row, one ``story_lineage``
    fork row names the source's ``story_uuid`` and ``source_db``. A source
    without a row (the template, an unbackfilled database) gives a ``clone``
    row and no lineage.

    Raises:
        ValueError: If ``slot`` is outside 1-5, or if ``target_db`` is locked
            (``default_transaction_read_only`` is on); nothing is dropped.
        RuntimeError: If the copy has no ``story_identity`` table (the source
            predates migration 146); run ``python scripts/migrate.py`` on it.
    """
    if slot < 1 or slot > 5:
        raise ValueError("Slot must be between 1 and 5 (inclusive)")
    if target_db is None:
        target_db = slot_dbname(slot)
    tools = _postgres_tools("dropdb", "createdb", "pg_dump", "psql")
    _refuse_locked_target(target_db)
    dispose_database(target_db)

    if force:
        subprocess.run(
            [tools["dropdb"], "--if-exists", target_db],
            check=True,
            env=subprocess_env(),
        )
        LOG.warning("Dropped database %s if it existed", target_db)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".sql") as tmp:
        dump_path = tmp.name

    try:
        # Plain text dump for easy filtering
        subprocess.run(
            [
                tools["pg_dump"],
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
            env=subprocess_env(),
        )
        subprocess.run([tools["createdb"], target_db], check=True, env=subprocess_env())

        # Ensure extensions before replaying functions/tables
        subprocess.run(
            [tools["psql"], target_db, "-c", "CREATE EXTENSION IF NOT EXISTS vector;"],
            check=True,
            env=subprocess_env(),
        )
        subprocess.run(
            [tools["psql"], target_db, "-c", "CREATE EXTENSION IF NOT EXISTS postgis;"],
            check=True,
            env=subprocess_env(),
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

        _restore_plain_dump(target_db, dump_path, tools)
        _post_clone_cleanup(target_db)
        # A clone is a fork (822-Q4): a new story_uuid with a parent link.
        connection = _connect(target_db)
        try:
            with connection as conn, conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.story_identity') IS NULL")
                if cur.fetchone()[0]:
                    raise RuntimeError(
                        f"{target_db} has no public.story_identity table: the "
                        f"source {source_db} predates migration 146. Run python "
                        f"scripts/migrate.py on {source_db}, then clone again."
                    )
                cur.execute("SELECT story_uuid::text FROM public.story_identity")
                copied = [row[0] for row in cur.fetchall()]
                child = replace_story_identity(cur, origin="clone")
                if copied:
                    record_fork(
                        cur,
                        child_uuid=child,
                        parent_uuid=copied[0],
                        source_dbname=source_db,
                        evidence=(
                            f"clone_slot_with_data copied {source_db} into {target_db}"
                        ),
                    )
        finally:
            if not USE_POOL:
                # As in initialize_slot_database: close the direct connection
                # on every path so a refusal cannot hold target_db open.
                connection.close()
        dispose_database(target_db)
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
    """Run slot setup from the command line.

    Logging is configured here, not at import, so a library importer (the
    new-story flow, the test fixtures) keeps its own root logger.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
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
        help=(
            "Drop and recreate the target slot database if it exists; "
            "a locked slot is refused"
        ),
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
