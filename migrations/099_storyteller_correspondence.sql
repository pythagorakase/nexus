-- Migration 099: immutable private storyteller correspondence (issue #617).
--
-- Replay relationship: these tables are deliberately excluded from the
-- world-state replay ledger. Correspondence is authorial planning, not world
-- canon. Its history is instead chunk-versioned directly: accepted letters
-- and digest versions reference narrative_chunks with ON DELETE CASCADE, so a
-- chunk rewind removes that exchange and restores the preceding digest as the
-- latest visible version. scripts/replay_state.py --verify checks these
-- provenance and orphan invariants alongside the world-state replay audit.
-- Digest integrity relies on accepted chunks being append-only, with any
-- administrative rewind deleting a suffix. Non-suffix chunk surgery must
-- rebuild correspondence digests before the slot returns to production.

CREATE TABLE IF NOT EXISTS storyteller_correspondence_letters (
    id BIGSERIAL PRIMARY KEY,
    chunk_id BIGINT NOT NULL
        REFERENCES narrative_chunks(id) ON DELETE CASCADE,
    seat TEXT NOT NULL
        CHECK (seat IN ('writer', 'gaia', 'single_pass')),
    body TEXT NOT NULL CHECK (btrim(body) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chunk_id, seat)
);

COMMENT ON TABLE storyteller_correspondence_letters IS
    'Accepted, player-invisible storyteller letters; excluded from world-state replay because they are authorial intent, not canon.';
COMMENT ON COLUMN storyteller_correspondence_letters.id IS
    'Stable append-only journal row identifier.';
COMMENT ON COLUMN storyteller_correspondence_letters.chunk_id IS
    'Accepted narrative chunk whose turn emitted this letter; chunk deletion removes the exchange for undo.';
COMMENT ON COLUMN storyteller_correspondence_letters.seat IS
    'Emitting storyteller seat: writer, gaia, or the combined single-pass mind.';
COMMENT ON COLUMN storyteller_correspondence_letters.body IS
    'Immutable private letter text; never copied into narrative text or embeddings.';
COMMENT ON COLUMN storyteller_correspondence_letters.created_at IS
    'Database time at acceptance-time journal insertion.';

CREATE INDEX IF NOT EXISTS idx_storyteller_correspondence_letters_chunk
    ON storyteller_correspondence_letters (chunk_id, id);

CREATE OR REPLACE FUNCTION reject_storyteller_letter_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'storyteller correspondence letters are immutable; append a new chunk exchange';
END;
$$;

DROP TRIGGER IF EXISTS storyteller_correspondence_letters_immutable
    ON storyteller_correspondence_letters;
CREATE TRIGGER storyteller_correspondence_letters_immutable
BEFORE UPDATE ON storyteller_correspondence_letters
FOR EACH ROW EXECUTE FUNCTION reject_storyteller_letter_update();

CREATE TABLE IF NOT EXISTS storyteller_correspondence_digest_versions (
    accepting_chunk_id BIGINT PRIMARY KEY
        REFERENCES narrative_chunks(id) ON DELETE CASCADE,
    compacted_through_chunk_id BIGINT NOT NULL
        REFERENCES narrative_chunks(id) ON DELETE CASCADE,
    digest TEXT NOT NULL CHECK (btrim(digest) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (compacted_through_chunk_id <= accepting_chunk_id)
);

COMMENT ON TABLE storyteller_correspondence_digest_versions IS
    'Chunk-versioned private correspondence digests; latest surviving accepting chunk is current, so undo restores the previous version.';
COMMENT ON COLUMN storyteller_correspondence_digest_versions.accepting_chunk_id IS
    'Accepted chunk that triggered this post-accept compaction version.';
COMMENT ON COLUMN storyteller_correspondence_digest_versions.compacted_through_chunk_id IS
    'Newest exchange fully represented by this digest; later letters remain verbatim.';
COMMENT ON COLUMN storyteller_correspondence_digest_versions.digest IS
    'Complete superseding authorial digest returned by the compaction model.';
COMMENT ON COLUMN storyteller_correspondence_digest_versions.created_at IS
    'Database time at digest-version insertion.';

CREATE INDEX IF NOT EXISTS idx_storyteller_correspondence_digest_compacted
    ON storyteller_correspondence_digest_versions (compacted_through_chunk_id);

CREATE OR REPLACE FUNCTION reject_storyteller_digest_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'storyteller correspondence digests are immutable; append a new version';
END;
$$;

DROP TRIGGER IF EXISTS storyteller_correspondence_digest_immutable
    ON storyteller_correspondence_digest_versions;
CREATE TRIGGER storyteller_correspondence_digest_immutable
BEFORE UPDATE ON storyteller_correspondence_digest_versions
FOR EACH ROW EXECUTE FUNCTION reject_storyteller_digest_update();

ALTER TABLE incubator
    ADD COLUMN IF NOT EXISTS correspondence_writer_letter TEXT,
    ADD COLUMN IF NOT EXISTS correspondence_gaia_letter TEXT;

COMMENT ON COLUMN incubator.correspondence_writer_letter IS
    'Player-invisible provisional writer or single-pass letter; copied to the immutable journal only when this incubator row is accepted.';
COMMENT ON COLUMN incubator.correspondence_gaia_letter IS
    'Player-invisible provisional Gaia reply; copied to the immutable journal only when this incubator row is accepted.';
