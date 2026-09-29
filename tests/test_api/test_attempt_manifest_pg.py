"""Real PostgreSQL and TEST-provider proof of attempt correlation and retention."""

from contextlib import closing
from datetime import timedelta
import json
import os
from uuid import uuid4

import pytest
import requests
import tomlkit

from nexus.telemetry.attempt_manifest import (
    finish_attempt,
    identity_hash,
    inspect_turn,
    manifest_scope,
    prune_manifests,
    start_attempt,
    update_validation,
)
from nexus.telemetry.prompt_window import PromptWindowRecord
from tests.pg_fixtures import (
    FIXTURE_TURN_CHOICES,
    connect,
    disposable_slot_database,
    seed_accepted_turn,
    seed_played_story,
    seed_relationship,
    seed_pending_turn,
)
from tests.scheduler_helpers import (
    gateway_lane,
    route_slot,
    run_cli,
    test_provider_config as configure_test,
)
from tests.test_logon_mock_integration import mock_openai_server  # noqa: F401

pytestmark = pytest.mark.requires_postgres
FIXTURE_CAST = ("Mara Quill", "Oren Vale")
# Hours between turns let the cast's needs come due, so the Orrery resolves.
FIXTURE_TURN_GAP = timedelta(hours=6)


def _stage_pending_turn(dbname):
    """Stage the draft the next ``continue --choice 1`` accepts, as play leaves it."""
    return seed_pending_turn(
        dbname,
        user_text=FIXTURE_TURN_CHOICES[0],
        storyteller_text="The pending fixture turn waits for the player's choice.",
        choices=list(FIXTURE_TURN_CHOICES),
        correspondence_writer_letter="Writer note for the pending fixture turn.",
        correspondence_gaia_letter="Gaia note for the pending fixture turn.",
    )


def test_manifest_reference_privacy_retention_and_readonly(monkeypatch):
    """A played clone keeps its canon; pruning touches terminal manifests only."""
    with disposable_slot_database("qa640_764_manifest") as dbname:
        route_slot(monkeypatch, dbname)
        chunk_ids = seed_played_story(dbname, turns=3, slot=4)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute("SELECT id, md5(raw_text) FROM narrative_chunks ORDER BY id")
            original = cur.fetchall()
        assert [row[0] for row in original] == chunk_ids
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            sessions = [str(uuid4()) for _ in range(3)]
            for session in sessions:
                cur.execute(
                    "INSERT INTO narrative_generation_sessions (session_id, operation, status) VALUES (%s,'continue','initiated')",
                    (session,),
                )
        for session in sessions:
            record = PromptWindowRecord(
                generation_session=session,
                seat="skald_writer",
                attempt=1,
                model="TEST",
                block_tokens={"story": 3},
                input_tokens=3,
                effective_ceiling=100,
                policy_headroom=10,
                headroom=97,
            )
            with manifest_scope(lambda: connect(dbname)):
                start_attempt(
                    record,
                    blocks=[
                        {
                            "kind": "story",
                            "tokens": 3,
                            "sha256": identity_hash("private canon"),
                        }
                    ],
                    system_prompt="private system",
                    prompt="private canon",
                    settings={"model": "TEST"},
                    wire_schema={"type": "object"},
                )
                record.validation_notes = [
                    {
                        "repair": "active-extend-expiry",
                        "entity_kind": "character",
                        "entity_id": 42,
                        "entity_name": "private name",
                        "tag": "private tag",
                    },
                    {
                        "repair": "scene-reset-crossings",
                        "moved": ["private name"],
                        "dropped": [],
                    },
                    {
                        "rejection": "wire-contract-violation",
                        "error": "private generated prose",
                    },
                ]
                update_validation(record)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE narrative_generation_sessions SET terminal_outcome='discarded' WHERE session_id=ANY(%s::uuid[])",
                (sessions[:2],),
            )
            cur.execute(
                "UPDATE generation_attempt_manifests SET created_at=now()-interval '90 days' WHERE generation_session_id=ANY(%s::uuid[])",
                ([sessions[0], sessions[2]],),
            )
            cur.execute(
                "SELECT row_to_json(m)::text FROM generation_attempt_manifests m WHERE generation_session_id=ANY(%s::uuid[])",
                (sessions,),
            )
            assert all("private" not in row[0] for row in cur.fetchall())
        with closing(connect(dbname)) as conn:
            result = inspect_turn(conn, session=sessions[0])
            assert result["manifests"][0]["validation"][1]["moved_count"] == 1
            with conn, conn.cursor() as cur:
                cur.execute("SHOW transaction_read_only")
                assert cur.fetchone()[0] == "on"
        output = run_cli(monkeypatch, "prune-manifests", "--slot", "4", "--json")
        assert json.loads(output)["manifests_pruned"] == 1
        with closing(connect(dbname)) as conn:
            assert prune_manifests(conn, 30) == 0
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT generation_session_id::text FROM generation_attempt_manifests WHERE generation_session_id=ANY(%s::uuid[]) ORDER BY generation_session_id",
                    (sessions,),
                )
                assert {row[0] for row in cur.fetchall()} == set(sessions[1:])
                cur.execute(
                    "SELECT count(*) FROM narrative_generation_sessions WHERE session_id=ANY(%s::uuid[])",
                    (sessions,),
                )
                assert cur.fetchone()[0] == 3
                cur.execute(
                    "SELECT id, md5(raw_text) FROM narrative_chunks ORDER BY id"
                )
                assert cur.fetchall() == original
            print(f"Pruning preserved {len(original)} chunk IDs and text hashes")
        output = run_cli(
            monkeypatch, "inspect-turn", "--slot", "4", "--session", sessions[1]
        )
        assert "active-extend-expiry" in output
        repair = result["manifests"][0]["validation"][0]
        assert repair == {
            "sha256": identity_hash(record.validation_notes[0]),
            "repair": "active-extend-expiry",
            "entity_kind": "character",
            "entity_id": 42,
        }
        # Cancel a session while its provider is between validation attempts.
        from nexus.api.narrative_lease import discard_generation

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            discard_generation(cur, sessions[2])
        record.attempt = 2
        with manifest_scope(lambda: connect(dbname)):
            start_attempt(
                record,
                blocks=[],
                system_prompt="private",
                prompt="private",
                settings={},
                wire_schema={},
            )
            finish_attempt(record, "accepted")
        with closing(connect(dbname)) as conn:
            late = inspect_turn(conn, session=sessions[2])["manifests"]
        assert [row["outcome"] for row in late] == ["discarded", "discarded"]
        assert late[1]["provider_outcome"] == "accepted"


def test_manifest_real_test_turn_and_child_job_correlation(
    monkeypatch, tmp_path, request
):
    """Both real TEST seats and an accepted compaction job share the session UUID."""
    # Configure before launching the HTTP TEST provider, so it loads TEST-only defaults.
    config = configure_test(tmp_path, "http://127.0.0.1:1", monkeypatch)
    provider = request.getfixturevalue("mock_openai_server")
    configure_test(tmp_path, provider, monkeypatch)
    doc = tomlkit.parse(config.read_text())
    doc["storyteller"]["correspondence"]["floor_turns"] = 1
    config.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "0")
    with disposable_slot_database("qa640_764_turn") as dbname:
        route_slot(monkeypatch, dbname)
        seed_played_story(
            dbname,
            turns=3,
            cast=FIXTURE_CAST,
            time_delta=FIXTURE_TURN_GAP,
            correspondence=True,
            slot=4,
        )
        _stage_pending_turn(dbname)
        import subprocess
        from nexus.database import database_url

        real_run = subprocess.run

        def run_in_clone(command, *args, **kwargs):
            if (
                isinstance(command, list)
                and "scripts/regenerate_embeddings.py" in command
            ):
                command = list(command)
                index = command.index("--database")
                assert command[index + 1] == dbname
                command[index : index + 2] = [
                    "--db-url",
                    database_url(dbname),
                ]
            return real_run(command, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", run_in_clone)
        with gateway_lane(monkeypatch):
            # Real public CLI, real HTTP providers, real accepting transaction.
            output = run_cli(
                monkeypatch, "continue", "--slot", "4", "--choice", "1", "--json"
            )
            payload = json.loads(output)
            assert payload["success"], payload
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute("SELECT session_id::text FROM incubator")
                session = cur.fetchone()[0]
            response = requests.post(
                f"{os.environ['NEXUS_API_URL']}/api/narrative/approve/{session}?slot=4&commit=true",
                timeout=120,
            )
            assert response.status_code == 200, response.text
            with closing(connect(dbname)) as conn:
                result = inspect_turn(conn, session=session)
            assert result["session"]["terminal_outcome"] == "accepted", result[
                "session"
            ]
            chunk = result["session"]["accepted_chunk_id"]
            manifests = result["manifests"]
            assert {row["seat"] for row in manifests} == {"skald_writer", "gaia"}
            assert all(
                row["model_id"] == "TEST"
                and row["outcome"] == "accepted"
                and row["response_sha256"]
                and row["provider_outcome"] == "accepted"
                for row in manifests
            )
            with closing(connect(dbname)) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM orrery_prompt_exposures WHERE tick_chunk_id=%s ORDER BY id",
                    (chunk,),
                )
                exposure_ids = [row[0] for row in cur.fetchall()]
            assert exposure_ids, "Acceptance must persist actual prompt exposures"
            assert all(row["exposure_ids"] == exposure_ids for row in manifests)
            assert {row["phase"] for row in result["phases"]} >= {
                "retrieval",
                "assembly",
                "writer",
                "gaia",
                "staging",
                "complete",
            }
            assert any(
                row["queue"] == "correspondence_compaction" for row in result["jobs"]
            ), result["jobs"]
            assert all(
                row["generation_session_id"] == session and isinstance(row["id"], int)
                for row in result["jobs"]
            )
            text = run_cli(
                monkeypatch, "inspect-turn", "--slot", "4", "--session", session
            )
            assert "[TEST MODE]" not in text
            # The joined observation reads this turn's real usage ledger (#802).
            observed = json.loads(
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
            assert observed["schema_version"] == 1
            assert observed["generation_session"] == session
            assert observed["ledger_days_read"]
            joined = {
                (row["seat"], row["attempt"]): row for row in observed["attempts"]
            }
            for seat in ("skald_writer", "gaia"):
                attempt = joined[(seat, 1)]
                window, usage = attempt["window"], attempt["usage"]
                assert attempt["model"] == "TEST"
                assert attempt["provider_outcome"] == "accepted"
                assert window["provenance"] == "attempt_manifest"
                assert window["block_tokens_total"] == window["input_tokens"]
                assert sum(window["influence_tokens"].values()) == (
                    window["input_tokens"]
                )
                # The TEST Responses mock reports exact counts and no cache details.
                assert usage["provenance"] == "provider_usage_ledger"
                assert (usage["input_tokens"], usage["output_tokens"]) == (1000, 800)
                assert usage["cached_input_tokens"] == "unknown"
            assert observed["phases"][-1]["phase"] == "complete"
            assert observed["wall_time"]["seconds"] > 0
            assert observed["jobs"]["total"] == len(result["jobs"])
            # Background spend follows each job's id; it never joins attempts.
            assert set(joined) >= {("skald_writer", 1), ("gaia", 1)}
            assert all(
                entry["usage"]["run_id"] == str(entry["id"])
                for entry in observed["jobs"]["entries"]
                if "usage" in entry
            )
            assert observed["usage_totals"]["critical_path"]["events"] >= 2
            summary = run_cli(
                monkeypatch,
                "inspect-turn",
                "--slot",
                "4",
                "--session",
                session,
                "--summary",
            )
            assert summary.startswith(f"Turn {session} (")
            assert "skald_writer #1 TEST" in summary
            assert "Session\tPhase" not in summary
            chunk_output = run_cli(
                monkeypatch,
                "inspect-turn",
                "--slot",
                "4",
                "--chunk",
                str(chunk),
                "--json",
            )
            assert (
                json.loads(chunk_output)["turn_inspection"]["session"]
                == result["session"]
            )
            run_cli(monkeypatch, "jobs", "--slot", "4")
            (tmp_path / "turn-inspection.json").write_text(json.dumps(result, indent=2))
            print(
                "Turn proof metadata: "
                + json.dumps(
                    {
                        "session": session,
                        "chunk": chunk,
                        "exposure_ids": exposure_ids,
                        "seats": [row["seat"] for row in manifests],
                        "jobs": result["jobs"],
                    }
                )
            )


def test_child_job_enqueue_correlation_and_transaction_reset(monkeypatch):
    """Real experience, maturation and trigger enqueue paths retain job identities."""
    from nexus.agents.orrery.experiences import enqueue_scene_experience_job_sync
    from nexus.agents.orrery.retrograde_maturation import (
        enqueue_declared_entity_maturations,
    )
    from nexus.agents.orrery.job_queues import load_job_queues_sync
    from nexus.config import load_settings_as_dict

    with disposable_slot_database("qa640_764_jobs") as dbname:
        route_slot(monkeypatch, dbname)
        parent = seed_played_story(
            dbname, turns=4, cast=FIXTURE_CAST, time_delta=FIXTURE_TURN_GAP, slot=4
        )[-1]
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM characters WHERE name = ANY(%s) ORDER BY name",
                (list(FIXTURE_CAST),),
            )
            subject, object_ = (row[0] for row in cur.fetchall())
        seed_relationship(
            dbname,
            subject_character_id=subject,
            object_character_id=object_,
            relationship_type="professional",
        )
        chunk = seed_accepted_turn(
            dbname,
            user_text=FIXTURE_TURN_CHOICES[0],
            storyteller_text="Manifest child-job boundary",
            slot=4,
        )
        session = str(uuid4())
        settings = load_settings_as_dict()
        with closing(connect(dbname)) as conn:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO narrative_generation_sessions (session_id, operation, status) VALUES (%s,'continue','initiated')",
                    (session,),
                )
                cur.execute(
                    "SELECT set_config('nexus.generation_session_id', %s, true)",
                    (session,),
                )
                cur.execute(
                    "UPDATE character_experience_jobs SET state='stale_rejected' WHERE state IN ('queued','leased','failed')"
                )
                count = enqueue_scene_experience_job_sync(
                    conn,
                    boundary_chunk_id=chunk,
                    scene_end_chunk_id=parent,
                    world_layer="primary",
                    slot=4,
                    settings=settings,
                )
                assert count > 0
                result = enqueue_declared_entity_maturations(
                    conn,
                    declarations=[
                        {
                            "kind": "character",
                            "name": "Manifest Courier",
                            "summary": "A courier bearing a manifest.",
                        }
                    ],
                    chunk_id=chunk,
                    raw_text="Manifest Courier arrives.",
                    slot=4,
                )
                assert result.jobs_enqueued == 1
                cur.execute("SELECT set_config('nexus.write_producer', 'manual', true)")
                cur.execute(
                    "SELECT set_config('nexus.source_chunk_id', %s, true)",
                    (str(chunk),),
                )
                cur.execute(
                    "SELECT character1_id, character2_id, valence_current FROM character_relationships LIMIT 1"
                )
                first, second, valence = cur.fetchone()
                cur.execute(
                    "UPDATE character_relationships SET emotional_valence=%s WHERE character1_id=%s AND character2_id=%s",
                    ("-5|hostile" if valence >= 0 else "+5|friendly", first, second),
                )
            status = load_job_queues_sync(conn)
            from scripts.qa_shift.qa_shift import _jobs_snapshot

            snapshot = _jobs_snapshot(
                json.loads(
                    json.dumps({"success": True, "slot": 4, **status}, default=str)
                ),
                slot=4,
            )
            assert snapshot["non_terminal_jobs"] == status["non_terminal_jobs"]
            correlated = [
                row
                for row in status["non_terminal_jobs"]
                if row.get("generation_session_id") == session
            ]
            assert {row["queue"] for row in correlated} >= {
                "experience_render",
                "retrograde_maturation",
                "relationship_milestone",
            }
            assert all(isinstance(row["id"], int) for row in correlated)
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT nullif(current_setting('nexus.generation_session_id', true), '')"
                )
                assert cur.fetchone()[0] is None
                enqueue_declared_entity_maturations(
                    conn,
                    declarations=[
                        {
                            "kind": "character",
                            "name": "Independent Courier",
                            "summary": "An independent courier.",
                        }
                    ],
                    chunk_id=chunk,
                    raw_text="Independent Courier arrives.",
                    slot=4,
                )
                cur.execute(
                    "SELECT generation_session_id FROM orrery_maturation_jobs WHERE entity_name='Independent Courier'"
                )
                assert cur.fetchone()[0] is None
            print("Correlated enqueue paths: " + json.dumps(correlated, default=str))


def test_inspect_turn_pre_session_chunk_and_duplicate_sessions(monkeypatch, capsys):
    """Legacy chunks get a concise CLI failure; ambiguous bindings stay loud."""
    import sys
    from nexus import cli

    with disposable_slot_database("qa640_800b_inspect") as dbname:
        route_slot(monkeypatch, dbname)
        chunk = seed_played_story(dbname, turns=2, slot=4)[0]
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM narrative_chunks WHERE id=%s", (chunk,))
            assert cur.fetchone() == (chunk,)
            # The factory binds every accepted turn; unbind one to stand for a
            # chunk accepted before session binding existed.
            cur.execute(
                "UPDATE narrative_generation_sessions SET chunk_id=NULL WHERE chunk_id=%s",
                (chunk,),
            )
            assert cur.rowcount == 1
        capsys.readouterr()
        monkeypatch.setattr(
            sys,
            "argv",
            ["nexus", "inspect-turn", "--slot", "4", "--chunk", str(chunk)],
        )
        assert cli.main() == 1
        captured = capsys.readouterr()
        assert captured.out == (
            f"chunk {chunk}: no generation session (accepted before session binding)\n"
        )
        assert captured.err == ""
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            for _ in range(2):
                cur.execute(
                    "INSERT INTO narrative_generation_sessions "
                    "(session_id, operation, status, chunk_id, terminal_outcome) "
                    "VALUES (%s, 'continue', 'complete', %s, 'accepted')",
                    (str(uuid4()), chunk),
                )
        with pytest.raises(
            ValueError, match="Expected one generation session; found 2"
        ):
            cli.main()
