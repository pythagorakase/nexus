"""Ecology-bundle machinery: signal detection policy + outbound pair tags.

The detection policy is a pure function and is tested directly. The
pair-tag ADD op and the detection gate ride the real commit writer
against live ``save_02`` rows (skipped unless ``NEXUS_RUN_POSTGRES=1``),
mirroring test_live_cycle's synthetic-draft-plus-cleanup harness — no
LLM involvement, so the test costs nothing but a transaction.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.events import (
    SignalDetection,
    coerce_signal_detection,
    commit_orrery_tick_sync,
)
from nexus.agents.orrery.resolver import OrreryResolutionDraft, OrreryTickProposal

LIVE_SLOT = 2


# ---------------------------------------------------------------------------
# SignalDetection policy (pure)
# ---------------------------------------------------------------------------


def test_signal_detection_roll_is_deterministic_and_threshold_bounded() -> None:
    policy = SignalDetection(default_pct=100, rates={"compliance_alert": 35})

    kwargs = dict(
        template_id="surveil",
        actor_entity_id=7,
        target_entity_id=9,
        tick_chunk_id=1200,
        event_type="compliance_alert",
    )
    first = policy.outcome(**kwargs)
    second = policy.outcome(**kwargs)
    assert first == second, "same state must roll the same outcome"
    assert first["threshold"] == 35
    assert 0 <= first["roll"] < 100

    # Different tick -> independent roll (the chain is per-emission).
    moved = policy.outcome(**{**kwargs, "tick_chunk_id": 1201})
    assert moved["roll"] != first["roll"] or moved == first

    always = SignalDetection(default_pct=100).outcome(**kwargs)
    assert always["detected"] is True and always["threshold"] == 100
    never = SignalDetection(default_pct=0).outcome(**kwargs)
    assert never["detected"] is False and never["threshold"] == 0


def test_coerce_signal_detection_shapes() -> None:
    assert coerce_signal_detection(None) == SignalDetection()

    mapping = coerce_signal_detection(
        {
            "signal_detection_default": 80,
            "signal_detection": {"threat_issued": 100},
        }
    )
    assert mapping.default_pct == 80
    assert mapping.rates == {"threat_issued": 100}

    with pytest.raises(ValueError):
        coerce_signal_detection(42)


# ---------------------------------------------------------------------------
# Live commit path (real save_02 rows, cleaned up)
# ---------------------------------------------------------------------------

pytestmark_live = pytest.mark.requires_postgres


def _connect() -> Any:
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=f"save_{LIVE_SLOT:02d}",
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )


def _hunt_draft(actor_entity_id: int, target_entity_id: int) -> OrreryResolutionDraft:
    return OrreryResolutionDraft(
        template_id="extract_vengeance",
        priority=90,
        binding_hash=f"ecology-live-{uuid.uuid4().hex}",
        bindings={"actor": actor_entity_id, "target": target_entity_id},
        branch_label="Declare the hunt",
        narrative_stub="{actor} starts hunting {target} in earnest.",
        state_delta={
            "character.current_activity": "hunting a grudge target",
            "entity_pair_tags.add_outbound": ["hunting"],
        },
        event_type="hunt_declared",
        signal_event_type="threat_issued",
        changed_fields=("character.current_activity", "entity_pair_tags"),
        magnitude=0.66,
    )


@pytest.mark.requires_postgres
def test_outbound_pair_tag_and_detection_gate_live() -> None:
    """Committing the hunt draft writes the edge; detection gates the signal."""

    conn: Any = None
    resolution_ids: list[int] = []
    pair_tag_ids: list[int] = []
    try:
        conn = _connect()
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT c.entity_id
                    FROM characters c
                    ORDER BY c.entity_id
                    LIMIT 2
                    """
                )
                rows = cur.fetchall()
                assert len(rows) == 2
                actor_id, target_id = (int(r["entity_id"]) for r in rows)
                cur.execute("SELECT max(id) AS max_id FROM narrative_chunks")
                anchor = int(cur.fetchone()["max_id"])

        def commit_hunt(detect_pct: int) -> int:
            proposal = OrreryTickProposal(
                anchor_chunk_id=anchor,
                actor_count=1,
                resolutions=(_hunt_draft(actor_id, target_id),),
            )
            with conn:
                result = commit_orrery_tick_sync(
                    conn,
                    proposal,
                    tick_chunk_id=anchor,
                    slot=LIVE_SLOT,
                    ecology_settings={
                        "signal_detection_default": 100,
                        "signal_detection": {"threat_issued": detect_pct},
                    },
                )
            assert result.resolution_count == 1
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT id FROM orrery_resolutions
                        WHERE tick_chunk_id = %s
                        ORDER BY id DESC LIMIT 1
                        """,
                        (anchor,),
                    )
                    resolution_id = int(cur.fetchone()["id"])
            resolution_ids.append(resolution_id)
            return resolution_id

        # Phase 1: guaranteed-undetected signal. The hunting edge lands;
        # the threat_issued row does not; the primary event records why.
        rid = commit_hunt(detect_pct=0)
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ept.id
                    FROM entity_pair_tags ept
                    JOIN pair_tags pt ON pt.id = ept.pair_tag_id
                    WHERE ept.subject_entity_id = %s
                      AND ept.object_entity_id = %s
                      AND pt.tag = 'hunting'
                      AND ept.cleared_at IS NULL
                      AND ept.template_id = 'extract_vengeance'
                    """,
                    (actor_id, target_id),
                )
                edge_rows = cur.fetchall()
                assert len(edge_rows) == 1, "hunting edge must be written once"
                pair_tag_ids.extend(int(r["id"]) for r in edge_rows)

                cur.execute(
                    """
                    SELECT event_type, payload
                    FROM world_events
                    WHERE resolution_id = %s
                    ORDER BY id
                    """,
                    (rid,),
                )
                events = cur.fetchall()
                assert [e["event_type"] for e in events] == ["hunt_declared"]
                detection = events[0]["payload"]["signal_detection"]
                assert detection["detected"] is False
                assert detection["threshold"] == 0

        # Phase 2: guaranteed-detected signal. The edge INSERT is a no-op
        # (live row exists) but the threat_issued signal lands.
        rid2 = commit_hunt(detect_pct=100)
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT event_type, payload
                    FROM world_events
                    WHERE resolution_id = %s
                    ORDER BY id
                    """,
                    (rid2,),
                )
                events = cur.fetchall()
                assert [e["event_type"] for e in events] == [
                    "hunt_declared",
                    "threat_issued",
                ]
                assert events[0]["payload"]["signal_detection"]["detected"] is True
                assert events[1]["payload"]["signal_of"] == "hunt_declared"
    finally:
        if conn is not None:
            with conn:
                with conn.cursor() as cur:
                    if resolution_ids:
                        cur.execute(
                            "DELETE FROM world_events WHERE resolution_id = ANY(%s)",
                            (resolution_ids,),
                        )
                        cur.execute(
                            "DELETE FROM orrery_resolutions WHERE id = ANY(%s)",
                            (resolution_ids,),
                        )
                    if pair_tag_ids:
                        cur.execute(
                            "DELETE FROM tag_clearance_log "
                            "WHERE entity_pair_tag_id = ANY(%s)",
                            (pair_tag_ids,),
                        )
                        cur.execute(
                            "DELETE FROM entity_pair_tags WHERE id = ANY(%s)",
                            (pair_tag_ids,),
                        )
            conn.close()
