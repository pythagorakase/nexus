"""Seed Orrery semantic place-affordance vocabulary."""

from __future__ import annotations

from typing import Sequence

from psycopg2.extensions import connection


# (tag, description)
PLACE_AFFORDANCE_TAGS: Sequence[tuple[str, str]] = (
    (
        "the_roots",
        "Place belongs to or behaves like the Roots: underground, "
        "infrastructural, hidden, or half-maintained transit space.",
    ),
    (
        "the_glow",
        "Place belongs to or behaves like the Glow: dense public urban space "
        "where ordinary cover work can blend into civilian flow.",
    ),
    (
        "place_of_remembrance",
        "Place supports mourning, memorial ritual, grave-tending, or other "
        "structured remembrance of the dead.",
    ),
    (
        "neutral_ground",
        "Place can plausibly host tense meetings without clearly favoring "
        "one participant's territory.",
    ),
    ("home", "Place is a character's familiar home or household shelter."),
    (
        "lodgings",
        "Place offers temporary lodging, rented rooms, guest quarters, or "
        "other ordinary sleep shelter.",
    ),
    (
        "safe_house",
        "Place can shelter a character discreetly and securely enough for "
        "off-screen recovery or hiding.",
    ),
    (
        "tavern",
        "Place provides public food, drink, and informal social contact.",
    ),
    (
        "teahouse",
        "Place provides public drink and quiet social ritual.",
    ),
    (
        "cafe",
        "Place provides public drink, light food, and low-stakes presence.",
    ),
    (
        "market",
        "Place can provide food, drink, goods, and public crowd cover.",
    ),
    (
        "public_water",
        "Place has an accessible water source for routine or urgent drinking.",
    ),
    (
        "wilderness",
        "Place is uncultivated or rural enough to support rough travel, "
        "foraging, hunting, or wild water sources.",
    ),
    (
        "restaurant",
        "Place primarily provides prepared public meals.",
    ),
    (
        "cookshop",
        "Place sells prepared food without necessarily being a full restaurant.",
    ),
)


def run(conn: connection) -> None:
    """Apply the place-affordance vocabulary migration."""

    with conn.cursor() as cur:
        for tag, description in PLACE_AFFORDANCE_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy,
                    clear_on, description
                ) VALUES (
                    %s, 'place_affordance', FALSE,
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
                (tag, description),
            )
        cur.execute(
            """
            SELECT tag, category
            FROM tags
            WHERE tag = ANY(%s)
              AND category <> 'place_affordance'
            ORDER BY tag
            """,
            ([tag for tag, _description in PLACE_AFFORDANCE_TAGS],),
        )
        mismatches = cur.fetchall()
        if mismatches:
            detail = ", ".join(f"{tag}={category}" for tag, category in mismatches)
            message = f"Unexpected Orrery place-affordance categories: {detail}"
            raise RuntimeError(message)
    conn.commit()
