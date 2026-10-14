# 811 Runtime Module Move: Source Checkpoint

Status: Codex authored the implementation, caller adaptations and guard tests on
the lane source and ran no proof there. The wave-B fixer ran the order's proof on
the integrated wave-B tree on 2026-10-13; the commands and tails are under
[Integrated-Tree Proof (2026-10-13)](#integrated-tree-proof-2026-10-13). The
whole-tree gate, the paid summary proof and fleet work remain the coordinator's
steps.

Source base: `a8cc15c43bf33cf370cd07567604980152db1318`, the committed 823
journal/staging prerequisite. Its main merge base is
`4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`. The frozen 811-S3a order and
coordinator's staging/runtime-move refresh govern this slice. The order requires
four restoring controls after implementation; it does not require an initial
unchanged-product red run.

## Mechanical Move and Compatibility

The four implementations move whole: migration, setup and target-name boundaries
to `nexus/maintenance`, and narrative summary generation to `nexus/jobs`.
The [bounded diff](bounded-move.diff) compares each new file to its original at
the source base. The lane recorded no command for its AST comparison. The
integrated-tree proof below records one: against the originals at `a4842c66`,
the only statement-level differences are the ordered import, bootstrap and
`MIGRATIONS_DIR` adaptations, plus the fixer's refusal-message change in
`discover_migrations`. Disposition comments and Black do not change the AST. Logger names, command examples and main
blocks remain intact. The summary provider shim import remains as ordered.

The original paths are deliberate re-export wrappers. Their AST-derived export
counts are **23 / 27 / 2 / 12**, respectively; private exports are retained and
import-only names are excluded. Wrappers document that assigning a wrapper name
does not change an implementation binding. Commands retain their original
bootstrap and main blocks; no forwarding proxy or new console script is added.
No runtime path imports one of these four wrappers.

The [source inventory](source-inventory.json) records all 66 import-site edits and
all **44 actual test importers** at the prerequisite: the previously measured 42
plus the two 823 test modules. Runtime lazy imports remain lazy. Script module
objects in the benchmark and identity backfill now name the implementation,
preserving assignment/patch behavior. Mixed imports are split while unrelated
script imports remain. Operator-only named imports retain their compatibility
wrappers, command subprocess paths remain `scripts/...`, and the logging probe
keeps both the implementation and wrapper imports.

One recorded predecessor adaptation is essential: 823 made the IDF rebuild
script production reachable. Its two named imports of migration/target helpers
therefore also move to `nexus.maintenance`; leaving them on wrappers would keep
two wrappers in the production closure. Its ambiguous-commit handling and all
journal/maintenance/staging behavior remain unchanged.

The four DDL allowlist paths and the planted setup path now follow the moved
implementations, retaining 823's `_build_from_template` and `_restore_clone`
function names and all existing reasons/rules. The three prompt-lint paths move
with the summary module. Routing imports target implementations; the three
command wrappers join the existing command-import logging guard.

Exactly **18** surviving path-keyed exception entries are removed and their
existing contracts marked on the moved handler headers. 823 already removed the
two temporary-dump cleanup handlers counted in the frozen order's 20. No entry
is added, no marker includes a `noqa` suffix, and no swallowing behavior changes.
The integrated-tree proof below records the delta: `git diff a4842c66 7f2d36ad --
config/exception_disposition_baseline.json` deletes 18 entries and adds none.

## Source Checks

The lane recorded no Black command or output. On the integrated tree,
`black --check` over the 69 changed Python files leaves every file unchanged
(command and tail below). The permitted source reachability generator
produced [this result](source-reachability.txt), with every finding list empty.
It explicitly does not prove route reachability.

```sh
PYTHONPATH="$PWD" nice -n 15 "$PY" -S scripts/check_reachability.py \
  --write-baseline \
  --reason '#811 S3a: migrate, new_story_setup and database_targets move into nexus/maintenance and summarize_narrative into nexus/jobs; the scripts/ wrappers become operator paths'
```

The baseline delta is exactly five new production paths (the maintenance package
and four implementation modules), four removed script wrappers, and the reason;
the unreachable set is unchanged. No additional discovery exemption is added.
The new wrapper test uses literal `importlib.import_module` calls so its imports
remain visible to source analysis. [Operator explanations](wrapper-operator-chains.json)
show each wrapper's actual root: its own main for the three commands, and the
Natural Earth loader for `database_targets`.

The lane's normal-hook results are not recorded in this file. The flake8 and
mypy comparisons, the reachability exit code and the four wrapper explanations
are recorded on the integrated tree below.

The [canonical closure](canonical-source-closure.json) is AGENTS, turn-flow and
decisions 0010/0040. Seat precedence, scheduling and test-fixture behavior remain
the same; quoted rulings, statuses and document bodies stay intact. 0040's source
follows `new_story_setup` into its implementation path. The first three stamps
advance to the source merge base; 0040 already carries that stamp from 823 and
was reverified. Recompute after the final normal merge with current main. The
[closure](canonical-source-closure.json) still cites the lane-time stamp
`4ae8b8d2`; the wave-B assembly moved all four `verified_commit` stamps to
`f073b371`, and `tests/test_doc_front_matter.py` passes on this tree (focused
set below).

## Integrated-Tree Proof (2026-10-13)

Every command below ran on branch `claude/waveb-fix-811-s3a` at `355092c1`
(integration head `7eb9a10c` plus the six fixer commits `e8d15c9e`, `adfbbab6`,
`3484fa61`, `529a8fa9`, `d0b6bef6`, `355092c1`), from the worktree root unless a
step says otherwise. The commit that records this file changes only evidence
files. `$PY` is `/Users/pythagor/nexus/.venv/bin/python`; every test run
unsets `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT`. Scratch files live
in the session scratchpad under `fix-waveb-r2-811-S3a/`.

### Fixes Applied by the Fixer

- `tests/test_runtime/test_init_plan_pg.py:23` and
  `tests/test_orrery/test_place_point_required_pg.py:11` bind
  `from nexus.maintenance import migrate` (`e8d15c9e`). The init-plan
  monkeypatches of `TEMPLATE_DB` now reach the binding readiness reads: the
  `api_runtime` run below reaches only `qa640_803s6_*` stand-ins and reports
  `owner targets: none`.
- The rewritten `nexus.maintenance` test imports sit above `from scripts ...` in
  their local group, and paired imports are merged into
  `from nexus.maintenance import migrate, new_story_setup` (`adfbbab6`).
- `discover_migrations` names `nexus/maintenance/migrate.py` in its refusal
  message (`3484fa61`).
- `test_wrapper_reexports_every_defined_name` also requires exactly one import
  from the implementation whose names equal the expected set (`529a8fa9`), and
  its two findings lists carry annotations for mypy (`355092c1`).
- [focused-selectors.json](focused-selectors.json) is recomputed from the
  integrated diff (`d0b6bef6`) and now also lists
  `tests/test_prose_metrics_pg.py`, which runs `scripts/migrate.py` (order
  item 6).

Importer rescan, as the finding gives it:

```sh
git grep -nP "from scripts import .*\b(migrate|new_story_setup|database_targets|summarize_narrative)\b|import scripts\.(migrate|new_story_setup|database_targets|summarize_narrative)" -- tests scripts
```

```text
tests/test_reachability.py:765:        "    import scripts.shared\n    import scripts.migrate\n",
tests/test_reachability.py:834:                "    import scripts.migrate\n",
tests/test_runtime/test_logging_config.py:468:import scripts.summarize_narrative
```

All three hits are source held in strings: the two fixtures of
`tests/test_reachability.py` and the `IMPORT_PROBE` string of
`tests/test_runtime/test_logging_config.py` (order item 6 keeps that probe line). The guard
test treats them as not imports, and it passes below.

Import path: `PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'`
printed `/Users/pythagor/nexus/.claude/worktrees/fix-811-s3a/nexus/__init__.py`.

### Guard Tests Offline

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_script_wrappers.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
9 passed, 5 warnings in 3.93s
```

### Red Runs

Script `plants.sh` (zsh), run as `plants.sh 2>&1 | tee plants.log`:

```sh
#!/bin/zsh
# Red-run plants for 811-S3a; each plant applied, tested, restored byte for byte.
cd /Users/pythagor/nexus/.claude/worktrees/fix-811-s3a || exit 2
PY=/Users/pythagor/nexus/.venv/bin/python
run() {
  local name="$1" target="$2"
  echo "=== PLANT $name ($target) on $(git rev-parse --short HEAD)"
  git diff --stat -- "$target"
  env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rf tests/test_script_wrappers.py 2>&1 | grep -E '^(FAILED|E  |secret-store|[0-9]+ (passed|failed))' | cut -c1-240 | tail -12
  git checkout -- "$target"
  git diff --quiet -- "$target" && echo "RESTORED: git diff --quiet -- $target exit 0"
}
sed -i '' -e '/^    _postgres_tools,$/d' -e '/^    "_postgres_tools",$/d' scripts/new_story_setup.py
run 1-drop-postgres-tools scripts/new_story_setup.py
sed -i '' -e '350s/from nexus.maintenance import migrate/from scripts import migrate/' nexus/runtime/readiness.py
run 2-readiness-wrapper-import nexus/runtime/readiness.py
sed -i '' -e '26s/^from nexus.maintenance import new_story_setup/from scripts import new_story_setup/' scripts/benchmark_experience_enqueue_fence.py
run 3-benchmark-wrapper-module scripts/benchmark_experience_enqueue_fence.py
sed -i '' -e '/^if __name__ == "__main__":$/,$d' scripts/migrate.py
run 4-migrate-wrapper-main scripts/migrate.py
echo "=== FINAL git status"; git status --short
```

A first attempt named the function's variable `path`. In zsh that variable is
tied to `PATH`, so `git` and `grep` were not found: the four plants were applied
and nothing ran. `git checkout --` on the four files and `git diff --quiet`
(exit 0, `clean`) restored them before the rerun below. No test ran on that
attempt.

```text
=== PLANT 1-drop-postgres-tools (scripts/new_story_setup.py) on 355092c1
 scripts/new_story_setup.py | 2 --
 1 file changed, 2 deletions(-)
E       AssertionError: assert ['LOG', 'TEMP...emplate', ...] == ['LOG', 'TEMP...emplate', ...]
E         
E         At index 13 diff: '_refuse_locked_target' != '_postgres_tools'
E         Right contains one more item: 'stage_slot_from_template'
E         Use -v to get more diff
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_script_wrappers.py::test_wrapper_reexports_every_defined_name[scripts.new_story_setup-nexus.maintenance.new_story_setup]
1 failed, 8 passed, 5 warnings in 4.31s
RESTORED: git diff --quiet -- scripts/new_story_setup.py exit 0
=== PLANT 2-readiness-wrapper-import (nexus/runtime/readiness.py) on 355092c1
 nexus/runtime/readiness.py | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
E       AssertionError: assert ['nexus/runti...iness.py:350'] == []
E         
E         Left contains one more item: 'nexus/runtime/readiness.py:350'
E         Use -v to get more diff
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_script_wrappers.py::test_runtime_imports_no_moved_script_module
1 failed, 8 passed, 5 warnings in 4.25s
RESTORED: git diff --quiet -- nexus/runtime/readiness.py exit 0
=== PLANT 3-benchmark-wrapper-module (scripts/benchmark_experience_enqueue_fence.py) on 355092c1
 scripts/benchmark_experience_enqueue_fence.py | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
E       AssertionError: assert ['scripts/ben..._fence.py:26'] == []
E         
E         Left contains one more item: 'scripts/benchmark_experience_enqueue_fence.py:26'
E         Use -v to get more diff
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
1 failed, 8 passed, 5 warnings in 4.21s
RESTORED: git diff --quiet -- scripts/benchmark_experience_enqueue_fence.py exit 0
=== PLANT 4-migrate-wrapper-main (scripts/migrate.py) on 355092c1
 scripts/migrate.py | 2 --
 1 file changed, 2 deletions(-)
E       AssertionError: assert 'usage:' in ''
E        +  where '' = <built-in method lower of str object at 0x103678a90>()
E        +    where <built-in method lower of str object at 0x103678a90> = ''.lower
E        +      where '' = CompletedProcess(args=['/Users/pythagor/nexus/.venv/bin/python', '/Users/pythagor/nexus/.claude/worktrees/fix-811-s3a/scripts/migrate.py', '--help'], returncode=0, stdout='', stderr='').stdout
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_script_wrappers.py::test_wrappers_run_as_commands[migrate]
1 failed, 8 passed, 5 warnings in 4.25s
RESTORED: git diff --quiet -- scripts/migrate.py exit 0
=== FINAL git status
```

Each plant fails exactly its own test, and the tree is clean afterward.

A fifth control covers the tightened export test (finding: an imported-only
name). Script `plant5.sh` inserts `get_connection,` after `_postgres_tools,` in
the setup wrapper's import list, which leaves `__all__` unchanged:

```sh
target=scripts/new_story_setup.py
sed -i '' -e 's/^    _postgres_tools,$/    _postgres_tools,\
    get_connection,/' $target
# then the same pytest, git checkout and git diff --quiet lines as plants.sh
```

```text
=== PLANT 5-imported-only-name (scripts/new_story_setup.py) on 355092c1
+    get_connection,
E       AssertionError: assert ['LOG', 'TEMP...emplate', ...] == ['LOG', 'TEMP...emplate', ...]
E         
E         At index 22 diff: 'get_connection' != 'initialize_slot_database'
E         Left contains one more item: 'stage_slot_from_template'
E         Use -v to get more diff
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_script_wrappers.py::test_wrapper_reexports_every_defined_name[scripts.new_story_setup-nexus.maintenance.new_story_setup]
1 failed, 8 passed, 5 warnings in 4.13s
RESTORED: git diff --quiet -- scripts/new_story_setup.py exit 0
```

### Focused PostgreSQL Proof

Script `pgrun.sh <label> <files...>`. Every run read `uptime` first and waited
in a bounded loop while the one-minute load was 24 or above (capped at 20
minutes). No run had to wait: each printed `load wait: 0s`.

```sh
#!/bin/bash
label="$1"; shift
S=<scratchpad>/fix-waveb-r2-811-S3a
cd /Users/pythagor/nexus/.claude/worktrees/fix-811-s3a || exit 2
echo "=== $label on $(git rev-parse --short HEAD) at $(date '+%H:%M:%S')"
echo "uptime: $(uptime)"
waited=0
until [ "$(sysctl -n vm.loadavg | awk '{print int($2)}')" -lt 24 ] || [ $waited -ge 1200 ]; do sleep 30; waited=$((waited+30)); done
echo "load wait: ${waited}s; load now: $(sysctl -n vm.loadavg)"
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD \
  nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -rs -p tests.dbname_audit "$@" > "$S/pg_$label.log" 2>&1
echo "pytest exit=$?"
```

The first run (`orrery`) used the same script before `-rs` was added, so its
eight skips carry no printed reason.

`orrery` (11:01, load 9.22): `test_acquisition_scan_pg`, `test_card_identity`,
`test_character_experiences_pg`, `test_claim_birth_coverage_pg`,
`test_experience_enqueue_gin_pg`, `test_geo_reference_pg`, `test_migrate`,
`test_migration_dead_strata_pg`, `test_narration_job_fencing_pg` (all under
`tests/test_orrery/`).

```text
pytest exit=0
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
709 passed, 8 skipped, 2 warnings in 4060.23s (1:07:40)
```

`orrery2` (12:09, load 18.10): `test_need_clock_anchor_pg`,
`test_place_point_required_pg`, `test_project_start_summary_orphans_migration_pg`,
`test_recall_disclosure_pg`, `test_retrograde_summary_migration_contract`,
`test_retrograde_summary_migration_pg`, `test_world_event_time_pg`.

```text
pytest exit=0
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
87 passed, 2 warnings in 85.56s (0:01:25)
```

`api_runtime` (12:11, load 23.17): `tests/test_api/` `test_benchmark_seat_jobs_pg`,
`test_maintenance_locked_pg`, `test_narrative_summary_paid_pg`,
`test_seat_policy_backfill_pg`, `test_wizard_messages_migration_pg`;
`tests/test_runtime/` `test_init_plan_pg`, `test_logging_config`,
`test_readiness`, `test_readiness_pg`.

```text
pytest exit=0
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 26 targets: postgres, qa640_1013_readiness_* x2, qa640_776_hosted_*, qa640_776_uuid_*, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slo…
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [1] tests/test_api/test_narrative_summary_paid_pg.py: Requires explicit two-call summary authorization
112 passed, 1 skipped, 5 warnings in 91.65s (0:01:31)
```

`rest_a` (12:13, load 16.08): `test_character_relationship_id_types_pg`,
`test_chunk_entity_references_pg`, `test_chunk_lifecycle_columns_migration_pg`,
`test_commit_choice_presence_pg`, `test_connection_lifecycle`,
`test_database_contract`, `test_doc_front_matter`, `test_new_story_cache`,
`test_new_story_setup`, `test_new_story_setup_config`,
`test_pg_fixtures_corpus_clone`, `test_player_identity_consumers_pg`,
`test_postgres_tools`, `test_prompt_lint`, `test_prose_metrics`.

```text
pytest exit=0
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner server: local:5432
dbname audit: owner names admitted on registered clusters: save_04@local:53912 (psycopg2), save_04@local:53913 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [4] tests/test_chunk_entity_references_pg.py:585: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [3] tests/test_pg_fixtures_corpus_clone.py: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
204 passed, 7 skipped, 2 warnings in 151.66s (0:02:31)
```

`rest_b` (12:15, load 20.70): `test_prose_metrics_pg`, `test_reachability`,
`test_rebuild_memory_idf_pg`, `test_record_revelation_cli_pg`,
`test_relationship_entity_ids_pg`, `test_scheduler_helpers_routing`,
`test_schema_documentation_pg`, `test_schema_ownership`, `test_script_wrappers`,
`test_slot_operations_journal`, `test_slot_operations_pg`,
`test_slot_routed_entrypoints`, `test_story_identity_pg`, `test_summary_triggers`,
`test_unowned_index_adoption_pg`, `test_wizard_opening_presence_pg`,
`test_world_clock_contract_pg`.

```text
pytest exit=1
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [4] tests/test_relationship_entity_ids_pg.py:414: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
2 failed, 295 passed, 4 skipped, 4 warnings in 500.36s (0:08:20)
```

The two failures are both in `tests/test_relationship_entity_ids_pg.py`, a file
from the 836-S6a lane that the 811 assembly touched only by its import line:

```text
tests/test_relationship_entity_ids_pg.py::test_entity_ids_cannot_diverge
E   psycopg2.errors.NotNullViolation: null value in column "emotional_valence" of relation "character_relationships" violates not-null constraint
tests/test_relationship_entity_ids_pg.py:250: NotNullViolation
tests/test_relationship_entity_ids_pg.py::test_migration_151_refuses_stale_ledger
tests/test_orrery/test_need_clock_anchor_pg.py:292: in _build_story_transition -> nexus/api/new_story_cache.py:1492 write_cache -> nexus/api/slot_utils.py:118
E   ValueError: Invalid database name: 'qa640_836s6a_b80eb713de5c'. Must be one of: save_01, save_02, save_03, save_04, save_05
```

Neither failing line touches `migrate`. The file alone, rerun on this tree
(`pgrun.sh relids_rerun tests/test_relationship_entity_ids_pg.py`, 12:24, load
8.21):

```text
pytest exit=1
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
2 failed, 5 passed, 4 skipped in 19.21s
```

The same file on the pre-811 integration point `a4842c66`, where it still binds
`from scripts import migrate`, run from a `git archive a4842c66` extraction in
the scratchpad (`nexus`, `scripts`, `tests`, `config`, `prompts`, `migrations`,
`docs`, `data`, `nexus.toml`, `pytest.ini`, `pyproject.toml`; `nexus.__file__`
printed the extraction):

```sh
cd <scratchpad>/fix-waveb-r2-811-S3a/base && env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_relationship_entity_ids_pg.py
```

```text
E               psycopg2.errors.NotNullViolation: null value in column "emotional_valence" of relation "character_relationships" violates not-null constraint
E               ValueError: Invalid database name: 'qa640_836s6a_06a1c0f5734e'. Must be one of: save_01, save_02, save_03, save_04, save_05
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
2 failed, 5 passed, 4 skipped in 20.79s
```

So both failures were already present before the 811 merge. They belong to the
836-S6a lane and are reported to the coordinator; this lane does not fix them.

Every other file of the focused set passes, including
`tests/test_orrery/test_card_identity.py`, `tests/test_connection_lifecycle.py`,
`tests/test_doc_front_matter.py`, `tests/test_reachability.py` and both importers
the assembly rewrote (`tests/test_api/test_wizard_messages_migration_pg.py`,
`tests/test_relationship_entity_ids_pg.py` apart from the two failures above).
The paid summary importer skips with live flags unset; its proof is the
coordinator's step.

### Read-Only Owner Probes

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PGOPTIONS='-c default_transaction_read_only=on' PYTHONPATH=$PWD nice -n 15 $PY scripts/migrate.py --status > migrate_status.log 2>&1   # exit=0
```

First line, then every line that is not an applied `[x]` row:

```text
Found 148 managed migrations in /Users/pythagor/nexus/.claude/worktrees/fix-811-s3a/migrations

NEXUS_template:
  [ ] 149_place_point_required
  [ ] 150_wizard_messages
  [ ] 151_relationship_entity_ids

save_01: [LOCKED]
  (locked - use --write-locked-slot to apply migrations)
save_02:
  [ ] 149_place_point_required
  [ ] 150_wizard_messages
  [ ] 151_relationship_entity_ids
(save_03, save_04 and save_05 list the same three pending migrations)
```

The first line names this worktree's `migrations/`, so
`MIGRATIONS_DIR = Path(__file__).parents[2] / "migrations"` resolves to the
repository root. Migrations 149 to 151 belong to other wave-B lanes; the fleet
application is the coordinator's step.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PGOPTIONS='-c default_transaction_read_only=on' PYTHONPATH=$PWD nice -n 15 $PY scripts/rebuild_memory_idf.py --all --dry-run > idf_dryrun.log 2>&1   # exit=0
```

```text
WARNING Database save_01 is LOCKED (read-only), skipping; rerun with --write-locked-slot to rebuild it
NEXUS_template: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 0 (source 0)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 0 (source 0)
save_01: skipped_locked [LOCKED]
save_02: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 1425 (source 1425)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 0 (source 0)
save_03: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 39 (source 39)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 18 (source 18)
save_04: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 45 (source 45)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 27 (source 27)
save_05: dry_run (server pg_catalog.english/v1/170011)
  narrative: key pg_catalog.english/v1/170011, documents 0 (source 0)
  retrograde_summary: key pg_catalog.english/v1/170011, documents 0 (source 0)
```

### Import Smoke From a Foreign Directory

```sh
D=$(mktemp -d) && cd $D && env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/fix-811-s3a nice -n 15 $PY <scratchpad>/import_smoke.py /Users/pythagor/nexus/.claude/worktrees/fix-811-s3a   # exit=0
```

```python
import importlib, pathlib, sys
import nexus
root = pathlib.Path(sys.argv[1])
names = sorted(f"scripts.qa_shift.{p.stem}" for p in (root / "scripts/qa_shift").glob("*.py") if p.stem != "__init__")
names += [f"scripts.{n}" for n in ("rebuild_memory_idf", "stamp_lore_pass_baseline", "entity_reference_parity", "benchmark_experience_enqueue_fence", "backfill_story_identity", "load_natural_earth", "migrate", "new_story_setup", "database_targets", "summarize_narrative")]
names += ["nexus.maintenance.migrate", "nexus.maintenance.new_story_setup", "nexus.maintenance.database_targets", "nexus.jobs.summarize_narrative"]
for name in names:
    module = importlib.import_module(name)
    assert str(pathlib.Path(module.__file__).resolve()).startswith(str(root)), module.__file__
    print("ok", name)
print("nexus.__file__", nexus.__file__)
print("imported", len(names))
```

```text
ok scripts.qa_shift.ann_gate
... (17 qa_shift modules, all ok)
ok scripts.rebuild_memory_idf
ok scripts.stamp_lore_pass_baseline
ok scripts.entity_reference_parity
ok scripts.benchmark_experience_enqueue_fence
ok scripts.backfill_story_identity
ok scripts.load_natural_earth
ok scripts.migrate
ok scripts.new_story_setup
ok scripts.database_targets
ok scripts.summarize_narrative
ok nexus.maintenance.migrate
ok nexus.maintenance.new_story_setup
ok nexus.maintenance.database_targets
ok nexus.jobs.summarize_narrative
nexus.__file__ /Users/pythagor/nexus/.claude/worktrees/fix-811-s3a/nexus/__init__.py
imported 31
```

`scripts/measure_place_coordinate_costs.py`, an importer the order names, is
absent from this tree: the 840-S2 lane deleted it (`ed5ce5a4`, "Require
authored coordinates for new places"). The first smoke attempt listed it and
stopped with `ModuleNotFoundError`; the run above omits it.

### Static Checks

The changed Python files are the union of
`git diff --name-only --diff-filter=AMR a4842c66 7f2d36ad` and
`git diff --name-only --diff-filter=AMR 7eb9a10c HEAD`, filtered to `*.py`: 69
files. No later wave-B lane touched any of them between `7f2d36ad` and
`7eb9a10c`. The comparison base is `git archive a4842c66` (the integration
point before the 811 merge) extracted into the scratchpad; each moved module is
compared with its `scripts/` original there.

```sh
nice -n 15 $PY -m black --check $(cat changed_py.txt)
```

```text
All done! ✨ 🍰 ✨
69 files would be left unchanged.
```

flake8, compared by (code, source-line text) multiset per file
(`flake8_multiset.py <worktree> <base> changed_py.txt`; it runs
`$PY -m flake8 <file>` in each tree, keys each diagnostic on its code and the
stripped source line, and prints head minus base):

```text
files=69 head_diagnostics=209 base_diagnostics=343 new=0
```

Per moved module (`$PY -m flake8 <file> | awk '{print $2}' | sort | uniq -c`):

```text
nexus/maintenance/migrate.py head:[ 3 E501 ] | base scripts/migrate.py:[ 3 E501 ] | wrapper scripts/migrate.py diagnostics: 0
nexus/maintenance/new_story_setup.py head:[ 7 E501 ] | base scripts/new_story_setup.py:[ 7 E501 ] | wrapper scripts/new_story_setup.py diagnostics: 1
nexus/maintenance/database_targets.py head:[] | base scripts/database_targets.py:[] | wrapper scripts/database_targets.py diagnostics: 0
nexus/jobs/summarize_narrative.py head:[ 3 E402 66 E501 1 F841 47 W291 ] | base scripts/summarize_narrative.py:[ 7 E402 66 E501 1 F841 47 W291 ] | wrapper scripts/summarize_narrative.py diagnostics: 0
```

The setup wrapper's one diagnostic is `scripts/new_story_setup.py:7:89: E501
line too long (101 > 88 characters)`, a line of the original docstring that
order item 3 keeps verbatim; the original carries the same diagnostic.

mypy, the sanctioned invocation, on head and on the base versions (63 of the 69
paths exist at the base; the six new files have none):

```sh
PYTHONPATH=$PWD nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratchpad>/mypy-head-cache $(cat changed_py.txt)
cd <base> && PYTHONPATH=$PWD nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratchpad>/mypy-base-cache $(cat base_py.txt)
```

```text
head: Found 74 errors in 16 files (checked 69 source files)
base: Found 79 errors in 16 files (checked 63 source files)
```

Compared by (file, message, source-line text) multiset with moved paths mapped
(`mypy_multiset.py`):

```text
head_errors=74 base_errors=79 new=0 gone=5
GONE 1 tests/test_database_contract.py Skipping analyzing "ir_eval.engine.run_executor": module is installed, but missing library stubs or
GONE 1 tests/test_database_contract.py Skipping analyzing "ir_eval.engine.storage": module is installed, but missing library stubs or py.ty
GONE 1 tests/test_database_contract.py Skipping analyzing "ir_eval.import_golden_queries": module is installed, but missing library stubs o
GONE 1 tests/test_database_contract.py Skipping analyzing "ir_eval.pg_db": module is installed, but missing library stubs or py.typed marke
GONE 1 tests/test_database_contract.py Skipping analyzing "ir_eval.runner": module is installed, but missing library stubs or py.typed marke
```

The five "gone" errors are an artifact of the extraction, which has no
`ir_eval/` directory, so mypy resolved the installed package there. No
diagnostic is new. The 74 head errors are pre-existing ones on untouched lines
(for example `tests/test_connection_lifecycle.py:257-258 [index]`).

AST comparison of each moved module with its original (`ast_compare.py`: the
`ast.dump` of every simple statement, compared with `difflib`):

```text
== scripts/migrate.py -> nexus/maintenance/migrate.py: 7 differing simple statements
  -Expr(... sys.path.insert ...)
  -ImportFrom(module='scripts.database_targets', names=[alias(name='evaluation_dbname')], level=0)
  +ImportFrom(module='nexus.maintenance.database_targets', names=[alias(name='evaluation_dbname')], level=0)
  -Assign(targets=[Name(id='MIGRATIONS_DIR', ...)], value=BinOp(left=Attribute(... Path(__file__).parent.parent ...
  +Assign(targets=[Name(id='MIGRATIONS_DIR', ...)], value=BinOp(left=Subscript(... Path(__file__).parents[2] ...
  -Raise(exc=Call(func=Name(id='RuntimeError'), ... 'Python migration ' ...   (refusal message, scripts/migrate.py)
  +Raise(exc=Call(func=Name(id='RuntimeError'), ... 'Python migration ' ...   (refusal message, nexus/maintenance/migrate.py)
== scripts/new_story_setup.py -> nexus/maintenance/new_story_setup.py: 2 differing simple statements
  -ImportFrom(module='scripts.migrate', names=[alias(name='migrate_database')], level=0)
  +ImportFrom(module='nexus.maintenance.migrate', names=[alias(name='migrate_database')], level=0)
== scripts/database_targets.py -> nexus/maintenance/database_targets.py: 0 differing simple statements
== scripts/summarize_narrative.py -> nexus/jobs/summarize_narrative.py: 3 differing simple statements
  -Import(names=[alias(name='os')])
  -Assign(targets=[Name(id='parent_dir', ...)], ...)
  -Expr(... sys.path.insert(0, parent_dir) ...)
```

(Long dumps abbreviated with `...`; the full lines are in the scratchpad's
command output.)

### Lints and Reachability

```sh
PYTHONPATH=$PWD nice -n 15 $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main   # exit=0
```

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

`git diff a4842c66 7f2d36ad -- config/exception_disposition_baseline.json`: 18
deleted lines, 0 added. The deleted keys are 2 `scripts/migrate.py`
(`apply_migration`, `show_status`), 2 `scripts/new_story_setup.py`
(`<module>`, `_copy_template_data`) and 14 `scripts/summarize_narrative.py`.

```sh
PYTHONPATH=$PWD nice -n 15 $PY scripts/check_reachability.py   # exit=0, every finding list empty, "route_reachability": "not_proven"
```

`git diff a4842c66 7f2d36ad -- config/reachability_baseline.json` adds the five
`nexus/` paths (`nexus/jobs/summarize_narrative.py`,
`nexus/maintenance/__init__.py`, `database_targets.py`, `migrate.py`,
`new_story_setup.py`), removes the four `scripts/` wrappers and changes the
reason; `scripts/replay_state.py` shows only as a trailing-comma line change.

Operator chains, one per wrapper:
`PYTHONPATH=$PWD nice -n 15 $PY scripts/check_reachability.py --explain <wrapper> --kind operator` (each exit=0):

```text
scripts/migrate.py reachable=True root=scripts/migrate.py:main
scripts/new_story_setup.py reachable=True root=scripts/new_story_setup.py:main
scripts/database_targets.py reachable=True root=scripts/load_natural_earth.py:main
scripts/summarize_narrative.py reachable=True root=scripts/summarize_narrative.py:main
```

### Coordinator's Steps

- The whole-tree PostgreSQL gate and the order's two whole offline suites
  (`tests --ignore=tests/test_api --ignore=tests/test_orrery`,
  `tests/test_api tests/test_orrery`).
- The paid summary proof (`tests/test_api/test_narrative_summary_paid_pg.py`
  skipped here with live flags unset).
- Fleet migrations (149 to 151 belong to other lanes) and the template.
- The installed-main import smoke at landing, the gateway restart owed when
  services run again, and the state-surface regeneration (no UI change here).
- The two `tests/test_relationship_entity_ids_pg.py` failures, which predate the
  811 merge, go to the 836-S6a lane.

## Predecessors and Landing

This branch preserves the committed 823 journal, validated maintenance targets,
identity lifecycle, current Natural Earth seed inventory, ir_eval schema copying,
asset-DDL refusal and all current command behavior. Later 809 fresh-NULL pin
changes must be ported into the moved setup implementation and its wrapper export
set; take the ordered deletion of `test_new_story_setup_config.py`. Do not restore
the old setup snapshot or remove new staging helpers while resolving conflicts.
Apply future changes from any still-edited `scripts` source to its implementation,
restore the wrapper, rescan importers and rerun the guards after each merge.

This slice adds no migration and performs no fleet work. Migrations 149/150/151
remain owned by their existing lanes. No `poetry install`, package-list change,
provider-shim relocation, UI rebuild or state-surface capture is included.
Owner services stay stopped; the next authorized startup must load the moved
code. The installed-main import smoke belongs to landing, after the paths exist
in the main checkout. Eventual publication says `Refs #811`; unrelated owner
questions remain outside scope.

Codex — GPT-6
