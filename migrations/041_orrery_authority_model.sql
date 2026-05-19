-- 041_orrery_authority_model.sql
--
-- Persist Skald's structured adjudication of current-tick Orrery proposals.
-- Absence of an adjudication ratifies the proposal; explicit rows record
-- defer/void/replace decisions for auditability.

ALTER TABLE incubator
ADD COLUMN IF NOT EXISTS orrery_adjudications JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN incubator.orrery_adjudications IS
    'Skald-authored defer/replace/void rulings for Orrery proposals in the provisional chunk.';

CREATE TABLE IF NOT EXISTS orrery_adjudication_log (
    id                       bigserial PRIMARY KEY,
    tick_chunk_id            bigint NOT NULL REFERENCES narrative_chunks(id),
    proposal_id              text NOT NULL,
    template_id              text NOT NULL,
    binding_hash             text NOT NULL,
    action                   text NOT NULL
        CHECK (action IN ('defer', 'replace', 'void')),
    adjudication_source      text NOT NULL DEFAULT 'explicit'
        CHECK (adjudication_source IN ('explicit', 'structured_state_update')),
    skald_note               text,
    original_state_delta     jsonb NOT NULL DEFAULT '{}'::jsonb,
    replacement_state_delta  jsonb,
    replacement_event_type   text REFERENCES event_types(type),
    applied_resolution_id    bigint REFERENCES orrery_resolutions(id),
    created_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_orrery_adjudication_log_tick_chunk_id
    ON orrery_adjudication_log (tick_chunk_id);

CREATE INDEX IF NOT EXISTS ix_orrery_adjudication_log_proposal_id
    ON orrery_adjudication_log (proposal_id);

CREATE INDEX IF NOT EXISTS ix_orrery_adjudication_log_action
    ON orrery_adjudication_log (action);

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
    i.orrery_adjudications,
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
