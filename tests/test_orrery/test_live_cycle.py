"""Live Orrery cycle integration test on slot 2.

Exercises Resolve -> Commit -> Promote -> Narrate -> Bleed against the real
``save_02`` database with a real frontier narration call. Skipped unless both
``NEXUS_RUN_LIVE_LLM=1`` and ``NEXUS_RUN_POSTGRES=1`` are set.

The test commits one synthetic high-salience resolution (real entity, valid
template) so Promote is guaranteed a row above the configured thresholds
regardless of current story state, then cleans up every row it created.
Resolve runs read-only against live world state. Narration drain may also
process unrelated queued jobs - that is the worker's actual contract.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from nexus.agents.orrery.bleed import select_bleed_menu
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryTickProposal,
    resolve_dry_run,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.agents.orrery.worker import (
    drain_narration_outbox_sync,
    promote_pending_resolutions_sync,
)
from nexus.api.slot_utils import get_slot_db_url
from nexus.config import load_settings_as_dict

LIVE_SLOT = 2

pytestmark = [pytest.mark.live_llm, pytest.mark.requires_postgres]


def _connect() -> Any:
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=f"save_{LIVE_SLOT:02d}",
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )


def _cleanup_resolutions(conn: Any, resolution_ids: list[int]) -> None:
    if not resolution_ids:
        return
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE orrery_resolutions
                SET narration_chunk_id = NULL
                WHERE id = ANY(%s)
                """,
                (resolution_ids,),
            )
            cur.execute(
                "DELETE FROM offscreen_narrations WHERE resolution_id = ANY(%s)",
                (resolution_ids,),
            )
            cur.execute(
                "DELETE FROM orrery_narration_jobs WHERE resolution_id = ANY(%s)",
                (resolution_ids,),
            )
            cur.execute(
                "DELETE FROM world_events WHERE resolution_id = ANY(%s)",
                (resolution_ids,),
            )
            cur.execute(
                "DELETE FROM orrery_resolutions WHERE id = ANY(%s)",
                (resolution_ids,),
            )


def test_live_orrery_cycle_resolve_commit_promote_narrate_bleed() -> None:
    """The full Orrery pipeline runs live on slot 2 with config thresholds."""

    settings = load_settings_as_dict()
    orrery_settings = settings["orrery"]
    assert orrery_settings["enabled"] is True, "Orrery must ship default-on"
    promote_settings = orrery_settings["promote"]
    priority_threshold = float(promote_settings["priority_threshold"])

    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT))
    session_factory = sessionmaker(bind=engine)

    # Stage 1 - Resolve: read-only dry run against live world state.
    with session_factory() as session:
        anchor_row = (
            session.execute(text("SELECT max(id) AS max_id FROM narrative_chunks"))
            .mappings()
            .first()
        )
        assert anchor_row is not None and anchor_row["max_id"] is not None
        anchor_chunk_id = int(anchor_row["max_id"])
        proposal = resolve_dry_run(
            session,
            BUILTIN_TEMPLATES,
            anchor_chunk_id=anchor_chunk_id,
            window_chunks=int(orrery_settings["binding"]["window_chunks"]),
            sunhelm_settings=orrery_settings.get("sunhelm"),
        )
    assert proposal.anchor_chunk_id == anchor_chunk_id
    assert proposal.actor_count >= 0

    conn = _connect()
    created_resolution_ids: list[int] = []
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM entities ORDER BY id LIMIT 1")
                actor_entity_id = int(cur.fetchone()["id"])

        # Stage 2 - Commit: materialize a synthetic salient draft stamped to
        # the anchor chunk. The unique binding hash keeps reruns idempotent.
        binding_hash = f"live-cycle-{uuid.uuid4().hex}"
        salient_draft = OrreryResolutionDraft(
            template_id="hide",
            priority=int(priority_threshold) + 1,
            binding_hash=binding_hash,
            bindings={"actor": actor_entity_id},
            branch_label="Live-cycle integration probe",
            narrative_stub=(
                "{actor} drops out of sight for a few hours, testing how far "
                "the city's attention can be made to slide off."
            ),
            magnitude=0.2,
        )
        synthetic_proposal = OrreryTickProposal(
            anchor_chunk_id=anchor_chunk_id,
            actor_count=1,
            resolutions=(salient_draft,),
        )
        with conn:
            result = commit_orrery_tick_sync(
                conn,
                synthetic_proposal,
                tick_chunk_id=anchor_chunk_id,
                slot=LIVE_SLOT,
                sunhelm_settings=orrery_settings.get("sunhelm"),
            )
        assert result.resolution_count == 1

        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, promotion_status FROM orrery_resolutions
                    WHERE binding_hash = %s
                    """,
                    (binding_hash,),
                )
                row = cur.fetchone()
        resolution_id = int(row["id"])
        created_resolution_ids.append(resolution_id)
        assert row["promotion_status"] == "pending"

        # Stage 4 - Promote: deterministic discriminator with config values.
        promoted, _skipped = promote_pending_resolutions_sync(
            LIVE_SLOT,
            limit=50,
            settings=settings,
            conn=conn,
        )
        assert promoted >= 1
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT promotion_status, narration_status,
                           promotion_verdict->>'reason' AS reason
                    FROM orrery_resolutions WHERE id = %s
                    """,
                    (resolution_id,),
                )
                promoted_row = cur.fetchone()
        assert promoted_row["promotion_status"] == "promoted"
        assert promoted_row["narration_status"] == "queued"
        assert "Deterministic promotion" in promoted_row["reason"]

        # Stage 5 - Narrate: real frontier call via the durable outbox.
        narrated, failed = drain_narration_outbox_sync(
            LIVE_SLOT,
            limit=20,
            settings=settings,
            conn=conn,
        )
        assert failed == 0
        assert narrated >= 1
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT text, embedding_status FROM offscreen_narrations
                    WHERE resolution_id = %s
                    """,
                    (resolution_id,),
                )
                narration = cur.fetchone()
        assert narration is not None
        assert len(narration["text"].strip()) > 40
        assert narration["embedding_status"] == "pending"

        # Stage 6 - Bleed: the narrated resolution is a deterministic
        # candidate for the next turn's ambient menu.
        with session_factory() as session:
            menu = select_bleed_menu(
                session,
                anchor_chunk_id=anchor_chunk_id,
                max_candidates=int(orrery_settings["bleed"]["max_candidates"]),
            )
        assert menu.candidates_considered >= 1
    finally:
        _cleanup_resolutions(conn, created_resolution_ids)
        conn.close()
        engine.dispose()
