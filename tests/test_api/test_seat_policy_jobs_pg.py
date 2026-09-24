"""Real TEST acceptance and durable seat identities on a populated save clone."""

from contextlib import closing
import json
import logging
import os

from psycopg2.extras import Json
import pytest
import requests
import tomlkit

from nexus.config import load_settings, load_settings_as_dict
from nexus.jobs.scheduler import SlotScheduler
from tests.pg_fixtures import connect, disposable_slot_database
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
    with disposable_slot_database(
        "qa640_814_seats", source_db="save_04", include_data=True
    ) as dbname:
        print(f"Migration 126 runner target: {dbname}", flush=True)
        route_slot(monkeypatch, dbname)
        from nexus.api import slot_endpoints

        monkeypatch.setattr(slot_endpoints, "slot_dbname", lambda slot: dbname)
        from scripts.stamp_lore_pass_baseline import refresh_tail_fingerprint

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "SELECT version FROM schema_migrations WHERE version LIKE '126%'"
            )
            assert cur.fetchone() is not None
            cur.execute("UPDATE global_variables SET model='TEST', gaia_model='TEST'")
            for table in TABLES:
                cur.execute(
                    f"UPDATE {table} SET state='stale_rejected' WHERE state IN ('queued','leased','failed')"
                )
        _, _, fingerprint = refresh_tail_fingerprint(dbname=dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE incubator SET lore_pass_baseline=jsonb_set(lore_pass_baseline, '{config_fingerprint}', to_jsonb(%s::text), false) WHERE lore_pass_baseline IS NOT NULL",
                (fingerprint,),
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
                # Isolate this identity proof from unrelated embedding and milestone work.
                cur.execute("DELETE FROM narrative_parent_embedding_claims")
                cur.execute("DELETE FROM narrative_embedding_jobs")
                cur.execute("DELETE FROM relationship_milestone_queue")
                cur.execute(
                    "UPDATE orrery_resolutions SET promotion_status='promoted' WHERE promotion_status='pending'"
                )
            print("Frozen jobs after repin: " + json.dumps(before), flush=True)
            result = SlotScheduler(
                4, dbname=dbname, settings=load_settings_as_dict()
            ).run_pass(narration_limit=0, experience_limit=1, maturation_limit=1)
            print("Scheduler pass: " + json.dumps(result), flush=True)
            for table in TABLES:
                assert any(
                    f"{table} job " in record.message
                    and "uses persisted model=TEST" in record.message
                    for record in caplog.records
                ), table
