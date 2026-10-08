-- Migration 144: Loud NULL-Base Failure and the Fixed base_timestamp (issue #778, slice S1b)
--
-- Decisions 778-Q8 (A) and 778-Q3 (B) on #778: a chunk_metadata write raises
-- while global_variables.base_timestamp is NULL or its row is missing (no
-- wall-clock fallback), and base_timestamp cannot change once chunk_metadata
-- holds a row.
--
-- What is wrong before this file (code at 364fef4b, read on 2026-10-07):
--   refresh_world_time_from_chunk()
--     (migrations/140_world_clock_primary_layer.sql:86-130, identical to
--     pg_get_functiondef on NEXUS_template) stamps every chunk from
--     COALESCE((SELECT base_timestamp FROM global_variables WHERE id = true),
--     now()) (:106-111). A chunk written while the base is NULL, or while the
--     global_variables row is missing, silently carries wall-clock time. Its
--     comment documents that fallback (:147-148), and 140 left it in place by
--     name (:62-64).
--   Nothing guards global_variables.base_timestamp: the table has no user
--     trigger on NEXUS_template or save_01 (read-only pg_trigger). An edit
--     after chunks exist leaves every stored world_time on the old base until
--     the next time_delta or world_layer write re-dates them, while stored
--     event times keep the old clock. The column comment
--     (migrations/118_world_clock_identity.sql:23-24) says nothing about when
--     the base may change.
--   Production seeds the base before any chunk: the transition sets it at
--     nexus/api/new_story_db_mapper.py:609-619, before the protagonist and
--     before the Retrograde hook (:680), which writes the prologue metadata
--     (nexus/agents/orrery/retrograde_persistence.py:2575).
--   The test harness does the reverse: seed_protagonist
--     (tests/pg_fixtures.py:597-664) sets the base from NULL under chunks that
--     already exist and re-stamps them (:642-643); seed_story_clock writes the
--     base by its own SQL (:806-810). This branch moves every fixture onto one
--     base path (set_story_base) that runs before the first chunk.
--
-- Fleet (read-only SQL, 2026-10-07): save_01 and save_02 hold 1,425 chunks
-- each, save_03 40 and save_04 46, all with a base; NEXUS_template (no
-- global_variables row) and save_05 (NULL base) hold no chunks. Every database
-- is at migration 143. The final SELECT below therefore raises nowhere and
-- writes no row.
--
-- Evidence for the comments below:
--   refresh_world_time_from_chunk(): the function body in this file (early
--     return with no chunk, the bootstrap RAISE, the NULL-base RAISE, the
--     primary-only running sum in chunk_id order, the IS DISTINCT FROM write
--     guard).
--   refuse_base_timestamp_change(): the function body in this file (raises
--     while chunk_metadata holds any row) and the trigger below;
--     migrations/140_world_clock_primary_layer.sql:124-128 (the refresh
--     updates chunk_metadata.world_time only) and
--     migrations/142_world_event_occurrence_time.sql:20-21 (stored
--     world_events.world_time is the exact occurrence time, which the
--     refresh never rewrites).
--   trg_global_variables_base_timestamp_fixed: the trigger definition below
--     (BEFORE UPDATE, FOR EACH ROW, WHEN OLD.base_timestamp IS DISTINCT FROM
--     NEW.base_timestamp; no OF column list, no DELETE or INSERT event).
--   global_variables.base_timestamp: migrations/118_world_clock_identity.sql:23-24
--     (the clock at the end of the bootstrap chunk, UTC face), the refresh
--     function's NULL-base RAISE (fired by
--     trg_chunk_metadata_refresh_world_time after INSERT or UPDATE OF
--     time_delta, world_layer; 140:140-143), and the guard trigger below.
--
-- Out of scope: a refresh trigger on global_variables and re-dating stored
-- event times (778-Q3 option A); guarding DELETE or INSERT of the
-- global_variables row (the next chunk write raises on a missing row); the
-- trigger-function and time_delta comments from 140, which stay unchanged.
--
-- Locks: DROP TRIGGER takes ACCESS EXCLUSIVE and CREATE TRIGGER takes SHARE
-- ROW EXCLUSIVE on global_variables, the one-row table every turn reads; the
-- final refresh reads every chunk_metadata row (at most 1,425, on save_01 and
-- save_02) and writes none on the fleet. The runner applies the file in one
-- transaction, so the ACCESS EXCLUSIVE lock is held until it commits.
-- lock_timeout below bounds each lock request, not the transaction: a run that
-- meets an open transaction on global_variables waits up to five seconds for
-- the lock, and while it waits, new reads and writes of the table queue behind
-- its request; at five seconds the run fails, the queue drains, and the run is
-- repeated later. Apply it when no turn is in flight.
--
-- Rerunnable: both functions are replaced, the trigger is dropped IF EXISTS
-- and recreated, and COMMENT ON replaces the previous text. A slot holding
-- chunks under a NULL base, or with no global_variables row, fails at the
-- final SELECT, and a slot whose bootstrap chunk carries a non-zero delta
-- fails there too; either failure rolls the whole file back.

SET LOCAL lock_timeout = '5s';

CREATE OR REPLACE FUNCTION public.refresh_world_time_from_chunk()
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    bootstrap_chunk_id bigint;
    bootstrap_delta interval;
    base_time timestamptz;
BEGIN
    SELECT cm.chunk_id, cm.time_delta
    INTO bootstrap_chunk_id, bootstrap_delta
    FROM chunk_metadata cm
    ORDER BY cm.chunk_id
    LIMIT 1;

    IF bootstrap_chunk_id IS NULL THEN
        RETURN;
    END IF;

    IF COALESCE(bootstrap_delta, interval '0') <> interval '0' THEN
        RAISE EXCEPTION
            'Bootstrap chunk % has time_delta %; base_timestamp is the clock at its end, so its time_delta must be zero',
            bootstrap_chunk_id, bootstrap_delta;
    END IF;

    SELECT gv.base_timestamp
    INTO base_time
    FROM global_variables gv
    WHERE gv.id = true;

    IF base_time IS NULL THEN
        RAISE EXCEPTION
            'Story clock has no base: global_variables.base_timestamp is NULL or its row is missing while chunk_metadata holds chunk %; set base_timestamp before the first chunk',
            bootstrap_chunk_id;
    END IF;

    WITH computed AS (
        SELECT
            cm.chunk_id,
            base_time + COALESCE(
                SUM(COALESCE(cm.time_delta, interval '0'))
                    FILTER (WHERE cm.world_layer = 'primary')
                    OVER (ORDER BY cm.chunk_id),
                interval '0'
            ) AS world_time
        FROM chunk_metadata cm
    )
    UPDATE chunk_metadata cm
    SET world_time = computed.world_time
    FROM computed
    WHERE cm.chunk_id = computed.chunk_id
      AND cm.world_time IS DISTINCT FROM computed.world_time;
END;
$$;

CREATE OR REPLACE FUNCTION public.refuse_base_timestamp_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM chunk_metadata) THEN
        RAISE EXCEPTION
            'global_variables.base_timestamp is fixed once chunk_metadata holds a row: refusing to change it from % to %',
            OLD.base_timestamp, NEW.base_timestamp;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_global_variables_base_timestamp_fixed
    ON public.global_variables;
CREATE TRIGGER trg_global_variables_base_timestamp_fixed
    BEFORE UPDATE ON public.global_variables
    FOR EACH ROW
    WHEN (OLD.base_timestamp IS DISTINCT FROM NEW.base_timestamp)
    EXECUTE FUNCTION refuse_base_timestamp_change();

SELECT public.refresh_world_time_from_chunk();

COMMENT ON FUNCTION public.refresh_world_time_from_chunk() IS
    'Recomputes chunk_metadata.world_time for every chunk as global_variables.base_timestamp plus the running sum, in chunk_id order, of the time_delta of primary-layer chunks (NULL counts as zero), so a chunk of any other layer, or with a NULL world_layer, carries the mainline clock at its position. Raises when chunk_metadata holds a row and base_timestamp is NULL or its row is missing; there is no wall-clock fallback. Raises when the bootstrap chunk (the lowest chunk_id) has a time_delta other than zero or NULL, because base_timestamp is the clock at its end. Writes only rows whose world_time changes; a world_time written by the inserter is overwritten.';

COMMENT ON FUNCTION public.refuse_base_timestamp_change() IS
    'Row trigger function for trg_global_variables_base_timestamp_fixed: raises when an UPDATE changes global_variables.base_timestamp while chunk_metadata holds any row, because refresh_world_time_from_chunk() would re-date chunk metadata while stored event times keep the old clock.';

COMMENT ON TRIGGER trg_global_variables_base_timestamp_fixed ON public.global_variables IS
    'Fixes base_timestamp at genesis: BEFORE UPDATE, for each row whose base_timestamp IS DISTINCT FROM its old value (NULL included), it calls refuse_base_timestamp_change(), which raises once chunk_metadata holds a row. An update that keeps the same value passes; a DELETE or INSERT of the row does not fire it.';

COMMENT ON COLUMN public.global_variables.base_timestamp IS
    'Story clock at the end of the bootstrap chunk, stored as timestamptz whose UTC face is the story clock face. It is set before the first chunk: while it is NULL, an INSERT into chunk_metadata, or an UPDATE of its time_delta or world_layer, raises when chunk_metadata then holds a row; once chunk_metadata holds a row, it cannot change.';
