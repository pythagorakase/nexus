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
    # Status reads answered before the transition was posted.
    snapshot_reads: int = 0
    scripted_reads: int = 0
    # Ordinals (from 0) of the status reads answered with a 502.
    failed_reads: set[int] = field(default_factory=set)
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
                scenario.transition_posted = True
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
                script = scenario.stage_script
                if not scenario.transition_posted:
                    scenario.snapshot_reads += 1
                    payload = scenario.stage_before
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
    wizard = config["orrery"]["retrograde"]["wizard"]
    wizard["status_poll_interval_seconds"] = scenario.stage_poll_seconds
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


@pytest.mark.parametrize("ready", [False, True], ids=["seed-confirm", "ready-resume"])
def test_cli_prints_each_genesis_stage_once_while_transition_runs(
    tmp_path: Path, ready: bool
) -> None:
    """Human output names each Retrograde stage once, in order, through done."""

    scenario = GenerationScenario(
        seed=not ready, ready=ready, stage_script=GENESIS_SCRIPT, stage_outcome=DONE
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
    assert scenario.snapshot_reads == 1
    assert scenario.stages_read[: len(scripted) + 1] == ["idle", *scripted]
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
    # One read before the post, one after the answer; no interval read.
    assert scenario.snapshot_reads == 1
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
