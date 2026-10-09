#!/usr/bin/env python3
"""
Database migration runner for NEXUS.

The sole migration runner: applies migrations to all slot databases and the
template database, and tracks applied migrations in a per-database
`schema_migrations` table. New migrations are SQL; Python migrations run only
when their version is in PYTHON_MIGRATION_ALLOWLIST.

Usage:
    python scripts/migrate.py --status          # Show pending migrations
    python scripts/migrate.py --all             # Apply to all unlocked DBs
    python scripts/migrate.py --slot 5          # Apply to specific slot
    python scripts/migrate.py --template        # Apply to NEXUS_template only
    python scripts/migrate.py --dbname ref_corpus  # Explicit evaluation DB
    python scripts/migrate.py --all --dry-run   # Show what would be applied
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable, List, Optional, Sequence, Tuple

import psycopg2

from nexus.api.db_pool import MaintenanceTarget
from nexus.database import connection_kwargs, maintenance_connection
from nexus.maintenance.database_targets import evaluation_dbname

LOG = logging.getLogger("nexus.migrate")

# The repository's migrations/ directory.
MIGRATIONS_DIR = Path(__file__).parents[2] / "migrations"
# Every migration is a file named NNN_name.sql or NNN_name.py.
MIGRATION_FILENAME = re.compile(r"^([0-9]{3})_([a-z0-9_]+)\.(sql|py)$")
# Interpreter and operating-system artifacts tolerated beside the migrations.
IGNORED_MIGRATION_ENTRIES = frozenset({"__pycache__", ".DS_Store"})
SCRIPT_ONLY_MIGRATIONS = {
    "008",  # migrations/008_populate_mock_database.py is a manual seed script.
}
# New migrations are SQL. Python is reserved for mechanics one SQL transaction
# cannot express (for example CREATE INDEX CONCURRENTLY); a new entry needs a
# comment giving its reason. Unlisted Python migrations abort discovery.
PYTHON_MIGRATION_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Historical Python migrations, preserved as written (#810).
        "008",
        "023",
        "025",
        "027",
        "028",
        "029",
        "030",
        "031",
        "032",
        "033",
        "034",
        "035",
        "036",
        "037",
        "038",
        "039",
        "042",
        "043",
        "045",
        "046",
        "047",
        "048",
        "049",
        "050",
        "051",
        "052",
        "053",
        "054",
        "055",
        "056",
        "057",
        "058",
        "059",
        "060",
        "061",
        "062",
        "078",
        "114",
        "126",
    }
)

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
    return psycopg2.connect(**connection_kwargs(dbname))


def is_db_locked(dbname: str) -> bool:
    """
    Check if a database is locked (read-only).

    Uses PostgreSQL's pg_db_role_setting to check for default_transaction_read_only.
    A connection or query error propagates: an unreadable lock state is not an
    unlocked database.
    """
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


def db_exists(dbname: str) -> bool:
    """Check if a database exists.

    A connection or query error propagates: an unreachable server is not a
    missing database.
    """
    conn = get_connection("postgres")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            return cur.fetchone() is not None
    finally:
        conn.close()


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
                LOG.info(
                    "  [DRY-RUN] Would drop old schema_migrations table (incompatible schema)"
                )
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
                );
                COMMENT ON TABLE schema_migrations IS
                    'Applied migration versions tracked by the migration runner.';
                COMMENT ON COLUMN schema_migrations.version IS
                    'Three-digit migration version from the migration filename or bootstrap list.';
                COMMENT ON COLUMN schema_migrations.name IS
                    'Migration name from the migration filename or bootstrap list.';
                COMMENT ON COLUMN schema_migrations.applied_at IS
                    'Database transaction timestamp when the migration stamp was inserted.';
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
        LOG.info(
            "  [DRY-RUN] Would bootstrap %d existing migrations",
            len(BOOTSTRAP_MIGRATIONS),
        )
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


def discover_migrations(
    migrations_dir: Optional[Path] = None,
) -> List[Tuple[str, str, Path]]:
    """
    Discover SQL and managed Python migration files.

    Every entry in ``migrations_dir`` (default: MIGRATIONS_DIR, read at call
    time) other than IGNORED_MIGRATION_ENTRIES must be a file matching
    MIGRATION_FILENAME whose version no other file uses, and every Python
    migration's version must be in PYTHON_MIGRATION_ALLOWLIST.

    Returns list of (version, name, path) tuples sorted by version.

    Raises:
        RuntimeError: If an entry is not a migration file, two files share a
            version, or a Python migration is not allowlisted.
    """
    root = MIGRATIONS_DIR if migrations_dir is None else migrations_dir
    migrations = []
    seen: dict[str, Path] = {}

    for path in sorted(root.iterdir()):
        if path.name in IGNORED_MIGRATION_ENTRIES:
            continue
        match = MIGRATION_FILENAME.match(path.name)
        if match is None or not path.is_file():
            raise RuntimeError(
                f"Unrecognized entry in {root}: {path}. Migrations are "
                "files named NNN_name.sql or NNN_name.py (lowercase snake_case)."
            )
        version, name, extension = match.groups()
        if version == "000":
            raise RuntimeError(
                f"Migration {path} uses version 000; versions start at 001, and a "
                "000 file would sort before every stamped migration and run against "
                "the current schema"
            )
        if version in seen:
            raise RuntimeError(
                f"Migration version {version} is used by both {seen[version]} "
                f"and {path}"
            )
        seen[version] = path
        if extension == "py" and version not in PYTHON_MIGRATION_ALLOWLIST:
            raise RuntimeError(
                f"Python migration {path} is not in PYTHON_MIGRATION_ALLOWLIST. "
                "New migrations are SQL; allowlist Python in scripts/migrate.py "
                "only with a reason comment."
            )
        if version in SCRIPT_ONLY_MIGRATIONS:
            continue
        migrations.append((version, name, path))

    return sorted(migrations, key=lambda x: x[0])


def _load_python_migration(path: Path) -> ModuleType:
    """Load a Python migration module from a filesystem path."""

    module_name = f"nexus_migration_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Python migration: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_migration(
    conn, version: str, name: str, path: Path, dry_run: bool = False
) -> bool:
    """
    Apply a single migration.

    Returns True if successful, False otherwise.
    """
    if dry_run:
        LOG.info("  [DRY-RUN] Would apply: %s_%s", version, name)
        return True

    try:
        if path.suffix == ".sql":
            sql = path.read_text()
            with conn.cursor() as cur:
                cur.execute("SET LOCAL nexus.write_producer = 'migration'")
                cur.execute(sql)
        elif path.suffix == ".py":
            # Python migrations may need to manage transaction boundaries
            # internally (for example CREATE INDEX CONCURRENTLY), so ensure the
            # connection is not inside an open transaction before handing it off.
            conn.commit()
            module = _load_python_migration(path)
            run = getattr(module, "run", None)
            if run is None:
                raise RuntimeError(f"Python migration {path.name} has no run(conn)")
            run(conn)
        else:
            raise RuntimeError(f"Unsupported migration type: {path}")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO schema_migrations (version, name)
                VALUES (%s, %s)
                """,
                (version, name),
            )
        conn.commit()
        LOG.info("  Applied: %s_%s", version, name)
        return True
    except (
        Exception
    ) as e:  # nexus-exception-disposition: fail; reason=rollback; safety=exit 1
        if getattr(conn, "autocommit", False):
            conn.autocommit = False
        conn.rollback()
        LOG.error("  FAILED: %s_%s - %s", version, name, e)
        return False


def migrate_database(
    dbname: str,
    dry_run: bool = False,
    skip_locked: bool = True,
    write_locked_slot: bool = False,
    migrations_dir: Optional[Path] = None,
    *,
    maintenance_target: MaintenanceTarget | None = None,
) -> Tuple[int, int]:
    """
    Apply pending migrations to a single database.

    Returns (applied_count, unapplied_count). The second value counts the
    pending migrations left unapplied after the first failure (the runner stops
    there and logs which migration failed); it is zero on success.

    Returns (0, 0) without touching anything when the database does not exist,
    or when it is locked and neither ``skip_locked=False`` nor
    ``write_locked_slot`` was given. Any other error, including a failure to
    connect to an existing database, propagates.

    The migration tree (``migrations_dir``, default MIGRATIONS_DIR) is
    validated before the database is touched, so a duplicate, misnamed, or
    unallowlisted migration fails without leaving a tracking table or bootstrap
    stamps behind.
    """
    if maintenance_target is not None and maintenance_target.dbname != dbname:
        raise ValueError("Maintenance target does not match migration database")
    all_migrations = discover_migrations(migrations_dir)

    if not db_exists(dbname):
        LOG.warning("Database %s does not exist, skipping", dbname)
        return (0, 0)

    if skip_locked and not write_locked_slot and is_db_locked(dbname):
        LOG.warning("Database %s is LOCKED (read-only), skipping", dbname)
        return (0, 0)

    LOG.info("Migrating %s...", dbname)

    if maintenance_target is not None:
        from nexus.runtime.slot_operations import require_authorized

        require_authorized(maintenance_target)
    conn = maintenance_connection(
        dbname, write_locked_slot=write_locked_slot, operation="migrate"
    )

    try:
        table_ready = ensure_tracking_table(conn, dry_run)

        if not table_ready:
            # In dry-run mode and table doesn't exist - show all migrations as pending
            LOG.info(
                "  [DRY-RUN] Would bootstrap %d existing migrations",
                len(BOOTSTRAP_MIGRATIONS),
            )
            pending = [
                m
                for m in all_migrations
                if m[0] not in {v for v, _ in BOOTSTRAP_MIGRATIONS}
            ]
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

        pending = [(v, n, p) for v, n, p in all_migrations if v not in applied]

        if not pending:
            LOG.info("  No pending migrations")
            return (0, 0)

    finally:
        conn.close()

    if dry_run:
        for version, name, _ in pending:
            LOG.info("  [DRY-RUN] Would apply: %s_%s", version, name)
        return (len(pending), 0)

    # Validators must not reuse a routine compiled by an earlier migration.
    # Bootstrap owns its connection; every pending migration gets a new backend.
    applied_count = 0
    for version, name, path in pending:
        if maintenance_target is not None:
            from nexus.runtime.slot_operations import require_authorized

            require_authorized(maintenance_target)
        conn = maintenance_connection(
            dbname, write_locked_slot=write_locked_slot, operation="migrate"
        )
        try:
            succeeded = apply_migration(conn, version, name, path, dry_run)
        finally:
            conn.close()
        if not succeeded:
            break
        applied_count += 1
    return (applied_count, len(pending) - applied_count)


def migrate_targets(
    targets: Sequence[str], migrate_one: Callable[[str], Tuple[int, int]]
) -> Tuple[int, int]:
    """
    Migrate each database in ``targets`` in order with ``migrate_one``.

    Returns the summed (applied_count, unapplied_count). A database whose
    migration fails reports it in its unapplied count and the run continues.
    A database that raises (for example, one that refuses connections) stops
    the run: the error log names the databases processed before it, the one
    that raised, and the ones not attempted, then the exception propagates.
    """
    total_applied = 0
    total_unapplied = 0
    for index, dbname in enumerate(targets):
        try:
            applied, unapplied = migrate_one(dbname)
        except Exception:
            LOG.error(
                "Stopped at %s, which raised. Processed before it: %s. "
                "Not attempted: %s.",
                dbname,
                ", ".join(targets[:index]) or "none",
                ", ".join(targets[index + 1 :]) or "none",
            )
            raise
        total_applied += applied
        total_unapplied += unapplied
    return (total_applied, total_unapplied)


def show_status() -> None:
    """Show migration status for all databases."""
    all_migrations = discover_migrations()
    print(f"Found {len(all_migrations)} managed migrations in {MIGRATIONS_DIR}\n")

    databases = [TEMPLATE_DB] + SLOT_DBS

    for dbname in databases:
        if not db_exists(dbname):
            print(f"{dbname}: [does not exist]")
            continue

        locked = is_db_locked(dbname)
        status = " [LOCKED]" if locked else ""
        print(f"{dbname}:{status}")

        if locked:
            print("  (locked - use --write-locked-slot to apply migrations)")
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

        except (
            psycopg2.Error
        ) as e:  # nexus-exception-disposition: fail; reason=status read; safety=printed
            print(f"  Error: {e}")
        print()  # Blank line between databases


def main():
    """Run the migration runner from the command line.

    Logging is configured here, not at import, so a library importer (the
    readiness checks, the test fixtures) keeps its own root logger.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
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
        "--dbname",
        type=evaluation_dbname,
        help="Apply only to an explicitly named qa640_* or ref_* database",
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

    parser.add_argument(
        "--write-locked-slot",
        action="store_true",
        help="Override read-only policy only for this maintenance session",
    )
    args = parser.parse_args()

    # Default to --status if no target specified
    if not any([args.all, args.slot, args.template, args.status, args.dbname]):
        args.status = True

    if args.status:
        show_status()
        return

    # Determine target databases
    if args.dbname:
        # Establish connectivity loudly before the legacy runner's skip paths.
        conn = get_connection(args.dbname)
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW default_transaction_read_only")
                if cur.fetchone()[0] == "on" and not args.write_locked_slot:
                    parser.error(f"Database {args.dbname} is read-only")
        finally:
            conn.close()
        targets = [args.dbname]
    elif args.all:
        targets = [TEMPLATE_DB] + SLOT_DBS
    elif args.slot:
        targets = [f"save_{args.slot:02d}"]
    elif args.template:
        targets = [TEMPLATE_DB]
    else:
        targets = []

    if args.dry_run:
        LOG.info("[DRY-RUN MODE - no changes will be made]")

    total_applied, total_skipped = migrate_targets(
        targets,
        lambda dbname: migrate_database(
            dbname, dry_run=args.dry_run, write_locked_slot=args.write_locked_slot
        ),
    )

    LOG.info("")
    LOG.info("Summary: %d applied, %d skipped/failed", total_applied, total_skipped)

    if args.dbname and not args.dry_run and total_skipped == 0:
        conn = get_connection(args.dbname)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*), max(version) FROM schema_migrations")
                count, level = cur.fetchone()
                LOG.info("%s: %s migration stamps; level %s", args.dbname, count, level)
        finally:
            conn.close()

    sys.exit(0 if total_skipped == 0 else 1)


if __name__ == "__main__":
    main()
