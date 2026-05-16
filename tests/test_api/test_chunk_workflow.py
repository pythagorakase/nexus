"""Tests for chunk acceptance and embedding handoff behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from nexus.api import chunk_workflow
from nexus.api.chunk_workflow import (
    ChunkState,
    ChunkWorkflow,
    build_embedding_scheduler,
)


class DummyCursor:
    """Cursor double with queued fetch results and executed SQL capture."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = list(rows or [])
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []

    def __enter__(self) -> "DummyCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        """Capture SQL and params for assertions."""

        self.executed.append((sql, params))

    def fetchone(self) -> Any:
        """Return the next queued row."""

        if not self.rows:
            return None
        return self.rows.pop(0)


class DummyConnection:
    """Connection double that returns a shared cursor."""

    def __init__(self, cursor: DummyCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self) -> "DummyConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def cursor(self) -> DummyCursor:
        """Return the cursor double."""

        return self.cursor_obj


def make_workflow() -> ChunkWorkflow:
    """Create a ChunkWorkflow without opening a database connection."""

    workflow = ChunkWorkflow.__new__(ChunkWorkflow)
    workflow.dbname = "save_05"
    return workflow


def test_accept_chunk_uses_scheduler_without_running_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepting via an injected scheduler should not run embeddings inline."""

    cursor = DummyCursor(
        rows=[
            (2,),
            (1, ChunkState.FINALIZED.value, "previous text", None),
        ]
    )
    monkeypatch.setattr(
        chunk_workflow,
        "get_connection",
        lambda *args, **kwargs: DummyConnection(cursor),
    )

    workflow = make_workflow()

    def fail_inline_trigger(chunk_id: int, job_id: str | None = None) -> None:
        pytest.fail("Embedding subprocess should be queued, not run inline")

    workflow.trigger_embedding_generation = fail_inline_trigger
    scheduled: list[int] = []

    def scheduler(chunk_id: int) -> str:
        scheduled.append(chunk_id)
        return "embed_1_test"

    response = workflow.accept_chunk(
        chunk_id=2,
        session_id="session-1",
        embedding_scheduler=scheduler,
    )

    assert scheduled == [1]
    assert response.previous_chunk_embedded is True
    assert response.embedding_job_id == "embed_1_test"
    assert (ChunkState.EMBEDDED.value, 1) not in [
        params for _sql, params in cursor.executed
    ]


def test_build_embedding_scheduler_queues_background_task() -> None:
    """The BackgroundTasks adapter should queue the trigger with a stable job id."""

    workflow = make_workflow()
    queued: list[tuple[Any, tuple[Any, ...]]] = []

    def add_task(func: Any, *args: Any) -> None:
        queued.append((func, args))

    monkeypatch_job_id = "embed_7_scheduled"
    workflow.create_embedding_job_id = lambda chunk_id: monkeypatch_job_id

    scheduler = build_embedding_scheduler(workflow, add_task)
    job_id = scheduler(7)

    assert job_id == monkeypatch_job_id
    assert queued == [(workflow.trigger_embedding_generation, (7, monkeypatch_job_id))]


def test_trigger_embedding_failure_clears_incomplete_embedding_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed subprocess should clear partial embedded state for retry/undo safety."""

    cursor = DummyCursor()
    monkeypatch.setattr(
        chunk_workflow,
        "get_connection",
        lambda *args, **kwargs: DummyConnection(cursor),
    )

    import nexus.config

    monkeypatch.setattr(
        nexus.config,
        "load_settings_as_dict",
        lambda: {
            "Agent Settings": {
                "MEMNON": {
                    "models": {
                        "Octen-Embedding-4B": {"is_active": True},
                    }
                }
            }
        },
    )
    monkeypatch.setattr(
        chunk_workflow.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="boom"),
    )

    workflow = make_workflow()
    result = workflow.trigger_embedding_generation(1, job_id="embed_1_test")

    assert result is None
    assert len(cursor.executed) == 1
    cleanup_sql, cleanup_params = cursor.executed[0]
    assert "embedding_generated_at = NULL" in cleanup_sql
    assert cleanup_params == (
        ChunkState.EMBEDDED.value,
        ChunkState.FINALIZED.value,
        1,
    )
