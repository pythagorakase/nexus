"""Rollback-only live coverage for ruled Orrery composition sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.audit import explain_dry_run
from nexus.agents.orrery.resolver import (
    compose_actor_faction_bindings,
    compose_actor_faction_routes,
    compose_actor_target_bindings,
    compose_actor_target_routes,
    hydrate_world_state,
    resolve_dry_run,
)
from nexus.agents.orrery.substrate import (
    ALWAYS,
    Branch,
    DriveBand,
    ProjectPolicy,
    RoutineAnchor,
    Slot,
    Template,
    TravelState,
    WorldState,
    evaluate,
)
from nexus.agents.orrery.templates import START_SEEK_REDEMPTION
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres

LIVE_SLOT = 5
COMPOSITION = {
    "hostile_source_enabled": True,
    "roster_source_enabled": True,
    "roster_reach": 2,
}
HOSTILE_TEMPLATE = Template(
    id="live_hostile_composition",
    priority=10,
    drive_band=DriveBand.PROJECT_IDENTITY,
    blurb="Live hostile composition fixture.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    package_gate=ALWAYS,
    branches=(Branch("act", ALWAYS, "{actor} faces {target}."),),
    composes_from_hostility=True,
)
HOSTILE_LEGACY_TEMPLATE = Template(
    id="live_hostile_legacy",
    priority=9,
    drive_band=DriveBand.PROJECT_IDENTITY,
    blurb="Live relationship-only fixture.",
    required_slots=(Slot.ACTOR, Slot.TARGET),
    package_gate=ALWAYS,
    branches=(Branch("act", ALWAYS, "{actor} ignores {target}."),),
)
ROSTER_TEMPLATE = Template(
    id="live_roster_composition",
    priority=10,
    drive_band=DriveBand.PROJECT_IDENTITY,
    blurb="Live roster composition fixture.",
    required_slots=(Slot.ACTOR, Slot.FACTION),
    package_gate=ALWAYS,
    branches=(Branch("act", ALWAYS, "{actor} courts {faction}."),),
    courts_factions=True,
)
ROSTER_LEGACY_TEMPLATE = Template(
    id="live_roster_legacy",
    priority=9,
    drive_band=DriveBand.PROJECT_IDENTITY,
    blurb="Live direct-institution-only fixture.",
    required_slots=(Slot.ACTOR, Slot.FACTION),
    package_gate=ALWAYS,
    branches=(Branch("act", ALWAYS, "{actor} avoids {faction}."),),
)


def _insert_relationship(
    session: Session, source_character_id: int, target_character_id: int
) -> None:
    session.execute(
        text(
            """
            INSERT INTO character_relationships (
                character1_id, character2_id, relationship_type,
                emotional_valence, dynamic, recent_events, history
            ) VALUES (
                :source_id, :target_id, 'associate', '+1|favorable',
                'Rollback-only composition fixture.',
                'No persistent events.',
                'Created solely for issue 532 live coverage.'
            )
            """
        ),
        {"source_id": source_character_id, "target_id": target_character_id},
    )


def _insert_pair_tag(
    session: Session, subject_id: int, object_id: int, tag: str
) -> None:
    session.execute(
        text(
            """
            INSERT INTO entity_pair_tags (
                subject_entity_id, object_entity_id, pair_tag_id,
                source_kind, template_id
            )
            SELECT :subject_id, :object_id, pt.id,
                   'template', 'test_composition_sources_live'
            FROM pair_tags pt
            WHERE pt.tag = :tag AND NOT pt.deprecated
            """
        ),
        {"subject_id": subject_id, "object_id": object_id, "tag": tag},
    )


@pytest.fixture()
def composition_db() -> Iterator[dict[str, Any]]:
    """Create a private hostile edge and roster graph, then roll it back."""

    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        token = uuid4().hex[:12]
        place_id = int(
            session.execute(
                text("SELECT id FROM places ORDER BY id LIMIT 1")
            ).scalar_one()
        )
        entities: dict[str, int] = {}
        characters: dict[str, int] = {}
        for label in (
            "actor",
            "hostile_target",
            "near_member",
            "far_member",
            "beyond_member",
            "unreachable_member",
        ):
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
                        "name": f"composition-{token}-{label}",
                        "entity_id": entity_id,
                    },
                ).scalar_one()
            )
            entities[label] = entity_id
            characters[label] = character_id

        factions: dict[str, int] = {}
        for label in ("near", "far", "beyond", "unreachable", "no_roster"):
            factions[label] = int(
                session.execute(
                    text(
                        """
                        INSERT INTO entities (kind, is_active)
                        VALUES ('faction', true)
                        RETURNING id
                        """
                    )
                ).scalar_one()
            )

        session.execute(
            text(
                """
                INSERT INTO character_routine_anchors (
                    character_entity_id, anchor_type, place_id,
                    mobility_policy, source
                ) VALUES (
                    :actor_id, 'home', :place_id, 'fixed_place',
                    'test_composition_sources_live'
                )
                """
            ),
            {"actor_id": entities["actor"], "place_id": place_id},
        )
        _insert_relationship(session, characters["actor"], characters["near_member"])
        _insert_relationship(
            session, characters["near_member"], characters["far_member"]
        )
        _insert_relationship(
            session, characters["far_member"], characters["beyond_member"]
        )
        _insert_pair_tag(
            session,
            entities["hostile_target"],
            entities["actor"],
            "hostile_to",
        )
        _insert_pair_tag(session, factions["near"], entities["actor"], "hostile_to")
        _insert_pair_tag(
            session, entities["near_member"], factions["near"], "status:junior"
        )
        _insert_pair_tag(
            session, entities["far_member"], factions["far"], "status:senior"
        )
        _insert_pair_tag(
            session,
            entities["beyond_member"],
            factions["beyond"],
            "status:senior",
        )
        _insert_pair_tag(
            session,
            entities["unreachable_member"],
            factions["unreachable"],
            "status:junior",
        )
        yield {
            "session": session,
            "entities": entities,
            "factions": factions,
            "place_id": place_id,
        }
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_live_hostile_pair_is_symmetric_isolated_and_fires_redemption(
    composition_db: dict[str, Any],
) -> None:
    """A hostile-only pair composes both ways, but only opted stacks see it."""

    session = composition_db["session"]
    entities = composition_db["entities"]
    actor = entities["actor"]
    target = entities["hostile_target"]
    bindings = compose_actor_target_bindings(
        session,
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids={actor, target},
        include_hostile_edges=True,
    )
    observed_pairs = {
        (binding[Slot.ACTOR], binding[Slot.TARGET]) for binding in bindings
    }
    assert {(actor, target), (target, actor)} <= observed_pairs
    assert not any(
        composition_db["factions"]["near"] in pair for pair in observed_pairs
    )

    routes = compose_actor_target_routes(
        session,
        state=WorldState(),
        templates=(HOSTILE_LEGACY_TEMPLATE, HOSTILE_TEMPLATE),
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids={actor},
        composition_settings=COMPOSITION,
    )
    routed_bindings, routed_templates = next(
        route for route in routes if route[0][Slot.TARGET] == target
    )
    assert routed_bindings == {Slot.ACTOR: actor, Slot.TARGET: target}
    assert routed_templates == (HOSTILE_TEMPLATE,)

    redemption_routes = compose_actor_target_routes(
        session,
        state=WorldState(),
        templates=(START_SEEK_REDEMPTION,),
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids={actor},
        composition_settings=COMPOSITION,
    )
    redemption_bindings, redemption_templates = next(
        route for route in redemption_routes if route[0][Slot.TARGET] == target
    )
    state = WorldState(
        locations={actor: composition_db["place_id"]},
        pair_tags={(target, actor): frozenset({"hostile_to"})},
        travel_states={actor: TravelState(status="at_place")},
        project_policy=ProjectPolicy(enabled=True),
        routine_anchors={
            (actor, "home"): RoutineAnchor(
                anchor_type="home",
                place_id=composition_db["place_id"],
                mobility_policy="fixed_place",
            )
        },
        world_time=datetime(2073, 8, 2, 12, tzinfo=timezone.utc),
    )
    assert redemption_templates == (START_SEEK_REDEMPTION,)
    assert evaluate(START_SEEK_REDEMPTION, state, redemption_bindings).passes


def test_live_roster_source_respects_reach_roster_liveness_and_opt_in(
    composition_db: dict[str, Any],
) -> None:
    """Only live rosters reachable within the configured neutral orbit compose."""

    session = composition_db["session"]
    actor = composition_db["entities"]["actor"]
    factions = composition_db["factions"]
    state = hydrate_world_state(
        session,
        anchor_chunk_id=None,
        window_chunks=30,
    )
    at_one = compose_actor_faction_bindings(
        session,
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids={actor},
        include_rosters=True,
        roster_reach=1,
        orbit_distance=state.orbit_distance,
    )
    at_two = compose_actor_faction_bindings(
        session,
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids={actor},
        include_rosters=True,
        roster_reach=2,
        orbit_distance=state.orbit_distance,
    )
    assert {binding[Slot.FACTION] for binding in at_one} == {factions["near"]}
    assert {binding[Slot.FACTION] for binding in at_two} == {
        factions["near"],
        factions["far"],
    }
    assert factions["unreachable"] not in {binding[Slot.FACTION] for binding in at_two}
    assert factions["beyond"] not in {binding[Slot.FACTION] for binding in at_two}
    assert factions["no_roster"] not in {binding[Slot.FACTION] for binding in at_two}

    routes = compose_actor_faction_routes(
        session,
        state=state,
        templates=(ROSTER_LEGACY_TEMPLATE, ROSTER_TEMPLATE),
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids={actor},
        composition_settings=COMPOSITION,
    )
    assert {
        (
            route[0][Slot.FACTION],
            tuple(template.id for template in route[1]),
        )
        for route in routes
    } == {
        (factions["near"], (ROSTER_TEMPLATE.id,)),
        (factions["far"], (ROSTER_TEMPLATE.id,)),
    }


def test_live_widened_sources_keep_resolver_and_audit_in_parity(
    composition_db: dict[str, Any],
) -> None:
    """Both real-schema dry-run dispatch sites see identical widened bindings."""

    session = composition_db["session"]
    actor = composition_db["entities"]["actor"]
    target = composition_db["entities"]["hostile_target"]
    factions = composition_db["factions"]
    templates = (HOSTILE_TEMPLATE, ROSTER_TEMPLATE)
    kwargs = {
        "anchor_chunk_id": None,
        "window_chunks": 30,
        "composition_settings": COMPOSITION,
    }
    proposal = resolve_dry_run(session, templates, **kwargs)
    report = explain_dry_run(session, templates, **kwargs)

    production = {
        (draft.template_id, tuple(sorted(draft.bindings.items())))
        for draft in proposal.resolutions
        if draft.bindings.get("actor") == actor
    }
    actor_report = next(item for item in report.actors if item.actor_entity_id == actor)
    audited = {
        (stack.winner_id, tuple(sorted(stack.bindings.items())))
        for stack in actor_report.two_party_stacks
    }
    widened_expected = {
        (HOSTILE_TEMPLATE.id, (("actor", actor), ("target", target))),
        *{
            (
                ROSTER_TEMPLATE.id,
                (("actor", actor), ("faction", faction_id)),
            )
            for faction_id in (factions["near"], factions["far"])
        },
    }
    assert widened_expected <= production
    assert audited == production
