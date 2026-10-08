"""PostgreSQL coverage for the public durable Orrery-jobs CLI readout."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
import uuid

from psycopg2 import sql
import pytest

from nexus import cli
from scripts.qa_shift import qa_shift
from tests.pg_fixtures import (
    DEFAULT_BASE_TIMESTAMP,
    connect,
    disposable_slot_database,
    route_slot_to_disposable,
    set_story_base,
)


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    """Open a direct PostgreSQL connection to a disposable database."""

    return connect(dbname)


def _disposable_jobs_db() -> Any:
    """Yield a migrated template clone, dropped afterward."""

    return disposable_slot_database("qa653")


def test_jobs_cli_reports_counts_and_non_terminal_rows(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The CLI combines every provider-capable queue in one public payload."""

    with _disposable_jobs_db() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                with conn.cursor() as cur:
                    set_story_base(cur, DEFAULT_BASE_TIMESTAMP)
                    cur.execute(
                        "INSERT INTO narrative_chunks (raw_text) VALUES (%s) "
                        "RETURNING id",
                        ("Issue 653 disposable chunk",),
                    )
                    scene_end_chunk_id = int(cur.fetchone()[0])
                    cur.execute(
                        "INSERT INTO narrative_chunks (raw_text) VALUES (%s) "
                        "RETURNING id",
                        ("Issue 653 disposable boundary",),
                    )
                    boundary_chunk_id = int(cur.fetchone()[0])
                    for chunk_id, scene in (
                        (scene_end_chunk_id, 1),
                        (boundary_chunk_id, 2),
                    ):
                        cur.execute(
                            """
                            INSERT INTO chunk_metadata (
                                chunk_id, season, episode, scene, world_layer
                            ) VALUES (%s, 1, 1, %s, 'primary')
                            """,
                            (chunk_id, scene),
                        )
                    cur.execute(
                        "INSERT INTO entities (kind) "
                        "SELECT 'character'::entity_kind "
                        "FROM generate_series(1, 4) RETURNING id"
                    )
                    entity_ids = [int(row[0]) for row in cur.fetchall()]
                    for index, (entity_id, state) in enumerate(
                        zip(
                            entity_ids,
                            ("queued", "leased", "succeeded", "failed"),
                            strict=True,
                        ),
                        start=1,
                    ):
                        cur.execute(
                            """
                            INSERT INTO orrery_maturation_jobs (
                                entity_id,
                                entity_kind,
                                entity_subtype_id,
                                entity_name,
                                slot,
                                requesting_chunk_id,
                                declaration,
                                state,
                                attempts,
                                available_at,
                                lease_until
                            ) VALUES (
                                %s, 'character', %s, %s, '4', %s,
                                '{}'::jsonb, %s::orrery_job_state, %s,
                                '2026-08-03T04:30:00+00:00'::timestamptz,
                                CASE WHEN %s = 'leased'
                                    THEN '2026-08-03T04:35:00+00:00'::timestamptz
                                    ELSE NULL
                                END
                            )
                            """,
                            (
                                entity_id,
                                index,
                                f"Entity {index}",
                                scene_end_chunk_id,
                                state,
                                index - 1,
                                state,
                            ),
                        )
                    experience_ids = []
                    for index in range(1, 6):
                        cur.execute(
                            """
                            INSERT INTO character_experiences (
                                character_entity_id, anchor_chunk_id,
                                world_event_ids, basis, seed_summary, salience,
                                source_digest, world_layer
                            ) VALUES (
                                %s, %s, ARRAY[%s]::bigint[], 'participant',
                                %s, 0.5, %s, 'primary'
                            ) RETURNING id
                            """,
                            (
                                entity_ids[0],
                                scene_end_chunk_id,
                                index,
                                f"Experience seed {index}",
                                f"qa653-experience-{index}",
                            ),
                        )
                        experience_ids.append(int(cur.fetchone()[0]))
                    for index, (experience_id, state) in enumerate(
                        zip(
                            experience_ids,
                            (
                                "queued",
                                "leased",
                                "succeeded",
                                "failed",
                                "stale_rejected",
                            ),
                            strict=True,
                        )
                    ):
                        cur.execute(
                            """
                            INSERT INTO character_experience_jobs (
                                boundary_chunk_id, scene_end_chunk_id,
                                world_layer, boundary_season, boundary_episode,
                                boundary_scene, scene_end_season,
                                scene_end_episode, scene_end_scene,
                                batch_ordinal, experience_ids, slot, state,
                                attempts, available_at, lease_until, last_error,
                                requested_model, source_digest
                            ) VALUES (
                                %s, %s, 'primary', 1, 1, 2, 1, 1, 1,
                                %s, ARRAY[%s]::bigint[], '4',
                                %s::orrery_job_state, %s,
                                '2026-08-03T04:30:00+00:00'::timestamptz,
                                CASE WHEN %s = 'leased'
                                    THEN '2026-08-03T04:35:00+00:00'::timestamptz
                                    ELSE NULL
                                END,
                                CASE WHEN %s = 'queued'
                                    THEN 'retryable validation failure'
                                    ELSE NULL
                                END,
                                'fixture-model', %s
                            )
                            """,
                            (
                                boundary_chunk_id,
                                scene_end_chunk_id,
                                index,
                                experience_id,
                                state,
                                1 if state in ("queued", "leased") else index,
                                state,
                                state,
                                f"qa653-job-{index}",
                            ),
                        )
        finally:
            conn.close()

        route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
        parsed = cli.build_parser().parse_args(["jobs", "--slot", "4", "--json"])
        payload = cli.run_jobs(argparse.Namespace(slot=parsed.slot))

        assert payload["success"] is True
        assert payload["slot"] == 4
        assert payload["counts"] == {
            "pending": 0,
            "stale_rejected": 1,
            "queued": 2,
            "leased": 2,
            "succeeded": 2,
            "failed": 2,
        }
        assert payload["queues"]["retrograde_maturation"]["counts"] == {
            "queued": 1,
            "leased": 1,
            "succeeded": 1,
            "failed": 1,
        }
        assert payload["queues"]["experience_render"]["counts"] == {
            "queued": 1,
            "leased": 1,
            "succeeded": 1,
            "failed": 1,
            "stale_rejected": 1,
        }
        assert payload["counts"] == {
            state: sum(
                queue["counts"].get(state, 0) for queue in payload["queues"].values()
            )
            for state in (
                "pending",
                "queued",
                "leased",
                "succeeded",
                "failed",
                "stale_rejected",
            )
        }
        assert [row["state"] for row in payload["non_terminal_jobs"]] == [
            "queued",
            "leased",
            "queued",
            "leased",
        ]
        assert [row["queue"] for row in payload["non_terminal_jobs"]] == [
            "experience_render",
            "experience_render",
            "retrograde_maturation",
            "retrograde_maturation",
        ]
        maturation_rows = payload["queues"]["retrograde_maturation"][
            "non_terminal_jobs"
        ]
        assert [row["entity_name"] for row in maturation_rows] == [
            "Entity 1",
            "Entity 2",
        ]
        assert set(maturation_rows[0]) == {
            "generation_session_id",
            "id",
            "queue",
            "state",
            "entity_kind",
            "entity_name",
            "requesting_chunk_id",
            "attempts",
            "available_at",
            "lease_until",
            "last_error",
        }
        experience_rows = payload["queues"]["experience_render"]["non_terminal_jobs"]
        assert set(experience_rows[0]) == {
            "generation_session_id",
            "id",
            "queue",
            "state",
            "attempts",
            "available_at",
            "lease_until",
            "last_error",
            "boundary_chunk_id",
            "scene_end_chunk_id",
            "batch_ordinal",
            "experience_ids",
        }
        assert experience_rows[0]["experience_ids"] == [experience_ids[0]]
        assert experience_rows[0]["last_error"] == "retryable validation failure"
        assert maturation_rows[0]["lease_until"] is None
        assert maturation_rows[1]["lease_until"] is not None
        assert all("queue" in row for row in payload["non_terminal_jobs"])

        cli.emit_output(payload, as_json=False)
        human_output = capsys.readouterr().out
        assert "retrograde_maturation" in human_output
        assert "experience_render" in human_output

        # Sol review (PR #738): push the REAL payload through the CLI's JSON
        # encoder and the guard's public entry points, so a serialization or
        # ordering mismatch cannot hide behind the fixture-based suites.
        cli.emit_output(payload, as_json=True)
        rendered = json.loads(capsys.readouterr().out)
        snapshot = qa_shift._jobs_snapshot(rendered, slot=4)
        assert [row["queue"] for row in snapshot["non_terminal_jobs"]] == [
            "experience_render",
            "experience_render",
            "retrograde_maturation",
            "retrograde_maturation",
        ]
        assert snapshot["counts"] == rendered["counts"]

        settled = json.loads(json.dumps(rendered))
        for queue in settled["queues"].values():
            queue["counts"] = {state: 0 for state in queue["counts"]}
            queue["non_terminal_jobs"] = []
        settled["counts"] = {state: 0 for state in settled["counts"]}
        settled["non_terminal_jobs"] = []

        now = datetime(2026, 7, 30, 4, 30, tzinfo=timezone.utc)

        def _usage_payload(_root: Path, _day: str | None) -> dict[str, Any]:
            return {
                "success": True,
                "usage": {
                    "day": "2026-07-30",
                    "events": [],
                    "providers": {},
                    "seats": {},
                    "openai_day_total": {
                        "total_tokens": 100,
                        "unknown_usage_events": 0,
                    },
                    "allowance": {},
                },
            }

        config = replace(qa_shift.load_shift_config(), archive_root=tmp_path, slot=4)
        begun = qa_shift.begin_shift(
            config=config,
            usage_reader=_usage_payload,
            jobs_reader=lambda _root, _slot: settled,
            bleed_uptake_reader=lambda _root, _slot: {
                "offered_count": 0,
                "used_count": 0,
            },
            now=now,
        )
        check = qa_shift.check_shift(
            archive=Path(begun["archive"]),
            mode=qa_shift.CheckMode.PRE_CALL,
            usage_reader=_usage_payload,
            jobs_reader=lambda _root, _slot: rendered,
            now=now + timedelta(seconds=1),
        )
        assert check["status"] == "pending"
        assert len(check["non_terminal_jobs"]) == 4
        assert {row["queue"] for row in check["non_terminal_jobs"]} == {
            "experience_render",
            "retrograde_maturation",
        }


def test_jobs_cli_reports_experiences_stamped_without_vectors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A stamp with no active-model vector surfaces in `nexus jobs` (#848)."""

    from nexus.agents.memnon.utils.source_embeddings import (
        CHARACTER_EXPERIENCE_SOURCE,
        active_memnon_embedding_model_dimensions,
    )

    with _disposable_jobs_db() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO narrative_chunks (raw_text) VALUES (%s) "
                        "RETURNING id",
                        ("Issue 848 disposable anchor",),
                    )
                    chunk_id = int(cur.fetchone()[0])
                    cur.execute(
                        "INSERT INTO entities (kind) "
                        "VALUES ('character'::entity_kind) RETURNING id"
                    )
                    entity_id = int(cur.fetchone()[0])
                    experience_ids = []
                    for index, stamped in enumerate((True, False), start=1):
                        cur.execute(
                            """
                            INSERT INTO character_experiences (
                                character_entity_id, anchor_chunk_id,
                                world_event_ids, basis, seed_summary, salience,
                                source_digest, world_layer, experience_text,
                                render_model, renderer_version,
                                render_generation_id, embedding_generated_at
                            ) VALUES (
                                %s, %s, ARRAY[%s]::bigint[], 'participant',
                                %s, 0.5, %s, 'primary', %s,
                                'fixture-model', 'fixture-v1', %s::uuid,
                                CASE WHEN %s THEN now() END
                            ) RETURNING id
                            """,
                            (
                                entity_id,
                                chunk_id,
                                index,
                                f"Seed {index}",
                                f"qa848-experience-{index}",
                                f"I remembered stamp case {index}.",
                                str(uuid.uuid4()),
                                stamped,
                            ),
                        )
                        experience_ids.append(int(cur.fetchone()[0]))
                    # Only a stamped row missing its vector is damage.
                    for (
                        model,
                        dimensions,
                    ) in active_memnon_embedding_model_dimensions().items():
                        table_name = (
                            CHARACTER_EXPERIENCE_SOURCE.table_name_for_dimensions(
                                dimensions
                            )
                        )
                        cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
                        if cur.fetchone()[0] is not None:
                            cur.execute(
                                sql.SQL(
                                    "DELETE FROM {} WHERE experience_id = ANY(%s)"
                                ).format(sql.Identifier(table_name)),
                                (experience_ids,),
                            )
        finally:
            conn.close()

        route_slot_to_disposable(monkeypatch.setattr, slot=4, dbname=dbname)
        payload = cli.run_jobs(argparse.Namespace(slot=4))

        assert payload["stamped_without_vectors"] == {
            "retrograde_summaries": 0,
            "character_experiences": 1,
        }
        # The unstamped rendered row is owed vectors, not damage (#754).
        assert payload["unembedded_rendered_experiences"] == 1
        cli.emit_output(payload, as_json=False)
        output = capsys.readouterr().out
        assert (
            "stamped_without_vectors: retrograde_summaries=0, "
            "character_experiences=1"
        ) in output
        assert "unembedded_rendered_experiences: 1" in output
