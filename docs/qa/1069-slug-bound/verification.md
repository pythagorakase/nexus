# Verification: Refuse the Chunk Slug Bound Loudly (1069-S1)

Issue #1069; Decisions 1069-D1, D3, D4 and D7 (coordinator comment
"Decisions Recorded From the 2026-10-26 Coordinator Review"). Branch
`claude/1069-slug-bound`, cut from `origin/main` at `c7ae2988`; `origin/main`
had not moved when this file was written, so the merge base is `c7ae2988`.
Migration 153 (`migrations/153_chunk_slug_bound_refusal.sql`); 152 is held by
#1106 (PR #1153, open).

## Cited Lines at `c7ae2988`

- `nexus/api/commit_handler_sync.py:93-142` `insert_chunk_metadata_sync`;
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

`grep -rnE "scene\s*=\s*(chunk_id|i|tick|index)|VALUES \(%s, 1, 1, %s" tests`
plus the four helpers the order names. Changed to
`slug_bounded_episode_scene(chunk_id)`:

- `tests/pg_fixtures.py` `_insert_experience_chunk` (slug column dropped).
- `tests/test_orrery/test_character_experiences_pg.py` `_insert_chunk`
  (slug column dropped).
- `tests/test_idf_dictionary_pg.py` `_metadata`.
- `tests/test_orrery/test_acquisition_scan_pg.py` `_insert_chunk`.

In range on a fresh clone, unchanged:

- `tests/test_api/test_reader_feed_pg.py:79-85` (1,200 chunks,
  `scene = 1 + i % 200` over three episodes and two seasons) and `:222`
  (six chunks, `scene = index + 1`).
- `tests/test_orrery/test_acquisition_scan_pg.py:484-495` (300 rows, 100 per
  episode).
- `tests/test_orrery/test_world_event_time_pg.py:117-119`, `:398`, `:444`
  (`scene = tick + 1`, loop capped at 100).
- `tests/test_orrery/test_world_hour_horizon_pg.py:82-90` (40).
- `tests/test_api/test_reader_chunk_range_pg.py:70-76` (7).
- Also found by the grep and in range: `tests/test_jobs_cli_pg.py:67-77`
  (scenes 1 and 2), `tests/test_orrery/test_experience_enqueue_gin_pg.py:90-110`
  (callers pass scene 1-3), `tests/test_api/test_correspondence_pg.py:56-77`
  (`scene = index`, counts 1 and 10).

## The Refusal as Raised

Scratch probe on a disposable `qa640_1069_msg_*` clone (dropped by the
fixture), calling `seed_committed_chunk`:

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
```

## Red Runs

(1) Migration file moved out of `migrations/`, new file run: every test except
`test_in_range_slugs_keep_the_legacy_format` fails.

```
E       Failed: DID NOT RAISE <class 'psycopg2.errors.NumericValueOutOfRange'>
E           psycopg2.errors.StringDataRightTruncation: value too long for type character varying(10)
E           CONTEXT:  PL/pgSQL function set_chunk_slug() line 3 at assignment
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
10 failed, 1 passed, 5 warnings in 5.41s
```

(2) Migration kept, `nexus/api/commit_handler_sync.py` restored from
`origin/main` (restored to the branch file afterwards):

```
E           psycopg2.errors.StringDataRightTruncation: value too long for type character varying(10)
nexus/api/commit_handler_sync.py:123: StringDataRightTruncation
ERROR    nexus.api.commit_handler_sync:commit_handler_sync.py:893 Failed to commit incubator session a91df3a8-011e-458a-af28-2c1b8053498a: value too long for type character varying(10)
dbname audit: owner targets: none
FAILED tests/test_api/test_chunk_slug_bound_pg.py::test_production_commit_refuses_scene_1000_and_rolls_back
1 failed, 10 passed, 5 warnings in 6.78s
```

## PostgreSQL Proof

`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset; load average
under 24 before each run (8.47, 17.89 and 20.92 one-minute).

Session one (`NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q
-rs -p tests.dbname_audit tests/test_api/test_chunk_slug_bound_pg.py
tests/test_commit_handler_sync.py tests/test_qa_shift.py
tests/test_world_clock_contract_pg.py tests/test_orrery/test_replay.py
tests/test_orrery/test_weather_live.py tests/test_lore/test_pass2_baseline_pg.py
tests/test_pg_accepted_turn_factory.py tests/test_orrery/test_migrate.py
tests/test_schema_documentation_pg.py tests/test_orrery/test_card_identity.py
tests/test_connection_lifecycle.py`):

```
E       AssertionError: assert {'013', '119', '152'} == frozenset({'013', '119'})
dbname audit: owner targets: none
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
1 failed, 289 passed, 2 skipped, 15 warnings in 216.87s (0:03:36)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
```

The one failure is the expected
`tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps`
while 152 is unmerged.

Session two (`... tests/test_idf_dictionary_pg.py
tests/test_orrery/test_acquisition_scan_pg.py
tests/test_orrery/test_character_experiences_pg.py
tests/test_api/test_reader_feed_pg.py tests/test_orrery/test_world_event_time_pg.py
tests/test_pg_disposable_target.py tests/test_pg_experience_seeds.py`):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
139 passed, 7 warnings in 207.39s (0:03:27)
```

`psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE
'qa640_1069%'"` printed nothing.

## Offline

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
3196 passed, 678 skipped, 8 warnings in 634.77s (0:10:34)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1909 passed, 1543 skipped, 7 warnings in 46.50s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py
120 passed, 5 warnings in 17.51s
```

## Static Checks

- `scripts/check_migration_comments.py`: `OK: every object created after
  migration 129 has a comment.`
- `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref
  origin/main`: `OK: exception disposition coverage and shrink-only baseline
  verified.` (no new handler; baseline unchanged).
- Black `--check` on the twelve changed or added Python files: `12 files
  would be left unchanged.`
- flake8 on the same files: 20 diagnostics on the branch, 20 on the
  `origin/main` versions of the eleven pre-existing files; the per-file
  message multiset is identical (no new diagnostic). The two order-quoted
  texts that would exceed 88 columns (the `insert_chunk_metadata_sync`
  docstring and the `test_reader_feed_pg.py` comment) are wrapped across two
  lines with the words unchanged.
- `$PY -m mypy --explicit-package-bases` on the same files: `Found 48 errors
  in 6 files (checked 12 source files)` on the branch; the eleven
  `origin/main` versions checked in-tree give `Found 48 errors in 6 files
  (checked 11 source files)`, with an identical per-file message multiset
  (no new diagnostic; the new test file adds none). Pre-existing
  diagnostics: `tests/test_orrery/test_replay.py` (20 `index`),
  `tests/test_idf_dictionary_pg.py` (`operator`, `arg-type`, `index`),
  `tests/test_orrery/test_character_experiences_pg.py` (`attr-defined` on
  `LogRecord`), `tests/test_qa_shift.py:192` and `:1088` (`attr-defined`,
  `call-overload`), `tests/test_world_clock_contract_pg.py:125` (`index`),
  `tests/test_commit_handler_sync.py:38` (`var-annotated`); none on a changed
  line.
