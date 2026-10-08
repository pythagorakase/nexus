# Travel Parts A/B Evidence

Verified October 8, 2026 in `claude/785-travel-trio`, continuing implementation
commits `d63e6a43` and `d3433dbb`, based on `origin/main` `afd034f3`.
This records focused Parts A/B proof. Part C sources and calibration are in
[calibration.md](calibration.md); the coordinator owns final integration and
canonical-document freshness. No full-suite gate is claimed here.

## Native Arrival Diagnostic (785-S1b)

The production accepted-turn fixture stages through `resolve_dry_run` and accepts
through `commit_orrery_tick_sync`; the test invokes neither directly. Two
independent disposable stories use the same seeded IDs and 32 fixed corpus
continuation deltas, without querying the reference corpus during the test.
The test overwrites the trigger-seeded socialize need row with debt 200 because
no production writer establishes standing debt without elapsed play.

The coordinator's amendment adds `urban_dense` to Repro Origin. An untagged
fixed location fails `can_move_publicly`, preventing every departure at the
ordered seed. `urban_dense` opens public movement without making the origin
a social venue. The seed and reason are retained in the test docstring.

Both runs depart at continuation 1, world time 2073-08-01 12:04 UTC, and arrive
at continuation 10, 12:35 UTC: departure offset 9. The test does not pin that
offset. Fast ETA is 8.395315 seconds after departure; slow ETA is about
27 hours 59 minutes after departure. Every committed package and event from
departure through arrival is identical. Fast travel stays in transit past its
ETA; slow travel arrives before its ETA. This deliberately reproduces the
arrival defect; 785-S3a will invert those expectations. `templates.py` is unchanged.

Offset -1 below is bootstrap. ETA clears when the arrival writer moves the
traveler to `at_place`; the departure ETA is retained in the test assertion.

### Fast Run (600.0 km/h)

| Departure offset | World time | Template | Event | Progress | ETA |
|---:|---|---|---|---:|---|
| -1 | 2073-08-01T12:00:00+00:00 | — | — | None | None |
| 0 | 2073-08-01T12:04:00+00:00 | socialize | social_travel_departed | 0.05 | 2073-08-01T12:04:08.395315+00:00 |
| 1 | 2073-08-01T12:07:00+00:00 | travel | travel_delayed | 0.05 | 2073-08-01T12:04:08.395315+00:00 |
| 2 | 2073-08-01T12:09:00+00:00 | travel | travel_progressed | 0.4 | 2073-08-01T12:04:08.395315+00:00 |
| 3 | 2073-08-01T12:12:00+00:00 | travel | travel_progressed | 0.75 | 2073-08-01T12:04:08.395315+00:00 |
| 4 | 2073-08-01T12:16:00+00:00 | travel | travel_delayed | 0.75 | 2073-08-01T12:04:08.395315+00:00 |
| 5 | 2073-08-01T12:20:00+00:00 | socialize | socialized_alone | 0.75 | 2073-08-01T12:04:08.395315+00:00 |
| 6 | 2073-08-01T12:23:00+00:00 | travel | travel_prepared | 0.75 | 2073-08-01T12:04:08.395315+00:00 |
| 7 | 2073-08-01T12:27:00+00:00 | travel | travel_progressed | 1.0 | 2073-08-01T12:04:08.395315+00:00 |
| 8 | 2073-08-01T12:31:00+00:00 | travel | travel_delayed | 1.0 | 2073-08-01T12:04:08.395315+00:00 |
| 9 | 2073-08-01T12:35:00+00:00 | travel | travel_arrived | 0.0 | None |

### Slow Run (0.05 km/h)

| Departure offset | World time | Template | Event | Progress | ETA |
|---:|---|---|---|---:|---|
| -1 | 2073-08-01T12:00:00+00:00 | — | — | None | None |
| 0 | 2073-08-01T12:04:00+00:00 | socialize | social_travel_departed | 0.05 | 2073-08-02T16:03:03.774999+00:00 |
| 1 | 2073-08-01T12:07:00+00:00 | travel | travel_delayed | 0.05 | 2073-08-02T16:03:03.774999+00:00 |
| 2 | 2073-08-01T12:09:00+00:00 | travel | travel_progressed | 0.4 | 2073-08-02T16:03:03.774999+00:00 |
| 3 | 2073-08-01T12:12:00+00:00 | travel | travel_progressed | 0.75 | 2073-08-02T16:03:03.774999+00:00 |
| 4 | 2073-08-01T12:16:00+00:00 | travel | travel_delayed | 0.75 | 2073-08-02T16:03:03.774999+00:00 |
| 5 | 2073-08-01T12:20:00+00:00 | socialize | socialized_alone | 0.75 | 2073-08-02T16:03:03.774999+00:00 |
| 6 | 2073-08-01T12:23:00+00:00 | travel | travel_prepared | 0.75 | 2073-08-02T16:03:03.774999+00:00 |
| 7 | 2073-08-01T12:27:00+00:00 | travel | travel_progressed | 1.0 | 2073-08-02T16:03:03.774999+00:00 |
| 8 | 2073-08-01T12:31:00+00:00 | travel | travel_delayed | 1.0 | 2073-08-02T16:03:03.774999+00:00 |
| 9 | 2073-08-01T12:35:00+00:00 | travel | travel_arrived | 0.0 | None |

## Routability Proof (785-S3d)

The new `tests/test_orrery/test_travel_routable_destinations_pg.py` uses real
psycopg2, asyncpg, SQLAlchemy hydration and commit writers on disposable
`qa640_785s3d_*` databases. Each story creates the uncharted venue before the
charted venue in the same zone, so the old chooser ordering selects the wrong
place. The 12 cases cover:

- Both class choosers choose the charted venue; a real accepted travel write
  records that destination and a non-NULL ETA.
- Hydrated gates and evidence reject the sole uncharted venue and report one
  unroutable destination, then accept it after coordinates are recorded.
- Timed authored edges permit uncharted travel, including reverse bidirectional
  edges, for gates, both class twins and both fixed-anchor twins. NULL-duration,
  graph-method and reverse one-way edges do not qualify.
- Relocation scouts and fixed/zone anchors choose only routable destinations.
- Planned travel, relocation completion and explicit destinations are refused
  before a draft exists; explicit destinations take precedence over either
  class or anchor selectors.
- Both commit twins recheck duration and raise before writing travel. After
  transaction rollback the full travel, resolution and event snapshots match.

The inherited offline contract failures were repaired by giving `RecordingCursor`
and `AsyncRoutineConn` explicit charted-place/edge knowledge and passing the
new origin argument. The old authored-edge NULL-ETA test now requires a refusal
and proves no travel INSERT ran. `RICH_STATE` in `test_evidence.py` charts its
existing places, preserving its positive predicate coverage.

Offline cases changed across the branch:

- `test_events.py`: `test_commit_orrery_tick_resolves_travel_destination_by_place_class`,
  `test_commit_orrery_tick_resolves_travel_destination_anchor`,
  `test_commit_orrery_tick_resolves_work_from_home_anchor`,
  `test_sync_malformed_home_work_from_home_anchor_fails_closed`,
  `test_async_routine_anchor_destination_resolves_work_from_home`,
  `test_async_routine_anchor_destination_resolves_zone`,
  `test_async_location_class_destination_resolves_place`,
  `test_async_malformed_home_work_from_home_anchor_fails_closed`, and renamed
  `test_commit_orrery_tick_refuses_authored_route_without_duration`.
- `test_substrate.py`: `test_work_from_home_anchor_resolves_against_home_anchor`,
  `test_location_class_destination_condition_finds_other_places`,
  `test_location_class_destination_condition_supports_legacy_single_class`,
  and new `test_route_known_rule`.
- `test_resolver.py`: `test_resolve_dry_run_fires_socialize_need_template`,
  `test_resolve_dry_run_fires_travel_departure_from_planned_destination`,
  `test_routine_commute_sends_actor_home_after_work_window`, plus both hydration
  labels in the fake session.
- `test_catalog.py`: `test_render_predicate_name_handles_known_predicates`.
  `test_projects.py` shared `_state` and `test_evidence.py` shared `RICH_STATE`
  now chart their existing destination fixtures.

### Negative Control

A scratch-only mutation removed the routability clause from the synchronous
class chooser and disabled `_refuse_route_without_duration`. A Python `finally`
restored the original `events.py` bytes, verified equal, before the green proof.
Command selection was the new PG file with
`-k 'location_class_chooser_skips_uncharted or commit_refuses_route_without_duration'`.
The expected failure tail was:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: postgres, qa640_785s3d_* x3
dbname audit: owner targets: none
FAILED tests/test_orrery/test_travel_routable_destinations_pg.py::test_location_class_chooser_skips_uncharted
FAILED tests/test_orrery/test_travel_routable_destinations_pg.py::test_commit_refuses_route_without_duration[sync]
FAILED tests/test_orrery/test_travel_routable_destinations_pg.py::test_commit_refuses_route_without_duration[async]
3 failed, 9 deselected in 4.76s
```

## Focused Verification

Interpreter: `/Users/pythagor/nexus/.venv/bin/python`. `PYTHONPATH=$PWD` resolved
`nexus.__file__` into this worktree. All pytest sessions used `nice -n 15`.
One-minute load was 5.06 before the combined PostgreSQL run, below 24.
Gateway/API/slot overrides and live-provider overrides were unset. The provider
and secret-store guards remained active. Raw focused, negative-control and
static logs are in worktree-local `temp/qa785-codex/`.

Offline:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_RUN_POSTGRES -u NEXUS_LIVE_LLM PYTHONPATH="$PWD" \
  nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q \
  tests/test_orrery/test_events.py tests/test_orrery/test_substrate.py \
  tests/test_orrery/test_resolver.py tests/test_orrery/test_evidence.py \
  tests/test_orrery/test_catalog.py tests/test_orrery/test_projects.py
```

```text
355 passed, 3 skipped, 5 warnings in 1.88s
```

Combined focused PostgreSQL proof (native output retained with `-s`):

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH="$PWD" \
  nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s \
  -p tests.dbname_audit \
  tests/test_orrery/test_travel_native_repro_pg.py \
  tests/test_orrery/test_travel_routable_destinations_pg.py \
  tests/test_orrery/test_travel_times_pg.py tests/test_travel_reachability_pg.py \
  tests/test_orrery/test_projects.py tests/test_orrery/test_card_identity.py \
  tests/test_connection_lifecycle.py tests/test_pg_disposable_target.py \
  tests/test_owner_target_guard.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 26 targets: mock, postgres, qa640_785_reach_* x3, qa640_785s1b_fast_*, qa640_785s1b_slow_*, qa640_785s2_*, qa640_785s3d_* x12, qa640_885_ren_replay_* x4, qa885_project_promotion_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:56064 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:56065 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:56064 (psycopg2), save_04@local:56065 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
183 passed, 3 skipped, 2 warnings in 74.53s (0:01:14)
```

The skipped cases require the separately gated reference corpus. Native and all
12 routability PostgreSQL cases ran. The isolated temporary clusters using the
name `save_04` were registered disposable servers, not the owner's slot databases.

Static commands used the 13 changed Parts A/B Python files: five Orrery modules
(`catalog`, `events`, `evidence`, `resolver`, `substrate`), six existing offline
files named above, and both new travel PG files.

- `python -m black --check <files>`: all 13 unchanged.
- `python -m flake8 <files>`: one existing `E501` in resolver (line 1396;
  origin/main line 1364), no new diagnostics.
- `python -m mypy --explicit-package-bases <files>`: 16 existing errors in four
  files; origin/main versions of the 11 pre-existing files report the same 16.
  Diagnostic multisets, normalized only for line numbers, match exactly.
  Both added PG files have no diagnostics.
- `python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`:
  `OK: exception disposition coverage and shrink-only baseline verified.`
- `python -m nexus.agents.orrery.catalog --check`: success.

Pre-existing mypy diagnostics are six resolver errors involving nullable sorting
keys, two events sorting-key errors, two substrate-test Slot key errors, and six
event-test fixture typing errors. Baseline source was exported from
`origin/main` to worktree scratch; no other checkout was modified for comparison.

## Fleet Survey (Read-Only)

Fresh October 8 survey used one read-only, repeatable-read transaction per
database and asserted `SHOW transaction_read_only = on`. Queries were
`SELECT count(*), count(coordinates) FROM places`, `SELECT count(*)` for each
listed table, and grouped `status`, `count(*)`, `count(destination_place_id)`
from `character_travel_states`. Every transaction rolled back and closed.

| Database | Charted/total places | Travel edges | Graph edges | Place graph nodes | Routine anchors | Travel states |
|---|---:|---:|---:|---:|---:|---|
| save_01 | 50/77 | 0 | 0 | 0 | 0 | 35 at_place; all destinations NULL |
| save_02 | 50/77 | 0 | 0 | 0 | 0 | 35 at_place; all destinations NULL |
| save_03 | 2/5 | 0 | 0 | 0 | 0 | 0 |
| save_04 | 2/7 | 0 | 0 | 0 | 0 | 0 |
| save_05 | 0/0 | 0 | 0 | 0 | 0 | 0 |
| ref_codex_bakeoff_2026_07 | 16/16 | 0 | 0 | 0 | 0 | 0 |

Thus 27 uncharted places in each of save_01/save_02, three in save_03 and five
in save_04 remain unavailable to destination choosers until charting or a timed
authored edge establishes a route. There is no migration or fleet application.

## Independent Corpus Check

The calibration review inspected all second-occurrence context windows in the
coordinator's 289 candidate excerpts, including ordinals, and expanded the
potential movement/timing passages in chunks 31, 49, 57, 65, 67, 75, 83, 107,
134 and 139–142. No additional complete bounded journey with two registered
endpoints and a stated elapsed travel duration was found. In particular, chunks
65/67 describe manufactured-emergency and diversion windows, chunk 75 a message
reply, chunk 107 a shutter deadline, and chunk 142 a partial skiff segment of
unspecified length. These do not justify a corpus calibration pair.

Remaining work belongs to the coordinator: Part C completion, canonical source
restamps, final integration gate, independent review and PR creation. Later #785
slices retain elapsed-time progress, delay factors, crossed-ETA arrival and replay
provenance. Owner services were not started or restarted; no paid calls occurred.

Codex — GPT-6
