"""Live tests for migration 064's forward-fix tag provenance.

Real writers against save_02 inside always-rolled-back transactions — real
SQL, real constraints, zero persistent writes. Pins the forward-fix
guarantees from docs/orrery_audit_dashboard_notes.md step 7:

1. Resolver bestowals stamp ``source_chunk_id`` and the bestowing chunk's
   in-world time (previously both were the NULL leak the notes cite).
2. tag_writer bestowals stamp the chunk key when the caller supplies it, and
   every tag_writer clear now writes a ``tag_clearance_log`` row.
3. Pair-tag clears — structurally unloggable before 064 — log with
   ``entity_pair_tag_id``.
4. The hover-audit's per-row provenance gains the "exact" tier, visible
   end-to-end through ``entity_context``.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import psycopg2
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from nexus.agents.orrery.audit import entity_context
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryTickProposal,
)
from nexus.agents.orrery.tag_writer import (
    apply_pair_tag_bestowal,
    apply_tag_bestowal,
    clear_pair_tag,
)
from nexus.agents.orrery.tag_schemas import OrreryTagBestowal
from nexus.api.slot_utils import get_slot_db_url

pytestmark = pytest.mark.requires_postgres

WRITE_SLOT = 2


def _connect() -> Any:
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=f"save_{WRITE_SLOT:02d}",
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )


def _anchor_and_actors(cur: Any) -> tuple[int, int, int]:
    cur.execute("SELECT max(id) FROM narrative_chunks")
    anchor_chunk_id = cur.fetchone()[0]
    cur.execute(
        """
        SELECT c.entity_id FROM characters c
        WHERE c.entity_id IS NOT NULL
        ORDER BY c.entity_id
        LIMIT 2
        """
    )
    rows = cur.fetchall()
    assert len(rows) == 2, "save_02 is expected to hold at least two characters"
    return anchor_chunk_id, rows[0][0], rows[1][0]


def test_resolver_commit_stamps_bestowal_provenance() -> None:
    """entity_tags.add through the tick commit carries chunk + world time."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            anchor_chunk_id, actor_id, target_id = _anchor_and_actors(cur)
            cur.execute(
                "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
                (anchor_chunk_id,),
            )
            row = cur.fetchone()
            chunk_world_time = row[0] if row else None
            # Give the target an inbound `hunting` pair tag so the draft's
            # clear_inbound delta has something real to clear and log.
            assert apply_pair_tag_bestowal(
                cur,
                subject_entity_id=actor_id,
                object_entity_id=target_id,
                subject_kind="character",
                object_kind="character",
                tag="hunting",
                source_chunk_id=anchor_chunk_id,
            )
            cur.execute(
                """
                SELECT source_chunk_id FROM entity_pair_tags
                WHERE subject_entity_id = %s AND object_entity_id = %s
                  AND cleared_at IS NULL
                ORDER BY id DESC LIMIT 1
                """,
                (actor_id, target_id),
            )
            assert cur.fetchone()[0] == anchor_chunk_id

        draft = OrreryResolutionDraft(
            template_id="evade_pursuers",
            priority=100,
            binding_hash=f"prov-{uuid.uuid4().hex}",
            bindings={"actor": actor_id, "target": target_id},
            branch_label="Provenance probe",
            narrative_stub="{actor} slips the cordon.",
            magnitude=0.5,
            state_delta={
                "entity_tags.add": ["off_grid"],
                "entity_pair_tags_target.clear_inbound": ["hunting"],
            },
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
        assert result.tag_mutation_count >= 2

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT et.source_chunk_id, et.applied_at_world_time
                FROM entity_tags et
                JOIN tags t ON t.id = et.tag_id
                WHERE et.entity_id = %s AND t.tag = 'off_grid'
                  AND et.cleared_at IS NULL
                  AND et.source_kind = 'template'
                ORDER BY et.id DESC LIMIT 1
                """,
                (actor_id,),
            )
            source_chunk_id, applied_world_time = cur.fetchone()
            assert source_chunk_id == anchor_chunk_id
            assert applied_world_time == chunk_world_time

            # The pair-tag clear must be logged with the pair row's id.
            cur.execute(
                """
                SELECT tcl.entity_pair_tag_id, tcl.source_chunk_id,
                       tcl.mechanism::text, ept.cleared_at
                FROM tag_clearance_log tcl
                JOIN entity_pair_tags ept ON ept.id = tcl.entity_pair_tag_id
                JOIN pair_tags pt ON pt.id = ept.pair_tag_id
                WHERE ept.subject_entity_id = %s
                  AND ept.object_entity_id = %s
                  AND pt.tag = 'hunting'
                ORDER BY tcl.id DESC LIMIT 1
                """,
                (actor_id, target_id),
            )
            log_row = cur.fetchone()
            assert log_row is not None, "pair-tag clearance must be logged"
            assert log_row[1] == anchor_chunk_id
            assert log_row[2] == "authored"
            assert log_row[3] is not None
    finally:
        conn.rollback()
        conn.close()


def test_tag_writer_clears_are_logged_and_bestowals_stamped() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            anchor_chunk_id, actor_id, target_id = _anchor_and_actors(cur)

            counters = apply_tag_bestowal(
                cur,
                entity_id=actor_id,
                entity_kind="character",
                bestowal=OrreryTagBestowal(applied_tags=["off_grid"]),
                source_chunk_id=anchor_chunk_id,
            )
            cur.execute(
                """
                SELECT et.source_chunk_id, et.applied_at_world_time
                FROM entity_tags et
                JOIN tags t ON t.id = et.tag_id
                WHERE et.entity_id = %s AND t.tag = 'off_grid'
                  AND et.cleared_at IS NULL
                ORDER BY et.id DESC LIMIT 1
                """,
                (actor_id,),
            )
            source_chunk_id, world_time = cur.fetchone()
            if counters["applied"]:
                assert source_chunk_id == anchor_chunk_id
                assert world_time is not None

            cleared = apply_tag_bestowal(
                cur,
                entity_id=actor_id,
                entity_kind="character",
                bestowal=OrreryTagBestowal(tags_to_clear=["off_grid"]),
                source_chunk_id=anchor_chunk_id,
            )
            assert cleared["cleared"] >= 1
            cur.execute(
                """
                SELECT tcl.mechanism::text, tcl.source_chunk_id,
                       tcl.justification->>'reason'
                FROM tag_clearance_log tcl
                JOIN entity_tags et ON et.id = tcl.entity_tag_id
                JOIN tags t ON t.id = et.tag_id
                WHERE et.entity_id = %s AND t.tag = 'off_grid'
                ORDER BY tcl.id DESC LIMIT 1
                """,
                (actor_id,),
            )
            mechanism, log_chunk, reason = cur.fetchone()
            assert mechanism == "authored"
            assert log_chunk == anchor_chunk_id
            assert reason == "bestowal.tags_to_clear"

            # Direct pair-tag clear path logs too.
            assert apply_pair_tag_bestowal(
                cur,
                subject_entity_id=actor_id,
                object_entity_id=target_id,
                subject_kind="character",
                object_kind="character",
                tag="hunting",
                source_chunk_id=anchor_chunk_id,
            )
            assert clear_pair_tag(
                cur,
                subject_entity_id=actor_id,
                object_entity_id=target_id,
                tag="hunting",
                source_chunk_id=anchor_chunk_id,
            )
            cur.execute(
                """
                SELECT count(*)
                FROM tag_clearance_log tcl
                JOIN entity_pair_tags ept ON ept.id = tcl.entity_pair_tag_id
                WHERE ept.subject_entity_id = %s AND ept.object_entity_id = %s
                  AND tcl.justification->>'reason' = 'clear_pair_tag'
                """,
                (actor_id, target_id),
            )
            assert cur.fetchone()[0] >= 1
    finally:
        conn.rollback()
        conn.close()


def test_entity_context_reports_exact_provenance_tier() -> None:
    """A 064-era bestowal shows as provenance "exact" in the hover payload."""

    engine = create_engine(get_slot_db_url(slot=WRITE_SLOT))
    try:
        with Session(engine) as session:
            raw = session.connection().connection.cursor()
            anchor_chunk_id, actor_id, _ = _anchor_and_actors(raw)
            apply_tag_bestowal(
                raw,
                entity_id=actor_id,
                entity_kind="character",
                bestowal=OrreryTagBestowal(applied_tags=["off_grid"]),
                source_chunk_id=anchor_chunk_id,
            )
            payload = entity_context(
                session,
                [actor_id],
                anchor_chunk_id=anchor_chunk_id,
            )
            (entity,) = payload["entities"]
            rows = entity["tags"]["durable"] + entity["tags"]["ephemeral"]
            exact_rows = [row for row in rows if row["provenance"] == "exact"]
            assert exact_rows, "the fresh bestowal must surface as exact"
            for row in exact_rows:
                assert row["source_chunk_id"] is not None
            for row in rows:
                if row["source_chunk_id"] is not None:
                    assert row["provenance"] == "exact"
                elif row["applied_at_world_time"] is not None:
                    assert row["provenance"] == "approximate"
                else:
                    assert row["provenance"] == "unknowable"
            session.rollback()
    finally:
        engine.dispose()


def test_chunk_keyed_bestowal_without_metadata_leaves_world_time_null() -> None:
    """A chunk-keyed row must never borrow the global-max clock (review
    finding on #425): chunk clock or NULL, so the "exact" tier cannot carry
    a fabricated world time."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            _, actor_id, _ = _anchor_and_actors(cur)
            cur.execute(
                """
                INSERT INTO narrative_chunks (raw_text)
                VALUES ('provenance probe: chunk without metadata')
                RETURNING id
                """
            )
            bare_chunk_id = cur.fetchone()[0]

            counters = apply_tag_bestowal(
                cur,
                entity_id=actor_id,
                entity_kind="character",
                bestowal=OrreryTagBestowal(applied_tags=["off_grid"]),
                source_chunk_id=bare_chunk_id,
            )
            assert counters["applied"] == 1
            cur.execute(
                """
                SELECT et.source_chunk_id, et.applied_at_world_time
                FROM entity_tags et
                JOIN tags t ON t.id = et.tag_id
                WHERE et.entity_id = %s AND t.tag = 'off_grid'
                  AND et.cleared_at IS NULL
                ORDER BY et.id DESC LIMIT 1
                """,
                (actor_id,),
            )
            source_chunk_id, world_time = cur.fetchone()
            assert source_chunk_id == bare_chunk_id
            assert world_time is None
    finally:
        conn.rollback()
        conn.close()
