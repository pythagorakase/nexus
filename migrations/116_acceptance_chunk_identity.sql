-- Drafts have a session identity; chunk identities exist only after acceptance.
ALTER TABLE incubator ALTER COLUMN chunk_id DROP NOT NULL;
UPDATE incubator SET chunk_id = NULL;
UPDATE narrative_generation_sessions gs
SET chunk_id = NULL
FROM incubator i
WHERE gs.session_id = i.session_id;
COMMENT ON COLUMN incubator.chunk_id IS
    'NULL while provisional; assigned from narrative_chunks INSERT RETURNING id inside acceptance before the incubator row is deleted.';
COMMENT ON COLUMN narrative_generation_sessions.chunk_id IS
    'Accepted narrative_chunks id, assigned in the accepting transaction; NULL for drafts generated under the acceptance identity contract. Historical sessions may retain legacy predicted ids.';
