# Issue #1100 Verification: The Genesis-Stage CLI Test Counts Reads Deterministically

Test-only change to `tests/test_cli_generation_http.py`. No migration, no gateway
lane, no paid call (token usage: 0). `nexus/cli.py` is unchanged.

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
invariant holds whatever the pre-POST read count is.

### Request Traces (Scratch Probe, Not Committed)

The scratch probes live in `/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1100/` and run from the worktree root as
`PYTHONPATH=$PWD $PY <scratch>/1100/<probe>.py`, where `<scratch>` is the
session scratchpad and `$PY` the shared interpreter:

- `probe_trace.py`: the request traces below.
- `probe_new_assertions.py`: the eight-run 1 ms tally below.
- `probe_siblings.py`: the sibling-test results under "Out of Scope".
- `probe_race.py <interval> <runs>`: pre-POST read counts at a given poll.
- `contended.sh <label> <iterations> <k-expr>`: the loop driver for the
  contended runs (starts eight hogs, records their pids, kills them by pid,
  and checks with `ps` that none survive).

The committed `interval-read-first` parametrization (see "Forced Early Read")
now proves the multi-read path in every run, so these probes are background
evidence, not the proof.

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

## What Changed

- `GenerationScenario.snapshot_served` (new): the record each pre-POST read
  served; the fake gateway appends `stage_before` in the pre-POST branch. The
  order requires the assertion on it, so it stays, but it is true by
  construction: it is a structural guard on the fake gateway, not a check of
  CLI behavior. What detects a stage line printed by an early read is the
  exact six-line `_stage_lines(stdout)` assertion together with the
  `stages_read` prefix, run with a forced early read (next item).
- `GenerationScenario.interval_reads_before_post` and `pre_post_reads_seen`
  (new, commit `854190c8`): when the field is non-zero, the fake gateway's
  transition POST handler waits on the Event before it sets
  `transition_posted`; the status handler sets the Event once
  `snapshot_reads >= 1 + interval_reads_before_post`. The wait is bounded at
  10 seconds and fails the test with `interval read never arrived`. No sleep.
- `test_cli_prints_each_genesis_stage_once_while_transition_runs`: now
  parametrized over `interval_reads_before_post` in `[0, 1]`
  (`posted-first`, `interval-read-first`), four items in all; `snapshot_reads
  == 1` became `>= 1 + interval_reads_before_post`; a new assertion requires every pre-POST read to have
  served `stage_before`; the stage-sequence assertion now starts after
  `snapshot_reads` pre-POST "idle" reads rather than exactly one. With one
  pre-POST read it states exactly what the old assertion stated. The six-line
  stage assertion, the single terminal `done` read, and the narrative ordering
  are unchanged.
- `test_cli_prints_a_terminal_stage_recorded_before_its_first_interval_read`:
  `snapshot_reads == 1` became `>= 1` plus the same `snapshot_served`
  assertion. This test runs the reader at a 60 s interval, so its exact
  `stages_read == [before["stage"], "failed"]` assertion (unchanged) still pins
  one pre-POST read, so the loosened count has no effect there; the comment
  above it now says so.

## Proof

All runs from the worktree root with `PYTHONPATH=$PWD`, the shared interpreter,
`-p tests.dbname_audit`, and `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT`
unset. The loops select the order's two tests plus the line-840 sibling:
`-k "genesis_stage_once or finished_stage_read or before_its_first_interval_read"`
(7 test items at `854190c8`; 5 at `934c3625`, before the forced-read
parametrization). The quiet loop, the contended-after loop, the full file and
the static checks below ran at `854190c8`; the contended-before loop ran at
`364fef4b` and the offline suites at `934c3625`.

### Forced Early Read: Red, Then Green

At `854190c8`, with the old line-748/749 assertions put back temporarily
(`snapshot_reads == 1` and `stages_read[: len(scripted) + 1] == ["idle",
*scripted]`), `-k genesis_stage_once` fails both `interval-read-first` items:

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

With the committed assertions restored, the same selection passes all four
items, and the loops below pass all seven.

### Contended Loop before the Fix (Unmodified Test)

Eight CPU hogs (pids 44170-44177) on a 16-core host, ten iterations of the
order's selection `-k "genesis_stage_once or finished_stage_read"`. It did
**not** reproduce the 2-read outcome; the race needs more contention than
eight hogs give a 16-core host.

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

### Quiet Loop after the Fix (30 Iterations, `854190c8`)

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
touches no database path.

`tests/test_reachability.py`:

```
dbname audit: owner targets: none
54 passed in 10.91s
```

`tests/test_doc_front_matter.py` (the changed test file is not a declared
source of any canonical document), rerun at `854190c8`:

```
dbname audit: owner targets: none
42 passed in 4.54s
```

`python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`
(rerun at `854190c8`):
`OK: exception disposition coverage and shrink-only baseline verified.`

### Static Checks

- Black: `1 file would be left unchanged.`
- flake8: no output on the branch file and on the `origin/main` copy.
- mypy (`--explicit-package-bases`): the branch file reports two diagnostics,
  `:350 [str-bytes-safe]` and `:474 [assignment]`; the `origin/main` copy
  reports the same two at `:331` and `:455` (shifted by the lines this branch
  adds above them), plus two `import-untyped` notes that come only from
  checking the copy outside the repository. No new diagnostics.

## Pre-Existing Diagnostics

`tests/test_cli_generation_http.py:350` (`str-bytes-safe`) and `:474`
(`assignment`), both on untouched lines.

## Out of Scope, Noted for the Coordinator

The same pre-POST interval read can shift `stages_read` in two other tests of
this file that the order keeps out of scope by name. At a 1 ms interval a
scratch probe saw:

```
finished_stage_read (757): code=0 snapshot_reads=2 stages_read=['idle', 'idle', 'idle', 'packet', 'done']
previous_runs_failure (795): code=0 snapshot_reads=2 stages_read=['failed', 'failed', 'failed', 'idle', 'packet']
```

`test_cli_stops_reading_at_a_finished_stage_read_before_the_answer` asserts
`stages_read == ["idle", "idle", "packet", "done"]` and
`test_cli_reads_past_the_previous_runs_failure_record` asserts
`stages_read[:4] == ["failed", "failed", "idle", "packet"]`; both run the reader
at the default 20 ms interval and can fail the same way under heavy load.

(The numbers in the probe's labels are the probe script's own stale line
references; at `854190c8` the two tests start at lines 792 and 830, with the
exact assertions at lines 801 and 845.)

Follow-up: https://github.com/pythagorakase/nexus/issues/1107 tracks both
tests, with the same pattern this branch applies (a `before`-aware prefix and
the `interval_reads_before_post` parametrization). Until it lands, both test
ids are known flakes under heavy load. Adding them to the known-flake
exemption in the session's common rules is the coordinator's step; this
branch does not edit that file.
