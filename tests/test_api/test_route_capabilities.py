"""Player/operator route-capability registry and projections (issue #824).

The registry classifies every route, websocket, and static mount the gateway
registers. These tests exercise the real gateway app, the real dashboard gate,
and both static-shell branches through real Starlette dispatch.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Set

import pytest
import tomlkit
from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.routing import BaseRoute, Mount, WebSocketRoute
from starlette.staticfiles import StaticFiles

from nexus.api import narrative, static_ui
from nexus.api.route_capabilities import (
    ROUTE_CAPABILITIES,
    RouteCapabilityError,
    RouteKey,
    UnclassifiedRouteError,
    build_operator_app,
    build_player_app,
    classify_app,
    require_classified,
    route_keys,
)
from nexus.config import get_gateway_cors_allowed_origins, load_settings
from nexus.config.settings_models import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]

# Operator endpoints the remote player plane must never route.
OPERATOR_REQUESTS = [
    ("GET", "/api/secrets/status"),
    ("PUT", "/api/secrets/openai"),
    ("POST", "/api/secrets/openai/verify"),
    ("GET", "/api/settings"),
    ("HEAD", "/api/settings"),
    ("GET", "/api/local-models/status"),
    ("POST", "/api/local-models/delete"),
    ("GET", "/runtime/status"),
    ("POST", "/api/slot/1/lock"),
    ("POST", "/api/slot/1/unlock"),
    ("PATCH", "/api/slot/1/settings"),
    ("POST", "/api/story/new/setup/reset"),
    ("POST", "/api/story/new/slot/select"),
    ("POST", "/api/characters/1/images"),
    ("DELETE", "/api/characters/1/images/1"),
    ("PUT", "/api/places/1/images/1/main"),
    ("GET", "/api/dev/backstage/health"),
    ("GET", "/api/dev/orrery/catalog"),
]


def _dashboard_settings(tmp_path: Path, enabled: bool) -> Settings:
    """Load the real nexus.toml with the dashboard gate forced."""
    document = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    document["orrery"]["dashboard"]["enabled"] = enabled  # type: ignore[index]
    path = tmp_path / f"dashboard_{'on' if enabled else 'off'}.toml"
    path.write_text(tomlkit.dumps(document))
    return load_settings(str(path))


def _is_static_tail(route: BaseRoute) -> bool:
    """The upload mounts and SPA shell that ``mount_ui`` registers."""
    return any(
        method == "MOUNT" or ROUTE_CAPABILITIES[(method, path)].capability == "ui.shell"
        for method, path in route_keys(route)
    )


def _gateway(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    built: bool,
    dashboard: bool = False,
) -> FastAPI:
    """Rebuild the production gateway's routes with a chosen static branch.

    The API routes are the production app's own objects, in order; the
    static tail comes from a real ``mount_ui`` call against temporary
    upload and dist directories, so both SPA branches are exercised in any
    checkout. ``dashboard`` injects the gated routers through the
    production gate before the static tail, as import does.
    """
    public = tmp_path / "public"
    (public / "character_portraits").mkdir(parents=True)
    (public / "character_portraits" / "hero.png").write_bytes(b"png")
    dist = tmp_path / "dist"
    if built:
        dist.mkdir()
        (dist / "index.html").write_text("<!doctype html><title>shell</title>")
    monkeypatch.setattr(static_ui, "UI_PUBLIC_DIR", public)
    monkeypatch.setattr(static_ui, "UI_DIST_DIR", dist)

    gateway = FastAPI(
        title=narrative.app.title,
        lifespan=narrative.gateway_lifespan,
        exception_handlers=dict(narrative.app.exception_handlers),
        middleware=list(narrative.app.user_middleware),
    )
    framework = {route.path for route in gateway.routes}  # type: ignore[attr-defined]
    gateway.router.routes.extend(
        route
        for route in narrative.app.routes
        if not _is_static_tail(route)
        and getattr(route, "path", None) not in framework
        and not str(getattr(route, "path", "")).startswith("/api/dev/")
    )
    if dashboard:
        settings = _dashboard_settings(tmp_path, enabled=True)
        narrative._include_orrery_dev_router(gateway, settings)
        narrative._include_backstage_router(gateway, settings)
    static_ui.mount_ui(gateway)
    return gateway


def _keys(app: FastAPI) -> Set[RouteKey]:
    """Every registry key the routes of ``app`` dispatch under."""
    return {key for route in app.routes for key in route_keys(route)}


def test_production_gateway_is_fully_classified() -> None:
    """Every route, websocket, and mount on the real app has an entry."""
    assert classify_app(narrative.app) == []
    require_classified(narrative.app)
    keys = _keys(narrative.app)
    assert ("WS", "/ws/narrative") in keys
    assert ("MOUNT", "/character_portraits") in keys
    assert ("MOUNT", "/place_images") in keys
    assert ("GET", "/runtime/status") in keys
    assert ("GET", "/health") in keys


def test_dashboard_routers_are_classified_through_the_real_gate(
    tmp_path: Path,
) -> None:
    """The dashboard-gated routers classify as operator when forced on."""
    target = FastAPI()
    settings = _dashboard_settings(tmp_path, enabled=True)
    narrative._include_orrery_dev_router(target, settings)
    narrative._include_backstage_router(target, settings)
    dev_keys = {key for key in _keys(target) if key[1].startswith("/api/dev/")}
    assert any(path.startswith("/api/dev/orrery/") for _, path in dev_keys)
    assert any(path.startswith("/api/dev/backstage/") for _, path in dev_keys)

    assert classify_app(target) == []
    assert {ROUTE_CAPABILITIES[key].plane for key in dev_keys} == {"operator"}
    assert not {
        key for key in _keys(build_player_app(target)) if key[1].startswith("/api/")
    }
    assert dev_keys <= _keys(build_operator_app(target))


@pytest.mark.parametrize("built", [False, True], ids=["dist-missing", "dist-built"])
def test_player_projection_omits_operator_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, built: bool
) -> None:
    """Operator endpoints answer 404/405 through the player app's dispatch."""
    gateway = _gateway(tmp_path, monkeypatch, built=built, dashboard=True)
    require_classified(gateway)
    player = TestClient(build_player_app(gateway))
    operator = TestClient(build_operator_app(gateway))

    for method, path in OPERATOR_REQUESTS:
        response = player.request(method, path)
        assert response.status_code in (404, 405), (method, path, response.text)

    # The same requests reach their handlers through the operator plane.
    assert operator.head("/api/settings").status_code == 200
    assert operator.post("/api/slot/abc/lock").status_code == 422
    assert operator.get("/api/dev/backstage/health").json() == {"ok": True}
    assert player.post("/api/slot/abc/lock").status_code in (404, 405)


@pytest.mark.parametrize("built", [False, True], ids=["dist-missing", "dist-built"])
def test_player_projection_keeps_reading_and_play_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, built: bool
) -> None:
    """Reading routes, the progress socket, uploads, and the shell stay routed."""
    gateway = _gateway(tmp_path, monkeypatch, built=built)
    player = TestClient(build_player_app(gateway))

    health = player.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    # Slot validation inside the reader handler proves the route matched.
    latest = player.get("/api/narrative/latest-chunk", params={"slot": 9})
    assert latest.status_code == 400
    assert player.get("/api/characters/1/images", params={"slot": 9}).status_code == (
        400
    )
    assert player.get("/character_portraits/hero.png").content == b"png"
    with player.websocket_connect("/ws/narrative?slot=1"):
        pass

    shell = player.get("/reader")
    if built:
        assert shell.status_code == 200
        assert "<title>shell</title>" in shell.text
    else:
        assert shell.status_code == 503
        assert "UI build not found" in shell.text


@pytest.mark.requires_postgres
def test_player_projection_paces_the_genesis_stage_waiter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_gate_db: str
) -> None:
    """The new-story wait screen needs nothing from the operator plane.

    ``GET /api/settings`` is operator-only, so the player-plane Retrograde
    status route the waiter reads before posting the transition carries the
    configured poll interval and the identity of the run owning its record.
    """
    document = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    document["orrery"]["retrograde"]["wizard"][  # type: ignore[index]
        "status_poll_interval_seconds"
    ] = 2.5
    config = tmp_path / "nexus.toml"
    config.write_text(tomlkit.dumps(document))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))
    player = TestClient(build_player_app(_gateway(tmp_path, monkeypatch, built=False)))

    assert player.get("/api/settings").status_code in (404, 405)
    status = player.get("/api/story/new/retrograde/status", params={"slot": 4})
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["status_poll_interval_seconds"] == 2.5
    assert body["run"] is None or isinstance(body["run"], str)


@pytest.mark.parametrize("built", [False, True], ids=["dist-missing", "dist-built"])
def test_projections_preserve_registration_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, built: bool
) -> None:
    """Both projections reuse the source route objects in source order."""
    gateway = _gateway(tmp_path, monkeypatch, built=built, dashboard=True)
    framework = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    source: List[BaseRoute] = [
        route
        for route in gateway.routes
        if getattr(route, "path", None) not in framework
    ]
    player = build_player_app(gateway)
    operator = build_operator_app(gateway)

    operator_routes = [
        route
        for route in operator.routes
        if getattr(route, "path", None) not in framework
    ]
    assert operator_routes == source
    player_routes = list(player.routes)
    assert player_routes == [
        route
        for route in source
        if all(ROUTE_CAPABILITIES[key].plane == "player" for key in route_keys(route))
    ]
    # The SPA catch-all stays last in both projections.
    for projected in (player_routes, operator_routes):
        tail = route_keys(projected[-1])
        assert all(ROUTE_CAPABILITIES[key].capability == "ui.shell" for key in tail)


def test_player_projection_serves_no_schema_or_docs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The schema describes only the operator app; the player app has none."""
    gateway = _gateway(tmp_path, monkeypatch, built=False)
    player = TestClient(build_player_app(gateway))
    operator = TestClient(build_operator_app(gateway))

    for path in ("/openapi.json", "/docs", "/redoc"):
        response = player.get(path)
        assert response.status_code == 503, path
        assert "swagger" not in response.text.lower()
        assert '"openapi"' not in response.text

    schema = operator.get("/openapi.json").json()
    assert "/api/secrets/status" in schema["paths"]
    assert "/api/narrative/continue" in schema["paths"]
    assert operator.get("/docs").status_code == 200


def test_projections_share_exception_handlers_and_middleware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validation errors never echo input, and CORS matches the gateway."""
    gateway = _gateway(tmp_path, monkeypatch, built=False)
    player = TestClient(build_player_app(gateway))

    secret = "sk-route-capability-probe"
    response = player.post(
        "/api/narrative/select-choice", json={"slot": 1, "chunk_id": secret}
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert all("input" not in error for error in response.json()["detail"])

    origin = get_gateway_cors_allowed_origins()[0]
    preflight = player.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin


def test_projections_carry_the_source_app_metadata() -> None:
    """A proxied gateway keeps its root path and schema metadata."""
    tags = [{"name": "narrative", "description": "Turns"}]
    source = FastAPI(
        debug=True,
        title="Probe",
        description="Route projection probe",
        version="9.9.9",
        openapi_tags=tags,
        root_path="/nexus",
    )
    for projection in (build_player_app(source), build_operator_app(source)):
        assert projection.debug is True
        assert projection.title == "Probe"
        assert projection.description == "Route projection probe"
        assert projection.version == "9.9.9"
        assert projection.openapi_tags == tags
        assert projection.root_path == "/nexus"


def test_projection_runs_the_gateway_lifespan_against_the_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared handlers read source state, and one lifespan runs at a time."""
    monkeypatch.delenv("NEXUS_SLOT", raising=False)
    player = build_player_app(narrative.app)
    operator = build_operator_app(narrative.app)

    with TestClient(player) as client:
        assert client.get("/health").status_code == 200
        assert narrative.app.state.route_projection_lifespan == "player"
        assert narrative.app.state.scheduler is None
        with pytest.raises(RouteCapabilityError, match="already running"):
            with TestClient(operator):
                pass
    assert narrative.app.state.route_projection_lifespan is None

    with TestClient(operator) as client:
        assert narrative.app.state.route_projection_lifespan == "operator"
    assert narrative.app.state.route_projection_lifespan is None


def test_unclassified_routes_fail_classification_and_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new router, websocket, or mount cannot silently enter either plane."""
    gateway = _gateway(tmp_path, monkeypatch, built=False)
    require_classified(gateway)

    dummy = APIRouter(prefix="/api/dummy")

    @dummy.get("/probe")
    async def probe() -> dict:
        return {"ok": True}

    async def dummy_socket(websocket: WebSocket) -> None:
        await websocket.close()

    gateway.include_router(dummy)
    gateway.router.routes.insert(0, WebSocketRoute("/ws/dummy", dummy_socket))
    gateway.router.routes.insert(
        0, Mount("/dummy_files", app=StaticFiles(directory=tmp_path))
    )

    expected = [
        ("MOUNT", "/dummy_files"),
        ("WS", "/ws/dummy"),
        ("GET", "/api/dummy/probe"),
    ]
    assert classify_app(gateway) == expected
    for check in (require_classified, build_player_app, build_operator_app):
        with pytest.raises(UnclassifiedRouteError) as excinfo:
            check(gateway)
        assert excinfo.value.keys == expected


def test_route_after_the_shell_catch_all_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A classified route registered after the catch-all could never match."""
    gateway = _gateway(tmp_path, monkeypatch, built=False)
    health = next(
        route for route in gateway.routes if getattr(route, "path", "") == "/health"
    )
    gateway.router.routes.append(health)
    with pytest.raises(RouteCapabilityError, match="after the app-shell catch-all"):
        build_player_app(gateway)


def test_registry_has_no_stale_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every entry names a route some gateway configuration registers."""
    registered = _keys(narrative.app)
    registered |= _keys(
        _gateway(tmp_path / "missing", monkeypatch, built=False, dashboard=True)
    )
    registered |= _keys(_gateway(tmp_path / "built", monkeypatch, built=True))
    assert set(ROUTE_CAPABILITIES) - registered == set()


def test_retired_chunk_state_route_is_not_served() -> None:
    """The slot-blind chunk-state route is gone rather than a 500 (#807).

    It called a two-argument method with three arguments and always failed.
    """
    response = TestClient(narrative.app).get(
        "/api/chunks/states", params={"start": 1, "end": 2, "slot": 5}
    )
    assert response.status_code == 404, response.text
    assert ("GET", "/api/chunks/states") not in _keys(narrative.app)
    assert ("GET", "/api/chunks/states") not in ROUTE_CAPABILITIES


def test_retired_wizard_stream_route_is_not_served() -> None:
    """The wizard's NDJSON stream route is removed rather than repaired (#1081).

    Its handler iterated ``agent.run_stream(...)``, an async context manager,
    so it raised before reaching the agent. POST now meets only the GET shell
    catch-all (built or missing UI), which answers 405. The empty body fails
    request validation (422) if the route ever returns, before any slot
    database is opened.
    """
    response = TestClient(narrative.app).post("/api/story/new/chat/stream", json={})
    assert response.status_code == 405, response.text
    assert ("POST", "/api/story/new/chat/stream") not in _keys(narrative.app)
    assert ("POST", "/api/story/new/chat/stream") not in ROUTE_CAPABILITIES


@pytest.mark.parametrize(
    "key",
    [
        ("POST", "/api/narrative/continue"),
        ("POST", "/api/narrative/approve"),
        ("POST", "/api/narrative/select-choice"),
        ("POST", "/api/narrative/retry"),
        ("POST", "/api/slot/{slot}/undo"),
        ("POST", "/api/story/new/setup/start"),
        ("POST", "/api/story/new/chat"),
        ("PUT", "/api/story/new/weird"),
        ("POST", "/api/story/new/transition"),
        ("PATCH", "/api/preferences"),
        ("WS", "/ws/narrative"),
    ],
)
def test_play_is_on_the_player_plane(key: RouteKey) -> None:
    """The issue's ruling keeps narrative turns, the wizard, and preferences."""
    assert ROUTE_CAPABILITIES[key].plane == "player"


def test_destructive_routes_are_pinned() -> None:
    """Exactly these routes can irreversibly wipe data, whatever their plane.

    The wizard admits any unlocked slot: ``setup/start`` discards an occupied
    slot's in-progress wizard and ``transition`` deletes its world, so both
    are destructive on the player plane. Everything else destructive is
    operator-only.
    """
    destructive = {
        key: capability.plane
        for key, capability in ROUTE_CAPABILITIES.items()
        if capability.destructive
    }
    assert destructive == {
        ("PUT", "/api/secrets/{provider}"): "operator",
        ("POST", "/api/story/new/setup/reset"): "operator",
        ("DELETE", "/api/characters/{character_id}/images/{image_id}"): "operator",
        ("DELETE", "/api/places/{place_id}/images/{image_id}"): "operator",
        ("POST", "/api/local-models/delete"): "operator",
        ("POST", "/api/story/new/setup/start"): "player",
        ("POST", "/api/story/new/transition"): "player",
    }


def test_unclassified_route_fails_the_gateway_import() -> None:
    """The import-time hook refuses to build a gateway with a gap."""
    code = (
        "from types import MappingProxyType\n"
        "import nexus.api.route_capabilities as rc\n"
        "rc.ROUTE_CAPABILITIES = MappingProxyType(\n"
        "    {k: v for k, v in rc.ROUTE_CAPABILITIES.items()\n"
        "     if k != ('POST', '/api/slot/{slot}/lock')}\n"
        ")\n"
        "import nexus.api.narrative\n"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode != 0
    assert "UnclassifiedRouteError" in result.stderr
    assert "POST /api/slot/{slot}/lock" in result.stderr


def test_feed_is_player_read_without_provider_effect() -> None:
    """The real feed is classified, projected, and precedes the SPA tail."""
    key = ("GET", "/api/narrative/feed")
    capability = ROUTE_CAPABILITIES[key]
    assert (
        capability.plane,
        capability.capability,
        capability.slot_mode,
        capability.provider_effect,
        capability.destructive,
    ) == (
        "player",
        "narrative.read",
        "read",
        False,
        False,
    )
    assert classify_app(narrative.app) == []
    player = build_player_app(narrative.app)
    assert key in _keys(player)
    for app in (narrative.app, player):
        feed = next(i for i, route in enumerate(app.routes) if key in route_keys(route))
        shell = next(
            i
            for i, route in enumerate(app.routes)
            if any(
                ROUTE_CAPABILITIES[k].capability == "ui.shell"
                for k in route_keys(route)
            )
        )
        assert feed < shell
    response = TestClient(player).get("/api/narrative/feed", params={"slot": 9})
    assert response.status_code == 400
