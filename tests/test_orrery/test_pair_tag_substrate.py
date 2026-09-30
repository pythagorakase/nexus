"""Real-DB integration tests for pair-tag WorldState hydration and predicates.

Exercises the Orrery Condition layer against a disposable template clone that
``pair_tag_slot`` owns for the module. Activated by ``NEXUS_RUN_POSTGRES=1``.
``test_entities`` creates fresh bare entity rows per test; the clone carries
the template's seeded ``pair_tags`` vocabulary and is dropped after the
module, so no owner slot is touched.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import closing

import psycopg2
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from nexus.agents.orrery.resolver import hydrate_world_state
from nexus.agents.orrery.substrate import (
    Slot,
    has_pair_tag,
    lacks_pair_tag,
)
from nexus.agents.orrery.tag_writer import (
    apply_pair_tag_bestowal,
    clear_pair_tag,
)
from tests.pg_fixtures import connect, disposable_slot_database, sqlalchemy_url


pytestmark = pytest.mark.requires_postgres

# Pair-tag names the suite bestows; migration 042 seeds them in the template.
REQUIRED_TAGS = ("mentors", "protects")


class _TestEntities:
    """Container for freshly-created test entity IDs."""

    def __init__(self, *, char_a: int, char_b: int, all_ids: list[int]):
        self.char_a = char_a
        self.char_b = char_b
        self.all_ids = all_ids


@pytest.fixture(scope="module")
def pair_tag_slot() -> Iterator[str]:
    """Own one template clone for the module; it is dropped afterward."""

    with disposable_slot_database("qa640_pair_tag_substrate") as dbname:
        yield dbname


@pytest.fixture
def slot_connection(
    pair_tag_slot: str,
) -> Generator[psycopg2.extensions.connection, None, None]:
    with closing(connect(pair_tag_slot)) as conn:
        yield conn


@pytest.fixture
def sqlalchemy_session(pair_tag_slot: str) -> Generator[Session, None, None]:
    engine = create_engine(sqlalchemy_url(pair_tag_slot), future=True)
    SessionFactory = sessionmaker(bind=engine, future=True)
    try:
        with SessionFactory() as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def test_entities(
    slot_connection: psycopg2.extensions.connection,
) -> _TestEntities:
    """Create fresh bare character entities for isolated pair-tag tests.

    The clone's template vocabulary must carry the pair tags the suite
    bestows (migration 042's seed); a clone without them fails here by name.
    """

    with slot_connection.cursor() as cur:
        cur.execute(
            "SELECT tag FROM pair_tags WHERE NOT deprecated AND tag = ANY(%s)",
            (list(REQUIRED_TAGS),),
        )
        registered = {row[0] for row in cur.fetchall()}
    slot_connection.rollback()
    assert registered == set(REQUIRED_TAGS), (
        f"pair_tag_slot's template vocabulary lacks "
        f"{sorted(set(REQUIRED_TAGS) - registered)} (migration 042's seed)"
    )

    created_ids: list[int] = []
    with slot_connection:
        with slot_connection.cursor() as cur:
            for _ in range(2):
                cur.execute(
                    "INSERT INTO entities (kind, is_active) "
                    "VALUES ('character', true) RETURNING id"
                )
                created_ids.append(cur.fetchone()[0])

    return _TestEntities(
        char_a=created_ids[0],
        char_b=created_ids[1],
        all_ids=created_ids,
    )


def _bestow(
    cur,
    *,
    subject: int,
    obj: int,
    tag: str,
) -> None:
    apply_pair_tag_bestowal(
        cur,
        subject_entity_id=subject,
        object_entity_id=obj,
        subject_kind="character",
        object_kind="character",
        tag=tag,
    )


def test_hydrate_world_state_loads_active_pair_tags(
    slot_connection: psycopg2.extensions.connection,
    sqlalchemy_session: Session,
    test_entities: _TestEntities,
) -> None:
    """WorldState hydration exposes active directed pair tags."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_b,
                tag="mentors",
            )

    state = hydrate_world_state(
        sqlalchemy_session,
        anchor_chunk_id=None,
        window_chunks=1,
    )

    assert state.pair_tags[(test_entities.char_a, test_entities.char_b)] == frozenset(
        {"mentors"}
    )


def test_pair_tag_conditions_are_direction_and_tag_sensitive(
    slot_connection: psycopg2.extensions.connection,
    sqlalchemy_session: Session,
    test_entities: _TestEntities,
) -> None:
    """Condition predicates read directed pair tags from hydrated state."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_b,
                tag="mentors",
            )

    state = hydrate_world_state(
        sqlalchemy_session,
        anchor_chunk_id=None,
        window_chunks=1,
    )

    bindings = {Slot.ACTOR: test_entities.char_a, Slot.TARGET: test_entities.char_b}
    reversed_bindings = {
        Slot.ACTOR: test_entities.char_b,
        Slot.TARGET: test_entities.char_a,
    }

    assert has_pair_tag("mentors")(state, bindings)
    assert not has_pair_tag("mentors")(state, reversed_bindings)
    assert not has_pair_tag("protects")(state, bindings)
    assert not lacks_pair_tag("mentors")(state, bindings)
    assert lacks_pair_tag("mentors")(state, reversed_bindings)
    assert lacks_pair_tag("protects")(state, bindings)


def test_cleared_pair_tags_do_not_hydrate(
    slot_connection: psycopg2.extensions.connection,
    sqlalchemy_session: Session,
    test_entities: _TestEntities,
) -> None:
    """Rows cleared through the writer are absent from WorldState pair_tags."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_b,
                tag="mentors",
            )
            clear_pair_tag(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                tag="mentors",
            )

    state = hydrate_world_state(
        sqlalchemy_session,
        anchor_chunk_id=None,
        window_chunks=1,
    )

    assert "mentors" not in state.pair_tags.get(
        (test_entities.char_a, test_entities.char_b),
        frozenset(),
    )


def test_deprecated_pair_tags_do_not_hydrate(
    slot_connection: psycopg2.extensions.connection,
    sqlalchemy_session: Session,
    test_entities: _TestEntities,
) -> None:
    """Hydration filters active rows whose pair_tag definition is deprecated."""

    deprecated_tag_id: int | None = None
    deprecated_tag_name = "_test_deprecated_relation_substrate"

    try:
        with slot_connection:
            with slot_connection.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM entity_pair_tags
                    WHERE pair_tag_id IN (
                        SELECT id FROM pair_tags WHERE tag = %s
                    )
                    """,
                    (deprecated_tag_name,),
                )
                cur.execute(
                    "DELETE FROM pair_tags WHERE tag = %s",
                    (deprecated_tag_name,),
                )
                cur.execute(
                    """
                    INSERT INTO pair_tags (
                        tag, subject_kinds, object_kinds,
                        is_ephemeral, deprecated, description
                    ) VALUES (
                        %s, %s, %s, false, true, %s
                    )
                    RETURNING id
                    """,
                    (
                        deprecated_tag_name,
                        ["character"],
                        ["character"],
                        "Test fixture only; exercises hydration deprecation filter.",
                    ),
                )
                deprecated_tag_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO entity_pair_tags (
                        subject_entity_id,
                        object_entity_id,
                        pair_tag_id,
                        source_kind
                    ) VALUES (%s, %s, %s, 'skald_inline'::entity_tag_source_kind)
                    """,
                    (
                        test_entities.char_a,
                        test_entities.char_b,
                        deprecated_tag_id,
                    ),
                )

        state = hydrate_world_state(
            sqlalchemy_session,
            anchor_chunk_id=None,
            window_chunks=1,
        )

        assert deprecated_tag_name not in state.pair_tags.get(
            (test_entities.char_a, test_entities.char_b),
            frozenset(),
        )
    finally:
        if deprecated_tag_id is not None:
            with slot_connection:
                with slot_connection.cursor() as cur:
                    cur.execute(
                        "DELETE FROM entity_pair_tags WHERE pair_tag_id = %s",
                        (deprecated_tag_id,),
                    )
                    cur.execute(
                        "DELETE FROM pair_tags WHERE id = %s", (deprecated_tag_id,)
                    )
