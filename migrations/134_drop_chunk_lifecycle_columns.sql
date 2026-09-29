-- Migration 134: Retire the Chunk Lifecycle Columns (issue #807)
--
-- narrative_chunks.state, finalized_at, and regeneration_count belonged to
-- ChunkWorkflow, which PR #993 deleted. Their column comments (migrations 018
-- and 021) still describe that class. Production acceptance never wrote them:
-- every accepted chunk kept the default 'draft' (save_01 and save_02: 1,425
-- rows each, all 'draft'; no row on any slot has regeneration_count <> 0).
-- The only 'finalized' rows (save_03 id 1, save_04 id 1) are Retrograde
-- prologues, written by _insert_prologue_chunk
-- (nexus/agents/orrery/retrograde_persistence.py:2547-2549 at 588fc543,
-- 'finalized', now()). The other writer was a QA probe
-- (scripts/qa_shift/card_identity_probe.py:323 at 588fc543), which wrote
-- 'accepted', a value no enum ever had. This change removes both writers.
--
-- The lifecycle predicates that remain are:
--   pending   = a row in incubator;
--   accepted  = a narrative_chunks row (the Retrograde prologue is excluded
--               by its authorial_directives marker, see
--               nexus/agents/orrery/reconstruction.py
--               playable_narrative_predicate);
--   embedded  = embedding_generated_at IS NOT NULL (migration 021's own
--               comment on state already names this as the authoritative
--               predicate).
--
-- On 2026-09-29 no view, materialized view, or index on NEXUS_template or
-- save_01..save_05 depended on the three columns (pg_depend, pg_indexes).
-- The guard below still refuses to drop them if a hand-made view or
-- materialized view depends on one, and names that view, instead of letting
-- a CASCADE remove it without notice.
--
-- embedding_generated_at is now the only lifecycle signal on narrative_chunks.
-- Its comment (migration 018) still names ChunkWorkflow as the writer, so this
-- migration rewrites it to name the job that sets it today
-- (nexus/jobs/embeddings.py).
--
-- Migration 078 requires and, on empty tables, recreates state. It is
-- historical, runs before this migration in numeric order, and is stamped on
-- every slot and on the template, so it does not run again after this drop.

DO $$
DECLARE
    dependents text;
BEGIN
    SELECT string_agg(
               DISTINCT format('%I.%I (%s)', vn.nspname, v.relname, a.attname),
               ', '
           )
    INTO dependents
    FROM pg_depend AS d
    JOIN pg_rewrite AS r ON r.oid = d.objid
    JOIN pg_class AS v ON v.oid = r.ev_class
    JOIN pg_namespace AS vn ON vn.oid = v.relnamespace
    JOIN pg_attribute AS a
      ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
    WHERE d.classid = 'pg_rewrite'::regclass
      AND d.refclassid = 'pg_class'::regclass
      AND d.refobjid = 'public.narrative_chunks'::regclass
      AND a.attname IN ('state', 'finalized_at', 'regeneration_count')
      AND v.relkind IN ('v', 'm')
      AND v.oid <> d.refobjid;

    IF dependents IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 134 cannot drop narrative_chunks lifecycle columns; dependent views: %',
            dependents;
    END IF;
END $$;

ALTER TABLE narrative_chunks
    DROP COLUMN state,
    DROP COLUMN finalized_at,
    DROP COLUMN regeneration_count;

COMMENT ON COLUMN narrative_chunks.embedding_generated_at IS 'Set by the narrative embedding job (nexus/jobs/embeddings.py) once the chunk has a row in a chunk_embeddings_*d table; NULL until then. IS NOT NULL is the authoritative embedded predicate.';
