"""Qualify the edited-choice and regenerate CLI payloads over real loopback HTTP.

A gateway-shaped server answers slot state, scheduling, and durable status.
The actual ``nexus`` command runs in a subprocess: argument parsing, the HTTP
payload, polling, and output are all real; no slot or provider is touched.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHOICES = ["Read the ledger.", "Ask Sana about the missing page."]
EDITED = "Ask Sana, quietly, about the page torn from the ledger."
NEXT = "Sana folds the torn page into your palm."


@dataclass
class Gateway:
    """The pending draft the CLI acts on, and every request it made."""

    scheduled: str | None = None
    wizard: bool = False
    requests: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)


@contextmanager
def _gateway(gateway: Gateway) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def _respond(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            gateway.requests.append(("POST", self.path, body))
            sessions = {
                "/api/narrative/continue": "next-18",
                "/api/narrative/regenerate": "regen-17",
            }
            if body.get("slot") != 5 or self.path not in sessions:
                self._respond({"detail": f"Unexpected POST {self.path}"}, 404)
                return
            gateway.scheduled = sessions[self.path]
            self._respond(
                {
                    "session_id": gateway.scheduled,
                    "status": "processing",
                    "message": "Narrative generation started",
                }
            )

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            gateway.requests.append(("GET", self.path, {}))
            url = urlparse(self.path)
            if url.path == "/api/slot/5/state":
                self._respond(
                    {
                        "is_empty": False,
                        "is_wizard_mode": gateway.wizard,
                        "has_pending": True,
                        "current_chunk_id": 17,
                        "session_id": gateway.scheduled or "draft-17",
                        "storyteller_text": (
                            NEXT if gateway.scheduled else "The ledger waits."
                        ),
                        "choices": ["Keep the page."] if gateway.scheduled else CHOICES,
                    }
                )
            elif (
                gateway.scheduled is not None
                and url.path == f"/api/narrative/status/{gateway.scheduled}"
                and parse_qs(url.query) == {"slot": ["5"]}
            ):
                self._respond(
                    {
                        "session_id": gateway.scheduled,
                        "status": "complete",
                        "chunk_id": None,
                        "error": None,
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


def _run_cli(gateway: Gateway, *argv: str) -> tuple[int, dict[str, Any]]:
    """Run ``nexus --json <argv>`` against the loopback gateway."""
    with _gateway(gateway) as base_url:
        completed = subprocess.run(
            [sys.executable, "-m", "nexus.cli", "--json", *argv],
            cwd=ROOT,
            env={
                **os.environ,
                "NEXUS_API_URL": base_url,
                "NEXUS_RUNTIME_CONFIG": str(ROOT / "nexus.toml"),
                "NEXUS_KEYRING_DISABLE": "1",
                "PYTHONPATH": str(ROOT),
            },
            capture_output=True,
            text=True,
            timeout=60,
        )
    output = completed.stdout if completed.returncode == 0 else completed.stderr
    assert "Traceback" not in completed.stderr, completed.stderr
    return completed.returncode, json.loads(output)


def _posts(gateway: Gateway, path: str) -> list[dict[str, Any]]:
    """Return the JSON bodies the CLI posted to one gateway path."""
    return [
        body
        for method, url, body in gateway.requests
        if (method, url) == ("POST", path)
    ]


@pytest.mark.parametrize("text_flag", ["--text", "--user-text"])
def test_continue_sends_the_choice_and_its_edited_text_as_one_payload(
    text_flag: str,
) -> None:
    """``--choice K --text "..."`` is one edited-choice request, then waits."""
    gateway = Gateway()
    code, payload = _run_cli(
        gateway, "continue", "--slot", "5", "--choice", "2", text_flag, EDITED
    )

    assert code == 0, payload
    assert _posts(gateway, "/api/narrative/continue") == [
        {"slot": 5, "user_text": EDITED, "choice": 2, "accept_fate": False}
    ]
    assert payload["success"] is True
    assert payload["session_id"] == "next-18"
    assert payload["message"] == NEXT


def test_wizard_continue_refuses_a_choice_with_text() -> None:
    """The wizard has no edited choice, so the CLI refuses rather than drop text."""
    gateway = Gateway(wizard=True)
    code, payload = _run_cli(
        gateway, "continue", "--slot", "5", "--choice", "2", "--text", EDITED
    )

    assert code == 1
    assert "not both" in payload["error"]
    assert [method for method, _url, _body in gateway.requests] == ["GET"]


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--note", "darker, plz"], {"slot": 5, "note": "darker, plz"}),
        ([], {"slot": 5}),
    ],
    ids=["note", "no-note"],
)
def test_regenerate_sends_its_optional_note(
    argv: list[str], expected: dict[str, Any]
) -> None:
    """``nexus regenerate`` re-rolls the pending draft with the note, if any."""
    gateway = Gateway()
    code, payload = _run_cli(gateway, "regenerate", "--slot", "5", *argv)

    assert code == 0, payload
    assert _posts(gateway, "/api/narrative/regenerate") == [expected]
    assert _posts(gateway, "/api/narrative/continue") == []
    assert payload["success"] is True
    assert payload["message"] == NEXT
    assert payload["choices"] == ["Keep the page."]
