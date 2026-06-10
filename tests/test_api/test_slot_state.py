"""Tests for slot-state narrative resolution around Retrograde chunks."""

from __future__ import annotations

import json
from typing import Any, Optional

from nexus.agents.orrery.retrograde_markers import (
    RETROGRADE_PROLOGUE_MARKER,
    RETROGRADE_SUMMARY_MARKER,
)
from nexus.api.slot_state import _get_narrative_state


class FakeSlotStateCursor:
    """Cursor double: empty incubator plus a scripted latest-chunk result."""

    def __init__(self, chunk_rows: list[dict[str, Any]]):
        self.chunk_rows = chunk_rows
        self.chunk_queries: list[tuple[str, Any]] = []
        self._result: list[dict[str, Any]] = []

    def execute(self, sql: str, params: Optional[Any] = None) -> None:
        if "FROM incubator" in sql:
            self._result = []
        elif "FROM narrative_chunks" in sql:
            self.chunk_queries.append((sql, params))
            self._result = list(self.chunk_rows)
        else:
            raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchone(self) -> Optional[dict[str, Any]]:
        return self._result[0] if self._result else None


def test_narrative_state_excludes_retrograde_chunks_from_resume_surface() -> None:
    """The latest-chunk query filters Retrograde prologue/summary chunks.

    Without the filter, a freshly transitioned slot (Retrograde history
    committed, no play chunks yet) would resolve a generated-history summary
    chunk as the continuation parent and skip narrative bootstrap.
    """

    cur = FakeSlotStateCursor(chunk_rows=[])
    state = _get_narrative_state(cur)

    # Bootstrap signal: no eligible chunk means chunk 0.
    assert state.current_chunk_id == 0
    assert state.has_pending is False

    sql, params = cur.chunk_queries[0]
    assert "authorial_directives" in sql
    assert params["retrograde_prologue_marker"] == json.dumps(
        [RETROGRADE_PROLOGUE_MARKER]
    )
    assert params["retrograde_summary_marker"] == json.dumps(
        [RETROGRADE_SUMMARY_MARKER]
    )


def test_narrative_state_returns_latest_play_chunk() -> None:
    """Ordinary play chunks still resolve as the continuation parent."""

    cur = FakeSlotStateCursor(
        chunk_rows=[{"id": 42, "raw_text": "The tram lurches.", "choice_object": None}]
    )
    state = _get_narrative_state(cur)

    assert state.current_chunk_id == 42
    assert state.storyteller_text == "The tram lurches."
