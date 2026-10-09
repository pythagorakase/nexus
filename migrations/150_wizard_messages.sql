-- Migration 150: Store Every Wizard Transcript in Its Slot Database (#776)
--
-- At bf229051, conversations.py:33-46 and :156-169 choose hosted OpenAI,
-- TEST memory or state_dir JSON files by provider. The memory store loses
-- messages on process exit and wizard_transcript.py:7-48 embeds provenance
-- in text. new_story_flow.py:157-160 creates provider threads; :173-335 copies
-- them during model switching. wizard_chat.py:147-232 reconciles a separate
-- introduction claim because transcript and choices cannot commit together.
-- setup_endpoints.py:73-79 likewise splits the welcome message from choices.
-- assets.new_story_creator.thread_id is free text; there is no transcript
-- table on the pre-150 schema. This table replaces every provider store.
--
-- Historical read-only survey, 2026-10-07: only save_05 had a hosted conv_
-- cache, with unconfirmed setting and character, updated 2026-09-23. It had
-- no chunk, incubator, character or genesis_runs row, and no global setting
-- or base timestamp. Removing that cache therefore leaves an empty slot
-- (nexus/api/slot_state.py:195-251). save_01 was locked. save_01..save_04 and
-- NEXUS_template had no cache. These are not current landing admission.
-- Decision 776-Q1 (q_776_legacy=discard) requires a fresh all-slot survey
-- before merge; locked-slot rules apply. No hosted object is read or deleted.
-- Retired local/test/NULL thread IDs refuse the whole migration; UUID rows
-- stay unchanged. The trait reset matches new_story_cache.py:1319-1327.
--
-- The runner applies this file in one transaction. CREATE TABLE locks only
-- the new relation; the cache DELETE and trait UPDATEs lock affected rows
-- and take ROW EXCLUSIVE table locks. Concurrent wizard writers may wait on
-- those rows until commit. lock_timeout bounds each lock acquisition to five
-- seconds, not the transaction: a conflicting transaction causes refusal and
-- rollback of the new table and cache reset. Apply while the gateway is quiet,
-- after the required survey, with the coordinator's locked-slot procedure.

SET LOCAL lock_timeout = '5s';

CREATE TABLE assets.wizard_messages (
    conversation_id uuid NOT NULL,
    seq integer NOT NULL CHECK (seq > 0),
    role text NOT NULL CHECK (role IN ('user', 'assistant')),
    origin text CHECK (origin IN ('user', 'wizard_control')),
    content text NOT NULL,
    phase text NOT NULL CHECK (phase IN ('setting', 'character', 'seed', 'ready')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    superseded_at timestamptz,
    PRIMARY KEY (conversation_id, seq),
    CHECK ((role = 'user') = (origin IS NOT NULL))
);

DO $$
DECLARE
    legacy_thread text;
BEGIN
    SELECT thread_id INTO legacy_thread
    FROM assets.new_story_creator WHERE id = TRUE;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    IF legacy_thread LIKE 'conv\_%' THEN
        DELETE FROM assets.new_story_creator WHERE id = TRUE;
        UPDATE assets.traits SET is_selected = FALSE, rationale = NULL,
            cold_start_relationships = 'allowed',
            preexisting_relationship_targets = '[]'::jsonb WHERE id <= 10;
        UPDATE assets.traits SET name = 'wildcard', rationale = NULL WHERE id = 11;
        RAISE NOTICE
            'Migration 150 discarded hosted wizard thread % (q_776_legacy=discard)',
            legacy_thread;
    ELSIF legacy_thread IS NULL OR legacy_thread !~
        '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    THEN
        RAISE EXCEPTION
            'Wizard thread % has its transcript in a retired local store; finish or reset that wizard before migration 150',
            COALESCE(legacy_thread, '<NULL>');
    END IF;
END;
$$;

COMMENT ON TABLE assets.wizard_messages IS 'Wizard transcript for every provider, one row per message, keyed by the conversation UUID that assets.new_story_creator.thread_id names; add_wizard_message and record_wizard_reply write it under the wizard cache row lock. Rows are kept after the wizard cache is cleared.';
COMMENT ON COLUMN assets.wizard_messages.conversation_id IS 'Conversation UUID minted by start_setup; assets.new_story_creator.thread_id holds it as text while the wizard runs.';
COMMENT ON COLUMN assets.wizard_messages.seq IS 'Position in the conversation from 1, assigned as one more than the highest seq while the writer holds the wizard cache row lock.';
COMMENT ON COLUMN assets.wizard_messages.role IS 'user for player or wizard-control input; assistant for a wizard reply.';
COMMENT ON COLUMN assets.wizard_messages.origin IS 'Provenance of a user message: user for player text, wizard_control for a message the client sends for the player. NULL exactly for assistant messages.';
COMMENT ON COLUMN assets.wizard_messages.content IS 'Model-facing message text, stored verbatim.';
COMMENT ON COLUMN assets.wizard_messages.phase IS 'WizardCache.current_phase() in the writing transaction (setting, character, seed or ready); written at message time and never recomputed.';
COMMENT ON COLUMN assets.wizard_messages.created_at IS 'Operational wall-clock insert time; never story time.';
COMMENT ON COLUMN assets.wizard_messages.superseded_at IS 'NULL in migration 150; the #776 undo slice (Decision 776-Q2: mark superseded) writes it. Transcript readers skip rows where it is set.';
COMMENT ON COLUMN assets.new_story_creator.thread_id IS 'Wizard conversation UUID as text, written by start_setup; assets.wizard_messages holds its transcript. Migration 150 removed rows that named a hosted OpenAI conversation (conv_ prefix).';
