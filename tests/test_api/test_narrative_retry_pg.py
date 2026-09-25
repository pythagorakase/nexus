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


def _frontier_state(parent: int):
    """Production-shaped slot state for a committed frontier with open choices."""
    return SimpleNamespace(
        is_wizard_mode=False,
        narrative_state=SimpleNamespace(
            has_pending=False,
            session_id=None,
            current_chunk_id=parent,
            choices=["Agree.", "Walk away."],
        ),
    )


def _continue(**request):
    from nexus.api.narrative_schemas import ContinueNarrativeRequest

    tasks = BackgroundTasks()
    return asyncio.run(
        narrative.continue_narrative(ContinueNarrativeRequest(slot=4, **request), tasks)
    )


def _latest_session(dbname):
    with connect(dbname, cursor_factory=RealDictCursor) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT session_id, status, parent_chunk_id, terminal_outcome "
            "FROM narrative_generation_sessions ORDER BY created_at DESC LIMIT 1"
        )
        return dict(cur.fetchone())


def test_failure_between_acceptance_and_bind_stays_retryable(recovery_db, monkeypatch):
    """A committed action survives a bind failure as the failed session's parent."""
    dbname, parent, _ = recovery_db
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM narrative_generation_sessions")
        cur.execute(
            "UPDATE narrative_chunks SET choice_text = NULL WHERE id = %s", (parent,)
        )
    monkeypatch.setattr(
        slot_state, "get_slot_state", lambda slot: _frontier_state(parent)
    )
    real_bind = narrative._bind_generation_owner
    bind_outage = {"active": True}

    def flaky_bind(**kwargs):
        if bind_outage["active"]:
            raise RuntimeError("bind connection lost")
        return real_bind(**kwargs)

    monkeypatch.setattr(narrative, "_bind_generation_owner", flaky_bind)

    # 1. A failure before acceptance records nothing and binds nothing.
    with pytest.raises(HTTPException) as rejected:
        _continue(choice=5)
    assert rejected.value.status_code == 400
    assert snapshot(dbname)[0][0]["choice_text"] is None
    unbound = _latest_session(dbname)
    assert (unbound["status"], unbound["parent_chunk_id"]) == ("error", None)
    with pytest.raises(HTTPException) as stale:
        retry(unbound["session_id"])
    assert stale.value.status_code == 409

    # 2. The action is accepted, then the bind fails on its own connection.
    with pytest.raises(RuntimeError, match="bind connection lost"):
        _continue(choice=1)
    assert snapshot(dbname)[0][0]["choice_text"] == "Agree."
    failed = _latest_session(dbname)
    assert (failed["status"], failed["terminal_outcome"]) == ("error", "error")
    assert failed["parent_chunk_id"] == parent
    assert snapshot(dbname)[2] == []

    # 3. A client that was not told about the recorded action sends another
    #    one: the 409 attempt is also bound to the recorded action, so the
    #    reader is offered recovery instead of a dead end.
    with pytest.raises(HTTPException) as conflict:
        _continue(choice=2)
    assert conflict.value.status_code == 409
    assert _latest_session(dbname)["parent_chunk_id"] == parent
    assert snapshot(dbname)[0][0]["choice_text"] == "Agree."

    # 4. Once the outage clears, the explicit retry of the displayed failure
    #    resumes the exact recorded action.
    bind_outage["active"] = False
    response, tasks = retry(_latest_session(dbname)["session_id"])
    assert tasks.tasks[0].args == (response.session_id, parent, "Agree.", 4)
    assert snapshot(dbname)[0][0]["choice_text"] == "Agree."


def _seed_pending(dbname: str, parent: int) -> tuple[str, int]:
    """Stage a complete pending draft with one open choice through production."""
    from nexus.api.narrative_generation import write_to_incubator
    from nexus.memory.manager import empty_pass2_baseline
    from tests.pg_fixtures import seed_protagonist
    from tests.test_api.test_narrative_continue_validation import _valid_override

    # The production commit resolves the canonical protagonist.
    seed_protagonist(dbname)
    pending_session = str(uuid.uuid4())
    draft = {
        "chunk_id": None,
        "parent_chunk_id": parent,
        "user_text": ACTION,
        "storyteller_text": "The hinges sigh open.",
        "generation_model": _valid_override(),
        "choice_object": {"presented": ["Enter.", "Wait."], "selected": None},
        "choice_text": None,
        "metadata_updates": {
            "chronology": {"episode_transition": "continue", "time_delta_minutes": 1},
            "world_layer": "primary",
        },
        "entity_updates": {},
        "reference_updates": {"characters": [], "places": [], "factions": []},
        "orrery_proposal": {},
        "orrery_adjudications": [],
        "new_entities": [],
        "lore_pass_baseline": empty_pass2_baseline({}).model_dump(mode="json"),
        "session_id": pending_session,
        "llm_response_id": None,
        "status": "complete",
    }
    with connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM narrative_generation_sessions")
        conn.commit()
        # The staging writer requires the writing session to own the lease.
        assert (
            narrative_lease.acquire_generation_lease(
                conn,
                session_id=pending_session,
                operation="continue",
                stale_timeout_seconds=600,
            )
            is None
        )
        narrative_lease.bind_generation_parent(
            conn, session_id=pending_session, parent_chunk_id=parent
        )
        asyncio.run(write_to_incubator(conn, draft))
        narrative_lease.finish_generation(
            conn, session_id=pending_session, status="complete"
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id FROM incubator WHERE session_id = %s",
                (pending_session,),
            )
            pending_chunk = cur.fetchone()[0]
    return pending_session, int(pending_chunk) if pending_chunk else parent + 1


def _pending_state(session: str, chunk: int):
    return SimpleNamespace(
        is_wizard_mode=False,
        narrative_state=SimpleNamespace(
            has_pending=True,
            session_id=session,
            current_chunk_id=chunk,
            choices=["Enter.", "Wait."],
        ),
    )


def _latest_chunk(dbname):
    with connect(dbname, cursor_factory=RealDictCursor) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, choice_text FROM narrative_chunks ORDER BY id DESC LIMIT 1"
        )
        return dict(cur.fetchone())


def test_explicit_frontier_chunk_bind_failure_stays_retryable(recovery_db, monkeypatch):
    """chunk_id supplied explicitly binds the same way as the inferred frontier."""
    dbname, parent, _ = recovery_db
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM narrative_generation_sessions")
        cur.execute(
            "UPDATE narrative_chunks SET choice_text = NULL WHERE id = %s", (parent,)
        )
    monkeypatch.setattr(
        slot_state, "get_slot_state", lambda slot: _frontier_state(parent)
    )
    real_bind = narrative._bind_generation_owner
    outage = {"active": True}

    def flaky_bind(**kwargs):
        if outage["active"]:
            raise RuntimeError("bind connection lost")
        return real_bind(**kwargs)

    monkeypatch.setattr(narrative, "_bind_generation_owner", flaky_bind)
    with pytest.raises(RuntimeError, match="bind connection lost"):
        _continue(chunk_id=parent, choice=1)
    assert snapshot(dbname)[0][0]["choice_text"] == "Agree."
    failed = _latest_session(dbname)
    assert (failed["status"], failed["parent_chunk_id"]) == ("error", parent)
    outage["active"] = False
    response, tasks = retry(failed["session_id"])
    assert tasks.tasks[0].args == (response.session_id, parent, "Agree.", 4)


def test_pending_approval_failure_after_commit_stays_retryable(
    recovery_db, monkeypatch
):
    """An exception after the incubator commit keeps the approved action bound."""
    dbname, parent, _ = recovery_db
    pending_session, pending_chunk = _seed_pending(dbname, parent)
    monkeypatch.setattr(
        slot_state,
        "get_slot_state",
        lambda slot: _pending_state(pending_session, pending_chunk),
    )
    monkeypatch.setattr(
        narrative,
        "wake_scheduler",
        lambda slot: (_ for _ in ()).throw(RuntimeError("scheduler offline")),
    )
    with pytest.raises(RuntimeError, match="scheduler offline"):
        _continue(choice=1)
    approved = _latest_chunk(dbname)
    assert approved["choice_text"] == "Enter."
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM incubator")
        assert cur.fetchone()[0] == 0
    failed = _latest_session(dbname)
    assert (failed["status"], failed["terminal_outcome"]) == ("error", "error")
    assert failed["parent_chunk_id"] == approved["id"]
    monkeypatch.setattr(narrative, "wake_scheduler", lambda slot: None)
    response, tasks = retry(failed["session_id"])
    assert tasks.tasks[0].args == (response.session_id, approved["id"], "Enter.", 4)


def test_abandon_before_worker_commit_still_binds_the_approved_action(
    recovery_db, monkeypatch
):
    """Cleanup that outruns the worker's commit is repaired by the commit itself."""
    dbname, parent, _ = recovery_db
    pending_session, pending_chunk = _seed_pending(dbname, parent)
    monkeypatch.setattr(narrative, "wake_scheduler", lambda slot: None)
    new_session = str(uuid.uuid4())
    with connect(dbname) as conn:
        assert (
            narrative_lease.acquire_generation_lease(
                conn,
                session_id=new_session,
                operation="continue",
                stale_timeout_seconds=600,
            )
            is None
        )
    # Ordering under test: the route's finally already abandoned the session
    # (candidate unknown: the approved chunk id does not exist yet) ...
    with connect(dbname) as conn:
        narrative_lease.abandon_generation(
            conn,
            session_id=new_session,
            error="CancelledError",
            error_class="CancelledError",
        )
    unbound = _latest_session(dbname)
    assert (unbound["status"], unbound["parent_chunk_id"]) == ("error", None)
    # ... and only then does the still-running worker commit the approval.
    text, approved = narrative._resolve_and_approve_pending_sync(
        slot=4,
        session_id=pending_session,
        chunk_id=pending_chunk,
        user_text="",
        choice=1,
        accept_fate=False,
        bind_session_id=new_session,
    )
    assert (text, approved) == ("Enter.", _latest_chunk(dbname)["id"])
    bound = _latest_session(dbname)
    assert (bound["session_id"], bound["status"]) == (new_session, "error")
    assert bound["parent_chunk_id"] == approved
    assert snapshot(dbname)[2] == []
    response, tasks = retry(new_session)
    assert tasks.tasks[0].args == (response.session_id, approved, "Enter.", 4)


def test_cancelled_route_leaves_a_retryable_failure_after_the_worker_commits(
    recovery_db, monkeypatch
):
    """Real cancellation during approval: the worker outlives the route safely."""
    from nexus.api.narrative_schemas import ContinueNarrativeRequest

    dbname, parent, _ = recovery_db
    pending_session, pending_chunk = _seed_pending(dbname, parent)
    monkeypatch.setattr(
        slot_state,
        "get_slot_state",
        lambda slot: _pending_state(pending_session, pending_chunk),
    )
    monkeypatch.setattr(narrative, "wake_scheduler", lambda slot: None)
    from nexus.api import commit_handler_sync

    gate = threading.Event()
    real_commit = commit_handler_sync.commit_incubator_to_database_sync

    def gated_commit(*args, **kwargs):
        assert gate.wait(timeout=20), "route never released the worker"
        return real_commit(*args, **kwargs)

    # The worker imports the commit from its defining module at call time.
    monkeypatch.setattr(
        commit_handler_sync, "commit_incubator_to_database_sync", gated_commit
    )
    observed = {}

    async def scenario():
        task = asyncio.create_task(
            narrative.continue_narrative(
                ContinueNarrativeRequest(slot=4, choice=1), BackgroundTasks()
            )
        )
        await asyncio.sleep(0.5)  # the worker is parked at the gate
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        observed["after_cancel"] = _latest_session(dbname)
        gate.set()
        for _ in range(100):
            await asyncio.sleep(0.1)
            if _latest_session(dbname)["parent_chunk_id"] is not None:
                break

    asyncio.run(scenario())
    after_cancel = observed["after_cancel"]
    assert (after_cancel["status"], after_cancel["parent_chunk_id"]) == ("error", None)
    approved = _latest_chunk(dbname)
    assert approved["choice_text"] == "Enter."
    final = _latest_session(dbname)
    assert final["session_id"] == after_cancel["session_id"]
    assert (final["status"], final["parent_chunk_id"]) == ("error", approved["id"])
    assert snapshot(dbname)[2] == []
    response, tasks = retry(final["session_id"])
    assert tasks.tasks[0].args == (response.session_id, approved["id"], "Enter.", 4)


class _PausingCursor:
    """Block after the first statement so a competing transaction can start."""

    def __init__(self, cur, held: threading.Event, proceed: threading.Event):
        self._cur = cur
        self._held = held
        self._proceed = proceed
        self.calls = 0

    def execute(self, *args, **kwargs):
        result = self._cur.execute(*args, **kwargs)
        self.calls += 1
        if self.calls == 1:
            self._held.set()
            assert self._proceed.wait(timeout=20), "test never released the worker"
        return result

    def __getattr__(self, name):
        return getattr(self._cur, name)


def test_worker_binding_and_cancelled_abandon_overlap_without_deadlock(recovery_db):
    """The worker's binding and a cancelled route's cleanup contend on the same rows.

    The worker is paused between its two statements, holding its first lock,
    while the abandon runs and blocks on it. Under the reversed lock order this
    is an ABBA deadlock that PostgreSQL resolves by aborting one side; under the
    module's lease -> session order the abandon simply waits and the final row
    is a retryable failure.
    """
    import time

    dbname, parent, _ = recovery_db
    session = str(uuid.uuid4())
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM narrative_generation_sessions")
    with connect(dbname) as conn:
        assert (
            narrative_lease.acquire_generation_lease(
                conn,
                session_id=session,
                operation="continue",
                stale_timeout_seconds=600,
            )
            is None
        )
    held, proceed = threading.Event(), threading.Event()
    timeline: dict = {}
    errors: dict = {}

    def worker():
        try:
            conn = connect(dbname)
            try:
                narrative_lease.associate_accepted_parent(
                    _PausingCursor(conn.cursor(), held, proceed),
                    session_id=session,
                    parent_chunk_id=parent,
                )
                conn.commit()
                timeline["worker_committed"] = time.monotonic()
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 - recorded for the assertion
            errors["worker"] = exc

    def cancelled_route():
        try:
            with connect(dbname) as conn:
                narrative_lease.abandon_generation(
                    conn,
                    session_id=session,
                    error="CancelledError",
                    error_class="CancelledError",
                )
            timeline["abandon_done"] = time.monotonic()
        except Exception as exc:  # noqa: BLE001 - recorded for the assertion
            errors["abandon"] = exc

    worker_thread = threading.Thread(target=worker)
    abandon_thread = threading.Thread(target=cancelled_route)
    worker_thread.start()
    assert held.wait(timeout=20)
    abandon_thread.start()
    time.sleep(
        0.5
    )  # let the abandon reach its first lock while the worker holds its own
    assert abandon_thread.is_alive(), "abandon must contend with the paused worker"
    proceed.set()
    worker_thread.join(timeout=30)
    abandon_thread.join(timeout=30)
    assert not worker_thread.is_alive() and not abandon_thread.is_alive()
    assert errors == {}, errors
    assert timeline["abandon_done"] > timeline["worker_committed"]
    final = _latest_session(dbname)
    assert (final["session_id"], final["status"]) == (session, "error")
    assert final["parent_chunk_id"] == parent
    assert snapshot(dbname)[2] == []
    response, tasks = retry(session)
    assert tasks.tasks[0].args == (response.session_id, parent, ACTION, 4)
