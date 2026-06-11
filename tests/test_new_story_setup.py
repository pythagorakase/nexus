"""Integration test: fresh story databases inherit the template's migration baseline.

Template-derived databases used to re-run every migration because pg_dump -s
strips schema_migrations rows; replaying DDL migrations against the
post-migration schema fails (053 alters factions.power_level, which 058
already dropped). initialize_slot_database now copies the template's data —
seed/vocab rows plus the schema_migrations stamps — so migrate.py sees a
stamped baseline and applies nothing on a fresh clone.

Uses throwaway databases created and dropped by the test itself. Live slots
(save_01 .. save_05) are never touched.
"""

from __future__ import annotations

import os
import subprocess
from typing import Generator

import psycopg2
import pytest

from scripts import migrate
from scripts import new_story_setup

pytestmark = pytest.mark.requires_postgres

_SOURCE_DB = f"nexus_m10_template_test_{os.getpid()}"
_TARGET_DB = f"nexus_m10_fresh_test_{os.getpid()}"

_SEED_ROWS = [("alert", "faction"), ("grieving", "character")]


def _connect(dbname: str) -> psycopg2.extensions.connection:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


def _all_known_migrations() -> list[tuple[str, str]]:
    """Every migration the runner would consider applied on a current template."""
    stamps = dict(migrate.BOOTSTRAP_MIGRATIONS)
    for version, name, _ in migrate.discover_migrations():
        stamps[version] = name
    return sorted(stamps.items())


@pytest.fixture
def template_db() -> Generator[str, None, None]:
    """A throwaway template: minimal schema, seed rows, full migration stamps."""
    subprocess.run(["createdb", _SOURCE_DB], check=True)
    try:
        conn = _connect(_SOURCE_DB)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE public.schema_migrations (
                        version TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE TABLE public.global_variables (
                        id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
                        new_story BOOLEAN,
                        model TEXT
                    );
                    CREATE TABLE public.tags (
                        id SERIAL PRIMARY KEY,
                        tag TEXT NOT NULL,
                        entity_kind TEXT NOT NULL
                    );
                    """
                )
                cur.executemany(
                    "INSERT INTO public.schema_migrations (version, name) "
                    "VALUES (%s, %s)",
                    _all_known_migrations(),
                )
                cur.executemany(
                    "INSERT INTO public.tags (tag, entity_kind) VALUES (%s, %s)",
                    _SEED_ROWS,
                )
        finally:
            conn.close()
        yield _SOURCE_DB
    finally:
        subprocess.run(["dropdb", "--if-exists", _SOURCE_DB], check=False)


def test_fresh_database_is_baseline_stamped(
    template_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A template-derived database carries stamps + seed rows; migrate is a no-op."""
    # The pooled connection path only accepts save_NN names; this test must
    # only ever touch its own throwaway databases.
    monkeypatch.setattr(new_story_setup, "USE_POOL", False)

    try:
        new_story_setup.initialize_slot_database(_TARGET_DB, source_db=template_db)

        expected_stamps = {version for version, _ in _all_known_migrations()}
        conn = _connect(_TARGET_DB)
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT version FROM public.schema_migrations")
                stamped = {row[0] for row in cur.fetchall()}
                cur.execute("SELECT tag, entity_kind FROM public.tags ORDER BY id")
                seeds = [tuple(row) for row in cur.fetchall()]
                cur.execute(
                    "SELECT new_story FROM public.global_variables WHERE id = TRUE"
                )
                global_row = cur.fetchone()
        finally:
            conn.close()

        assert stamped == expected_stamps, (
            f"missing stamps: {sorted(expected_stamps - stamped)}; "
            f"unexpected: {sorted(stamped - expected_stamps)}"
        )
        assert seeds == _SEED_ROWS
        assert global_row is not None and global_row[0] is True

        # The regression itself: a follow-up migrate run must be pure no-op —
        # nothing pending (already stamped), nothing failed (no 053 replay).
        applied, failed = migrate.migrate_database(_TARGET_DB, skip_locked=False)
        assert (applied, failed) == (0, 0)
    finally:
        subprocess.run(["dropdb", "--if-exists", _TARGET_DB], check=False)
