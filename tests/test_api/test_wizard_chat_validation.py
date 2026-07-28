"""Request-boundary validation for wizard chat turns."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api.wizard_chat import router


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
