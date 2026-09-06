"""Qualify the public CLI generation protocol over a real loopback HTTP server.

The server serves gateway-shaped scheduling, durable-status, and slot-state
responses. CLI parsing, HTTP transport, polling, result validation, formatting,
exit codes, and interruption run in a subprocess; no slot or provider is used.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event, Thread
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

import pytest
import tomlkit

ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = "776-opening-session"
NARRATIVE = "Rain needles the orchard glass."


@dataclass
class GenerationScenario:
    """Gateway protocol state and observations for one CLI invocation."""

    result: str = "complete"
    seed: bool = True
    scheduled: bool = False
    status_reads: int = 0
    state_reads: int = 0
    requests: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    waiting: Event = field(default_factory=Event)


@contextmanager
def _gateway(scenario: GenerationScenario) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def _respond(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # The interruption case may close an in-flight status read.
                pass

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            scenario.requests.append(("POST", self.path, body))
            if body.get("slot") != 5:
                self._respond({"detail": "Explicit test slot required"}, 422)
            elif self.path == "/api/story/new/chat":
                self._respond(
                    {
                        "message": "The seed is saved.",
                        "phase": "seed",
                        "phase_complete": True,
                        "artifact_type": "story_seed",
                        "data": {"title": "The Glass Orchard"},
                    }
                )
            elif self.path == "/api/story/new/transition":
                self._respond({"retrograde": {"status": "complete"}})
            elif self.path == "/api/narrative/continue":
                if scenario.result == "schedule_error":
                    self._respond({"detail": "Opening generation unavailable"}, 503)
                    return
                scenario.scheduled = True
                self._respond(
                    {
                        "session_id": (
                            None if scenario.result == "missing_session" else SESSION_ID
                        ),
                        "status": "generating",
                        "message": "Narrative generation started",
                    }
                )
            else:
                self._respond({"detail": f"Unexpected POST {self.path}"}, 404)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            scenario.requests.append(("GET", self.path, {}))
            url = urlparse(self.path)
            if url.path == f"/api/narrative/status/{SESSION_ID}":
                scenario.status_reads += 1
                scenario.waiting.set()
                if parse_qs(url.query) != {"slot": ["5"]}:
                    self._respond({"detail": "Explicit test slot required"}, 422)
                    return
                if scenario.result == "status_error":
                    self._respond({"detail": "Status unavailable"}, 503)
                    return
                status = "processing"
                if scenario.result not in {"timeout", "interrupted"}:
                    status = (
                        "error"
                        if scenario.result == "generation_error"
                        else "complete" if scenario.status_reads > 1 else "processing"
                    )
                self._respond(
                    {
                        "session_id": SESSION_ID,
                        "status": status,
                        "chunk_id": 17 if status == "complete" else None,
                        "error": "Writer failed" if status == "error" else None,
                    }
                )
            elif url.path == "/api/slot/5/state":
                scenario.state_reads += 1
                if not scenario.scheduled:
                    self._respond(
                        {
                            "is_empty": False,
                            "is_wizard_mode": scenario.seed,
                            "phase": "seed" if scenario.seed else None,
                            "choices": ["Commit the final seed."],
                        }
                    )
                elif scenario.result == "load_error":
                    self._respond({"detail": "Completed state unavailable"}, 503)
                else:
                    self._respond(
                        {
                            "is_empty": False,
                            "is_wizard_mode": False,
                            "has_pending": True,
                            "session_id": (
                                "different-session"
                                if scenario.result == "mismatched_session"
                                else SESSION_ID
                            ),
                            "current_chunk_id": (
                                18 if scenario.result == "mismatched_chunk" else 17
                            ),
                            "storyteller_text": (
                                None if scenario.result == "empty_text" else NARRATIVE
                            ),
                            "choices": ["Enter the gate."],
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
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _run_cli(scenario: GenerationScenario, tmp_path: Path) -> tuple[int, str, str]:
    """Run the actual command against this isolated gateway and config."""

    config = tomlkit.parse((ROOT / "nexus.toml").read_text())
    config["apex"]["generation_timeout_seconds"] = (
        1 if scenario.result == "timeout" else 5
    )
    config_path = tmp_path / "nexus.toml"
    config_path.write_text(tomlkit.dumps(config))
    with _gateway(scenario) as base_url:
        env = {
            **os.environ,
            "NEXUS_API_URL": base_url,
            "NEXUS_RUNTIME_CONFIG": str(config_path),
            "NEXUS_KEYRING_DISABLE": "1",
            "PYTHONPATH": str(ROOT),
        }
        with subprocess.Popen(
            [
                sys.executable,
                "-m",
                "nexus.cli",
                "continue",
                "--slot",
                "5",
                "--choice",
                "1",
                "--json",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as process:
            if scenario.result == "interrupted":
                assert scenario.waiting.wait(timeout=10), "CLI never polled generation"
                process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=20)
            return process.returncode, stdout, stderr


@pytest.mark.parametrize("seed", [True, False], ids=["seed", "continuation"])
def test_cli_waits_for_real_generation_response_shape(
    tmp_path: Path, seed: bool
) -> None:
    """Scheduling cannot be mistaken for completed prose on either path."""

    scenario = GenerationScenario(seed=seed)
    code, stdout, stderr = _run_cli(scenario, tmp_path)
    assert code == 0, stderr
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["success"] is True
    assert payload["chunk_id"] == 17
    assert payload["session_id"] == SESSION_ID
    assert payload["choices"] == ["Enter the gate."]
    assert payload["next_phase_intro" if seed else "message"] == NARRATIVE
    if seed:
        assert payload["narrative_bootstrap"] is True
        assert payload["phase"] is None
        assert payload["artifact_data"] == {"title": "The Glass Orchard"}
        assert payload["retrograde"] == {"status": "complete"}
    assert scenario.status_reads == 2
    assert scenario.state_reads == 2
    scheduled = [
        request
        for request in scenario.requests
        if request[:2] == ("POST", "/api/narrative/continue")
    ]
    assert len(scheduled) == 1
    assert "model" not in scheduled[0][2]


@pytest.mark.parametrize(
    "outcome",
    [
        "schedule_error",
        "missing_session",
        "generation_error",
        "status_error",
        "load_error",
        "empty_text",
        "mismatched_chunk",
        "mismatched_session",
        "timeout",
        "interrupted",
    ],
)
def test_seed_bootstrap_failure_preserves_partial_work(
    tmp_path: Path, outcome: str
) -> None:
    """No failure or interruption reports empty success or repeats inference."""

    scenario = GenerationScenario(result=outcome)
    code, stdout, stderr = _run_cli(scenario, tmp_path)
    assert code == 1, (stdout, stderr)
    assert stdout == ""
    assert "Traceback" not in stderr
    payload = json.loads(stderr)
    assert payload["success"] is False
    assert payload["narrative_bootstrap"] is False
    assert payload["artifact_data"] == {"title": "The Glass Orchard"}
    assert payload["retrograde"] == {"status": "complete"}
    assert payload["phase"] is None
    assert payload["bootstrap_error"]["detail"]
    assert payload["recovery_command"] == "nexus load --slot 5"
    assert payload["recovery_command"] in payload["error"]
    assert "next_phase_intro" not in payload
    if outcome not in {"schedule_error", "missing_session"}:
        assert payload["session_id"] == SESSION_ID
    assert (
        sum(
            request[:2] == ("POST", "/api/narrative/continue")
            for request in scenario.requests
        )
        == 1
    )
