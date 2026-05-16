-- 021_dedup_embedded_state.sql
--
-- Retire the redundant narrative_chunks.state value 'embedded'. The state
-- 'embedded' carried the same information as embedding_generated_at IS NOT
-- NULL — the timestamp is the single source of truth for ironman status,
-- so the state value duplicated it.
--
-- This migration backfills existing rows (state='embedded' → 'finalized')
-- and refreshes the column comment from migration 018 to drop the
-- "synonymous with 'embedded' in practice" parenthetical. Application
-- code (ChunkState enum + accept_chunk's prev-chunk guard) has been
-- updated in the same PR to write 'finalized' and to check
-- embedding_generated_at IS NULL instead of state == 'finalized'.
--
-- Idempotent: re-running on a database where no 'embedded' rows remain
-- is a no-op UPDATE; COMMENT ON overwrites the prior comment.

UPDATE narrative_chunks
SET state = 'finalized'
WHERE state = 'embedded';

COMMENT ON COLUMN narrative_chunks.state IS
    'Chunk lifecycle state. One of: ''draft'' (initial), ''pending_review'' (storyteller has produced text, user has not yet accepted), ''finalized'' (user accepted; chunk is locked). The authoritative "has been embedded" predicate is embedding_generated_at IS NOT NULL, not a state value. See ChunkState enum in nexus/api/chunk_workflow.py.';
