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

-- Update the incubator_view to include choice_object
-- Must DROP and CREATE since adding columns mid-order fails with CREATE OR REPLACE
DROP VIEW IF EXISTS incubator_view;
CREATE VIEW incubator_view AS
SELECT
    i.chunk_id,
    i.parent_chunk_id,
    nc.raw_text AS parent_chunk_text,
    i.user_text,
    i.storyteller_text,
    i.choice_object,  -- Added: structured choice data for UI display
    i.metadata_updates -> 'chronology' ->> 'episode_transition' AS episode_transition,
    i.metadata_updates -> 'chronology' ->> 'time_delta_description' AS time_delta,
    i.metadata_updates ->> 'world_layer' AS world_layer,
    i.metadata_updates ->> 'pacing' AS pacing,
    COALESCE(jsonb_array_length(i.entity_updates -> 'characters'), 0)
        + COALESCE(jsonb_array_length(i.entity_updates -> 'locations'), 0)
        + COALESCE(jsonb_array_length(i.entity_updates -> 'factions'), 0)
        AS entity_update_count,
    i.entity_updates AS entity_changes,
    i.reference_updates AS "references",
    i.status,
    i.session_id,
    i.created_at
FROM incubator i
LEFT JOIN narrative_chunks nc ON nc.id = i.parent_chunk_id
WHERE i.id = TRUE;
