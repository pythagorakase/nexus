# 823 Operation Journal: Source Checkpoint

Status: the authoring checkpoint (Codex, below) ran no proof. The wave-B fixer
then ran the order's proof on the integrated tree; see "Integrated-Tree Proof
(2026-10-13)" at the end. The whole-tree PostgreSQL gate, fleet migrations and
the owner-host smoke remain the coordinator's steps.

Authoring base: `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. The assembly moved the
canonical documents' `verified_commit` stamps to `f073b371`;
[canonical-source-closure.json](canonical-source-closure.json) still cites
`4ae8b8d2`, the authoring base, and `docs/decisions/0040-story-bundles.md` now
declares `nexus/maintenance/new_story_setup.py` at `f073b371`. Scope follows the frozen
823-S1 order, including its amendment removing the offline CLI entrypoint
tripwires, and the source refresh for the landed predecessors. The ruled journal,
maintenance target and validation choices are recorded in
[issue 823](https://github.com/pythagorakase/nexus/issues/823#issuecomment-5915951639).
No additional owner choice is required for this slice.

## Change and Source Review

The existing direct setup paths drop/rebuild a destination before validation and
have no operation journal. `scripts/new_story_setup.py::stage_slot_from_template`
and `stage_slot_clone` instead open and lock a durable JSON operation before
creating a derived staging database. Existing direct initialization and clone
behavior remain, including the direct clone's deliberate lack of migration,
alignment and IDF rebuilding. `tests/test_new_story_setup.py` is byte-identical
to the base. The shared dump helpers retain the original schema selections and
messages; only the two ordered dump-cleanup handlers leave the exception baseline.

`nexus/runtime/slot_operations.py` owns atomic/fsynced journal updates, legal
phase transitions and exact staging-name derivation. `require_authorized`
re-reads filename, operation ID, derived name and phase on every explicit
maintenance checkout. `nexus/api/db_pool.py::get_maintenance_connection` is
unpooled and owns commit, rollback and close. Gameplay admission is unchanged.
Migration and IDF runners revalidate each maintenance connection and retain their
existing behavior with no maintenance target. The IDF runner's existing
`commit_unknown` outcome is preserved; staging accepts only `rebuilt` and never
replays an uncertain commit automatically.

`validate_staging` uses one repeatable-read, read-only database session. It
collects stamp, story, slot, resolved-seat, tail Pass-2 compatibility, IDF analyzer,
replay-invariant and referenced-upload refusals. Missing or invalid story settings
skip only their dependent pin/Pass-2 checks. Database errors propagate. Uploads
remain rooted where the current endpoints serve them, `repo_root() / UPLOADS_DIR`.
A failed/refused database remains until an explicit sweep. Sweep takes the lock,
re-reads ownership and drops only the journal's exact derived name; locked and
unowned matching databases remain untouched.

Landed predecessor contracts retained:

- 822 template staging mints a wizard identity after IDF initialization; clone
  staging forks the copied UUID after migrations/cleanup and removes inherited
  lineage. Direct clone's identity preflight still precedes destination disposal.
- 840's template seed inventory, including Natural Earth, is unchanged. 812's
  template schema copy still includes `public`, `assets` and `ir_eval`; the
  existing full-data clone remains `public` plus `assets` only.
- 810's `require_assets_tables` and ANN behavior are unchanged. The two extension
  allowlist keys now name the extracted helpers, without broadening the allowance.
- 806 receipts, 816 test-provider routing and current model logic are unchanged.
  809's later fresh-NULL pin change must be merged normally and preserved;
  validation resolves precedence without persisting a new pin.
- 811 had not landed at the authoring base. On the integrated tree the setup and
  migration code lives in `nexus/maintenance/new_story_setup.py` and
  `nexus/maintenance/migrate.py`, and `scripts/new_story_setup.py` re-exports the
  six staging helpers; `scripts/rebuild_memory_idf.py` and
  `scripts/replay_state.py` do not move.

The authoring session reported two source reviews with no blocking finding. No
record of them is kept here, so they are not evidence. The later independent
review found the defects that the integrated-tree fixes below address.

## Source Checks Completed

The prescribed reachability generator and explanations show exactly four added
production paths: `nexus/runtime/slot_operations.py`,
`scripts/rebuild_memory_idf.py`, `scripts/replay_state.py`, and
`nexus/agents/orrery/replay.py`. The root is `nexus/api/narrative.py:app`; the two
scripts are reclassified as runtime. There are no removed production paths or
changed unreachable exemptions. This is module-import reachability, not proof
that a route invokes staging. The authoring output is not reproduced here; the
fixer regenerated the baseline on the integrated tree and recorded the four
`--explain` chains below.

The [canonical closure](canonical-source-closure.json) contains only decision
0040. Its quoted ruling is unchanged. At authoring its stamp was refreshed to
`4ae8b8d2`; the assembly moved it to `f073b371`. The frozen order's statement
that no declared source changes is stale because that decision declares the
setup module (now `nexus/maintenance/new_story_setup.py`).

The authoring checkpoint recorded no Black, flake8, mypy or pytest result. It
had shortened the four disposition markers to fit 88 columns; the fixer restored
the order's exact reason and safety text (see below). Black, flake8, mypy and the
disposition lint are recorded in the integrated-tree proof.

## Proof Plan as Authored

Use the shared absolute interpreter, exact worktree `PYTHONPATH`, `nice -n 15`,
load below 24, clean ambient runtime/routing/libpq/PYTEST/live overrides, disabled
Keychain and the normal TEST-provider/receipt/owner guards. Every staging run
must use routed `qa640_` destinations with private journal/uploads directories.
No owner-host staging or sweeping is part of worker authorization.

The required PostgreSQL selection is:

```sh
NEXUS_RUN_POSTGRES=1 nice -n 15 "$PY" -m pytest -q -p tests.dbname_audit \
  tests/test_slot_operations_pg.py tests/test_new_story_setup.py \
  tests/test_postgres_tools.py tests/test_api/test_db_pool_pg.py \
  tests/test_api/test_correspondence_pg.py tests/test_pg_disposable_target.py \
  tests/test_owner_target_guard.py tests/test_orrery/test_card_identity.py \
  tests/test_connection_lifecycle.py
```

Add the new journal file, schema-ownership file, current story-identity and
migration/IDF runner consumer tests, reachability and canonical freshness to the
coordinator's deduplicated focused selection. The new real PostgreSQL cases
check unchanged destination OID/marker, source counts/stamps, identities,
pending migration execution, all six refusal categories, post-refusal checkout
revocation, unstamped refusal before migration, stale-IDF rebuild, child-process
journal reuse, held locks, unowned reporting and idempotent sweep. Offline cases
exercise real files/process locks and the exact early CLI errors without mocks.

After focused green, run the two distinct required plants, restoring exact source
bytes between them and before committing proof:

1. Remove only clone staging's `_align_slot_number` call. The played-story clone
   test must refuse with `slot: slot_number is None, expected 5`: the clone
   source's `slot_number` is NULL, as the order says (`seed_played_story(...,
   slot=4)` uses the slot only for routing and writes no `slot_number`). The
   integrated-tree run below shows that reason.
2. Remove only the validator's Pass-2 check. Both `pass2_missing` and
   `pass2_fingerprint` cases must fail because `StagingRefused` was not raised.

Retain the actual tails, guard/receipt/owner summaries, separate plant hashes and
restoration hashes, static comparisons against the same base, and a real sample
journal from the disposable proof. After fixture cleanup, the read-only postgres
catalog query must return no `qa640_823s1%` database. Broader integration coverage
is coordinator-owned; no separate whole offline gate is claimed.

## Fleet Observations and Landing

The authoring checkpoint performed no owner-fleet survey. The fixer's read-only
survey (2026-10-13, tree `933992b5`) is recorded under the integrated-tree
proof. Disposable proof uses migrations actually on disk and the script-only 008
exemption rather than a historical count.

No migration, fleet application, config change, UI rebuild or state-surface
regeneration is required by this slice. Owner services remain stopped; the next
authorized gateway startup must load the changed setup/maintenance modules.
There is no replacement/swap, backup policy, automatic quarantine or automatic
routing of current reset/clone/start-setup through staging in this slice.

Codex — GPT-6 (authoring checkpoint)

## Integrated-Tree Proof (2026-10-13)

Run by the wave-B fixer (Claude Opus 5.5) in the worktree
`.claude/worktrees/fix-823-s1`, branch `claude/waveb-fix-823-s1`, cut from the
integration head `7eb9a10c` (origin/main `f073b371` plus fifteen wave-B lanes, the
777 shell and a palette commit). `$PY` is `/Users/pythagor/nexus/.venv/bin/python`;
`PYTHONPATH=$PWD $PY -c 'import nexus;print(nexus.__file__)'` printed
`/Users/pythagor/nexus/.claude/worktrees/fix-823-s1/nexus/__init__.py`. Every
PostgreSQL run had `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset.

### Fixes Made on This Tree

- `32047ccf`: `validate_staging` runs the three `invariants:` replay checks
  (now in `_validate_invariants`) only when the `global_variables` row exists,
  so a missing row returns `story: global_variables row is missing` instead of
  raising `RuntimeError("Missing global_variables singleton")` from
  `verify_chunk_clocks_sync`. The four markers in `nexus/runtime/slot_operations.py`
  carry the order's exact text (`fail; reason=a validation failure becomes a
  staging refusal; safety=the refusal blocks the operation and the staging
  database is kept` on the three validation handlers, `safe-continuation;
  reason=a live process holds the operation lock; safety=its staging database and
  record are left untouched` on the sweep's `BlockingIOError` handler).
  `get_maintenance_connection` commits in an `else:` branch (the `transaction`
  shape), so an `AmbiguousCommit` no longer leads to a rollback on a closed
  connection and a false "Rollback failed" log.
- `7146f7ac`: `test_validator_refuses_a_mutated_built_staging` builds a real
  template staging (`open_operation`, `building`, `_build_from_template`,
  `_align_slot_number`, `built`), checks that `validate_staging` returns `[]`,
  applies one real mutation through `get_maintenance_connection` with the phase
  still `built`, and asserts the single reason: `idf_key`, `idf_missing`, `slot`,
  `stamps_missing` and `story` (the deleted row; no exception).
  `test_migration_runner_revalidates_every_checkout` restores a clone into
  staging and runs `migrate_database` with two probe migrations. Probe 998
  rewrites the journal to `failed` with a server-side `COPY ... TO` the journal
  path, and the runner must refuse the checkout for probe 999 (stamp 998 present,
  999 absent, table absent). `test_clone_staging_refuses` also asserts that
  `rebuild_database(..., dry_run=True, maintenance_target=target)` refuses.
- `933992b5`: `config/reachability_baseline.json` regenerated (below).

The marker regex in `scripts/check_exception_dispositions.py` is anchored with
`\Z`, and `_header_marker` reads comments only on the line of the handler's
header colon, so a marker on the line above the `except` is not read. The four
marker lines therefore exceed 88 columns (E501, accepted below); no `# noqa` is
appended to a marker.

### Focused PostgreSQL Selection

The order's selection plus `tests/test_slot_operations_journal.py`,
`tests/test_schema_ownership.py` and `tests/test_script_wrappers.py`, split in
two sessions run one after the other on `933992b5`. Piece one started with a
one-minute load of 24.74 (`uptime` at 12:36): this fixer did not wait for the
load to drop below 24 before that run, which the shared-machine rule requires.
Every later PostgreSQL run started below 24 (19.01 was the highest).

```sh
unset NEXUS_GATEWAY_PORT NEXUS_API_URL NEXUS_SLOT
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_slot_operations_pg.py tests/test_slot_operations_journal.py \
  tests/test_new_story_setup.py tests/test_postgres_tools.py \
  tests/test_schema_ownership.py tests/test_script_wrappers.py \
  tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 97 targets: nexus_m10_fresh_test_65149, nexus_m10_template_test_65149, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_810s3_ann_* x2, qa640_810s3_ann_high_* x2, qa640_810s3_ann_precheck_* x12, qa640_810s3_assets_*, qa640_810s3_importer_*, qa640_810s3_provider_*, qa640_810s3_regen_*, qa640_810s3_scene_* x2, qa640_810s3_season_*, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_823s1_dest_* x20, qa640_823s1_dest_07e99227eb65_staging_*, qa640_823s1_dest_0baa75d89d80_staging_*, qa640_823s1_dest_2941d114a9a2_staging_*, qa640_823s1_dest_2fe8878b150d_staging_*, qa640_823s1_dest_429c2a700a05_staging_*, qa640_823s1_dest_44b60508c3f5_staging_*, qa640_823s1_dest_51f0997a2edd_staging_*, qa640_823s1_dest_5af8507c4f85_staging_*, qa640_823s1_dest_7eccbd7337fa_staging_*, qa640_823s1_dest_808f2640e36a_staging_*, qa640_823s1_dest_8433e5e9afa9_staging_*, qa640_823s1_dest_9022975ea8af_staging_*, qa640_823s1_dest_a18588d11e39_staging_*, qa640_823s1_dest_caed52172586_staging_*, qa640_823s1_dest_d4d0fde32607_staging_*, qa640_823s1_dest_df15b105b432_staging_*, qa640_823s1_dest_e70df426ac54_staging_*, qa640_823s1_dest_eb57e9f2a3a9_staging_*, qa640_823s1_src_* x20, qa640_823s1_tpl_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
1 failed, 248 passed, 2 warnings in 224.57s (0:03:44)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The one failure is not in a file this lane changed. The wave-B 811-S3a wrapper
test finds two other lanes' test files importing `from scripts import migrate`:
`tests/test_orrery/test_place_point_required_pg.py:11` (840-S2) and
`tests/test_runtime/test_init_plan_pg.py:23` (803-S1). It is reported to the
coordinator and not fixed here.

```sh
unset NEXUS_GATEWAY_PORT NEXUS_API_URL NEXUS_SLOT
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_api/test_db_pool_pg.py tests/test_api/test_correspondence_pg.py \
  tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 20 targets: nexus_test_correspondence_* x2, postgres, qa640_804_* x12, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:55955 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:55958 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:55955 (psycopg2), save_04@local:55958 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
24 passed, 2 skipped, 7 warnings in 57.15s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The two skips are `tests/test_orrery/test_card_identity.py:122` ("Set
NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones."), shown by a
rerun of that file with `-rs`.

Cleanup after every run, including the plants:

```sh
psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_823s1%'"
```

```text
(no rows)
```

### Sample Journal Record

From `tests/test_slot_operations_pg.py::test_stage_clone_of_played_story_validates`
on `933992b5` with `--basetemp` in the fixer's scratch directory (`1 passed`;
the teardown sweep added `swept`):

```json
{
  "schema_version": 1,
  "operation_id": "9da7f4ca18f24382be9bb7bf729676b8",
  "kind": "stage_clone",
  "slot": 5,
  "destination_db": "qa640_823s1_dest_0bec52444e4a",
  "source_db": "qa640_823s1_src_3029f5d13a4d",
  "staging_db": "qa640_823s1_dest_0bec52444e4a_staging_9da7f4ca18f2",
  "pid": 86277,
  "created_at": "2026-10-13T17:46:00.159234Z",
  "updated_at": "2026-10-13T17:46:02.912883Z",
  "phase": "swept",
  "history": [
    {
      "phase": "created",
      "at": "2026-10-13T17:46:00.159234Z",
      "detail": null
    },
    {
      "phase": "building",
      "at": "2026-10-13T17:46:00.159927Z",
      "detail": null
    },
    {
      "phase": "built",
      "at": "2026-10-13T17:46:02.538748Z",
      "detail": null
    },
    {
      "phase": "validated",
      "at": "2026-10-13T17:46:02.580470Z",
      "detail": null
    },
    {
      "phase": "swept",
      "at": "2026-10-13T17:46:02.912883Z",
      "detail": null
    }
  ],
  "refusals": [],
  "error": null
}
```

### Red Runs

Each plant was a separate scratch edit, run, then restored before the next;
nothing was committed with a plant. The order requires Plants A and B; C to H
show that each new test fails without its check.

### Plant A: Clone Staging Without Slot Alignment

Ran on `933992b5` with only this plant applied to `nexus/maintenance/new_story_setup.py`, then restored:

```diff
-        _align_slot_number(target, slot)   # line 768, in stage_slot_clone
```

```sh
unset NEXUS_GATEWAY_PORT NEXUS_API_URL NEXUS_SLOT
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  'tests/test_slot_operations_pg.py::test_stage_clone_of_played_story_validates'
git checkout -- nexus/maintenance/new_story_setup.py; git diff --quiet -- nexus/maintenance/new_story_setup.py && echo restored-clean
```

```text
E               nexus.runtime.slot_operations.StagingRefused: Staging database qa640_823s1_dest_35eedd6c0e2f_staging_ee1fe63b91a0 refused: slot: slot_number is None, expected 5 (journal /private/var/folders/r5/zvbnrwp55r7dctnkr9s3b3780000gn/T/pytest-of-pythagor/pytest-674/test_stage_clone_of_played_sto0/journal/ee1fe63b91a04a77b80ce687776bdc27.json)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
FAILED tests/test_slot_operations_pg.py::test_stage_clone_of_played_story_validates
1 failed, 2 warnings in 6.54s
restored-clean
```

SHA-256 before the plant `29d5b3bc...`, with it `c7c57e7a...`, after restoring `29d5b3bc...`. The refusal reads `slot: slot_number is None, expected 5`, confirming that the clone source's `slot_number` is NULL.

### Plant B: Validator Without the Pass-2 Check

Ran on `933992b5` with only this plant applied to `nexus/runtime/slot_operations.py`, then restored:

```diff
-                _validate_pass2(cur, story, settings, refusals)
```

```sh
unset NEXUS_GATEWAY_PORT NEXUS_API_URL NEXUS_SLOT
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_slot_operations_pg.py -k 'test_clone_staging_refuses and pass2'
git checkout -- nexus/runtime/slot_operations.py; git diff --quiet -- nexus/runtime/slot_operations.py && echo restored-clean
```

```text
E       Failed: DID NOT RAISE <class 'nexus.runtime.slot_operations.StagingRefused'>
E       Failed: DID NOT RAISE <class 'nexus.runtime.slot_operations.StagingRefused'>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
FAILED tests/test_slot_operations_pg.py::test_clone_staging_refuses[pass2_missing-pass2:]
FAILED tests/test_slot_operations_pg.py::test_clone_staging_refuses[pass2_fingerprint-pass2:]
2 failed, 18 deselected, 2 warnings in 11.69s
restored-clean
```

SHA-256 before `45167520...`, with the plant `8a9a3d19...`, after restoring `45167520...`. Both cases fail with `Failed: DID NOT RAISE <class 'nexus.runtime.slot_operations.StagingRefused'>`.

### Plant C: Invariants Run Without the Story Row

Ran on `933992b5` with only this plant applied to `nexus/runtime/slot_operations.py`, then restored:

```diff
-            if row is not None:
+            if True:
```

```sh
unset NEXUS_GATEWAY_PORT NEXUS_API_URL NEXUS_SLOT
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_slot_operations_pg.py -k 'validator_refuses and story'
git checkout -- nexus/runtime/slot_operations.py; git diff --quiet -- nexus/runtime/slot_operations.py && echo restored-clean
```

```text
E           RuntimeError: Missing global_variables singleton
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
FAILED tests/test_slot_operations_pg.py::test_validator_refuses_a_mutated_built_staging[story-DELETE FROM global_variables-story: global_variables row is missing]
1 failed, 19 deselected, 2 warnings in 8.81s
restored-clean
```

The failure is `RuntimeError: Missing global_variables singleton`, the defect this tree fixes.

### Plant D: Runner Without Per-Migration Revalidation

Ran on `933992b5` with only this plant applied to `nexus/maintenance/migrate.py`, then restored:

```diff
-        if maintenance_target is not None:
-            from nexus.runtime.slot_operations import require_authorized
-
-            require_authorized(maintenance_target)
```

```sh
unset NEXUS_GATEWAY_PORT NEXUS_API_URL NEXUS_SLOT
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_slot_operations_pg.py -k revalidates_every
git checkout -- nexus/maintenance/migrate.py; git diff --quiet -- nexus/maintenance/migrate.py && echo restored-clean
```

```text
E           Failed: DID NOT RAISE <class 'nexus.runtime.slot_operations.MaintenanceTargetError'>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
FAILED tests/test_slot_operations_pg.py::test_migration_runner_revalidates_every_checkout
1 failed, 19 deselected, 2 warnings in 6.49s
restored-clean
```

The failure is `Failed: DID NOT RAISE <class 'nexus.runtime.slot_operations.MaintenanceTargetError'>`.

### Plant E: Validator Without the IDF Check

Ran on `933992b5` with only this plant applied to `nexus/runtime/slot_operations.py`, then restored:

```diff
-                if kind not in corpora:
+                if False:
-                elif corpora[kind] != live_key:
+                elif False:
```

```sh
unset NEXUS_GATEWAY_PORT NEXUS_API_URL NEXUS_SLOT
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_slot_operations_pg.py -k 'validator_refuses and idf'
git checkout -- nexus/runtime/slot_operations.py; git diff --quiet -- nexus/runtime/slot_operations.py && echo restored-clean
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
FAILED tests/test_slot_operations_pg.py::test_validator_refuses_a_mutated_built_staging[idf_key-UPDATE memory_idf_corpora SET analyzer_version = 'pg_catalog.english/v1/0' WHERE corpus_kind = 'narrative'-idf: narrative analyzer 'pg_catalog.english/v1/0', expected pg_catalog.english/v1/]
FAILED tests/test_slot_operations_pg.py::test_validator_refuses_a_mutated_built_staging[idf_missing-DELETE FROM memory_idf_corpora WHERE corpus_kind = 'retrograde_summary'-idf: missing retrograde_summary corpus]
2 failed, 18 deselected, 2 warnings in 15.51s
restored-clean
```
### Plant F: Validator Without the Slot Check

Ran on `933992b5` with only this plant applied to `nexus/runtime/slot_operations.py`, then restored:

```diff
-    if row[3] != slot:
-        refusals.append(f"slot: slot_number is {row[3]!r}, expected {slot}")
```

```sh
unset NEXUS_GATEWAY_PORT NEXUS_API_URL NEXUS_SLOT
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_slot_operations_pg.py -k 'validator_refuses and slot'
git checkout -- nexus/runtime/slot_operations.py; git diff --quiet -- nexus/runtime/slot_operations.py && echo restored-clean
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
FAILED tests/test_slot_operations_pg.py::test_validator_refuses_a_mutated_built_staging[slot-UPDATE global_variables SET slot_number = 3-slot: slot_number is 3, expected 5]
1 failed, 4 passed, 15 deselected, 2 warnings in 31.59s
restored-clean
```

(The `-k` expression also matched four other parametrized ids, whose names contain `slot`; they passed.)

### Plant G: Validator Without the Missing-Stamp Check

Ran on `933992b5` with only this plant applied to `nexus/runtime/slot_operations.py`, then restored:

```diff
-            refusals.extend(
-                f"stamps: missing {version}"
-                for version in sorted(expected_stamps - stamped)
-            )
```

```sh
unset NEXUS_GATEWAY_PORT NEXUS_API_URL NEXUS_SLOT
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_slot_operations_pg.py -k 'validator_refuses and stamps_missing'
git checkout -- nexus/runtime/slot_operations.py; git diff --quiet -- nexus/runtime/slot_operations.py && echo restored-clean
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
FAILED tests/test_slot_operations_pg.py::test_validator_refuses_a_mutated_built_staging[stamps_missing-DELETE FROM schema_migrations WHERE version = (SELECT max(version) FROM schema_migrations)-stamps: missing ]
1 failed, 19 deselected, 2 warnings in 9.74s
restored-clean
```
### Plant H: IDF Dry Run Without Revalidation

Ran on `933992b5` with only this plant applied to `scripts/rebuild_memory_idf.py`, then restored:

```diff
-    if maintenance_target is not None:
-        from nexus.runtime.slot_operations import require_authorized
-
-        require_authorized(maintenance_target)   # in _dry_run
```

```sh
unset NEXUS_GATEWAY_PORT NEXUS_API_URL NEXUS_SLOT
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_slot_operations_pg.py -k 'test_clone_staging_refuses and pins'
git checkout -- scripts/rebuild_memory_idf.py; git diff --quiet -- scripts/rebuild_memory_idf.py && echo restored-clean
```

```text
E       Failed: DID NOT RAISE <class 'nexus.runtime.slot_operations.MaintenanceTargetError'>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
FAILED tests/test_slot_operations_pg.py::test_clone_staging_refuses[pins-pins:]
1 failed, 19 deselected, 2 warnings in 7.06s
restored-clean
```

The failure is at the new `dry_run=True` assertion (`tests/test_slot_operations_pg.py:333`, `Failed: DID NOT RAISE <class 'nexus.runtime.slot_operations.MaintenanceTargetError'>`).

### Offline Suites

Run with `NEXUS_RUN_POSTGRES` unset, on `933992b5`, one after the other:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES \
  PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api \
  --ignore=tests/test_orrery -p no:cacheprovider
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
5 failed, 3192 passed, 677 skipped, 8 warnings in 708.29s (0:11:48)
exit=1
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES \
  PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery \
  -p no:cacheprovider
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_queues_narration_job
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_skips_low_signal_rows
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_state_signal_without_brief
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_configured_thresholds
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_persists_offscreen_narration
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_requeues_transient_failures
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_marks_terminal_after_max_attempts
FAILED tests/test_orrery/test_worker.py::test_clear_semantic_tags_is_conservative_noop_without_local_inference
11 failed, 1896 passed, 1517 skipped, 7 warnings in 53.49s
exit=1
```

None of these failures is in a file this lane changed or reached from it. They
are reported to the coordinator for triage: the assembled-prompt fingerprint
and Gaia prompt length (`tests/test_lore/`), the `NewEntityDeclaration.coordinates`
wire-schema budget (`tests/test_skald_wire.py`, 840-S2), the wrapper-binding test
above, `tests/test_wizard_agent.py`, `tests/test_api/test_wizard_confirmation.py`,
`tests/test_orrery/test_config.py`, and eight `tests/test_orrery/test_worker.py`
cases that fail with `orrery.projects.milestone_magnitude must be >=
orrery.promote.magnitude_threshold`.

```sh
PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_slot_operations_journal.py
PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py
PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py
```

```text
21 passed, 5 warnings in 0.36s
54 passed, 5 warnings in 12.83s
66 passed, 5 warnings in 8.79s
```

(The journal file ran on the working tree before `32047ccf` was committed, with
the same content; the other two ran on `933992b5`.)

### Reachability

```sh
PYTHONPATH=$PWD $PY scripts/check_reachability.py --write-baseline --reason "Wave B (2026-10-09): 823-S1 slot operation journal and staging; 840-S2 required place points; 803-S1 readiness import and desktop checks; 811-S3a maintenance module moves; 777 shell UI-config route"
```

The diff changes only the `reason` (from the hand-merged "Combined #803
init/desktop, #823 journal, #840 point policy and #811 maintenance-module
closure; final assembled AST admission pending"); the production and unreachable
sets that the assembly had merged by hand equal the generator's output. Each
`--explain` (production, reachable, root `nexus/api/narrative.py:app`):

```text
nexus/runtime/slot_operations.py: nexus/api/narrative.py -> nexus/api/db_pool.py -> nexus/runtime/slot_operations.py
scripts/rebuild_memory_idf.py: nexus/api/narrative.py -> nexus/api/new_story_flow.py -> nexus/maintenance/new_story_setup.py -> scripts/rebuild_memory_idf.py
scripts/replay_state.py: nexus/api/narrative.py -> nexus/api/db_pool.py -> nexus/runtime/slot_operations.py -> scripts/replay_state.py
nexus/agents/orrery/replay.py: nexus/api/narrative.py -> nexus/api/db_pool.py -> nexus/runtime/slot_operations.py -> nexus/agents/orrery/replay.py
```

### Static Checks

Files: `nexus/api/db_pool.py`, `nexus/runtime/slot_operations.py`,
`nexus/maintenance/migrate.py`, `nexus/maintenance/new_story_setup.py`,
`scripts/rebuild_memory_idf.py`, `tests/test_slot_operations_journal.py`,
`tests/test_slot_operations_pg.py`, `tests/test_schema_ownership.py`, on
`933992b5`. The base comparison uses `git show origin/main:<path>` copies
(`f073b371`) of `nexus/api/db_pool.py`, `scripts/rebuild_memory_idf.py`,
`tests/test_schema_ownership.py`, `scripts/migrate.py` and
`scripts/new_story_setup.py` (the last two are the pre-move homes of the
`nexus/maintenance/` modules).

```text
$ $PY -m black --check <files>
All done! ✨ 🍰 ✨
8 files would be left unchanged.

$ $PY -m flake8 <files>            # HEAD
nexus/api/db_pool.py:30:1: F401 'nexus.database.database_url' imported but unused
nexus/maintenance/migrate.py:180:89: E501 line too long (94 > 88 characters)
nexus/maintenance/migrate.py:201:89: E501 line too long (99 > 88 characters)
nexus/maintenance/migrate.py:205:89: E501 line too long (92 > 88 characters)
nexus/maintenance/new_story_setup.py:7:89: E501 line too long (101 > 88 characters)
nexus/maintenance/new_story_setup.py:66:89: E501 line too long (90 > 88 characters)
nexus/maintenance/new_story_setup.py:81:89: E501 line too long (91 > 88 characters)
nexus/maintenance/new_story_setup.py:125:89: E501 line too long (101 > 88 characters)
nexus/maintenance/new_story_setup.py:253:89: E501 line too long (96 > 88 characters)
nexus/maintenance/new_story_setup.py:395:89: E501 line too long (90 > 88 characters)
nexus/maintenance/new_story_setup.py:818:89: E501 line too long (116 > 88 characters)
nexus/runtime/slot_operations.py:300:89: E501 line too long (179 > 88 characters)
nexus/runtime/slot_operations.py:315:89: E501 line too long (183 > 88 characters)
nexus/runtime/slot_operations.py:343:89: E501 line too long (179 > 88 characters)
nexus/runtime/slot_operations.py:477:89: E501 line too long (163 > 88 characters)

$ flake8 <origin/main copies>      # base
nexus/api/db_pool.py:28:1: F401 'nexus.database.database_url' imported but unused
scripts/migrate.py:181:89: E501 line too long (94 > 88 characters)
scripts/migrate.py:202:89: E501 line too long (99 > 88 characters)
scripts/migrate.py:206:89: E501 line too long (92 > 88 characters)
scripts/new_story_setup.py:7:89: E501 line too long (101 > 88 characters)
scripts/new_story_setup.py:53:89: E501 line too long (90 > 88 characters)
scripts/new_story_setup.py:66:89: E501 line too long (91 > 88 characters)
scripts/new_story_setup.py:105:89: E501 line too long (101 > 88 characters)
scripts/new_story_setup.py:233:89: E501 line too long (96 > 88 characters)
scripts/new_story_setup.py:360:89: E501 line too long (90 > 88 characters)
scripts/new_story_setup.py:642:89: E501 line too long (116 > 88 characters)

$ PYTHONPATH=$PWD $PY -m mypy --explicit-package-bases <files>    # HEAD
nexus/api/db_pool.py:96: error: Item "None" of "APISettings | None" has no attribute "database"  [union-attr]
nexus/api/db_pool.py:99: error: "ThreadedConnectionPool" has no attribute "_kwargs"  [attr-defined]
nexus/api/db_pool.py:158: error: Item "None" of "APISettings | None" has no attribute "database"  [union-attr]
Found 3 errors in 1 file (checked 8 source files)

$ PYTHONPATH=$PWD $PY -m mypy --explicit-package-bases <origin/main copies>   # base
nexus/api/db_pool.py:94: error: Item "None" of "APISettings | None" has no attribute "database"  [union-attr]
nexus/api/db_pool.py:97: error: "ThreadedConnectionPool" has no attribute "_kwargs"  [attr-defined]
nexus/api/db_pool.py:156: error: Item "None" of "APISettings | None" has no attribute "database"  [union-attr]
Found 3 errors in 1 file (checked 5 source files)

$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

Pre-existing diagnostics: the F401, the eleven moved E501 lines (same lengths as
on `origin/main`) and the three mypy errors in `nexus/api/db_pool.py` (lines
96, 99 and 158 at HEAD; 94, 97 and 156 on the base), none on a line this lane
changed. Accepted new diagnostics: the four E501 marker lines in
`nexus/runtime/slot_operations.py` (300, 315, 343, 477). The marker regex is
`\Z`-anchored and is read only from the header-colon line, so the order's exact
text cannot be wrapped or followed by `# noqa`.

### Read-Only Fleet Facts (2026-10-13, Tree `933992b5`)

```sh
for db in NEXUS_template save_01 save_02 save_03 save_04 save_05; do
  PGOPTIONS='-c default_transaction_read_only=on' psql -d $db -AtF' | ' -c "SELECT current_database(), (SELECT count(*) FROM schema_migrations), (SELECT max(version) FROM schema_migrations), (SELECT slot_number FROM global_variables WHERE id = TRUE), (SELECT string_agg(corpus_kind || '=' || analyzer_version, ', ' ORDER BY corpus_kind) FROM memory_idf_corpora), (SELECT max(id) FROM narrative_chunks), current_setting('server_version_num')"
done
```

```text
NEXUS_template | 145 | 148 |  | narrative=pg_catalog.english/v1/170011, retrograde_summary=pg_catalog.english/v1/170011 |  | 170011
save_01 | 145 | 148 |  | narrative=pg_catalog.english/v1/170011, retrograde_summary=pg_catalog.english/v1/170011 | 1425 | 170011
save_02 | 145 | 148 |  | narrative=pg_catalog.english/v1/170011, retrograde_summary=pg_catalog.english/v1/170011 | 1425 | 170011
save_03 | 145 | 148 |  | narrative=pg_catalog.english/v1/170011, retrograde_summary=pg_catalog.english/v1/170011 | 100 | 170011
save_04 | 145 | 148 | 4 | narrative=pg_catalog.english/v1/170011, retrograde_summary=pg_catalog.english/v1/170011 | 49 | 170011
save_05 | 145 | 148 |  | narrative=pg_catalog.english/v1/170011, retrograde_summary=pg_catalog.english/v1/170011 |  | 170011
```

A read-only Python probe (each session opened with
`options='-c default_transaction_read_only=on'` and `set_session(readonly=True)`,
then rolled back) compared each database's stamps with `discover_migrations()`
and ran `parse_pass2_baseline` and `incompatible_pass2_baseline_reason` on each
slot's tail under today's settings:

```text
on-disk versions: 148 max 151 script-only ['008']
NEXUS_template: stamps missing=['149', '150', '151'] unknown=[]
save_01: stamps missing=['149', '150', '151'] unknown=[]; tail 1425: schema 1, parent 1425, compat reason=None
save_02: stamps missing=['149', '150', '151'] unknown=[]; tail 1425: schema 1, parent 1425, compat reason=None
save_03: stamps missing=['149', '150', '151'] unknown=[]; tail 100: schema 1, parent 100, compat reason=None
save_04: stamps missing=['149', '150', '151'] unknown=[]; tail 49: schema 1, parent 49, compat reason=None
save_05: stamps missing=['149', '150', '151'] unknown=[]
```

So every database lacks only the wave-B migrations 149-151, which a staging
build applies inside staging (fleet application is the coordinator's step); only
`save_04` holds a `slot_number` (4); every tail baseline is schema 1 with the
right parent and no compatibility reason; every IDF corpus carries the live key
`pg_catalog.english/v1/170011`. `scripts/replay_state.py --verify` was not run
against the owner's slots for this record.

### Coordinator's Steps

- The whole-tree PostgreSQL gate.
- Fleet and template migrations (149-151 on this tree).
- The state-surface regeneration (this lane changes no `ui/` file).
- The optional owner-host smoke (`--stage --mode clone --source save_02`, then
  `--sweep-staging`) and the gateway restart that loads the changed setup and
  maintenance modules.
