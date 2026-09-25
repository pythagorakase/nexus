-- Accepted name reveals retain the original character and all its history.
CREATE TABLE character_identity_rulings (
    id bigserial PRIMARY KEY,
    source_chunk_id bigint NOT NULL REFERENCES narrative_chunks(id) ON DELETE CASCADE,
    character_id bigint NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    entity_id bigint NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    decision text NOT NULL CHECK (decision = 'same_as'),
    previous_name text NOT NULL CHECK (length(btrim(previous_name)) > 0),
    new_name text NOT NULL CHECK (length(btrim(new_name)) > 0),
    evidence text NOT NULL CHECK (length(btrim(evidence)) > 0),
    generation_session_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_chunk_id, character_id)
);
CREATE INDEX character_identity_rulings_character_idx
    ON character_identity_rulings(character_id, id);
COMMENT ON TABLE character_identity_rulings IS
    'Explicit accepted same-person name reveals; does not merge existing rows or authorize fuzzy identity binding.';
COMMENT ON COLUMN character_identity_rulings.id IS 'Durable identity ruling key.';
COMMENT ON COLUMN character_identity_rulings.source_chunk_id IS 'Accepted narrative chunk establishing the revealed name.';
COMMENT ON COLUMN character_identity_rulings.character_id IS 'Unchanged canonical character subtype ID.';
COMMENT ON COLUMN character_identity_rulings.entity_id IS 'Unchanged global entity ID for the character.';
COMMENT ON COLUMN character_identity_rulings.decision IS 'Explicit same_as ruling; other identity decisions are not supported here.';
COMMENT ON COLUMN character_identity_rulings.previous_name IS 'Exact canonical name checked before acceptance; retained as an authored alias.';
COMMENT ON COLUMN character_identity_rulings.new_name IS 'Revealed canonical name accepted on the same character row.';
COMMENT ON COLUMN character_identity_rulings.evidence IS 'Literal finished-narrative quotation containing the revealed name.';
COMMENT ON COLUMN character_identity_rulings.generation_session_id IS 'Actual accepting generation session; does not infer a provider attempt ordinal.';
COMMENT ON COLUMN character_identity_rulings.created_at IS 'Wall-clock time the accepted ruling was recorded.';
