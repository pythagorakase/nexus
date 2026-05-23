"""Seed trait-compiler substrate vocabulary and audit storage."""

from __future__ import annotations

from typing import Sequence


ROLE_CATEGORIES: Sequence[tuple[str, int, str]] = (
    (
        "role.resources",
        30,
        "Exclusive character wealth/resource tier used by the Resources trait.",
    ),
    (
        "role.fame",
        40,
        "Exclusive ambient recognition radius used by the Fame trait.",
    ),
)


ROLE_TAGS: Sequence[tuple[str, str, str]] = (
    ("destitute", "role.resources", "Resource tier: destitute."),
    ("poor", "role.resources", "Resource tier: poor."),
    ("comfortable", "role.resources", "Resource tier: comfortable/default."),
    ("wealthy", "role.resources", "Resource tier: wealthy."),
    ("magnate", "role.resources", "Resource tier: magnate."),
    ("obscure", "role.fame", "Fame tier: obscure/default."),
    ("known", "role.fame", "Fame tier: known."),
    ("renowned", "role.fame", "Fame tier: renowned."),
    ("legendary", "role.fame", "Fame tier: legendary."),
)


PAIR_TAGS: Sequence[tuple[str, list[str], list[str], bool, str]] = (
    (
        "ally",
        ["character"],
        ["character"],
        False,
        "Affective relationship gate: willing to help and take risks.",
    ),
    (
        "contact",
        ["character"],
        ["character"],
        False,
        "Affective relationship gate: information/favor pipeline.",
    ),
    (
        "hostile_to",
        ["character", "faction"],
        ["character", "faction"],
        False,
        "Durable active opposition distinct from acute pursuit.",
    ),
)


STATUS_PAIR_TAGS: Sequence[tuple[str, list[str], list[str], bool, str]] = tuple(
    (
        f"status:{level}",
        ["character", "faction"],
        ["faction"],
        False,
        f"Scope-bound status level: {level}.",
    )
    for level in (
        "junior",
        "senior",
        "executive",
        "sovereign",
        "respected",
        "elite",
        "outcast",
        "pariah",
        "enslaved",
    )
)


def run(conn) -> None:
    """Apply trait-compiler substrate changes."""

    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE IF EXISTS assets.new_story_creator
            ADD COLUMN IF NOT EXISTS trait_compile_result jsonb
            """
        )
        cur.execute(
            """
            COMMENT ON COLUMN assets.new_story_creator.trait_compile_result IS
                'Dry-run or final trait compiler audit result for debugging.';
            """
        )

        for category, prompt_order, description in ROLE_CATEGORIES:
            cur.execute(
                """
                INSERT INTO tag_category_registry (
                    category, entity_kind, prompt_order, description,
                    deprecated, replacement_categories
                ) VALUES (
                    %s, 'character'::entity_kind, %s, %s,
                    FALSE, NULL
                )
                ON CONFLICT (category, entity_kind) DO UPDATE SET
                    prompt_order = EXCLUDED.prompt_order,
                    description = EXCLUDED.description,
                    deprecated = FALSE,
                    replacement_categories = NULL
                """,
                (category, prompt_order, description),
            )

        for tag, category, description in ROLE_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy,
                    clear_on, deprecated, description
                ) VALUES (
                    %s, %s, FALSE,
                    NULL, NULL,
                    NULL, FALSE, %s
                )
                ON CONFLICT (tag) DO UPDATE SET
                    category = EXCLUDED.category,
                    is_ephemeral = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    reapplication_policy = EXCLUDED.reapplication_policy,
                    clear_on = EXCLUDED.clear_on,
                    deprecated = FALSE,
                    description = EXCLUDED.description
                """,
                (tag, category, description),
            )

        for tag, subject_kinds, object_kinds, is_ephemeral, description in (
            PAIR_TAGS + STATUS_PAIR_TAGS
        ):
            cur.execute(
                """
                INSERT INTO pair_tags (
                    tag, subject_kinds, object_kinds,
                    is_ephemeral, clearance_kind, description, deprecated
                ) VALUES (
                    %s, %s, %s,
                    %s, NULL, %s, FALSE
                )
                ON CONFLICT (tag) DO UPDATE SET
                    subject_kinds = EXCLUDED.subject_kinds,
                    object_kinds = EXCLUDED.object_kinds,
                    is_ephemeral = EXCLUDED.is_ephemeral,
                    clearance_kind = EXCLUDED.clearance_kind,
                    description = EXCLUDED.description,
                    deprecated = FALSE
                """,
                (tag, subject_kinds, object_kinds, is_ephemeral, description),
            )

        cur.execute(
            """
            UPDATE pair_tags
            SET subject_kinds = ARRAY['character', 'faction']
            WHERE tag = 'claims'
            """
        )

        cur.execute(
            """
            UPDATE assets.traits
            SET name = 'fame'
            WHERE id = 6
              AND name = 'reputation'
            """
        )

    conn.commit()
