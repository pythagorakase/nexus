"""PostgreSQL integration tests for chunk acceptance embedding handoff."""

from __future__ import annotations

from typing import Generator

import psycopg2
import pytest
from fastapi import BackgroundTasks

from nexus.api import chunk_workflow
from nexus.api.chunk_workflow import (
    ChunkState,
    ChunkWorkflow,
    build_embedding_scheduler,
)

TEST_DBNAME = "save_05"
TEMP_CHUNK_IDS = (990001, 990002)

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def slot_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Provide a real slot database connection and remove test rows afterward."""

    conn = psycopg2.connect(
        dbname=TEST_DBNAME,
        user="pythagor",
        host="localhost",
        port=5432,
    )
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM narrative_chunks WHERE id = ANY(%s)",
                    (list(TEMP_CHUNK_IDS),),
                )
        yield conn
    finally:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM narrative_chunks WHERE id = ANY(%s)",
                    (list(TEMP_CHUNK_IDS),),
                )
        conn.close()
        with chunk_workflow._queued_embedding_jobs_lock:
            chunk_workflow._queued_embedding_jobs.discard((TEST_DBNAME, 990001))


def test_accept_chunk_queues_background_embedding_with_real_slot_db(
    slot_connection: psycopg2.extensions.connection,
) -> None:
    """Accepting a chunk should queue, not run, the previous chunk embedding."""

    previous_id, current_id = TEMP_CHUNK_IDS
    with slot_connection:
        with slot_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO narrative_chunks (id, raw_text, state)
                VALUES
                    (%s, 'temporary previous chunk', %s),
                    (%s, 'temporary current chunk', %s)
                """,
                (
                    previous_id,
                    ChunkState.FINALIZED.value,
                    current_id,
                    ChunkState.PENDING_REVIEW.value,
                ),
            )

    workflow = ChunkWorkflow(TEST_DBNAME)
    background_tasks = BackgroundTasks()
    scheduler = build_embedding_scheduler(workflow, background_tasks.add_task)

    response = workflow.accept_chunk(
        chunk_id=current_id,
        session_id="test-session-issue-206",
        embedding_scheduler=scheduler,
    )

    assert response.chunk_id == current_id
    assert response.state == ChunkState.FINALIZED
    assert response.previous_chunk_embedded is True
    assert response.embedding_job_id is not None
    assert len(background_tasks.tasks) == 1

    # The in-process scheduler suppresses duplicate queueing while a task is
    # already pending in this API worker.
    assert scheduler(previous_id) is None
    assert len(background_tasks.tasks) == 1

    with slot_connection.cursor() as cur:
        cur.execute(
            """
            SELECT id, state, finalized_at, embedding_generated_at
            FROM narrative_chunks
            WHERE id = ANY(%s)
            ORDER BY id
            """,
            (list(TEMP_CHUNK_IDS),),
        )
        rows = cur.fetchall()

    assert rows[0][0] == previous_id
    assert rows[0][1] == ChunkState.FINALIZED.value
    assert rows[0][3] is None
    assert rows[1][0] == current_id
    assert rows[1][1] == ChunkState.FINALIZED.value
    assert rows[1][2] is not None


def test_default_workflow_singleton_reuses_one_pool() -> None:
    """get_default_workflow() must hand every caller one workflow and one pool.

    Guards the lazy-singleton invariant from issue #369: endpoint handlers
    (accept/reject/edit/states) all route through get_default_workflow(), so
    repeated access must never construct a fresh ChunkWorkflow or open an
    additional connection pool per request.
    """
    from nexus.api import db_pool

    chunk_workflow._default_workflow = None
    db_pool.close_all_pools()
    try:
        first = chunk_workflow.get_default_workflow()
        second = chunk_workflow.get_default_workflow()
        assert first is second

        # A real read through the workflow must reuse the existing pool.
        first.get_chunk_states(1, 1)
        assert list(db_pool._pools) == [first.dbname]
    finally:
        chunk_workflow._default_workflow = None
        db_pool.close_all_pools()
