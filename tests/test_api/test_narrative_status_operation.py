"""The durable attempt routes name what started each attempt.

The reader tells a failed re-roll (whose pending draft survives) from a failed
continuation by this field. PostgreSQL coverage of the real rows lives in
test_acceptance_staging_pg.py; here the database read is the only double.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nexus.api import narrative


def _session_row(operation: str) -> dict[str, Any]:
    """Return one narrative_generation_sessions row as read_generation_session does."""
    now = datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc)
    return {
        "session_id": "regen-13",
        "operation": operation,
        "status": "error",
        "phase": "writer",
        "terminal_outcome": "error",
        "replaced_by_session_id": None,
        "error_class": "WireContractViolation",
        "error": "Writer refused the draft",
        "heartbeat_at": now,
        "expires_at": None,
        "chunk_id": None,
        "parent_chunk_id": 9,
        "created_at": now,
    }


@pytest.mark.parametrize("operation", ["continue", "regenerate"])
@pytest.mark.parametrize(
    "path", ["/api/narrative/active", "/api/narrative/status/regen-13"]
)
def test_attempt_routes_expose_the_operation(
    monkeypatch: pytest.MonkeyPatch, operation: str, path: str
) -> None:
    """Both the latest-attempt and per-session reads carry the operation."""
    monkeypatch.setattr(
        narrative,
        "get_db_connection",
        lambda _slot: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(
        narrative,
        "read_generation_session",
        lambda _conn, session_id=None: _session_row(operation),
    )

    response = TestClient(narrative.app).get(path, params={"slot": 4})

    assert response.status_code == 200
    assert response.json()["operation"] == operation


def test_attempt_routes_reject_an_unknown_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operation outside the schema's CHECK constraint is not reported."""
    monkeypatch.setattr(
        narrative,
        "get_db_connection",
        lambda _slot: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(
        narrative,
        "read_generation_session",
        lambda _conn, session_id=None: _session_row("retry"),
    )

    with pytest.raises(ValidationError, match="operation"):
        TestClient(narrative.app).get("/api/narrative/active", params={"slot": 4})
