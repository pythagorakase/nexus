"""Secret-manager contract coverage against a private in-memory store.

Every test here injects ``InMemorySecretBackend`` through the
``in_memory_secret_store`` fixture; the session guard in ``tests/conftest.py``
fails any test that reaches the real Keychain or keyring store instead.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.util.secret_manager import (
    _SECURITY_CALL_TIMEOUT_SEC,
    InMemorySecretBackend,
    KeyringLibraryBackend,
    MacOSKeychainBackend,
    MissingSecretError,
    SecretStoreAccessError,
    active_backend,
    get_secret,
    get_secret_uncached,
    keychain_read_error,
    platform_backend,
    set_secret,
    use_secret_backend,
)
from tests import secret_store_guard
from tests.conftest import UnreadableSecretBackend

TEST_ACCOUNT = "test-secret-455"
REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_ENV_VAR = f"{TEST_ACCOUNT.upper()}_API_KEY"


def test_set_secret_round_trip_and_overwrite_clear_cached_value(
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write, cached-read, overwrite, and read again in one process."""
    monkeypatch.delenv(TEST_ENV_VAR, raising=False)
    first = secrets.token_urlsafe(24)
    second = secrets.token_urlsafe(24)
    assert in_memory_secret_store.read(TEST_ACCOUNT) is None

    set_secret(TEST_ACCOUNT, first)
    assert secrets.compare_digest(get_secret(TEST_ACCOUNT), first)

    set_secret(TEST_ACCOUNT.upper(), second)
    assert secrets.compare_digest(get_secret(TEST_ACCOUNT), second)
    assert in_memory_secret_store.accounts() == {TEST_ACCOUNT}

    in_memory_secret_store.delete(TEST_ACCOUNT)
    in_memory_secret_store.delete(TEST_ACCOUNT)
    assert in_memory_secret_store.accounts() == frozenset()


def test_get_secret_serves_cache_until_set_secret_invalidates(
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store change outside ``set_secret`` stays hidden until a write."""
    monkeypatch.delenv(TEST_ENV_VAR, raising=False)
    first = secrets.token_urlsafe(24)
    out_of_band = secrets.token_urlsafe(24)
    rotated = secrets.token_urlsafe(24)

    set_secret(TEST_ACCOUNT, first)
    assert get_secret(TEST_ACCOUNT) == first
    in_memory_secret_store.write(TEST_ACCOUNT, out_of_band)
    assert get_secret(TEST_ACCOUNT) == first

    set_secret(TEST_ACCOUNT, rotated)
    assert get_secret(TEST_ACCOUNT) == rotated
    assert in_memory_secret_store.read(TEST_ACCOUNT) == rotated


STDERR_SENTINEL = "STDERR-SENTINEL-821"


@pytest.mark.parametrize(
    ("error", "reason", "failure", "remediation"),
    [
        pytest.param(
            subprocess.CalledProcessError(
                36,
                ["security", "find-generic-password", "-a", TEST_ACCOUNT, "-w"],
                output=STDERR_SENTINEL,
                stderr=STDERR_SENTINEL,
            ),
            "locked",
            f"The login keychain refused to read account '{TEST_ACCOUNT}' "
            "(security exit 36).",
            "Unlock the login keychain (Keychain Access, or security "
            "unlock-keychain) and retry.",
            id="locked",
        ),
        pytest.param(
            subprocess.TimeoutExpired(
                ["security", "find-generic-password", "-a", TEST_ACCOUNT, "-w"],
                _SECURITY_CALL_TIMEOUT_SEC,
                output=STDERR_SENTINEL,
                stderr=STDERR_SENTINEL,
            ),
            "timeout",
            f"The login keychain did not answer a read of account "
            f"'{TEST_ACCOUNT}' within {_SECURITY_CALL_TIMEOUT_SEC}s.",
            "Unlock the login keychain (Keychain Access, or security "
            "unlock-keychain), then retry.",
            id="timeout",
        ),
        pytest.param(
            FileNotFoundError(2, STDERR_SENTINEL, "security"),
            "no_security_cli",
            f"The security executable is not on this process's PATH, so account "
            f"'{TEST_ACCOUNT}' could not be read.",
            "Put /usr/bin (where macOS ships security) back on this process's "
            "PATH and retry.",
            id="no-security-cli",
        ),
    ],
)
def test_keychain_read_error_names_each_failure(
    error: (
        FileNotFoundError | subprocess.CalledProcessError | subprocess.TimeoutExpired
    ),
    reason: str,
    failure: str,
    remediation: str,
) -> None:
    """Each real ``security`` failure becomes an access error, never absence."""
    exc = keychain_read_error(TEST_ACCOUNT, error)

    assert isinstance(exc, SecretStoreAccessError)
    assert not isinstance(exc, MissingSecretError)
    assert not issubclass(SecretStoreAccessError, MissingSecretError)
    assert (exc.account, exc.reason) == (TEST_ACCOUNT, reason)
    assert exc.failure == failure
    assert exc.remediation == remediation
    assert str(exc) == f"{exc.failure} {exc.remediation}"
    assert STDERR_SENTINEL not in str(exc)


def test_access_error_never_falls_back_to_the_environment(
    unreadable_secret_store: UnreadableSecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store that cannot be read is not an absent item: no env fallback."""
    monkeypatch.setenv(TEST_ENV_VAR, "env-fallback-value")

    with pytest.raises(SecretStoreAccessError) as raised:
        get_secret(TEST_ACCOUNT)
    assert raised.value.reason == "locked"
    with pytest.raises(SecretStoreAccessError):
        get_secret_uncached(TEST_ACCOUNT)
    assert STDERR_SENTINEL not in str(raised.value)


@pytest.mark.parametrize("case", ["store", "env-fallback", "env-only"])
def test_get_secret_uncached_sees_an_out_of_band_write(
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """The uncached reader follows each lookup path past a warm cache."""
    first = secrets.token_urlsafe(24)
    second = secrets.token_urlsafe(24)
    monkeypatch.delenv(TEST_ENV_VAR, raising=False)

    if case == "store":
        set_secret(TEST_ACCOUNT, first)
        assert get_secret(TEST_ACCOUNT) == first
        in_memory_secret_store.write(TEST_ACCOUNT, second)
    elif case == "env-fallback":
        monkeypatch.setenv(TEST_ENV_VAR, first)
        assert get_secret(TEST_ACCOUNT) == first
        monkeypatch.setenv(TEST_ENV_VAR, second)
    else:
        # set_secret refuses this mode, so the store is filled directly; a
        # read of it would answer this value instead of the variable's.
        monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
        in_memory_secret_store.write(TEST_ACCOUNT, "store-held-value")
        monkeypatch.setenv(TEST_ENV_VAR, first)
        assert get_secret(TEST_ACCOUNT) == first
        monkeypatch.setenv(TEST_ENV_VAR, second)

    assert get_secret_uncached(TEST_ACCOUNT) == second
    assert get_secret(TEST_ACCOUNT) == first

    if case == "env-only":
        monkeypatch.delenv(TEST_ENV_VAR)
        with pytest.raises(
            MissingSecretError,
            match=f"NEXUS_KEYRING_DISABLE=1 but {TEST_ENV_VAR} is not set",
        ):
            get_secret_uncached(TEST_ACCOUNT)


def test_store_value_wins_over_environment_fallback(
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The store is consulted first; the env var covers only an absent item."""
    monkeypatch.setenv(TEST_ENV_VAR, "env-fallback-value")
    assert get_secret(TEST_ACCOUNT) == "env-fallback-value"

    set_secret(TEST_ACCOUNT, "store-value")
    assert get_secret(TEST_ACCOUNT) == "store-value"


def test_missing_everywhere_raises_missing_secret_error(
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TEST_ENV_VAR, raising=False)
    with pytest.raises(MissingSecretError, match="API KEYS card"):
        get_secret(TEST_ACCOUNT)


def test_environment_only_mode_never_reads_the_store(
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``NEXUS_KEYRING_DISABLE=1`` answers from the environment alone."""
    in_memory_secret_store.write(TEST_ACCOUNT, "store-value")
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    monkeypatch.delenv(TEST_ENV_VAR, raising=False)
    with pytest.raises(MissingSecretError, match="is not set"):
        get_secret(TEST_ACCOUNT)

    monkeypatch.setenv(TEST_ENV_VAR, "env-value")
    assert get_secret(TEST_ACCOUNT) == "env-value"


def test_set_secret_persists_trimmed_value(
    in_memory_secret_store: InMemorySecretBackend,
) -> None:
    """A pasted key with surrounding whitespace is stored trimmed."""
    set_secret(TEST_ACCOUNT, "  sk-padded-key-value\n")
    assert in_memory_secret_store.read(TEST_ACCOUNT) == "sk-padded-key-value"


def test_set_secret_rejects_blank_values(
    in_memory_secret_store: InMemorySecretBackend,
) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        set_secret(TEST_ACCOUNT, "   ")
    assert in_memory_secret_store.accounts() == frozenset()


def test_set_secret_rejects_environment_only_mode(
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    with pytest.raises(RuntimeError, match="disables writable secret storage"):
        set_secret(TEST_ACCOUNT, secrets.token_urlsafe(24))
    assert in_memory_secret_store.accounts() == frozenset()


def test_use_secret_backend_restores_selection_and_clears_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nested overrides unwind on error and never serve another store's value."""
    monkeypatch.delenv("NEXUS_KEYRING_DISABLE", raising=False)
    monkeypatch.delenv(TEST_ENV_VAR, raising=False)
    outer = InMemorySecretBackend()
    inner = InMemorySecretBackend()
    outer.write(TEST_ACCOUNT, "outer-value")
    inner.write(TEST_ACCOUNT, "inner-value")

    with use_secret_backend(outer):
        assert active_backend() is outer
        assert get_secret(TEST_ACCOUNT) == "outer-value"
        with pytest.raises(LookupError, match="body failed"):
            with use_secret_backend(inner):
                assert active_backend() is inner
                assert get_secret(TEST_ACCOUNT) == "inner-value"
                raise LookupError("body failed")
        assert active_backend() is outer
        assert get_secret(TEST_ACCOUNT) == "outer-value"

    assert get_secret.cache_info().currsize == 0
    assert type(active_backend()) is type(platform_backend())


def test_platform_backend_targets_production_service() -> None:
    """The default selection is the platform store on service ``nexus-api``."""
    backend = platform_backend()
    assert isinstance(backend, (MacOSKeychainBackend, KeyringLibraryBackend))
    assert backend.service == "nexus-api"
    if isinstance(backend, MacOSKeychainBackend):
        assert backend.keychain is None


INNER_CHILD_TEST = """
import subprocess
import sys


REPORT = "import os; print(os.environ.get('NEXUS_KEYRING_DISABLE'))"


def test_child_reports_environment_only_mode():
    child = subprocess.run(
        [sys.executable, "-c", REPORT],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert child.stdout.strip() == "1"
"""


@pytest.mark.parametrize("flag", [None, "NEXUS_RUN_SECRET_STORE", "NEXUS_RUN_LIVE_LLM"])
def test_child_processes_inherit_environment_only_mode(
    flag: str | None,
    tmp_path: Path,
) -> None:
    """Children stay env-only in a fresh session, whatever its opt-in flags.

    The inner session starts with ``NEXUS_KEYRING_DISABLE=0`` through
    ``store_access_env`` (the only opt-out), so only its own guard can put the
    child back into env-only mode. The child only reports its environment; it
    never touches a secret store, so this probe stays safe even if the rule
    regresses.
    """
    inner = tmp_path / "test_inner_child_env.py"
    inner.write_text(INNER_CHILD_TEST)
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("NEXUS_RUN_SECRET_STORE", "NEXUS_RUN_LIVE_LLM")
    }
    env["NEXUS_KEYRING_DISABLE"] = "0"
    if flag is not None:
        env[flag] = "1"
    # The inner session must start outside env-only mode to prove its own
    # guard restores it for the grandchild; the probe touches no store.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "tests.conftest",
            str(inner),
        ],
        cwd=REPO_ROOT,
        env=secret_store_guard.store_access_env(env),
        capture_output=True,
        text=True,
        timeout=180.0,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
