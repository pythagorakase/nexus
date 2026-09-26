"""Proof that the session guard denies the real platform secret store (#963).

Each probe first asserts that the guard is installed, so a broken guard fails
the test before any real backend method can run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import keyring
import keyring.core
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api import secrets_endpoints
from nexus.api.secrets_endpoints import SecretProvider, router
from nexus.util.secret_manager import (
    SERVICE_NAME,
    KeyringLibraryBackend,
    MacOSKeychainBackend,
    get_secret,
    set_secret,
)
from tests import secret_store_guard

PROBE_ACCOUNT = "guard-probe-963"
DISPOSABLE_SERVICE = "nexus-test-guard-probe"
REAL_BACKENDS = [MacOSKeychainBackend, KeyringLibraryBackend]

live_reads_allowed = pytest.mark.skipif(
    secret_store_guard.LIVE_LLM_OPT_IN,
    reason="NEXUS_RUN_LIVE_LLM=1 sessions may read service nexus-api.",
)


@pytest.fixture(autouse=True)
def _hostile_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set every variable a test might use to try to reopen the store.

    The guard's opt-ins were read before collection, so none of these edits
    may widen it.
    """
    monkeypatch.delenv("NEXUS_KEYRING_DISABLE", raising=False)
    monkeypatch.setenv(secret_store_guard.SECRET_STORE_FLAG, "1")
    monkeypatch.setenv("NEXUS_RUN_LIVE_LLM", "1")
    assert secret_store_guard.installed()


def test_every_real_backend_operation_is_wrapped() -> None:
    for backend in REAL_BACKENDS:
        for operation in secret_store_guard.OPERATIONS:
            method = backend.__dict__[operation]
            assert getattr(method, secret_store_guard.GUARD_MARKER, False), (
                backend,
                operation,
            )


@pytest.mark.parametrize("backend_cls", REAL_BACKENDS)
@pytest.mark.parametrize("operation", ["write", "delete"])
def test_production_mutation_is_denied(
    backend_cls: type[MacOSKeychainBackend | KeyringLibraryBackend],
    operation: str,
) -> None:
    backend = backend_cls()
    assert not secret_store_guard.access_allowed(backend, operation)
    args = ("never-stored",) if operation == "write" else ()
    with pytest.raises(pytest.fail.Exception, match=f"secret-store {operation}"):
        getattr(backend, operation)(PROBE_ACCOUNT, *args)


@live_reads_allowed
@pytest.mark.parametrize("backend_cls", REAL_BACKENDS)
def test_production_read_is_denied(
    backend_cls: type[MacOSKeychainBackend | KeyringLibraryBackend],
) -> None:
    backend = backend_cls()
    assert not secret_store_guard.access_allowed(backend, "read")
    with pytest.raises(pytest.fail.Exception, match="secret-store read"):
        backend.read(PROBE_ACCOUNT)


@pytest.mark.parametrize("operation", secret_store_guard.OPERATIONS)
def test_owner_keyring_is_denied_under_any_service(operation: str) -> None:
    """The keyring default store is the owner's; no service makes it disposable."""
    backend = KeyringLibraryBackend(service=DISPOSABLE_SERVICE)
    assert not secret_store_guard.access_allowed(backend, operation)
    args = ("never-stored",) if operation == "write" else ()
    with pytest.raises(pytest.fail.Exception, match=f"secret-store {operation}"):
        getattr(backend, operation)(PROBE_ACCOUNT, *args)


@pytest.mark.parametrize("operation", secret_store_guard.OPERATIONS)
def test_login_keychain_search_list_is_denied_under_any_service(
    operation: str,
) -> None:
    """A non-production service still needs an explicit disposable keychain."""
    backend = MacOSKeychainBackend(service=DISPOSABLE_SERVICE)
    assert not secret_store_guard.access_allowed(backend, operation)
    args = ("never-stored",) if operation == "write" else ()
    with pytest.raises(pytest.fail.Exception, match=f"secret-store {operation}"):
        getattr(backend, operation)(PROBE_ACCOUNT, *args)


@pytest.mark.skipif(
    secret_store_guard.SECRET_STORE_OPT_IN,
    reason="NEXUS_RUN_SECRET_STORE=1 sessions may use disposable keychains.",
)
@pytest.mark.parametrize("operation", secret_store_guard.OPERATIONS)
def test_disposable_keychain_needs_session_opt_in(
    operation: str,
    tmp_path: Path,
) -> None:
    backend = MacOSKeychainBackend(
        service=DISPOSABLE_SERVICE,
        keychain=tmp_path / "guard-probe.keychain-db",
    )
    assert secret_store_guard.is_disposable_keychain(backend.keychain)
    assert not secret_store_guard.access_allowed(backend, operation)
    args = ("never-stored",) if operation == "write" else ()
    with pytest.raises(pytest.fail.Exception, match=f"secret-store {operation}"):
        getattr(backend, operation)(PROBE_ACCOUNT, *args)


def test_keychain_outside_the_temp_root_is_never_disposable() -> None:
    login = Path.home() / "Library" / "Keychains" / "login.keychain-db"
    assert not secret_store_guard.is_disposable_keychain(login)
    assert not secret_store_guard.is_disposable_keychain(None)
    backend = MacOSKeychainBackend(service=DISPOSABLE_SERVICE, keychain=login)
    for operation in secret_store_guard.OPERATIONS:
        assert not secret_store_guard.access_allowed(backend, operation)


def test_set_secret_without_injection_is_denied() -> None:
    with pytest.raises(pytest.fail.Exception, match="secret-store write"):
        set_secret(PROBE_ACCOUNT, "never-stored")


@live_reads_allowed
def test_get_secret_without_injection_is_denied() -> None:
    get_secret.cache_clear()
    with pytest.raises(pytest.fail.Exception, match="secret-store read"):
        get_secret(PROBE_ACCOUNT)


@live_reads_allowed
def test_verify_endpoint_cannot_swallow_the_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The verify route catches ``Exception``; the guard is a BaseException."""
    get_secret.cache_clear()
    provider = SecretProvider(provider=PROBE_ACCOUNT, account=PROBE_ACCOUNT)
    monkeypatch.setattr(secrets_endpoints, "get_secret_providers", lambda: [provider])
    app = FastAPI()
    app.include_router(router)
    with pytest.raises(pytest.fail.Exception, match="secret-store read"):
        TestClient(app).post(f"/api/secrets/{PROBE_ACCOUNT}/verify")


def test_direct_security_cli_spawn_is_denied() -> None:
    """The #963 tests shelled out to ``security`` directly; that fails too."""
    with pytest.raises(pytest.fail.Exception, match="security CLI"):
        subprocess.run(
            ["security", "delete-generic-password", "-s", SERVICE_NAME, "-a", "x"],
            capture_output=True,
            timeout=5.0,
        )


def test_shell_security_cli_spawn_is_denied() -> None:
    with pytest.raises(pytest.fail.Exception, match="security CLI"):
        subprocess.run(
            f"/usr/bin/security find-generic-password -s {SERVICE_NAME} -a x -w",
            shell=True,
            capture_output=True,
            timeout=5.0,
        )


def test_other_subprocesses_still_run() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "print('ok')"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30.0,
    )
    assert result.stdout == "ok\n"


@pytest.mark.parametrize("module", [keyring, keyring.core])
@pytest.mark.parametrize(
    "name,args",
    [
        ("get_password", (SERVICE_NAME, PROBE_ACCOUNT)),
        ("set_password", (SERVICE_NAME, PROBE_ACCOUNT, "never-stored")),
        ("delete_password", (SERVICE_NAME, PROBE_ACCOUNT)),
    ],
)
def test_direct_keyring_call_is_denied(
    module: object,
    name: str,
    args: tuple[str, ...],
) -> None:
    with pytest.raises(pytest.fail.Exception, match=f"keyring.{name}"):
        getattr(module, name)(*args)


@pytest.mark.skipif(
    secret_store_guard.SECRET_STORE_OPT_IN,
    reason="NEXUS_RUN_SECRET_STORE=1 sessions may set up disposable keychains.",
)
def test_disposable_keychain_setup_needs_session_opt_in(tmp_path: Path) -> None:
    with pytest.raises(pytest.fail.Exception, match="without opt-in"):
        with secret_store_guard.disposable_keychain_setup(tmp_path / "x.keychain"):
            pass
