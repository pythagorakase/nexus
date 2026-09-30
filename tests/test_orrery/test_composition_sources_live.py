"""Rollback-only live coverage for ruled Orrery composition sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.audit import explain_dry_run
from nexus.agents.orrery.events import commit_orrery_tick_sync
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
from nexus.agents.orrery.templates import (
    MAKE_ACQUAINTANCE,
    START_PURSUE_ROMANCE,
    START_RECRUIT_ALLY,
    START_SEEK_REDEMPTION,
)
from tests.pg_fixtures import (
    disposable_slot_database,
    seed_character,
    seed_faction,
    seed_pair_tag,
    seed_place,
    seed_relationship,
    seed_routine_anchor,
    seed_story_clock,
    seed_zone,
    sqlalchemy_url,
)


pytestmark = [pytest.mark.requires_postgres, pytest.mark.live_llm]

STORY_WORLD_TIME = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)
COMPOSITION = {
    "acquaintance_source_enabled": True,
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


def _insert_pair_tag(
    session: Session, subject_id: int, object_id: int, tag: str
) -> None:
    """Add one in-transaction pair tag; a missing vocabulary tag fails."""

    row = session.execute(
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
            RETURNING id
            """
        ),
        {"subject_id": subject_id, "object_id": object_id, "tag": tag},
    ).one_or_none()
    assert row is not None, f"pair tag {tag!r} is not seeded"


@pytest.fixture(scope="module")
def composition_clone() -> Iterator[dict[str, Any]]:
    """Own one clone seeded with a private hostile edge and roster graph.

    The actor is anchored at home in the first of two places and nobody is
    located anywhere, so both places are empty until a test moves a pair.
    Associate edges chain actor, near, far, and beyond members; each member
    holds a status in its own faction, and the unreachable member's faction
    has no path from the actor. The story clock gives the acquaintance commit
    its tick chunk and every need row its anchor.
    """

    with disposable_slot_database("qa885_composition_sources") as dbname:
        seed_zone(
            dbname,
            name="Composition Zone",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        places = tuple(
            seed_place(dbname, name=name, longitude=longitude)[0]
            for name, longitude in (
                ("Composition Hall", -73.9857),
                ("Composition Yard", -73.9601),
            )
        )
        chunk_id = seed_story_clock(dbname, world_time=STORY_WORLD_TIME)
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
            characters[label], entities[label] = seed_character(
                dbname, name=f"composition-{label}"
            )

        factions = {
            label: seed_faction(dbname, name=f"Composition {label}")[1]
            for label in ("near", "far", "beyond", "unreachable", "no_roster")
        }

        seed_routine_anchor(
            dbname,
            character_entity_id=entities["actor"],
            place_id=places[0],
            source="test_composition_sources_live",
        )
        for source_label, target_label in (
            ("actor", "near_member"),
            ("near_member", "far_member"),
            ("far_member", "beyond_member"),
        ):
            seed_relationship(
                dbname,
                subject_character_id=characters[source_label],
                object_character_id=characters[target_label],
                relationship_type="associate",
                emotional_valence="+1|favorable",
                dynamic="Composition fixture.",
                recent_events="No persistent events.",
                history="Created solely for issue 532 live coverage.",
            )
        for subject_id, object_id, tag in (
            (entities["hostile_target"], entities["actor"], "hostile_to"),
            (factions["near"], entities["actor"], "hostile_to"),
            (entities["near_member"], factions["near"], "status:junior"),
            (entities["far_member"], factions["far"], "status:senior"),
            (entities["beyond_member"], factions["beyond"], "status:senior"),
            (
                entities["unreachable_member"],
                factions["unreachable"],
                "status:junior",
            ),
        ):
            seed_pair_tag(
                dbname,
                subject_entity_id=subject_id,
                object_entity_id=object_id,
                tag=tag,
                template_id="test_composition_sources_live",
            )
        yield {
            "dbname": dbname,
            "entities": entities,
            "factions": factions,
            "places": places,
            "chunk_id": chunk_id,
        }


@pytest.fixture()
def composition_db(
    composition_clone: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Open one rolled-back transaction over the seeded composition clone."""

    engine = create_engine(sqlalchemy_url(composition_clone["dbname"]), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield {
            "session": session,
            "entities": composition_clone["entities"],
            "factions": composition_clone["factions"],
            "place_id": composition_clone["places"][0],
            "places": composition_clone["places"],
            "chunk_id": composition_clone["chunk_id"],
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


def test_live_acquaintance_writes_mutual_contact_and_feeds_next_tick(
    composition_db: dict[str, Any],
) -> None:
    """One same-place introduction becomes a mutual social source next tick."""

    session = composition_db["session"]
    actor = composition_db["entities"]["actor"]
    stranger = composition_db["entities"]["far_member"]
    empty_place = session.execute(
        text(
            """
            SELECT p.id
            FROM places p
            LEFT JOIN characters c ON c.current_location = p.id
            GROUP BY p.id
            HAVING count(c.id) = 0
            ORDER BY p.id
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    assert empty_place is not None, "the clone seeds two places nobody occupies"
    session.execute(
        text(
            """
            UPDATE characters
            SET current_location = :place_id
            WHERE entity_id IN (:actor, :stranger)
            """
        ),
        {"place_id": int(empty_place), "actor": actor, "stranger": stranger},
    )
    session.flush()
    kwargs = {
        "anchor_chunk_id": None,
        "window_chunks": 30,
        "composition_settings": COMPOSITION,
    }
    proposal = resolve_dry_run(session, (MAKE_ACQUAINTANCE,), **kwargs)
    report = explain_dry_run(session, (MAKE_ACQUAINTANCE,), **kwargs)
    expected_bindings = {"actor": min(actor, stranger), "target": max(actor, stranger)}
    drafts = [
        draft
        for draft in proposal.resolutions
        if draft.template_id == MAKE_ACQUAINTANCE.id
        and draft.bindings == expected_bindings
    ]
    assert len(drafts) == 1
    audited = {
        (stack.winner_id, tuple(sorted(stack.bindings.items())))
        for actor_report in report.actors
        for stack in actor_report.two_party_stacks
    }
    assert (
        MAKE_ACQUAINTANCE.id,
        tuple(sorted(expected_bindings.items())),
    ) in audited

    raw = session.connection().connection.driver_connection
    tick_chunk_id = int(composition_db["chunk_id"])
    result = commit_orrery_tick_sync(
        raw,
        proposal,
        tick_chunk_id=tick_chunk_id,
    )
    assert result.tag_mutation_count >= 2
    session.expire_all()
    rows = session.execute(
        text(
            """
            SELECT ept.subject_entity_id, ept.object_entity_id, pt.tag
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            WHERE ept.cleared_at IS NULL
              AND pt.tag = 'contact:social'
              AND ept.subject_entity_id IN (:actor, :stranger)
              AND ept.object_entity_id IN (:actor, :stranger)
            ORDER BY ept.subject_entity_id, ept.object_entity_id
            """
        ),
        {"actor": actor, "stranger": stranger},
    ).all()
    assert rows == [
        (min(actor, stranger), max(actor, stranger), "contact:social"),
        (max(actor, stranger), min(actor, stranger), "contact:social"),
    ]
    assert (
        session.execute(
            text(
                """
            SELECT count(*)
            FROM world_events we
            WHERE we.tick_chunk_id = :tick_chunk_id
              AND we.event_type = 'contact_made'
              AND we.actor_entity_id = :actor
              AND we.target_entity_id = :target
            """
            ),
            {**expected_bindings, "tick_chunk_id": tick_chunk_id},
        ).scalar_one()
        == 1
    )

    next_tick_routes = compose_actor_target_routes(
        session,
        state=WorldState(),
        templates=(START_RECRUIT_ALLY, START_PURSUE_ROMANCE),
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids={expected_bindings["actor"]},
        composition_settings=COMPOSITION,
    )
    routed = next(
        route
        for route in next_tick_routes
        if route[0]
        == {
            Slot.ACTOR: expected_bindings["actor"],
            Slot.TARGET: expected_bindings["target"],
        }
    )
    assert routed[1] == (START_RECRUIT_ALLY, START_PURSUE_ROMANCE)


@pytest.mark.parametrize(
    "rebuff",
    ("relationship", "contact", "hostile", "different_place"),
)
def test_live_acquaintance_rebuffs_prior_ties_and_separation(
    composition_db: dict[str, Any],
    rebuff: str,
) -> None:
    """Every ruled exclusion blocks the specific live-schema pair."""

    session = composition_db["session"]
    actor = composition_db["entities"]["actor"]
    if rebuff == "relationship":
        target = composition_db["entities"]["near_member"]
    elif rebuff == "hostile":
        target = composition_db["entities"]["hostile_target"]
    else:
        target = composition_db["entities"]["far_member"]
    place_ids = [
        int(value)
        for value in session.execute(
            text("SELECT id FROM places ORDER BY id")
        ).scalars()
    ]
    assert place_ids == sorted(composition_db["places"]), (
        "the clone must hold exactly the two seeded places, " f"found {place_ids!r}"
    )
    actor_place = place_ids[0]
    target_place = place_ids[1] if rebuff == "different_place" else actor_place
    session.execute(
        text(
            """
            UPDATE characters
            SET current_location = CASE
                WHEN entity_id = :actor THEN :actor_place
                ELSE :target_place
            END
            WHERE entity_id IN (:actor, :target)
            """
        ),
        {
            "actor": actor,
            "target": target,
            "actor_place": actor_place,
            "target_place": target_place,
        },
    )
    if rebuff == "contact":
        _insert_pair_tag(session, target, actor, "contact:social")
    session.flush()
    proposal = resolve_dry_run(
        session,
        (MAKE_ACQUAINTANCE,),
        anchor_chunk_id=None,
        window_chunks=30,
        composition_settings=COMPOSITION,
    )
    canonical = {"actor": min(actor, target), "target": max(actor, target)}
    assert not any(
        draft.template_id == MAKE_ACQUAINTANCE.id and draft.bindings == canonical
        for draft in proposal.resolutions
    )
