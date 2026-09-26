"""The ordinary reader never serves the hidden psychology profile (issue #769)."""

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from nexus.api.narrative import app as gateway_app
from nexus.api.reader_endpoints import router as reader_router


def test_gateway_registers_no_character_psychology_route() -> None:
    """The assembled gateway mounts the cast routes but no psychology view."""
    paths = {route.path for route in gateway_app.routes if isinstance(route, APIRoute)}

    assert "/api/characters/{character_id}/relationships" in paths
    assert not [path for path in paths if "psychology" in path]


def test_reader_router_leaves_psychology_path_unrouted() -> None:
    """The retired path is FastAPI's own 404, not a lookup that found no row."""
    app = FastAPI()
    app.include_router(reader_router)

    response = TestClient(app).get("/api/characters/1/psychology?slot=4")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
