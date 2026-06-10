"""Live retrieval proof: Retrograde history comes back from MEMNON search.

This test commits Retrograde summary chunks on save_05 (idempotent), embeds
any pending ones through the standard chunk embedding lifecycle (a real
Octen-Embedding-4B run via scripts/regenerate_embeddings.py), then runs the
production MEMNON hybrid search path and asserts a retrograde-sourced chunk
is retrieved. Skipped unless ``NEXUS_RUN_LIVE_LLM=1`` and
``NEXUS_RUN_POSTGRES=1`` are both set.
"""

from __future__ import annotations

from typing import Any

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.orrery.retrograde_embedding import (
    embed_retrograde_summary_chunks,
)
from nexus.agents.orrery.retrograde_persistence import (
    plan_retrograde_summary_chunks,
)

SAVE_05_DSN = "postgresql://pythagor@localhost:5432/save_05"
SAVE_05_DBNAME = "save_05"

pytestmark = [pytest.mark.live, pytest.mark.requires_postgres]

# Phrased near the persisted retrograde event summaries on save_05 without
# quoting any of them verbatim, so the hit has to come from semantic and
# keyword relevance rather than string identity.
RETROGRADE_QUERY = (
    "How did Mara's safe aliases end up carrying Vale's debt after Vale "
    "disappeared through the shelter network?"
)


def _ensure_summary_chunks_committed() -> list[dict[str, Any]]:
    conn = psycopg2.connect(SAVE_05_DSN)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows = plan_retrograde_summary_chunks(cur, dry_run=False)
        conn.commit()
        return rows
    finally:
        conn.close()


def test_retrograde_history_comes_back_from_memnon_search() -> None:
    """A retrograde-sourced memory is retrieved by the production search."""

    rows = _ensure_summary_chunks_committed()
    assert rows, "save_05 holds no persisted Retrograde events to retrieve"

    summary_chunk_ids = {int(row["chunk_id"]) for row in rows}
    pending = [int(row["chunk_id"]) for row in rows if row["embedding_pending"]]
    if pending:
        embedded = embed_retrograde_summary_chunks(SAVE_05_DBNAME, pending)
        assert {entry["chunk_id"] for entry in embedded} == set(pending)

    memnon = MEMNON(interface=None, db_url=SAVE_05_DSN)
    result = memnon.query_memory(
        query=RETROGRADE_QUERY,
        k=15,
        use_hybrid=True,
    )

    returned_ids = {
        int(chunk.get("chunk_id") or chunk["id"]) for chunk in result["results"]
    }
    hits = returned_ids & summary_chunk_ids
    assert hits, (
        "No Retrograde summary chunk retrieved. "
        f"summary_chunk_ids={sorted(summary_chunk_ids)} "
        f"returned_ids={sorted(returned_ids)}"
    )
