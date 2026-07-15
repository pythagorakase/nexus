"""
Regression tests for wizard default-model resolution.

The wizard UI no longer carries a model picker; clients omit `model` and the
backend resolves it: explicit request override -> slot's stamped model
(locked at setup start) -> configured wizard default from nexus.toml. The
mock TEST server must never be selected implicitly.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nexus.api import new_story_flow, setup_endpoints, storyteller
from nexus.api.config_utils import get_new_story_model
from nexus.api.narrative_schemas import ChatRequest, StartSetupRequest
from nexus.api.new_story_flow import resolve_setup_model
from nexus.api.wizard_chat import resolve_wizard_model, wizard_model_lock_candidate


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


def test_setup_model_explicit_request_wins() -> None:
    assert (
        resolve_setup_model(
            "explicit-model",
            "operator-model",
            default_slot_model="fresh-placeholder",
            wizard_default_model="wizard-default",
        )
        == "explicit-model"
    )


def test_setup_model_preserves_operator_slot_model() -> None:
    assert (
        resolve_setup_model(
            None,
            "operator-model",
            default_slot_model="fresh-placeholder",
            wizard_default_model="wizard-default",
        )
        == "operator-model"
    )


def test_setup_model_treats_empty_request_as_omitted() -> None:
    assert (
        resolve_setup_model(
            "",
            "operator-model",
            default_slot_model="fresh-placeholder",
            wizard_default_model="wizard-default",
        )
        == "operator-model"
    )


@pytest.mark.parametrize("slot_model", [None, "", "fresh-placeholder"])
def test_setup_model_uses_wizard_default_only_for_fresh_slot(
    slot_model: str | None,
) -> None:
    assert (
        resolve_setup_model(
            None,
            slot_model,
            default_slot_model="fresh-placeholder",
            wizard_default_model="wizard-default",
        )
        == "wizard-default"
    )


@pytest.mark.parametrize(
    ("requested_model", "slot_model", "expected_model"),
    [
        ("explicit-model", "operator-model", "explicit-model"),
        (None, "operator-model", "operator-model"),
        (None, "fresh-placeholder", "wizard-default"),
    ],
)
def test_start_setup_persists_resolved_model(
    monkeypatch: pytest.MonkeyPatch,
    requested_model: str | None,
    slot_model: str,
    expected_model: str,
) -> None:
    """The core applies precedence once, then persists the selected model."""
    clients: list[str] = []
    upserts: list[dict[str, Any]] = []

    class FakeConnection:
        def close(self) -> None:
            """Mirror the psycopg connection close surface."""

    class FakeConversationsClient:
        def __init__(self, model: str) -> None:
            clients.append(model)

        def create_thread(self) -> str:
            """Return a deterministic thread without a provider call."""
            return "thread-explicit"

    monkeypatch.setattr(
        new_story_flow.psycopg2,
        "connect",
        lambda **_kwargs: FakeConnection(),
    )
    monkeypatch.setattr(new_story_flow, "slot_dbname", lambda _slot: "save_test")
    monkeypatch.setattr(
        new_story_flow,
        "get_slot_model",
        lambda _slot, dbname=None: slot_model,
    )
    monkeypatch.setattr(new_story_flow, "clear_cache", lambda _dbname: None)
    monkeypatch.setattr(new_story_flow, "init_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(new_story_flow, "clear_active", lambda _dbname: None)
    monkeypatch.setattr(
        new_story_flow,
        "upsert_slot",
        lambda slot, **kwargs: upserts.append({"slot": slot, **kwargs}),
    )
    monkeypatch.setattr(new_story_flow, "ConversationsClient", FakeConversationsClient)
    monkeypatch.setattr(
        "nexus.config.load_settings",
        lambda: SimpleNamespace(
            global_=SimpleNamespace(
                model=SimpleNamespace(default_slot_model="fresh-placeholder")
            ),
            wizard=SimpleNamespace(default_model="wizard-default"),
        ),
    )

    thread_id = new_story_flow.start_setup(4, model=requested_model)

    assert thread_id == "thread-explicit"
    assert clients == [expected_model]
    assert upserts == [
        {
            "slot": 4,
            "is_active": True,
            "model": expected_model,
            "dbname": "save_test",
        }
    ]


def test_setup_endpoint_passes_omitted_model_to_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The HTTP layer must not replace omission with the roster default."""
    starts: list[tuple[int, str | None]] = []

    class FakeConversationsClient:
        def __init__(self, model: str) -> None:
            assert model == "operator-model"

        def add_message(self, *_args: Any) -> None:
            """Accept welcome-message seeding without a provider call."""

    def fake_start_setup(slot: int, model: str | None) -> str:
        starts.append((slot, model))
        return "thread-operator"

    monkeypatch.setattr(
        setup_endpoints,
        "start_setup",
        fake_start_setup,
    )
    monkeypatch.setattr(
        setup_endpoints,
        "get_slot_model",
        lambda _slot, dbname=None: "operator-model",
    )
    monkeypatch.setattr(setup_endpoints, "slot_dbname", lambda _slot: "save_test")
    monkeypatch.setattr(setup_endpoints, "ConversationsClient", FakeConversationsClient)
    monkeypatch.setattr(
        setup_endpoints, "write_wizard_choices", lambda *_args, **_kwargs: None
    )

    app = FastAPI()
    app.include_router(setup_endpoints.router)
    response = TestClient(app).post("/api/story/new/setup/start", json={"slot": 4})

    assert response.status_code == 200
    assert starts == [(4, None)]
    assert response.json()["model"] == "operator-model"


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
    assert resolve_wizard_model("explicit-model", "slot-model") == "explicit-model"


def test_resolve_wizard_model_falls_back_to_slot_stamp() -> None:
    """Omitted request model resolves to the slot's stamped (locked) model."""
    assert resolve_wizard_model(None, "slot-model") == "slot-model"


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
