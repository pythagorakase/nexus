"""Real-DB integration tests for the multi-entity tag DB-level predicates.

Exercises ``pair_tag_exists`` / ``lookup_pair_tag_subjects`` /
``lookup_pair_tag_objects`` against a disposable template clone that
``pair_tag_slot`` owns for the module. Activated by ``NEXUS_RUN_POSTGRES=1``.

**Test isolation:** ``test_entities`` creates *fresh* bare entities for each
test (``INSERT INTO entities (kind, is_active)`` with no backing characters /
factions subtype row), so no test depends on rows another test wrote, and
false-when-absent assertions cannot be broken by pre-existing pair tags. The
clone carries the template's seeded ``pair_tags`` vocabulary and is dropped
after the module, so no owner slot is touched.
"""

from __future__ import annotations

from contextlib import closing
from typing import Generator, Iterator

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
from tests.pg_fixtures import connect, disposable_slot_database


pytestmark = pytest.mark.requires_postgres

# Pair-tag names the suite bestows; migration 042 seeds them in the template.
REQUIRED_TAGS = ("mentors", "protects")


class _TestEntities:
    """Container for freshly-created test entity IDs."""

    def __init__(
        self,
        *,
        char_a: int,
        char_b: int,
        char_c: int,
        faction: int | None,
        all_ids: list[int],
    ):
        self.char_a = char_a
        self.char_b = char_b
        self.char_c = char_c
        self.faction = faction
        self.all_ids = all_ids


@pytest.fixture(scope="module")
def pair_tag_slot() -> Iterator[str]:
    """Own one template clone for the module; it is dropped afterward."""

    with disposable_slot_database("qa640_pair_tag_predicates") as dbname:
        yield dbname


@pytest.fixture
def slot_connection(
    pair_tag_slot: str,
) -> Generator[psycopg2.extensions.connection, None, None]:
    with closing(connect(pair_tag_slot)) as conn:
        yield conn


@pytest.fixture
def test_entities(
    slot_connection: psycopg2.extensions.connection,
) -> _TestEntities:
    """Create 3 fresh bare character entities + 1 fresh bare faction.

    Bare = entity row with no backing characters/factions subtype row, which
    is sufficient for pair-tag tests (they only need valid entity_ids to
    satisfy FK constraints). The clone's template vocabulary must carry the
    pair tags the suite bestows (migration 042's seed); a clone without them
    fails here by name rather than deep inside ``apply_pair_tag_bestowal``.
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
            character_ids = []
            for _ in range(3):
                cur.execute(
                    "INSERT INTO entities (kind, is_active) "
                    "VALUES ('character', true) RETURNING id"
                )
                character_ids.append(cur.fetchone()[0])
            char_a, char_b, char_c = character_ids
            created_ids.extend(character_ids)

            cur.execute(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('faction', true) RETURNING id"
            )
            faction = cur.fetchone()[0]
            created_ids.append(faction)

    return _TestEntities(
        char_a=char_a,
        char_b=char_b,
        char_c=char_c,
        faction=faction,
        all_ids=created_ids,
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
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_b,
                tag="mentors",
            )
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
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_b,
                tag="mentors",
            )
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
    """Two subjects mentoring the same object appear in ascending ID order."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_c,
                tag="mentors",
            )
            _bestow(
                cur,
                subject=test_entities.char_b,
                obj=test_entities.char_c,
                tag="mentors",
            )
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
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_b,
                tag="mentors",
            )
            _bestow(
                cur,
                subject=test_entities.char_c,
                obj=test_entities.char_b,
                tag="protects",
            )
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
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_c,
                tag="mentors",
            )
            _bestow(
                cur,
                subject=test_entities.char_b,
                obj=test_entities.char_c,
                tag="mentors",
            )
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
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_b,
                tag="mentors",
            )
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_c,
                tag="mentors",
            )
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
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_b,
                tag="mentors",
            )
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_c,
                tag="mentors",
            )
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
    """Different relations from one subject don't bleed into each other's results."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_b,
                tag="mentors",
            )
            _bestow(
                cur,
                subject=test_entities.char_a,
                obj=test_entities.char_c,
                tag="protects",
            )
            assert lookup_pair_tag_objects(
                cur, subject_entity_id=test_entities.char_a, tag="mentors"
            ) == [test_entities.char_b]
            assert lookup_pair_tag_objects(
                cur, subject_entity_id=test_entities.char_a, tag="protects"
            ) == [test_entities.char_c]


# ---------------------------------------------------------------------------
# Deprecated-tag exclusion (covers the `NOT pt.deprecated` filter in all three
# predicates). Creates a temporary deprecated `pair_tags` row, inserts an
# `entity_pair_tags` edge using it (bypassing `apply_pair_tag_bestowal`'s
# deprecation check by writing the row directly), verifies all three
# predicates treat it as absent, and cleans up the registry row.
# ---------------------------------------------------------------------------


def test_deprecated_pair_tag_is_excluded_from_all_predicates(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """All three predicates filter out rows whose pair_tag is deprecated."""

    deprecated_tag_id: int | None = None
    deprecated_tag_name = "_test_deprecated_relation_predicate"

    try:
        # Phase 1: register a deprecated test-only pair_tag (committed).
        # Defensive cleanup of stale residue from a prior failed run before
        # inserting — `ON CONFLICT (tag) DO UPDATE` would also work but the
        # explicit delete makes the test's invariant ("this row is freshly
        # created by us") clear.
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
                        "Test fixture only — exercises predicate deprecation filter.",
                    ),
                )
                deprecated_tag_id = cur.fetchone()[0]

        # Phase 2: write an active entity_pair_tags row bypassing the writer
        # (which would reject the deprecated tag), then exercise predicates.
        with slot_connection:
            with slot_connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO entity_pair_tags (
                        subject_entity_id, object_entity_id, pair_tag_id, source_kind
                    ) VALUES (%s, %s, %s, 'skald_inline'::entity_tag_source_kind)
                    """,
                    (test_entities.char_a, test_entities.char_b, deprecated_tag_id),
                )

                assert (
                    pair_tag_exists(
                        cur,
                        subject_entity_id=test_entities.char_a,
                        object_entity_id=test_entities.char_b,
                        tag=deprecated_tag_name,
                    )
                    is False
                )
                assert (
                    lookup_pair_tag_subjects(
                        cur,
                        object_entity_id=test_entities.char_b,
                        tag=deprecated_tag_name,
                    )
                    == []
                )
                assert (
                    lookup_pair_tag_objects(
                        cur,
                        subject_entity_id=test_entities.char_a,
                        tag=deprecated_tag_name,
                    )
                    == []
                )
    finally:
        # The test's finally runs BEFORE the fixture's teardown, so the
        # entity_pair_tags row using this pair_tag is still alive and would
        # cause an FK violation on pair_tags DELETE. Clear the referring
        # rows first, then drop the registry row.
        if deprecated_tag_id is not None:
            with slot_connection:
                with slot_connection.cursor() as cur:
                    cur.execute(
                        "DELETE FROM entity_pair_tags WHERE pair_tag_id = %s",
                        (deprecated_tag_id,),
                    )
                    cur.execute(
                        "DELETE FROM pair_tags WHERE id = %s",
                        (deprecated_tag_id,),
                    )
