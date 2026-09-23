"""Settings HTTP tests using real configuration and temporary TOML writes."""

import shutil
import tomllib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api import settings_endpoints
from nexus.api.settings_endpoints import (
    FontSlotsPatch,
    SettingsPatchRequest,
    _build_payload,
    _read_raw_settings,
    _updates_from_patch,
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


@pytest.mark.parametrize(
    "body,status",
    [
        ({}, 400),
        ({"embedding_model": "x"}, 422),
        ({"typewriter_ms_per_char": 35}, 422),
        ({"apex_model_id": "unregistered-model"}, 422),
        ({"apex_model_id": "@anthropic.deep"}, 422),
        ({"gaia_model_id": "unregistered-model"}, 422),
        ({"gaia_model_id": "@openai.default"}, 422),
        ({"gaia_model_id": ""}, 422),
        ({"wizard_model_id": "@openai.default"}, 422),
        ({"apex_model_ref": "@openai.default"}, 422),
    ],
)
def test_invalid_patch_preserves_file(
    client: TestClient, config_path: Path, body: dict, status: int
) -> None:
    before = config_path.read_bytes()
    assert client.patch("/api/settings", json=body).status_code == status
    assert config_path.read_bytes() == before


def test_patch_maps_supported_fields() -> None:
    model = load_settings().apex.model
    patch = SettingsPatchRequest(
        theme="gilded",
        fonts={"vector": FontSlotsPatch(menu="Monaco")},
        test_mode=True,
        apex_model_id=model,
        gaia_model_id=model,
        wizard_model_id=model,
        apex_context_window=100_000,
    )
    assert _updates_from_patch(patch) == {
        "ui.theme": "gilded",
        "ui.fonts.vector.menu": "Monaco",
        "global.narrative.test_mode": True,
        "apex.model": model,
        "apex.gaia_model": model,
        "wizard.default_model": model,
        "lore.token_budget.apex_context_window": 100_000,
    }


@pytest.mark.parametrize("provider", ["openai", "anthropic", "local", "openrouter"])
def test_picker_write_moves_roster_uses_and_survives_model_upgrade(
    client: TestClient, config_path: Path, provider: str
) -> None:
    """Selection and later ID replacement work without maintaining aliases."""
    settings = load_settings(config_path)
    gaia_model = settings.apex.gaia_model
    model = settings.global_.model.api_models[provider].models[-1].id
    response = client.patch(
        "/api/settings",
        json={"apex_model_id": model, "wizard_model_id": model, "theme": "vector"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["apex"]["model"] == model
    assert response.json()["wizard"]["default_model"] == model
    assert response.json()["apex"].get("gaia_model") == gaia_model
    assert response.json()["apex"]["provider"] == (
        provider if provider in {"openai", "anthropic"} else "local"
    )
    raw = tomllib.loads(config_path.read_text())
    assert "model" not in raw["apex"]
    assert "default_model" not in raw["wizard"]
    assert "# Active NEXUS IRIS theme" in config_path.read_text()
    entries = [
        e for p in raw["global"]["model"]["api_models"].values() for e in p["models"]
    ]
    for use in ("apex.model", "wizard.default_model"):
        assert [e["id"] for e in entries if use in e.get("uses", [])] == [model]

    # Exactly one ID edit; assignments and every model capability remain intact.
    updated_id = model + "-next"
    text = config_path.read_text()
    assert text.count(f'id = "{model}"') == 1
    config_path.write_text(text.replace(f'id = "{model}"', f'id = "{updated_id}"'))
    refreshed = client.get("/api/settings").json()
    assert refreshed["apex"]["model"] == updated_id
    assert refreshed["wizard"]["default_model"] == updated_id
    assert load_settings(config_path).apex.model == updated_id


@pytest.mark.parametrize("provider", ["openai", "anthropic", "local", "openrouter"])
def test_gaia_assignment_is_independent_and_tracks_roster_upgrades(
    client: TestClient, config_path: Path, provider: str
) -> None:
    """The Gaia picker moves only its own use, leaving every other seat intact."""
    before = load_settings(config_path)
    model = before.global_.model.api_models[provider].models[-1].id
    response = client.patch("/api/settings", json={"gaia_model_id": model})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["apex"]["gaia_model"] == model
    assert payload["API Settings"]["apex"]["gaia_model"] == model
    after = load_settings(config_path)
    assert after.apex.model == before.apex.model
    assert after.apex.provider == before.apex.provider
    assert after.wizard.default_model == before.wizard.default_model
    assert after.orrery.experiences.model == before.orrery.experiences.model
    assert (
        after.storyteller.correspondence.compaction_model
        == before.storyteller.correspondence.compaction_model
    )

    raw = tomllib.loads(config_path.read_text())
    assert "gaia_model" not in raw["apex"]
    entries = [
        e for p in raw["global"]["model"]["api_models"].values() for e in p["models"]
    ]
    assert [e["id"] for e in entries if "apex.gaia_model" in e.get("uses", [])] == [
        model
    ]
    updated_id = model + "-next"
    config_path.write_text(
        config_path.read_text().replace(f'id = "{model}"', f'id = "{updated_id}"')
    )
    assert client.get("/api/settings").json()["apex"]["gaia_model"] == updated_id
    assert load_settings(config_path).apex.gaia_model == updated_id


def test_explicit_null_restores_gaia_following_skald(
    client: TestClient, config_path: Path
) -> None:
    """Omitted Gaia stays pinned; explicit null clears even a literal override."""
    before = load_settings(config_path)
    model = before.apex.model
    config_path.write_text(
        config_path.read_text().replace("[apex]", f'[apex]\ngaia_model = "{model}"')
    )
    response = client.patch("/api/settings", json={"apex_model_id": model})
    assert response.status_code == 200, response.text
    assert response.json()["apex"]["gaia_model"] == model

    response = client.patch("/api/settings", json={"gaia_model_id": None})
    assert response.status_code == 200, response.text
    assert response.json()["apex"].get("gaia_model") is None
    after = load_settings(config_path)
    assert after.apex.gaia_model is None
    assert after.apex.model == model
    assert after.wizard.default_model == before.wizard.default_model
    assert after.orrery.experiences.model == before.orrery.experiences.model
    raw = tomllib.loads(config_path.read_text())
    assert "gaia_model" not in raw["apex"]
    assert all(
        "apex.gaia_model" not in e.get("uses", [])
        for p in raw["global"]["model"]["api_models"].values()
        for e in p["models"]
    )
