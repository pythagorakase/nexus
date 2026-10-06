-- Migration 143: Retire the frozen #813 table/enum closure, never CASCADE.
-- 813-Q1 retains the six vector helpers for #812; Q2 drops all seven orphan
-- enums; Q6 requires catalog identities and conservative body resolution.
-- Manifest: tests/fixtures/813_pre143_manifest.json, frozen from full-data,
-- read-only dumps of NEXUS_template and save_01..05 on 2026-10-01.
-- set_updated_at() catalog body: BEGIN NEW.updated_at = now(); RETURN NEW; END.
-- Surviving triggers: public.characters.trg_characters_set_updated and
-- public.places.trg_places_set_updated. Their definitions and body are untouched.
--
-- Locks: ACCESS EXCLUSIVE on dropped relations/types and public.characters when
-- items RI triggers are removed; held through validators, comment, stamp and commit.
-- Each wait is bounded at five seconds; queued characters readers can also wait.
-- A timeout rolls back the whole transaction.
--
-- Contract: PostgreSQL decides catalog dependencies: every drop is RESTRICT, and
-- SQL-standard bodies (prosqlbody) carry real dependencies. String-bodied routines are
-- decided lexically under allowlisted declared SET clauses on top of session startup
-- settings: a token naming a drop target refuses, every decoded string literal or
-- decoded name-array element resolving to a drop target refuses, and an unclassifiable
-- form refuses. After the drops, PostgreSQL's validators check every surviving
-- application routine under that environment, with identity settings reserved for
-- scanner lookups and validators run as the migration user. The guard refuses non-extension
-- format/concat/concat_ws functions and || operators outside pg_catalog;
-- proconfig names other than search_path, role, session_authorization,
-- standard_conforming_strings, backslash_quote, DateStyle, IntervalStyle, TimeZone,
-- extra_float_digits, default_text_search_config, client_min_messages and
-- application_name; statement-initial bare SET/RESET, any set_config identifier and
-- recognized pg_settings UPDATE targets; enabled event triggers before helper DDL;
-- unsupported application languages or different SECURITY DEFINER owners; raw U&' or U&"
-- or UESCAPE, even in comments/data; target-bearing unmodeled column-definition lists; recognized nonliteral or unresolved
-- catalog-input operands (reg* casts, to_reg*, nextval/currval/setval); and nonconstant or unresolved SQL in recognized EXECUTE, DO, nested CREATE
-- FUNCTION/PROCEDURE and SQL-text consumer forms. Migration parsing/deparsing pins
-- search_path=pg_catalog, standard_conforming_strings=on, backslash_quote=safe_encoding,
-- exit_on_error=off, quote_all_identifiers=off and lock_timeout=5s; validators reassert
-- check_function_bodies=on. Role and session_authorization apply to scanner lookups and
-- are skipped by validators. Non-routine stored definitions meet the literal rule and
-- constant SQL-text fold; pg_depend decides their outer identifier references. Constant
-- SQL through an unrecognized consumer remains an in-contract residual, not a
-- nonconstant-data exclusion. Outside the static guarantee are names arriving as runtime
-- data (nonliteral catalog-input arguments or reg* parameters), nonconstant SQL through
-- unrecognized forms, and unrecognized path/role mutations. Late-bound PL/pgSQL
-- expressions and polymorphic SQL remain limited by their native validators:
-- fmgr_sql_validator only syntax-checks polymorphic SQL; plpgsql_validator checks syntax
-- and declared types.
--
-- Plain/E/N/B/X/dollar strings and newline continuation are delimited before
-- PostgreSQL decodes them. Spaceless typed literals are identifier plus string.
-- Unicode-escape forms refuse, including raw U&', U&" or UESCAPE in comments/data.
-- Typed literals, casts, declarations and nested JSON RETURNING are type contexts;
-- query/trigger columns require catalog proof and cannot supply type proof.
-- Candidate targets include catalog-generated row/array types and owned indexes.
-- Constant EXECUTE, DO and query_to_xml/query_to_xmlschema/
-- query_to_xml_and_xmlschema/ts_stat and argument two of two-argument ts_rewrite
-- inputs fold through builtin
-- format/concat/|| only. Non-extension overloads outside pg_catalog
-- refuse globally; extension-owned overloads are excluded. Other folds refuse.
-- Unsupported languages and different SECURITY DEFINER owners refuse.
-- Recognized catalog-input positions (reg* casts, to_reg*, nextval/currval/setval)
-- additionally refuse nonliteral/unresolved operands.
-- SET values split at the first equals sign in one shared parser. Each validator
-- and every environment-applying helper run in a sentinel subtransaction, restoring
-- the native GUC stack including privilege settings. check_function_bodies=on,
-- the migration lock timeout are reasserted after the allowlisted SETs.
-- Only search_path, role, session_authorization, standard_conforming_strings,
-- backslash_quote, DateStyle, IntervalStyle, TimeZone, extra_float_digits,
-- default_text_search_config, client_min_messages and application_name apply.
-- Statement-initial SET/RESET and any set_config identifier refuse. Enabled
-- event triggers refuse before helper DDL. Non-routine stored definitions and
-- aggregate initial values meet the literal rule and SQL-text fold; pg_depend
-- decides their outer identifier references. Parameter defaults use startup
-- settings, not routine SETs; parameter names meet only the literal rule.
-- No runtime DDL or routine execution: definitions, OIDs, ownership, ACLs and
-- comments survive unchanged except the prescribed set_updated_at() comment.
-- Refusals roll back drops/comments/stamping.
-- Scanner guards precede DROP; validators run inside the same atomic transaction.
-- No persistent helper/debt remains.
--
-- Residuals:
-- - R3 conservatively refuses statement-start set/reset variables and declaration-entry
-- collateral, SET CONSTRAINTS and SET TRANSACTION; the owner renames or restructures (Astra pass 10 P3; third panel #9).
-- - Query-column proof conservatively refuses INSERT column lists, EXCLUDED columns, and
-- FROM in extract/substring/IS DISTINCT FROM; flat clause/alias ambiguity remains
-- fail-closed (third panel #9; second panel column-position reproductions).
-- - R6 validators bind names as the superuser migration user: role-specific $user and
-- missing USAGE on an earlier schema can falsely refuse healthy routines; scanner
-- lookups still use the declared identity (third panel #19; R9 granted $user probe).
-- - Runtime/computed catalog names, including implicit reg* parameters such as
-- pg_relation_size(v), and SQL or path/role changes through unrecognized forms remain
-- outside the guarantee. Unrecognized setting mutations via an updatable pg_settings
-- view or set_config in a caller default remain in-contract residuals (third panel
-- #10, #16, #23; second panel runtime-data reproductions).
-- - Extension SQL-text consumers such as tablefunc.crosstab are an in-contract residual:
-- the guard does not recognize their constant SQL arguments; non-SQL/plpgsql DO
-- languages are unproved when the language is unavailable (third panel #3 variant;
-- second panel F7 language reproduction).
-- - Trigger arguments without WHEN are not read by F12; a late-binding trigger argument
-- remains an in-contract residual (third panel #18(c)).
-- - Healthy scalar reg*[] brace casts may conservatively refuse through the scalar
-- catalog-cast classifier; ordinary brace data passes. Startup scs replay has code
-- coverage but no discriminating shipped mutant proof; startup_pin proves migration
-- parsing only (third panel #1 controls, #21).
-- - Late-bound PL/pgSQL expressions, polymorphic SQL validation and runtime data remain
-- outside the second-line guarantee. Unmodeled constant folds refuse when recognized;
-- arbitrary unrecognized SQL consumers remain the residual above (third panel :23
-- implicit-reg* parameter reproductions; Astra pass 10 contract audit).

-- The migration's own code resolves unqualified functions, operators and
-- types under a single-schema path, pg_catalog alone, for its whole run: this
-- SET LOCAL comes first, every pg_temp helper pins the same path, and the only
-- code that ever runs under a routine's declared path is (a) a prebuilt,
-- fully qualified catalog lookup inside pg_temp.dead143_resolve and (b) the
-- post-drop validator call, whose statements are all pg_catalog-qualified.
-- Precedence rules ("pg_catalog first") are not enough: PostgreSQL ranks every
-- candidate signature across the path, so a more specific overload in a later
-- schema can win over a variadic or polymorphic builtin.
SET LOCAL search_path = pg_catalog;
SET LOCAL standard_conforming_strings = on;
SET LOCAL backslash_quote = safe_encoding;
SET LOCAL exit_on_error = off;
SET LOCAL quote_all_identifiers = off;
-- Single policy value: pinned helpers/validator capture this before routine SETs.
SET LOCAL lock_timeout = '5s';

-- R1/R4 run before helper DDL, so no event-trigger routine is invoked.
DO $refusals$
DECLARE
    offenders text;
BEGIN
    SELECT string_agg(identity, ', ' ORDER BY identity) INTO offenders FROM (
        SELECT pg_catalog.pg_describe_object('pg_proc'::regclass,p.oid,0) AS identity
        FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname<>'pg_catalog' AND p.proname IN ('format','concat','concat_ws')
        AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')
        UNION ALL
        SELECT pg_catalog.pg_describe_object('pg_operator'::regclass,o.oid,0)
        FROM pg_catalog.pg_operator o JOIN pg_catalog.pg_namespace n ON n.oid=o.oprnamespace
        WHERE n.nspname<>'pg_catalog' AND o.oprname='||'
        AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid='pg_operator'::regclass AND d.objid=o.oid AND d.deptype='e')
    ) overloads;
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION 'noncatalog fold overloads refuse: %',offenders;
    END IF;
    SELECT string_agg(evtname, ', ' ORDER BY evtname) INTO offenders
    FROM pg_catalog.pg_event_trigger WHERE evtenabled<>'D';
    IF offenders IS NOT NULL THEN RAISE EXCEPTION 'enabled event triggers refuse: %',offenders; END IF;
END
$refusals$;

CREATE FUNCTION pg_temp.dead143_tokens(body text, effective_scs text, setting_names text[], setting_values text[]) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog AS $lexer$
DECLARE
    i integer := 1;
    start_at integer;
    depth integer;
    ch text;
    delimiter text;
    value text;
    raw text;
    kind text;
    result jsonb := '[]';
    escaped boolean;
    prefix text;
    suffix text;
BEGIN
    IF strpos(lower(body),'u&''')>0 OR strpos(lower(body),'u&"')>0
        OR strpos(lower(body),'uescape')>0 THEN
        RAISE EXCEPTION 'unicode-escape literal or identifier; edit the routine';
    END IF;
    WHILE i <= length(body) LOOP
        ch := substr(body, i, 1);
        IF ch ~ '[ \t\n\r\f\v]' THEN i := i + 1; CONTINUE; END IF;
        IF substr(body, i, 2) = '--' THEN
            WHILE i <= length(body) AND substr(body, i, 1) NOT IN (E'\n',E'\r') LOOP i := i + 1; END LOOP;
            CONTINUE;
        END IF;
        IF substr(body, i, 2) = '/*' THEN
            depth := 1; i := i + 2;
            WHILE depth > 0 AND i <= length(body) LOOP
                IF substr(body, i, 2) = '/*' THEN depth := depth + 1; i := i + 2;
                ELSIF substr(body, i, 2) = '*/' THEN depth := depth - 1; i := i + 2;
                ELSE i := i + 1; END IF;
            END LOOP;
            IF depth <> 0 THEN RAISE EXCEPTION 'unclosed comment'; END IF;
            CONTINUE;
        END IF;
        start_at := i; value := ''; escaped := false;
        prefix := substring(substr(body,i) FROM '^([eEbBxXnN])''');
        IF i>1 AND substr(body,i-1,1) ~ '[A-Za-z_0-9$]|[^\x00-\x7F]' THEN prefix := NULL; END IF;
        IF ch = '''' OR prefix IS NOT NULL THEN
            escaped := lower(coalesce(prefix,''))='e' OR
                (lower(coalesce(prefix,'')) IN ('','n') AND effective_scs='off');
            i := i + length(coalesce(prefix,'')) + 1;
            LOOP
                IF i > length(body) THEN RAISE EXCEPTION 'unclosed string'; END IF;
                ch := substr(body,i,1); i := i + 1;
                IF escaped AND ch = E'\\' THEN
                    i := i + 1;
                ELSIF ch = '''' THEN
                    IF substr(body,i,1) = '''' THEN i := i + 1;
                    ELSE
                        -- SQL newline concatenation is one literal, including
                        -- escape semantics inherited from its first segment.
                        -- scan.l quotecontinue: line comments belong to the
                        -- whitespace grammar; block comments never do.
                        suffix := substring(substr(body,i) FROM E'^(([ \\t\\f\\v]|--[^\\n\\r]*)*[\\n\\r]([ \\t\\n\\r\\f\\v]+|--[^\\n\\r]*[\\n\\r])*)''');
                        IF suffix IS NOT NULL THEN
                            i := i + length(suffix) + 1;
                        ELSE EXIT; END IF;
                    END IF;
                END IF;
            END LOOP;
            raw := substr(body,start_at,i-start_at);
            -- Only the fully delimited literal grammar above reaches EXECUTE.
            -- PostgreSQL decodes escapes; no caller expression executes.
            BEGIN
                value := pg_temp.dead143_resolve('SELECT ('||raw||')::pg_catalog.text',setting_names,setting_values);
            EXCEPTION WHEN OTHERS THEN
                RAISE EXCEPTION 'unresolved string literal: %',SQLERRM;
            END;
            kind := 'string';
        ELSIF ch = '"' THEN
            i := i + 1;
            LOOP
                IF i > length(body) THEN RAISE EXCEPTION 'unclosed identifier'; END IF;
                ch := substr(body,i,1); i := i + 1;
                IF ch = '"' THEN
                    IF substr(body,i,1) = '"' THEN value := value || '"'; i := i + 1;
                    ELSE EXIT; END IF;
                ELSE value := value || ch; END IF;
            END LOOP;
            kind := 'qid';
        ELSIF ch = '$' AND substr(body,i) ~ '^\$(?:(?:[A-Za-z_]|[^\x00-\x7F])(?:[A-Za-z_0-9]|[^\x00-\x7F])*)?\$' THEN
            delimiter := substring(substr(body,i) FROM '^\$(?:(?:[A-Za-z_]|[^\x00-\x7F])(?:[A-Za-z_0-9]|[^\x00-\x7F])*)?\$');
            i := i + length(delimiter);
            depth := strpos(substr(body,i),delimiter);
            IF depth = 0 THEN RAISE EXCEPTION 'unclosed dollar literal'; END IF;
            value := substr(body,i,depth-1); i := i + depth-1 + length(delimiter);
            kind := 'string';
        ELSIF ch ~ '[A-Za-z_]|[^\x00-\x7F]' THEN
            WHILE i <= length(body) AND substr(body,i,1) ~ '[A-Za-z_0-9$]|[^\x00-\x7F]' LOOP i := i + 1; END LOOP;
            value := lower(substr(body,start_at,i-start_at)); kind := 'id';
        ELSE
            value := ch; kind := 'punct'; i := i + 1;
            IF substr(body,start_at,2) IN ('::','||',':=') THEN
                value := substr(body,start_at,2); i := start_at + 2;
            END IF;
        END IF;
        raw := substr(body,start_at,i-start_at);
        result := result || jsonb_build_array(jsonb_build_object('k',kind,'v',value,'raw',raw));
    END LOOP;
    RETURN result;
END
$lexer$;
COMMENT ON FUNCTION pg_temp.dead143_tokens(text, text, text[], text[]) IS 'Migration 143 transaction-local SQL lexer: distinguish identifiers from comments and diagnostic literals; removed before stamping.';

CREATE FUNCTION pg_temp.dead143_setting(setting text) RETURNS text[]
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog AS $setting$
DECLARE
    parsed text[] := ARRAY[substr(setting,1,strpos(setting,'=')-1), substr(setting,strpos(setting,'=')+1)];
BEGIN
    IF lower(parsed[1]) NOT IN ('search_path','role','session_authorization',
        'standard_conforming_strings','backslash_quote','datestyle','intervalstyle',
        'timezone','extra_float_digits','default_text_search_config','client_min_messages','application_name') THEN
        RAISE EXCEPTION 'unresolved environment setting: %',parsed[1];
    END IF;
    RETURN parsed;
END
$setting$;
COMMENT ON FUNCTION pg_temp.dead143_setting(text) IS 'Migration 143 transaction-local proconfig parser: name before first equals, complete value after it, shared by scanner and validator; removed before stamping.';

CREATE FUNCTION pg_temp.dead143_resolve(statement text, setting_names text[], setting_values text[]) RETURNS text
LANGUAGE plpgsql SET search_path = pg_catalog AS $resolve$
-- Precompute under pg_catalog. Only qualified statements run under the routine
-- environment; native sentinel-subtransaction GUC unwind restores it without fresh assignments.
DECLARE
    result text;
    startup_path text := (SELECT reset_val FROM pg_catalog.pg_settings WHERE name='search_path');
    startup_scs text := (SELECT reset_val FROM pg_catalog.pg_settings WHERE name='standard_conforming_strings');
    setting_count integer := coalesce(pg_catalog.array_length(setting_names,1),0);
    lock_policy CONSTANT text := pg_catalog.current_setting('lock_timeout');
    i integer;
BEGIN
    BEGIN
        PERFORM pg_catalog.set_config('search_path',startup_path,true);
        PERFORM pg_catalog.set_config('standard_conforming_strings',startup_scs,true);
        FOR i IN 1..setting_count LOOP
            PERFORM pg_catalog.set_config(setting_names[i],setting_values[i],true);
        END LOOP;
        PERFORM pg_catalog.set_config('lock_timeout',lock_policy,true);
        PERFORM pg_catalog.set_config('check_function_bodies','on',true);
        EXECUTE statement INTO result;
        -- A helper's SET search_path saves that GUC alone. Abort the local
        -- subtransaction to unwind every arbitrary SET, including privileges.
        RAISE SQLSTATE 'D1430' USING MESSAGE='dead143 validation complete';
    EXCEPTION WHEN SQLSTATE 'D1430' THEN
        IF SQLERRM <> 'dead143 validation complete' THEN RAISE; END IF;
    END;
    RETURN result;
END
$resolve$;
COMMENT ON FUNCTION pg_temp.dead143_resolve(text, text[], text[]) IS 'Migration 143 transaction-local prebuilt qualified lookup/decoding under every routine SET clause; native sentinel-subtransaction GUC unwind; removed before stamping.';

CREATE FUNCTION pg_temp.dead143_body(body text, function_oid oid, targets oid[], relation_targets oid[], names text[], setting_names text[], setting_values text[], nesting integer DEFAULT 0, literal_only boolean DEFAULT false) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog AS $scanner$
DECLARE
    effective_scs text := pg_temp.dead143_resolve('SELECT pg_catalog.current_setting(''standard_conforming_strings'')',setting_names,setting_values);
    tokens jsonb := pg_temp.dead143_tokens(body,effective_scs,setting_names,setting_values);
    i integer := 0;
    j integer;
    count_tokens integer := jsonb_array_length(tokens);
    name text;
    qualified text;
    kind text;
    expression text;
    folded text;
    relation_oid oid;
    type_oid oid;
    column_type oid;
    found_column boolean;
    left_edge integer;
    right_edge integer;
    relation_at integer;
    alias_name text;
    qualifier text;
    relation_name text;
    type_context boolean;
    catalog_kind text;
    catalog_at integer;
    expression_left integer;
    expression_right integer;
    depth integer;
    column_position boolean;
    clause text;
    catalog_types text[] := ARRAY['regclass','regtype','regproc','regprocedure','regoper','regoperator','regconfig','regdictionary','regnamespace','regrole','regcollation'];
    r record;
    token jsonb;
    fold_end text;
    statement_initial boolean;
    group_openers integer[];
    opener integer;
    returning_type boolean;
    literal_names text[];
    literal_name text;
    fold_start integer;
    argument_commas integer;
    nested_definition boolean;
    atomic_fold boolean;
BEGIN
    IF nesting > 8 THEN RAISE EXCEPTION 'unresolved nested dynamic SQL'; END IF;
    FOR token IN SELECT value FROM jsonb_array_elements(tokens) LOOP
        name := token->>'v';
        IF token->>'k'='string' THEN
            literal_names := ARRAY[name];
            IF position('{' in name)>0 THEN
                BEGIN
                    literal_names := ARRAY[name] || ARRAY(
                        SELECT jsonb_array_elements_text(pg_temp.dead143_resolve(
                            'SELECT pg_catalog.array_to_json(ARRAY(SELECT pg_catalog.unnest('||quote_literal(name)||
                            '::pg_catalog.text[])))::pg_catalog.text',
                            setting_names,setting_values)::jsonb));
                EXCEPTION WHEN OTHERS THEN literal_names := ARRAY[name]; END;
            END IF;
            FOREACH literal_name IN ARRAY literal_names LOOP
            -- Each input parser may reject non-name data independently: a type
            -- name such as item_type[] need not be a valid relation name.
            BEGIN
                relation_oid := pg_temp.dead143_resolve('SELECT pg_catalog.to_regclass('||quote_literal(literal_name)||')::pg_catalog.oid::pg_catalog.text',setting_names,setting_values)::oid;
            EXCEPTION WHEN OTHERS THEN relation_oid := NULL; END;
            BEGIN
                type_oid := pg_temp.dead143_resolve('SELECT pg_catalog.to_regtype('||quote_literal(literal_name)||')::pg_catalog.oid::pg_catalog.text',setting_names,setting_values)::oid;
            EXCEPTION WHEN OTHERS THEN type_oid := NULL; END;
            IF relation_oid=ANY(relation_targets) OR type_oid=ANY(targets) THEN
                RAISE EXCEPTION 'literal names a drop target: %',literal_name;
            END IF;
            END LOOP;
        END IF;
    END LOOP;
    WHILE i < count_tokens LOOP
        name := tokens->i->>'v'; kind := tokens->i->>'k';
        statement_initial := i=0 OR (tokens->(i-1)->>'k'='punct' AND tokens->(i-1)->>'v'=';')
            OR (tokens->(i-1)->>'k'='id' AND tokens->(i-1)->>'v' IN ('begin','then','else','loop'))
            OR (tokens->(i-1)->>'k'='id' AND tokens->(i-1)->>'v'='atomic' AND tokens->(i-2)->>'v'='begin');
        IF NOT literal_only THEN
        IF kind IN ('id','qid') AND name='set_config' THEN
            RAISE EXCEPTION 'unresolved runtime environment change: set_config';
        END IF;
        IF kind='id' AND name IN ('set','reset') AND statement_initial THEN
            RAISE EXCEPTION 'unresolved runtime environment change: %',name;
        END IF;
        j := i+1;
        IF tokens->j->>'k'='id' AND tokens->j->>'v'='only' THEN j := j+1; END IF;
        IF tokens->j->>'k'='punct' AND tokens->j->>'v'='(' THEN j := j+1; END IF;
        IF kind='id' AND name='update' AND (
            tokens->j->>'v'='pg_settings' OR
            (tokens->j->>'v'='pg_catalog' AND tokens->(j+1)->>'v'='.' AND tokens->(j+2)->>'v'='pg_settings')
        ) THEN RAISE EXCEPTION 'unresolved runtime pg_settings mutation'; END IF;
        END IF;
        -- CREATE bodies are constant SQL too. Refuse inner environment/language
        -- forms rather than guessing an environment different from the wrapper.
        nested_definition := false; atomic_fold := false; fold_start := NULL;
        IF kind='id' AND name='create' AND NOT (
            i=0 AND nesting=0 AND EXISTS (SELECT 1 FROM pg_proc
                WHERE oid=function_oid AND prosqlbody IS NOT NULL)
        ) THEN
            j := i+1;
            IF tokens->j->>'v'='or' AND tokens->(j+1)->>'v'='replace' THEN j := j+2; END IF;
            IF tokens->j->>'k'='id' AND tokens->j->>'v' IN ('function','procedure') THEN
                nested_definition := true; j := j+1; depth := 0;
                WHILE j<count_tokens LOOP
                    IF tokens->j->>'k'='id' AND tokens->j->>'v'='set' THEN
                        RAISE EXCEPTION 'unresolved nested routine SET environment';
                    END IF;
                    IF tokens->j->>'k'='id' AND tokens->j->>'v'='language'
                        AND tokens->(j+1)->>'v' NOT IN ('sql','plpgsql') THEN
                        RAISE EXCEPTION 'unresolved nested routine language';
                    END IF;
                    IF tokens->j->>'k'='id' AND tokens->j->>'v'='as'
                        AND depth=0 THEN fold_start := j+1; EXIT; END IF;
                    IF tokens->j->>'k'='id' AND tokens->j->>'v'='begin'
                        AND tokens->(j+1)->>'v'='atomic' AND depth=0 THEN
                        expression := ''; depth := 1; j := j+2;
                        WHILE j<count_tokens AND depth>0 LOOP
                            IF tokens->j->>'k'='id' AND tokens->j->>'v' IN ('begin','case') THEN depth := depth+1;
                            ELSIF tokens->j->>'k'='id' AND tokens->j->>'v'='end' THEN depth := depth-1; END IF;
                            IF depth>0 THEN expression := expression||' '||(tokens->j->>'raw'); END IF;
                            j := j+1;
                        END LOOP;
                        IF depth<>0 THEN RAISE EXCEPTION 'unresolved nested BEGIN ATOMIC'; END IF;
                        PERFORM pg_temp.dead143_body(expression,function_oid,targets,relation_targets,names,setting_names,setting_values,nesting+1);
                        atomic_fold := true; EXIT;
                    END IF;
                    IF tokens->j->>'k'='punct' AND tokens->j->>'v'='(' THEN depth := depth+1;
                    ELSIF tokens->j->>'k'='punct' AND tokens->j->>'v'=')' THEN depth := depth-1;
                    ELSIF tokens->j->>'k'='punct' AND tokens->j->>'v'=';' THEN EXIT; END IF;
                    j := j+1;
                END LOOP;
                IF fold_start IS NULL THEN
                    IF atomic_fold THEN i := i+1; CONTINUE; END IF;
                    RAISE EXCEPTION 'unresolved nested routine body';
                END IF;
            END IF;
        END IF;
        -- Only the two-argument ts_rewrite consumes SQL, in argument two.
        IF kind IN ('id','qid') AND name='ts_rewrite'
            AND tokens->(i+1)->>'k'='punct' AND tokens->(i+1)->>'v'='(' THEN
            j := i+2; depth := 0; argument_commas := 0;
            WHILE j<count_tokens LOOP
                IF tokens->j->>'k'='punct' THEN
                    IF tokens->j->>'v'='(' THEN depth := depth+1;
                    ELSIF tokens->j->>'v'=')' THEN
                        IF depth=0 THEN EXIT; END IF;
                        depth := depth-1;
                    ELSIF tokens->j->>'v'=',' AND depth=0 THEN
                        argument_commas := argument_commas+1; fold_start := j+1;
                    END IF;
                END IF;
                j := j+1;
            END LOOP;
            IF argument_commas=2 THEN fold_start := NULL;
            ELSIF argument_commas<>1 OR j=count_tokens THEN RAISE EXCEPTION 'unresolved ts_rewrite arguments'; END IF;
        END IF;
        IF fold_start IS NOT NULL OR (NOT literal_only AND kind='id' AND (name='execute' OR (name='do' AND statement_initial)))
            OR (kind IN ('id','qid') AND name IN ('query_to_xml','query_to_xmlschema',
                'query_to_xml_and_xmlschema','ts_stat')
                AND tokens->(i+1)->>'k'='punct' AND tokens->(i+1)->>'v'='(') THEN
            expression := ''; j := i+1; depth := 0;
            fold_end := CASE WHEN name IN ('execute','do') OR nested_definition THEN 'statement' ELSE 'argument' END;
            IF name='do' AND tokens->j->>'k'='id' AND tokens->j->>'v'='language' THEN j := j+2; END IF;
            IF fold_end='argument' THEN j := j+1; END IF;
            IF fold_start IS NOT NULL THEN j := fold_start; END IF;
            WHILE j<count_tokens LOOP
                IF depth=0 AND ((tokens->j->>'k'='punct' AND tokens->j->>'v'=';')
                    OR (fold_end='statement' AND tokens->j->>'k'='id' AND tokens->j->>'v' IN ('into','using','loop','language'))
                    OR (fold_end='argument' AND tokens->j->>'k'='punct' AND tokens->j->>'v' IN (',',')'))) THEN EXIT; END IF;
                IF tokens->j->>'k'='punct' AND tokens->j->>'v'='(' THEN depth := depth+1;
                ELSIF tokens->j->>'k'='punct' AND tokens->j->>'v'=')' THEN depth := depth-1; END IF;
                IF tokens->j->>'k' = 'string' OR (tokens->j->>'k'='punct' AND tokens->j->>'v' IN ('(',')',',','||')) THEN
                    expression := expression || ' ' || (tokens->j->>'raw');
                ELSIF tokens->j->>'k'='punct' AND tokens->j->>'v'='::'
                    AND tokens->(j+1)->>'k'='id' AND tokens->(j+1)->>'v'='text' THEN
                    -- pg_get_* deparsers attach this builtin cast to text constants.
                    expression := expression || '::pg_catalog.text'; j := j+1;
                ELSIF tokens->j->>'k'='id' AND tokens->j->>'v' = 'pg_catalog' AND tokens->(j+1)->>'v' = '.' AND tokens->(j+2)->>'v' IN ('format','concat') THEN
                    expression := expression || ' pg_catalog.' || (tokens->(j+2)->>'v');
                    j := j + 2;
                ELSIF tokens->j->>'k' = 'id' AND tokens->j->>'v' IN ('format','concat')
                    AND tokens->(j+1)->>'v' = '(' THEN
                    expression := expression || ' ' || (tokens->j->>'raw');
                ELSE
                    RAISE EXCEPTION 'target public.items/public.ai_notebook or enum: unresolved dynamic EXECUTE expression';
                END IF;
                j := j + 1;
            END LOOP;
            IF expression = '' THEN RAISE EXCEPTION 'unresolved empty EXECUTE'; END IF;
            folded := pg_temp.dead143_resolve('SELECT ('||expression||')::pg_catalog.text',array_append(setting_names,'search_path'),array_append(setting_values,'pg_catalog'));
            IF folded IS NULL THEN RAISE EXCEPTION 'unresolved NULL EXECUTE'; END IF;
            PERFORM pg_temp.dead143_body(folded,function_oid,targets,relation_targets,names,setting_names,setting_values,nesting+1);
            i := CASE WHEN nested_definition THEN i+1 ELSE j END; CONTINUE;
        END IF;
        IF literal_only THEN i := i+1; CONTINUE; END IF;
        -- Catalog casts are inspected from their operator, not from a literal:
        -- this catches CAST, parentheses, and computed expressions uniformly.
        catalog_kind := NULL; expression_left := NULL; expression_right := NULL;
        IF kind='id' AND (name=ANY(catalog_types) OR name LIKE 'to_reg%'
            OR name IN ('nextval','currval','setval')) THEN
            catalog_kind := CASE
                WHEN name IN ('nextval','currval','setval') THEN 'regclass'
                WHEN name LIKE 'to_reg%' THEN substr(name,4)
                ELSE name END;
            IF NOT catalog_kind=ANY(catalog_types) THEN
                RAISE EXCEPTION 'unresolved catalog lookup %',name;
            END IF;
            IF tokens->(i+1)->>'k'='string' AND name=ANY(catalog_types) THEN
                expression_left := i+1; expression_right := i+1;
            ELSIF tokens->(i+1)->>'v'='(' THEN
                expression_left := i+2; j := i+2; depth := 0;
                WHILE j<count_tokens LOOP
                    IF tokens->j->>'k'='punct' AND tokens->j->>'v'='(' THEN depth := depth+1;
                    ELSIF tokens->j->>'k'='punct' AND tokens->j->>'v'=')' THEN
                        IF depth=0 THEN EXIT; END IF;
                        depth := depth-1;
                    ELSIF depth=0 AND tokens->j->>'k'='punct' AND tokens->j->>'v'=',' THEN EXIT; END IF;
                    j := j+1;
                END LOOP;
                expression_right := j-1;
            ELSE catalog_kind := NULL; END IF;
        ELSIF kind='punct' AND name='::' THEN
            catalog_at := i+1;
            IF tokens->catalog_at->>'v'='pg_catalog' AND tokens->(catalog_at+1)->>'v'='.' THEN
                catalog_at := catalog_at+2;
            END IF;
            catalog_kind := tokens->catalog_at->>'v';
            expression_right := i-1; expression_left := expression_right;
            IF tokens->expression_right->>'k'='punct' AND tokens->expression_right->>'v'=')' THEN
                depth := 1; expression_left := expression_right-1;
                WHILE expression_left>=0 AND depth>0 LOOP
                    IF tokens->expression_left->>'k'='punct' AND tokens->expression_left->>'v'=')' THEN depth := depth+1;
                    ELSIF tokens->expression_left->>'k'='punct' AND tokens->expression_left->>'v'='(' THEN depth := depth-1; END IF;
                    IF depth>0 THEN expression_left := expression_left-1; END IF;
                END LOOP;
                -- A function call is computed, even if all its arguments are literals.
                IF tokens->(expression_left-1)->>'k'='id'
                    AND tokens->(expression_left-1)->>'v' NOT IN ('select','perform','return','then','when','else') THEN
                    expression_left := expression_left-1;
                END IF;
            END IF;
        ELSIF kind='id' AND name='cast' AND tokens->(i+1)->>'v'='(' THEN
            depth := 0; j := i+2;
            WHILE j<count_tokens LOOP
                IF tokens->j->>'k'='punct' AND tokens->j->>'v'='(' THEN depth := depth+1;
                ELSIF tokens->j->>'k'='punct' AND tokens->j->>'v'=')' THEN
                    IF depth=0 THEN EXIT; END IF;
                    depth := depth-1;
                ELSIF depth=0 AND tokens->j->>'k'='id' AND tokens->j->>'v'='as' THEN
                    expression_left := i+2; expression_right := j-1;
                    catalog_at := j+1;
                    IF tokens->catalog_at->>'v'='pg_catalog' AND tokens->(catalog_at+1)->>'v'='.' THEN
                        catalog_at := catalog_at+2;
                    END IF;
                    catalog_kind := tokens->catalog_at->>'v'; EXIT;
                END IF;
                j := j+1;
            END LOOP;
        END IF;
        IF catalog_kind=ANY(catalog_types) OR catalog_kind='regtypeoid' THEN
            -- Strip only parentheses enclosing the complete expression.
            WHILE expression_left<expression_right AND tokens->expression_left->>'k'='punct' AND tokens->expression_left->>'v'='('
                AND tokens->expression_right->>'k'='punct' AND tokens->expression_right->>'v'=')' LOOP
                depth := 0; j := expression_left;
                WHILE j<expression_right LOOP
                    IF tokens->j->>'k'='punct' AND tokens->j->>'v'='(' THEN depth := depth+1;
                    ELSIF tokens->j->>'k'='punct' AND tokens->j->>'v'=')' THEN depth := depth-1; END IF;
                    IF depth=0 THEN EXIT; END IF;
                    j := j+1;
                END LOOP;
                IF j<expression_right THEN EXIT; END IF;
                expression_left := expression_left+1; expression_right := expression_right-1;
            END LOOP;
            IF expression_left IS NULL OR expression_left<>expression_right
                OR tokens->expression_left->>'k' IS DISTINCT FROM 'string' THEN
                RAISE EXCEPTION 'unresolved computed catalog cast/lookup %',catalog_kind;
            END IF;
            folded := tokens->expression_left->>'v';
            relation_oid := NULL; type_oid := NULL;
            BEGIN
                relation_oid := pg_temp.dead143_resolve(
                    'SELECT '||quote_literal(folded)||'::pg_catalog.'||
                    quote_ident(CASE WHEN catalog_kind='regtypeoid' THEN 'regtype' ELSE catalog_kind END)||'::pg_catalog.oid',
                    setting_names,setting_values)::oid;
            EXCEPTION WHEN OTHERS THEN
                RAISE EXCEPTION 'unresolved catalog literal % for %: %',folded,catalog_kind,SQLERRM;
            END;
            IF catalog_kind IN ('regtype','regtypeoid') THEN type_oid := relation_oid; END IF;
            IF (catalog_kind='regclass' AND relation_oid=ANY(relation_targets)) OR type_oid=ANY(targets) THEN
                RAISE EXCEPTION 'target %: catalog body reference',folded;
            END IF;
        END IF;
        IF kind IN ('id','qid') AND name = ANY(names) THEN
            qualified := quote_ident(name);
            IF i >= 2 AND tokens->(i-1)->>'v' = '.' AND tokens->(i-2)->>'k' IN ('id','qid') THEN
                qualified := quote_ident(tokens->(i-2)->>'v') || '.' || qualified;
            END IF;
            type_context := tokens->(i+1)->>'k'='string'
                OR (tokens->(i+1)->>'k'='punct' AND tokens->(i+1)->>'v'='(')
                OR (i>0 AND ((tokens->(i-1)->>'k'='punct' AND tokens->(i-1)->>'v'='::')
                    OR (tokens->(i-1)->>'k'='id' AND tokens->(i-1)->>'v'='as')));
            IF i>=3 AND tokens->(i-1)->>'v'='.' THEN
                type_context := coalesce(type_context,false)
                    OR (tokens->(i-3)->>'k'='punct' AND tokens->(i-3)->>'v'='::')
                    OR (tokens->(i-3)->>'k'='id' AND tokens->(i-3)->>'v'='as');
            END IF;
            -- NEW/OLD is a column use, not an enum use, only with catalog proof.
            IF i >= 2 AND tokens->(i-1)->>'v' = '.' AND tokens->(i-2)->>'v' IN ('new','old')
                AND NOT coalesce(type_context,false) THEN
                found_column := false;
                FOR r IN SELECT tgrelid FROM pg_trigger WHERE tgfoid = function_oid LOOP
                    SELECT atttypid INTO column_type FROM pg_attribute
                    WHERE attrelid=r.tgrelid AND attname=name AND attnum>0 AND NOT attisdropped;
                    IF column_type IS NULL OR column_type = ANY(targets) THEN
                        RAISE EXCEPTION 'target public.%: unresolved or target-typed column % on %',name,qualified,r.tgrelid::regclass;
                    END IF;
                    found_column := true;
                END LOOP;
                IF NOT found_column THEN RAISE EXCEPTION 'target public.%: unbound %',name,qualified; END IF;
            ELSE
                -- Prove a query-column use in this semicolon-delimited statement.
                -- Recognize direct relation names and FROM/JOIN/UPDATE/INTO aliases.
                -- Cast/declaration type contexts cannot borrow a column's proof.
                left_edge := i; right_edge := i;
                WHILE left_edge>0 AND NOT (tokens->(left_edge-1)->>'k'='punct' AND tokens->(left_edge-1)->>'v'=';') LOOP left_edge := left_edge-1; END LOOP;
                WHILE right_edge<count_tokens-1 AND NOT (tokens->(right_edge+1)->>'k'='punct' AND tokens->(right_edge+1)->>'v'=';') LOOP right_edge := right_edge+1; END LOOP;
                qualifier := NULL;
                IF i>=2 AND tokens->(i-1)->>'v'='.' THEN qualifier := tokens->(i-2)->>'v'; END IF;
                found_column := false;
                -- Classify expression clauses, rather than only SELECT's
                -- first column. Declarations/types never borrow column proof.
                clause := NULL; group_openers := ARRAY[]::integer[];
                returning_type := false;
                FOR j IN left_edge..i LOOP
                    IF tokens->j->>'k'='punct' AND tokens->j->>'v'='(' THEN
                        group_openers := array_append(group_openers,j);
                    ELSIF tokens->j->>'k'='punct' AND tokens->j->>'v'=')' THEN
                        group_openers := group_openers[1:coalesce(array_length(group_openers,1),0)-1];
                        returning_type := false;
                    END IF;
                    IF tokens->j->>'k'='id' AND tokens->j->>'v'='returning' THEN
                        opener := group_openers[array_length(group_openers,1)];
                        IF opener IS NULL OR (tokens->(opener+1)->>'k'='id' AND tokens->(opener+1)->>'v' IN ('insert','update','delete','merge')) THEN
                            returning_type := false;
                        ELSIF tokens->(opener-1)->>'k' IN ('id','qid')
                            AND NOT (tokens->(opener-1)->>'k'='id' AND tokens->(opener-1)->>'v' IN ('as','in','exists')) THEN
                            returning_type := true;
                        ELSE RAISE EXCEPTION 'unclassifiable RETURNING context'; END IF;
                    END IF;
                    IF tokens->j->>'k'='id' AND tokens->j->>'v' IN
                        ('select','where','having','on','group','order','returning','set',
                         'from','join','update','into','declare','begin','returns') THEN
                        clause := tokens->j->>'v';
                    END IF;
                END LOOP;
                FOREACH opener IN ARRAY group_openers LOOP
                    IF (tokens->(opener-1)->>'k'='id' AND tokens->(opener-1)->>'v'='columns')
                        OR (tokens->(opener-2)->>'k'='id' AND tokens->(opener-2)->>'v'='as'
                            AND tokens->(opener-3)->>'k'='punct' AND tokens->(opener-3)->>'v'=')')
                        OR (tokens->(opener-1)->>'k' IN ('id','qid')
                            AND tokens->(opener-2)->>'k'='punct' AND tokens->(opener-2)->>'v'=')')
                        OR (tokens->(opener-1)->>'k'='id' AND tokens->(opener-1)->>'v'='xmltable'
                            AND EXISTS (SELECT 1 FROM generate_series(opener+1,i) k
                                WHERE tokens->k->>'k'='id' AND tokens->k->>'v'='columns')) THEN
                        RAISE EXCEPTION 'unclassifiable column-definition list: %',name;
                    END IF;
                END LOOP;
                type_context := coalesce(type_context,false) OR returning_type;
                column_position := clause IN ('select','where','having','on','group','order','returning','set');
                IF clause IN ('declare','returns') AND NOT (
                    tokens->(i+1)->>'v'='%' AND tokens->(i+2)->>'v'='type'
                ) THEN type_context := true; END IF;
                IF coalesce(column_position,false) AND NOT coalesce(type_context,false) THEN
                    FOR j IN left_edge..right_edge LOOP
                        IF tokens->j->>'k'='id' AND tokens->j->>'v' IN ('from','join','update','into') AND tokens->(j+1)->>'k' IN ('id','qid') THEN
                            relation_at := j+1;
                            relation_name := quote_ident(tokens->relation_at->>'v');
                            IF tokens->(relation_at+1)->>'v'='.' AND tokens->(relation_at+2)->>'k' IN ('id','qid') THEN
                                relation_at := relation_at+2;
                                relation_name := relation_name||'.'||quote_ident(tokens->relation_at->>'v');
                            END IF;
                            -- A relation name itself is never a column exemption.
                            IF i BETWEEN j+1 AND relation_at THEN CONTINUE; END IF;
                            relation_oid := pg_temp.dead143_resolve('SELECT pg_catalog.to_regclass('||quote_literal(relation_name)||')::pg_catalog.oid',setting_names,setting_values)::oid;
                            alias_name := tokens->(relation_at+1)->>'v';
                            IF alias_name='as' THEN alias_name := tokens->(relation_at+2)->>'v'; END IF;
                            IF qualifier IS NULL OR qualifier IN (alias_name,tokens->relation_at->>'v') THEN
                                SELECT atttypid INTO column_type FROM pg_attribute
                                WHERE attrelid=relation_oid AND attname=name AND attnum>0 AND NOT attisdropped;
                                IF column_type IS NOT NULL AND NOT column_type=ANY(targets) THEN found_column := true;
                                ELSIF column_type=ANY(targets) THEN RAISE EXCEPTION 'target public.%: target-typed query column on %',name,relation_name; END IF;
                            END IF;
                        END IF;
                    END LOOP;
                END IF;
                IF found_column THEN i := i+1; CONTINUE; END IF;
                type_oid := pg_temp.dead143_resolve('SELECT pg_catalog.to_regtype('||quote_literal(qualified)||')::pg_catalog.oid',setting_names,setting_values)::oid;
                relation_oid := pg_temp.dead143_resolve('SELECT pg_catalog.to_regclass('||quote_literal(qualified)||')::pg_catalog.oid',setting_names,setting_values)::oid;
                IF type_oid = ANY(targets) OR relation_oid = ANY(relation_targets) THEN
                    RAISE EXCEPTION 'target %: hidden body identifier reference',qualified;
                END IF;
                -- A qualified column must resolve to a real, unrelated column.
                IF i >= 2 AND tokens->(i-1)->>'v' = '.' AND NOT coalesce(type_context,false) THEN
                    relation_name := quote_ident(tokens->(i-2)->>'v');
                    IF i>=4 AND tokens->(i-3)->>'v'='.' AND tokens->(i-4)->>'k' IN ('id','qid') THEN
                        relation_name := quote_ident(tokens->(i-4)->>'v')||'.'||relation_name;
                    END IF;
                    relation_oid := pg_temp.dead143_resolve('SELECT pg_catalog.to_regclass('||quote_literal(relation_name)||')::pg_catalog.oid',setting_names,setting_values)::oid;
                    SELECT atttypid INTO column_type FROM pg_attribute
                    WHERE attrelid=relation_oid AND attname=name AND attnum>0 AND NOT attisdropped;
                    IF column_type IS NOT NULL AND NOT column_type = ANY(targets) THEN
                        i := i + 1; CONTINUE;
                    END IF;
                END IF;
                IF type_oid IS NULL AND relation_oid IS NULL THEN
                    RAISE EXCEPTION 'target public.%: unsupported or unresolved body identifier %',name,qualified;
                END IF;
            END IF;
        END IF;
        i := i + 1;
    END LOOP;
END
$scanner$;
COMMENT ON FUNCTION pg_temp.dead143_body(text, oid, oid[], oid[], text[], text[], text[], integer, boolean) IS 'Migration 143 transaction-local catalog-aware body guard, including constant dynamic SQL folding; removed before stamping.';

DO $guard$
DECLARE
    enum_manifest jsonb := $manifest$
[
    [
        "public",
        "agent_type",
        "e",
        [
            "LOGON",
            "LORE",
            "GAIA",
            "PSYCHE",
            "MEMNON",
            "MAESTRO",
            "NEMESIS"
        ],
        null
    ],
    [
        "public",
        "emotional_valence",
        "e",
        [
            "+5|devoted",
            "+4|admiring",
            "+3|trusting",
            "+2|friendly",
            "+1|favorable",
            "0|neutral",
            "-1|wary",
            "-2|disapproving",
            "-3|resentful",
            "-4|hostile",
            "-5|hateful"
        ],
        null
    ],
    [
        "public",
        "entity_type",
        "e",
        [
            "character",
            "faction",
            "place",
            "item"
        ],
        null
    ],
    [
        "public",
        "item_type",
        "e",
        [
            "currency",
            "weapon",
            "cybernetic",
            "tech",
            "wearable",
            "consumable",
            "tool",
            "data",
            "artifact"
        ],
        null
    ],
    [
        "public",
        "log_level_type",
        "e",
        [
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL"
        ],
        null
    ],
    [
        "public",
        "relationship_type",
        "e",
        [
            "family",
            "romantic",
            "friend",
            "companion",
            "ally",
            "contact",
            "pedagogical",
            "professional",
            "authority",
            "rival",
            "enemy",
            "acquaintance",
            "stranger",
            "complex",
            "chosen_kin",
            "comrade",
            "handler",
            "asset",
            "ward",
            "guardian",
            "captor",
            "mentor",
            "patron"
        ],
        null
    ],
    [
        "public",
        "threat_domain_type",
        "e",
        [
            "physical",
            "psychological",
            "social",
            "environmental"
        ],
        null
    ],
    [
        "public",
        "threat_lifecycle_type",
        "e",
        [
            "inception",
            "gestation",
            "manifestation",
            "escalation",
            "culmination",
            "resolution",
            "aftermath"
        ],
        null
    ],
    [
        "public",
        "trait",
        "e",
        [
            "allies",
            "contacts",
            "patron",
            "dependents",
            "status",
            "reputation",
            "resources",
            "domain",
            "enemies",
            "obligations"
        ],
        null
    ]
]
$manifest$;
    column_manifest jsonb := $manifest$
[
    [
        "ai_notebook",
        "id",
        "bigint",
        true,
        "nextval('public.ai_notebook_id_seq'::regclass)",
        null
    ],
    [
        "ai_notebook",
        "timestamp",
        "timestamp with time zone",
        true,
        "now()",
        null
    ],
    [
        "ai_notebook",
        "log_entry",
        "text",
        true,
        null,
        null
    ],
    [
        "ai_notebook",
        "agent",
        "public.agent_type",
        true,
        null,
        null
    ],
    [
        "ai_notebook",
        "level",
        "public.log_level_type",
        true,
        "'INFO'::public.log_level_type",
        null
    ],
    [
        "items",
        "id",
        "bigint",
        true,
        "nextval('public.items_id_seq'::regclass)",
        "Unique item identifier"
    ],
    [
        "items",
        "type",
        "character varying(100)",
        true,
        null,
        "Category or classification of item (weapon, data, artifact, etc.)"
    ],
    [
        "items",
        "quantity",
        "integer",
        true,
        "1",
        "Number of units if stackable/countable"
    ],
    [
        "items",
        "summary",
        "character varying(500)",
        true,
        null,
        "Brief description of the item"
    ],
    [
        "items",
        "name",
        "character varying(50)",
        true,
        null,
        "Item name or designation"
    ],
    [
        "items",
        "owner_id",
        "bigint",
        false,
        null,
        "Foreign key to characters.id - current owner/possessor"
    ],
    [
        "items",
        "history",
        "text",
        false,
        null,
        "Provenance and past ownership/usage of the item"
    ],
    [
        "items",
        "status",
        "character varying(50)",
        true,
        "'functional'::character varying",
        "Current condition (intact, damaged, active, depleted, etc.)"
    ],
    [
        "items",
        "extra_data",
        "jsonb",
        false,
        null,
        "JSONB for item-specific properties, abilities, or metadata"
    ],
    [
        "items",
        "created_at",
        "timestamp with time zone",
        true,
        "now()",
        "When item record was created"
    ],
    [
        "items",
        "updated_at",
        "timestamp with time zone",
        true,
        "now()",
        "Last modification to item record"
    ]
]
$manifest$;
    permitted text[] := ARRAY[
        'pg_attrdef:default value for column created_at of table public.items',
        'pg_attrdef:default value for column id of table public.ai_notebook',
        'pg_attrdef:default value for column id of table public.items',
        'pg_attrdef:default value for column level of table public.ai_notebook',
        'pg_attrdef:default value for column quantity of table public.items',
        'pg_attrdef:default value for column status of table public.items',
        'pg_attrdef:default value for column timestamp of table public.ai_notebook',
        'pg_attrdef:default value for column updated_at of table public.items',
        'pg_class:column agent of table public.ai_notebook',
        'pg_class:column created_at of table public.items',
        'pg_class:column extra_data of table public.items',
        'pg_class:column history of table public.items',
        'pg_class:column id of table public.ai_notebook',
        'pg_class:column id of table public.items',
        'pg_class:column level of table public.ai_notebook',
        'pg_class:column log_entry of table public.ai_notebook',
        'pg_class:column name of table public.items',
        'pg_class:column owner_id of table public.items',
        'pg_class:column quantity of table public.items',
        'pg_class:column status of table public.items',
        'pg_class:column summary of table public.items',
        'pg_class:column timestamp of table public.ai_notebook',
        'pg_class:column type of table public.items',
        'pg_class:column updated_at of table public.items',
        'pg_class:index pg_toast.pg_toast_TABLEOID_index',
        'pg_class:index pg_toast.pg_toast_TABLEOID_index',
        'pg_class:index public.ai_notebook_pkey',
        'pg_class:index public.items_name_key',
        'pg_class:index public.items_pkey',
        'pg_class:sequence public.ai_notebook_id_seq',
        'pg_class:sequence public.items_id_seq',
        'pg_class:table public.ai_notebook',
        'pg_class:table public.items',
        'pg_class:toast table pg_toast.pg_toast_TABLEOID',
        'pg_class:toast table pg_toast.pg_toast_TABLEOID',
        'pg_constraint:constraint ai_notebook_pkey on table public.ai_notebook',
        'pg_constraint:constraint items_name_key on table public.items',
        'pg_constraint:constraint items_owner_id_fkey1 on table public.items',
        'pg_constraint:constraint items_pkey on table public.items',
        'pg_trigger:trigger RI_ConstraintTrigger_a_OID on table public.characters',
        'pg_trigger:trigger RI_ConstraintTrigger_a_OID on table public.characters',
        'pg_trigger:trigger RI_ConstraintTrigger_c_OID on table public.items',
        'pg_trigger:trigger RI_ConstraintTrigger_c_OID on table public.items',
        'pg_trigger:trigger trg_items_set_updated on table public.items',
        'pg_type:type public.agent_type',
        'pg_type:type public.agent_type[]',
        'pg_type:type public.ai_notebook',
        'pg_type:type public.ai_notebook[]',
        'pg_type:type public.emotional_valence',
        'pg_type:type public.emotional_valence[]',
        'pg_type:type public.entity_type',
        'pg_type:type public.entity_type[]',
        'pg_type:type public.item_type',
        'pg_type:type public.item_type[]',
        'pg_type:type public.items',
        'pg_type:type public.items[]',
        'pg_type:type public.log_level_type',
        'pg_type:type public.log_level_type[]',
        'pg_type:type public.relationship_type',
        'pg_type:type public.relationship_type[]',
        'pg_type:type public.threat_domain_type',
        'pg_type:type public.threat_domain_type[]',
        'pg_type:type public.threat_lifecycle_type',
        'pg_type:type public.threat_lifecycle_type[]',
        'pg_type:type public.trait',
        'pg_type:type public.trait[]'
    ];
    permitted_edges text[] := ARRAY[
        'pg_attrdef:default value for column created_at of table public.items:a:column created_at of table public.items',
        'pg_attrdef:default value for column id of table public.ai_notebook:a:column id of table public.ai_notebook',
        'pg_attrdef:default value for column id of table public.ai_notebook:n:sequence public.ai_notebook_id_seq',
        'pg_attrdef:default value for column id of table public.items:a:column id of table public.items',
        'pg_attrdef:default value for column id of table public.items:n:sequence public.items_id_seq',
        'pg_attrdef:default value for column level of table public.ai_notebook:a:column level of table public.ai_notebook',
        'pg_attrdef:default value for column level of table public.ai_notebook:n:type public.log_level_type',
        'pg_attrdef:default value for column quantity of table public.items:a:column quantity of table public.items',
        'pg_attrdef:default value for column status of table public.items:a:column status of table public.items',
        'pg_attrdef:default value for column timestamp of table public.ai_notebook:a:column timestamp of table public.ai_notebook',
        'pg_attrdef:default value for column updated_at of table public.items:a:column updated_at of table public.items',
        'pg_class:column agent of table public.ai_notebook:n:type public.agent_type',
        'pg_class:column level of table public.ai_notebook:n:type public.log_level_type',
        'pg_class:index pg_toast.pg_toast_TABLEOID_index:a:column chunk_id of toast table pg_toast.pg_toast_TABLEOID',
        'pg_class:index pg_toast.pg_toast_TABLEOID_index:a:column chunk_seq of toast table pg_toast.pg_toast_TABLEOID',
        'pg_class:index pg_toast.pg_toast_TABLEOID_index:a:column chunk_id of toast table pg_toast.pg_toast_TABLEOID',
        'pg_class:index pg_toast.pg_toast_TABLEOID_index:a:column chunk_seq of toast table pg_toast.pg_toast_TABLEOID',
        'pg_class:index public.ai_notebook_pkey:i:constraint ai_notebook_pkey on table public.ai_notebook',
        'pg_class:index public.items_name_key:i:constraint items_name_key on table public.items',
        'pg_class:index public.items_pkey:i:constraint items_pkey on table public.items',
        'pg_class:sequence public.ai_notebook_id_seq:a:column id of table public.ai_notebook',
        'pg_class:sequence public.ai_notebook_id_seq:n:schema public',
        'pg_class:sequence public.items_id_seq:a:column id of table public.items',
        'pg_class:sequence public.items_id_seq:n:schema public',
        'pg_class:table public.ai_notebook:n:schema public',
        'pg_class:table public.items:n:schema public',
        'pg_class:toast table pg_toast.pg_toast_TABLEOID:i:table public.ai_notebook',
        'pg_class:toast table pg_toast.pg_toast_TABLEOID:i:table public.items',
        'pg_constraint:constraint ai_notebook_pkey on table public.ai_notebook:a:column id of table public.ai_notebook',
        'pg_constraint:constraint items_name_key on table public.items:a:column name of table public.items',
        'pg_constraint:constraint items_owner_id_fkey1 on table public.items:a:column owner_id of table public.items',
        'pg_constraint:constraint items_owner_id_fkey1 on table public.items:n:column id of table public.characters',
        'pg_constraint:constraint items_owner_id_fkey1 on table public.items:n:index public.characters_pkey',
        'pg_constraint:constraint items_pkey on table public.items:a:column id of table public.items',
        'pg_trigger:trigger RI_ConstraintTrigger_a_OID on table public.characters:i:constraint items_owner_id_fkey1 on table public.items',
        'pg_trigger:trigger RI_ConstraintTrigger_a_OID on table public.characters:i:constraint items_owner_id_fkey1 on table public.items',
        'pg_trigger:trigger RI_ConstraintTrigger_c_OID on table public.items:i:constraint items_owner_id_fkey1 on table public.items',
        'pg_trigger:trigger RI_ConstraintTrigger_c_OID on table public.items:i:constraint items_owner_id_fkey1 on table public.items',
        'pg_trigger:trigger trg_items_set_updated on table public.items:a:table public.items',
        'pg_trigger:trigger trg_items_set_updated on table public.items:n:function public.set_updated_at()',
        'pg_type:type public.agent_type:n:schema public',
        'pg_type:type public.agent_type[]:i:type public.agent_type',
        'pg_type:type public.ai_notebook:i:table public.ai_notebook',
        'pg_type:type public.ai_notebook[]:i:type public.ai_notebook',
        'pg_type:type public.emotional_valence:n:schema public',
        'pg_type:type public.emotional_valence[]:i:type public.emotional_valence',
        'pg_type:type public.entity_type:n:schema public',
        'pg_type:type public.entity_type[]:i:type public.entity_type',
        'pg_type:type public.item_type:n:schema public',
        'pg_type:type public.item_type[]:i:type public.item_type',
        'pg_type:type public.items:i:table public.items',
        'pg_type:type public.items[]:i:type public.items',
        'pg_type:type public.log_level_type:n:schema public',
        'pg_type:type public.log_level_type[]:i:type public.log_level_type',
        'pg_type:type public.relationship_type:n:schema public',
        'pg_type:type public.relationship_type[]:i:type public.relationship_type',
        'pg_type:type public.threat_domain_type:n:schema public',
        'pg_type:type public.threat_domain_type[]:i:type public.threat_domain_type',
        'pg_type:type public.threat_lifecycle_type:n:schema public',
        'pg_type:type public.threat_lifecycle_type[]:i:type public.threat_lifecycle_type',
        'pg_type:type public.trait:n:schema public',
        'pg_type:type public.trait[]:i:type public.trait'
    ];
    names text[];
    tables oid[] := ARRAY[]::oid[];
    enums oid[] := ARRAY[]::oid[];
    targets oid[];
    target_name text;
    object_oid oid;
    sequence_oid oid;
    owner_oid oid;
    id_number integer;
    row_count bigint;
    actual jsonb;
    expected jsonb;
    offender record;
    f record;
    item jsonb;
    -- The path the session started with (reset_val, not the SET LOCAL above):
    -- the proxy for a routine that declares no search_path of its own.
    setting_names text[];
    setting_values text[];
    setting text;
    parsed_setting text[];
    relation_targets oid[];
    key text;
    edge_key text;
BEGIN
    PERFORM pg_catalog.set_config('search_path','pg_catalog',true);
    FOREACH target_name IN ARRAY ARRAY['items','ai_notebook'] LOOP
        SELECT c.oid,c.relowner INTO object_oid,owner_oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname=target_name AND c.relkind='r';
        IF object_oid IS NULL THEN RAISE EXCEPTION 'target public.%: missing or wrongly typed table identity',target_name; END IF;
        tables := array_append(tables,object_oid);
        EXECUTE format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE',target_name);
    END LOOP;
    -- Both locks are held before either row count.
    FOREACH object_oid IN ARRAY tables LOOP
        SELECT relname,relowner INTO target_name,owner_oid FROM pg_class WHERE oid=object_oid;
        EXECUTE format('SELECT count(*) FROM public.%I',target_name) INTO row_count;
        IF row_count <> 0 THEN RAISE EXCEPTION 'target public.%: % unexpected rows',target_name,row_count; END IF;
        SELECT attnum INTO id_number FROM pg_attribute WHERE attrelid=object_oid AND attname='id' AND NOT attisdropped;
        SELECT c.oid INTO sequence_oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname=target_name||'_id_seq' AND c.relkind='S' AND c.relowner=owner_oid;
        IF sequence_oid IS NULL OR NOT EXISTS (
            SELECT 1 FROM pg_depend WHERE classid='pg_class'::regclass AND objid=sequence_oid
            AND refclassid='pg_class'::regclass AND refobjid=object_oid AND refobjsubid=id_number AND deptype='a'
        ) THEN RAISE EXCEPTION 'target public.%: sequence public.%_id_seq identity or ownership mismatch',target_name,target_name; END IF;
    END LOOP;
    FOR item IN SELECT value FROM jsonb_array_elements(enum_manifest) LOOP
        SELECT t.oid INTO object_oid FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname='public' AND t.typname=item->>1 AND t.typtype='e';
        IF object_oid IS NULL THEN RAISE EXCEPTION 'target public.%: missing or wrongly typed enum identity',item->>1; END IF;
        SELECT jsonb_agg(enumlabel ORDER BY enumsortorder) INTO actual FROM pg_enum WHERE enumtypid=object_oid;
        IF actual IS DISTINCT FROM item->3 THEN RAISE EXCEPTION 'target public.%: enum labels differ from manifest',item->>1; END IF;
        enums := array_append(enums,object_oid);
    END LOOP;
    -- Validate frozen columns/defaults before permitting their closure identities.
    SELECT jsonb_agg(jsonb_build_array(c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,
        pg_get_expr(d.adbin,d.adrelid),col_description(c.oid,a.attnum)) ORDER BY c.relname,a.attnum)
    INTO actual FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid
    LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
    WHERE c.oid=ANY(tables) AND a.attnum>0 AND NOT a.attisdropped;
    IF actual IS DISTINCT FROM column_manifest THEN RAISE EXCEPTION 'target public.items/public.ai_notebook: columns or defaults differ from frozen manifest: %',actual; END IF;
    SELECT jsonb_agg(jsonb_build_array(conname,conrelid::regclass::text,pg_get_constraintdef(oid),obj_description(oid,'pg_constraint')) ORDER BY conname)
    INTO actual FROM pg_constraint WHERE conrelid=ANY(tables);
    IF actual IS DISTINCT FROM $manifest$
[
    [
        "ai_notebook_pkey",
        "public.ai_notebook",
        "PRIMARY KEY (id)",
        null
    ],
    [
        "items_name_key",
        "public.items",
        "UNIQUE (name)",
        null
    ],
    [
        "items_owner_id_fkey1",
        "public.items",
        "FOREIGN KEY (owner_id) REFERENCES public.characters(id) ON DELETE SET NULL",
        null
    ],
    [
        "items_pkey",
        "public.items",
        "PRIMARY KEY (id)",
        null
    ]
]
$manifest$::jsonb THEN RAISE EXCEPTION 'target public.items/public.ai_notebook: named constraint definitions differ: %',actual; END IF;
    IF (SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid=tables[1] AND tgname='trg_items_set_updated')
        IS DISTINCT FROM 'CREATE TRIGGER trg_items_set_updated BEFORE UPDATE ON public.items FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()' THEN
        RAISE EXCEPTION 'target public.items: trigger public.items.trg_items_set_updated identity differs';
    END IF;
    SELECT jsonb_agg(jsonb_build_array(t.tgrelid::regclass::text,t.tgfoid::regprocedure::text,t.tgtype,t.tgenabled,
        t.tgconstrrelid::regclass::text,t.tgdeferrable,t.tginitdeferred,encode(t.tgargs,'hex')) ORDER BY t.tgrelid::regclass::text,t.tgfoid::regprocedure::text)
    INTO actual FROM pg_trigger t JOIN pg_constraint c ON c.oid=t.tgconstraint
    WHERE c.conname='items_owner_id_fkey1' AND c.conrelid=tables[1] AND t.tgisinternal;
    IF actual IS DISTINCT FROM $manifest$
[
    [
        "public.characters",
        "\"RI_FKey_noaction_upd\"()",
        17,
        "O",
        "public.items",
        false,
        false,
        ""
    ],
    [
        "public.characters",
        "\"RI_FKey_setnull_del\"()",
        9,
        "O",
        "public.items",
        false,
        false,
        ""
    ],
    [
        "public.items",
        "\"RI_FKey_check_ins\"()",
        5,
        "O",
        "public.characters",
        false,
        false,
        ""
    ],
    [
        "public.items",
        "\"RI_FKey_check_upd\"()",
        17,
        "O",
        "public.characters",
        false,
        false,
        ""
    ]
]
$manifest$::jsonb THEN RAISE EXCEPTION 'target public.items: internal FK trigger definitions differ: %',actual; END IF;
    -- Every reached address is compared to an explicit manifest identity, including
    -- internal/automatic objects. Never authorize a dependent by deptype alone.
    FOR offender IN
        WITH RECURSIVE roots(classid,objid,objsubid,target) AS (
            SELECT 'pg_class'::regclass::oid,t,0,t::regclass::text FROM unnest(tables) t
            UNION SELECT 'pg_class'::regclass::oid,a.attrelid,a.attnum,a.attrelid::regclass::text FROM pg_attribute a WHERE a.attrelid=ANY(tables) AND a.attnum>0 AND NOT a.attisdropped
            UNION SELECT 'pg_type'::regclass::oid,t,0,t::regtype::text FROM unnest(enums) t
        ), closure AS (
            SELECT * FROM roots UNION
            SELECT d.classid,d.objid,d.objsubid,c.target FROM pg_depend d JOIN closure c
            ON d.refclassid=c.classid AND d.refobjid=c.objid AND (c.objsubid=0 OR d.refobjsubid=c.objsubid)
        ) SELECT c.classid,c.objid,c.objsubid,c.target,pg_describe_object(c.classid,c.objid,c.objsubid) AS identity,
            d.deptype,pg_describe_object(d.refclassid,d.refobjid,d.refobjsubid) AS referenced
          FROM closure c LEFT JOIN pg_depend d
          ON d.classid=c.classid AND d.objid=c.objid AND d.objsubid=c.objsubid
    LOOP
        key := offender.classid::regclass::text || ':' || offender.identity;
        edge_key := key||':'||offender.deptype::text||':'||offender.referenced;
        -- Normalize only TOASTs actually owned by the two targets and RI triggers
        -- actually attached to the frozen FK with definitions checked above.
        IF offender.classid='pg_class'::regclass THEN
            relation_targets := array_append(relation_targets,offender.objid);
            FOR f IN SELECT oid AS table_oid FROM pg_class WHERE oid=ANY(tables) LOOP
                key := replace(key,'pg_toast_'||f.table_oid::text,'pg_toast_TABLEOID');
                edge_key := replace(edge_key,'pg_toast_'||f.table_oid::text,'pg_toast_TABLEOID');
            END LOOP;
        ELSIF offender.classid='pg_trigger'::regclass AND EXISTS (
            SELECT 1 FROM pg_trigger t JOIN pg_constraint c ON c.oid=t.tgconstraint
            WHERE t.oid=offender.objid AND t.tgisinternal AND c.conname='items_owner_id_fkey1' AND c.conrelid=tables[1]
        ) THEN
            key := regexp_replace(key,'RI_ConstraintTrigger_([ac])_[0-9]+','RI_ConstraintTrigger_\1_OID');
            edge_key := regexp_replace(edge_key,'RI_ConstraintTrigger_([ac])_[0-9]+','RI_ConstraintTrigger_\1_OID');
        END IF;
        IF NOT key=ANY(permitted) THEN
            RAISE EXCEPTION 'target %: unexpected dependent % (catalog %)',offender.target,offender.identity,offender.classid::regclass;
        END IF;
        IF edge_key IS NOT NULL AND NOT edge_key=ANY(permitted_edges) THEN
            RAISE EXCEPTION 'target %: unexpected dependency edge % -> % (catalog %, deptype %)',
                offender.target,offender.identity,offender.referenced,offender.classid::regclass,offender.deptype;
        END IF;
    END LOOP;
    -- Resolve signature/domain/array types via the complete catalog closure.
    WITH RECURSIVE types(oid) AS (
        (SELECT unnest(enums) UNION SELECT reltype FROM pg_class WHERE oid=ANY(tables))
        UNION SELECT t.oid FROM pg_type t JOIN types b ON t.typbasetype=b.oid OR t.typelem=b.oid
    ) SELECT array_agg(oid) INTO targets FROM types;
    -- typname supplies the actual generated array names, never guessed spellings.
    SELECT array_agg(DISTINCT candidate) INTO names FROM (
        SELECT typname AS candidate FROM pg_type WHERE oid=ANY(targets)
        UNION SELECT relname FROM pg_class WHERE oid=ANY(tables)
        UNION SELECT relname FROM pg_class WHERE oid=ANY(relation_targets)
    ) candidates;

    FOR f IN SELECT p.*,l.lanname,format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) AS identity
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang
        WHERE p.prokind IN ('f','p','w','a') AND p.oid>=16384 AND n.nspname !~ '^pg_(temp|toast)'
        AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')
    LOOP
        BEGIN
            IF f.prosecdef AND f.proowner<>current_user::regrole::oid THEN
                RAISE EXCEPTION 'unresolved SECURITY DEFINER owner/search_path context';
            END IF;
            IF f.prokind<>'a' AND f.lanname NOT IN ('sql','plpgsql') THEN RAISE EXCEPTION 'unsupported application body language %',f.lanname; END IF;
            setting_names := ARRAY[]::text[]; setting_values := ARRAY[]::text[];
            FOR setting IN SELECT unnest(f.proconfig) LOOP
                parsed_setting := pg_temp.dead143_setting(setting);
                setting_names := array_append(setting_names,parsed_setting[1]);
                setting_values := array_append(setting_values,parsed_setting[2]);
            END LOOP;
            IF f.prokind='a' THEN
                FOR setting IN SELECT quote_literal(v) FROM pg_aggregate a,
                    LATERAL unnest(ARRAY[a.agginitval,a.aggminitval]) v WHERE a.aggfnoid=f.oid AND v IS NOT NULL LOOP
                    PERFORM pg_temp.dead143_body(setting,f.oid,targets,relation_targets,names,
                        array_append(setting_names,'standard_conforming_strings'),array_append(setting_values,'on'),0,true);
                END LOOP;
            ELSE
                IF f.prosqlbody IS NULL THEN
                    PERFORM pg_temp.dead143_body(f.prosrc,f.oid,targets,relation_targets,names,setting_names,setting_values);
                ELSE
                    PERFORM pg_temp.dead143_body(pg_get_functiondef(f.oid),f.oid,targets,relation_targets,names,
                        array_append(setting_names,'standard_conforming_strings'),array_append(setting_values,'on'));
                END IF;
                -- Defaults belong to the caller; parameter names are not body tokens.
                PERFORM pg_temp.dead143_body(pg_get_function_arguments(f.oid),f.oid,targets,relation_targets,names,
                    ARRAY['standard_conforming_strings'],ARRAY['on'],0,true);
            END IF;
        EXCEPTION WHEN OTHERS THEN
            RAISE EXCEPTION 'target public.items/public.ai_notebook/nine enums: function/procedure % refuses: %',f.identity,SQLERRM;
        END;
    END LOOP;
    -- Deparsers render with the migration's pinned string convention. Resolve
    -- their names under the session startup path, never under the DDL pin.
    FOR offender IN
        SELECT pg_describe_object('pg_class'::regclass,c.oid,0) AS identity,
               pg_get_viewdef(c.oid) AS definition
        FROM pg_class c WHERE c.oid>=16384 AND c.relkind IN ('v','m')
        AND NOT c.oid=ANY(relation_targets)
        AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e')
        UNION ALL
        SELECT pg_describe_object('pg_constraint'::regclass,c.oid,0),pg_get_expr(c.conbin,c.conrelid)
        FROM pg_constraint c WHERE c.oid>=16384 AND c.conbin IS NOT NULL
        AND NOT c.conrelid=ANY(relation_targets) AND NOT c.contypid=ANY(targets)
        UNION ALL
        SELECT pg_describe_object('pg_attrdef'::regclass,a.oid,0),pg_get_expr(a.adbin,a.adrelid)
        FROM pg_attrdef a WHERE a.oid>=16384 AND NOT a.adrelid=ANY(relation_targets)
        UNION ALL
        SELECT pg_describe_object('pg_trigger'::regclass,t.oid,0),pg_get_triggerdef(t.oid)
        FROM pg_trigger t WHERE t.oid>=16384 AND t.tgqual IS NOT NULL AND NOT t.tgrelid=ANY(relation_targets)
        UNION ALL
        SELECT pg_describe_object('pg_class'::regclass,i.indexrelid,0),
               pg_get_expr(i.indexprs,i.indrelid) || ';' || coalesce(pg_get_expr(i.indpred,i.indrelid),'')
        FROM pg_index i WHERE i.indexprs IS NOT NULL AND NOT i.indexrelid=ANY(relation_targets)
        UNION ALL
        SELECT pg_describe_object('pg_class'::regclass,i.indexrelid,0),pg_get_expr(i.indpred,i.indrelid)
        FROM pg_index i WHERE i.indpred IS NOT NULL AND NOT i.indexrelid=ANY(relation_targets)
        UNION ALL
        SELECT pg_describe_object('pg_policy'::regclass,p.oid,0),
               coalesce(pg_get_expr(p.polqual,p.polrelid),'') || ';' || coalesce(pg_get_expr(p.polwithcheck,p.polrelid),'')
        FROM pg_policy p WHERE NOT p.polrelid=ANY(relation_targets)
        UNION ALL
        SELECT pg_describe_object('pg_type'::regclass,t.oid,0),pg_get_expr(t.typdefaultbin,0)
        FROM pg_type t WHERE t.oid>=16384 AND t.typtype='d' AND t.typdefaultbin IS NOT NULL
        AND NOT t.oid=ANY(targets)
        UNION ALL
        SELECT pg_describe_object('pg_rewrite'::regclass,r.oid,0),pg_get_ruledef(r.oid)
        FROM pg_rewrite r WHERE r.oid>=16384 AND r.rulename<>'_RETURN'
        AND NOT r.ev_class=ANY(relation_targets)
    LOOP
        BEGIN
            PERFORM pg_temp.dead143_body(offender.definition,0,targets,relation_targets,names,
                ARRAY['standard_conforming_strings'],ARRAY['on'],0,true);
        EXCEPTION WHEN OTHERS THEN
            RAISE EXCEPTION 'target public.items/public.ai_notebook/nine enums: object % refuses: %',offender.identity,SQLERRM;
        END;
    END LOOP;

END
$guard$;

DROP TABLE public.items RESTRICT;
DROP TABLE public.ai_notebook RESTRICT;
DO $sequences$
BEGIN
    IF to_regclass('public.items_id_seq') IS NOT NULL OR to_regclass('public.ai_notebook_id_seq') IS NOT NULL THEN
        RAISE EXCEPTION 'target public.items/public.ai_notebook: owned sequence unexpectedly survived';
    END IF;
END
$sequences$;
DROP TYPE public.agent_type RESTRICT;
DROP TYPE public.log_level_type RESTRICT;
DROP TYPE public.emotional_valence RESTRICT;
DROP TYPE public.entity_type RESTRICT;
DROP TYPE public.item_type RESTRICT;
DROP TYPE public.relationship_type RESTRICT;
DROP TYPE public.threat_domain_type RESTRICT;
DROP TYPE public.threat_lifecycle_type RESTRICT;
DROP TYPE public.trait RESTRICT;
-- Independent second line: PostgreSQL's language validators check every surviving
-- application function/procedure against the post-drop catalog as the migration
-- user, skipping identity settings, without creating or replacing anything.
SET LOCAL check_function_bodies = on;
DO $validate$
DECLARE
    f record;
    setting text;
    parsed_setting text[];
    setting_names text[];
    setting_values text[];
    validator_statement text;
BEGIN
    FOR f IN SELECT p.oid,p.proconfig,l.lanname,
        format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) AS identity
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang
        WHERE p.prokind IN ('f','p','w') AND p.oid>=16384 AND n.nspname !~ '^pg_(temp|toast)'
        AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')
        ORDER BY p.oid
    LOOP
        -- Parse every SET clause and choose the validator under pg_catalog, before
        -- any setting is applied: once a routine's own environment is in force,
        -- only prebuilt, qualified statements run.
        validator_statement := CASE f.lanname WHEN 'sql' THEN 'SELECT pg_catalog.fmgr_sql_validator(' WHEN 'plpgsql' THEN 'SELECT pg_catalog.plpgsql_validator(' END || f.oid::text || '::pg_catalog.oid)';
        IF validator_statement IS NULL THEN
            RAISE EXCEPTION 'target public.items/public.ai_notebook/nine enums: post-drop function/procedure % validation refuses: unsupported application body language %',f.identity,f.lanname;
        END IF;
        setting_names := ARRAY[]::text[];
        setting_values := ARRAY[]::text[];
        FOR setting IN SELECT pg_catalog.unnest(f.proconfig) LOOP
            parsed_setting := pg_temp.dead143_setting(setting);
            IF parsed_setting[1] IN ('role','session_authorization') THEN CONTINUE; END IF;
            setting_names := pg_catalog.array_append(setting_names,parsed_setting[1]);
            setting_values := pg_catalog.array_append(setting_values,parsed_setting[2]);
        END LOOP;
        BEGIN
            PERFORM pg_temp.dead143_resolve(validator_statement,setting_names,setting_values);
        EXCEPTION
            WHEN OTHERS THEN
                RAISE EXCEPTION 'target public.items/public.ai_notebook/nine enums: post-drop function/procedure % validation refuses: %',f.identity,SQLERRM;
        END;
    END LOOP;
END
$validate$;
COMMENT ON FUNCTION public.set_updated_at() IS 'BEFORE UPDATE trigger on characters and places (trg_characters_set_updated, trg_places_set_updated): stamps updated_at with now(), the transaction start time.';
DROP FUNCTION pg_temp.dead143_body(text, oid, oid[], oid[], text[], text[], text[], integer, boolean);
DROP FUNCTION pg_temp.dead143_resolve(text, text[], text[]);
DROP FUNCTION pg_temp.dead143_tokens(text, text, text[], text[]);
DROP FUNCTION pg_temp.dead143_setting(text);
-- Hand the session's startup path back for the rest of the runner's transaction
-- (its own stamp statement names schema_migrations unqualified).
SET LOCAL search_path TO DEFAULT;
