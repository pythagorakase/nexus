-- Add missing columns to assets.new_story_creator
ALTER TABLE assets.new_story_creator 
ADD COLUMN IF NOT EXISTS layer_draft JSONB,
ADD COLUMN IF NOT EXISTS zone_draft JSONB,
ADD COLUMN IF NOT EXISTS initial_location JSONB;
