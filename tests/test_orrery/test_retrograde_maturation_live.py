"""Live end-to-end test for runtime Retrograde stub maturation on a clone.

Skipped unless ``NEXUS_RUN_LIVE_LLM=1`` is set. Makes real frontier calls
(R4 seed generation + R6 expansion) and commits real rows to a disposable
template clone that ``maturation_story`` seeds with a persisted wizard setting
and a clocked head chunk and routes under ``ROUTED_SLOT``; the clone is
dropped afterward, so no owner slot is written. Each run declares a uniquely
named entity. The enqueue and
idempotency path this test drives before its first model call, and the drain's
job-context and story-setting loads, are proven without the live opt-in in
``tests/test_live_gate_clones_pg.py``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.retrograde_maturation import (
    drain_maturation_jobs_sync,
    enqueue_declared_entity_maturations,
)
from nexus.database import database_url
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_story_clock,
    seed_story_setting,
)

pytestmark = [pytest.mark.live, pytest.mark.live_llm, pytest.mark.requires_postgres]

# The slot label the clone is routed under; maturation jobs record it and the
# drain resolves its connection through it.
ROUTED_SLOT = 4
WORLD_TIME = datetime(2073, 8, 1, 12, 0, tzinfo=timezone.utc)
# Maturation reads the persisted wizard setting before its first model call;
# its genre selects the Retrograde weird band.
SETTING_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "slot3_midnight_qa_wizard_cache.json"
)


@dataclass(frozen=True)
class MaturationStory:
    """The clone and the head chunk ``seed_maturation_story`` committed."""

    dbname: str
    chunk_id: int


def seed_maturation_story(
    dbname: str, patch: Callable[[Any, str, Any], None]
) -> MaturationStory:
    """Persist a setting, clock one head chunk, and route ``ROUTED_SLOT``."""

    route_slot_to_disposable(patch, slot=ROUTED_SLOT, dbname=dbname)
    seed_story_setting(
        dbname, setting=json.loads(SETTING_FIXTURE.read_text())["setting"]
    )
    chunk_id = seed_story_clock(
        dbname,
        world_time=WORLD_TIME,
        raw_text="The archive stacks settle into their night silence.",
    )
    return MaturationStory(dbname=dbname, chunk_id=chunk_id)


def archivist_declaration(name: str) -> dict[str, str]:
    """The Skald new-entity declaration this module matures."""

    return {
        "kind": "character",
        "name": name,
        "summary": (
            "A reclusive records broker who trades in pre-Pulse municipal "
            "archives and remembers debts nobody else does."
        ),
    }


@pytest.fixture()
def maturation_story(monkeypatch: pytest.MonkeyPatch) -> Iterator[MaturationStory]:
    """A routed clone with the source story pins preserved for live models."""

    with disposable_slot_database("qa640_maturation_live", story_pin=None) as dbname:
        monkeypatch.setenv("NEXUS_SLOT", str(ROUTED_SLOT))
        yield seed_maturation_story(dbname, monkeypatch.setattr)


@pytest.fixture()
def maturation_conn(maturation_story: MaturationStory) -> Iterator[Any]:
    with closing(connect(maturation_story.dbname)) as conn:
        yield conn


def test_live_maturation_end_to_end(
    maturation_story: MaturationStory, maturation_conn: Any
) -> None:
    """A declared entity matures into persisted, embedded Retrograde history."""

    suffix = uuid.uuid4().hex[:8]
    name = f"Archivist Veil-{suffix}"
    declaration = archivist_declaration(name)
    chunk_id = maturation_story.chunk_id

    result = enqueue_declared_entity_maturations(
        maturation_conn,
        declarations=[declaration],
        chunk_id=chunk_id,
        raw_text=f"{name} surfaces from the archive stacks with a ledger.",
        slot=ROUTED_SLOT,
    )
    maturation_conn.commit()
    assert result.stubs_created == 1
    assert result.jobs_enqueued == 1

    matured, failed = drain_maturation_jobs_sync(slot=ROUTED_SLOT, limit=10)
    assert failed == 0
    assert matured >= 1

    with maturation_conn.cursor(cursor_factory=RealDictCursor) as cur:
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
    # and embedded dedicated summaries on MEMNON's retrieval surface.
    with maturation_conn.cursor(cursor_factory=RealDictCursor) as cur:
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

        pending = manifest.get("embedding_pending_summary_ids") or []
        if pending:
            cur.execute(
                """
                SELECT count(*) AS n
                FROM retrograde_summaries
                WHERE id = ANY(%s) AND embedding_generated_at IS NOT NULL
                """,
                (pending,),
            )
            assert int(cur.fetchone()["n"]) == len(pending)

    # MEMNON retrieves the matured history through the production search.
    if pending:
        from nexus.agents.memnon.memnon import MEMNON

        memnon = MEMNON(interface=None, db_url=database_url(maturation_story.dbname))
        search = memnon.query_memory(query=name, k=15, use_hybrid=True)
        returned_ids = {
            int(item["summary_id"])
            for item in search["results"]
            if item.get("content_type") == "retrograde_summary"
        }
        assert returned_ids & set(pending), (
            "MEMNON did not retrieve the matured history: "
            f"summaries={sorted(pending)} returned={sorted(returned_ids)}"
        )

    # Idempotency: a matured entity never re-matures.
    rerun = enqueue_declared_entity_maturations(
        maturation_conn,
        declarations=[declaration],
        chunk_id=chunk_id,
        raw_text=f"{name} appears again.",
        slot=ROUTED_SLOT,
    )
    maturation_conn.commit()
    assert rerun.jobs_enqueued == 0
    assert rerun.jobs_already_present == 1
