-- Migration 146: Story Identity and Fork Lineage (issue #822)
--
-- No story has a durable identity. On 2026-10-07 (read-only SQL, all six
-- databases at migration 143) to_regclass('public.story_identity') and
-- to_regclass('public.story_lineage') were NULL on NEXUS_template and on
-- save_01..save_05, and git grep found no story_uuid anywhere.
--
-- What stands in for an identity today (code at 364fef4b):
--   SlotState.story_id (nexus/api/slot_state.py:100) is derived from the
--     protagonist row as player:{id}:{created_at} (:216-231), only in
--     narrative mode; SlotStateResponse.story_id
--     (nexus/api/narrative_schemas.py:324) carries it
--     (nexus/api/slot_endpoints.py:157), and the reader keys its browser
--     drafts and unconfirmed actions by [slot, story_id]
--     (ui/client/src/lib/reader-draft.ts:18-28).
--   A new story can be born into a reused database: start_setup reuses an
--     existing slot database (nexus/api/new_story_flow.py:130-138), and
--     perform_transition keeps the global_variables row while it deletes the
--     entity tables and restarts their sequences
--     (nexus/api/new_story_db_mapper.py:549-599).
--   initialize_slot_database copies only the template's seed tables
--     (scripts/new_story_setup.py:302, :363-370); clone_slot_with_data
--     replays the source verbatim (:517), and _post_clone_cleanup sets only
--     new_story (:528-535). Disposable clones (tests/pg_fixtures.py:193-238
--     and four scripts/qa_shift probes) also replay a slot verbatim.
--
-- Fleet (read-only, 2026-10-07): save_01 and save_02 each hold 1,425 chunks
-- (ids 1..1425) with slot_created_at 2026-01-14 18:22:29.574584-05 and the
-- setting title "The Zenith Pulse & Fractured Future"; save_03 (40 chunks,
-- ids 1..100) and save_04 (46 chunks, ids 1..49) share slot_created_at
-- 2026-07-30 00:49:44.071666-04; save_05 holds no chunk and no character.
--
-- This file creates the two tables and writes no row (822-Q11, 822-Q17).
-- NEXUS_template carries the tables and never a row (822-Q13). Slot
-- initialization and every wizard transition mint a row, a slot clone mints
-- a new row with a story_lineage fork row, and
-- scripts/backfill_story_identity.py mints the rows of slots that predate
-- this migration and records that save_02 forks save_01 (822-Q4).
--
-- Locks: both tables are new, so the file takes no lock on an existing
-- table. lock_timeout bounds the catalog locks all the same.

SET LOCAL lock_timeout = '5s';

CREATE TABLE public.story_identity (
    id boolean PRIMARY KEY DEFAULT TRUE CHECK (id),
    story_uuid uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    title text,
    origin text NOT NULL
        CONSTRAINT story_identity_origin_check
        CHECK (origin IN ('wizard', 'clone', 'import', 'backfill')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.story_lineage (
    child_uuid uuid NOT NULL
        REFERENCES public.story_identity (story_uuid) ON DELETE CASCADE,
    parent_uuid uuid NOT NULL,
    relation text NOT NULL
        CONSTRAINT story_lineage_relation_check CHECK (relation = 'fork'),
    source_dbname text NOT NULL,
    evidence text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (child_uuid, parent_uuid),
    CONSTRAINT story_lineage_not_self CHECK (child_uuid <> parent_uuid)
);

COMMENT ON TABLE public.story_identity IS 'The identity of the story this database holds: exactly one row in a save slot database, none in NEXUS_template. Slot initialization writes it; each wizard transition replaces it with a new story_uuid; a slot clone replaces the copied row and records the parent in story_lineage; scripts/backfill_story_identity.py writes it for a slot that predates migration 146.';
COMMENT ON COLUMN public.story_identity.id IS 'Singleton guard: always TRUE, so the table holds at most one row.';
COMMENT ON COLUMN public.story_identity.story_uuid IS 'The story''s identity. A replacement story or a clone gets a new value. The slot state reports it as story_id, and the reader keys its browser drafts by it.';
COMMENT ON COLUMN public.story_identity.title IS 'The story''s title, or NULL when none is recorded.';
COMMENT ON COLUMN public.story_identity.origin IS 'How this identity was minted: wizard (slot initialization or a wizard transition), clone (a copy of another story database), import (a story bundle import), or backfill (a story that predates migration 146).';
COMMENT ON COLUMN public.story_identity.created_at IS 'When this identity row was written.';

COMMENT ON TABLE public.story_lineage IS 'The parentage of the story in story_identity: one row for each story it was copied from. Rows are deleted with their story_identity row.';
COMMENT ON COLUMN public.story_lineage.child_uuid IS 'story_identity.story_uuid of this database''s story.';
COMMENT ON COLUMN public.story_lineage.parent_uuid IS 'story_uuid of the story it was copied from, read from the source database when the row was written; not a foreign key, because the parent lives in another database.';
COMMENT ON COLUMN public.story_lineage.relation IS 'The kind of parentage; fork (a copy that became a separate story) is the only value.';
COMMENT ON COLUMN public.story_lineage.source_dbname IS 'The database the parent story was read from when the row was written.';
COMMENT ON COLUMN public.story_lineage.evidence IS 'What establishes the parentage: the clone that made the copy, or the record the backfill cites.';
COMMENT ON COLUMN public.story_lineage.recorded_at IS 'When this row was written.';
