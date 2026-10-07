"""Qualify the public CLI generation protocol over a real loopback HTTP server.

The server serves gateway-shaped scheduling, durable-status, and slot-state
responses. CLI parsing, HTTP transport, polling, result validation, formatting,
exit codes, and interruption run in a subprocess; no slot or provider is used.
One seed-bootstrap case runs in process, to pass the scheduling POST a budget
short enough for a real stalled answer to trip it.
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

from nexus import cli
from nexus.cli_contract import ExitCode, exit_code_for, partial_fields

ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = "776-opening-session"
NARRATIVE = "Rain needles the orchard glass."
WELCOME = "A new story waits for its world."
WELCOME_CHOICES = ["Begin with a place.", "Begin with a person."]


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
    # Retrograde stage payloads served in order once the transition is posted,
    # which is held until the CLI has read them all; the last one repeats.
    # None serves no stage endpoint at all.
    stage_script: list[dict[str, Any]] | None = None
    # The record the gateway holds before the transition is posted: the
    # previous run's, or none. Reads after the post serve it too while no
    # scripted stage or recorded outcome replaces it.
    stage_before: dict[str, Any] = field(default_factory=lambda: dict(NO_RUN))
    # The terminal record the run leaves behind. Like the gateway, the
    # transition records it just before it answers; every later read serves it.
    stage_outcome: dict[str, Any] | None = None
    outcome_recorded: bool = False
    transition_posted: bool = False
    stage_poll_seconds: float = 0.02
    # The stage each status read served ("502" for a failed read).
    stages_read: list[str] = field(default_factory=list)
    # Status reads answered before the transition was posted: the CLI's
    # snapshot, plus any interval read its stage poller takes before the
    # transition POST is sent (the poller starts first).
    snapshot_reads: int = 0
    # The record each of those reads served. The gateway always serves
    # stage_before there, so this guards the fake gateway, not the CLI.
    snapshot_served: list[dict[str, Any]] = field(default_factory=list)
    # Interval reads the transition POST waits for before it counts as
    # received, which forces the early read a slow host can produce.
    interval_reads_before_post: int = 0
    pre_post_reads_seen: Event = field(default_factory=Event)
    scripted_reads: int = 0
    # Ordinals (from 0) of the status reads answered with a 502.
    failed_reads: set[int] = field(default_factory=set)
    stages_served: Event = field(default_factory=Event)
    transition_error: str | None = None
    # Detail of a refused strangeness save; None echoes the saved level.
    weird_error: str | None = None
    # The slot holds nothing until the CLI starts a wizard on it.
    empty: bool = False
    wizard_started: bool = False
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

        def _stall_after_headers(self, payload: dict[str, Any]) -> None:
            """Send the headers and half the body, then hold the rest back."""
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body[: len(body) // 2])
            scenario.release_response.wait(timeout=10)
            self.close_connection = True

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            scenario.requests.append(("POST", self.path, body))
            if body.get("slot") != 5:
                self._respond({"detail": "Explicit test slot required"}, 422)
            elif self.path == "/api/story/new/setup/start":
                scenario.wizard_started = True
                self._respond(
                    {
                        "status": "started",
                        "thread_id": "conv_new_story",
                        "slot": 5,
                        "model": "slot-model",
                        "welcome_message": WELCOME,
                        "welcome_choices": WELCOME_CHOICES,
                    }
                )
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
                if scenario.interval_reads_before_post:
                    assert scenario.pre_post_reads_seen.wait(
                        timeout=10
                    ), "interval read never arrived"
                scenario.transition_posted = True
                if scenario.result == "transition_drop":
                    # The gateway dies while transitioning: no answer at all.
                    self.close_connection = True
                    return
                if scenario.result == "transition_stall":
                    # The answer stops after its headers until teardown.
                    self._stall_after_headers({"retrograde": {"status": "complete"}})
                    return
                if scenario.stage_script:
                    # Hold the transition like a live Retrograde run until the
                    # CLI has read every scripted stage.
                    assert scenario.stages_served.wait(timeout=10), "stages unread"
                if scenario.stage_outcome is not None:
                    scenario.outcome_recorded = True
                if scenario.transition_error is not None:
                    self._respond({"detail": scenario.transition_error}, 400)
                    return
                scenario.transitioned = True
                self._respond({"retrograde": {"status": "complete"}})
            elif self.path == "/api/narrative/continue":
                if scenario.result == "schedule_error":
                    self._respond({"detail": "Opening generation unavailable"}, 503)
                    return
                if scenario.result == "schedule_drop":
                    # The gateway dies while scheduling: no answer at all.
                    self.close_connection = True
                    return
                if scenario.result == "schedule_stall":
                    # The answer stops after its headers until teardown.
                    self._stall_after_headers({"session_id": SESSION_ID})
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

        def do_PUT(self) -> None:  # noqa: N802 - stdlib handler contract
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            scenario.requests.append(("PUT", self.path, body))
            if body.get("slot") != 5:
                self._respond({"detail": "Explicit test slot required"}, 422)
            elif self.path == "/api/story/new/weird":
                if scenario.weird_error is not None:
                    self._respond({"detail": scenario.weird_error}, 409)
                    return
                self._respond(
                    {
                        "status": "recorded",
                        "slot": 5,
                        "weird_level": body["weird_level"],
                    }
                )
            else:
                self._respond({"detail": f"Unexpected PUT {self.path}"}, 404)

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
                script = scenario.stage_script
                if not scenario.transition_posted:
                    scenario.snapshot_reads += 1
                    payload = scenario.stage_before
                    scenario.snapshot_served.append(payload)
                    if (
                        scenario.snapshot_reads
                        >= 1 + scenario.interval_reads_before_post
                    ):
                        scenario.pre_post_reads_seen.set()
                elif scenario.outcome_recorded and scenario.stage_outcome:
                    payload = scenario.stage_outcome
                elif script:
                    index = scenario.scripted_reads
                    scenario.scripted_reads += 1
                    payload = script[min(index, len(script) - 1)]
                    # Chosen before the release, so the last scripted read is
                    # not answered with the outcome the released transition
                    # records.
                    if index + 1 >= len(script):
                        scenario.stages_served.set()
                else:
                    payload = scenario.stage_before
                failed = len(scenario.stages_read) in scenario.failed_reads
                scenario.stages_read.append("502" if failed else payload["stage"])
                if failed:
                    self._respond({"detail": "Gateway worker restarted"}, 502)
                    return
                self._respond(payload)
            elif url.path == f"/api/narrative/status/{SESSION_ID}":
                scenario.status_reads += 1
                scenario.waiting.set()
                if parse_qs(url.query) != {"slot": ["5"]}:
                    self._respond({"detail": "Explicit test slot required"}, 422)
                    return
                if scenario.result == "status_error":
                    self._respond({"detail": "Status unavailable"}, 503)
                    return
                if scenario.result == "status_drop" and scenario.status_reads == 2:
                    # The gateway dies mid-wait: the second read gets no answer.
                    self.close_connection = True
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
                if scenario.empty and not scenario.wizard_started:
                    self._respond(
                        {
                            "slot": 5,
                            "is_empty": True,
                            "is_wizard_mode": False,
                            "model": "slot-model",
                        }
                    )
                elif scenario.ready and not scenario.transitioned:
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
    scenario: GenerationScenario,
    tmp_path: Path,
    *,
    json_output: bool = True,
    choice: str | None = "1",
    extra_args: tuple[str, ...] = (),
) -> tuple[int, str, str]:
    """Run the actual command against this isolated gateway and config."""

    config: Any = tomlkit.parse((ROOT / "nexus.toml").read_text())
    config["apex"]["generation_timeout_seconds"] = (
        1 if scenario.result in {"timeout", "response_timeout"} else 5
    )
    wizard = config["orrery"]["retrograde"]["wizard"]
    wizard["status_poll_interval_seconds"] = scenario.stage_poll_seconds
    if scenario.result == "transition_stall":
        # The stalled answer trips a 1 s transition budget, not the shipped one.
        wizard["transition_timeout_seconds"] = 1
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
                *(["--choice", choice] if choice is not None else []),
                *extra_args,
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
    envelope = json.loads(stderr)
    # A non-2xx answer while scheduling, waiting or loading is api_error.
    code = (
        "api_error"
        if outcome in {"schedule_error", "status_error", "load_error"}
        else "domain_failure"
    )
    assert (envelope["ok"], envelope["code"]) == (False, code)
    payload = envelope["partial"]
    assert payload["narrative_bootstrap"] is False
    assert payload["artifact_data"] == {"title": "The Glass Orchard"}
    assert payload["retrograde"] == {"status": "complete"}
    # The transition left wizard mode: the seed phase is not preserved.
    assert "phase" not in payload
    assert payload["bootstrap_error"]["detail"]
    assert payload["recovery_command"] == "nexus load --slot 5"
    assert payload["recovery_command"] in envelope["error"]
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


@pytest.mark.parametrize("outcome", ["schedule_drop", "status_drop"])
def test_seed_bootstrap_lost_gateway_is_unreachable_and_keeps_the_seed(
    tmp_path: Path, outcome: str
) -> None:
    """A gateway lost during the opening turn exits 4 with the seed in partial."""

    scenario = GenerationScenario(result=outcome)
    code, stdout, stderr = _run_cli(scenario, tmp_path)
    assert code == 4, (stdout, stderr)
    assert stdout == ""
    assert "Traceback" not in stderr
    envelope = json.loads(stderr)
    assert (envelope["ok"], envelope["code"]) == (False, "api_unreachable")
    assert "Cannot connect to API server at " in envelope["error"]
    payload = envelope["partial"]
    assert payload["narrative_bootstrap"] is False
    assert payload["artifact_data"] == {"title": "The Glass Orchard"}
    assert payload["retrograde"] == {"status": "complete"}
    assert payload["bootstrap_error"]["detail"].startswith(
        "Cannot connect to API server at "
    )
    assert payload["recovery_command"] == "nexus load --slot 5"
    assert payload["recovery_command"] in envelope["error"]
    assert "next_phase_intro" not in payload
    if outcome == "status_drop":
        assert payload["bootstrap_error"]["session_id"] == SESSION_ID
        assert payload["session_id"] == SESSION_ID
        assert payload["generation_error"]["status"] == "unreachable"
        assert scenario.status_reads == 2
    else:
        assert "session_id" not in payload
        assert scenario.status_reads == 0
    assert (
        sum(
            request[:2] == ("POST", "/api/narrative/continue")
            for request in scenario.requests
        )
        == 1
    )


def test_seed_bootstrap_schedule_stalled_after_headers_keeps_the_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scheduling answer that stalls after its headers is exit 1, seed kept.

    Requests reports the stalled body as a ConnectionError wrapping urllib3's
    ReadTimeoutError. The opening turn classifies it with the waiter's helper
    as a timeout, a domain failure, not a lost gateway (exit 4). The request
    and the stall are real; only the POST's 120 s budget is passed as 0.5 s.
    """
    scenario = GenerationScenario(result="schedule_stall")
    saved = {
        "success": True,
        "phase": "seed",
        "artifact_data": {"title": "The Glass Orchard"},
        "retrograde": {"status": "complete"},
    }
    monkeypatch.delenv("NEXUS_RUNTIME_CONFIG", raising=False)
    monkeypatch.delenv("NEXUS_HOME", raising=False)
    with _gateway(scenario) as base_url:
        monkeypatch.setenv("NEXUS_API_URL", base_url)
        result = cli._bootstrap_seed_narrative(
            result=saved, slot=5, model=None, schedule_timeout=0.5
        )

    assert result["success"] is False
    # main() exits with the result's code, domain_failure when it names none.
    code = result.get("code", "domain_failure")
    assert (code, exit_code_for(code)) == ("domain_failure", ExitCode.DOMAIN_FAILURE)
    detail = result["bootstrap_error"]["detail"]
    assert detail.startswith(f"Timed out waiting for API server at {base_url}: ")
    assert "Read timed out" in detail
    assert result["error"] == (
        "The seed was saved and the story initialized, but the opening "
        f"narrative could not be loaded: {detail}. Inspect with: nexus load --slot 5"
    )
    # The partial main() prints: the saved seed, and no session to recover.
    assert partial_fields(result) == {
        "artifact_data": {"title": "The Glass Orchard"},
        "retrograde": {"status": "complete"},
        "narrative_bootstrap": False,
        "bootstrap_error": {"detail": detail, "session_id": None},
        "recovery_command": "nexus load --slot 5",
    }
    assert scenario.status_reads == 0
    assert [request[:2] for request in scenario.requests] == [
        ("POST", "/api/narrative/continue")
    ]


@pytest.mark.parametrize("outcome", ["transition_stall", "transition_drop"])
def test_seed_transition_stalled_after_headers_keeps_the_seed(
    tmp_path: Path, outcome: str
) -> None:
    """A transition answer that stalls after its headers is exit 1, seed kept.

    Requests reports the stalled body as a ConnectionError wrapping urllib3's
    ReadTimeoutError. The transition classifies it with the waiter's helper as
    its timeout; a transition POST the gateway drops is a lost gateway (exit
    4). Either way the saved seed and its retry command stay in ``partial``.
    """
    exit_code, error_code, status = {
        "transition_stall": (1, "domain_failure", "timeout"),
        "transition_drop": (4, "api_unreachable", "unreachable"),
    }[outcome]
    scenario = GenerationScenario(result=outcome)
    code, stdout, stderr = _run_cli(scenario, tmp_path)
    assert code == exit_code, (stdout, stderr)
    assert stdout == ""
    assert "Traceback" not in stderr
    envelope = json.loads(stderr)
    assert (envelope["ok"], envelope["code"]) == (False, error_code)
    assert envelope["error"] == (
        "Seed artifact was saved, but the narrative transition failed. "
        "Retry with: nexus continue --slot 5"
    )
    payload = envelope["partial"]
    assert payload["artifact_type"] == "story_seed"
    assert payload["artifact_data"] == {"title": "The Glass Orchard"}
    assert payload["retry_command"] == "nexus continue --slot 5"
    failure = payload["transition_error"]
    assert (failure["status"], failure["status_code"]) == (status, None)
    if outcome == "transition_drop":
        assert failure["detail"].startswith("Cannot connect to API server at ")
    else:
        assert failure["detail"].endswith("Read timed out.")
    assert "retrograde" not in payload
    assert scenario.transition_posted
    # The failed transition schedules no opening turn.
    assert not any(
        request[:2] == ("POST", "/api/narrative/continue")
        for request in scenario.requests
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
    envelope = json.loads(stderr)
    assert (envelope["ok"], envelope["code"]) == (False, "domain_failure")
    payload = envelope["partial"]
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


PREVIOUS_RUN = "run-before-this-transition"
THIS_RUN = "run-of-this-transition"


def _stage(name: str, *, run: str = THIS_RUN, **detail: Any) -> dict[str, Any]:
    """One gateway-shaped Retrograde status payload for slot 5."""

    return {"slot": 5, "run": run, "stage": name, "detail": detail, "stages": []}


# No run has started for the slot in this gateway process.
NO_RUN: dict[str, Any] = {"slot": 5, "run": None, "stage": "idle", "stages": []}
# This transition's run, reset and not yet at its first stage.
IDLE: dict[str, Any] = {"slot": 5, "run": THIS_RUN, "stage": "idle", "stages": []}
GENESIS_SCRIPT = [
    IDLE,
    _stage("packet"),
    _stage("packet"),
    _stage("seed_candidates", weird="medium"),
    _stage("expansion", candidates=6, selected=3),
    _stage("expansion", candidates=6, selected=3),
    _stage("persistence"),
    _stage("embedding", pending_summaries=4),
]
DONE = _stage("done", embedded_summaries=4)
PERSISTENCE_FAILED = _stage("failed", stage="persistence")
PREVIOUS_RUN_FAILED = _stage("failed", run=PREVIOUS_RUN, stage="persistence")
# Slow enough that no interval read follows the transition's answer: only the
# read taken after the answer can see the outcome recorded just before it.
ANSWER_ONLY_POLL_SECONDS = 0.25
# Longer than any test: the transition answers before the first interval read.
NO_INTERVAL_READ_SECONDS = 60.0


def _stage_lines(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if line.startswith("Genesis stage")]


# "unforced" (0) leaves the order of reads and the post to the host's timing,
# so early reads are still possible there.
@pytest.mark.parametrize(
    "interval_reads_before_post", [0, 1], ids=["unforced", "interval-read-first"]
)
@pytest.mark.parametrize("ready", [False, True], ids=["seed-confirm", "ready-resume"])
def test_cli_prints_each_genesis_stage_once_while_transition_runs(
    tmp_path: Path, ready: bool, interval_reads_before_post: int
) -> None:
    """Human output names each Retrograde stage once, in order, through done."""

    scenario = GenerationScenario(
        seed=not ready,
        ready=ready,
        stage_script=GENESIS_SCRIPT,
        stage_outcome=DONE,
        interval_reads_before_post=interval_reads_before_post,
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
    scripted = [payload["stage"] for payload in GENESIS_SCRIPT]
    # The stage poller starts before the transition is posted, so an interval
    # read can precede the post; each such read serves the previous record.
    # "interval-read-first" holds the post until one has been answered.
    before = scenario.snapshot_reads
    assert before >= 1 + interval_reads_before_post
    # A guard on the fake gateway: it serves stage_before to every such read.
    assert scenario.snapshot_served == [scenario.stage_before] * before
    assert scenario.stages_read[: before + len(scripted)] == [
        *(["idle"] * before),
        *scripted,
    ]
    # "done" is terminal: it is read once, and no read follows it.
    assert scenario.stages_read.count("done") == 1
    assert scenario.stages_read[-1] == "done"
    assert NARRATIVE in stdout
    assert stdout.index("Genesis stage: done") < stdout.index(NARRATIVE)


def test_cli_stops_reading_at_a_finished_stage_read_before_the_answer(
    tmp_path: Path,
) -> None:
    """A "done" read while the transition is in flight ends the reads."""

    scenario = GenerationScenario(stage_script=[IDLE, _stage("packet"), DONE])
    code, stdout, stderr = _run_cli(scenario, tmp_path, json_output=False)
    assert code == 0, (stdout, stderr)
    assert _stage_lines(stdout) == ["Genesis stage: packet", "Genesis stage: done"]
    assert scenario.stages_read == ["idle", "idle", "packet", "done"]


def test_cli_prints_the_failed_genesis_stage_and_the_transition_error(
    tmp_path: Path,
) -> None:
    """The failure recorded as the transition answers is named once."""

    scenario = GenerationScenario(
        stage_script=[_stage("packet"), _stage("expansion", candidates=6, selected=3)],
        stage_outcome=PERSISTENCE_FAILED,
        stage_poll_seconds=ANSWER_ONLY_POLL_SECONDS,
        transition_error="Retrograde persistence blocked: 2 unresolved refs",
    )
    code, stdout, stderr = _run_cli(scenario, tmp_path, json_output=False)
    assert code == 1, (stdout, stderr)
    assert _stage_lines(stdout) == [
        "Genesis stage: packet",
        "Genesis stage: expansion",
        "Genesis stage: failed (persistence)",
    ]
    assert scenario.stages_read == ["idle", "packet", "expansion", "failed"]
    assert "the narrative transition failed" in stderr
    assert not any(
        request[:2] == ("POST", "/api/narrative/continue")
        for request in scenario.requests
    )


def test_cli_reads_past_the_previous_runs_failure_record(tmp_path: Path) -> None:
    """A retry's reads can precede its reset; the old failure is not news."""

    scenario = GenerationScenario(
        stage_before=PREVIOUS_RUN_FAILED,
        stage_script=[
            PREVIOUS_RUN_FAILED,
            IDLE,
            _stage("packet"),
        ],
        stage_outcome=DONE,
    )
    code, stdout, stderr = _run_cli(scenario, tmp_path, json_output=False)
    assert code == 0, (stdout, stderr)
    assert _stage_lines(stdout) == ["Genesis stage: packet", "Genesis stage: done"]
    assert scenario.stages_read[:4] == ["failed", "failed", "idle", "packet"]
    assert scenario.stages_read[-1] == "done"


@pytest.mark.parametrize(
    "before",
    [NO_RUN, _stage("done", run=PREVIOUS_RUN, embedded_summaries=2)],
    ids=["no-previous-run", "previous-run-done"],
)
def test_cli_prints_a_terminal_stage_recorded_before_its_first_interval_read(
    tmp_path: Path, before: dict[str, Any]
) -> None:
    """A run whose first record the CLI sees is terminal still names its stage.

    The transition fails before the first interval read, so only the read
    after its answer sees this run; the run identity read before the post
    marks that "failed" record as this run's, not the previous run's.
    """

    scenario = GenerationScenario(
        stage_before=before,
        stage_script=[],
        stage_outcome=PERSISTENCE_FAILED,
        stage_poll_seconds=NO_INTERVAL_READ_SECONDS,
        transition_error="Retrograde persistence blocked: 2 unresolved refs",
    )
    code, stdout, stderr = _run_cli(scenario, tmp_path, json_output=False)
    assert code == 1, (stdout, stderr)
    assert _stage_lines(stdout) == ["Genesis stage: failed (persistence)"]
    # The snapshot count is loosened to match the genesis-stage test; at this
    # 60 s interval the exact stages_read below still pins one read before the
    # post and one after the answer, with no interval read.
    assert scenario.snapshot_reads >= 1
    assert scenario.snapshot_served == [before] * scenario.snapshot_reads
    assert scenario.stages_read == [before["stage"], "failed"]
    assert "the narrative transition failed" in stderr


def test_cli_names_no_stage_when_the_transition_is_refused_before_it_runs(
    tmp_path: Path,
) -> None:
    """A refused transition leaves the previous run's record; none is printed."""

    scenario = GenerationScenario(
        stage_before=PREVIOUS_RUN_FAILED,
        stage_script=[PREVIOUS_RUN_FAILED],
        stage_poll_seconds=ANSWER_ONLY_POLL_SECONDS,
        transition_error="Confirm the setting and character before starting the story.",
    )
    code, stdout, stderr = _run_cli(scenario, tmp_path, json_output=False)
    assert code == 1, (stdout, stderr)
    assert _stage_lines(stdout) == []
    # One read before the post, one while it was held, one after it answered.
    assert scenario.stages_read == ["failed", "failed", "failed"]
    assert "the narrative transition failed" in stderr


@pytest.mark.parametrize(
    ("script", "failed_read", "read"),
    [([], 0, ["502"]), ([_stage("packet")], 1, ["idle", "502"])],
    ids=["before-the-post", "while-in-flight"],
)
def test_cli_reports_an_unreadable_genesis_stage_and_keeps_the_transition(
    tmp_path: Path, script: list[dict[str, Any]], failed_read: int, read: list[str]
) -> None:
    """A failed stage read is reported once; the transition outcome stands."""

    scenario = GenerationScenario(
        stage_script=script, stage_outcome=DONE, failed_reads={failed_read}
    )
    code, stdout, stderr = _run_cli(scenario, tmp_path, json_output=False)
    assert code == 0, (stdout, stderr)
    assert _stage_lines(stdout) == []
    assert stderr.count("Genesis stage unavailable:") == 1
    assert "502" in stderr
    # No read follows the failed one, not even after the transition answers.
    assert scenario.stages_read == read
    assert NARRATIVE in stdout


def _writes(scenario: GenerationScenario) -> list[tuple[str, str, dict[str, Any]]]:
    return [request for request in scenario.requests if request[0] != "GET"]


def _transition_bodies(scenario: GenerationScenario) -> list[dict[str, Any]]:
    return [
        request[2]
        for request in scenario.requests
        if request[:2] == ("POST", "/api/story/new/transition")
    ]


@pytest.mark.parametrize("ready", [False, True], ids=["seed-confirm", "ready-resume"])
def test_cli_weird_saves_the_level_then_posts_it_with_the_transition(
    tmp_path: Path, ready: bool
) -> None:
    """--weird is saved before any wizard step and rides the transition."""

    scenario = GenerationScenario(seed=not ready, ready=ready)
    code, stdout, stderr = _run_cli(scenario, tmp_path, extra_args=("--weird", "high"))
    assert code == 0, (stdout, stderr)
    assert _writes(scenario)[0] == (
        "PUT",
        "/api/story/new/weird",
        {"slot": 5, "weird_level": "high"},
    )
    assert _transition_bodies(scenario) == [{"slot": 5, "weird_level": "high"}]
    payload = json.loads(stdout)
    assert payload["success"] is True
    assert payload["session_id"] == SESSION_ID


def test_cli_without_weird_leaves_the_stored_level_in_charge(tmp_path: Path) -> None:
    scenario = GenerationScenario()
    code, stdout, stderr = _run_cli(scenario, tmp_path)
    assert code == 0, (stdout, stderr)
    assert not any(request[0] == "PUT" for request in scenario.requests)
    assert _transition_bodies(scenario) == [{"slot": 5}]


def test_cli_rejects_weird_for_a_story_in_narrative_mode(tmp_path: Path) -> None:
    scenario = GenerationScenario(seed=False)
    code, stdout, stderr = _run_cli(scenario, tmp_path, extra_args=("--weird", "low"))
    assert code == 1, (stdout, stderr)
    assert stdout == ""
    assert json.loads(stderr) == {
        "ok": False,
        "code": "domain_failure",
        "error": (
            "--weird applies only to a new story; slot 5 already holds a story "
            "in narrative mode."
        ),
        "partial": {},
    }
    assert _writes(scenario) == []


def test_cli_stops_when_the_wizard_refuses_the_weird_level(tmp_path: Path) -> None:
    scenario = GenerationScenario(
        weird_error="The wizard changed while this response was being generated."
    )
    code, stdout, stderr = _run_cli(
        scenario, tmp_path, extra_args=("--weird", "medium")
    )
    assert code == 1, (stdout, stderr)
    error = json.loads(stderr)["error"]
    assert error.startswith("Failed to save --weird medium: ")
    assert "The wizard changed while this response was being generated." in error
    # No wizard step or transition follows a refused save.
    assert [request[:2] for request in _writes(scenario)] == [
        ("PUT", "/api/story/new/weird")
    ]


def test_cli_weird_on_an_empty_slot_starts_the_wizard_then_saves_the_level(
    tmp_path: Path,
) -> None:
    """On an empty slot, --weird is saved on the wizard the call starts."""

    scenario = GenerationScenario(empty=True)
    code, stdout, stderr = _run_cli(
        scenario, tmp_path, choice=None, extra_args=("--weird", "high")
    )
    assert code == 0, (stdout, stderr)
    # Starting the wizard is this call's step: the level is saved on it at once,
    # and the call ends at the welcome, before any wizard turn or transition.
    assert scenario.requests == [
        ("GET", "/api/slot/5/state", {}),
        ("POST", "/api/story/new/setup/start", {"slot": 5}),
        ("PUT", "/api/story/new/weird", {"slot": 5, "weird_level": "high"}),
    ]
    assert json.loads(stdout) == {
        "success": True,
        "message": WELCOME,
        "choices": WELCOME_CHOICES,
        "phase": "setting",
        "model": "slot-model",
    }


def test_cli_stops_when_the_new_wizard_refuses_the_weird_level(
    tmp_path: Path,
) -> None:
    """A refused save on the wizard the call just started ends the call."""

    scenario = GenerationScenario(
        empty=True, weird_error="No new-story wizard is in progress for slot 5."
    )
    code, stdout, stderr = _run_cli(
        scenario, tmp_path, choice=None, extra_args=("--weird", "low")
    )
    assert code == 1, (stdout, stderr)
    assert stdout == ""
    error = json.loads(stderr)["error"]
    assert error.startswith("Failed to save --weird low: ")
    assert "No new-story wizard is in progress for slot 5." in error
    assert [request[:2] for request in _writes(scenario)] == [
        ("POST", "/api/story/new/setup/start"),
        ("PUT", "/api/story/new/weird"),
    ]
