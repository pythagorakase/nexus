-- 080_epistemics_knowers.sql
--
-- Institutions and every other event-participating entity may possess claims.

ALTER TABLE claim_awareness
    RENAME COLUMN character_entity_id TO knower_entity_id;

ALTER TABLE claim_awareness
    RENAME CONSTRAINT claim_awareness_character_entity_id_fkey
    TO claim_awareness_knower_entity_id_fkey;

-- PostgreSQL renames the unique constraint's backing index with the constraint.
ALTER TABLE claim_awareness
    RENAME CONSTRAINT claim_awareness_claim_id_character_entity_id_key
    TO claim_awareness_claim_id_knower_entity_id_key;

COMMENT ON TABLE claim_awareness IS
    'Append-only Epistemics v1 binary possession rows, one per claim and knower entity.';
COMMENT ON COLUMN claim_awareness.knower_entity_id IS
    'Entity spine id of the knower; any entity that can participate in a world event can possess a claim.';
