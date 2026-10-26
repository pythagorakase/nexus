# Verification: Redaction, `_stop_pid` Reaping and the Probe dictConfig (#842)

Work order 842-S5S6S7, branch `claude/842-redaction-and-stop-pid`, cut from
`origin/main` at `c7ae2988`. No migration, no paid call, no gateway lane, no
write to any `save_NN`, `NEXUS_template` or `ref_codex_bakeoff_2026_07`. The
only database written is the `qa640_842s5_redaction_*` clone that
`tests/pg_fixtures.py` creates and drops.

## Cited Lines, Checked at `c7ae2988`

Every line the order cites was read before editing and matched:

- INFO: `nexus/api/narrative.py:1023`; `nexus/agents/lore/lore.py:354`, `:356`,
  `:547`; `nexus/agents/memnon/memnon.py:1465`;
  `nexus/agents/memnon/utils/alias_search.py:240`;
  `nexus/agents/memnon/utils/db_access.py:609-611`;
  `nexus/api/wizard_chat.py:753-757`; `nexus/memory/manager.py:897-901`;
  `nexus/api/new_story_db_mapper.py:249`, `:269`.
- WARNING: `nexus/agents/lore/logon_utility.py:336`;
  `nexus/api/choice_handling.py:112-114`.
- ERROR: `memnon.py:1473`; `wizard_chat.py:906`; `new_story_db_mapper.py:251`,
  `:271`; `scripts/api_openrouter.py:482-484`, `:505-507`.
- `nexus.toml:1455` is `level = "INFO"`; `docs/runtime.md:291` ends "kept.".
- `nexus/runtime/supervisor.py:1008-1019` (`_stop_pid`, three `_pid_alive`
  calls), `:57-58` (imports of `pid_alive as _pid_alive` and
  `process_running`); `nexus/runtime/log_capture.py:316-326`
  (`process_running`).
- `tests/test_runtime/test_supervisor.py:1021-1022` (`os.waitpid(pid, 0)`).
- `scripts/qa_shift/card_identity_probe.py:535-541`,
  `scripts/qa_shift/long_absence_probe.py:264-270` (`basicConfig` then
  `uvicorn.run` without `log_config`); `nexus/runtime/logging_config.py:105`
  (`"disable_existing_loggers": False`).

## Scanner List on the Unchanged Tree (Test 1 Red Run)

`tests/test_runtime/test_log_redaction.py` written first, run against the
unchanged product code. Exactly 17 calls, every order item 1 site except
`wizard_chat.py:906` (argument `e`) and `logon_utility.py:336` (argument
`value`):

```
nexus/agents/lore/lore.py:354 user_input [process_turn]
nexus/agents/lore/lore.py:356 note [process_turn]
nexus/agents/lore/lore.py:547 directive [_process_single_directive]
nexus/agents/memnon/memnon.py:1465 query [query_memory]
nexus/agents/memnon/memnon.py:1473 query [query_memory]
nexus/agents/memnon/utils/alias_search.py:240 query_text [hybrid_alias_search]
nexus/agents/memnon/utils/db_access.py:609 query_text [execute_multi_model_hybrid_search]
nexus/api/choice_handling.py:112 raw [parse_choice_object]
nexus/api/narrative.py:1023 resolved_user_text [continue_narrative]
nexus/api/new_story_db_mapper.py:249 title [save_story_seed]
nexus/api/new_story_db_mapper.py:251 title [save_story_seed]
nexus/api/new_story_db_mapper.py:269 title [save_story_seed]
nexus/api/new_story_db_mapper.py:271 title [save_story_seed]
nexus/api/wizard_chat.py:753 ui_choices [new_story_chat_endpoint]
nexus/memory/manager.py:897 user_input [_is_simple_choice]
scripts/api_openrouter.py:482 text [_get_completion_http]
scripts/api_openrouter.py:505 text [_get_completion_http]
```

The real-path alias test failed in the same run, in its INFO case:

```
E   AssertionError: (20, "INFO     nexus.memnon.alias_search:alias_search.py:240 Query 'qa842-sentinel Ask Kessa Brin what she remembers' ...
E   assert ('qa842-sentinel Ask Kessa Brin what she remembers' in "INFO ... Query 'qa842-sentinel Ask Kessa Brin what she remembers' conta...") is False
FAILED tests/test_runtime/test_log_redaction.py::test_no_story_text_reaches_info_or_above
FAILED tests/test_runtime/test_log_redaction.py::test_alias_search_logs_query_text_only_at_debug
2 failed, 2 passed in 4.04s
dbname audit: owner targets: none
```

## Exception-Disposition Baseline Keys Removed

```
nexus/agents/lore/logon_utility.py|_coerce_mapping|5a7f261c3d14193f407fdf2ddd0163b1c28355ff4255a33ce45653bccb198c7f|1
nexus/agents/memnon/memnon.py|MEMNON.query_memory|9ec0e1a08d1d273e569bf018c730475a6f3dbdd8669d449b100e7defec5fd4b1|1
nexus/api/choice_handling.py|parse_choice_object|ed36ae0ad120d998526ffd76bed048413133af7e5582ad7b47eafe66ce4576b1|1
scripts/api_openrouter.py|OpenRouterProvider._get_completion_http|cc6ad09a674e043b3961dd6371c9c8912cf4fff878f98854583d666516080b1c|1
```

Each handler carries the order's marker verbatim on its `except` line, in the
Black-parenthesized form of `nexus/runtime/log_capture.py:87-94`; the marker
lines measure 84, 88, 86 and 85 columns.

```
$ python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

## Test 2 Red Run (Unchanged `_stop_pid`)

```
>           assert elapsed < 2, elapsed
E           AssertionError: 5.225126583000019
E           assert 5.225126583000019 < 2
tests/test_runtime/test_supervisor.py:1047: AssertionError
>           with pytest.raises(ChildProcessError):
E           Failed: DID NOT RAISE <class 'ChildProcessError'>
tests/test_runtime/test_supervisor.py:1023: Failed
2 failed, 70 deselected, 5 warnings in 7.24s
```

The second failure is the converted stale assertion in
`test_check_children_stops_a_service_whose_writer_died`: the unchanged
`_stop_pid` left the stopped child unreaped.

## Test 3 Red Run (Scratch Plant Without `log_config=`, Reverted)

```
E       AssertionError: assert {'host': '127... 'port': 8015} == {'host': '127... 'port': 8015}
E         Right contains 1 more item:
E         {'log_config': {'disable_existing_loggers': False,
E       AssertionError: assert {'host': '127... 'port': 8018} == {'host': '127... 'port': 8018}
E         Right contains 1 more item:
2 failed, 55 deselected, 5 warnings in 1.28s
```

## PostgreSQL Proof (`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` Unset)

Load before each piece stayed between 4 and 8 (cap 24); no wait was needed.
The order's single command was split into four pieces, run serially:

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
248 passed in 148.10s (0:02:28)

$ ... tests/test_slot_routed_entrypoints.py tests/test_memnon/test_ann_gate.py tests/test_lore/test_memory_manager.py tests/test_lore/test_turn_cycle.py tests/test_lore/test_lore_retrieve_context.py tests/test_api/test_wizard_chat_validation.py tests/test_api/test_wizard_weird_level.py tests/test_api/test_wizard_confirmation_pg.py tests/test_api/test_genesis_fingerprint.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
195 passed, 1 skipped, 5 warnings in 97.14s (0:01:37)

$ ... tests/test_native_structured_output.py tests/test_orrery_tag_validation.py tests/test_idf_dictionary_pg.py tests/test_memnon_model_failures_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
208 passed, 10 warnings in 94.69s (0:01:34)

$ ... tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
10 passed, 2 skipped, 2 warnings in 40.83s

$ psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_842s5%'"
(no rows)
```

The single skip in the second piece is `tests/test_memnon/test_ann_gate.py`'s
`@requires_corpus` test, and the two in the fourth are the card-identity
corpus probes; both need `NEXUS_RUN_CORPUS=1`, which the common rules reserve.

## Offline Suites

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
3202 passed, 679 skipped, 8 warnings in 623.90s (0:10:23)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1910 passed, 1532 skipped, 7 warnings in 51.53s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
120 passed, 5 warnings in 29.36s
```

## Static Checks

- Black: `17 files would be left unchanged.` over every changed Python file.
- flake8: 263 diagnostics on the branch and 263 on the `origin/main` versions
  of the same files; with line numbers stripped the two multisets are
  identical (no new diagnostic). The added test file has none.
- mypy (`--explicit-package-bases`, fresh cache each side): with line numbers
  stripped, the diagnostics on the changed files are identical between the
  branch and an `origin/main` export of `nexus/`, `scripts/` and `tests/`; the
  added test file has none.

## Document Freshness

`git diff --name-only origin/main...HEAD` matched the declared `sources:` of
exactly the ten documents the order names. None of them describes these log
lines, `_stop_pid` or the probe launch; each `verified_commit` moved to the
merge base `c7ae2988d07b443f627a04d3a4eed1816b1cd438`: `AGENTS.md`,
`docs/turn_flow_sequence.md`, and decision records 0006, 0009, 0010, 0019,
0024, 0029, 0034 and 0048.
