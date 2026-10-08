# 778-S3 world-hour predicates — source checkpoint

Status: **source checkpoint; runtime proof pending**. This checkpoint implements
frozen `778-S3.md` on base `4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8`.
No pytest session, PostgreSQL connection, browser, build, npm install, flake8 or
mypy run has been performed for this lane. The coordinator is deliberately
preparing independent source changes while the previous batch owns the serial
heavy-test slot. No passing result from that batch applies to this checkpoint.

## Contract and implementation

The binding [778-Q5 decision](https://github.com/pythagorakase/nexus/issues/778#issuecomment-5922751866)
was re-read on 2026-10-08 and still selects an occurrence-time horizon. The order's
2026-10-07 fleet survey is historical; a fresh read-only fleet count is pending
an available coordinator slot. No current fleet count is claimed here.

- `substrate.py:326` appends optional occurrence time to `EventRecord`.
  `WorldState` retains `charted_place_ids` and `timed_route_pairs` from 785,
  adds a separate validated dated horizon and immutable candidate buckets,
  and leaves the tick tuple and its predicates intact. The four new factories
  follow the tick forms' binding, fields and epistemics behavior, measuring
  occurrence time with an inclusive floor. Every evaluation first refuses a
  missing/naive clock or insufficient configured horizon. Since-last compares
  the latest occurrence with that floor, equivalent to elapsed time being at
  least the requested interval; it never selects by latest tick.
- `resolver.py:520` validates the horizon, with the shipped default read only
  when no explicit value is supplied. `hydrate_world_state` rejects a naive
  clock by anchor name before history loading. `_load_event_history` at line
  2963 performs one ordered, anchor-bounded query and partitions each row's
  single `EventRecord` into tick and/or dated history. Undated Retrograde rows
  remain eligible for tick reads and never enter the hour horizon. Epistemic
  hydration receives IDs from both sets. Audit, coverage and LORE carry the
  optional horizon; no request-level override is introduced.
- `[orrery.binding] recent_event_horizon_hours = 24.0` is the only configuration
  change. No built-in template switches to hour predicates, and no named hour
  policy, coverage validator, event writer, migration, index or legacy event
  dating is included.
- Evidence adds ISO occurrence clocks, horizon/floor values, count and elapsed
  hours. Catalog and event-consumer audit understand all four kinds. The
  existing dev-view evidence line and event lens understand the ordered hour
  forms; no UI element is added.

## Source checks performed

Black ran through the shared interpreter at `nice -n 15`, with one-minute load
16.38 and runtime/PG/live/pytest environment flags cleared: 9 Python files
reformatted, 5 unchanged. The prescribed catalog write ran through the same
interpreter/import path. It printed this worktree's `nexus/__init__.py`, wrote
`docs/orrery_packages.md`, and that file remained byte-identical to the branch
base. No template or catalog output changed.

The coordinator's independent source review caught an authoring replacement
error in the recent-hour evidence loop; it was corrected to `horizon_events`
before this checkpoint. A source-only AST inspection then confirmed that the
eight new predicate/evidence functions refer only to declared `WorldState`
fields; all four predicates use horizon candidates and all four evidence
resolvers read the horizon tuple. This is source inspection, not runtime proof.

[Canonical closure](canonical-closure.json) was recomputed from declared sources:
AGENTS, turn flow, and decisions 0009, 0010, 0024, 0034 and 0042. Their bodies and
quoted rulings remain byte-identical; stamps move to the current merge base.
The added binding key and separate event horizon do not change the CLI usage
ledger, model seats/storage, correspondence contract or durable-project rules.

The coordinator completed independent review of the corrected production diff,
catalog, VM and PostgreSQL tests with no further behavioral blocker. A second
agent independently checked both new Python test files against the frozen order
and migration-144 helpers, including the four required planted-control failures;
no test/import was used in either review. Two new overlong Python string literals
identified during review were split without changing their values.

Normal commit-hook results will be recorded separately after the checkpoint
commit succeeds. All dynamic proof and static comparisons remain pending.

## Authored tests and pending proof

`test_substrate_world_hours.py` covers the eight ordered cases: independent
tick/hour measurement, occurrence ordering and equality, counting/epistemics,
fail-fast horizon admission, dated-horizon validation, tick isolation, exact
name round trips and setting/coercer validation. Existing evidence, catalog,
audit and coverage tests gain the hour variants and observed-clock assertions.
The existing `test_evidence.py::RICH_STATE` clock is now explicitly UTC; this is
the only pre-existing naive fixture corrected at this checkpoint.

`test_world_hour_horizon_pg.py` authors four real proofs on an independently
owned `qa640_778s3_horizon` clone using current migration-144 fixtures. The base
is set before the first chunk; forty committed chunks span 39 minutes. Dated
strolls occur at chunks 2, 5 and 10. An undated Retrograde threat remains visible
in the tick tuple without affecting the stroll cooldown. Proofs assert early
occurrence visibility, the exact half-hour floor, historical replay under later
inserts, and a bounded claim on an event outside the chunk window.

After the coordinator grants the slot:

1. Prove the shared interpreter imports this checkout, clear runtime/PG/live/
   pytest overrides, require load below 24, and run serially at `nice -n 15`.
   The coordinator may deduplicate this lane's focused files with the other
   prepared lanes on an assembled tree. Record the exact assembled head and
   command, secret-store guard, receipt isolation and owner-target audit.
2. Run the ordered focused files: `test_world_hour_horizon_pg.py`,
   `test_event_sources_pg.py`, `test_relationship_provenance_pg.py`,
   `test_claim_propagation_live.py`, `test_epistemics.py`,
   `test_world_event_time_pg.py`, `test_routine_clock_required_pg.py`,
   `test_travel_times_pg.py`, `test_evidence.py`,
   `tests/test_api/test_orrery_dev_endpoints.py`, `test_card_identity.py`,
   and `tests/test_connection_lifecycle.py`. Orrery filenames are under
   `tests/test_orrery/`. Also run the authored pure tests and existing catalog,
   audit and coverage-accounting tests.
3. Run the hydration consumers: `test_pair_tag_substrate.py`,
   `test_faction_membership_roles_pg.py`, `test_composition_sources_live.py`,
   `test_orbit_distance_live.py`, `test_stage2a_status_live.py`,
   and `tests/test_lore/test_recent_orrery_rulings_pg.py`.
4. Plant `horizon_floor=None` only in the hydration call. Require all four new
   PostgreSQL proofs to fail for their intended missing-horizon assertions,
   restore source byte-for-byte, and retain failure tails and restoration
   hashes. This prescribed control has **not** run.
5. Run changed-file flake8/mypy against a matching base comparison, exception
   dispositions, reachability and canonical freshness. Any unrelated fake-row
   window mismatch is reported rather than changing the required partition;
   stale naive anchor fixtures may be made explicitly UTC and listed here.
6. The coordinator owns the complete integration gate; no standalone or full
   offline run is claimed. The earlier nine-lane gate and current four-lane
   gate do not cover this new branch.
7. After landed 777/824 and any other preceding UI source is merged normally,
   run the ordered UI checks and `dev-orrery/vm.test.ts`, regenerate the final
   state-surface receipt from that baseline, require identical measurements,
   and run full Vitest. No state receipt is captured or hand-merged now.

## Landing boundary

No owner database was accessed, and no fleet operation, migration, provider
call, service start or restart was performed. There is no fleet application for
this slice. Product/config changes require the next authorized gateway startup
to use the new code; the changed dev-view source requires a UI rebuild. Owner
services stay stopped unless separately authorized. No push or PR occurs until
the coordinator's gates and publication sequence permit it. Future PR: Refs #778.

Codex — GPT-6
