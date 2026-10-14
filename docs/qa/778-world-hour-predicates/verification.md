# 778-S3 World-Hour Predicates: Source Checkpoint

Status: **proved on the integrated wave-B tree (2026-10-13)**, except the steps
named "coordinator's step" below. The lane implemented frozen `778-S3.md` on base
`4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8` (Codex, source only). Its integrated
range is `8d2e4999..c8abc33f`; the fixer branch `claude/waveb-fix-778-s3` was cut
from the integration head `7eb9a10c` (origin/main `f073b371` plus fifteen wave-B
lanes, the 777 shell and a palette commit). Every run below names the commit it
ran on.

## Contract and Implementation

The binding [778-Q5 decision](https://github.com/pythagorakase/nexus/issues/778#issuecomment-5922751866)
was re-read on 2026-10-08 and still selects an occurrence-time horizon. The
order's 2026-10-07 fleet survey is historical; the fresh read-only survey is in
"Integrated-Tree Proof (2026-10-13)" below and matches it.

- `substrate.py` appends optional occurrence time to `EventRecord`.
  `WorldState` retains `charted_place_ids` and `timed_route_pairs` from 785,
  adds a separate validated dated horizon and immutable candidate buckets,
  and leaves the tick tuple and its predicates intact. The four new factories
  follow the tick forms' binding, fields and epistemics behavior, measuring
  occurrence time with an inclusive floor. Every evaluation first refuses a
  missing/naive clock or insufficient configured horizon. Since-last compares
  the latest occurrence with that floor, equivalent to elapsed time being at
  least the requested interval; it never selects by latest tick.
- `resolver.py` validates the horizon (`coerce_event_horizon_hours`), with the
  shipped default read only when no explicit value is supplied.
  `hydrate_world_state` rejects a naive clock by anchor name before history
  loading, and its docstring now states the naive-clock refusal and the
  `event_horizon_hours` parameter. `_load_event_history` performs one ordered,
  anchor-bounded query and partitions each row's single `EventRecord` into
  tick and/or dated history. Undated Retrograde rows remain eligible for tick
  reads and never enter the hour horizon. Epistemic hydration receives IDs from
  both sets. Audit, coverage and LORE carry the optional horizon; no
  request-level override is introduced.
- `[orrery.binding] recent_event_horizon_hours = 24.0` is the only configuration
  change. No built-in template switches to hour predicates, and no named hour
  policy, coverage validator, event writer, migration, index or legacy event
  dating is included.
- Evidence adds ISO occurrence clocks, horizon/floor values, count and elapsed
  hours. Catalog and event-consumer audit understand all four kinds. The
  existing dev-view evidence line and event lens understand the ordered hour
  forms; no UI element is added.

## Source Checks Performed

The lane's original checkpoint recorded a Black run and a catalog write without
their commands. What is actually known now: on the integrated head `247dc734`,
`black --check` over the eight product files and seven test files reports "15
files would be left unchanged", and `docs/orrery_packages.md` is byte-identical
across the lane's own range (`git diff --quiet 8d2e4999 c8abc33f --
docs/orrery_packages.md` exits 0; a later change to it on the integration branch
is commit `9641f184`, another lane's Backstage work). Commands and tails are
below.

The lane's checkpoint also said a second agent had checked "the four required
planted-control failures". No command or output backed that sentence, and the
control had not run. It has now run; see "Red Run: `horizon_floor=None`" below.

[Canonical closure](canonical-closure.json) covers the declared sources:
AGENTS, turn flow, and decisions 0009, 0010, 0024, 0034 and 0042. The lane
stamped them at `4ae8b8d2`; the assembly merge `c8abc33f` took main's
`81163beb` for three of them, and assembly commit `894d8c88` re-stamped all
seven to `f073b3711a3bd0273943c9defad85913452fd00b` (origin/main, the merge base
of the integration branch). `canonical-closure.json` now records that stamp.
Against `f073b371` the seven documents differ only in their `verified_commit`
line (command below), so their bodies are unchanged. The added binding key and
separate event horizon do not change the CLI usage ledger, model seats/storage,
correspondence contract or durable-project rules.

## Authored Tests

`test_substrate_world_hours.py` covers the eight ordered cases: independent
tick/hour measurement, occurrence ordering and equality, counting/epistemics,
fail-fast horizon admission, dated-horizon validation, tick isolation, exact
name round trips and setting/coercer validation. The fixer added
`test_dry_run_entry_points_thread_the_horizon`, which proves `resolve_dry_run`,
`explain_dry_run` and `analyze_coverage` each pass `event_horizon_hours` through
to hydration (an explicit 0 must raise `ValueError` naming
`recent_event_horizon_hours`; a dropped keyword falls back to the shipped 24.0
and the call succeeds).

Existing evidence, catalog, audit and coverage tests gain the hour variants and
observed-clock assertions. The fixer added
`knows_recent_event_within_hours("threat_issued", within_hours=2,
target_slot=Slot.ACTOR)` to `FACTORY_SWEEP` (the TARGET entry never matched an
event, so the visible-candidate path was never compared with the closure) and
`test_knows_hour_evidence_matches_closure_under_epistemics`, which compares
evidence with the closure for a bounded claim with and without awareness. The
`test_audit.py` substrate imports are now alphabetized. The existing
`test_evidence.py::RICH_STATE` clock is explicitly UTC; this is the only
pre-existing naive fixture corrected.

`test_world_hour_horizon_pg.py` authors four real proofs on an independently
owned `qa640_778s3_horizon` clone using current migration-144 fixtures. The base
is set before the first chunk; forty committed chunks span 39 minutes. Dated
strolls occur at chunks 2, 5 and 10. An undated Retrograde threat remains visible
in the tick tuple without affecting the stroll cooldown. Proofs assert early
occurrence visibility, the exact half-hour floor, historical replay under later
inserts, and a bounded claim on an event outside the chunk window.

Stale consumer fixed by the fixer: `tests/test_orrery/test_faction_membership_roles_pg.py`
mirrors TurnCycle's dry-run sections and forbids any fallback to
`load_settings()`. TurnCycle now passes `[orrery.binding]
recent_event_horizon_hours`; the mirror lacked it, so both parametrizations of
`test_dry_run_entry_points_forward_resolver_settings` failed (tail below). The
mirror now includes `event_horizon_hours` from the same settings dump; the
product contract is unchanged.

## Integrated-Tree Proof (2026-10-13)

All commands ran from `/Users/pythagor/nexus/.claude/worktrees/fix-778-s3` with
`PY=/Users/pythagor/nexus/.venv/bin/python`, `PYTHONPATH=$PWD`, and
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset. They ran on the
assembled head, not on lane source `fd35896d`. The import check printed
`/Users/pythagor/nexus/.claude/worktrees/fix-778-s3/nexus/__init__.py`.

Load: every PostgreSQL run read `uptime` first and waited in a bounded loop
(`until [ "$(sysctl -n vm.loadavg | awk '{print int($2)}')" -lt 24 ] || [ $n
-ge 40 ]; do sleep 30; ...`) for the one-minute load to fall below 24. The
one-minute load before each run was between 4.89 and 15.42, so no run waited.
No connection timeout occurred.

### Red Run: `horizon_floor=None`

Green first, on `4db727e2`:

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_world_hour_horizon_pg.py
....                                                                     [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 5 targets: postgres, qa640_778s3_horizon_* x4
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
4 passed in 13.48s
```

Plant on `4db727e2`, the hydration call only (line 791 after the docstring
change; the order's line 784):

```
@@ -788,7 +788,7 @@ def hydrate_world_state(
         session,
         anchor_chunk_id=anchor_chunk_id,
         window_chunks=window_chunks,
-        horizon_floor=world_time - timedelta(hours=horizon),
+        horizon_floor=None,
     )
```

Same command, failing tail (each failure is on its horizon assertion; the
epistemics proof fails with `KeyError` on `claimed_event_scopes`):

```
E       assert {1, 2} <= set()
tests/test_orrery/test_world_hour_horizon_pg.py:129: AssertionError
E       assert set() == {3}
tests/test_orrery/test_world_hour_horizon_pg.py:143: AssertionError
E       assert {1, 2} <= set()
tests/test_orrery/test_world_hour_horizon_pg.py:156: AssertionError
E       KeyError: 1
tests/test_orrery/test_world_hour_horizon_pg.py:187: KeyError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_world_hour_horizon_pg.py::test_horizon_sees_what_the_chunk_window_misses
FAILED tests/test_orrery/test_world_hour_horizon_pg.py::test_horizon_floor_follows_world_time
FAILED tests/test_orrery/test_world_hour_horizon_pg.py::test_hydration_is_anchor_bounded_and_replay_identical
FAILED tests/test_orrery/test_world_hour_horizon_pg.py::test_epistemics_scopes_cover_horizon_events
4 failed in 12.58s
```

Restored with `git checkout -- nexus/agents/orrery/resolver.py`; `git diff
--quiet -- nexus/agents/orrery/resolver.py` exited 0; sha256 before and after
`f516881965e9daa05ed8c7eaec6c5f0621cf733a93625da079bdda05a60faa44`. The plant
was never committed.

### Red Run: Dropped Horizon Keyword in Each Dry-Run Entry Point

On `4db727e2`, each plant removed one `event_horizon_hours=event_horizon_hours,`
argument, ran `PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q
tests/test_orrery/test_substrate_world_hours.py -k thread`, and restored the file
with `git checkout`:

```
### plant: dropped event_horizon_hours keyword in nexus/agents/orrery/resolver.py
E       Failed: DID NOT RAISE <class 'ValueError'>
FAILED tests/test_orrery/test_substrate_world_hours.py::test_dry_run_entry_points_thread_the_horizon[resolve]
1 failed, 2 passed, 8 deselected, 5 warnings in 0.35s
restored: git diff --quiet ok; sha256 before=f516881965e9daa05ed8c7eaec6c5f0621cf733a93625da079bdda05a60faa44 after=f516881965e9daa05ed8c7eaec6c5f0621cf733a93625da079bdda05a60faa44
### plant: dropped event_horizon_hours keyword in nexus/agents/orrery/audit.py
E       Failed: DID NOT RAISE <class 'ValueError'>
FAILED tests/test_orrery/test_substrate_world_hours.py::test_dry_run_entry_points_thread_the_horizon[explain]
FAILED tests/test_orrery/test_substrate_world_hours.py::test_dry_run_entry_points_thread_the_horizon[coverage]
2 failed, 1 passed, 8 deselected, 5 warnings in 0.41s
restored: git diff --quiet ok; sha256 before=45c27bdfa7d46e4aa9a7b77b24c228954b9890da07583467a306f7c76a8ef189 after=45c27bdfa7d46e4aa9a7b77b24c228954b9890da07583467a306f7c76a8ef189
### plant: dropped event_horizon_hours keyword in nexus/agents/orrery/coverage.py
FAILED tests/test_orrery/test_substrate_world_hours.py::test_dry_run_entry_points_thread_the_horizon[coverage]
1 failed, 2 passed, 8 deselected, 5 warnings in 0.39s
restored: git diff --quiet ok; sha256 before=267e8dc165e7ee762182670d19f670868eeefcbbe033da72e59b5fd8e9648417 after=267e8dc165e7ee762182670d19f670868eeefcbbe033da72e59b5fd8e9648417
```

### Focused PostgreSQL Proof, Piece One

On `247dc734` (one-minute load 7.80):

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rs tests/test_orrery/test_world_hour_horizon_pg.py tests/test_orrery/test_event_sources_pg.py tests/test_orrery/test_relationship_provenance_pg.py tests/test_orrery/test_claim_propagation_live.py tests/test_orrery/test_epistemics.py tests/test_orrery/test_world_event_time_pg.py tests/test_orrery/test_routine_clock_required_pg.py tests/test_orrery/test_travel_times_pg.py tests/test_orrery/test_evidence.py tests/test_api/test_orrery_dev_endpoints.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 42 targets: postgres, qa640_778s2a_time_* x14, qa640_778s3_horizon_* x4, qa640_783s6_* x11, qa640_785s2_*, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_drift_*, qa885_claim_propagation_*, qa885_epistemics_*, qa885_evidence_*, qa885_orrery_dev_*, test_event_sources_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:58748 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:58749 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:58748 (psycopg2), save_04@local:58749 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
212 passed, 2 skipped, 7 warnings in 150.86s (0:02:30)
```

The same piece also passed on `4db727e2` (212 passed, 2 skipped in 142.72s).
The two skips are the `requires_corpus` owner-corpus probes.

### Focused PostgreSQL Proof, Piece Two (Hydration Consumers)

First run, on `4db727e2` (load 9.55), before the stale mirror was fixed:

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_pair_tag_substrate.py tests/test_orrery/test_faction_membership_roles_pg.py tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_orbit_distance_live.py tests/test_orrery/test_stage2a_status_live.py tests/test_lore/test_recent_orrery_rulings_pg.py
_____ test_dry_run_entry_points_forward_resolver_settings[resolve_dry_run] _____
E       AssertionError: an Orrery entry point fell back to load_settings()
tests/test_orrery/test_faction_membership_roles_pg.py:193: AssertionError
_____ test_dry_run_entry_points_forward_resolver_settings[explain_dry_run] _____
E       AssertionError: an Orrery entry point fell back to load_settings()
tests/test_orrery/test_faction_membership_roles_pg.py:193: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
2 failed, 24 passed, 5 warnings in 17.33s
```

After commit `247dc734` (TurnCycle mirror includes the horizon), same command
with `-rs` (load 4.89):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 9 targets: nexus_test_i685_* x3, postgres, qa640_membership_roles_*, qa640_orbit_distance_*, qa640_pair_tag_substrate_*, qa885_composition_sources_*, qa885_stage2a_status_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
26 passed, 5 warnings in 17.13s
```

### Offline Suites

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests
--ignore=tests/test_api --ignore=tests/test_orrery`, on `247dc734`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
5 failed, 3192 passed, 671 skipped, 8 warnings in 647.07s (0:10:47)
```

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api
tests/test_orrery`, on `247dc734`:

```
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_queues_narration_job
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_skips_low_signal_rows
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_state_signal_without_brief
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_configured_thresholds
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_persists_offscreen_narration
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_requeues_transient_failures
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_marks_terminal_after_max_attempts
FAILED tests/test_orrery/test_worker.py::test_clear_semantic_tags_is_conservative_noop_without_local_inference
11 failed, 1902 passed, 1517 skipped, 7 warnings in 46.91s
```

None of these sixteen failures is in a file or a code path this lane changed:
the Gaia prompt fingerprint and length, the script-wrapper binding list
(`tests/test_orrery/test_place_point_required_pg.py`), the wire schema
description (`NewEntityDeclaration.coordinates`), two wizard tests that open a
psycopg2 connection in an offline test, the epistemics background-branch
validator, and `orrery.projects.milestone_magnitude must be >=
orrery.promote.magnitude_threshold` in `test_worker.py`. The lane's
`settings_models.py` diff is the one `recent_event_horizon_hours` field. They
are reported for the coordinator's triage and not fixed here.

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider
tests/test_reachability.py tests/test_doc_front_matter.py`, on `247dc734`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 18.70s
```

The lane's own offline files (`test_substrate_world_hours.py`, `test_audit.py`,
`test_catalog.py`, `test_coverage_accounting.py`, `test_evidence.py`) passed on
the uncommitted fixer edits before commit `4db727e2`: `167 passed, 1 skipped`.

### Read-Only Fleet Survey

`PGOPTIONS='-c default_transaction_read_only=on' psql -X -d <db>` for each of
`save_01`..`save_05` and `NEXUS_template` (each session printed
`default_transaction_read_only = on`), 2026-10-13 13:58 CDT:

```
SELECT count(*) AS events, count(*) FILTER (WHERE world_time IS NULL) AS null_world_time FROM world_events;
SELECT source::text, count(*), count(*) FILTER (WHERE world_time IS NULL) FROM world_events GROUP BY source ORDER BY source::text;
SELECT max(version) FROM schema_migrations;
```

| Database | Events | NULL `world_time` | By source | Migration stamp |
| --- | --- | --- | --- | --- |
| save_01 | 0 | 0 | none | 148 |
| save_02 | 0 | 0 | none | 148 |
| save_03 | 96 | 21 | resolver 75 (0 NULL), retrograde 21 (21 NULL) | 148 |
| save_04 | 133 | 30 | resolver 103 (0 NULL), retrograde 30 (30 NULL) | 148 |
| save_05 | 0 | 0 | none | 148 |
| NEXUS_template | 0 | 0 | none | 148 |

`SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'world_events'
AND indexdef ILIKE '%world_time%'` on `save_03` returned 0 rows: there is still
no index on `world_time` (out of scope). The counts match the order's
2026-10-07 survey.

### Static Checks

Black, on `247dc734`:

```
nice -n 15 $PY -m black --check nexus/agents/orrery/{audit,catalog,coverage,evidence,resolver,substrate}.py nexus/config/settings_models.py nexus/agents/lore/utils/turn_cycle.py tests/test_orrery/{test_audit,test_catalog,test_coverage_accounting,test_evidence,test_substrate_world_hours,test_world_hour_horizon_pg,test_faction_membership_roles_pg}.py
All done! ✨ 🍰 ✨
15 files would be left unchanged.
```

flake8 on the eight changed product files, head `4db727e2` against base
`8d2e4999` (base copies from `git show 8d2e4999:<path>` in a scratch directory,
run with `--config .flake8`): eleven diagnostics on each side, identical except
for line shifts, all on lines this lane did not touch (`turn_cycle.py:508`
F401; E501 in `audit.py`, `resolver.py` and `settings_models.py`). No new
diagnostic. flake8 on the seven changed test files exits 0.

mypy, `$PY -m mypy --explicit-package-bases --no-incremental` over the same
eight files, run in two `git archive` exports (`nexus scripts pyproject.toml`)
of `8d2e4999` and `4db727e2` so both sides resolve imports the same way:

```
== 8d2e4999: Found 190 errors in 35 files (checked 8 source files)
== 4db727e2: Found 190 errors in 35 files (checked 8 source files)
== diagnostics present at 4db727e2 but not at 8d2e4999 (line numbers stripped):
nexus/jobs/summarize_narrative.py: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
```

The one line is the same note on a file another wave-B lane moved from
`scripts/summarize_narrative.py` to `nexus/jobs/summarize_narrative.py`. It is
a note, not an error, and no diagnostic is new on a line this lane changed.

Exception dispositions, on `247dc734`:

```
nice -n 15 $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

Canonical stamps:

```
git diff f073b371 HEAD -- AGENTS.md docs/turn_flow_sequence.md docs/decisions/0009-dollars-in-the-ledger.md docs/decisions/0010-the-gaia-seat.md docs/decisions/0024-killed-c102.md docs/decisions/0034-conspiracy-channel.md docs/decisions/0042-durable-intentions.md | grep -E '^[-+][^-+]' | sort | uniq -c
   3 -verified_commit: "81163beb0f02041f2e83c50a96dfa60286cbb28a"
   4 -verified_commit: "d70a1991210ce16aef5d6f9b57b0ec563ee1d164"
   7 +verified_commit: "f073b3711a3bd0273943c9defad85913452fd00b"
```

### UI

On `247dc734`: `nice -n 15 npm --prefix ui ci` exited 0.

```
nice -n 15 npm --prefix ui run check
> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync
> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
(exit 0)

nice -n 15 npm --prefix ui test -- dev-orrery/vm.test.ts
 ✓ src/pages/dev-orrery/vm.test.ts (4 tests) 1ms
 Test Files  1 passed (1)
      Tests  4 passed (4)
```

`nice -n 15 npm --prefix ui test -- state-shades.test.ts` fails as expected
with `Stale browser-resolved state surfaces: run npm --prefix ui run
resolve-state-surfaces`: `vm.ts` changed and `vm.test.ts` is new, and both are
hashed inputs. `vm.ts` is not a measured surface, so the measurements should not
change.

### Coordinator's Steps

- The whole-tree PostgreSQL gate.
- `npm --prefix ui run resolve-state-surfaces` on the final UI union, the
  committed receipt and artifacts, and the full `npm --prefix ui test`
  (`state-shades.test.ts` included).
- Fleet migrations: none for this lane.
- Owner services: the next authorized gateway start picks up the product and
  `nexus.toml` change, and the dev-view change needs a UI rebuild.

## Landing Boundary

No owner database was written: the fleet survey ran in read-only sessions, and
every PostgreSQL test database was a fixture-owned disposable (`dbname audit:
owner targets: none`). No fleet operation, migration, provider call, service
start or restart was performed. There is no fleet application for this slice.
No push or PR from the fixer; the coordinator merges the branch. Future PR:
Refs #778.

Codex (GPT-6), source checkpoint; Claude Opus 5.5, integrated-tree proof and fixes.
