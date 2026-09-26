"""Pure tests for slot-state narrative resume semantics."""

from __future__ import annotations

import pytest

from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER
from nexus.api.slot_state import (
    _LATEST_PLAYABLE_CHUNK_SQL,
    _narrative_state_from_committed_chunk,
)


def test_latest_resume_query_excludes_only_the_retrograde_prologue() -> None:
    """A fresh post-transition slot bootstraps past its synthetic FK anchor."""

    assert RETROGRADE_PROLOGUE_MARKER in _LATEST_PLAYABLE_CHUNK_SQL
    assert "orrery:retrograde_event_summary" not in _LATEST_PLAYABLE_CHUNK_SQL
    assert "authorial_directives" in _LATEST_PLAYABLE_CHUNK_SQL


def test_no_playable_chunk_returns_bootstrap_state() -> None:
    state = _narrative_state_from_committed_chunk(None)

    assert state.current_chunk_id == 0
    assert state.has_pending is False
    assert state.storyteller_text is None
    assert state.choices == []


def test_latest_playable_chunk_returns_resume_state() -> None:
    state = _narrative_state_from_committed_chunk(
        {
            "id": 42,
            "raw_text": "The tram lurches.",
            "choice_object": {"presented": ["Brace", "Jump"]},
        }
    )

    assert state.current_chunk_id == 42
    assert state.storyteller_text == "The tram lurches."
    assert state.choices == ["Brace", "Jump"]


def test_slot_endpoint_includes_creation_identity_for_reader_drafts(
    monkeypatch,
) -> None:
    """The reader gets a stable story identity separately from its frontier."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nexus.api import slot_endpoints, slot_state

    identity = "2026-09-25T06:00:00+00:00"
    state = slot_state.SlotState(
        slot=4,
        is_empty=False,
        is_wizard_mode=False,
        wizard_state=None,
        narrative_state=_narrative_state_from_committed_chunk(
            {"id": 42, "raw_text": "The tram lurches.", "choice_object": None}
        ),
        model="TEST",
        story_id=identity,
    )
    monkeypatch.setattr(slot_state, "get_slot_state", lambda _slot: state)
    app = FastAPI()
    app.include_router(slot_endpoints.router)
    with TestClient(app) as client:
        response = client.get("/api/slot/4/state")
    assert response.status_code == 200
    assert response.json()["story_id"] == identity
    assert response.json()["current_chunk_id"] == 42
