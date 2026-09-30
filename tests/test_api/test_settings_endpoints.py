"""Settings HTTP tests using real configuration and temporary TOML writes."""

import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api.settings_endpoints import (
    _build_payload,
    _build_settings_meta,
    _read_raw_settings,
    router,
)
from nexus.config.loader import load_settings
from nexus.config.settings_models import materialize_model_selections
from nexus.runtime.contract import HOME_ENV, RUNTIME_CONFIG_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]

# The retired dict-façade aliases (issue #809); GET must not serve them.
LEGACY_ALIAS_KEYS = ("Agent Settings", "API Settings")

# Sections SettingsPayload in ui/client/src/types/settings.ts reads, plus the
# top-level global block the payload still serves raw.
CLIENT_SECTIONS = (
    "global",
    "apex",
    "local_models",
    "wizard",
    "lore",
    "memnon",
    "orrery",
    "ui",
)


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "nexus.toml"
    shutil.copy2(REPO_ROOT / "nexus.toml", path)
    monkeypatch.delenv(HOME_ENV, raising=False)
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(path))
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
    raw = materialize_model_selections(_read_raw_settings())
    assert payload["apex"] == raw["apex"]
    assert payload["global"] == raw["global"]


def test_get_serves_no_legacy_alias_blocks(client: TestClient) -> None:
    payload = client.get("/api/settings").json()
    for key in LEGACY_ALIAS_KEYS:
        assert key not in payload
    raw = materialize_model_selections(_read_raw_settings())
    assert set(payload) == (set(raw) - {"secrets"}) | {"settings_meta"}
    for section in CLIENT_SECTIONS:
        assert payload[section] == raw[section], section
    assert payload["settings_meta"] == _build_settings_meta(raw)


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


@pytest.mark.parametrize("method", ["patch", "put"])
@pytest.mark.parametrize("alias", LEGACY_ALIAS_KEYS)
def test_alias_bodies_meet_the_same_read_only_refusal(
    client: TestClient, config_path: Path, method: str, alias: str
) -> None:
    before = config_path.read_bytes()
    body = {alias: {"apex": {"model": "rejected"}}}
    assert getattr(client, method)("/api/settings", json=body).status_code == 405
    assert config_path.read_bytes() == before
