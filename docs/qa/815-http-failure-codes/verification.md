# Verification: HTTP Failure Codes Without Broad Excepts (#815 Slice S1)

Work order 815-S1 applies decision 815-Q6: a non-2xx answer is `api_error` in
every handler, a 401, 403 or unfollowed redirect is `config_error`, a database
error in `model` is the new `database_error`, and inspect keeps `not_found`.
Branch `claude/815-http-failure-codes`, cut from `origin/main` at `41783c1d`
(no newer commit on `origin/main` at push time). No migration, no gateway lane,
no paid call, no `save_NN` or `NEXUS_template` write.

Import check from the worktree root:

```text
$ PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/815-http-failure-codes/nexus/__init__.py
```

## Red: New and Rewritten Tests Against the Unchanged Product Code

The tests were written first and run against `41783c1d`'s product code (the
grep keeps the guard line, each FAILED id, and the summary):

```text
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT $PY -m pytest -q -p no:cacheprovider <the 17 new or rewritten test functions, by node id>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[load-502]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[continue-502]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[retry-502]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[undo-502]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[regenerate-502]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[model-set-502]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[clear-502]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[lock-502]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[unlock-502]
FAILED tests/test_cli_contract.py::test_http_handler_error_answer_is_an_api_error[load-404]
FAILED tests/test_cli_contract.py::test_http_handler_non_json_success_is_an_invalid_response[load-html]
FAILED tests/test_cli_contract.py::test_http_handler_non_json_success_is_an_invalid_response[continue-html]
FAILED tests/test_cli_contract.py::test_http_handler_non_json_success_is_an_invalid_response[retry-html]
FAILED tests/test_cli_contract.py::test_http_handler_non_json_success_is_an_invalid_response[undo-html]
FAILED tests/test_cli_contract.py::test_http_handler_non_json_success_is_an_invalid_response[regenerate-html]
FAILED tests/test_cli_contract.py::test_http_handler_non_json_success_is_an_invalid_response[model-set-html]
FAILED tests/test_cli_contract.py::test_http_handler_non_json_success_is_an_invalid_response[load-array]
FAILED tests/test_cli_contract.py::test_http_handler_non_json_success_is_an_invalid_response[continue-array]
FAILED tests/test_cli_contract.py::test_access_rejection_is_a_config_error[401-load]
FAILED tests/test_cli_contract.py::test_access_rejection_is_a_config_error[401-inspect-slot]
FAILED tests/test_cli_contract.py::test_access_rejection_is_a_config_error[302-access-login-load]
FAILED tests/test_cli_contract.py::test_access_rejection_is_a_config_error[302-access-login-inspect-slot]
FAILED tests/test_cli_contract.py::test_remote_up_against_a_closed_port_exits_four
FAILED tests/test_cli_contract.py::test_model_read_database_error_is_a_database_error
FAILED tests/test_cli_contract.py::test_http_command_unanswered_request_exits_four[regenerate]
FAILED tests/test_cli_contract.py::test_json_failure_preserves_every_partial_field
FAILED tests/test_cli_session_wait.py::test_wait_reports_an_http_error_answer_with_its_body
FAILED tests/test_cli_session_wait.py::test_wait_reports_an_access_rejection_as_a_config_error
FAILED tests/test_cli_session_wait.py::test_command_keeps_the_session_when_the_status_route_answers_an_error[continue]
FAILED tests/test_cli_session_wait.py::test_command_keeps_the_session_when_the_status_route_answers_an_error[regenerate]
FAILED tests/test_cli.py::test_cli_requests_take_no_literal_timeout
FAILED tests/test_cli.py::test_http_handlers_have_no_broad_except
FAILED tests/test_cli.py::test_seed_completion_transition_http_failure_exits_nonzero_with_retry[300-True-config_error]
FAILED tests/test_cli.py::test_seed_completion_transition_http_failure_exits_nonzero_with_retry[400-False-api_error]
FAILED tests/test_cli.py::test_seed_completion_transition_http_failure_exits_nonzero_with_retry[422-False-api_error]
FAILED tests/test_cli.py::test_seed_completion_transition_http_failure_exits_nonzero_with_retry[500-False-api_error]
FAILED tests/test_cli_generation_http.py::test_seed_bootstrap_failure_preserves_partial_work[schedule_error]
FAILED tests/test_cli_generation_http.py::test_seed_bootstrap_failure_preserves_partial_work[status_error]
FAILED tests/test_cli_generation_http.py::test_seed_bootstrap_failure_preserves_partial_work[load_error]
FAILED tests/test_cli_wizard_confirmation.py::test_revision_start_failure_never_sends_player_text[failure0]
FAILED tests/test_cli_wizard_confirmation.py::test_revision_start_failure_never_sends_player_text[failure1]
FAILED tests/config/test_settings_models.py::test_cli_turn_request_timeout_must_be_finite_and_positive[inf]
FAILED tests/config/test_settings_models.py::test_cli_turn_request_timeout_must_be_finite_and_positive[nan]
FAILED tests/config/test_settings_models.py::test_cli_turn_request_timeout_must_be_finite_and_positive[zero]
FAILED tests/config/test_settings_models.py::test_cli_turn_request_timeout_must_be_finite_and_positive[negative]
45 failed, 14 passed, 5 warnings in 55.21s
```

Failure reasons, counted from the same log: 13 `'domain_failure' == 'api_error'`,
7 `'domain_failure' == 'invalid_response'`, 6 `(False, 'domain_failure') ==
(False, 'api_error')`, 4 `config_error` mismatches (2 from `domain_failure`, 2
from inspect's `api_error`), 2 exit `1 == 4` (`up` against a closed port, and
`regenerate`, whose config key did not exist yet), the `retry` HTML body's
`JSONDecodeError` traceback, `domain_failure == database_error`, the two AST
tests (eight literal budgets; the nine handlers' broad excepts), `DID NOT RAISE`
for the revision-start 409 and 503, and the unknown settings key.

`test_retry_without_a_usable_session_is_an_invalid_response` was added after
that run. It was later run against the base product code: a scratch copy of
the tree at `914ba5ff` (tests included) with `nexus/cli.py`,
`nexus/cli_contract.py`, `nexus/config/settings_models.py` and `nexus.toml`
taken from `41783c1d` (`git show`, no stash). The same run includes
`test_followed_redirect_loop_is_a_domain_failure` (see Review Fixes below):

```text
$ cd <scratch copy> && env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider --tb=line -W ignore::DeprecationWarning tests/test_cli_contract.py::test_retry_without_a_usable_session_is_an_invalid_response tests/test_cli_contract.py::test_followed_redirect_loop_is_a_domain_failure
<scratch>/tests/test_cli_contract.py:252: AssertionError: Traceback (most recent call last):
<scratch>/tests/test_cli_contract.py:252: AssertionError: Traceback (most recent call last):
<scratch>/tests/test_cli_contract.py:252: AssertionError: Traceback (most recent call last):
<scratch>/tests/test_cli_contract.py:787: AssertionError: assert False
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_cli_contract.py::test_retry_without_a_usable_session_is_an_invalid_response[recovery-string]
FAILED tests/test_cli_contract.py::test_retry_without_a_usable_session_is_an_invalid_response[recovery-without-session]
FAILED tests/test_cli_contract.py::test_retry_without_a_usable_session_is_an_invalid_response[answer-without-session]
FAILED tests/test_cli_contract.py::test_followed_redirect_loop_is_a_domain_failure
4 failed in 4.77s
```

The three `retry` tracebacks, from the `--tb=short` rerun of the same copy:
`TypeError: string indices must be integers, not 'str'` at base
`nexus/cli.py:2812` (`recovery-string`), `KeyError: 'session_id'` at :2812
(`recovery-without-session`) and at :2816 (`answer-without-session`), each in
`run_retry`.

## Green

Order's offline CLI files (final run, after the last product change):

```text
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider tests/test_cli_contract.py tests/test_cli_session_wait.py tests/test_cli_generation_http.py tests/test_cli_model_selection.py tests/test_cli.py tests/test_cli_wizard_confirmation.py tests/test_cli_choice_http.py tests/config/test_settings_models.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
435 passed, 5 warnings in 270.20s (0:04:30)
```

PostgreSQL files (disposable clones only; the audit names no owner target):

```text
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_cli_inspect_pg.py tests/test_record_revelation_cli_pg.py tests/test_jobs_cli_pg.py tests/test_tags_audit_pg.py tests/test_api/test_acceptance_staging_pg.py tests/test_api/test_attempt_manifest_pg.py tests/test_api/test_seat_policy_jobs_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 35 targets: postgres, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_800b_inspect_*, qa640_811_tags_audit_* x5, qa640_811_tags_audit_nocol_*, qa640_814_seats_*, qa640_815_inspect_*, qa640_acceptance_* x19, qa653_* x2, qa_wt664_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
40 passed, 9 warnings in 100.25s (0:01:40)
```

`NEXUS_SLOT` was also unset for this run.

Offline suites. The first run of the first command omitted `PYTHONPATH=$PWD`;
`tests/test_database_contract.py::test_postgres_installer_helper_from_foreign_directory[False|True]`
then ran a helper from a foreign directory that imported the main checkout's
`nexus` and rejected the worktree's new `[runtime.cli]` key (`2 failed, 2660
passed, 419 skipped`). The rerun with `PYTHONPATH=$PWD`:

```text
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2662 passed, 419 skipped, 8 warnings in 447.43s (0:07:27)

$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1816 passed, 742 skipped, 7 warnings in 42.38s
```

`tests/test_reachability.py` ran inside the first offline command and alone
with `tests/test_database_contract.py` (`62 passed, 2 skipped`).

Black reports the ten changed Python files unchanged. flake8 on them reports
only the 15 `E501` lines that `origin/main`'s `nexus/cli.py` (9) and
`nexus/config/settings_models.py` (6) already carry. mypy on the three changed
product files reports 7 errors, all in `nexus/config/settings_models.py` lines
this change does not touch (130-138, 4396); the one new finding
(`_get_next_phase` given `Any | None` once the wizard chat body is typed
`Dict[str, Any]`) was fixed with an `isinstance` guard that keeps the old
result. The `validate-config` pre-commit hook passed on the `nexus.toml`
change.

## Site Table

Line numbers are `nexus/cli.py` at the base `41783c1d`. "Old" is the code the
envelope reported at the base; "new" is the code now. Every `.json()` in the
nine handlers and their helpers is listed; `grep -n "\.json()" nexus/cli.py`
after the change finds only `_api_answer`, the inspect reads (`_inspect_body`,
`_inspect_chunks`), and the unchanged rows below marked "unchanged read".

| Base line | Function | Path now | Old code | New code |
| --- | --- | --- | --- | --- |
| :1224 | `run_load` state | `_api_object` | non-2xx `domain_failure`; 3xx, non-JSON, non-object `domain_failure` | non-2xx `api_error`; 401/403/3xx `config_error`; non-JSON or non-object `invalid_response` |
| :1645 | `_RetrogradeStageEcho._fetch` | unchanged read (side channel, own catch) | prints "Genesis stage unavailable" | unchanged |
| :1876-1882 | `wait_for_session` status | non-2xx gets `code=_answer_failure_code`; body read unchanged | `http_error` / `domain_failure` | `http_error` / `api_error` or `config_error`; unusable payload stays `invalid_response` / `domain_failure` |
| :1920-1926 | `_load_session_result` state | same as above | `http_error` / `domain_failure` | `http_error` / `api_error` or `config_error`; unusable state stays `domain_failure` |
| :2026-2027 | `_bootstrap_seed_narrative` schedule answer | explicit status check; unchanged read | non-2xx `domain_failure` (`raise_for_status` text); a 3xx reached `.json()`; a non-object body raised `AttributeError` past the seed's catch to the broad except, losing the saved seed from `partial` | non-2xx `api_error` or `config_error` with `"{url} returned HTTP {status}: {text}"`, seed kept; non-JSON or non-object 2xx is the existing `ValueError`, `domain_failure`, seed kept |
| :2174 | `_apply_traits_to_wildcard_transition` | `_api_object`; failure into `intro_error` | non-JSON body reached the broad except: `domain_failure`, saved traits not reported | success with `intro_error` (message, status code) and the retry command |
| :2219-2221 | `_confirm_wizard_artifact_and_introduce` | non-2xx code added; body read unchanged (local `ValueError` and shape check) | `domain_failure` | `api_error` or `config_error`, recovery fields kept |
| :2277-2279 | `_introduce_accepted_phase` | non-2xx code added; body read unchanged | `domain_failure` | `api_error` or `config_error`, recovery fields kept |
| :2310-2312 | `_start_wizard_character_revision` | non-2xx raises `ApiAnswerFailure`; body via `_api_answer`; identity check stays `ValueError` | `domain_failure` | `api_error` or `config_error` (status in `partial`); non-JSON `invalid_response`; wrong identity `domain_failure` |
| :2335-2338 | `_record_wizard_weird_level` | non-2xx raises `ApiAnswerFailure`; body via `_api_object` | `domain_failure` | `api_error` or `config_error`; non-object `invalid_response`; level mismatch stays `domain_failure` |
| :2359-2360 | `run_continue` state | `_api_object` | as `run_load` | as `run_load` |
| :2386-2393 | `run_continue` setup start | non-2xx result gets `code`; body via `_api_object` | `domain_failure` | `api_error` (`config_error` for 401/403; a 3xx passes `.ok` and `_api_object` raises `config_error`) |
| :2476 | `_wizard_artifact_identity` call | `ValueError` caught at the call | broad except, `domain_failure` | `domain_failure` |
| :2493-2498 | `run_continue` ready transition | non-2xx result gets `code`; answer via `_api_object` | `domain_failure` | `api_error` or `config_error`; non-object `invalid_response` |
| :2501-2502 | `run_continue` state refresh | `_api_object` (there was no status check) | any answer read as JSON: `domain_failure` | as `run_load` |
| :2571-2573 | trait toggle POST | `_api_object`, turn budget | `domain_failure` | as `run_load` |
| :2634-2636 | wizard chat POST | `_api_object`, turn budget | `domain_failure` | as `run_load` |
| :2711-2723 | seed transition | non-2xx `code=_answer_failure_code`; answer via `_api_object` caught into `_seed_transition_failure` | `domain_failure` | `api_error` or `config_error`; non-object `invalid_response` with status `invalid_response`; seed and retry command kept |
| :2754-2756 | narrative continue POST | `_api_object`, turn budget | `domain_failure` | as `run_load` |
| :2802-2803 | `run_retry` state | `_api_object`; recovery must be an object with a session ID | non-2xx `domain_failure`; non-JSON or odd recovery: traceback | as `run_load`; odd recovery `invalid_response` |
| :2815-2816 | `run_retry` answer | `_api_object`; session ID must be a non-empty string; turn budget | non-2xx `domain_failure`; non-JSON or missing ID: traceback | as `run_load`; missing ID `invalid_response` |
| :2832-2833 | `run_undo` | `_api_object` | `domain_failure` | as `run_load` |
| :2865-2866 | `run_regenerate` | `_api_object`, turn budget | `domain_failure` | as `run_load`; no session ID stays `domain_failure` |
| :2911-2912 | `run_model --set/--clear` | `_api_object` | `domain_failure` | as `run_load` |
| :2931 | `run_model` slot read | `except psycopg2.Error` | `domain_failure` | `database_error` |
| :2933-2936 | `run_model` seat resolution | `except ValueError` | `domain_failure` | `domain_failure` (unchanged, remedy in the error) |
| :2965-2966, :4012-4013, :4034-4035 | `run_clear`, `run_lock`, `run_unlock` | `_check_answer` | `domain_failure` | `api_error` or `config_error` |
| :1338-1347 | `_inspect_body` | Access check after the 404 check | 401/403/3xx `api_error` | `config_error`; 404 stays `not_found` |
| :4059-4077 | `run_up` | `except _TRANSPORT_ERRORS: raise` first; `MissingSecretError` dropped from the tuple | unreachable remote runtime exit 1 | exit 4 `api_unreachable`; credential errors `config_error` |

Request budgets: the seven `timeout=120` literals (`nexus/cli.py:2144`, :2275,
:2571, :2634, :2754, :2813, :2864 at the base) and the `schedule_timeout: float
= 120` default (:2010) now read `[runtime.cli].turn_request_timeout_seconds`
(120.0 in the checkout).

## Rewritten Assertions

- `tests/test_cli_contract.py` `test_json_failure_preserves_every_partial_field`:
  the 503 next-phase introduction is `api_error`.
- `tests/test_cli_session_wait.py` `test_wait_reports_an_http_error_answer_with_its_body`:
  `("http_error", "api_error")`.
- `tests/test_cli.py` `test_seed_completion_transition_http_failure_exits_nonzero_with_retry`:
  300 is `config_error`; 400, 422, 500 are `api_error`.
- `tests/test_cli_generation_http.py` `test_seed_bootstrap_failure_preserves_partial_work`:
  `schedule_error`, `status_error`, `load_error` are `api_error`; the rest stay
  `domain_failure`.
- `tests/test_cli_wizard_confirmation.py` `test_revision_start_failure_never_sends_player_text`:
  409 and 503 raise `ApiAnswerFailure` (`api_error`, the status, one request);
  the wrong-thread 200 keeps its return assertion.
- `tests/test_cli_contract.py` `test_http_command_unanswered_request_exits_four`
  gains `regenerate` (with `turn_request_timeout_seconds = 0.5` and its short
  budgets at 30 s, so only the turn budget gives `read timeout=0.5`).

Fakes given the attributes the classifier reads, nothing else changed:
`DummyResponse` and the `run_load` `Response` in `tests/test_cli.py`,
`DummyResponse` in `tests/test_cli_model_selection.py`, `Response` in
`tests/test_cli_wizard_confirmation.py` (`url`, `headers`, and `status_code`
where missing).

## Review Fixes (Commit `914ba5ff`)

The review of `57907768` found these, all fixed in `914ba5ff`; the tails
below ran on that tree.

- `main()` now reports any other `requests.RequestException` as
  `domain_failure` (`Could not read <API URL>: <error>`), not a traceback.
  The broad excepts had absorbed it; `57907768` let it escape. New test
  `test_followed_redirect_loop_is_a_domain_failure` (a route that redirects to
  itself, no credential, so `requests` follows it). Red against `57907768`'s
  `nexus/cli.py` in a scratch copy:

  ```text
  E       File "nexus/cli.py", line 1324, in run_load
  E       File "nexus/cli.py", line 178, in _api_request
  E     requests.exceptions.TooManyRedirects: Exceeded 30 redirects.
  FAILED tests/test_cli_contract.py::test_followed_redirect_loop_is_a_domain_failure
  1 failed in 1.96s
  ```

  Against the base (`41783c1d`, run above) the broad except reported it as
  `domain_failure` with the bare message `Exceeded 30 redirects.`, so there
  the test fails only on the message prefix (`test_cli_contract.py:787`).
- `docs/cli.md` scopes the answer rules to the play and slot commands and
  `inspect`. `partial.status_code` and the Access-naming message apply where
  the command's own read rejects the answer. The steps that keep their own
  wording are listed with what they carry: setup, the transition,
  confirmations and phase introductions have the body only; `--weird` and
  revision have `partial.status_code`; the seed transition has
  `transition_error.status_code`; the opening turn and the generation wait
  have the URL and status in their detail.
- `turn_request_timeout_seconds`'s description drops "A request without an
  answer in time exits 4". The phase introductions and the opening turn do
  not exit 4.
- `run_continue`'s two one-line implicit concatenations are merged into single
  literals (same text).
- `test_http_handlers_have_no_broad_except` checks each element of a tuple
  and a qualified name. A sabotage copy of `914ba5ff` whose `run_clear` wraps
  `_check_answer` in `except (Exception, ValueError): raise`, then in
  `except builtins.Exception: raise`, fails it both times:
  `AssertionError: assert ['run_clear at line 3132'] == []`.
- The `regenerate` case of `test_http_command_unanswered_request_exits_four`
  keeps `request_timeout_seconds` and `inspect_timeout_seconds` at 30.0. A
  sabotage copy whose `run_regenerate` reads `_request_timeout_seconds()`
  fails it after 31 s:
  `assert 'read timeout=0.5' in "... Read timed out. (read timeout=30.0)"`.

Covering tests on `914ba5ff`:

```text
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider tests/test_cli_contract.py tests/test_cli_session_wait.py tests/test_cli_generation_http.py tests/test_cli_model_selection.py tests/test_cli.py tests/test_cli_wizard_confirmation.py tests/test_cli_choice_http.py tests/config/test_settings_models.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
436 passed, 5 warnings in 255.17s (0:04:15)
```

Black reports the four changed Python files unchanged. Their flake8 output
matches `57907768`'s (the same 15 `E501` findings, compared without line
numbers). mypy on `nexus/cli.py` and `nexus/config/settings_models.py` reports
the same 7 errors at `settings_models.py` 130-138 and 4395 (4396 before one
description line was dropped). The `validate-config` hook passed. Not rerun
for `914ba5ff` (they ran on `57907768`, above): the PostgreSQL files and the
two whole-tree offline commands. The change since then is the `main()`
clause, two string literals, one description string, docs, and tests.
