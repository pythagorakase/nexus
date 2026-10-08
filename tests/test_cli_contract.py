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
import re
import socket
import subprocess
import sys
from threading import Event, Thread
from typing import Any, Iterator, Optional
from urllib.parse import parse_qs, urlparse

import pytest
import tomlkit

from nexus import cli
from nexus.api.deprecated_tag_audit import audit_database_names
from nexus.api.route_capabilities import ROUTE_CAPABILITIES
from nexus.cli_contract import (
    COMMAND_TRANSPORTS,
    ENVELOPE_COMMANDS,
    ERROR_CODES,
    FLAG_TRANSPORTS,
    REMOTE_PROFILE_TRANSPORTS,
    RUNTIME_CONFIG_COMMANDS,
    SELF_DIAGNOSTIC_COMMANDS,
    ExitCode,
    detect_remote_runtime,
    error_envelope,
    is_loopback_url,
    iter_command_paths,
    partial_fields,
)
from nexus.config import load_settings
from nexus.util.secret_manager import InMemorySecretBackend, keychain_read_error

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


@dataclass(frozen=True)
class Raw:
    """A route answer sent as given: its own body, content type and headers."""

    body: str
    content_type: str = "text/html"
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Gateway:
    """Routes a loopback gateway answers, and every request it received.

    A route answers ``(status, payload)``: a payload is sent as JSON, a
    :class:`Raw` payload as given.
    """

    routes: dict[tuple[str, str], tuple[int, Any]] = field(default_factory=dict)
    requests: list[tuple[str, str, Any]] = field(default_factory=list)
    # The parsed query string of each request, in the order of ``requests``.
    queries: list[dict[str, list[str]]] = field(default_factory=list)
    # Accept and record every request but answer none while the gateway serves:
    # a runtime that is up yet never answers within the CLI's request timeout.
    stall: bool = False
    # Promise a longer body than is sent, then close the connection: a gateway
    # that dies while sending its answer.
    truncate: bool = False


@contextmanager
def _serve(gateway: Gateway) -> Iterator[str]:
    """Serve ``gateway`` on loopback; unknown routes answer 404 like FastAPI."""
    released = Event()

    class Handler(BaseHTTPRequestHandler):
        def _answer(self, method: str) -> None:
            url = urlparse(self.path)
            path = url.path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            gateway.requests.append((method, path, json.loads(raw) if raw else None))
            gateway.queries.append(parse_qs(url.query))
            if gateway.stall:
                released.wait()
                return
            status, payload = gateway.routes.get(
                (method, path), (404, {"detail": "Not Found"})
            )
            if isinstance(payload, Raw):
                body = payload.body.encode()
                content_type = payload.content_type
                headers = payload.headers
            else:
                body = json.dumps(payload).encode()
                content_type = "application/json"
                headers = {}
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            for name, value in headers.items():
                self.send_header(name, value)
            promised = len(body) + (4096 if gateway.truncate else 0)
            self.send_header("Content-Length", str(promised))
            self.end_headers()
            self.wfile.write(body)
            if gateway.truncate:
                self.close_connection = True

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            self._answer("GET")

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            self._answer("POST")

        def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler contract
            self._answer("PATCH")

        def do_PUT(self) -> None:  # noqa: N802 - stdlib handler contract
            self._answer("PUT")

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        released.set()
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


def _config(
    tmp_path: Path,
    *,
    profile: str,
    base_url: Optional[str] = None,
    cli_settings: Optional[dict[str, float]] = None,
) -> Path:
    """Write a copy of the checkout config with the given runtime profile.

    ``cli_settings`` overrides keys of ``[runtime.cli]``, such as its request
    timeouts.
    """
    document: Any = tomlkit.parse((ROOT / "nexus.toml").read_text(encoding="utf-8"))
    document["runtime"]["profile"] = profile
    document["runtime"]["cli"].update(cli_settings or {})
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
    assert set(SELF_DIAGNOSTIC_COMMANDS) <= set(COMMAND_TRANSPORTS)
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


@pytest.mark.parametrize(
    ("argv", "sent"),
    [
        (("inspect", "slot", "--slot", "5"), ("GET", "/api/slot/5/state")),
        (("load", "--slot", "5"), ("GET", "/api/slot/5/state")),
        (("lock", "--slot", "5"), ("POST", "/api/slot/5/lock")),
        (
            ("model", "--slot", "5", "--set", "slot-pinned-model"),
            ("PATCH", "/api/slot/5/settings"),
        ),
        (("regenerate", "--slot", "5"), ("POST", "/api/narrative/regenerate")),
        (("accept", "--slot", "5"), ("POST", "/api/narrative/approve")),
    ],
    ids=["inspect-slot", "load", "lock", "model-set", "regenerate", "accept"],
)
def test_http_command_unanswered_request_exits_four(
    tmp_path: Path, argv: tuple[str, ...], sent: tuple[str, str]
) -> None:
    """A gateway that accepts the request but never answers is api_unreachable.

    The legacy handlers once caught the read timeout as a domain failure
    (exit 1); every HTTP command now reports it like an unreachable API.
    ``regenerate``'s scheduling POST is bounded by
    ``[runtime.cli].turn_request_timeout_seconds``, once a 120 s literal. Its
    short-request budgets stay at 30 s, so only the turn budget can produce
    ``read timeout=0.5``.
    ``accept``'s commit POST takes the turn budget too.
    """
    cli_settings = {"request_timeout_seconds": 0.5, "inspect_timeout_seconds": 0.5}
    if argv[0] in ("regenerate", "accept"):
        cli_settings = {
            "request_timeout_seconds": 30.0,
            "inspect_timeout_seconds": 30.0,
            "turn_request_timeout_seconds": 0.5,
        }
    config = _config(tmp_path, profile="local", cli_settings=cli_settings)
    gateway = Gateway(stall=True)
    with _serve(gateway) as base_url:
        completed = _run(
            *argv,
            "--json",
            env={"NEXUS_API_URL": base_url, "NEXUS_RUNTIME_CONFIG": str(config)},
        )

    assert completed.returncode == ExitCode.UNREACHABLE
    envelope = _failure(completed)
    assert envelope["code"] == "api_unreachable"
    assert envelope["error"].startswith(
        f"Timed out waiting for API server at {base_url}"
    )
    assert "read timeout=0.5" in envelope["error"]
    assert [request[:2] for request in gateway.requests] == [sent]


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
    [
        ("load", "--json"),
        ("--json", "load"),
        ("inspect", "--json", "slot"),
    ],
    ids=["json-after-command", "json-before-command", "nested-command"],
)
def test_argparse_rejection_under_json_is_the_usage_envelope(
    argv: tuple[str, ...],
) -> None:
    """argparse's own rejection prints the envelope, not its usage text.

    Before the contract covered it, argparse exited 2 with its plain-text usage
    block, so a caller parsing stderr as JSON failed on a missing flag.
    """
    completed = _run(*argv, env={})

    assert completed.returncode == ExitCode.USAGE
    assert "usage:" not in completed.stderr
    assert _failure(completed) == {
        "ok": False,
        "code": "usage_error",
        "error": "the following arguments are required: --slot",
        "partial": {},
    }


def test_argparse_rejection_without_json_keeps_argparse_output() -> None:
    """Without --json argparse prints its usage and error, and --help still works."""
    rejected = _run("load", env={})
    helped = _run("--json", "load", "--help", env={})

    assert rejected.returncode == ExitCode.USAGE
    assert rejected.stdout == ""
    assert rejected.stderr.startswith("usage: ")
    assert rejected.stderr.endswith(
        " load: error: the following arguments are required: --slot\n"
    )
    assert helped.returncode == ExitCode.OK
    assert helped.stderr == ""
    assert helped.stdout.startswith("usage: ")
    assert "--slot SLOT" in helped.stdout


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


# The inspect family and the legacy HTTP handlers both propagate request
# failures to main(), which reports them alike.
_HTTP_COMMANDS = pytest.mark.parametrize(
    "argv",
    [("inspect", "slot", "--slot", "5"), ("load", "--slot", "5")],
    ids=["inspect-slot", "load"],
)


@_HTTP_COMMANDS
@pytest.mark.parametrize(
    ("api_url", "message"),
    [
        ("localhost:8002", "NEXUS_API_URL has no host: 'localhost:8002'"),
        ("ftp://127.0.0.1:8002", "No connection adapters were found"),
    ],
    ids=["no-scheme", "not-http"],
)
def test_http_command_malformed_api_url_is_a_config_error(
    argv: tuple[str, ...], api_url: str, message: str
) -> None:
    """An API URL requests cannot use is a config error, not a traceback."""
    completed = _run(*argv, "--json", env={"NEXUS_API_URL": api_url})

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "config_error"
    assert envelope["error"].startswith(message)


@pytest.mark.parametrize(
    "argv",
    [
        ("inspect", "slot", "--slot", "5"),
        ("load", "--slot", "5"),
        ("model", "--slot", "5", "--set", "slot-pinned-model"),
    ],
    ids=["inspect-slot", "load", "model-set"],
)
def test_http_command_missing_access_secret_is_a_config_error(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    """A remote profile whose Access secret is absent fails before any request."""
    config = _config(tmp_path, profile="remote")
    completed = _run(*argv, "--json", env={"NEXUS_RUNTIME_CONFIG": str(config)})

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "config_error"
    assert "CLOUDFLARE_ACCESS_CLIENT_ID_API_KEY is not set" in envelope["error"]


@_HTTP_COMMANDS
def test_http_command_refuses_plaintext_credentials_as_a_config_error(
    argv: tuple[str, ...],
) -> None:
    """NEXUS_AUTH bound for a non-loopback plain-HTTP API is never sent."""
    completed = _run(
        *argv,
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


def _run_in_process(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *argv: str,
    env: dict[str, str],
) -> tuple[int, str, str]:
    """Run ``cli.main()`` in this process, so an injected store reaches it.

    A child process cannot use the backend a fixture injects, so these tests
    call the real entry point here, with the isolated environment ``_run``
    gives a child.
    """
    for name in _ISOLATED_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["nexus", *argv])
    exit_code = cli.main()
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def _locked_access_store_message() -> str:
    """The message the unreadable store gives for the Access client id read."""
    return str(
        keychain_read_error(
            "cloudflare_access_client_id",
            subprocess.CalledProcessError(
                36, ["security"], stderr="STDERR-SENTINEL-821"
            ),
        )
    )


def test_http_command_unreadable_access_store_is_a_config_error(
    unreadable_secret_store: InMemorySecretBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A locked store under the remote profile is a config error, not a crash."""
    config = _config(tmp_path, profile="remote")
    exit_code, out, err = _run_in_process(
        monkeypatch,
        capsys,
        "inspect",
        "slot",
        "--slot",
        "5",
        "--json",
        env={"NEXUS_RUNTIME_CONFIG": str(config)},
    )

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert out == ""
    envelope = json.loads(err)
    assert envelope["code"] == "config_error"
    assert envelope["error"] == _locked_access_store_message()
    assert "security unlock-keychain" in envelope["error"]
    assert "STDERR-SENTINEL-821" not in err


def test_runtime_status_names_an_unreadable_access_store(
    unreadable_secret_store: InMemorySecretBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """nexus status reports the locked store's message; nothing escapes."""
    config = _config(tmp_path, profile="remote")
    exit_code, out, err = _run_in_process(
        monkeypatch,
        capsys,
        "status",
        "--config",
        str(config),
        "--json",
        env={},
    )

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert out == ""
    envelope = json.loads(err)
    assert envelope["error"] == _locked_access_store_message()
    assert "STDERR-SENTINEL-821" not in err


# ---------------------------------------------------------------------------
# Answers the HTTP handlers cannot use
# ---------------------------------------------------------------------------

# Each legacy HTTP handler and the first request it sends.
_HANDLER_FIRST_REQUESTS: dict[str, tuple[tuple[str, ...], tuple[str, str]]] = {
    "load": (("load", "--slot", "5"), ("GET", "/api/slot/5/state")),
    "continue": (
        ("continue", "--slot", "5", "--choice", "1"),
        ("GET", "/api/slot/5/state"),
    ),
    "retry": (("retry", "--slot", "5"), ("GET", "/api/slot/5/state")),
    "undo": (("undo", "--slot", "5"), ("POST", "/api/slot/5/undo")),
    "accept": (("accept", "--slot", "5"), ("POST", "/api/narrative/approve")),
    "regenerate": (
        ("regenerate", "--slot", "5"),
        ("POST", "/api/narrative/regenerate"),
    ),
    "model-set": (
        ("model", "--slot", "5", "--set", "slot-pinned-model"),
        ("PATCH", "/api/slot/5/settings"),
    ),
    "clear": (("clear", "--slot", "5"), ("POST", "/api/story/new/setup/reset")),
    "lock": (("lock", "--slot", "5"), ("POST", "/api/slot/5/lock")),
    "unlock": (("unlock", "--slot", "5"), ("POST", "/api/slot/5/unlock")),
}
_BAD_GATEWAY_PAGE = "<html><body><h1>502 Bad Gateway</h1></body></html>"
_SUCCESS_PAGE = "<html><body>Signed in.</body></html>"
_ACCESS_LOGIN = (
    "https://pythagora.cloudflareaccess.com/cdn-cgi/access/login/"
    "nexus.pythagora.net?kid=815&redirect_url=%2Fapi%2Fslot%2F5%2Fstate"
)


@pytest.mark.parametrize(
    ("handler", "status", "answer", "body"),
    [
        *(
            (handler, 502, Raw(_BAD_GATEWAY_PAGE), _BAD_GATEWAY_PAGE)
            for handler in _HANDLER_FIRST_REQUESTS
        ),
        ("load", 404, {"detail": "Not Found"}, '{"detail": "Not Found"}'),
    ],
    ids=[*(f"{handler}-502" for handler in _HANDLER_FIRST_REQUESTS), "load-404"],
)
def test_http_handler_error_answer_is_an_api_error(
    handler: str, status: int, answer: Any, body: str
) -> None:
    """A non-2xx answer is api_error with its body and status, in every handler.

    The handlers once caught it as a domain failure with an empty partial.
    """
    argv, first = _HANDLER_FIRST_REQUESTS[handler]
    gateway = Gateway(routes={first: (status, answer)})
    with _serve(gateway) as base_url:
        completed = _run(*argv, "--json", env={"NEXUS_API_URL": base_url})

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "api_error"
    assert envelope["error"] == f"API error: {body}"
    assert envelope["partial"] == {"status_code": status}
    assert [request[:2] for request in gateway.requests] == [first]


@pytest.mark.parametrize(
    ("handler", "answer", "message"),
    [
        *(
            (handler, Raw(_SUCCESS_PAGE), "returned a body that is not JSON: ")
            for handler in (
                "load",
                "continue",
                "retry",
                "undo",
                "accept",
                "regenerate",
                "model-set",
            )
        ),
        *(
            (
                handler,
                Raw("[]", content_type="application/json"),
                "returned a body that is not a JSON object",
            )
            for handler in ("load", "continue")
        ),
    ],
    ids=[
        *(
            f"{handler}-html"
            for handler in (
                "load",
                "continue",
                "retry",
                "undo",
                "accept",
                "regenerate",
                "model-set",
            )
        ),
        "load-array",
        "continue-array",
    ],
)
def test_http_handler_non_json_success_is_an_invalid_response(
    handler: str, answer: Raw, message: str
) -> None:
    """A 2xx body that is not a JSON object is invalid_response, not a traceback.

    The handlers once reported it as a domain failure, and ``retry`` raised.
    """
    argv, first = _HANDLER_FIRST_REQUESTS[handler]
    gateway = Gateway(routes={first: (200, answer)})
    with _serve(gateway) as base_url:
        completed = _run(*argv, "--json", env={"NEXUS_API_URL": base_url})

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "invalid_response"
    assert envelope["error"].startswith(f"{base_url}{first[1]} {message}")
    assert envelope["partial"] == {}
    assert [request[:2] for request in gateway.requests] == [first]


def test_accept_sends_slot_and_commit_and_reports_the_chunk() -> None:
    """Accept commits the pending draft without adding a session or choice."""
    gateway = Gateway(
        routes={
            ("POST", "/api/narrative/approve"): (
                200,
                {
                    "status": "committed",
                    "message": "Narrative committed as chunk 42",
                    "chunk_id": 42,
                },
            )
        }
    )
    with _serve(gateway) as base_url:
        completed = _run(
            "accept", "--slot", "5", "--json", env={"NEXUS_API_URL": base_url}
        )

    assert completed.returncode == ExitCode.OK, completed.stderr
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {
        "success": True,
        "message": "Slot 5: committed chunk 42",
        "chunk_id": 42,
    }
    assert gateway.requests == [
        ("POST", "/api/narrative/approve", {"slot": 5, "commit": True})
    ]


@pytest.mark.parametrize(
    "answer",
    [
        {"status": "reviewed", "chunk_id": 42},
        {"status": "committed", "chunk_id": None},
        {"status": "committed", "chunk_id": True},
    ],
    ids=["not-committed", "missing-id", "bool-id"],
)
def test_accept_refuses_an_answer_without_a_chunk_id(answer: dict[str, Any]) -> None:
    """A reviewed, absent or boolean chunk ID is not evidence of a commit."""
    gateway = Gateway(routes={("POST", "/api/narrative/approve"): (200, answer)})
    with _serve(gateway) as base_url:
        completed = _run(
            "accept", "--slot", "5", "--json", env={"NEXUS_API_URL": base_url}
        )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "invalid_response"
    assert envelope["error"] == (
        f"{base_url}/api/narrative/approve returned no committed chunk ID"
    )


@pytest.mark.parametrize(
    ("argv", "partial"),
    [
        (("load", "--slot", "5"), {}),
        (("inspect", "slot", "--slot", "5"), {"slot": 5}),
    ],
    ids=["load", "inspect-slot"],
)
@pytest.mark.parametrize(
    ("status", "answer"),
    [
        (401, Raw("Unauthorized")),
        (302, Raw("", headers={"Location": _ACCESS_LOGIN})),
    ],
    ids=["401", "302-access-login"],
)
def test_access_rejection_is_a_config_error(
    argv: tuple[str, ...], partial: dict[str, Any], status: int, answer: Raw
) -> None:
    """A 401, 403 or unfollowed redirect is an edge's rejection: config_error.

    The gateway itself answers none of them, so the error names the status,
    any redirect target, and the Access settings to check. A credential is
    set, so the redirect is not followed.
    """
    gateway = Gateway(routes={("GET", "/api/slot/5/state"): (status, answer)})
    with _serve(gateway) as base_url:
        completed = _run(
            *argv,
            "--json",
            env={"NEXUS_API_URL": base_url, "NEXUS_AUTH": "815-token"},
        )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "config_error"
    assert f"{base_url}/api/slot/5/state" in envelope["error"]
    assert f"HTTP {status}" in envelope["error"]
    assert "[runtime.remote.cloudflare_access]" in envelope["error"]
    if status == 302:
        assert _ACCESS_LOGIN in envelope["error"]
    assert envelope["partial"] == {**partial, "status_code": status}
    assert [request[:2] for request in gateway.requests] == [
        ("GET", "/api/slot/5/state")
    ]


@pytest.mark.parametrize(
    ("state", "route", "prefix"),
    [
        (
            {"is_empty": True},
            ("POST", "/api/story/new/setup/start"),
            "Failed to initialize wizard: ",
        ),
        (
            {"is_wizard_mode": True, "phase": "ready"},
            ("POST", "/api/story/new/transition"),
            "Transition failed: ",
        ),
    ],
    ids=["wizard-setup", "transition"],
)
def test_own_wording_step_keeps_its_text_for_a_redirect(
    state: dict[str, Any], route: tuple[str, str], prefix: str
) -> None:
    """Wizard setup and the transition keep their own text for an Access redirect.

    A 3xx is not 2xx, so the step reports the answer's body under its own
    wording with the code ``config_error``, and names no Access setting.
    """
    gateway = Gateway(
        routes={
            ("GET", "/api/slot/5/state"): (200, state),
            route: (302, Raw("redirected", headers={"Location": _ACCESS_LOGIN})),
        }
    )
    with _serve(gateway) as base_url:
        completed = _run(
            "continue",
            "--slot",
            "5",
            "--json",
            env={"NEXUS_API_URL": base_url, "NEXUS_AUTH": "815-token"},
        )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "config_error"
    assert envelope["error"] == f"{prefix}redirected"
    assert "[runtime.remote.cloudflare_access]" not in envelope["error"]
    assert envelope["partial"] == {}
    assert [request[:2] for request in gateway.requests] == [
        ("GET", "/api/slot/5/state"),
        route,
    ]


def test_followed_redirect_loop_is_a_domain_failure() -> None:
    """A request that gets no usable answer is a domain failure, not a traceback.

    Without a runtime credential the redirect is followed, so a route that
    redirects to itself ends in too many redirects: no answer to classify,
    which the generation waiter also reports as a domain failure.
    """
    route = ("GET", "/api/slot/5/state")
    gateway = Gateway(routes={route: (302, Raw("", headers={"Location": route[1]}))})
    with _serve(gateway) as base_url:
        completed = _run(
            "load", "--slot", "5", "--json", env={"NEXUS_API_URL": base_url}
        )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "domain_failure"
    assert envelope["error"].startswith(f"Could not read {base_url}: ")
    assert "redirects" in envelope["error"]
    assert envelope["partial"] == {}
    assert len(gateway.requests) > 1
    assert {request[:2] for request in gateway.requests} == {route}


def test_remote_up_against_a_closed_port_exits_four(tmp_path: Path) -> None:
    """``up`` under the remote profile reports an unreachable runtime as exit 4."""
    base_url = f"http://127.0.0.1:{_closed_port()}"
    config = _config(tmp_path, profile="remote", base_url=base_url)
    completed = _run("up", "--json", env={"NEXUS_RUNTIME_CONFIG": str(config)})

    assert completed.returncode == ExitCode.UNREACHABLE
    envelope = _failure(completed)
    assert envelope["code"] == "api_unreachable"
    assert envelope["error"].startswith(f"Cannot connect to API server at {base_url}")


@pytest.mark.parametrize(
    ("recovery", "retry_answer", "message", "sent"),
    [
        ("failed-8", None, "returned a recovery that is not a JSON object", 1),
        ({"parent_chunk_id": 9}, None, "returned a recovery with no session ID", 1),
        (
            {"session_id": "failed-8"},
            {"status": "initiated"},
            "returned no session ID",
            2,
        ),
    ],
    ids=["recovery-string", "recovery-without-session", "answer-without-session"],
)
def test_retry_without_a_usable_session_is_an_invalid_response(
    recovery: Any, retry_answer: Any, message: str, sent: int
) -> None:
    """``retry`` needs a recovery session and a new session, never a traceback."""
    gateway = Gateway(
        routes={
            ("GET", "/api/slot/5/state"): (200, {**SLOT_STATE, "recovery": recovery}),
            ("POST", "/api/narrative/retry"): (200, retry_answer),
        }
    )
    with _serve(gateway) as base_url:
        completed = _run(
            "retry", "--slot", "5", "--json", env={"NEXUS_API_URL": base_url}
        )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "invalid_response"
    assert message in envelope["error"]
    assert envelope["partial"] == {}
    assert len(gateway.requests) == sent


def test_model_read_database_error_is_a_database_error(tmp_path: Path) -> None:
    """``model --slot N`` reports a slot database it cannot open as database_error.

    ``[api.database]`` leaves host and port to the PG environment, so a
    closed loopback port stands in for a database that is down.
    """
    config = _config(tmp_path, profile="local")
    completed = _run(
        "model",
        "--slot",
        "5",
        "--json",
        env={
            "NEXUS_RUNTIME_CONFIG": str(config),
            "PGHOST": "127.0.0.1",
            "PGPORT": str(_closed_port()),
        },
    )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == "database_error"
    assert "127.0.0.1" in envelope["error"]
    assert envelope["partial"] == {}


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
    [("tags", "audit", "--slot", "3"), ("tags", "audit", "--all")],
    ids=["one-slot", "all"],
)
def test_remote_profile_refuses_the_tags_audit_without_connecting(
    tmp_path: Path, argv: tuple[str, ...]
) -> None:
    """The deprecated-tag audit reads databases directly, so remote refuses it."""
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
    assert "'nexus tags audit' uses the database transport" in envelope["error"]
    assert accepted == []


def test_tags_audit_is_a_slot_checked_database_envelope_command() -> None:
    """``tags audit`` is JSON-first, reads databases directly, and checks --slot."""
    registered = set(iter_command_paths(cli.build_parser()))
    assert {path for path in registered if path.startswith("tags ")} == {"tags audit"}
    assert COMMAND_TRANSPORTS["tags audit"] == "database"
    assert "tags audit" in ENVELOPE_COMMANDS
    assert "tags audit" in cli._SLOT_COMMANDS
    # --all reads NEXUS_template first, then save_01 through save_05.
    assert audit_database_names(None) == [
        "NEXUS_template",
        "save_01",
        "save_02",
        "save_03",
        "save_04",
        "save_05",
    ]
    assert audit_database_names(4) == ["save_04"]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (("--slot", "9"), "Slot must be between 1 and 5"),
        (("--slot", "3", "--all"), "not allowed with argument --slot"),
        ((), "one of the arguments --slot --all is required"),
    ],
    ids=["slot-range", "slot-and-all", "no-scope"],
)
def test_tags_audit_rejects_an_unusable_scope_before_any_connection(
    argv: tuple[str, ...], message: str
) -> None:
    """A bad --slot/--all scope is a usage error that opens no connection."""
    with _postgres_sentinel() as (port, accepted):
        completed = _run(
            "tags",
            "audit",
            *argv,
            "--json",
            env={"PGHOST": "127.0.0.1", "PGPORT": str(port)},
        )

    assert completed.returncode == ExitCode.USAGE
    envelope = _failure(completed)
    assert envelope["code"] == "usage_error"
    assert message in envelope["error"]
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


def test_doctor_reports_its_own_config_under_a_remote_runtime(tmp_path: Path) -> None:
    """The self-diagnostic command is neither refused nor pre-empted by config_error."""
    config = tmp_path / "nexus.toml"
    config.write_text("[runtime\n", encoding="utf-8")
    completed = _run(
        "doctor",
        "--target",
        "ci-runner",
        "--config",
        str(config),
        env={"NEXUS_API_URL": "https://nexus.example.invalid"},
    )

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    assert "Traceback" not in completed.stderr, completed.stderr
    assert "transport_refused" not in completed.stderr
    assert "config_error" not in completed.stderr
    lines = completed.stdout.splitlines()
    assert len(lines) == 2, completed.stdout
    assert lines[0].startswith(f"fail  config.valid       {config}: ")
    assert lines[1] == "skip  reachability.gate  config.valid failed"


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
# The player-plane inspect family
# ---------------------------------------------------------------------------


def _chunk(chunk_id: int) -> dict[str, Any]:
    """One chunk in the reader routes' wire shape."""
    return {
        "id": chunk_id,
        "rawText": f"Chunk {chunk_id} prose.",
        "storytellerText": f"Chunk {chunk_id} prose.",
        "choiceObject": None,
        "choiceText": None,
        "createdAt": "2100-01-01T00:00:00+00:00",
        "hasInlineSceneMarkup": False,
        "metadata": {"id": chunk_id, "chunkId": chunk_id, "season": 1, "episode": 1},
    }


def _adjacent(
    chunk_id: int, previous: Optional[int], following: Optional[int]
) -> tuple[tuple[str, str], tuple[int, Any]]:
    """The adjacent-chunks route of ``chunk_id`` in a story of those chunks."""
    return (
        ("GET", f"/api/narrative/chunks/{chunk_id}/adjacent"),
        (
            200,
            {
                "previous": _chunk(previous) if previous is not None else None,
                "next": _chunk(following) if following is not None else None,
            },
        ),
    )


DRAFT = {
    "session_id": "815-draft",
    "chunk_id": None,
    "parent_chunk_id": 12,
    "user_text": "Follow the lamplighter.",
    "storyteller_text": "The lamplighter turns down an alley.",
    "choice_object": {"presented": ["Follow.", "Wait."]},
}
CHARACTERS = [
    {"id": 1, "name": "Fixture Player", "currentLocation": "1"},
    {"id": 3, "name": "Mara Quill", "currentLocation": "2"},
]
PLACES = [
    {"id": 1, "name": "Fixture Plaza", "type": "fixed_location"},
    {"id": 2, "name": "Quill House", "type": "fixed_location"},
]
FACTIONS = [{"id": 7, "name": "The Lamplighters", "summary": "Keepers of light."}]
# A story whose committed chunks are 10, 11, and 12 (13 was never committed).
INSPECT_ROUTES: dict[tuple[str, str], tuple[int, Any]] = dict(
    [
        (("GET", "/api/narrative/latest-chunk"), (200, _chunk(12))),
        (("GET", "/api/narrative/chunks/12"), (200, _chunk(12))),
        _adjacent(0, None, 10),
        _adjacent(9, None, 10),
        _adjacent(10, None, 11),
        _adjacent(11, 10, 12),
        _adjacent(12, 11, None),
        (("GET", "/api/narrative/incubator"), (200, DRAFT)),
        (("GET", "/api/characters"), (200, CHARACTERS)),
        (("GET", "/api/places"), (200, PLACES)),
        (("GET", "/api/factions"), (200, FACTIONS)),
    ]
)
SLOT_QUERY = {"slot": ["5"]}

# Each verb, the data its envelope carries, and the requests it sends.
INSPECT_CASES: dict[str, tuple[tuple[str, ...], Any, list[tuple[str, dict]]]] = {
    "chunks-last": (
        ("chunks", "--last", "2"),
        [_chunk(11), _chunk(12)],
        [
            ("/api/narrative/latest-chunk", SLOT_QUERY),
            ("/api/narrative/chunks/12/adjacent", SLOT_QUERY),
        ],
    ),
    "chunks-last-past-the-first": (
        ("chunks", "--last", "5"),
        [_chunk(10), _chunk(11), _chunk(12)],
        [
            ("/api/narrative/latest-chunk", SLOT_QUERY),
            ("/api/narrative/chunks/12/adjacent", SLOT_QUERY),
            ("/api/narrative/chunks/11/adjacent", SLOT_QUERY),
            ("/api/narrative/chunks/10/adjacent", SLOT_QUERY),
        ],
    ),
    "chunks-range": (
        ("chunks", "--from", "10", "--to", "11"),
        [_chunk(10), _chunk(11)],
        [
            ("/api/narrative/chunks/9/adjacent", SLOT_QUERY),
            ("/api/narrative/chunks/10/adjacent", SLOT_QUERY),
        ],
    ),
    "chunks-first-to": (
        ("chunks", "--to", "11"),
        [_chunk(10), _chunk(11)],
        [
            ("/api/narrative/chunks/0/adjacent", SLOT_QUERY),
            ("/api/narrative/chunks/10/adjacent", SLOT_QUERY),
        ],
    ),
    # No committed chunk has id 13: one more request finds the story's end.
    "chunks-range-past-the-last": (
        ("chunks", "--from", "11", "--to", "13"),
        [_chunk(11), _chunk(12)],
        [
            ("/api/narrative/chunks/10/adjacent", SLOT_QUERY),
            ("/api/narrative/chunks/11/adjacent", SLOT_QUERY),
            ("/api/narrative/chunks/12/adjacent", SLOT_QUERY),
        ],
    ),
    "chunk": (
        ("chunk", "12"),
        _chunk(12),
        [("/api/narrative/chunks/12", SLOT_QUERY)],
    ),
    "incubator": (
        ("incubator",),
        DRAFT,
        [("/api/narrative/incubator", SLOT_QUERY)],
    ),
    "characters": (
        ("characters",),
        CHARACTERS,
        [("/api/characters", SLOT_QUERY)],
    ),
    "character": (
        ("characters", "3"),
        CHARACTERS[1],
        [("/api/characters", {**SLOT_QUERY, "startId": ["3"], "endId": ["3"]})],
    ),
    "places": (("places",), PLACES, [("/api/places", SLOT_QUERY)]),
    "place": (("places", "2"), PLACES[1], [("/api/places", SLOT_QUERY)]),
    "factions": (("factions",), FACTIONS, [("/api/factions", SLOT_QUERY)]),
    "faction": (("factions", "7"), FACTIONS[0], [("/api/factions", SLOT_QUERY)]),
}


def _inspect(
    gateway: Gateway, *argv: str, json_output: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run ``nexus inspect <argv> --slot 5`` against the gateway."""
    with _serve(gateway) as base_url:
        return _run(
            "inspect",
            *argv,
            "--slot",
            "5",
            *(["--json"] if json_output else []),
            env={"NEXUS_API_URL": base_url},
        )


def test_inspect_family_registers_every_verb_as_an_http_envelope_command() -> None:
    """Every inspect verb is an HTTP, JSON-first, slot-checked command."""
    registered = {
        path for path in iter_command_paths(cli.build_parser()) if " " in path
    }
    verbs = {path for path in registered if path.startswith("inspect ")}
    assert verbs == {
        "inspect slot",
        "inspect chunks",
        "inspect chunk",
        "inspect incubator",
        "inspect characters",
        "inspect places",
        "inspect factions",
    }
    for verb in verbs:
        assert COMMAND_TRANSPORTS[verb] == "http", verb
        assert verb in ENVELOPE_COMMANDS, verb
        assert verb in cli._SLOT_COMMANDS, verb


@pytest.mark.parametrize("case", sorted(INSPECT_CASES))
def test_inspect_verb_prints_the_route_body_in_the_envelope(case: str) -> None:
    """Each verb reads its player-plane route and changes nothing but the envelope."""
    argv, data, sent = INSPECT_CASES[case]
    gateway = Gateway(routes=dict(INSPECT_ROUTES))
    completed = _inspect(gateway, *argv)

    assert completed.returncode == ExitCode.OK, completed.stderr
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {"ok": True, "data": data}
    assert [request[:2] for request in gateway.requests] == [
        ("GET", path) for path, _query in sent
    ]
    assert gateway.queries == [query for _path, query in sent]


def _route_template(path: str) -> Optional[tuple[str, str]]:
    """The ROUTE_CAPABILITIES key serving a concrete GET path, if any.

    Of the templates matching the path, the one with the fewest parameters
    wins, as in the gateway: ``/chunks/12/adjacent`` is the adjacent-chunks
    route, not ``/chunks/{season_id}/{episode_id}``.
    """
    matches = []
    for method, template in ROUTE_CAPABILITIES:
        if method != "GET" or "{full_path" in template:
            continue
        pattern = re.sub(r"\\{[^/]+?\\}", "[^/]+", re.escape(template))
        if re.fullmatch(pattern, path):
            matches.append((template.count("{"), method, template))
    if not matches:
        return None
    _parameters, method, template = min(matches)
    return method, template


def test_inspect_verbs_read_only_player_plane_routes() -> None:
    """No inspect verb reaches an operator route (issue #815's plane split)."""
    gateway = Gateway(routes=dict(INSPECT_ROUTES))
    with _serve(gateway) as base_url:
        for argv, _data, _sent in INSPECT_CASES.values():
            completed = _run(
                "inspect", *argv, "--slot", "5", env={"NEXUS_API_URL": base_url}
            )
            assert completed.returncode == ExitCode.OK, completed.stderr

    templates = set()
    for method, path, _body in gateway.requests:
        assert method == "GET", path
        key = _route_template(path)
        assert key is not None, f"{path} is not a declared route"
        capability = ROUTE_CAPABILITIES[key]
        assert capability.plane == "player", (key, capability)
        assert capability.slot_mode == "read", (key, capability)
        templates.add(key[1])
    assert templates == {
        "/api/narrative/latest-chunk",
        "/api/narrative/chunks/{chunk_id}/adjacent",
        "/api/narrative/chunks/{chunk_id}",
        "/api/narrative/incubator",
        "/api/characters",
        "/api/places",
        "/api/factions",
    }


def test_inspect_incubator_reports_an_empty_incubator_as_null() -> None:
    """No pending draft is an explicit ``data: null``, not a message to parse."""
    gateway = Gateway(
        routes={
            ("GET", "/api/narrative/incubator"): (
                200,
                {"message": "Incubator is empty"},
            )
        }
    )
    as_json = _inspect(gateway, "incubator")
    human = _inspect(gateway, "incubator", json_output=False)

    assert as_json.returncode == ExitCode.OK, as_json.stderr
    assert json.loads(as_json.stdout) == {"ok": True, "data": None}
    assert human.returncode == ExitCode.OK, human.stderr
    assert human.stdout == "Incubator is empty.\n"


def test_inspect_chunks_of_an_unplayed_story_is_an_empty_list() -> None:
    """The latest-chunk route's "No chunks found" answer is an empty read."""
    gateway = Gateway(
        routes={
            ("GET", "/api/narrative/latest-chunk"): (
                404,
                {"detail": "No chunks found"},
            )
        }
    )
    completed = _inspect(gateway, "chunks", "--last", "3")

    assert completed.returncode == ExitCode.OK, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True, "data": []}


def test_inspect_chunk_range_sends_no_request_past_its_last_chunk() -> None:
    """``--from 10 --to 11`` costs exactly two requests, one per chunk.

    The walk stops at the chunk with id ``--to``, so a failing read of chunk
    11's neighbours, which could only find chunk 12 outside the range, cannot
    discard the complete range.
    """
    routes = dict(INSPECT_ROUTES)
    routes[("GET", "/api/narrative/chunks/11/adjacent")] = (
        500,
        {"detail": "Internal Server Error"},
    )
    gateway = Gateway(routes=routes)
    completed = _inspect(gateway, "chunks", "--from", "10", "--to", "11")

    assert completed.returncode == ExitCode.OK, completed.stderr
    assert json.loads(completed.stdout) == {
        "ok": True,
        "data": [_chunk(10), _chunk(11)],
    }
    assert [request[:2] for request in gateway.requests] == [
        ("GET", "/api/narrative/chunks/9/adjacent"),
        ("GET", "/api/narrative/chunks/10/adjacent"),
    ]


def test_inspect_list_prints_each_record_without_json() -> None:
    """Human output prints one field per line, records separated by a blank line."""
    gateway = Gateway(routes=dict(INSPECT_ROUTES))
    completed = _inspect(gateway, "characters", json_output=False)

    assert completed.returncode == ExitCode.OK, completed.stderr
    assert completed.stdout == (
        "id: 1\nname: Fixture Player\ncurrentLocation: 1\n\n"
        "id: 3\nname: Mara Quill\ncurrentLocation: 2\n"
    )


@pytest.mark.parametrize(
    ("argv", "code", "message"),
    [
        (("factions", "8"), "not_found", "/api/factions lists no faction 8 in slot 5"),
        (("characters", "4"), "not_found", "lists no character 4 in slot 5"),
        (("chunk", "13"), "not_found", "/api/narrative/chunks/13 returned 404"),
    ],
    ids=["faction", "character", "chunk"],
)
def test_inspect_missing_record_is_not_found(
    argv: tuple[str, ...], code: str, message: str
) -> None:
    """An id the route does not serve exits 1 with not_found and the slot."""
    routes = dict(INSPECT_ROUTES)
    routes[("GET", "/api/characters")] = (200, [])
    gateway = Gateway(routes=routes)
    completed = _inspect(gateway, *argv)

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    envelope = _failure(completed)
    assert envelope["code"] == code
    assert message in envelope["error"]
    assert envelope["partial"]["slot"] == 5


@pytest.mark.parametrize(
    ("argv", "body"),
    [
        (("characters",), {"detail": "not a list"}),
        (("places",), [{"name": "No id"}]),
        (("incubator",), ["not", "an", "object"]),
        (("incubator",), {"storyteller_text": "No session"}),
        (("chunks", "--last", "1"), [_chunk(12)]),
    ],
    ids=["list-shape", "record-id", "incubator-shape", "draft-session", "chunk"],
)
def test_inspect_unusable_body_is_an_invalid_response(
    argv: tuple[str, ...], body: Any
) -> None:
    """A body the verb cannot pass through unchanged exits 1, never a traceback."""
    route = {
        "characters": "/api/characters",
        "places": "/api/places",
        "incubator": "/api/narrative/incubator",
        "chunks": "/api/narrative/latest-chunk",
    }[argv[0]]
    gateway = Gateway(routes={("GET", route): (200, body)})
    completed = _inspect(gateway, *argv)

    assert completed.returncode == ExitCode.DOMAIN_FAILURE
    assert _failure(completed)["code"] == "invalid_response"


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (("chunks",), "Pass --last N or a --from/--to chunk id range"),
        (
            ("chunks", "--last", "2", "--to", "9"),
            "--last cannot be combined with --from or --to",
        ),
        (("chunks", "--last", "0"), "--last must be a positive integer"),
        (("chunks", "--from", "0"), "--from must be a positive integer"),
        (
            ("chunks", "--from", "11"),
            "--from needs --to, so a range cannot walk the whole story",
        ),
        (("chunks", "--from", "9", "--to", "3"), "--from must not exceed --to"),
        (("chunk",), "the following arguments are required: chunk_id"),
        (("characters", "first"), "argument entity_id: invalid int value: 'first'"),
        (("places", "first"), "argument entity_id: invalid int value: 'first'"),
        (("factions", "first"), "argument entity_id: invalid int value: 'first'"),
    ],
    ids=[
        "no-range",
        "last-and-range",
        "last-zero",
        "from-zero",
        "from-open",
        "reversed",
        "chunk-id",
        "character-id",
        "place-id",
        "faction-id",
    ],
)
def test_inspect_rejects_unusable_arguments_before_any_request(
    argv: tuple[str, ...], message: str
) -> None:
    """Bad inspect arguments are a usage error (exit 2) and send nothing."""
    gateway = Gateway(routes=dict(INSPECT_ROUTES))
    completed = _inspect(gateway, *argv)

    assert completed.returncode == ExitCode.USAGE
    envelope = _failure(completed)
    assert envelope["code"] == "usage_error"
    assert envelope["error"] == message
    assert gateway.requests == []


# One well-formed invocation of every inspect verb, less its --slot.
INSPECT_VERB_ARGV: dict[str, tuple[str, ...]] = {
    "slot": ("slot",),
    "chunks": ("chunks", "--last", "1"),
    "chunk": ("chunk", "12"),
    "incubator": ("incubator",),
    "characters": ("characters",),
    "character": ("characters", "3"),
    "places": ("places",),
    "place": ("places", "2"),
    "factions": ("factions",),
    "faction": ("factions", "7"),
}


@pytest.mark.parametrize("verb", sorted(INSPECT_VERB_ARGV))
@pytest.mark.parametrize(
    ("slot_args", "message"),
    [
        (("--slot", "9"), "Slot must be between 1 and 5"),
        ((), "the following arguments are required: --slot"),
    ],
    ids=["out-of-range", "missing"],
)
def test_inspect_verb_refuses_an_unusable_slot_before_any_request(
    verb: str, slot_args: tuple[str, ...], message: str
) -> None:
    """Every inspect verb needs a slot from 1 to 5 and sends nothing without."""
    gateway = Gateway(routes=dict(INSPECT_ROUTES))
    with _serve(gateway) as base_url:
        completed = _run(
            "inspect",
            *INSPECT_VERB_ARGV[verb],
            *slot_args,
            "--json",
            env={"NEXUS_API_URL": base_url},
        )

    assert completed.returncode == ExitCode.USAGE
    envelope = _failure(completed)
    assert envelope["code"] == "usage_error"
    assert envelope["error"] == message
    assert gateway.requests == []


@pytest.mark.parametrize(
    "argv",
    [
        ("chunks", "--last", "1"),
        ("chunk", "12"),
        ("incubator",),
        ("characters",),
        ("places", "2"),
        ("factions",),
    ],
    ids=["chunks", "chunk", "incubator", "characters", "place", "factions"],
)
def test_inspect_verb_body_cut_off_mid_answer_exits_four(
    argv: tuple[str, ...],
) -> None:
    """A gateway that drops the connection while sending a body is unreachable."""
    gateway = Gateway(routes=dict(INSPECT_ROUTES), truncate=True)
    completed = _inspect(gateway, *argv)

    assert completed.returncode == ExitCode.UNREACHABLE
    envelope = _failure(completed)
    assert envelope["code"] == "api_unreachable"
    assert envelope["error"].startswith("Cannot connect to API server at ")
    assert gateway.requests


@pytest.mark.parametrize(
    "argv",
    [
        ("chunks", "--last", "1"),
        ("chunk", "12"),
        ("incubator",),
        ("characters",),
        ("places", "2"),
        ("factions",),
    ],
    ids=["chunks", "chunk", "incubator", "characters", "place", "factions"],
)
def test_inspect_verb_unreachable_api_exits_four(argv: tuple[str, ...]) -> None:
    """Nothing listening at the API URL is api_unreachable for every verb."""
    base_url = f"http://127.0.0.1:{_closed_port()}"
    completed = _run(
        "inspect", *argv, "--slot", "5", "--json", env={"NEXUS_API_URL": base_url}
    )

    assert completed.returncode == ExitCode.UNREACHABLE
    assert _failure(completed)["code"] == "api_unreachable"


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
    # The introduction's 503 is a non-2xx answer: api_error.
    assert envelope["code"] == "api_error"
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
