-- migrations/102_narration_job_fencing.sql
-- Owner-fenced, idempotent Orrery narration jobs.

ALTER TYPE orrery_job_state
    ADD VALUE IF NOT EXISTS 'stale_rejected';

ALTER TABLE orrery_narration_jobs
    ADD COLUMN IF NOT EXISTS lease_nonce uuid,
    ADD COLUMN IF NOT EXISTS anchor_tick_chunk_id bigint,
    ADD COLUMN IF NOT EXISTS anchor_world_layer world_layer_type,
    ADD COLUMN IF NOT EXISTS superseded_at timestamptz;

UPDATE orrery_narration_jobs AS jobs
SET anchor_tick_chunk_id = resolutions.tick_chunk_id,
    anchor_world_layer = COALESCE(metadata.world_layer, 'primary'::world_layer_type)
FROM orrery_resolutions AS resolutions
LEFT JOIN chunk_metadata AS metadata
    ON metadata.chunk_id = resolutions.tick_chunk_id
WHERE resolutions.id = jobs.resolution_id
  AND (
      jobs.anchor_tick_chunk_id IS NULL
      OR jobs.anchor_world_layer IS NULL
  );

ALTER TABLE orrery_narration_jobs
    ALTER COLUMN anchor_tick_chunk_id SET NOT NULL,
    ALTER COLUMN anchor_world_layer SET NOT NULL;

ALTER TABLE orrery_narration_jobs
    DROP CONSTRAINT IF EXISTS orrery_narration_jobs_anchor_tick_chunk_id_fkey;

ALTER TABLE orrery_narration_jobs
    ADD CONSTRAINT orrery_narration_jobs_anchor_tick_chunk_id_fkey
    FOREIGN KEY (anchor_tick_chunk_id)
    REFERENCES narrative_chunks(id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_orrery_narration_jobs_effective_resolution
    ON orrery_narration_jobs (resolution_id)
    WHERE superseded_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_offscreen_narrations_resolution
    ON offscreen_narrations (resolution_id);

COMMENT ON COLUMN orrery_narration_jobs.lease_nonce IS
    'Fresh UUID stamped for each lease acquisition; completion and failure writes must present the current nonce together with locked_by before lease expiry.';
COMMENT ON COLUMN orrery_narration_jobs.anchor_tick_chunk_id IS
    'Canonical resolution tick copied at enqueue and revalidated atomically before narration output is inserted.';
COMMENT ON COLUMN orrery_narration_jobs.anchor_world_layer IS
    'Canonical timeline layer copied from chunk_metadata at enqueue and revalidated atomically at completion.';
COMMENT ON COLUMN orrery_narration_jobs.superseded_at IS
    'Explicit retirement timestamp; only one row with NULL superseded_at may be effective for a resolution.';
COMMENT ON COLUMN orrery_narration_jobs.locked_by IS
    'Worker owner identifier stamped at lease acquisition and required with lease_nonce for fenced writes.';
COMMENT ON INDEX ux_orrery_narration_jobs_effective_resolution IS
    'Allows exactly one non-superseded narration job per Orrery resolution.';
COMMENT ON INDEX ux_offscreen_narrations_resolution IS
    'Makes narration completion idempotent at the database boundary: one output per Orrery resolution.';
