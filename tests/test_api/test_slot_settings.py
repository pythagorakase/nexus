"""Real route, resolver, and wizard checks on a disposable migrated slot clone."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import tomlkit

from nexus.api import new_story_flow, slot_endpoints
from nexus.config import load_settings, load_settings_as_dict
from nexus.config.preferences import save_preferences
from nexus.config.story_model import (
    StorySettings,
    read_story_settings,
    resolve_story_model,
    story_context_settings,
)
from nexus.memory.manager import pass2_baseline_config_fingerprint
from tests.pg_fixtures import connect

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def client(offline_gate_db: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(slot_endpoints, "slot_dbname", lambda slot: offline_gate_db)
    app = FastAPI()
    app.include_router(slot_endpoints.router)
    return TestClient(app)


def test_slot_settings_round_trip(client: TestClient, offline_gate_db: str) -> None:
    model = load_settings().apex.model
    patch = {"skald_model": model, "gaia_model": model, "apex_context_window": 100_000}
    response = client.patch("/api/slot/4/settings", json=patch)
    assert response.status_code == 200, response.text
    assert response.json() == patch
    assert client.get("/api/slot/4/settings").json() == patch
    with connect(offline_gate_db) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT model, gaia_model, apex_context_window FROM global_variables WHERE id"
        )
        assert cur.fetchone() == (model, model, 100_000)
    assert (
        client.patch("/api/slot/4/settings", json={"gaia_model": None}).json()[
            "gaia_model"
        ]
        is None
    )
    assert client.get("/api/slot/4/model").status_code == 404
    for patch in (
        {"skald_model": "retired-id"},
        {"gaia_model": "retired-id"},
        {"apex_context_window": 999},
    ):
        assert client.patch("/api/slot/4/settings", json=patch).status_code == 422


def test_retired_pin_raises_and_can_be_cleared(
    client: TestClient, offline_gate_db: str
) -> None:
    with connect(offline_gate_db) as conn, conn.cursor() as cur:
        cur.execute("UPDATE global_variables SET model = 'retired-id' WHERE id")
    story = read_story_settings(offline_gate_db)
    with pytest.raises(ValueError, match="absent from the registry"):
        resolve_story_model("skald", story=story)
    assert resolve_story_model("skald", story=story, override="TEST") == "TEST"
    assert (
        client.patch("/api/slot/4/settings", json={"skald_model": None}).status_code
        == 200
    )
    assert (
        resolve_story_model("skald", story=read_story_settings(offline_gate_db))
        == load_settings().apex.model
    )


def test_context_fingerprint_is_scoped_to_story(
    client: TestClient, offline_gate_db: str
) -> None:
    defaults = load_settings_as_dict()
    other = story_context_settings(defaults, StorySettings(apex_context_window=75_000))
    other_fingerprint = pass2_baseline_config_fingerprint(other)
    before = pass2_baseline_config_fingerprint(defaults)
    assert (
        client.patch(
            "/api/slot/4/settings", json={"apex_context_window": 100_000}
        ).status_code
        == 200
    )
    changed = story_context_settings(defaults, read_story_settings(offline_gate_db))
    assert pass2_baseline_config_fingerprint(changed) != before
    assert pass2_baseline_config_fingerprint(other) == other_fingerprint
    assert pass2_baseline_config_fingerprint(defaults) == before


def test_wizard_records_player_model_in_slot(
    offline_gate_db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "nexus.toml"
    doc = tomlkit.parse(Path("nexus.toml").read_text())
    doc["runtime"]["state_dir"] = str(tmp_path / "player-state")
    config.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))
    save_preferences({"wizard_model": "TEST"})
    thread_id = new_story_flow.start_setup(4)
    assert thread_id
    assert read_story_settings(offline_gate_db).skald_model == "TEST"
    with connect(offline_gate_db) as conn, conn.cursor() as cur:
        cur.execute("SELECT thread_id FROM assets.new_story_creator WHERE id")
        assert cur.fetchone() == (thread_id,)


def test_setting_card_database_failure_is_loud(offline_gate_db: str) -> None:
    """An actual failed Setting Card query never becomes a cached empty prompt."""
    import psycopg2
    from nexus.agents.lore.logon_utility import LogonUtility

    utility = LogonUtility(load_settings_as_dict(), dbname=offline_gate_db)
    with connect(offline_gate_db) as conn, conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE global_variables RENAME COLUMN setting TO unavailable_setting"
        )
    try:
        for _ in range(2):
            with pytest.raises(psycopg2.errors.UndefinedColumn, match="setting"):
                utility._load_setting_context()
            assert utility._setting_context_loaded is False
    finally:
        with connect(offline_gate_db) as conn, conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE global_variables RENAME COLUMN unavailable_setting TO setting"
            )
    utility._load_setting_context()
    assert utility._setting_context_loaded is True
