"""A started wizard stream must report stale drafts without a broken body."""

from contextlib import contextmanager
from copy import deepcopy
import json
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.tools import DeferredToolRequests
import pytest

from nexus.api import new_story_cache, slot_state, wizard_agent, wizard_chat
from nexus.api.conversations import ConversationsClient
from nexus.api.new_story_cache import WizardCache
from nexus.api.new_story_schemas import WizardResponse
from nexus.api.slot_state import SlotState, WizardState


@pytest.mark.parametrize("changed_at", ["session", "artifact", "write_lock"])
def test_started_stream_ends_with_conflict_event(monkeypatch, changed_at) -> None:
    """Concurrent edits after a preview must yield recovery, never stale success."""
    storage = ConversationsClient("TEST")
    thread_id = storage.create_thread()
    storage.add_message(thread_id, "assistant", "Welcome")
    cache = WizardCache(thread_id=thread_id, choices=["Current choice"])
    state = SlotState(
        slot=4,
        is_empty=False,
        is_wizard_mode=True,
        narrative_state=None,
        model="TEST",
        wizard_state=WizardState(
            phase="setting",
            thread_id=thread_id,
            choices=cache.choices,
            has_concept=False,
            has_traits=False,
            has_wildcard=False,
        ),
    )

    class GeneratedTurn:
        def __init__(self, context):
            self.context = context

        async def stream_output(self):
            yield WizardResponse(
                message="Draft preview", choices=["Old choice", "Another old choice"]
            )

        async def get_output(self):
            cache.setting.genre = "fantasy"
            cache.setting.world_name = "Original draft"
            self.context.last_tool_result = {
                "phase_complete": True,
                "choices": ["Stale artifact choice"],
                **cache.confirmation_metadata(),
            }
            if changed_at == "session":
                cache.thread_id = "replacement-story"
            elif changed_at == "artifact":
                cache.setting.world_name = "Newer draft"
            return DeferredToolRequests()

    class Agent:
        async def run_stream(self, *args, deps, **kwargs):
            yield GeneratedTurn(deps)

    @contextmanager
    def connection(*args, **kwargs):
        # The canonical guard sees the edit after _artifact_response's first read.
        cache.setting.world_name = "Newer draft"
        yield Mock(cursor=lambda: Mock(__enter__=Mock(), __exit__=Mock()))

    monkeypatch.setattr(slot_state, "get_slot_state", lambda slot: state)
    monkeypatch.setattr(wizard_chat, "require_writable_slot", lambda slot: None)
    for module in (wizard_chat, wizard_agent):
        monkeypatch.setattr(module, "read_cache", lambda dbname: deepcopy(cache))
    monkeypatch.setattr(new_story_cache, "get_connection", connection)
    monkeypatch.setattr(
        new_story_cache, "read_cache_cursor", lambda *a, **kw: deepcopy(cache)
    )
    monkeypatch.setattr(wizard_chat, "ConversationsClient", lambda model: storage)
    monkeypatch.setattr(wizard_chat, "get_wizard_agent", lambda context: Agent())
    monkeypatch.setattr(wizard_chat, "get_wizard_streaming_enabled", lambda: True)
    monkeypatch.setattr(
        wizard_chat,
        "build_pydantic_ai_model_with_provider",
        lambda model: (None, "test"),
    )
    monkeypatch.setattr(wizard_chat, "record_pydantic_ai_result", lambda *a, **k: None)
    write_choices = Mock()
    monkeypatch.setattr(wizard_chat, "write_wizard_choices", write_choices)
    app = FastAPI()
    app.include_router(wizard_chat.router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/story/new/chat/stream", json={"slot": 4, "message": "A harbor city"}
    )

    # Once the preview starts, HTTP status is fixed; the last NDJSON record is
    # authoritative. The HTTP exception must not escape and truncate the stream.
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-ndjson"
    assert response.text.endswith("\n"), response.text
    records = [json.loads(line) for line in response.text.splitlines()]
    assert records[0] == {
        "type": "message",
        "message": "Draft preview",
        "choices": ["Old choice", "Another old choice"],
    }
    assert [record["type"] for record in records] == ["message", "error"]
    assert records[-1]["status_code"] == 409
    assert "changed" in records[-1]["detail"]
    assert cache.choices == ["Current choice"]
    write_choices.assert_not_called()
