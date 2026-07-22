"""Live GIS tests for the three physical-place stub insertion paths."""

from __future__ import annotations

import uuid
from typing import Any, Iterator

import psycopg2
import pytest

from nexus.agents.logon.apex_schema import NewEntityDeclaration
from nexus.agents.orrery.retrograde_maturation import (
    _apply_maturation_coordinates,
    _insert_declared_stub,
)
from nexus.agents.orrery.retrograde_persistence import (
    _insert_place_stub as insert_retrograde_place_stub,
)
from nexus.api.trait_compiler import _insert_place_stub as insert_trait_place_stub
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def stub_cur() -> Iterator[Any]:
    conn = psycopg2.connect(get_slot_db_url(slot=5))
    schema = f"gis_stubs_{uuid.uuid4().hex}"
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
                    id bigserial PRIMARY KEY,
                    entity_id bigserial NOT NULL,
                    name text NOT NULL,
                    type public.place_type NOT NULL,
                    zone bigint,
                    summary text,
                    current_status text,
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
                INSERT INTO global_variables (id, user_character)
                VALUES (true, 1)
                """
            )
            yield cur
    finally:
        conn.rollback()
        conn.close()


def _place_row(cur: Any, name: str) -> tuple[Any, ...]:
    cur.execute(
        """
        SELECT id,
               zone,
               ST_X(coordinates::geometry),
               ST_Y(coordinates::geometry)
        FROM places
        WHERE name = %s
        """,
        (name,),
    )
    return cur.fetchone()


def test_trait_compiler_place_stub_is_zoned(stub_cur: Any) -> None:
    insert_trait_place_stub(
        stub_cur,
        name="Trait Domain",
        trait="domain",
        role="domain",
    )

    assert _place_row(stub_cur, "Trait Domain")[1:] == (10, None, None)


def test_retrograde_persistence_place_stub_is_zoned(stub_cur: Any) -> None:
    insert_retrograde_place_stub(
        stub_cur,
        entity_ref="Retrograde Place",
        sources=["seed_1"],
    )

    assert _place_row(stub_cur, "Retrograde Place")[1:] == (10, None, None)


def test_declared_place_stub_uses_story_zone_without_coordinates(
    stub_cur: Any,
) -> None:
    _insert_declared_stub(
        stub_cur,
        NewEntityDeclaration(
            kind="place",
            name="Declared Place",
            summary="A location declared during play.",
        ),
    )

    assert _place_row(stub_cur, "Declared Place")[1:] == (10, None, None)


def test_declared_place_coordinates_persist_and_resolve(stub_cur: Any) -> None:
    _insert_declared_stub(
        stub_cur,
        NewEntityDeclaration(
            kind="place",
            name="Declared Remote Place",
            summary="A location with declaration-time GIS.",
            coordinates={"lat": 50, "lon": 50},
        ),
    )

    assert _place_row(stub_cur, "Declared Remote Place")[1:] == (
        20,
        50.0,
        50.0,
    )


def test_maturation_coordinates_rezone_stub(stub_cur: Any) -> None:
    _insert_declared_stub(
        stub_cur,
        NewEntityDeclaration(
            kind="place",
            name="Maturing Place",
            summary="A stub whose authored point belongs elsewhere.",
        ),
    )
    place_id = _place_row(stub_cur, "Maturing Place")[0]

    _apply_maturation_coordinates(
        stub_cur,
        row={"entity_kind": "place", "entity_subtype_id": place_id},
        expansion_payload={"coordinates": {"lat": 50, "lon": 50}},
    )

    assert _place_row(stub_cur, "Maturing Place")[1:] == (20, 50.0, 50.0)
