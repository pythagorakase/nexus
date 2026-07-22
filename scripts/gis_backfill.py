#!/usr/bin/env python3
"""Author missing physical-place coordinates for one mutable save slot."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.geo import resolve_zone_for_point, story_active_zone
from nexus.agents.orrery.geo_authoring import author_place_coordinates
from nexus.api.slot_utils import all_slots, get_slot_db_url
from nexus.config import load_settings


FROZEN_SLOTS = frozenset({1, 2})


@dataclass(frozen=True)
class BackfillCandidate:
    """One physical place needing a model-authored point."""

    place_id: int
    name: str
    summary: str | None
    zone_id: int
    zone_name: str
    zone_summary: str | None
    needs_zone_write: bool


@dataclass(frozen=True)
class ZoneAssignment:
    """One zone-less place that must inherit the story-active zone."""

    place_id: int
    name: str
    place_type: str
    zone_id: int


def load_zone_assignments(cur: Any) -> list[ZoneAssignment]:
    """Plan story-zone writes for zone-less places of every type."""

    cur.execute(
        """
        SELECT id, name, type::text AS type
        FROM places
        WHERE zone IS NULL
        ORDER BY id
        """
    )
    places = cur.fetchall()
    if not places:
        return []
    zone_id = story_active_zone(cur)
    return [
        ZoneAssignment(
            place_id=int(place["id"]),
            name=str(place["name"]),
            place_type=str(place["type"]),
            zone_id=zone_id,
        )
        for place in places
    ]


def load_candidates(cur: Any) -> list[BackfillCandidate]:
    """Read the pure backfill plan without model calls or writes."""

    cur.execute(
        """
        SELECT id, name, summary, zone
        FROM places
        WHERE type::text <> 'virtual'
          AND coordinates IS NULL
        ORDER BY id
        """
    )
    places = cur.fetchall()
    if not places:
        return []
    active_zone = story_active_zone(cur)
    candidates = []
    for place in places:
        place = dict(place)
        zone_id = int(place["zone"] or active_zone)
        cur.execute(
            "SELECT name, summary FROM zones WHERE id = %s",
            (zone_id,),
        )
        zone = cur.fetchone()
        if zone is None:
            raise ValueError(
                f"Place {place['name']!r} resolves to missing zone {zone_id}"
            )
        zone = dict(zone)
        candidates.append(
            BackfillCandidate(
                place_id=int(place["id"]),
                name=str(place["name"]),
                summary=place["summary"],
                zone_id=zone_id,
                zone_name=str(zone["name"]),
                zone_summary=zone["summary"],
                needs_zone_write=place["zone"] is None,
            )
        )
    return candidates


def format_dry_run(
    slot: int,
    candidates: Sequence[BackfillCandidate],
    zone_assignments: Sequence[ZoneAssignment] = (),
) -> str:
    """Render a deterministic plan; dry-run deliberately does no inference."""

    lines = [f"GIS BACKFILL DRY RUN — slot {slot}"]
    for assignment in zone_assignments:
        lines.append(
            f"place {assignment.place_id}: {assignment.name} "
            f"({assignment.place_type}) | assign story zone {assignment.zone_id}"
        )
    if not candidates:
        lines.append("No physical places need coordinates.")
        return "\n".join(lines)
    assignment_ids = {assignment.place_id for assignment in zone_assignments}
    for candidate in candidates:
        zone_note = (
            " + assign story zone"
            if candidate.needs_zone_write and candidate.place_id not in assignment_ids
            else ""
        )
        lines.append(
            f"place {candidate.place_id}: {candidate.name} | "
            f"zone {candidate.zone_id}: {candidate.zone_name}{zone_note} | "
            "coordinates: MODEL_CALL_ON_APPLY"
        )
    return "\n".join(lines)


def apply_backfill(
    cur: Any,
    *,
    candidates: Sequence[BackfillCandidate],
    zone_assignments: Sequence[ZoneAssignment],
    model: str,
    max_tokens: int,
) -> None:
    """Author and persist every planned coordinate, failing atomically."""

    for assignment in zone_assignments:
        cur.execute(
            "UPDATE places SET zone = %s WHERE id = %s AND zone IS NULL",
            (assignment.zone_id, assignment.place_id),
        )
        print(
            f"Assigned story zone {assignment.zone_id} to "
            f"{assignment.name} (id={assignment.place_id})"
        )

    for candidate in candidates:
        print(f"Authoring coordinates for {candidate.name} (id={candidate.place_id})")
        response = author_place_coordinates(
            model=model,
            max_tokens=max_tokens,
            place_name=candidate.name,
            place_summary=candidate.summary,
            zone_name=candidate.zone_name,
            zone_summary=candidate.zone_summary,
        )
        coordinates = response.coordinates
        zone_id = resolve_zone_for_point(
            cur,
            longitude=coordinates.lon,
            latitude=coordinates.lat,
        )
        cur.execute(
            """
            UPDATE places
            SET coordinates = ST_SetSRID(
                    ST_MakePoint(%s, %s, 0, 0), 4326
                )::geography,
                zone = %s
            WHERE id = %s
              AND coordinates IS NULL
            """,
            (coordinates.lon, coordinates.lat, zone_id, candidate.place_id),
        )
        print(
            f"  proposed ({coordinates.lat:.6f}, {coordinates.lon:.6f}); "
            f"resolved zone {zone_id}; updated {cur.rowcount} row"
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, choices=all_slots(), required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Plan or apply a GIS backfill for one non-golden slot."""

    args = build_parser().parse_args(argv)
    if args.slot in FROZEN_SLOTS:
        print(
            f"REFUSED: slot {args.slot} is frozen golden-master/evidence data; "
            "GIS backfill is forbidden."
        )
        return 2
    conn = psycopg2.connect(get_slot_db_url(slot=args.slot))
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            zone_assignments = load_zone_assignments(cur)
            candidates = load_candidates(cur)
            if not args.apply:
                print(format_dry_run(args.slot, candidates, zone_assignments))
                conn.rollback()
                return 0
            settings = load_settings()
            if settings.orrery is None:
                raise ValueError("[orrery] settings are required for GIS backfill")
            cfg = settings.orrery.retrograde.maturation
            apply_backfill(
                cur,
                candidates=candidates,
                zone_assignments=zone_assignments,
                model=cfg.model_ref,
                max_tokens=cfg.max_tokens,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"GIS backfill complete: {len(candidates)} place(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
