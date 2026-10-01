-- Migration 143: Retire the frozen #813 table/enum closure, never CASCADE.
-- 813-Q1 retains the six vector helpers for #812; Q2 drops all seven orphan
-- enums; Q6 requires catalog identities and conservative body resolution.
-- Manifest: tests/fixtures/813_pre143_manifest.json, frozen from full-data,
-- read-only dumps of NEXUS_template and save_01..05 on 2026-10-01.
-- set_updated_at() catalog body: BEGIN NEW.updated_at = now(); RETURN NEW; END.
-- Surviving triggers: public.characters.trg_characters_set_updated and
-- public.places.trg_places_set_updated. Their definitions and body are untouched.
--
-- Locks: ACCESS EXCLUSIVE on each dropped relation and type; each lock waits
-- at most five seconds, and a timeout rolls back the whole transaction.
--
-- First line of defense: the catalog-aware scanner covers SQL/PLpgSQL relation
-- and type names, casts, declarations, %TYPE/%ROWTYPE, arrays and constant EXECUTE.
-- Ordinary, E, B, X, N, dollar/tagged literals and newline
-- literal concatenation (including -- comments, CR/LF) are single string tokens.
-- Unknown prefixes/malformed literals refuse. PostgreSQL decodes only validated literal grammar, never a
-- computed operand. Unicode-escape literals/identifiers refuse as unclassifiable:
-- raw source containing U&', U&" or UESCAPE (case-insensitive, even in comments
-- and strings) refuses before tokenizing. Other diagnostic strings/comments
-- are not identifier uses.
-- Typed literals, ::, CAST AS and declarations are type contexts. Columns in
-- SELECT/WHERE/HAVING/ON/GROUP BY/ORDER BY/RETURNING, arguments and UPDATE SET
-- require catalog proof on resolved FROM/JOIN/UPDATE/INSERT targets or aliases;
-- NEW/OLD requires proof on EVERY attached relation. Unclassified names refuse.
-- Candidate names include the catalog's actual generated arrays and row types.
-- regclass/regtype/regproc/regprocedure/regoper/regoperator/regconfig/
-- regdictionary/regnamespace/regrole/regcollation (bare or pg_catalog-qualified)
-- support typed literals, CAST AS, :: and function-style casts, plus to_reg*.
-- Literal operands resolve through catalog input functions; closure references
-- refuse. Every nonliteral operand or unresolved catalog literal refuses.
-- Constant EXECUTE supports literal concatenation and pg_catalog.format; fold
-- then scan recursively. Variable/parameter expressions, non-SQL application
-- languages, ambiguous paths, runtime search_path/role mutation, different
-- SECURITY DEFINER owners refuse.
-- Resolution uses each function's effective search_path, never a name allowlist.
-- Second line of defense: after restrictive drops, before comments/stamping,
-- run PostgreSQL's own language validators (fmgr_sql_validator, plpgsql_validator)
-- over EVERY surviving application function/procedure with check_function_bodies=on
-- under every routine SET clause. The environment is applied and unwound
-- through PostgreSQL's GUC stack, as CREATE FUNCTION does: each validator runs
-- in its own subtransaction, aborted by a dedicated success sentinel. Native
-- unwind restores settings, including role/session_authorization, without
-- fresh permission-checked assignments under a temporarily changed role.
-- check_function_bodies is re-asserted on after the routine's own SET clauses,
-- so a routine declared with SET check_function_bodies=off is still validated
-- (one place this guard is stricter than CREATE FUNCTION).
-- That is the check CREATE FUNCTION performs, against the
-- post-drop catalog, with no DDL: nothing is re-created, so OIDs, ownership, ACLs
-- and comments are untouched and a named failure rolls the transaction back.
-- Residual risk: polymorphic SQL bodies (any polymorphic argument or return type)
-- receive only a syntax check from fmgr_sql_validator, shared by re-creation.
-- Other SQL bodies are parsed/analyzed; PLpgSQL syntax/declared types are validated.
-- Neither defense completely covers late-bound PLpgSQL expression-level references.
-- SET values split at the first equals sign in one helper shared with the scanner.
-- set_config uses GUC_ACTION_LOCAL; subtransaction abort restores natively,
-- while CREATE FUNCTION uses GUC_ACTION_SAVE at a GUC nesting level.
-- All catalog/scanner guards precede DROP. Post-drop validation remains within
-- the runner's same atomic transaction. No persistent helper/debt remains.

SET LOCAL lock_timeout = '5s';

CREATE FUNCTION pg_temp.dead143_tokens(body text) RETURNS jsonb
LANGUAGE plpgsql AS $lexer$
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
        IF ch ~ '\s' THEN i := i + 1; CONTINUE; END IF;
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
        prefix := substring(substr(body,i) FROM '^([a-zA-Z]+)''');
        IF ch = '''' OR prefix IS NOT NULL THEN
            IF prefix IS NOT NULL AND lower(prefix) NOT IN ('e','b','x','n') THEN
                RAISE EXCEPTION 'unresolved string literal prefix %',prefix;
            END IF;
            escaped := lower(coalesce(prefix,''))='e';
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
                EXECUTE 'SELECT ('||raw||')::text' INTO value;
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
            kind := 'id';
        ELSIF ch = '$' AND substr(body,i) ~ '^\$[a-zA-Z_0-9]*\$' THEN
            delimiter := substring(substr(body,i) FROM '^\$[a-zA-Z_0-9]*\$');
            i := i + length(delimiter);
            depth := strpos(substr(body,i),delimiter);
            IF depth = 0 THEN RAISE EXCEPTION 'unclosed dollar literal'; END IF;
            value := substr(body,i,depth-1); i := i + depth-1 + length(delimiter);
            kind := 'string';
        ELSIF ch ~ '[a-zA-Z_]' THEN
            WHILE i <= length(body) AND substr(body,i,1) ~ '[a-zA-Z_0-9$]' LOOP i := i + 1; END LOOP;
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
COMMENT ON FUNCTION pg_temp.dead143_tokens(text) IS 'Migration 143 transaction-local SQL lexer: distinguish identifiers from comments and diagnostic literals; removed before stamping.';

CREATE FUNCTION pg_temp.dead143_setting(setting text) RETURNS text[]
LANGUAGE sql IMMUTABLE AS $setting$
    SELECT ARRAY[substr(setting,1,strpos(setting,'=')-1),
                 substr(setting,strpos(setting,'=')+1)]
$setting$;
COMMENT ON FUNCTION pg_temp.dead143_setting(text) IS 'Migration 143 transaction-local proconfig parser: name before first equals, complete value after it, shared by scanner and validator; removed before stamping.';

CREATE FUNCTION pg_temp.dead143_body(body text, function_oid oid, targets oid[], relation_targets oid[], names text[], nesting integer DEFAULT 0) RETURNS void
LANGUAGE plpgsql AS $scanner$
DECLARE
    tokens jsonb := pg_temp.dead143_tokens(body);
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
BEGIN
    IF nesting > 8 THEN RAISE EXCEPTION 'unresolved nested dynamic SQL'; END IF;
    WHILE i < count_tokens LOOP
        name := tokens->i->>'v'; kind := tokens->i->>'k';
        IF kind='id' AND name='set_config' AND tokens->(i+1)->>'v'='('
            AND (tokens->(i+2)->>'k' IS DISTINCT FROM 'string'
                OR tokens->(i+3)->>'v' IS DISTINCT FROM ','
                OR lower(tokens->(i+2)->>'v') IN ('search_path','role','session_authorization')) THEN
            RAISE EXCEPTION 'target public.items/public.ai_notebook or enum: unresolved runtime search_path mutation';
        END IF;
        IF kind='id' AND name IN ('set','reset') THEN
            j := i+1;
            IF tokens->j->>'v' IN ('local','session') THEN j := j+1; END IF;
            IF (lower(tokens->j->>'v') IN ('search_path','role','session_authorization')
                OR (name='reset' AND lower(tokens->j->>'v')='all')) AND (
                (SELECT prosqlbody IS NULL FROM pg_proc WHERE oid=function_oid)
                OR EXISTS (SELECT 1 FROM jsonb_array_elements(tokens) WITH ORDINALITY t(token,position)
                    WHERE position<=i AND token->>'k'='id' AND token->>'v'='begin')
            ) THEN
                RAISE EXCEPTION 'target public.items/public.ai_notebook or enum: unresolved runtime search_path mutation';
            END IF;
        END IF;
        IF kind = 'id' AND name = 'execute' THEN
            expression := ''; j := i + 1;
            WHILE j < count_tokens AND tokens->j->>'v' NOT IN (';', 'into', 'using') LOOP
                IF tokens->j->>'k' = 'string' OR tokens->j->>'v' IN ('(',')',',','||') THEN
                    expression := expression || ' ' || (tokens->j->>'raw');
                ELSIF tokens->j->>'v' = 'pg_catalog' AND tokens->(j+1)->>'v' = '.' AND tokens->(j+2)->>'v' = 'format' THEN
                    j := j + 1; -- the next token is the validated format call
                ELSIF tokens->j->>'k' = 'id' AND tokens->j->>'v' = 'format'
                    AND tokens->(j+1)->>'v' = '(' THEN
                    expression := expression || ' pg_catalog.format';
                ELSE
                    RAISE EXCEPTION 'target public.items/public.ai_notebook or enum: unresolved dynamic EXECUTE expression';
                END IF;
                j := j + 1;
            END LOOP;
            IF expression = '' THEN RAISE EXCEPTION 'unresolved empty EXECUTE'; END IF;
            EXECUTE 'SELECT (' || expression || ')::text' INTO folded;
            IF folded IS NULL THEN RAISE EXCEPTION 'unresolved NULL EXECUTE'; END IF;
            PERFORM pg_temp.dead143_body(folded,function_oid,targets,relation_targets,names,nesting+1);
            i := j; CONTINUE;
        END IF;
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
                    IF tokens->j->>'v'='(' THEN depth := depth+1;
                    ELSIF tokens->j->>'v'=')' THEN
                        IF depth=0 THEN EXIT; END IF;
                        depth := depth-1;
                    ELSIF depth=0 AND tokens->j->>'v'=',' THEN EXIT; END IF;
                    j := j+1;
                END LOOP;
                expression_right := j-1;
            ELSE catalog_kind := NULL; END IF;
        ELSIF name='::' THEN
            catalog_at := i+1;
            IF tokens->catalog_at->>'v'='pg_catalog' AND tokens->(catalog_at+1)->>'v'='.' THEN
                catalog_at := catalog_at+2;
            END IF;
            catalog_kind := tokens->catalog_at->>'v';
            expression_right := i-1; expression_left := expression_right;
            IF tokens->expression_right->>'v'=')' THEN
                depth := 1; expression_left := expression_right-1;
                WHILE expression_left>=0 AND depth>0 LOOP
                    IF tokens->expression_left->>'v'=')' THEN depth := depth+1;
                    ELSIF tokens->expression_left->>'v'='(' THEN depth := depth-1; END IF;
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
                IF tokens->j->>'v'='(' THEN depth := depth+1;
                ELSIF tokens->j->>'v'=')' THEN
                    IF depth=0 THEN EXIT; END IF;
                    depth := depth-1;
                ELSIF depth=0 AND tokens->j->>'v'='as' THEN
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
            WHILE expression_left<expression_right AND tokens->expression_left->>'v'='('
                AND tokens->expression_right->>'v'=')' LOOP
                depth := 0; j := expression_left;
                WHILE j<expression_right LOOP
                    IF tokens->j->>'v'='(' THEN depth := depth+1;
                    ELSIF tokens->j->>'v'=')' THEN depth := depth-1; END IF;
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
                EXECUTE 'SELECT '||quote_literal(folded)||'::pg_catalog.'||
                    quote_ident(CASE WHEN catalog_kind='regtypeoid' THEN 'regtype' ELSE catalog_kind END)||'::oid'
                    INTO relation_oid;
            EXCEPTION WHEN OTHERS THEN
                RAISE EXCEPTION 'unresolved catalog literal % for %: %',folded,catalog_kind,SQLERRM;
            END;
            IF catalog_kind IN ('regtype','regtypeoid') THEN type_oid := relation_oid; END IF;
            IF (catalog_kind='regclass' AND relation_oid=ANY(relation_targets)) OR type_oid=ANY(targets) THEN
                RAISE EXCEPTION 'target %: catalog body reference',folded;
            END IF;
        END IF;
        IF kind = 'id' AND name = ANY(names) THEN
            qualified := quote_ident(name);
            IF i >= 2 AND tokens->(i-1)->>'v' = '.' AND tokens->(i-2)->>'k' = 'id' THEN
                qualified := quote_ident(tokens->(i-2)->>'v') || '.' || qualified;
            END IF;
            type_context := tokens->(i+1)->>'k'='string' OR tokens->(i+1)->>'v'='('
                OR (i>0 AND tokens->(i-1)->>'v' IN ('::','as'));
            IF i>=3 AND tokens->(i-1)->>'v'='.' THEN
                type_context := coalesce(type_context,false) OR tokens->(i-3)->>'v' IN ('::','as');
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
                WHILE left_edge>0 AND tokens->(left_edge-1)->>'v'<>';' LOOP left_edge := left_edge-1; END LOOP;
                WHILE right_edge<count_tokens-1 AND tokens->(right_edge+1)->>'v'<>';' LOOP right_edge := right_edge+1; END LOOP;
                qualifier := NULL;
                IF i>=2 AND tokens->(i-1)->>'v'='.' THEN qualifier := tokens->(i-2)->>'v'; END IF;
                found_column := false;
                -- Classify expression clauses, rather than only SELECT's
                -- first column. Declarations/types never borrow column proof.
                clause := NULL;
                FOR j IN left_edge..i LOOP
                    IF tokens->j->>'k'='id' AND tokens->j->>'v' IN
                        ('select','where','having','on','group','order','returning','set',
                         'from','join','update','into','declare','begin','returns') THEN
                        clause := tokens->j->>'v';
                    END IF;
                END LOOP;
                column_position := clause IN ('select','where','having','on','group','order','returning','set');
                IF clause IN ('declare','returns') AND NOT (
                    tokens->(i+1)->>'v'='%' AND tokens->(i+2)->>'v'='type'
                ) THEN type_context := true; END IF;
                IF coalesce(column_position,false) AND NOT coalesce(type_context,false) THEN
                    FOR j IN left_edge..right_edge LOOP
                        IF tokens->j->>'v' IN ('from','join','update','into') AND tokens->(j+1)->>'k'='id' THEN
                            relation_at := j+1;
                            relation_name := quote_ident(tokens->relation_at->>'v');
                            IF tokens->(relation_at+1)->>'v'='.' AND tokens->(relation_at+2)->>'k'='id' THEN
                                relation_at := relation_at+2;
                                relation_name := relation_name||'.'||quote_ident(tokens->relation_at->>'v');
                            END IF;
                            -- A relation name itself is never a column exemption.
                            IF i BETWEEN j+1 AND relation_at THEN CONTINUE; END IF;
                            relation_oid := to_regclass(relation_name);
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
                type_oid := to_regtype(qualified); relation_oid := to_regclass(qualified);
                IF type_oid = ANY(targets) OR relation_oid = ANY(relation_targets) THEN
                    RAISE EXCEPTION 'target %: hidden body identifier reference',qualified;
                END IF;
                -- A qualified column must resolve to a real, unrelated column.
                IF i >= 2 AND tokens->(i-1)->>'v' = '.' AND NOT coalesce(type_context,false) THEN
                    relation_name := quote_ident(tokens->(i-2)->>'v');
                    IF i>=4 AND tokens->(i-3)->>'v'='.' AND tokens->(i-4)->>'k'='id' THEN
                        relation_name := quote_ident(tokens->(i-4)->>'v')||'.'||relation_name;
                    END IF;
                    relation_oid := to_regclass(relation_name);
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
COMMENT ON FUNCTION pg_temp.dead143_body(text, oid, oid[], oid[], text[], integer) IS 'Migration 143 transaction-local catalog-aware body guard, including constant dynamic SQL folding; removed before stamping.';

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
    saved_path text := current_setting('search_path');
    effective_path text;
    key text;
    edge_key text;
BEGIN
    PERFORM set_config('search_path','pg_catalog',true);
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
        UNION SELECT relname FROM pg_class WHERE oid IN (to_regclass('public.items_id_seq'),to_regclass('public.ai_notebook_id_seq'))
    ) candidates;

    FOR f IN SELECT p.*,l.lanname,format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) AS identity
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang
        WHERE p.prokind IN ('f','p') AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_(temp|toast)'
        AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')
    LOOP
        BEGIN
            IF f.prosecdef AND f.proowner<>current_user::regrole::oid THEN
                RAISE EXCEPTION 'unresolved SECURITY DEFINER owner/search_path context';
            END IF;
            IF f.lanname NOT IN ('sql','plpgsql') THEN RAISE EXCEPTION 'unsupported application body language %',f.lanname; END IF;
            SELECT (pg_temp.dead143_setting(setting))[2] INTO effective_path FROM unnest(f.proconfig) setting WHERE setting LIKE 'search_path=%';
            PERFORM set_config('search_path',coalesce(effective_path,saved_path),true);
            PERFORM pg_temp.dead143_body(CASE WHEN f.prosqlbody IS NULL THEN f.prosrc ELSE pg_get_functiondef(f.oid) END,f.oid,targets,tables || ARRAY[to_regclass('public.items_id_seq')::oid,to_regclass('public.ai_notebook_id_seq')::oid],names);
        EXCEPTION WHEN OTHERS THEN
            RAISE EXCEPTION 'target public.items/public.ai_notebook/nine enums: function/procedure % refuses: %',f.identity,SQLERRM;
        END;
    END LOOP;
    PERFORM set_config('search_path',saved_path,true);
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
-- application function/procedure against the post-drop catalog, exactly as
-- CREATE FUNCTION would, without creating or replacing anything.
SET LOCAL check_function_bodies = on;
DO $validate$
DECLARE
    f record;
    setting text;
    parsed_setting text[];
BEGIN
    FOR f IN SELECT p.oid,p.proconfig,l.lanname,
        format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) AS identity
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang
        WHERE p.prokind IN ('f','p') AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_(temp|toast)'
        AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')
        ORDER BY p.oid
    LOOP
        BEGIN
            FOR setting IN SELECT unnest(f.proconfig) LOOP
                parsed_setting := pg_temp.dead143_setting(setting);
                PERFORM set_config(parsed_setting[1],parsed_setting[2],true);
            END LOOP;
            -- A routine's own SET check_function_bodies=off would switch the
            -- validator off; the second line validates every routine regardless.
            PERFORM set_config('check_function_bodies','on',true);
            CASE f.lanname
                WHEN 'sql' THEN PERFORM pg_catalog.fmgr_sql_validator(f.oid);
                WHEN 'plpgsql' THEN PERFORM pg_catalog.plpgsql_validator(f.oid);
                ELSE RAISE EXCEPTION 'unsupported application body language %',f.lanname;
            END CASE;
            -- Abort even on success: PostgreSQL unwinds the entire GUC stack.
            RAISE SQLSTATE 'D1430' USING MESSAGE='dead143 validation complete';
        EXCEPTION
            WHEN SQLSTATE 'D1430' THEN
                IF SQLERRM <> 'dead143 validation complete' THEN
                    RAISE EXCEPTION 'target public.items/public.ai_notebook/nine enums: post-drop function/procedure % validation refuses: %',f.identity,SQLERRM;
                END IF;
            WHEN OTHERS THEN
                RAISE EXCEPTION 'target public.items/public.ai_notebook/nine enums: post-drop function/procedure % validation refuses: %',f.identity,SQLERRM;
        END;
    END LOOP;
END
$validate$;
COMMENT ON FUNCTION public.set_updated_at() IS 'BEFORE UPDATE trigger on characters and places (trg_characters_set_updated, trg_places_set_updated): stamps updated_at with now(), the transaction start time.';
DROP FUNCTION pg_temp.dead143_body(text, oid, oid[], oid[], text[], integer);
DROP FUNCTION pg_temp.dead143_tokens(text);
DROP FUNCTION pg_temp.dead143_setting(text);
