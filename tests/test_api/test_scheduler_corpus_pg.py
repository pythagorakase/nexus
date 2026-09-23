"""Run the deferred owner against a disposable copy of the starved corpus.

The default proof uses TEST. NEXUS_800_PAID_PROOF=1 explicitly enables one
experience job with the configured real provider, before the TEST idle drain.
It disables structured repair retries and limits the paid pass to one job.
"""

from contextlib import closing
import json
import os
from pathlib import Path

import pytest
import tomlkit

from nexus.agents.orrery.job_queues import load_job_queues_sync
from nexus.config import load_settings_as_dict
from nexus.jobs.scheduler import SlotScheduler
from nexus.telemetry import usage
from tests.pg_fixtures import connect, disposable_slot_database
from tests.scheduler_helpers import (
    route_slot,
    run_cli,
    test_provider_config as configure_test,
)
from tests.test_api.test_scheduler_pg import wait_until
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401

pytestmark = pytest.mark.requires_postgres


def test_scheduler_drains_starved_corpus(monkeypatch, tmp_path, mock_openai_server):
    """The nine original jobs become terminal with no accepting transaction."""
    with disposable_slot_database(
        "qa640_800_corpus", source_db="save_04", include_data=True
    ) as dbname:
        route_slot(monkeypatch, dbname)
        print(f"Disposable corpus: {dbname}", flush=True)
        run_cli(monkeypatch, "jobs", "--slot", "4")
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM character_experience_jobs WHERE state='queued' ORDER BY id"
            )
            original_ids = [row[0] for row in cur.fetchall()]
            assert len(original_ids) == 9
            cur.execute(
                "SELECT id, state::text FROM orrery_maturation_jobs ORDER BY id"
            )
            maturation = cur.fetchall()
            print(f"Maturation before: {maturation}", flush=True)
            assert all(state == "succeeded" for _, state in maturation)

        if os.environ.get("NEXUS_800_PAID_PROOF") == "1":
            doc = tomlkit.parse(Path("nexus.toml").read_text())
            doc["wizard"]["max_retries"] = 0
            path = tmp_path / "paid.toml"
            path.write_text(tomlkit.dumps(doc))
            monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(path))
            result = SlotScheduler(4).run_pass(
                narration_limit=0, experience_limit=1, maturation_limit=0
            )
            print(f"Paid scheduler pass: {result}", flush=True)
            events = [
                json.loads(line)
                for p in usage._config.usage_dir.glob("*.jsonl")
                for line in p.read_text().splitlines()
            ]
            print("Paid usage: " + json.dumps(events, sort_keys=True), flush=True)
            assert len(events) == 1, events
            assert events[0]["seat"] == "experience_renderer"
            assert result["character_experience_jobs"][0] > 0, result

        path = configure_test(tmp_path, mock_openai_server, monkeypatch)
        doc = tomlkit.parse(path.read_text())
        doc["orrery"]["experiences"]["retry_delay_seconds"] = 1
        doc["orrery"]["promote"]["priority_threshold"] = 0
        doc["orrery"]["promote"]["magnitude_threshold"] = 0.0
        path.write_text(tomlkit.dumps(doc))
        # Requeue one already-promoted real resolution only in the clone to
        # prove deterministic narration dispatch on the same owner pass.
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE orrery_resolutions SET promotion_status='pending' WHERE id=(SELECT r.id FROM orrery_resolutions r WHERE NOT EXISTS (SELECT 1 FROM offscreen_narrations n WHERE n.resolution_id=r.id) ORDER BY r.priority DESC, r.id LIMIT 1)"
            )
        scheduler = SlotScheduler(4)
        scheduler.start()
        try:

            def drained():
                with closing(connect(dbname)) as conn, conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*) FROM character_experience_jobs WHERE id=ANY(%s) AND state IN ('queued','leased')",
                        (original_ids,),
                    )
                    return cur.fetchone()[0] == 0

            wait_until(drained, timeout=30)
            with closing(connect(dbname)) as conn:
                status = load_job_queues_sync(conn)
                assert status["queues"]["narration"]["counts"]["succeeded"] >= 1
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id,state::text,attempts FROM character_experience_jobs WHERE id=ANY(%s) ORDER BY id",
                        (original_ids,),
                    )
                    print(f"Original jobs after: {cur.fetchall()}", flush=True)
            run_cli(monkeypatch, "jobs", "--slot", "4")
        finally:
            scheduler.stop()


def test_scheduler_live_turn_starts_before_queued_render(
    monkeypatch, tmp_path, mock_openai_server
):
    """A real auto-accept/TEST turn outruns due maintenance on lane 8017."""
    import threading
    import time
    import requests
    from nexus.api import narrative
    from nexus.jobs import gate
    from tests.scheduler_helpers import gateway_lane

    configure_test(tmp_path, mock_openai_server, monkeypatch)
    with disposable_slot_database(
        "qa640_800_turn", source_db="save_04", include_data=True
    ) as dbname:
        route_slot(monkeypatch, dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE global_variables SET model='TEST', gaia_model='TEST'")
            cur.execute(
                "UPDATE character_experience_jobs SET available_at=clock_timestamp()+interval '1 hour' WHERE state='queued'"
            )
        generation_started = threading.Event()
        render_started = threading.Event()
        order = []
        original_progress = narrative.manager.send_progress
        original_accept = narrative._resolve_and_approve_pending_sync
        original_report = gate.report_leased_job

        async def observe_progress(session_id, status, data=None):
            if status == "loading_chunk":
                order.append(("generation", time.monotonic()))
                generation_started.set()
            return await original_progress(session_id, status, data)

        def accept_and_make_retry_due(**kwargs):
            result = original_accept(**kwargs)
            with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE character_experience_jobs SET available_at=clock_timestamp()-interval '1 second' WHERE state='queued'"
                )
            order.append(("commit", time.monotonic()))
            narrative.wake_scheduler(4)
            return result

        def observe_render(queue, job_id):
            if queue == "character_experience_jobs":
                order.append(("render", time.monotonic()))
                assert generation_started.is_set(), order
                render_started.set()
            return original_report(queue, job_id)

        monkeypatch.setattr(narrative.manager, "send_progress", observe_progress)
        monkeypatch.setattr(
            narrative, "_resolve_and_approve_pending_sync", accept_and_make_retry_due
        )
        monkeypatch.setattr(gate, "report_leased_job", observe_render)
        with gateway_lane(monkeypatch):
            output = run_cli(
                monkeypatch, "continue", "--slot", "4", "--choice", "1", "--json"
            )
            payload = json.loads(output)
            assert payload["success"], payload
            wait_until(render_started.is_set, timeout=30)
            assert [item[0] for item in order[:3]] == [
                "commit",
                "generation",
                "render",
            ], order
            print(f"Live ordering: {order}", flush=True)
            run_cli(monkeypatch, "status")
            status = requests.get("http://127.0.0.1:8017/runtime/status", timeout=10)
            assert status.status_code == 200, status.text
            print(
                "/runtime/status: " + json.dumps(status.json(), sort_keys=True),
                flush=True,
            )
            assert status.json()["database"]["dbname"] == dbname
            assert status.json()["jobs"]["scheduler"]["active"]


def test_scheduler_rechecks_generation_after_leasing_before_provider(
    monkeypatch, tmp_path, mock_openai_server
):
    """A generation starting after job selection still holds the real HTTP call."""
    from threading import Event
    from time import sleep
    from uuid import uuid4
    from nexus.agents.orrery import experiences
    from nexus.api import narrative_lease

    configure_test(tmp_path, mock_openai_server, monkeypatch)
    with disposable_slot_database(
        "qa640_800_call_gate", source_db="save_04", include_data=True
    ) as dbname:
        route_slot(monkeypatch, dbname)
        session = str(uuid4())
        selected = Event()
        render_prompt = experiences._render_prompt

        def start_interactive_after_lease(rows):
            if not selected.is_set():
                with closing(connect(dbname)) as conn:
                    assert (
                        narrative_lease.acquire_generation_lease(
                            conn,
                            session_id=session,
                            operation="continue",
                            stale_timeout_seconds=60,
                        )
                        is None
                    )
                selected.set()
            return render_prompt(rows)

        monkeypatch.setattr(
            experiences, "_render_prompt", start_interactive_after_lease
        )
        scheduler = SlotScheduler(4)
        scheduler.start()
        try:
            assert selected.wait(5)
            sleep(0.2)
            assert not list(usage._config.usage_dir.glob("*.jsonl"))
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM character_experience_jobs WHERE state='leased'"
                )
                assert cur.fetchone() == (1,)
                narrative_lease.finish_generation(
                    conn, session_id=session, status="complete"
                )

            def completed():
                with closing(connect(dbname)) as conn, conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*) FROM character_experience_jobs WHERE state='succeeded'"
                    )
                    return cur.fetchone()[0] > 0

            wait_until(completed)
            events = [
                json.loads(line)
                for p in usage._config.usage_dir.glob("*.jsonl")
                for line in p.read_text().splitlines()
            ]
            assert events and all(event["provider"] == "test" for event in events)
        finally:
            scheduler.stop()
