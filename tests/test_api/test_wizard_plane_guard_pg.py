"""The player-plane wizard guard (issue #824, Decisions 824-Q4 and D-824-TRANSITION).

The player routes ``setup/start`` and ``transition`` refuse to overwrite or
repin a slot; the operator routes ``setup/overwrite`` and
``transition/overwrite`` keep that power. Every request goes through the real
player and operator projections of the gateway against a real slot-4 template
clone (``offline_gate_db``). The clients are never entered as context
managers, so no lifespan or scheduler runs.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any, Optional

import pytest
import tomlkit
from fastapi.testclient import TestClient

from nexus.api import narrative, new_story_flow
from nexus.api.new_story_cache import read_cache_raw
from nexus.api.route_capabilities import build_operator_app, build_player_app
from nexus.api.slot_state import get_slot_state
from nexus.config.story_model import read_story_settings
from tests.pg_fixtures import connect, seed_played_story

pytestmark = pytest.mark.requires_postgres

OCCUPIED_DETAIL = (
    "Slot 4 holds a story or a new-story wizard; only the operator plane can "
    "overwrite it"
)
PIN_DETAIL = "Slot 4 is pinned to TEST; only the operator plane can change its model"
STORY_DETAIL = "Slot 4 holds a story; only the operator plane can replace it"


@pytest.fixture
def player() -> TestClient:
    """The player projection of the gateway, without its lifespan."""
    return TestClient(build_player_app(narrative.app))


@pytest.fixture
def operator() -> TestClient:
    """The operator projection of the gateway, without its lifespan."""
    return TestClient(build_operator_app(narrative.app))


@pytest.fixture
def test_b(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Register a second test-provider model, ``TEST-B``, in a copied config."""
    config = tmp_path / "nexus.toml"
    doc: Any = tomlkit.parse(Path("nexus.toml").read_text())
    doc["runtime"]["state_dir"] = str(tmp_path / "player-state")
    models = doc["global"]["model"]["api_models"]["test"]["models"]
    second = tomlkit.inline_table()
    for key, value in models[0].items():
        if key != "uses":
            second[key] = value
    second["id"] = "TEST-B"
    second["label"] = "TEST-B"
    models.append(second)
    config.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))
    return "TEST-B"


def _chunk_ids(dbname: str) -> list[int]:
    """Every narrative chunk id on the clone, in order."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM narrative_chunks ORDER BY id")
        return [int(row[0]) for row in cur.fetchall()]


def _slot_model(dbname: str) -> Optional[str]:
    """The clone's ``global_variables.model`` (the Skald pin)."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT model FROM global_variables WHERE id = TRUE")
        row = cur.fetchone()
        return None if row is None else row[0]


def _genesis_run_count(dbname: str) -> int:
    """The number of genesis transition runs recorded on the clone."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM genesis_runs")
        return int(cur.fetchone()[0])


def _cached_thread(dbname: str) -> Optional[str]:
    """The wizard cache's thread id, or None without a cache."""
    cache = read_cache_raw(dbname)
    return None if cache is None else cache["thread_id"]


def test_player_start_refuses_an_occupied_slot(
    offline_gate_db: str, player: TestClient
) -> None:
    """A slot that holds a story is never restarted from the player plane."""
    chunks = seed_played_story(offline_gate_db, turns=1, slot=4)
    assert get_slot_state(4).is_empty is False
    model = _slot_model(offline_gate_db)

    response = player.post("/api/story/new/setup/start", json={"slot": 4})

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == OCCUPIED_DETAIL
    assert read_cache_raw(offline_gate_db) is None
    assert _chunk_ids(offline_gate_db) == chunks
    assert _slot_model(offline_gate_db) == model


def test_player_start_refuses_a_wizard_in_progress(
    offline_gate_db: str, player: TestClient
) -> None:
    """An in-progress wizard is never discarded from the player plane."""
    thread = new_story_flow.start_setup(4)

    response = player.post("/api/story/new/setup/start", json={"slot": 4})

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == OCCUPIED_DETAIL
    assert _cached_thread(offline_gate_db) == thread


def test_player_start_refuses_a_repin(
    offline_gate_db: str, player: TestClient, test_b: str
) -> None:
    """An empty slot keeps its model pin against a player-plane override."""
    assert get_slot_state(4).is_empty is True
    assert read_story_settings(offline_gate_db).skald_model == "TEST"

    response = player.post(
        "/api/story/new/setup/start", json={"slot": 4, "model": test_b}
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == PIN_DETAIL
    assert read_cache_raw(offline_gate_db) is None
    assert read_story_settings(offline_gate_db).skald_model == "TEST"


@pytest.mark.parametrize(
    "body",
    [{"slot": 4}, {"slot": 4, "model": "TEST"}],
    ids=["omitted-model", "pinned-model"],
)
def test_player_start_admits_an_empty_slot(
    offline_gate_db: str, player: TestClient, body: dict[str, Any]
) -> None:
    """An empty slot starts on the player plane, naming its pin or no model."""
    assert get_slot_state(4).is_empty is True

    response = player.post("/api/story/new/setup/start", json=body)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["model"] == "TEST"
    assert _cached_thread(offline_gate_db) == result["thread_id"]


def test_operator_overwrite_restarts_and_repins(
    offline_gate_db: str, player: TestClient, operator: TestClient, test_b: str
) -> None:
    """The operator route restarts an occupied wizard and replaces its pin."""
    old = new_story_flow.start_setup(4)

    response = operator.post(
        "/api/story/new/setup/overwrite", json={"slot": 4, "model": test_b}
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["thread_id"] != old
    assert _cached_thread(offline_gate_db) == result["thread_id"]
    assert read_story_settings(offline_gate_db).skald_model == test_b
    refused = player.post(
        "/api/story/new/setup/overwrite", json={"slot": 4, "model": test_b}
    )
    assert refused.status_code in {404, 405}, refused.text


def test_player_transition_refuses_a_story_slot(
    offline_gate_db: str, player: TestClient, operator: TestClient
) -> None:
    """The player transition never wipes a story, whichever projection serves it."""
    chunks = seed_played_story(offline_gate_db, turns=1, slot=4)
    runs = _genesis_run_count(offline_gate_db)

    for client in (player, operator):
        response = client.post("/api/story/new/transition", json={"slot": 4})
        assert response.status_code == 409, response.text
        assert response.json()["detail"] == STORY_DETAIL

    assert _genesis_run_count(offline_gate_db) == runs
    assert _chunk_ids(offline_gate_db) == chunks


def test_operator_transition_passes_the_guard(
    offline_gate_db: str, player: TestClient, operator: TestClient
) -> None:
    """The operator transition reaches the wizard cache read on a story slot."""
    chunks = seed_played_story(offline_gate_db, turns=1, slot=4)

    response = operator.post("/api/story/new/transition/overwrite", json={"slot": 4})

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == (
        "No setup data found for slot 4. Complete the wizard first."
    )
    assert _chunk_ids(offline_gate_db) == chunks
    refused = player.post("/api/story/new/transition/overwrite", json={"slot": 4})
    assert refused.status_code in {404, 405}, refused.text


def test_player_transition_admits_a_fresh_wizard(
    offline_gate_db: str, player: TestClient
) -> None:
    """A wizard on an empty slot passes the guard and meets the cache checks."""
    new_story_flow.start_setup(4)

    response = player.post("/api/story/new/transition", json={"slot": 4})

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == (
        "Confirm the setting and character before starting the story."
    )
