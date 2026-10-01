---
name: manage-api-keys
description: Manage NEXUS provider API keys in the canonical macOS Keychain or cross-platform keyring store. Use when setting or rotating a key, checking masked presence, verifying credentials against a real provider, troubleshooting secret-store access, or migrating legacy 1Password entries.
---

# Manage API Keys

Use the settings pane's API KEYS card as the supported operator path. Keep
plaintext out of output, logs, exception messages, source, shell history, and
React Query state.

## Choose the Path

- To inspect presence, use the API KEYS card or `GET /api/secrets/status`.
  Expect only `provider`, `account`, `present`, at most `last4`, and the
  seat-derived `required` and `required_by` (seat and model ID) fields.
  Add `?slot=N` to resolve requiredness against that slot's story pins.
- To set or rotate, enter the value in the card and commit it. Runtime code
  must call `nexus.util.secret_manager.set_secret(account, key)`; do not add a
  second writer.
- To verify, use the card or `POST /api/secrets/{provider}/verify`. Verification
  makes a real models-list call and returns a sanitized class/status result.
- To read inside runtime code, call `get_secret(account)`.

## Follow Registry Mapping

Derive providers from `[global.model.api_models]` and honor `ui_visible`:

- Native providers use the provider name as the account.
- Non-native providers require `api_key_secret`; use its value as the account.
- Exclude keyless and UI-hidden providers.

`set_secret` lowercases the account, rejects blank values, writes to service
`nexus-api`, and clears the `get_secret` cache after success. On macOS it uses
delete-then-add with `security ... -A`; do not replace this with `-U`, which can
trigger a blocking ACL prompt. Elsewhere it uses `keyring.set_password`.

## Handle Environment-Only Mode

`NEXUS_KEYRING_DISABLE=1` is a read-only CI/debug escape hatch. Reads use
`<ACCOUNT>_API_KEY`; writes must fail loudly until the flag is unset.

## Keep Tests Off the Owner's Store

Every store operation goes through a `SecretBackend` (`read`, `write`,
`delete`). Tests inject `InMemorySecretBackend` with `use_secret_backend`,
usually through the `in_memory_secret_store` fixture. The session guard in
`tests/secret_store_guard.py` fails any test that reaches the real backends,
a `keyring` backend, or the `security` CLI. Do not unset
`NEXUS_KEYRING_DISABLE` or shell out to `security` to test storage.

`NEXUS_RUN_SECRET_STORE=1` runs the macOS integration test against a
disposable keychain file under pytest's base temp directory and a throwaway
service. Never point a test at service `nexus-api` or the login keychain.

The guard covers credential-store access in the pytest process. A `security`
spawn runs only as an argv list that exactly matches an open backend or
disposable-keychain scope. Every child process gets `NEXUS_KEYRING_DISABLE=1`
whatever the opt-in flags and whatever its `env` says; a child that genuinely
needs store access gets `env=secret_store_guard.store_access_env(...)`, with
the reason beside the call. `os.exec*`, fork-then-exec, a renamed copy of
`security`, a child that runs `security` itself, and `ctypes` calls into the
Security framework are not covered. It does not guard protected paths, and
there is no launcher preflight outside pytest.

## Preserve Failure Safety

Never render provider exception messages. Verification failures expose only the
exception class and status code, or the sanitized `SecretStoreAccessError`
message when the store itself could not be read; that message never carries the
`security` CLI's stderr or stdout, or key material. Secret-store write failures
must use sanitized exceptions with no chained subprocess/backend exception that
can retain argv.

On macOS, a login Keychain that cannot be read raises `SecretStoreAccessError`,
never `MissingSecretError`, and `get_secret` does not fall back to the
environment variable after it (the `keyring` backend elsewhere still reads a
`KeyringError` as absent). Its `reason` is `locked` (a `security` exit other than 44;
unlock the login keychain in Keychain Access or with `security unlock-keychain`
and retry), `timeout` (the keychain did not answer within the `security` call
timeout; unlock it, then retry), or `no_security_cli` (no `security` on the
process's `PATH`; put `/usr/bin` back on it). The doctor lists such an account
as unreadable, and the card's status and write answer 503 with the remediation.

## Legacy Migration

`scripts/sync_secrets.py` is a deprecated personal migration shim for legacy
1Password entries. It delegates storage to `set_secret`; do not restore
1Password bootstrap or rotation as the supported workflow.
