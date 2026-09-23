"""
Regression tests for wizard default-model resolution.

The wizard UI no longer carries a model picker; clients omit `model` and the
backend resolves it: explicit request override -> slot's stamped model
(locked at setup start) -> configured wizard default from nexus.toml. The
mock TEST server must never be selected implicitly.
"""

from contextlib import closing
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nexus.api import new_story_flow, setup_endpoints, storyteller
from nexus.api.config_utils import get_new_story_model
from nexus.api.new_story_cache import read_cache_raw
from nexus.api.narrative_schemas import ChatRequest, StartSetupRequest
from nexus.api.new_story_flow import resolve_setup_model
from nexus.api.wizard_chat import resolve_wizard_model, wizard_model_lock_candidate
from tests.pg_fixtures import connect


def test_chat_request_model_defaults_to_none() -> None:
    """Omitted model stays None so the slot's stamped model can win."""
    request = ChatRequest(slot=5, message="hello")
    assert request.model is None


def test_chat_request_rejects_unknown_model() -> None:
    with pytest.raises(ValidationError, match="Invalid model"):
        ChatRequest(slot=5, message="hello", model="not-a-registry-id")


def test_chat_request_accepts_explicit_test_model() -> None:
    """TEST stays available as an explicit, backend-only override.

    Requires the test provider entry in nexus.toml's api_models registry;
    validate_model checks against get_available_api_models().
    """
    request = ChatRequest(slot=5, message="hello", model="TEST")
    assert request.model == "TEST"


def test_start_setup_request_model_defaults_to_none() -> None:
    request = StartSetupRequest(slot=5)
    assert request.model is None


def test_setup_model_preserves_operator_slot_model() -> None:
    assert (
        resolve_setup_model(
            "operator-model",
            setup_started=False,
            default_slot_model="fresh-placeholder",
            wizard_default_model="wizard-default",
        )
        == "operator-model"
    )


def test_setup_model_preserves_default_named_model_after_setup_started() -> None:
    """A prior wizard row disambiguates an intentional TEST model stamp."""
    assert (
        resolve_setup_model(
            "TEST",
            setup_started=True,
            default_slot_model="TEST",
            wizard_default_model="wizard-default",
        )
        == "TEST"
    )


@pytest.mark.parametrize("slot_model", [None, "", "fresh-placeholder"])
def test_setup_model_uses_wizard_default_only_for_fresh_slot(
    slot_model: str | None,
) -> None:
    assert (
        resolve_setup_model(
            slot_model,
            setup_started=False,
            default_slot_model="fresh-placeholder",
            wizard_default_model="wizard-default",
        )
        == "wizard-default"
    )


@pytest.mark.requires_postgres
def test_setup_endpoint_passes_omitted_model_to_core(
    monkeypatch: pytest.MonkeyPatch,
    offline_gate_db: str,
) -> None:
    """Pass omission unchanged to real setup and preserve its persisted stamp."""
    starts: list[tuple[int, str | None]] = []
    original_start_setup = setup_endpoints.start_setup

    def observed_start_setup(slot: int, model: str | None) -> str:
        """Record endpoint arguments while running the genuine setup."""
        starts.append((slot, model))
        return original_start_setup(slot, model)

    monkeypatch.setattr(setup_endpoints, "start_setup", observed_start_setup)
    # Establish an intentional TEST stamp, distinct from a fresh-slot default.
    previous_thread = new_story_flow.start_setup(4, model="TEST")
    app = FastAPI()
    app.include_router(setup_endpoints.router)
    response = TestClient(app).post("/api/story/new/setup/start", json={"slot": 4})

    assert response.status_code == 200, response.text
    assert starts == [(4, None)]
    result = response.json()
    assert result["model"] == "TEST"
    assert result["thread_id"] != previous_thread
    cache = read_cache_raw(offline_gate_db)
    assert cache is not None
    assert cache["thread_id"] == result["thread_id"]
    with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
        cur.execute("SELECT model FROM global_variables WHERE id = TRUE")
        assert cur.fetchone() == ("TEST",)
        cur.execute(
            "SELECT choice_object FROM assets.new_story_creator WHERE id = TRUE"
        )
        assert cur.fetchone()[0]["presented"] == result["welcome_choices"]


def test_legacy_storyteller_setup_passes_omitted_model_to_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second setup HTTP surface must preserve omission as well."""
    starts: list[tuple[int, str | None]] = []

    def fake_start_setup(slot: int, model: str | None = None) -> str:
        starts.append((slot, model))
        return "thread-operator"

    monkeypatch.setattr(storyteller, "start_new_story_setup", fake_start_setup)

    response = storyteller.new_story_setup_start(
        storyteller.NewStoryStartRequest(slot=4)
    )

    assert starts == [(4, None)]
    assert response.thread_id == "thread-operator"
    assert response.slot == 4


def test_configured_wizard_default_is_not_the_mock() -> None:
    """The resolved wizard.default_model must be a real model, never TEST."""
    assert get_new_story_model() != "TEST"


def test_resolve_wizard_model_explicit_override_wins() -> None:
    assert resolve_wizard_model("TEST", get_new_story_model()) == "TEST"


def test_resolve_wizard_model_falls_back_to_slot_stamp() -> None:
    """Omitted request model resolves to the slot's stamped (locked) model."""
    assert resolve_wizard_model(None, "TEST") == "TEST"


def test_resolve_wizard_model_falls_back_to_configured_default() -> None:
    resolved = resolve_wizard_model(None, None)
    assert resolved == get_new_story_model()
    assert resolved != "TEST"


def test_omitted_model_is_never_a_lock_conflict() -> None:
    """Normal UI requests (no model) can never trip the 409 model lock."""
    assert wizard_model_lock_candidate(None, "slot-model") is False
    assert wizard_model_lock_candidate(None, None) is False


def test_matching_override_is_not_a_lock_conflict() -> None:
    assert wizard_model_lock_candidate("slot-model", "slot-model") is False


def test_differing_override_is_a_lock_conflict_candidate() -> None:
    assert wizard_model_lock_candidate("other-model", "slot-model") is True
