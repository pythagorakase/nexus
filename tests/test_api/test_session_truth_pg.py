"""Durable recovery on real PostgreSQL, with no provider substitutions.

The browser proof uses the repository TEST HTTP provider and a disposable copy
of save_04. Nothing writes to a saved story or calls a paid provider.
"""

from contextlib import closing
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from nexus.api import narrative
from nexus.api.narrative_lease import (
    acquire_generation_lease,
    heartbeat_generation,
    read_generation_session,
)
from tests.pg_fixtures import connect, disposable_slot_database
from tests.scheduler_helpers import route_slot

pytestmark = pytest.mark.requires_postgres


def test_session_phase_heartbeat_expiry_and_slot_scope(monkeypatch):
    """Actual leases expose phases, renew, expire, and cannot cross slot boundaries."""
    with disposable_slot_database("qa640_775_status") as dbname:
        route_slot(monkeypatch, dbname)
        session = str(uuid4())
        with closing(connect(dbname)) as conn:
            assert (
                acquire_generation_lease(
                    conn,
                    session_id=session,
                    operation="continue",
                    stale_timeout_seconds=60,
                )
                is None
            )
            initial = read_generation_session(conn)
            assert initial["session_id"] == session
            assert initial["phase"] == "retrieval"
            for phase in ("assembly", "writer", "gaia", "staging"):
                heartbeat_generation(
                    conn, session_id=session, timeout_seconds=60, phase=phase
                )
                row = read_generation_session(conn, session_id=session)
                assert row["phase"] == phase
                assert row["heartbeat_at"] > initial["heartbeat_at"]
                assert row["expires_at"] > initial["expires_at"]
            # Mount the real route without starting unrelated maintenance.
            with TestClient(narrative.app) as client:
                active = client.get("/api/narrative/active", params={"slot": 4})
                assert active.status_code == 200, active.text
                assert active.json()["session_id"] == session
                assert active.json()["slot"] == 4
                assert client.get("/api/narrative/active").status_code == 422
                assert client.get(f"/api/narrative/status/{session}").status_code == 422
                assert (
                    client.get(
                        f"/api/narrative/status/{uuid4()}", params={"slot": 4}
                    ).status_code
                    == 404
                )
            with conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE narrative_generation_lease SET expires_at = NOW() - INTERVAL '1 second'"
                )
            expired = read_generation_session(conn)
            assert expired["terminal_outcome"] == "error"
            assert expired["error_class"] == "GenerationLeaseExpired"
            assert expired["expires_at"] is None
            with pytest.raises(RuntimeError, match="lost its lease"):
                heartbeat_generation(conn, session_id=session, timeout_seconds=60)
            assert read_generation_session(conn) == expired


def test_session_routes_and_socket_hints_do_not_cross_slots(monkeypatch):
    """Two real slot databases and two sockets remain isolated by explicit slot."""
    from nexus.api import slot_utils

    with (
        disposable_slot_database("qa640_775_left") as left,
        disposable_slot_database("qa640_775_right") as right,
    ):
        route_slot(monkeypatch, left)
        monkeypatch.setattr(slot_utils, "VALID_DBNAMES", {left, right})
        monkeypatch.setattr(
            slot_utils, "slot_dbname", lambda slot: {4: left, 5: right}[slot]
        )
        session = str(uuid4())
        with closing(connect(left)) as conn:
            acquire_generation_lease(
                conn, session_id=session, operation="continue", stale_timeout_seconds=60
            )
        with TestClient(narrative.app) as client:
            assert (
                client.get("/api/narrative/active", params={"slot": 5}).json() is None
            )
            assert (
                client.get(
                    f"/api/narrative/status/{session}", params={"slot": 5}
                ).status_code
                == 404
            )
            with (
                client.websocket_connect("/ws/narrative?slot=4") as own,
                client.websocket_connect("/ws/narrative?slot=5") as other,
            ):
                client.portal.call(
                    narrative.manager.send_progress, session, "writer", {"slot": 4}
                )
                assert own.receive_json()["session_id"] == session
                other_connection = next(
                    ws
                    for ws in narrative.manager.active_connections
                    if ws.query_params["slot"] == "5"
                )
                client.portal.call(
                    narrative.manager.send_personal_message,
                    "end of hints",
                    other_connection,
                )
                assert other.receive_text() == "end of hints"
