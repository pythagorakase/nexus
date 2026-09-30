"""Table/column documentation ratchet on disposable real PostgreSQL clones.

Requires NEXUS_template (public/assets tables and installed extensions), pg_dump,
createdb, and dropdb. The template is read only; every write targets qa640_*.
The gate covers tables and their columns, enums, functions and procedures, and
views and materialized views that NEXUS owns in public and assets. Views are
documented at the view level only; their columns are not inventoried.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

import pytest
from psycopg2.extensions import connection

from nexus.database import subprocess_env
from scripts import migrate, new_story_setup
from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres
ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "config/schema_docs_baseline.json"

# Match pg_depend by catalog as well as OID: OIDs are not globally unique.
# Extension ownership of a relation also excludes all of that relation's columns.
# Only table columns are inventoried: view DDL declares no column list, so
# scripts/check_migration_comments.py requires COMMENT ON VIEW but cannot require
# view column comments, and the ratchet must not be stricter than that lint.
# Functions are keyed by identity arguments because overloads share a name;
# prokind 'a' (aggregates) stays outside the gate. format_type renders those
# arguments schema-qualified only for types off the search_path, so _inventory
# pins search_path to public (the path the baseline was rendered under).
INVENTORY_SQL = """
WITH owned_relations AS (
    SELECT c.oid, n.nspname, c.relname, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('public', 'assets')
      AND c.relkind IN ('r', 'p', 'f', 'v', 'm')
      AND NOT EXISTS (
          SELECT 1 FROM pg_depend d
          WHERE d.classid = 'pg_class'::regclass
            AND d.objid = c.oid AND d.objsubid = 0 AND d.deptype = 'e'
      )
)
SELECT CASE WHEN relkind IN ('v', 'm') THEN 'view:' ELSE 'table:' END
       || quote_ident(nspname) || '.' || quote_ident(relname),
       obj_description(oid, 'pg_class')
FROM owned_relations
UNION ALL
SELECT 'column:' || quote_ident(t.nspname) || '.' || quote_ident(t.relname)
       || '.' || quote_ident(a.attname), col_description(t.oid, a.attnum)
FROM owned_relations t
JOIN pg_attribute a ON a.attrelid = t.oid
WHERE t.relkind IN ('r', 'p', 'f')
  AND a.attnum > 0 AND NOT a.attisdropped
  AND NOT EXISTS (
      SELECT 1 FROM pg_depend d
      WHERE d.classid = 'pg_class'::regclass AND d.objid = t.oid
        AND d.objsubid = a.attnum AND d.deptype = 'e'
  )
UNION ALL
SELECT 'enum:' || quote_ident(n.nspname) || '.' || quote_ident(t.typname),
       obj_description(t.oid, 'pg_type')
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname IN ('public', 'assets')
  AND t.typtype = 'e'
  AND NOT EXISTS (
      SELECT 1 FROM pg_depend d
      WHERE d.classid = 'pg_type'::regclass
        AND d.objid = t.oid AND d.deptype = 'e'
  )
UNION ALL
SELECT 'function:' || quote_ident(n.nspname) || '.' || quote_ident(p.proname)
       || '(' || pg_get_function_identity_arguments(p.oid) || ')',
       obj_description(p.oid, 'pg_proc')
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname IN ('public', 'assets')
  AND p.prokind IN ('f', 'w', 'p')
  AND NOT EXISTS (
      SELECT 1 FROM pg_depend d
      WHERE d.classid = 'pg_proc'::regclass
        AND d.objid = p.oid AND d.deptype = 'e'
  )
ORDER BY 1
"""
KINDS = ("table:", "column:", "enum:", "function:", "view:")

# Documented probe objects committed to the shared clone so the refresh tests
# prove an enum, a function, and a view comment survive the schema copy with
# known, test-owned comment text, independent of which legacy objects remain
# baselined debt.
REFRESH_PROBE_DDL = """
CREATE TYPE public.schema_docs_refresh_probe AS ENUM ('kept');
COMMENT ON TYPE public.schema_docs_refresh_probe IS 'Refresh probe enum';
CREATE FUNCTION public.schema_docs_refresh_probe(value integer)
RETURNS integer LANGUAGE sql IMMUTABLE AS 'SELECT value';
COMMENT ON FUNCTION public.schema_docs_refresh_probe(integer)
    IS 'Refresh probe function';
CREATE VIEW public.schema_docs_refresh_probe_v AS
SELECT 'kept'::public.schema_docs_refresh_probe AS state;
COMMENT ON VIEW public.schema_docs_refresh_probe_v IS 'Refresh probe view';
"""
REFRESH_PROBES = {
    "enum:public.schema_docs_refresh_probe": "Refresh probe enum",
    "function:public.schema_docs_refresh_probe(value integer)": (
        "Refresh probe function"
    ),
    "view:public.schema_docs_refresh_probe_v": "Refresh probe view",
}


def _assert_refresh_probes(objects: dict[str, str | None]) -> None:
    assert {key: objects.get(key) for key in REFRESH_PROBES} == REFRESH_PROBES


def _inventory(conn: connection) -> dict[str, str | None]:
    with conn.cursor() as cur:
        # Transaction-local, so it also works on read-only sessions and leaves
        # the caller's path intact after its rollback or commit.
        cur.execute("SELECT set_config('search_path', 'public', true)")
        cur.execute(INVENTORY_SQL)
        return dict(cur.fetchall())


def _baseline() -> dict[str, str]:
    # Reject duplicate JSON keys instead of silently losing a debt entry.
    def unique_object(pairs: list[tuple[str, str]]) -> dict[str, str]:
        result = dict(pairs)
        assert len(result) == len(pairs), "Duplicate schema documentation baseline key"
        return result

    result = json.loads(BASELINE.read_text(), object_pairs_hook=unique_object)
    assert isinstance(result, dict), "Baseline must be an object of names to reasons"
    for key, reason in result.items():
        assert key.startswith(KINDS), key
        assert isinstance(reason, str) and reason.strip(), f"Missing reason: {key}"
    return result


def _assert_coverage(objects: dict[str, str | None], baseline: dict[str, str]) -> None:
    missing = {key for key, comment in objects.items() if not (comment or "").strip()}
    untracked = sorted(missing - baseline.keys())
    retired = sorted(baseline.keys() - missing)
    assert not (untracked or retired), (
        f"Undocumented objects absent from baseline: {untracked}\n"
        f"Retire documented or removed baseline entries: {retired}"
    )


@contextmanager
def _schema_only_clone(source: str) -> Iterator[str]:
    """Copy schema and comments with real pg_dump -s; never copy source data."""
    dbname = f"qa640_schema_docs_{uuid.uuid4().hex[:12]}"
    tools = new_story_setup._postgres_tools("createdb", "dropdb", "pg_dump", "psql")
    env = subprocess_env()
    subprocess.run([tools["createdb"], dbname], check=True, env=env)
    try:
        with tempfile.TemporaryFile(mode="w+") as dump:
            subprocess.run(
                [tools["pg_dump"], "-s", source],
                stdout=dump,
                check=True,
                env=env,
            )
            dump.seek(0)
            subprocess.run(
                [tools["psql"], "-X", "-v", "ON_ERROR_STOP=1", dbname],
                stdin=dump,
                stdout=subprocess.DEVNULL,
                check=True,
                env=env,
            )
        yield dbname
    finally:
        subprocess.run([tools["dropdb"], dbname], check=True, env=env)


@pytest.fixture(scope="module")
def documented_clone() -> Iterator[str]:
    """Yield a migrated template clone plus the committed, documented probes."""
    with disposable_slot_database("qa640_schema_docs") as dbname:
        with closing(connect(dbname)) as conn:
            conn.set_session(readonly=True)
            _assert_coverage(_inventory(conn), _baseline())
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(REFRESH_PROBE_DDL)
        with closing(connect(dbname)) as conn:
            conn.set_session(readonly=True)
            objects = _inventory(conn)
            _assert_refresh_probes(objects)
            _assert_coverage(objects, _baseline())
        yield dbname


def test_schema_documentation_coverage(documented_clone: str) -> None:
    """Reject new debt and require the baseline to shrink with documented debt."""
    with closing(connect(documented_clone)) as conn:
        conn.set_session(readonly=True)
        objects = _inventory(conn)
        _assert_coverage(objects, _baseline())
        assert "table:public.spatial_ref_sys" not in objects
        assert not any(
            key.startswith("column:public.spatial_ref_sys.") for key in objects
        )
        # PostGIS and pgvector install functions and views into public; their
        # extension membership, not a name list, keeps them out of the gate.
        for key in (
            "view:public.geometry_columns",
            "view:public.geography_columns",
            "function:public.postgis_full_version()",
            "function:public.vector_dims(vector)",
        ):
            assert key not in objects, key
        assert {key.split(":", 1)[0] + ":" for key in objects} == set(KINDS)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_depend WHERE classid = 'pg_class'::regclass "
                "AND objid = 'public.spatial_ref_sys'::regclass AND deptype = 'e'"
            )
            assert cur.fetchone(), "PostGIS extension ownership must be real"
            cur.execute(
                "SELECT count(*) FROM pg_depend WHERE classid = 'pg_proc'::regclass "
                "AND objid IN ('public.postgis_full_version()'::regprocedure, "
                "'public.vector_dims(vector)'::regprocedure) AND deptype = 'e'"
            )
            assert cur.fetchone() == (2,), "Extension function ownership must be real"
            cur.execute(
                "SELECT count(*) FROM pg_depend WHERE classid = 'pg_class'::regclass "
                "AND objid IN ('public.geometry_columns'::regclass, "
                "'public.geography_columns'::regclass) AND deptype = 'e'"
            )
            assert cur.fetchone() == (2,), "Extension view ownership must be real"
            cur.execute("SELECT version FROM schema_migrations WHERE version = '127'")
            assert cur.fetchall() == [("127",)]


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            "CREATE TABLE public.schema_docs_probe (id integer)",
            "table:public.schema_docs_probe",
        ),
        (
            "ALTER TABLE assets.character_images ADD COLUMN docs_probe text",
            "column:assets.character_images.docs_probe",
        ),
        (
            "COMMENT ON COLUMN public.schema_migrations.name IS '   '",
            "column:public.schema_migrations.name",
        ),
        ("COMMENT ON TABLE public.entities IS NULL", "table:public.entities"),
        (
            "CREATE TYPE assets.schema_docs_probe AS ENUM ('a')",
            "enum:assets.schema_docs_probe",
        ),
        (
            "COMMENT ON TYPE public.schema_docs_refresh_probe IS '   '",
            "enum:public.schema_docs_refresh_probe",
        ),
        (
            "CREATE FUNCTION public.schema_docs_probe() RETURNS trigger "
            "LANGUAGE plpgsql AS 'BEGIN RETURN NEW; END'",
            "function:public.schema_docs_probe()",
        ),
        (
            "CREATE FUNCTION public.schema_docs_refresh_probe(text) "
            "RETURNS text LANGUAGE sql AS 'SELECT $1'",
            "function:public.schema_docs_refresh_probe(text)",
        ),
        (
            "CREATE PROCEDURE assets.schema_docs_probe(n integer) "
            "LANGUAGE sql AS 'SELECT n'",
            "function:assets.schema_docs_probe(IN n integer)",
        ),
        (
            "COMMENT ON FUNCTION public.clear_incubator() IS NULL",
            "function:public.clear_incubator()",
        ),
        (
            "CREATE VIEW public.schema_docs_probe AS SELECT 1 AS id",
            "view:public.schema_docs_probe",
        ),
        (
            "CREATE MATERIALIZED VIEW assets.schema_docs_probe AS SELECT 1 AS id",
            "view:assets.schema_docs_probe",
        ),
        (
            "COMMENT ON VIEW public.narrative_view IS NULL",
            "view:public.narrative_view",
        ),
    ],
    ids=[
        "new-table",
        "new-column",
        "blank-comment",
        "removed-comment",
        "new-enum",
        "blank-enum-comment",
        "new-trigger-function",
        "new-overload",
        "new-procedure",
        "removed-function-comment",
        "new-view",
        "new-materialized-view",
        "removed-view-comment",
    ],
)
def test_ratchet_rejects_catalog_regressions(
    documented_clone: str, mutation: str, expected: str
) -> None:
    """Exercise catalog mutations, not fabricated catalog rows; roll each back."""
    with closing(connect(documented_clone)) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(mutation)
            with pytest.raises(AssertionError, match=re.escape(repr(expected))):
                _assert_coverage(_inventory(conn), _baseline())
        finally:
            conn.rollback()


RETIREMENT_DEBT = {
    "table": (
        "CREATE TABLE assets.schema_docs_debt_t (id integer);"
        "COMMENT ON COLUMN assets.schema_docs_debt_t.id IS 'Probe ID'",
        "table:assets.schema_docs_debt_t",
        "COMMENT ON TABLE assets.schema_docs_debt_t IS 'Probe comment'",
        "DROP TABLE assets.schema_docs_debt_t",
    ),
    "column": (
        "CREATE TABLE assets.schema_docs_debt (id integer, legacy text);"
        "COMMENT ON TABLE assets.schema_docs_debt IS 'Retirement probe';"
        "COMMENT ON COLUMN assets.schema_docs_debt.id IS 'Probe ID'",
        "column:assets.schema_docs_debt.legacy",
        "COMMENT ON COLUMN assets.schema_docs_debt.legacy IS 'Probe comment'",
        "ALTER TABLE assets.schema_docs_debt DROP COLUMN legacy",
    ),
    "enum": (
        "CREATE TYPE assets.schema_docs_debt AS ENUM ('a')",
        "enum:assets.schema_docs_debt",
        "COMMENT ON TYPE assets.schema_docs_debt IS 'Probe comment'",
        "DROP TYPE assets.schema_docs_debt",
    ),
    "function": (
        "CREATE FUNCTION assets.schema_docs_debt(integer) RETURNS integer "
        "LANGUAGE sql AS 'SELECT $1'",
        "function:assets.schema_docs_debt(integer)",
        "COMMENT ON FUNCTION assets.schema_docs_debt(integer) IS 'Probe comment'",
        "DROP FUNCTION assets.schema_docs_debt(integer)",
    ),
    "view": (
        "CREATE VIEW assets.schema_docs_debt AS SELECT 1 AS id",
        "view:assets.schema_docs_debt",
        "COMMENT ON VIEW assets.schema_docs_debt IS 'Probe comment'",
        "DROP VIEW assets.schema_docs_debt",
    ),
}


@pytest.mark.parametrize("kind", sorted(RETIREMENT_DEBT))
@pytest.mark.parametrize("retire", ["documented", "removed"])
def test_baseline_retirement(documented_clone: str, kind: str, retire: str) -> None:
    """Exercise retirement even after all actual legacy debt has been resolved."""
    setup, key, document, remove = RETIREMENT_DEBT[kind]
    with closing(connect(documented_clone)) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(setup)
            baseline = {**_baseline(), key: "Deliberate test debt"}
            _assert_coverage(_inventory(conn), baseline)
            with conn.cursor() as cur:
                cur.execute(document if retire == "documented" else remove)
            with pytest.raises(
                AssertionError, match="Retire documented or removed baseline entries"
            ):
                _assert_coverage(_inventory(conn), baseline)
            baseline.pop(key)
            _assert_coverage(_inventory(conn), baseline)
        finally:
            conn.rollback()


@pytest.mark.parametrize(
    "key",
    [
        "table:public.schema_docs_ghost",
        "column:public.schema_docs_ghost.id",
        "enum:public.schema_docs_ghost",
        "function:public.schema_docs_ghost()",
        "view:public.schema_docs_ghost",
    ],
)
def test_baseline_rejects_nonexistent_keys(documented_clone: str, key: str) -> None:
    """A baseline key naming no catalog object must be retired, not kept."""
    with closing(connect(documented_clone)) as conn:
        conn.set_session(readonly=True)
        with pytest.raises(AssertionError, match=re.escape(repr(key))):
            _assert_coverage(_inventory(conn), {**_baseline(), key: "Ghost"})


def test_views_are_documented_at_view_level(documented_clone: str) -> None:
    """Require the view comment, never view column comments, as the lint does."""
    view_keys = ["view:assets.schema_docs_probe", "view:public.schema_docs_probe"]
    view_column = "column:public.schema_docs_probe.id"
    with closing(connect(documented_clone)) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE VIEW public.schema_docs_probe AS SELECT 1 AS id;"
                    "CREATE MATERIALIZED VIEW assets.schema_docs_probe AS "
                    "SELECT 1 AS id"
                )
            objects = _inventory(conn)
            assert view_column not in objects
            # The views alone are reported, never their uncommented columns.
            with pytest.raises(AssertionError, match=re.escape(repr(view_keys))):
                _assert_coverage(objects, _baseline())
            with conn.cursor() as cur:
                cur.execute(
                    "COMMENT ON VIEW public.schema_docs_probe IS 'Probe view';"
                    "COMMENT ON MATERIALIZED VIEW assets.schema_docs_probe "
                    "IS 'Probe view'"
                )
            _assert_coverage(_inventory(conn), _baseline())
            # A view column is not debt the baseline can carry.
            with pytest.raises(AssertionError, match=re.escape(repr([view_column]))):
                _assert_coverage(
                    _inventory(conn), {**_baseline(), view_column: "View column"}
                )
        finally:
            conn.rollback()


def test_schema_only_refresh_preserves_comments(documented_clone: str) -> None:
    """Prove pg_dump -s carries exact comments of every kind without rows."""
    with _schema_only_clone(documented_clone) as refreshed:
        with (
            closing(connect(documented_clone)) as source,
            closing(connect(refreshed)) as target,
        ):
            source.set_session(readonly=True)
            target.set_session(readonly=True)
            assert _inventory(target) == _inventory(source)
            _assert_refresh_probes(_inventory(target))
            _assert_coverage(_inventory(target), _baseline())
            with target.cursor() as cur:
                cur.execute("SELECT count(*) FROM schema_migrations")
                assert cur.fetchone() == (0,)


def test_story_setup_and_runner_preserve_comments(documented_clone: str) -> None:
    """Run the production schema-copy, seed-copy, and migration path twice."""
    with closing(connect(documented_clone)) as conn:
        conn.set_session(readonly=True)
        expected = _inventory(conn)
        _assert_refresh_probes(expected)
        _assert_coverage(expected, _baseline())
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM schema_migrations WHERE version='127'")
            assert cur.fetchone() == (1,)
    # Copied stamps suppress replay of 127, so equality proves that setup's
    # actual schema dump/restore preserves comments rather than repairing them.
    with disposable_slot_database(
        "qa640_docs_refresh", source_db=documented_clone
    ) as second:
        with closing(connect(second)) as conn:
            conn.set_session(readonly=True)
            assert _inventory(conn) == expected
            _assert_refresh_probes(_inventory(conn))
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM schema_migrations WHERE version='127'"
                )
                assert cur.fetchone() == (1,)


def test_runner_creates_documented_tracking_table(documented_clone: str) -> None:
    """A runner-created ledger is documented even before migration 127 runs."""
    with _schema_only_clone(documented_clone) as dbname:
        with closing(connect(dbname)) as conn:
            expected = {
                key: value
                for key, value in _inventory(conn).items()
                if key == "table:public.schema_migrations"
                or key.startswith("column:public.schema_migrations.")
            }
            with conn.cursor() as cur:
                cur.execute("DROP TABLE public.schema_migrations")
            assert migrate.ensure_tracking_table(conn)
            actual = {
                key: value
                for key, value in _inventory(conn).items()
                if key == "table:public.schema_migrations"
                or key.startswith("column:public.schema_migrations.")
            }
            assert len(actual) == 4
            assert all(actual.values())
            assert actual == expected
