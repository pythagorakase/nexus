"""Real TEST acceptance and durable seat identities on a factory-played clone."""

from contextlib import closing
from datetime import timedelta
import json
import logging
import os

from psycopg2.extras import Json
import pytest
import requests
import tomlkit

from nexus.config import load_settings
from nexus.jobs.scheduler import SlotScheduler
from tests.pg_fixtures import (
    FIXTURE_TURN_CHOICES,
    connect,
    disposable_slot_database,
    seed_pending_turn,
    seed_played_story,
)
from tests.scheduler_helpers import gateway_lane, route_slot, run_cli
from tests.scheduler_helpers import test_provider_config as configure_test
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401

pytestmark = pytest.mark.requires_postgres
TABLES = (
    "character_experience_jobs",
    "orrery_maturation_jobs",
    "correspondence_compaction_jobs",
    "narrative_summary_jobs",
)


def test_accept_repin_and_scheduler_use_literal_seat_models(
    monkeypatch, tmp_path, request, caplog
):
    """Acceptance freezes all four queues; repinning cannot retarget dispatch."""
    caplog.set_level(logging.INFO, logger="nexus.config.story_model")
    configure_test(tmp_path, "http://127.0.0.1:1", monkeypatch)
    provider = request.getfixturevalue("mock_openai_server")
    config = configure_test(tmp_path, provider, monkeypatch)
    doc = tomlkit.parse(config.read_text())
    doc["storyteller"]["correspondence"]["floor_turns"] = 1
    config.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "8019")
    monkeypatch.setenv("NEXUS_API_URL", "http://127.0.0.1:8019")
    with disposable_slot_database("qa640_814_seats") as dbname:
        print(f"Migration 126 runner target: {dbname}", flush=True)
        route_slot(monkeypatch, dbname)
        # A played story whose off-screen cast has formed experience seeds and
        # whose correspondence crosses the compaction floor, with the next
        # turn staged for ``continue --choice 1``.
        seed_played_story(
            dbname,
            turns=4,
            cast=("Mara Quill", "Oren Vale"),
            time_delta=timedelta(hours=6),
            correspondence=True,
            slot=4,
        )
        seed_pending_turn(
            dbname,
            user_text=FIXTURE_TURN_CHOICES[0],
            storyteller_text="The pending fixture turn waits for the player's choice.",
            choices=list(FIXTURE_TURN_CHOICES),
            correspondence_writer_letter="Writer note for the pending fixture turn.",
            correspondence_gaia_letter="Gaia note for the pending fixture turn.",
        )

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "SELECT version FROM schema_migrations WHERE version LIKE '126%'"
            )
            assert cur.fetchone() is not None
            for table in TABLES:
                cur.execute(
                    f"UPDATE {table} SET state='stale_rejected' WHERE state IN ('queued','leased','failed')"
                )
        with gateway_lane(monkeypatch) as scheduler:
            scheduler.stop()
            output = run_cli(
                monkeypatch, "continue", "--slot", "4", "--choice", "1", "--json"
            )
            assert json.loads(output)["success"]
            # Arrange explicit accepting boundaries and a new named declaration in
            # the real TEST draft, so every deferred enqueue path is exercised.
            with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                cur.execute("SELECT session_id::text, metadata_updates FROM incubator")
                session, metadata = cur.fetchone()
                metadata["scene_boundary"] = True
                metadata.setdefault("chronology", {})[
                    "episode_transition"
                ] = "new_season"
                cur.execute(
                    "UPDATE incubator SET metadata_updates=%s, storyteller_text=storyteller_text || ' Policy Courier arrives.', new_entities=%s",
                    (
                        Json(metadata),
                        Json(
                            [
                                {
                                    "kind": "character",
                                    "name": "Policy Courier",
                                    "summary": "A courier carrying a sealed message.",
                                }
                            ]
                        ),
                    ),
                )
            response = requests.post(
                f"{os.environ['NEXUS_API_URL']}/api/narrative/approve/{session}?slot=4&commit=true",
                timeout=120,
            )
            assert response.status_code == 200, response.text
            before = {}
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                for table in TABLES:
                    cur.execute(
                        f"SELECT id, resolved_model, resolved_source FROM {table} WHERE generation_session_id=%s ORDER BY id",
                        (session,),
                    )
                    before[table] = cur.fetchall()
                    assert before[table], table
                    assert all(row[1] == "TEST" for row in before[table]), before
                cur.execute(
                    "SELECT story_pin->>'resolved_source' FROM generation_attempt_manifests WHERE generation_session_id=%s",
                    (session,),
                )
                assert all(row[0] is not None for row in cur.fetchall())
            # Use the public CLI/PATCH path, routed only to the disposable clone.
            replacement = (
                load_settings().global_.model.api_models["openai"].models[0].id
            )
            run_cli(monkeypatch, "model", "--slot", "4", "--set", replacement)
            run_cli(monkeypatch, "model", "--slot", "4")
            with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
                for table in TABLES:
                    cur.execute(
                        f"SELECT id, resolved_model, resolved_source FROM {table} WHERE generation_session_id=%s ORDER BY id",
                        (session,),
                    )
                    assert cur.fetchall() == before[table]
                # Dispatch the compaction belonging to this accepted TEST turn.
                cur.execute(
                    "UPDATE correspondence_compaction_jobs SET state='stale_rejected' "
                    "WHERE generation_session_id IS DISTINCT FROM %s AND state='queued'",
                    (session,),
                )
                # Isolate this identity proof from unrelated embedding and milestone work.
                cur.execute("DELETE FROM narrative_parent_embedding_claims")
                cur.execute("DELETE FROM narrative_embedding_jobs")
                cur.execute("DELETE FROM relationship_milestone_queue")
                cur.execute(
                    "UPDATE orrery_resolutions SET promotion_status='promoted' WHERE promotion_status='pending'"
                )
            print("Frozen jobs after repin: " + json.dumps(before), flush=True)
            result = SlotScheduler(4, dbname=dbname, settings=load_settings()).run_pass(
                narration_limit=0,
                experience_limit=1,
                maturation_limit=1,
                experience_embedding_limit=0,
            )
            print("Scheduler pass: " + json.dumps(result), flush=True)
            for table in TABLES:
                assert any(
                    f"{table} job {row[0]} uses persisted model=TEST" in record.message
                    for row in before[table]
                    for record in caplog.records
                ), table
            # Each queue's provider calls land in the ledger under the numeric
            # job id, and inspect-turn attaches them to the job row (#802).
            from nexus.telemetry import usage
            from nexus.telemetry.attempt_manifest import PROVIDER_JOB_SEATS

            events = [
                json.loads(line)
                for path in usage._config.usage_dir.glob("usage-*.jsonl")
                for line in path.read_text().splitlines()
            ]
            background = {
                seat for seats in PROVIDER_JOB_SEATS.values() for seat in seats
            }
            assert not [
                event
                for event in events
                if event["run_id"] == session and event["seat"] in background
            ]
            observation = json.loads(
                run_cli(
                    monkeypatch,
                    "inspect-turn",
                    "--slot",
                    "4",
                    "--session",
                    session,
                    "--json",
                )
            )["observation"]
            entries = {
                (entry["queue"], entry["id"]): entry
                for entry in observation["jobs"]["entries"]
            }
            joined = 0
            for queue, table in (
                ("experience_render", "character_experience_jobs"),
                ("retrograde_maturation", "orrery_maturation_jobs"),
                ("correspondence_compaction", "correspondence_compaction_jobs"),
                ("narrative_summary", "narrative_summary_jobs"),
            ):
                for job_id, _, _ in before[table]:
                    own = [
                        event
                        for event in events
                        if event["run_id"] == str(job_id)
                        and event["slot"] == 4
                        and event["seat"] in PROVIDER_JOB_SEATS[queue]
                    ]
                    job_usage = entries[(queue, job_id)]["usage"]
                    assert job_usage["run_id"] == str(job_id)
                    assert job_usage["events"] == len(own), (queue, job_id, own)
                    if own:
                        joined += 1
                        assert job_usage["provenance"] == "provider_usage_ledger"
                        assert job_usage["model"] == "TEST"
                        assert job_usage["input_tokens"] == sum(
                            event["input_tokens"] for event in own
                        )
            assert joined, "No provider-backed job of this turn recorded usage"
            totals = observation["usage_totals"]
            assert totals["background"]["events"] == sum(
                entry["usage"]["events"]
                for entry in entries.values()
                if "usage" in entry
            )
            print("Background usage: " + json.dumps(totals["background"]), flush=True)
