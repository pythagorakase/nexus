-- Preserve the current turn's ranked proposal snapshot after acceptance.
-- This is audit history, not a pending-proposal or rearm ledger.
ALTER TABLE narrative_chunks
    ADD COLUMN IF NOT EXISTS orrery_proposal jsonb;
COMMENT ON COLUMN narrative_chunks.orrery_proposal IS
    'Accepted-turn Orrery proposal snapshot, including template_id:binding_hash identities, zero-based positions in descending effective-priority order, canonical binding names, evaluated_at world time, and rendered_cards (the exact ordered kind/proposal_id selection, including repeated joint parents). NULL before migration 122; not a pending or rearm ledger.';

ALTER TABLE orrery_prompt_exposures
    ADD COLUMN IF NOT EXISTS card jsonb;
COMMENT ON COLUMN orrery_prompt_exposures.card IS
    'Exact rendered card data, including binding names, bindings, evaluated_at and persisted proposal position. Joint-beat rows identify each underlying proposal and include joint_beat_position. NULL on pre-122 exposures.';

ALTER TABLE orrery_prompt_exposures
    DROP CONSTRAINT orrery_prompt_exposures_kind_check;
ALTER TABLE orrery_prompt_exposures
    ADD CONSTRAINT orrery_prompt_exposures_kind_check
    CHECK (kind IN ('resolution', 'scene_pressure', 'joint_beat'));
COMMENT ON COLUMN orrery_prompt_exposures.position IS
    'Zero-based persisted proposal rank for resolution and joint_beat exposures; scene-pressure render position otherwise. Pre-122 rows retain their original within-kind render position.';
