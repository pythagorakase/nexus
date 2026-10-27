# Verification: Offline Test Tier in CI and the Local-Models Marker (816-S2S4a)

Issue #816; Decisions 816-D1, 816-D5 and 816-D10 (coordinator comment
"Decisions Recorded From the 2026-10-26 Coordinator Review"). Branch
`claude/816-offline-ci-tier`, cut from `origin/main` at `c7ae2988`, merged with
`origin/main` at `9a0714d7` and `b0e9cb77` before the first push, and at
`e058005f` and `d295eef0` while CI ran. `AGENTS.md` and
`docs/decisions/0076-the-offline-merge-gate.md` are re-stamped to the last
merge base, `d295eef0`. No migration, no file under `nexus/`, `scripts/` or `ui/`, and no
committed `nexus.toml` change. No paid call; no gateway lane started by hand.

Scratch directory for every log below (called `<scratch>`):
`/private/tmp/claude-501/-Users-pythagor-nexus/9dcd8ba0-5aed-4efa-8d64-38cffa54a15d/scratchpad/816-S2S4a/`.

## Cited Lines (Verified at c7ae2988)

- `grep -l pytest .github/workflows/*.yml` printed nothing; the eight workflows
  were agent-review-orchestration, claude-code-review, claude,
  exception-disposition-check, migration-comment-check, model-drift-check,
  notify-edi and reachability-check.
- `pytest.ini:5-11`: the marker list (six markers, no model marker).
- `tests/conftest.py:297-303`: `pytest_terminal_summary` writes
  `secret_store_guard.describe()`; `:323-357` apply the opt-in skips.
- `nexus.toml:952` (`[memnon.models."Octen-Embedding-4B"].local_path`) and
  `nexus.toml:1134` (`[memnon.retrieval.cross_encoder_reranking].model_path`)
  are absolute owner paths.
- `nexus/agents/memnon/utils/embedding_manager.py:148-151` raises
  `Embedding model '<name>' is not installed: local_path <path> does not exist.`
- `tests/scheduler_helpers.py:50-55` copies the checkout's `nexus.toml` and
  exports the copy as `NEXUS_RUNTIME_CONFIG`.
- `tests/test_doc_front_matter.py:29` (`BASE_REF = "origin/main"`) and
  `:592-602` (shallow clone and missing `origin/main` refusals).
- `tests/test_scripts/test_check_exception_dispositions.py:437-466`
  (`_interpreters`): the owner path at `:445` falls through to
  `shutil.which(name)`.
- `AGENTS.md:32` and `:34` declare `pytest.ini` and `docs/agent_workflow.md`
  as sources; `verified_commit` at `:38`.

Premise deviations found: (b) of item 3 holds 21 files at c7ae2988, not 20,
and one of them (`tests/test_lore/test_window_coverage_pg.py`, which imports
`run_cli` from `tests.scheduler_helpers` at `:33`) is also in (a). The union
is 48 files. After the merge of `origin/main`, the union holds 49: the new
`tests/test_model_artifact_lock_committed.py` (#812, landed in a8c6e3f5)
matches `tokenizer_repository`. The confirm and clean PostgreSQL runs use the
49-file set.

## The Audit Edit

`<scratch>/absent_models_config.py`, run as
`$PY <scratch>/absent_models_config.py nexus.toml <scratch>/absent-models`:

```python
"""Point the production embedder and reranker paths at a root that does not exist.

Usage: absent_models_config.py <toml> <absent-root>

Sets local_path of every [memnon.models] entry to <absent-root>/<entry name>
and [memnon.retrieval.cross_encoder_reranking].model_path to
<absent-root>/reranker, then writes <toml> back. No other key changes; the
[ir_eval.*] candidates keep their paths. Scratch audit tool for order
816-S2S4a; never committed.
"""

import sys
from pathlib import Path

import tomlkit


def main() -> None:
    toml_path = Path(sys.argv[1])
    absent_root = sys.argv[2].rstrip("/")
    if Path(absent_root).exists():
        raise SystemExit(f"absent root exists: {absent_root}")
    document = tomlkit.parse(toml_path.read_text(encoding="utf-8"))
    memnon = document["memnon"]
    for name, entry in memnon["models"].items():
        entry["local_path"] = f"{absent_root}/{name}"
    reranking = memnon["retrieval"]["cross_encoder_reranking"]
    reranking["model_path"] = f"{absent_root}/reranker"
    toml_path.write_text(tomlkit.dumps(document), encoding="utf-8")


if __name__ == "__main__":
    main()
```

It changes exactly two lines of the worktree's `nexus.toml` (the
`[ir_eval.*]` candidates keep their paths):

```
-local_path = "/Users/pythagor/nexus/models/Octen-Embedding-4B"
+local_path = "<scratch>/absent-models/Octen-Embedding-4B"
-model_path = "/Users/pythagor/nexus/models/naver-trecdl22-crossencoder-debertav3"
+model_path = "<scratch>/absent-models/reranker"
```

Before the first edit, `git rev-parse --show-toplevel` printed
`/Users/pythagor/nexus/.claude/worktrees/816-S2S4a`. Before every audit run,
with `NEXUS_RUNTIME_CONFIG` and `NEXUS_HOME` unset, the `load_settings` check
of item 2 printed `load_settings check exit 0` (`<scratch>/*.precheck`). After
every audit run, `git checkout -- nexus.toml && git diff --exit-code
nexus.toml` printed `restore exit 0`. Every commit and the push were made with
`git diff --exit-code nexus.toml` passing.

Each run was classified by `<scratch>/analyze_junit.py <run>.xml
<run>-tmp`: a testcase with `<failure>` or `<error>` whose message, text,
`system-out` or `system-err` matches R, or whose `tmp_path` directory (the
test name truncated to 30 characters) holds a file that `grep -rlE` matches
with R, is an artifact failure. No run's basetemp held an R match in any file:
the gateways the PostgreSQL tests start returned the R text in their HTTP
error body, which the failing assertion printed.

## Audit Runs

### Offline Find (c7ae2988 Plus the Marker Registration)

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery \
    --junitxml=<scratch>/offline-find-1.xml -o junit_logging=all --basetemp=<scratch>/offline-find-1-tmp
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
1 failed, 3195 passed, 678 skipped, 8 warnings in 673.84s (0:11:13)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery \
    --junitxml=<scratch>/offline-find-2.xml -o junit_logging=all --basetemp=<scratch>/offline-find-2-tmp
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1532 skipped, 7 warnings in 49.21s
```

- Artifact failures: none.
- Passing testcases matching R: none. Two passing testcases mention
  `absent-models` without matching R:
  `tests/test_ir_eval_v2/test_candidate_registry.py::test_candidates_cannot_shadow_production[embedder-path]`
  and `[reranker-path]`. They copy the config, point an `[ir_eval]` candidate
  at the production path on purpose, and assert the validation error that
  names it; no model loads.
- Audit-method failures:
  `tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit`
  (`AGENTS.md: nexus.toml, pytest.ini changed since the merge base c7ae2988d07b
  without a re-stamp`): the audit edit changes a declared source, and the
  re-stamp had not been made yet. It passes in the clean runs.
- Other failures: none.

### PostgreSQL Find (48 Files)

Load before the run: `18:01 up 6:39, load averages: 8.03 10.12 14.52`.

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit <48 files> \
    --junitxml=<scratch>/pg-find.xml -o junit_logging=all --basetemp=<scratch>/pg-find-tmp
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner server: local:5432
dbname audit: owner targets: none
30 failed, 549 passed, 15 skipped, 18 warnings in 909.90s (0:15:09)
```

Artifact failures (28 testcases; the text is the first R match in the
failure message):

| Test | Artifact text |
| --- | --- |
| `tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_api/test_backstage_endpoints_pg.py::test_economics_matches_inspect_turn_for_a_test_turn` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_live_turn_starts_before_queued_render` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_api/test_scheduler_pg.py::test_scheduler_embeds_rendered_experiences_and_skips_the_rest` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_api/test_seat_policy_jobs_pg.py::test_accept_repin_and_scheduler_use_literal_seat_models` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_cli_inspect_pg.py::test_continue_waits_then_inspect_reads_the_played_clone` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_embedding_table_ownership_pg.py::test_embedding_job_source_path_propagates_ensure_failure` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_embedding_table_ownership_pg.py::test_content_processor_embedding_method_propagates_ensure_failure` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_baseline_fingerprint_refresh_pg.py::test_divergence_fingerprint_refresh_preserves_continuation` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_logon_lazy_init.py::test_lore_keeps_logon_lazy` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_pass2_baseline_pg.py::test_story_settings_pinned_window_survives_accepted_turn` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_runtime_config.py::test_lore_honors_runtime_config_for_both_storyteller_seats` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_runtime_config.py::test_explicit_lore_settings_path_beats_runtime_environment` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_runtime_config.py::test_lore_without_runtime_environment_falls_back_to_repo_root` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_runtime_config.py::test_lore_instances_keep_independent_memnon_configuration` | `FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_scene_order_render.py::test_recent_warm_window_ends_at_historical_parent` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_window_coverage_pg.py::test_window_coverage_is_written_only_from_post_render_kept_chunks` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_window_coverage_pg.py::test_historical_coverage_matches_rendered_prefix[5-1]` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_window_coverage_pg.py::test_historical_coverage_matches_rendered_prefix[15-1]` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_window_coverage_pg.py::test_historical_coverage_matches_rendered_prefix[15-2500]` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_window_coverage_pg.py::test_removed_tokens_reach_real_attempt_manifest_and_observation[two_pass]` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_lore/test_window_coverage_pg.py::test_removed_tokens_reach_real_attempt_manifest_and_observation[single_pass]` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_memnon_embedding_cache.py::test_memnon_close_disposes_engine` | `Cross-encoder reranker is not installed: [memnon.retrieval.cross_encoder_reranking].model_path <scratch>/absent-models/reranker` |
| `tests/test_memnon_embedding_cache.py::test_per_turn_lore_stacks_share_embedder_and_close` | `FATAL: MEMNON initialization failed: Cross-encoder reranker is not installed: [memnon.retrieval.cross_encoder_reranking].model_path <scratch>/absent-models/reranker` |
| `tests/test_memnon_runtime_config.py::test_memnon_uses_runtime_config_instead_of_legacy_settings_path` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_memnon/test_source_embeddings.py::test_experiences_load_and_stamp_only_valid_rendered_rows` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_memnon/test_source_embeddings.py::test_wrappers_are_the_shared_orchestrator` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |
| `tests/test_orrery/test_experiences.py::test_embedding_upsert_binds_each_correct_experience_id` | `Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B` |

- Passing testcases matching R: none.
- Audit-method failures:
  `tests/test_api/test_narrative_jobs_pg.py::test_scheduler_accepts_summary_and_embeds_once_in_process[new_episode]`
  and `[new_season]`: `ValueError: Path <scratch>/absent-models/Octen-Embedding-4B
  not found`. The test body loads the production embedder itself
  (`tests/test_api/test_narrative_jobs_pg.py:77-82` calls
  `get_or_load_sentence_transformer(config["local_path"])` for the active
  `[memnon.models]` entry), so the error is sentence-transformers' own, not R.
  It passes in the clean run. Item 2 says such a failure is not marked; it is
  left unmarked and raised for the coordinator (see Open Questions in the PR).
- Other failures: none.

### Offline Confirm

The first confirm ran on the branch before the merge of `origin/main`; it was
rerun on the merged tree.

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -m 'not requires_local_models' tests --ignore=tests/test_api --ignore=tests/test_orrery \
    --junitxml=<scratch>/offline-confirm-1.xml -o junit_logging=all --basetemp=<scratch>/offline-confirm-1-tmp
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
FAILED tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline
2 failed, 3198 passed, 655 skipped, 23 deselected, 8 warnings in 624.83s (0:10:24)
```

- Artifact failures: none. Matching passes: none.
- Audit-method failures: the freshness check (`nexus.toml` changed by the
  audit edit), and
  `test_repository_tree_matches_committed_baseline` (`baseline growth
  forbidden`, 123 entries): `origin/main` had moved to `9a0714d7` during the
  run, and its baseline had shrunk below the branch's copy from `c7ae2988`.
  Both pass after the merge and in the clean runs.

Merged tree (after `git merge origin/main`):

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -m 'not requires_local_models' tests/test_api tests/test_orrery \
    --junitxml=<scratch>/offline-confirm-2.xml -o junit_logging=all --basetemp=<scratch>/offline-confirm-2-tmp
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1541 skipped, 6 deselected, 7 warnings in 45.60s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -m 'not requires_local_models' tests --ignore=tests/test_api --ignore=tests/test_orrery \
    --junitxml=<scratch>/offline-confirm-1m.xml -o junit_logging=all --basetemp=<scratch>/offline-confirm-1m-tmp
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit
1 failed, 3246 passed, 675 skipped, 22 deselected, 8 warnings in 660.19s (0:11:00)
```

- Artifact failures: none. Matching passes: none.
- Audit-method failure: the freshness check (`docs/decisions/0009-dollars-in-the-ledger.md:
  nexus.toml changed since the merge base 9a0714d7...`), the audit edit
  again. It passes in the clean runs.

### PostgreSQL Confirm (49 Files, Merged Tree)

Load before the run: `18:32 up 7:10, load averages: 18.52 18.47 16.82`.

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -m 'not requires_local_models' <49 files> \
    --junitxml=<scratch>/pg-confirm.xml -o junit_logging=all --basetemp=<scratch>/pg-confirm-tmp
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner server: local:5432
dbname audit: owner targets: none
FAILED tests/test_api/test_narrative_jobs_pg.py::test_scheduler_accepts_summary_and_embeds_once_in_process[new_episode]
FAILED tests/test_api/test_narrative_jobs_pg.py::test_scheduler_accepts_summary_and_embeds_once_in_process[new_season]
2 failed, 563 passed, 14 skipped, 28 deselected, 18 warnings in 766.51s (0:12:46)
```

- Artifact failures: none. Matching passes: none.
- Audit-method failures: the two `test_narrative_jobs_pg.py` parameters, as in
  the find run.

## Marked Tests

Function markers (`@pytest.mark.requires_local_models`, the topmost
decorator):

- `tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation`
- `tests/test_api/test_backstage_endpoints_pg.py::test_economics_matches_inspect_turn_for_a_test_turn`
- `tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_live_turn_starts_before_queued_render`
- `tests/test_api/test_scheduler_pg.py::test_scheduler_embeds_rendered_experiences_and_skips_the_rest`
- `tests/test_cli_inspect_pg.py::test_continue_waits_then_inspect_reads_the_played_clone`
- `tests/test_embedding_table_ownership_pg.py::test_embedding_job_source_path_propagates_ensure_failure`
- `tests/test_lore/test_logon_lazy_init.py::test_lore_keeps_logon_lazy`
- `tests/test_lore/test_pass2_baseline_pg.py::test_story_settings_pinned_window_survives_accepted_turn`
- `tests/test_lore/test_runtime_config.py`: `test_lore_honors_runtime_config_for_both_storyteller_seats`,
  `test_explicit_lore_settings_path_beats_runtime_environment`,
  `test_lore_without_runtime_environment_falls_back_to_repo_root`,
  `test_lore_instances_keep_independent_memnon_configuration`
- `tests/test_lore/test_scene_order_render.py::test_recent_warm_window_ends_at_historical_parent`
- `tests/test_lore/test_window_coverage_pg.py`: `test_window_coverage_is_written_only_from_post_render_kept_chunks`,
  `test_historical_coverage_matches_rendered_prefix` (parametrized, marked
  whole), `test_removed_tokens_reach_real_attempt_manifest_and_observation`
  (parametrized, marked whole)
- `tests/test_memnon_embedding_cache.py`: `test_memnon_close_disposes_engine`,
  `test_per_turn_lore_stacks_share_embedder_and_close`
- `tests/test_memnon_runtime_config.py::test_memnon_uses_runtime_config_instead_of_legacy_settings_path`
- `tests/test_memnon/test_source_embeddings.py`: `test_experiences_load_and_stamp_only_valid_rendered_rows`,
  `test_wrappers_are_the_shared_orchestrator`
- `tests/test_orrery/test_experiences.py::test_embedding_upsert_binds_each_correct_experience_id`
- `tests/test_memnon_cross_encoder_dependencies.py::test_local_deberta_cross_encoder_reranks_minimal_pair`
  (above its existing `skipif`; from the path reading, not an audit run).

Module markers (every collected test of the module failed; the single marker
became a list that keeps `requires_postgres`):

- `tests/test_api/test_seat_policy_jobs_pg.py` (1 test:
  `test_accept_repin_and_scheduler_use_literal_seat_models`)
- `tests/test_lore/test_baseline_fingerprint_refresh_pg.py` (1 test:
  `test_divergence_fingerprint_refresh_preserves_continuation`)

`tests/test_embedding_table_ownership_pg.py::test_content_processor_embedding_method_propagates_ensure_failure`
was also an artifact failure and was marked; `origin/main` (#1091, retiring
the legacy importer it exercised) deleted the test, and the merge takes main's
deletion.

Two of the marked tests carry `requires_bge_large`
(`tests/test_memnon_embedding_cache.py:231` and `:263`). The order says to
leave `requires_bge_large` tests unmarked because they load an `[ir_eval]`
candidate; these two also build a MEMNON whose reranker is the production
`[memnon.retrieval.cross_encoder_reranking].model_path`, and each failed with
`Cross-encoder reranker is not installed: [memnon.retrieval.cross_encoder_reranking].model_path
<scratch>/absent-models/reranker does not exist.` They are marked as artifact
failures. The other two `requires_bge_large` tests
(`test_embedding_manager_shares_one_model_per_process`,
`test_cached_model_survives_manager_teardown`) load only bge-large, passed
under the audit edit, and are unmarked and unchanged.

`tests/test_memnon_cross_encoder_dependencies.py:9-13` builds
`Path(__file__).resolve().parents[1] / "models" / "naver-trecdl22-crossencoder-debertav3"`:
the reranker that `nexus.toml:1134` names, read from the checkout's own
`models/` directory. The worktree has no `models/` directory
(`ls models: No such file or directory`), so the test skips in every audit run
and in the clean run ("Local DeBERTa cross-encoder model is not available");
it runs only in the main checkout.

## Tests That Escape the Edit

`grep -nE 'NEXUS_RUNTIME_CONFIG|"nexus\.toml"|/Users/pythagor|"models"|local_path=|model_path='`
over the PostgreSQL set plus `tests/scheduler_helpers.py`,
`tests/settings_helpers.py` and `tests/pg_fixtures.py` gave 109 hits
(`<scratch>/escape-scan.txt`). Verdicts by file:

- `tests/scheduler_helpers.py:50-55`, `tests/settings_helpers.py:62`: copies of
  the worktree's `nexus.toml` (directly, or through `resolve_config_path()`);
  they carry the edit. No action.
- `tests/test_api/test_acceptance_staging_pg.py:644`,
  `tests/test_api/test_backstage_endpoints_pg.py:822`,
  `tests/test_api/test_scheduler_corpus_pg.py:66-70`,
  `tests/test_lore/test_window_coverage_pg.py:497-499`,
  `tests/test_lore/test_pass2_baseline_pg.py:380`,
  `tests/test_orrery/test_experiences.py:104,128`,
  `tests/test_lore/test_token_estimator.py:76-390`,
  `tests/test_api/test_import_side_effects.py:65-77`,
  `tests/test_scheduler_helpers_routing.py:167-185`: read or copy the
  worktree's `nexus.toml` by relative path or `REPO_ROOT`; they carry the edit.
  No action.
- `tests/test_memnon_model_failures_pg.py:103-115`,
  `tests/test_embedding_artifacts.py:146-170`,
  `tests/test_memnon_embedding_contract.py:136-245`,
  `tests/test_memnon_cross_encoder_artifact.py:80,306,331`,
  `tests/test_memnon_embedding_cache.py:297`: replace `local_path` and
  `model_path` with tiny fixture artifacts or a missing folder under
  `tmp_path`; they load no production artifact. No action.
- `tests/test_memnon_embedding_cache.py:93-106`,
  `tests/test_regenerate_embeddings_truncate_pg.py:85-101`: use an `[ir_eval]`
  candidate (bge-large) or a missing folder for it. No action (the two
  production-reranker tests of the first file are marked from the audit).
- `tests/test_memnon_runtime_config.py:70,90`: `NEXUS_RUNTIME_CONFIG` names a
  config written from the worktree file; carries the edit. No action.
- `tests/test_golden_path_live.py:481-491`: copies the worktree's file (or
  `NEXUS_RUNTIME_CONFIG`); a live-tier test that skips without
  `NEXUS_RUN_LIVE_LLM=1`, so no audit run saw it. Not marked (the order marks
  only tests that load the artifact by a path the edit does not reach; the
  edit reaches this one, and the live tier belongs to 816-S5).
- `tests/test_api/test_narrative_jobs_pg.py:78`: reads `local_path` from the
  worktree's settings; carries the edit (the audit-method failure above).
- `tests/test_api/test_summary_budget_usage.py:61`,
  `tests/test_lore/test_runtime_config.py:23,171,201`,
  `tests/test_memnon/test_source_embeddings.py:185`,
  `tests/test_memnon_script_model_loaders.py:76`,
  `tests/test_schema_ownership.py:443`,
  `tests/test_memnon_embedding_contract.py:42,123`,
  `tests/test_embedding_artifacts.py:65-71,221,502,544-1058`: key lookups,
  provider model lists, CLI argument strings or `tmp_path` folders; no model
  path. No action.
- `tests/test_memnon_cross_encoder_dependencies.py:11,58`: the one escape;
  marked (above).
- `tests/test_model_artifact_lock_committed.py:30-81` (added by the merge):
  reads the committed `nexus.toml` as TOML and the committed lock; loads no
  model. No action.

## Red Runs

(a) A `paths: ["nexus/**"]` entry under `pull_request` (scratch plant, then
`git checkout -- .github/workflows/offline-tests.yml`):

```
F                                                                        [100%]
=================================== FAILURES ===================================
___________ test_offline_tests_job_is_the_unfiltered_required_check ____________
tests/test_offline_ci_workflow.py:73: in test_offline_tests_job_is_the_unfiltered_required_check
    assert "paths" not in trigger
E   AssertionError: assert 'paths' not in {'branches': ['main'], 'paths': ['nexus/**']}
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_offline_ci_workflow.py::test_offline_tests_job_is_the_unfiltered_required_check
1 failed in 0.29s
```

(b) The guard check of item 4, as written, against a copy of a real offline
log (`<scratch>/offline-confirm-2.log`) with the guard line deleted:

```
$ grep -v 'secret-store guard: active; nexus-api: denied' red-b.log > red-b-noguard.log
$ bash -c "grep -qF 'secret-store guard: active; nexus-api: denied' red-b-noguard.log"; echo $?
1
$ bash -c "grep -qF 'secret-store guard: active; nexus-api: denied' red-b.log"; echo $?
0
```

(c) With the audit edit applied (`load_settings check exit 0`), the marker
removed from
`tests/test_lore/test_runtime_config.py::test_lore_honors_runtime_config_for_both_storyteller_seats`:

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit --tb=line \
    -m 'not requires_local_models' tests/test_lore/test_runtime_config.py::test_lore_honors_runtime_config_for_both_storyteller_seats
/Users/pythagor/nexus/.claude/worktrees/816-S2S4a/nexus/agents/lore/lore.py:268: RuntimeError: FATAL: MEMNON initialization failed: Embedding model 'Octen-Embedding-4B' is not installed: local_path <scratch>/absent-models/Octen-Embedding-4B does not exist. Run `nexus models fetch` to download embedder 'Octen-Embedding-4B' into <scratch>/absent-models/Octen-Embedding-4B.
dbname audit: owner targets: none
FAILED tests/test_lore/test_runtime_config.py::test_lore_honors_runtime_config_for_both_storyteller_seats
1 failed in 4.55s
```

With the marker restored:

```
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 deselected in 0.32s
```

## Clean Runs (No Audit Edit; `git diff --exit-code nexus.toml` Passes)

PostgreSQL set (49 files, merged tree at `9a0714d7`), no `-m`, with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` and `NEXUS_RUNTIME_CONFIG`
unset. Load before the run: `18:58 up 7:36, load averages: 22.07 20.84 20.06`.

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit <49 files>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner server: local:5432
dbname audit: owner targets: none
592 passed, 15 skipped, 24 warnings in 1097.28s (0:18:17)
```

Every marked testcase ran and passed (no local skip), except
`tests/test_memnon_cross_encoder_dependencies.py::test_local_deberta_cross_encoder_reranks_minimal_pair`,
which its own pre-existing `skipif` skips in a worktree ("Local DeBERTa
cross-encoder model is not available"; the worktree has no `models/`):

```
tests.test_api.test_attempt_manifest_pg::test_manifest_real_test_turn_and_child_job_correlation: passed 
tests.test_api.test_backstage_endpoints_pg::test_economics_matches_inspect_turn_for_a_test_turn: passed 
tests.test_api.test_scheduler_corpus_pg::test_scheduler_live_turn_starts_before_queued_render: passed 
tests.test_api.test_scheduler_pg::test_scheduler_embeds_rendered_experiences_and_skips_the_rest: passed 
tests.test_api.test_seat_policy_jobs_pg::test_accept_repin_and_scheduler_use_literal_seat_models: passed 
tests.test_cli_inspect_pg::test_continue_waits_then_inspect_reads_the_played_clone: passed 
tests.test_embedding_table_ownership_pg::test_embedding_job_source_path_propagates_ensure_failure: passed 
tests.test_lore.test_baseline_fingerprint_refresh_pg::test_divergence_fingerprint_refresh_preserves_continuation: passed 
tests.test_lore.test_logon_lazy_init::test_lore_keeps_logon_lazy: passed 
tests.test_lore.test_pass2_baseline_pg::test_story_settings_pinned_window_survives_accepted_turn: passed 
tests.test_lore.test_runtime_config::test_lore_honors_runtime_config_for_both_storyteller_seats: passed 
tests.test_lore.test_runtime_config::test_explicit_lore_settings_path_beats_runtime_environment: passed 
tests.test_lore.test_runtime_config::test_lore_without_runtime_environment_falls_back_to_repo_root: passed 
tests.test_lore.test_runtime_config::test_lore_instances_keep_independent_memnon_configuration: passed 
tests.test_lore.test_scene_order_render::test_recent_warm_window_ends_at_historical_parent: passed 
tests.test_lore.test_window_coverage_pg::test_window_coverage_is_written_only_from_post_render_kept_chunks: passed 
tests.test_lore.test_window_coverage_pg::test_historical_coverage_matches_rendered_prefix[5-1]: passed 
tests.test_lore.test_window_coverage_pg::test_historical_coverage_matches_rendered_prefix[15-1]: passed 
tests.test_lore.test_window_coverage_pg::test_historical_coverage_matches_rendered_prefix[15-2500]: passed 
tests.test_lore.test_window_coverage_pg::test_removed_tokens_reach_real_attempt_manifest_and_observation[two_pass]: passed 
tests.test_lore.test_window_coverage_pg::test_removed_tokens_reach_real_attempt_manifest_and_observation[single_pass]: passed 
tests.test_memnon_cross_encoder_dependencies::test_local_deberta_cross_encoder_reranks_minimal_pair: ['skipped'] ['Local DeBERTa cross-encoder model is not available']
tests.test_memnon_embedding_cache::test_memnon_close_disposes_engine: passed 
tests.test_memnon_embedding_cache::test_per_turn_lore_stacks_share_embedder_and_close: passed 
tests.test_memnon_runtime_config::test_memnon_uses_runtime_config_instead_of_legacy_settings_path: passed 
tests.test_memnon.test_source_embeddings::test_experiences_load_and_stamp_only_valid_rendered_rows: passed 
tests.test_memnon.test_source_embeddings::test_wrappers_are_the_shared_orchestrator: passed 
tests.test_orrery.test_experiences::test_embedding_upsert_binds_each_correct_experience_id: passed 
28 marked testcases
```

Offline, as CI runs it, then without `-m` (merged tree at `9a0714d7`):

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -m 'not requires_local_models' tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3247 passed, 675 skipped, 22 deselected, 8 warnings in 653.89s (0:10:53)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -m 'not requires_local_models' tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1541 skipped, 6 deselected, 7 warnings in 43.51s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3247 passed, 697 skipped, 8 warnings in 661.35s (0:11:01)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1547 skipped, 7 warnings in 44.49s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_offline_ci_workflow.py tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
130 passed, 5 warnings in 15.51s
```

## Second Merge of `origin/main` (`b0e9cb77`)

`origin/main` moved to `b0e9cb77` (#1165, #1162) before the push. The merge
re-stamps `AGENTS.md` to `b0e9cb77`, and re-stamps
`docs/decisions/0076-the-offline-merge-gate.md` (added by #1162; canonical,
declares `pytest.ini` as a source; it records Decisions 816-D1 to 816-D11,
which this branch implements, so its text stays accurate):

```
E         Left contains one more item: 'docs/decisions/0076-the-offline-merge-gate.md: pytest.ini changed since the merge base b0e9cb77af52 without a re-stamped verified_commit'
```

After the re-stamp:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_offline_ci_workflow.py tests/test_reachability.py tests/test_doc_front_matter.py tests/test_cli_reference_doc.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
163 passed in 16.73s
```

The union grep now also lists `tests/test_ir_eval_v2/test_ensemble_parity_pg.py`
(#1165). An audit run with the edit applied over it and over the five set
files the merge changed (`tests/test_memnon_embedding_cache.py`,
`tests/test_lore/test_runtime_config.py`,
`tests/test_memnon/test_source_embeddings.py`,
`tests/test_presence_boost_pg.py`, `tests/test_memnon_embedding_contract.py`),
no `-m` (load `19:43 up 8:21, load averages: 12.05 13.92 14.72`;
`load_settings check exit 0`; `restore exit 0`):

```
        missing folder or a file in its place is never passed to ``from_pretrained``
        missing folder or a file in its place is never passed to ``from_pretrained``
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_memnon_embedding_cache.py::test_memnon_close_disposes_engine
FAILED tests/test_memnon_embedding_cache.py::test_per_turn_lore_stacks_share_embedder_and_close
FAILED tests/test_lore/test_runtime_config.py::test_lore_honors_runtime_config_for_both_storyteller_seats
FAILED tests/test_lore/test_runtime_config.py::test_explicit_lore_settings_path_beats_runtime_environment
FAILED tests/test_lore/test_runtime_config.py::test_lore_without_runtime_environment_falls_back_to_repo_root
FAILED tests/test_lore/test_runtime_config.py::test_lore_instances_keep_independent_memnon_configuration
FAILED tests/test_memnon/test_source_embeddings.py::test_experiences_load_and_stamp_only_valid_rendered_rows
FAILED tests/test_memnon/test_source_embeddings.py::test_wrappers_are_the_shared_orchestrator
8 failed, 37 passed, 5 warnings in 52.13s
```

The eight failures are all already-marked tests (artifact failures, R in the
failure message); the new `test_ensemble_parity_pg.py` passes under the edit
and is not marked.

Offline on the final merged tree, as CI runs it:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -m 'not requires_local_models' tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3271 passed, 679 skipped, 22 deselected, 8 warnings in 651.06s (0:10:51)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -m 'not requires_local_models' tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1541 skipped, 6 deselected, 7 warnings in 44.10s
```

## Static Checks

Black, flake8 and mypy on `tests/test_offline_ci_workflow.py` and the 18
changed test files (`git diff --name-only origin/main -- tests`); the
`origin/main` versions were checked out in place, checked, and restored with
`git checkout HEAD -- <files>`.

```
$ black --check <19 files>
19 files would be left unchanged.
$ flake8 <19 files>: 69 diagnostics; origin/main versions: 69 diagnostics.
  Normalized (line and column numbers removed) the two lists are identical:
  flake8: no new diagnostics. tests/test_offline_ci_workflow.py: 0.
$ $PY -m mypy --explicit-package-bases <19 files>
Found 43 errors in 10 files (checked 19 source files)
$ $PY -m mypy --explicit-package-bases <18 origin/main versions>
Found 43 errors in 10 files (checked 18 source files)
  Normalized lists identical: mypy: no new diagnostics. tests/test_offline_ci_workflow.py: 0.
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

Pre-existing diagnostics (untouched lines): E501 in the SQL and JSON literals
of the PostgreSQL tests, F811 `mock_openai_server` fixture redefinitions in
`test_scheduler_pg.py` and `test_scheduler_corpus_pg.py`, F401 in
`test_logon_lazy_init.py` and `test_memnon_embedding_cache.py`; mypy's 43
errors in 10 files (`<scratch>/mypy-base.txt`).

## CI Runs

Every run is on PR #1167 (`pull_request`, so the checkout is the PR merge
ref). Logs: `<scratch>/ci1-*.log`, `<scratch>/ci2-*.log`,
`<scratch>/ci3-*.log`.

### Run 1: https://github.com/pythagorakase/nexus/actions/runs/40429661948

Head `0ff505db`. Conclusion: failure. `offline-tests`: failure (first suite
red; the second suite step was skipped). `ui-tests`: failure.

```
FAILED tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit - AssertionError: assert ['AGENTS.md: ...ified_commit'] == []
  Left contains one more item: 'AGENTS.md: docs/agent_workflow.md, pytest.ini changed since the merge base e058005f8df0 without a re-stamped verified_commit'
FAILED tests/test_lore/test_token_budget.py::TestTokenBudgetManager::test_real_local_model_produces_positive_allocations - ValueError: Model 'nousresearch/hermes-4-70b': tokenizer_repository 'NousResearch/Hermes-4-70B' at tokenizer_revision 'd5dec2bd6b3930a09ddefd0b7fc6523fe0720d09' is not in the local Hugging Face cache. Run `nexus models fetch` to download it.
FAILED tests/test_lore/test_token_estimator.py::test_registry_token_estimator[nousresearch/hermes-4-70b] - ValueError: (same, Hermes-4-70B)
FAILED tests/test_lore/test_token_estimator.py::test_registry_token_estimator[nousresearch/hermes-4.3-36b] - ValueError: ... 'NousResearch/Hermes-4.3-36B' at tokenizer_revision '3899db2b6c4b35f16bde3b570bb7dd2775d56161' is not in the local Hugging Face cache.
FAILED tests/test_lore/test_token_estimator.py::test_registry_token_estimator[deepseek/deepseek-v4-pro] - ValueError: ... 'deepseek-ai/DeepSeek-V4-Pro' ...
FAILED tests/test_lore/test_token_estimator.py::test_registry_token_estimator[nousresearch/hermes-4-405b] - ValueError: ... 'NousResearch/Hermes-4-405B' ...
FAILED tests/test_lore/test_token_estimator.py::test_registry_token_estimator[minimax/minimax-m3] - ValueError: ... 'MiniMaxAI/Minimax-M3' ...
FAILED tests/test_lore/test_turn_cycle.py::test_process_user_input_uses_provider_profile_budget[nousresearch/hermes-4-70b-local-local-32000] - ValueError: (same, Hermes-4-70B)
FAILED tests/test_runtime/test_supervisor.py::test_failed_start_keeps_the_record_when_the_writer_probe_cannot_run - FileNotFoundError: [Errno 2] No such file or directory: '/tmp/pytest-of-runner/pytest-0/test_failed_start_keeps_the_re0/state/echo.log'
9 failed, 3277 passed, 683 skipped, 22 deselected, 8 warnings in 1117.85s (0:18:37)
```

- Freshness check: `origin/main` moved to `e058005f` (#1166) after the push,
  and a pull-request run diffs the merge ref against the newest `main`. Fixed
  by merging `origin/main` again and re-stamping `AGENTS.md` and decision 0076
  to `e058005f` (merge commit `19a2a363`).
- `test_failed_start_keeps_the_record_when_the_writer_probe_cannot_run`: on
  Linux the log writer had not yet created `echo.log` when the wait loop
  first read it (`tests/test_runtime/test_supervisor.py:1478`). Made portable
  in the test file (commit `2d38d73d`): the loop treats a missing file as not
  yet printed, under the same ten-second deadline, as the loop at `:813` of
  the same file already does. The test passes locally (73 passed for the
  file) and on runs 2 and 3.
- The seven tokenizer tests: reported, left red (see below).
- `ui-tests`: `src/state-shades.test.ts` fails at `:51`:

```
FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Command failed: git show 8ccd3008a48bdf8115232667399868e2bdf66f93:ui/client/src/index.css
fatal: path 'ui/client/src/index.css' exists on disk, but not in '8ccd3008a48bdf8115232667399868e2bdf66f93'
 ❯ src/state-shades.test.ts:51:17
 Test Files  1 failed | 43 passed (44)
      Tests  667 passed (667)
```

  `8ccd3008` is #1093's commit on `main`; the order's `ui-tests` checkout is
  depth 1, so the object is absent. Nothing under `ui/` was changed for it.

### Run 2: https://github.com/pythagorakase/nexus/actions/runs/40431989474

Head `19a2a363`. Conclusion: failure. `offline-tests`: failure (first suite;
second suite skipped). `ui-tests`: failure (same `state-shades.test.ts`
tail).

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_lore/test_token_budget.py::TestTokenBudgetManager::test_real_local_model_produces_positive_allocations - ValueError: Model 'nousresearch/hermes-4-70b': tokenizer_repository 'NousResearch/Hermes-4-70B' at tokenizer_revision 'd5dec2bd6b393...
FAILED tests/test_lore/test_token_estimator.py::test_registry_token_estimator[nousresearch/hermes-4-70b] - ...
FAILED tests/test_lore/test_token_estimator.py::test_registry_token_estimator[nousresearch/hermes-4.3-36b] - ...
FAILED tests/test_lore/test_token_estimator.py::test_registry_token_estimator[deepseek/deepseek-v4-pro] - ...
FAILED tests/test_lore/test_token_estimator.py::test_registry_token_estimator[nousresearch/hermes-4-405b] - ...
FAILED tests/test_lore/test_token_estimator.py::test_registry_token_estimator[minimax/minimax-m3] - ...
FAILED tests/test_lore/test_turn_cycle.py::test_process_user_input_uses_provider_profile_budget[nousresearch/hermes-4-70b-local-local-32000] - ...
7 failed, 3279 passed, 683 skipped, 22 deselected, 8 warnings in 786.44s (0:13:06)
```

### Run 3: https://github.com/pythagorakase/nexus/actions/runs/40433497563

Head `db84d6fc`, a scratch commit that added `if: ${{ !cancelled() }}` to the
second suite step so that the second suite would run on Linux despite the
red first suite; the next commit reverts it, so the committed workflow is
the ordered one. Conclusion: failure. `offline-tests`: first suite failure
(the same seven tokenizer tests, `7 failed, 3279 passed, 683 skipped, 22
deselected in 1081.70s`), second suite success:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1910 passed, 1541 skipped, 6 deselected, 7 warnings in 89.60s (0:01:29)
```

`ui-tests`: failure, the same `state-shades.test.ts:51` tail
(`Test Files 1 failed | 43 passed (44)`, `Tests 672 passed (672)`).

### Left Red and Reported

The seven tokenizer tests fail only on Linux CI and pass locally, where the
owner's Hugging Face cache holds the pinned tokenizers:

- `tests/test_lore/test_token_budget.py::TestTokenBudgetManager::test_real_local_model_produces_positive_allocations`
- `tests/test_lore/test_token_estimator.py::test_registry_token_estimator[nousresearch/hermes-4-70b]`,
  `[nousresearch/hermes-4.3-36b]`, `[deepseek/deepseek-v4-pro]`,
  `[nousresearch/hermes-4-405b]`, `[minimax/minimax-m3]`
- `tests/test_lore/test_turn_cycle.py::test_process_user_input_uses_provider_profile_budget[nousresearch/hermes-4-70b-local-local-32000]`

The raise is in `nexus/telemetry/prompt_window.py:368` and `:386`
(`TokenizerNotCachedError`, then a `ValueError` that says the tokenizer is
not in the local Hugging Face cache and to run `nexus models fetch`): the pinned tokenizers of #1126
(landed in `a8c6e3f5` after the order was written) load only from the local
cache. The fix is not in the failing test files (it needs the cache filled on
the runner, a workflow or `nexus/` change, or a marker decision), so under
the order's Sequencing they are left red.

