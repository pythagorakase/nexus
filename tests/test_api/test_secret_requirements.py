"""Seat-derived requiredness on ``/api/secrets`` status rows (issue #821).

Each test writes a copy of the repository ``nexus.toml`` with explicit seat
assignments and a private ``[runtime].state_dir``, points
``NEXUS_RUNTIME_CONFIG`` at it, and drives the real router. Model IDs are read
from the copied roster, never written here, so roster upgrades do not touch
these tests. Keys come from environment variables under
``NEXUS_KEYRING_DISABLE=1`` or from the private in-memory store. Slot-aware
tests pin a disposable template clone through the real slot settings route.
"""

from __future__ import annotations

import re
import secrets
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import tomlkit
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api import secrets_endpoints, slot_endpoints
from nexus.api.secrets_endpoints import REQUIRED_SECRET_SEATS, router
from nexus.config.loader import RUNTIME_CONFIG_ENV, load_settings
from nexus.config.preferences import (
    load_preferences,
    preferences_path,
    save_preferences,
)
from nexus.util.secret_manager import InMemorySecretBackend, get_secret
from tests.pg_fixtures import connect

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_CONFIG = REPOSITORY_ROOT / "nexus.toml"
SECRET_TYPES = REPOSITORY_ROOT / "ui" / "client" / "src" / "types" / "secrets.ts"
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
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the repository config with ``assignments`` and make it active.

    ``overrides`` sets dotted TOML keys, and a ``None`` value removes the key.
    """
    data = tomllib.loads(REPOSITORY_CONFIG.read_text())
    for use, model_id in assignments.items():
        _assign(data, use, model_id)
    for dotted, value in (overrides or {}).items():
        *parents, key = dotted.split(".")
        table = data
        for part in parents:
            table = table[part]
        if value is None:
            del table[key]
        else:
            table[key] = value
    data["ir_eval"]["judgment"]["model_policy"] = "fixed"
    data["runtime"]["state_dir"] = str(tmp_path / "state")
    path = tmp_path / "nexus.toml"
    path.write_text(tomlkit.dumps(data))
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(path))
    return data


def _split_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, Any] | None = None,
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
        overrides,
    )
    return anthropic, openrouter, openai


def _rows(client: TestClient, query: str = "") -> dict[str, dict[str, Any]]:
    response = client.get(f"/api/secrets/status{query}")
    assert response.status_code == 200, response.text
    return {row["provider"]: row for row in response.json()}


def _seats(row: dict[str, Any]) -> list[str]:
    return [item["seat"] for item in row["required_by"]]


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


def test_ui_seat_union_matches_the_required_seats() -> None:
    """The UI throws on a seat it cannot label; keep its union in lockstep."""
    union = re.search(
        r"export type SecretSeat =(?P<body>[^;]+);", SECRET_TYPES.read_text()
    )
    assert union is not None
    assert tuple(re.findall(r'"([^"]+)"', union["body"])) == REQUIRED_SECRET_SEATS


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


def test_switched_off_subsystems_need_no_key(
    client: TestClient,
    env_keys: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled experience and maturation queues never call their seat's model."""
    _, _, openai = _split_config(
        tmp_path,
        monkeypatch,
        {
            "orrery.experiences.enabled": False,
            "orrery.retrograde.maturation.enabled": False,
        },
    )
    assert _rows(client)["openai"]["required_by"] == [
        {"seat": "storyteller.correspondence.compaction_model", "model": openai}
    ]

    # Without [orrery] no Orrery seat exists to need a key.
    _write_config(
        tmp_path,
        monkeypatch,
        {
            "apex.model": openai,
            "apex.gaia_model": None,
            "wizard.default_model": openai,
            "summaries.model": None,
            "storyteller.correspondence.compaction_model": openai,
            "orrery.experiences.model": None,
            "orrery.retrograde.maturation.model_ref": None,
        },
        {"orrery": None},
    )
    assert _seats(_rows(client)["openai"]) == [
        "skald",
        "gaia",
        "wizard",
        "storyteller.correspondence.compaction_model",
        "summaries.model",
    ]


def test_unresolvable_seat_fails_status_and_blocks_the_write(
    client: TestClient,
    in_memory_secret_store: InMemorySecretBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale player preference fails loudly, naming its seat and its repair."""
    _split_config(tmp_path, monkeypatch)
    settings = load_settings()
    # A model the player chose, since removed from the roster.
    stale = {**load_preferences(settings).model_dump(), "wizard_model": "retired-821"}
    path = preferences_path(settings)
    path.parent.mkdir(parents=True)
    path.write_text(tomlkit.dumps(stale))

    status = client.get("/api/secrets/status")
    written = client.put(
        "/api/secrets/openrouter", json={"key": secrets.token_urlsafe(24)}
    )

    for response in (status, written):
        assert response.status_code == 500
        assert response.json() == {
            "detail": (
                "Cannot derive required API keys from the wizard seat: Cannot "
                "resolve wizard model 'retired-821' (player_preference): absent "
                "from the registry. Replace or remove wizard_model in "
                "preferences.toml."
            )
        }
    assert in_memory_secret_store.accounts() == frozenset()


@pytest.fixture
def slot_client(offline_gate_db: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Serve the secrets and slot settings routes against the slot 4 clone."""
    for module in (secrets_endpoints, slot_endpoints):
        monkeypatch.setattr(module, "slot_dbname", lambda slot: offline_gate_db)
    app = FastAPI()
    app.include_router(router)
    app.include_router(slot_endpoints.router)
    return TestClient(app)


@pytest.mark.requires_postgres
def test_slot_skald_pin_moves_the_requirement(
    slot_client: TestClient,
    in_memory_secret_store: InMemorySecretBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Skald picked in the Model card moves the keys that slot's turns read."""
    data = tomllib.loads(REPOSITORY_CONFIG.read_text())
    openai = _reasoning_model(data, "openai")
    anthropic = _reasoning_model(data, "anthropic")
    _write_config(
        tmp_path,
        monkeypatch,
        {
            "apex.model": openai,
            "apex.gaia_model": None,
            "wizard.default_model": openai,
            "summaries.model": None,
            "orrery.experiences.model": openai,
            "storyteller.correspondence.compaction_model": openai,
            "orrery.retrograde.maturation.model_ref": openai,
        },
        {
            "orrery.experiences.model_policy": "follow_story",
            "storyteller.correspondence.compaction_model_policy": "follow_story",
            "orrery.retrograde.maturation.model_ref_policy": "fixed",
            "summaries.model_policy": "follow_story",
        },
    )
    for account in KEYED_PROVIDERS:
        monkeypatch.delenv(f"{account.upper()}_API_KEY", raising=False)
    cleared = {"skald_model": None, "gaia_model": None, "apex_context_window": None}
    assert slot_client.patch("/api/slot/4/settings", json=cleared).status_code == 200
    assert _rows(slot_client, "?slot=4")["anthropic"]["required"] is False

    pinned = slot_client.patch("/api/slot/4/settings", json={"skald_model": anthropic})
    assert pinned.status_code == 200, pinned.text

    rows = _rows(slot_client, "?slot=4")
    needed = [
        {"seat": seat, "model": anthropic}
        for seat in (
            "skald",
            "gaia",
            "wizard",
            "orrery.experiences.model",
            "storyteller.correspondence.compaction_model",
            "summaries.model",
        )
    ]
    assert rows["anthropic"] == {
        "provider": "anthropic",
        "account": "anthropic",
        "present": False,
        "last4": None,
        "required": True,
        "required_by": needed,
    }
    assert rows["openai"]["required_by"] == [
        {"seat": "orrery.retrograde.maturation.model_ref", "model": openai}
    ]
    # Without a slot the repository defaults still put every seat on OpenAI.
    assert _rows(slot_client)["anthropic"]["required"] is False

    key = secrets.token_urlsafe(24)
    written = slot_client.put("/api/secrets/anthropic?slot=4", json={"key": key})
    assert written.status_code == 200, written.text
    assert written.json() == {**rows["anthropic"], "present": True, "last4": key[-4:]}
    assert in_memory_secret_store.read("anthropic") == key


@pytest.mark.requires_postgres
def test_retired_slot_pin_names_the_story_pin_repair(
    slot_client: TestClient,
    env_keys: None,
    offline_gate_db: str,
) -> None:
    """A pin the roster no longer has fails loudly with the pin's own repair."""
    with connect(offline_gate_db) as conn, conn.cursor() as cur:
        cur.execute("UPDATE global_variables SET model = 'retired-821' WHERE id")

    response = slot_client.get("/api/secrets/status?slot=4")

    assert response.status_code == 500
    assert response.json() == {
        "detail": (
            "Cannot derive required API keys from the skald seat: Cannot resolve "
            "skald model 'retired-821' (story_pin): absent from the registry. "
            "Clear or replace the story pin with nexus model --slot N --clear."
        )
    }
