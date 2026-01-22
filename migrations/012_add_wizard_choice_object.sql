-- Migration 012: Add choice_object column to new_story_creator table
--
-- The new_story_creator table stores wizard state during story setup.
-- Adding choice_object allows the wizard to persist the choices presented
-- to the user, enabling the CLI's --choice flag to work correctly.
--
-- This mirrors the pattern used in the incubator table for narrative mode.

ALTER TABLE assets.new_story_creator
ADD COLUMN IF NOT EXISTS choice_object JSONB;

COMMENT ON COLUMN assets.new_story_creator.choice_object IS
'Structured choice data from last wizard response: {presented: string[], selected: {label, text, edited}}';
