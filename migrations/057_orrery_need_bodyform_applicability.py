"""Sync Orrery need rows with bodyform-driven applicability."""

from __future__ import annotations

from psycopg2.extensions import connection


NEED_TYPES: tuple[str, ...] = ("sleep", "hunger", "thirst", "socialize", "intimacy")


def run(conn: connection) -> None:
    """Install need-applicability sync helpers and prune stale rows."""

    with conn.cursor() as cur:
        _install_applicability_functions(cur)
        _replace_character_initializer(cur)
        _install_entity_tag_sync_trigger(cur)
        _sync_existing_characters(cur)
    conn.commit()


def _install_applicability_functions(cur) -> None:
    cur.execute(
        """
        CREATE OR REPLACE FUNCTION orrery_need_applies_to_tags(
            p_need_type character_need_type,
            p_active_tags text[]
        )
        RETURNS boolean AS $$
        DECLARE
            active_tags text[] := COALESCE(p_active_tags, ARRAY[]::text[]);
        BEGIN
            IF p_need_type::text IN ('sleep', 'hunger', 'thirst')
               AND active_tags && ARRAY[
                   'bodyform:android',
                   'bodyform:construct',
                   'bodyform:non_corporeal',
                   'digital_mind',
                   'inorganic',
                   'virtual'
               ]::text[] THEN
                RETURN FALSE;
            END IF;

            IF p_need_type::text = 'intimacy'
               AND active_tags && ARRAY[
                   'bodyform:non_corporeal',
                   'digital_mind',
                   'libido_absent',
                   'virtual'
               ]::text[] THEN
                RETURN FALSE;
            END IF;

            RETURN TRUE;
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;

        CREATE OR REPLACE FUNCTION orrery_active_character_tag_names(
            p_character_entity_id bigint
        )
        RETURNS text[] AS $$
            SELECT COALESCE(array_agg(DISTINCT t.tag), ARRAY[]::text[])
            FROM entity_tags et
            JOIN tags t ON t.id = et.tag_id
            WHERE et.entity_id = p_character_entity_id
              AND et.cleared_at IS NULL;
        $$ LANGUAGE sql STABLE;

        CREATE OR REPLACE FUNCTION orrery_sync_character_need_states(
            p_character_entity_id bigint
        )
        RETURNS integer AS $$
        DECLARE
            active_tags text[];
            anchor_world_time timestamptz;
            affected integer := 0;
            row_count integer := 0;
        BEGIN
            IF p_character_entity_id IS NULL THEN
                RETURN 0;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM entities e
                WHERE e.id = p_character_entity_id
                  AND e.kind = 'character'
                  AND e.is_active = true
            ) THEN
                RETURN 0;
            END IF;

            SELECT orrery_active_character_tag_names(p_character_entity_id)
            INTO active_tags;

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
            SELECT p_character_entity_id,
                   needs.need_type::character_need_type,
                   0,
                   anchor_world_time,
                   '{"synced_by": "need_applicability"}'::jsonb
            FROM (
                VALUES
                    ('sleep'),
                    ('hunger'),
                    ('thirst'),
                    ('socialize'),
                    ('intimacy')
            ) AS needs(need_type)
            WHERE orrery_need_applies_to_tags(
                needs.need_type::character_need_type,
                active_tags
            )
            ON CONFLICT (character_entity_id, need_type) DO NOTHING;
            GET DIAGNOSTICS row_count = ROW_COUNT;
            affected := affected + row_count;

            DELETE FROM character_need_states cns
            WHERE cns.character_entity_id = p_character_entity_id
              AND NOT orrery_need_applies_to_tags(cns.need_type, active_tags);
            GET DIAGNOSTICS row_count = ROW_COUNT;
            affected := affected + row_count;

            UPDATE entity_tags et
            SET cleared_at = now()
            FROM tags t,
                 (
                    VALUES
                        ('sleep', 'sleep_deprived'),
                        ('hunger', 'hungry'),
                        ('thirst', 'thirsty'),
                        ('socialize', 'under_socialized'),
                        ('intimacy', 'intimacy_starved')
                 ) AS severity(need_type, prefix)
            WHERE et.entity_id = p_character_entity_id
              AND et.tag_id = t.id
              AND et.cleared_at IS NULL
              AND t.tag LIKE severity.prefix || '\\_%'
              AND NOT orrery_need_applies_to_tags(
                  severity.need_type::character_need_type,
                  active_tags
              );
            GET DIAGNOSTICS row_count = ROW_COUNT;
            affected := affected + row_count;

            RETURN affected;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def _replace_character_initializer(cur) -> None:
    cur.execute(
        """
        CREATE OR REPLACE FUNCTION orrery_initialize_character_need_states()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.entity_id IS NOT NULL THEN
                PERFORM orrery_sync_character_need_states(NEW.entity_id);
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_characters_need_state_init ON characters;

        CREATE TRIGGER trg_characters_need_state_init
        AFTER INSERT OR UPDATE OF entity_id ON characters
        FOR EACH ROW
        WHEN (NEW.entity_id IS NOT NULL)
        EXECUTE FUNCTION orrery_initialize_character_need_states();
        """
    )


def _install_entity_tag_sync_trigger(cur) -> None:
    cur.execute(
        """
        CREATE OR REPLACE FUNCTION orrery_sync_need_states_after_entity_tag_change()
        RETURNS trigger AS $$
        DECLARE
            affected_entity_id bigint;
        BEGIN
            affected_entity_id := COALESCE(NEW.entity_id, OLD.entity_id);
            PERFORM orrery_sync_character_need_states(affected_entity_id);
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_entity_tags_need_state_applicability
            ON entity_tags;

        CREATE TRIGGER trg_entity_tags_need_state_applicability
        AFTER INSERT OR UPDATE OR DELETE ON entity_tags
        FOR EACH ROW
        EXECUTE FUNCTION orrery_sync_need_states_after_entity_tag_change();
        """
    )


def _sync_existing_characters(cur) -> None:
    cur.execute(
        """
        SELECT orrery_sync_character_need_states(e.id)
        FROM entities e
        WHERE e.kind = 'character'
          AND e.is_active = true
        """
    )
