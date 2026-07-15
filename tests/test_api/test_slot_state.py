"""Pure tests for slot-state narrative resume semantics."""

from __future__ import annotations

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
