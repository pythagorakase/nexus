-- Migration 140: Primary-Only World Clock, Layer Refresh, Delta CHECK, and the Two-Clock Comments (issue #778)
--
-- Sketch steps 1-2 of #778: the story clock advances on primary-layer time
-- only, a world_layer edit restamps it, story time never runs backward, the
-- bootstrap chunk elapses no time, and PostgreSQL comments state both clocks.
--
-- What is wrong before this file (code at 9fff6a75, read on 2026-09-30):
--   refresh_world_time_from_chunk() (migrations/023_orrery_schema.py:721-746,
--     identical to pg_get_functiondef on NEXUS_template) sets every row to
--     COALESCE(base_timestamp, now()) plus the running SUM of time_delta over
--     all layers, so a flashback's delta advances the mainline clock.
--   trg_chunk_metadata_refresh_world_time (023_orrery_schema.py:756-761) fires
--     AFTER INSERT OR UPDATE OF time_delta ... FOR EACH STATEMENT, so a
--     world_layer edit does not restamp the clock.
--   chunk_metadata has one CHECK (chunk_metadata_scene_weather_check); nothing
--     stops a negative time_delta.
--   Migration 118 defines base_timestamp as the clock at the end of the
--     bootstrap chunk (migrations/118_world_clock_identity.sql:17-24), so a
--     non-zero bootstrap delta counts twice; nothing enforces it.
--     seed_committed_chunk defaults to one minute (tests/pg_fixtures.py:665-672),
--     so its first chunk on an empty clone breaks the contract.
--   The function comment documents the all-layer sum
--     (migrations/135_schema_docs_backfill.sql:188-189); the trigger-function
--     comment names only UPDATE OF time_delta (:191-192);
--     orrery_resolutions.tick_chunk_id
--     (migrations/127_schema_documentation.sql:280) and
--     world_events.tick_chunk_id (:418) do not state the tick clock's role.
--   tests/test_world_clock_contract_pg.py:96-99 pins the inclusive semantics:
--     deltas primary 0, primary 7, flashback 3, retrograde 0 give
--     (0, 7, 10, 10) minutes.
--   tests/pg_fixtures.py:730-738 (_require_need_clock_anchor) and :798-806
--     (seed_story_clock) compute the head clock with the all-layer sum.
--
-- Fleet (read-only SQL, 2026-09-30): no negative time_delta anywhere. Every
-- bootstrap row carries 00:00:00: chunk 1 is extradiegetic on save_01 and
-- save_02 and retrograde on save_03, save_04, and ref_codex_bakeoff_2026_07.
-- Every non-primary row carries a zero delta. A primary-only recompute differs
-- from stored world_time on 0 rows of save_01..save_04 and of the reference
-- corpus. NEXUS_template and save_05 hold no chunks. No world_layer is NULL.
-- On the fleet the final SELECT below therefore writes no row.
--
-- Evidence for the comments below:
--   refresh_world_time_from_chunk(): the function body in this file
--     (base_timestamp or now(), primary-only running sum in chunk_id order,
--     the bootstrap RAISE, the IS DISTINCT FROM write guard).
--   refresh_world_time_from_chunk_trigger(): PERFORM
--     refresh_world_time_from_chunk() (023_orrery_schema.py:748-754, not
--     replaced here) and the trigger definition below;
--     nexus/api/commit_handler_sync.py:144-157 (_require_chunk_world_time_sync)
--     reads the trigger-authored world_time after insertion.
--   trg_chunk_metadata_refresh_world_time: the trigger definition below
--     (statement-level, INSERT or UPDATE OF time_delta, world_layer; PostgreSQL
--     fires a statement trigger even when the statement affects no row, and
--     fires UPDATE OF only when a listed column is in the SET list).
--   chunk_metadata_time_delta_nonnegative: the CHECK below (NULL passes).
--   world_events.tick_chunk_id: nexus/agents/orrery/propagation.py:363
--     (COALESCE(event.world_time, metadata.world_time), with metadata joined
--     on event.tick_chunk_id at :367-368) and migrations/083_claim_propagation_ledger.sql:14-15
--     (world_events.world_time is the exact occurrence time; NULL rows inherit
--     the tick chunk world time).
--
-- Out of scope: the now() fallback for a NULL base_timestamp stays (the
-- comment still documents it); no DELETE refresh; world_layer stays nullable;
-- narrative_view's definition and the base_timestamp comment are unchanged.
--
-- Locks: ADD CONSTRAINT holds an ACCESS EXCLUSIVE lock on chunk_metadata
-- while it scans every row to validate the CHECK (at most 1,425 rows, on
-- save_01 and save_02); DROP TRIGGER takes ACCESS EXCLUSIVE and CREATE
-- TRIGGER takes SHARE ROW EXCLUSIVE on the same table (both already covered
-- by the ALTER TABLE lock), and the final refresh reads every row. The
-- runner applies the file in one transaction, so the ACCESS EXCLUSIVE lock is
-- held until it commits. lock_timeout below bounds each lock request, not the
-- transaction: a run that meets an open transaction on chunk_metadata waits up
-- to five seconds for the lock, and while it waits, new reads and writes of
-- the table queue behind its request; at five seconds the run fails, the queue
-- drains, and the run is repeated later. Apply it when no turn is in flight.
--
-- Rerunnable: the function is replaced, the CHECK and the trigger are dropped
-- IF EXISTS and recreated, and COMMENT ON replaces the previous text. A slot
-- holding a negative delta fails at ADD CONSTRAINT, and a slot whose bootstrap
-- chunk carries a non-zero delta fails at the final SELECT; either failure
-- rolls the whole file back.

SET LOCAL lock_timeout = '5s';

CREATE OR REPLACE FUNCTION public.refresh_world_time_from_chunk()
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    bootstrap_chunk_id bigint;
    bootstrap_delta interval;
BEGIN
    SELECT cm.chunk_id, cm.time_delta
    INTO bootstrap_chunk_id, bootstrap_delta
    FROM chunk_metadata cm
    ORDER BY cm.chunk_id
    LIMIT 1;

    IF FOUND AND COALESCE(bootstrap_delta, interval '0') <> interval '0' THEN
        RAISE EXCEPTION
            'Bootstrap chunk % has time_delta %; base_timestamp is the clock at its end, so its time_delta must be zero',
            bootstrap_chunk_id, bootstrap_delta;
    END IF;

    WITH baseline AS (
        SELECT COALESCE(
            (SELECT base_timestamp FROM global_variables WHERE id = true),
            now()
        ) AS base_time
    ),
    computed AS (
        SELECT
            cm.chunk_id,
            baseline.base_time + COALESCE(
                SUM(COALESCE(cm.time_delta, interval '0'))
                    FILTER (WHERE cm.world_layer = 'primary')
                    OVER (ORDER BY cm.chunk_id),
                interval '0'
            ) AS world_time
        FROM chunk_metadata cm
        CROSS JOIN baseline
    )
    UPDATE chunk_metadata cm
    SET world_time = computed.world_time
    FROM computed
    WHERE cm.chunk_id = computed.chunk_id
      AND cm.world_time IS DISTINCT FROM computed.world_time;
END;
$$;

ALTER TABLE public.chunk_metadata
    DROP CONSTRAINT IF EXISTS chunk_metadata_time_delta_nonnegative;
ALTER TABLE public.chunk_metadata
    ADD CONSTRAINT chunk_metadata_time_delta_nonnegative
    CHECK (time_delta >= interval '0');

DROP TRIGGER IF EXISTS trg_chunk_metadata_refresh_world_time
    ON public.chunk_metadata;
CREATE TRIGGER trg_chunk_metadata_refresh_world_time
    AFTER INSERT OR UPDATE OF time_delta, world_layer ON public.chunk_metadata
    FOR EACH STATEMENT
    EXECUTE FUNCTION refresh_world_time_from_chunk_trigger();

SELECT public.refresh_world_time_from_chunk();

COMMENT ON FUNCTION public.refresh_world_time_from_chunk() IS
    'Recomputes chunk_metadata.world_time for every chunk as global_variables.base_timestamp (now() if absent) plus the running sum, in chunk_id order, of the time_delta of primary-layer chunks (NULL counts as zero), so a chunk of any other layer, or with a NULL world_layer, carries the mainline clock at its position. Raises when the bootstrap chunk (the lowest chunk_id) has a time_delta other than zero or NULL, because base_timestamp is the clock at its end. Writes only rows whose world_time changes; a world_time written by the inserter is overwritten.';

COMMENT ON FUNCTION public.refresh_world_time_from_chunk_trigger() IS
    'Statement trigger function for trg_chunk_metadata_refresh_world_time (AFTER INSERT OR UPDATE OF time_delta, world_layer on chunk_metadata): calls refresh_world_time_from_chunk(); commit_handler_sync reads the resulting trigger-authored world_time after insertion.';

COMMENT ON TRIGGER trg_chunk_metadata_refresh_world_time ON public.chunk_metadata IS
    'Restamps chunk_metadata.world_time through refresh_world_time_from_chunk() after every INSERT statement and every UPDATE statement with time_delta or world_layer in its SET list, even one that inserts or changes no row. A DELETE or TRUNCATE does not fire it.';

COMMENT ON CONSTRAINT chunk_metadata_time_delta_nonnegative ON public.chunk_metadata IS
    'Story time never runs backward within a chunk: time_delta is NULL or at least zero.';

COMMENT ON COLUMN public.chunk_metadata.time_delta IS
    'Story time elapsing during this chunk, NULL or at least zero. Only a primary-layer delta advances the mainline clock, and world_time is that clock at the chunk''s end; a delta on any other layer leaves the mainline clock unchanged. The bootstrap chunk (lowest chunk_id) carries zero or NULL, because base_timestamp is the clock at its end.';

COMMENT ON COLUMN public.chunk_metadata.world_time IS
    'The canonical story clock is chunk_metadata.world_time: for a primary-layer chunk, the mainline clock at the end of the chunk; for a chunk of any other layer, the mainline clock at its position. Only primary-layer time_delta advances it; base_timestamp is the clock at the end of the bootstrap chunk. It is stored as timestamptz whose UTC face is the story clock face.';
COMMENT ON VIEW public.narrative_view IS
    'The canonical story clock is chunk_metadata.world_time: for a primary-layer chunk, the mainline clock at the end of the chunk; for a chunk of any other layer, the mainline clock at its position. Only primary-layer time_delta advances it; base_timestamp is the clock at the end of the bootstrap chunk. It is stored as timestamptz whose UTC face is the story clock face.';
COMMENT ON COLUMN public.narrative_view.world_time IS
    'The canonical story clock is chunk_metadata.world_time: for a primary-layer chunk, the mainline clock at the end of the chunk; for a chunk of any other layer, the mainline clock at its position. Only primary-layer time_delta advances it; base_timestamp is the clock at the end of the bootstrap chunk. It is stored as timestamptz whose UTC face is the story clock face.';

COMMENT ON COLUMN public.orrery_resolutions.tick_chunk_id IS
    'Tick chunk under which the resolution was applied. Ticks are the turn clock, which serves ordering, replay, exposure fairness, habituation, and narration cadence; the story time at this tick is chunk_metadata.world_time of this chunk.';

COMMENT ON COLUMN public.world_events.tick_chunk_id IS
    'Tick chunk attributed to the event by its writer. Ticks are the turn clock, which serves ordering, replay, exposure fairness, habituation, and narration cadence; the event''s story time is world_events.world_time, and a NULL world_time inherits chunk_metadata.world_time of this chunk.';
