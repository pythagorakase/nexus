"""Rollback-only live coverage for localized weather and Skald persistence."""

from datetime import datetime, timezone
from pathlib import Path
import uuid

import asyncpg
import psycopg2
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
from nexus.api.slot_utils import get_slot_db_url
from nexus.config import load_settings_as_dict


pytestmark = pytest.mark.requires_postgres


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


def test_live_anchor_override_and_disabled_mode() -> None:
    engine = create_engine(get_slot_db_url(slot=5), future=True)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        has_column = connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'chunk_metadata'
                      AND column_name = 'scene_weather'
                )
                """
            )
        ).scalar_one()
        if not has_column:
            connection.exec_driver_sql(_migration_sql())
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
        if anchor is None:
            pytest.skip("save_05 needs a timed anchor with a zoned setting place")
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


def test_sync_commit_stack_persists_scene_weather() -> None:
    conn = psycopg2.connect(get_slot_db_url(slot=5))
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
            assert cur.fetchone()[0] == "fog"
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.asyncio
async def test_async_commit_stack_persists_scene_weather() -> None:
    conn = await asyncpg.connect(get_slot_db_url(slot=5))
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
