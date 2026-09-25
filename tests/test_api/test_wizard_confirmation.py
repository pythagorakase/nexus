"""Draft completion, revision and player confirmation are distinct transitions."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import CallDeferred, ModelRetry
import pytest

from nexus.api import setup_endpoints, wizard_agent, wizard_chat, slot_state
from nexus.api.new_story_cache import (
    WizardCache,
    CharacterData,
    SettingData,
    SuggestedTrait,
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
