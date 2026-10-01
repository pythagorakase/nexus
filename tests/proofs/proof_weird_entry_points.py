"""Zero-spend entry-point proof for the genesis strangeness selection (#838).

Two real entry points carry the player's strangeness level to the transition
against a real gateway, a real PostgreSQL clone, and the real built client:

- ``nexus continue --weird high`` walks the TEST wizard from an empty slot to
  the transition; every call saves the level and the transition carries it.
- Chromium clicks the three Introduction glyphs; each shows pressed only once
  the gateway saved it, a reload keeps the stored level, Confirm is held while
  a save is in flight, and the transition carries the last saved level.

The gateway is ``narrative.app`` behind ``StrangenessRequestRecorder``, which
records the strangeness save and transition requests and responses without
changing a byte. The lane is ``NEXUS_GATEWAY_PORT`` (required; never 8002):
the 8012 nightly-QA lane when the QA kit is idle, otherwise the first free
port from 8014 upward that is not a suite lane (8015, then 8020 and up). Each
story is a disposable ``qa640_838_`` template clone routed as slot 4; no owner
slot is read or written. Every model call goes to the TEST provider through a
private mock server, so the proof makes no paid call. Evidence files are
written to the test's temporary directory; set ``NEXUS_PROOF_EXPORT_EVIDENCE=1``
to write them into the tracked ``docs/qa/838-entry-points`` instead.
"""

from collections.abc import Iterator
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any

from playwright.sync_api import expect, sync_playwright
import pytest
import requests  # type: ignore[import-untyped]
import uvicorn

from nexus.api import narrative
from nexus.telemetry import usage
from tests.pg_fixtures import connect, disposable_slot_database
from tests.scheduler_helpers import (
    require_private_runtime_config,
    route_slot,
    run_cli,
    test_provider_config as configure_test,
)
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401

pytestmark = pytest.mark.requires_postgres

LANE_ENV = "NEXUS_GATEWAY_PORT"
OWNER_GATEWAY_PORT = 8002
EXPORT_ENV = "NEXUS_PROOF_EXPORT_EVIDENCE"
_REPO = Path(__file__).resolve().parents[2]
TRACKED_EVIDENCE = _REPO / "docs/qa/838-entry-points"
BUILT_CLIENT = _REPO / "ui/dist/public/index.html"
SLOT = 4
LEVELS = ("low", "medium", "high")
# Proof parameters, not runtime settings: the most CLI steps either walk may
# take, and how long a gateway start, a UI state, or a transition may take.
MAX_WIZARD_STEPS = 12
GATEWAY_START_SECONDS = 30
GATEWAY_STOP_SECONDS = 60
UI_WAIT_MS = 60_000
TRANSITION_WAIT_SECONDS = 120
SKIPPED_RETROGRADE = {"enabled": False, "skip_reason": "mock_wizard_model"}
RECORDED_ROUTES = frozenset(
    {("PUT", "/api/story/new/weird"), ("POST", "/api/story/new/transition")}
)


def require_zero_spend_lane() -> int:
    """Check the proof's guards and return its gateway lane.

    Raises:
        RuntimeError: when ``NEXUS_GATEWAY_PORT`` is unset or names the owner's
            gateway, or when the session could reach a paid provider.
    """
    raw = os.environ.get(LANE_ENV)
    if not raw:
        raise RuntimeError(f"{LANE_ENV} is unset; the order assigns the lane")
    lane = int(raw)
    if lane == OWNER_GATEWAY_PORT:
        raise RuntimeError(f"{LANE_ENV}={lane} is the owner's gateway")
    if os.environ.get("NEXUS_TEST_PROVIDER_ONLY") != "1":
        raise RuntimeError("NEXUS_TEST_PROVIDER_ONLY must be 1: no paid call")
    if os.environ.get("NEXUS_RUN_LIVE_LLM") == "1":
        raise RuntimeError("NEXUS_RUN_LIVE_LLM=1 would allow a paid call")
    if not BUILT_CLIENT.is_file():
        pytest.fail(
            f"{BUILT_CLIENT} is missing: "
            "run npm --prefix ui ci && npm --prefix ui run build first"
        )
    return lane


def evidence_dir(tmp_path: Path) -> Path:
    """Where evidence lands: a temporary directory unless export is requested."""
    export = os.environ.get(EXPORT_ENV)
    if export not in (None, "", "0", "1"):
        raise ValueError(f"{EXPORT_ENV} must be 1 or 0, got {export!r}")
    if export == "1":
        TRACKED_EVIDENCE.mkdir(parents=True, exist_ok=True)
        return TRACKED_EVIDENCE
    directory = tmp_path / "838-entry-points"
    directory.mkdir()
    return directory


class StrangenessRequestRecorder:
    """An ASGI wrapper that records the strangeness requests it passes through.

    For ``PUT /api/story/new/weird`` and ``POST /api/story/new/transition`` it
    reads the whole request body, hands the same messages to the app, passes
    every response message through unchanged, and then appends ``{"method",
    "path", "request", "status", "response"}`` with both bodies parsed as
    JSON. Every other scope, lifespan included, reaches the app untouched.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self.records: list[dict[str, Any]] = []

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        """Serve one ASGI connection, recording it when its route is watched."""
        if (
            scope["type"] != "http"
            or (scope["method"], scope["path"]) not in RECORDED_ROUTES
        ):
            await self.app(scope, receive, send)
            return
        received: list[Any] = []
        while True:
            message = await receive()
            received.append(message)
            if message["type"] != "http.request" or not message.get("more_body"):
                break
        request_body = b"".join(
            message.get("body", b"")
            for message in received
            if message["type"] == "http.request"
        )
        pending = list(received)

        async def replay() -> Any:
            if pending:
                return pending.pop(0)
            return await receive()

        status: list[int] = []
        response_body: list[bytes] = []

        async def forward(message: Any) -> None:
            if message["type"] == "http.response.start":
                status.append(message["status"])
            elif message["type"] == "http.response.body":
                response_body.append(message.get("body", b""))
            await send(message)

        await self.app(scope, replay, forward)
        self.records.append(
            {
                "method": scope["method"],
                "path": scope["path"],
                "request": json.loads(request_body),
                "status": status[0],
                "response": json.loads(b"".join(response_body)),
            }
        )


@contextmanager
def _recorded_gateway(
    monkeypatch: pytest.MonkeyPatch, lane: int
) -> Iterator[StrangenessRequestRecorder]:
    """Serve the recorded real gateway on ``lane``, then stop only it.

    It closes with ``nexus down`` under the private runtime config, which it
    requires before it binds and again before that ``down``.
    """
    require_private_runtime_config()
    check = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{lane}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    assert check.returncode == 1, check.stdout + check.stderr
    recorder = StrangenessRequestRecorder(narrative.app)
    server = uvicorn.Server(
        uvicorn.Config(recorder, host="127.0.0.1", port=lane, log_level="warning")
    )
    thread = threading.Thread(target=server.run)
    thread.start()
    try:
        deadline = time.monotonic() + GATEWAY_START_SECONDS
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started, f"Gateway {lane} failed to start"
        yield recorder
    finally:
        server.should_exit = True
        thread.join(timeout=GATEWAY_STOP_SECONDS)
        assert not thread.is_alive(), f"Gateway {lane} did not shut down"
        require_private_runtime_config()
        run_cli(monkeypatch, "down")


def read_clone(dbname: str, label: str, reads: list[dict[str, Any]]) -> dict:
    """Read the clone's stored strangeness and genesis record into ``reads``."""
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT weird_level FROM assets.new_story_creator")
        rows = cur.fetchall()
        cur.execute("SELECT count(*) FROM assets.new_story_creator")
        (count,) = cur.fetchone()
        cur.execute("SELECT genesis_weird FROM global_variables")
        (genesis_weird,) = cur.fetchone()
    item = {
        "label": label,
        "weird_level": rows[0][0] if rows else "no row",
        "new_story_creator_rows": count,
        "genesis_weird": genesis_weird,
    }
    reads.append(item)
    print(json.dumps(item), flush=True)
    return item


def slot_state(base: str) -> dict[str, Any]:
    """Read the gateway's slot state for the routed slot."""
    response = requests.get(f"{base}/api/slot/{SLOT}/state", timeout=60)
    response.raise_for_status()
    return response.json()


def transcribed_cli(
    monkeypatch: pytest.MonkeyPatch, transcript: list[str], *args: str
) -> str:
    """Run one CLI call through ``run_cli`` and keep it for the transcript."""
    output = run_cli(monkeypatch, *args)
    transcript.append(f"$ nexus {' '.join(args)}\n{output}")
    return output


def configure_zero_spend(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route every provider consumer to the TEST provider's private mock."""
    configure_test(tmp_path, "http://127.0.0.1:1", monkeypatch)
    # Start the mock with this private config already in its environment.
    provider = request.getfixturevalue("mock_openai_server")
    configure_test(tmp_path, provider, monkeypatch)


def write_json(path: Path, value: Any) -> None:
    """Write ``value`` as indented JSON."""
    path.write_text(json.dumps(value, indent=2) + "\n")


def record_usage(evidence: Path, key: str) -> list[dict[str, Any]]:
    """Record this test's provider usage events; every one must name TEST."""
    usage_dir = usage._get_recorder_config().usage_dir
    events = [
        json.loads(line)
        for path in sorted(usage_dir.glob("*.jsonl"))
        for line in path.read_text().splitlines()
    ]
    assert all(event["model"] == "TEST" for event in events), events
    target = evidence / "provider-usage.json"
    recorded = json.loads(target.read_text()) if target.exists() else {}
    recorded[key] = events or "no usage events"
    write_json(target, recorded)
    return events


def assert_saves(
    records: list[dict[str, Any]], levels: list[str]
) -> list[dict[str, Any]]:
    """Assert the recorded saves are ``levels`` in order, each answered 200."""
    saves = [record for record in records if record["method"] == "PUT"]
    assert [save["request"] for save in saves] == [
        {"slot": SLOT, "weird_level": level} for level in levels
    ], saves
    assert all(save["status"] == 200 for save in saves), saves
    return saves


def assert_one_transition(records: list[dict[str, Any]], level: str) -> None:
    """Assert one transition, after the last save, carried ``level``."""
    transitions = [
        index for index, record in enumerate(records) if record["method"] == "POST"
    ]
    assert len(transitions) == 1, records
    (index,) = transitions
    last_save = max(
        position for position, record in enumerate(records) if record["method"] == "PUT"
    )
    assert index > last_save, records
    transition = records[index]
    assert transition["request"] == {"slot": SLOT, "weird_level": level}, transition
    assert transition["status"] == 200, transition
    assert transition["response"]["retrograde"] == SKIPPED_RETROGRADE, transition


def assert_transitioned_clone(dbname: str, label: str, reads: list[dict]) -> None:
    """The cache is cleared and Retrograde, skipped for TEST, recorded nothing."""
    after = read_clone(dbname, label, reads)
    assert after["new_story_creator_rows"] == 0, after
    assert after["weird_level"] == "no row", after
    assert after["genesis_weird"] is None, after


def test_cli_weird_high_walks_the_wizard_to_the_transition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """``--weird high`` is saved on every call and carried by the transition."""
    lane = require_zero_spend_lane()
    base = f"http://127.0.0.1:{lane}"
    evidence = evidence_dir(tmp_path)
    print(f"Lane {lane}; evidence directory {evidence}", flush=True)
    configure_zero_spend(tmp_path, request, monkeypatch)
    monkeypatch.setenv("NEXUS_API_URL", base)
    transcript: list[str] = []
    reads: list[dict[str, Any]] = []
    with disposable_slot_database("qa640_838_cli") as dbname:
        route_slot(monkeypatch, dbname)
        with _recorded_gateway(monkeypatch, lane) as recorder:
            try:
                transcribed_cli(
                    monkeypatch,
                    transcript,
                    "continue",
                    "--slot",
                    str(SLOT),
                    "--model",
                    "TEST",
                    "--weird",
                    "high",
                )
                started = read_clone(dbname, "after setup", reads)
                assert started["weird_level"] == "high", started
                state = slot_state(base)
                assert state["is_wizard_mode"] is True, state
                assert state["model"] == "TEST", state
                assert state["weird_level"] == "high", state
                calls = 1
                for step in range(1, MAX_WIZARD_STEPS + 1):
                    transcribed_cli(
                        monkeypatch,
                        transcript,
                        "continue",
                        "--slot",
                        str(SLOT),
                        "--accept-fate",
                        "--weird",
                        "high",
                    )
                    calls += 1
                    state = slot_state(base)
                    if not state["is_wizard_mode"]:
                        break
                    held = read_clone(dbname, f"after step {step}", reads)
                    assert held["weird_level"] == "high", held
                    assert state["weird_level"] == "high", state
                else:
                    pytest.fail(
                        f"{MAX_WIZARD_STEPS} --accept-fate calls did not leave "
                        "wizard mode:\n" + "\n".join(transcript)
                    )
                records = list(recorder.records)
                assert_saves(records, ["high"] * calls)
                assert_one_transition(records, "high")
                assert_transitioned_clone(dbname, "after transition", reads)
            finally:
                (evidence / "cli-transcript.txt").write_text("\n".join(transcript))
                write_json(evidence / "cli-requests.json", recorder.records)
                write_json(
                    evidence / "cli-clone-reads.json",
                    {"database": dbname, "reads": reads},
                )
    record_usage(evidence, "cli")


def test_browser_glyphs_hold_confirm_and_ride_the_transition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """Glyphs save before they show, Confirm waits, the transition carries it."""
    lane = require_zero_spend_lane()
    base = f"http://127.0.0.1:{lane}"
    evidence = evidence_dir(tmp_path)
    print(f"Lane {lane}; evidence directory {evidence}", flush=True)
    configure_zero_spend(tmp_path, request, monkeypatch)
    monkeypatch.setenv("NEXUS_API_URL", base)
    transcript: list[str] = []
    reads: list[dict[str, Any]] = []
    console_errors: list[dict[str, Any]] = []
    with disposable_slot_database("qa640_838_browser") as dbname:
        route_slot(monkeypatch, dbname)
        with _recorded_gateway(monkeypatch, lane) as recorder:
            try:
                transcribed_cli(
                    monkeypatch,
                    transcript,
                    "continue",
                    "--slot",
                    str(SLOT),
                    "--model",
                    "TEST",
                )
                for _ in range(MAX_WIZARD_STEPS):
                    state = slot_state(base)
                    if (
                        state["phase"] == "seed"
                        and state["pending_confirmation"] is None
                        and state["awaiting_introduction"] is None
                    ):
                        break
                    transcribed_cli(
                        monkeypatch,
                        transcript,
                        "continue",
                        "--slot",
                        str(SLOT),
                        "--accept-fate",
                    )
                else:
                    state = slot_state(base)
                assert state["phase"] == "seed", "\n".join(transcript)
                assert state["pending_confirmation"] is None, state
                assert state["awaiting_introduction"] is None, state
                introduced = read_clone(dbname, "at the introduction", reads)
                assert introduced["weird_level"] is None, introduced

                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 1000},
                        service_workers="block",
                    )
                    context.add_init_script(
                        f"localStorage.setItem('activeSlot', '{SLOT}');"
                    )
                    page = context.new_page()
                    page.on(
                        "console",
                        lambda message: (
                            console_errors.append(
                                {"text": message.text, "location": message.location}
                            )
                            if message.type == "error"
                            else None
                        ),
                    )

                    def glyph(level: str) -> Any:
                        return page.get_by_role(
                            "button", name=f"Strangeness: {level}", exact=True
                        )

                    def expect_pressed(level: str | None) -> None:
                        for each in LEVELS:
                            expect(glyph(each)).to_have_attribute(
                                "aria-pressed",
                                "true" if each == level else "false",
                                timeout=UI_WAIT_MS,
                            )

                    def shot(name: str) -> None:
                        page.screenshot(path=str(evidence / name), full_page=True)

                    def expect_stored(level: str, label: str) -> None:
                        stored = read_clone(dbname, label, reads)
                        assert stored["weird_level"] == level, stored
                        assert slot_state(base)["weird_level"] == level

                    page.goto(base + "/continue")
                    for level in LEVELS:
                        glyph(level).wait_for(timeout=UI_WAIT_MS)
                    expect_pressed(None)
                    shot("glyphs-unset.png")

                    for level in LEVELS:
                        glyph(level).click()
                        expect_pressed(level)
                        expect_stored(level, f"after clicking {level}")
                        shot(f"glyph-{level}.png")

                    page.goto(base + "/continue")
                    for level in LEVELS:
                        glyph(level).wait_for(timeout=UI_WAIT_MS)
                    expect_pressed("high")
                    shot("reload-high.png")

                    page.get_by_role("button", name="Accept Fate", exact=True).click()
                    confirm = page.get_by_role("button", name="Confirm", exact=True)
                    confirm.wait_for(timeout=UI_WAIT_MS)
                    expect(confirm).to_be_enabled(timeout=UI_WAIT_MS)

                    held: list[Any] = []

                    def hold_save(route: Any) -> None:
                        # Answer nothing yet: the save waits in the browser.
                        held.append(route)

                    page.route("**/api/story/new/weird", hold_save)
                    glyph("low").click()
                    deadline = time.monotonic() + UI_WAIT_MS / 1000
                    while not held and time.monotonic() < deadline:
                        page.wait_for_timeout(50)
                    assert held, "The strangeness save never left the browser"
                    expect(confirm).to_be_disabled(timeout=UI_WAIT_MS)
                    for level in LEVELS:
                        expect(glyph(level)).to_be_disabled(timeout=UI_WAIT_MS)
                    expect_pressed("high")
                    expect_stored("high", "while the low save is held")
                    shot("confirm-held.png")
                    held[0].continue_()
                    page.unroute("**/api/story/new/weird", hold_save)
                    expect_pressed("low")
                    expect(confirm).to_be_enabled(timeout=UI_WAIT_MS)
                    expect_stored("low", "after the held save lands")
                    shot("confirm-released.png")

                    confirm.click()
                    deadline = time.monotonic() + TRANSITION_WAIT_SECONDS
                    while time.monotonic() < deadline and not any(
                        record["method"] == "POST" for record in recorder.records
                    ):
                        page.wait_for_timeout(200)
                    records = list(recorder.records)
                    assert_one_transition(records, "low")
                    assert_saves(records, ["low", "medium", "high", "low"])
                    assert_transitioned_clone(dbname, "after transition", reads)
                    browser.close()
            finally:
                (evidence / "browser-transcript.txt").write_text("\n".join(transcript))
                write_json(evidence / "browser-requests.json", recorder.records)
                write_json(
                    evidence / "browser-clone-reads.json",
                    {"database": dbname, "reads": reads},
                )
                write_json(evidence / "console-errors.json", console_errors)
    record_usage(evidence, "browser")
