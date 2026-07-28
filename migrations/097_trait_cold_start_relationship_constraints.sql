-- Persist player-authored cold-start relationship boundaries beside each trait.

ALTER TABLE assets.traits
    ADD COLUMN IF NOT EXISTS cold_start_relationships TEXT NOT NULL DEFAULT 'allowed';

ALTER TABLE assets.traits
    ADD COLUMN IF NOT EXISTS preexisting_relationship_targets JSONB
    NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE assets.traits
    DROP CONSTRAINT IF EXISTS traits_cold_start_relationships_check;

ALTER TABLE assets.traits
    ADD CONSTRAINT traits_cold_start_relationships_check
    CHECK (cold_start_relationships IN ('allowed', 'forbidden'));

ALTER TABLE assets.traits
    DROP CONSTRAINT IF EXISTS traits_preexisting_relationship_targets_check;

ALTER TABLE assets.traits
    ADD CONSTRAINT traits_preexisting_relationship_targets_check
    CHECK (jsonb_typeof(preexisting_relationship_targets) = 'array');

COMMENT ON COLUMN assets.traits.cold_start_relationships IS
    'Whether setup may materialize preexisting relationship or pair-tag rows for this trait';

COMMENT ON COLUMN assets.traits.preexisting_relationship_targets IS
    'Player-explicit preexisting relationship target names captured by trait confirmation';
