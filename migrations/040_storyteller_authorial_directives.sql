-- 040_storyteller_authorial_directives.sql
--
-- Persist Storyteller-authored retrieval priorities so each committed chunk can
-- steer the next turn's MEMNON retrieval, matching storyteller_core.md.

ALTER TABLE narrative_chunks
ADD COLUMN IF NOT EXISTS authorial_directives JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE incubator
ADD COLUMN IF NOT EXISTS authorial_directives JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN narrative_chunks.authorial_directives IS
    'Storyteller-authored retrieval directives for the successor turn.';

COMMENT ON COLUMN incubator.authorial_directives IS
    'Provisional Storyteller-authored retrieval directives to persist when accepted.';

DROP VIEW IF EXISTS incubator_view;
CREATE VIEW incubator_view AS
SELECT
    i.chunk_id,
    i.parent_chunk_id,
    nc.raw_text AS parent_chunk_text,
    i.user_text,
    i.storyteller_text,
    i.choice_object,
    i.choice_text,
    i.authorial_directives,
    i.orrery_proposal,
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
