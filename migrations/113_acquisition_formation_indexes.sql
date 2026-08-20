-- Bound acquisition-experience formation by acquisition provenance and
-- delivery-event identity.

CREATE INDEX IF NOT EXISTS ix_claim_awareness_acquisition_sweep
    ON claim_awareness (source_chunk_id, id)
    WHERE source_tier IN ('told', 'granted');

COMMENT ON INDEX ix_claim_awareness_acquisition_sweep IS
    'Supports anchor-bounded told/granted acquisition-experience formation without scanning unrelated awareness tiers.';

CREATE INDEX IF NOT EXISTS ix_world_events_awareness_delivery
    ON world_events (tick_chunk_id, (payload ->> 'awareness_id'))
    WHERE (payload ->> 'awareness_id') IS NOT NULL;

COMMENT ON INDEX ix_world_events_awareness_delivery IS
    'Supports acquisition-experience delivery lookup by source chunk and durable claim-awareness identity while excluding events without awareness ids.';
