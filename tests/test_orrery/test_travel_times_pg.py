"""PostgreSQL tests for travel world-time hydration and configured route speeds.

Everything runs on one module-scoped disposable template clone, routed under
``ROUTED_SLOT`` and dropped afterward, so no owner slot is read or written.
The clone carries a located player, an actor at an origin place, and a
destination place about a kilometer north in Manhattan.

The hydration test drives the real ``commit_orrery_tick_sync`` writer for a
``travel.start`` and commits it (the clone is disposable), then reads the row
back through ``hydrate_world_state`` and the hover audit's ``entity_context``.
The graph test seeds a one-edge walking graph under its own graph key, so the
``default`` graph the hydration test routes over stays empty in any order.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any, NamedTuple
import uuid

import asyncpg
import psycopg2.extras
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from nexus.agents.orrery.audit import entity_context
from nexus.agents.orrery.events import (
    _select_route_async,
    _select_route_sync,
    commit_orrery_tick_sync,
)
from nexus.agents.orrery.resolver import (
    OrreryResolutionDraft,
    OrreryTickProposal,
    hydrate_world_state,
)
from nexus.config.loader import settings_path_scope
from nexus.config.settings_models import OrreryTravelModeTable
from tests.pg_fixtures import (
    asyncpg_kwargs,
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_character,
    seed_place,
    seed_protagonist,
    seed_story_clock,
    seed_zone,
    sqlalchemy_url,
)

pytestmark = pytest.mark.requires_postgres

# The slot label the clone is routed under; the commit writer receives it as
# the production turn does.
ROUTED_SLOT = 2
WORLD_TIME = datetime(2073, 8, 1, 12, tzinfo=timezone.utc)
GRAPH_KEY = "qa785_graph"
ORIGIN = (-73.9857, 40.7484)
DESTINATION = (-73.9857, 40.7574)
WALKING_SPEED_KMH = 10.0
WALKING_DETOUR = 2.0
TIME_FIELDS = ("started_at_world_time", "updated_at_world_time", "eta_world_time")


class TravelStory(NamedTuple):
    """The clone, its actor, the two places, and the tick chunk."""

    dbname: str
    actor_entity_id: int
    origin_place_id: int
    destination_place_id: int
    tick_chunk_id: int


@pytest.fixture(scope="module")
def travel_story() -> Iterator[TravelStory]:
    """A routed clone with a player, an actor at the origin, and a tick chunk."""

    with disposable_slot_database("qa640_785s2") as dbname:
        with pytest.MonkeyPatch.context() as mp:
            route_slot_to_disposable(mp.setattr, slot=ROUTED_SLOT, dbname=dbname)
            seed_zone(
                dbname,
                name="Travel Zone",
                min_longitude=-74.1,
                min_latitude=40.6,
                max_longitude=-73.8,
                max_latitude=40.9,
            )
            origin_place_id, _ = seed_place(
                dbname,
                name="Travel Origin",
                longitude=ORIGIN[0],
                latitude=ORIGIN[1],
            )
            destination_place_id, _ = seed_place(
                dbname,
                name="Travel Destination",
                longitude=DESTINATION[0],
                latitude=DESTINATION[1],
            )
            seed_protagonist(
                dbname,
                base_timestamp=WORLD_TIME.isoformat(),
                current_location=origin_place_id,
            )
            seed_story_clock(dbname, world_time=WORLD_TIME)
            _, actor_entity_id = seed_character(
                dbname, name="Travel Actor", current_location=origin_place_id
            )
            tick_chunk_id = seed_story_clock(
                dbname, world_time=WORLD_TIME + timedelta(hours=1), scene=2
            )
            yield TravelStory(
                dbname,
                actor_entity_id,
                origin_place_id,
                destination_place_id,
                tick_chunk_id,
            )


def _walking_travel_config(tmp_path: Path) -> Path:
    """Write the real nexus.toml with walking at 10 km/h and a detour of 2."""

    source = Path("nexus.toml").read_text()
    for table, value in (
        ("speed_kmh", WALKING_SPEED_KMH),
        ("detour_factor", WALKING_DETOUR),
    ):
        source, replaced = re.subn(
            rf"(^\[orrery\.travel\.{table}\]\n)walking = .*$",
            rf"\g<1>walking = {value}",
            source,
            count=1,
            flags=re.MULTILINE,
        )
        assert replaced == 1
    config = tmp_path / "nexus.toml"
    config.write_text(source)
    return config


def _fetch_one(cur: Any, sql: str, params: tuple = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    assert row is not None, sql
    return row


def test_hydration_returns_the_times_travel_start_wrote(
    travel_story: TravelStory, tmp_path: Path
) -> None:
    """travel.start's three world times reach TravelState and the hover audit."""

    actor = travel_story.actor_entity_id
    tick = travel_story.tick_chunk_id
    draft = OrreryResolutionDraft(
        template_id="travel",
        priority=21,
        binding_hash=f"travel-times-{uuid.uuid4().hex}",
        bindings={"actor": actor},
        branch_label="Depart toward the planned destination",
        narrative_stub="{actor} starts the journey.",
        state_delta={
            "travel.start": {
                "destination_place_id": travel_story.destination_place_id,
                "mode": "walking",
                "initial_progress": 0.05,
            }
        },
        event_type="travel_departed",
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=tick, actor_count=1, resolutions=(draft,)
    )

    with settings_path_scope(_walking_travel_config(tmp_path)):
        conn = connect(travel_story.dbname)
        try:
            result = commit_orrery_tick_sync(
                conn, proposal, tick_chunk_id=tick, slot=ROUTED_SLOT
            )
            conn.commit()
            assert result.resolution_count == 1
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                row = _fetch_one(
                    cur,
                    """
                    SELECT status::text AS status,
                           route_method::text AS route_method,
                           estimated_duration_minutes,
                           started_at_world_time,
                           updated_at_world_time,
                           eta_world_time,
                           route_metadata
                    FROM character_travel_states
                    WHERE character_entity_id = %s
                    """,
                    (actor,),
                )
                tick_world_time = _fetch_one(
                    cur,
                    "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
                    (tick,),
                )["world_time"]
                geodesic_distance_m = float(
                    _fetch_one(
                        cur,
                        """
                        SELECT ST_Distance(o.coordinates, d.coordinates) AS meters
                        FROM places o, places d
                        WHERE o.id = %s AND d.id = %s
                        """,
                        (
                            travel_story.origin_place_id,
                            travel_story.destination_place_id,
                        ),
                    )["meters"]
                )
        finally:
            conn.close()

        engine = create_engine(sqlalchemy_url(travel_story.dbname), future=True)
        session = Session(bind=engine)
        try:
            state = hydrate_world_state(session, anchor_chunk_id=tick, window_chunks=30)
            context = entity_context(session, [actor], anchor_chunk_id=tick)
        finally:
            session.close()
            engine.dispose()

    assert row["status"] == "in_transit"
    assert row["route_method"] == "estimated"
    assert all(row[key] is not None for key in TIME_FIELDS)
    assert 900.0 < geodesic_distance_m < 1100.0

    travel = state.travel_states[actor]
    for key in TIME_FIELDS:
        assert getattr(travel, key) == row[key]
    assert travel.started_at_world_time == tick_world_time
    assert travel.updated_at_world_time == tick_world_time

    assert row["route_metadata"]["detour_factor"] == WALKING_DETOUR
    assert row["route_metadata"]["speed_kmh"] == WALKING_SPEED_KMH
    expected_minutes = (
        geodesic_distance_m * WALKING_DETOUR / 1000 / WALKING_SPEED_KMH * 60
    )
    started = row["started_at_world_time"]
    eta = row["eta_world_time"]
    assert float(row["estimated_duration_minutes"]) == pytest.approx(
        expected_minutes, abs=1e-6
    )
    assert (eta - started).total_seconds() / 60.0 == pytest.approx(
        expected_minutes, abs=1e-6
    )

    (entity,) = context["entities"]
    assert entity["entity_id"] == actor
    payload = entity["travel_state"]
    for key in TIME_FIELDS:
        assert isinstance(payload[key], str)
        assert payload[key] == getattr(travel, key).isoformat()
        assert datetime.fromisoformat(payload[key]) == row[key]


def _seed_walking_graph(story: TravelStory) -> None:
    """Seed one 1 km walking edge without a duration under ``GRAPH_KEY``."""

    conn = connect(story.dbname)
    try:
        with conn, conn.cursor() as cur:
            node_ids = []
            for node_key, (longitude, latitude) in (
                ("qa785-origin", ORIGIN),
                ("qa785-destination", DESTINATION),
            ):
                cur.execute(
                    """
                    INSERT INTO orrery_route_graph_nodes
                        (graph_key, node_key, coordinates, source)
                    VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), 'qa785')
                    ON CONFLICT (graph_key, node_key) DO UPDATE
                        SET source = EXCLUDED.source
                    RETURNING id
                    """,
                    (GRAPH_KEY, node_key, longitude, latitude),
                )
                node_ids.append(cur.fetchone()[0])
            cur.execute(
                "DELETE FROM orrery_route_graph_edges WHERE graph_key = %s",
                (GRAPH_KEY,),
            )
            cur.execute(
                """
                INSERT INTO orrery_route_graph_edges
                    (graph_key, from_node_id, to_node_id, travel_mode,
                     distance_m, duration_minutes, source)
                VALUES (%s, %s, %s, 'walking', 1000, NULL, 'qa785')
                """,
                (GRAPH_KEY, node_ids[0], node_ids[1]),
            )
            for place_id, node_id in (
                (story.origin_place_id, node_ids[0]),
                (story.destination_place_id, node_ids[1]),
            ):
                cur.execute(
                    """
                    INSERT INTO orrery_place_route_graph_nodes
                        (place_id, graph_key, travel_mode, node_id, source)
                    VALUES (%s, %s, 'walking', %s, 'qa785')
                    ON CONFLICT (place_id, graph_key, travel_mode) DO UPDATE
                        SET node_id = EXCLUDED.node_id
                    """,
                    (place_id, GRAPH_KEY, node_id),
                )
    finally:
        conn.close()


def test_graph_route_speed_comes_from_config(
    travel_story: TravelStory, tmp_path: Path
) -> None:
    """A graph edge without a duration is timed at the configured walking speed."""

    _seed_walking_graph(travel_story)
    route_args: dict[str, Any] = {
        "origin_place_id": travel_story.origin_place_id,
        "destination_place_id": travel_story.destination_place_id,
        "mode": "walking",
        "risk": "low",
        "route_graph_key": GRAPH_KEY,
    }

    async def select_async() -> dict[str, Any]:
        conn = await asyncpg.connect(**asyncpg_kwargs(travel_story.dbname))
        try:
            return await _select_route_async(conn, **route_args)
        finally:
            await conn.close()

    with settings_path_scope(_walking_travel_config(tmp_path)):
        conn = connect(travel_story.dbname)
        try:
            with conn.cursor() as cur:
                sync_route = _select_route_sync(cur, **route_args)
        finally:
            conn.rollback()
            conn.close()
        async_route = asyncio.run(select_async())

    for route in (sync_route, async_route):
        assert route["route_method"] == "osm_graph"
        assert route["metadata"]["graph_key"] == GRAPH_KEY
        assert route["distance_m"] == pytest.approx(1000.0, abs=1e-6)
        assert route["duration_minutes"] == pytest.approx(6.0, abs=1e-6)


def test_mode_table_matches_travel_mode_enum(travel_story: TravelStory) -> None:
    """Every orrery_travel_mode label has a configured value, and nothing more."""

    conn = connect(travel_story.dbname)
    try:
        with conn.cursor() as cur:
            (labels,) = _fetch_one(
                cur, "SELECT enum_range(NULL::orrery_travel_mode)::text[]"
            )
    finally:
        conn.rollback()
        conn.close()

    assert set(OrreryTravelModeTable.model_fields) == set(labels)
