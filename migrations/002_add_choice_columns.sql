-- migrations/002_add_choice_columns.sql
-- Description: Add structured choice support to narrative_chunks
-- Date: 2025-11-26
-- PR: #117 (Structured Story Choices)

-- Three new columns for the two-phase choice storage pattern:
--   storyteller_text: Pure narrative prose (before user choice appended)
--   choice_object: JSONB with {presented: [...], selected: {...}}
--   choice_text: Markdown summary of choices and selection

ALTER TABLE narrative_chunks
ADD COLUMN IF NOT EXISTS storyteller_text TEXT,
ADD COLUMN IF NOT EXISTS choice_object JSONB,
ADD COLUMN IF NOT EXISTS choice_text TEXT;

-- Add comment for documentation
COMMENT ON COLUMN narrative_chunks.storyteller_text IS 'Pure narrative prose before user choice is appended';
COMMENT ON COLUMN narrative_chunks.choice_object IS 'Structured choice data: {presented: string[], selected: {label, text, edited}}';
COMMENT ON COLUMN narrative_chunks.choice_text IS 'Markdown-formatted summary of choices and user selection';
