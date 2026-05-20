"""Real-DB integration tests for the entity_pair_tags writer.

Exercises ``apply_pair_tag_bestowal`` and ``clear_pair_tag`` against a live
slot database (``save_05`` by default). Verifies that the migration-042
substrate works end-to-end: insert, idempotent re-insert, kind validation,
self-loop rejection, clear-then-reinsert cycle, polymorphic acceptance.

These tests are guarded by the ``requires_postgres`` marker; activate with
``NEXUS_RUN_POSTGRES=1`` to run them.

**Cleanup scoping (data-safety guarantee):** the fixture snapshots the IDs of
all ``entity_pair_tags`` rows that already exist for the chosen test entity
pair before the test runs, then on teardown deletes only rows whose IDs are
NOT in that snapshot. This preserves any legitimate pre-existing relations
between the chosen entities — the fixture only removes rows that the test
itself created.

**Entity selection:** the fixture queries ``entities`` at setup time for
character/faction IDs rather than hardcoding sentinel values. If insufficient
characters exist (e.g., a freshly reset save_05), the test is skipped rather
than failing on FK violations.
"""

from __future__ import annotations

from typing import Generator, Optional

import psycopg2
import pytest

from nexus.agents.orrery.tag_writer import (
    apply_pair_tag_bestowal,
    clear_pair_tag,
)
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


TEST_DBNAME = "save_05"


class _TestEntities:
    """Container for resolved test entity IDs and the row-ID snapshots used for
    surgical cleanup."""

    def __init__(
        self,
        *,
        char_a: int,
        char_b: int,
        faction: Optional[int],
        preexisting_ids: set[int],
    ):
        self.char_a = char_a
        self.char_b = char_b
        self.faction = faction
        self.preexisting_ids = preexisting_ids


@pytest.fixture
def slot_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Yield a save_05 connection (no entity setup; resolved by `test_entities`)."""

    conn = psycopg2.connect(get_slot_db_url(dbname=TEST_DBNAME))
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def test_entities(
    slot_connection: psycopg2.extensions.connection,
) -> Generator[_TestEntities, None, None]:
    """Resolve two character entity IDs (and optionally a faction) for the test
    suite, snapshot any pre-existing pair_tags rows between them, yield, then
    on teardown remove only rows the test created."""

    with slot_connection.cursor() as cur:
        cur.execute(
            "SELECT id FROM entities WHERE kind = 'character' ORDER BY id LIMIT 2"
        )
        char_rows = cur.fetchall()
        if len(char_rows) < 2:
            pytest.skip(
                f"{TEST_DBNAME} has fewer than 2 character entities; "
                "cannot exercise pair-tag writer."
            )
        char_a, char_b = char_rows[0][0], char_rows[1][0]

        cur.execute("SELECT id FROM entities WHERE kind = 'faction' ORDER BY id LIMIT 1")
        faction_row = cur.fetchone()
        faction = faction_row[0] if faction_row else None

        # Snapshot pre-existing row IDs between the chosen entities so cleanup
        # can be surgical (delete only test-created rows).
        ids_in_scope = [char_a, char_b]
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
        faction=faction,
        preexisting_ids=preexisting_ids,
    )

    try:
        yield entities
    finally:
        with slot_connection:
            with slot_connection.cursor() as cur:
                ids_in_scope = [char_a, char_b]
                if faction is not None:
                    ids_in_scope.append(faction)
                cur.execute(
                    """
                    DELETE FROM entity_pair_tags
                    WHERE subject_entity_id = ANY(%s)
                      AND object_entity_id = ANY(%s)
                      AND NOT (id = ANY(%s))
                    """,
                    (ids_in_scope, ids_in_scope, list(entities.preexisting_ids)),
                )


def _count_active_pair_tags(
    conn: psycopg2.extensions.connection,
    *,
    subject_id: int,
    object_id: int,
    tag: str,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            WHERE ept.subject_entity_id = %s
              AND ept.object_entity_id = %s
              AND pt.tag = %s
              AND ept.cleared_at IS NULL
            """,
            (subject_id, object_id, tag),
        )
        return cur.fetchone()[0]


def test_insert_durable_pair_tag(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """A fresh insert succeeds and creates exactly one active row."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            inserted = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                subject_kind="character",
                object_kind="character",
                tag="mentors",
            )
            assert inserted is True

    assert (
        _count_active_pair_tags(
            slot_connection,
            subject_id=test_entities.char_a,
            object_id=test_entities.char_b,
            tag="mentors",
        )
        == 1
    )


def test_insert_is_idempotent(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """Inserting the same (subject, object, tag) twice yields exactly one active row."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            first = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                subject_kind="character",
                object_kind="character",
                tag="mentors",
            )
            second = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                subject_kind="character",
                object_kind="character",
                tag="mentors",
            )
            assert first is True
            assert second is False  # Duplicate suppressed by unique partial index

    assert (
        _count_active_pair_tags(
            slot_connection,
            subject_id=test_entities.char_a,
            object_id=test_entities.char_b,
            tag="mentors",
        )
        == 1
    )


def test_insert_rejects_self_loop(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """A pair tag from an entity to itself is rejected before SQL is issued."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            with pytest.raises(ValueError, match="distinct subject and object"):
                apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=test_entities.char_a,
                    object_entity_id=test_entities.char_a,
                    subject_kind="character",
                    object_kind="character",
                    tag="mentors",
                )


def test_insert_rejects_unknown_tag(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """An unknown pair_tag raises ValueError without issuing an INSERT."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            with pytest.raises(ValueError, match="Unknown or deprecated pair_tag"):
                apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=test_entities.char_a,
                    object_entity_id=test_entities.char_b,
                    subject_kind="character",
                    object_kind="character",
                    tag="this_tag_does_not_exist",
                )


def test_insert_rejects_invalid_subject_kind(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """A subject_kind not in the tag's allowed list raises ValueError."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            # `mentors` requires both subject and object to be `character`
            with pytest.raises(ValueError, match="does not allow subject_kind"):
                apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=test_entities.char_a,
                    object_entity_id=test_entities.char_b,
                    subject_kind="faction",  # not allowed for mentors
                    object_kind="character",
                    tag="mentors",
                )


def test_insert_rejects_invalid_object_kind(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """An object_kind not in the tag's allowed list raises ValueError."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            # `mentors` requires both subject and object to be `character`
            with pytest.raises(ValueError, match="does not allow object_kind"):
                apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=test_entities.char_a,
                    object_entity_id=test_entities.char_b,
                    subject_kind="character",
                    object_kind="place",  # not allowed for mentors
                    tag="mentors",
                )


def test_clear_then_reinsert_cycle(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """Clearing an active row allows a fresh insert (active count goes 1 → 0 → 1)."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            apply_pair_tag_bestowal(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                subject_kind="character",
                object_kind="character",
                tag="mentors",
            )
            assert (
                _count_active_pair_tags(
                    slot_connection,
                    subject_id=test_entities.char_a,
                    object_id=test_entities.char_b,
                    tag="mentors",
                )
                == 1
            )

            cleared = clear_pair_tag(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                tag="mentors",
            )
            assert cleared is True

    assert (
        _count_active_pair_tags(
            slot_connection,
            subject_id=test_entities.char_a,
            object_id=test_entities.char_b,
            tag="mentors",
        )
        == 0
    )

    with slot_connection:
        with slot_connection.cursor() as cur:
            reinserted = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                subject_kind="character",
                object_kind="character",
                tag="mentors",
            )
            assert reinserted is True

    assert (
        _count_active_pair_tags(
            slot_connection,
            subject_id=test_entities.char_a,
            object_id=test_entities.char_b,
            tag="mentors",
        )
        == 1
    )


def test_clear_returns_false_when_no_active_row(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """Clearing a relation that isn't active returns False without raising."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            cleared = clear_pair_tag(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                tag="mentors",
            )
            assert cleared is False


def test_polymorphic_subject_kind_character_path(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """A pair_tag with polymorphic subject_kinds accepts the character path."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            inserted = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.char_b,
                subject_kind="character",
                object_kind="character",
                tag="obligation",
            )
            assert inserted is True


def test_polymorphic_object_kind_faction_path(
    slot_connection: psycopg2.extensions.connection,
    test_entities: _TestEntities,
) -> None:
    """A pair_tag with polymorphic object_kinds accepts the faction path.

    ``obligation`` allows ``character|faction`` on both ends — this case
    exercises the faction object path that the character-only test above does
    not. Skipped if save_05 has no faction entities.
    """

    if test_entities.faction is None:
        pytest.skip(f"{TEST_DBNAME} has no faction entities; skipping faction polymorphism case.")

    with slot_connection:
        with slot_connection.cursor() as cur:
            inserted = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=test_entities.char_a,
                object_entity_id=test_entities.faction,
                subject_kind="character",
                object_kind="faction",
                tag="obligation",
            )
            assert inserted is True
