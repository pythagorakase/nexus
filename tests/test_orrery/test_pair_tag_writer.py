"""Real-DB integration tests for the entity_pair_tags writer.

Exercises ``apply_pair_tag_bestowal`` and ``clear_pair_tag`` against a
disposable clone of the canonical template. Verifies that the migration-042
substrate works end-to-end: insert, idempotent re-insert, kind validation,
self-loop rejection, clear-then-reinsert cycle, polymorphic acceptance.

These tests are guarded by the ``requires_postgres`` marker; activate with
``NEXUS_RUN_POSTGRES=1`` to run them.

Each test receives a fresh database and fixture-owned character/faction
entities, so no save-slot data is read or mutated.
"""

from __future__ import annotations

import os
from typing import Any, Generator, Optional

import psycopg2
import pytest

from nexus.agents.orrery.tag_writer import (
    apply_pair_tag_bestowal,
    clear_pair_tag,
)
from tests.pg_fixtures import disposable_slot_database


pytestmark = pytest.mark.requires_postgres


class _TestEntities:
    """Container for fixture-owned entity IDs."""

    def __init__(
        self,
        *,
        char_a: int,
        char_b: int,
        faction: Optional[int],
    ):
        self.char_a = char_a
        self.char_b = char_b
        self.faction = faction


def _connect(dbname: str) -> Any:
    """Open a direct connection to a disposable database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@pytest.fixture
def slot_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Yield a fresh canonical database and always drop it afterward."""

    with disposable_slot_database("qa735_pair_tags") as dbname:
        conn = _connect(dbname)
        try:
            yield conn
        finally:
            conn.close()


@pytest.fixture
def test_entities(
    slot_connection: psycopg2.extensions.connection,
) -> Generator[_TestEntities, None, None]:
    """Seed two characters, one faction, and a canonical player identity."""

    with slot_connection.cursor() as cur:
        cur.execute(
            "UPDATE global_variables SET base_timestamp = %s WHERE id = true",
            ("2100-01-01T00:00:00+00:00",),
        )
        assert cur.rowcount == 1
        characters: list[tuple[int, int]] = []
        for index in range(2):
            cur.execute("INSERT INTO entities (kind) VALUES ('character') RETURNING id")
            entity_row = cur.fetchone()
            assert entity_row is not None
            entity_id = int(entity_row[0])
            cur.execute(
                """
                INSERT INTO characters (name, summary, entity_id)
                VALUES (%s, 'Fixture-owned pair-tag character.', %s)
                RETURNING id
                """,
                (f"Pair Tag Character {index + 1}", entity_id),
            )
            character_row = cur.fetchone()
            assert character_row is not None
            characters.append((entity_id, int(character_row[0])))
        cur.execute("INSERT INTO entities (kind) VALUES ('faction') RETURNING id")
        faction_row = cur.fetchone()
        assert faction_row is not None
        faction = int(faction_row[0])
        cur.execute(
            """
            INSERT INTO factions (id, name, summary, entity_id)
            VALUES (%s, 'Pair Tag Faction', 'Fixture-owned faction.', %s)
            """,
            (faction, faction),
        )
        cur.execute(
            "UPDATE global_variables SET user_character = %s WHERE id = true",
            (characters[0][1],),
        )
        assert cur.rowcount == 1
    slot_connection.commit()

    entities = _TestEntities(
        char_a=characters[0][0],
        char_b=characters[1][0],
        faction=faction,
    )
    yield entities


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
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


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
    not.
    """

    assert test_entities.faction is not None

    active_before = _count_active_pair_tags(
        slot_connection,
        subject_id=test_entities.char_a,
        object_id=test_entities.faction,
        tag="obligation",
    )
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
            assert inserted is (active_before == 0)

    assert (
        _count_active_pair_tags(
            slot_connection,
            subject_id=test_entities.char_a,
            object_id=test_entities.faction,
            tag="obligation",
        )
        == 1
    )
