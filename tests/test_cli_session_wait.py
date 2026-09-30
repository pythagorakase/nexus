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
from threading import Event, Thread
import time
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

import pytest
import requests  # type: ignore[import-untyped]
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
    # 1-based ordinal of the status read whose answer stops after its headers
    # and part of its body, as a gateway that stalls mid-answer does.
    stall_body_read: int | None = None
    # HTTP status of every status read, when the route answers with an error.
    status_code: int = 200
    # Every status read redirects to itself, so no read ever gets an answer.
    redirect_status: bool = False
    # What the state read after the session finished does instead of
    # answering: "drop" closes the connection, "stall" holds it unanswered,
    # "stall_body" sends the headers and part of the body, then holds the rest.
    state_failure: str | None = None
    status_reads: int = 0
    read_times: list[float] = field(default_factory=list)
    requests: list[tuple[str, str]] = field(default_factory=list)


@contextmanager
def _gateway(session: Session) -> Iterator[str]:
    """Serve scheduling, durable status, and slot state for one session."""

    released = Event()

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stall_body(self, payload: Any) -> None:
            """Send the headers and half the body, then hold the rest back."""
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body[: len(body) // 2])
            released.wait()
            self.close_connection = True

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
                if has_run and session.state_failure == "drop":
                    self.close_connection = True
                    return
                if has_run and session.state_failure == "stall":
                    released.wait()
                    return
                state = {
                    "is_empty": False,
                    "is_wizard_mode": False,
                    "has_pending": True,
                    "current_chunk_id": 40,
                    "session_id": SESSION if has_run else "draft-before",
                    "storyteller_text": NARRATIVE if has_run else "Before.",
                    "choices": ["Follow the dark."],
                }
                if has_run and session.state_failure == "stall_body":
                    self._stall_body(state)
                    return
                self._respond(state)
            elif url.path == f"/api/narrative/status/{SESSION}":
                assert parse_qs(url.query) == {"slot": ["5"]}, url.query
                session.status_reads += 1
                session.read_times.append(time.monotonic())
                if session.status_reads == session.drop_read:
                    # Close the connection without answering.
                    self.close_connection = True
                    return
                if session.redirect_status:
                    self.send_response(302)
                    self.send_header("Location", self.path)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if session.status_code != 200:
                    self._respond({"detail": "Session gone"}, session.status_code)
                    return
                index = min(session.status_reads, len(session.statuses)) - 1
                status = session.statuses[index]
                payload = {
                    "session_id": SESSION,
                    "status": status,
                    "chunk_id": None,
                    "error": session.error if status == "error" else None,
                }
                if session.status_reads == session.stall_body_read:
                    self._stall_body(payload)
                    return
                self._respond(payload)
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
        released.set()
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


def test_wait_reports_a_status_answer_stalled_after_its_headers_as_a_timeout(
    api_url,
) -> None:
    """A status answer whose body stalls past the budget is a timeout, not a loss.

    Requests reports a body read that runs out of time as a ConnectionError
    wrapping urllib3's ReadTimeoutError, not as a Timeout; the gateway did
    answer, so the wait ends as the budget running out.
    """
    session = Session(statuses=["initiated"], stall_body_read=2)
    with _gateway(session) as base_url:
        api_url(base_url)
        started = time.monotonic()
        with pytest.raises(cli.SessionWaitFailure) as caught:
            cli.wait_for_session(SESSION, slot=5, timeout=1.0, interval=0.05)
        elapsed = time.monotonic() - started

    assert (caught.value.status, caught.value.code) == ("timeout", "domain_failure")
    assert caught.value.detail == "Generation timed out: no status answer within 1.0s"
    assert ERROR_CODES[caught.value.code] == ExitCode.DOMAIN_FAILURE
    # The shape this guards: the stall surfaced as a wrapped ConnectionError.
    assert isinstance(caught.value.__cause__, requests.exceptions.ConnectionError)
    assert not isinstance(caught.value.__cause__, requests.exceptions.Timeout)
    # The stalled read is not retried.
    assert session.status_reads == 2
    assert 0.9 <= elapsed < 5


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


def test_wait_keeps_a_gone_gateway_unreachable_while_a_read_timeout_is_handled(
    api_url,
) -> None:
    """A read timeout the caller is handling is not a cause of a later failure.

    Python chains that handled exception onto the refused connection as its
    ``__context__``, so the read-timeout check follows only causes.
    """
    api_url(f"http://127.0.0.1:{_closed_port()}")
    try:
        raise requests.exceptions.ReadTimeout("An earlier read ran out of time")
    except requests.exceptions.ReadTimeout:
        with pytest.raises(cli.SessionWaitFailure) as caught:
            cli.wait_for_session(SESSION, slot=5, timeout=10, interval=0.05)

    assert (caught.value.status, caught.value.code) == (
        "unreachable",
        "api_unreachable",
    )


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


def test_wait_reports_any_other_failed_read_as_a_domain_failure(api_url) -> None:
    """A request error that is not a lost connection keeps the domain code."""
    session = Session(redirect_status=True)
    with _gateway(session) as base_url:
        api_url(base_url)
        with pytest.raises(cli.SessionWaitFailure) as caught:
            cli.wait_for_session(SESSION, slot=5, timeout=10, interval=0.05)

    assert (caught.value.status, caught.value.code) == ("http_error", "domain_failure")
    assert caught.value.detail.startswith(
        f"Could not read {base_url}/api/narrative/status/{SESSION}: "
    )
    assert "redirects" in caught.value.detail


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


def _run(
    base_url: str, *argv: str, config: Path = ROOT / "nexus.toml"
) -> subprocess.CompletedProcess[str]:
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
            "NEXUS_RUNTIME_CONFIG": str(config),
            "NEXUS_KEYRING_DISABLE": "1",
            "PYTHONPATH": str(ROOT),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )


def _cli_config(
    tmp_path: Path, *, apex: dict[str, Any] | None = None, **cli_settings: float
) -> Path:
    """Write a copy of the checkout config with ``[runtime.cli]`` overrides.

    ``apex`` overrides ``[apex]`` keys too (the generation budget).
    """
    document: Any = tomlkit.parse((ROOT / "nexus.toml").read_text(encoding="utf-8"))
    document["runtime"]["cli"].update(cli_settings)
    document["apex"].update(apex or {})
    config = tmp_path / "nexus.toml"
    config.write_text(tomlkit.dumps(document), encoding="utf-8")
    return config


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


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_command_polls_at_the_configured_interval(command: str, tmp_path: Path) -> None:
    """Each command waits [runtime.cli].poll_interval_seconds between reads."""
    argv, _route = COMMANDS[command]
    config = _cli_config(tmp_path, poll_interval_seconds=0.3)
    session = Session(statuses=["initiated", "initiated", "complete"])
    with _gateway(session) as base_url:
        completed = _run(base_url, *argv, config=config)

    assert completed.returncode == ExitCode.OK, completed.stderr
    assert session.status_reads == 3
    gaps = [b - a for a, b in zip(session.read_times, session.read_times[1:])]
    # The checkout's own interval is 1.0s; these reads are 0.3s apart.
    assert all(0.29 <= gap < 1.0 for gap in gaps), gaps


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_command_keeps_the_session_when_a_read_fails_otherwise(command: str) -> None:
    """A failed status read that is not a lost connection keeps the partial.

    The request error (here too many redirects) is a domain failure, not an
    escape past the waiter that loses the scheduled session.
    """
    argv, _route = COMMANDS[command]
    session = Session(redirect_status=True)
    with _gateway(session) as base_url:
        completed = _run(base_url, *argv)

    assert completed.returncode == ExitCode.DOMAIN_FAILURE, completed.stderr
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr
    envelope = json.loads(completed.stderr)
    assert envelope["code"] == "domain_failure"
    assert envelope["error"].startswith(f"Could not read {base_url}/api/narrative/")
    assert envelope["partial"]["session_id"] == SESSION
    assert envelope["partial"]["generation_error"]["status"] == "http_error"
    assert envelope["partial"]["recovery_command"] == "nexus load --slot 5"


def test_continue_reports_a_state_read_dropped_after_the_session_as_unreachable() -> (
    None
):
    """The state read after a finished session can lose the gateway too."""
    session = Session(statuses=["complete"], state_failure="drop")
    with _gateway(session) as base_url:
        completed = _run(base_url, *COMMANDS["continue"][0])

    assert completed.returncode == ExitCode.UNREACHABLE, completed.stderr
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr
    envelope = json.loads(completed.stderr)
    assert envelope["code"] == "api_unreachable"
    assert envelope["error"].startswith(f"Cannot connect to API server at {base_url}")
    assert envelope["partial"]["session_id"] == SESSION
    assert envelope["partial"]["generation_error"]["status"] == "unreachable"
    assert envelope["partial"]["recovery_command"] == "nexus load --slot 5"
    assert session.status_reads == 1


def test_continue_reports_a_stalled_state_read_as_a_domain_failure(
    tmp_path: Path,
) -> None:
    """A gateway that accepted the state read but answered too late is exit 1.

    It did not refuse or drop the connection, so the saved-work rule makes it
    a domain failure, as a status read that times out already is.
    """
    config = _cli_config(tmp_path, request_timeout_seconds=0.5)
    session = Session(statuses=["complete"], state_failure="stall")
    with _gateway(session) as base_url:
        completed = _run(base_url, *COMMANDS["continue"][0], config=config)

    assert completed.returncode == ExitCode.DOMAIN_FAILURE, completed.stderr
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr
    envelope = json.loads(completed.stderr)
    assert envelope["code"] == "domain_failure"
    assert envelope["error"].startswith(
        f"Timed out waiting for API server at {base_url}"
    )
    assert envelope["partial"]["session_id"] == SESSION
    assert envelope["partial"]["generation_error"]["status"] == "timeout"
    assert envelope["partial"]["recovery_command"] == "nexus load --slot 5"


@pytest.mark.parametrize("read", ["status", "state"])
def test_continue_reports_an_answer_stalled_after_its_headers_as_a_domain_failure(
    read: str, tmp_path: Path
) -> None:
    """A read whose body stalls past its timeout is exit 1, not a lost gateway.

    The gateway sends the headers and part of the body, then holds the rest.
    Requests reports that as a ConnectionError wrapping urllib3's
    ReadTimeoutError; the status read and the slot-state read after it both
    report it as their timeout and keep the scheduled session in ``partial``.
    """
    if read == "status":
        config = _cli_config(tmp_path, apex={"generation_timeout_seconds": 1})
        session = Session(statuses=["initiated"], stall_body_read=1)
    else:
        config = _cli_config(tmp_path, request_timeout_seconds=0.5)
        session = Session(statuses=["complete"], state_failure="stall_body")
    with _gateway(session) as base_url:
        completed = _run(base_url, *COMMANDS["continue"][0], config=config)

    assert completed.returncode == ExitCode.DOMAIN_FAILURE, completed.stderr
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr
    envelope = json.loads(completed.stderr)
    assert envelope["code"] == "domain_failure"
    if read == "status":
        assert envelope["error"] == "Generation timed out: no status answer within 1s"
    else:
        assert envelope["error"].startswith(
            f"Timed out waiting for API server at {base_url}: "
        )
        assert "Read timed out" in envelope["error"]
    assert envelope["partial"]["session_id"] == SESSION
    assert envelope["partial"]["generation_error"] == {
        "status": "timeout",
        "detail": envelope["error"],
    }
    assert envelope["partial"]["recovery_command"] == "nexus load --slot 5"
    assert session.status_reads == 1
