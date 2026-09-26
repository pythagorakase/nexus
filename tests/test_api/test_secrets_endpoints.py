"""Tests for the ``/api/secrets`` router against a private in-memory store.

Default tests inject ``InMemorySecretBackend`` through the
``in_memory_secret_store`` fixture; the session guard in ``tests/conftest.py``
fails any test that reaches the real Keychain or keyring store instead.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api import secrets_endpoints
from nexus.api.secrets_endpoints import SecretProvider, get_secret_providers, router
from nexus.util.secret_manager import InMemorySecretBackend, set_secret

TEST_ACCOUNT = "test-secret-455"
TEST_ENV_VAR = f"{TEST_ACCOUNT.upper()}_API_KEY"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def synthetic_provider(
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> SecretProvider:
    """Expose one synthetic provider whose account lives in the private store."""
    monkeypatch.delenv(TEST_ENV_VAR, raising=False)
    provider = SecretProvider(provider=TEST_ACCOUNT, account=TEST_ACCOUNT)
    monkeypatch.setattr(
        secrets_endpoints,
        "get_secret_providers",
        lambda: [provider],
    )
    return provider


@pytest.fixture
def models_endpoint() -> Iterator[tuple[str, list[tuple[str, str | None]], list[int]]]:
    """Serve a local OpenAI-compatible ``/v1/models`` and record each request.

    The yielded status list holds the one status code the server answers with;
    tests replace it before calling verify.
    """
    received: list[tuple[str, str | None]] = []
    status: list[int] = [200]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            received.append((self.path, self.headers.get("Authorization")))
            if status[0] == 200:
                body = json.dumps({"object": "list", "data": []}).encode()
            else:
                body = json.dumps({"error": {"message": "rejected"}}).encode()
            self.send_response(status[0])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", received, status
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_provider_derivation_uses_registry_accounts() -> None:
    providers = {row.provider: row for row in get_secret_providers()}
    assert providers["openai"].account == "openai"
    assert providers["anthropic"].account == "anthropic"
    assert "test" not in providers


def test_status_put_status_and_unknown_provider_flow(
    client: TestClient,
    synthetic_provider: SecretProvider,
    in_memory_secret_store: InMemorySecretBackend,
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
    assert in_memory_secret_store.read(TEST_ACCOUNT) == key

    refreshed = client.get("/api/secrets/status")
    assert refreshed.status_code == 200
    assert refreshed.json() == [written.json()]

    unknown = client.put("/api/secrets/not-in-registry", json={"key": key})
    assert unknown.status_code == 404
    assert in_memory_secret_store.accounts() == {TEST_ACCOUNT}

    for response in (initial, written, refreshed, unknown):
        assert response.content.find(key.encode()) == -1


def test_put_overwrites_and_status_reflects_rotation(
    client: TestClient,
    synthetic_provider: SecretProvider,
    in_memory_secret_store: InMemorySecretBackend,
) -> None:
    """A second PUT replaces the key and invalidates the cached status read."""
    first = secrets.token_urlsafe(24)
    second = secrets.token_urlsafe(24)
    written = client.put(f"/api/secrets/{TEST_ACCOUNT}", json={"key": first})
    assert written.json()["last4"] == first[-4:]
    assert client.get("/api/secrets/status").json()[0]["last4"] == first[-4:]

    rotated = client.put(f"/api/secrets/{TEST_ACCOUNT}", json={"key": second})
    assert rotated.json()["last4"] == second[-4:]
    assert client.get("/api/secrets/status").json()[0]["last4"] == second[-4:]
    assert in_memory_secret_store.read(TEST_ACCOUNT) == second


def test_blank_put_is_rejected_without_writing(
    client: TestClient,
    synthetic_provider: SecretProvider,
    in_memory_secret_store: InMemorySecretBackend,
) -> None:
    response = client.put(f"/api/secrets/{TEST_ACCOUNT}", json={"key": "  \n"})
    assert response.status_code == 422
    assert response.json() == {"detail": "API key must not be empty or whitespace."}
    assert in_memory_secret_store.accounts() == frozenset()


def test_registry_put_writes_only_its_account(
    client: TestClient,
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real registry maps the route to one account; others stay absent."""
    for provider in get_secret_providers():
        monkeypatch.delenv(f"{provider.account.upper()}_API_KEY", raising=False)
    key = secrets.token_urlsafe(24)

    written = client.put("/api/secrets/openai", json={"key": key})

    assert written.status_code == 200
    assert written.json() == {
        "provider": "openai",
        "account": "openai",
        "present": True,
        "last4": key[-4:],
    }
    rows = {row["provider"]: row for row in client.get("/api/secrets/status").json()}
    assert rows["openai"] == written.json()
    assert [name for name, row in rows.items() if row["present"]] == ["openai"]
    assert in_memory_secret_store.accounts() == {"openai"}


@pytest.mark.parametrize(
    "status_code,expected",
    [
        (200, {"verified": True, "detail": "Models endpoint reachable."}),
        (401, {"verified": False, "detail": "AuthenticationError (status 401)"}),
    ],
)
def test_verify_sends_the_stored_key_to_the_provider(
    client: TestClient,
    in_memory_secret_store: InMemorySecretBackend,
    models_endpoint: tuple[str, list[tuple[str, str | None]], list[int]],
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected: dict[str, object],
) -> None:
    """Verify reads the injected store and makes one real models-list call."""
    base_url, received, status = models_endpoint
    status[0] = status_code
    monkeypatch.delenv(TEST_ENV_VAR, raising=False)
    provider = SecretProvider(
        provider=TEST_ACCOUNT, account=TEST_ACCOUNT, base_url=base_url
    )
    monkeypatch.setattr(secrets_endpoints, "get_secret_providers", lambda: [provider])
    key = secrets.token_urlsafe(24)
    set_secret(TEST_ACCOUNT, key)

    response = client.post(f"/api/secrets/{TEST_ACCOUNT}/verify")

    assert response.status_code == 200
    assert response.json() == {"provider": TEST_ACCOUNT, **expected}
    assert received == [("/v1/models", f"Bearer {key}")]
    assert response.content.find(key.encode()) == -1


def test_verify_without_a_stored_key_reports_missing_secret(
    client: TestClient,
    synthetic_provider: SecretProvider,
) -> None:
    response = client.post(f"/api/secrets/{TEST_ACCOUNT}/verify")
    assert response.status_code == 200
    assert response.json() == {
        "provider": TEST_ACCOUNT,
        "verified": False,
        "detail": "MissingSecretError",
    }


def test_verify_unknown_provider_is_not_found(
    client: TestClient,
    synthetic_provider: SecretProvider,
) -> None:
    assert client.post("/api/secrets/not-in-registry/verify").status_code == 404


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
def test_openai_verify_wrong_key_returns_sanitized_failure(
    client: TestClient,
    in_memory_secret_store: InMemorySecretBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TEST_ENV_VAR, raising=False)
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
