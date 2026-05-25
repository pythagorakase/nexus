"""Rename the active-targeting pair-tag from pursuing to hunting."""

from __future__ import annotations


HUNTING_DESCRIPTION = (
    "Subject is actively hunting the target. Ephemeral; also confers narrow "
    "targeted detection sensitivity for that target (see issue #282)."
)
PURSUING_REPLACEMENT_NOTE = (
    "Renamed to `hunting`: active intentional targeting without implying "
    "physical chase physics."
)
UNDER_ACTIVE_PURSUIT_REPLACEMENT_NOTE = (
    "Replaced by inbound `hunting` pair-tags; this single-entity signal could "
    "not identify who was hunting the character."
)


def run(conn) -> None:
    """Seed ``hunting`` and migrate any active ``pursuing`` edges to it."""

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pair_tags (
                tag, subject_kinds, object_kinds,
                is_ephemeral, clearance_kind, description, deprecated
            ) VALUES (
                'hunting',
                ARRAY['character', 'faction'],
                ARRAY['character'],
                TRUE,
                'semantic'::entity_tag_clearance_kind,
                %s,
                FALSE
            )
            ON CONFLICT (tag) DO UPDATE SET
                subject_kinds = EXCLUDED.subject_kinds,
                object_kinds = EXCLUDED.object_kinds,
                is_ephemeral = EXCLUDED.is_ephemeral,
                clearance_kind = EXCLUDED.clearance_kind,
                description = EXCLUDED.description,
                deprecated = FALSE
            """,
            (HUNTING_DESCRIPTION,),
        )

        cur.execute("SELECT id FROM pair_tags WHERE tag = 'hunting'")
        hunting_row = cur.fetchone()
        if hunting_row is None:
            raise RuntimeError("Failed to seed hunting pair_tag")
        hunting_id = hunting_row[0]

        cur.execute("SELECT id FROM pair_tags WHERE tag = 'pursuing'")
        pursuing_row = cur.fetchone()
        if pursuing_row is not None:
            pursuing_id = pursuing_row[0]
            cur.execute(
                """
                UPDATE entity_pair_tags old
                SET cleared_at = now()
                WHERE old.pair_tag_id = %s
                  AND old.cleared_at IS NULL
                  AND EXISTS (
                      SELECT 1
                      FROM entity_pair_tags existing
                      WHERE existing.subject_entity_id = old.subject_entity_id
                        AND existing.object_entity_id = old.object_entity_id
                        AND existing.pair_tag_id = %s
                        AND existing.cleared_at IS NULL
                  )
                """,
                (pursuing_id, hunting_id),
            )
            # This is a vocabulary rename, not a clearance event: historical
            # cleared rows should resolve through the canonical tag name too.
            # Active duplicates are cleared above before this FK retarget.
            cur.execute(
                """
                UPDATE entity_pair_tags
                SET pair_tag_id = %s
                WHERE pair_tag_id = %s
                """,
                (hunting_id, pursuing_id),
            )
            cur.execute(
                """
                UPDATE pair_tags
                SET deprecated = TRUE,
                    description = CASE
                        WHEN description IS NULL OR description = ''
                            THEN %s
                        WHEN description LIKE '%%Renamed to `hunting`%%'
                            THEN description
                        ELSE description || ' ' || %s
                    END
                WHERE tag = 'pursuing'
                """,
                (PURSUING_REPLACEMENT_NOTE, PURSUING_REPLACEMENT_NOTE),
            )

        cur.execute(
            """
            UPDATE tags
            SET deprecated = TRUE,
                description = CASE
                    WHEN description IS NULL OR description = ''
                        THEN %s
                    WHEN description LIKE '%%Replaced by inbound `hunting`%%'
                        THEN description
                    ELSE description || ' ' || %s
                END
            WHERE tag = 'under_active_pursuit'
            """,
            (
                UNDER_ACTIVE_PURSUIT_REPLACEMENT_NOTE,
                UNDER_ACTIVE_PURSUIT_REPLACEMENT_NOTE,
            ),
        )

    conn.commit()
