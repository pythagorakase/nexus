"""Centralized API key storage for NEXUS.

All runtime API key access funnels through :func:`get_secret`, and all writes
funnel through :func:`set_secret`. The platform secret store is the canonical
source of truth: macOS uses the login Keychain through the system ``security``
CLI, while other platforms use the ``keyring`` library.

Lookup order in :func:`get_secret`:

1. ``NEXUS_KEYRING_DISABLE=1`` → consult environment variables only.
2. The active :class:`SecretBackend` (the platform-native store by default):

   * macOS → ``security find-generic-password -s nexus-api -a <provider> -w``
   * Other platforms → ``keyring.get_password("nexus-api", <provider>)``

3. Environment variable ``<PROVIDER>_API_KEY`` (case-insensitive provider).
4. Raise :class:`MissingSecretError` with actionable remediation.

Backends
--------
Every store operation goes through a :class:`SecretBackend` (``read``,
``write``, ``delete``). :func:`platform_backend` selects the production store
for this platform: :class:`MacOSKeychainBackend` on Darwin and
:class:`KeyringLibraryBackend` elsewhere, both on service ``nexus-api``.
:func:`use_secret_backend` routes :func:`get_secret` and :func:`set_secret`
through another backend for the duration of a ``with`` block. Tests inject
:class:`InMemorySecretBackend`; the opt-in platform-store integration test
injects a Keychain backend bound to a disposable keychain file and service.

Why ``security`` CLI on macOS rather than the ``keyring`` Python library?
The ``security`` binary is Apple-signed and unconditionally trusted by
Keychain Services, so reads from items created with ``-A`` (allow any
application) are silent. The ``keyring`` library makes Keychain Services
calls from inside the Python interpreter, which is ad-hoc-signed and not in
any item's partition-list grant -- so the same read triggers a GUI prompt
that blocks unattended runs. Subprocessing to ``security`` is the
documented workaround.

The result of a successful lookup is cached for the lifetime of the process
(``functools.lru_cache``). :func:`set_secret` clears that cache after every
successful write so rotations are visible immediately, and entering or
leaving :func:`use_secret_backend` clears it so no value crosses backends.
Tests that need an unconditional fresh read can also call
``get_secret.cache_clear()``.
"""

from __future__ import annotations

import contextlib
import functools
import os
import platform
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

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


class SecretBackend(Protocol):
    """One secret-store namespace used by :func:`get_secret`/:func:`set_secret`."""

    def read(self, account: str) -> str | None:
        """Return the stored key, or ``None`` when ``account`` is absent."""
        ...

    def write(self, account: str, key: str) -> None:
        """Store or replace the key for ``account``."""
        ...

    def delete(self, account: str) -> None:
        """Remove ``account``; an already-absent account is not an error."""
        ...


class MacOSKeychainBackend:
    """Keychain items reached through Apple's signed ``security`` CLI.

    With ``keychain=None`` every command searches the user's keychain list,
    which is the owner's login Keychain in production. An explicit
    ``keychain`` path scopes every command to that one keychain file.
    """

    def __init__(
        self,
        service: str = SERVICE_NAME,
        keychain: Path | None = None,
    ) -> None:
        self.service = service
        self.keychain = keychain

    def _argv(self, command: str, account: str, *options: str) -> list[str]:
        """Build one ``security`` command scoped to this service and keychain."""
        argv = ["security", command, "-s", self.service, "-a", account, *options]
        if self.keychain is not None:
            argv.append(os.fspath(self.keychain))
        return argv

    def read(self, account: str) -> str | None:
        """Read from the Keychain via the ``security`` CLI.

        Returns the key on success, or ``None`` when the item is genuinely
        absent (``errSecItemNotFound`` / exit 44) so the caller can try the
        env-var fallback.

        Raises :class:`MissingSecretError` for any other failure (locked
        keychain, timeout, corrupted store). Per project policy these surface
        visibly rather than silently degrading to "no key".
        """
        try:
            result = subprocess.run(
                self._argv("find-generic-password", account, "-w"),
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

    def write(self, account: str, key: str) -> None:
        """Replace a Keychain item without exposing ``key`` on failure.

        Delete-then-add intentionally avoids ``security ... -U``: updating an
        existing item can trigger a GUI ACL prompt, while a fresh item created
        by Apple's signed ``security`` binary completes silently. ``-A``
        preserves silent reads from unattended NEXUS processes.
        """
        try:
            # A missing item returns non-zero and is expected on the first write.
            subprocess.run(
                self._argv("delete-generic-password", account),
                capture_output=True,
                timeout=_SECURITY_CALL_TIMEOUT_SEC,
            )
            subprocess.run(
                self._argv("add-generic-password", account, "-A", "-w", key),
                capture_output=True,
                check=True,
                timeout=_SECURITY_CALL_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            # TimeoutExpired retains the full argv (including the key), so sever
            # the exception chain and emit only sanitized context.
            raise RuntimeError(
                f"Keychain write timed out for account '{account}' after "
                f"{_SECURITY_CALL_TIMEOUT_SEC}s."
            ) from None
        except subprocess.CalledProcessError as exc:
            # CalledProcessError also retains argv. Never include stderr: a
            # secret store's diagnostics are not a safe response or logging
            # surface.
            raise RuntimeError(
                f"Keychain write failed for account '{account}' "
                f"(security exit {exc.returncode})."
            ) from None
        except OSError:
            raise RuntimeError(
                f"Keychain write could not start for account '{account}'."
            ) from None

    def delete(self, account: str) -> None:
        """Remove a Keychain item; ``errSecItemNotFound`` means already gone."""
        try:
            result = subprocess.run(
                self._argv("delete-generic-password", account),
                capture_output=True,
                timeout=_SECURITY_CALL_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Keychain delete timed out for account '{account}' after "
                f"{_SECURITY_CALL_TIMEOUT_SEC}s."
            ) from None
        except OSError:
            raise RuntimeError(
                f"Keychain delete could not start for account '{account}'."
            ) from None
        if result.returncode not in (0, _ERRSEC_ITEM_NOT_FOUND):
            raise RuntimeError(
                f"Keychain delete failed for account '{account}' "
                f"(security exit {result.returncode})."
            )


class KeyringLibraryBackend:
    """Items in the cross-platform ``keyring`` library's default store."""

    def __init__(self, service: str = SERVICE_NAME) -> None:
        self.service = service

    def read(self, account: str) -> str | None:
        """Read via the ``keyring`` library.

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
            return keyring.get_password(self.service, account)
        except keyring.errors.KeyringError:
            return None

    def write(self, account: str, key: str) -> None:
        """Replace a keyring item, failing loudly and safely."""
        try:
            import keyring  # type: ignore[import-not-found]
        except ImportError:
            raise RuntimeError(
                "The keyring package is required to store API keys on this platform."
            ) from None

        try:
            keyring.set_password(self.service, account, key)
        except Exception as exc:  # noqa: BLE001 - sanitize backend-specific failures
            raise RuntimeError(
                f"Keyring write failed for account '{account}' "
                f"({type(exc).__name__})."
            ) from None

    def delete(self, account: str) -> None:
        """Remove a keyring item; an item confirmed absent is already gone."""
        try:
            import keyring  # type: ignore[import-not-found]
            import keyring.errors  # type: ignore[import-not-found]
        except ImportError:
            raise RuntimeError(
                "The keyring package is required to delete API keys on this platform."
            ) from None

        try:
            keyring.delete_password(self.service, account)
        except keyring.errors.PasswordDeleteError:
            # Backends raise this for a missing item and for a refused delete,
            # so only a follow-up read that finds nothing means "already gone".
            try:
                absent = keyring.get_password(self.service, account) is None
            except Exception as exc:  # noqa: BLE001 - sanitize backend failures
                raise RuntimeError(
                    f"Keyring delete failed for account '{account}' "
                    f"({type(exc).__name__})."
                ) from None
            if not absent:
                raise RuntimeError(
                    f"Keyring delete failed for account '{account}' "
                    "(PasswordDeleteError)."
                ) from None
        except Exception as exc:  # noqa: BLE001 - sanitize backend-specific failures
            raise RuntimeError(
                f"Keyring delete failed for account '{account}' "
                f"({type(exc).__name__})."
            ) from None


class InMemorySecretBackend:
    """Process-local store for tests; nothing leaves this object."""

    def __init__(self) -> None:
        self._items: dict[str, str] = {}

    def read(self, account: str) -> str | None:
        """Return the stored key, or ``None`` when ``account`` is absent."""
        return self._items.get(account)

    def write(self, account: str, key: str) -> None:
        """Store or replace the key for ``account``."""
        self._items[account] = key

    def delete(self, account: str) -> None:
        """Remove ``account``; an already-absent account is not an error."""
        self._items.pop(account, None)

    def accounts(self) -> frozenset[str]:
        """Return the accounts currently stored, for teardown assertions."""
        return frozenset(self._items)


_backend_override: SecretBackend | None = None


def platform_backend() -> SecretBackend:
    """Return this platform's production store on service ``nexus-api``."""
    if platform.system() == "Darwin":
        return MacOSKeychainBackend()
    return KeyringLibraryBackend()


def active_backend() -> SecretBackend:
    """Return the backend :func:`get_secret` and :func:`set_secret` use now."""
    if _backend_override is not None:
        return _backend_override
    return platform_backend()


@contextlib.contextmanager
def use_secret_backend(backend: SecretBackend) -> Iterator[SecretBackend]:
    """Route :func:`get_secret` and :func:`set_secret` through ``backend``.

    The previous selection is restored on exit, including when the block
    raises. The read cache is cleared on entry and exit so a value read from
    one backend is never served while another is active. Overrides nest.
    """
    global _backend_override
    previous = _backend_override
    _backend_override = backend
    get_secret.cache_clear()
    try:
        yield backend
    finally:
        _backend_override = previous
        get_secret.cache_clear()


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

    value = active_backend().read(provider)
    if value:
        return value

    value = os.environ.get(env_var)
    if value:
        return value

    raise MissingSecretError(
        f"No API key found for provider '{provider}'. "
        "Set it in the settings pane's API KEYS card, or "
        f"export {env_var} for a one-off run."
    )


def set_secret(provider: str, key: str) -> None:
    """Store ``key`` for ``provider`` in the active secret store.

    Environment-only mode deliberately has no write path. Successful writes
    invalidate all cached reads so the new value is visible in this process.
    """
    account = provider.lower()
    # Persist the trimmed value, not just validate it: pasted keys routinely
    # carry a trailing newline/space (terminal copy, .env line, provider
    # reveal UIs). macOS reads strip incidentally, but the keyring backend
    # does not, so an untrimmed store corrupts the key on non-Darwin.
    key = key.strip()
    if not key:
        raise ValueError("API key must not be empty or whitespace.")
    if os.environ.get("NEXUS_KEYRING_DISABLE") == "1":
        raise RuntimeError(
            "NEXUS_KEYRING_DISABLE=1 disables writable secret storage. "
            "Unset it before storing an API key."
        )

    active_backend().write(account, key)

    get_secret.cache_clear()
