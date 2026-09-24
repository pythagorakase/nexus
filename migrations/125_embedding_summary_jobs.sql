CREATE TABLE narrative_embedding_jobs (
    id bigserial PRIMARY KEY,
    state orrery_job_state NOT NULL DEFAULT 'queued',
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    locked_by text,
    lease_nonce uuid,
    last_error text,
    error_class text,
    generation_session_id uuid DEFAULT nullif(current_setting('nexus.generation_session_id', true), '')::uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    chunk_id bigint NOT NULL UNIQUE REFERENCES narrative_chunks(id) ON DELETE CASCADE
);
COMMENT ON TABLE narrative_embedding_jobs IS 'Durable in-process embedding plans for locked narrative chunks; excludes off-screen narrations.';
COMMENT ON COLUMN narrative_embedding_jobs.id IS 'Durable job identity.';
COMMENT ON COLUMN narrative_embedding_jobs.state IS 'Durable execution state.';
COMMENT ON COLUMN narrative_embedding_jobs.attempts IS 'Number of acquired execution attempts.';
COMMENT ON COLUMN narrative_embedding_jobs.available_at IS 'Earliest retry dispatch time.';
COMMENT ON COLUMN narrative_embedding_jobs.lease_until IS 'Current execution lease expiry.';
COMMENT ON COLUMN narrative_embedding_jobs.locked_by IS 'Owner holding the execution lease.';
COMMENT ON COLUMN narrative_embedding_jobs.lease_nonce IS 'Unique acquisition token fencing every completion write.';
COMMENT ON COLUMN narrative_embedding_jobs.last_error IS 'Most recent execution failure message.';
COMMENT ON COLUMN narrative_embedding_jobs.error_class IS 'Exception class of the most recent failure, retained on terminal failure.';
COMMENT ON COLUMN narrative_embedding_jobs.generation_session_id IS 'Originating generation session; NULL for legacy or independent work.';
COMMENT ON COLUMN narrative_embedding_jobs.created_at IS 'Enqueue timestamp.';
COMMENT ON COLUMN narrative_embedding_jobs.updated_at IS 'Latest execution state transition.';
COMMENT ON COLUMN narrative_embedding_jobs.chunk_id IS 'Locked narrative chunk to embed exactly once.';
CREATE INDEX narrative_embedding_jobs_pending ON narrative_embedding_jobs (available_at, id) WHERE state IN ('queued', 'leased');
CREATE INDEX narrative_embedding_jobs_session ON narrative_embedding_jobs (generation_session_id);

CREATE TABLE narrative_summary_jobs (
    id bigserial PRIMARY KEY,
    state orrery_job_state NOT NULL DEFAULT 'queued',
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    locked_by text,
    lease_nonce uuid,
    last_error text,
    error_class text,
    generation_session_id uuid DEFAULT nullif(current_setting('nexus.generation_session_id', true), '')::uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    kind text NOT NULL CHECK (kind IN ('episode', 'season')),
    season integer NOT NULL,
    episode integer,
    CHECK ((kind = 'episode') = (episode IS NOT NULL)),
    UNIQUE NULLS NOT DISTINCT (kind, season, episode)
);
COMMENT ON TABLE narrative_summary_jobs IS 'Episode and season summary plans created atomically with accepting transitions.';
COMMENT ON COLUMN narrative_summary_jobs.id IS 'Durable job identity.';
COMMENT ON COLUMN narrative_summary_jobs.state IS 'Durable execution state.';
COMMENT ON COLUMN narrative_summary_jobs.attempts IS 'Number of acquired execution attempts.';
COMMENT ON COLUMN narrative_summary_jobs.available_at IS 'Earliest retry dispatch time.';
COMMENT ON COLUMN narrative_summary_jobs.lease_until IS 'Current execution lease expiry.';
COMMENT ON COLUMN narrative_summary_jobs.locked_by IS 'Owner holding the execution lease.';
COMMENT ON COLUMN narrative_summary_jobs.lease_nonce IS 'Unique acquisition token fencing every completion write.';
COMMENT ON COLUMN narrative_summary_jobs.last_error IS 'Most recent execution failure message.';
COMMENT ON COLUMN narrative_summary_jobs.error_class IS 'Exception class of the most recent failure, retained on terminal failure.';
COMMENT ON COLUMN narrative_summary_jobs.generation_session_id IS 'Originating generation session; NULL for legacy or independent work.';
COMMENT ON COLUMN narrative_summary_jobs.created_at IS 'Enqueue timestamp.';
COMMENT ON COLUMN narrative_summary_jobs.updated_at IS 'Latest execution state transition.';
COMMENT ON COLUMN narrative_summary_jobs.kind IS 'Summary target kind.';
COMMENT ON COLUMN narrative_summary_jobs.season IS 'Target season number.';
COMMENT ON COLUMN narrative_summary_jobs.episode IS 'Target episode number; NULL for a season summary.';
CREATE INDEX narrative_summary_jobs_pending ON narrative_summary_jobs (available_at, id) WHERE state IN ('queued', 'leased');
CREATE INDEX narrative_summary_jobs_session ON narrative_summary_jobs (generation_session_id);

-- Retire legacy error payloads without losing their retry plans.
INSERT INTO narrative_summary_jobs (kind, season, episode, last_error, error_class)
SELECT 'episode', season, episode, summary->>'error', 'LegacySummaryError'
FROM episodes WHERE summary->>'status' = 'error';
INSERT INTO narrative_summary_jobs (kind, season, last_error, error_class)
SELECT 'season', id, summary->>'error', 'LegacySummaryError'
FROM seasons WHERE summary->>'status' = 'error';
UPDATE episodes SET summary=NULL WHERE summary->>'status' = 'error';
UPDATE seasons SET summary=NULL WHERE summary->>'status' = 'error';
