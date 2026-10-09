"""Shared API-test boundaries: disposable slot databases and offline registries."""

from collections.abc import Iterator
from pathlib import Path
import socket
from typing import Any

import pytest
import tomlkit

from nexus.api import conversations
from nexus.config import load_settings
from nexus.runtime.contract import RUNTIME_CONFIG_ENV
from nexus.util.secret_manager import get_secret
from tests.pg_fixtures import disposable_slot_database, route_slot_to_disposable


@pytest.fixture
def offline_gate_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Route slot 4 to a real template clone, including the unchanged lock guard.

    The template supplies global_variables, assets.new_story_creator,
    assets.traits, narrative/incubator tables, generation leases, and Orrery
    queues. ``route_slot_to_disposable`` routes slot 4 to the clone in every
    loaded module and refuses every other slot; only this clone is written,
    and the helper closes pools and drops it.
    """
    with disposable_slot_database("qa640_offline_gate") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
        yield dbname


@pytest.fixture(autouse=True)
def empty_memory_conversation_store() -> Iterator[None]:
    """Start and leave every test with no threads in the in-memory TEST store."""
    conversations._MEMORY_STORE.threads.clear()
    yield
    conversations._MEMORY_STORE.threads.clear()


@pytest.fixture
def offline_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Remove credentials, refuse sockets, and configure a private state directory.

    Yields:
        The directory that receives file-backed wizard threads.
    """
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    for provider, config in load_settings().global_.model.api_models.items():
        accounts = {provider}
        if config.api_key_secret is not None:
            accounts.add(config.api_key_secret)
        for account in accounts:
            monkeypatch.delenv(f"{account.upper()}_API_KEY", raising=False)
    get_secret.cache_clear()

    def refuse_network(*args: object, **kwargs: object) -> None:
        pytest.fail("Wizard conversation storage opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse_network)
    monkeypatch.setattr(socket, "create_connection", refuse_network)
    document: Any = tomlkit.parse(
        (Path(__file__).resolve().parents[2] / "nexus.toml").read_text()
    )
    document["runtime"]["state_dir"] = str(tmp_path / "state")
    runtime_config = tmp_path / "nexus.toml"
    runtime_config.write_text(tomlkit.dumps(document))
    monkeypatch.setenv(RUNTIME_CONFIG_ENV, str(runtime_config))
    thread_dir = tmp_path / "state" / conversations.WIZARD_THREADS_DIRNAME
    yield thread_dir
    get_secret.cache_clear()
