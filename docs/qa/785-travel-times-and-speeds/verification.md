# 785-S2 Verification: Travel Times and Route Speeds

Work order 785-S2 (issue #785). Branch `claude/785-travel-times-and-speeds`, cut
from `origin/main` at `9fff6a75`. No migration, no paid call, no gateway lane.
No `save_NN` or `NEXUS_template` was written; every database read below ran
in a `BEGIN READ ONLY` transaction or against a disposable `qa640_785s2_*`
clone.

## Cited Lines (Checked on `origin/main` at `9fff6a75`)

| Claim | Location |
| --- | --- |
| `TravelState` has no time field | `nexus/agents/orrery/substrate.py:189-209` |
| `WorldState.world_time` exists | `nexus/agents/orrery/substrate.py:382` |
| `_load_travel_states` selects eleven columns plus `route_metadata ->> 'purpose'`, no world times | `nexus/agents/orrery/resolver.py:892-945` |
| Callers of `_load_travel_states` | `resolver.py:754`, `audit.py:2435` |
| `travel.start` reads the tick clock | `events.py:5067` (`_tick_world_time_sync`) |
| ETA computed from the route duration | `events.py:5103`; `_eta` at `events.py:7876-7879` |
| Insert writes `world_time, world_time, eta` | `events.py:5153-5155` (sync), `events.py:5174`, `:5261-5263` (async) |
| Hover audit emits `asdict(travel)` beside its own `_iso` clock | `audit.py:2577`, `audit.py:2585`, `_iso` at `audit.py:1203-1204` |
| Travel evidence observes only `progress_ratio` | `evidence.py:951-968` |
| Module literals (the detour-factor and speed dicts) | `events.py:224-232`, `events.py:233-241` |
| Literal read sites | `events.py:4999` (`_travel_mode`), `:7377` (sync graph), `:7424` (async graph), `:7846-7847` (estimate) |
| Existing route-graph config only | `nexus.toml:614-615` |
| `travel.advance` delta (unchanged, out of scope) | `events.py:5278` |

`NEXUS_template`, `\d+ character_travel_states` (read-only):

```
 started_at_world_time      | timestamp with time zone | ... | World time when the current in-transit journey began.
 updated_at_world_time      | timestamp with time zone | ... | Most recent world time at which Orrery updated this travel state.
 eta_world_time             | timestamp with time zone | ... | Estimated world-time arrival for the current route, when duration is known.
```

`SELECT enum_range(NULL::orrery_travel_mode)` on `NEXUS_template`:
`{walking,vehicle,rail,water,air,covert,mixed}`, the seven keys of both
literals and of `OrreryTravelModeTable`.

## Live Travel Rows (Read-Only)

`SELECT status::text, count(*), count(started_at_world_time),
count(updated_at_world_time), count(eta_world_time) FROM character_travel_states
GROUP BY 1` inside `BEGIN READ ONLY`:

```
== save_01
at_place|35|0|0|0
total|35
== save_02
at_place|35|0|0|0
total|35
== save_04
total|0
== ref_codex_bakeoff_2026_07
total|0
```

No live row carries a journey time, so the hydration proof is a seeded,
disposable clone (`tests/test_orrery/test_travel_times_pg.py`).

## PostgreSQL Proof

`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset:

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit \
  tests/test_orrery/test_travel_times_pg.py tests/test_orrery/test_adjudication_history.py \
  tests/test_orrery/test_need_clock_anchor_pg.py tests/test_orrery/test_replay.py \
  tests/test_owner_target_guard.py
```

```
........................................................................ [ 55%]
.........................................................                [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 22 targets: postgres, qa640_* x18, qa640_785s2_*, qa640_replay_*, qa885_adjudication_history_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
129 passed in 17.73s
```

## Red Run

A scratch plant restored both literal tables, the literal at the sync graph
site (`events.py:7377`), and the literals at the estimate site
(`events.py:7846-7847`). It was reverted byte-for-byte from a saved copy
before any commit (`cmp` clean), and the grep below is empty afterward.

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit \
  tests/test_orrery/test_travel_times_pg.py tests/test_orrery/test_routing.py
```

```
E       assert 1.35 == 2.0
E           assert 12.0 == 6.0 ± 1.0e-06
E             Obtained: 12.0
E             Expected: 6.0 ± 1.0e-06
E       assert 1350.0 == 2000.0 ± 1.0e-06
E         Obtained: 1350.0
E         Expected: 2000.0 ± 1.0e-06
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_travel_times_pg.py::test_hydration_returns_the_times_travel_start_wrote
FAILED tests/test_orrery/test_travel_times_pg.py::test_graph_route_speed_comes_from_config
FAILED tests/test_orrery/test_routing.py::test_route_estimate_reads_configured_speed_and_detour
3 failed, 7 passed in 2.03s
```

A second plant at the async graph site alone (`events.py:7424`) also fails
`test_graph_route_speed_comes_from_config` (`assert 12.0 == 6.0 ± 1.0e-06`,
`1 failed in 1.65s`), so each graph site is guarded.

## Offline Suites

```
$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2661 passed, 420 skipped, 8 warnings in 422.03s (0:07:02)

$PY -m pytest -q tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1181 passed, 508 skipped, 7 warnings in 11.46s

$PY -m pytest -q tests/test_api
secret-store guard: active; nexus-api: denied; disposable keychain: denied
641 passed, 237 skipped, 7 warnings in 27.10s

$PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.29s
```

The `tests/test_api tests/test_orrery` run was split by directory for the
ten-minute shell limit.

## Static Checks

- Black: `11 files would be left unchanged.` over every changed Python file.
- flake8: the new and test files are clean. `audit.py` (3), `resolver.py` (1)
  and `settings_models.py` (6) report the same E501 count on `origin/main` as
  on this branch; none is on a changed line.
- mypy on the six changed product files: the sorted error list (line numbers
  stripped) is identical to `origin/main`'s (15 errors, all pre-existing). The
  new PostgreSQL test adds the `asyncpg` `import-untyped` note that every
  existing `import asyncpg` test carries.
- `git grep -nE "TRAVEL_MODE_(SPEED_KMH|DETOUR_FACTOR)" -- nexus scripts tests docs`:
  empty (exit 1).
