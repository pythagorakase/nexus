"""Privacy regressions for the package-exported Storyteller session API."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from nexus.agents.logon.apex_schema import StorytellerResponseMinimal
from nexus.api.session_manager import SessionManager
from nexus.api.storyteller import app, get_lore, get_session_manager


class _PrivateContextLore:
    """Return public prose while exposing a private generation context internally."""

    def __init__(self) -> None:
        self.secret = "WRITER-GAIA-CONSPIRACY-MUST-NEVER-PERSIST"
        self.turn_context = SimpleNamespace(
            context_payload={
                "storyteller_correspondence": self.secret,
                "public_marker": "safe diagnostic context",
            }
        )

    async def process_turn(self, _user_input: str) -> StorytellerResponseMinimal:
        return StorytellerResponseMinimal(
            narrative="The public clock advances one minute.",
            choices=["Wait.", "Leave."],
        )


def test_story_context_storage_and_all_read_endpoints_exclude_correspondence(
    tmp_path: Path,
) -> None:
    """Append and regenerate structurally omit the private context key."""

    manager = SessionManager(base_path=tmp_path)
    lore = _PrivateContextLore()
    app.dependency_overrides[get_session_manager] = lambda: manager
    app.dependency_overrides[get_lore] = lambda: lore
    client = TestClient(app)
    try:
        created = client.post("/api/story/session/create", json={})
        assert created.status_code == 200
        session_id = created.json()["session_id"]

        turn = client.post(
            "/api/story/turn",
            json={"session_id": session_id, "user_input": "Continue."},
        )
        assert turn.status_code == 200

        context = client.get(f"/api/story/context/{session_id}")
        assert context.status_code == 200
        assert context.json()["context_payload"]["public_marker"] == (
            "safe diagnostic context"
        )

        lore.secret = "REGENERATED-CONSPIRACY-MUST-NEVER-PERSIST"
        lore.turn_context.context_payload["storyteller_correspondence"] = lore.secret
        regenerated = client.post(
            "/api/story/regenerate",
            json={"session_id": session_id},
        )
        assert regenerated.status_code == 200

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
