# 824-S4 Verification: The Player-Plane Wizard Guard

Issue #824, Decisions 824-Q4 and D-824-TRANSITION. Branch
`claude/824-player-wizard-guard`, cut from `origin/main` at c7ae2988, brought
forward to d295eef0 before any edit, and merged with `origin/main` at
70a1ff95 and again at 5ba97c05. No migration and no paid call. The build
used no gateway lane; the review fixes ran the #838 entry-point proof on the
disposable lane 8012 (see "A Second Consumer the Order Did Not Name"). Every
PostgreSQL write went to disposable `qa640_*` clones.

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

### Re-Located on `origin/main` 5ba97c05

Every citation above and in the order was re-checked on 5ba97c05, the
merge base of this branch. These moved:

| Citation at c7ae2988 | On 5ba97c05 |
|---|---|
| `wizard_chat.py:822-949` (transition handler) | `:823-956` |
| `wizard_chat.py:822-823` (decorator, `def`) | `:823-824` |
| `wizard_chat.py:836` (lock) | `:837` |
| `wizard_chat.py:839-911` (`prepare`) | `:840-918` |
| `wizard_chat.py:917-921` (`run_genesis_transition`) | `:924-928` |
| `wizard_chat.py:940-941` (`except HTTPException: raise`) | `:947-948` |
| `route_capabilities.py:127-129` (`_WIZARD_OVERWRITE`) | `:130-132` |
| `route_capabilities.py:175-180` (setup comment, `setup/start`) | `:178-183` |
| `route_capabilities.py:195-196` (transition comment and entry) | `:198-199` |
| `cli.py:2620-2632` (`setup/start` block) | `:2631-2643` |
| `cli.py:2627-2629` (`--model` forward) | `:2638-2640` |
| `cli.py:2739`, `:2936`, `:3017` (transition posts) | `:2750`, `:2947`, `:3028` (`:2753`, `:2950`, `:3031` on this branch) |
| `cli.py:6306-6324` (`_active_remote_runtime`) | `:6400-6418` |
| `docs/runtime.md:155` (Operator row) | `:158` |
| `docs/runtime.md:157-163` (planes paragraph) | `:160-166` |
| `tests/test_api/test_route_capabilities.py:523-544` | `:525-546` |

These did not move: `setup_endpoints.py:50-92`, `:53`, `:58`, `:90-92` and
`:235`; `new_story_flow.py:131-143`; `slot_state.py:106-255`, `:132-134` and
`:199-216`; `route_capabilities.py:12-15`; `wizard_chat.py:508-516` (the
chat route's `model` repin, Known Limit (c), cited as `:507-515` before);
`InteractiveWizard.tsx:383-390` and `:630`; `SlotSelector.tsx:67` and
`:126-133`; `usePlane.ts`.

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

The first green PostgreSQL proof run failed tests in three named proof files.
Each failing test calls `transition_to_narrative_endpoint` with the handler's
storage boundary replaced (`read_cache` and `run_genesis_transition`; "no
database is opened") and opens no slot database. The new story-slot refusal
reads `get_slot_state`, which reached `save_04` (refused by the dbname audit)
or the nonexistent `qa640_fake_wizard_slot`. Each test now also replaces
`wizard_chat.get_slot_state` with a wizard-mode `SlotState`, so the refusal
runs and passes as it does for a slot that holds a wizard (commit c002bbbc).
The other direct callers (`tests/test_api/test_genesis_ledger_pg.py`,
`tests/genesis_owner_child.py`) run on the routed clone and pass unchanged.

The first run's log was not kept. Re-run on c002bbbc's parent (52041b8b, a
`git archive` in the session scratchpad, `ui/` excluded; its log is
`824-S4/c002bbbc-parent-run.log` there, and the `dbname audit: FAILED` line
below is pasted from it verbatim): 14 tests fail, 11 in
`test_wizard_weird_level.py`, 2 in `test_wizard_confirmation.py` and 1 in
`test_wizard_agent.py`. The earlier text said 11 (8 + 2 + 1); it left out
the three unparametrized `test_wizard_weird_level.py` tests.

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_wizard_weird_level.py tests/test_api/test_wizard_confirmation.py tests/test_wizard_agent.py
E               tests.dbname_audit.OwnerDatabaseConnectionRefused: dbname audit: refused a psycopg2 connection to owner database 'save_04' from tests/test_api/test_wizard_weird_level.py::test_transition_persists_a_supplied_level_before_it_runs on the owner's server (local:5432); tests connect only to disposable databases, or to an owner name on a registered disposable cluster
E        +  where 500 = HTTPException(status_code=500, detail='Transition failed: connection to server on socket "/tmp/.s.PGSQL.5432" failed: FATAL:  database "qa640_fake_wizard_slot" does not exist\n').status_code
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 20 targets: postgres, qa640_fake_wizard_slot, qa640_offline_gate_* x17, save_04
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: FAILED: owner targets: save_04 (psycopg2) from tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed], tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed], tests/test_api/test_wizard_weird_level.py::test_transition_forwards_the_stored_selection[None], tests/test_api/test_wizard_weird_level.py::test_transition_forwards_the_stored_selection[high], tests/test_api/test_wizard_weird_level.py::test_transition_forwards_the_stored_selection[low], tests/test_api/test_wizard_weird_level.py::test_transition_forwards_the_stored_selection[medium], tests/test_api/test_wizard_weird_level.py::test_transition_guards_refuse_before_recording_a_level[changes0-409-Confirm the setting and character], tests/test_api/test_wizard_weird_level.py::test_transition_guards_refuse_before_recording_a_level[changes1-409-Confirm the setting and character], tests/test_api/test_wizard_weird_level.py::test_transition_guards_refuse_before_recording_a_level[changes2-409-Finish the character revision], tests/test_api/test_wizard_weird_level.py::test_transition_guards_refuse_before_recording_a_level[changes3-422-Missing: base_timestamp], tests/test_api/test_wizard_weird_level.py::test_transition_persists_a_supplied_level_before_it_runs, tests/test_api/test_wizard_weird_level.py::test_transition_refuses_an_incomplete_seed_before_recording_a_level, tests/test_api/test_wizard_weird_level.py::test_transition_reports_a_concurrent_wizard_change_without_running
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_persists_a_supplied_level_before_it_runs
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_forwards_the_stored_selection[low]
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_forwards_the_stored_selection[medium]
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_forwards_the_stored_selection[high]
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_forwards_the_stored_selection[None]
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_guards_refuse_before_recording_a_level[changes0-409-Confirm the setting and character]
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_guards_refuse_before_recording_a_level[changes1-409-Confirm the setting and character]
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_guards_refuse_before_recording_a_level[changes2-409-Finish the character revision]
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_guards_refuse_before_recording_a_level[changes3-422-Missing: base_timestamp]
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_refuses_an_incomplete_seed_before_recording_a_level
FAILED tests/test_api/test_wizard_weird_level.py::test_transition_reports_a_concurrent_wizard_change_without_running
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
14 failed, 89 passed, 5 warnings in 40.75s
```

The same three files with `tests/test_doc_front_matter.py`, on 5f67524c:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_wizard_weird_level.py tests/test_api/test_wizard_confirmation.py tests/test_wizard_agent.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 18 targets: postgres, qa640_offline_gate_* x17
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
192 passed, 5 warnings in 45.97s
```

## A Second Consumer the Order Did Not Name

`tests/proofs/proof_weird_entry_points.py` (the #838 entry-point proof)
serves the unprojected `narrative.app`, which reports the operator plane
(`nexus/api/narrative.py:1770`), so the built client now posts
`POST /api/story/new/transition/overwrite`. Its `StrangenessRequestRecorder`
recorded only `/api/story/new/transition`, so the browser half saw no
transition. Commit 6eeec8ee adds the overwrite route to `RECORDED_ROUTES` and
names both transition routes in the module and recorder docstrings. The CLI
half still posts the player route. Commit 75cd1625 gives
`assert_one_transition` an expected `path` and asserts
`transition["path"] == path`: the CLI half passes
`/api/story/new/transition` and the browser half
`/api/story/new/transition/overwrite`, so the proof fails if either half posts
the other route.

The proof does not run on main as committed: `tests/conftest.py:82-83` routes
every process to the never-created `qa640_816_test_provider_unrouted` (#816),
and the proof does not request `routed_test_provider_database`, so its
private mock answers 500 at the first wizard chat (`database
"qa640_816_test_provider_unrouted" does not exist`, in both halves, before
any transition). That is outside this order and left unfixed. The runs below
add a scratch plugin, `route_838_test_provider.py` in the session scratchpad's
`824-S4/plugins/`, whose only content is an autouse fixture that requests
`routed_test_provider_database`. Lane 8012 was free (`lsof` empty) and load
was under 6. The client was rebuilt first (`nice -n 15 npm --prefix ui run
build`, exit 0).

With the recorder as it was (6710a3ab's proof file in the 5f67524c tree):

```
$ env -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 NEXUS_GATEWAY_PORT=8012 PYTHONPATH=$PWD:<scratch>/824-S4/plugins nice -n 15 $PY -m pytest -q -s -p tests.dbname_audit -p route_838_test_provider tests/proofs/proof_weird_entry_points.py
E       AssertionError: [{'method': 'PUT', 'path': '/api/story/new/weird', 'request': {'slot': 4, 'weird_level': 'low'}, 'response': {'slot': ...request': {'slot': 4, 'weird_level': 'low'}, 'response': {'slot': 4, 'status': 'recorded', 'weird_level': 'low'}, ...}]
E       assert 0 == 1
E        +  where 0 = len([])
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa640_816_test_provider_* x2, qa640_838_browser_*, qa640_838_cli_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/proofs/proof_weird_entry_points.py::test_browser_glyphs_hold_confirm_and_ride_the_transition
1 failed, 1 passed, 2 warnings in 154.69s (0:02:34)
```

With 6eeec8ee's recorder (on 5f67524c):

```
$ env -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 NEXUS_GATEWAY_PORT=8012 PYTHONPATH=$PWD:<scratch>/824-S4/plugins nice -n 15 $PY -m pytest -q -s -p tests.dbname_audit -p route_838_test_provider tests/proofs/proof_weird_entry_points.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa640_816_test_provider_* x2, qa640_838_browser_*, qa640_838_cli_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
2 passed, 2 warnings in 36.31s
```

That run's assertions did not check the path; its recorded requests went to
the test's temporary directory and are not kept. With 75cd1625's path check
(on 75cd1625; client rebuilt first with `nice -n 15 npm --prefix ui run
build`, exit 0; lane 8012 free by `lsof` before and after):

```
$ env -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 NEXUS_GATEWAY_PORT=8012 PYTHONPATH=$PWD:<scratch>/824-S4/plugins nice -n 15 $PY -m pytest -q -s -p tests.dbname_audit -p route_838_test_provider tests/proofs/proof_weird_entry_points.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 5 targets: postgres, qa640_816_test_provider_* x2, qa640_838_browser_*, qa640_838_cli_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
2 passed, 2 warnings in 34.95s
```

Both halves pass with the path asserted: the CLI half's one transition is
`POST /api/story/new/transition` and the browser half's is `POST
/api/story/new/transition/overwrite`, each after its last save. The tracked
`docs/qa/838-entry-points` is unchanged.

## Green Runs

### PostgreSQL Proof Set (on 75cd1625)

Re-run on 75cd1625, the branch's last code commit (later commits change only
this file), so the evidence shows the environment. The `env | grep` runs in
the same `env -u` environment as pytest and prints nothing: no `NEXUS_`
variable is set. Load 6.75 at start; no wait needed. This replaces the
earlier run on cf9762c1, whose command line did not show the unset variables
(`647 passed, 2 skipped` there too).

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT sh -c 'env | grep "^NEXUS_"; echo "env-check-done"'
env-check-done
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_api/test_wizard_plane_guard_pg.py tests/test_api/test_slot_mutation_guard.py tests/test_api/test_wizard_model_resolution.py tests/test_api/test_route_capabilities.py tests/test_api/test_genesis_ledger_pg.py tests/test_api/test_wizard_weird_level.py tests/test_api/test_wizard_confirmation.py tests/test_wizard_agent.py tests/test_cli_contract.py tests/test_cli_model_selection.py tests/test_cli_generation_http.py tests/test_owner_target_guard.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 60 targets: postgres, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_offline_gate_* x53, test_slot_guard_c6b717ca68514205a1dcffc873d5dc78
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:49974 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:49975 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:49974 (psycopg2), save_04@local:49975 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
647 passed, 2 skipped, 7 warnings in 487.10s (0:08:07)
$ psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_offline_gate%'"; echo "psql exit $?"
psql exit 0
```

The `psql` check printed nothing (no `qa640_offline_gate%` database is left)
and exited 0.

### Offline Suites (Merged Tree, HEAD cf9762c1)

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
D-824-TRANSITION, which this branch implements) and was re-stamped. 0067
(declaring the state-surface receipt) is back at main's `verified_commit`,
since the branch no longer changes its sources (5f67524c).
AGENTS.md, `docs/turn_flow_sequence.md` and decision 0009 describe neither
the wizard routes nor `continue --model` and were re-stamped as item 7 asks.

## Static Checks (Against `origin/main` Versions)

```
black --check (12 files): 12 files would be left unchanged.
flake8: branch 38, main 38. The only lines that differ are the two
  pre-existing F811 diagnostics in tests/test_wizard_agent.py, whose message
  now says "from line 41" instead of "from line 40" (one import was added).
$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

mypy, re-run on 75cd1625 with the 13 changed Python files (12 pre-existing,
`tests/proofs/proof_weird_entry_points.py` included, plus the new
`tests/test_api/test_wizard_plane_guard_pg.py`). Both runs are from the
worktree root: main's versions were checked out in place with `git checkout
origin/main -- <the 12 pre-existing files>` and restored with `git checkout
HEAD -- <same>` (status clean afterwards). An earlier note gave main as
"Found 267 errors in 58 files"; that came from a `git archive` tree outside
the checkout, where mypy also reports every imported module, and is withdrawn.

```
$ nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratch>/mypy-cache-wt-main <the 12 pre-existing files, main's versions>
Found 33 errors in 5 files (checked 12 source files)
$ nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratch>/mypy-cache-branch <the 13 changed files>
Found 33 errors in 5 files (checked 13 source files)
$ diff <(strip main) <(strip branch)     # strip = drop "Found", drop file:line[:col], sort
(empty; exit 0)
```

black --check on the 13 files (on 75cd1625): "13 files would be left
unchanged". flake8 on `tests/proofs/proof_weird_entry_points.py`: no output on
the branch or on main's version. Every diagnostic is listed under
"Pre-existing Diagnostics".

No swallowing handler was added; the baseline does not change.

## Pre-existing Diagnostics

All on 75cd1625. The branch's 33 mypy and 38 flake8 diagnostics are main's,
moved by lines the branch added above them. None falls on a line the branch
adds or changes: `changed_lines.py` (session scratchpad, `824-S4/`) reads the
`+` ranges of `git diff -U0 origin/main HEAD -- '*.py'` and tests each
diagnostic's `file:line` against them.

```
$ $PY <scratch>/824-S4/changed_lines.py $PWD origin/main <flake8 branch output>
38 diagnostics checked; 0 on lines added or changed since origin/main
$ $PY <scratch>/824-S4/changed_lines.py $PWD origin/main <mypy branch error lines>
33 diagnostics checked; 0 on lines added or changed since origin/main
```

mypy notes (`note:` lines) are omitted below; only the `error:` lines and the
summary are pasted. With line numbers stripped, the main and branch mypy lists
are identical; the flake8 lists differ only in the two F811 messages ("from
line 40" on main, "from line 41" on the branch, one import added above).

### flake8, Branch (13 Files)

```
$ $PY -m flake8 <the 13 changed files>
nexus/api/wizard_chat.py:23:1: F401 'nexus.api.config_utils.get_new_story_model' imported but unused
nexus/api/wizard_chat.py:90:89: E501 line too long (136 > 88 characters)
nexus/api/wizard_chat.py:308:89: E501 line too long (108 > 88 characters)
nexus/api/wizard_chat.py:328:89: E501 line too long (101 > 88 characters)
nexus/api/wizard_chat.py:333:89: E501 line too long (92 > 88 characters)
nexus/api/wizard_chat.py:348:89: E501 line too long (93 > 88 characters)
nexus/api/wizard_chat.py:412:89: E501 line too long (100 > 88 characters)
nexus/api/wizard_chat.py:416:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:448:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:495:89: E501 line too long (90 > 88 characters)
nexus/cli.py:985:89: E501 line too long (92 > 88 characters)
nexus/cli.py:4395:89: E501 line too long (96 > 88 characters)
nexus/cli.py:4404:89: E501 line too long (96 > 88 characters)
nexus/cli.py:4413:89: E501 line too long (96 > 88 characters)
nexus/cli.py:4557:89: E501 line too long (93 > 88 characters)
nexus/cli.py:5094:89: E501 line too long (113 > 88 characters)
nexus/cli.py:5123:89: E501 line too long (118 > 88 characters)
nexus/cli.py:5163:89: E501 line too long (90 > 88 characters)
nexus/cli.py:5248:89: E501 line too long (151 > 88 characters)
nexus/cli.py:5274:89: E501 line too long (94 > 88 characters)
nexus/cli.py:5275:89: E501 line too long (103 > 88 characters)
nexus/cli.py:5294:89: E501 line too long (101 > 88 characters)
tests/test_api/test_slot_mutation_guard.py:108:89: E501 line too long (96 > 88 characters)
tests/test_api/test_wizard_model_resolution.py:12:1: F401 'types.SimpleNamespace' imported but unused
tests/test_wizard_agent.py:22:1: F401 'nexus.api.new_story_schemas.LayerDefinition' imported but unused
tests/test_wizard_agent.py:22:1: F401 'nexus.api.new_story_schemas.LayerType' imported but unused
tests/test_wizard_agent.py:22:1: F401 'nexus.api.new_story_schemas.PlaceProfile' imported but unused
tests/test_wizard_agent.py:22:1: F401 'nexus.api.new_story_schemas.ZoneDefinition' imported but unused
tests/test_wizard_agent.py:585:1: F811 redefinition of unused 'PromptId' from line 41
tests/test_wizard_agent.py:585:1: F811 redefinition of unused 'load' from line 41
tests/test_wizard_agent.py:585:1: E402 module level import not at top of file
tests/test_wizard_agent.py:586:1: E402 module level import not at top of file
tests/test_wizard_agent.py:599:1: E402 module level import not at top of file
tests/test_wizard_agent.py:600:1: E402 module level import not at top of file
tests/test_wizard_agent.py:601:1: F401 'pydantic_ai.tools.DeferredToolRequests' imported but unused
tests/test_wizard_agent.py:601:1: E402 module level import not at top of file
tests/test_wizard_agent.py:733:89: E501 line too long (110 > 88 characters)
tests/test_wizard_agent.py:734:89: E501 line too long (96 > 88 characters)
```

### flake8, Main (the 12 Pre-existing Files, `git show origin/main:<path>` With Main's `.flake8`)

```
$ $PY -m flake8 <main's 12 pre-existing files>
nexus/api/wizard_chat.py:23:1: F401 'nexus.api.config_utils.get_new_story_model' imported but unused
nexus/api/wizard_chat.py:89:89: E501 line too long (136 > 88 characters)
nexus/api/wizard_chat.py:307:89: E501 line too long (108 > 88 characters)
nexus/api/wizard_chat.py:327:89: E501 line too long (101 > 88 characters)
nexus/api/wizard_chat.py:332:89: E501 line too long (92 > 88 characters)
nexus/api/wizard_chat.py:347:89: E501 line too long (93 > 88 characters)
nexus/api/wizard_chat.py:411:89: E501 line too long (100 > 88 characters)
nexus/api/wizard_chat.py:415:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:447:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:494:89: E501 line too long (90 > 88 characters)
nexus/cli.py:985:89: E501 line too long (92 > 88 characters)
nexus/cli.py:4392:89: E501 line too long (96 > 88 characters)
nexus/cli.py:4401:89: E501 line too long (96 > 88 characters)
nexus/cli.py:4410:89: E501 line too long (96 > 88 characters)
nexus/cli.py:4554:89: E501 line too long (93 > 88 characters)
nexus/cli.py:5091:89: E501 line too long (113 > 88 characters)
nexus/cli.py:5120:89: E501 line too long (118 > 88 characters)
nexus/cli.py:5160:89: E501 line too long (90 > 88 characters)
nexus/cli.py:5245:89: E501 line too long (151 > 88 characters)
nexus/cli.py:5271:89: E501 line too long (94 > 88 characters)
nexus/cli.py:5272:89: E501 line too long (103 > 88 characters)
nexus/cli.py:5291:89: E501 line too long (101 > 88 characters)
tests/test_api/test_slot_mutation_guard.py:106:89: E501 line too long (96 > 88 characters)
tests/test_api/test_wizard_model_resolution.py:12:1: F401 'types.SimpleNamespace' imported but unused
tests/test_wizard_agent.py:21:1: F401 'nexus.api.new_story_schemas.LayerDefinition' imported but unused
tests/test_wizard_agent.py:21:1: F401 'nexus.api.new_story_schemas.LayerType' imported but unused
tests/test_wizard_agent.py:21:1: F401 'nexus.api.new_story_schemas.PlaceProfile' imported but unused
tests/test_wizard_agent.py:21:1: F401 'nexus.api.new_story_schemas.ZoneDefinition' imported but unused
tests/test_wizard_agent.py:570:1: F811 redefinition of unused 'PromptId' from line 40
tests/test_wizard_agent.py:570:1: F811 redefinition of unused 'load' from line 40
tests/test_wizard_agent.py:570:1: E402 module level import not at top of file
tests/test_wizard_agent.py:571:1: E402 module level import not at top of file
tests/test_wizard_agent.py:584:1: E402 module level import not at top of file
tests/test_wizard_agent.py:585:1: E402 module level import not at top of file
tests/test_wizard_agent.py:586:1: F401 'pydantic_ai.tools.DeferredToolRequests' imported but unused
tests/test_wizard_agent.py:586:1: E402 module level import not at top of file
tests/test_wizard_agent.py:718:89: E501 line too long (110 > 88 characters)
tests/test_wizard_agent.py:719:89: E501 line too long (96 > 88 characters)
```

### mypy, Branch (13 Files)

```
$ nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratch>/mypy-cache-branch <the 13 changed files>
nexus/api/setup_endpoints.py:13: error: Skipping analyzing "frontmatter": module is installed, but missing library stubs or py.typed marker  [import-untyped]
nexus/api/setup_endpoints.py:165: error: Argument "current_phase" to "ResumeSetupResponse" has incompatible type "str"; expected "Literal['setting', 'character', 'seed', 'ready']"  [arg-type]
nexus/api/setup_endpoints.py:166: error: Argument "pending_confirmation" to "ResumeSetupResponse" has incompatible type "str | None"; expected "Literal['setting', 'character'] | None"  [arg-type]
nexus/api/setup_endpoints.py:177: error: Argument "messages" to "ResumeSetupResponse" has incompatible type "list[dict[str, str]]"; expected "list[WizardHistoryMessage]"  [arg-type]
nexus/api/wizard_chat.py:17: error: Skipping analyzing "frontmatter": module is installed, but missing library stubs or py.typed marker  [import-untyped]
nexus/api/wizard_chat.py:242: error: No overload variant of "run" of "AbstractAgent" matches argument types "str", "WizardContext", "list[Any]", "Any", "ModelSettings"  [call-overload]
nexus/api/wizard_chat.py:282: error: Item "None" of "WizardCache | None" has no attribute "confirmation_metadata"  [union-attr]
nexus/api/wizard_chat.py:339: error: Incompatible types in assignment (expression has type "str", variable has type "Literal['setting', 'character', 'seed'] | None")  [assignment]
nexus/api/wizard_chat.py:622: error: No overload variant of "run" of "AbstractAgent" matches argument types "str | None", "WizardContext", "list[ModelRequest | ModelResponse]", "Model", "ModelSettings"  [call-overload]
nexus/api/wizard_chat.py:653: error: Argument after ** must be a mapping, not "dict[str, Any] | None"  [arg-type]
nexus/api/wizard_chat.py:753: error: "str" has no attribute "choices"  [attr-defined]
nexus/api/wizard_chat.py:756: error: "str" has no attribute "message"  [attr-defined]
nexus/api/wizard_chat.py:763: error: "str" has no attribute "message"  [attr-defined]
nexus/api/wizard_chat.py:769: error: "str" has no attribute "message"  [attr-defined]
tests/test_wizard_agent.py:94: error: Missing named argument "language_notes" for "SettingCard"  [call-arg]
tests/test_wizard_agent.py:147: error: Missing named argument "dependents" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:147: error: Missing named argument "status" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:147: error: Missing named argument "fame" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:147: error: Missing named argument "reputation" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:147: error: Missing named argument "resources" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:147: error: Missing named argument "domain" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:147: error: Missing named argument "enemies" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:147: error: Missing named argument "obligations" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:184: error: Missing named argument "second" for "StoryTimestamp"  [call-arg]
tests/test_wizard_agent.py:378: error: Missing named argument "second" for "StoryTimestamp"  [call-arg]
tests/test_api/test_wizard_confirmation.py:83: error: Item "None" of "str | None" has no attribute "replace"  [union-attr]
tests/test_api/test_wizard_confirmation.py:154: error: Argument "thread_id" to "WizardContext" has incompatible type "str | None"; expected "str"  [arg-type]
tests/test_api/test_wizard_confirmation.py:168: error: Value of type "dict[str, Any] | None" is not indexable  [index]
tests/test_api/test_wizard_confirmation.py:175: error: Value of type "dict[str, Any] | None" is not indexable  [index]
tests/test_api/test_wizard_confirmation.py:176: error: Value of type "dict[str, Any] | None" is not indexable  [index]
tests/test_api/test_wizard_confirmation.py:179: error: Argument 1 to "_require_revision_submission" has incompatible type "DummyRunContext"; expected "RunContext[WizardContext]"  [arg-type]
tests/test_api/test_wizard_confirmation.py:372: error: Argument "model_settings" to "_handle_accept_fate_traits" has incompatible type "None"; expected "ModelSettings"  [arg-type]
tests/test_api/test_slot_mutation_guard.py:149: error: Incompatible types in assignment (expression has type "object", variable has type "dict[str, bool] | dict[str, int]")  [assignment]
Found 33 errors in 5 files (checked 13 source files)
```

### mypy, Main (the 12 Pre-existing Files, Checked Out in Place)

```
$ nice -n 15 $PY -m mypy --explicit-package-bases --cache-dir <scratch>/mypy-cache-wt-main <main's 12 pre-existing files>
nexus/api/setup_endpoints.py:13: error: Skipping analyzing "frontmatter": module is installed, but missing library stubs or py.typed marker  [import-untyped]
nexus/api/setup_endpoints.py:123: error: Argument "current_phase" to "ResumeSetupResponse" has incompatible type "str"; expected "Literal['setting', 'character', 'seed', 'ready']"  [arg-type]
nexus/api/setup_endpoints.py:124: error: Argument "pending_confirmation" to "ResumeSetupResponse" has incompatible type "str | None"; expected "Literal['setting', 'character'] | None"  [arg-type]
nexus/api/setup_endpoints.py:135: error: Argument "messages" to "ResumeSetupResponse" has incompatible type "list[dict[str, str]]"; expected "list[WizardHistoryMessage]"  [arg-type]
nexus/api/wizard_chat.py:17: error: Skipping analyzing "frontmatter": module is installed, but missing library stubs or py.typed marker  [import-untyped]
nexus/api/wizard_chat.py:241: error: No overload variant of "run" of "AbstractAgent" matches argument types "str", "WizardContext", "list[Any]", "Any", "ModelSettings"  [call-overload]
nexus/api/wizard_chat.py:281: error: Item "None" of "WizardCache | None" has no attribute "confirmation_metadata"  [union-attr]
nexus/api/wizard_chat.py:338: error: Incompatible types in assignment (expression has type "str", variable has type "Literal['setting', 'character', 'seed'] | None")  [assignment]
nexus/api/wizard_chat.py:621: error: No overload variant of "run" of "AbstractAgent" matches argument types "str | None", "WizardContext", "list[ModelRequest | ModelResponse]", "Model", "ModelSettings"  [call-overload]
nexus/api/wizard_chat.py:652: error: Argument after ** must be a mapping, not "dict[str, Any] | None"  [arg-type]
nexus/api/wizard_chat.py:752: error: "str" has no attribute "choices"  [attr-defined]
nexus/api/wizard_chat.py:755: error: "str" has no attribute "message"  [attr-defined]
nexus/api/wizard_chat.py:762: error: "str" has no attribute "message"  [attr-defined]
nexus/api/wizard_chat.py:768: error: "str" has no attribute "message"  [attr-defined]
tests/test_wizard_agent.py:93: error: Missing named argument "language_notes" for "SettingCard"  [call-arg]
tests/test_wizard_agent.py:146: error: Missing named argument "dependents" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:146: error: Missing named argument "status" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:146: error: Missing named argument "fame" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:146: error: Missing named argument "reputation" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:146: error: Missing named argument "resources" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:146: error: Missing named argument "domain" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:146: error: Missing named argument "enemies" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:146: error: Missing named argument "obligations" for "TraitRationales"  [call-arg]
tests/test_wizard_agent.py:183: error: Missing named argument "second" for "StoryTimestamp"  [call-arg]
tests/test_wizard_agent.py:377: error: Missing named argument "second" for "StoryTimestamp"  [call-arg]
tests/test_api/test_wizard_confirmation.py:83: error: Item "None" of "str | None" has no attribute "replace"  [union-attr]
tests/test_api/test_wizard_confirmation.py:154: error: Argument "thread_id" to "WizardContext" has incompatible type "str | None"; expected "str"  [arg-type]
tests/test_api/test_wizard_confirmation.py:168: error: Value of type "dict[str, Any] | None" is not indexable  [index]
tests/test_api/test_wizard_confirmation.py:175: error: Value of type "dict[str, Any] | None" is not indexable  [index]
tests/test_api/test_wizard_confirmation.py:176: error: Value of type "dict[str, Any] | None" is not indexable  [index]
tests/test_api/test_wizard_confirmation.py:179: error: Argument 1 to "_require_revision_submission" has incompatible type "DummyRunContext"; expected "RunContext[WizardContext]"  [arg-type]
tests/test_api/test_wizard_confirmation.py:358: error: Argument "model_settings" to "_handle_accept_fate_traits" has incompatible type "None"; expected "ModelSettings"  [arg-type]
tests/test_api/test_slot_mutation_guard.py:147: error: Incompatible types in assignment (expression has type "object", variable has type "dict[str, bool] | dict[str, int]")  [assignment]
Found 33 errors in 5 files (checked 12 source files)
```

## UI

```
$ nice -n 15 npm --prefix ui test -- InteractiveWizard SlotSelector WizardShell
 Test Files  5 passed (5)
      Tests  107 passed (107)
$ nice -n 15 npm --prefix ui run check     (exit 0)
$ nice -n 15 npm --prefix ui run build     (exit 0)
```

The whole UI suite, on 75cd1625:

```
$ nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 43 passed (44)
      Tests  677 passed (677)
```

The one failing file is the expected stale `state-shades.test.ts` (see
"State Surfaces"): the coordinator regenerates the state surfaces on the
wave's UI union branch. The other 43 files pass.

## State Surfaces

This branch does not regenerate the browser-resolved state surfaces. The
stale `state-shades.test.ts` failure ("Stale browser-resolved state
surfaces") is expected: the coordinator regenerates once on the wave's UI
union branch, and that regeneration covers this order's three closure files
(`InteractiveWizard.tsx`, `InteractiveWizard.test.tsx`,
`InteractiveWizard.transition.test.tsx`). An earlier commit (22ec5882) wrote
the receipt against that rule; 5f67524c restores main's receipt pointer and
decision 0067's `verified_commit`. On 5f67524c:

```
$ nice -n 15 npm --prefix ui test -- state-shades
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 1 passed (2)
      Tests  95 passed (95)
```
