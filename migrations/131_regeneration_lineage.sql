-- Migration 131: Regeneration Lineage (issue #773)
--
-- A re-roll starts a new generation session while the pending draft it would
-- replace stays in the incubator. replaced_by_session_id (migration 121) is
-- written on that incumbent only after the replacement succeeds, so a failed,
-- in-flight, or abandoned re-roll recorded nothing about the draft it targeted.
-- The new session now names that draft from the moment it acquires the slot.
-- Existing rows keep NULL: which draft an old re-roll targeted was never
-- recorded and is not reconstructed here.

ALTER TABLE narrative_generation_sessions
    ADD COLUMN IF NOT EXISTS supersedes_session_id UUID
        REFERENCES narrative_generation_sessions(session_id);

COMMENT ON COLUMN narrative_generation_sessions.supersedes_session_id IS
    'Pending draft session this regenerate attempt was started to replace, recorded when it acquires the slot; NULL for continue attempts and pre-#773 rows.';
