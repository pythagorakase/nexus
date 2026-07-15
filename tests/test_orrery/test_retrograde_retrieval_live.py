"""Opt-in real-Postgres proof for dedicated Retrograde summary retrieval.

The test database must already contain migration 078, at least one embedded
Retrograde summary, and the corresponding configured local embedding model.
It is deliberately read-only and refuses every production/save-slot database.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import psycopg2
import pytest

from nexus.agents.memnon.memnon import MEMNON


TEST_DB_URL = os.environ.get("NEXUS_RETROGRADE_RETRIEVAL_TEST_DB_URL")

pytestmark = [
    pytest.mark.live,
    pytest.mark.requires_postgres,
    pytest.mark.skipif(
        not TEST_DB_URL,
        reason="NEXUS_RETROGRADE_RETRIEVAL_TEST_DB_URL is not configured",
    ),
]


def _require_disposable_database(db_url: str) -> None:
    """Reject every known user/runtime database before opening a connection."""
    database = urlparse(db_url).path.lstrip("/")
    protected = {"NEXUS", *(f"save_{slot:02d}" for slot in range(1, 6))}
    if database in protected or not database.startswith("test_"):
        raise RuntimeError(
            "Retrograde retrieval live tests require a disposable database "
            "whose name starts with 'test_'; got "
            f"{database!r}"
        )


def test_retrograde_history_comes_back_with_typed_identity() -> None:
    """Production hybrid search retrieves a pre-embedded summary as itself."""
    assert TEST_DB_URL is not None
    _require_disposable_database(TEST_DB_URL)

    with psycopg2.connect(TEST_DB_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, summary_text
                FROM retrograde_summaries
                WHERE embedding_generated_at IS NOT NULL
                ORDER BY id
                LIMIT 1
                """
            )
            row = cursor.fetchone()
    assert row is not None, "fixture database has no embedded Retrograde summary"
    summary_id, summary_text = int(row[0]), str(row[1])
    query = " ".join(summary_text.split()[:16])

    memnon = MEMNON(interface=None, db_url=TEST_DB_URL)
    try:
        result = memnon.query_memory(query=query, k=15, use_hybrid=True)
    finally:
        memnon.close()

    matching = [
        candidate
        for candidate in result["results"]
        if candidate.get("id") == f"retrograde_summary:{summary_id}"
    ]
    assert matching, (
        "Dedicated Retrograde summary was not retrieved; "
        f"summary_id={summary_id}, returned_ids="
        f"{[candidate.get('id') for candidate in result['results']]}"
    )
    assert matching[0]["content_type"] == "retrograde_summary"
    assert matching[0]["summary_id"] == summary_id
    assert "chunk_id" not in matching[0]
