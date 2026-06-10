"""Live Orrery cycle integration test on slot 2.

Exercises Resolve -> Commit (with Clear's expiry sweep) -> Promote ->
Narrate -> Bleed against the real ``save_02`` database with a real frontier
narration call. Skipped unless both ``NEXUS_RUN_LIVE_LLM=1`` and
``NEXUS_RUN_POSTGRES=1`` are set.

The test commits one synthetic high-salience resolution (real entity, valid
template) so Promote is guaranteed a row above the configured thresholds
regardless of current story state, then cleans up every row it created.
Resolve runs read-only against live world state. Narration drains are
bounded to at most ten single-job iterations so ambient outbox backlog
cannot turn the test into an unbounded API spend.
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
PROMOTION_DRAIN_ATTEMPTS = 20
NARRATION_DRAIN_ATTEMPTS = 10

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
    conn: Any = None
    created_resolution_ids: list[int] = []
    try:
        session_factory = sessionmaker(engine)

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
        assert proposal.actor_count >= 1, "Mature slot 2 must bind live actors"

        conn = _connect()
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM entities ORDER BY id LIMIT 1")
                actor_entity_id = int(cur.fetchone()["id"])

        # Stages 2+3 - Commit: materialize a synthetic salient draft stamped
        # to the anchor chunk; Clear's scheduled-expiry sweep runs inside the
        # same commit transaction. The unique binding hash keeps reruns
        # idempotent. Magnitude is set high so the Bleed selector's
        # tick-then-magnitude ordering deterministically ranks this row.
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
            magnitude=0.9,
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
            # Capture the id inside the commit transaction so cleanup can
            # never miss a row that made it to disk.
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
        # The worker drains pending rows oldest-tick first, so loop (bounded)
        # until any pre-existing backlog ahead of the synthetic row is
        # processed rather than relying on a single global limit.
        promoted_row = None
        for _attempt in range(PROMOTION_DRAIN_ATTEMPTS):
            promoted, skipped = promote_pending_resolutions_sync(
                LIVE_SLOT,
                limit=50,
                settings=settings,
                conn=conn,
            )
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
            if promoted_row["promotion_status"] != "pending":
                break
            if promoted == 0 and skipped == 0:
                break  # nothing left to drain; assertions below fail loudly
        assert promoted_row is not None
        assert promoted_row["promotion_status"] == "promoted"
        assert promoted_row["narration_status"] == "queued"
        assert "Deterministic promotion" in promoted_row["reason"]

        # Stage 5 - Narrate: real frontier call via the durable outbox.
        # Single-job drains keep total API spend bounded by the attempt cap
        # even when the outbox holds unrelated queued jobs; assertions are
        # scoped to the synthetic row, not global drain counters.
        narration = None
        for _attempt in range(NARRATION_DRAIN_ATTEMPTS):
            narrated, failed = drain_narration_outbox_sync(
                LIVE_SLOT,
                limit=1,
                settings=settings,
                conn=conn,
            )
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
            if narration is not None:
                break
            if narrated == 0 and failed == 0:
                break  # outbox idle without our row; assertions fail loudly
        assert narration is not None, (
            "Narration outbox drained without producing a narration for the "
            f"synthetic resolution {resolution_id}"
        )
        assert len(narration["text"].strip()) > 40
        assert narration["embedding_status"] == "pending"

        # Stage 6 - Bleed: the synthetic narrated resolution must propagate
        # into the deterministic ambient menu for the next turn.
        with session_factory() as session:
            menu = select_bleed_menu(
                session,
                anchor_chunk_id=anchor_chunk_id,
                max_candidates=int(orrery_settings["bleed"]["max_candidates"]),
            )
        selected_resolution_ids = {
            candidate.resolution_id for candidate in menu.selected
        }
        assert resolution_id in selected_resolution_ids
    finally:
        if conn is not None:
            _cleanup_resolutions(conn, created_resolution_ids)
            conn.close()
        engine.dispose()
