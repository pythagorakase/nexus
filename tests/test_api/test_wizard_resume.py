"""Resume must restore the persisted conversation without starting a new one."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.tools import DeferredToolRequests

from nexus.api import setup_endpoints, slot_state, wizard_agent, wizard_chat
from nexus.api.conversations import ConversationsClient
from nexus.api.narrative_schemas import ChatRequest
from nexus.api.new_story_cache import (
    CharacterData,
    SeedData,
    SettingData,
    SuggestedTrait,
    WizardCache,
    _row_to_cache,
)
from nexus.api.new_story_schemas import WizardResponse
from nexus.api.slot_state import SlotState, WizardState


@pytest.fixture
def resume_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Mount the production resume route with isolated storage boundaries."""
    monkeypatch.setattr(
        setup_endpoints, "get_slot_model", lambda *a, **k: "saved-model"
    )
    app = FastAPI()
    app.include_router(setup_endpoints.router)
    return TestClient(app)


def test_resume_restores_all_messages_choices_and_drafts(
    monkeypatch: pytest.MonkeyPatch, resume_client: TestClient
) -> None:
    """The resume contract adapts normalized cache data and keeps older turns."""
    cache = _row_to_cache(
        {
            "thread_id": "conv_saved",
            "target_slot": 4,
            "setting_genre": "folklore",
            "setting_world_name": "The Waking Wood",
            "choice_object": {
                "presented": ["A wanderer", "A keeper"],
                "selected": None,
            },
        }
    )
    monkeypatch.setattr(setup_endpoints, "resume_setup", lambda slot: cache)
    messages = [
        {"role": "assistant" if i % 2 == 0 else "user", "content": f"Turn {i}"}
        for i in range(27)
    ]
    storage = SimpleNamespace(
        list_messages=Mock(return_value=list(reversed(messages))),
        client=SimpleNamespace(close=Mock()),
    )
    factory = Mock(return_value=storage)
    monkeypatch.setattr(setup_endpoints, "ConversationsClient", factory)

    response = resume_client.get("/api/story/new/setup/resume?slot=4")

    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == messages
    assert data["choices"] == ["A wanderer", "A keeper"]
    assert data["thread_id"] == "conv_saved"
    assert data["current_phase"] == "character"
    assert data["setting_draft"]["world_name"] == "The Waking Wood"
    assert data["character_draft"] is None
    factory.assert_called_once_with(model="saved-model")
    storage.list_messages.assert_called_once_with("conv_saved", limit=0)
    storage.client.close.assert_called_once_with()


def test_resume_does_not_hide_history_failure(
    monkeypatch: pytest.MonkeyPatch, resume_client: TestClient
) -> None:
    """An unavailable conversation must not appear as a successful empty resume."""
    monkeypatch.setattr(
        setup_endpoints,
        "resume_setup",
        lambda slot: WizardCache(thread_id="conv_saved"),
    )
    storage = SimpleNamespace(
        list_messages=Mock(side_effect=RuntimeError("Conversation unavailable")),
        client=SimpleNamespace(close=Mock()),
    )
    monkeypatch.setattr(setup_endpoints, "ConversationsClient", lambda model: storage)

    response = resume_client.get("/api/story/new/setup/resume?slot=4")

    assert response.status_code == 500
    assert response.json()["detail"] == "Conversation unavailable"
    storage.client.close.assert_called_once_with()


@pytest.mark.parametrize("traits_confirmed", [False, True])
def test_resume_restores_partial_character(
    monkeypatch: pytest.MonkeyPatch,
    resume_client: TestClient,
    traits_confirmed: bool,
) -> None:
    """Concept and confirmed traits survive before the wildcard is completed."""
    cache = WizardCache(
        thread_id="conv_saved",
        setting=SettingData(genre="folklore"),
        character=CharacterData(
            name="Rowan",
            archetype="Keeper",
            traits_confirmed=traits_confirmed,
            suggested_traits=[SuggestedTrait("duty", "The gate must stay closed")],
        ),
    )
    monkeypatch.setattr(setup_endpoints, "resume_setup", lambda slot: cache)
    monkeypatch.setattr(
        setup_endpoints,
        "ConversationsClient",
        lambda model: SimpleNamespace(list_messages=lambda *a, **k: [], client=None),
    )
    response = resume_client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 200
    data = response.json()
    assert data["current_phase"] == "character"
    assert data["character_draft"] is None
    state = data["character_state"]
    assert state["concept"]["name"] == "Rowan"
    assert state["concept"]["suggested_traits"] == ["duty"]
    assert ("trait_selection" in state) is traits_confirmed
    assert "wildcard" not in state

    # Older clients can send other draft data without character_state.
    # Hydration must preserve that context and add the saved character.
    monkeypatch.setattr(wizard_chat, "read_cache", lambda dbname: cache)
    context = {"setting": {"world_name": "The Waking Wood"}}
    request = ChatRequest(
        slot=4, message="Continue", current_phase="character", context_data=context
    )
    assert wizard_chat._hydrate_character_context(request) == {
        **context,
        "character_state": state,
    }
    assert "character_state" not in context


def test_resume_restores_seed_awaiting_confirmation(
    monkeypatch: pytest.MonkeyPatch, resume_client: TestClient
) -> None:
    """A ready wizard includes the seed and complete set design for confirmation."""
    cache = WizardCache(
        thread_id="conv_saved",
        setting=SettingData(genre="folklore"),
        character=CharacterData(
            name="Rowan", traits_confirmed=True, wildcard_rationale="A hidden name"
        ),
        seed=SeedData(
            seed_type="mystery",
            title="The missing key",
            layer_name="Mortal world",
            zone_name="The wood",
            initial_location={"name": "The gate", "summary": "An ancient arch"},
        ),
        base_timestamp=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(setup_endpoints, "resume_setup", lambda slot: cache)
    monkeypatch.setattr(
        setup_endpoints,
        "ConversationsClient",
        lambda model: SimpleNamespace(list_messages=lambda *a, **k: [], client=None),
    )
    response = resume_client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 200
    data = response.json()
    assert data["current_phase"] == "ready"
    assert data["selected_seed"]["title"] == "The missing key"
    assert data["layer_draft"]["name"] == "Mortal world"
    assert data["zone_draft"]["name"] == "The wood"
    assert data["initial_location"]["summary"] == "An ancient arch"
    assert data["character_draft"] == data["character_state"]


@pytest.mark.parametrize(
    ("cache", "status"), [(None, 404), (WizardCache(thread_id=None), 500)]
)
def test_resume_rejects_missing_session(
    monkeypatch: pytest.MonkeyPatch,
    resume_client: TestClient,
    cache: WizardCache | None,
    status: int,
) -> None:
    """An absent or damaged session must never silently start a replacement."""
    monkeypatch.setattr(setup_endpoints, "resume_setup", lambda slot: cache)
    factory = Mock()
    monkeypatch.setattr(setup_endpoints, "ConversationsClient", factory)
    assert resume_client.get("/api/story/new/setup/resume?slot=4").status_code == status
    factory.assert_not_called()


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("reply", ["choices", "debug", "artifact"])
def test_resume_keeps_only_choices_from_the_latest_turn(
    monkeypatch: pytest.MonkeyPatch, streaming: bool, reply: str
) -> None:
    """Both chat transports must replace old choices, including with an empty set."""
    storage = ConversationsClient("TEST")
    thread_id = storage.create_thread()
    storage.add_message(thread_id, "assistant", "Welcome")
    cache = WizardCache(thread_id=thread_id, choices=["Old option"])
    state = SlotState(
        slot=4,
        is_empty=False,
        is_wizard_mode=True,
        wizard_state=WizardState(
            phase="setting",
            thread_id=thread_id,
            choices=cache.choices,
            has_concept=False,
            has_traits=False,
            has_wildcard=False,
        ),
        narrative_state=None,
        model="TEST",
    )
    expected_choices = ["New option", "Another option"] if reply == "choices" else []
    output = (
        DeferredToolRequests()
        if reply == "artifact"
        else (
            "Debug answer"
            if reply == "debug"
            else WizardResponse(message="Saved answer", choices=expected_choices)
        )
    )

    class GeneratedTurn:
        async def stream_output(self):
            yield output

        async def get_output(self):
            return output

    class Agent:
        def set_artifact(self, context: Any) -> None:
            if reply == "artifact":
                context.last_tool_result = {"phase_complete": True, "data": {}}

        async def run(self, *args: Any, **kwargs: Any) -> Any:
            self.set_artifact(kwargs["deps"])
            return SimpleNamespace(output=output)

        async def run_stream(self, *args: Any, **kwargs: Any):
            self.set_artifact(kwargs["deps"])
            yield GeneratedTurn()

    monkeypatch.setattr(slot_state, "get_slot_state", lambda slot: state)
    monkeypatch.setattr(wizard_agent, "read_cache", lambda dbname: cache)
    monkeypatch.setattr(wizard_chat, "require_writable_slot", lambda slot: None)
    monkeypatch.setattr(wizard_chat, "ConversationsClient", lambda model: storage)
    monkeypatch.setattr(wizard_chat, "get_wizard_agent", lambda context: Agent())
    monkeypatch.setattr(wizard_chat, "wizard_debug_agent", Agent())
    monkeypatch.setattr(wizard_chat, "get_wizard_streaming_enabled", lambda: True)
    monkeypatch.setattr(
        wizard_chat,
        "build_pydantic_ai_model_with_provider",
        lambda model: (None, "test"),
    )
    monkeypatch.setattr(wizard_chat, "record_pydantic_ai_result", lambda *a, **k: None)
    monkeypatch.setattr(
        wizard_chat,
        "write_wizard_choices",
        lambda choices, dbname: setattr(cache, "choices", choices),
    )
    monkeypatch.setattr(setup_endpoints, "resume_setup", lambda slot: cache)
    monkeypatch.setattr(setup_endpoints, "get_slot_model", lambda *a, **k: "TEST")
    monkeypatch.setattr(setup_endpoints, "ConversationsClient", lambda model: storage)
    app = FastAPI()
    app.include_router(wizard_chat.router)
    app.include_router(setup_endpoints.router)
    client = TestClient(app)

    endpoint = "/api/story/new/chat/stream" if streaming else "/api/story/new/chat"
    response = client.post(
        endpoint, json={"slot": 4, "message": "A forest", "dev": reply == "debug"}
    )
    assert response.status_code == 200, response.text
    resumed = client.get("/api/story/new/setup/resume?slot=4")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["choices"] == expected_choices
    assert {"role": "user", "content": "A forest"} in resumed.json()["messages"]
