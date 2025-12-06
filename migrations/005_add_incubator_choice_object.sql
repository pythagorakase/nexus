-- Migration 005: Add missing choice_object column to incubator table
--
-- The incubator table stores in-progress narrative generation data.
-- The choice_object column stores the structured choice data that will be
-- presented to the user after narrative generation completes.
--
-- Schema defined in scripts/create_incubator_table.sql but was missing
-- from live save slot databases.

ALTER TABLE incubator
ADD COLUMN IF NOT EXISTS choice_object JSONB;

COMMENT ON COLUMN incubator.choice_object IS
'Structured choice data: {presented: string[], selected: {label, text, edited}}';
