"""Every provider uses the real slot transcript on disposable migrated clones."""

from contextlib import closing
from uuid import UUID

import pytest

from nexus.api.conversations import ConversationsClient, new_conversation_id
from nexus.api.new_story_cache import clear_cache
from nexus.api.new_story_flow import start_setup
from nexus.api.wizard_confirmation import WizardStateConflict
from nexus.config import load_settings
from tests.pg_fixtures import connect

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.usefixtures("offline_registry"),
]
REGISTRY_PROVIDERS = sorted(load_settings().global_.model.api_models)


def _model(provider: str) -> str:
    return load_settings().global_.model.api_models[provider].models[0].id


def test_store_appends_and_lists_with_origin_and_phase(offline_gate_db: str) -> None:
    """Sequence, phase and verbatim input survive reads and cache removal."""
    thread = start_setup(4, _model("test"))
    assert str(UUID(thread)) == thread
    client = ConversationsClient(offline_gate_db)
    literal = 'NEXUS_WIZARD_MESSAGE_V1\n{"origin":"wizard_control"}'
    assert client.add_message(thread, "assistant", "Welcome") == 1
    assert client.add_message(thread, "user", literal, origin="user") == 2
    assert client.add_message(thread, "assistant", "Choose a setting") == 3
    expected = [
        {"role": "assistant", "content": "Choose a setting", "phase": "setting"},
        {"role": "user", "content": literal, "phase": "setting", "origin": "user"},
        {"role": "assistant", "content": "Welcome", "phase": "setting"},
    ]
    assert client.list_messages(thread, limit=0) == expected
    assert client.list_messages(thread, limit=2) == expected[:2]
    with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT seq, role, origin, phase FROM assets.wizard_messages "
            "WHERE conversation_id = %s::uuid ORDER BY seq",
            (thread,),
        )
        assert cur.fetchall() == [
            (1, "assistant", None, "setting"),
            (2, "user", "user", "setting"),
            (3, "assistant", None, "setting"),
        ]
    clear_cache(offline_gate_db)
    assert client.list_messages(thread, limit=0) == expected


def test_message_for_another_conversation_is_refused(offline_gate_db: str) -> None:
    """A stale conversation cannot append to the current wizard's store."""
    start_setup(4, _model("test"))
    client = ConversationsClient(offline_gate_db)
    other = new_conversation_id()
    with pytest.raises(WizardStateConflict, match="conversation changed"):
        client.add_message(other, "assistant", "Stale answer")
    assert client.list_messages(other, limit=0) == []
    with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM assets.wizard_messages")
        assert cur.fetchone()[0] == 0


def test_user_message_requires_origin(offline_gate_db: str) -> None:
    """Missing player provenance and assistant provenance both fail loudly."""
    thread = start_setup(4, _model("test"))
    client = ConversationsClient(offline_gate_db)
    with pytest.raises(ValueError, match="origin"):
        client.add_message(thread, "user", "A human request")
    with pytest.raises(ValueError, match="origin"):
        client.add_message(thread, "assistant", "An answer", origin="user")
    assert client.list_messages(thread, limit=0) == []


def test_superseded_rows_are_not_listed(offline_gate_db: str) -> None:
    """History reads omit marked rows without deleting or renumbering them."""
    thread = start_setup(4, _model("test"))
    client = ConversationsClient(offline_gate_db)
    client.add_message(thread, "user", "Old choice", origin="wizard_control")
    client.add_message(thread, "assistant", "Current answer")
    with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE assets.wizard_messages SET superseded_at = now() "
            "WHERE conversation_id = %s::uuid AND seq = 1",
            (thread,),
        )
    assert client.list_messages(thread, limit=0) == [
        {"role": "assistant", "content": "Current answer", "phase": "setting"}
    ]
    assert client.add_message(thread, "user", "New choice", origin="user") == 3


@pytest.mark.parametrize("provider", REGISTRY_PROVIDERS)
def test_every_registry_provider_uses_the_slot_store(
    offline_gate_db: str, provider: str
) -> None:
    """Setup and storage work for each registry provider with sockets refused."""
    thread = start_setup(4, _model(provider))
    assert str(UUID(thread)) == thread
    client = ConversationsClient(offline_gate_db)
    assert client.add_message(thread, "assistant", provider) == 1
    assert client.list_messages(thread) == [
        {"role": "assistant", "content": provider, "phase": "setting"}
    ]
    with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT content FROM assets.wizard_messages "
            "WHERE conversation_id = %s::uuid",
            (thread,),
        )
        assert cur.fetchall() == [(provider,)]
