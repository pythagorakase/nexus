-- Migration 138: Adopt Three Unowned Indexes and the chunk_metadata.scene Column (issue #810)
--
-- Every object below exists on NEXUS_template and save_01..save_05, but no
-- migration creates it, so a database built by the runner alone depends on
-- run-time code and legacy scripts to have them. On 2026-09-30 pg_indexes
-- showed these definitions, identical on all six databases:
--   narrative_chunks_text_idx
--     CREATE INDEX narrative_chunks_text_idx ON public.narrative_chunks
--     USING gin (to_tsvector('english'::regconfig, raw_text))
--   idx_chunk_metadata_scene
--     CREATE INDEX idx_chunk_metadata_scene ON public.chunk_metadata
--     USING btree (scene)
--   idx_chunk_metadata_season_episode_scene
--     CREATE INDEX idx_chunk_metadata_season_episode_scene
--     ON public.chunk_metadata USING btree (season, episode, scene)
-- and chunk_metadata.scene as integer, comment 'Scene number within the
-- episode'. git grep over migrations/ finds no statement that adds the
-- column (migration 001 only names it in a prose list of the manual schema).
--
-- Former owners (at c8dd8c85):
--   narrative_chunks_text_idx: setup_database_indexes, run on every
--     DatabaseManager construction
--     (nexus/agents/memnon/utils/db_access.py:478).
--   idx_chunk_metadata_scene, idx_chunk_metadata_season_episode_scene:
--     scripts/extract_scene_numbers.py:171,174 and
--     scripts/update_scene_numbers.py:84,87.
--   chunk_metadata.scene: scripts/extract_scene_numbers.py:163 and
--     scripts/update_scene_numbers.py:76 (each with its own comment text,
--     which the live comment no longer matches).
-- The run-time statement in setup_database_indexes and the legacy scripts
-- keep their IF NOT EXISTS DDL for now; this migration makes them redundant.
--
-- A database that lacks an object gets exactly the live definition. A
-- database that has them all changes nothing: ADD COLUMN IF NOT EXISTS and
-- CREATE INDEX IF NOT EXISTS skip, and COMMENT ON writes the text it already
-- has. IF NOT EXISTS matches by name only, so the final block reads the
-- catalog and refuses, naming the object, when a same-named index has
-- another definition or the column has another type.
--
-- Locks on a complete database: ADD COLUMN IF NOT EXISTS takes an ACCESS
-- EXCLUSIVE lock on chunk_metadata before it finds the column, and each
-- CREATE INDEX IF NOT EXISTS takes a SHARE lock on its table before it finds
-- the index; both last milliseconds when nothing else holds the table. The
-- runner applies the file in one transaction, so lock_timeout below makes a
-- run that meets an open transaction on chunk_metadata fail at once, to be
-- rerun, instead of queuing every new read and write behind its request.
-- Apply it while the gateway is quiet.

SET LOCAL lock_timeout = '5s';

ALTER TABLE public.chunk_metadata ADD COLUMN IF NOT EXISTS scene integer;

COMMENT ON COLUMN public.chunk_metadata.scene IS 'Scene number within the episode';

CREATE INDEX IF NOT EXISTS narrative_chunks_text_idx
    ON public.narrative_chunks USING gin (to_tsvector('english'::regconfig, raw_text));

CREATE INDEX IF NOT EXISTS idx_chunk_metadata_scene
    ON public.chunk_metadata USING btree (scene);

CREATE INDEX IF NOT EXISTS idx_chunk_metadata_season_episode_scene
    ON public.chunk_metadata USING btree (season, episode, scene);

DO $$
DECLARE
    mismatches text;
    scene_type text;
BEGIN
    WITH expected (indexname, indexdef) AS (
        VALUES
            ('narrative_chunks_text_idx',
             'CREATE INDEX narrative_chunks_text_idx ON public.narrative_chunks USING gin (to_tsvector(''english''::regconfig, raw_text))'),
            ('idx_chunk_metadata_scene',
             'CREATE INDEX idx_chunk_metadata_scene ON public.chunk_metadata USING btree (scene)'),
            ('idx_chunk_metadata_season_episode_scene',
             'CREATE INDEX idx_chunk_metadata_season_episode_scene ON public.chunk_metadata USING btree (season, episode, scene)')
    )
    SELECT string_agg(
               format('%s (found %s)', e.indexname, coalesce(i.indexdef, 'no index')),
               '; '
               ORDER BY e.indexname
           )
    INTO mismatches
    FROM expected AS e
    LEFT JOIN pg_indexes AS i
      ON i.schemaname = 'public' AND i.indexname = e.indexname
    WHERE i.indexdef IS DISTINCT FROM e.indexdef;

    IF mismatches IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 138: an index has another definition than the one it adopts: %',
            mismatches;
    END IF;

    SELECT format_type(a.atttypid, a.atttypmod)
    INTO scene_type
    FROM pg_attribute AS a
    WHERE a.attrelid = 'public.chunk_metadata'::regclass
      AND a.attname = 'scene'
      AND NOT a.attisdropped;

    IF scene_type IS DISTINCT FROM 'integer' THEN
        RAISE EXCEPTION
            'Migration 138: chunk_metadata.scene is %, not integer',
            coalesce(scene_type, 'missing');
    END IF;
END $$;
