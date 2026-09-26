"""Opt-in integration with a disposable real platform secret store (#963).

Runs only with ``NEXUS_RUN_SECRET_STORE=1`` set before the session starts, and
only on macOS. Every operation targets a keychain file created under pytest's
temp directory and a random service name. The fixture proves that target
before the first read, write, or delete, then deletes the keychain and checks
that the user's keychain search list is unchanged. The owner's login keychain
and the production ``nexus-api`` service are never addressed.

Known limitation: ``security create-keychain`` can add the new keychain to the
user's search list while the test runs. The before/after equality check
detects drift that survives teardown but does not prevent the temporary
change. This test has not yet run on macOS; it was written and exercised
only to the point of its skip on Linux.
"""

from __future__ import annotations

import platform
import secrets
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from nexus.util.secret_manager import (
    SERVICE_NAME,
    MacOSKeychainBackend,
    get_secret,
    set_secret,
    use_secret_backend,
)
from tests import secret_store_guard

pytestmark = [
    pytest.mark.requires_secret_store,
    pytest.mark.skipif(
        platform.system() != "Darwin",
        reason="The keyring library's default store is the owner's login store; "
        "only a macOS keychain file can be proven disposable.",
    ),
]


def _security(keychain: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one keychain-management command for the disposable keychain."""
    with secret_store_guard.disposable_keychain_setup(keychain):
        return subprocess.run(
            ["security", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=10.0,
        )


def _user_search_list(keychain: Path) -> list[str]:
    """Return the user keychain search list (paths only, no item data)."""
    listing = _security(keychain, "list-keychains", "-d", "user").stdout
    return [line.strip().strip('"') for line in listing.splitlines() if line.strip()]


@pytest.fixture
def disposable_keychain(tmp_path: Path) -> Iterator[MacOSKeychainBackend]:
    """Create, prove, and finally delete a throwaway keychain and service."""
    keychain = tmp_path / f"nexus-secret-it-{secrets.token_hex(8)}.keychain-db"
    service = f"nexus-test-{secrets.token_hex(8)}"
    password = secrets.token_urlsafe(24)
    backend = MacOSKeychainBackend(service=service, keychain=keychain)

    # Prove the target before any credential operation.
    assert service != SERVICE_NAME
    assert not keychain.exists()
    assert secret_store_guard.is_disposable_keychain(keychain)
    login_keychains = (Path.home() / "Library" / "Keychains").resolve()
    assert not keychain.resolve().is_relative_to(login_keychains)
    assert backend.keychain == keychain and backend.service == service
    for operation in secret_store_guard.OPERATIONS:
        assert secret_store_guard.access_allowed(backend, operation)
        # The guard refuses any security spawn outside this exact scope.
        scope = secret_store_guard.backend_scope(backend, operation)
        assert scope.keychain == str(keychain) and scope.service == service
    search_list_before = _user_search_list(keychain)

    _security(keychain, "create-keychain", "-p", password, str(keychain))
    try:
        assert keychain.is_file()
        _security(keychain, "unlock-keychain", "-p", password, str(keychain))
        _security(keychain, "show-keychain-info", str(keychain))
        yield backend
    finally:
        _security(keychain, "delete-keychain", str(keychain))
        assert not keychain.exists()
        assert _user_search_list(keychain) == search_list_before


def test_disposable_keychain_round_trip_through_public_api(
    disposable_keychain: MacOSKeychainBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write, cached read, overwrite, and delete through the real CLI."""
    monkeypatch.delenv("NEXUS_KEYRING_DISABLE", raising=False)
    account = f"it-{secrets.token_hex(4)}"
    monkeypatch.delenv(f"{account.upper()}_API_KEY", raising=False)
    first = secrets.token_urlsafe(24)
    second = secrets.token_urlsafe(24)

    with use_secret_backend(disposable_keychain):
        assert disposable_keychain.read(account) is None
        set_secret(account, first)
        assert secrets.compare_digest(get_secret(account), first)

        set_secret(account.upper(), second)
        assert secrets.compare_digest(get_secret(account), second)
        assert disposable_keychain.read(account) == second

        disposable_keychain.delete(account)
        assert disposable_keychain.read(account) is None
        disposable_keychain.delete(account)
