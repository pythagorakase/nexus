-- 111_experience_job_enqueue_gin_fence.sql
-- Index the active experience-job membership fence used at scene boundaries.

CREATE INDEX IF NOT EXISTS ix_character_experience_jobs_pending_experience_ids
    ON character_experience_jobs USING GIN (experience_ids)
    WHERE state IN (
        'queued'::orrery_job_state,
        'leased'::orrery_job_state,
        'failed'::orrery_job_state
    );

COMMENT ON INDEX ix_character_experience_jobs_pending_experience_ids IS
    'Supports the scene-boundary enqueue fence that rejects experience ids already owned by queued, leased, or failed rendering jobs.';
