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

The implementation is nexus.maintenance.migrate; this module re-exports its names.
Assigning a name here does not change the implementation: patch
nexus.maintenance.migrate instead.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus.maintenance.migrate import (  # noqa: E402
    BOOTSTRAP_MIGRATIONS,
    IGNORED_MIGRATION_ENTRIES,
    LOG,
    MIGRATIONS_DIR,
    MIGRATION_FILENAME,
    PYTHON_MIGRATION_ALLOWLIST,
    SCRIPT_ONLY_MIGRATIONS,
    SLOT_DBS,
    TEMPLATE_DB,
    _load_python_migration,
    apply_migration,
    bootstrap_migrations,
    db_exists,
    discover_migrations,
    ensure_tracking_table,
    get_applied_migrations,
    get_connection,
    is_db_locked,
    main,
    migrate_database,
    migrate_targets,
    needs_bootstrap,
    show_status,
)

__all__ = [
    "BOOTSTRAP_MIGRATIONS",
    "IGNORED_MIGRATION_ENTRIES",
    "LOG",
    "MIGRATIONS_DIR",
    "MIGRATION_FILENAME",
    "PYTHON_MIGRATION_ALLOWLIST",
    "SCRIPT_ONLY_MIGRATIONS",
    "SLOT_DBS",
    "TEMPLATE_DB",
    "_load_python_migration",
    "apply_migration",
    "bootstrap_migrations",
    "db_exists",
    "discover_migrations",
    "ensure_tracking_table",
    "get_applied_migrations",
    "get_connection",
    "is_db_locked",
    "main",
    "migrate_database",
    "migrate_targets",
    "needs_bootstrap",
    "show_status",
]


if __name__ == "__main__":
    main()
