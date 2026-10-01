# Verification: Live Log Rotation Under the Configured Policy (#842 S2, S3)

Work order 842-B. Branch `claude/842-log-rotation`, cut from `origin/main` at
`41783c1d` and rebased onto `e528cc08` (#811 S1) before the final gates below.
No migration, no paid call, no gateway lane: every live test takes
OS-assigned ports.

## The Premise, Checked at `41783c1d`

Each cited line was read with `git show 41783c1d:<path> | sed -n ...`.

- Rotation happens at spawn only. `nexus/runtime/supervisor.py:164-180`
  `_rotate_log` returns early below `max_bytes` (`:173-174`); `_spawn` calls it
  at `:547-549`, then opens `<service>.log` with `"ab"` and hands the handle to
  the child (`:563-564`).
- The text said so: `nexus/config/settings_models.py:635-637` ("rotates that
  file at spawn") and `:675-678` (the `max_bytes` description),
  `nexus.toml:1406-1407` and `:1415`, `nexus/runtime/logging_config.py:3-5`,
  `docs/runtime.md:224-227` ("a long-running service's capture grows until its
  next spawn"), and the supervisor docstrings at `:272`, `:320` and `:961`.
- `scripts/qa_shift/mission_prompt.md:100-101` records "the source log's byte
  offset", `:248-249` copies the gateway log, and `:258-259` mines "the
  gateway-log slice after the recorded byte/PID/time boundary".
- `nexus/api/local_inference.py:466-471` (`activate`) and `:576-578`
  (`start_download`) open `local-model.log` and `local-model.download.log` with
  `"ab"`; `_download_error` reads the last line at `:643-646`; `_logs_dir`
  (`:55-59`) and `_state_dir` (`:48-52`) ignore the `gateway-<port>`
  subdirectory the supervisor adds at `supervisor.py:391-393`.
- `tests/test_api/test_local_inference.py:86`, `:322`, `:358`, `:404-405`,
  `:434` and `:728-729` replaced `local_inference.subprocess.Popen`, the
  global `subprocess` module's attribute.
- `nexus/cli.py:4213-4214` refuses `--json` with `-f`.

Read-only listing of the owner's runtime directory, 2026-09-30 20:44 CDT:

```
-rw-r--r--@ 1 pythagor  staff     23690 Sep 30 18:54 /Users/pythagor/nexus/.nexus/runtime/gateway.log
-rw-r--r--@ 1 pythagor  staff  40140822 Sep 29 09:35 /Users/pythagor/nexus/.nexus/runtime/gateway.log.1
-rw-r--r--@ 1 pythagor  staff       666 Jul 13 13:28 /Users/pythagor/nexus/.nexus/runtime/local-model.download.log
-rw-r--r--@ 1 pythagor  staff    260043 Jul 25 00:46 /Users/pythagor/nexus/.nexus/runtime/local-model.log
-rw-r--r--@ 1 pythagor  staff     61608 Sep 30 18:54 /Users/pythagor/nexus/.nexus/runtime/mock_openai.log
-rw-r--r--@ 1 pythagor  staff     23469 Jul 15 03:32 /Users/pythagor/nexus/.nexus/runtime/slot5_sol_progress.log
```

`gateway.log.1` holds 40,140,822 bytes, 3.8 times `max_bytes = 10485760`.

## Red Runs

Each plant was a scratch edit of the working tree, run, and restored by
copying the saved file back (checked with `cmp`) before the commit.

### Direct `open("ab")` Capture Restored in `_spawn`

The plant replaced the `spawn_captured` call with the pre-change
`open(log_path, "ab")` capture and returned a placeholder pid as the writer.

`test_writer_rotates_a_live_capture_without_losing_lines` (one 8,200-byte
file, no segment):

```
E       AssertionError: assert (1 - 1) >= 8
E        +  where 1 = len([PosixPath('/private/var/folders/r5/zvbnrwp55r7dctnkr9s3b3780000gn/T/pytest-of-pythagor/pytest-2793/test_writer_rotates_a_live_cap0/state/echo.log')])
1 failed, 39 deselected, 5 warnings in 0.52s
```

`test_live_gateway_rotates_and_keeps_every_line`, with a detached `sleep 90`
as the placeholder writer so the test reaches its `.2` poll:

```
>               assert time.monotonic() < deadline, "the live capture never rotated"
E               AssertionError: the live capture never rotated
dbname audit: owner targets: none
1 failed, 12 deselected in 65.63s (0:01:05)
```

### Direct Capture Restored in `activate`

`test_activate_captures_through_the_writer_under_the_policy`:

```
>           assert rotated_segment(log_path, 9).read_bytes() == SEED
E       FileNotFoundError: [Errno 2] No such file or directory: '/private/var/folders/r5/zvbnrwp55r7dctnkr9s3b3780000gn/T/pytest-of-pythagor/pytest-2847/test_activate_captures_through0/state/local-model.log.9'
1 failed, 23 deselected, 7 warnings in 0.63s
```

### Writer Stderr Inherited in `spawn_captured`

`test_spawn_captured_releases_the_callers_stderr` (the writer held the
caller's stderr pipe, so `subprocess.run` never returned):

```
E           subprocess.TimeoutExpired: Command '['/Users/pythagor/nexus/.venv/bin/python', '-c', "import sys\nfrom pathlib import Path\n..."]' timed out after 10 seconds
1 failed, 39 deselected, 5 warnings in 10.31s
```

## Gates

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime
tests/test_runtime_home.py tests/test_api/test_local_inference.py
tests/test_api/test_local_models_endpoints.py tests/test_owner_target_guard.py`
with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_1013_readiness_* x2, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
322 passed, 7 warnings in 108.17s (0:01:48)
```

The first run of that gate failed `test_doctor_ci_runner_passes_on_this_checkout`:
the reachability gate asked for `nexus/runtime/log_capture.py` in the
baseline's production paths (`baseline_add_production_paths`). The baseline
was rewritten with `scripts/check_reachability.py --write-baseline --reason`,
and the gate above is the final run on the rebased branch.

Offline `$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2653 passed, 420 skipped, 8 warnings in 374.07s (0:06:14)
```

(Its first run failed `tests/test_prompt_lint.py::test_python_has_no_embedded_prompt_prose`
on the writer's argparse description; the description was dropped and the
whole suite rerun; the tail above is the final run on the rebased branch.)

Offline `$PY -m pytest -q tests/test_api tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1819 passed, 742 skipped, 7 warnings in 33.47s
```

`$PY -m pytest -q tests/test_reachability.py`:

```
54 passed, 5 warnings in 9.09s
```

## Review Fixes (Commits `b2b4f609` and `df003728`)

Confirmed review findings applied after the gates above:

- `logs_since` and `log_mark` read a half-finished rotation as a complete
  chain. `_open_segments` now treats a segment that exists past the first
  missing one as a rotation in progress and retakes the snapshot every
  `poll_interval_seconds`, raising when the gap outlasts `stop_grace_seconds`;
  `log_mark` waits the same way when the current file is missing while `.1`
  exists, and returns `0:0:0` only when `.1` is absent too. The empty mark's
  `.backup_count` refusal now runs before the snapshot.
- `wait_for_writer` re-checks the writer's identity on each poll when the
  writer is not this process's child, so an exited writer that another live
  parent has not reaped (a zombie) counts as gone instead of timing out into a
  false "outlived its service" error. The caller's own child is still reaped
  by the poll's `waitpid`.
- `test_spawn_captured_releases_the_callers_stderr` records its pids on disk
  before the script exits, so a timed-out run still kills both processes; the
  activation test's disk poll treats the writer's rename gap as "not yet".
- The QA kit paragraph's 109-column line is rewrapped; no words changed.

Red run of the three new tests, with `_open_segments`, `log_mark` and the
`wait_for_writer` loop planted back to their pre-fix logic (restored by copying
the saved files back before the commit):

```
E           AssertionError: assert ['current'] == ['oldest', 'current', 'fresh']
E       Failed: DID NOT RAISE <class 'nexus.runtime.supervisor.RuntimeError_'>
E           AssertionError: assert False is True
E            +  where False = wait_for_writer(59519, PosixPath('<tmp>/logs/brief.log'), 5, 0.1)
FAILED tests/test_runtime/test_supervisor.py::test_logs_since_waits_out_a_rotation_in_progress
FAILED tests/test_runtime/test_supervisor.py::test_logs_since_refuses_a_lasting_gap_in_the_chain
FAILED tests/test_runtime/test_supervisor.py::test_wait_for_writer_returns_for_another_parents_exited_writer
3 failed, 40 deselected, 5 warnings in 6.93s
```

The same PostgreSQL gate command as above, on `df003728`, with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_1013_readiness_* x2, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
325 passed, 7 warnings in 121.44s (0:02:01)
```

(The run of that gate on `b2b4f609` failed
`test_activate_captures_through_the_writer_under_the_policy` at
`assert not pid_alive(writer_pid)`: the first version of the identity
re-check reported the test process's own exited writer gone before reaping
it. `df003728` limits the re-check to writers this process cannot reap.)

`$PY -m pytest -q tests/test_reachability.py tests/test_prompt_lint.py` on
`df003728`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
76 passed, 5 warnings in 22.74s
```

Black on the four changed Python files: `4 files left unchanged.` Flake8 on
them reports nothing; mypy reports only the 9 pre-existing
`nexus/runtime/supervisor.py` errors named below.

The branch does not hold the two slice commits the order asked for (842-S2,
then 842-S3): S2 fixes and the evidence came after the S3 commit, and these
review fixes add two more. Rebuilding it would rewrite published history,
which this fix pass may not do; the coordinator decides.

## Static Checks

Black: `10 files would be left unchanged.` Flake8 on the changed files reports
nothing new: `nexus/cli.py` and `nexus/config/settings_models.py` keep their 9
and 6 pre-existing E501 lines, the same counts as `origin/main`. Mypy: the
changed files are clean except `nexus/runtime/supervisor.py`, which reports 9
pre-existing errors (requests stubs, Windows-only `subprocess` attributes,
optional external/remote settings); `origin/main`'s copy reports 10. The
`validate-config` hook passed on the `nexus.toml` commit.
