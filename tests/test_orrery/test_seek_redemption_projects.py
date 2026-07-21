"""SEEK_REDEMPTION character-targeted project acceptance coverage."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
import psycopg2.extras
import pytest

from nexus.agents.orrery.events import (
    _apply_state_delta_sync,
    _upsert_reconciled_relationship_sync,
)
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.resolver import OrreryResolutionDraft
from nexus.agents.orrery.substrate import (
    BranchSelection,
    ProjectPolicy,
    ProjectState,
    RoutineAnchor,
    Slot,
    TravelState,
    WorldState,
    evaluate,
)
from nexus.agents.orrery.templates import ADVANCE_SEEK_REDEMPTION, START_SEEK_REDEMPTION
from nexus.api.slot_utils import get_slot_db_url

ACTOR = 10
TARGET = 20
NOW = datetime(2073, 8, 2, 12, tzinfo=timezone.utc)
POLICY = ProjectPolicy(
    enabled=True,
    advance_interval_hours=24.0,
    stall_abandon_threshold=3,
    abandon_after_stalled_world_hours=168.0,
)
BINDINGS = {Slot.ACTOR: ACTOR, Slot.TARGET: TARGET}


def _start_state(**changes: Any) -> WorldState:
    values: dict[str, Any] = {
        "locations": {ACTOR: 1},
        "trust": {(TARGET, ACTOR): -1},
        "travel_states": {ACTOR: TravelState(status="at_place")},
        "project_policy": POLICY,
        "routine_anchors": {
            (ACTOR, "home"): RoutineAnchor(
                anchor_type="home", place_id=1, mobility_policy="fixed_place"
            )
        },
        "world_time": NOW,
    }
    values.update(changes)
    return WorldState(**values)


def _project(
    *,
    stage: str = "owning_the_wrong",
    progress: float = 0.0,
    stall_count: int = 0,
    due_at: datetime = NOW,
    target_active: bool = True,
) -> ProjectState:
    return ProjectState(
        id=7,
        project_type="seek_redemption",
        status="active",
        stage=stage,
        target_character_entity_id=TARGET,
        target_character_is_active=target_active,
        progress=progress,
        stall_count=stall_count,
        next_eligible_at_world_time=due_at,
        source_chunk_id=100,
    )


def _advance_state(project: ProjectState, **changes: Any) -> WorldState:
    values: dict[str, Any] = {
        "project_states": {ACTOR: project},
        "project_policy": POLICY,
        "travel_states": {ACTOR: TravelState(status="at_place")},
        "world_time": NOW,
    }
    values.update(changes)
    return WorldState(**values)


def test_entry_gate_wronged_party_evidence_or_clause_and_contract() -> None:
    arms = (
        _start_state(),
        _start_state(
            trust={},
            relationship_types={(ACTOR, TARGET): frozenset({"enemy"})},
        ),
        _start_state(
            trust={},
            relationship_types={(TARGET, ACTOR): frozenset({"rival"})},
        ),
        _start_state(
            trust={},
            pair_tags={(TARGET, ACTOR): frozenset({"hostile_to"})},
        ),
    )
    for state in arms:
        assert evaluate(START_SEEK_REDEMPTION, state, BINDINGS).passes is True
    result = evaluate(START_SEEK_REDEMPTION, arms[0], BINDINGS)
    assert START_SEEK_REDEMPTION.required_slots == (Slot.ACTOR, Slot.TARGET)
    assert START_SEEK_REDEMPTION.starts_from_social_contact is True
    assert result.state_delta["project.start"] == {
        "project_type": "seek_redemption",
        "stage": "owning_the_wrong",
        "milestone": True,
    }


def test_entry_gate_requires_wronged_party_evidence_and_blocks_actor_hostility() -> (
    None
):
    assert (
        evaluate(
            START_SEEK_REDEMPTION,
            _start_state(trust={}),
            BINDINGS,
        ).passes
        is False
    )
    assert (
        evaluate(
            START_SEEK_REDEMPTION,
            _start_state(pair_tags={(ACTOR, TARGET): frozenset({"hostile_to"})}),
            BINDINGS,
        ).passes
        is False
    )


@pytest.mark.parametrize(
    ("state", "label", "delta_key"),
    (
        (
            _advance_state(_project(target_active=False)),
            "End amends whose wronged party is no longer available",
            "project.abandon",
        ),
        (
            _advance_state(
                _project(stage="earning_forgiveness", progress=1.0),
            ),
            "Have the amends accepted",
            "project.complete",
        ),
        (
            _advance_state(_project(), trust={(TARGET, ACTOR): -3}),
            "Abandon amends that are thrown back",
            "project.abandon",
        ),
        (
            # Strict boundary: trust_below(-2) does not spurn at exactly -2.
            _advance_state(_project(), trust={(TARGET, ACTOR): -2}),
            "Name the wrong without self-exoneration",
            "project.advance",
        ),
        (
            _advance_state(_project(stall_count=3)),
            "Let the attempt at redemption go",
            "project.abandon",
        ),
        (
            _advance_state(_project(progress=1.0)),
            "Turn ownership into amends",
            "project.advance",
        ),
        (
            _advance_state(_project(stage="making_amends", progress=1.0)),
            "Let amends ask for forgiveness",
            "project.advance",
        ),
        (
            _advance_state(
                _project(
                    stage="earning_forgiveness",
                    progress=0.5,
                    due_at=NOW - timedelta(hours=24),
                )
            ),
            "Lose ground through neglected amends",
            "project.stall",
        ),
        (
            _advance_state(_project(progress=0.2)),
            "Name the wrong without self-exoneration",
            "project.advance",
        ),
        (
            _advance_state(_project(stage="making_amends", progress=0.2)),
            "Make one concrete repair",
            "project.advance",
        ),
        (
            _advance_state(_project(stage="earning_forgiveness", progress=0.2)),
            "Leave forgiveness in the wronged party's hands",
            "project.advance",
        ),
    ),
)
def test_full_ladder(state: WorldState, label: str, delta_key: str) -> None:
    result = evaluate(
        ADVANCE_SEEK_REDEMPTION,
        state,
        BINDINGS,
        BranchSelection(mode="authored_order"),
    )
    assert result.branch_label == label
    assert delta_key in result.state_delta
    if delta_key == "project.complete":
        assert result.state_delta == {
            "project.complete": {"milestone": True},
            "entity_tags_target.remove": ["grudge_active"],
        }


def test_completion_needs_no_trust_recovery_and_yields_to_hostility() -> None:
    project = _project(stage="earning_forgiveness", progress=1.0)
    no_trust = evaluate(
        ADVANCE_SEEK_REDEMPTION,
        _advance_state(project),
        BINDINGS,
    )
    actor_hostile = evaluate(
        ADVANCE_SEEK_REDEMPTION,
        _advance_state(project, pair_tags={(ACTOR, TARGET): frozenset({"hostile_to"})}),
        BINDINGS,
    )
    target_hostile = evaluate(
        ADVANCE_SEEK_REDEMPTION,
        _advance_state(
            project,
            pair_tags={(TARGET, ACTOR): frozenset({"hunting"})},
        ),
        BINDINGS,
    )
    assert "project.complete" in no_trust.state_delta
    assert "project.abandon" in actor_hostile.state_delta
    assert "project.abandon" in target_hostile.state_delta


def _create_schema(cur: Any, schema: str) -> None:
    cur.execute(f'CREATE SCHEMA "{schema}"')
    cur.execute(f'SET LOCAL search_path = "{schema}", public')
    cur.execute(
        """
        CREATE TABLE event_types (
            type text PRIMARY KEY, category text NOT NULL,
            severity text NOT NULL, description text
        );
        CREATE TABLE orrery_resolutions (
            id bigint PRIMARY KEY, state_delta jsonb NOT NULL
        );
        CREATE TABLE character_project_states (
            id bigserial PRIMARY KEY, character_entity_id bigint NOT NULL,
            project_type text NOT NULL, status text NOT NULL, stage text NOT NULL,
            target_place_id bigint, target_character_entity_id bigint,
            target_faction_entity_id bigint, progress numeric(5,4) NOT NULL DEFAULT 0,
            stall_count integer NOT NULL DEFAULT 0,
            next_eligible_at_world_time timestamptz, source_chunk_id bigint,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT character_project_states_project_type_check CHECK (
                project_type IN (
                    'plan_relocation', 'recruit_ally', 'build_venture',
                    'pursue_romance'
                )),
            CONSTRAINT character_project_states_stage_by_type_check CHECK (
                (project_type='plan_relocation'
                    AND stage IN ('saving','scouting','committing')) OR
                (project_type='recruit_ally'
                    AND stage IN (
                        'sounding_out','earning_trust','sealing_commitment'
                    )) OR
                (project_type='build_venture'
                    AND stage IN (
                        'laying_groundwork','securing_backing','opening_doors'
                    )) OR
                (project_type='pursue_romance'
                    AND stage IN (
                        'testing_waters','growing_closer','declaring_intentions'
                    ))),
            CONSTRAINT character_project_states_target_by_type_check CHECK (
                (project_type='plan_relocation'
                    AND target_character_entity_id IS NULL) OR
                (project_type='recruit_ally'
                    AND target_place_id IS NULL
                    AND target_character_entity_id IS NOT NULL) OR
                (project_type='build_venture'
                    AND target_place_id IS NULL
                    AND target_character_entity_id IS NULL
                    AND target_faction_entity_id IS NULL) OR
                (project_type='pursue_romance'
                    AND target_place_id IS NULL
                    AND target_character_entity_id IS NOT NULL
                    AND target_faction_entity_id IS NULL)),
            CONSTRAINT character_project_states_completed_target_check CHECK (
                status <> 'completed' OR
                (project_type='plan_relocation' AND target_place_id IS NOT NULL) OR
                (project_type='recruit_ally'
                    AND target_character_entity_id IS NOT NULL) OR
                project_type='build_venture' OR
                (project_type='pursue_romance'
                    AND target_character_entity_id IS NOT NULL))
        );
        CREATE UNIQUE INDEX ux_character_project_states_open_budget
            ON character_project_states(character_entity_id)
            WHERE status IN ('active','paused','stalled');
        """
    )
    cur.execute(
        (
            Path(__file__).parents[2] / "migrations/087_seek_redemption_projects.sql"
        ).read_text()
    )


@pytest.fixture()
def live_redemption_db() -> Iterator[dict[str, Any]]:
    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        with conn.cursor() as cur:
            _create_schema(cur, f"seek_redemption_{uuid4().hex[:12]}")
            cur.execute(
                "SELECT entity_id FROM characters WHERE entity_id IS NOT NULL "
                "ORDER BY id LIMIT 2"
            )
            actor, target = (int(row[0]) for row in cur.fetchall())
            cur.execute(
                "SELECT chunk_id FROM chunk_metadata WHERE world_time IS NOT NULL "
                "ORDER BY chunk_id DESC LIMIT 1"
            )
            chunk = int(cur.fetchone()[0])
            cur.execute(
                "DELETE FROM character_relationships USING characters a, characters t "
                "WHERE character_relationships.character1_id=a.id "
                "AND character_relationships.character2_id=t.id "
                "AND a.entity_id=%s AND t.entity_id=%s",
                (actor, target),
            )
            cur.execute(
                "UPDATE entity_tags et SET cleared_at=now() FROM tags t "
                "WHERE et.tag_id=t.id AND et.entity_id=%s "
                "AND t.tag='grudge_active' AND et.cleared_at IS NULL",
                (target,),
            )
        yield {
            "conn": conn,
            "actor": actor,
            "target": target,
            "chunk": chunk,
            "ids": count(1),
        }
    finally:
        conn.rollback()
        conn.close()


def _apply(db: dict[str, Any], draft: OrreryResolutionDraft) -> dict[str, Any]:
    resolution_id = next(db["ids"])
    with db["conn"].cursor() as cur:
        cur.execute(
            "INSERT INTO orrery_resolutions VALUES (%s,%s::jsonb)",
            (resolution_id, psycopg2.extras.Json(draft.state_delta)),
        )
        _apply_state_delta_sync(
            cur,
            draft,
            resolution_id=resolution_id,
            actor_entity_id=db["actor"],
            target_entity_id=db["target"],
            source_chunk_id=db["chunk"],
            need_tuning=load_need_tuning(),
            project_policy=POLICY,
        )
        cur.execute(
            "SELECT state_delta FROM orrery_resolutions WHERE id=%s", (resolution_id,)
        )
        return cur.fetchone()[0]


def _start_and_ready_for_completion(db: dict[str, Any]) -> OrreryResolutionDraft:
    base = OrreryResolutionDraft(
        template_id="start_seek_redemption",
        priority=17,
        binding_hash="start",
        bindings={"actor": db["actor"], "target": db["target"]},
        branch_label="start",
        narrative_stub="start",
        state_delta={
            "project.start": {
                "project_type": "seek_redemption",
                "stage": "owning_the_wrong",
                "target_character_entity_id": db["target"],
                "milestone": True,
            }
        },
        magnitude=0.4,
    )
    _apply(db, base)
    with db["conn"].cursor() as cur:
        cur.execute(
            "UPDATE character_project_states "
            "SET stage='earning_forgiveness',progress=1 "
            "WHERE character_entity_id=%s",
            (db["actor"],),
        )
    return base


def _completion_delta() -> dict[str, Any]:
    return {
        "project.complete": {"milestone": True},
        "entity_tags_target.remove": ["grudge_active"],
    }


@pytest.mark.requires_postgres
def test_fresh_completion_inserts_reconciliation_and_absent_grudge_is_noop(
    live_redemption_db: dict[str, Any],
) -> None:
    db = live_redemption_db
    base = _start_and_ready_for_completion(db)
    ledger = _apply(
        db,
        replace(
            base,
            template_id="advance_seek_redemption",
            binding_hash="complete",
            state_delta=_completion_delta(),
        ),
    )
    with db["conn"].cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM entity_tags et JOIN tags t ON t.id=et.tag_id "
            "WHERE et.entity_id=%s AND t.tag='grudge_active' "
            "AND et.cleared_at IS NULL",
            (db["target"],),
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            "SELECT cr.relationship_type,cr.emotional_valence,cr.extra_data "
            "FROM character_relationships cr "
            "JOIN characters a ON a.id=cr.character1_id "
            "JOIN characters t ON t.id=cr.character2_id "
            "WHERE a.entity_id=%s AND t.entity_id=%s",
            (db["actor"], db["target"]),
        )
        relationship_type, valence, extra = cur.fetchone()
    assert (relationship_type, valence) == ("complex", "+1|favorable")
    assert extra["orrery_seek_redemption"]["template_id"] == "advance_seek_redemption"
    assert extra["orrery_seek_redemption"]["previous_relationship_type"] is None
    assert extra["orrery_seek_redemption"]["previous_emotional_valence"] is None
    applied = ledger["project.complete"]["applied"]
    assert applied["relationship_mutation"]["relationship_type"] == "complex"
    assert applied["relationship_mutation"]["emotional_valence"] == "+1|favorable"


@pytest.mark.requires_postgres
def test_existing_negative_relationship_is_repaired_and_originals_survive_rewrite(
    live_redemption_db: dict[str, Any],
) -> None:
    db = live_redemption_db
    with db["conn"].cursor() as cur:
        cur.execute(
            "INSERT INTO character_relationships "
            "(character1_id, character2_id, relationship_type, "
            " emotional_valence, dynamic, recent_events, history) "
            "SELECT a.id, t.id, 'enemy', '-4|hostile', 'd', 'r', 'h' "
            "FROM characters a, characters t "
            "WHERE a.entity_id=%s AND t.entity_id=%s",
            (db["actor"], db["target"]),
        )
        cur.execute(
            "INSERT INTO entity_tags (entity_id,tag_id,source_kind,template_id) "
            "SELECT %s,id,'template','test_seek_redemption' FROM tags "
            "WHERE tag='grudge_active'",
            (db["target"],),
        )
    base = _start_and_ready_for_completion(db)
    _apply(
        db,
        replace(
            base,
            template_id="advance_seek_redemption",
            binding_hash="complete-preserve",
            state_delta=_completion_delta(),
        ),
    )
    with db["conn"].cursor() as cur:
        second = _upsert_reconciled_relationship_sync(
            cur,
            actor_entity_id=db["actor"],
            target_entity_id=db["target"],
            template_id="advance_seek_redemption",
            source_chunk_id=db["chunk"],
        )
        cur.execute(
            "SELECT cr.relationship_type,cr.emotional_valence,cr.extra_data "
            "FROM character_relationships cr "
            "JOIN characters a ON a.id=cr.character1_id "
            "JOIN characters t ON t.id=cr.character2_id "
            "WHERE a.entity_id=%s AND t.entity_id=%s",
            (db["actor"], db["target"]),
        )
        relationship_type, valence, extra = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM entity_tags et JOIN tags t ON t.id=et.tag_id "
            "WHERE et.entity_id=%s AND t.tag='grudge_active' "
            "AND et.cleared_at IS NULL",
            (db["target"],),
        )
        assert cur.fetchone()[0] == 0
    assert relationship_type == "complex"
    assert valence == "+1|favorable"
    provenance = extra["orrery_seek_redemption"]
    assert provenance["previous_relationship_type"] == "enemy"
    assert provenance["previous_emotional_valence"] == "-4|hostile"
    assert second["previous_relationship_type"] == "complex"
    assert second["previous_emotional_valence"] == "+1|favorable"
