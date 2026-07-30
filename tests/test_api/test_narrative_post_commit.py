"""Tests for post-commit Orrery work scheduling in the narrative API.

FastAPI background tasks run sequentially in add order, and the
auto-approve path schedules post-commit Orrery work BEFORE the next
chunk's generation task. The Retrograde maturation drain makes
multi-minute frontier calls, so it must detach from that chain
(fire-and-forget, spec decision 10) while quick outbox work stays inline.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from fastapi import BackgroundTasks

from nexus.api import commit_handler_sync
from nexus.api import narrative


def test_post_commit_orrery_work_detaches_maturation(monkeypatch) -> None:
    """Quick outbox work runs inline with maturation excluded; the
    maturation drain starts on a detached daemon thread instead."""

    outbox_calls: list[dict[str, Any]] = []

    def fake_outbox(slot: Any, *args: Any, **kwargs: Any) -> None:
        outbox_calls.append({"slot": slot, **kwargs})

    def fake_drain(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("drain must not run inline")

    started: dict[str, Any] = {}

    class FakeThread:
        def __init__(
            self,
            *,
            target: Any,
            args: tuple[Any, ...] = (),
            name: str | None = None,
            daemon: bool | None = None,
        ) -> None:
            started["target"] = target
            started["args"] = args
            started["name"] = name
            started["daemon"] = daemon

        def start(self) -> None:
            started["started"] = True

    monkeypatch.setattr(
        "nexus.agents.orrery.worker.process_orrery_outbox_sync",
        fake_outbox,
    )
    monkeypatch.setattr(
        "nexus.agents.orrery.retrograde_maturation.drain_maturation_jobs_sync",
        fake_drain,
    )
    monkeypatch.setattr(narrative.threading, "Thread", FakeThread)

    narrative._run_post_commit_orrery_work(2)

    assert outbox_calls == [{"slot": 2, "maturation_limit": 0}]
    assert started["started"] is True
    assert started["target"] is fake_drain
    assert started["args"] == (2,)
    assert started["daemon"] is True


@pytest.mark.asyncio
async def test_auto_approval_runs_commit_and_compaction_off_event_loop(
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

    def commit_in_worker(_conn: Any, session_id: str, slot: int | None) -> int:
        assert session_id == "pending-session"
        assert slot == 4
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()
        commit_threads.append(threading.get_ident())
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
    background_tasks = BackgroundTasks()

    result = await narrative._resolve_and_approve_pending(
        slot=4,
        session_id="pending-session",
        chunk_id=41,
        user_text="Take the left stair.",
        choice=1,
        accept_fate=False,
        background_tasks=background_tasks,
    )

    assert result == ("resolved player response", 42)
    assert commit_threads and commit_threads[0] != event_loop_thread
    assert connection.closed is True
    assert len(background_tasks.tasks) == 1


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
async def test_explicit_approval_runs_commit_and_compaction_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The standalone approval route uses the same worker boundary."""

    event_loop_thread = threading.get_ident()
    connection = _PendingConnection()
    commit_threads: list[int] = []

    def commit_in_worker(_conn: Any, _session_id: str, _slot: int | None) -> int:
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
    commit_threads: list[int] = []
    close_threads: list[int] = []

    class BlockingConnection(_PendingConnection):
        def close(self) -> None:
            close_threads.append(threading.get_ident())
            connection_closed.set()

    connection = BlockingConnection()

    def blocking_commit(_conn: Any, _session_id: str, _slot: int | None) -> int:
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
    assert commit_threads
    assert close_threads == commit_threads
