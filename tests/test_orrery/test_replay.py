"""Live tests for the replay consumer (nexus/agents/orrery/replay.py).

Real writers, real triggers, real ledgers against save_05 inside
always-rolled-back transactions — the #428 test pattern. Each test
fabricates post-checkpoint history through the same code paths production
uses, then proves the replayer inverts it:

- scalar round trip: Skald writes then an Orrery activity write in one
  chunk; replay honors within-chunk ordering (Skald first) and the
  checkpoint-pair verify oracle reports zero drift.
- tag window replay: bestowals and clearances land/lift at exactly the
  chunks their provenance says.
- relationship unwind: updates rewind to pre-images, deletes resurrect,
  post-chunk INSERTs are dropped by wall-clock correlation.
- need replay: the production fulfillment applier's debt math is
  reproduced through the same effective_debt_score authority.
- drift detection: an un-ledgered scalar write between checkpoints is
  caught by verify — the oracle actually fires.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg2
import pytest

from nexus.agents.logon.apex_schema import (
    CharacterStateUpdate,
    LocationStateUpdate,
    StateUpdates,
)
from nexus.agents.orrery.events import (
    _apply_need_fulfillment_sync,
    _apply_state_delta_sync,
)
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.reconstruction import (
    capture_state_checkpoint_sync,
    set_commit_chunk_attribution_sync,
)
from nexus.agents.orrery.replay import (
    reconstruct_state_at_sync,
    verify_checkpoints_sync,
)
from nexus.agents.orrery.resolver import OrreryResolutionDraft
from nexus.agents.orrery.substrate import ProjectPolicy
from nexus.api.commit_handler_sync import apply_state_updates_sync

pytestmark = pytest.mark.requires_postgres

WRITE_SLOT = 5


def _connect() -> Any:
    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=f"save_{WRITE_SLOT:02d}",
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )
    with conn.cursor() as cur:
        _apply_migration_074(cur)
    return conn


def _head_chunk(cur: Any) -> int:
    cur.execute("SELECT max(id) FROM narrative_chunks")
    return cur.fetchone()[0]


def _fabricate_chunk(
    cur: Any,
    world_time: Optional[datetime],
    *,
    created_offset_minutes: int = 0,
) -> int:
    # now() is transaction time — constant across one rolled-back test
    # transaction — so tests that depend on wall-clock ordering (the
    # relationship insert-drop filter) must stagger created_at explicitly,
    # the way separate production transactions would naturally.
    cur.execute(
        """
        INSERT INTO narrative_chunks (id, raw_text, created_at)
        SELECT max(id) + 1, 'replay probe chunk',
               now() + make_interval(mins => %s)
        FROM narrative_chunks
        RETURNING id
        """,
        (created_offset_minutes,),
    )
    chunk_id = cur.fetchone()[0]
    if world_time is not None:
        cur.execute(
            "INSERT INTO chunk_metadata (chunk_id, world_time) VALUES (%s, %s)",
            (chunk_id, world_time),
        )
        # The statement-level metadata trigger recomputes world_time after
        # INSERT from cumulative time_delta. Restore the requested test clock
        # with a world_time-only UPDATE, which does not retrigger that function.
        cur.execute(
            "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
            (world_time, chunk_id),
        )
    # No metadata row when world_time is None: trg_chunk_metadata_refresh_
    # world_time backfills world_time on insert, so a NULL-world-time chunk
    # is only fabricable by omitting the row entirely.
    return chunk_id


def _insert_resolution(
    cur: Any, chunk_id: int, actor_entity_id: int, state_delta: dict[str, Any]
) -> int:
    cur.execute(
        """
        INSERT INTO orrery_resolutions (
            tick_chunk_id, template_id, binding_hash, actor_entity_id,
            priority, magnitude, state_delta
        ) VALUES (%s, 'replay_probe', %s, %s, 50, 0.5, %s)
        RETURNING id
        """,
        (chunk_id, f"probe-{chunk_id}", actor_entity_id, json.dumps(state_delta)),
    )
    return cur.fetchone()[0]


def _probe_character(cur: Any) -> tuple[int, int, str, Optional[int]]:
    cur.execute(
        """
        SELECT id, entity_id, current_activity, current_location
        FROM characters WHERE entity_id IS NOT NULL ORDER BY id LIMIT 1
        """
    )
    return cur.fetchone()


def _section_row(rows: list[dict[str, Any]], **match: Any) -> Optional[dict]:
    for row in rows:
        if all(row.get(k) == v for k, v in match.items()):
            return row
    return None


def _next_world_time(cur: Any) -> datetime:
    """A world_time after every existing stamp, so need accrual is sane."""

    cur.execute("SELECT max(world_time) FROM chunk_metadata")
    latest = cur.fetchone()[0]
    base = latest or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(hours=6)


PROJECT_POLICY = ProjectPolicy(
    enabled=True,
    advance_interval_hours=24.0,
    max_active_per_character=1,
    stall_abandon_threshold=3,
    abandon_after_stalled_world_hours=168.0,
    milestone_magnitude=0.40,
    coverage_distribution_tolerance=0.05,
)


def _apply_migration_074(cur: Any) -> None:
    """Create the pilot table only inside this rolled-back save_05 transaction."""

    cur.execute(Path("migrations/074_plan_relocation_projects.sql").read_text())


def _apply_transition(
    cur: Any,
    *,
    chunk_id: int,
    actor_entity_id: int,
    state_delta: dict[str, Any],
) -> None:
    """Write a real projection transition plus its replay ledger row."""

    resolution_id = _insert_resolution(cur, chunk_id, actor_entity_id, state_delta)
    draft = OrreryResolutionDraft(
        template_id="replay_probe",
        priority=47,
        binding_hash=f"project-{chunk_id}",
        bindings={"actor": actor_entity_id},
        branch_label="project replay probe",
        narrative_stub="probe",
        state_delta=state_delta,
        magnitude=0.4,
    )
    _apply_state_delta_sync(
        cur,
        draft,
        resolution_id=resolution_id,
        actor_entity_id=actor_entity_id,
        target_entity_id=None,
        source_chunk_id=chunk_id,
        need_tuning=load_need_tuning(),
        project_policy=PROJECT_POLICY,
    )


def test_scalar_replay_round_trip_and_within_chunk_ordering() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            char_id, char_entity, original_activity, original_location = (
                _probe_character(cur)
            )
            cur.execute("SELECT id FROM places ORDER BY id LIMIT 1")
            place_id = cur.fetchone()[0]

            base_id = capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            probe_chunk = _fabricate_chunk(cur, _next_world_time(cur))

        # Skald writes first (Step 8), through the real writer + ledger.
        apply_state_updates_sync(
            conn,
            StateUpdates(
                characters=[
                    CharacterStateUpdate(
                        character_id=char_id,
                        character_name="probe",
                        current_activity="skald probe activity",
                        current_location=place_id,
                    )
                ],
                locations=[
                    LocationStateUpdate(
                        place_id=place_id,
                        place_name="probe",
                        current_conditions="replay probe conditions",
                    )
                ],
            ),
            source_chunk_id=probe_chunk,
        )

        with conn.cursor() as cur:
            # Orrery activity write lands after Skald's in the same chunk
            # (Step 8.5) — the replayed final value must be Orrery's.
            cur.execute(
                "UPDATE characters SET current_activity = %s WHERE entity_id = %s",
                ("orrery probe activity", char_entity),
            )
            _insert_resolution(
                cur,
                probe_chunk,
                char_entity,
                {"character.current_activity": "orrery probe activity"},
            )
            capture_state_checkpoint_sync(cur, chunk_id=probe_chunk, label="manual")

            at_head = reconstruct_state_at_sync(cur, head, base_checkpoint_id=base_id)
            row = _section_row(at_head.state["characters"], id=char_id)
            assert row["current_activity"] == original_activity
            assert row["current_location"] == original_location

            # Force forward replay across the window (default base selection
            # would pick the checkpoint AT probe_chunk — pure passthrough).
            at_probe = reconstruct_state_at_sync(
                cur, probe_chunk, base_checkpoint_id=base_id
            )
            row = _section_row(at_probe.state["characters"], id=char_id)
            assert row["current_activity"] == "orrery probe activity"
            assert row["current_location"] == place_id
            place_row = _section_row(at_probe.state["places"], id=place_id)
            assert place_row["current_status"] == "replay probe conditions"

            verdicts = verify_checkpoints_sync(cur)
            probe_pair = [v for v in verdicts if v.target_chunk_id == probe_chunk]
            assert len(probe_pair) == 1
            assert probe_pair[0].drifts == []
    finally:
        conn.rollback()
        conn.close()


def test_tag_bestowal_and_clearance_replay_at_exact_chunks() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            _, char_entity, _, _ = _probe_character(cur)
            cur.execute(
                """
                SELECT t.id FROM tags t
                WHERE NOT t.deprecated AND t.synonym_for IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM entity_tags et
                    WHERE et.entity_id = %s AND et.tag_id = t.id
                      AND et.cleared_at IS NULL
                  )
                ORDER BY t.id LIMIT 1
                """,
                (char_entity,),
            )
            new_tag_id = cur.fetchone()[0]
            cur.execute(
                "SELECT id FROM entity_tags WHERE cleared_at IS NULL "
                "ORDER BY id LIMIT 1"
            )
            victim_row_id = cur.fetchone()[0]

            capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            bestow_chunk = _fabricate_chunk(cur, None)
            clear_chunk = _fabricate_chunk(cur, None)

            cur.execute(
                """
                INSERT INTO entity_tags (
                    entity_id, tag_id, source_kind, source_chunk_id
                ) VALUES (%s, %s, 'template', %s) RETURNING id
                """,
                (char_entity, new_tag_id, bestow_chunk),
            )
            bestowed_row_id = cur.fetchone()[0]
            cur.execute(
                "UPDATE entity_tags SET cleared_at = now() WHERE id = %s",
                (victim_row_id,),
            )
            cur.execute(
                """
                INSERT INTO tag_clearance_log (
                    entity_tag_id, mechanism, source_chunk_id
                ) VALUES (%s, 'authored', %s)
                """,
                (victim_row_id, clear_chunk),
            )
            capture_state_checkpoint_sync(cur, chunk_id=clear_chunk, label="manual")

            def active_ids(chunk: int) -> set[int]:
                result = reconstruct_state_at_sync(cur, chunk)
                return {row["id"] for row in result.state["entity_tags"]}

            at_head = active_ids(head)
            assert bestowed_row_id not in at_head
            assert victim_row_id in at_head

            at_bestow = active_ids(bestow_chunk)
            assert bestowed_row_id in at_bestow
            assert victim_row_id in at_bestow

            at_clear = active_ids(clear_chunk)
            assert bestowed_row_id in at_clear
            assert victim_row_id not in at_clear

            verdicts = verify_checkpoints_sync(cur)
            probe_pair = [v for v in verdicts if v.target_chunk_id == clear_chunk]
            assert len(probe_pair) == 1
            assert probe_pair[0].drifts == []
    finally:
        conn.rollback()
        conn.close()


def test_relationship_unwind_restores_updates_deletes_and_drops_inserts() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # Reconstruct at a fabricated pre-chunk, not the historical head:
            # anchoring at head would unwind any unattributed version rows
            # accumulated on native slot 5, making the assertions hostage
            # to unrelated history.
            head = _fabricate_chunk(cur, None)
            cur.execute(
                """
                SELECT character1_id, character2_id, dynamic
                FROM character_relationships ORDER BY character1_id LIMIT 2
                """
            )
            (u1, u2, original_dynamic), (d1, d2, _) = cur.fetchall()

            probe_chunk = _fabricate_chunk(cur, None)
            set_commit_chunk_attribution_sync(cur, probe_chunk)
            cur.execute(
                """
                UPDATE character_relationships SET dynamic = 'replay probe dynamic'
                WHERE character1_id = %s AND character2_id = %s
                """,
                (u1, u2),
            )
            cur.execute(
                """
                DELETE FROM character_relationships
                WHERE character1_id = %s AND character2_id = %s
                """,
                (d1, d2),
            )

            at_head = reconstruct_state_at_sync(cur, head)
            rows = at_head.state["character_relationships"]
            updated = _section_row(rows, character1_id=u1, character2_id=u2)
            assert updated["dynamic"] == original_dynamic
            assert _section_row(
                rows, character1_id=d1, character2_id=d2
            ), "delete pre-image must resurrect at the earlier chunk"

            at_probe = reconstruct_state_at_sync(cur, probe_chunk)
            rows = at_probe.state["character_relationships"]
            updated = _section_row(rows, character1_id=u1, character2_id=u2)
            assert updated["dynamic"] == "replay probe dynamic"
            assert _section_row(rows, character1_id=d1, character2_id=d2) is None

            # A row INSERTed after probe_chunk never fires the trigger; the
            # wall-clock filter must drop it at probe_chunk and keep it at a
            # later chunk.
            cur.execute(
                """
                SELECT a.id, b.id FROM characters a
                JOIN characters b ON b.id > a.id
                WHERE NOT EXISTS (
                    SELECT 1 FROM character_relationships r
                    WHERE r.character1_id = a.id AND r.character2_id = b.id
                )
                ORDER BY a.id, b.id LIMIT 1
                """
            )
            n1, n2 = cur.fetchone()
            cur.execute(
                """
                INSERT INTO character_relationships (
                    character1_id, character2_id, relationship_type,
                    emotional_valence, dynamic, recent_events, history,
                    created_at
                ) VALUES (%s, %s, 'ally', 'neutral', 'probe', 'probe',
                          'probe', now() + interval '1 minute')
                """,
                (n1, n2),
            )
            later_chunk = _fabricate_chunk(cur, None, created_offset_minutes=2)

            at_probe = reconstruct_state_at_sync(cur, probe_chunk)
            assert (
                _section_row(
                    at_probe.state["character_relationships"],
                    character1_id=n1,
                    character2_id=n2,
                )
                is None
            ), "post-chunk INSERT must be dropped by wall-clock correlation"
            at_later = reconstruct_state_at_sync(cur, later_chunk)
            assert _section_row(
                at_later.state["character_relationships"],
                character1_id=n1,
                character2_id=n2,
            )
    finally:
        conn.rollback()
        conn.close()


def test_need_fulfillment_replay_matches_production_applier() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            _, char_entity, _, _ = _probe_character(cur)
            capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            probe_chunk = _fabricate_chunk(cur, _next_world_time(cur))

            payload = {"type": "hunger", "quality": "probe_meal", "discharge_debt": 3.5}
            _apply_need_fulfillment_sync(
                cur,
                actor_entity_id=char_entity,
                fulfillment=dict(payload),
                template_id="replay_probe",
                source_chunk_id=probe_chunk,
                need_tuning=load_need_tuning(),
            )
            _insert_resolution(cur, probe_chunk, char_entity, {"need.fulfill": payload})
            capture_state_checkpoint_sync(cur, chunk_id=probe_chunk, label="manual")

            cur.execute(
                """
                SELECT debt_score, last_evaluated_chunk_id
                FROM character_need_states
                WHERE character_entity_id = %s AND need_type = 'hunger'
                """,
                (char_entity,),
            )
            live_debt, live_chunk_stamp = cur.fetchone()
            assert live_chunk_stamp == probe_chunk

            at_probe = reconstruct_state_at_sync(cur, probe_chunk)
            row = _section_row(
                at_probe.state["character_need_states"],
                character_entity_id=char_entity,
                need_type="hunger",
            )
            assert row["last_evaluated_chunk_id"] == probe_chunk
            assert abs(row["debt_score"] - float(live_debt)) < 0.005
            assert row["metadata"]["last_fulfillment"]["quality"] == "probe_meal"

            verdicts = verify_checkpoints_sync(cur)
            probe_pair = [v for v in verdicts if v.target_chunk_id == probe_chunk]
            assert len(probe_pair) == 1
            assert probe_pair[0].drifts == []
    finally:
        conn.rollback()
        conn.close()


def test_verify_catches_unledgered_scalar_drift() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            char_id, _, _, _ = _probe_character(cur)
            capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            probe_chunk = _fabricate_chunk(cur, None)

            # The forbidden move: mutate checkpointed state with no ledger
            # record of any kind.
            cur.execute(
                "UPDATE characters SET emotional_state = %s WHERE id = %s",
                ("unledgered drift probe", char_id),
            )
            capture_state_checkpoint_sync(cur, chunk_id=probe_chunk, label="manual")

            verdicts = verify_checkpoints_sync(cur)
            probe_pair = [v for v in verdicts if v.target_chunk_id == probe_chunk]
            assert len(probe_pair) == 1
            drifts = probe_pair[0].drifts
            assert any(
                d.section == "characters"
                and d.column == "emotional_state"
                and d.kind == "value"
                and d.expected == "unledgered drift probe"
                for d in drifts
            ), f"verify must catch the un-ledgered write; got {drifts}"
    finally:
        conn.rollback()
        conn.close()


def test_reconstruction_refuses_pre_instrumentation_chunks() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT min(chunk_id) FROM state_checkpoints "
                "WHERE chunk_id IS NOT NULL"
            )
            earliest = cur.fetchone()[0]
            assert earliest is not None, "save_05 must carry a genesis checkpoint"
            cur.execute(
                "SELECT max(id) FROM narrative_chunks WHERE id < %s", (earliest,)
            )
            ancient = cur.fetchone()[0]
            with pytest.raises(ValueError, match="instrumentation era"):
                reconstruct_state_at_sync(cur, ancient)
    finally:
        conn.rollback()
        conn.close()


def test_need_applicability_trigger_is_mirrored() -> None:
    """Bestowing a need-immunity tag fires the REAL migration-057 trigger
    (deleting the character's need rows, un-logged); the replayer's mirror
    must reproduce that from the final tag set, or verify cries wolf on
    honest data."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            _, char_entity, _, _ = _probe_character(cur)
            cur.execute(
                "SELECT count(*) FROM character_need_states "
                "WHERE character_entity_id = %s",
                (char_entity,),
            )
            assert cur.fetchone()[0] > 0, "probe character must carry need rows"

            base_id = capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            probe_chunk = _fabricate_chunk(cur, None)
            cur.execute("SELECT id FROM tags WHERE tag = 'inorganic'")
            immunity_tag_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO entity_tags (
                    entity_id, tag_id, source_kind, source_chunk_id
                ) VALUES (%s, %s, 'template', %s)
                """,
                (char_entity, immunity_tag_id, probe_chunk),
            )
            # 'inorganic' exempts sleep/hunger/thirst; socialize and intimacy
            # legitimately survive (NEED_IMMUNITY_TAGS).
            cur.execute(
                "SELECT need_type::text FROM character_need_states "
                "WHERE character_entity_id = %s ORDER BY need_type",
                (char_entity,),
            )
            live_need_types = {row[0] for row in cur.fetchall()}
            assert not live_need_types & {
                "sleep",
                "hunger",
                "thirst",
            }, "the DB trigger must have deleted the immune needs"
            capture_state_checkpoint_sync(cur, chunk_id=probe_chunk, label="manual")

            at_probe = reconstruct_state_at_sync(
                cur, probe_chunk, base_checkpoint_id=base_id
            )
            replayed_need_types = {
                row["need_type"]
                for row in at_probe.state["character_need_states"]
                if row["character_entity_id"] == char_entity
            }
            assert (
                replayed_need_types == live_need_types
            ), "mirror must reproduce exactly the trigger's surviving rows"
            at_head = reconstruct_state_at_sync(cur, head, base_checkpoint_id=base_id)
            assert {
                row["need_type"]
                for row in at_head.state["character_need_states"]
                if row["character_entity_id"] == char_entity
            } & {
                "sleep",
                "hunger",
                "thirst",
            }, "immune needs must survive at the pre-bestowal chunk"

            verdicts = verify_checkpoints_sync(cur)
            probe_pair = [v for v in verdicts if v.target_chunk_id == probe_chunk]
            assert len(probe_pair) == 1
            assert probe_pair[0].drifts == []
    finally:
        conn.rollback()
        conn.close()


def test_applicability_toggle_resets_need_row_to_fresh_shape() -> None:
    """Immunity applied at one chunk and cleared at the next: the REAL
    trigger deletes then re-inserts a FRESH need row. The mirror must reset
    the checkpoint-inherited row rather than let stale contents survive."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            _, char_entity, _, _ = _probe_character(cur)
            base_id = capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            bestow_chunk = _fabricate_chunk(cur, None)
            clear_chunk = _fabricate_chunk(cur, None)

            cur.execute("SELECT id FROM tags WHERE tag = 'inorganic'")
            immunity_tag_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO entity_tags (
                    entity_id, tag_id, source_kind, source_chunk_id
                ) VALUES (%s, %s, 'template', %s) RETURNING id
                """,
                (char_entity, immunity_tag_id, bestow_chunk),
            )
            immunity_row_id = cur.fetchone()[0]
            # Clear it one chunk later — the UPDATE fires the trigger, which
            # re-inserts fresh rows for the newly-applicable needs.
            cur.execute(
                "UPDATE entity_tags SET cleared_at = now() WHERE id = %s",
                (immunity_row_id,),
            )
            cur.execute(
                """
                INSERT INTO tag_clearance_log (
                    entity_tag_id, mechanism, source_chunk_id
                ) VALUES (%s, 'authored', %s)
                """,
                (immunity_row_id, clear_chunk),
            )
            cur.execute(
                """
                SELECT metadata FROM character_need_states
                WHERE character_entity_id = %s AND need_type = 'hunger'
                """,
                (char_entity,),
            )
            live_metadata = cur.fetchone()[0]
            assert (
                live_metadata.get("synced_by") == "need_applicability"
            ), "the DB trigger must have re-inserted a fresh row"
            capture_state_checkpoint_sync(cur, chunk_id=clear_chunk, label="manual")

            at_clear = reconstruct_state_at_sync(
                cur, clear_chunk, base_checkpoint_id=base_id
            )
            row = _section_row(
                at_clear.state["character_need_states"],
                character_entity_id=char_entity,
                need_type="hunger",
            )
            assert row is not None, "hunger must be applicable again at clear_chunk"
            assert row["debt_score"] == 0.0
            assert row["metadata"] == {"synced_by": "need_applicability"}
            assert (
                "character_need_states",
                f"{char_entity}:hunger",
                "last_evaluated_at",
            ) in at_clear.unreproducible

            verdicts = verify_checkpoints_sync(cur)
            probe_pair = [v for v in verdicts if v.target_chunk_id == clear_chunk]
            assert len(probe_pair) == 1
            assert probe_pair[0].drifts == []
    finally:
        conn.rollback()
        conn.close()


def test_travel_replay_start_advance_arrive() -> None:
    """Travel deltas replay production-faithfully for explicit payloads:
    travel.start anchors at the origin, travel.arrive moves the character
    (an Orrery location write with NO state_delta_log row) and resets the
    row; route-derived columns are flagged unreproducible so verify skips
    rather than lies."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            _, char_entity, _, _ = _probe_character(cur)
            cur.execute("SELECT id FROM places ORDER BY id LIMIT 2")
            (origin,), (destination,) = cur.fetchall()

            base_id = capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            start_chunk = _fabricate_chunk(cur, _next_world_time(cur))
            arrive_chunk = _fabricate_chunk(
                cur, _next_world_time(cur) + timedelta(hours=1)
            )

            # trg_chunk_metadata_refresh_world_time recomputes world_time on
            # insert; the production-shape writes below must use what the DB
            # actually stored, exactly as the real appliers do.
            def stored_world_time(chunk: int) -> datetime:
                cur.execute(
                    "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
                    (chunk,),
                )
                return cur.fetchone()[0]

            world_time_1 = stored_world_time(start_chunk)
            world_time_2 = stored_world_time(arrive_chunk)

            start_payload = {
                "origin_place_id": origin,
                "destination_place_id": destination,
                "initial_progress": 0.25,
            }
            # Production-shape writes (the full-row upsert travel.start
            # performs, with route columns the replayer must NOT claim).
            cur.execute(
                """
                INSERT INTO character_travel_states (
                    character_entity_id, status, anchor_place_id,
                    origin_place_id, destination_place_id, route_method,
                    travel_mode, risk, progress_ratio, estimated_distance_m,
                    estimated_duration_minutes, started_at_world_time,
                    updated_at_world_time, eta_world_time, route_metadata
                ) VALUES (
                    %s, 'in_transit', %s, %s, %s, 'estimated', 'mixed', 'low',
                    0.25, 1234.5, 42, %s, %s, %s, '{"probe": true}'::jsonb
                )
                ON CONFLICT (character_entity_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    anchor_place_id = EXCLUDED.anchor_place_id,
                    origin_place_id = EXCLUDED.origin_place_id,
                    destination_place_id = EXCLUDED.destination_place_id,
                    route_method = EXCLUDED.route_method,
                    travel_mode = EXCLUDED.travel_mode,
                    risk = EXCLUDED.risk,
                    progress_ratio = EXCLUDED.progress_ratio,
                    estimated_distance_m = EXCLUDED.estimated_distance_m,
                    estimated_duration_minutes = EXCLUDED.estimated_duration_minutes,
                    started_at_world_time = EXCLUDED.started_at_world_time,
                    updated_at_world_time = EXCLUDED.updated_at_world_time,
                    eta_world_time = EXCLUDED.eta_world_time,
                    route_metadata = EXCLUDED.route_metadata,
                    updated_at = now()
                """,
                (
                    char_entity,
                    origin,
                    origin,
                    destination,
                    world_time_1,
                    world_time_1,
                    world_time_1,
                ),
            )
            _insert_resolution(
                cur, start_chunk, char_entity, {"travel.start": start_payload}
            )

            # Arrive: production writes characters.current_location and
            # resets the travel row.
            cur.execute(
                "UPDATE characters SET current_location = %s WHERE entity_id = %s",
                (destination, char_entity),
            )
            cur.execute(
                """
                UPDATE character_travel_states
                SET status = 'at_place', anchor_place_id = %s,
                    origin_place_id = NULL, destination_place_id = NULL,
                    progress_ratio = 0, estimated_distance_m = NULL,
                    estimated_duration_minutes = NULL,
                    started_at_world_time = NULL,
                    updated_at_world_time = %s, eta_world_time = NULL,
                    route_metadata = route_metadata
                        || jsonb_build_object('last_arrived_place_id', %s::bigint),
                    updated_at = now()
                WHERE character_entity_id = %s
                """,
                (destination, world_time_2, destination, char_entity),
            )
            _insert_resolution(cur, arrive_chunk, char_entity, {"travel.arrive": True})
            capture_state_checkpoint_sync(cur, chunk_id=arrive_chunk, label="manual")

            at_start = reconstruct_state_at_sync(
                cur, start_chunk, base_checkpoint_id=base_id
            )
            travel_row = _section_row(
                at_start.state["character_travel_states"],
                character_entity_id=char_entity,
            )
            assert travel_row["status"] == "in_transit"
            assert (
                travel_row["anchor_place_id"] == origin
            ), "production anchors an in-transit row at its origin"
            assert travel_row["origin_place_id"] == origin
            assert travel_row["destination_place_id"] == destination
            assert travel_row["progress_ratio"] == 0.25

            at_arrive = reconstruct_state_at_sync(
                cur, arrive_chunk, base_checkpoint_id=base_id
            )
            char_row = _section_row(
                at_arrive.state["characters"], entity_id=char_entity
            )
            assert char_row["current_location"] == destination, (
                "travel.arrive's location write has no state_delta_log row; "
                "replay must apply it from the Orrery ledger"
            )
            travel_row = _section_row(
                at_arrive.state["character_travel_states"],
                character_entity_id=char_entity,
            )
            assert travel_row["status"] == "at_place"
            assert travel_row["anchor_place_id"] == destination
            assert travel_row["destination_place_id"] is None

            verdicts = verify_checkpoints_sync(cur)
            probe_pair = [v for v in verdicts if v.target_chunk_id == arrive_chunk]
            assert len(probe_pair) == 1
            assert probe_pair[0].drifts == []
            assert (
                probe_pair[0].skipped_unreproducible > 0
            ), "route-derived columns must be skipped as unreproducible"
    finally:
        conn.rollback()
        conn.close()


def test_unresolved_arrival_marks_location_unreproducible() -> None:
    """travel.start via anchor/class (no explicit destination) followed by a
    bare travel.arrive: production moved the character somewhere replay
    cannot know — every column the arrival wrote must be flagged, not left
    to read as false drift."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            char_id, char_entity, _, _ = _probe_character(cur)
            base_id = capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            start_chunk = _fabricate_chunk(cur, _next_world_time(cur))
            arrive_chunk = _fabricate_chunk(
                cur, _next_world_time(cur) + timedelta(hours=1)
            )
            _insert_resolution(
                cur,
                start_chunk,
                char_entity,
                {"travel.start": {"destination_anchor": "home"}},
            )
            _insert_resolution(cur, arrive_chunk, char_entity, {"travel.arrive": True})

            at_arrive = reconstruct_state_at_sync(
                cur, arrive_chunk, base_checkpoint_id=base_id
            )
            assert (
                "characters",
                str(char_id),
                "current_location",
            ) in at_arrive.unreproducible
            for column in ("anchor_place_id", "route_metadata", "destination_place_id"):
                assert (
                    "character_travel_states",
                    str(char_entity),
                    column,
                ) in at_arrive.unreproducible
            assert "characters" in at_arrive.approximate_sections
    finally:
        conn.rollback()
        conn.close()


def test_null_world_time_marks_need_timestamps_unreproducible() -> None:
    """A tick without world_time makes production stamp wall-clock now();
    replay must flag those columns instead of guessing — and verify must
    skip them, not drift."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            _, char_entity, _, _ = _probe_character(cur)
            base_id = capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            probe_chunk = _fabricate_chunk(cur, None)  # world_time NULL

            _apply_need_fulfillment_sync(
                cur,
                actor_entity_id=char_entity,
                fulfillment={"type": "thirst", "discharge_debt": 1.0},
                template_id="replay_probe",
                source_chunk_id=probe_chunk,
                need_tuning=load_need_tuning(),
            )
            _insert_resolution(
                cur,
                probe_chunk,
                char_entity,
                {"need.fulfill": {"type": "thirst", "discharge_debt": 1.0}},
            )
            capture_state_checkpoint_sync(cur, chunk_id=probe_chunk, label="manual")

            at_probe = reconstruct_state_at_sync(
                cur, probe_chunk, base_checkpoint_id=base_id
            )
            row_key = f"{char_entity}:thirst"
            for column in ("last_evaluated_at", "last_fulfilled_at", "debt_score"):
                assert (
                    "character_need_states",
                    row_key,
                    column,
                ) in at_probe.unreproducible, (
                    f"{column} depends on the wall-clock fallback and must be "
                    "flagged"
                )

            verdicts = verify_checkpoints_sync(cur)
            probe_pair = [v for v in verdicts if v.target_chunk_id == probe_chunk]
            assert len(probe_pair) == 1
            assert probe_pair[0].drifts == []
            assert probe_pair[0].skipped_unreproducible >= 3
    finally:
        conn.rollback()
        conn.close()


def test_verify_catches_unlogged_tag_clear() -> None:
    """The oracle must be sensitive beyond character scalars: a tag cleared
    without a tag_clearance_log row is exactly the class of un-ledgered
    write verify exists to catch."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            probe_chunk = _fabricate_chunk(cur, None)

            # A non-severity tag cleared with no log row (severity tags are
            # legitimately cleared un-logged by the applicability trigger and
            # mirrored; anything else is drift).
            cur.execute(
                """
                UPDATE entity_tags et SET cleared_at = now()
                FROM tags t
                WHERE et.tag_id = t.id AND et.cleared_at IS NULL
                  AND t.tag NOT LIKE 'sleep_deprived%%'
                  AND t.tag NOT LIKE 'hungry%%'
                  AND t.tag NOT LIKE 'thirsty%%'
                  AND t.tag NOT LIKE 'under_socialized%%'
                  AND t.tag NOT LIKE 'intimacy_starved%%'
                  AND et.id = (
                    SELECT et2.id FROM entity_tags et2
                    JOIN tags t2 ON t2.id = et2.tag_id
                    WHERE et2.cleared_at IS NULL
                      AND t2.tag NOT LIKE 'sleep_deprived%%'
                      AND t2.tag NOT LIKE 'hungry%%'
                      AND t2.tag NOT LIKE 'thirsty%%'
                      AND t2.tag NOT LIKE 'under_socialized%%'
                      AND t2.tag NOT LIKE 'intimacy_starved%%'
                    ORDER BY et2.id LIMIT 1
                  )
                RETURNING et.id
                """
            )
            cleared_row_id = cur.fetchone()[0]
            capture_state_checkpoint_sync(cur, chunk_id=probe_chunk, label="manual")

            verdicts = verify_checkpoints_sync(cur)
            probe_pair = [v for v in verdicts if v.target_chunk_id == probe_chunk]
            assert len(probe_pair) == 1
            assert any(
                d.section == "entity_tags"
                and d.kind == "extra_row"
                and d.row_key == str(cleared_row_id)
                for d in probe_pair[0].drifts
            ), "verify must catch the un-logged clear as extra_row drift"
    finally:
        conn.rollback()
        conn.close()


def test_project_transition_window_replays_with_zero_checkpoint_drift() -> None:
    """Every project transition plus a crisis no-op survives checkpoint replay."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            _apply_migration_074(cur)
            cur.execute(
                """
                SELECT c.entity_id, c.current_location
                FROM characters c
                WHERE c.entity_id IS NOT NULL
                  AND c.current_location IS NOT NULL
                ORDER BY c.id LIMIT 1
                """
            )
            actor_entity, origin = cur.fetchone()
            cur.execute(
                "SELECT id FROM places WHERE id <> %s ORDER BY id LIMIT 1", (origin,)
            )
            target = cur.fetchone()[0]

            base_time = _next_world_time(cur)
            base_chunk = _fabricate_chunk(cur, base_time)
            base_id = capture_state_checkpoint_sync(
                cur, chunk_id=base_chunk, label="manual"
            )
            # Imported pre-074 checkpoints may lack the additive section.
            # Replay treats that one omission as an empty genesis with an
            # explicit fidelity note, then applies project ledger entries.
            cur.execute(
                """
                UPDATE state_checkpoints
                SET state = state - 'character_project_states'
                WHERE id = %s
                """,
                (base_id,),
            )

            start_one = _fabricate_chunk(cur, base_time + timedelta(hours=24))
            _apply_transition(
                cur,
                chunk_id=start_one,
                actor_entity_id=actor_entity,
                state_delta={
                    "project.start": {
                        "project_type": "plan_relocation",
                        "stage": "saving",
                        "milestone": True,
                    }
                },
            )
            advance_one = _fabricate_chunk(cur, base_time + timedelta(hours=48))
            _apply_transition(
                cur,
                chunk_id=advance_one,
                actor_entity_id=actor_entity,
                state_delta={"project.advance": {"progress_delta": 0.35}},
            )

            # A crisis-band win writes only its own activity. The project row
            # must remain byte-for-byte untouched and replay must preserve that.
            cur.execute(
                """
                SELECT status, stage, progress, stall_count,
                       next_eligible_at_world_time, source_chunk_id
                FROM character_project_states
                WHERE character_entity_id = %s
                  AND status IN ('active', 'paused', 'stalled')
                """,
                (actor_entity,),
            )
            before_crisis = cur.fetchone()
            assert before_crisis[4] == base_time + timedelta(hours=72)
            crisis_chunk = _fabricate_chunk(cur, base_time + timedelta(hours=72))
            _apply_transition(
                cur,
                chunk_id=crisis_chunk,
                actor_entity_id=actor_entity,
                state_delta={
                    "character.current_activity": "evading replay probe crisis"
                },
            )
            cur.execute(
                """
                SELECT status, stage, progress, stall_count,
                       next_eligible_at_world_time, source_chunk_id
                FROM character_project_states
                WHERE character_entity_id = %s
                  AND status IN ('active', 'paused', 'stalled')
                """,
                (actor_entity,),
            )
            assert cur.fetchone() == before_crisis

            # The crisis tick left the project due. The next project
            # evaluation resumes it and advances the cadence normally.
            resume = _fabricate_chunk(cur, base_time + timedelta(hours=73))
            _apply_transition(
                cur,
                chunk_id=resume,
                actor_entity_id=actor_entity,
                state_delta={"project.advance": {"progress_delta": 0.15}},
            )
            cur.execute(
                """
                SELECT status, next_eligible_at_world_time
                FROM character_project_states
                WHERE character_entity_id = %s
                  AND status IN ('active', 'paused', 'stalled')
                """,
                (actor_entity,),
            )
            assert cur.fetchone() == (
                "active",
                base_time + timedelta(hours=97),
            )
            stall = _fabricate_chunk(cur, base_time + timedelta(hours=97))
            _apply_transition(
                cur,
                chunk_id=stall,
                actor_entity_id=actor_entity,
                state_delta={"project.stall": {"increment": 1}},
            )
            # Stall cadence is due at +121h. By +290h it is 169h overdue,
            # beyond the configured 168h aging threshold.
            cur.execute(
                """
                SELECT stall_count, next_eligible_at_world_time
                FROM character_project_states
                WHERE character_entity_id = %s
                  AND status IN ('active', 'paused', 'stalled')
                """,
                (actor_entity,),
            )
            assert cur.fetchone() == (
                1,
                base_time + timedelta(hours=121),
            )
            abandon = _fabricate_chunk(cur, base_time + timedelta(hours=290))
            _apply_transition(
                cur,
                chunk_id=abandon,
                actor_entity_id=actor_entity,
                state_delta={
                    "project.abandon": {
                        "reason": "overdue_world_time",
                        "milestone": True,
                    }
                },
            )

            start_two = _fabricate_chunk(cur, base_time + timedelta(hours=314))
            _apply_transition(
                cur,
                chunk_id=start_two,
                actor_entity_id=actor_entity,
                state_delta={
                    "project.start": {
                        "project_type": "plan_relocation",
                        "stage": "saving",
                        "milestone": True,
                    }
                },
            )
            ready = _fabricate_chunk(cur, base_time + timedelta(hours=338))
            _apply_transition(
                cur,
                chunk_id=ready,
                actor_entity_id=actor_entity,
                state_delta={
                    "project.advance": {
                        "stage": "committing",
                        "target_place_id": target,
                        "set_progress": 1.0,
                        "milestone": True,
                    }
                },
            )
            complete = _fabricate_chunk(cur, base_time + timedelta(hours=362))
            _apply_transition(
                cur,
                chunk_id=complete,
                actor_entity_id=actor_entity,
                state_delta={
                    "project.complete": {
                        "mode": "mixed",
                        "initial_progress": 0.0,
                        "milestone": True,
                    }
                },
            )
            target_id = capture_state_checkpoint_sync(
                cur, chunk_id=complete, label="manual"
            )

            reconstructed = reconstruct_state_at_sync(
                cur, complete, base_checkpoint_id=base_id
            )
            assert "character_project_states" in reconstructed.approximate_sections
            assert any(
                "migration 074" in note
                for note in reconstructed.notes["character_project_states"]
            )
            statuses = {
                row["status"]
                for row in reconstructed.state["character_project_states"]
                if row["character_entity_id"] == actor_entity
            }
            assert statuses == {"abandoned", "completed"}

            verdicts = verify_checkpoints_sync(cur)
            pair = [
                verdict
                for verdict in verdicts
                if verdict.base_checkpoint_id == base_id
                and verdict.target_checkpoint_id == target_id
            ]
            assert len(pair) == 1
            assert pair[0].drifts == []
    finally:
        conn.rollback()
        conn.close()


def test_project_complete_hands_off_and_real_travel_applier_relocates() -> None:
    """Completion starts travel at the project target; arrival moves the actor."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            _apply_migration_074(cur)
            cur.execute(
                """
                SELECT c.entity_id, c.current_location
                FROM characters c
                WHERE c.entity_id IS NOT NULL
                  AND c.current_location IS NOT NULL
                ORDER BY c.id LIMIT 1
                """
            )
            actor_entity, origin = cur.fetchone()
            cur.execute(
                "SELECT id FROM places WHERE id <> %s ORDER BY id LIMIT 1", (origin,)
            )
            target = cur.fetchone()[0]
            base_time = _next_world_time(cur)

            start = _fabricate_chunk(cur, base_time)
            _apply_transition(
                cur,
                chunk_id=start,
                actor_entity_id=actor_entity,
                state_delta={
                    "project.start": {
                        "project_type": "plan_relocation",
                        "stage": "saving",
                    }
                },
            )
            ready = _fabricate_chunk(cur, base_time + timedelta(hours=24))
            _apply_transition(
                cur,
                chunk_id=ready,
                actor_entity_id=actor_entity,
                state_delta={
                    "project.advance": {
                        "stage": "committing",
                        "target_place_id": target,
                        "set_progress": 1.0,
                    }
                },
            )
            complete = _fabricate_chunk(cur, base_time + timedelta(hours=48))
            _apply_transition(
                cur,
                chunk_id=complete,
                actor_entity_id=actor_entity,
                state_delta={"project.complete": {"mode": "mixed"}},
            )
            cur.execute(
                """
                SELECT cps.status, cts.status, cts.destination_place_id
                FROM character_project_states cps
                JOIN character_travel_states cts
                  ON cts.character_entity_id = cps.character_entity_id
                WHERE cps.character_entity_id = %s
                ORDER BY cps.id DESC LIMIT 1
                """,
                (actor_entity,),
            )
            assert cur.fetchone() == ("completed", "in_transit", target)

            arrive = _fabricate_chunk(cur, base_time + timedelta(hours=49))
            _apply_transition(
                cur,
                chunk_id=arrive,
                actor_entity_id=actor_entity,
                state_delta={"travel.arrive": True},
            )
            cur.execute(
                """
                SELECT c.current_location, cts.status,
                       cts.destination_place_id
                FROM characters c
                JOIN character_travel_states cts
                  ON cts.character_entity_id = c.entity_id
                WHERE c.entity_id = %s
                """,
                (actor_entity,),
            )
            assert cur.fetchone() == (target, "at_place", None)
    finally:
        conn.rollback()
        conn.close()


def test_project_applied_ledger_survives_replay_policy_retuning(monkeypatch) -> None:
    """Replay consumes committed cadence and milestone reset, not live tuning."""

    import nexus.agents.orrery.replay as replay_module

    conn = _connect()
    try:
        with conn.cursor() as cur:
            _char_id, actor_entity, _activity, _location = _probe_character(cur)
            base_time = _next_world_time(cur)
            base_chunk = _fabricate_chunk(cur, base_time)
            base_id = capture_state_checkpoint_sync(
                cur, chunk_id=base_chunk, label="manual"
            )

            start = _fabricate_chunk(cur, base_time + timedelta(hours=24))
            _apply_transition(
                cur,
                chunk_id=start,
                actor_entity_id=actor_entity,
                state_delta={
                    "project.start": {
                        "project_type": "plan_relocation",
                        "stage": "saving",
                        "milestone": True,
                    }
                },
            )
            stall = _fabricate_chunk(cur, base_time + timedelta(hours=48))
            _apply_transition(
                cur,
                chunk_id=stall,
                actor_entity_id=actor_entity,
                state_delta={"project.stall": {"increment": 1}},
            )
            milestone = _fabricate_chunk(cur, base_time + timedelta(hours=72))
            _apply_transition(
                cur,
                chunk_id=milestone,
                actor_entity_id=actor_entity,
                state_delta={
                    "project.advance": {
                        "stage": "scouting",
                        "set_progress": 0.0,
                        "milestone": True,
                    }
                },
            )
            target_id = capture_state_checkpoint_sync(
                cur, chunk_id=milestone, label="manual"
            )

            cur.execute(
                """
                SELECT state_delta->'project.advance'->'applied'
                FROM orrery_resolutions
                WHERE tick_chunk_id = %s AND template_id = 'replay_probe'
                """,
                (milestone,),
            )
            applied = cur.fetchone()[0]
            assert applied["stage"] == "scouting"
            assert applied["stall_count"] == 0
            assert datetime.fromisoformat(
                applied["next_eligible_at_world_time"]
            ) == base_time + timedelta(hours=96)

            monkeypatch.setattr(
                replay_module,
                "_load_project_policy",
                lambda: ProjectPolicy(
                    enabled=True,
                    advance_interval_hours=12.0,
                    stall_abandon_threshold=3,
                    abandon_after_stalled_world_hours=168.0,
                    milestone_magnitude=0.40,
                    coverage_distribution_tolerance=0.05,
                ),
            )
            verdicts = verify_checkpoints_sync(cur)
            pair = [
                verdict
                for verdict in verdicts
                if verdict.base_checkpoint_id == base_id
                and verdict.target_checkpoint_id == target_id
            ]
            assert len(pair) == 1
            assert pair[0].drifts == []
    finally:
        conn.rollback()
        conn.close()


def test_project_replay_rejects_ledger_without_applied_projection() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            _char_id, actor_entity, _activity, _location = _probe_character(cur)
            base_time = _next_world_time(cur)
            base_chunk = _fabricate_chunk(cur, base_time)
            base_id = capture_state_checkpoint_sync(
                cur, chunk_id=base_chunk, label="manual"
            )
            raw_chunk = _fabricate_chunk(cur, base_time + timedelta(hours=24))
            _insert_resolution(
                cur,
                raw_chunk,
                actor_entity,
                {"project.start": {"project_type": "plan_relocation"}},
            )

            with pytest.raises(ValueError, match="missing its required applied"):
                reconstruct_state_at_sync(cur, raw_chunk, base_checkpoint_id=base_id)
    finally:
        conn.rollback()
        conn.close()


def test_relationship_multi_version_unwind_order() -> None:
    """Two attributed updates across two chunks must unwind newest-first
    (relationship_versions.id DESC): the middle chunk sees the middle value."""

    conn = _connect()
    try:
        with conn.cursor() as cur:
            pre_chunk = _fabricate_chunk(cur, None)
            mid_chunk = _fabricate_chunk(cur, None)
            late_chunk = _fabricate_chunk(cur, None)
            cur.execute(
                """
                SELECT character1_id, character2_id, dynamic
                FROM character_relationships ORDER BY character1_id LIMIT 1
                """
            )
            c1, c2, original = cur.fetchone()

            set_commit_chunk_attribution_sync(cur, mid_chunk)
            cur.execute(
                """
                UPDATE character_relationships SET dynamic = 'mid value'
                WHERE character1_id = %s AND character2_id = %s
                """,
                (c1, c2),
            )
            set_commit_chunk_attribution_sync(cur, late_chunk)
            cur.execute(
                """
                UPDATE character_relationships SET dynamic = 'late value'
                WHERE character1_id = %s AND character2_id = %s
                """,
                (c1, c2),
            )

            def dynamic_at(chunk: int) -> str:
                result = reconstruct_state_at_sync(cur, chunk)
                return _section_row(
                    result.state["character_relationships"],
                    character1_id=c1,
                    character2_id=c2,
                )["dynamic"]

            assert dynamic_at(pre_chunk) == original
            assert dynamic_at(mid_chunk) == "mid value"
            assert dynamic_at(late_chunk) == "late value"
    finally:
        conn.rollback()
        conn.close()


def test_pair_tag_bestowal_and_clearance_replay() -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            head = _head_chunk(cur)
            cur.execute(
                """
                SELECT pt.id FROM pair_tags pt WHERE NOT pt.deprecated
                ORDER BY pt.id LIMIT 1
                """
            )
            pair_tag_id = cur.fetchone()[0]
            cur.execute(
                """
                SELECT a.entity_id, b.entity_id FROM characters a
                JOIN characters b ON b.entity_id > a.entity_id
                WHERE a.entity_id IS NOT NULL AND b.entity_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM entity_pair_tags ept
                    WHERE ept.subject_entity_id = a.entity_id
                      AND ept.object_entity_id = b.entity_id
                      AND ept.pair_tag_id = %s AND ept.cleared_at IS NULL
                  )
                ORDER BY a.entity_id, b.entity_id LIMIT 1
                """,
                (pair_tag_id,),
            )
            subject, obj = cur.fetchone()

            capture_state_checkpoint_sync(cur, chunk_id=head, label="manual")
            bestow_chunk = _fabricate_chunk(cur, None)
            clear_chunk = _fabricate_chunk(cur, None)
            cur.execute(
                """
                INSERT INTO entity_pair_tags (
                    subject_entity_id, object_entity_id, pair_tag_id,
                    source_kind, source_chunk_id
                ) VALUES (%s, %s, %s, 'template', %s) RETURNING id
                """,
                (subject, obj, pair_tag_id, bestow_chunk),
            )
            pair_row_id = cur.fetchone()[0]
            cur.execute(
                "UPDATE entity_pair_tags SET cleared_at = now() WHERE id = %s",
                (pair_row_id,),
            )
            cur.execute(
                """
                INSERT INTO tag_clearance_log (
                    entity_pair_tag_id, mechanism, source_chunk_id
                ) VALUES (%s, 'authored', %s)
                """,
                (pair_row_id, clear_chunk),
            )
            capture_state_checkpoint_sync(cur, chunk_id=clear_chunk, label="manual")

            def pair_ids(chunk: int) -> set[int]:
                result = reconstruct_state_at_sync(cur, chunk)
                return {row["id"] for row in result.state["entity_pair_tags"]}

            assert pair_row_id not in pair_ids(head)
            assert pair_row_id in pair_ids(bestow_chunk)
            assert pair_row_id not in pair_ids(clear_chunk)

            verdicts = verify_checkpoints_sync(cur)
            probe_pair = [v for v in verdicts if v.target_chunk_id == clear_chunk]
            assert len(probe_pair) == 1
            assert probe_pair[0].drifts == []
    finally:
        conn.rollback()
        conn.close()


def test_pg_round_matches_postgres_numeric_storage() -> None:
    """Postgres numeric rounds half away from zero; Python round() is
    banker's. 2.675 must store as 2.68."""

    from nexus.agents.orrery.replay import _pg_round

    assert _pg_round(2.675, 2) == 2.68
    assert _pg_round(0.5, 0) == 1.0
    assert _pg_round(0.35125, 4) == 0.3513
    assert round(2.675, 2) != 2.68, "if this fails, Python changed rounding"
