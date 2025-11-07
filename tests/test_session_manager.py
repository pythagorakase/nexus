"""Unit tests for the storyteller session manager."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from nexus.api.session_manager import (
    SessionManager,
    SessionMetadata,
    SessionNotFoundError,
    SessionState,
    SessionTurn,
)


@pytest.mark.asyncio
async def test_create_and_persist_session(tmp_path: Path) -> None:
    """Test creating a session and persisting data."""
    manager = SessionManager(base_path=tmp_path)

    # Create session
    state = await manager.create_session(
        session_name="Test",
        initial_context="Once upon a time"
    )

    assert state.metadata.session_id
    assert state.metadata.session_name == "Test"
    assert state.metadata.initial_context == "Once upon a time"
    assert isinstance(state.metadata.created_at, datetime)

    # List sessions
    sessions = []
    async for session_metadata in manager.iter_sessions():
        sessions.append(session_metadata)

    assert len(sessions) == 1
    assert sessions[0].session_name == "Test"

    # Add a turn
    turn = await manager.append_turn(
        session_id=state.metadata.session_id,
        user_input="Hello",
        response={"narrative": {"text": "World"}},
        options={"temperature": 0.8},
        context_payload={"warm_slice": []}
    )

    assert turn.turn_id  # Should have a generated turn_id
    assert turn.user_input == "Hello"
    assert turn.response["narrative"]["text"] == "World"

    # Load session state
    loaded_state = await manager.load_session(state.metadata.session_id)
    assert len(loaded_state.turns) == 1
    assert loaded_state.turns[0].user_input == "Hello"
    assert loaded_state.turns[0].response["narrative"]["text"] == "World"

    # Get history
    history = await manager.load_turn_history(
        state.metadata.session_id,
        limit=5,
        offset=0
    )
    assert len(history) == 1
    assert history[0].user_input == "Hello"

    # Replace last turn (regenerate)
    new_turn = await manager.replace_last_turn(
        session_id=state.metadata.session_id,
        user_input="Hello again",
        response={"narrative": {"text": "Universe"}},
        options={},
        context_payload={"warm_slice": [1]}
    )

    assert new_turn.turn_id == turn.turn_id  # Same turn ID
    assert new_turn.user_input == "Hello again"
    assert new_turn.response["narrative"]["text"] == "Universe"

    # Verify replacement
    loaded_state = await manager.load_session(state.metadata.session_id)
    assert len(loaded_state.turns) == 1  # Still 1 turn
    assert loaded_state.turns[0].response["narrative"]["text"] == "Universe"

    # Delete session
    await manager.delete_session(state.metadata.session_id)

    # Verify deletion
    with pytest.raises(SessionNotFoundError):
        await manager.load_session(state.metadata.session_id)


@pytest.mark.asyncio
async def test_history_bounds(tmp_path: Path) -> None:
    """Test history retrieval with various bounds."""
    manager = SessionManager(base_path=tmp_path)
    state = await manager.create_session()

    # Empty history
    history = await manager.load_turn_history(
        state.metadata.session_id,
        limit=5,
        offset=0
    )
    assert history == []

    # Add multiple turns
    for i in range(10):
        await manager.append_turn(
            session_id=state.metadata.session_id,
            user_input=f"Input {i}",
            response={"narrative": {"text": f"Response {i}"}},
        )

    # Test different slices
    history = await manager.load_turn_history(
        state.metadata.session_id,
        limit=3,
        offset=0
    )
    assert len(history) == 3
    assert history[0].user_input == "Input 9"  # Most recent
    assert history[2].user_input == "Input 7"

    history = await manager.load_turn_history(
        state.metadata.session_id,
        limit=3,
        offset=3
    )
    assert len(history) == 3
    assert history[0].user_input == "Input 6"
    assert history[2].user_input == "Input 4"

    # Test offset beyond available turns
    history = await manager.load_turn_history(
        state.metadata.session_id,
        limit=5,
        offset=10
    )
    assert history == []


@pytest.mark.asyncio
async def test_session_not_found(tmp_path: Path) -> None:
    """Test handling of missing sessions."""
    manager = SessionManager(base_path=tmp_path)

    with pytest.raises(SessionNotFoundError):
        await manager.load_session("nonexistent-session")

    with pytest.raises(SessionNotFoundError):
        await manager.load_turn_history("missing", limit=1, offset=0)

    # Delete should raise for missing session
    with pytest.raises(SessionNotFoundError):
        await manager.delete_session("nonexistent-session")


@pytest.mark.asyncio
async def test_update_metadata(tmp_path: Path) -> None:
    """Test metadata updates and phase tracking."""
    manager = SessionManager(base_path=tmp_path)
    state = await manager.create_session(session_name="TestSession")

    # Initial phase should be idle
    assert state.metadata.current_phase == "idle"

    # Update phase
    updated_metadata = await manager.update_metadata(
        state.metadata.session_id,
        current_phase="apex_generation"
    )
    assert updated_metadata.current_phase == "apex_generation"

    # Verify persistence
    loaded_state = await manager.load_session(state.metadata.session_id)
    assert loaded_state.metadata.current_phase == "apex_generation"

    # Finalize turn (should reset to idle)
    await manager.finalize_turn(state.metadata.session_id)
    loaded_state = await manager.load_session(state.metadata.session_id)
    assert loaded_state.metadata.current_phase == "idle"


@pytest.mark.asyncio
async def test_context_pruning(tmp_path: Path) -> None:
    """Test that old context files are pruned."""
    manager = SessionManager(base_path=tmp_path, max_context_files=3)
    state = await manager.create_session()

    # Add more turns than max_context_files
    for i in range(5):
        await manager.append_turn(
            session_id=state.metadata.session_id,
            user_input=f"Input {i}",
            response={"narrative": {"text": f"Response {i}"}},
            context_payload={"turn_number": i}
        )
        await manager.finalize_turn(state.metadata.session_id)

    # Check that only 3 most recent context files exist
    context_dir = manager._context_dir(state.metadata.session_id)
    context_files = list(context_dir.glob("*.json"))
    assert len(context_files) <= 3

    # Verify we have exactly 3 files (the max)
    assert len(context_files) == 3


@pytest.mark.asyncio
async def test_session_id_validation(tmp_path: Path) -> None:
    """Test session ID validation and security."""
    manager = SessionManager(base_path=tmp_path)

    # Valid UUID should work
    state = await manager.create_session()
    assert state.metadata.session_id

    # Path traversal attempts should be rejected
    with pytest.raises(ValueError, match="Invalid session|outside base|invalid characters"):
        await manager.load_session("../etc/passwd")

    with pytest.raises(ValueError, match="Invalid session"):
        await manager.load_session(".")

    with pytest.raises(ValueError, match="Invalid session"):
        await manager.load_session("..")

    # None should be rejected
    with pytest.raises(ValueError, match="required"):
        await manager.load_session(None)


@pytest.mark.asyncio
async def test_concurrent_access(tmp_path: Path) -> None:
    """Test concurrent session access with locks."""
    manager = SessionManager(base_path=tmp_path)
    state = await manager.create_session()

    # Define tasks that would conflict without proper locking
    async def add_turn(turn_num: int):
        await manager.append_turn(
            session_id=state.metadata.session_id,
            user_input=f"Input {turn_num}",
            response={"narrative": {"text": f"Response {turn_num}"}},
        )

    # Run multiple turns concurrently
    tasks = [add_turn(i) for i in range(10)]
    await asyncio.gather(*tasks)

    # Verify all turns were recorded
    loaded_state = await manager.load_session(state.metadata.session_id)
    assert len(loaded_state.turns) == 10

    # Verify no turns were lost due to race conditions
    turn_inputs = {turn.user_input for turn in loaded_state.turns}
    expected_inputs = {f"Input {i}" for i in range(10)}
    assert turn_inputs == expected_inputs