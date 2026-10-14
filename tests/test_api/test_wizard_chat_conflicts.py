"""A generated wizard artifact must report stale drafts as a 409, never success."""

from contextlib import closing, contextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.tools import DeferredToolRequests
import pytest

from nexus.api import new_story_cache, wizard_chat
from nexus.api.conversations import ConversationsClient, new_conversation_id
from nexus.api.new_story_cache import WizardCache
from tests.pg_fixtures import connect

pytestmark = pytest.mark.requires_postgres


@pytest.mark.parametrize(
    ("changed_at", "detail"),
    [
        ("session", "The wizard session changed."),
        (
            "artifact",
            "This artifact changed before its response arrived. "
            "Resume to review the current draft.",
        ),
        (
            "write_lock",
            "The wizard changed while this response was being generated. "
            "Resume before retrying.",
        ),
    ],
)
def test_generated_artifact_ends_with_conflict(
    monkeypatch, offline_gate_db: str, seed_wizard_cache, changed_at: str, detail: str
) -> None:
    """Concurrent edits during generation must yield recovery, never stale success."""
    cache = seed_wizard_cache(
        WizardCache(choices=["Current choice"], choices_recorded=True)
    )
    storage = ConversationsClient(offline_gate_db)
    thread_id = cache.thread_id
    storage.add_message(thread_id, "assistant", "Welcome")

    def update(sql: str, values: tuple = ()) -> None:
        with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
            cur.execute(sql, values)

    class Agent:
        async def run(self, *args, deps, **kwargs):
            update(
                "UPDATE assets.new_story_creator SET setting_genre = 'fantasy', "
                "setting_world_name = 'Original draft' WHERE id = TRUE"
            )
            generated = new_story_cache.read_cache(offline_gate_db)
            assert generated is not None
            deps.last_tool_result = {
                "phase_complete": True,
                "choices": ["Stale artifact choice"],
                **generated.confirmation_metadata(),
            }
            if changed_at == "session":
                update(
                    "UPDATE assets.new_story_creator SET thread_id = %s "
                    "WHERE id = TRUE",
                    (new_conversation_id(),),
                )
            elif changed_at == "artifact":
                update(
                    "UPDATE assets.new_story_creator "
                    "SET setting_world_name = 'Newer draft' WHERE id = TRUE"
                )
            return SimpleNamespace(output=DeferredToolRequests())

    original_guard = wizard_chat.guarded_wizard_write

    @contextmanager
    def concurrent_change_before_lock(dbname, expected):
        # Schedule a real committed edit after the artifact response's first read;
        # the unchanged production guard must detect it under the row lock.
        if changed_at == "write_lock":
            update(
                "UPDATE assets.new_story_creator "
                "SET setting_world_name = 'Newer draft' WHERE id = TRUE"
            )
        with original_guard(dbname, expected):
            yield

    monkeypatch.setattr(
        wizard_chat, "guarded_wizard_write", concurrent_change_before_lock
    )
    monkeypatch.setattr(wizard_chat, "get_wizard_agent", lambda context: Agent())
    monkeypatch.setattr(
        wizard_chat,
        "build_pydantic_ai_model_with_provider",
        lambda model: (None, "test"),
    )
    monkeypatch.setattr(wizard_chat, "record_pydantic_ai_result", lambda *a, **k: None)
    app = FastAPI()
    app.include_router(wizard_chat.router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/story/new/chat", json={"slot": 4, "message": "A harbor city"}
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == detail
    persisted = new_story_cache.read_cache(offline_gate_db)
    assert persisted is not None and persisted.choices == ["Current choice"]
    assert [
        item["content"]
        for item in storage.list_messages(thread_id, limit=0)
        if item["role"] == "assistant"
    ] == ["Welcome"]
