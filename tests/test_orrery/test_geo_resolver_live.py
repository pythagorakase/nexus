"""Live PostGIS contract tests for the shared zone resolver."""

from __future__ import annotations

import uuid
from typing import Any, Iterator

import psycopg2
import pytest

from nexus.agents.orrery.geo import resolve_zone_for_point, story_active_zone
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def geo_cur() -> Iterator[Any]:
    """Create a rollback-only schema with only the GIS contract tables."""

    conn = psycopg2.connect(get_slot_db_url(slot=5))
    schema = f"gis_resolver_{uuid.uuid4().hex}"
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(
                """
                CREATE TABLE zones (
                    id bigint PRIMARY KEY,
                    name text NOT NULL,
                    boundary geometry(MultiPolygon, 4326)
                );
                CREATE TABLE places (
                    id bigint PRIMARY KEY,
                    zone bigint
                );
                CREATE TABLE characters (
                    id bigint PRIMARY KEY,
                    current_location bigint
                );
                CREATE TABLE global_variables (
                    id boolean PRIMARY KEY,
                    user_character bigint
                )
                """
            )
            yield cur
    finally:
        conn.rollback()
        conn.close()


def _square(cur: Any, zone_id: int, x: float, y: float, size: float = 2) -> None:
    cur.execute(
        """
        INSERT INTO zones (id, name, boundary)
        VALUES (
            %s,
            %s,
            ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        )
        """,
        (zone_id, f"Zone {zone_id}", x, y, x + size, y + size),
    )


def test_covering_zone_wins_over_nearer_noncovering_zone(geo_cur: Any) -> None:
    _square(geo_cur, 20, 0, 0, 10)
    _square(geo_cur, 10, 1, 1, 1)

    assert resolve_zone_for_point(geo_cur, longitude=1.5, latitude=1.5) == 10


def test_nearest_boundary_wins_outside_all_zones(geo_cur: Any) -> None:
    _square(geo_cur, 10, 0, 0)
    _square(geo_cur, 20, 20, 20)

    assert resolve_zone_for_point(geo_cur, longitude=4, latitude=1) == 10


def test_zone_id_breaks_equal_distance_tie(geo_cur: Any) -> None:
    _square(geo_cur, 20, -3, -1)
    _square(geo_cur, 10, 1, -1)

    assert resolve_zone_for_point(geo_cur, longitude=0, latitude=0) == 10


def test_no_bounded_zone_raises(geo_cur: Any) -> None:
    geo_cur.execute("INSERT INTO zones (id, name) VALUES (1, 'Unbounded')")

    with pytest.raises(ValueError, match="no zone has a boundary"):
        resolve_zone_for_point(geo_cur, longitude=0, latitude=0)


def test_story_active_zone_and_corruption_raise(geo_cur: Any) -> None:
    geo_cur.execute("INSERT INTO places (id, zone) VALUES (5, 42)")
    geo_cur.execute("INSERT INTO characters (id, current_location) VALUES (7, 5)")
    geo_cur.execute(
        "INSERT INTO global_variables (id, user_character) VALUES (true, 7)"
    )
    assert story_active_zone(geo_cur) == 42

    geo_cur.execute("UPDATE characters SET current_location = NULL WHERE id = 7")
    with pytest.raises(ValueError, match="no current zoned place"):
        story_active_zone(geo_cur)
