# Issue #1100 Verification: The Genesis-Stage CLI Tests Count Reads Deterministically

Test-only change to `tests/test_cli_generation_http.py`. No migration, no gateway
lane, no paid call (token usage: 0). `nexus/cli.py` and everything else under
`nexus/` are unchanged (`git diff --stat origin/main...HEAD -- nexus/` is empty
at `e34d03c8`).

The order named two tests. The coordinator's rulings widened the fix to every
test in the file that assumed exactly one status read before the transition
POST, so this branch now covers seven tests (listed under "The Seven
Race-Exposed Tests") and the race class in this file is closed. #1107, opened
for the five tests the order had left out, is covered here in full.

Every proof tail below names the commit it ran on. The newest code commit is
`e34d03c8`; the commit that adds this file's final text changes only this file.

## The CLI's Call Sequence from Launch to the Transition POST

All line numbers are at `364fef4b` (`origin/main` when this branch was cut).

1. `GET /api/slot/5/state`: `run_continue` reads the slot state
   (`nexus/cli.py:2519-2520`).
2. Seed-confirm only: `POST /api/story/new/chat` sends the wizard choice
   (`_api_post` at `nexus/cli.py:2801`, the non-trait path a plain choice
   takes; the URL is built at `nexus/cli.py:2692`); the answer reports `phase_complete` with next phase
   `ready`, which enters the transition branch at `nexus/cli.py:2848-2857`.
   Ready-resume skips this step and enters the transition branch at
   `nexus/cli.py:2649-2659` because the state read reported `phase: ready`.
3. Both branches open `with _echo_retrograde_stages(...)` around the transition
   POST (`nexus/cli.py:2654` and `nexus/cli.py:2852`). On entry, the context
   manager:
   - sends `GET /api/story/new/retrograde/status?slot=5` once, synchronously,
     on the main thread: `echo.snapshot()` (`nexus/cli.py:1811`, defined at
     `nexus/cli.py:1756`);
   - creates the stage reader thread (`nexus/cli.py:1812-1818`) and **starts it**
     (`nexus/cli.py:1819`) **before** it yields (`nexus/cli.py:1821`). The thread
     runs `poll` (`nexus/cli.py:1777-1781`):
     `while not self.settled and not stopped.wait(interval_seconds): self.read()`,
     so its first `GET /api/story/new/retrograde/status?slot=5` fires one
     interval after `reader.start()`.
4. After the yield, the main thread sends `POST /api/story/new/transition`
   (`nexus/cli.py:2655` / `nexus/cli.py:2853`).
5. When the POST answers, `stopped.set()` and `reader.join()`
   (`nexus/cli.py:1823-1824`), then one more read if not settled
   (`nexus/cli.py:1828`).

The test runs the reader at `status_poll_interval_seconds = 0.02`
(`GenerationScenario.stage_poll_seconds`, written into the run's `nexus.toml`
by `_run_cli`). Between `reader.start()` and the moment the gateway receives
the POST, the main thread must return from the generator, build the request,
open a TCP connection and send it. If that takes longer than 20 ms, the
reader's first interval read reaches the gateway before the POST, and the fake
gateway counts it as a second pre-POST read (`do_GET`: `if not
scenario.transition_posted: scenario.snapshot_reads += 1`).

## Choice: (b)

The CLI legitimately polls on an interval whose first tick can fire before the
transition POST is sent: the reader thread is started at `nexus/cli.py:1819`,
before the generator yields at `nexus/cli.py:1821`, and the POST is sent only
after the yield (`nexus/cli.py:2655`, `nexus/cli.py:2853`). A second pre-POST
read is therefore possible by construction, not an artifact of when the fake
gateway flips `transition_posted`. Holding such a read in the fake gateway
(option (a)) would hide real CLI behavior. The `== 1` assertions pinned an
implementation accident.

Every pre-POST read is answered with `stage_before`, a record of the previous
run (or of no run), and `_RetrogradeStageEcho.read` skips any record whose
`run` equals `_previous_run` (`nexus/cli.py:1770-1771`), so an early read
cannot print or duplicate a stage line. This is the reason the user-visible
invariant holds whatever the pre-POST read count is. This is a reading of the
code; the `interval-read-first` case of
`test_cli_reads_past_the_previous_runs_failure_record` (test 5 under "The
Seven Race-Exposed Tests") exercises the filter for an early read.

### Request Traces (Background, Not the Proof)

These probes were scratch files under the earlier session scratchpad's `1100/`
directory (`probe_trace.py`, `probe_new_assertions.py`, `probe_siblings.py`,
`probe_race.py`). They no longer exist: the host rebooted at about 13:20 CDT on
2026-10-07, which cleared `/private/tmp`. Their results were first recorded at
`586fd5a2` (test file as of `934c3625`; `nexus/cli.py` is the same at every
commit of this branch). The committed `interval-read-first` parametrization
proves the multi-read path in every run, so these results are background, not
the proof.

A scratch probe ran the seed-confirm and ready-resume scenarios through the
real `_run_cli` and printed `scenario.requests` up to the transition POST. At
the test's 20 ms interval the trace was always the single-snapshot form; at a
1 ms interval (to make the race likely without loading the machine) both forms
appeared:

```
ready=False interval=0.02: GET /api/slot/5/state -> POST /api/story/new/chat -> GET /api/story/new/retrograde/status?slot=5 -> POST /api/story/new/transition
ready=False interval=0.001: GET /api/slot/5/state -> POST /api/story/new/chat -> GET /api/story/new/retrograde/status?slot=5 -> GET /api/story/new/retrograde/status?slot=5 -> POST /api/story/new/transition
ready=True interval=0.02: GET /api/slot/5/state -> GET /api/story/new/retrograde/status?slot=5 -> POST /api/story/new/transition
ready=True interval=0.001: GET /api/slot/5/state -> GET /api/story/new/retrograde/status?slot=5 -> GET /api/story/new/retrograde/status?slot=5 -> POST /api/story/new/transition
```

A second probe, at a 1 ms interval, ran the reworked assertions of the
genesis-stage test eight times: `{2: '5 runs, new assertions pass, old
assertions pass 0', 1: '3 runs, new assertions pass, old assertions pass 3'}`.
Every run printed the six stage lines once, in order. With two pre-POST reads,
`stages_read` began `['idle', 'idle', 'idle', 'packet']`, so the old line-749
assertion (`stages_read[: len(scripted) + 1] == ["idle", *scripted]`) failed
too, not only the `== 1` count.

## The Seven Race-Exposed Tests

### Shared Fake-Gateway Bookkeeping

All of it lives in `tests/test_cli_generation_http.py`; no other test file
changed.

- `GenerationScenario.snapshot_served` (`934c3625`): the record each pre-POST
  read served; the fake gateway appends `stage_before` in the pre-POST branch.
  It is true by construction, so it is a structural guard on the fake gateway,
  not a check of CLI behavior.
- `GenerationScenario.interval_reads_before_post` and `pre_post_reads_seen`
  (`854190c8`): when the field is non-zero, the fake gateway's transition POST
  handler waits on the Event before it sets `transition_posted`; the status
  handler sets the Event once `snapshot_reads >= 1 + interval_reads_before_post`.
  The wait is bounded at 10 seconds and fails the test with `interval read
  never arrived`. No sleep, retry or timing margin.
- `GenerationScenario.failed_reads_before_post` and `failed_reads_after_post`
  (`e34d03c8`) replace `failed_reads`. A failed read's ordinal is counted among
  the reads on its own side of the POST (0 before the POST is the snapshot), so
  an early interval read cannot take the 502 meant for the first read in
  flight.

### Why No Contended Loop Is Needed

Each `interval-read-first` item forces the race outcome on every run: the fake
gateway holds the transition POST until the CLI's stage poller has taken one
interval read, so every such run has two pre-POST reads, whatever the machine
load. Load can only move an `unforced` item between one and more pre-POST
reads, and every assertion now accepts any count of at least one. The
forced-read parametrization therefore makes the race deterministic, which is
why the eight-hog contended loop is not needed and was not run at `e34d03c8`
(the coordinator's ruling: the owner is using this machine). The contended
loops recorded under "Earlier Proof" ran at `364fef4b` and `854190c8`.

### The Fixed List

Line numbers are at `e34d03c8`. Tests 1 and 3-7 take
`before = scenario.snapshot_reads`, assert
`before >= 1 + interval_reads_before_post`, and build their `stages_read`
expectation from `before` (a prefix in tests 1 and 5, the exact list in tests
3, 4, 6 and 7). Test 2 is the exception: its count is loosened to `>= 1`, and
its `stages_read` still pins one pre-POST read at its 60 s poll (item 2).

1. `test_cli_prints_each_genesis_stage_once_while_transition_runs` (line 763;
   20 ms poll; the order's named test; `934c3625`, `854190c8`, id rename at
   `d48f91bb`). Parametrized over `interval_reads_before_post` in `[0, 1]`
   (`unforced`, `interval-read-first`) beside `seed-confirm` / `ready-resume`.
   `snapshot_reads == 1` became `>= 1 + interval_reads_before_post`; new
   assertion `snapshot_served == [stage_before] * snapshot_reads`; the
   stage-sequence assertion now starts after `before` idle reads (old:
   `stages_read[: len(scripted) + 1] == ["idle", *scripted]`, which hard-codes
   one pre-POST read). The six stage lines, the single terminal `done` read and
   the narrative ordering are unchanged.
2. `test_cli_prints_a_terminal_stage_recorded_before_its_first_interval_read`
   (line 905; 60 s poll; the order's sibling at old line 840; `934c3625`).
   `snapshot_reads == 1` became `>= 1` plus the `snapshot_served` assertion.
   Its exact `stages_read == [before["stage"], "failed"]` is unchanged and
   still pins one pre-POST read: the test's premise is that no interval read
   happens at all, and a forced early read would hold the POST for 60 s, past
   the 10 s bound. It takes no forced-read case.
3. `test_cli_stops_reading_at_a_finished_stage_read_before_the_answer`
   (line 808; 20 ms poll; `e34d03c8`). Parametrized `unforced` /
   `interval-read-first`. Old: `stages_read == ["idle", "idle", "packet",
   "done"]`. New: `[*(["idle"] * before), "idle", "packet", "done"]`.
4. `test_cli_prints_the_failed_genesis_stage_and_the_transition_error`
   (line 829; 0.25 s poll; `e34d03c8`). Parametrized the same way. Old:
   `["idle", "packet", "expansion", "failed"]`. New: `[*(["idle"] * before),
   "packet", "expansion", "failed"]`.
5. `test_cli_reads_past_the_previous_runs_failure_record` (line 866; 20 ms
   poll; `e34d03c8`). Parametrized the same way. Old: `stages_read[:4] ==
   ["failed", "failed", "idle", "packet"]`. New: `stages_read[: before + 3] ==
   [*(["failed"] * before), "failed", "idle", "packet"]`, plus two new
   assertions: `snapshot_served == [PREVIOUS_RUN_FAILED] * before` and
   `"Genesis stage: failed" not in stdout`. Under `interval-read-first`, one
   pre-POST read is the stage poller's own read of the previous run's failure
   record, so this case exercises the run-identity filter at
   `nexus/cli.py:1770-1771` for an early read: without the filter, that read
   would print `Genesis stage: failed`.
6. `test_cli_names_no_stage_when_the_transition_is_refused_before_it_runs`
   (line 937; 0.25 s poll; `e34d03c8`). Parametrized the same way. Old:
   `["failed", "failed", "failed"]`. New: `["failed"] * (before + 2)` (the
   reads before the post, one while it was held, one after it answered).
7. `test_cli_reports_an_unreadable_genesis_stage_and_keeps_the_transition`
   (line 976; 20 ms poll; `e34d03c8`). Cases `before-the-post` (snapshot read
   fails: `failed_reads_before_post={0}`), `while-in-flight-unforced` and
   `while-in-flight-interval-read-first` (first read after the post fails:
   `failed_reads_after_post={0}`). `before-the-post` takes no forced read: its
   failed snapshot settles the stage reader before the poller starts, so no
   interval read can precede the post. Old: `stages_read == read`, with
   `read` `["502"]` / `["idle", "502"]`. New: the pre-POST reads (`idle`
   unless their ordinal fails) followed by one `502` per failed post-POST
   ordinal. Before `e34d03c8`, a forced early read took the global read
   ordinal 1, got the 502 and settled the reader; no scripted read followed,
   so the POST handler waited 10 s on `stages_served` and the CLI exited 4
   (`code=4 elapsed=11.3s stages_read=['idle', '502']`, probe recorded at
   `0defe321` against the test file as of `d48f91bb`). The split ordinals fix
   that.

Before `e34d03c8`, scratch probes showed each of tests 3-7's exposure (the
1 ms results recorded at `586fd5a2`, the forced-read results at `0defe321`):
a single early interval read gave `['idle', 'idle', 'idle', 'packet', 'done']`
(test 3), `['idle', 'idle', 'packet', 'expansion', 'failed']` (test 4),
`['failed', 'failed', 'failed', 'idle', 'packet']` (test 5), four `failed`
reads (test 6) and the exit-4 stall above (test 7). The red run below
reproduces each failure from the committed parametrization.

## Proof at `e34d03c8`

All runs from the worktree root with `PYTHONPATH=$PWD`, the shared interpreter
under `nice -n 15`, `-p tests.dbname_audit`, `NEXUS_RUN_POSTGRES=1`, and
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` unset. One pytest session
at a time. The one-minute load average was 5.9 to 8.1 before each run (below
the cap of 24, so no wait was needed). Scratch files for this round live in
the session scratchpad's `1104-evidence/`: `quiet_loop.sh <label>
<iterations>` (the loop driver), `kexpr.txt` (the seven-test selection) and
`plant_old_assertions.py` (the red plant).

### Full File (`e34d03c8`)

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_cli_generation_http.py`:

```
.............................................................            [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
61 passed in 107.92s (0:01:47)
```

### Quiet Loop of the Seven Tests (Ten Iterations, `e34d03c8`)

Selection (17 items: the seven tests with all their parametrizations):
`-k "genesis_stage_once or before_its_first_interval_read or finished_stage_read
or failed_genesis_stage_and_the_transition_error or previous_runs_failure_record
or refused_before_it_runs or unreadable_genesis_stage"`.

```
head: e34d03c8
iteration 1 rc=0 17 passed, 44 deselected in 33.63s
iteration 2 rc=0 17 passed, 44 deselected in 33.83s
iteration 3 rc=0 17 passed, 44 deselected in 33.88s
iteration 4 rc=0 17 passed, 44 deselected in 33.68s
iteration 5 rc=0 17 passed, 44 deselected in 33.71s
iteration 6 rc=0 17 passed, 44 deselected in 33.55s
iteration 7 rc=0 17 passed, 44 deselected in 33.51s
iteration 8 rc=0 17 passed, 44 deselected in 33.94s
iteration 9 rc=0 17 passed, 44 deselected in 33.36s
iteration 10 rc=0 17 passed, 44 deselected in 33.41s
loop summary: quiet7 iterations=10 fails=0
--- last tail (quiet7.run10.log)
.................                                                        [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
17 passed, 44 deselected in 33.41s
```

### Red Run: Old Assertions with the Forced Read On (Plant at `e34d03c8`)

`plant_old_assertions.py` put back the `0defe321` exact-list assertions (from
`git show 0defe321:tests/test_cli_generation_http.py`, lines 803, 824, 847,
900 and 923) in tests 3-7, keeping the forced-read parametrization and
everything else at `e34d03c8`. For test 7 the old `read` parameter is inlined
as `["502"]` for `before-the-post` and `["idle", "502"]` for
`while-in-flight`. The plant diff was `1 file changed, 5 insertions(+), 15
deletions(-)`. Selection: `-k "finished_stage_read or
failed_genesis_stage_and_the_transition_error or previous_runs_failure_record
or refused_before_it_runs or unreadable_genesis_stage"`. Every
`interval-read-first` item fails, and every `unforced` item and
`before-the-post` pass:

```
E       AssertionError: assert ['idle', 'idl...cket', 'done'] == ['idle', 'idl...cket', 'done']
E         At index 2 diff: 'idle' != 'packet'
E         Left contains one more item: 'done'
E       AssertionError: assert ['idle', 'idl...on', 'failed'] == ['idle', 'pac...on', 'failed']
E         At index 1 diff: 'idle' != 'packet'
E         Left contains one more item: 'failed'
E       AssertionError: assert ['failed', 'f...iled', 'idle'] == ['failed', 'f...le', 'packet']
E         At index 2 diff: 'failed' != 'idle'
E       AssertionError: assert ['failed', 'f...ed', 'failed'] == ['failed', 'failed', 'failed']
E         Left contains one more item: 'failed'
E       AssertionError: assert ['idle', 'idle', '502'] == ['idle', '502']
E         At index 1 diff: 'idle' != '502'
E         Left contains one more item: '502'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_cli_generation_http.py::test_cli_stops_reading_at_a_finished_stage_read_before_the_answer[interval-read-first]
FAILED tests/test_cli_generation_http.py::test_cli_prints_the_failed_genesis_stage_and_the_transition_error[interval-read-first]
FAILED tests/test_cli_generation_http.py::test_cli_reads_past_the_previous_runs_failure_record[interval-read-first]
FAILED tests/test_cli_generation_http.py::test_cli_names_no_stage_when_the_transition_is_refused_before_it_runs[interval-read-first]
FAILED tests/test_cli_generation_http.py::test_cli_reports_an_unreadable_genesis_stage_and_keeps_the_transition[while-in-flight-interval-read-first]
5 failed, 6 passed, 50 deselected in 22.36s
```

The plant was reverted with `git checkout -- tests/test_cli_generation_http.py`
before anything else ran; `git diff --stat` printed nothing and `git status
--short` listed no file. The committed assertions are the ones the full-file
run and the quiet loop above passed. (The red run for tests 1-2 is under
"Earlier Proof", at `854190c8`.)

### Static Checks and Gates (`e34d03c8`)

- Black: `1 file would be left unchanged.`
- flake8: no output (exit 0).
- mypy (`--explicit-package-bases`): `Found 2 errors in 1 file`, at `:361
  [str-bytes-safe]` (`yield f"http://{host}:{port}"`) and `:485 [assignment]`
  (`"api_error"`). The `origin/main` copy has the same two on the same lines at
  `:331` and `:455`; both are on untouched lines. No new diagnostics.
- `tests/test_doc_front_matter.py`: `42 passed in 4.65s`, with `dbname audit:
  owner targets: none` (the changed test file is not a declared source of any
  canonical document).
- `python -S scripts/check_exception_dispositions.py --baseline-base-ref
  origin/main`: `OK: exception disposition coverage and shrink-only baseline
  verified.`

## Earlier Proof (Older Commits)

These ran before `e34d03c8`; each names its commit. Unless a block says
otherwise, the runs used `PYTHONPATH=$PWD`, the shared interpreter,
`-p tests.dbname_audit`, and `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`,
`NEXUS_SLOT` unset. Loops up to `d48f91bb` selected `-k "genesis_stage_once or
finished_stage_read or before_its_first_interval_read"` (7 items at
`854190c8` and `d48f91bb`; 5 at `934c3625`).

### Red Run for Test 1 (`854190c8`)

With the old line-748/749 assertions put back temporarily
(`snapshot_reads == 1` and `stages_read[: len(scripted) + 1] == ["idle",
*scripted]`), `-k genesis_stage_once` failed both `interval-read-first` items:

```
E       AssertionError: assert 2 == 1
E       AssertionError: assert 2 == 1
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_cli_generation_http.py::test_cli_prints_each_genesis_stage_once_while_transition_runs[seed-confirm-interval-read-first]
FAILED tests/test_cli_generation_http.py::test_cli_prints_each_genesis_stage_once_while_transition_runs[ready-resume-interval-read-first]
2 failed, 2 passed, 52 deselected in 9.32s
```

With only the old prefix assertion put back (the new count assertion kept):

```
E       AssertionError: assert ['idle', 'idl...didates', ...] == ['idle', 'idl...pansion', ...]
E         At index 2 diff: 'idle' != 'packet'
FAILED tests/test_cli_generation_http.py::test_cli_prints_each_genesis_stage_once_while_transition_runs[seed-confirm-interval-read-first]
FAILED tests/test_cli_generation_http.py::test_cli_prints_each_genesis_stage_once_while_transition_runs[ready-resume-interval-read-first]
2 failed, 2 passed, 52 deselected in 9.30s
```

### Contended Loop before the Fix (`364fef4b`, Unmodified Test)

Eight CPU hogs (pids 44170-44177) on a 16-core host, ten iterations of the
order's selection `-k "genesis_stage_once or finished_stage_read"`. It did
**not** reproduce the 2-read outcome; eight hogs do not saturate this host.

```
hog pids: 44170 44171 44172 44173 44174 44175 44176 44177
loop summary: prefix_contended iterations=10 fails=0
surviving hogs:
none survive
--- last tail (prefix_contended.run10.log)
...                                                                      [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
3 passed, 51 deselected in 6.95s
```

### Quiet Loop (30 Iterations, `854190c8`)

```
loop summary: iterations=30 failed=0
.......                                                                  [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
7 passed, 49 deselected in 13.73s
```

### Contended Loop after the Fix (Eight Hogs, Ten Iterations, `854190c8`)

```
hog pids: 72955 72956 72957 72959 72960 72961 72962 72963
loop summary: fix2_contended iterations=10 fails=0
surviving hogs:
none survive
--- last tail (fix2_contended.run10.log)
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
.......                                                                  [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
7 passed, 49 deselected in 14.59s
```

### Full File (`854190c8`)

```
........................................................                 [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
56 passed in 96.26s (0:01:36)
```

### Loop Selection and Full File after the Id Rename (`d48f91bb`)

Collected ids of test 1:

```
tests/test_cli_generation_http.py::test_cli_prints_each_genesis_stage_once_while_transition_runs[seed-confirm-unforced]
tests/test_cli_generation_http.py::test_cli_prints_each_genesis_stage_once_while_transition_runs[seed-confirm-interval-read-first]
tests/test_cli_generation_http.py::test_cli_prints_each_genesis_stage_once_while_transition_runs[ready-resume-unforced]
tests/test_cli_generation_http.py::test_cli_prints_each_genesis_stage_once_while_transition_runs[ready-resume-interval-read-first]
```

Loop selection:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
====================== 7 passed, 49 deselected in 14.65s =======================
```

Full file:

```
........................................................                 [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
56 passed in 109.65s (0:01:49)
```

Black, flake8 and mypy at `d48f91bb` matched the `e34d03c8` results above
(mypy then at `:350` and `:474`); `tests/test_doc_front_matter.py`:
`42 passed, 5 warnings in 6.21s`.

### Offline Suites (`934c3625`)

`tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
2943 passed, 559 skipped, 8 warnings in 526.43s (0:08:46)
```

`tests/test_api tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1865 passed, 1369 skipped, 7 warnings in 48.21s
```

The skips in both offline runs are the PostgreSQL-backed and corpus tests,
which run only under `NEXUS_RUN_POSTGRES=1` / `NEXUS_RUN_CORPUS=1`; this change
touches no database path. Every commit after `934c3625` changed only
`tests/test_cli_generation_http.py` and this file, and the full-file run at
`e34d03c8` covers that test file; the offline suites were not rerun (the
coordinator's ruling limits this round to the files it names, and the
whole-tree gate at the final commit is the coordinator's).

`tests/test_reachability.py` (`934c3625`):

```
dbname audit: owner targets: none
54 passed in 10.91s
```

## Pre-Existing Diagnostics

`tests/test_cli_generation_http.py:361` (`str-bytes-safe`) and `:485`
(`assignment`) at `e34d03c8`, both on untouched lines (`:331` and `:455` on
`origin/main`).

## Coverage of #1107

Issue #1107 tracked the five tests the order had left out (tests 3-7 above) and
proposed this branch's pattern: a `before`-aware assertion, the
`interval_reads_before_post` parametrization, and a failed-read ordinal
relative to the pre-POST read count for `while-in-flight`. `e34d03c8` applies
all three, and the red run above shows each forced case failing under the old
assertions. With the order's two tests, this branch made seven tests
before-aware. Only these seven tests in `tests/test_cli_generation_http.py`
assert the status reads, and the only one that still pins exactly one pre-POST
read is test 2, by design: its 60 s poll leaves no interval read to race. The
race class in this file is closed, and none of the seven needs a known-flake
exemption.
