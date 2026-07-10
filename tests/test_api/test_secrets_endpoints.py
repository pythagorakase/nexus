"""Live secret-store tests for the ``/api/secrets`` router."""

from __future__ import annotations

import platform
import secrets
import subprocess
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api import secrets_endpoints
from nexus.api.secrets_endpoints import SecretProvider, get_secret_providers, router
from nexus.util.secret_manager import SERVICE_NAME, get_secret, set_secret

TEST_ACCOUNT = "test-secret-455"
IS_DARWIN = platform.system() == "Darwin"


def _delete_test_account() -> None:
    """Remove the isolated Keychain item used by this module."""
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


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def isolated_keychain(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[SecretProvider]:
    if not IS_DARWIN:
        pytest.skip("macOS Keychain test")
    monkeypatch.delenv("NEXUS_KEYRING_DISABLE", raising=False)
    monkeypatch.delenv(f"{TEST_ACCOUNT.upper()}_API_KEY", raising=False)
    provider = SecretProvider(provider=TEST_ACCOUNT, account=TEST_ACCOUNT)
    monkeypatch.setattr(
        secrets_endpoints,
        "get_secret_providers",
        lambda: [provider],
    )
    _delete_test_account()
    try:
        yield provider
    finally:
        _delete_test_account()


def test_provider_derivation_uses_registry_accounts() -> None:
    providers = {row.provider: row for row in get_secret_providers()}
    assert providers["openai"].account == "openai"
    assert providers["anthropic"].account == "anthropic"
    assert "test" not in providers


def test_status_put_status_and_unknown_provider_flow(
    client: TestClient,
    isolated_keychain: SecretProvider,
) -> None:
    initial = client.get("/api/secrets/status")
    assert initial.status_code == 200
    assert initial.json() == [
        {
            "provider": TEST_ACCOUNT,
            "account": TEST_ACCOUNT,
            "present": False,
            "last4": None,
        }
    ]

    key = secrets.token_urlsafe(24)
    written = client.put(f"/api/secrets/{TEST_ACCOUNT}", json={"key": key})
    assert written.status_code == 200
    assert written.json() == {
        "provider": TEST_ACCOUNT,
        "account": TEST_ACCOUNT,
        "present": True,
        "last4": key[-4:],
    }

    refreshed = client.get("/api/secrets/status")
    assert refreshed.status_code == 200
    assert refreshed.json() == [written.json()]

    unknown = client.put("/api/secrets/not-in-registry", json={"key": key})
    assert unknown.status_code == 404

    for response in (initial, written, refreshed, unknown):
        assert response.content.find(key.encode()) == -1


def test_malformed_write_body_does_not_echo_submitted_key() -> None:
    """A 422 on the secrets route must never mirror the submitted plaintext.

    Uses the real gateway app, which registers the RequestValidationError
    handler that strips ``input``/``ctx``. FastAPI's default handler echoes
    the offending value, so a mistyped field name would otherwise bounce the
    plaintext key straight back into the response body.
    """
    from nexus.api.narrative import app as gateway_app

    leak_probe = "sk-echo-regression-" + secrets.token_urlsafe(16)
    gateway_client = TestClient(gateway_app)
    for body in (
        {"api_key": leak_probe},  # wrong field name → "missing" + "extra_forbidden"
        {"key": {"nested": leak_probe}},  # non-string → type error
    ):
        response = gateway_client.put("/api/secrets/openai", json=body)
        assert response.status_code == 422
        assert leak_probe.encode() not in response.content


@pytest.mark.live_llm
def test_openai_verify_uses_real_models_endpoint(client: TestClient) -> None:
    response = client.post("/api/secrets/openai/verify")
    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai",
        "verified": True,
        "detail": "Models endpoint reachable.",
    }


@pytest.mark.live_llm
@pytest.mark.skipif(not IS_DARWIN, reason="macOS Keychain test")
def test_openai_verify_wrong_key_returns_sanitized_failure(
    client: TestClient,
    isolated_keychain: SecretProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SecretProvider(provider="openai", account=TEST_ACCOUNT)
    monkeypatch.setattr(
        secrets_endpoints,
        "get_secret_providers",
        lambda: [provider],
    )
    wrong_key = secrets.token_urlsafe(24)
    set_secret(TEST_ACCOUNT, wrong_key)

    response = client.post("/api/secrets/openai/verify")

    assert response.status_code == 200
    assert response.json()["provider"] == "openai"
    assert response.json()["verified"] is False
    assert response.json()["detail"].endswith("(status 401)")
    assert response.content.find(wrong_key.encode()) == -1
