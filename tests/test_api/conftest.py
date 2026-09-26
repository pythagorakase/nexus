"""Shared API-test boundaries: disposable slot databases and offline registries."""

from collections.abc import Iterator
from pathlib import Path
import socket

import pytest

from nexus.api import conversations
from nexus.api import new_story_flow, setup_endpoints, slot_mutations, slot_state
from nexus.api import slot_utils
from nexus.config import load_settings
from nexus.util.secret_manager import get_secret
from tests.pg_fixtures import disposable_slot_database


@pytest.fixture
def offline_gate_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Route slot 4 to a real template clone, including the unchanged lock guard.

    The template supplies global_variables, assets.new_story_creator,
    assets.traits, narrative/incubator tables, generation leases, and Orrery
    queues. Only this clone is written; the helper closes pools and drops it.
    """
    with disposable_slot_database("qa640_offline_gate") as dbname:

        def fixture_slot_dbname(slot: int) -> str:
            assert slot == 4, f"Unexpected slot access: {slot}"
            return dbname

        monkeypatch.setattr(
            slot_utils, "VALID_DBNAMES", slot_utils.VALID_DBNAMES | {dbname}
        )
        for module in (
            slot_utils,
            slot_mutations,
            slot_state,
            new_story_flow,
            setup_endpoints,
        ):
            monkeypatch.setattr(module, "slot_dbname", fixture_slot_dbname)
        yield dbname


@pytest.fixture(autouse=True)
def empty_memory_conversation_store() -> Iterator[None]:
    """Start and leave every test with no threads in the in-memory TEST store."""
    conversations._MEMORY_STORE.threads.clear()
    yield
    conversations._MEMORY_STORE.threads.clear()


@pytest.fixture
def offline_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Remove every registry credential, refuse sockets, and isolate thread files.

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
    thread_dir = tmp_path / "wizard_threads"
    monkeypatch.setattr(conversations, "_FILE_STORE_DIR", thread_dir)
    yield thread_dir
    get_secret.cache_clear()
