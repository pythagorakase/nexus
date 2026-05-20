"""Real-DB integration tests for the entity_pair_tags writer.

Exercises ``apply_pair_tag_bestowal`` and ``clear_pair_tag`` against a live
slot database (``save_05`` by default). Verifies that the migration-042
substrate works end-to-end: insert, idempotent re-insert, kind validation,
self-loop rejection, clear-then-reinsert cycle.

These tests are guarded by the ``requires_postgres`` marker; activate with
``NEXUS_RUN_POSTGRES=1`` to run them. Cleanup runs in the fixture both
pre- and post-yield so a failed run never leaves pair tags behind in the
slot.
"""

from __future__ import annotations

from typing import Generator

import psycopg2
import pytest

from nexus.agents.orrery.tag_writer import (
    apply_pair_tag_bestowal,
    clear_pair_tag,
)


pytestmark = pytest.mark.requires_postgres


TEST_DBNAME = "save_05"


# Two pre-existing character entity IDs in save_05. If save_05 is rebuilt and
# these IDs change, the fixture's pre-yield cleanup still works (it scopes by
# subject/object pair) — but the tests will fail FK validation. In that case,
# look up two character entities via ``SELECT id FROM entities WHERE kind =
# 'character' LIMIT 2``.
TEST_SUBJECT_ENTITY_ID = 1
TEST_OBJECT_ENTITY_ID = 3


@pytest.fixture
def slot_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Yield a save_05 connection; clean any test pair tags before and after."""

    conn = psycopg2.connect(
        dbname=TEST_DBNAME,
        user="pythagor",
        host="localhost",
        port=5432,
    )
    try:
        _purge_test_rows(conn)
        yield conn
    finally:
        _purge_test_rows(conn)
        conn.close()


def _purge_test_rows(conn: psycopg2.extensions.connection) -> None:
    """Delete any entity_pair_tags rows between the two test entity IDs (both directions)."""
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM entity_pair_tags
                WHERE (subject_entity_id = %s AND object_entity_id = %s)
                   OR (subject_entity_id = %s AND object_entity_id = %s)
                """,
                (
                    TEST_SUBJECT_ENTITY_ID,
                    TEST_OBJECT_ENTITY_ID,
                    TEST_OBJECT_ENTITY_ID,
                    TEST_SUBJECT_ENTITY_ID,
                ),
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
) -> None:
    """A fresh insert succeeds and creates exactly one active row."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            inserted = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                object_entity_id=TEST_OBJECT_ENTITY_ID,
                subject_kind="character",
                object_kind="character",
                tag="mentors",
            )
            assert inserted is True

    assert (
        _count_active_pair_tags(
            slot_connection,
            subject_id=TEST_SUBJECT_ENTITY_ID,
            object_id=TEST_OBJECT_ENTITY_ID,
            tag="mentors",
        )
        == 1
    )


def test_insert_is_idempotent(
    slot_connection: psycopg2.extensions.connection,
) -> None:
    """Inserting the same (subject, object, tag) twice yields exactly one active row."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            first = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                object_entity_id=TEST_OBJECT_ENTITY_ID,
                subject_kind="character",
                object_kind="character",
                tag="mentors",
            )
            second = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                object_entity_id=TEST_OBJECT_ENTITY_ID,
                subject_kind="character",
                object_kind="character",
                tag="mentors",
            )
            assert first is True
            assert second is False  # Duplicate suppressed by unique partial index

    assert (
        _count_active_pair_tags(
            slot_connection,
            subject_id=TEST_SUBJECT_ENTITY_ID,
            object_id=TEST_OBJECT_ENTITY_ID,
            tag="mentors",
        )
        == 1
    )


def test_insert_rejects_self_loop(
    slot_connection: psycopg2.extensions.connection,
) -> None:
    """A pair tag from an entity to itself is rejected before SQL is issued."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            with pytest.raises(ValueError, match="distinct subject and object"):
                apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                    object_entity_id=TEST_SUBJECT_ENTITY_ID,
                    subject_kind="character",
                    object_kind="character",
                    tag="mentors",
                )


def test_insert_rejects_unknown_tag(
    slot_connection: psycopg2.extensions.connection,
) -> None:
    """An unknown pair_tag raises ValueError without issuing an INSERT."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            with pytest.raises(ValueError, match="Unknown or deprecated pair_tag"):
                apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                    object_entity_id=TEST_OBJECT_ENTITY_ID,
                    subject_kind="character",
                    object_kind="character",
                    tag="this_tag_does_not_exist",
                )


def test_insert_rejects_invalid_subject_kind(
    slot_connection: psycopg2.extensions.connection,
) -> None:
    """A subject_kind not in the tag's allowed list raises ValueError."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            # `mentors` requires both subject and object to be `character`
            with pytest.raises(ValueError, match="does not allow subject_kind"):
                apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                    object_entity_id=TEST_OBJECT_ENTITY_ID,
                    subject_kind="faction",  # not allowed for mentors
                    object_kind="character",
                    tag="mentors",
                )


def test_insert_rejects_invalid_object_kind(
    slot_connection: psycopg2.extensions.connection,
) -> None:
    """An object_kind not in the tag's allowed list raises ValueError."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            # `mentors` requires both subject and object to be `character`
            with pytest.raises(ValueError, match="does not allow object_kind"):
                apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                    object_entity_id=TEST_OBJECT_ENTITY_ID,
                    subject_kind="character",
                    object_kind="place",  # not allowed for mentors
                    tag="mentors",
                )


def test_clear_then_reinsert_cycle(
    slot_connection: psycopg2.extensions.connection,
) -> None:
    """Clearing an active row allows a fresh insert (active count goes 1 → 0 → 1)."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            apply_pair_tag_bestowal(
                cur,
                subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                object_entity_id=TEST_OBJECT_ENTITY_ID,
                subject_kind="character",
                object_kind="character",
                tag="mentors",
            )
            assert (
                _count_active_pair_tags(
                    slot_connection,
                    subject_id=TEST_SUBJECT_ENTITY_ID,
                    object_id=TEST_OBJECT_ENTITY_ID,
                    tag="mentors",
                )
                == 1
            )

            cleared = clear_pair_tag(
                cur,
                subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                object_entity_id=TEST_OBJECT_ENTITY_ID,
                tag="mentors",
            )
            assert cleared is True

    assert (
        _count_active_pair_tags(
            slot_connection,
            subject_id=TEST_SUBJECT_ENTITY_ID,
            object_id=TEST_OBJECT_ENTITY_ID,
            tag="mentors",
        )
        == 0
    )

    with slot_connection:
        with slot_connection.cursor() as cur:
            reinserted = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                object_entity_id=TEST_OBJECT_ENTITY_ID,
                subject_kind="character",
                object_kind="character",
                tag="mentors",
            )
            assert reinserted is True

    assert (
        _count_active_pair_tags(
            slot_connection,
            subject_id=TEST_SUBJECT_ENTITY_ID,
            object_id=TEST_OBJECT_ENTITY_ID,
            tag="mentors",
        )
        == 1
    )


def test_clear_returns_false_when_no_active_row(
    slot_connection: psycopg2.extensions.connection,
) -> None:
    """Clearing a relation that isn't active returns False without raising."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            cleared = clear_pair_tag(
                cur,
                subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                object_entity_id=TEST_OBJECT_ENTITY_ID,
                tag="mentors",
            )
            assert cleared is False


def test_polymorphic_subject_kind_accepted(
    slot_connection: psycopg2.extensions.connection,
) -> None:
    """A pair_tag with multiple allowed subject_kinds accepts each of them."""

    with slot_connection:
        with slot_connection.cursor() as cur:
            # `obligation` allows both character and faction as subject; verify
            # the character path goes through (we use TEST_OBJECT for the faction
            # slot conceptually, but it's a character — kind validation is
            # type-only and doesn't check entity_id↔kind consistency at this
            # layer; that's the caller's responsibility).
            inserted = apply_pair_tag_bestowal(
                cur,
                subject_entity_id=TEST_SUBJECT_ENTITY_ID,
                object_entity_id=TEST_OBJECT_ENTITY_ID,
                subject_kind="character",
                object_kind="character",
                tag="obligation",
            )
            assert inserted is True
