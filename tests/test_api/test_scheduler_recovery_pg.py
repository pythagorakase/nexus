import os

"""Real interruptions, lock waits, and concurrent reads of deferred ownership."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from time import sleep, monotonic
from uuid import uuid4

import pytest
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from nexus.api import narrative_lease
from nexus.agents.orrery.job_queues import load_job_queues_sync
from nexus.jobs.scheduler import SlotScheduler
from tests.pg_fixtures import connect, seed_protagonist
from tests.test_api.test_scheduler_pg import (
    seed_narration,
    job_state,
    wait_until,
)
from tests.test_orrery.test_narration_job_fencing_pg import _insert_chunk

pytestmark = pytest.mark.requires_postgres


def test_scheduler_recovers_terminated_heartbeat_backend(
    offline_gate_db, caplog, monkeypatch, tmp_path, mock_openai_server
):
    """Kill an actual blocked heartbeat connection; the same loop reacquires."""
    seed_narration(offline_gate_db)
    session = str(uuid4())
    with closing(connect(offline_gate_db)) as conn:
        narrative_lease.acquire_generation_lease(
            conn, session_id=session, operation="continue", stale_timeout_seconds=60
        )
    import json
    import requests
    import tomlkit
    from contextlib import ExitStack
    from tests.scheduler_helpers import (
        gateway_lane,
        route_slot,
        run_cli,
        test_provider_config,
    )

    path = test_provider_config(tmp_path, mock_openai_server, monkeypatch)
    doc = tomlkit.parse(path.read_text())
    doc["runtime"]["scheduler"]["error_backoff_seconds"] = 0.2
    path.write_text(tomlkit.dumps(doc))
    route_slot(monkeypatch, offline_gate_db)
    with ExitStack() as stack:
        scheduler = stack.enter_context(gateway_lane(monkeypatch))
        original_nonce = scheduler.nonce
        with closing(connect(offline_gate_db)) as locker, locker.cursor() as lock:
            lock.execute("SELECT id FROM deferred_work_scheduler FOR UPDATE")

            def kill_waiting_backend():
                with (
                    closing(connect(offline_gate_db)) as conn,
                    conn,
                    conn.cursor() as cur,
                ):
                    cur.execute(
                        """SELECT pid FROM pg_stat_activity WHERE datname=%s
                        AND pid<>pg_backend_pid() AND wait_event_type='Lock'
                        AND query LIKE '%%SET heartbeat_at = clock_timestamp()%%'""",
                        (offline_gate_db,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return False
                    cur.execute("SELECT pg_terminate_backend(%s)", row)
                    assert cur.fetchone() == (True,)
                    print(f"Terminated heartbeat backend: {row[0]}", flush=True)
                    return True

            wait_until(kill_waiting_backend)
            wait_until(lambda: scheduler.state == "recovering")
            assert not scheduler.stopping.is_set()
            assert scheduler.last_error
            print(
                f"Recovery state: {scheduler.state}; last_error={scheduler.last_error}",
                flush=True,
            )
            status = requests.get(
                os.environ["NEXUS_API_URL"] + "/runtime/status", timeout=10
            ).json()
            assert status["jobs"]["scheduler"]["state"] == "recovering"
            assert status["jobs"]["scheduler"]["last_error"] == scheduler.last_error
            print(
                "Recovering runtime scheduler: "
                + json.dumps(status["jobs"]["scheduler"], sort_keys=True),
                flush=True,
            )
            locker.rollback()
        with closing(connect(offline_gate_db)) as conn:
            narrative_lease.finish_generation(
                conn, session_id=session, status="complete"
            )
        wait_until(
            lambda: scheduler.state == "owner" and scheduler.nonce != original_nonce,
            timeout=10,
        )
        wait_until(lambda: job_state(offline_gate_db) == [("succeeded", 1)])
        assert scheduler._thread.is_alive()
        assert "recovering" in caplog.text
        run_cli(monkeypatch, "status")
        status = requests.get(
            os.environ["NEXUS_API_URL"] + "/runtime/status", timeout=10
        ).json()
        assert status["jobs"]["scheduler"]["state"] == "owner"
        assert status["jobs"]["scheduler"]["last_error"]
        print(
            "Recovered runtime scheduler: "
            + json.dumps(status["jobs"]["scheduler"], sort_keys=True),
            flush=True,
        )
        print(
            f"Reacquired: {original_nonce} -> {scheduler.nonce}; narration={job_state(offline_gate_db)}",
            flush=True,
        )


def _leased_job(dbname, queue):
    character, entity = seed_protagonist(dbname)
    nonce = str(uuid4())
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        chunk = _insert_chunk(cur, "Lease lock proof")
        if queue == "orrery_maturation_jobs":
            cur.execute(
                """INSERT INTO orrery_maturation_jobs
                (entity_id,entity_kind,entity_subtype_id,entity_name,slot,requesting_chunk_id,declaration)
                VALUES (%s,'character',%s,'Fixture Player','4',%s,'{}') RETURNING id""",
                (entity, character, chunk),
            )
        else:
            cur.execute(
                "INSERT INTO correspondence_compaction_jobs (accepting_chunk_id) VALUES (%s) RETURNING id",
                (chunk,),
            )
        job_id = cur.fetchone()[0]
        cur.execute(
            sql.SQL(
                """UPDATE {} SET state='leased', attempts=1, locked_by='proof',
            lease_nonce=%s, lease_until=clock_timestamp()+interval '1 second' WHERE id=%s"""
            ).format(sql.Identifier(queue)),
            (nonce, job_id),
        )
    return {"job_id": job_id, "locked_by": "proof", "lease_nonce": nonce}


@pytest.mark.parametrize(
    "queue", ["orrery_maturation_jobs", "correspondence_compaction_jobs"]
)
def test_completion_fence_rechecks_clock_after_row_lock(offline_gate_db, queue):
    """A completion already waiting for a lock must reject a now-expired lease."""
    from nexus.agents.orrery.retrograde_maturation import _mark_maturation_succeeded
    from nexus.jobs.compaction import require_compaction_lease

    job = _leased_job(offline_gate_db, queue)

    def finish():
        with (
            closing(connect(offline_gate_db)) as conn,
            conn,
            conn.cursor(cursor_factory=RealDictCursor) as cur,
        ):
            if queue == "orrery_maturation_jobs":
                _mark_maturation_succeeded(
                    cur,
                    row=job,
                    manifest={
                        "schema_version": "orrery_retrograde_maturation_manifest.v1"
                    },
                )
            else:
                require_compaction_lease(
                    cur, job_id=job["job_id"], owner="proof", nonce=job["lease_nonce"]
                )
                cur.execute(
                    "UPDATE correspondence_compaction_jobs SET state='succeeded' WHERE id=%s",
                    (job["job_id"],),
                )

    with closing(connect(offline_gate_db)) as locker, ThreadPoolExecutor(1) as pool:
        with locker.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT id FROM {} WHERE id=%s FOR UPDATE").format(
                    sql.Identifier(queue)
                ),
                (job["job_id"],),
            )
        future = pool.submit(finish)
        try:

            def waiting():
                with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND wait_event_type='Lock'",
                        (offline_gate_db,),
                    )
                    return cur.fetchone()[0] > 0

            wait_until(waiting)
            sleep(1.1)
        finally:
            locker.rollback()
        with pytest.raises(RuntimeError, match="lost its lease"):
            future.result(timeout=5)
    with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT state::text FROM {} WHERE id=%s").format(
                sql.Identifier(queue)
            ),
            (job["job_id"],),
        )
        assert cur.fetchone() == ("leased",)


@pytest.mark.parametrize(
    "queue", ["orrery_narration_jobs", "correspondence_compaction_jobs"]
)
def test_queue_snapshot_is_consistent_across_concurrent_completion(
    offline_gate_db, queue
):
    """Commit from another connection between executing status SQL and fetching."""
    if queue == "orrery_narration_jobs":
        seed_narration(offline_gate_db)
    else:
        _leased_job(offline_gate_db, queue)
    completed = []

    class CompletionCursor(RealDictCursor):
        def execute(self, query, vars=None):
            result = super().execute(query, vars)
            rendered = self.query.decode()
            if not completed and f'FROM "{queue}"' in rendered:
                with (
                    closing(connect(offline_gate_db)) as other,
                    other,
                    other.cursor() as cur,
                ):
                    cur.execute(
                        sql.SQL(
                            "UPDATE {} SET state='succeeded', lease_until=NULL, locked_by=NULL, lease_nonce=NULL"
                        ).format(sql.Identifier(queue))
                    )
                completed.append(True)
            return result

    from nexus.agents.orrery.job_queues import _queue_status

    with (
        closing(connect(offline_gate_db)) as conn,
        conn.cursor(cursor_factory=CompletionCursor) as cur,
    ):
        status = _queue_status(cur, queue, queue)
    assert completed
    assert (
        status["counts"]["queued"] + status["counts"]["leased"]
        == len(status["non_terminal_jobs"])
        == 1
    )
    with closing(connect(offline_gate_db)) as conn:
        status = load_job_queues_sync(conn)
    assert not status["non_terminal_jobs"]


@pytest.mark.parametrize(
    "queue", ["character_experience_jobs", "correspondence_compaction_jobs"]
)
@pytest.mark.parametrize("lose_lease", [False, True])
def test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt(
    monkeypatch, tmp_path, mock_openai_server, queue, lose_lease
):
    """Hold generation past the job TTL; renew or abandon before real HTTP."""
    from threading import Event
    import tomlkit
    from nexus.config import load_settings
    from nexus.memory.correspondence import persist_staged_correspondence
    from nexus.jobs.compaction import enqueue_compaction
    from nexus.telemetry import usage
    from tests.pg_fixtures import disposable_slot_database
    from tests.scheduler_helpers import route_slot, test_provider_config

    path = test_provider_config(tmp_path, mock_openai_server, monkeypatch)
    doc = tomlkit.parse(path.read_text())
    doc["orrery"]["experiences"]["lease_duration_seconds"] = 1
    doc["runtime"]["scheduler"]["compaction_lease_duration_seconds"] = 1
    doc["runtime"]["scheduler"]["generation_wait_seconds"] = 1
    path.write_text(tomlkit.dumps(doc))
    with disposable_slot_database(
        "qa640_800_renew", source_db="save_04", include_data=True
    ) as dbname:
        route_slot(monkeypatch, dbname)
        with (
            closing(connect(dbname)) as conn,
            conn,
            conn.cursor(cursor_factory=RealDictCursor) as cur,
        ):
            cur.execute(
                "UPDATE character_experience_jobs SET available_at=clock_timestamp()+interval '1 hour' WHERE state='queued'"
            )
            if queue == "character_experience_jobs":
                cur.execute(
                    "UPDATE character_experience_jobs SET available_at=clock_timestamp() WHERE id=3"
                )
            else:
                cfg = load_settings().storyteller.correspondence
                for i in range(cfg.ceiling_turns + 1):
                    with conn.cursor() as insert_cur:
                        chunk = _insert_chunk(insert_cur, f"Compaction wait {i}")
                    persist_staged_correspondence(
                        cur,
                        chunk_id=chunk,
                        writer_letter="Keep the unresolved pressure.",
                        gaia_letter="The state is consistent.",
                    )
                enqueue_compaction(
                    cur, accepting_chunk_id=chunk, floor_turns=cfg.floor_turns
                )
        selected = Event()
        scheduler = SlotScheduler(4)
        original_track = scheduler._track_lease
        session = str(uuid4())
        leased = {}

        def preempt_after_selection(table, job_id, **lease):
            original_track(table, job_id, **lease)
            if not selected.is_set():
                assert table == queue
                leased.update(id=job_id, **lease)
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

        monkeypatch.setattr(scheduler, "_track_lease", preempt_after_selection)
        scheduler.start()
        try:
            assert selected.wait(5)
            sleep(1.3)
            assert not list(usage._config.usage_dir.glob("*.jsonl"))
            with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "SELECT state::text, attempts, lease_nonce::text, lease_until>clock_timestamp() FROM {} WHERE id=%s"
                    ).format(sql.Identifier(queue)),
                    (leased["id"],),
                )
                assert cur.fetchone() == ("leased", 1, leased["lease_nonce"], True)
            observer = SlotScheduler(4)
            assert observer.run_pass() == {"owner": False, "drained": False}
            if lose_lease:
                with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "UPDATE {} SET lease_until=clock_timestamp()-interval '1 second', available_at=clock_timestamp()+interval '1 hour' WHERE id=%s"
                        ).format(sql.Identifier(queue)),
                        (leased["id"],),
                    )
                scheduler.wakeup.set()
                expected = ("queued", 0)
            else:
                before_release = monotonic()
                with closing(connect(dbname)) as conn:
                    narrative_lease.finish_generation(
                        conn, session_id=session, status="complete"
                    )
                expected = ("succeeded", 1)

            def finished():
                with closing(connect(dbname)) as conn, conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "SELECT state::text, attempts FROM {} WHERE id=%s"
                        ).format(sql.Identifier(queue)),
                        (leased["id"],),
                    )
                    return cur.fetchone() == expected

            wait_until(finished)
            if lose_lease:
                assert not list(usage._config.usage_dir.glob("*.jsonl"))
            else:
                # Default fallback is one second; local notification resumes promptly.
                assert monotonic() - before_release < 1
            print(
                f"{queue}: held beyond 1s TTL; outcome={expected}; lost={lose_lease}",
                flush=True,
            )
        finally:
            scheduler.stop()


from tests.test_logon_mock_integration import mock_openai_server  # noqa: E402,F401


def test_scheduler_gateway_sigkill_resumes_inflight_experience(
    monkeypatch, tmp_path, request
):
    """SIGKILL the real gateway during TEST HTTP; a new process finishes once."""
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys
    import requests
    import tomlkit
    from nexus.config import load_settings
    from nexus.agents.orrery.experiences import (
        _complete_render,
        ExperienceLeaseLostError,
    )
    from tests.pg_fixtures import disposable_slot_database
    from tests.scheduler_helpers import test_provider_config

    # Configure before spawning TEST so its process inherits the same file.
    path = test_provider_config(
        tmp_path, load_settings().global_.model.api_models["test"].base_url, monkeypatch
    )
    doc = tomlkit.parse(path.read_text())
    doc["api"]["test_provider"]["experience_response_delay_seconds"] = 4
    doc["orrery"]["experiences"]["lease_duration_seconds"] = 8
    path.write_text(tomlkit.dumps(doc))
    mock_url = request.getfixturevalue("delayed_mock_openai_server")
    from urllib.parse import urlsplit

    doc["global"]["model"]["api_models"]["test"]["base_url"] = mock_url
    doc["runtime"]["services"]["mock_openai"]["port"] = urlsplit(mock_url).port
    path.write_text(tomlkit.dumps(doc))

    with disposable_slot_database(
        "qa640_800_kill", source_db="save_04", include_data=True
    ) as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE character_experience_jobs SET available_at=clock_timestamp()+interval '1 hour' WHERE state='queued'"
            )
            cur.execute(
                "UPDATE character_experience_jobs SET available_at=clock_timestamp() WHERE id=3"
            )
            cur.execute(
                """CREATE TABLE scheduler_completion_proof (job_id bigint NOT NULL);
                COMMENT ON TABLE scheduler_completion_proof IS 'Test-only audit of successful job transitions';
                COMMENT ON COLUMN scheduler_completion_proof.job_id IS 'Job reaching succeeded in the interruption proof';
                CREATE FUNCTION scheduler_record_completion() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN INSERT INTO scheduler_completion_proof VALUES (NEW.id); RETURN NEW; END $$;
                CREATE TRIGGER scheduler_record_completion AFTER UPDATE ON character_experience_jobs
                FOR EACH ROW WHEN (OLD.state <> 'succeeded' AND NEW.state = 'succeeded')
                EXECUTE FUNCTION scheduler_record_completion();"""
            )
        import socket

        port = int(os.environ.get("NEXUS_GATEWAY_PORT", "8018"))
        check = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
        )
        assert check.returncode == 1, check.stdout + check.stderr
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", port))
            listener.listen(128)
            listener.set_inheritable(True)
            port = listener.getsockname()[1]
            check = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
            )
            # The only listener is the socket this test just bound.
            assert check.returncode == 0 and str(os.getpid()) in check.stdout
            env = {
                **os.environ,
                "PYTHONPATH": str(Path.cwd()),
                "NEXUS_SLOT": "4",
                "NEXUS_GATEWAY_PORT": str(port),
                "NEXUS_API_URL": f"http://127.0.0.1:{port}",
            }
            runner = tmp_path / "gateway_process.py"
            runner.write_text(
                """import sys
import pytest
import uvicorn
from tests.scheduler_helpers import route_slot
route_slot(pytest.MonkeyPatch(), sys.argv[1])
from nexus.api.narrative import app
uvicorn.run(app, fd=int(sys.argv[2]), log_level="info")
"""
            )
            processes = []

            def start(label):
                log_path = tmp_path / f"gateway-{label}.log"
                with log_path.open("w") as log:
                    process = subprocess.Popen(
                        [sys.executable, str(runner), dbname, str(listener.fileno())],
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        pass_fds=(listener.fileno(),),
                    )
                processes.append(process)

                def ready():
                    assert process.poll() is None, log_path.read_text()
                    try:
                        return requests.get(
                            env["NEXUS_API_URL"] + "/health", timeout=0.2
                        ).ok
                    except requests.RequestException:
                        return False

                wait_until(ready, timeout=30)
                return process

            try:
                first = start("first")
                wait_until(
                    lambda: "Experience render received; response delay=4"
                    in (tmp_path / "mock_openai.log").read_text(),
                    timeout=15,
                )
                with (
                    closing(connect(dbname)) as conn,
                    conn.cursor(cursor_factory=RealDictCursor) as cur,
                ):
                    cur.execute(
                        "SELECT *, id AS job_id FROM character_experience_jobs WHERE id=3"
                    )
                    dead = dict(cur.fetchone())
                    assert dead["state"] == "leased" and dead["attempts"] == 1
                first.kill()
                first.wait(timeout=10)
                assert first.returncode == -9
                print(
                    f'SIGKILL gateway pid={first.pid}; job=3; nonce={dead["lease_nonce"]}',
                    flush=True,
                )
                second = start("second")

                def completed():
                    with closing(connect(dbname)) as conn, conn.cursor() as cur:
                        cur.execute(
                            "SELECT state::text, attempts FROM character_experience_jobs WHERE id=3"
                        )
                        return cur.fetchone() == ("succeeded", 2)

                wait_until(completed, timeout=30)
                with closing(connect(dbname)) as conn, conn.cursor() as cur:
                    cur.execute(
                        "SELECT job_id,count(*) FROM scheduler_completion_proof GROUP BY job_id"
                    )
                    assert cur.fetchall() == [(3, 1)]
                    cur.execute(
                        "SELECT count(DISTINCT render_generation_id) FROM character_experiences WHERE id=ANY(%s)",
                        (dead["experience_ids"],),
                    )
                    assert cur.fetchone() == (1,)
                with (
                    closing(connect(dbname)) as conn,
                    pytest.raises(ExperienceLeaseLostError),
                ):
                    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                        _complete_render(
                            cur,
                            job=dead,
                            source_rows=[],
                            validation=None,
                            render_model="TEST",
                            cfg=load_settings().orrery.experiences,
                        )
                status = requests.get(
                    env["NEXUS_API_URL"] + "/runtime/status", timeout=10
                ).json()
                assert status["jobs"]["scheduler"]["state"] == "owner"
                assert str(second.pid) in status["jobs"]["scheduler"]["owner_id"]
                print(
                    f"Restarted gateway pid={second.pid}; job=(succeeded,2); successful transitions=1; dead nonce rejected",
                    flush=True,
                )
                print(
                    "SIGKILL runtime scheduler: "
                    + json.dumps(status["jobs"]["scheduler"], sort_keys=True),
                    flush=True,
                )
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
                down = subprocess.run(
                    [sys.executable, "-m", "nexus.cli", "down"],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert down.returncode == 0, down.stdout + down.stderr
                print(f"nexus down ({port}): {down.stdout.strip()}", flush=True)


@pytest.fixture
def delayed_mock_openai_server(tmp_path):
    """Run the actual TEST server with request-start logging for the kill proof."""
    import os
    import subprocess
    import sys
    import requests
    from pathlib import Path
    from tests.test_logon_mock_integration import _bound_listener

    with _bound_listener() as listener:
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        log_path = tmp_path / "mock_openai.log"
        runner = tmp_path / "test_provider_process.py"
        runner.write_text(
            'import logging, sys, uvicorn\nlogging.basicConfig(level=logging.INFO)\nuvicorn.run("nexus.api.mock_openai:app", fd=int(sys.argv[1]))\n'
        )
        with log_path.open("w") as log:
            process = subprocess.Popen(
                [sys.executable, str(runner), str(listener.fileno())],
                env={**os.environ, "PYTHONPATH": str(Path.cwd())},
                stdout=log,
                stderr=subprocess.STDOUT,
                pass_fds=(listener.fileno(),),
            )
        try:

            def ready():
                assert process.poll() is None, log_path.read_text()
                try:
                    return requests.get(url + "/health", timeout=0.2).ok
                except requests.RequestException:
                    return False

            wait_until(ready, timeout=20)
            yield url + "/v1"
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
