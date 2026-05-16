-- 024_orrery_commit_pipeline.sql
--
-- Persist the dry-run Orrery proposal across the preview/approval boundary and
-- seed the controlled vocabulary required by the initial built-in packages.

ALTER TABLE incubator
ADD COLUMN IF NOT EXISTS orrery_proposal JSONB;

COMMENT ON COLUMN incubator.orrery_proposal IS
    'No-write OrreryTickProposal generated during preview; stamped into canonical Orrery tables only when the incubator chunk is accepted.';

DROP INDEX IF EXISTS ix_entity_tags_current;
CREATE UNIQUE INDEX ix_entity_tags_current
    ON entity_tags (entity_id, tag_id)
    WHERE cleared_at IS NULL;

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

INSERT INTO event_types (type, category, severity, description)
VALUES
    ('evade_pursuit', 'orrery_resolution', 'moderate', 'An off-screen character evades active pursuit.'),
    ('honor_debt', 'orrery_resolution', 'moderate', 'An off-screen character services a binding obligation.'),
    ('pursue_identity_lead', 'orrery_resolution', 'moderate', 'An off-screen character follows a lead about buried identity.'),
    ('maintain_cover', 'orrery_resolution', 'minor', 'An off-screen character maintains plausible baseline activity.')
ON CONFLICT (type) DO NOTHING;

INSERT INTO tags (
    tag, category, is_ephemeral, clearance_kind, reapplication_policy,
    clear_on, description
)
VALUES
    (
        'contacts_available',
        'orrery_state',
        false,
        NULL,
        NULL,
        NULL,
        'Entity has contacts that can plausibly support off-screen action.'
    ),
    (
        'ghostprint_active',
        'orrery_state',
        false,
        NULL,
        NULL,
        NULL,
        'Entity has access to an active Ghostprint Key or equivalent identity artifact.'
    ),
    (
        'off_grid',
        'orrery_state',
        false,
        NULL,
        NULL,
        NULL,
        'Entity has temporarily reduced their observable footprint.'
    ),
    (
        'seeking_identity',
        'orrery_state',
        false,
        NULL,
        NULL,
        NULL,
        'Entity is actively trying to reconstruct or pursue buried identity leads.'
    ),
    (
        'debt_pulse_active',
        'orrery_signal',
        true,
        'event',
        'replace',
        '{"event_types": ["honor_debt"]}'::jsonb,
        'Ephemeral signal that a binding obligation is currently pressing.'
    ),
    (
        'under_active_pursuit',
        'orrery_signal',
        true,
        'event',
        'replace',
        '{"event_types": ["evade_pursuit"]}'::jsonb,
        'Ephemeral signal that an entity is being actively pursued.'
    )
ON CONFLICT (tag) DO NOTHING;
