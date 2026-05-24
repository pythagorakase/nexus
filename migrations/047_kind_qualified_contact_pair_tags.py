"""Seed kind-qualified contact pair-tags and retire contact flags."""

from __future__ import annotations

from typing import Sequence


CONTACT_PAIR_TAGS: Sequence[tuple[str, str]] = (
    (
        "contact:lodging",
        "Subject can reach a contact who can provide lodging, shelter, "
        "or safe-house access.",
    ),
    (
        "contact:social",
        "Subject can reach a contact for ordinary social connection, favors, "
        "messages, or indirect channels.",
    ),
    (
        "contact:intimate",
        "Subject can reach a contact for contracted intimacy access "
        "where the setting supports it.",
    ),
)

LEGACY_CONTACT_TAGS: Sequence[tuple[str, str]] = (
    (
        "contacts_available",
        "Replaced by kind-qualified contact pair-tags: contact:lodging, "
        "contact:social, and contact:intimate.",
    ),
    (
        "intimate_services_contact",
        "Replaced by the contact:intimate pair-tag.",
    ),
)
LEGACY_CONTACT_PAIR_TAGS: Sequence[tuple[str, str]] = (
    (
        "contact",
        "Replaced by kind-qualified contact pair-tags: contact:lodging, "
        "contact:social, and contact:intimate.",
    ),
)


def run(conn) -> None:
    """Apply the issue #317 contact-kind vocabulary update."""

    with conn.cursor() as cur:
        for tag, description in CONTACT_PAIR_TAGS:
            cur.execute(
                """
                INSERT INTO pair_tags (
                    tag, subject_kinds, object_kinds,
                    is_ephemeral, clearance_kind, description, deprecated
                ) VALUES (
                    %s,
                    ARRAY['character'],
                    ARRAY['character'],
                    FALSE,
                    NULL,
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
                (tag, description),
            )

        for tag, replacement_note in LEGACY_CONTACT_TAGS:
            cur.execute(
                """
                UPDATE tags
                SET deprecated = TRUE,
                    description = CASE
                        WHEN description IS NULL OR description = ''
                            THEN %s
                        WHEN description LIKE '%%Replaced by%%'
                            THEN description
                        ELSE description || ' ' || %s
                    END
                WHERE tag = %s
                """,
                (replacement_note, replacement_note, tag),
            )

        for tag, replacement_note in LEGACY_CONTACT_PAIR_TAGS:
            cur.execute(
                """
                UPDATE pair_tags
                SET deprecated = TRUE,
                    description = CASE
                        WHEN description IS NULL OR description = ''
                            THEN %s
                        WHEN description LIKE '%%Replaced by%%'
                            THEN description
                        ELSE description || ' ' || %s
                    END
                WHERE tag = %s
                """,
                (replacement_note, replacement_note, tag),
            )

    conn.commit()
