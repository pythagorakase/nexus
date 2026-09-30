"""PostgreSQL tests for adjudication-history persistence and the history payload.

Everything runs on one module-scoped disposable template clone, routed under
``ROUTED_SLOT`` and dropped afterward, so no owner slot is read or written.
The clone carries a located player, an explicit actor, and a committed Skald
ruling ledger from ``seed_adjudication_ledger``.

The commit-side test drives the real ``commit_orrery_tick_sync`` writer on
the clone inside a transaction that is **always rolled back** (real SQL, real
constraints, nothing kept). It pins the three 063 guarantees:

1. Adjudication log rows carry the subject (``actor_entity_id`` +
   ``bindings``) stamped while the draft is in hand.
2. Scene pressures and the rendered-slice prompt exposures persist at
   commit, including on re-commit (idempotent, ON CONFLICT).
3. A replace ruling whose resolution insert conflicts still reaches the log
   with the existing resolution id; the pre-063 silent skip is closed.

The history-payload tests read the seeded ledger: the SQL oracle, and a
self-check that the ledger holds every streak outcome and promotion status
the history renders, so the oracle is never vacuous.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple

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
from tests.pg_fixtures import (
    AdjudicationLedgerSeed,
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_adjudication_ledger,
    seed_character,
    seed_place,
    seed_protagonist,
    seed_story_clock,
    seed_zone,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres

# The slot label the clone is routed under; the commit writer receives it as
# the production turn does.
ROUTED_SLOT = 2
WORLD_TIME = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)


class AdjudicationStory(NamedTuple):
    """The clone, its explicit actor, the commit test's anchor, and the ledger."""

    dbname: str
    actor_entity_id: int
    anchor_chunk_id: int
    ledger: AdjudicationLedgerSeed


@pytest.fixture(scope="module")
def adjudication_story() -> Iterator[AdjudicationStory]:
    """A routed clone with a player, an actor, a committed ledger, and an anchor.

    Seeded in need-clock anchor order: zone, place, and the located player
    (which sets ``base_timestamp``), then the first clocked chunk, the actor,
    and two more ticks. The ledger is committed over the three ticks; the
    commit test anchors on a fourth chunk that carries no ledger row.
    """

    with disposable_slot_database("qa885_adjudication_history") as dbname:
        with pytest.MonkeyPatch.context() as mp:
            route_slot_to_disposable(mp.setattr, slot=ROUTED_SLOT, dbname=dbname)
            seed_zone(
                dbname,
                name="Adjudication Zone",
                min_longitude=-74.1,
                min_latitude=40.6,
                max_longitude=-73.8,
                max_latitude=40.9,
            )
            place_id, _ = seed_place(dbname, name="Adjudication Plaza")
            seed_protagonist(
                dbname,
                base_timestamp=WORLD_TIME.isoformat(),
                current_location=place_id,
            )
            ticks = [seed_story_clock(dbname, world_time=WORLD_TIME)]
            _, actor_entity_id = seed_character(
                dbname, name="Adjudication Actor", current_location=place_id
            )
            for scene in (2, 3):
                ticks.append(
                    seed_story_clock(
                        dbname,
                        world_time=WORLD_TIME + timedelta(hours=scene - 1),
                        scene=scene,
                    )
                )
            ledger = seed_adjudication_ledger(
                dbname, actor_entity_id=actor_entity_id, ticks=ticks
            )
            anchor_chunk_id = seed_story_clock(
                dbname, world_time=WORLD_TIME + timedelta(hours=3), scene=4
            )
            yield AdjudicationStory(dbname, actor_entity_id, anchor_chunk_id, ledger)


def _fetch_one(cur: Any, sql: str, params: tuple = ()) -> tuple:
    cur.execute(sql, params)
    row = cur.fetchone()
    assert row is not None, sql
    return row


def test_commit_persists_enriched_history_then_rolls_back(
    adjudication_story: AdjudicationStory,
) -> None:
    anchor_chunk_id = adjudication_story.anchor_chunk_id
    actor_entity_id = adjudication_story.actor_entity_id
    conn = connect(adjudication_story.dbname)
    try:
        with conn.cursor() as cur:
            # The seeded anchor and actor are real rows on the clone.
            _fetch_one(
                cur,
                "SELECT id FROM narrative_chunks WHERE id = %s",
                (anchor_chunk_id,),
            )
            _fetch_one(
                cur,
                """
                SELECT c.entity_id FROM characters c
                JOIN entities e ON e.id = c.entity_id
                WHERE c.entity_id = %s
                """,
                (actor_entity_id,),
            )

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
            slot=ROUTED_SLOT,
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
            slot=ROUTED_SLOT,
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
            slot=ROUTED_SLOT,
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
    check = connect(adjudication_story.dbname)
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


def test_adjudication_history_matches_sql_oracle(
    adjudication_story: AdjudicationStory,
) -> None:
    engine = create_engine(sqlalchemy_url(adjudication_story.dbname))
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


def test_seeded_ledger_covers_every_outcome_the_history_renders(
    adjudication_story: AdjudicationStory,
) -> None:
    """The oracle's ledger holds every streak outcome and promotion status.

    This replaces a probe that the owner's audited slots hold Skald
    rulings (neither does). What the oracle needs is a ledger in which every
    branch of the history is populated, so that is what is checked here.
    """

    ledger = adjudication_story.ledger
    engine = create_engine(sqlalchemy_url(adjudication_story.dbname))
    try:
        with Session(engine) as session:
            payload = adjudication_history(session)
            statuses = {
                (row["promotion_status"], row["narration_status"])
                for row in session.execute(
                    text(
                        """
                        SELECT promotion_status::text AS promotion_status,
                               narration_status::text AS narration_status
                        FROM orrery_resolutions
                        """
                    )
                ).mappings()
            }
    finally:
        engine.dispose()

    totals = payload["totals"]
    assert totals["log_rows"] == len(ledger.adjudication_log_ids) > 0
    assert all(totals["actions"][action] > 0 for action in ("defer", "replace", "void"))
    assert {streak["outcome"] for streak in payload["defer_streaks"]} == {
        "ratified",
        "replace",
        "void",
        "open",
    }
    assert {
        streak["proposal_id"]: (streak["outcome"], streak["length"])
        for streak in payload["defer_streaks"]
    } == dict(ledger.streaks)
    assert statuses == set(ledger.resolutions.values())
    assert {promotion for promotion, _narration in statuses} == {
        "promoted",
        "skipped",
        "pending",
    }
    assert ("promoted", "succeeded") in statuses
    funnel = {
        key: sum(entry[key] for entry in payload["templates"].values())
        for key in (
            "promoted",
            "promotion_skipped",
            "promotion_pending",
            "narrated",
            "replaced_with_delta_committed",
        )
    }
    assert all(count > 0 for count in funnel.values()), funnel
    assert payload["scene_pressures"]["rows"] == len(ledger.scene_pressure_ids)
    assert payload["exposures"]["resolution"]["rows"] > 0
    assert payload["exposures"]["scene_pressure"]["rows"] > 0
    assert payload["epoch"]["log_rows_with_subject"] == totals["log_rows"]
