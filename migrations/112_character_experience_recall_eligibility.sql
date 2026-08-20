-- 112_character_experience_recall_eligibility.sql
-- Actor-owned experience eligibility for entitlement-first recall.

CREATE INDEX IF NOT EXISTS ix_character_experiences_recall_eligibility
    ON character_experiences (
        character_entity_id,
        world_layer,
        anchor_chunk_id DESC
    )
    WHERE invalidation_status = 'valid';

COMMENT ON INDEX ix_character_experiences_recall_eligibility IS
    'Supports actor-owned recall eligibility across both rendered and unrendered valid experiences by owner, world layer, and descending anchor.';
