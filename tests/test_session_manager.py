"""Unit tests for the storyteller session manager."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from nexus.api.session_manager import SessionManager, SessionNotFoundError, TurnRecord


def test_create_and_persist_session(tmp_path: Path) -> None:
    manager = SessionManager(base_path=tmp_path)
    metadata = manager.create_session(session_name="Test", initial_context="Once upon a time")

    assert metadata.session_id
    assert metadata.session_name == "Test"
    assert "T" in metadata.created_at  # ISO formatted timestamp

    listed = manager.list_sessions()
    assert len(listed) == 1
    assert listed[0]["session_name"] == "Test"

    turn = TurnRecord(
        turn_id="turn-1",
        timestamp=datetime.utcnow().isoformat(),
        user_input="Hello",
        response={"narrative": {"text": "World"}},
        options={"temperature": 0.8},
        phase_states={"apex_generation": {"success": True}},
        memory_state={"pass1": {"baseline_chunks": []}},
    )

    manager.append_turn(metadata.session_id, turn, context_snapshot={"warm_slice": []})

    history = manager.get_history(metadata.session_id, limit=5, offset=0)
    assert len(history) == 1
    assert history[0]["user_input"] == "Hello"
    assert history[0]["response"]["narrative"]["text"] == "World"

    context = manager.load_latest_context(metadata.session_id)
    assert context["warm_slice"] == []
    assert context["turn_id"] == "turn-1"

    replacement = TurnRecord(
        turn_id="turn-1",
        timestamp=datetime.utcnow().isoformat(),
        user_input="Hello again",
        response={"narrative": {"text": "Universe"}},
        options={},
        phase_states={},
        memory_state={},
    )

    manager.replace_last_turn(metadata.session_id, replacement, context_snapshot={"warm_slice": [1]})
    updated_history = manager.get_history(metadata.session_id, limit=5, offset=0)
    assert updated_history[0]["response"]["narrative"]["text"] == "Universe"

    state = manager.get_session_state(metadata.session_id)
    assert state["turn_count"] == 1
    assert state["last_turn"]["user_input"] == "Hello again"

    manager.delete_session(metadata.session_id)
    with pytest.raises(SessionNotFoundError):
        manager.load_metadata(metadata.session_id)


def test_history_bounds(tmp_path: Path) -> None:
    manager = SessionManager(base_path=tmp_path)
    metadata = manager.create_session()

    with pytest.raises(SessionNotFoundError):
        manager.get_history("missing", limit=1, offset=0)

    history = manager.get_history(metadata.session_id, limit=5, offset=0)
    assert history == []

