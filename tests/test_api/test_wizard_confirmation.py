"""Draft completion, revision and player confirmation are distinct transitions."""

from copy import deepcopy
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import CallDeferred, ModelRetry
import pytest

from nexus import cli
from nexus.api import (
    new_story_cache,
    setup_endpoints,
    slot_endpoints,
    wizard_agent,
    wizard_chat,
)
from nexus.api.conversations import ConversationsClient
from nexus.api.new_story_cache import (
    WizardCache,
    CharacterData,
    SettingData,
    SuggestedTrait,
    _row_to_cache,
)
from nexus.api.new_story_schemas import WizardResponse, CharacterCreationState
from nexus.api.slot_state import _get_wizard_state_from_row
from tests.pg_fixtures import connect
from tests.test_cli_wizard_confirmation import Response, arguments
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


@pytest.mark.requires_postgres
def test_resume_restores_complete_character_card_without_inference(
    offline_gate_db: str, seed_wizard_cache
) -> None:
    cache = seed_wizard_cache(character_cache())
    app = FastAPI()
    app.include_router(setup_endpoints.router)
    client = TestClient(app)
    response = client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["current_phase"] == data["pending_confirmation"] == "character"
    assert data["artifact_token"] == cache.artifact_token()
    assert data["character_sheet"]["name"] == "Mara"
    assert data["character_state"]["concept"]["background"].startswith("Age 38")
    with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE assets.new_story_creator SET character_revision_pending = TRUE "
            "WHERE id = TRUE"
        )
    response = client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 200, response.text
    revised = response.json()
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


@pytest.mark.requires_postgres
@pytest.mark.parametrize("stale", ["thread", "phase", "complete"])
def test_chat_rejects_stale_or_unconfirmed_character_before_provider_setup(
    monkeypatch, seed_wizard_cache, stale
) -> None:
    cache = seed_wizard_cache(character_cache())
    provider = Mock(side_effect=AssertionError("must reject before provider access"))
    monkeypatch.setattr(wizard_chat, "build_pydantic_ai_model_with_provider", provider)
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


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_accept_fate_prose_fallback_carries_committed_confirmation_metadata(
    monkeypatch,
    offline_gate_db: str,
    seed_wizard_cache,
) -> None:
    """A bare wildcard reply after real trait acceptance still passes the gate."""
    cache = seed_wizard_cache(character_cache(complete=False))
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

    monkeypatch.setattr(wizard_chat, "get_wizard_agent", lambda context: Agent())
    monkeypatch.setattr(wizard_chat, "record_pydantic_ai_result", lambda *a, **k: None)
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
        client=ConversationsClient(offline_gate_db),
        thread_id=cache.thread_id,
    )
    committed = new_story_cache.read_cache(offline_gate_db)
    assert committed is not None and committed.character.traits_confirmed
    assert result is not None
    assert result["traits_auto_confirmed"] is True
    for key, value in committed.confirmation_metadata().items():
        assert result[key] == value, key
    assert wizard_chat._artifact_response(result, 4, cache.thread_id) is result
    saved = new_story_cache.read_cache(offline_gate_db)
    assert saved is not None
    assert saved.choices == ["Answer the bell", "Ignore the bell"]


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


@pytest.mark.requires_postgres
@pytest.mark.parametrize(("accepted", "introduced"), CHECKPOINTS)
def test_resume_restores_accepted_artifact_while_its_introduction_is_missing(
    offline_gate_db: str, seed_wizard_cache, accepted: str, introduced: str
) -> None:
    """An interrupted transition resumes as accepted, not an empty next phase."""
    cache = seed_wizard_cache(accepted_cache(accepted, reply_recorded=False))
    app = FastAPI()
    app.include_router(setup_endpoints.router)
    client = TestClient(app)
    response = client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["current_phase"] == data["awaiting_introduction"] == introduced
    assert data["pending_confirmation"] is None
    assert data["choices"] == []
    assert data["setting_draft"]["genre"] == "fantasy"
    if accepted == "character":
        assert data["character_sheet"]["name"] == "Mara"
    else:
        assert data["character_sheet"] is None
    new_story_cache.record_wizard_reply(
        offline_gate_db,
        expected_thread_id=cache.thread_id,
        message="Where does it begin?",
        choices=[],
        introduction=True,
    )
    response = client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 200, response.text
    introduced_data = response.json()
    assert introduced_data["current_phase"] == introduced
    assert introduced_data["awaiting_introduction"] is None
    assert introduced_data["character_sheet"] is None


def introduction_routes(
    monkeypatch: pytest.MonkeyPatch,
    dbname: str,
    seed_wizard_cache,
    accepted: str,
    introduced: str,
    replies: list,
) -> SimpleNamespace:
    """Mount chat/resume/state on a real accepted, unintroduced slot wizard."""
    cache = seed_wizard_cache(accepted_cache(accepted, reply_recorded=False))
    storage = ConversationsClient(dbname)
    thread_id = cache.thread_id
    storage.add_message(thread_id, "assistant", "Anything else before we finish?")
    storage.add_message(thread_id, "user", "That is everything.", origin="user")

    class Agent:
        async def run(self, *args, **kwargs):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return SimpleNamespace(output=reply() if callable(reply) else reply)

    monkeypatch.setattr(wizard_chat, "get_wizard_agent", lambda context: Agent())
    monkeypatch.setattr(
        wizard_chat, "build_pydantic_ai_model_with_provider", lambda m: (None, "test")
    )
    monkeypatch.setattr(wizard_chat, "record_pydantic_ai_result", lambda *a, **k: None)
    app = FastAPI()
    app.include_router(wizard_chat.router)
    app.include_router(setup_endpoints.router)
    app.include_router(slot_endpoints.router)
    return SimpleNamespace(
        client=TestClient(app, raise_server_exceptions=False),
        dbname=dbname,
        storage=storage,
        thread_id=thread_id,
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
    """Chronological replies after the one seeded before acceptance."""
    return [
        message["content"]
        for message in reversed(routes.storage.list_messages(routes.thread_id, limit=0))
        if message["role"] == "assistant"
    ][1:]


def resume(routes: SimpleNamespace) -> dict:
    """Read the wizard exactly as a reload does."""
    response = routes.client.get("/api/story/new/setup/resume?slot=4")
    assert response.status_code == 200, response.text
    return response.json()


def slot_state_of(routes: SimpleNamespace) -> dict:
    """Read the slot state the CLI and Continue use."""
    response = routes.client.get("/api/slot/4/state")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.requires_postgres
@pytest.mark.parametrize(("accepted", "introduced"), CHECKPOINTS)
def test_interrupted_introduction_is_retried_once_then_refused(
    monkeypatch: pytest.MonkeyPatch,
    offline_gate_db: str,
    seed_wizard_cache,
    accepted: str,
    introduced: str,
) -> None:
    """A failed introduction stays requestable; a completed one cannot repeat."""
    replies: list = [
        RuntimeError("Provider unavailable"),
        WizardResponse(
            message="Where does it begin?", choices=["The harbor", "The lighthouse"]
        ),
        WizardResponse(
            message="Tell me about the harbor.", choices=["Its lamps", "Its debts"]
        ),
    ]
    routes = introduction_routes(
        monkeypatch, offline_gate_db, seed_wizard_cache, accepted, introduced, replies
    )
    client, introduction = routes.client, routes.introduction

    assert client.post("/api/story/new/chat", json=introduction).status_code == 500
    interrupted = resume(routes)
    assert interrupted["awaiting_introduction"] == introduced
    assert interrupted["messages"][-1]["content"] == "That is everything."

    retried = client.post("/api/story/new/chat", json=introduction)
    assert retried.status_code == 200, retried.text
    assert retried.json()["choices"] == ["The harbor", "The lighthouse"]
    resumed = resume(routes)
    assert resumed["current_phase"] == introduced
    assert resumed["awaiting_introduction"] is None
    assert resumed["choices"] == ["The harbor", "The lighthouse"]
    assert resumed["messages"][-1] == {
        "role": "assistant",
        "content": "Where does it begin?",
    }

    before = routes.storage.list_messages(routes.thread_id, limit=0)
    repeated = client.post("/api/story/new/chat", json=introduction)
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


@pytest.mark.requires_postgres
@pytest.mark.parametrize(("accepted", "introduced"), CHECKPOINTS)
def test_concurrent_introduction_keeps_only_the_committed_reply(
    monkeypatch: pytest.MonkeyPatch,
    offline_gate_db: str,
    seed_wizard_cache,
    accepted: str,
    introduced: str,
) -> None:
    """An introduction committed during generation wins the actual row lock."""
    routes: SimpleNamespace

    def concurrent_winner_goes_first() -> WizardResponse:
        new_story_cache.record_wizard_reply(
            offline_gate_db,
            expected_thread_id=routes.thread_id,
            message="The winning introduction.",
            choices=["The winner's option", "Another"],
            introduction=True,
        )
        return WizardResponse(
            message="A second introduction.", choices=["Late one", "Late two"]
        )

    routes = introduction_routes(
        monkeypatch,
        offline_gate_db,
        seed_wizard_cache,
        accepted,
        introduced,
        [concurrent_winner_goes_first],
    )
    response = routes.client.post("/api/story/new/chat", json=routes.introduction)
    assert response.status_code == 409, response.text
    assert "already introduced" in response.json()["detail"]
    assert assistant_messages(routes) == ["The winning introduction."]
    cache = new_story_cache.read_cache(offline_gate_db)
    assert cache is not None and cache.choices == ["The winner's option", "Another"]


@pytest.mark.requires_postgres
@pytest.mark.parametrize(("accepted", "introduced"), CHECKPOINTS)
def test_cli_uses_the_committed_introduction(
    monkeypatch: pytest.MonkeyPatch,
    offline_gate_db: str,
    seed_wizard_cache,
    accepted: str,
    introduced: str,
) -> None:
    """Real slot state shows delivered choices, so the CLI cannot reintroduce."""
    routes = introduction_routes(
        monkeypatch,
        offline_gate_db,
        seed_wizard_cache,
        accepted,
        introduced,
        [WizardResponse(message="Where does it begin?", choices=["Here", "There"])],
    )
    response = routes.client.post("/api/story/new/chat", json=routes.introduction)
    assert response.status_code == 200, response.text
    assert assistant_messages(routes) == ["Where does it begin?"]

    posts: list[tuple[str, dict]] = []

    def gateway_get(url: str, **kwargs):
        assert url.endswith("/api/slot/4/state")
        return Response(slot_state_of(routes))

    def gateway_post(url: str, *, json: dict, **kwargs):
        posts.append((url.split("/api/")[-1], json))
        return Response({"message": "The harbor waits.", "choices": []})

    monkeypatch.setattr(cli, "_api_get", gateway_get)
    monkeypatch.setattr(cli, "_api_post", gateway_post)

    loaded = cli.run_load(arguments())
    assert "awaiting_introduction" not in loaded
    assert loaded["choices"] == ["Here", "There"]
    # Without input there is no introduction left to request.
    idle = cli.run_continue(arguments())
    assert idle["success"] is False
    assert posts == []
    # The delivered choices answer the introduction.
    answered = cli.run_continue(arguments(choice=1))
    assert answered["success"] is True
    assert [(path, body["message"]) for path, body in posts] == [
        ("story/new/chat", "Here")
    ]
    assert "message_origin" not in posts[0][1]
