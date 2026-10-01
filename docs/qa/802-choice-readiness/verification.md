# Verification: Choice Readiness and the Manifest's Window Counts (#802 S1a)

Work order 802-S1a, branch `claude/802-choice-readiness-observation`, cut from
`origin/main` at `9fff6a75`. No migration, no paid call, no gateway lane of its
own, no write to any `save_NN` or `NEXUS_template`.

## Cited Lines, Rechecked at `9fff6a75`

Each line the order cites was read in this worktree before the change.

- `nexus/telemetry/turn_observation.py:249-338`: `derive_turn_observation`
  returned no readiness key (`:321-338`); `SCHEMA_VERSION = 1` (`:95`).
- `:705-736`: `_phase_spans` ended `wall_time` at the last observed phase,
  whatever it was (`:730-735`).
- `migrations/124_attempt_manifests.sql:68-73`: `generation_session_phases.recorded_at`
  defaults to `clock_timestamp()`. The trigger function (`:80-95`) inserts a row
  on INSERT and on each change of `phase`. Its live body on `NEXUS_template`
  (read with `SELECT prosrc FROM pg_proc WHERE proname='record_generation_session_phase'`)
  is the same text.
- `nexus/api/narrative_lease.py:515`: `finish_generation(..., status="complete")`
  sets `phase = 'complete'`. `nexus/api/narrative_generation.py:632-633`:
  `write_to_incubator` calls it inside the staging transaction, after
  `report_generation_phase("staging")` (`:375`).
- The other `phase = 'complete'` writers act on a draft that is already
  complete: accept (`nexus/api/commit_handler_sync.py:533`) and supersede
  (`nexus/api/narrative_generation.py:624`). The heartbeat writes `phase` only
  while `status = 'initiated'` (`narrative_lease.py:594-598`), and a complete
  session refuses the error downgrade (`:491-501`).
- `nexus/telemetry/usage.py:81-82`, `:100`: `UsageEvent.ts` defaults to the
  moment the event is built; the recorders build it after the response returns
  (`:625-642`, `:668-684`).
- `usage.py:543-566`: `record_token_estimate` adds cache reads and writes to
  `anthropic_messages` input (`:550-554`).
  `nexus/telemetry/attempt_manifest.py:241-266`: `record_token_counts` merges
  both counts into `window_record` with jsonb `||` (`:250-258`).
- `attempt_manifest.py:100-109` names six `PromptWindowRecord` fields, and
  that model (`nexus/telemetry/prompt_window.py:229-246`) has no estimate
  field, so the include set filters nothing out. `attempt_manifest.py` is
  unchanged.
- Readers of the observation: `nexus/cli.py:4385` (`observe_turn`) and
  `:5797-5799` (`format_turn_summary`) only. The order cited `:4377` and
  `:5789-5791` at `41783c1d`; later commits on `main` moved them by 8 lines. No
  gateway module and no client code imports the module
  (`grep -rn turn_observation nexus ui/client/src scripts`).

## Read-Only Fleet Counts (2026-10-01, Inside `BEGIN READ ONLY`)

```
save_01: 0 phase rows, 0 manifest rows, max migration 138
save_02: 0 phase rows, 0 manifest rows, max migration 138
save_03: 0 phase rows, 0 manifest rows, max migration 138
save_04: 0 phase rows, 0 manifest rows, max migration 138
save_05: 0 phase rows, 0 manifest rows, max migration 138
NEXUS_template: 0 phase rows, 0 manifest rows, max migration 138
```

## PostgreSQL Proof

`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset:

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit --basetemp <scratch>/basetemp \
  tests/test_api/test_attempt_manifest_pg.py tests/test_api/test_seat_policy_jobs_pg.py \
  tests/test_lore/test_token_estimator.py tests/test_owner_target_guard.py
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 10 targets: postgres, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_800b_inspect_*, qa640_802_reported_*, qa640_814_seats_*, qa640_818_estimate_*, qa640_818_pin_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
120 passed, 9 warnings in 54.66s
```

The TEST turn stored an estimate for both seats, so the swallowed-failure stop
condition did not arise. `turn-observation.json` and `turn-summary.txt` in this
directory were copied from that run's `--basetemp`
(`test_manifest_real_test_turn_a0/`). In them, `choice_ready_at` is
`2026-10-01T04:53:39.882869Z`, the `complete` row. Readiness came 11.059392 s
after the first phase. The writer's response arrived at `04:53:39.459484Z` and
Gaia's at `04:53:39.782408Z`, both before readiness. Each seat's window reads
`reported 1,000`, equal to its usage `in 1,000`. The estimates are 6,011 for the
writer and 8,629 for Gaia.

## Red Runs (Scratch Plants, Reverted Before Commit)

Plant 1, readiness taken from the wall's end (in `derive_turn_observation`):
`choice_ready_at, seconds_to_choice_ready = wall_time["ended_at"], wall_time["seconds"]`.

```
$PY -m pytest -q tests/test_turn_observation.py -k choice_readiness
>       assert failed["choice_ready_at"] is None
E       AssertionError: assert '2026-10-01T00:00:11.125000Z' is None
1 failed, 16 deselected, 5 warnings in 0.59s
```

Plant 2, `_window` without `estimated_input_tokens` and `reported_input_tokens`:

```
$PY -m pytest -q tests/test_turn_observation.py -k window_projects
E       KeyError: 'estimated_input_tokens'
1 failed, 16 deselected, 5 warnings in 0.61s

NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_attempt_manifest_pg.py -k normalised_reported
E           KeyError: 'reported_input_tokens'
dbname audit: owner targets: none
FAILED tests/test_api/test_attempt_manifest_pg.py::test_observation_projects_normalised_reported_input
1 failed, 4 deselected, 5 warnings in 1.61s
```

`git checkout -- nexus/telemetry/turn_observation.py` reverted each plant;
`git diff --stat` was empty afterwards.

## Offline Gates

```
$PY -m pytest -q tests/test_turn_observation.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
17 passed, 5 warnings in 1.53s

$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2656 passed, 420 skipped, 8 warnings in 411.22s (0:06:51)

$PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1820 passed, 743 skipped, 7 warnings in 39.57s

$PY -m pytest -q tests/test_reachability.py tests/test_turn_observation.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
71 passed, 5 warnings in 12.06s
```

The skips in the offline runs are the PostgreSQL-marked tests, which run only
with `NEXUS_RUN_POSTGRES=1` (the PostgreSQL proof above).

## Lint, Format and Types

- `black --check` on the three changed Python files: unchanged.
- `flake8` on `nexus/telemetry/turn_observation.py` and
  `tests/test_turn_observation.py`: clean. On
  `tests/test_api/test_attempt_manifest_pg.py`: 15 `E501` lines, the same count
  as `origin/main` (long SQL literals that were already there; the new test adds
  none).
- `mypy` on the three files: one error, `Library stubs not installed for
  "requests"`, from the existing `import requests` at
  `tests/test_api/test_attempt_manifest_pg.py:10`. The change adds none.
