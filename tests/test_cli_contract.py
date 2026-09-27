"""Qualify the CLI command contract (issue #815) through the real entry point.

The inventory tests walk the real parser. The command tests run
``python -m nexus.cli`` in a subprocess against a loopback HTTP gateway, and,
for refused commands, against a loopback TCP listener standing in for
PostgreSQL that records every connection it accepts. No slot database or
provider is used.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Event, Thread
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

import pytest
import tomlkit

from nexus import cli
from nexus.cli_contract import (
    COMMAND_TRANSPORTS,
    ENVELOPE_COMMANDS,
    ERROR_CODES,
    FLAG_TRANSPORTS,
    REMOTE_PROFILE_TRANSPORTS,
    RUNTIME_CONFIG_COMMANDS,
    ExitCode,
    detect_remote_runtime,
    error_envelope,
    is_loopback_url,
    iter_command_paths,
    partial_fields,
)
from nexus.config import load_settings

ROOT = Path(__file__).resolve().parents[1]
SLOT_STATE = {
    "slot": 5,
    "is_empty": False,
    "is_wizard_mode": False,
    "current_chunk_id": 41,
    "has_pending": False,
    "storyteller_text": "Rain needles the orchard glass.",
    "choices": ["Enter the gate.", "Wait for dawn."],
    "model": "slot-pinned-model",
    "recovery": None,
}
# Environment the CLI must not inherit from the developer's shell.
_ISOLATED_ENV = (
    "NEXUS_API_URL",
    "NEXUS_AUTH",
    "NEXUS_HOME",
    "NEXUS_RUNTIME_CONFIG",
    "NEXUS_GATEWAY_PORT",
    "CLOUDFLARE_ACCESS_CLIENT_ID_API_KEY",
    "CLOUDFLARE_ACCESS_CLIENT_SECRET_API_KEY",
    "PGHOST",
    "PGPORT",
    "PGHOSTADDR",
)


@dataclass
class Gateway:
    """Routes a loopback gateway answers, and every request it received."""

    routes: dict[tuple[str, str], tuple[int, Any]] = field(default_factory=dict)
    requests: list[tuple[str, str, Any]] = field(default_factory=list)


@contextmanager
def _serve(gateway: Gateway) -> Iterator[str]:
    """Serve ``gateway`` on loopback; unknown routes answer 404 like FastAPI."""

    class Handler(BaseHTTPRequestHandler):
        def _answer(self, method: str) -> None:
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            gateway.requests.append((method, path, json.loads(raw) if raw else None))
            status, payload = gateway.routes.get(
                (method, path), (404, {"detail": "Not Found"})
            )
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            self._answer("GET")

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            self._answer("POST")

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def _postgres_sentinel() -> Iterator[tuple[int, list[Any]]]:
    """Listen where PostgreSQL would be and record every accepted connection."""
    accepted: list[Any] = []
    stopped = Event()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.05)

    def accept() -> None:
        while not stopped.is_set():
            try:
                connection, address = listener.accept()
            except socket.timeout:
                continue
            accepted.append(address)
            connection.close()

    thread = Thread(target=accept, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], accepted
    finally:
        stopped.set()
        thread.join(timeout=5)
        listener.close()


def _closed_port() -> int:
    """Return a loopback port nothing listens on."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _config(tmp_path: Path, *, profile: str, base_url: Optional[str] = None) -> Path:
    """Write a copy of the checkout config with the given runtime profile."""
    document: Any = tomlkit.parse((ROOT / "nexus.toml").read_text(encoding="utf-8"))
    document["runtime"]["profile"] = profile
    if base_url is not None:
        remote = document["runtime"]["remote"]
        remote["base_url"] = base_url
        # Access credentials are only ever sent to an HTTPS origin.
        del remote["cloudflare_access"]
    path = tmp_path / f"{profile}.toml"
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _run(*argv: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the real CLI entry point with an isolated environment."""
    base = {key: value for key, value in os.environ.items() if key not in _ISOLATED_ENV}
    return subprocess.run(
        [sys.executable, "-m", "nexus.cli", *argv],
        cwd=ROOT,
        env={
            **base,
            "NEXUS_KEYRING_DISABLE": "1",
            "PYTHONPATH": str(ROOT),
            **env,
        },
        capture_output=True,
        text=True,
        timeout=120,
    )


def _failure(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """Parse the one JSON failure envelope a failed --json command printed."""
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr, completed.stderr
    envelope = json.loads(completed.stderr)
    assert set(envelope) == {"ok", "code", "error", "partial"}
    assert envelope["ok"] is False
    assert ERROR_CODES[envelope["code"]] == completed.returncode
    return dict(envelope)


# ---------------------------------------------------------------------------
# The transport inventory
# ---------------------------------------------------------------------------


def test_every_registered_command_declares_its_transport() -> None:
    """A command added to or removed from the parser must update the registry."""
    registered = set(iter_command_paths(cli.build_parser()))
    declared = set(COMMAND_TRANSPORTS)

    assert not registered - declared, (
        "Commands without a declared transport in nexus/cli_contract.py: "
        f"{sorted(registered - declared)}"
    )
    assert not declared - registered, (
        "COMMAND_TRANSPORTS names commands the parser no longer registers: "
        f"{sorted(declared - registered)}"
    )
    # Nested families are keyed by their full path, never by the group name.
    assert {"models lock", "models verify", "inspect slot"} <= registered
    assert "models" not in declared and "inspect" not in declared


def _leaf_parsers() -> dict[str, Any]:
    """Map each registered command path to its argparse parser."""
    parser = cli.build_parser()
    leaves: dict[str, Any] = {}
    for path in iter_command_paths(parser):
        node = parser
        for name in path.split(" "):
            node = next(
                action.choices[name]
                for action in node._actions
                if isinstance(action.choices, dict) and name in action.choices
            )
        leaves[path] = node
    return leaves


def test_contract_side_tables_name_real_commands_and_flags() -> None:
    """Flag, profile, config, and envelope tables cannot drift from the parser."""
    leaves = _leaf_parsers()

    for command, flags in FLAG_TRANSPORTS.items():
        destinations = {action.dest for action in leaves[command]._actions}
        for flag, _transport in flags:
            assert flag in destinations, f"{command} has no {flag} argument"
    assert set(REMOTE_PROFILE_TRANSPORTS) <= set(COMMAND_TRANSPORTS)
    assert set(ENVELOPE_COMMANDS) <= set(COMMAND_TRANSPORTS)
    for command in RUNTIME_CONFIG_COMMANDS:
        assert "--config" in leaves[command]._option_string_actions, command


# ---------------------------------------------------------------------------
# nexus inspect slot
# ---------------------------------------------------------------------------


def test_inspect_slot_prints_the_slot_state_envelope() -> None:
    """A read returns the gateway's slot state unchanged inside the envelope."""
    gateway = Gateway(routes={("GET", "/api/slot/5/state"): (200, SLOT_STATE)})
    with _serve(gateway) as base_url:
        as_json = _run(
            "inspect",
            "slot",
            "--slot",
            "5",
            "--json",
            env={
                "NEXUS_API_URL": base_url,
            },
        )
        human = _run(
            "inspect",
            "slot",
            "--slot",
            "5",
            env={
                "NEXUS_API_URL": base_url,
            },
        )

    assert as_json.returncode == ExitCode.OK, as_json.stderr
    assert as_json.stderr == ""
    assert json.loads(as_json.stdout) == {"ok": True, "data": SLOT_STATE}
    assert human.returncode == ExitCode.OK, human.stderr
    assert "current_chunk_id: 41" in human.stdout
    assert "Rain needles the orchard glass." in human.stdout
    assert [request[:2] for request in gateway.requests] == [
        ("GET", "/api/slot/5/state"),
        ("GET", "/api/slot/5/state"),
    ]


def test_inspect_slot_missing_route_is_a_domain_failure() -> None:
    """A 404 exits 1 with not_found and keeps the slot and status code."""
    gateway = Gateway()
    with _serve(gateway) as base_url:
        completed = _run(
            "inspect",
            "slot",
            "--slot",
            "5",
            "--json",
            env={"NEXUS_API_URL": base_url},
        )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "not_found"
    assert envelope["partial"] == {"slot": 5, "status_code": 404}
    assert "/api/slot/5/state returned 404" in envelope["error"]


def test_inspect_slot_unreachable_api_exits_four() -> None:
    """Nothing listening at the API URL is reported as api_unreachable."""
    base_url = f"http://127.0.0.1:{_closed_port()}"
    completed = _run(
        "inspect", "slot", "--slot", "5", "--json", env={"NEXUS_API_URL": base_url}
    )

    assert completed.returncode == ExitCode.UNREACHABLE
    envelope = _failure(completed)
    assert envelope["code"] == "api_unreachable"
    assert envelope["error"].startswith(f"Cannot connect to API server at {base_url}")


def test_inspect_slot_rejects_an_invalid_slot_before_any_request() -> None:
    """An out-of-range slot is a usage error (exit 2) and sends nothing."""
    gateway = Gateway(routes={("GET", "/api/slot/9/state"): (200, SLOT_STATE)})
    with _serve(gateway) as base_url:
        completed = _run(
            "inspect",
            "slot",
            "--slot",
            "9",
            "--json",
            env={"NEXUS_API_URL": base_url},
        )

    assert completed.returncode == ExitCode.USAGE
    assert _failure(completed) == {
        "ok": False,
        "code": "usage_error",
        "error": "Slot must be between 1 and 5",
        "partial": {},
    }
    assert gateway.requests == []


@pytest.mark.parametrize(
    "argv",
    [("inspect", "slot", "--slot", "5"), ("load", "--slot", "5")],
    ids=["inspect-slot", "load"],
)
def test_http_command_with_a_missing_runtime_config_is_a_config_error(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    """HTTP commands resolve the active config before dispatch, like the rest."""
    absent = tmp_path / "absent.toml"
    completed = _run(*argv, "--json", env={"NEXUS_RUNTIME_CONFIG": str(absent)})

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "config_error"
    assert envelope["error"].startswith(f"Configuration file not found: {absent}")
    assert "NEXUS_RUNTIME_CONFIG" in envelope["error"]


@pytest.mark.parametrize(
    ("api_url", "message"),
    [
        ("localhost:8002", "NEXUS_API_URL has no host: 'localhost:8002'"),
        ("ftp://127.0.0.1:8002", "No connection adapters were found"),
    ],
    ids=["no-scheme", "not-http"],
)
def test_inspect_slot_malformed_api_url_is_a_config_error(
    api_url: str, message: str
) -> None:
    """An API URL requests cannot use is a config error, not a traceback."""
    completed = _run(
        "inspect", "slot", "--slot", "5", "--json", env={"NEXUS_API_URL": api_url}
    )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "config_error"
    assert envelope["error"].startswith(message)


def test_inspect_slot_missing_access_secret_is_a_config_error(
    tmp_path: Path,
) -> None:
    """A remote profile whose Access secret is absent fails before any request."""
    config = _config(tmp_path, profile="remote")
    completed = _run(
        "inspect",
        "slot",
        "--slot",
        "5",
        "--json",
        env={"NEXUS_RUNTIME_CONFIG": str(config)},
    )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "config_error"
    assert "CLOUDFLARE_ACCESS_CLIENT_ID_API_KEY is not set" in envelope["error"]


def test_inspect_slot_refuses_plaintext_credentials_as_a_config_error() -> None:
    """NEXUS_AUTH bound for a non-loopback plain-HTTP API is never sent."""
    completed = _run(
        "inspect",
        "slot",
        "--slot",
        "5",
        "--json",
        env={
            "NEXUS_API_URL": "http://nexus.example.invalid",
            "NEXUS_AUTH": "815-token",
        },
    )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "config_error"
    assert "Refusing to send NEXUS_AUTH over plaintext" in envelope["error"]


# ---------------------------------------------------------------------------
# Remote-profile refusal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ("trait-audit", "--slot", "5"),
        ("inspect-turn", "--slot", "5", "--session", "815-session"),
        ("faction-audit", "--slot", "5"),
        ("model", "--slot", "5"),
    ],
    ids=["trait-audit", "inspect-turn", "faction-audit", "model-read"],
)
def test_remote_profile_refuses_database_commands_without_connecting(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    """Under the remote profile a direct-database verb never reaches PostgreSQL."""
    config = _config(tmp_path, profile="remote")
    with _postgres_sentinel() as (port, accepted):
        completed = _run(
            *argv,
            "--json",
            env={
                "NEXUS_RUNTIME_CONFIG": str(config),
                "PGHOST": "127.0.0.1",
                "PGPORT": str(port),
                "PGCONNECT_TIMEOUT": "2",
            },
        )

    assert completed.returncode == ExitCode.TRANSPORT_REFUSED
    envelope = _failure(completed)
    assert envelope["code"] == "transport_refused"
    assert envelope["partial"] == {}
    assert f"'nexus {argv[0]}' uses the database transport" in envelope["error"]
    assert "[runtime] profile is 'remote'" in envelope["error"]
    assert accepted == []


@pytest.mark.parametrize(
    "argv",
    [
        ("usage",),
        ("logs", "gateway"),
        ("models", "verify"),
        ("model", "--list"),
        ("retrograde-expand-seeds", "--packet", "p.json", "--seed-candidates", "s"),
    ],
    ids=["usage-ledger", "logs", "models-verify", "model-list", "provider-call"],
)
def test_remote_profile_refuses_local_operator_commands(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    """Local ledgers, logs, artifacts and secrets are not read for a remote runtime."""
    config = _config(tmp_path, profile="remote")
    completed = _run(*argv, "--json", env={"NEXUS_RUNTIME_CONFIG": str(config)})

    assert completed.returncode == ExitCode.TRANSPORT_REFUSED
    envelope = _failure(completed)
    assert envelope["code"] == "transport_refused"
    assert "uses the local_operator transport" in envelope["error"]


def test_explicit_runtime_config_selects_the_profile_checked(tmp_path: Path) -> None:
    """A runtime verb's --config decides, not the checkout's local profile."""
    config = _config(tmp_path, profile="remote")
    completed = _run("logs", "gateway", "--config", str(config), "--json", env={})

    assert completed.returncode == ExitCode.TRANSPORT_REFUSED
    assert _failure(completed)["code"] == "transport_refused"


def test_non_loopback_api_url_refuses_database_commands(tmp_path: Path) -> None:
    """A local profile aimed at a remote API still refuses local database reads."""
    config = _config(tmp_path, profile="local")
    with _postgres_sentinel() as (port, accepted):
        completed = _run(
            "inspect-turn",
            "--slot",
            "5",
            "--chunk",
            "7",
            "--json",
            env={
                "NEXUS_RUNTIME_CONFIG": str(config),
                "NEXUS_API_URL": "https://nexus.example.invalid",
                "PGHOST": "127.0.0.1",
                "PGPORT": str(port),
                "PGCONNECT_TIMEOUT": "2",
            },
        )

    assert completed.returncode == ExitCode.TRANSPORT_REFUSED
    envelope = _failure(completed)
    assert "NEXUS_API_URL targets https://nexus.example.invalid" in envelope["error"]
    assert accepted == []


def test_remote_profile_keeps_http_commands_and_the_runtime_probe(
    tmp_path: Path,
) -> None:
    """HTTP verbs, and up/status probing the hosted runtime, still run."""
    runtime_status = {"ok": True, "profile": "local", "version": "815"}
    gateway = Gateway(
        routes={
            ("GET", "/api/slot/5/state"): (200, SLOT_STATE),
            ("GET", "/runtime/status"): (200, runtime_status),
        }
    )
    with _serve(gateway) as base_url:
        config = _config(tmp_path, profile="remote", base_url=base_url)
        env = {"NEXUS_RUNTIME_CONFIG": str(config)}
        inspected = _run("inspect", "slot", "--slot", "5", "--json", env=env)
        status = _run("status", "--json", env=env)
        up = _run("up", "--json", env=env)

    assert inspected.returncode == ExitCode.OK, inspected.stderr
    assert json.loads(inspected.stdout) == {"ok": True, "data": SLOT_STATE}
    assert status.returncode == ExitCode.OK, status.stderr
    assert json.loads(status.stdout)["runtime"] == runtime_status
    assert up.returncode == ExitCode.OK, up.stderr
    assert json.loads(up.stdout)["profile"] == "remote"
    assert [request[:2] for request in gateway.requests] == [
        ("GET", "/api/slot/5/state"),
        ("GET", "/runtime/status"),
        ("GET", "/runtime/status"),
    ]


# ---------------------------------------------------------------------------
# The error envelope
# ---------------------------------------------------------------------------


def test_json_failure_preserves_every_partial_field() -> None:
    """A confirmed artifact whose next phase fails keeps its recovery fields.

    Before the contract, ``--json`` printed only ``{"error": ...}`` here and
    discarded the accepted phase and the recovery command.
    """
    gateway = Gateway(
        routes={
            ("GET", "/api/slot/5/state"): (
                200,
                {
                    "slot": 5,
                    "is_empty": False,
                    "is_wizard_mode": True,
                    "phase": "setting",
                    "pending_confirmation": "setting",
                    "thread_id": "thread-815",
                    "artifact_token": "setting-token",
                    "choices": [],
                },
            ),
            ("POST", "/api/story/new/setup/confirm"): (
                200,
                {
                    "status": "confirmed",
                    "phase": "setting",
                    "next_phase": "character",
                    "thread_id": "thread-815",
                },
            ),
            ("POST", "/api/story/new/chat"): (
                503,
                {"detail": "Introduction unavailable"},
            ),
        }
    )
    with _serve(gateway) as base_url:
        completed = _run(
            "--json", "continue", "--slot", "5", env={"NEXUS_API_URL": base_url}
        )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "domain_failure"
    assert envelope["error"].startswith(
        "Artifact confirmed, but the next phase could not be loaded: "
    )
    assert envelope["partial"] == {
        "phase": "character",
        "phase_complete": True,
        "recovery_command": "nexus load --slot 5",
    }
    assert [request[:2] for request in gateway.requests] == [
        ("GET", "/api/slot/5/state"),
        ("POST", "/api/story/new/setup/confirm"),
        ("POST", "/api/story/new/chat"),
    ]


def test_partial_fields_keep_meaningful_falsy_values() -> None:
    """False and zero are preserved work; None and empty containers are not."""
    result = {
        "success": False,
        "error": "Generation failed",
        "code": "domain_failure",
        "narrative_bootstrap": False,
        "chunk_id": 0,
        "phase": None,
        "choices": [],
        "message": "",
        "generation_error": {"status": "timeout", "status_code": None},
    }

    assert partial_fields(result) == {
        "narrative_bootstrap": False,
        "chunk_id": 0,
        "generation_error": {"status": "timeout", "status_code": None},
    }


def test_error_envelope_refuses_an_unregistered_code() -> None:
    """A handler naming an unknown code is a programming fault, raised loudly."""
    with pytest.raises(ValueError, match="Unregistered CLI error code"):
        error_envelope("mystery", "message", {})


# ---------------------------------------------------------------------------
# Remote detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "loopback"),
    [
        ("http://localhost:8002", True),
        ("http://127.0.0.1:8002", True),
        ("http://127.8.0.2:8002", True),
        ("http://[::1]:8002", True),
        ("http://gateway.localhost:8002", True),
        ("https://nexus.pythagora.net", False),
        ("http://10.0.0.5:8002", False),
        ("http://localhost.example.com", False),
    ],
)
def test_loopback_detection(url: str, loopback: bool) -> None:
    """Only this machine's addresses count as a local API target."""
    assert is_loopback_url(url) is loopback


def test_api_url_without_a_host_is_refused() -> None:
    """A malformed override is an error, not silently treated as local."""
    with pytest.raises(ValueError, match="NEXUS_API_URL has no host"):
        is_loopback_url("localhost:8002")


def test_checkout_config_is_local_and_the_remote_profile_is_remote() -> None:
    """The shipped config is local; flipping its profile makes it remote."""
    settings = load_settings(ROOT / "nexus.toml")
    runtime = settings.runtime
    assert runtime is not None
    assert detect_remote_runtime(runtime, None) is None
    assert detect_remote_runtime(runtime, "http://127.0.0.1:8002") is None

    remote = detect_remote_runtime(
        runtime.model_copy(update={"profile": "remote"}), None
    )
    assert remote is not None and remote.profile is True
    assert runtime.remote is not None
    assert runtime.remote.base_url in remote.reason
