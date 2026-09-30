"""Rollback-only live proof of faction COURT_PATRON's composition circle."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine
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
from tests.pg_fixtures import (
    disposable_slot_database,
    seed_character,
    seed_faction,
    seed_pair_tag,
    seed_place,
    seed_protagonist,
    seed_relationship,
    seed_routine_anchor,
    seed_story_clock,
    seed_zone,
    sqlalchemy_url,
)


pytestmark = pytest.mark.requires_postgres
STORY_WORLD_TIME = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)
POLICY = ProjectPolicy(enabled=True, advance_interval_hours=24.0)


@pytest.fixture(scope="module")
def patron_circle_clone() -> Iterator[dict[str, Any]]:
    """Own one clone seeded with the patron circle: actor, member, faction.

    The actor lives at its home anchor; the member holds ``status:senior`` in
    the faction and is the actor's associate, which is the roster path into
    the institution. The protagonist gives the anchored dry run a canonical
    player. The story clock and every need anchor share one world time, so
    need debt is zero and the start gate's need clauses pass.
    """

    with disposable_slot_database("qa885_patron_circle") as dbname:
        seed_zone(
            dbname,
            name="Patron Circle Zone",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        place_id, _ = seed_place(dbname, name="Patron Circle Hall")
        seed_protagonist(
            dbname,
            current_location=place_id,
            base_timestamp=STORY_WORLD_TIME.isoformat(),
        )
        chunk = seed_story_clock(dbname, world_time=STORY_WORLD_TIME)
        actor_character, actor = seed_character(
            dbname, name="patron-circle-actor", current_location=place_id
        )
        member_character, member = seed_character(dbname, name="patron-circle-member")
        _, faction = seed_faction(dbname, name="Patron Circle Court")
        seed_relationship(
            dbname,
            subject_character_id=actor_character,
            object_character_id=member_character,
            relationship_type="associate",
            emotional_valence="+1|fixture",
            dynamic="The member can introduce the actor to the institution.",
            recent_events="No persistent events.",
            history="Created for the polymorphic patron live proof.",
        )
        seed_routine_anchor(
            dbname,
            character_entity_id=actor,
            place_id=place_id,
            source="test_polymorphic_patron_live",
        )
        seed_pair_tag(
            dbname,
            subject_entity_id=member,
            object_entity_id=faction,
            tag="status:senior",
            template_id="test_polymorphic_patron_live",
        )
        yield {
            "dbname": dbname,
            "actor": actor,
            "member": member,
            "faction": faction,
            "chunk": chunk,
        }


@pytest.fixture()
def patron_circle_db(
    patron_circle_clone: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Re-run 096 over the seeded clone inside one rolled-back transaction."""

    engine = create_engine(sqlalchemy_url(patron_circle_clone["dbname"]), future=True)
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
        yield {
            "session": session,
            "raw": raw,
            "actor": patron_circle_clone["actor"],
            "member": patron_circle_clone["member"],
            "faction": patron_circle_clone["faction"],
            "chunk": patron_circle_clone["chunk"],
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
        assert cur.rowcount == 1, f"pair tag status:{level} is not seeded"


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
