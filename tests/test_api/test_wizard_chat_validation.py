"""Request-boundary validation for wizard chat turns."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api.slot_state import SlotState, WizardState
from nexus.api.wizard_chat import router


def _client_with_wizard_state(
    monkeypatch: pytest.MonkeyPatch,
    *,
    phase: str,
    has_concept: bool,
    has_traits: bool,
    has_wildcard: bool,
) -> TestClient:
    """Mount the real endpoint with a deterministic persisted-state boundary."""
    from nexus.api import slot_state

    state = SlotState(
        slot=4,
        is_empty=False,
        is_wizard_mode=True,
        wizard_state=WizardState(
            phase=phase,
            thread_id="thread-test",
            choices=[],
            has_concept=has_concept,
            has_traits=has_traits,
            has_wildcard=has_wildcard,
        ),
        narrative_state=None,
        model="TEST",
    )
    monkeypatch.setattr(slot_state, "get_slot_state", lambda _slot: state)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_wizard_chat_rejects_blank_message_locally() -> None:
    """Blank conversation input must fail before reaching a model provider."""
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).post(
        "/api/story/new/chat",
        json={"slot": 4, "message": "   "},
    )

    assert response.status_code == 422
    assert "Wizard message must be non-empty" in response.text


def test_wizard_chat_allows_blank_deterministic_trait_action() -> None:
    """Trait toggles and confirmation intentionally carry no user message."""
    from nexus.api.narrative_schemas import ChatRequest

    request = ChatRequest(slot=4, message="", trait_choice=0)

    assert request.trait_choice == 0


def test_wizard_chat_allows_blank_accept_fate_action() -> None:
    """Accept-fate requests use a local synthetic prompt instead of a message."""
    from nexus.api.narrative_schemas import ChatRequest

    request = ChatRequest(slot=4, message="", accept_fate=True)

    assert request.accept_fate is True


def test_repeated_trait_confirmation_reports_wildcard_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A confirmation repeated after trait commit must never reach inference."""
    client = _client_with_wizard_state(
        monkeypatch,
        phase="character",
        has_concept=True,
        has_traits=True,
        has_wildcard=False,
    )

    response = client.post(
        "/api/story/new/chat",
        json={"slot": 4, "message": "", "trait_choice": 0},
    )

    assert response.status_code == 409
    assert "phase 'character', subphase 'wildcard'" in response.json()["detail"]
    assert "non-empty message" in response.json()["detail"]


def test_trait_choice_outside_character_reports_current_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A trait action during another phase must fail before provider setup."""
    client = _client_with_wizard_state(
        monkeypatch,
        phase="setting",
        has_concept=False,
        has_traits=False,
        has_wildcard=False,
    )

    response = client.post(
        "/api/story/new/chat",
        json={"slot": 4, "message": "", "trait_choice": 1},
    )

    assert response.status_code == 409
    assert "phase 'setting', subphase 'none'" in response.json()["detail"]
    assert "non-empty message" in response.json()["detail"]
