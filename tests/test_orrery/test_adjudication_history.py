"""Live tests for adjudication-history persistence and the history payload.

The commit-side tests drive the real ``commit_orrery_tick_sync`` writer
against save_02 inside a transaction that is **always rolled back** — real
SQL, real constraints, zero persistent writes (see CLAUDE.md testing
philosophy). They pin the three 063 guarantees:

1. Adjudication log rows carry the subject (``actor_entity_id`` +
   ``bindings``) stamped while the draft is in hand.
2. Scene pressures and the rendered-slice prompt exposures persist at
   commit, including on re-commit (idempotent, ON CONFLICT).
3. A replace ruling whose resolution insert conflicts still reaches the log
   with the existing resolution id — the pre-063 silent skip is closed.

The history-payload tests read the real ledgers on save_02/save_05.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import psycopg2
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.history import adjudication_history
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryScenePressureDraft,
    OrreryTickProposal,
)
from nexus.api.slot_utils import get_slot_db_url

pytestmark = pytest.mark.requires_postgres

WRITE_SLOT = 2
HISTORY_SLOTS = (2, 5)


def _connect(slot: int) -> Any:
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=f"save_{slot:02d}",
        user=os.environ.get("PGUSER", "pythagor"),
        port=os.environ.get("PGPORT", "5432"),
    )


def _fetch_one(cur: Any, sql: str, params: tuple = ()) -> tuple:
    cur.execute(sql, params)
    row = cur.fetchone()
    assert row is not None, sql
    return row


def test_commit_persists_enriched_history_then_rolls_back() -> None:
    conn = _connect(WRITE_SLOT)
    try:
        with conn.cursor() as cur:
            anchor_chunk_id = _fetch_one(cur, "SELECT max(id) FROM narrative_chunks")[0]
            actor_entity_id = _fetch_one(
                cur,
                """
                SELECT c.entity_id FROM characters c
                JOIN entities e ON e.id = c.entity_id
                WHERE c.entity_id IS NOT NULL
                ORDER BY c.entity_id
                LIMIT 1
                """,
            )[0]

        ratify_hash = f"audit-ratify-{uuid.uuid4().hex}"
        defer_hash = f"audit-defer-{uuid.uuid4().hex}"
        pressure_hash = f"audit-pressure-{uuid.uuid4().hex}"
        ratified = OrreryResolutionDraft(
            template_id="hide",
            priority=40,
            binding_hash=ratify_hash,
            bindings={"actor": actor_entity_id},
            branch_label="Audit-history probe (ratified)",
            narrative_stub="{actor} keeps their head down.",
            magnitude=0.4,
        )
        deferred = OrreryResolutionDraft(
            template_id="sleep",
            priority=25,
            binding_hash=defer_hash,
            bindings={"actor": actor_entity_id},
            branch_label="Audit-history probe (deferred)",
            narrative_stub="{actor} finally rests.",
            magnitude=0.2,
        )
        pressure = OrreryScenePressureDraft(
            template_id="sleep_need_pressure",
            priority=25,
            binding_hash=pressure_hash,
            bindings={"actor": actor_entity_id},
            branch_label="critical",
            pressure_stub="{actor} is running on fumes.",
            prompt_text="Someone is running on fumes.",
            magnitude=0.3,
        )
        proposal = OrreryTickProposal(
            anchor_chunk_id=anchor_chunk_id,
            actor_count=1,
            resolutions=(ratified, deferred),
            scene_pressures=(pressure,),
        )

        # --- Round 1: ratify A, defer B; render caps 1/1 -------------------
        result = commit_orrery_tick_sync(
            conn,
            proposal,
            tick_chunk_id=anchor_chunk_id,
            slot=WRITE_SLOT,
            adjudications=[{"proposal_id": deferred.proposal_id, "action": "defer"}],
            prompt_settings={
                "max_rendered_proposals": 1,
                "max_rendered_pressures": 1,
            },
        )
        assert result.resolution_count == 1
        assert result.deferred_count == 1
        assert result.scene_pressure_count == 1
        # One resolution exposure (cap 1 of 2 drafts) + one pressure exposure.
        assert result.prompt_exposure_count == 2

        with conn.cursor() as cur:
            log_actor, log_bindings = _fetch_one(
                cur,
                """
                SELECT actor_entity_id, bindings
                FROM orrery_adjudication_log
                WHERE binding_hash = %s
                """,
                (defer_hash,),
            )
            assert log_actor == actor_entity_id
            assert log_bindings == {"actor": actor_entity_id}

            pressure_row = _fetch_one(
                cur,
                """
                SELECT actor_entity_id, prompt_text, magnitude
                FROM orrery_scene_pressures
                WHERE tick_chunk_id = %s AND binding_hash = %s
                """,
                (anchor_chunk_id, pressure_hash),
            )
            assert pressure_row[0] == actor_entity_id
            assert pressure_row[1] == "Someone is running on fumes."

            cur.execute(
                """
                SELECT kind, template_id, position
                FROM orrery_prompt_exposures
                WHERE tick_chunk_id = %s
                  AND binding_hash IN (%s, %s, %s)
                ORDER BY kind, position
                """,
                (anchor_chunk_id, ratify_hash, defer_hash, pressure_hash),
            )
            exposures = cur.fetchall()
            # The deferred draft sat beyond the render cap: not recorded.
            assert [(k, t, p) for k, t, p in exposures] == [
                ("resolution", "hide", 0),
                ("scene_pressure", "sleep_need_pressure", 0),
            ]

            existing_resolution_id = _fetch_one(
                cur,
                "SELECT id FROM orrery_resolutions WHERE binding_hash = %s",
                (ratify_hash,),
            )[0]

        # --- Round 2: re-commit; replace-with-delta hits ON CONFLICT -------
        result_two = commit_orrery_tick_sync(
            conn,
            proposal,
            tick_chunk_id=anchor_chunk_id,
            slot=WRITE_SLOT,
            adjudications=[
                {"proposal_id": deferred.proposal_id, "action": "defer"},
                {
                    "proposal_id": ratified.proposal_id,
                    "action": "replace",
                    "note": "audit probe: ruling must survive re-commit",
                    "replacement_state_delta": {
                        "character.current_activity": "audit-history probe"
                    },
                },
            ],
            prompt_settings={
                "max_rendered_proposals": 1,
                "max_rendered_pressures": 1,
            },
        )
        assert result_two.skipped_existing_count == 1
        assert result_two.replaced_count == 1
        # Idempotent: no duplicate pressure/exposure rows on re-commit.
        assert result_two.scene_pressure_count == 0
        assert result_two.prompt_exposure_count == 0

        with conn.cursor() as cur:
            replace_row = _fetch_one(
                cur,
                """
                SELECT action, applied_resolution_id, actor_entity_id
                FROM orrery_adjudication_log
                WHERE binding_hash = %s AND action = 'replace'
                """,
                (ratify_hash,),
            )
            # The pre-063 writer silently dropped this ruling; it must now
            # land, pointing at the resolution row that already existed.
            assert replace_row[1] == existing_resolution_id
            assert replace_row[2] == actor_entity_id

        # --- Round 3: a third commit must not duplicate the replace row ----
        result_three = commit_orrery_tick_sync(
            conn,
            proposal,
            tick_chunk_id=anchor_chunk_id,
            slot=WRITE_SLOT,
            adjudications=[
                {
                    "proposal_id": ratified.proposal_id,
                    "action": "replace",
                    "replacement_state_delta": {
                        "character.current_activity": "audit-history probe"
                    },
                },
            ],
        )
        assert result_three.replaced_count == 0
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM orrery_adjudication_log
                WHERE binding_hash = %s AND action = 'replace'
                """,
                (ratify_hash,),
            )
            assert (
                cur.fetchone()[0] == 1
            ), "repeated re-commits must not inflate replace history"
    finally:
        conn.rollback()
        conn.close()

    # Nothing persisted: the probe hashes must not exist outside the txn.
    check = _connect(WRITE_SLOT)
    try:
        with check.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM orrery_adjudication_log
                WHERE binding_hash IN (%s, %s)
                """,
                (ratify_hash, defer_hash),
            )
            assert cur.fetchone()[0] == 0
    finally:
        check.close()


@pytest.mark.parametrize("slot", HISTORY_SLOTS)
def test_adjudication_history_matches_sql_oracle(slot: int) -> None:
    engine = create_engine(get_slot_db_url(slot=slot))
    try:
        with Session(engine) as session:
            payload = adjudication_history(session)
            oracle_actions = {
                row["action"]: row["count"]
                for row in session.execute(
                    text(
                        """
                        SELECT action, count(*) AS count
                        FROM orrery_adjudication_log GROUP BY action
                        """
                    )
                ).mappings()
            }
            oracle_committed = session.execute(
                text("SELECT count(*) FROM orrery_resolutions")
            ).scalar()
            oracle_promoted = session.execute(
                text(
                    """
                    SELECT count(*) FROM orrery_resolutions
                    WHERE promotion_status = 'promoted'
                    """
                )
            ).scalar()
    finally:
        engine.dispose()

    totals = payload["totals"]
    for action in ("defer", "replace", "void"):
        assert totals["actions"][action] == oracle_actions.get(action, 0)
    assert totals["committed_resolutions"] == oracle_committed
    assert (
        sum(entry["promoted"] for entry in payload["templates"].values())
        == oracle_promoted
    )

    # Streak arithmetic: every defer belongs to exactly one streak.
    assert (
        sum(streak["length"] for streak in payload["defer_streaks"])
        == totals["actions"]["defer"]
    )
    for streak in payload["defer_streaks"]:
        assert streak["outcome"] in {"ratified", "replace", "void", "open"}
        assert streak["length"] >= 1
        assert streak["start_tick"] <= streak["end_tick"]

    # Funnel monotonicity per template.
    for template_id, entry in payload["templates"].items():
        assert entry["narrated"] <= entry["promoted"] <= entry["committed"], template_id
        assert entry["ratified_committed"] >= 0

    json.dumps(payload)


def test_history_is_non_vacuous_on_audited_slots() -> None:
    """Both slots must still carry adjudication data or the suite is hollow."""

    total_rows = 0
    for slot in HISTORY_SLOTS:
        engine = create_engine(get_slot_db_url(slot=slot))
        try:
            with Session(engine) as session:
                total_rows += adjudication_history(session)["totals"]["log_rows"]
        finally:
            engine.dispose()
    assert total_rows > 0, (
        "no audited slot has adjudication-log rows — the history assertions "
        "are vacuous; repoint HISTORY_SLOTS at a slot with Skald rulings"
    )
