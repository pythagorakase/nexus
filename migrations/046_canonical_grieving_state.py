"""Canonicalize grief vocabulary around the ``grieving`` state tag."""

from __future__ import annotations


LEGACY_TAGS = ("bereaved", "grieving_recent_partner")


def run(conn) -> None:
    """Seed ``grieving`` and migrate legacy grief tags to the canonical row."""

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tags (
                tag, category, is_ephemeral,
                clearance_kind, reapplication_policy, clear_on,
                deprecated, description
            ) VALUES (
                'grieving', 'state', TRUE,
                'event',
                'extend_expiry'::entity_tag_reapplication_policy,
                '{"event_types": ["mourning_completed"]}'::jsonb,
                FALSE,
                'Actor is grieving a consequential loss. Long-lived; gates '
                'MOURN_LOSS and suppresses incompatible routine/social/intimacy '
                'branches until cleared by mourning_completed.'
            )
            ON CONFLICT (tag) DO UPDATE SET
                category = EXCLUDED.category,
                is_ephemeral = EXCLUDED.is_ephemeral,
                clearance_kind = EXCLUDED.clearance_kind,
                reapplication_policy = EXCLUDED.reapplication_policy,
                clear_on = EXCLUDED.clear_on,
                deprecated = FALSE,
                synonym_for = NULL,
                description = EXCLUDED.description
            RETURNING id
            """
        )
        canonical_id = cur.fetchone()[0]

        cur.execute(
            """
            SELECT id
            FROM tags
            WHERE tag = ANY(%s)
            """,
            (list(LEGACY_TAGS),),
        )
        legacy_ids = [row[0] for row in cur.fetchall()]

        for legacy_id in legacy_ids:
            cur.execute(
                """
                INSERT INTO entity_tags (
                    entity_id, tag_id, applied_at, applied_at_world_time,
                    clear_on_override, template_id, source_kind
                )
                SELECT et.entity_id,
                       %s,
                       et.applied_at,
                       et.applied_at_world_time,
                       et.clear_on_override,
                       et.template_id,
                       et.source_kind
                FROM entity_tags et
                WHERE et.tag_id = %s
                  AND et.cleared_at IS NULL
                ON CONFLICT (entity_id, tag_id)
                  WHERE cleared_at IS NULL
                  DO NOTHING
                """,
                (canonical_id, legacy_id),
            )
            cur.execute(
                """
                UPDATE entity_tags
                SET cleared_at = now()
                WHERE tag_id = %s
                  AND cleared_at IS NULL
                """,
                (legacy_id,),
            )

        cur.execute(
            """
            UPDATE tags
            SET deprecated = TRUE,
                synonym_for = %s,
                description = COALESCE(description, '')
                    || ' Deprecated alias of grieving.'
            WHERE tag = ANY(%s)
              AND id <> %s
            """,
            (canonical_id, list(LEGACY_TAGS), canonical_id),
        )

    conn.commit()
