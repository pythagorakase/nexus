CREATE TABLE deferred_work_scheduler (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    owner_id text NOT NULL,
    lease_nonce uuid NOT NULL,
    heartbeat_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    current_job text,
    last_error text
);
COMMENT ON TABLE deferred_work_scheduler IS 'Singleton durable ownership lease for this slot deferred-work scheduler.';
COMMENT ON COLUMN deferred_work_scheduler.id IS 'Singleton key; only true is permitted.';
COMMENT ON COLUMN deferred_work_scheduler.owner_id IS 'Gateway or operator process identifier.';
COMMENT ON COLUMN deferred_work_scheduler.lease_nonce IS 'Unique acquisition token fencing heartbeats, release and job dispatch.';
COMMENT ON COLUMN deferred_work_scheduler.heartbeat_at IS 'Wall-clock timestamp of the last successful owner heartbeat.';
COMMENT ON COLUMN deferred_work_scheduler.expires_at IS 'Wall-clock expiry after which another scheduler may acquire ownership.';
COMMENT ON COLUMN deferred_work_scheduler.current_job IS 'Queue currently being drained; NULL while idle.';
COMMENT ON COLUMN deferred_work_scheduler.last_error IS 'Most recent scheduler pass error, cleared after a successful pass.';

ALTER TABLE orrery_maturation_jobs ADD COLUMN locked_by text;
ALTER TABLE orrery_maturation_jobs ADD COLUMN lease_nonce uuid;
COMMENT ON COLUMN orrery_maturation_jobs.locked_by IS 'Worker identity holding the current maturation lease.';
COMMENT ON COLUMN orrery_maturation_jobs.lease_nonce IS 'Unique lease acquisition token required for every completion and manifest write.';

CREATE TABLE correspondence_compaction_jobs (
    id bigserial PRIMARY KEY,
    accepting_chunk_id bigint NOT NULL UNIQUE REFERENCES narrative_chunks(id) ON DELETE CASCADE,
    state orrery_job_state NOT NULL DEFAULT 'queued',
    attempts integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    locked_by text,
    lease_nonce uuid,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE correspondence_compaction_jobs IS 'Durable retry plans for accepted storyteller correspondence; the journal and digest remain authoritative.';
COMMENT ON COLUMN correspondence_compaction_jobs.id IS 'Compaction job identifier.';
COMMENT ON COLUMN correspondence_compaction_jobs.accepting_chunk_id IS 'Accepted chunk that requested compaction; execution replans against the current journal.';
COMMENT ON COLUMN correspondence_compaction_jobs.state IS 'Durable compaction execution state.';
COMMENT ON COLUMN correspondence_compaction_jobs.attempts IS 'Number of acquired execution leases.';
COMMENT ON COLUMN correspondence_compaction_jobs.available_at IS 'Earliest wall-clock time a queued retry may run.';
COMMENT ON COLUMN correspondence_compaction_jobs.lease_until IS 'Wall-clock expiry of the current execution lease.';
COMMENT ON COLUMN correspondence_compaction_jobs.locked_by IS 'Owner of the current execution lease.';
COMMENT ON COLUMN correspondence_compaction_jobs.lease_nonce IS 'Unique token fencing the current execution attempt.';
COMMENT ON COLUMN correspondence_compaction_jobs.last_error IS 'Most recent execution failure.';
COMMENT ON COLUMN correspondence_compaction_jobs.created_at IS 'Wall-clock enqueue timestamp.';
COMMENT ON COLUMN correspondence_compaction_jobs.updated_at IS 'Wall-clock timestamp of the latest state transition.';
CREATE INDEX correspondence_compaction_jobs_pending ON correspondence_compaction_jobs (available_at, id) WHERE state IN ('queued', 'leased');
