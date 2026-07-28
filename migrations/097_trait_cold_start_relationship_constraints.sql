-- Persist player-authored cold-start relationship boundaries beside each trait.

ALTER TABLE assets.traits
    ADD COLUMN IF NOT EXISTS cold_start_relationships TEXT NOT NULL DEFAULT 'allowed';

ALTER TABLE assets.traits
    DROP CONSTRAINT IF EXISTS traits_cold_start_relationships_check;

ALTER TABLE assets.traits
    ADD CONSTRAINT traits_cold_start_relationships_check
    CHECK (cold_start_relationships IN ('allowed', 'forbidden'));

COMMENT ON COLUMN assets.traits.cold_start_relationships IS
    'Whether setup may materialize a preexisting relationship row for this trait';
