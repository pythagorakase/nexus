-- 093_claim_awareness_knower_index.sql
--
-- Present-character knowledge lookup should not scan the full awareness ledger.

CREATE INDEX ix_claim_awareness_knower_entity_id
    ON claim_awareness USING btree (knower_entity_id);

COMMENT ON INDEX ix_claim_awareness_knower_entity_id IS
    'Supports the per-turn Storyteller knowledge digest lookup by present knower without scanning claim awareness history.';
