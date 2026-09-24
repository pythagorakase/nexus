"""Explicit TEST-provider/browser proof for work order 775; lane 8014 only."""

from contextlib import closing
import json
from pathlib import Path
import subprocess
import threading
import time

from playwright.sync_api import sync_playwright
import pytest
import requests
import tomlkit
import uvicorn

from nexus.api import narrative, slot_endpoints, chunk_workflow
from nexus.telemetry import usage
from tests.pg_fixtures import connect, disposable_slot_database, sqlalchemy_url
from tests.scheduler_helpers import (
    route_slot,
    run_cli,
    test_provider_config as configure_test,
)
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401

pytestmark = pytest.mark.requires_postgres
BASE = "http://127.0.0.1:8014"
EVIDENCE = Path("docs/qa/775-session-truth")


def wait_status(session: str, expected: str = "complete") -> dict:
    """Poll the actual gateway and fail on a durable error."""
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        response = requests.get(
            f"{BASE}/api/narrative/status/{session}", params={"slot": 4}, timeout=60
        )
        response.raise_for_status()
        status = response.json()
        assert status["status"] != "error", status
        if status["status"] == expected:
            return status
        time.sleep(0.1)
    raise AssertionError(f"Session {session} did not reach {expected}")


def test_disconnected_session_browser_recovery(monkeypatch, tmp_path, request):
    """Close a reader mid-writer, remount the real UI, accept, and regenerate."""
    config = configure_test(tmp_path, "http://127.0.0.1:1", monkeypatch)
    # Start the TEST subprocess with this private config already in its env.
    provider = request.getfixturevalue("mock_openai_server")
    configure_test(tmp_path, provider, monkeypatch)
    doc = tomlkit.parse(config.read_text())
    doc["api"]["test_provider"]["writer_response_delay_seconds"] = 3
    doc["api"]["narrative_generation"]["poll_interval_seconds"] = 0.2
    doc["api"]["narrative_generation"]["wake_gap_threshold_seconds"] = 1
    config.write_text(tomlkit.dumps(doc))
    with disposable_slot_database(
        "qa640_775_browser", source_db="save_04", include_data=True
    ) as dbname:
        route_slot(monkeypatch, dbname)
        monkeypatch.setattr(chunk_workflow, "VALID_DATABASES", {dbname})
        real_run = subprocess.run

        def run_in_clone(command, *args, **kwargs):
            # The embedding CLI validates --database against saved-slot names
            # in its fresh process. Use its existing explicit URL interface for
            # this fixture, while still executing the real embedding script.
            if (
                isinstance(command, list)
                and "scripts/regenerate_embeddings.py" in command
            ):
                command = list(command)
                index = command.index("--database")
                assert command[index + 1] == dbname
                command[index : index + 2] = [
                    "--db-url",
                    sqlalchemy_url(dbname).render_as_string(hide_password=False),
                ]
            return real_run(command, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", run_in_clone)
        monkeypatch.setattr(
            slot_endpoints, "slot_dbname", lambda slot: dbname if slot == 4 else None
        )
        monkeypatch.setenv("NEXUS_GATEWAY_PORT", "8014")
        monkeypatch.setenv("NEXUS_API_URL", BASE)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE global_variables SET model='TEST', gaia_model='TEST'")
            cur.execute(
                "UPDATE character_experience_jobs SET available_at=clock_timestamp()+INTERVAL '1 hour' WHERE state='queued'"
            )
        from scripts.stamp_lore_pass_baseline import refresh_tail_fingerprint

        _, _, fingerprint = refresh_tail_fingerprint(dbname=dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE incubator SET lore_pass_baseline=jsonb_set(lore_pass_baseline, '{config_fingerprint}', to_jsonb(%s::text), false) WHERE lore_pass_baseline IS NOT NULL",
                (fingerprint,),
            )
        check = subprocess.run(
            ["lsof", "-nP", "-iTCP:8014", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
        )
        assert check.returncode == 1, check.stdout + check.stderr
        server = uvicorn.Server(
            uvicorn.Config(
                narrative.app, host="127.0.0.1", port=8014, log_level="warning"
            )
        )
        thread = threading.Thread(target=server.run)
        thread.start()
        rows = []

        def snapshot(label):
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT session_id::text, operation, status, phase, terminal_outcome, chunk_id, replaced_by_session_id::text, error_class, created_at::text, heartbeat_at::text FROM narrative_generation_sessions ORDER BY created_at DESC LIMIT 4"
                )
                item = {
                    "label": label,
                    "columns": [column.name for column in cur.description],
                    "rows": cur.fetchall(),
                }
                rows.append(item)
                print(json.dumps(item, indent=2), flush=True)

        try:
            deadline = time.monotonic() + 30
            while (
                not server.started and thread.is_alive() and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            assert server.started
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000}, service_workers="block"
                )
                context.add_init_script(
                    """
                    localStorage.setItem('activeSlot', '4');
                    window.proofSockets = [];
                    const Socket = window.WebSocket;
                    window.WebSocket = class extends Socket {
                        constructor(...args) { super(...args); window.proofSockets.push(this); }
                    };
                """
                )
                page = context.new_page()
                page.goto(BASE + "/nexus")
                page.get_by_test_id("input-freeform").wait_for()
                # An explicit human submission; recovery itself must never POST.
                with page.expect_response(
                    lambda r: r.request.method == "POST"
                    and r.url.endswith("/api/narrative/continue"),
                    timeout=180000,
                ) as initiated:
                    page.get_by_test_id("input-freeform").fill(
                        "I pause and listen before making my next move."
                    )
                    page.get_by_test_id("input-freeform").press("Enter")
                first = initiated.value.json()["session_id"]
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    active = requests.get(
                        BASE + "/api/narrative/active", params={"slot": 4}, timeout=60
                    ).json()
                    assert active["status"] != "error", active
                    if active["phase"] == "writer":
                        break
                    time.sleep(0.05)
                assert active["phase"] == "writer", active
                snapshot("Writer Active Before Disconnect")
                page.close()  # Closes the socket and all in-memory session refs.
                time.sleep(3.2)
                wait_status(first)
                snapshot("Complete While Client Absent")
                recovered = context.new_page()
                posts = []
                seen_statuses = []
                recovered.on(
                    "request",
                    lambda r: (
                        posts.append(r.url)
                        if r.method == "POST" and "/api/narrative/" in r.url
                        else None
                    ),
                )
                recovered.on(
                    "response",
                    lambda r: (
                        seen_statuses.append(r.json())
                        if f"/api/narrative/status/{first}?" in r.url and r.ok
                        else None
                    ),
                )
                recovered.goto(BASE + "/nexus")
                deadline = time.monotonic() + 30
                while not seen_statuses and time.monotonic() < deadline:
                    recovered.wait_for_timeout(100)
                assert (
                    seen_statuses and seen_statuses[-1]["status"] == "complete"
                ), seen_statuses
                assert posts == [], posts
                # Exercise the same mounted reader's remaining recovery boundaries
                # using real browser lifecycle events and a real closed socket.
                discoveries = []
                recovered.on(
                    "response",
                    lambda r: (
                        discoveries.append(r.url)
                        if "/api/narrative/active?" in r.url
                        else None
                    ),
                )
                for boundary in (
                    "document.dispatchEvent(new Event('visibilitychange'))",
                    "window.proofSockets.forEach(socket => socket.close())",
                    "(() => { const start = Date.now(); while (Date.now() - start < 1200) {} })()",
                ):
                    before = len(discoveries)
                    recovered.evaluate(boundary)
                    deadline = time.monotonic() + 10
                    while len(discoveries) == before and time.monotonic() < deadline:
                        recovered.wait_for_timeout(100)
                    assert len(discoveries) > before, boundary
                assert posts == [], posts
                recovered.screenshot(
                    path=str(EVIDENCE / "recovered-reader.png"), full_page=True
                )
                # The reader's next explicit choice accepts the recovered draft.
                with recovered.expect_response(
                    lambda r: r.request.method == "POST"
                    and r.url.endswith("/api/narrative/continue"),
                    timeout=180000,
                ) as next_turn:
                    recovered.get_by_test_id("input-freeform").fill(
                        "I take a careful step forward."
                    )
                    recovered.get_by_test_id("input-freeform").press("Enter")
                second = next_turn.value.json()["session_id"]
                accepted = requests.get(
                    f"{BASE}/api/narrative/status/{first}",
                    params={"slot": 4},
                    timeout=60,
                ).json()
                assert accepted["terminal_outcome"] == "accepted", accepted
                assert accepted["chunk_id"] is not None
                with closing(connect(dbname)) as conn, conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM narrative_chunks WHERE id = %s",
                        (accepted["chunk_id"],),
                    )
                    assert cur.fetchone() == (accepted["chunk_id"],)
                snapshot("Recovered Draft Accepted With Inserted Chunk")
                wait_status(second)
                replacement = requests.post(
                    BASE + "/api/narrative/regenerate",
                    json={"slot": 4, "session_id": second},
                    timeout=30,
                )
                replacement.raise_for_status()
                third = replacement.json()["session_id"]
                wait_status(third)
                superseded = requests.get(
                    f"{BASE}/api/narrative/status/{second}",
                    params={"slot": 4},
                    timeout=60,
                ).json()
                assert superseded["terminal_outcome"] == "superseded", superseded
                assert superseded["replaced_by_session_id"] == third
                snapshot("Regenerate Replacement Lineage")
                run_cli(monkeypatch, "load", "--slot", "4", "--json")
                browser.close()
            events = [
                json.loads(line)
                for path in usage._config.usage_dir.glob("*.jsonl")
                for line in path.read_text().splitlines()
            ]
            turn_events = [
                event
                for event in events
                if event.get("run_id") in {first, second, third}
            ]
            assert turn_events and all(
                event["model"] == "TEST" for event in turn_events
            ), turn_events
            assert {event["seat"] for event in turn_events} >= {"skald_writer", "gaia"}
            (EVIDENCE / "provider-usage.json").write_text(
                json.dumps(turn_events, indent=2) + "\n"
            )
            (EVIDENCE / "session-rows.json").write_text(
                json.dumps({"database": dbname, "snapshots": rows}, indent=2) + "\n"
            )
        finally:
            server.should_exit = True
            thread.join(timeout=60)
            assert not thread.is_alive()
            run_cli(monkeypatch, "down")
