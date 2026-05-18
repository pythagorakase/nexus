#!/usr/bin/env python3
"""Import a small OSM-derived route graph for Orrery travel.

The importer expects pre-digested JSON rather than raw .osm.pbf data. Normal
Orrery ticks never call OSM, Google Maps, or an LLM; they only read the tables
this script populates.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json

from nexus.agents.orrery.routing import (
    DEFAULT_ROUTE_GRAPH_MAX_EDGES_PER_QUERY,
    ROUTE_GRAPH_MODES,
)

VALID_MODES = set(ROUTE_GRAPH_MODES)
VALID_RISKS = {"low", "moderate", "high", "extreme"}


def get_connection(dbname: str):
    """Open a PostgreSQL connection using the same defaults as migrations."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


def import_route_graph(
    conn: Any,
    payload: dict[str, Any],
    *,
    replace: bool,
    max_edges: int = DEFAULT_ROUTE_GRAPH_MAX_EDGES_PER_QUERY,
) -> None:
    """Import one preprocessed route graph payload."""

    graph_key = str(payload.get("graph_key") or "default")
    source = payload.get("source")
    nodes = payload.get("nodes") or []
    edges = payload.get("edges") or []
    place_nodes = payload.get("place_nodes") or []
    if not nodes:
        raise ValueError("Route graph payload requires at least one node")
    _validate_edge_count(edges, max_edges=max_edges, graph_key=graph_key)

    with conn.cursor() as cur:
        if replace:
            cur.execute(
                "DELETE FROM orrery_route_graph_nodes WHERE graph_key = %s",
                (graph_key,),
            )

        node_ids: dict[str, int] = {}
        for node in nodes:
            node_key = _required_text(node, "key")
            lat = float(node["lat"])
            lon = float(node["lon"])
            cur.execute(
                """
                INSERT INTO orrery_route_graph_nodes (
                    graph_key, node_key, osm_node_id, coordinates, source, metadata
                ) VALUES (
                    %s, %s, %s,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                    %s, %s::jsonb
                )
                ON CONFLICT (graph_key, node_key) DO UPDATE SET
                    osm_node_id = EXCLUDED.osm_node_id,
                    coordinates = EXCLUDED.coordinates,
                    source = EXCLUDED.source,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                RETURNING id
                """,
                (
                    graph_key,
                    node_key,
                    node.get("osm_node_id"),
                    lon,
                    lat,
                    node.get("source") or source,
                    Json(node.get("metadata") or {}),
                ),
            )
            node_ids[node_key] = cur.fetchone()[0]

        for edge in edges:
            mode = _mode(edge.get("mode") or edge.get("travel_mode") or "vehicle")
            risk = _risk(edge.get("risk") or "low")
            from_node_id = node_ids[_required_text(edge, "from")]
            to_node_id = node_ids[_required_text(edge, "to")]
            geometry = edge.get("geometry")
            geometry_str = json.dumps(geometry) if geometry is not None else None
            cur.execute(
                """
                INSERT INTO orrery_route_graph_edges (
                    graph_key, from_node_id, to_node_id, travel_mode, risk,
                    bidirectional, distance_m, duration_minutes, route_geometry,
                    source, metadata
                ) VALUES (
                    %s, %s, %s, %s::orrery_travel_mode, %s::orrery_travel_risk,
                    %s, %s, %s,
                    CASE WHEN %s IS NULL THEN NULL
                         ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                    END,
                    %s, %s::jsonb
                )
                """,
                (
                    graph_key,
                    from_node_id,
                    to_node_id,
                    mode,
                    risk,
                    bool(edge.get("bidirectional", True)),
                    float(edge["distance_m"]),
                    edge.get("duration_minutes"),
                    geometry_str,
                    geometry_str,
                    edge.get("source") or source,
                    Json(edge.get("metadata") or {}),
                ),
            )

        for anchor in place_nodes:
            mode = _mode(anchor.get("mode") or anchor.get("travel_mode") or "vehicle")
            node_id = node_ids[_required_text(anchor, "node")]
            cur.execute(
                """
                INSERT INTO orrery_place_route_graph_nodes (
                    place_id, graph_key, travel_mode, node_id,
                    distance_m, source, metadata
                ) VALUES (
                    %s, %s, %s::orrery_travel_mode, %s, %s, %s, %s::jsonb
                )
                ON CONFLICT (place_id, graph_key, travel_mode) DO UPDATE SET
                    node_id = EXCLUDED.node_id,
                    distance_m = EXCLUDED.distance_m,
                    source = EXCLUDED.source,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                (
                    int(anchor["place_id"]),
                    graph_key,
                    mode,
                    node_id,
                    anchor.get("distance_m"),
                    anchor.get("source") or source,
                    Json(anchor.get("metadata") or {}),
                ),
            )
    conn.commit()


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value in (None, ""):
        raise ValueError(f"Route graph item requires {key!r}")
    return str(value)


def _mode(value: str) -> str:
    mode = str(value)
    if mode not in VALID_MODES:
        supported = ", ".join(sorted(VALID_MODES))
        raise ValueError(
            f"Unsupported route graph travel mode: {mode!r}; "
            f"supported graph modes are: {supported}"
        )
    return mode


def _risk(value: str) -> str:
    risk = str(value)
    if risk not in VALID_RISKS:
        raise ValueError(f"Unsupported route graph risk: {risk!r}")
    return risk


def _validate_edge_count(
    edges: list[Any],
    *,
    max_edges: int,
    graph_key: str,
) -> None:
    if max_edges < 1:
        raise ValueError("Route graph max_edges must be at least 1")
    if len(edges) > max_edges:
        raise ValueError(
            f"Route graph {graph_key!r} has {len(edges)} edges, exceeding "
            f"the configured cap of {max_edges}; import a smaller bounded "
            "extract or raise the cap deliberately"
        )


def main() -> None:
    """Import one route graph JSON file from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", type=Path)
    parser.add_argument("--database", default="save_05")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing nodes/edges for the graph_key before importing.",
    )
    parser.add_argument(
        "--max-edges",
        type=int,
        default=DEFAULT_ROUTE_GRAPH_MAX_EDGES_PER_QUERY,
        help=(
            "Fail if the import contains more edges than this cap "
            f"(default: {DEFAULT_ROUTE_GRAPH_MAX_EDGES_PER_QUERY})."
        ),
    )
    args = parser.parse_args()

    payload = json.loads(args.json_path.read_text())
    conn = get_connection(args.database)
    try:
        import_route_graph(
            conn, payload, replace=args.replace, max_edges=args.max_edges
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
