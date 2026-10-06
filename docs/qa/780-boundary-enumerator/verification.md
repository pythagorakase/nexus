# Read-Only Crossed-Boundary Enumerator: Verification (#780, 780-S1)

Branch `claude/780-boundary-enumerator`, cut from `origin/main` at `4a063652`
and rebased onto `56c884e7` (migration 139) before the final gate runs.
No migration, no fleet application, no gateway, no paid call. Every family run
below reads one repeatable-read session whose transactions are read-only; the
only writes were the PostgreSQL tests' writes to their own `qa640_780_*`
clones.

## What Is Wrong Today (Cited at `4a063652`)

- **Only claim propagation stamps exact occurrence times.**
  `_plan_propagations` (`nexus/agents/orrery/propagation.py:593-708`) pushes
  every hop onto a heap (`:644`) and pops it in order (`:675`), skips a hop
  scheduled after its `world_time` argument (`:640`), and stamps
  `acquired_at_world_time=scheduled` (`:693`, `:702`).
  `drain_claim_propagation_sync` (`:118-171`) runs it at the accepting clock
  (`_commit_clock_sync`, `:131`; layer check `:132-133`) inside
  `commit_orrery_tick_sync` (`nexus/agents/orrery/events.py:772`).
- **Tag expiry stamps the accepting clock.** `_sweep_expired_entity_tags_sync`
  (`events.py:7944-7990`, called at `:748`) clears every tag with
  `expires_at_world_time <= world_time` and logs `cleared_at_world_time` as
  the accepting chunk's clock.
- **Projects are evaluated at one instant per turn.** `project_due`
  (`nexus/agents/orrery/substrate.py:1398`): due at `:1476`
  (`next_eligible_at_world_time <= state.world_time`); abandon at `:1482-1486`;
  neglected at `:1487-1492`; `project_overdue_hours` at `:1323-1331`; an open
  project without a due time raises at `:1468-1471`. Start, advance and stall
  reschedule from the accepting clock (`_project_next_eligible`,
  `events.py:3242-3243`, called at `:3444`, `:3540`, `:3660`, `:3718`, `:3769`,
  `:3818`); abandon and complete clear the due time (`:3863`, `:4796`). Policy:
  `nexus.toml:449-460`.
- **Travel arrival ignores the ETA.** `travel.start` writes the ETA
  (`events.py:5103`); arrival is gated on `travel_progress_at_or_above(0.95)`
  (`nexus/agents/orrery/templates.py:1906`, `:1928`), stamped at the accepting
  clock (`events.py:5406`), and clears the ETA (`:5430`).
- **The resolver sees only the parent anchor.** `resolve_orrery`
  (`nexus/agents/lore/utils/turn_cycle.py:754`) calls `resolve_dry_run` at
  `:787` without `world_time_override` (`nexus/agents/orrery/resolver.py:2398`);
  the proposal is staged with Gaia's adjudications in one incubator write
  (`nexus/api/narrative_generation.py:340-352`; INSERT `:562`, UPDATE `:590`).
- **One tick cannot hold two crossings of one package and binding.**
  `orrery_resolutions_tick_chunk_id_template_id_binding_hash_key` is
  `UNIQUE (tick_chunk_id, template_id, binding_hash)`, and the table has no
  occurrence-time column (read on `NEXUS_template`, schema 138).
- **Live skips are short and scheduled state is sparse** (read-only SQL):

  | Database | Schema | Largest primary `time_delta` | Primary chunks of 1 day or more | Uncleared expiring tags | Open projects | In transit |
  |---|---|---|---|---|---|---|
  | `ref_codex_bakeoff_2026_07` | 114 | 2:00:00 | 0 | 0 | 0 | 0 |
  | `save_01` | 138 | 88:05:00 | 3 | 0 | 0 | 0 |
  | `save_02` | 138 | 88:05:00 | 3 | 0 | 0 | 0 |
  | `save_03` | 138 | 0:09:00 | 0 | 1 (2189-10-17 18:32-04) | 2 | 0 |
  | `save_04` | 138 | 0:10:00 | 0 | 0 | 2 | 0 |

## Family Runs

`PYTHONPATH=$PWD $PY scripts/qa_shift/boundary_catchup.py --dbname ref_codex_bakeoff_2026_07`,
then `--slot 3` and `--slot 4`. Each exited 0. The fleet reached schema 139
between the SQL above and these runs. "Pending at start" sums
`at_or_before_previous` over the producers.

`ref_codex_bakeoff_2026_07` (schema 114, parent chunk 147, previous clock
2042-08-18T12:50:00+00:00, read-only `on`): the zero baseline.

| Window | `tag_expiry` | `claim_propagation` | `travel_eta` | `project_due` | `project_neglected` | `project_abandon` | Total | Pending at start |
|---|---|---|---|---|---|---|---|---|
| 0 min | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 60 min | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4320 min | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

`save_03` (schema 139, parent chunk 100, previous clock
2189-10-17T22:07:00+00:00, read-only `on`):

| Window | `tag_expiry` | `claim_propagation` | `travel_eta` | `project_due` | `project_neglected` | `project_abandon` | Total | Pending at start |
|---|---|---|---|---|---|---|---|---|
| 0 min | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 60 min | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| 4320 min | 1 | 0 | 0 | 2 | 2 | 0 | 5 | 0 |

The one tag crossing is `entity_tag` 56 at 2189-10-17T22:32:00+00:00 (25
minutes after the head clock). The projects fall due at 2189-10-18T19:12 and
20:32 UTC and are neglected 24 hours later.

`save_04` (schema 139, parent chunk 49, previous clock
2189-10-17T22:37:00+00:00, read-only `on`):

| Window | `tag_expiry` | `claim_propagation` | `travel_eta` | `project_due` | `project_neglected` | `project_abandon` | Total | Pending at start |
|---|---|---|---|---|---|---|---|---|
| 0 min | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 60 min | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4320 min | 0 | 15 | 0 | 2 | 2 | 0 | 19 | 0 |

The 15 hops come from incidents 161, 177 and 178 under the live
`[orrery.contagion]` tiers (trusting 24h, neutral 96h); the first lands at
2189-10-18T10:23:00+00:00.

## Storm Calibration

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit -s tests/test_orrery/test_boundary_enumeration_pg.py -k calibration | grep '^BOUNDARY_CALIBRATION '`

```
BOUNDARY_CALIBRATION {"windows": [{"window": "skip_0m", "source": "projected_child_clock", "counts": {"tag_expiry": 0, "claim_propagation": 0, "travel_eta": 0, "project_due": 0, "project_neglected": 0, "project_abandon": 0}, "total": 0, "max_crossings_per_subject": 0, "wall_clock_ms": 9.1}, {"window": "skip_60m", "source": "projected_child_clock", "counts": {"tag_expiry": 2, "claim_propagation": 5, "travel_eta": 0, "project_due": 1, "project_neglected": 0, "project_abandon": 0}, "total": 8, "max_crossings_per_subject": 1, "wall_clock_ms": 3.6}, {"window": "skip_4320m", "source": "projected_child_clock", "counts": {"tag_expiry": 50, "claim_propagation": 20, "travel_eta": 10, "project_due": 50, "project_neglected": 48, "project_abandon": 10}, "total": 188, "max_crossings_per_subject": 3, "wall_clock_ms": 3.9}, {"window": "target_7d", "source": "target_horizon", "counts": {"tag_expiry": 50, "claim_propagation": 20, "travel_eta": 10, "project_due": 50, "project_neglected": 50, "project_abandon": 10}, "total": 190, "max_crossings_per_subject": 3, "wall_clock_ms": 4.0}, {"window": "target_30d", "source": "target_horizon", "counts": {"tag_expiry": 50, "claim_propagation": 20, "travel_eta": 10, "project_due": 50, "project_neglected": 50, "project_abandon": 50}, "total": 230, "max_crossings_per_subject": 3, "wall_clock_ms": 4.0}]}
```

The synthetic clone holds 50 characters (k = 1..50), each with a tag expiring
at T0+k·30m and one open project due at T0+k·1h (3 stalls when k is divisible
by 5); the first 10 travel with ETA T0+k·6h; 5 chains of 5 characters carry
one claim each, born at T0 (4 hops each at depth cap 4, trusting latency 1h).

| Window | Source | `tag_expiry` | `claim_propagation` | `travel_eta` | `project_due` | `project_neglected` | `project_abandon` | Total | Most per subject | Enumeration ms |
|---|---|---|---|---|---|---|---|---|---|---|
| skip_0m | projected_child_clock | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 9.1 |
| skip_60m | projected_child_clock | 2 | 5 | 0 | 1 | 0 | 0 | 8 | 1 | 3.6 |
| skip_4320m | projected_child_clock | 50 | 20 | 10 | 50 | 48 | 10 | 188 | 3 | 3.9 |
| target_7d | target_horizon | 50 | 20 | 10 | 50 | 50 | 10 | 190 | 3 | 4.0 |
| target_30d | target_horizon | 50 | 20 | 10 | 50 | 50 | 50 | 230 | 3 | 4.0 |

The test asserts every count against closed forms of those constants. The
three project producers share one subject, so a project crosses at most three
boundaries in one window. This slice decides no cap.

## Gates

PostgreSQL proof (`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset):

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_boundary_enumeration_pg.py tests/test_world_clock_contract_pg.py tests/test_prose_metrics_pg.py tests/test_owner_target_guard.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_780_boundaries_*, qa640_780_storm_*, qa640_clock_*, qa640_prose_metrics_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
150 passed, 2 warnings in 17.12s
```

Offline suites (after the rebase):

```
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2668 passed, 428 skipped, 8 warnings in 393.42s (0:06:33)

$ $PY -m pytest -q tests/test_api tests/test_orrery tests/test_reachability.py tests/test_qa_shift.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1940 passed, 750 skipped, 7 warnings in 52.02s
```

The skips are the PostgreSQL-backed tests, which the offline runs leave out.

Black, flake8 and mypy on every changed Python file: Black is clean. flake8
reports six E501 lines in `nexus/config/settings_models.py` (79, 126, 141,
149, 2448, 4384), all present on `origin/main`. mypy reports seven errors in
`settings_models.py` (lines 130-138 and 4382) and two in
`tests/test_qa_shift.py` (lines 181 and 1078); the same errors appear on the
`origin/main` copies of both files (lines 176 and 1062 there). The new files
type-check clean.

A mutation check removed precedence from the sort key only: four tests
failed (`test_three_day_skip_orders_by_instant_then_precedence`,
`test_target_horizon_reaches_abandonment`, `test_family_is_read_only`, and
the offline `test_crossings_order_by_instant_then_precedence`), and the file
was restored from the index.

## Review Fixes (Commit `c715ab45`)

Three confirmed review findings, applied at `c715ab45`; the tails below ran
on that commit.

- `CrossedBoundary.detail` is declared `field(default_factory=dict,
  hash=False)`: a crossing hashes on producer, subject, instant, class,
  precedence and owner issue, and equality still compares `detail`
  (`test_crossing_is_hashable_and_detail_still_compares` asserts
  `len({c, c}) == 1`). Before the fix, `hash()` raised `TypeError` on every
  crossing because the read-only `MappingProxyType` took part in the hash.
- `tests/test_orrery/test_boundary_contract.py` now defines two independent
  producer classes, `DeterministicFixture` and `AdjudicableFixture`, each
  declaring name, class, precedence and owner issue as class attributes and
  returning its own crossings from `scan()`. The name and precedence clashes
  are small subclasses; the stamping-mismatch cases use their own
  `MisstampedFixture`.
- The stale fixture tag in `test_boundary_enumeration_pg.py` is applied at
  T0−70m and expires at T0−10m, so the zero-time
  `at_or_before_previous["tag_expiry"] == 1` rests on a tag that really
  lapsed and is still uncleared.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_boundary_enumeration_pg.py tests/test_world_clock_contract_pg.py tests/test_prose_metrics_pg.py tests/test_owner_target_guard.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_780_boundaries_*, qa640_780_storm_*, qa640_clock_*, qa640_prose_metrics_*, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
150 passed, 2 warnings in 15.40s

$ $PY -m pytest -q tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1199 passed, 512 skipped, 7 warnings in 9.01s

$ $PY -m pytest -q tests/test_orrery/test_boundary_contract.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
74 passed, 5 warnings in 9.87s
```

Black, flake8 and `mypy --explicit-package-bases` are clean on the three
changed files. The calibration is unchanged: the storm clone does not use the
stale tag.
