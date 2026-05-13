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
any item's partition-list grant — so the same read triggers a GUI prompt
that blocks unattended runs. Subprocessing to ``security`` is the
documented workaround.
"""
from __future__ import annotations

import os
import platform
import subprocess

SERVICE_NAME = "nexus-api"


class MissingSecretError(RuntimeError):
    """Raised when no API key can be located for the requested provider."""


def _read_macos_keychain(account: str) -> str | None:
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
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    value = result.stdout.strip()
    return value or None


def _read_keyring_library(account: str) -> str | None:
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        return None
    return keyring.get_password(SERVICE_NAME, account)


def get_secret(provider: str) -> str:
    """Retrieve the API key for ``provider`` (e.g. ``"openai"``).

    Raises :class:`MissingSecretError` if no key is available.
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
