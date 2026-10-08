# 812-S4a Verification: One Runtime Embedder

Branch: `claude/812-one-embedder`; base: `afd034f360e625f8bc4ffa8a717dda28422b19c7`.
Saved implementation: `3322374f`. Product amendment and regression tests:
`ea5bb96d6e03d45531439f608e287a23fdef9e86`. Final code/test revision:
`a9f87c64c6dcc976ca084f2190bb7da5cbf3c9fb` (TOML fixture type annotations).
The follow-up evidence commit changes only this directory.

The implementation follows [812-Q3, Q11 and Q12](https://github.com/pythagorakase/nexus/issues/812#issuecomment-5915948801)
and the 2026-10-08 schema-copy amendment. The current branch already contains
`origin/main` at `afd034f3`; no further main merge was needed.

## Contract and Source Evidence

- `nexus/config/settings_models.py:3238` defines a candidate without runtime
  `weight` or `is_active`; `:4066` types the two offline registries; `:4485`
  requires exactly one active runtime entry; `:4509` rejects production name
  and path shadowing; `:4675` exposes the combined registry for offline scripts.
- `ir_eval/engine/run_executor.py:79` and `:96` resolve named embedders and
  rerankers. `:299` resolves the complete snapshot before `store.create_run`;
  `:105` requires snapshot names to equal the selected names; execution at
  `:327` uses the stored reranker identity, without consulting live candidates.
- `nexus/agents/memnon/utils/artifact_manifest.py:126` uses the production
  reranker's explicit name and repository. The committed artifact lock is
  unchanged. The lock and artifact tests passed; `nexus models verify` was
  intentionally reserved for the coordinator at landing.
- `nexus/runtime/home_plan.py:296` lists production paths only. Offline script
  loaders resolve candidates at their call site. `--all-models` remains
  production-only. No ir_eval V1 implementation file changed; its existing
  override test passed unchanged.
- `AGENTS.md` and `docs/turn_flow_sequence.md` were already re-verified at
  `afd034f3` in the saved branch. Freshness tests pass.

[Key-by-key registry comparison](resume-2026-10-08/registry-comparison.txt)
compares the current TOML with `git show origin/main:nexus.toml`. All nine
embedder identities/paths/dimensions are preserved; the eight moved entries
lose only the ordered runtime switches. The production embedder keeps all five
keys. All three offline reranker entries keep their four keys, while the
production reranker's name, model path and repository match its old candidate.

## Product Fix: Copy the Evaluation Schema Into Fresh Slots

`scripts/new_story_setup.py:255` now includes `ir_eval` in the schema-only dump
and `:299` recreates its filtered schema before restoring objects. Previously,
the target copied template migration stamps for migrations 015–017 without
copying the schema those stamps covered. This is an initialization fix, with
no new migration and no existing-slot application.

`tests/test_ir_eval_v2/test_create_run_candidates_pg.py:55` proves a fresh
clone contains `ir_eval.eval_runs` and zero rows. The tests use disposable
`qa640_812s4a_*` databases and the real command parser/store. They additionally
prove an unknown enabled reranker writes no run (`:140`), while a disabled
unknown reranker is ignored and preserves the production snapshot (`:154`).

The [read-only fleet survey](resume-2026-10-08/fleet-read-only.txt), performed
on 2026-10-08 with `transaction_read_only=on`, found zero runs in
`NEXUS_template` and `save_01`; `save_02`–`save_05` lack `ir_eval.eval_runs`.
No stored snapshot requires migration. This existing fleet inconsistency is
[recorded on #812](https://github.com/pythagorakase/nexus/issues/812#issuecomment-6052979949)
and is deferred; no owner database was written.

## Focused Proof

All tests ran serially under `nice -n 15`, with the shared interpreter
`PY=/Users/pythagor/nexus/.venv/bin/python` and exact worktree `PYTHONPATH=$PWD`.
Import verification printed
`/Users/pythagor/nexus/.claude/worktrees/812-one-embedder/nexus/__init__.py`.
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` and `NEXUS_RUN_LIVE_LLM`
were unset; PostgreSQL sessions used `NEXUS_RUN_POSTGRES=1` and
`-p tests.dbname_audit`. One-minute load was 3.50 for the first run and 3.56
for the consumer run, below the order's limit of 24.

At `ea5bb96d`, the ordered focused PostgreSQL set plus initialization consumers:

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_ir_eval_v2 tests/test_lore/test_runtime_config.py tests/test_regenerate_embeddings_truncate_pg.py tests/test_memnon_embedding_cache.py tests/test_memnon_model_failures_pg.py tests/test_api/test_narrative_jobs_pg.py tests/test_database_contract.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py tests/test_owner_target_guard.py tests/test_new_story_setup.py tests/test_postgres_tools.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
209 passed, 2 skipped, 23 warnings in 154.53s (0:02:34)
```

At `a9f87c64`, all other modified consumers and the two annotation-updated
fixture files (including real local bge model/cache paths):

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_memnon_embedding_contract.py tests/test_memnon_script_model_loaders.py tests/test_embedding_artifacts.py tests/test_model_artifact_lock_committed.py tests/test_memnon_cross_encoder_artifact.py tests/test_runtime_home.py tests/config/test_settings_parity.py tests/test_config/test_ir_eval_golden_overrides.py tests/test_reachability.py tests/test_doc_front_matter.py tests/test_memnon_embedding_cache.py tests/test_lore/test_runtime_config.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
223 passed, 14 warnings in 74.61s (0:01:14)
```

After all negative controls were reverted byte for byte, the final code/test
revision remained `a9f87c64`, with `git status --short` empty:

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_ir_eval_v2/test_candidate_registry.py tests/test_ir_eval_v2/test_create_run_candidates_pg.py tests/test_doc_front_matter.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
113 passed in 27.13s
```

Full [PostgreSQL output](resume-2026-10-08/focused-pg.txt),
[consumer output](resume-2026-10-08/changed-consumers.txt), and
[restored-tree output](resume-2026-10-08/restored-focused.txt) are retained.
These are focused proofs. The full offline and PostgreSQL gates remain for
the coordinator's single serial integration run; no whole-suite pass is claimed.

## Negative Controls

Each control changed only the named source file, ran one pytest session, then
restored the original bytes in a `finally` block. Each returned pytest exit 1,
with the secret-store guard active and `dbname audit: owner targets: none`.
The exact patches, failure tracebacks and final tails are retained. Repeated
captured setup/call output is elided with each omitted line count; the raw
local logs remain under `temp/codex-812-resume/`.

- [Skip create-run resolution](resume-2026-10-08/red-resolution.patch), using
  `origin/main`'s original `create_run` method. Command: the same guarded pytest
  invocation over `tests/test_ir_eval_v2/test_create_run_candidates_pg.py`.
  [Result](resume-2026-10-08/red-resolution.txt): **3 failed, 3 passed in 9.14s**.
  The named embedder snapshot and unknown embedder/reranker refusal assertions
  fail.
- [Remove the entry-count guard](resume-2026-10-08/red-entry-count.patch).
  Command: the same invocation over
  `tests/test_ir_eval_v2/test_candidate_registry.py`.
  [Result](resume-2026-10-08/red-entry-count.txt): **2 failed, 9 passed in 4.19s**.
  Both second-runtime-entry cases fail the required contextual diagnostic.
- [Restore the initializer before the ir_eval fix](resume-2026-10-08/red-ir-eval-schema.patch).
  Command: the same invocation over
  `tests/test_ir_eval_v2/test_create_run_candidates_pg.py::test_fresh_clone_copies_ir_eval_schema_without_run_data`.
  [Result](resume-2026-10-08/red-ir-eval-schema.txt): **1 failed in 3.22s**;
  `to_regclass('ir_eval.eval_runs')` returns `None`.

## Static Checks and Existing Diagnostics

The changed Python file list is `git diff --name-only origin/main...HEAD -- '*.py'`
at `a9f87c64` (25 files). Every command used `nice -n 15 $PY`.

- `-m black --check <changed files>`: all 25 unchanged;
  [output](resume-2026-10-08/black-final.txt).
- `-m flake8 <changed files>`: 183 inherited diagnostics versus 187 on the
  pre-existing files' `origin/main` versions; **no new diagnostic messages**.
  Full [branch](resume-2026-10-08/flake-final.txt),
  [main](resume-2026-10-08/flake-main.txt), and
  [comparison](resume-2026-10-08/flake-comparison.txt).
- `-m mypy --explicit-package-bases <changed files>`: 82 inherited errors
  versus 90 on main; **no new diagnostic messages**. For a like-for-like module
  resolution, main's 852 Python/config files were exported from `origin/main`
  under scratch and the same command ran from that root over the 23
  pre-existing changed files. Full [branch](resume-2026-10-08/mypy-final.txt),
  [main](resume-2026-10-08/mypy-main-context.txt), and
  [comparison](resume-2026-10-08/mypy-comparison.txt).
  Added/changed TOML fixture statements were typed explicitly to remove their
  diagnostics; unrelated existing diagnostics were not altered.
- `-S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`:
  [passed](resume-2026-10-08/exceptions.txt).
- `scripts/validate_config_commit.py`: [exit 0](resume-2026-10-08/config.txt).

## Landing and Deferred Work

No migration or fleet application. Product code and `nexus.toml` change, so
run `nexus models verify` on the owner host before landing and restart the
gateway when the owner's services run again. No UI change, rebuild or
state-surface regeneration. The artifact lock is unchanged.

The order overlaps settings files with 806/816, offline scripts with 810,
and slot initialization with 822; integration must retain both sides' changes.
No product decision is needed for this slice. The 812-S4b weighting/ensemble
move, S3/S6 boot/doctor/model commands, S5/S7 legacy work, owner data questions
Q4b/Q9, #820 path anchoring and V1's pending #811 ruling remain deferred.
No paid provider, owner service, model directory or credential was changed.

Codex — GPT-6
