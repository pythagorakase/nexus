# 778-S1b Verification: Loud NULL-Base Failure, Base-Edit Guard and Fixture Ordering

Issue #778, work order 778-S1b, branch `claude/778-null-base-guard`, cut from
`origin/main` at `364fef4b` (still the tip of `origin/main` at push time, so
the merge of `origin/main` was a no-op). Decisions 778-Q8 (A) and 778-Q3 (B)
from the "Decisions Recorded" comment on #778. No `save_NN`, `NEXUS_template`
or `ref_codex_bakeoff_2026_07` was written; every write went to a disposable
clone (`qa640_*`, `qa676_*`, `qa762_*`, `qa_wt724_*`, `nexus_test_*`). No paid
call, no gateway lane.

## Resumed on 2026-10-07

The coordinator stopped the first builder at 12:50 CDT for machine load. The
resumed builder found one commit and seven modified files.

| Commit or file | Order items | State found | Left unfinished |
| --- | --- | --- | --- |
| `36cc28ea` (migration 144, `docs/database.md`) | 1, 2, 3 | Complete; re-read against the order (comments byte-equal to the order, statement order, lock and rerun paragraphs). | Nothing. |
| `tests/pg_fixtures.py` (uncommitted) | 4 | `DEFAULT_BASE_TIMESTAMP`, `set_story_base`, `seed_story_base`, `seed_protagonist`/`seed_story_clock` rewrites, prose fixes. | Committed as `1b5473d9`. |
| `tests/test_pg_disposable_target.py` (uncommitted) | 4 | `seed_story_base` registered in `SEED_CALLS`. | Committed as `1b5473d9`. |
| `tests/test_interactions_pg.py`, `tests/test_orrery/test_retrograde_retrieval_pg.py`, `tests/test_lore/conftest.py` (uncommitted) | 5 | Known fixes applied. | Committed as `1b5473d9`. |
| `tests/test_connection_lifecycle.py` (uncommitted) | 5 | `set_story_base(cur, timestamp)` added at `:102`. | Discarded: the gate failed it (see below). |
| `tests/test_world_clock_contract_pg.py` (uncommitted) | Tests | Five new tests written. | Docstring reflowed to 88 columns; committed as `5c5b4615`. |
| (nothing) | 5, 6 (rest of the gate) | Not started. | Done in `58cef582`. |
| (nothing) | 7, 8, evidence, proofs | Not started. | Done in this file and the AGENTS.md commit. |

## What Is Wrong at `364fef4b` (Checked)

- `migrations/140_world_clock_primary_layer.sql:106-111` stamps from
  `COALESCE((SELECT base_timestamp ...), now())`; its comment documents the
  fallback (`:147-148`) and 140 keeps it by name (`:62-64`). On
  `NEXUS_template`, `pg_get_functiondef('public.refresh_world_time_from_chunk()')`
  still carries `COALESCE(` ... `now()` (read-only, lines 22-24 of the
  definition).
- `global_variables` has no user trigger on `NEXUS_template` or any slot (read-only
  `pg_trigger ... NOT tgisinternal` = 0 on all six databases, below).
- `migrations/118_world_clock_identity.sql:23-24`: the base comment says nothing
  about when it may change.
- Production order: `nexus/api/new_story_db_mapper.py:609-619` sets the base in
  the transition before the character rows and before the Retrograde hook
  (`:680`), which writes the prologue metadata at
  `nexus/agents/orrery/retrograde_persistence.py:2575`.
- Test harness at `origin/main`: `tests/pg_fixtures.py:637-643` sets the base
  under existing chunks and re-stamps them; `:806-810` writes the base by its
  own SQL.

## Fleet Survey (Read-Only, 2026-10-07)

`PGOPTIONS='-c default_transaction_read_only=on'`; columns: chunks, base set,
migration level, user triggers on `global_variables`.

```text
NEXUS_template 0||143|0
save_01 1425|t|143|0
save_02 1425|t|143|0
save_03 40|t|143|0
save_04 46|t|143|0
save_05 0|f|143|0
```

`NEXUS_template` has no `global_variables` row; `save_05` has a NULL base. No
database holds chunks under a NULL base, so 144's final refresh raises nowhere.

## Comments From a Migrated Clone

`createdb -T NEXUS_template qa640_778s1b_template`, then
`PYTHONPATH=$PWD $PY scripts/migrate.py --dbname qa640_778s1b_template`
(`Applied: 144_world_clock_base_contract`, `level 144`). `obj_description` and
`col_description` from the clone:

```text
FUNCTION refresh_world_time_from_chunk(): Recomputes chunk_metadata.world_time for every chunk as global_variables.base_timestamp plus the running sum, in chunk_id order, of the time_delta of primary-layer chunks (NULL counts as zero), so a chunk of any other layer, or with a NULL world_layer, carries the mainline clock at its position. Raises when chunk_metadata holds a row and base_timestamp is NULL or its row is missing; there is no wall-clock fallback. Raises when the bootstrap chunk (the lowest chunk_id) has a time_delta other than zero or NULL, because base_timestamp is the clock at its end. Writes only rows whose world_time changes; a world_time written by the inserter is overwritten.
FUNCTION refuse_base_timestamp_change(): Row trigger function for trg_global_variables_base_timestamp_fixed: raises when an UPDATE changes global_variables.base_timestamp while chunk_metadata holds any row, because refresh_world_time_from_chunk() would re-date chunk metadata while stored event times keep the old clock.
TRIGGER trg_global_variables_base_timestamp_fixed: Fixes base_timestamp at genesis: BEFORE UPDATE, for each row whose base_timestamp IS DISTINCT FROM its old value (NULL included), it calls refuse_base_timestamp_change(), which raises once chunk_metadata holds a row. An update that keeps the same value passes; a DELETE or INSERT of the row does not fire it.
COLUMN global_variables.base_timestamp: Story clock at the end of the bootstrap chunk, stored as timestamptz whose UTC face is the story clock face. It is set before the first chunk: while it is NULL, an INSERT into chunk_metadata, or an UPDATE of its time_delta or world_layer, raises when chunk_metadata then holds a row; once chunk_metadata holds a row, it cannot change.
```

A script compared each line with the migration's `COMMENT ON` literals (with
`''` unescaped) and with the order's item 2 text: `4 4 [True, True, True, True]`
for both. `$PY scripts/check_migration_comments.py`:
`OK: every object created after migration 129 has a comment.`

## Template-Clone Proof

On the same migrated clone:

```text
$ NEXUS_TEST_TEMPLATE_DB=qa640_778s1b_template NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_need_clock_anchor_pg.py
..................                                                       [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 19 targets: postgres, qa640_* x18
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
18 passed in 12.57s
```

Then `dropdb qa640_778s1b_template`.

## Zero-Change Proof

For N in 02, 03, 04: `createdb -T template0 qa640_778s1b_N`;
`pg_dump --format=custom save_N`; `pg_restore --exit-on-error --no-owner
--no-acl`; `SELECT chunk_id, world_layer, time_delta, world_time FROM
chunk_metadata ORDER BY chunk_id` before and after
`PYTHONPATH=$PWD $PY scripts/migrate.py --dbname qa640_778s1b_N`; `cmp`; drop.

```text
save_02: Applied 144; level 144; 1425 rows; cmp IDENTICAL; sha1 3c9fda06e9785affe2f19fadc0d4c4f89e93da91 (before = after)
save_03: Applied 144; level 144;   40 rows; cmp IDENTICAL; sha1 2d79726a12e7063e2c7f190ad813083b3f1720a2 (before = after)
save_04: Applied 144; level 144;   46 rows; cmp IDENTICAL; sha1 0b18288107f4310327e6f0200d14e8ae408178c7 (before = after)
```

No `qa640_778s1b_*` database remains (`psql -Atl`).

## Red Run

Three scratch copies of 144, each copied over the migration for one run and
reverted before commit (`git status --short migrations` clean afterwards). The
five new tests under each:

- Plant A (140's function body, guard kept):
  ```text
  PASSED test_base_timestamp_fixed_once_chunks_exist
  PASSED test_base_timestamp_free_before_chunks
  FAILED test_null_base_rejects_first_chunk            tests/test_world_clock_contract_pg.py:396: Failed: DID NOT RAISE <class 'psycopg2.errors.RaiseException'>
  FAILED test_null_base_rejects_later_writes           tests/test_world_clock_contract_pg.py:408: Failed: DID NOT RAISE <class 'psycopg2.errors.RaiseException'>
  FAILED test_migration_144_refuses_null_base_and_reruns  tests/test_world_clock_contract_pg.py:492: assert (1, 0) == (0, 1)
  3 failed, 2 passed, 7 deselected in 7.71s
  ```
- Plant B (no `CREATE TRIGGER` and no `COMMENT ON TRIGGER`):
  ```text
  PASSED test_null_base_rejects_first_chunk
  PASSED test_base_timestamp_free_before_chunks
  FAILED test_null_base_rejects_later_writes           tests/test_world_clock_contract_pg.py:366: psycopg2.errors.UndefinedObject: trigger "trg_global_variables_base_timestamp_fixed" for table "global_variables" does not exist
  FAILED test_base_timestamp_fixed_once_chunks_exist   tests/test_world_clock_contract_pg.py:423: Failed: DID NOT RAISE <class 'psycopg2.errors.RaiseException'>
  FAILED test_migration_144_refuses_null_base_and_reruns  tests/test_world_clock_contract_pg.py:366: psycopg2.errors.UndefinedObject: trigger "trg_global_variables_base_timestamp_fixed" for table "global_variables" does not exist
  3 failed, 2 passed, 7 deselected in 7.72s
  ```
  Tests 2 and 5 fail on the missing trigger in `_set_guard`, which runs in the
  test body (not in a fixture), so pytest reports FAILED rather than a setup
  ERROR. Test 3 fails on its own assertion.
- Plant C (`refuse_base_timestamp_change()` always raises):
  ```text
  PASSED test_null_base_rejects_first_chunk
  ERROR  test_null_base_rejects_later_writes           (clock_db: seed_protagonist -> tests/pg_fixtures.py:613 RaiseException: ... is fixed once chunk_metadata holds a row: refusing to change it from <NULL> to 2189-10-17 19:12:00+00)
  ERROR  test_base_timestamp_fixed_once_chunks_exist   (same setup error)
  FAILED test_base_timestamp_free_before_chunks        (seed_story_base -> same RaiseException with no chunk)
  FAILED test_migration_144_refuses_null_base_and_reruns  (seed_protagonist -> same RaiseException)
  2 failed, 1 passed, 7 deselected, 2 errors in 7.20s
  ```

Test 4 (`test_base_timestamp_free_before_chunks`) passes under Plants A and B.

## Item 8: Production Writers

- `global_variables.base_timestamp` has one production writer:
  `nexus/api/new_story_db_mapper.py:612-619`, inside the wizard-to-narrative
  transition, before the character rows and before the Retrograde hook
  (`:680`) writes the prologue metadata
  (`nexus/agents/orrery/retrograde_persistence.py:2575`). No production path
  writes the base after `chunk_metadata` holds a row. The other
  `base_timestamp` writes in `nexus/` (`nexus/api/new_story_cache.py:1190`,
  `:1753`) target `assets.new_story_creator`, the wizard cache, not
  `global_variables`. `scripts/qa_shift/` only reads the base
  (`scripts/qa_shift/world_clock.py:30`).
- Chunk-metadata writers that do not set a base themselves (each raises now
  on a slot whose base is NULL or whose `global_variables` row is missing, and
  each writes into a story that already has one in the paths that run today):
  `nexus/api/commit_handler_sync.py:124,134` (turn commit, after the
  transition), `nexus/agents/orrery/retrograde_persistence.py:2575` (after the
  base write in the same transaction),
  `nexus/agents/memnon/utils/content_processor.py:337` (MEMNON file ingest),
  `scripts/update_raw_text.py:733`, `scripts/simple_update.py:415,933`,
  `scripts/estimate_time_delta.py:1286` (legacy import/maintenance scripts),
  and `scripts/qa_shift/card_identity_probe.py:334` (copies an anchor's
  metadata in a story that has chunks, hence a base). None writes chunk
  metadata before the base in the paths read. The guard is not softened.

## Changed Tests and the Failure That Forced Each

Every failure below carried `Story clock has no base: global_variables.base_timestamp
is NULL or its row is missing while chunk_metadata holds chunk N`. None carried
`is fixed once chunk_metadata holds a row` except the discarded lifecycle edit.

| File | Fix | Failing tests before the fix |
| --- | --- | --- |
| `tests/test_interactions_pg.py` | `set_story_base(cur, DEFAULT_BASE_TIMESTAMP)` on the raw template clone | Known fix (item 5); cannot fail red before landing (raw 143-template clone). |
| `tests/test_orrery/test_retrograde_retrieval_pg.py` | `set_story_base` on `disposable_cursor` before the prologue chunk | Known fix (item 5); cannot fail red before landing (raw 143-template clone). |
| `tests/test_lore/conftest.py` | `seed_story_base` in `lore_infra_database` | Known fix (item 5). |
| `tests/test_idf_dictionary_pg.py` | `seed_story_base` in `idf_slot`, `qa762_other`, `qa762_fresh` | 17 tests (`test_slot_and_corpus_isolation` ... `test_data_clone_migrates_without_unlocking_source`). |
| `tests/test_orrery/test_narration_job_fencing_pg.py` | `set_story_base` in `_disposable_narration_db` (a `qa676_` raw template clone) | 7 tests (`test_duplicate_enqueue_collapses_to_one_effective_job` ... `test_descriptor_retirement_preserves_canon_legacy_jobs_and_bleed`). |
| `tests/test_orrery/test_recall_disclosure_pg.py` | `set_story_base` in module fixture `recall_database` | 21 tests. |
| `tests/test_orrery/test_bleed_proximity_live.py` | `seed_story_base` in `bleed_proximity_db` | 4 setup errors. |
| `tests/test_memnon/test_ann_gate.py` | `seed_story_base` in `ann_schema_clone` | 2 setup errors. |
| `tests/test_regenerate_embeddings_truncate_pg.py` | `seed_story_base` in `seeded_slot` | 2 setup errors. |
| `tests/test_api/test_narrative_jobs_pg.py` | `seed_story_base(offline_gate_db)` in the test (shared fixture left base-free) | `test_embedding_job_names_the_embedder_restore_command[missing]`, `[incomplete]`. |
| `tests/test_jobs_cli_pg.py` | `set_story_base` on the inserting cursor in the test | `test_jobs_cli_reports_counts_and_non_terminal_rows`. |
| `tests/test_lore/test_pass2_baseline_pg.py` | `seed_story_base` in the test | `test_evaluation_database_baseline_stamp_uses_story_settings`. |
| `tests/test_lore/test_scene_order_render.py` | `seed_story_base` in both tests | `test_recalled_render_clocks_come_from_narrative_view`, `test_assembly_hydrates_only_selected_recalled_entries_with_null_clocks`. |
| `tests/test_embedding_table_ownership_pg.py` | `seed_story_base` in `seed_source` before a chunk (an identical re-seed passes the guard) | 16 tests (every `chunk_id` parameter, plus `test_embedding_job_source_path_propagates_ensure_failure` and `test_content_processor_embedding_method_propagates_ensure_failure`). |
| `tests/test_api/test_scheduler_pg.py` | `seed_story_base` in `seed_experiences` (on `offline_gate_db`) | `test_scheduler_embeds_rendered_experiences_and_skips_the_rest`. |
| `tests/test_api/test_narrative_retry_pg.py` | `seed_story_base` in `recovery_db` before `_reset_to_committed_parent` | 17 setup errors. |

`tests/test_connection_lifecycle.py` is not changed. The order's known fix for
`:101` (`set_story_base(cur, timestamp)` first) is wrong for this test: by
then the wizard has bootstrapped `save_04` on the disposable cluster, so the
base is already set (1347-06-11 03:21) and chunks exist. The added call
failed the test with
`RaiseException: global_variables.base_timestamp is fixed once chunk_metadata holds a row: refusing to change it from 1347-06-11 03:21:00+00 to 2196-07-06 23:00:00+00`.
Without the call the chunk insert has a base and the test passes as on `main`
(`1 passed in 27.69s`).

`tests/test_world_clock_contract_pg.py` gains the five new tests;
`tests/test_pg_disposable_target.py` registers `seed_story_base`.

## Which PostgreSQL Files Ran

The Machine load rule forbids the whole PostgreSQL gate. Instead of the
three-piece split, these focused sets ran, one session at a time, under
`nice -n 15`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset:

1. The order's proof set plus every changed test file (final runs A and B below).
2. Every test file the order's static list names, every file that writes
   `chunk_metadata` directly (40 more files found by
   `grep -E "INSERT INTO chunk_metadata|insert_chunk_metadata_sync\(|seed_committed_chunk\("`),
   every test module importing a helper from one of those files (14 files),
   and every not-yet-run file with a raw `base_timestamp` write (5 files).
   After the fixes, all of these passed (tails below).

The coordinator's whole-tree gate at landing covers the remaining PostgreSQL
files, which write chunks only through `seed_protagonist`,
`seed_played_story`, `seed_story_clock`, the accepted-turn factory or the
wizard transition (each sets the base first).

Load: every run before the last two started at a one-minute load between 5.7
and 10.5. Final run A started at 33.72 (I did not read `uptime` before
launching it; the guard was skipped by mistake). Before run B the bounded wait
loop ran and found 14.65 (no wait).

## Tails

Final run A (the order's proof set, the known fixes and `tests/test_lore`):

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_world_clock_contract_pg.py tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py tests/test_orrery/test_need_clock_anchor_pg.py tests/test_qa_shift.py tests/test_new_story_setup.py tests/test_pg_accepted_turn_factory.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py tests/test_interactions_pg.py tests/test_orrery/test_retrograde_retrieval_pg.py tests/test_lore
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_lore/test_infrastructure.py:219: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_lore/test_pass2_chunk1369.py: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [2] tests/test_lore/test_window_coverage_pg.py:488: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
873 passed, 6 skipped, 15 warnings in 265.74s (0:04:25)
```

`test_migration_sequence_has_only_known_gaps` passed (every number below 144
is on `main`).

Final run B (the other changed test files):

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_api/test_narrative_jobs_pg.py tests/test_api/test_narrative_retry_pg.py tests/test_api/test_scheduler_pg.py tests/test_embedding_table_ownership_pg.py tests/test_idf_dictionary_pg.py tests/test_jobs_cli_pg.py tests/test_memnon/test_ann_gate.py tests/test_orrery/test_bleed_proximity_live.py tests/test_orrery/test_narration_job_fencing_pg.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_regenerate_embeddings_truncate_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
SKIPPED [1] tests/test_memnon/test_ann_gate.py:120: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
160 passed, 1 skipped, 7 warnings in 279.05s (0:04:39)
```

Survey runs (same environment), in order:

```text
proof1  (order set + known fixes, lifecycle edit present): 1 failed, 412 passed, 3 skipped in 142.59s   FAILED test_connection_two_clusters_story_lifecycle (is fixed once ...)
proof1b (tests/test_connection_lifecycle.py, edit discarded): 1 passed in 27.69s
proof2  (static list + tests/test_lore, before fixes): 51 failed, 513 passed, 5 skipped, 8 errors in 205.84s   (all "Story clock has no base")
proof2b (the ten failing files, after fixes): 101 passed, 1 skipped in 125.13s
proof3a (20 direct chunk writers): 16 failed, 265 passed in 279.54s   (tests/test_embedding_table_ownership_pg.py, "Story clock has no base")
proof3a2 (tests/test_embedding_table_ownership_pg.py, after fix): 52 passed in 77.89s
proof3b (20 more direct chunk writers): 180 passed in 135.65s
proof4  (14 importers of changed helpers): 2 failed, 153 passed, 17 errors in 302.98s
proof4b (the three failing files, after fixes): 34 passed in 122.78s
proof5  (5 files with raw base writes): 28 passed in 70.82s
```

Every survey tail showed `secret-store guard: active; nexus-api: denied` and
`dbname audit: owner targets: none`. In proof4,
`tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]`
failed on a timing bound (`assert (2492.553798708 - 2491.374662458) < 1`)
at a one-minute load near 10, with no clock or base error; the same file
passed whole in proof4b (`34 passed`). It is reported, not fixed.

Offline suites:

```text
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2944 passed, 564 skipped, 8 warnings in 515.65s (0:08:35)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1865 passed, 1369 skipped, 7 warnings in 47.26s

$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_doc_front_matter.py tests/test_reachability.py
96 passed, 5 warnings in 15.41s
```

Static checks on the 19 changed Python files:

```text
black --check: 19 files would be left unchanged.
flake8: 53 diagnostics on the branch, 53 on the origin/main versions; the
  same set once line numbers are dropped (the only text difference is
  test_scheduler_pg.py F811 "from line 377" -> "from line 378", shifted by
  the import line).
mypy --explicit-package-bases: Found 39 errors in 8 files (checked 19 source
  files) on the branch and on the origin/main versions; no new diagnostic.
$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
  OK: exception disposition coverage and shrink-only baseline verified.
```

Pre-existing diagnostics: the 53 flake8 and 39 mypy diagnostics above are all
on lines this branch does not change.

## Document Freshness

`tests/pg_fixtures.py` and `tests/test_lore/conftest.py` are `AGENTS.md`
sources. `AGENTS.md` names them only as the fixture modules to reuse
(`:53`), which stays true; `verified_commit` moves from `41783c1d` to the
merge base `364fef4b` (a descendant). No `docs/turn_flow_sequence.md` source
changed.

## Landing Notes

Migration 144. Apply when no turn is in flight: `python scripts/migrate.py --all`,
then `python scripts/migrate.py --slot 1 --write-locked-slot`, then
`nexus doctor`. With the template at 144, rerun every raw-template-clone file
the order lists (`tests/test_interactions_pg.py`,
`tests/test_orrery/test_retrograde_retrieval_pg.py`,
`tests/test_orrery/test_need_clock_anchor_pg.py`,
`tests/test_presence_boost_pg.py`, `tests/test_orrery_tag_validation_pg.py`,
`tests/test_lore/test_recent_orrery_rulings_pg.py`,
`tests/test_api/test_mock_wizard_responses.py`,
`tests/test_correspondence_live.py`, `tests/test_presence_reconciliation.py`,
`tests/test_orrery/test_gaia_registry_schema_pg.py`) with
`NEXUS_RUN_POSTGRES=1 ... -p tests.dbname_audit`. Migration, tests and docs
only: no gateway restart, no UI rebuild.
