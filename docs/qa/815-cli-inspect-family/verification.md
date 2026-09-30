# CLI Session Waiter and Inspect Family: Verification

Work order 815-A. Issue #815. Base: `origin/main` at 696ccf29. No migration. Gateway lane 8017, TEST provider only, no paid calls.

**Write safety.** The PostgreSQL proof writes only a disposable `qa640_815_inspect_*` clone created and dropped by `tests.pg_fixtures.disposable_slot_database`; slot 4 is routed to the clone in process (`tests.scheduler_helpers.route_slot`). No `save_NN` or `NEXUS_template` was written. No `qa640_815*` database remains after the runs (`psql -d postgres -Atc "select datname from pg_database where datname like 'qa640_815%'"` printed nothing).

## What Changed

- `nexus/cli.py`: `wait_for_session(session_id, *, slot, timeout, interval)` is the one waiter. `_wait_for_narrative_result` composes it with the slot-state load and serves `continue`, `retry`, `regenerate`, and the seed's opening turn. `regenerate`'s own loop is deleted.
- `nexus/cli.py`: `nexus inspect chunks|chunk|incubator|characters|places|factions`, each reading player-plane GET routes and putting each route's own payload, unchanged, under `data` (`inspect chunks` lists them oldest first; `inspect incubator` reports the empty answer as `null`).
- `nexus/cli_contract.py`: the six verbs are `http` transport and `ENVELOPE_COMMANDS`; the docstring states how a saved-work failure reports a lost gateway.
- `nexus/config/settings_models.py`, `nexus.toml`: `[runtime.cli] poll_interval_seconds = 1.0`.
- `docs/cli.md`: the inspect table and a Waiting on a Generation section.

## Session-Wait Contract

1. Reads `GET /api/narrative/status/{id}?slot=N` every `[runtime.cli].poll_interval_seconds`, within `[apex].generation_timeout_seconds` overall; returns the terminal status payload.
2. `status: "error"` from the API: domain failure (exit 1) whose `error` is the API's message.
3. Budget spent while the session runs, a read that times out (the status read or the slot-state read after it), an HTTP error answer or any other failed request (too many redirects, an undecodable body), or an unusable payload: domain failure (exit 1).
4. Connection refused or dropped mid-wait, a body cut off mid-answer included: `api_unreachable` (exit 4). A failed read is never retried.
5. Every failed wait keeps `session_id`, `generation_error`, and `recovery_command` (and the saved seed) in `partial`.

## Review Fix Round

- `wait_for_session` and the slot-state load after it map every other `requests` failure (for example `TooManyRedirects`) to `http_error`, so it keeps the scheduled session in `partial` instead of escaping to `continue`'s broad `except` or `retry`'s traceback.
- A slot-state read or seed scheduling request that times out is a domain failure (exit 1) worded `Timed out waiting for API server at ...`, matching the status read and the saved-work rule in `docs/cli.md`. Only a refused or dropped connection is `api_unreachable` there, worded `Cannot connect to API server at ...`.
- `main()` and `_TRANSPORT_ERRORS` treat `ChunkedEncodingError` (a body cut off mid-answer) like `ConnectionError`, so every inspect verb exits 4 with `api_unreachable`.
- Human `inspect` output prints `_INSPECT_EMPTY[verb]` directly; the unreachable `"Nothing to show."` default is gone. The help epilog's incubator example has its two-space column gap.
- New tests: a self-redirecting status route (in process, and `continue`/`regenerate` keeping the partial, exit 1); a dropped and a stalled slot-state read (`continue`, exit 4 and exit 1); `continue`/`regenerate` polling at a configured 0.3s interval; the seed's opening turn losing the gateway on the schedule POST and on the second status read (exit 4, seed kept in `partial`); every inspect verb with a truncated body (exit 4); every inspect verb with `--slot 9` and with no `--slot` (exit 2, no request); non-integer `places`/`factions` ids; and the PostgreSQL proof reads the real gateway's empty incubator as `null` before the pending turn is staged.

## Second Review Fix Round

- `inspect chunks --from A` without `--to` is now a usage error (exit 2, no request): `--from needs --to, so a range cannot walk the whole story`. `--to B` alone still starts at the first chunk. `docs/cli.md` and the `--last`/`--from` help state the cost: one sequential request per chunk. No cap was added.
- `docs/cli.md` now says `wait_for_session` returns the terminal status, that `[apex].generation_timeout_seconds` bounds the status polling only, and that `_wait_for_narrative_result` then loads the turn from `/api/slot/{slot}/state` under `[runtime.cli].request_timeout_seconds`.
- `docs/cli.md` and the `run_inspect` docstring now say each record is the route's own payload, unchanged; `inspect chunks` lists them oldest first and `inspect incubator` reports the empty answer as `null`.
- `SessionWaitFailure.__init__` is annotated `-> None`.
- The base commit above is corrected to the branch's real merge base, and the transcript below is one run at this branch's head.

## Astra Review Fixes

The independent review of `adb4843e` (GPT-6 Astra, `CHANGES_REQUIRED`) raised three findings; this round fixes those three and nothing else, in `c62f6ba3` (finding 1), `d69884d9` (finding 2), and `614d91e5` (finding 3). The gates below ran on the tree those commits produce. Each new test was written first and failed on the unfixed code.

- **[P2] A body stalled after its headers was reported as a lost gateway.** Requests 2.32.3 raises `ReadTimeout` when the headers do not arrive in time, but reports a body that stalls after them as a `requests.exceptions.ConnectionError` wrapping urllib3's `ReadTimeoutError` (not a `Timeout`; its `__cause__` is `None` and the urllib3 error is its wrapped argument), so `wait_for_session` and `_load_session_result` exited 4 with `api_unreachable`. Both reads now classify a failed request through one helper, `_failed_session_read`: a read timeout in the cause chain (`_is_read_timeout`) is `timeout`, a domain failure (exit 1) that keeps the partial; a refused or dropped connection, a body cut off mid-answer included, stays `unreachable` (exit 4); any other failed request stays `http_error`. Error messages are unchanged. The walk follows only causes (exception arguments and `__cause__`), never `__context__`: with `__context__` followed, a gone gateway reached while a caller handles a `ReadTimeout` was classified as a timeout (probe below). `docs/cli.md` now says a read that times out before its headers arrive or while its body stalls after them is exit 1.
- **[P2] `poll_interval_seconds` accepted infinity.** `RuntimeCliSettings.poll_interval_seconds` adds `allow_inf_nan=False` to `gt=0`: the Pydantic form of `math.isfinite(value) and value > 0`, as the repository's other finite floats in `settings_models.py` declare it. `inf` and `nan` fail with `finite_number` and `0` and `-1.0` with `greater_than`, each located at `runtime.cli.poll_interval_seconds` (`poll_interval_seconds` on the bare model). The `nexus.toml` comment and the field description state the constraint.
- **[P3] The range walk requested one chunk past `--to`.** `inspect chunks --from/--to` stops at the chunk with id `--to`, so `--from 10 --to 11` sends exactly two requests and a failing read of chunk 11's neighbours can no longer discard the complete range. A range sends one more request only when no committed chunk has id `--to`, to find where it ends; `docs/cli.md`, the `--from` help, and the `_inspect_chunks` docstring say so.
- New tests: a status answer stalled after its headers, in process (`timeout`, `domain_failure`, the cause a wrapped `ConnectionError`, not retried); `continue` against a status read and a slot-state read that each stall after their headers (exit 1, `generation_error.status` `timeout`, `session_id` and `recovery_command` kept); a gone gateway reached while a `ReadTimeout` is being handled (still `unreachable`); `inf`, `nan`, `0`, and `-1.0` rejected by `RuntimeCliSettings`, by `Settings`, and by `load_settings` of a TOML file; `--from 10 --to 11` with chunk 11's adjacent route answering 500 (exit 0, both chunks, exactly two requests); and a `--from 11 --to 13` case pinning the extra request when chunk `--to` does not exist. The `chunks-range` and `chunks-first-to` cases now expect two requests, not three. The existing before-headers slot-state stall test is unchanged and green.

Before the fixes (tests written first, run on the unfixed code):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_cli_session_wait.py -k "stalled_after_its_headers"
E       AssertionError: {
E           "code": "api_unreachable",
E           "error": "Cannot connect to API server at http://127.0.0.1:56406: HTTPConnectionPool(host='127.0.0.1', port=56406): Read timed out.",
E           "ok": false,
E           "partial": {
E             "generation_error": {
E               "detail": "Cannot connect to API server at http://127.0.0.1:56406: HTTPConnectionPool(host='127.0.0.1', port=56406): Read timed out.",
E               "status": "unreachable"
E             },
E             "recovery_command": "nexus load --slot 5",
E             "session_id": "815-wait-session"
E           }
E         }
E
E       assert 4 == <ExitCode.DOMAIN_FAILURE: 1>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_cli_session_wait.py::test_wait_reports_a_status_answer_stalled_after_its_headers_as_a_timeout
FAILED tests/test_cli_session_wait.py::test_continue_reports_an_answer_stalled_after_its_headers_as_a_domain_failure[status]
FAILED tests/test_cli_session_wait.py::test_continue_reports_an_answer_stalled_after_its_headers_as_a_domain_failure[state]
3 failed, 20 deselected in 5.01s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/config/test_settings_models.py -k "poll_interval"
>       with pytest.raises(ValidationError) as direct:
E       Failed: DID NOT RAISE <class 'pydantic_core._pydantic_core.ValidationError'>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/config/test_settings_models.py::test_cli_poll_interval_must_be_finite_and_positive[inf]
1 failed, 3 passed, 81 deselected in 0.72s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_cli_contract.py -k "inspect_verb_prints or no_request_past or read_only_player_plane"
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_cli_contract.py::test_inspect_verb_prints_the_route_body_in_the_envelope[chunks-first-to]
FAILED tests/test_cli_contract.py::test_inspect_verb_prints_the_route_body_in_the_envelope[chunks-range]
FAILED tests/test_cli_contract.py::test_inspect_chunk_range_sends_no_request_past_its_last_chunk
3 failed, 12 passed, 105 deselected in 19.04s
```

On the unfixed walk, the range with a failing read past `--to` discarded both chunks:

```
E       AssertionError: {
E           "code": "api_error",
E           "error": "http://127.0.0.1:56798/api/narrative/chunks/11/adjacent returned HTTP 500: {\"detail\": \"Internal Server Error\"}",
E           "ok": false,
E           "partial": {
E             "slot": 5,
E             "status_code": 500
E           }
E         }
E
E       assert 1 == <ExitCode.OK: 0>
```

Why the walk skips `__context__`: a scratch probe outside the repository (`context_probe.py`; the new test is its reproducible form) calls `wait_for_session` against a closed loopback port, once plainly and once inside an `except requests.exceptions.ReadTimeout` block. With `__context__` followed, the second call was misclassified; with causes only (as shipped) it is not. With `__context__` added back to the walk, `test_wait_keeps_a_gone_gateway_unreachable_while_a_read_timeout_is_handled` fails (`1 failed, 23 deselected in 0.30s`).

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_RUNTIME_CONFIG -u NEXUS_HOME PYTHONPATH=$PWD $PY context_probe.py   # __context__ followed
  cause: ConnectionError | args[0]: MaxRetryError
plain call: unreachable
  cause: ConnectionError | args[0]: MaxRetryError
inside a handled ReadTimeout: timeout
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_RUNTIME_CONFIG -u NEXUS_HOME PYTHONPATH=$PWD $PY context_probe.py   # causes only
  cause: ConnectionError | args[0]: MaxRetryError
plain call: unreachable
  cause: ConnectionError | args[0]: MaxRetryError
inside a handled ReadTimeout: unreachable
```

The validation messages after the fix:

```
inf -> poll_interval_seconds | finite_number | Input should be a finite number
nan -> poll_interval_seconds | finite_number | Input should be a finite number
0 -> poll_interval_seconds | greater_than | Input should be greater than 0
-1.0 -> poll_interval_seconds | greater_than | Input should be greater than 0
1.0 -> 1.0
```

Gates after the fixes, from the worktree root with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset (`PYTHONPATH=$PWD $PY -c 'import nexus;print(nexus.__file__)'` printed the worktree's `nexus/__init__.py`):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD $PY -m pytest -q tests/test_cli_contract.py tests/test_cli_session_wait.py tests/config/test_settings_models.py tests/test_cli.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
300 passed, 5 warnings in 110.54s (0:01:50)
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_cli_inspect_pg.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 passed, 9 warnings in 18.01s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_cli_generation_http.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
89 passed in 92.19s (0:01:32)
$ NEXUS_GATEWAY_PORT=8017 NEXUS_API_URL=http://127.0.0.1:8017 PYTHONPATH=$PWD $PY -m nexus.cli down
nothing running
$ lsof -nP -iTCP:8017 -sTCP:LISTEN; echo $?
1
$ psql -d postgres -Atc "select datname from pg_database where datname like 'qa640_815%'"
$ $PY -m black --check nexus/cli.py nexus/config/settings_models.py tests/test_cli_session_wait.py tests/test_cli_contract.py tests/config/test_settings_models.py
All done! ✨ 🍰 ✨
5 files would be left unchanged.
$ $PY -m flake8 tests/test_cli_session_wait.py tests/test_cli_contract.py tests/config/test_settings_models.py; echo $?
0
$ $PY -m mypy nexus/cli.py tests/test_cli_session_wait.py tests/test_cli_contract.py tests/config/test_settings_models.py
Success: no issues found in 4 source files
```

`flake8 nexus/cli.py` still reports the 9 E501 lines and `flake8 nexus/config/settings_models.py` the 6 it reported at `adb4843e`, none in a changed line; `mypy nexus/config/settings_models.py` reports the same 7 pre-existing errors.

Two follow-ups the coordinator added to this round, in `b9cf6f0a` (the seed's scheduling POST) and `22f54d73` (the `--to` help):

- **The seed's opening-turn POST had the same stall bug.** `_bootstrap_seed_narrative` split `ConnectionError` from `Timeout` itself, so a `POST /api/narrative/continue` answer that stalled after its headers exited 4 with `api_unreachable`, where the saved-work rule in `docs/cli.md` makes a late answer a domain failure. Its transport failures (`ConnectionError`, `ChunkedEncodingError`, `Timeout`) now go through `_failed_session_read`. A stall is `Timed out waiting for API server at ...` (exit 1) with the saved seed in `partial`. A refused or dropped connection stays `api_unreachable` (exit 4; the existing `schedule_drop` test is unchanged and green). An HTTP error answer or an unreadable body keeps its message. The POST's budget was a literal 120 s, so a subprocess test would wait two minutes. The function now takes it as `schedule_timeout`, defaulting to the same 120, so behavior is unchanged. The new in-process test passes 0.5 s against a real loopback gateway that sends the headers and half the body, then holds the rest. It asserts what `main()` reports from the result: `domain_failure` (exit 1), the exact error, and the exact `partial` (artifact, Retrograde outcome, `narrative_bootstrap: false`, `bootstrap_error`, `recovery_command`, no session).
- **The `--to` help stated a default that no longer exists.** It said `(default: the latest chunk)`, stale since `--from` without `--to` became a usage error. It now states the rule. `docs/cli.md` already stated the rule and never repeated the default.

Before the fix (test written first, run on the unfixed classification). The assertion that failed was `('api_unreach...REACHABLE: 4>) == ('domain_fail...N_FAILURE: 1>)`, `At index 0 diff: 'api_unreachable' != 'domain_failure'`:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_cli_generation_http.py -k "schedule_stalled"
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_cli_generation_http.py::test_seed_bootstrap_schedule_stalled_after_headers_keeps_the_seed
1 failed, 51 deselected in 1.27s
```

After both follow-ups:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD $PY -m pytest -q tests/test_cli_session_wait.py tests/test_cli_contract.py tests/test_cli.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
215 passed, 5 warnings in 106.76s (0:01:46)
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings tests/test_new_story_cli.py tests/test_cli_generation_http.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed in 85.64s (0:01:25)
$ PYTHONPATH=$PWD $PY -m nexus.cli inspect chunks --help | tail -5
  --from FROM_ID  First chunk id of the range (default: the first chunk);
                  needs --to. One request per chunk in the range, one more if
                  chunk --to does not exist
  --to TO_ID      Last chunk id of the range; required with --from (alone, the
                  range starts at the first chunk)
$ $PY -m black --check nexus/cli.py tests/test_cli_generation_http.py
All done! ✨ 🍰 ✨
2 files would be left unchanged.
$ $PY -m flake8 tests/test_cli_generation_http.py; echo $?
0
$ $PY -m mypy nexus/cli.py
Success: no issues found in 1 source file
$ NEXUS_GATEWAY_PORT=8017 NEXUS_API_URL=http://127.0.0.1:8017 PYTHONPATH=$PWD $PY -m nexus.cli down
nothing running
$ lsof -nP -iTCP:8017 -sTCP:LISTEN; echo $?
1
```

`mypy tests/test_cli_generation_http.py` reports the same 5 errors as at `a833224b` (the `tomlkit` config indexing in `_run_cli` and the teardown's `str-bytes-safe` line), none in an added line; `flake8 nexus/cli.py` reports the same 9 E501 lines.

## CLI Transcript on the Played Clone

`tests/test_cli_inspect_pg.py` at this branch's head, run with `-s`: `seed_played_story(turns=3, cast=("Mara Quill", "Oren Vale"))` and one seeded faction; the real gateway's empty incubator is read first, then a pending turn from `seed_pending_turn` is staged. The in-process gateway serves 127.0.0.1:8017 with every provider routed to TEST. Each command ran as a `python -m nexus.cli` subprocess. Verbatim stdout of that one run; only the in-process gateway's own output between commands (the fixture's schema load, model-load progress, retrieval logging, and tokenizer fork warnings) is removed:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -s -p no:warnings tests/test_cli_inspect_pg.py
$ nexus inspect incubator --slot 4 --json
{
  "data": null,
  "ok": true
}

$ nexus continue --slot 4 --choice 1 --json
{
  "choices": [
    "Continue following the immediate lead.",
    "Pause and reassess the pressure around the scene.",
    "Shift attention to the quieter off-screen consequence."
  ],
  "chunk_id": null,
  "message": "[TEST MODE] The scene advances under deterministic mock control. Orrery pressure is acknowledged structurally, while the prose remains simple enough for integration tests to inspect.",
  "session_id": "b907fd1b-0be6-455f-b235-6ebf38d371ad",
  "success": true
}

$ nexus inspect chunks --last 2 --slot 4 --json
{
  "data": [
    {
      "choiceObject": {
        "presented": [
          "Press on toward the lit doorway.",
          "Wait and watch the street.",
          "Ask the nearest stranger for directions."
        ],
        "selected": null
      },
      "choiceText": null,
      "createdAt": "2026-09-30T00:30:05.628630Z",
      "hasInlineSceneMarkup": false,
      "id": 3,
      "metadata": {
        "chunkId": 3,
        "episode": 1,
        "generationDate": "2026-09-30T00:30:05.637969",
        "id": 3,
        "scene": 3,
        "season": 1,
        "slug": "S01E01_003",
        "timeDelta": "02:00:00",
        "worldLayer": "primary",
        "worldTime": "2100-01-01T04:00:00+00:00",
        "worldTimeFace": "1 Jan 2100 \u00b7 04:00"
      },
      "rawText": "Fixture turn 3: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business.",
      "storytellerText": "Fixture turn 3: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business."
    },
    {
      "choiceObject": {
        "presented": [
          "Press on toward the lit doorway.",
          "Wait and watch the street.",
          "Ask the nearest stranger for directions."
        ],
        "selected": 1
      },
      "choiceText": "Press on toward the lit doorway.",
      "createdAt": "2026-09-30T00:30:07.058982Z",
      "hasInlineSceneMarkup": false,
      "id": 4,
      "metadata": {
        "chunkId": 4,
        "episode": 1,
        "generationDate": "2026-09-30T00:30:07.069209",
        "id": 4,
        "scene": 4,
        "season": 1,
        "slug": "S01E01_004",
        "timeDelta": "00:05:00",
        "worldLayer": "primary",
        "worldTime": "2100-01-01T04:05:00+00:00",
        "worldTimeFace": "1 Jan 2100 \u00b7 04:05"
      },
      "rawText": "The pending fixture turn waits for the player's choice.\n\nPress on toward the lit doorway.",
      "storytellerText": "The pending fixture turn waits for the player's choice."
    }
  ],
  "ok": true
}

$ nexus inspect chunks --from 1 --to 2 --slot 4 --json
{
  "data": [
    {
      "choiceObject": {
        "presented": [
          "Press on toward the lit doorway.",
          "Wait and watch the street.",
          "Ask the nearest stranger for directions."
        ],
        "selected": 1
      },
      "choiceText": "Press on toward the lit doorway.",
      "createdAt": "2026-09-30T00:30:05.312206Z",
      "hasInlineSceneMarkup": false,
      "id": 1,
      "metadata": {
        "chunkId": 1,
        "episode": 1,
        "generationDate": "2026-09-30T00:30:05.321403",
        "id": 1,
        "scene": 1,
        "season": 1,
        "slug": "S01E01_001",
        "timeDelta": "00:00:00",
        "worldLayer": "primary",
        "worldTime": "2100-01-01T00:00:00+00:00",
        "worldTimeFace": "1 Jan 2100 \u00b7 00:00"
      },
      "rawText": "Fixture turn 1: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business.\n\nPress on toward the lit doorway.",
      "storytellerText": "Fixture turn 1: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business."
    },
    {
      "choiceObject": {
        "presented": [
          "Press on toward the lit doorway.",
          "Wait and watch the street.",
          "Ask the nearest stranger for directions."
        ],
        "selected": 1
      },
      "choiceText": "Press on toward the lit doorway.",
      "createdAt": "2026-09-30T00:30:05.452117Z",
      "hasInlineSceneMarkup": false,
      "id": 2,
      "metadata": {
        "chunkId": 2,
        "episode": 1,
        "generationDate": "2026-09-30T00:30:05.461594",
        "id": 2,
        "scene": 2,
        "season": 1,
        "slug": "S01E01_002",
        "timeDelta": "02:00:00",
        "worldLayer": "primary",
        "worldTime": "2100-01-01T02:00:00+00:00",
        "worldTimeFace": "1 Jan 2100 \u00b7 02:00"
      },
      "rawText": "Fixture turn 2: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business.\n\nPress on toward the lit doorway.",
      "storytellerText": "Fixture turn 2: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business."
    }
  ],
  "ok": true
}

$ nexus inspect chunk 2 --slot 4 --json
{
  "data": {
    "choiceObject": {
      "presented": [
        "Press on toward the lit doorway.",
        "Wait and watch the street.",
        "Ask the nearest stranger for directions."
      ],
      "selected": 1
    },
    "choiceText": "Press on toward the lit doorway.",
    "createdAt": "2026-09-30T00:30:05.452117Z",
    "hasInlineSceneMarkup": false,
    "id": 2,
    "metadata": {
      "chunkId": 2,
      "episode": 1,
      "generationDate": "2026-09-30T00:30:05.461594",
      "id": 2,
      "scene": 2,
      "season": 1,
      "slug": "S01E01_002",
      "timeDelta": "02:00:00",
      "worldLayer": "primary",
      "worldTime": "2100-01-01T02:00:00+00:00",
      "worldTimeFace": "1 Jan 2100 \u00b7 02:00"
    },
    "rawText": "Fixture turn 2: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business.\n\nPress on toward the lit doorway.",
    "storytellerText": "Fixture turn 2: Fixture Player crosses Fixture Plaza as the evening crowd thins. Across town at Fixture Docks, Mara Quill and Oren Vale keep to their own business."
  },
  "ok": true
}

$ nexus inspect incubator --slot 4 --json
{
  "data": {
    "authorial_directives": [],
    "choice_object": {
      "presented": [
        "Continue following the immediate lead.",
        "Pause and reassess the pressure around the scene.",
        "Shift attention to the quieter off-screen consequence."
      ],
      "selected": null
    },
    "choice_text": null,
    "chunk_id": null,
    "created_at": "2026-09-30T00:30:07.178506+00:00",
    "entity_changes": {
      "characters": [],
      "factions": [],
      "locations": [],
      "relationships": []
    },
    "entity_update_count": 0,
    "episode_transition": null,
    "orrery_adjudications": [],
    "orrery_proposal": {
      "_bleed_offer_resolution_ids": [],
      "actor_count": 2,
      "ambient_scene_seeds": [],
      "anchor_chunk_id": 4,
      "epistemics_settings": {
        "aware_roles": [
          "actor",
          "observer",
          "target",
          "witness"
        ],
        "claim_event_types": [
          "compliance_alert",
          "encoded_message",
          "hunt_called_off",
          "hunt_declared",
          "informant_contact",
          "intel_acquired",
          "intel_acted_on",
          "protective_intervention",
          "pursue_romance_completed",
          "recruit_ally_completed",
          "relationship_drift_milestone",
          "retaliation_attempted",
          "retaliation_executed",
          "rival_consulted",
          "seek_redemption_completed",
          "surveillance_performed",
          "threat_issued",
          "warning_delivered"
        ],
        "enabled": true
      },
      "generated_at": "2026-09-30T00:30:12.834621+00:00",
      "joint_beats": [],
      "rendered_cards": [
        {
          "kind": "resolution",
          "proposal_id": "upkeep:a339b89d4d913c763526bd612c4b3b2b567321e0aa43e1db0523d256f4f8bd68"
        },
        {
          "kind": "resolution",
          "proposal_id": "recreate:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8"
        }
      ],
      "resolutions": [
        {
          "binding_hash": "a339b89d4d913c763526bd612c4b3b2b567321e0aa43e1db0523d256f4f8bd68",
          "binding_names": {
            "actor": "Oren Vale",
            "place": "Fixture Docks"
          },
          "bindings": {
            "actor": 5
          },
          "branch_label": "Tidy what is theirs",
          "changed_fields": [
            "character.current_activity"
          ],
          "effective_priority": 11.0,
          "evaluated_at": "2100-01-01T04:05:00+00:00",
          "event_type": "upkeep_done",
          "magnitude": 0.08,
          "narrative_stub": "Oren Vale tends whatever corner of the world is currently theirs \u2014 folding, sorting, wiping down, the small housekeeping that keeps a life from silting up.",
          "position": 0,
          "priority": 11,
          "promotable": true,
          "proposal_id": "upkeep:a339b89d4d913c763526bd612c4b3b2b567321e0aa43e1db0523d256f4f8bd68",
          "signal_event_type": null,
          "state_delta": {
            "character.current_activity": "tidying their own space"
          },
          "template_id": "upkeep"
        },
        {
          "binding_hash": "85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
          "binding_names": {
            "actor": "Mara Quill",
            "place": "Fixture Docks"
          },
          "bindings": {
            "actor": 4
          },
          "branch_label": "Watch the world go by",
          "changed_fields": [
            "character.current_activity"
          ],
          "effective_priority": 9.0,
          "evaluated_at": "2100-01-01T04:05:00+00:00",
          "event_type": "recreation_taken",
          "magnitude": 0.1,
          "narrative_stub": "Mara Quill claims a seat with a view of other people's evenings and lets the spectacle of ordinary life be the entertainment.",
          "position": 1,
          "priority": 9,
          "promotable": true,
          "proposal_id": "recreate:85dcc9f3819171e3e0ba0de152d371151c3b51cc44f39eb6803227245e505db8",
          "signal_event_type": null,
          "state_delta": {
            "character.current_activity": "watching the world go by"
          },
          "template_id": "recreate"
        }
      ],
      "scene_conditions": {
        "time_of_day": "night",
        "weather": "clear"
      },
      "scene_pressures": []
    },
    "pacing": null,
    "parent_chunk_id": 4,
    "parent_chunk_text": "The pending fixture turn waits for the player's choice.\n\nPress on toward the lit doorway.",
    "references": {
      "characters": [
        {
          "character_id": 1,
          "character_name": "Fixture Player",
          "reference_type": "present"
        }
      ],
      "factions": [],
      "places": [
        {
          "place_id": 1,
          "place_name": "Fixture Plaza",
          "reference_type": "setting"
        }
      ]
    },
    "session_id": "b907fd1b-0be6-455f-b235-6ebf38d371ad",
    "status": "provisional",
    "storyteller_text": "[TEST MODE] The scene advances under deterministic mock control. Orrery pressure is acknowledged structurally, while the prose remains simple enough for integration tests to inspect.",
    "time_delta": null,
    "user_text": "Press on toward the lit doorway.",
    "world_layer": "primary"
  },
  "ok": true
}

$ nexus inspect characters --slot 4 --json
{
  "data": [
    {
      "appearance": null,
      "background": "unknown",
      "createdAt": "2026-09-30T00:30:05.137258Z",
      "currentActivity": null,
      "currentLocation": "1",
      "currentLocationName": "Fixture Plaza",
      "emotionalState": null,
      "extraData": null,
      "id": 1,
      "name": "Fixture Player",
      "personality": null,
      "portraitPath": null,
      "summary": "Canonical player for PostgreSQL coverage.",
      "updatedAt": "2026-09-30T00:30:05.137258Z"
    },
    {
      "appearance": null,
      "background": "unknown",
      "createdAt": "2026-09-30T00:30:05.196946Z",
      "currentActivity": "tidying their own space",
      "currentLocation": "2",
      "currentLocationName": "Fixture Docks",
      "emotionalState": null,
      "extraData": null,
      "id": 2,
      "name": "Mara Quill",
      "personality": null,
      "portraitPath": null,
      "summary": "Mara Quill works the night shift at Fixture Docks.",
      "updatedAt": "2026-09-30T00:30:07.058982Z"
    },
    {
      "appearance": null,
      "background": "unknown",
      "createdAt": "2026-09-30T00:30:05.218489Z",
      "currentActivity": "watching the world go by",
      "currentLocation": "2",
      "currentLocationName": "Fixture Docks",
      "emotionalState": null,
      "extraData": null,
      "id": 3,
      "name": "Oren Vale",
      "personality": null,
      "portraitPath": null,
      "summary": "Oren Vale works the night shift at Fixture Docks.",
      "updatedAt": "2026-09-30T00:30:07.058982Z"
    }
  ],
  "ok": true
}

$ nexus inspect characters 2 --slot 4 --json
{
  "data": {
    "appearance": null,
    "background": "unknown",
    "createdAt": "2026-09-30T00:30:05.196946Z",
    "currentActivity": "tidying their own space",
    "currentLocation": "2",
    "currentLocationName": "Fixture Docks",
    "emotionalState": null,
    "extraData": null,
    "id": 2,
    "name": "Mara Quill",
    "personality": null,
    "portraitPath": null,
    "summary": "Mara Quill works the night shift at Fixture Docks.",
    "updatedAt": "2026-09-30T00:30:07.058982Z"
  },
  "ok": true
}

$ nexus inspect places --slot 4 --json
{
  "data": [
    {
      "createdAt": "2026-09-30T00:30:05.102111Z",
      "currentStatus": null,
      "extraData": null,
      "geometry": {
        "coordinates": [
          -73.9857,
          40.7484,
          0
        ],
        "type": "Point"
      },
      "history": null,
      "id": 1,
      "inhabitants": null,
      "name": "Fixture Plaza",
      "summary": "Fixture place.",
      "type": "fixed_location",
      "updatedAt": "2026-09-30T00:30:05.102111Z",
      "zone": 1
    },
    {
      "createdAt": "2026-09-30T00:30:05.162666Z",
      "currentStatus": null,
      "extraData": null,
      "geometry": {
        "coordinates": [
          -74,
          40.7,
          0
        ],
        "type": "Point"
      },
      "history": null,
      "id": 2,
      "inhabitants": null,
      "name": "Fixture Docks",
      "summary": "Fixture place.",
      "type": "fixed_location",
      "updatedAt": "2026-09-30T00:30:05.162666Z",
      "zone": 1
    }
  ],
  "ok": true
}

$ nexus inspect places 2 --slot 4 --json
{
  "data": {
    "createdAt": "2026-09-30T00:30:05.162666Z",
    "currentStatus": null,
    "extraData": null,
    "geometry": {
      "coordinates": [
        -74,
        40.7,
        0
      ],
      "type": "Point"
    },
    "history": null,
    "id": 2,
    "inhabitants": null,
    "name": "Fixture Docks",
    "summary": "Fixture place.",
    "type": "fixed_location",
    "updatedAt": "2026-09-30T00:30:05.162666Z",
    "zone": 1
  },
  "ok": true
}

$ nexus inspect factions --slot 4 --json
{
  "data": [
    {
      "createdAt": "2026-09-30T00:30:05.682376Z",
      "extraData": null,
      "id": 1,
      "name": "The Lamplighters",
      "primaryLocation": null,
      "summary": "Fixture faction.",
      "updatedAt": "2026-09-30T00:30:05.682376Z"
    }
  ],
  "ok": true
}

$ nexus inspect factions 1 --slot 4 --json
{
  "data": {
    "createdAt": "2026-09-30T00:30:05.682376Z",
    "extraData": null,
    "id": 1,
    "name": "The Lamplighters",
    "primaryLocation": null,
    "summary": "Fixture faction.",
    "updatedAt": "2026-09-30T00:30:05.682376Z"
  },
  "ok": true
}

$ nexus down
nothing running

.
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 passed in 17.30s
```

`nexus down` on the lane after the run:

```
$ NEXUS_GATEWAY_PORT=8017 NEXUS_API_URL=http://127.0.0.1:8017 PYTHONPATH=$PWD $PY -m nexus.cli down
nothing running
$ lsof -nP -iTCP:8017 -sTCP:LISTEN; echo $?
1
```

## Gates

`$PY` is `/Users/pythagor/nexus/.venv/bin/python`; every run is from the worktree root with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset. `PYTHONPATH=$PWD $PY -c 'import nexus;print(nexus.__file__)'` printed the worktree's `nexus/__init__.py`.

Order PostgreSQL gate (rerun after the second review fix round), and the waiter's own suites:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:warnings tests/test_cli_contract.py tests/test_cli.py tests/test_cli_inspect_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
190 passed in 94.84s (0:01:34)
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:warnings tests/test_cli_session_wait.py tests/test_cli_generation_http.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
71 passed in 107.77s (0:01:47)
```

The runs below are from the first review fix round; the second round changed only `inspect chunks` argument validation, docstrings, one annotation, and docs.

Reachability and every other CLI, `continue`, and `regenerate` test (PostgreSQL enabled, no skips):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:warnings tests/test_reachability.py tests/test_cli_session_wait.py tests/test_cli_generation_http.py tests/test_cli_choice_http.py tests/test_cli_wizard_confirmation.py tests/test_cli_model_selection.py tests/test_new_story_cli.py tests/test_record_revelation_cli_pg.py tests/test_jobs_cli_pg.py tests/test_api/test_acceptance_staging_pg.py tests/test_api/test_seat_policy_jobs_pg.py tests/test_api/test_attempt_manifest_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
183 passed in 178.33s (0:02:58)
```

Offline `pytest -q`, split to stay under the ten-minute command limit. `tests/` holds 105 top-level `test_*.py` files; parts A and B take them in `ls` order (1-57 and 58-105), and parts C and D take every test directory:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:warnings $(ls tests/test_*.py | sed -n 1,57p)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_database_contract.py::test_postgres_installer_helper_from_foreign_directory[False]
FAILED tests/test_database_contract.py::test_postgres_installer_helper_from_foreign_directory[True]
2 failed, 829 passed, 98 skipped in 230.77s (0:03:50)
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:warnings $(ls tests/test_*.py | sed -n 58,105p)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
807 passed, 179 skipped in 52.84s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:warnings tests/config tests/proofs tests/test_api tests/test_config tests/test_ir_eval_v2 tests/test_runtime tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
964 passed, 254 skipped in 40.72s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL $PY -m pytest -q -p no:warnings tests/test_lore tests/test_memnon tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1628 passed, 543 skipped in 30.10s
```

The two `test_postgres_installer_helper_from_foreign_directory` failures are this worktree's environment, not the change. The test runs `python -c 'from nexus.config import load_settings ...'` from a foreign directory without `PYTHONPATH`, so the child imports the shared venv's editable install, which points at the main checkout (`File "/Users/pythagor/nexus/nexus/database.py"` in the failure). That checkout's `RuntimeCliSettings` has no `poll_interval_seconds`, so it rejects the worktree's `nexus.toml` (`runtime.cli.poll_interval_seconds  Extra inputs are not permitted`). With the worktree's code on the path the same test passes:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=$PWD $PY -m pytest -q -p no:warnings "tests/test_database_contract.py::test_postgres_installer_helper_from_foreign_directory"
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2 passed in 1.84s
```

Lane 8017 afterwards:

```
$ NEXUS_GATEWAY_PORT=8017 NEXUS_API_URL=http://127.0.0.1:8017 PYTHONPATH=$PWD $PY -m nexus.cli down
nothing running
$ lsof -nP -iTCP:8017 -sTCP:LISTEN; echo $?
1
```

Formatting, lint, and types on the changed Python files:

```
$ $PY -m black --check nexus/cli.py nexus/cli_contract.py nexus/config/settings_models.py tests/test_cli_contract.py tests/test_cli_session_wait.py tests/test_cli_inspect_pg.py tests/test_cli_generation_http.py
All done! ✨ 🍰 ✨
7 files would be left unchanged.
$ $PY -m flake8 nexus/cli_contract.py tests/test_cli_contract.py tests/test_cli_session_wait.py tests/test_cli_inspect_pg.py tests/test_cli_generation_http.py; echo $?
0
$ $PY -m mypy nexus/cli.py nexus/cli_contract.py tests/test_cli_contract.py tests/test_cli_session_wait.py tests/test_cli_inspect_pg.py
Success: no issues found in 5 source files
```

`flake8 nexus/cli.py` reports 9 E501 lines and `flake8 nexus/config/settings_models.py` 6, the same counts as `origin/main` (all in lines this change does not touch). `mypy nexus/config/settings_models.py` reports the same 7 `[operator]` errors at `origin/main` (lines 130, 131, 138, and the local-window check). `mypy tests/test_cli_generation_http.py` reports the same 5 errors before and after the fix round (the `tomlkit` config indexing in `_run_cli` and one `str-bytes-safe` line), none in lines this round added.

## Deferred on #815

The global `{ok, data}` envelope for the remaining commands, the review verbs bound to the incubator lifecycle, operator gating and redaction of spoiler-bearing inspect fields (the incubator draft is served as the player-plane route serves it), inspect verbs for interactions, queues, settings, and secrets status (no player-plane read routes yet; they wait on the operator-plane ruling), and removing the legacy handlers' broad `except Exception`.
