# 824-S2ab Verification: Two Listeners, Re-Pointed Clients, CORS per Plane

Branch `claude/824-two-listeners`. Commits: 824-S2a `b36e92c4`, 824-S2b
`9f8f7b75`, merge of `origin/main` `48517d3c` (merge base `b0e9cb77`),
canonical re-stamps `35486cf2`, mypy typing of two new tests `29a691e8`.
"Main" below is the merge base `b0e9cb77`, exported with `git archive` to a
scratch directory (not a git worktree) for the red runs and the static
comparisons. A second merge brought in `e058005f` (845-S1S2, no conflicts,
no file this order touches), and the canonical documents were re-stamped to
that merge base; the doc, reachability and CLI-reference checks and the
launcher, CORS and supervisor unit files were rerun after it (last section).

## What Main Does Today (Cited Lines at `b0e9cb77`)

- `nexus.toml:1469`: the gateway service runs
  `["{python}", "-m", "uvicorn", "nexus.api.narrative:app", ...]` on
  `:1471` `port = 8002`; `:1387-1393` is one CORS list, `:1391` still lists
  `http://localhost:5173`.
- `nexus/api/narrative.py:1761`: the unprojected app declares itself the
  operator plane; `:115` `gateway_lifespan` sets no owner mark; `:161`
  installs the single CORS list on the source app.
- `nexus/api/route_capabilities.py:22`: "Binding each projection to its own
  listener is a later slice."; `:478`/`:492` `build_player_app` /
  `build_operator_app` have no production caller; `:409` `_shared_lifespan`
  guards projection against projection only; `:461` copies the source
  middleware; `:271` classifies `/runtime/status` as operator.
- `docs/runtime.md:171`: "beside a projection in one process is not yet
  detected"; `:180` "The gateway still serves the whole runtime on one
  listener."
- `nexus/runtime/supervisor.py:435` overwrites `gateway.port` with the lane;
  `:612` `_service_argv` knows one `{port}`; `:864` the record carries one
  port; `:1096` `down` waits for one port; `:1183`/`:1191` status reports one
  port; `:959` `up` echoes one URL; `:1145` `gateway_url()` is the service
  port.
- `nexus/api/runtime_status.py:102` reports one gateway port.
- `scripts/qa_shift/qa_shift.py:174` refuses only 8002.
- `scripts/check_reachability.py:270` raises "Unregistered Python service
  command" for any `{python}` command other than `-m uvicorn`.
- `nexus/cli.py:108` `DEFAULT_API_URL = "http://localhost:8002"`, returned at
  `:168`.
- `nexus/cli_contract.py:132-134` `clear`/`lock`/`unlock` are `http`; `:176`
  `model --set`/`--clear` are `http`.
- `nexus/runtime/readiness.py:1147` and `:1239` read `supervisor.gateway_url()`
  for `gateway.reachable` and the desktop `runtimeOrigin` comparison.
- `ui/src-tauri/nexus.desktop.json:2`, `ui/src-tauri/src/lib.rs:17`, `:720`,
  `:731`, `:737`, `nexus/runtime/desktop_config.py:40` pin
  `http://127.0.0.1:8002`; `ui/vite.config.ts:119` defaults the dev proxy to
  `8002`.

### Static Record of Main's Direct-Launch Default

`nexus/api/narrative.py:1779-1784` at `b0e9cb77`:

```python
    uvicorn.run(
        app,
        host=os.environ.get("NARRATIVE_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("NARRATIVE_API_PORT", "8002")),
        log_config=build_logging_config(_runtime.logs),
    )
```

Main serves the unprojected app on 8002 when `NARRATIVE_API_PORT` is unset.
`test_direct_launch_defaults_to_the_configured_operator_port` was therefore
never run on main (it would bind 8002).

## Owner Ports (`lsof -nP -iTCP:8002 -iTCP:8003 -sTCP:LISTEN`)

| When | Output | Exit |
|---|---|---|
| 19:01 CDT, before any work | (none) | 1 |
| 19:32 CDT, before the green PostgreSQL runs | (none) | 1 |
| 19:53 CDT, before the red runs | (none) | 1 |
| 19:54 CDT, after the red runs | (none) | 1 |
| 20:06 CDT, after every proof | (none) | 1 |

Every listener a test started took an OS-assigned port; nothing bound 8002
or 8003, on the branch or on main.

## Red Runs on Main (`b0e9cb77`, Branch Test Files Overlaid)

Offline (`NEXUS_SLOT`, `NEXUS_GATEWAY_PORT`, `NEXUS_PLAYER_PORT`,
`NEXUS_API_URL`, `NARRATIVE_API_PORT` unset):

```
FAILED tests/test_api/test_serve.py::test_launcher_serves_both_planes_and_stops_on_sigterm
  AssertionError: /Users/pythagor/nexus/.venv/bin/python: No module named nexus.api.serve
FAILED tests/test_api/test_serve.py::test_direct_launch_serves_the_operator_projection
  AssertionError: assert 'https://nexus.pythagora.net' is None
FAILED tests/test_api/test_serve.py::test_gateway_lifespan_excludes_projections
  Failed: DID NOT RAISE <class 'nexus.api.route_capabilities.RouteCapabilityError'>
FAILED tests/test_cli_contract.py::test_remote_profile_refuses_operator_route_commands[argv0..argv4]
  clear: exit 1 api_error (the stand-in got the request); lock, unlock,
  model --set, model --clear: exit 0, "Slot 5 locked" / "Model changed to None"
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
8 failed, 7 warnings in 7.94s
```

```
tests/test_api/test_cors.py
E   ModuleNotFoundError: No module named 'nexus.api.serve'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
7 warnings, 1 error in 0.67s
```

PostgreSQL (`NEXUS_RUN_POSTGRES=1 ... -p tests.dbname_audit`): each fails
before any process starts, at the temporary config's argv check, because
main ships the single-listener uvicorn argv:

```
>       assert command == GATEWAY_ARGV_TEMPLATE, command
E       AssertionError: ['{python}', '-m', 'uvicorn', 'nexus.api.narrative:app', '--host', '{host}', ...]
E         At index 2 diff: 'uvicorn' != 'nexus.api.serve'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa885_supervisor_*
dbname audit: owner targets: none
FAILED tests/test_runtime/test_supervisor_live.py::test_local_profile_full_lifecycle
FAILED tests/test_runtime/test_supervisor_live.py::test_gateway_port_override_coexists_with_default_instance
FAILED tests/test_runtime/test_supervisor_live.py::test_dual_plane_lane_opens_both_listeners
FAILED tests/test_runtime/test_supervisor_live.py::test_player_port_override_requires_gateway_port
4 failed in 2.85s
```

## Green Runs on the Branch

PostgreSQL run 1 (`35486cf2`; load average 14.92 before the run):

```
NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_runtime/test_supervisor_live.py tests/test_slot_routed_entrypoints.py \
  tests/test_live_gate_clones_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 9 targets: postgres, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*, qa885_entrypoints_*, qa885_supervisor_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
59 passed, 2 warnings in 97.92s (0:01:37)
```

PostgreSQL run 2 (`29a691e8`, the final product head; load average 14.04):

```
NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit \
  tests/test_api/test_serve.py tests/test_api/test_cors.py \
  tests/test_api/test_route_capabilities.py tests/test_cli_contract.py \
  tests/test_runtime/test_supervisor.py tests/test_runtime/test_readiness.py \
  tests/test_runtime/test_readiness_pg.py tests/test_runtime/test_remote_auth.py \
  tests/test_runtime/test_desktop_config.py tests/config/test_settings_models.py \
  tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 17 targets: postgres, qa640_1013_readiness_* x2, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_offline_gate_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:62546 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:62547 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:62546 (psycopg2), save_04@local:62547 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
530 passed, 2 skipped, 7 warnings in 306.50s (0:05:06)
```

Golden-path default port (never run; it is paid):

```
$ PYTHONPATH=$PWD $PY -c 'import tests.test_golden_path_live as g; print(g.API)'
http://localhost:8003
```

Offline suites:

```
nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery   # 35486cf2
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3282 passed, 704 skipped, 8 warnings in 675.85s (0:11:15)

nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery   # 29a691e8
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1923 passed, 1547 skipped, 7 warnings in 56.01s

$PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py tests/test_cli_reference_doc.py   # 29a691e8
160 passed, 5 warnings in 16.75s
```

`docs/cli_reference.md` was regenerated after the last merge
(`$PY -m scripts.render_cli_reference --write`, no further change).

## UI and Rust

```
nice -n 15 npm --prefix ui ci         # exit 0
nice -n 15 npm --prefix ui run check  # exit 0 (tsc, then check:design-sync)
nice -n 15 npm --prefix ui test       # exit 1, the expected stale receipt only:
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 43 passed (44)
      Tests  667 passed (667)
nice -n 15 npm --prefix ui run build  # exit 0
```

`vite.config.ts` is a state-surface freshness input
(`ui/scripts/state-surfaces/inputs.mjs:37`); the coordinator regenerates the
receipt on the wave's UI union.

Cargo did not run: this machine has not accepted the Xcode license, so `cc`
cannot link any build script.

```
CARGO_TARGET_DIR=<scratch>/824-S2ab/cargo nohup nice -n 15 cargo test \
  --manifest-path ui/src-tauri/Cargo.toml --lib
error: linking with `cc` failed: exit status: 69
  = note: You have not agreed to the Xcode license agreements. Please run 'sudo xcodebuild -license' from within a Terminal window to review and agree to the Xcode and Apple SDKs license.
error: could not compile `serde_json` (build script) due to 1 previous error
```

The Rust change is four string literals (`lib.rs:17`, `:720`, `:731`,
`:737`) from `8002` to `8003`;
`tests/test_runtime/test_desktop_config.py::test_shipped_shell_targets_the_operator_listener`
reads `DEFAULT_RUNTIME_ORIGIN` from `lib.rs` and checks it against the
shipped config and `operator_url`. The `cargo test` gate stays open until
the license is accepted.

## Static Checks (Branch vs `b0e9cb77`, the 35 Changed or Added Python Files)

- Black: `35 files would be left unchanged`.
- flake8: 73 diagnostics on both sides. The only keyed difference is the
  pre-existing `nexus/api/narrative.py` F811 "redefinition of unused
  'slot_dbname'", which names line 56 instead of 57 after the removed
  `CORSMiddleware` import.
- mypy (`--explicit-package-bases`): no diagnostic on the branch that main
  lacks. The two new-test diagnostics found on the first pass (an Optional
  `remediation` and a tomlkit index) are fixed in `29a691e8`.
- `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`:
  `OK: exception disposition coverage and shrink-only baseline verified.` The
  `Supervisor._await_healthy` baseline entry is removed: its health probe
  moved to `Supervisor._health_answer` with a `retry` marker.
- `scripts/check_reachability.py`: exit 0; `nexus/api/serve.py` is added to
  `production_reachable` in `config/reachability_baseline.json`.

## After the Second Merge (`e058005f`)

The re-stamp commit's tails are recorded in the PR body: the doc front
matter, CLI reference and reachability tests, the exception-disposition
lint, and `tests/test_api/test_serve.py`, `tests/test_api/test_cors.py` and
`tests/test_runtime/test_supervisor.py` offline.
