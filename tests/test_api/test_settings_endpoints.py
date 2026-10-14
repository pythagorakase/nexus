"""Settings HTTP tests using real configuration and temporary TOML writes."""

import shutil
from pathlib import Path

import pytest
import tomlkit
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

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

# Every top-level key GET /api/settings serves: each nexus.toml section except
# secrets, plus the derived settings_meta block.
SERVED_KEYS = {
    "global",
    "local_models",
    "ui",
    "wizard",
    "api",
    "lore",
    "orrery",
    "memnon",
    "memory",
    "storyteller",
    "apex",
    "summaries",
    "ir_eval",
    "usage",
    "runtime",
    "character_identity",
    "settings_meta",
}


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
    for section in set(raw) - {"secrets"}:
        assert payload[section] == raw[section], section
    assert payload["settings_meta"] == _build_settings_meta(raw).model_dump()


def test_get_top_level_keys_are_pinned(client: TestClient) -> None:
    """The served sections and the typed response declare the same keys."""
    from nexus.api.settings_endpoints import SettingsPayload

    payload = client.get("/api/settings").json()
    assert set(payload) == SERVED_KEYS
    declared = {
        field.alias or name for name, field in SettingsPayload.model_fields.items()
    }
    assert declared == SERVED_KEYS


def test_get_declares_the_typed_response(client: TestClient) -> None:
    """The OpenAPI schema names SettingsPayload as the GET response."""
    schema = client.app.openapi()  # type: ignore[attr-defined]
    response = schema["paths"]["/api/settings"]["get"]["responses"]["200"]
    ref = response["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/SettingsPayload")


def test_absent_optional_section_is_omitted(
    client: TestClient, config_path: Path
) -> None:
    """A section absent from the file is absent from the JSON, never null."""
    doc = tomlkit.parse(config_path.read_text())
    del doc["api"]
    config_path.write_text(tomlkit.dumps(doc))
    payload = client.get("/api/settings").json()
    assert "api" not in payload


def test_unknown_section_fails_loudly(client: TestClient, config_path: Path) -> None:
    """An unknown top-level section raises instead of being served."""
    config_path.write_text(config_path.read_text() + "\n[stray]\nkey = 1\n")
    with pytest.raises(ValidationError, match="stray"):
        client.get("/api/settings")


def test_picker_lists_every_visible_model() -> None:
    raw = _read_raw_settings()
    meta = _build_payload(raw).settings_meta.model_dump()
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
