"""Qualify the CLI's one generation-session waiter over real loopback HTTP.

``nexus.cli.wait_for_session`` is exercised in process against a
``ThreadingHTTPServer`` this module starts, and ``continue`` and
``regenerate`` run as real ``python -m nexus.cli`` subprocesses against the
same kind of gateway. Nothing mocks ``requests``; no slot or provider is used.
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
from threading import Thread
import time
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

import pytest
import tomlkit

from nexus import cli
from nexus.cli_contract import ERROR_CODES, ExitCode

ROOT = Path(__file__).resolve().parents[1]
SESSION = "815-wait-session"
NARRATIVE = "The lamps along the quay gutter out one by one."


@dataclass
class Session:
    """The status script one generation session serves, and what was read."""

    # Status values served in order; the last one repeats.
    statuses: list[str] = field(default_factory=lambda: ["complete"])
    error: str | None = None
    # 1-based ordinal of the status read whose connection the gateway drops
    # without an answer, as a gateway process that dies mid-wait does.
    drop_read: int | None = None
    # HTTP status of every status read, when the route answers with an error.
    status_code: int = 200
    status_reads: int = 0
    read_times: list[float] = field(default_factory=list)
    requests: list[tuple[str, str]] = field(default_factory=list)


@contextmanager
def _gateway(session: Session) -> Iterator[str]:
    """Serve scheduling, durable status, and slot state for one session."""

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else {}
            session.requests.append(("POST", self.path))
            if self.path in {"/api/narrative/continue", "/api/narrative/regenerate"}:
                assert body.get("slot") == 5, body
                self._respond({"session_id": SESSION, "status": "initiated"})
                return
            self._respond({"detail": f"Unexpected POST {self.path}"}, 404)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            url = urlparse(self.path)
            session.requests.append(("GET", url.path))
            if url.path == "/api/slot/5/state":
                has_run = session.status_reads > 0
                self._respond(
                    {
                        "is_empty": False,
                        "is_wizard_mode": False,
                        "has_pending": True,
                        "current_chunk_id": 40,
                        "session_id": SESSION if has_run else "draft-before",
                        "storyteller_text": NARRATIVE if has_run else "Before.",
                        "choices": ["Follow the dark."],
                    }
                )
            elif url.path == f"/api/narrative/status/{SESSION}":
                assert parse_qs(url.query) == {"slot": ["5"]}, url.query
                session.status_reads += 1
                session.read_times.append(time.monotonic())
                if session.status_reads == session.drop_read:
                    # Close the connection without answering.
                    self.close_connection = True
                    return
                if session.status_code != 200:
                    self._respond({"detail": "Session gone"}, session.status_code)
                    return
                index = min(session.status_reads, len(session.statuses)) - 1
                status = session.statuses[index]
                self._respond(
                    {
                        "session_id": SESSION,
                        "status": status,
                        "chunk_id": None,
                        "error": session.error if status == "error" else None,
                    }
                )
            else:
                self._respond({"detail": f"Unexpected GET {self.path}"}, 404)

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


def _closed_port() -> int:
    """Return a loopback port nothing listens on."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture()
def api_url(monkeypatch: pytest.MonkeyPatch):
    """Point the in-process CLI at a URL for the length of one test."""

    def point(url: str) -> None:
        monkeypatch.setenv("NEXUS_API_URL", url)

    monkeypatch.delenv("NEXUS_RUNTIME_CONFIG", raising=False)
    monkeypatch.delenv("NEXUS_HOME", raising=False)
    return point


# ---------------------------------------------------------------------------
# wait_for_session, in process
# ---------------------------------------------------------------------------


def test_wait_returns_the_terminal_status_after_polling_at_the_interval(
    api_url,
) -> None:
    """A running session is read at the interval until it reports completion."""
    session = Session(statuses=["initiated", "initiated", "complete"])
    with _gateway(session) as base_url:
        api_url(base_url)
        status = cli.wait_for_session(SESSION, slot=5, timeout=10, interval=0.2)

    assert status == {
        "session_id": SESSION,
        "status": "complete",
        "chunk_id": None,
        "error": None,
    }
    assert session.status_reads == 3
    gaps = [b - a for a, b in zip(session.read_times, session.read_times[1:])]
    assert all(gap >= 0.19 for gap in gaps), gaps


def test_wait_reports_a_failed_generation_with_the_apis_message(api_url) -> None:
    """A session the API reports as failed is a domain failure, not a retry."""
    session = Session(statuses=["initiated", "error"], error="Writer seat refused")
    with _gateway(session) as base_url:
        api_url(base_url)
        with pytest.raises(cli.SessionWaitFailure) as caught:
            cli.wait_for_session(SESSION, slot=5, timeout=10, interval=0.05)

    failure = caught.value
    assert (failure.status, failure.detail, failure.code) == (
        "error",
        "Writer seat refused",
        "domain_failure",
    )
    assert session.status_reads == 2


def test_wait_times_out_while_the_session_still_runs(api_url) -> None:
    """The overall budget ends a wait on a session that never finishes."""
    session = Session(statuses=["initiated"])
    with _gateway(session) as base_url:
        api_url(base_url)
        started = time.monotonic()
        with pytest.raises(cli.SessionWaitFailure) as caught:
            cli.wait_for_session(SESSION, slot=5, timeout=0.5, interval=0.1)
        elapsed = time.monotonic() - started

    assert (caught.value.status, caught.value.code) == ("timeout", "domain_failure")
    assert caught.value.detail == "Generation timed out"
    assert 0.5 <= elapsed < 5
    assert session.status_reads >= 3


def test_wait_surfaces_a_gateway_that_drops_the_connection(api_url) -> None:
    """A status read the gateway never answers ends the wait as unreachable."""
    session = Session(statuses=["initiated"], drop_read=2)
    with _gateway(session) as base_url:
        api_url(base_url)
        with pytest.raises(cli.SessionWaitFailure) as caught:
            cli.wait_for_session(SESSION, slot=5, timeout=10, interval=0.05)

    assert (caught.value.status, caught.value.code) == (
        "unreachable",
        "api_unreachable",
    )
    assert caught.value.detail.startswith(f"Cannot connect to API server at {base_url}")
    # The failed read is not retried.
    assert session.status_reads == 2


def test_wait_surfaces_a_gateway_that_is_gone(api_url) -> None:
    """Nothing listening at the API URL is unreachable on the first read."""
    base_url = f"http://127.0.0.1:{_closed_port()}"
    api_url(base_url)
    with pytest.raises(cli.SessionWaitFailure) as caught:
        cli.wait_for_session(SESSION, slot=5, timeout=10, interval=0.05)

    assert (caught.value.status, caught.value.code) == (
        "unreachable",
        "api_unreachable",
    )
    assert ERROR_CODES[caught.value.code] == ExitCode.UNREACHABLE


def test_wait_reports_an_http_error_answer_with_its_body(api_url) -> None:
    """A status route that answers with an error status is a domain failure."""
    session = Session(status_code=404)
    with _gateway(session) as base_url:
        api_url(base_url)
        with pytest.raises(cli.SessionWaitFailure) as caught:
            cli.wait_for_session(SESSION, slot=5, timeout=10, interval=0.05)

    assert (caught.value.status, caught.value.code) == ("http_error", "domain_failure")
    assert "returned HTTP 404" in caught.value.detail
    assert "Session gone" in caught.value.detail


def test_poll_interval_is_read_from_runtime_cli(tmp_path: Path, monkeypatch) -> None:
    """The wait cadence is the [runtime.cli] poll_interval_seconds setting."""
    document: Any = tomlkit.parse((ROOT / "nexus.toml").read_text(encoding="utf-8"))
    assert document["runtime"]["cli"]["poll_interval_seconds"] > 0
    document["runtime"]["cli"]["poll_interval_seconds"] = 0.125
    config = tmp_path / "nexus.toml"
    config.write_text(tomlkit.dumps(document), encoding="utf-8")
    monkeypatch.delenv("NEXUS_HOME", raising=False)
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))

    assert cli._poll_interval_seconds() == 0.125


# ---------------------------------------------------------------------------
# continue and regenerate, through the real entry point
# ---------------------------------------------------------------------------


def _run(base_url: str, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run ``nexus <argv> --json`` against the loopback gateway."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"NEXUS_HOME", "NEXUS_GATEWAY_PORT"}
    }
    return subprocess.run(
        [sys.executable, "-m", "nexus.cli", *argv, "--json"],
        cwd=ROOT,
        env={
            **env,
            "NEXUS_API_URL": base_url,
            "NEXUS_RUNTIME_CONFIG": str(ROOT / "nexus.toml"),
            "NEXUS_KEYRING_DISABLE": "1",
            "PYTHONPATH": str(ROOT),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )


COMMANDS = {
    "continue": (("continue", "--slot", "5", "--choice", "1"), "continue"),
    "regenerate": (("regenerate", "--slot", "5"), "regenerate"),
}


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_command_waits_through_a_running_session(command: str) -> None:
    """Both commands load the finished session's narrative after it runs."""
    argv, route = COMMANDS[command]
    session = Session(statuses=["initiated", "complete"])
    with _gateway(session) as base_url:
        completed = _run(base_url, *argv)

    assert completed.returncode == ExitCode.OK, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["success"] is True
    assert payload["session_id"] == SESSION
    assert payload["message"] == NARRATIVE
    assert session.status_reads == 2
    assert ("POST", f"/api/narrative/{route}") in session.requests


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_command_reports_a_failed_generation_as_a_domain_failure(
    command: str,
) -> None:
    """The API's own failure message is the error; the session is kept."""
    argv, _route = COMMANDS[command]
    session = Session(statuses=["initiated", "error"], error="Writer seat refused")
    with _gateway(session) as base_url:
        completed = _run(base_url, *argv)

    assert completed.returncode == ExitCode.DOMAIN_FAILURE, completed.stderr
    assert completed.stdout == ""
    envelope = json.loads(completed.stderr)
    assert envelope["code"] == "domain_failure"
    assert envelope["error"] == "Writer seat refused"
    assert envelope["partial"]["session_id"] == SESSION
    assert envelope["partial"]["generation_error"] == {
        "status": "error",
        "detail": "Writer seat refused",
    }
    assert envelope["partial"]["recovery_command"] == "nexus load --slot 5"


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_command_reports_a_gateway_lost_mid_wait_as_unreachable(
    command: str,
) -> None:
    """A dead gateway mid-wait exits 4 and keeps the scheduled session.

    ``regenerate`` once swallowed the failed read and retried every second
    until its budget ran out.
    """
    argv, _route = COMMANDS[command]
    session = Session(statuses=["initiated"], drop_read=2)
    with _gateway(session) as base_url:
        started = time.monotonic()
        completed = _run(base_url, *argv)
        elapsed = time.monotonic() - started

    assert completed.returncode == ExitCode.UNREACHABLE, completed.stderr
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr
    envelope = json.loads(completed.stderr)
    assert envelope["code"] == "api_unreachable"
    assert envelope["error"].startswith(f"Cannot connect to API server at {base_url}")
    assert envelope["partial"]["session_id"] == SESSION
    assert envelope["partial"]["generation_error"]["status"] == "unreachable"
    assert envelope["partial"]["recovery_command"] == "nexus load --slot 5"
    assert session.status_reads == 2
    assert elapsed < 30
