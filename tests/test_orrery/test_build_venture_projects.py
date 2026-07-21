"""BUILD_VENTURE actor-only project acceptance coverage."""

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
    ADVANCE_BUILD_VENTURE,
    START_BUILD_VENTURE,
)
from nexus.api.slot_utils import get_slot_db_url


ACTOR = 10
HUNTER = 20
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
BINDINGS = {Slot.ACTOR: ACTOR}


def _start_state(*, pair_tags: dict[tuple[int, int], frozenset[str]] | None = None):
    return WorldState(
        locations={ACTOR: 1},
        pair_tags=pair_tags or {},
        travel_states={ACTOR: TravelState(status="at_place")},
        project_policy=POLICY,
        routine_anchors={
            (ACTOR, "home"): RoutineAnchor(
                anchor_type="home", place_id=1, mobility_policy="fixed_place"
            )
        },
        world_time=NOW,
    )


def _project(
    *,
    stage: str = "laying_groundwork",
    progress: float = 0.0,
    stall_count: int = 0,
    due_at: datetime = NOW,
) -> ProjectState:
    return ProjectState(
        id=7,
        project_type="build_venture",
        status="active",
        stage=stage,
        progress=progress,
        stall_count=stall_count,
        next_eligible_at_world_time=due_at,
        source_chunk_id=100,
    )


def _advance_state(project: ProjectState, *, world_time: datetime = NOW) -> WorldState:
    return WorldState(
        project_states={ACTOR: project},
        project_policy=POLICY,
        travel_states={ACTOR: TravelState(status="at_place")},
        world_time=world_time,
    )


def test_entry_gate_is_actor_only_stable_and_target_free() -> None:
    eligible = evaluate(START_BUILD_VENTURE, _start_state(), BINDINGS)
    assert eligible.passes is True
    assert START_BUILD_VENTURE.required_slots == (Slot.ACTOR,)
    assert START_BUILD_VENTURE.binds_project_target is False
    assert START_BUILD_VENTURE.binds_project_faction is False
    assert START_BUILD_VENTURE.starts_from_social_contact is False
    assert eligible.state_delta == {
        "project.start": {
            "project_type": "build_venture",
            "stage": "laying_groundwork",
            "milestone": True,
        }
    }

    hunted = _start_state(pair_tags={(HUNTER, ACTOR): frozenset({"hunting"})})
    hostile = _start_state(pair_tags={(HUNTER, ACTOR): frozenset({"hostile_to"})})
    assert evaluate(START_BUILD_VENTURE, hunted, BINDINGS).passes is False
    assert evaluate(START_BUILD_VENTURE, hostile, BINDINGS).passes is False


@pytest.mark.parametrize(
    ("project", "expected_label", "delta_key"),
    (
        (
            _project(stage="opening_doors", progress=1.0),
            "Open the doors",
            "project.complete",
        ),
        (
            _project(stall_count=POLICY.stall_abandon_threshold),
            "Let the venture go",
            "project.abandon",
        ),
        (
            _project(stage="laying_groundwork", progress=1.0),
            "Turn groundwork into backing",
            "project.advance",
        ),
        (
            _project(stage="securing_backing", progress=1.0),
            "Turn backing into an opening",
            "project.advance",
        ),
        (
            _project(
                stage="opening_doors",
                progress=0.5,
                due_at=NOW - timedelta(hours=POLICY.advance_interval_hours),
            ),
            "Lose ground through neglect",
            "project.stall",
        ),
        (
            _project(stage="laying_groundwork", progress=0.2),
            "Make the venture legible",
            "project.advance",
        ),
        (
            _project(stage="securing_backing", progress=0.2),
            "Secure one more commitment",
            "project.advance",
        ),
        (
            _project(stage="opening_doors", progress=0.2),
            "Finish the next opening task",
            "project.advance",
        ),
    ),
)
def test_full_branch_ladder_traversal(
    project: ProjectState, expected_label: str, delta_key: str
) -> None:
    resolution = evaluate(
        ADVANCE_BUILD_VENTURE,
        _advance_state(project),
        BINDINGS,
        BranchSelection(mode="authored_order"),
    )
    assert resolution.branch_label == expected_label
    assert delta_key in resolution.state_delta
    if expected_label in {
        "Make the venture legible",
        "Secure one more commitment",
        "Finish the next opening task",
    }:
        assert resolution.promotable is False


def _create_runtime_schema(cur: Any, schema: str) -> None:
    cur.execute(f'CREATE SCHEMA "{schema}"')
    cur.execute(f'SET LOCAL search_path = "{schema}", public')
    cur.execute(
        """
        CREATE TABLE event_types (
            type text PRIMARY KEY, category text NOT NULL,
            severity text NOT NULL, description text
        );
        CREATE TABLE tag_category_registry (
            category text NOT NULL, entity_kind entity_kind NOT NULL,
            prompt_order integer NOT NULL, description text,
            deprecated boolean NOT NULL DEFAULT false,
            replacement_categories text[], PRIMARY KEY (category, entity_kind)
        );
        CREATE TABLE tags (
            id bigserial PRIMARY KEY, tag text UNIQUE NOT NULL,
            category text NOT NULL, is_ephemeral boolean NOT NULL DEFAULT false,
            clearance_kind entity_tag_clearance_kind,
            reapplication_policy entity_tag_reapplication_policy,
            clear_on jsonb, synonym_for bigint,
            deprecated boolean NOT NULL DEFAULT false, description text,
            CHECK (is_ephemeral = (clearance_kind IS NOT NULL))
        );
        CREATE TABLE entity_tags (
            id bigserial PRIMARY KEY, entity_id bigint NOT NULL,
            tag_id bigint NOT NULL, applied_at timestamptz NOT NULL DEFAULT now(),
            applied_at_world_time timestamptz, clear_on_override jsonb,
            cleared_at timestamptz, template_id text,
            source_kind entity_tag_source_kind NOT NULL, source_chunk_id bigint
        );
        CREATE UNIQUE INDEX ix_entity_tags_current
            ON entity_tags (entity_id, tag_id) WHERE cleared_at IS NULL;
        CREATE TABLE orrery_resolutions (
            id bigint PRIMARY KEY, state_delta jsonb NOT NULL
        );
        CREATE TABLE character_project_states (
            id bigserial PRIMARY KEY, character_entity_id bigint NOT NULL,
            project_type text NOT NULL, status text NOT NULL,
            stage text NOT NULL, target_place_id bigint,
            target_character_entity_id bigint, target_faction_entity_id bigint,
            progress numeric(5,4) NOT NULL DEFAULT 0,
            stall_count integer NOT NULL DEFAULT 0,
            next_eligible_at_world_time timestamptz, source_chunk_id bigint,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT character_project_states_project_type_check
                CHECK (project_type IN ('plan_relocation', 'recruit_ally')),
            CONSTRAINT character_project_states_stage_by_type_check CHECK (
                (project_type = 'plan_relocation'
                    AND stage IN ('saving', 'scouting', 'committing')) OR
                (project_type = 'recruit_ally'
                    AND stage IN (
                        'sounding_out', 'earning_trust', 'sealing_commitment'
                    ))
            ),
            CONSTRAINT character_project_states_target_by_type_check CHECK (
                (project_type = 'plan_relocation'
                    AND target_character_entity_id IS NULL) OR
                (project_type = 'recruit_ally'
                    AND target_place_id IS NULL
                    AND target_character_entity_id IS NOT NULL)
            ),
            CONSTRAINT character_project_states_completed_target_check CHECK (
                status <> 'completed' OR
                (project_type = 'plan_relocation' AND target_place_id IS NOT NULL) OR
                (project_type = 'recruit_ally'
                    AND target_character_entity_id IS NOT NULL)
            )
        );
        CREATE UNIQUE INDEX ux_character_project_states_open_budget
            ON character_project_states (character_entity_id)
            WHERE status IN ('active', 'paused', 'stalled')
        """
    )
    migration_sql = (
        Path(__file__).parents[2] / "migrations" / "084_build_venture_projects.sql"
    ).read_text()
    cur.execute(migration_sql)


@pytest.fixture()
def live_venture_db() -> Iterator[dict[str, Any]]:
    """Use live entities/time with project writes isolated in a throwaway schema."""

    conn = psycopg2.connect(get_slot_db_url(slot=2))
    schema = f"build_venture_{uuid4().hex[:12]}"
    try:
        with conn.cursor() as cur:
            _create_runtime_schema(cur, schema)
            cur.execute(
                "SELECT entity_id FROM characters WHERE entity_id IS NOT NULL "
                "ORDER BY id LIMIT 2"
            )
            actor, other = (int(row[0]) for row in cur.fetchall())
            cur.execute(
                "SELECT cm.chunk_id, cm.world_time FROM chunk_metadata cm "
                "WHERE cm.world_time IS NOT NULL ORDER BY cm.chunk_id DESC LIMIT 1"
            )
            chunk_id, world_time = cur.fetchone()
        yield {
            "conn": conn,
            "actor": actor,
            "other": other,
            "chunk_id": int(chunk_id),
            "world_time": world_time,
            "resolution_ids": count(1),
        }
    finally:
        conn.rollback()
        conn.close()


def _apply(db: dict[str, Any], draft: OrreryResolutionDraft) -> int:
    resolution_id = next(db["resolution_ids"])
    with db["conn"].cursor() as cur:
        cur.execute(
            "INSERT INTO orrery_resolutions (id, state_delta) VALUES (%s, %s::jsonb)",
            (resolution_id, psycopg2.extras.Json(draft.state_delta)),
        )
        return _apply_state_delta_sync(
            cur,
            draft,
            resolution_id=resolution_id,
            actor_entity_id=int(db["actor"]),
            target_entity_id=None,
            source_chunk_id=int(db["chunk_id"]),
            need_tuning=load_need_tuning(),
            project_policy=POLICY,
        )


def _row(db: dict[str, Any]) -> tuple[Any, ...]:
    with db["conn"].cursor() as cur:
        cur.execute(
            """
            SELECT project_type, status, stage, target_place_id,
                   target_character_entity_id, target_faction_entity_id,
                   progress, stall_count
            FROM character_project_states
            WHERE character_entity_id = %s ORDER BY id DESC LIMIT 1
            """,
            (db["actor"],),
        )
        return cur.fetchone()


@pytest.mark.requires_postgres
def test_live_applier_runs_start_progress_milestones_and_completion(
    live_venture_db: dict[str, Any],
) -> None:
    db = live_venture_db
    actor = int(db["actor"])
    start = OrreryResolutionDraft(
        template_id="start_build_venture",
        priority=17,
        binding_hash="build-start",
        bindings={"actor": actor},
        branch_label="Lay the first groundwork",
        narrative_stub="start",
        state_delta={
            "project.start": {
                "project_type": "build_venture",
                "stage": "laying_groundwork",
                "milestone": True,
            }
        },
        magnitude=0.4,
    )
    assert _apply(db, start) == 0
    assert _row(db)[:6] == (
        "build_venture",
        "active",
        "laying_groundwork",
        None,
        None,
        None,
    )

    progress = replace(
        start,
        template_id="advance_build_venture",
        binding_hash="build-progress",
        state_delta={"project.advance": {"progress_delta": 0.35}},
        promotable=False,
    )
    assert _apply(db, progress) == 0
    assert float(_row(db)[6]) == 0.35

    for stage, next_stage in (
        ("laying_groundwork", "securing_backing"),
        ("securing_backing", "opening_doors"),
    ):
        with db["conn"].cursor() as cur:
            cur.execute(
                "UPDATE character_project_states SET stage = %s, progress = 1, "
                "stall_count = 2 WHERE character_entity_id = %s",
                (stage, actor),
            )
        milestone = replace(
            start,
            template_id="advance_build_venture",
            binding_hash=f"build-{next_stage}",
            state_delta={
                "project.advance": {
                    "stage": next_stage,
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
        )
        assert _apply(db, milestone) == 0
        row = _row(db)
        assert row[2] == next_stage
        assert float(row[6]) == 0.0
        assert row[7] == 0

    with db["conn"].cursor() as cur:
        cur.execute(
            "UPDATE character_project_states SET progress = 1 "
            "WHERE character_entity_id = %s",
            (actor,),
        )
    complete = replace(
        start,
        template_id="advance_build_venture",
        binding_hash="build-complete",
        state_delta={
            "project.complete": {"milestone": True},
            "entity_tags.add": ["proprietor"],
        },
    )
    assert _apply(db, complete) == 1
    assert _row(db)[1] == "completed"
    with db["conn"].cursor() as cur:
        cur.execute(
            """
            SELECT t.tag, et.template_id, et.source_chunk_id
            FROM entity_tags et JOIN tags t ON t.id = et.tag_id
            WHERE et.entity_id = %s AND et.cleared_at IS NULL
            """,
            (actor,),
        )
        assert cur.fetchall() == [
            ("proprietor", "advance_build_venture", db["chunk_id"])
        ]
        cur.execute(
            "SELECT state_delta FROM orrery_resolutions " "WHERE id = %s",
            (next(db["resolution_ids"]) - 1,),
        )
        applied = cur.fetchone()[0]["project.complete"]["applied"]
    assert applied["status"] == "completed"
    assert applied["target_place_id"] is None
    assert applied["target_character_entity_id"] is None
    assert applied["target_faction_entity_id"] is None


@pytest.mark.requires_postgres
def test_live_stall_abandon_and_budget_interaction(
    live_venture_db: dict[str, Any],
) -> None:
    db = live_venture_db
    actor = int(db["actor"])
    other = int(db["other"])
    start = OrreryResolutionDraft(
        template_id="start_build_venture",
        priority=17,
        binding_hash="build-stall-start",
        bindings={"actor": actor},
        branch_label="start",
        narrative_stub="start",
        state_delta={
            "project.start": {
                "project_type": "build_venture",
                "stage": "laying_groundwork",
            }
        },
    )
    _apply(db, start)
    with db["conn"].cursor() as cur:
        cur.execute("SAVEPOINT budget")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                """
                INSERT INTO character_project_states (
                    character_entity_id, project_type, status, stage
                ) VALUES (%s, 'build_venture', 'active', 'laying_groundwork')
                """,
                (actor,),
            )
        cur.execute("ROLLBACK TO SAVEPOINT budget")

    stall = replace(
        start,
        template_id="advance_build_venture",
        binding_hash="build-stall",
        state_delta={"project.stall": {"increment": 1}},
    )
    _apply(db, stall)
    assert _row(db)[1] == "stalled"
    assert _row(db)[7] == 1

    abandon = replace(
        start,
        template_id="advance_build_venture",
        binding_hash="build-abandon",
        state_delta={
            "project.abandon": {
                "reason": "stalled_or_overdue",
                "milestone": True,
            }
        },
    )
    _apply(db, abandon)
    assert _row(db)[1] == "abandoned"
    with db["conn"].cursor() as cur:
        cur.execute(
            """
            INSERT INTO character_project_states (
                character_entity_id, project_type, status, stage
            ) VALUES (%s, 'build_venture', 'active', 'laying_groundwork')
            """,
            (actor,),
        )
        cur.execute(
            """
            INSERT INTO character_project_states (
                character_entity_id, project_type, status, stage
            ) VALUES (%s, 'build_venture', 'active', 'laying_groundwork')
            """,
            (other,),
        )


@pytest.mark.requires_postgres
def test_live_start_rejects_every_target_column(
    live_venture_db: dict[str, Any],
) -> None:
    db = live_venture_db
    for key in (
        "target_place_id",
        "target_character_entity_id",
        "target_faction_entity_id",
    ):
        draft = OrreryResolutionDraft(
            template_id="start_build_venture",
            priority=17,
            binding_hash=f"reject-{key}",
            bindings={"actor": db["actor"]},
            branch_label="reject target",
            narrative_stub="reject",
            state_delta={
                "project.start": {
                    "project_type": "build_venture",
                    "stage": "laying_groundwork",
                    key: 999,
                }
            },
        )
        with db["conn"].cursor() as cur:
            cur.execute("SAVEPOINT reject_target")
            cur.execute(
                "INSERT INTO orrery_resolutions (id, state_delta) "
                "VALUES (%s, '{}'::jsonb)",
                (next(db["resolution_ids"]),),
            )
            with pytest.raises(ValueError, match="forbids all targets"):
                _apply_state_delta_sync(
                    cur,
                    draft,
                    resolution_id=next(db["resolution_ids"]),
                    actor_entity_id=int(db["actor"]),
                    target_entity_id=None,
                    source_chunk_id=int(db["chunk_id"]),
                    need_tuning=load_need_tuning(),
                    project_policy=POLICY,
                )
            cur.execute("ROLLBACK TO SAVEPOINT reject_target")
