# Verification: 806-S1 Receipt Store, Envelope, Config-Load Receipts, Compacted Read

Issue #806 (decisions 806-Q1, Q2, Q5, Q12). Branch `claude/806-receipt-store`,
cut from `origin/main` at `b0da93ea`. No migration, no paid call, no gateway
lane. Every test is offline and in-process or a `nexus` subprocess that starts
no service.

## What Was Wrong (Cited on `origin/main` at `b0da93ea`)

- No receipt store: the home layout names `CACHE_DIR` and `BACKUPS_DIR`
  (`nexus/runtime/home.py:47-48`) and no receipts directory; `RuntimeHome`
  (`:163-198`) and `build_runtime_home` (`:201-225`) carry none.
- `load_settings` (`nexus/config/loader.py:235-285`) and `_load_from_toml`
  (`:288-306`) raise `FileNotFoundError` (`:272-273`), `ValueError`
  (`:284-285`), `tomllib.TOMLDecodeError` (`:290-291`) and pydantic's
  `ValidationError` (`:300-306`) and persist nothing; `:303-306` prints the
  `ValidationError` text (with input values) to stderr only, and the CLI turns
  these into `config_error` (`nexus/cli.py:6092-6101`).
- `load_preferences` parses and validates `preferences.toml` at
  `nexus/config/preferences.py:33-34` and persists nothing on failure.
- `RuntimeHomeError` is raised at `home.py:137-141` (relative `NEXUS_HOME`),
  `:148-154` (two locators name different configurations) and `:207-211` (no
  `[runtime]` section); nothing persists it.
- No sanitizer for a durable record. Precedents: `nexus/api/narrative.py:154-171`
  drops `input` and `ctx`; `readiness.one_line` (`readiness.py:181-191`) keeps
  pydantic's `msg`, so it is not used. Append precedent:
  `nexus/telemetry/usage.py:251-277`.
- No reader: `SELF_DIAGNOSTIC_COMMANDS` is `{"doctor"}`
  (`nexus/cli_contract.py:187` after #817 S1 moved it from `:185`), and
  `COMMAND_TRANSPORTS` (`:92-149`) has no receipts command.
- `tests/conftest.py` isolates the usage ledger through a module attribute
  (`:192-204`), which a child does not see; it exports
  `NEXUS_TEST_PROVIDER_ONLY` (`:17-19`) so children inherit it. Nothing
  isolated receipts.

## One Receipt Line From Each of Tests 1-3

Produced by a scratch script that repeats tests 1-3 against the helpers in
`tests/test_runtime/test_receipts.py` (scratch path shortened to `<scratch>`).
None contains either planted string, a message, an input or a source line.

Test 1 (malformed TOML, `details == {"kind": "toml", "line": 3, "column": 11}`):

```json
{"schema_version":1,"recorded_at":"2026-10-08T04:19:43.035131Z","surface":"config.load_settings","pid":16550,"config_path":"<scratch>/806-S1/ev/broken.toml","exception_type":"TOMLDecodeError","exception_module":"tomllib","frames":[{"file":"nexus/config/loader.py","line":278,"function":"load_settings"},{"file":"nexus/config/loader.py","line":299,"function":"_load_from_toml"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":66,"function":"load"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":102,"function":"loads"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":326,"function":"key_value_rule"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":369,"function":"parse_key_value_pair"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":649,"function":"parse_value"}],"frames_dropped":0,"details":{"kind":"toml","line":3,"column":11},"fingerprint":"d187a33a6f219a3c0244ab0b8f2a3ca2496d5a22bd4b3f89c46eec650a9fd179"}
```

Test 2 (validation: `loc` and `type` only; both unknown keys are `["runtime", "?"]`):

```json
{"schema_version":1,"recorded_at":"2026-10-08T04:19:43.296436Z","surface":"config.load_settings","pid":16550,"config_path":"<scratch>/806-S1/ev/invalid.toml","exception_type":"ValidationError","exception_module":"pydantic_core._pydantic_core","frames":[{"file":"nexus/config/loader.py","line":278,"function":"load_settings"},{"file":"nexus/config/loader.py","line":309,"function":"_load_from_toml"},{"file":"/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/pydantic/main.py","line":253,"function":"__init__"}],"frames_dropped":0,"details":{"kind":"validation","model":"Settings","error_count":3,"errors":[{"loc":["runtime","default_slot"],"type":"int_parsing"},{"loc":["runtime","?"],"type":"extra_forbidden"},{"loc":["runtime","?"],"type":"extra_forbidden"}]},"fingerprint":"81a1c6aaf3c48a22df9e8d84eb915d2a084672f4ab97734563cf4845f7107696"}
```

Test 3 (malformed `preferences.toml`):

```json
{"schema_version":1,"recorded_at":"2026-10-08T04:19:43.304658Z","surface":"config.preferences","pid":16550,"config_path":"<scratch>/806-S1/ev/state/preferences.toml","exception_type":"TOMLDecodeError","exception_module":"tomllib","frames":[{"file":"nexus/config/preferences.py","line":36,"function":"load_preferences"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":66,"function":"load"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":102,"function":"loads"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":326,"function":"key_value_rule"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":369,"function":"parse_key_value_pair"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":649,"function":"parse_value"}],"frames_dropped":0,"details":{"kind":"toml","line":1,"column":9},"fingerprint":"42e12f179a442d3a2e87e8798e2f4558c4b392ad87782e52ec1fe8227ba8127b"}
```

## Reachability Delta

`PYTHONPATH=$PWD $PY scripts/check_reachability.py --write-baseline --reason "#806 S1: nexus/runtime/receipts.py is imported by nexus/runtime/home.py (receipt hooks), so it joins production_reachable"`
changed `config/reachability_baseline.json` in exactly two places: the
`reason` line, and one added entry `"nexus/runtime/receipts.py"` in the
production-reachable list (between `nexus/runtime/readiness.py` and
`nexus/runtime/remote_auth.py`).

## Red Runs

(a) The `load_settings` hook removed (its `record_failure` call replaced by
`del exc, record_failure`), then reverted with `git checkout`. Tests 1, 2, 4,
5, 6, 7 and 8 fail; 3 and 9 pass:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
PASSED tests/test_runtime/test_receipts.py::test_preferences_failure_writes_a_receipt
PASSED tests/test_runtime/test_receipts.py::test_receipts_command_reports_a_broken_home
FAILED tests/test_runtime/test_receipts.py::test_malformed_toml_writes_one_sanitized_receipt
FAILED tests/test_runtime/test_receipts.py::test_validation_receipt_keeps_loc_and_type_only
FAILED tests/test_runtime/test_receipts.py::test_runtime_home_error_goes_to_the_fallback_root
FAILED tests/test_runtime/test_receipts.py::test_production_roots_without_the_seam
FAILED tests/test_runtime/test_receipts.py::test_repeats_compact_to_one_group
FAILED tests/test_runtime/test_receipts.py::test_unwritable_root_does_not_mask_the_error
FAILED tests/test_runtime/test_receipts.py::test_child_receipts_land_in_the_session_root
7 failed, 2 passed in 0.88s
```

(b) The seam export in `tests/conftest.py` replaced by `pass`, test 8 run
alone, then reverted with `git checkout`; the worktree's `.nexus/receipts`
was deleted afterwards:

```
>       assert (_snapshot(checkout), _snapshot(user)) == before
E       AssertionError: assert ([('failures-... 1228)], None) == (None, None)
E         
E         At index 0 diff: [('failures-2026-10-08.jsonl', 1228)] != None
E         Use -v to get more diff

tests/test_runtime/test_receipts.py:402: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: receipts changed (/Users/pythagor/nexus/.claude/worktrees/806-receipt-store/.nexus/receipts)
=========================== short test summary info ============================
FAILED tests/test_runtime/test_receipts.py::test_child_receipts_land_in_the_session_root
1 failed in 0.60s
```

## Proof Tails

Focused set, offline:
`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:warnings tests/test_runtime/test_receipts.py tests/test_runtime_home.py tests/test_cli_contract.py tests/test_runtime tests/test_config`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
484 passed, 18 skipped in 222.72s (0:03:42)
```

PostgreSQL. The machine-load rule of 2026-10-07 forbids builders the whole
PostgreSQL gate; it is satisfied by the focused set plus
`tests/test_orrery/test_card_identity.py` and
`tests/test_connection_lifecycle.py`, with `NEXUS_GATEWAY_PORT`,
`NEXUS_API_URL` and `NEXUS_SLOT` unset. The one-minute load was 42 when
first read; the run started after a bounded wait brought it to 22.
`NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:warnings -p tests.dbname_audit tests/test_runtime/test_receipts.py tests/test_runtime_home.py tests/test_cli_contract.py tests/test_runtime tests/test_config tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py`
(the two skips are the two parametrizations of the `requires_corpus` test
`test_card_exposure_rank_joint_and_backstage_parity`):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 17 targets: mock, postgres, qa640_1013_readiness_* x2, qa640_885_ren_replay_* x4, qa885_supervisor_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:62477 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:62478 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:62477 (psycopg2), save_04@local:62478 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
512 passed, 2 skipped in 333.98s (0:05:33)
exit 0
```

Offline runs skip every `requires_postgres` test by design (`NEXUS_RUN_POSTGRES`
unset). Offline `tests --ignore=tests/test_api --ignore=tests/test_orrery`. The first
run failed only `tests/test_doc_front_matter.py::test_declared_sources_carry_a_fresh_verified_commit`
(`AGENTS.md` declares `tests/conftest.py`; its `verified_commit` had not yet
moved). After the `AGENTS.md` commit:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
2973 passed, 562 skipped in 559.78s (0:09:19)
exit 0
```

Offline `tests/test_api tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1848 passed, 1369 skipped in 60.41s (0:01:00)
exit 0
```

`tests/test_doc_front_matter.py tests/test_reachability.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
96 passed in 14.63s
```

## Static Checks

- Black: `$PY -m black --check` on the eleven changed Python files: unchanged.
- flake8 on the changed files gives 12 diagnostics, all on untouched lines of
  `nexus/cli.py` (nine E501) and `nexus/config/loader.py` (two F541, one
  E501); the `origin/main` versions give the same 12 (compared by file, code
  and text; line numbers shift).
- mypy: `$PY -m mypy --explicit-package-bases` on the eleven changed Python
  files: `Success: no issues found in 11 source files`.
- Exception dispositions:
  `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`:
  `OK: exception disposition coverage and shrink-only baseline verified.`

## Markers

The order's marker texts do not fit the 88-column header line the lint reads,
so each header carries a short marker, as earlier markers in
`nexus/runtime/` do, and the order's full reason and safety are a comment
directly above the handler:

- `nexus/runtime/receipts.py` `_receipt_dir`: `safe-continuation; reason=806-Q12; safety=logged`.
- `nexus/runtime/receipts.py` `record_failure`: `safe-continuation; reason=no mask; safety=raise`.
- `nexus/cli.py` `run_receipts`, home locator: `degrade-read-only; reason=no home; safety=exit 1`.
- `nexus/cli.py` `run_receipts`, read: `fail; reason=bad line; safety=exit 1`.
