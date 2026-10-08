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

Regenerated at `e846614e` (the review fixes added a non-identifier
`[usage.daily_allowance]` key to test 2's configuration, so its receipt now
holds four errors). The script below, saved as `<scratch>/806-S1/ev_lines.py`,
repeats tests 1-3 with the helpers in `tests/test_runtime/test_receipts.py`
and prints the last receipt line after each failure. It was run from the
worktree root as

```
PYTHONPATH=$PWD $PY <scratch>/806-S1/ev_lines.py <scratch>/806-S1/ev > <scratch>/806-S1/ev_lines.out
```

with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset and
`NEXUS_KEYRING_DISABLE=1`; the lines below are its stdout with the scratch
path shortened to `<scratch>`. None contains either planted string
(`grep -c PLANTED` on the output prints `0`), a message, an input or a source
line.

```python
"""Print one receipt line from each of tests 1-3 of test_receipts.py.

Usage, from the worktree root:
    PYTHONPATH=$PWD $PY <scratch>/806-S1/ev_lines.py <scratch>/806-S1/ev
"""

import os
import sys
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)
os.environ["NEXUS_TEST_RECEIPTS_DIR"] = str(out / "receipts")
os.environ.pop("NEXUS_HOME", None)
os.environ.pop("NEXUS_RUNTIME_CONFIG", None)

from nexus.config.loader import load_settings  # noqa: E402
from nexus.config.preferences import load_preferences, preferences_path  # noqa: E402
from tests.test_runtime import test_receipts as t  # noqa: E402

home = out / "receipts" / "home"
for label, path in (
    ("test 1", t._broken_config(out)),
    ("test 2", t._invalid_config(out)),
):
    try:
        load_settings(path)
    except Exception as exc:
        print(label, "raised", type(exc).__name__, file=sys.stderr)
    print(t._receipt_lines(home)[-1].decode())

settings = load_settings()
runtime = settings.runtime.model_copy(update={"state_dir": str(out / "state")})
settings = settings.model_copy(update={"runtime": runtime})
prefs = preferences_path(settings)
prefs.parent.mkdir(parents=True)
prefs.write_text(
    f"theme = {t.PLANTED_SECRET}\nwizard_model = {t.PLANTED_PROMPT}\n",
    encoding="utf-8",
)
try:
    load_preferences(settings)
except Exception as exc:
    print("test 3 raised", type(exc).__name__, file=sys.stderr)
print(t._receipt_lines(home)[-1].decode())
```

Test 1 (malformed TOML, `details == {"kind": "toml", "line": 3, "column": 11}`):

```json
{"schema_version":1,"recorded_at":"2026-10-08T05:13:06.459743Z","surface":"config.load_settings","pid":33996,"config_path":"<scratch>/806-S1/ev/broken.toml","exception_type":"TOMLDecodeError","exception_module":"tomllib","frames":[{"file":"nexus/config/loader.py","line":278,"function":"load_settings"},{"file":"nexus/config/loader.py","line":299,"function":"_load_from_toml"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":66,"function":"load"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":102,"function":"loads"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":326,"function":"key_value_rule"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":369,"function":"parse_key_value_pair"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":649,"function":"parse_value"}],"frames_dropped":0,"details":{"kind":"toml","line":3,"column":11},"fingerprint":"d187a33a6f219a3c0244ab0b8f2a3ca2496d5a22bd4b3f89c46eec650a9fd179"}
```

Test 2 (validation: `loc` and `type` only; both unknown `[runtime]` keys are
`["runtime", "?"]`, and the prompt-named `[usage.daily_allowance]` key is
`["usage", "daily_allowance", "?"]`):

```json
{"schema_version":1,"recorded_at":"2026-10-08T05:13:06.711334Z","surface":"config.load_settings","pid":33996,"config_path":"<scratch>/806-S1/ev/invalid.toml","exception_type":"ValidationError","exception_module":"pydantic_core._pydantic_core","frames":[{"file":"nexus/config/loader.py","line":278,"function":"load_settings"},{"file":"nexus/config/loader.py","line":309,"function":"_load_from_toml"},{"file":"/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/pydantic/main.py","line":253,"function":"__init__"}],"frames_dropped":0,"details":{"kind":"validation","model":"Settings","error_count":4,"errors":[{"loc":["runtime","default_slot"],"type":"int_parsing"},{"loc":["runtime","?"],"type":"extra_forbidden"},{"loc":["runtime","?"],"type":"extra_forbidden"},{"loc":["usage","daily_allowance","?"],"type":"int_parsing"}]},"fingerprint":"81a1c6aaf3c48a22df9e8d84eb915d2a084672f4ab97734563cf4845f7107696"}
```

Test 3 (malformed `preferences.toml`):

```json
{"schema_version":1,"recorded_at":"2026-10-08T05:13:06.719723Z","surface":"config.preferences","pid":33996,"config_path":"<scratch>/806-S1/ev/state/preferences.toml","exception_type":"TOMLDecodeError","exception_module":"tomllib","frames":[{"file":"nexus/config/preferences.py","line":36,"function":"load_preferences"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":66,"function":"load"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":102,"function":"loads"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":326,"function":"key_value_rule"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":369,"function":"parse_key_value_pair"},{"file":"/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/tomllib/_parser.py","line":649,"function":"parse_value"}],"frames_dropped":0,"details":{"kind":"toml","line":1,"column":9},"fingerprint":"42e12f179a442d3a2e87e8798e2f4558c4b392ad87782e52ec1fe8227ba8127b"}
```

## Reachability Delta

`PYTHONPATH=$PWD $PY scripts/check_reachability.py --write-baseline --reason "#806 S1: nexus/runtime/receipts.py is imported by nexus/runtime/home.py (receipt hooks), so it joins production_reachable"`
changed `config/reachability_baseline.json` in exactly two places: the
`reason` line, and one added entry `"nexus/runtime/receipts.py"` in the
production-reachable list (between `nexus/runtime/readiness.py` and
`nexus/runtime/remote_auth.py`).

## Red Runs

Rerun at `e846614e` (eleven tests after the review fixes). Each plant was reverted
with `git checkout` before anything was committed.

(a) The `load_settings` hook removed (its `record_failure(...)` call in
`nexus/config/loader.py` replaced by `del exc, record_failure`). Tests 1, 2,
4, 5, 6, 7 and 8 fail, and so does
`test_home_equal_to_user_home_reads_each_receipt_once`, which plants its
receipt through `load_settings`; 3, 9 and
`test_undecodable_receipt_line_is_a_read_error` pass:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:warnings -rpf tests/test_runtime/test_receipts.py
tests/test_runtime/test_receipts.py:485: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
PASSED tests/test_runtime/test_receipts.py::test_preferences_failure_writes_a_receipt
PASSED tests/test_runtime/test_receipts.py::test_receipts_command_reports_a_broken_home
PASSED tests/test_runtime/test_receipts.py::test_undecodable_receipt_line_is_a_read_error
FAILED tests/test_runtime/test_receipts.py::test_malformed_toml_writes_one_sanitized_receipt
FAILED tests/test_runtime/test_receipts.py::test_validation_receipt_keeps_loc_and_type_only
FAILED tests/test_runtime/test_receipts.py::test_runtime_home_error_goes_to_the_fallback_root
FAILED tests/test_runtime/test_receipts.py::test_production_roots_without_the_seam
FAILED tests/test_runtime/test_receipts.py::test_repeats_compact_to_one_group
FAILED tests/test_runtime/test_receipts.py::test_unwritable_root_does_not_mask_the_error
FAILED tests/test_runtime/test_receipts.py::test_child_receipts_land_in_the_session_root
FAILED tests/test_runtime/test_receipts.py::test_home_equal_to_user_home_reads_each_receipt_once
8 failed, 3 passed in 0.99s
```

(b) The seam export in `tests/conftest.py`
(`os.environ[TEST_RECEIPTS_ENV] = _RECEIPT_SEAM`) replaced by `pass`, test 8
run alone with `NEXUS_TEST_RECEIPTS_DIR` also unset in the shell; the
worktree's `.nexus/receipts` was deleted afterwards:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:warnings tests/test_runtime/test_receipts.py::test_child_receipts_land_in_the_session_root
>       assert (_snapshot(checkout), _snapshot(user)) == before
E       AssertionError: assert ([('failures-... 1228)], None) == (None, None)
E         
E         At index 0 diff: [('failures-2026-10-08.jsonl', 1228)] != None
E         Use -v to get more diff

tests/test_runtime/test_receipts.py:422: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: receipts changed (/Users/pythagor/nexus/.claude/worktrees/806-receipt-store/.nexus/receipts)
=========================== short test summary info ============================
FAILED tests/test_runtime/test_receipts.py::test_child_receipts_land_in_the_session_root
1 failed in 0.49s
```

Review-fix plants at `e846614e`, each run as
`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:warnings tests/test_runtime/test_receipts.py`
and reverted from a scratch copy:

- `_read_receipts` back to `path.open("r", encoding="utf-8")`:
  `FAILED ...::test_undecodable_receipt_line_is_a_read_error`, `1 failed, 10 passed`.
- `run_receipts` reading the home root whenever it is known:
  `FAILED ...::test_home_equal_to_user_home_reads_each_receipt_once`, `1 failed, 10 passed`.
- `_safe_token(str(part))` replaced by `str(part)` for `loc` parts:
  `FAILED ...::test_validation_receipt_keeps_loc_and_type_only`, `1 failed, 10 passed`.
- The `last_seen` sort removed, and separately made ascending:
  `FAILED ...::test_repeats_compact_to_one_group`, `1 failed, 10 passed` each.

## Proof Tails

Focused set, offline, at `e846614e`:
`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:warnings tests/test_runtime/test_receipts.py tests/test_runtime_home.py tests/test_cli_contract.py tests/test_runtime tests/test_config tests/test_cli_reference_doc.py tests/test_doc_front_matter.py tests/test_reachability.py`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
594 passed, 18 skipped in 209.59s (0:03:29)
```

The PostgreSQL and whole-tree offline tails below were recorded before
`e846614e`, with the evidence commit `e7f7a29d`. `e846614e` changes no PostgreSQL path
(the receipt reader, `run_receipts`, comments, docs and offline tests); the
coordinator's whole-tree gate at the final commit supersedes them.

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

## Static Checks

At `e846614e`, on every Python file the branch changes
(`git diff --name-only origin/main...HEAD`). The flake8 gate is no new
diagnostics: the branch's 12 are the `origin/main` copies' 12, by file, code
and text (line numbers shift by the added code); `nexus/runtime/receipts.py`
and `tests/test_runtime/test_receipts.py` are new and have none.

```
$ $PY -m black --check nexus/cli.py nexus/cli_contract.py nexus/config/loader.py nexus/config/preferences.py nexus/runtime/contract.py nexus/runtime/home.py nexus/runtime/home_plan.py nexus/runtime/receipts.py tests/conftest.py tests/test_runtime/test_receipts.py tests/test_runtime_home.py
All done! ✨ 🍰 ✨
11 files would be left unchanged.

$ $PY -m flake8 nexus/cli.py nexus/cli_contract.py nexus/config/loader.py nexus/config/preferences.py nexus/runtime/contract.py nexus/runtime/home.py nexus/runtime/home_plan.py nexus/runtime/receipts.py tests/conftest.py tests/test_runtime/test_receipts.py tests/test_runtime_home.py   # branch, at HEAD
nexus/cli.py:976:89: E501 line too long (92 > 88 characters)
nexus/cli.py:4330:89: E501 line too long (93 > 88 characters)
nexus/cli.py:4788:89: E501 line too long (113 > 88 characters)
nexus/cli.py:4817:89: E501 line too long (118 > 88 characters)
nexus/cli.py:4857:89: E501 line too long (90 > 88 characters)
nexus/cli.py:4942:89: E501 line too long (151 > 88 characters)
nexus/cli.py:4968:89: E501 line too long (94 > 88 characters)
nexus/cli.py:4969:89: E501 line too long (103 > 88 characters)
nexus/cli.py:4988:89: E501 line too long (101 > 88 characters)
nexus/config/loader.py:365:13: F541 f-string is missing placeholders
nexus/config/loader.py:368:15: F541 f-string is missing placeholders
nexus/config/loader.py:388:89: E501 line too long (89 > 88 characters)
(exit 1)

$ cd <scratch>/806-S1/main && $PY -m flake8 --config <worktree>/.flake8 nexus/cli.py nexus/cli_contract.py nexus/config/loader.py nexus/config/preferences.py nexus/runtime/contract.py nexus/runtime/home.py nexus/runtime/home_plan.py tests/conftest.py tests/test_runtime_home.py   # origin/main copies
nexus/cli.py:976:89: E501 line too long (92 > 88 characters)
nexus/cli.py:4330:89: E501 line too long (93 > 88 characters)
nexus/cli.py:4696:89: E501 line too long (113 > 88 characters)
nexus/cli.py:4725:89: E501 line too long (118 > 88 characters)
nexus/cli.py:4765:89: E501 line too long (90 > 88 characters)
nexus/cli.py:4850:89: E501 line too long (151 > 88 characters)
nexus/cli.py:4876:89: E501 line too long (94 > 88 characters)
nexus/cli.py:4877:89: E501 line too long (103 > 88 characters)
nexus/cli.py:4896:89: E501 line too long (101 > 88 characters)
nexus/config/loader.py:357:13: F541 f-string is missing placeholders
nexus/config/loader.py:360:15: F541 f-string is missing placeholders
nexus/config/loader.py:380:89: E501 line too long (89 > 88 characters)
(exit 1)

$ $PY -m mypy --explicit-package-bases nexus/cli.py nexus/cli_contract.py nexus/config/loader.py nexus/config/preferences.py nexus/runtime/contract.py nexus/runtime/home.py nexus/runtime/home_plan.py nexus/runtime/receipts.py tests/conftest.py tests/test_runtime/test_receipts.py tests/test_runtime_home.py
Success: no issues found in 11 source files

$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

## Markers

The order's marker texts do not fit the 88-column header line the lint reads,
so each header carries a short marker, as earlier markers in
`nexus/runtime/` do, and the order's full reason and safety are a comment
directly above the handler:

- `nexus/runtime/receipts.py` `_receipt_dir`: `safe-continuation; reason=Q12; safety=receipted` (the `RuntimeHomeError` already wrote its own `runtime.home` receipt to the fallback root).
- `nexus/runtime/receipts.py` `record_failure`: `safe-continuation; reason=no mask; safety=caller` (the handler prints to stderr; the caller re-raises).
- `nexus/cli.py` `run_receipts`, home locator: `degrade-read-only; reason=no home; safety=exit 1`.
- `nexus/cli.py` `run_receipts`, read: `fail; reason=bad line; safety=exit 1`.
