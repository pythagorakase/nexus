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
    doc["api"]["narrative_generation"]["request_timeout_seconds"] = 5
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
                held_submissions = []
                polled_while_submitting = []

                def hold_submission_response(route):
                    # Forward the real POST, but lose its response to the reader.
                    held_submissions.append(route.fetch(timeout=180000))

                page.route("**/api/narrative/continue", hold_submission_response)
                page.on(
                    "response",
                    lambda r: (
                        polled_while_submitting.append(r.url)
                        if "/api/narrative/status/" in r.url and r.ok
                        else None
                    ),
                )
                page.get_by_test_id("input-freeform").fill(
                    "I pause and listen before making my next move."
                )
                page.get_by_test_id("input-freeform").press("Enter")
                deadline = time.monotonic() + 180
                while not held_submissions and time.monotonic() < deadline:
                    page.wait_for_timeout(50)
                assert held_submissions
                first = held_submissions[0].json()["session_id"]
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
                deadline = time.monotonic() + 10
                while not polled_while_submitting and time.monotonic() < deadline:
                    page.wait_for_timeout(50)
                assert polled_while_submitting, "Pending POST disabled recovery"
                print(
                    "Recovery polled durable status while the real POST response was withheld"
                )
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
                failures = {"slot": 0, "active": 0, "status": 0}
                stalled = []
                aborted = []
                recovered.on("requestfailed", lambda r: aborted.append(r.url))

                def disrupt_first_reads(route):
                    url = route.request.url
                    kind = (
                        "slot"
                        if "/api/slot/4/state" in url
                        else ("active" if "/api/narrative/active?" in url else "status")
                    )
                    failures[kind] += 1
                    if kind == "slot" and failures[kind] <= 2:
                        route.abort("connectionfailed")
                    elif kind == "active" and failures[kind] == 1:
                        route.abort("connectionfailed")
                    elif (kind == "active" and failures[kind] == 2) or (
                        kind == "status" and failures[kind] == 1
                    ):
                        stalled.append(route)  # No fabricated server response.
                    else:
                        route.continue_()

                recovered.route("**/api/slot/4/state", disrupt_first_reads)
                recovered.route("**/api/narrative/active?*", disrupt_first_reads)
                recovered.route("**/api/narrative/status/*", disrupt_first_reads)
                recovered.goto(BASE + "/nexus")
                deadline = time.monotonic() + 30
                while not seen_statuses and time.monotonic() < deadline:
                    recovered.wait_for_timeout(100)
                assert (
                    seen_statuses and seen_statuses[-1]["status"] == "complete"
                ), seen_statuses
                assert posts == [], posts
                assert failures["active"] >= 3 and failures["status"] >= 2, failures
                assert any("/api/narrative/active?" in url for url in aborted), aborted
                assert any("/api/narrative/status/" in url for url in aborted), aborted
                print(
                    f"Recovered after failed slot/discovery reads and timed-out discovery/status: {failures}"
                )
                recovered.unroute_all(behavior="ignoreErrors")
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
                    pending = []

                    def hold_one_discovery(route):
                        if not pending:
                            pending.append(route)
                        else:
                            route.continue_()

                    recovered.route("**/api/narrative/active?*", hold_one_discovery)
                    deadline = time.monotonic() + 10
                    while not pending and time.monotonic() < deadline:
                        recovered.wait_for_timeout(50)
                    assert pending
                    before, before_aborted = len(discoveries), len(aborted)
                    recovered.evaluate(boundary)
                    deadline = (
                        time.monotonic() + 4.5
                    )  # Shorter than configured request timeout.
                    while len(discoveries) == before and time.monotonic() < deadline:
                        recovered.wait_for_timeout(50)
                    assert len(discoveries) > before, boundary
                    assert len(aborted) > before_aborted, boundary
                    recovered.unroute("**/api/narrative/active?*", hold_one_discovery)
                    print(f"Recovery boundary preempted stalled discovery: {boundary}")
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
                # Undo the actual pending replacement, then mount a new reader.
                recovered.close()
                racing = context.new_page()

                def undo_after_discovery(route):
                    # Delay a real discovery response across undo so the next
                    # status read sees discarded, exercising the quiet client
                    # terminal branch as well as the later empty discovery.
                    response = route.fetch()
                    assert response.json()["session_id"] == third
                    run_cli(monkeypatch, "undo", "--slot", "4", "--json")
                    route.fulfill(response=response)

                racing.route("**/api/narrative/active?*", undo_after_discovery, times=1)
                with racing.expect_response(
                    lambda response: f"/api/narrative/status/{third}?" in response.url
                ) as raced_status:
                    racing.goto(BASE + "/nexus")
                assert raced_status.value.json()["terminal_outcome"] == "discarded"
                racing.get_by_test_id("input-freeform").wait_for()
                racing.wait_for_timeout(500)
                assert racing.get_by_text("Generation Failed", exact=True).count() == 0
                racing.close()
                discarded = wait_status(third)
                assert discarded["terminal_outcome"] == "discarded", discarded
                assert discarded["error_class"] is None
                assert discarded["error"] is None
                snapshot("Draft Discarded by Undo")
                fresh = context.new_page()
                discoveries_after_undo = []
                fresh_posts = []
                fresh.on(
                    "response",
                    lambda response: (
                        discoveries_after_undo.append(response)
                        if "/api/narrative/active?" in response.url
                        else None
                    ),
                )
                fresh.on(
                    "request",
                    lambda request: (
                        fresh_posts.append(request.url)
                        if request.method == "POST"
                        else None
                    ),
                )
                fresh.goto(BASE + "/nexus")
                fresh.get_by_test_id("input-freeform").wait_for()
                deadline = time.monotonic() + 15
                while len(discoveries_after_undo) < 3 and time.monotonic() < deadline:
                    fresh.wait_for_timeout(50)
                assert len(discoveries_after_undo) >= 3
                for response in discoveries_after_undo:
                    assert response.status == 200
                    assert response.json() is None
                assert fresh.get_by_text("Generation Failed", exact=True).count() == 0
                assert fresh.get_by_text("DraftDiscarded").count() == 0
                assert fresh_posts == [], fresh_posts
                fresh.screenshot(
                    path=str(EVIDENCE / "discarded-reader.png"), full_page=True
                )
                print(
                    "Undo: discarded; fresh reader: no active attempt, no error, no inference"
                )
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
