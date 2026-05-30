"""Add routine anchors for home/work schedule behavior.

Orrery's first work package treated workplace-like places as sufficient
evidence that any actor standing there had work to do. Routine anchors make the
missing fact explicit: some characters have a home anchor, some have a work
anchor, some have neither, and special cases can collapse or avoid those
anchors without inventing generic jobs for everyone.
"""

from __future__ import annotations

from typing import Sequence

from psycopg2 import sql
from psycopg2.extensions import connection


ROUTINE_ANCHOR_TYPES: Sequence[str] = ("home", "work")
ROUTINE_MOBILITY_POLICIES: Sequence[str] = (
    "fixed_place",
    "zone_resolved",
    "works_from_home",
    "nomadic",
    "none",
)


def run(conn: connection) -> None:
    """Create routine anchor enums and table."""

    _create_enum(conn, "orrery_routine_anchor_type", ROUTINE_ANCHOR_TYPES)
    _create_enum(
        conn,
        "orrery_routine_mobility_policy",
        ROUTINE_MOBILITY_POLICIES,
    )
    _create_routine_anchor_table(conn)


def _create_enum(conn: connection, type_name: str, values: Sequence[str]) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_type WHERE typname = %s", (type_name,))
        if cur.fetchone() is not None:
            return
        cur.execute(
            sql.SQL("CREATE TYPE {} AS ENUM ({})").format(
                sql.Identifier(type_name),
                sql.SQL(", ").join(sql.Literal(value) for value in values),
            )
        )
    conn.commit()


def _create_routine_anchor_table(conn: connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS character_routine_anchors (
                id bigserial PRIMARY KEY,
                character_entity_id bigint NOT NULL
                    REFERENCES entities(id) ON DELETE CASCADE,
                anchor_type orrery_routine_anchor_type NOT NULL,
                place_id bigint REFERENCES places(id) ON DELETE SET NULL,
                zone_id bigint REFERENCES zones(id) ON DELETE SET NULL,
                mobility_policy orrery_routine_mobility_policy
                    NOT NULL DEFAULT 'fixed_place',
                schedule jsonb NOT NULL DEFAULT '{}'::jsonb,
                source text NOT NULL DEFAULT 'manual',
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                UNIQUE (character_entity_id, anchor_type),
                CHECK (
                    (
                        mobility_policy = 'fixed_place'
                        AND place_id IS NOT NULL
                    )
                    OR (
                        mobility_policy = 'zone_resolved'
                        AND zone_id IS NOT NULL
                    )
                    OR (
                        mobility_policy IN (
                            'works_from_home',
                            'nomadic',
                            'none'
                        )
                        AND place_id IS NULL
                    )
                ),
                CHECK (
                    anchor_type = 'work'
                    OR mobility_policy <> 'works_from_home'
                )
            );
            CREATE INDEX IF NOT EXISTS ix_character_routine_anchors_type
                ON character_routine_anchors (anchor_type);
            CREATE INDEX IF NOT EXISTS ix_character_routine_anchors_place
                ON character_routine_anchors (place_id);
            CREATE INDEX IF NOT EXISTS ix_character_routine_anchors_zone
                ON character_routine_anchors (zone_id);
            """
        )
        cur.execute(
            """
            COMMENT ON TABLE character_routine_anchors IS
                'Home/work schedule anchors for ordinary off-screen routines.
                Anchors are explicit actor facts, not inferred from the class of
                the place the actor currently occupies.';
            COMMENT ON COLUMN character_routine_anchors.anchor_type IS
                'Routine kind. MVP values are home and work.';
            COMMENT ON COLUMN character_routine_anchors.place_id IS
                'Concrete place target when the routine has a known place.';
            COMMENT ON COLUMN character_routine_anchors.zone_id IS
                'Coarse zone target for routines that can hydrate a concrete
                place later.';
            COMMENT ON COLUMN character_routine_anchors.mobility_policy IS
                'How Orrery interprets the anchor: concrete place, zone-only,
                work-from-home, nomadic, or intentionally absent.';
            COMMENT ON COLUMN character_routine_anchors.schedule IS
                'JSON schedule. Supported MVP shape: weekdays array, start
                HH:MM, end HH:MM. Weekdays use Python datetime.weekday()
                numbering: 0=Monday through 6=Sunday. Empty JSON means always
                due. Windows may cross midnight.';
            COMMENT ON COLUMN character_routine_anchors.source IS
                'Human/source provenance for the anchor.';
            """
        )
    conn.commit()
