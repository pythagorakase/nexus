"""Real-DB integration tests for pair-tag WorldState hydration and predicates.

Exercises the Orrery Condition layer against a live ``save_05`` database.
Activated by ``NEXUS_RUN_POSTGRES=1``. Tests create fresh bare entity rows and
delete them on teardown; ``entity_pair_tags`` uses ON DELETE CASCADE for those
endpoints, so no user narrative data is touched.
"""

from __future__ import annotations

from collections.abc import Generator

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
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


TEST_DBNAME = "save_05"


class _TestEntities:
    """Container for freshly-created test entity IDs."""

    def __init__(self, *, char_a: int, char_b: int, all_ids: list[int]):
        self.char_a = char_a
        self.char_b = char_b
        self.all_ids = all_ids


@pytest.fixture
def slot_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    conn = psycopg2.connect(get_slot_db_url(dbname=TEST_DBNAME))
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def sqlalchemy_session() -> Generator[Session, None, None]:
    engine = create_engine(get_slot_db_url(dbname=TEST_DBNAME), future=True)
    SessionFactory = sessionmaker(bind=engine, future=True)
    try:
        with SessionFactory() as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def test_entities(
    slot_connection: psycopg2.extensions.connection,
) -> Generator[_TestEntities, None, None]:
    """Create fresh bare character entities for isolated pair-tag tests."""

    required_tags = ("mentors", "protects")
    try:
        with slot_connection.cursor() as cur:
            cur.execute(
                "SELECT tag FROM pair_tags WHERE NOT deprecated AND tag = ANY(%s)",
                (list(required_tags),),
            )
            registered = {row[0] for row in cur.fetchall()}
    except psycopg2.errors.UndefinedTable:
        slot_connection.rollback()
        pytest.skip(f"{TEST_DBNAME}.pair_tags is missing; run migration 042 first.")

    missing_tags = set(required_tags) - registered
    if missing_tags:
        pytest.skip(
            f"{TEST_DBNAME}.pair_tags is missing {sorted(missing_tags)}; "
            "substrate tests require migration 042's seed vocabulary."
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

    entities = _TestEntities(
        char_a=created_ids[0],
        char_b=created_ids[1],
        all_ids=created_ids,
    )
    try:
        yield entities
    finally:
        with slot_connection:
            with slot_connection.cursor() as cur:
                # tag_clearance_log references entity_pair_tags without
                # ON DELETE CASCADE (migration 064), so purge log rows for
                # the test entities' pair rows first; the entities DELETE
                # then cascades to entity_pair_tags as before.
                cur.execute(
                    """
                    DELETE FROM tag_clearance_log
                    WHERE entity_pair_tag_id IN (
                        SELECT id FROM entity_pair_tags
                        WHERE subject_entity_id = ANY(%s)
                           OR object_entity_id = ANY(%s)
                    )
                    """,
                    (created_ids, created_ids),
                )
                cur.execute("DELETE FROM entities WHERE id = ANY(%s)", (created_ids,))


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
