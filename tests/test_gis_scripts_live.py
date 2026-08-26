"""Live throwaway-schema contract tests for the GIS CLI helpers."""

from __future__ import annotations

from typing import Any, Iterator

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

from scripts.gis_backfill import (
    apply_backfill,
    format_dry_run,
    load_candidates,
    load_zone_assignments,
    main as backfill_main,
)
from scripts.gis_hygiene import audit_slot, format_slot_report
from tests.pg_fixtures import disposable_slot_database


pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def script_conn() -> Iterator[Any]:
    """Yield a canonical disposable slot seeded for GIS script coverage."""

    with disposable_slot_database("qa735_gis_scripts") as dbname:
        conn: Any = psycopg2.connect(
            dbname=dbname,
            user="pythagor",
            cursor_factory=RealDictCursor,
        )
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
                    VALUES ('GIS Script Layer') RETURNING id
                    """
                )
                layer_id = int(cur.fetchone()["id"])
                cur.execute(
                    """
                    INSERT INTO zones (id, name, summary, boundary, layer)
                    VALUES (
                        10,
                        'Story Zone',
                        'The active story region.',
                        ST_Multi(ST_MakeEnvelope(-2, -2, 2, 2, 4326)),
                        %s
                    ), (
                        20,
                        'Boundary Gap',
                        'A deliberately boundary-less audit row.',
                        NULL,
                        %s
                    ), (
                        30,
                        'Far Zone',
                        'A remote region far from the protagonist.',
                        ST_Multi(ST_MakeEnvelope(48, 48, 52, 52, 4326)),
                        %s
                    )
                    """,
                    (layer_id, layer_id, layer_id),
                )
                place_entity_ids: list[int] = []
                for _index in range(4):
                    cur.execute(
                        "INSERT INTO entities (kind) VALUES ('place') RETURNING id"
                    )
                    place_entity_ids.append(int(cur.fetchone()["id"]))
                cur.execute(
                    """
                    INSERT INTO places (
                        id, entity_id, name, summary, type, zone, coordinates
                    ) VALUES (
                        100,
                        %s,
                        'Story Place',
                        'The protagonist location.',
                        'fixed_location',
                        10,
                        ST_SetSRID(ST_MakePoint(0, 0, 0, 0), 4326)::geography
                    ), (
                        101,
                        %s,
                        'Missing Point',
                        'A physical place awaiting coordinates.',
                        'fixed_location',
                        NULL,
                        NULL
                    ), (
                        102,
                        %s,
                        'Virtual Forum',
                        'A virtual place exempt from coordinates.',
                        'virtual',
                        NULL,
                        NULL
                    ), (
                        103,
                        %s,
                        'Far Coordinated Place',
                        'A mapped physical place whose zone was lost.',
                        'fixed_location',
                        NULL,
                        ST_SetSRID(
                            ST_MakePoint(50, 50, 0, 0), 4326
                        )::geography
                    )
                    """,
                    tuple(place_entity_ids),
                )
                character_entity_ids: list[int] = []
                for _index in range(2):
                    cur.execute(
                        "INSERT INTO entities (kind) "
                        "VALUES ('character') RETURNING id"
                    )
                    character_entity_ids.append(int(cur.fetchone()["id"]))
                cur.execute(
                    """
                    INSERT INTO characters (
                        id, name, current_location, extra_data, entity_id
                    ) VALUES (
                        1,
                        'Protagonist',
                        100,
                        '{"source": "wizard"}'::jsonb,
                        %s
                    ), (
                        2,
                        'Placeless Witness',
                        NULL,
                        '{"source": "retrograde"}'::jsonb,
                        %s
                    )
                    """,
                    tuple(character_entity_ids),
                )
                cur.execute(
                    "UPDATE global_variables SET user_character = 1 WHERE id = true"
                )
                assert cur.rowcount == 1
            yield conn
        finally:
            conn.rollback()
            conn.close()


def test_gis_hygiene_plain_table_output_contract(script_conn: Any) -> None:
    categories = audit_slot(script_conn)
    report = format_slot_report(5, categories)

    assert "Placeless characters (1)" in report
    assert "Placeless Witness | retrograde" in report
    assert "Unlocated non-virtual places (1)" in report
    assert "Missing Point" in report
    assert "Zone-less places (3)" in report
    assert "Virtual Forum" in report
    assert "Far Coordinated Place" in report
    assert "Boundary-less zones (1)" in report
    assert "20 | Boundary Gap" in report


def test_gis_backfill_dry_run_plan_is_pure(script_conn: Any) -> None:
    with script_conn.cursor() as cur:
        assignments = load_zone_assignments(cur)
        candidates = load_candidates(cur)
    report = format_dry_run(5, candidates, assignments)

    assert len(candidates) == 2
    assert len(assignments) == 2
    missing_point = next(row for row in candidates if row.place_id == 101)
    coordinated = next(row for row in candidates if row.place_id == 103)
    assert missing_point.zone_id == 10
    assert missing_point.needs_zone_write is True
    assert coordinated.zone_id == 30
    assert coordinated.needs_coordinate_authoring is False
    assert "coordinates: MODEL_CALL_ON_APPLY" in report
    assert "coordinates: EXISTING_POINT_GEOMETRY" in report
    assert "Virtual Forum (virtual) | assign story zone 10" in report
    with script_conn.cursor() as cur:
        cur.execute("SELECT zone, coordinates FROM places WHERE id = 101")
        row = cur.fetchone()
    assert row == {"zone": None, "coordinates": None}


def test_gis_backfill_resolves_existing_point_without_model_call(
    script_conn: Any,
    monkeypatch: Any,
) -> None:
    with script_conn.cursor() as cur:
        candidate = next(row for row in load_candidates(cur) if row.place_id == 103)
        monkeypatch.setattr(
            "scripts.gis_backfill.author_place_coordinates",
            lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("existing coordinates must not call the model")
            ),
        )
        apply_backfill(
            cur,
            candidates=[candidate],
            zone_assignments=[],
            model="unused",
            max_tokens=1,
        )
        cur.execute("SELECT zone FROM places WHERE id = 103")
        row = cur.fetchone()

    assert row == {"zone": 30}


def test_gis_backfill_refuses_frozen_slots(capsys: Any) -> None:
    assert backfill_main(["--slot", "1", "--apply"]) == 2
    assert "REFUSED: slot 1" in capsys.readouterr().out
