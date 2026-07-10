"""Credentialed CORS policy tests for the real gateway app (issue #458)."""

import pytest
from fastapi.testclient import TestClient

from nexus.api.narrative import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a client backed by the fully constructed gateway app."""
    return TestClient(app)


def test_preflight_allows_vite_dev_origin(client: TestClient) -> None:
    """The Vite development server remains an allowed cross-origin caller."""
    origin = "http://localhost:5173"
    response = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.headers["access-control-allow-origin"] == origin


def test_preflight_rejects_unconfigured_origin(client: TestClient) -> None:
    """A preflight from an arbitrary website receives no origin grant."""
    origin = "https://evil.example.com"
    response = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.headers.get("access-control-allow-origin") != origin


@pytest.mark.parametrize(
    ("origin", "is_allowed"),
    [
        ("http://127.0.0.1:5173", True),
        ("https://evil.example.com", False),
    ],
)
def test_health_get_applies_origin_allowlist(
    client: TestClient, origin: str, is_allowed: bool
) -> None:
    """Simple health requests reflect only configured origins."""
    response = client.get("/health", headers={"Origin": origin})

    assert response.status_code == 200
    if is_allowed:
        assert response.headers["access-control-allow-origin"] == origin
    else:
        assert response.headers.get("access-control-allow-origin") != origin
