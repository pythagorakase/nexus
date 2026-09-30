"""``seed_character_pair`` seeds a clocked chunk and two characters on a clone.

The helper replaces the "first two characters by id plus the latest clocked
chunk" reads that the project-applier tests once made against the owner's
``save_02``. These tests read back what it wrote on a disposable template
clone: the need-clock anchor, the exact chunk clock, two active character
entities with need rows, and a second pair that never reuses the first.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from tests.pg_fixtures import (
    CharacterPairSeed,
    connect,
    disposable_slot_database,
    seed_character_pair,
)

pytestmark = pytest.mark.requires_postgres

WORLD_TIME = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)


def test_pair_anchors_the_clock_then_seeds_two_active_characters() -> None:
    """The clone's first pair sets ``base_timestamp`` and clocks its chunk."""

    with disposable_slot_database("qa885_character_pair") as dbname:
        pair = seed_character_pair(
            dbname,
            world_time=WORLD_TIME,
            actor_name="Pair Actor",
            target_name="Pair Target",
        )
        assert isinstance(pair, CharacterPairSeed)
        assert pair.world_time == WORLD_TIME
        assert pair.actor_entity_id != pair.target_entity_id
        assert pair.actor_character_id != pair.target_character_id
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT base_timestamp FROM global_variables WHERE id = true")
            assert cur.fetchone()[0] == WORLD_TIME
            cur.execute(
                "SELECT chunk_id, world_time FROM chunk_metadata "
                "WHERE world_time IS NOT NULL ORDER BY chunk_id DESC LIMIT 1"
            )
            assert cur.fetchone() == (pair.chunk_id, WORLD_TIME)
            cur.execute(
                "SELECT c.id, c.entity_id, c.name, e.kind::text, e.is_active "
                "FROM characters c JOIN entities e ON e.id = c.entity_id "
                "ORDER BY c.id"
            )
            assert cur.fetchall() == [
                (
                    pair.actor_character_id,
                    pair.actor_entity_id,
                    "Pair Actor",
                    "character",
                    True,
                ),
                (
                    pair.target_character_id,
                    pair.target_entity_id,
                    "Pair Target",
                    "character",
                    True,
                ),
            ]
            cur.execute(
                "SELECT character_entity_id, count(*) FROM character_need_states "
                "GROUP BY character_entity_id ORDER BY character_entity_id"
            )
            need_rows = dict(cur.fetchall())
            assert set(need_rows) == {pair.actor_entity_id, pair.target_entity_id}
            assert all(count > 0 for count in need_rows.values())
            cur.execute("SELECT count(*) FROM character_relationships")
            assert cur.fetchone()[0] == 0


def test_second_pair_is_distinct_and_the_clock_never_moves_backward() -> None:
    """A later pair adds its own chunk and characters; an earlier clock fails."""

    with disposable_slot_database("qa885_character_pair") as dbname:
        first = seed_character_pair(
            dbname,
            world_time=WORLD_TIME,
            actor_name="First Actor",
            target_name="First Target",
        )
        later = WORLD_TIME + timedelta(hours=6)
        second = seed_character_pair(
            dbname,
            world_time=later,
            actor_name="Second Actor",
            target_name="Second Target",
        )
        assert second.chunk_id != first.chunk_id
        assert not {second.actor_entity_id, second.target_entity_id} & {
            first.actor_entity_id,
            first.target_entity_id,
        }
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id, world_time FROM chunk_metadata ORDER BY chunk_id"
            )
            assert cur.fetchall() == [
                (first.chunk_id, WORLD_TIME),
                (second.chunk_id, later),
            ]
            cur.execute("SELECT count(*) FROM characters")
            assert cur.fetchone()[0] == 4
        with pytest.raises(AssertionError, match="cannot move the clock backward"):
            seed_character_pair(
                dbname,
                world_time=WORLD_TIME,
                actor_name="Late Actor",
                target_name="Late Target",
            )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM characters")
            assert cur.fetchone()[0] == 4
