"""Draft completion, revision and player confirmation are distinct transitions."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import CallDeferred, ModelRetry
import pytest

from nexus.api import setup_endpoints, wizard_agent, wizard_chat, slot_state
from nexus.api.conversations import ConversationsClient
from nexus.api.new_story_cache import (
    WizardCache,
    CharacterData,
    SettingData,
    SuggestedTrait,
    _row_to_cache,
)
from nexus.api.new_story_schemas import WizardResponse, CharacterCreationState
from nexus.api.slot_state import SlotState, WizardState, _get_wizard_state_from_row
from tests.test_wizard_agent import sample_concept_submission, DummyRunContext


def character_cache(*, complete: bool = True) -> WizardCache:
    """Build a realistic saved character with independently chosen mechanics."""
    return WizardCache(
        thread_id="saved-thread",
        setting_confirmed=True,
        setting=SettingData(genre="fantasy"),
        character=CharacterData(
            name="Mara",
            archetype="Veteran harbor engineer",
            background="Age 38. Repairs the harbor machinery and protects its workers.",
            appearance="Gray coat, dark curls, and a grease-stained collar.",
            traits_confirmed=complete,
            selected_trait_count=3,
            suggested_traits=[
                SuggestedTrait(
                    "allies", "The workers owe her a favor.", "forbidden", []
                ),
                SuggestedTrait("contacts", "Dockworkers share quiet warnings."),
                SuggestedTrait("patron", "The old shipyard pays her bills."),
            ],
            wildcard_name="The bell" if complete else None,
            wildcard_rationale=(
                "She hears the bell before anyone else in the harbor."
                if complete
                else None
            ),
            trait_compile_result={"old": "derived from age 38"},
        ),
    )


def test_complete_drafts_wait_for_player_confirmation() -> None:
    cache = character_cache()
    assert cache.current_phase() == "character"
    assert cache.pending_confirmation() == "character"
    cache.character_confirmed = True
    assert cache.current_phase() == "seed"
    cache.setting_confirmed = False
    assert cache.current_phase() == "setting"
    assert cache.pending_confirmation() == "setting"


def test_canonical_token_changes_for_prose_and_trait_constraints_only() -> None:
    cache = character_cache()
    token = cache.artifact_token()
    cache.choices = ["A different conversation option"]
    assert cache.artifact_token() == token
    cache.character.background = cache.character.background.replace("38", "54")
    assert cache.artifact_token() != token
    token = cache.artifact_token()
    cache.character.suggested_traits[0].cold_start_relationships = "allowed"
    assert cache.artifact_token() != token


def test_slot_projection_waits_for_both_phase_confirmations() -> None:
    row = dict(
        thread_id="saved",
        setting_genre="fantasy",
        character_name="Mara",
        traits_confirmed=True,
        wildcard_rationale="Bell",
        setting_confirmed=False,
        character_confirmed=False,
    )
    assert _get_wizard_state_from_row(row).phase == "setting"
    row["setting_confirmed"] = True
    assert _get_wizard_state_from_row(row).phase == "character"
    row["character_confirmed"] = True
    assert _get_wizard_state_from_row(row).phase == "seed"


def test_resume_restores_complete_character_card_without_inference(monkeypatch) -> None:
    cache = character_cache()
    monkeypatch.setattr(setup_endpoints, "resume_setup", lambda slot: cache)
    monkeypatch.setattr(setup_endpoints, "get_slot_model", lambda *a, **kw: "TEST")
    monkeypatch.setattr(
        setup_endpoints,
        "ConversationsClient",
        lambda *a, **kw: SimpleNamespace(
            list_messages=lambda *a, **kw: [], client=None
        ),
    )
    app = FastAPI()
    app.include_router(setup_endpoints.router)
    data = TestClient(app).get("/api/story/new/setup/resume?slot=4").json()
    assert data["current_phase"] == data["pending_confirmation"] == "character"
    assert data["artifact_token"] == cache.artifact_token()
    assert data["character_sheet"]["name"] == "Mara"
    assert data["character_state"]["concept"]["background"].startswith("Age 38")
    cache.character_revision_pending = True
    revised = TestClient(app).get("/api/story/new/setup/resume?slot=4").json()
    assert revised["current_phase"] == "character"
    assert revised["pending_confirmation"] is None
    assert revised["character_revision_pending"] is True
    assert revised["character_state"] == data["character_state"]


@pytest.mark.asyncio
@pytest.mark.parametrize("complete", [False, True])
async def test_revision_requires_actual_replacement_and_preserves_mechanics(
    monkeypatch, complete
) -> None:
    cache = character_cache(complete=complete)
    cache.character_revision_pending = True
    replacement = deepcopy(cache)
    replacement.character.background = (
        "Age 54. Repairs the harbor machinery and protects its workers."
    )
    replacement.character_revision_pending = False
    persist = Mock(return_value=replacement)
    monkeypatch.setattr(wizard_agent, "replace_character_concept", persist)
    context = wizard_agent.WizardContext(
        slot=4,
        cache=cache,
        phase="character",
        thread_id=cache.thread_id,
        model="TEST",
        context_data={"character_state": cache.get_character_state_dict()},
    )
    assert (
        wizard_agent.get_wizard_agent(context) is wizard_agent._concept_revision_agent
    )
    concept = sample_concept_submission().model_copy(
        update={"background": replacement.character.background}
    )
    with pytest.raises(CallDeferred):
        await wizard_agent.submit_character_concept(DummyRunContext(context), concept)
    assert persist.call_args.kwargs["thread_id"] == cache.thread_id
    assert persist.call_args.kwargs["artifact_token"] == cache.artifact_token()
    state = context.last_tool_result["data"]["character_state"]
    assert state["concept"]["background"].startswith("Age 54")
    canonical = CharacterCreationState.model_validate(
        cache.get_character_state_dict()
    ).model_dump()
    assert state.get("trait_selection") == canonical.get("trait_selection")
    assert state.get("wildcard") == canonical.get("wildcard")
    assert context.last_tool_result["character_revised"] is True
    assert context.last_tool_result["phase_complete"] is complete
    with pytest.raises(ModelRetry, match="does not update"):
        await wizard_agent._require_revision_submission(
            DummyRunContext(context),
            WizardResponse(
                message="Sure, she is now 54.", choices=["Keep this", "Change again"]
            ),
        )


@pytest.mark.parametrize("stale", ["thread", "phase", "complete"])
def test_chat_rejects_stale_or_unconfirmed_character_before_provider_setup(
    monkeypatch, stale
) -> None:
    cache = character_cache()
    monkeypatch.setattr(wizard_chat, "require_writable_slot", lambda slot: None)
    monkeypatch.setattr(wizard_chat, "read_cache", lambda db: cache)
    monkeypatch.setattr(
        slot_state,
        "get_slot_state",
        lambda slot: SlotState(
            slot=4,
            is_empty=False,
            is_wizard_mode=True,
            wizard_state=WizardState(
                phase="character",
                thread_id=cache.thread_id,
                choices=[],
                has_concept=True,
                has_traits=True,
                has_wildcard=True,
            ),
            narrative_state=None,
            model="TEST",
        ),
    )
    provider = Mock(side_effect=AssertionError("must reject before provider access"))
    monkeypatch.setattr(wizard_chat, "ConversationsClient", provider)
    app = FastAPI()
    app.include_router(wizard_chat.router)
    response = TestClient(app).post(
        "/api/story/new/chat",
        json={
            "slot": 4,
            "thread_id": "old-thread" if stale == "thread" else cache.thread_id,
            "current_phase": "seed" if stale == "phase" else "character",
            "message": "Introduce the next phase",
        },
    )
    assert response.status_code == 409
    provider.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("unconfirmed", ["setting_confirmed", "character_confirmed"])
async def test_final_transition_cannot_bypass_artifact_acceptance(
    monkeypatch, unconfirmed
):
    from nexus.api.narrative_schemas import TransitionRequest
    from fastapi import HTTPException

    cache = character_cache()
    cache.setting_confirmed = cache.character_confirmed = True
    setattr(cache, unconfirmed, False)
    monkeypatch.setattr(wizard_chat, "require_writable_slot", lambda slot: None)
    monkeypatch.setattr(wizard_chat, "read_cache", lambda dbname: cache)
    with pytest.raises(HTTPException) as caught:
        await wizard_chat.transition_to_narrative_endpoint(TransitionRequest(slot=4))
    assert caught.value.status_code == 409
    assert "Confirm the setting and character" in caught.value.detail


def test_tool_response_cannot_be_relabeled_with_replacement_story(monkeypatch):
    cache = character_cache()
    cache.thread_id = "new-story"
    monkeypatch.setattr(wizard_chat, "read_cache", lambda dbname: cache)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        wizard_chat._artifact_response({"phase_complete": True}, 4, "old-story")
    assert caught.value.status_code == 409


@pytest.mark.asyncio
async def test_second_tool_submission_in_one_response_is_rejected_before_writes():
    from nexus.api.wizard_confirmation import WizardStateConflict

    cache = character_cache()
    context = wizard_agent.WizardContext(
        slot=4,
        cache=cache,
        phase="character",
        thread_id=cache.thread_id,
        model="TEST",
        last_tool_result={"phase_complete": True},
    )
    with pytest.raises(WizardStateConflict, match="Only one artifact"):
        await wizard_agent.submit_character_concept(
            DummyRunContext(context), sample_concept_submission()
        )


def test_delayed_artifact_response_cannot_confirm_a_newer_unseen_draft(monkeypatch):
    """The displayed data and confirmation token must describe one saved artifact."""
    from fastapi import HTTPException

    cache = character_cache()
    old_result = {
        "phase": "character",
        "phase_complete": True,
        "data": {"background": cache.character.background},
        **cache.confirmation_metadata(),
    }
    cache.character.background = (
        "Age 54. A newer draft produced by another browser tab."
    )
    monkeypatch.setattr(wizard_chat, "read_cache", lambda dbname: cache)
    with pytest.raises(HTTPException) as caught:
        wizard_chat._artifact_response(old_result, 4, cache.thread_id)
    assert caught.value.status_code == 409
    assert old_result["artifact_token"] != cache.artifact_token()
    assert old_result["data"]["background"].startswith("Age 38")


def test_stale_client_context_cannot_restore_prose_after_revision(monkeypatch):
    """Normal traits/wildcard requests use the revised canonical concept too."""
    cache = character_cache(complete=False)
    stale = cache.get_character_state_dict()
    cache.character.background = "Age 54. The revised canonical concept."
    monkeypatch.setattr(wizard_agent, "read_cache", lambda dbname: cache)
    context = wizard_agent.WizardContext.from_request(
        slot=4,
        phase="character",
        thread_id=cache.thread_id,
        model="TEST",
        context_data={"character_state": stale},
        accept_fate=False,
        dev_mode=False,
        history_len=2,
        user_turns=1,
        assistant_turns=1,
    )
    assert not context.cache.character_revision_pending
    assert context.context_data["character_state"]["concept"]["background"].startswith(
        "Age 54"
    )
    assert stale["concept"]["background"].startswith("Age 38")


@pytest.mark.asyncio
async def test_accept_fate_prose_fallback_carries_committed_confirmation_metadata(
    monkeypatch,
) -> None:
    """A bare wildcard reply after auto-confirmed traits must still pass the gate."""
    from contextlib import nullcontext

    cache = character_cache(complete=False)
    committed = deepcopy(cache)
    committed.character.traits_confirmed = True
    context = wizard_agent.WizardContext(
        slot=4,
        cache=cache,
        phase="character",
        thread_id=cache.thread_id,
        model="TEST",
        context_data={
            "character_state": {
                "concept": {"name": cache.character.name},
                "trait_selection": None,
            }
        },
        accept_fate=True,
    )

    class Agent:
        async def run(self, *args, **kwargs):
            return SimpleNamespace(
                output=WizardResponse(
                    message="The bell rings once before the wildcard is chosen.",
                    choices=["Answer the bell", "Ignore the bell"],
                )
            )

    monkeypatch.setattr(wizard_chat, "guarded_wizard_write", lambda *a: nullcontext())
    monkeypatch.setattr(wizard_chat, "clear_suggested_traits", lambda dbname: None)
    monkeypatch.setattr(wizard_chat, "record_drafts", lambda slot, **drafts: None)
    monkeypatch.setattr(wizard_chat, "read_cache", lambda dbname: committed)
    monkeypatch.setattr(wizard_chat, "get_wizard_agent", lambda context: Agent())
    monkeypatch.setattr(wizard_chat, "record_pydantic_ai_result", lambda *a, **k: None)
    monkeypatch.setattr(wizard_chat, "write_wizard_choices", lambda *a, **k: None)

    result = await wizard_chat._handle_accept_fate_traits(
        context=context,
        accept_fate=True,
        current_phase="character",
        slot=4,
        message_history=[],
        model=None,
        model_name="TEST",
        provider_name="test",
        model_settings=None,
        client=Mock(),
        thread_id=cache.thread_id,
    )

    assert result is not None
    assert result["traits_auto_confirmed"] is True
    for key, value in committed.confirmation_metadata().items():
        assert result[key] == value, key
    # The same consistency gate every other artifact path passes through.
    assert wizard_chat._artifact_response(result, 4, cache.thread_id) is result


# Each accepted checkpoint and the phase its acceptance enters (#955).
CHECKPOINTS = [("setting", "character"), ("character", "seed")]


def accepted_cache(accepted: str, *, reply_recorded: bool) -> WizardCache:
    """A saved wizard whose `accepted` artifact was confirmed by the player."""
    cache = character_cache()
    if accepted == "setting":
        cache.character = CharacterData()
    else:
        cache.character_confirmed = True
    cache.choices_recorded = reply_recorded
    return cache


def accepted_row(accepted: str, choice_object: object) -> WizardCache:
    """Read an accepted checkpoint through the database row adapter."""
    character = accepted == "character"
    return _row_to_cache(
        {
            "thread_id": "saved-thread",
            "setting_genre": "fantasy",
            "setting_confirmed": True,
            "character_name": "Mara" if character else None,
            "character_confirmed": character,
            "choice_object": choice_object,
        },
        traits_confirmed=character,
        wildcard_row=(
            {"name": "The bell", "rationale": "She hears it first."}
            if character
            else None
        ),
    )


@pytest.mark.parametrize(("accepted", "introduced"), CHECKPOINTS)
def test_acceptance_awaits_the_next_introduction_until_a_reply_is_recorded(
    accepted: str, introduced: str
) -> None:
    """Acceptance clears the choices; only a recorded reply introduces the phase."""
    waiting = accepted_row(accepted, None)
    assert waiting.current_phase() == introduced
    assert waiting.pending_confirmation() is None
    assert waiting.awaiting_introduction() == introduced

    # An introduction that offered no choices still recorded its reply.
    replied = accepted_row(accepted, {"presented": [], "selected": None})
    assert replied.current_phase() == introduced
    assert replied.awaiting_introduction() is None

    # Completion without acceptance is a pending confirmation, never a transition.
    unaccepted = accepted_row(accepted, None)
    setattr(unaccepted, f"{accepted}_confirmed", False)
    assert unaccepted.pending_confirmation() == accepted
    assert unaccepted.awaiting_introduction() is None

    # A draft in the entered phase proves it was already introduced.
    drafted = accepted_row(accepted, None)
    if introduced == "character":
        drafted.character.name = "Mara"
    else:
        drafted.seed.seed_type = "mystery"
    assert drafted.awaiting_introduction() is None


@pytest.mark.parametrize(("accepted", "introduced"), CHECKPOINTS)
def test_resume_restores_accepted_artifact_while_its_introduction_is_missing(
    monkeypatch: pytest.MonkeyPatch, accepted: str, introduced: str
) -> None:
    """An interrupted transition resumes as accepted, not as an empty next phase."""
    cache = accepted_cache(accepted, reply_recorded=False)
    monkeypatch.setattr(setup_endpoints, "resume_setup", lambda slot: cache)
    monkeypatch.setattr(setup_endpoints, "get_slot_model", lambda *a, **kw: "TEST")
    monkeypatch.setattr(
        setup_endpoints,
        "ConversationsClient",
        lambda *a, **kw: SimpleNamespace(
            list_messages=lambda *a, **kw: [], client=None
        ),
    )
    app = FastAPI()
    app.include_router(setup_endpoints.router)
    client = TestClient(app)

    data = client.get("/api/story/new/setup/resume?slot=4").json()
    assert data["current_phase"] == data["awaiting_introduction"] == introduced
    assert data["pending_confirmation"] is None
    assert data["choices"] == []
    assert data["setting_draft"]["genre"] == "fantasy"
    if accepted == "character":
        assert data["character_sheet"]["name"] == "Mara"
    else:
        assert data["character_sheet"] is None

    cache.choices_recorded = True
    introduced_data = client.get("/api/story/new/setup/resume?slot=4").json()
    assert introduced_data["current_phase"] == introduced
    assert introduced_data["awaiting_introduction"] is None
    assert introduced_data["character_sheet"] is None


def introduction_routes(
    monkeypatch: pytest.MonkeyPatch, accepted: str, introduced: str, replies: list
) -> SimpleNamespace:
    """Mount the chat and resume routes on an accepted, unintroduced wizard.

    Choice writes follow the database contract: an introduction claim succeeds
    only while no reply has recorded choices, and a release withdraws it.
    """
    from nexus.api.wizard_confirmation import WizardStateConflict

    cache = accepted_cache(accepted, reply_recorded=False)
    storage = ConversationsClient("TEST")
    thread_id = storage.create_thread()
    cache.thread_id = thread_id
    storage.add_message(thread_id, "assistant", "Anything else before we finish?")
    storage.add_message(thread_id, "user", "That is everything.")
    released: list[list[str]] = []

    class Agent:
        async def run(self, *args, **kwargs):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return SimpleNamespace(output=reply() if callable(reply) else reply)

        async def run_stream(self, *args, **kwargs):
            output = (await self.run()).output

            class Turn:
                async def stream_output(self):
                    yield output

                async def get_output(self):
                    return output

            yield Turn()

    def record_choices(choices, dbname, *, expected_thread_id, **kwargs):
        assert expected_thread_id == thread_id
        if kwargs.get("claim_introduction") and cache.choices_recorded:
            raise WizardStateConflict(
                "This phase was already introduced. Resume before continuing."
            )
        cache.choices = choices
        cache.choices_recorded = True

    def release(choices, dbname, *, expected_thread_id):
        assert expected_thread_id == thread_id
        released.append(choices)
        cache.choices = []
        cache.choices_recorded = False

    state = SlotState(
        slot=4,
        is_empty=False,
        is_wizard_mode=True,
        wizard_state=WizardState(
            phase=introduced,
            thread_id=thread_id,
            choices=[],
            has_concept=accepted == "character",
            has_traits=accepted == "character",
            has_wildcard=accepted == "character",
        ),
        narrative_state=None,
        model="TEST",
    )
    monkeypatch.setattr(slot_state, "get_slot_state", lambda slot: state)
    monkeypatch.setattr(wizard_agent, "read_cache", lambda dbname: cache)
    monkeypatch.setattr(wizard_chat, "read_cache", lambda dbname: cache)
    monkeypatch.setattr(wizard_chat, "require_writable_slot", lambda slot: None)
    monkeypatch.setattr(wizard_chat, "ConversationsClient", lambda model: storage)
    monkeypatch.setattr(wizard_chat, "get_wizard_agent", lambda context: Agent())
    monkeypatch.setattr(wizard_chat, "get_wizard_streaming_enabled", lambda: True)
    monkeypatch.setattr(
        wizard_chat, "build_pydantic_ai_model_with_provider", lambda m: (None, "test")
    )
    monkeypatch.setattr(wizard_chat, "record_pydantic_ai_result", lambda *a, **k: None)
    monkeypatch.setattr(wizard_chat, "write_wizard_choices", record_choices)
    monkeypatch.setattr(wizard_chat, "release_wizard_introduction", release)
    monkeypatch.setattr(setup_endpoints, "resume_setup", lambda slot: cache)
    monkeypatch.setattr(setup_endpoints, "get_slot_model", lambda *a, **k: "TEST")
    monkeypatch.setattr(setup_endpoints, "ConversationsClient", lambda model: storage)
    app = FastAPI()
    app.include_router(wizard_chat.router)
    app.include_router(setup_endpoints.router)
    return SimpleNamespace(
        client=TestClient(app, raise_server_exceptions=False),
        cache=cache,
        storage=storage,
        thread_id=thread_id,
        released=released,
        introduction={
            "slot": 4,
            "thread_id": thread_id,
            "current_phase": introduced,
            "message": (
                f"[SYSTEM] Phase {accepted} complete. Proceeding to {introduced}. "
                "Please introduce the next phase."
            ),
            "message_origin": "wizard_control",
        },
    )


def assistant_messages(routes: SimpleNamespace) -> list[str]:
    """Transcript replies, excluding the two seeded before acceptance."""
    return [
        message["content"]
        for message in routes.storage.list_messages(routes.thread_id, limit=0)
        if message["role"] == "assistant"
    ][1:]


@pytest.mark.parametrize(("accepted", "introduced"), CHECKPOINTS)
def test_interrupted_introduction_is_retried_once_then_refused(
    monkeypatch: pytest.MonkeyPatch, accepted: str, introduced: str
) -> None:
    """A failed introduction stays requestable; a recorded one cannot repeat."""
    replies: list = [
        RuntimeError("Provider unavailable"),
        WizardResponse(
            message="Where does it begin?", choices=["The harbor", "The lighthouse"]
        ),
        WizardResponse(
            message="Tell me about the harbor.", choices=["Its lamps", "Its debts"]
        ),
    ]
    routes = introduction_routes(monkeypatch, accepted, introduced, replies)
    client, introduction = routes.client, routes.introduction

    assert client.post("/api/story/new/chat", json=introduction).status_code == 500
    interrupted = client.get("/api/story/new/setup/resume?slot=4").json()
    assert interrupted["awaiting_introduction"] == introduced
    assert interrupted["messages"][-1]["content"] == "That is everything."

    retried = client.post("/api/story/new/chat", json=introduction)
    assert retried.status_code == 200, retried.text
    assert retried.json()["choices"] == ["The harbor", "The lighthouse"]
    resumed = client.get("/api/story/new/setup/resume?slot=4").json()
    assert resumed["current_phase"] == introduced
    assert resumed["awaiting_introduction"] is None
    assert resumed["choices"] == ["The harbor", "The lighthouse"]
    assert resumed["messages"][-1] == {
        "role": "assistant",
        "content": "Where does it begin?",
    }

    before = routes.storage.list_messages(routes.thread_id, limit=0)
    for endpoint in ("/api/story/new/chat", "/api/story/new/chat/stream"):
        repeated = client.post(endpoint, json=introduction)
        assert repeated.status_code == 409
        assert "already introduced" in repeated.json()["detail"]
    assert routes.storage.list_messages(routes.thread_id, limit=0) == before
    assert len(replies) == 1

    # The refusal is specific to the application's introduction control.
    player = client.post(
        "/api/story/new/chat",
        json=introduction
        | {"message": "Start at the harbor.", "message_origin": "user"},
    )
    assert player.status_code == 200, player.text
    assert replies == []
    assert routes.released == []


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(("accepted", "introduced"), CHECKPOINTS)
def test_introduction_that_loses_the_claim_never_reaches_the_transcript(
    monkeypatch: pytest.MonkeyPatch, accepted: str, introduced: str, stream: bool
) -> None:
    """Concurrent introductions: only the reply that records choices is kept."""
    routes: SimpleNamespace

    def concurrent_winner_lands_first() -> WizardResponse:
        # Another request introduced the phase while this model call ran.
        routes.cache.choices = ["The winner's option", "Another"]
        routes.cache.choices_recorded = True
        return WizardResponse(
            message="A second introduction.", choices=["Late one", "Late two"]
        )

    routes = introduction_routes(
        monkeypatch, accepted, introduced, [concurrent_winner_lands_first]
    )
    endpoint = "/api/story/new/chat" + ("/stream" if stream else "")
    response = routes.client.post(endpoint, json=routes.introduction)
    if stream:
        assert response.status_code == 200
        record = json.loads(response.text.strip().splitlines()[-1])
        assert (record["type"], record["status_code"]) == ("error", 409)
        assert "already introduced" in record["detail"]
    else:
        assert response.status_code == 409
        assert "already introduced" in response.json()["detail"]
    assert assistant_messages(routes) == []
    assert routes.cache.choices == ["The winner's option", "Another"]
    assert routes.released == []


@pytest.mark.parametrize(("accepted", "introduced"), CHECKPOINTS)
def test_transcript_failure_withdraws_the_introduction_claim(
    monkeypatch: pytest.MonkeyPatch, accepted: str, introduced: str
) -> None:
    """A claimed introduction that never reached the transcript stays requestable."""
    routes = introduction_routes(
        monkeypatch,
        accepted,
        introduced,
        [WizardResponse(message="Lost on the way.", choices=["One", "Two"])],
    )
    add_message = routes.storage.add_message

    def failing_assistant_write(thread_id, role, content, **kwargs):
        if role == "assistant":
            raise RuntimeError("Conversation store unavailable")
        return add_message(thread_id, role, content, **kwargs)

    routes.storage.add_message = failing_assistant_write
    response = routes.client.post("/api/story/new/chat", json=routes.introduction)
    assert response.status_code == 500
    assert "Conversation store unavailable" in response.json()["detail"]
    assert routes.released == [["One", "Two"]]
    resumed = routes.client.get("/api/story/new/setup/resume?slot=4").json()
    assert resumed["awaiting_introduction"] == introduced
    assert assistant_messages(routes) == []
