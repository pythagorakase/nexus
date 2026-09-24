"""Real slot databases exercise ownership, idle recovery and interactive priority."""

from contextlib import closing
from time import monotonic, sleep
from uuid import uuid4

import pytest
from psycopg2.extras import RealDictCursor

from nexus.api import narrative_lease
from nexus.agents.orrery.job_queues import load_job_queues_sync
from nexus.config import load_settings_as_dict
from nexus.jobs.scheduler import SlotScheduler
from tests.pg_fixtures import connect, seed_protagonist
from tests.test_orrery.test_narration_job_fencing_pg import (
    _materialize_pending_resolution,
    _enqueue,
)

pytestmark = pytest.mark.requires_postgres


def scheduler_settings():
    settings = load_settings_as_dict()
    settings["runtime"]["scheduler"].update(
        poll_interval_seconds=0.02,
        generation_wait_seconds=0.01,
        heartbeat_interval_seconds=0.1,
        lease_duration_seconds=2,
    )
    return settings


def wait_until(predicate, timeout=5):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.01)
    raise AssertionError("Scheduler did not reach the expected durable state")


def job_state(dbname):
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT state::text, attempts FROM orrery_narration_jobs ORDER BY id"
        )
        return cur.fetchall()


def seed_narration(dbname):
    seed_protagonist(dbname)
    with closing(connect(dbname)) as conn:
        resolution, chunk = _materialize_pending_resolution(conn, label="scheduler")
        _enqueue(conn, resolution)
    return chunk


def test_scheduler_single_owner_and_expired_takeover(offline_gate_db):
    first = SlotScheduler(4, dbname=offline_gate_db)
    second = SlotScheduler(4, dbname=offline_gate_db)
    assert first.acquire()
    assert not second.acquire()
    assert second.run_pass() == {"owner": False, "drained": False}
    with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE deferred_work_scheduler SET expires_at = clock_timestamp() - interval '1 second'"
        )
    assert second.acquire()
    assert not first.renew()
    first.release()
    assert second.renew()
    second.release()


def test_scheduler_idle_drain_waits_for_generation(offline_gate_db):
    seed_narration(offline_gate_db)
    session = str(uuid4())
    with closing(connect(offline_gate_db)) as conn:
        assert (
            narrative_lease.acquire_generation_lease(
                conn, session_id=session, operation="continue", stale_timeout_seconds=60
            )
            is None
        )
    scheduler = SlotScheduler(4, dbname=offline_gate_db, settings=scheduler_settings())
    scheduler.start()
    try:
        sleep(0.15)
        assert job_state(offline_gate_db) == [("queued", 0)]
        with closing(connect(offline_gate_db)) as conn:
            narrative_lease.finish_generation(
                conn, session_id=session, status="complete"
            )
        wait_until(lambda: job_state(offline_gate_db) == [("succeeded", 1)])
        with closing(connect(offline_gate_db)) as conn:
            status = load_job_queues_sync(conn)
        assert status["scheduler"]["active"]
        assert status["scheduler"]["owner_id"] == scheduler.owner
        assert status["queues"]["narration"]["counts"]["succeeded"] == 1
        assert set(status["queues"]) == {
            "narration",
            "experience_render",
            "retrograde_maturation",
            "correspondence_compaction",
            "relationship_milestone",
            "narrative_embedding",
            "narrative_summary",
        }
    finally:
        scheduler.stop()
    with closing(connect(offline_gate_db)) as conn:
        assert not load_job_queues_sync(conn)["scheduler"]["active"]


def test_scheduler_next_start_resumes_expired_job(offline_gate_db):
    seed_narration(offline_gate_db)
    first = SlotScheduler(4, dbname=offline_gate_db)
    assert first.acquire()
    with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE orrery_narration_jobs SET state='leased', attempts=1, locked_by='stopped', lease_nonce=%s, lease_until=clock_timestamp()-interval '1 second'",
            (str(uuid4()),),
        )
    first.stop()
    successor = SlotScheduler(4, dbname=offline_gate_db, settings=scheduler_settings())
    successor.start()
    try:
        wait_until(lambda: job_state(offline_gate_db) == [("succeeded", 2)])
    finally:
        successor.stop()


def test_maturation_completion_rejects_stale_nonce(offline_gate_db):
    from nexus.agents.orrery.retrograde_maturation import (
        _mark_maturation_succeeded,
        MaturationLeaseLostError,
    )

    character, entity = seed_protagonist(offline_gate_db)
    from tests.test_orrery.test_narration_job_fencing_pg import _insert_chunk

    with closing(connect(offline_gate_db)) as conn:
        with conn, conn.cursor() as cur:
            chunk = _insert_chunk(cur, "maturation fence")
            nonce = str(uuid4())
            cur.execute(
                """INSERT INTO orrery_maturation_jobs
                (entity_id, entity_kind, entity_subtype_id, entity_name, slot, requesting_chunk_id, declaration, state, locked_by, lease_nonce, lease_until)
                VALUES (%s, 'character', %s, 'Fixture Player', '4', %s, '{}', 'leased', 'new-owner', %s, now()+interval '1 minute') RETURNING id""",
                (entity, character, chunk, nonce),
            )
            job = cur.fetchone()[0]
        with pytest.raises(MaturationLeaseLostError):
            with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                _mark_maturation_succeeded(
                    cur,
                    row={
                        "job_id": job,
                        "locked_by": "new-owner",
                        "lease_nonce": str(uuid4()),
                    },
                    manifest={"stale": True},
                )
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            _mark_maturation_succeeded(
                cur,
                row={"job_id": job, "locked_by": "new-owner", "lease_nonce": nonce},
                manifest={
                    "schema_version": "orrery_retrograde_maturation_manifest.v1",
                    "current": True,
                },
            )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT state::text, result_manifest FROM orrery_maturation_jobs WHERE id=%s",
                (job,),
            )
            assert cur.fetchone() == (
                "succeeded",
                {
                    "schema_version": "orrery_retrograde_maturation_manifest.v1",
                    "current": True,
                },
            )


def test_scheduler_milestone_recovery_preserves_anchor_age_and_idempotency(
    offline_gate_db,
):
    """Recover old crossings once, keeping unanchored ones on the latest head."""
    from nexus.agents.orrery.relationship_provenance import relationship_producer
    from tests.test_orrery.test_narration_job_fencing_pg import _insert_chunk

    first, _ = seed_protagonist(offline_gate_db)
    second, _ = seed_protagonist(offline_gate_db, name="Second Player")
    with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
        older = _insert_chunk(cur, "Older accepted turn")
        head = _insert_chunk(cur, "Current accepted turn")
        with relationship_producer(cur, "manual"):
            cur.execute(
                "INSERT INTO character_relationships (character1_id,character2_id,relationship_type,valence_current,dynamic,recent_events,history) VALUES (%s,%s,'friend',0,'Fixture','Fixture','Fixture'),(%s,%s,'friend',0,'Fixture','Fixture','Fixture')",
                (first, second, second, first),
            )
        with relationship_producer(cur, "manual", source_chunk_id=older):
            cur.execute(
                "UPDATE character_relationships SET valence_current=0.5 WHERE character1_id=%s",
                (first,),
            )
        with relationship_producer(cur, "manual"):
            cur.execute(
                "UPDATE character_relationships SET valence_current=0.5 WHERE character1_id=%s",
                (second,),
            )
        cur.execute(
            "UPDATE relationship_versions SET created_at=clock_timestamp()-interval '2 minutes'"
        )
        with relationship_producer(cur, "manual", source_chunk_id=head):
            cur.execute(
                "UPDATE character_relationships SET valence_current=-0.5 WHERE character1_id=%s",
                (first,),
            )
    scheduler = SlotScheduler(4, dbname=offline_gate_db)
    result = scheduler.run_pass()
    assert result["relationship_milestone_queue"] == 2
    assert scheduler.run_pass()["relationship_milestone_queue"] == 0
    with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT v.source_chunk_id,e.tick_chunk_id FROM relationship_milestone_queue q JOIN relationship_versions v ON v.id=q.version_id JOIN world_events e ON e.id=q.event_id ORDER BY v.id"
        )
        assert cur.fetchall() == [(older, older), (None, head)]
        assert load_job_queues_sync(conn)["queues"]["relationship_milestone"][
            "counts"
        ] == {"pending": 1}


def test_scheduler_gateway_restart_recovers_leased_job(
    offline_gate_db, monkeypatch, tmp_path, mock_openai_server
):
    """The actual gateway lifespan releases its lease and recovers at next start."""
    from tests.scheduler_helpers import gateway_lane, route_slot, test_provider_config

    test_provider_config(tmp_path, mock_openai_server, monkeypatch)
    route_slot(monkeypatch, offline_gate_db)
    seed_narration(offline_gate_db)
    session = str(uuid4())
    with closing(connect(offline_gate_db)) as conn:
        assert (
            narrative_lease.acquire_generation_lease(
                conn, session_id=session, operation="continue", stale_timeout_seconds=60
            )
            is None
        )
    with gateway_lane(monkeypatch) as first:
        assert job_state(offline_gate_db) == [("queued", 0)]
        with closing(connect(offline_gate_db)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE orrery_narration_jobs SET state='leased', attempts=1, locked_by='interrupted', lease_nonce=%s, lease_until=clock_timestamp()-interval '1 second'",
                (str(uuid4()),),
            )
    with closing(connect(offline_gate_db)) as conn:
        assert not load_job_queues_sync(conn)["scheduler"]["active"]
        narrative_lease.finish_generation(conn, session_id=session, status="complete")
    with gateway_lane(monkeypatch) as successor:
        assert first.owner != successor.owner
        wait_until(lambda: job_state(offline_gate_db) == [("succeeded", 2)])
    with closing(connect(offline_gate_db)) as conn:
        assert not load_job_queues_sync(conn)["scheduler"]["active"]


from tests.test_logon_mock_integration import mock_openai_server  # noqa: E402,F401
