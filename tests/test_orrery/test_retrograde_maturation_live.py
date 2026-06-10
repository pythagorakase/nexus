"""Live end-to-end test for runtime Retrograde stub maturation on save_02.

Skipped unless ``NEXUS_RUN_LIVE_LLM=1`` is set. Makes real frontier calls
(R4 seed generation + R6 expansion) and commits real rows to save_02 — the
writable working slot. Each run declares a uniquely named entity so the
per-entity idempotency boundary never blocks repeat runs.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterator

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.retrograde_maturation import (
    drain_maturation_jobs_sync,
    enqueue_declared_entity_maturations,
)

SAVE_02_DSN = "postgresql://pythagor@localhost:5432/save_02"

pytestmark = [pytest.mark.live, pytest.mark.live_llm, pytest.mark.requires_postgres]


@pytest.fixture()
def save_02_conn() -> Iterator[Any]:
    conn = psycopg2.connect(SAVE_02_DSN)
    try:
        yield conn
    finally:
        conn.close()


def test_live_maturation_end_to_end(save_02_conn: Any) -> None:
    """A declared entity matures into persisted, embedded Retrograde history."""

    suffix = uuid.uuid4().hex[:8]
    name = f"Archivist Veil-{suffix}"
    declaration = {
        "kind": "character",
        "name": name,
        "summary": (
            "A reclusive records broker who trades in pre-Pulse municipal "
            "archives and remembers debts nobody else does."
        ),
    }

    with save_02_conn.cursor() as cur:
        cur.execute("SELECT max(id) FROM narrative_chunks")
        chunk_id = int(cur.fetchone()[0])

    result = enqueue_declared_entity_maturations(
        save_02_conn,
        declarations=[declaration],
        chunk_id=chunk_id,
        raw_text=f"{name} surfaces from the archive stacks with a ledger.",
        slot=2,
    )
    save_02_conn.commit()
    assert result.stubs_created == 1
    assert result.jobs_enqueued == 1

    matured, failed = drain_maturation_jobs_sync(slot=2, limit=10)
    assert failed == 0
    assert matured >= 1

    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT state::text AS state, result_manifest
            FROM orrery_maturation_jobs
            WHERE entity_name = %s
            """,
            (name,),
        )
        job = cur.fetchone()
    assert job is not None
    assert job["state"] == "succeeded"
    manifest = job["result_manifest"]
    assert manifest["persisted"] is True
    assert manifest["world_event_ids"], "Maturation must persist world events"
    assert manifest["embedding"]["status"] in {"succeeded", "none_pending"}

    # The matured history is real world_events rows with retrograde source
    # and embedded summary chunks (MEMNON's chunk-search surface).
    with save_02_conn.cursor(cursor_factory=RealDictCursor) as cur:
        event_ids = list(manifest["world_event_ids"].values())
        cur.execute(
            """
            SELECT count(*) AS n
            FROM world_events
            WHERE id = ANY(%s) AND source = 'retrograde'::event_source_kind
            """,
            (event_ids,),
        )
        assert int(cur.fetchone()["n"]) == len(event_ids)

        pending = manifest.get("embedding_pending_chunk_ids") or []
        if pending:
            cur.execute(
                """
                SELECT count(*) AS n
                FROM narrative_chunks
                WHERE id = ANY(%s) AND embedding_generated_at IS NOT NULL
                """,
                (pending,),
            )
            assert int(cur.fetchone()["n"]) == len(pending)

    # MEMNON retrieves the matured history through the production search.
    if pending:
        from nexus.agents.memnon.memnon import MEMNON

        memnon = MEMNON(interface=None, db_url=SAVE_02_DSN)
        search = memnon.query_memory(query=name, k=15, use_hybrid=True)
        returned_ids = {
            int(chunk.get("chunk_id") or chunk["id"]) for chunk in search["results"]
        }
        assert returned_ids & set(pending), (
            "MEMNON did not retrieve the matured history: "
            f"summary_chunks={sorted(pending)} returned={sorted(returned_ids)}"
        )

    # Idempotency: a matured entity never re-matures.
    rerun = enqueue_declared_entity_maturations(
        save_02_conn,
        declarations=[declaration],
        chunk_id=chunk_id,
        raw_text=f"{name} appears again.",
        slot=2,
    )
    save_02_conn.commit()
    assert rerun.jobs_enqueued == 0
    assert rerun.jobs_already_present == 1
