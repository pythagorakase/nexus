"""Real process lifecycle tests for the managed runtime (issue #396).

No mocks: these spawn the actual gateway and mock_openai with uvicorn via the
real CLI entrypoint, probe real HTTP health, and assert teardown by port and
pid. Every port is OS-assigned (``ephemeral_ports``), so a developer stack on
:8002/:5102 is never touched.

No owner slot is touched either (issue #885). Every gateway serves slot
``TEST_SLOT`` routed to one module-scoped disposable template clone: the
supervisor spawns ``tests.slot_routed_uvicorn`` in place of ``python -m
uvicorn`` (same argv otherwise), the CLI runs as ``tests.slot_routed_cli`` so
the supervisor's own ``recover_active_slot_choice`` reaches the clone, and
``runtime.default_slot`` in each temporary config is the routed slot, so an
``up`` without ``--slot`` resolves to it as well. Each gateway lifespan's
``SlotScheduler`` therefore takes its lease in the clone's
``deferred_work_scheduler``.

Run with: NEXUS_RUN_POSTGRES=1 python -m pytest tests/test_runtime
"""

from __future__ import annotations


import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import requests  # type: ignore[import-untyped]
import tomlkit

from nexus.config import load_settings
from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from nexus.runtime.supervisor import _pid_alive, _port_open
from tests.model_registry_helpers import registry_model
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    routed_slot_environment,
    seed_protagonist,
    seed_story_clock,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
# Placeholders only: the autouse ephemeral_ports fixture replaces all four with
# OS-assigned ports before every test.
GATEWAY_PORT = 0
MOCK_PORT = 0
EXTERNAL_GATEWAY_PORT = 0
OVERRIDE_GATEWAY_PORT = 0
# The routed slot number: it resolves to ROUTED_DATABASE, never to an owner
# save, in every process these tests start.
TEST_SLOT = 5
# A slot the routed processes refuse: the restart steps set it as NEXUS_SLOT to
# prove the running slot, not the environment or the default, is restarted.
CONFLICTING_SLOT = 3
# The disposable clone serving TEST_SLOT; routed_clone sets it before each test.
ROUTED_DATABASE = ""
ROUTED_LAUNCHER = "tests.slot_routed_uvicorn"
ROUTED_CLI = "tests.slot_routed_cli"
# The supervisor's own gateway argv template, as nexus.toml ships it.
GATEWAY_ARGV_TEMPLATE = [
    "{python}",
    "-m",
    "uvicorn",
    "nexus.api.narrative:app",
    "--host",
    "{host}",
    "--port",
    "{port}",
    "--log-config",
    "{log_config}",
]

pytestmark = pytest.mark.requires_postgres


@pytest.fixture(scope="module")
def supervisor_clone() -> Iterator[str]:
    """One disposable template clone that every gateway in this module serves.

    The protagonist and story clock give the clone a canonical clock; no
    playable story is needed, because these tests exercise the supervisor,
    not narration.
    """
    with disposable_slot_database("qa885_supervisor") as dbname:
        seed_protagonist(dbname)
        seed_story_clock(
            dbname, world_time=datetime(2100, 1, 1, 1, tzinfo=timezone.utc)
        )
        yield dbname


@pytest.fixture(autouse=True)
def routed_clone(supervisor_clone: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point ROUTED_DATABASE at the module clone for the helpers below."""
    monkeypatch.setitem(globals(), "ROUTED_DATABASE", supervisor_clone)


def _routed_env() -> dict[str, str]:
    """The variables that route TEST_SLOT to the clone in a child process."""
    assert ROUTED_DATABASE, "routed_clone did not run"
    return routed_slot_environment(TEST_SLOT, ROUTED_DATABASE)


def _clone_lease_owner() -> str | None:
    """The owner of the clone's deferred-work scheduler lease, if any."""
    with closing(connect(ROUTED_DATABASE)) as conn, conn.cursor() as cur:
        cur.execute("SELECT owner_id FROM deferred_work_scheduler WHERE id")
        row = cur.fetchone()
    return None if row is None else row[0]


@pytest.fixture(autouse=True)
def ephemeral_ports(monkeypatch):
    """Allocate independent ports for real supervisor processes."""
    import contextlib

    with contextlib.ExitStack() as stack:
        for name in (
            "GATEWAY_PORT",
            "MOCK_PORT",
            "EXTERNAL_GATEWAY_PORT",
            "OVERRIDE_GATEWAY_PORT",
        ):
            sock = stack.enter_context(socket.socket())
            sock.bind(("127.0.0.1", 0))
            monkeypatch.setitem(globals(), name, sock.getsockname()[1])


def _write_config(
    tmp_path: Path,
    *,
    profile: str = "local",
    gateway_port: int | None = None,
    mock_port: int | None = None,
    include_test_provider: bool = True,
    external_gateway_url: str | None = None,
    remote_base_url: str | None = None,
) -> Path:
    gateway_port = GATEWAY_PORT if gateway_port is None else gateway_port
    mock_port = MOCK_PORT if mock_port is None else mock_port
    doc: Any = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    doc["runtime"]["profile"] = profile
    doc["runtime"]["state_dir"] = str(tmp_path / "state")
    # An `up` without --slot resolves runtime.default_slot: keep it routed.
    doc["runtime"]["default_slot"] = TEST_SLOT
    gateway = doc["runtime"]["services"]["gateway"]
    # Spawn the routed launcher with the supervisor's own argv template.
    command = [str(part) for part in gateway["command"]]
    assert command == GATEWAY_ARGV_TEMPLATE, command
    command[2] = ROUTED_LAUNCHER
    gateway["command"] = command
    gateway["env"] = _routed_env()
    gateway["port"] = gateway_port
    doc["runtime"]["services"]["mock_openai"]["port"] = mock_port
    if include_test_provider:
        doc["global"]["model"]["api_models"]["test"][
            "base_url"
        ] = f"http://127.0.0.1:{mock_port}/v1"
    else:
        del doc["global"]["model"]["api_models"]["test"]
        # default_slot_model = "TEST" would dangle without the registry entry
        doc["global"]["model"]["default_slot_model"] = registry_model("openai")
    if external_gateway_url:
        doc["runtime"]["external"] = {"gateway_url": external_gateway_url}
    if remote_base_url:
        doc["runtime"]["remote"] = {"base_url": remote_base_url}
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "nexus.toml"
    path.write_text(tomlkit.dumps(doc))
    return path


def _cli(
    *args: str,
    config: Path,
    timeout: float = 120,
    env_extra: dict | None = None,
) -> dict:
    env = dict(os.environ)
    for name in (
        "NEXUS_API_URL",
        "NEXUS_GATEWAY_PORT",
        "NEXUS_SLOT",
        RUNTIME_CONFIG_ENV,
    ):
        env.pop(name, None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.update(_routed_env())
    if env_extra:
        env.update(env_extra)
    completed = subprocess.run(
        [sys.executable, "-m", ROUTED_CLI, "--json", *args, "--config", str(config)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=timeout,
    )
    output = completed.stdout or completed.stderr
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        raise AssertionError(
            f"nexus {' '.join(args)} exited {completed.returncode} without JSON:\n"
            f"{completed.stderr[-2000:]}"
        ) from None
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
        # The supervisor spawned the routed launcher with its own argv.
        assert up["services"]["gateway"]["command"][1:3] == ["-m", ROUTED_LAUNCHER]
        # The gateway's scheduler holds its lease in the clone, not an owner.
        assert (_clone_lease_owner() or "").startswith(f"gateway:{gateway_pid}:")

        # The gateway answers /health and the aggregate /runtime/status.
        base = f"http://127.0.0.1:{GATEWAY_PORT}"
        assert requests.get(f"{base}/health", timeout=5).status_code == 200
        status_response = requests.get(f"{base}/runtime/status", timeout=5)
        assert status_response.status_code == 200
        runtime_status = status_response.json()
        assert runtime_status["profile"] == "local"
        assert runtime_status["slot"] == TEST_SLOT
        assert runtime_status["database"]["ok"] is True
        assert runtime_status["database"]["dbname"] == ROUTED_DATABASE
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
        assert status["runtime"]["database"]["dbname"] == ROUTED_DATABASE

        # Captured logs are readable through nexus logs; the routed launcher
        # runs uvicorn's own __main__, so the banner is uvicorn's.
        logs = _cli("logs", "gateway", "-n", "50", config=config)
        assert logs["_returncode"] == 0
        assert any(
            f"Uvicorn running on http://127.0.0.1:{GATEWAY_PORT}" in line
            for line in logs["lines"]
        )

        # A second up refuses while services run.
        again = _cli("up", config=config)
        assert again["_returncode"] == 1
        assert "already running" in again["error"]

        # runtime.default_slot is the routed slot here, so a restart that
        # dropped the recorded running slot and fell back to the default would
        # still pick TEST_SLOT. The restarts therefore run with a conflicting
        # NEXUS_SLOT: a restart that resolves the slot from the environment or
        # the default hands the routed CLI a slot it refuses, and the test
        # fails before any database opens.
        conflicting_slot = {"NEXUS_SLOT": str(CONFLICTING_SLOT)}

        # Restarting the gateway yields a new pid; mock_openai is untouched.
        mock_pid = up["services"]["mock_openai"]["pid"]
        restart = _cli("restart", "gateway", config=config, env_extra=conflicting_slot)
        assert restart["_returncode"] == 0, restart
        assert restart["services"]["gateway"]["slot"] == TEST_SLOT
        new_pid = restart["services"]["gateway"]["pid"]
        assert new_pid != gateway_pid
        assert _pid_alive(new_pid)
        assert _pid_alive(mock_pid)
        assert requests.get(f"{base}/health", timeout=5).status_code == 200
        status = _cli("status", config=config)
        assert status["runtime"]["slot"] == TEST_SLOT
        assert status["runtime"]["database"]["dbname"] == ROUTED_DATABASE

        # A full restart without --slot preserves the running slot instead of
        # falling back to NEXUS_SLOT or runtime.default_slot.
        full_restart = _cli("restart", config=config, env_extra=conflicting_slot)
        assert full_restart["_returncode"] == 0, full_restart
        assert full_restart["slot"] == TEST_SLOT
        full_gateway_pid = full_restart["services"]["gateway"]["pid"]
        full_mock_pid = full_restart["services"]["mock_openai"]["pid"]
        assert full_gateway_pid != new_pid
        assert full_mock_pid != mock_pid
        runtime_status = requests.get(f"{base}/runtime/status", timeout=5).json()
        assert runtime_status["slot"] == TEST_SLOT
        assert runtime_status["database"]["dbname"] == ROUTED_DATABASE
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
        # The refusal identifies the squatter (this pytest process) and
        # points test shells at the isolated-port lane.
        if shutil.which("lsof"):
            assert "Listener: pid=" in result["error"]
        assert "NEXUS_GATEWAY_PORT" in result["error"]
        state_dir = tmp_path / "state"
        assert not list(state_dir.glob("*.pid.json"))
    finally:
        blocker.close()
        _down(config)


def test_gateway_port_override_coexists_with_default_instance(tmp_path):
    """NEXUS_GATEWAY_PORT runs an isolated-state gateway beside the default."""
    config = _write_config(tmp_path)
    override_env = {"NEXUS_GATEWAY_PORT": str(OVERRIDE_GATEWAY_PORT)}
    try:
        base = _cli("up", config=config)
        assert base["_returncode"] == 0

        result = _cli("up", config=config, env_extra=override_env)
        assert result["_returncode"] == 0
        assert result["services"]["gateway"]["port"] == OVERRIDE_GATEWAY_PORT
        # The fixed-port sibling is borrowed from the default instance, not
        # respawned and not refused.
        assert result["services"]["mock_openai"].get("attached") is True
        assert _port_open("127.0.0.1", OVERRIDE_GATEWAY_PORT)
        assert _port_open("127.0.0.1", GATEWAY_PORT)

        # Isolated state: each instance keeps its own pidfiles.
        override_state = tmp_path / "state" / f"gateway-{OVERRIDE_GATEWAY_PORT}"
        assert (override_state / "gateway.pid.json").exists()
        assert (tmp_path / "state" / "gateway.pid.json").exists()

        # The override instance reports the port actually serving requests.
        status = requests.get(
            f"http://127.0.0.1:{OVERRIDE_GATEWAY_PORT}/runtime/status",
            timeout=10,
        ).json()
        assert status["services"]["gateway"]["port"] == OVERRIDE_GATEWAY_PORT

        # Downing the override instance leaves the default stack running.
        down = _cli("down", config=config, env_extra=override_env)
        assert set(down["stopped"]) == {"gateway"}
        assert not _port_open("127.0.0.1", OVERRIDE_GATEWAY_PORT)
        assert _port_open("127.0.0.1", GATEWAY_PORT)
        assert _port_open("127.0.0.1", MOCK_PORT)
    finally:
        _cli("down", config=config, env_extra=override_env)
        _down(config)


def test_gateway_port_override_garbage_is_loud(tmp_path):
    """A malformed override refuses to start anything, with a clear error."""
    config = _write_config(tmp_path)
    result = _cli("up", config=config, env_extra={"NEXUS_GATEWAY_PORT": "styrofoam"})
    assert result["_returncode"] == 1
    assert "NEXUS_GATEWAY_PORT must be an integer port" in result["error"]
    assert not _port_open("127.0.0.1", GATEWAY_PORT)


def test_gateway_port_override_first_then_default_stack(tmp_path):
    """Reverse order: override-first skips siblings, so default still owns them."""
    config = _write_config(tmp_path)
    override_env = {"NEXUS_GATEWAY_PORT": str(OVERRIDE_GATEWAY_PORT)}
    try:
        first = _cli("up", config=config, env_extra=override_env)
        assert first["_returncode"] == 0, first
        # No default stack yet: the fixed-port sibling is skipped, never
        # spawned into the override's isolated state.
        assert first["services"]["mock_openai"].get("skipped") is True
        assert _port_open("127.0.0.1", OVERRIDE_GATEWAY_PORT)
        assert not _port_open("127.0.0.1", MOCK_PORT)

        # The default stack then starts cleanly and owns its siblings.
        base = _cli("up", config=config)
        assert base["_returncode"] == 0, base
        assert base["services"]["mock_openai"].get("pid")
        assert _port_open("127.0.0.1", GATEWAY_PORT)
        assert _port_open("127.0.0.1", MOCK_PORT)
    finally:
        _cli("down", config=config, env_extra=override_env)
        _down(config)


def test_override_refuses_foreign_healthy_listener_on_sibling_port(tmp_path):
    """Health 200 alone is not ownership; a foreign listener is still refused."""
    config = _write_config(tmp_path)
    override_env = {"NEXUS_GATEWAY_PORT": str(OVERRIDE_GATEWAY_PORT)}
    foreign = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                "class H(BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        self.send_response(200)\n"
                "        self.end_headers()\n"
                "        self.wfile.write(b'ok')\n"
                "    def log_message(self, *a):\n"
                "        pass\n"
                f"HTTPServer(('127.0.0.1', {MOCK_PORT}), H).serve_forever()\n"
            ),
        ],
    )
    try:
        deadline = time.monotonic() + 10
        while not _port_open("127.0.0.1", MOCK_PORT):
            assert time.monotonic() < deadline, "foreign listener never bound"
            time.sleep(0.1)
        result = _cli("up", config=config, env_extra=override_env)
        assert result["_returncode"] == 1
        assert "already in use by an unmanaged process" in result["error"]
        # All-or-nothing: the already-started override gateway rolled back.
        assert not _port_open("127.0.0.1", OVERRIDE_GATEWAY_PORT)
    finally:
        foreign.terminate()
        foreign.wait(timeout=10)
        _cli("down", config=config, env_extra=override_env)


def test_gateway_port_override_sibling_collision_is_loud(tmp_path):
    """An override equal to another service's port is a config error."""
    config = _write_config(tmp_path)
    result = _cli("up", config=config, env_extra={"NEXUS_GATEWAY_PORT": str(MOCK_PORT)})
    assert result["_returncode"] == 1
    assert "collides with [runtime.services.mock_openai]" in result["error"]
    assert not _port_open("127.0.0.1", MOCK_PORT)


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
    """A gateway this test suite does NOT manage - started out-of-band.

    It serves the routed clone under its own temporary config, never the
    repository nexus.toml (whose state_dir and TEST base_url are the owner's).
    """
    external_dir = tmp_path_factory.mktemp("external")
    config = _write_config(external_dir, gateway_port=EXTERNAL_GATEWAY_PORT)
    env = dict(os.environ)
    for name in ("NEXUS_API_URL", "NEXUS_GATEWAY_PORT"):
        env.pop(name, None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["NEXUS_SLOT"] = str(TEST_SLOT)
    env[RUNTIME_CONFIG_ENV] = str(config)
    env.update(_routed_env())
    log_path = external_dir / "gateway.log"
    with open(log_path, "wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                ROUTED_LAUNCHER,
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
    # An OS-assigned port held bound but never listening: connections to it
    # are refused for as long as the socket stays open, so no other process
    # on the host can answer /health there while `up` runs.
    with socket.socket() as dead:
        dead.bind(("127.0.0.1", 0))
        dead_port = dead.getsockname()[1]
        config = _write_config(
            tmp_path,
            profile="external",
            external_gateway_url=f"http://127.0.0.1:{dead_port}",
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
    assert up["runtime"]["database"]["dbname"] == ROUTED_DATABASE

    status = _cli("status", config=config)
    assert status["gateway_url"] == external_gateway
    assert status["runtime"]["profile"] == "local"  # the remote host's profile
    assert status["runtime"]["version"]


def test_mock_port_must_match_test_base_url(tmp_path):
    """Config-load consistency: mock service port vs test provider base_url."""
    doc: Any = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    doc["runtime"]["services"]["mock_openai"]["port"] = 5999
    path = tmp_path / "drift.toml"
    path.write_text(tomlkit.dumps(doc))
    with pytest.raises(Exception, match="does not match"):
        load_settings(path)
