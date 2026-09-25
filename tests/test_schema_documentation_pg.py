"""Table/column documentation ratchet on disposable real PostgreSQL clones.

Requires NEXUS_template (public/assets tables and installed extensions), pg_dump,
createdb, and dropdb. The template is read only; every write targets qa640_*.
Enums, functions, and views are intentionally outside this first-slice gate.
"""

from __future__ import annotations

import json
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
# Extension ownership of a table also excludes all of that table's columns.
INVENTORY_SQL = """
WITH owned_tables AS (
    SELECT c.oid, n.nspname, c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('public', 'assets')
      AND c.relkind IN ('r', 'p', 'f')
      AND NOT EXISTS (
          SELECT 1 FROM pg_depend d
          WHERE d.classid = 'pg_class'::regclass
            AND d.objid = c.oid AND d.objsubid = 0 AND d.deptype = 'e'
      )
)
SELECT 'table:' || quote_ident(nspname) || '.' || quote_ident(relname),
       obj_description(oid, 'pg_class')
FROM owned_tables
UNION ALL
SELECT 'column:' || quote_ident(t.nspname) || '.' || quote_ident(t.relname)
       || '.' || quote_ident(a.attname), col_description(t.oid, a.attnum)
FROM owned_tables t
JOIN pg_attribute a ON a.attrelid = t.oid
WHERE a.attnum > 0 AND NOT a.attisdropped
  AND NOT EXISTS (
      SELECT 1 FROM pg_depend d
      WHERE d.classid = 'pg_class'::regclass AND d.objid = t.oid
        AND d.objsubid = a.attnum AND d.deptype = 'e'
  )
ORDER BY 1
"""


def _inventory(conn: connection) -> dict[str, str | None]:
    with conn.cursor() as cur:
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
        assert key.startswith(("table:", "column:")), key
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
    with disposable_slot_database("qa640_schema_docs") as dbname:
        with closing(connect(dbname)) as conn:
            conn.set_session(readonly=True)
            _assert_coverage(_inventory(conn), _baseline())
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
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_depend WHERE classid = 'pg_class'::regclass "
                "AND objid = 'public.spatial_ref_sys'::regclass AND deptype = 'e'"
            )
            assert cur.fetchone(), "PostGIS extension ownership must be real"
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
    ],
    ids=[
        "new-table",
        "new-column",
        "blank-comment",
        "removed-comment",
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
            with pytest.raises(AssertionError, match=expected):
                _assert_coverage(_inventory(conn), _baseline())
        finally:
            conn.rollback()


@pytest.mark.parametrize(
    "mutation",
    [
        "COMMENT ON COLUMN assets.schema_docs_debt.legacy IS 'Probe comment'",
        "ALTER TABLE assets.schema_docs_debt DROP COLUMN legacy",
    ],
    ids=["documented-debt", "removed-debt"],
)
def test_baseline_retirement(documented_clone: str, mutation: str) -> None:
    """Exercise retirement even after all actual legacy debt has been resolved."""
    with closing(connect(documented_clone)) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE TABLE assets.schema_docs_debt (id integer, legacy text);"
                    "COMMENT ON TABLE assets.schema_docs_debt IS 'Retirement probe';"
                    "COMMENT ON COLUMN assets.schema_docs_debt.id IS 'Probe ID'"
                )
            baseline = {
                **_baseline(),
                "column:assets.schema_docs_debt.legacy": "Deliberate test debt",
            }
            _assert_coverage(_inventory(conn), baseline)
            with conn.cursor() as cur:
                cur.execute(mutation)
            with pytest.raises(
                AssertionError, match="Retire documented or removed baseline entries"
            ):
                _assert_coverage(_inventory(conn), baseline)
            baseline.pop("column:assets.schema_docs_debt.legacy")
            _assert_coverage(_inventory(conn), baseline)
        finally:
            conn.rollback()


def test_schema_only_refresh_preserves_comments(documented_clone: str) -> None:
    """Prove pg_dump -s carries exact table and column comments without rows."""
    with _schema_only_clone(documented_clone) as refreshed:
        with (
            closing(connect(documented_clone)) as source,
            closing(connect(refreshed)) as target,
        ):
            source.set_session(readonly=True)
            target.set_session(readonly=True)
            assert _inventory(target) == _inventory(source)
            _assert_coverage(_inventory(target), _baseline())
            with target.cursor() as cur:
                cur.execute("SELECT count(*) FROM schema_migrations")
                assert cur.fetchone() == (0,)


def test_story_setup_and_runner_preserve_comments(documented_clone: str) -> None:
    """Run the production schema-copy, seed-copy, and migration path twice."""
    with closing(connect(documented_clone)) as conn:
        conn.set_session(readonly=True)
        expected = _inventory(conn)
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
