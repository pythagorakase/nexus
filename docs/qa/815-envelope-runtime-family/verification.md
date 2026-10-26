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

Captured at the branch head with the `tests/test_cli_contract.py` helpers (`Gateway`, `_serve`, `_config`, `_run`, `_closed_port`); temporary paths shown as `<tmp>`:

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
receipt isolation: checkout and user receipts untouched
3212 passed, 678 skipped, 8 warnings in 721.89s (0:12:01)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
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
- mypy (`$PY -m mypy --explicit-package-bases <21 changed .py files>`), branch vs the `origin/main` versions (exported with `git archive origin/main` into a scratch tree): the per-file multiset of messages in the changed files is identical (diff empty). Branch total: 52 errors in 6 files, all pre-existing on untouched lines (`nexus/runtime/supervisor.py` 12, `tests/test_connection_lifecycle.py` 24, `tests/test_reentry_wire_ledger.py` 9, `tests/test_runtime/test_remote_auth.py` 7, `tests/test_qa_shift.py` 5, `tests/test_cli.py` 1, `tests/test_runtime/test_supervisor_live.py` 1).
- flake8, branch vs `origin/main` (messages with line numbers stripped): the only new diagnostics are three `nexus/cli.py: E501 line too long (96 > 88 characters)`, the three handler header lines of `_remote_runtime_report`. Each carries the marker the order mandates, `# nexus-exception-disposition: fail; reason=remote probe; safety=failure envelope`, which the lint requires as the whole comment on the header's colon line (no `noqa` can follow it); the shortest legal header is 89 columns even without `as exc`. The same pattern is pre-existing elsewhere in `nexus/cli.py` (for example the `reason=logs` marker line, 93 columns). The other change is the `F811 two_clusters` line moving from 38 to 39 after the added import.
- `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`: "OK: exception disposition coverage and shrink-only baseline verified." `config/exception_disposition_baseline.json` is unchanged (no baseline delta: the `run_up` and `run_status` fingerprints did not move).

## Document Freshness

`nexus/cli.py`, `nexus.toml` and `scripts/qa_shift/qa_shift.py` changed. The seven documents that declare one of them (`AGENTS.md`, `docs/turn_flow_sequence.md`, `docs/decisions/0009-dollars-in-the-ledger.md`, `0010-the-gaia-seat.md`, `0021-killed-c063.md`, `0024-killed-c102.md`, `0034-conspiracy-channel.md`) were re-read; nothing in them describes the remote probe, the success shapes, or `_read_usage`'s envelope check, and the reviewer citations quoted in 0021 and 0024 are dated records whose claims stay true. Each `verified_commit` moved to the merge base c7ae2988d07b443f627a04d3a4eed1816b1cd438, which descends from both earlier values (a01c162f, f073b371).

## Observation for the Coordinator

When `config.valid` fails on an import error, `nexus/config/loader.py:328` prints `❌ Error validating <path>:` and the error on stderr before the CLI prints its envelope there. A failing `doctor --json` therefore leaves that text ahead of the JSON envelope on stderr (seen in `tests/test_runtime/test_readiness.py::test_doctor_json_reports_a_broken_install`, which now parses from the envelope's first line). CI's `readiness-error.json` will carry the same prefix in that case. A TOML syntax error prints nothing extra (the stand-in envelope above parses whole). The loader is outside this order's scope.
