"""Settings HTTP tests using real configuration and temporary TOML writes."""

import shutil
import tomllib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api import settings_endpoints
from nexus.api.settings_endpoints import (
    _build_payload,
    _read_raw_settings,
    router,
)
from nexus.config.loader import load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "nexus.toml"
    shutil.copy2(REPO_ROOT / "nexus.toml", path)
    monkeypatch.setattr(settings_endpoints, "NEXUS_TOML", path)
    return path


@pytest.fixture
def client(config_path: Path) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_head_and_get_serve_concrete_selections(client: TestClient) -> None:
    assert client.head("/api/settings").status_code == 200
    response = client.get("/api/settings")
    assert response.status_code == 200
    payload = response.json()
    assert "secrets" not in payload
    assert "typewriter_ms_per_char" not in payload["ui"]
    assert "typewriter" not in payload["settings_meta"]
    assert payload["apex"]["model"] == load_settings().apex.model
    assert payload["apex"].get("gaia_model") == load_settings().apex.gaia_model
    assert not payload["apex"]["model"].startswith("@")
    assert payload["API Settings"]["apex"] == payload["apex"]
    assert payload["Agent Settings"]["global"] == payload["global"]


def test_picker_lists_every_visible_model() -> None:
    raw = _read_raw_settings()
    meta = _build_payload(raw)["settings_meta"]
    expected = {
        (provider, model["id"])
        for provider, cfg in raw["global"]["model"]["api_models"].items()
        if cfg.get("ui_visible", True)
        for model in cfg["models"]
    }
    assert {(m["provider"], m["id"]) for m in meta["models"]} == expected
    assert "test" not in meta["apex_allowed_providers"]
    assert {"openai", "anthropic", "local"} <= set(meta["apex_allowed_providers"])
    assert "typewriter" not in meta
    assert "model_roles" not in meta


def test_repository_settings_are_read_only(
    client: TestClient, config_path: Path
) -> None:
    before = config_path.read_bytes()
    assert client.patch("/api/settings", json={"theme": "vector"}).status_code == 405
    assert config_path.read_bytes() == before
