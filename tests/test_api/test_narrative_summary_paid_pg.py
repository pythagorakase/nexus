"""Explicitly authorized two-call summary proof on a seeded two-episode story.

The proof needs only a story with a finished second episode in its first
season: ``seed_two_episode_story`` seeds one on a template clone through the
accepted-turn factory, so no owner save is cloned.
"""

from contextlib import closing
from datetime import timedelta
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
import tomlkit

from nexus.api.summary_triggers import SummaryTask, schedule_summary_generation
from nexus.config import load_settings
from nexus.jobs.scheduler import SlotScheduler
from nexus.telemetry import usage
from nexus.jobs.summarize_narrative import SummaryGenerator
from tests.pg_fixtures import (
    FIXTURE_TURN_CHOICES,
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    seed_accepted_turn,
    seed_played_story,
)

pytestmark = [
    pytest.mark.requires_postgres,
    pytest.mark.live_llm,
    pytest.mark.skipif(
        os.environ.get("NEXUS_800B_PAID_PROOF") != "1",
        reason="Requires explicit two-call summary authorization",
    ),
]


# The slot the scheduler serves; routed to the seeded clone.
SUMMARY_SLOT = 4
# Accepted turns per episode.
EPISODE_TURNS = 2


def seed_two_episode_story(dbname: str) -> None:
    """Seed season 1 with two finished episodes and a third begun.

    Episode 1 is the played story's opening turns; each later episode starts
    with an accepted ``new_episode`` turn, as play records one. Episode 2
    therefore holds ``EPISODE_TURNS`` accepted chunks and is closed by the
    first turn of episode 3. The clone's slot must be routed first.
    """
    chunk_ids = seed_played_story(dbname, turns=EPISODE_TURNS, slot=SUMMARY_SLOT)
    for episode in (2, 3):
        turns = EPISODE_TURNS if episode == 2 else 1
        for turn in range(1, turns + 1):
            chunk_ids.append(
                seed_accepted_turn(
                    dbname,
                    user_text=FIXTURE_TURN_CHOICES[0],
                    storyteller_text=(
                        f"Episode {episode}, turn {turn}: Fixture Player crosses "
                        "Fixture Plaza once more as the lamps come on."
                    ),
                    choices=list(FIXTURE_TURN_CHOICES),
                    choice_text=FIXTURE_TURN_CHOICES[0],
                    time_delta=timedelta(minutes=5),
                    episode_transition="new_episode" if turn == 1 else "continue",
                    slot=SUMMARY_SLOT,
                )
            )
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT cm.season, cm.episode, count(*) FROM chunk_metadata cm "
            "WHERE cm.chunk_id = ANY(%s) GROUP BY 1, 2 ORDER BY 1, 2",
            (chunk_ids,),
        )
        assert cur.fetchall() == [
            (1, 1, EPISODE_TURNS),
            (1, 2, EPISODE_TURNS),
            (1, 3, 1),
        ]


def queue_episode_and_season_summaries(dbname: str, session: str) -> None:
    """Clear the story's own queued work and queue the two proof summaries."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        # Isolate already-caused summary work; touch only the disposable clone.
        cur.execute("DELETE FROM correspondence_compaction_jobs")
        cur.execute("DELETE FROM narrative_parent_embedding_claims")
        cur.execute("DELETE FROM narrative_embedding_jobs")
        cur.execute("DELETE FROM narrative_summary_jobs")
        cur.execute("DELETE FROM relationship_milestone_queue")
        cur.execute(
            "UPDATE orrery_resolutions SET promotion_status='promoted' "
            "WHERE promotion_status='pending'"
        )
        cur.execute("UPDATE episodes SET summary=NULL WHERE season=1 AND episode=2")
        cur.execute("UPDATE seasons SET summary=NULL WHERE id=1")
        schedule_summary_generation(
            [SummaryTask("episode", 1, 2), SummaryTask("season", 1)],
            cur=cur,
            session_id=session,
        )


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
    wire_usage = []

    def bounded_provider(self, mode):
        # This wraps the real SDK; no fabricated responses or credentials.
        provider = initialize(self, mode)
        provider.client.max_retries = 0

        def capture_response(response):
            response.read()
            payload = response.json()
            wire_usage.append(
                {
                    "mode": mode,
                    "status": payload.get("status"),
                    "incomplete_details": payload.get("incomplete_details"),
                    "usage": payload.get("usage"),
                    "id": payload.get("id"),
                }
            )
            Path("docs/qa/800-embedding-summaries/paid-wire-usage.json").write_text(
                json.dumps(wire_usage, indent=2) + "\n"
            )

        provider.client._client.event_hooks["response"].append(capture_response)
        issued.append(mode)
        assert len(issued) <= 2, "The authorized two-call proof budget is exhausted"
        return provider

    monkeypatch.setattr(SummaryGenerator, "_initialize_provider", bounded_provider)
    with disposable_slot_database("qa640_800b_paid") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=SUMMARY_SLOT, dbname=dbname)
        seed_two_episode_story(dbname)
        session = str(uuid4())
        queue_episode_and_season_summaries(dbname, session)
        scheduler = SlotScheduler(SUMMARY_SLOT, dbname=dbname, settings=load_settings())
        error = None
        try:
            result = scheduler.run_pass(
                narration_limit=0,
                experience_limit=0,
                maturation_limit=0,
                experience_embedding_limit=0,
            )
        except Exception as exc:
            error = exc
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT kind, state::text, attempts, generation_session_id::text, id::text FROM narrative_summary_jobs ORDER BY id"
            )
            jobs = cur.fetchall()
            cur.execute(
                "SELECT length(summary->>'summary') FROM episodes WHERE season=1 AND episode=2 UNION ALL SELECT length(summary->>'summary') FROM seasons WHERE id=1"
            )
            lengths = [row[0] for row in cur.fetchall()]
            cur.execute(
                "SELECT 'episode' AS kind, summary FROM episodes WHERE season=1 AND episode=2 "
                "UNION ALL SELECT 'season' AS kind, summary FROM seasons WHERE id=1"
            )
            persisted_summaries = dict(cur.fetchall())
        events = [
            json.loads(line)
            for path in usage._config.usage_dir.glob("*.jsonl")
            for line in path.read_text().splitlines()
        ]
        evidence = {
            "database": dbname,
            "error": str(error) if error else None,
            "wire_usage": wire_usage,
            "jobs": jobs,
            "summary_lengths": lengths,
            "persisted_summaries": persisted_summaries,
            "usage": events,
        }
        path = Path("docs/qa/800-embedding-summaries/paid-proof.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, indent=2) + "\n")
        print("PAID PROOF " + json.dumps(evidence, sort_keys=True), flush=True)
        if error is not None:
            raise error
        assert result["narrative_summary_jobs"] == 2
        assert issued == ["episode", "season"]
        assert all(row[1:3] == ("succeeded", 1) for row in jobs)
        assert len(lengths) == 2 and all(lengths)
        assert len(events) == 2, events
        assert all(row[3] == session for row in jobs)
        # Each summary records under its numeric job id (#802).
        assert sorted(event["run_id"] for event in events) == sorted(
            row[4] for row in jobs
        )
        assert all(
            event["provider"] != "test" and event["total_tokens"] > 0
            for event in events
        )
