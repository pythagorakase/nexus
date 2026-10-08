"""Integration test: fresh story databases inherit the template's migration baseline.

Template-derived databases used to re-run every migration because pg_dump -s
strips schema_migrations rows; replaying DDL migrations against the
post-migration schema fails (053 alters factions.power_level, which 058
already dropped). initialize_slot_database now copies the template's data —
seed/vocab rows plus the schema_migrations stamps — so migrate.py sees a
stamped baseline and applies nothing on a fresh clone.

Issue #810/#823 hardening: setup fails loudly. A template clone replays no
migration; a failing pending migration leaves no stamp and makes slot
initialization raise before the fresh-slot IDF corpora are seeded; a plain-dump
restore stops at its first failing statement; and the runner propagates a
connection error to an existing database instead of reporting nothing pending.

Uses throwaway databases created and dropped by the test itself, including a
disposable stand-in for the template. Live slots (save_01 .. save_05) are
never touched; NEXUS_template is only read, by the stand-in's pg_dump.
"""

from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Generator
import uuid

import psycopg2
from psycopg2 import sql
import pytest
import tomlkit

from nexus.api import slot_utils
from nexus.api.save_slots import is_slot_locked
from scripts import migrate
from scripts import new_story_setup
from tests.pg_fixtures import (
    connect,
    disposable_database,
    disposable_slot_database,
    route_slot_to_disposable,
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
                    CREATE TABLE public.story_identity (
                        id boolean PRIMARY KEY DEFAULT TRUE CHECK (id),
                        story_uuid uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
                        title text,
                        origin text NOT NULL
                            CONSTRAINT story_identity_origin_check
                            CHECK (origin IN ('wizard', 'clone', 'import', 'backfill')),
                        created_at timestamptz NOT NULL DEFAULT now()
                    );
                    CREATE TABLE public.story_lineage (
                        child_uuid uuid NOT NULL
                            REFERENCES public.story_identity (story_uuid)
                            ON DELETE CASCADE,
                        parent_uuid uuid NOT NULL,
                        relation text NOT NULL
                            CONSTRAINT story_lineage_relation_check
                            CHECK (relation = 'fork'),
                        source_dbname text NOT NULL,
                        evidence text NOT NULL,
                        recorded_at timestamptz NOT NULL DEFAULT now(),
                        PRIMARY KEY (child_uuid, parent_uuid),
                        CONSTRAINT story_lineage_not_self
                            CHECK (child_uuid <> parent_uuid)
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


# The migration the template stand-in lags on purpose. Migration 135 is
# comment-only and idempotent (its header says so): undoing it is setting each
# comment it writes back to NULL, and reapplying it on top of the later schema
# restores them. A clone of the stand-in must apply it after copying the
# stand-in's stamps, which is the path a real template takes whenever a branch
# adds a migration the fleet template has not seen.
_LAGGING_MIGRATION = "135"
# One object migration 135 comments, read back to prove it was reapplied.
_LAG_PROBE_SQL = "SELECT obj_description('public.orrery_job_state'::regtype, 'pg_type')"


def _lagging_comment_targets() -> list[str]:
    """Every ``COMMENT ON <target> IS`` target in the lagging migration."""
    (path,) = [
        path
        for version, _, path in migrate.discover_migrations()
        if version == _LAGGING_MIGRATION
    ]
    targets = re.findall(r"^COMMENT ON (.+) IS$", path.read_text(), flags=re.M)
    assert targets, f"migration {_LAGGING_MIGRATION} writes no comment"
    return targets


def _lag_probe(dbname: str) -> object:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(_LAG_PROBE_SQL)
        return cur.fetchone()[0]


@pytest.fixture(scope="module")
def template_source() -> Generator[str, None, None]:
    """A disposable stand-in for the canonical template, shared by the module.

    ``disposable_slot_database`` builds it the way every fresh slot is built
    from ``NEXUS_template`` (schema, seed rows, and the template's stamps with
    their original applied_at, then any migration the template lags), so it
    starts as a stamped, fully migrated template image. The fixture then rolls
    back ``_LAGGING_MIGRATION`` (its comments and its stamp), so the stand-in
    lags ``main`` by one migration the way the fleet template does whenever a
    branch adds one. These tests read and clone it; the owner's
    ``NEXUS_template`` is read only by that initial pg_dump.
    """
    with disposable_slot_database("qa640_810_template") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            for target in _lagging_comment_targets():
                cur.execute(f"COMMENT ON {target} IS NULL")
            cur.execute(
                "DELETE FROM public.schema_migrations WHERE version = %s",
                (_LAGGING_MIGRATION,),
            )
            assert cur.rowcount == 1, "the stand-in carries no lagging stamp"
        assert _lag_probe(dbname) is None
        yield dbname


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


def test_template_clone_replays_no_migration(template_source: str) -> None:
    """A template clone keeps the template's stamps and ends fully migrated.

    The template's stamps arrive with their original applied_at (copied, not
    re-applied); the only other stamps are migrations the template has not
    seen yet, which initialization applied; and a follow-up run is a no-op.
    The stand-in lags ``_LAGGING_MIGRATION``, so the applied branch runs.
    """
    template_stamps = _stamps(template_source)
    discovered = {version for version, _, _ in migrate.discover_migrations()}
    # The lag branch is proven, not vacuous: the stand-in misses a migration.
    assert discovered - set(template_stamps) == {_LAGGING_MIGRATION}
    with disposable_slot_database(
        "qa640_810_clone", source_db=template_source
    ) as dbname:
        clone_stamps = _stamps(dbname)
        # Initialization applied the lagging migration's effect, not only
        # its stamp.
        assert _lag_probe(dbname)
        # Idempotence check only: initialization already raises on any
        # unapplied migration. The applied_at and stamp-set assertions below
        # are the proof that nothing was replayed.
        assert migrate.migrate_database(dbname, skip_locked=False) == (0, 0)

    copied = {version: clone_stamps.get(version) for version in template_stamps}
    assert copied == template_stamps
    assert set(clone_stamps) == set(template_stamps) | discovered


def test_template_clone_first_runner_pass_applies_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, template_source: str
) -> None:
    """A raw template clone's first runner pass finds nothing to replay.

    The runner sees a tree holding only the migrations the template has
    stamped, so the result does not depend on how far the fleet template lags
    ``main``. Initialization copies the template's stamps with their original
    applied_at and adds none: nothing was replayed on the first pass.
    """
    monkeypatch.setattr(new_story_setup, "USE_POOL", False)
    template_stamps = _stamps(template_source)
    tree = tmp_path / "migrations"
    tree.mkdir()
    for version, _, path in migrate.discover_migrations():
        if version in template_stamps:
            shutil.copy2(path, tree / path.name)

    with disposable_database("qa640_810_firstpass") as dbname:
        new_story_setup.initialize_slot_database(
            dbname, source_db=template_source, force=True, migrations_dir=tree
        )
        assert _stamps(dbname) == template_stamps


def test_failing_migration_is_unapplied_and_initialization_raises(
    tmp_path: Path, template_source: str
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
        ) as raised:
            new_story_setup.initialize_slot_database(
                dbname, source_db=template_source, force=True, migrations_dir=tree
            )
        assert "partial database was left in place" in str(raised.value)
        assert "recreate it with --force (force=True)" in str(raised.value)

        assert "999" not in _stamps(dbname)
        # The raise precedes the fresh-slot IDF corpora and the "ready" log
        # line (the global_variables row is already written by then).
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
    monkeypatch: pytest.MonkeyPatch, template_source: str
) -> None:
    """The data clone replays a real dump under ON_ERROR_STOP into ``target_db``."""
    monkeypatch.setattr(new_story_setup, "USE_POOL", False)
    template_stamps = _stamps(template_source)
    with disposable_database("qa640_810_dataclone") as dbname:
        new_story_setup.clone_slot_with_data(
            5, source_db=template_source, force=True, target_db=dbname
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


# Issue #823: setup refuses a locked target before any drop. The lock is
# ``default_transaction_read_only=on`` on the database, which blocks writes
# inside it but not ``dropdb``, which connects to another database.
_MARKER_TABLE = "qa823_marker"
_MARKER_ROW = "the story that must survive"


def _set_read_only(dbname: str, value: str) -> None:
    """Set the database-level read-only default to ``value`` (on or off)."""
    admin = connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "ALTER DATABASE {} SET default_transaction_read_only = {}"
                ).format(sql.Identifier(dbname), sql.SQL(value))
            )
    finally:
        admin.close()


def _database_oid(dbname: str) -> int:
    with closing(connect("postgres")) as conn, conn.cursor() as cur:
        cur.execute("SELECT oid FROM pg_database WHERE datname = %s", (dbname,))
        row = cur.fetchone()
    assert row is not None, f"{dbname} does not exist"
    return int(row[0])


def _plant_marker(dbname: str) -> int:
    """Create the marker table with one row; return the database's oid."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE TABLE {} (note text)").format(sql.Identifier(_MARKER_TABLE))
        )
        cur.execute(
            sql.SQL("INSERT INTO {} VALUES (%s)").format(sql.Identifier(_MARKER_TABLE)),
            (_MARKER_ROW,),
        )
    return _database_oid(dbname)


def _marker_rows(dbname: str) -> list[tuple[str, ...]]:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT note FROM {}").format(sql.Identifier(_MARKER_TABLE))
        )
        return [tuple(row) for row in cur.fetchall()]


def _marker_exists(dbname: str) -> bool:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{_MARKER_TABLE}",))
        return cur.fetchone()[0] is not None


def test_initialize_refuses_locked_target(
    monkeypatch: pytest.MonkeyPatch, template_source: str
) -> None:
    """A locked target survives ``initialize_slot_database(force=True)``."""
    monkeypatch.setattr(new_story_setup, "USE_POOL", False)
    with disposable_database("qa640_823_locked_init") as dbname:
        oid = _plant_marker(dbname)
        _set_read_only(dbname, "on")

        kept: ValueError | None = None
        try:
            new_story_setup.initialize_slot_database(
                dbname, source_db=template_source, force=True
            )
        except ValueError as error:
            kept = error

        assert _database_oid(dbname) == oid
        assert _marker_rows(dbname) == [(_MARKER_ROW,)]
        assert is_slot_locked(0, dbname=dbname) is True
        assert kept is not None
        assert str(kept) == new_story_setup._locked_target_message(dbname)


def test_clone_refuses_locked_target(
    monkeypatch: pytest.MonkeyPatch, template_source: str
) -> None:
    """A locked target survives ``clone_slot_with_data(force=True)``."""
    monkeypatch.setattr(new_story_setup, "USE_POOL", False)
    with disposable_database("qa640_823_locked_clone") as dbname:
        oid = _plant_marker(dbname)
        _set_read_only(dbname, "on")

        kept: ValueError | None = None
        try:
            new_story_setup.clone_slot_with_data(
                5, source_db=template_source, force=True, target_db=dbname
            )
        except ValueError as error:
            kept = error

        assert _database_oid(dbname) == oid
        assert _marker_rows(dbname) == [(_MARKER_ROW,)]
        assert is_slot_locked(0, dbname=dbname) is True
        assert kept is not None
        assert str(kept) == new_story_setup._locked_target_message(dbname)


@pytest.mark.parametrize("path", ["init", "clone"])
def test_unlocked_setting_off_proceeds(
    monkeypatch: pytest.MonkeyPatch, template_source: str, path: str
) -> None:
    """``default_transaction_read_only = off`` (what unlock writes) is unlocked."""
    monkeypatch.setattr(new_story_setup, "USE_POOL", False)
    with disposable_database(f"qa640_823_unlocked_{path}") as dbname:
        oid = _plant_marker(dbname)
        _set_read_only(dbname, "off")
        assert is_slot_locked(0, dbname=dbname) is False

        if path == "init":
            new_story_setup.initialize_slot_database(
                dbname, source_db=template_source, force=True
            )
        else:
            new_story_setup.clone_slot_with_data(
                5, source_db=template_source, force=True, target_db=dbname
            )

        assert not _marker_exists(dbname)
        assert _database_oid(dbname) != oid


def test_locked_target_message_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """A slot gets reset's text; any other name, routed or not, gets none."""
    assert (
        new_story_setup._locked_target_message("save_01")
        == "Slot 1 is locked. Unlock it first with: nexus unlock --slot 1"
    )
    probe = "qa640_823_route_probe"
    database_text = new_story_setup._locked_target_message(probe)
    assert probe in database_text
    assert "nexus unlock" not in database_text

    route_slot_to_disposable(monkeypatch.setattr, slot=5, dbname=probe)
    assert slot_utils.VALID_DBNAMES == {probe}
    assert new_story_setup._locked_target_message(probe) == database_text
