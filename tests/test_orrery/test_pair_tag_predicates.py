"""Real-DB integration tests for the multi-entity tag DB-level predicates.

Exercises ``pair_tag_exists`` / ``lookup_pair_tag_subjects`` /
``lookup_pair_tag_objects`` against a live slot database (``save_05``).
Activated by ``NEXUS_RUN_POSTGRES=1``.

**Test isolation:** the fixture creates *fresh* bare entities for each test
(``INSERT INTO entities (kind, is_active)`` with no backing characters /
factions subtype row) and DELETEs them on teardown — the ON DELETE CASCADE
on ``entity_pair_tags.subject_entity_id`` / ``object_entity_id`` cleans up
any pair tags created between them automatically. This guarantees tests
are independent of whatever pre-existing data lives in save_05 (no risk
that an existing `mentors(char_1 → char_3)` row makes a false-when-absent
assertion fail). The trade-off: tests can't cross-check that
pre-existing user data is unaffected, but they don't touch it in the
first place.
"""

from __future__ import annotations

from typing import Generator

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
    """Create 3 fresh bare character entities + 1 fresh bare faction for
    isolated testing. Bare = entity row with no backing characters/factions
    subtype row, which is sufficient for pair-tag tests (they only need
    valid entity_ids to satisfy FK constraints). Teardown DELETEs the
    entities; the ON DELETE CASCADE on ``entity_pair_tags`` removes any
    pair tags created between them."""

    # Vocabulary guard: confirm the pair_tag names the test suite uses are
    # actually registered in `save_05.pair_tags`. If the slot was initialized
    # from a template lacking migration 042's seed, skip cleanly rather than
    # exploding with `ValueError: Unknown or deprecated pair_tag` deep in
    # `apply_pair_tag_bestowal`.
    required_tags = ("mentors", "protects")
    with slot_connection.cursor() as cur:
        cur.execute(
            "SELECT tag FROM pair_tags WHERE NOT deprecated AND tag = ANY(%s)",
            (list(required_tags),),
        )
        registered = {row[0] for row in cur.fetchall()}
    missing_tags = set(required_tags) - registered
    if missing_tags:
        pytest.skip(
            f"{TEST_DBNAME}.pair_tags is missing {sorted(missing_tags)}; "
            "predicate tests require migration 042's seed vocabulary."
        )

    created_ids: list[int] = []
    with slot_connection:
        with slot_connection.cursor() as cur:
            character_ids = []
            for _ in range(3):
                cur.execute(
                    "INSERT INTO entities (kind, is_active) VALUES ('character', true) RETURNING id"
                )
                character_ids.append(cur.fetchone()[0])
            char_a, char_b, char_c = character_ids
            created_ids.extend(character_ids)

            cur.execute(
                "INSERT INTO entities (kind, is_active) VALUES ('faction', true) RETURNING id"
            )
            faction = cur.fetchone()[0]
            created_ids.append(faction)

    entities = _TestEntities(
        char_a=char_a,
        char_b=char_b,
        char_c=char_c,
        faction=faction,
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
                cur.execute(
                    "DELETE FROM entities WHERE id = ANY(%s)",
                    (created_ids,),
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
    """Two distinct subjects both mentoring the same object appear in ascending ID order."""

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
    """Different relations from the same subject don't bleed into each other's results."""

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
