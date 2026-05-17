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

    _create_enum_types(conn)
    _create_travel_state_table(conn)
    _create_travel_edges_table(conn)
    _backfill_travel_states(conn)
    _seed_durable_tags(conn)
    _seed_place_affordance_tags(conn)
    _seed_event_types(conn)


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
                    status <> 'in_transit'
                    OR (origin_place_id IS NOT NULL AND destination_place_id IS NOT NULL)
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
