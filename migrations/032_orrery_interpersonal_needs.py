"""Add Orrery interpersonal need-state vocabulary."""

from __future__ import annotations


NEED_TYPES = ("socialize", "intimacy")

SEVERITY_TAGS = (
    ("under_socialized_1_mild", "orrery_need", "Mild socialization debt."),
    ("under_socialized_2_moderate", "orrery_need", "Moderate socialization debt."),
    ("under_socialized_3_severe", "orrery_need", "Severe socialization debt."),
    ("under_socialized_4_critical", "orrery_need", "Critical socialization debt."),
    ("intimacy_starved_1_mild", "orrery_need", "Mild intimacy debt."),
    ("intimacy_starved_2_moderate", "orrery_need", "Moderate intimacy debt."),
    ("intimacy_starved_3_severe", "orrery_need", "Severe intimacy debt."),
    ("intimacy_starved_4_critical", "orrery_need", "Critical intimacy debt."),
    (
        "extroversion_low",
        "orrery_social_modulator",
        "Lower social-contact need threshold pressure.",
    ),
    (
        "extroversion_moderate",
        "orrery_social_modulator",
        "Default social-contact need threshold pressure.",
    ),
    (
        "extroversion_high",
        "orrery_social_modulator",
        "Higher social-contact need threshold pressure.",
    ),
    (
        "libido_absent",
        "orrery_intimacy_modulator",
        "Intimacy need does not apply to this character.",
    ),
    (
        "libido_low",
        "orrery_intimacy_modulator",
        "Lower intimacy need threshold pressure.",
    ),
    (
        "libido_moderate",
        "orrery_intimacy_modulator",
        "Default intimacy need threshold pressure.",
    ),
    (
        "libido_high",
        "orrery_intimacy_modulator",
        "Higher intimacy need threshold pressure.",
    ),
    (
        "partnered_exclusively",
        "orrery_intimacy_context",
        "Routes intimacy behavior toward established-partner branches.",
    ),
    (
        "ethically_opposed_to_contracted_intimacy",
        "orrery_intimacy_context",
        "Excludes contracted-intimacy branches.",
    ),
    (
        "vow_of_celibacy",
        "orrery_intimacy_suppressor",
        "Principled abstention suppressing intimacy-package fulfillment.",
    ),
    (
        "religiously_abstinent",
        "orrery_intimacy_suppressor",
        "Cultural or spiritual abstention suppressing intimacy-package fulfillment.",
    ),
    (
        "closeted",
        "orrery_intimacy_suppressor",
        "Identity or circumstance suppresses intimacy-package fulfillment.",
    ),
)

EPHEMERAL_TAGS = (
    (
        "grieving_recent_partner",
        "orrery_intimacy_suppressor",
        "semantic",
        '{"description": "cleared when grief no longer suppresses intimacy behavior"}',
        "Recent partner grief suppresses intimacy-package fulfillment.",
    ),
    (
        "recently_traumatized_intimate",
        "orrery_intimacy_suppressor",
        "semantic",
        '{"description": "cleared by authored healing or durable safety"}',
        "Recent intimate trauma suppresses intimacy-package fulfillment.",
    ),
    (
        "focus_committed",
        "orrery_intimacy_suppressor",
        "semantic",
        '{"description": "cleared when the consuming work or mission resolves"}',
        "Voluntary mission focus suppresses intimacy-package fulfillment.",
    ),
)

PLACE_AFFORDANCE_TAGS = (
    ("town_square", "A civic public space where people gather."),
    ("public_space", "A general public space with routine social presence."),
    ("general_social_venue", "A venue built for ordinary social contact."),
    (
        "intimate_social_venue",
        "A venue where intimate possibility is socially legible.",
    ),
    (
        "intimate_services_establishment",
        "A venue where contracted intimate companionship can be arranged.",
    ),
    ("private_quarters", "Private quarters suitable for solitary intimate privacy."),
)

EVENT_TYPES = (
    ("socialized", "social", "minor", "A character fulfills social-contact need."),
    (
        "socialized_alone",
        "social",
        "minor",
        "A character partially fulfills social-contact need alone.",
    ),
    (
        "intimacy_fulfilled",
        "embodied",
        "minor",
        "A character fulfills intimacy need.",
    ),
    (
        "intimacy_pursued",
        "embodied",
        "minor",
        "A character seeks conditions for intimacy without an assumed outcome.",
    ),
    (
        "intimacy_partial",
        "embodied",
        "minor",
        "A character partially fulfills intimacy need privately.",
    ),
    (
        "intimacy_deferred",
        "embodied",
        "minor",
        "A character leaves intimacy pressure unresolved.",
    ),
)


def run(conn) -> None:
    """Apply the interpersonal need-state migration."""

    _extend_need_type_enum(conn)
    _seed_durable_tags(conn)
    _seed_ephemeral_tags(conn)
    _seed_place_affordance_tags(conn)
    _seed_event_types(conn)
    _replace_need_initializer_function(conn)
    _backfill_need_states(conn)


def _extend_need_type_enum(conn) -> None:
    with conn.cursor() as cur:
        for need_type in NEED_TYPES:
            cur.execute(
                f"ALTER TYPE character_need_type ADD VALUE IF NOT EXISTS '{need_type}'"
            )
    conn.commit()


def _seed_durable_tags(conn) -> None:
    with conn.cursor() as cur:
        for tag, category, description in SEVERITY_TAGS:
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
                ON CONFLICT (tag) DO NOTHING
                """,
                (tag, category, description),
            )
    conn.commit()


def _seed_ephemeral_tags(conn) -> None:
    with conn.cursor() as cur:
        for tag, category, clearance_kind, clear_on_json, description in EPHEMERAL_TAGS:
            cur.execute(
                """
                INSERT INTO tags (
                    tag, category, is_ephemeral,
                    clearance_kind, reapplication_policy,
                    clear_on, description
                ) VALUES (
                    %s, %s, TRUE,
                    %s::entity_tag_clearance_kind,
                    'extend_expiry'::entity_tag_reapplication_policy,
                    %s::jsonb, %s
                )
                ON CONFLICT (tag) DO NOTHING
                """,
                (tag, category, clearance_kind, clear_on_json, description),
            )
    conn.commit()


def _seed_place_affordance_tags(conn) -> None:
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
                ON CONFLICT (tag) DO NOTHING
                """,
                (tag, description),
            )
    conn.commit()


def _seed_event_types(conn) -> None:
    with conn.cursor() as cur:
        for event_type, category, severity, description in EVENT_TYPES:
            cur.execute(
                """
                INSERT INTO event_types (
                    type, category, severity, description
                ) VALUES (
                    %s, %s, %s::event_severity_kind, %s
                )
                ON CONFLICT (type) DO NOTHING
                """,
                (event_type, category, severity, description),
            )
    conn.commit()


def _replace_need_initializer_function(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE OR REPLACE FUNCTION orrery_initialize_character_need_states()
            RETURNS trigger AS $$
            DECLARE
                anchor_world_time timestamptz;
            BEGIN
                IF NEW.entity_id IS NULL THEN
                    RETURN NEW;
                END IF;

                SELECT COALESCE(MAX(world_time), now())
                INTO anchor_world_time
                FROM chunk_metadata;

                INSERT INTO character_need_states (
                    character_entity_id,
                    need_type,
                    debt_score,
                    last_evaluated_at,
                    metadata
                )
                SELECT NEW.entity_id,
                       need_type::character_need_type,
                       0,
                       anchor_world_time,
                       '{"initialized_by": "character_trigger"}'::jsonb
                FROM (
                    VALUES
                        ('sleep'),
                        ('hunger'),
                        ('thirst'),
                        ('socialize'),
                        ('intimacy')
                ) AS needs(need_type)
                ON CONFLICT (character_entity_id, need_type) DO NOTHING;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    conn.commit()


def _backfill_need_states(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH clock AS (
                SELECT COALESCE(MAX(world_time), now()) AS world_time
                FROM chunk_metadata
            ),
            needs(need_type) AS (
                VALUES ('socialize'), ('intimacy')
            )
            INSERT INTO character_need_states (
                character_entity_id,
                need_type,
                debt_score,
                last_evaluated_at,
                metadata
            )
            SELECT c.entity_id,
                   needs.need_type::character_need_type,
                   0,
                   clock.world_time,
                   '{"backfilled_by": "migration_032"}'::jsonb
            FROM characters c
            JOIN entities e ON e.id = c.entity_id
            CROSS JOIN needs
            CROSS JOIN clock
            WHERE c.entity_id IS NOT NULL
              AND e.kind = 'character'
              AND e.is_active = true
            ON CONFLICT (character_entity_id, need_type) DO NOTHING
            """
        )
    conn.commit()
