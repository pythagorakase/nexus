-- Migration 153: Refuse the Chunk Slug Bound Loudly (#1069)
--
-- At c7ae2988, no migration defines public.set_chunk_slug(); its only
-- migration text is the comment at migrations/135_schema_docs_backfill.sql:
-- 200-201. NEXUS_template and save_01..save_05 (all stamped 151) carry the
-- same body: NEW.slug := 'S' || TO_CHAR(NEW.season, 'FM00') || 'E' ||
-- TO_CHAR(NEW.episode, 'FM00') || '_' || TO_CHAR(NEW.scene, 'FM000').
-- trg_chunk_metadata_slug fires BEFORE INSERT OR UPDATE ... FOR EACH ROW with
-- no column list. slug is character varying(10) under UNIQUE (slug)
-- (unique_slug); season, episode and scene are nullable integers.
--
-- to_char(1000, 'FM000') is ###, to_char(100, 'FM00') is ##, and
-- to_char(-1, 'FM000') is -001 (an 11-character slug). The native commit sets
-- db_meta["scene"] = parent_meta["scene"] + 1 with no reset
-- (nexus/api/commit_handler_sync.py:460) and formats its own slug at
-- :573-577, passed at :588 to insert_chunk_metadata_sync (:95-142, slug at
-- :105, :119, :127, :137). At scene 1000 that 11-character Python slug fails
-- the varchar(10) assignment check before the trigger runs, so the commit
-- fails with "value too long for type character varying(10)" at about the
-- 1,000th chunk of the story; the commit runs inside "with conn:" (:352) and
-- the handler at :892-895 rolls back and re-raises. ### is written by any
-- INSERT whose supplied slug fits varchar(10) and by any UPDATE.
--
-- Decision 1069-D1: land the loud refusal now as its own slice; the slug
-- counter waits for 750-S1a. No counter, no wider column, no in-range slug
-- changes.
-- Decision 1069-D3: set_chunk_slug() is the sole author of the slug and
-- raises on an out-of-range value; Python no longer formats a slug.
-- Decision 1069-D4: refuse scene > 999, season > 99, episode > 99 and any
-- negative value, with a message naming the column, the value and the bound.
-- NULL handling is unchanged: a NULL part fails neither comparison and still
-- yields a NULL slug.
--
-- Locks: CREATE OR REPLACE FUNCTION locks only the function's catalog row and
-- reads or rewrites no chunk_metadata row. lock_timeout is 5s; apply when no
-- turn is in flight.

SET LOCAL lock_timeout = '5s';

CREATE OR REPLACE FUNCTION public.set_chunk_slug()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.season < 0 OR NEW.season > 99 THEN
    RAISE EXCEPTION USING
      ERRCODE = 'numeric_value_out_of_range',
      MESSAGE = format('Chunk slug bound exceeded: chunk_id %s has %s %s, outside 0..%s (season %s, episode %s, scene %s)', NEW.chunk_id, 'season', NEW.season, 99, NEW.season, NEW.episode, NEW.scene),
      SCHEMA = 'public',
      TABLE = 'chunk_metadata',
      COLUMN = 'season';
  END IF;
  IF NEW.episode < 0 OR NEW.episode > 99 THEN
    RAISE EXCEPTION USING
      ERRCODE = 'numeric_value_out_of_range',
      MESSAGE = format('Chunk slug bound exceeded: chunk_id %s has %s %s, outside 0..%s (season %s, episode %s, scene %s)', NEW.chunk_id, 'episode', NEW.episode, 99, NEW.season, NEW.episode, NEW.scene),
      SCHEMA = 'public',
      TABLE = 'chunk_metadata',
      COLUMN = 'episode';
  END IF;
  IF NEW.scene < 0 OR NEW.scene > 999 THEN
    RAISE EXCEPTION USING
      ERRCODE = 'numeric_value_out_of_range',
      MESSAGE = format('Chunk slug bound exceeded: chunk_id %s has %s %s, outside 0..%s (season %s, episode %s, scene %s)', NEW.chunk_id, 'scene', NEW.scene, 999, NEW.season, NEW.episode, NEW.scene),
      SCHEMA = 'public',
      TABLE = 'chunk_metadata',
      COLUMN = 'scene';
  END IF;
  NEW.slug :=
    'S' || TO_CHAR(NEW.season, 'FM00') ||
    'E' || TO_CHAR(NEW.episode, 'FM00') ||
    '_' || TO_CHAR(NEW.scene, 'FM000');
  RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.set_chunk_slug() IS 'BEFORE INSERT OR UPDATE trigger on chunk_metadata (trg_chunk_metadata_slug) and the sole author of slug: sets it to S<season>E<episode>_<scene> with two, two and three zero-padded digits, overwriting any slug an inserter supplies. Raises numeric_value_out_of_range naming chunk_id, the part, its value and its bound when season or episode is outside 0..99 or scene is outside 0..999, so it never writes # (#1069, migration 153). A NULL part gives a NULL slug.';
