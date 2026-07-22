"""Live sync/async Skald place-creation GIS contract tests."""

from __future__ import annotations

import uuid
from typing import Any, Iterator

import asyncpg
import psycopg2
import pytest

from nexus.agents.logon.apex_schema import Coordinates, NewPlace
from nexus.api.commit_handler_sync import create_new_place_sync
from nexus.api.db_converters import create_new_place
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres

_DDL = """
CREATE TABLE zones (
    id bigint PRIMARY KEY,
    name text NOT NULL,
    boundary geometry(MultiPolygon, 4326)
);
CREATE TABLE places (
    id bigserial PRIMARY KEY,
    entity_id bigserial NOT NULL,
    name text NOT NULL,
    type public.place_type NOT NULL,
    zone bigint,
    summary text,
    history text,
    current_status text,
    secrets text,
    extra_data jsonb,
    coordinates geography(PointZM, 4326)
);
CREATE TABLE characters (
    id bigint PRIMARY KEY,
    current_location bigint
);
CREATE TABLE global_variables (
    id boolean PRIMARY KEY,
    user_character bigint
);
INSERT INTO zones (id, name, boundary)
VALUES (
    10,
    'Story Zone',
    ST_Multi(ST_MakeEnvelope(-2, -2, 2, 2, 4326))
), (
    20,
    'Remote Zone',
    ST_Multi(ST_MakeEnvelope(48, 48, 52, 52, 4326))
);
INSERT INTO places (id, entity_id, name, type, zone)
VALUES (100, 100, 'Story Place', 'fixed_location', 10);
INSERT INTO characters (id, current_location) VALUES (1, 100);
INSERT INTO global_variables (id, user_character) VALUES (true, 1);
"""


@pytest.fixture()
def sync_cur() -> Iterator[Any]:
    conn = psycopg2.connect(get_slot_db_url(slot=5))
    schema = f"gis_new_place_{uuid.uuid4().hex}"
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(_DDL)
            yield cur
    finally:
        conn.rollback()
        conn.close()


def _sync_row(cur: Any, place_id: int) -> tuple[Any, ...]:
    cur.execute(
        """
        SELECT zone,
               ST_X(coordinates::geometry),
               ST_Y(coordinates::geometry)
        FROM places
        WHERE id = %s
        """,
        (place_id,),
    )
    return cur.fetchone()


def test_sync_coordinates_persist_and_resolve(sync_cur: Any) -> None:
    place_id = create_new_place_sync(
        sync_cur,
        NewPlace(
            name="Remote Observatory",
            coordinates=Coordinates(lat=50, lon=50),
        ),
    )

    assert _sync_row(sync_cur, place_id) == (20, 50.0, 50.0)


def test_sync_missing_coordinates_uses_story_zone(sync_cur: Any) -> None:
    place_id = create_new_place_sync(sync_cur, NewPlace(name="Unmapped Annex"))

    assert _sync_row(sync_cur, place_id) == (10, None, None)


def test_sync_virtual_place_never_persists_coordinates(sync_cur: Any) -> None:
    place_id = create_new_place_sync(
        sync_cur,
        NewPlace(
            name="The Mesh",
            type="virtual",
            coordinates=Coordinates(lat=50, lon=50),
        ),
    )

    assert _sync_row(sync_cur, place_id) == (10, None, None)


async def _async_case(new_place: NewPlace) -> tuple[Any, ...]:
    conn = await asyncpg.connect(get_slot_db_url(slot=5))
    transaction = conn.transaction()
    await transaction.start()
    schema = f"gis_new_place_async_{uuid.uuid4().hex}"
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET LOCAL search_path = "{schema}", public')
        await conn.execute(_DDL)
        place_id = await create_new_place(conn, new_place)
        row = await conn.fetchrow(
            """
            SELECT zone,
                   ST_X(coordinates::geometry) AS lon,
                   ST_Y(coordinates::geometry) AS lat
            FROM places
            WHERE id = $1
            """,
            place_id,
        )
        return tuple(row)
    finally:
        await transaction.rollback()
        await conn.close()


@pytest.mark.asyncio
async def test_async_coordinates_persist_and_resolve() -> None:
    row = await _async_case(
        NewPlace(
            name="Remote Observatory",
            coordinates=Coordinates(lat=50, lon=50),
        )
    )
    assert row == (20, 50.0, 50.0)


@pytest.mark.asyncio
async def test_async_missing_coordinates_uses_story_zone() -> None:
    assert await _async_case(NewPlace(name="Unmapped Annex")) == (10, None, None)


@pytest.mark.asyncio
async def test_async_virtual_place_never_persists_coordinates() -> None:
    row = await _async_case(
        NewPlace(
            name="The Mesh",
            type="virtual",
            coordinates=Coordinates(lat=50, lon=50),
        )
    )
    assert row == (10, None, None)
