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
    InMemorySecretBackend,
    KeyringLibraryBackend,
    MacOSKeychainBackend,
    MissingSecretError,
    active_backend,
    get_secret,
    platform_backend,
    set_secret,
    use_secret_backend,
)
from tests import secret_store_guard

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
