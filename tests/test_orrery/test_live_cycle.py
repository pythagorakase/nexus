"""Orrery cycle integration test on a seeded disposable clone.

Exercises Resolve -> Commit (with Clear's expiry sweep) -> Promote ->
Record -> Bleed against a template clone that ``live_cycle_story`` seeds
through the production paths: a played story whose accepted turns commit the
resolver's real proposals for an off-screen cast (a promotion backlog of
pending resolutions), plus one salient backlog resolution committed on an
earlier tick so the promotion drain enqueues a narration job ahead of the
test's own. The off-screen record stage is deterministic; this test keeps its
explicit live gate and is skipped unless both ``NEXUS_RUN_LIVE_LLM=1`` and
``NEXUS_RUN_POSTGRES=1`` are set. The clone is pinned to TEST and dropped
afterward, so no owner slot is read or written.

The test commits one synthetic high-salience resolution (seeded actor, valid
template) so Promote is guaranteed a row above the configured thresholds,
drains the seeded backlog ahead of it oldest-tick first, and asserts that the
backlog was processed as well as the synthetic row. Resolve runs read-only.
Narration drains are bounded to at most ten single-job iterations.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from typing import Any

import pytest
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from nexus.agents.orrery.bleed import (
    load_bleed_anchor_entity_ids,
    select_bleed_menu,
)
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
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_played_story,
)

# The slot label the clone is routed under for the production slot resolvers
# (get_slot_db_url, the worker drains' job labels).
ROUTED_SLOT = 4
PROMOTION_DRAIN_ATTEMPTS = 20
PROMOTION_BATCH = 3
NARRATION_DRAIN_ATTEMPTS = 10
CAST = ("Mara Voss", "Tobin Reyes")

pytestmark = [pytest.mark.live_llm, pytest.mark.requires_postgres]


@dataclass(frozen=True)
class LiveCycleStory:
    """The clone and the backlog ``live_cycle_story`` seeded into it."""

    dbname: str
    anchor_chunk_id: int
    cast_entity_ids: tuple[int, ...]
    backlog_resolution_ids: tuple[int, ...]
    salient_backlog_resolution_id: int


def _salient_draft(
    *, actor_entity_id: int, priority: int, label: str, magnitude: float
) -> OrreryResolutionDraft:
    return OrreryResolutionDraft(
        template_id="hide",
        priority=priority,
        binding_hash=f"live-cycle-{label}-{uuid.uuid4().hex}",
        bindings={"actor": actor_entity_id},
        branch_label=f"Live-cycle {label} probe",
        narrative_stub=(
            "{actor} drops out of sight for a few hours, testing how far "
            "the city's attention can be made to slide off."
        ),
        magnitude=magnitude,
    )


def seed_live_cycle_story(dbname: str) -> LiveCycleStory:
    """Seed a played story with an off-screen cast and a promotion backlog.

    Four accepted turns commit the resolver's own proposals for the cast
    (resolutions on ticks 2-4). One salient resolution for the second cast
    member is then committed on tick 2 through ``commit_orrery_tick_sync`` so
    the promotion drain enqueues a narration job for it ahead of the test's
    synthetic row. The slot must already be routed to ``dbname`` under
    ``ROUTED_SLOT``. The backlog is asserted pending with no narration job.
    """

    settings = load_settings_as_dict()
    priority_threshold = float(settings["orrery"]["promote"]["priority_threshold"])
    chunk_ids = seed_played_story(dbname, turns=4, cast=CAST, slot=ROUTED_SLOT)
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT entity_id FROM characters WHERE name = ANY(%s) ORDER BY id",
            (list(CAST),),
        )
        cast_entity_ids = tuple(int(row[0]) for row in cur.fetchall())
    assert len(cast_entity_ids) == len(CAST), "seed_played_story seeds the cast"
    backlog_draft = _salient_draft(
        actor_entity_id=cast_entity_ids[1],
        priority=int(priority_threshold) + 1,
        label="backlog",
        magnitude=0.5,
    )
    with closing(connect(dbname)) as conn:
        with conn:
            result = commit_orrery_tick_sync(
                conn,
                OrreryTickProposal(
                    anchor_chunk_id=chunk_ids[1],
                    actor_count=1,
                    resolutions=(backlog_draft,),
                ),
                tick_chunk_id=chunk_ids[1],
                slot=ROUTED_SLOT,
                sunhelm_settings=settings["orrery"].get("sunhelm"),
            )
        assert result.resolution_count == 1
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id FROM orrery_resolutions WHERE binding_hash = %s",
                (backlog_draft.binding_hash,),
            )
            salient_id = int(cur.fetchone()["id"])
            cur.execute(
                "SELECT id, promotion_status FROM orrery_resolutions ORDER BY id"
            )
            seeded = cur.fetchall()
            cur.execute("SELECT count(*) AS n FROM orrery_narration_jobs")
            queued_jobs = int(cur.fetchone()["n"])
    # Acceptance may skip a resolution outright (make_acquaintance); every
    # other seeded row is backlog the promotion drain must process.
    backlog_ids = tuple(
        int(row["id"]) for row in seeded if row["promotion_status"] == "pending"
    )
    assert salient_id in backlog_ids and len(backlog_ids) >= 2, (
        "seed_live_cycle_story must seed the accepted turns' pending "
        f"resolutions plus the salient backlog row; found {seeded!r}"
    )
    assert queued_jobs == 0, "no narration job exists before promotion"
    return LiveCycleStory(
        dbname=dbname,
        anchor_chunk_id=chunk_ids[-1],
        cast_entity_ids=cast_entity_ids,
        backlog_resolution_ids=backlog_ids,
        salient_backlog_resolution_id=salient_id,
    )


@pytest.fixture()
def live_cycle_story(monkeypatch: pytest.MonkeyPatch) -> Iterator[LiveCycleStory]:
    """A TEST-pinned clone routed under ``ROUTED_SLOT`` with the seeded backlog."""

    with disposable_slot_database("qa640_live_cycle") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=ROUTED_SLOT, dbname=dbname)
        monkeypatch.setenv("NEXUS_SLOT", str(ROUTED_SLOT))
        yield seed_live_cycle_story(dbname)


def test_live_orrery_cycle_resolve_commit_promote_narrate_bleed(
    live_cycle_story: LiveCycleStory,
) -> None:
    """The full Orrery pipeline runs on the seeded clone with config thresholds."""

    settings = load_settings_as_dict()
    orrery_settings = settings["orrery"]
    assert orrery_settings["enabled"] is True, "Orrery must ship default-on"
    promote_settings = orrery_settings["promote"]
    priority_threshold = float(promote_settings["priority_threshold"])

    story = live_cycle_story
    engine = create_engine(get_slot_db_url(slot=ROUTED_SLOT))
    conn: Any = None
    try:
        session_factory = sessionmaker(engine)

        # Stage 1 - Resolve: read-only dry run against the seeded world state.
        with session_factory() as session:
            anchor_row = (
                session.execute(text("SELECT max(id) AS max_id FROM narrative_chunks"))
                .mappings()
                .first()
            )
            assert anchor_row is not None and anchor_row["max_id"] is not None
            anchor_chunk_id = int(anchor_row["max_id"])
            assert anchor_chunk_id == story.anchor_chunk_id
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=int(orrery_settings["binding"]["window_chunks"]),
                sunhelm_settings=orrery_settings.get("sunhelm"),
            )
        assert proposal.anchor_chunk_id == anchor_chunk_id
        assert (
            proposal.actor_count >= 1
        ), "live_cycle_story's mentioned cast must bind as Orrery actors"

        conn = connect(story.dbname)
        actor_entity_id = story.cast_entity_ids[0]

        # Stages 2+3 - Commit: materialize a synthetic salient draft stamped
        # to the anchor chunk; Clear's scheduled-expiry sweep runs inside the
        # same commit transaction. Magnitude is set high so the Bleed
        # selector's tick-then-magnitude ordering deterministically ranks
        # this row.
        salient_draft = _salient_draft(
            actor_entity_id=actor_entity_id,
            priority=int(priority_threshold) + 1,
            label="integration",
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
                slot=ROUTED_SLOT,
                sunhelm_settings=orrery_settings.get("sunhelm"),
            )
            assert result.resolution_count == 1
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, promotion_status FROM orrery_resolutions
                    WHERE binding_hash = %s
                    """,
                    (salient_draft.binding_hash,),
                )
                row = cur.fetchone()
            resolution_id = int(row["id"])
        assert row["promotion_status"] == "pending"
        assert resolution_id not in story.backlog_resolution_ids

        # Stage 4 - Promote: deterministic discriminator with config values.
        # The worker drains pending rows oldest tick first (then priority) in
        # small batches, so the seeded backlog on earlier ticks is processed
        # before the synthetic row. Drain (bounded) until the worker is idle.
        drains = 0
        drained_to_idle = False
        for _attempt in range(PROMOTION_DRAIN_ATTEMPTS):
            promoted, skipped = promote_pending_resolutions_sync(
                ROUTED_SLOT,
                limit=PROMOTION_BATCH,
                settings=settings,
                conn=conn,
            )
            drains += 1
            if promoted == 0 and skipped == 0:
                drained_to_idle = True
                break
        assert drained_to_idle, "the promotion backlog did not drain"
        assert drains > 2, "the seeded backlog must take more than one batch"
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
        assert promoted_row is not None
        assert promoted_row["promotion_status"] == "promoted"
        assert promoted_row["narration_status"] == "queued"
        assert "Deterministic promotion" in promoted_row["reason"]

        # The seeded backlog ahead of the synthetic row was processed: the
        # accepted turns' mundane resolutions were skipped below the
        # thresholds and the salient backlog row was promoted and queued.
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, promotion_status, narration_status
                    FROM orrery_resolutions WHERE id = ANY(%s)
                    ORDER BY id
                    """,
                    (list(story.backlog_resolution_ids),),
                )
                backlog = {int(r["id"]): r for r in cur.fetchall()}
                cur.execute(
                    """
                    SELECT resolution_id FROM orrery_narration_jobs
                    ORDER BY available_at, id
                    """
                )
                job_order = [int(r["resolution_id"]) for r in cur.fetchall()]
        assert set(backlog) == set(story.backlog_resolution_ids)
        assert all(row["promotion_status"] != "pending" for row in backlog.values())
        salient_backlog = backlog.pop(story.salient_backlog_resolution_id)
        assert salient_backlog["promotion_status"] == "promoted"
        assert salient_backlog["narration_status"] == "queued"
        assert backlog and all(
            row["promotion_status"] == "skipped" for row in backlog.values()
        ), f"live_cycle_story's mundane backlog must skip: {backlog!r}"
        assert job_order == [story.salient_backlog_resolution_id, resolution_id], (
            "the backlog's narration job must queue ahead of the synthetic row's: "
            f"{job_order!r}"
        )

        # Stage 5 - Record: deterministic descriptor via the durable outbox.
        # Single-job drains keep total work bounded by the attempt cap; the
        # seeded backlog job is ahead of the synthetic row's in the outbox.
        narration = None
        narrated_total = 0
        for _attempt in range(NARRATION_DRAIN_ATTEMPTS):
            narrated, failed = drain_narration_outbox_sync(
                ROUTED_SLOT,
                limit=1,
                settings=settings,
                conn=conn,
            )
            narrated_total += narrated
            assert failed == 0
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT text, perceptual_descriptor, embedding_status
                        FROM offscreen_narrations
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
        assert json.loads(narration["text"]) == narration["perceptual_descriptor"]
        assert (
            narration["perceptual_descriptor"]["record_kind"]
            == "deterministic_descriptor"
        )
        assert narration["embedding_status"] == "pending"
        assert narrated_total == 2, "the backlog job drains before the synthetic job"
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT n.resolution_id, j.state::text AS state
                    FROM offscreen_narrations n
                    JOIN orrery_narration_jobs j ON j.resolution_id = n.resolution_id
                    ORDER BY n.id
                    """
                )
                narrated_rows = [
                    (int(r["resolution_id"]), r["state"]) for r in cur.fetchall()
                ]
        assert [resolution for resolution, _ in narrated_rows] == [
            story.salient_backlog_resolution_id,
            resolution_id,
        ]
        assert {state for _, state in narrated_rows} == {"succeeded"}

        # Stage 6 - Bleed: the synthetic narrated resolution must propagate
        # into the deterministic ambient menu for the next turn.
        with session_factory() as session:
            bleed_settings = orrery_settings["bleed"]
            menu = select_bleed_menu(
                session,
                anchor_chunk_id=anchor_chunk_id,
                anchor_entity_ids=load_bleed_anchor_entity_ids(
                    session,
                    anchor_chunk_id=anchor_chunk_id,
                ),
                density=1.0,
                max_candidates=int(bleed_settings["max_candidates"]),
                near_distance_max=int(bleed_settings["near_distance_max"]),
                reserved_remote_slots=int(bleed_settings["reserved_remote_slots"]),
                scan_limit=24,
            )
        selected_resolution_ids = {
            candidate.resolution_id for candidate in menu.selected
        }
        assert resolution_id in selected_resolution_ids
    finally:
        if conn is not None:
            conn.close()
        engine.dispose()
