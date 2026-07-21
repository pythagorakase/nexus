"""COURT_PATRON character-targeted project acceptance coverage."""

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

from nexus.agents.orrery.events import _apply_state_delta_sync
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
from nexus.agents.orrery.templates import ADVANCE_COURT_PATRON, START_COURT_PATRON
from nexus.api.slot_utils import get_slot_db_url

ACTOR = 10
TARGET = 20
FACTION = 30
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
        "pair_tags": {
            (ACTOR, TARGET): frozenset({"contact:social"}),
            (TARGET, ACTOR): frozenset({"authority_over"}),
        },
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
    stage: str = "gaining_notice",
    progress: float = 0.0,
    stall_count: int = 0,
    due_at: datetime = NOW,
    target_active: bool = True,
) -> ProjectState:
    return ProjectState(
        id=7,
        project_type="court_patron",
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


def test_entry_gate_power_marker_or_clause_and_contract() -> None:
    arms = (
        _start_state(
            pair_tags={
                (ACTOR, TARGET): frozenset({"contact:social"}),
                (TARGET, FACTION): frozenset({"status:senior"}),
            }
        ),
        _start_state(
            pair_tags={(ACTOR, TARGET): frozenset({"contact:social"})},
            tags={TARGET: frozenset({"leader"})},
        ),
        _start_state(),
    )
    for state in arms:
        assert evaluate(START_COURT_PATRON, state, BINDINGS).passes is True
    result = evaluate(START_COURT_PATRON, arms[0], BINDINGS)
    assert START_COURT_PATRON.required_slots == (Slot.ACTOR, Slot.TARGET)
    assert START_COURT_PATRON.starts_from_social_contact is True
    assert result.state_delta["project.start"] == {
        "project_type": "court_patron",
        "stage": "gaining_notice",
        "milestone": True,
    }


def test_entry_gate_requires_social_base_and_power_and_blocks_redundancy() -> None:
    assert (
        evaluate(
            START_COURT_PATRON,
            _start_state(pair_tags={(ACTOR, TARGET): frozenset({"contact:social"})}),
            BINDINGS,
        ).passes
        is False
    )
    assert (
        evaluate(
            START_COURT_PATRON,
            _start_state(pair_tags={(TARGET, ACTOR): frozenset({"authority_over"})}),
            BINDINGS,
        ).passes
        is False
    )
    for changes in (
        {
            "pair_tags": {
                (ACTOR, TARGET): frozenset({"contact:social"}),
                (TARGET, ACTOR): frozenset({"authority_over", "sponsors"}),
            }
        },
        {"relationship_types": {(ACTOR, TARGET): frozenset({"patron"})}},
        {
            "pair_tags": {
                (ACTOR, TARGET): frozenset({"contact:social", "hostile_to"}),
                (TARGET, ACTOR): frozenset({"authority_over"}),
            }
        },
    ):
        assert (
            evaluate(START_COURT_PATRON, _start_state(**changes), BINDINGS).passes
            is False
        )


@pytest.mark.parametrize(
    ("state", "label", "delta_key"),
    (
        (
            _advance_state(_project(target_active=False)),
            "End a patronage effort whose target is no longer available",
            "project.abandon",
        ),
        (
            _advance_state(
                _project(stage="securing_favor", progress=1.0),
                trust={(TARGET, ACTOR): 2},
            ),
            "Secure the patron's favor",
            "project.complete",
        ),
        (
            _advance_state(_project(), trust={(TARGET, ACTOR): -2}),
            "Withdraw after being spurned",
            "project.abandon",
        ),
        (
            # Strict boundary: a merely wary patron (-1) does NOT spurn —
            # trust_below(-1) means strictly worse than wary; the courtship
            # keeps making routine progress instead.
            _advance_state(_project(), trust={(TARGET, ACTOR): -1}),
            "Make useful work visible",
            "project.advance",
        ),
        (
            _advance_state(_project(stall_count=3)),
            "Let the bid for patronage go",
            "project.abandon",
        ),
        (
            _advance_state(_project(progress=1.0)),
            "Turn notice into a chance to prove worth",
            "project.advance",
        ),
        (
            _advance_state(_project(stage="proving_worth", progress=1.0)),
            "Ask proven worth to become favor",
            "project.advance",
        ),
        (
            _advance_state(
                _project(
                    stage="securing_favor",
                    progress=0.5,
                    due_at=NOW - timedelta(hours=24),
                )
            ),
            "Lose ground through neglect",
            "project.stall",
        ),
        (
            _advance_state(_project(progress=0.2)),
            "Make useful work visible",
            "project.advance",
        ),
        (
            _advance_state(_project(stage="proving_worth", progress=0.2)),
            "Prove reliable under scrutiny",
            "project.advance",
        ),
        (
            _advance_state(_project(stage="securing_favor", progress=0.2)),
            "Make the next claim on favor legible",
            "project.advance",
        ),
    ),
)
def test_full_ladder(state: WorldState, label: str, delta_key: str) -> None:
    result = evaluate(
        ADVANCE_COURT_PATRON,
        state,
        BINDINGS,
        BranchSelection(mode="authored_order"),
    )
    assert result.branch_label == label
    assert delta_key in result.state_delta
    if delta_key == "project.complete":
        assert result.state_delta == {
            "project.complete": {"milestone": True},
            "entity_pair_tags.add_inbound": ["sponsors"],
            "entity_pair_tags.add_outbound": ["obligation"],
        }


def test_completion_uses_patron_reverse_trust_and_yields_to_hostility() -> None:
    project = _project(stage="securing_favor", progress=1.0)
    reverse = evaluate(
        ADVANCE_COURT_PATRON,
        _advance_state(project, trust={(TARGET, ACTOR): 2}),
        BINDINGS,
    )
    forward_only = evaluate(
        ADVANCE_COURT_PATRON,
        _advance_state(project, trust={(ACTOR, TARGET): 2}),
        BINDINGS,
    )
    hostile = evaluate(
        ADVANCE_COURT_PATRON,
        _advance_state(
            project,
            trust={(TARGET, ACTOR): 2},
            pair_tags={(ACTOR, TARGET): frozenset({"hostile_to"})},
        ),
        BINDINGS,
    )
    assert "project.complete" in reverse.state_delta
    assert "project.complete" not in forward_only.state_delta
    assert "project.abandon" in hostile.state_delta


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
            Path(__file__).parents[2] / "migrations/086_court_patron_projects.sql"
        ).read_text()
    )


@pytest.fixture()
def live_patron_db() -> Iterator[dict[str, Any]]:
    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        with conn.cursor() as cur:
            _create_schema(cur, f"court_patron_{uuid4().hex[:12]}")
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


@pytest.mark.requires_postgres
def test_completion_applies_inbound_outbound_and_patron_relationship(
    live_patron_db: dict[str, Any],
) -> None:
    db = live_patron_db
    base = OrreryResolutionDraft(
        template_id="start_court_patron",
        priority=17,
        binding_hash="start",
        bindings={"actor": db["actor"], "target": db["target"]},
        branch_label="start",
        narrative_stub="start",
        state_delta={
            "project.start": {
                "project_type": "court_patron",
                "stage": "gaining_notice",
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
            "SET stage='securing_favor',progress=1 "
            "WHERE character_entity_id=%s",
            (db["actor"],),
        )
    ledger = _apply(
        db,
        replace(
            base,
            template_id="advance_court_patron",
            binding_hash="complete",
            state_delta={
                "project.complete": {"milestone": True},
                "entity_pair_tags.add_inbound": ["sponsors"],
                "entity_pair_tags.add_outbound": ["obligation"],
            },
        ),
    )
    with db["conn"].cursor() as cur:
        cur.execute(
            "SELECT ept.subject_entity_id,ept.object_entity_id,pt.tag "
            "FROM entity_pair_tags ept "
            "JOIN pair_tags pt ON pt.id=ept.pair_tag_id WHERE ept.cleared_at IS NULL "
            "AND ((ept.subject_entity_id=%s AND ept.object_entity_id=%s "
            "AND pt.tag='sponsors') OR (ept.subject_entity_id=%s "
            "AND ept.object_entity_id=%s AND pt.tag='obligation')) ORDER BY pt.tag",
            (db["target"], db["actor"], db["actor"], db["target"]),
        )
        assert cur.fetchall() == [
            (db["actor"], db["target"], "obligation"),
            (db["target"], db["actor"], "sponsors"),
        ]
        cur.execute(
            "SELECT cr.relationship_type,cr.emotional_valence,cr.extra_data "
            "FROM character_relationships cr "
            "JOIN characters a ON a.id=cr.character1_id "
            "JOIN characters t ON t.id=cr.character2_id "
            "WHERE a.entity_id=%s AND t.entity_id=%s",
            (db["actor"], db["target"]),
        )
        relationship_type, valence, extra = cur.fetchone()
    assert (relationship_type, valence) == ("patron", "+2|friendly")
    assert extra["orrery_court_patron"]["template_id"] == "advance_court_patron"
    applied = ledger["project.complete"]["applied"]
    assert applied["relationship_mutation"]["relationship_type"] == "patron"
    assert {mutation["operation"] for mutation in applied["pair_tag_mutations"]} == {
        "add_inbound",
        "add_outbound",
    }


@pytest.mark.requires_postgres
def test_completion_preserves_existing_relationship_valence(
    live_patron_db: dict[str, Any],
) -> None:
    """The conflict arm updates the type but never the valence — the family
    convention (recruit_ally, pursue_romance); valence movement on existing
    rows is seek_redemption's deliberate innovation, not patron's."""

    db = live_patron_db
    with db["conn"].cursor() as cur:
        cur.execute(
            "INSERT INTO character_relationships "
            "(character1_id, character2_id, relationship_type, "
            " emotional_valence, dynamic, recent_events, history) "
            "SELECT a.id, t.id, 'mentor', '+4|admiring', 'd', 'r', 'h' "
            "FROM characters a, characters t "
            "WHERE a.entity_id=%s AND t.entity_id=%s",
            (db["actor"], db["target"]),
        )
    base = OrreryResolutionDraft(
        template_id="start_court_patron",
        priority=17,
        binding_hash="start-preserve",
        bindings={"actor": db["actor"], "target": db["target"]},
        branch_label="start",
        narrative_stub="start",
        state_delta={
            "project.start": {
                "project_type": "court_patron",
                "stage": "gaining_notice",
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
            "SET stage='securing_favor',progress=1 "
            "WHERE character_entity_id=%s",
            (db["actor"],),
        )
    _apply(
        db,
        replace(
            base,
            template_id="advance_court_patron",
            binding_hash="complete-preserve",
            state_delta={
                "project.complete": {"milestone": True},
                "entity_pair_tags.add_inbound": ["sponsors"],
                "entity_pair_tags.add_outbound": ["obligation"],
            },
        ),
    )
    with db["conn"].cursor() as cur:
        cur.execute(
            "SELECT cr.relationship_type,cr.emotional_valence,cr.extra_data "
            "FROM character_relationships cr "
            "JOIN characters a ON a.id=cr.character1_id "
            "JOIN characters t ON t.id=cr.character2_id "
            "WHERE a.entity_id=%s AND t.entity_id=%s",
            (db["actor"], db["target"]),
        )
        relationship_type, valence, extra = cur.fetchone()
    assert relationship_type == "patron"
    assert valence == "+4|admiring"
    assert (
        extra["orrery_court_patron"]["previous_relationship_type"] == "mentor"
    )
