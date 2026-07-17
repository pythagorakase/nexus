-- 083_claim_propagation_ledger.sql
--
-- Register the Stage 2c system event that double-enters every passively
-- propagated secondhand-knowledge acquisition.  The event-local world clock
-- preserves the scheduled acquisition time when a large accepted-chunk time
-- skip releases several staggered hops in one transaction.
-- New checkpoint captures add the 'claim_awareness' section in Python. Older
-- checkpoint documents intentionally remain untouched so replay can identify
-- the missing section and skip that unreproducible comparison window.

ALTER TABLE world_events
    ADD COLUMN IF NOT EXISTS world_time timestamptz;

COMMENT ON COLUMN world_events.world_time IS
    'Exact diegetic occurrence time for system events whose schedule may precede their committing chunk; NULL legacy/resolver rows inherit the tick chunk world time.';

CREATE INDEX IF NOT EXISTS ix_world_events_claim_propagated_claim_id
    ON world_events (((payload ->> 'claim_id')::bigint))
    WHERE event_type = 'claim_propagated';

COMMENT ON INDEX ix_world_events_claim_propagated_claim_id IS
    'Supports Stage 2c frontier depth recovery by claim id without scanning unrelated world-event payloads.';

INSERT INTO event_types (type, category, severity, description)
VALUES (
    'claim_propagated',
    'intelligence',
    'minor',
    'System-minted secondhand-knowledge acquisition produced by the deterministic Social Contagion frontier drain.'
)
ON CONFLICT (type) DO NOTHING;
