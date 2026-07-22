"""Rollback-only live proof of faction COURT_PATRON's composition circle."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.events import (
    _apply_state_delta_sync,
    _insert_resolution_sync,
)
from nexus.agents.orrery.needs import load_need_tuning
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    compose_actor_faction_bindings,
    compose_actor_faction_routes,
    resolve_dry_run,
)
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    DriveBand,
    ProjectPolicy,
    Slot,
    Template,
    WorldState,
)
from nexus.agents.orrery.templates import START_COURT_PATRON_FACTION
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres
POLICY = ProjectPolicy(enabled=True, advance_interval_hours=24.0)


@pytest.fixture()
def patron_circle_db() -> Iterator[dict[str, Any]]:
    engine = create_engine(get_slot_db_url(slot=5), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    raw = connection.connection.driver_connection
    try:
        with raw.cursor() as cur:
            cur.execute(
                (
                    Path(__file__).parents[2] / "migrations/096_polymorphic_patron.sql"
                ).read_text()
            )
        token = uuid4().hex[:12]
        entity_ids = [
            int(value)
            for value in session.execute(
                text(
                    """
                    INSERT INTO entities (kind, is_active)
                    VALUES ('character', true), ('character', true),
                           ('faction', true)
                    RETURNING id
                    """
                )
            ).scalars()
        ]
        actor, member, faction = entity_ids
        place_id = int(
            session.execute(
                text("SELECT id FROM places ORDER BY id LIMIT 1")
            ).scalar_one()
        )
        session.execute(
            text(
                """
                INSERT INTO characters (name, entity_id, current_location)
                VALUES (:actor_name, :actor, :place_id),
                       (:member_name, :member, NULL)
                """
            ),
            {
                "actor_name": f"patron-circle-{token}-actor",
                "actor": actor,
                "member_name": f"patron-circle-{token}-member",
                "member": member,
                "place_id": place_id,
            },
        )
        character_ids = tuple(
            int(value)
            for value in session.execute(
                text(
                    """
                    SELECT id FROM characters
                    WHERE entity_id IN (:actor, :member)
                    ORDER BY entity_id
                    """
                ),
                {"actor": actor, "member": member},
            ).scalars()
        )
        actor_character, member_character = character_ids
        session.execute(
            text(
                """
                INSERT INTO character_relationships (
                    character1_id, character2_id, relationship_type,
                    emotional_valence, dynamic, recent_events, history
                ) VALUES (
                    :actor, :member, 'associate', '+1|fixture',
                    'The member can introduce the actor to the institution.',
                    'No persistent events.',
                    'Created for the polymorphic patron live proof.'
                )
                """
            ),
            {"actor": actor_character, "member": member_character},
        )
        session.execute(
            text(
                """
                INSERT INTO character_routine_anchors (
                    character_entity_id, anchor_type, place_id,
                    mobility_policy, source
                ) VALUES (
                    :actor, 'home', :place_id, 'fixed_place',
                    'test_polymorphic_patron_live'
                )
                """
            ),
            {"actor": actor, "place_id": place_id},
        )
        session.execute(
            text(
                """
                INSERT INTO entity_pair_tags (
                    subject_entity_id, object_entity_id, pair_tag_id,
                    source_kind, template_id
                )
                SELECT :member, :faction, pt.id, 'template',
                       'test_polymorphic_patron_live'
                FROM pair_tags pt
                WHERE pt.tag = 'status:senior' AND NOT pt.deprecated
                """
            ),
            {"member": member, "faction": faction},
        )
        chunk = int(
            session.execute(
                text(
                    """
                    SELECT chunk_id FROM chunk_metadata
                    WHERE world_time IS NOT NULL
                    ORDER BY chunk_id DESC LIMIT 1
                    """
                )
            ).scalar_one()
        )
        session.flush()
        yield {
            "session": session,
            "raw": raw,
            "actor": actor,
            "member": member,
            "faction": faction,
            "chunk": chunk,
        }
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def _apply(db: dict[str, Any], draft: OrreryResolutionDraft) -> int:
    with db["raw"].cursor() as cur:
        resolution_id = _insert_resolution_sync(
            cur,
            draft,
            tick_chunk_id=db["chunk"],
            actor_entity_id=db["actor"],
            brief=draft.narrative_stub,
        )
        assert resolution_id is not None
        return _apply_state_delta_sync(
            cur,
            draft,
            resolution_id=resolution_id,
            actor_entity_id=db["actor"],
            target_entity_id=None,
            source_chunk_id=db["chunk"],
            need_tuning=load_need_tuning(),
            project_policy=POLICY,
        )


def _seed_mid_project_status(db: dict[str, Any], level: str) -> None:
    with db["raw"].cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_pair_tags (
                subject_entity_id, object_entity_id, pair_tag_id,
                source_kind, source_chunk_id, template_id
            )
            SELECT %s, %s, pt.id, 'template', %s,
                   'test_mid_project_status_gain'
            FROM pair_tags pt
            WHERE pt.tag = %s AND NOT pt.deprecated
            """,
            (
                db["actor"],
                db["faction"],
                db["chunk"],
                f"status:{level}",
            ),
        )


def test_roster_start_to_status_completion_closes_institutional_circle(
    patron_circle_db: dict[str, Any],
) -> None:
    db = patron_circle_db
    actor = db["actor"]
    faction = db["faction"]
    roster_state = WorldState(orbit_distance={(actor, db["member"]): 1})
    roster_routes = compose_actor_faction_routes(
        db["session"],
        state=roster_state,
        templates=(START_COURT_PATRON_FACTION,),
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids={actor},
        composition_settings={
            "roster_source_enabled": True,
            "roster_reach": 2,
        },
    )
    assert any(
        route[0] == {Slot.ACTOR: actor, Slot.FACTION: faction}
        and route[1] == (START_COURT_PATRON_FACTION,)
        for route in roster_routes
    )

    proposal = resolve_dry_run(
        db["session"],
        (START_COURT_PATRON_FACTION,),
        anchor_chunk_id=db["chunk"],
        window_chunks=30,
        project_settings=POLICY,
        composition_settings={
            "roster_source_enabled": True,
            "roster_reach": 2,
        },
    )
    base = next(
        draft
        for draft in proposal.resolutions
        if draft.template_id == START_COURT_PATRON_FACTION.id
        and draft.bindings == {"actor": actor, "faction": faction}
    )
    assert base.state_delta["project.start"] == {
        "project_type": "court_patron",
        "stage": "gaining_notice",
        "milestone": True,
        "target_faction_entity_id": faction,
    }
    _apply(db, base)
    _seed_mid_project_status(db, "respected")
    _apply(
        db,
        replace(
            base,
            template_id="advance_court_patron_faction",
            binding_hash="faction-advance-one",
            state_delta={
                "project.advance": {
                    "stage": "proving_worth",
                    "set_progress": 0.0,
                    "milestone": True,
                }
            },
        ),
    )
    _apply(
        db,
        replace(
            base,
            template_id="advance_court_patron_faction",
            binding_hash="faction-advance-two",
            state_delta={
                "project.advance": {
                    "stage": "securing_favor",
                    "set_progress": 1.0,
                    "milestone": True,
                }
            },
        ),
    )
    completion_mutations = _apply(
        db,
        replace(
            base,
            template_id="advance_court_patron_faction",
            binding_hash="faction-complete",
            state_delta={
                "project.complete": {"milestone": True},
                "status.bestow": {"level": "junior"},
            },
        ),
    )
    assert completion_mutations == 0

    with db["raw"].cursor() as cur:
        cur.execute(
            """
            SELECT cps.status, cps.target_character_entity_id,
                   cps.target_faction_entity_id, pt.tag, ept.template_id
            FROM character_project_states cps
            JOIN entity_pair_tags ept
              ON ept.subject_entity_id = cps.character_entity_id
             AND ept.object_entity_id = cps.target_faction_entity_id
             AND ept.cleared_at IS NULL
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            WHERE cps.character_entity_id = %s
              AND pt.tag LIKE 'status:%%'
            """,
            (actor,),
        )
        assert cur.fetchone() == (
            "completed",
            None,
            faction,
            "status:respected",
            "test_mid_project_status_gain",
        )

    institutional = compose_actor_faction_bindings(
        db["session"],
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids={actor},
    )
    assert {Slot.ACTOR: actor, Slot.FACTION: faction} in institutional
    institutional_template = Template(
        id="institutional_circle_probe",
        priority=1,
        drive_band=DriveBand.PROJECT_IDENTITY,
        blurb="Institutional circle probe.",
        required_slots=(Slot.ACTOR, Slot.FACTION),
        package_gate=ALWAYS,
        branches=(Branch("act", ALWAYS, "{actor} works with {faction}."),),
    )
    routes = compose_actor_faction_routes(
        db["session"],
        state=WorldState(),
        templates=(institutional_template,),
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids={actor},
    )
    assert routes == (
        (
            {Slot.ACTOR: actor, Slot.FACTION: faction},
            (institutional_template,),
        ),
    )
