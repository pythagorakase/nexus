# Verification for #815 Slices S4 and S6a: Remote Exit Codes and the Runtime-Family Envelope

Branch `claude/815-envelope-runtime-family`, cut from `origin/main` at c7ae2988 (still the newest `origin/main` when this was written, so the merge base is c7ae2988). All commands ran from the worktree root with the shared interpreter `/Users/pythagor/nexus/.venv/bin/python` (`$PY`) and `PYTHONPATH=$PWD`; `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` were unset. No migration, no paid call, no gateway lane of this order's own.

## What Was Wrong (Read at c7ae2988)

- `nexus/runtime/supervisor.py:13`: the module docstring says remote "status hits <base_url>/runtime/status". `:896-897`: `up()` returns `self._check_remote()` under the remote profile; `:984-995` `_check_remote` GETs `remote.base_url + RUNTIME_STATUS_PATH` and calls `raise_for_status()`.
- `nexus/api/route_capabilities.py:271`: `("GET", "/runtime/status"): _operator("diagnostics.runtime", "read")`; `:255`: `("GET", "/health"): _HEALTH` (player plane). `nexus/api/narrative.py:825-832`: `/health` returns `status`, `service` and `plane`.
- `supervisor.py:1115-1129`: `_fetch_runtime_status` turns any `RequestException` into `{"error": "runtime status unreachable at ..."}`; `:1134` sets `"success": True`; `:1161` nests it under `runtime`. `nexus/cli.py:6502`: `main()` fails only on a top-level `error` or `success: false`, so remote status exited 0.
- `nexus/cli.py:4371-4374`: `run_up` re-raises `_TRANSPORT_ERRORS`, so `main()` reported `api_unreachable` with `partial: {}`; `:4375-4381`: an `HTTPError` became a plain `domain_failure`.
- `nexus/cli.py:6510-6513`: only `ENVELOPE_COMMANDS` printed `success_envelope`; `:6522` printed every other result raw through `emit_output`. `:4740-4742`: `receipts` printed its document raw; `run_doctor`/`run_init` printed their reports on stdout and exited 1 on failure.
- `scripts/qa_shift/qa_shift.py:225-227`: `_read_usage` required `payload["success"] is True`. `.github/workflows/reachability-check.yml:38`: `poetry run nexus doctor --target ci-runner --json | tee readiness-report.json`.

## Red Run (New Tests Committed, Product Code Unchanged)

Commits 0bae1bac (S4 tests) and c2ca24f5 (S6a tests), before any change under `nexus/`, `scripts/` or `.github/`:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -k "remote_probe or remote_up_and_status or local_status_with_the_gateway or result_envelope_family or failing_doctor_report or supervisor_remote or read_usage_parses" tests/test_cli_contract.py tests/test_runtime/test_remote_auth.py tests/test_qa_shift.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_cli_contract.py::test_remote_probe_against_a_closed_port_exits_four[up]
FAILED tests/test_cli_contract.py::test_remote_probe_against_a_closed_port_exits_four[status]
FAILED tests/test_cli_contract.py::test_remote_probe_unanswered_exits_four[up]
FAILED tests/test_cli_contract.py::test_remote_probe_unanswered_exits_four[status]
FAILED tests/test_cli_contract.py::test_remote_probe_error_answer_is_an_api_error[up]
FAILED tests/test_cli_contract.py::test_remote_probe_error_answer_is_an_api_error[status]
FAILED tests/test_cli_contract.py::test_remote_probe_access_rejection_is_a_config_error[forbidden-up]
FAILED tests/test_cli_contract.py::test_remote_probe_access_rejection_is_a_config_error[forbidden-status]
FAILED tests/test_cli_contract.py::test_remote_probe_access_rejection_is_a_config_error[unfollowed-redirect-up]
FAILED tests/test_cli_contract.py::test_remote_probe_access_rejection_is_a_config_error[unfollowed-redirect-status]
FAILED tests/test_cli_contract.py::test_remote_probe_non_object_health_is_an_invalid_response[up]
FAILED tests/test_cli_contract.py::test_remote_probe_non_object_health_is_an_invalid_response[status]
FAILED tests/test_cli_contract.py::test_local_status_with_the_gateway_down_still_exits_zero
FAILED tests/test_cli_contract.py::test_remote_up_and_status_report_the_player_health
FAILED tests/test_cli_contract.py::test_runtime_family_is_the_result_envelope_family
FAILED tests/test_cli_contract.py::test_failing_doctor_report_is_the_failure_envelope
FAILED tests/test_runtime/test_remote_auth.py::test_supervisor_remote_probe_reaches_live_runtime
FAILED tests/test_runtime/test_remote_auth.py::test_supervisor_remote_profile_runs_nothing
FAILED tests/test_qa_shift.py::test_read_usage_parses_the_cli_success_envelope
19 failed, 292 deselected, 5 warnings in 22.11s
```

Representative failure reasons from the same run:

```
E       AssertionError: assert {} == {'config': '/...le': 'remote'}
E       assert 0 == <ExitCode.UNREACHABLE: 4>
E       AssertionError: assert 'domain_failure' == 'api_error'
E       assert 0 == <ExitCode.DOMAIN_FAILURE: 1>
```

(`up` against a closed port had `partial == {}`; `status` exited 0 with `"success": true` and a nested `runtime.error`; a 502 on the probe was `domain_failure`; the requests went to `/runtime/status`.)

## Envelopes From the Loopback Stand-In

Captured at 927b0a1f (the S6a head before review) with the `tests/test_cli_contract.py` helpers (`Gateway`, `_serve`, `_config`, `_run`, `_closed_port`); temporary paths shown as `<tmp>`. The capture command, run from the worktree root, was `PYTHONPATH=$PWD $PY <scratchpad>/815-S4S6a/capture_envelopes.py`, where the script is:

```python
"""Capture remote status/up and failing doctor envelopes via the test stand-in."""
import tempfile
from pathlib import Path

from tests.test_cli_contract import HEALTH, Gateway, _closed_port, _config, _run, _serve

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    gateway = Gateway(routes={("GET", "/health"): (200, HEALTH)})
    with _serve(gateway) as base_url:
        config = _config(tmp_path, profile="remote", base_url=base_url)
        env = {"NEXUS_RUNTIME_CONFIG": str(config)}
        for verb in ("status", "up"):
            done = _run(verb, "--json", env=env)
            print(f"$ nexus {verb} --json  (remote, /health answers 200)  exit {done.returncode}")
            print(done.stdout + done.stderr)
    print("requests:", [r[:2] for r in gateway.requests])
    closed = f"http://127.0.0.1:{_closed_port()}"
    config = _config(tmp_path / "closed", profile="remote", base_url=closed) if (tmp_path / "closed").mkdir() is None else None
    done = _run("status", "--json", env={"NEXUS_RUNTIME_CONFIG": str(config)})
    print(f"$ nexus status --json  (remote, closed port)  exit {done.returncode}")
    print("stdout:", repr(done.stdout))
    print(done.stderr)
    broken = tmp_path / "nexus.toml"
    broken.write_text("[runtime\n", encoding="utf-8")
    done = _run("doctor", "--target", "ci-runner", "--config", str(broken), "--json",
                env={"NEXUS_API_URL": "https://nexus.example.invalid"})
    print(f"$ nexus doctor --target ci-runner --config <broken> --json  exit {done.returncode}")
    print("stdout:", repr(done.stdout))
    print(done.stderr)
```

The same payloads are pinned by the assertions of `tests/test_cli_contract.py::test_remote_up_and_status_report_the_player_health`, `::test_remote_probe_against_a_closed_port_exits_four[status]` and `::test_failing_doctor_report_is_the_failure_envelope`.


```
$ nexus status --json  (remote, /health answers 200)  exit 0
{
  "data": {
    "config": "<tmp>/remote.toml",
    "gateway_url": "http://127.0.0.1:61019",
    "health": {
      "plane": "player",
      "service": "narrative_api",
      "status": "healthy"
    },
    "profile": "remote"
  },
  "ok": true
}

$ nexus up --json  (remote, /health answers 200)  exit 0
{
  "data": {
    "config": "<tmp>/remote.toml",
    "gateway_url": "http://127.0.0.1:61019",
    "health": {
      "plane": "player",
      "service": "narrative_api",
      "status": "healthy"
    },
    "profile": "remote"
  },
  "ok": true
}

requests: [('GET', '/health'), ('GET', '/health')]
$ nexus status --json  (remote, closed port)  exit 4
stdout: ''
{
  "code": "api_unreachable",
  "error": "Cannot connect to API server at http://127.0.0.1:61042: HTTPConnectionPool(host='127.0.0.1', port=61042): Max retries exceeded with url: /health (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x109b04690>: Failed to establish a new connection: [Errno 61] Connection refused'))",
  "ok": false,
  "partial": {
    "config": "<tmp>/closed/remote.toml",
    "gateway_url": "http://127.0.0.1:61042",
    "profile": "remote"
  }
}

$ nexus doctor --target ci-runner --config <broken> --json  exit 1
stdout: ''
{
  "code": "domain_failure",
  "error": "readiness checks failed for ci-runner: config.valid",
  "ok": false,
  "partial": {
    "checks": [
      {
        "depends_on": [],
        "id": "config.valid",
        "observed": "<tmp>/nexus.toml: Expected ']' at the end of a table declaration (at line 1, column 9)",
        "remediation": "Correct <tmp>/nexus.toml where the error points; the fields are defined in nexus/config/settings_models.py.",
        "status": "fail",
        "targets": [
          "owner-host",
          "owner-client",
          "ci-runner"
        ]
      },
      {
        "depends_on": [
          "config.valid"
        ],
        "id": "reachability.gate",
        "observed": "config.valid failed",
        "remediation": "Resolve config.valid first.",
        "status": "skip",
        "targets": [
          "ci-runner"
        ]
      }
    ],
    "ok": false,
    "omitted": [],
    "schema_version": 1,
    "target": "ci-runner"
  }
}

```

## PostgreSQL Proof Set

Load average before the run: 8.05 (below 24; no wait).

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_runtime/test_supervisor_live.py tests/test_slot_routed_entrypoints.py tests/test_connection_lifecycle.py tests/test_orrery/test_card_identity.py tests/test_lore/test_window_coverage_pg.py tests/test_runtime/test_init_plan_pg.py tests/test_runtime/test_readiness_pg.py tests/test_api/test_acceptance_staging_pg.py tests/test_api/test_scheduler_recovery_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 60 targets: postgres, qa640_1013_readiness_* x2, qa640_756s1_distinct_*, qa640_756s1_generation_* x2, qa640_800_kill_*, qa640_800_renew_* x4, qa640_803s6_slot1_*, qa640_803s6_slot2_*, qa640_803s6_slot3_*, qa640_803s6_slot4_*, qa640_803s6_slot5_*, qa640_803s6_template_*, qa640_816_lifecycle_test_provider, qa640_885_ren_replay_* x4, qa640_acceptance_* x19, qa640_historical_coverage_* x3, qa640_offline_gate_* x5, qa640_window_coverage_*, qa885_entrypoints_*, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:57407 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:57409 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:57407 (psycopg2), save_04@local:57409 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
101 passed, 4 skipped, 9 warnings in 317.46s (0:05:17)
```

The four skips are the `@requires_corpus` tests (`test_window_coverage_pg.py::test_configured_k_bounds_the_deep_query_pool[3|15]`, `test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[False|True]`), which run only under `NEXUS_RUN_CORPUS=1`.

## Offline Suites

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3212 passed, 678 skipped, 8 warnings in 721.89s (0:12:01)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1532 skipped, 7 warnings in 53.63s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
120 passed, 5 warnings in 22.10s

$ PYTHONPATH=$PWD $PY -m scripts.render_cli_reference --check
(no output, exit 0: no parser help or rendered table changed, so no --write)
```

## Static Checks

- Black: `$PY -m black --check` on the 4 product files and 17 changed test files: "21 files would be left unchanged."
- mypy (`$PY -m mypy --explicit-package-bases <21 changed .py files>`), branch vs the `origin/main` versions (exported with `git archive origin/main` into a scratch tree, where the same command also reports errors in imported modules that this comparison leaves out), rerun at 080bf3ca after review: the first branch run compared message multisets with line numbers stripped, which hid that the new `probe_remote_health` line `url = remote.base_url.rstrip("/") + "/health"` carried `Item "None" of "RuntimeRemoteSettings | None" has no attribute "base_url"  [union-attr]` (the same message `_check_remote` carried on `origin/main` at `supervisor.py:986`). 080bf3ca adds `if remote is None: raise RuntimeError_(...)` before that line, which clears it. In the changed files, `origin/main` has 52 errors in 6 files (`nexus/runtime/supervisor.py` 9, `tests/test_connection_lifecycle.py` 24, `tests/test_reentry_wire_ledger.py` 9, `tests/test_runtime/test_remote_auth.py` 7, `tests/test_qa_shift.py` 2, `tests/test_cli.py` 1); the branch has "Found 51 errors in 6 files (checked 21 source files)" (`nexus/runtime/supervisor.py` 8, the other five files unchanged). The only multiset difference is that removed `union-attr` message. Checked against `git diff -U0 origin/main`, no branch diagnostic sits on a changed or added line. The remaining `supervisor.py` diagnostics are the `requests` stubs import (`:36`), the two Windows creation flags (`:652`), the `external` union-attr lines in `_attach_external` (`:975-977`) and `gateway_url()` (`:1127`, `:1129`), all on lines this branch does not change (the order keeps `gateway_url()` and the external path as they are).
- flake8, branch vs `origin/main` (messages with line numbers stripped): the only new diagnostics are three `nexus/cli.py: E501 line too long (96 > 88 characters)`, the three handler header lines of `_remote_runtime_report`. Each carries the marker the order mandates, `# nexus-exception-disposition: fail; reason=remote probe; safety=failure envelope`, which the lint requires as the whole comment on the header's colon line (no `noqa` can follow it); the shortest legal header is 89 columns even without `as exc`. The same over-length marker pattern is pre-existing in `nexus/runtime/slot_operations.py:300`, `:315` and `:343` on `origin/main` (179, 183 and 179 columns); no marker line in `nexus/cli.py` was over 88 columns on `origin/main`. The other change is the `F811 two_clusters` line moving from 38 to 39 after the added import.
- `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`: "OK: exception disposition coverage and shrink-only baseline verified." `config/exception_disposition_baseline.json` is unchanged (no baseline delta: the `run_up` and `run_status` fingerprints did not move).

## Document Freshness

`nexus/cli.py`, `nexus.toml` and `scripts/qa_shift/qa_shift.py` changed. The seven documents that declare one of them (`AGENTS.md`, `docs/turn_flow_sequence.md`, `docs/decisions/0009-dollars-in-the-ledger.md`, `0010-the-gaia-seat.md`, `0021-killed-c063.md`, `0024-killed-c102.md`, `0034-conspiracy-channel.md`) were re-read; nothing in them describes the remote probe, the success shapes, or `_read_usage`'s envelope check, and the reviewer citations quoted in 0021 and 0024 are dated records whose claims stay true. Each `verified_commit` moved to the merge base c7ae2988d07b443f627a04d3a4eed1816b1cd438, which descends from both earlier values (a01c162f, f073b371).

## Observation for the Coordinator

When `config.valid` fails on an import error, `nexus/config/loader.py:328` prints `❌ Error validating <path>:` and the error on stderr before the CLI prints its envelope there. A failing `doctor --json` therefore leaves that text ahead of the JSON envelope on stderr (seen in `tests/test_runtime/test_readiness.py::test_doctor_json_reports_a_broken_install`, which now parses from the envelope's first line). CI's `readiness-error.json` will carry the same prefix in that case. A TOML syntax error prints nothing extra (the stand-in envelope above parses whole). The loader is outside this order's scope; the follow-up is #1157 (see the second review fixes below).

## Review Fixes (080bf3ca)

080bf3ca narrows `probe_remote_health`'s `remote` before use, corrects the `RemoteRuntime.profile` docstring and `run_up`'s re-raise comment, extends `test_remote_up_and_status_report_the_player_health` with a text-mode `status` run (stdout `NEXUS runtime - profile remote - <base_url>` then `health healthy - plane player`, a third `GET /health`), and adds `test_remote_status_text_error_answer_prints_one_error_line` (a 502 prints one `Error:` line on stderr and nothing on stdout). The tails below ran on the working tree that 080bf3ca committed. The PostgreSQL proof set and the two offline suites above ran at 927b0a1f, before these changes.

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_cli_contract.py tests/test_runtime/test_remote_auth.py tests/test_runtime/test_supervisor.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
367 passed, 5 warnings in 231.74s (0:03:51)
```

`tests/test_orrery/test_character_identity_pg.py` changed on this branch (`test_identity_ambiguity_never_retries_test_provider` reads `["data"]` from `window-replay` and `usage`) and was in no earlier run. Load average before the run: 8.39 (below 24; no wait).

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_character_identity_pg.py
...........                                                              [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 12 targets: postgres, qa640_roster798_* x11
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
11 passed in 28.87s
```

Black (`$PY -m black --check` on the four changed files): "4 files would be left unchanged." flake8 on `nexus/runtime/supervisor.py`, `nexus/cli_contract.py` and `tests/test_cli_contract.py`: no output; on `nexus/cli.py` the same E501 set as before (the three marker lines plus the pre-existing long lines). `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`: "OK: exception disposition coverage and shrink-only baseline verified."

## Review Fixes, Second Round (dad95ff8)

dad95ff8 applies three review findings. The tails below ran on the working tree that dad95ff8 committed.

- `test_remote_status_text_error_answer_prints_one_error_line` (`tests/test_cli_contract.py:1484`) passed even with the remote branch of `run_status` removed: `supervisor.status()` then raises `RuntimeError_(_REMOTE_RUNS_NOTHING)` (`supervisor.py:1151-1152`), which `run_status`'s own `except RuntimeError_` turns into one `Error:` line and exit 1. The test now also requires `[request[:2] for request in gateway.requests] == [("GET", "/health")]` and `lines[0] == f"Error: API error: {_BAD_GATEWAY_PAGE}"` (the `api_error` message `_check_answer` builds, `nexus/cli.py:1282-1284`).
- The `nexus/cli_contract.py` module docstring lines 56-69 are reflowed to 79 columns so `handlers (``load``,` no longer stands alone; the wording is unchanged (the joined text is byte-identical before and after the reflow).
- The loader's validation print (`nexus/config/loader.py:328-329`) is outside this order, so the finding's second option was taken: follow-up issue #1157 names `tests/test_runtime/test_readiness.py:347` and CI's `readiness-error.json`, and the test's comment at the loosened slice now names #1157. The loader is unchanged.

Red run for the strengthened test: the five-line remote branch of `run_status` (`if supervisor.runtime.profile == "remote": ... return result`) was removed from a working copy of `nexus/cli.py`, the test was run, and `nexus/cli.py` was restored with `git checkout -- nexus/cli.py` (`git status --short` afterwards lists only the three committed files).

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_cli_contract.py -k test_remote_status_text_error_answer_prints_one_error_line
E       AssertionError: assert [] == [('GET', '/health')]
E         
E         Right contains one more item: ('GET', '/health')
E         Use -v to get more diff

tests/test_cli_contract.py:1495: AssertionError
...
FAILED tests/test_cli_contract.py::test_remote_status_text_error_answer_prints_one_error_line
1 failed, 209 deselected, 5 warnings in 1.38s
```

Green, the same test with `nexus/cli.py` as committed:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_cli_contract.py -k test_remote_status_text_error_answer_prints_one_error_line
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1 passed, 209 deselected, 5 warnings in 1.41s
```

The covering files (load average 3.04 before the run; no wait):

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_cli_contract.py tests/test_runtime/test_readiness.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
320 passed, 5 warnings in 198.11s (0:03:18)
```

Black (`$PY -m black --check nexus/cli_contract.py tests/test_cli_contract.py tests/test_runtime/test_readiness.py`): "3 files would be left unchanged." flake8 on the same three files: no output (the `origin/main` version of `test_readiness.py` also prints nothing). No exception handler changed, so the disposition baseline is untouched; no declared source changed, so no freshness stamp moves.
