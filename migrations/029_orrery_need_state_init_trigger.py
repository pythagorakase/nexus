"""Initialize Sunhelm need state rows for newly-created characters."""

from __future__ import annotations


def run(conn) -> None:
    """Install a trigger that keeps character_need_states initialized."""

    _create_initializer_function(conn)
    _install_initializer_trigger(conn)
    _backfill_missing_need_states(conn)


def _create_initializer_function(conn) -> None:
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
                    VALUES ('sleep'), ('hunger'), ('thirst')
                ) AS needs(need_type)
                ON CONFLICT (character_entity_id, need_type) DO NOTHING;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    conn.commit()


def _install_initializer_trigger(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DROP TRIGGER IF EXISTS trg_characters_need_state_init ON characters"
        )
        cur.execute(
            """
            CREATE TRIGGER trg_characters_need_state_init
            AFTER INSERT OR UPDATE OF entity_id ON characters
            FOR EACH ROW
            WHEN (NEW.entity_id IS NOT NULL)
            EXECUTE FUNCTION orrery_initialize_character_need_states()
            """
        )
    conn.commit()


def _backfill_missing_need_states(conn) -> None:
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
                   '{"backfilled_by": "migration_029"}'::jsonb
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
