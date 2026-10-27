"""#813 migration 154 guards on full-data disposable clones.

Migration 154 drops the six legacy vector-helper functions and seven all-NULL
legacy columns behind a catalog-identity, row, dependency, stored-definition
and dynamic-SQL guard, and comments the two retained provenance columns.
Sources are read ONLY by read-only pg_dump subprocesses; every driver targets
postgres or a qa640_813_154_* allocation from tests.pg_fixtures. All provider
pins are TEST.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

import pytest

from nexus.api.db_pool import close_all_pools
from nexus.config.story_model import StorySettings, write_story_settings
from nexus.maintenance import migrate
from tests.pg_fixtures import (
    connect,
    disposable_database,
    require_disposable_target,
    route_slot_to_disposable,
    seed_committed_chunk,
    seed_protagonist,
    subprocess_env,
)

pytestmark = pytest.mark.requires_postgres
ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "tests/fixtures/813_pre143_manifest.json").read_text())
COLUMNS_FIXTURE = ROOT / "tests/fixtures/813_pre154_columns.sql"
MIGRATION = ROOT / "migrations/154_drop_vector_helpers_and_legacy_columns.sql"
SLUG = "drop_vector_helpers_and_legacy_columns"
SOURCES = ("NEXUS_template", "save_01", "save_02", "save_03", "save_04", "save_05")
CLONE_PREFIX = "qa640_813_154"

FUNCTIONS = {
    "public.hybrid_search(text,bytea,double precision,double precision,integer,text)": (
        "36fb85af820eff8182f252abaeac2a33"
    ),
    (
        "public.hybrid_search(text,public.vector,double precision,"
        "double precision,integer,text)"
    ): "9c990bf25cc932df73413510183f01e1",
    (
        "public.hybrid_search(text,public.vector,double precision,"
        "double precision,integer,text,text[])"
    ): "bf4098a509bf993ced0967bf3518d408",
    "public.migrate_embeddings()": "fdb7a2ac64ccd83eb2edbf29c5527a85",
    "public.pad_vector_384_to_1024(public.vector)": "6a08f7bb736fdbdd24e9266b2d948281",
    "public.pad_vector_to_1024(public.vector)": "cc3741074399976ff5501e875faf0b5b",
}
COLUMNS = (
    ("assets", "new_story_creator", "seed_starting_location", "text"),
    ("assets", "new_story_creator", "seed_initial_mystery", "text"),
    ("assets", "new_story_creator", "seed_potential_obstacles", "text[]"),
    ("assets", "new_story_creator", "zone_boundary_description", "text"),
    ("assets", "new_story_creator", "zone_approximate_area", "text"),
    ("public", "entity_tags", "clear_on_override", "jsonb"),
    ("public", "world_events", "narration_chunk_id", "bigint"),
)
TABLES = ("assets.new_story_creator", "public.entity_tags", "public.world_events")
FOREIGN_KEY = "world_events_narration_chunk_id_fkey"
FOREIGN_KEY_DEF = "FOREIGN KEY (narration_chunk_id) REFERENCES offscreen_narrations(id)"
PROVIDER_COMMENT = (
    "Provider name a job recorded under the retired provider-era narration "
    "path. Retained as provenance: the deterministic descriptor drain "
    "(drain_narration_outbox_sync) never uses it to make a call, and the "
    "current job insert writes no value, so new jobs hold NULL."
)
MODEL_REF_COMMENT = (
    "Model identifier a job recorded under the retired provider-era narration "
    "path, paired with provider. Retained as provenance: the descriptor drain "
    "never uses it to make a call, and the current job insert writes no value, "
    "so new jobs hold NULL."
)


def _dump_sources(sources: tuple[str, ...], directory: Path) -> dict[str, Path]:
    """Take read-only custom dumps of the named sources."""
    result = {}
    for source in sources:
        archive = directory / (source + ".dump")
        env = subprocess_env()
        env["PGOPTIONS"] = (
            env.get("PGOPTIONS", "") + " -c default_transaction_read_only=on"
        )
        subprocess.run(
            ["pg_dump", "--format=custom", "--file", str(archive), "--dbname", source],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=540,
        )
        result[source] = archive
    return result


@pytest.fixture(scope="module")
def archives() -> Iterator[dict[str, Path]]:
    """Ordinary cases dump only the template and delete the archive at exit."""
    with tempfile.TemporaryDirectory(prefix="813-154-template-") as directory:
        yield _dump_sources(("NEXUS_template",), Path(directory))


@pytest.fixture(scope="module")
def fleet_archives(
    archives: dict[str, Path], request: pytest.FixtureRequest
) -> Iterator[dict[str, Path]]:
    """Only the corpus-selected fleet test may read save slots, via pg_dump."""
    if not any(
        item.get_closest_marker("requires_corpus") for item in request.session.items
    ):
        raise RuntimeError("fleet_archives requires a requires_corpus test")
    if os.environ.get("NEXUS_RUN_CORPUS") != "1":
        raise RuntimeError("fleet archives require NEXUS_RUN_CORPUS=1")
    with tempfile.TemporaryDirectory(prefix="813-154-corpus-") as directory:
        yield {**archives, **_dump_sources(SOURCES[1:], Path(directory))}


def _pre154_state(cur: Any) -> dict[str, Any]:
    """The target catalog as the fixture builds it, independent of OIDs/attnums."""
    state: dict[str, Any] = {}
    for signature in FUNCTIONS:
        cur.execute(
            "SELECT l.lanname,p.prosecdef,p.proconfig,md5(p.prosrc) "
            "FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang "
            "WHERE p.oid=to_regprocedure(%s)",
            (signature,),
        )
        state[signature] = cur.fetchone()
    for schema, table, column, _ in COLUMNS:
        cur.execute(
            "SELECT format_type(a.atttypid,a.atttypmod),a.attnotnull,a.atthasdef,"
            "a.attgenerated FROM pg_attribute a "
            "WHERE a.attrelid=to_regclass(%s) AND a.attname=%s AND NOT a.attisdropped",
            (f"{schema}.{table}", column),
        )
        state[f"{schema}.{table}.{column}"] = cur.fetchone()
    cur.execute(
        "SELECT pg_get_constraintdef(oid),confrelid::regclass::text FROM pg_constraint "
        "WHERE conname=%s AND conrelid='public.world_events'::regclass",
        (FOREIGN_KEY,),
    )
    state[FOREIGN_KEY] = cur.fetchone()
    return state


EXPECTED_PRE154 = {
    **{s: ("plpgsql", False, None, md5) for s, md5 in FUNCTIONS.items()},
    **{f"{s}.{t}.{c}": (kind, False, False, "") for s, t, c, kind in COLUMNS},
    FOREIGN_KEY: (FOREIGN_KEY_DEF, "offscreen_narrations"),
}


def _prepare_pre154(dbname: str) -> None:
    """Rebuild the targets on a clone stamped 154; otherwise assert they match."""
    require_disposable_target(dbname)
    assert dbname.startswith(CLONE_PREFIX + "_"), dbname
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM schema_migrations WHERE version='154'")
        if cur.fetchone()[0]:
            cur.execute(";\n".join(f[3] for f in MANIFEST["deferred_functions"]))
            cur.execute(COLUMNS_FIXTURE.read_text())
            cur.execute("DELETE FROM schema_migrations WHERE version='154'")
            assert cur.rowcount == 1
        assert _pre154_state(cur) == EXPECTED_PRE154, "pre-154 catalog drift"


@contextmanager
def _clone(
    archives: dict[str, Path], tmp_path: Path, source: str = "NEXUS_template"
) -> Iterator[str]:
    """Restore a source, migrate it through every migration but 154, pin TEST."""
    tree = tmp_path / "preceding"
    tree.mkdir(exist_ok=True)
    for version, _, path in migrate.discover_migrations():
        if version != "154":
            shutil.copy2(path, tree / path.name)
    with disposable_database(CLONE_PREFIX) as dbname:
        require_disposable_target(dbname)
        subprocess.run(
            [
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "--dbname",
                dbname,
                str(archives[source]),
            ],
            env=subprocess_env(),
            check=True,
            capture_output=True,
            text=True,
            timeout=540,
        )
        applied, failed = migrate.migrate_database(
            dbname, skip_locked=False, migrations_dir=tree
        )
        assert failed == 0, (applied, failed)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO global_variables(id,new_story) VALUES(true,true)"
                " ON CONFLICT(id) DO NOTHING"
            )
            write_story_settings(
                cur, StorySettings(skald_model="TEST", gaia_model=None)
            )
        _prepare_pre154(dbname)
        yield dbname


def _apply(dbname: str) -> bool:
    with closing(connect(dbname)) as conn:
        return migrate.apply_migration(conn, "154", SLUG, MIGRATION)


def _sql(dbname: str, statement: str, params: Any = None) -> None:
    require_disposable_target(dbname)
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(statement, params)


def _snapshot(dbname: str) -> str:
    """Hash the whole pg_dump (schema, data, comments, stamps)."""
    result = subprocess.run(
        ["pg_dump", "--dbname", dbname],
        env=subprocess_env(),
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    text = re.sub(r"^\\(?:un)?restrict .*\n", "", result.stdout, flags=re.MULTILINE)
    return hashlib.sha256(text.encode()).hexdigest()


def _stamped(dbname: str) -> bool:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM schema_migrations WHERE version='154'")
        return bool(cur.fetchone()[0])


def _routines(dbname: str) -> list[Any]:
    """Every application routine with oid, definition, owner, ACL and comment."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT p.oid,n.nspname,p.proname,pg_get_functiondef(p.oid),"
            "p.proowner,p.proacl,p.proconfig,obj_description(p.oid,'pg_proc') "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE p.oid >= 16384 AND n.nspname !~ '^pg_(temp|toast)' "
            "AND p.prokind IN ('f','p','w') ORDER BY p.oid"
        )
        return cur.fetchall()


def _table_columns(dbname: str) -> list[Any]:
    """Every live column of the three altered tables, by name."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT n.nspname||'.'||c.relname,a.attnum,a.attname,"
            "format_type(a.atttypid,a.atttypmod),a.attnotnull,"
            "pg_get_expr(d.adbin,d.adrelid),col_description(c.oid,a.attnum) "
            "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum "
            "WHERE c.oid = ANY(%s::regclass[]) AND a.attnum>0 AND NOT a.attisdropped "
            "ORDER BY 1,2",
            (list(TABLES),),
        )
        return cur.fetchall()


def _target_ids(dbname: str) -> set[int]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT to_regprocedure(s)::oid FROM unnest(%s::text[]) s",
            (list(FUNCTIONS),),
        )
        return {row[0] for row in cur.fetchall()}


def _assert_refused(
    dbname: str, caplog: pytest.LogCaptureFixture, *expected: str
) -> None:
    """The runner returns False, logs the reason, and leaves no trace."""
    before = _snapshot(dbname)
    caplog.clear()
    assert not _apply(dbname)
    assert "target " in caplog.text, caplog.text
    for text in expected:
        assert text in caplog.text, caplog.text
    assert _snapshot(dbname) == before, "partial migration or changed row/comment"
    assert not _stamped(dbname)
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        assert all(
            row is not None for row in _pre154_state(cur).values()
        ), "a target vanished"


def test_migration_154_drops_exactly_its_targets(
    archives: dict[str, Path], tmp_path: Path
) -> None:
    """Six functions, seven columns and one foreign key go; nothing else moves."""
    with _clone(archives, tmp_path) as dbname:
        targets = _target_ids(dbname)
        assert len(targets) == 6 and None not in targets
        routines = [r for r in _routines(dbname) if r[0] not in targets]
        dropped = {(f"{s}.{t}", c) for s, t, c, _ in COLUMNS}
        columns = [c for c in _table_columns(dbname) if (c[0], c[2]) not in dropped]
        assert len(columns) == len(_table_columns(dbname)) - len(COLUMNS)

        assert _apply(dbname)

        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            state = _pre154_state(cur)
            assert all(value is None for value in state.values()), state
            cur.execute(
                "SELECT count(*) FROM pg_constraint WHERE conname=%s", (FOREIGN_KEY,)
            )
            assert cur.fetchone() == (0,)
            cur.execute(
                "SELECT col_description('public.orrery_narration_jobs'::regclass,"
                "a.attnum) FROM pg_attribute a WHERE a.attrelid="
                "'public.orrery_narration_jobs'::regclass AND a.attname=ANY(%s) "
                "ORDER BY a.attname",
                (["model_ref", "provider"],),
            )
            assert cur.fetchall() == [(MODEL_REF_COMMENT,), (PROVIDER_COMMENT,)]
        assert _stamped(dbname)
        assert _routines(dbname) == routines
        assert _table_columns(dbname) == columns
        assert migrate.migrate_database(dbname, skip_locked=False) == (0, 0)


def _seed_non_null(dbname: str, column: str) -> None:
    """Write one real non-NULL value into the named target column."""
    if column in {c for s, t, c, _ in COLUMNS if t == "new_story_creator"}:
        value = "{probe}" if column == "seed_potential_obstacles" else "probe"
        _sql(
            dbname,
            f"INSERT INTO assets.new_story_creator (id, {column}) VALUES (true, %s)",
            (value,),
        )
        return
    _, entity_id = seed_protagonist(dbname)
    if column == "clear_on_override":
        _sql(
            dbname,
            "INSERT INTO entity_tags (entity_id, tag_id, source_kind, "
            "clear_on_override) SELECT %s, min(id), 'system', '{}'::jsonb FROM tags",
            (entity_id,),
        )
        return
    assert column == "narration_chunk_id", column
    chunk_id = seed_committed_chunk(dbname, raw_text="Migration 154 probe anchor.")
    _sql(
        dbname,
        "WITH r AS (INSERT INTO orrery_resolutions (tick_chunk_id, template_id, "
        "binding_hash, priority, state_delta) VALUES (%(chunk)s, 'probe154', "
        "'probe154', 0, '{}'::jsonb) RETURNING id), n AS (INSERT INTO "
        "offscreen_narrations (resolution_id, tick_chunk_id, text) SELECT id, "
        "%(chunk)s, 'Migration 154 probe narration.' FROM r RETURNING id) "
        "INSERT INTO world_events (event_type, tick_chunk_id, source, "
        "narration_chunk_id) SELECT (SELECT min(type) FROM event_types), "
        "%(chunk)s, 'resolver', id FROM n",
        {"chunk": chunk_id},
    )


@pytest.mark.parametrize("column", [c for _, _, c, _ in COLUMNS])
def test_migration_154_refuses_a_non_null_value_atomically(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    column: str,
) -> None:
    """One real non-NULL value refuses the whole migration by column name."""
    with _clone(archives, tmp_path) as dbname:
        _seed_non_null(dbname, column)
        _assert_refused(dbname, caplog, column, "non-NULL")


PLANTED = {
    "perform": (
        "CREATE FUNCTION public.probe154() RETURNS void LANGUAGE plpgsql AS "
        "$probe$BEGIN PERFORM public.pad_vector_to_1024(NULL); END$probe$",
        ("probe154", "pad_vector_to_1024"),
    ),
    "execute-literal": (
        "CREATE FUNCTION public.probe154() RETURNS void LANGUAGE plpgsql AS "
        "$probe$BEGIN EXECUTE 'SELECT * FROM public.hybrid_search(NULL::text, "
        "NULL::bytea, 0, 1, 1, NULL::text)'; END$probe$",
        ("probe154", "hybrid_search", "dynamic SQL"),
    ),
    "execute-concat": (
        "CREATE FUNCTION public.probe154() RETURNS void LANGUAGE plpgsql AS "
        "$probe$BEGIN EXECUTE 'SELECT public.hybrid_' || 'search(NULL)'; "
        "END$probe$",
        ("probe154", "dynamic SQL"),
    ),
    "sql-column": (
        "CREATE FUNCTION public.probe154() RETURNS text LANGUAGE sql AS "
        "$probe$SELECT seed_starting_location FROM assets.new_story_creator"
        "$probe$",
        ("probe154", "seed_starting_location"),
    ),
    "view": (
        "CREATE VIEW public.probe154 AS SELECT narration_chunk_id "
        "FROM public.world_events",
        ("probe154", "narration_chunk_id"),
    ),
    "default": (
        "CREATE TABLE public.probe154 (marker text DEFAULT "
        "(public.migrate_embeddings())::text)",
        ("probe154", "migrate_embeddings"),
    ),
}


@pytest.mark.parametrize("case", PLANTED)
def test_migration_154_refuses_a_planted_caller_atomically(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    """A planted reference, static or dynamic, refuses the whole migration."""
    statement, expected = PLANTED[case]
    with _clone(archives, tmp_path) as dbname:
        _sql(dbname, "SET LOCAL check_function_bodies=off; " + statement)
        _assert_refused(dbname, caplog, *expected)
        if case == "execute-concat":
            assert "names hybrid_search" not in caplog.text, caplog.text


IDENTITY = {
    "function-body": (
        "CREATE OR REPLACE FUNCTION public.pad_vector_to_1024(v public.vector) "
        "RETURNS public.vector LANGUAGE plpgsql AS $probe$BEGIN RETURN v; "
        "END$probe$",
        ("public.pad_vector_to_1024(public.vector)", "body md5"),
    ),
    "column-type": (
        "ALTER TABLE public.entity_tags ALTER COLUMN clear_on_override TYPE text",
        ("public.entity_tags.clear_on_override", "type is text"),
    ),
}


@pytest.mark.parametrize("case", IDENTITY)
def test_migration_154_refuses_a_changed_identity(
    archives: dict[str, Path],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    """A changed function body or column type refuses before any drop."""
    statement, expected = IDENTITY[case]
    with _clone(archives, tmp_path) as dbname:
        _sql(dbname, statement)
        before = _snapshot(dbname)
        caplog.clear()
        assert not _apply(dbname)
        for text in expected:
            assert text in caplog.text, caplog.text
        assert _snapshot(dbname) == before
        assert not _stamped(dbname)


def test_write_seed_runs_after_154(
    archives: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seed writer names no dropped column and still clears allies."""
    from nexus.api.new_story_cache import init_cache, write_seed

    with _clone(archives, tmp_path) as dbname:
        assert _apply(dbname)
        route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
        try:
            init_cache(dbname, "thread-813-154", 4)
            _sql(
                dbname,
                "UPDATE assets.new_story_creator "
                "SET seed_potential_allies = ARRAY['probe ally'] WHERE id = true",
            )
            write_seed(
                dbname,
                seed_type="mystery",
                title="Probe 154",
                situation="A probe situation.",
                hook="A probe hook.",
                immediate_goal="A probe goal.",
                stakes="Probe stakes.",
                tension_source="A probe tension.",
                secrets="A probe secret.",
                layer_name="Probe Layer",
                layer_type="planet",
                layer_description="A probe layer.",
                zone_name="Probe Zone",
                zone_summary="A probe zone.",
            )
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT seed_title, seed_potential_allies "
                    "FROM assets.new_story_creator WHERE id = true"
                )
                assert cur.fetchone() == ("Probe 154", None)
        finally:
            close_all_pools()


def _fleet_rows(dbname: str) -> tuple[Any, ...]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        counts = []
        for table in TABLES:
            cur.execute(f"SELECT count(*) FROM {table}")
            counts.append(cur.fetchone()[0])
        cur.execute(
            "SELECT id, provider, model_ref FROM orrery_narration_jobs ORDER BY id"
        )
        return tuple(counts), cur.fetchall()


@pytest.mark.requires_corpus
@pytest.mark.parametrize("source", SOURCES)
def test_migration_154_preserves_fleet_data(
    fleet_archives: dict[str, Path], tmp_path: Path, source: str
) -> None:
    """Each fleet source's rows and provenance survive the drop unchanged."""
    with _clone(fleet_archives, tmp_path, source) as dbname:
        before = _fleet_rows(dbname)
        assert _apply(dbname)
        assert _fleet_rows(dbname) == before
        print("813-154 fleet", source, before[0], len(before[1]), flush=True)
