-- 110_experience_formation_sweep.sql
-- Durable event-level formation tracking for past-anchored experience sweeps.

ALTER TABLE world_events
    ADD COLUMN IF NOT EXISTS experiences_formed_at timestamptz;

COMMENT ON COLUMN world_events.experiences_formed_at IS
    'Database time when the accepted-chunk experience sweep processed this event; NULL means it remains eligible for formation.';

-- Preserve healthy saves: events already represented by a direct
-- participant/witness seed have already crossed the formation boundary.
-- Acquisition arrays are deliberately excluded because their incident event
-- may never have had its direct receipts processed.
UPDATE world_events event
SET experiences_formed_at = represented.formed_at
FROM (
    SELECT source.event_id, min(experience.created_at) AS formed_at
    FROM character_experiences experience
    CROSS JOIN LATERAL unnest(experience.world_event_ids) source(event_id)
    WHERE experience.claim_awareness_id IS NULL
    GROUP BY source.event_id
) represented
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
