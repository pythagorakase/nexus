-- 070_need_state_chunk_stamp.sql
--
-- Tick-floor need accrual (Bundle 4b): need debt currently accrues only
-- with elapsed WORLD time, but the narrative advances ~5 minutes per
-- chunk, so hour-denominated thresholds take hundreds of chunks to
-- re-arm (socialize mild = 24h ≈ 288 chunks) — a measured starvation
-- regime (548 need-debt refusals in the blocker histogram).
--
-- last_evaluated_chunk_id records WHICH tick last evaluated the row, so
-- the resolver can floor accrual in story time:
--   effective_hours = max(elapsed_world_hours,
--                         chunks_elapsed * min_accrual_hours_per_chunk)
-- Rows never stamped (NULL) get no floor — the floor engages as ticks
-- naturally restamp the cast.

ALTER TABLE character_need_states
    ADD COLUMN IF NOT EXISTS last_evaluated_chunk_id BIGINT;

COMMENT ON COLUMN character_need_states.last_evaluated_chunk_id IS
    'Tick chunk that last evaluated/stamped this need row. Enables the '
    'story-time accrual floor ([orrery.sunhelm] min_accrual_hours_per_chunk): '
    'each elapsed chunk counts as at least that many world-hours of accrual. '
    'NULL = never stamped since migration 070; floor inert for the row.';
