"""Private PostgreSQL proofs of atomic failure recovery and stale retry fencing.

Requires narrative_chunks, chunk_metadata, incubator, generation sessions/lease
and embedding claims from the normal disposable-slot migrations. All writes
are restricted to a fresh database created and dropped by the shared fixture.
"""

import asyncio
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from psycopg2.extras import Json, RealDictCursor

from nexus.api import narrative, narrative_lease, slot_state
from nexus.api.narrative_schemas import RetryNarrativeRequest
from tests.pg_fixtures import connect, disposable_slot_database
from tests.test_api.test_narrative_continue_validation import _reset_to_committed_parent

pytestmark = pytest.mark.requires_postgres
ACTION = (
    "Record both conditions—don't imply agreement.\nAsk for a witnessed inspection."
)


@pytest.fixture
def recovery_db(monkeypatch):
    """Create a committed player action and its failed continuation."""
    with disposable_slot_database("nexus_test_retry") as dbname:
        parent = _reset_to_committed_parent(dbname)
        failed = str(uuid.uuid4())
        with connect(dbname) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE narrative_chunks SET choice_text = %s, choice_object = %s "
                "WHERE id = %s",
                (
                    ACTION,
                    Json({"presented": ["Agree.", "Walk away."], "selected": None}),
                    parent,
                ),
            )
            cur.execute(
                "INSERT INTO narrative_generation_sessions "
                "(session_id, operation, status, terminal_outcome, "
                "parent_chunk_id, error_class) "
                "VALUES (%s, 'continue', 'error', 'error', %s, "
                "'WireContractViolation')",
                (failed, parent),
            )
        monkeypatch.setattr(narrative, "require_writable_slot", lambda slot: dbname)
        monkeypatch.setattr(
            narrative, "get_db_connection", lambda slot: connect(dbname)
        )
        monkeypatch.setattr(
            slot_state,
            "get_slot_state",
            lambda slot: SimpleNamespace(is_wizard_mode=False),
        )

        async def progress(*args, **kwargs):
            return None

        monkeypatch.setattr(narrative.manager, "send_progress", progress)
        yield dbname, parent, failed


def retry(failed):
    """Exercise production route without executing the captured provider task."""
    tasks = BackgroundTasks()
    response = asyncio.run(
        narrative.retry_narrative(
            RetryNarrativeRequest(slot=4, expected_session_id=failed), tasks
        )
    )
    return response, tasks


def snapshot(dbname):
    """Capture player narrative and canonical generation state."""
    with connect(dbname, cursor_factory=RealDictCursor) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, raw_text, choice_text, choice_object "
            "FROM narrative_chunks ORDER BY id"
        )
        chunks = [dict(row) for row in cur.fetchall()]
        cur.execute(
            "SELECT session_id, parent_chunk_id, status, replaced_by_session_id "
            "FROM narrative_generation_sessions ORDER BY created_at"
        )
        sessions = [dict(row) for row in cur.fetchall()]
        cur.execute(
            "SELECT session_id, parent_chunk_id FROM narrative_generation_lease"
        )
        leases = [dict(row) for row in cur.fetchall()]
    return chunks, sessions, leases


def test_concurrent_retry_has_one_owner_and_never_recommits_action(recovery_db):
    """Two deliberate clicks create one retry and preserve the accepted frontier."""
    dbname, parent, failed = recovery_db
    original = snapshot(dbname)[0]
    barrier = threading.Barrier(2)

    def submit():
        barrier.wait(timeout=10)
        try:
            return retry(failed)
        except HTTPException as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))
    successes = [result for result in results if not isinstance(result, HTTPException)]
    failures = [result for result in results if isinstance(result, HTTPException)]
    assert len(successes) == len(failures) == 1
    response, tasks = successes[0]
    assert failures[0].status_code == 409
    assert tasks.tasks[0].args == (response.session_id, parent, ACTION, 4)
    assert len(tasks.tasks) == 1
    chunks, sessions, leases = snapshot(dbname)
    assert chunks == original
    assert len(sessions) == 2
    assert str(sessions[0]["replaced_by_session_id"]) == response.session_id
    assert leases == [{"session_id": response.session_id, "parent_chunk_id": parent}]

    # Even after a replacement ends and releases its lease, an old retry button
    # must not schedule another paid generation for the old failure.
    with connect(dbname) as conn:
        narrative_lease.abandon_generation(
            conn,
            session_id=response.session_id,
            error="fixture failure",
            error_class="FixtureError",
        )
    with pytest.raises(HTTPException) as error:
        retry(failed)
    assert error.value.status_code == 409
    assert len(snapshot(dbname)[1]) == 2
    second, second_tasks = retry(response.session_id)
    assert second.session_id != response.session_id
    assert second_tasks.tasks[0].args[1:3] == (parent, ACTION)
    assert snapshot(dbname)[0] == original


@pytest.mark.parametrize(
    "change",
    [
        "pending",
        "newer_attempt",
        "newer_chunk",
        "missing_action",
        "discarded",
        "missing_parent",
    ],
)
def test_retry_rejects_changed_durable_state_before_session_creation(
    recovery_db, change
):
    """Stale clients cannot bypass database frontier and attempt guards."""
    dbname, parent, failed = recovery_db
    with connect(dbname) as conn, conn.cursor() as cur:
        if change == "pending":
            cur.execute(
                "INSERT INTO incubator "
                "(session_id, parent_chunk_id, chunk_id, storyteller_text) "
                "VALUES (%s, %s, %s, 'Pending story')",
                (str(uuid.uuid4()), parent, parent + 1),
            )
        elif change == "newer_attempt":
            cur.execute(
                "INSERT INTO narrative_generation_sessions "
                "(session_id, operation, status, terminal_outcome, parent_chunk_id) "
                "VALUES (%s, 'continue', 'complete', 'accepted', %s)",
                (str(uuid.uuid4()), parent),
            )
        elif change == "newer_chunk":
            cur.execute(
                "INSERT INTO narrative_chunks (raw_text, storyteller_text, state) "
                "VALUES ('New scene', 'New scene', 'finalized')"
            )
        elif change == "missing_action":
            cur.execute(
                "UPDATE narrative_chunks SET choice_text = NULL WHERE id = %s",
                (parent,),
            )
        elif change == "discarded":
            cur.execute(
                "UPDATE narrative_generation_sessions "
                "SET terminal_outcome = 'discarded' WHERE session_id = %s",
                (failed,),
            )
        else:
            cur.execute(
                "UPDATE narrative_generation_sessions "
                "SET parent_chunk_id = NULL WHERE session_id = %s",
                (failed,),
            )
    before = snapshot(dbname)
    with pytest.raises(HTTPException) as error:
        retry(failed)
    assert error.value.status_code == 409
    assert snapshot(dbname) == before


def test_retry_bootstrap_without_a_playable_parent(recovery_db):
    """Failed bootstrap is recoverable without fabricating a player action."""
    dbname, _, failed = recovery_db
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM narrative_chunks")
        cur.execute(
            "UPDATE narrative_generation_sessions SET parent_chunk_id = 0 "
            "WHERE session_id = %s",
            (failed,),
        )
    response, tasks = retry(failed)
    assert tasks.tasks[0].args == (response.session_id, 0, "", 4)
    assert snapshot(dbname)[0] == []
