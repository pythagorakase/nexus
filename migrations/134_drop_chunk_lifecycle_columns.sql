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
-- PostgreSQL records no dependency for a column named inside a function
-- body, so the view guard cannot see a trigger that the drop would break: a
-- BEFORE INSERT trigger whose function assigns NEW.state would let the drop
-- succeed, and every later narrative_chunks insert would then fail inside
-- the trigger. The second guard reads function source text (pg_proc.prosrc)
-- and refuses, naming each function and the column it references. It reads
-- every function that a non-internal trigger on narrative_chunks calls (any
-- schema or language) and every PL/pgSQL function in public. Matching is
-- case-insensitive, and a column name matches only as a whole identifier
-- (no letter, digit, underscore, or $ on either side), so chunk_state,
-- state_updates, and SQLSTATE never match. A function refuses the drop for a
-- column when either pattern matches:
--   1. Trigger record field, checked only in a function that a trigger on
--      narrative_chunks calls:
--        (?<![\w$.])(new|old)\s*\.\s*"?<column>"?(?![\w$])
--      NEW.state in a trigger function on another table (a job table's own
--      state column) is not checked against this pattern.
--   2. Statement adjacency, checked in every function read: one statement
--      (the text between two semicolons) names the table,
--        (?<![\w$])"?narrative_chunks"?(?![\w$])
--      and also names the column, bare or qualified (nc.state,
--      narrative_chunks.state):
--        (?<![\w$])"?<column>"?(?![\w$])
--      A job table's state column in a statement that does not name
--      narrative_chunks does not match.
-- The patterns err toward refusing. Comments and string literals are read
-- too, so dynamic SQL is covered, and a statement that names both
-- narrative_chunks and another table's state column also refuses; read the
-- named function before changing it. On 2026-09-29 neither pattern matched
-- on NEXUS_template or save_01..save_05. Their only narrative_chunks trigger
-- functions are migration 114's IDF functions (lock_memory_idf_corpora, and
-- maintain_memory_idf, which calls sync_memory_idf_document as migration 133
-- rewrote it) and migration 078's
-- nexus_reject_legacy_retrograde_summary_chunk; none names the three columns.
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
    referencing_functions text;
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

    WITH chunk_trigger_functions AS (
        SELECT t.tgfoid AS function_oid
        FROM pg_trigger AS t
        WHERE t.tgrelid = 'public.narrative_chunks'::regclass
          AND NOT t.tgisinternal
    ),
    read_functions AS (
        SELECT format(
                   '%I.%I(%s)',
                   fn.nspname,
                   p.proname,
                   pg_get_function_identity_arguments(p.oid)
               ) AS signature,
               p.prosrc AS body,
               p.oid IN (
                   SELECT function_oid FROM chunk_trigger_functions
               ) AS fires_on_narrative_chunks
        FROM pg_proc AS p
        JOIN pg_namespace AS fn ON fn.oid = p.pronamespace
        JOIN pg_language AS l ON l.oid = p.prolang
        WHERE p.oid IN (SELECT function_oid FROM chunk_trigger_functions)
           OR (fn.nspname = 'public' AND l.lanname = 'plpgsql')
    ),
    lifecycle_columns (column_name) AS (
        VALUES ('state'), ('finalized_at'), ('regeneration_count')
    )
    SELECT string_agg(
               DISTINCT format('%s (%s)', f.signature, c.column_name),
               ', '
           )
    INTO referencing_functions
    FROM read_functions AS f
    CROSS JOIN lifecycle_columns AS c
    WHERE (
            f.fires_on_narrative_chunks
            AND f.body ~* (
                '(?<![\w$.])(new|old)\s*\.\s*"?'
                || c.column_name
                || '"?(?![\w$])'
            )
        )
       OR EXISTS (
            SELECT 1
            FROM regexp_split_to_table(f.body, ';') AS s (statement_text)
            WHERE s.statement_text ~* '(?<![\w$])"?narrative_chunks"?(?![\w$])'
              AND s.statement_text ~* (
                  '(?<![\w$])"?' || c.column_name || '"?(?![\w$])'
              )
        );

    IF referencing_functions IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 134 cannot drop narrative_chunks lifecycle columns; functions reference them: %',
            referencing_functions;
    END IF;
END $$;

ALTER TABLE narrative_chunks
    DROP COLUMN state,
    DROP COLUMN finalized_at,
    DROP COLUMN regeneration_count;

COMMENT ON COLUMN narrative_chunks.embedding_generated_at IS 'Set by the narrative embedding job (nexus/jobs/embeddings.py) once the chunk has a row in a chunk_embeddings_*d table; NULL until then. IS NOT NULL is the authoritative embedded predicate.';
