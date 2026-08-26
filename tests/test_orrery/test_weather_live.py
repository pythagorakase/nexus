"""Rollback-only live coverage for localized weather and Skald persistence."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import uuid

import asyncpg  # type: ignore[import-untyped]
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from nexus.agents.orrery.resolver import hydrate_world_state
from nexus.agents.orrery.weather import (
    classify_weather,
    climate_for_seed,
    derive_weather,
)
from nexus.agents.orrery.substrate import (
    Slot,
    TravelState,
    WorldState,
    evaluate_stack,
    weather_is,
)
from nexus.agents.orrery.templates import STROLL
from nexus.api.commit_handler import insert_chunk_metadata
from nexus.api.commit_handler_sync import insert_chunk_metadata_sync
from nexus.config import load_settings_as_dict
from tests import pg_fixtures
from tests.pg_fixtures import disposable_slot_database


pytestmark = pytest.mark.requires_postgres


@pytest.fixture(scope="module")
def weather_database() -> Iterator[str]:
    """Yield a migrated NEXUS_template clone and always drop it afterward."""

    with disposable_slot_database("qa735_weather") as dbname:
        yield dbname


def _migration_sql() -> str:
    return (
        Path(__file__).parents[2] / "migrations" / "094_scene_weather_override.sql"
    ).read_text()


def _create_metadata_table_sql() -> str:
    return """
        CREATE TABLE chunk_metadata (
            chunk_id bigint PRIMARY KEY,
            season integer NOT NULL,
            episode integer NOT NULL,
            scene integer NOT NULL,
            world_layer text NOT NULL,
            time_delta bigint,
            generation_date timestamptz,
            slug text NOT NULL,
            generation_model text
        )
    """


def test_binding_weather_uses_location_transit_origin_and_unknown() -> None:
    state = WorldState(
        locations={1: 10, 2: 20},
        place_weather={10: "warm", 20: "snow"},
        localized_weather_enabled=True,
        travel_states={
            2: TravelState(
                status="in_transit",
                origin_place_id=10,
                destination_place_id=20,
            )
        },
    )

    assert weather_is("warm")(state, {Slot.ACTOR: 1})
    assert weather_is("warm")(state, {Slot.ACTOR: 2})
    assert not weather_is("warm", "snow")(state, {Slot.ACTOR: 3})


def test_warm_arm_fires_from_local_weather() -> None:
    settings = {
        "climate_name": "warm_test",
        "period_hours": 6,
        "climates": {"warm_test": ["warm"]},
    }
    observed = derive_weather(
        7,
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        settings,
    )
    state = WorldState(
        locations={1: 10},
        location_classes={10: frozenset({"fixed_location"})},
        place_weather={10: observed},
        localized_weather_enabled=True,
        current_tick=100,
    )

    result = evaluate_stack((STROLL,), state, {Slot.ACTOR: 1})

    assert observed == "warm"
    assert result is not None
    assert result.branch_label == "Walk under open sky"


def test_live_anchor_override_and_disabled_mode(weather_database: str) -> None:
    engine = create_engine(pg_fixtures.sqlalchemy_url(weather_database), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        world_time = datetime(2088, 6, 1, 12, tzinfo=timezone.utc)
        connection.execute(
            text(
                "UPDATE global_variables SET base_timestamp = :world_time "
                "WHERE id = true"
            ),
            {"world_time": world_time},
        )
        layer_id = int(
            connection.execute(
                text(
                    "INSERT INTO layers (name, type) "
                    "VALUES ('Issue 735 Weather Layer', 'planet') RETURNING id"
                )
            ).scalar_one()
        )
        zone_id = int(
            connection.execute(
                text(
                    "INSERT INTO zones (name, layer) "
                    "VALUES ('Issue 735 Weather Zone', :layer_id) RETURNING id"
                ),
                {"layer_id": layer_id},
            ).scalar_one()
        )
        entity_ids = [
            int(row[0])
            for row in connection.execute(
                text(
                    "INSERT INTO entities (kind) VALUES "
                    "('place'), ('place'), ('character'), ('character') "
                    "RETURNING id"
                )
            )
        ]
        anchor_place_id = int(
            connection.execute(
                text(
                    "INSERT INTO places (name, type, zone, entity_id) "
                    "VALUES ('Issue 735 Anchor', 'fixed_location', :zone_id, "
                    ":entity_id) RETURNING id"
                ),
                {"zone_id": zone_id, "entity_id": entity_ids[0]},
            ).scalar_one()
        )
        remote_place_id = int(
            connection.execute(
                text(
                    "INSERT INTO places (name, type, zone, entity_id) "
                    "VALUES ('Issue 735 Remote', 'fixed_location', :zone_id, "
                    ":entity_id) RETURNING id"
                ),
                {"zone_id": zone_id, "entity_id": entity_ids[1]},
            ).scalar_one()
        )
        protagonist_id = int(
            connection.execute(
                text(
                    "INSERT INTO characters (name, current_location, entity_id) "
                    "VALUES ('Issue 735 Protagonist', :place_id, :entity_id) "
                    "RETURNING id"
                ),
                {"place_id": anchor_place_id, "entity_id": entity_ids[2]},
            ).scalar_one()
        )
        connection.execute(
            text(
                "INSERT INTO characters (name, current_location, entity_id) "
                "VALUES ('Issue 735 Remote Actor', :place_id, :entity_id)"
            ),
            {"place_id": remote_place_id, "entity_id": entity_ids[3]},
        )
        chunk_id = int(
            connection.execute(
                text(
                    "INSERT INTO narrative_chunks (raw_text) "
                    "VALUES ('Issue 735 weather anchor.') RETURNING id"
                )
            ).scalar_one()
        )
        connection.execute(
            text(
                "INSERT INTO chunk_metadata (chunk_id, world_time) "
                "VALUES (:chunk_id, :world_time)"
            ),
            {
                "chunk_id": chunk_id,
                "world_time": world_time,
            },
        )
        connection.execute(
            text(
                "UPDATE global_variables "
                "SET user_character = :protagonist_id, "
                'setting = \'{"story_seed": {"weather": "rain"}}\'::jsonb '
                "WHERE id = true"
            ),
            {"protagonist_id": protagonist_id},
        )
        anchor = (
            connection.execute(
                text(
                    """
                SELECT cm.chunk_id, active_place.id AS place_id
                FROM chunk_metadata cm
                JOIN global_variables gv ON gv.id = true
                JOIN characters protagonist
                  ON protagonist.id = gv.user_character
                JOIN places active_place
                  ON active_place.id = protagonist.current_location
                WHERE cm.world_time IS NOT NULL
                  AND active_place.zone IS NOT NULL
                ORDER BY cm.chunk_id DESC
                LIMIT 1
                """
                )
            )
            .mappings()
            .first()
        )
        assert anchor is not None
        connection.execute(
            text(
                "UPDATE chunk_metadata SET scene_weather = 'warm' "
                "WHERE chunk_id = :chunk_id"
            ),
            {"chunk_id": anchor["chunk_id"]},
        )
        weather_settings = load_settings_as_dict()["orrery"]["weather"]
        seed_weather = (
            connection.execute(
                text(
                    "SELECT setting #>> '{story_seed,weather}' "
                    "FROM global_variables WHERE id = true"
                )
            ).scalar_one_or_none()
            or ""
        )
        with Session(bind=connection) as session:
            localized = hydrate_world_state(
                session,
                anchor_chunk_id=int(anchor["chunk_id"]),
                window_chunks=30,
                weather_settings=weather_settings,
            )
            disabled = hydrate_world_state(
                session,
                anchor_chunk_id=int(anchor["chunk_id"]),
                window_chunks=30,
                weather_settings={"enabled": False},
            )

        anchor_place_id = int(anchor["place_id"])
        assert localized.weather == "warm"
        assert localized.place_weather[anchor_place_id] == "warm"
        assert disabled.place_weather == {}
        assert not disabled.localized_weather_enabled
        assert disabled.weather == classify_weather(seed_weather)

        remote = next(
            (
                place_id
                for place_id in localized.place_weather
                if place_id != anchor_place_id
            ),
            None,
        )
        assert remote is not None
        assert localized.world_time is not None
        runtime_settings = {
            **weather_settings,
            "climate_name": climate_for_seed(seed_weather, weather_settings),
        }
        assert localized.place_weather[remote] == derive_weather(
            localized.location_zones[remote],
            localized.world_time,
            runtime_settings,
        )
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_sync_commit_stack_persists_scene_weather(weather_database: str) -> None:
    conn = pg_fixtures.connect(weather_database)
    schema = f"weather_sync_{uuid.uuid4().hex}"
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}"')
            cur.execute(_create_metadata_table_sql())
            cur.execute(_migration_sql())
            insert_chunk_metadata_sync(
                cur,
                chunk_id=1,
                season=1,
                episode=1,
                scene=1,
                world_layer="primary",
                time_delta=0,
                generation_date=datetime.now(timezone.utc),
                slug="S01E01_001",
                generation_model="test-model",
                scene_weather="fog",
            )
            cur.execute("SELECT scene_weather FROM chunk_metadata WHERE chunk_id = 1")
            weather_row = cur.fetchone()
            assert weather_row is not None
            assert weather_row[0] == "fog"
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.asyncio
async def test_async_commit_stack_persists_scene_weather(
    weather_database: str,
) -> None:
    conn = await asyncpg.connect(**pg_fixtures.asyncpg_kwargs(weather_database))
    transaction = conn.transaction()
    await transaction.start()
    schema = f"weather_async_{uuid.uuid4().hex}"
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET LOCAL search_path = "{schema}"')
        await conn.execute(_create_metadata_table_sql())
        await conn.execute(_migration_sql())
        await insert_chunk_metadata(
            conn,
            chunk_id=1,
            season=1,
            episode=1,
            scene=1,
            world_layer="primary",
            time_delta=0,
            generation_model="test-model",
            scene_weather="snow",
        )
        assert (
            await conn.fetchval(
                "SELECT scene_weather FROM chunk_metadata WHERE chunk_id = 1"
            )
            == "snow"
        )
    finally:
        await transaction.rollback()
        await conn.close()
