"""Add scheduled-expiry substrate for Orrery entity tags."""

from __future__ import annotations


def run(conn) -> None:
    """Add ``expires_at_world_time`` and an index for expiry sweeps."""

    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE entity_tags
                ADD COLUMN IF NOT EXISTS expires_at_world_time timestamptz;

            COMMENT ON COLUMN entity_tags.expires_at_world_time IS
                'World-time deadline for scheduled tag expiry. NULL means the '
                'tag does not expire by elapsed world time.';

            CREATE INDEX IF NOT EXISTS ix_entity_tags_expiring
                ON entity_tags (expires_at_world_time)
                WHERE cleared_at IS NULL
                  AND expires_at_world_time IS NOT NULL;
            """
        )

    conn.commit()
