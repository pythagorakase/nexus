# TEST Provider Database Isolation — Verification

Verified 2026-10-08 on `claude/816-test-provider-database`, resumed from Claude's
saved WIP `25d6a01a`. Merge base / fetched `origin/main` is
`afd034f360e625f8bc4ffa8a717dda28422b19c7`; `git merge origin/main` reported
`Already up to date.` This completes 816-Q3 and 816-Q4 from the
[September 30 decisions](https://github.com/pythagorakase/nexus/issues/816#issuecomment-5915949753).
Refs #816; Q1/Q2 and the CI tiers remain outside this slice.

## Behavior and Source Evidence

- The old provider hardcoded `MOCK_DB = "mock"`; two singleton readers returned
  `{}` and cached bootstrap returned `[TEST MODE] No mock data available` when
  rows were absent. The production wizard consumes these same readers in
  process (`nexus/api/wizard_chat.py:730`).
- The new route is `[api.test_provider] database` (`nexus.toml:232`), default
  `mock`, with validated `NEXUS_TEST_PROVIDER_DATABASE` overlay
  (`nexus/config/loader.py:40`, `:305`). `APITestProviderSettings`
  (`nexus/config/settings_models.py:3985`) rejects an empty value, `save_NN`,
  and `NEXUS_template` before connection. It accepts `mock` and disposable names.
- `nexus/api/mock_openai.py:78` connects to the configured database. Readers
  (`:101`, `:138`, `:155`) raise a `RuntimeError` naming the actual database,
  missing table, and explicit `--dbname` seeding command. Cached bootstrap
  (`:1096`) propagates that error. No non-data TEST fallback was changed.
- `migrations/008_populate_mock_database.py:439` exposes the production seeder:
  validate before connecting, use `connection_kwargs`, load the unchanged
  JSON fixture, run all four populate steps in one transaction, commit once,
  roll back and propagate every failure, and close the connection. The CLI
  (`:462`) takes `--dbname`, defaulting to the configured provider database.
- Tests unconditionally start on the never-created
  `qa640_816_test_provider_unrouted` (`tests/conftest.py:52`); an unrouted parent
  or child read fails instead of reaching `mock`. The routed function fixture
  (`:202`) uses the production seeder through
  `disposable_test_provider_database` (`tests/pg_fixtures.py:451`) and the
  owner-refusing environment route helper (`:473`). The seeder's two dynamic
  imports are registered in `config/reachability.toml:178` and `:184`; the
  existing `008:main` operator root remains at `:137`.
- `mock` is protected independently by the runtime dbname audit
  (`tests/dbname_audit.py:103`), the AST owner-target guard
  (`tests/test_owner_target_guard.py:63`), and shared seed/route refusal
  (`tests/pg_fixtures.py:421`). Owner-refusal tables cover both new experience
  seeds in `tests/test_pg_disposable_target.py`.
- Shared `ExperienceCandidatesSeed` / `ExperienceRenderJobSeed`
  (`tests/pg_fixtures.py:2859`) describe the new seed results.
  `seed_experience_candidates` (`:2926`) requires a clock, inserts the scene,
  actors and event roles, and runs the production experience sweep.
  `seed_experience_render_job` (`:2994`) queues through the production scene
  enqueue path and reads the resulting job. Chunk times come from the save's
  `base_timestamp`. Four private-builder callers now use this shared seed;
  the other direct builders remain unchanged.

## 008 Current-Schema Fixes and Owner Decision

1. The selected fixture trait `reputation` matches canonical `fame` through
   `canonical_trait_name`; rationale lookup keeps the fixture spelling
   (`008:100`). The fixture JSON is unchanged.
2. After the character/layer truncations, the base clock is written before
   character insertion (`008:244`). The remaining story settings update the
   singleton (`:324`) instead of deleting the clock-bearing row. This satisfies
   the real character need-clock trigger on current schema.
3. The retired `assets.save_slots` write is removed. `populate_save_slot`
   (`008:430`) asserts the singleton update and pins
   `StorySettings(skald_model="TEST", gaia_model=None)` through
   `write_story_settings`, which writes the current story model column.

The coordinator explicitly received the owner's approval on October 8:
**“Keep the planned change; seed current-schema databases with an explicit
--dbname.”** The compatibility decision is resolved; legacy support is not
added. With unchanged default configuration, the old bare 008 command still
selects `mock`, but the owner's legacy database lacks canonical `fame` and the
`global_variables.model` column. It will raise and roll back, so operators seed
a current-schema database with an explicit target instead.

Read-only owner inspection used:

```sh
PGOPTIONS='-c default_transaction_read_only=on' psql -d mock -At -c \
"SELECT current_setting('transaction_read_only');
 SELECT id,name FROM assets.traits WHERE id=6;
 SELECT column_name FROM information_schema.columns
 WHERE table_schema='public' AND table_name='global_variables' AND column_name='model';
 SELECT to_regclass('public.schema_migrations'),to_regclass('assets.save_slots');"
```

Output was `on`, `6|reputation`, and `|assets.save_slots`, with no model-column
row. The owner database was never seeded or written. A disposable current-schema
clone with the legacy trait spelling proves the real CLI errors without its
success message and rolls back both trait resets and the earlier cache write
(`tests/test_mock_openai.py:450`).

## Consumer and Child-Environment Audit

The two in-process bootstrap tests now request the routed provider fixture.
`test_set_designer_failure.py` routes its source clone through the shared helper.
The connection lifecycle test creates/seeds `qa640_816_lifecycle_test_provider`
on its own registered private cluster and exports that name before starting
its provider. Its `save_04` databases are admitted only on those registered
private clusters (ports 55222 and 55223), not on the owner server.

The real child sentinel proof writes a UUID narrative to the routed clone and
receives exactly that narrative through the child HTTP API
(`tests/test_mock_openai.py:504`). The unrouted child returns HTTP 500 and its
log identifies the never-created database (`:527`). No further hidden reader
required routing in the focused supervisor, recovery, lifecycle, bootstrap,
manifest, scheduler, or seat-policy consumers. The coordinator's combined gate
must still check the rest of the tree.

The complete output of `git grep -nE 'env=\{|env=dict\(' -- tests` is preserved
in [child-environment-sites.txt](child-environment-sites.txt). Each hit was
traced to the actual spawn, including helper-built environments:

- Ordinary literal expansions and `dict(os.environ)` inherit the route. This
  covers scheduler helpers, the mock integration server, delayed recovery
  provider, lifecycle provider, supervisor children, acceptance staging,
  genesis ledger, CLI choice/inspect, embedding tools, golden overrides,
  parity/registry/token/prompt/prose tools and travel proofs.
- `tests/test_cli_contract.py:232` and `test_cli_session_wait.py:389` construct
  child environments from `os.environ` before applying the callers' small
  `env={...}` dictionaries. Their isolated-key lists do not remove the provider
  route. `test_slot_routed_entrypoints.py:125` likewise starts with
  `dict(os.environ)`; the filtered embedding-artifact child environment removes
  only its runtime-config override. These retain the provider database route.
- `tests/test_qa_shift.py:348` deliberately supplies only PATH and an owner-home
  sentinel to `bash -c '. "$1" && env -0'`. That child prints its environment;
  it launches no provider, imports no application code, and opens no database.
  The parent later constructs a supervisor without spawning it in this test.
- The explicit/minimal environments in `tests/test_secret_store_guard.py`
  (including `:626`, its `env=minimal` forms and store-access forms) run only the
  inline `CHILD_REPORT` script. It imports `os, sys` and writes the guard flag
  to a temporary report; it cannot read the TEST database.
- The new 008 CLI rollback child uses `{**os.environ, "PYTHONPATH": root}` and
  explicitly passes its disposable `--dbname`.

These environment exceptions need no provider route. The dbname audit itself
does not instrument arbitrary subprocesses, so the inherited route and real
sentinel/refusal tests provide the separate child-process evidence.

## Focused Commands and Tails

All runs used `/Users/pythagor/nexus/.venv/bin/python` (`PY` below),
`PYTHONPATH=$PWD` from this worktree, and `nice -n 15`. Import provenance printed
this worktree's `nexus/__init__.py`. Before each PostgreSQL run, `uptime` showed
one-minute load below 24 (no load wait needed); only one pytest ran in this lane
at a time. The common PostgreSQL prefix was:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH="$PWD" \
  nice -n 15 "$PY" -m pytest
```

### Experience Count Before and After

The pre-conversion test file was read with
`git show origin/main:tests/test_orrery/test_character_experiences_pg.py` into a
temporary `tests/test_orrery/_816_experience_baseline.py`, run under the current
branch's shared fixtures/runtime, and removed in `finally`. This is a count
and behavior comparison of the original test file, **not** a claim that a clean
main checkout was gated. The coordinator approved that constrained comparison.
The original and converted files both run the same 28 cases.

### Original Experience Test File

PostgreSQL prefix above:

```sh
-q -p tests.dbname_audit tests/test_orrery/_816_experience_baseline.py
```

```text

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 30 targets: postgres, qa640_wizard_drain_* x3, qa_wt724_experience_* x26
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
28 passed, 2 warnings in 33.10s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Converted Experience Test File

PostgreSQL prefix above:

```sh
-q -p tests.dbname_audit tests/test_orrery/test_character_experiences_pg.py
```

```text

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 30 targets: postgres, qa640_wizard_drain_* x3, qa_wt724_experience_* x26
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
28 passed, 2 warnings in 34.51s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Initial Contract and Guard Proof

PostgreSQL prefix above:

```sh
-q -p tests.dbname_audit tests/test_mock_openai.py \
  tests/test_config/test_test_provider_database.py tests/test_pg_experience_seeds.py \
  tests/test_logon_mock_integration.py tests/test_pg_disposable_target.py \
  tests/test_dbname_audit.py tests/test_owner_target_guard.py
```

```text
........................................................................ [ 69%]
................................................................         [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 10 targets: postgres, qa640_816_empty_*, qa640_816_experience_seed_* x2, qa640_816_test_provider_* x4, qa735_slot_model_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
208 passed in 25.03s
```

This first run preceded the additional traits missing-row case and CLI rollback
proof. Those additions are covered in the next consumer run.

### Updated Consumers and Rollback Proof

PostgreSQL prefix above:

```sh
-q -p tests.dbname_audit tests/test_mock_openai.py \
  tests/test_orrery/test_character_experiences_pg.py \
  tests/test_api/test_set_designer_failure.py tests/test_connection_lifecycle.py \
  tests/test_orrery/test_card_identity.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 48 targets: postgres, qa640_816_empty_* x4, qa640_816_legacy_trait_*, qa640_816_lifecycle_test_provider, qa640_816_test_provider_* x4, qa640_840s3a_slot_* x2, qa640_840s3a_source_* x2, qa640_885_ren_replay_* x4, qa640_wizard_drain_* x3, qa_wt724_experience_* x26
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:55222 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:55223 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:55222 (psycopg2), save_04@local:55223 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
65 passed, 2 skipped, 7 warnings in 90.56s (0:01:30)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The two skips are the pre-existing `requires_corpus` exposure-rank probes.

### Five Current #964 Nodes

PostgreSQL prefix above:

```sh
-vv -p tests.dbname_audit \
  tests/test_mock_openai.py::test_mock_responses_routes_bootstrap_schema_as_final_result_tool \
  tests/test_mock_openai.py::test_mock_responses_routes_bootstrap_schema_as_native_text_format \
  tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation \
  tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_live_turn_starts_before_queued_render \
  tests/test_api/test_seat_policy_jobs_pg.py::test_accept_repin_and_scheduler_use_literal_seat_models
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_764_turn_*, qa640_800_turn_*, qa640_814_seats_*, qa640_816_test_provider_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
======================== 5 passed, 9 warnings in 41.55s ========================
```

```text
tests/test_mock_openai.py::test_mock_responses_routes_bootstrap_schema_as_final_result_tool PASSED [ 20%]
tests/test_mock_openai.py::test_mock_responses_routes_bootstrap_schema_as_native_text_format PASSED [ 40%]
tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation PASSED [ 60%]
tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_live_turn_starts_before_queued_render PASSED [ 80%]
tests/test_api/test_seat_policy_jobs_pg.py::test_accept_repin_and_scheduler_use_literal_seat_models PASSED [100%]
```

The former manifest `[async]` / `[sync]` pair is now this one unparametrized
node because #1012 retired async mode; the coordinator can record all five
current node results in #964.

### Additional Child Consumers and Initial Reachability Failure

PostgreSQL prefix above:

```sh
-q -p tests.dbname_audit tests/test_runtime/test_supervisor_live.py \
  tests/test_api/test_scheduler_recovery_pg.py tests/test_doc_front_matter.py \
  tests/test_reachability.py tests/test_pg_target_contract.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 13 targets: postgres, qa640_800_kill_*, qa640_800_renew_* x4, qa640_offline_gate_* x5, qa804_fixture_target, qa885_supervisor_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_reachability.py::test_repository_reachability_ratchet - ass...
FAILED tests/test_reachability.py::test_checker_cli_is_stdlib_only_and_writes_evidence_without_importing_app
2 failed, 226 passed, 7 warnings in 135.56s (0:02:15)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

Both failures were the two new file-based 008 imports missing dynamic-edge
registrations. Added exactly those two entries; the operator root and
reachability rule remain intact. All child consumers in this run passed.

### Reachability and Canonical Documents After Repair

Offline command:

```sh
PYTHONPATH="$PWD" nice -n 15 "$PY" -m pytest -q \
  tests/test_reachability.py tests/test_doc_front_matter.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
96 passed, 5 warnings in 15.68s
```

### Deliberate Missing-Row Fallback Mutation

Temporarily replaced only the wizard/bootstrap readers' raise blocks with
`return row or {}` and restored the old cached-bootstrap placeholder branch.
Each missing-row assertion has a separate parametrized case. The scratch
wrapper required exit 1 and restored the entire source file in `finally`, then
verified byte-for-byte equality with its pre-plant contents. The three planted
fallbacks failed exactly as expected; the untouched traits refusal passed.

### Red Control

PostgreSQL prefix above:

```sh
-q -p tests.dbname_audit tests/test_mock_openai.py::test_missing_test_provider_rows_raise
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa640_816_empty_* x4
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_mock_openai.py::test_missing_test_provider_rows_raise[wizard]
FAILED tests/test_mock_openai.py::test_missing_test_provider_rows_raise[bootstrap]
FAILED tests/test_mock_openai.py::test_missing_test_provider_rows_raise[cached-bootstrap]
3 failed, 1 passed in 5.22s
```

### Restored Source

PostgreSQL prefix above:

```sh
-q -p tests.dbname_audit tests/test_mock_openai.py::test_missing_test_provider_rows_raise
```

```text
....                                                                     [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa640_816_empty_* x4
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
4 passed in 4.88s
```

## Static Checks and Canonical Freshness

The [changed Python list](files.txt) contains 16 files. Black reports all 16
unchanged. Flake8 and mypy compared those files with the 14 pre-existing files
exported from `origin/main` into a scratch directory; the two new test files
are also checked on the branch. Exact invocations (from the appropriate root):

```sh
PYTHONPATH="$PWD" nice -n 15 "$PY" -m black --check <files>
PYTHONPATH="$PWD" nice -n 15 "$PY" -m flake8 --config=<worktree>/.flake8 <files>
PYTHONPATH=<worktree> MYPYPATH=<worktree> nice -n 15 "$PY" -m mypy --explicit-package-bases <files>
PYTHONPATH="$PWD" nice -n 15 "$PY" -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
PYTHONPATH="$PWD" nice -n 15 "$PY" scripts/check_model_drift.py
git diff --check
```

Exception dispositions, model drift and diff whitespace checks passed.

Pre-existing diagnostics, with **zero new diagnostics** after normalizing source
line/column shifts (and the old lifecycle F811's embedded `from line` number):

- Flake8: 29 output lines / 28 distinct normalized diagnostics on each tree;
  [main](flake8-main.txt), [branch](flake8-branch.txt).
- Mypy: `Found 48 errors in 4 files` on each tree (14 main files, 16 branch
  files); [main](mypy-main.txt), [branch](mypy-branch.txt). Errors are on unchanged
  lines, and the two added test files introduce none.

Re-verified `AGENTS.md` against its changed source declarations (`nexus.toml`,
`tests/conftest.py`, `tests/pg_fixtures.py`, and the owner-audit wording in
`docs/agent_workflow.md`), and `docs/turn_flow_sequence.md` against its declared
`nexus.toml`. Their architecture/turn-flow statements remain accurate. Both
`verified_commit` values now name merge base `afd034f360e625f8bc4ffa8a717dda28422b19c7`.
The freshness check passes in the 96-test run above.

## Landing and Remaining Gate

- The coordinator owns the one combined whole-tree PostgreSQL gate and offline
  gate; neither is claimed here. No new PR is opened until that combined gate
  passes. This branch is ready for that integration review/gate.
- No numbered schema migration, template/fleet application, owner save reset,
  owner-data write, paid call, or owner-service restart occurred. The production
  default continues to read `mock`; the explicit-target seeder compatibility
  change is approved above.
- Product runtime files changed, so gateway and mock-provider restarts are owed
  when the coordinator next starts the services. No UI files changed; no UI
  rebuild is needed.
- Read-only cleanup check on `postgres`:
  `SELECT datname FROM pg_database WHERE datname LIKE 'qa640_816_%' ORDER BY datname`
  returned no rows after the proofs. The unrouted sentinel database was never
  created. Fixture-owned children and clones were cleaned up by their fixtures.

## Integration Repair: Reseeding After Migration 148

Cross-slice review found that 008's `TRUNCATE layers CASCADE` clears all three
source junctions, including factions through their place foreign key, while
`entities` and `narrative_chunks` survive. Migration 148's row triggers do not
fire for TRUNCATE, so previously mirrored references remained stale after a
successful reseed. 008 now checks for `public.chunk_entity_references` and
clears it in the same transaction before the existing truncates. The table
check preserves seeding support for current-schema targets predating 148.

`test_reseeding_test_provider_preserves_reference_parity` uses the actual
migration when present: a production roster write creates one character,
place and faction reference, the parity tool proves the starting rows, and two
real 008 CLI reseeds must leave zero junction/unified references while retaining
the original chunk and all three entities. It skips only when the checkout does
not contain migration 148; when that migration file exists, a missing live table
is an assertion failure rather than a skip. No synthetic schema is used.

Before integration, this 816 branch contains migrations through 145. With
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT`, `NEXUS_RUN_LIVE_LLM` unset:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH="$PWD" nice -n 15 "$PY" -m pytest -q -rs \
  -p tests.dbname_audit \
  tests/test_mock_openai.py::test_seeded_test_provider_database_holds_the_rows_the_provider_reads \
  tests/test_mock_openai.py::test_seeder_trait_mismatch_rolls_back_every_write \
  tests/test_mock_openai.py::test_reseeding_test_provider_preserves_reference_parity
```

The seeded-row proof now includes a successful real CLI reseed, proving the
new optional-table check against pre-148 schema. Tail:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
SKIPPED [1] tests/test_mock_openai.py:501: cross-slice reseed proof requires the real migration 148
2 passed, 1 skipped in 3.94s
```

Black passes both edited Python files; mypy reports no issues in either.
Flake8 retains exactly the same thirteen existing seeder line-length diagnostics
as `origin/main`, with none in the test file and no new messages. Diff whitespace
passes. An independent source review found no requested correction.

### Real Migration-148 Integration Proof

The coordinator merged code/test commit `9765bf1a149d1688c1cc8ce4b220276c92b38650`
and the companion 836 documentation correction into integration head
`188d9aab3ab2328db0fed9714cd9379537af2010`. Import provenance pointed at that
checkout. Its tree was clean before and after this proof; no integration
commit or owner write occurred. Load was 2.71 before red and 3.67 before green.

The [mutation harness](reseed-148-mutation.py.txt) removed only the three
`to_regclass` / conditional DELETE statements. It ran the new regression and
restored the seeder byte-for-byte in `finally` (SHA256
`0aaf62f366f5a143b3a339dc870450fcb4f11b6f996990458d3da486a8ffba2c`).
[Red transcript](reseed-148-red.txt): the real CLI seed succeeded, but its
post-seed parity assertion failed because the junctions were empty while their
mirrored references remained. The fixture's pre-seed parity check had proved
one row of each of character, place and faction.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH="$PWD" nice -n 15 "$PY" -m pytest -q -rs \
  -p tests.dbname_audit \
  tests/test_mock_openai.py::test_reseeding_test_provider_preserves_reference_parity
```

```text
>           assert after["parity"], after["kinds"]
E           assert False
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
1 failed in 2.46s
```

After restoration, the new regression, existing provider/rollback proof and
both reference/parity consumer files ran in one session:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH="$PWD" nice -n 15 "$PY" -m pytest -q -rs \
  -p tests.dbname_audit \
  tests/test_mock_openai.py::test_reseeding_test_provider_preserves_reference_parity \
  tests/test_mock_openai.py::test_seeded_test_provider_database_holds_the_rows_the_provider_reads \
  tests/test_mock_openai.py::test_seeder_trait_mismatch_rolls_back_every_write \
  tests/test_chunk_entity_references_pg.py tests/test_entity_reference_parity_pg.py
```

[Green transcript](reseed-148-green.txt):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
SKIPPED [4] tests/test_chunk_entity_references_pg.py:585: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
19 passed, 4 skipped, 2 warnings in 26.81s
```

The cross-slice regression ran and passed, including both actual CLI reseeds;
only the four existing corpus probes skipped. The pre-148 branch transcript is
also retained in [reseed-pre148.txt](reseed-pre148.txt). A read-only catalog
check found no remaining `qa640_816_%` or `qa640_836%` databases. This targeted
proof completes the repair; the coordinator still owns the full combined gate.

Codex — GPT-6

## PR 1123 Operator Review Fixes (2026-10-08)

Addressed the actionable portions of
[Claude's review](https://github.com/pythagorakase/nexus/pull/1123#issuecomment-6065700584).
The two singleton UPDATE checks now raise `RuntimeError` explicitly, including
under optimized Python. `main` parses arguments before reading the default target
from settings, so `--help` works with malformed configuration. Explicit targets
still use `connection_kwargs` and `write_story_settings`, which require validated
configuration; no connection-policy bypass was added. Successful output names
the selected database. `docs/settings_scopes.md` now documents the process-wide
validated `NEXUS_TEST_PROVIDER_DATABASE` override.

The frozen order's Pydantic `mock` default and literal test-owner guards remain:
deriving the protected owner from an environment-overlaid setting would weaken
isolation. Existing proof logs, story-name refusals, current-schema requirements,
single-transaction rollback and conditional migration-148 cleanup remain intact.

Merged landed main `d476db9117104d5dfddba742e85e7966efec89e4` as `cf6d459e`,
resolving `tests/conftest.py` to the already-tested f291 contents. After the first
focused pass, merged landed 812 main `7399bd991294715ba724e7779ae753f66f80cfe6`
as `0668a640ee9db4601d1ea99abdbcff4eabab8ae1`. Canonical source declarations were
reviewed and their freshness stamps advanced to that main commit. The
[scoped diff from f291](review-2026-10-08/scoped-f291.patch) records only this
review repair's source, tests and settings documentation.

The new tests run the actual 008 CLI under `python -O`. For each singleton
UPDATE separately, a trigger on a disposable database suppresses that UPDATE;
the test requires the specific runtime refusal and unchanged singleton/cache
data after rollback. No fake cursor or monkeypatched seeding path is used.

The following commands used `PY=/Users/pythagor/nexus/.venv/bin/python`, this
worktree's exact `PYTHONPATH`, and unset `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and
`NEXUS_SLOT`. Import provenance printed this worktree's `nexus/__init__.py`.
Pre-run one-minute loads were 3.93, 6.28, 5.66 and 5.49, all below 24.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q \
  -p tests.dbname_audit tests/test_test_provider_seeder.py \
  tests/test_mock_openai.py::test_seeded_test_provider_database_holds_the_rows_the_provider_reads
```

[Red](review-2026-10-08/red.txt): `4 failed, 1 passed in 7.31s`. Both optimized
singleton cases incorrectly reported success before the fix; malformed-config
help and target-specific success output also failed. The retained
[initial red](review-2026-10-08/red-initial.txt) has one additional test assertion
error: TOML's exception did not include the config filename. The test was
corrected to require `TOMLDecodeError` before the reported red run; production
source was still unchanged.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs \
  -p tests.dbname_audit tests/test_test_provider_seeder.py \
  tests/test_mock_openai.py tests/test_config/test_test_provider_database.py \
  tests/test_owner_target_guard.py tests/test_doc_front_matter.py \
  tests/test_reachability.py
```

[First repaired run](review-2026-10-08/green.txt): `1 failed, 213 passed, 1 skipped
in 37.82s`. The sole failure was the turn-flow document's freshness stamp after
the main merge; the sole skip was the actual-148 parity test because migration
148 is not yet on this feature branch. Every operator/routing/rollback test
passed. After the next main merge and freshness repair:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs \
  -p tests.dbname_audit tests/test_test_provider_seeder.py \
  tests/test_mock_openai.py::test_seeded_test_provider_database_holds_the_rows_the_provider_reads \
  tests/test_mock_openai.py::test_seeder_trait_mismatch_rolls_back_every_write \
  tests/test_config/test_test_provider_database.py tests/test_doc_front_matter.py
```

[Final focused run](review-2026-10-08/green-after-main.txt):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
57 passed in 12.73s
```

Black passes all three changed Python files. Mypy with
`--explicit-package-bases` reports no issues in those three files or in the two
existing files from `origin/main`. Flake8 reports the same thirteen pre-existing
008 line-length diagnostics on both sides, none on changed lines or either test
file. The exception disposition checker passes against `origin/main`. Outputs
are retained in [review-2026-10-08](review-2026-10-08/).

A second agent reviewed the final source/test diff without executing it and
found no blocker. No owner call, paid call, service change or whole-suite run
was made. The coordinator will exercise the unchanged actual-148 parity test
again after merging this repair into the combined integration.

Codex — GPT-6

### Final Main Refresh

Merged landed 785 main `6f338c55c1d1f769633136f91c2cad1bc8ff99ae` as
`9b6940e04e9141d96f74598f8a8fdc2f3025241d`. The travel/configuration changes
match tested integration f291. The seeder and review-regression tests remain
byte-identical to `e6d3d146`; 008 SHA256 is
`6c1dcdadf733fd7570221d368f97b9507c1cfa1bdffc6c50a19935cad51bf925`.
Within the 816 production scope, the only difference from f291 remains the
operator patch shown above. Other branch-versus-f291 differences are the still
unlanded 810/836 lanes, not new 816 changes.

Rechecked the canonical document claims against the merged sources: no prose
correction was required. Both source freshness stamps now name `6f338c55`.
With the coordinated test slot free and one-minute load 3.95:

```sh
PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python \
  -m pytest -q tests/test_doc_front_matter.py
```

[Final document check](review-2026-10-08/final-doc-freshness.txt):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
42 passed, 5 warnings in 4.02s
```

No behavioral tests were repeated for this unchanged-source merge. The test
slot was released to the 810 reviewer immediately after this check.

Codex — GPT-6
