"""Persist protagonist Orrery tags through the normalized wizard cache."""

from __future__ import annotations

from psycopg2.extensions import connection


def run(conn: connection) -> None:
    """Add a JSONB cache column for wildcard-time protagonist tag bestowal."""

    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE IF EXISTS assets.new_story_creator
                ADD COLUMN IF NOT EXISTS character_orrery_tags jsonb;
            COMMENT ON COLUMN assets.new_story_creator.character_orrery_tags IS
                'OrreryTagBestowal JSON captured during protagonist wildcard creation.';
            """
        )
    conn.commit()
