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
        session.execute(
            text(
                """
                INSERT INTO characters (name, entity_id)
                VALUES (:actor_name, :actor), (:member_name, :member)
                """
            ),
            {
                "actor_name": f"patron-circle-{token}-actor",
                "actor": actor,
                "member_name": f"patron-circle-{token}-member",
                "member": member,
            },
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


def _apply(db: dict[str, Any], draft: OrreryResolutionDraft) -> None:
    with db["raw"].cursor() as cur:
        resolution_id = _insert_resolution_sync(
            cur,
            draft,
            tick_chunk_id=db["chunk"],
            actor_entity_id=db["actor"],
            brief=draft.narrative_stub,
        )
        assert resolution_id is not None
        _apply_state_delta_sync(
            cur,
            draft,
            resolution_id=resolution_id,
            actor_entity_id=db["actor"],
            target_entity_id=None,
            source_chunk_id=db["chunk"],
            need_tuning=load_need_tuning(),
            project_policy=POLICY,
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

    base = OrreryResolutionDraft(
        template_id="start_court_patron_faction",
        priority=17,
        binding_hash="faction-start",
        bindings={"actor": actor, "faction": faction},
        branch_label="Begin seeking the faction's notice",
        narrative_stub="The actor courts the faction.",
        state_delta={
            "project.start": {
                "project_type": "court_patron",
                "stage": "gaining_notice",
                "milestone": True,
            }
        },
        magnitude=0.4,
    )
    _apply(db, base)
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
    _apply(
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
            "status:junior",
            "advance_court_patron_faction",
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
