-- Migration: Add traits_confirmed column to track explicit user confirmation
-- The existing logic used selected_trait_count == 3 to determine if traits subphase
-- was complete, but this conflicts with LLM pre-selecting suggested traits.
-- This column explicitly tracks when the user confirms their selection.

ALTER TABLE assets.new_story_creator
    ADD COLUMN IF NOT EXISTS traits_confirmed BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN assets.new_story_creator.traits_confirmed IS
    'Set to TRUE when user confirms trait selection (choice 0 in trait menu)';
