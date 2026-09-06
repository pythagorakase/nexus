"""Privacy regressions for the package-exported Storyteller session API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from nexus.api.session_manager import SessionManager
from nexus.api.storyteller import app, get_lore, get_session_manager


def test_story_context_storage_and_all_read_endpoints_exclude_correspondence(
    tmp_path: Path,
) -> None:
    """Append and regenerate structurally omit the private context key."""

    manager = SessionManager(base_path=tmp_path)
    app.dependency_overrides[get_session_manager] = lambda: manager
    client = TestClient(app)
    try:
        created = client.post("/api/story/session/create", json={})
        assert created.status_code == 200
        session_id = created.json()["session_id"]

        context_payload = {
            "storyteller_correspondence": "WRITER-GAIA-CONSPIRACY-MUST-NEVER-PERSIST",
            "public_marker": "safe diagnostic context",
        }
        public_response = {
            "narrative": "The public clock advances one minute.",
            "choices": ["Wait.", "Leave."],
        }
        asyncio.run(
            manager.append_turn(
                session_id,
                user_input="Continue.",
                response=public_response,
                context_payload=context_payload,
            )
        )

        context = client.get(f"/api/story/context/{session_id}")
        assert context.status_code == 200
        assert context.json()["public_marker"] == (
            "safe diagnostic context"
        )

        context_payload["storyteller_correspondence"] = (
            "REGENERATED-CONSPIRACY-MUST-NEVER-PERSIST"
        )
        asyncio.run(
            manager.replace_last_turn(
                session_id,
                user_input="Continue.",
                response=public_response,
                context_payload=context_payload,
            )
        )

        payloads = [
            client.get(f"/api/story/context/{session_id}").json(),
            client.get(f"/api/story/session/{session_id}").json(),
            client.get(f"/api/story/history/{session_id}").json(),
        ]
        serialized = json.dumps(payloads)
        assert "WRITER-GAIA-CONSPIRACY" not in serialized
        assert "REGENERATED-CONSPIRACY" not in serialized

        context_files = list((tmp_path / session_id / "context").glob("*.json"))
        assert len(context_files) == 1
        assert "storyteller_correspondence" not in context_files[0].read_text()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("operation", ["turn", "regenerate"])
def test_legacy_generation_rejects_before_session_or_provider_work(
    operation: str,
) -> None:
    """A conversation ID cannot masquerade as a durable generation attempt."""

    def unexpected_dependency() -> None:
        pytest.fail("Retired generation must not initialize LORE or session storage")

    app.dependency_overrides[get_lore] = unexpected_dependency
    app.dependency_overrides[get_session_manager] = unexpected_dependency
    try:
        response = TestClient(app).post(
            f"/api/story/{operation}",
            json={"session_id": "conversation-id", "user_input": "Continue."},
        )
        assert response.status_code == 410, response.text
        assert "/api/narrative/" in response.json()["detail"]
        assert "explicit slot" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
