"""Tests for branch signal emissions — the live package-to-package chains.

Before this feature, threat_issued / compliance_alert / encoded_message were
gate-consumed but never emitted: package chaining was aspirational. A branch
signal is a second, additive world-event emission (the deed keeps its own
event_type and cooldowns; the signal is what the act gives off). The live
test drives the real commit path and then proves the chain input: the
consuming gate's predicate sees the signal on real slot state.
"""

from __future__ import annotations

import os
import uuid

import psycopg2
import pytest

from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryTickProposal,
)
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    DriveBand,
    Slot,
    Template,
    WorldState,
    evaluate,
    recent_event,
)
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES

WRITE_SLOT = 2

SIGNALLED = Template(
    id="extract_vengeance",  # real id keeps prose/catalog lookups valid
    priority=60,
    drive_band=DriveBand.PROJECT_IDENTITY,
    blurb="Synthetic signal-bearing template.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    package_gate=ALWAYS,
    branches=(
        Branch(
            label="show the hand",
            conditions=ALWAYS,
            narrative_stub="{actor} lets {target} feel the pressure.",
            event_type="retaliation_attempted",
            signal_event_type="threat_issued",
            magnitude=0.5,
        ),
    ),
)


def test_resolution_carries_the_branch_signal() -> None:
    resolution = evaluate(
        SIGNALLED, WorldState(current_tick=10), {Slot.ACTOR: 1, Slot.TARGET: 2}
    )
    assert resolution.passes
    assert resolution.event_type == "retaliation_attempted"
    assert resolution.signal_event_type == "threat_issued"


def test_builtin_signal_wiring() -> None:
    by_id = {template.id: template for template in BUILTIN_TEMPLATES}
    signals = {
        template_id: {
            branch.label: branch.signal_event_type
            for branch in by_id[template_id].branches
            if branch.signal_event_type
        }
        for template_id in ("extract_vengeance", "surveil", "cultivate_informant")
    }
    assert set(signals["extract_vengeance"].values()) == {"threat_issued"}
    assert set(signals["surveil"].values()) == {"compliance_alert"}
    assert set(signals["cultivate_informant"].values()) == {"encoded_message"}
    # The deed events are untouched: cooldown consumers keep their food.
    assert all(
        branch.event_type != branch.signal_event_type
        for template in BUILTIN_TEMPLATES
        for branch in template.branches
        if branch.signal_event_type
    )


def test_draft_serialization_round_trips_signal() -> None:
    draft = OrreryResolutionDraft(
        template_id="extract_vengeance",
        priority=60,
        binding_hash="h",
        bindings={"actor": 1, "target": 2},
        branch_label="show the hand",
        narrative_stub="x",
        event_type="retaliation_attempted",
        signal_event_type="threat_issued",
        magnitude=0.5,
    )
    hydrated = OrreryResolutionDraft.from_dict(draft.to_dict())
    assert hydrated.signal_event_type == "threat_issued"


@pytest.mark.requires_postgres
def test_committed_signal_feeds_consumer_gates_live() -> None:
    """The full chain, on real state: commit emits deed + signal rows, and
    the hunted target's gate predicate hears the threat next resolve."""

    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=f"save_{WRITE_SLOT:02d}",
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(id) FROM narrative_chunks")
            anchor_chunk_id = cur.fetchone()[0]
            cur.execute(
                """
                SELECT entity_id FROM characters
                WHERE entity_id IS NOT NULL ORDER BY entity_id LIMIT 2
                """
            )
            (avenger,), (target,) = cur.fetchall()

        draft = OrreryResolutionDraft(
            template_id="extract_vengeance",
            priority=60,
            binding_hash=f"signal-{uuid.uuid4().hex}",
            bindings={"actor": avenger, "target": target},
            branch_label="show the hand",
            narrative_stub="{actor} lets {target} feel the pressure.",
            event_type="retaliation_attempted",
            signal_event_type="threat_issued",
            magnitude=0.5,
        )
        result = commit_orrery_tick_sync(
            conn,
            OrreryTickProposal(
                anchor_chunk_id=anchor_chunk_id,
                actor_count=1,
                resolutions=(draft,),
            ),
            tick_chunk_id=anchor_chunk_id,
            slot=WRITE_SLOT,
        )
        assert result.resolution_count == 1

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_type, payload->>'signal_of'
                FROM world_events
                WHERE tick_chunk_id = %s AND target_entity_id = %s
                  AND event_type IN ('retaliation_attempted', 'threat_issued')
                ORDER BY id
                """,
                (anchor_chunk_id, target),
            )
            rows = cur.fetchall()
        kinds = {row[0]: row[1] for row in rows}
        assert set(kinds) == {"retaliation_attempted", "threat_issued"}
        assert kinds["threat_issued"] == "retaliation_attempted"

        # The chain input: the committed signal is queryable exactly as
        # hydration's recent-events window will read it next resolve.
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM world_events
                WHERE event_type = 'threat_issued'
                  AND target_entity_id = %s
                  AND tick_chunk_id >= %s - 5
                """,
                (target, anchor_chunk_id),
            )
            heard = cur.fetchone()[0]
        assert heard >= 1

        # Predicate semantics on state mirroring the committed rows: the
        # target hears the threat as next tick's actor; the avenger does not.
        from nexus.agents.orrery.substrate import EventRecord

        threatened_gate = recent_event(
            "threat_issued", within_ticks=5, target_slot=Slot.ACTOR
        )
        state = WorldState(
            recent_events=(
                EventRecord(
                    event_type="threat_issued",
                    tick=anchor_chunk_id,
                    actor_entity_id=avenger,
                    target_entity_id=target,
                ),
            ),
            current_tick=anchor_chunk_id,
        )
        assert threatened_gate(state, {Slot.ACTOR: target}) is True
        assert threatened_gate(state, {Slot.ACTOR: avenger}) is False
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.requires_postgres
def test_async_commit_emits_signal_rows_live() -> None:
    """The asyncpg twin needs explicit ::world_layer_type / ::text[] casts
    (review finding on #429) — and had no live coverage anywhere before
    this test. Real commit_orrery_tick_async, rolled-back transaction."""

    import asyncio

    import asyncpg

    async def _run() -> None:
        conn = await asyncpg.connect(
            host=os.environ.get("PGHOST", "localhost"),
            database=f"save_{WRITE_SLOT:02d}",
            user=os.environ.get("PGUSER", "pythagor"),
        )
        tx = conn.transaction()
        await tx.start()
        try:
            anchor = await conn.fetchval("SELECT max(id) FROM narrative_chunks")
            rows = await conn.fetch(
                """
                SELECT entity_id FROM characters
                WHERE entity_id IS NOT NULL ORDER BY entity_id LIMIT 2
                """
            )
            avenger, target = rows[0][0], rows[1][0]
            draft = OrreryResolutionDraft(
                template_id="extract_vengeance",
                priority=60,
                binding_hash=f"async-signal-{uuid.uuid4().hex}",
                bindings={"actor": avenger, "target": target},
                branch_label="show the hand",
                narrative_stub="{actor} lets {target} feel the pressure.",
                event_type="retaliation_attempted",
                signal_event_type="threat_issued",
                magnitude=0.5,
            )
            from nexus.agents.orrery.events import commit_orrery_tick_async

            result = await commit_orrery_tick_async(
                conn,
                OrreryTickProposal(
                    anchor_chunk_id=anchor, actor_count=1, resolutions=(draft,)
                ),
                tick_chunk_id=anchor,
                slot=WRITE_SLOT,
            )
            assert result.resolution_count == 1
            kinds = {
                row[0]
                for row in await conn.fetch(
                    """
                    SELECT event_type FROM world_events
                    WHERE tick_chunk_id = $1 AND target_entity_id = $2
                      AND event_type IN (
                        'retaliation_attempted', 'threat_issued'
                      )
                    """,
                    anchor,
                    target,
                )
            }
            assert kinds == {"retaliation_attempted", "threat_issued"}
        finally:
            await tx.rollback()
            await conn.close()

    asyncio.run(_run())
