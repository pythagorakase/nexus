"""Real HTTP feed proofs on TEST-pinned clones; no owner database is opened.

Tables: narrative_chunks, chunk_metadata, global_variables, incubator, and the
protagonist tables seeded by the existing helper. Fixtures own/drop all writes.
The large seed retains the real slug, world-time and IDF triggers.
"""

from contextlib import closing
from typing import Any, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg2.extras import Json

from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER
from nexus.api.reader_endpoints import router
from nexus.config import load_settings
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_committed_chunk,
    seed_protagonist,
)

pytestmark = pytest.mark.requires_postgres
SLOT = 3


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Exercise the production reader router without gateway side effects."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _prologue(dbname: str, *, scene: int = 0) -> int:
    """Insert the marker case that the committed-chunk helper cannot supply."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO narrative_chunks (raw_text, authorial_directives) "
            "VALUES (%s, %s) RETURNING id",
            (
                "You stand beside Lake Michigan in Chicago.",
                Json([RETROGRADE_PROLOGUE_MARKER]),
            ),
        )
        chunk_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO chunk_metadata (chunk_id, season, episode, scene, "
            "world_layer, time_delta) VALUES (%s, 0, 0, %s, 'primary', interval '0')",
            (chunk_id, scene),
        )
        return int(chunk_id)


@pytest.fixture(scope="module")
def story() -> Iterator[tuple[str, list[int], int, int]]:
    """Seed 1,200 chunks once, preserving all real per-statement triggers."""
    with disposable_slot_database("qa640_767s1_feed") as dbname:
        seed_protagonist(dbname)
        prologue = _prologue(dbname)
        ids = []
        unused = 0
        for i in range(1200):
            if i % 37 == 0:
                with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                    cur.execute("SELECT nextval('narrative_chunks_id_seq')")
                    unused = int(cur.fetchone()[0])
            prose = f"You walk along the Chicago River and count bridge {i + 1}."
            if i == 601:
                prose = (
                    "<!-- SCENE BREAK: S02E01_002 (storyteller heading) -->\n"
                    "# Chicago\n" + prose
                )
            ids.append(
                seed_committed_chunk(
                    dbname,
                    raw_text=prose,
                    season=1 + i // 600,
                    episode=1 + (i // 200) % 3,
                    scene=1 + i % 200,
                )
            )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*), count(DISTINCT slug), min(scene), max(scene) "
                "FROM chunk_metadata WHERE season > 0"
            )
            assert cur.fetchone() == (1200, 1200, 1, 200)
            cur.execute(
                "SELECT world_time = base_timestamp + interval '1200 minutes' "
                "FROM chunk_metadata, global_variables WHERE chunk_id = %s",
                (ids[-1],),
            )
            assert cur.fetchone() == (True,)
            cur.execute(
                "SELECT tgenabled FROM pg_trigger "
                "WHERE tgrelid = 'chunk_metadata'::regclass "
                "AND tgname = 'trg_chunk_metadata_refresh_world_time'"
            )
            assert cur.fetchone() == ("O",)
        yield dbname, ids, prologue, unused


@pytest.fixture
def routed(
    story: tuple[str, list[int], int, int], monkeypatch: pytest.MonkeyPatch
) -> tuple[str, list[int], int, int]:
    """Route only the test slot; all other slot targets fail closed."""
    route_slot_to_disposable(monkeypatch.setattr, slot=SLOT, dbname=story[0])
    return story


def _feed(client: TestClient, **options: Any) -> dict[str, Any]:
    response = client.get("/api/narrative/feed", params={"slot": SLOT, **options})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"chunks", "previousCursor", "nextCursor"}
    assert [row["id"] for row in body["chunks"]] == sorted(
        row["id"] for row in body["chunks"]
    )
    return body


def _ids(page: dict[str, Any]) -> list[int]:
    return [row["id"] for row in page["chunks"]]


def test_feed_walks_1200_chunks_both_directions_without_gaps_or_duplicates(
    client: TestClient, routed: tuple[str, list[int], int, int]
) -> None:
    """Both strict cursor walks exactly reproduce the sparse playable corpus."""
    ids = routed[1]
    forward = []
    page = _feed(client, after=1, limit=73)
    assert page["previousCursor"] is None
    while True:
        forward.extend(_ids(page))
        if page["nextCursor"] is None:
            break
        page = _feed(client, after=page["nextCursor"], limit=73)
    backward: list[int] = []
    page = _feed(client, limit=73)
    assert page["nextCursor"] is None
    while True:
        backward = _ids(page) + backward
        if page["previousCursor"] is None:
            break
        page = _feed(client, before=page["previousCursor"], limit=73)
    assert forward == backward == ids
    assert len(set(forward)) == 1200


def test_feed_anchor_centers_and_fills_at_story_edges(
    client: TestClient, routed: tuple[str, list[int], int, int]
) -> None:
    """Odd/even centers and edge shortages return exact neighboring IDs."""
    ids = routed[1]
    for index in (0, 1, 199, 200, 600, 1198, 1199):
        for limit in (1, 4, 5):
            start = max(0, min(index - (limit - 1) // 2, len(ids) - limit))
            assert (
                _ids(_feed(client, anchor=ids[index], limit=limit))
                == ids[start : start + limit]
            )


def test_feed_episode_boundaries_use_global_playable_predecessors(
    client: TestClient,
    routed: tuple[str, list[int], int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Page edges, prologues, nullable coordinates and recurrence stay honest."""
    ids = routed[1]
    assert [
        row["episodeBoundary"]
        for row in _feed(client, after=ids[197], limit=4)["chunks"]
    ] == [False, False, True, False]
    assert (
        _feed(client, after=ids[199], limit=1)["chunks"][0]["episodeBoundary"] is True
    )
    assert (
        _feed(client, after=ids[599], limit=1)["chunks"][0]["episodeBoundary"] is True
    )
    assert _feed(client, before=ids[1], limit=1)["chunks"][0]["episodeBoundary"] is True
    with disposable_slot_database("qa640_767s1_feed") as dbname:
        seed_protagonist(dbname)
        small = []
        for index, pair in enumerate(
            ((1, 1), (1, 2), (1, 1), (None, 1), (None, 1), (None, None))
        ):
            if index == 4:
                _prologue(dbname)
            if None in pair:
                # Helper formats integer slugs; only this nullable case needs SQL.
                with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO narrative_chunks (raw_text) "
                        "VALUES ('You cross the Potomac River in Washington.') "
                        "RETURNING id"
                    )
                    chunk_id = int(cur.fetchone()[0])
                    cur.execute(
                        "INSERT INTO chunk_metadata (chunk_id, season, episode, "
                        "scene, world_layer, time_delta) "
                        "VALUES (%s, %s, %s, %s, 'primary', interval '0')",
                        (chunk_id, *pair, index + 1),
                    )
                    small.append(chunk_id)
            else:
                assert pair[0] is not None and pair[1] is not None
                small.append(
                    seed_committed_chunk(
                        dbname,
                        raw_text="You cross the Potomac River in Washington.",
                        season=pair[0],
                        episode=pair[1],
                        scene=index + 1,
                    )
                )
        route_slot_to_disposable(monkeypatch.setattr, slot=SLOT, dbname=dbname)
        page = _feed(client)
        assert _ids(page) == small
        assert [row["episodeBoundary"] for row in page["chunks"]] == [
            True,
            True,
            True,
            True,
            False,
            True,
        ]
        assert (
            _feed(client, after=small[3], limit=1)["chunks"][0]["episodeBoundary"]
            is False
        )


def test_feed_rejects_bad_selectors_limits_and_unplayable_anchors(
    client: TestClient, routed: tuple[str, list[int], int, int]
) -> None:
    """Invalid selectors fail validation and absent anchors retain exact 404s."""
    for options in (
        {"anchor": 1, "before": 2},
        {"anchor": 1, "after": 2},
        {"before": 1, "after": 2},
        {"anchor": 1, "before": 2, "after": 3},
    ):
        response = client.get("/api/narrative/feed", params={"slot": SLOT, **options})
        assert response.status_code == 422
        assert (
            response.json()["detail"] == "Specify at most one of anchor, before, after"
        )
    for key in ("anchor", "before", "after", "limit"):
        for value in ("bad", "1.5", 0, -1):
            assert (
                client.get(
                    "/api/narrative/feed", params={"slot": SLOT, key: value}
                ).status_code
                == 422
            )
    assert (
        client.get(
            "/api/narrative/feed",
            params={"slot": SLOT, "limit": load_settings().ui.reader.max_page_size + 1},
        ).status_code
        == 422
    )
    for anchor in (routed[2], routed[3], routed[1][-1] + 999):
        response = client.get(
            "/api/narrative/feed", params={"slot": SLOT, "anchor": anchor}
        )
        assert response.status_code == 404
        assert response.json()["detail"] == f"Chunk {anchor} not found"


def test_feed_defaults_empty_edges_and_sparse_thresholds(
    client: TestClient,
    routed: tuple[str, list[int], int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defaults read the newest page; thresholds need not identify a row."""
    ids, unused = routed[1], routed[3]
    assert _ids(_feed(client)) == ids[-load_settings().ui.reader.default_page_size :]
    assert (
        _ids(_feed(client, limit=load_settings().ui.reader.max_page_size)) == ids[-200:]
    )
    for options in ({"before": ids[0]}, {"after": ids[-1]}):
        assert _feed(client, **options) == {
            "chunks": [],
            "previousCursor": None,
            "nextCursor": None,
        }
    assert (
        _ids(_feed(client, before=unused, limit=4))
        == [i for i in ids if i < unused][-4:]
    )
    assert (
        _ids(_feed(client, after=unused, limit=4)) == [i for i in ids if i > unused][:4]
    )
    with disposable_slot_database("qa640_767s1_feed") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=SLOT, dbname=dbname)
        assert _feed(client) == {
            "chunks": [],
            "previousCursor": None,
            "nextCursor": None,
        }


def test_feed_preserves_existing_chunk_payload(
    client: TestClient, routed: tuple[str, list[int], int, int]
) -> None:
    """Every field, including UTC clock and inline markup, matches by-ID HTTP."""
    for options in (
        {"limit": 4},
        {"before": routed[1][4], "limit": 4},
        {"after": routed[1][598], "limit": 4},
        {"anchor": routed[1][600], "limit": 4},
    ):
        for row in _feed(client, **options)["chunks"]:
            row.pop("episodeBoundary")
            response = client.get(
                f"/api/narrative/chunks/{row['id']}", params={"slot": SLOT}
            )
            assert response.status_code == 200
            assert row == response.json()


def _canonical_rows(dbname: str) -> list[Any]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        result = []
        for table, key in (
            ("narrative_chunks", "id"),
            ("chunk_metadata", "chunk_id"),
            ("global_variables", "id"),
            ("incubator", "id"),
        ):
            cur.execute(f"SELECT row_to_json(t) FROM {table} t ORDER BY {key}")
            result.append(cur.fetchall())
        return result


def test_feed_read_leaves_canonical_rows_unchanged(
    client: TestClient, routed: tuple[str, list[int], int, int]
) -> None:
    """All selector reads leave all four canonical table snapshots identical."""
    before = _canonical_rows(routed[0])
    for options in (
        {},
        {"before": routed[1][600]},
        {"after": routed[1][600]},
        {"anchor": routed[1][600]},
    ):
        _feed(client, **options)
    assert _canonical_rows(routed[0]) == before
