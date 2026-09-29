"""Integration test: fresh story databases inherit the template's migration baseline.

Template-derived databases used to re-run every migration because pg_dump -s
strips schema_migrations rows; replaying DDL migrations against the
post-migration schema fails (053 alters factions.power_level, which 058
already dropped). initialize_slot_database now copies the template's data —
seed/vocab rows plus the schema_migrations stamps — so migrate.py sees a
stamped baseline and applies nothing on a fresh clone.

Issue #810/#823 hardening: setup fails loudly. A template clone replays no
migration; a failing pending migration leaves no stamp and makes slot
initialization raise before the database is seeded as a story; a plain-dump
restore stops at its first failing statement; and the runner propagates a
connection error to an existing database instead of reporting nothing pending.

Uses throwaway databases created and dropped by the test itself. Live slots
(save_01 .. save_05) are never touched; NEXUS_template is only read.
"""

from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import shutil
import subprocess
from typing import Generator
import uuid

import psycopg2
from psycopg2 import sql
import pytest
import tomlkit

from scripts import migrate
from scripts import new_story_setup
from tests.pg_fixtures import (
    connect,
    disposable_database,
    disposable_slot_database,
    subprocess_env,
)

pytestmark = pytest.mark.requires_postgres

_SOURCE_DB = f"nexus_m10_template_test_{os.getpid()}"
_TARGET_DB = f"nexus_m10_fresh_test_{os.getpid()}"

_SEED_ROWS = [("alert", "faction"), ("grieving", "character")]


def _connect(dbname: str) -> psycopg2.extensions.connection:
    return connect(dbname)


def _all_known_migrations() -> list[tuple[str, str]]:
    """Every migration the runner would consider applied on a current template."""
    stamps = dict(migrate.BOOTSTRAP_MIGRATIONS)
    for version, name, _ in migrate.discover_migrations():
        stamps[version] = name
    return sorted(stamps.items())


@pytest.fixture
def template_db() -> Generator[str, None, None]:
    """A throwaway template: minimal schema, seed rows, full migration stamps."""
    subprocess.run(["createdb", _SOURCE_DB], check=True, env=subprocess_env())
    try:
        conn = _connect(_SOURCE_DB)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE SCHEMA assets;
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
                    CREATE TABLE public.event_types (id SERIAL PRIMARY KEY, name TEXT);
                    CREATE TABLE public.pair_tags (id SERIAL PRIMARY KEY, tag TEXT);
                    CREATE TABLE public.tag_category_registry (
                        id SERIAL PRIMARY KEY, category TEXT
                    );
                    CREATE TABLE assets.traits (id SERIAL PRIMARY KEY, name TEXT);
                    -- Non-seed table: rows here must NEVER reach a fresh slot,
                    -- even when --mode schema points at a populated source.
                    CREATE TABLE public.narrative_chunks (
                        id BIGSERIAL PRIMARY KEY,
                        raw_text TEXT
                    );
                    CREATE TABLE public.retrograde_summaries (
                        id BIGSERIAL PRIMARY KEY, summary_text TEXT
                    );
                    CREATE TABLE public.memory_idf_corpora (
                        corpus_kind TEXT PRIMARY KEY,
                        analyzer_version TEXT NOT NULL,
                        corpus_epoch BIGINT NOT NULL DEFAULT 0,
                        document_count BIGINT NOT NULL DEFAULT 0
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
                cur.execute(
                    "INSERT INTO public.narrative_chunks (raw_text) "
                    "VALUES ('story data that must stay behind')"
                )
        finally:
            conn.close()
        yield _SOURCE_DB
    finally:
        subprocess.run(
            ["dropdb", "--if-exists", _SOURCE_DB], check=False, env=subprocess_env()
        )


@pytest.mark.parametrize("desktop_reset", [False, True], ids=["fresh", "desktop-reset"])
def test_fresh_database_is_baseline_stamped(
    template_db: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    desktop_reset: bool,
) -> None:
    """A template-derived database carries stamps + seed rows; migrate is a no-op."""
    # The pooled connection path only accepts save_NN names; this test must
    # only ever touch its own throwaway databases.
    monkeypatch.setattr(new_story_setup, "USE_POOL", False)

    try:
        if desktop_reset:
            admin = _connect("postgres")
            admin.autocommit = True
            try:
                with admin.cursor() as cur:
                    cur.execute(
                        sql.SQL("CREATE DATABASE {}").format(sql.Identifier(_TARGET_DB))
                    )
            finally:
                admin.close()
            existing = _connect(_TARGET_DB)
            try:
                with existing, existing.cursor() as cur:
                    cur.execute("CREATE TABLE previous_story (content text)")
                    cur.execute(
                        "INSERT INTO previous_story VALUES ('erase this story')"
                    )
            finally:
                existing.close()

            # Model the desktop process's restricted PATH while still using
            # the real installed tools through the configured search paths.
            tool_dirs = set()
            for name in ("dropdb", "createdb", "pg_dump", "psql"):
                executable = shutil.which(name)
                assert executable is not None, f"PostgreSQL gate requires {name}"
                tool_dirs.add(str(Path(executable).parent))
            document = tomlkit.parse(
                (Path(__file__).resolve().parents[1] / "nexus.toml").read_text()
            )
            document["api"]["database"]["tool_search_paths"] = sorted(tool_dirs)
            config_path = tmp_path / "desktop.toml"
            config_path.write_text(tomlkit.dumps(document))
            with monkeypatch.context() as desktop:
                desktop.setenv("PATH", str(tmp_path))
                desktop.setenv("NEXUS_RUNTIME_CONFIG", str(config_path))
                new_story_setup.initialize_slot_database(
                    _TARGET_DB, source_db=template_db, force=True
                )
        else:
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
                cur.execute("SELECT COUNT(*) FROM public.narrative_chunks")
                narrative_count = cur.fetchone()[0]
                cur.execute("SELECT to_regclass('public.previous_story')")
                assert cur.fetchone()[0] is None
        finally:
            conn.close()

        assert stamped == expected_stamps, (
            f"missing stamps: {sorted(expected_stamps - stamped)}; "
            f"unexpected: {sorted(stamped - expected_stamps)}"
        )
        assert seeds == _SEED_ROWS
        assert global_row is not None and global_row[0] is True
        # Only the seed image crosses; story rows in the source stay behind.
        assert narrative_count == 0

        # The regression itself: a follow-up migrate run must be pure no-op —
        # nothing pending (already stamped), nothing failed (no 053 replay).
        applied, failed = migrate.migrate_database(_TARGET_DB, skip_locked=False)
        assert (applied, failed) == (0, 0)
    finally:
        subprocess.run(
            ["dropdb", "--if-exists", _TARGET_DB], check=False, env=subprocess_env()
        )


_TEMPLATE = "NEXUS_template"

# A pending migration that fails inside its transaction, in the repository's
# migration header style.
_FAILING_MIGRATION = """\
-- Migration 999: Fail Loudly (issue #810 test fixture)
--
-- Division by zero aborts the migration transaction, so the runner must roll
-- back, leave no 999 stamp, and report one unapplied migration.

SELECT 1/0;
"""


def _stamps(dbname: str) -> dict[str, object]:
    """Map every schema_migrations version in ``dbname`` to its applied_at."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT version, applied_at FROM public.schema_migrations")
        return dict(cur.fetchall())


def _failing_tree(tmp_path: Path) -> Path:
    """Copy the real migration tree and add a failing 999 migration."""
    tree = tmp_path / "migrations"
    shutil.copytree(
        migrate.MIGRATIONS_DIR,
        tree,
        ignore=shutil.ignore_patterns(*migrate.IGNORED_MIGRATION_ENTRIES),
    )
    (tree / "999_fail_loudly.sql").write_text(_FAILING_MIGRATION)
    return tree


def test_template_clone_replays_no_migration() -> None:
    """A NEXUS_template clone keeps the template's stamps and ends fully migrated.

    The template's stamps arrive with their original applied_at (copied, not
    re-applied); the only other stamps are migrations the template has not
    seen yet, which initialization applied; and a follow-up run is a no-op.
    """
    template_stamps = _stamps(_TEMPLATE)
    discovered = {version for version, _, _ in migrate.discover_migrations()}
    with disposable_slot_database("qa640_810_clone") as dbname:
        clone_stamps = _stamps(dbname)
        assert migrate.migrate_database(dbname, skip_locked=False) == (0, 0)

    copied = {version: clone_stamps.get(version) for version in template_stamps}
    assert copied == template_stamps
    assert set(clone_stamps) == set(template_stamps) | discovered


def test_failing_migration_is_unapplied_and_initialization_raises(
    tmp_path: Path,
) -> None:
    """A failing pending migration stays unstamped and aborts initialization."""
    tree = _failing_tree(tmp_path)
    with disposable_slot_database("qa640_810_fail") as dbname:
        assert migrate.migrate_database(
            dbname, skip_locked=False, migrations_dir=tree
        ) == (0, 1)
        assert "999" not in _stamps(dbname)

        with pytest.raises(
            RuntimeError,
            match=rf"^Migrations failed on {dbname}: \d+ applied, 1 unapplied\.",
        ):
            new_story_setup.initialize_slot_database(
                dbname, source_db=_TEMPLATE, force=True, migrations_dir=tree
            )

        assert "999" not in _stamps(dbname)
        # The raise precedes fresh-story seeding: no IDF corpus identities.
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM memory_idf_corpora")
            assert cur.fetchone()[0] == 0


def test_restore_plain_dump_stops_at_first_error(tmp_path: Path) -> None:
    """ON_ERROR_STOP turns a failing dump statement into CalledProcessError."""
    tools = new_story_setup._postgres_tools("psql")
    invalid = tmp_path / "invalid.sql"
    invalid.write_text(
        "CREATE TABLE restore_first (id integer);\n"
        "INSERT INTO restore_missing VALUES (1);\n"
        "CREATE TABLE restore_never (id integer);\n"
    )
    valid = tmp_path / "valid.sql"
    valid.write_text(
        "CREATE TABLE restore_ok (id integer);\n" "INSERT INTO restore_ok VALUES (7);\n"
    )
    with disposable_database("qa640_810_restore") as dbname:
        with pytest.raises(subprocess.CalledProcessError):
            new_story_setup._restore_plain_dump(dbname, str(invalid), tools)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('restore_never')")
            assert cur.fetchone()[0] is None

        new_story_setup._restore_plain_dump(dbname, str(valid), tools)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM restore_ok")
            assert cur.fetchall() == [(7,)]


def test_clone_with_data_restores_template_into_disposable_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The data clone replays a real dump under ON_ERROR_STOP into ``target_db``."""
    monkeypatch.setattr(new_story_setup, "USE_POOL", False)
    template_stamps = _stamps(_TEMPLATE)
    with disposable_database("qa640_810_dataclone") as dbname:
        new_story_setup.clone_slot_with_data(
            5, source_db=_TEMPLATE, force=True, target_db=dbname
        )
        assert _stamps(dbname) == template_stamps
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT new_story FROM public.global_variables WHERE id")
            assert cur.fetchone()[0] is True


def test_migrate_database_propagates_connection_errors() -> None:
    """A missing database is skipped; an unreachable existing one raises."""
    missing = f"qa640_does_not_exist_{uuid.uuid4().hex[:12]}"
    assert migrate.migrate_database(missing) == (0, 0)

    with disposable_database("qa640_810_noconn") as dbname:
        admin = connect("postgres")
        admin.autocommit = True
        try:
            with admin.cursor() as cur:
                cur.execute(
                    sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(
                        sql.Identifier(dbname)
                    )
                )
            try:
                with pytest.raises(psycopg2.Error):
                    migrate.migrate_database(dbname)
            finally:
                with admin.cursor() as cur:
                    cur.execute(
                        sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(
                            sql.Identifier(dbname)
                        )
                    )
        finally:
            admin.close()
