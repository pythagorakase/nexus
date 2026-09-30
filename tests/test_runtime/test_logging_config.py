"""Runtime logging configuration: settings, dictConfig, access filter (#842).

No mocks: access records are built exactly as uvicorn builds them, the
dictConfig is applied by a real ``uvicorn --log-config`` process spawned by the
real supervisor, and import side effects are observed in a fresh interpreter.
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import pytest
import tomlkit
from pydantic import ValidationError

from nexus.api.mock_openai import direct_launch_config
from nexus.config import load_settings
from nexus.config.settings_models import RuntimeLogsSettings
from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from nexus.runtime.logging_config import (
    ACCESS_LOGGER_LEVEL,
    SuccessfulAccessFilter,
    build_logging_config,
)
from tests.settings_helpers import settings_with

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_CONFIG = REPO_ROOT / "nexus.toml"
TEST_SLOT = 5

# The exact message uvicorn's h11/httptools protocols log on uvicorn.access.
UVICORN_ACCESS_MSG = '%s - "%s %s HTTP/%s" %d'

# A dependency-free ASGI app: answers every path with ?status=<code> (default
# 200) and logs one application record per request through a nexus logger.
# A WebSocket connection (only with a WebSocket library installed) is accepted
# and closed.
PROBE_APP = """
import logging
from urllib.parse import parse_qs

logger = logging.getLogger("nexus.probe")


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] == "websocket":
        await receive()
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.close", "code": 1000})
        return
    query = parse_qs(scope["query_string"].decode())
    status = int(query.get("status", ["200"])[0])
    logger.info("probe handled %s", scope["path"])
    logger.debug("probe debug detail")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"ok"})
"""


def _access_record(path: str, status: int) -> logging.LogRecord:
    """Build an access record with uvicorn's exact message and argument shape."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=UVICORN_ACCESS_MSG,
        args=("127.0.0.1:50000", "GET", path, "1.1", status),
        exc_info=None,
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# ---------------------------------------------------------------------------
# SuccessfulAccessFilter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,status,kept",
    (
        ("/health", 200, False),
        ("/health", 204, False),
        ("/health", 399, False),
        ("/health?probe=1", 200, False),
        ("/runtime/status", 200, False),
        ("/health", 400, True),
        ("/health", 404, True),
        ("/health", 500, True),
        ("/health?probe=1", 503, True),
        ("/runtime/status", 502, True),
        ("/api/story", 200, True),
        ("/api/story", 500, True),
        ("/health/deep", 200, True),
        ("/healthz", 200, True),
    ),
)
def test_successful_access_filter_drops_only_excluded_successes(
    path: str, status: int, kept: bool
) -> None:
    """Every 4xx/5xx and every unlisted path survives; excluded 2xx/3xx drop."""
    access_filter = SuccessfulAccessFilter(["/health", "/runtime/status"])

    assert access_filter.filter(_access_record(path, status)) is kept


def test_successful_access_filter_with_no_exclusions_keeps_everything() -> None:
    """An empty exclusion list suppresses nothing."""
    access_filter = SuccessfulAccessFilter([])

    assert access_filter.filter(_access_record("/health", 200)) is True


@pytest.mark.parametrize(
    "args",
    (
        None,
        ("127.0.0.1:50000", "GET", "/health", "1.1"),
        ("127.0.0.1:50000", "GET", b"/health", "1.1", 200),
        ("127.0.0.1:50000", "GET", "/health", "1.1", "200"),
    ),
    ids=("no-args", "short", "bytes-path", "string-status"),
)
def test_successful_access_filter_rejects_unexpected_record_shape(
    args: Any,
) -> None:
    """A changed uvicorn access shape fails loudly instead of filtering blind."""
    record = _access_record("/health", 200)
    record.args = args

    with pytest.raises(TypeError, match="uvicorn.access record"):
        SuccessfulAccessFilter(["/health"]).filter(record)


# ---------------------------------------------------------------------------
# build_logging_config
# ---------------------------------------------------------------------------


def test_build_logging_config_routes_everything_through_one_stdout_handler() -> None:
    """Root and uvicorn loggers share one stdout handler and one formatter."""
    settings = RuntimeLogsSettings(
        level="WARNING",
        format="%(levelname)s|%(name)s|%(message)s",
        access_success_exclude_paths=["/health"],
    )

    config = build_logging_config(settings)

    assert json.loads(json.dumps(config)) == config
    assert config["version"] == 1
    assert config["disable_existing_loggers"] is False
    assert config["formatters"] == {
        "standard": {"format": "%(levelname)s|%(name)s|%(message)s"}
    }
    assert config["handlers"] == {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        }
    }
    assert config["filters"] == {
        "successful_access": {
            "()": "nexus.runtime.logging_config.SuccessfulAccessFilter",
            "exclude_paths": ["/health"],
        }
    }
    assert config["root"] == {"handlers": ["console"], "level": "WARNING"}
    assert config["loggers"] == {
        "uvicorn": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "uvicorn.error": {"level": "WARNING", "propagate": True},
        # uvicorn logs every response at INFO: the access logger stays there
        # so the filter, not the level, decides which access records drop.
        "uvicorn.access": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
            "filters": ["successful_access"],
        },
    }


@pytest.mark.parametrize("level", ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"))
def test_build_logging_config_pins_only_the_access_logger_at_info(
    level: str,
) -> None:
    """Every level gates root and uvicorn; none gates the access route."""
    config = build_logging_config(RuntimeLogsSettings.model_validate({"level": level}))

    assert ACCESS_LOGGER_LEVEL == "INFO"
    assert config["loggers"]["uvicorn.access"]["level"] == "INFO"
    assert config["root"]["level"] == level
    assert config["loggers"]["uvicorn"]["level"] == level
    assert config["loggers"]["uvicorn.error"]["level"] == level
    assert "level" not in config["handlers"]["console"]


def test_repo_config_gateway_uses_the_supervisor_log_config(tmp_path: Path) -> None:
    """The shipped gateway argv hands uvicorn the supervisor-written config."""
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    cast(Any, document["runtime"])["state_dir"] = str(tmp_path / "state")
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(tomlkit.dumps(document), encoding="utf-8")
    supervisor = Supervisor(load_settings(config_path), config_path)

    argv = supervisor._service_argv(supervisor.runtime.services["gateway"])

    assert argv[argv.index("--log-config") + 1] == str(
        tmp_path / "state" / "logging.json"
    )
    assert "{log_config}" in supervisor.runtime.services["gateway"].command


# ---------------------------------------------------------------------------
# Real uvicorn under the real supervisor
# ---------------------------------------------------------------------------


def _probe_supervisor(tmp_path: Path, level: str) -> Supervisor:
    """A supervisor whose 'probe' service is uvicorn with {log_config}."""
    (tmp_path / "probe_app.py").write_text(PROBE_APP, encoding="utf-8")
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    runtime = cast(Any, document["runtime"])
    runtime["state_dir"] = str(tmp_path / "state")
    logs = runtime["logs"]
    logs["level"] = level
    logs["format"] = "%(levelname)s|%(name)s|%(message)s"
    logs["access_success_exclude_paths"] = ["/health", "/runtime/status"]
    probe = tomlkit.table()
    probe["command"] = [
        "{python}",
        "-m",
        "uvicorn",
        "probe_app:app",
        "--app-dir",
        str(tmp_path),
        "--host",
        "{host}",
        "--port",
        "{port}",
        "--log-config",
        "{log_config}",
    ]
    probe["host"] = "127.0.0.1"
    probe["port"] = _free_port()
    probe["health_path"] = "/health"
    probe["enabled"] = "never"
    runtime["services"]["probe"] = probe
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(tomlkit.dumps(document), encoding="utf-8")
    supervisor = Supervisor(load_settings(config_path), config_path)
    supervisor.state_dir.mkdir(parents=True)
    return supervisor


def _get(port: int, target: str) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", target)
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def _websocket_upgrade(port: int, target: str) -> int:
    """Send a real WebSocket upgrade request; return the response status code."""
    request = (
        f"GET {target} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(request.encode("ascii"))
        with sock.makefile("rb") as response:
            status_line = response.readline()
    return int(status_line.split()[1])


def _serve_probe(
    tmp_path: Path,
    level: str,
    requests_made: Dict[str, int],
    websocket_upgrades: Optional[Dict[str, int]] = None,
) -> List[str]:
    """Start the probe under the real supervisor, make requests, return its log.

    Each target in ``requests_made`` (plain GET) and ``websocket_upgrades``
    (WebSocket upgrade) must answer with its mapped status. The service is
    stopped before its captured log (stdout and stderr) is read, and that log
    must hold no logging error: a filter or formatter that raises would print
    ``--- Logging error ---`` there on every record.
    """
    supervisor = _probe_supervisor(tmp_path, level)
    service = supervisor.runtime.services["probe"]

    record = supervisor._start_service("probe", service, TEST_SLOT, detached=True)
    try:
        for target, expected in requests_made.items():
            assert _get(service.port, target) == expected
        for target, expected in (websocket_upgrades or {}).items():
            assert _websocket_upgrade(service.port, target) == expected
    finally:
        # This test process is the service's parent, so it reaps the child
        # itself; a detached CLI supervisor leaves that to init.
        os.kill(int(record["pid"]), signal.SIGTERM)
        os.waitpid(int(record["pid"]), 0)

    written = json.loads(supervisor.log_config_path().read_text())
    assert written == build_logging_config(supervisor.runtime.logs)
    assert record["command"][-1] == str(supervisor.log_config_path())
    lines = supervisor.log_path("probe").read_text(encoding="utf-8").splitlines()
    assert "--- Logging error ---" not in lines
    return lines


def _access_request_lines(lines: List[str]) -> List[str]:
    """The request line of every uvicorn access record in a captured log."""
    return [
        line.split('"')[1] for line in lines if line.startswith("INFO|uvicorn.access|")
    ]


def test_supervised_uvicorn_applies_log_config_and_filters_access_noise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """uvicorn --log-config {log_config}: one format, noise out, failures in."""
    monkeypatch.delenv("NEXUS_GATEWAY_PORT", raising=False)
    lines = _serve_probe(
        tmp_path,
        "INFO",
        {
            "/health": 200,
            "/health?status=503": 503,
            "/runtime/status": 200,
            "/runtime/status?status=500": 500,
            "/api/story": 200,
            "/api/missing?status=404": 404,
        },
    )

    assert _access_request_lines(lines) == [
        "GET /health?status=503 HTTP/1.1",
        "GET /runtime/status?status=500 HTTP/1.1",
        "GET /api/story HTTP/1.1",
        "GET /api/missing?status=404 HTTP/1.1",
    ]
    # The supervisor's own startup health probes were successes on /health.
    assert not any("GET /health HTTP" in line for line in lines)
    # uvicorn's lifecycle lines and the app's records share the one format.
    assert any(
        line.startswith("INFO|uvicorn.error|Uvicorn running on") for line in lines
    )
    assert "INFO|nexus.probe|probe handled /api/story" in lines
    # The configured level applies to application loggers through root.
    assert not any("probe debug detail" in line for line in lines)


def test_supervised_uvicorn_keeps_access_records_above_info_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At WARNING, 4xx/5xx and unexcluded access records still reach the log.

    uvicorn logs every response at INFO. The access logger stays at INFO, so
    only the filter drops access records: excluded successes vanish, while a
    404, a 500 and a 200 on an unexcluded path remain. Root and uvicorn.error
    still honour WARNING, so their INFO records are gone.
    """
    monkeypatch.delenv("NEXUS_GATEWAY_PORT", raising=False)
    lines = _serve_probe(
        tmp_path,
        "WARNING",
        {
            "/health": 200,
            "/api/missing?status=404": 404,
            "/api/story?status=500": 500,
            "/api/story": 200,
        },
    )

    assert _access_request_lines(lines) == [
        "GET /api/missing?status=404 HTTP/1.1",
        "GET /api/story?status=500 HTTP/1.1",
        "GET /api/story HTTP/1.1",
    ]
    assert not any("GET /health HTTP" in line for line in lines)
    assert not any("uvicorn.error|Uvicorn running on" in line for line in lines)
    assert not any("probe handled" in line for line in lines)


def test_supervised_uvicorn_websocket_upgrade_keeps_the_access_log_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real WebSocket upgrade never reaches the access filter malformed.

    uvicorn (pinned < 0.35) logs WebSocket handshakes on uvicorn.error, never
    uvicorn.access. Without a WebSocket library (uvicorn is locked without its
    ``standard`` extra) the upgrade is served as plain HTTP and logged as an
    ordinary access record. Either way the filter never sees another shape.
    """
    monkeypatch.delenv("NEXUS_GATEWAY_PORT", raising=False)
    websocket_library = any(
        importlib.util.find_spec(name) is not None for name in ("websockets", "wsproto")
    )

    lines = _serve_probe(
        tmp_path,
        "INFO",
        {},
        websocket_upgrades={"/ws/probe": 101 if websocket_library else 200},
    )

    if websocket_library:
        assert '"WebSocket /ws/probe" [accepted]' in "\n".join(lines)
        assert _access_request_lines(lines) == []
    else:
        assert "WARNING|uvicorn.error|Unsupported upgrade request." in lines
        assert _access_request_lines(lines) == ["GET /ws/probe HTTP/1.1"]


# ---------------------------------------------------------------------------
# Provider clients configure no logging on import
# ---------------------------------------------------------------------------

IMPORT_PROBE = """
import json
import logging

import scripts.api_anthropic
import scripts.api_openai
import scripts.api_openrouter
import scripts.summarize_narrative

def handler_types(logger):
    return [type(handler).__name__ for handler in logger.handlers]

print(json.dumps({
    "root": handler_types(logging.getLogger()),
    "loggers": {
        name: handler_types(logging.getLogger(name))
        for name in ("nexus.metadata", "nexus.openrouter", "nexus.summarize_narrative")
    },
}))
"""


def test_importing_provider_clients_creates_no_log_file_or_handler(
    tmp_path: Path,
) -> None:
    """Gateway-imported provider modules leave logging to the host process."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    env[RUNTIME_CONFIG_ENV] = str(REPO_CONFIG)

    completed = subprocess.run(
        [sys.executable, "-c", IMPORT_PROBE],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )

    handlers: Dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
    assert handlers == {
        "root": [],
        "loggers": {
            "nexus.metadata": [],
            "nexus.openrouter": [],
            "nexus.summarize_narrative": [],
        },
    }
    created: List[str] = sorted(path.name for path in tmp_path.iterdir())
    assert created == []


# ---------------------------------------------------------------------------
# Direct launch of the mock provider
# ---------------------------------------------------------------------------


def test_mock_openai_direct_launch_uses_the_shared_log_config() -> None:
    """`python -m nexus.api.mock_openai` gets [runtime.logs] and loopback."""
    runtime = load_settings().runtime
    assert runtime is not None

    config = direct_launch_config()

    assert set(config) == {"host", "port", "log_config"}
    assert config["log_config"] == build_logging_config(runtime.logs)
    assert config["host"] == "127.0.0.1"
    assert config["port"] == runtime.services["mock_openai"].port


def test_mock_openai_direct_launch_requires_the_runtime_section() -> None:
    """Without [runtime] the direct launch raises instead of using defaults."""
    # A configured local model reads its serving window from
    # [runtime.services.llama_server], so a config without [runtime] has none.
    settings = settings_with({"runtime": None, "local_models.model": None})
    assert settings.runtime is None

    with pytest.raises(RuntimeError, match=re.escape("[runtime]")):
        direct_launch_config(settings)


def test_mock_openai_direct_launch_requires_the_mock_service_entry() -> None:
    """Without [runtime.services.mock_openai] there is no port to bind."""
    runtime = load_settings().runtime
    assert runtime is not None
    services = {
        name: service.model_dump()
        for name, service in runtime.services.items()
        if name != "mock_openai"
    }
    settings = settings_with({"runtime.services": services})

    with pytest.raises(RuntimeError, match=re.escape("[runtime.services.mock_openai]")):
        direct_launch_config(settings)


MOCK_IMPORT_PROBE = """
import json
import logging
import os
import stat


def socket_fds():
    fds = set()
    for name in os.listdir("/dev/fd"):
        try:
            if stat.S_ISSOCK(os.fstat(int(name)).st_mode):
                fds.add(int(name))
        except OSError:
            pass
    return fds


before = socket_fds()

import nexus.api.mock_openai

print(json.dumps({
    "new_sockets": sorted(socket_fds() - before),
    "root": [type(handler).__name__ for handler in logging.getLogger().handlers],
    "loggers": {
        name: [type(handler).__name__ for handler in logging.getLogger(name).handlers]
        for name in ("nexus.api.mock_openai", "uvicorn", "uvicorn.access")
    },
}))
"""


def test_importing_mock_openai_binds_no_port_and_configures_no_logging(
    tmp_path: Path,
) -> None:
    """Only the __main__ block launches; importing the module has no effects."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    env[RUNTIME_CONFIG_ENV] = str(REPO_CONFIG)

    completed = subprocess.run(
        [sys.executable, "-c", MOCK_IMPORT_PROBE],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )

    observed: Dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
    assert observed == {
        "new_sockets": [],
        "root": [],
        "loggers": {
            "nexus.api.mock_openai": [],
            "uvicorn": [],
            "uvicorn.access": [],
        },
    }


MOCK_MAIN_PROBE = """
import json
import os
import runpy
import stat
import sys

import uvicorn

CALL = "UVICORN_RUN_CALL "
EXIT = "RUN_MODULE_EXIT "


def socket_fds():
    fds = set()
    for name in os.listdir("/dev/fd"):
        try:
            if stat.S_ISSOCK(os.fstat(int(name)).st_mode):
                fds.add(int(name))
        except OSError:
            pass
    return fds


def record_run(app, *args, **kwargs):
    module = sys._getframe(1).f_globals
    spec = module.get("__spec__")
    print(CALL + json.dumps({
        "caller": module.get("__name__"),
        "module": spec.name if spec is not None else None,
        "app_is_module_app": app is module.get("app"),
        "app_type": type(app).__module__ + "." + type(app).__qualname__,
        "args": list(args),
        "kwargs": kwargs,
    }), flush=True)
    raise SystemExit("uvicorn.run recorded")


uvicorn.run = record_run
before = socket_fds()
try:
    runpy.run_module("nexus.api.mock_openai", run_name="__main__")
except SystemExit as exc:
    print(EXIT + json.dumps(str(exc)))
print(EXIT + "sockets " + json.dumps(sorted(socket_fds() - before)))
"""


def test_mock_openai_main_block_launches_with_direct_launch_config(
    tmp_path: Path,
) -> None:
    """`python -m nexus.api.mock_openai` hands uvicorn.run the helper's kwargs."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    env[RUNTIME_CONFIG_ENV] = str(REPO_CONFIG)
    # NEXUS_HOME outranks NEXUS_RUNTIME_CONFIG; the child must read REPO_CONFIG.
    env.pop("NEXUS_HOME", None)

    completed = subprocess.run(
        [sys.executable, "-c", MOCK_MAIN_PROBE],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )

    lines = completed.stdout.strip().splitlines()
    calls: List[Dict[str, Any]] = [
        json.loads(line[len("UVICORN_RUN_CALL ") :])
        for line in lines
        if line.startswith("UVICORN_RUN_CALL ")
    ]
    exits = [line for line in lines if line.startswith("RUN_MODULE_EXIT ")]
    assert len(calls) == 1, completed.stdout
    assert exits == [
        'RUN_MODULE_EXIT "uvicorn.run recorded"',
        "RUN_MODULE_EXIT sockets []",
    ]
    call = calls[0]
    assert call["caller"] == "__main__"
    assert call["module"] == "nexus.api.mock_openai"
    assert call["app_is_module_app"] is True
    assert call["app_type"] == "fastapi.applications.FastAPI"
    assert call["args"] == []
    expected = direct_launch_config(load_settings(REPO_CONFIG))
    assert call["kwargs"] == json.loads(json.dumps(expected))


# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------


def test_repo_runtime_logs_settings_load() -> None:
    """The shipped [runtime.logs] validates and keeps failures visible."""
    settings = load_settings(REPO_CONFIG)
    assert settings.runtime is not None
    logs = settings.runtime.logs

    assert logs.level == "INFO"
    assert logs.max_bytes > 0
    assert logs.backup_count >= 1
    assert logs.access_success_exclude_paths == ["/health", "/runtime/status"]
    assert RuntimeLogsSettings(format=logs.format).format == logs.format
    formatter = logging.Formatter(logs.format)
    application = logging.LogRecord(
        "nexus.probe", logging.WARNING, __file__, 1, "saved %s", ("slot",), None
    )
    assert formatter.format(application).endswith(
        " - nexus.probe - WARNING - saved slot"
    )
    assert formatter.format(_access_record("/api/story", 500)).endswith(
        ' - uvicorn.access - INFO - 127.0.0.1:50000 - "GET /api/story HTTP/1.1" 500'
    )


@pytest.mark.parametrize(
    "overrides,message",
    (
        ({"level": "VERBOSE"}, "level"),
        ({"level": "info"}, "level"),
        ({"format": ""}, "format"),
        ({"format": "no fields at all"}, "not a valid %-style logging format"),
        ({"format": "%(asctime"}, "not a valid %-style logging format"),
        ({"max_bytes": 0}, "max_bytes"),
        ({"max_bytes": -1}, "max_bytes"),
        ({"backup_count": 0}, "backup_count"),
        ({"access_success_exclude_paths": ["health"]}, "starting with '/'"),
        ({"access_success_exclude_paths": ["/health?x=1"]}, "query string"),
        ({"access_success_exclude_paths": ["/health#top"]}, "query string"),
        (
            {"access_success_exclude_paths": ["/health", "/health"]},
            "duplicate entries",
        ),
        ({"path": "/var/log/nexus.log"}, "Extra inputs are not permitted"),
    ),
)
def test_runtime_logs_settings_reject_invalid_values(
    overrides: Dict[str, Any], message: str
) -> None:
    """Invalid [runtime.logs] values fail at config load with a clear message."""
    with pytest.raises(ValidationError, match=message):
        RuntimeLogsSettings(**overrides)


# Formats that parse under Formatter(validate=True) but raise on every record.
UNRENDERABLE_FORMATS = (
    ("%(message)d", "TypeError", "'%(message)d'"),
    ("%(asctime)s %(does_not_exist)s", "ValueError", "'%(does_not_exist)s'"),
)


@pytest.mark.parametrize(
    "fmt,error,placeholder", UNRENDERABLE_FORMATS, ids=("message-d", "unknown-field")
)
def test_runtime_logs_format_must_render_a_record(
    fmt: str, error: str, placeholder: str
) -> None:
    """A format that parses but cannot render a record is rejected by name."""
    logging.Formatter(fmt, validate=True)

    with pytest.raises(ValidationError) as caught:
        RuntimeLogsSettings(format=fmt)

    message = str(caught.value)
    assert "[runtime.logs] format" in message
    assert f"cannot render a nexus.runtime log record ({error}:" in message
    assert f"failing placeholder: {placeholder}" in message


def test_runtime_logs_format_rejects_a_stray_percent_sign() -> None:
    """A lone '%' outside the placeholders parses but cannot render."""
    with pytest.raises(ValidationError, match=re.escape("write a literal percent")):
        RuntimeLogsSettings(format="%(message)s at 100%")


@pytest.mark.parametrize(
    "key,value,message",
    (
        ("backup_count", 0, "backup_count"),
        ("format", "%(message)d", re.escape("failing placeholder: '%(message)d'")),
        (
            "format",
            "%(does_not_exist)s",
            re.escape("failing placeholder: '%(does_not_exist)s'"),
        ),
    ),
    ids=("backup-count", "format-message-d", "format-unknown-field"),
)
def test_invalid_runtime_logs_in_nexus_toml_fails_load(
    tmp_path: Path, key: str, value: Any, message: str
) -> None:
    """A bad [runtime.logs] entry in nexus.toml aborts load_settings."""
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    cast(Any, document["runtime"])["logs"][key] = value
    config_path = tmp_path / "nexus.toml"
    config_path.write_text(tomlkit.dumps(document), encoding="utf-8")

    with pytest.raises(ValidationError, match=message):
        load_settings(config_path)
