"""Real preference-file persistence and read-only repository configuration."""

from pathlib import Path
import subprocess

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import tomlkit

from nexus.api.preferences_endpoints import router
from nexus.config import load_settings
from nexus.config.preferences import load_preferences, preferences_path


@pytest.fixture
def preferences_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "config" / "nexus.toml"
    config.parent.mkdir()
    doc = tomlkit.parse(Path("nexus.toml").read_text())
    doc["runtime"]["state_dir"] = str(tmp_path / "player-state")
    config.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))
    return config


def test_preferences_round_trip_keeps_repository_clean(
    preferences_config: Path,
) -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    repository_config = Path("nexus.toml")
    before = repository_config.read_bytes()
    status = subprocess.check_output(["git", "status", "--porcelain"])
    settings = load_settings()
    path = preferences_path(settings)
    assert not path.is_relative_to(Path.cwd())
    assert not path.exists()
    default = client.get("/api/preferences").json()
    assert default["theme"] == settings.ui.theme
    assert not path.exists()
    response = client.patch(
        "/api/preferences",
        json={"theme": "vector", "fonts": {"veil": {"body": "Georgia"}}},
    )
    assert response.status_code == 200, response.text
    assert path.exists()
    assert client.get("/api/preferences").json() == response.json()
    persisted = load_preferences()
    assert persisted.theme == "vector"
    assert persisted.fonts.veil.body == "Georgia"
    assert persisted.fonts.gilded == settings.ui.fonts.gilded
    assert persisted.wizard_model == settings.wizard.default_model
    assert repository_config.read_bytes() == before
    assert subprocess.check_output(["git", "status", "--porcelain"]) == status


@pytest.mark.parametrize(
    "patch",
    [
        {"test_mode": True},
        {"skald_model": "TEST"},
        {"theme": "bogus"},
        {"fonts": {"veil": {"unknown": "Georgia"}}},
        {"wizard_model": "retired-id"},
    ],
)
def test_invalid_preferences_never_create_file(
    preferences_config: Path, patch: dict
) -> None:
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).patch("/api/preferences", json=patch).status_code == 422
    assert not preferences_path(load_settings()).exists()
