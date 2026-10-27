-- Migration 154: Drop the Vector Helpers and the All-NULL Legacy Columns (issue #813)
--
-- The last schema slice of #813 (813-S4). File:line citations are against
-- main at c7ae2988.
--
-- Coordinator defaults (#813 comment "Decisions Recorded From the 2026-10-26
-- Coordinator Review"):
--   D1: drop the six vector-helper functions now. Decision 813-Q1 ("The six
--       vector-helper functions wait for #812's legacy inventory") is met:
--       that inventory landed in PR #1050 (88fddbde).
--   D2: drop the seven all-NULL legacy columns behind the guard; keep
--       orrery_narration_jobs.provider and model_ref, commented as provenance.
-- Decision 813-Q6: "The drop guard uses catalog identities and an explicit
-- dependency closure, plus type-aware checks of function bodies that reject
-- an unresolved reference. Drops are restrictive, never CASCADE."
-- Decision 813-D1: this migration takes number 154 (152 is #1106's, 153 is
-- #1069's).
-- Decision 813-D2 (at order freeze): reuse migration 143's catalog
-- identities, RESTRICT drops and row and dependency refusals, but not its
-- lexer; refuse every whole-word target reference and every dynamic-SQL form
-- in routine bodies instead.
--
-- Targets:
--   public.hybrid_search(text,bytea,double precision,double precision,integer,text)
--   public.hybrid_search(text,public.vector,double precision,double precision,integer,text)
--   public.hybrid_search(text,public.vector,double precision,double precision,integer,text,text[])
--   public.migrate_embeddings()
--   public.pad_vector_384_to_1024(public.vector)
--   public.pad_vector_to_1024(public.vector)
--   assets.new_story_creator.seed_starting_location      text
--   assets.new_story_creator.seed_initial_mystery        text
--   assets.new_story_creator.seed_potential_obstacles    text[]
--   assets.new_story_creator.zone_boundary_description   text
--   assets.new_story_creator.zone_approximate_area       text
--   public.entity_tags.clear_on_override                 jsonb
--   public.world_events.narration_chunk_id               bigint, with
--     world_events_narration_chunk_id_fkey REFERENCES offscreen_narrations(id)
-- Kept and commented: public.orrery_narration_jobs.provider and model_ref.
-- The drain docstring says the provenance "is retained, but never used to make
-- a call" (nexus/agents/orrery/worker.py:245-246), and the only job insert
-- (worker.py:816-818) writes neither column.
--
-- Read-only fleet check, 2026-10-26, NEXUS_template and save_01..save_05 all
-- at migration 151: each of the six functions is plpgsql, not SECURITY
-- DEFINER, without SET clauses, with the same md5(prosrc) on all six
-- databases (the frozen values below), and no pg_depend row references any of
-- them. Each of the seven columns is NULL in every row; the only pg_depend row
-- on any of them is the foreign key (deptype a), whose only dependents are its
-- four internal RI triggers (deptype i). No stored definition names a target
-- as a whole word, no routine body holds EXECUTE, a SQL-text consumer or a
-- Unicode-escape form, and no database has an event trigger.
--
-- The guard (all in DO blocks; it creates no helper function, table or type),
-- in order, refusing with "target <identity>: <reason>":
--   1. any enabled event trigger;
--   2. functions: each signature resolves through to_regprocedure, is
--      plpgsql, not SECURITY DEFINER, has no SET clause, and its md5(prosrc)
--      equals the frozen value; any pg_depend row that references one of the
--      six refuses;
--   3. columns: after the locks below, each column exists with its frozen
--      type and no default, NOT NULL or generation expression; any non-NULL
--      value refuses with its count; any pg_depend row on a column refuses
--      except world_events_narration_chunk_id_fkey (deptype a), which must be
--      a foreign key from world_events(narration_chunk_id) to
--      offscreen_narrations(id) whose only dependents are four internal
--      triggers;
--   4. stored definitions: every function, procedure and window function
--      (pg_get_functiondef), view and materialized view, non-_RETURN rule,
--      non-internal trigger, column default, check and exclusion constraint,
--      expression or partial index and policy expression outside pg_catalog,
--      information_schema, pg_toast and pg_temp_*, other than extension
--      members and the six targets, refuses when it names any of the eleven
--      target names as a whole word (case-insensitive) or holds a U& or
--      UESCAPE form. Same-named columns on other tables
--      (entity_pair_tags.clear_on_override,
--      orrery_resolutions.narration_chunk_id) refuse too, by design;
--   5. dynamic SQL: any routine in that set whose body (prosrc, or its parsed
--      SQL-standard body) names EXECUTE, query_to_xml, query_to_xmlschema,
--      query_to_xml_and_xmlschema, dblink, dblink_exec, dblink_open or
--      dblink_send_query as a whole word refuses.
-- Departure from migration 143: 154 does not port 143's lexer or its constant
-- folds. For these targets the body check refuses every whole-word reference,
-- resolved or not, and check 5 refuses every dynamic-SQL form, so a constant
-- concatenation inside EXECUTE refuses as 143's fold would. The fleet passes
-- both checks today.
--
-- Drops, all RESTRICT: the six functions, then the foreign key, then
-- world_events.narration_chunk_id, then entity_tags.clear_on_override, then
-- the five new_story_creator columns in one ALTER TABLE. After the drops,
-- PostgreSQL's own validators (fmgr_sql_validator, plpgsql_validator) run
-- over every surviving non-extension routine under the runner's default
-- search_path with check_function_bodies on; a routine with a SET clause or a
-- language other than sql or plpgsql refuses (none exists today).
--
-- Residuals, outside the static guarantee: SQL that code outside the
-- database assembles and sends (covered by the code grep in
-- docs/qa/813-dead-strata-154/verification.md, not by this migration); and
-- SQL-text consumers that extensions add beyond the list in check 5. The
-- post-drop plpgsql_validator checks syntax only.
--
-- Locks: ACCESS EXCLUSIVE on assets.new_story_creator, public.entity_tags,
-- public.world_events and public.offscreen_narrations (the foreign key's two
-- RI triggers on it go with the drop), taken in that order before the column
-- checks and held through the drops, validators, comments, the runner's stamp
-- and commit. lock_timeout bounds each lock wait at five seconds; a timeout
-- rolls back the whole transaction, stamp included.

SET LOCAL search_path = pg_catalog;
SET LOCAL standard_conforming_strings = on;
SET LOCAL lock_timeout = '5s';

-- 1. Event triggers.
DO $events$
DECLARE
    offenders text;
BEGIN
    SELECT pg_catalog.string_agg(evtname::text, ', ' ORDER BY evtname) INTO offenders
    FROM pg_catalog.pg_event_trigger WHERE evtenabled <> 'D';
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION 'target migration 154 drop set: enabled event triggers refuse: %', offenders;
    END IF;
END
$events$;

-- 2. Functions: catalog identity and dependents.
DO $functions$
DECLARE
    f record;
    found_oid pg_catalog.oid;
    lang pg_catalog.name;
    secdef boolean;
    config text[];
    body_md5 text;
    offenders text;
BEGIN
    FOR f IN SELECT * FROM (VALUES
        ('public.hybrid_search(text,bytea,double precision,double precision,integer,text)', '36fb85af820eff8182f252abaeac2a33'),
        ('public.hybrid_search(text,public.vector,double precision,double precision,integer,text)', '9c990bf25cc932df73413510183f01e1'),
        ('public.hybrid_search(text,public.vector,double precision,double precision,integer,text,text[])', 'bf4098a509bf993ced0967bf3518d408'),
        ('public.migrate_embeddings()', 'fdb7a2ac64ccd83eb2edbf29c5527a85'),
        ('public.pad_vector_384_to_1024(public.vector)', '6a08f7bb736fdbdd24e9266b2d948281'),
        ('public.pad_vector_to_1024(public.vector)', 'cc3741074399976ff5501e875faf0b5b')
    ) AS frozen(signature, frozen_md5)
    LOOP
        found_oid := pg_catalog.to_regprocedure(f.signature)::pg_catalog.oid;
        IF found_oid IS NULL THEN
            RAISE EXCEPTION 'target %: function is missing', f.signature;
        END IF;
        SELECT l.lanname, p.prosecdef, p.proconfig, pg_catalog.md5(p.prosrc)
        INTO lang, secdef, config, body_md5
        FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_language l ON l.oid = p.prolang
        WHERE p.oid = found_oid;
        IF lang <> 'plpgsql' THEN
            RAISE EXCEPTION 'target %: language is %, not plpgsql', f.signature, lang;
        END IF;
        IF secdef THEN
            RAISE EXCEPTION 'target %: function is SECURITY DEFINER', f.signature;
        END IF;
        IF config IS NOT NULL THEN
            RAISE EXCEPTION 'target %: function has SET clauses %', f.signature, config;
        END IF;
        IF body_md5 IS DISTINCT FROM f.frozen_md5 THEN
            RAISE EXCEPTION 'target %: body md5 % differs from frozen %', f.signature, body_md5, f.frozen_md5;
        END IF;
        SELECT pg_catalog.string_agg(
                   pg_catalog.pg_describe_object(d.classid, d.objid, d.objsubid) || ' (deptype ' || d.deptype::pg_catalog.text || ')',
                   ', ' ORDER BY d.classid, d.objid, d.objsubid)
        INTO offenders
        FROM pg_catalog.pg_depend d
        WHERE d.refclassid = 'pg_catalog.pg_proc'::pg_catalog.regclass AND d.refobjid = found_oid;
        IF offenders IS NOT NULL THEN
            RAISE EXCEPTION 'target %: catalog dependents refuse: %', f.signature, offenders;
        END IF;
    END LOOP;
END
$functions$;

-- 3. Columns: locks, catalog identity, rows and dependents.
DO $columns$
DECLARE
    c record;
    rel pg_catalog.oid;
    att record;
    offenders text;
    fk record;
    narration_attnum smallint;
    narration_id_attnum smallint;
    fk_dependents text;
BEGIN
    LOCK TABLE assets.new_story_creator, public.entity_tags, public.world_events, public.offscreen_narrations
        IN ACCESS EXCLUSIVE MODE;

    SELECT * INTO fk FROM pg_catalog.pg_constraint
    WHERE conname = 'world_events_narration_chunk_id_fkey'
      AND conrelid = 'public.world_events'::pg_catalog.regclass;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'target public.world_events.narration_chunk_id: foreign key world_events_narration_chunk_id_fkey is missing';
    END IF;

    FOR c IN SELECT * FROM (VALUES
        ('assets.new_story_creator', 'seed_starting_location', 'text'),
        ('assets.new_story_creator', 'seed_initial_mystery', 'text'),
        ('assets.new_story_creator', 'seed_potential_obstacles', 'text[]'),
        ('assets.new_story_creator', 'zone_boundary_description', 'text'),
        ('assets.new_story_creator', 'zone_approximate_area', 'text'),
        ('public.entity_tags', 'clear_on_override', 'jsonb'),
        ('public.world_events', 'narration_chunk_id', 'bigint')
    ) AS frozen(relation, column_name, column_type)
    LOOP
        rel := pg_catalog.to_regclass(c.relation)::pg_catalog.oid;
        IF rel IS NULL THEN
            RAISE EXCEPTION 'target %.%: table is missing', c.relation, c.column_name;
        END IF;
        SELECT a.attnum, pg_catalog.format_type(a.atttypid, a.atttypmod) AS column_type,
               a.atthasdef, a.attnotnull, a.attgenerated
        INTO att
        FROM pg_catalog.pg_attribute a
        WHERE a.attrelid = rel AND a.attname = c.column_name AND NOT a.attisdropped AND a.attnum > 0;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'target %.%: column is missing or dropped', c.relation, c.column_name;
        END IF;
        IF att.column_type <> c.column_type THEN
            RAISE EXCEPTION 'target %.%: type is %, not %', c.relation, c.column_name, att.column_type, c.column_type;
        END IF;
        IF att.atthasdef THEN
            RAISE EXCEPTION 'target %.%: column has a default', c.relation, c.column_name;
        END IF;
        IF att.attnotnull THEN
            RAISE EXCEPTION 'target %.%: column is NOT NULL', c.relation, c.column_name;
        END IF;
        IF att.attgenerated <> '' THEN
            RAISE EXCEPTION 'target %.%: column is generated', c.relation, c.column_name;
        END IF;
        SELECT pg_catalog.string_agg(
                   pg_catalog.pg_describe_object(d.classid, d.objid, d.objsubid) || ' (deptype ' || d.deptype::pg_catalog.text || ')',
                   ', ' ORDER BY d.classid, d.objid, d.objsubid)
        INTO offenders
        FROM pg_catalog.pg_depend d
        WHERE d.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass
          AND d.refobjid = rel AND d.refobjsubid = att.attnum
          AND NOT (
              c.column_name = 'narration_chunk_id'
              AND d.classid = 'pg_catalog.pg_constraint'::pg_catalog.regclass
              AND d.objid = fk.oid AND d.objsubid = 0 AND d.deptype = 'a'
          );
        IF offenders IS NOT NULL THEN
            RAISE EXCEPTION 'target %.%: catalog dependents refuse: %', c.relation, c.column_name, offenders;
        END IF;
        IF c.column_name = 'narration_chunk_id' THEN
            narration_attnum := att.attnum;
        END IF;
    END LOOP;

    -- Rows: static counts, planned only after every column passed its identity check.
    FOR c IN
        SELECT 'assets.new_story_creator' AS relation, v.column_name, v.non_null
        FROM (SELECT pg_catalog.count(seed_starting_location) AS seed_starting_location,
                     pg_catalog.count(seed_initial_mystery) AS seed_initial_mystery,
                     pg_catalog.count(seed_potential_obstacles) AS seed_potential_obstacles,
                     pg_catalog.count(zone_boundary_description) AS zone_boundary_description,
                     pg_catalog.count(zone_approximate_area) AS zone_approximate_area
              FROM assets.new_story_creator) s
        CROSS JOIN LATERAL (VALUES
            ('seed_starting_location', s.seed_starting_location),
            ('seed_initial_mystery', s.seed_initial_mystery),
            ('seed_potential_obstacles', s.seed_potential_obstacles),
            ('zone_boundary_description', s.zone_boundary_description),
            ('zone_approximate_area', s.zone_approximate_area)
        ) AS v(column_name, non_null)
        UNION ALL
        SELECT 'public.entity_tags', 'clear_on_override', pg_catalog.count(clear_on_override)
        FROM public.entity_tags
        UNION ALL
        SELECT 'public.world_events', 'narration_chunk_id', pg_catalog.count(narration_chunk_id)
        FROM public.world_events
    LOOP
        IF c.non_null <> 0 THEN
            RAISE EXCEPTION 'target %.%: % row(s) hold a non-NULL value', c.relation, c.column_name, c.non_null;
        END IF;
    END LOOP;

    SELECT a.attnum INTO narration_id_attnum FROM pg_catalog.pg_attribute a
    WHERE a.attrelid = 'public.offscreen_narrations'::pg_catalog.regclass AND a.attname = 'id' AND NOT a.attisdropped;
    IF fk.contype <> 'f'
        OR fk.conrelid <> 'public.world_events'::pg_catalog.regclass
        OR fk.confrelid <> 'public.offscreen_narrations'::pg_catalog.regclass
        OR fk.conkey IS DISTINCT FROM ARRAY[narration_attnum]::smallint[]
        OR fk.confkey IS DISTINCT FROM ARRAY[narration_id_attnum]::smallint[] THEN
        RAISE EXCEPTION 'target public.world_events.narration_chunk_id: world_events_narration_chunk_id_fkey is not FOREIGN KEY (narration_chunk_id) REFERENCES offscreen_narrations(id): %',
            pg_catalog.pg_get_constraintdef(fk.oid);
    END IF;
    SELECT pg_catalog.string_agg(
               pg_catalog.pg_describe_object(d.classid, d.objid, d.objsubid) || ' (deptype ' || d.deptype::pg_catalog.text || ')',
               ', ' ORDER BY d.classid, d.objid, d.objsubid)
    INTO fk_dependents
    FROM pg_catalog.pg_depend d
    WHERE d.refclassid = 'pg_catalog.pg_constraint'::pg_catalog.regclass AND d.refobjid = fk.oid
      AND NOT (d.classid = 'pg_catalog.pg_trigger'::pg_catalog.regclass AND d.deptype = 'i');
    IF fk_dependents IS NOT NULL THEN
        RAISE EXCEPTION 'target public.world_events.narration_chunk_id: foreign key dependents refuse: %', fk_dependents;
    END IF;
    IF (SELECT pg_catalog.count(*) FROM pg_catalog.pg_depend d
        WHERE d.refclassid = 'pg_catalog.pg_constraint'::pg_catalog.regclass AND d.refobjid = fk.oid) <> 4 THEN
        RAISE EXCEPTION 'target public.world_events.narration_chunk_id: foreign key does not have exactly four internal triggers';
    END IF;
END
$columns$;

-- 4 and 5. Stored definitions and dynamic SQL.
DO $definitions$
DECLARE
    offenders text;
BEGIN
    WITH app_ns AS (
        SELECT n.oid FROM pg_catalog.pg_namespace n
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND n.nspname !~ '^pg_temp_'
    ), extension_members AS (
        SELECT d.classid, d.objid FROM pg_catalog.pg_depend d WHERE d.deptype = 'e'
    ), app_rel AS (
        SELECT c.oid, c.relkind FROM pg_catalog.pg_class c
        WHERE c.relnamespace IN (SELECT oid FROM app_ns)
          AND (c.oid) NOT IN (SELECT objid FROM extension_members
                              WHERE classid = 'pg_catalog.pg_class'::pg_catalog.regclass)
    ), target_functions AS (
        SELECT pg_catalog.to_regprocedure(signature)::pg_catalog.oid AS oid
        FROM pg_catalog.unnest(ARRAY[
            'public.hybrid_search(text,bytea,double precision,double precision,integer,text)',
            'public.hybrid_search(text,public.vector,double precision,double precision,integer,text)',
            'public.hybrid_search(text,public.vector,double precision,double precision,integer,text,text[])',
            'public.migrate_embeddings()',
            'public.pad_vector_384_to_1024(public.vector)',
            'public.pad_vector_to_1024(public.vector)'
        ]) AS signature
    ), routines AS (
        SELECT p.oid, p.prosrc FROM pg_catalog.pg_proc p
        WHERE p.pronamespace IN (SELECT oid FROM app_ns)
          AND p.prokind IN ('f', 'p', 'w')
          AND p.oid NOT IN (SELECT oid FROM target_functions)
          AND p.oid NOT IN (SELECT objid FROM extension_members
                            WHERE classid = 'pg_catalog.pg_proc'::pg_catalog.regclass)
    ), definitions(classid, objid, objsubid, body) AS (
        SELECT 'pg_catalog.pg_proc'::pg_catalog.regclass::pg_catalog.oid, r.oid, 0,
               pg_catalog.pg_get_functiondef(r.oid)
        FROM routines r
        UNION ALL
        SELECT 'pg_catalog.pg_class'::pg_catalog.regclass::pg_catalog.oid, c.oid, 0,
               pg_catalog.pg_get_viewdef(c.oid)
        FROM app_rel c WHERE c.relkind IN ('v', 'm')
        UNION ALL
        SELECT 'pg_catalog.pg_rewrite'::pg_catalog.regclass::pg_catalog.oid, rw.oid, 0,
               pg_catalog.pg_get_ruledef(rw.oid)
        FROM pg_catalog.pg_rewrite rw
        WHERE rw.ev_class IN (SELECT oid FROM app_rel) AND rw.rulename <> '_RETURN'
        UNION ALL
        SELECT 'pg_catalog.pg_trigger'::pg_catalog.regclass::pg_catalog.oid, tg.oid, 0,
               pg_catalog.pg_get_triggerdef(tg.oid)
        FROM pg_catalog.pg_trigger tg
        WHERE tg.tgrelid IN (SELECT oid FROM app_rel) AND NOT tg.tgisinternal
        UNION ALL
        SELECT 'pg_catalog.pg_attrdef'::pg_catalog.regclass::pg_catalog.oid, ad.oid, 0,
               pg_catalog.pg_get_expr(ad.adbin, ad.adrelid)
        FROM pg_catalog.pg_attrdef ad
        WHERE ad.adrelid IN (SELECT oid FROM app_rel)
        UNION ALL
        SELECT 'pg_catalog.pg_constraint'::pg_catalog.regclass::pg_catalog.oid, co.oid, 0,
               pg_catalog.pg_get_constraintdef(co.oid)
        FROM pg_catalog.pg_constraint co
        WHERE co.contype IN ('c', 'x')
          AND co.connamespace IN (SELECT oid FROM app_ns)
          AND (co.conrelid = 0 OR co.conrelid IN (SELECT oid FROM app_rel))
          AND co.contypid NOT IN (SELECT objid FROM extension_members
                                  WHERE classid = 'pg_catalog.pg_type'::pg_catalog.regclass)
        UNION ALL
        SELECT 'pg_catalog.pg_class'::pg_catalog.regclass::pg_catalog.oid, i.indexrelid, 0,
               pg_catalog.pg_get_indexdef(i.indexrelid)
        FROM pg_catalog.pg_index i
        WHERE i.indrelid IN (SELECT oid FROM app_rel)
          AND (i.indexprs IS NOT NULL OR i.indpred IS NOT NULL)
        UNION ALL
        SELECT 'pg_catalog.pg_policy'::pg_catalog.regclass::pg_catalog.oid, pol.oid, 0,
               pg_catalog.concat_ws(' ', pg_catalog.pg_get_expr(pol.polqual, pol.polrelid),
                                    pg_catalog.pg_get_expr(pol.polwithcheck, pol.polrelid))
        FROM pg_catalog.pg_policy pol
        WHERE pol.polrelid IN (SELECT oid FROM app_rel)
    ), target_names(name, identity) AS (
        VALUES
            ('hybrid_search', 'public.hybrid_search (three overloads)'),
            ('migrate_embeddings', 'public.migrate_embeddings()'),
            ('pad_vector_384_to_1024', 'public.pad_vector_384_to_1024(public.vector)'),
            ('pad_vector_to_1024', 'public.pad_vector_to_1024(public.vector)'),
            ('seed_starting_location', 'assets.new_story_creator.seed_starting_location'),
            ('seed_initial_mystery', 'assets.new_story_creator.seed_initial_mystery'),
            ('seed_potential_obstacles', 'assets.new_story_creator.seed_potential_obstacles'),
            ('zone_boundary_description', 'assets.new_story_creator.zone_boundary_description'),
            ('zone_approximate_area', 'assets.new_story_creator.zone_approximate_area'),
            ('clear_on_override', 'public.entity_tags.clear_on_override'),
            ('narration_chunk_id', 'public.world_events.narration_chunk_id')
    ), refusals(message) AS (
        SELECT 'target ' || t.identity || ': '
               || pg_catalog.pg_describe_object(d.classid, d.objid, d.objsubid)
               || ' names ' || t.name || ' as a whole word'
        FROM definitions d JOIN target_names t ON d.body ~* ('\m' || t.name || '\M')
        UNION ALL
        SELECT 'target migration 154 drop set: '
               || pg_catalog.pg_describe_object(d.classid, d.objid, d.objsubid)
               || ' holds a U& or UESCAPE form'
        FROM definitions d
        WHERE d.body ~* 'U&[''"]' OR d.body ~* '\muescape\M'
        UNION ALL
        SELECT 'target migration 154 drop set: '
               || pg_catalog.pg_describe_object('pg_catalog.pg_proc'::pg_catalog.regclass, r.oid, 0)
               || ' holds dynamic SQL (EXECUTE or a SQL-text consumer)'
        FROM routines r
        CROSS JOIN LATERAL (
            SELECT COALESCE(pg_catalog.pg_get_function_sqlbody(r.oid), r.prosrc) AS body
        ) b
        WHERE b.body ~* '\mexecute\M'
           OR b.body ~* '\m(query_to_xml|query_to_xmlschema|query_to_xml_and_xmlschema|dblink|dblink_exec|dblink_open|dblink_send_query)\M'
    )
    SELECT pg_catalog.string_agg(message, '; ' ORDER BY message) INTO offenders FROM refusals;
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION '%', offenders;
    END IF;
END
$definitions$;

-- The drops, all RESTRICT.
DROP FUNCTION public.hybrid_search(text,bytea,double precision,double precision,integer,text) RESTRICT;
DROP FUNCTION public.hybrid_search(text,public.vector,double precision,double precision,integer,text) RESTRICT;
DROP FUNCTION public.hybrid_search(text,public.vector,double precision,double precision,integer,text,text[]) RESTRICT;
DROP FUNCTION public.migrate_embeddings() RESTRICT;
DROP FUNCTION public.pad_vector_384_to_1024(public.vector) RESTRICT;
DROP FUNCTION public.pad_vector_to_1024(public.vector) RESTRICT;
ALTER TABLE public.world_events DROP CONSTRAINT world_events_narration_chunk_id_fkey RESTRICT;
ALTER TABLE public.world_events DROP COLUMN narration_chunk_id RESTRICT;
ALTER TABLE public.entity_tags DROP COLUMN clear_on_override RESTRICT;
ALTER TABLE assets.new_story_creator
    DROP COLUMN seed_starting_location RESTRICT,
    DROP COLUMN seed_initial_mystery RESTRICT,
    DROP COLUMN seed_potential_obstacles RESTRICT,
    DROP COLUMN zone_boundary_description RESTRICT,
    DROP COLUMN zone_approximate_area RESTRICT;

-- Independent second line: PostgreSQL's language validators check every
-- surviving application routine against the post-drop catalog under the
-- runner's default search_path, without creating or replacing anything.
SET LOCAL search_path TO DEFAULT;
SET LOCAL check_function_bodies = on;
DO $validate$
DECLARE
    f record;
BEGIN
    FOR f IN
        SELECT p.oid, p.proconfig, l.lanname,
               pg_catalog.format('%I.%I(%s)', n.nspname, p.proname,
                                 pg_catalog.pg_get_function_identity_arguments(p.oid)) AS identity
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_catalog.pg_language l ON l.oid = p.prolang
        WHERE p.prokind IN ('f', 'p', 'w')
          AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND n.nspname !~ '^pg_temp_'
          AND NOT EXISTS (
              SELECT 1 FROM pg_catalog.pg_depend d
              WHERE d.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass
                AND d.objid = p.oid AND d.deptype = 'e'
          )
        ORDER BY p.oid
    LOOP
        IF f.proconfig IS NOT NULL THEN
            RAISE EXCEPTION 'target %: post-drop validation refuses: routine has SET clauses %', f.identity, f.proconfig;
        END IF;
        IF f.lanname NOT IN ('sql', 'plpgsql') THEN
            RAISE EXCEPTION 'target %: post-drop validation refuses: unsupported language %', f.identity, f.lanname;
        END IF;
        BEGIN
            IF f.lanname = 'sql' THEN
                PERFORM pg_catalog.fmgr_sql_validator(f.oid);
            ELSE
                PERFORM pg_catalog.plpgsql_validator(f.oid);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE EXCEPTION 'target %: post-drop validation refuses: %', f.identity, SQLERRM;
        END;
    END LOOP;
END
$validate$;

-- Default D2: the provider-era provenance columns stay, documented.
COMMENT ON COLUMN public.orrery_narration_jobs.provider IS 'Provider name a job recorded under the retired provider-era narration path. Retained as provenance: the deterministic descriptor drain (drain_narration_outbox_sync) never uses it to make a call, and the current job insert writes no value, so new jobs hold NULL.';
COMMENT ON COLUMN public.orrery_narration_jobs.model_ref IS 'Model identifier a job recorded under the retired provider-era narration path, paired with provider. Retained as provenance: the descriptor drain never uses it to make a call, and the current job insert writes no value, so new jobs hold NULL.';
