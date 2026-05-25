"""Add time-based tag clearance mechanism for expiry sweeps."""

from __future__ import annotations

from psycopg2 import sql


def run(conn) -> None:
    """Allow ``tag_clearance_log.mechanism`` to record elapsed-time sweeps."""

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "ALTER TYPE entity_tag_clearance_kind ADD VALUE IF NOT EXISTS {}"
            ).format(sql.Literal("time"))
        )
    conn.commit()
