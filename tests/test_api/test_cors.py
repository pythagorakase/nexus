"""Credentialed CORS policy per listener (issues #458 and #824, D-824-CORS).

``nexus.api.serve.build_plane_app`` installs each plane's own origin list on
its projection; the gateway app itself carries no CORS middleware.
"""

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from nexus.api.narrative import app
from nexus.api.serve import build_plane_app
from nexus.config import get_gateway_cors_allowed_origins


@pytest.fixture(scope="module")
def player() -> TestClient:
    """A client backed by the gateway's player projection."""
    return TestClient(build_plane_app(app, "player"))


@pytest.fixture(scope="module")
def operator() -> TestClient:
    """A client backed by the gateway's operator projection."""
    return TestClient(build_plane_app(app, "operator"))


def _preflight_grant(client: TestClient, origin: str) -> str | None:
    response = client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    return response.headers.get("access-control-allow-origin")


@pytest.mark.parametrize(
    "origin", ["https://nexus.pythagora.net", "http://127.0.0.1:8002"]
)
def test_player_plane_grants_its_origins(player: TestClient, origin: str) -> None:
    """The tunnel's hostname and the local player origin may call the player."""
    assert _preflight_grant(player, origin) == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://127.0.0.1:8003",
        "https://nexus-admin.pythagora.net",
        "http://localhost:5173",
        "https://evil.example.com",
    ],
)
def test_player_plane_refuses_other_origins(player: TestClient, origin: str) -> None:
    """Operator origins, the retired Vite port and arbitrary sites get no grant."""
    assert _preflight_grant(player, origin) != origin


def test_operator_plane_grants_only_the_operator_list(operator: TestClient) -> None:
    """The operator plane answers its own list and refuses the player hostname."""
    operator_origins = get_gateway_cors_allowed_origins("operator")
    assert operator_origins == [
        "http://localhost:8003",
        "http://127.0.0.1:8003",
        "https://nexus-admin.pythagora.net",
    ]
    for origin in operator_origins:
        assert _preflight_grant(operator, origin) == origin
    assert _preflight_grant(operator, "https://nexus.pythagora.net") is None
    assert _preflight_grant(operator, "https://evil.example.com") is None


@pytest.mark.parametrize(
    ("origin", "is_allowed"),
    [
        ("https://nexus.pythagora.net", True),
        ("https://evil.example.com", False),
    ],
)
def test_player_health_get_applies_origin_allowlist(
    player: TestClient, origin: str, is_allowed: bool
) -> None:
    """Simple health requests reflect only configured origins."""
    response = player.get("/health", headers={"Origin": origin})

    assert response.status_code == 200
    if is_allowed:
        assert response.headers["access-control-allow-origin"] == origin
    else:
        assert response.headers.get("access-control-allow-origin") != origin


def test_gateway_app_carries_no_cors_middleware() -> None:
    """Only the projections install CORS; the gateway app has none to copy."""
    assert not any(
        middleware.cls is CORSMiddleware for middleware in app.user_middleware
    )
    for plane in ("player", "operator"):
        projection = build_plane_app(app, plane)
        cors = [m for m in projection.user_middleware if m.cls is CORSMiddleware]
        assert len(cors) == 1, plane
        assert cors[0].kwargs["allow_origins"] == get_gateway_cors_allowed_origins(
            plane
        )
