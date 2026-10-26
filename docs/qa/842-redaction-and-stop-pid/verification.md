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

Rerun on `e9bb89e1` for the review round, with the eleven product files of order
item 1 checked out from `origin/main` and restored from `HEAD` afterwards
(`git status --short` clean after the restore). The scanner lists exactly 17
calls, every order item 1 site except `wizard_chat.py:906` (argument `e`) and
`logon_utility.py:336` (argument `value`). Command:

```
$ P=(nexus/api/narrative.py nexus/agents/lore/lore.py nexus/agents/memnon/memnon.py nexus/agents/memnon/utils/alias_search.py nexus/agents/memnon/utils/db_access.py nexus/api/wizard_chat.py nexus/memory/manager.py nexus/api/new_story_db_mapper.py nexus/agents/lore/logon_utility.py nexus/api/choice_handling.py scripts/api_openrouter.py)
$ git checkout origin/main -- "${P[@]}"
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime/test_log_redaction.py
$ git checkout HEAD -- "${P[@]}"
```

Log lines 17-44, verbatim (the scanner failure):

```
>       assert violations == [], (
            "Story or player text reaches INFO or above; log a metadata line at "
            "the level and the text on a paired DEBUG line (#842):\n" + _format(violations)
        )
E       AssertionError: Story or player text reaches INFO or above; log a metadata line at the level and the text on a paired DEBUG line (#842):
E         nexus/agents/lore/lore.py:354 user_input [process_turn]
E         nexus/agents/lore/lore.py:356 note [process_turn]
E         nexus/agents/lore/lore.py:547 directive [_process_single_directive]
E         nexus/agents/memnon/memnon.py:1465 query [query_memory]
E         nexus/agents/memnon/memnon.py:1473 query [query_memory]
E         nexus/agents/memnon/utils/alias_search.py:240 query_text [hybrid_alias_search]
E         nexus/agents/memnon/utils/db_access.py:609 query_text [execute_multi_model_hybrid_search]
E         nexus/api/choice_handling.py:112 raw [parse_choice_object]
E         nexus/api/narrative.py:1023 resolved_user_text [continue_narrative]
E         nexus/api/new_story_db_mapper.py:249 title [save_story_seed]
E         nexus/api/new_story_db_mapper.py:251 title [save_story_seed]
E         nexus/api/new_story_db_mapper.py:269 title [save_story_seed]
E         nexus/api/new_story_db_mapper.py:271 title [save_story_seed]
E         nexus/api/wizard_chat.py:753 ui_choices [new_story_chat_endpoint]
E         nexus/memory/manager.py:897 user_input [_is_simple_choice]
E         scripts/api_openrouter.py:482 text [_get_completion_http]
E         scripts/api_openrouter.py:505 text [_get_completion_http]
E       assert [('nexus/agen...y_text'), ...] == []
E         
E         Left contains 17 more items, first extra item: ('nexus/agents/lore/lore.py', 354, 'process_turn', 'user_input')
E         Use -v to get more diff

tests/test_runtime/test_log_redaction.py:197: AssertionError
```

Log lines 76-82, verbatim (the real-path alias test fails in its INFO case):

```
>                   assert (SENTINEL in caplog.text) is present, (level, caplog.text)
E                   AssertionError: (20, "INFO     nexus.memnon.alias_search:alias_search.py:240 Query 'qa842-sentinel Ask Kessa Brin what she remembers' ...alias_search:alias_search.py:244 Embedding table chunk_embeddings_0007d does not exist; alias vector search skipped
E                     ")
E                   assert ('qa842-sentinel Ask Kessa Brin what she remembers' in "INFO     nexus.memnon.alias_search:alias_search.py:240 Query 'qa842-sentinel Ask Kessa Brin what she remembers' conta....alias_search:alias_search.py:244 Embedding table chunk_embeddings_0007d does not exist; alias vector search skipped\n") is False
E                    +  where "INFO     nexus.memnon.alias_search:alias_search.py:240 Query 'qa842-sentinel Ask Kessa Brin what she remembers' conta....alias_search:alias_search.py:244 Embedding table chunk_embeddings_0007d does not exist; alias vector search skipped\n" = <_pytest.logging.LogCaptureFixture object at 0x10a145250>.text

tests/test_runtime/test_log_redaction.py:259: AssertionError
```

The last lines of the run, verbatim:

```
pg_dump: hint: Consider using a full dump instead of a --data-only dump to avoid this problem.
------------------------------ Captured log call -------------------------------
INFO     nexus.memnon.alias_search:alias_search.py:240 Query 'qa842-sentinel Ask Kessa Brin what she remembers' contains character references: []
WARNING  nexus.memnon.alias_search:alias_search.py:244 Embedding table chunk_embeddings_0007d does not exist; alias vector search skipped
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa640_842s5_redaction_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_runtime/test_log_redaction.py::test_no_story_text_reaches_info_or_above
FAILED tests/test_runtime/test_log_redaction.py::test_alias_search_logs_query_text_only_at_debug
2 failed, 2 passed in 4.49s
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

Rerun on `e9bb89e1` with `nexus/runtime/supervisor.py` checked out from
`origin/main` and restored from `HEAD` afterwards:

```
$ git checkout origin/main -- nexus/runtime/supervisor.py
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime/test_supervisor.py -k 'stop_pid or writer_died'
$ git checkout HEAD -- nexus/runtime/supervisor.py
```

Log lines 25-34 and 48 to the end, verbatim:

```
                "service."
            )
            with pytest.raises(RuntimeError_) as raised:
                supervisor._check_children(services, 5, {}, echo=False)
            assert str(raised.value) == expected
            # _stop_pid reaped its own child (#842).
>           with pytest.raises(ChildProcessError):
E           Failed: DID NOT RAISE <class 'ChildProcessError'>

tests/test_runtime/test_supervisor.py:1023: Failed
```

```
        writer_reaped = False
        try:
            started = time.monotonic()
            supervisor._stop_pid(pid)
            elapsed = time.monotonic() - started
>           assert elapsed < 2, elapsed
E           AssertionError: 5.2979927500000485
E           assert 5.2979927500000485 < 2

tests/test_runtime/test_supervisor.py:1047: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_runtime/test_supervisor.py::test_check_children_stops_a_service_whose_writer_died
FAILED tests/test_runtime/test_supervisor.py::test_stop_pid_reaps_its_own_child_inside_the_grace
2 failed, 70 deselected in 7.24s
```

The first failure is the converted stale assertion in
`test_check_children_stops_a_service_whose_writer_died`: the unchanged
`_stop_pid` left the stopped child unreaped.

## Test 3 Red Run (Scratch Plant Without `log_config=`, Reverted)

Rerun on `e9bb89e1`; the plant deletes the `log_config=` line from both probes and
`git checkout HEAD` reverts it (`git status --short` clean afterwards):

```
$ sed -i '' '/log_config=build_logging_config(runtime.logs),/d' scripts/qa_shift/card_identity_probe.py scripts/qa_shift/long_absence_probe.py
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_runtime/test_logging_config.py -k qa_probe
$ git checkout HEAD -- scripts/qa_shift/card_identity_probe.py scripts/qa_shift/long_absence_probe.py
```

Log lines 53-70 and 127-138 (one block per probe), then the last lines of the
run, verbatim:

```
        assert runtime is not None
>       assert call["kwargs"] == {
            "host": "127.0.0.1",
            "port": port,
            "log_config": json.loads(json.dumps(build_logging_config(runtime.logs))),
        }
E       AssertionError: assert {'host': '127... 'port': 8015} == {'host': '127... 'port': 8015}
E         
E         Omitting 2 identical items, use -vv to show
E         Right contains 1 more item:
E         {'log_config': {'disable_existing_loggers': False,
E                         'filters': {'successful_access': {'()': 'nexus.runtime.logging_config.SuccessfulAccessFilter',
E                                                           'exclude_paths': ['/health',
E                                                                             '/runtime/status']}},...
E         
E         ...Full output truncated (18 lines hidden), use '-vv' to show

tests/test_runtime/test_logging_config.py:809: AssertionError
```

```
E       AssertionError: assert {'host': '127... 'port': 8018} == {'host': '127... 'port': 8018}
E         
E         Omitting 2 identical items, use -vv to show
E         Right contains 1 more item:
E         {'log_config': {'disable_existing_loggers': False,
E                         'filters': {'successful_access': {'()': 'nexus.runtime.logging_config.SuccessfulAccessFilter',
E                                                           'exclude_paths': ['/health',
E                                                                             '/runtime/status']}},...
E         
E         ...Full output truncated (18 lines hidden), use '-vv' to show

tests/test_runtime/test_logging_config.py:809: AssertionError
```

```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_runtime/test_logging_config.py::test_qa_probe_gateways_use_the_shared_log_config[scripts.qa_shift.card_identity_probe-8015]
FAILED tests/test_runtime/test_logging_config.py::test_qa_probe_gateways_use_the_shared_log_config[scripts.qa_shift.long_absence_probe-8018]
2 failed, 55 deselected, 5 warnings in 1.62s
```

## PostgreSQL Proof (`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` Unset)

Rerun on `e9bb89e1` for the review round. `uptime` before each piece read a
one-minute load of 19.91, 7.56, 6.30 and 15.76 (cap 24); no wait was needed.
The order's single command was split into four pieces, run serially. Each
tail below runs from the guard line to the end of the output, verbatim.

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 19 targets: postgres, qa640_1013_readiness_* x2, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slot5_*, qa640_803s6_template_*, qa640_842s5_redaction_*, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
248 passed in 166.78s (0:02:46)
```

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_slot_routed_entrypoints.py tests/test_memnon/test_ann_gate.py tests/test_lore/test_memory_manager.py tests/test_lore/test_turn_cycle.py tests/test_lore/test_lore_retrieve_context.py tests/test_api/test_wizard_chat_validation.py tests/test_api/test_wizard_weird_level.py tests/test_api/test_wizard_confirmation_pg.py tests/test_api/test_genesis_fingerprint.py -rs
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 31 targets: postgres, qa640_766_schema_*, qa640_offline_gate_* x28, qa885_entrypoints_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [1] tests/test_memnon/test_ann_gate.py:120: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
195 passed, 1 skipped, 5 warnings in 107.35s (0:01:47)
```

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_native_structured_output.py tests/test_orrery_tag_validation.py tests/test_idf_dictionary_pg.py tests/test_memnon_model_failures_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 38 targets: postgres, qa762_corpus_copy_*, qa762_fresh_*, qa762_idf_* x19, qa762_other_*, qa_model_failures_* x15
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
208 passed, 10 warnings in 116.57s (0:01:56)
```

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py -rs
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 6 targets: postgres, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:54968 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:54977 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:54968 (psycopg2), save_04@local:54977 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
10 passed, 2 skipped, 2 warnings in 56.97s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```
$ psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_842s5%'"
(no output; exit 0)
```

The single skip in the second piece is `tests/test_memnon/test_ann_gate.py`'s
`@requires_corpus` test, and the two in the fourth are the card-identity
corpus probes; both need `NEXUS_RUN_CORPUS=1`, which the common rules reserve.

The review fix also ran on its own before the commit, verbatim from the guard
line:

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime/test_supervisor.py tests/test_runtime/test_supervisor_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa885_supervisor_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
85 passed in 88.57s (0:01:28)
```

## Offline Suites

Run on `45f80ec4` (the review fix changes only `_stop_pid`, whose tests ran in
the PostgreSQL pieces above on `e9bb89e1`). Each tail runs from the guard line to
the end, verbatim:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3202 passed, 679 skipped, 8 warnings in 623.90s (0:10:23)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1532 skipped, 7 warnings in 51.53s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 29.36s
```

On `e9bb89e1`:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
66 passed, 5 warnings in 8.11s

$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

## Static Checks

Run on `e9bb89e1` by this script (`$S` is the order's scratch directory; `FILES`
is the 17 changed Python files, `MAINFILES` the 16 of them that exist on
`origin/main`, exported with `git archive origin/main nexus scripts tests`):

```zsh
cd $WT
FILES=(${(f)"$(git diff --name-only origin/main...HEAD -- '*.py')"})
MAINFILES=(); for f in $FILES; do git cat-file -e origin/main:$f 2>/dev/null && MAINFILES+=$f; done
echo "== black (branch)"; $PY -m black --check $FILES 2>&1 | tail -1
echo "== flake8 (branch)"; $PY -m flake8 $FILES > $S/s2_flake8_branch.txt; echo "exit $? lines $(wc -l < $S/s2_flake8_branch.txt)"
rm -rf $S/s2_main; mkdir -p $S/s2_main
git archive origin/main nexus scripts tests .flake8 pyproject.toml | tar -x -C $S/s2_main
echo "== flake8 (origin/main export)"; (cd $S/s2_main && $PY -m flake8 $MAINFILES > $S/s2_flake8_main.txt); echo "exit $? lines $(wc -l < $S/s2_flake8_main.txt)"
echo "== mypy (branch)"; rm -rf $S/s2_mypycache_branch; $PY -m mypy --explicit-package-bases --cache-dir $S/s2_mypycache_branch $FILES > $S/s2_mypy_branch.txt 2>&1; echo "exit $?"; tail -1 $S/s2_mypy_branch.txt
echo "== mypy (origin/main export)"; rm -rf $S/s2_mypycache_main; (cd $S/s2_main && $PY -m mypy --explicit-package-bases --cache-dir $S/s2_mypycache_main $MAINFILES > $S/s2_mypy_main.txt 2>&1; echo "exit $?"); tail -1 $S/s2_mypy_main.txt
strip() { sed -E 's/^([^:]+):[0-9]+:([0-9]+:)?/\1:/' "$1" | grep -v '^Found \|^Success' | sort; }
echo "== flake8 diff (line numbers stripped; < main, > branch)"; diff <(strip $S/s2_flake8_main.txt) <(strip $S/s2_flake8_branch.txt); echo "diff exit $?"
echo "== mypy diff (line numbers stripped; < main, > branch)"; diff <(strip $S/s2_mypy_main.txt) <(strip $S/s2_mypy_branch.txt); echo "diff exit $?"
echo "== diagnostics on the added test file"; grep -c 'test_log_redaction' $S/s2_flake8_branch.txt $S/s2_mypy_branch.txt
echo "== mypy diff restricted to the changed files (line numbers stripped; < main, > branch)"
PAT="^($(print -r -- ${(j:|:)FILES} | sed 's/\./\\./g')):"
diff <(grep -E "$PAT" $S/s2_mypy_main.txt | sed -E 's/^([^:]+):[0-9]+:([0-9]+:)?/\1:/' | sort) <(grep -E "$PAT" $S/s2_mypy_branch.txt | sed -E 's/^([^:]+):[0-9]+:([0-9]+:)?/\1:/' | sort); echo "diff exit $?"
echo "changed-file mypy lines: main $(grep -cE "$PAT" $S/s2_mypy_main.txt) branch $(grep -cE "$PAT" $S/s2_mypy_branch.txt)"
```

Its output follows, with the unrestricted mypy diff (output lines 16-224)
elided. Every hunk of that diff is a deletion (`NdM` headers and `<` lines
only), and none of its lines names a changed file: the `origin/main` export
also reports diagnostics in modules mypy follows outside the changed files
(299 errors in 55 files against 124 in 11). The gate therefore compares the
changed files only, in the restricted diff at the end, which is empty:

```
== black (branch)
17 files would be left unchanged.
== flake8 (branch)
exit 1 lines      263
== flake8 (origin/main export)
exit 1 lines      263
== mypy (branch)
exit 1
Found 124 errors in 11 files (checked 17 source files)
== mypy (origin/main export)
exit 1
Found 299 errors in 55 files (checked 16 source files)
== flake8 diff (line numbers stripped; < main, > branch)
diff exit 0
== mypy diff (line numbers stripped; < main, > branch)
[209 lines of `<` diagnostics in files outside the changed set]
diff exit 1
== diagnostics on the added test file
/private/tmp/claude-501/-Users-pythagor-nexus/9dcd8ba0-5aed-4efa-8d64-38cffa54a15d/scratchpad/842-S5S6S7/s2_flake8_branch.txt:0
/private/tmp/claude-501/-Users-pythagor-nexus/9dcd8ba0-5aed-4efa-8d64-38cffa54a15d/scratchpad/842-S5S6S7/s2_mypy_branch.txt:0
== mypy diff restricted to the changed files (line numbers stripped; < main, > branch)
diff exit 0
changed-file mypy lines: main 161 branch 161
```

`flake8` on the branch (263 lines) and on the export (263 lines) differ only in
line numbers. Pre-existing diagnostics on lines this order kept verbatim:
`scripts/api_openrouter.py:487` and `:517` E501 (105 and 92 characters) are
the unchanged f-string arguments that the paired DEBUG lines keep, and were
E501 on `origin/main` at `:483` and `:506`; the order requires those
arguments unchanged.

## Document Freshness

`git diff --name-only origin/main...HEAD` matched the declared `sources:` of
exactly the ten documents the order names. None of them describes these log
lines, `_stop_pid` or the probe launch; each `verified_commit` moved to the
merge base `c7ae2988d07b443f627a04d3a4eed1816b1cd438`: `AGENTS.md`,
`docs/turn_flow_sequence.md`, and decision records 0006, 0009, 0010, 0019,
0024, 0029, 0034 and 0048.

## Review Round (`e9bb89e1`)

- `_stop_pid` keeps the last `process_running` result and probes again only
  while the pid is still held, so it never probes, and never signals, a pid its
  own probe already reaped and the system may reuse. It still has three
  `process_running` calls and no other liveness call. The supervisor tests, the
  red runs and the PostgreSQL pieces above all ran on this commit.
- The red-run and PostgreSQL blocks above are now the commands and the verbatim
  pytest output; the static checks record their script and output.
- Not changed in this round: `CharacterIdentityAmbiguity`'s "declared
  evidence" suffix (`nexus/presence/identity.py:143-144`) still reached WARNING
  through `nexus/telemetry/usage.py:54`. Coordinator ruling 1 later settled it;
  see Fix Round 3.

## Review Round 2 (`1bb472fb`)

- A second test was made stale by S6:
  `test_check_children_still_fails_a_live_child_without_its_writer` stops its
  child through `_check_children` -> `_stop_pid`, which now reaps it, and its
  `finally` still sent SIGKILL to that freed pid. It now asserts
  `os.waitpid(pid, os.WNOHANG)` raises `ChildProcessError` (comment
  `# _stop_pid reaped its own child (#842).`), sets `reaped = True`, and its
  `finally` signals and reaps the pid only when `reaped` is still `False`, the
  same guard as `test_check_children_stops_a_service_whose_writer_died`.
- Run on `1bb472fb` (one-minute load 5.30), with `NEXUS_GATEWAY_PORT`,
  `NEXUS_API_URL` and `NEXUS_SLOT` unset; Black and flake8 are clean on the
  changed file:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_runtime/test_supervisor.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
72 passed, 5 warnings in 31.36s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest tests/test_runtime/test_supervisor.py -k "writer_died or without_its_writer or stop_pid" -rA -q
PASSED tests/test_runtime/test_supervisor.py::test_check_children_stops_a_service_whose_writer_died
PASSED tests/test_runtime/test_supervisor.py::test_stop_pid_reaps_its_own_child_inside_the_grace
PASSED tests/test_runtime/test_supervisor.py::test_doctor_fails_a_live_service_without_its_writer
PASSED tests/test_runtime/test_supervisor.py::test_check_children_still_fails_a_live_child_without_its_writer

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py
66 passed, 5 warnings in 7.52s
```

- Still not changed in this round: the `CharacterIdentityAmbiguity` "declared
  evidence" text reaching WARNING through `nexus/telemetry/usage.py:54`
  (above). Fix Round 3 changes it under coordinator ruling 1.

## Fix Round 3: Coordinator Rulings 1 and 2 (`db73e43d`, `65e4031a`)

Both rulings are posted on PR #1155 and amend the order. `origin/main` was
still `c7ae2988` when this round started and when it was pushed, so no merge
was needed.

### Ruling 2: the SIGKILL Branch Reaps (`db73e43d`)

- `nexus/runtime/supervisor.py` `_stop_pid`: after `_signal_pid(pid, kill_sig)`
  the `time.sleep(0.2)` is replaced by a bounded poll. While
  `process_running(pid)` is true and `time.monotonic()` is under a second
  deadline of `stop_grace_seconds` (no new setting), it sleeps 0.1 s.
  `process_running` reaps the killed child, so the method returns with the pid
  free; the docstring says so.
- New `test_stop_pid_reaps_a_child_it_had_to_kill`: the child sets
  `signal.signal(signal.SIGTERM, signal.SIG_IGN)`, touches a ready file and
  sleeps. The test waits for the ready file (so SIGTERM cannot land before the
  handler), then `_stop_pid(pid)` with `stop_grace_seconds = 0.5`. It asserts
  the call took at least 0.5 s (the SIGKILL branch ran) and that
  `os.waitpid(pid, os.WNOHANG)` raises `ChildProcessError`. The pid and writer
  guards match `test_stop_pid_reaps_its_own_child_inside_the_grace`.
- Red run: `nexus/runtime/supervisor.py` from `dac4cd8b` copied over the
  working file, the new test run, and the fixed file restored
  (`git diff --stat` showed only the round's intended edits after the restore):

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_runtime/test_supervisor.py -k "stop_pid_reaps_a_child_it_had_to_kill"
            started = time.monotonic()
            supervisor._stop_pid(pid)
            elapsed = time.monotonic() - started
            assert elapsed >= 0.5, elapsed
>           with pytest.raises(ChildProcessError):
E           Failed: DID NOT RAISE <class 'ChildProcessError'>

tests/test_runtime/test_supervisor.py:1087: Failed
...
FAILED tests/test_runtime/test_supervisor.py::test_stop_pid_reaps_a_child_it_had_to_kill
1 failed, 72 deselected, 5 warnings in 1.29s
```

- Green, on `db73e43d`:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_runtime/test_supervisor.py -k "stop_pid" -rA
PASSED tests/test_runtime/test_supervisor.py::test_stop_pid_reaps_its_own_child_inside_the_grace
PASSED tests/test_runtime/test_supervisor.py::test_stop_pid_reaps_a_child_it_had_to_kill
2 passed, 71 deselected, 5 warnings in 1.78s
```

### Ruling 1: Declared Evidence Only at DEBUG (`65e4031a`)

- `nexus/presence/identity.py` (`resolve_character_declaration`, the old
  `:142-144`): the reason no longer appends `"; declared evidence: "` and the
  text. It appends `f"; {len(evidence)} declared evidence values"`, and a new
  module logger writes `logger.debug("Ambiguous character declaration %r
  declared evidence: %s", name, "; ".join(evidence))`. Every
  `CharacterIdentityAmbiguity` reason comes from this function, so its message
  now holds names, ids, the ambiguity kind and counts.
  `nexus/telemetry/usage.py` is unchanged.
- Raise count, from `git grep -nE "raise (WireContractViolation|CharacterIdentityAmbiguity|CharacterNameRevealConflict)\(" nexus scripts`:
  21 raises. Four are `CharacterIdentityAmbiguity` (`identity.py:195` and
  `:276`, `presence_reconciliation.py:374`, `retrograde_persistence.py:2953`),
  14 are `CharacterNameRevealConflict` and 3 are `WireContractViolation`
  (`place_reference_validation.py:59`, `:62`, `roster.py:497`): 17 others. Of
  the four, `retrograde_persistence.py:2953` resolves `{"name": ...}` only, so
  three could carry evidence.
- New `test_ambiguous_declaration_evidence_reaches_only_debug`
  (`tests/test_runtime/test_log_redaction.py`): an in-memory identity index
  with Silas Wren and Ada Wren, a declaration "Wren" with a summary, role and
  location, run through the real `validate_character_batch` inside the real
  `validation_attempt(None)`. The only WARNING record is `nexus.usage`'s wire
  rejection; none of the three texts appears in it or in the exception
  message; each appears at DEBUG; the message says `3 declared evidence
  values`.
- Red run: `nexus/presence/identity.py` from `dac4cd8b` copied over the
  working file, the new test run, and the fixed file restored:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_runtime/test_log_redaction.py -k ambiguous
>           assert all(text not in r.getMessage() for r in warnings), caplog.text
E           AssertionError: WARNING  nexus.usage:usage.py:54 Wire rejection session=None note={'rejection': 'wire-contract-violation', 'error': "Ambiguous character declaration 'Wren': partial or fuzzy name match; declared evidence: qa842-summary A courier who hums old union songs; qa842-role keeper of the dockside ledgers; qa842-location Pier Nine; candidates: Silas Wren (character id=1), Ada Wren (character id=2). Review requires same_as, create_new, or distinct_from."}
E             
E           assert False
E            +  where False = all(<generator object test_ambiguous_declaration_evidence_reaches_only_debug.<locals>.<genexpr> at 0x10e9e7bc0>)

tests/test_runtime/test_log_redaction.py:273: AssertionError
=========================== short test summary info ============================
FAILED tests/test_runtime/test_log_redaction.py::test_ambiguous_declaration_evidence_reaches_only_debug
1 failed, 4 deselected, 5 warnings in 0.33s
```

- Stale assertion made stale by the ruling: `tests/test_presence_roster_pg.py`
  `test_identity_frontier_location_narrows_without_resolving` asserted
  `"Hall" in caught.value.reason`. Hall is the frontier location, now evidence
  text at DEBUG. The assertion is now
  `caught.value.reason == "partial or fuzzy name match; 2 declared evidence values"`
  (the summary and Hall), which still proves the frontier location reached
  the evidence; the candidate-narrowing assertion is unchanged.
- `docs/runtime.md`: the #842 bullet gains one sentence: wire rejections and
  repairs log at WARNING with names, ids, tags, paths, counts and fixed text,
  and an ambiguous declaration's summary, role and location appear only on a
  DEBUG line (`nexus/presence/identity.py`). The `_WIRE_NOTES` allowlist reason
  now reads "wire notes hold names, ids, tags, paths, counts and fixed text (an
  ambiguous declaration's evidence goes to DEBUG), and feed the prompt-window
  ledger (842-D4)".
- No privacy-contract sentinel test failed on the new DEBUG line
  (`tests/test_native_structured_output.py`, `tests/test_orrery_tag_validation.py`
  below), so it stays.

### PostgreSQL Proof for This Round

Both runs used the tree committed as `65e4031a` (on top of `db73e43d`; the
commit followed the runs with no further edit), with `NEXUS_GATEWAY_PORT`,
`NEXUS_API_URL` and `NEXUS_SLOT` unset. The one-minute load was 21.00 before
the first run and 28.25 before the second; the second run started without the
wait loop the machine-load rule asks for above 24 (it took 14 s). Tails from
the guard line to the end, verbatim:

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime/test_log_redaction.py tests/test_runtime/test_supervisor.py tests/test_presence_roster_pg.py tests/test_orrery/test_character_identity_pg.py tests/test_orrery/test_identity_consumers_pg.py tests/test_orrery/test_retrograde_maturation.py tests/test_trait_compiler.py tests/test_doc_front_matter.py -rs
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 47 targets: postgres, qa640_840s2_drain_*, qa640_842s5_redaction_*, qa640_maturation799_*, qa640_roster798_* x43
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
261 passed in 154.53s (0:02:34)

$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_native_structured_output.py tests/test_orrery_tag_validation.py tests/test_orrery/test_card_identity.py -rs
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 5 targets: postgres, qa640_885_ren_replay_* x4
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
183 passed, 2 skipped, 2 warnings in 14.00s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

$ psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_842s5%'"
(no output; exit 0)
```

On `65e4031a`:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py
66 passed, 5 warnings in 6.86s

$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

### Static Checks for This Round

Files: `nexus/presence/identity.py`, `nexus/runtime/supervisor.py`,
`tests/test_runtime/test_log_redaction.py`, `tests/test_presence_roster_pg.py`,
`tests/test_runtime/test_supervisor.py`; compared against the same files at
`dac4cd8b` (flake8 on `git show` copies; mypy on a `git archive dac4cd8b`
export of `nexus`, `tests`, `scripts` and `pyproject.toml`), line numbers
stripped:

```
== black (branch)
5 files would be left unchanged.
== flake8: branch 18 lines, dac4cd8b 18 lines
flake8 diff exit 0
== mypy --explicit-package-bases, restricted to the five files
restricted diff exit 0
changed-file lines: base 25 branch 25
```

The 18 flake8 lines are pre-existing E501s on untouched lines of
`nexus/presence/identity.py` (SQL constants) and
`tests/test_presence_roster_pg.py`.

## Fix Round 4: Second-Pass Findings on Rulings 1 and 2

Two P3 findings, documentation only; no code or test changed.

- Raise-site line numbers. The raise list under "Ruling 1" cited
  `identity.py:184` and `:265`, and the PR body also cited `identity.py:188`.
  Those are the `c7ae2988` numbers; `65e4031a` added 11 lines above them. At
  this head `git grep -nE "raise (CharacterIdentityAmbiguity|CharacterNameRevealConflict)\(" nexus/presence/identity.py`
  prints `:195` and `:276` (`CharacterIdentityAmbiguity`) and `:199`
  (`CharacterNameRevealConflict`). The list above and the PR body now cite
  those. Every other line in the list is unchanged at this head.
- `docs/runtime.md` (#842 bullet). "Structured-output and validator payloads
  stay out of every level" contradicted the ruling-1 sentence that puts an
  ambiguous declaration's summary, role and location on a DEBUG line. It now
  states the contract it cites: "Structured-output and validator error
  messages carry no payload text at any level
  (`structured_output_error_text` in `nexus/api/native_structured_output.py`)."
  The ruling-1 sentence is unchanged.

Covering tests (load average 19.67 before the run):

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_runtime/test_log_redaction.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_842s5_redaction_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
71 passed in 11.49s
```
