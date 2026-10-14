"""Resume must restore the persisted conversation without starting a new one."""

from contextlib import closing
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Literal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.tools import DeferredToolRequests

from nexus.api import new_story_cache, setup_endpoints, wizard_chat
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
from nexus.api.wizard_transcript import MessageOrigin
from nexus.api.config_utils import get_wizard_history_limit
from tests.pg_fixtures import connect


pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def resume_client() -> TestClient:
    """Mount the production resume route on the routed disposable slot."""
    app = FastAPI()
    app.include_router(setup_endpoints.router)
    return TestClient(app)


def test_resume_returns_full_transcript(
    offline_gate_db: str, seed_wizard_cache, resume_client: TestClient
) -> None:
    """The UI restores every turn and projects controls out without a limit."""
    cache = seed_wizard_cache(
        _row_to_cache(
            {
                "setting_genre": "fantasy",
                "setting_confirmed": True,
                "setting_world_name": "The Waking Wood",
                "choice_object": {
                    "presented": ["A wanderer", "A keeper"],
                    "selected": None,
                },
            }
        )
    )
    storage = ConversationsClient(offline_gate_db)
    expected = []
    for i in range(get_wizard_history_limit() + 3):
        role: Literal["user", "assistant"] = "assistant" if i % 2 == 0 else "user"
        origin: MessageOrigin = "wizard_control" if i == 1 else "user"
        message = {"role": role, "content": f"Turn {i}"}
        storage.add_message(
            cache.thread_id,
            role,
            message["content"],
            origin=origin if role == "user" else None,
        )
        if i != 1:
            expected.append(message)
    response = resume_client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["messages"] == expected
    assert data["choices"] == ["A wanderer", "A keeper"]
    assert data["thread_id"] == cache.thread_id
    assert data["current_phase"] == "character"
    assert data["setting_draft"]["world_name"] == "The Waking Wood"
    assert data["character_draft"] is None
    assert (
        len(storage.list_messages(cache.thread_id, limit=0))
        == get_wizard_history_limit() + 3
    )


def test_resume_does_not_hide_history_failure(
    offline_gate_db: str, seed_wizard_cache, resume_client: TestClient
) -> None:
    """An unavailable real transcript table cannot become an empty success."""
    seed_wizard_cache(WizardCache())
    with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE assets.wizard_messages RENAME TO wizard_messages_unavailable"
        )
    response = resume_client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 500
    assert (
        'relation "assets.wizard_messages" does not exist' in response.json()["detail"]
    )


@pytest.mark.parametrize("traits_confirmed", [False, True])
def test_resume_restores_partial_character(
    seed_wizard_cache,
    resume_client: TestClient,
    traits_confirmed: bool,
) -> None:
    """Concept and confirmed traits survive before the wildcard is completed."""
    cache = WizardCache(
        thread_id="conv_saved",
        setting_confirmed=True,
        setting=SettingData(genre="fantasy"),
        character=CharacterData(
            name="Rowan",
            archetype="Keeper",
            traits_confirmed=traits_confirmed,
            suggested_traits=[SuggestedTrait("allies", "The gate must stay closed")],
        ),
    )
    cache = seed_wizard_cache(cache)
    response = resume_client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 200
    data = response.json()
    assert data["current_phase"] == "character"
    assert data["character_draft"] is None
    state = data["character_state"]
    assert state["concept"]["name"] == "Rowan"
    assert state["concept"]["suggested_traits"] == ["allies"]
    assert ("trait_selection" in state) is traits_confirmed
    assert "wildcard" not in state

    # Older clients can send other draft data without character_state.
    # Hydration must preserve that context and add the saved character.
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
    seed_wizard_cache, resume_client: TestClient
) -> None:
    """A ready wizard includes the seed and complete set design for confirmation."""
    cache = WizardCache(
        thread_id="conv_saved",
        character_confirmed=True,
        setting_confirmed=True,
        setting=SettingData(genre="fantasy"),
        character=CharacterData(
            name="Rowan",
            traits_confirmed=True,
            wildcard_name="The hidden name",
            wildcard_rationale="A hidden name",
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
    cache = seed_wizard_cache(cache)
    response = resume_client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 200
    data = response.json()
    assert data["current_phase"] == "ready"
    assert data["selected_seed"]["title"] == "The missing key"
    assert data["layer_draft"]["name"] == "Mortal world"
    assert data["zone_draft"]["name"] == "The wood"
    assert data["initial_location"]["summary"] == "An ancient arch"
    assert data["character_draft"] == data["character_state"]


@pytest.mark.parametrize(("missing", "status"), [("cache", 404), ("thread", 500)])
def test_resume_rejects_missing_session(
    offline_gate_db: str,
    seed_wizard_cache,
    resume_client: TestClient,
    missing: str,
    status: int,
) -> None:
    """An absent or damaged real session must not start a replacement."""
    seed_wizard_cache(WizardCache())
    if missing == "cache":
        new_story_cache.clear_cache(offline_gate_db)
    else:
        with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE assets.new_story_creator SET thread_id = NULL WHERE id = TRUE"
            )
    assert resume_client.get("/api/story/new/setup/resume?slot=4").status_code == status
    with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM assets.wizard_messages")
        assert cur.fetchone()[0] == 0


@pytest.mark.parametrize("reply", ["choices", "debug", "artifact"])
@pytest.mark.parametrize("message_origin", ["user", "wizard_control"])
def test_resume_keeps_only_choices_from_the_latest_turn(
    monkeypatch: pytest.MonkeyPatch,
    offline_gate_db: str,
    seed_wizard_cache,
    reply: str,
    message_origin: str,
) -> None:
    """A chat turn must replace old choices, including with an empty set."""
    cache = seed_wizard_cache(
        WizardCache(choices=["Old option"], choices_recorded=True)
    )
    storage = ConversationsClient(offline_gate_db)
    thread_id = cache.thread_id
    storage.add_message(thread_id, "assistant", "Welcome")
    # An old control and a new player message can have identical text. Only the
    # explicitly attributed player message should survive the resume projection.
    message = (
        "[SYSTEM] Phase setting complete. Proceeding to character. "
        "Please introduce the next phase."
    )
    storage.add_message(thread_id, "user", message, origin="wizard_control")
    seen_history = []
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

    class Agent:
        def set_artifact(self, context: Any) -> None:
            if reply == "artifact":
                context.last_tool_result = {
                    "phase_complete": True,
                    "data": {},
                    **cache.confirmation_metadata(),
                }

        async def run(self, *args: Any, **kwargs: Any) -> Any:
            seen_history.extend(kwargs["message_history"])
            self.set_artifact(kwargs["deps"])
            return SimpleNamespace(output=output)

    monkeypatch.setattr(wizard_chat, "get_wizard_agent", lambda context: Agent())
    monkeypatch.setattr(wizard_chat, "wizard_debug_agent", Agent())
    monkeypatch.setattr(
        wizard_chat,
        "build_pydantic_ai_model_with_provider",
        lambda model: (None, "test"),
    )
    monkeypatch.setattr(wizard_chat, "record_pydantic_ai_result", lambda *a, **k: None)
    app = FastAPI()
    app.include_router(wizard_chat.router)
    app.include_router(setup_endpoints.router)
    client = TestClient(app)

    payload = {"slot": 4, "message": message, "dev": reply == "debug"}
    if message_origin == "wizard_control":
        payload["message_origin"] = message_origin
    response = client.post("/api/story/new/chat", json=payload)
    assert response.status_code == 200, response.text
    resumed = client.get("/api/story/new/setup/resume?slot=4")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["choices"] == expected_choices
    assert resumed.json()["messages"].count({"role": "user", "content": message}) == (
        1 if message_origin == "user" else 0
    )
    # Controls retain the same user role and original text for inference; the
    # stored provenance must not become another model prompt or raise authority.
    assert seen_history[-1].parts[0].part_kind == "user-prompt"
    assert seen_history[-1].parts[0].content == message
