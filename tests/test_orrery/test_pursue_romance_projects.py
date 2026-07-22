"""PURSUE_ROMANCE character-targeted project acceptance coverage."""

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
from nexus.agents.orrery.templates import (
    ADVANCE_PURSUE_ROMANCE,
    START_PURSUE_ROMANCE,
)
from nexus.api.slot_utils import get_slot_db_url

ACTOR = 10
TARGET = 20
NOW = datetime(2073, 8, 2, 12, tzinfo=timezone.utc)
POLICY = ProjectPolicy(
    enabled=True,
    advance_interval_hours=24.0,
    max_active_per_character=1,
    stall_abandon_threshold=3,
    abandon_after_stalled_world_hours=168.0,
    milestone_magnitude=0.40,
    coverage_distribution_tolerance=0.05,
)
BINDINGS = {Slot.ACTOR: ACTOR, Slot.TARGET: TARGET}


def _start_state(**changes: Any) -> WorldState:
    values: dict[str, Any] = {
        "locations": {ACTOR: 1},
        "pair_tags": {(ACTOR, TARGET): frozenset({"contact:social"})},
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
    stage: str = "testing_waters",
    progress: float = 0.0,
    stall_count: int = 0,
    due_at: datetime = NOW,
    target_active: bool = True,
) -> ProjectState:
    return ProjectState(
        id=7,
        project_type="pursue_romance",
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


def test_entry_gate_contract_and_all_eligibility_arms() -> None:
    result = evaluate(START_PURSUE_ROMANCE, _start_state(), BINDINGS)
    assert result.passes is True
    assert START_PURSUE_ROMANCE.required_slots == (Slot.ACTOR, Slot.TARGET)
    assert START_PURSUE_ROMANCE.starts_from_social_contact is True
    assert result.state_delta["project.start"] == {
        "project_type": "pursue_romance",
        "stage": "testing_waters",
        "milestone": True,
    }
    for state in (
        _start_state(
            pair_tags={(ACTOR, TARGET): frozenset({"contact:intimate"})},
        ),
        _start_state(pair_tags={}, trust={(ACTOR, TARGET): 1}),
        _start_state(
            pair_tags={},
            relationship_types={(TARGET, ACTOR): frozenset({"friend"})},
        ),
    ):
        assert evaluate(START_PURSUE_ROMANCE, state, BINDINGS).passes is True


@pytest.mark.parametrize(
    "changes",
    (
        {"tags": {ACTOR: frozenset({"partnered_exclusively"})}},
        {"tags": {ACTOR: frozenset({"married"})}},
        {"tags": {ACTOR: frozenset({"closeted"})}},
        {"tags": {ACTOR: frozenset({"focus_committed"})}},
        {"tags": {ACTOR: frozenset({"recently_traumatized_intimate"})}},
        {"tags": {ACTOR: frozenset({"religiously_abstinent"})}},
        {"tags": {ACTOR: frozenset({"vow_of_celibacy"})}},
        {"tags": {ACTOR: frozenset({"libido_absent"})}},
        {"relationship_types": {(ACTOR, TARGET): frozenset({"romantic"})}},
        {"pair_tags": {(TARGET, ACTOR): frozenset({"hostile_to"})}},
        {"pair_tags": {(ACTOR, TARGET): frozenset({"hunting"})}},
    ),
)
def test_entry_gate_blocks_partnered_suppressed_or_hostile_actors(
    changes: dict[str, Any],
) -> None:
    assert (
        evaluate(START_PURSUE_ROMANCE, _start_state(**changes), BINDINGS).passes
        is False
    )


@pytest.mark.parametrize(
    ("state", "label", "delta_key"),
    (
        (
            _advance_state(_project(target_active=False)),
            "End a courtship whose target is no longer available",
            "project.abandon",
        ),
        (
            _advance_state(
                _project(stage="declaring_intentions", progress=1.0),
                trust={(ACTOR, TARGET): 2, (TARGET, ACTOR): 1},
            ),
            "Declare the feeling and be answered",
            "project.complete",
        ),
        (
            _advance_state(_project(), trust={(TARGET, ACTOR): -2}),
            "Withdraw after being rebuffed",
            "project.abandon",
        ),
        (
            _advance_state(_project(stall_count=3)),
            "Let the courtship go rather than force it",
            "project.abandon",
        ),
        (
            _advance_state(_project(progress=1.0)),
            "Let tentative interest become closeness",
            "project.advance",
        ),
        (
            _advance_state(_project(stage="growing_closer", progress=1.0)),
            "Move from closeness toward declared intention",
            "project.advance",
        ),
        (
            _advance_state(
                _project(
                    stage="declaring_intentions",
                    progress=0.5,
                    due_at=NOW - timedelta(hours=24),
                )
            ),
            "Lose romantic ground through neglect",
            "project.stall",
        ),
        (
            _advance_state(_project(progress=0.2)),
            "Offer another honest opening",
            "project.advance",
        ),
        (
            _advance_state(_project(stage="growing_closer", progress=0.2)),
            "Build closeness through chosen time",
            "project.advance",
        ),
        (
            _advance_state(_project(stage="declaring_intentions", progress=0.2)),
            "Make the next intention legible",
            "project.advance",
        ),
    ),
)
def test_full_ladder_and_terminals(
    state: WorldState, label: str, delta_key: str
) -> None:
    result = evaluate(
        ADVANCE_PURSUE_ROMANCE,
        state,
        BINDINGS,
        BranchSelection(mode="authored_order"),
    )
    assert result.branch_label == label
    assert delta_key in result.state_delta
    if label == "Declare the feeling and be answered":
        assert result.state_delta["mood.set"] == {"mood": "elated"}
    if label == "Withdraw after being rebuffed":
        assert result.state_delta["mood.set"] == {"mood": "sour"}
    if label in {
        "Offer another honest opening",
        "Build closeness through chosen time",
        "Make the next intention legible",
    }:
        assert result.promotable is False


def test_completion_requires_mutual_warmth() -> None:
    project = _project(stage="declaring_intentions", progress=1.0)
    cold = evaluate(ADVANCE_PURSUE_ROMANCE, _advance_state(project), BINDINGS)
    warm = evaluate(
        ADVANCE_PURSUE_ROMANCE,
        _advance_state(project, trust={(ACTOR, TARGET): 2, (TARGET, ACTOR): 1}),
        BINDINGS,
    )
    # One-sided warmth must NOT complete: forward-only (the actor is smitten,
    # the target neutral) and reverse-only (the target warm, the actor cooled).
    forward_only = evaluate(
        ADVANCE_PURSUE_ROMANCE,
        _advance_state(project, trust={(ACTOR, TARGET): 2, (TARGET, ACTOR): 0}),
        BINDINGS,
    )
    reverse_only = evaluate(
        ADVANCE_PURSUE_ROMANCE,
        _advance_state(project, trust={(ACTOR, TARGET): 0, (TARGET, ACTOR): 1}),
        BINDINGS,
    )
    assert "project.complete" not in cold.state_delta
    assert "project.complete" in warm.state_delta
    assert "project.complete" not in forward_only.state_delta
    assert "project.complete" not in reverse_only.state_delta


def test_completion_yields_to_hostility_despite_mutual_warmth() -> None:
    """An active hostile edge routes a warm, due courtship to the rebuffed
    arm instead of completing it (the completion arm's hostility exclusion)."""

    project = _project(stage="declaring_intentions", progress=1.0)
    hostile = evaluate(
        ADVANCE_PURSUE_ROMANCE,
        _advance_state(
            project,
            trust={(ACTOR, TARGET): 2, (TARGET, ACTOR): 1},
            pair_tags={(TARGET, ACTOR): frozenset({"hunting"})},
        ),
        BINDINGS,
    )
    assert "project.complete" not in hostile.state_delta
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
                    'plan_relocation', 'recruit_ally', 'build_venture'
                )),
            CONSTRAINT character_project_states_stage_by_type_check CHECK (
                (project_type = 'plan_relocation'
                    AND stage IN ('saving', 'scouting', 'committing')) OR
                (project_type = 'recruit_ally'
                    AND stage IN (
                        'sounding_out', 'earning_trust', 'sealing_commitment'
                    )) OR
                (project_type = 'build_venture'
                    AND stage IN (
                        'laying_groundwork', 'securing_backing', 'opening_doors'
                    ))),
            CONSTRAINT character_project_states_target_by_type_check CHECK (
                (project_type = 'plan_relocation'
                    AND target_character_entity_id IS NULL) OR
                (project_type = 'recruit_ally'
                    AND target_place_id IS NULL
                    AND target_character_entity_id IS NOT NULL) OR
                (project_type = 'build_venture'
                    AND target_place_id IS NULL
                    AND target_character_entity_id IS NULL
                    AND target_faction_entity_id IS NULL)),
            CONSTRAINT character_project_states_completed_target_check CHECK (
                status <> 'completed' OR
                (project_type = 'plan_relocation'
                    AND target_place_id IS NOT NULL) OR
                (project_type = 'recruit_ally'
                    AND target_character_entity_id IS NOT NULL) OR
                project_type = 'build_venture')
        );
        CREATE UNIQUE INDEX ux_character_project_states_open_budget
            ON character_project_states(character_entity_id)
            WHERE status IN ('active','paused','stalled');
        """
    )
    cur.execute(
        (
            Path(__file__).parents[2] / "migrations/085_pursue_romance_projects.sql"
        ).read_text()
    )


@pytest.fixture()
def live_romance_db() -> Iterator[dict[str, Any]]:
    conn = psycopg2.connect(get_slot_db_url(slot=2))
    try:
        with conn.cursor() as cur:
            _create_schema(cur, f"pursue_romance_{uuid4().hex[:12]}")
            cur.execute(
                "SELECT entity_id FROM characters WHERE entity_id IS NOT NULL "
                "ORDER BY id LIMIT 2"
            )
            actor, target = (int(row[0]) for row in cur.fetchall())
            cur.execute(
                "SELECT chunk_id FROM chunk_metadata WHERE world_time IS NOT NULL "
                "ORDER BY chunk_id DESC LIMIT 1"
            )
            chunk_id = int(cur.fetchone()[0])
            cur.execute(
                "DELETE FROM character_relationships USING characters a, characters t "
                "WHERE character_relationships.character1_id=a.id AND "
                "character_relationships.character2_id=t.id "
                "AND a.entity_id=%s AND t.entity_id=%s",
                (actor, target),
            )
        yield {
            "conn": conn,
            "actor": actor,
            "target": target,
            "chunk": chunk_id,
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
def test_sync_applier_fresh_romance_and_overwrite_preserve_first_provenance(
    live_romance_db: dict[str, Any],
) -> None:
    db = live_romance_db
    base = OrreryResolutionDraft(
        template_id="start_pursue_romance",
        priority=17,
        binding_hash="start",
        bindings={"actor": db["actor"], "target": db["target"]},
        branch_label="start",
        narrative_stub="start",
        state_delta={
            "project.start": {
                "project_type": "pursue_romance",
                "stage": "testing_waters",
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
            "SET stage='declaring_intentions', progress=1 "
            "WHERE character_entity_id=%s",
            (db["actor"],),
        )
    complete = replace(
        base,
        template_id="advance_pursue_romance",
        binding_hash="complete",
        state_delta={
            "project.complete": {"milestone": True},
            "entity_pair_tags.add_outbound": ["contact:intimate"],
        },
    )
    ledger = _apply(db, complete)
    with db["conn"].cursor() as cur:
        cur.execute(
            "SELECT cr.relationship_type, cr.emotional_valence, cr.extra_data "
            "FROM character_relationships cr "
            "JOIN characters a ON a.id=cr.character1_id "
            "JOIN characters t ON t.id=cr.character2_id "
            "WHERE a.entity_id=%s AND t.entity_id=%s",
            (db["actor"], db["target"]),
        )
        relationship_type, valence, extra = cur.fetchone()
    assert (relationship_type, valence) == ("romantic", "+4|admiring")
    assert extra["orrery_pursue_romance"]["previous_relationship_type"] is None
    assert (
        ledger["project.complete"]["applied"]["relationship_mutation"][
            "relationship_type"
        ]
        == "romantic"
    )

    with db["conn"].cursor() as cur:
        cur.execute(
            "UPDATE character_relationships SET relationship_type='friend', "
            "extra_data='{}'::jsonb "
            "WHERE character1_id=(SELECT id FROM characters WHERE entity_id=%s) "
            "AND character2_id=(SELECT id FROM characters WHERE entity_id=%s)",
            (db["actor"], db["target"]),
        )
        cur.execute(
            "UPDATE character_project_states "
            "SET status='active', stage='declaring_intentions', progress=1 "
            "WHERE character_entity_id=%s",
            (db["actor"],),
        )
    _apply(db, replace(complete, binding_hash="complete-again"))
    with db["conn"].cursor() as cur:
        cur.execute(
            "SELECT cr.relationship_type, cr.extra_data "
            "FROM character_relationships cr "
            "JOIN characters a ON a.id=cr.character1_id "
            "JOIN characters t ON t.id=cr.character2_id "
            "WHERE a.entity_id=%s AND t.entity_id=%s",
            (db["actor"], db["target"]),
        )
        relationship_type, extra = cur.fetchone()
    assert relationship_type == "romantic"
    assert extra["orrery_pursue_romance"]["previous_relationship_type"] == "friend"

    with db["conn"].cursor() as cur:
        cur.execute(
            "UPDATE character_relationships SET relationship_type='rival' "
            "WHERE character1_id=(SELECT id FROM characters WHERE entity_id=%s) "
            "AND character2_id=(SELECT id FROM characters WHERE entity_id=%s)",
            (db["actor"], db["target"]),
        )
        cur.execute(
            "UPDATE character_project_states SET status='active', "
            "stage='declaring_intentions', progress=1 "
            "WHERE character_entity_id=%s",
            (db["actor"],),
        )
    _apply(db, replace(complete, binding_hash="complete-third"))
    with db["conn"].cursor() as cur:
        cur.execute(
            "SELECT cr.extra_data FROM character_relationships cr "
            "JOIN characters a ON a.id=cr.character1_id "
            "JOIN characters t ON t.id=cr.character2_id "
            "WHERE a.entity_id=%s AND t.entity_id=%s",
            (db["actor"], db["target"]),
        )
        extra = cur.fetchone()[0]
    assert extra["orrery_pursue_romance"]["previous_relationship_type"] == "friend"
