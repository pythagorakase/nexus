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
it. `df003728` limits the re-check to writers this process cannot reap.
That fix covered only the poll loop; the identity check before the loop kept
the same race until `102daeef`, below.)

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

## Second Review Fix Pass (Commit `102daeef`)

Confirmed review findings applied on top of `1a869905`:

- `wait_for_writer`'s first identity check could return True for the
  caller's own writer when the writer exited between the first `_reap` and the
  `ps` probe: `ps` saw a zombie whose command no longer names the file, and the
  zombie stayed unreaped (`test_activate_captures_through_the_writer_under_the_policy`
  then fails at `assert not pid_alive(writer_pid)`). The first check now keeps
  the reap's result and reaps once more before that return.
- `_check_children` unlinked an exited service's pidfile before deciding
  whether to respawn, and waited for the writer only on the respawn branch.
  It now waits for each exited record's `log_writer_pid` before the unlink,
  on the `never` and retries-exhausted paths too.
- `_read_active` (llama-server dead after readiness; pid no longer ours) and
  the three early returns of `_deactivate_locked` (no current record, failed,
  ownership lost) unlinked `local-model.pid.json` without waiting for its
  `log_writer_pid`. Each now waits first, so the record never goes while its
  writer can still be live. (The not-ours branch of `_read_active` is the same
  unlink; it is covered with the dead-after-readiness branch.)
- `test_logs_since_waits_out_a_rotation_in_progress` created its fresh file
  with `Path.write_text`, which leaves an empty file for a moment; a mark taken
  in that moment held size 0. The test now writes a staging sibling and
  `os.replace`s it into place.

The activation test and the rotation-in-progress test, 12 runs each on
`102daeef`:

```
run 1: 2 passed, 7 warnings in 3.35s
...
run 12: 2 passed, 7 warnings in 2.92s
(12 of 12 passed)
```

The same 12-run loop of the activation test with `1a869905`'s
`log_capture.py` planted back passed 12 of 12 on this machine, so the race did
not reproduce here under this load; the fix is applied as the reviewer
diagnosed it, not as a reproduced red run.

Two scratch probes (session scratchpad `842-B/fix3/`, not committed), each red
with the `1a869905` file planted back and green on `102daeef`:

`test_check_children_probe.py`: a holding child whose writer outlives it, an
`autorestart = "never"` record, `stop_grace_seconds = 1`; `_check_children`
must raise the writer error, SIGKILL the writer, and keep the pidfile.

```
1a869905 supervisor.py:
E           nexus.runtime.supervisor.RuntimeError_: Service 'echo' (pid 8443) exited and autorestart is 'never'.
E           AssertionError: Regex pattern did not match.
1 failed, 5 warnings in 0.82s
102daeef:
1 passed, 5 warnings in 1.81s
```

`test_read_active_probe.py`: a `ready_observed` record whose llama-server pid
is reaped and whose `log_writer_pid` is a held writer; `active()` must raise
`LocalInferenceError` naming the writer, SIGKILL it, and keep the record.

```
1a869905 local_inference.py:
E           Failed: DID NOT RAISE <class 'nexus.api.local_inference.LocalInferenceError'>
1 failed, 7 warnings in 0.83s
102daeef:
1 passed, 7 warnings in 1.84s
```

`$PY -m pytest -q tests/test_runtime/test_supervisor.py tests/test_api/test_local_inference.py`
on `102daeef`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
67 passed, 7 warnings in 18.43s
```

The PostgreSQL gate command above, on `102daeef`, with `NEXUS_GATEWAY_PORT`,
`NEXUS_API_URL` and `NEXUS_SLOT` unset:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_1013_readiness_* x2, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
325 passed, 7 warnings in 119.10s (0:01:59)
```

Black on the four changed Python files: `4 files would be left unchanged.`
Flake8 on them reports nothing; mypy on the three product files reports only
the 9 pre-existing `nexus/runtime/supervisor.py` errors.

The branch layout finding (842-S2 and 842-S3 not each in one commit) is not
applied: it needs a history rewrite, which this fix pass may not do. The
coordinator rebuilds the branch or lands it with a waiver.

## Static Checks

Black: `10 files would be left unchanged.` Flake8 on the changed files reports
nothing new: `nexus/cli.py` and `nexus/config/settings_models.py` keep their 9
and 6 pre-existing E501 lines, the same counts as `origin/main`. Mypy: the
changed files are clean except `nexus/runtime/supervisor.py`, which reports 9
pre-existing errors (requests stubs, Windows-only `subprocess` attributes,
optional external/remote settings); `origin/main`'s copy reports 10. The
`validate-config` hook passed on the `nexus.toml` commit.

## After the Independent Review (Merge `0594ca0f`, Fix `85fc9b43`)

`origin/main` (`f8dd073c`) was merged into the branch first (`0594ca0f`); it
merged without a conflict. The five findings, each applied as the coordinator
decided:

1. **A failed identity probe certified absence.** `_is_writer_for`
   (`nexus/runtime/log_capture.py`) now raises `WriterProbeError` (a
   `RuntimeError`) naming the pid, the file and the failure when `ps` cannot
   be started, exits non-zero while the pid is alive (stderr omitted), or
   outlasts the timeout. A non-zero exit for a pid that has meanwhile gone is
   the probe's answer, not a failure. `wait_for_writer` lets the error
   through; `Supervisor._await_writer` re-raises it as `RuntimeError_` and
   `local_inference._await_capture_writer` as `LocalInferenceError`, both
   before any unlink, so the record that names the writer stays and the
   writer is never signalled.
2. **A dead writer under a live service went unnoticed.** New
   `log_capture.writer_alive` reaps first; a running unreaped child of this
   process is its recorded writer (an unreaped pid is never recycled), any
   other live pid is the writer only when the probe names the file, and a
   probe that cannot run raises. `_check_children` checks each live service
   whose record carries `log_writer_pid`; a dead writer stops the service
   through `_stop_pid`, removes its pidfile, and raises the decided text.
   `nexus status` adds `log_writer` (`alive`, `dead`, or `-`) to every
   service entry and a `WRITER` column to the text table. `nexus doctor` had
   no supervisor check (its only supervisor-backed check is the owner-client
   `gateway.reachable`, which the default `owner-host` target does not run),
   so the dead-writer report is a new owner-host check,
   `runtime.log_writers` (depends on `config.valid`), whose remediation is
   "Restart the service by name: nexus restart <service>".
3. **Local-model records were unlinked before their writers.** Every unlink
   of `local-model.pid.json` and `local-model.download.json` now goes through
   `_release_record(settings, path, log_path)`, which waits for the record's
   `log_writer_pid` first (kill and raise after the grace, record kept):
   `_read_active` (two paths), `_deactivate_locked` (four paths; the stop
   path now releases the record after the port release instead of unlinking
   it before), the failed-record branch of `activate` (before port and
   executable validation), and both `cancel_download` paths. The helper
   takes `settings` as a first argument for the grace and poll values.
4. **The empty-mark retention check raced the snapshot.** `logs_since`
   keeps the pre-wait `.backup_count` check as a fast path and raises the
   same `RuntimeError_` when the snapshot `_open_segments` returns holds
   `.backup_count`.
5. **Identity churn retried without a deadline.** One monotonic deadline of
   `stop_grace_seconds` bounds the whole `_open_segments` wait; past it a
   lasting gap raises the existing gap text and churn raises "The segments
   of <path> kept changing identity between opens for <grace>s (churn)".

New tests: `test_wait_for_writer_raises_when_the_probe_cannot_run`
(`missing`, `exits-1`, `sleeps`: `PATH` holds no `ps`, a `ps` that exits 1,
a `ps` that sleeps past the 0.5 s timeout; the writer and its child are still
running afterwards), `test_stop_keeps_the_record_when_the_writer_probe_cannot_run`,
`test_check_children_stops_a_service_whose_writer_died`,
`test_status_reports_each_services_log_writer` (gateway port OS-assigned, so
the status fetch touches no live gateway), `test_doctor_fails_a_live_service_without_its_writer`,
`test_logs_since_empty_mark_rechecks_retention_after_the_wait`,
`test_open_segments_deadline_bounds_identity_churn` (a module-level `open`
that replaces the file after each open), and in
`tests/test_api/test_local_inference.py`
`test_failed_activation_releases_its_record_only_after_the_writer` and
`test_cancel_releases_a_lost_download_record_only_after_the_writer` (a held
writer and `stop_grace_seconds = 1`: the first call raises naming the writer,
SIGKILLs it, and keeps the record; the retry removes the record and, for
activation, then raises the missing-executable error).
`tests/test_runtime/test_readiness.py` registers `runtime.log_writers` in
`EXPECTED_REGISTRY` and in the config-failure skip list; `docs/runtime.md`
carries the table row and the rules.

### Red Runs

Each a scratch plant of the pre-fix logic, run, then restored by copying the
saved file back (`cmp` confirmed), before the commit; test line numbers are
from before Black rewrapped the new local-inference tests.

Item 1, `_is_writer_for` back to `except (OSError, SubprocessError): return False`:

```
tests/test_runtime/test_supervisor.py:929: Failed: DID NOT RAISE <class 'nexus.runtime.log_capture.WriterProbeError'>
tests/test_runtime/test_supervisor.py:929: Failed: DID NOT RAISE <class 'nexus.runtime.log_capture.WriterProbeError'>
tests/test_runtime/test_supervisor.py:929: Failed: DID NOT RAISE <class 'nexus.runtime.log_capture.WriterProbeError'>
tests/test_runtime/test_supervisor.py:959: Failed: DID NOT RAISE <class 'nexus.runtime.supervisor.RuntimeError_'>
FAILED tests/test_runtime/test_supervisor.py::test_wait_for_writer_raises_when_the_probe_cannot_run[missing]
FAILED tests/test_runtime/test_supervisor.py::test_wait_for_writer_raises_when_the_probe_cannot_run[exits-1]
FAILED tests/test_runtime/test_supervisor.py::test_wait_for_writer_raises_when_the_probe_cannot_run[sleeps]
FAILED tests/test_runtime/test_supervisor.py::test_stop_keeps_the_record_when_the_writer_probe_cannot_run
4 failed, 48 deselected in 1.97s
```

Item 2, the dead-writer branch of `_check_children` disabled:

```
tests/test_runtime/test_supervisor.py:1004: Failed: DID NOT RAISE <class 'nexus.runtime.supervisor.RuntimeError_'>
FAILED tests/test_runtime/test_supervisor.py::test_check_children_stops_a_service_whose_writer_died
1 failed, 51 deselected in 0.41s
```

Item 3, the bare unlinks restored in `activate` and the ownership-lost
`cancel_download` branch:

```
tests/test_api/test_local_inference.py:1111: AssertionError: Regex pattern did not match.
tests/test_api/test_local_inference.py:1156: Failed: DID NOT RAISE <class 'nexus.api.local_inference.LocalInferenceError'>
FAILED tests/test_api/test_local_inference.py::test_failed_activation_releases_its_record_only_after_the_writer
FAILED tests/test_api/test_local_inference.py::test_cancel_releases_a_lost_download_record_only_after_the_writer
2 failed, 24 deselected in 0.92s
```

Item 4, the post-snapshot retention check removed (the old code returned
`["line-3", "line-4", "line-5"]`):

```
tests/test_runtime/test_supervisor.py:1118: Failed: DID NOT RAISE <class 'nexus.runtime.supervisor.RuntimeError_'>
FAILED tests/test_runtime/test_supervisor.py::test_logs_since_empty_mark_rechecks_retention_after_the_wait
1 failed, 51 deselected in 0.83s
```

Item 5, the deadline enforced only on a gap again (`if beyond and ...`):

```
tests/test_runtime/test_supervisor.py:1155: AssertionError: the snapshot retried past its deadline
FAILED tests/test_runtime/test_supervisor.py::test_open_segments_deadline_bounds_identity_churn
1 failed, 51 deselected in 6.36s
```

### Gates on `85fc9b43`

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
339 passed, 7 warnings in 127.70s (0:02:07)
```

Offline `tests --ignore=tests/test_api --ignore=tests/test_orrery`, split in
three for the ten-minute shell limit (the test subdirectories; the first 70
top-level `tests/test_*.py` files in sorted order; the remaining 53):

```
tests/config tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_util:
secret-store guard: active; nexus-api: denied; disposable keychain: denied
824 passed, 71 skipped, 7 warnings in 68.88s (0:01:08)
top-level files 1-70:
secret-store guard: active; nexus-api: denied; disposable keychain: denied
967 passed, 182 skipped, 8 warnings in 262.00s (0:04:22)
top-level files 71-123:
secret-store guard: active; nexus-api: denied; disposable keychain: denied
900 passed, 169 skipped, 7 warnings in 71.87s (0:01:11)
```

Offline `$PY -m pytest -q tests/test_api tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1825 passed, 743 skipped, 7 warnings in 36.39s
```

`$PY -m pytest -q tests/test_reachability.py tests/test_prompt_lint.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
76 passed, 5 warnings in 21.24s
```

Black on the eight changed Python files: `8 files would be left unchanged.`
Flake8 on them reports only `nexus/cli.py`'s 9 pre-existing E501 lines (the
same count as `origin/main`); mypy reports only the 9 pre-existing
`nexus/runtime/supervisor.py` errors. `nexus.toml` is unchanged in this pass;
the commit's `validate-config` hook passed.

## After the Verification Pass (Merge `d7272f23`, Fix `d7881bfc`)

Two verifiers proved two more defects on `e56457da`.

1. **An unanswered local-model ownership probe read as "not ours" (P2).**
   `_process_is_ours` and `_download_process_is_ours`
   (`nexus/api/local_inference.py`) caught `OSError` and `SubprocessError`,
   `TimeoutExpired` included, and returned False. Since this PR that verdict
   goes to `_release_record` (`_read_active`, `_deactivate_locked`,
   `cancel_download`) and to the failed branch of `download_status`, which
   wait for the recorded writer. The live server still holds the pipe, so the
   wait timed out and `kill_writer` killed the writer of a running server.
   The ownership probe times out at `[runtime.health].timeout_seconds` (2 s)
   and the writer wait at `stop_grace_seconds` (10 s), so any `ps` latency
   between the two got past the item-1 guard. Fix: both functions share
   `_probe_command`, which raises `LocalInferenceError` ("Cannot tell whether
   pid N is the managed llama-server" or "... the local-model download
   worker", then the reason) when `ps` cannot be started, outlasts
   `timeout_seconds`, or exits non-zero while the pid is alive. A non-zero
   exit for a pid that has meanwhile gone is the probe's answer (None). Only
   a probe that ran and whose command line lacks the markers returns False.
2. **The PostgreSQL proof set was red from branch staleness (P3).**
   `origin/main` gained migration 139 (`56c884e7`, #1064) after `0594ca0f`,
   and `NEXUS_template` is stamped 139, so
   `test_migration_state_compares_stamps_with_this_checkout` saw
   `unknown=[139]`. Fix: `origin/main` (`56c884e7`) merged as the plain merge
   commit `d7272f23` without a conflict; `migrations/` now ends at
   `139_character_relationship_bigint_ids.sql`. No product code changed for
   this finding.

New tests in `tests/test_api/test_local_inference.py` (the capture config
gains a `timeout_seconds` keyword; each runs with `timeout_seconds = 1` and
`stop_grace_seconds = 4`, and each kind of `ps` stands first on `PATH`:
`slow` sleeps 1.5 s then runs `/bin/ps`, `exits-1` exits 1, `missing` leaves
no `ps` on `PATH`):

- `test_active_raises_when_the_ownership_probe_goes_unanswered[kind]`:
  `activate` starts the stub llama-server under a real writer; with the stub
  in place `active()` raises the probe error in under 4 s, the writer is
  still a running unreaped child (`waitpid(writer, WNOHANG) == (0, 0)`), the
  server is alive, and the record is byte-for-byte unchanged. With the real
  `ps` back, `deactivate()` stops the server and its writer is gone.
- `test_download_status_raises_when_the_ownership_probe_goes_unanswered[kind]`:
  a live process whose command line names `nexus.api.local_download_worker`
  and `qa842/none`, under a real writer, with its record; `download_status()`
  raises the probe error in under 4 s, the writer still runs, and the record
  is unchanged. With the real `ps` back, `download_status()` reports
  `downloading`.

### Red Run

Scratch plant: the old verdict restored, each of the two functions wrapping
`_probe_command` in `except LocalInferenceError: return False`. Reverted with
`git checkout -- nexus/api/local_inference.py` before anything else ran.

```
$ PYTHONPATH=$PWD $PY -m pytest -q -rf tests/test_api/test_local_inference.py -k unanswered
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_api/test_local_inference.py::test_active_raises_when_the_ownership_probe_goes_unanswered[exits-1]
FAILED tests/test_api/test_local_inference.py::test_active_raises_when_the_ownership_probe_goes_unanswered[missing]
FAILED tests/test_api/test_local_inference.py::test_active_raises_when_the_ownership_probe_goes_unanswered[slow]
FAILED tests/test_api/test_local_inference.py::test_download_status_raises_when_the_ownership_probe_goes_unanswered[exits-1]
FAILED tests/test_api/test_local_inference.py::test_download_status_raises_when_the_ownership_probe_goes_unanswered[missing]
FAILED tests/test_api/test_local_inference.py::test_download_status_raises_when_the_ownership_probe_goes_unanswered[slow]
6 failed, 26 deselected, 7 warnings in 15.45s
```

The `slow` case reproduces the verifier's finding exactly: the planted
`active()` raised "Log writer pid 57913 for .../local-model.log outlived its
process by 4.0s; a process still holds the captured output. Killed the
writer." while the server lived. In the `exits-1` and `missing` cases the
planted verdict reached the writer wait, whose own probe (item 1 of the
previous pass) raised `WriterProbeError`, so the error named the writer, not
the server. Green on the fix: `6 passed, 26 deselected, 7 warnings in 4.72s`.

### Gates on `d7881bfc`

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime tests/test_runtime_home.py tests/test_api/test_local_inference.py tests/test_api/test_local_models_endpoints.py tests/test_owner_target_guard.py`
(`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` unset):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_1013_readiness_* x2, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
345 passed, 7 warnings in 136.89s (0:02:16)
```

Offline `$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2691 passed, 429 skipped, 8 warnings in 420.88s (0:07:00)
```

Offline `$PY -m pytest -q tests/test_api tests/test_reachability.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
706 passed, 238 skipped, 7 warnings in 43.74s
```

Offline `$PY -m pytest -q tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1179 passed, 505 skipped, 7 warnings in 10.10s
```

Black on the two changed Python files: `2 files would be left unchanged.`
Flake8 on them is clean; mypy: `Success: no issues found in 2 source files`.
`nexus.toml` is unchanged in this pass; the commit's `validate-config` hook
passed.

## After the Second Independent Review (Merge `75fbf48f`, Fix `e3a9ed9c`)

`origin/main` (`fedebf92`) merged in first as the plain merge commit
`75fbf48f`, without a conflict. The second independent pass (frozen at
`870f4ba5`) found four P2 in the process model; all four are fixed.

1. **An unreaped service exit read as a live service that lost its writer.**
   In foreground mode the services are children of the supervisor, and an
   exited child answers `kill(pid, 0)` until it is reaped. `_check_children`
   took the live branch; when the writer had drained and exited normally,
   `_writer_alive` reaped it and the branch raised a capture failure instead
   of reaching `autorestart = "on-failure"`. Fix: the new
   `log_capture.process_running(pid)` calls `_child_state(pid)` first: an
   exited own child (False) is reaped and takes the exited path (wait out the
   writer, unlink, autorestart); a running child (True), or a pid that is not
   ours and still answers `pid_alive` (None), is live and gets the dead-writer
   check. `_await_healthy` uses the same check for its "exited during
   startup" branch, which had the same blind spot: a start that exits at once
   is now reported at once rather than after `startup_deadline_seconds`.
2. **A startup failure could leave a live writer with no record.**
   `_start_service` now writes the pidfile immediately after `_spawn` (the
   same record; `started_at` taken then). `_await_healthy`'s two failure
   branches unlink it only after `_await_writer` has returned; when that wait
   raises, the record stays, so the next `_start_service` finds it stale and
   waits for that writer (raising again while the probe cannot run) instead
   of starting a second writer. `up()`'s rollback stops every enabled service
   that has a pidfile at that moment, not only the names in `started`; each
   teardown failure is attached to the original exception with
   `exc.add_note(f"Teardown of '{name}' also failed: {teardown_exc}")` and the
   original is re-raised. One guard beyond the order's letter: a record that
   already existed, unchanged, before this `up()` call is not stopped. Without
   it, `nexus up` over a running stack (refused as "already running") would
   stop that stack, and a stale record whose writer could not be waited out
   would be retried in the rollback for a duplicate error.
3. **A failed child spawn abandoned its writer.** `spawn_captured` takes a
   required `health: RuntimeHealthSettings` (both callers pass
   `settings.runtime.health`). When the child's `Popen` raises, it closes
   `writer.stdin`, calls `wait_for_writer(writer.pid, log_path,
   stop_grace_seconds, poll_interval_seconds)`, kills and collects the writer
   when that returns False, and re-raises the original exception; a
   `WriterProbeError` from the wait is raised `from` the spawn error. The
   docstring sentence that began "If the child cannot be started" says so.
4. **A record-write failure left the worker and its writer running.**
   `local_inference._abandon_spawn(settings, process, log_path)`, used by
   `activate` and `start_download`: SIGTERM to the process group (a
   `ProcessLookupError` is fine), wait for the process to exit for
   `stop_grace_seconds` polling at `poll_interval_seconds` (through
   `process_running`, so the gateway reaps its own child), SIGKILL the group
   when it still runs at the deadline, then `wait_for_writer`/`kill_writer` on
   `process.writer_pid` with the same bounds (a `WriterProbeError`
   propagates), then the caller re-raises its `LocalInferenceError`.

`docs/runtime.md` states the four rules beside the writer lifecycle and the
local-model captures.

New tests:

- `tests/test_runtime/test_supervisor.py::test_check_children_restarts_an_unreaped_service_exit`:
  a foreground-style captured child (`ONE_LINE_CHILD`) prints one line and
  exits normally; `autorestart = "on-failure"`, one retry. The test waits
  until both the child and its writer are zombies, probing `ps` through
  `os.posix_spawn` because every new `subprocess.Popen` first reaps the
  exited children of discarded `Popen` objects. `_check_children` raises
  nothing, `restarts == {"echo": 1}`, the new pidfile names a new pid, and
  the capture reads `one-line` twice.
- `test_check_children_still_fails_a_live_child_without_its_writer`: the same
  child with its marker present keeps running (it serves 200 on its port);
  with its writer killed, `_check_children` raises the ordered capture-failure
  text exactly.
- `test_up_leaves_no_record_and_no_writer_when_a_service_exits_at_once`: only
  `echo` enabled, its command `raise SystemExit(3)`; `up()` raises "'echo'
  exited during startup", no pidfile remains, and the real `ps` lists no live
  writer for the capture.
- `test_failed_start_keeps_the_record_when_the_writer_probe_cannot_run`: the
  holding child under `up()` with no `ps` on `PATH`. `up()` raises "Cannot
  tell whether pid W ...", carries the note "Teardown of 'echo' also failed:
  Cannot tell ...", and leaves the pidfile with its `log_writer_pid`; a
  second `_start_service` raises the probe error for the same writer before
  any spawn; with the real `ps` restored exactly one writer runs for the
  capture (the recorded one) and the record is unchanged.
- `test_failed_child_spawn_waits_out_its_writer`: `spawn_captured` on a
  missing executable raises `FileNotFoundError`; afterwards the real `ps`
  lists no live writer for the capture and `.writer-error` is empty.
- `tests/test_api/test_local_inference.py::test_activation_abandons_a_spawn_whose_record_cannot_be_written`
  and `test_download_abandons_a_spawn_whose_record_cannot_be_written`: a real
  stub llama-server that prints one line and sleeps (and, for the download,
  the real worker under `HF_HUB_OFFLINE=1`) under a real writer, with the
  record write failing for real. `activate` / `start_download` raise "Cannot
  write local model state"; afterwards no child of the test process that the
  call started remains, running or unreaped (listed through `os.posix_spawn`
  of `ps`), the real `ps` lists no live writer, and no record exists.

Deviation in the item 4 tests: the order said to replace the state directory
by a plain file before the call. `logs_dir` equals `state_dir`, and both
calls read the previous record (and the writer opens the capture) in that
directory before they spawn, so a plain file there fails the read first and
never reaches the write. The tests instead make the state directory
read-only (`0o555`) with the capture and its `.writer-error` file created
beforehand: the record read finds no file, the writer appends to the
existing capture, and `tempfile.mkstemp` in `_write_json` fails with
`PermissionError`, mapped to `LocalInferenceError`. No mock.

### Red Runs

Each plant restored the old behavior in a scratch edit; the file was copied
back from a saved copy and compared with `cmp` before anything else ran.

Item 1, `_check_children` deciding liveness with `_pid_alive(pid)` again:

```
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_runtime/test_supervisor.py -k unreaped
E           nexus.runtime.supervisor.RuntimeError_: Log writer for 'echo' (pid 89537) died while the service (pid 89538) was running; its output had nowhere to go. Stopped the service.
1 failed, 56 deselected, 5 warnings in 2.05s
```

Item 3, `spawn_captured` re-raising without the writer wait:

```
$ PYTHONPATH=$PWD $PY -m pytest -q -rf tests/test_runtime/test_supervisor.py -k failed_child_spawn
E       assert [89612] == []
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_runtime/test_supervisor.py::test_failed_child_spawn_waits_out_its_writer
1 failed, 56 deselected, 5 warnings in 0.48s
```

Item 4, `_abandon_spawn` reduced to the old SIGTERM and return:

```
$ PYTHONPATH=$PWD $PY -m pytest -q -rf tests/test_api/test_local_inference.py -k abandons
E       AssertionError: activation left children behind: [91108, 91111]
E       AssertionError: the download left children behind: [91134, 91135]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_api/test_local_inference.py::test_activation_abandons_a_spawn_whose_record_cannot_be_written
FAILED tests/test_api/test_local_inference.py::test_download_abandons_a_spawn_whose_record_cannot_be_written
2 failed, 32 deselected, 7 warnings in 0.76s
```

Green on the fix: `9 passed, 82 deselected, 7 warnings in 6.64s` for the
seven new tests plus the two earlier probe tests that share their names'
keywords.

### Gates on `e3a9ed9c`

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime tests/test_runtime_home.py tests/test_api/test_local_inference.py tests/test_api/test_local_models_endpoints.py tests/test_owner_target_guard.py`
(`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` unset):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_1013_readiness_* x2, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
352 passed, 7 warnings in 138.87s (0:02:18)
```

Offline `$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2704 passed, 444 skipped, 8 warnings in 445.00s (0:07:25)
```

Offline `$PY -m pytest -q tests/test_api tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1833 passed, 743 skipped, 7 warnings in 43.22s
```

Offline `$PY -m pytest -q tests/test_reachability.py tests/test_prompt_lint.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
76 passed, 5 warnings in 21.47s
```

Black on the five changed Python files: `5 files would be left unchanged.`
Flake8 on them is clean; mypy reports only the 9 pre-existing
`nexus/runtime/supervisor.py` errors. `nexus.toml` is unchanged in this pass;
the commit's `validate-config` hook passed.

## After the Third Independent Review

Round 3 implements all three P2 findings in `review-1065c.out.md` under
work order `1065-astra-fix-r3.md`. Fix commit `605c0e6c9939d80513d0b0a84856b0c761968992`. `origin/main`
`d05481d8` was merged first in `6f124613996d31c2617944f4ea4d2827d0b84e78`;
when main advanced during validation, `5d99c5b2` was merged in `91e5fa9ba7bcc6ceda1c14aab6b5b56670766c30`
without conflicts or history rewriting. The later merge only adds the #782
probe, its test, reachability entries and documentation; its added test and
reachability/prompt lint were validated separately (85 passed).

- **Abandon on a failed record write.** `_start_service` owns its spawned
  service and writer until its pidfile exists. Any pidfile-write exception
  calls `_abandon_service(name, pid, writer_pid)` (`_stop_pid`, then
  `_await_writer`), then re-raises the original exception. A cleanup error
  propagates from that write exception, retaining both causes. The waits
  use the existing health bounds; `_stop_pid` is unchanged.
- **Rollback by spawned pid, never by pidfile comparison.** `up()` records
  only the `(name, pid, log_writer_pid)` triples returned by this invocation's
  successful starts. On failure it stops those pids and waits for those
  writers, then unlinks only a record still naming the stopped service pid.
  Refused, attached and skipped starts are never owned. The earlier snapshot
  logic is deleted; teardown errors still attach notes to the original error.
- **Recheck the service before classifying a dead writer.**
  `_child_capture_state` reaps/checks the service first, checks its writer,
  and checks the service again if the writer is dead. A normal exit between
  checks reaches the existing wait/unlink/autorestart path. A still-running
  service with a dead writer retains the ordered capture-failure text.


The round-2 departure (a), preservation based on an unchanged pre-call
record, is superseded by invocation ownership. A record that changed during
this call does not establish ownership either. The earlier failed-start
probe test now expects no rollback retry/note: the failing start never
returned a successful record to `up()`, and its retained writer record is
still tested as unchanged and blocks a second spawn.

Five new cases use real children, real capture writers and isolated state
under `tmp_path`. All new live-service ports come from the imported
`ephemeral_ports` fixture in `tests/test_runtime/test_supervisor_live.py`:

- `test_up_abandons_a_service_whose_pidfile_cannot_be_written`: existing
  capture and writer-error files, then `chmod(0o555)` on the state directory.
  `up()` raises `PermissionError`; neither pid is running, both are reaped,
  and no pidfile exists. A wrapper observes real `_spawn` pids; it does not
  replace spawning or writing. The test reaps an exited service when checking
  it, consistent with the deferred `_stop_pid` zombie observation below.
- `test_refused_up_preserves_another_invocations_stack[existing/concurrent]`:
  another `Supervisor` really starts on the same isolated state directory.
  The concurrent case starts it at the first supervisor's `_start_service`
  boundary (after the old snapshot point). The refusal leaves its exact
  record, service, writer and health endpoint intact.
- `test_up_rolls_back_only_its_successfully_started_pids`: a real healthy
  first service and a second child that exits during startup. The second
  cleans itself up; rollback stops the first pid and its writer; no records
  remain.
- `test_check_children_restarts_a_service_that_exits_during_the_writer_check`:
  the real child waits on its own release file; the writer probe releases it,
  waits for both zombies without reaping via `os.posix_spawn` of `/bin/ps`,
  then performs the real writer check. The next child serves real HTTP health;
  `restarts` is 1 and both `one-line` outputs are captured. The existing
  killed-writer case still asserts the exact ordered capture-failure text.

### Commands and Verbatim Tails

Every command ran from this worktree with `PYTHONPATH=$PWD` and
`PY=/Users/pythagor/nexus/.venv/bin/python`; the import proof printed
`/Users/pythagor/nexus/.claude/worktrees/842-log-rotation/nexus/__init__.py`.
For all full gates, `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT`,
`NEXUS_RUN_LIVE_LLM` and `NEXUS_RUN_SECRET_STORE` were unset; offline gates
also unset `NEXUS_RUN_POSTGRES`. Commands below were run through
`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/842-B-fix3/run_gate.py`, which runs each command in the foreground with
`subprocess.run(..., timeout=590)`, saves the exact argv, exit code and log,
and was waited for to completion. No timeout, owner target, paid call or
PostgreSQL permission-dialog error occurred. No owner service was signalled.

The two offline non-API/non-Orrery commands partition the earlier ordered
suite by directories (2750 passed, 449 skipped combined). Root also covers
`tests/test_config`, `tests/test_ir_eval_v2` and `tests/proofs`; the ignored
`tests/golden` and `tests/test_agents` paths do not exist. No tests were
omitted. API and Orrery run separately. PostgreSQL proof ran with its flag
set and zero skips.

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rf -p tests.dbname_audit tests/test_runtime tests/test_runtime_home.py tests/test_api/test_local_inference.py tests/test_api/test_local_models_endpoints.py tests/test_owner_target_guard.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_1013_readiness_* x2, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
357 passed, 7 warnings in 147.44s (0:02:27)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

`$PY -m pytest -q -rf -p tests.dbname_audit tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/config --ignore=tests/golden --ignore=tests/test_agents --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --ignore=tests/test_util`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
2006 passed, 378 skipped, 8 warnings in 390.52s (0:06:30)
```

`$PY -m pytest -q -rf -p tests.dbname_audit tests/config tests/test_lore tests/test_memnon tests/test_runtime tests/test_util`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
744 passed, 71 skipped, 7 warnings in 83.63s (0:01:23)
```

`$PY -m pytest -q -rf -p tests.dbname_audit tests/test_api`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
654 passed, 238 skipped, 7 warnings in 34.80s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

`$PY -m pytest -q -rf -p tests.dbname_audit tests/test_orrery`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1188 passed, 508 skipped, 2 warnings in 9.50s
```

`$PY -m pytest -q -rf -p tests.dbname_audit tests/test_reachability.py tests/test_prompt_lint.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
76 passed in 22.05s
```

`$PY -m pytest -q -rf -p tests.dbname_audit tests/test_intention_revision_weight.py tests/test_reachability.py tests/test_prompt_lint.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
85 passed in 22.28s
```


### Red Runs

The plants saved the green source under this scratch directory, restored
it in `finally` and compared bytes after each run. Test finalizers cleaned
up the real children even on assertion failure. No stash was used.

`$PY -m pytest -q -rf -p tests.dbname_audit tests/test_runtime/test_supervisor.py -k pidfile_cannot`:

```text
E           AssertionError: service pid 58476 is still running
E           assert not True
E            +  where True = process_running(58476)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_runtime/test_supervisor.py::test_up_abandons_a_service_whose_pidfile_cannot_be_written
1 failed, 61 deselected in 0.23s
```

`$PY -m pytest -q -rf -p tests.dbname_audit tests/test_runtime/test_supervisor.py -k during_the_writer_check`:

```text
E           nexus.runtime.supervisor.RuntimeError_: Log writer for 'echo' (pid 58494) died while the service (pid 58495) was running; its output had nowhere to go. Stopped the service.
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_runtime/test_supervisor.py::test_check_children_restarts_a_service_that_exits_during_the_writer_check
1 failed, 61 deselected in 1.79s
```

The first plant restores the bare `_write_pidfile` call; the test detects a
still-running service after the write raises. The second restores the
pre-fix dead-writer classification without rechecking the service; the test
raises the ordered capture failure on its ordinary exit instead of restarting.

Initial test-development runs used the same focused selector below:

`PYTHONPATH=$PWD $PY -m pytest -q -rf -p tests.dbname_audit tests/test_runtime/test_supervisor.py -k 'pidfile_cannot or another_invocations or successfully_started or during_the_writer_check or failed_start_keeps or still_fails_a_live'`:

focused:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_runtime/test_supervisor.py::test_refused_up_preserves_another_invocations_stack[existing]
FAILED tests/test_runtime/test_supervisor.py::test_refused_up_preserves_another_invocations_stack[concurrent]
FAILED tests/test_runtime/test_supervisor.py::test_check_children_restarts_a_service_that_exits_during_the_writer_check
3 failed, 4 passed, 55 deselected in 7.52s
```

focused-green:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_runtime/test_supervisor.py::test_check_children_restarts_a_service_that_exits_during_the_writer_check
1 failed, 6 passed, 55 deselected in 10.04s
```

focused-green-final:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
7 passed, 55 deselected in 10.62s
```

The first run exposed test defects: the second supervisor reloaded default
service settings instead of the test's isolated service selection, so it
refused the already occupied owner gateway port before spawning anything;
and the log API is a generator. Its service selection was corrected before
the subsequent run, which then exposed the need to wait for the restarted
writer's buffered line. That test now polls with the configured health
bounds; the final focused run and both full gates containing it passed.

### Python Checks

`$PY -m black --check nexus/runtime/supervisor.py tests/test_runtime/test_supervisor.py`:

```text
All done! ✨ 🍰 ✨
2 files would be left unchanged.
```

`$PY -m flake8 nexus/runtime/supervisor.py tests/test_runtime/test_supervisor.py`:

```text
(no output; exit 0)
```

`$PY -m mypy nexus/runtime/supervisor.py tests/test_runtime/test_supervisor.py`:

```text
nexus/runtime/supervisor.py:31: error: Library stubs not installed for "requests"  [import-untyped]
nexus/runtime/supervisor.py:31: note: Hint: "python3 -m pip install types-requests"
nexus/runtime/supervisor.py:31: note: (or run "mypy --install-types" to install all missing stub packages)
nexus/runtime/supervisor.py:31: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
tests/test_runtime/__init__.py: error: Source file found twice under different module names: "test_runtime" and "tests.test_runtime"
Found 2 errors in 2 files (errors prevented further checking)
```

`$PY -m mypy --explicit-package-bases nexus/runtime/supervisor.py tests/test_runtime/test_supervisor.py`:

```text
nexus/runtime/supervisor.py:31: error: Library stubs not installed for "requests"  [import-untyped]
nexus/runtime/supervisor.py:31: note: Hint: "python3 -m pip install types-requests"
nexus/runtime/supervisor.py:31: note: (or run "mypy --install-types" to install all missing stub packages)
nexus/runtime/supervisor.py:31: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
nexus/runtime/supervisor.py:580: error: Module has no attribute "CREATE_NEW_PROCESS_GROUP"  [attr-defined]
nexus/runtime/supervisor.py:580: error: Module has no attribute "DETACHED_PROCESS"  [attr-defined]
nexus/runtime/supervisor.py:902: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "gateway_url"  [union-attr]
nexus/runtime/supervisor.py:903: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "mock_openai_url"  [union-attr]
nexus/runtime/supervisor.py:904: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "mock_openai_url"  [union-attr]
nexus/runtime/supervisor.py:921: error: Item "None" of "RuntimeRemoteSettings | None" has no attribute "base_url"  [union-attr]
nexus/runtime/supervisor.py:1044: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "gateway_url"  [union-attr]
nexus/runtime/supervisor.py:1046: error: Item "None" of "RuntimeRemoteSettings | None" has no attribute "base_url"  [union-attr]
Found 9 errors in 1 file (checked 2 source files)
```

`$PY -m mypy --explicit-package-bases nexus/runtime/supervisor.py`:

```text
nexus/runtime/supervisor.py:31: error: Library stubs not installed for "requests"  [import-untyped]
nexus/runtime/supervisor.py:31: note: Hint: "python3 -m pip install types-requests"
nexus/runtime/supervisor.py:31: note: (or run "mypy --install-types" to install all missing stub packages)
nexus/runtime/supervisor.py:31: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
nexus/runtime/supervisor.py:580: error: Module has no attribute "CREATE_NEW_PROCESS_GROUP"  [attr-defined]
nexus/runtime/supervisor.py:580: error: Module has no attribute "DETACHED_PROCESS"  [attr-defined]
nexus/runtime/supervisor.py:890: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "gateway_url"  [union-attr]
nexus/runtime/supervisor.py:891: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "mock_openai_url"  [union-attr]
nexus/runtime/supervisor.py:892: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "mock_openai_url"  [union-attr]
nexus/runtime/supervisor.py:909: error: Item "None" of "RuntimeRemoteSettings | None" has no attribute "base_url"  [union-attr]
nexus/runtime/supervisor.py:1032: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "gateway_url"  [union-attr]
nexus/runtime/supervisor.py:1034: error: Item "None" of "RuntimeRemoteSettings | None" has no attribute "base_url"  [union-attr]
Found 9 errors in 1 file (checked 1 source file)
```

The default mypy invocation stops on a module-name collision introduced by
importing the shared test fixture. With `--explicit-package-bases`, the
changed test file has no errors and the supervisor reports nine. A scratch
plant of the pre-round supervisor at the same path reports exactly the
same nine diagnostics after normalizing line numbers; the source was
restored and byte-compared. These pre-existing diagnostics are not fixed in
this scoped order. No package installation or error-code suppression was
used. The fix commit's pre-commit hooks reported:

```text
Regenerate Orrery package catalog........................................Passed
Validate NEXUS config and model-ID drift.................................Passed
Require COMMENT ON for new migration objects.........(no files to check)Skipped
```

### Deferred

P3 for #842: the reviewer's `_stop_pid` zombie observation remains. An
exited foreground child answers `_pid_alive` until reaped, so `_stop_pid`
waits the full grace before SIGKILL. Round 3 explicitly forbids changing
`_stop_pid`. The nine pre-existing mypy diagnostics above also remain.
No round-3 P2 was left unfixed. No new tunable, migration, paid call or
owner database write. Landing notes remain restart-by-name, writer status,
no client change and no UI rebuild.


## After the Fourth Independent Review

Round-4 order `1065-astra-fix-r4.md`, reviewer `review-1065d.out.md`, frozen
head `9712e0fd32fd1b0b8c8e560bf6f0230ab8e3196a`.
`origin/main` at `5b977eabcba5f7aedf1a64a6ee20c021ab290911` was merged first
as `5b9958a136c175417b9a63bac5138db6a1cae6f5`, without conflicts or history
rewriting. Import proof before testing printed
`/Users/pythagor/nexus/.claude/worktrees/842-log-rotation/nexus/__init__.py`.

### Writer Lifecycle Rules

- **One start at a time per state directory.** `_start_lock`
  (`nexus/runtime/supervisor.py:509`) opens `supervisor.lock` once per instance
  and uses exclusive nonblocking `fcntl.flock`, polling under the existing
  `startup_deadline_seconds` and `poll_interval_seconds`. The error names the
  path and deadline. `_start_service` (`:763`) locks the existing-record,
  free-port, spawn and record-write sequence, and releases in `finally` before
  `_await_healthy`. A contender then sees the recorded live pid and is refused
  as already running.
- **Unlink only your own record.** `_unlink_own_record` (`:534`) reads the
  record, deletes it only when its pid matches the owned pid, and raises with
  `record now names pid N; left in place` otherwise. Both startup-health
  failure branches (`:719`) and `_abandon_service` (`:854`) use it; rollback
  routes through `_abandon_service` and keeps its error-note treatment.
  `_check_children` is unchanged.

### Real-Process Regression Coverage

`tests/test_runtime/test_supervisor.py:1666` starts two supervisor instances
from two threads on the same temporary state directory and one fixture-owned
OS-assigned port. The first is held at spawn with its real advisory lock
acquired; the second's real nonblocking flock reports contention. Exactly
one invocation succeeds and one raises already-running; the record names the
only service/writer pair, the service serves HTTP health, and real `/bin/ps`
finds exactly one writer for that capture.

`:1760` holds the real lock in a test thread and proves the second instance
raises the named bounded-lock error at its configured deadline without a
capture, record or writer. `:1799` verifies a foreign record survives helper,
startup-exit and abandonment cleanup, with the required error text; `:1830`
checks the health-deadline failure as well, including both owned pids gone.

The earlier read-only-directory regression initially failed before spawn:
the new lock could not be created after chmod. Its setup now opens the lock
before chmod (alongside the already-created captures), preserving the intended
real pidfile-write failure after spawn. The first failed tail and corrected
passing run are both recorded below.

### Test Commands and Verbatim Tails

All commands ran from this worktree. `PY=/Users/pythagor/nexus/.venv/bin/python`;
`SP=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/842-B-fix4`.
The foreground runner `$PY $SP/run_gate.py LABEL ...` supplied
`PYTHONPATH=$PWD`, `TMPDIR=$SP`, `NEXUS_DBNAME_AUDIT=1`, unset gateway/API
URLs and live-LLM/secret-store opt-ins, used a 590-second deadline and a
120-second silence limit, and waited for completion. Only `postgres-proof`
had `NEXUS_RUN_POSTGRES=1`; the offline runs had it unset. `--basetemp`
keeps all test-created state inside this order's scratch directory. Each
invocation below is the runner's actual argv, with the above substitutions.

The required red run replaced `_start_lock` with an unlocked context manager
at the worktree source path, using `$SP/red_run.py` and backup
`$SP/supervisor-green.py`. The deterministic test let the contender reach its
spawn while the first remained held; it failed with `the contender spawned
inside the startup window`. Cleanup completed, and the green source was
restored in `finally` and byte-compared before the full proof gates.

**focused (exit 1)**

`$PY -m pytest -q -p tests.dbname_audit tests/test_runtime/test_supervisor.py -k 'concurrent_starts or start_lock or preserves_a_record or up_abandons' --basetemp=$SP/focused-tmp`:

```text
            return pids
    
        monkeypatch.setattr(supervisor, "_spawn", observe_spawn)
        supervisor.state_dir.chmod(0o555)
        try:
            with pytest.raises(PermissionError):
                supervisor.up(slot=5, echo=False)
>           assert len(spawned) == 1
E           assert 0 == 1
E            +  where 0 = len([])

tests/test_runtime/test_supervisor.py:1484: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_runtime/test_supervisor.py::test_up_abandons_a_service_whose_pidfile_cannot_be_written
1 failed, 4 passed, 61 deselected in 5.60s
```

**focused-final (exit 0)**

`$PY -m pytest -q -p tests.dbname_audit tests/test_runtime/test_supervisor.py -k 'concurrent_starts or start_lock or preserves_a_record or up_abandons' --basetemp=$SP/focused-final-tmp`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
5 passed, 61 deselected in 6.79s
```

**red-unlocked (exit 1)**

`$PY -m pytest -q -p tests.dbname_audit tests/test_runtime/test_supervisor.py::test_concurrent_starts_share_one_service_and_writer --basetemp=$SP/red-tmp`:

```text
            assert decision.wait(5), "the contender neither blocked nor spawned"
            release.set()
            for thread in threads:
                thread.join(10)
                assert not thread.is_alive(), "a concurrent start did not finish"
>           assert blocked.is_set(), "the contender spawned inside the startup window"
E           AssertionError: the contender spawned inside the startup window
E           assert False
E            +  where False = is_set()
E            +    where is_set = <threading.Event at 0x10f7501d0: unset>.is_set

tests/test_runtime/test_supervisor.py:1734: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_runtime/test_supervisor.py::test_concurrent_starts_share_one_service_and_writer
1 failed in 1.71s
```

**postgres-proof (exit 0)**

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime tests/test_runtime_home.py tests/test_api/test_local_inference.py tests/test_api/test_local_models_endpoints.py tests/test_owner_target_guard.py --basetemp=$SP/postgres-tmp`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_1013_readiness_* x2, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
361 passed, 7 warnings in 149.84s (0:02:29)
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

**offline-root (exit 0)**

`$PY -m pytest -q -p tests.dbname_audit tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/test_config --ignore=tests/test_util --ignore=tests/test_ir_eval_v2 --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --basetemp=$SP/root-tmp`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
2049 passed, 387 skipped, 8 warnings in 389.67s (0:06:29)
```

**offline-support (exit 0)**

`$PY -m pytest -q -p tests.dbname_audit tests/test_config tests/test_util tests/test_ir_eval_v2 --basetemp=$SP/support-tmp`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
101 passed, 2 warnings in 4.42s
```

**offline-lore-memnon (exit 0)**

`$PY -m pytest -q -p tests.dbname_audit tests/test_lore tests/test_memnon --basetemp=$SP/lore-tmp`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
454 passed, 53 skipped, 5 warnings in 27.14s
```

**offline-runtime (exit 0)**

`$PY -m pytest -q -p tests.dbname_audit tests/test_runtime --basetemp=$SP/runtime-tmp`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
166 passed, 18 skipped in 55.53s
```

**offline-api (exit 0)**

`$PY -m pytest -q -p tests.dbname_audit tests/test_api --basetemp=$SP/api-tmp`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
654 passed, 238 skipped, 7 warnings in 37.12s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

**offline-orrery (exit 0)**

`$PY -m pytest -q -p tests.dbname_audit tests/test_orrery --basetemp=$SP/orrery-tmp`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1188 passed, 508 skipped, 2 warnings in 11.07s
```

**reachability (exit 0)**

`$PY -m pytest -q -p tests.dbname_audit tests/test_reachability.py --basetemp=$SP/reachability-tmp`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
54 passed in 10.52s
```

### Python Checks

`$PY -m black --check nexus/runtime/supervisor.py tests/test_runtime/test_supervisor.py`:

```text
All done! ✨ 🍰 ✨
2 files would be left unchanged.
```

`$PY -m flake8 nexus/runtime/supervisor.py tests/test_runtime/test_supervisor.py`:

```text
(no output; exit 0)
```

`$PY -m mypy nexus/runtime/supervisor.py tests/test_runtime/test_supervisor.py`:

```text
nexus/runtime/supervisor.py:33: error: Library stubs not installed for "requests"  [import-untyped]
nexus/runtime/supervisor.py:33: note: Hint: "python3 -m pip install types-requests"
nexus/runtime/supervisor.py:33: note: (or run "mypy --install-types" to install all missing stub packages)
nexus/runtime/supervisor.py:33: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
tests/test_runtime/test_supervisor_live.py: error: Source file found twice under different module names: "test_runtime" and "tests.test_runtime"
Found 2 errors in 2 files (errors prevented further checking)
```

`$PY -m mypy --explicit-package-bases nexus/runtime/supervisor.py tests/test_runtime/test_supervisor.py`:

```text
nexus/runtime/supervisor.py:33: error: Library stubs not installed for "requests"  [import-untyped]
nexus/runtime/supervisor.py:33: note: Hint: "python3 -m pip install types-requests"
nexus/runtime/supervisor.py:33: note: (or run "mypy --install-types" to install all missing stub packages)
nexus/runtime/supervisor.py:33: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
nexus/runtime/supervisor.py:622: error: Module has no attribute "CREATE_NEW_PROCESS_GROUP"  [attr-defined]
nexus/runtime/supervisor.py:622: error: Module has no attribute "DETACHED_PROCESS"  [attr-defined]
nexus/runtime/supervisor.py:943: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "gateway_url"  [union-attr]
nexus/runtime/supervisor.py:944: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "mock_openai_url"  [union-attr]
nexus/runtime/supervisor.py:945: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "mock_openai_url"  [union-attr]
nexus/runtime/supervisor.py:962: error: Item "None" of "RuntimeRemoteSettings | None" has no attribute "base_url"  [union-attr]
nexus/runtime/supervisor.py:1085: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "gateway_url"  [union-attr]
nexus/runtime/supervisor.py:1087: error: Item "None" of "RuntimeRemoteSettings | None" has no attribute "base_url"  [union-attr]
Found 9 errors in 1 file (checked 2 source files)
```

Scratch plant of `git show HEAD:nexus/runtime/supervisor.py` (the pre-fix merge
head), checked as `$PY -m mypy --explicit-package-bases nexus/runtime/supervisor.py`:

```text
nexus/runtime/supervisor.py:31: error: Library stubs not installed for "requests"  [import-untyped]
nexus/runtime/supervisor.py:31: note: Hint: "python3 -m pip install types-requests"
nexus/runtime/supervisor.py:31: note: (or run "mypy --install-types" to install all missing stub packages)
nexus/runtime/supervisor.py:31: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
nexus/runtime/supervisor.py:580: error: Module has no attribute "CREATE_NEW_PROCESS_GROUP"  [attr-defined]
nexus/runtime/supervisor.py:580: error: Module has no attribute "DETACHED_PROCESS"  [attr-defined]
nexus/runtime/supervisor.py:902: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "gateway_url"  [union-attr]
nexus/runtime/supervisor.py:903: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "mock_openai_url"  [union-attr]
nexus/runtime/supervisor.py:904: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "mock_openai_url"  [union-attr]
nexus/runtime/supervisor.py:921: error: Item "None" of "RuntimeRemoteSettings | None" has no attribute "base_url"  [union-attr]
nexus/runtime/supervisor.py:1044: error: Item "None" of "RuntimeExternalSettings | None" has no attribute "gateway_url"  [union-attr]
nexus/runtime/supervisor.py:1046: error: Item "None" of "RuntimeRemoteSettings | None" has no attribute "base_url"  [union-attr]
Found 9 errors in 1 file (checked 1 source file)
```

The nine diagnostics match exactly after line-number normalization; the changed
test file has no errors with explicit package bases. The green source was
restored and byte-compared. No dependency installation or diagnostic suppression.
Black, flake8 and `git diff --check` pass; no `nexus.toml` change.

### Deferred and Landing Notes

No round-4 P2 remains unfixed. The nine pre-existing mypy diagnostics and the
standard invocation's module-name collision remain outside this scoped fix.
P3 for #842 remains explicitly deferred: an exited foreground child still
answers `_pid_alive` until reaped, so `_stop_pid` waits its full grace before
SIGKILL. `_stop_pid` is unchanged.

No new tunable, schema change, paid call, or owner database write. No owner
service signalled. Landing notes remain restart by name (`nexus restart
gateway`, then `nexus restart mock_openai`), `nexus status` shows each service's
writer, no client change and no UI rebuild. The coordinator owns merge and
any whole-tree PostgreSQL gate.
