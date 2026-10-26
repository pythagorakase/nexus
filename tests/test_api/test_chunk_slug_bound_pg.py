"""Migration 153 makes set_chunk_slug() refuse an out-of-range slug part (#1069).

The trigger is the sole author of ``chunk_metadata.slug`` (Decision 1069-D3).
It keeps the legacy ``SxxEyy_zzz`` output for every in-range value and raises
``numeric_value_out_of_range`` naming the chunk, the part, its value and its
bound when season or episode leaves 0..99 or scene leaves 0..999 (Decision
1069-D4), so it never writes ``#``. The module owns one template clone
(``qa640_1069_slug_*``) and the production-commit test owns its own
(``qa640_1069_commit_*``); tables: chunk_metadata, narrative_chunks, incubator,
memory_idf_documents, memory_idf_corpora and schema_migrations.

A NULL part still gives a NULL slug on INSERT and on UPDATE (Decision 1069-D4:
NULL handling is unchanged).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
import re
from typing import Any

import pytest
from psycopg2.errors import NumericValueOutOfRange

from nexus.maintenance import migrate
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_accepted_turn,
    seed_committed_chunk,
    seed_protagonist,
)

pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "migrations" / "153_chunk_slug_bound_refusal.sql"
BOUND = (
    r"Chunk slug bound exceeded: chunk_id \d+ has {part} {value}, outside 0\.\.{bound}"
)
LEGACY_FORMULA_MISMATCHES = """
    SELECT count(*) FROM chunk_metadata
    WHERE slug IS DISTINCT FROM
        'S' || to_char(season, 'FM00') || 'E' || to_char(episode, 'FM00')
        || '_' || to_char(scene, 'FM000')
"""


@pytest.fixture(autouse=True)
def _no_ambient_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep an exported ``NEXUS_SLOT`` from labelling the clone's jobs."""

    monkeypatch.delenv("NEXUS_SLOT", raising=False)


@pytest.fixture(scope="module")
def slug_db() -> Iterator[str]:
    """Own one migrated template clone with a bound player; drop it after."""

    with disposable_slot_database("qa640_1069_slug") as dbname:
        seed_protagonist(dbname)
        yield dbname


def _bound(part: str, value: int, bound: int) -> str:
    return BOUND.format(part=part, value=value, bound=bound)


def _scalar(dbname: str, query: str, params: tuple[Any, ...] = ()) -> Any:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        assert row is not None
        return row[0]


def _narrative_count(dbname: str) -> int:
    return int(_scalar(dbname, "SELECT count(*) FROM narrative_chunks"))


def _hash_slug_count(dbname: str) -> int:
    return int(
        _scalar(
            dbname, "SELECT count(*) FROM chunk_metadata WHERE strpos(slug, '#') > 0"
        )
    )


def _seed_chunk_with_parts(
    dbname: str, season: int | None, episode: int | None, scene: int | None
) -> int:
    """Seed one committed chunk whose slug parts may be NULL; return its ID.

    ``seed_committed_chunk`` types the parts as int, so a NULL part needs SQL.
    A zero ``time_delta`` suits the bootstrap chunk and every later one.
    """

    text = f"Nullable slug parts {(season, episode, scene)}."
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
            "VALUES (%s, %s) RETURNING id",
            (text, text),
        )
        chunk_id = int(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO chunk_metadata (chunk_id, season, episode, scene, "
            "world_layer, time_delta, generation_date) "
            "VALUES (%s, %s, %s, %s, 'primary', interval '0', now())",
            (chunk_id, season, episode, scene),
        )
        assert cur.rowcount == 1
    return chunk_id


def _parts_and_slug(dbname: str, chunk_id: int) -> tuple[Any, Any, Any, Any]:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT season, episode, scene, slug FROM chunk_metadata "
            "WHERE chunk_id = %s",
            (chunk_id,),
        )
        row = cur.fetchone()
        assert row is not None
        season, episode, scene, slug = row
        return season, episode, scene, slug


def test_in_range_slugs_keep_the_legacy_format(slug_db: str) -> None:
    """Fails if the in-range trigger output changes by one byte."""

    expected = {
        (1, 1, 1): "S01E01_001",
        (1, 1, 999): "S01E01_999",
        (5, 17, 80): "S05E17_080",
        (99, 99, 999): "S99E99_999",
        (0, 0, 0): "S00E00_000",
    }
    ids = {
        parts: seed_committed_chunk(
            slug_db,
            raw_text=f"In-range slug {parts}.",
            season=parts[0],
            episode=parts[1],
            scene=parts[2],
        )
        for parts in expected
    }
    with closing(connect(slug_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT chunk_id, slug FROM chunk_metadata WHERE chunk_id = ANY(%s)",
            (list(ids.values()),),
        )
        before = dict(cur.fetchall())
        assert {parts: before[ids[parts]] for parts in expected} == expected
        cur.execute("UPDATE chunk_metadata SET season = season")
        cur.execute(
            "SELECT chunk_id, slug FROM chunk_metadata WHERE chunk_id = ANY(%s)",
            (list(ids.values()),),
        )
        assert dict(cur.fetchall()) == before
        cur.execute(LEGACY_FORMULA_MISMATCHES)
        assert cur.fetchone()[0] == 0


@pytest.mark.parametrize(
    "case",
    [
        (100, 1, 1, "season", 99),
        (1, 100, 1, "episode", 99),
        (1, 1, 1000, "scene", 999),
        (-1, 1, 1, "season", 99),
        (1, -1, 1, "episode", 99),
        (1, 1, -1, "scene", 999),
    ],
    ids=[
        "season-100",
        "episode-100",
        "scene-1000",
        "season-minus-1",
        "episode-minus-1",
        "scene-minus-1",
    ],
)
def test_out_of_range_part_is_refused(
    slug_db: str, case: tuple[int, int, int, str, int]
) -> None:
    """Fails on today's trigger, which writes ### or ## or overflows varchar(10)."""

    season, episode, scene, part, bound = case
    value = {"season": season, "episode": episode, "scene": scene}[part]
    before = _narrative_count(slug_db)
    with pytest.raises(NumericValueOutOfRange, match=_bound(part, value, bound)):
        seed_committed_chunk(
            slug_db,
            raw_text=f"Out-of-range slug {case}.",
            season=season,
            episode=episode,
            scene=scene,
        )
    assert _narrative_count(slug_db) == before
    assert _hash_slug_count(slug_db) == 0


def test_update_past_the_bound_is_refused(slug_db: str) -> None:
    """Fails if an UPDATE can move scene past 999 and write ###."""

    chunk_id = seed_committed_chunk(
        slug_db,
        raw_text="The last scene of the episode.",
        season=1,
        episode=2,
        scene=999,
    )
    with closing(connect(slug_db)) as conn:
        with (
            pytest.raises(NumericValueOutOfRange, match=_bound("scene", 1000, 999)),
            conn,
            conn.cursor() as cur,
        ):
            cur.execute(
                "UPDATE chunk_metadata SET scene = 1000 WHERE chunk_id = %s",
                (chunk_id,),
            )
    assert (
        _scalar(
            slug_db, "SELECT slug FROM chunk_metadata WHERE chunk_id = %s", (chunk_id,)
        )
        == "S01E02_999"
    )


@pytest.mark.parametrize(
    "parts",
    [(None, 4, 1), (1, None, 1), (1, 4, None)],
    ids=["season-null", "episode-null", "scene-null"],
)
def test_null_part_insert_yields_a_null_slug(
    slug_db: str, parts: tuple[int | None, int | None, int | None]
) -> None:
    """Fails if a NULL part becomes digits (or any slug) instead of a NULL slug."""

    chunk_id = _seed_chunk_with_parts(slug_db, *parts)
    season, episode, scene, slug = _parts_and_slug(slug_db, chunk_id)
    assert (season, episode, scene) == parts
    assert slug is None


def test_update_to_a_null_part_clears_the_slug(slug_db: str) -> None:
    """Fails if nulling a part on UPDATE keeps the old slug or writes digits."""

    chunk_id = seed_committed_chunk(
        slug_db,
        raw_text="The ferry clock stops at noon.",
        season=1,
        episode=5,
        scene=1,
    )
    assert _parts_and_slug(slug_db, chunk_id) == (1, 5, 1, "S01E05_001")
    with closing(connect(slug_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE chunk_metadata SET scene = NULL WHERE chunk_id = %s", (chunk_id,)
        )
        assert cur.rowcount == 1
    season, episode, scene, slug = _parts_and_slug(slug_db, chunk_id)
    assert (season, episode, scene) == (1, 5, None)
    assert slug is None


def test_refusal_leaves_idf_and_clock_triggers_live(slug_db: str) -> None:
    """Fails if the replaced trigger stops the IDF or world-clock triggers."""

    count_sql = (
        "SELECT document_count FROM memory_idf_corpora WHERE corpus_kind = 'narrative'"
    )
    before = int(_scalar(slug_db, count_sql))
    chunk_id = seed_committed_chunk(
        slug_db,
        raw_text="Rain drums on the tin roof of the ferry office.",
        season=1,
        episode=3,
        scene=1,
    )
    assert (
        _scalar(
            slug_db,
            "SELECT count(*) FROM memory_idf_documents "
            "WHERE corpus_kind = 'narrative' AND document_id = %s",
            (chunk_id,),
        )
        == 1
    )
    after = int(_scalar(slug_db, count_sql))
    assert after == before + 1
    assert (
        _scalar(
            slug_db,
            "SELECT world_time IS NOT NULL FROM chunk_metadata WHERE chunk_id = %s",
            (chunk_id,),
        )
        is True
    )
    with pytest.raises(NumericValueOutOfRange, match=_bound("scene", 1000, 999)):
        seed_committed_chunk(
            slug_db,
            raw_text="A scene past the bound.",
            season=1,
            episode=3,
            scene=1000,
        )
    assert int(_scalar(slug_db, count_sql)) == after


def test_production_commit_refuses_scene_1000_and_rolls_back() -> None:
    """Fails on main with StringDataRightTruncation from the Python slug."""

    with disposable_slot_database("qa640_1069_commit") as dbname:
        seed_protagonist(dbname)
        seed_committed_chunk(
            dbname, raw_text="The last lamp on the bridge still burns.", scene=999
        )
        before = _narrative_count(dbname)
        with pytest.raises(NumericValueOutOfRange, match=_bound("scene", 1000, 999)):
            seed_accepted_turn(
                dbname,
                user_text="Wait.",
                storyteller_text="The bridge lamps flicker over the river.",
            )
        assert _narrative_count(dbname) == before
        assert (
            _scalar(dbname, "SELECT count(*) FROM chunk_metadata WHERE scene = 1000")
            == 0
        )
        assert _scalar(dbname, "SELECT count(*) FROM incubator") == 1


def test_migration_153_rerun_is_a_no_op(slug_db: str) -> None:
    """Fails if re-applying migration 153 changes the function or its stamp."""

    state_sql = (
        "SELECT pg_get_functiondef('public.set_chunk_slug'::regproc), "
        "obj_description('public.set_chunk_slug'::regproc, 'pg_proc')"
    )

    def state() -> tuple[str, str]:
        with closing(connect(slug_db)) as conn, conn, conn.cursor() as cur:
            cur.execute(state_sql)
            definition, comment = cur.fetchone()
            return definition, comment

    before = state()
    assert re.search(r"numeric_value_out_of_range", before[0])
    with closing(connect(slug_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(MIGRATION.read_text())
    assert state() == before
    assert (
        _scalar(slug_db, "SELECT count(*) FROM schema_migrations WHERE version = '153'")
        == 1
    )
    assert migrate.migrate_database(slug_db, skip_locked=False) == (0, 0)
