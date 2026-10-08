-- Migration 145: Routine-Anchor Custody Ledger and Unknown Schedules (issue #783)
--
-- Slice S1a of #783 (owner ruling, Arachne sequence 39: build; decisions
-- 783-Q1 dedicated ledger table and 783-Q9 NULL schedule). It adds the
-- provenance carrier that the custody function in
-- nexus/agents/orrery/routine_anchors.py writes, and lets a schedule be
-- unknown. Nothing calls the custody function yet; the writer slices
-- (783-S2, S3, S4, S5, S7) add the call sites.
--
-- Facts at 364fef4b:
--   character_routine_anchors is created by
--   migrations/056_orrery_routine_anchors.py:58-94. schedule is
--   jsonb NOT NULL DEFAULT '{}' (:67), and its comment says "Empty JSON means
--   always due" (:119-123), so there is no encoding for an unknown schedule.
--   source (:68, comment :124-125) is the only provenance: free text, with no
--   chunk, event, story time or history; updated_at is wall clock.
--   No runtime writer exists. The only inserts are
--   scripts/backfill_routine_anchors.py:235-241,
--   scripts/seed_slot2_routine_anchors.py:87-93, tests/pg_fixtures.py:1331
--   (seed_routine_anchor) and
--   tests/test_orrery/test_claim_birth_coverage_pg.py:234.
--   Only the foreign keys (056 :60-64) and the two CHECKs (:72-93) constrain
--   a write. Nothing refuses a zone on fixed_place, works_from_home, nomadic
--   or none, or a place on zone_resolved; nothing refuses an entity that is
--   not a character; nothing checks the home that a works_from_home work
--   anchor needs (nexus/agents/orrery/substrate.py:1767-1770 and :1798-1806
--   read it); nothing checks the schedule shape. Malformed hours fail only at
--   tick time in _minute_of_day (substrate.py:1833-1847).
--   Replay passes the table through from the checkpoint
--   (nexus/agents/orrery/replay.py:58-59, :1234-1243); the checkpoint
--   captures whole rows (nexus/agents/orrery/reconstruction.py:139-142).
--   Nothing records a change by chunk.
--   The only reader of schedule is _load_routine_anchors
--   (nexus/agents/orrery/resolver.py:870-899), which coerces NULL to {} at
--   :898; _routine_schedule_due (substrate.py:1810-1830) treats {} and a
--   schedule missing start or end as due. Both change in 783-S1c, which also
--   updates the schedule comment below in its own comment migration.
--   Precedents for the clock refusal: _require_accepting_world_time
--   (nexus/agents/orrery/retrograde_maturation.py:387-400) and
--   _require_chunk_world_time_sync (nexus/api/commit_handler_sync.py:144-157)
--   refuse a chunk without chunk_metadata.world_time; state_delta_log.writer
--   is CHECKed to skald_state_update or wizard_seed, and the Gaia commit
--   writes skald_state_update (commit_handler_sync.py:1050, :1089).
--   Genesis deletes places and zones (nexus/api/new_story_db_mapper.py:
--   569-586). An anchor's place_id/zone_id is ON DELETE SET NULL (056
--   :63-64), so a fixed_place or zone_resolved anchor makes that delete fail
--   on the CHECK. That loud failure stays: the ledger has no foreign key to
--   places or zones, no ON DELETE action and no trigger.
--   Fleet, read-only on 2026-10-07: 0 rows in character_routine_anchors on
--   NEXUS_template and save_01..save_05, all six at migration 143.
--
-- Rows written outside custody keep last_log_id NULL. Dropping the schedule
-- default makes an insert that omits schedule store NULL (unknown) instead
-- of {}; the resolver still reads NULL as {} until 783-S1c lands.
--
-- Locks: the two ALTER TABLE statements take ACCESS EXCLUSIVE on
-- character_routine_anchors (0 rows on the fleet), which the resolver reads
-- on every tick, until the transaction commits; the rewrite-free changes
-- last milliseconds once the lock is granted. The new foreign keys of
-- character_routine_anchor_log take SHARE ROW EXCLUSIVE on entities,
-- narrative_chunks and world_events until commit; that blocks writers to
-- those tables (every turn commit and every mint) but not readers. The
-- runner executes this file as one transaction after
-- SET LOCAL nexus.write_producer = 'migration' (scripts/migrate.py:330-335).
-- The lock_timeout below bounds each lock request, not the transaction: a
-- run that meets an open transaction waits up to five seconds, new requests
-- queue behind it for that long, and then the run fails, the queue drains,
-- and the run is repeated later (as migrations 138 and 139 do). Apply it
-- with no turn in flight and no idle-in-transaction session on
-- character_routine_anchors, entities, narrative_chunks or world_events.

SET LOCAL lock_timeout = '5s';

CREATE TYPE orrery_routine_anchor_writer AS ENUM (
    'skald_state_update',
    'retrograde_expansion',
    'retrograde_maturation',
    'relocation_arrival',
    'offline_ladder'
);

CREATE TABLE character_routine_anchor_log (
    id bigserial PRIMARY KEY,
    character_entity_id bigint NOT NULL REFERENCES entities(id),
    anchor_type orrery_routine_anchor_type NOT NULL,
    operation text NOT NULL CHECK (operation IN ('upsert', 'clear')),
    writer_kind orrery_routine_anchor_writer NOT NULL,
    source_chunk_id bigint NOT NULL REFERENCES narrative_chunks(id),
    chunk_sequence integer NOT NULL CHECK (chunk_sequence >= 1),
    source_event_id bigint REFERENCES world_events(id),
    world_time timestamptz NOT NULL,
    before_image jsonb,
    after_image jsonb,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (source_chunk_id, chunk_sequence),
    CHECK ((operation = 'upsert') = (after_image IS NOT NULL)),
    CHECK (operation = 'upsert' OR before_image IS NOT NULL)
);

CREATE INDEX ix_character_routine_anchor_log_anchor
    ON character_routine_anchor_log (character_entity_id, anchor_type, id);

ALTER TABLE character_routine_anchors
    ADD COLUMN last_log_id bigint REFERENCES character_routine_anchor_log(id);

ALTER TABLE character_routine_anchors
    ALTER COLUMN schedule DROP NOT NULL,
    ALTER COLUMN schedule DROP DEFAULT;

COMMENT ON TYPE orrery_routine_anchor_writer IS
    'Writer of one routine-anchor custody change: skald_state_update (the Gaia state-update commit), retrograde_expansion (wizard-time Retrograde, the genesis writer), retrograde_maturation, relocation_arrival (the verified arrival that completes an accepted relocation), offline_ladder (the reviewed offline backfill and seed scripts).';

COMMENT ON TABLE character_routine_anchor_log IS
    'Append-only history of every routine-anchor upsert and clear written through custody (nexus.agents.orrery.routine_anchors), one row per change, inserted in the transaction of the change, ordered by source_chunk_id, then chunk_sequence.';
COMMENT ON COLUMN character_routine_anchor_log.id IS
    'Ledger row identifier.';
COMMENT ON COLUMN character_routine_anchor_log.character_entity_id IS
    'Character entity whose anchor changed.';
COMMENT ON COLUMN character_routine_anchor_log.anchor_type IS
    'Anchor that changed (home or work).';
COMMENT ON COLUMN character_routine_anchor_log.operation IS
    'upsert writes the anchor in after_image; clear deletes the anchor, which returns it to unknown.';
COMMENT ON COLUMN character_routine_anchor_log.writer_kind IS
    'Custody writer that made the change.';
COMMENT ON COLUMN character_routine_anchor_log.source_chunk_id IS
    'Accepted chunk the change belongs to; replay applies it at this chunk.';
COMMENT ON COLUMN character_routine_anchor_log.chunk_sequence IS
    'Order of the change among the changes with the same source_chunk_id, from 1.';
COMMENT ON COLUMN character_routine_anchor_log.source_event_id IS
    'World event that caused the change, when the writer names one; NULL otherwise.';
COMMENT ON COLUMN character_routine_anchor_log.world_time IS
    'Story clock of the change: chunk_metadata.world_time of source_chunk_id when custody wrote it.';
COMMENT ON COLUMN character_routine_anchor_log.before_image IS
    'The anchor before the change as an object with the keys mobility_policy, place_id, zone_id and schedule; NULL when no anchor existed.';
COMMENT ON COLUMN character_routine_anchor_log.after_image IS
    'The anchor after an upsert, in the before_image shape; NULL for a clear.';
COMMENT ON COLUMN character_routine_anchor_log.recorded_at IS
    'Operational wall-clock insert time; never story time.';

COMMENT ON COLUMN character_routine_anchors.last_log_id IS
    'character_routine_anchor_log row of the latest custody upsert of this anchor; NULL when the row was written outside custody.';
COMMENT ON COLUMN character_routine_anchors.schedule IS
    'Authored timing as a JSON object, or NULL when the timing is unknown. {"always": true} is authored always-due. Otherwise the keys are weekdays (Python weekday() numbers, 0=Monday through 6=Sunday; absent means every day), start and end (zero-padded HH:MM; an end earlier than the start crosses midnight). A schedule without start or end keeps its known keys and has unknown hours.';
COMMENT ON COLUMN character_routine_anchors.source IS
    'Writer label: the orrery_routine_anchor_writer value for a row written through custody; free text for a row written outside it.';
