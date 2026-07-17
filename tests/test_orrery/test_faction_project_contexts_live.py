"""Rollback-only live coverage for faction-bound Orrery project contexts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.audit import explain_dry_run
from nexus.agents.orrery.events import (
    _apply_project_advance_sync,
    _apply_state_delta_sync,
    _insert_resolution_sync,
)
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    compose_actor_bindings,
    compose_actor_faction_bindings,
    compose_actor_target_bindings,
    compose_actor_target_faction_bindings,
    hydrate_world_state,
    resolve_dry_run,
)
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    DriveBand,
    ProjectPolicy,
    Slot,
    Template,
    project_faction_is,
)
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres

LIVE_SLOT = 5
POLICY = ProjectPolicy(enabled=True, advance_interval_hours=24.0)
START_FACTION_PROJECT = Template(
    id="test_start_faction_project",
    priority=10,
    drive_band=DriveBand.PROJECT_IDENTITY,
    blurb="Rollback-only faction project entry fixture.",
    required_slots=(Slot.ACTOR, Slot.FACTION),
    package_gate=ALWAYS,
    branches=(
        Branch(
            label="Bind the institution",
            conditions=ALWAYS,
            narrative_stub="{actor} opens a project with {faction}.",
            state_delta={
                "project.start": {
                    "project_type": "plan_relocation",
                    "stage": "saving",
                }
            },
        ),
    ),
)
ADVANCE_FACTION_PROJECT = Template(
    id="test_advance_faction_project",
    priority=10,
    drive_band=DriveBand.PROJECT_IDENTITY,
    blurb="Rollback-only faction project continuation fixture.",
    required_slots=(Slot.ACTOR, Slot.FACTION),
    package_gate=project_faction_is(Slot.FACTION),
    branches=(
        Branch(
            label="Advance with the institution",
            conditions=ALWAYS,
            narrative_stub="{actor} advances the project with {faction}.",
            state_delta={"project.advance": {"progress_delta": 0.25}},
        ),
    ),
    binds_project_faction=True,
)
TRIPLE_TEMPLATE = Template(
    id="test_actor_target_faction_product",
    priority=10,
    drive_band=DriveBand.PROJECT_IDENTITY,
    blurb="Rollback-only target by faction product fixture.",
    required_slots=(Slot.ACTOR, Slot.TARGET, Slot.FACTION),
    package_gate=ALWAYS,
    branches=(
        Branch(
            label="Coordinate the product",
            conditions=ALWAYS,
            narrative_stub="{actor} coordinates {target} with {faction}.",
        ),
    ),
)


@pytest.fixture()
def faction_context_db() -> Iterator[dict[str, Any]]:
    """Apply 081 and build isolated slot-5 fixtures in one transaction."""

    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    raw_connection = connection.connection.driver_connection
    migration_sql = (
        Path(__file__).parents[2] / "migrations" / "081_faction_project_contexts.sql"
    ).read_text()
    try:
        with raw_connection.cursor() as cur:
            cur.execute(migration_sql)
        token = uuid4().hex[:12]
        place_id = int(
            session.execute(
                text("SELECT id FROM places ORDER BY id LIMIT 1")
            ).scalar_one()
        )
        chunk_id = int(
            session.execute(text("SELECT max(id) FROM narrative_chunks")).scalar_one()
        )
        faction_ids = [
            int(value)
            for value in session.execute(
                text(
                    """
                    SELECT f.entity_id
                    FROM factions f
                    JOIN entities e ON e.id = f.entity_id
                    WHERE f.entity_id IS NOT NULL AND e.is_active
                    ORDER BY f.entity_id
                    LIMIT 2
                    """
                )
            ).scalars()
        ]
        if len(faction_ids) != 2:
            pytest.skip("save_05 needs two active faction entities")

        actors: dict[str, int] = {}
        character_ids: dict[str, int] = {}
        for label in ("bound", "zero", "target_a", "target_b"):
            entity_id = int(
                session.execute(
                    text(
                        """
                        INSERT INTO entities (kind, is_active)
                        VALUES ('character', true)
                        RETURNING id
                        """
                    )
                ).scalar_one()
            )
            character_id = int(
                session.execute(
                    text(
                        """
                        INSERT INTO characters (name, entity_id)
                        VALUES (:name, :entity_id)
                        RETURNING id
                        """
                    ),
                    {
                        "name": f"faction-context-{token}-{label}",
                        "entity_id": entity_id,
                    },
                ).scalar_one()
            )
            actors[label] = entity_id
            character_ids[label] = character_id

        for label in ("bound", "zero"):
            session.execute(
                text(
                    """
                    INSERT INTO character_routine_anchors (
                        character_entity_id, anchor_type, place_id,
                        mobility_policy, source
                    ) VALUES (
                        :entity_id, 'home', :place_id, 'fixed_place',
                        'test_faction_project_contexts_live'
                    )
                    """
                ),
                {"entity_id": actors[label], "place_id": place_id},
            )

        for faction_id in faction_ids:
            session.execute(
                text(
                    """
                    INSERT INTO entity_pair_tags (
                        subject_entity_id, object_entity_id, pair_tag_id,
                        source_kind, template_id
                    )
                    SELECT :actor_id, :faction_id, pt.id,
                           'template', 'test_faction_project_contexts_live'
                    FROM pair_tags pt
                    WHERE pt.tag = 'obligation'
                    """
                ),
                {"actor_id": actors["bound"], "faction_id": faction_id},
            )

        for target_label in ("target_a", "target_b"):
            session.execute(
                text(
                    """
                    INSERT INTO character_relationships (
                        character1_id, character2_id, relationship_type,
                        emotional_valence, dynamic, recent_events, history
                    ) VALUES (
                        :actor_character_id, :target_character_id, 'associate',
                        '+1|fixture', 'Rollback-only faction context fixture.',
                        'No persistent events.', 'Created for issue 477 coverage.'
                    )
                    """
                ),
                {
                    "actor_character_id": character_ids["bound"],
                    "target_character_id": character_ids[target_label],
                },
            )
        session.execute(
            text(
                """
                INSERT INTO character_relationships (
                    character1_id, character2_id, relationship_type,
                    emotional_valence, dynamic, recent_events, history
                ) VALUES (
                    :actor_character_id, :target_character_id, 'associate',
                    '+1|fixture', 'Rollback-only zero-edge fixture.',
                    'No persistent events.', 'Created for issue 477 coverage.'
                )
                """
            ),
            {
                "actor_character_id": character_ids["zero"],
                "target_character_id": character_ids["target_a"],
            },
        )
        yield {
            "connection": connection,
            "session": session,
            "raw_connection": raw_connection,
            "chunk_id": chunk_id,
            "actors": actors,
            "factions": tuple(faction_ids),
        }
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def _accepted_draft(db: dict[str, Any], draft: OrreryResolutionDraft) -> int:
    actor_id = int(db["actors"]["bound"])
    with db["raw_connection"].cursor() as cur:
        resolution_id = _insert_resolution_sync(
            cur,
            draft,
            tick_chunk_id=int(db["chunk_id"]),
            actor_entity_id=actor_id,
            brief="Accepted rollback-only faction project fixture",
        )
        assert resolution_id is not None
        _apply_state_delta_sync(
            cur,
            draft,
            resolution_id=int(resolution_id),
            actor_entity_id=actor_id,
            target_entity_id=None,
            source_chunk_id=int(db["chunk_id"]),
            need_tuning=load_need_tuning(),
            project_policy=POLICY,
        )
    return int(resolution_id)


def _actor_drafts(
    proposal: Any, actor_id: int, template_id: str
) -> list[OrreryResolutionDraft]:
    return [
        draft
        for draft in proposal.resolutions
        if draft.template_id == template_id and draft.bindings.get("actor") == actor_id
    ]


def test_live_faction_enumeration_is_truthful_distinct_and_ordered(
    faction_context_db: dict[str, Any],
) -> None:
    session = faction_context_db["session"]
    actor_id = int(faction_context_db["actors"]["bound"])
    factions = faction_context_db["factions"]

    bindings = compose_actor_faction_bindings(
        session,
        anchor_chunk_id=int(faction_context_db["chunk_id"]),
        window_chunks=30,
        actor_ids={actor_id},
    )

    assert bindings == tuple(
        {Slot.ACTOR: actor_id, Slot.FACTION: faction_id}
        for faction_id in sorted(factions)
    )


def test_live_zero_edge_actor_keeps_actor_and_target_composition(
    faction_context_db: dict[str, Any],
) -> None:
    session = faction_context_db["session"]
    chunk_id = int(faction_context_db["chunk_id"])
    actor_id = int(faction_context_db["actors"]["zero"])

    actor_bindings = compose_actor_bindings(
        session, anchor_chunk_id=chunk_id, window_chunks=30
    )
    target_bindings = compose_actor_target_bindings(
        session,
        anchor_chunk_id=chunk_id,
        window_chunks=30,
        actor_ids={actor_id},
    )
    faction_bindings = compose_actor_faction_bindings(
        session,
        anchor_chunk_id=chunk_id,
        window_chunks=30,
        actor_ids={actor_id},
    )

    assert {binding[Slot.ACTOR] for binding in actor_bindings} >= {actor_id}
    assert len(target_bindings) == 1
    assert target_bindings[0][Slot.ACTOR] == actor_id
    assert faction_bindings == ()


def test_live_accepted_entry_persists_and_advances_stored_faction(
    faction_context_db: dict[str, Any],
) -> None:
    db = faction_context_db
    session = db["session"]
    actor_id = int(db["actors"]["bound"])
    faction_id = int(min(db["factions"]))
    project_settings = POLICY

    entry = resolve_dry_run(
        session,
        (START_FACTION_PROJECT,),
        anchor_chunk_id=int(db["chunk_id"]),
        window_chunks=30,
        project_settings=project_settings,
    )
    entry_draft = next(
        draft
        for draft in _actor_drafts(entry, actor_id, START_FACTION_PROJECT.id)
        if draft.bindings["faction"] == faction_id
    )
    assert (
        entry_draft.state_delta["project.start"]["target_faction_entity_id"]
        == faction_id
    )
    entry_resolution_id = _accepted_draft(db, entry_draft)

    row = (
        session.execute(
            text(
                """
            SELECT id, target_faction_entity_id, progress
            FROM character_project_states
            WHERE character_entity_id = :actor_id
              AND status IN ('active', 'paused', 'stalled')
            """
            ),
            {"actor_id": actor_id},
        )
        .mappings()
        .one()
    )
    assert row["target_faction_entity_id"] == faction_id
    hydrated = hydrate_world_state(
        session,
        anchor_chunk_id=int(db["chunk_id"]),
        window_chunks=30,
        project_settings=project_settings,
    )
    assert project_faction_is(Slot.FACTION)(
        hydrated,
        {Slot.ACTOR: actor_id, Slot.FACTION: faction_id},
    )

    continuation = resolve_dry_run(
        session,
        (ADVANCE_FACTION_PROJECT,),
        anchor_chunk_id=int(db["chunk_id"]),
        window_chunks=30,
        project_settings=project_settings,
    )
    advance_draft = _actor_drafts(continuation, actor_id, ADVANCE_FACTION_PROJECT.id)[0]
    assert advance_draft.bindings["faction"] == faction_id
    _accepted_draft(db, advance_draft)

    advanced = (
        session.execute(
            text(
                """
            SELECT target_faction_entity_id, progress
            FROM character_project_states
            WHERE id = :project_id
            """
            ),
            {"project_id": row["id"]},
        )
        .mappings()
        .one()
    )
    assert advanced["target_faction_entity_id"] == faction_id
    assert float(advanced["progress"]) == 0.25
    applied = session.execute(
        text("SELECT state_delta FROM orrery_resolutions WHERE id = :id"),
        {"id": entry_resolution_id},
    ).scalar_one()["project.start"]["applied"]
    assert applied["target_faction_entity_id"] == faction_id


def test_live_faction_rebinding_raises_loudly(
    faction_context_db: dict[str, Any],
) -> None:
    db = faction_context_db
    actor_id = int(db["actors"]["bound"])
    faction_id, other_faction_id = sorted(db["factions"])
    entry = resolve_dry_run(
        db["session"],
        (START_FACTION_PROJECT,),
        anchor_chunk_id=int(db["chunk_id"]),
        window_chunks=30,
        project_settings=POLICY,
    )
    draft = next(
        item
        for item in _actor_drafts(entry, actor_id, START_FACTION_PROJECT.id)
        if item.bindings["faction"] == faction_id
    )
    _accepted_draft(db, draft)

    with (
        db["raw_connection"].cursor() as cur,
        pytest.raises(ValueError, match="immutable"),
    ):
        _apply_project_advance_sync(
            cur,
            actor_entity_id=actor_id,
            payload={"target_faction_entity_id": other_faction_id},
            source_chunk_id=int(db["chunk_id"]),
            policy=POLICY,
        )

    with db["raw_connection"].cursor() as cur:
        cur.execute("SAVEPOINT faction_rebinding_trigger")
        with pytest.raises(psycopg2.errors.RaiseException, match="immutable"):
            cur.execute(
                """
                UPDATE character_project_states
                SET target_faction_entity_id = %s
                WHERE character_entity_id = %s
                  AND status IN ('active', 'paused', 'stalled')
                """,
                (other_faction_id, actor_id),
            )
        cur.execute("ROLLBACK TO SAVEPOINT faction_rebinding_trigger")

    comment = (
        db["session"]
        .execute(
            text(
                """
            SELECT col_description(
                'character_project_states'::regclass,
                attnum
            )
            FROM pg_attribute
            WHERE attrelid = 'character_project_states'::regclass
              AND attname = 'target_faction_entity_id'
            """
            )
        )
        .scalar_one()
    )
    assert comment == (
        "The institutional counterparty bound at project entry; NULL for "
        "projects whose template declares no faction slot; immutable once set."
    )


def test_live_target_faction_product_is_bounded_and_deterministic(
    faction_context_db: dict[str, Any],
) -> None:
    db = faction_context_db
    session = db["session"]
    chunk_id = int(db["chunk_id"])
    actor_id = int(db["actors"]["bound"])
    targets = tuple(
        sorted(
            (
                int(db["actors"]["target_a"]),
                int(db["actors"]["target_b"]),
            )
        )
    )
    factions = tuple(sorted(int(value) for value in db["factions"]))

    bindings = compose_actor_target_faction_bindings(
        session,
        anchor_chunk_id=chunk_id,
        window_chunks=30,
        actor_ids={actor_id},
    )
    assert bindings == tuple(
        {
            Slot.ACTOR: actor_id,
            Slot.TARGET: target_id,
            Slot.FACTION: faction_id,
        }
        for target_id in targets
        for faction_id in factions
    )

    kwargs = {
        "anchor_chunk_id": chunk_id,
        "window_chunks": 30,
        "fanout_settings": {"max_pair_drafts_per_actor": 2},
    }
    first = resolve_dry_run(session, (TRIPLE_TEMPLATE,), **kwargs)
    second = resolve_dry_run(session, (TRIPLE_TEMPLATE,), **kwargs)
    first_bindings = [
        draft.bindings for draft in _actor_drafts(first, actor_id, TRIPLE_TEMPLATE.id)
    ]
    second_bindings = [
        draft.bindings for draft in _actor_drafts(second, actor_id, TRIPLE_TEMPLATE.id)
    ]
    assert len(first_bindings) == 2
    assert second_bindings == first_bindings


def test_live_production_and_explain_compose_same_faction_bindings(
    faction_context_db: dict[str, Any],
) -> None:
    db = faction_context_db
    session = db["session"]
    chunk_id = int(db["chunk_id"])
    actor_id = int(db["actors"]["bound"])

    production = resolve_dry_run(
        session,
        (START_FACTION_PROJECT,),
        anchor_chunk_id=chunk_id,
        window_chunks=30,
        project_settings=POLICY,
    )
    explained = explain_dry_run(
        session,
        (START_FACTION_PROJECT,),
        anchor_chunk_id=chunk_id,
        window_chunks=30,
        project_settings=POLICY,
    )
    production_bindings = {
        tuple(sorted(draft.bindings.items()))
        for draft in _actor_drafts(production, actor_id, START_FACTION_PROJECT.id)
    }
    actor_group = next(
        group for group in explained.actors if group.actor_entity_id == actor_id
    )
    explained_bindings = {
        tuple(sorted(stack.bindings.items())) for stack in actor_group.two_party_stacks
    }

    assert explained_bindings == production_bindings
