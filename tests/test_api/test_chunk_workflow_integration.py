"""PostgreSQL integration tests for chunk acceptance embedding handoff."""

from __future__ import annotations

from contextlib import closing

import pytest

from nexus.api import chunk_workflow, slot_utils
from nexus.api.chunk_workflow import ChunkState, ChunkWorkflow
from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def slot_database(monkeypatch):
    """Clone the corpus and apply pending migrations only to the disposable copy."""
    with disposable_slot_database(
        "qa640_800b_accept", source_db="save_04", include_data=True
    ) as dbname:
        monkeypatch.setattr(chunk_workflow, "VALID_DATABASES", {dbname})
        monkeypatch.setattr(slot_utils, "VALID_DBNAMES", {dbname})
        yield dbname


def test_accept_chunk_queues_background_embedding_with_real_slot_db(slot_database):
    """Acceptance commits one durable job without running local inference."""
    previous_id, current_id = 990001, 990002
    with closing(connect(slot_database)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO narrative_chunks (id, raw_text, state) VALUES "
            "(%s, 'temporary previous chunk', 'finalized'), "
            "(%s, 'temporary current chunk', 'pending_review')",
            (previous_id, current_id),
        )
    workflow = ChunkWorkflow(slot_database)
    response = workflow.accept_chunk(current_id, "test-session-issue-206")
    assert response.chunk_id == current_id
    assert response.state == ChunkState.FINALIZED
    assert response.previous_chunk_embedded is True
    assert (
        workflow.trigger_embedding_generation(previous_id) == response.embedding_job_id
    )
    with closing(connect(slot_database)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, state::text, attempts FROM narrative_embedding_jobs WHERE chunk_id=%s",
            (previous_id,),
        )
        assert cur.fetchall() == [(int(response.embedding_job_id), "queued", 0)]
        cur.execute(
            "SELECT state, finalized_at, embedding_generated_at FROM narrative_chunks WHERE id=%s",
            (current_id,),
        )
        state, finalized_at, embedded_at = cur.fetchone()
        assert state == "finalized" and finalized_at is not None and embedded_at is None


def test_default_workflow_singleton_reuses_one_pool(slot_database, monkeypatch) -> None:
    """get_default_workflow() must hand every caller one workflow and one pool.

    Guards the lazy-singleton invariant from issue #369: endpoint handlers
    (accept/reject/edit/states) all route through get_default_workflow(), so
    repeated access must never construct a fresh ChunkWorkflow or open an
    additional connection pool per request.
    """
    from functools import partial
    from nexus.api import db_pool

    monkeypatch.setattr(
        chunk_workflow, "ChunkWorkflow", partial(ChunkWorkflow, slot_database)
    )

    chunk_workflow._default_workflow = None
    db_pool.close_all_pools()
    try:
        first = chunk_workflow.get_default_workflow()
        second = chunk_workflow.get_default_workflow()
        assert first is second

        # Any real query forces pool creation; (1, 1) is an arbitrary
        # one-chunk range, not a boundary assertion.
        first.get_chunk_states(1, 1)
        assert list(db_pool._pools) == [first.dbname]
    finally:
        # close_all_pools() also clears the connect-timeout cache, so this
        # fully resets pool-related state for subsequent tests.
        chunk_workflow._default_workflow = None
        db_pool.close_all_pools()
