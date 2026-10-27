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
The review fixes are `4c4031e4`; a third merge `688e90e9` brought in
`d295eef0` (1102-S1, #1170, UI only, no conflicts, no file this order
touches). The one source the fixes touch again, `docs/runtime.md` (0061,
0079), only moved its `/health` paragraph back above the new subsection, so
no record's claim changed. The supervisor sites the fixes edit were located
on the branch head `5dee9e73` (which contains `9a0714d7`), not by the
order's `c7ae2988` line numbers: before the fix, at `5dee9e73`, the
unmanaged-port refusal is `supervisor.py:943-949`, the plane check `:852`
and `_health_answer` `:876`; after the fix, at `4c4031e4`, they sit at
`:963-969`, `:865` and `:889`. The second review round is `5d2734d6` (code
and tests) and `f6af9784` (the 25 canonical documents re-stamped from
`e058005f` to the merge base `d295eef0`); its evidence is the last section,
"After the Round-2 Review Fixes", whose tails all ran on `f6af9784`.

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

`nexus/api/narrative.py:1780-1785` at `b0e9cb77` (`:1783` is the
`NARRATIVE_API_PORT` default of `"8002"`):

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
| 20:25 CDT, before the review-fix runs | (none) | 1 |
| 20:31 CDT, before and after the behavioral red runs | (none) | 1 |
| 20:32 CDT, before and after the offline red reruns | (none) | 1 |
| 20:35 CDT, after the review-fix proofs | (none) | 1 |

Every listener a test started took an OS-assigned port; nothing bound 8002
or 8003, on the branch or on main.

## Red Runs on Main (`b0e9cb77`, Branch Test Files Overlaid)

The red runs that replace the first pass's were made after the review, on a
fresh export of the merge base:

```
git archive b0e9cb77 | tar -x -C /private/tmp/claude-501/-Users-pythagor-nexus/9dcd8ba0-5aed-4efa-8d64-38cffa54a15d/scratchpad/824-S2ab/red_b0e9cb77
```

The export is a plain directory, not a git worktree. Each run used
`cd /private/tmp/claude-501/-Users-pythagor-nexus/9dcd8ba0-5aed-4efa-8d64-38cffa54a15d/scratchpad/824-S2ab/red_b0e9cb77` and `PYTHONPATH=` that directory (`nexus.__file__`
resolved inside it), with `NEXUS_GATEWAY_PORT`, `NEXUS_PLAYER_PORT`,
`NEXUS_API_URL`, `NEXUS_SLOT` and `NARRATIVE_API_PORT` unset. Overlaid files,
each byte-identical to the branch at `4c4031e4` except the one marked:

- `tests/test_api/test_serve.py`
- `tests/test_cli_contract.py`
- `tests/test_api/test_cors.py`
- `tests/test_runtime/test_supervisor_live.py`, with a red-only overlay so
  that its temporary config is one main accepts (every port stays
  OS-assigned):

  ```
  73c73
  < ROUTED_LAUNCHER = "tests.slot_routed_serve"
  ---
  > ROUTED_LAUNCHER = "tests.slot_routed_uvicorn"  # RED OVERLAY: main's launcher
  78c78
  < GATEWAY_ARGV_TEMPLATE = [
  ---
  > GATEWAY_ARGV_TEMPLATE = [  # RED OVERLAY: main's single-listener argv
  81c81,82
  <     "nexus.api.serve",
  ---
  >     "uvicorn",
  >     "nexus.api.narrative:app",
  86,87d86
  <     "--operator-port",
  <     "{operator_port}",
  191c190
  <     doc["runtime"]["gateway"]["operator_port"] = OPERATOR_PORT
  ---
  >     # RED OVERLAY: main's [runtime.gateway] forbids operator_port.
  ```

### Offline

```
nice -n 15 $PY -m pytest -q \
  tests/test_api/test_serve.py::test_launcher_serves_both_planes_and_stops_on_sigterm \
  tests/test_api/test_serve.py::test_direct_launch_serves_the_operator_projection \
  tests/test_api/test_serve.py::test_gateway_lifespan_excludes_projections \
  tests/test_cli_contract.py::test_remote_profile_refuses_operator_route_commands
```

Failure lines, verbatim:

```
E           AssertionError: /Users/pythagor/nexus/.venv/bin/python: No module named nexus.api.serve
tests/test_api/test_serve.py:123: AssertionError
E       AssertionError: assert 'https://nexus.pythagora.net' is None
tests/test_api/test_serve.py:299: AssertionError
>           with pytest.raises(RouteCapabilityError, match="already running"):
E           Failed: DID NOT RAISE <class 'nexus.api.route_capabilities.RouteCapabilityError'>
>           with pytest.raises(RouteCapabilityError, match="already running"):
E           Failed: DID NOT RAISE <class 'nexus.api.route_capabilities.RouteCapabilityError'>
E       assert 1 == <ExitCode.TRANSPORT_REFUSED: 3>
E        +  where 1 = CompletedProcess(args=['/Users/pythagor/nexus/.venv/bin/python', '-m', 'nexus.cli', 'clear', '--slot', '5', '--json'],...ror": "API error: {\\"detail\\": \\"Not Found\\"}",\n  "ok": false,\n  "partial": {\n    "status_code": 404\n  }\n}\n').returncode
E       assert 0 == <ExitCode.TRANSPORT_REFUSED: 3>
E        +  where 0 = CompletedProcess(args=['/Users/pythagor/nexus/.venv/bin/python', '-m', 'nexus.cli', 'lock', '--slot', '5', '--json'], returncode=0, stdout='{\n  "message": "Slot 5 locked",\n  "success": true\n}\n', stderr='').returncode
E       assert 0 == <ExitCode.TRANSPORT_REFUSED: 3>
E        +  where 0 = CompletedProcess(args=['/Users/pythagor/nexus/.venv/bin/python', '-m', 'nexus.cli', 'unlock', '--slot', '5', '--json'], returncode=0, stdout='{\n  "message": "Slot 5 unlocked",\n  "success": true\n}\n', stderr='').returncode
E       assert 0 == <ExitCode.TRANSPORT_REFUSED: 3>
E        +  where 0 = CompletedProcess(args=['/Users/pythagor/nexus/.venv/bin/python', '-m', 'nexus.cli', 'model', '--slot', '5', '--set', '..., returncode=0, stdout='{\n  "message": "Model changed to None",\n  "model": null,\n  "success": true\n}\n', stderr='').returncode
E       assert 0 == <ExitCode.TRANSPORT_REFUSED: 3>
E        +  where 0 = CompletedProcess(args=['/Users/pythagor/nexus/.venv/bin/python', '-m', 'nexus.cli', 'model', '--slot', '5', '--clear',..., returncode=0, stdout='{\n  "message": "Model changed to None",\n  "model": null,\n  "success": true\n}\n', stderr='').returncode
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_api/test_serve.py::test_launcher_serves_both_planes_and_stops_on_sigterm
FAILED tests/test_api/test_serve.py::test_direct_launch_serves_the_operator_projection
FAILED tests/test_api/test_serve.py::test_gateway_lifespan_excludes_projections[gateway]
FAILED tests/test_api/test_serve.py::test_gateway_lifespan_excludes_projections[projection]
FAILED tests/test_cli_contract.py::test_remote_profile_refuses_operator_route_commands[argv0]
FAILED tests/test_cli_contract.py::test_remote_profile_refuses_operator_route_commands[argv1]
FAILED tests/test_cli_contract.py::test_remote_profile_refuses_operator_route_commands[argv2]
FAILED tests/test_cli_contract.py::test_remote_profile_refuses_operator_route_commands[argv3]
FAILED tests/test_cli_contract.py::test_remote_profile_refuses_operator_route_commands[argv4]
9 failed, 7 warnings in 8.06s
```

The lifespan-exclusion test now runs each order as its own case: `[gateway]`
starts `narrative.app` and then a player projection, `[projection]` starts
an operator projection and then `narrative.app`. Main lets both pairs start.

```
nice -n 15 $PY -m pytest -q tests/test_api/test_cors.py
tests/test_api/test_cors.py:12: in <module>
    from nexus.api.serve import build_plane_app
E   ModuleNotFoundError: No module named 'nexus.api.serve'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
ERROR tests/test_api/test_cors.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
7 warnings, 1 error in 0.65s
```

`test_direct_launch_defaults_to_the_configured_operator_port` was not run on
main (with `NARRATIVE_API_PORT` unset it would bind 8002).

### PostgreSQL: Behavior, Not the Argv Check

The first pass's four PostgreSQL reds stopped at `_write_config`'s
`assert command == GATEWAY_ARGV_TEMPLATE`. With the overlay above, main's
supervisor starts real processes and each test fails on the behavior the
order names (load average 9.51 before the run):

```
NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_runtime/test_supervisor_live.py::test_local_profile_full_lifecycle \
  tests/test_runtime/test_supervisor_live.py::test_gateway_port_override_coexists_with_default_instance \
  tests/test_runtime/test_supervisor_live.py::test_dual_plane_lane_opens_both_listeners \
  tests/test_runtime/test_supervisor_live.py::test_player_port_override_requires_gateway_port
            assert _port_open("127.0.0.1", GATEWAY_PORT)
>           assert _port_open("127.0.0.1", OPERATOR_PORT)
E           AssertionError: assert False
E            +  where False = _port_open('127.0.0.1', 59923)
tests/test_runtime/test_supervisor_live.py:276: AssertionError
>           assert lane["port"] is None
E           assert 59955 is None
tests/test_runtime/test_supervisor_live.py:518: AssertionError
>           assert gateway["port"] == PLAYER_OVERRIDE_PORT
E           assert 59999 == 60000
tests/test_runtime/test_supervisor_live.py:583: AssertionError
>           assert result["_returncode"] != 0, result
E           AssertionError: {'_returncode': 0, 'profile': 'local', 'services': {'gateway': {'command': ['/Users/pythagor/nexus/.venv/bin/python', ...-pythagor/pytest-635/test_player_port_override_requ0/state/mock_openai.log', 'log_writer_pid': 93760, ...}}, 'slot': 5}
E           assert 0 != 0
tests/test_runtime/test_supervisor_live.py:610: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa885_supervisor_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_runtime/test_supervisor_live.py::test_local_profile_full_lifecycle
FAILED tests/test_runtime/test_supervisor_live.py::test_gateway_port_override_coexists_with_default_instance
FAILED tests/test_runtime/test_supervisor_live.py::test_dual_plane_lane_opens_both_listeners
FAILED tests/test_runtime/test_supervisor_live.py::test_player_port_override_requires_gateway_port
4 failed in 18.49s
```

Main opens only the player port (no operator listener), runs a
`NEXUS_GATEWAY_PORT` lane as one listener with `port` equal to the lane,
ignores `NEXUS_PLAYER_PORT` beside a lane, and ignores it alone, so `up`
exits 0 and the test's `finally` runs `down`.

### Supervisor Plane Refusal (Branch, Check Disabled)

`test_up_refuses_a_gateway_that_serves_the_wrong_plane` configures the
pre-#824 argv (`tests.slot_routed_uvicorn nexus.api.narrative:app --host
{host} --port {port} --log-config {log_config}`). Its red run is on the
branch at `4c4031e4` with `supervisor.py:865` changed from
`if not plane or answer.get("plane") == plane:` to `if True:` in the working
tree, then restored with `git checkout -- nexus/runtime/supervisor.py`:

```
NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_runtime/test_supervisor_live.py::test_up_refuses_a_gateway_that_serves_the_wrong_plane
>           assert "as plane 'operator', not 'player'" in result["error"]
E           assert "as plane 'operator', not 'player'" in "Service 'gateway' failed to become healthy at http://127.0.0.1:59538/health within 30.0s. Last log lines:\n2026-10-26...NFO - Application shutdown complete.\n2026-10-26 20:30:28,632 - uvicorn.error - INFO - Finished server process [89545]"
tests/test_runtime/test_supervisor_live.py:498: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa885_supervisor_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_runtime/test_supervisor_live.py::test_up_refuses_a_gateway_that_serves_the_wrong_plane
1 failed in 33.97s
```

Without the check the supervisor accepts the operator answer on the player
port and waits out the deadline for an operator listener that never opens.

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

PostgreSQL run 2 (`29a691e8`; not the product head: `4c4031e4` and `5d2734d6`
changed product code afterwards, and this set was rerun at `f6af9784` in the
last section; load average 14.04):

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

These UI tails ran at 19:42 CDT on the branch before merge `688e90e9`
brought in `d295eef0` (which changes `LocalModelRows.tsx` and its test);
their commit was not recorded. The rerun on `f6af9784`, the merged branch,
is in the last section and supersedes them.

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
shipped config and `operator_url`; it does not compile or run the test
literals at `:720`, `:731` and `:737`.

Rechecked at 20:33 CDT for the review fixes, still blocked:

```
$ cc lic.c -o lic        # a one-line C program in the scratch directory
You have not agreed to the Xcode license agreements. Please run 'sudo xcodebuild -license' from within a Terminal window to review and agree to the Xcode and Apple SDKs license.
cc exit 69
```

**Open gate, owed before merge:** after the owner accepts the license
(`sudo xcodebuild -license`), run
`CARGO_TARGET_DIR=<scratch>/824-S2ab/cargo nice -n 15 cargo test --manifest-path ui/src-tauri/Cargo.toml --lib`
on the PR head and paste its tail, with the commit id, here and in the PR;
or the coordinator records a waiver on #824.

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
  moved to `Supervisor._health_answer` with a `retry` marker. Its JSON
  handler carries `fail` (see "After the Review Fixes").
- `scripts/check_reachability.py`: exit 0; `nexus/api/serve.py` is added to
  `production_reachable` in `config/reachability_baseline.json`.

## After the Review Fixes (`4c4031e4`)

The first pass's reachability/doc/CLI-reference run (160 passed) and the
post-merge run (252 passed, recorded only in the PR body) were saved without
their guard lines. Both are superseded by the runs below, at `4c4031e4`,
whose tails are pasted whole.

PostgreSQL run 1 (load average 17.52 before the run):

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
60 passed, 2 warnings in 102.17s (0:01:42)
```

Supervisor files together (load average 17.32):

```
NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit \
  tests/test_runtime/test_supervisor_live.py tests/test_runtime/test_supervisor.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 2 targets: postgres, qa885_supervisor_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
92 passed in 90.46s (0:01:30)
```

Offline, the files the fixes touch plus the doc, CLI-reference and
reachability checks:

```
nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py tests/test_cli_reference_doc.py \
  tests/test_reachability.py tests/test_api/test_serve.py tests/test_api/test_cors.py \
  tests/test_runtime/test_supervisor.py tests/test_fable_probe_parsing.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
259 passed, 7 warnings in 62.64s (0:01:02)
```

After the merge of `d295eef0` (`688e90e9`):

```
$PY -m pytest -q tests/test_doc_front_matter.py
89 passed, 5 warnings in 7.43s
```

Static checks on the files the fixes change: Black leaves all five
unchanged; flake8 reports nothing on `nexus/runtime/supervisor.py` and the
four test files; mypy `--explicit-package-bases nexus/runtime/supervisor.py`
reports the same eight pre-existing diagnostics as the PR head `5dee9e73`
(Windows-only `subprocess` constants, Optional `external`/`remote`);
`$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`
prints `OK: exception disposition coverage and shrink-only baseline verified.`

What the fixes change:

- `Supervisor._start_service`'s unmanaged-port refusal names the key that
  sets the held listener: `[runtime.gateway].operator_port` (or
  `NEXUS_GATEWAY_PORT` in a lane) for the operator listener,
  `NEXUS_PLAYER_PORT` for a lane's player listener, otherwise
  `[runtime.services.<name>] port`. `test_up_refuses_port_held_by_unmanaged_process`
  asserts the key for each held port.
- `Supervisor._health_answer(url, plane)` parses JSON only for a gateway
  listener, so its `ValueError` handler runs only where the plane check then
  refuses the answer, and the `fail` marker is accurate. A service with no
  plane keeps the 200-is-healthy contract without parsing.
- `tests/test_api/test_serve.py::test_launcher_exits_nonzero_when_the_operator_port_is_held`:
  the operator port held, the launcher exits 1, the player port never opens
  and no player banner is logged.
- `tests/test_fable_structured_output_live.py::probe_lane` refuses 8002 and
  8003 (`OWNER_GATEWAY_PORTS`); `test_probe_lane_refuses_unset_and_play_port`
  covers both.
- `docs/runtime.md`: the `/health` paragraph stays in the planes section and
  "Listeners and the Tunnel" follows it, before "Profiles".

## After the Round-2 Review Fixes (`5d2734d6`, `f6af9784`, Merge `52465f4b`)

Commits: `5d2734d6` (code and tests), `f6af9784` (the 25 branch-stamped
canonical documents moved from `e058005f` to the then merge base
`d295eef0`), and `52465f4b`, a merge of `origin/main` at `571f982b`
(845-S3 #1172, 813-S4S5 #1168, 821-S2 #1171). The merge's only conflicts
were `verified_commit` lines: main had re-stamped the shared documents to
`b75f6241`; every one of the 25 now carries the new merge base `571f982b`.
`docs/cli_reference.md` was regenerated after the merge (no change). Every
tail in this section ran on `52465f4b` unless it names another commit; each
run had `NEXUS_GATEWAY_PORT`, `NEXUS_PLAYER_PORT`, `NEXUS_API_URL`,
`NARRATIVE_API_PORT` and `NEXUS_SLOT` unset, and
`lsof -nP -iTCP:8002 -iTCP:8003 -sTCP:LISTEN` was empty (exit 1) before and
after.

What the fixes change:

- `gateway_listener_ports` (`nexus/runtime/contract.py`) refuses a lane port
  (`NEXUS_GATEWAY_PORT` or `NEXUS_PLAYER_PORT`) equal to
  `[runtime.services.gateway].port` (the tunnel's address) or
  `[runtime.gateway].operator_port` (the default instance's operator
  listener), naming the variable and the key. The finding's optional player
  case is taken, for both configured ports. `test_connection_lifecycle.py`
  set its operator-only lane equal to the configured player port; it now
  gives the configured player port its own OS-assigned port, never bound.
- `nexus.api.serve.main` applies `--log-config` (`_configure_logging`,
  mirroring uvicorn 0.34's `.json`/`.yaml`/`fileConfig` dispatch) before it
  imports the gateway, so import-time records carry the `[runtime.logs]`
  format.
- `test_launcher_serves_both_planes_and_stops_on_sigterm` runs under
  `SIGTERM` and `SIGINT`, asserts exit 0 for `SIGINT`, and asserts a
  formatted `nexus.api.static_ui` record.
- The unmanaged-port refusal spells the configured key
  `[runtime.services.<name>].port`, as `__init__`'s collision check does.
- New `test_lane_refusal_names_the_lane_variable_of_the_held_port`
  (`player`, `operator`): a dual-plane lane with one lane port held refuses
  with "Adjust NEXUS_PLAYER_PORT or stop" or "Adjust NEXUS_GATEWAY_PORT or
  stop", writes no pidfile and leaves the other lane port closed. It covers
  `_listener_port_key`'s lane branches, which `4c4031e4` added; it is not a
  red test.
- `NEXUS_PLAYER_PORT` joins every remaining test env strip that dropped
  only `NEXUS_GATEWAY_PORT`: `tests/test_cli.py`,
  `tests/test_fable_probe_parsing.py`, `tests/test_logon_mock_integration.py`,
  `tests/test_scheduler_helpers_basetemp.py`,
  `tests/test_api/test_local_inference.py`,
  `tests/test_runtime/test_desktop_config.py`,
  `tests/test_runtime/test_init_plan.py`,
  `tests/test_runtime/test_init_plan_pg.py`,
  `tests/test_runtime/test_logging_config.py` (three) and
  `tests/test_runtime/test_remote_auth.py`.

Red runs (the new tests against the PR head `fbe20636`'s product file,
restored afterwards):

```
$ git show HEAD:nexus/api/serve.py > nexus/api/serve.py   # HEAD = fbe20636
$ nice -n 15 $PY -m pytest -q tests/test_api/test_serve.py::test_launcher_serves_both_planes_and_stops_on_sigterm
E       AssertionError: 2026-10-26 20:54:14,650 - uvicorn.error - INFO - Started server process [55764]
tests/test_api/test_serve.py:184: AssertionError
FAILED tests/test_api/test_serve.py::test_launcher_serves_both_planes_and_stops_on_sigterm[SIGTERM]
FAILED tests/test_api/test_serve.py::test_launcher_serves_both_planes_and_stops_on_sigterm[SIGINT]
2 failed, 5 warnings in 3.95s
```

Both fail only at the `nexus.api.static_ui` assertion: the launcher log has
no `static_ui` record at all, because it was logged before logging was
configured. The `SIGINT` case had already passed its exit-0 assertion.

```
$ git show HEAD:nexus/runtime/contract.py > nexus/runtime/contract.py   # HEAD = fbe20636
$ nice -n 15 $PY -m pytest -q tests/test_runtime/test_supervisor.py::test_gateway_listener_ports_follow_the_lane_contract
>           with pytest.raises(ValueError, match=f"{variable}={value} is {key}"):
E           Failed: DID NOT RAISE <class 'ValueError'>
tests/test_runtime/test_supervisor.py:249: Failed
1 failed, 5 warnings in 0.43s
```

Green, the launcher and supervisor unit files at `5d2734d6`'s tree:

```
nice -n 15 $PY -m pytest -q tests/test_api/test_serve.py tests/test_runtime/test_supervisor.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
85 passed, 7 warnings in 42.88s
```

PostgreSQL run 1 (load average 6.63 before the run):

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
62 passed, 2 warnings in 112.72s (0:01:52)
```

PostgreSQL run 2, the full twelve-file set (load average 9.07):

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
dbname audit: registered disposable clusters: two_clusters[0] at local:53783 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:53795 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:53783 (psycopg2), save_04@local:53795 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
533 passed, 2 skipped, 7 warnings in 333.57s (0:05:33)
```

Both PostgreSQL sets also passed at `f6af9784`, before the merge (62 passed;
533 passed, 2 skipped, the same corpus skips).

Offline suites:

```
nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3300 passed, 708 skipped, 8 warnings in 725.59s (0:12:05)

nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1926 passed, 1570 skipped, 7 warnings in 59.01s
```

The first half also ran at `f6af9784`, before the merge, and failed one
test only because `origin/main` moved during the run:
`tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline`
compares the tree with `origin/main`, whose baseline 813-S4S5 (#1168) had
just shrunk (`nexus/agents/memnon/memnon.py:347: baseline growth forbidden:
... MEMNON.get_schema_summary ...`; `1 failed, 3299 passed, 708 skipped`).
After the merge it passes (the run above, and the next block).

```
nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py tests/test_cli_reference_doc.py \
  tests/test_reachability.py tests/test_scripts/test_check_exception_dispositions.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
254 passed, 5 warnings in 38.10s
$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
$ PYTHONPATH=$PWD $PY -c 'import tests.test_golden_path_live as g; print(g.API)'
http://localhost:8003
```

UI, on the merged branch (which includes `d295eef0`'s `LocalModelRows` and
`571f982b`'s `SettingsPane` changes):

```
nice -n 15 npm --prefix ui ci         # exit 0
nice -n 15 npm --prefix ui run check  # exit 0
nice -n 15 npm --prefix ui test       # exit 1, only the expected stale receipt:
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 43 passed (44)
      Tests  673 passed (673)
nice -n 15 npm --prefix ui run build  # exit 0
```

Cargo, rechecked at 21:27 CDT on `52465f4b`, still blocked:

```
CARGO_TARGET_DIR=<scratch>/824-S2ab/cargo nice -n 15 cargo test --manifest-path ui/src-tauri/Cargo.toml --lib
error: linking with `cc` failed: exit status: 69
  = note: You have not agreed to the Xcode license agreements. Please run 'sudo xcodebuild -license' from within a Terminal window to review and agree to the Xcode and Apple SDKs license.
cargo exit 101
```

The cargo gate stays open: the owner accepts the license and the test runs
on the PR head, or the coordinator records a waiver on #824 naming the four
unrun Rust literals (`lib.rs:17`, `:720`, `:731`, `:737`).

Static checks on the 17 Python files `5d2734d6` changes, against their
`fbe20636` versions: Black leaves all 17 unchanged; flake8 reports only the
two pre-existing `tests/test_connection_lifecycle.py` diagnostics (`:111`
E501, `:161` F811), the same on both sides; mypy `--explicit-package-bases`
reports 40 errors on both sides, identical apart from line numbers:
`nexus/runtime/supervisor.py` (11: Windows-only `subprocess` constants,
Optional `external`/`remote`), `tests/test_connection_lifecycle.py` (24,
tomlkit indexing), `tests/test_runtime/test_remote_auth.py` (7),
`tests/test_runtime/test_supervisor_live.py` (2) and `tests/test_cli.py`
(1, an untyped import).
