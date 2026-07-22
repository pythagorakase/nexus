"""Live throwaway-schema contract tests for the GIS CLI helpers."""

from __future__ import annotations

import uuid
from typing import Any, Iterator

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

from nexus.api.slot_utils import get_slot_db_url
from scripts.gis_backfill import (
    apply_backfill,
    format_dry_run,
    load_candidates,
    load_zone_assignments,
    main as backfill_main,
)
from scripts.gis_hygiene import audit_slot, format_slot_report


pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def script_conn() -> Iterator[Any]:
    conn = psycopg2.connect(
        get_slot_db_url(slot=5),
        cursor_factory=RealDictCursor,
    )
    schema = f"gis_scripts_{uuid.uuid4().hex}"
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(
                """
                CREATE TABLE zones (
                    id bigint PRIMARY KEY,
                    name text NOT NULL,
                    summary text,
                    boundary geometry(MultiPolygon, 4326)
                );
                CREATE TABLE places (
                    id bigint PRIMARY KEY,
                    name text NOT NULL,
                    summary text,
                    type public.place_type NOT NULL,
                    zone bigint,
                    coordinates geography(PointZM, 4326)
                );
                CREATE TABLE characters (
                    id bigint PRIMARY KEY,
                    name text NOT NULL,
                    current_location bigint,
                    extra_data jsonb
                );
                CREATE TABLE global_variables (
                    id boolean PRIMARY KEY,
                    user_character bigint
                );
                INSERT INTO zones (id, name, summary, boundary)
                VALUES (
                    10,
                    'Story Zone',
                    'The active story region.',
                    ST_Multi(ST_MakeEnvelope(-2, -2, 2, 2, 4326))
                ), (
                    20,
                    'Boundary Gap',
                    'A deliberately boundary-less audit row.',
                    NULL
                ), (
                    30,
                    'Far Zone',
                    'A remote region far from the protagonist.',
                    ST_Multi(ST_MakeEnvelope(48, 48, 52, 52, 4326))
                );
                INSERT INTO places (
                    id, name, summary, type, zone, coordinates
                ) VALUES (
                    100,
                    'Story Place',
                    'The protagonist location.',
                    'fixed_location',
                    10,
                    ST_SetSRID(ST_MakePoint(0, 0, 0, 0), 4326)::geography
                ), (
                    101,
                    'Missing Point',
                    'A physical place awaiting coordinates.',
                    'fixed_location',
                    NULL,
                    NULL
                ), (
                    102,
                    'Virtual Forum',
                    'A virtual place exempt from coordinates.',
                    'virtual',
                    NULL,
                    NULL
                ), (
                    103,
                    'Far Coordinated Place',
                    'A mapped physical place whose zone was lost.',
                    'fixed_location',
                    NULL,
                    ST_SetSRID(
                        ST_MakePoint(50, 50, 0, 0), 4326
                    )::geography
                );
                INSERT INTO characters (
                    id, name, current_location, extra_data
                ) VALUES (
                    1,
                    'Protagonist',
                    100,
                    '{"source": "wizard"}'::jsonb
                ), (
                    2,
                    'Placeless Witness',
                    NULL,
                    '{"source": "retrograde"}'::jsonb
                );
                INSERT INTO global_variables (id, user_character)
                VALUES (true, 1)
                """
            )
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
