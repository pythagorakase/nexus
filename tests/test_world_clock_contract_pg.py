"""Clock identity through real metadata writes on a disposable template clone.

Requires narrative_chunks, chunk_metadata (including its clock trigger),
narrative_view, global_variables, characters, and places. The shared fixture
migrates and drops only its disposable database; no live save is written.
"""

from collections.abc import Iterator
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.api.commit_handler_sync import insert_chunk_metadata_sync
from nexus.api.reader_endpoints import _CHUNK_SELECT, _chunk_payload
from nexus.util.clock_face import clock_face
from scripts.qa_shift.world_clock import measure_connection
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_protagonist,
    sqlalchemy_url,
)

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
                    # Pin the existing inclusive, all-layer trigger semantics.
                    assert [r["world_time"] for r in rows] == [
                        BASE + timedelta(minutes=m) for m in (0, 7, 10, 10)
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
                prompt = LogonUtility({})._format_context_prompt(
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
