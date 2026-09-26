"""Seat-derived requiredness on ``/api/secrets`` status rows (issue #821).

Each test writes a copy of the repository ``nexus.toml`` with explicit seat
assignments and a private ``[runtime].state_dir``, points
``NEXUS_RUNTIME_CONFIG`` at it, and drives the real router. Model IDs are read
from the copied roster, never written here, so roster upgrades do not touch
these tests. Keys come from environment variables under
``NEXUS_KEYRING_DISABLE=1`` or from the private in-memory store.
"""

from __future__ import annotations

import secrets
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import tomlkit
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api.secrets_endpoints import REQUIRED_SECRET_SEATS, router
from nexus.config.loader import RUNTIME_CONFIG_ENV, load_settings
from nexus.config.preferences import (
    load_preferences,
    preferences_path,
    save_preferences,
)
from nexus.util.secret_manager import InMemorySecretBackend, get_secret

REPOSITORY_CONFIG = Path(__file__).resolve().parents[2] / "nexus.toml"
KEYED_PROVIDERS = ("openai", "anthropic", "openrouter")


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def env_keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Read keys from environment variables only, starting with none set."""
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    for account in (*KEYED_PROVIDERS, "test", "local"):
        monkeypatch.delenv(f"{account.upper()}_API_KEY", raising=False)
    get_secret.cache_clear()
    yield
    get_secret.cache_clear()


def _registry(data: dict[str, Any]) -> dict[str, Any]:
    return data["global"]["model"]["api_models"]


def _reasoning_model(data: dict[str, Any], provider: str) -> str:
    """Return a roster ID on ``provider`` that accepts the seats' reasoning effort."""
    return next(
        entry["id"]
        for entry in _registry(data)[provider]["models"]
        if entry["reasoning_accounting"] != "none"
        and "reasoning_effort" not in entry.get("unsupported_params", [])
    )


def _assign(data: dict[str, Any], use: str, model_id: str | None) -> None:
    """Move one roster ``use`` to ``model_id``, or leave it unassigned."""
    for provider in _registry(data).values():
        for entry in provider["models"]:
            uses = entry.get("uses", [])
            if use in uses:
                uses.remove(use)
            if entry["id"] == model_id:
                entry["uses"] = [*uses, use]


def _write_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    assignments: dict[str, str | None],
) -> dict[str, Any]:
    """Write the repository config with ``assignments`` and make it active."""
    data = tomllib.loads(REPOSITORY_CONFIG.read_text())
    for use, model_id in assignments.items():
        _assign(data, use, model_id)
    data["ir_eval"]["judgment"]["model_policy"] = "fixed"
    data["runtime"]["state_dir"] = str(tmp_path / "state")
    path = tmp_path / "nexus.toml"
    path.write_text(tomlkit.dumps(data))
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(path))
    return data


def _split_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, str, str]:
    """Put each keyed provider behind different seats; the wizard runs keyless.

    Returns the Anthropic, OpenRouter, and OpenAI model IDs in use.
    """
    data = tomllib.loads(REPOSITORY_CONFIG.read_text())
    anthropic = _reasoning_model(data, "anthropic")
    openrouter = _reasoning_model(data, "openrouter")
    openai = _reasoning_model(data, "openai")
    local = _registry(data)["local"]["models"][0]["id"]
    assert "api_key_secret" not in _registry(data)["local"]
    assert _registry(data)["openrouter"]["api_key_secret"] == "openrouter"
    _write_config(
        tmp_path,
        monkeypatch,
        {
            "apex.model": anthropic,
            "apex.gaia_model": openrouter,
            "wizard.default_model": local,
            "summaries.model": None,
            "orrery.experiences.model": openai,
            "storyteller.correspondence.compaction_model": openai,
            "orrery.retrograde.maturation.model_ref": openai,
            "ir_eval.judgment.model": openai,
            "global.model.default_model": openai,
        },
    )
    return anthropic, openrouter, openai


def _rows(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/secrets/status")
    assert response.status_code == 200
    return {row["provider"]: row for row in response.json()}


def test_requiredness_counts_only_generation_seats() -> None:
    """Offline judgment and the display-only default never require a key.

    The UI labels exactly these seats; adding one here needs a label there.
    """
    assert REQUIRED_SECRET_SEATS == (
        "skald",
        "gaia",
        "wizard",
        "orrery.experiences.model",
        "storyteller.correspondence.compaction_model",
        "orrery.retrograde.maturation.model_ref",
        "summaries.model",
    )


def test_status_marks_each_account_the_resolved_seats_need(
    client: TestClient,
    env_keys: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anthropic, openrouter, openai = _split_config(tmp_path, monkeypatch)
    key = secrets.token_urlsafe(24)
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)

    response = client.get("/api/secrets/status")

    assert response.status_code == 200
    assert response.content.find(key.encode()) == -1
    rows = {row["provider"]: row for row in response.json()}
    # The keyless local wizard and the hidden keyless mock add no row and no
    # requirement; summaries follows the writer's model by default.
    assert set(rows) == set(KEYED_PROVIDERS)
    assert rows["anthropic"] == {
        "provider": "anthropic",
        "account": "anthropic",
        "present": True,
        "last4": key[-4:],
        "required": True,
        "required_by": [
            {"seat": "skald", "model": anthropic},
            {"seat": "summaries.model", "model": anthropic},
        ],
    }
    assert rows["openrouter"] == {
        "provider": "openrouter",
        "account": "openrouter",
        "present": False,
        "last4": None,
        "required": True,
        "required_by": [{"seat": "gaia", "model": openrouter}],
    }
    assert rows["openai"] == {
        "provider": "openai",
        "account": "openai",
        "present": False,
        "last4": None,
        "required": True,
        "required_by": [
            {"seat": "orrery.experiences.model", "model": openai},
            {"seat": "storyteller.correspondence.compaction_model", "model": openai},
            {"seat": "orrery.retrograde.maturation.model_ref", "model": openai},
        ],
    }


def test_offline_and_display_only_seats_leave_keys_optional(
    client: TestClient,
    env_keys: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = tomllib.loads(REPOSITORY_CONFIG.read_text())
    openai = _reasoning_model(data, "openai")
    generation = {
        use: openai
        for use in (
            "apex.model",
            "wizard.default_model",
            "orrery.experiences.model",
            "storyteller.correspondence.compaction_model",
            "orrery.retrograde.maturation.model_ref",
        )
    }
    _write_config(
        tmp_path,
        monkeypatch,
        {
            **generation,
            "apex.gaia_model": None,
            "summaries.model": None,
            "ir_eval.judgment.model": _reasoning_model(data, "anthropic"),
            "global.model.default_model": _reasoning_model(data, "openrouter"),
        },
    )
    key = secrets.token_urlsafe(24)
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)

    rows = _rows(client)

    assert [seat["seat"] for seat in rows["openai"]["required_by"]] == list(
        REQUIRED_SECRET_SEATS
    )
    assert {seat["model"] for seat in rows["openai"]["required_by"]} == {openai}
    assert (rows["openai"]["required"], rows["openai"]["present"]) == (True, False)
    assert rows["anthropic"] == {
        "provider": "anthropic",
        "account": "anthropic",
        "present": True,
        "last4": key[-4:],
        "required": False,
        "required_by": [],
    }
    assert rows["openrouter"]["required"] is False
    assert rows["openrouter"]["required_by"] == []
    assert rows["openrouter"]["present"] is False


def test_player_wizard_preference_moves_the_requirement(
    client: TestClient,
    env_keys: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _split_config(tmp_path, monkeypatch)
    before = _rows(client)
    assert [seat["seat"] for seat in before["anthropic"]["required_by"]] == [
        "skald",
        "summaries.model",
    ]

    preferred = _reasoning_model(
        tomllib.loads(REPOSITORY_CONFIG.read_text()), "openrouter"
    )
    save_preferences({"wizard_model": preferred}, load_settings())

    after = _rows(client)
    assert after["openrouter"]["required_by"] == [
        {"seat": "gaia", "model": preferred},
        {"seat": "wizard", "model": preferred},
    ]
    assert after["anthropic"]["required_by"] == before["anthropic"]["required_by"]


def test_put_returns_requiredness_with_the_stored_key(
    client: TestClient,
    in_memory_secret_store: InMemorySecretBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, openrouter, _ = _split_config(tmp_path, monkeypatch)
    for account in KEYED_PROVIDERS:
        monkeypatch.delenv(f"{account.upper()}_API_KEY", raising=False)
    assert _rows(client)["openrouter"]["present"] is False
    key = secrets.token_urlsafe(24)

    written = client.put("/api/secrets/openrouter", json={"key": key})

    assert written.status_code == 200
    assert written.json() == {
        "provider": "openrouter",
        "account": "openrouter",
        "present": True,
        "last4": key[-4:],
        "required": True,
        "required_by": [{"seat": "gaia", "model": openrouter}],
    }
    assert _rows(client)["openrouter"] == written.json()
    assert in_memory_secret_store.read("openrouter") == key
    assert written.content.find(key.encode()) == -1


def test_unresolvable_seat_fails_status_and_blocks_the_write(
    client: TestClient,
    in_memory_secret_store: InMemorySecretBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale player preference surfaces as an error, never as optional keys."""
    _split_config(tmp_path, monkeypatch)
    settings = load_settings()
    # A model the player chose, since removed from the roster.
    stale = {**load_preferences(settings).model_dump(), "wizard_model": "retired-821"}
    path = preferences_path(settings)
    path.parent.mkdir(parents=True)
    path.write_text(tomlkit.dumps(stale))

    with pytest.raises(ValueError, match="Cannot resolve wizard model"):
        client.get("/api/secrets/status")
    with pytest.raises(ValueError, match="Cannot resolve wizard model"):
        client.put("/api/secrets/openrouter", json={"key": secrets.token_urlsafe(24)})
    assert in_memory_secret_store.accounts() == frozenset()
