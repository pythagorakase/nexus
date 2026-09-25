"""Real persistence and resume on disposable migrated wizard databases.

Needs assets.new_story_creator and assets.traits; no provider calls or real saves.
"""

from contextlib import closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nexus.api import setup_endpoints
from nexus.api.new_story_cache import init_cache, read_cache, write_cache
from nexus.api.wizard_confirmation import (
    WizardStateConflict,
    begin_character_revision,
    confirm_artifact,
    replace_character_concept,
)
from tests.pg_fixtures import connect
from tests.test_api.test_wizard_confirmation import character_cache
from tests.test_wizard_agent import sample_setting

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def saved_character(offline_gate_db: str) -> str:
    init_cache(offline_gate_db, "saved-thread", 4)
    write_cache(
        dbname=offline_gate_db,
        setting_draft=sample_setting().model_dump(),
        character_draft=character_cache().get_character_state_dict(),
    )
    with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE assets.new_story_creator SET setting_confirmed = TRUE, "
            "trait_compile_result = '{\"old\": true}'::jsonb"
        )
    return offline_gate_db


def test_revision_replaces_persisted_prose_without_resetting_mechanics(
    saved_character: str,
) -> None:
    before = read_cache(saved_character)
    token = before.artifact_token()
    result = begin_character_revision(
        saved_character, thread_id=before.thread_id, artifact_token=token
    )
    assert result["status"] == "revision_started"
    resumed = read_cache(saved_character)
    assert resumed.current_phase() == "character"
    assert resumed.pending_confirmation() is None
    assert resumed.character_revision_pending
    assert resumed.get_character_state_dict() == before.get_character_state_dict()
    concept = {
        **before.get_character_state_dict()["concept"],
        "background": "Age 54. Repairs the harbor machinery and protects its workers.",
    }
    replace_character_concept(
        saved_character,
        thread_id=before.thread_id,
        artifact_token=token,
        concept=concept,
    )
    after = read_cache(saved_character)
    assert after.character.background.startswith("Age 54")
    assert after.character.trait_compile_result is None
    assert after.pending_confirmation() == "character"
    assert not after.character_revision_pending
    assert (
        after.get_character_state_dict()["trait_selection"]
        == before.get_character_state_dict()["trait_selection"]
    )
    assert (
        after.get_character_state_dict()["wildcard"]
        == before.get_character_state_dict()["wildcard"]
    )
    with pytest.raises(WizardStateConflict):
        confirm_artifact(
            saved_character,
            thread_id=before.thread_id,
            phase="character",
            artifact_token=token,
        )
    result = confirm_artifact(
        saved_character,
        thread_id=before.thread_id,
        phase="character",
        artifact_token=after.artifact_token(),
    )
    assert result["next_phase"] == "seed"
    assert read_cache(saved_character).current_phase() == "seed"
    with pytest.raises(WizardStateConflict):
        confirm_artifact(
            saved_character,
            thread_id=before.thread_id,
            phase="character",
            artifact_token=after.artifact_token("character"),
        )


@pytest.mark.parametrize("stale", ["thread", "artifact", "subphase"])
def test_stale_revision_cannot_replace_a_changed_story(
    saved_character: str, stale: str
) -> None:
    before = read_cache(saved_character)
    token = before.artifact_token()
    begin_character_revision(
        saved_character, thread_id=before.thread_id, artifact_token=token
    )
    with closing(connect(saved_character)) as conn, conn, conn.cursor() as cur:
        if stale == "thread":
            cur.execute(
                "UPDATE assets.new_story_creator SET thread_id = 'replacement-story'"
            )
        elif stale == "artifact":
            cur.execute(
                "UPDATE assets.new_story_creator SET character_background = 'A "
                "newer player revision.'"
            )
        else:
            cur.execute(
                "UPDATE assets.new_story_creator SET character_revision_pending = "
                "FALSE, character_confirmed = TRUE"
            )
    expected = read_cache(saved_character)
    with pytest.raises(WizardStateConflict):
        replace_character_concept(
            saved_character,
            thread_id=before.thread_id,
            artifact_token=token,
            concept={
                **before.get_character_state_dict()["concept"],
                "background": "Stale late model result.",
            },
        )
    actual = read_cache(saved_character)
    assert actual.get_character_state_dict() == expected.get_character_state_dict()
    assert actual.thread_id == expected.thread_id


def test_confirmation_endpoint_rejects_revision_in_progress(
    saved_character: str, monkeypatch
) -> None:
    cache = read_cache(saved_character)
    begin_character_revision(
        saved_character,
        thread_id=cache.thread_id,
        artifact_token=cache.artifact_token(),
    )
    app = FastAPI()
    app.include_router(setup_endpoints.router)
    response = TestClient(app).post(
        "/api/story/new/setup/confirm",
        json={
            "slot": 4,
            "thread_id": cache.thread_id,
            "phase": "character",
            "artifact_token": cache.artifact_token(),
        },
    )
    assert response.status_code == 409
    assert read_cache(saved_character).current_phase() == "character"


@pytest.mark.parametrize(
    "legacy_progress", ["setting_draft", "complete_character", "seed_started"]
)
def test_migration_only_backfills_confirmation_from_later_persisted_progress(
    saved_character: str, legacy_progress: str
) -> None:
    migration = (
        Path(__file__).resolve().parents[2] / "migrations/129_wizard_confirmation.sql"
    )
    with closing(connect(saved_character)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE assets.new_story_creator DROP COLUMN setting_confirmed, "
            "DROP COLUMN character_confirmed, DROP COLUMN "
            "character_revision_pending"
        )
        if legacy_progress == "setting_draft":
            cur.execute(
                "UPDATE assets.new_story_creator SET character_name = NULL, "
                "traits_confirmed = FALSE"
            )
        elif legacy_progress == "seed_started":
            cur.execute(
                "UPDATE assets.new_story_creator SET layer_name = 'Persisted "
                "introduction world'"
            )
        cur.execute(migration.read_text())
    cache = read_cache(saved_character)
    assert cache.setting_confirmed is (legacy_progress != "setting_draft")
    assert cache.character_confirmed is (legacy_progress == "seed_started")
    if legacy_progress == "complete_character":
        assert cache.pending_confirmation() == "character"
        assert cache.character.background.startswith("Age 38")


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_phase", ["setting", "traits", "wildcard"])
async def test_late_ordinary_tool_cannot_overwrite_accepted_or_revising_draft(
    saved_character: str, monkeypatch, tool_phase: str
) -> None:
    """A model result racing Confirm/Revise changes neither cache nor any trait row."""
    from nexus.api import wizard_agent
    from nexus.api.wizard_agent import WizardContext
    from tests.test_wizard_agent import (
        DummyRunContext,
        sample_trait_selection,
        sample_wildcard,
    )

    monkeypatch.setattr(wizard_agent, "slot_dbname", lambda slot: saved_character)
    with closing(connect(saved_character)) as conn, conn, conn.cursor() as cur:
        if tool_phase == "setting":
            cur.execute("UPDATE assets.new_story_creator SET setting_confirmed = FALSE")
        elif tool_phase == "traits":
            cur.execute("UPDATE assets.new_story_creator SET traits_confirmed = FALSE")
        if tool_phase in {"traits", "wildcard"}:
            cur.execute(
                "UPDATE assets.traits SET name = 'wildcard', rationale = NULL "
                "WHERE id = 11"
            )
    before_inference = read_cache(saved_character)
    context = WizardContext(
        slot=4,
        cache=before_inference,
        phase="setting" if tool_phase == "setting" else "character",
        thread_id=before_inference.thread_id,
        model="TEST",
        context_data={"character_state": before_inference.get_character_state_dict()},
    )
    if tool_phase == "setting":
        confirm_artifact(
            saved_character,
            thread_id=context.thread_id,
            phase="setting",
            artifact_token=before_inference.artifact_token(),
        )
        tool, payload = wizard_agent.submit_world_document, sample_setting().model_copy(
            update={"world_name": "Late overwritten world"}
        )
    else:
        begin_character_revision(
            saved_character,
            thread_id=context.thread_id,
            artifact_token=before_inference.artifact_token(),
        )
        tool, payload = (
            (wizard_agent.submit_trait_selection, sample_trait_selection())
            if tool_phase == "traits"
            else (wizard_agent.submit_wildcard_trait, sample_wildcard())
        )
    accepted = read_cache(saved_character)
    with pytest.raises(WizardStateConflict):
        await tool(DummyRunContext(context), payload)
    actual = read_cache(saved_character)
    assert actual.get_setting_dict() == accepted.get_setting_dict()
    assert actual.get_character_state_dict() == accepted.get_character_state_dict()
    assert actual.setting_confirmed == accepted.setting_confirmed
    assert actual.character_revision_pending == accepted.character_revision_pending


def test_tool_transaction_rolls_back_trait_mutation_on_error(
    saved_character: str,
) -> None:
    from nexus.api.new_story_cache import clear_suggested_traits, guarded_wizard_write

    before = read_cache(saved_character)
    with pytest.raises(RuntimeError, match="fixture failure"):
        with guarded_wizard_write(saved_character, before):
            clear_suggested_traits(saved_character)
            raise RuntimeError("fixture failure after first trait write")
    assert (
        read_cache(saved_character).get_character_state_dict()
        == before.get_character_state_dict()
    )


@pytest.mark.asyncio
async def test_successful_tool_captures_metadata_inside_its_commit(
    saved_character: str, monkeypatch
) -> None:
    from nexus.api import wizard_agent, wizard_chat
    from nexus.api.wizard_agent import WizardContext
    from pydantic_ai import CallDeferred
    from fastapi import HTTPException
    from tests.test_wizard_agent import DummyRunContext, sample_wildcard
    from nexus.agents.orrery import tag_writer
    from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
    from nexus.api.new_story_cache import _wizard_transaction

    monkeypatch.setattr(wizard_agent, "slot_dbname", lambda slot: saved_character)
    monkeypatch.setattr(wizard_chat, "slot_dbname", lambda slot: saved_character)
    with closing(connect(saved_character)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE assets.traits SET name = 'wildcard', rationale = NULL WHERE id = 11"
        )
    before = read_cache(saved_character)
    context = WizardContext(
        slot=4,
        cache=before,
        phase="character",
        thread_id=before.thread_id,
        model="TEST",
        context_data={"character_state": before.get_character_state_dict()},
    )
    original_validate = tag_writer.validate_tag_bestowal
    validated_connections = []

    def validate_in_tool_transaction(cur, **kwargs):
        assert cur.connection is _wizard_transaction.get()[1]
        validated_connections.append(cur.connection)
        return original_validate(cur, **kwargs)

    monkeypatch.setattr(
        tag_writer, "validate_tag_bestowal", validate_in_tool_transaction
    )
    wildcard = sample_wildcard().model_copy(
        update={"orrery_tags": OrreryTagBestowal(applied_tags=[], tags_to_clear=[])}
    )
    with pytest.raises(CallDeferred):
        await wizard_agent.submit_wildcard_trait(DummyRunContext(context), wildcard)
    assert len(validated_connections) == 1
    accepted = read_cache(saved_character)
    assert (
        context.persisted_tool_cache.confirmation_metadata()
        == accepted.confirmation_metadata()
    )
    assert context.last_tool_result["artifact_token"] == accepted.artifact_token()
    begin_character_revision(
        saved_character,
        thread_id=accepted.thread_id,
        artifact_token=accepted.artifact_token(),
    )
    with pytest.raises(HTTPException) as caught:
        wizard_chat._artifact_response(context.last_tool_result, 4, accepted.thread_id)
    assert caught.value.status_code == 409
    assert read_cache(saved_character).character_revision_pending


@pytest.mark.asyncio
async def test_stale_client_trait_submission_preserves_revised_concept(
    saved_character: str, monkeypatch
) -> None:
    from nexus.api import wizard_agent
    from pydantic_ai import CallDeferred
    from tests.test_wizard_agent import DummyRunContext, sample_trait_selection

    monkeypatch.setattr(wizard_agent, "slot_dbname", lambda slot: saved_character)
    with closing(connect(saved_character)) as conn, conn, conn.cursor() as cur:
        cur.execute("UPDATE assets.new_story_creator SET traits_confirmed = FALSE")
        cur.execute(
            "UPDATE assets.traits SET name = 'wildcard', rationale = NULL WHERE id = 11"
        )
    old = read_cache(saved_character)
    stale_context = old.get_character_state_dict()
    begin_character_revision(
        saved_character, thread_id=old.thread_id, artifact_token=old.artifact_token()
    )
    replace_character_concept(
        saved_character,
        thread_id=old.thread_id,
        artifact_token=old.artifact_token(),
        concept={
            **stale_context["concept"],
            "background": "Age 54. A revised concept saved in the other tab.",
        },
    )
    context = wizard_agent.WizardContext.from_request(
        slot=4,
        phase="character",
        thread_id=old.thread_id,
        model="TEST",
        context_data={"character_state": stale_context},
        accept_fate=False,
        dev_mode=False,
        history_len=2,
        user_turns=1,
        assistant_turns=1,
    )
    with pytest.raises(CallDeferred):
        await wizard_agent.submit_trait_selection(
            DummyRunContext(context), sample_trait_selection()
        )
    after = read_cache(saved_character)
    assert after.character.background.startswith("Age 54")
    assert after.character.traits_confirmed
    assert not after.character_revision_pending
