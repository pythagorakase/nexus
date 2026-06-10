"""Add explicit Retrograde provenance values for canonical writes."""

from __future__ import annotations

from psycopg2 import sql
from psycopg2.extensions import connection


RETROGRADE_SOURCE = "retrograde"


def run(conn: connection) -> None:
    """Allow Retrograde to stamp world events and tag rows distinctly."""

    _add_enum_value(conn, "event_source_kind", RETROGRADE_SOURCE)
    _add_enum_value(conn, "entity_tag_source_kind", RETROGRADE_SOURCE)


def _add_enum_value(conn: connection, type_name: str, value: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("ALTER TYPE {} ADD VALUE IF NOT EXISTS {}").format(
                sql.Identifier(type_name),
                sql.Literal(value),
            )
        )
    conn.commit()
