-- Extend the existing attempt UUID; legacy predicted chunk IDs are not proof
-- of acceptance, so historical complete rows retain an unknown outcome.
ALTER TABLE narrative_generation_sessions
    ADD COLUMN phase TEXT NOT NULL DEFAULT 'retrieval'
        CHECK (phase IN ('retrieval', 'assembly', 'writer', 'gaia', 'staging', 'complete')),
    ADD COLUMN terminal_outcome TEXT
        CHECK (terminal_outcome IN ('accepted', 'superseded', 'error')),
    ADD COLUMN replaced_by_session_id UUID
        REFERENCES narrative_generation_sessions(session_id),
    ADD COLUMN error_class TEXT,
    ADD COLUMN heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

UPDATE narrative_generation_sessions
SET phase = CASE WHEN status = 'complete' THEN 'complete' ELSE 'retrieval' END,
    terminal_outcome = CASE WHEN status = 'error' THEN 'error' END,
    error_class = CASE WHEN status = 'error' THEN 'LegacyGenerationError' END,
    heartbeat_at = updated_at;

COMMENT ON COLUMN narrative_generation_sessions.phase IS
    'Last durable engine phase: retrieval, assembly, writer, gaia, staging, or complete.';
COMMENT ON COLUMN narrative_generation_sessions.terminal_outcome IS
    'Canonical attempt outcome; NULL while generating or awaiting a draft decision, accepted only in the accepting transaction.';
COMMENT ON COLUMN narrative_generation_sessions.replaced_by_session_id IS
    'Replacement attempt UUID, bound atomically when regenerate replaces the draft.';
COMMENT ON COLUMN narrative_generation_sessions.error_class IS
    'Exception class for failed attempts; LegacyGenerationError for historical failures.';
COMMENT ON COLUMN narrative_generation_sessions.heartbeat_at IS
    'Last successful generation heartbeat or phase transition, in server time.';
COMMENT ON TABLE narrative_generation_sessions IS
    'Durable per-slot generation attempts, phases, accepted chunk bindings, and replacement lineage.';
