-- Migration 107: durable Pass-1/Pass-2 baselines staged with provisional prose.

ALTER TABLE incubator
    ADD COLUMN IF NOT EXISTS lore_pass_baseline JSONB;

COMMENT ON COLUMN incubator.lore_pass_baseline IS
    'Unbound versioned Pass-2 baseline staged atomically with provisional storyteller prose and discarded on rejection.';

CREATE TABLE IF NOT EXISTS lore_pass_baselines (
    chunk_id BIGINT PRIMARY KEY
        REFERENCES narrative_chunks(id) ON DELETE CASCADE,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE lore_pass_baselines IS
    'Accepted versioned Pass-2 baselines, promoted in the same transaction as their narrative chunk.';
COMMENT ON COLUMN lore_pass_baselines.chunk_id IS
    'Actual accepted narrative_chunks id returned by insertion; also the parent identity required during next-turn hydration.';
COMMENT ON COLUMN lore_pass_baselines.schema_version IS
    'Validated baseline wire-schema version duplicated from payload for indexed administrative inspection.';
COMMENT ON COLUMN lore_pass_baselines.payload IS
    'Validated bound Pass-2 baseline containing exact typed memory identities, token accounting, and compatibility fingerprint.';
COMMENT ON COLUMN lore_pass_baselines.created_at IS
    'Database time at accepted-chunk promotion.';
