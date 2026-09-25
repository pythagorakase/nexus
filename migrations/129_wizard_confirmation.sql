-- Draft completion is not player acceptance. Preserve legacy progress only where
-- a persisted later artifact proves that the previous phase was crossed.
ALTER TABLE assets.new_story_creator
    ADD COLUMN setting_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN character_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN character_revision_pending BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE assets.new_story_creator SET
    setting_confirmed = setting_genre IS NOT NULL AND (
        character_name IS NOT NULL OR traits_confirmed OR seed_type IS NOT NULL
        OR layer_name IS NOT NULL OR zone_name IS NOT NULL OR initial_location IS NOT NULL
    ),
    character_confirmed = character_name IS NOT NULL AND (
        seed_type IS NOT NULL OR layer_name IS NOT NULL OR zone_name IS NOT NULL
        OR initial_location IS NOT NULL
    );

COMMENT ON COLUMN assets.new_story_creator.setting_confirmed IS
    'Explicit player acceptance of the current setting artifact.';
COMMENT ON COLUMN assets.new_story_creator.character_confirmed IS
    'Explicit player acceptance of the complete character; completeness alone is insufficient.';
COMMENT ON COLUMN assets.new_story_creator.character_revision_pending IS
    'Durable concept revision mode; the next character response must persist a replacement concept.';
