"""Tests for MEMNON direct chunk retrieval."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from nexus.agents.memnon.memnon import MEMNON


class CapturingSession:
    """Minimal SQLAlchemy session double for direct chunk lookup tests."""

    def __init__(self, row: Any = None, error: Exception | None = None) -> None:
        self.row = row
        self.error = error
        self.query_text = ""
        self.params: dict[str, Any] = {}

    def __enter__(self) -> "CapturingSession":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, query: Any, params: dict[str, Any]) -> "CapturingSession":
        if self.error:
            raise self.error
        self.query_text = str(query)
        self.params = params
        return self

    def fetchone(self) -> Any:
        return self.row


def _memnon_with_session(session: CapturingSession) -> MEMNON:
    """Build a MEMNON instance without running heavyweight initialization."""
    memnon = MEMNON.__new__(MEMNON)
    memnon.Session = lambda: session
    return memnon


def test_get_chunk_by_id_uses_place_references_for_header() -> None:
    """Direct chunk lookup should use current place reference schema."""
    row = SimpleNamespace(
        id=1,
        raw_text="Rain comes down like static.",
        season=1,
        episode=1,
        scene=1,
        world_time="Night",
        place_names="Halcyon Row, Metro Entrance",
    )
    session = CapturingSession(row=row)
    memnon = _memnon_with_session(session)

    chunk = memnon.get_chunk_by_id(1)

    assert chunk is not None
    assert chunk["id"] == 1
    assert "Halcyon Row, Metro Entrance" in chunk["header"]
    assert "place_chunk_references pcr" in session.query_text
    assert "LEFT JOIN places p ON pcr.place_id = p.id" in session.query_text
    assert "cm.place" not in session.query_text
    assert session.params == {"chunk_id": 1}


def test_get_chunk_by_id_logs_fetch_errors_without_instance_logger(
    caplog,
) -> None:
    """Fetch failures should log the real error instead of masking it."""
    session = CapturingSession(error=RuntimeError("database boom"))
    memnon = _memnon_with_session(session)

    with caplog.at_level(logging.ERROR, logger="nexus.memnon"):
        chunk = memnon.get_chunk_by_id(1)

    assert chunk is None
    assert "Error fetching chunk 1: database boom" in caplog.text
