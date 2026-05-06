-- migrations/017_add_judgment_justification.sql
-- Description: Ensure ir_eval.judgments has a justification column for storing
--   the LLM's reasoning when relevance is judged on demand.  Existing
--   databases (e.g. NEXUS) already have this column from prior ad-hoc
--   ALTERs; this migration makes it part of the formal schema for fresh
--   targets.
-- Date: 2026-05-06

ALTER TABLE ir_eval.judgments
    ADD COLUMN IF NOT EXISTS justification TEXT;
