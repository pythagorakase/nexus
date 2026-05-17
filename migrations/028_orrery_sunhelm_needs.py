"""Add Orrery Sunhelm need-state substrate and vocabulary."""

from __future__ import annotations


NEED_TYPES = ("sleep", "hunger", "thirst")

SEVERITY_TAGS = (
    ("sleep_deprived_1_mild", "orrery_need", "Mild sleep debt."),
    ("sleep_deprived_2_moderate", "orrery_need", "Moderate sleep debt."),
    ("sleep_deprived_3_severe", "orrery_need", "Severe sleep debt."),
    ("sleep_deprived_4_critical", "orrery_need", "Critical sleep debt."),
    ("hungry_1_mild", "orrery_need", "Mild hunger debt."),
    ("hungry_2_moderate", "orrery_need", "Moderate hunger debt."),
    ("hungry_3_severe", "orrery_need", "Severe hunger debt."),
    ("hungry_4_critical", "orrery_need", "Critical hunger debt."),
    ("thirsty_1_mild", "orrery_need", "Mild thirst debt."),
    ("thirsty_2_moderate", "orrery_need", "Moderate thirst debt."),
    ("thirsty_3_severe", "orrery_need", "Severe thirst debt."),
    ("thirsty_4_critical", "orrery_need", "Critical thirst debt."),
    (
        "bodyform:android",
        "bodyform",
        "Android bodyform; usually immune to embodied needs.",
    ),
    (
        "bodyform:undead",
        "bodyform",
        "Undead bodyform; need behavior is setting-specific.",
    ),
    (
        "bodyform:construct",
        "bodyform",
        "Construct bodyform; usually immune to embodied needs.",
    ),
    (
        "bodyform:non_corporeal",
        "bodyform",
        "Non-corporeal bodyform; usually immune to embodied needs.",
    ),
    (
        "bodyform:biologically_immortal",
        "bodyform",
        "Biologically immortal bodyform with setting-specific need curves.",
    ),
    ("sleep_schedule:diurnal", "orrery_schedule", "Default night-sleep schedule."),
    ("sleep_schedule:nocturnal", "orrery_schedule", "Day-sleep schedule."),
    ("sleep_schedule:nightshift", "orrery_schedule", "Work-at-night sleep schedule."),
    ("sleep_schedule:siesta", "orrery_schedule", "Split sleep with a daytime rest."),
    ("sleep_schedule:polyphasic", "orrery_schedule", "Multiple short sleep windows."),
)

EPHEMERAL_TAGS = (
    (
        "cns_stimulated",
        "orrery_need_modifier",
        "semantic",
        '{"description": "cleared when the stimulant, magic, or equivalent fatigue suppressor wears off"}',
        "Fatigue is physiologically accruing but sleep behavior is suppressed.",
    ),
)

EVENT_TYPES = (
    ("slept", "physiological", "minor", "A character fulfills sleep need."),
    ("ate", "physiological", "minor", "A character fulfills hunger need."),
    ("drank", "physiological", "minor", "A character fulfills thirst need."),
)


def run(conn) -> None:
    """Apply the Sunhelm need-state migration."""

    _create_need_type_enum(conn)
    _create_need_state_table(conn)
    _seed_durable_tags(conn)
    _seed_ephemeral_tags(conn)
    _seed_event_types(conn)
    _backfill_need_states(conn)


def _create_need_type_enum(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'character_need_type'
                ) THEN
                    CREATE TYPE character_need_type AS ENUM (
                        'sleep', 'hunger', 'thirst'
                    );
                END IF;
            END $$;
            """
        )
    conn.commit()


def _create_need_state_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS character_need_states (
                character_entity_id bigint NOT NULL
                    REFERENCES entities(id) ON DELETE CASCADE,
                need_type character_need_type NOT NULL,
                debt_score numeric(8, 2) NOT NULL DEFAULT 0,
                last_evaluated_at timestamptz NOT NULL,
                last_fulfilled_at timestamptz,
                metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (character_entity_id, need_type),
                CHECK (debt_score >= 0)
            );

            CREATE INDEX IF NOT EXISTS ix_character_need_states_need_debt
                ON character_need_states (need_type, debt_score DESC);

            COMMENT ON TABLE character_need_states IS
                'Orrery Sunhelm need state: timestamp plus debt pressure per character need.';
            COMMENT ON COLUMN character_need_states.debt_score IS
                'Hours-equivalent homeostatic debt. Fulfillment may discharge partially.';
            COMMENT ON COLUMN character_need_states.last_evaluated_at IS
                'In-world timestamp through which debt_score has already accrued.';
            COMMENT ON COLUMN character_need_states.last_fulfilled_at IS
                'Last in-world fulfillment timestamp for audit and prose context.';
            """
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


def _backfill_need_states(conn) -> None:
    """Initialize forgiving need state rows for existing active characters."""

    with conn.cursor() as cur:
        cur.execute(
            """
            WITH clock AS (
                SELECT COALESCE(MAX(world_time), now()) AS world_time
                FROM chunk_metadata
            ),
            needs(need_type) AS (
                VALUES ('sleep'), ('hunger'), ('thirst')
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
                   '{"backfilled": true}'::jsonb
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
