"""Shared API-test boundaries: disposable slot databases and offline registries."""

from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import asdict
import json
import socket

import pytest

from nexus.api.new_story_cache import (
    WizardCache,
    read_cache,
    write_cache,
    write_suggested_traits,
)
from nexus.api.new_story_flow import start_setup
from nexus.config import load_settings
from nexus.util.secret_manager import get_secret
from tests.model_registry_helpers import registry_model
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
)


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


@pytest.fixture
def offline_registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove credentials and refuse sockets; every transcript uses the slot DB."""
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
    yield
    get_secret.cache_clear()


@pytest.fixture
def seed_wizard_cache(
    offline_gate_db: str, offline_registry: None
) -> Callable[[WizardCache], WizardCache]:
    """Persist a checkpoint through real writers on the routed slot-4 clone.

    The explicit confirmation fields represent the already accepted checkpoint;
    neither cache reads nor transcript writes are replaced by this seed helper.
    """

    def seed(cache: WizardCache) -> WizardCache:
        start_setup(4, registry_model("test"))
        write_cache(
            dbname=offline_gate_db,
            setting_draft=asdict(cache.setting),
            character_draft=cache.get_character_state_dict(),
            selected_seed=asdict(cache.seed),
            layer_draft=cache.get_layer_dict(),
            zone_draft=cache.get_zone_dict(),
            initial_location=cache.get_initial_location(),
            base_timestamp=(
                cache.base_timestamp.isoformat() if cache.base_timestamp else None
            ),
        )
        if (
            not cache.character.traits_confirmed
            or len(cache.character.suggested_traits) != 3
        ):
            write_suggested_traits(
                offline_gate_db,
                [
                    {"trait": item.trait, "rationale": item.rationale}
                    for item in cache.character.suggested_traits
                ],
            )
        choice_object = (
            json.dumps({"presented": cache.choices, "selected": None})
            if cache.choices_recorded
            else None
        )
        with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE assets.new_story_creator SET setting_confirmed = %s, "
                "character_confirmed = %s, character_revision_pending = %s, "
                "traits_confirmed = %s, trait_compile_result = %s::jsonb, "
                "choice_object = %s::jsonb, weird_level = %s WHERE id = TRUE",
                (
                    cache.setting_confirmed,
                    cache.character_confirmed,
                    cache.character_revision_pending,
                    cache.character.traits_confirmed,
                    json.dumps(cache.character.trait_compile_result),
                    choice_object,
                    cache.weird_level,
                ),
            )
        saved = read_cache(offline_gate_db)
        assert saved is not None and saved.thread_id is not None
        return saved

    return seed
