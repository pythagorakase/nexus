-- 110_experience_formation_sweep.sql
-- Durable event-level formation tracking for past-anchored experience sweeps.

ALTER TABLE world_events
    ADD COLUMN IF NOT EXISTS experiences_formed_at timestamptz;

COMMENT ON COLUMN world_events.experiences_formed_at IS
    'Database time when the accepted-chunk experience sweep processed this event; NULL means it remains eligible for formation.';

-- Preserve healthy saves only when every eligible receipt owner is already
-- represented by a direct participant/witness seed. Acquisition arrays are
-- deliberately excluded because their incident event may never have had its
-- direct receipts processed. The dossier predicate mirrors migration 110's
-- shipped [orrery.experiences] defaults; SQL migrations cannot read nexus.toml.
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
receipt_owner_rows AS (
    SELECT event.id AS event_id, participant.entity_id
    FROM world_events event
    JOIN world_event_entities participant ON participant.event_id = event.id
    CROSS JOIN experience_role_policy policy
    WHERE CASE
        WHEN policy.roles_by_event_type ? event.event_type
            THEN (policy.roles_by_event_type -> event.event_type)
                 ? participant.role::text
        ELSE participant.role::text IN ('actor', 'target', 'beneficiary')
    END

    UNION

    SELECT event.id AS event_id, audience.entity_id
    FROM world_events event
    CROSS JOIN LATERAL (
        SELECT raw.value::bigint AS entity_id
        FROM jsonb_array_elements_text(
            CASE
                WHEN event.payload -> 'on_screen_public' = 'true'::jsonb
                    THEN COALESCE(
                        event.payload -> 'audience_entity_ids',
                        'null'::jsonb
                    )
                ELSE '[]'::jsonb
            END
        ) raw(value)
    ) audience
),
receipt_owner_maps AS (
    SELECT event_id,
           jsonb_object_agg(
               entity_id::text,
               true ORDER BY entity_id
           ) AS receipt_owners
    FROM receipt_owner_rows
    GROUP BY event_id
),
eligible_receipt_owners AS (
    SELECT receipt.event_id, owner.key::bigint AS character_entity_id
    FROM receipt_owner_maps receipt
    CROSS JOIN LATERAL jsonb_object_keys(receipt.receipt_owners) owner(key)
    JOIN characters character ON character.entity_id = owner.key::bigint
    WHERE num_nonnulls(
        NULLIF(btrim(character.summary), ''),
        NULLIF(btrim(character.background), ''),
        NULLIF(btrim(character.personality), '')
    ) >= 2
),
direct_seed_owners AS (
    SELECT source.event_id,
           experience.character_entity_id,
           max(experience.created_at) AS represented_at
    FROM character_experiences experience
    CROSS JOIN LATERAL unnest(experience.world_event_ids) source(event_id)
    WHERE experience.claim_awareness_id IS NULL
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
        FROM eligible_receipt_owners receipt
        WHERE receipt.event_id = seeded.event_id
          AND NOT EXISTS (
              SELECT 1
              FROM direct_seed_owners represented
              WHERE represented.event_id = receipt.event_id
                AND represented.character_entity_id =
                    receipt.character_entity_id
          )
    )
)
UPDATE world_events event
SET experiences_formed_at = represented.formed_at
FROM owner_complete_events represented
WHERE event.id = represented.event_id
  AND event.experiences_formed_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_world_events_unformed_experiences
    ON world_events (tick_chunk_id, id)
    WHERE experiences_formed_at IS NULL
      AND superseded_by_event_id IS NULL;

-- Migration 104 allowed only one direct seed per owner/anchor/basis. A later
-- event at an already-formed historical anchor needs a distinct seed for its
-- newly processed event set, while acquisitions retain awareness-row identity.
DROP INDEX IF EXISTS ux_character_experiences_seed_identity;

CREATE UNIQUE INDEX IF NOT EXISTS ux_character_experiences_event_set_identity
    ON character_experiences (
        character_entity_id,
        anchor_chunk_id,
        basis,
        world_event_ids
    )
    WHERE claim_awareness_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_character_experiences_acquisition_identity
    ON character_experiences (claim_awareness_id)
    WHERE claim_awareness_id IS NOT NULL;

-- Supersession is a world-event write, so invalidate pending direct memories
-- in the same transaction no matter which producer writes the retcon. A race
-- with rendering is deterministic: whichever row lock wins decides whether
-- the seed is pending (invalidate it) or narrative history (retain it).
CREATE OR REPLACE FUNCTION invalidate_experiences_for_event_supersession()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    invalidated_seed_ids bigint[];
    rendered_seed_ids bigint[];
BEGIN
    IF NEW.superseded_by_event_id IS NULL
       OR NEW.superseded_by_event_id IS NOT DISTINCT FROM
          OLD.superseded_by_event_id THEN
        RETURN NEW;
    END IF;

    WITH invalidated AS (
        UPDATE character_experiences experience
        SET invalidation_status = 'invalidated',
            invalidated_at = CURRENT_TIMESTAMP
        WHERE experience.claim_awareness_id IS NULL
          AND experience.world_event_ids @> ARRAY[NEW.id]
          AND experience.experience_text IS NULL
          AND experience.invalidation_status = 'valid'
        RETURNING experience.id
    )
    SELECT COALESCE(array_agg(id ORDER BY id), '{}'::bigint[])
    INTO invalidated_seed_ids
    FROM invalidated;

    SELECT COALESCE(array_agg(experience.id ORDER BY experience.id), '{}'::bigint[])
    INTO rendered_seed_ids
    FROM character_experiences experience
    WHERE experience.claim_awareness_id IS NULL
      AND experience.world_event_ids @> ARRAY[NEW.id]
      AND experience.experience_text IS NOT NULL;

    RAISE WARNING 'orrery_experience_supersession %', jsonb_build_object(
        'event_id', NEW.id,
        'replacement_event_id', NEW.superseded_by_event_id,
        'invalidated_seed_ids', to_jsonb(invalidated_seed_ids),
        'retained_rendered_seed_ids', to_jsonb(rendered_seed_ids)
    );
    RETURN NEW;
END
$$;

COMMENT ON FUNCTION invalidate_experiences_for_event_supersession() IS
    'Atomically invalidates pending direct experience seeds when a source event is superseded, while retaining rendered narrative history.';

DROP TRIGGER IF EXISTS trg_invalidate_experiences_for_event_supersession
    ON world_events;

CREATE TRIGGER trg_invalidate_experiences_for_event_supersession
AFTER UPDATE OF superseded_by_event_id ON world_events
FOR EACH ROW
EXECUTE FUNCTION invalidate_experiences_for_event_supersession();

COMMENT ON TRIGGER trg_invalidate_experiences_for_event_supersession
    ON world_events IS
    'Invalidates unrendered direct experiences that reference a newly superseded world event.';
