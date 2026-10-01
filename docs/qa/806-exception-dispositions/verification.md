# 806-S4 Exception Dispositions Verification

Date: 2026-10-01 (America/Chicago). Refs #806. Coordinator Amendment 1 applied.
The accepted stop-report is retained as a dated historical section below.

Final source/inventory revision: `57a104461289fc9bd0cd35b8714722901c9bec4d`. Newest incorporated origin/main:
`2e70e9cb2c566f6f48e70ea84874670a719055f9`. The amended implementation is `4650ad215b99c1bcbca561330317f137490c6c2a`.
Core/API/Orrery offline partitions, standalone reachability, static checks, and
PostgreSQL safety attempts ran at 4650ad21. Main advanced during those gates with
#1086 (cooldown report); the branch incorporated it and reran the checker,
reachability, and changed cooldown tests together at 57a10446, then reran the
entire cross-version CLI matrix there. The new main operator has no handlers;
its additions do not change inventory or baseline. This record is a subsequent
documentation-only commit and does not claim earlier gates ran at its own hash.

## Result and Scope

All required proof gates passed, including the previously blocked reachability
assertion. This slice converts **no product handler**, adds no product marker,
and approves no legacy fallback. The 584-entry baseline moved byte-for-byte from
scripts/ to `config/exception_disposition_baseline.json`; the obsolete
classification row was removed, without changing tests/test_reachability.py.
Q10 and Q11 remain unchanged.

| Root | Total | Always Raises | Marked | Baseline Entries |
| --- | ---: | ---: | ---: | ---: |
| nexus/ | 507 | 226 | 0 | 281 |
| scripts/ | 356 | 52 | 1 | 303 |
| Total | 863 | 278 | 1 | 584 |

The one-handler difference from the original 862-handler syntax census is the
new checker reporting handler, marked fail and exiting 1. Non-exempt handlers:
585. Syntax counts and baseline membership are not approved dispositions.

## Files Changed

- `scripts/check_exception_dispositions.py`: stdlib-only collector, AST exemption, marker validation, stable identities, and shrink-only ratchet; baseline default now points to config/.
- `config/exception_disposition_baseline.json`: 584 unchanged legacy debt entries, relocated byte-for-byte; no legacy fallback is approved.
- `tests/test_scripts/test_check_exception_dispositions.py`: 68 real git/source/CLI proofs; temporary baseline parent is created in config/.
- `.pre-commit-config.yaml`: always-run hook with the exact required entry and an explicit config/ baseline description.
- `.github/workflows/exception-disposition-check.yml`: stdlib-only Python 3.11/3.12/3.13 matrix, complete history, and real event-base comparison.
- `config/reachability.toml`: checker operator and sorted checker classification only; the config/ baseline needs no classification.
- `CLAUDE.md`: only the required hook paragraph, amended to name config/.
- `docs/qa/806-exception-dispositions/verification.md`: current verification, exact proof tails, complete current inventory, and dated accepted stop-report.

## Verified Citations

- `.flake8:1-11` has no exception policy. The migration hook remains at `.pre-commit-config.yaml:36-48`; the new hook is `:49-57`. Both checker and config/ baseline are absent at the recorded origin/main (read-only `git ls-tree`), so comparison there is bootstrap.
- `nexus/agents/lore/utils/turn_cycle.py:376-377` logs requested-chunk lookup failure and continues; `:406-408` logs warm-slice failure and keeps assembled chunks; `:517-520` re-raises RuntimeError and only logs general Exception. These remain inventory examples, with no conversions.
- `scripts/check_migration_comments.py:94-97` freezes watermark 129; `:1641-1669` supplies the stdlib CLI/reporting model. `tests/test_schema_documentation_pg.py:136-157` rejects malformed and missing/stale baseline entries. These are unchanged.
- `pyproject.toml:9` supports Python 3.11 through 3.13. The accepted stop-report's original census was 507 nexus/ and 355 scripts/ handlers; direct Exception counts 153 and 204; bare counts 5 and 4; direct BaseException counts 9 and 1. It records 730 raw-dump differences among those 862 handlers between Python 3.11.12 and 3.13.5. Current inventory retains exactly those identities plus the one new marked checker handler; main changed two tag_writer.py source positions without changing identities. Canonical encoding is documented at `scripts/check_exception_dispositions.py:1-13`, implemented at `:169-222`, and freshly proved cross-version below.
- `.github/workflows/migration-comment-check.yml:8-31` is the unchanged CI model. The new matrix and event-base check are `.github/workflows/exception-disposition-check.yml:3-33`. `CLAUDE.md:20-26` keeps the existing hook list; `:28` is the only added paragraph.
- `config/reachability.toml:97-99` registers the checker; `:176-177` scopes classification to scripts/ and ir_eval/; `:274` classifies the checker as operator. The baseline is outside that scope. `docs/reachability.md:89-114` requires sorted, reasoned paths, including non-Python paths in scope.
- Collector: `scripts/check_exception_dispositions.py:374-430`; tokenizer-owned contracts: `:343-371`; ordered exits: `:249-321`; baseline validation and read-only git ratchet: `:467-535`; amended default: `:32`.

## Proof Environment and History Preservation

Every shell command ran in `/Users/pythagor/nexus/.claude/worktrees/806-exception-disposition-lint`. `$PY` is
`/Users/pythagor/nexus/.venv/bin/python`. Before proofs, the command
`PYTHONPATH=$PWD $PY -c 'import nexus; print(nexus.__file__)'` printed
`/Users/pythagor/nexus/.claude/worktrees/806-exception-disposition-lint/nexus/__init__.py`.
All scratch files, temporary test repositories, and logs are under
`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4`. `run_amendment_gate.py` there owns one foreground child at a time,
with an explicit 590-second timeout and a 120-second silence limit, and sets
TMPDIR, PYTHONPATH=$PWD, and the existing interpreter-only bin/ shim on PATH.
Core was split into all eight non-API/Orrery test subdirectories and the
remaining top-level partition; API and Orrery were run separately. These pieces
cover the complete requested offline partitions. No live-provider guard was
bypassed. No paid call, owner-database write, gateway start, or runtime change
occurred.

Commits dc903caf and 3d347913 are preserved with their original hashes and both
remain ancestors of HEAD. To satisfy preservation and the newest-main rebase,
main was incorporated by merges, followed by
`git rebase --rebase-merges=no-rebase-cousins origin/main`. A preliminary plain
rebase replayed them; its unpushed result was discarded by restoring the merge
checkpoint before using the preserving mode. No existing commit was amended,
squashed, or replaced in the delivered history. Ancestor checks for both originals
and origin/main all exited 0.

### Relocation Hook Transition

The normal relocation commit attempt ran all hooks. The disposition hook failed
because its pre-commit HEAD had the checker but only the old scripts/ baseline:

```text
Regenerate Orrery package catalog............................................Passed
Validate NEXUS config and model-ID drift.....................................Passed
Require COMMENT ON for new migration objects.............(no files to check)Skipped
Require dispositions for swallowing exception handlers.......................Failed
- hook id: check-exception-dispositions
- exit code: 1

config/exception_disposition_baseline.json:1: Prior baseline missing at HEAD; checker already exists
```

The proposed config/ JSON was proved byte-identical to 3d347913, and the exact
origin/main bootstrap comparison passed. Only that hook was skipped for the
relocation commit with `SKIP=check-exception-dispositions`; other applicable hooks
passed. After 4650ad21 existed, the unmodified hook was run normally and passed.
No checker bypass flag or alternate ratchet semantics was introduced. Both
transition attempts and the post-commit hook result are recorded below.

## Current Proof Commands and Verbatim Tails

The commands below are the exact child argv recorded by the bounded runner.
The runner's PYTHONPATH and TMPDIR settings above apply to each. Exit status is
shown separately; `(no output)` is an annotation for empty output.

### Amended Bootstrap Comparison

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

### Relocation Commit with One-Time Hook Transition

```sh
env SKIP=check-exception-dispositions git commit -m 'Move exception disposition baseline into config (806-S4, GPT-6)' -m 'Apply coordinator Amendment 1 without changing legacy debt or product handlers. Remove the baseline classification and update the checker, temporary repository helper, hook, CI, and documentation references.' -m 'The relocation is byte-identical and the origin/main bootstrap comparison passed. Skip only the disposition hook for this commit because HEAD still holds its old baseline path; rerun the hook against the committed relocation.' -m 'Co-Authored-By: Codex <noreply@openai.com>
Claude-Session: https://claude.ai/code/session_019Z1vFjhTSTxxopapYaEv1y
Agent: Codex (GPT-6)'
```

Exit: 0.

```text
Regenerate Orrery package catalog............................................Passed
Validate NEXUS config and model-ID drift.....................................Passed
Require COMMENT ON for new migration objects.............(no files to check)Skipped
Require dispositions for swallowing exception handlers......................Skipped
[claude/806-exception-disposition-lint 4650ad21] Move exception disposition baseline into config (806-S4, GPT-6)
 7 files changed, 7 insertions(+), 4 deletions(-)
 rename {scripts => config}/exception_disposition_baseline.json (100%)
```

### Normal Hook After Relocation

```sh
/Users/pythagor/nexus/.venv/bin/python -m pre_commit run check-exception-dispositions --all-files
```

Exit: 0.

```text
Require dispositions for swallowing exception handlers.......................Passed
```

### Focused Checker: 68 Tests

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_scripts/test_check_exception_dispositions.py
```

Exit: 0.

```text
....................................................................     [100%]
=============================== warnings summary ===============================
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
68 passed, 5 warnings in 22.54s
```

### Offline API Partition

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api
```

Exit: 0.

```text
.....sss....sssssssssssss............................................... [ 16%]
......ssss....................................................ssssssssss [ 24%]
.......ssssssssssssss...s............................................... [ 32%]
.sssssssssssssssss.......sssssssssss...ssssssssss...............ssssssss [ 40%]
ssssssssssss...............sss.....sss............ss..ssssssssssssssssss [ 49%]
s..........................................ssssssssss................... [ 57%]
..............sss...ssssssssssssssssssssssss........ss..............ssss [ 65%]
ss...................................................................... [ 73%]
........................sssssss....................ssss...ss............ [ 81%]
.............................sssssssssssssssss.........s................ [ 90%]
............s........................................................... [ 98%]
................                                                         [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
641 passed, 239 skipped, 7 warnings in 23.64s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Offline Orrery Partition

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_orrery
```

Exit: 0.

```text
ssssssssssssssssssssssssss....................s........................s [ 50%]
ssssssssssssssssssssssssss..s.........sss...........ssss................ [ 55%]
........sss.....ssssssssssssssssssssss......sssss..s...................s [ 59%]
sssssssssssssssssssssssssssssssssssss................................... [ 63%]
........................................................................ [ 67%]
.ssssssss............................................................... [ 72%]
......................s.................sssss...s....................... [ 76%]
...........................sssssssssssssssssssssssss.................... [ 80%]
....................................sssssssssssss.s......s.............. [ 84%]
.....s....ssssssssss.....ss...............ssss.......................... [ 89%]
............ss....sssssssssss........................................... [ 93%]
....................................sssssssssss........................s [ 97%]
sssssssssss.............sssss..........s.                                [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1188 passed, 509 skipped, 7 warnings in 11.31s
```

### Offline Core Subdirectories

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/config tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util
```

Exit: 0.

```text
........................................................................ [ 15%]
........................................................................ [ 22%]
.................s...........sssssss.................................... [ 30%]
.........ss............ssssssss...............s......................... [ 38%]
........................................................................ [ 45%]
...........sssssssss....................sssss...s......sssss......sss... [ 53%]
...............s........................................................ [ 61%]
..s..ss................................................................. [ 68%]
....ssss.........................sss.................................... [ 76%]
........................................................................ [ 83%]
...........sssss................................................ssssssss [ 91%]
ssss.................................................................... [ 99%]
.......                                                                  [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
873 passed, 70 skipped, 7 warnings in 75.14s (0:01:15)
```

### Offline Core Top-Level Partition

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/config --ignore=tests/test_config --ignore=tests/test_ir_eval_v2 --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --ignore=tests/test_scripts --ignore=tests/test_util
```

Exit: 0.

```text
.............................................ssssssssssssssss.ss........ [ 77%]
...................sssss................................................ [ 80%]
..........ssssssssssssssssssssssssssssssssss............................ [ 83%]
........................................................................ [ 86%]
........ss.............................................................. [ 89%]
.............................s..s.............................ssss...... [ 92%]
...........sssss...................................sssss................ [ 95%]
...sss..............ssss..............................................ss [ 98%]
sssssssssssssssssssssssss                                                [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_memnon_cross_encoder_artifact.py::test_qwen3_loads_its_local_folder_and_scores
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/tokenization_utils_base.py:2718: UserWarning: `max_length` is ignored when `padding`=`True` and there is no truncation strategy. To pad to max length, use `padding='max_length'`.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1927 passed, 404 skipped, 8 warnings in 375.73s (0:06:15)
```

### Standalone Reachability

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

Exit: 0.

```text
......................................................                   [100%]
=============================== warnings summary ===============================
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 9.87s
```

### Black

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check scripts/check_exception_dispositions.py tests/test_scripts/test_check_exception_dispositions.py
```

Exit: 0.

```text
All done! ✨ 🍰 ✨
2 files would be left unchanged.
```

### Flake8

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 scripts/check_exception_dispositions.py tests/test_scripts/test_check_exception_dispositions.py
```

Exit: 0.

```text
(no output)
```

### Mypy with Explicit Package Bases

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases scripts/check_exception_dispositions.py tests/test_scripts/test_check_exception_dispositions.py
```

Exit: 0.

```text
Success: no issues found in 2 source files
```

### PostgreSQL Safety: First Attempt

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_new_story_setup.py tests/test_owner_target_guard.py tests/test_dbname_audit.py
```

Exit: 1.

```text
            attempt_path = tmp_path / f"attempt_{attempt}"
            attempt_path.mkdir()
            before = _owner_sessions_started()
            assert sorted(before) == sorted(OWNER_TARGETS), before
            result = _owner_session(
                attempt_path,
                ["-p", "tests.dbname_audit"],
                {"NEXUS_RUN_POSTGRES": "1"},
                inherited=poisoned,
            )
            # A backend adds its session to the statistics by the time it exits;
            # give any backend the child started time to finish exiting.
            time.sleep(0.5)
            after = _owner_sessions_started()
            _assert_owner_session_failed(result)
            delta = {name: after[name] - before[name] for name in OWNER_TARGETS}
            brackets.append(delta)
            uncleared -= {name for name, moved in delta.items() if moved == 0}
            if not uncleared:
                return
>       pytest.fail(
            f"session counters moved in every bracket for {sorted(uncleared)}: "
            f"{brackets}"
        )
E       Failed: session counters moved in every bracket for ['NEXUS_template']: [{'NEXUS_template': 1, 'save_01': 0, 'save_02': 0, 'save_03': 0, 'save_04': 0, 'save_05': 0}, {'NEXUS_template': 2, 'save_01': 0, 'save_02': 0, 'save_03': 0, 'save_04': 0, 'save_05': 0}, {'NEXUS_template': 2, 'save_01': 0, 'save_02': 0, 'save_03': 0, 'save_04': 0, 'save_05': 0}, {'NEXUS_template': 1, 'save_01': 1, 'save_02': 0, 'save_03': 0, 'save_04': 0, 'save_05': 0}, {'NEXUS_template': 2, 'save_01': 0, 'save_02': 0, 'save_03': 0, 'save_04': 0, 'save_05': 0}]

tests/test_dbname_audit.py:730: Failed
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 10 targets: nexus_m10_fresh_test_60007, nexus_m10_template_test_60007, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_dbname_audit.py::test_owner_session_starts_no_owner_backend
1 failed, 111 passed in 24.41s
```

### PostgreSQL Safety: Unchanged Repeat

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_new_story_setup.py tests/test_owner_target_guard.py tests/test_dbname_audit.py
```

Exit: 0.

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
........................................................................ [ 64%]
........................................                                 [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 10 targets: nexus_m10_fresh_test_62020, nexus_m10_template_test_62020, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
112 passed in 20.92s
```

### Final-Main Checker, Reachability, and Cooldown Proof

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_scripts/test_check_exception_dispositions.py tests/test_reachability.py tests/test_qa_shift.py
```

Exit: 0.

```text
........................................................................ [ 40%]
........................................................................ [ 80%]
............................ssssss                                       [100%]
=============================== warnings summary ===============================
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
172 passed, 6 skipped, 5 warnings in 36.49s
```

### Merge-Preserving Rebase onto Newest Main

```sh
git rebase --rebase-merges=no-rebase-cousins origin/main
```

Exit: 0.

```text
Rebasing (1/7)
Rebasing (2/7)
Rebasing (3/7)
Rebasing (4/7)
Rebasing (5/7)
Rebasing (6/7)
Rebasing (7/7)
Successfully rebased and updated refs/heads/claude/806-exception-disposition-lint.
```

### Pre-existing Diagnostics

None. The checker and its test file are new on origin/main: `git ls-tree
origin/main -- scripts/check_exception_dispositions.py
tests/test_scripts/test_check_exception_dispositions.py` returned no paths.
There are no pre-existing changed Python files to extract with git show and run
through the same commands. Flake8 is silent; sanctioned mypy with
--explicit-package-bases emits no diagnostic. No diagnostic was suppressed.

### Shared Session-Counter Failure for Coordinator Triage

The first PostgreSQL attempt failed only
`tests/test_dbname_audit.py::test_owner_session_starts_no_owner_backend` at
`tests/test_dbname_audit.py:730`: NEXUS_template's global session counter changed
in every observation bracket. The audit for this run reports owner targets:
none. The identical full proof, with no edit or skipped test, then passed all
112 cases. Concurrent activity from another suite is a plausible explanation,
not a proved attribution; both raw tails are retained for the coordinator.
No owner database was opened by the audited Python connections, and no
PostgreSQL authentication permission-dialog error occurred.

### Final Cross-Version CLI Matrix

The following full command records come from final_proof_matrix.py in the
scratch directory. Each subprocess has a 45-second timeout; no interpreter is
skipped. Inventory redirections show the exact destination written by the
runner; the full shared JSON appears below. Every comparison exited 0 with no
output. Python versions: 3.11.12, 3.12.9, 3.13.5.

```sh
/Users/pythagor/nexus/.venv/bin/python --version
```

Exit: 0.

```text
Python 3.11.12
```

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --inventory > /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_1.json
```

Exit: 0.

```text
(no output)
```

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/.pyenv/versions/3.11.12/bin/python3.11 --version
```

Exit: 0.

```text
Python 3.11.12
```

```sh
/Users/pythagor/.pyenv/versions/3.11.12/bin/python3.11 -S scripts/check_exception_dispositions.py --inventory > /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_3.11.json
```

Exit: 0.

```text
(no output)
```

```sh
/Users/pythagor/.pyenv/versions/3.11.12/bin/python3.11 -S scripts/check_exception_dispositions.py
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/.pyenv/versions/3.11.12/bin/python3.11 -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/.local/share/uv/python/cpython-3.12.9-macos-aarch64-none/bin/python3.12 --version
```

Exit: 0.

```text
Python 3.12.9
```

```sh
/Users/pythagor/.local/share/uv/python/cpython-3.12.9-macos-aarch64-none/bin/python3.12 -S scripts/check_exception_dispositions.py --inventory > /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_3.12.json
```

Exit: 0.

```text
(no output)
```

```sh
/Users/pythagor/.local/share/uv/python/cpython-3.12.9-macos-aarch64-none/bin/python3.12 -S scripts/check_exception_dispositions.py
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/.local/share/uv/python/cpython-3.12.9-macos-aarch64-none/bin/python3.12 -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/opt/homebrew/bin/python3.13 --version
```

Exit: 0.

```text
Python 3.13.5
```

```sh
/opt/homebrew/bin/python3.13 -S scripts/check_exception_dispositions.py --inventory > /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_3.13.json
```

Exit: 0.

```text
(no output)
```

```sh
/opt/homebrew/bin/python3.13 -S scripts/check_exception_dispositions.py
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/opt/homebrew/bin/python3.13 -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --inventory > /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_2.json
```

Exit: 0.

```text
(no output)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_1.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_2.json
```

Exit: 0.

```text
(no output)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_1.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_3.11.json
```

Exit: 0.

```text
(no output)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_1.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_3.12.json
```

Exit: 0.

```text
(no output)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_1.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_3.13.json
```

Exit: 0.

```text
(no output)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_3.11.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_3.12.json
```

Exit: 0.

```text
(no output)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_3.11.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/final_inventory_3.13.json
```

Exit: 0.

```text
(no output)
```

## Landing Notes and Open Questions

No migration number or fleet application; no database schema, product code, or
nexus.toml changes relative to origin/main. No gateway restart (including the
owner's port 8002), no UI rebuild, and no service restart. The hook is active on
the next checkout that reruns `poetry run pre-commit install`; the coordinator
runs the whole-tree PostgreSQL gate at the final commit. Push and PR creation
are the remaining handoff actions after this documentation commit. Do not merge.

Coordinator triage question: should the shared session-counter failure above
be tracked separately? No owner ruling is requested or reopened; Q10/Q11 and
the unrelated #811 pending questions are unchanged.

## Accepted Stop-Report: 2026-10-01

Historical record from retained commit 3d347913, accepted by Amendment 1.
The paths under scripts/ and the question in this section describe the original
stop condition and are superseded by the amendment. The stop-report prose and
original proof tails are preserved below; its original complete inventory is
retained verbatim in commit 3d347913. Current complete inventory follows this
historical section and supersedes source line positions.

<details>
<summary>Accepted stop-report and original proof tails</summary>

### STOP-REPORT: 806-S4 Exception Dispositions

Date: 2026-10-01 (America/Chicago).
Implementation and every source citation below: `dc903caf2a168241018456e2b7b27cad5e9c0cab`.
Base: `5b977eabcba5f7aedf1a64a6ee20c021ab290911`; `git fetch origin`
confirmed this was still `origin/main` before the implementation commit.
This evidence document is a later documentation-only commit; it changes no scanned
source or baseline identity. No PR was opened, no push or merge was performed.

#### Why the Frozen Order Cannot Pass Its Gate

The order requires `scripts/exception_disposition_baseline.json` to be an
`operator` classification, now at `config/reachability.toml:312`. The existing
`RULES_811_S1` assigns `scripts/*.json` to `pending-ruling:811-Q3` at
`tests/test_reachability.py:965-979`. Its first-match predicate is at
`:985-992`, and `test_repository_classification_applies_811_decisions`
compares the exact held sets at `:1013-1019`. The required new baseline is thus
present in the expected held set and absent from the actual held set. The exact
failing test is:

`tests/test_reachability.py::test_repository_classification_applies_811_decisions`

Both the full core offline partition and the independent reachability gate fail
on that one assertion. This is **introduced by the required registration**, not
pre-existing diagnostic debt and not an exempt #885 slot-5 failure.

The common rules say: "Any other failure in a file you did not change: report
the exact test id and the failure tail, do not fix it, do not skip it; the
coordinator triages." They also say: "if honest attempts cannot satisfy a rule
or a gate, STOP and write a stop-report". No edit was made to that test, no
classification requirement was weakened, and no alternative baseline location
was invented. Q10 and Q11 are unchanged and are not reopened.

Read-only predicate isolation (the actual literal test rules and actual
`origin/main`/worktree TOML, not mocked configuration):

```text
scripts/exception_disposition_baseline.json: first matching frozen test rule = pending-ruling:811-Q3
origin/main: held/pattern equality = True; extras in pattern = []
origin/main: baseline classification = []
worktree: held/pattern equality = False; extras in pattern = ['scripts/exception_disposition_baseline.json']
worktree: baseline classification = ['operator']
```

#### Files and Scope

- `scripts/check_exception_dispositions.py`: stdlib-only git/AST/token inventory,
  conservative exits, version-independent typed JSON hashes, contracts, exact
  baseline coverage, and prior-ref shrinkage.
- `scripts/exception_disposition_baseline.json`: 584 sorted legacy identities,
  with the frozen seed reason. No legacy fallback is approved by this inventory.
- `tests/test_scripts/test_check_exception_dispositions.py`: 68 real git/source/
  subprocess proofs; no mocks, provider, or PostgreSQL requirement.
- `.pre-commit-config.yaml`: adds only the always-run disposition hook.
- `.github/workflows/exception-disposition-check.yml`: stdlib-only 3.11/3.12/3.13
  matrix comparing against the actual event base ref, with complete git history.
- `config/reachability.toml`: adds the operator and two sorted operator path rows;
  leaves all existing classifications and the reachability baseline unchanged.
- `CLAUDE.md`: only the exact paragraph in the frozen order is inserted.
- `docs/qa/806-exception-dispositions/verification.md`: this stop-report, proof
  outputs, citations, and complete JSON inventory.

`git diff 5b977eab..dc903caf2a168241018456e2b7b27cad5e9c0cab -- nexus/ nexus.toml .flake8
scripts/check_migration_comments.py config/schema_docs_baseline.json
.github/workflows/migration-comment-check.yml tests/test_reachability.py` is
empty. This slice converts **no product handler** and adds no product marker.
The checker's own new reporting handler carries a `fail` marker; it exits 1.
No migration, schema, UI, runtime tunable, paid call, or gateway is part of it.

#### Verified Citations and Census

- `.flake8:1-11` has no exception policy; existing migration hook remains at
  `.pre-commit-config.yaml:36-48`. The new hook is `:49-54`. Neither new script
  nor baseline exists at `origin/main` (read-only `git ls-tree`).
- `nexus/agents/lore/utils/turn_cycle.py:376-377` logs requested-chunk lookup
  failure and continues; `:406-408` logs warm-slice failure and retains chunks;
  `:517-520` re-raises `RuntimeError` but only logs general `Exception`.
  They are inventory examples, not conversion targets.
- `scripts/check_migration_comments.py:94-97` keeps watermark 129;
  `:1641-1669` is the stdlib CLI/reporting model.
  `tests/test_schema_documentation_pg.py:136-157` validates baseline and
  missing/stale coverage. These files are unchanged.
- `pyproject.toml:9` supports 3.11 through 3.13. A fresh read-only AST census of
  the 862 original git-visible handlers reproduces all frozen syntax counts:
  `nexus`: 507 total, 153 direct Exception, 5 bare, 9 direct BaseException;
  `scripts`: 355 total, 204 direct Exception, 4 bare, 1 direct BaseException.
  Comparing actual Python 3.11.12 and 3.13.5 dumps again finds 730 differing
  dumps for the same 862 handlers. The frozen canonical encoding is documented
  at `scripts/check_exception_dispositions.py:1-13` and implemented at `:169-222`.
- `.github/workflows/migration-comment-check.yml:8-31` is the unchanged trigger,
  runner, permission, and stdlib model. The new matrix is
  `.github/workflows/exception-disposition-check.yml:3-33`.
  `CLAUDE.md:20-27` keeps the existing hook list; `:29` adds only the frozen
  paragraph.
- `config/reachability.toml:90-95` keeps the migration operator and registers the
  new operator. `:172-173` scopes paths to scripts/ and ir_eval/; `:270-271`
  classifies the checkers; `:312` classifies the JSON baseline.
  `docs/reachability.md:89-114` requires sorted classified paths, including
  non-Python files. The conflict is in the untouched test, not those docs.
- Discovery is `scripts/check_exception_dispositions.py:374-430`;
  token-owned contracts are `:343-371`; ordered exit analysis is `:249-321`;
  validated baseline and read-only git ratchet are `:467-535`.

Full current summary (original handlers plus the one new marked checker handler):

```json
{
  "nexus": {
    "always_raises": 226,
    "baseline_entries": 281,
    "marked": 0,
    "total": 507
  },
  "scripts": {
    "always_raises": 52,
    "baseline_entries": 303,
    "marked": 1,
    "total": 356
  }
}
```

Total: 863. Always-raising AST exemptions: 278. Non-exempt: 585. Marked: 1
(`fail`, in the checker only). Missing markers/baseline entries: 584.
The change from the original syntax counts is exactly that one new tuple-catch
handler in the checker. Syntax counts do not mean swallowing counts or approved
dispositions. No legacy handler is approved merely because it is baselined.

#### Proof Environment and Commands

All commands ran from the assigned worktree. `$PY` is
`/Users/pythagor/nexus/.venv/bin/python`, and `PYTHONPATH=$PWD` resolved
`nexus.__file__` to this worktree's `nexus/__init__.py` before any proof.
All scratch output is under
`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4`.
The order's `temp/806-S4/` output paths were replaced with this directory to
obey the user's stricter scratch-only instruction.

Subsequent gates used `run_gate.py` in that directory: it runs one foreground
command at a time with a 590-second timeout, writes its full output and status,
and waits for completion. It sets `TMPDIR` to this scratch directory and adds
its `bin/` to PATH; the only shim there is a symlink to the installed uv Python
3.12.9 interpreter. No interpreter was skipped or installed, and no main
checkout file was modified. The initial PostgreSQL proof and initial focused
proofs were directly executed and waited to completion.

##### PostgreSQL Safety Proof (Exit 0)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit tests/test_new_story_setup.py tests/test_owner_target_guard.py tests/test_dbname_audit.py
```

Complete tail, including the guard and audit:

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
........................................................................ [ 64%]
........................................                                 [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 10 targets: nexus_m10_fresh_test_66994, nexus_m10_template_test_66994, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
112 passed in 23.52s
```

The audit names the existing fixtures' disposable prefixes (including the
existing migration-test prefixes permitted by the common rules) and no owner
connection. No test fixture was renamed.

##### Focused Proof Attempts

Command for all attempts: `$PY -m pytest -q tests/test_scripts/test_check_exception_dispositions.py`.
The first attempt caught a test unpacking error on a nested handler; the test
was corrected to verify every handler, without changing the exemption to hide
it. The next pass preceded the three additional suspension cases; the final
68-case run includes them. Full tails are preserved below.

Attempt `checker-tests`, exit 1:

```text
.......................F.........................................        [100%]
=================================== FAILURES ===================================
_ test_always_raising_handlers_are_exempt[try:\n    raise\nexcept ValueError:\n    raise\nelse:\n    raise] _

repo = PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/pytest-of-pythagor/pytest-0/test_always_raising_handlers_a5')
body = 'try:\n    raise\nexcept ValueError:\n    raise\nelse:\n    raise'

    @pytest.mark.parametrize(
        "body",
        [
            "raise",
            "raise caught",
            "raise RuntimeError('translated') from caught",
            "log(caught)\nraise",
            "if flag:\n    raise\nelse:\n    raise caught",
            "try:\n    raise\nexcept ValueError:\n    raise\nelse:\n    raise",
            "try:\n    return\nfinally:\n    raise",
            "match value:\n    case 1:\n        raise\n    case _:\n        raise",
            "raise\nyield caught",  # unreachable suspension does not prevent exemption
        ],
    )
    def test_always_raising_handlers_are_exempt(repo: Path, body: str) -> None:
        _write(repo, "def function():\n" + textwrap.indent(_catch(body), "    "))
>       (handler,) = _handlers(repo)
E       ValueError: too many values to unpack (expected 1)

tests/test_scripts/test_check_exception_dispositions.py:257: ValueError
=============================== warnings summary ===============================
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_scripts/test_check_exception_dispositions.py::test_always_raising_handlers_are_exempt[try:\n    raise\nexcept ValueError:\n    raise\nelse:\n    raise]
1 failed, 64 passed, 5 warnings in 23.30s
```

Attempt `checker-tests-final`, exit 0:

```text
.................................................................        [100%]
=============================== warnings summary ===============================
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
65 passed, 5 warnings in 22.67s
```

Attempt `checker-final`, exit 0:

```text
....................................................................     [100%]
=============================== warnings summary ===============================
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
68 passed, 5 warnings in 24.79s
```

##### Core Offline Partition (Exit 1)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
........................................................................ [  2%]
.........................................................s.............. [  4%]
........................sssssss...ssss.................................. [  6%]
........................................................................ [  8%]
........................................................................ [ 11%]
........................................................................ [ 13%]
.........................................s.............................. [ 15%]
...................................ssssssssss...................s....... [ 17%]
........................................................................ [ 19%]
.......s........................s......................ss............... [ 22%]
.s..ss..................s............................................... [ 24%]
....ssssssss........sssssssssssssss.....s....s..........s..sssssssssssss [ 26%]
sssssssssssssssssss..........ssssssssssssss............ssssssssssss..... [ 28%]
..............s...........sssssss....................................... [ 30%]
......ss............ssssssss...............s............................ [ 33%]
........................................................................ [ 35%]
........sssssssss....................sssss...s......sssss......sss...... [ 37%]
............s..........................................................s [ 39%]
..ss.................................................................... [ 42%]
.ssss....................s....ss..........sss........................... [ 44%]
........................................s........ss.............ssssssss [ 46%]
ssssssss............................................................ss.. [ 48%]
.............sss....................................................ssss [ 50%]
ss.................ss................................................... [ 53%]
........................................................................ [ 55%]
........ss..ss................................ssssssssssss.............. [ 57%]
............................................ssssssssssssssssssssssssssss [ 59%]
ssssssssss.............................................................. [ 61%]
..................sssssssssssssssss..................................... [ 64%]
....................s.ssssss............................................ [ 66%]
................................................................s.....ss [ 68%]
ssssssssssssssss........s...ss.....................s.................... [ 70%]
......sssssssssssssssssssssss.........................................s. [ 72%]
........................................................................ [ 75%]
.........................F....ssssssssssssssss.ss....................... [ 77%]
....sssss............................................................... [ 79%]
..................sssss................................................s [ 81%]
sssssssssss..........................................................sss [ 84%]
sssssssssssssssssssssssssssssss......................................... [ 86%]
........................................................................ [ 88%]
...............................................................ss....... [ 90%]
........................................................................ [ 92%]
............s..s.............................ssss.................sssss. [ 95%]
..................................sssss...................sss........... [ 97%]
...ssss.....................................................ssssssssssss [ 99%]
sssssssssssssss                                                          [100%]
=================================== FAILURES ===================================
_____________ test_repository_classification_applies_811_decisions _____________

    def test_repository_classification_applies_811_decisions() -> None:
        """Paths decided on #811 keep the class those decisions gave them."""
        classification = _repository_config()["classification"]
        by_class: dict[str, set[str]] = {}
        for entry in classification["paths"]:
            by_class.setdefault(entry["class"], set()).add(entry["path"])
        assert by_class["pending-ruling:811-Q4"] == {
            "scripts/api_anthropic.py",
            "scripts/api_openai.py",
        }
        assert by_class["openrouter-shim"] == {"scripts/api_openrouter.py"}
        assert by_class["pending-ruling:811-Q1"] == {
            "scripts/apply_slot2_semantic_tags.py",
            "scripts/backfill_routine_anchors.py",
            "scripts/seed_slot2_routine_anchors.py",
        }
        assert "ir_eval/ir_eval.py" in by_class["pending-ruling:811-Q5"]
        assert "ir_eval/ir_eval.db" in by_class["pending-ruling:811-Q3"]
        pattern_classes: dict[str, set[str]] = {}
        for path in {entry["path"] for entry in classification["paths"]}:
            rule_class = _first_811_rule_class(path)
            if rule_class in PATTERN_HELD_CLASSES:
                pattern_classes.setdefault(rule_class, set()).add(path)
        for held in PATTERN_HELD_CLASSES:
>           assert by_class[held] == pattern_classes[held]
E           AssertionError: assert {'ir_eval/ir_...nt.json', ...} == {'ir_eval/ir_...nt.json', ...}
E             
E             Extra items in the right set:
E             'scripts/exception_disposition_baseline.json'
E             Use -v to get more diff

tests/test_reachability.py:1019: AssertionError
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_memnon_cross_encoder_artifact.py::test_qwen3_loads_its_local_folder_and_scores
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/tokenization_utils_base.py:2718: UserWarning: `max_length` is ignored when `padding`=`True` and there is no truncation strategy. To pad to max length, use `padding='max_length'`.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_reachability.py::test_repository_classification_applies_811_decisions
1 failed, 2799 passed, 457 skipped, 8 warnings in 480.91s (0:08:00)
```

##### Required Reachability Gate (Exit 1)

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

```text
...................................................F..                   [100%]
=================================== FAILURES ===================================
_____________ test_repository_classification_applies_811_decisions _____________

    def test_repository_classification_applies_811_decisions() -> None:
        """Paths decided on #811 keep the class those decisions gave them."""
        classification = _repository_config()["classification"]
        by_class: dict[str, set[str]] = {}
        for entry in classification["paths"]:
            by_class.setdefault(entry["class"], set()).add(entry["path"])
        assert by_class["pending-ruling:811-Q4"] == {
            "scripts/api_anthropic.py",
            "scripts/api_openai.py",
        }
        assert by_class["openrouter-shim"] == {"scripts/api_openrouter.py"}
        assert by_class["pending-ruling:811-Q1"] == {
            "scripts/apply_slot2_semantic_tags.py",
            "scripts/backfill_routine_anchors.py",
            "scripts/seed_slot2_routine_anchors.py",
        }
        assert "ir_eval/ir_eval.py" in by_class["pending-ruling:811-Q5"]
        assert "ir_eval/ir_eval.db" in by_class["pending-ruling:811-Q3"]
        pattern_classes: dict[str, set[str]] = {}
        for path in {entry["path"] for entry in classification["paths"]}:
            rule_class = _first_811_rule_class(path)
            if rule_class in PATTERN_HELD_CLASSES:
                pattern_classes.setdefault(rule_class, set()).add(path)
        for held in PATTERN_HELD_CLASSES:
>           assert by_class[held] == pattern_classes[held]
E           AssertionError: assert {'ir_eval/ir_...nt.json', ...} == {'ir_eval/ir_...nt.json', ...}
E             
E             Extra items in the right set:
E             'scripts/exception_disposition_baseline.json'
E             Use -v to get more diff

tests/test_reachability.py:1019: AssertionError
=============================== warnings summary ===============================
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_reachability.py::test_repository_classification_applies_811_decisions
1 failed, 53 passed, 5 warnings in 11.16s
```

##### Black (Exit 0)

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check scripts/check_exception_dispositions.py tests/test_scripts/test_check_exception_dispositions.py
```

```text
All done! ✨ 🍰 ✨
2 files would be left unchanged.
```

##### Flake8 (Exit 0)

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 scripts/check_exception_dispositions.py tests/test_scripts/test_check_exception_dispositions.py
```

```text
(no output)
```

##### Mypy (Exit 0)

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases scripts/check_exception_dispositions.py tests/test_scripts/test_check_exception_dispositions.py
```

```text
Success: no issues found in 2 source files
```

##### Pre-existing Diagnostics

None. Both Python files are new at origin/main, so there are no pre-existing
changed Python files to extract or compare. The sanctioned mypy invocation
uses `--explicit-package-bases`; neither mypy nor flake8 emits any diagnostics.
The reachability assertion above is a test-policy conflict, not static debt.

##### Cross-Version CLI and Deterministic Inventory (All Exits 0)

The exact invoked commands, output, and statuses (inventory output is reproduced
in full below rather than duplicated for every interpreter):

```sh
/Users/pythagor/nexus/.venv/bin/python --version
```

Exit: 0.

```text
Python 3.11.12
```

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --inventory
```

Exit: 0.

```text
(saved to inventory_1.json)
```

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/.pyenv/versions/3.11.12/bin/python3.11 --version
```

Exit: 0.

```text
Python 3.11.12
```

```sh
/Users/pythagor/.pyenv/versions/3.11.12/bin/python3.11 -S scripts/check_exception_dispositions.py --inventory
```

Exit: 0.

```text
(saved to inventory_3.11.json)
```

```sh
/Users/pythagor/.pyenv/versions/3.11.12/bin/python3.11 -S scripts/check_exception_dispositions.py
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/.pyenv/versions/3.11.12/bin/python3.11 -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/.local/share/uv/python/cpython-3.12.9-macos-aarch64-none/bin/python3.12 --version
```

Exit: 0.

```text
Python 3.12.9
```

```sh
/Users/pythagor/.local/share/uv/python/cpython-3.12.9-macos-aarch64-none/bin/python3.12 -S scripts/check_exception_dispositions.py --inventory
```

Exit: 0.

```text
(saved to inventory_3.12.json)
```

```sh
/Users/pythagor/.local/share/uv/python/cpython-3.12.9-macos-aarch64-none/bin/python3.12 -S scripts/check_exception_dispositions.py
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/.local/share/uv/python/cpython-3.12.9-macos-aarch64-none/bin/python3.12 -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/opt/homebrew/bin/python3.13 --version
```

Exit: 0.

```text
Python 3.13.5
```

```sh
/opt/homebrew/bin/python3.13 -S scripts/check_exception_dispositions.py --inventory
```

Exit: 0.

```text
(saved to inventory_3.13.json)
```

```sh
/opt/homebrew/bin/python3.13 -S scripts/check_exception_dispositions.py
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/opt/homebrew/bin/python3.13 -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

Exit: 0.

```text
OK: exception disposition coverage and shrink-only baseline verified.
```

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --inventory
```

Exit: 0.

```text
(saved to inventory_2.json)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_1.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_2.json
```

Exit: 0.

```text
(no output)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_1.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_3.11.json
```

Exit: 0.

```text
(no output)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_1.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_3.12.json
```

Exit: 0.

```text
(no output)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_1.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_3.13.json
```

Exit: 0.

```text
(no output)
```

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_3.11.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_3.12.json
```

Exit: 0. No output.

```sh
cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_3.11.json /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/806-S4/inventory_3.13.json
```

Exit: 0. No output.

The post-implementation-commit HEAD and origin/main CLI checks both returned
exit 0 with the same `OK: exception disposition coverage and shrink-only
baseline verified.` line. Existing hooks ran on the implementation commit:

```text
Regenerate Orrery package catalog............................................Passed
Validate NEXUS config and model-ID drift.....................................Passed
Require COMMENT ON for new migration objects.............(no files to check)Skipped
Require dispositions for swallowing exception handlers.......................Passed
[claude/806-exception-disposition-lint dc903caf] Add exception disposition inventory and ratchet (806-S4, GPT-6)
 7 files changed, 1742 insertions(+)
 create mode 100644 .github/workflows/exception-disposition-check.yml
 create mode 100644 scripts/check_exception_dispositions.py
 create mode 100644 scripts/exception_disposition_baseline.json
 create mode 100644 tests/test_scripts/test_check_exception_dispositions.py
```

#### Unfinished Work and Coordinator Question

Not run after the stop condition: the second offline partition
(`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=0
$PY -m pytest -q tests/test_api tests/test_orrery`). This report makes no claim
that it passed. No whole-tree PostgreSQL gate, rebase-for-push, push, PR, review,
or merge occurred. No owner gateway restart, UI rebuild, or fleet application
is needed for these files. The coordinator's post-landing pre-commit install
and whole-tree PostgreSQL gate remain deferred.

Coordinator question: may the frozen order be amended to authorize a specific
operator-rule exception for `scripts/exception_disposition_baseline.json` in
`tests/test_reachability.py`, followed by completing both offline partitions and
all required gates at the final revision? This is a scope/gate amendment only;
Q10, Q11, and all handler-conversion decisions remain unchanged.

</details>

## Complete Current Inventory JSON

All repeated and supported-interpreter CLI inventories at the final source
revision are byte-identical to this document. The baseline exactly equals its
non-exempt, unmarked set.

```json
{
  "counts": {
    "by_caught_type": {
      "(Exception, SchedulerStopped)": 1,
      "(Exception, asyncio.CancelledError)": 1,
      "(IDFRebuildError, psycopg2.Error)": 1,
      "(ImportError, RuntimeError)": 3,
      "(ImportError, ValueError)": 3,
      "(IndexError, ValueError)": 1,
      "(KeyError, IndexError)": 1,
      "(KeyError, OSError, TypeError, tomlkit.exceptions.ParseError)": 1,
      "(KeyError, TypeError)": 2,
      "(KeyError, TypeError, ValueError)": 4,
      "(KeyError, TypeError, ValueError, OverflowError)": 1,
      "(OSError, TypeError)": 1,
      "(OSError, UnicodeDecodeError)": 1,
      "(OSError, UnicodeError)": 1,
      "(OSError, ValueError, RuntimeHomeError)": 1,
      "(OSError, ValueError, SyntaxError, tokenize.TokenError, subprocess.CalledProcessError)": 1,
      "(OSError, ValueError, json.JSONDecodeError)": 3,
      "(OSError, json.JSONDecodeError)": 3,
      "(OSError, subprocess.SubprocessError)": 3,
      "(OSError, tomllib.TOMLDecodeError)": 1,
      "(ProcessLookupError, PermissionError)": 1,
      "(RuntimeError, ValueError)": 2,
      "(RuntimeError, WebSocketDisconnect, OSError)": 1,
      "(RuntimeError_, FileNotFoundError)": 2,
      "(RuntimeError_, FileNotFoundError, MissingSecretError, SecretStoreAccessError, ValueError)": 1,
      "(RuntimeError_, FileNotFoundError, ValueError, requests.RequestException)": 1,
      "(RuntimeError_, FileNotFoundError, requests.RequestException)": 1,
      "(RuntimeHomeError, HomePlanError, FileNotFoundError)": 1,
      "(RuntimeHomeError, ValueError)": 1,
      "(SummaryInputTooLong, SummaryOutputTruncated)": 3,
      "(TypeError, ValueError)": 17,
      "(TypeError, ValueError, OverflowError)": 1,
      "(TypeError, ValueError, ValidationError)": 2,
      "(ValidationError, json.JSONDecodeError, ValueError)": 6,
      "(ValueError, AttributeError)": 1,
      "(ValueError, RuntimeError)": 1,
      "(ValueError, RuntimeError, MissingSecretError)": 1,
      "(ValueError, TypeError)": 2,
      "(ValueError, ZoneInfoNotFoundError)": 1,
      "(ValueError, requests.exceptions.RequestException)": 2,
      "(_HeaderError, OSError, struct.error)": 1,
      "(psycopg2.Error, OSError)": 1,
      "(psycopg2.OperationalError, psycopg2.DatabaseError)": 1,
      "(psycopg2.OperationalError, psycopg2.InterfaceError)": 1,
      "(requests.RequestException, ValueError)": 1,
      "(requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError)": 1,
      "(requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.exceptions.Timeout)": 2,
      "(requests.exceptions.RequestException, ValueError)": 1,
      "(subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError)": 1,
      "<bare>": 9,
      "AmbiguousCommit": 7,
      "ApiAnswerFailure": 3,
      "ArtifactLockError": 1,
      "BackstagePayloadError": 1,
      "BaseException": 10,
      "CallDeferred": 1,
      "CognitionTraceInputError": 1,
      "DeprecatedTagAuditError": 1,
      "EOFError": 10,
      "EpistemicsValidationError": 1,
      "Exception": 357,
      "ExperienceLeaseLostError": 3,
      "ExperienceSourceStaleError": 1,
      "FileExistsError": 1,
      "FileNotFoundError": 14,
      "GenerationRetryConflict": 2,
      "HTTPException": 7,
      "IDFStateError": 3,
      "ImportError": 34,
      "InspectFailure": 1,
      "InteractionAuthorizationDenied": 2,
      "InvalidOperation": 1,
      "KeyError": 7,
      "KeyboardInterrupt": 6,
      "LocalInferenceError": 2,
      "MalformedExperienceEventError": 1,
      "MaturationLeaseLostError": 1,
      "MissingSecretError": 4,
      "ModelRetry": 5,
      "ModuleNotFoundError": 3,
      "NarrationCompletionRejectedError": 1,
      "NarrationLeaseLostError": 1,
      "NoGenerationSessionError": 1,
      "NoPromptWindowsError": 1,
      "OSError": 18,
      "OverrideValidationError": 1,
      "PackageNotFoundError": 1,
      "PermissionError": 2,
      "PlayerIdentityNotEstablishedError": 3,
      "ProcessLookupError": 8,
      "RetrogradeExpansionValidationError": 1,
      "RetrogradeSeedCandidateValidationError": 1,
      "RuntimeError": 16,
      "RuntimeError_": 1,
      "RuntimeHomeError": 4,
      "SQLAlchemyError": 1,
      "SchedulerStopped": 1,
      "SeatRequirementError": 2,
      "SecretStoreAccessError": 5,
      "SessionWaitFailure": 1,
      "ShiftError": 2,
      "StarletteHTTPException": 1,
      "SyntaxError": 1,
      "TypeError": 2,
      "UnicodeDecodeError": 3,
      "UsageReadError": 1,
      "UsageWriteError": 1,
      "ValidationError": 1,
      "ValueError": 91,
      "WebSocketDisconnect": 1,
      "WireContractViolation": 7,
      "WizardConversationMoveError": 1,
      "WizardStateConflict": 7,
      "_API_URL_ERRORS": 1,
      "_CREDENTIAL_ERRORS": 1,
      "_CreationCommandAlreadyRecorded": 1,
      "_LexError": 1,
      "_TRANSPORT_ERRORS": 1,
      "asyncio.CancelledError": 3,
      "json.JSONDecodeError": 18,
      "keyring.errors.KeyringError": 1,
      "keyring.errors.PasswordDeleteError": 1,
      "local_inference.LocalInferenceError": 6,
      "openai.OpenAIError": 1,
      "psycopg2.Error": 22,
      "psycopg2.OperationalError": 2,
      "psycopg2.errors.ReadOnlySqlTransaction": 3,
      "requests.RequestException": 6,
      "requests.exceptions.ConnectionError": 1,
      "requests.exceptions.HTTPError": 1,
      "requests.exceptions.RequestException": 4,
      "requests.exceptions.Timeout": 1,
      "subprocess.CalledProcessError": 3,
      "subprocess.TimeoutExpired": 4
    },
    "by_disposition": {
      "fail": 1,
      "unmarked": 862
    },
    "by_exemption": {
      "always-raises": 278,
      "not-exempt": 585
    },
    "by_root": {
      "nexus": 507,
      "scripts": 356
    },
    "missing_marker": 584,
    "total": 863
  },
  "handlers": [
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/logon/apex_schema.py|validate_story_turn_response|714f915292db7bbea5d2379df05c748d1377644fefb1c5c76f5dc8bbbaaa4d3a|1",
      "line": 897,
      "marker": null,
      "path": "nexus/agents/logon/apex_schema.py",
      "scope": "validate_story_turn_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/logon/apex_schema.py|validate_story_turn_response|714f915292db7bbea5d2379df05c748d1377644fefb1c5c76f5dc8bbbaaa4d3a|2",
      "line": 903,
      "marker": null,
      "path": "nexus/agents/logon/apex_schema.py",
      "scope": "validate_story_turn_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/logon/apex_schema.py|validate_story_turn_response|714f915292db7bbea5d2379df05c748d1377644fefb1c5c76f5dc8bbbaaa4d3a|3",
      "line": 909,
      "marker": null,
      "path": "nexus/agents/logon/apex_schema.py",
      "scope": "validate_story_turn_response"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/logon/gaia_registry_schema.py|load_gaia_registry_wire_spec|9c68b4cd08f7e8d5a5182f6ae5cd984a54176781c1ade298f370e2e2ed4ae11c|1",
      "line": 119,
      "marker": null,
      "path": "nexus/agents/logon/gaia_registry_schema.py",
      "scope": "load_gaia_registry_wire_spec"
    },
    {
      "ast_exempt": true,
      "caught_type": "TypeError",
      "identity": "nexus/agents/logon/gaia_registry_schema.py|_normalize_names|7f933b8c66a894092dc1551752ec7a443dc44ca9e42216459f78058754d6b789|1",
      "line": 256,
      "marker": null,
      "path": "nexus/agents/logon/gaia_registry_schema.py",
      "scope": "_normalize_names"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/logon/orrery_tag_validation.py|_replacement_pair_tag_issues|97d091b2ac7d6f68cfd410b78825b20ec1888122de812bc7fb64751268c544e0|1",
      "line": 423,
      "marker": null,
      "path": "nexus/agents/logon/orrery_tag_validation.py",
      "scope": "_replacement_pair_tag_issues"
    },
    {
      "ast_exempt": false,
      "caught_type": "WireContractViolation",
      "identity": "nexus/agents/logon/place_reference_validation.py|validate_place_references|65b3e53312d1ca760076ae7ff1c08d99e51b34af6a8d67cb3c96ce2583ac3d7e|1",
      "line": 57,
      "marker": null,
      "path": "nexus/agents/logon/place_reference_validation.py",
      "scope": "validate_place_references"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/agents/logon/place_reference_validation.py|validate_place_references|8caefc55a2f1a8a0e7c9bf24930710f78dd3c368a2d85d8655dface8b5d47ad1|1",
      "line": 61,
      "marker": null,
      "path": "nexus/agents/logon/place_reference_validation.py",
      "scope": "validate_place_references"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "nexus/agents/lore/logon_utility.py|_coerce_mapping|5a7f261c3d14193f407fdf2ddd0163b1c28355ff4255a33ce45653bccb198c7f|1",
      "line": 335,
      "marker": null,
      "path": "nexus/agents/lore/logon_utility.py",
      "scope": "_coerce_mapping"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/logon_utility.py|LogonUtility._initialize_provider|20eb973c6db67e529683e0cbdbaf8f35a05fe8dbdcf997e617930ca9e574f19a|1",
      "line": 736,
      "marker": null,
      "path": "nexus/agents/lore/logon_utility.py",
      "scope": "LogonUtility._initialize_provider"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/logon_utility.py|LogonUtility.generate_narrative|dc520bc60716fac8b04d4ebb5d8e71172b4189d7a950a8b8462266c287535997|1",
      "line": 967,
      "marker": null,
      "path": "nexus/agents/lore/logon_utility.py",
      "scope": "LogonUtility.generate_narrative"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/logon_utility.py|LogonUtility.generate_narrative_async|dc520bc60716fac8b04d4ebb5d8e71172b4189d7a950a8b8462266c287535997|1",
      "line": 1058,
      "marker": null,
      "path": "nexus/agents/lore/logon_utility.py",
      "scope": "LogonUtility.generate_narrative_async"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/lore.py|LORE._load_settings|e36238cce69a61c1c9c4fb74b8ee0bae5edec761b92444a303bd6d463d83f5d0|1",
      "line": 183,
      "marker": null,
      "path": "nexus/agents/lore/lore.py",
      "scope": "LORE._load_settings"
    },
    {
      "ast_exempt": true,
      "caught_type": "ImportError",
      "identity": "nexus/agents/lore/lore.py|LORE._initialize_memnon|7b454143dca5bf6be1659891cc7f4b206d8af5b245a41c62d1cdfcfc1abf65ba|1",
      "line": 228,
      "marker": null,
      "path": "nexus/agents/lore/lore.py",
      "scope": "LORE._initialize_memnon"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/lore.py|LORE._initialize_memnon|0c6356c442ac3df44e5e1730969f50720ee91b82e537774aa2a0f0e1f5caf810|1",
      "line": 264,
      "marker": null,
      "path": "nexus/agents/lore/lore.py",
      "scope": "LORE._initialize_memnon"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/lore.py|LORE._initialize_logon|b941d23585de81d6c63e3a24e168146b30eae17bbdb5bf00b8a061a07c715071|1",
      "line": 285,
      "marker": null,
      "path": "nexus/agents/lore/lore.py",
      "scope": "LORE._initialize_logon"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/lore.py|LORE.process_turn|c991fca15ff427789859583027c4e77beba56afea761d50f072439c6432f1916|1",
      "line": 422,
      "marker": null,
      "path": "nexus/agents/lore/lore.py",
      "scope": "LORE.process_turn"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/lore.py|LORE.retrieve_context|163d65617243b6c2ace02b34aa728899507f51351ceb738cc8043a4c6b98b4bf|1",
      "line": 478,
      "marker": null,
      "path": "nexus/agents/lore/lore.py",
      "scope": "LORE.retrieve_context"
    },
    {
      "ast_exempt": false,
      "caught_type": "KeyboardInterrupt",
      "identity": "nexus/agents/lore/lore.py|main|ce56ea5a44bce26e1be700e257725ea1ce1126cf3cecb940ceb7f4fa2f0b8b69|1",
      "line": 874,
      "marker": null,
      "path": "nexus/agents/lore/lore.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/lore.py|main|2f1ebaa1c2ae650eda686f064aa37f15848598cab77714f4bf2142d17364c54d|1",
      "line": 877,
      "marker": null,
      "path": "nexus/agents/lore/lore.py",
      "scope": "main"
    },
    {
      "ast_exempt": true,
      "caught_type": "KeyError",
      "identity": "nexus/agents/lore/seat_blocks.py|influence_role|c9f1180d4208d49d09dc8e28d835cc7db3a6bb3cb4170a8c2442da49817399a9|1",
      "line": 150,
      "marker": null,
      "path": "nexus/agents/lore/seat_blocks.py",
      "scope": "influence_role"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|<module>|88f6a4659be7600d6374adacc701bb602a3fc8ef92f4179be70841d0f096eaf1|1",
      "line": 59,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|_sorted_chunk_ids.sort_key|de284752fc1546f6e7510ad3ec4a6e88cdfb68ceaced01f609a88825f419dd60|1",
      "line": 106,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "_sorted_chunk_ids.sort_key"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|_warm_chunk_recency_id|8dca1ca5004730bc25e16f3c74797730000ffa88e7fa4386c72d53f9d32590dd|1",
      "line": 180,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "_warm_chunk_recency_id"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|TurnCycleManager.perform_warm_analysis|e6c700ed11431a969287e3fa02814a16c50cf1db355a5be28264ffee0c201e0f|1",
      "line": 376,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "TurnCycleManager.perform_warm_analysis"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|TurnCycleManager.perform_warm_analysis|185fdabafe53437bfe54dba43648337ea2f47c025803b1667b4f2e5b453faab3|1",
      "line": 406,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "TurnCycleManager.perform_warm_analysis"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeError",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|TurnCycleManager.query_entity_states|32a89207e753649daef5c3cd2d258e0974e6b81f6e1d1d359c4152f211d3b964|1",
      "line": 517,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "TurnCycleManager.query_entity_states"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|TurnCycleManager.query_entity_states|4c937fb57587b30274ff707673fb95911855db0bb2e90d52c737aeb9777fd820|1",
      "line": 519,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "TurnCycleManager.query_entity_states"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|TurnCycleManager.query_entity_states|672fd73b0fdcc8546cc05c7eedb8e67e4c56b9bae71ed0a9f36d8e0ab166eaf0|1",
      "line": 567,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "TurnCycleManager.query_entity_states"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|TurnCycleManager.query_entity_states|ec523696ad5d794d78376baac0deea2e95b523e314546094327e020c4448ec5e|1",
      "line": 584,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "TurnCycleManager.query_entity_states"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|TurnCycleManager.query_entity_states|43366b8522edfa38561c6f81a0b69c452a053da3adc89fff6d4b5af02ed5031d|1",
      "line": 601,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "TurnCycleManager.query_entity_states"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|TurnCycleManager.call_apex_ai|edb48a5c735c8f9a786a8df5e331f91db90381b82114029e53ef545cf7f6e023|1",
      "line": 1537,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "TurnCycleManager.call_apex_ai"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|TurnCycleManager.call_apex_ai|9e2718e1e2892f096bdd6c407a34ee766940085d5bcb236e1e8b39cff9538e30|1",
      "line": 1604,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "TurnCycleManager.call_apex_ai"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/lore/utils/turn_cycle.py|TurnCycleManager.integrate_response|06d208bd174e83c7608d032ca92996554ca5c809768df138c9592c912d0cb4ce|1",
      "line": 1699,
      "marker": null,
      "path": "nexus/agents/lore/utils/turn_cycle.py",
      "scope": "TurnCycleManager.integrate_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "<bare>",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.get_schema_summary|8b45aeb9105f690ebae0c255b5d1af528c44b2861367e190c373c64befedb0bf|1",
      "line": 395,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.get_schema_summary"
    },
    {
      "ast_exempt": false,
      "caught_type": "<bare>",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.get_schema_summary|8b45aeb9105f690ebae0c255b5d1af528c44b2861367e190c373c64befedb0bf|2",
      "line": 423,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.get_schema_summary"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.get_schema_summary|10fa351c44071888da1d1374be458e0349839ba22e7c5a873ef1b2b05e648d57|1",
      "line": 431,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.get_schema_summary"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.get_schema_summary|630165eefb5b8609f424737ab5ff1a040f27c3bb166fea918f652c2e30cfe81f|1",
      "line": 441,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.get_schema_summary"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.execute_readonly_sql|714f915292db7bbea5d2379df05c748d1377644fefb1c5c76f5dc8bbbaaa4d3a|1",
      "line": 507,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.execute_readonly_sql"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.execute_readonly_sql|5080d229deb6968ad8bcac747bf21d1df81e669f3cd2e351c8e0216b50b2caa7|1",
      "line": 528,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.execute_readonly_sql"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON._query_structured_data|b9b663afd0fe37de6c5ea177f722292cc389b6875d609b7b9cc74e4c1975504d|1",
      "line": 967,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON._query_structured_data"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.process_all_narrative_files|2c17ca45a5e22090f1b795e05e0eba30b4432df46b9f5dc6485356f9f2197826|1",
      "line": 1015,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.process_all_narrative_files"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.step|2a54afdd83bae0151b09ce4ac6a54b3b05f9ee467821a136bae01411d166e31a|1",
      "line": 1070,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.step"
    },
    {
      "ast_exempt": true,
      "caught_type": "IDFStateError",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.step|9ce3313079813788d1542340594409eaedba1708b36f9f29529b9457978aa98a|1",
      "line": 1104,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.step"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.step|80d4d643140967a29357e005fde5465b99fe1210292ea7fab7bd547e550906d1|1",
      "line": 1106,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.step"
    },
    {
      "ast_exempt": false,
      "caught_type": "<bare>",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON._parse_command|f3525a98d98648666635947e9eeab036f3a854ddedd3ea44124cae6108cc32f4|1",
      "line": 1164,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON._parse_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "<bare>",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON._parse_command|8b45aeb9105f690ebae0c255b5d1af528c44b2861367e190c373c64befedb0bf|1",
      "line": 1186,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON._parse_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "<bare>",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON._parse_command|8b45aeb9105f690ebae0c255b5d1af528c44b2861367e190c373c64befedb0bf|2",
      "line": 1196,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON._parse_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON._get_status|1b227d9b8306610123bd0ff7e97151e7ca60a0def0ff23092bf0126b4fc4131c|1",
      "line": 1240,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON._get_status"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON._get_status|c8a4e0702898b02b43d6d4fa4cbc1989379e6bf1da5dfce95b98bbdf6257dd1e|1",
      "line": 1297,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON._get_status"
    },
    {
      "ast_exempt": true,
      "caught_type": "IDFStateError",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON._test_hybrid_search|9ce3313079813788d1542340594409eaedba1708b36f9f29529b9457978aa98a|1",
      "line": 1354,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON._test_hybrid_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON._test_hybrid_search|dd911e6f6b91ebe85ea0db40592b1106efa20993046cce6ad119eef157971d1d|1",
      "line": 1356,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON._test_hybrid_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.get_chunk_by_id|c2a649c23f9230df72172ceefe6faf477d2bff4debfda362b6c693c9193bd95e|1",
      "line": 1419,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.get_chunk_by_id"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.get_recent_chunks|9464a58fcdf18b8954c819785ffa7075f8ebe8752676f92af45d5fd98e31e829|1",
      "line": 1489,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.get_recent_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/memnon/memnon.py|MEMNON.query_memory|9ec0e1a08d1d273e569bf018c730475a6f3dbdd8669d449b100e7defec5fd4b1|1",
      "line": 1587,
      "marker": null,
      "path": "nexus/agents/memnon/memnon.py",
      "scope": "MEMNON.query_memory"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/test_idf_dictionary.py|main|28dce23550f4bd9487b13dd232045b57966c4c90254c7b1491b490ed7ac5a72a|1",
      "line": 101,
      "marker": null,
      "path": "nexus/agents/memnon/test_idf_dictionary.py",
      "scope": "main"
    },
    {
      "ast_exempt": true,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/agents/memnon/utils/artifact_manifest.py|_git_revision|7b465ac05a99aa152ea1c55afb5be596fbeb166c6ee64649bf20ccdcdf2ce2a0|1",
      "line": 272,
      "marker": null,
      "path": "nexus/agents/memnon/utils/artifact_manifest.py",
      "scope": "_git_revision"
    },
    {
      "ast_exempt": true,
      "caught_type": "UnicodeDecodeError",
      "identity": "nexus/agents/memnon/utils/artifact_manifest.py|read_manifest|5485676818f8d6d943722b0580bcd53ec2efcb3c749a2bc484f80eba5bd972de|1",
      "line": 502,
      "marker": null,
      "path": "nexus/agents/memnon/utils/artifact_manifest.py",
      "scope": "read_manifest"
    },
    {
      "ast_exempt": true,
      "caught_type": "json.JSONDecodeError",
      "identity": "nexus/agents/memnon/utils/artifact_manifest.py|read_manifest|70e9bd660942bc81d9d68e2b5c8f2dd4f188c98f84aafe11bcb03625e5c1ca7b|1",
      "line": 507,
      "marker": null,
      "path": "nexus/agents/memnon/utils/artifact_manifest.py",
      "scope": "read_manifest"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/agents/memnon/utils/artifact_manifest.py|run_models_command|b7c266d7dd09a84a091f3bdf099fa6f473423a89258a92b57d1fa58c16940aef|1",
      "line": 685,
      "marker": null,
      "path": "nexus/agents/memnon/utils/artifact_manifest.py",
      "scope": "run_models_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "RuntimeHomeError",
      "identity": "nexus/agents/memnon/utils/artifact_manifest.py|run_models_command|6b5675d88e0e201ecd6c27de0c1b1251f46c51768dc6326f68b008a2f985bbbe|1",
      "line": 692,
      "marker": null,
      "path": "nexus/agents/memnon/utils/artifact_manifest.py",
      "scope": "run_models_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "ArtifactLockError",
      "identity": "nexus/agents/memnon/utils/artifact_manifest.py|run_models_command|a0a5085de6f24794317b9c7908cc0ed6ab80628dcbe094e8a15ffa76aa525be4|1",
      "line": 706,
      "marker": null,
      "path": "nexus/agents/memnon/utils/artifact_manifest.py",
      "scope": "run_models_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/content_processor.py|ContentProcessor.process_all_narrative_files|0ee9149abcfeff1eee5a302b06cb72f6271e315d460bc3b45f6d3a10df9cd513|1",
      "line": 97,
      "marker": null,
      "path": "nexus/agents/memnon/utils/content_processor.py",
      "scope": "ContentProcessor.process_all_narrative_files"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/content_processor.py|ContentProcessor.process_chunked_file|69c62473ac5af6839a53d76e3d779148875b37e6331b46b3402d29be2d3b84a3|1",
      "line": 119,
      "marker": null,
      "path": "nexus/agents/memnon/utils/content_processor.py",
      "scope": "ContentProcessor.process_chunked_file"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/content_processor.py|ContentProcessor.process_chunked_file|4b235d34507881a202238d6d737e423180c087c4e808d28712f8dac30cb3b034|1",
      "line": 222,
      "marker": null,
      "path": "nexus/agents/memnon/utils/content_processor.py",
      "scope": "ContentProcessor.process_chunked_file"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/content_processor.py|ContentProcessor.store_narrative_chunk|b9e00fc0d200b7291fefe676afb4573a2188da0da804ad4de336076c79458e36|1",
      "line": 370,
      "marker": null,
      "path": "nexus/agents/memnon/utils/content_processor.py",
      "scope": "ContentProcessor.store_narrative_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/content_processor.py|ContentProcessor._generate_chunk_embeddings|31f7919238de69c3543c28a5f4d3cd41891ee39576b41f1c7a3995ef3f15bd7c|1",
      "line": 436,
      "marker": null,
      "path": "nexus/agents/memnon/utils/content_processor.py",
      "scope": "ContentProcessor._generate_chunk_embeddings"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/continuous_temporal_search.py|get_total_chunks|cac98b49124d15c1793540e56fd10971631fedda32390c97c1180ab983299109|1",
      "line": 277,
      "marker": null,
      "path": "nexus/agents/memnon/utils/continuous_temporal_search.py",
      "scope": "get_total_chunks"
    },
    {
      "ast_exempt": true,
      "caught_type": "IDFStateError",
      "identity": "nexus/agents/memnon/utils/continuous_temporal_search.py|execute_time_aware_search|9ce3313079813788d1542340594409eaedba1708b36f9f29529b9457978aa98a|1",
      "line": 430,
      "marker": null,
      "path": "nexus/agents/memnon/utils/continuous_temporal_search.py",
      "scope": "execute_time_aware_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/continuous_temporal_search.py|execute_time_aware_search|db0aeaec7ace4d03508b101f2302162b9a633259f674a430e528ef7ec3ff08d4|1",
      "line": 432,
      "marker": null,
      "path": "nexus/agents/memnon/utils/continuous_temporal_search.py",
      "scope": "execute_time_aware_search"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/cross_encoder.py|CrossEncoderReranker.__init__|0101484faa4a27a29100ff4e358f8d0b7bb4f89e30f51d611991b3cc1586a7f9|1",
      "line": 185,
      "marker": null,
      "path": "nexus/agents/memnon/utils/cross_encoder.py",
      "scope": "CrossEncoderReranker.__init__"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/cross_encoder.py|Qwen3LMReranker.__init__|3e3f1d1124622d40d33973605df0bfb2fc943cf7e7409634bce456e980dfde78|1",
      "line": 570,
      "marker": null,
      "path": "nexus/agents/memnon/utils/cross_encoder.py",
      "scope": "Qwen3LMReranker.__init__"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/db_access.py|check_vector_extension|f40e90a1a69e734e892bdb1e18105828c1ad1daab08ee68d12708d68ea1c690d|1",
      "line": 200,
      "marker": null,
      "path": "nexus/agents/memnon/utils/db_access.py",
      "scope": "check_vector_extension"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/db_access.py|execute_vector_search|05a3372b4b5db966d10fbe935d89b7e7711dde9cc73b61afd8bf894c0ddee7c9|1",
      "line": 355,
      "marker": null,
      "path": "nexus/agents/memnon/utils/db_access.py",
      "scope": "execute_vector_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/db_access.py|setup_database_indexes|6b53a987b88e0246e5a5eacc97fb056ca97ee8a11515646ad1739d8aff80b97e|1",
      "line": 467,
      "marker": null,
      "path": "nexus/agents/memnon/utils/db_access.py",
      "scope": "setup_database_indexes"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/db_access.py|setup_database_indexes|189003dbed1940b3d1b2a58593ac3723f8b855f86e2b765e74cf551e5438aabd|1",
      "line": 493,
      "marker": null,
      "path": "nexus/agents/memnon/utils/db_access.py",
      "scope": "setup_database_indexes"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/db_access.py|setup_database_indexes|2bb427024de559e1ae86584eb5f578ae011aea3698e4dba7be021cd51681568e|1",
      "line": 540,
      "marker": null,
      "path": "nexus/agents/memnon/utils/db_access.py",
      "scope": "setup_database_indexes"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/db_access.py|setup_database_indexes|8eeb5b357c45b106dbc295a5b7f93670b0ca7b9a76dd750a09c920efd37721ee|1",
      "line": 559,
      "marker": null,
      "path": "nexus/agents/memnon/utils/db_access.py",
      "scope": "setup_database_indexes"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/db_access.py|setup_database_indexes|e332f0cb4568ce6249f95968cd12acac6068e9b6f1f82925832df010bdb6d61b|1",
      "line": 566,
      "marker": null,
      "path": "nexus/agents/memnon/utils/db_access.py",
      "scope": "setup_database_indexes"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/db_access.py|setup_database_indexes|5335445c524ecdc3e2087e1cbfb22bfbd2ade6020fd38bcf7cfa082bf0863247|1",
      "line": 576,
      "marker": null,
      "path": "nexus/agents/memnon/utils/db_access.py",
      "scope": "setup_database_indexes"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/db_schema.py|DatabaseManager._initialize_database_connection|78cbe891ac6763f83f302e70b03856e37f4edfe8d67ead2326e9de44040f8f4b|1",
      "line": 159,
      "marker": null,
      "path": "nexus/agents/memnon/utils/db_schema.py",
      "scope": "DatabaseManager._initialize_database_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/db_schema.py|DatabaseManager._setup_hybrid_search|315aba118220cefb097d0462c142438cae259783338e5cccfe6dee34203d9c77|1",
      "line": 183,
      "marker": null,
      "path": "nexus/agents/memnon/utils/db_schema.py",
      "scope": "DatabaseManager._setup_hybrid_search"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/embedding_manager.py|load_local_model|b91001d73fee4ad256a7c31132bad07d0123b3a54787e7ea6723a0e389b743c1|1",
      "line": 153,
      "marker": null,
      "path": "nexus/agents/memnon/utils/embedding_manager.py",
      "scope": "load_local_model"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/embedding_manager.py|EmbeddingManager.generate_embedding|b90dcd920444a59a3f94c6a4a1bab68826dc1e40da0b4f46cce201df70703228|1",
      "line": 273,
      "marker": null,
      "path": "nexus/agents/memnon/utils/embedding_manager.py",
      "scope": "EmbeddingManager.generate_embedding"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/embedding_manager.py|EmbeddingManager.generate_embeddings_batch|b90dcd920444a59a3f94c6a4a1bab68826dc1e40da0b4f46cce201df70703228|1",
      "line": 314,
      "marker": null,
      "path": "nexus/agents/memnon/utils/embedding_manager.py",
      "scope": "EmbeddingManager.generate_embeddings_batch"
    },
    {
      "ast_exempt": true,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/agents/memnon/utils/idf_dictionary.py|IDFDictionary._cursor|39550f47afc4924669d8ff3f842e36474ddb35a68786669245516cae870e5ce9|1",
      "line": 105,
      "marker": null,
      "path": "nexus/agents/memnon/utils/idf_dictionary.py",
      "scope": "IDFDictionary._cursor"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/search.py|SearchManager.query_text_search|1b5853f9e31d16c327eefee0061f6c0e6b73943dc2419c6e6e0947b19f1b9720|1",
      "line": 556,
      "marker": null,
      "path": "nexus/agents/memnon/utils/search.py",
      "scope": "SearchManager.query_text_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/search.py|SearchManager.query_structured_data|b9b663afd0fe37de6c5ea177f722292cc389b6875d609b7b9cc74e4c1975504d|1",
      "line": 742,
      "marker": null,
      "path": "nexus/agents/memnon/utils/search.py",
      "scope": "SearchManager.query_structured_data"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/temporal_search.py|get_total_chunks|690aa3def6c2beb6ad3cf8c7147cc967317890918d014e05895719ac898eee2c|1",
      "line": 156,
      "marker": null,
      "path": "nexus/agents/memnon/utils/temporal_search.py",
      "scope": "get_total_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/memnon/utils/temporal_search.py|execute_time_aware_search|c5fcc13f925ca51c0d01cd6228ffe8eb4f640f8ad12da06d1cbb05deb63c7677|1",
      "line": 284,
      "marker": null,
      "path": "nexus/agents/memnon/utils/temporal_search.py",
      "scope": "execute_time_aware_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "(KeyError, TypeError)",
      "identity": "nexus/agents/orrery/bleed.py|_row_value|abade343d60e140f9a94e2eb119ff28d9b76dca53736efa7c34a130f25d98849|1",
      "line": 494,
      "marker": null,
      "path": "nexus/agents/orrery/bleed.py",
      "scope": "_row_value"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/declaration_validation.py|collect_new_entity_declaration_vocabulary_issues|b8ba10e1def56fc6f3407db120269ed72fcc7f3c51fc11aa2f93fa95532a4426|1",
      "line": 70,
      "marker": null,
      "path": "nexus/agents/orrery/declaration_validation.py",
      "scope": "collect_new_entity_declaration_vocabulary_issues"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/declaration_validation.py|collect_new_entity_declaration_vocabulary_issues|1ca02889db16e4eab57ee0c7b91b81074a6589d2ef30f5b8b34217f42dacd6d7|1",
      "line": 95,
      "marker": null,
      "path": "nexus/agents/orrery/declaration_validation.py",
      "scope": "collect_new_entity_declaration_vocabulary_issues"
    },
    {
      "ast_exempt": false,
      "caught_type": "(KeyError, TypeError)",
      "identity": "nexus/agents/orrery/epistemics.py|_row_value|c101ebdd4371f4cf9946cda3926e2f933d08f512959cfca3120ce892f72ae7bf|1",
      "line": 1488,
      "marker": null,
      "path": "nexus/agents/orrery/epistemics.py",
      "scope": "_row_value"
    },
    {
      "ast_exempt": true,
      "caught_type": "KeyError",
      "identity": "nexus/agents/orrery/events.py|_render_brief|a093210856172989d7fe91511471beb4f62ea1f2e67c2535ede27211812df2ac|1",
      "line": 1604,
      "marker": null,
      "path": "nexus/agents/orrery/events.py",
      "scope": "_render_brief"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/orrery/events.py|_entity_label|169a7ffa4ea3c8520e576fcea8c2814e19799519cb0f8ea95840a1a278e7d5c1|1",
      "line": 1619,
      "marker": null,
      "path": "nexus/agents/orrery/events.py",
      "scope": "_entity_label"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/events.py|_json_snapshot|a262eab41d8b78783953646a52b5df691549377c43868327468ec71627e62fce|1",
      "line": 2815,
      "marker": null,
      "path": "nexus/agents/orrery/events.py",
      "scope": "_json_snapshot"
    },
    {
      "ast_exempt": true,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/orrery/events.py|_coerce_need_fulfillment|b4dd1c4b17c7985d3c1427e2271cec2d1071250d3a3ee1f417906ed5dd463aa4|1",
      "line": 3028,
      "marker": null,
      "path": "nexus/agents/orrery/events.py",
      "scope": "_coerce_need_fulfillment"
    },
    {
      "ast_exempt": true,
      "caught_type": "InvalidOperation",
      "identity": "nexus/agents/orrery/events.py|_validate_need_debt_score_domain|e87acb29d993ef91f4785f923f2ae1dbadc11e39fc74016f1fb11e42b2a30e86|1",
      "line": 3053,
      "marker": null,
      "path": "nexus/agents/orrery/events.py",
      "scope": "_validate_need_debt_score_domain"
    },
    {
      "ast_exempt": true,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/orrery/events.py|_coerce_int|8c4568ea18edd1056b1ef5464450b1527a0f270040eabe181a8a5d15b33f7716|1",
      "line": 8094,
      "marker": null,
      "path": "nexus/agents/orrery/events.py",
      "scope": "_coerce_int"
    },
    {
      "ast_exempt": false,
      "caught_type": "(KeyError, IndexError)",
      "identity": "nexus/agents/orrery/events.py|_row_get_optional|98fc721ac869d505f82f3cd6ded506351689cfddc5d5736f9a34056ded04937f|1",
      "line": 8101,
      "marker": null,
      "path": "nexus/agents/orrery/events.py",
      "scope": "_row_get_optional"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "nexus/agents/orrery/events.py|_decode_json_value|ba791834291820841a859da062a3eb3d5ae10d36390516fb1094626428c55469|1",
      "line": 8115,
      "marker": null,
      "path": "nexus/agents/orrery/events.py",
      "scope": "_decode_json_value"
    },
    {
      "ast_exempt": false,
      "caught_type": "(IndexError, ValueError)",
      "identity": "nexus/agents/orrery/events.py|_affected_count|048efa8ff4620e29b76d9084f6bf306b31a8d0eab38babba96aab90965d7502f|1",
      "line": 8123,
      "marker": null,
      "path": "nexus/agents/orrery/events.py",
      "scope": "_affected_count"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/evidence.py|_has_severity_tag_at_or_above|8f365da9b5cf71c155fd007fbe9e4019ce20098f994e1576a4f9053172f30a55|1",
      "line": 299,
      "marker": null,
      "path": "nexus/agents/orrery/evidence.py",
      "scope": "_has_severity_tag_at_or_above"
    },
    {
      "ast_exempt": true,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/orrery/experiences.py|_public_audience_entity_ids|0853108b1b0b2cd9c36b594aefeb2c0e916a6ffbf8edc834ac419666d2b33577|1",
      "line": 466,
      "marker": null,
      "path": "nexus/agents/orrery/experiences.py",
      "scope": "_public_audience_entity_ids"
    },
    {
      "ast_exempt": true,
      "caught_type": "(TypeError, ValueError, OverflowError)",
      "identity": "nexus/agents/orrery/experiences.py|_public_audience_entity_ids|ca1ac436ed6285a742af7a5406d2c4be57bf675ee4479bad88d453c24b306d43|1",
      "line": 496,
      "marker": null,
      "path": "nexus/agents/orrery/experiences.py",
      "scope": "_public_audience_entity_ids"
    },
    {
      "ast_exempt": true,
      "caught_type": "(KeyError, TypeError, ValueError, OverflowError)",
      "identity": "nexus/agents/orrery/experiences.py|_event_receipts|64769055c828b22ff28e44e146d111dee68f84fb6e63280bcd22b40f3894fb03|1",
      "line": 550,
      "marker": null,
      "path": "nexus/agents/orrery/experiences.py",
      "scope": "_event_receipts"
    },
    {
      "ast_exempt": false,
      "caught_type": "MalformedExperienceEventError",
      "identity": "nexus/agents/orrery/experiences.py|seed_character_experiences_sync|71ecd0a7000a7638fe073ad9811e3888d47800105a22f6900e05e76fa614501a|1",
      "line": 770,
      "marker": null,
      "path": "nexus/agents/orrery/experiences.py",
      "scope": "seed_character_experiences_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "ExperienceLeaseLostError",
      "identity": "nexus/agents/orrery/experiences.py|drain_experience_render_jobs_sync|dc9817face912420db0a149b946ffec2068313a882af421ee52404865334fdd0|1",
      "line": 2118,
      "marker": null,
      "path": "nexus/agents/orrery/experiences.py",
      "scope": "drain_experience_render_jobs_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "ExperienceSourceStaleError",
      "identity": "nexus/agents/orrery/experiences.py|drain_experience_render_jobs_sync|436a00c3e2a2bff36f679fc192896596bcf8b8496a6622b7e0282e776228a9a1|1",
      "line": 2121,
      "marker": null,
      "path": "nexus/agents/orrery/experiences.py",
      "scope": "drain_experience_render_jobs_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "ExperienceLeaseLostError",
      "identity": "nexus/agents/orrery/experiences.py|drain_experience_render_jobs_sync|2e5bfe7909b3a2db03ad64d76f05f24e318f047460197ec4e3c0438ac3be5dd9|1",
      "line": 2127,
      "marker": null,
      "path": "nexus/agents/orrery/experiences.py",
      "scope": "drain_experience_render_jobs_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/orrery/experiences.py|drain_experience_render_jobs_sync|9b945d602e986fe2c938f4eb55bf67b41bc0eef4027c246e203841326ebfef4b|1",
      "line": 2133,
      "marker": null,
      "path": "nexus/agents/orrery/experiences.py",
      "scope": "drain_experience_render_jobs_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "ExperienceLeaseLostError",
      "identity": "nexus/agents/orrery/experiences.py|drain_experience_render_jobs_sync|541dfbb91b88519b08ed22e3a2584696761dcec5d0dbf904d276a576f7862600|1",
      "line": 2141,
      "marker": null,
      "path": "nexus/agents/orrery/experiences.py",
      "scope": "drain_experience_render_jobs_sync"
    },
    {
      "ast_exempt": true,
      "caught_type": "(KeyError, TypeError, ValueError)",
      "identity": "nexus/agents/orrery/propagation.py|_payload_int|c4f80c33f1b89c487dffca3b2e4a27d968b89fb0d90ac674e0626d12ed9ffabe|1",
      "line": 938,
      "marker": null,
      "path": "nexus/agents/orrery/propagation.py",
      "scope": "_payload_int"
    },
    {
      "ast_exempt": true,
      "caught_type": "BaseException",
      "identity": "nexus/agents/orrery/relationship_provenance.py|relationship_producer|8247fd23841289b1bebde2cde428a50596ee458cf137f8d5fda992f493f9224e|1",
      "line": 70,
      "marker": null,
      "path": "nexus/agents/orrery/relationship_provenance.py",
      "scope": "relationship_producer"
    },
    {
      "ast_exempt": true,
      "caught_type": "BaseException",
      "identity": "nexus/agents/orrery/relationship_provenance.py|relationship_producer_async|8247fd23841289b1bebde2cde428a50596ee458cf137f8d5fda992f493f9224e|1",
      "line": 102,
      "marker": null,
      "path": "nexus/agents/orrery/relationship_provenance.py",
      "scope": "relationship_producer_async"
    },
    {
      "ast_exempt": true,
      "caught_type": "(KeyError, TypeError, ValueError)",
      "identity": "nexus/agents/orrery/replay.py|_propagated_claim_identity|215bc96e0c2a47adbc8b88a7e7e0ca42ae9c8c132c64e8783c104851f675e037|1",
      "line": 361,
      "marker": null,
      "path": "nexus/agents/orrery/replay.py",
      "scope": "_propagated_claim_identity"
    },
    {
      "ast_exempt": true,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/orrery/replay.py|_propagated_claim_identity|95f939a1e91050da6b011cb129067f8d393d309d0eb3ef93c5f9962fc15c8dba|1",
      "line": 370,
      "marker": null,
      "path": "nexus/agents/orrery/replay.py",
      "scope": "_propagated_claim_identity"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/replay.py|canonicalize|a262eab41d8b78783953646a52b5df691549377c43868327468ec71627e62fce|1",
      "line": 444,
      "marker": null,
      "path": "nexus/agents/orrery/replay.py",
      "scope": "canonicalize"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/replay.py|canonicalize|a2d5170969589f421cea31928c042192b43bce7cf6d9cee1e16c43aa736123de|1",
      "line": 448,
      "marker": null,
      "path": "nexus/agents/orrery/replay.py",
      "scope": "canonicalize"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/replay.py|_values_equal|0f66b1c93bad2ce598c0087fc93dad328e7f1ceb4bbe44d4c6a341b7451a228b|1",
      "line": 3231,
      "marker": null,
      "path": "nexus/agents/orrery/replay.py",
      "scope": "_values_equal"
    },
    {
      "ast_exempt": true,
      "caught_type": "KeyError",
      "identity": "nexus/agents/orrery/resolver.py|_render_bound_text|b545e285e1cabb0d0897df49ffcc356536ce7c5cd5e7966b56e7ec34bfb080b9|1",
      "line": 3408,
      "marker": null,
      "path": "nexus/agents/orrery/resolver.py",
      "scope": "_render_bound_text"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/orrery/resolver.py|_entity_label|169a7ffa4ea3c8520e576fcea8c2814e19799519cb0f8ea95840a1a278e7d5c1|1",
      "line": 3425,
      "marker": null,
      "path": "nexus/agents/orrery/resolver.py",
      "scope": "_entity_label"
    },
    {
      "ast_exempt": true,
      "caught_type": "RetrogradeExpansionValidationError",
      "identity": "nexus/agents/orrery/retrograde_expansion.py|generate_expansion_with_skald._validate_output|a2b0b0af87a210500472c30359349a975f1638e66adc8e021ea6fae3a9f3ac96|1",
      "line": 787,
      "marker": null,
      "path": "nexus/agents/orrery/retrograde_expansion.py",
      "scope": "generate_expansion_with_skald._validate_output"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeError",
      "identity": "nexus/agents/orrery/retrograde_expansion.py|generate_expansion_with_skald|550c6d392bb80cd094a435e63b2d99e82d412a59c9304bcbdb64cd008dee2bd2|1",
      "line": 798,
      "marker": null,
      "path": "nexus/agents/orrery/retrograde_expansion.py",
      "scope": "generate_expansion_with_skald"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/retrograde_expansion.py|_planned_project_dependency_relationships|179d511e5c70bd77bdbe76353287ae4ee7c73eb4465779db28066ac45643a680|1",
      "line": 1099,
      "marker": null,
      "path": "nexus/agents/orrery/retrograde_expansion.py",
      "scope": "_planned_project_dependency_relationships"
    },
    {
      "ast_exempt": false,
      "caught_type": "MaturationLeaseLostError",
      "identity": "nexus/agents/orrery/retrograde_maturation.py|drain_maturation_jobs_sync|41b3a4ecfa26c019f01733460ebf0acbca308cbd9eec2cb705005e65fe401d72|1",
      "line": 690,
      "marker": null,
      "path": "nexus/agents/orrery/retrograde_maturation.py",
      "scope": "drain_maturation_jobs_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/orrery/retrograde_maturation.py|drain_maturation_jobs_sync|33b71dfe1ead74aa12f92645134fd50860b45524b884ab2d324280377d641f22|1",
      "line": 695,
      "marker": null,
      "path": "nexus/agents/orrery/retrograde_maturation.py",
      "scope": "drain_maturation_jobs_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/orrery/retrograde_maturation.py|_slot_int|bdd58aae791b5c5db7ad74a3234bdc195728aa3c54a085552881793ffb7ad4cf|1",
      "line": 1698,
      "marker": null,
      "path": "nexus/agents/orrery/retrograde_maturation.py",
      "scope": "_slot_int"
    },
    {
      "ast_exempt": true,
      "caught_type": "KeyError",
      "identity": "nexus/agents/orrery/retrograde_project_dependencies.py|is_wary_or_worse|b94beb61ac5be08960c396e42096e245fe41714273770fb2e20e325b90c36ca4|1",
      "line": 34,
      "marker": null,
      "path": "nexus/agents/orrery/retrograde_project_dependencies.py",
      "scope": "is_wary_or_worse"
    },
    {
      "ast_exempt": true,
      "caught_type": "RetrogradeSeedCandidateValidationError",
      "identity": "nexus/agents/orrery/retrograde_seed_candidates.py|generate_seed_candidates_with_skald._validate_output|cda5124aa1b22b13955407a65d34fa6b960923c01e7a0fe74f2be009ad20aabc|1",
      "line": 638,
      "marker": null,
      "path": "nexus/agents/orrery/retrograde_seed_candidates.py",
      "scope": "generate_seed_candidates_with_skald._validate_output"
    },
    {
      "ast_exempt": true,
      "caught_type": "KeyError",
      "identity": "nexus/agents/orrery/substrate.py|contact_pair_tag_for_kind|000310ee912800fb6c93bc2dec714f33c0a0c3c01c0fe560c4feb10dffa94323|1",
      "line": 700,
      "marker": null,
      "path": "nexus/agents/orrery/substrate.py",
      "scope": "contact_pair_tag_for_kind"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/substrate.py|has_severity_tag_at_or_above._condition|9e48d5735b088664d0c5f145e8dd35dc5c7e9323607ac43d10f1147d4c01aae6|1",
      "line": 1109,
      "marker": null,
      "path": "nexus/agents/orrery/substrate.py",
      "scope": "has_severity_tag_at_or_above._condition"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/substrate.py|_minute_of_day|f08a9bcb843a8fca1380cfe91e1cdf24aa63c5c3ae531ce30a1f2e9c44153108|1",
      "line": 1834,
      "marker": null,
      "path": "nexus/agents/orrery/substrate.py",
      "scope": "_minute_of_day"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/tag_library.py|_kind_order|ec0ff246a5a31570554364ae21755ecddfc432ea97ae4d4f1307b1aa27b7d717|1",
      "line": 659,
      "marker": null,
      "path": "nexus/agents/orrery/tag_library.py",
      "scope": "_kind_order"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/agents/orrery/tag_writer.py|validate_tag_bestowal|551026ca2b4884e1094cb9575e347c9986902549ae3590cb8f3af3fd86989599|1",
      "line": 229,
      "marker": null,
      "path": "nexus/agents/orrery/tag_writer.py",
      "scope": "validate_tag_bestowal"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/orrery/tag_writer.py|_asyncpg_status_changed|63fa5572e75c19e7c5894ed37f20d259c061c56f8c47c61608faf87e17a3ba4e|1",
      "line": 1304,
      "marker": null,
      "path": "nexus/agents/orrery/tag_writer.py",
      "scope": "_asyncpg_status_changed"
    },
    {
      "ast_exempt": false,
      "caught_type": "NarrationCompletionRejectedError",
      "identity": "nexus/agents/orrery/worker.py|drain_narration_outbox_sync|64b918570998e833a531547ad342d4f1386add5c8bbdeb6568d8f956c2b4de21|1",
      "line": 359,
      "marker": null,
      "path": "nexus/agents/orrery/worker.py",
      "scope": "drain_narration_outbox_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/agents/orrery/worker.py|drain_narration_outbox_sync|4e6d967e2ceb51288814fe54911875d432cfc454acaa2e45b84541695e112481|1",
      "line": 366,
      "marker": null,
      "path": "nexus/agents/orrery/worker.py",
      "scope": "drain_narration_outbox_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "NarrationLeaseLostError",
      "identity": "nexus/agents/orrery/worker.py|drain_narration_outbox_sync|eab8710fa4d1aeb4051c7b3c90bcfff7211bf26d2dcd80c62edfc70ea6b40e6e|1",
      "line": 380,
      "marker": null,
      "path": "nexus/agents/orrery/worker.py",
      "scope": "drain_narration_outbox_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/agents/orrery/worker.py|_numeric_or_zero|b022b9ddd242d4a6a481e640a11aca59fb4e7df48aa0a2ceb4dc1465520efdbf|1",
      "line": 858,
      "marker": null,
      "path": "nexus/agents/orrery/worker.py",
      "scope": "_numeric_or_zero"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.errors.ReadOnlySqlTransaction",
      "identity": "nexus/agents/orrery/worker.py|main|da00386b84d687015bb1b065ced8023bb8036bacda977ded98a8ff35616c7bef|1",
      "line": 1000,
      "marker": null,
      "path": "nexus/agents/orrery/worker.py",
      "scope": "main"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/asset_endpoints.py|_handle_upload|4c1bcded1f23c30c79383020bc0d228315c14f87f9612ddd67b43e07b2d9a3ab|1",
      "line": 244,
      "marker": null,
      "path": "nexus/api/asset_endpoints.py",
      "scope": "_handle_upload"
    },
    {
      "ast_exempt": false,
      "caught_type": "OSError",
      "identity": "nexus/api/asset_endpoints.py|_delete_image|f09c36e28f59eb9273cf2103df7c6e7e92d90d4336a04319ef90c5c401030f15|1",
      "line": 275,
      "marker": null,
      "path": "nexus/api/asset_endpoints.py",
      "scope": "_delete_image"
    },
    {
      "ast_exempt": true,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/api/backfill_review_packet.py|_validate_manifest_slot|7f832227a62264d39364bba963cb54bcbab370067fae9102e0ffd83b500a83b1|1",
      "line": 227,
      "marker": null,
      "path": "nexus/api/backfill_review_packet.py",
      "scope": "_validate_manifest_slot"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/backstage_endpoints.py|_slot_session|cbfd537b784345bd9c7c1e614fc8ccb9c61a0a532550b9f3223f2550351bc47b|1",
      "line": 36,
      "marker": null,
      "path": "nexus/api/backstage_endpoints.py",
      "scope": "_slot_session"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeError",
      "identity": "nexus/api/backstage_endpoints.py|_slot_session|220e3931487f2e61e11390776aed5fafe98a1c53fd84a3d49b9adeaec8c391f5|1",
      "line": 38,
      "marker": null,
      "path": "nexus/api/backstage_endpoints.py",
      "scope": "_slot_session"
    },
    {
      "ast_exempt": true,
      "caught_type": "BackstagePayloadError",
      "identity": "nexus/api/backstage_endpoints.py|get_backstage_turn|61fd46f81cb43f77f8b0f1430bcb80e965f203763abd033fb3eaa84ae46308ee|1",
      "line": 58,
      "marker": null,
      "path": "nexus/api/backstage_endpoints.py",
      "scope": "get_backstage_turn"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "nexus/api/choice_handling.py|parse_choice_object|ed36ae0ad120d998526ffd76bed048413133af7e5582ad7b47eafe66ce4576b1|1",
      "line": 111,
      "marker": null,
      "path": "nexus/api/choice_handling.py",
      "scope": "parse_choice_object"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/choice_handling.py|parse_choice_object|84d798c1f637d9acdead9ced8534f201b27cf20ca976964426010dea4798b45a|1",
      "line": 124,
      "marker": null,
      "path": "nexus/api/choice_handling.py",
      "scope": "parse_choice_object"
    },
    {
      "ast_exempt": true,
      "caught_type": "json.JSONDecodeError",
      "identity": "nexus/api/choice_handling.py|normalize_choice_object|47388a4ea2a044f65fbc2348ba1494bb43682d82bd1fc6ea40b788bd135bb3be|1",
      "line": 145,
      "marker": null,
      "path": "nexus/api/choice_handling.py",
      "scope": "normalize_choice_object"
    },
    {
      "ast_exempt": true,
      "caught_type": "json.JSONDecodeError",
      "identity": "nexus/api/choice_handling.py|selected_text_from_choice_object|47388a4ea2a044f65fbc2348ba1494bb43682d82bd1fc6ea40b788bd135bb3be|1",
      "line": 200,
      "marker": null,
      "path": "nexus/api/choice_handling.py",
      "scope": "selected_text_from_choice_object"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/choice_handling.py|_parse_selection|231f6102b7cf1663e9029680557ebbe29ffb61fe318d734817f5d20ff573c29b|1",
      "line": 330,
      "marker": null,
      "path": "nexus/api/choice_handling.py",
      "scope": "_parse_selection"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/commit_handler_sync.py|commit_incubator_to_database_sync|dc3849d7bcb074aba87102854c899f29fdf24ee7950e609de1c116a0fc750f10|1",
      "line": 887,
      "marker": null,
      "path": "nexus/api/commit_handler_sync.py",
      "scope": "commit_incubator_to_database_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "openai.OpenAIError",
      "identity": "nexus/api/conversations.py|ConversationsClient.delete_thread|8b694df8a3a7085a2a1f1199e9ef3af933e50fba474661c70890f1b52b058c25|1",
      "line": 357,
      "marker": null,
      "path": "nexus/api/conversations.py",
      "scope": "ConversationsClient.delete_thread"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/api/db_pool.py|get_connection|59c2638015d861dee72510009b282c559816d0431b88cbff422ca4183a94fe3a|1",
      "line": 160,
      "marker": null,
      "path": "nexus/api/db_pool.py",
      "scope": "get_connection"
    },
    {
      "ast_exempt": true,
      "caught_type": "BaseException",
      "identity": "nexus/api/db_pool.py|get_connection|ee6c2d015238189d97a820aebb0010749fd7658b3480c810e475aea329921234|1",
      "line": 167,
      "marker": null,
      "path": "nexus/api/db_pool.py",
      "scope": "get_connection"
    },
    {
      "ast_exempt": true,
      "caught_type": "BaseException",
      "identity": "nexus/api/db_pool.py|get_connection|031eb64c11dfe84c27ca39dcaf693ef21a4d74abc4fefcdc3910a4d85ecdb867|1",
      "line": 179,
      "marker": null,
      "path": "nexus/api/db_pool.py",
      "scope": "get_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/db_pool.py|get_connection|c66f7dcbe569835cda231f29255b2949ab3817663e8311e9f5f69bce5be5a247|1",
      "line": 186,
      "marker": null,
      "path": "nexus/api/db_pool.py",
      "scope": "get_connection"
    },
    {
      "ast_exempt": true,
      "caught_type": "AmbiguousCommit",
      "identity": "nexus/api/db_pool.py|get_connection|4d9812088882d6d79a9d8efdf9b1c09ee8ff8c37393b737caae5cfb6e48d514a|1",
      "line": 193,
      "marker": null,
      "path": "nexus/api/db_pool.py",
      "scope": "get_connection"
    },
    {
      "ast_exempt": true,
      "caught_type": "BaseException",
      "identity": "nexus/api/db_pool.py|get_connection|c1e69db972e809cf605a444b6cac43b8eaf8b46bf708e46b44a7ec5853b17c73|1",
      "line": 196,
      "marker": null,
      "path": "nexus/api/db_pool.py",
      "scope": "get_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/db_pool.py|get_connection|c66f7dcbe569835cda231f29255b2949ab3817663e8311e9f5f69bce5be5a247|2",
      "line": 199,
      "marker": null,
      "path": "nexus/api/db_pool.py",
      "scope": "get_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/local_download_worker.py|main|650beac4e84d0d422c3637eac18e67f9901c657fd10f2467b93bb898d6c32c35|1",
      "line": 26,
      "marker": null,
      "path": "nexus/api/local_download_worker.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/api/local_inference.py|_read_json|c7a0a01b51f7db73f7fce5bdf9fb59b74451bcb95dbe524f41726c526aa69985|1",
      "line": 77,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_read_json"
    },
    {
      "ast_exempt": true,
      "caught_type": "(OSError, json.JSONDecodeError)",
      "identity": "nexus/api/local_inference.py|_read_json|6b17107573b8f11f20a76ebe33b83a243c1b4e6ced2a5a3351ad06a79ec16607|1",
      "line": 79,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_read_json"
    },
    {
      "ast_exempt": true,
      "caught_type": "OSError",
      "identity": "nexus/api/local_inference.py|_write_json|de418874659c5e2de5fe94d93d75314a08f5849ca04ad7bfbae89e5b0075bcbf|1",
      "line": 100,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_write_json"
    },
    {
      "ast_exempt": false,
      "caught_type": "ProcessLookupError",
      "identity": "nexus/api/local_inference.py|_pid_alive|34164cab0e2fff68bfc4f15b988750df1f90ec9726fb2eb1137d839acb70234d|1",
      "line": 113,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_pid_alive"
    },
    {
      "ast_exempt": false,
      "caught_type": "PermissionError",
      "identity": "nexus/api/local_inference.py|_pid_alive|14ffbc89fb4fa254e4dbfb3ab7758ecee940f086f7b5f16aa32cafd94f71cb35|1",
      "line": 115,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_pid_alive"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.RequestException",
      "identity": "nexus/api/local_inference.py|_health_ok|af6187141a8050060c36ded3287173220fffaf421b07f8046cfbb2dfe1727b29|1",
      "line": 230,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_health_ok"
    },
    {
      "ast_exempt": false,
      "caught_type": "(OSError, subprocess.SubprocessError)",
      "identity": "nexus/api/local_inference.py|_process_is_ours|c829651a3d0b37c04b9ed9232199ba0d95638d82263e26d703a6523b90238792|1",
      "line": 278,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_process_is_ours"
    },
    {
      "ast_exempt": false,
      "caught_type": "(OSError, subprocess.SubprocessError)",
      "identity": "nexus/api/local_inference.py|_download_process_is_ours|c829651a3d0b37c04b9ed9232199ba0d95638d82263e26d703a6523b90238792|1",
      "line": 296,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_download_process_is_ours"
    },
    {
      "ast_exempt": true,
      "caught_type": "(KeyError, TypeError, ValueError)",
      "identity": "nexus/api/local_inference.py|_read_active|8ec6418c0869d1c99d7f8d286dfd7a473ffa417f8477439de73b4a1fb792f594|1",
      "line": 314,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_read_active"
    },
    {
      "ast_exempt": false,
      "caught_type": "ProcessLookupError",
      "identity": "nexus/api/local_inference.py|_deactivate_locked|f53b8abd09fa91cbbe76d53558cf43853113962f419b6d7ab1576bf895722901|1",
      "line": 393,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_deactivate_locked"
    },
    {
      "ast_exempt": false,
      "caught_type": "ProcessLookupError",
      "identity": "nexus/api/local_inference.py|_deactivate_locked|f53b8abd09fa91cbbe76d53558cf43853113962f419b6d7ab1576bf895722901|2",
      "line": 409,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_deactivate_locked"
    },
    {
      "ast_exempt": true,
      "caught_type": "OSError",
      "identity": "nexus/api/local_inference.py|activate|7bf355f443be14287620a68a06a8ae08836bd9661860d5bac8ee8e185eca49fc|1",
      "line": 479,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "activate"
    },
    {
      "ast_exempt": true,
      "caught_type": "LocalInferenceError",
      "identity": "nexus/api/local_inference.py|activate|42fb503c8dbbca747304a0ba67e4ce9bef20709f56e445f79337734f717135bc|1",
      "line": 491,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "activate"
    },
    {
      "ast_exempt": false,
      "caught_type": "ProcessLookupError",
      "identity": "nexus/api/local_inference.py|activate|f53b8abd09fa91cbbe76d53558cf43853113962f419b6d7ab1576bf895722901|1",
      "line": 494,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "activate"
    },
    {
      "ast_exempt": true,
      "caught_type": "(KeyError, TypeError, ValueError)",
      "identity": "nexus/api/local_inference.py|_read_download_record|f43f6b8105883e8bd8d9d0075f73e05261d12deb9efe2bde38d82d722d59da98|1",
      "line": 521,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_read_download_record"
    },
    {
      "ast_exempt": true,
      "caught_type": "OSError",
      "identity": "nexus/api/local_inference.py|start_download|20175d0c8bd22dc747fe20613b9bdb5eb4f99100d2c84633740fd6120673549d|1",
      "line": 587,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "start_download"
    },
    {
      "ast_exempt": true,
      "caught_type": "LocalInferenceError",
      "identity": "nexus/api/local_inference.py|start_download|42fb503c8dbbca747304a0ba67e4ce9bef20709f56e445f79337734f717135bc|1",
      "line": 604,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "start_download"
    },
    {
      "ast_exempt": false,
      "caught_type": "ProcessLookupError",
      "identity": "nexus/api/local_inference.py|start_download|f53b8abd09fa91cbbe76d53558cf43853113962f419b6d7ab1576bf895722901|1",
      "line": 607,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "start_download"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/api/local_inference.py|_downloaded_bytes|33b566d793eadc4bd554a2f419e806470a1f558dee2eb5375a98bfb2baf93e0c|1",
      "line": 631,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_downloaded_bytes"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/api/local_inference.py|_downloaded_bytes|33b566d793eadc4bd554a2f419e806470a1f558dee2eb5375a98bfb2baf93e0c|2",
      "line": 638,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_downloaded_bytes"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/api/local_inference.py|_download_error|9854ae515b205ad9237c956ea1c25c176a28807e7fba37aca18d04f35512ea4b|1",
      "line": 647,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "_download_error"
    },
    {
      "ast_exempt": false,
      "caught_type": "ProcessLookupError",
      "identity": "nexus/api/local_inference.py|cancel_download|f53b8abd09fa91cbbe76d53558cf43853113962f419b6d7ab1576bf895722901|1",
      "line": 710,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "cancel_download"
    },
    {
      "ast_exempt": false,
      "caught_type": "ProcessLookupError",
      "identity": "nexus/api/local_inference.py|cancel_download|f53b8abd09fa91cbbe76d53558cf43853113962f419b6d7ab1576bf895722901|2",
      "line": 727,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "cancel_download"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/api/local_inference.py|delete_model|f979f0bbcbd16006fbeac3d4efbf63887f4216d62b89f48cfc8e4a4e587be302|1",
      "line": 748,
      "marker": null,
      "path": "nexus/api/local_inference.py",
      "scope": "delete_model"
    },
    {
      "ast_exempt": false,
      "caught_type": "OSError",
      "identity": "nexus/api/local_models_endpoints.py|_cached_inspect|eee13425411e59d213b04aca785d3e2b0147a6b6b63920794500c6d5fa2f6e6b|1",
      "line": 46,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "_cached_inspect"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/local_models_endpoints.py|_cached_inspect|73c69398fbd8a04e5d889a402fc1ebd2abb4546f06b38aa36511205abd1aa565|1",
      "line": 55,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "_cached_inspect"
    },
    {
      "ast_exempt": true,
      "caught_type": "HTTPException",
      "identity": "nexus/api/local_models_endpoints.py|_verified_path|0c82a7bfa4acd3c06e8d143e2c58cd68c1226bd95a9f80d5113c39de6f8b2297|1",
      "line": 73,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "_verified_path"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/local_models_endpoints.py|_verified_path|f6e8fbef4fc56604e80b3b2f050ed3876cd497e06f14439df80f361da2c82a01|1",
      "line": 75,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "_verified_path"
    },
    {
      "ast_exempt": false,
      "caught_type": "OSError",
      "identity": "nexus/api/local_models_endpoints.py|_installed_models|d3bbc0b0de94eeaba586943bf0bf259e36131290f276b7825a4386567b4e1728|1",
      "line": 120,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "_installed_models"
    },
    {
      "ast_exempt": true,
      "caught_type": "local_inference.LocalInferenceError",
      "identity": "nexus/api/local_models_endpoints.py|status|14cf7b705f35d09e8cc4f2c382564146231ba8ddf8ea5bea6c003462870c2439|1",
      "line": 178,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "status"
    },
    {
      "ast_exempt": true,
      "caught_type": "local_inference.LocalInferenceError",
      "identity": "nexus/api/local_models_endpoints.py|activate|53ab91bbbe9e8ac358f86da776b72a9b7f15af1ccfdd795a9b21a33399484aa9|1",
      "line": 188,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "activate"
    },
    {
      "ast_exempt": true,
      "caught_type": "local_inference.LocalInferenceError",
      "identity": "nexus/api/local_models_endpoints.py|deactivate|14cf7b705f35d09e8cc4f2c382564146231ba8ddf8ea5bea6c003462870c2439|1",
      "line": 209,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "deactivate"
    },
    {
      "ast_exempt": true,
      "caught_type": "local_inference.LocalInferenceError",
      "identity": "nexus/api/local_models_endpoints.py|download|53ab91bbbe9e8ac358f86da776b72a9b7f15af1ccfdd795a9b21a33399484aa9|1",
      "line": 272,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "download"
    },
    {
      "ast_exempt": true,
      "caught_type": "local_inference.LocalInferenceError",
      "identity": "nexus/api/local_models_endpoints.py|delete_model|53ab91bbbe9e8ac358f86da776b72a9b7f15af1ccfdd795a9b21a33399484aa9|1",
      "line": 300,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "delete_model"
    },
    {
      "ast_exempt": true,
      "caught_type": "OSError",
      "identity": "nexus/api/local_models_endpoints.py|browse|bf40318f6233cefb47a02e118f2ebe76b52736d76b7543a41425956400b0cf09|1",
      "line": 348,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "browse"
    },
    {
      "ast_exempt": true,
      "caught_type": "local_inference.LocalInferenceError",
      "identity": "nexus/api/local_models_endpoints.py|register|1ba6055e5af22bef41d2fb208f78101929f1b858cd923bf3fb8b53b2cd893346|1",
      "line": 364,
      "marker": null,
      "path": "nexus/api/local_models_endpoints.py",
      "scope": "register"
    },
    {
      "ast_exempt": false,
      "caught_type": "(RuntimeError, WebSocketDisconnect, OSError)",
      "identity": "nexus/api/narrative.py|ConnectionManager.broadcast|6302a740cc5f79b3b32faa25ff01236d756c14009e8ec783ba08d763f09985c3|1",
      "line": 255,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "ConnectionManager.broadcast"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative.py|_record_player_response_for_chunk|106ca293b69a767e7c874e44cc70abdad7c24132cfe2c0718792fc2f7cb6079f|1",
      "line": 450,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "_record_player_response_for_chunk"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/narrative.py|_record_player_response_for_chunk|faee086562e1ce77d5b6f8940d048407e665a5ef539d8f40b66016a34fde382b|1",
      "line": 508,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "_record_player_response_for_chunk"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/narrative.py|_record_player_response_for_chunk|faee086562e1ce77d5b6f8940d048407e665a5ef539d8f40b66016a34fde382b|2",
      "line": 521,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "_record_player_response_for_chunk"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/narrative.py|_record_player_response_for_chunk|faee086562e1ce77d5b6f8940d048407e665a5ef539d8f40b66016a34fde382b|3",
      "line": 562,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "_record_player_response_for_chunk"
    },
    {
      "ast_exempt": true,
      "caught_type": "HTTPException",
      "identity": "nexus/api/narrative.py|_record_player_response_for_chunk|7da1f4b88fc5c7c3d5432d3295e572d96d1c281f8bed27564e5a37b8d8893cb8|1",
      "line": 593,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "_record_player_response_for_chunk"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative.py|_record_player_response_for_chunk|63b4cdee0533a47da4d847dcbec4150f2aa258c71e45e73b66818cd577cd9a98|1",
      "line": 597,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "_record_player_response_for_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative.py|_abandon_unscheduled_generation_owner|75c730a273b45010c92bbb9bac91947a612cdf64ba31b1186c31c94ef828c0f8|1",
      "line": 711,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "_abandon_unscheduled_generation_owner"
    },
    {
      "ast_exempt": true,
      "caught_type": "HTTPException",
      "identity": "nexus/api/narrative.py|_resolve_and_approve_pending_sync|38ff8214f9766bccc6bd590289f254cdb80d8c0fc0ecb703013ffa3ac759c659|1",
      "line": 760,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "_resolve_and_approve_pending_sync"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative.py|_resolve_and_approve_pending_sync|ace24c94f8794b659ed888cc7ae39b3048b3f9e94b2c3a9dbe84780cfe1a2f81|1",
      "line": 763,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "_resolve_and_approve_pending_sync"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/narrative.py|continue_narrative|b5fe9b8f1780203f3b1f3b43d93881e3ff956fa7757a0da03e23273cff6c0791|1",
      "line": 867,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "continue_narrative"
    },
    {
      "ast_exempt": true,
      "caught_type": "asyncio.CancelledError",
      "identity": "nexus/api/narrative.py|continue_narrative|b84daec58db23c340041d5559260f569b9e8e1cbc4a8da95041277e0badc1d8c|1",
      "line": 1043,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "continue_narrative"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative.py|continue_narrative|82c4c08ce0eb6045766aeca24d28aa9624dfec68df649b400fee302ebeb18c4c|1",
      "line": 1047,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "continue_narrative"
    },
    {
      "ast_exempt": true,
      "caught_type": "GenerationRetryConflict",
      "identity": "nexus/api/narrative.py|retry_narrative|aa6772a588582a60c8b709c6518399e34458078ae94e7e15a162a48058b47cb6|1",
      "line": 1082,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "retry_narrative"
    },
    {
      "ast_exempt": true,
      "caught_type": "asyncio.CancelledError",
      "identity": "nexus/api/narrative.py|retry_narrative|b84daec58db23c340041d5559260f569b9e8e1cbc4a8da95041277e0badc1d8c|1",
      "line": 1135,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "retry_narrative"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative.py|retry_narrative|82c4c08ce0eb6045766aeca24d28aa9624dfec68df649b400fee302ebeb18c4c|1",
      "line": 1139,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "retry_narrative"
    },
    {
      "ast_exempt": true,
      "caught_type": "asyncio.CancelledError",
      "identity": "nexus/api/narrative.py|regenerate_narrative|b84daec58db23c340041d5559260f569b9e8e1cbc4a8da95041277e0badc1d8c|1",
      "line": 1297,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "regenerate_narrative"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative.py|regenerate_narrative|82c4c08ce0eb6045766aeca24d28aa9624dfec68df649b400fee302ebeb18c4c|1",
      "line": 1301,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "regenerate_narrative"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative.py|_approve_narrative_sync|fc1b4a478b4108f5c5223ef8b079a2e4bfcdf9bd7241b3bd2144ea0746fdcbdf|1",
      "line": 1417,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "_approve_narrative_sync"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/narrative.py|select_choice|faee086562e1ce77d5b6f8940d048407e665a5ef539d8f40b66016a34fde382b|1",
      "line": 1513,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "select_choice"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/narrative.py|select_choice|faee086562e1ce77d5b6f8940d048407e665a5ef539d8f40b66016a34fde382b|2",
      "line": 1543,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "select_choice"
    },
    {
      "ast_exempt": true,
      "caught_type": "HTTPException",
      "identity": "nexus/api/narrative.py|select_choice|38ff8214f9766bccc6bd590289f254cdb80d8c0fc0ecb703013ffa3ac759c659|1",
      "line": 1594,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "select_choice"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative.py|select_choice|dc4c22a7be9e51b59a36c4b5bf7f607292d38e85b9ff2f718b035d7dd54cbc01|1",
      "line": 1597,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "select_choice"
    },
    {
      "ast_exempt": false,
      "caught_type": "WebSocketDisconnect",
      "identity": "nexus/api/narrative.py|websocket_endpoint|9a5ff51b667710f15cef499786276a40ecf1bef62d002bc3ad7f848c5c7b46c7|1",
      "line": 1614,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "websocket_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "(RuntimeError, ValueError)",
      "identity": "nexus/api/narrative.py|get_user_character|e25d095ec17d7f7d97ed564ac4676e86997df2c95df16fba413211a5680d3e23|1",
      "line": 1681,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "get_user_character"
    },
    {
      "ast_exempt": false,
      "caught_type": "PlayerIdentityNotEstablishedError",
      "identity": "nexus/api/narrative.py|get_user_character|77d8a7c698a9432747eaefdf438a23087a656ac600ea6fb7fa31ba6e1319259c|1",
      "line": 1701,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "get_user_character"
    },
    {
      "ast_exempt": true,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/api/narrative.py|get_user_character|0f19a1f58b8320cab1ca1e360a95a649a1e50f219f2021edc95a68be406d924b|1",
      "line": 1722,
      "marker": null,
      "path": "nexus/api/narrative.py",
      "scope": "get_user_character"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_generation.py|generate_narrative_async.renew|3c336fa9a46af6d5b6372a85f23413b666a899c771fe4263d6501eafaeb76e70|1",
      "line": 219,
      "marker": null,
      "path": "nexus/api/narrative_generation.py",
      "scope": "generate_narrative_async.renew"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_generation.py|generate_narrative_async|0270e57a15b0ebed7a4c92640db02f7656c1e3cae287634e8ec5281606d3bb55|1",
      "line": 281,
      "marker": null,
      "path": "nexus/api/narrative_generation.py",
      "scope": "generate_narrative_async"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_generation.py|generate_narrative_async|a3ecdc4933de63252a386e703d650ed8ae2d354384ff70001cbbe47d88954641|1",
      "line": 319,
      "marker": null,
      "path": "nexus/api/narrative_generation.py",
      "scope": "generate_narrative_async"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_generation.py|generate_narrative_async|aa28e1602a8edfdae13c8be27d0d7d996834bd49c209168fb039375d6004a7cd|1",
      "line": 396,
      "marker": null,
      "path": "nexus/api/narrative_generation.py",
      "scope": "generate_narrative_async"
    },
    {
      "ast_exempt": false,
      "caught_type": "(Exception, asyncio.CancelledError)",
      "identity": "nexus/api/narrative_generation.py|generate_narrative_async|ede55b2a3aaf2a00e1228849abd2e344c803c3568040cbeee636f7e173e3ef52|1",
      "line": 406,
      "marker": null,
      "path": "nexus/api/narrative_generation.py",
      "scope": "generate_narrative_async"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_generation.py|generate_narrative_async|f4b7b372171ac03ada353c16a63d86f3cfade8433e66dfb8a9a413640d86e3fe|1",
      "line": 420,
      "marker": null,
      "path": "nexus/api/narrative_generation.py",
      "scope": "generate_narrative_async"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_generation.py|generate_narrative_async|18910c3f691df6710bc7a45d693de441a39bb840e698ddb0f962273e2f154ebf|1",
      "line": 428,
      "marker": null,
      "path": "nexus/api/narrative_generation.py",
      "scope": "generate_narrative_async"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_generation.py|write_to_incubator|30022d6c035fbb03281428a83d86157281f33882f85c3468385752e4d857da61|1",
      "line": 636,
      "marker": null,
      "path": "nexus/api/narrative_generation.py",
      "scope": "write_to_incubator"
    },
    {
      "ast_exempt": false,
      "caught_type": "GenerationRetryConflict",
      "identity": "nexus/api/narrative_lease.py|read_retryable_failure|950212bf50e2687c5c3996a9310d3d79e49274ea3c498f73ae47163e30a09e14|1",
      "line": 89,
      "marker": null,
      "path": "nexus/api/narrative_lease.py",
      "scope": "read_retryable_failure"
    },
    {
      "ast_exempt": true,
      "caught_type": "AmbiguousCommit",
      "identity": "nexus/api/narrative_lease.py|acquire_generation_lease|f36991a5b1fc200f927208ec74020ce236f93ff368b6b9564d4392eb0bc86de5|1",
      "line": 276,
      "marker": null,
      "path": "nexus/api/narrative_lease.py",
      "scope": "acquire_generation_lease"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_lease.py|acquire_generation_lease|30022d6c035fbb03281428a83d86157281f33882f85c3468385752e4d857da61|1",
      "line": 278,
      "marker": null,
      "path": "nexus/api/narrative_lease.py",
      "scope": "acquire_generation_lease"
    },
    {
      "ast_exempt": true,
      "caught_type": "AmbiguousCommit",
      "identity": "nexus/api/narrative_lease.py|bind_generation_parent|f36991a5b1fc200f927208ec74020ce236f93ff368b6b9564d4392eb0bc86de5|1",
      "line": 350,
      "marker": null,
      "path": "nexus/api/narrative_lease.py",
      "scope": "bind_generation_parent"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_lease.py|bind_generation_parent|30022d6c035fbb03281428a83d86157281f33882f85c3468385752e4d857da61|1",
      "line": 352,
      "marker": null,
      "path": "nexus/api/narrative_lease.py",
      "scope": "bind_generation_parent"
    },
    {
      "ast_exempt": true,
      "caught_type": "AmbiguousCommit",
      "identity": "nexus/api/narrative_lease.py|claim_parent_embedding|f36991a5b1fc200f927208ec74020ce236f93ff368b6b9564d4392eb0bc86de5|1",
      "line": 402,
      "marker": null,
      "path": "nexus/api/narrative_lease.py",
      "scope": "claim_parent_embedding"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_lease.py|claim_parent_embedding|30022d6c035fbb03281428a83d86157281f33882f85c3468385752e4d857da61|1",
      "line": 404,
      "marker": null,
      "path": "nexus/api/narrative_lease.py",
      "scope": "claim_parent_embedding"
    },
    {
      "ast_exempt": true,
      "caught_type": "AmbiguousCommit",
      "identity": "nexus/api/narrative_lease.py|_finish_generation|f36991a5b1fc200f927208ec74020ce236f93ff368b6b9564d4392eb0bc86de5|1",
      "line": 552,
      "marker": null,
      "path": "nexus/api/narrative_lease.py",
      "scope": "_finish_generation"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/narrative_lease.py|_finish_generation|30022d6c035fbb03281428a83d86157281f33882f85c3468385752e4d857da61|1",
      "line": 554,
      "marker": null,
      "path": "nexus/api/narrative_lease.py",
      "scope": "_finish_generation"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "nexus/api/native_structured_output.py|strict_json_schema|680edd7c43fdc3abec95619775c35e9ac8115f46cebd65949f48021622d9cbe1|1",
      "line": 52,
      "marker": null,
      "path": "nexus/api/native_structured_output.py",
      "scope": "strict_json_schema"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "nexus/api/native_structured_output.py|openai_response_text_format|bddf1b7918d64a9c06acaa54d7595727e56c95e56577b46f32d609cb47085ab3|1",
      "line": 73,
      "marker": null,
      "path": "nexus/api/native_structured_output.py",
      "scope": "openai_response_text_format"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_db_mapper.py|NewStoryDatabaseMapper.save_setting_to_globals|6debc11d210956ca6bdff42edbe57750c64a4a9059ac195e7b680700d72d991f|1",
      "line": 202,
      "marker": null,
      "path": "nexus/api/new_story_db_mapper.py",
      "scope": "NewStoryDatabaseMapper.save_setting_to_globals"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_db_mapper.py|NewStoryDatabaseMapper.save_setting_to_globals|6debc11d210956ca6bdff42edbe57750c64a4a9059ac195e7b680700d72d991f|2",
      "line": 217,
      "marker": null,
      "path": "nexus/api/new_story_db_mapper.py",
      "scope": "NewStoryDatabaseMapper.save_setting_to_globals"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_db_mapper.py|NewStoryDatabaseMapper.save_story_seed|ab56c1f541e40a302d5faa49cdc0c3aa4332b79428740d02ce94f2456a90d3bd|1",
      "line": 249,
      "marker": null,
      "path": "nexus/api/new_story_db_mapper.py",
      "scope": "NewStoryDatabaseMapper.save_story_seed"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_db_mapper.py|NewStoryDatabaseMapper.save_story_seed|ab56c1f541e40a302d5faa49cdc0c3aa4332b79428740d02ce94f2456a90d3bd|2",
      "line": 269,
      "marker": null,
      "path": "nexus/api/new_story_db_mapper.py",
      "scope": "NewStoryDatabaseMapper.save_story_seed"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_db_mapper.py|NewStoryDatabaseMapper.create_location_hierarchy|76fc9ef85af44e45d160bc295e16773a7415b57c02dcf7dbc6682c471e55b0f1|1",
      "line": 470,
      "marker": null,
      "path": "nexus/api/new_story_db_mapper.py",
      "scope": "NewStoryDatabaseMapper.create_location_hierarchy"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_db_mapper.py|NewStoryDatabaseMapper.create_location_hierarchy|21347ce4a8f2ca8126cf0f00a07cd4b115ae7b80be2627310cc771ccb8d7d79b|1",
      "line": 482,
      "marker": null,
      "path": "nexus/api/new_story_db_mapper.py",
      "scope": "NewStoryDatabaseMapper.create_location_hierarchy"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_db_mapper.py|NewStoryDatabaseMapper.perform_transition|0f6c15b3337d1c048083476e75aa0821607f52ec5b5e599a3af5a70fca001bee|1",
      "line": 686,
      "marker": null,
      "path": "nexus/api/new_story_db_mapper.py",
      "scope": "NewStoryDatabaseMapper.perform_transition"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.OperationalError",
      "identity": "nexus/api/new_story_flow.py|start_setup|20496987d3d887e9b590fb750206605c6c5255040d7df84d410e3fffcb102cc2|1",
      "line": 130,
      "marker": null,
      "path": "nexus/api/new_story_flow.py",
      "scope": "start_setup"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_flow.py|_remove_partial_copy|6b6e926a87da3e6b8cfd27602d118d31e071fdbb41d2e11ee8d6ebe8fbc17a59|1",
      "line": 186,
      "marker": null,
      "path": "nexus/api/new_story_flow.py",
      "scope": "_remove_partial_copy"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_flow.py|_remove_partial_copy|1e7775daf71217e0dbf4d0cbdda9227ad84191b45457ed811ea79a87fb07ab9f|1",
      "line": 203,
      "marker": null,
      "path": "nexus/api/new_story_flow.py",
      "scope": "_remove_partial_copy"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_flow.py|switch_wizard_model|6d3a5acbda0d5553e76a116e6a21c6a2579922131569cb8c9709f544ce7e19c6|1",
      "line": 281,
      "marker": null,
      "path": "nexus/api/new_story_flow.py",
      "scope": "switch_wizard_model"
    },
    {
      "ast_exempt": true,
      "caught_type": "AmbiguousCommit",
      "identity": "nexus/api/new_story_flow.py|switch_wizard_model|d819a702a512609763652169780b3101f14f2caa803f4bad576e0d612b2f5661|1",
      "line": 308,
      "marker": null,
      "path": "nexus/api/new_story_flow.py",
      "scope": "switch_wizard_model"
    },
    {
      "ast_exempt": true,
      "caught_type": "BaseException",
      "identity": "nexus/api/new_story_flow.py|switch_wizard_model|26b7127ab9b163df5cfc34bd63f62fb807cc375e547732f0c617ea5ab1bae932|1",
      "line": 319,
      "marker": null,
      "path": "nexus/api/new_story_flow.py",
      "scope": "switch_wizard_model"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_flow.py|perform_transition_with_retrograde|e249e851aa0f29cdb6c151b6daf5ee2d6b0de7c3a85a107055a92fc18eec1d9b|1",
      "line": 632,
      "marker": null,
      "path": "nexus/api/new_story_flow.py",
      "scope": "perform_transition_with_retrograde"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeError",
      "identity": "nexus/api/new_story_flow.py|perform_transition_with_retrograde|5df7fce6219d043045d272a5c934afa7cc5931d04812d5d948d0b9226c270c4d|1",
      "line": 644,
      "marker": null,
      "path": "nexus/api/new_story_flow.py",
      "scope": "perform_transition_with_retrograde"
    },
    {
      "ast_exempt": false,
      "caught_type": "(psycopg2.Error, OSError)",
      "identity": "nexus/api/new_story_flow.py|activate_slot|2414808ef7c6f378846cca4bd5f1c406348bce1d4f79839708d75bb52f044190|1",
      "line": 732,
      "marker": null,
      "path": "nexus/api/new_story_flow.py",
      "scope": "activate_slot"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_generator.py|StoryComponentGenerator.generate_setting_card|bc607e7bdb2084b07a0b843ee751c3f2ad51c71aa84d3eadcc6206b059ae1542|1",
      "line": 126,
      "marker": null,
      "path": "nexus/api/new_story_generator.py",
      "scope": "StoryComponentGenerator.generate_setting_card"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_generator.py|StoryComponentGenerator.generate_character_sheet|dc794ae5c4df7c2c12649bb92e60742eb7ef291bdefde7db8e132e775ddec027|1",
      "line": 175,
      "marker": null,
      "path": "nexus/api/new_story_generator.py",
      "scope": "StoryComponentGenerator.generate_character_sheet"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_generator.py|StoryComponentGenerator.generate_story_seeds|af0fb4d79d60913de1d2993770b84d5a659ffccb14d63677f3d21cf6ac10d540|1",
      "line": 240,
      "marker": null,
      "path": "nexus/api/new_story_generator.py",
      "scope": "StoryComponentGenerator.generate_story_seeds"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/new_story_generator.py|StoryComponentGenerator.generate_location_hierarchy|0f8d0bb76b81e59a34a40abf64e1d410e861abc51daee966b8a76894778c446c|1",
      "line": 295,
      "marker": null,
      "path": "nexus/api/new_story_generator.py",
      "scope": "StoryComponentGenerator.generate_location_hierarchy"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/orrery_dev_endpoints.py|_slot_session|cbfd537b784345bd9c7c1e614fc8ccb9c61a0a532550b9f3223f2550351bc47b|1",
      "line": 270,
      "marker": null,
      "path": "nexus/api/orrery_dev_endpoints.py",
      "scope": "_slot_session"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeError",
      "identity": "nexus/api/orrery_dev_endpoints.py|_slot_session|220e3931487f2e61e11390776aed5fafe98a1c53fd84a3d49b9adeaec8c391f5|1",
      "line": 272,
      "marker": null,
      "path": "nexus/api/orrery_dev_endpoints.py",
      "scope": "_slot_session"
    },
    {
      "ast_exempt": true,
      "caught_type": "OverrideValidationError",
      "identity": "nexus/api/orrery_dev_endpoints.py|post_resolve|93971215a64c151689023de598da4ddbde9f995350304965d9956ea3cfea0af6|1",
      "line": 475,
      "marker": null,
      "path": "nexus/api/orrery_dev_endpoints.py",
      "scope": "post_resolve"
    },
    {
      "ast_exempt": false,
      "caught_type": "CognitionTraceInputError",
      "identity": "nexus/api/orrery_dev_endpoints.py|post_cognition_trace|71ff3e0019a5b606d79cc8300898c82db5e4269f3b82178d7d66e63c53741673|1",
      "line": 524,
      "marker": null,
      "path": "nexus/api/orrery_dev_endpoints.py",
      "scope": "post_cognition_trace"
    },
    {
      "ast_exempt": false,
      "caught_type": "TypeError",
      "identity": "nexus/api/place_tag_manifest.py|_stringify_extra_data|3ae56b802107e0135b162fc2b37d63744a25fae7268f8a071630c7583b9d587c|1",
      "line": 728,
      "marker": null,
      "path": "nexus/api/place_tag_manifest.py",
      "scope": "_stringify_extra_data"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/preferences_endpoints.py|patch_preferences|b5fe9b8f1780203f3b1f3b43d93881e3ff956fa7757a0da03e23273cff6c0791|1",
      "line": 58,
      "marker": null,
      "path": "nexus/api/preferences_endpoints.py",
      "scope": "patch_preferences"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/presence_audit.py|audit_chunk_presence|478315f926bb8e9bf1dda91bfbc2808c47c51ec3520e893937c425a96a9ab28d|1",
      "line": 141,
      "marker": null,
      "path": "nexus/api/presence_audit.py",
      "scope": "audit_chunk_presence"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/reader_endpoints.py|resolve_dbname|cbfd537b784345bd9c7c1e614fc8ccb9c61a0a532550b9f3223f2550351bc47b|1",
      "line": 61,
      "marker": null,
      "path": "nexus/api/reader_endpoints.py",
      "scope": "resolve_dbname"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeError",
      "identity": "nexus/api/reader_endpoints.py|resolve_dbname|220e3931487f2e61e11390776aed5fafe98a1c53fd84a3d49b9adeaec8c391f5|1",
      "line": 63,
      "marker": null,
      "path": "nexus/api/reader_endpoints.py",
      "scope": "resolve_dbname"
    },
    {
      "ast_exempt": false,
      "caught_type": "(RuntimeError, ValueError)",
      "identity": "nexus/api/runtime_status.py|_database_status|e2643d5644a3a7fe66ec35fe2b9b9cd6b5772361779fe19b6b17df051c332870|1",
      "line": 40,
      "marker": null,
      "path": "nexus/api/runtime_status.py",
      "scope": "_database_status"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/api/runtime_status.py|_database_status|4acd8b614a67520b5ec610b7b08ee533da76ebf79464792bc4813a3f412a87e2|1",
      "line": 59,
      "marker": null,
      "path": "nexus/api/runtime_status.py",
      "scope": "_database_status"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/api/runtime_status.py|build_runtime_status|b74c39f702dc64011303736b719fdc14a698b1662bc0fc0fa111a0a2826c1c1c|1",
      "line": 92,
      "marker": null,
      "path": "nexus/api/runtime_status.py",
      "scope": "build_runtime_status"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.RequestException",
      "identity": "nexus/api/runtime_status.py|build_runtime_status|58d304e38ec768cd415a3cd71204914ead0c087a4512ce65a2e62186b8dddf48|1",
      "line": 122,
      "marker": null,
      "path": "nexus/api/runtime_status.py",
      "scope": "build_runtime_status"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeError",
      "identity": "nexus/api/save_slots.py|list_slots|32a89207e753649daef5c3cd2d258e0974e6b81f6e1d1d359c4152f211d3b964|1",
      "line": 53,
      "marker": null,
      "path": "nexus/api/save_slots.py",
      "scope": "list_slots"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/save_slots.py|list_slots|1d3b1073774a77ed170a60018d8a2446a530eae3e94fd07e21d87395ca0b38f0|1",
      "line": 55,
      "marker": null,
      "path": "nexus/api/save_slots.py",
      "scope": "list_slots"
    },
    {
      "ast_exempt": false,
      "caught_type": "PlayerIdentityNotEstablishedError",
      "identity": "nexus/api/save_slots.py|_get_slot_metadata|088c9c5a62501e45d1ff7eef3ba3c4b4906b6b6cbfbc2bfc2c2950d67df98f5c|1",
      "line": 82,
      "marker": null,
      "path": "nexus/api/save_slots.py",
      "scope": "_get_slot_metadata"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/secrets_endpoints.py|required_secret_accounts|3c223790d69907bd5ec7c6df0bb66eb48f76c280b22ba7895c3b4da8d7209415|1",
      "line": 171,
      "marker": null,
      "path": "nexus/api/secrets_endpoints.py",
      "scope": "required_secret_accounts"
    },
    {
      "ast_exempt": true,
      "caught_type": "SeatRequirementError",
      "identity": "nexus/api/secrets_endpoints.py|_requirements_for|b09ff588db25235b8f26ed15f874c74036a42fcd1e75902c9300e78a76c741ad|1",
      "line": 201,
      "marker": null,
      "path": "nexus/api/secrets_endpoints.py",
      "scope": "_requirements_for"
    },
    {
      "ast_exempt": false,
      "caught_type": "MissingSecretError",
      "identity": "nexus/api/secrets_endpoints.py|_status_for|7e9fca78a7e19f5ab50697b5755a40302706de3bac8f4584e222c05d22c4f3df|1",
      "line": 216,
      "marker": null,
      "path": "nexus/api/secrets_endpoints.py",
      "scope": "_status_for"
    },
    {
      "ast_exempt": true,
      "caught_type": "SecretStoreAccessError",
      "identity": "nexus/api/secrets_endpoints.py|_status_for|209a65fdc4aa97c2290da2ce075c824b9586576fe8542ad81dbcb8e2bfc0ca8e|1",
      "line": 221,
      "marker": null,
      "path": "nexus/api/secrets_endpoints.py",
      "scope": "_status_for"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/secrets_endpoints.py|put_secret|7ffcfd93d562a937bc41d1512918360eab8bff38e4a549d83f72e0961c1f55dc|1",
      "line": 306,
      "marker": null,
      "path": "nexus/api/secrets_endpoints.py",
      "scope": "put_secret"
    },
    {
      "ast_exempt": false,
      "caught_type": "SecretStoreAccessError",
      "identity": "nexus/api/secrets_endpoints.py|verify_secret|fc605f42a00e2e99e6398a83307b091d8cebab8ca2538933a708a548dc344a9f|1",
      "line": 326,
      "marker": null,
      "path": "nexus/api/secrets_endpoints.py",
      "scope": "verify_secret"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/secrets_endpoints.py|verify_secret|3af01d960d2c5e6421da9c8e26aeec4b3dc78ade261ee4966da8c58ab4a08dd0|1",
      "line": 332,
      "marker": null,
      "path": "nexus/api/secrets_endpoints.py",
      "scope": "verify_secret"
    },
    {
      "ast_exempt": false,
      "caught_type": "ModuleNotFoundError",
      "identity": "nexus/api/settings_endpoints.py|<module>|689dcd6843e00986a109881f733498a45cf510cfaf3bfa73fdc6acb01c3c93fc|1",
      "line": 13,
      "marker": null,
      "path": "nexus/api/settings_endpoints.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/setup_endpoints.py|start_setup_endpoint|75412b35a44411afe89705c7f33346834a2980bd5697d098a39b5113b70c6a8f|1",
      "line": 89,
      "marker": null,
      "path": "nexus/api/setup_endpoints.py",
      "scope": "start_setup_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "HTTPException",
      "identity": "nexus/api/setup_endpoints.py|resume_setup_endpoint|0c82a7bfa4acd3c06e8d143e2c58cd68c1226bd95a9f80d5113c39de6f8b2297|1",
      "line": 151,
      "marker": null,
      "path": "nexus/api/setup_endpoints.py",
      "scope": "resume_setup_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/setup_endpoints.py|resume_setup_endpoint|14082a1784f4785afb5769e83dafee48f432c25f8f01b265b581c0de452bf420|1",
      "line": 153,
      "marker": null,
      "path": "nexus/api/setup_endpoints.py",
      "scope": "resume_setup_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "WizardStateConflict",
      "identity": "nexus/api/setup_endpoints.py|confirm_setup_artifact_endpoint|7ca9ecf9a3dccc87ae3c81eaf1b8abd0d3276daa48a9fcb9b9eb02c8ff01f126|1",
      "line": 171,
      "marker": null,
      "path": "nexus/api/setup_endpoints.py",
      "scope": "confirm_setup_artifact_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "WizardStateConflict",
      "identity": "nexus/api/setup_endpoints.py|revise_character_endpoint|7ca9ecf9a3dccc87ae3c81eaf1b8abd0d3276daa48a9fcb9b9eb02c8ff01f126|1",
      "line": 185,
      "marker": null,
      "path": "nexus/api/setup_endpoints.py",
      "scope": "revise_character_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/setup_endpoints.py|record_drafts_endpoint|ed73c34da00921035a40a78a8c58496f3460c1d2041472e6f4a6007aa3552a2f|1",
      "line": 203,
      "marker": null,
      "path": "nexus/api/setup_endpoints.py",
      "scope": "record_drafts_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/setup_endpoints.py|reset_setup_endpoint|891b991a532733678f4b83e3fa0a6eae0ab735161a1eaf8ff9cab947759c33ba|1",
      "line": 215,
      "marker": null,
      "path": "nexus/api/setup_endpoints.py",
      "scope": "reset_setup_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/setup_endpoints.py|select_slot_endpoint|8cc23de735a634e225af3cfe2f500b0ac82a623ea4ddb45c97e2a43c0cb1e052|1",
      "line": 229,
      "marker": null,
      "path": "nexus/api/setup_endpoints.py",
      "scope": "select_slot_endpoint"
    },
    {
      "ast_exempt": false,
      "caught_type": "(psycopg2.OperationalError, psycopg2.DatabaseError)",
      "identity": "nexus/api/setup_endpoints.py|get_slots_status_endpoint|2fabb28c05ff11e3ffe6633dd6797caab213ae3cb151b8d6df2880ca59613d13|1",
      "line": 269,
      "marker": null,
      "path": "nexus/api/setup_endpoints.py",
      "scope": "get_slots_status_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/setup_endpoints.py|get_slots_status_endpoint|46dd8f988658d02d257cf447572db32674eacb8ad4165a698a701ece8e8e7935|1",
      "line": 275,
      "marker": null,
      "path": "nexus/api/setup_endpoints.py",
      "scope": "get_slots_status_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/slot_endpoints.py|get_slot_state_endpoint|47baf01b4dc79976a894847f3e7491001e765408cc99bce131332de465714f71|1",
      "line": 183,
      "marker": null,
      "path": "nexus/api/slot_endpoints.py",
      "scope": "get_slot_state_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/slot_endpoints.py|slot_undo_endpoint|e0d6c70a3d92c909f8130f25bebb8d2d9d7ec15f90f5f5ca2122461eccd43651|1",
      "line": 323,
      "marker": null,
      "path": "nexus/api/slot_endpoints.py",
      "scope": "slot_undo_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/slot_endpoints.py|patch_slot_settings_endpoint|b5fe9b8f1780203f3b1f3b43d93881e3ff956fa7757a0da03e23273cff6c0791|1",
      "line": 359,
      "marker": null,
      "path": "nexus/api/slot_endpoints.py",
      "scope": "patch_slot_settings_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeError",
      "identity": "nexus/api/slot_endpoints.py|patch_slot_settings_endpoint|1753cb528591de024af9de3374057f4a124dc51c828d84fcb2c56f4a853a8c38|1",
      "line": 361,
      "marker": null,
      "path": "nexus/api/slot_endpoints.py",
      "scope": "patch_slot_settings_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeError",
      "identity": "nexus/api/slot_endpoints.py|patch_slot_settings_endpoint|1753cb528591de024af9de3374057f4a124dc51c828d84fcb2c56f4a853a8c38|2",
      "line": 376,
      "marker": null,
      "path": "nexus/api/slot_endpoints.py",
      "scope": "patch_slot_settings_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/slot_endpoints.py|lock_slot_endpoint|d995d5591f333d69d2d0c00434d063644a930eb4fef1b2975982e37944dc19c4|1",
      "line": 397,
      "marker": null,
      "path": "nexus/api/slot_endpoints.py",
      "scope": "lock_slot_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/slot_endpoints.py|unlock_slot_endpoint|0523da53a8193697e021d03c6ae5add389bfd8f72b9288d94138de5bb0be1adc|1",
      "line": 418,
      "marker": null,
      "path": "nexus/api/slot_endpoints.py",
      "scope": "unlock_slot_endpoint"
    },
    {
      "ast_exempt": false,
      "caught_type": "PlayerIdentityNotEstablishedError",
      "identity": "nexus/api/slot_state.py|get_slot_state|7f977ce16f67a2f182214e22244aa0af958f4552d0532d60363fbd44df805bd7|1",
      "line": 178,
      "marker": null,
      "path": "nexus/api/slot_state.py",
      "scope": "get_slot_state"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/slot_utils.py|get_active_slot|b837a8f4f529056722734ab793eec9e3f9fb368f6dd89a19d85768b588d538d9|1",
      "line": 70,
      "marker": null,
      "path": "nexus/api/slot_utils.py",
      "scope": "get_active_slot"
    },
    {
      "ast_exempt": false,
      "caught_type": "StarletteHTTPException",
      "identity": "nexus/api/static_ui.py|SpaStaticFiles.get_response|176b7731aa08be0fcbefca3ada9ec5ec5fa96c7ac02e5799366c88b71d4cb0e9|1",
      "line": 59,
      "marker": null,
      "path": "nexus/api/static_ui.py",
      "scope": "SpaStaticFiles.get_response"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/trait_compiler.py|apply_character_trait_compilation|2ac1f90dff2bd96a15991e960fe0c14965ace6417f54ff21f84da74e951d1529|1",
      "line": 338,
      "marker": null,
      "path": "nexus/api/trait_compiler.py",
      "scope": "apply_character_trait_compilation"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/api/trait_compiler.py|_compile_status|9818ba90cd2442c1faba6a4c9b4cffd37f164a390ef40fc07882148328194b13|1",
      "line": 703,
      "marker": null,
      "path": "nexus/api/trait_compiler.py",
      "scope": "_compile_status"
    },
    {
      "ast_exempt": true,
      "caught_type": "KeyError",
      "identity": "nexus/api/trait_compiler.py|_project_authored_valence_for_report|9fbdada91d5f0d231a88cb392872d25ca93353e020dd2f4cef8a1e248ecc993c|1",
      "line": 1996,
      "marker": null,
      "path": "nexus/api/trait_compiler.py",
      "scope": "_project_authored_valence_for_report"
    },
    {
      "ast_exempt": false,
      "caught_type": "CallDeferred",
      "identity": "nexus/api/wizard_agent.py|_atomic_artifact_write.guarded|c676387aaab34687d0ac162e8a265c6aea9a11a2544bbc75fe7b94abff9edd7a|1",
      "line": 327,
      "marker": null,
      "path": "nexus/api/wizard_agent.py",
      "scope": "_atomic_artifact_write.guarded"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_endpoint|fb0fba2b5d218b71a960a846f0e49c24022812e642d4b532e743048bb69734d8|1",
      "line": 772,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_endpoint"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_endpoint|730a0ad62f7e700aedc6d1c8b16ab2f8cab571a9ca7336c33066c121bbe32550|1",
      "line": 815,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "HTTPException",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_endpoint|0c82a7bfa4acd3c06e8d143e2c58cd68c1226bd95a9f80d5113c39de6f8b2297|1",
      "line": 857,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "WizardStateConflict",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_endpoint|8bdecf35d1605ca6e548399d01e8343570606b297ec36fbca85c305f4777406b|1",
      "line": 859,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_endpoint|b5c560b5211ef1d4b11b30a29c3ecfc78cc8b8ccb30b29b68a3e71cf354815f6|1",
      "line": 861,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "WizardStateConflict",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_stream_endpoint|7ca9ecf9a3dccc87ae3c81eaf1b8abd0d3276daa48a9fcb9b9eb02c8ff01f126|1",
      "line": 925,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_stream_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "WizardStateConflict",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_stream_endpoint|7ca9ecf9a3dccc87ae3c81eaf1b8abd0d3276daa48a9fcb9b9eb02c8ff01f126|2",
      "line": 977,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_stream_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "WizardConversationMoveError",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_stream_endpoint|7a5a97dac70e37f3a80f39076b0351fe5cff3a81a51e2ce9a84d5f251abf44a4|1",
      "line": 979,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_stream_endpoint"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_stream_endpoint.wizard_events|2e26b6145d23378bbe531f8663edbfc55460043d18da997bc263bca43ef00e4b|1",
      "line": 1168,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_stream_endpoint.wizard_events"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_stream_endpoint.wizard_events|326cd8cce1c1e55ab05eb3c7bc20df030ab107da8b427799b8070ce405d49952|1",
      "line": 1210,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_stream_endpoint.wizard_events"
    },
    {
      "ast_exempt": false,
      "caught_type": "HTTPException",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_stream_endpoint.event_stream|0a5cd444e4e9ed1deb4ebe327582a9c296c3e8c491603e998514d422f7ce4242|1",
      "line": 1254,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_stream_endpoint.event_stream"
    },
    {
      "ast_exempt": false,
      "caught_type": "WizardStateConflict",
      "identity": "nexus/api/wizard_chat.py|new_story_chat_stream_endpoint.event_stream|681aaff4fc4ba4e430e83b7825aa636414c6cede1811c147f0d70637b350a805|1",
      "line": 1258,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "new_story_chat_stream_endpoint.event_stream"
    },
    {
      "ast_exempt": true,
      "caught_type": "WizardStateConflict",
      "identity": "nexus/api/wizard_chat.py|_record_weird_level|7ca9ecf9a3dccc87ae3c81eaf1b8abd0d3276daa48a9fcb9b9eb02c8ff01f126|1",
      "line": 1277,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "_record_weird_level"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValidationError",
      "identity": "nexus/api/wizard_chat.py|transition_to_narrative_endpoint|4f381ece74e931e4c39e5cbc72aabfebf7ae2bf101634ed248dcf59b6d10c210|1",
      "line": 1382,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "transition_to_narrative_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/api/wizard_chat.py|transition_to_narrative_endpoint|34ddfb1a84d78b7161cc73bb234794dae6532040bf2e23b9c9f25dd746464017|1",
      "line": 1416,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "transition_to_narrative_endpoint"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/api/wizard_chat.py|transition_to_narrative_endpoint|0414be15e9e2b29d1a9a5b46e4f30ef1a6653491adf6218d6c8874bfadec476c|1",
      "line": 1421,
      "marker": null,
      "path": "nexus/api/wizard_chat.py",
      "scope": "transition_to_narrative_endpoint"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "nexus/api/wizard_test_cache.py|load_cache|cb6106b44a52aa8bb2a023ce798379e898dad062d1c253596cc6b4ef474e4a7a|1",
      "line": 51,
      "marker": null,
      "path": "nexus/api/wizard_test_cache.py",
      "scope": "load_cache"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|_get_next_phase|489da708bbcbc410fb31ed5dfbce85104c4aed252b3ba734ad9c81d8997c1e14|1",
      "line": 209,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_get_next_phase"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|_api_answer|877177b55418fae12d0b75cf15618856bbcf11313109c78c104c6697906a6502|1",
      "line": 1275,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_api_answer"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|_inspect_body|47ed4fbf770aa9535ca8f4cf44614f778316fbe6eaf981c60bff5aeb63cfcff1|1",
      "line": 1453,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_inspect_body"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValueError, AttributeError)",
      "identity": "nexus/cli.py|_inspect_chunks|e4bcef6ba89efbed878149ed9cb4e246fa2e7a8e6073ea30d56e47006b5476ac|1",
      "line": 1531,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_inspect_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "InspectFailure",
      "identity": "nexus/cli.py|run_inspect|3556798c7fe27816b5e12d2fe4a86e5fdc7727e9d38389a03f8f370dc8950a02|1",
      "line": 1638,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_inspect"
    },
    {
      "ast_exempt": false,
      "caught_type": "(requests.RequestException, ValueError)",
      "identity": "nexus/cli.py|_RetrogradeStageEcho._fetch|d7fe139526a7379a1c1a7ca0ea7a5bae91433b5b2831fb5785a4ce1745440daa|1",
      "line": 1750,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_RetrogradeStageEcho._fetch"
    },
    {
      "ast_exempt": true,
      "caught_type": "requests.exceptions.RequestException",
      "identity": "nexus/cli.py|wait_for_session|3ccf1da841f71d2462fcc7c1139a6e065ca8c0bade1d51e7da3a7f8e7bbd28a2|1",
      "line": 1975,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "wait_for_session"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|wait_for_session|a55877a51b62ac27c6120f11e7519faa75caaea43cecfe8f86161a59023a658e|1",
      "line": 1989,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "wait_for_session"
    },
    {
      "ast_exempt": true,
      "caught_type": "KeyboardInterrupt",
      "identity": "nexus/cli.py|wait_for_session|89cc8580fea376cee281c7a0ec9398d1f38be4f64589a0f7eb60682d633cedff|1",
      "line": 2001,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "wait_for_session"
    },
    {
      "ast_exempt": true,
      "caught_type": "requests.exceptions.RequestException",
      "identity": "nexus/cli.py|_load_session_result|3da36d2e461de85378c4dceb5be1b5264122c450ca04c8e72a5d6b69de91aaaa|1",
      "line": 2025,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_load_session_result"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|_load_session_result|a55877a51b62ac27c6120f11e7519faa75caaea43cecfe8f86161a59023a658e|1",
      "line": 2052,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_load_session_result"
    },
    {
      "ast_exempt": false,
      "caught_type": "KeyboardInterrupt",
      "identity": "nexus/cli.py|_wait_for_narrative_result|14cf5dd35faee16b6ee86c3012c83c5e179aa96dadb4330dcf16abdd80daad5e|1",
      "line": 2101,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_wait_for_narrative_result"
    },
    {
      "ast_exempt": false,
      "caught_type": "SessionWaitFailure",
      "identity": "nexus/cli.py|_wait_for_narrative_result|2b6b0790f6f9773642caedd733e4602d0c4fae058b6cf6fcf96eb0def2bf4fe9|1",
      "line": 2105,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_wait_for_narrative_result"
    },
    {
      "ast_exempt": false,
      "caught_type": "KeyboardInterrupt",
      "identity": "nexus/cli.py|_bootstrap_seed_narrative|aa5ff2bca6b573171e2fd516a3b8287160775dd8fcaf7153b581dde13ff85b6f|1",
      "line": 2158,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_bootstrap_seed_narrative"
    },
    {
      "ast_exempt": false,
      "caught_type": "(requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.exceptions.Timeout)",
      "identity": "nexus/cli.py|_bootstrap_seed_narrative|6bd8e46899b343416ecb7f2733d3ae9f6cb822a9ebbf58f5017d5b732c37e250|1",
      "line": 2163,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_bootstrap_seed_narrative"
    },
    {
      "ast_exempt": false,
      "caught_type": "(requests.exceptions.RequestException, ValueError)",
      "identity": "nexus/cli.py|_bootstrap_seed_narrative|d4453210db157d85a973502202c862d81431217e25f2db0c84ce1988abe1708b|1",
      "line": 2177,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_bootstrap_seed_narrative"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.exceptions.RequestException",
      "identity": "nexus/cli.py|_apply_traits_to_wildcard_transition|03ed12eb3b8d2c4a4a942b5798ca91be9f1a194accd1e8b54092e3d519946c83|1",
      "line": 2288,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_apply_traits_to_wildcard_transition"
    },
    {
      "ast_exempt": false,
      "caught_type": "ApiAnswerFailure",
      "identity": "nexus/cli.py|_apply_traits_to_wildcard_transition|9ff0fdf3d4671d1db083abb662bb008f780e786c1bcd6c1627a8abae0f6b2b51|1",
      "line": 2301,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_apply_traits_to_wildcard_transition"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValueError, requests.exceptions.RequestException)",
      "identity": "nexus/cli.py|_confirm_wizard_artifact_and_introduce|3252244bb5f971cc5dda3543130daa399ab87e3d03d20f2997215ca3d2257551|1",
      "line": 2366,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_confirm_wizard_artifact_and_introduce"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValueError, requests.exceptions.RequestException)",
      "identity": "nexus/cli.py|_introduce_accepted_phase|846b120f5e5a9f715ba3d0195ab06818e622572f3e6dd8b59db630ead0113c31|1",
      "line": 2434,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_introduce_accepted_phase"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|run_continue|6e87db5868e6add47754fef69fc7e30cd2812be73380c877ea719eef52c252b4|1",
      "line": 2644,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_continue"
    },
    {
      "ast_exempt": false,
      "caught_type": "(requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.exceptions.Timeout)",
      "identity": "nexus/cli.py|run_continue|ee79b8c396d605854f162f8ca63940c46f1e77629244b0bb06236f3ec1537a97|1",
      "line": 2858,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_continue"
    },
    {
      "ast_exempt": false,
      "caught_type": "ApiAnswerFailure",
      "identity": "nexus/cli.py|run_continue|835aeb580b17ee1e317a9e8a41fdcb0d799c0c5d7f8b8403ac8725f9ab186c4a|1",
      "line": 2896,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_continue"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/cli.py|run_model|ece3691252bd9b4974e2f7c3d9daa50f0e836295c35a2cffa2eae2d39ed75519|1",
      "line": 3100,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_model"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|run_model|6e87db5868e6add47754fef69fc7e30cd2812be73380c877ea719eef52c252b4|1",
      "line": 3108,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_model"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "nexus/cli.py|run_trait_audit|032bd815a8532fffc57ddc0a8a3cf3b8be6f4f7ca1e9448a0601e650ebf827fa|1",
      "line": 3160,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_trait_audit"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|run_trait_audit|766bc0988e6446c72d74b871e6446636eb8fb57603eb22eee498d330cc1566e0|1",
      "line": 3162,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_trait_audit"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|run_retrograde_packet|6e87db5868e6add47754fef69fc7e30cd2812be73380c877ea719eef52c252b4|1",
      "line": 3253,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_retrograde_packet"
    },
    {
      "ast_exempt": false,
      "caught_type": "(OSError, ValueError, json.JSONDecodeError)",
      "identity": "nexus/cli.py|run_retrograde_seed_candidates|42bdd35e402542c779092ff0a04f6c6715a7fa25957349317777423ae71688c5|1",
      "line": 3284,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_retrograde_seed_candidates"
    },
    {
      "ast_exempt": false,
      "caught_type": "(OSError, ValueError, json.JSONDecodeError)",
      "identity": "nexus/cli.py|run_retrograde_expand_seeds|42bdd35e402542c779092ff0a04f6c6715a7fa25957349317777423ae71688c5|1",
      "line": 3336,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_retrograde_expand_seeds"
    },
    {
      "ast_exempt": false,
      "caught_type": "(OSError, ValueError, json.JSONDecodeError)",
      "identity": "nexus/cli.py|run_retrograde_apply_expansion|42bdd35e402542c779092ff0a04f6c6715a7fa25957349317777423ae71688c5|1",
      "line": 3382,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_retrograde_apply_expansion"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|run_retrograde_apply_expansion|6e87db5868e6add47754fef69fc7e30cd2812be73380c877ea719eef52c252b4|1",
      "line": 3416,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_retrograde_apply_expansion"
    },
    {
      "ast_exempt": false,
      "caught_type": "RuntimeError",
      "identity": "nexus/cli.py|run_retrograde_apply_expansion|76852a6e211c1964e599f5be0e40790e574e681e70a8bc788ef52de6da2cfea2|1",
      "line": 3426,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_retrograde_apply_expansion"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValueError, RuntimeError)",
      "identity": "nexus/cli.py|run_retrograde_embed_history|a653da0cbb308a80a86916ef8d27f99bc6cabe86173ab8d16f09ff523b15cb49|1",
      "line": 3499,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_retrograde_embed_history"
    },
    {
      "ast_exempt": false,
      "caught_type": "RuntimeError",
      "identity": "nexus/cli.py|run_retrograde_embed_history|cb7454f090c4e8791f8066736478d64d8216fd1fa62753d2c7722c7f13bc30c1|1",
      "line": 3511,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_retrograde_embed_history"
    },
    {
      "ast_exempt": false,
      "caught_type": "EpistemicsValidationError",
      "identity": "nexus/cli.py|run_record_revelation.apply|3325cae141f223aa71ca89751530ac7f61d3df276d7b8fb3f671e076f257a0ce|1",
      "line": 3568,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_record_revelation.apply"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|parse_record_revelation_world_time|e3fe0d8f95f1b8a26004d8b0962fd45cc776eed18f69f51fa5f883bda7e32f49|1",
      "line": 3609,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "parse_record_revelation_world_time"
    },
    {
      "ast_exempt": true,
      "caught_type": "_TRANSPORT_ERRORS",
      "identity": "nexus/cli.py|run_up|6246fe58c19c081b00bfa75521e838d21bcda4f063a8c0b4e26f84490f3ebb61|1",
      "line": 4215,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_up"
    },
    {
      "ast_exempt": false,
      "caught_type": "(RuntimeError_, FileNotFoundError, ValueError, requests.RequestException)",
      "identity": "nexus/cli.py|run_up|df4b89214c91eb5de5add345b066b35bed0e394c2f063a94cbbf876981285d8f|1",
      "line": 4219,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_up"
    },
    {
      "ast_exempt": false,
      "caught_type": "(RuntimeError_, FileNotFoundError)",
      "identity": "nexus/cli.py|run_down|68580e7587afcf9a2d0407514bc1f95ca91c9e2bdc2706fda7bf5be7b1d81b7a|1",
      "line": 4243,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_down"
    },
    {
      "ast_exempt": false,
      "caught_type": "(RuntimeError_, FileNotFoundError, requests.RequestException)",
      "identity": "nexus/cli.py|run_restart|1f1c2d114898e2ed9598fdd324d241495d4b82f93640fa81d1787c1968b95816|1",
      "line": 4258,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_restart"
    },
    {
      "ast_exempt": false,
      "caught_type": "(RuntimeError_, FileNotFoundError, MissingSecretError, SecretStoreAccessError, ValueError)",
      "identity": "nexus/cli.py|run_status|fa07fd1fe0d789209c23892c11a3c425dca238bb69636cf3c17171e696e18ef1|1",
      "line": 4353,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_status"
    },
    {
      "ast_exempt": false,
      "caught_type": "KeyboardInterrupt",
      "identity": "nexus/cli.py|run_logs|437bfdb1233fc2f733fda77e8c3c74e850d730714c6f70ba09a2a2271a35dc50|1",
      "line": 4379,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_logs"
    },
    {
      "ast_exempt": false,
      "caught_type": "(RuntimeError_, FileNotFoundError)",
      "identity": "nexus/cli.py|run_logs|68580e7587afcf9a2d0407514bc1f95ca91c9e2bdc2706fda7bf5be7b1d81b7a|1",
      "line": 4382,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_logs"
    },
    {
      "ast_exempt": false,
      "caught_type": "(RuntimeHomeError, HomePlanError, FileNotFoundError)",
      "identity": "nexus/cli.py|run_home|22474dcc6cb9a67a499805e33473f3ca6ee23f8931c8f1408490796fc8c532c2|1",
      "line": 4393,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_home"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|run_window_replay|6e87db5868e6add47754fef69fc7e30cd2812be73380c877ea719eef52c252b4|1",
      "line": 4445,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_window_replay"
    },
    {
      "ast_exempt": false,
      "caught_type": "NoPromptWindowsError",
      "identity": "nexus/cli.py|run_window_replay|67cb212d328bb1bc17386b02ac9fca6c17923db7d3317ed4a43bace740443089|1",
      "line": 4459,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_window_replay"
    },
    {
      "ast_exempt": false,
      "caught_type": "DeprecatedTagAuditError",
      "identity": "nexus/cli.py|run_tags_audit|2a2e57e059a1f8fc123ffaaf5b678a2b6c6e33faa8a216083e5f8646e47cb4a9|1",
      "line": 4579,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_tags_audit"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.OperationalError",
      "identity": "nexus/cli.py|run_tags_audit|1712d63e8c43c49be64f0647b0787ccf7939d40569c42e59d3b71a2696878501|1",
      "line": 4581,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "run_tags_audit"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|_usage_error|bc031c96ab265db073d5a8ba45030098c5afc0b570bfa7284c0a9255b6374f70|1",
      "line": 5866,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_usage_error"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/cli.py|_usage_error|bc031c96ab265db073d5a8ba45030098c5afc0b570bfa7284c0a9255b6374f70|2",
      "line": 5873,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_usage_error"
    },
    {
      "ast_exempt": false,
      "caught_type": "NoGenerationSessionError",
      "identity": "nexus/cli.py|_dispatch|f5b6ee770b0eff950d38917043840c42127a312c75daa4dcda72747a69d7ff88|1",
      "line": 5937,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "_dispatch"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/cli.py|main|d09fbfb29db16feaaca31e1a4bf9e5eaceebfb179f021957e3e47e0f1cbcfdb3|1",
      "line": 6027,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "(RuntimeHomeError, ValueError)",
      "identity": "nexus/cli.py|main|3413d702a81ff858de07157ce77a8662f5623b4e58075e6d81585bac53483161|1",
      "line": 6029,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "(requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError)",
      "identity": "nexus/cli.py|main|6745e5a1a11225b5a437b36ef2090dd3e3943927189064054e0bb296df5b27eb|1",
      "line": 6042,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.exceptions.Timeout",
      "identity": "nexus/cli.py|main|297c635f62429bcab68692baf079e38b028f3e703a2a5f3299806cda544cf057|1",
      "line": 6050,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "_API_URL_ERRORS",
      "identity": "nexus/cli.py|main|5fcbd90ff7607daf25d83adf29f22308fe20ae005b2e024b733469060051e1a8|1",
      "line": 6055,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "_CREDENTIAL_ERRORS",
      "identity": "nexus/cli.py|main|3da895cf46dc21dc1ed26b5dc0942836d9b420612afc5637ab98d13b4ffc8be0|1",
      "line": 6061,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "ApiAnswerFailure",
      "identity": "nexus/cli.py|main|002d387b32980f72a7bf09edcc9bc95a16dc2e4451aac5d6c990ba14d806f57b|1",
      "line": 6063,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.exceptions.RequestException",
      "identity": "nexus/cli.py|main|4a58b79bf70fa6abd83e77eeef30225f7c6d343a4fc02b990aa9f2f06fd6ff8f|1",
      "line": 6070,
      "marker": null,
      "path": "nexus/cli.py",
      "scope": "main"
    },
    {
      "ast_exempt": true,
      "caught_type": "KeyError",
      "identity": "nexus/cli_contract.py|exit_code_for|dc1a5d09764e8ed1a5021c3a34e38e3b5cc1a948f0081c4c7c724ee327656ada|1",
      "line": 224,
      "marker": null,
      "path": "nexus/cli_contract.py",
      "scope": "exit_code_for"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/cli_contract.py|is_loopback_url|7d0e8d9691f890c01670266608ee21503804bacb5b6a21234b1f5e71c861d66f|1",
      "line": 326,
      "marker": null,
      "path": "nexus/cli_contract.py",
      "scope": "is_loopback_url"
    },
    {
      "ast_exempt": false,
      "caught_type": "ModuleNotFoundError",
      "identity": "nexus/config/loader.py|<module>|1a2d48b34a24cddc4c312dfc8dee531b154e356519936d83f56417a64040498e|1",
      "line": 26,
      "marker": null,
      "path": "nexus/config/loader.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": true,
      "caught_type": "ModuleNotFoundError",
      "identity": "nexus/config/loader.py|<module>|9a24712d89d1d38bae52b3665cbdd79ac138ff7258d76d1a52cdad049cd542f2|1",
      "line": 29,
      "marker": null,
      "path": "nexus/config/loader.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/config/loader.py|_load_from_toml|ce84bcf5e19001ee4555a0e36e9ea2a39ce0e146a384db71d463f9319a666acd|1",
      "line": 303,
      "marker": null,
      "path": "nexus/config/loader.py",
      "scope": "_load_from_toml"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/config/loader.py|_load_from_json|ca9e1618a6852545370deacbaedec1c12afec14659e76a0475399ea623089938|1",
      "line": 354,
      "marker": null,
      "path": "nexus/config/loader.py",
      "scope": "_load_from_json"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/config/settings_models.py|_failing_log_placeholders|2f69eda87500e545cae9ed316f54f971a68fb6e0eb5d4d33f88f670a94c33500|1",
      "line": 627,
      "marker": null,
      "path": "nexus/config/settings_models.py",
      "scope": "_failing_log_placeholders"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/config/settings_models.py|RuntimeLogsSettings._validate_format|57f70c607774f0b8eb776c899daff1e925edabe74d6cf933580c61750f8b8f9d|1",
      "line": 705,
      "marker": null,
      "path": "nexus/config/settings_models.py",
      "scope": "RuntimeLogsSettings._validate_format"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/config/settings_models.py|RuntimeLogsSettings._validate_format|f3b6501bf96ef3c6897298119f13eaf2901462ba9bb4e785065ced3db55cafad|1",
      "line": 713,
      "marker": null,
      "path": "nexus/config/settings_models.py",
      "scope": "RuntimeLogsSettings._validate_format"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/config/settings_models.py|RuntimeGatewaySettings._validate_cors_allowed_origins|606eede5d683c75262a26aa82a58f976f8abf95321e608ddfe6ed160139b619c|1",
      "line": 968,
      "marker": null,
      "path": "nexus/config/settings_models.py",
      "scope": "RuntimeGatewaySettings._validate_cors_allowed_origins"
    },
    {
      "ast_exempt": true,
      "caught_type": "(ValueError, ZoneInfoNotFoundError)",
      "identity": "nexus/config/settings_models.py|APIDatabaseSettings.validate_session_timezone|275b033110a805a00cca380596fea200583494681ab145b151cfe6129576bee9|1",
      "line": 3898,
      "marker": null,
      "path": "nexus/config/settings_models.py",
      "scope": "APIDatabaseSettings.validate_session_timezone"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/config/story_model.py|resolve_seat|d3735ae5708f2a921c4bc8d40b363a4b4d20516fa20e7d54dd5a03a1b14783c1|1",
      "line": 196,
      "marker": null,
      "path": "nexus/config/story_model.py",
      "scope": "resolve_seat"
    },
    {
      "ast_exempt": true,
      "caught_type": "(psycopg2.OperationalError, psycopg2.InterfaceError)",
      "identity": "nexus/database.py|commit_transaction|7a792687be0fb3c6b952deec535480fd6479f0668f136659de91b9a15cf4f2dd|1",
      "line": 55,
      "marker": null,
      "path": "nexus/database.py",
      "scope": "commit_transaction"
    },
    {
      "ast_exempt": true,
      "caught_type": "BaseException",
      "identity": "nexus/database.py|transaction|e6aea7b1899ba7dc21e46e423c181d7272499497f2eb900225a4e229c4bf5deb|1",
      "line": 65,
      "marker": null,
      "path": "nexus/database.py",
      "scope": "transaction"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/database.py|transaction|3efc3c8a86f2c187b7cfc47bd0cbeaa2e1d9be38af135ca12d4efa14c5cb3adb|1",
      "line": 68,
      "marker": null,
      "path": "nexus/database.py",
      "scope": "transaction"
    },
    {
      "ast_exempt": true,
      "caught_type": "BaseException",
      "identity": "nexus/database.py|maintenance_connection|84e3e5979720b2985591e7674edb9efffdd2eb8da1be4ffdaa4cfaed0c7d106d|1",
      "line": 219,
      "marker": null,
      "path": "nexus/database.py",
      "scope": "maintenance_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError, ValidationError)",
      "identity": "nexus/interactions/evaluator.py|evaluate_authorizations|1a1bcb2ff345eec68683e08dd5246517c06251e7fca49be8705ae5dd4a6106fb|1",
      "line": 106,
      "marker": null,
      "path": "nexus/interactions/evaluator.py",
      "scope": "evaluate_authorizations"
    },
    {
      "ast_exempt": false,
      "caught_type": "_CreationCommandAlreadyRecorded",
      "identity": "nexus/interactions/service.py|InteractionService.propose|cd6565553b142b1d3b19a6397c3566f1a0704efa0a01ddd2676a3efafe794eca|1",
      "line": 275,
      "marker": null,
      "path": "nexus/interactions/service.py",
      "scope": "InteractionService.propose"
    },
    {
      "ast_exempt": false,
      "caught_type": "InteractionAuthorizationDenied",
      "identity": "nexus/interactions/service.py|InteractionService.evaluate|661d2018f76cca66835a144294eb2cafd8d77c03fe54ac1848a533a747a0dc2c|1",
      "line": 504,
      "marker": null,
      "path": "nexus/interactions/service.py",
      "scope": "InteractionService.evaluate"
    },
    {
      "ast_exempt": false,
      "caught_type": "InteractionAuthorizationDenied",
      "identity": "nexus/interactions/service.py|InteractionService._authorization_decision|661d2018f76cca66835a144294eb2cafd8d77c03fe54ac1848a533a747a0dc2c|1",
      "line": 1324,
      "marker": null,
      "path": "nexus/interactions/service.py",
      "scope": "InteractionService._authorization_decision"
    },
    {
      "ast_exempt": true,
      "caught_type": "SQLAlchemyError",
      "identity": "nexus/interactions/service.py|InteractionService._authorization_decision|1dde0cef7276581455a099394d2c039bb2862eea9d4a976be16f557863c34793|1",
      "line": 1326,
      "marker": null,
      "path": "nexus/interactions/service.py",
      "scope": "InteractionService._authorization_decision"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/interactions/service.py|InteractionService._require_fresh_anchor_under_lock|a89f4797eb237d9a8d6ee7a9ff5c60820ceb16c3062405d6d19f266e04f37cfa|1",
      "line": 1359,
      "marker": null,
      "path": "nexus/interactions/service.py",
      "scope": "InteractionService._require_fresh_anchor_under_lock"
    },
    {
      "ast_exempt": true,
      "caught_type": "(TypeError, ValueError, ValidationError)",
      "identity": "nexus/interactions/service.py|InteractionService._validated_policy|90cce4eeeefb80856ee1b45f69628f76fdde7e4f731ff810b705d115689c80d0|1",
      "line": 1518,
      "marker": null,
      "path": "nexus/interactions/service.py",
      "scope": "InteractionService._validated_policy"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/jobs/compaction.py|drain_compaction|3327c8e76f39c32c9f8e764e05e48ce196dc14117b836b9a955b19c8faf4f3fc|1",
      "line": 117,
      "marker": null,
      "path": "nexus/jobs/compaction.py",
      "scope": "drain_compaction"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/jobs/narrative_jobs.py|drain_job|68e1de182951627839ea6a730c106d4a0bff98f9b267cc1745afc7ea6a0bbaf3|1",
      "line": 101,
      "marker": null,
      "path": "nexus/jobs/narrative_jobs.py",
      "scope": "drain_job"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/jobs/scheduler.py|SlotScheduler._heartbeats|ff735bd837fd24dd95b650903b9dc176ba157bee8a409e09a1110ebefa1657d3|1",
      "line": 415,
      "marker": null,
      "path": "nexus/jobs/scheduler.py",
      "scope": "SlotScheduler._heartbeats"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.errors.ReadOnlySqlTransaction",
      "identity": "nexus/jobs/scheduler.py|SlotScheduler.run_pass|d28b04e4b628b25458999ab792aacf6d83e290073c3e545e85ad307c5ff32d1c|1",
      "line": 465,
      "marker": null,
      "path": "nexus/jobs/scheduler.py",
      "scope": "SlotScheduler.run_pass"
    },
    {
      "ast_exempt": false,
      "caught_type": "SchedulerStopped",
      "identity": "nexus/jobs/scheduler.py|SlotScheduler.run_pass|67911c2ea399b582829b66787434b75759d8170914e7fc83fa956d648251ac05|1",
      "line": 468,
      "marker": null,
      "path": "nexus/jobs/scheduler.py",
      "scope": "SlotScheduler.run_pass"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/jobs/scheduler.py|SlotScheduler.run_pass|94a20d49c6eb91bdd3ab1e3f659fdbeb9f85ed35635c3308ffc067e76902f7c1|1",
      "line": 472,
      "marker": null,
      "path": "nexus/jobs/scheduler.py",
      "scope": "SlotScheduler.run_pass"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.errors.ReadOnlySqlTransaction",
      "identity": "nexus/jobs/scheduler.py|SlotScheduler.run_pass|d28b04e4b628b25458999ab792aacf6d83e290073c3e545e85ad307c5ff32d1c|2",
      "line": 480,
      "marker": null,
      "path": "nexus/jobs/scheduler.py",
      "scope": "SlotScheduler.run_pass"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/jobs/scheduler.py|SlotScheduler.start|4377a7350ba88cc6a1e6fc413859cb96e889600daf478640883072bb6fe18904|1",
      "line": 674,
      "marker": null,
      "path": "nexus/jobs/scheduler.py",
      "scope": "SlotScheduler.start"
    },
    {
      "ast_exempt": false,
      "caught_type": "(Exception, SchedulerStopped)",
      "identity": "nexus/jobs/scheduler.py|SlotScheduler._run|da576334bc3e94c2761a14b3904953546556d7a0b95b55a93a6bf79628a9547b|1",
      "line": 709,
      "marker": null,
      "path": "nexus/jobs/scheduler.py",
      "scope": "SlotScheduler._run"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/jobs/scheduler.py|SlotScheduler._run|ffc52434d9c5d319904bab928d3249e752477f552cde10eb6baaef480e319e49|1",
      "line": 720,
      "marker": null,
      "path": "nexus/jobs/scheduler.py",
      "scope": "SlotScheduler._run"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/jobs/scheduler.py|SlotScheduler.stop|ffc52434d9c5d319904bab928d3249e752477f552cde10eb6baaef480e319e49|1",
      "line": 737,
      "marker": null,
      "path": "nexus/jobs/scheduler.py",
      "scope": "SlotScheduler.stop"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/memory/context_state.py|memory_identity|8dca1ca5004730bc25e16f3c74797730000ffa88e7fa4386c72d53f9d32590dd|1",
      "line": 234,
      "marker": null,
      "path": "nexus/memory/context_state.py",
      "scope": "memory_identity"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/memory/context_state.py|memory_identity|8dca1ca5004730bc25e16f3c74797730000ffa88e7fa4386c72d53f9d32590dd|2",
      "line": 244,
      "marker": null,
      "path": "nexus/memory/context_state.py",
      "scope": "memory_identity"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/memory/entity_detector.py|HighSpecificityEntityDetector._load_entities|c94df56b5546797a9a154107bccab8c4016c4e62c24acf6329da7b458a537537|1",
      "line": 92,
      "marker": null,
      "path": "nexus/memory/entity_detector.py",
      "scope": "HighSpecificityEntityDetector._load_entities"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/memory/incremental.py|IncrementalRetriever.expand_warm_slice|cc7890073470479baff6122b79b6d7f3ac97ab1fb85f6d951c43a559d925d757|1",
      "line": 190,
      "marker": null,
      "path": "nexus/memory/incremental.py",
      "scope": "IncrementalRetriever.expand_warm_slice"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "nexus/memory/manager.py|<module>|c8f6091e776e72d6058851689aba75824ac00424d23d5529c61ae2bf4498dd01|1",
      "line": 53,
      "marker": null,
      "path": "nexus/memory/manager.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/memory/manager.py|ContextMemoryManager.export_pass2_baseline|3f3d05dc18876ea3992035a25ec4f48c7b440584924ab1543728d5c79990e7da|1",
      "line": 589,
      "marker": null,
      "path": "nexus/memory/manager.py",
      "scope": "ContextMemoryManager.export_pass2_baseline"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeError",
      "identity": "nexus/memory/manager.py|ContextMemoryManager._initialize_entity_maps|32a89207e753649daef5c3cd2d258e0974e6b81f6e1d1d359c4152f211d3b964|1",
      "line": 1300,
      "marker": null,
      "path": "nexus/memory/manager.py",
      "scope": "ContextMemoryManager._initialize_entity_maps"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/memory/manager.py|ContextMemoryManager._initialize_entity_maps|87db5601ec4a607d91312f6b0ad24174699fba9009117910292f09abc29382aa|1",
      "line": 1302,
      "marker": null,
      "path": "nexus/memory/manager.py",
      "scope": "ContextMemoryManager._initialize_entity_maps"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "nexus/memory/retrieval_coverage.py|coerce_chunk_id|8dca1ca5004730bc25e16f3c74797730000ffa88e7fa4386c72d53f9d32590dd|1",
      "line": 79,
      "marker": null,
      "path": "nexus/memory/retrieval_coverage.py",
      "scope": "coerce_chunk_id"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/runtime/contract.py|gateway_port_override|0541a10391963b55748c97035d480dffeae31ed723c3ee35b998ebb7ac07b15b|1",
      "line": 62,
      "marker": null,
      "path": "nexus/runtime/contract.py",
      "scope": "gateway_port_override"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/runtime/home_plan.py|_blocker|c7a0a01b51f7db73f7fce5bdf9fb59b74451bcb95dbe524f41726c526aa69985|1",
      "line": 221,
      "marker": null,
      "path": "nexus/runtime/home_plan.py",
      "scope": "_blocker"
    },
    {
      "ast_exempt": false,
      "caught_type": "PackageNotFoundError",
      "identity": "nexus/runtime/readiness.py|runtime_version|793a0fc9d8347cfa976924c29a280697ed0a947e3a9c26d108d3f2bc17a6518c|1",
      "line": 226,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "runtime_version"
    },
    {
      "ast_exempt": false,
      "caught_type": "RuntimeHomeError",
      "identity": "nexus/runtime/readiness.py|_check_config|574c8701a382c6e8e59a99408e47a9b4640fbb0b98e29a4d9eb5187a1503f5da|1",
      "line": 246,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_config"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/runtime/readiness.py|_check_config|28bfe09f6ec466bde7432485fc0fceb0e751175264e0791259a6f99845e1365d|1",
      "line": 256,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_config"
    },
    {
      "ast_exempt": false,
      "caught_type": "(OSError, ValueError, RuntimeHomeError)",
      "identity": "nexus/runtime/readiness.py|_check_config|664ad390163f5c9d0194cd902fdd874b08b06e1cc9895ff381c4abe6ffa07f34|1",
      "line": 262,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_config"
    },
    {
      "ast_exempt": true,
      "caught_type": "BaseException",
      "identity": "nexus/runtime/readiness.py|read_only_connection|84e3e5979720b2985591e7674edb9efffdd2eb8da1be4ffdaa4cfaed0c7d106d|1",
      "line": 293,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "read_only_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "SecretStoreAccessError",
      "identity": "nexus/runtime/readiness.py|_check_postgres_reachable|0c907a46627f2acf642fd27a6f4c9dc4b48d319726b288a1a32775727a29c9fc|1",
      "line": 381,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_postgres_reachable"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValueError, RuntimeError, MissingSecretError)",
      "identity": "nexus/runtime/readiness.py|_check_postgres_reachable|39ed7ca25008a3eb8bf52644777c5a6a411b7e41edcb69d45be71b0818c99b06|1",
      "line": 383,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_postgres_reachable"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/runtime/readiness.py|_check_postgres_reachable|1c4a1ba5c02b7bd8b25cc0e0e3fe62a38286f89677d6010bfc7acda4801d7b22|1",
      "line": 395,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_postgres_reachable"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/runtime/readiness.py|_check_postgres_extensions|4bb81b1a8c81e1f925d6349194698c661f6639fffdcd875f390ade667bd3312b|1",
      "line": 413,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_postgres_extensions"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/runtime/readiness.py|_check_template_present|4bb81b1a8c81e1f925d6349194698c661f6639fffdcd875f390ade667bd3312b|1",
      "line": 441,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_template_present"
    },
    {
      "ast_exempt": false,
      "caught_type": "RuntimeError",
      "identity": "nexus/runtime/readiness.py|_discovered_migrations|c9a608a76b45f94bcda51ddef704b86ae37de4170bb5026121e15d71147f2a81|1",
      "line": 463,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_discovered_migrations"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/runtime/readiness.py|_check_template_migrations|4bb81b1a8c81e1f925d6349194698c661f6639fffdcd875f390ade667bd3312b|1",
      "line": 478,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_template_migrations"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/runtime/readiness.py|_check_slot_migrations|4bb81b1a8c81e1f925d6349194698c661f6639fffdcd875f390ade667bd3312b|1",
      "line": 525,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_slot_migrations"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/runtime/readiness.py|idf_analyzer_outcome|4bb81b1a8c81e1f925d6349194698c661f6639fffdcd875f390ade667bd3312b|1",
      "line": 706,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "idf_analyzer_outcome"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "nexus/runtime/readiness.py|slot_idf_outcome|4bb81b1a8c81e1f925d6349194698c661f6639fffdcd875f390ade667bd3312b|1",
      "line": 785,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "slot_idf_outcome"
    },
    {
      "ast_exempt": false,
      "caught_type": "SeatRequirementError",
      "identity": "nexus/runtime/readiness.py|_check_seat_secrets|499d590d1ae73afe258744914884d2e95f074a7d02fc613173ed0060e2d69cf0|1",
      "line": 872,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_seat_secrets"
    },
    {
      "ast_exempt": false,
      "caught_type": "MissingSecretError",
      "identity": "nexus/runtime/readiness.py|_check_seat_secrets|29e24a35884d615dd999a21bccdb182bc07e9b4126185313972e57ec96b53670|1",
      "line": 887,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_seat_secrets"
    },
    {
      "ast_exempt": false,
      "caught_type": "SecretStoreAccessError",
      "identity": "nexus/runtime/readiness.py|_check_seat_secrets|c2683cd32d82ffe4d3aed512bb71b13d0cd4382a23052a3b10db257d6e44dd65|1",
      "line": 889,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_seat_secrets"
    },
    {
      "ast_exempt": false,
      "caught_type": "RuntimeError_",
      "identity": "nexus/runtime/readiness.py|_check_gateway_reachable|1d351b83d4ab546ade49f6a458abdd950f00de7a80a7185a71dd3240fcf0e07b|1",
      "line": 950,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_gateway_reachable"
    },
    {
      "ast_exempt": false,
      "caught_type": "SecretStoreAccessError",
      "identity": "nexus/runtime/readiness.py|_check_gateway_reachable|0c907a46627f2acf642fd27a6f4c9dc4b48d319726b288a1a32775727a29c9fc|1",
      "line": 961,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_gateway_reachable"
    },
    {
      "ast_exempt": false,
      "caught_type": "MissingSecretError",
      "identity": "nexus/runtime/readiness.py|_check_gateway_reachable|ade3b8dbdfba56ab627aa1898837b8586148c65600a91f2e79b06aabcc2a5b05|1",
      "line": 963,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_gateway_reachable"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/runtime/readiness.py|_check_gateway_reachable|4b51b2d06f5efb148412beaee95682923dbd38b0da62827719819d6280ee212d|1",
      "line": 969,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_gateway_reachable"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.RequestException",
      "identity": "nexus/runtime/readiness.py|_check_gateway_reachable|6bb38996c3f6719a6c3adff635f0eb1365cdc1b35c971f64046dd14c856ec581|1",
      "line": 983,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_gateway_reachable"
    },
    {
      "ast_exempt": false,
      "caught_type": "subprocess.TimeoutExpired",
      "identity": "nexus/runtime/readiness.py|_check_reachability_gate|bae9282b226b5147c73a6b6d59ecbfc0ea470ac0bb8ab0d1d8baf122f1c0ccae|1",
      "line": 1040,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_reachability_gate"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "nexus/runtime/readiness.py|_check_reachability_gate|86a4d028e0a67b476e1e5c7d6602475052566eecf236b77b68802820d31fdad3|1",
      "line": 1047,
      "marker": null,
      "path": "nexus/runtime/readiness.py",
      "scope": "_check_reachability_gate"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/runtime/remote_auth.py|_normalized_origin|489da708bbcbc410fb31ed5dfbce85104c4aed252b3ba734ad9c81d8997c1e14|1",
      "line": 47,
      "marker": null,
      "path": "nexus/runtime/remote_auth.py",
      "scope": "_normalized_origin"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/runtime/remote_auth.py|_credential_transport_is_safe|7d0e8d9691f890c01670266608ee21503804bacb5b6a21234b1f5e71c861d66f|1",
      "line": 72,
      "marker": null,
      "path": "nexus/runtime/remote_auth.py",
      "scope": "_credential_transport_is_safe"
    },
    {
      "ast_exempt": false,
      "caught_type": "ProcessLookupError",
      "identity": "nexus/runtime/supervisor.py|_pid_alive|34164cab0e2fff68bfc4f15b988750df1f90ec9726fb2eb1137d839acb70234d|1",
      "line": 81,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "_pid_alive"
    },
    {
      "ast_exempt": false,
      "caught_type": "PermissionError",
      "identity": "nexus/runtime/supervisor.py|_pid_alive|14ffbc89fb4fa254e4dbfb3ab7758ecee940f086f7b5f16aa32cafd94f71cb35|1",
      "line": 83,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "_pid_alive"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ProcessLookupError, PermissionError)",
      "identity": "nexus/runtime/supervisor.py|_signal_pid|13cfdf08740fd2c5858ab49a4851814d8cef276601498c61f91cdb394db46ae1|1",
      "line": 98,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "_signal_pid"
    },
    {
      "ast_exempt": false,
      "caught_type": "(OSError, subprocess.SubprocessError)",
      "identity": "nexus/runtime/supervisor.py|_describe_port_occupant|2efed055b3aa9bcc85195f9ca6fc0c59d0d9ee1be741d0bcfc1fba930b82dbb9|1",
      "line": 143,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "_describe_port_occupant"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeHomeError",
      "identity": "nexus/runtime/supervisor.py|Supervisor.__init__|ae7963ab155fe6eadd13d372b8fc1f86577c605a684d2aa802a448ab841aa4d9|1",
      "line": 357,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "Supervisor.__init__"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/runtime/supervisor.py|Supervisor.__init__|5c2db7ed5bdf9a77e3c535b58db81a56c977dc1d1c82380a60e4df49d6b7c751|1",
      "line": 370,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "Supervisor.__init__"
    },
    {
      "ast_exempt": true,
      "caught_type": "RuntimeHomeError",
      "identity": "nexus/runtime/supervisor.py|Supervisor.from_config|ae7963ab155fe6eadd13d372b8fc1f86577c605a684d2aa802a448ab841aa4d9|1",
      "line": 404,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "Supervisor.from_config"
    },
    {
      "ast_exempt": false,
      "caught_type": "(OSError, json.JSONDecodeError)",
      "identity": "nexus/runtime/supervisor.py|Supervisor._sibling_owned_by_default|8759c9b5cfdf65301f6c6609db6b6aaf4f12c3fcfdcffaad790ce04c28f4fa24|1",
      "line": 492,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "Supervisor._sibling_owned_by_default"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.RequestException",
      "identity": "nexus/runtime/supervisor.py|Supervisor._await_healthy|c9f9ac20975d7f0d1f160e1c2fd58fe8b15c207fb952ed8690acd3f532787ef8|1",
      "line": 599,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "Supervisor._await_healthy"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/runtime/supervisor.py|Supervisor.up|5ee7553106852b13c5fd23d855188f0e54ab2f3ef704edee5882f5ee05ebd104|1",
      "line": 733,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "Supervisor.up"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.RequestException",
      "identity": "nexus/runtime/supervisor.py|Supervisor._probe|af6187141a8050060c36ded3287173220fffaf421b07f8046cfbb2dfe1727b29|1",
      "line": 796,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "Supervisor._probe"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.RequestException",
      "identity": "nexus/runtime/supervisor.py|Supervisor._fetch_runtime_status|98eea3eb70678c807f36e0408054e1dfcd53e909ac087d55b0db163d122d1ba6|1",
      "line": 916,
      "marker": null,
      "path": "nexus/runtime/supervisor.py",
      "scope": "Supervisor._fetch_runtime_status"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/telemetry/prompt_window.py|local_text_counter|4abf188110874c4dc575016153be0c7bdcb67adfc1b0c2507db2176e29fb4607|1",
      "line": 135,
      "marker": null,
      "path": "nexus/telemetry/prompt_window.py",
      "scope": "local_text_counter"
    },
    {
      "ast_exempt": true,
      "caught_type": "WireContractViolation",
      "identity": "nexus/telemetry/usage.py|validation_attempt|5565acc7d463b9b6540d7d39a98948924c461214b6a56c39d2b8dd764c1adc38|1",
      "line": 51,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "validation_attempt"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/telemetry/usage.py|_parse_utc_timestamp|2aa40b507df991fdf14e7cee7596b7d22a658fa33af875574e2e146610350473|1",
      "line": 88,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "_parse_utc_timestamp"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/telemetry/usage.py|current_usage_context|cedb88ee90d8a45e6357a72e91c0f70583aaebd4f60f3da1f97c28aca2564215|1",
      "line": 227,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "current_usage_context"
    },
    {
      "ast_exempt": true,
      "caught_type": "UsageWriteError",
      "identity": "nexus/telemetry/usage.py|record_usage_event|f55ee3025617e492bd392fbaa1f2c7dff7d189b753813923fb6821ede3392e67|1",
      "line": 274,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "record_usage_event"
    },
    {
      "ast_exempt": true,
      "caught_type": "OSError",
      "identity": "nexus/telemetry/usage.py|record_usage_event|e5f933dcedb0d88597374e9c75f0114e2d99f7e0a2644d65ed2a2568675272b3|1",
      "line": 276,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "record_usage_event"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "nexus/telemetry/usage.py|validate_usage_day|092adcd96ae9898af91f5f3d35b00c3c339939ed039617d9318e156069747f70|1",
      "line": 404,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "validate_usage_day"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/telemetry/usage.py|summarize_usage|950321e97ec343d70d528ae8ca476628ae83ea2aad65ca02a770ed1b5c6f1f1a|1",
      "line": 434,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "summarize_usage"
    },
    {
      "ast_exempt": true,
      "caught_type": "UsageReadError",
      "identity": "nexus/telemetry/usage.py|summarize_usage|85673c1e393d4acf3317ccf0eb3badfde609f27d08ea3370cb9afccdc420e89a|1",
      "line": 446,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "summarize_usage"
    },
    {
      "ast_exempt": true,
      "caught_type": "OSError",
      "identity": "nexus/telemetry/usage.py|summarize_usage|b26ad5ab53e5a79a1536957223ec6adcd673ec89cf6b97cf2d062aadda1e1819|1",
      "line": 448,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "summarize_usage"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/telemetry/usage.py|_record_request_estimate|67efc8785c6e97056943c2754990e676e69bc1dff63095d6aa0c4c14e1473276|1",
      "line": 577,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "_record_request_estimate"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "nexus/telemetry/usage.py|record_pydantic_ai_result|67efc8785c6e97056943c2754990e676e69bc1dff63095d6aa0c4c14e1473276|1",
      "line": 790,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "record_pydantic_ai_result"
    },
    {
      "ast_exempt": true,
      "caught_type": "OSError",
      "identity": "nexus/telemetry/usage.py|record_prompt_window|857eb08662db92432f8be99354948400a16e1ddaec5aba52fc79a4442c5ce8a6|1",
      "line": 819,
      "marker": null,
      "path": "nexus/telemetry/usage.py",
      "scope": "record_prompt_window"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "nexus/util/gguf_inspect.py|_quantization_name|fa5c3c904ad1340ac9f3ce258e673f21f20711b525336ad42bd0e33610d11010|1",
      "line": 146,
      "marker": null,
      "path": "nexus/util/gguf_inspect.py",
      "scope": "_quantization_name"
    },
    {
      "ast_exempt": false,
      "caught_type": "OSError",
      "identity": "nexus/util/gguf_inspect.py|inspect_gguf|a4c8f1fe6b4a25dd436bfe4b3de6c439dec776c6cbc4c9a3dead5629059adb04|1",
      "line": 215,
      "marker": null,
      "path": "nexus/util/gguf_inspect.py",
      "scope": "inspect_gguf"
    },
    {
      "ast_exempt": false,
      "caught_type": "OSError",
      "identity": "nexus/util/gguf_inspect.py|inspect_gguf|a4c8f1fe6b4a25dd436bfe4b3de6c439dec776c6cbc4c9a3dead5629059adb04|2",
      "line": 220,
      "marker": null,
      "path": "nexus/util/gguf_inspect.py",
      "scope": "inspect_gguf"
    },
    {
      "ast_exempt": false,
      "caught_type": "(_HeaderError, OSError, struct.error)",
      "identity": "nexus/util/gguf_inspect.py|inspect_gguf|c27282ffb109b8ecbfcaabd22742e81ee278cd3f14d58885ed7ea91f2404e28b|1",
      "line": 226,
      "marker": null,
      "path": "nexus/util/gguf_inspect.py",
      "scope": "inspect_gguf"
    },
    {
      "ast_exempt": true,
      "caught_type": "FileNotFoundError",
      "identity": "nexus/util/secret_manager.py|MacOSKeychainBackend.read|bdb15b9c75f4298f6deb6d352d9a6950c3a8bbe0f59bddfd732f2472c0844f4c|1",
      "line": 219,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "MacOSKeychainBackend.read"
    },
    {
      "ast_exempt": false,
      "caught_type": "subprocess.CalledProcessError",
      "identity": "nexus/util/secret_manager.py|MacOSKeychainBackend.read|fe569e8a9b7556b1461a3520c7c6638b7c488d71fc5e264e94b96db415023896|1",
      "line": 221,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "MacOSKeychainBackend.read"
    },
    {
      "ast_exempt": true,
      "caught_type": "subprocess.TimeoutExpired",
      "identity": "nexus/util/secret_manager.py|MacOSKeychainBackend.read|24b8fb662fa3e33545a77c07f9eec62ccd1cfb75bb9077e036c528115125b9b4|1",
      "line": 225,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "MacOSKeychainBackend.read"
    },
    {
      "ast_exempt": true,
      "caught_type": "subprocess.TimeoutExpired",
      "identity": "nexus/util/secret_manager.py|MacOSKeychainBackend.write|2e4302dd5da529213bde535bc57bed32cc01efe68eec0a967470bb2a86bd566d|1",
      "line": 252,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "MacOSKeychainBackend.write"
    },
    {
      "ast_exempt": true,
      "caught_type": "subprocess.CalledProcessError",
      "identity": "nexus/util/secret_manager.py|MacOSKeychainBackend.write|6d2976fd940e637a47dcbcd3ced3a3b29a3b47201c97b07f56dad9195ddb7387|1",
      "line": 259,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "MacOSKeychainBackend.write"
    },
    {
      "ast_exempt": true,
      "caught_type": "OSError",
      "identity": "nexus/util/secret_manager.py|MacOSKeychainBackend.write|732968b60e8b9d8e56b8f3675d85e2e03cbf6b6b2b1bf0a7917e1236da3f998e|1",
      "line": 267,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "MacOSKeychainBackend.write"
    },
    {
      "ast_exempt": true,
      "caught_type": "subprocess.TimeoutExpired",
      "identity": "nexus/util/secret_manager.py|MacOSKeychainBackend.delete|53103b13fac76a30b10e7971dc7564fd14af593e0faad8662077d493ee299819|1",
      "line": 280,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "MacOSKeychainBackend.delete"
    },
    {
      "ast_exempt": true,
      "caught_type": "OSError",
      "identity": "nexus/util/secret_manager.py|MacOSKeychainBackend.delete|a4c33d32042424eb7095a61fea9e1a503fe57ee3a127ad74a6c322af6bf2b572|1",
      "line": 285,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "MacOSKeychainBackend.delete"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "nexus/util/secret_manager.py|KeyringLibraryBackend.read|ea2497964b945c80a49192f9ff1d3efc41b08215a434492b8dc86c2c893fa585|1",
      "line": 314,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "KeyringLibraryBackend.read"
    },
    {
      "ast_exempt": false,
      "caught_type": "keyring.errors.KeyringError",
      "identity": "nexus/util/secret_manager.py|KeyringLibraryBackend.read|ab496a0c4488fc7dc50fd8c13a49cba66ce7d7163a829fd315f01b0b743b3a80|1",
      "line": 318,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "KeyringLibraryBackend.read"
    },
    {
      "ast_exempt": true,
      "caught_type": "ImportError",
      "identity": "nexus/util/secret_manager.py|KeyringLibraryBackend.write|206a0dc346e5c91d0038f3affeb6e425596002a6f65ff1603d35ed274045ca4d|1",
      "line": 325,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "KeyringLibraryBackend.write"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/util/secret_manager.py|KeyringLibraryBackend.write|97e480b97cd96c06853fb7ed917466211d4a31d19942a74fd807baeb4c098541|1",
      "line": 332,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "KeyringLibraryBackend.write"
    },
    {
      "ast_exempt": true,
      "caught_type": "ImportError",
      "identity": "nexus/util/secret_manager.py|KeyringLibraryBackend.delete|c3877425cca7e85b1323748dc5cb82eb6f3af727cd4a91efa853412ed04ed36c|1",
      "line": 343,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "KeyringLibraryBackend.delete"
    },
    {
      "ast_exempt": false,
      "caught_type": "keyring.errors.PasswordDeleteError",
      "identity": "nexus/util/secret_manager.py|KeyringLibraryBackend.delete|f2044f069c1daea0bcbb236b0c2f49d942ad33320213b8dc3933f72709efed94|1",
      "line": 350,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "KeyringLibraryBackend.delete"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/util/secret_manager.py|KeyringLibraryBackend.delete|5f7a0921e6375c39208226b5ef493ad073fc9f578171f850bbcec496b388f31f|1",
      "line": 355,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "KeyringLibraryBackend.delete"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "nexus/util/secret_manager.py|KeyringLibraryBackend.delete|5f7a0921e6375c39208226b5ef493ad073fc9f578171f850bbcec496b388f31f|2",
      "line": 365,
      "marker": null,
      "path": "nexus/util/secret_manager.py",
      "scope": "KeyringLibraryBackend.delete"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/api_anthropic.py|<module>|eab7b4aec8946a954d54cd668c5b6209ab6d3586df99d01292b2545dba445f0e|1",
      "line": 65,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/api_anthropic.py|<module>|e08747dc2d4050cc9f744f179e40c9e35347508413791cb3b276a3f88d620c0f|1",
      "line": 71,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/api_anthropic.py|<module>|a9dad04b35b4bea4a298019a7b51364dffde56195f4d71baa83e3094b87d473d|1",
      "line": 106,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/api_anthropic.py|AnthropicProvider.get_completion|99d47782a71fabecd586a55811a12f8760072b90fd429ceefc7fe2321fd0f876|1",
      "line": 493,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider.get_completion"
    },
    {
      "ast_exempt": false,
      "caught_type": "RuntimeError",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._raise_if_running_loop|312c903db5940cfe7d93b91a7f84d4aee7e1bdf7497d11fcf5c2f289168ee2c7|1",
      "line": 610,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._raise_if_running_loop"
    },
    {
      "ast_exempt": true,
      "caught_type": "WireContractViolation",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_native_sync|dbbe12b88dc84dcf190857b9678722263d6a6749660d1244fc40c3aa8b10c672|1",
      "line": 740,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._get_structured_completion_native_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "ModelRetry",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_native_sync|b579fbe35541eef974979bcc8ee3044c903ee09048f42eca3fdeb57800748287|1",
      "line": 746,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._get_structured_completion_native_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValidationError, json.JSONDecodeError, ValueError)",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_native_sync|4f6aee874518d7b497c8121263bd00be2622b97d6150540559f7fb6fe422b552|1",
      "line": 757,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._get_structured_completion_native_sync"
    },
    {
      "ast_exempt": true,
      "caught_type": "WireContractViolation",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_tool_envelope_sync|99180bca38548b03cc3d7ff4f30b44dc662d982cfe7181151af763f141b12942|1",
      "line": 840,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._get_structured_completion_tool_envelope_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "ModelRetry",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_tool_envelope_sync|32200c3c3fd5336910000f1cc344e3db3f1f2a1f249e076c4fe3e341f7078312|1",
      "line": 846,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._get_structured_completion_tool_envelope_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValidationError, json.JSONDecodeError, ValueError)",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_tool_envelope_sync|bc244d791756853f3e74618648e36e6201cf5a9b794e4957d423b16cf6af1c83|1",
      "line": 857,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._get_structured_completion_tool_envelope_sync"
    },
    {
      "ast_exempt": true,
      "caught_type": "WireContractViolation",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_prompted_sync|036ce906f670b91dfc035e9ceb0420c4937e5be76fc3a03c2f691eceeb59dded|1",
      "line": 936,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._get_structured_completion_prompted_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "ModelRetry",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_prompted_sync|5232a12fde564bdeaa332a92ecd6206c668145821c73cda37cbb1135dcd9f5fa|1",
      "line": 942,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._get_structured_completion_prompted_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValidationError, json.JSONDecodeError, ValueError)",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_prompted_sync|ef6a33f673935b9a879846bf2a53c0eeea43e2d8b61af8f0fa4309149e7e0430|1",
      "line": 953,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._get_structured_completion_prompted_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValidationError, json.JSONDecodeError, ValueError)",
      "identity": "scripts/api_anthropic.py|AnthropicProvider._extract_prompted_parsed_output|48afe6ce46a0af97879a8c2c78ac3d19d756e0a628041cf85ab91464b96b7ce9|1",
      "line": 1142,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "AnthropicProvider._extract_prompted_parsed_output"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/api_anthropic.py|setup_abort_handler|74fee6afe2a86ffa69f4959240e4a22c16d47c358be835d8e5bae84c31db8591|1",
      "line": 1449,
      "marker": null,
      "path": "scripts/api_anthropic.py",
      "scope": "setup_abort_handler"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/api_openai.py|<module>|eab7b4aec8946a954d54cd668c5b6209ab6d3586df99d01292b2545dba445f0e|1",
      "line": 69,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/api_openai.py|<module>|342ba95f67bf2c7b0a17697da083ca2df807fb09403a67d5182115fad7a5e332|1",
      "line": 75,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/api_openai.py|<module>|a9dad04b35b4bea4a298019a7b51364dffde56195f4d71baa83e3094b87d473d|1",
      "line": 114,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "scripts/api_openai.py|OpenAIProvider.initialize|4dd19cbc95843d5f51eaee2d28401a9b897ae2879543025261c1e105d3b7a072|1",
      "line": 358,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "OpenAIProvider.initialize"
    },
    {
      "ast_exempt": false,
      "caught_type": "RuntimeError",
      "identity": "scripts/api_openai.py|OpenAIProvider._raise_if_running_loop|312c903db5940cfe7d93b91a7f84d4aee7e1bdf7497d11fcf5c2f289168ee2c7|1",
      "line": 500,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "OpenAIProvider._raise_if_running_loop"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/api_openai.py|OpenAIProvider._get_structured_completion_native_sync|c4fb34d65d0ec04e1a23d465012dc2acfd2fd1482d61109ab896fb1780bb390e|1",
      "line": 587,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "OpenAIProvider._get_structured_completion_native_sync"
    },
    {
      "ast_exempt": true,
      "caught_type": "WireContractViolation",
      "identity": "scripts/api_openai.py|OpenAIProvider._get_structured_completion_native_sync|1d7c0160910075d12d049877a2e082b2612f00163ecfefe88d9c7f5e643b7e16|1",
      "line": 620,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "OpenAIProvider._get_structured_completion_native_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "ModelRetry",
      "identity": "scripts/api_openai.py|OpenAIProvider._get_structured_completion_native_sync|6a5ba186f6ff069c0c2104b41a094105e1d61b032840d6d08312559d21c38529|1",
      "line": 626,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "OpenAIProvider._get_structured_completion_native_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValidationError, json.JSONDecodeError, ValueError)",
      "identity": "scripts/api_openai.py|OpenAIProvider._get_structured_completion_native_sync|47ff63a9e862d730246030bbdb9463fb3e48aabc823b40ce08667145068c8bda|1",
      "line": 637,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "OpenAIProvider._get_structured_completion_native_sync"
    },
    {
      "ast_exempt": true,
      "caught_type": "WireContractViolation",
      "identity": "scripts/api_openai.py|OpenAIProvider._get_structured_completion_chat_completions_sync|7fbcbe55e4ba9b0572e93db9cbb3c4c8f9d0729a512e9b39c9bab536a37e70fe|1",
      "line": 762,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "OpenAIProvider._get_structured_completion_chat_completions_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "ModelRetry",
      "identity": "scripts/api_openai.py|OpenAIProvider._get_structured_completion_chat_completions_sync|da4b30f6fc91b90bce4c77b9b1d7ad2a66c7a562d6eb7fe1ab49c5f6fcb80a8e|1",
      "line": 768,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "OpenAIProvider._get_structured_completion_chat_completions_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValidationError, json.JSONDecodeError, ValueError)",
      "identity": "scripts/api_openai.py|OpenAIProvider._get_structured_completion_chat_completions_sync|fd60eb66ecbd7821d5e8ee6cc9873065aabf1133eef3b6b859aaff9990fba1d1|1",
      "line": 779,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "OpenAIProvider._get_structured_completion_chat_completions_sync"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/api_openai.py|OpenAIProvider._get_completion_unified|d3f7adbbdf0716a1af5a64e81c87ebab226eaba989318364a3072be44b0fae81|1",
      "line": 1054,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "OpenAIProvider._get_completion_unified"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/api_openai.py|setup_abort_handler|74fee6afe2a86ffa69f4959240e4a22c16d47c358be835d8e5bae84c31db8591|1",
      "line": 1291,
      "marker": null,
      "path": "scripts/api_openai.py",
      "scope": "setup_abort_handler"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/api_openrouter.py|<module>|342ba95f67bf2c7b0a17697da083ca2df807fb09403a67d5182115fad7a5e332|1",
      "line": 36,
      "marker": null,
      "path": "scripts/api_openrouter.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/api_openrouter.py|<module>|a9dad04b35b4bea4a298019a7b51364dffde56195f4d71baa83e3094b87d473d|1",
      "line": 59,
      "marker": null,
      "path": "scripts/api_openrouter.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/api_openrouter.py|OpenRouterProvider.get_completion|524a52d91dfede362257442965b3c291f49727e92af268a88285450b355914a0|1",
      "line": 388,
      "marker": null,
      "path": "scripts/api_openrouter.py",
      "scope": "OpenRouterProvider.get_completion"
    },
    {
      "ast_exempt": true,
      "caught_type": "json.JSONDecodeError",
      "identity": "scripts/api_openrouter.py|OpenRouterProvider._get_completion_http|82f04ed0c3baf2d05789ceed5ac370399f43f6703c1597a09df15ce219f7ab72|1",
      "line": 481,
      "marker": null,
      "path": "scripts/api_openrouter.py",
      "scope": "OpenRouterProvider._get_completion_http"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.exceptions.HTTPError",
      "identity": "scripts/api_openrouter.py|OpenRouterProvider._get_completion_http|cc6ad09a674e043b3961dd6371c9c8912cf4fff878f98854583d666516080b1c|1",
      "line": 496,
      "marker": null,
      "path": "scripts/api_openrouter.py",
      "scope": "OpenRouterProvider._get_completion_http"
    },
    {
      "ast_exempt": true,
      "caught_type": "json.JSONDecodeError",
      "identity": "scripts/api_openrouter.py|OpenRouterProvider._get_completion_http|a0c94760837f163c88a1474b6558c00a15ab86db4d41a298ca29c36a6b52628a|1",
      "line": 509,
      "marker": null,
      "path": "scripts/api_openrouter.py",
      "scope": "OpenRouterProvider._get_completion_http"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/api_openrouter.py|OpenRouterProvider._get_completion_http|c3b5c7d882f83120b58bbc0ff7136dc5a7eb8317cc561669b16865be08538890|1",
      "line": 512,
      "marker": null,
      "path": "scripts/api_openrouter.py",
      "scope": "OpenRouterProvider._get_completion_http"
    },
    {
      "ast_exempt": false,
      "caught_type": "RuntimeError",
      "identity": "scripts/apply_slot2_semantic_tags.py|_resolve_database_url|863399c80a3f0be9719ccaead9997aafd27bc88a8dce5eee749efb6b4cae6061|1",
      "line": 187,
      "marker": null,
      "path": "scripts/apply_slot2_semantic_tags.py",
      "scope": "_resolve_database_url"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/assemble_context.py|ContextAssembler._connect_to_db|4764daab1623e6215aa04177a4031953d71023341bacb6de10caa1337b15190f|1",
      "line": 83,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler._connect_to_db"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/assemble_context.py|ContextAssembler._load_file|5966781390eb3fe12855a383a85ed7429b64ef59b0b8c761570bc352e91acecb|1",
      "line": 96,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler._load_file"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/assemble_context.py|ContextAssembler._save_file|3c8577fda0a34daf7c1c520015386c97f737e700e583746bf85b77dc911d5ffd|1",
      "line": 155,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler._save_file"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/assemble_context.py|ContextAssembler.add_episode_raw|36ae5b8c6d34fba0ce31e0cd997e7154250ded834d6691f71ffc4bcf853fbf28|1",
      "line": 706,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.add_episode_raw"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.add_chunks|49bedd438506eda472a6c9e6c7fa42efe68a1104b0b923d0f20a9409f315a7ec|1",
      "line": 1042,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.add_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.add_chunks|8d980d4da3a1e3d18b29e3ff820b24091cc65b097abfb70fe648955c67a94ee5|1",
      "line": 1052,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.add_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.add_chunks|e0dcd5531e9ffa78e7f0f208462c9fe4369b852bb1fbb07212269b4e0345900b|1",
      "line": 1067,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.add_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.add_chunks|23aebbfdadc875883bb129ed509f3c06e7b1ca4e45f744ad4b682c2404c5cc1b|1",
      "line": 1074,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.add_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.remove_chunks|49bedd438506eda472a6c9e6c7fa42efe68a1104b0b923d0f20a9409f315a7ec|1",
      "line": 1194,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.remove_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.remove_chunks|8d980d4da3a1e3d18b29e3ff820b24091cc65b097abfb70fe648955c67a94ee5|1",
      "line": 1204,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.remove_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.remove_chunks|e0dcd5531e9ffa78e7f0f208462c9fe4369b852bb1fbb07212269b4e0345900b|1",
      "line": 1219,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.remove_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.remove_chunks|23aebbfdadc875883bb129ed509f3c06e7b1ca4e45f744ad4b682c2404c5cc1b|1",
      "line": 1226,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.remove_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.handle_command|ef114e3f0a6be9fa79c1d6a3633e7f707537db238e11d5b4451b26de918d37bd|1",
      "line": 1316,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.handle_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.handle_command|06baa615936c1ffc5117dcf4f1afe1a9dc951d2999a8d547e722314e744c761c|1",
      "line": 1339,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.handle_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.handle_command|e63812cc1ad19d08697700cabfbd514542c936225a0f452df76275d37f325804|1",
      "line": 1417,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.handle_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.handle_command|e63812cc1ad19d08697700cabfbd514542c936225a0f452df76275d37f325804|2",
      "line": 1449,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.handle_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/assemble_context.py|ContextAssembler.handle_command|06baa615936c1ffc5117dcf4f1afe1a9dc951d2999a8d547e722314e744c761c|2",
      "line": 1502,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "ContextAssembler.handle_command"
    },
    {
      "ast_exempt": false,
      "caught_type": "KeyboardInterrupt",
      "identity": "scripts/assemble_context.py|main|9be3cec98175d2ad467d7adb7bec68ad5523314bd1c8e6682cc60b942296f4d8|1",
      "line": 1681,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "EOFError",
      "identity": "scripts/assemble_context.py|main|a811f3debd376cd884d7c241b6cbd5809ebc9527e602728e99ec6a62ed0615fa|1",
      "line": 1683,
      "marker": null,
      "path": "scripts/assemble_context.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "(OSError, ValueError, SyntaxError, tokenize.TokenError, subprocess.CalledProcessError)",
      "identity": "scripts/check_exception_dispositions.py|main|3d9d3d4237cd1d8a2c53ee0fe8e2d5fa79df94a920d80c8f4e4be30010437c9d|1",
      "line": 555,
      "marker": {
        "kind": "fail",
        "reason": "lint error",
        "safety": "exit 1"
      },
      "path": "scripts/check_exception_dispositions.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/check_migration_comments.py|Finding.render|2db3f05443929199ec7af3c70ba2c77830f30351c96460100079d4a08e6cbcd3|1",
      "line": 326,
      "marker": null,
      "path": "scripts/check_migration_comments.py",
      "scope": "Finding.render"
    },
    {
      "ast_exempt": false,
      "caught_type": "_LexError",
      "identity": "scripts/check_migration_comments.py|_scan_sql|be1aa1a8f1e105ecdccb5eaf62c4a0038a61885f997a92d5391f58879e1c22f7|1",
      "line": 1537,
      "marker": null,
      "path": "scripts/check_migration_comments.py",
      "scope": "_scan_sql"
    },
    {
      "ast_exempt": false,
      "caught_type": "SyntaxError",
      "identity": "scripts/check_migration_comments.py|check_file|71543273ac77464d85aacf437a44070179825ba2ed24ed158cd4d48a463b0a2b|1",
      "line": 1621,
      "marker": null,
      "path": "scripts/check_migration_comments.py",
      "scope": "check_file"
    },
    {
      "ast_exempt": false,
      "caught_type": "(OSError, UnicodeDecodeError)",
      "identity": "scripts/check_model_drift.py|find_violations|08168fb10fc7b04c946f5540b189e75d75ddcc9d3cb89a5e379208f1285f40c3|1",
      "line": 107,
      "marker": null,
      "path": "scripts/check_model_drift.py",
      "scope": "find_violations"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ImportError, ValueError)",
      "identity": "scripts/check_reachability.py|analyze_repository.ImportVisitor.literal_dynamic_name|e7c5d9e8cb978249efc29254173b483513e9d518b4451b2fa3085b4de1c6259d|1",
      "line": 576,
      "marker": null,
      "path": "scripts/check_reachability.py",
      "scope": "analyze_repository.ImportVisitor.literal_dynamic_name"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/create_vector_index.py|<module>|b3af6c4e90cca9342a7c4d3b1490fe9005dd09f1696b37dbd3cafccba6f23d00|1",
      "line": 42,
      "marker": null,
      "path": "scripts/create_vector_index.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/create_vector_index.py|create_vector_indexes|6d0be0be54e34ea3a5615a35603975a846d0cbf586a1634e6523ee524c5ba662|1",
      "line": 203,
      "marker": null,
      "path": "scripts/create_vector_index.py",
      "scope": "create_vector_indexes"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/create_vector_index.py|create_vector_indexes|9b0bab420e3c3afd1ffe6b4ea3aa4982fbef090bbd6ee2c546110f69a247f640|1",
      "line": 216,
      "marker": null,
      "path": "scripts/create_vector_index.py",
      "scope": "create_vector_indexes"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/create_vector_index.py|main|467a7aaad63846f65005ffe01f8791816a2dcd53236d62b789d85ba2d710d391|1",
      "line": 239,
      "marker": null,
      "path": "scripts/create_vector_index.py",
      "scope": "main"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/creative_character_expansion.py|connect_to_database|6d3cf722de429a3c739f2d94d601911df63dad201a61488e0cfbc19fcd37acdf|1",
      "line": 313,
      "marker": null,
      "path": "scripts/creative_character_expansion.py",
      "scope": "connect_to_database"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/creative_character_expansion.py|update_character_expansion|68cb4e67f852565e364506a17982d8182c7301ec300ef09a58b28d6e56da37e2|1",
      "line": 640,
      "marker": null,
      "path": "scripts/creative_character_expansion.py",
      "scope": "update_character_expansion"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/creative_character_expansion.py|update_character_expansion|b6c13a049a37af3932dc62f9089796a99ef9a5d3bd714db0c89d9b3a147c837d|1",
      "line": 663,
      "marker": null,
      "path": "scripts/creative_character_expansion.py",
      "scope": "update_character_expansion"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/creative_character_expansion.py|update_character_expansion|ed657d00572662cbcb6963804e5225649add75f00ff07a68b44f818e98669a17|1",
      "line": 723,
      "marker": null,
      "path": "scripts/creative_character_expansion.py",
      "scope": "update_character_expansion"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/creative_character_expansion.py|load_prompt_from_json|ce2baf0ec5e3e9b3e5df9a71e39012888f544c0ffb5fe993b7fe2c348b863362|1",
      "line": 952,
      "marker": null,
      "path": "scripts/creative_character_expansion.py",
      "scope": "load_prompt_from_json"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/creative_character_expansion.py|load_manual_context|2c456b693a23665692b7a4146c31e8f4ccf4878cef9778198be99ebb7e395ef9|1",
      "line": 989,
      "marker": null,
      "path": "scripts/creative_character_expansion.py",
      "scope": "load_manual_context"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/creative_character_expansion.py|load_expansion_from_file|ded6f304449e68598b28aeb1574931ceccbfe1803cd7f478536d9d0d165bb887|1",
      "line": 1179,
      "marker": null,
      "path": "scripts/creative_character_expansion.py",
      "scope": "load_expansion_from_file"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/creative_character_expansion.py|generate_expansions|e546a41b8d5ac64550ba70fbdf7818ba6d2c637dfaa9e86e2ed9d23f1749e6cd|1",
      "line": 1482,
      "marker": null,
      "path": "scripts/creative_character_expansion.py",
      "scope": "generate_expansions"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/creative_character_expansion.py|main|4e7600015c2cb60b260df66fbe0aba7f638b364bae3e004c49fe0b76131fca06|1",
      "line": 1574,
      "marker": null,
      "path": "scripts/creative_character_expansion.py",
      "scope": "main"
    },
    {
      "ast_exempt": true,
      "caught_type": "BaseException",
      "identity": "scripts/entity_reference_parity.py|open_read_only_connection|84e3e5979720b2985591e7674edb9efffdd2eb8da1be4ffdaa4cfaed0c7d106d|1",
      "line": 200,
      "marker": null,
      "path": "scripts/entity_reference_parity.py",
      "scope": "open_read_only_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/estimate_time_delta.py|<module>|e08747dc2d4050cc9f744f179e40c9e35347508413791cb3b276a3f88d620c0f|1",
      "line": 49,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/estimate_time_delta.py|<module>|342ba95f67bf2c7b0a17697da083ca2df807fb09403a67d5182115fad7a5e332|1",
      "line": 54,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|<module>|672550b9ed7bb507a26b7a9273bb304fb56c16525b5f8b80a3f5b9ba080470b9|1",
      "line": 83,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|LLMProvider.from_provider_name|c066a1ad8aa7fa84a8d2e8f507c6effe6cbd9ecf0ab8db328c8cccd5e737ef67|1",
      "line": 244,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "LLMProvider.from_provider_name"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|OpenAIProvider.initialize|937c97911c43051d09a8b787fa56553288771f1a20f0d60028ab9dc11cdf33fc|1",
      "line": 374,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "OpenAIProvider.initialize"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|OpenAIProvider._get_reasoned_completion|7a0a3d95c9a7ed8ec820e83c44d61c1b76d05cdb14b95e2882c331ea26c4828d|1",
      "line": 474,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "OpenAIProvider._get_reasoned_completion"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|OpenAIProvider._get_reasoned_completion|62aa083c98f18a33be506bb076a7d63b71e1c715809a3bab60fd069e0cd9f806|1",
      "line": 502,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "OpenAIProvider._get_reasoned_completion"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|get_db_connection|4c01ecfa155f3fa5c48bec02d17058af6dfc7aaf57a952b5ca5fc78145bf0ece|1",
      "line": 644,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "get_db_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|get_chunk_by_id|3b8666a8eb7ac7afedae64722b49b9288719e2e94cb4497a5c39b11d688d53b0|1",
      "line": 661,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "get_chunk_by_id"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|get_chunks_in_range|2a5d1ec9bdcd179223eb200fb2341f80e1321f00eeb6767510ed4e18a1d28356|1",
      "line": 683,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "get_chunks_in_range"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|get_all_chunks_needing_time_delta|8ff4678d8947538b0af1a37b05c8a3760d8c0e6ea459a4843b9d35f1821af315|1",
      "line": 721,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "get_all_chunks_needing_time_delta"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|get_chunk_world_layer|4237c676be3b7ab064107b273bd7eb61c913d63f4e0b087c2f7a6efde66f5dda|1",
      "line": 742,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "get_chunk_world_layer"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|get_context_chunks|cc7b8f66ee48fc3ab81a0777237984483e057095677792f3b918f3ce2880e6db|1",
      "line": 764,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "get_context_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|get_extended_context_chunks|3df12827226519d0ef271a99ce97e1ae3d2e168de5bc9e6bb4c5ae7fb92a48b0|1",
      "line": 873,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "get_extended_context_chunks"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|query_llm|237bc793709dc61b955924070e3ac079d95a0e4e9e360d8da6d922695e553cae|1",
      "line": 1066,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "query_llm"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|parse_time_delta|ab252bb843db85c0f00b9433abc4e59ec6ddd9464720c5ab6d44a4e50a850685|1",
      "line": 1134,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "parse_time_delta"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|parse_time_delta|f1c09838e3692d40b16a9b2c0f074534605343c1fef62e4bfbc248cb1aba138b|1",
      "line": 1179,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "parse_time_delta"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|parse_time_delta|9392582b3eb23ed9af9d340c93eb62e54be88d082002b84464ffcff9d4cfcd16|1",
      "line": 1194,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "parse_time_delta"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|parse_time_delta|9d8ade73f9c2bd3fbad0b13aaac97488b744feddef62f4eba1ce87d757a0cba7|1",
      "line": 1216,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "parse_time_delta"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|update_chunk_metadata|c05cb09f7944796db74273702734033bf236f7821c7f31fea267444580b7902c|1",
      "line": 1314,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "update_chunk_metadata"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|update_chunk_metadata|776bf1c331daf01aed0a11fb264b3f50926b93b3d68e6c13114437d46e146b83|1",
      "line": 1325,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "update_chunk_metadata"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|get_chunk_time_delta|9ce575dbd3c0effbff49591238aa423fb21a5f14a7225ba50ecdb1be146172ff|1",
      "line": 1346,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "get_chunk_time_delta"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|main|967f098e08860b6e34f9b75e614270be375f2ba5f79e48ac75cc6d58a77241f1|1",
      "line": 1662,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|main|c8c9789ca2e8f5fb6bd43169d2fc18a05b55dda046d6f43b903d4a29a47384b3|1",
      "line": 1745,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/estimate_time_delta.py|main|ac86ac8e9fbb69b787c77a52a4183f0dcab232cf3eeaa7008a33b6554d605c30|1",
      "line": 1798,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "<bare>",
      "identity": "scripts/estimate_time_delta.py|main|e475442a6813c605fa66f0bd88b10de33869705ae31f2051ad9f36b8d16c83a3|1",
      "line": 1804,
      "marker": null,
      "path": "scripts/estimate_time_delta.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "scripts/extract_scene_numbers.py|connect_to_db|4ef87b1e791b697e14335b7d8cac0dd8b4185b2ca13e1d591666baee1bf28c8d|1",
      "line": 56,
      "marker": null,
      "path": "scripts/extract_scene_numbers.py",
      "scope": "connect_to_db"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/extract_scene_numbers.py|extract_scene_from_slug|0f7335a414b10dfe03fa1139db52235b8cf5ad382bc53b1c76407c42bcf65dff|1",
      "line": 80,
      "marker": null,
      "path": "scripts/extract_scene_numbers.py",
      "scope": "extract_scene_from_slug"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "scripts/extract_scene_numbers.py|get_chunks_without_scene|b1cdac99335815b7a6d8aed82f6dfbbb251a2392bd273a6a557303ae1e9569ec|1",
      "line": 118,
      "marker": null,
      "path": "scripts/extract_scene_numbers.py",
      "scope": "get_chunks_without_scene"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "scripts/extract_scene_numbers.py|update_scene_numbers|5b159e8efea8bfb888b8ea049daff2111450dba00956e1825c4e17099c735230|1",
      "line": 141,
      "marker": null,
      "path": "scripts/extract_scene_numbers.py",
      "scope": "update_scene_numbers"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "scripts/extract_scene_numbers.py|add_scene_column_if_not_exists|61337d22cec127200f4d6710690fd39a1c3ef2b0716a6a3c75363a26ce54b049|1",
      "line": 187,
      "marker": null,
      "path": "scripts/extract_scene_numbers.py",
      "scope": "add_scene_column_if_not_exists"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/extract_season_episode.py|SeasonEpisodeExtractor.process_chunks|dbed0eeea310fde98711e0e358cf44899ba01c7fef50c25f2ba8291ef21b3978|1",
      "line": 306,
      "marker": null,
      "path": "scripts/extract_season_episode.py",
      "scope": "SeasonEpisodeExtractor.process_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/faction_relationship_analyst.py|get_db_connection|4764daab1623e6215aa04177a4031953d71023341bacb6de10caa1337b15190f|1",
      "line": 225,
      "marker": null,
      "path": "scripts/faction_relationship_analyst.py",
      "scope": "get_db_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/faction_relationship_analyst.py|get_faction_roster|d2c47a1c91e4e09914a2104169bbcd7284dd7bf6faf01b4619f55945ab3c05d0|1",
      "line": 251,
      "marker": null,
      "path": "scripts/faction_relationship_analyst.py",
      "scope": "get_faction_roster"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/faction_relationship_analyst.py|get_faction_data|5e3a5f12973557c3597ad702654db10c1c987a5e4776741bc23a49036b1173d1|1",
      "line": 291,
      "marker": null,
      "path": "scripts/faction_relationship_analyst.py",
      "scope": "get_faction_data"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/faction_relationship_analyst.py|get_character_data|36dac83928cffd6c193a6910c0c5261241c9a18b115af3c6de0738260ce14476|1",
      "line": 331,
      "marker": null,
      "path": "scripts/faction_relationship_analyst.py",
      "scope": "get_character_data"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/faction_relationship_analyst.py|call_openai_api_faction_to_faction|cddb1425366880c1a2fe8b0645649f081f61aa02dc199835bcbfba704a609571|1",
      "line": 455,
      "marker": null,
      "path": "scripts/faction_relationship_analyst.py",
      "scope": "call_openai_api_faction_to_faction"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/faction_relationship_analyst.py|call_openai_api_faction_to_character|cddb1425366880c1a2fe8b0645649f081f61aa02dc199835bcbfba704a609571|1",
      "line": 491,
      "marker": null,
      "path": "scripts/faction_relationship_analyst.py",
      "scope": "call_openai_api_faction_to_character"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/faction_relationship_analyst.py|save_faction_to_faction_relationship|6607607d62dabc1afa6aea9202165f1dba7a0e13bc3b8df16ad90cc3982f7e3e|1",
      "line": 584,
      "marker": null,
      "path": "scripts/faction_relationship_analyst.py",
      "scope": "save_faction_to_faction_relationship"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/faction_relationship_analyst.py|save_faction_to_character_relationship|9a0fa88f719972cb6555718e250150566bc6d574b5d786ccbcac0fd455e0b68d|1",
      "line": 678,
      "marker": null,
      "path": "scripts/faction_relationship_analyst.py",
      "scope": "save_faction_to_character_relationship"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/faction_relationship_analyst.py|main|d5458d17591644e384d381eb85185f05040bb332ae23273f23abcf6de62b02d3|1",
      "line": 722,
      "marker": null,
      "path": "scripts/faction_relationship_analyst.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/fix_chunks.py|main|86bf725ef62c8252972cc0a0da8abce1886ecec1bd3528f17f9772cea8303119|1",
      "line": 103,
      "marker": null,
      "path": "scripts/fix_chunks.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/fix_episode_ranges.py|main|827e2d7e5a2f1b9251b829aa3e0e3dc0010247e1777d56148f048b793d93c30d|1",
      "line": 104,
      "marker": null,
      "path": "scripts/fix_episode_ranges.py",
      "scope": "main"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/freestyle_api_query.py|connect_to_database|6d3cf722de429a3c739f2d94d601911df63dad201a61488e0cfbc19fcd37acdf|1",
      "line": 202,
      "marker": null,
      "path": "scripts/freestyle_api_query.py",
      "scope": "connect_to_database"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/freestyle_api_query.py|save_api_package|6e25a01e071cc8d253b506867881e64d7ba0bb7b2c1239b00fe71d61eaa802f4|1",
      "line": 641,
      "marker": null,
      "path": "scripts/freestyle_api_query.py",
      "scope": "save_api_package"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/freestyle_api_query.py|load_api_package|b8720ae696c2e7f4cf378c38c689f5d9464965200cbe8166f89f74b1fb3b2ce5|1",
      "line": 676,
      "marker": null,
      "path": "scripts/freestyle_api_query.py",
      "scope": "load_api_package"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/freestyle_api_query.py|call_openai_api|a84b958b772f02433c835c96a083ea6bc53bb4cb20d1340d868a3f4a26203fec|1",
      "line": 698,
      "marker": null,
      "path": "scripts/freestyle_api_query.py",
      "scope": "call_openai_api"
    },
    {
      "ast_exempt": false,
      "caught_type": "MissingSecretError",
      "identity": "scripts/freestyle_api_query.py|call_openai_api|a0824612a87a4189d93984bf69f181bf75db737eeff939c11c0cdec209779775|1",
      "line": 707,
      "marker": null,
      "path": "scripts/freestyle_api_query.py",
      "scope": "call_openai_api"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/freestyle_api_query.py|call_openai_api|c6b04d729d39bc081c84003fc18433ad229929cd140e45f50814399c29ef1a76|1",
      "line": 752,
      "marker": null,
      "path": "scripts/freestyle_api_query.py",
      "scope": "call_openai_api"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/freestyle_api_query.py|main|d44a6db06e55e9cb6ac48fb3cdd947039c7b885f4326a95cf49a84b3a04b1fdf|1",
      "line": 903,
      "marker": null,
      "path": "scripts/freestyle_api_query.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/freestyle_api_query.py|main|133d86095fb110a518d8cee44282c57eec68ae82b8740230ea06ac3c439b213c|1",
      "line": 947,
      "marker": null,
      "path": "scripts/freestyle_api_query.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/freestyle_api_query.py|main|6e25a01e071cc8d253b506867881e64d7ba0bb7b2c1239b00fe71d61eaa802f4|1",
      "line": 1006,
      "marker": null,
      "path": "scripts/freestyle_api_query.py",
      "scope": "main"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/gis_backfill.py|main|30022d6c035fbb03281428a83d86157281f33882f85c3468385752e4d857da61|1",
      "line": 292,
      "marker": null,
      "path": "scripts/gis_backfill.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/import_narratives.py|<module>|31f932a3dfc720fe6b4856f6a41530b76d99685313db2d5af54df22968c06457|1",
      "line": 37,
      "marker": null,
      "path": "scripts/import_narratives.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/import_narratives.py|<module>|bc16a264337aeff2635fc1fde956a58aa7b4a433e53b52b8772394e36ad69515|1",
      "line": 109,
      "marker": null,
      "path": "scripts/import_narratives.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/import_narratives.py|<module>|f69ea4153a2aa9bd14ae2b196b423c976954a3eaacd5943fc9bd3ee336290a84|1",
      "line": 119,
      "marker": null,
      "path": "scripts/import_narratives.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/import_narratives.py|<module>|4a73365399727cd33460405b69a10a20f10fe761360f8391110b23135c745a45|1",
      "line": 148,
      "marker": null,
      "path": "scripts/import_narratives.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/import_narratives.py|NarrativeImporter.__init__|47a57f7af7baae82b56efa768c34ec70c5400718c3b3156dbaa608bf21c16e29|1",
      "line": 265,
      "marker": null,
      "path": "scripts/import_narratives.py",
      "scope": "NarrativeImporter.__init__"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/import_narratives.py|NarrativeImporter.process_chunked_file|311a4109dd97ee86996d06ef0a9a6ff3cf4ee44b4f0f751e58ccacfa64a4f16f|1",
      "line": 384,
      "marker": null,
      "path": "scripts/import_narratives.py",
      "scope": "NarrativeImporter.process_chunked_file"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/import_narratives.py|NarrativeImporter.store_narrative_chunk|e629d8420750b684ed03b755d6d06bf3d46af9a4133b768b94d1b91a7d0b1bb2|1",
      "line": 602,
      "marker": null,
      "path": "scripts/import_narratives.py",
      "scope": "NarrativeImporter.store_narrative_chunk"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/import_narratives.py|NarrativeImporter.store_narrative_chunk|fecf88820a6ddb46cb0ff03997be53c9a598fef66e9a94ec0137610f3210ad22|1",
      "line": 615,
      "marker": null,
      "path": "scripts/import_narratives.py",
      "scope": "NarrativeImporter.store_narrative_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/import_narratives.py|main|55e7ce774b7cf4c7300b8cffd43f923bb38d906f6204c139be19a8c0bcb80a1b|1",
      "line": 684,
      "marker": null,
      "path": "scripts/import_narratives.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/map_builder_legacy.py|<module>|a7b9da76e3ada305c03d47b81a8ff50bb1817abbc544d8214ab19dd5eff62131|1",
      "line": 102,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|get_db_connection|9d2b72ca9e75c4661d651fac7b328ec98b9c276f36640ffe74ea82692bff7745|1",
      "line": 254,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_db_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|check_database_schema|215999eb2491e9c41533d346735942e6f59c33c42776ede8fdd39f56991f6ae2|1",
      "line": 289,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "check_database_schema"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|check_database_schema|f0c7ba2e3d3740e45755f6c3013ab4ff30c34b45b479e990dbe3ff7a62cc3215|1",
      "line": 292,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "check_database_schema"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|load_known_places|de9ec4cb905d68edfabfaecba25aa6c47f249642e004b54242bd82211fee77cd|1",
      "line": 317,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "load_known_places"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|load_zones|5c8deaead6596ba96443b73f311e9940ceeefa37a0eae62827dcdcd13b5f0b7a|1",
      "line": 336,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "load_zones"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|get_chunks_to_process|726451ba3d00cb14e77759a8090d2df846e8abde98df40a9afebd0c8f3e4f7e4|1",
      "line": 411,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_chunks_to_process"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|get_llm_structured_response|32daaece3e8661421e98b7ad5c84d8c7b73dbc23c72b6a52382440172dcb9b66|1",
      "line": 715,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|get_llm_structured_response|6373c219f982d49b6b80678ebae83f0fb38d0f31f1e86f2b611b5889b03c4e42|1",
      "line": 809,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|get_llm_structured_response|e62c8af76901ddd29957ae8ef0a67220dd5f29505794dc33da9260b64cf0f56c|1",
      "line": 844,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|get_llm_structured_response|b0e45bf959044b2b278b40eec27c60879caef59634b7b3d4e9d4a03400728e74|1",
      "line": 1039,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "scripts/map_builder_legacy.py|get_llm_structured_response|a1f2567546db63958b85c13e4bf653fa2d00c426e351224dd07fe33011931bfb|1",
      "line": 1126,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "scripts/map_builder_legacy.py|get_llm_structured_response|5cfa74fa97714e8cf3e1769d3fdbedff2fa3e93ebd3be09136d227cf7c058ceb|1",
      "line": 1146,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|get_llm_structured_response|9a823474ea9dde6688011fec6c6d97f1917cd83dc3ba2bde3729d8c4e2f33efb|1",
      "line": 1152,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|get_llm_structured_response|7cf30ec6fb12fd83c131efed73e951facb0ae23e9b67a6a6f15c6d4a20411621|1",
      "line": 1166,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|add_new_place|4eb390ac9fa61755408612ba598f18484a180485d771da408216a547d56beaa8|1",
      "line": 1272,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "add_new_place"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|add_new_place|1ef8cd69ffb5f2c9d268da8f88a8c67eab5ab84ac2e52220c53306664829e939|1",
      "line": 1316,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "add_new_place"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|add_new_place|5e24fd0d2a9e000130f0a3919898a9320aad4526d877b7aef6186f52267029e8|1",
      "line": 1324,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "add_new_place"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|update_chunk_metadata|b77c4f7462490edf0abd16842cabe5318afd62d24d8ee4a46ccb1f90bf4a8489|1",
      "line": 1386,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "update_chunk_metadata"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|update_chunk_metadata|0a82db2e7c7ee18ccc71d4b28ce3b31167797cdb1a0cca13f912a725b09d1c49|1",
      "line": 1392,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "update_chunk_metadata"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|get_previous_chunks_info|0bf5908351772af83e1788da6ae5563797594aa31edc3732df36bb4ee3c1f5ef|1",
      "line": 1468,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "get_previous_chunks_info"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|process_chunk|62ed33b86560957bb8090520e57115c2a7fd589cb1435e7d4bed7886c945ecc2|1",
      "line": 1570,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/map_builder_legacy.py|process_chunk|778afe4bec4e172579413cce96e52664cfb736ae6a1141ac475b42a19e43840c|1",
      "line": 1658,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/map_builder_legacy.py|process_chunk|f884cc89a8b08e589f3c01210617b2b48bcf6205be4aed74e03cedbdf41f44aa|1",
      "line": 1703,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "EOFError",
      "identity": "scripts/map_builder_legacy.py|process_chunk|f916e6891bbd7594c56af315491e478ff4561f3e29db23678fe9263eb94679bf|1",
      "line": 1760,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/map_builder_legacy.py|process_chunk|18cb46c6c1e67dd0fb8e809ae6aa8fc0e1bfc0cda83be3b5275758e1808abb24|1",
      "line": 1931,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/map_builder_legacy.py|process_chunk|f884cc89a8b08e589f3c01210617b2b48bcf6205be4aed74e03cedbdf41f44aa|2",
      "line": 1986,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/map_builder_legacy.py|process_chunk|28f586d8eb112da0d1fa57313afcfcaa7c0df58bbbb8f3583cbc615c64f4370f|1",
      "line": 2133,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/map_builder_legacy.py|process_chunk|18cb46c6c1e67dd0fb8e809ae6aa8fc0e1bfc0cda83be3b5275758e1808abb24|2",
      "line": 2177,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/map_builder_legacy.py|process_chunk|18cb46c6c1e67dd0fb8e809ae6aa8fc0e1bfc0cda83be3b5275758e1808abb24|3",
      "line": 2268,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "EOFError",
      "identity": "scripts/map_builder_legacy.py|process_chunk|400c00d68e456593215ccdc445f3790f62d88851d060fc5b21dd934c1a9aaec4|1",
      "line": 2285,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "EOFError",
      "identity": "scripts/map_builder_legacy.py|process_chunk|2f8afbbad335695f16d6cb84ea654ed991b15c6e4cb697ef51b2b25405c3dc5d|1",
      "line": 2318,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|main|794719a3b9d7c38223c7ed351b22a89c3b8db1f2d3515a303f2406d07c04bb79|1",
      "line": 2354,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|main|4e6c491a89deadad7987aa5b3375032912174304bfb1f3f31698fa113fe1f8a9|1",
      "line": 2365,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|main|401a67fd70212216550fd61619f2d6d4f7c26374aba658c55872d95943e83f08|1",
      "line": 2429,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ImportError, ValueError)",
      "identity": "scripts/map_builder_legacy.py|main|8210ea0da73cd5405bf5cf88e67f4f436039d27206de5c20e69bcc38bdb86b47|1",
      "line": 2436,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|main|3e469c3d88934a6a1bad6a7aad52f240f6e5c36782f98e44c2ce8a39e7a66eb5|1",
      "line": 2445,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|main|f00e0462712b756df88860a3daba8c3f4ee84e4f39899b59f97e3ee39de0cff4|1",
      "line": 2456,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|main|0485b4617c0352652201f12d440ba72d9d3e9567a4b8e8f78bccf7ee5d437978|1",
      "line": 2504,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/map_builder_legacy.py|main|e6e5295a71bc8176ff052b9f216d5a96c2cbb7cabdf52e6e17db7f8e88e4ee9a|1",
      "line": 2569,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "EOFError",
      "identity": "scripts/map_builder_legacy.py|main|a87876e247760e051d282babdbd52631c6540b5fefa26d0982ae0f43523a1b27|1",
      "line": 2613,
      "marker": null,
      "path": "scripts/map_builder_legacy.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/migrate.py|apply_migration|6996ecb3e1bff1228e38febb5d1e8b590b3d821ea706c7d2664f85297b22dcd6|1",
      "line": 360,
      "marker": null,
      "path": "scripts/migrate.py",
      "scope": "apply_migration"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/migrate.py|migrate_targets|6779499827bb540ef751eacd45bc1bfd5f21eb2bff87a64f9f1efff33f265426|1",
      "line": 475,
      "marker": null,
      "path": "scripts/migrate.py",
      "scope": "migrate_targets"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "scripts/migrate.py|show_status|67e96e92fb2860baa1ced0bd3a877db4585da661467715a47337f29f06b9a2a9|1",
      "line": 538,
      "marker": null,
      "path": "scripts/migrate.py",
      "scope": "show_status"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/migrate_chunk_character_references.py|resolve_unknown_character|9508b8aab8d58709d5f0a8b76f4f0fcda8294b507c6c1463d177870b43075483|1",
      "line": 118,
      "marker": null,
      "path": "scripts/migrate_chunk_character_references.py",
      "scope": "resolve_unknown_character"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/migrate_chunk_character_references.py|migrate_references|6ec48996d5ec8b97791aeb8d7d4ba6f749eae2c7c50ec04823fb32aa5433dec4|1",
      "line": 268,
      "marker": null,
      "path": "scripts/migrate_chunk_character_references.py",
      "scope": "migrate_references"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/migrate_chunk_character_references.py|main|f988fa590a34f6e40dfa50d6b28a4a36e7044c23e5eea3ef4376a6b7ce9a0b9d|1",
      "line": 346,
      "marker": null,
      "path": "scripts/migrate_chunk_character_references.py",
      "scope": "main"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/migrate_provider_names.py|migrate|28061ae513194e5696b77ea1b54238f92f981f68e220ef56ea670ac8032edf4a|1",
      "line": 122,
      "marker": null,
      "path": "scripts/migrate_provider_names.py",
      "scope": "migrate"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/new_story_setup.py|<module>|59e1a4ba7492a02efae120e4085d91ec13dd0b9602208de19b2ad7d95987142b|1",
      "line": 39,
      "marker": null,
      "path": "scripts/new_story_setup.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "OSError",
      "identity": "scripts/new_story_setup.py|initialize_slot_database|bf33d5d59a3b5a5379a1c583da99df80bc6e68a07c0f0abdad1c379b5cd6d625|1",
      "line": 259,
      "marker": null,
      "path": "scripts/new_story_setup.py",
      "scope": "initialize_slot_database"
    },
    {
      "ast_exempt": false,
      "caught_type": "OSError",
      "identity": "scripts/new_story_setup.py|_copy_template_data|bf33d5d59a3b5a5379a1c583da99df80bc6e68a07c0f0abdad1c379b5cd6d625|1",
      "line": 357,
      "marker": null,
      "path": "scripts/new_story_setup.py",
      "scope": "_copy_template_data"
    },
    {
      "ast_exempt": false,
      "caught_type": "OSError",
      "identity": "scripts/new_story_setup.py|clone_slot_with_data|bf33d5d59a3b5a5379a1c583da99df80bc6e68a07c0f0abdad1c379b5cd6d625|1",
      "line": 480,
      "marker": null,
      "path": "scripts/new_story_setup.py",
      "scope": "clone_slot_with_data"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/process_characters.py|<module>|a7b9da76e3ada305c03d47b81a8ff50bb1817abbc544d8214ab19dd5eff62131|1",
      "line": 98,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|get_db_connection|9d2b72ca9e75c4661d651fac7b328ec98b9c276f36640ffe74ea82692bff7745|1",
      "line": 228,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "get_db_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|load_known_characters|a17bf50850d526d5abbc51d03a1469595001b961b2760993b99467d62a169ccb|1",
      "line": 252,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "load_known_characters"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|get_chunks_to_process|726451ba3d00cb14e77759a8090d2df846e8abde98df40a9afebd0c8f3e4f7e4|1",
      "line": 327,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "get_chunks_to_process"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "scripts/process_characters.py|get_llm_structured_response|b31bb64e29437a6ddc0c303afaae02fe02474844cadd0cb4d01e218b797dd6d1|1",
      "line": 379,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|get_llm_structured_response|7cf30ec6fb12fd83c131efed73e951facb0ae23e9b67a6a6f15c6d4a20411621|1",
      "line": 383,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "scripts/process_characters.py|get_llm_structured_response|66ac81c28ddc34e1be0aaba5b9d89b7d90cac96fb3572d8b792fcbd170149a60|1",
      "line": 515,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|get_llm_structured_response|dd7832d1aecd168382625a342780cc138df2fe24f91028a96c6b45eed2846c36|1",
      "line": 553,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|get_llm_structured_response|fca218bff8bc10955d53019798f4159a7f480ccd008113ca5f17292663c5ad1d|1",
      "line": 566,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|get_llm_structured_response|145a978ba2ce8d152e07c47c2233ebc192c704c1e44c2c9af53333b38a546457|1",
      "line": 605,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "get_llm_structured_response"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|add_new_character|d294c14a306049551c1f807693bae559e77900ac3a866f89a924fa4a5fff76fa|1",
      "line": 688,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "add_new_character"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|add_new_character|a3763d3d69d8e9135424ceab668b6f618ff9743f15b113f38922acde7c6727c4|1",
      "line": 694,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "add_new_character"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|add_aliases_to_character|ae4dc79623c5ab7cff43625fdb7ffa9d3d4b98c0d34454f83c091ad61bddafeb|1",
      "line": 775,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "add_aliases_to_character"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|add_aliases_to_character|335929d829463ccd58abd20aced0ff7fef766072037198da41626613cc6b88b5|1",
      "line": 781,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "add_aliases_to_character"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|update_chunk_metadata|b77c4f7462490edf0abd16842cabe5318afd62d24d8ee4a46ccb1f90bf4a8489|1",
      "line": 890,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "update_chunk_metadata"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|update_chunk_metadata|0a82db2e7c7ee18ccc71d4b28ce3b31167797cdb1a0cca13f912a725b09d1c49|1",
      "line": 896,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "update_chunk_metadata"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|process_chunk|4bb63c2bb2fbbee0a15ed6a6dbbbedbef370329c7edf08d37eb0173e50aeb4f7|1",
      "line": 936,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|process_chunk|fbb495bfc7f8bf6a1d9de60b5faa5cd406a6945f3e1147ba1391824b41d5f81a|1",
      "line": 957,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/process_characters.py|process_chunk|f884cc89a8b08e589f3c01210617b2b48bcf6205be4aed74e03cedbdf41f44aa|1",
      "line": 1269,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "EOFError",
      "identity": "scripts/process_characters.py|process_chunk|eba4bab95c8a817e3309d060f04da4ed5864e383e8b9853b18be8bb5fa41784b|1",
      "line": 1271,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "EOFError",
      "identity": "scripts/process_characters.py|process_chunk|515fd94d3fd5bff43e6a21a419f367902e1228034c26da162a44240e84b05462|1",
      "line": 1322,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "EOFError",
      "identity": "scripts/process_characters.py|process_chunk|887626ea042bc7cfcd14c2d207f22b1cd1e20d4c75c210b8d239765fd6c18d1e|1",
      "line": 1457,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "EOFError",
      "identity": "scripts/process_characters.py|process_chunk|2f8afbbad335695f16d6cb84ea654ed991b15c6e4cb697ef51b2b25405c3dc5d|1",
      "line": 1525,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "process_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|main|0d83d6bb90a40098cd18baca34e97cfd2e3020e5c352ff350b24cbe166b41960|1",
      "line": 1555,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|main|794719a3b9d7c38223c7ed351b22a89c3b8db1f2d3515a303f2406d07c04bb79|1",
      "line": 1569,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|main|fdec43c4ebc0592e13ef3599d234b698c6c57781f5aa99255c0ca879f946f3dd|1",
      "line": 1579,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|main|401a67fd70212216550fd61619f2d6d4f7c26374aba658c55872d95943e83f08|1",
      "line": 1608,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ImportError, ValueError)",
      "identity": "scripts/process_characters.py|main|8210ea0da73cd5405bf5cf88e67f4f436039d27206de5c20e69bcc38bdb86b47|1",
      "line": 1615,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|main|3e469c3d88934a6a1bad6a7aad52f240f6e5c36782f98e44c2ce8a39e7a66eb5|1",
      "line": 1624,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|main|0485b4617c0352652201f12d440ba72d9d3e9567a4b8e8f78bccf7ee5d437978|1",
      "line": 1669,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_characters.py|main|f05ae1cdd21952783fc96176cf0a30d85e60e71bdeb045238eca390b7ac9d122|1",
      "line": 1743,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "EOFError",
      "identity": "scripts/process_characters.py|main|a87876e247760e051d282babdbd52631c6540b5fefa26d0982ae0f43523a1b27|1",
      "line": 1781,
      "marker": null,
      "path": "scripts/process_characters.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_factions.py|get_db_connection|4764daab1623e6215aa04177a4031953d71023341bacb6de10caa1337b15190f|1",
      "line": 90,
      "marker": null,
      "path": "scripts/process_factions.py",
      "scope": "get_db_connection"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_factions.py|get_faction_roster|3cf0b56fa0f097797b2abc032a6014cf0bd0acb8cd0fd02b6ad519ae2ffa853e|1",
      "line": 110,
      "marker": null,
      "path": "scripts/process_factions.py",
      "scope": "get_faction_roster"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_factions.py|get_chunks_to_process|9097366b7bdd9c0ec84c070f57aa348180bf7a9ba7af02f6e909e22904ea57c1|1",
      "line": 133,
      "marker": null,
      "path": "scripts/process_factions.py",
      "scope": "get_chunks_to_process"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_factions.py|get_chunk_with_context|36bbdb98c26a1061c3826b3a30fa1822365ea652c8d7c1baee37dd940306d3c3|1",
      "line": 194,
      "marker": null,
      "path": "scripts/process_factions.py",
      "scope": "get_chunk_with_context"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/process_factions.py|save_faction_references|5a1505efcbd7ff511251c4a20dd320f84ca46314e8dbbaf886e28b4a854f31c0|1",
      "line": 238,
      "marker": null,
      "path": "scripts/process_factions.py",
      "scope": "save_faction_references"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/process_factions.py|call_openai_api|cddb1425366880c1a2fe8b0645649f081f61aa02dc199835bcbfba704a609571|1",
      "line": 355,
      "marker": null,
      "path": "scripts/process_factions.py",
      "scope": "call_openai_api"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/process_factions.py|process_chunks|e28075fc429a61ec86d688de2536e2c9105a9579fc43c837c5b789a4fe5f3889|1",
      "line": 432,
      "marker": null,
      "path": "scripts/process_factions.py",
      "scope": "process_chunks"
    },
    {
      "ast_exempt": true,
      "caught_type": "(OSError, tomllib.TOMLDecodeError)",
      "identity": "scripts/qa_shift/qa_shift.py|load_shift_config|64b3fd5c05621fcf7aaf2ba2b6451675baa729fb235aa6f7c454a0cde2ebdd84|1",
      "line": 148,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "load_shift_config"
    },
    {
      "ast_exempt": true,
      "caught_type": "FileNotFoundError",
      "identity": "scripts/qa_shift/qa_shift.py|_read_usage|10fa9a32d6e3f37f3d40ffb3d2a964ee8a9637ab33f22ffecd9b818cdd26509c|1",
      "line": 213,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_read_usage"
    },
    {
      "ast_exempt": true,
      "caught_type": "json.JSONDecodeError",
      "identity": "scripts/qa_shift/qa_shift.py|_read_usage|f80209ff08bd54ac164537a8e243132031ecd3d26b6697d4f2d56c78ac1506ff|1",
      "line": 223,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_read_usage"
    },
    {
      "ast_exempt": true,
      "caught_type": "FileNotFoundError",
      "identity": "scripts/qa_shift/qa_shift.py|_read_jobs|10fa9a32d6e3f37f3d40ffb3d2a964ee8a9637ab33f22ffecd9b818cdd26509c|1",
      "line": 242,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_read_jobs"
    },
    {
      "ast_exempt": true,
      "caught_type": "json.JSONDecodeError",
      "identity": "scripts/qa_shift/qa_shift.py|_read_jobs|c24f258d194358fbc0862624d1557dfde8daa3aebd32d50c2ac414911fd6d3a8|1",
      "line": 252,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_read_jobs"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "scripts/qa_shift/qa_shift.py|_jobs_snapshot.validate_job|6e6c988ee60192f0990cbd91d87899e9d7dc03d21b3f61ac5f439291f1a97751|1",
      "line": 437,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_jobs_snapshot.validate_job"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "scripts/qa_shift/qa_shift.py|_parse_utc|0b36fb47d3305d8930f28373737d4bea495f48c6b55ef6dd36f35c80e90a6e72|1",
      "line": 733,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_parse_utc"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileExistsError",
      "identity": "scripts/qa_shift/qa_shift.py|_new_archive|e93512d3cbbc63010fb2eba0c5b87f2ec651ce3a43262a785f3496373a5f7cd5|1",
      "line": 762,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_new_archive"
    },
    {
      "ast_exempt": true,
      "caught_type": "ShiftError",
      "identity": "scripts/qa_shift/qa_shift.py|_write_runtime_config|7d25a1a77520047698606eea1b8a92e6543866525e93185b079a0360bec8d132|1",
      "line": 813,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_write_runtime_config"
    },
    {
      "ast_exempt": true,
      "caught_type": "(KeyError, OSError, TypeError, tomlkit.exceptions.ParseError)",
      "identity": "scripts/qa_shift/qa_shift.py|_write_runtime_config|a15792d4c5b6bbcf232aebdbeeabaaab8217c91ee7aa46ce17825a5f36d3f692|1",
      "line": 815,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_write_runtime_config"
    },
    {
      "ast_exempt": true,
      "caught_type": "(OSError, TypeError)",
      "identity": "scripts/qa_shift/qa_shift.py|_write_runtime_config|1a1bfde0b78ce2329a65186c8485427d49469113bc077daafdb2701286cd9ac8|1",
      "line": 821,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_write_runtime_config"
    },
    {
      "ast_exempt": true,
      "caught_type": "(OSError, json.JSONDecodeError)",
      "identity": "scripts/qa_shift/qa_shift.py|_load_state|7636a7c989bb6463a59fdb692599d9c98f616161f15a2e26fbde8cf866223042|1",
      "line": 961,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_load_state"
    },
    {
      "ast_exempt": true,
      "caught_type": "(OSError, UnicodeError)",
      "identity": "scripts/qa_shift/qa_shift.py|_read_validation_evidence|c91a7665a39bc2e71e4f46284781e2152a0273316d80407694156fbe69649bc7|1",
      "line": 1006,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "_read_validation_evidence"
    },
    {
      "ast_exempt": false,
      "caught_type": "ShiftError",
      "identity": "scripts/qa_shift/qa_shift.py|main|4fb26ec4cd56a786a25786e4dd8faf0397a5fa4464446229dd87e2503586525b|1",
      "line": 1533,
      "marker": null,
      "path": "scripts/qa_shift/qa_shift.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/query_narratives_simple.py|main|33c22b44c18f362cae9613bb3e7f027de0fbf511fb59fec9812634dbcb249422|1",
      "line": 70,
      "marker": null,
      "path": "scripts/query_narratives_simple.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/query_narratives_vector.py|<module>|fc6a1b9dc37c52773d0025e16c4e07924d3e290e4f3197c366d2045ab4c7fe42|1",
      "line": 36,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/query_narratives_vector.py|<module>|31f932a3dfc720fe6b4856f6a41530b76d99685313db2d5af54df22968c06457|1",
      "line": 50,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/query_narratives_vector.py|<module>|bc16a264337aeff2635fc1fde956a58aa7b4a433e53b52b8772394e36ad69515|1",
      "line": 119,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/query_narratives_vector.py|<module>|161eb9b17726b1892799b0a792da432a8348d4f035f1801f68df430cac760742|1",
      "line": 129,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/query_narratives_vector.py|<module>|8eb1de059e07a121c9f1ecdeba1bdc137c9ff01ae6e1312dae03b070b40e8100|1",
      "line": 138,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/query_narratives_vector.py|NarrativeSearcher._check_pgvector|b64340246b41c33a17b4c762c049975d928645082cd871c89541b7febcb561e8|1",
      "line": 194,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "NarrativeSearcher._check_pgvector"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/query_narratives_vector.py|NarrativeSearcher.semantic_search|ecd6081464931ac7b96d878a49af9d50240683114e6501db0886d9120234a61f|1",
      "line": 237,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "NarrativeSearcher.semantic_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "<bare>",
      "identity": "scripts/query_narratives_vector.py|NarrativeSearcher.semantic_search|8b45aeb9105f690ebae0c255b5d1af528c44b2861367e190c373c64befedb0bf|1",
      "line": 319,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "NarrativeSearcher.semantic_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/query_narratives_vector.py|NarrativeSearcher.semantic_search|f80784422e7804e9f6bd306f12b8e8dc86da88396151f3d210e0f95480eeb55f|1",
      "line": 336,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "NarrativeSearcher.semantic_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "<bare>",
      "identity": "scripts/query_narratives_vector.py|NarrativeSearcher.text_search|8b45aeb9105f690ebae0c255b5d1af528c44b2861367e190c373c64befedb0bf|1",
      "line": 395,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "NarrativeSearcher.text_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/query_narratives_vector.py|NarrativeSearcher.text_search|1b5853f9e31d16c327eefee0061f6c0e6b73943dc2419c6e6e0947b19f1b9720|1",
      "line": 411,
      "marker": null,
      "path": "scripts/query_narratives_vector.py",
      "scope": "NarrativeSearcher.text_search"
    },
    {
      "ast_exempt": false,
      "caught_type": "AmbiguousCommit",
      "identity": "scripts/rebuild_memory_idf.py|rebuild_database|90c8eb2f198d9bcb4d40693d88fb3ef452ab09d178eb75e5c72897f6c9f01d83|1",
      "line": 417,
      "marker": null,
      "path": "scripts/rebuild_memory_idf.py",
      "scope": "rebuild_database"
    },
    {
      "ast_exempt": false,
      "caught_type": "(IDFRebuildError, psycopg2.Error)",
      "identity": "scripts/rebuild_memory_idf.py|rebuild_database|6de995a8a2c7dea6d6a87722640ad08f67d777531c66d50c6ab51887d08aea2f|1",
      "line": 421,
      "marker": null,
      "path": "scripts/rebuild_memory_idf.py",
      "scope": "rebuild_database"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/regenerate_embeddings.py|<module>|95c1f1206daa82ecbe7c50b3f125f2887bd08ffe956662136f62bc09c1c906fa|1",
      "line": 68,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|<module>|31f932a3dfc720fe6b4856f6a41530b76d99685313db2d5af54df22968c06457|1",
      "line": 116,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/regenerate_embeddings.py|<module>|bc16a264337aeff2635fc1fde956a58aa7b4a433e53b52b8772394e36ad69515|1",
      "line": 151,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/regenerate_embeddings.py|<module>|161eb9b17726b1892799b0a792da432a8348d4f035f1801f68df430cac760742|1",
      "line": 161,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|ModelLoader.get_embedding|ac1ea5fe65eece549530ee81115031e5bcf5932183cf845d4c5b8467f91cd3b1|1",
      "line": 272,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "ModelLoader.get_embedding"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ImportError, RuntimeError)",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.__init__|56cf98781a2cdd48fd526f8b0cce4ddb592696510c2429720931e978a6cecc1a|1",
      "line": 324,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.__init__"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.__init__|314c0dabb8b68f65f947a36b4ecfe613de55376f696cbcc8a45274f7ce132b94|1",
      "line": 342,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.__init__"
    },
    {
      "ast_exempt": false,
      "caught_type": "<bare>",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.__init__|8b45aeb9105f690ebae0c255b5d1af528c44b2861367e190c373c64befedb0bf|1",
      "line": 382,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.__init__"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.__init__|60d4556e918516f37721851699b95ab35ff1274af03c9131b3176b8daaae6fc9|1",
      "line": 414,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.__init__"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator._ensure_dimension_table_exists|b9a4bce6f249ba9f964a81c23f2e7e28a14135b136d0df8979d9ee22bce71022|1",
      "line": 456,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator._ensure_dimension_table_exists"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.get_all_chunks|9d7817df1f6853b5f3313d5df1cd8a351baca4e16a3550848ad5080278476dab|1",
      "line": 498,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.get_all_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.delete_existing_embeddings|6b79b5e2ad433080cb4e6aff26fb9c265698382b9f093f8747146c2d5185eae2|1",
      "line": 559,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.delete_existing_embeddings"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.store_embedding_batch|4e691a235ea6d90d24c8cdf49afd3dbb8e6a62046515facb48459f32d010ab4f|1",
      "line": 621,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.store_embedding_batch"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.store_embedding_batch|2e0689182ecd1a30424c9945d482bcce415a080574702a16bbe097db68725298|1",
      "line": 675,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.store_embedding_batch"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.store_embedding_batch|e406e392d2c80f38a00ad48f00393a23948a60714f1ae70e5b14b14a98722244|1",
      "line": 704,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.store_embedding_batch"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.create_vector_indexes|a678ffbd6da76dc08463075c908911ed19888345f8674762da154733b81ea303|1",
      "line": 762,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.create_vector_indexes"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.create_vector_indexes|5134fbfa21d844d7b590a3809b00ec0f992215a48cb860628fcb13359699df9b|1",
      "line": 785,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.create_vector_indexes"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|EmbeddingRegenerator.regenerate_all_embeddings|7a37396a333d82239ba882db1cec2eeb37c124217bf49953a79a5c6a3b8f1cb6|1",
      "line": 895,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "EmbeddingRegenerator.regenerate_all_embeddings"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|regenerate_all_models|3ced488116ce72b76c7e091450e68759ade1ef11a3d5e224384884302c9bc8d1|1",
      "line": 1065,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "regenerate_all_models"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ImportError, RuntimeError)",
      "identity": "scripts/regenerate_embeddings.py|regenerate_missing_chunks|8533bd88d5e45e39e61216b3ff71abae5d69ed2aa3a0b14b281db46f0d085c81|1",
      "line": 1114,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "regenerate_missing_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|regenerate_missing_chunks|7a37396a333d82239ba882db1cec2eeb37c124217bf49953a79a5c6a3b8f1cb6|1",
      "line": 1194,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "regenerate_missing_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|regenerate_missing_chunks|d77edf212beb3589914b0a83769436367fb0ed4cde1e294160f910d657376059|1",
      "line": 1211,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "regenerate_missing_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ImportError, RuntimeError)",
      "identity": "scripts/regenerate_embeddings.py|delete_existing_chunk_embedding|8533bd88d5e45e39e61216b3ff71abae5d69ed2aa3a0b14b281db46f0d085c81|1",
      "line": 1245,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "delete_existing_chunk_embedding"
    },
    {
      "ast_exempt": false,
      "caught_type": "OSError",
      "identity": "scripts/regenerate_embeddings.py|regenerate_specific_chunk|92138126e742113854e94a61a027f692544b222c75392ea737c8c1e4c2d3afec|1",
      "line": 1357,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "regenerate_specific_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|main|3f6e4d7f90bb0c8109a2f7e7db574075a3b20a9cdd9906de9e74a1300ab6428b|1",
      "line": 1419,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/regenerate_embeddings.py|main|631058e0c16be74b9d002fcb70895bd13151c76990a591700a568b81ff6246c9|1",
      "line": 1604,
      "marker": null,
      "path": "scripts/regenerate_embeddings.py",
      "scope": "main"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "scripts/register_drift_study.py|_parse_slots|bdd56bf908b200ed4aa08920b8db6aa0031c369c23801428c22fe29ad5d9bd3b|1",
      "line": 1822,
      "marker": null,
      "path": "scripts/register_drift_study.py",
      "scope": "_parse_slots"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "scripts/retrieval_query_bakeoff.py|_result_chunk_id|8dca1ca5004730bc25e16f3c74797730000ffa88e7fa4386c72d53f9d32590dd|1",
      "line": 189,
      "marker": null,
      "path": "scripts/retrieval_query_bakeoff.py",
      "scope": "_result_chunk_id"
    },
    {
      "ast_exempt": false,
      "caught_type": "json.JSONDecodeError",
      "identity": "scripts/retrieval_query_bakeoff.py|_coerce_directives|2d3f7d119d3fe7eb5888a25592938674a66be1938b24880ace1164db2ebd96c8|1",
      "line": 197,
      "marker": null,
      "path": "scripts/retrieval_query_bakeoff.py",
      "scope": "_coerce_directives"
    },
    {
      "ast_exempt": false,
      "caught_type": "(TypeError, ValueError)",
      "identity": "scripts/retrieval_query_bakeoff.py|_sqlite_judgments|ff4cccac669b8e93ae7f5c5607359a13d2277cd6d74ffa97a17c4aea9563f618|1",
      "line": 785,
      "marker": null,
      "path": "scripts/retrieval_query_bakeoff.py",
      "scope": "_sqlite_judgments"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/run_golden_queries.py|run_golden_queries|92b13c60a72b2c06d82849925d2927dd1c809a6aa9af8d5dc4077beb206fc126|1",
      "line": 271,
      "marker": null,
      "path": "scripts/run_golden_queries.py",
      "scope": "run_golden_queries"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/run_golden_queries.py|run_golden_queries|adcb4ceada7f081ca79f0a53f62879fe95b1bb8614263a2252c8c2249faec84f|1",
      "line": 307,
      "marker": null,
      "path": "scripts/run_golden_queries.py",
      "scope": "run_golden_queries"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/run_golden_queries.py|run_golden_queries|11e9e5984ac826045b27a4259abf36a956ae2059a47fcd9ec2dbf18727f06ef8|1",
      "line": 348,
      "marker": null,
      "path": "scripts/run_golden_queries.py",
      "scope": "run_golden_queries"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValueError, TypeError)",
      "identity": "scripts/run_golden_queries.py|run_golden_queries|c55e6ee8c739d0dd80be160300cba61bc421e3d8eff916bfbb58409401742b90|1",
      "line": 428,
      "marker": null,
      "path": "scripts/run_golden_queries.py",
      "scope": "run_golden_queries"
    },
    {
      "ast_exempt": false,
      "caught_type": "(ValueError, TypeError)",
      "identity": "scripts/run_golden_queries.py|run_golden_queries|4eccedcae835d2bd1853dc3eef3fc69cf7b40ec375560c41ea2d171d597e6b0c|1",
      "line": 438,
      "marker": null,
      "path": "scripts/run_golden_queries.py",
      "scope": "run_golden_queries"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/run_golden_queries.py|run_golden_queries|bae157612850f41ef89fd3ffd8c9cff44ebd9a96ea6927a4cc9b753f3ce993ee|1",
      "line": 461,
      "marker": null,
      "path": "scripts/run_golden_queries.py",
      "scope": "run_golden_queries"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/run_golden_queries.py|run_golden_queries|fb002aad36826dc973a74dadbb19c28ffd449037ef59fe8a4769ff4b718297fc|1",
      "line": 491,
      "marker": null,
      "path": "scripts/run_golden_queries.py",
      "scope": "run_golden_queries"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/run_golden_queries.py|run_golden_queries|392ac2a0ba2004fa55b88ee896153fed73463cf8f503899b8bf2cd491d65edbe|1",
      "line": 501,
      "marker": null,
      "path": "scripts/run_golden_queries.py",
      "scope": "run_golden_queries"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/simple_update.py|<module>|52108ced8b6e1f8aca26b0daee8cc0dc9e2c332b74bea4457638c7d32febf5b9|1",
      "line": 49,
      "marker": null,
      "path": "scripts/simple_update.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/simple_update.py|update_chunk|ee01d576503f5a2a6bc8d3ee2602a94d0b3babb1e026aaaa260b9bf3e317a75b|1",
      "line": 330,
      "marker": null,
      "path": "scripts/simple_update.py",
      "scope": "update_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/simple_update.py|ensure_all_chunks_have_metadata|1410962cf2082f0bbf248ec1b42c17a6c072ce7a3601f63edee88ad190f14546|1",
      "line": 443,
      "marker": null,
      "path": "scripts/simple_update.py",
      "scope": "ensure_all_chunks_have_metadata"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/simple_update.py|resequence_all_chunks|cf9551ab6adf06c856a30b58bff0e38c4b7116bed8e7ff475b33be98a5ab8e8a|1",
      "line": 771,
      "marker": null,
      "path": "scripts/simple_update.py",
      "scope": "resequence_all_chunks"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/simple_update.py|reorganize_chunk_ids|db21731cec91ee3b33ab3514854286430a2c8d5272b15e2de9251c97ccb28a5c|1",
      "line": 859,
      "marker": null,
      "path": "scripts/simple_update.py",
      "scope": "reorganize_chunk_ids"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/simple_update.py|create_chunk|f3fc68cd4e9143597a32804e2e4fb8796380a85ff46054130dbedc1debcd4253|1",
      "line": 941,
      "marker": null,
      "path": "scripts/simple_update.py",
      "scope": "create_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/simple_update.py|main|3a8ae01aaf66385552150ea7efdbd9718cb98577356e8aa841539af52fcc2b4c|1",
      "line": 1086,
      "marker": null,
      "path": "scripts/simple_update.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|DatabaseManager.get_previous_season_summaries|01a9f6a260a0118dbadb82f65168d5d5366585dc4998c184912b4ab72214a65f|1",
      "line": 725,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "DatabaseManager.get_previous_season_summaries"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|DatabaseManager.get_previous_episode_summaries|96ec8a2500cd2c1d5d428182f52781385cda10f180ad0c7eb57107aec9e9c225|1",
      "line": 776,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "DatabaseManager.get_previous_episode_summaries"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|DatabaseManager.episode_summary_exists|17bf33b790244cd3e2b5b94ab033a1c4840c2890616b891347f263aa947ceb67|1",
      "line": 810,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "DatabaseManager.episode_summary_exists"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|DatabaseManager.get_season_summary|69cb2081ddcbb795e6cfd72d1ae5a9680f496ca57d33865f8fd33b79f34727c7|1",
      "line": 845,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "DatabaseManager.get_season_summary"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|DatabaseManager.season_summary_exists|c653432151e7e98124e9acd3fa30a14614877d4a19939b77836c1d7c30507f77|1",
      "line": 874,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "DatabaseManager.season_summary_exists"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|DatabaseManager.save_season_summary|e2391892019ab110aa3abba94dd004a91280eb08e4b3e70bf22cca8ee6bc5537|1",
      "line": 990,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "DatabaseManager.save_season_summary"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|DatabaseManager.save_episode_summary|f5b2671106a87c8ff70ab6d07ccc2ca1cf7c1c68f06a3c6089dfa366b6200d54|1",
      "line": 1154,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "DatabaseManager.save_episode_summary"
    },
    {
      "ast_exempt": true,
      "caught_type": "ValueError",
      "identity": "scripts/summarize_narrative.py|SummaryGenerator._model_rejects_temperature|8d41946435ee2b1bc7785ec0497b8a50d79ae24fb0761e201e8fb9bdbca69d7d|1",
      "line": 1317,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "SummaryGenerator._model_rejects_temperature"
    },
    {
      "ast_exempt": true,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|SummaryGenerator._initialize_provider|c628fdde11e097ecbc3a44490c17da7d50ade050d863736c82aeeaa7ec10e259|1",
      "line": 1359,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "SummaryGenerator._initialize_provider"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|SummaryGenerator._save_prompt_to_file|d0f676d5c1f07ba3ff9f6f75ba5df648b61a7a36fc643bde7f9e897c8d4e3b38|1",
      "line": 1494,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "SummaryGenerator._save_prompt_to_file"
    },
    {
      "ast_exempt": true,
      "caught_type": "(SummaryInputTooLong, SummaryOutputTruncated)",
      "identity": "scripts/summarize_narrative.py|SummaryGenerator.generate_season_summary|68a9bb2907815831dc6f9fd8a384f7ad64f997f5e0463d16301bedd53d3171bf|1",
      "line": 1615,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "SummaryGenerator.generate_season_summary"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|SummaryGenerator.generate_season_summary|f0c69c9780cadf2b990d0503c3da6348db956fcbd924b618b13dfb2b5ed14762|1",
      "line": 1617,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "SummaryGenerator.generate_season_summary"
    },
    {
      "ast_exempt": true,
      "caught_type": "(SummaryInputTooLong, SummaryOutputTruncated)",
      "identity": "scripts/summarize_narrative.py|SummaryGenerator.generate_episode_summary|68a9bb2907815831dc6f9fd8a384f7ad64f997f5e0463d16301bedd53d3171bf|1",
      "line": 1803,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "SummaryGenerator.generate_episode_summary"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|SummaryGenerator.generate_episode_summary|c47877c9c1f4e89b9afa0fafe7c8cd88cf227db9a8a07498363537ff92158972|1",
      "line": 1805,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "SummaryGenerator.generate_episode_summary"
    },
    {
      "ast_exempt": true,
      "caught_type": "(SummaryInputTooLong, SummaryOutputTruncated)",
      "identity": "scripts/summarize_narrative.py|SummaryGenerator.generate_chunk_range_summary|68a9bb2907815831dc6f9fd8a384f7ad64f997f5e0463d16301bedd53d3171bf|1",
      "line": 2148,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "SummaryGenerator.generate_chunk_range_summary"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|SummaryGenerator.generate_chunk_range_summary|399ba3eda846b8961f2795dac5687b340fe4ebeeedc4b0452ef92438239954c5|1",
      "line": 2150,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "SummaryGenerator.generate_chunk_range_summary"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/summarize_narrative.py|SummaryGenerator._get_last_episode_of_season|9c06cca0208765fa589b9a5d8fcaf5d71182459301e869abfb7432abf5c548b4|1",
      "line": 2176,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "SummaryGenerator._get_last_episode_of_season"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/summarize_narrative.py|main|105fdad30a1f04b28f8046b98244b30c0cde96c1d943f2419a9723c14b75e006|1",
      "line": 2385,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "ValueError",
      "identity": "scripts/summarize_narrative.py|main|b28583a04829ce2e1f425cad0b488e1b19b777ca06503631e1fb79d06a453f9a|1",
      "line": 2425,
      "marker": null,
      "path": "scripts/summarize_narrative.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "FileNotFoundError",
      "identity": "scripts/sync_secrets.py|fetch_from_1password|e375ad2eede8bf1d0511f17a69d4d0ffd2e3ad28d5de54df5a81fc1905861ca4|1",
      "line": 68,
      "marker": null,
      "path": "scripts/sync_secrets.py",
      "scope": "fetch_from_1password"
    },
    {
      "ast_exempt": false,
      "caught_type": "subprocess.CalledProcessError",
      "identity": "scripts/sync_secrets.py|fetch_from_1password|722853120c86ae8f7fac555eecb2d89922382533c85b9d71f4b0171bc43311c8|1",
      "line": 70,
      "marker": null,
      "path": "scripts/sync_secrets.py",
      "scope": "fetch_from_1password"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/sync_secrets.py|verify|aa1e7fabc499ca807156e276e7ab965523eff87a74dca868d595b8c52dc3c0c0|1",
      "line": 92,
      "marker": null,
      "path": "scripts/sync_secrets.py",
      "scope": "verify"
    },
    {
      "ast_exempt": false,
      "caught_type": "requests.exceptions.ConnectionError",
      "identity": "scripts/test_narrative_api.py|main|8ac93bb73d50daacd1e9ca8fdc1ed80a1508ab8eb3def1a467356cae0927a30c|1",
      "line": 192,
      "marker": null,
      "path": "scripts/test_narrative_api.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/test_narrative_api.py|main|cee8217941eecbc6034ed31b6d51250d2c8dbd3fe2db4efc7a2a6336b1a9eb51|1",
      "line": 195,
      "marker": null,
      "path": "scripts/test_narrative_api.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/test_setup_flow.py|test_setup_flow|fe3a78dec0de29a9b4e2a7022f48f0136d4ec776615e64fecb047f35a7d1f248|1",
      "line": 24,
      "marker": null,
      "path": "scripts/test_setup_flow.py",
      "scope": "test_setup_flow"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/test_setup_flow.py|test_setup_flow|0a7150ae02ee289aa55f81999e740199ebb5dac4a3d10cef4bb8b727a701890c|1",
      "line": 76,
      "marker": null,
      "path": "scripts/test_setup_flow.py",
      "scope": "test_setup_flow"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/token_counter.py|read_file_with_fallback|662c2bc6b711691fbaad29c08c2d8eac755de9c0d6c3446741920296119028bb|1",
      "line": 40,
      "marker": null,
      "path": "scripts/token_counter.py",
      "scope": "read_file_with_fallback"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/token_counter.py|read_file_with_fallback|746f9aacf8bf1dcae7925f8701c2133f9ce22537476e574e7f908ff132be418f|1",
      "line": 44,
      "marker": null,
      "path": "scripts/token_counter.py",
      "scope": "read_file_with_fallback"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/token_counter.py|read_file_with_fallback|d785294cb93f040ff92c05ad319ff676ae8369ab4a18ef2933baae7c5c29a26b|1",
      "line": 69,
      "marker": null,
      "path": "scripts/token_counter.py",
      "scope": "read_file_with_fallback"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/token_counter.py|read_file_with_fallback|c9ac6c70670be57523a6d5095731bb453b3b66d1a454e4d361f9a6071d9db00b|1",
      "line": 73,
      "marker": null,
      "path": "scripts/token_counter.py",
      "scope": "read_file_with_fallback"
    },
    {
      "ast_exempt": false,
      "caught_type": "UnicodeDecodeError",
      "identity": "scripts/token_counter.py|read_file_with_fallback|588d3487e1a24d1dcb97590582253f3c2a465cc5224ebc08c130bf5e36210c4a|1",
      "line": 80,
      "marker": null,
      "path": "scripts/token_counter.py",
      "scope": "read_file_with_fallback"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/token_counter.py|read_file_with_fallback|7d47c3bb7f1fca5649e510465f7d3292ae139f87c0b9550dfe92d06edf7b52d9|1",
      "line": 88,
      "marker": null,
      "path": "scripts/token_counter.py",
      "scope": "read_file_with_fallback"
    },
    {
      "ast_exempt": false,
      "caught_type": "UnicodeDecodeError",
      "identity": "scripts/token_counter.py|read_file_with_fallback|ea91139362d40f37721f2e4dd477c39da86c9b308c8f4f906d17e7608c61688b|1",
      "line": 96,
      "marker": null,
      "path": "scripts/token_counter.py",
      "scope": "read_file_with_fallback"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/token_counter.py|read_file_with_fallback|d8465070b3ec75ba78f11d97fb2518c1b8ce25a6fc88d69c7e10c3b06da31097|1",
      "line": 102,
      "marker": null,
      "path": "scripts/token_counter.py",
      "scope": "read_file_with_fallback"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/trim_oversized_contexts.py|main|d31612fefae51a3961d2a906052ad1edeaae87e97a9efe28a1991e1c4b3696c7|1",
      "line": 263,
      "marker": null,
      "path": "scripts/trim_oversized_contexts.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "ImportError",
      "identity": "scripts/update_raw_text.py|<module>|bc16a264337aeff2635fc1fde956a58aa7b4a433e53b52b8772394e36ad69515|1",
      "line": 47,
      "marker": null,
      "path": "scripts/update_raw_text.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/update_raw_text.py|<module>|45a7cc215dc3317c04a54b7512bd76c615f46d70e363569693e4009e1ca63ee3|1",
      "line": 57,
      "marker": null,
      "path": "scripts/update_raw_text.py",
      "scope": "<module>"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/update_raw_text.py|ChunkUpdater.create_backup_table|de8a2f7813802f44f926c0d9d67591c23f64f942f9e44af5f8b6ac8f04c2f6da|1",
      "line": 137,
      "marker": null,
      "path": "scripts/update_raw_text.py",
      "scope": "ChunkUpdater.create_backup_table"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/update_raw_text.py|ChunkUpdater.update_chunk_raw_text|d0c5977572196cafd6981eddebb16c6f4ce6ee3034e63d32163a9235b6c3e970|1",
      "line": 296,
      "marker": null,
      "path": "scripts/update_raw_text.py",
      "scope": "ChunkUpdater.update_chunk_raw_text"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/update_raw_text.py|ChunkUpdater.reorganize_chunk_ids|b5644add8a0c2a5657d185aa0ae084e4c19853e6d48363d8f4819d77b23d7dde|1",
      "line": 630,
      "marker": null,
      "path": "scripts/update_raw_text.py",
      "scope": "ChunkUpdater.reorganize_chunk_ids"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/update_raw_text.py|ChunkUpdater.reorganize_chunk_ids|f39a1d859094ce8c2ccbf4f58a014e23ac4c39168a82b47041a91cfe811e5e01|1",
      "line": 640,
      "marker": null,
      "path": "scripts/update_raw_text.py",
      "scope": "ChunkUpdater.reorganize_chunk_ids"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/update_raw_text.py|ChunkUpdater.create_new_chunk|2cac25fe71996aca1b56e16ba7864ee674cd675502347e7246d571bdf6c34020|1",
      "line": 758,
      "marker": null,
      "path": "scripts/update_raw_text.py",
      "scope": "ChunkUpdater.create_new_chunk"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/update_raw_text.py|ChunkUpdater.process_files|0e6408e2253d0cf7f57a462aea2f3a8c2abacc259eec5fc34f6c7e00fadda124|1",
      "line": 832,
      "marker": null,
      "path": "scripts/update_raw_text.py",
      "scope": "ChunkUpdater.process_files"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/update_raw_text.py|ChunkUpdater.process_files|7819d29a2ed2d6fb7bdf43a9d85a2b9f246b8b64c5d944a06f4c154375795210|1",
      "line": 842,
      "marker": null,
      "path": "scripts/update_raw_text.py",
      "scope": "ChunkUpdater.process_files"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "scripts/update_scene_numbers.py|connect_to_db|4ef87b1e791b697e14335b7d8cac0dd8b4185b2ca13e1d591666baee1bf28c8d|1",
      "line": 38,
      "marker": null,
      "path": "scripts/update_scene_numbers.py",
      "scope": "connect_to_db"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "scripts/update_scene_numbers.py|add_scene_column_if_not_exists|61337d22cec127200f4d6710690fd39a1c3ef2b0716a6a3c75363a26ce54b049|1",
      "line": 100,
      "marker": null,
      "path": "scripts/update_scene_numbers.py",
      "scope": "add_scene_column_if_not_exists"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "scripts/update_scene_numbers.py|get_chunks_without_scene|ea0e5c36f8b207f5618f83152bcd42fd3fd5867d55a4dc44db54ab195d1a1801|1",
      "line": 123,
      "marker": null,
      "path": "scripts/update_scene_numbers.py",
      "scope": "get_chunks_without_scene"
    },
    {
      "ast_exempt": false,
      "caught_type": "psycopg2.Error",
      "identity": "scripts/update_scene_numbers.py|update_scene_numbers|5b159e8efea8bfb888b8ea049daff2111450dba00956e1825c4e17099c735230|1",
      "line": 147,
      "marker": null,
      "path": "scripts/update_scene_numbers.py",
      "scope": "update_scene_numbers"
    },
    {
      "ast_exempt": true,
      "caught_type": "(subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError)",
      "identity": "scripts/validate_config_commit.py|validate_tokenizer_registry|4f0814c7d5220d4f21b002922a5ecdfc9bdec1d87065247c157fc2a829d6cf6c|1",
      "line": 75,
      "marker": null,
      "path": "scripts/validate_config_commit.py",
      "scope": "validate_tokenizer_registry"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/validate_config_commit.py|main|fa8cbb923d2da60dd9f2985d8326f055fe342e7b3a984cb77edf20f54a408b3d|1",
      "line": 104,
      "marker": null,
      "path": "scripts/validate_config_commit.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/validate_embeddings.py|main|c206c238809e8420b2ba1517bdd08cbb98d47e8fb69d7806ee06f444f74e358a|1",
      "line": 195,
      "marker": null,
      "path": "scripts/validate_embeddings.py",
      "scope": "main"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/vector_migration.py|migrate_small_embeddings|b7ca145691995f716fc3f2b163f76bc8425e72f1e1d0699e4a9eade549508890|1",
      "line": 146,
      "marker": null,
      "path": "scripts/vector_migration.py",
      "scope": "migrate_small_embeddings"
    },
    {
      "ast_exempt": false,
      "caught_type": "Exception",
      "identity": "scripts/vector_migration.py|create_index|c274d08051e0940b33d634d2aa0935bf1f0327d50de3b0dfca10b87957c8465b|1",
      "line": 203,
      "marker": null,
      "path": "scripts/vector_migration.py",
      "scope": "create_index"
    }
  ]
}
```

Agent: Codex (GPT-6)
