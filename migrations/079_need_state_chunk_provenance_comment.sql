-- 079_need_state_chunk_provenance_comment.sql
--
-- Keep installed schema documentation aligned with the current use of
-- last_evaluated_chunk_id after retiring chunk-based need-debt accrual.

COMMENT ON COLUMN character_need_states.last_evaluated_chunk_id IS
    'Narrative chunk that last evaluated or mutated this need-state row. '
    'Preserved as mutation and replay provenance; it does not participate '
    'in elapsed-world-time debt accrual. NULL means no chunk provenance '
    'has been recorded.';
