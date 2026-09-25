"""Real sync/async acceptance of bootstrap and subsequent episode transitions.

Each test clones the template into a disposable database. It exercises the
production commit readers/writers, metadata triggers, and summary job inserts;
no provider is called and no saved campaign is used as a fixture.
"""

import asyncio
from collections.abc import Iterator
from contextlib import closing
from uuid import uuid4

import pytest

from nexus.agents.orrery.retrograde_persistence import (
    _ensure_prologue_metadata,
    _insert_prologue_chunk,
)
from nexus.api.commit_handler import commit_incubator_to_database
from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.api.slot_utils import VALID_DBNAMES
from tests.pg_fixtures import connect, disposable_slot_database, seed_protagonist
from tests.test_commit_choice_presence_pg import _connect_async, _insert_staged_turn

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def episode_database() -> Iterator[tuple[str, int, int]]:
    """Create a fresh story's player, setting, and real Retrograde prologue."""
    with disposable_slot_database("qa947_episode") as dbname:
        VALID_DBNAMES.add(dbname)
        try:
            character_id, _ = seed_protagonist(dbname)
            with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO places (name, type) "
                    "VALUES ('Harbor Office', 'fixed_location') RETURNING id"
                )
                place_id = cur.fetchone()[0]
                prologue_id = _insert_prologue_chunk(cur)
                _ensure_prologue_metadata(cur, prologue_chunk_id=prologue_id)
            yield dbname, character_id, place_id
        finally:
            VALID_DBNAMES.discard(dbname)


def _accept_turn(
    dbname: str,
    character_id: int,
    place_id: int,
    *,
    acceptance: str,
    parent_id: int,
    transition: str,
) -> tuple[int, str]:
    """Stage a complete draft and invoke an unpatched accepting transaction."""
    session_id = str(uuid4())
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        _insert_staged_turn(
            cur,
            session_id=session_id,
            parent_chunk_id=parent_id,
            storyteller_text="Rain darkens the harbor office windows.",
            choice_object={
                "presented": ["Read the launch order.", "Wait."],
                "selected": 1,
            },
            choice_text=None,
            reference_updates={
                "characters": [
                    {"character_id": character_id, "reference_type": "present"}
                ],
                "places": [{"place_id": place_id, "reference_type": "setting"}],
                "factions": [],
            },
            metadata_updates={
                "chronology": {
                    "episode_transition": transition,
                    "time_delta_minutes": 0 if parent_id == 0 else 5,
                    "time_delta_description": (
                        "Story begins" if parent_id == 0 else "Later"
                    ),
                },
                "world_layer": "primary",
            },
        )
    if acceptance == "async":

        async def accept() -> int:
            conn = await _connect_async(dbname)
            try:
                return await commit_incubator_to_database(conn, session_id)
            finally:
                await conn.close()

        return asyncio.run(accept()), session_id
    with closing(connect(dbname)) as conn:
        return commit_incubator_to_database_sync(conn, session_id), session_id


@pytest.mark.parametrize("acceptance", ["sync", "async"])
def test_opening_and_real_transitions_schedule_only_populated_predecessors(
    episode_database: tuple[str, int, int], acceptance: str
) -> None:
    """S1E1 opens without work; later transitions each queue valid spans once."""
    dbname, character_id, place_id = episode_database
    parent_id = 0
    expected_jobs: list[tuple[str, int, int | None, str]] = []
    for transition, expected_episode, closed_spans in [
        ("new_episode", (1, 1), []),
        ("continue", (1, 1), []),
        ("new_episode", (1, 2), [("episode", 1, 1)]),
        ("continue", (1, 2), []),
        ("new_season", (2, 1), [("episode", 1, 2), ("season", 1, None)]),
        ("continue", (2, 1), []),
    ]:
        chunk_id, session_id = _accept_turn(
            dbname,
            character_id,
            place_id,
            acceptance=acceptance,
            parent_id=parent_id,
            transition=transition,
        )
        expected_jobs.extend((*span, session_id) for span in closed_spans)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT season, episode, scene, time_delta, slug "
                "FROM chunk_metadata WHERE chunk_id = %s",
                (chunk_id,),
            )
            season, episode, scene, elapsed, slug = cur.fetchone()
            assert (season, episode) == expected_episode
            if parent_id == 0:
                assert (scene, elapsed.total_seconds(), slug) == (1, 0, "S01E01_001")
            else:
                assert elapsed.total_seconds() == 300
            cur.execute(
                "SELECT kind, season, episode, generation_session_id::text "
                "FROM narrative_summary_jobs ORDER BY id"
            )
            assert cur.fetchall() == expected_jobs
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone() == (0,)
            # Every scheduled predecessor really contains playable narrative.
            cur.execute(
                """SELECT count(*) FROM narrative_summary_jobs j
                WHERE NOT EXISTS (
                    SELECT 1 FROM chunk_metadata m
                    WHERE m.season = j.season
                      AND (j.kind = 'season' OR m.episode = j.episode)
                      AND m.world_layer = 'primary'
                )"""
            )
            assert cur.fetchone() == (0,)
        parent_id = chunk_id
