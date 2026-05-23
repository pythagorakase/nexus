"""Phase 1 compatibility metadata for the Orrery category refactor.

The vocabulary design splits broad legacy categories such as
``place_affordance`` into narrower axes. This migration records that cutover
metadata and registers the new category names without rewriting existing tags
or entity_tags rows. Runtime compatibility is handled by the resolver shim
that hydrates old and new place categories into ``WorldState.location_classes``.
"""

from __future__ import annotations

from typing import Optional, Sequence

from psycopg2.extensions import connection


# (category, entity_kind, prompt_order, description)
NEW_CATEGORY_REGISTRY: Sequence[tuple[str, str, int, str]] = (
    (
        "place_function",
        "place",
        10,
        "Functional role a place serves for package gates.",
    ),
    (
        "place_visibility",
        "place",
        20,
        "Whether a place is broadly known or hidden.",
    ),
    (
        "place_access",
        "place",
        30,
        "Whether a place is open or restricted.",
    ),
    (
        "place_environment",
        "place",
        40,
        "Physical or geographic environment of a place.",
    ),
    (
        "place_threat",
        "place",
        50,
        "Current safety or danger posture of a place.",
    ),
    (
        "ideology",
        "faction",
        10,
        "Faction worldview, political, or metaphysical orientation.",
    ),
    (
        "power_status",
        "faction",
        20,
        "Current faction strength or momentum.",
    ),
    (
        "agenda",
        "faction",
        30,
        "Active faction goals, schemes, or pressure vectors.",
    ),
    (
        "resource_base",
        "faction",
        40,
        "Material, economic, institutional, or informational resources.",
    ),
    (
        "legitimacy",
        "faction",
        50,
        "Public, legal, or underworld legitimacy posture.",
    ),
    (
        "operational_mode",
        "faction",
        60,
        "Whether faction action is overt, covert, or hybrid.",
    ),
)

# (legacy_category, entity_kind, replacement_categories)
DEPRECATED_CATEGORY_REPLACEMENTS: Sequence[
    tuple[str, str, Optional[tuple[str, ...]]]
] = (
    (
        "place_affordance",
        "place",
        (
            "place_function",
            "place_visibility",
            "place_access",
            "place_environment",
            "place_threat",
        ),
    ),
    ("profession_lite", "character", ("role",)),
    ("orrery_signal", "character", ("state",)),
    ("ideology_axis", "faction", ("ideology",)),
    ("power_posture", "faction", ("power_status",)),
    ("legitimacy_status", "faction", ("legitimacy",)),
    ("operational_secrecy", "faction", ("operational_mode",)),
    ("resource_class", "faction", ("resource_base",)),
    ("hidden_agenda_class", "faction", ("agenda",)),
    ("history_class", "faction", None),
)


def run(conn: connection) -> None:
    """Register new categories and mark legacy categories as deprecated."""

    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE tag_category_registry
            ADD COLUMN IF NOT EXISTS deprecated boolean NOT NULL DEFAULT false
            """
        )
        cur.execute(
            """
            ALTER TABLE tag_category_registry
            ADD COLUMN IF NOT EXISTS replacement_categories text[]
            """
        )
        cur.execute(
            """
            COMMENT ON COLUMN tag_category_registry.deprecated IS
                'Category-level cutover marker; existing tag rows remain live '
                'until a data migration rewrites them.';
            """
        )
        cur.execute(
            """
            COMMENT ON COLUMN tag_category_registry.replacement_categories IS
                'Preferred successor categories for deprecated category rows, '
                'when any exist.';
            """
        )

        for category, entity_kind, prompt_order, description in NEW_CATEGORY_REGISTRY:
            cur.execute(
                """
                INSERT INTO tag_category_registry (
                    category, entity_kind, prompt_order, description,
                    deprecated, replacement_categories
                ) VALUES (
                    %s, %s::entity_kind, %s, %s,
                    FALSE, NULL
                )
                ON CONFLICT (category, entity_kind) DO UPDATE SET
                    prompt_order = EXCLUDED.prompt_order,
                    description = EXCLUDED.description,
                    deprecated = FALSE,
                    replacement_categories = NULL
                """,
                (category, entity_kind, prompt_order, description),
            )

        for (
            legacy_category,
            entity_kind,
            replacement_categories,
        ) in DEPRECATED_CATEGORY_REPLACEMENTS:
            cur.execute(
                """
                UPDATE tag_category_registry
                SET deprecated = TRUE,
                    replacement_categories = %s
                WHERE category = %s
                  AND entity_kind = %s::entity_kind
                """,
                (
                    list(replacement_categories) if replacement_categories else None,
                    legacy_category,
                    entity_kind,
                ),
            )
    conn.commit()
