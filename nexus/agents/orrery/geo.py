"""Shared GIS invariants for Orrery entity writers."""

from __future__ import annotations

from typing import Any


_ZONE_FOR_POINT_SQL = """
    WITH point AS (
        SELECT ST_SetSRID(ST_MakePoint({lon}, {lat}, 0, 0), 4326) AS geom
    )
    SELECT z.id
    FROM zones z
    CROSS JOIN point p
    WHERE z.boundary IS NOT NULL
    ORDER BY
        CASE WHEN ST_Covers(z.boundary, p.geom) THEN 0 ELSE 1 END,
        CASE
            WHEN ST_Covers(z.boundary, p.geom) THEN 0
            ELSE ST_Distance(z.boundary::geography, p.geom::geography)
        END,
        z.id
    LIMIT 1
"""

_STORY_ACTIVE_ZONE_SQL = """
    SELECT p.zone
    FROM global_variables gv
    JOIN characters c ON c.id = gv.user_character
    JOIN places p ON p.id = c.current_location
    WHERE gv.id = true
      AND p.zone IS NOT NULL
"""


def _row_value(row: Any) -> Any:
    """Return the first value from tuple- or mapping-shaped DB rows."""

    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    return row[0]


def resolve_zone_for_point(cur: Any, *, longitude: float, latitude: float) -> int:
    """Return the covering zone, or the nearest bounded zone.

    Covering wins because a zone boundary is the canonical spatial claim.
    Nearest is used only outside every boundary so authored real-Earth points
    remain located despite imperfect regional coverage. Zone id is the final
    tie-break, making identical geometries and equidistant boundaries stable.
    A slot with no bounded zone is corrupt and raises instead of inventing a
    fallback region.
    """

    cur.execute(
        _ZONE_FOR_POINT_SQL.format(lon="%s", lat="%s"),
        (longitude, latitude),
    )
    zone_id = _row_value(cur.fetchone())
    if zone_id is None:
        raise ValueError("Cannot resolve GIS point: no zone has a boundary")
    return int(zone_id)


async def resolve_zone_for_point_async(
    conn: Any, *, longitude: float, latitude: float
) -> int:
    """Asyncpg counterpart to :func:`resolve_zone_for_point`."""

    zone_id = await conn.fetchval(
        _ZONE_FOR_POINT_SQL.format(lon="$1", lat="$2"),
        longitude,
        latitude,
    )
    if zone_id is None:
        raise ValueError("Cannot resolve GIS point: no zone has a boundary")
    return int(zone_id)


def story_active_zone(cur: Any) -> int:
    """Return the protagonist's current place zone, raising on corruption."""

    cur.execute(_STORY_ACTIVE_ZONE_SQL)
    zone_id = _row_value(cur.fetchone())
    if zone_id is None:
        raise ValueError(
            "Cannot locate new entity: protagonist has no current zoned place"
        )
    return int(zone_id)


async def story_active_zone_async(conn: Any) -> int:
    """Asyncpg counterpart to :func:`story_active_zone`."""

    zone_id = await conn.fetchval(_STORY_ACTIVE_ZONE_SQL)
    if zone_id is None:
        raise ValueError(
            "Cannot locate new entity: protagonist has no current zoned place"
        )
    return int(zone_id)
