# 802-S3 Free Proofs (Verbatim Tails at 7f2a6dd7)

The builder's stop-report kept these in its scratch logs; the coordinator records them here after the Astra review of PR #1175 asked for traceable tails. The paid run's evidence file (`verification.md`) is written after a green retry (#1174 first).

## PostgreSQL proof set (commit 7f2a6dd7; `tests/test_api/test_attempt_manifest_pg.py tests/test_api/test_backstage_endpoints_pg.py tests/test_live_gate_clones_pg.py tests/test_turn_observation.py tests/test_golden_path_run_config.py`, `-p tests.dbname_audit`, gateway variables unset)

```text
tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/convert_slow_tokenizer.py:559: UserWarning: The sentencepiece tokenizer that you are converting to a fast tokenizer uses the byte fallback option which is not implemented in the fast tokenizers. In practice this means that the fast version of the tokenizer can produce unknown tokens whereas the sentencepiece version would have converted these unknown tokens into a sequence of byte tokens matching the original piece of text.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 15 targets: postgres, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_778s6a_backstage_*, qa640_778s6a_empty_*, qa640_800b_inspect_*, qa640_802_reported_*, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*, qa640_uib_turn_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
71 passed, 9 warnings in 70.97s (0:01:10)
```

## Offline suite, part 1 (`tests --ignore=tests/test_api --ignore=tests/test_orrery`)

```text
tests/test_memnon_cross_encoder_artifact.py::test_qwen3_loads_its_local_folder_and_scores
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/tokenization_utils_base.py:2718: UserWarning: `max_length` is ignored when `padding`=`True` and there is no truncation strategy. To pad to max length, use `padding='max_length'`.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3287 passed, 703 skipped, 8 warnings in 706.25s (0:11:46)
```

## Offline suite, part 2 (`tests/test_api tests/test_orrery`)

```text

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1570 skipped, 7 warnings in 53.38s
```

## Reachability and document front matter

```text
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
149 passed, 5 warnings in 18.26s
```

## Red run A (`+1` planted in `_critical_path_totals`; reverted)

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa640_764_turn_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation
1 failed, 9 warnings in 19.86s
```

## Red run B (the `usage_dir` line deleted; reverted)

```text

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_golden_path_run_config.py::test_golden_run_config_pins_an_absolute_usage_dir[no_override]
FAILED tests/test_golden_path_run_config.py::test_golden_run_config_pins_an_absolute_usage_dir[override]
2 failed, 5 warnings in 1.11s
```

## mypy on the changed files, HEAD (`--explicit-package-bases`)

```text
tests/test_golden_path_live.py:75: error: Library stubs not installed for "requests"  [import-untyped]
tests/test_golden_path_live.py:75: note: Hint: "python3 -m pip install types-requests"
tests/test_golden_path_live.py:75: note: (or run "mypy --install-types" to install all missing stub packages)
tests/test_golden_path_live.py:75: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
tests/test_golden_path_live.py:274: error: Item "None" of "WizardCache | None" has no attribute "thread_id"  [union-attr]
tests/test_golden_path_live.py:274: error: Argument "thread_id" to "confirm_artifact" has incompatible type "str | Any | None"; expected "str"  [arg-type]
tests/test_golden_path_live.py:276: error: Item "None" of "WizardCache | None" has no attribute "artifact_token"  [union-attr]
tests/test_golden_path_live.py:276: error: Argument "artifact_token" to "confirm_artifact" has incompatible type "str | Any | None"; expected "str"  [arg-type]
tests/test_api/test_attempt_manifest_pg.py:10: error: Library stubs not installed for "requests"  [import-untyped]
Found 6 errors in 2 files (checked 5 source files)
```

## mypy on the origin/main versions of the pre-existing changed files

```text
tests/test_golden_path_live.py:71: error: Library stubs not installed for "requests"  [import-untyped]
tests/test_golden_path_live.py:71: note: Hint: "python3 -m pip install types-requests"
tests/test_golden_path_live.py:71: note: (or run "mypy --install-types" to install all missing stub packages)
tests/test_golden_path_live.py:71: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
tests/test_golden_path_live.py:256: error: Item "None" of "WizardCache | None" has no attribute "thread_id"  [union-attr]
tests/test_golden_path_live.py:256: error: Argument "thread_id" to "confirm_artifact" has incompatible type "str | Any | None"; expected "str"  [arg-type]
tests/test_golden_path_live.py:258: error: Item "None" of "WizardCache | None" has no attribute "artifact_token"  [union-attr]
tests/test_golden_path_live.py:258: error: Argument "artifact_token" to "confirm_artifact" has incompatible type "str | Any | None"; expected "str"  [arg-type]
tests/test_golden_path_live.py:483: error: Value of type "Item | Container" is not indexable  [index]
tests/test_golden_path_live.py:483: error: Unsupported target for indexed assignment ("Any | Item | Container")  [index]
tests/test_golden_path_live.py:484: error: Unsupported target for indexed assignment ("Item | Container")  [index]
tests/test_golden_path_live.py:485: error: Unsupported target for indexed assignment ("Item | Container")  [index]
tests/test_golden_path_live.py:486: error: Unsupported target for indexed assignment ("Item | Container")  [index]
tests/test_golden_path_live.py:488: error: Value of type "Item | Container" is not indexable  [index]
tests/test_golden_path_live.py:488: error: Value of type "Any | Item | Container" is not indexable  [index]
tests/test_golden_path_live.py:488: error: Unsupported target for indexed assignment ("Any | Item | Container")  [index]
tests/test_api/test_attempt_manifest_pg.py:10: error: Library stubs not installed for "requests"  [import-untyped]
Found 14 errors in 2 files (checked 3 source files)
```

## flake8, HEAD

```text
tests/test_api/test_attempt_manifest_pg.py:83:89: E501 line too long (131 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:134:89: E501 line too long (121 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:138:89: E501 line too long (138 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:142:89: E501 line too long (126 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:158:89: E501 line too long (166 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:163:89: E501 line too long (106 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:239:89: E501 line too long (100 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:260:89: E501 line too long (96 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:448:89: E501 line too long (131 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:456:89: E501 line too long (125 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:487:89: E501 line too long (111 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:491:89: E501 line too long (122 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:517:89: E501 line too long (93 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:534:89: E501 line too long (118 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:554:89: E501 line too long (91 > 88 characters)
```

## flake8, origin/main versions

```text
tests/test_api/test_attempt_manifest_pg.py:82:89: E501 line too long (131 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:133:89: E501 line too long (121 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:137:89: E501 line too long (138 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:141:89: E501 line too long (126 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:157:89: E501 line too long (166 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:162:89: E501 line too long (106 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:238:89: E501 line too long (100 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:259:89: E501 line too long (96 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:441:89: E501 line too long (131 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:449:89: E501 line too long (125 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:480:89: E501 line too long (111 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:484:89: E501 line too long (122 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:510:89: E501 line too long (93 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:527:89: E501 line too long (118 > 88 characters)
tests/test_api/test_attempt_manifest_pg.py:547:89: E501 line too long (91 > 88 characters)
```

## The paid golden-path run (802-D11; lane 8022; 2026-10-26 21:28-21:41 CDT; exit 1)

```text
ERROR tests/test_golden_path_live.py::test_stage1_retrograde_cold_start - Run...
ERROR tests/test_golden_path_live.py::test_stage2_turns_played - RuntimeError...
ERROR tests/test_golden_path_live.py::test_stage3_chunk_persistence_and_incubator
ERROR tests/test_golden_path_live.py::test_stage4_embedding_lifecycle - Runti...
ERROR tests/test_golden_path_live.py::test_stage5_retrograde_history_retrievable
ERROR tests/test_golden_path_live.py::test_stage6_orrery_promotion_narration_bleed
ERROR tests/test_golden_path_live.py::test_stage7_runtime_maturation - Runtim...
ERROR tests/test_golden_path_live.py::test_stage8_server_log_clean - RuntimeE...
ERROR tests/test_golden_path_live.py::test_stage9_turn_observation - RuntimeE...
9 errors in 795.07s (0:13:15)
```

## Usage of the paid run (from `<basetemp>/golden_usage0`, `summarize_usage(day=2026-10-27)`)

18 events, 18 calls, all `openai gpt-6-astra`: input 250,824, output 24,983, total 275,807, cached input 75,310, reasoning 5,790. Seats: trait_input_derivation 1 (2,309/461), retrograde_seed_candidates 1 (25,871/4,775), retrograde_seed_selection 1 (6,329/501), retrograde_expansion 1 (14,518/3,088), skald_single_pass 1 (17,083/955), skald_writer 6 (74,533/8,347), gaia 6 (109,386/6,686), experience_renderer 1 (795/170). No other ledger was touched (the worktree has no `.nexus/runtime/usage`). The failure at turn 7 is #1174.
