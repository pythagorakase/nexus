-- 082_generation_model_provenance.sql
--
-- Preserve the concrete registry model id that produced accepted storyteller
-- prose. Historical rows and non-storyteller writers remain NULL.

ALTER TABLE incubator
    ADD COLUMN IF NOT EXISTS generation_model TEXT NULL;

ALTER TABLE chunk_metadata
    ADD COLUMN IF NOT EXISTS generation_model TEXT NULL;

COMMENT ON COLUMN incubator.generation_model IS
    'The registry model id that produced the accepted storyteller text; NULL for pre-082 history and rows not produced by the storyteller pipeline.';

COMMENT ON COLUMN chunk_metadata.generation_model IS
    'The registry model id that produced the accepted storyteller text; NULL for pre-082 history and rows not produced by the storyteller pipeline.';
