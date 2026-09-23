"""Request-boundary validation for wizard chat turns."""

from contextlib import closing

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api.new_story_cache import init_cache
from nexus.api.wizard_chat import router
from tests.pg_fixtures import connect


def _client_with_wizard_state(
    dbname: str,
    *,
    setting_genre: str | None,
    character_name: str | None,
    traits_confirmed: bool,
) -> TestClient:
    """Mount the endpoint with phase/trait state persisted in the real cache."""
    init_cache(dbname, thread_id="thread-test", target_slot=4)
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE assets.new_story_creator
            SET setting_genre = %s, character_name = %s, traits_confirmed = %s
            WHERE id = TRUE
            """,
            (setting_genre, character_name, traits_confirmed),
        )
        cur.execute("UPDATE assets.traits SET rationale = NULL WHERE id = 11")
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


@pytest.mark.requires_postgres
def test_repeated_trait_confirmation_reports_wildcard_state(
    offline_gate_db: str,
) -> None:
    """A confirmation repeated after trait commit must never reach inference."""
    client = _client_with_wizard_state(
        offline_gate_db,
        setting_genre="fantasy",
        character_name="Fixture Player",
        traits_confirmed=True,
    )

    response = client.post(
        "/api/story/new/chat",
        json={"slot": 4, "message": "", "trait_choice": 0},
    )

    assert response.status_code == 409
    assert "phase 'character', subphase 'wildcard'" in response.json()["detail"]
    assert "non-empty message" in response.json()["detail"]


@pytest.mark.requires_postgres
def test_trait_choice_outside_character_reports_current_state(
    offline_gate_db: str,
) -> None:
    """A trait action during another phase must fail before provider setup."""
    client = _client_with_wizard_state(
        offline_gate_db,
        setting_genre=None,
        character_name=None,
        traits_confirmed=False,
    )

    response = client.post(
        "/api/story/new/chat",
        json={"slot": 4, "message": "", "trait_choice": 1},
    )

    assert response.status_code == 409
    assert "phase 'setting', subphase 'none'" in response.json()["detail"]
    assert "non-empty message" in response.json()["detail"]
