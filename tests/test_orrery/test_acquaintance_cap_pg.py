"""Real acquaintance composition on disposable clones, with rolled-back sessions.

Uses layers, zones, places, entities, characters, the story clock/need tables,
relationships, and pair tags from the template; never opens an owner database.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from nexus.agents.orrery.resolver import (
    compose_acquaintance_bindings,
    compose_actor_target_routes,
)
from nexus.agents.orrery.substrate import Bindings, Slot, Template, WorldState
from nexus.agents.orrery.templates import MAKE_ACQUAINTANCE
from nexus.config import load_settings
from nexus.config.settings_models import OrreryCompositionSettings
from tests.pg_fixtures import (
    disposable_slot_database,
    seed_character,
    seed_place,
    seed_story_clock,
    seed_zone,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres
CAP = "acquaintance_introductions_per_entity_per_tick"
Fixture = tuple[Session, tuple[int, ...]]


@contextmanager
def _seeded_characters(count: int) -> Iterator[tuple[str, tuple[int, ...]]]:
    with disposable_slot_database("qa640_788s7_acquaintance") as dbname:
        seed_zone(
            dbname,
            name="Acquaintance Zone",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        place_id, _ = seed_place(dbname, name="Acquaintance Hall")
        seed_story_clock(
            dbname, world_time=datetime(2073, 8, 1, 12, tzinfo=timezone.utc)
        )
        entities = tuple(
            seed_character(
                dbname, name=f"acquaintance-{index}", current_location=place_id
            )[1]
            for index in range(count)
        )
        assert list(entities) == sorted(set(entities))
        yield dbname, entities


@pytest.fixture(scope="module")
def three_character_clone() -> Iterator[tuple[str, tuple[int, ...]]]:
    """Seed three active co-located strangers under the TEST story pin."""
    with _seeded_characters(3) as clone:
        yield clone


@pytest.fixture(scope="module")
def four_character_clone() -> Iterator[tuple[str, tuple[int, ...]]]:
    """Seed a separate four-character clone for endpoint saturation checks."""
    with _seeded_characters(4) as clone:
        yield clone


@contextmanager
def _rolled_back_session(clone: tuple[str, tuple[int, ...]]) -> Iterator[Fixture]:
    dbname, entities = clone
    engine = create_engine(sqlalchemy_url(dbname), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session, entities
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def acquaintance_db(
    three_character_clone: tuple[str, tuple[int, ...]],
) -> Iterator[Fixture]:
    """Roll back each test's session over the three-character clone."""
    with _rolled_back_session(three_character_clone) as fixture:
        yield fixture


@pytest.fixture
def four_character_db(
    four_character_clone: tuple[str, tuple[int, ...]],
) -> Iterator[Fixture]:
    """Roll back each test's session over the four-character clone."""
    with _rolled_back_session(four_character_clone) as fixture:
        yield fixture


def _shipped_mapping() -> dict[str, Any]:
    orrery = load_settings("nexus.toml").orrery
    assert orrery is not None
    return orrery.model_dump()["composition"]


def _routes(
    db: Fixture, settings: Any
) -> tuple[tuple[Bindings, tuple[Template, ...]], ...]:
    session, entities = db
    return compose_actor_target_routes(
        session,
        state=WorldState(),
        templates=(MAKE_ACQUAINTANCE,),
        anchor_chunk_id=None,
        window_chunks=30,
        actor_ids=entities,
        composition_settings=settings,
    )


def _bindings(*pairs: tuple[int, int]) -> tuple[Bindings, ...]:
    return tuple({Slot.ACTOR: actor, Slot.TARGET: target} for actor, target in pairs)


def _expected_routes(
    *pairs: tuple[int, int]
) -> tuple[tuple[Bindings, tuple[Template, ...]], ...]:
    return tuple((binding, (MAKE_ACQUAINTANCE,)) for binding in _bindings(*pairs))


def _direct(
    db: Fixture, cap: int, actors: set[int] | None = None
) -> tuple[Bindings, ...]:
    session, entities = db
    return compose_acquaintance_bindings(
        session,
        anchor_chunk_id=None,
        actor_ids=entities if actors is None else actors,
        introductions_per_entity=cap,
    )


def test_shipped_default_composes_todays_pairs(acquaintance_db: Fixture) -> None:
    """The shipped cap and repeated calls preserve the existing first pair."""
    _, (e1, e2, e3) = acquaintance_db
    settings = _shipped_mapping()
    assert settings[CAP] == 1
    assert _routes(acquaintance_db, settings) == _expected_routes((e1, e2))
    assert _direct(acquaintance_db, 1) == _bindings((e1, e2))
    assert _direct(acquaintance_db, 1) == _bindings((e1, e2))


def test_cap_of_two_introduces_each_entity_twice(acquaintance_db: Fixture) -> None:
    """The settings reader and route caller pass the configured cap through."""
    _, (e1, e2, e3) = acquaintance_db
    settings = _shipped_mapping()
    settings[CAP] = 2
    routes = _routes(acquaintance_db, settings)
    assert routes == _expected_routes((e1, e2), (e1, e3), (e2, e3))
    assert Counter(entity for binding, _ in routes for entity in binding.values()) == {
        e1: 2,
        e2: 2,
        e3: 2,
    }


def test_cap_of_two_rejects_pairs_after_either_endpoint_is_full(
    four_character_db: Fixture,
) -> None:
    """Both endpoints count, including when the hydrated actor is higher-ID."""
    _, (e1, e2, e3, e4) = four_character_db
    settings = _shipped_mapping()
    settings[CAP] = 2
    routes = _routes(four_character_db, settings)
    expected = ((e1, e2), (e1, e3), (e2, e3))
    assert routes == _expected_routes(*expected)
    assert _direct(four_character_db, 2) == _bindings(*expected)
    counts = Counter(entity for binding, _ in routes for entity in binding.values())
    assert {entity: counts[entity] for entity in (e1, e2, e3, e4)} == {
        e1: 2,
        e2: 2,
        e3: 2,
        e4: 0,
    }
    assert _direct(four_character_db, 2, {e2, e3, e4}) == _bindings(
        (e2, e1), (e3, e1), (e2, e3)
    )
    assert _direct(four_character_db, 2, {e4}) == _bindings((e4, e1), (e4, e2))


def test_cap_counts_targets_and_preserves_hydrated_actor_orientation(
    acquaintance_db: Fixture,
) -> None:
    """Unhydrated targets consume the same cap as hydrated actors."""
    _, (e1, e2, e3) = acquaintance_db
    assert _direct(acquaintance_db, 1, {e2, e3}) == _bindings((e2, e1))
    assert _direct(acquaintance_db, 2, {e2, e3}) == _bindings(
        (e2, e1), (e3, e1), (e2, e3)
    )


def test_omitted_cap_and_typed_settings_use_the_model_default(
    acquaintance_db: Fixture,
) -> None:
    """Legacy partial mappings and typed composition settings share a default."""
    _, (e1, e2, e3) = acquaintance_db
    partial = {"acquaintance_source_enabled": True}
    for settings in (partial, OrreryCompositionSettings.model_validate(partial)):
        assert _routes(acquaintance_db, settings) == _expected_routes((e1, e2))


def test_nonpositive_cap_fails_before_composition(acquaintance_db: Fixture) -> None:
    """Invalid caps raise through both real paths, never suppressing pairs."""
    session, _ = acquaintance_db
    for invalid in (0, -1):
        # Real session with autobegin disabled: any query would raise.
        with Session(bind=session.get_bind(), autobegin=False) as no_query_session:
            with pytest.raises(
                ValueError, match="^introductions_per_entity must be at least 1$"
            ):
                _direct((no_query_session, acquaintance_db[1]), invalid)
        settings = _shipped_mapping()
        settings[CAP] = invalid
        with pytest.raises(ValidationError, match=CAP):
            _routes(acquaintance_db, settings)
