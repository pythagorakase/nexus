ALTER TABLE orrery_resolutions
    ADD COLUMN used_chunk_id bigint REFERENCES narrative_chunks(id),
    ADD COLUMN use_count integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN orrery_resolutions.used_chunk_id IS
    'Most recent accepted narrative chunk that used this offered Bleed resolution, detected by exact actor-name uptake.';

COMMENT ON COLUMN orrery_resolutions.use_count IS
    'Cumulative number of accepted narrative chunks that used this offered Bleed resolution by exact actor-name uptake.';
