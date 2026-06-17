"""Real process lifecycle tests for the managed runtime (issue #396).

No mocks: these spawn the actual gateway and mock_openai with uvicorn via the
real CLI entrypoint (``python -m nexus.cli``), probe real HTTP health, and
assert teardown by port and pid. They run on lane-assigned ports (8032+/5133)
so a developer stack on :8002/:5102 is never touched.

Run with: NEXUS_RUN_POSTGRES=1 python -m pytest tests/test_runtime
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests
import tomlkit

from nexus.config import load_settings
from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from nexus.runtime.supervisor import _pid_alive, _port_open

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_PORT = 8032
MOCK_PORT = 5133
EXTERNAL_GATEWAY_PORT = 8034
TEST_SLOT = 5

pytestmark = pytest.mark.requires_postgres


def _write_config(
    tmp_path: Path,
    *,
    profile: str = "local",
    gateway_port: int = GATEWAY_PORT,
    mock_port: int = MOCK_PORT,
    include_test_provider: bool = True,
    external_gateway_url: str | None = None,
    remote_base_url: str | None = None,
) -> Path:
    doc = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    doc["runtime"]["profile"] = profile
    doc["runtime"]["state_dir"] = str(tmp_path / "state")
    doc["runtime"]["services"]["gateway"]["port"] = gateway_port
    doc["runtime"]["services"]["mock_openai"]["port"] = mock_port
    if include_test_provider:
        doc["global"]["model"]["api_models"]["test"][
            "base_url"
        ] = f"http://127.0.0.1:{mock_port}/v1"
    else:
        del doc["global"]["model"]["api_models"]["test"]
        # default_slot_model = "TEST" would dangle without the registry entry
        doc["global"]["model"]["default_slot_model"] = "@openai.default"
    if external_gateway_url:
        doc["runtime"]["external"] = {"gateway_url": external_gateway_url}
    if remote_base_url:
        doc["runtime"]["remote"] = {"base_url": remote_base_url}
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "nexus.toml"
    path.write_text(tomlkit.dumps(doc))
    return path


def _cli(*args: str, config: Path, timeout: float = 120) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    completed = subprocess.run(
        [sys.executable, "-m", "nexus.cli", "--json", *args, "--config", str(config)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=timeout,
    )
    output = completed.stdout or completed.stderr
    payload = json.loads(output)
    payload["_returncode"] = completed.returncode
    return payload


def _down(config: Path) -> None:
    _cli("down", config=config)


def test_local_profile_full_lifecycle(tmp_path):
    """up -> status -> logs -> restart -> down against real processes."""
    config = _write_config(tmp_path)
    try:
        up = _cli("up", "--slot", str(TEST_SLOT), config=config)
        assert up["_returncode"] == 0, up
        assert set(up["services"]) == {"gateway", "mock_openai"}
        gateway_pid = up["services"]["gateway"]["pid"]
        assert _pid_alive(gateway_pid)

        # The gateway answers /health and the aggregate /runtime/status.
        base = f"http://127.0.0.1:{GATEWAY_PORT}"
        assert requests.get(f"{base}/health", timeout=5).status_code == 200
        status_response = requests.get(f"{base}/runtime/status", timeout=5)
        assert status_response.status_code == 200
        runtime_status = status_response.json()
        assert runtime_status["profile"] == "local"
        assert runtime_status["slot"] == TEST_SLOT
        assert runtime_status["database"]["ok"] is True
        assert runtime_status["database"]["dbname"] == f"save_0{TEST_SLOT}"
        assert runtime_status["services"]["gateway"]["ok"] is True
        assert runtime_status["services"]["mock_openai"]["ok"] is True
        assert runtime_status["auth"]["header"] == "X-Nexus-Auth"
        assert runtime_status["ok"] is True

        # nexus status merges supervisor process state with the endpoint.
        status = _cli("status", config=config)
        assert status["processes"]["gateway"]["state"] == "running"
        assert status["processes"]["gateway"]["pid"] == gateway_pid
        assert status["processes"]["gateway"]["port"] == GATEWAY_PORT
        assert status["processes"]["gateway"]["uptime_seconds"] >= 0
        assert status["runtime"]["ok"] is True

        # Captured logs are readable through nexus logs.
        logs = _cli("logs", "gateway", "-n", "50", config=config)
        assert logs["_returncode"] == 0
        assert any("Uvicorn running" in line for line in logs["lines"])

        # A second up refuses while services run.
        again = _cli("up", config=config)
        assert again["_returncode"] == 1
        assert "already running" in again["error"]

        # Restarting the gateway yields a new pid; mock_openai is untouched.
        mock_pid = up["services"]["mock_openai"]["pid"]
        restart = _cli("restart", "gateway", config=config)
        new_pid = restart["services"]["gateway"]["pid"]
        assert new_pid != gateway_pid
        assert _pid_alive(new_pid)
        assert _pid_alive(mock_pid)
        assert requests.get(f"{base}/health", timeout=5).status_code == 200

        # A full restart without --slot preserves the running slot instead of
        # falling back to runtime.default_slot.
        full_restart = _cli("restart", config=config)
        assert full_restart["slot"] == TEST_SLOT
        full_gateway_pid = full_restart["services"]["gateway"]["pid"]
        full_mock_pid = full_restart["services"]["mock_openai"]["pid"]
        assert full_gateway_pid != new_pid
        assert full_mock_pid != mock_pid
        runtime_status = requests.get(f"{base}/runtime/status", timeout=5).json()
        assert runtime_status["slot"] == TEST_SLOT
        assert runtime_status["database"]["dbname"] == f"save_0{TEST_SLOT}"
        new_pid = full_gateway_pid
        mock_pid = full_mock_pid

        # down leaves no orphans: pids dead, ports closed, pidfiles gone.
        down = _cli("down", config=config)
        assert set(down["stopped"]) == {"gateway", "mock_openai"}
        for pid in (new_pid, mock_pid):
            assert not _pid_alive(pid)
        assert not _port_open("127.0.0.1", GATEWAY_PORT)
        assert not _port_open("127.0.0.1", MOCK_PORT)
        state_dir = tmp_path / "state"
        assert not list(state_dir.glob("*.pid.json"))
        # Captured logs survive shutdown for postmortem reading.
        assert (state_dir / "gateway.log").exists()
    finally:
        _down(config)


def test_up_refuses_port_held_by_unmanaged_process(tmp_path):
    """A foreign listener on the gateway port is a hard error, not a takeover."""
    config = _write_config(tmp_path)
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", GATEWAY_PORT))
    blocker.listen(1)
    try:
        result = _cli("up", config=config)
        assert result["_returncode"] == 1
        assert "already in use by an unmanaged process" in result["error"]
        state_dir = tmp_path / "state"
        assert not list(state_dir.glob("*.pid.json"))
    finally:
        blocker.close()
        _down(config)


def test_mock_openai_auto_gating_follows_test_provider(tmp_path):
    """enabled='auto' spawns the mock only while TEST is in the registry."""
    with_test = _write_config(tmp_path, include_test_provider=True)
    supervisor = Supervisor.from_config(with_test)
    assert set(supervisor.enabled_services()) == {"gateway", "mock_openai"}

    without_test = _write_config(tmp_path / "no-test", include_test_provider=False)
    supervisor = Supervisor.from_config(without_test)
    assert set(supervisor.enabled_services()) == {"gateway"}


@pytest.fixture()
def external_gateway(tmp_path_factory):
    """A gateway this test suite does NOT manage - started out-of-band."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["NEXUS_SLOT"] = str(TEST_SLOT)
    env[RUNTIME_CONFIG_ENV] = str(REPO_ROOT / "nexus.toml")
    log_path = tmp_path_factory.mktemp("external") / "gateway.log"
    with open(log_path, "wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "nexus.api.narrative:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(EXTERNAL_GATEWAY_PORT),
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    url = f"http://127.0.0.1:{EXTERNAL_GATEWAY_PORT}"
    deadline = time.monotonic() + 60
    while True:
        try:
            if requests.get(f"{url}/health", timeout=1).status_code == 200:
                break
        except requests.RequestException:
            pass
        if time.monotonic() > deadline:
            process.terminate()
            raise TimeoutError(f"external gateway never became healthy:\n{log_path}")
        time.sleep(0.25)
    yield url
    process.terminate()
    process.wait(timeout=15)


def test_external_profile_attaches_and_never_spawns(tmp_path, external_gateway):
    """profile=external health-checks the running stack and manages nothing."""
    config = _write_config(
        tmp_path, profile="external", external_gateway_url=external_gateway
    )
    up = _cli("up", config=config)
    assert up["_returncode"] == 0
    assert up["profile"] == "external"
    assert up["services"]["gateway"]["ok"] is True
    # Nothing was spawned: no pidfiles appear.
    assert not list((tmp_path / "state").glob("*.pid.json"))

    status = _cli("status", config=config)
    assert status["runtime"]["services"]["gateway"]["ok"] is True
    assert "processes" not in status

    down = _cli("down", config=config)
    assert down["_returncode"] == 1
    assert "profile" in down["error"]

    logs = _cli("logs", config=config)
    assert logs["_returncode"] == 1


def test_external_profile_fails_loud_when_target_is_down(tmp_path):
    """Attaching to a dead stack is an error, not a silent success."""
    config = _write_config(
        tmp_path,
        profile="external",
        external_gateway_url="http://127.0.0.1:39999",
    )
    up = _cli("up", config=config)
    assert up["_returncode"] == 1
    assert "unhealthy" in up["error"]


def test_remote_profile_status_hits_runtime_endpoint(tmp_path, external_gateway):
    """profile=remote reports the hosted runtime's /runtime/status."""
    config = _write_config(tmp_path, profile="remote", remote_base_url=external_gateway)
    up = _cli("up", config=config)
    assert up["_returncode"] == 0
    assert up["profile"] == "remote"
    assert up["runtime"]["services"]["gateway"]["ok"] is True

    status = _cli("status", config=config)
    assert status["gateway_url"] == external_gateway
    assert status["runtime"]["profile"] == "local"  # the remote host's profile
    assert status["runtime"]["version"]


def test_mock_port_must_match_test_base_url(tmp_path):
    """Config-load consistency: mock service port vs test provider base_url."""
    doc = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    doc["runtime"]["services"]["mock_openai"]["port"] = 5999
    path = tmp_path / "drift.toml"
    path.write_text(tomlkit.dumps(doc))
    with pytest.raises(Exception, match="does not match"):
        load_settings(path)
