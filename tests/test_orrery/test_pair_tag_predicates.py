"""Real-DB integration tests for the multi-entity tag DB-level predicates.

Exercises ``pair_tag_exists`` / ``lookup_pair_tag_subjects`` /
``lookup_pair_tag_objects`` against a live slot database (``save_05``).
Activated by ``NEXUS_RUN_POSTGRES=1``.

Reuses the same surgical-cleanup pattern as ``test_pair_tag_writer.py``:
snapshot pre-existing row IDs between chosen entities, restore-by-deletion
of only test-created rows on teardown.
"""

from __future__ import annotations

from typing import Generator, Optional

import psycopg2
import pytest

from nexus.agents.orrery.pair_tag_predicates import (
    lookup_pair_tag_objects,
    lookup_pair_tag_subjects,
    pair_tag_exists,
)
from nexus.agents.orrery.tag_writer import (
    apply_pair_tag_bestowal,
    clear_pair_tag,
)
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


TEST_DBNAME = "save_05"


class _TestEntities:
    """Container for resolved test entity IDs and row-ID snapshots."""

    def __init__(
        self,
        *,
        char_a: int,
        char_b: int,
        char_c: int,
        faction: Optional[int],
        preexisting_ids: set[int],
    ):
        self.char_a = char_a
        self.char_b = char_b
        self.char_c = char_c
        self.faction = faction
        self.preexisting_ids = preexisting_ids


@pytest.fixture
def slot_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    conn = psycopg2.connect(get_slot_db_url(dbname=TEST_DBNAME))
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def test_entities(
    slot_connection: psycopg2.extensions.connection,
) -> Generator[_TestEntities, None, None]:
    """Resolve three character entity IDs (and optionally a faction) for tests
    that need a non-trivial inbound/outbound fan-out, snapshot pre-existing
    pair_tags rows between them, and remove only test-created rows on
    teardown."""

    with slot_connection.cursor() as cur:
        cur.execute(
            "SELECT id FROM entities WHERE kind = 'character' ORDER BY id LIMIT 3"
        )
        char_rows = cur.fetchall()
        if len(char_rows) < 3:
            pytest.skip(
                f"{TEST_DBNAME} has fewer than 3 character entities; "
                "cannot exercise pair-tag predicates with fan-out."
            )
        char_a, char_b, char_c = (row[0] for row in char_rows)

        cur.execute("SELECT id FROM entities WHERE kind = 'faction' ORDER BY id LIMIT 1")
        faction_row = cur.fetchone()
        faction = faction_row[0] if faction_row else None

        ids_in_scope = [char_a, char_b, char_c]
        if faction is not None:
            ids_in_scope.append(faction)
        cur.execute(
            """
            SELECT id FROM entity_pair_tags
            WHERE subject_entity_id = ANY(%s) AND object_entity_id = ANY(%s)
            """,
            (ids_in_scope, ids_in_scope),
        )
        preexisting_ids = {row[0] for row in cur.fetchall()}

    entities = _TestEntities(
        char_a=char_a,
        char_b=char_b,
        char_c=char_c,
        faction=faction,
        preexisting_ids=preexisting_ids,
    )

    try:
        yield entities
    finally:
        with slot_connection:
            with slot_connection.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM entity_pair_tags
                    WHERE subject_entity_id = ANY(%s)
                      AND object_entity_id = ANY(%s)
                      AND NOT (id = ANY(%s))
                    """,
                    (ids_in_scope, ids_in_scope, list(entities.preexisting_ids)),
                )


def _bestow(
    cur,
    *,
    subject: int,
    obj: int,
    tag: str,
    subject_kind: str = "character",
    object_kind: str = "character",
) -> None:
    apply_pair_tag_bestowal(
        cur,
        subject_entity_id=subject,
        object_entity_id=obj,
        subject_kind=subject_kind,
        object_kind=object_kind,
        tag=tag,
    )


# ---------------------------------------------------------------------------
# pair_tag_exists
# ---------------------------------------------------------------------------


def test_exists_returns_false_for_missing_row(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """Absent relation returns False."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            assert (
                pair_tag_exists(
                    cur,
                    subject_entity_id=test_entities.char_a,
                    object_entity_id=test_entities.char_b,
                    tag="mentors",
                )
                is False
            )


def test_exists_returns_true_after_bestowal(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """Active relation returns True."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_b, tag="mentors")
            assert (
                pair_tag_exists(
                    cur,
                    subject_entity_id=test_entities.char_a,
                    object_entity_id=test_entities.char_b,
                    tag="mentors",
                )
                is True
            )


def test_exists_returns_false_after_clear(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """Cleared relation no longer exists from the predicate's perspective."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_b, tag="mentors")
            clear_pair_tag(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                tag="mentors",
            )
            assert (
                pair_tag_exists(
                    cur,
                    subject_entity_id=test_entities.char_a,
                    object_entity_id=test_entities.char_b,
                    tag="mentors",
                )
                is False
            )


def test_exists_is_direction_sensitive(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """A relation in one direction is NOT seen as existing in the reverse direction."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_b, tag="mentors")
            assert (
                pair_tag_exists(
                    cur,
                    subject_entity_id=test_entities.char_a,
                    object_entity_id=test_entities.char_b,
                    tag="mentors",
                )
                is True
            )
            assert (
                pair_tag_exists(
                    cur,
                    subject_entity_id=test_entities.char_b,
                    object_entity_id=test_entities.char_a,
                    tag="mentors",
                )
                is False
            )


# ---------------------------------------------------------------------------
# lookup_pair_tag_subjects (inbound)
# ---------------------------------------------------------------------------


def test_lookup_subjects_empty_when_no_rows(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """Inbound lookup against an object with no incoming relations returns []."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            assert (
                lookup_pair_tag_subjects(
                    cur,
                    object_entity_id=test_entities.char_b,
                    tag="mentors",
                )
                == []
            )


def test_lookup_subjects_returns_multiple_in_id_order(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """Two distinct subjects both mentoring the same object appear in ascending ID order."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_c, tag="mentors")
            _bestow(cur, subject=test_entities.char_b, obj=test_entities.char_c, tag="mentors")
            subjects = lookup_pair_tag_subjects(
                cur,
                object_entity_id=test_entities.char_c,
                tag="mentors",
            )
            assert subjects == sorted([test_entities.char_a, test_entities.char_b])


def test_lookup_subjects_filters_by_tag(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """An unrelated relation does not appear when querying for a different tag."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_b, tag="mentors")
            _bestow(cur, subject=test_entities.char_c, obj=test_entities.char_b, tag="protects")
            assert lookup_pair_tag_subjects(
                cur, object_entity_id=test_entities.char_b, tag="mentors"
            ) == [test_entities.char_a]
            assert lookup_pair_tag_subjects(
                cur, object_entity_id=test_entities.char_b, tag="protects"
            ) == [test_entities.char_c]


def test_lookup_subjects_excludes_cleared(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """A cleared subject is not returned."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_c, tag="mentors")
            _bestow(cur, subject=test_entities.char_b, obj=test_entities.char_c, tag="mentors")
            clear_pair_tag(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_c,
                tag="mentors",
            )
            subjects = lookup_pair_tag_subjects(
                cur,
                object_entity_id=test_entities.char_c,
                tag="mentors",
            )
            assert subjects == [test_entities.char_b]


# ---------------------------------------------------------------------------
# lookup_pair_tag_objects (outbound)
# ---------------------------------------------------------------------------


def test_lookup_objects_empty_when_no_rows(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """Outbound lookup with no outgoing relations returns []."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            assert (
                lookup_pair_tag_objects(
                    cur,
                    subject_entity_id=test_entities.char_a,
                    tag="mentors",
                )
                == []
            )


def test_lookup_objects_returns_multiple_in_id_order(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """One subject mentoring multiple distinct objects produces sorted output."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_b, tag="mentors")
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_c, tag="mentors")
            objects = lookup_pair_tag_objects(
                cur,
                subject_entity_id=test_entities.char_a,
                tag="mentors",
            )
            assert objects == sorted([test_entities.char_b, test_entities.char_c])


def test_lookup_objects_excludes_cleared(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """A cleared object is not returned."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_b, tag="mentors")
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_c, tag="mentors")
            clear_pair_tag(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                tag="mentors",
            )
            objects = lookup_pair_tag_objects(
                cur,
                subject_entity_id=test_entities.char_a,
                tag="mentors",
            )
            assert objects == [test_entities.char_c]


def test_lookup_objects_filters_by_tag(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """Different relations from the same subject don't bleed into each other's results."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_b, tag="mentors")
            _bestow(cur, subject=test_entities.char_a, obj=test_entities.char_c, tag="protects")
            assert lookup_pair_tag_objects(
                cur, subject_entity_id=test_entities.char_a, tag="mentors"
            ) == [test_entities.char_b]
            assert lookup_pair_tag_objects(
                cur, subject_entity_id=test_entities.char_a, tag="protects"
            ) == [test_entities.char_c]
