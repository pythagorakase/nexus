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
  Expect only `provider`, `account`, `present`, and at most `last4`.
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

## Preserve Failure Safety

Never render provider exception messages. Verification failures expose only the
exception class and status code. Secret-store write failures must use sanitized
exceptions with no chained subprocess/backend exception that can retain argv.

## Legacy Migration

`scripts/sync_secrets.py` is a deprecated personal migration shim for legacy
1Password entries. It delegates storage to `set_secret`; do not restore
1Password bootstrap or rotation as the supported workflow.
