"""Centralized API key retrieval for NEXUS.

All runtime API key access funnels through :func:`get_secret`. On macOS, keys
live in the login Keychain and are read via the system ``security`` CLI.
1Password remains the canonical source of truth and is consulted only by
``scripts/sync_secrets.py`` during bootstrap or rotation.

Lookup order in :func:`get_secret`:

1. ``NEXUS_KEYRING_DISABLE=1`` → consult environment variables only.
2. Platform-native secret store:

   * macOS → ``security find-generic-password -s nexus-api -a <provider> -w``
   * Other platforms → ``keyring.get_password("nexus-api", <provider>)``

3. Environment variable ``<PROVIDER>_API_KEY`` (case-insensitive provider).
4. Raise :class:`MissingSecretError` with actionable remediation.

Why ``security`` CLI on macOS rather than the ``keyring`` Python library?
The ``security`` binary is Apple-signed and unconditionally trusted by
Keychain Services, so reads from items created with ``-A`` (allow any
application) are silent. The ``keyring`` library makes Keychain Services
calls from inside the Python interpreter, which is ad-hoc-signed and not in
any item's partition-list grant -- so the same read triggers a GUI prompt
that blocks unattended runs. Subprocessing to ``security`` is the
documented workaround.

The result of a successful lookup is cached for the lifetime of the
process (``functools.lru_cache``). Rotation is an offline operation
(``scripts/sync_secrets.py`` runs in a fresh process), so process-scoped
caching is safe and avoids redundant ``security`` subprocess invocations on
busy code paths (e.g., the cloud backend probes for key availability and
then later resolves it). Tests that want a fresh read can call
``get_secret.cache_clear()``.
"""
from __future__ import annotations

import functools
import os
import platform
import subprocess

SERVICE_NAME = "nexus-api"

# Apple Keychain status returned by ``security`` exit codes. 44 is
# ``errSecItemNotFound`` -- a benign "no key bootstrapped yet" signal that we
# translate into a fall-through to the env-var path. Every other non-zero
# exit code (e.g., 36 ``errSecAuthFailed`` for a locked keychain) is treated
# as an error worth surfacing.
_ERRSEC_ITEM_NOT_FOUND = 44

# Bounded wait for ``security`` subprocesses. The login keychain can stall
# indefinitely in degraded states (locked, corrupted), so this guarantees a
# NEXUS run can never block on a missing biometric / unresponsive securityd.
_SECURITY_CALL_TIMEOUT_SEC = 5.0


class MissingSecretError(RuntimeError):
    """Raised when no API key can be located for the requested provider."""


def _read_macos_keychain(account: str) -> str | None:
    """Read from the login Keychain via the ``security`` CLI.

    Returns the key on success, or ``None`` when the item is genuinely
    absent (``errSecItemNotFound`` / exit 44) so the caller can try the
    env-var fallback.

    Raises :class:`MissingSecretError` for any other failure (locked
    keychain, timeout, corrupted store). Per project policy these surface
    visibly rather than silently degrading to "no key".
    """
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                SERVICE_NAME,
                "-a",
                account,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=_SECURITY_CALL_TIMEOUT_SEC,
        )
    except FileNotFoundError:
        return None
    except subprocess.CalledProcessError as exc:
        if exc.returncode == _ERRSEC_ITEM_NOT_FOUND:
            return None
        raise MissingSecretError(
            f"Keychain read failed for provider '{account}' "
            f"(security exit {exc.returncode}). "
            f"If your login keychain is locked, unlock it and retry.\n"
            f"stderr: {(exc.stderr or '').strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MissingSecretError(
            f"Keychain read timed out for provider '{account}' after "
            f"{_SECURITY_CALL_TIMEOUT_SEC}s. The login keychain may be "
            f"locked or in a degraded state."
        ) from exc

    value = result.stdout.strip()
    return value or None


def _read_keyring_library(account: str) -> str | None:
    """Read via the cross-platform ``keyring`` library (non-Darwin fallback).

    Returns ``None`` if the library is missing or its backend raises a
    ``KeyringError`` (common on headless CI hosts with no secret store).
    Backend failures are non-fatal here so the caller falls through to the
    env-var path -- otherwise a stock Linux CI box could not run NEXUS even
    with ``<PROVIDER>_API_KEY`` correctly exported.
    """
    try:
        import keyring  # type: ignore[import-not-found]
        import keyring.errors  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return keyring.get_password(SERVICE_NAME, account)
    except keyring.errors.KeyringError:
        return None


@functools.lru_cache(maxsize=None)
def get_secret(provider: str) -> str:
    """Retrieve the API key for ``provider`` (e.g. ``"openai"``).

    Raises :class:`MissingSecretError` if no key is available. The result
    is cached per process; see module docstring for caching rationale.
    Exceptions are not cached.
    """
    provider = provider.lower()
    env_var = f"{provider.upper()}_API_KEY"

    if os.environ.get("NEXUS_KEYRING_DISABLE") == "1":
        value = os.environ.get(env_var)
        if value:
            return value
        raise MissingSecretError(
            f"NEXUS_KEYRING_DISABLE=1 but {env_var} is not set. "
            f"Either unset NEXUS_KEYRING_DISABLE to use Keychain, or "
            f"export {env_var} for this run."
        )

    if platform.system() == "Darwin":
        value = _read_macos_keychain(provider)
    else:
        value = _read_keyring_library(provider)

    if value:
        return value

    value = os.environ.get(env_var)
    if value:
        return value

    raise MissingSecretError(
        f"No API key found for provider '{provider}'. "
        f"Run `python scripts/sync_secrets.py --provider {provider}` to "
        f"populate Keychain from 1Password, or export {env_var} for a "
        f"one-off run."
    )
