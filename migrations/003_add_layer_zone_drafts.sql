-- migrations/003_add_layer_zone_drafts.sql
-- Description: Add layer_draft and zone_draft columns to new_story_creator
-- Date: 2025-11-26
-- Issue: Wizard initialization fails on save_04/save_05 due to missing columns

-- These columns were added to some databases but not propagated to all.
-- The write_cache() function expects these columns to exist.

ALTER TABLE assets.new_story_creator
ADD COLUMN IF NOT EXISTS layer_draft JSONB,
ADD COLUMN IF NOT EXISTS zone_draft JSONB;

-- Add comments for documentation
COMMENT ON COLUMN assets.new_story_creator.layer_draft IS 'JSON draft of layer/world configuration';
COMMENT ON COLUMN assets.new_story_creator.zone_draft IS 'JSON draft of zone/region configuration';
