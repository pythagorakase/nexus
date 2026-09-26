"""Approval wakes the lifespan scheduler without joining deferred work.

The real PostgreSQL cancellation proof retains accepted state and recovery;
no provider-capable drain is registered ahead of interactive generation.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from contextlib import closing
from typing import Any

import pytest
from fastapi import BackgroundTasks

from nexus.agents.orrery import retrograde_maturation
from nexus.api import commit_handler_sync, narrative, narrative_lease
from nexus.api.narrative_generation import write_to_incubator
from nexus.memory.manager import empty_pass2_baseline
from tests.pg_fixtures import connect, seed_protagonist


@pytest.mark.requires_postgres
def test_post_commit_wakes_scheduler_without_joining(
    offline_gate_db, monkeypatch
) -> None:
    """A commit signals the sole lifespan owner without starting a second drain."""
    from nexus.jobs.scheduler import SlotScheduler

    scheduler = SlotScheduler(4, dbname=offline_gate_db)
    monkeypatch.setattr(narrative.app.state, "scheduler", scheduler, raising=False)
    narrative.wake_scheduler(4)
    assert scheduler.wakeup.is_set()
    assert scheduler._thread is None
    assert not hasattr(narrative, "_start_post_commit_orrery_work")
    assert not hasattr(narrative, "_run_post_commit_orrery_work")


@pytest.mark.asyncio
async def test_auto_approval_runs_commit_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The continue route's approval seam isolates the synchronous provider."""

    event_loop_thread = threading.get_ident()
    connection = type(
        "Connection",
        (),
        {
            "rollback": lambda self: None,
            "close": lambda self: setattr(self, "closed", True),
        },
    )()
    commit_threads: list[int] = []
    quarantine_warning = {
        "code": "experience_event_quarantined",
        "message": "Experience formation quarantined malformed world event 73",
        "world_event_id": 73,
        "event_type": "warning_delivered",
        "reason_code": "invalid_audience_id",
        "reason": "Public event 73 audience index 0 has invalid entity id 0",
    }

    def commit_in_worker(
        _conn: Any,
        session_id: str,
        slot: int | None,
        *,
        warning_sink: list[dict[str, Any]] | None = None,
        bind_session_id: str | None = None,
    ) -> int:
        assert session_id == "pending-session"
        assert slot == 4
        assert warning_sink is not None
        # The continue route binds its new session inside this commit.
        assert bind_session_id == "continuing-session"
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()
        commit_threads.append(threading.get_ident())
        warning_sink.append(quarantine_warning)
        return 42

    monkeypatch.setattr(narrative, "get_db_connection", lambda _slot: connection)
    monkeypatch.setattr(
        narrative,
        "_record_player_response_for_chunk",
        lambda **_kwargs: "resolved player response",
    )
    monkeypatch.setattr(
        commit_handler_sync,
        "commit_incubator_to_database_sync",
        commit_in_worker,
    )
    woken = threading.Event()
    monkeypatch.setattr(
        narrative,
        "wake_scheduler",
        lambda _slot: woken.set(),
    )
    background_tasks = BackgroundTasks()

    result = await narrative._resolve_and_approve_pending(
        slot=4,
        session_id="pending-session",
        chunk_id=41,
        user_text="Take the left stair.",
        choice=1,
        accept_fate=False,
        background_tasks=background_tasks,
        bind_session_id="continuing-session",
    )

    assert result == ("resolved player response", 42, [quarantine_warning])
    assert commit_threads and commit_threads[0] != event_loop_thread
    assert connection.closed is True
    assert len(background_tasks.tasks) == 0
    await background_tasks()
    assert woken.is_set()


class _PendingCursor:
    """Serve one pending row to the explicit approval endpoint."""

    def __enter__(self) -> "_PendingCursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, _query: str, _params: Any) -> None:
        return None

    def fetchone(self) -> dict[str, int]:
        return {"chunk_id": 41}


class _PendingConnection:
    """Small approval-route connection double."""

    closed = False

    def cursor(self, **_kwargs: Any) -> _PendingCursor:
        return _PendingCursor()

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_explicit_approval_runs_commit_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The standalone approval route uses the same worker boundary."""

    event_loop_thread = threading.get_ident()
    connection = _PendingConnection()
    commit_threads: list[int] = []

    def commit_in_worker(
        _conn: Any,
        _session_id: str,
        _slot: int | None,
        *,
        warning_sink: list[dict[str, Any]] | None = None,
    ) -> int:
        assert warning_sink == []
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()
        commit_threads.append(threading.get_ident())
        return 42

    monkeypatch.setattr(narrative, "get_db_connection", lambda _slot: connection)
    monkeypatch.setattr(
        commit_handler_sync,
        "commit_incubator_to_database_sync",
        commit_in_worker,
    )
    monkeypatch.setattr(
        narrative,
        "wake_scheduler",
        lambda _slot: None,
    )

    result = await narrative._approve_narrative_impl(
        "pending-session",
        True,
        4,
    )

    assert result == {
        "status": "committed",
        "message": "Narrative committed as chunk 42",
        "chunk_id": 42,
    }
    assert commit_threads and commit_threads[0] != event_loop_thread
    assert connection.closed is True


@pytest.mark.asyncio
async def test_cancelled_approval_leaves_worker_connection_owned_until_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation cannot close a connection underneath the commit worker."""

    commit_started = threading.Event()
    release_commit = threading.Event()
    connection_closed = threading.Event()
    post_commit_finished = threading.Event()
    commit_threads: list[int] = []
    close_threads: list[int] = []

    class BlockingConnection(_PendingConnection):
        def close(self) -> None:
            close_threads.append(threading.get_ident())
            connection_closed.set()

    connection = BlockingConnection()

    def blocking_commit(
        _conn: Any,
        _session_id: str,
        _slot: int | None,
        *,
        warning_sink: list[dict[str, Any]] | None = None,
    ) -> int:
        assert warning_sink == []
        commit_threads.append(threading.get_ident())
        commit_started.set()
        assert release_commit.wait(timeout=5)
        assert not connection_closed.is_set()
        return 42

    monkeypatch.setattr(narrative, "get_db_connection", lambda _slot: connection)
    monkeypatch.setattr(
        commit_handler_sync,
        "commit_incubator_to_database_sync",
        blocking_commit,
    )
    monkeypatch.setattr(
        narrative,
        "wake_scheduler",
        lambda _slot: post_commit_finished.set(),
    )
    approval_task = asyncio.create_task(
        narrative._approve_narrative_impl(
            "pending-session",
            True,
            4,
        )
    )

    try:
        assert await asyncio.to_thread(commit_started.wait, 2)
        approval_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await approval_task
        assert not connection_closed.is_set()
    finally:
        release_commit.set()

    assert await asyncio.to_thread(connection_closed.wait, 2)
    assert await asyncio.to_thread(post_commit_finished.wait, 2)
    assert commit_threads
    assert close_threads == commit_threads


@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit(
    monkeypatch: pytest.MonkeyPatch,
    offline_gate_db: str,
) -> None:
    """Cancel a real leased approval; its worker still commits and wakes recovery."""
    dbname = offline_gate_db
    seed_protagonist(dbname)
    pending_session = str(uuid.uuid4())
    with closing(connect(dbname)) as conn:
        assert (
            narrative_lease.acquire_generation_lease(
                conn,
                session_id=pending_session,
                operation="continue",
                stale_timeout_seconds=60,
            )
            is None
        )
        narrative_lease.bind_generation_parent(
            conn, session_id=pending_session, parent_chunk_id=0
        )
        await write_to_incubator(
            conn,
            {
                "chunk_id": None,
                "parent_chunk_id": 0,
                "user_text": "Begin.",
                "storyteller_text": "The stair awaits.",
                "generation_model": "TEST",
                "choice_object": {
                    "presented": ["Take the left stair."],
                    "selected": None,
                },
                "metadata_updates": {},
                "entity_updates": {},
                "reference_updates": {},
                "lore_pass_baseline": empty_pass2_baseline({}).model_dump(mode="json"),
                "session_id": pending_session,
                "llm_response_id": None,
                "status": "provisional",
            },
        )
        narrative_lease.finish_generation(
            conn, session_id=pending_session, status="complete"
        )

    commit_started = threading.Event()
    release_commit = threading.Event()
    post_commit_finished = threading.Event()
    maturation_finished = threading.Event()
    commit_connections: list[Any] = []
    worker_errors: list[BaseException] = []
    acquired_sessions: list[str] = []
    abandoned_sessions: list[tuple[str, str]] = []
    original_acquire = narrative._acquire_generation_owner
    original_abandon = narrative._abandon_generation_owner
    original_commit = commit_handler_sync.commit_incubator_to_database_sync
    from nexus.jobs.scheduler import SlotScheduler

    scheduler = SlotScheduler(4, dbname=dbname)
    original_post_commit = lambda slot: scheduler.run_pass()
    original_maturation = retrograde_maturation.drain_maturation_jobs_sync

    def observed_acquire(**kwargs: Any) -> None:
        """Record the session passed to the real lease acquisition."""
        acquired_sessions.append(kwargs["session_id"])
        original_acquire(**kwargs)

    def observed_abandon(**kwargs: Any) -> None:
        """Record cancellation arguments while releasing the real lease."""
        abandoned_sessions.append((kwargs["session_id"], kwargs["error"]))
        original_abandon(**kwargs)

    def gated_real_commit(
        conn: Any,
        session_id: str,
        slot: int | None,
        *,
        warning_sink: list[dict[str, Any]] | None = None,
    ) -> int:
        """Pause the real commit at entry without replacing its SQL or connection."""
        commit_connections.append(conn)
        commit_started.set()
        try:
            assert warning_sink == []
            assert release_commit.wait(timeout=5)
            assert not conn.closed
            return original_commit(conn, session_id, slot, warning_sink=warning_sink)
        except BaseException as exc:
            worker_errors.append(exc)
            raise

    def observed_post_commit(slot: int | None) -> None:
        """Observe the production outbox drain, including worker-owned close."""
        try:
            assert commit_connections[0].closed
            original_post_commit(slot)
        except BaseException as exc:
            worker_errors.append(exc)
            raise
        finally:
            post_commit_finished.set()

    def observed_maturation(*args: Any, **kwargs: Any) -> tuple[int, int]:
        """Wait for the real detached drain before dropping its database."""
        try:
            return original_maturation(*args, **kwargs)
        except BaseException as exc:
            worker_errors.append(exc)
            raise
        finally:
            maturation_finished.set()

    monkeypatch.setattr(narrative, "_acquire_generation_owner", observed_acquire)
    monkeypatch.setattr(narrative, "_abandon_generation_owner", observed_abandon)
    monkeypatch.setattr(
        commit_handler_sync, "commit_incubator_to_database_sync", gated_real_commit
    )
    monkeypatch.setattr(narrative, "wake_scheduler", observed_post_commit)
    monkeypatch.setattr(
        retrograde_maturation, "drain_maturation_jobs_sync", observed_maturation
    )
    continue_task = asyncio.create_task(
        narrative.continue_narrative(
            narrative.ContinueNarrativeRequest(slot=4, choice=1),
            BackgroundTasks(),
        )
    )

    try:
        assert await asyncio.to_thread(commit_started.wait, 2)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT session_id FROM narrative_generation_lease")
            lease_session = cur.fetchone()[0]
        continue_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await continue_task
        assert acquired_sessions == [lease_session]
        assert abandoned_sessions == [(acquired_sessions[0], "CancelledError")]
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM narrative_generation_lease")
            assert cur.fetchone() == (0,)
            cur.execute(
                "SELECT status, error FROM narrative_generation_sessions WHERE session_id = %s",
                (lease_session,),
            )
            assert cur.fetchone() == ("error", "CancelledError")
        assert not commit_connections[0].closed
    finally:
        release_commit.set()
        if not continue_task.done():
            continue_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await continue_task
        assert await asyncio.to_thread(post_commit_finished.wait, 2), worker_errors
        assert await asyncio.to_thread(maturation_finished.wait, 2), worker_errors

    assert not worker_errors
    assert commit_connections[0].closed
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM incubator")
        assert cur.fetchone() == (0,)
        cur.execute("SELECT choice_text FROM narrative_chunks")
        assert cur.fetchone() == ("Take the left stair.",)
