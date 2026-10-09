"""Bounded chunk-range HTTP reads on disposable, TEST-pinned PostgreSQL clones.

Tables: narrative_chunks, chunk_metadata, global_variables and protagonist
tables. All seeding retains production triggers; fixtures remove their clones.
"""

from contextlib import closing
from pathlib import Path
from typing import Any, Iterator

import pytest
import tomlkit
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg2.extras import Json

from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER
from nexus.api.reader_endpoints import router
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_committed_chunk,
    seed_protagonist,
)
from tests.scheduler_helpers import private_runtime_config

pytestmark = pytest.mark.requires_postgres
SLOT = 3
Story = tuple[str, list[int], list[int], int]


@pytest.fixture(autouse=True)
def small_pages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the configured bound through a private runtime configuration."""
    document: Any
    document, path = private_runtime_config(tmp_path, monkeypatch)
    document["ui"]["reader"].update(default_page_size=3, max_page_size=3)
    path.write_text(tomlkit.dumps(document))


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Dispatch the real router without starting a gateway lifespan."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(scope="module")
def story() -> Iterator[Story]:
    """Seed a prologue followed by seven playable chunks with two ID gaps."""
    with disposable_slot_database("qa640_815s2_range") as dbname:
        seed_protagonist(dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO narrative_chunks (raw_text, authorial_directives) "
                "VALUES (%s, %s) RETURNING id",
                ("You stand beside Lake Michigan.", Json([RETROGRADE_PROLOGUE_MARKER])),
            )
            prologue = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO chunk_metadata (chunk_id, season, episode, scene, "
                "world_layer, time_delta) "
                "VALUES (%s, 0, 0, 0, 'primary', interval '0')",
                (prologue,),
            )
        ids, gaps = [], []
        for index in range(7):
            ids.append(
                seed_committed_chunk(
                    dbname,
                    raw_text=f"You cross Chicago bridge {index + 1}.",
                    scene=index + 1,
                )
            )
            if index in (1, 4):
                with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                    cur.execute("SELECT nextval('narrative_chunks_id_seq')")
                    gaps.append(int(cur.fetchone()[0]))
        yield dbname, ids, gaps, prologue


@pytest.fixture
def routed(story: Story, monkeypatch: pytest.MonkeyPatch) -> Story:
    """Route only this slot to the clone and refuse other slot connections."""
    route_slot_to_disposable(monkeypatch.setattr, slot=SLOT, dbname=story[0])
    return story


def _page(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/narrative/chunks", params={"slot": SLOT, **params})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"chunks", "nextCursor"}
    return body


def test_desc_pages_walk_every_playable_chunk_across_gaps(
    client: TestClient, routed: Story
) -> None:
    """The configured cap and extra-row probe retain all seven sparse rows."""
    collected: list[int] = []
    sizes: list[int] = []
    cursor = None
    for _ in range(4):
        options: dict[str, int] = {} if cursor is None else {"before": cursor}
        page = _page(client, order="desc", limit=5, **options)
        collected.extend(row["id"] for row in page["chunks"])
        sizes.append(len(page["chunks"]))
        cursor = page["nextCursor"]
        if cursor is None:
            break
        assert cursor == page["chunks"][-1]["id"]
    assert collected == list(reversed(routed[1]))
    assert sizes == [3, 3, 1]
    assert len(set(collected)) == 7
    assert routed[3] not in collected


def test_asc_bounds_are_exclusive_and_cursor_continues(
    client: TestClient, routed: Story
) -> None:
    """Both bounds exclude their rows and a threshold need not name a row."""
    ids = routed[1]
    page = _page(client, order="asc", limit=3, after=ids[1], before=ids[-1])
    assert [row["id"] for row in page["chunks"]] == ids[2:5]
    assert page["nextCursor"] == ids[4]
    page = _page(client, order="asc", limit=3, after=page["nextCursor"], before=ids[-1])
    assert [row["id"] for row in page["chunks"]] == ids[5:6]
    assert page["nextCursor"] is None
    page = _page(client, order="asc", limit=3, after=routed[2][0])
    assert page["chunks"][0]["id"] == ids[2]


def test_last_page_ending_at_the_edge_has_no_cursor(
    client: TestClient, routed: Story
) -> None:
    """Exactly one capped page of remaining rows is final, not an extra request."""
    page = _page(client, order="asc", limit=4, after=routed[1][3])
    assert [row["id"] for row in page["chunks"]] == routed[1][4:]
    assert page["nextCursor"] is None


def test_range_payload_equals_the_single_chunk_route(
    client: TestClient, routed: Story
) -> None:
    """The CLI route preserves the existing per-chunk wire shape exactly."""
    for chunk_id in routed[1]:
        page = _page(client, order="asc", limit=1, after=chunk_id - 1)
        response = client.get(
            f"/api/narrative/chunks/{chunk_id}", params={"slot": SLOT}
        )
        assert response.status_code == 200
        assert page["chunks"] == [response.json()]


def test_range_rejects_bad_parameters(client: TestClient, routed: Story) -> None:
    """Required selectors and positive bounds are enforced before any read."""
    cases: tuple[dict[str, Any], ...] = (
        {"limit": 1},
        {"order": "asc"},
        {"order": "sideways", "limit": 1},
        {"order": "asc", "limit": 0},
        {"order": "asc", "limit": 1, "after": -1},
        {"order": "asc", "limit": 1, "before": 0},
    )
    for params in cases:
        response = client.get("/api/narrative/chunks", params={"slot": SLOT, **params})
        assert response.status_code == 422, response.text


def test_range_of_an_unplayed_story_is_empty(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh clone returns one empty page and no cursor."""
    with disposable_slot_database("qa640_815s2_range_empty") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=SLOT, dbname=dbname)
        assert _page(client, order="desc", limit=1) == {
            "chunks": [],
            "nextCursor": None,
        }
