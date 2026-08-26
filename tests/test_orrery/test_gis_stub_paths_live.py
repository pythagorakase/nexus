"""Live GIS tests for the three physical-place stub insertion paths."""

from __future__ import annotations

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
from tests.pg_fixtures import disposable_slot_database


pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def stub_cur() -> Iterator[Any]:
    """Yield a cursor backed by a canonical disposable slot image."""

    with disposable_slot_database("qa735_gis_stubs") as dbname:
        conn: Any = psycopg2.connect(dbname=dbname, user="pythagor")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE global_variables SET base_timestamp = %s WHERE id = true",
                    ("2100-01-01T00:00:00+00:00",),
                )
                assert cur.rowcount == 1
                cur.execute(
                    """
                    INSERT INTO layers (name)
                    VALUES ('GIS Stub Layer') RETURNING id
                    """
                )
                layer_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO zones (id, name, boundary, layer)
                    VALUES (
                        10,
                        'Story Zone',
                        ST_Multi(ST_MakeEnvelope(-2, -2, 2, 2, 4326)),
                        %s
                    ), (
                        20,
                        'Remote Zone',
                        ST_Multi(ST_MakeEnvelope(48, 48, 52, 52, 4326)),
                        %s
                    )
                    """,
                    (layer_id, layer_id),
                )
                cur.execute("INSERT INTO entities (kind) VALUES ('place') RETURNING id")
                place_entity_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO places (id, entity_id, name, type, zone)
                    VALUES (100, %s, 'Story Place', 'fixed_location', 10)
                    """,
                    (place_entity_id,),
                )
                cur.execute(
                    "INSERT INTO entities (kind) VALUES ('character') RETURNING id"
                )
                character_entity_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO characters (
                        id, name, summary, current_location, entity_id
                    ) VALUES (
                        1, 'GIS Stub Player', 'Canonical fixture player.', 100, %s
                    )
                    """,
                    (character_entity_id,),
                )
                cur.execute(
                    "UPDATE global_variables SET user_character = 1 WHERE id = true"
                )
                assert cur.rowcount == 1
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
