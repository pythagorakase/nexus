# Vector-Helper and Legacy-Column Retirement: 813-S4 and 813-S5

Implementation and proof for migration 154 and the `MEMNON.get_schema_summary`
deletion (issue #813; defaults D1, D2 and D3; Decisions 813-Q1, 813-Q6, 813-D1
and 813-D2). No fleet write, paid call, gateway or UI change was made. The
coordinator owns fleet application.

All commands ran in `/Users/pythagor/nexus/.claude/worktrees/813-S4S5` with the
shared interpreter (`nexus.__file__` resolved under the worktree), with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset and every
PostgreSQL run under `-p tests.dbname_audit` and `nice -n 15`. Scratch files:
`/private/tmp/claude-501/-Users-pythagor-nexus/9dcd8ba0-5aed-4efa-8d64-38cffa54a15d/scratchpad/813-S4S5/`.

## Migration Number Check

`gh pr list --repo pythagorakase/nexus --state open` and
`git ls-tree --name-only -r <branch> migrations/` over every remote branch on
2026-10-26: no branch held a `154_*`; only `claude/1106-incubator-comments` held
a migration above 151 (`152_incubator_column_comments.sql`). Migrations 152
(#1153) and 153 (#1163) landed on main during this work and are merged into the
branch.

## Read-Only Preflight (2026-10-26)

Each database was read with
`PGOPTIONS='-c default_transaction_read_only=on' psql -X -d <db> -At -F' | ' -f preflight.sql`.
Every fleet database was at migration 151.

```sql
\echo == max stamp
SELECT max(version) FROM public.schema_migrations;
\echo == functions md5(prosrc), lang, secdef, config
SELECT p.oid::regprocedure, l.lanname, p.prosecdef, p.proconfig, md5(p.prosrc), obj_description(p.oid,'pg_proc') IS NULL AS uncommented
FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang
WHERE p.proname IN ('hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024') ORDER BY 1::text;
\echo == pg_depend on the six functions
SELECT classid::regclass, objid, deptype FROM pg_depend WHERE refclassid='pg_proc'::regclass AND refobjid IN (SELECT oid FROM pg_proc WHERE proname IN ('hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024'));
\echo == column types / defaults / notnull / comments
SELECT n.nspname||'.'||c.relname||'.'||a.attname, format_type(a.atttypid,a.atttypmod), a.attnotnull, a.atthasdef, a.attgenerated, a.attnum, col_description(c.oid,a.attnum) IS NULL AS uncommented
FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE (n.nspname,c.relname,a.attname) IN (('assets','new_story_creator','seed_starting_location'),('assets','new_story_creator','seed_initial_mystery'),('assets','new_story_creator','seed_potential_obstacles'),('assets','new_story_creator','zone_boundary_description'),('assets','new_story_creator','zone_approximate_area'),('public','entity_tags','clear_on_override'),('public','world_events','narration_chunk_id'),('public','orrery_narration_jobs','provider'),('public','orrery_narration_jobs','model_ref')) AND NOT a.attisdropped ORDER BY 1;
\echo == row counts and non-NULL counts
SELECT 'new_story_creator', count(*), count(seed_starting_location), count(seed_initial_mystery), count(seed_potential_obstacles), count(zone_boundary_description), count(zone_approximate_area) FROM assets.new_story_creator;
SELECT 'entity_tags', count(*), count(clear_on_override) FROM public.entity_tags;
SELECT 'world_events', count(*), count(narration_chunk_id) FROM public.world_events;
SELECT 'orrery_narration_jobs', count(*), count(provider), count(model_ref) FROM public.orrery_narration_jobs;
\echo == pg_depend on the seven columns
SELECT d.classid::regclass, d.objid, d.deptype, ref.relname, a.attname, CASE WHEN d.classid='pg_constraint'::regclass THEN (SELECT conname FROM pg_constraint WHERE oid=d.objid) END
FROM pg_depend d JOIN pg_class ref ON ref.oid=d.refobjid JOIN pg_attribute a ON a.attrelid=d.refobjid AND a.attnum=d.refobjsubid
WHERE d.refclassid='pg_class'::regclass AND (ref.relname,a.attname) IN (('new_story_creator','seed_starting_location'),('new_story_creator','seed_initial_mystery'),('new_story_creator','seed_potential_obstacles'),('new_story_creator','zone_boundary_description'),('new_story_creator','zone_approximate_area'),('entity_tags','clear_on_override'),('world_events','narration_chunk_id'));
\echo == dependents of the fk
SELECT d.classid::regclass, d.deptype, count(*) FROM pg_depend d WHERE d.refclassid='pg_constraint'::regclass AND d.refobjid=(SELECT oid FROM pg_constraint WHERE conname='world_events_narration_chunk_id_fkey') GROUP BY 1,2;
\echo == event triggers
SELECT count(*) FROM pg_event_trigger;
\echo == whole-word hits in non-extension routine bodies (excluding the six)
SELECT p.oid::regprocedure, m.name FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
CROSS JOIN unnest(ARRAY['hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024','seed_starting_location','seed_initial_mystery','seed_potential_obstacles','zone_boundary_description','zone_approximate_area','clear_on_override','narration_chunk_id']) AS m(name)
WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND NOT EXISTS (SELECT 1 FROM pg_depend e WHERE e.classid='pg_proc'::regclass AND e.objid=p.oid AND e.deptype='e')
AND p.proname NOT IN ('hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024')
AND pg_get_functiondef(p.oid) ~* ('\m'||m.name||'\M') AND p.prokind IN ('f','p','w');
\echo == whole-word hits in views/rules/triggers/defaults/constraints/indexes/policies
SELECT 'view '||c.oid::regclass, m.name FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN unnest(ARRAY['hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024','seed_starting_location','seed_initial_mystery','seed_potential_obstacles','zone_boundary_description','zone_approximate_area','clear_on_override','narration_chunk_id']) AS m(name)
 WHERE c.relkind IN ('v','m') AND n.nspname NOT IN ('pg_catalog','information_schema') AND pg_get_viewdef(c.oid) ~* ('\m'||m.name||'\M')
UNION ALL SELECT 'trigger '||t.tgname, m.name FROM pg_trigger t CROSS JOIN unnest(ARRAY['hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024','seed_starting_location','seed_initial_mystery','seed_potential_obstacles','zone_boundary_description','zone_approximate_area','clear_on_override','narration_chunk_id']) AS m(name) WHERE NOT t.tgisinternal AND pg_get_triggerdef(t.oid) ~* ('\m'||m.name||'\M')
UNION ALL SELECT 'default '||ad.adrelid::regclass, m.name FROM pg_attrdef ad CROSS JOIN unnest(ARRAY['hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024','seed_starting_location','seed_initial_mystery','seed_potential_obstacles','zone_boundary_description','zone_approximate_area','clear_on_override','narration_chunk_id']) AS m(name) WHERE pg_get_expr(ad.adbin,ad.adrelid) ~* ('\m'||m.name||'\M')
UNION ALL SELECT 'constraint '||co.conname, m.name FROM pg_constraint co CROSS JOIN unnest(ARRAY['hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024','seed_starting_location','seed_initial_mystery','seed_potential_obstacles','zone_boundary_description','zone_approximate_area','clear_on_override','narration_chunk_id']) AS m(name) WHERE co.contype IN ('c','x') AND pg_get_constraintdef(co.oid) ~* ('\m'||m.name||'\M')
UNION ALL SELECT 'index '||i.indexrelid::regclass, m.name FROM pg_index i CROSS JOIN unnest(ARRAY['hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024','seed_starting_location','seed_initial_mystery','seed_potential_obstacles','zone_boundary_description','zone_approximate_area','clear_on_override','narration_chunk_id']) AS m(name) WHERE (i.indexprs IS NOT NULL OR i.indpred IS NOT NULL) AND pg_get_indexdef(i.indexrelid) ~* ('\m'||m.name||'\M')
UNION ALL SELECT 'rule '||r.rulename, m.name FROM pg_rewrite r CROSS JOIN unnest(ARRAY['hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024','seed_starting_location','seed_initial_mystery','seed_potential_obstacles','zone_boundary_description','zone_approximate_area','clear_on_override','narration_chunk_id']) AS m(name) WHERE r.rulename<>'_RETURN' AND pg_get_ruledef(r.oid) ~* ('\m'||m.name||'\M')
UNION ALL SELECT 'policy '||pol.polname, m.name FROM pg_policy pol CROSS JOIN unnest(ARRAY['hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024','seed_starting_location','seed_initial_mystery','seed_potential_obstacles','zone_boundary_description','zone_approximate_area','clear_on_override','narration_chunk_id']) AS m(name) WHERE coalesce(pg_get_expr(pol.polqual,pol.polrelid),'')||' '||coalesce(pg_get_expr(pol.polwithcheck,pol.polrelid),'') ~* ('\m'||m.name||'\M');
\echo == dynamic SQL / U& in non-extension routines
SELECT p.oid::regprocedure, l.lanname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang
WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND NOT EXISTS (SELECT 1 FROM pg_depend e WHERE e.classid='pg_proc'::regclass AND e.objid=p.oid AND e.deptype='e')
AND p.proname NOT IN ('hybrid_search','migrate_embeddings','pad_vector_384_to_1024','pad_vector_to_1024')
AND (p.prosrc ~* '\mexecute\M' OR p.prosrc ~* '\m(query_to_xml|query_to_xmlschema|query_to_xml_and_xmlschema|dblink|dblink_exec|dblink_open|dblink_send_query)\M' OR p.prosrc ~* 'U&[''"]' OR p.prosrc ~* '\muescape\M');
\echo == non-extension languages / proconfig
SELECT l.lanname, count(*), count(*) FILTER (WHERE p.proconfig IS NOT NULL) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang
WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND NOT EXISTS (SELECT 1 FROM pg_depend e WHERE e.classid='pg_proc'::regclass AND e.objid=p.oid AND e.deptype='e') GROUP BY 1;
```

Output (one block per database):

```text
######## NEXUS_template
== max stamp
151
== functions md5(prosrc), lang, secdef, config
hybrid_search(text,bytea,double precision,double precision,integer,text) | plpgsql | f |  | 36fb85af820eff8182f252abaeac2a33 | t
hybrid_search(text,vector,double precision,double precision,integer,text) | plpgsql | f |  | 9c990bf25cc932df73413510183f01e1 | t
hybrid_search(text,vector,double precision,double precision,integer,text,text[]) | plpgsql | f |  | bf4098a509bf993ced0967bf3518d408 | t
migrate_embeddings() | plpgsql | f |  | fdb7a2ac64ccd83eb2edbf29c5527a85 | t
pad_vector_384_to_1024(vector) | plpgsql | f |  | 6a08f7bb736fdbdd24e9266b2d948281 | t
pad_vector_to_1024(vector) | plpgsql | f |  | cc3741074399976ff5501e875faf0b5b | t
== pg_depend on the six functions
== column types / defaults / notnull / comments
assets.new_story_creator.seed_initial_mystery | text | f | f |  | 38 | t
assets.new_story_creator.seed_potential_obstacles | text[] | f | f |  | 40 | t
assets.new_story_creator.seed_starting_location | text | f | f |  | 35 | t
assets.new_story_creator.zone_approximate_area | text | f | f |  | 48 | t
assets.new_story_creator.zone_boundary_description | text | f | f |  | 47 | t
public.entity_tags.clear_on_override | jsonb | f | f |  | 6 | t
public.orrery_narration_jobs.model_ref | text | f | f |  | 11 | t
public.orrery_narration_jobs.provider | text | f | f |  | 10 | t
public.world_events.narration_chunk_id | bigint | f | f |  | 4 | t
== row counts and non-NULL counts
new_story_creator | 0 | 0 | 0 | 0 | 0 | 0
entity_tags | 0 | 0
world_events | 0 | 0
orrery_narration_jobs | 0 | 0 | 0
== pg_depend on the seven columns
pg_constraint | 511851 | a | world_events | narration_chunk_id | world_events_narration_chunk_id_fkey
== dependents of the fk
pg_trigger | i | 4
== event triggers
0
== whole-word hits in non-extension routine bodies (excluding the six)
== whole-word hits in views/rules/triggers/defaults/constraints/indexes/policies
== dynamic SQL / U& in non-extension routines
== non-extension languages / proconfig
sql | 1 | 0
plpgsql | 40 | 0
######## save_01
== max stamp
151
== functions md5(prosrc), lang, secdef, config
hybrid_search(text,bytea,double precision,double precision,integer,text) | plpgsql | f |  | 36fb85af820eff8182f252abaeac2a33 | t
hybrid_search(text,vector,double precision,double precision,integer,text) | plpgsql | f |  | 9c990bf25cc932df73413510183f01e1 | t
hybrid_search(text,vector,double precision,double precision,integer,text,text[]) | plpgsql | f |  | bf4098a509bf993ced0967bf3518d408 | t
migrate_embeddings() | plpgsql | f |  | fdb7a2ac64ccd83eb2edbf29c5527a85 | t
pad_vector_384_to_1024(vector) | plpgsql | f |  | 6a08f7bb736fdbdd24e9266b2d948281 | t
pad_vector_to_1024(vector) | plpgsql | f |  | cc3741074399976ff5501e875faf0b5b | t
== pg_depend on the six functions
== column types / defaults / notnull / comments
assets.new_story_creator.seed_initial_mystery | text | f | f |  | 38 | t
assets.new_story_creator.seed_potential_obstacles | text[] | f | f |  | 40 | t
assets.new_story_creator.seed_starting_location | text | f | f |  | 35 | t
assets.new_story_creator.zone_approximate_area | text | f | f |  | 48 | t
assets.new_story_creator.zone_boundary_description | text | f | f |  | 47 | t
public.entity_tags.clear_on_override | jsonb | f | f |  | 6 | t
public.orrery_narration_jobs.model_ref | text | f | f |  | 11 | t
public.orrery_narration_jobs.provider | text | f | f |  | 10 | t
public.world_events.narration_chunk_id | bigint | f | f |  | 4 | t
== row counts and non-NULL counts
new_story_creator | 0 | 0 | 0 | 0 | 0 | 0
entity_tags | 0 | 0
world_events | 0 | 0
orrery_narration_jobs | 0 | 0 | 0
== pg_depend on the seven columns
pg_constraint | 554008 | a | world_events | narration_chunk_id | world_events_narration_chunk_id_fkey
== dependents of the fk
pg_trigger | i | 4
== event triggers
0
== whole-word hits in non-extension routine bodies (excluding the six)
== whole-word hits in views/rules/triggers/defaults/constraints/indexes/policies
== dynamic SQL / U& in non-extension routines
== non-extension languages / proconfig
sql | 1 | 0
plpgsql | 40 | 0
######## save_02
== max stamp
151
== functions md5(prosrc), lang, secdef, config
hybrid_search(text,bytea,double precision,double precision,integer,text) | plpgsql | f |  | 36fb85af820eff8182f252abaeac2a33 | t
hybrid_search(text,vector,double precision,double precision,integer,text) | plpgsql | f |  | 9c990bf25cc932df73413510183f01e1 | t
hybrid_search(text,vector,double precision,double precision,integer,text,text[]) | plpgsql | f |  | bf4098a509bf993ced0967bf3518d408 | t
migrate_embeddings() | plpgsql | f |  | fdb7a2ac64ccd83eb2edbf29c5527a85 | t
pad_vector_384_to_1024(vector) | plpgsql | f |  | 6a08f7bb736fdbdd24e9266b2d948281 | t
pad_vector_to_1024(vector) | plpgsql | f |  | cc3741074399976ff5501e875faf0b5b | t
== pg_depend on the six functions
== column types / defaults / notnull / comments
assets.new_story_creator.seed_initial_mystery | text | f | f |  | 33 | t
assets.new_story_creator.seed_potential_obstacles | text[] | f | f |  | 35 | t
assets.new_story_creator.seed_starting_location | text | f | f |  | 30 | t
assets.new_story_creator.zone_approximate_area | text | f | f |  | 43 | t
assets.new_story_creator.zone_boundary_description | text | f | f |  | 42 | t
public.entity_tags.clear_on_override | jsonb | f | f |  | 6 | t
public.orrery_narration_jobs.model_ref | text | f | f |  | 11 | t
public.orrery_narration_jobs.provider | text | f | f |  | 10 | t
public.world_events.narration_chunk_id | bigint | f | f |  | 4 | t
== row counts and non-NULL counts
new_story_creator | 0 | 0 | 0 | 0 | 0 | 0
entity_tags | 0 | 0
world_events | 0 | 0
orrery_narration_jobs | 0 | 0 | 0
== pg_depend on the seven columns
pg_constraint | 967226 | a | world_events | narration_chunk_id | world_events_narration_chunk_id_fkey
== dependents of the fk
pg_trigger | i | 4
== event triggers
0
== whole-word hits in non-extension routine bodies (excluding the six)
== whole-word hits in views/rules/triggers/defaults/constraints/indexes/policies
== dynamic SQL / U& in non-extension routines
== non-extension languages / proconfig
sql | 1 | 0
plpgsql | 40 | 0
######## save_03
== max stamp
151
== functions md5(prosrc), lang, secdef, config
hybrid_search(text,bytea,double precision,double precision,integer,text) | plpgsql | f |  | 36fb85af820eff8182f252abaeac2a33 | t
hybrid_search(text,vector,double precision,double precision,integer,text) | plpgsql | f |  | 9c990bf25cc932df73413510183f01e1 | t
hybrid_search(text,vector,double precision,double precision,integer,text,text[]) | plpgsql | f |  | bf4098a509bf993ced0967bf3518d408 | t
migrate_embeddings() | plpgsql | f |  | fdb7a2ac64ccd83eb2edbf29c5527a85 | t
pad_vector_384_to_1024(vector) | plpgsql | f |  | 6a08f7bb736fdbdd24e9266b2d948281 | t
pad_vector_to_1024(vector) | plpgsql | f |  | cc3741074399976ff5501e875faf0b5b | t
== pg_depend on the six functions
== column types / defaults / notnull / comments
assets.new_story_creator.seed_initial_mystery | text | f | f |  | 33 | t
assets.new_story_creator.seed_potential_obstacles | text[] | f | f |  | 35 | t
assets.new_story_creator.seed_starting_location | text | f | f |  | 30 | t
assets.new_story_creator.zone_approximate_area | text | f | f |  | 43 | t
assets.new_story_creator.zone_boundary_description | text | f | f |  | 42 | t
public.entity_tags.clear_on_override | jsonb | f | f |  | 6 | t
public.orrery_narration_jobs.model_ref | text | f | f |  | 11 | t
public.orrery_narration_jobs.provider | text | f | f |  | 10 | t
public.world_events.narration_chunk_id | bigint | f | f |  | 4 | t
== row counts and non-NULL counts
new_story_creator | 0 | 0 | 0 | 0 | 0 | 0
entity_tags | 35 | 0
world_events | 96 | 0
orrery_narration_jobs | 9 | 9 | 9
== pg_depend on the seven columns
pg_constraint | 1901001 | a | world_events | narration_chunk_id | world_events_narration_chunk_id_fkey
== dependents of the fk
pg_trigger | i | 4
== event triggers
0
== whole-word hits in non-extension routine bodies (excluding the six)
== whole-word hits in views/rules/triggers/defaults/constraints/indexes/policies
== dynamic SQL / U& in non-extension routines
== non-extension languages / proconfig
sql | 1 | 0
plpgsql | 40 | 0
######## save_04
== max stamp
151
== functions md5(prosrc), lang, secdef, config
hybrid_search(text,bytea,double precision,double precision,integer,text) | plpgsql | f |  | 36fb85af820eff8182f252abaeac2a33 | t
hybrid_search(text,vector,double precision,double precision,integer,text) | plpgsql | f |  | 9c990bf25cc932df73413510183f01e1 | t
hybrid_search(text,vector,double precision,double precision,integer,text,text[]) | plpgsql | f |  | bf4098a509bf993ced0967bf3518d408 | t
migrate_embeddings() | plpgsql | f |  | fdb7a2ac64ccd83eb2edbf29c5527a85 | t
pad_vector_384_to_1024(vector) | plpgsql | f |  | 6a08f7bb736fdbdd24e9266b2d948281 | t
pad_vector_to_1024(vector) | plpgsql | f |  | cc3741074399976ff5501e875faf0b5b | t
== pg_depend on the six functions
== column types / defaults / notnull / comments
assets.new_story_creator.seed_initial_mystery | text | f | f |  | 33 | t
assets.new_story_creator.seed_potential_obstacles | text[] | f | f |  | 35 | t
assets.new_story_creator.seed_starting_location | text | f | f |  | 30 | t
assets.new_story_creator.zone_approximate_area | text | f | f |  | 43 | t
assets.new_story_creator.zone_boundary_description | text | f | f |  | 42 | t
public.entity_tags.clear_on_override | jsonb | f | f |  | 6 | t
public.orrery_narration_jobs.model_ref | text | f | f |  | 11 | t
public.orrery_narration_jobs.provider | text | f | f |  | 10 | t
public.world_events.narration_chunk_id | bigint | f | f |  | 4 | t
== row counts and non-NULL counts
new_story_creator | 0 | 0 | 0 | 0 | 0 | 0
entity_tags | 42 | 0
world_events | 133 | 0
orrery_narration_jobs | 0 | 0 | 0
== pg_depend on the seven columns
pg_constraint | 3989785 | a | world_events | narration_chunk_id | world_events_narration_chunk_id_fkey
== dependents of the fk
pg_trigger | i | 4
== event triggers
0
== whole-word hits in non-extension routine bodies (excluding the six)
== whole-word hits in views/rules/triggers/defaults/constraints/indexes/policies
== dynamic SQL / U& in non-extension routines
== non-extension languages / proconfig
sql | 1 | 0
plpgsql | 40 | 0
######## save_05
== max stamp
151
== functions md5(prosrc), lang, secdef, config
hybrid_search(text,bytea,double precision,double precision,integer,text) | plpgsql | f |  | 36fb85af820eff8182f252abaeac2a33 | t
hybrid_search(text,vector,double precision,double precision,integer,text) | plpgsql | f |  | 9c990bf25cc932df73413510183f01e1 | t
hybrid_search(text,vector,double precision,double precision,integer,text,text[]) | plpgsql | f |  | bf4098a509bf993ced0967bf3518d408 | t
migrate_embeddings() | plpgsql | f |  | fdb7a2ac64ccd83eb2edbf29c5527a85 | t
pad_vector_384_to_1024(vector) | plpgsql | f |  | 6a08f7bb736fdbdd24e9266b2d948281 | t
pad_vector_to_1024(vector) | plpgsql | f |  | cc3741074399976ff5501e875faf0b5b | t
== pg_depend on the six functions
== column types / defaults / notnull / comments
assets.new_story_creator.seed_initial_mystery | text | f | f |  | 33 | t
assets.new_story_creator.seed_potential_obstacles | text[] | f | f |  | 35 | t
assets.new_story_creator.seed_starting_location | text | f | f |  | 30 | t
assets.new_story_creator.zone_approximate_area | text | f | f |  | 43 | t
assets.new_story_creator.zone_boundary_description | text | f | f |  | 42 | t
public.entity_tags.clear_on_override | jsonb | f | f |  | 6 | t
public.orrery_narration_jobs.model_ref | text | f | f |  | 11 | t
public.orrery_narration_jobs.provider | text | f | f |  | 10 | t
public.world_events.narration_chunk_id | bigint | f | f |  | 4 | t
== row counts and non-NULL counts
new_story_creator | 0 | 0 | 0 | 0 | 0 | 0
entity_tags | 0 | 0
world_events | 0 | 0
orrery_narration_jobs | 0 | 0 | 0
== pg_depend on the seven columns
pg_constraint | 16239019 | a | world_events | narration_chunk_id | world_events_narration_chunk_id_fkey
== dependents of the fk
pg_trigger | i | 4
== event triggers
0
== whole-word hits in non-extension routine bodies (excluding the six)
== whole-word hits in views/rules/triggers/defaults/constraints/indexes/policies
== dynamic SQL / U& in non-extension routines
== non-extension languages / proconfig
sql | 1 | 0
plpgsql | 40 | 0
```

Summary: the six `md5(prosrc)` values are identical on all six databases and
equal the frozen values; no `pg_depend` row references any of the six; each of
the seven columns is NULL in every row (`entity_tags` 35 rows on `save_03` and
42 on `save_04`; `world_events` 96 and 133); the only `pg_depend` row on the
seven is `world_events_narration_chunk_id_fkey` (deptype `a`) with four internal
triggers; `provider` and `model_ref` are set on all 9 rows of `save_03` and on no
other row; there are no event triggers, no whole-word hits, and no dynamic-SQL
or Unicode-escape form in any non-extension routine (40 `plpgsql` and 1 `sql`
routine per database, none with SET clauses).

## Red Runs

Each plant was a scratch edit, restored from a saved copy before any commit
(`cmp` confirmed the migration and `git diff` confirmed `new_story_cache.py`).

1. Row guard removed (`IF false AND c.non_null <> 0`): the non-NULL test fails
   for all seven columns because the migration applies.

```text
E       AssertionError: assert not True
E       AssertionError: assert not True
E       AssertionError: assert not True
E       AssertionError: assert not True
E       AssertionError: assert not True
E       AssertionError: assert not True
E       AssertionError: assert not True
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_migration_154_dead_strata_pg.py::test_migration_154_refuses_a_non_null_value_atomically[seed_starting_location]
FAILED tests/test_orrery/test_migration_154_dead_strata_pg.py::test_migration_154_refuses_a_non_null_value_atomically[seed_initial_mystery]
FAILED tests/test_orrery/test_migration_154_dead_strata_pg.py::test_migration_154_refuses_a_non_null_value_atomically[seed_potential_obstacles]
FAILED tests/test_orrery/test_migration_154_dead_strata_pg.py::test_migration_154_refuses_a_non_null_value_atomically[zone_boundary_description]
FAILED tests/test_orrery/test_migration_154_dead_strata_pg.py::test_migration_154_refuses_a_non_null_value_atomically[zone_approximate_area]
FAILED tests/test_orrery/test_migration_154_dead_strata_pg.py::test_migration_154_refuses_a_non_null_value_atomically[clear_on_override]
FAILED tests/test_orrery/test_migration_154_dead_strata_pg.py::test_migration_154_refuses_a_non_null_value_atomically[narration_chunk_id]
7 failed, 16 deselected in 22.81s
```

2. Stored-definition name scan removed (`JOIN target_names t ON false`): the
   `perform` case fails (the migration applies) and `execute-literal` loses its
   name. `execute-concat` still refuses on the dynamic-SQL check, `view` and
   `default` refuse on the dependency checks, and `sql-column` refuses through
   the post-drop `fmgr_sql_validator`.

```text
E       AssertionError: assert not True
E           AssertionError: ERROR    nexus.migrate:migrate.py:365   FAILED: 154_drop_vector_helpers_and_legacy_columns - target migration 154 drop set: function public.probe154() holds dynamic SQL (EXECUTE or a SQL-text consumer)
E           assert 'hybrid_search' in 'ERROR    nexus.migrate:migrate.py:365   FAILED: 154_drop_vector_helpers_and_legacy_columns - target migration 154 dro...olds dynamic SQL (EXECUTE or a SQL-text consumer)\nCONTEXT:  PL/pgSQL function inline_code_block line 114 at RAISE\n\n'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_migration_154_dead_strata_pg.py::test_migration_154_refuses_a_planted_caller_atomically[perform]
FAILED tests/test_orrery/test_migration_154_dead_strata_pg.py::test_migration_154_refuses_a_planted_caller_atomically[execute-literal]
2 failed, 4 passed, 17 deselected in 19.76s
```

3. Item 5 reverted (`new_story_cache.py` from `origin/main`) with migration 154
   present:

```text
            guarded_wizard_write,
            with guarded_wizard_write(dbname, before):
            with guarded_wizard_write(dbname, before):
E               psycopg2.errors.UndefinedColumn: column "seed_starting_location" of relation "new_story_creator" does not exist
E               LINE 10:                     seed_starting_location = NULL,
E                                            ^
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_new_story_cache.py::test_weird_level_round_trips_and_only_a_new_wizard_clears_it
1 failed in 2.46s
```

4. `seed_potential_allies = NULL` deleted from `write_seed`:

```text
E                   AssertionError: assert ('Probe 154', ['probe ally']) == ('Probe 154', None)
E                     
E                     At index 1 diff: ['probe ally'] != None
E                     Use -v to get more diff
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_migration_154_dead_strata_pg.py::test_write_seed_runs_after_154
1 failed, 22 deselected in 3.99s
```

## PostgreSQL Proof Set

Run one file per command. `tests/test_orrery/test_migration_dead_strata_pg.py`
ran in full (one hour) after the first merge of `origin/main` (head `5ac3adb7`,
migrations 152 and 153 present). The later merges brought no migration, fixture
or test-helper change; the only file they changed that this test reaches is
`nexus/api/new_story_db_mapper.py`, so its transition and deferred cases ran
again at the final head.

`tests/test_orrery/test_migration_154_dead_strata_pg.py` (final head):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 18 targets: postgres, qa640_813_154_* x17
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
17 passed, 6 skipped in 52.23s
```

`tests/test_orrery/test_migration_dead_strata_pg.py` (full, at `5ac3adb7`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 543 targets: postgres, qa640_813_case_* x542
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
542 passed, 6 skipped in 3695.84s (1:01:35)
```

Same file, `-k "transition or deferred"` (final head):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 5 targets: postgres, qa640_813_case_* x4
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
4 passed, 544 deselected in 31.87s
```

`tests/test_schema_documentation_pg.py tests/test_new_story_cache.py tests/test_api/test_wizard_confirmation_pg.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 29 targets: postgres, qa640_docs_refresh_*, qa640_offline_gate_* x22, qa640_schema_docs_* x3, qa838_genesis_weird_*, qa838_weird_level_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
66 passed, 5 warnings in 68.14s (0:01:08)
```

`tests/test_orrery/test_migrate.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 8 targets: postgres, qa640_grieving_migration_*, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db
1 failed, 76 passed in 15.35s
```

`test_migration_sequence_has_only_known_gaps` failed before migrations 152 and
153 reached main (`{'013', '119', '152', '153'}` against
`frozenset({'013', '119'})`) and passes at the final head. The remaining failure
is `test_canonical_grieving_migration_executes_against_slot_db`; see Open Item
below.

`tests/test_orrery/test_card_identity.py` (the two skips are its
`requires_corpus` cases):

```text
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
9 passed, 2 skipped, 2 warnings in 10.96s
```

`tests/test_connection_lifecycle.py`:

```text
dbname audit: owner names admitted on registered clusters: save_04@local:53563 (psycopg2), save_04@local:53567 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed in 32.58s
```

Corpus fleet run, `NEXUS_RUN_CORPUS=1 ... -k fleet` (counts are
`new_story_creator`, `entity_tags`, `world_events`, then the number of
`orrery_narration_jobs` rows; every `(id, provider, model_ref)` is equal before
and after):

```text
.813-154 fleet save_03 (0, 35, 96) 9
.813-154 fleet save_04 (0, 42, 133) 0
.813-154 fleet save_05 (0, 0, 0) 0
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 7 targets: postgres, qa640_813_154_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
6 passed, 17 deselected in 53.63s
```

The run of the card, lifecycle and fleet files started at a one-minute load of
24.84, just above the cap of 24; every other PostgreSQL run started below it.

## Open Item: Migration 046 Re-Run Test

`tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db`
re-runs the historical Python migration `migrations/046_canonical_grieving_state.py`
against a template clone that the runner has migrated to the head (154
included). Migration 046 copies `entity_tags.clear_on_override`
(`migrations/046_canonical_grieving_state.py:56-66`), so the re-run raises:

```text
E               psycopg2.errors.UndefinedColumn: column "clear_on_override" of relation "entity_tags" does not exist
E               LINE 4:                     clear_on_override, template_id, source_k...
E                                           ^
migrations/046_canonical_grieving_state.py:54: UndefinedColumn
```

The runner applies 046 before 154 on a fresh database, and every fleet
database is stamped 046 (read-only check at push time: `NEXUS_template` and
`save_01` to `save_05` each hold stamps 046, 152 and 153), so no runtime path
re-runs it. Under the common rules a
failure in a file this branch did not change is reported, not fixed: the test
is unchanged and the remedy is the coordinator's call.

## Static Checks

The changed Python files were checked as written on the branch and as they are
on `origin/main` (`git show`/`git archive` into the scratch directory):

- `black --check`: 5 files unchanged.
- `flake8`: 65 diagnostics on the branch, 72 on main, none present only on the
  branch. Deleting `get_schema_summary` left `sqlalchemy.inspect` unused (F401),
  so the import was removed.
- `mypy --explicit-package-bases`: 33 errors in `memnon.py` and
  `new_story_cache.py` on both sides; no diagnostic is present only on the
  branch.
- `scripts/check_migration_comments.py`: `OK: every object created after
  migration 129 has a comment.` A first draft counted rows with `EXECUTE
  format(...)`, which the lint refuses; the counts are now static queries.
- `scripts/check_exception_dispositions.py --baseline-base-ref origin/main`:
  `OK`. Removed keys:
  `nexus/agents/memnon/memnon.py|MEMNON.get_schema_summary|10fa351c...|1`,
  `|630165ee...|1`, `|8b45aeb9...|1` and `|8b45aeb9...|2`.

## Offline Suites

`tests --ignore=tests/test_api --ignore=tests/test_orrery` (at `bd15f8aa`,
before the merge of #1166):

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline
1 failed, 3266 passed, 701 skipped, 8 warnings in 650.24s (0:10:50)
```

The one failure is `test_repository_tree_matches_committed_baseline`. It
compares the baseline with `origin/main`, and #1166 landed on `origin/main`
during the run. After merging #1166 the test passes at `af3b500e` (below).

`tests/test_api tests/test_orrery` (at `af3b500e`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1570 skipped, 7 warnings in 45.88s
```

`tests/test_reachability.py tests/test_doc_front_matter.py tests/test_schema_docs_baseline_routing.py`
(at `af3b500e`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
151 passed, 5 warnings in 16.19s
```

`tests/test_scripts/test_check_exception_dispositions.py` (at `af3b500e`):

```text
receipt isolation: checkout and user receipts untouched
94 passed, 5 warnings in 23.74s
```

## Code Grep

```text
$ git grep -n -e get_schema_summary -e seed_starting_location -e clear_on_override -- . ':!docs/qa' ':!migrations' ':!temp'
docs/dead_retrieval_subtraction.md:170:`config/exception_disposition_baseline.json`. `MEMNON.get_schema_summary` stays
docs/dead_retrieval_subtraction.md:186:- `assets.new_story_creator.seed_starting_location`, `assets.new_story_creator.seed_initial_mystery`, `assets.new_story_creator.seed_potential_obstacles`, `as...
docs/dead_retrieval_subtraction.md:187:- `public.entity_tags.clear_on_override`, created by migration 023. No code reads or writes it; only migration 046 copied it. `entity_pair_tags.clear_on_overr...
docs/dead_retrieval_subtraction.md:195:Migration 154 drops the six functions under Deferred Vector-Helper Function Manifest and seven of the nine columns under Legacy Columns Without Evidence: the ...
docs/dead_retrieval_subtraction.md:197:`MEMNON.get_schema_summary` is deleted with its four baselined handlers. It had no caller, its comment queries ran on a closed connection, and bare `except` h...
docs/decisions/0025-legacy-new-story-seed-columns.md:30:> column:assets.new_story_creator.seed_starting_location: Current cache writers clear this legacy field to NULL; no current reader consumes i...
docs/decisions/0026-entity-tag-clear-on-override.md:27:> column:public.entity_tags.clear_on_override: No current reader or writer establishes how this legacy override should interact with tags.clea...
docs/orrery_design_plan.md:227:  clear_on_override      jsonb,
docs/orrery_design_plan.md:306:  clear_on_override     jsonb,
tests/fixtures/813_pre154_columns.sql:6:ALTER TABLE assets.new_story_creator ADD COLUMN seed_starting_location text;
tests/fixtures/813_pre154_columns.sql:11:ALTER TABLE public.entity_tags ADD COLUMN clear_on_override jsonb;
tests/test_orrery/test_build_venture_async.py:59:            applied_at_world_time timestamptz, clear_on_override jsonb,
tests/test_orrery/test_build_venture_projects.py:220:            applied_at_world_time timestamptz, clear_on_override jsonb,
tests/test_orrery/test_build_venture_replay.py:59:            applied_at_world_time timestamptz, clear_on_override jsonb,
tests/test_orrery/test_migration_154_dead_strata_pg.py:66:    ("assets", "new_story_creator", "seed_starting_location", "text"),
tests/test_orrery/test_migration_154_dead_strata_pg.py:71:    ("public", "entity_tags", "clear_on_override", "jsonb"),
tests/test_orrery/test_migration_154_dead_strata_pg.py:361:    if column == "clear_on_override":
tests/test_orrery/test_migration_154_dead_strata_pg.py:365:            "clear_on_override) SELECT %s, min(id), 'system', '{}'::jsonb FROM tags",
tests/test_orrery/test_migration_154_dead_strata_pg.py:418:        "$probe$SELECT seed_starting_location FROM assets.new_story_creator"
tests/test_orrery/test_migration_154_dead_strata_pg.py:420:        ("probe154", "seed_starting_location"),
tests/test_orrery/test_migration_154_dead_strata_pg.py:459:        "ALTER TABLE public.entity_tags ALTER COLUMN clear_on_override TYPE text",
tests/test_orrery/test_migration_154_dead_strata_pg.py:460:        ("public.entity_tags.clear_on_override", "type is text"),
tests/test_orrery/test_mood_live.py:72:            clear_on_override jsonb, cleared_at timestamptz,
```

## Landing Notes

- Merge only after #1106 (152) and #1069 (153) are on main; both are.
- After merge: `python scripts/migrate.py --all`, then
  `python scripts/migrate.py --slot 1 --write-locked-slot`, then `nexus doctor`.
  Every database must reach 154 with the IDF analyzer current.
- A gateway restart is owed: `nexus/api/new_story_cache.py` and
  `nexus/agents/memnon/memnon.py` are imported product code. `nexus.toml` is
  unchanged.
- No `ui/` change: no rebuild, no state-surface regeneration, and no new UI
  element.
- Owner host: the gitignored
  `/Users/pythagor/nexus/.claude/skills/nexus-database-schema/SKILL.md`
  ("Method 2", `:37-55`, and `:230`, `:264`, `:282`) still describes the deleted
  method.
- After fleet application, post the #813 landing comment listing PRs #866,
  #973, #1098, #1108 and this PR, and records 0025-0029.
