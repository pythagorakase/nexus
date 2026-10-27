"""The gateway's two-listener launcher and its direct launch (issue #824).

Offline: every child process runs with ``NEXUS_SLOT`` unset (no scheduler, no
slot database) and ``NEXUS_RUNTIME_CONFIG`` naming a private copy of the
checkout's ``nexus.toml`` whose state directory is the test's, and every port
is OS-assigned, so no owner port (8002, 8003) is ever bound.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import pytest
import requests  # type: ignore[import-untyped]
import tomlkit
from fastapi.testclient import TestClient

from nexus.api.route_capabilities import (
    RouteCapabilityError,
    build_operator_app,
    build_player_app,
)
from nexus.config import load_settings
from nexus.runtime import RUNTIME_CONFIG_ENV
from nexus.runtime.logging_config import build_logging_config

REPO_ROOT = Path(__file__).resolve().parents[2]
STARTUP_DEADLINE_SECONDS = 60
STOP_DEADLINE_SECONDS = 30


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _private_config(tmp_path: Path, *, operator_port: int | None = None) -> Path:
    """A copy of the checkout's nexus.toml with this test's state directory."""
    document: Any = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    document["runtime"]["state_dir"] = str(tmp_path / "state")
    if operator_port is not None:
        document["runtime"]["gateway"]["operator_port"] = operator_port
    path = tmp_path / "nexus.toml"
    path.write_text(tomlkit.dumps(document))
    return path


def _log_config(tmp_path: Path, config: Path) -> Path:
    """The dictConfig JSON the supervisor writes for ``--log-config``."""
    runtime = load_settings(config).runtime
    assert runtime is not None
    path = tmp_path / "logging.json"
    path.write_text(json.dumps(build_logging_config(runtime.logs)))
    return path


def _child_env(config: Path, **extra: str) -> dict[str, str]:
    env = dict(os.environ)
    for name in (
        "NEXUS_SLOT",
        "NEXUS_API_URL",
        "NEXUS_GATEWAY_PORT",
        "NEXUS_PLAYER_PORT",
        "NARRATIVE_API_HOST",
        "NARRATIVE_API_PORT",
    ):
        env.pop(name, None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env[RUNTIME_CONFIG_ENV] = str(config)
    env.update(extra)
    return env


@pytest.fixture()
def spawn(tmp_path: Path) -> Iterator[Any]:
    """Start a child Python module with its output in a log; stop it afterwards."""
    children: list[subprocess.Popen[bytes]] = []

    def _spawn(
        argv: list[str], env: dict[str, str], name: str = "child"
    ) -> tuple[subprocess.Popen[bytes], Path]:
        log_path = tmp_path / f"{name}.log"
        with open(log_path, "wb") as log:
            process = subprocess.Popen(
                [sys.executable, *argv],
                cwd=REPO_ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        children.append(process)
        return process, log_path

    yield _spawn
    for process in children:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=STOP_DEADLINE_SECONDS)


def _await_planes(
    process: subprocess.Popen[bytes], log_path: Path, planes: dict[int, str]
) -> None:
    """Wait until each port's ``/health`` answers 200 and names its plane."""
    pending = dict(planes)
    deadline = time.monotonic() + STARTUP_DEADLINE_SECONDS
    while pending:
        assert process.poll() is None, log_path.read_text()
        for port, plane in list(pending.items()):
            try:
                health = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            except requests.RequestException:
                continue
            assert health.status_code == 200, health.text
            assert health.json()["plane"] == plane, (port, health.text)
            del pending[port]
        assert time.monotonic() < deadline, log_path.read_text()
        time.sleep(0.2)


def _launcher_argv(player: str, operator: int, log_config: Path) -> list[str]:
    return [
        "-m",
        "nexus.api.serve",
        "--host",
        "127.0.0.1",
        "--port",
        player,
        "--operator-port",
        str(operator),
        "--log-config",
        str(log_config),
    ]


def test_launcher_serves_both_planes_and_stops_on_sigterm(
    tmp_path: Path, spawn: Any
) -> None:
    """One process, two listeners; SIGTERM closes both and runs one shutdown."""
    config = _private_config(tmp_path)
    player, operator = _free_port(), _free_port()
    process, log_path = spawn(
        _launcher_argv(str(player), operator, _log_config(tmp_path, config)),
        _child_env(config),
        name="serve",
    )
    _await_planes(process, log_path, {player: "player", operator: "operator"})

    settings_on_player = requests.get(f"http://127.0.0.1:{player}/api/settings")
    settings_on_operator = requests.get(f"http://127.0.0.1:{operator}/api/settings")
    assert settings_on_player.status_code == 404
    assert settings_on_operator.status_code == 200, settings_on_operator.text

    process.send_signal(signal.SIGTERM)
    process.wait(timeout=STOP_DEADLINE_SECONDS)
    assert not _port_open(player)
    assert not _port_open(operator)
    output = log_path.read_text()
    # The operator listener ran the gateway's one lifespan; the player ran none.
    assert output.count("Application startup complete.") == 1, output
    assert output.count("Application shutdown complete.") == 1, output
    for port in (player, operator):
        assert f"Uvicorn running on http://127.0.0.1:{port}" in output


def test_launcher_port_off_opens_only_the_operator_listener(
    tmp_path: Path, spawn: Any
) -> None:
    """``--port off`` is an operator-only lane: one listener, the whole runtime."""
    config = _private_config(tmp_path)
    operator = _free_port()
    process, log_path = spawn(
        _launcher_argv("off", operator, _log_config(tmp_path, config)),
        _child_env(config),
        name="serve-off",
    )
    _await_planes(process, log_path, {operator: "operator"})
    assert requests.get(f"http://127.0.0.1:{operator}/api/settings").status_code == 200
    output = log_path.read_text()
    assert output.count("Uvicorn running on") == 1, output

    process.send_signal(signal.SIGTERM)
    process.wait(timeout=STOP_DEADLINE_SECONDS)
    assert not _port_open(operator)


def test_launcher_refuses_equal_ports(tmp_path: Path) -> None:
    """The two listeners need two ports; the refusal binds nothing."""
    config = _private_config(tmp_path)
    port = _free_port()
    completed = subprocess.run(
        [
            sys.executable,
            *_launcher_argv(str(port), port, _log_config(tmp_path, config)),
        ],
        cwd=REPO_ROOT,
        env=_child_env(config),
        capture_output=True,
        text=True,
        timeout=STARTUP_DEADLINE_SECONDS,
    )
    assert completed.returncode == 2, completed.stderr
    assert "need two ports" in completed.stderr
    assert not _port_open(port)


def test_launcher_exits_nonzero_when_the_player_port_is_held(
    tmp_path: Path, spawn: Any
) -> None:
    """A player listener that cannot bind stops the operator listener too."""
    config = _private_config(tmp_path)
    player, operator = _free_port(), _free_port()
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", player))
        holder.listen()
        process, log_path = spawn(
            _launcher_argv(str(player), operator, _log_config(tmp_path, config)),
            _child_env(config),
            name="serve-held",
        )
        returncode = process.wait(timeout=STARTUP_DEADLINE_SECONDS)
    output = log_path.read_text()
    assert returncode == 1, output
    assert not _port_open(operator)
    # The operator listener started, then shut its lifespan down once.
    assert output.count("Application shutdown complete.") == 1, output


def test_direct_launch_defaults_to_the_configured_operator_port(
    tmp_path: Path, spawn: Any
) -> None:
    """``python -m nexus.api.narrative`` binds [runtime.gateway].operator_port."""
    operator = _free_port()
    config = _private_config(tmp_path, operator_port=operator)
    process, log_path = spawn(
        ["-m", "nexus.api.narrative"], _child_env(config), name="direct"
    )
    _await_planes(process, log_path, {operator: "operator"})
    assert f"Uvicorn running on http://127.0.0.1:{operator}" in log_path.read_text()


def test_gateway_lifespan_excludes_projections() -> None:
    """The gateway app and a projection never run the one lifespan together."""
    from nexus.api import narrative

    gateway = narrative.app
    with TestClient(gateway):
        with pytest.raises(RouteCapabilityError, match="already running"):
            with TestClient(build_player_app(gateway)):
                pass
    with TestClient(build_operator_app(gateway)):
        with pytest.raises(RouteCapabilityError, match="already running"):
            with TestClient(gateway):
                pass
    # Each exit released the lifespan: either side starts again alone.
    with TestClient(gateway) as client:
        assert client.get("/health").json()["plane"] == "operator"
    with TestClient(build_player_app(gateway)) as client:
        assert client.get("/health").json()["plane"] == "player"
