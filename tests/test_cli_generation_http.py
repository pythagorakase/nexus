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
    release_response: Event = field(default_factory=Event)
    status_body: bytes | None = None
    state_body: bytes | None = None
    # Retrograde stage payloads served in order while the transition is held;
    # the last one repeats. None serves no stage endpoint at all.
    stage_script: list[dict[str, Any]] | None = None
    stage_reads: int = 0
    stage_failure: bool = False
    stages_served: Event = field(default_factory=Event)
    transition_error: str | None = None
    ready: bool = False
    transitioned: bool = False


@contextmanager
def _gateway(scenario: GenerationScenario) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def _respond(self, payload: dict[str, Any], status: int = 200) -> None:
            self._respond_body(json.dumps(payload).encode(), status)

        def _respond_body(self, body: bytes, status: int = 200) -> None:
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
                if scenario.stage_script is not None:
                    # Hold the transition like a live Retrograde run until the
                    # CLI has read every scripted stage.
                    assert scenario.stages_served.wait(timeout=10), "stages unread"
                if scenario.transition_error is not None:
                    self._respond({"detail": scenario.transition_error}, 400)
                    return
                scenario.transitioned = True
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
            if (
                url.path == "/api/story/new/retrograde/status"
                and scenario.stage_script is not None
            ):
                if parse_qs(url.query) != {"slot": ["5"]}:
                    self._respond({"detail": "Explicit test slot required"}, 422)
                    return
                scenario.stage_reads += 1
                script = scenario.stage_script
                if scenario.stage_reads >= len(script):
                    scenario.stages_served.set()
                if scenario.stage_failure:
                    self._respond({"detail": "Gateway worker restarted"}, 502)
                    return
                self._respond(script[min(scenario.stage_reads, len(script)) - 1])
            elif url.path == f"/api/narrative/status/{SESSION_ID}":
                scenario.status_reads += 1
                scenario.waiting.set()
                if parse_qs(url.query) != {"slot": ["5"]}:
                    self._respond({"detail": "Explicit test slot required"}, 422)
                    return
                if scenario.result == "status_error":
                    self._respond({"detail": "Status unavailable"}, 503)
                    return
                if scenario.result == "response_timeout":
                    # Hold the real HTTP response until the CLI's own deadline
                    # expires; teardown releases the handler after process exit.
                    scenario.release_response.wait(timeout=10)
                if scenario.status_body is not None:
                    self._respond_body(scenario.status_body)
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
                if scenario.ready and not scenario.transitioned:
                    self._respond(
                        {"is_empty": False, "is_wizard_mode": True, "phase": "ready"}
                    )
                elif not scenario.scheduled:
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
                elif scenario.state_body is not None:
                    self._respond_body(scenario.state_body)
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
        scenario.release_response.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _run_cli(
    scenario: GenerationScenario, tmp_path: Path, *, json_output: bool = True
) -> tuple[int, str, str]:
    """Run the actual command against this isolated gateway and config."""

    config = tomlkit.parse((ROOT / "nexus.toml").read_text())
    config["apex"]["generation_timeout_seconds"] = (
        1 if scenario.result in {"timeout", "response_timeout"} else 5
    )
    config["orrery"]["retrograde"]["wizard"]["status_poll_interval_seconds"] = 0.02
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
                *(["--json"] if json_output else []),
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
    # JSON callers get the transition outcome alone; no stage reads.
    assert not any("/retrograde/status" in request[1] for request in scenario.requests)
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


@pytest.mark.parametrize("seed", [True, False], ids=["seed", "continuation"])
@pytest.mark.parametrize(
    ("result", "endpoint", "body", "expected_status"),
    [
        ("response_timeout", "status", None, "timeout"),
        ("complete", "status", b'{"status":', "invalid_response"),
        ("complete", "status", b"[]", "invalid_response"),
        ("complete", "status", b'{"status": []}', "invalid_response"),
        ("complete", "status", b"{}", "invalid_response"),
        ("complete", "state", b'{"storyteller_text":', "invalid_response"),
        ("complete", "state", b"null", "invalid_response"),
        ("complete", "state", b'{"has_pending": "false"}', "invalid_response"),
        ("complete", "state", b'{"current_chunk_id": true}', "invalid_response"),
        ("complete", "state", b'{"choices": "Enter the gate."}', "invalid_response"),
    ],
    ids=[
        "http-timeout",
        "status-json",
        "status-array",
        "status-value",
        "missing-status",
        "state-json",
        "state-null",
        "state-flag",
        "state-chunk",
        "state-choices",
    ],
)
def test_generation_response_failures_keep_session_recovery(
    tmp_path: Path,
    seed: bool,
    result: str,
    endpoint: str,
    body: bytes | None,
    expected_status: str,
) -> None:
    """Transport and payload failures retain one session on both CLI paths."""

    scenario = GenerationScenario(result=result, seed=seed)
    setattr(scenario, f"{endpoint}_body", body)
    code, stdout, stderr = _run_cli(scenario, tmp_path)
    assert code == 1, (stdout, stderr)
    assert stdout == ""
    assert "Traceback" not in stderr
    payload = json.loads(stderr)
    assert payload["success"] is False
    assert payload["session_id"] == SESSION_ID
    assert payload["generation_error"]["status"] == expected_status
    assert payload["generation_error"]["detail"]
    assert payload["recovery_command"] == "nexus load --slot 5"
    assert scenario.status_reads == (2 if endpoint == "state" else 1)
    assert scenario.state_reads == (2 if endpoint == "state" else 1)
    assert (
        sum(
            request[:2] == ("POST", "/api/narrative/continue")
            for request in scenario.requests
        )
        == 1
    )
    if seed:
        assert payload["artifact_data"] == {"title": "The Glass Orchard"}
        assert payload["retrograde"] == {"status": "complete"}
        assert payload["narrative_bootstrap"] is False
        assert payload["bootstrap_error"]["session_id"] == SESSION_ID
        assert (
            payload["bootstrap_error"]["detail"]
            == payload["generation_error"]["detail"]
        )
        assert "next_phase_intro" not in payload


def _stage(name: str, **detail: Any) -> dict[str, Any]:
    """One gateway-shaped Retrograde status payload for slot 5."""

    return {"slot": 5, "stage": name, "detail": detail, "stages": []}


GENESIS_SCRIPT = [
    {"slot": 5, "stage": "idle", "stages": []},
    _stage("packet"),
    _stage("packet"),
    _stage("seed_candidates", weird="medium"),
    _stage("expansion", candidates=6, selected=3),
    _stage("expansion", candidates=6, selected=3),
    _stage("persistence"),
    _stage("embedding", pending_summaries=4),
    _stage("done", embedded_summaries=4),
]


def _stage_lines(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if line.startswith("Genesis stage")]


@pytest.mark.parametrize("ready", [False, True], ids=["seed-confirm", "ready-resume"])
def test_cli_prints_each_genesis_stage_once_while_transition_runs(
    tmp_path: Path, ready: bool
) -> None:
    """Human output names each Retrograde stage once, in order, then stops."""

    scenario = GenerationScenario(
        seed=not ready, ready=ready, stage_script=GENESIS_SCRIPT
    )
    code, stdout, stderr = _run_cli(scenario, tmp_path, json_output=False)
    assert code == 0, (stdout, stderr)
    assert stderr == ""
    assert _stage_lines(stdout) == [
        "Genesis stage: packet",
        "Genesis stage: seed_candidates",
        "Genesis stage: expansion",
        "Genesis stage: persistence",
        "Genesis stage: embedding",
        "Genesis stage: done",
    ]
    # "done" is terminal: the reader stopped on it, not on a later read.
    assert scenario.stage_reads == len(GENESIS_SCRIPT)
    assert NARRATIVE in stdout
    assert stdout.index("Genesis stage: done") < stdout.index(NARRATIVE)


def test_cli_prints_the_failed_genesis_stage_and_the_transition_error(
    tmp_path: Path,
) -> None:
    """A failure record names its stage once; the transition error stays loud."""

    scenario = GenerationScenario(
        stage_script=[
            _stage("packet"),
            _stage("expansion", candidates=6, selected=3),
            _stage("failed", stage="persistence"),
        ],
        transition_error="Retrograde persistence blocked: 2 unresolved refs",
    )
    code, stdout, stderr = _run_cli(scenario, tmp_path, json_output=False)
    assert code == 1, (stdout, stderr)
    assert _stage_lines(stdout) == [
        "Genesis stage: packet",
        "Genesis stage: expansion",
        "Genesis stage: failed (persistence)",
    ]
    assert scenario.stage_reads == 3
    assert "the narrative transition failed" in stderr
    assert not any(
        request[:2] == ("POST", "/api/narrative/continue")
        for request in scenario.requests
    )


def test_cli_reports_an_unreadable_genesis_stage_and_keeps_the_transition(
    tmp_path: Path,
) -> None:
    """A failed stage read is reported once; the transition outcome stands."""

    scenario = GenerationScenario(stage_script=[_stage("packet")], stage_failure=True)
    code, stdout, stderr = _run_cli(scenario, tmp_path, json_output=False)
    assert code == 0, (stdout, stderr)
    assert _stage_lines(stdout) == []
    assert stderr.count("Genesis stage unavailable:") == 1
    assert "502" in stderr
    assert scenario.stage_reads == 1
    assert NARRATIVE in stdout
