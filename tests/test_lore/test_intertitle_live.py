"""Live intertitle hydration: the raw SQL runs against real PostgreSQL.

The formatting tests construct intertitle dicts directly, which cannot
catch a wrong column name in the loader's SQL — per the repo's testing
philosophy, the query itself must execute against real Postgres. It runs on
a module-scoped disposable template clone seeded with a canonical player at
a zoned place and a clocked head chunk; no owner slot is read or written.
Skipped unless NEXUS_RUN_POSTGRES=1.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import NamedTuple

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from tests.pg_fixtures import (
    disposable_slot_database,
    seed_place,
    seed_protagonist,
    seed_story_clock,
    seed_zone,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres

WORLD_TIME = datetime(2073, 8, 1, 18, 45, tzinfo=timezone.utc)
PLACE_NAME = "Intertitle Plaza"
PLACE_LONGITUDE = -73.9857
PLACE_LATITUDE = 40.7484


class IntertitleStory(NamedTuple):
    """The clone and the clocked head chunk the intertitle anchors on."""

    dbname: str
    head_chunk_id: int


@pytest.fixture(scope="module")
def intertitle_story() -> Iterator[IntertitleStory]:
    """A clone with a located canonical player and one clocked chunk.

    Seeded in need-clock anchor order: a bounded zone, a place resolved into
    it, the player standing there (which sets ``base_timestamp``), then the
    head chunk clocked at ``WORLD_TIME``.
    """

    with disposable_slot_database("qa885_intertitle") as dbname:
        seed_zone(
            dbname,
            name="Intertitle Zone",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        place_id, _ = seed_place(
            dbname,
            name=PLACE_NAME,
            longitude=PLACE_LONGITUDE,
            latitude=PLACE_LATITUDE,
        )
        seed_protagonist(
            dbname,
            name="Intertitle Player",
            base_timestamp=WORLD_TIME.isoformat(),
            current_location=place_id,
        )
        head_chunk_id = seed_story_clock(dbname, world_time=WORLD_TIME)
        yield IntertitleStory(dbname, head_chunk_id)


def test_load_intertitle_executes_against_seeded_clone(
    intertitle_story: IntertitleStory,
) -> None:
    engine = create_engine(sqlalchemy_url(intertitle_story.dbname))
    try:
        with sessionmaker(engine)() as session:
            anchor = session.execute(
                text("SELECT max(chunk_id) FROM chunk_metadata")
            ).scalar()
            assert anchor == intertitle_story.head_chunk_id
            intertitle = TurnCycleManager._load_intertitle(
                session, anchor_chunk_id=int(anchor)
            )
    finally:
        engine.dispose()

    assert intertitle is not None
    assert intertitle["season"] is not None
    assert intertitle["world_time"] is not None
    assert intertitle["world_time"] == WORLD_TIME.isoformat()
    assert intertitle["location_name"] == PLACE_NAME
    # The user character's place carries Earth-shaped WGS84 coordinates.
    assert intertitle["location_geom"].startswith("SRID=4326;POINT(")


def test_anchor_fallback_skips_retrograde_prologue(
    intertitle_story: IntertitleStory,
) -> None:
    """A synthetic prologue at head must not become the intertitle anchor."""

    import json as _json

    from nexus.agents.lore.utils.turn_context import TurnContext
    from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER

    engine = create_engine(sqlalchemy_url(intertitle_story.dbname))
    try:
        with sessionmaker(engine)() as session:
            session.execute(
                text(
                    """
                    INSERT INTO narrative_chunks (raw_text, authorial_directives)
                    VALUES ('synthetic prologue anchor', CAST(:markers AS jsonb))
                    """
                ),
                {"markers": _json.dumps([RETROGRADE_PROLOGUE_MARKER])},
            )
            inserted = session.execute(
                text("SELECT max(id) FROM narrative_chunks")
            ).scalar()

            mgr = TurnCycleManager.__new__(TurnCycleManager)
            ctx = TurnContext(turn_id="t", user_input="x", start_time=0)
            anchor = TurnCycleManager._orrery_anchor_chunk_id(mgr, session, ctx)

            assert inserted is not None
            assert anchor is not None and anchor < inserted
            assert anchor == intertitle_story.head_chunk_id
            session.rollback()
    finally:
        engine.dispose()
