"""Explicitly authorized two-call summary proof on a disposable save_04 clone."""

from contextlib import closing
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
import tomlkit

from nexus.api.summary_triggers import SummaryTask, schedule_summary_generation
from nexus.config import load_settings_as_dict
from nexus.jobs.scheduler import SlotScheduler
from nexus.telemetry import usage
from scripts.summarize_narrative import SummaryGenerator
from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.live_llm,
    pytest.mark.skipif(
        os.environ.get("NEXUS_800B_PAID_PROOF") != "1",
        reason="Requires explicit two-call summary authorization",
    ),
]


def test_scheduler_paid_episode_and_season(monkeypatch, tmp_path):
    """Call the configured real provider once per summary, with SDK retries off."""
    config = tomlkit.parse(Path("nexus.toml").read_text())
    config["runtime"]["state_dir"] = str(tmp_path / "runtime")
    config["runtime"]["scheduler"]["summaries"]["max_attempts"] = 1
    config["summaries"]["structured_output_retries"] = 0
    config_path = tmp_path / "paid.toml"
    config_path.write_text(tomlkit.dumps(config))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config_path))
    initialize = SummaryGenerator._initialize_provider
    issued = []

    def bounded_provider(self, mode):
        # This wraps the real SDK; no fabricated responses or credentials.
        provider = initialize(self, mode)
        provider.client.max_retries = 0
        issued.append(mode)
        assert len(issued) <= 2, "The authorized two-call proof budget is exhausted"
        return provider

    monkeypatch.setattr(SummaryGenerator, "_initialize_provider", bounded_provider)
    with disposable_slot_database(
        "qa640_800b_paid", source_db="save_04", include_data=True
    ) as dbname:
        session = str(uuid4())
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            # Isolate already-caused summary work; touch only the disposable clone.
            cur.execute("DELETE FROM correspondence_compaction_jobs")
            cur.execute("DELETE FROM narrative_parent_embedding_claims")
            cur.execute("DELETE FROM narrative_embedding_jobs")
            cur.execute("DELETE FROM narrative_summary_jobs")
            cur.execute("DELETE FROM relationship_milestone_queue")
            cur.execute(
                "UPDATE orrery_resolutions SET promotion_status='promoted' WHERE promotion_status='pending'"
            )
            cur.execute("UPDATE episodes SET summary=NULL WHERE season=1 AND episode=2")
            cur.execute("UPDATE seasons SET summary=NULL WHERE id=1")
            schedule_summary_generation(
                [SummaryTask("episode", 1, 2), SummaryTask("season", 1)],
                cur=cur,
                session_id=session,
            )
        scheduler = SlotScheduler(4, dbname=dbname, settings=load_settings_as_dict())
        result = scheduler.run_pass(
            narration_limit=0, experience_limit=0, maturation_limit=0
        )
        assert result["narrative_summary_jobs"] == 2
        assert issued == ["episode", "season"]
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT kind, state::text, attempts, generation_session_id::text FROM narrative_summary_jobs ORDER BY id"
            )
            jobs = cur.fetchall()
            assert all(row[1:3] == ("succeeded", 1) for row in jobs)
            cur.execute(
                "SELECT length(summary->>'summary') FROM episodes WHERE season=1 AND episode=2 UNION ALL SELECT length(summary->>'summary') FROM seasons WHERE id=1"
            )
            lengths = [row[0] for row in cur.fetchall()]
            assert len(lengths) == 2 and all(lengths)
        events = [
            json.loads(line)
            for path in usage._config.usage_dir.glob("*.jsonl")
            for line in path.read_text().splitlines()
        ]
        assert len(events) == 2, events
        assert all(
            event["provider"] != "test"
            and event["total_tokens"] > 0
            and event["run_id"] == session
            for event in events
        )
        evidence = {
            "database": dbname,
            "jobs": jobs,
            "summary_lengths": lengths,
            "usage": events,
        }
        path = Path("docs/qa/800-embedding-summaries/paid-proof.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, indent=2) + "\n")
        print("PAID PROOF " + json.dumps(evidence, sort_keys=True), flush=True)
