-- Anchor Orrery need clocks to canonical story time and repair wall-time rows.

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

    anchor_world_time := COALESCE(
        (SELECT MAX(world_time) FROM chunk_metadata),
        (SELECT base_timestamp FROM global_variables)
    );
    IF anchor_world_time IS NULL THEN
        RAISE EXCEPTION
            'need-clock anchor unavailable: no canonical world time or base_timestamp';
    END IF;

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
      AND t.tag LIKE severity.prefix || '\_%'
      AND NOT orrery_need_applies_to_tags(
          severity.need_type::character_need_type,
          active_tags
      );
    GET DIAGNOSTICS row_count = ROW_COUNT;
    affected := affected + row_count;

    RETURN affected;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION orrery_sync_character_need_states(bigint) IS
    'Synchronizes applicable character need rows and anchors new clocks to canonical story time; raises when neither chunk world time nor the story base timestamp exists.';

DO $$
DECLARE
    canonical_base_timestamp timestamptz;
    reconciliation_anchor timestamptz;
    evaluated_row_count integer := 0;
    fulfilled_row_count integer := 0;
BEGIN
    SELECT base_timestamp
    INTO canonical_base_timestamp
    FROM global_variables;

    IF canonical_base_timestamp IS NOT NULL THEN
        SELECT COALESCE(MAX(world_time), canonical_base_timestamp)
        INTO reconciliation_anchor
        FROM chunk_metadata;

        UPDATE character_need_states
        SET last_evaluated_at = reconciliation_anchor
        WHERE last_evaluated_at < canonical_base_timestamp
           OR last_evaluated_at > reconciliation_anchor;
        GET DIAGNOSTICS evaluated_row_count = ROW_COUNT;

        UPDATE character_need_states
        SET last_fulfilled_at = reconciliation_anchor
        WHERE last_fulfilled_at < canonical_base_timestamp
           OR last_fulfilled_at > reconciliation_anchor;
        GET DIAGNOSTICS fulfilled_row_count = ROW_COUNT;
    END IF;

    RAISE NOTICE
        'need-clock reconciliation: last_evaluated_at rows=%, last_fulfilled_at rows=%',
        evaluated_row_count,
        fulfilled_row_count;
END;
$$;
