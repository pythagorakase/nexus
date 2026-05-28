"""Retire defaults that create new legacy faction semantic data."""

from __future__ import annotations


def run(conn) -> None:
    """Stop omitted faction inserts from backfilling legacy power_level."""

    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE factions
                ALTER COLUMN power_level DROP DEFAULT;

            COMMENT ON COLUMN factions.power_level IS
                'Legacy faction-strength column retained for staged migration. '
                'New runtime writers should use Orrery power_status tags instead.';
            """
        )

    conn.commit()
