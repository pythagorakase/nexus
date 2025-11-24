-- Migration: Add layer_draft and zone_draft columns to assets.new_story_creator
-- Date: 2025-11-23
-- Purpose: Support persisting layer and zone artifacts from the new story wizard

-- Add layer_draft column
ALTER TABLE assets.new_story_creator
ADD COLUMN IF NOT EXISTS layer_draft jsonb;

-- Add zone_draft column
ALTER TABLE assets.new_story_creator
ADD COLUMN IF NOT EXISTS zone_draft jsonb;

-- Verify the changes
\d assets.new_story_creator;
