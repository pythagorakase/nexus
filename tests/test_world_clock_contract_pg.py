"""Clock identity through real metadata writes on a disposable template clone.

Requires narrative_chunks, chunk_metadata (including its clock trigger and the
time_delta CHECK of migration 140), narrative_view, global_variables,
characters, and places. The shared fixture migrates and drops only its
disposable database; no live save is written.
"""

from collections.abc import Iterator
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2.errors
import pytest
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.api.commit_handler_sync import insert_chunk_metadata_sync
from nexus.api.reader_endpoints import _CHUNK_SELECT, _chunk_payload
from nexus.util.clock_face import clock_face
from scripts import migrate
from scripts.qa_shift.world_clock import measure_connection
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_committed_chunk,
    seed_protagonist,
    sqlalchemy_url,
)
from tests.settings_helpers import settings_with

pytestmark = pytest.mark.requires_postgres
BASE = datetime(2189, 10, 17, 19, 12, tzinfo=timezone.utc)


@pytest.fixture()
def clock_db() -> Iterator[tuple[str, int]]:
    """Seed primary, flashback, and Retrograde metadata through the real writer."""
    with disposable_slot_database("qa640_clock") as dbname:
        seed_protagonist(dbname, base_timestamp=BASE.isoformat())
        with closing(connect(dbname)) as conn, conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO seasons (id) VALUES (1)")
                cur.execute("INSERT INTO episodes (episode, season) VALUES (1, 1)")
                first = None
                for scene, (layer, minutes) in enumerate(
                    [
                        ("primary", 0),
                        ("primary", 7),
                        ("flashback", 3),
                        ("retrograde", 0),
                    ],
                    start=1,
                ):
                    cur.execute(
                        "INSERT INTO narrative_chunks (raw_text) VALUES (%s) RETURNING id",
                        (f"Clock contract {layer}",),
                    )
                    chunk_id = cur.fetchone()[0]
                    if first is None:
                        first = chunk_id
                    insert_chunk_metadata_sync(
                        cur,
                        chunk_id=chunk_id,
                        season=1,
                        episode=1,
                        scene=scene,
                        world_layer=layer,
                        time_delta=timedelta(minutes=minutes),
                        generation_date=datetime.now(timezone.utc),
                        slug=f"S01E01_{scene:03d}",
                        generation_model=None,
                        scene_weather=None,
                    )
        assert first is not None
        yield dbname, first


def test_world_clock_identity_and_face(clock_db: tuple[str, int]) -> None:
    """The view, writer, reader, and guard agree in UTC and New York sessions."""
    dbname, first = clock_db
    faces = []
    engine = create_engine(sqlalchemy_url(dbname))
    try:
        for zone in ("America/New_York", "UTC"):
            with closing(connect(dbname)) as conn, conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT set_config('TimeZone', %s, true)", (zone,))
                    cur.execute(
                        "SELECT cm.world_time, nv.world_time AS view_time "
                        "FROM chunk_metadata cm JOIN narrative_view nv ON nv.id = cm.chunk_id "
                        "ORDER BY cm.chunk_id"
                    )
                    rows = cur.fetchall()
                    assert len(rows) == 4
                    assert all(r["world_time"] == r["view_time"] for r in rows)
                    # Primary-only: the flashback's 3 minutes leave the
                    # mainline clock unchanged (the all-layer sum gave 10, 10).
                    assert [r["world_time"] for r in rows] == [
                        BASE + timedelta(minutes=m) for m in (0, 7, 7, 7)
                    ]
                    faces.append(clock_face(rows[0]["world_time"]))
                    cur.execute(
                        _CHUNK_SELECT
                        + " FROM narrative_chunks nc JOIN chunk_metadata cm "
                        "ON nc.id = cm.chunk_id WHERE nc.id = %s",
                        (first,),
                    )
                    payload = _chunk_payload(dict(cur.fetchone()))
                    assert payload["metadata"]["worldTime"] == BASE.isoformat()
                    assert payload["metadata"]["worldTimeFace"] == faces[-1]
            with Session(engine) as session:
                session.execute(
                    text("SELECT set_config('TimeZone', :zone, true)"), {"zone": zone}
                )
                intertitle = TurnCycleManager._load_intertitle(
                    session, anchor_chunk_id=first
                )
                assert intertitle["world_time"] == BASE.isoformat()
                prompt = LogonUtility(
                    settings_with({"apex.turn_pipeline": "single_pass"})
                )._format_context_prompt(
                    {"user_input": "Continue.", "intertitle": intertitle}
                )
                assert "\n17 Oct 2189 · 19:12\n" in prompt
                assert "15:12" not in prompt
        assert faces == ["17 Oct 2189 · 19:12"] * 2
        with closing(connect(dbname)) as conn:
            conn.set_session(readonly=True)
            assert measure_connection(conn) == {
                "chunks": 4,
                "disagreements": 0,
                "base_timestamp_face": "17 Oct 2189 · 19:12",
            }
    finally:
        engine.dispose()


def _clock_minutes(dbname: str) -> list[float]:
    """Return each chunk's clock as minutes after ``BASE``, in chunk order."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT world_time FROM chunk_metadata ORDER BY chunk_id")
        return [(row[0] - BASE).total_seconds() / 60 for row in cur.fetchall()]


def _insert_chunk(cur: Any, *, scene: int, layer: str, delta: timedelta | None) -> int:
    """Insert one chunk and its metadata through the production writer."""
    cur.execute(
        "INSERT INTO narrative_chunks (raw_text) VALUES (%s) RETURNING id",
        (f"Clock contract scene {scene}",),
    )
    chunk_id = int(cur.fetchone()[0])
    insert_chunk_metadata_sync(
        cur,
        chunk_id=chunk_id,
        season=1,
        episode=1,
        scene=scene,
        world_layer=layer,
        time_delta=delta,
        generation_date=datetime.now(timezone.utc),
        slug=f"S01E01_{scene:03d}",
        generation_model=None,
        scene_weather=None,
    )
    return chunk_id


def test_world_layer_edit_restamps_clock(clock_db: tuple[str, int]) -> None:
    """An UPDATE of world_layer alone restamps the clock in both directions."""
    dbname, _ = clock_db
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE chunk_metadata SET world_layer = 'primary' "
            "WHERE world_layer = 'flashback' RETURNING chunk_id"
        )
        (flashback_id,) = cur.fetchone()
    assert _clock_minutes(dbname) == [0, 7, 10, 10]
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE chunk_metadata SET world_layer = 'flashback' WHERE chunk_id = %s",
            (flashback_id,),
        )
        assert cur.rowcount == 1
    assert _clock_minutes(dbname) == [0, 7, 7, 7]


def test_negative_time_delta_rejected(clock_db: tuple[str, int]) -> None:
    """Story time never runs backward: insert and update both hit the CHECK."""
    dbname, first = clock_db
    with closing(connect(dbname)) as conn:
        with pytest.raises(psycopg2.errors.CheckViolation) as inserted:
            with conn, conn.cursor() as cur:
                _insert_chunk(
                    cur, scene=5, layer="primary", delta=timedelta(minutes=-1)
                )
        assert inserted.value.diag.constraint_name == (
            "chunk_metadata_time_delta_nonnegative"
        )
        with pytest.raises(psycopg2.errors.CheckViolation) as updated:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE chunk_metadata SET time_delta = interval '-1 minute' "
                    "WHERE chunk_id = %s",
                    (first + 1,),
                )
        assert updated.value.diag.constraint_name == (
            "chunk_metadata_time_delta_nonnegative"
        )
    assert _clock_minutes(dbname) == [0, 7, 7, 7]


def test_bootstrap_delta_must_be_zero() -> None:
    """base_timestamp is the clock at the end of the bootstrap chunk."""
    with disposable_slot_database("qa640_clock") as dbname:
        seed_protagonist(dbname, base_timestamp=BASE.isoformat())
        with closing(connect(dbname)) as conn:
            with pytest.raises(psycopg2.errors.RaiseException) as raised:
                with conn, conn.cursor() as cur:
                    _insert_chunk(
                        cur, scene=1, layer="primary", delta=timedelta(minutes=5)
                    )
            assert "Bootstrap chunk" in str(raised.value)
            with conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM chunk_metadata")
                assert cur.fetchone()[0] == 0
            with conn, conn.cursor() as cur:
                bootstrap_id = _insert_chunk(cur, scene=1, layer="primary", delta=None)
            assert _clock_minutes(dbname) == [0]
            with pytest.raises(psycopg2.errors.RaiseException) as updated:
                with conn, conn.cursor() as cur:
                    cur.execute(
                        "UPDATE chunk_metadata SET time_delta = interval '1 minute' "
                        "WHERE chunk_id = %s",
                        (bootstrap_id,),
                    )
            assert "Bootstrap chunk" in str(updated.value)
            with conn, conn.cursor() as cur:
                cur.execute("SELECT time_delta FROM chunk_metadata")
                assert cur.fetchall() == [(None,)]


def test_refresh_writes_only_changed_rows(clock_db: tuple[str, int]) -> None:
    """A new chunk restamps itself; rows whose clock holds are not rewritten."""
    dbname, _ = clock_db
    xmin_sql = "SELECT chunk_id, xmin::text FROM chunk_metadata ORDER BY chunk_id"
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(xmin_sql)
        before = cur.fetchall()
        assert len(before) == 4
        _insert_chunk(cur, scene=5, layer="primary", delta=timedelta(minutes=2))
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(xmin_sql)
        assert cur.fetchall()[:4] == before
    assert _clock_minutes(dbname) == [0, 7, 7, 7, 9]


def test_seed_committed_chunk_bootstrap_elapses_no_time() -> None:
    """The shared seed's default delta is zero for the bootstrap chunk only."""
    with disposable_slot_database("qa640_clock") as dbname:
        seed_protagonist(dbname, base_timestamp=BASE.isoformat())
        seed_committed_chunk(dbname, raw_text="Bootstrap.", scene=1)
        seed_committed_chunk(dbname, raw_text="Next.", scene=2)
        assert _clock_minutes(dbname) == [0, 1]


def _migration_140_state(dbname: str) -> dict[str, Any]:
    """Read the clocks, the 140 stamp, the CHECK, and the trigger's state."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT world_time FROM chunk_metadata ORDER BY chunk_id")
        clocks = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT count(*) FROM schema_migrations WHERE version = '140'")
        stamps = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM pg_constraint "
            "WHERE conrelid = 'public.chunk_metadata'::regclass "
            "AND conname = 'chunk_metadata_time_delta_nonnegative'"
        )
        checks = cur.fetchone()[0]
        cur.execute(
            "SELECT tgenabled FROM pg_trigger "
            "WHERE tgrelid = 'public.chunk_metadata'::regclass "
            "AND tgname = 'trg_chunk_metadata_refresh_world_time'"
        )
        (enabled,) = cur.fetchone()
    return {"clocks": clocks, "stamps": stamps, "checks": checks, "enabled": enabled}


def test_migration_140_refuses_bad_clocks() -> None:
    """Migration 140 fails whole on a bad bootstrap or negative delta, then reruns."""
    with disposable_slot_database("qa640_clock") as dbname:
        seed_protagonist(dbname, base_timestamp=BASE.isoformat())
        chunk_ids = [
            seed_committed_chunk(dbname, raw_text=f"Chunk {scene}.", scene=scene)
            for scene in (1, 2, 3)
        ]
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE chunk_metadata "
                "DISABLE TRIGGER trg_chunk_metadata_refresh_world_time"
            )
            cur.execute(
                "ALTER TABLE chunk_metadata "
                "DROP CONSTRAINT chunk_metadata_time_delta_nonnegative"
            )
            cur.execute("DELETE FROM schema_migrations WHERE version = '140'")
            assert cur.rowcount == 1
            cur.execute(
                "UPDATE chunk_metadata SET time_delta = interval '5 minutes' "
                "WHERE chunk_id = %s",
                (chunk_ids[0],),
            )
        stored = _migration_140_state(dbname)
        assert stored["clocks"] == [BASE + timedelta(minutes=m) for m in (0, 1, 2)]
        assert (stored["stamps"], stored["checks"], stored["enabled"]) == (0, 0, "D")

        assert migrate.migrate_database(dbname, skip_locked=False) == (0, 1)
        assert _migration_140_state(dbname) == stored

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE chunk_metadata SET time_delta = interval '0' "
                "WHERE chunk_id = %s",
                (chunk_ids[0],),
            )
            cur.execute(
                "UPDATE chunk_metadata SET time_delta = interval '-1 minute' "
                "WHERE chunk_id = %s",
                (chunk_ids[2],),
            )
        assert migrate.migrate_database(dbname, skip_locked=False) == (0, 1)
        assert _migration_140_state(dbname) == stored

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE chunk_metadata SET time_delta = interval '1 minute' "
                "WHERE chunk_id = %s",
                (chunk_ids[2],),
            )
        assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)
        applied = _migration_140_state(dbname)
        assert applied["clocks"] == stored["clocks"]
        assert (applied["stamps"], applied["checks"], applied["enabled"]) == (
            1,
            1,
            "O",
        )
