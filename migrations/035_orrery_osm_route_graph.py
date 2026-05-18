"""Add offline Orrery route-graph tables for OSM-derived routing."""

from __future__ import annotations

from psycopg2.extensions import connection


def run(conn: connection) -> None:
    """Create local route-graph tables used by Orrery travel starts."""

    _create_route_graph_tables(conn)
    _comment_schema(conn)


def _create_route_graph_tables(conn: connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE EXTENSION IF NOT EXISTS postgis;

            CREATE TABLE IF NOT EXISTS orrery_route_graph_nodes (
                id bigserial PRIMARY KEY,
                graph_key text NOT NULL DEFAULT 'default',
                node_key text NOT NULL,
                osm_node_id bigint,
                coordinates geometry(Point, 4326) NOT NULL,
                source text,
                metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                UNIQUE (graph_key, node_key)
            );

            CREATE INDEX IF NOT EXISTS ix_orrery_route_graph_nodes_graph_key
                ON orrery_route_graph_nodes (graph_key);
            CREATE INDEX IF NOT EXISTS ix_orrery_route_graph_nodes_coordinates
                ON orrery_route_graph_nodes USING GIST (coordinates);

            CREATE TABLE IF NOT EXISTS orrery_route_graph_edges (
                id bigserial PRIMARY KEY,
                graph_key text NOT NULL DEFAULT 'default',
                from_node_id bigint NOT NULL
                    REFERENCES orrery_route_graph_nodes(id) ON DELETE CASCADE,
                to_node_id bigint NOT NULL
                    REFERENCES orrery_route_graph_nodes(id) ON DELETE CASCADE,
                travel_mode orrery_travel_mode NOT NULL DEFAULT 'vehicle',
                risk orrery_travel_risk NOT NULL DEFAULT 'low',
                bidirectional boolean NOT NULL DEFAULT true,
                distance_m numeric NOT NULL CHECK (distance_m >= 0),
                duration_minutes numeric CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
                route_geometry geometry(LineString, 4326),
                source text,
                metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                CHECK (from_node_id <> to_node_id)
            );

            CREATE INDEX IF NOT EXISTS ix_orrery_route_graph_edges_graph_mode
                ON orrery_route_graph_edges (graph_key, travel_mode);
            CREATE INDEX IF NOT EXISTS ix_orrery_route_graph_edges_from
                ON orrery_route_graph_edges (from_node_id);
            CREATE INDEX IF NOT EXISTS ix_orrery_route_graph_edges_to
                ON orrery_route_graph_edges (to_node_id);
            CREATE INDEX IF NOT EXISTS ix_orrery_route_graph_edges_geometry
                ON orrery_route_graph_edges USING GIST (route_geometry);

            CREATE TABLE IF NOT EXISTS orrery_place_route_graph_nodes (
                place_id bigint NOT NULL REFERENCES places(id) ON DELETE CASCADE,
                graph_key text NOT NULL DEFAULT 'default',
                travel_mode orrery_travel_mode NOT NULL DEFAULT 'vehicle',
                node_id bigint NOT NULL
                    REFERENCES orrery_route_graph_nodes(id) ON DELETE CASCADE,
                distance_m numeric CHECK (distance_m IS NULL OR distance_m >= 0),
                source text,
                metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (place_id, graph_key, travel_mode)
            );

            CREATE INDEX IF NOT EXISTS ix_orrery_place_route_graph_nodes_node
                ON orrery_place_route_graph_nodes (node_id);
            """
        )
    conn.commit()


def _comment_schema(conn: connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            COMMENT ON TABLE orrery_route_graph_nodes IS
                'Offline OSM-derived graph nodes used by Orrery route computation.';
            COMMENT ON COLUMN orrery_route_graph_nodes.graph_key IS
                'Local graph namespace, such as default or a bounded regional OSM extract.';
            COMMENT ON COLUMN orrery_route_graph_nodes.node_key IS
                'Stable importer-facing node identifier inside one graph_key.';
            COMMENT ON COLUMN orrery_route_graph_nodes.osm_node_id IS
                'Optional original OpenStreetMap node id when the graph was derived from OSM.';
            COMMENT ON COLUMN orrery_route_graph_nodes.coordinates IS
                'WGS84 node point used for local debugging and future nearest-node matching.';

            COMMENT ON TABLE orrery_route_graph_edges IS
                'Mode-aware local graph edges used for offline Orrery route computation.';
            COMMENT ON COLUMN orrery_route_graph_edges.route_geometry IS
                'Optional OSM-derived path geometry for debugging or future route display.';
            COMMENT ON COLUMN orrery_route_graph_edges.duration_minutes IS
                'Optional precomputed traversal duration; Orrery falls back to mode speed when absent.';

            COMMENT ON TABLE orrery_place_route_graph_nodes IS
                'Explicit place-to-route-graph anchors so travel.start can route without external map APIs.';
            COMMENT ON COLUMN orrery_place_route_graph_nodes.travel_mode IS
                'Mode-specific anchor; mixed acts as a generic fallback for concrete travel modes.';
            """
        )
    conn.commit()
