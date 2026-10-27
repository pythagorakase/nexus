# 824-S4 Verification: The Player-Plane Wizard Guard

Issue #824, Decisions 824-Q4 and D-824-TRANSITION. Branch
`claude/824-player-wizard-guard`, cut from `origin/main` at c7ae2988, brought
forward to d295eef0 before any edit, and merged with `origin/main` at
70a1ff95 and again at 5ba97c05. No migration, no paid call, no gateway lane.
Every PostgreSQL write went to the disposable `qa640_offline_gate_*` clones.

## What Was Wrong (Lines at c7ae2988)

- `nexus/api/setup_endpoints.py:50-92`: `POST /api/story/new/setup/start`
  checks only the lock (`:53`) and calls `start_setup` (`:58`); its
  `except Exception` (`:90-92`) turns every error, an `HTTPException`
  included, into a 500. The slot list reports `"is_active": not state.is_empty`
  (`:235`).
- `nexus/api/new_story_flow.py:131-143`: `start_setup` resolves the model with
  the request's override (`:131-136`), clears the wizard cache (`:138`) and
  persists the resolved model as the slot's Skald pin (`:143`).
- `nexus/api/wizard_chat.py:822-949`: `POST /api/story/new/transition` checks
  the lock (`:836`) and the wizard cache inside `prepare` (`:839-911`) before
  `run_genesis_transition` (`:917-921`); `except HTTPException: raise`
  (`:940-941`) passes a `prepare` refusal through.
- `nexus/api/route_capabilities.py:127-129`, `:180`, `:195-196`: both routes
  were `_WIZARD_OVERWRITE`, a player-plane destructive capability.
- `nexus/api/slot_state.py:199-216`: empty means neither a wizard cache nor
  narrative data; narrative data is chunks, an incubator row or a committed
  story marker. `:132-134` reads the model from `global_variables.model`.
- `ui/client/src/components/NewStoryWizard/InteractiveWizard.tsx:383-390`
  posted `setup/start` with `{slot}` and `:630` posted `transition` on both
  planes. `nexus/cli.py:2620-2632` posted `setup/start` with `--model` when
  given.

## Read-Only Facts About the Owner's Databases

```
$ PGOPTIONS='-c default_transaction_read_only=on' psql -d save_05 -Atc "SELECT (SELECT count(*) FROM narrative_chunks) AS chunks, (SELECT count(*) FROM incubator) AS incubator, (SELECT count(*) FROM assets.new_story_creator) AS wizard_rows, setting IS NULL AS setting_null, base_timestamp IS NULL AS base_ts_null, model FROM global_variables WHERE id = TRUE"
0|0|0|t|t|gpt-6-astra
$ PGOPTIONS='-c default_transaction_read_only=on' psql -d NEXUS_template -Atc "SELECT count(*) FROM global_variables"
0
```

`save_05` is an empty slot that carries a pin (`gpt-6-astra`), so the player
route admits a start on it with no model or with `gpt-6-astra`, and refuses
any other `model` with 409. `NEXUS_template` has no `global_variables` row,
so a fresh slot cloned from it has no pin.

## shadcn/ui

`https://ui.shadcn.com/docs/components` lists 66 components (Accordion
through Typography). None chooses an API route or endpoint; the change adds no
UI element and nothing visible changes, so no component applies.

## Red Runs (Tests First, Product Code Unchanged, at 1df29789)

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api/test_route_capabilities.py "tests/test_cli_contract.py::test_continue_model_override_takes_the_operator_start_only_on_this_machine"
FAILED tests/test_api/test_route_capabilities.py::test_destructive_routes_are_pinned
FAILED tests/test_api/test_route_capabilities.py::test_wizard_routes_split_by_plane
FAILED tests/test_cli_contract.py::test_continue_model_override_takes_the_operator_start_only_on_this_machine[local]
3 failed, 37 passed, 1 skipped, 7 warnings in 6.05s
```

The remote and local-without-model CLI cases pass on main, as they should
(main already posts `setup/start` there).

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_wizard_plane_guard_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 10 targets: postgres, qa640_offline_gate_* x9
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_api/test_wizard_plane_guard_pg.py::test_player_start_refuses_an_occupied_slot
FAILED tests/test_api/test_wizard_plane_guard_pg.py::test_player_start_refuses_a_wizard_in_progress
FAILED tests/test_api/test_wizard_plane_guard_pg.py::test_player_start_refuses_a_repin
FAILED tests/test_api/test_wizard_plane_guard_pg.py::test_operator_overwrite_restarts_and_repins
FAILED tests/test_api/test_wizard_plane_guard_pg.py::test_player_transition_refuses_a_story_slot
FAILED tests/test_api/test_wizard_plane_guard_pg.py::test_operator_transition_passes_the_guard
6 failed, 3 passed, 7 warnings in 22.23s
```

The six failures were for the expected reasons: the three player starts
answered 200 and wrote a new cache (the repin answered `"model":"TEST-B"`);
`setup/overwrite` and `transition/overwrite` answered 405 (no such route); the
story-slot transition answered 400 "No setup data found for slot 4". The
three passes are `test_player_start_admits_an_empty_slot[omitted-model]`,
`[pinned-model]` and `test_player_transition_admits_a_fresh_wizard`.

```
$ nice -n 15 npm --prefix ui test -- InteractiveWizard
   × wizard start route by plane > starts on plane operator through /api/story/new/setup/overwrite 12ms
   × genesis stage waiter > posts the operator transition when the operator plane serves the client 82ms
 Test Files  2 failed (2)
      Tests  2 failed | 59 passed (61)
```

## A Consumer the Order Did Not Name

The first green PostgreSQL proof run failed 11 tests in three named proof
files: `tests/test_api/test_wizard_weird_level.py` (8),
`tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance`
(2) and `tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp`
(1). Each calls `transition_to_narrative_endpoint` with the handler's storage
boundary replaced (`read_cache` and `run_genesis_transition`; "no database is
opened") and opens no slot database. The new story-slot refusal reads
`get_slot_state`, which reached `save_04` (refused by the dbname audit:
`OwnerDatabaseConnectionRefused ... owner database 'save_04'`) or the
nonexistent `qa640_fake_wizard_slot`. Each test now also replaces
`wizard_chat.get_slot_state` with a wizard-mode `SlotState`, so the refusal
runs and passes as it does for a slot that holds a wizard (commit c002bbbc).
The other direct callers (`tests/test_api/test_genesis_ledger_pg.py`,
`tests/genesis_owner_child.py`) run on the routed clone and pass unchanged.

## Green Runs (Merged Tree, HEAD cf9762c1 Before the Final Receipt)

PostgreSQL proof set (load 1.98 at start; no wait needed):

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_api/test_wizard_plane_guard_pg.py tests/test_api/test_slot_mutation_guard.py tests/test_api/test_wizard_model_resolution.py tests/test_api/test_route_capabilities.py tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_wizard_weird_level.py tests/test_api/test_wizard_confirmation.py tests/test_wizard_agent.py tests/test_cli_contract.py tests/test_cli_model_selection.py tests/test_cli_generation_http.py tests/test_owner_target_guard.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 60 targets: postgres, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_offline_gate_* x53, test_slot_guard_4a339bea65254f558c75220890a0d368
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:52226 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:52227 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:52226 (psycopg2), save_04@local:52227 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
647 passed, 2 skipped, 7 warnings in 523.08s (0:08:43)
$ psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_offline_gate%'"
(no rows)
```

Offline suites:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3305 passed, 709 skipped, 8 warnings in 686.73s (0:11:26)
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1941 passed, 1579 skipped, 7 warnings in 53.39s
```

`tests/test_reachability.py` and `tests/test_doc_front_matter.py` are inside
the first piece. The first piece failed once, before the merge, on
`test_declared_sources_carry_a_fresh_verified_commit`: decisions 0061 and 0079
(declaring `docs/runtime.md`), 0069 (`nexus/api/wizard_chat.py`) and 0063 and
0073 (`nexus/cli.py`) were added on main after the order was written. Each
records an issue ruling that the route split leaves true (0079 quotes
D-824-TRANSITION, which this branch implements) and was re-stamped; 0067
(declaring the state-surface receipt) was re-stamped at the second merge.
AGENTS.md, `docs/turn_flow_sequence.md` and decision 0009 describe neither
the wizard routes nor `continue --model` and were re-stamped as item 7 asks.

## Static Checks (Against `origin/main` Versions, via `git archive`)

```
black --check (12 files): 12 files would be left unchanged.
flake8: branch 38, main 38. The only lines that differ are the two
  pre-existing F811 diagnostics in tests/test_wizard_agent.py, whose message
  now says "from line 41" instead of "from line 40" (one import was added).
mypy --explicit-package-bases: branch "Found 33 errors in 5 files (checked
  12 source files)"; every branch diagnostic is also reported on main's
  versions (main run: "Found 267 errors in 58 files"); new on branch: none.
$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

No swallowing handler was added; the baseline does not change.

## UI

```
$ nice -n 15 npm --prefix ui test -- InteractiveWizard SlotSelector WizardShell
 Test Files  5 passed (5)
      Tests  107 passed (107)
$ nice -n 15 npm --prefix ui run check     (exit 0)
$ nice -n 15 npm --prefix ui run build     (exit 0)
```

## State Surfaces

`InteractiveWizard.tsx` and both wizard test files are in the state-surface
input closure. Main's receipt is already stale: it is the receipt of
a01c162f, and 1102-S1 (`LocalModelRows.tsx`, `tooltip-focus-trace.mjs`) and
later 821-S2 (`SettingsPane.tsx`, `nexus-layout.css`, `vite.config.ts`, the
Radix popover) landed without regenerating it (Decision 0067, 821-D3: the
coordinator regenerates once on the wave's UI union). At d295eef0, before any
edit of this order, `npm --prefix ui test -- state-shades` already failed with
"Stale browser-resolved state surfaces".

First regeneration, on this branch before the second merge (tree with
d295eef0's UI plus this order's three files): nine bounded `nice -n 15`
capture batches of `npm --prefix ui run resolve-state-surfaces` with
`STATE_SURFACES_CONDITION` over the 33 media conditions, then
`--assemble`:

```
Resolved painted state surfaces: renders=126078; wall=3500.300s (sum of bounded capture shards); Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 33 media conditions; file://; network aborted; requests=0; errors=0
Wrote ui/client/src/state-surfaces.resolved.json; module graph=2099 inputs; SHA-256 72208704ee04a968655e30faa980b6126e4e7a6d4b685b1a8fac253749b17018
$ nice -n 15 npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
 Test Files  4 passed (4)
      Tests  123 passed (123)
$ nice -n 15 npm --prefix ui test
 Test Files  44 passed (44)
      Tests  687 passed (687)
```

Against main's receipt, ignoring settle timings: the media inventory is
equal, every painted color (`meanLinear`, `controlMeanLinear`, `rgb`,
`coreSize`) is equal, and the recorded tables still match. The only
differences are on the exceeds-RAM delete row, whose inputs 1102-S1 changed:
its focus-visible captures record an Escape dismissal (`escapePressed`,
`action`: 1,978 samples each) and its rest box sits lower (`y`: 204 samples).
No sample of this order's surfaces moved. That receipt is committed
(22ec5882).

Second regeneration, after merging 5ba97c05 (same nine batches, module graph
2108 inputs, SHA-256 eb1ab6e7...): 821-S2's inputs move painted measurements
on the delete rows (`rgb` 446, `meanLinear` 68, `coreSize` 68, `signature`
6,744 samples; contexts `delete/ready-exceeds/focus-visible`,
`delete/ready/rest`, `delete/ready-exceeds/rest`,
`delete/ready-exceeds/button-hover`) and change the media inventory, so
`browser_measurements_match_recorded_tables` fails until the recorded tables
under `docs/qa/777-glyph-first-states/amendment-2/` are refreshed. Certifying
those moves is the union regeneration that 821-D3 assigns to the coordinator,
so the branch keeps the first receipt. On the merged tree:

```
$ nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 43 passed (44)
      Tests  677 passed (677)
```

This is the same staleness `origin/main` shows (its receipt is a01c162f's,
with 1102-S1's and 821-S2's inputs changed since).
