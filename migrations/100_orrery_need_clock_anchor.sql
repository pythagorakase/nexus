-- Anchor Orrery need clocks to canonical story time and repair wall-time rows.

CREATE TABLE IF NOT EXISTS character_need_state_reconciliations (
    character_entity_id bigint NOT NULL,
    need_type character_need_type NOT NULL,
    field text NOT NULL,
    prior_value timestamptz NOT NULL,
    new_value timestamptz NOT NULL,
    debt_score_pre_image numeric(8, 2) NOT NULL,
    reconciled_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT character_need_state_reconciliations_pkey
        PRIMARY KEY (character_entity_id, need_type, field),
    CONSTRAINT character_need_state_reconciliations_field_check
        CHECK (field IN ('last_evaluated_at', 'last_fulfilled_at')),
    CONSTRAINT character_need_state_reconciliations_value_change_check
        CHECK (prior_value IS DISTINCT FROM new_value)
);

COMMENT ON TABLE character_need_state_reconciliations IS
    'Immutable migration-100 audit ledger. One row records each need-clock field restamped from an unreproducible wall-time value; it deliberately has no foreign key to the mutable need-state row so applicability deletion and reinsertion cannot erase replay authority.';
COMMENT ON COLUMN character_need_state_reconciliations.character_entity_id IS
    'Entity-spine character identifier of the need row as it existed when migration 100 reconciled it.';
COMMENT ON COLUMN character_need_state_reconciliations.need_type IS
    'Need dimension of the reconciled row.';
COMMENT ON COLUMN character_need_state_reconciliations.field IS
    'Restamped timestamp field: last_evaluated_at or last_fulfilled_at.';
COMMENT ON COLUMN character_need_state_reconciliations.prior_value IS
    'Exact timestamp pre-image replaced by migration 100.';
COMMENT ON COLUMN character_need_state_reconciliations.new_value IS
    'Exact canonical story-clock timestamp written by migration 100.';
COMMENT ON COLUMN character_need_state_reconciliations.debt_score_pre_image IS
    'Exact stored debt_score observed before this field was restamped; legacy wall-clock accrual remains opaque to replay.';
COMMENT ON COLUMN character_need_state_reconciliations.reconciled_at IS
    'Database transaction time when migration 100 inserted this immutable audit record.';
COMMENT ON CONSTRAINT character_need_state_reconciliations_pkey
    ON character_need_state_reconciliations IS
    'Permits at most one immutable reconciliation record per character, need, and field.';
COMMENT ON CONSTRAINT character_need_state_reconciliations_field_check
    ON character_need_state_reconciliations IS
    'Restricts audit rows to the two need-clock fields migration 100 can restamp.';
COMMENT ON CONSTRAINT character_need_state_reconciliations_value_change_check
    ON character_need_state_reconciliations IS
    'Requires every audit row to describe an actual timestamp change.';

CREATE OR REPLACE FUNCTION reject_character_need_state_reconciliation_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'character need state reconciliation audit rows are immutable';
END;
$$;

COMMENT ON FUNCTION reject_character_need_state_reconciliation_mutation() IS
    'Rejects UPDATE and DELETE so migration-100 replay provenance remains append-only.';

DROP TRIGGER IF EXISTS character_need_state_reconciliations_immutable
    ON character_need_state_reconciliations;
CREATE TRIGGER character_need_state_reconciliations_immutable
BEFORE UPDATE OR DELETE ON character_need_state_reconciliations
FOR EACH ROW
EXECUTE FUNCTION reject_character_need_state_reconciliation_mutation();

COMMENT ON TRIGGER character_need_state_reconciliations_immutable
    ON character_need_state_reconciliations IS
    'Protects reconciliation audit rows from mutation after their migration transaction commits.';

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

        -- Lock each pre-image, insert its durable audit row, and apply the
        -- reconciliation in one data-modifying statement. A prior audit row
        -- wins permanently; on an ordinary re-run the candidate predicate is
        -- empty because every touched clock already equals the anchor.
        WITH candidates AS MATERIALIZED (
            SELECT character_entity_id,
                   need_type,
                   last_evaluated_at AS prior_value,
                   debt_score
            FROM character_need_states
            WHERE last_evaluated_at < canonical_base_timestamp
               OR last_evaluated_at > reconciliation_anchor
            FOR UPDATE
        ),
        inserted AS (
            INSERT INTO character_need_state_reconciliations (
                character_entity_id,
                need_type,
                field,
                prior_value,
                new_value,
                debt_score_pre_image
            )
            SELECT character_entity_id,
                   need_type,
                   'last_evaluated_at',
                   prior_value,
                   reconciliation_anchor,
                   debt_score
            FROM candidates
            ON CONFLICT (character_entity_id, need_type, field) DO NOTHING
            RETURNING character_entity_id, need_type, field
        )
        UPDATE character_need_states AS cns
        SET last_evaluated_at = reconciliation_anchor,
            metadata = cns.metadata || jsonb_build_object(
                'reconciled_by',
                'migration_100',
                'reconciled_last_evaluated_from',
                candidates.prior_value::text,
                'reconciled_last_evaluated_to',
                reconciliation_anchor::text
            )
        FROM candidates
        JOIN inserted
          ON inserted.character_entity_id = candidates.character_entity_id
         AND inserted.need_type = candidates.need_type
         AND inserted.field = 'last_evaluated_at'
        WHERE cns.character_entity_id = candidates.character_entity_id
          AND cns.need_type = candidates.need_type;
        GET DIAGNOSTICS evaluated_row_count = ROW_COUNT;

        WITH candidates AS MATERIALIZED (
            SELECT character_entity_id,
                   need_type,
                   last_fulfilled_at AS prior_value,
                   debt_score
            FROM character_need_states
            WHERE last_fulfilled_at < canonical_base_timestamp
               OR last_fulfilled_at > reconciliation_anchor
            FOR UPDATE
        ),
        inserted AS (
            INSERT INTO character_need_state_reconciliations (
                character_entity_id,
                need_type,
                field,
                prior_value,
                new_value,
                debt_score_pre_image
            )
            SELECT character_entity_id,
                   need_type,
                   'last_fulfilled_at',
                   prior_value,
                   reconciliation_anchor,
                   debt_score
            FROM candidates
            ON CONFLICT (character_entity_id, need_type, field) DO NOTHING
            RETURNING character_entity_id, need_type, field
        )
        UPDATE character_need_states AS cns
        SET last_fulfilled_at = reconciliation_anchor,
            metadata = cns.metadata || jsonb_build_object(
                'reconciled_by',
                'migration_100',
                'reconciled_last_fulfilled_from',
                candidates.prior_value::text,
                'reconciled_last_fulfilled_to',
                reconciliation_anchor::text
            )
        FROM candidates
        JOIN inserted
          ON inserted.character_entity_id = candidates.character_entity_id
         AND inserted.need_type = candidates.need_type
         AND inserted.field = 'last_fulfilled_at'
        WHERE cns.character_entity_id = candidates.character_entity_id
          AND cns.need_type = candidates.need_type;
        GET DIAGNOSTICS fulfilled_row_count = ROW_COUNT;
    END IF;

    RAISE NOTICE
        'need-clock reconciliation: last_evaluated_at rows=%, last_fulfilled_at rows=%',
        evaluated_row_count,
        fulfilled_row_count;
END;
$$;
