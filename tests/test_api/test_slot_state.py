"""Pure tests for slot-state narrative resume semantics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER
from nexus.api.narrative_lease import RetryableFailure
from nexus.api.slot_state import (
    _LATEST_PLAYABLE_CHUNK_SQL,
    _get_narrative_state,
    _narrative_state_from_committed_chunk,
)


def test_latest_resume_query_excludes_only_the_retrograde_prologue() -> None:
    """A fresh post-transition slot bootstraps past its synthetic FK anchor."""

    assert RETROGRADE_PROLOGUE_MARKER in _LATEST_PLAYABLE_CHUNK_SQL
    assert "orrery:retrograde_event_summary" not in _LATEST_PLAYABLE_CHUNK_SQL
    assert "authorial_directives" in _LATEST_PLAYABLE_CHUNK_SQL


def test_latest_resume_query_reads_the_recorded_action() -> None:
    """A consumed menu is recognized from the chunk's recorded action."""

    assert "nc.choice_text" in _LATEST_PLAYABLE_CHUNK_SQL


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
            "choice_text": None,
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
            {
                "id": 42,
                "raw_text": "The tram lurches.",
                "choice_object": None,
                "choice_text": None,
            }
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


# ---------------------------------------------------------------------------
# #952: a durable failed continuation resumes as recovery, not as live choices
# ---------------------------------------------------------------------------

STAGING_ERROR = (
    "Unresolved place state update name 'Machine-Shop'; new places must be "
    "declared through new_entities in the same turn."
)
ACTION = "Record both conditions—don't imply agreement.\nAsk for an inspection."
MENU = {
    "presented": ["Agree.", "Record the joint plan.", "Walk away."],
    "selected": {"label": "freeform", "text": ACTION, "edited": False},
}


def _frontier(**overrides: Any) -> Dict[str, Any]:
    """The committed chunk that recorded the player's action (id 9)."""
    return {
        "id": 9,
        "raw_text": "The hearing stalls.",
        "choice_object": MENU,
        "choice_text": ACTION,
        "world_time": None,
    } | overrides


def _failed(**overrides: Any) -> Dict[str, Any]:
    """The latest durable attempt: both calls accounted, staging rejected."""
    return {
        "session_id": "a3ca073b-c2a0-45d2-b983-43e2c7770fb1",
        "status": "error",
        "terminal_outcome": "error",
        "parent_chunk_id": 9,
        "replaced_by_session_id": None,
        "error": STAGING_ERROR,
        "error_class": "WireContractViolation",
    } | overrides


class DurableSlotCursor:
    """Serve one slot's durable rows to the production resolvers, read-only."""

    def __init__(
        self,
        *,
        chunk: Optional[Dict[str, Any]],
        session: Optional[Dict[str, Any]],
        pending: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.rows = {
            "narrative_generation_sessions": session,
            "incubator": pending,
            "narrative_chunks": chunk,
        }
        self.queries: List[str] = []
        self.result: Optional[Dict[str, Any]] = None

    def execute(self, query: str, params: Any = None) -> None:
        normalized = " ".join(query.split())
        self.queries.append(normalized)
        for table, row in self.rows.items():
            if f"FROM {table}" in normalized:
                self.result = row
                return
        raise AssertionError(f"Unexpected slot-state query: {normalized}")

    def fetchone(self) -> Optional[Dict[str, Any]]:
        return self.result


def test_failed_continuation_resumes_as_recovery_without_consumed_choices() -> None:
    """has_pending=false after a staging failure reports recovery, not a menu."""
    cursor = DurableSlotCursor(chunk=_frontier(), session=_failed())

    state = _get_narrative_state(cursor)

    assert (state.current_chunk_id, state.has_pending, state.session_id) == (
        9,
        False,
        None,
    )
    assert state.choices == []
    assert state.recorded_action == ACTION
    assert state.recovery == RetryableFailure(
        session_id="a3ca073b-c2a0-45d2-b983-43e2c7770fb1",
        parent_chunk_id=9,
        error=STAGING_ERROR,
        error_class="WireContractViolation",
    )
    # Resume state only reads; the retry route alone locks and writes.
    assert all(query.startswith("SELECT") for query in cursor.queries)
    assert not any("FOR UPDATE" in query for query in cursor.queries)


@pytest.mark.parametrize(
    "session",
    [
        _failed(replaced_by_session_id="retry-session"),
        _failed(session_id="retry-session", status="initiated", terminal_outcome=None),
        _failed(status="complete", terminal_outcome="discarded"),
        _failed(parent_chunk_id=8),
        _failed(parent_chunk_id=None),
        None,
    ],
    ids=["replaced", "retry-running", "discarded", "older-parent", "unbound", "none"],
)
def test_stale_or_ineligible_failure_is_not_offered_for_retry(
    session: Optional[Dict[str, Any]],
) -> None:
    """Only the attempt the retry route would accept becomes resume recovery."""
    state = _get_narrative_state(DurableSlotCursor(chunk=_frontier(), session=session))

    assert state.recovery is None
    assert state.choices == []
    assert state.recorded_action == ACTION


def test_cleared_action_reopens_the_menu_without_recovery() -> None:
    """After undo or restart recovery clears the action, the menu is live again."""
    state = _get_narrative_state(
        DurableSlotCursor(
            chunk=_frontier(choice_text=None, choice_object=dict(MENU, selected=None)),
            session=_failed(),
        )
    )

    assert state.recovery is None
    assert state.recorded_action is None
    assert state.choices == MENU["presented"]


def test_pending_result_supersedes_recovery() -> None:
    """A staged draft is the live decision; no retry is offered beside it."""
    state = _get_narrative_state(
        DurableSlotCursor(
            chunk=_frontier(),
            session=_failed(),
            pending={
                "session_id": "pending-10",
                "chunk_id": 10,
                "storyteller_text": "The inspection begins.",
                "choice_object": {"presented": ["Follow.", "Wait."]},
            },
        )
    )

    assert (state.has_pending, state.session_id) == (True, "pending-10")
    assert state.choices == ["Follow.", "Wait."]
    assert state.recovery is None


def _failed_frontier_response(monkeypatch, *, locked: bool) -> Dict[str, Any]:
    """Serve a failed frontier through the slot route with a known lock state."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nexus.api import slot_endpoints, slot_state

    narrative_state = _get_narrative_state(
        DurableSlotCursor(chunk=_frontier(), session=_failed())
    )
    state = slot_state.SlotState(
        slot=4,
        is_empty=False,
        is_wizard_mode=False,
        wizard_state=None,
        narrative_state=narrative_state,
        model="TEST",
        story_id="player:1:2026-09-25T06:00:00+00:00",
    )
    lock_checks: List[tuple[int, Optional[str]]] = []

    def is_slot_locked(slot: int, dbname: Optional[str] = None) -> bool:
        lock_checks.append((slot, dbname))
        return locked

    monkeypatch.setattr(slot_state, "get_slot_state", lambda _slot: state)
    monkeypatch.setattr(slot_endpoints, "is_slot_locked", is_slot_locked)
    app = FastAPI()
    app.include_router(slot_endpoints.router)
    with TestClient(app) as client:
        response = client.get("/api/slot/4/state")
    assert response.status_code == 200
    assert lock_checks == [(4, "save_04")]
    return response.json()


def test_slot_endpoint_reports_recovery_for_the_failed_frontier(monkeypatch) -> None:
    """The reader and CLI receive the terminal-failure fact from resume state."""
    body = _failed_frontier_response(monkeypatch, locked=False)

    assert body["has_pending"] is False
    assert body["session_id"] is None
    assert body["choices"] == []
    assert body["recovery"] == {
        "session_id": "a3ca073b-c2a0-45d2-b983-43e2c7770fb1",
        "parent_chunk_id": 9,
        "error": STAGING_ERROR,
        "error_class": "WireContractViolation",
    }


def test_locked_slot_never_offers_a_retry_the_route_refuses(monkeypatch) -> None:
    """POST /api/narrative/retry rejects locked slots, so none is advertised."""
    body = _failed_frontier_response(monkeypatch, locked=True)

    assert body["recovery"] is None
    assert body["choices"] == []
    assert body["has_pending"] is False
