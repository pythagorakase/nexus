"""Live local-secret-store coverage for ``nexus.util.secret_manager``."""

from __future__ import annotations

import platform
import secrets
import subprocess

import pytest

from nexus.util.secret_manager import SERVICE_NAME, get_secret, set_secret

TEST_ACCOUNT = "test-secret-455"


def _delete_test_account() -> None:
    """Remove the isolated test item, ignoring the expected absent status."""
    subprocess.run(
        [
            "security",
            "delete-generic-password",
            "-s",
            SERVICE_NAME,
            "-a",
            TEST_ACCOUNT,
        ],
        capture_output=True,
        timeout=5.0,
    )
    get_secret.cache_clear()


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS Keychain test")
def test_set_secret_round_trip_and_overwrite_clear_cached_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write, cached-read, overwrite, and read again in one process."""
    monkeypatch.delenv("NEXUS_KEYRING_DISABLE", raising=False)
    monkeypatch.delenv(f"{TEST_ACCOUNT.upper()}_API_KEY", raising=False)
    first = secrets.token_urlsafe(24)
    second = secrets.token_urlsafe(24)
    _delete_test_account()

    try:
        set_secret(TEST_ACCOUNT, first)
        assert secrets.compare_digest(get_secret(TEST_ACCOUNT), first)

        set_secret(TEST_ACCOUNT.upper(), second)
        assert secrets.compare_digest(get_secret(TEST_ACCOUNT), second)
    finally:
        _delete_test_account()


def test_set_secret_persists_trimmed_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pasted key with surrounding whitespace is stored trimmed.

    Platform-independent: captures the value handed to BOTH write backends,
    so it fails on the keyring path (Linux/Windows) that has no read-side
    strip to mask an untrimmed store.
    """
    from nexus.util import secret_manager

    monkeypatch.delenv("NEXUS_KEYRING_DISABLE", raising=False)
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        secret_manager,
        "_write_macos_keychain",
        lambda account, key: captured.update(value=key),
    )
    monkeypatch.setattr(
        secret_manager,
        "_write_keyring_library",
        lambda account, key: captured.update(value=key),
    )

    set_secret(TEST_ACCOUNT, "  sk-padded-key-value\n")
    assert captured["value"] == "sk-padded-key-value"


def test_set_secret_rejects_blank_values() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        set_secret(TEST_ACCOUNT, "   ")


def test_set_secret_rejects_environment_only_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    with pytest.raises(RuntimeError, match="disables writable secret storage"):
        set_secret(TEST_ACCOUNT, secrets.token_urlsafe(24))
