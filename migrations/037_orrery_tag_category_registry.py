"""Add a registry for Orrery tag-category/entity-kind compatibility."""

from __future__ import annotations

from typing import Sequence

from psycopg2.extensions import connection


# (category, entity_kind, prompt_order, description)
CATEGORY_REGISTRY: Sequence[tuple[str, str, int, str]] = (
    (
        "bodyform",
        "character",
        10,
        "Embodiment or personhood form.",
    ),
    ("capacity", "character", 20, "Abilities, training, or usable skills."),
    (
        "disposition",
        "character",
        30,
        "Stable behavior tendencies or priority inclinations.",
    ),
    (
        "role",
        "character",
        40,
        "Social, professional, or household roles.",
    ),
    (
        "profession_lite",
        "character",
        50,
        "Lightweight occupations used by package gates.",
    ),
    (
        "state",
        "character",
        60,
        "Durable or ephemeral character state.",
    ),
    (
        "orrery_state",
        "character",
        70,
        "Orrery-specific readiness, identity, or signal state.",
    ),
    (
        "orrery_signal",
        "character",
        80,
        "Orrery-specific pressure signal.",
    ),
    (
        "orrery_need",
        "character",
        90,
        "Homeostatic need severity state.",
    ),
    (
        "orrery_need_modifier",
        "character",
        100,
        "Modifiers that alter need pressure.",
    ),
    (
        "orrery_schedule",
        "character",
        110,
        "Sleep, work, or routine schedule tendencies.",
    ),
    (
        "orrery_social_modulator",
        "character",
        120,
        "Social-need threshold modifiers.",
    ),
    (
        "orrery_intimacy_modulator",
        "character",
        130,
        "Intimacy-need threshold modifiers.",
    ),
    (
        "orrery_intimacy_context",
        "character",
        140,
        "Context that routes intimacy packages.",
    ),
    (
        "orrery_intimacy_suppressor",
        "character",
        150,
        "Context that suppresses intimacy packages.",
    ),
    (
        "orrery_travel",
        "character",
        160,
        "Travel readiness or route knowledge.",
    ),
    (
        "orrery_work",
        "character",
        170,
        "Routine work, duty, or livelihood state.",
    ),
    (
        "orrery_cover",
        "character",
        180,
        "Cover identities and routines.",
    ),
    (
        "orrery_concealment",
        "character",
        190,
        "Hidden, absent, wanted, or unrevealed status.",
    ),
    (
        "relationship_risk",
        "character",
        200,
        "Relationship context that changes package interpretation.",
    ),
    (
        "place_affordance",
        "place",
        10,
        "A functional affordance a place offers to packages.",
    ),
    (
        "ideology_axis",
        "faction",
        10,
        "Worldview, political, or metaphysical orientation.",
    ),
    (
        "power_posture",
        "faction",
        20,
        "How a faction projects power.",
    ),
    (
        "legitimacy_status",
        "faction",
        30,
        "Public, legal, or underworld legitimacy posture.",
    ),
    (
        "operational_secrecy",
        "faction",
        40,
        "Secrecy, compartmentalization, or exposure model.",
    ),
    (
        "resource_class",
        "faction",
        50,
        "Material, economic, or informational resource base.",
    ),
    (
        "hidden_agenda_class",
        "faction",
        60,
        "Covert agendas or internal threats.",
    ),
    (
        "history_class",
        "faction",
        70,
        "Institutional continuity, age, or origin.",
    ),
)


def run(conn: connection) -> None:
    """Create and seed the tag-category compatibility registry."""

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tag_category_registry (
                category     text NOT NULL,
                entity_kind  entity_kind NOT NULL,
                prompt_order integer NOT NULL DEFAULT 1000,
                description  text NOT NULL DEFAULT '',
                created_at   timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (category, entity_kind),
                CHECK (btrim(category) <> '')
            )
            """
        )
        cur.execute(
            """
            COMMENT ON TABLE tag_category_registry IS
                'Source of truth for which tag categories may be applied to each entity kind.';
            """
        )
        for category, entity_kind, prompt_order, description in CATEGORY_REGISTRY:
            cur.execute(
                """
                INSERT INTO tag_category_registry (
                    category, entity_kind, prompt_order, description
                ) VALUES (
                    %s, %s::entity_kind, %s, %s
                )
                ON CONFLICT (category, entity_kind) DO UPDATE SET
                    prompt_order = EXCLUDED.prompt_order,
                    description = EXCLUDED.description
                """,
                (category, entity_kind, prompt_order, description),
            )
        cur.execute(
            """
            SELECT DISTINCT t.category
            FROM tags t
            WHERE t.deprecated = FALSE
              AND t.synonym_for IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM tag_category_registry r
                  WHERE r.category = t.category
              )
            ORDER BY t.category
            """
        )
        unregistered = [row[0] for row in cur.fetchall()]
        if unregistered:
            detail = ", ".join(unregistered)
            raise RuntimeError(f"Unregistered Orrery tag categories: {detail}")
    conn.commit()
