# Verification: Keychain Access Errors and the Verified Mark (#821, Order 821-B)

Branch `claude/821-access-errors-and-verified-mark`, cut from `origin/main` at
`41783c1d`. `origin/main` had not moved when the branch was pushed, so no
rebase was needed. Every command ran from the worktree root with the shared
interpreter (`$PY` = `/Users/pythagor/nexus/.venv/bin/python`) and
`PYTHONPATH=$PWD`; `nexus.__file__` resolved inside the worktree. No gateway
was started, no `save_NN` or `NEXUS_template` was written, no paid call was
made, and every test used an injected secret backend.

## Red Runs against `main`

### 1. The New Tests against `main` Exactly

`main` has none of the names the tests need, so the session stops at the
shared fixture's import.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider tests/test_secret_manager.py
```

```text
ImportError while loading conftest '.../tests/conftest.py'.
tests/conftest.py:39: in <module>
    from nexus.util.secret_manager import (
E   ImportError: cannot import name 'keychain_read_error' from 'nexus.util.secret_manager'
```

### 2. Consumer Tests with Only the Secret-Manager Change

`nexus/util/secret_manager.py` carried items 1 to 3 (the error class, the
translation, the uncached reader); `secrets_endpoints.py`, `readiness.py` and
`cli.py` were still `main`. Each consumer test fails for the reason the order
names.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit tests/test_secret_manager.py tests/test_api/test_secrets_endpoints.py tests/test_runtime/test_readiness.py tests/test_cli_contract.py -k "keychain_read_error or never_falls_back or uncached or behind_the_process_cache or out_of_band_rotation or unreadable"
```

```text
E       AssertionError: assert '6TZI' == '8jB7'                                  (status served the cached key)
E       At index 0 diff: ('/v1/models', 'Bearer eg8V...') != ('/v1/models', 'Bearer Svny...')   (verify sent the cached key)
E       nexus.util.secret_manager.SecretStoreAccessError: The login keychain refused ... (status/PUT: no 503, the error escaped)
E       {'detail': 'SecretStoreAccessError'} != {'detail': "The login keychain refused ..."}   (verify printed the class name)
E       nexus.util.secret_manager.SecretStoreAccessError: ... account 'openai' ...   (doctor seat check: escaped)
E       AssertionError: assert 'The login ke...n) and retry.' == 'The login ke...ity exit 36).'   (postgres.reachable: caught as RuntimeError, "Correct [api.database]")
E       nexus.util.secret_manager.SecretStoreAccessError: ... 'cloudflare_access_client_id' ...   (gateway.reachable, inspect slot, status: escaped)
FAILED tests/test_api/test_secrets_endpoints.py::test_status_reads_the_store_behind_the_process_cache
FAILED tests/test_api/test_secrets_endpoints.py::test_verify_sends_an_out_of_band_rotation_to_the_provider
FAILED tests/test_api/test_secrets_endpoints.py::test_unreadable_store_fails_status_and_put_with_its_remediation
FAILED tests/test_api/test_secrets_endpoints.py::test_verify_of_an_unreadable_store_names_its_remediation
FAILED tests/test_runtime/test_readiness.py::test_seat_secrets_name_an_unreadable_store
FAILED tests/test_runtime/test_readiness.py::test_postgres_reachable_names_an_unreadable_password_store
FAILED tests/test_runtime/test_readiness.py::test_gateway_reachable_names_an_unreadable_access_store
FAILED tests/test_cli_contract.py::test_http_command_unreadable_access_store_is_a_config_error
FAILED tests/test_cli_contract.py::test_runtime_status_names_an_unreadable_access_store
9 failed, 7 passed, 174 deselected, 5 warnings in 2.45s
```

The seven passing tests are the secret-manager tests, green once the module
change exists.

### 3. The Card Tests against `main`'s `useSecrets.ts` and `SettingsPane.tsx`

```sh
cd ui && npx vitest run client/src/components/nexus/SettingsPane.test.tsx
```

```text
 FAIL  ... > SettingsPane API keys > clears a verified mark when the key is replaced
 FAIL  ... > SettingsPane API keys > a status refresh clears the verified mark even when the last four match
 FAIL  ... > SettingsPane model IDs > re-derives the slot's required keys when the Skald pin changes
AssertionError: expected undefined to be 'GET /api/secrets/status?slot=4' // Object.is equality
 FAIL  ... > SettingsPane API keys > fetches key status again when the pane opens
Error: expect(element).toHaveAttribute("placeholder", "••••••••9876") ... Received: placeholder="••••••••wxyz"
 FAIL  ... > SettingsPane API keys > shows an unreadable store in the card's existing alert
TestingLibraryElementError: Unable to find an element by: [data-testid="keys-error"]
 FAIL  ... > preference save failures (#961) > shows the rejection for an online HTTP failure and keeps the saved font
AssertionError: expected [ 'PATCH /api/preferences' ] to deeply equal [ …(2) ]
      Tests  6 failed | 13 passed (19)
```

With `refetchOnMount: "always"` in place and the `dataUpdatedAt` effect
removed, only the refresh test fails; the replace test still passes on the
per-row backstop in `commit`:

```text
   × SettingsPane API keys > a status refresh clears the verified mark even when the last four match 1077ms
      Tests  1 failed | 18 passed (19)
```

## Green Runs at the Pushed Head

### The Order's PostgreSQL Proof

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_secret_manager.py tests/test_api/test_secrets_endpoints.py tests/test_api/test_secret_requirements.py tests/test_runtime/test_readiness.py tests/test_runtime/test_readiness_pg.py tests/test_cli_contract.py tests/test_secret_store_guard.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 13 targets: postgres, qa640_1013_readiness_* x2, qa640_offline_gate_* x2, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
291 passed, 2 skipped, 7 warnings in 125.78s (0:02:05)
```

The two skips are the `live_llm` tests (`test_secrets_endpoints.py:384`,
`:395`: "Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.").

### The Client

```sh
npm --prefix ui ci
npm --prefix ui run check
npm --prefix ui test
```

```text
> tsc && npm run check:design-sync
> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
(exit 0)

 Test Files  35 passed (35)
      Tests  465 passed (465)
```

### Offline Suites

```sh
$PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2637 passed, 420 skipped, 8 warnings in 412.09s (0:06:52)
```

```sh
$PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1820 passed, 742 skipped, 7 warnings in 38.32s
```

```sh
$PY -m pytest -q -p no:cacheprovider tests/test_reachability.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.33s
```

### Format, Lint, Types

```text
$PY -m black --check <the ten changed Python files>   -> 10 files would be left unchanged.
$PY -m flake8 <the changed files except nexus/cli.py> -> exit 0
$PY -m flake8 nexus/cli.py                            -> 9 E501, the same 9 as origin/main's copy (none on a changed line)
$PY -m mypy nexus/util/secret_manager.py nexus/api/secrets_endpoints.py nexus/runtime/readiness.py nexus/cli.py
                                                      -> Success: no issues found in 4 source files
```

### After the Review Fixes (`d50e5714`)

`d50e5714` removes `tests/test_secret_manager.py`'s import of `tests.conftest`
(the fixture parameter is now annotated `InMemorySecretBackend`) and changes
only Markdown otherwise. The changed test file and the guard tests, rerun at
`d50e5714`:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit tests/test_secret_manager.py tests/test_secret_store_guard.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
108 passed in 3.53s
```

`$PY -m black --check tests/test_secret_manager.py` -> 1 file would be left
unchanged; `$PY -m flake8 tests/test_secret_manager.py` -> exit 0.

### After the Second Review Fix (`6f73a3ab`)

`6f73a3ab` scopes the unreadable-store rule to the macOS Keychain in the
`manage-api-keys` skill and the `_check_seat_secrets` docstring: only
`MacOSKeychainBackend.read` raises `SecretStoreAccessError`, and the `keyring`
backend used elsewhere still reads a `KeyringError` as absent. No code path
changed. The readiness and secret-manager tests, rerun at `6f73a3ab`:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit tests/test_runtime/test_readiness.py tests/test_secret_manager.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
46 passed in 10.99s
```

`$PY -m black --check nexus/runtime/readiness.py` -> 1 file would be left
unchanged.

### Not Run

`tests/test_secret_store_integration.py::test_missing_security_executable_is_an_access_error`
is written and not run: it needs `NEXUS_RUN_SECRET_STORE=1` (the disposable
keychain), which this order does not opt in to.

## Every `MissingSecretError` Catch and Its Handling Now

| Site | `MissingSecretError` | `SecretStoreAccessError` |
| --- | --- | --- |
| `nexus/api/secrets_endpoints.py` `_status_for` | absent key (`present: false`), unchanged | `HTTPException(503, detail=str(exc))`: status GET and PUT fail whole |
| `nexus/api/secrets_endpoints.py` `verify_secret` (broad `except`) | `verified: false`, detail `MissingSecretError`, unchanged | explicit `except` first: `verified: false`, `detail=str(exc)` |
| `nexus/runtime/readiness.py` `_check_postgres_reachable` | "Correct [api.database] ..." remediation, unchanged | explicit `except` first: `_failed(exc.failure, exc.remediation)` |
| `nexus/runtime/readiness.py` `_check_seat_secrets` | `missing:` list, "Store the missing keys" remediation, unchanged | `unreadable:` list; any unreadable account fails with the first one's remediation (sorted) |
| `nexus/runtime/readiness.py` `_check_gateway_reachable` | "Store the Cloudflare Access service token accounts" remediation, unchanged | explicit `except` first: `_failed(exc.failure, exc.remediation)` |
| `nexus/cli.py` `_CREDENTIAL_ERRORS` (and `_TRANSPORT_ERRORS`, which spreads it) | `config_error` envelope | added beside it: `config_error` envelope |
| `nexus/cli.py` `run_up` | `{"success": False, "error": str(exc)}` | added beside it: same |
| `nexus/cli.py` `run_status` (reached through `Supervisor._fetch_runtime_status`, which catches only `RequestException`) | `{"success": False, "error": str(exc)}` | added beside it: same |
| `scripts/freestyle_api_query.py:707` | logs and exits 1 | out of scope by name: propagates as a traceback |
| `scripts/sync_secrets.py:91` (deprecated, broad `except Exception`) | prints `[FAIL]` | out of scope by name: prints `[FAIL]` with the sanitized message |

`MacOSKeychainBackend.read` no longer raises `MissingSecretError` at all: a
non-44 exit, a timeout, and a missing `security` executable each raise
`keychain_read_error(...) from exc`; exit 44 still returns `None`.

## After the Independent Review

Astra's P2 at `c28de203`: a verification still in flight when a status refresh
lands (the store rotated outside the app, then the pane reopened or another row
was replaced) added its row to `verified` after the refresh had cleared the set,
so the card marked the rotated key Verified although it was never verified.

Fix, inside `KeysSection` only (`ui/client/src/components/nexus/SettingsPane.tsx`):
a `revisionRef` holds the latest `dataUpdatedAt`, set in the same effect that
clears the set; `verify` captures `startedAt = revisionRef.current` before the
request and discards a success whose revision has since changed (no mark, no
error). A failed verification and a thrown error behave as before. The per-row
clearing in `commit` and the whole-set clearing on `dataUpdatedAt` are unchanged;
no new visual state, class or label.

New test: `SettingsPane API keys > a verification started before a refresh does
not mark the refreshed row` (verify POST held open on a deferred promise, clock
advanced with `vi.useFakeTimers({ toFake: ["Date"] })` and `vi.setSystemTime`,
status invalidated and answered with `last4` `rot8`, then the held POST resolved
with `verified: true`).

### Red on `c28de203` (Component Hunk Absent, New Test Present)

`npm --prefix ui test -- -t "a verification started before a refresh" client/src/components/nexus/SettingsPane.test.tsx`

```
 FAIL  src/components/nexus/SettingsPane.test.tsx > SettingsPane API keys > a verification started before a refresh does not mark the refreshed row
Error: expect(element).toHaveClass("present")

Expected the element to have class:
  present
Received:
  key-status verified

 Test Files  1 failed (1)
      Tests  1 failed | 19 skipped (20)
```

### Green with the Fix

`npm --prefix ui run check`

```
> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
```

(exit 0)

`npm --prefix ui test`

```
 Test Files  35 passed (35)
      Tests  466 passed (466)
```

`$PY -m pytest -q tests/test_api/test_secrets_endpoints.py tests/test_secret_manager.py`
(unchanged Python, sanity tail; the two skips are the `live_llm` tests)

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
34 passed, 2 skipped, 7 warnings in 4.51s
```
