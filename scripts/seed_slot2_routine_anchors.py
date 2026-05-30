#!/usr/bin/env python3
"""Seed Slot 2 reference routine anchors for Cam and Celia.

This is intentionally narrow test-slot data: Cam and Celia are boring-citizen
fixtures for Orrery's home/work cycle. The script is idempotent and does not
move characters; it only records routine anchors and home residence pair-tags.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import psycopg2
from psycopg2.extensions import connection
from psycopg2.extras import Json

from nexus.agents.orrery.tag_writer import apply_pair_tag_bestowal


WORK_SCHEDULE = {"weekdays": [0, 1, 2, 3, 4], "start": "09:00", "end": "17:00"}
HOME_SCHEDULE = {"start": "17:00", "end": "08:30"}

ROUTINES = (
    {
        "character": "Cam",
        "work_place": "Bougie Mall High-End Fashion Outlet",
        "home_place": "Coastal Safehouse",
    },
    {
        "character": "Celia",
        "work_place": "Low Tide",
        "home_place": "Back-Alley Hacker Den",
    },
)


def _connect(slot: int) -> connection:
    return psycopg2.connect(
        dbname=f"save_{slot:02d}",
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


def _character(cur: Any, name: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id, entity_id, name
        FROM characters
        WHERE name = %s
        """,
        (name,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Character not found: {name!r}")
    return {"id": row[0], "entity_id": row[1], "name": row[2]}


def _place(cur: Any, name: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id, entity_id, name, zone
        FROM places
        WHERE name = %s
        """,
        (name,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Place not found: {name!r}")
    return {"id": row[0], "entity_id": row[1], "name": row[2], "zone_id": row[3]}


def _upsert_anchor(
    cur: Any,
    *,
    character_entity_id: int,
    anchor_type: str,
    place_id: int,
    zone_id: int | None,
    schedule: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO character_routine_anchors (
            character_entity_id, anchor_type, place_id, zone_id,
            mobility_policy, schedule, source
        ) VALUES (
            %s, %s::orrery_routine_anchor_type, %s, %s,
            'fixed_place', %s::jsonb, 'slot2_reference_seed'
        )
        ON CONFLICT (character_entity_id, anchor_type) DO UPDATE SET
            place_id = EXCLUDED.place_id,
            zone_id = EXCLUDED.zone_id,
            mobility_policy = EXCLUDED.mobility_policy,
            schedule = EXCLUDED.schedule,
            source = EXCLUDED.source,
            updated_at = now()
        """,
        (
            character_entity_id,
            anchor_type,
            place_id,
            zone_id,
            Json(schedule),
        ),
    )


def seed(slot: int) -> dict[str, Any]:
    """Seed routine fixtures and return a summary."""

    summary: list[dict[str, Any]] = []
    with _connect(slot) as conn:
        with conn.cursor() as cur:
            for item in ROUTINES:
                character = _character(cur, item["character"])
                work_place = _place(cur, item["work_place"])
                home_place = _place(cur, item["home_place"])
                _upsert_anchor(
                    cur,
                    character_entity_id=character["entity_id"],
                    anchor_type="work",
                    place_id=work_place["id"],
                    zone_id=work_place["zone_id"],
                    schedule=WORK_SCHEDULE,
                )
                _upsert_anchor(
                    cur,
                    character_entity_id=character["entity_id"],
                    anchor_type="home",
                    place_id=home_place["id"],
                    zone_id=home_place["zone_id"],
                    schedule=HOME_SCHEDULE,
                )
                inserted_residence = apply_pair_tag_bestowal(
                    cur,
                    subject_entity_id=character["entity_id"],
                    object_entity_id=home_place["entity_id"],
                    tag="resides_at",
                    subject_kind="character",
                    object_kind="place",
                    source_kind="authored",
                )
                summary.append(
                    {
                        "character": character["name"],
                        "entity_id": character["entity_id"],
                        "work_place": work_place["name"],
                        "home_place": home_place["name"],
                        "inserted_residence": inserted_residence,
                    }
                )
    return {"slot": slot, "routines": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(seed(args.slot), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
