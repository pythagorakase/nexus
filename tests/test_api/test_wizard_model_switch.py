"""A switch repoints the slot model on one slot-database conversation."""

from contextlib import closing
from typing import Optional

import pytest

from nexus.api.conversations import ConversationsClient
from nexus.api.new_story_cache import (
    init_cache,
    read_cache,
    repoint_wizard_conversation,
)
from nexus.api.new_story_flow import start_setup, switch_wizard_model
from nexus.api.save_slots import get_slot_model, set_slot_model
from nexus.api.wizard_confirmation import WizardStateConflict
from nexus.config import load_settings
from tests.model_registry_helpers import registry_model
from tests.pg_fixtures import connect

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.usefixtures("offline_registry"),
]


@pytest.mark.parametrize(
    ("source_provider", "target_provider"),
    [("openai", "anthropic"), ("anthropic", "test"), ("test", "openai")],
)
def test_model_switch_keeps_one_conversation(
    offline_gate_db: str, source_provider: str, target_provider: str
) -> None:
    """Changing provider keeps the UUID and every persisted message identical."""
    registry = load_settings().global_.model.api_models
    source = registry[source_provider].models[0].id
    target = registry[target_provider].models[0].id
    thread = start_setup(4, source)
    client = ConversationsClient(offline_gate_db)
    client.add_message(thread, "assistant", "Welcome")
    client.add_message(thread, "user", "A harbor city", origin="user")

    def rows() -> list[tuple]:
        with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM assets.wizard_messages ORDER BY seq")
            return list(cur.fetchall())

    before = rows()
    assert (
        switch_wizard_model(4, thread_id=thread, slot_model=source, model=target)
        == thread
    )
    assert get_slot_model(4, dbname=offline_gate_db) == target
    cache = read_cache(offline_gate_db)
    assert cache is not None and cache.thread_id == thread
    assert rows() == before
    with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(DISTINCT conversation_id) FROM assets.wizard_messages"
        )
        assert cur.fetchone()[0] == 1


@pytest.mark.requires_postgres
def test_repoint_commits_model_and_thread_together(offline_gate_db: str) -> None:
    """The SQL switch writes both slot rows or neither, fenced on what was read."""
    init_cache(offline_gate_db, "thread-before", 4)
    set_slot_model(4, "TEST", offline_gate_db)
    target = registry_model("local")

    def persisted() -> tuple[Optional[str], Optional[str]]:
        cache = read_cache(offline_gate_db)
        assert cache is not None
        return cache.thread_id, get_slot_model(4, dbname=offline_gate_db)

    # The thread row updates first; the stale model fence must roll it back.
    with pytest.raises(WizardStateConflict, match="slot model changed"):
        repoint_wizard_conversation(
            offline_gate_db,
            expected_thread_id="thread-before",
            thread_id="thread-after",
            expected_model=target,
            model="TEST",
        )
    assert persisted() == ("thread-before", "TEST")
    with pytest.raises(WizardStateConflict, match="conversation changed"):
        repoint_wizard_conversation(
            offline_gate_db,
            expected_thread_id="thread-elsewhere",
            thread_id="thread-after",
            expected_model="TEST",
            model=target,
        )
    assert persisted() == ("thread-before", "TEST")
    repoint_wizard_conversation(
        offline_gate_db,
        expected_thread_id="thread-before",
        thread_id="thread-after",
        expected_model="TEST",
        model=target,
    )
    assert persisted() == ("thread-after", target)
