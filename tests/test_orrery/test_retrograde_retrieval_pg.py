"""PostgreSQL-gated tests for the Retrograde retrieval surface on save_05.

These tests run real SQL against save_05 inside transactions that are always
rolled back, so the slot state is untouched. They are skipped unless
``NEXUS_RUN_POSTGRES=1`` is set.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Iterator

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.orrery.retrograde_markers import (
    RETROGRADE_PROLOGUE_MARKER,
    RETROGRADE_SUMMARY_MARKER,
    retrograde_event_marker,
)
from nexus.agents.orrery.retrograde_persistence import (
    _insert_character_stub,
    _insert_faction_stub,
    _insert_place_stub,
    plan_retrograde_summary_chunks,
)

SAVE_05_DSN = "postgresql://pythagor@localhost:5432/save_05"

pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def save_05_cursor() -> Iterator[Any]:
    """Open a save_05 cursor whose transaction is always rolled back."""

    conn = psycopg2.connect(SAVE_05_DSN)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
    finally:
        conn.rollback()
        conn.close()


def _retrograde_event_count(cur: Any) -> int:
    cur.execute(
        """
        SELECT count(*) AS n
        FROM world_events
        WHERE source = 'retrograde'::event_source_kind
        """
    )
    return int(cur.fetchone()["n"])


def test_summary_chunks_cover_every_retrograde_event(save_05_cursor: Any) -> None:
    """Execute mode leaves every Retrograde event with a finalized chunk."""

    cur = save_05_cursor
    event_count = _retrograde_event_count(cur)
    if event_count == 0:
        pytest.skip(
            "save_05 holds no Retrograde events (dev slot reset since the "
            "last cold start) — run the wizard cold start to restore coverage"
        )

    rows = plan_retrograde_summary_chunks(cur, dry_run=False)

    assert len(rows) == event_count
    slugs: list[str] = []
    for row in rows:
        assert row["status"] in {"inserted", "already_present"}
        assert row["chunk_id"] is not None

        cur.execute(
            """
            SELECT nc.raw_text, nc.storyteller_text, nc.authorial_directives,
                   nc.state, cm.season, cm.episode, cm.world_layer::text AS layer,
                   cm.slug, cm.world_time
            FROM narrative_chunks nc
            JOIN chunk_metadata cm ON cm.chunk_id = nc.id
            WHERE nc.id = %s
            """,
            (row["chunk_id"],),
        )
        chunk = cur.fetchone()
        assert chunk is not None
        directives = chunk["authorial_directives"]
        assert RETROGRADE_SUMMARY_MARKER in directives
        assert retrograde_event_marker(row["event_ref"]) in directives
        assert chunk["state"] == "finalized"
        assert chunk["raw_text"] == chunk["storyteller_text"]
        assert chunk["season"] == 0
        assert chunk["episode"] == 0
        assert chunk["layer"] == "primary"
        # slug comes from the set_chunk_slug trigger; world_time from the
        # statement-level cumulative time_delta recompute.
        assert str(chunk["slug"]).startswith("S00E00_")
        assert chunk["world_time"] is not None
        slugs.append(str(chunk["slug"]))

        cur.execute(
            """
            SELECT payload ->> 'summary' AS summary,
                   payload ->> 'retrograde_summary_chunk_id' AS linked_chunk
            FROM world_events
            WHERE id = %s
            """,
            (row["world_event_id"],),
        )
        event = cur.fetchone()
        assert event["summary"] == chunk["raw_text"]
        if row["status"] == "inserted":
            assert int(event["linked_chunk"]) == row["chunk_id"]

    assert len(set(slugs)) == len(slugs), f"summary slugs must be unique: {slugs}"


def test_summary_chunk_planning_is_idempotent(save_05_cursor: Any) -> None:
    """A second execute pass reports already_present with stable chunk ids."""

    cur = save_05_cursor
    first = plan_retrograde_summary_chunks(cur, dry_run=False)
    second = plan_retrograde_summary_chunks(cur, dry_run=False)

    assert [row["event_ref"] for row in first] == [row["event_ref"] for row in second]
    assert all(row["status"] == "already_present" for row in second)
    assert [row["chunk_id"] for row in first] == [row["chunk_id"] for row in second]


def test_dry_run_is_read_only(save_05_cursor: Any) -> None:
    """Dry-run planning works inside a READ ONLY transaction."""

    cur = save_05_cursor
    cur.execute("SET TRANSACTION READ ONLY")
    rows = plan_retrograde_summary_chunks(cur, dry_run=True)

    assert len(rows) == _retrograde_event_count(cur)
    assert all(row["status"] in {"would_insert", "already_present"} for row in rows)


def test_entity_stub_inserts_match_live_schema(save_05_cursor: Any) -> None:
    """Stub INSERT column lists stay aligned with the live slot schema.

    Regression coverage for migration 058 (retire faction legacy columns):
    the faction stub used to write factions.current_activity, which no
    longer exists, so execute-mode stub creation crashed on current schema.
    """

    cur = save_05_cursor
    sources = [{"plan": "event_plan", "event_ref": "pg_test", "role": "actor"}]

    _insert_faction_stub(cur, entity_ref="M3 PG Test Faction", sources=sources)
    cur.execute(
        "SELECT summary, extra_data, entity_id FROM factions WHERE name = %s",
        ("M3 PG Test Faction",),
    )
    faction = cur.fetchone()
    assert faction is not None
    assert faction["entity_id"] is not None
    assert faction["extra_data"]["source"] == "retrograde"
    assert "faction stub" in faction["summary"]

    _insert_character_stub(cur, entity_ref="M3 PG Test Character", sources=sources)
    cur.execute(
        "SELECT extra_data, entity_id FROM characters WHERE name = %s",
        ("M3 PG Test Character",),
    )
    character = cur.fetchone()
    assert character is not None
    assert character["entity_id"] is not None
    assert character["extra_data"]["source"] == "retrograde"

    _insert_place_stub(cur, entity_ref="M3 PG Test Place", sources=sources)
    cur.execute(
        "SELECT extra_data, entity_id FROM places WHERE name = %s",
        ("M3 PG Test Place",),
    )
    place = cur.fetchone()
    assert place is not None
    assert place["entity_id"] is not None
    assert place["extra_data"]["source"] == "retrograde"


def test_recent_chunks_surface_excludes_retrograde_history() -> None:
    """The recency surface never returns Retrograde prologue chunks."""

    engine = create_engine(SAVE_05_DSN)
    try:
        memnon = SimpleNamespace(Session=sessionmaker(bind=engine))
        result = MEMNON.get_recent_chunks(memnon, limit=500)

        returned_ids = {int(chunk["id"]) for chunk in result["results"]}
        with engine.connect() as conn:
            marked = conn.exec_driver_sql(
                """
                SELECT id
                FROM narrative_chunks
                WHERE authorial_directives @> %(prologue)s::jsonb
                   OR authorial_directives @> %(summary)s::jsonb
                """,
                {
                    "prologue": json.dumps([RETROGRADE_PROLOGUE_MARKER]),
                    "summary": json.dumps([RETROGRADE_SUMMARY_MARKER]),
                },
            ).fetchall()
        marked_ids = {int(row[0]) for row in marked}

        if not marked_ids:
            pytest.skip(
                "save_05 holds no Retrograde prologue anchor (dev slot reset "
                "since the last cold start) — run the wizard cold start to "
                "restore coverage"
            )
        assert returned_ids.isdisjoint(marked_ids)
    finally:
        engine.dispose()
