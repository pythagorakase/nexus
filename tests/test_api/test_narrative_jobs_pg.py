"""Real acceptance, TEST summaries, and cached embedding on disposable slots."""

from contextlib import closing
import asyncio
import json
import sys
import traceback
from uuid import uuid4

import pytest

from nexus.agents.orrery.job_queues import load_job_queues_sync
from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.api.narrative_generation import write_to_incubator
from nexus.api.narrative_lease import claim_parent_embedding, finish_generation
from nexus.api.summary_triggers import SummaryTask, schedule_summary_generation
from nexus.config import load_settings_as_dict
from nexus.jobs.narrative_jobs import require_lease
from nexus.jobs.scheduler import SlotScheduler
from nexus.telemetry import usage
from tests.pg_fixtures import connect
from tests.scheduler_helpers import test_provider_config as configure_test
from tests.test_api.test_acceptance_staging_pg import (
    acceptance_slot,
    draft,
    own_draft,
)
from tests.test_logon_mock_integration import mock_openai_server

pytestmark = pytest.mark.requires_postgres


@pytest.mark.parametrize("transition", ["new_episode", "new_season"])
def test_scheduler_accepts_summary_and_embeds_once_in_process(
    acceptance_slot, monkeypatch, tmp_path, mock_openai_server, transition
):
    """Accept a transition, recover expired leases, and prove no worker spawn."""
    configure_test(tmp_path, mock_openai_server, monkeypatch)
    dbname, parent, resolution = acceptance_slot
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        data = draft(parent, resolution, session)
        data["metadata_updates"]["chronology"]["episode_transition"] = transition
        asyncio.run(write_to_incubator(conn, data))
        finish_generation(conn, session_id=session, status="complete")
        child = commit_incubator_to_database_sync(conn, session, slot=4)
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT kind, season, episode, state::text, generation_session_id::text FROM narrative_summary_jobs"
            )
            expected = [("episode", 1, 1, "queued", session)]
            if transition == "new_season":
                expected.append(("season", 1, None, "queued", session))
            assert cur.fetchall() == expected
        next_session = own_draft(conn, child)
        assert claim_parent_embedding(
            conn, session_id=next_session, parent_chunk_id=child
        )
        finish_generation(conn, session_id=next_session, status="complete")
        with conn, conn.cursor() as cur:
            cur.execute("SELECT chunk_id, state::text FROM narrative_embedding_jobs")
            assert cur.fetchall() == [(parent, "queued")]
            for table in ("narrative_embedding_jobs", "narrative_summary_jobs"):
                cur.execute(
                    f"UPDATE {table} SET state='leased', attempts=1, locked_by='crashed', lease_nonce=%s, lease_until=clock_timestamp()-interval '1 second'",
                    (str(uuid4()),),
                )

    # Match a gateway that already holds the real embedder in its process cache.
    from nexus.agents.memnon.utils.embedding_manager import (
        _get_or_load_sentence_transformer,
    )

    settings = load_settings_as_dict()
    models = settings["Agent Settings"]["MEMNON"]["models"]
    active = {name: config for name, config in models.items() if config["is_active"]}
    cached = {
        name: _get_or_load_sentence_transformer(config["local_path"])
        for name, config in active.items()
    }
    spawned = []
    recording = [True]

    def audit(event, args):
        if recording[0] and event in {
            "subprocess.Popen",
            "os.posix_spawn",
            "os.fork",
            "os.exec",
        }:
            if any(
                frame.filename.endswith("/jobs/embeddings.py")
                for frame in traceback.extract_stack()
            ):
                spawned.append(event)

    sys.addaudithook(audit)
    scheduler = SlotScheduler(4, dbname=dbname)
    try:
        result = scheduler.run_pass(
            narration_limit=0, experience_limit=0, maturation_limit=0
        )
    finally:
        recording[0] = False
    assert spawned == []
    assert result["narrative_embedding_jobs"] == 1
    assert result["narrative_summary_jobs"] == len(expected)
    for name, config in active.items():
        assert _get_or_load_sentence_transformer(config["local_path"]) is cached[name]
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT summary FROM episodes WHERE season=1 AND episode=1")
        assert cur.fetchone()[0]["summary"]
        if transition == "new_season":
            cur.execute("SELECT summary FROM seasons WHERE id=1")
            assert cur.fetchone()[0]["summary"]
        cur.execute(
            "SELECT embedding_generated_at FROM narrative_chunks WHERE id=%s", (parent,)
        )
        stamp = cur.fetchone()[0]
        assert stamp is not None
        for name, config in active.items():
            cur.execute(
                f"SELECT count(*) FROM chunk_embeddings_{config['dimensions']:04d}d WHERE chunk_id=%s AND model=%s",
                (parent, name),
            )
            assert cur.fetchone() == (1,)
        for table in ("narrative_embedding_jobs", "narrative_summary_jobs"):
            cur.execute(f"SELECT state::text, attempts FROM {table}")
            assert cur.fetchall() == [("succeeded", 2)] * (
                len(expected) if table == "narrative_summary_jobs" else 1
            )
    assert (
        scheduler.run_pass(narration_limit=0, experience_limit=0, maturation_limit=0)[
            "narrative_embedding_jobs"
        ]
        == 0
    )
    with closing(connect(dbname)) as conn:
        status = load_job_queues_sync(conn)
        assert status["queues"]["narrative_embedding"]["counts"]["succeeded"] == 1
        assert status["queues"]["narrative_summary"]["counts"]["succeeded"] == len(
            expected
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT embedding_generated_at FROM narrative_chunks WHERE id=%s",
                (parent,),
            )
            assert cur.fetchone()[0] == stamp
    events = [
        json.loads(line)
        for path in usage._config.usage_dir.glob("*.jsonl")
        for line in path.read_text().splitlines()
    ]
    summaries = [event for event in events if event["seat"] == "summaries"]
    assert len(summaries) == len(expected)
    assert summaries[0]["run_id"] == session
    print(
        f"In-process embedding: processes={spawned}, chunk={parent}, stamp={stamp}; summary usage={summaries}"
    )


def test_summary_queue_transaction_and_terminal_failure(offline_gate_db):
    """A rolled-back transition has no plan; exhausted work retains its error."""
    session = str(uuid4())
    with closing(connect(offline_gate_db)) as conn:
        with pytest.raises(ValueError, match="rollback"):
            with conn, conn.cursor() as cur:
                schedule_summary_generation(
                    [SummaryTask("season", 1)], cur=cur, session_id=session
                )
                raise ValueError("rollback")
        with conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM narrative_summary_jobs")
            assert cur.fetchone() == (0,)
            schedule_summary_generation(
                [SummaryTask("season", 1)], cur=cur, session_id=session
            )
            schedule_summary_generation(
                [SummaryTask("season", 1)], cur=cur, session_id=session
            )
            cur.execute("SELECT count(*) FROM narrative_summary_jobs")
            assert cur.fetchone() == (1,)
    settings = load_settings_as_dict()
    settings["runtime"]["scheduler"]["summaries"]["max_attempts"] = 1
    scheduler = SlotScheduler(4, dbname=offline_gate_db, settings=settings)
    with pytest.raises(RuntimeError, match="Summary provider returned no summary"):
        scheduler.run_pass(narration_limit=0, experience_limit=0, maturation_limit=0)
    with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT state::text, attempts, error_class FROM narrative_summary_jobs"
        )
        assert cur.fetchone() == ("failed", 1, "RuntimeError")
        cur.execute("SELECT count(*) FROM seasons WHERE summary IS NOT NULL")
        assert cur.fetchone() == (0,)


def test_summary_completion_rejects_stale_nonce(offline_gate_db):
    """An expired worker cannot write a replacement owner's summary."""
    with closing(connect(offline_gate_db)) as conn:
        with conn, conn.cursor() as cur:
            schedule_summary_generation(
                [SummaryTask("season", 1)], cur=cur, session_id=str(uuid4())
            )
            cur.execute(
                "UPDATE narrative_summary_jobs SET state='leased', locked_by='current', lease_nonce=%s, lease_until=clock_timestamp()+interval '1 minute' RETURNING id",
                (str(uuid4()),),
            )
            job_id = cur.fetchone()[0]
        with pytest.raises(RuntimeError, match="lost its execution lease"):
            with conn, conn.cursor() as cur:
                require_lease(
                    cur,
                    "narrative_summary_jobs",
                    {"id": job_id, "locked_by": "current", "lease_nonce": str(uuid4())},
                )


def test_scheduler_new_queue_status_and_interactive_priority(
    acceptance_slot, monkeypatch, tmp_path, mock_openai_server
):
    """A live generation keeps both plans queued across runtime and CLI status."""
    import requests

    from nexus.jobs.embeddings import enqueue_embedding
    from tests.scheduler_helpers import gateway_lane, route_slot, run_cli

    configure_test(tmp_path, mock_openai_server, monkeypatch)
    dbname, parent, _ = acceptance_slot
    route_slot(monkeypatch, dbname)
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "8016")
    monkeypatch.setenv("NEXUS_API_URL", "http://127.0.0.1:8016")
    with closing(connect(dbname)) as conn:
        session = own_draft(conn, parent)
        with conn, conn.cursor() as cur:
            enqueue_embedding(cur, parent, session)
            schedule_summary_generation(
                [SummaryTask("episode", 1, 1)], cur=cur, session_id=session
            )
        try:
            with gateway_lane(monkeypatch):
                response = requests.get(
                    "http://127.0.0.1:8016/runtime/status", timeout=10
                )
                response.raise_for_status()
                queues = response.json()["jobs"]["queues"]
                for name in ("narrative_embedding", "narrative_summary"):
                    assert queues[name]["counts"]["queued"] == 1
                    assert queues[name]["non_terminal_jobs"][0]["attempts"] == 0
                cli_jobs = run_cli(monkeypatch, "jobs", "--slot", "4")
                assert (
                    "narrative_embedding" in cli_jobs
                    and "narrative_summary" in cli_jobs
                )
                cli_status = run_cli(monkeypatch, "status", "--json")
                assert (
                    "narrative_embedding" in cli_status
                    and "narrative_summary" in cli_status
                )
        finally:
            finish_generation(conn, session_id=session, status="complete")
