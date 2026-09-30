"""The routed child-process entry points never reach an owner slot (issue #885).

``tests.slot_routed_cli``, ``tests.slot_routed_uvicorn`` and
``tests.slot_routed_gateway`` route one slot to a disposable clone before the
CLI or gateway loads. The offline tests prove that each refuses to run, before
anything else happens, when a routing variable is missing or names an owner
database. The PostgreSQL tests prove, on a seeded template clone, that a routed
CLI ``up``/``status``/``down`` opens no database but the clone (and the
``postgres`` admin database), and that the routed launcher, spawned from the
supervisor's own argv and environment, serves the clone on the port it was
given and refuses any other slot.
"""

from __future__ import annotations

import json
import os
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

from nexus.api import slot_utils
from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from nexus.runtime.supervisor import _port_open
from tests.pg_fixtures import (
    ROUTED_SLOT_DATABASE_ENV,
    ROUTED_SLOT_ENV,
    connect,
    disposable_slot_database,
    route_slot_from_environment,
    routed_slot_environment,
    seed_protagonist,
    seed_story_clock,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTED_SLOT = 5
OWNER_DATABASES = (
    "NEXUS_template",
    *(slot_utils.slot_dbname(slot) for slot in slot_utils.all_slots()),
)
ENTRY_POINTS = (
    "tests.slot_routed_cli",
    "tests.slot_routed_uvicorn",
    "tests.slot_routed_gateway",
)
# Runs a routed CLI with every libpq connection's database name appended to
# SPY_LOG, one JSON line each, and a final line saying whether asyncpg (which
# bypasses libpq) was ever loaded. The connections themselves are real.
CONNECTION_SPY = """
import atexit, json, os, sys
import psycopg2, psycopg2.extensions

log = open(os.environ["SPY_LOG"], "a", encoding="utf-8")
real_connect = psycopg2._connect

def recording_connect(dsn, *args, **kwargs):
    dbname = psycopg2.extensions.parse_dsn(dsn).get("dbname")
    log.write(json.dumps({"dbname": dbname}) + "\\n")
    log.flush()
    return real_connect(dsn, *args, **kwargs)

psycopg2._connect = recording_connect
atexit.register(
    lambda: (log.write(json.dumps({"asyncpg": "asyncpg" in sys.modules}) + "\\n"),
             log.flush())
)
from tests.slot_routed_cli import main
main()
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _child_env(extra: dict[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    for name in (
        "NEXUS_API_URL",
        "NEXUS_GATEWAY_PORT",
        "NEXUS_SLOT",
        RUNTIME_CONFIG_ENV,
        ROUTED_SLOT_ENV,
        ROUTED_SLOT_DATABASE_ENV,
    ):
        env.pop(name, None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.update(extra)
    return env


def _write_config(tmp_path: Path, *, routed_database: str | None) -> Path:
    """A temporary nexus.toml whose gateway runs the routed launcher.

    Every port is OS-assigned and the state directory is ``tmp_path``, so no
    owner runtime state or port is touched. ``routed_database=None`` leaves
    the routing variables out of the gateway environment.
    """
    gateway_port, mock_port = _free_port(), _free_port()
    doc: Any = tomlkit.parse((REPO_ROOT / "nexus.toml").read_text())
    runtime = doc["runtime"]
    runtime["state_dir"] = str(tmp_path / "state")
    runtime["default_slot"] = ROUTED_SLOT
    gateway = runtime["services"]["gateway"]
    command = [str(part) for part in gateway["command"]]
    assert command[1:3] == ["-m", "uvicorn"], command
    command[2] = "tests.slot_routed_uvicorn"
    gateway["command"] = command
    gateway["port"] = gateway_port
    if routed_database is not None:
        gateway["env"] = routed_slot_environment(ROUTED_SLOT, routed_database)
    runtime["services"]["mock_openai"]["port"] = mock_port
    doc["global"]["model"]["api_models"]["test"][
        "base_url"
    ] = f"http://127.0.0.1:{mock_port}/v1"
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "nexus.toml"
    path.write_text(tomlkit.dumps(doc))
    return path


# ---------------------------------------------------------------------------
# Offline: refusals happen before anything runs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("environ", "message"),
    [
        ({}, f"needs {ROUTED_SLOT_ENV} and {ROUTED_SLOT_DATABASE_ENV}"),
        ({ROUTED_SLOT_ENV: "5"}, f"needs {ROUTED_SLOT_DATABASE_ENV}:"),
        ({ROUTED_SLOT_DATABASE_ENV: "qa885_x"}, f"needs {ROUTED_SLOT_ENV}:"),
        (
            {ROUTED_SLOT_ENV: "five", ROUTED_SLOT_DATABASE_ENV: "qa885_x"},
            "must be a slot number",
        ),
        (
            {ROUTED_SLOT_ENV: "9", ROUTED_SLOT_DATABASE_ENV: "qa885_x"},
            "is not a slot",
        ),
    ],
)
def test_route_from_environment_requires_both_variables(
    environ: dict[str, str], message: str
) -> None:
    """A missing or malformed variable raises and routes nothing."""
    resolver = slot_utils.slot_dbname
    with pytest.raises(RuntimeError, match=message):
        route_slot_from_environment(environ)
    assert slot_utils.slot_dbname is resolver


@pytest.mark.parametrize("owner", OWNER_DATABASES)
def test_route_from_environment_refuses_owner_databases(owner: str) -> None:
    """Every owner database is refused before the resolver is touched."""
    resolver = slot_utils.slot_dbname
    valid = slot_utils.VALID_DBNAMES
    environ = {ROUTED_SLOT_ENV: "5", ROUTED_SLOT_DATABASE_ENV: owner}
    refusal = f"{ROUTED_SLOT_DATABASE_ENV}={owner!r} names an owner database"
    with pytest.raises(RuntimeError, match=refusal):
        route_slot_from_environment(environ)
    assert slot_utils.slot_dbname is resolver
    assert slot_utils.VALID_DBNAMES is valid
    with pytest.raises(RuntimeError, match=refusal):
        routed_slot_environment(ROUTED_SLOT, owner)


@pytest.mark.parametrize("module", ENTRY_POINTS)
@pytest.mark.parametrize(
    ("routing", "message"),
    [
        (
            {ROUTED_SLOT_ENV: "5"},
            f"needs {ROUTED_SLOT_DATABASE_ENV}:",
        ),
        (
            {ROUTED_SLOT_ENV: "5", ROUTED_SLOT_DATABASE_ENV: "save_05"},
            f"{ROUTED_SLOT_DATABASE_ENV}='save_05' names an owner database",
        ),
    ],
)
def test_entry_point_refuses_before_anything_runs(
    tmp_path: Path, module: str, routing: dict[str, str], message: str
) -> None:
    """Each entry point exits loudly and starts nothing when unrouted.

    The CLI is asked to ``up`` a stack and each gateway to bind a port; a
    refusal leaves no state directory, no output, and no listener.
    """
    config = _write_config(tmp_path, routed_database=None)
    port = _free_port()
    argv = {
        "tests.slot_routed_cli": ["--json", "up", "--config", str(config)],
        "tests.slot_routed_uvicorn": [
            "nexus.api.narrative:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        "tests.slot_routed_gateway": [],
    }[module]
    env = _child_env(
        {
            **routing,
            "NEXUS_SLOT": str(ROUTED_SLOT),
            RUNTIME_CONFIG_ENV: str(config),
            "NARRATIVE_API_PORT": str(port),
        }
    )
    completed = subprocess.run(
        [sys.executable, "-m", module, *argv],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=120,
    )
    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "Traceback" in completed.stderr
    assert message in completed.stderr
    assert "Uvicorn running" not in completed.stderr
    assert not (tmp_path / "state").exists()
    assert not _port_open("127.0.0.1", port)


# ---------------------------------------------------------------------------
# PostgreSQL: the routed CLI and launcher reach only the clone
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def entrypoint_clone() -> Iterator[str]:
    """A seeded disposable template clone serving the routed slot."""
    with disposable_slot_database("qa885_entrypoints") as dbname:
        seed_protagonist(dbname)
        seed_story_clock(
            dbname, world_time=datetime(2100, 1, 1, 1, tzinfo=timezone.utc)
        )
        yield dbname


def _spy_cli(*args: str, clone: str, spy_log: Path) -> dict:
    env = _child_env({**routed_slot_environment(ROUTED_SLOT, clone)})
    env["SPY_LOG"] = str(spy_log)
    completed = subprocess.run(
        [sys.executable, "-c", CONNECTION_SPY, "--json", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=180,
    )
    # The routed CLI logs as the production CLI does: the fixture module's
    # import-time logging.basicConfig must not add INFO records to stderr,
    # where the CLI prints its JSON errors.
    assert "Created connection pool" not in completed.stderr, completed.stderr
    payload = json.loads(completed.stdout or completed.stderr)
    payload["_returncode"] = completed.returncode
    return payload


def _spied(spy_log: Path) -> tuple[list[str | None], bool]:
    records = [json.loads(line) for line in spy_log.read_text().splitlines()]
    assert records and "asyncpg" in records[-1], records
    return [r["dbname"] for r in records if "dbname" in r], records[-1]["asyncpg"]


@pytest.mark.requires_postgres
def test_routed_cli_up_status_down_never_open_an_owner_slot(
    tmp_path: Path, entrypoint_clone: str
) -> None:
    """Every connection the CLI process opens goes to the clone or the admin DB.

    ``up`` is the positive control: the supervisor's own
    ``recover_active_slot_choice`` must open the clone. ``status`` and
    ``down`` report on and stop the routed stack.
    """
    config = _write_config(tmp_path, routed_database=entrypoint_clone)
    logs = {verb: tmp_path / f"{verb}.jsonl" for verb in ("up", "status", "down")}
    try:
        up = _spy_cli(
            "up",
            "--slot",
            str(ROUTED_SLOT),
            "--config",
            str(config),
            clone=entrypoint_clone,
            spy_log=logs["up"],
        )
        assert up["_returncode"] == 0, up
        status = _spy_cli(
            "status",
            "--config",
            str(config),
            clone=entrypoint_clone,
            spy_log=logs["status"],
        )
        assert status["_returncode"] == 0, status
        assert status["processes"]["gateway"]["state"] == "running"
        assert status["runtime"]["slot"] == ROUTED_SLOT
        assert status["runtime"]["database"]["dbname"] == entrypoint_clone
    finally:
        down = _spy_cli(
            "down",
            "--config",
            str(config),
            clone=entrypoint_clone,
            spy_log=logs["down"],
        )
    assert down["_returncode"] == 0, down
    assert set(down["stopped"]) == {"gateway", "mock_openai"}

    opened: dict[str, list[str | None]] = {}
    for verb, log in logs.items():
        opened[verb], used_asyncpg = _spied(log)
        assert used_asyncpg is False, verb
        assert set(opened[verb]) <= {entrypoint_clone, "postgres"}, (verb, opened)
        assert not set(opened[verb]) & set(OWNER_DATABASES), (verb, opened)
    assert entrypoint_clone in opened["up"], opened


def _spawn_routed_gateway(
    tmp_path: Path, clone: str, *, slot: int
) -> tuple[subprocess.Popen, Supervisor, Path]:
    """Spawn the routed launcher from the supervisor's own argv and env."""
    supervisor = Supervisor.from_config(_write_config(tmp_path, routed_database=clone))
    service = supervisor.runtime.services["gateway"]
    supervisor.state_dir.mkdir(parents=True, exist_ok=True)
    supervisor._write_log_config()
    argv = supervisor._service_argv(service)
    assert argv[1:4] == ["-m", "tests.slot_routed_uvicorn", "nexus.api.narrative:app"]
    assert argv[-2:] == ["--log-config", str(supervisor.log_config_path())]
    env = supervisor._service_env(service, slot)
    for name in ("NEXUS_API_URL", "NEXUS_GATEWAY_PORT"):
        env.pop(name, None)
    log_path = tmp_path / "gateway.log"
    with open(log_path, "wb") as log:
        process = subprocess.Popen(
            argv,
            cwd=supervisor.root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    return process, supervisor, log_path


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=30)


@pytest.mark.requires_postgres
def test_routed_launcher_serves_the_clone_on_its_port(
    tmp_path: Path, entrypoint_clone: str
) -> None:
    """The supervisor's argv under the launcher serves the clone, not an owner."""
    process, supervisor, log_path = _spawn_routed_gateway(
        tmp_path, entrypoint_clone, slot=ROUTED_SLOT
    )
    port = supervisor.runtime.services["gateway"].port
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 60
        while True:
            assert process.poll() is None, log_path.read_text()
            try:
                if requests.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                pass
            assert time.monotonic() < deadline, log_path.read_text()
            time.sleep(0.25)
        status = requests.get(f"{base}/runtime/status", timeout=10).json()
        assert status["slot"] == ROUTED_SLOT
        assert status["database"]["ok"] is True
        assert status["database"]["dbname"] == entrypoint_clone
        assert status["services"]["gateway"]["port"] == port
        # The gateway's scheduler took its lease in the clone.
        with closing(connect(entrypoint_clone)) as conn, conn.cursor() as cur:
            cur.execute("SELECT owner_id FROM deferred_work_scheduler WHERE id")
            row = cur.fetchone()
        assert row is not None
        assert row[0].startswith(f"gateway:{process.pid}:")
    finally:
        _stop(process)
    assert f"Uvicorn running on http://127.0.0.1:{port}" in log_path.read_text()


@pytest.mark.requires_postgres
def test_routed_launcher_refuses_an_unrouted_active_slot(
    tmp_path: Path, entrypoint_clone: str
) -> None:
    """A gateway whose NEXUS_SLOT is not the routed slot fails at startup."""
    other_slot = next(slot for slot in slot_utils.all_slots() if slot != ROUTED_SLOT)
    process, supervisor, log_path = _spawn_routed_gateway(
        tmp_path, entrypoint_clone, slot=other_slot
    )
    try:
        returncode = process.wait(timeout=60)
    finally:
        _stop(process)
    output = log_path.read_text()
    assert returncode != 0, output
    assert f"Slot {other_slot} is not routed" in output
    assert not _port_open("127.0.0.1", supervisor.runtime.services["gateway"].port)
