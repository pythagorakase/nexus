"""Runtime logging configuration: settings, dictConfig, access filter (#842).

No mocks: access records are built exactly as uvicorn builds them, the
dictConfig is applied by a real ``uvicorn --log-config`` process spawned by the
real supervisor, and import side effects are observed in a fresh interpreter.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, cast

import pytest
import tomlkit
from pydantic import ValidationError

from nexus.config import load_settings
from nexus.config.settings_models import RuntimeLogsSettings
from nexus.runtime import RUNTIME_CONFIG_ENV, Supervisor
from nexus.runtime.logging_config import (
    SuccessfulAccessFilter,
    build_logging_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_CONFIG = REPO_ROOT / "nexus.toml"
TEST_SLOT = 5

# The exact message uvicorn's h11/httptools protocols log on uvicorn.access.
UVICORN_ACCESS_MSG = '%s - "%s %s HTTP/%s" %d'

# A dependency-free ASGI app: answers every path with ?status=<code> (default
# 200) and logs one application record per request through a nexus logger.
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
        "uvicorn.access": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
            "filters": ["successful_access"],
        },
    }


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


def _probe_supervisor(tmp_path: Path) -> Supervisor:
    """A supervisor whose 'probe' service is uvicorn with {log_config}."""
    (tmp_path / "probe_app.py").write_text(PROBE_APP, encoding="utf-8")
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    runtime = cast(Any, document["runtime"])
    runtime["state_dir"] = str(tmp_path / "state")
    logs = runtime["logs"]
    logs["level"] = "INFO"
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


def test_supervised_uvicorn_applies_log_config_and_filters_access_noise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """uvicorn --log-config {log_config}: one format, noise out, failures in."""
    monkeypatch.delenv("NEXUS_GATEWAY_PORT", raising=False)
    supervisor = _probe_supervisor(tmp_path)
    service = supervisor.runtime.services["probe"]

    record = supervisor._start_service("probe", service, TEST_SLOT, detached=True)
    try:
        requests_made = {
            "/health": 200,
            "/health?status=503": 503,
            "/runtime/status": 200,
            "/runtime/status?status=500": 500,
            "/api/story": 200,
            "/api/missing?status=404": 404,
        }
        for target, expected in requests_made.items():
            assert _get(service.port, target) == expected
    finally:
        supervisor._stop_service("probe")

    written = json.loads(supervisor.log_config_path().read_text())
    assert written == build_logging_config(supervisor.runtime.logs)
    assert record["command"][-1] == str(supervisor.log_config_path())

    lines = supervisor.log_path("probe").read_text(encoding="utf-8").splitlines()
    access = [line for line in lines if line.startswith("INFO|uvicorn.access|")]
    assert [line.split('"')[1] for line in access] == [
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
    logging.Formatter(logs.format, validate=True)


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


def test_invalid_runtime_logs_in_nexus_toml_fails_load(tmp_path: Path) -> None:
    """A bad [runtime.logs] entry in nexus.toml aborts load_settings."""
    document = tomlkit.parse(REPO_CONFIG.read_text(encoding="utf-8"))
    cast(Any, document["runtime"])["logs"]["backup_count"] = 0
    config_path = tmp_path / "nexus.toml"
    config_path.write_text(tomlkit.dumps(document), encoding="utf-8")

    with pytest.raises(ValidationError, match="backup_count"):
        load_settings(config_path)
