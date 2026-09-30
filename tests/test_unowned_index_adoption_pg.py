"""Migration 138 owns three fleet indexes and a column; the constructor makes no table.

Issue #810. The PostgreSQL cases run on disposable ``qa640_*`` clones of
``NEXUS_template`` made through ``tests/pg_fixtures.py``. A clone runs pending
migrations when it is made, so 138 has already applied (as a no-op, because
the template already has every object) when a test body starts. Each case
reads the clone's own catalog as the fresh-clone reference, then changes the
clone and reruns the real ``scripts/migrate.py`` runner. No save slot or
template is written.

The offline case walks the source tree: no code under ``nexus/`` calls
``create_all``, so constructing a runtime object cannot create tables behind
the migration runner.
"""

from __future__ import annotations

import ast
import logging
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from nexus.agents.memnon.utils.db_schema import DatabaseManager
from nexus.database import database_url
from scripts import migrate
from tests.pg_fixtures import connect, disposable_slot_database

REPO_ROOT = Path(__file__).resolve().parents[1]

# The live definitions on NEXUS_template and save_01..save_05 (pg_indexes,
# 2026-09-30), which migration 138 adopts.
ADOPTED_INDEXES = {
    "idx_chunk_metadata_scene": (
        "CREATE INDEX idx_chunk_metadata_scene ON public.chunk_metadata "
        "USING btree (scene)"
    ),
    "idx_chunk_metadata_season_episode_scene": (
        "CREATE INDEX idx_chunk_metadata_season_episode_scene ON "
        "public.chunk_metadata USING btree (season, episode, scene)"
    ),
    "narrative_chunks_text_idx": (
        "CREATE INDEX narrative_chunks_text_idx ON public.narrative_chunks "
        "USING gin (to_tsvector('english'::regconfig, raw_text))"
    ),
}
SCENE_COMMENT = "Scene number within the episode"
MIGRATION = "138_adopt_unowned_fleet_indexes"


def _index_definitions(cur: Any) -> dict[str, str]:
    cur.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = ANY(%s)
        """,
        (sorted(ADOPTED_INDEXES),),
    )
    return {str(name): str(definition) for name, definition in cur.fetchall()}


def _index_oids(cur: Any) -> dict[str, int]:
    cur.execute(
        """
        SELECT c.relname, c.oid::bigint
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = ANY(%s)
        """,
        (sorted(ADOPTED_INDEXES),),
    )
    return {str(name): int(oid) for name, oid in cur.fetchall()}


def _scene_column(cur: Any) -> tuple[str, str | None, int] | None:
    """Return the type, comment, and attnum of chunk_metadata.scene, if any."""

    cur.execute(
        """
        SELECT format_type(a.atttypid, a.atttypmod),
               col_description(a.attrelid, a.attnum),
               a.attnum
        FROM pg_attribute AS a
        WHERE a.attrelid = 'public.chunk_metadata'::regclass
          AND a.attname = 'scene'
          AND NOT a.attisdropped
        """
    )
    row = cur.fetchone()
    return None if row is None else (str(row[0]), row[1], int(row[2]))


def _is_stamped(cur: Any) -> bool:
    cur.execute("SELECT 1 FROM schema_migrations WHERE version = '138'")
    return cur.fetchone() is not None


def _catalog(dbname: str) -> tuple[dict[str, str], tuple[str, str | None, int] | None]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        return _index_definitions(cur), _scene_column(cur)


@pytest.mark.requires_postgres
def test_migration_138_recreates_the_indexes_and_column_it_owns() -> None:
    """A clone without the objects and the stamp gets the fresh-clone catalog back."""

    with disposable_slot_database("qa640_810_adopt_recreate") as dbname:
        fresh_indexes, fresh_scene = _catalog(dbname)
        assert fresh_indexes == ADOPTED_INDEXES
        assert fresh_scene is not None
        assert fresh_scene[:2] == ("integer", SCENE_COMMENT)

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            assert _is_stamped(cur)
            cur.execute("DELETE FROM schema_migrations WHERE version = '138'")
            for index_name in sorted(ADOPTED_INDEXES):
                cur.execute(f"DROP INDEX public.{index_name}")
            # Three views read the column (narrative_view,
            # chunk_character_references_view, chunk_places_view); CASCADE
            # drops them with it on this clone. They are not compared below.
            cur.execute("ALTER TABLE public.chunk_metadata DROP COLUMN scene CASCADE")
            assert _index_definitions(cur) == {}
            assert _scene_column(cur) is None

        assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)

        rebuilt_indexes, rebuilt_scene = _catalog(dbname)
        assert rebuilt_indexes == fresh_indexes
        assert rebuilt_scene is not None
        assert rebuilt_scene[:2] == fresh_scene[:2]
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            assert _is_stamped(cur)


@pytest.mark.requires_postgres
def test_migration_138_changes_nothing_on_a_complete_database() -> None:
    """The fleet case: every object exists, so rerunning 138 rebuilds nothing."""

    with disposable_slot_database("qa640_810_adopt_noop") as dbname:
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            before_indexes = _index_definitions(cur)
            before_oids = _index_oids(cur)
            before_scene = _scene_column(cur)
        assert before_indexes == ADOPTED_INDEXES
        assert set(before_oids) == set(ADOPTED_INDEXES)

        # A second runner pass over the fresh clone applies nothing.
        assert migrate.migrate_database(dbname, skip_locked=False) == (0, 0)

        # The fleet has the objects but not the stamp: 138 applies there and
        # must leave the same indexes (same OIDs, so none was rebuilt) and the
        # same column in place.
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM schema_migrations WHERE version = '138'")
        assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)

        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            assert _index_definitions(cur) == before_indexes
            assert _index_oids(cur) == before_oids
            assert _scene_column(cur) == before_scene
            assert _is_stamped(cur)


@pytest.mark.requires_postgres
def test_migration_138_refuses_a_same_named_index_with_another_definition(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """IF NOT EXISTS matches by name only, so the catalog check names the drift."""

    with disposable_slot_database("qa640_810_adopt_drift") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM schema_migrations WHERE version = '138'")
            cur.execute("DROP INDEX public.idx_chunk_metadata_scene")
            cur.execute(
                "CREATE INDEX idx_chunk_metadata_scene "
                "ON public.chunk_metadata USING btree (episode)"
            )

        with caplog.at_level(logging.ERROR, logger="nexus.migrate"):
            assert migrate.migrate_database(dbname, skip_locked=False) == (0, 1)
        failure = caplog.text
        assert f"FAILED: {MIGRATION}" in failure
        assert (
            "idx_chunk_metadata_scene (found CREATE INDEX idx_chunk_metadata_scene "
            "ON public.chunk_metadata USING btree (episode))"
        ) in failure
        assert "narrative_chunks_text_idx" not in failure
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            assert not _is_stamped(cur)


@pytest.mark.requires_postgres
def test_database_manager_construction_creates_no_table() -> None:
    """A mapped table the constructor does not need stays absent after construction.

    ``characters`` is mapped by ``db_schema.Base``; before #810 the
    constructor's ``Base.metadata.create_all`` recreated it on any database
    that lacked it.
    """

    with disposable_slot_database("qa640_810_no_create_all") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DROP TABLE public.characters CASCADE")
            cur.execute("SELECT to_regclass('public.characters')")
            assert cur.fetchone() == (None,)

        manager = DatabaseManager(database_url(dbname))
        try:
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.characters')")
                assert cur.fetchone() == (None,)
        finally:
            manager.close()


def test_no_create_all_call_under_nexus() -> None:
    """No runtime module calls ``create_all``; migrations own the schema."""

    calls = []
    for path in sorted((REPO_ROOT / "nexus").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else None
            )
            if name == "create_all":
                calls.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

    assert calls == []
