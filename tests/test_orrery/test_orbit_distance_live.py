"""Live PostgreSQL coverage for neutral narrative-orbit hydration.

Activated by ``NEXUS_RUN_POSTGRES=1``. The test owns a seeded template clone;
its fixture graph is created inside an external SQLAlchemy transaction and
always rolled back.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.relationship_provenance import (
    relationship_producer_sqlalchemy,
)
from nexus.agents.orrery.resolver import hydrate_world_state
from tests.pg_fixtures import disposable_slot_database, seed_story_clock, sqlalchemy_url


pytestmark = pytest.mark.requires_postgres

WORLD_TIME = datetime(2073, 8, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def orbit_slot() -> Iterator[str]:
    """Own a template clone whose story clock anchors character need clocks."""

    with disposable_slot_database("qa640_orbit_distance") as dbname:
        seed_story_clock(dbname, world_time=WORLD_TIME)
        yield dbname


def _insert_entity(session: Session, *, active: bool) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO entities (kind, is_active)
                VALUES ('character', :active)
                RETURNING id
                """
            ),
            {"active": active},
        ).scalar_one()
    )


def _insert_character(
    session: Session,
    *,
    entity_id: int,
    label: str,
    token: str,
) -> int:
    return int(
        session.execute(
            text(
                """
                INSERT INTO characters (name, entity_id)
                VALUES (:name, :entity_id)
                RETURNING id
                """
            ),
            {"name": f"orbit-live-{token}-{label}", "entity_id": entity_id},
        ).scalar_one()
    )


def _insert_relationship(
    session: Session,
    *,
    source_character_id: int,
    target_character_id: int,
    relationship_type: str,
    emotional_valence: str,
) -> None:
    # Migration 115 refuses relationship writes without a producer.
    relationship_producer_sqlalchemy(session, "manual")
    session.execute(
        text(
            """
            INSERT INTO character_relationships (
                character1_id,
                character2_id,
                relationship_type,
                emotional_valence,
                dynamic,
                recent_events,
                history
            ) VALUES (
                :source_character_id,
                :target_character_id,
                :relationship_type,
                :emotional_valence,
                'Rollback-only orbit-distance fixture.',
                'No persistent events.',
                'Created solely for PostgreSQL integration coverage.'
            )
            """
        ),
        {
            "source_character_id": source_character_id,
            "target_character_id": target_character_id,
            "relationship_type": relationship_type,
            "emotional_valence": emotional_valence,
        },
    )


def test_hydrate_orbit_distance_from_active_relationship_graph(
    orbit_slot: str,
) -> None:
    """Hydration treats current active-character relationships as neutral hops."""

    engine = create_engine(sqlalchemy_url(orbit_slot), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        token = uuid4().hex[:12]
        entity_ids = {
            label: _insert_entity(session, active=label != "inactive_bridge")
            for label in ("a", "b", "c", "d", "bare", "inactive_bridge")
        }
        character_ids = {
            label: _insert_character(
                session,
                entity_id=entity_ids[label],
                label=label,
                token=token,
            )
            for label in ("a", "b", "c", "d", "inactive_bridge")
        }

        # A -> B is maximally friendly. C -> B deliberately stores the second
        # edge in the reverse direction and with maximally hostile valence.
        # Both must still be one neutral, undirected hop.
        _insert_relationship(
            session,
            source_character_id=character_ids["a"],
            target_character_id=character_ids["b"],
            relationship_type="friend",
            emotional_valence="+5|devoted",
        )
        _insert_relationship(
            session,
            source_character_id=character_ids["c"],
            target_character_id=character_ids["b"],
            relationship_type="enemy",
            emotional_valence="-5|hateful",
        )

        # This apparent A-to-D route exists only through an inactive entity,
        # so neither edge may enter the active narrative-orbit graph.
        _insert_relationship(
            session,
            source_character_id=character_ids["a"],
            target_character_id=character_ids["inactive_bridge"],
            relationship_type="friend",
            emotional_valence="+5|devoted",
        )
        _insert_relationship(
            session,
            source_character_id=character_ids["inactive_bridge"],
            target_character_id=character_ids["d"],
            relationship_type="enemy",
            emotional_valence="-5|hateful",
        )

        state = hydrate_world_state(
            session,
            anchor_chunk_id=None,
            window_chunks=0,
            world_time_override=WORLD_TIME,
            epistemics_settings={"enabled": False},
        )

        a = entity_ids["a"]
        b = entity_ids["b"]
        c = entity_ids["c"]
        d = entity_ids["d"]
        bare = entity_ids["bare"]
        inactive_bridge = entity_ids["inactive_bridge"]
        fixture_entities = frozenset(entity_ids.values())
        observed = {
            pair: distance
            for pair, distance in state.orbit_distance.items()
            if pair[0] in fixture_entities or pair[1] in fixture_entities
        }

        assert observed == {
            (a, a): 0,
            (a, b): 1,
            (a, c): 2,
            (b, a): 1,
            (b, b): 0,
            (b, c): 1,
            (c, a): 2,
            (c, b): 1,
            (c, c): 0,
            (d, d): 0,
            (bare, bare): 0,
        }
        assert (a, d) not in state.orbit_distance
        assert (d, a) not in state.orbit_distance
        assert not any(inactive_bridge in pair for pair in state.orbit_distance)
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()
