"""Live probe (776-S1b Phase 2): a killed gateway's genesis run resumes for free.

One paid genesis run on a disposable, migrated template clone routed under
slot 4, served by a real gateway on lane 8021. The probe POSTs the transition,
waits until the run has saved its expansion output, SIGKILLs the gateway, and
writes the four saved stage outputs to ``NEXUS_GENESIS_CAPTURE_PATH`` at once
(the capture the Phase 2 PostgreSQL tests replay). A restarted gateway then
answers a second POST from those saved outputs: the stopped run is recorded
``GenesisRunInterrupted`` and no provider seat records a new usage event.

Gating: ``NEXUS_RUN_LIVE_LLM=1``, ``NEXUS_RUN_POSTGRES=1`` and the explicit
paid-probe opt-in ``NEXUS_GENESIS_RESUME_PROBE=1``. Bound: one genesis run's
calls (one derivation, two seed calls, one expansion, plus the structured-output
retries ``[wizard].max_retries`` allows); none after the restart. Run it once.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pytest
import requests
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.retrograde_orchestrator import GENESIS_RUN_INTERRUPTED
from tests import secret_store_guard
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    routed_slot_environment,
)
from tests.test_orrery.test_retrograde_wizard_live import (
    ROUTED_SLOT,
    stage_fixture_world,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_llm,
    pytest.mark.requires_postgres,
    pytest.mark.skipif(
        os.environ.get("NEXUS_GENESIS_RESUME_PROBE") != "1",
        reason="Set NEXUS_GENESIS_RESUME_PROBE=1 to run the paid genesis resume probe.",
    ),
]

# The order assigned lane 8021, but macOS's com.apple.ftp-proxy launchd job
# owns 127.0.0.1:8021 and ::1:8021 (``netstat -anv`` names ``launchd:1``), a
# socket user-level ``lsof`` does not list. 8022 is the next free lane; no
# other suite or order binds it, and 8002/8012 are never used.
LANE = 8022
API = f"http://127.0.0.1:{LANE}"
REPO = Path(__file__).resolve().parents[2]
USAGE_DIR = REPO / ".nexus" / "runtime" / "usage"
STAGES = ("derivation", "packet", "seed_candidates", "expansion")
PROVIDER_SEATS = frozenset(
    {
        "trait_input_derivation",
        "retrograde_seed_candidates",
        "retrograde_seed_selection",
        "retrograde_expansion",
    }
)
# Proof parameters, not runtime settings: how long a gateway start, the paid
# generation, the resumed answer, and a gateway stop may take.
GATEWAY_START_SECONDS = 90
GENERATION_SECONDS = 1500
RESUME_SECONDS = 600
GATEWAY_STOP_SECONDS = 30
LEDGER_POLL_SECONDS = 0.05


def _lane_listeners() -> str:
    """Describe whatever holds the lane (empty when it is free).

    ``lsof`` lists this user's listeners; a bind attempt also catches a
    socket another user or launchd holds, which ``lsof`` cannot see.
    """
    found = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{LANE}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    held = found.stdout.strip()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        # As uvicorn binds: closed connections in TIME_WAIT do not hold it.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", LANE))
        except OSError as exc:
            held = f"{held}\nbind 127.0.0.1:{LANE}: {exc}".strip()
    return held


def _query(dbname: str, sql: str, params: Any = None) -> list[dict[str, Any]]:
    with closing(connect(dbname, cursor_factory=RealDictCursor)) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def _latest_run(dbname: str) -> Optional[dict[str, Any]]:
    rows = _query(
        dbname,
        "SELECT run_id::text AS run_id, status, error FROM genesis_runs "
        "ORDER BY started_at DESC LIMIT 1",
    )
    return rows[0] if rows else None


def _stage_rows(dbname: str, run_id: str) -> dict[str, dict[str, Any]]:
    rows = _query(
        dbname,
        "SELECT stage, detail, output FROM genesis_run_stages "
        "WHERE run_id = %s::uuid ORDER BY started_at",
        (run_id,),
    )
    return {row["stage"]: row for row in rows}


def _provider_events(since: datetime) -> list[dict[str, Any]]:
    """Every usage event a provider seat of genesis recorded since ``since``."""
    events: list[dict[str, Any]] = []
    for path in sorted(USAGE_DIR.glob("usage-*.jsonl")):
        for line in path.read_text().splitlines():
            event = json.loads(line)
            stamp = datetime.fromisoformat(event["ts"].replace("Z", "+00:00"))
            if stamp >= since and event["seat"] in PROVIDER_SEATS:
                events.append(event)
    return events


def _launch_gateway(dbname: str, log: Any) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO),
        **routed_slot_environment(ROUTED_SLOT, dbname),
    }
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.slot_routed_uvicorn",
            "nexus.api.narrative:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(LANE),
        ],
        cwd=REPO,
        stdout=log,
        stderr=subprocess.STDOUT,
        # This probe is the one paid run the order authorizes: the gateway's
        # derivation, seed and expansion calls read the provider key from the
        # owner's store (a live read of nexus-api). Without this opt-out the
        # spawn guard starts it in env-only mode and the first call fails.
        env=secret_store_guard.store_access_env(env),
    )


def _wait_healthy(gateway: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + GATEWAY_START_SECONDS
    while time.monotonic() < deadline:
        if gateway.poll() is not None:
            raise RuntimeError(f"Gateway on {LANE} exited with {gateway.returncode}")
        try:
            if requests.get(f"{API}/health", timeout=3).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Gateway on {LANE} never became healthy")


def _stop(gateway: subprocess.Popen[bytes]) -> None:
    if gateway.poll() is None:
        gateway.terminate()
        try:
            gateway.wait(timeout=GATEWAY_STOP_SECONDS)
        except subprocess.TimeoutExpired:
            gateway.kill()
            gateway.wait(timeout=GATEWAY_STOP_SECONDS)


def test_killed_gateway_run_resumes_from_saved_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second POST answers from the killed run's four saved outputs."""
    capture_path = os.environ.get("NEXUS_GENESIS_CAPTURE_PATH")
    if not capture_path:
        pytest.fail("NEXUS_GENESIS_CAPTURE_PATH must name the capture file")
    listeners = _lane_listeners()
    if listeners:
        pytest.fail(f"Lane {LANE} already has a listener; refusing:\n{listeners}")

    from nexus.api.save_slots import get_slot_model

    with disposable_slot_database("qa640_776s1b_probe", story_pin=None) as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=ROUTED_SLOT, dbname=dbname)
        stage_fixture_world(dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE assets.new_story_creator SET "
                "setting_confirmed = TRUE, character_confirmed = TRUE"
            )
        model = get_slot_model(ROUTED_SLOT, dbname=dbname)
        probe_start = datetime.now(timezone.utc)
        first_answer: list[Any] = []

        def post_first() -> None:
            try:
                first_answer.append(
                    requests.post(
                        f"{API}/api/story/new/transition",
                        json={"slot": ROUTED_SLOT},
                        timeout=GENERATION_SECONDS,
                    )
                )
            except requests.RequestException as exc:
                # The gateway is killed mid-request on purpose.
                first_answer.append(exc)

        with (tmp_path / "gateway-first.log").open("wb") as log:
            gateway = _launch_gateway(dbname, log)
            try:
                _wait_healthy(gateway)
                poster = threading.Thread(target=post_first, daemon=True)
                poster.start()
                deadline = time.monotonic() + GENERATION_SECONDS
                run: Optional[dict[str, Any]] = None
                stages: dict[str, dict[str, Any]] = {}
                while time.monotonic() < deadline:
                    run = _latest_run(dbname)
                    if run is not None:
                        stages = _stage_rows(dbname, run["run_id"])
                        expansion = stages.get("expansion")
                        if expansion is not None and expansion["output"] is not None:
                            break
                        if run["status"] != "running":
                            break
                    if not poster.is_alive():
                        break
                    time.sleep(LEDGER_POLL_SECONDS)
                os.kill(gateway.pid, signal.SIGKILL)
                gateway.wait(timeout=GATEWAY_STOP_SECONDS)
            finally:
                _stop(gateway)
        poster.join(timeout=GATEWAY_STOP_SECONDS)
        assert run is not None, "The first POST never started a genesis run"
        assert all(
            stages.get(stage) is not None and stages[stage]["output"] is not None
            for stage in STAGES
        ), (
            f"Run {run['run_id']} ended {run['status']} ({run['error']}) before "
            f"saving every output; first answer: {first_answer!r}"
        )
        Path(capture_path).write_text(
            json.dumps(
                {
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "model": model,
                    "outputs": {stage: stages[stage]["output"] for stage in STAGES},
                    "details": {stage: stages[stage]["detail"] for stage in STAGES},
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        killed = _latest_run(dbname)
        assert killed is not None and killed["run_id"] == run["run_id"]
        persistence = _stage_rows(dbname, run["run_id"]).get("persistence")
        assert killed["status"] == "running" and (
            persistence is None or persistence["output"] is None
        ), (
            "STOP: the run passed persistence before the kill; the capture is "
            f"kept at {capture_path}; spend no second paid run ({killed})"
        )
        paid = _provider_events(probe_start)
        assert paid, "The paid run recorded no provider usage events"

        restart = datetime.now(timezone.utc)
        with (tmp_path / "gateway-second.log").open("wb") as log:
            gateway = _launch_gateway(dbname, log)
            try:
                _wait_healthy(gateway)
                answer = requests.post(
                    f"{API}/api/story/new/transition",
                    json={"slot": ROUTED_SLOT},
                    timeout=RESUME_SECONDS,
                )
            finally:
                _stop(gateway)
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["retrograde"]["reused_stages"] == list(STAGES)
        [stopped] = _query(
            dbname,
            "SELECT status, error FROM genesis_runs WHERE run_id = %s::uuid",
            (run["run_id"],),
        )
        assert (stopped["status"], stopped["error"]) == (
            "failed",
            GENESIS_RUN_INTERRUPTED,
        )
        assert body["run"] != run["run_id"].replace("-", "")
        assert _provider_events(restart) == []
    assert _lane_listeners() == "", f"Lane {LANE} is still held"
