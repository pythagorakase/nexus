"""The player UI receives only explicitly allowlisted display configuration."""

from pathlib import Path
from typing import Any

import pytest
import tomlkit
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.api import narrative
from nexus.api.route_capabilities import (
    ROUTE_CAPABILITIES,
    build_player_app,
    route_keys,
)


def test_ui_config_serves_only_the_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real route returns the configured hold without leaking other UI keys."""
    from nexus.api.ui_config_endpoints import router

    config = tmp_path / "config" / "nexus.toml"
    config.parent.mkdir()
    document: Any = tomlkit.parse(Path("nexus.toml").read_text())
    document["runtime"]["state_dir"] = str(tmp_path / "player-state")
    document["ui"]["announcer"] = {"hold_ms": 7300}
    config.write_text(tomlkit.dumps(document))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/api/config/ui")
    assert response.status_code == 200, response.text
    assert response.json() == {"announcer": {"hold_ms": 7300}}


def test_ui_config_is_a_player_route() -> None:
    """The actual gateway registers and projects this database-free player read."""
    key = ("GET", "/api/config/ui")
    capability = ROUTE_CAPABILITIES[key]
    assert (
        capability.plane,
        capability.capability,
        capability.slot_mode,
        capability.provider_effect,
        capability.destructive,
    ) == ("player", "ui.config", "none", False, False)
    player = build_player_app(narrative.app)
    assert key in {key for route in player.routes for key in route_keys(route)}
