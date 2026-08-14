-- 110_experience_formation_sweep.sql
-- Durable event-level formation tracking for past-anchored experience sweeps.

ALTER TABLE world_events
    ADD COLUMN IF NOT EXISTS experiences_formed_at timestamptz,
    ADD COLUMN IF NOT EXISTS experiences_quarantined_at timestamptz;

COMMENT ON COLUMN world_events.experiences_formed_at IS
    'Database time when the accepted-chunk experience sweep processed this event; NULL means unprocessed unless experiences_quarantined_at is non-NULL.';

COMMENT ON COLUMN world_events.experiences_quarantined_at IS
    'Database time when experience formation quarantined this malformed event; non-NULL excludes it from automatic formation until manually cleared.';

-- Preserve healthy saves only when every receipt owner is already represented
-- by a valid direct participant/witness seed. Acquisition arrays are
-- deliberately excluded because their incident event may never have had its
-- direct receipts processed. This backfill derives receipt ownership from
-- event data only; live configuration remains the runtime sweep's judgment.
WITH experience_role_policy AS (
    SELECT '{
        "compliance_alert": ["actor", "target"],
        "encoded_message": ["actor", "target"],
        "hunt_called_off": ["actor"],
        "hunt_declared": ["actor"],
        "informant_contact": ["actor", "target"],
        "intel_acquired": ["actor", "target"],
        "intel_acted_on": ["actor"],
        "protective_intervention": ["actor"],
        "pursue_romance_completed": ["actor", "target"],
        "recruit_ally_completed": ["actor", "target"],
        "relationship_drift_milestone": ["actor"],
        "retaliation_attempted": ["actor"],
        "retaliation_executed": ["actor", "target"],
        "rival_consulted": ["actor", "target"],
        "seek_redemption_completed": ["actor", "target"],
        "surveillance_performed": ["actor"],
        "threat_issued": ["actor", "target"],
        "warning_delivered": ["actor", "target"]
    }'::jsonb AS roles_by_event_type
),
participant_receipt_owner_tokens AS (
    SELECT event.id AS event_id,
           'entity:' || participant.entity_id::text AS owner_token
    FROM world_events event
    JOIN world_event_entities participant ON participant.event_id = event.id
    CROSS JOIN experience_role_policy policy
    WHERE CASE
        WHEN policy.roles_by_event_type ? event.event_type
            THEN (policy.roles_by_event_type -> event.event_type)
                 ? participant.role::text
        ELSE participant.role::text IN ('actor', 'target', 'beneficiary')
    END
),
public_event_audiences AS (
    SELECT event.id AS event_id,
           event.payload -> 'audience_entity_ids' AS audience
    FROM world_events event
    WHERE jsonb_typeof(event.payload) = 'object'
      AND event.payload -> 'on_screen_public' = 'true'::jsonb
),
audience_elements AS (
    SELECT audience.event_id, item.ordinality, item.value,
           jsonb_typeof(item.value) AS value_type
    FROM public_event_audiences audience
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(audience.audience) = 'array'
                THEN audience.audience
            ELSE '[]'::jsonb
        END
    ) WITH ORDINALITY AS item(value, ordinality)
),
audience_string_candidates AS (
    SELECT element.*,
           btrim(element.value #>> '{}', E' \t\n\r\f') AS trimmed_value
    FROM audience_elements element
    WHERE element.value_type = 'string'
),
audience_string_unsigned AS (
    SELECT candidate.*,
           CASE
               WHEN left(candidate.trimmed_value, 1) = '+'
                   THEN substr(candidate.trimmed_value, 2)
               ELSE candidate.trimmed_value
           END AS unsigned_value
    FROM audience_string_candidates candidate
),
audience_string_canonical AS (
    SELECT candidate.*,
           COALESCE(
               NULLIF(ltrim(candidate.unsigned_value, '0'), ''),
               '0'
           ) AS canonical_value
    FROM audience_string_unsigned candidate
),
audience_owner_tokens AS (
    -- JSON numeric values are already PostgreSQL numerics. Python int() also
    -- truncates JSON floats toward zero before enforcing the positive-id gate.
    SELECT element.event_id,
           CASE
               WHEN trunc((element.value #>> '{}')::numeric)
                        BETWEEN 1::numeric AND 9223372036854775807::numeric
                   THEN 'entity:'
                        || trunc((element.value #>> '{}')::numeric)::text
               ELSE 'invalid-audience:' || element.ordinality::text
                    || ':' || element.value::text
           END AS owner_token
    FROM audience_elements element
    WHERE element.value_type = 'number'

    UNION ALL

    -- Normalize positive decimal strings without casting, so arbitrarily
    -- malformed or oversized values cannot abort or disappear in migration.
    SELECT candidate.event_id,
           CASE
               WHEN candidate.unsigned_value ~ '^[0-9]+$'
                AND candidate.canonical_value <> '0'
                AND (
                    length(candidate.canonical_value) < 19
                    OR (
                        length(candidate.canonical_value) = 19
                        AND candidate.canonical_value <= '9223372036854775807'
                    )
                )
                   THEN 'entity:' || candidate.canonical_value
               ELSE 'invalid-audience:' || candidate.ordinality::text
                    || ':' || candidate.value::text
           END AS owner_token
    FROM audience_string_canonical candidate

    UNION ALL

    SELECT element.event_id,
           'invalid-audience:' || element.ordinality::text
           || ':' || element.value::text AS owner_token
    FROM audience_elements element
    WHERE element.value_type NOT IN ('number', 'string')

    UNION ALL

    -- A public event with a missing or non-array audience is invalid at the
    -- runtime boundary. Keep it unformed with an unmatchable owner sentinel.
    SELECT audience.event_id,
           'invalid-audience-container:'
           || COALESCE(audience.audience::text, '<missing>') AS owner_token
    FROM public_event_audiences audience
    WHERE jsonb_typeof(audience.audience) IS DISTINCT FROM 'array'

    UNION ALL

    -- Runtime receipt derivation rejects a non-object payload before it can
    -- inspect public-audience fields, so migration must not bless that event.
    SELECT event.id AS event_id,
           'invalid-event-payload:' || event.payload::text AS owner_token
    FROM world_events event
    WHERE jsonb_typeof(event.payload) IS DISTINCT FROM 'object'
),
receipt_owner_tokens AS (
    SELECT event_id, owner_token
    FROM participant_receipt_owner_tokens

    UNION

    SELECT event_id, owner_token
    FROM audience_owner_tokens
),
direct_seed_owners AS (
    SELECT source.event_id,
           'entity:' || experience.character_entity_id::text AS owner_token,
           max(experience.created_at) AS represented_at
    FROM character_experiences experience
    CROSS JOIN LATERAL unnest(experience.world_event_ids) source(event_id)
    WHERE experience.claim_awareness_id IS NULL
      AND experience.invalidation_status = 'valid'
    GROUP BY source.event_id, experience.character_entity_id
),
seeded_events AS (
    SELECT event_id, max(represented_at) AS formed_at
    FROM direct_seed_owners
    GROUP BY event_id
),
owner_complete_events AS (
    SELECT seeded.event_id, seeded.formed_at
    FROM seeded_events seeded
    WHERE NOT EXISTS (
        SELECT 1
        FROM receipt_owner_tokens receipt
        WHERE receipt.event_id = seeded.event_id
          AND NOT EXISTS (
              SELECT 1
              FROM direct_seed_owners represented
              WHERE represented.event_id = receipt.event_id
                AND represented.owner_token = receipt.owner_token
          )
    )
)
UPDATE world_events event
SET experiences_formed_at = represented.formed_at
FROM owner_complete_events represented
WHERE event.id = represented.event_id
  AND event.experiences_formed_at IS NULL
  AND event.experiences_quarantined_at IS NULL;

DROP INDEX IF EXISTS ix_world_events_unformed_experiences;

CREATE INDEX ix_world_events_unformed_experiences
    ON world_events (tick_chunk_id, id)
    WHERE experiences_formed_at IS NULL
      AND experiences_quarantined_at IS NULL
      AND superseded_by_event_id IS NULL;

-- Migration 104 allowed only one direct seed per owner/anchor/basis. A later
-- event at an already-formed historical anchor needs a distinct seed for its
-- newly processed event set, while acquisitions retain awareness-row identity.
DROP INDEX IF EXISTS ux_character_experiences_seed_identity;
DROP INDEX IF EXISTS ux_character_experiences_event_set_identity;

CREATE UNIQUE INDEX ux_character_experiences_event_set_identity
    ON character_experiences (
        character_entity_id,
        anchor_chunk_id,
        basis,
        world_event_ids
    )
    WHERE claim_awareness_id IS NULL
      AND invalidation_status = 'valid';

CREATE UNIQUE INDEX IF NOT EXISTS ux_character_experiences_acquisition_identity
    ON character_experiences (claim_awareness_id)
    WHERE claim_awareness_id IS NOT NULL;

-- Earlier review builds installed a trigger for future supersessions. Replay
-- treats application writes as the ledger, so remove that side-write path;
-- future invalidation belongs to the application supersession transaction.
DROP TRIGGER IF EXISTS trg_invalidate_experiences_for_event_supersession
    ON world_events;

DROP FUNCTION IF EXISTS invalidate_experiences_for_event_supersession();

-- One-shot repair for supersessions already present when migration 110 lands.
-- First invalidate pending direct seeds that still reference superseded events.
-- Then consider every invalidated direct seed, including rows invalidated by an
-- earlier review-build trigger, and reopen each stamped live event whose owner
-- has no valid direct seed covering it. Rendered valid rows remain narrative
-- history and are reported by durable id.
DO $$
DECLARE
    newly_invalidated_seed_ids bigint[];
    reopen_source_invalidated_seed_ids bigint[];
    reopened_live_event_ids bigint[];
    rendered_seed_ids bigint[];
BEGIN
    WITH newly_invalidated AS (
        UPDATE character_experiences experience
        SET invalidation_status = 'invalidated',
            invalidated_at = CURRENT_TIMESTAMP
        WHERE experience.claim_awareness_id IS NULL
          AND experience.experience_text IS NULL
          AND experience.invalidation_status = 'valid'
          AND EXISTS (
              SELECT 1
              FROM world_events superseded
              WHERE superseded.id = ANY(experience.world_event_ids)
                AND superseded.superseded_by_event_id IS NOT NULL
          )
        RETURNING experience.id
    )
    SELECT COALESCE(array_agg(id ORDER BY id), '{}'::bigint[])
    INTO newly_invalidated_seed_ids
    FROM newly_invalidated;

    -- This is deliberately a separate statement: PostgreSQL data-modifying
    -- CTEs share a snapshot, while this read must see the rows invalidated by
    -- the statement above as well as rows invalidated before migration 110.
    WITH reopen_candidates AS (
        SELECT DISTINCT experience.id AS seed_id, live.id AS event_id
        FROM character_experiences experience
        CROSS JOIN LATERAL unnest(experience.world_event_ids) source(event_id)
        JOIN world_events live ON live.id = source.event_id
        WHERE experience.claim_awareness_id IS NULL
          AND experience.invalidation_status = 'invalidated'
          AND live.superseded_by_event_id IS NULL
          AND live.experiences_formed_at IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM character_experiences covering
              WHERE covering.claim_awareness_id IS NULL
                AND covering.invalidation_status = 'valid'
                AND covering.character_entity_id =
                    experience.character_entity_id
                AND covering.world_event_ids
                    @> ARRAY[live.id]::bigint[]
          )
    ),
    reopened AS (
        UPDATE world_events live
        SET experiences_formed_at = NULL
        FROM (
            SELECT DISTINCT event_id
            FROM reopen_candidates
        ) candidate
        WHERE live.id = candidate.event_id
          AND live.experiences_formed_at IS NOT NULL
        RETURNING live.id
    )
    SELECT COALESCE(
               (
                   SELECT array_agg(seed_id ORDER BY seed_id)
                   FROM (
                       SELECT DISTINCT seed_id
                       FROM reopen_candidates
                   ) source_seeds
               ),
               '{}'::bigint[]
           ),
           COALESCE(
               (SELECT array_agg(id ORDER BY id) FROM reopened),
               '{}'::bigint[]
           )
    INTO reopen_source_invalidated_seed_ids, reopened_live_event_ids;

    SELECT COALESCE(array_agg(experience.id ORDER BY experience.id), '{}'::bigint[])
    INTO rendered_seed_ids
    FROM character_experiences experience
    WHERE experience.claim_awareness_id IS NULL
      AND experience.experience_text IS NOT NULL
      AND experience.invalidation_status = 'valid'
      AND EXISTS (
          SELECT 1
          FROM world_events superseded
          WHERE superseded.id = ANY(experience.world_event_ids)
            AND superseded.superseded_by_event_id IS NOT NULL
      );

    RAISE NOTICE 'orrery_experience_supersession_migration_cleanup %',
      jsonb_build_object(
        'invalidated_seed_count', cardinality(newly_invalidated_seed_ids),
        'invalidated_seed_ids', to_jsonb(newly_invalidated_seed_ids),
        'reopen_source_invalidated_seed_count',
            cardinality(reopen_source_invalidated_seed_ids),
        'reopen_source_invalidated_seed_ids',
            to_jsonb(reopen_source_invalidated_seed_ids),
        'reopened_live_event_count', cardinality(reopened_live_event_ids),
        'reopened_live_event_ids', to_jsonb(reopened_live_event_ids),
        'retained_rendered_seed_count', cardinality(rendered_seed_ids),
        'retained_rendered_seed_ids', to_jsonb(rendered_seed_ids)
      );
END
$$;
