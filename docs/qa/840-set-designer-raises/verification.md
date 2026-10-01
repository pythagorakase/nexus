# 840-S3a Verification

Date: 2026-10-01 (America/Chicago). Product and test commit: `b2aa6a1437a59a5deb7c8e5e3bd38f3c4e6f788c`.
Base: `5b977eabcba5f7aedf1a64a6ee20c021ab290911`. `git fetch origin; git rebase origin/main` reported the branch current; no conflicts or new base changes.

Refs #840. Implemented under frozen 840-S3a and Amendment 1, applying LG-Q1, “B. Release all three now.”
The streaming live failure and success tests are dropped under the amendment: [#1081](https://github.com/pythagorakase/nexus/issues/1081) owns the async-context-manager loop and TEST SSE transport. There are no prerequisite landing commits to cite: the amendment withdrew that condition. The loop is unchanged. No live streaming success or design-failure claim is made.

## Verified Source Evidence

All current citations below were checked against the product/test commit above. Baseline defect citations explicitly name the base commit.

- At base `5b977eab`, `nexus/api/wizard_chat.py:735-774`, `:778-818`, `:1133-1172`, and `:1179-1212` contain the four swallowing handlers. The baseline failure response below reproduces the non-streaming TEST defect: HTTP 200 with a partial artifact and `set_design_error` after a rejected design UPDATE.
- At the implementation commit, `nexus/api/wizard_chat.py:735-772` and `:774-809` let TEST queries, production generation and guarded persistence reach the existing boundary at `:848-855`. Streaming branches at `:1119-1160` and `:1162-1196` also contain no inner handler. The AST proof at `tests/test_api/test_set_designer_failure.py:306-348` counts two queries, two generator calls and four draft writes, rejecting any inner Try.
- `rg -n 'set_design_error' nexus ui/client/src` and `rg -n 'set_design_error' nexus/cli.py` both return no matches after the change. At the base only the four assignments exist; there is no client/CLI consumer.
- The streaming general boundary at `nexus/api/wizard_chat.py:1245-1253` logs the exception, uses the non-streaming cause expression, yields one newline-terminated 500 error record and returns. Existing HTTPException and 409 serialization stay at `:1237-1244`. This is source/structural evidence, not a live streaming proof.
- The unmodified loop remains at `nexus/api/wizard_chat.py:1071-1077`; installed Pydantic AI `agent/abstract.py:406-407` marks `run_stream` as `@asynccontextmanager`. TEST request schema `nexus/api/mock_openai.py:410-415` and completion return `:746-763` still provide no SSE path. These #1081 findings are source inspection, not an executed streaming reproduction.
- Registry-based provider identity stays at `nexus/api/wizard_chat.py:730` and `:1119`, using `nexus/config/settings_models.py:4532-4539`. No provider identity rule changes.
- `_record_set_design` still guards `record_drafts` at `nexus/api/wizard_chat.py:356-360`; `nexus/api/new_story_cache.py:1716-1759` constructs one UPDATE for layer, zone and location. The seed was committed first by `nexus/api/wizard_agent.py:574-593` and the deferred-tool guard at `:324-333`. The rejected design does not roll back that seed.
- The success assertions at `tests/test_api/test_set_designer_failure.py:243-266` compare the artifact, all design values and current confirmation metadata. Failure assertions at `:269-303` verify HTTP 500 naming the constraint, all eight design fields NULL, retained seed and `seed_complete() == False`.
- UI behavior is source evidence only: `ui/client/src/components/NewStoryWizard/InteractiveWizard.tsx:874-886` calls non-streaming chat and throws on a non-OK response; `:928-939` displays the Transmission Error toast. No UI component changes or rendered/UI proof are claimed.

## Isolation and Cleanup

The fixture in `tests/test_api/test_set_designer_failure.py:159-240` uses separate disposable target/source clones, production cache writers, real confirmation actions and a real TEST ConversationsClient. Source routing is temporary during setup, before any server starts. Slot 4 is then routed to the target before either server starts. Only `mock_openai.MOCK_DB` changes to route the real TEST app's query to the source. The agent, generator, cache reader, writer, guard, provider builder and telemetry recorder are not replaced.

The gateway runs on 8024 using `test_provider_config` and `gateway_lane`; its private config/state and usage records are under pytest `tmp_path`. The TEST server owns a distinct ephemeral loopback socket above 8013. `gateway_lane` checks 8024 with lsof and invokes routed `nexus down` under the same private environment on exit. Both server threads are joined and the TEST thread is deleted. No owner gateway, mock server, runtime state, save database or template was written. The required clone helper reads template schema/seed data in subprocesses; the audit explicitly does not cover those subprocesses or C `ReplicationConnection` classes.

Final proof: success used TEST port 52850; failure used 52867. Subsequent `lsof -nP -iTCP:<port> -sTCP:LISTEN` returned exit 1 for both, as did lane 8024. Read-only cleanup SQL on postgres:

```sql
SELECT datname FROM pg_database WHERE datname LIKE 'qa640_840s3a_%';
-- []
```

The final two real HTTP tests each recorded one `provider=test`, `model=TEST`, `seat=wizard`, `slot=4` aggregate, with synthetic TEST usage 1000 input / 800 output / 1800 total tokens. No paid provider was called; the pytest TEST-only and secret-store guards remained active. Offline suites may fabricate usage as part of their own unit tests; these figures concern the real new HTTP proof only.

## Endpoint Responses and Persistence

Each snapshot below was captured by real `read_cache_raw` before and after the HTTP request. The response body is verbatim. The selected persistence fields cover every layer/zone column, initial_location, seed and timestamp. Complete raw snapshots and logs remain under the order scratchpad.

### Pre-Edit Success

Target: `qa640_840s3a_slot_41d34b52b74b`. Source: `qa640_840s3a_source_c7698448aaa1`.

`POST /api/story/new/chat` with `slot=4`, the fixture thread, `current_phase="seed"`, `message="Begin at the harbor."`. HTTP 200.

```json
{"message":"Generating artifact...","phase_complete":true,"subphase_complete":false,"phase":"seed","artifact_type":"submit_starting_scenario","data":{"seed":{"seed_type":"discovery","title":"The Harbor Bell","situation":"Mara finds a damaged harbor crane before the morning shift.","hook":"An unsigned warning links the damage to the planned yard closure.","immediate_goal":"Inspect the crane before the workers arrive.","stakes":"The workers' safety and the future of the repair yard.","tension_source":"The foreman wants the dock reopened immediately.","base_timestamp":{"year":2024,"month":6,"day":15,"hour":8,"minute":0,"second":0},"weather":"Clear morning","key_npcs":["The harbor foreman"],"secrets":"The crane was disabled by someone trying to delay the closure."},"location_sketch":"A place called Baltimore Inner Harbor in the Baltimore Harbor region of Earth. A busy waterfront where harbor workers gather beside the repair dock."},"location_sketch":"A place called Baltimore Inner Harbor in the Baltimore Harbor region of Earth. A busy waterfront where harbor workers gather beside the repair dock.","requires_set_design":true,"thread_id":"test_thread_ad44b65fa9a348cf","pending_confirmation":null,"artifact_token":"c5ef9ead7ba74dcd0019fc03e7af843963204517d04d79af319c0daacdbe9483","character_revision_pending":false,"set_design":{"layer":{"name":"Earth","type":"planet","description":"The real Earth in the year 2024."},"zone":{"name":"Baltimore Harbor","summary":"Baltimore's working waterfront in Maryland."},"location":{"name":"Baltimore Inner Harbor","history":"The waterfront has supported generations of Baltimore workers.","secrets":"A warning note is tucked behind the crane's control panel.","summary":"A busy waterfront where harbor workers gather beside the repair dock.","latitude":39.285,"longitude":-76.61,"extra_data":null,"place_type":"fixed_location","inhabitants":["Harbor workers"],"orrery_tags":null,"current_status":"The morning shift is gathering beside the damaged crane."}}}
```

Before:

```json
{
  "seed_type": null,
  "seed_title": null,
  "seed_situation": null,
  "seed_hook": null,
  "seed_immediate_goal": null,
  "seed_stakes": null,
  "seed_tension_source": null,
  "seed_starting_location": null,
  "seed_weather": null,
  "seed_key_npcs": null,
  "seed_initial_mystery": null,
  "seed_potential_allies": null,
  "seed_potential_obstacles": null,
  "seed_secrets": null,
  "layer_name": null,
  "layer_type": null,
  "layer_description": null,
  "zone_name": null,
  "zone_summary": null,
  "zone_boundary_description": null,
  "zone_approximate_area": null,
  "initial_location": null,
  "base_timestamp": null,
  "setting_confirmed": true,
  "character_confirmed": true
}
```
After:

```json
{
  "seed_type": "discovery",
  "seed_title": "The Harbor Bell",
  "seed_situation": "Mara finds a damaged harbor crane before the morning shift.",
  "seed_hook": "An unsigned warning links the damage to the planned yard closure.",
  "seed_immediate_goal": "Inspect the crane before the workers arrive.",
  "seed_stakes": "The workers' safety and the future of the repair yard.",
  "seed_tension_source": "The foreman wants the dock reopened immediately.",
  "seed_starting_location": null,
  "seed_weather": "Clear morning",
  "seed_key_npcs": [
    "The harbor foreman"
  ],
  "seed_initial_mystery": null,
  "seed_potential_allies": null,
  "seed_potential_obstacles": null,
  "seed_secrets": "The crane was disabled by someone trying to delay the closure.",
  "layer_name": "Earth",
  "layer_type": "planet",
  "layer_description": "The real Earth in the year 2024.",
  "zone_name": "Baltimore Harbor",
  "zone_summary": "Baltimore's working waterfront in Maryland.",
  "zone_boundary_description": null,
  "zone_approximate_area": null,
  "initial_location": {
    "name": "Baltimore Inner Harbor",
    "history": "The waterfront has supported generations of Baltimore workers.",
    "secrets": "A warning note is tucked behind the crane's control panel.",
    "summary": "A busy waterfront where harbor workers gather beside the repair dock.",
    "latitude": 39.285,
    "longitude": -76.61,
    "extra_data": null,
    "place_type": "fixed_location",
    "inhabitants": [
      "Harbor workers"
    ],
    "orrery_tags": null,
    "current_status": "The morning shift is gathering beside the damaged crane."
  },
  "base_timestamp": "2024-06-15 08:00:00+00:00",
  "setting_confirmed": true,
  "character_confirmed": true
}
```

### Pre-Edit Rejected Write (Red Regression)

Target: `qa640_840s3a_slot_2f737ccb5512`. Source: `qa640_840s3a_source_3aa216afa41d`.

`POST /api/story/new/chat` with `slot=4`, the fixture thread, `current_phase="seed"`, `message="Begin at the harbor."`. HTTP 200.

```json
{"message":"Generating artifact...","phase_complete":false,"subphase_complete":false,"phase":"seed","artifact_type":"submit_starting_scenario","data":{"seed":{"seed_type":"discovery","title":"The Harbor Bell","situation":"Mara finds a damaged harbor crane before the morning shift.","hook":"An unsigned warning links the damage to the planned yard closure.","immediate_goal":"Inspect the crane before the workers arrive.","stakes":"The workers' safety and the future of the repair yard.","tension_source":"The foreman wants the dock reopened immediately.","base_timestamp":{"year":2024,"month":6,"day":15,"hour":8,"minute":0,"second":0},"weather":"Clear morning","key_npcs":["The harbor foreman"],"secrets":"The crane was disabled by someone trying to delay the closure."},"location_sketch":"A place called Baltimore Inner Harbor in the Baltimore Harbor region of Earth. A busy waterfront where harbor workers gather beside the repair dock."},"location_sketch":"A place called Baltimore Inner Harbor in the Baltimore Harbor region of Earth. A busy waterfront where harbor workers gather beside the repair dock.","requires_set_design":true,"thread_id":"test_thread_d08cfd62ef024cdd","pending_confirmation":null,"artifact_token":"5bd027d4573b45ad0b5a82000dae090d1f2e9649872e2cc9206130972eb89db3","character_revision_pending":false,"set_design_error":"new row for relation \"new_story_creator\" violates check constraint \"qa840_reject_set_design\"\nDETAIL:  Failing row contains (t, test_thread_d08cfd62ef024cdd, 4, contemporary, {}, Earth, June 15, 2024, modern, f, null, Municipal government, Harbor workers face the closure of their repair yard., balanced, {duty,community}, Baltimore dockworkers keep their neighborhood connected., null, regional, Baltimore Harbor Notice, June 15, 2024: The repair yard opens at..., Mara, Veteran harbor engineer, Age 38. Repairs the harbor machinery and protects its workers., Gray coat, dark curls, and a grease-stained collar., discovery, The Harbor Bell, Mara finds a damaged harbor crane before the morning shift., An unsigned warning links the damage to the planned yard closure..., Inspect the crane before the workers arrive., The workers' safety and the future of the repair yard., The foreman wants the dock reopened immediately., null, Clear morning, {\"The harbor foreman\"}, null, null, null, The crane was disabled by someone trying to delay the closure., Earth, planet, The real Earth in the year 2024., Baltimore Harbor, Baltimore's working waterfront in Maryland., null, null, {\"name\": \"Baltimore Inner Harbor\", \"history\": \"The waterfront ha..., 2024-06-15 08:00:00+00, 2026-10-01 07:48:59.101761+00, t, null, null, null, t, t, f, null).\n"}
```

Before:

```json
{
  "seed_type": null,
  "seed_title": null,
  "seed_situation": null,
  "seed_hook": null,
  "seed_immediate_goal": null,
  "seed_stakes": null,
  "seed_tension_source": null,
  "seed_starting_location": null,
  "seed_weather": null,
  "seed_key_npcs": null,
  "seed_initial_mystery": null,
  "seed_potential_allies": null,
  "seed_potential_obstacles": null,
  "seed_secrets": null,
  "layer_name": null,
  "layer_type": null,
  "layer_description": null,
  "zone_name": null,
  "zone_summary": null,
  "zone_boundary_description": null,
  "zone_approximate_area": null,
  "initial_location": null,
  "base_timestamp": null,
  "setting_confirmed": true,
  "character_confirmed": true
}
```
After:

```json
{
  "seed_type": "discovery",
  "seed_title": "The Harbor Bell",
  "seed_situation": "Mara finds a damaged harbor crane before the morning shift.",
  "seed_hook": "An unsigned warning links the damage to the planned yard closure.",
  "seed_immediate_goal": "Inspect the crane before the workers arrive.",
  "seed_stakes": "The workers' safety and the future of the repair yard.",
  "seed_tension_source": "The foreman wants the dock reopened immediately.",
  "seed_starting_location": null,
  "seed_weather": "Clear morning",
  "seed_key_npcs": [
    "The harbor foreman"
  ],
  "seed_initial_mystery": null,
  "seed_potential_allies": null,
  "seed_potential_obstacles": null,
  "seed_secrets": "The crane was disabled by someone trying to delay the closure.",
  "layer_name": null,
  "layer_type": null,
  "layer_description": null,
  "zone_name": null,
  "zone_summary": null,
  "zone_boundary_description": null,
  "zone_approximate_area": null,
  "initial_location": null,
  "base_timestamp": "2024-06-15 08:00:00+00:00",
  "setting_confirmed": true,
  "character_confirmed": true
}
```

### Final Success

Target: `qa640_840s3a_slot_1aedc563c6de`. Source: `qa640_840s3a_source_0747808dcc5b`.

`POST /api/story/new/chat` with `slot=4`, the fixture thread, `current_phase="seed"`, `message="Begin at the harbor."`. HTTP 200.

```json
{"message":"Generating artifact...","phase_complete":true,"subphase_complete":false,"phase":"seed","artifact_type":"submit_starting_scenario","data":{"seed":{"seed_type":"discovery","title":"The Harbor Bell","situation":"Mara finds a damaged harbor crane before the morning shift.","hook":"An unsigned warning links the damage to the planned yard closure.","immediate_goal":"Inspect the crane before the workers arrive.","stakes":"The workers' safety and the future of the repair yard.","tension_source":"The foreman wants the dock reopened immediately.","base_timestamp":{"year":2024,"month":6,"day":15,"hour":8,"minute":0,"second":0},"weather":"Clear morning","key_npcs":["The harbor foreman"],"secrets":"The crane was disabled by someone trying to delay the closure."},"location_sketch":"A place called Baltimore Inner Harbor in the Baltimore Harbor region of Earth. A busy waterfront where harbor workers gather beside the repair dock."},"location_sketch":"A place called Baltimore Inner Harbor in the Baltimore Harbor region of Earth. A busy waterfront where harbor workers gather beside the repair dock.","requires_set_design":true,"thread_id":"test_thread_79e7e078f5a142f1","pending_confirmation":null,"artifact_token":"c5ef9ead7ba74dcd0019fc03e7af843963204517d04d79af319c0daacdbe9483","character_revision_pending":false,"set_design":{"layer":{"name":"Earth","type":"planet","description":"The real Earth in the year 2024."},"zone":{"name":"Baltimore Harbor","summary":"Baltimore's working waterfront in Maryland."},"location":{"name":"Baltimore Inner Harbor","history":"The waterfront has supported generations of Baltimore workers.","secrets":"A warning note is tucked behind the crane's control panel.","summary":"A busy waterfront where harbor workers gather beside the repair dock.","latitude":39.285,"longitude":-76.61,"extra_data":null,"place_type":"fixed_location","inhabitants":["Harbor workers"],"orrery_tags":null,"current_status":"The morning shift is gathering beside the damaged crane."}}}
```

Before:

```json
{
  "seed_type": null,
  "seed_title": null,
  "seed_situation": null,
  "seed_hook": null,
  "seed_immediate_goal": null,
  "seed_stakes": null,
  "seed_tension_source": null,
  "seed_starting_location": null,
  "seed_weather": null,
  "seed_key_npcs": null,
  "seed_initial_mystery": null,
  "seed_potential_allies": null,
  "seed_potential_obstacles": null,
  "seed_secrets": null,
  "layer_name": null,
  "layer_type": null,
  "layer_description": null,
  "zone_name": null,
  "zone_summary": null,
  "zone_boundary_description": null,
  "zone_approximate_area": null,
  "initial_location": null,
  "base_timestamp": null,
  "setting_confirmed": true,
  "character_confirmed": true
}
```
After:

```json
{
  "seed_type": "discovery",
  "seed_title": "The Harbor Bell",
  "seed_situation": "Mara finds a damaged harbor crane before the morning shift.",
  "seed_hook": "An unsigned warning links the damage to the planned yard closure.",
  "seed_immediate_goal": "Inspect the crane before the workers arrive.",
  "seed_stakes": "The workers' safety and the future of the repair yard.",
  "seed_tension_source": "The foreman wants the dock reopened immediately.",
  "seed_starting_location": null,
  "seed_weather": "Clear morning",
  "seed_key_npcs": [
    "The harbor foreman"
  ],
  "seed_initial_mystery": null,
  "seed_potential_allies": null,
  "seed_potential_obstacles": null,
  "seed_secrets": "The crane was disabled by someone trying to delay the closure.",
  "layer_name": "Earth",
  "layer_type": "planet",
  "layer_description": "The real Earth in the year 2024.",
  "zone_name": "Baltimore Harbor",
  "zone_summary": "Baltimore's working waterfront in Maryland.",
  "zone_boundary_description": null,
  "zone_approximate_area": null,
  "initial_location": {
    "name": "Baltimore Inner Harbor",
    "history": "The waterfront has supported generations of Baltimore workers.",
    "secrets": "A warning note is tucked behind the crane's control panel.",
    "summary": "A busy waterfront where harbor workers gather beside the repair dock.",
    "latitude": 39.285,
    "longitude": -76.61,
    "extra_data": null,
    "place_type": "fixed_location",
    "inhabitants": [
      "Harbor workers"
    ],
    "orrery_tags": null,
    "current_status": "The morning shift is gathering beside the damaged crane."
  },
  "base_timestamp": "2024-06-15 08:00:00+00:00",
  "setting_confirmed": true,
  "character_confirmed": true
}
```

### Final Rejected Write

Target: `qa640_840s3a_slot_a11547211bd0`. Source: `qa640_840s3a_source_af68d5e1cd7b`.

`POST /api/story/new/chat` with `slot=4`, the fixture thread, `current_phase="seed"`, `message="Begin at the harbor."`. HTTP 500.

```json
{"detail":"new row for relation \"new_story_creator\" violates check constraint \"qa840_reject_set_design\"\nDETAIL:  Failing row contains (t, test_thread_d92a973192a14976, 4, contemporary, {}, Earth, June 15, 2024, modern, f, null, Municipal government, Harbor workers face the closure of their repair yard., balanced, {duty,community}, Baltimore dockworkers keep their neighborhood connected., null, regional, Baltimore Harbor Notice, June 15, 2024: The repair yard opens at..., Mara, Veteran harbor engineer, Age 38. Repairs the harbor machinery and protects its workers., Gray coat, dark curls, and a grease-stained collar., discovery, The Harbor Bell, Mara finds a damaged harbor crane before the morning shift., An unsigned warning links the damage to the planned yard closure..., Inspect the crane before the workers arrive., The workers' safety and the future of the repair yard., The foreman wants the dock reopened immediately., null, Clear morning, {\"The harbor foreman\"}, null, null, null, The crane was disabled by someone trying to delay the closure., Earth, planet, The real Earth in the year 2024., Baltimore Harbor, Baltimore's working waterfront in Maryland., null, null, {\"name\": \"Baltimore Inner Harbor\", \"history\": \"The waterfront ha..., 2024-06-15 08:00:00+00, 2026-10-01 08:00:56.93923+00, t, null, null, null, t, t, f, null).\n"}
```

Before:

```json
{
  "seed_type": null,
  "seed_title": null,
  "seed_situation": null,
  "seed_hook": null,
  "seed_immediate_goal": null,
  "seed_stakes": null,
  "seed_tension_source": null,
  "seed_starting_location": null,
  "seed_weather": null,
  "seed_key_npcs": null,
  "seed_initial_mystery": null,
  "seed_potential_allies": null,
  "seed_potential_obstacles": null,
  "seed_secrets": null,
  "layer_name": null,
  "layer_type": null,
  "layer_description": null,
  "zone_name": null,
  "zone_summary": null,
  "zone_boundary_description": null,
  "zone_approximate_area": null,
  "initial_location": null,
  "base_timestamp": null,
  "setting_confirmed": true,
  "character_confirmed": true
}
```
After:

```json
{
  "seed_type": "discovery",
  "seed_title": "The Harbor Bell",
  "seed_situation": "Mara finds a damaged harbor crane before the morning shift.",
  "seed_hook": "An unsigned warning links the damage to the planned yard closure.",
  "seed_immediate_goal": "Inspect the crane before the workers arrive.",
  "seed_stakes": "The workers' safety and the future of the repair yard.",
  "seed_tension_source": "The foreman wants the dock reopened immediately.",
  "seed_starting_location": null,
  "seed_weather": "Clear morning",
  "seed_key_npcs": [
    "The harbor foreman"
  ],
  "seed_initial_mystery": null,
  "seed_potential_allies": null,
  "seed_potential_obstacles": null,
  "seed_secrets": "The crane was disabled by someone trying to delay the closure.",
  "layer_name": null,
  "layer_type": null,
  "layer_description": null,
  "zone_name": null,
  "zone_summary": null,
  "zone_boundary_description": null,
  "zone_approximate_area": null,
  "initial_location": null,
  "base_timestamp": "2024-06-15 08:00:00+00:00",
  "setting_confirmed": true,
  "character_confirmed": true
}
```

## Commands and Verbatim Tails

Every command ran from `/Users/pythagor/nexus/.claude/worktrees/840-set-designer-raises`.
Shell setup:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
export PYTHONPATH=$PWD
export TMPDIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/840-S3a/tmp
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/840-set-designer-raises/nexus/__init__.py
```

Pytest gates were wrapped with `perl -e 'alarm 570; exec @ARGV'` and stdout/stderr redirected to the named scratch log (the first preflight used `tee` with pipefail). Initial runs exported `PYTEST_ADDOPTS=--basetemp=<scratch>/<run>-tmp` with run names `preflight`, `preflight2`, `red`, `proof`, `offline1`. Later runs unset `PYTEST_ADDOPTS` with `env -u PYTEST_ADDOPTS`; TMPDIR alone controls their temp paths.

The first preflight failed in fixture setup, before starting servers or issuing HTTP: the target-only route rejected the source database used by the production cache writer. A temporary source route while seeding corrected fixture construction; no product code was edited until the second preflight passed. Exact initial error:

```text
ValueError: Invalid database name: 'qa640_840s3a_source_5608e3f34ced'. Must be one of: qa640_840s3a_slot_d13004dd8904
```

The first offline suite's one failure was invocation-induced, not a repository behavior failure: inherited `PYTEST_ADDOPTS=--basetemp=...` reached the prompt-lint test's child pytest whose cwd is inside that base. The full suite completed; the entire affected file then passed with that option unset. Both tails are retained; the original run is not represented as all-green.

Exact failed test: `tests/test_prompt_lint.py::test_review_injections_fail_the_gate_in_scratch_copy`.

```text
ERROR: usage: __main__.py [options] [file_or_dir] [file_or_dir] [...]
__main__.py: error: argument --basetemp: basetemp must not be empty, the current working directory or any parent directory of it (via PYTEST_ADDOPTS)
```

### Initial Fixture Setup

Log: `preflight.log`.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_set_designer_failure.py::test_successful_set_design_still_persists_and_returns_artifact
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_840s3a_slot_*, qa640_840s3a_source_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
ERROR tests/test_api/test_set_designer_failure.py::test_successful_set_design_still_persists_and_returns_artifact[/api/story/new/chat]
5 warnings, 1 error in 3.03s
```

### Required Pre-Edit Success

Log: `preflight2.log`.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_set_designer_failure.py::test_successful_set_design_still_persists_and_returns_artifact
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_840s3a_slot_*, qa640_840s3a_source_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed, 7 warnings in 6.62s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Red Regression

Log: `red.log`.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_set_designer_failure.py::test_chat_set_design_write_failure_returns_500_without_design_draft tests/test_api/test_set_designer_failure.py::test_neither_provider_branch_swallows_set_design_errors
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_840s3a_slot_*, qa640_840s3a_source_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_set_designer_failure.py::test_chat_set_design_write_failure_returns_500_without_design_draft
FAILED tests/test_api/test_set_designer_failure.py::test_neither_provider_branch_swallows_set_design_errors
2 failed, 7 warnings in 5.90s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Initial Focused Proof

Log: `proof.log`.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_set_designer_failure.py tests/test_api/test_wizard_confirmation_pg.py tests/test_api/test_wizard_stream_conflicts.py tests/test_owner_target_guard.py tests/test_pg_disposable_target.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 22 targets: postgres, qa640_840s3a_slot_* x2, qa640_840s3a_source_* x2, qa640_offline_gate_* x16, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
163 passed, 7 warnings in 37.94s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Offline Suite One

Log: `offline1.log`.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_prompt_lint.py::test_review_injections_fail_the_gate_in_scratch_copy
1 failed, 2731 passed, 457 skipped, 8 warnings in 439.37s (0:07:19)
```

### Prompt-Lint Invocation Correction

Log: `prompt-rerun.log`.

```sh
env -u PYTEST_ADDOPTS -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT $PY -m pytest -q tests/test_prompt_lint.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
22 passed, 5 warnings in 13.17s
```

### Offline Suite Two

Log: `offline2.log`.

```sh
env -u PYTEST_ADDOPTS -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT $PY -m pytest -q tests/test_api tests/test_orrery
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1830 passed, 748 skipped, 7 warnings in 39.27s
```

### Reachability

Log: `reachability.log`.

```sh
$PY -m pytest -q tests/test_reachability.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.74s
```

### Final Focused Proof

Log: `proof-final.log`.

```sh
env -u PYTEST_ADDOPTS -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_set_designer_failure.py tests/test_api/test_wizard_confirmation_pg.py tests/test_api/test_wizard_stream_conflicts.py tests/test_owner_target_guard.py tests/test_pg_disposable_target.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 22 targets: postgres, qa640_840s3a_slot_* x2, qa640_840s3a_source_* x2, qa640_offline_gate_* x16, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
163 passed, 7 warnings in 41.52s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Black

Log: `black-final.log`.

```sh
$PY -m black --check nexus/api/wizard_chat.py tests/test_api/test_set_designer_failure.py
```

```text
All done! ✨ 🍰 ✨
2 files would be left unchanged.
```

### Flake8

Log: `flake8-final.log`.

```sh
$PY -m flake8 nexus/api/wizard_chat.py tests/test_api/test_set_designer_failure.py
```

```text
nexus/api/wizard_chat.py:25:1: F401 'nexus.api.config_utils.get_new_story_model' imported but unused
nexus/api/wizard_chat.py:95:89: E501 line too long (136 > 88 characters)
nexus/api/wizard_chat.py:378:89: E501 line too long (108 > 88 characters)
nexus/api/wizard_chat.py:398:89: E501 line too long (101 > 88 characters)
nexus/api/wizard_chat.py:403:89: E501 line too long (92 > 88 characters)
nexus/api/wizard_chat.py:418:89: E501 line too long (93 > 88 characters)
nexus/api/wizard_chat.py:486:89: E501 line too long (100 > 88 characters)
nexus/api/wizard_chat.py:490:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:522:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:569:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:867:89: E501 line too long (90 > 88 characters)
nexus/api/wizard_chat.py:876:89: E501 line too long (97 > 88 characters)
nexus/api/wizard_chat.py:895:89: E501 line too long (89 > 88 characters)
nexus/api/wizard_chat.py:904:89: E501 line too long (92 > 88 characters)
nexus/api/wizard_chat.py:1319:89: E501 line too long (94 > 88 characters)
nexus/api/wizard_chat.py:1404:89: E501 line too long (91 > 88 characters)
```

### Mypy

Log: `mypy-final.log`.

```sh
$PY -m mypy nexus/api/wizard_chat.py tests/test_api/test_set_designer_failure.py
```

```text
nexus/api/wizard_chat.py:19: error: Skipping analyzing "frontmatter": module is installed, but missing library stubs or py.typed marker  [import-untyped]
nexus/api/wizard_chat.py:19: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
nexus/api/wizard_chat.py:312: error: No overload variant of "run" of "AbstractAgent" matches argument types "str", "WizardContext", "list[Any]", "Any", "ModelSettings"  [call-overload]
nexus/api/wizard_chat.py:312: note: Possible overload variants:
nexus/api/wizard_chat.py:312: note:     def run(self, user_prompt: str | Sequence[str | ImageUrl | AudioUrl | DocumentUrl | VideoUrl | BinaryContent | CachePoint] | None = ..., *, output_type: None = ..., message_history: Sequence[ModelRequest | ModelResponse] | None = ..., deferred_tool_results: DeferredToolResults | None = ..., model: Literal['anthropic:claude-3-5-haiku-20241022', 'anthropic:claude-3-5-haiku-latest', 'anthropic:claude-3-7-sonnet-20250219', 'anthropic:claude-3-7-sonnet-latest', 'anthropic:claude-3-haiku-20240307', 'anthropic:claude-3-opus-20240229', 'anthropic:claude-3-opus-latest', 'anthropic:claude-4-opus-20250514', 'anthropic:claude-4-sonnet-20250514', 'anthropic:claude-haiku-4-5', 'anthropic:claude-haiku-4-5-20251001', 'anthropic:claude-opus-4-0', 'anthropic:claude-opus-4-1-20250805', 'anthropic:claude-opus-4-20250514', 'anthropic:claude-opus-4-5', 'anthropic:claude-opus-4-5-20251101', 'anthropic:claude-sonnet-4-0', 'anthropic:claude-sonnet-4-20250514', 'anthropic:claude-sonnet-4-5', 'anthropic:claude-sonnet-4-5-20250929', 'bedrock:amazon.titan-text-express-v1', 'bedrock:amazon.titan-text-lite-v1', 'bedrock:amazon.titan-tg1-large', 'bedrock:anthropic.claude-3-5-haiku-20241022-v1:0', 'bedrock:anthropic.claude-3-5-sonnet-20240620-v1:0', 'bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0', 'bedrock:anthropic.claude-3-7-sonnet-20250219-v1:0', 'bedrock:anthropic.claude-3-haiku-20240307-v1:0', 'bedrock:anthropic.claude-3-opus-20240229-v1:0', 'bedrock:anthropic.claude-3-sonnet-20240229-v1:0', 'bedrock:anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:anthropic.claude-instant-v1', 'bedrock:anthropic.claude-opus-4-20250514-v1:0', 'bedrock:anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:anthropic.claude-v2', 'bedrock:anthropic.claude-v2:1', 'bedrock:cohere.command-light-text-v14', 'bedrock:cohere.command-r-plus-v1:0', 'bedrock:cohere.command-r-v1:0', 'bedrock:cohere.command-text-v14', 'bedrock:eu.anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:eu.anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:global.anthropic.claude-opus-4-5-20251101-v1:0', 'bedrock:meta.llama3-1-405b-instruct-v1:0', 'bedrock:meta.llama3-1-70b-instruct-v1:0', 'bedrock:meta.llama3-1-8b-instruct-v1:0', 'bedrock:meta.llama3-70b-instruct-v1:0', 'bedrock:meta.llama3-8b-instruct-v1:0', 'bedrock:mistral.mistral-7b-instruct-v0:2', 'bedrock:mistral.mistral-large-2402-v1:0', 'bedrock:mistral.mistral-large-2407-v1:0', 'bedrock:mistral.mixtral-8x7b-instruct-v0:1', 'bedrock:us.amazon.nova-lite-v1:0', 'bedrock:us.amazon.nova-micro-v1:0', 'bedrock:us.amazon.nova-pro-v1:0', 'bedrock:us.anthropic.claude-3-5-haiku-20241022-v1:0', 'bedrock:us.anthropic.claude-3-5-sonnet-20240620-v1:0', 'bedrock:us.anthropic.claude-3-5-sonnet-20241022-v2:0', 'bedrock:us.anthropic.claude-3-7-sonnet-20250219-v1:0', 'bedrock:us.anthropic.claude-3-haiku-20240307-v1:0', 'bedrock:us.anthropic.claude-3-opus-20240229-v1:0', 'bedrock:us.anthropic.claude-3-sonnet-20240229-v1:0', 'bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:us.anthropic.claude-opus-4-20250514-v1:0', 'bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:us.meta.llama3-1-70b-instruct-v1:0', 'bedrock:us.meta.llama3-1-8b-instruct-v1:0', 'bedrock:us.meta.llama3-2-11b-instruct-v1:0', 'bedrock:us.meta.llama3-2-1b-instruct-v1:0', 'bedrock:us.meta.llama3-2-3b-instruct-v1:0', 'bedrock:us.meta.llama3-2-90b-instruct-v1:0', 'bedrock:us.meta.llama3-3-70b-instruct-v1:0', 'cerebras:gpt-oss-120b', 'cerebras:llama-3.3-70b', 'cerebras:llama3.1-8b', 'cerebras:qwen-3-235b-a22b-instruct-2507', 'cerebras:qwen-3-32b', 'cerebras:zai-glm-4.6', 'cohere:c4ai-aya-expanse-32b', 'cohere:c4ai-aya-expanse-8b', 'cohere:command-nightly', 'cohere:command-r-08-2024', 'cohere:command-r-plus-08-2024', 'cohere:command-r7b-12-2024', 'deepseek:deepseek-chat', 'deepseek:deepseek-reasoner', 'gateway/anthropic:claude-3-5-haiku-20241022', 'gateway/anthropic:claude-3-5-haiku-latest', 'gateway/anthropic:claude-3-7-sonnet-20250219', 'gateway/anthropic:claude-3-7-sonnet-latest', 'gateway/anthropic:claude-3-haiku-20240307', 'gateway/anthropic:claude-3-opus-20240229', 'gateway/anthropic:claude-3-opus-latest', 'gateway/anthropic:claude-4-opus-20250514', 'gateway/anthropic:claude-4-sonnet-20250514', 'gateway/anthropic:claude-haiku-4-5', 'gateway/anthropic:claude-haiku-4-5-20251001', 'gateway/anthropic:claude-opus-4-0', 'gateway/anthropic:claude-opus-4-1-20250805', 'gateway/anthropic:claude-opus-4-20250514', 'gateway/anthropic:claude-opus-4-5', 'gateway/anthropic:claude-opus-4-5-20251101', 'gateway/anthropic:claude-sonnet-4-0', 'gateway/anthropic:claude-sonnet-4-20250514', 'gateway/anthropic:claude-sonnet-4-5', 'gateway/anthropic:claude-sonnet-4-5-20250929', 'gateway/bedrock:amazon.titan-text-express-v1', 'gateway/bedrock:amazon.titan-text-lite-v1', 'gateway/bedrock:amazon.titan-tg1-large', 'gateway/bedrock:anthropic.claude-3-5-haiku-20241022-v1:0', 'gateway/bedrock:anthropic.claude-3-5-sonnet-20240620-v1:0', 'gateway/bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0', 'gateway/bedrock:anthropic.claude-3-7-sonnet-20250219-v1:0', 'gateway/bedrock:anthropic.claude-3-haiku-20240307-v1:0', 'gateway/bedrock:anthropic.claude-3-opus-20240229-v1:0', 'gateway/bedrock:anthropic.claude-3-sonnet-20240229-v1:0', 'gateway/bedrock:anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:anthropic.claude-instant-v1', 'gateway/bedrock:anthropic.claude-opus-4-20250514-v1:0', 'gateway/bedrock:anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:anthropic.claude-v2', 'gateway/bedrock:anthropic.claude-v2:1', 'gateway/bedrock:cohere.command-light-text-v14', 'gateway/bedrock:cohere.command-r-plus-v1:0', 'gateway/bedrock:cohere.command-r-v1:0', 'gateway/bedrock:cohere.command-text-v14', 'gateway/bedrock:eu.anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:eu.anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:global.anthropic.claude-opus-4-5-20251101-v1:0', 'gateway/bedrock:meta.llama3-1-405b-instruct-v1:0', 'gateway/bedrock:meta.llama3-1-70b-instruct-v1:0', 'gateway/bedrock:meta.llama3-1-8b-instruct-v1:0', 'gateway/bedrock:meta.llama3-70b-instruct-v1:0', 'gateway/bedrock:meta.llama3-8b-instruct-v1:0', 'gateway/bedrock:mistral.mistral-7b-instruct-v0:2', 'gateway/bedrock:mistral.mistral-large-2402-v1:0', 'gateway/bedrock:mistral.mistral-large-2407-v1:0', 'gateway/bedrock:mistral.mixtral-8x7b-instruct-v0:1', 'gateway/bedrock:us.amazon.nova-lite-v1:0', 'gateway/bedrock:us.amazon.nova-micro-v1:0', 'gateway/bedrock:us.amazon.nova-pro-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-haiku-20241022-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-sonnet-20240620-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-sonnet-20241022-v2:0', 'gateway/bedrock:us.anthropic.claude-3-7-sonnet-20250219-v1:0', 'gateway/bedrock:us.anthropic.claude-3-haiku-20240307-v1:0', 'gateway/bedrock:us.anthropic.claude-3-opus-20240229-v1:0', 'gateway/bedrock:us.anthropic.claude-3-sonnet-20240229-v1:0', 'gateway/bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:us.anthropic.claude-opus-4-20250514-v1:0', 'gateway/bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:us.meta.llama3-1-70b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-1-8b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-11b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-1b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-3b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-90b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-3-70b-instruct-v1:0', 'gateway/google-vertex:gemini-2.0-flash', 'gateway/google-vertex:gemini-2.0-flash-lite', 'gateway/google-vertex:gemini-2.5-flash', 'gateway/google-vertex:gemini-2.5-flash-image', 'gateway/google-vertex:gemini-2.5-flash-lite', 'gateway/google-vertex:gemini-2.5-flash-lite-preview-09-2025', 'gateway/google-vertex:gemini-2.5-flash-preview-09-2025', 'gateway/google-vertex:gemini-2.5-pro', 'gateway/google-vertex:gemini-3-pro-image-preview', 'gateway/google-vertex:gemini-3-pro-preview', 'gateway/google-vertex:gemini-flash-latest', 'gateway/google-vertex:gemini-flash-lite-latest', 'gateway/groq:deepseek-r1-distill-llama-70b', 'gateway/groq:deepseek-r1-distill-qwen-32b', 'gateway/groq:distil-whisper-large-v3-en', 'gateway/groq:gemma2-9b-it', 'gateway/groq:llama-3.1-8b-instant', 'gateway/groq:llama-3.2-11b-vision-preview', 'gateway/groq:llama-3.2-1b-preview', 'gateway/groq:llama-3.2-3b-preview', 'gateway/groq:llama-3.2-90b-vision-preview', 'gateway/groq:llama-3.3-70b-specdec', 'gateway/groq:llama-3.3-70b-versatile', 'gateway/groq:llama-guard-3-8b', 'gateway/groq:llama3-70b-8192', 'gateway/groq:llama3-8b-8192', 'gateway/groq:mistral-saba-24b', 'gateway/groq:moonshotai/kimi-k2-instruct', 'gateway/groq:playai-tts', 'gateway/groq:playai-tts-arabic', 'gateway/groq:qwen-2.5-32b', 'gateway/groq:qwen-2.5-coder-32b', 'gateway/groq:qwen-qwq-32b', 'gateway/groq:whisper-large-v3', 'gateway/groq:whisper-large-v3-turbo', 'gateway/openai:chatgpt-4o-latest', 'gateway/openai:codex-mini-latest', 'gateway/openai:computer-use-preview', 'gateway/openai:computer-use-preview-2025-03-11', 'gateway/openai:gpt-3.5-turbo', 'gateway/openai:gpt-3.5-turbo-0125', 'gateway/openai:gpt-3.5-turbo-0301', 'gateway/openai:gpt-3.5-turbo-0613', 'gateway/openai:gpt-3.5-turbo-1106', 'gateway/openai:gpt-3.5-turbo-16k', 'gateway/openai:gpt-3.5-turbo-16k-0613', 'gateway/openai:gpt-4', 'gateway/openai:gpt-4-0125-preview', 'gateway/openai:gpt-4-0314', 'gateway/openai:gpt-4-0613', 'gateway/openai:gpt-4-1106-preview', 'gateway/openai:gpt-4-32k', 'gateway/openai:gpt-4-32k-0314', 'gateway/openai:gpt-4-32k-0613', 'gateway/openai:gpt-4-turbo', 'gateway/openai:gpt-4-turbo-2024-04-09', 'gateway/openai:gpt-4-turbo-preview', 'gateway/openai:gpt-4-vision-preview', 'gateway/openai:gpt-4.1', 'gateway/openai:gpt-4.1-2025-04-14', 'gateway/openai:gpt-4.1-mini', 'gateway/openai:gpt-4.1-mini-2025-04-14', 'gateway/openai:gpt-4.1-nano', 'gateway/openai:gpt-4.1-nano-2025-04-14', 'gateway/openai:gpt-4o', 'gateway/openai:gpt-4o-2024-05-13', 'gateway/openai:gpt-4o-2024-08-06', 'gateway/openai:gpt-4o-2024-11-20', 'gateway/openai:gpt-4o-audio-preview', 'gateway/openai:gpt-4o-audio-preview-2024-10-01', 'gateway/openai:gpt-4o-audio-preview-2024-12-17', 'gateway/openai:gpt-4o-audio-preview-2025-06-03', 'gateway/openai:gpt-4o-mini', 'gateway/openai:gpt-4o-mini-2024-07-18', 'gateway/openai:gpt-4o-mini-audio-preview', 'gateway/openai:gpt-4o-mini-audio-preview-2024-12-17', 'gateway/openai:gpt-4o-mini-search-preview', 'gateway/openai:gpt-4o-mini-search-preview-2025-03-11', 'gateway/openai:gpt-4o-search-preview', 'gateway/openai:gpt-4o-search-preview-2025-03-11', 'gateway/openai:gpt-5', 'gateway/openai:gpt-5-2025-08-07', 'gateway/openai:gpt-5-chat-latest', 'gateway/openai:gpt-5-codex', 'gateway/openai:gpt-5-mini', 'gateway/openai:gpt-5-mini-2025-08-07', 'gateway/openai:gpt-5-nano', 'gateway/openai:gpt-5-nano-2025-08-07', 'gateway/openai:gpt-5-pro', 'gateway/openai:gpt-5-pro-2025-10-06', 'gateway/openai:gpt-5.1', 'gateway/openai:gpt-5.1-2025-11-13', 'gateway/openai:gpt-5.1-chat-latest', 'gateway/openai:gpt-5.1-codex', 'gateway/openai:gpt-5.1-mini', 'gateway/openai:o1', 'gateway/openai:o1-2024-12-17', 'gateway/openai:o1-mini', 'gateway/openai:o1-mini-2024-09-12', 'gateway/openai:o1-preview', 'gateway/openai:o1-preview-2024-09-12', 'gateway/openai:o1-pro', 'gateway/openai:o1-pro-2025-03-19', 'gateway/openai:o3', 'gateway/openai:o3-2025-04-16', 'gateway/openai:o3-deep-research', 'gateway/openai:o3-deep-research-2025-06-26', 'gateway/openai:o3-mini', 'gateway/openai:o3-mini-2025-01-31', 'gateway/openai:o3-pro', 'gateway/openai:o3-pro-2025-06-10', 'gateway/openai:o4-mini', 'gateway/openai:o4-mini-2025-04-16', 'gateway/openai:o4-mini-deep-research', 'gateway/openai:o4-mini-deep-research-2025-06-26', 'google-gla:gemini-flash-latest', 'google-gla:gemini-flash-lite-latest', 'google-gla:gemini-2.0-flash', 'google-gla:gemini-2.0-flash-lite', 'google-gla:gemini-2.5-flash', 'google-gla:gemini-2.5-flash-preview-09-2025', 'google-gla:gemini-2.5-flash-image', 'google-gla:gemini-2.5-flash-lite', 'google-gla:gemini-2.5-flash-lite-preview-09-2025', 'google-gla:gemini-2.5-pro', 'google-gla:gemini-3-pro-preview', 'google-gla:gemini-3-pro-image-preview', 'google-vertex:gemini-flash-latest', 'google-vertex:gemini-flash-lite-latest', 'google-vertex:gemini-2.0-flash', 'google-vertex:gemini-2.0-flash-lite', 'google-vertex:gemini-2.5-flash', 'google-vertex:gemini-2.5-flash-preview-09-2025', 'google-vertex:gemini-2.5-flash-image', 'google-vertex:gemini-2.5-flash-lite', 'google-vertex:gemini-2.5-flash-lite-preview-09-2025', 'google-vertex:gemini-2.5-pro', 'google-vertex:gemini-3-pro-preview', 'google-vertex:gemini-3-pro-image-preview', 'grok:grok-2-image-1212', 'grok:grok-2-vision-1212', 'grok:grok-3', 'grok:grok-3-fast', 'grok:grok-3-mini', 'grok:grok-3-mini-fast', 'grok:grok-4', 'grok:grok-4-0709', 'grok:grok-4-fast', 'grok:grok-4-fast-reasoning', 'grok:grok-4-fast-non-reasoning', 'grok:grok-code-fast-1', 'grok:grok-4-1-fast', 'grok:grok-4-1-fast-reasoning', 'grok:grok-4-1-fast-non-reasoning', 'groq:deepseek-r1-distill-llama-70b', 'groq:deepseek-r1-distill-qwen-32b', 'groq:distil-whisper-large-v3-en', 'groq:gemma2-9b-it', 'groq:llama-3.1-8b-instant', 'groq:llama-3.2-11b-vision-preview', 'groq:llama-3.2-1b-preview', 'groq:llama-3.2-3b-preview', 'groq:llama-3.2-90b-vision-preview', 'groq:llama-3.3-70b-specdec', 'groq:llama-3.3-70b-versatile', 'groq:llama-guard-3-8b', 'groq:llama3-70b-8192', 'groq:llama3-8b-8192', 'groq:mistral-saba-24b', 'groq:moonshotai/kimi-k2-instruct', 'groq:playai-tts', 'groq:playai-tts-arabic', 'groq:qwen-2.5-32b', 'groq:qwen-2.5-coder-32b', 'groq:qwen-qwq-32b', 'groq:whisper-large-v3', 'groq:whisper-large-v3-turbo', 'heroku:amazon-rerank-1-0', 'heroku:claude-3-5-haiku', 'heroku:claude-3-5-sonnet-latest', 'heroku:claude-3-7-sonnet', 'heroku:claude-3-haiku', 'heroku:claude-4-5-haiku', 'heroku:claude-4-5-sonnet', 'heroku:claude-4-sonnet', 'heroku:cohere-rerank-3-5', 'heroku:gpt-oss-120b', 'heroku:nova-lite', 'heroku:nova-pro', 'huggingface:Qwen/QwQ-32B', 'huggingface:Qwen/Qwen2.5-72B-Instruct', 'huggingface:Qwen/Qwen3-235B-A22B', 'huggingface:Qwen/Qwen3-32B', 'huggingface:deepseek-ai/DeepSeek-R1', 'huggingface:meta-llama/Llama-3.3-70B-Instruct', 'huggingface:meta-llama/Llama-4-Maverick-17B-128E-Instruct', 'huggingface:meta-llama/Llama-4-Scout-17B-16E-Instruct', 'mistral:codestral-latest', 'mistral:mistral-large-latest', 'mistral:mistral-moderation-latest', 'mistral:mistral-small-latest', 'moonshotai:kimi-k2-0711-preview', 'moonshotai:kimi-latest', 'moonshotai:kimi-thinking-preview', 'moonshotai:moonshot-v1-128k', 'moonshotai:moonshot-v1-128k-vision-preview', 'moonshotai:moonshot-v1-32k', 'moonshotai:moonshot-v1-32k-vision-preview', 'moonshotai:moonshot-v1-8k', 'moonshotai:moonshot-v1-8k-vision-preview', 'openai:chatgpt-4o-latest', 'openai:codex-mini-latest', 'openai:computer-use-preview', 'openai:computer-use-preview-2025-03-11', 'openai:gpt-3.5-turbo', 'openai:gpt-3.5-turbo-0125', 'openai:gpt-3.5-turbo-0301', 'openai:gpt-3.5-turbo-0613', 'openai:gpt-3.5-turbo-1106', 'openai:gpt-3.5-turbo-16k', 'openai:gpt-3.5-turbo-16k-0613', 'openai:gpt-4', 'openai:gpt-4-0125-preview', 'openai:gpt-4-0314', 'openai:gpt-4-0613', 'openai:gpt-4-1106-preview', 'openai:gpt-4-32k', 'openai:gpt-4-32k-0314', 'openai:gpt-4-32k-0613', 'openai:gpt-4-turbo', 'openai:gpt-4-turbo-2024-04-09', 'openai:gpt-4-turbo-preview', 'openai:gpt-4-vision-preview', 'openai:gpt-4.1', 'openai:gpt-4.1-2025-04-14', 'openai:gpt-4.1-mini', 'openai:gpt-4.1-mini-2025-04-14', 'openai:gpt-4.1-nano', 'openai:gpt-4.1-nano-2025-04-14', 'openai:gpt-4o', 'openai:gpt-4o-2024-05-13', 'openai:gpt-4o-2024-08-06', 'openai:gpt-4o-2024-11-20', 'openai:gpt-4o-audio-preview', 'openai:gpt-4o-audio-preview-2024-10-01', 'openai:gpt-4o-audio-preview-2024-12-17', 'openai:gpt-4o-audio-preview-2025-06-03', 'openai:gpt-4o-mini', 'openai:gpt-4o-mini-2024-07-18', 'openai:gpt-4o-mini-audio-preview', 'openai:gpt-4o-mini-audio-preview-2024-12-17', 'openai:gpt-4o-mini-search-preview', 'openai:gpt-4o-mini-search-preview-2025-03-11', 'openai:gpt-4o-search-preview', 'openai:gpt-4o-search-preview-2025-03-11', 'openai:gpt-5', 'openai:gpt-5-2025-08-07', 'openai:gpt-5-chat-latest', 'openai:gpt-5-codex', 'openai:gpt-5-mini', 'openai:gpt-5-mini-2025-08-07', 'openai:gpt-5-nano', 'openai:gpt-5-nano-2025-08-07', 'openai:gpt-5-pro', 'openai:gpt-5-pro-2025-10-06', 'openai:gpt-5.1', 'openai:gpt-5.1-2025-11-13', 'openai:gpt-5.1-chat-latest', 'openai:gpt-5.1-codex', 'openai:gpt-5.1-mini', 'openai:o1', 'openai:o1-2024-12-17', 'openai:o1-mini', 'openai:o1-mini-2024-09-12', 'openai:o1-preview', 'openai:o1-preview-2024-09-12', 'openai:o1-pro', 'openai:o1-pro-2025-03-19', 'openai:o3', 'openai:o3-2025-04-16', 'openai:o3-deep-research', 'openai:o3-deep-research-2025-06-26', 'openai:o3-mini', 'openai:o3-mini-2025-01-31', 'openai:o3-pro', 'openai:o3-pro-2025-06-10', 'openai:o4-mini', 'openai:o4-mini-2025-04-16', 'openai:o4-mini-deep-research', 'openai:o4-mini-deep-research-2025-06-26', 'test'] | Model | str | None = ..., instructions: str | Callable[[RunContext[None]], str] | Callable[[RunContext[None]], Awaitable[str]] | Callable[[], str] | Callable[[], Awaitable[str]] | Sequence[str | Callable[[RunContext[None]], str] | Callable[[RunContext[None]], Awaitable[str]] | Callable[[], str] | Callable[[], Awaitable[str]]] | None = ..., deps: None = ..., model_settings: ModelSettings | None = ..., usage_limits: UsageLimits | None = ..., usage: RunUsage | None = ..., infer_name: bool = ..., toolsets: Sequence[AbstractToolset[None]] | None = ..., builtin_tools: Sequence[AbstractBuiltinTool | Callable[[RunContext[None]], Awaitable[AbstractBuiltinTool | None] | AbstractBuiltinTool | None]] | None = ..., event_stream_handler: Callable[[RunContext[None], AsyncIterable[PartStartEvent | PartDeltaEvent | PartEndEvent | FinalResultEvent | FunctionToolCallEvent | FunctionToolResultEvent | BuiltinToolCallEvent | BuiltinToolResultEvent]], Awaitable[None]] | None = ...) -> Coroutine[Any, Any, AgentRunResult[str]]
nexus/api/wizard_chat.py:312: note:     def [RunOutputDataT] run(self, user_prompt: str | Sequence[str | ImageUrl | AudioUrl | DocumentUrl | VideoUrl | BinaryContent | CachePoint] | None = ..., *, output_type: type[RunOutputDataT] | Callable[..., Awaitable[RunOutputDataT] | RunOutputDataT] | ToolOutput[RunOutputDataT] | NativeOutput[RunOutputDataT] | PromptedOutput[RunOutputDataT] | TextOutput[RunOutputDataT] | Sequence[Any], message_history: Sequence[ModelRequest | ModelResponse] | None = ..., deferred_tool_results: DeferredToolResults | None = ..., model: Literal['anthropic:claude-3-5-haiku-20241022', 'anthropic:claude-3-5-haiku-latest', 'anthropic:claude-3-7-sonnet-20250219', 'anthropic:claude-3-7-sonnet-latest', 'anthropic:claude-3-haiku-20240307', 'anthropic:claude-3-opus-20240229', 'anthropic:claude-3-opus-latest', 'anthropic:claude-4-opus-20250514', 'anthropic:claude-4-sonnet-20250514', 'anthropic:claude-haiku-4-5', 'anthropic:claude-haiku-4-5-20251001', 'anthropic:claude-opus-4-0', 'anthropic:claude-opus-4-1-20250805', 'anthropic:claude-opus-4-20250514', 'anthropic:claude-opus-4-5', 'anthropic:claude-opus-4-5-20251101', 'anthropic:claude-sonnet-4-0', 'anthropic:claude-sonnet-4-20250514', 'anthropic:claude-sonnet-4-5', 'anthropic:claude-sonnet-4-5-20250929', 'bedrock:amazon.titan-text-express-v1', 'bedrock:amazon.titan-text-lite-v1', 'bedrock:amazon.titan-tg1-large', 'bedrock:anthropic.claude-3-5-haiku-20241022-v1:0', 'bedrock:anthropic.claude-3-5-sonnet-20240620-v1:0', 'bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0', 'bedrock:anthropic.claude-3-7-sonnet-20250219-v1:0', 'bedrock:anthropic.claude-3-haiku-20240307-v1:0', 'bedrock:anthropic.claude-3-opus-20240229-v1:0', 'bedrock:anthropic.claude-3-sonnet-20240229-v1:0', 'bedrock:anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:anthropic.claude-instant-v1', 'bedrock:anthropic.claude-opus-4-20250514-v1:0', 'bedrock:anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:anthropic.claude-v2', 'bedrock:anthropic.claude-v2:1', 'bedrock:cohere.command-light-text-v14', 'bedrock:cohere.command-r-plus-v1:0', 'bedrock:cohere.command-r-v1:0', 'bedrock:cohere.command-text-v14', 'bedrock:eu.anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:eu.anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:global.anthropic.claude-opus-4-5-20251101-v1:0', 'bedrock:meta.llama3-1-405b-instruct-v1:0', 'bedrock:meta.llama3-1-70b-instruct-v1:0', 'bedrock:meta.llama3-1-8b-instruct-v1:0', 'bedrock:meta.llama3-70b-instruct-v1:0', 'bedrock:meta.llama3-8b-instruct-v1:0', 'bedrock:mistral.mistral-7b-instruct-v0:2', 'bedrock:mistral.mistral-large-2402-v1:0', 'bedrock:mistral.mistral-large-2407-v1:0', 'bedrock:mistral.mixtral-8x7b-instruct-v0:1', 'bedrock:us.amazon.nova-lite-v1:0', 'bedrock:us.amazon.nova-micro-v1:0', 'bedrock:us.amazon.nova-pro-v1:0', 'bedrock:us.anthropic.claude-3-5-haiku-20241022-v1:0', 'bedrock:us.anthropic.claude-3-5-sonnet-20240620-v1:0', 'bedrock:us.anthropic.claude-3-5-sonnet-20241022-v2:0', 'bedrock:us.anthropic.claude-3-7-sonnet-20250219-v1:0', 'bedrock:us.anthropic.claude-3-haiku-20240307-v1:0', 'bedrock:us.anthropic.claude-3-opus-20240229-v1:0', 'bedrock:us.anthropic.claude-3-sonnet-20240229-v1:0', 'bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:us.anthropic.claude-opus-4-20250514-v1:0', 'bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:us.meta.llama3-1-70b-instruct-v1:0', 'bedrock:us.meta.llama3-1-8b-instruct-v1:0', 'bedrock:us.meta.llama3-2-11b-instruct-v1:0', 'bedrock:us.meta.llama3-2-1b-instruct-v1:0', 'bedrock:us.meta.llama3-2-3b-instruct-v1:0', 'bedrock:us.meta.llama3-2-90b-instruct-v1:0', 'bedrock:us.meta.llama3-3-70b-instruct-v1:0', 'cerebras:gpt-oss-120b', 'cerebras:llama-3.3-70b', 'cerebras:llama3.1-8b', 'cerebras:qwen-3-235b-a22b-instruct-2507', 'cerebras:qwen-3-32b', 'cerebras:zai-glm-4.6', 'cohere:c4ai-aya-expanse-32b', 'cohere:c4ai-aya-expanse-8b', 'cohere:command-nightly', 'cohere:command-r-08-2024', 'cohere:command-r-plus-08-2024', 'cohere:command-r7b-12-2024', 'deepseek:deepseek-chat', 'deepseek:deepseek-reasoner', 'gateway/anthropic:claude-3-5-haiku-20241022', 'gateway/anthropic:claude-3-5-haiku-latest', 'gateway/anthropic:claude-3-7-sonnet-20250219', 'gateway/anthropic:claude-3-7-sonnet-latest', 'gateway/anthropic:claude-3-haiku-20240307', 'gateway/anthropic:claude-3-opus-20240229', 'gateway/anthropic:claude-3-opus-latest', 'gateway/anthropic:claude-4-opus-20250514', 'gateway/anthropic:claude-4-sonnet-20250514', 'gateway/anthropic:claude-haiku-4-5', 'gateway/anthropic:claude-haiku-4-5-20251001', 'gateway/anthropic:claude-opus-4-0', 'gateway/anthropic:claude-opus-4-1-20250805', 'gateway/anthropic:claude-opus-4-20250514', 'gateway/anthropic:claude-opus-4-5', 'gateway/anthropic:claude-opus-4-5-20251101', 'gateway/anthropic:claude-sonnet-4-0', 'gateway/anthropic:claude-sonnet-4-20250514', 'gateway/anthropic:claude-sonnet-4-5', 'gateway/anthropic:claude-sonnet-4-5-20250929', 'gateway/bedrock:amazon.titan-text-express-v1', 'gateway/bedrock:amazon.titan-text-lite-v1', 'gateway/bedrock:amazon.titan-tg1-large', 'gateway/bedrock:anthropic.claude-3-5-haiku-20241022-v1:0', 'gateway/bedrock:anthropic.claude-3-5-sonnet-20240620-v1:0', 'gateway/bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0', 'gateway/bedrock:anthropic.claude-3-7-sonnet-20250219-v1:0', 'gateway/bedrock:anthropic.claude-3-haiku-20240307-v1:0', 'gateway/bedrock:anthropic.claude-3-opus-20240229-v1:0', 'gateway/bedrock:anthropic.claude-3-sonnet-20240229-v1:0', 'gateway/bedrock:anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:anthropic.claude-instant-v1', 'gateway/bedrock:anthropic.claude-opus-4-20250514-v1:0', 'gateway/bedrock:anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:anthropic.claude-v2', 'gateway/bedrock:anthropic.claude-v2:1', 'gateway/bedrock:cohere.command-light-text-v14', 'gateway/bedrock:cohere.command-r-plus-v1:0', 'gateway/bedrock:cohere.command-r-v1:0', 'gateway/bedrock:cohere.command-text-v14', 'gateway/bedrock:eu.anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:eu.anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:global.anthropic.claude-opus-4-5-20251101-v1:0', 'gateway/bedrock:meta.llama3-1-405b-instruct-v1:0', 'gateway/bedrock:meta.llama3-1-70b-instruct-v1:0', 'gateway/bedrock:meta.llama3-1-8b-instruct-v1:0', 'gateway/bedrock:meta.llama3-70b-instruct-v1:0', 'gateway/bedrock:meta.llama3-8b-instruct-v1:0', 'gateway/bedrock:mistral.mistral-7b-instruct-v0:2', 'gateway/bedrock:mistral.mistral-large-2402-v1:0', 'gateway/bedrock:mistral.mistral-large-2407-v1:0', 'gateway/bedrock:mistral.mixtral-8x7b-instruct-v0:1', 'gateway/bedrock:us.amazon.nova-lite-v1:0', 'gateway/bedrock:us.amazon.nova-micro-v1:0', 'gateway/bedrock:us.amazon.nova-pro-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-haiku-20241022-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-sonnet-20240620-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-sonnet-20241022-v2:0', 'gateway/bedrock:us.anthropic.claude-3-7-sonnet-20250219-v1:0', 'gateway/bedrock:us.anthropic.claude-3-haiku-20240307-v1:0', 'gateway/bedrock:us.anthropic.claude-3-opus-20240229-v1:0', 'gateway/bedrock:us.anthropic.claude-3-sonnet-20240229-v1:0', 'gateway/bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:us.anthropic.claude-opus-4-20250514-v1:0', 'gateway/bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:us.meta.llama3-1-70b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-1-8b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-11b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-1b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-3b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-90b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-3-70b-instruct-v1:0', 'gateway/google-vertex:gemini-2.0-flash', 'gateway/google-vertex:gemini-2.0-flash-lite', 'gateway/google-vertex:gemini-2.5-flash', 'gateway/google-vertex:gemini-2.5-flash-image', 'gateway/google-vertex:gemini-2.5-flash-lite', 'gateway/google-vertex:gemini-2.5-flash-lite-preview-09-2025', 'gateway/google-vertex:gemini-2.5-flash-preview-09-2025', 'gateway/google-vertex:gemini-2.5-pro', 'gateway/google-vertex:gemini-3-pro-image-preview', 'gateway/google-vertex:gemini-3-pro-preview', 'gateway/google-vertex:gemini-flash-latest', 'gateway/google-vertex:gemini-flash-lite-latest', 'gateway/groq:deepseek-r1-distill-llama-70b', 'gateway/groq:deepseek-r1-distill-qwen-32b', 'gateway/groq:distil-whisper-large-v3-en', 'gateway/groq:gemma2-9b-it', 'gateway/groq:llama-3.1-8b-instant', 'gateway/groq:llama-3.2-11b-vision-preview', 'gateway/groq:llama-3.2-1b-preview', 'gateway/groq:llama-3.2-3b-preview', 'gateway/groq:llama-3.2-90b-vision-preview', 'gateway/groq:llama-3.3-70b-specdec', 'gateway/groq:llama-3.3-70b-versatile', 'gateway/groq:llama-guard-3-8b', 'gateway/groq:llama3-70b-8192', 'gateway/groq:llama3-8b-8192', 'gateway/groq:mistral-saba-24b', 'gateway/groq:moonshotai/kimi-k2-instruct', 'gateway/groq:playai-tts', 'gateway/groq:playai-tts-arabic', 'gateway/groq:qwen-2.5-32b', 'gateway/groq:qwen-2.5-coder-32b', 'gateway/groq:qwen-qwq-32b', 'gateway/groq:whisper-large-v3', 'gateway/groq:whisper-large-v3-turbo', 'gateway/openai:chatgpt-4o-latest', 'gateway/openai:codex-mini-latest', 'gateway/openai:computer-use-preview', 'gateway/openai:computer-use-preview-2025-03-11', 'gateway/openai:gpt-3.5-turbo', 'gateway/openai:gpt-3.5-turbo-0125', 'gateway/openai:gpt-3.5-turbo-0301', 'gateway/openai:gpt-3.5-turbo-0613', 'gateway/openai:gpt-3.5-turbo-1106', 'gateway/openai:gpt-3.5-turbo-16k', 'gateway/openai:gpt-3.5-turbo-16k-0613', 'gateway/openai:gpt-4', 'gateway/openai:gpt-4-0125-preview', 'gateway/openai:gpt-4-0314', 'gateway/openai:gpt-4-0613', 'gateway/openai:gpt-4-1106-preview', 'gateway/openai:gpt-4-32k', 'gateway/openai:gpt-4-32k-0314', 'gateway/openai:gpt-4-32k-0613', 'gateway/openai:gpt-4-turbo', 'gateway/openai:gpt-4-turbo-2024-04-09', 'gateway/openai:gpt-4-turbo-preview', 'gateway/openai:gpt-4-vision-preview', 'gateway/openai:gpt-4.1', 'gateway/openai:gpt-4.1-2025-04-14', 'gateway/openai:gpt-4.1-mini', 'gateway/openai:gpt-4.1-mini-2025-04-14', 'gateway/openai:gpt-4.1-nano', 'gateway/openai:gpt-4.1-nano-2025-04-14', 'gateway/openai:gpt-4o', 'gateway/openai:gpt-4o-2024-05-13', 'gateway/openai:gpt-4o-2024-08-06', 'gateway/openai:gpt-4o-2024-11-20', 'gateway/openai:gpt-4o-audio-preview', 'gateway/openai:gpt-4o-audio-preview-2024-10-01', 'gateway/openai:gpt-4o-audio-preview-2024-12-17', 'gateway/openai:gpt-4o-audio-preview-2025-06-03', 'gateway/openai:gpt-4o-mini', 'gateway/openai:gpt-4o-mini-2024-07-18', 'gateway/openai:gpt-4o-mini-audio-preview', 'gateway/openai:gpt-4o-mini-audio-preview-2024-12-17', 'gateway/openai:gpt-4o-mini-search-preview', 'gateway/openai:gpt-4o-mini-search-preview-2025-03-11', 'gateway/openai:gpt-4o-search-preview', 'gateway/openai:gpt-4o-search-preview-2025-03-11', 'gateway/openai:gpt-5', 'gateway/openai:gpt-5-2025-08-07', 'gateway/openai:gpt-5-chat-latest', 'gateway/openai:gpt-5-codex', 'gateway/openai:gpt-5-mini', 'gateway/openai:gpt-5-mini-2025-08-07', 'gateway/openai:gpt-5-nano', 'gateway/openai:gpt-5-nano-2025-08-07', 'gateway/openai:gpt-5-pro', 'gateway/openai:gpt-5-pro-2025-10-06', 'gateway/openai:gpt-5.1', 'gateway/openai:gpt-5.1-2025-11-13', 'gateway/openai:gpt-5.1-chat-latest', 'gateway/openai:gpt-5.1-codex', 'gateway/openai:gpt-5.1-mini', 'gateway/openai:o1', 'gateway/openai:o1-2024-12-17', 'gateway/openai:o1-mini', 'gateway/openai:o1-mini-2024-09-12', 'gateway/openai:o1-preview', 'gateway/openai:o1-preview-2024-09-12', 'gateway/openai:o1-pro', 'gateway/openai:o1-pro-2025-03-19', 'gateway/openai:o3', 'gateway/openai:o3-2025-04-16', 'gateway/openai:o3-deep-research', 'gateway/openai:o3-deep-research-2025-06-26', 'gateway/openai:o3-mini', 'gateway/openai:o3-mini-2025-01-31', 'gateway/openai:o3-pro', 'gateway/openai:o3-pro-2025-06-10', 'gateway/openai:o4-mini', 'gateway/openai:o4-mini-2025-04-16', 'gateway/openai:o4-mini-deep-research', 'gateway/openai:o4-mini-deep-research-2025-06-26', 'google-gla:gemini-flash-latest', 'google-gla:gemini-flash-lite-latest', 'google-gla:gemini-2.0-flash', 'google-gla:gemini-2.0-flash-lite', 'google-gla:gemini-2.5-flash', 'google-gla:gemini-2.5-flash-preview-09-2025', 'google-gla:gemini-2.5-flash-image', 'google-gla:gemini-2.5-flash-lite', 'google-gla:gemini-2.5-flash-lite-preview-09-2025', 'google-gla:gemini-2.5-pro', 'google-gla:gemini-3-pro-preview', 'google-gla:gemini-3-pro-image-preview', 'google-vertex:gemini-flash-latest', 'google-vertex:gemini-flash-lite-latest', 'google-vertex:gemini-2.0-flash', 'google-vertex:gemini-2.0-flash-lite', 'google-vertex:gemini-2.5-flash', 'google-vertex:gemini-2.5-flash-preview-09-2025', 'google-vertex:gemini-2.5-flash-image', 'google-vertex:gemini-2.5-flash-lite', 'google-vertex:gemini-2.5-flash-lite-preview-09-2025', 'google-vertex:gemini-2.5-pro', 'google-vertex:gemini-3-pro-preview', 'google-vertex:gemini-3-pro-image-preview', 'grok:grok-2-image-1212', 'grok:grok-2-vision-1212', 'grok:grok-3', 'grok:grok-3-fast', 'grok:grok-3-mini', 'grok:grok-3-mini-fast', 'grok:grok-4', 'grok:grok-4-0709', 'grok:grok-4-fast', 'grok:grok-4-fast-reasoning', 'grok:grok-4-fast-non-reasoning', 'grok:grok-code-fast-1', 'grok:grok-4-1-fast', 'grok:grok-4-1-fast-reasoning', 'grok:grok-4-1-fast-non-reasoning', 'groq:deepseek-r1-distill-llama-70b', 'groq:deepseek-r1-distill-qwen-32b', 'groq:distil-whisper-large-v3-en', 'groq:gemma2-9b-it', 'groq:llama-3.1-8b-instant', 'groq:llama-3.2-11b-vision-preview', 'groq:llama-3.2-1b-preview', 'groq:llama-3.2-3b-preview', 'groq:llama-3.2-90b-vision-preview', 'groq:llama-3.3-70b-specdec', 'groq:llama-3.3-70b-versatile', 'groq:llama-guard-3-8b', 'groq:llama3-70b-8192', 'groq:llama3-8b-8192', 'groq:mistral-saba-24b', 'groq:moonshotai/kimi-k2-instruct', 'groq:playai-tts', 'groq:playai-tts-arabic', 'groq:qwen-2.5-32b', 'groq:qwen-2.5-coder-32b', 'groq:qwen-qwq-32b', 'groq:whisper-large-v3', 'groq:whisper-large-v3-turbo', 'heroku:amazon-rerank-1-0', 'heroku:claude-3-5-haiku', 'heroku:claude-3-5-sonnet-latest', 'heroku:claude-3-7-sonnet', 'heroku:claude-3-haiku', 'heroku:claude-4-5-haiku', 'heroku:claude-4-5-sonnet', 'heroku:claude-4-sonnet', 'heroku:cohere-rerank-3-5', 'heroku:gpt-oss-120b', 'heroku:nova-lite', 'heroku:nova-pro', 'huggingface:Qwen/QwQ-32B', 'huggingface:Qwen/Qwen2.5-72B-Instruct', 'huggingface:Qwen/Qwen3-235B-A22B', 'huggingface:Qwen/Qwen3-32B', 'huggingface:deepseek-ai/DeepSeek-R1', 'huggingface:meta-llama/Llama-3.3-70B-Instruct', 'huggingface:meta-llama/Llama-4-Maverick-17B-128E-Instruct', 'huggingface:meta-llama/Llama-4-Scout-17B-16E-Instruct', 'mistral:codestral-latest', 'mistral:mistral-large-latest', 'mistral:mistral-moderation-latest', 'mistral:mistral-small-latest', 'moonshotai:kimi-k2-0711-preview', 'moonshotai:kimi-latest', 'moonshotai:kimi-thinking-preview', 'moonshotai:moonshot-v1-128k', 'moonshotai:moonshot-v1-128k-vision-preview', 'moonshotai:moonshot-v1-32k', 'moonshotai:moonshot-v1-32k-vision-preview', 'moonshotai:moonshot-v1-8k', 'moonshotai:moonshot-v1-8k-vision-preview', 'openai:chatgpt-4o-latest', 'openai:codex-mini-latest', 'openai:computer-use-preview', 'openai:computer-use-preview-2025-03-11', 'openai:gpt-3.5-turbo', 'openai:gpt-3.5-turbo-0125', 'openai:gpt-3.5-turbo-0301', 'openai:gpt-3.5-turbo-0613', 'openai:gpt-3.5-turbo-1106', 'openai:gpt-3.5-turbo-16k', 'openai:gpt-3.5-turbo-16k-0613', 'openai:gpt-4', 'openai:gpt-4-0125-preview', 'openai:gpt-4-0314', 'openai:gpt-4-0613', 'openai:gpt-4-1106-preview', 'openai:gpt-4-32k', 'openai:gpt-4-32k-0314', 'openai:gpt-4-32k-0613', 'openai:gpt-4-turbo', 'openai:gpt-4-turbo-2024-04-09', 'openai:gpt-4-turbo-preview', 'openai:gpt-4-vision-preview', 'openai:gpt-4.1', 'openai:gpt-4.1-2025-04-14', 'openai:gpt-4.1-mini', 'openai:gpt-4.1-mini-2025-04-14', 'openai:gpt-4.1-nano', 'openai:gpt-4.1-nano-2025-04-14', 'openai:gpt-4o', 'openai:gpt-4o-2024-05-13', 'openai:gpt-4o-2024-08-06', 'openai:gpt-4o-2024-11-20', 'openai:gpt-4o-audio-preview', 'openai:gpt-4o-audio-preview-2024-10-01', 'openai:gpt-4o-audio-preview-2024-12-17', 'openai:gpt-4o-audio-preview-2025-06-03', 'openai:gpt-4o-mini', 'openai:gpt-4o-mini-2024-07-18', 'openai:gpt-4o-mini-audio-preview', 'openai:gpt-4o-mini-audio-preview-2024-12-17', 'openai:gpt-4o-mini-search-preview', 'openai:gpt-4o-mini-search-preview-2025-03-11', 'openai:gpt-4o-search-preview', 'openai:gpt-4o-search-preview-2025-03-11', 'openai:gpt-5', 'openai:gpt-5-2025-08-07', 'openai:gpt-5-chat-latest', 'openai:gpt-5-codex', 'openai:gpt-5-mini', 'openai:gpt-5-mini-2025-08-07', 'openai:gpt-5-nano', 'openai:gpt-5-nano-2025-08-07', 'openai:gpt-5-pro', 'openai:gpt-5-pro-2025-10-06', 'openai:gpt-5.1', 'openai:gpt-5.1-2025-11-13', 'openai:gpt-5.1-chat-latest', 'openai:gpt-5.1-codex', 'openai:gpt-5.1-mini', 'openai:o1', 'openai:o1-2024-12-17', 'openai:o1-mini', 'openai:o1-mini-2024-09-12', 'openai:o1-preview', 'openai:o1-preview-2024-09-12', 'openai:o1-pro', 'openai:o1-pro-2025-03-19', 'openai:o3', 'openai:o3-2025-04-16', 'openai:o3-deep-research', 'openai:o3-deep-research-2025-06-26', 'openai:o3-mini', 'openai:o3-mini-2025-01-31', 'openai:o3-pro', 'openai:o3-pro-2025-06-10', 'openai:o4-mini', 'openai:o4-mini-2025-04-16', 'openai:o4-mini-deep-research', 'openai:o4-mini-deep-research-2025-06-26', 'test'] | Model | str | None = ..., instructions: str | Callable[[RunContext[None]], str] | Callable[[RunContext[None]], Awaitable[str]] | Callable[[], str] | Callable[[], Awaitable[str]] | Sequence[str | Callable[[RunContext[None]], str] | Callable[[RunContext[None]], Awaitable[str]] | Callable[[], str] | Callable[[], Awaitable[str]]] | None = ..., deps: None = ..., model_settings: ModelSettings | None = ..., usage_limits: UsageLimits | None = ..., usage: RunUsage | None = ..., infer_name: bool = ..., toolsets: Sequence[AbstractToolset[None]] | None = ..., builtin_tools: Sequence[AbstractBuiltinTool | Callable[[RunContext[None]], Awaitable[AbstractBuiltinTool | None] | AbstractBuiltinTool | None]] | None = ..., event_stream_handler: Callable[[RunContext[None], AsyncIterable[PartStartEvent | PartDeltaEvent | PartEndEvent | FinalResultEvent | FunctionToolCallEvent | FunctionToolResultEvent | BuiltinToolCallEvent | BuiltinToolResultEvent]], Awaitable[None]] | None = ...) -> Coroutine[Any, Any, AgentRunResult[RunOutputDataT]]
nexus/api/wizard_chat.py:352: error: Item "None" of "WizardCache | None" has no attribute "confirmation_metadata"  [union-attr]
nexus/api/wizard_chat.py:409: error: Incompatible types in assignment (expression has type "str", variable has type "Literal['setting', 'character', 'seed'] | None")  [assignment]
nexus/api/wizard_chat.py:563: error: Argument "model" to "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:565: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:599: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:601: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:602: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:606: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:612: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:621: error: Argument "thread_id" to "from_request" of "WizardContext" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:631: error: Argument 1 to "build_message_history" has incompatible type "list[Message]"; expected "Sequence[dict[str, Any]]"  [arg-type]
nexus/api/wizard_chat.py:653: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:682: error: Argument "thread_id" to "_handle_accept_fate_traits" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:685: error: Argument 3 to "_artifact_response" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:694: error: No overload variant of "run" of "AbstractAgent" matches argument types "str | None", "WizardContext", "list[ModelRequest | ModelResponse]", "Model", "ModelSettings"  [call-overload]
nexus/api/wizard_chat.py:694: note: Possible overload variants:
nexus/api/wizard_chat.py:694: note:     def run(self, user_prompt: str | Sequence[str | ImageUrl | AudioUrl | DocumentUrl | VideoUrl | BinaryContent | CachePoint] | None = ..., *, output_type: None = ..., message_history: Sequence[ModelRequest | ModelResponse] | None = ..., deferred_tool_results: DeferredToolResults | None = ..., model: Literal['anthropic:claude-3-5-haiku-20241022', 'anthropic:claude-3-5-haiku-latest', 'anthropic:claude-3-7-sonnet-20250219', 'anthropic:claude-3-7-sonnet-latest', 'anthropic:claude-3-haiku-20240307', 'anthropic:claude-3-opus-20240229', 'anthropic:claude-3-opus-latest', 'anthropic:claude-4-opus-20250514', 'anthropic:claude-4-sonnet-20250514', 'anthropic:claude-haiku-4-5', 'anthropic:claude-haiku-4-5-20251001', 'anthropic:claude-opus-4-0', 'anthropic:claude-opus-4-1-20250805', 'anthropic:claude-opus-4-20250514', 'anthropic:claude-opus-4-5', 'anthropic:claude-opus-4-5-20251101', 'anthropic:claude-sonnet-4-0', 'anthropic:claude-sonnet-4-20250514', 'anthropic:claude-sonnet-4-5', 'anthropic:claude-sonnet-4-5-20250929', 'bedrock:amazon.titan-text-express-v1', 'bedrock:amazon.titan-text-lite-v1', 'bedrock:amazon.titan-tg1-large', 'bedrock:anthropic.claude-3-5-haiku-20241022-v1:0', 'bedrock:anthropic.claude-3-5-sonnet-20240620-v1:0', 'bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0', 'bedrock:anthropic.claude-3-7-sonnet-20250219-v1:0', 'bedrock:anthropic.claude-3-haiku-20240307-v1:0', 'bedrock:anthropic.claude-3-opus-20240229-v1:0', 'bedrock:anthropic.claude-3-sonnet-20240229-v1:0', 'bedrock:anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:anthropic.claude-instant-v1', 'bedrock:anthropic.claude-opus-4-20250514-v1:0', 'bedrock:anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:anthropic.claude-v2', 'bedrock:anthropic.claude-v2:1', 'bedrock:cohere.command-light-text-v14', 'bedrock:cohere.command-r-plus-v1:0', 'bedrock:cohere.command-r-v1:0', 'bedrock:cohere.command-text-v14', 'bedrock:eu.anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:eu.anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:global.anthropic.claude-opus-4-5-20251101-v1:0', 'bedrock:meta.llama3-1-405b-instruct-v1:0', 'bedrock:meta.llama3-1-70b-instruct-v1:0', 'bedrock:meta.llama3-1-8b-instruct-v1:0', 'bedrock:meta.llama3-70b-instruct-v1:0', 'bedrock:meta.llama3-8b-instruct-v1:0', 'bedrock:mistral.mistral-7b-instruct-v0:2', 'bedrock:mistral.mistral-large-2402-v1:0', 'bedrock:mistral.mistral-large-2407-v1:0', 'bedrock:mistral.mixtral-8x7b-instruct-v0:1', 'bedrock:us.amazon.nova-lite-v1:0', 'bedrock:us.amazon.nova-micro-v1:0', 'bedrock:us.amazon.nova-pro-v1:0', 'bedrock:us.anthropic.claude-3-5-haiku-20241022-v1:0', 'bedrock:us.anthropic.claude-3-5-sonnet-20240620-v1:0', 'bedrock:us.anthropic.claude-3-5-sonnet-20241022-v2:0', 'bedrock:us.anthropic.claude-3-7-sonnet-20250219-v1:0', 'bedrock:us.anthropic.claude-3-haiku-20240307-v1:0', 'bedrock:us.anthropic.claude-3-opus-20240229-v1:0', 'bedrock:us.anthropic.claude-3-sonnet-20240229-v1:0', 'bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:us.anthropic.claude-opus-4-20250514-v1:0', 'bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:us.meta.llama3-1-70b-instruct-v1:0', 'bedrock:us.meta.llama3-1-8b-instruct-v1:0', 'bedrock:us.meta.llama3-2-11b-instruct-v1:0', 'bedrock:us.meta.llama3-2-1b-instruct-v1:0', 'bedrock:us.meta.llama3-2-3b-instruct-v1:0', 'bedrock:us.meta.llama3-2-90b-instruct-v1:0', 'bedrock:us.meta.llama3-3-70b-instruct-v1:0', 'cerebras:gpt-oss-120b', 'cerebras:llama-3.3-70b', 'cerebras:llama3.1-8b', 'cerebras:qwen-3-235b-a22b-instruct-2507', 'cerebras:qwen-3-32b', 'cerebras:zai-glm-4.6', 'cohere:c4ai-aya-expanse-32b', 'cohere:c4ai-aya-expanse-8b', 'cohere:command-nightly', 'cohere:command-r-08-2024', 'cohere:command-r-plus-08-2024', 'cohere:command-r7b-12-2024', 'deepseek:deepseek-chat', 'deepseek:deepseek-reasoner', 'gateway/anthropic:claude-3-5-haiku-20241022', 'gateway/anthropic:claude-3-5-haiku-latest', 'gateway/anthropic:claude-3-7-sonnet-20250219', 'gateway/anthropic:claude-3-7-sonnet-latest', 'gateway/anthropic:claude-3-haiku-20240307', 'gateway/anthropic:claude-3-opus-20240229', 'gateway/anthropic:claude-3-opus-latest', 'gateway/anthropic:claude-4-opus-20250514', 'gateway/anthropic:claude-4-sonnet-20250514', 'gateway/anthropic:claude-haiku-4-5', 'gateway/anthropic:claude-haiku-4-5-20251001', 'gateway/anthropic:claude-opus-4-0', 'gateway/anthropic:claude-opus-4-1-20250805', 'gateway/anthropic:claude-opus-4-20250514', 'gateway/anthropic:claude-opus-4-5', 'gateway/anthropic:claude-opus-4-5-20251101', 'gateway/anthropic:claude-sonnet-4-0', 'gateway/anthropic:claude-sonnet-4-20250514', 'gateway/anthropic:claude-sonnet-4-5', 'gateway/anthropic:claude-sonnet-4-5-20250929', 'gateway/bedrock:amazon.titan-text-express-v1', 'gateway/bedrock:amazon.titan-text-lite-v1', 'gateway/bedrock:amazon.titan-tg1-large', 'gateway/bedrock:anthropic.claude-3-5-haiku-20241022-v1:0', 'gateway/bedrock:anthropic.claude-3-5-sonnet-20240620-v1:0', 'gateway/bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0', 'gateway/bedrock:anthropic.claude-3-7-sonnet-20250219-v1:0', 'gateway/bedrock:anthropic.claude-3-haiku-20240307-v1:0', 'gateway/bedrock:anthropic.claude-3-opus-20240229-v1:0', 'gateway/bedrock:anthropic.claude-3-sonnet-20240229-v1:0', 'gateway/bedrock:anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:anthropic.claude-instant-v1', 'gateway/bedrock:anthropic.claude-opus-4-20250514-v1:0', 'gateway/bedrock:anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:anthropic.claude-v2', 'gateway/bedrock:anthropic.claude-v2:1', 'gateway/bedrock:cohere.command-light-text-v14', 'gateway/bedrock:cohere.command-r-plus-v1:0', 'gateway/bedrock:cohere.command-r-v1:0', 'gateway/bedrock:cohere.command-text-v14', 'gateway/bedrock:eu.anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:eu.anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:global.anthropic.claude-opus-4-5-20251101-v1:0', 'gateway/bedrock:meta.llama3-1-405b-instruct-v1:0', 'gateway/bedrock:meta.llama3-1-70b-instruct-v1:0', 'gateway/bedrock:meta.llama3-1-8b-instruct-v1:0', 'gateway/bedrock:meta.llama3-70b-instruct-v1:0', 'gateway/bedrock:meta.llama3-8b-instruct-v1:0', 'gateway/bedrock:mistral.mistral-7b-instruct-v0:2', 'gateway/bedrock:mistral.mistral-large-2402-v1:0', 'gateway/bedrock:mistral.mistral-large-2407-v1:0', 'gateway/bedrock:mistral.mixtral-8x7b-instruct-v0:1', 'gateway/bedrock:us.amazon.nova-lite-v1:0', 'gateway/bedrock:us.amazon.nova-micro-v1:0', 'gateway/bedrock:us.amazon.nova-pro-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-haiku-20241022-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-sonnet-20240620-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-sonnet-20241022-v2:0', 'gateway/bedrock:us.anthropic.claude-3-7-sonnet-20250219-v1:0', 'gateway/bedrock:us.anthropic.claude-3-haiku-20240307-v1:0', 'gateway/bedrock:us.anthropic.claude-3-opus-20240229-v1:0', 'gateway/bedrock:us.anthropic.claude-3-sonnet-20240229-v1:0', 'gateway/bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:us.anthropic.claude-opus-4-20250514-v1:0', 'gateway/bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:us.meta.llama3-1-70b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-1-8b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-11b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-1b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-3b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-90b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-3-70b-instruct-v1:0', 'gateway/google-vertex:gemini-2.0-flash', 'gateway/google-vertex:gemini-2.0-flash-lite', 'gateway/google-vertex:gemini-2.5-flash', 'gateway/google-vertex:gemini-2.5-flash-image', 'gateway/google-vertex:gemini-2.5-flash-lite', 'gateway/google-vertex:gemini-2.5-flash-lite-preview-09-2025', 'gateway/google-vertex:gemini-2.5-flash-preview-09-2025', 'gateway/google-vertex:gemini-2.5-pro', 'gateway/google-vertex:gemini-3-pro-image-preview', 'gateway/google-vertex:gemini-3-pro-preview', 'gateway/google-vertex:gemini-flash-latest', 'gateway/google-vertex:gemini-flash-lite-latest', 'gateway/groq:deepseek-r1-distill-llama-70b', 'gateway/groq:deepseek-r1-distill-qwen-32b', 'gateway/groq:distil-whisper-large-v3-en', 'gateway/groq:gemma2-9b-it', 'gateway/groq:llama-3.1-8b-instant', 'gateway/groq:llama-3.2-11b-vision-preview', 'gateway/groq:llama-3.2-1b-preview', 'gateway/groq:llama-3.2-3b-preview', 'gateway/groq:llama-3.2-90b-vision-preview', 'gateway/groq:llama-3.3-70b-specdec', 'gateway/groq:llama-3.3-70b-versatile', 'gateway/groq:llama-guard-3-8b', 'gateway/groq:llama3-70b-8192', 'gateway/groq:llama3-8b-8192', 'gateway/groq:mistral-saba-24b', 'gateway/groq:moonshotai/kimi-k2-instruct', 'gateway/groq:playai-tts', 'gateway/groq:playai-tts-arabic', 'gateway/groq:qwen-2.5-32b', 'gateway/groq:qwen-2.5-coder-32b', 'gateway/groq:qwen-qwq-32b', 'gateway/groq:whisper-large-v3', 'gateway/groq:whisper-large-v3-turbo', 'gateway/openai:chatgpt-4o-latest', 'gateway/openai:codex-mini-latest', 'gateway/openai:computer-use-preview', 'gateway/openai:computer-use-preview-2025-03-11', 'gateway/openai:gpt-3.5-turbo', 'gateway/openai:gpt-3.5-turbo-0125', 'gateway/openai:gpt-3.5-turbo-0301', 'gateway/openai:gpt-3.5-turbo-0613', 'gateway/openai:gpt-3.5-turbo-1106', 'gateway/openai:gpt-3.5-turbo-16k', 'gateway/openai:gpt-3.5-turbo-16k-0613', 'gateway/openai:gpt-4', 'gateway/openai:gpt-4-0125-preview', 'gateway/openai:gpt-4-0314', 'gateway/openai:gpt-4-0613', 'gateway/openai:gpt-4-1106-preview', 'gateway/openai:gpt-4-32k', 'gateway/openai:gpt-4-32k-0314', 'gateway/openai:gpt-4-32k-0613', 'gateway/openai:gpt-4-turbo', 'gateway/openai:gpt-4-turbo-2024-04-09', 'gateway/openai:gpt-4-turbo-preview', 'gateway/openai:gpt-4-vision-preview', 'gateway/openai:gpt-4.1', 'gateway/openai:gpt-4.1-2025-04-14', 'gateway/openai:gpt-4.1-mini', 'gateway/openai:gpt-4.1-mini-2025-04-14', 'gateway/openai:gpt-4.1-nano', 'gateway/openai:gpt-4.1-nano-2025-04-14', 'gateway/openai:gpt-4o', 'gateway/openai:gpt-4o-2024-05-13', 'gateway/openai:gpt-4o-2024-08-06', 'gateway/openai:gpt-4o-2024-11-20', 'gateway/openai:gpt-4o-audio-preview', 'gateway/openai:gpt-4o-audio-preview-2024-10-01', 'gateway/openai:gpt-4o-audio-preview-2024-12-17', 'gateway/openai:gpt-4o-audio-preview-2025-06-03', 'gateway/openai:gpt-4o-mini', 'gateway/openai:gpt-4o-mini-2024-07-18', 'gateway/openai:gpt-4o-mini-audio-preview', 'gateway/openai:gpt-4o-mini-audio-preview-2024-12-17', 'gateway/openai:gpt-4o-mini-search-preview', 'gateway/openai:gpt-4o-mini-search-preview-2025-03-11', 'gateway/openai:gpt-4o-search-preview', 'gateway/openai:gpt-4o-search-preview-2025-03-11', 'gateway/openai:gpt-5', 'gateway/openai:gpt-5-2025-08-07', 'gateway/openai:gpt-5-chat-latest', 'gateway/openai:gpt-5-codex', 'gateway/openai:gpt-5-mini', 'gateway/openai:gpt-5-mini-2025-08-07', 'gateway/openai:gpt-5-nano', 'gateway/openai:gpt-5-nano-2025-08-07', 'gateway/openai:gpt-5-pro', 'gateway/openai:gpt-5-pro-2025-10-06', 'gateway/openai:gpt-5.1', 'gateway/openai:gpt-5.1-2025-11-13', 'gateway/openai:gpt-5.1-chat-latest', 'gateway/openai:gpt-5.1-codex', 'gateway/openai:gpt-5.1-mini', 'gateway/openai:o1', 'gateway/openai:o1-2024-12-17', 'gateway/openai:o1-mini', 'gateway/openai:o1-mini-2024-09-12', 'gateway/openai:o1-preview', 'gateway/openai:o1-preview-2024-09-12', 'gateway/openai:o1-pro', 'gateway/openai:o1-pro-2025-03-19', 'gateway/openai:o3', 'gateway/openai:o3-2025-04-16', 'gateway/openai:o3-deep-research', 'gateway/openai:o3-deep-research-2025-06-26', 'gateway/openai:o3-mini', 'gateway/openai:o3-mini-2025-01-31', 'gateway/openai:o3-pro', 'gateway/openai:o3-pro-2025-06-10', 'gateway/openai:o4-mini', 'gateway/openai:o4-mini-2025-04-16', 'gateway/openai:o4-mini-deep-research', 'gateway/openai:o4-mini-deep-research-2025-06-26', 'google-gla:gemini-flash-latest', 'google-gla:gemini-flash-lite-latest', 'google-gla:gemini-2.0-flash', 'google-gla:gemini-2.0-flash-lite', 'google-gla:gemini-2.5-flash', 'google-gla:gemini-2.5-flash-preview-09-2025', 'google-gla:gemini-2.5-flash-image', 'google-gla:gemini-2.5-flash-lite', 'google-gla:gemini-2.5-flash-lite-preview-09-2025', 'google-gla:gemini-2.5-pro', 'google-gla:gemini-3-pro-preview', 'google-gla:gemini-3-pro-image-preview', 'google-vertex:gemini-flash-latest', 'google-vertex:gemini-flash-lite-latest', 'google-vertex:gemini-2.0-flash', 'google-vertex:gemini-2.0-flash-lite', 'google-vertex:gemini-2.5-flash', 'google-vertex:gemini-2.5-flash-preview-09-2025', 'google-vertex:gemini-2.5-flash-image', 'google-vertex:gemini-2.5-flash-lite', 'google-vertex:gemini-2.5-flash-lite-preview-09-2025', 'google-vertex:gemini-2.5-pro', 'google-vertex:gemini-3-pro-preview', 'google-vertex:gemini-3-pro-image-preview', 'grok:grok-2-image-1212', 'grok:grok-2-vision-1212', 'grok:grok-3', 'grok:grok-3-fast', 'grok:grok-3-mini', 'grok:grok-3-mini-fast', 'grok:grok-4', 'grok:grok-4-0709', 'grok:grok-4-fast', 'grok:grok-4-fast-reasoning', 'grok:grok-4-fast-non-reasoning', 'grok:grok-code-fast-1', 'grok:grok-4-1-fast', 'grok:grok-4-1-fast-reasoning', 'grok:grok-4-1-fast-non-reasoning', 'groq:deepseek-r1-distill-llama-70b', 'groq:deepseek-r1-distill-qwen-32b', 'groq:distil-whisper-large-v3-en', 'groq:gemma2-9b-it', 'groq:llama-3.1-8b-instant', 'groq:llama-3.2-11b-vision-preview', 'groq:llama-3.2-1b-preview', 'groq:llama-3.2-3b-preview', 'groq:llama-3.2-90b-vision-preview', 'groq:llama-3.3-70b-specdec', 'groq:llama-3.3-70b-versatile', 'groq:llama-guard-3-8b', 'groq:llama3-70b-8192', 'groq:llama3-8b-8192', 'groq:mistral-saba-24b', 'groq:moonshotai/kimi-k2-instruct', 'groq:playai-tts', 'groq:playai-tts-arabic', 'groq:qwen-2.5-32b', 'groq:qwen-2.5-coder-32b', 'groq:qwen-qwq-32b', 'groq:whisper-large-v3', 'groq:whisper-large-v3-turbo', 'heroku:amazon-rerank-1-0', 'heroku:claude-3-5-haiku', 'heroku:claude-3-5-sonnet-latest', 'heroku:claude-3-7-sonnet', 'heroku:claude-3-haiku', 'heroku:claude-4-5-haiku', 'heroku:claude-4-5-sonnet', 'heroku:claude-4-sonnet', 'heroku:cohere-rerank-3-5', 'heroku:gpt-oss-120b', 'heroku:nova-lite', 'heroku:nova-pro', 'huggingface:Qwen/QwQ-32B', 'huggingface:Qwen/Qwen2.5-72B-Instruct', 'huggingface:Qwen/Qwen3-235B-A22B', 'huggingface:Qwen/Qwen3-32B', 'huggingface:deepseek-ai/DeepSeek-R1', 'huggingface:meta-llama/Llama-3.3-70B-Instruct', 'huggingface:meta-llama/Llama-4-Maverick-17B-128E-Instruct', 'huggingface:meta-llama/Llama-4-Scout-17B-16E-Instruct', 'mistral:codestral-latest', 'mistral:mistral-large-latest', 'mistral:mistral-moderation-latest', 'mistral:mistral-small-latest', 'moonshotai:kimi-k2-0711-preview', 'moonshotai:kimi-latest', 'moonshotai:kimi-thinking-preview', 'moonshotai:moonshot-v1-128k', 'moonshotai:moonshot-v1-128k-vision-preview', 'moonshotai:moonshot-v1-32k', 'moonshotai:moonshot-v1-32k-vision-preview', 'moonshotai:moonshot-v1-8k', 'moonshotai:moonshot-v1-8k-vision-preview', 'openai:chatgpt-4o-latest', 'openai:codex-mini-latest', 'openai:computer-use-preview', 'openai:computer-use-preview-2025-03-11', 'openai:gpt-3.5-turbo', 'openai:gpt-3.5-turbo-0125', 'openai:gpt-3.5-turbo-0301', 'openai:gpt-3.5-turbo-0613', 'openai:gpt-3.5-turbo-1106', 'openai:gpt-3.5-turbo-16k', 'openai:gpt-3.5-turbo-16k-0613', 'openai:gpt-4', 'openai:gpt-4-0125-preview', 'openai:gpt-4-0314', 'openai:gpt-4-0613', 'openai:gpt-4-1106-preview', 'openai:gpt-4-32k', 'openai:gpt-4-32k-0314', 'openai:gpt-4-32k-0613', 'openai:gpt-4-turbo', 'openai:gpt-4-turbo-2024-04-09', 'openai:gpt-4-turbo-preview', 'openai:gpt-4-vision-preview', 'openai:gpt-4.1', 'openai:gpt-4.1-2025-04-14', 'openai:gpt-4.1-mini', 'openai:gpt-4.1-mini-2025-04-14', 'openai:gpt-4.1-nano', 'openai:gpt-4.1-nano-2025-04-14', 'openai:gpt-4o', 'openai:gpt-4o-2024-05-13', 'openai:gpt-4o-2024-08-06', 'openai:gpt-4o-2024-11-20', 'openai:gpt-4o-audio-preview', 'openai:gpt-4o-audio-preview-2024-10-01', 'openai:gpt-4o-audio-preview-2024-12-17', 'openai:gpt-4o-audio-preview-2025-06-03', 'openai:gpt-4o-mini', 'openai:gpt-4o-mini-2024-07-18', 'openai:gpt-4o-mini-audio-preview', 'openai:gpt-4o-mini-audio-preview-2024-12-17', 'openai:gpt-4o-mini-search-preview', 'openai:gpt-4o-mini-search-preview-2025-03-11', 'openai:gpt-4o-search-preview', 'openai:gpt-4o-search-preview-2025-03-11', 'openai:gpt-5', 'openai:gpt-5-2025-08-07', 'openai:gpt-5-chat-latest', 'openai:gpt-5-codex', 'openai:gpt-5-mini', 'openai:gpt-5-mini-2025-08-07', 'openai:gpt-5-nano', 'openai:gpt-5-nano-2025-08-07', 'openai:gpt-5-pro', 'openai:gpt-5-pro-2025-10-06', 'openai:gpt-5.1', 'openai:gpt-5.1-2025-11-13', 'openai:gpt-5.1-chat-latest', 'openai:gpt-5.1-codex', 'openai:gpt-5.1-mini', 'openai:o1', 'openai:o1-2024-12-17', 'openai:o1-mini', 'openai:o1-mini-2024-09-12', 'openai:o1-preview', 'openai:o1-preview-2024-09-12', 'openai:o1-pro', 'openai:o1-pro-2025-03-19', 'openai:o3', 'openai:o3-2025-04-16', 'openai:o3-deep-research', 'openai:o3-deep-research-2025-06-26', 'openai:o3-mini', 'openai:o3-mini-2025-01-31', 'openai:o3-pro', 'openai:o3-pro-2025-06-10', 'openai:o4-mini', 'openai:o4-mini-2025-04-16', 'openai:o4-mini-deep-research', 'openai:o4-mini-deep-research-2025-06-26', 'test'] | Model | str | None = ..., instructions: str | Callable[[RunContext[None]], str] | Callable[[RunContext[None]], Awaitable[str]] | Callable[[], str] | Callable[[], Awaitable[str]] | Sequence[str | Callable[[RunContext[None]], str] | Callable[[RunContext[None]], Awaitable[str]] | Callable[[], str] | Callable[[], Awaitable[str]]] | None = ..., deps: None = ..., model_settings: ModelSettings | None = ..., usage_limits: UsageLimits | None = ..., usage: RunUsage | None = ..., infer_name: bool = ..., toolsets: Sequence[AbstractToolset[None]] | None = ..., builtin_tools: Sequence[AbstractBuiltinTool | Callable[[RunContext[None]], Awaitable[AbstractBuiltinTool | None] | AbstractBuiltinTool | None]] | None = ..., event_stream_handler: Callable[[RunContext[None], AsyncIterable[PartStartEvent | PartDeltaEvent | PartEndEvent | FinalResultEvent | FunctionToolCallEvent | FunctionToolResultEvent | BuiltinToolCallEvent | BuiltinToolResultEvent]], Awaitable[None]] | None = ...) -> Coroutine[Any, Any, AgentRunResult[str]]
nexus/api/wizard_chat.py:694: note:     def [RunOutputDataT] run(self, user_prompt: str | Sequence[str | ImageUrl | AudioUrl | DocumentUrl | VideoUrl | BinaryContent | CachePoint] | None = ..., *, output_type: type[RunOutputDataT] | Callable[..., Awaitable[RunOutputDataT] | RunOutputDataT] | ToolOutput[RunOutputDataT] | NativeOutput[RunOutputDataT] | PromptedOutput[RunOutputDataT] | TextOutput[RunOutputDataT] | Sequence[Any], message_history: Sequence[ModelRequest | ModelResponse] | None = ..., deferred_tool_results: DeferredToolResults | None = ..., model: Literal['anthropic:claude-3-5-haiku-20241022', 'anthropic:claude-3-5-haiku-latest', 'anthropic:claude-3-7-sonnet-20250219', 'anthropic:claude-3-7-sonnet-latest', 'anthropic:claude-3-haiku-20240307', 'anthropic:claude-3-opus-20240229', 'anthropic:claude-3-opus-latest', 'anthropic:claude-4-opus-20250514', 'anthropic:claude-4-sonnet-20250514', 'anthropic:claude-haiku-4-5', 'anthropic:claude-haiku-4-5-20251001', 'anthropic:claude-opus-4-0', 'anthropic:claude-opus-4-1-20250805', 'anthropic:claude-opus-4-20250514', 'anthropic:claude-opus-4-5', 'anthropic:claude-opus-4-5-20251101', 'anthropic:claude-sonnet-4-0', 'anthropic:claude-sonnet-4-20250514', 'anthropic:claude-sonnet-4-5', 'anthropic:claude-sonnet-4-5-20250929', 'bedrock:amazon.titan-text-express-v1', 'bedrock:amazon.titan-text-lite-v1', 'bedrock:amazon.titan-tg1-large', 'bedrock:anthropic.claude-3-5-haiku-20241022-v1:0', 'bedrock:anthropic.claude-3-5-sonnet-20240620-v1:0', 'bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0', 'bedrock:anthropic.claude-3-7-sonnet-20250219-v1:0', 'bedrock:anthropic.claude-3-haiku-20240307-v1:0', 'bedrock:anthropic.claude-3-opus-20240229-v1:0', 'bedrock:anthropic.claude-3-sonnet-20240229-v1:0', 'bedrock:anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:anthropic.claude-instant-v1', 'bedrock:anthropic.claude-opus-4-20250514-v1:0', 'bedrock:anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:anthropic.claude-v2', 'bedrock:anthropic.claude-v2:1', 'bedrock:cohere.command-light-text-v14', 'bedrock:cohere.command-r-plus-v1:0', 'bedrock:cohere.command-r-v1:0', 'bedrock:cohere.command-text-v14', 'bedrock:eu.anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:eu.anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:global.anthropic.claude-opus-4-5-20251101-v1:0', 'bedrock:meta.llama3-1-405b-instruct-v1:0', 'bedrock:meta.llama3-1-70b-instruct-v1:0', 'bedrock:meta.llama3-1-8b-instruct-v1:0', 'bedrock:meta.llama3-70b-instruct-v1:0', 'bedrock:meta.llama3-8b-instruct-v1:0', 'bedrock:mistral.mistral-7b-instruct-v0:2', 'bedrock:mistral.mistral-large-2402-v1:0', 'bedrock:mistral.mistral-large-2407-v1:0', 'bedrock:mistral.mixtral-8x7b-instruct-v0:1', 'bedrock:us.amazon.nova-lite-v1:0', 'bedrock:us.amazon.nova-micro-v1:0', 'bedrock:us.amazon.nova-pro-v1:0', 'bedrock:us.anthropic.claude-3-5-haiku-20241022-v1:0', 'bedrock:us.anthropic.claude-3-5-sonnet-20240620-v1:0', 'bedrock:us.anthropic.claude-3-5-sonnet-20241022-v2:0', 'bedrock:us.anthropic.claude-3-7-sonnet-20250219-v1:0', 'bedrock:us.anthropic.claude-3-haiku-20240307-v1:0', 'bedrock:us.anthropic.claude-3-opus-20240229-v1:0', 'bedrock:us.anthropic.claude-3-sonnet-20240229-v1:0', 'bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0', 'bedrock:us.anthropic.claude-opus-4-20250514-v1:0', 'bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0', 'bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0', 'bedrock:us.meta.llama3-1-70b-instruct-v1:0', 'bedrock:us.meta.llama3-1-8b-instruct-v1:0', 'bedrock:us.meta.llama3-2-11b-instruct-v1:0', 'bedrock:us.meta.llama3-2-1b-instruct-v1:0', 'bedrock:us.meta.llama3-2-3b-instruct-v1:0', 'bedrock:us.meta.llama3-2-90b-instruct-v1:0', 'bedrock:us.meta.llama3-3-70b-instruct-v1:0', 'cerebras:gpt-oss-120b', 'cerebras:llama-3.3-70b', 'cerebras:llama3.1-8b', 'cerebras:qwen-3-235b-a22b-instruct-2507', 'cerebras:qwen-3-32b', 'cerebras:zai-glm-4.6', 'cohere:c4ai-aya-expanse-32b', 'cohere:c4ai-aya-expanse-8b', 'cohere:command-nightly', 'cohere:command-r-08-2024', 'cohere:command-r-plus-08-2024', 'cohere:command-r7b-12-2024', 'deepseek:deepseek-chat', 'deepseek:deepseek-reasoner', 'gateway/anthropic:claude-3-5-haiku-20241022', 'gateway/anthropic:claude-3-5-haiku-latest', 'gateway/anthropic:claude-3-7-sonnet-20250219', 'gateway/anthropic:claude-3-7-sonnet-latest', 'gateway/anthropic:claude-3-haiku-20240307', 'gateway/anthropic:claude-3-opus-20240229', 'gateway/anthropic:claude-3-opus-latest', 'gateway/anthropic:claude-4-opus-20250514', 'gateway/anthropic:claude-4-sonnet-20250514', 'gateway/anthropic:claude-haiku-4-5', 'gateway/anthropic:claude-haiku-4-5-20251001', 'gateway/anthropic:claude-opus-4-0', 'gateway/anthropic:claude-opus-4-1-20250805', 'gateway/anthropic:claude-opus-4-20250514', 'gateway/anthropic:claude-opus-4-5', 'gateway/anthropic:claude-opus-4-5-20251101', 'gateway/anthropic:claude-sonnet-4-0', 'gateway/anthropic:claude-sonnet-4-20250514', 'gateway/anthropic:claude-sonnet-4-5', 'gateway/anthropic:claude-sonnet-4-5-20250929', 'gateway/bedrock:amazon.titan-text-express-v1', 'gateway/bedrock:amazon.titan-text-lite-v1', 'gateway/bedrock:amazon.titan-tg1-large', 'gateway/bedrock:anthropic.claude-3-5-haiku-20241022-v1:0', 'gateway/bedrock:anthropic.claude-3-5-sonnet-20240620-v1:0', 'gateway/bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0', 'gateway/bedrock:anthropic.claude-3-7-sonnet-20250219-v1:0', 'gateway/bedrock:anthropic.claude-3-haiku-20240307-v1:0', 'gateway/bedrock:anthropic.claude-3-opus-20240229-v1:0', 'gateway/bedrock:anthropic.claude-3-sonnet-20240229-v1:0', 'gateway/bedrock:anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:anthropic.claude-instant-v1', 'gateway/bedrock:anthropic.claude-opus-4-20250514-v1:0', 'gateway/bedrock:anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:anthropic.claude-v2', 'gateway/bedrock:anthropic.claude-v2:1', 'gateway/bedrock:cohere.command-light-text-v14', 'gateway/bedrock:cohere.command-r-plus-v1:0', 'gateway/bedrock:cohere.command-r-v1:0', 'gateway/bedrock:cohere.command-text-v14', 'gateway/bedrock:eu.anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:eu.anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:eu.anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:global.anthropic.claude-opus-4-5-20251101-v1:0', 'gateway/bedrock:meta.llama3-1-405b-instruct-v1:0', 'gateway/bedrock:meta.llama3-1-70b-instruct-v1:0', 'gateway/bedrock:meta.llama3-1-8b-instruct-v1:0', 'gateway/bedrock:meta.llama3-70b-instruct-v1:0', 'gateway/bedrock:meta.llama3-8b-instruct-v1:0', 'gateway/bedrock:mistral.mistral-7b-instruct-v0:2', 'gateway/bedrock:mistral.mistral-large-2402-v1:0', 'gateway/bedrock:mistral.mistral-large-2407-v1:0', 'gateway/bedrock:mistral.mixtral-8x7b-instruct-v0:1', 'gateway/bedrock:us.amazon.nova-lite-v1:0', 'gateway/bedrock:us.amazon.nova-micro-v1:0', 'gateway/bedrock:us.amazon.nova-pro-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-haiku-20241022-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-sonnet-20240620-v1:0', 'gateway/bedrock:us.anthropic.claude-3-5-sonnet-20241022-v2:0', 'gateway/bedrock:us.anthropic.claude-3-7-sonnet-20250219-v1:0', 'gateway/bedrock:us.anthropic.claude-3-haiku-20240307-v1:0', 'gateway/bedrock:us.anthropic.claude-3-opus-20240229-v1:0', 'gateway/bedrock:us.anthropic.claude-3-sonnet-20240229-v1:0', 'gateway/bedrock:us.anthropic.claude-haiku-4-5-20251001-v1:0', 'gateway/bedrock:us.anthropic.claude-opus-4-20250514-v1:0', 'gateway/bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0', 'gateway/bedrock:us.anthropic.claude-sonnet-4-5-20250929-v1:0', 'gateway/bedrock:us.meta.llama3-1-70b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-1-8b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-11b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-1b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-3b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-2-90b-instruct-v1:0', 'gateway/bedrock:us.meta.llama3-3-70b-instruct-v1:0', 'gateway/google-vertex:gemini-2.0-flash', 'gateway/google-vertex:gemini-2.0-flash-lite', 'gateway/google-vertex:gemini-2.5-flash', 'gateway/google-vertex:gemini-2.5-flash-image', 'gateway/google-vertex:gemini-2.5-flash-lite', 'gateway/google-vertex:gemini-2.5-flash-lite-preview-09-2025', 'gateway/google-vertex:gemini-2.5-flash-preview-09-2025', 'gateway/google-vertex:gemini-2.5-pro', 'gateway/google-vertex:gemini-3-pro-image-preview', 'gateway/google-vertex:gemini-3-pro-preview', 'gateway/google-vertex:gemini-flash-latest', 'gateway/google-vertex:gemini-flash-lite-latest', 'gateway/groq:deepseek-r1-distill-llama-70b', 'gateway/groq:deepseek-r1-distill-qwen-32b', 'gateway/groq:distil-whisper-large-v3-en', 'gateway/groq:gemma2-9b-it', 'gateway/groq:llama-3.1-8b-instant', 'gateway/groq:llama-3.2-11b-vision-preview', 'gateway/groq:llama-3.2-1b-preview', 'gateway/groq:llama-3.2-3b-preview', 'gateway/groq:llama-3.2-90b-vision-preview', 'gateway/groq:llama-3.3-70b-specdec', 'gateway/groq:llama-3.3-70b-versatile', 'gateway/groq:llama-guard-3-8b', 'gateway/groq:llama3-70b-8192', 'gateway/groq:llama3-8b-8192', 'gateway/groq:mistral-saba-24b', 'gateway/groq:moonshotai/kimi-k2-instruct', 'gateway/groq:playai-tts', 'gateway/groq:playai-tts-arabic', 'gateway/groq:qwen-2.5-32b', 'gateway/groq:qwen-2.5-coder-32b', 'gateway/groq:qwen-qwq-32b', 'gateway/groq:whisper-large-v3', 'gateway/groq:whisper-large-v3-turbo', 'gateway/openai:chatgpt-4o-latest', 'gateway/openai:codex-mini-latest', 'gateway/openai:computer-use-preview', 'gateway/openai:computer-use-preview-2025-03-11', 'gateway/openai:gpt-3.5-turbo', 'gateway/openai:gpt-3.5-turbo-0125', 'gateway/openai:gpt-3.5-turbo-0301', 'gateway/openai:gpt-3.5-turbo-0613', 'gateway/openai:gpt-3.5-turbo-1106', 'gateway/openai:gpt-3.5-turbo-16k', 'gateway/openai:gpt-3.5-turbo-16k-0613', 'gateway/openai:gpt-4', 'gateway/openai:gpt-4-0125-preview', 'gateway/openai:gpt-4-0314', 'gateway/openai:gpt-4-0613', 'gateway/openai:gpt-4-1106-preview', 'gateway/openai:gpt-4-32k', 'gateway/openai:gpt-4-32k-0314', 'gateway/openai:gpt-4-32k-0613', 'gateway/openai:gpt-4-turbo', 'gateway/openai:gpt-4-turbo-2024-04-09', 'gateway/openai:gpt-4-turbo-preview', 'gateway/openai:gpt-4-vision-preview', 'gateway/openai:gpt-4.1', 'gateway/openai:gpt-4.1-2025-04-14', 'gateway/openai:gpt-4.1-mini', 'gateway/openai:gpt-4.1-mini-2025-04-14', 'gateway/openai:gpt-4.1-nano', 'gateway/openai:gpt-4.1-nano-2025-04-14', 'gateway/openai:gpt-4o', 'gateway/openai:gpt-4o-2024-05-13', 'gateway/openai:gpt-4o-2024-08-06', 'gateway/openai:gpt-4o-2024-11-20', 'gateway/openai:gpt-4o-audio-preview', 'gateway/openai:gpt-4o-audio-preview-2024-10-01', 'gateway/openai:gpt-4o-audio-preview-2024-12-17', 'gateway/openai:gpt-4o-audio-preview-2025-06-03', 'gateway/openai:gpt-4o-mini', 'gateway/openai:gpt-4o-mini-2024-07-18', 'gateway/openai:gpt-4o-mini-audio-preview', 'gateway/openai:gpt-4o-mini-audio-preview-2024-12-17', 'gateway/openai:gpt-4o-mini-search-preview', 'gateway/openai:gpt-4o-mini-search-preview-2025-03-11', 'gateway/openai:gpt-4o-search-preview', 'gateway/openai:gpt-4o-search-preview-2025-03-11', 'gateway/openai:gpt-5', 'gateway/openai:gpt-5-2025-08-07', 'gateway/openai:gpt-5-chat-latest', 'gateway/openai:gpt-5-codex', 'gateway/openai:gpt-5-mini', 'gateway/openai:gpt-5-mini-2025-08-07', 'gateway/openai:gpt-5-nano', 'gateway/openai:gpt-5-nano-2025-08-07', 'gateway/openai:gpt-5-pro', 'gateway/openai:gpt-5-pro-2025-10-06', 'gateway/openai:gpt-5.1', 'gateway/openai:gpt-5.1-2025-11-13', 'gateway/openai:gpt-5.1-chat-latest', 'gateway/openai:gpt-5.1-codex', 'gateway/openai:gpt-5.1-mini', 'gateway/openai:o1', 'gateway/openai:o1-2024-12-17', 'gateway/openai:o1-mini', 'gateway/openai:o1-mini-2024-09-12', 'gateway/openai:o1-preview', 'gateway/openai:o1-preview-2024-09-12', 'gateway/openai:o1-pro', 'gateway/openai:o1-pro-2025-03-19', 'gateway/openai:o3', 'gateway/openai:o3-2025-04-16', 'gateway/openai:o3-deep-research', 'gateway/openai:o3-deep-research-2025-06-26', 'gateway/openai:o3-mini', 'gateway/openai:o3-mini-2025-01-31', 'gateway/openai:o3-pro', 'gateway/openai:o3-pro-2025-06-10', 'gateway/openai:o4-mini', 'gateway/openai:o4-mini-2025-04-16', 'gateway/openai:o4-mini-deep-research', 'gateway/openai:o4-mini-deep-research-2025-06-26', 'google-gla:gemini-flash-latest', 'google-gla:gemini-flash-lite-latest', 'google-gla:gemini-2.0-flash', 'google-gla:gemini-2.0-flash-lite', 'google-gla:gemini-2.5-flash', 'google-gla:gemini-2.5-flash-preview-09-2025', 'google-gla:gemini-2.5-flash-image', 'google-gla:gemini-2.5-flash-lite', 'google-gla:gemini-2.5-flash-lite-preview-09-2025', 'google-gla:gemini-2.5-pro', 'google-gla:gemini-3-pro-preview', 'google-gla:gemini-3-pro-image-preview', 'google-vertex:gemini-flash-latest', 'google-vertex:gemini-flash-lite-latest', 'google-vertex:gemini-2.0-flash', 'google-vertex:gemini-2.0-flash-lite', 'google-vertex:gemini-2.5-flash', 'google-vertex:gemini-2.5-flash-preview-09-2025', 'google-vertex:gemini-2.5-flash-image', 'google-vertex:gemini-2.5-flash-lite', 'google-vertex:gemini-2.5-flash-lite-preview-09-2025', 'google-vertex:gemini-2.5-pro', 'google-vertex:gemini-3-pro-preview', 'google-vertex:gemini-3-pro-image-preview', 'grok:grok-2-image-1212', 'grok:grok-2-vision-1212', 'grok:grok-3', 'grok:grok-3-fast', 'grok:grok-3-mini', 'grok:grok-3-mini-fast', 'grok:grok-4', 'grok:grok-4-0709', 'grok:grok-4-fast', 'grok:grok-4-fast-reasoning', 'grok:grok-4-fast-non-reasoning', 'grok:grok-code-fast-1', 'grok:grok-4-1-fast', 'grok:grok-4-1-fast-reasoning', 'grok:grok-4-1-fast-non-reasoning', 'groq:deepseek-r1-distill-llama-70b', 'groq:deepseek-r1-distill-qwen-32b', 'groq:distil-whisper-large-v3-en', 'groq:gemma2-9b-it', 'groq:llama-3.1-8b-instant', 'groq:llama-3.2-11b-vision-preview', 'groq:llama-3.2-1b-preview', 'groq:llama-3.2-3b-preview', 'groq:llama-3.2-90b-vision-preview', 'groq:llama-3.3-70b-specdec', 'groq:llama-3.3-70b-versatile', 'groq:llama-guard-3-8b', 'groq:llama3-70b-8192', 'groq:llama3-8b-8192', 'groq:mistral-saba-24b', 'groq:moonshotai/kimi-k2-instruct', 'groq:playai-tts', 'groq:playai-tts-arabic', 'groq:qwen-2.5-32b', 'groq:qwen-2.5-coder-32b', 'groq:qwen-qwq-32b', 'groq:whisper-large-v3', 'groq:whisper-large-v3-turbo', 'heroku:amazon-rerank-1-0', 'heroku:claude-3-5-haiku', 'heroku:claude-3-5-sonnet-latest', 'heroku:claude-3-7-sonnet', 'heroku:claude-3-haiku', 'heroku:claude-4-5-haiku', 'heroku:claude-4-5-sonnet', 'heroku:claude-4-sonnet', 'heroku:cohere-rerank-3-5', 'heroku:gpt-oss-120b', 'heroku:nova-lite', 'heroku:nova-pro', 'huggingface:Qwen/QwQ-32B', 'huggingface:Qwen/Qwen2.5-72B-Instruct', 'huggingface:Qwen/Qwen3-235B-A22B', 'huggingface:Qwen/Qwen3-32B', 'huggingface:deepseek-ai/DeepSeek-R1', 'huggingface:meta-llama/Llama-3.3-70B-Instruct', 'huggingface:meta-llama/Llama-4-Maverick-17B-128E-Instruct', 'huggingface:meta-llama/Llama-4-Scout-17B-16E-Instruct', 'mistral:codestral-latest', 'mistral:mistral-large-latest', 'mistral:mistral-moderation-latest', 'mistral:mistral-small-latest', 'moonshotai:kimi-k2-0711-preview', 'moonshotai:kimi-latest', 'moonshotai:kimi-thinking-preview', 'moonshotai:moonshot-v1-128k', 'moonshotai:moonshot-v1-128k-vision-preview', 'moonshotai:moonshot-v1-32k', 'moonshotai:moonshot-v1-32k-vision-preview', 'moonshotai:moonshot-v1-8k', 'moonshotai:moonshot-v1-8k-vision-preview', 'openai:chatgpt-4o-latest', 'openai:codex-mini-latest', 'openai:computer-use-preview', 'openai:computer-use-preview-2025-03-11', 'openai:gpt-3.5-turbo', 'openai:gpt-3.5-turbo-0125', 'openai:gpt-3.5-turbo-0301', 'openai:gpt-3.5-turbo-0613', 'openai:gpt-3.5-turbo-1106', 'openai:gpt-3.5-turbo-16k', 'openai:gpt-3.5-turbo-16k-0613', 'openai:gpt-4', 'openai:gpt-4-0125-preview', 'openai:gpt-4-0314', 'openai:gpt-4-0613', 'openai:gpt-4-1106-preview', 'openai:gpt-4-32k', 'openai:gpt-4-32k-0314', 'openai:gpt-4-32k-0613', 'openai:gpt-4-turbo', 'openai:gpt-4-turbo-2024-04-09', 'openai:gpt-4-turbo-preview', 'openai:gpt-4-vision-preview', 'openai:gpt-4.1', 'openai:gpt-4.1-2025-04-14', 'openai:gpt-4.1-mini', 'openai:gpt-4.1-mini-2025-04-14', 'openai:gpt-4.1-nano', 'openai:gpt-4.1-nano-2025-04-14', 'openai:gpt-4o', 'openai:gpt-4o-2024-05-13', 'openai:gpt-4o-2024-08-06', 'openai:gpt-4o-2024-11-20', 'openai:gpt-4o-audio-preview', 'openai:gpt-4o-audio-preview-2024-10-01', 'openai:gpt-4o-audio-preview-2024-12-17', 'openai:gpt-4o-audio-preview-2025-06-03', 'openai:gpt-4o-mini', 'openai:gpt-4o-mini-2024-07-18', 'openai:gpt-4o-mini-audio-preview', 'openai:gpt-4o-mini-audio-preview-2024-12-17', 'openai:gpt-4o-mini-search-preview', 'openai:gpt-4o-mini-search-preview-2025-03-11', 'openai:gpt-4o-search-preview', 'openai:gpt-4o-search-preview-2025-03-11', 'openai:gpt-5', 'openai:gpt-5-2025-08-07', 'openai:gpt-5-chat-latest', 'openai:gpt-5-codex', 'openai:gpt-5-mini', 'openai:gpt-5-mini-2025-08-07', 'openai:gpt-5-nano', 'openai:gpt-5-nano-2025-08-07', 'openai:gpt-5-pro', 'openai:gpt-5-pro-2025-10-06', 'openai:gpt-5.1', 'openai:gpt-5.1-2025-11-13', 'openai:gpt-5.1-chat-latest', 'openai:gpt-5.1-codex', 'openai:gpt-5.1-mini', 'openai:o1', 'openai:o1-2024-12-17', 'openai:o1-mini', 'openai:o1-mini-2024-09-12', 'openai:o1-preview', 'openai:o1-preview-2024-09-12', 'openai:o1-pro', 'openai:o1-pro-2025-03-19', 'openai:o3', 'openai:o3-2025-04-16', 'openai:o3-deep-research', 'openai:o3-deep-research-2025-06-26', 'openai:o3-mini', 'openai:o3-mini-2025-01-31', 'openai:o3-pro', 'openai:o3-pro-2025-06-10', 'openai:o4-mini', 'openai:o4-mini-2025-04-16', 'openai:o4-mini-deep-research', 'openai:o4-mini-deep-research-2025-06-26', 'test'] | Model | str | None = ..., instructions: str | Callable[[RunContext[None]], str] | Callable[[RunContext[None]], Awaitable[str]] | Callable[[], str] | Callable[[], Awaitable[str]] | Sequence[str | Callable[[RunContext[None]], str] | Callable[[RunContext[None]], Awaitable[str]] | Callable[[], str] | Callable[[], Awaitable[str]]] | None = ..., deps: None = ..., model_settings: ModelSettings | None = ..., usage_limits: UsageLimits | None = ..., usage: RunUsage | None = ..., infer_name: bool = ..., toolsets: Sequence[AbstractToolset[None]] | None = ..., builtin_tools: Sequence[AbstractBuiltinTool | Callable[[RunContext[None]], Awaitable[AbstractBuiltinTool | None] | AbstractBuiltinTool | None]] | None = ..., event_stream_handler: Callable[[RunContext[None], AsyncIterable[PartStartEvent | PartDeltaEvent | PartEndEvent | FinalResultEvent | FunctionToolCallEvent | FunctionToolResultEvent | BuiltinToolCallEvent | BuiltinToolResultEvent]], Awaitable[None]] | None = ...) -> Coroutine[Any, Any, AgentRunResult[RunOutputDataT]]
nexus/api/wizard_chat.py:725: error: Argument after ** must be a mapping, not "dict[str, Any] | None"  [arg-type]
nexus/api/wizard_chat.py:812: error: Argument 3 to "_artifact_response" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:825: error: "str" has no attribute "choices"  [attr-defined]
nexus/api/wizard_chat.py:828: error: "str" has no attribute "message"  [attr-defined]
nexus/api/wizard_chat.py:834: error: Argument "thread_id" to "_record_text_reply" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:835: error: "str" has no attribute "message"  [attr-defined]
nexus/api/wizard_chat.py:842: error: "str" has no attribute "message"  [attr-defined]
nexus/api/wizard_chat.py:887: error: Incompatible types in assignment (expression has type "str", variable has type "Literal['setting', 'character', 'seed'] | None")  [assignment]
nexus/api/wizard_chat.py:947: error: Argument "model" to "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:948: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:977: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:979: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:980: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:984: error: Argument 1 to "add_message" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:987: error: Argument 1 to "list_messages" of "ConversationsClient" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:996: error: Argument "thread_id" to "from_request" of "WizardContext" has incompatible type "str | None"; expected "str"  [arg-type]
nexus/api/wizard_chat.py:1006: error: Argument 1 to "build_message_history" has incompatible type "list[Message]"; expected "Sequence[dict[str, Any]]"  [arg-type]
Found 34 errors in 1 file (checked 2 source files)
```

## Existing Static-Check Failures

No new test-file diagnostics remain. The untouched base `wizard_chat.py` was extracted with `git show 5b977eab:nexus/api/wizard_chat.py` into the order scratchpad, then checked with the same flake8/mypy commands. Flake8 base: 18 diagnostics; final: 16, all pre-existing source lines. Two log strings in the changed streaming branches were wrapped without changing their values. Mypy base and final: the same 34 errors; diagnostic-message multisets match after removing filename/line prefixes. No unrelated cleanup or suppression was added to product code.

Exact baseline commands (working directory remains this worktree):

```sh
$PY -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/840-S3a/wizard_chat.py
$PY -m mypy /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/840-S3a/wizard_chat.py
```

Earlier new-file diagnostics were corrected before the final proof. The initial formatting command was `$PY -m black nexus/api/wizard_chat.py tests/test_api/test_set_designer_failure.py`, which reported `2 files reformatted.` Subsequent formatting reported `2 files left unchanged.` All initial and final checker logs remain in the scratchpad.

## Coordinator Handoff

No migration, fleet application, configuration, prompt, client, script path or UI rebuild. After landing, the coordinator restarts the owner gateway by name with `nexus restart gateway`; the implementer did not run that command. Leave #840 open. No merge or review-bot wait is part of this run.

Open questions: none for this frozen slice. #1081 retains its separate remove-or-repair decision. The documented existing flake8/mypy debt remains for coordinator triage; no new diagnostics were introduced.

Implemented by Codex (GPT-6 Astra).
