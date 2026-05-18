"""Reconcile baseline Orrery vocabulary drift across slots."""

from __future__ import annotations

from typing import Sequence

from psycopg2.extensions import connection


# (tag, category, description)
DURABLE_TAGS: Sequence[tuple[str, str, str]] = (
    (
        "intimate_services_contact",
        "orrery_intimacy_context",
        "Character has contacts at an intimate services establishment.",
    ),
    (
        "kin_protector",
        "disposition",
        "Character has strong protective instincts toward relational kin.",
    ),
)


def run(conn: connection) -> None:
    """Upsert baseline tags that drifted between template and fresh slots."""

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
                ON CONFLICT (tag) DO UPDATE SET
                    category = EXCLUDED.category,
                    is_ephemeral = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    reapplication_policy = EXCLUDED.reapplication_policy,
                    clear_on = EXCLUDED.clear_on,
                    description = EXCLUDED.description
                """,
                (tag, category, description),
            )
    conn.commit()
