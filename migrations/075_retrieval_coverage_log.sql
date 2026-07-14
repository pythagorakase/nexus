-- 075_retrieval_coverage_log.sql
--
-- Instrument Pass 2 retrieval coverage without changing retrieval behavior.

CREATE TABLE IF NOT EXISTS retrieval_coverage_log (
    id                 bigserial PRIMARY KEY,
    created_at         timestamptz NOT NULL DEFAULT now(),
    turn_id            text,
    user_input         text NOT NULL,
    detected_entities  jsonb NOT NULL DEFAULT '[]'::jsonb,
    raw_result_count   integer NOT NULL CHECK (raw_result_count >= 0),
    kept_chunk_ids     bigint[] NOT NULL DEFAULT ARRAY[]::bigint[],
    kept_tokens        integer NOT NULL CHECK (kept_tokens >= 0),
    available_budget   integer NOT NULL CHECK (available_budget >= 0),
    coverage           jsonb NOT NULL DEFAULT '[]'::jsonb,
    gap_entities       jsonb NOT NULL DEFAULT '[]'::jsonb
);

COMMENT ON TABLE retrieval_coverage_log IS
    'Per-turn Pass 2 retrieval coverage telemetry. Records detector matches, kept-chunk references, and detected entities absent from the kept context; never changes retrieval behavior.';
COMMENT ON COLUMN retrieval_coverage_log.id IS
    'Monotonic identifier for the retrieval coverage audit row.';
COMMENT ON COLUMN retrieval_coverage_log.created_at IS
    'Wall-clock time when the retrieval coverage audit row was written.';
COMMENT ON COLUMN retrieval_coverage_log.turn_id IS
    'LORE TurnContext.turn_id when the caller has a turn context; NULL for direct manager callers.';
COMMENT ON COLUMN retrieval_coverage_log.user_input IS
    'Exact user text used for Pass 2 raw-input retrieval and entity detection.';
COMMENT ON COLUMN retrieval_coverage_log.detected_entities IS
    'Detector matches as a JSON array of objects with kind, id, and canonical name.';
COMMENT ON COLUMN retrieval_coverage_log.raw_result_count IS
    'Number of raw-input retrieval results presented to the final Pass 2 budget truncation step.';
COMMENT ON COLUMN retrieval_coverage_log.kept_chunk_ids IS
    'Ordered narrative chunk ids retained by the final Pass 2 budget truncation step.';
COMMENT ON COLUMN retrieval_coverage_log.kept_tokens IS
    'Estimated token count consumed by the kept Pass 2 chunks.';
COMMENT ON COLUMN retrieval_coverage_log.available_budget IS
    'Pass 2 token budget available before the raw-input retrieval step.';
COMMENT ON COLUMN retrieval_coverage_log.coverage IS
    'Per detected entity, whether any kept chunk has a commit-time reference and the covering chunk ids.';
COMMENT ON COLUMN retrieval_coverage_log.gap_entities IS
    'Detected entities with no commit-time reference from any kept Pass 2 chunk.';

