"""Add Orrery travel-state schema and Work/Travel vocabulary."""

from __future__ import annotations

from typing import Sequence

from psycopg2 import sql


TRAVEL_STATUS_VALUES: Sequence[str] = ("at_place", "planned", "in_transit")
TRAVEL_ROUTE_METHOD_VALUES: Sequence[str] = ("estimated", "authored_edge", "osm_graph")
TRAVEL_MODE_VALUES: Sequence[str] = (
    "walking",
    "vehicle",
    "rail",
    "water",
    "air",
    "covert",
    "mixed",
)
TRAVEL_RISK_VALUES: Sequence[str] = ("low", "moderate", "high", "extreme")


# (tag, category, description)
DURABLE_TAGS: Sequence[tuple[str, str, str]] = (
    (
        "work_obligation",
        "orrery_work",
        "Character carries routine livelihood, duty, or institutional work.",
    ),
    (
        "field_worker",
        "orrery_work",
        "Character's work often occurs away from a fixed shop or office.",
    ),
    (
        "route_familiar",
        "orrery_travel",
        "Character knows local routes well enough to travel efficiently.",
    ),
    (
        "travel_ready",
        "orrery_travel",
        "Character is prepared to begin or continue an ordinary journey.",
    ),
)


# (tag, description)
PLACE_AFFORDANCE_TAGS: Sequence[tuple[str, str]] = (
    (
        "workplace",
        "Place supports routine livelihood, duty, organizational, or service work.",
    ),
    (
        "worksite",
        "Place supports physical, field, maintenance, construction, or repair work.",
    ),
    (
        "administrative_office",
        "Place supports bureaucratic, clerical, planning, or institutional work.",
    ),
    (
        "transit_hub",
        "Place supports route departure, transfer, arrival, or travel logistics.",
    ),
)


# (event_type, category, severity, description)
EVENT_TYPES: Sequence[tuple[str, str, str, str]] = (
    ("travel_departed", "movement", "minor", "A character begins a journey."),
    (
        "travel_prepared",
        "movement",
        "minor",
        "A character prepares to begin a journey without departing yet.",
    ),
    (
        "travel_progressed",
        "movement",
        "minor",
        "A character advances along an off-screen route.",
    ),
    (
        "travel_delayed",
        "movement",
        "minor",
        "A character loses time or pauses while traveling.",
    ),
    (
        "travel_arrived",
        "movement",
        "minor",
        "A character arrives at a planned destination.",
    ),
    (
        "work_performed",
        "livelihood",
        "minor",
        "A character performs routine work or duty.",
    ),
    (
        "household_work_performed",
        "livelihood",
        "minor",
        "A character performs household labor or caretaking work.",
    ),
)


def run(conn) -> None:
    """Apply the Orrery Work/Travel schema and vocabulary migration."""

    _ensure_postgis(conn)
    _create_enum_types(conn)
    _create_travel_state_table(conn)
    _create_travel_edges_table(conn)
    _comment_schema(conn)
    _backfill_travel_states(conn)
    _seed_durable_tags(conn)
    _seed_place_affordance_tags(conn)
    _seed_event_types(conn)


def _ensure_postgis(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    conn.commit()


def _create_enum_types(conn) -> None:
    _create_enum(conn, "orrery_travel_status", TRAVEL_STATUS_VALUES)
    _create_enum(conn, "orrery_travel_route_method", TRAVEL_ROUTE_METHOD_VALUES)
    _create_enum(conn, "orrery_travel_mode", TRAVEL_MODE_VALUES)
    _create_enum(conn, "orrery_travel_risk", TRAVEL_RISK_VALUES)


def _create_enum(conn, type_name: str, values: Sequence[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_type WHERE typname = %s",
            (type_name,),
        )
        if cur.fetchone() is not None:
            return
        cur.execute(
            sql.SQL("CREATE TYPE {} AS ENUM ({})").format(
                sql.Identifier(type_name),
                sql.SQL(", ").join(sql.Literal(value) for value in values),
            )
        )
    conn.commit()


def _create_travel_state_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS character_travel_states (
                character_entity_id bigint PRIMARY KEY
                    REFERENCES entities(id) ON DELETE CASCADE,
                status orrery_travel_status NOT NULL DEFAULT 'at_place',
                anchor_place_id bigint REFERENCES places(id) ON DELETE SET NULL,
                origin_place_id bigint REFERENCES places(id) ON DELETE SET NULL,
                destination_place_id bigint REFERENCES places(id) ON DELETE SET NULL,
                route_method orrery_travel_route_method NOT NULL DEFAULT 'estimated',
                travel_mode orrery_travel_mode NOT NULL DEFAULT 'mixed',
                risk orrery_travel_risk NOT NULL DEFAULT 'low',
                progress_ratio numeric(5,4) NOT NULL DEFAULT 0,
                estimated_distance_m numeric,
                estimated_duration_minutes numeric,
                started_at_world_time timestamptz,
                updated_at_world_time timestamptz,
                eta_world_time timestamptz,
                route_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                CHECK (progress_ratio >= 0 AND progress_ratio <= 1),
                CHECK (
                    status <> 'at_place'
                    OR (origin_place_id IS NULL AND destination_place_id IS NULL)
                ),
                CHECK (
                    status <> 'planned'
                    OR destination_place_id IS NOT NULL
                ),
                CHECK (
                    status <> 'in_transit'
                    OR (
                        origin_place_id IS NOT NULL
                        AND destination_place_id IS NOT NULL
                    )
                )
            );
            CREATE INDEX IF NOT EXISTS ix_character_travel_states_status
                ON character_travel_states (status);
            CREATE INDEX IF NOT EXISTS ix_character_travel_states_destination
                ON character_travel_states (destination_place_id);
            """
        )
    conn.commit()


def _create_travel_edges_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orrery_travel_edges (
                id bigserial PRIMARY KEY,
                from_place_id bigint NOT NULL REFERENCES places(id) ON DELETE CASCADE,
                to_place_id bigint NOT NULL REFERENCES places(id) ON DELETE CASCADE,
                route_method orrery_travel_route_method NOT NULL DEFAULT 'authored_edge',
                travel_mode orrery_travel_mode NOT NULL DEFAULT 'mixed',
                risk orrery_travel_risk NOT NULL DEFAULT 'low',
                bidirectional boolean NOT NULL DEFAULT true,
                distance_m numeric,
                duration_minutes numeric,
                route_geometry geometry(LineString, 4326),
                source text,
                metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                CHECK (from_place_id <> to_place_id)
            );
            CREATE INDEX IF NOT EXISTS ix_orrery_travel_edges_from
                ON orrery_travel_edges (from_place_id);
            CREATE INDEX IF NOT EXISTS ix_orrery_travel_edges_to
                ON orrery_travel_edges (to_place_id);
            CREATE INDEX IF NOT EXISTS ix_orrery_travel_edges_method
                ON orrery_travel_edges (route_method);
            CREATE INDEX IF NOT EXISTS ix_orrery_travel_edges_geometry
                ON orrery_travel_edges USING GIST (route_geometry);
            CREATE UNIQUE INDEX IF NOT EXISTS ux_orrery_travel_edges_unique
                ON orrery_travel_edges (
                    from_place_id, to_place_id, travel_mode, route_method
                );
            """
        )
    conn.commit()


def _comment_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            COMMENT ON TABLE character_travel_states IS
                'Additive Orrery travel state for characters; preserves characters.current_location as a place anchor while tracking planned or in-transit movement.';
            COMMENT ON COLUMN character_travel_states.character_entity_id IS
                'Entity spine id for the character whose travel state this row describes.';
            COMMENT ON COLUMN character_travel_states.status IS
                'Travel lifecycle: at_place, planned, or in_transit.';
            COMMENT ON COLUMN character_travel_states.anchor_place_id IS
                'Readable place anchor used while not moving, and the last semantic place anchor while in transit.';
            COMMENT ON COLUMN character_travel_states.origin_place_id IS
                'Place where the current or planned journey begins; NULL when the character is simply at a place.';
            COMMENT ON COLUMN character_travel_states.destination_place_id IS
                'Place the character intends to reach; required for planned and in_transit rows.';
            COMMENT ON COLUMN character_travel_states.route_method IS
                'How the route was selected: coarse estimate now, authored_edge or osm_graph in later routing phases.';
            COMMENT ON COLUMN character_travel_states.travel_mode IS
                'Coarse travel mode used for route selection and duration estimates.';
            COMMENT ON COLUMN character_travel_states.risk IS
                'Coarse route risk for package gating and delay behavior.';
            COMMENT ON COLUMN character_travel_states.progress_ratio IS
                'Route completion ratio from 0.0 to 1.0; arrival resets it to zero.';
            COMMENT ON COLUMN character_travel_states.estimated_distance_m IS
                'Estimated route distance in meters for the selected route method, if known.';
            COMMENT ON COLUMN character_travel_states.estimated_duration_minutes IS
                'Estimated route duration in minutes for the selected route method, if known.';
            COMMENT ON COLUMN character_travel_states.started_at_world_time IS
                'World time when the current in-transit journey began.';
            COMMENT ON COLUMN character_travel_states.updated_at_world_time IS
                'Most recent world time at which Orrery updated this travel state.';
            COMMENT ON COLUMN character_travel_states.eta_world_time IS
                'Estimated world-time arrival for the current route, when duration is known.';
            COMMENT ON COLUMN character_travel_states.route_metadata IS
                'JSON metadata explaining route selection, fallback estimates, delay notes, and arrival history.';
            COMMENT ON COLUMN character_travel_states.created_at IS
                'Database timestamp when this travel state row was created.';
            COMMENT ON COLUMN character_travel_states.updated_at IS
                'Database timestamp when this travel state row was last updated.';

            COMMENT ON TABLE orrery_travel_edges IS
                'Optional authored or imported route edges between places for future Orrery routing phases.';
            COMMENT ON COLUMN orrery_travel_edges.id IS
                'Surrogate id for an authored or imported travel edge.';
            COMMENT ON COLUMN orrery_travel_edges.from_place_id IS
                'Origin place id for this route edge.';
            COMMENT ON COLUMN orrery_travel_edges.to_place_id IS
                'Destination place id for this route edge.';
            COMMENT ON COLUMN orrery_travel_edges.route_method IS
                'Route source/method represented by this edge, such as authored_edge or osm_graph.';
            COMMENT ON COLUMN orrery_travel_edges.travel_mode IS
                'Travel mode this edge supports.';
            COMMENT ON COLUMN orrery_travel_edges.risk IS
                'Default risk for traversing this edge.';
            COMMENT ON COLUMN orrery_travel_edges.bidirectional IS
                'Whether the route edge may be used in reverse.';
            COMMENT ON COLUMN orrery_travel_edges.distance_m IS
                'Route distance in meters for this edge, if known.';
            COMMENT ON COLUMN orrery_travel_edges.duration_minutes IS
                'Route duration in minutes for this edge, if known.';
            COMMENT ON COLUMN orrery_travel_edges.route_geometry IS
                'Optional PostGIS LineString geometry for debugging, authored pathing, or OSM-derived routes.';
            COMMENT ON COLUMN orrery_travel_edges.source IS
                'Human-readable route source such as author, import job, or dataset name.';
            COMMENT ON COLUMN orrery_travel_edges.metadata IS
                'JSON metadata for route provenance, constraints, and future routing/debug details.';
            COMMENT ON COLUMN orrery_travel_edges.created_at IS
                'Database timestamp when this travel edge was created.';
            COMMENT ON COLUMN orrery_travel_edges.updated_at IS
                'Database timestamp when this travel edge was last updated.';
            """
        )
    conn.commit()


def _backfill_travel_states(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO character_travel_states (
                character_entity_id,
                status,
                anchor_place_id,
                progress_ratio,
                route_metadata
            )
            SELECT c.entity_id,
                   'at_place'::orrery_travel_status,
                   c.current_location,
                   0,
                   jsonb_build_object('backfilled_from_current_location', true)
            FROM characters c
            JOIN entities e
              ON e.id = c.entity_id
             AND e.kind = 'character'
             AND e.is_active = true
            WHERE c.entity_id IS NOT NULL
              AND c.current_location IS NOT NULL
            ON CONFLICT (character_entity_id) DO NOTHING
            """
        )
    conn.commit()


def _seed_durable_tags(conn) -> None:
    with conn.cursor() as cur:
        for tag, category, description in DURABLE_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy,
                    clear_on, description
                ) VALUES (
                    %s, %s, FALSE,
                    NULL, NULL,
                    NULL, %s
                )
                ON CONFLICT (tag) DO NOTHING
                """,
                (tag, category, description),
            )
    conn.commit()


def _seed_place_affordance_tags(conn) -> None:
    with conn.cursor() as cur:
        for tag, description in PLACE_AFFORDANCE_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy,
                    clear_on, description
                ) VALUES (
                    %s, 'place_affordance', FALSE,
                    NULL, NULL,
                    NULL, %s
                )
                ON CONFLICT (tag) DO UPDATE SET
                    category = EXCLUDED.category,
                    is_ephemeral = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    reapplication_policy = EXCLUDED.reapplication_policy,
                    clear_on = EXCLUDED.clear_on,
                    description = EXCLUDED.description
                """,
                (tag, description),
            )
    conn.commit()


def _seed_event_types(conn) -> None:
    with conn.cursor() as cur:
        for event_type, category, severity, description in EVENT_TYPES:
            cur.execute(
                """
                INSERT INTO event_types (
                    type, category, severity, description
                ) VALUES (
                    %s, %s, %s::event_severity_kind, %s
                )
                ON CONFLICT (type) DO NOTHING
                """,
                (event_type, category, severity, description),
            )
    conn.commit()
