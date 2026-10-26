# Verification: Refuse the Chunk Slug Bound Loudly (1069-S1)

Issue #1069; Decisions 1069-D1, D3, D4 and D7 (coordinator comment
"Decisions Recorded From the 2026-10-26 Coordinator Review"). Branch
`claude/1069-slug-bound`, cut from `origin/main` at `c7ae2988`; `origin/main`
had not moved when this file was written, so the merge base is `c7ae2988`.
Migration 153 (`migrations/153_chunk_slug_bound_refusal.sql`); 152 is held by
#1106 (PR #1153, open).

## Cited Lines at `c7ae2988`

- `nexus/api/commit_handler_sync.py:95-142` `insert_chunk_metadata_sync`;
  `slug: str` at `:105`, in `metadata_values` at `:119`, in both INSERT
  column lists at `:127` and `:137`.
- `:352` `with conn:  # This creates a transaction context`.
- `:460` `db_meta["scene"] = parent_meta["scene"] + 1` (no reset).
- `:573-577` the Python slug `f"S{season:02d}E{episode:02d}_{scene:03d}"`,
  passed at `:588`, logged at `:592`.
- `:892-895` `except Exception` logs, `conn.rollback()`, re-raises.
- `tests/pg_fixtures.py:843` `seed_committed_chunk`; slug column at `:886`,
  formatted value at `:897`. `:2877-2891` `_insert_experience_chunk` sets
  `scene = chunk_id` and slug `qa677_{chunk_id}`.
- `migrations/135_schema_docs_backfill.sql:200-201` is the only migration
  text that names `set_chunk_slug()` (its comment).
- `docs/turn_flow_sequence.md:270-271` (old step 5), sources at `:22`,
  `verified_commit` at `:57`; `AGENTS.md` sources `:27`, `:29`,
  `verified_commit` at `:38`.

## Read-Only Fleet Query (2026-10-26)

```
for d in NEXUS_template save_01 save_02 save_03 save_04 save_05; do
  PGOPTIONS='-c default_transaction_read_only=on' psql -d $d -Atc "SELECT '$d',
    md5(pg_get_functiondef('public.set_chunk_slug'::regproc)),
    (SELECT max(version) FROM schema_migrations), count(*), max(season),
    max(episode), max(scene), count(*) FILTER (WHERE slug IS NULL),
    count(*) FILTER (WHERE slug LIKE '%#%'),
    count(*) FILTER (WHERE slug IS DISTINCT FROM 'S' || to_char(season,'FM00')
      || 'E' || to_char(episode,'FM00') || '_' || to_char(scene,'FM000'))
    FROM chunk_metadata"; done
```

```
NEXUS_template|93b37a039193571fae65c73e8d3f0f72|151|0||||0|0|0
save_01|93b37a039193571fae65c73e8d3f0f72|151|1425|5|17|80|0|0|0
save_02|93b37a039193571fae65c73e8d3f0f72|151|1425|5|17|80|0|0|0
save_03|93b37a039193571fae65c73e8d3f0f72|151|40|1|2|39|0|0|0
save_04|93b37a039193571fae65c73e8d3f0f72|151|46|1|2|45|0|0|0
save_05|93b37a039193571fae65c73e8d3f0f72|151|0||||0|0|0
```

Today's body (`NEXUS_template`):

```
CREATE OR REPLACE FUNCTION public.set_chunk_slug()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
  NEW.slug :=
    'S' || TO_CHAR(NEW.season, 'FM00') ||
    'E' || TO_CHAR(NEW.episode, 'FM00') ||
    '_' || TO_CHAR(NEW.scene, 'FM000');
  RETURN NEW;
END;
$function$
```

`SELECT to_char(1000,'FM000'), to_char(100,'FM00'), to_char(-1,'FM000')`
on `NEXUS_template`: `###|##|-001`. `\d chunk_metadata`: `slug character
varying(10)`, `"unique_slug" UNIQUE CONSTRAINT, btree (slug)`,
`trg_chunk_metadata_slug BEFORE INSERT OR UPDATE ON chunk_metadata FOR EACH
ROW EXECUTE FUNCTION set_chunk_slug()`; `season`, `episode`, `scene` are
nullable integers.

## Fixture Grep (Item 5)

The grep first recorded here was
`grep -rnE "scene\s*=\s*(chunk_id|i|tick|index)|VALUES \(%s, 1, 1, %s" tests`.
It cannot match a helper that passes the chunk id positionally after a
`season` parameter (`tests/test_lore/test_pass2_baseline_pg.py` `_seed_parent`)
or a helper that takes the next free scene with `max(scene) + 1`. Its raw output
on the branch head (`1d04c8ce`):

```
tests/test_chunk_entity_references_pg.py:144:        scene = int(cur.fetchone()[0])
tests/test_jobs_cli_pg.py:75:                            ) VALUES (%s, 1, 1, %s, 'primary')
tests/test_orrery/test_experience_enqueue_gin_pg.py:101:        ) VALUES (%s, 1, 1, %s, 'primary', %s, %s)
Binary file tests/test_orrery/__pycache__/test_experience_enqueue_gin_pg.cpython-311-pytest-8.3.5.pyc matches
tests/test_orrery/test_world_hour_horizon_pg.py:86:                scene=i + 1,
tests/test_orrery/test_world_event_time_pg.py:118:                dbname, raw_text="Quiet passage.", scene=tick + 1
tests/test_orrery/test_world_event_time_pg.py:398:        scene=tick + 1,
tests/test_orrery/test_world_event_time_pg.py:444:        dbname, raw_text="Unresolved clock.", scene=tick + 1
tests/test_embedding_table_ownership_pg.py:76:        scene = int(cur.fetchone()[0])
Binary file tests/__pycache__/test_jobs_cli_pg.cpython-311-pytest-8.3.5.pyc matches
tests/pg_fixtures.py:1241:        scene = int(cur.fetchone()[0])
tests/test_api/test_reader_chunk_range_pg.py:74:                    scene=index + 1,
Binary file tests/test_api/__pycache__/test_correspondence_pg.cpython-311-pytest-8.3.5.pyc matches
tests/test_api/test_reader_feed_pg.py:222:                        scene=index + 1,
tests/test_api/test_correspondence_pg.py:74:            VALUES (%s, 1, 1, %s, 'primary', %s)
```

The widened grep, run on the base commit so that it shows the pre-change
shape of every converted site:

```
$ git grep -nE "scene\s*=\s*(chunk_id|i|tick|index)|VALUES \(%s, (%s|1), 1, %s|\(chunk_id, [A-Za-z_0-9]+, chunk_id|chunk_id, 1, chunk_id|max\(scene\)" c7ae2988 -- tests
c7ae2988:tests/pg_fixtures.py:1229:            "SELECT COALESCE(max(scene), 0) + 1 FROM chunk_metadata "
c7ae2988:tests/pg_fixtures.py:2890:        "VALUES (%s, 1, 1, %s, 'primary', %s)",
c7ae2988:tests/test_api/test_correspondence_pg.py:74:            VALUES (%s, 1, 1, %s, 'primary', %s)
c7ae2988:tests/test_api/test_reader_chunk_range_pg.py:74:                    scene=index + 1,
c7ae2988:tests/test_api/test_reader_feed_pg.py:89:                "SELECT count(*), count(DISTINCT slug), min(scene), max(scene) "
c7ae2988:tests/test_api/test_reader_feed_pg.py:221:                        scene=index + 1,
c7ae2988:tests/test_chunk_entity_references_pg.py:141:            "SELECT COALESCE(max(scene), 0) + 1 FROM chunk_metadata "
c7ae2988:tests/test_embedding_table_ownership_pg.py:75:        cur.execute("SELECT coalesce(max(scene), 0) + 1 FROM chunk_metadata")
c7ae2988:tests/test_idf_dictionary_pg.py:52:        VALUES (%s, 1, 1, %s, 'primary', interval '0 seconds', now())
c7ae2988:tests/test_jobs_cli_pg.py:75:                            ) VALUES (%s, 1, 1, %s, 'primary')
c7ae2988:tests/test_lore/test_pass2_baseline_pg.py:239:            ) VALUES (%s, %s, 1, %s, 'primary', %s)
c7ae2988:tests/test_lore/test_pass2_baseline_pg.py:241:            (chunk_id, season, chunk_id, f"pass2-{chunk_id}"),
c7ae2988:tests/test_orrery/test_acquisition_scan_pg.py:130:        ) VALUES (%s, 1, 1, %s, %s::world_layer_type, %s)
c7ae2988:tests/test_orrery/test_character_experiences_pg.py:170:        "VALUES (%s, 1, 1, %s, 'primary', %s)",
c7ae2988:tests/test_orrery/test_experience_enqueue_gin_pg.py:101:        ) VALUES (%s, 1, 1, %s, 'primary', %s, %s)
c7ae2988:tests/test_orrery/test_world_event_time_pg.py:118:                dbname, raw_text="Quiet passage.", scene=tick + 1
c7ae2988:tests/test_orrery/test_world_event_time_pg.py:398:        scene=tick + 1,
c7ae2988:tests/test_orrery/test_world_event_time_pg.py:444:        dbname, raw_text="Unresolved clock.", scene=tick + 1
c7ae2988:tests/test_orrery/test_world_hour_horizon_pg.py:86:                scene=i + 1,
```

Changed to `slug_bounded_episode_scene(chunk_id)` (episode and scene from the
helper in place of the literal `1` and the chunk id):

- `tests/pg_fixtures.py` `_insert_experience_chunk` (slug column dropped).
- `tests/test_orrery/test_character_experiences_pg.py` `_insert_chunk`
  (slug column dropped).
- `tests/test_idf_dictionary_pg.py` `_metadata`.
- `tests/test_orrery/test_acquisition_scan_pg.py` `_insert_chunk`.
- `tests/test_lore/test_pass2_baseline_pg.py` `_seed_parent` (slug column and
  its `pass2-{chunk_id}` placeholder dropped; fixer commit `1d04c8ce`). It has
  the same shape as the four helpers Decision 1069-D7 names, so it takes the
  same conversion; its largest caller seeds twelve parents on one
  function-scoped clone, so no result changes today.

In range on a fresh clone, unchanged:

- `tests/test_api/test_reader_feed_pg.py:79-85` (1,200 chunks,
  `scene = 1 + i % 200` over three episodes and two seasons), `:89` (a
  `max(scene)` read, not a seed) and `:222` (six chunks, `scene = index + 1`).
- `tests/test_orrery/test_acquisition_scan_pg.py:484-495` (300 rows, 100 per
  episode).
- `tests/test_orrery/test_world_event_time_pg.py:117-119`, `:398`, `:444`
  (`scene = tick + 1`, loop capped at 100).
- `tests/test_orrery/test_world_hour_horizon_pg.py:82-90` (40).
- `tests/test_api/test_reader_chunk_range_pg.py:70-76` (7).
- `tests/test_jobs_cli_pg.py:67-77` (scenes 1 and 2),
  `tests/test_orrery/test_experience_enqueue_gin_pg.py:90-110` (callers pass
  scene 1-3), `tests/test_api/test_correspondence_pg.py:56-77`
  (`scene = index`, counts 1 and 10).
- Three helpers that take the next free scene of S01E01 with
  `max(scene) + 1`:
  - `tests/test_chunk_entity_references_pg.py:137-145` `_chunk`: at most ten
    calls on the module clone (`:241`, `:335-336` parametrized over three
    kinds, `:370-371`, `:425`) and one call on each of the two function clones
    (`:503`, `:551`).
  - `tests/test_embedding_table_ownership_pg.py:70-79` `seed_source`: one call
    per test on a function-scoped clone (`ownership_db`).
  - `tests/pg_fixtures.py:1211-1244` `seed_character_pair` (the `max(scene)`
    read at `:1238`): at most three calls per clone
    (`tests/test_pg_character_pair_seed.py:87`, `:94`, `:116`, the third
    refused by the clock check); every other caller makes one or two.

## The Refusal as Raised

Run outside pytest (so no session guard line applies), on a disposable
`qa640_1069_msg_*` clone that `disposable_slot_database` creates and drops, at
fixer commit `1d04c8ce`. The probe calls `seed_committed_chunk` with
`(1, 1, 1000)`, `(100, 1, 1)` and `(1, -1, 1)` and prints each exception's
class, `pgcode`, `diag.column_name` and message:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY <scratch>/1069-S1/show_refusal.py > <scratch>/1069-S1/fix/refusal.log 2>&1
```

The first 2,269 lines of the log are the clone's `psql` restore output; the
rest, verbatim:

```
psycopg2.errors.NumericValueOutOfRange 22003 scene
Chunk slug bound exceeded: chunk_id 1 has scene 1000, outside 0..999 (season 1, episode 1, scene 1000)
CONTEXT:  PL/pgSQL function set_chunk_slug() line 20 at RAISE
---
psycopg2.errors.NumericValueOutOfRange 22003 season
Chunk slug bound exceeded: chunk_id 2 has season 100, outside 0..99 (season 100, episode 1, scene 1)
CONTEXT:  PL/pgSQL function set_chunk_slug() line 4 at RAISE
---
psycopg2.errors.NumericValueOutOfRange 22003 episode
Chunk slug bound exceeded: chunk_id 3 has episode -1, outside 0..99 (season 1, episode -1, scene 1)
CONTEXT:  PL/pgSQL function set_chunk_slug() line 12 at RAISE
---
```

## Red Runs

Both plants ran at fixer commit `1d04c8ce` and were reverted before any
commit; `git status --short` was empty afterwards.

(1) Plant: the migration file moved out of `migrations/`. Every test except
`test_in_range_slugs_keep_the_legacy_format` fails.

```
$ mv migrations/153_chunk_slug_bound_refusal.sql <scratch>/1069-S1/fix/
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_chunk_slug_bound_pg.py > <scratch>/1069-S1/fix/red1.log 2>&1
$ mv <scratch>/1069-S1/fix/153_chunk_slug_bound_refusal.sql migrations/
```

Tail, verbatim from the guard line to the end:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 3 targets: postgres, qa640_1069_commit_*, qa640_1069_slug_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_out_of_range_part_is_refused[season-100]
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_out_of_range_part_is_refused[episode-100]
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_out_of_range_part_is_refused[scene-1000]
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_out_of_range_part_is_refused[season-minus-1]
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_out_of_range_part_is_refused[episode-minus-1]
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_out_of_range_part_is_refused[scene-minus-1]
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_update_past_the_bound_is_refused
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_refusal_leaves_idf_and_clock_triggers_live
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_production_commit_refuses_scene_1000_and_rolls_back
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_migration_153_rerun_is_a_no_op
10 failed, 1 passed, 5 warnings in 6.08s
```

The failure lines (`grep -E '^E  ' red1.log | sort | uniq -c`):

```
   3 E           CONTEXT:  PL/pgSQL function set_chunk_slug() line 3 at assignment
   2 E           Failed: DID NOT RAISE <class 'psycopg2.errors.NumericValueOutOfRange'>
   3 E           psycopg2.errors.StringDataRightTruncation: value too long for type character varying(10)
   1 E        +    where <function search at 0x10a225a80> = re.search
   1 E        +  where None = <function search at 0x10a225a80>('numeric_value_out_of_range', "CREATE OR REPLACE FUNCTION public.set_chunk_slug()\n RETURNS trigger\n LANGUAGE plpgsql\nAS $function$\nBEGIN\n  NEW....    'E' || TO_CHAR(NEW.episode, 'FM00') ||\n    '_' || TO_CHAR(NEW.scene, 'FM000');\n  RETURN NEW;\nEND;\n$function$\n")
   1 E       assert None
   4 E       Failed: DID NOT RAISE <class 'psycopg2.errors.NumericValueOutOfRange'>
```

(2) Plant: the migration kept, `nexus/api/commit_handler_sync.py` restored from
`origin/main` (the slug parameter, both INSERT column lists and the Python
slug). The production-commit test fails with `StringDataRightTruncation`.

```
$ cp nexus/api/commit_handler_sync.py <scratch>/1069-S1/fix/commit_handler_sync.branch.py
$ git show origin/main:nexus/api/commit_handler_sync.py > nexus/api/commit_handler_sync.py
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_chunk_slug_bound_pg.py > <scratch>/1069-S1/fix/red2.log 2>&1
$ git checkout -- nexus/api/commit_handler_sync.py
$ cmp nexus/api/commit_handler_sync.py <scratch>/1069-S1/fix/commit_handler_sync.branch.py && echo restored
restored
```

Tail, verbatim from the guard line to the end:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 3 targets: postgres, qa640_1069_commit_*, qa640_1069_slug_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_production_commit_refuses_scene_1000_and_rolls_back
1 failed, 10 passed, 5 warnings in 6.04s
```

The failure lines (`grep -n`):

```
68:E           psycopg2.errors.StringDataRightTruncation: value too long for type character varying(10)
2343:ERROR    nexus.api.commit_handler_sync:commit_handler_sync.py:893 Failed to commit incubator session c61eaede-ab1b-4ec2-b657-5601afa45ef4: value too long for type character varying(10)
```

## PostgreSQL Proof

`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset; load average
under 24 before each run (8.47, 17.89 and 20.92 one-minute for the builder's
runs; 18.19 before the fixer's session one). `<scratch>` is the session
scratchpad.

Session one, rerun at fixer commit `1d04c8ce` (it holds
`tests/test_lore/test_pass2_baseline_pg.py`, which that commit changes):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_api/test_chunk_slug_bound_pg.py tests/test_commit_handler_sync.py tests/test_qa_shift.py tests/test_world_clock_contract_pg.py tests/test_orrery/test_replay.py tests/test_orrery/test_weather_live.py tests/test_lore/test_pass2_baseline_pg.py tests/test_pg_accepted_turn_factory.py tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py > <scratch>/1069-S1/fix/pg1.log 2>&1
```

Tail, verbatim from the guard line to the end:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 73 targets: nexus_test_pass2_* x7, postgres, qa640_1069_commit_*, qa640_1069_slug_*, qa640_759_measure_*, qa640_778s4a_tests_* x6, qa640_778s6a_family_* x9, qa640_778s6a_played_*, qa640_778s6a_replay_* x7, qa640_816_factory_*, qa640_816_free_text_*, qa640_816_lifecycle_test_provider, qa640_816_pending_*, qa640_816_preconditions_*, qa640_816_staging_failure_*, qa640_885_remembered_*, qa640_885_remembered_opening_*, qa640_885_ren_replay_* x4, qa640_clock_* x12, qa640_compaction_retry_*, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_replay_*, qa640_schema_docs_* x3, qa640_settings_stamp_*, qa640_vocab_migration_* x6, qa735_weather_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:60949 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:60952 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:60949 (psycopg2), save_04@local:60952 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
1 failed, 289 passed, 2 skipped, 15 warnings in 217.39s (0:03:37)
```

The one failure (`grep -n` on the log) is the expected
`tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps`
while 152 is unmerged:

```
7:_________________ test_migration_sequence_has_only_known_gaps __________________
18:E       AssertionError: assert {'013', '119', '152'} == frozenset({'013', '119'})
```

Session two, run by the builder at commit `7324332f` with the order's
session-two command (no file in this session changed after it; log
`<scratch>/1069-S1/pg2.log`):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_idf_dictionary_pg.py tests/test_orrery/test_acquisition_scan_pg.py tests/test_orrery/test_character_experiences_pg.py tests/test_api/test_reader_feed_pg.py tests/test_orrery/test_world_event_time_pg.py tests/test_pg_disposable_target.py tests/test_pg_experience_seeds.py
```

Tail, verbatim from the guard line to the end:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 73 targets: postgres, qa640_767s1_feed_* x3, qa640_778s2a_time_* x14, qa640_816_experience_seed_* x2, qa640_wizard_drain_* x3, qa762_corpus_copy_*, qa762_fresh_*, qa762_idf_* x19, qa762_other_*, qa885_transaction_writer_*, qa_wt723_*, qa_wt724_experience_* x26
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
139 passed, 7 warnings in 207.39s (0:03:27)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

`psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE
'qa640_1069%'"` printed nothing after the builder's sessions and again after
the fixer's runs and probe.

## Offline

`tests --ignore=tests/test_api --ignore=tests/test_orrery` ran at builder commit
`7324332f` (the fixer commit changes only PostgreSQL-marked test files, which
this run skips; log `<scratch>/1069-S1/off1.log`):

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3196 passed, 678 skipped, 8 warnings in 634.77s (0:10:34)
```

`tests/test_api tests/test_orrery`, rerun at fixer commit `1d04c8ce` with
`tests/test_lore` added (the directory of the changed pass-two file):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery tests/test_lore > <scratch>/1069-S1/fix/off2.log 2>&1
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 2323 passed, 1598 skipped, 7 warnings in 66.06s (0:01:06)
```

At fixer commit `1d04c8ce`:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py > <scratch>/1069-S1/fix/reach.log 2>&1
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 17.81s
```

## Static Checks

Recorded by the review fixer at commit `33a23ea6` (the builder's and first
fixer's runs gave counts only; these replace them). `origin/main` is
`c7ae2988`. The changed Python files are the thirteen pre-existing files
`$MOD` and the added `$ADD`:

```
MOD="nexus/api/commit_handler_sync.py tests/pg_fixtures.py tests/test_api/test_reader_feed_pg.py tests/test_commit_handler_sync.py tests/test_idf_dictionary_pg.py tests/test_lore/test_pass2_baseline_pg.py tests/test_orrery/claim_accounts_test_support.py tests/test_orrery/test_acquisition_scan_pg.py tests/test_orrery/test_character_experiences_pg.py tests/test_orrery/test_replay.py tests/test_orrery/test_weather_live.py tests/test_qa_shift.py tests/test_world_clock_contract_pg.py"
ADD="tests/test_api/test_chunk_slug_bound_pg.py"
```

The `origin/main` side is a full export of `nexus/`, `tests/`, `scripts/`,
`pyproject.toml` and `.flake8` at `origin/main`, so imports resolve as they do
in-tree and no worktree file is swapped:

```
$ git archive origin/main nexus tests scripts pyproject.toml .flake8 | tar -x -C <scratch>/1069-S1/static/main_tree
```

### Migration Comments and Exception Dispositions

```
$ PYTHONPATH=$PWD $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

No new handler; the baseline is unchanged.

### Black

```
$ nice -n 15 $PY -m black --check $MOD $ADD
All done! ✨ 🍰 ✨
14 files would be left unchanged.
```

### flake8

Branch, 21 lines:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m flake8 $MOD $ADD
nexus/api/commit_handler_sync.py:859:89: E501 line too long (91 > 88 characters)
tests/test_commit_handler_sync.py:194:89: E501 line too long (163 > 88 characters)
tests/test_commit_handler_sync.py:202:89: E501 line too long (176 > 88 characters)
tests/test_commit_handler_sync.py:824:5: F811 redefinition of unused 'mock_openai_server' from line 1029
tests/test_commit_handler_sync.py:863:89: E501 line too long (99 > 88 characters)
tests/test_commit_handler_sync.py:865:89: E501 line too long (114 > 88 characters)
tests/test_commit_handler_sync.py:879:89: E501 line too long (94 > 88 characters)
tests/test_commit_handler_sync.py:885:89: E501 line too long (100 > 88 characters)
tests/test_idf_dictionary_pg.py:113:89: E501 line too long (93 > 88 characters)
tests/test_idf_dictionary_pg.py:146:89: E501 line too long (105 > 88 characters)
tests/test_idf_dictionary_pg.py:228:89: E501 line too long (98 > 88 characters)
tests/test_idf_dictionary_pg.py:336:89: E501 line too long (91 > 88 characters)
tests/test_idf_dictionary_pg.py:624:89: E501 line too long (89 > 88 characters)
tests/test_idf_dictionary_pg.py:654:89: E501 line too long (112 > 88 characters)
tests/test_idf_dictionary_pg.py:693:89: E501 line too long (90 > 88 characters)
tests/test_lore/test_pass2_baseline_pg.py:253:89: E501 line too long (113 > 88 characters)
tests/test_orrery/test_character_experiences_pg.py:3574:89: E501 line too long (91 > 88 characters)
tests/test_orrery/test_character_experiences_pg.py:3580:89: E501 line too long (107 > 88 characters)
tests/test_orrery/test_replay.py:1056:89: E501 line too long (110 > 88 characters)
tests/test_world_clock_contract_pg.py:63:89: E501 line too long (91 > 88 characters)
tests/test_world_clock_contract_pg.py:97:89: E501 line too long (95 > 88 characters)
```

`origin/main`, 21 lines (the added file does not exist there):

```
$ cd <scratch>/1069-S1/static/main_tree && PYTHONPATH=$PWD nice -n 15 $PY -m flake8 $MOD
nexus/api/commit_handler_sync.py:867:89: E501 line too long (91 > 88 characters)
tests/test_commit_handler_sync.py:193:89: E501 line too long (163 > 88 characters)
tests/test_commit_handler_sync.py:201:89: E501 line too long (176 > 88 characters)
tests/test_commit_handler_sync.py:823:5: F811 redefinition of unused 'mock_openai_server' from line 1027
tests/test_commit_handler_sync.py:862:89: E501 line too long (99 > 88 characters)
tests/test_commit_handler_sync.py:864:89: E501 line too long (114 > 88 characters)
tests/test_commit_handler_sync.py:878:89: E501 line too long (94 > 88 characters)
tests/test_commit_handler_sync.py:884:89: E501 line too long (100 > 88 characters)
tests/test_idf_dictionary_pg.py:107:89: E501 line too long (93 > 88 characters)
tests/test_idf_dictionary_pg.py:140:89: E501 line too long (105 > 88 characters)
tests/test_idf_dictionary_pg.py:222:89: E501 line too long (98 > 88 characters)
tests/test_idf_dictionary_pg.py:330:89: E501 line too long (91 > 88 characters)
tests/test_idf_dictionary_pg.py:618:89: E501 line too long (89 > 88 characters)
tests/test_idf_dictionary_pg.py:648:89: E501 line too long (112 > 88 characters)
tests/test_idf_dictionary_pg.py:687:89: E501 line too long (90 > 88 characters)
tests/test_lore/test_pass2_baseline_pg.py:251:89: E501 line too long (113 > 88 characters)
tests/test_orrery/test_character_experiences_pg.py:3572:89: E501 line too long (91 > 88 characters)
tests/test_orrery/test_character_experiences_pg.py:3578:89: E501 line too long (107 > 88 characters)
tests/test_orrery/test_replay.py:1056:89: E501 line too long (110 > 88 characters)
tests/test_world_clock_contract_pg.py:63:89: E501 line too long (91 > 88 characters)
tests/test_world_clock_contract_pg.py:98:89: E501 line too long (95 > 88 characters)
```

With line and column numbers stripped, the two sorted lists differ only in
the line number inside the F811 message text (`from line 1029` on the branch,
`from line 1027` on `origin/main`, the same `mock_openai_server` fixture moved
by two added lines). No diagnostic is new, none is on a changed line, and the
added test file and `tests/test_orrery/claim_accounts_test_support.py` have
none. (The earlier count of 20 was for twelve files and omitted the pass-two
file, recorded separately; with it, both sides have 21.)

### mypy

Branch:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratch>/1069-S1/static/mypy_cache_branch $MOD $ADD
tests/test_world_clock_contract_pg.py:125: error: Value of type "dict[str, Any] | None" is not indexable  [index]
tests/test_qa_shift.py:192: error: "Collection[Collection[str]]" has no attribute "get"  [attr-defined]
tests/test_qa_shift.py:1088: error: No overload variant of "int" matches argument type "object"  [call-overload]
tests/test_qa_shift.py:1088: note: Possible overload variants:
tests/test_qa_shift.py:1088: note:     def __new__(cls, str | Buffer | SupportsInt | SupportsIndex | SupportsTrunc = ..., /) -> int
tests/test_qa_shift.py:1088: note:     def __new__(cls, str | bytes | bytearray, /, base: SupportsIndex) -> int
tests/test_orrery/test_character_experiences_pg.py:1598: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1599: error: "LogRecord" has no attribute "world_event_type"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1600: error: "LogRecord" has no attribute "world_event_tick_chunk_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1601: error: "LogRecord" has no attribute "world_event_actor_entity_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1602: error: "LogRecord" has no attribute "world_event_target_entity_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1603: error: "LogRecord" has no attribute "world_event_resolution_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1604: error: "LogRecord" has no attribute "world_event_source"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1605: error: "LogRecord" has no attribute "world_event_world_layer"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1606: error: "LogRecord" has no attribute "quarantine_reason_code"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2731: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2732: error: "LogRecord" has no attribute "replacement_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2831: error: "LogRecord" has no attribute "supersession_rejection_reason"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2838: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2839: error: "LogRecord" has no attribute "replacement_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2840: error: "LogRecord" has no attribute "supersession_rejection_detail"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:183: error: "_RouteProvider" has no attribute "prompt_window_guard"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:389: error: Incompatible types in assignment (expression has type "_DatabaseMemnon", variable has type "None")  [assignment]
tests/test_lore/test_pass2_baseline_pg.py:402: error: Incompatible types in assignment (expression has type "_RouteProvider", variable has type "OpenAIProvider | AnthropicProvider | None")  [assignment]
tests/test_lore/test_pass2_baseline_pg.py:452: error: Argument 1 to "run" has incompatible type "Awaitable[None]"; expected "Coroutine[Any, Any, Never]"  [arg-type]
tests/test_lore/test_pass2_baseline_pg.py:465: error: "None" has no attribute "turn_id"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:467: error: "None" has no attribute "context_payload"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:472: error: "None" has no attribute "memory_state"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:475: error: "None" has no attribute "memory_state"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:488: error: Argument 1 to "run" has incompatible type "Awaitable[None]"; expected "Coroutine[Any, Any, Never]"  [arg-type]
tests/test_lore/test_pass2_baseline_pg.py:503: error: "None" has no attribute "turn_id"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:505: error: "None" has no attribute "context_payload"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:509: error: "None" has no attribute "memory_state"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:1059: error: "None" has no attribute "token_counts"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:1060: error: "None" has no attribute "export_pass2_baseline"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:1083: error: "None" has no attribute "token_counts"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:1084: error: "None" has no attribute "memory_state"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:1086: error: "None" has no attribute "export_pass2_baseline"  [attr-defined]
tests/test_idf_dictionary_pg.py:161: error: Unsupported operand types for + ("None" and "int")  [operator]
tests/test_idf_dictionary_pg.py:161: note: Left operand is of type "int | None"
tests/test_idf_dictionary_pg.py:201: error: Unsupported operand types for + ("None" and "int")  [operator]
tests/test_idf_dictionary_pg.py:201: note: Left operand is of type "int | None"
tests/test_idf_dictionary_pg.py:284: error: Unsupported operand types for > ("int" and "None")  [operator]
tests/test_idf_dictionary_pg.py:284: error: Unsupported operand types for < ("int" and "None")  [operator]
tests/test_idf_dictionary_pg.py:284: error: Unsupported left operand type for > ("None")  [operator]
tests/test_idf_dictionary_pg.py:284: note: Both left and right operands are unions
tests/test_idf_dictionary_pg.py:340: error: Unsupported operand types for + ("None" and "int")  [operator]
tests/test_idf_dictionary_pg.py:340: note: Left operand is of type "int | None"
tests/test_idf_dictionary_pg.py:375: error: Unsupported operand types for + ("None" and "int")  [operator]
tests/test_idf_dictionary_pg.py:375: note: Left operand is of type "int | None"
tests/test_idf_dictionary_pg.py:410: error: Argument 1 to "append" of "list" has incompatible type "tuple[bytes | None, Any]"; expected "tuple[bytes, dict[str, int]]"  [arg-type]
tests/test_idf_dictionary_pg.py:410: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:311: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:312: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:320: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:321: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:323: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:583: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:591: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:685: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:686: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:687: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1483: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1485: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1487: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1488: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1489: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1497: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1505: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1506: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1507: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:2171: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_commit_handler_sync.py:38: error: Need type annotation for "description" (hint: "description: list[<type>] = ...")  [var-annotated]
Found 65 errors in 7 files (checked 14 source files)
```

`origin/main`:

```
$ cd <scratch>/1069-S1/static/main_tree && PYTHONPATH=$PWD nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratch>/1069-S1/static/mypy_cache_main $MOD
tests/test_world_clock_contract_pg.py:126: error: Value of type "dict[str, Any] | None" is not indexable  [index]
tests/test_qa_shift.py:192: error: "Collection[Collection[str]]" has no attribute "get"  [attr-defined]
tests/test_qa_shift.py:1088: error: No overload variant of "int" matches argument type "object"  [call-overload]
tests/test_qa_shift.py:1088: note: Possible overload variants:
tests/test_qa_shift.py:1088: note:     def __new__(cls, str | Buffer | SupportsInt | SupportsIndex | SupportsTrunc = ..., /) -> int
tests/test_qa_shift.py:1088: note:     def __new__(cls, str | bytes | bytearray, /, base: SupportsIndex) -> int
tests/test_orrery/test_character_experiences_pg.py:1596: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1597: error: "LogRecord" has no attribute "world_event_type"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1598: error: "LogRecord" has no attribute "world_event_tick_chunk_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1599: error: "LogRecord" has no attribute "world_event_actor_entity_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1600: error: "LogRecord" has no attribute "world_event_target_entity_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1601: error: "LogRecord" has no attribute "world_event_resolution_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1602: error: "LogRecord" has no attribute "world_event_source"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1603: error: "LogRecord" has no attribute "world_event_world_layer"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1604: error: "LogRecord" has no attribute "quarantine_reason_code"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2729: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2730: error: "LogRecord" has no attribute "replacement_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2829: error: "LogRecord" has no attribute "supersession_rejection_reason"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2836: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2837: error: "LogRecord" has no attribute "replacement_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2838: error: "LogRecord" has no attribute "supersession_rejection_detail"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:182: error: "_RouteProvider" has no attribute "prompt_window_guard"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:387: error: Incompatible types in assignment (expression has type "_DatabaseMemnon", variable has type "None")  [assignment]
tests/test_lore/test_pass2_baseline_pg.py:400: error: Incompatible types in assignment (expression has type "_RouteProvider", variable has type "OpenAIProvider | AnthropicProvider | None")  [assignment]
tests/test_lore/test_pass2_baseline_pg.py:450: error: Argument 1 to "run" has incompatible type "Awaitable[None]"; expected "Coroutine[Any, Any, Never]"  [arg-type]
tests/test_lore/test_pass2_baseline_pg.py:463: error: "None" has no attribute "turn_id"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:465: error: "None" has no attribute "context_payload"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:470: error: "None" has no attribute "memory_state"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:473: error: "None" has no attribute "memory_state"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:486: error: Argument 1 to "run" has incompatible type "Awaitable[None]"; expected "Coroutine[Any, Any, Never]"  [arg-type]
tests/test_lore/test_pass2_baseline_pg.py:501: error: "None" has no attribute "turn_id"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:503: error: "None" has no attribute "context_payload"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:507: error: "None" has no attribute "memory_state"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:1057: error: "None" has no attribute "token_counts"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:1058: error: "None" has no attribute "export_pass2_baseline"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:1081: error: "None" has no attribute "token_counts"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:1082: error: "None" has no attribute "memory_state"  [attr-defined]
tests/test_lore/test_pass2_baseline_pg.py:1084: error: "None" has no attribute "export_pass2_baseline"  [attr-defined]
tests/test_idf_dictionary_pg.py:155: error: Unsupported operand types for + ("None" and "int")  [operator]
tests/test_idf_dictionary_pg.py:155: note: Left operand is of type "int | None"
tests/test_idf_dictionary_pg.py:195: error: Unsupported operand types for + ("None" and "int")  [operator]
tests/test_idf_dictionary_pg.py:195: note: Left operand is of type "int | None"
tests/test_idf_dictionary_pg.py:278: error: Unsupported operand types for > ("int" and "None")  [operator]
tests/test_idf_dictionary_pg.py:278: error: Unsupported operand types for < ("int" and "None")  [operator]
tests/test_idf_dictionary_pg.py:278: error: Unsupported left operand type for > ("None")  [operator]
tests/test_idf_dictionary_pg.py:278: note: Both left and right operands are unions
tests/test_idf_dictionary_pg.py:334: error: Unsupported operand types for + ("None" and "int")  [operator]
tests/test_idf_dictionary_pg.py:334: note: Left operand is of type "int | None"
tests/test_idf_dictionary_pg.py:369: error: Unsupported operand types for + ("None" and "int")  [operator]
tests/test_idf_dictionary_pg.py:369: note: Left operand is of type "int | None"
tests/test_idf_dictionary_pg.py:404: error: Argument 1 to "append" of "list" has incompatible type "tuple[bytes | None, Any]"; expected "tuple[bytes, dict[str, int]]"  [arg-type]
tests/test_idf_dictionary_pg.py:404: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:311: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:312: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:320: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:321: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:323: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:583: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:591: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:685: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:686: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:687: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1483: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1485: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1487: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1488: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1489: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1497: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1505: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1506: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:1507: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_orrery/test_replay.py:2171: error: Value of type "dict[Any, Any] | None" is not indexable  [index]
tests/test_commit_handler_sync.py:37: error: Need type annotation for "description" (hint: "description: list[<type>] = ...")  [var-annotated]
Found 65 errors in 7 files (checked 13 source files)
```

With line numbers stripped, the sorted `error`/`note` lines of the two runs are
identical (`diff` prints nothing). All 65 errors are pre-existing; none is on a
changed line. The added test file and
`tests/test_orrery/claim_accounts_test_support.py` have none.

## Review Fixer Rerun at `33a23ea6`

Commit `33a23ea6` rewrites the comment above `_SCENE_NUMBERS` in
`tests/test_orrery/claim_accounts_test_support.py` (it described the pre-153
trigger writing `###` and colliding on `unique_slug`; it now says
`set_chunk_slug()` refuses scene > 999 with `numeric_value_out_of_range`) and
corrects the `insert_chunk_metadata_sync` cite above to `:95-142`. The change
to the support module is a comment only. The PostgreSQL file in the proof set
that imports it, one more importer, and the front-matter check were rerun
(one-minute load 20.21 before the run, no wait):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_pg_disposable_target.py tests/test_orrery/test_epistemics.py tests/test_doc_front_matter.py > <scratch>/1069-S1/static/pg_fix.log 2>&1
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 3 targets: postgres, qa885_epistemics_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
150 passed in 12.59s
```

`psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE
'qa640_1069%'"` printed nothing afterwards.
