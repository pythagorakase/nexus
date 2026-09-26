-- Migration 132: Genesis Strangeness Selection and Provenance (issue #838)
--
-- The wizard's coarse strangeness control (low | medium | high) is player
-- consent to be surprised, not a guarantee of bizarre content. The selection
-- lives in the wizard cache so a failed transition retries with the same
-- level; the transition records the selected level, and the level and genre
-- band Retrograde resolved it to, beside the world it wrote, in the same
-- transaction.
--
-- Both columns are nullable and additive: a wizard with no selection uses
-- [orrery.retrograde.weird].default_level, and a story that began without
-- Retrograde history has no genesis provenance. No existing row changes.

ALTER TABLE assets.new_story_creator
    ADD COLUMN weird_level TEXT
        CONSTRAINT new_story_creator_weird_level_check
        CHECK (weird_level IN ('low', 'medium', 'high'));

ALTER TABLE global_variables
    ADD COLUMN genesis_weird JSONB;

COMMENT ON COLUMN assets.new_story_creator.weird_level IS
    'Player-selected genesis strangeness (low, medium, or high); NULL until chosen, when the transition uses [orrery.retrograde.weird].default_level. Only a new wizard clears it.';
COMMENT ON COLUMN global_variables.genesis_weird IS
    'Genesis strangeness provenance written by the wizard transition with its Retrograde history: selected_level (the wizard''s stored choice, null when the player chose none), the resolved level, resolved genre, band source, and raw_min/raw_max. NULL when the story began without Retrograde history.';
