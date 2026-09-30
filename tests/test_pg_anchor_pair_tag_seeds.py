"""PostgreSQL coverage for the routine-anchor and pair-tag seed helpers.

``seed_routine_anchor`` and ``seed_pair_tag`` commit one row each into a
disposable template clone. These tests read the rows back on a fresh
connection and prove that each helper fails loudly on the inputs the schema or
the vocabulary refuses, rather than inserting nothing.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from typing import Iterator

import psycopg2
import pytest

from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_character,
    seed_pair_tag,
    seed_place,
    seed_routine_anchor,
    seed_story_clock,
    seed_zone,
)

pytestmark = pytest.mark.requires_postgres

WORLD_TIME = datetime(2073, 8, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def seeded_db() -> Iterator[dict[str, int | str]]:
    """Own one clone with a clock, a place, and two characters."""

    with disposable_slot_database("qa885_anchor_pair_seeds") as dbname:
        seed_zone(
            dbname,
            name="Seed Helper Zone",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        place_id, _ = seed_place(dbname, name="Seed Helper Hall")
        chunk_id = seed_story_clock(dbname, world_time=WORLD_TIME)
        _, first_entity_id = seed_character(dbname, name="Seed Helper First")
        _, second_entity_id = seed_character(dbname, name="Seed Helper Second")
        yield {
            "dbname": dbname,
            "place_id": place_id,
            "chunk_id": chunk_id,
            "first": first_entity_id,
            "second": second_entity_id,
        }


def test_seed_routine_anchor_commits_one_row(
    seeded_db: dict[str, int | str],
) -> None:
    """The anchor is committed with its type, place, policy, and schedule."""

    dbname = str(seeded_db["dbname"])
    anchor_id = seed_routine_anchor(
        dbname,
        character_entity_id=int(seeded_db["first"]),
        place_id=int(seeded_db["place_id"]),
        anchor_type="work",
        schedule={"days": ["mon"]},
        source="test_pg_anchor_pair_tag_seeds",
    )
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT character_entity_id, anchor_type::text, place_id,
                   mobility_policy::text, schedule, source
            FROM character_routine_anchors
            WHERE id = %s
            """,
            (anchor_id,),
        )
        assert cur.fetchone() == (
            int(seeded_db["first"]),
            "work",
            int(seeded_db["place_id"]),
            "fixed_place",
            {"days": ["mon"]},
            "test_pg_anchor_pair_tag_seeds",
        )


def test_seed_routine_anchor_defaults_to_a_fixed_home(
    seeded_db: dict[str, int | str],
) -> None:
    """The defaults give a fixed-place home anchor with an empty schedule."""

    dbname = str(seeded_db["dbname"])
    anchor_id = seed_routine_anchor(
        dbname,
        character_entity_id=int(seeded_db["second"]),
        place_id=int(seeded_db["place_id"]),
    )
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT anchor_type::text, mobility_policy::text, schedule, source "
            "FROM character_routine_anchors WHERE id = %s",
            (anchor_id,),
        )
        assert cur.fetchone() == ("home", "fixed_place", {}, "test")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        seed_routine_anchor(
            dbname,
            character_entity_id=int(seeded_db["second"]),
            place_id=int(seeded_db["place_id"]),
        )


def test_seed_routine_anchor_refuses_a_fixed_anchor_without_a_place(
    seeded_db: dict[str, int | str],
) -> None:
    """The table's check constraint, not the helper, decides the location."""

    with pytest.raises(psycopg2.errors.CheckViolation):
        seed_routine_anchor(
            str(seeded_db["dbname"]),
            character_entity_id=int(seeded_db["first"]),
            place_id=None,
        )


def test_seed_pair_tag_commits_one_active_row(
    seeded_db: dict[str, int | str],
) -> None:
    """The row resolves its tag by name and is active and attributed."""

    dbname = str(seeded_db["dbname"])
    row_id = seed_pair_tag(
        dbname,
        subject_entity_id=int(seeded_db["first"]),
        object_entity_id=int(seeded_db["second"]),
        tag="contact:social",
        template_id="test_pg_anchor_pair_tag_seeds",
        source_chunk_id=int(seeded_db["chunk_id"]),
    )
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ept.subject_entity_id, ept.object_entity_id, pt.tag,
                   ept.source_kind::text, ept.template_id, ept.source_chunk_id,
                   ept.cleared_at
            FROM entity_pair_tags ept
            JOIN pair_tags pt ON pt.id = ept.pair_tag_id
            WHERE ept.id = %s
            """,
            (row_id,),
        )
        assert cur.fetchone() == (
            int(seeded_db["first"]),
            int(seeded_db["second"]),
            "contact:social",
            "template",
            "test_pg_anchor_pair_tag_seeds",
            int(seeded_db["chunk_id"]),
            None,
        )


@pytest.mark.parametrize("tag", ["no_such_pair_tag", "contact"])
def test_seed_pair_tag_refuses_unknown_and_deprecated_tags(
    seeded_db: dict[str, int | str], tag: str
) -> None:
    """An unknown or deprecated tag fails by name and commits nothing."""

    dbname = str(seeded_db["dbname"])
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT deprecated FROM pair_tags WHERE tag = %s", (tag,))
        row = cur.fetchone()
        # "contact" is the template's deprecated pair tag; the unknown tag has
        # no vocabulary row at all.
        assert row == ((True,) if tag == "contact" else None)
        cur.execute("SELECT count(*) FROM entity_pair_tags")
        before = cur.fetchone()[0]
    with pytest.raises(AssertionError, match=repr(tag)):
        seed_pair_tag(
            dbname,
            subject_entity_id=int(seeded_db["second"]),
            object_entity_id=int(seeded_db["first"]),
            tag=tag,
        )
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM entity_pair_tags")
        assert cur.fetchone()[0] == before
