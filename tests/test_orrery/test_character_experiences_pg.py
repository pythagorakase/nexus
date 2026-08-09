"""Real accepted-commit and queue proofs for character experiences."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from nexus.agents.orrery.experiences import (
    ExperienceRecollection,
    ExperienceRenderBatch,
    drain_experience_render_jobs_sync,
    enqueue_scene_experience_job_sync,
    seed_character_experiences_sync,
)
from nexus.agents.orrery.resolver import resolve_dry_run
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.config import load_settings_as_dict


pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).parents[2]
MIGRATION_SQL = (ROOT / "migrations" / "104_character_experiences.sql").read_text()


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


@contextmanager
def _disposable_database() -> Iterator[str]:
    """Yield one migrated template clone and drop it even after failure."""
    dbname = f"qa677_{uuid4().hex[:12]}"
    source = os.environ.get("NEXUS_TEST_TEMPLATE_DB", "NEXUS_template")
    assert source == "NEXUS_template" or source.startswith("qa677_")
    admin: Any = None
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname), sql.Identifier(source)
                )
            )
        conn = _connect(dbname)
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(MIGRATION_SQL)
        finally:
            conn.close()
        yield dbname
    finally:
        if admin is not None:
            with admin.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (dbname,),
                )
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
            admin.close()


def _insert_chunk(cur: Any, label: str) -> int:
    cur.execute(
        "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
        "VALUES (%s, %s) RETURNING id",
        (label, label),
    )
    chunk_id = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO chunk_metadata "
        "(chunk_id, season, episode, scene, world_layer, slug) "
        "VALUES (%s, 1, 1, %s, 'primary', %s)",
        (chunk_id, chunk_id, f"qa677_{chunk_id}"),
    )
    cur.execute(
        "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
        (datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc), chunk_id),
    )
    return chunk_id


def _insert_character(
    cur: Any,
    name: str,
    *,
    summary: str | None,
    background: str | None,
) -> tuple[int, int]:
    cur.execute("INSERT INTO entities (kind) VALUES ('character') RETURNING id")
    entity_id = int(cur.fetchone()[0])
    cur.execute(
        """
        INSERT INTO characters (name, entity_id, summary, background)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (name, entity_id, summary, background),
    )
    return int(cur.fetchone()[0]), entity_id


def _resolve_sleep(dbname: str, parent_chunk_id: int) -> Any:
    engine = create_engine(
        URL.create(
            "postgresql+psycopg2",
            username=os.environ.get("PGUSER", "pythagor"),
            host=os.environ.get("PGHOST", "localhost"),
            port=int(os.environ.get("PGPORT", "5432")),
            database=dbname,
        ),
        future=True,
    )
    try:
        with Session(engine) as session:
            return resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=parent_chunk_id,
                window_chunks=30,
                epistemics_settings={"enabled": False},
            )
    finally:
        engine.dispose()


def _stage_incubator(
    cur: Any,
    *,
    session_id: str,
    parent_chunk_id: int,
    proposal: Any,
    character_ids: list[int],
    scene_boundary: bool,
) -> None:
    metadata = {
        "chronology": {"episode_transition": "continue"},
        "world_layer": "primary",
    }
    if scene_boundary:
        metadata["scene_boundary"] = True
    references = {
        "characters": [
            {"character_id": character_id, "reference_type": "present"}
            for character_id in character_ids
        ],
        "places": [],
        "factions": [],
    }
    cur.execute(
        """
        INSERT INTO incubator (
            id, chunk_id, parent_chunk_id, user_text, storyteller_text,
            generation_model, choice_object, choice_text,
            metadata_updates, entity_updates, reference_updates,
            orrery_proposal, orrery_adjudications, new_entities,
            correspondence_writer_letter, correspondence_gaia_letter,
            session_id, llm_response_id, status
        ) VALUES (
            TRUE, %s, %s, 'Continue.', 'The accepted scene advances.',
            'TEST', NULL, NULL, %s, %s, %s, %s, %s, %s,
            NULL, NULL, %s, %s, 'provisional'
        )
        """,
        (
            parent_chunk_id + 1,
            parent_chunk_id,
            Json(metadata),
            Json({}),
            Json(references),
            Json(proposal.to_dict()) if proposal is not None else None,
            Json([]),
            Json([]),
            session_id,
            f"response-{session_id}",
        ),
    )


class _SceneProvider:
    """Structured provider double invoked only after a genuine durable lease."""

    def get_structured_completion(
        self, prompt: str, _schema: type[ExperienceRenderBatch]
    ) -> tuple[ExperienceRenderBatch, None]:
        ids = [int(value) for value in re.findall(r'"experience_id": (\d+)', prompt)]
        return (
            ExperienceRenderBatch(
                recollections=[
                    ExperienceRecollection(
                        experience_id=experience_id,
                        experience_text=(
                            "I remembered the accepted event clearly. "
                            "I felt watchful after it ended."
                        ),
                    )
                    for experience_id in ids
                ]
            ),
            None,
        )


class _FailingSceneProvider:
    """Provider double proving failures leave deterministic seeds untouched."""

    def get_structured_completion(self, *_args: Any) -> Any:
        raise RuntimeError("synthetic experience render failure")


class _LeaseStealingProvider(_SceneProvider):
    """Replace the durable owner/nonce before returning a late valid batch."""

    def __init__(self, dbname: str) -> None:
        self.dbname = dbname

    def get_structured_completion(
        self, prompt: str, schema: type[ExperienceRenderBatch]
    ) -> tuple[ExperienceRenderBatch, None]:
        conn = _connect(self.dbname)
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE character_experience_jobs
                        SET locked_by = 'replacement-worker',
                            lease_nonce = %s,
                            lease_until = clock_timestamp() + interval '5 minutes'
                        WHERE state = 'leased'
                        """,
                        (str(uuid4()),),
                    )
                    assert cur.rowcount == 1
        finally:
            conn.close()
        return super().get_structured_completion(prompt, schema)


def test_real_commit_forms_verified_seeds_and_boundary_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve, accept, seed, boundary-enqueue, lease, and render end to end."""
    monkeypatch.setattr(
        "nexus.api.presence_audit.presence_audit_enabled", lambda: False
    )
    settings = load_settings_as_dict()
    with _disposable_database() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                with conn.cursor() as cur:
                    parent_chunk_id = _insert_chunk(cur, "Issue 677 parent")
                    actor_character_id, actor_entity_id = _insert_character(
                        cur,
                        "Aster Vale",
                        summary="A courier who keeps moving.",
                        background="Raised among the night trains.",
                    )
                    witness_character_id, witness_entity_id = _insert_character(
                        cur,
                        "Beren Quill",
                        summary="A station observer.",
                        background="Records arrivals for the archive.",
                    )
                    extra_character_id, extra_entity_id = _insert_character(
                        cur,
                        "Passing Extra",
                        summary="A one-scene passerby.",
                        background=None,
                    )
                    _absent_character_id, absent_entity_id = _insert_character(
                        cur,
                        "Absent Dossier",
                        summary="A known investigator.",
                        background="Working elsewhere tonight.",
                    )
                    _proximity_character_id, proximity_entity_id = _insert_character(
                        cur,
                        "Nearby Dossier",
                        summary="A nearby resident.",
                        background="Lives beside the station.",
                    )
                    cur.execute(
                        """
                        UPDATE character_need_states
                        SET debt_score = 60, last_evaluated_at = %s
                        WHERE character_entity_id = %s AND need_type = 'sleep'
                        """,
                        (
                            datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc),
                            actor_entity_id,
                        ),
                    )
                    assert cur.rowcount == 1
                    cur.execute(
                        """
                        INSERT INTO world_events (
                            event_type, tick_chunk_id, actor_entity_id,
                            world_layer, source, changed_fields, payload
                        ) VALUES (
                            'slept', %s, %s, 'primary', 'resolver', '{}', '{}'::jsonb
                        )
                        """,
                        (parent_chunk_id, actor_entity_id),
                    )
            proposal = _resolve_sleep(dbname, parent_chunk_id)
            assert proposal.resolutions
            assert any(draft.template_id == "sleep" for draft in proposal.resolutions)
            formation_session = str(uuid4())
            with conn:
                with conn.cursor() as cur:
                    _stage_incubator(
                        cur,
                        session_id=formation_session,
                        parent_chunk_id=parent_chunk_id,
                        proposal=proposal,
                        character_ids=[
                            actor_character_id,
                            witness_character_id,
                            extra_character_id,
                        ],
                        scene_boundary=False,
                    )
            accepted_chunk_id = commit_incubator_to_database_sync(
                conn, formation_session, slot=677
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT character_entity_id, basis::text AS basis,
                           experience_text
                    FROM character_experiences
                    WHERE anchor_chunk_id = %s
                    ORDER BY character_entity_id
                    """,
                    (accepted_chunk_id,),
                )
                formation = [dict(row) for row in cur.fetchall()]
            assert [
                (row["character_entity_id"], row["basis"]) for row in formation
            ] == [
                (actor_entity_id, "participant"),
                (witness_entity_id, "witness"),
            ]
            assert all(row["experience_text"] is None for row in formation)
            assert absent_entity_id not in {
                row["character_entity_id"] for row in formation
            }
            assert proximity_entity_id not in {
                row["character_entity_id"] for row in formation
            }
            assert extra_entity_id not in {
                row["character_entity_id"] for row in formation
            }

            boundary_session = str(uuid4())
            with conn:
                with conn.cursor() as cur:
                    _stage_incubator(
                        cur,
                        session_id=boundary_session,
                        parent_chunk_id=accepted_chunk_id,
                        proposal=None,
                        character_ids=[actor_character_id],
                        scene_boundary=True,
                    )
            boundary_chunk_id = commit_incubator_to_database_sync(
                conn, boundary_session, slot=677
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT state::text AS state, experience_ids,
                           boundary_chunk_id, lease_nonce
                    FROM character_experience_jobs
                    """
                )
                job = dict(cur.fetchone())
            assert job["state"] == "queued"
            assert job["boundary_chunk_id"] == boundary_chunk_id
            assert len(job["experience_ids"]) == 2
            assert job["lease_nonce"] is None

            rendered, failed = drain_experience_render_jobs_sync(
                slot=677,
                settings=settings,
                conn=conn,
                provider=_SceneProvider(),
            )
            assert (rendered, failed) == (2, 0)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT experience_text, render_model, renderer_version,
                           render_generation_id
                    FROM character_experiences
                    WHERE id = ANY(%s)
                    ORDER BY id
                    """,
                    (job["experience_ids"],),
                )
                rendered_rows = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    "SELECT state::text AS state, locked_by, lease_nonce "
                    "FROM character_experience_jobs"
                )
                completed_job = dict(cur.fetchone())
            assert all(row["experience_text"] for row in rendered_rows)
            assert all(
                row["render_model"] == settings["orrery"]["experiences"]["model"]
                for row in rendered_rows
            )
            assert all(
                row["renderer_version"] == "experience-renderer-v1"
                for row in rendered_rows
            )
            assert len({row["render_generation_id"] for row in rendered_rows}) == 1
            assert completed_job == {
                "state": "succeeded",
                "locked_by": None,
                "lease_nonce": None,
            }
        finally:
            conn.close()


def test_acquisition_requires_told_or_granted_delivered_account() -> None:
    """Only durable delivered-account awareness mints acquisition experiences."""
    settings = load_settings_as_dict()
    with _disposable_database() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                with conn.cursor() as cur:
                    chunk_id = _insert_chunk(cur, "Issue 677 acquisition")
                    _character_id, entity_id = _insert_character(
                        cur,
                        "Cora Flint",
                        summary="A careful listener.",
                        background="Keeps an indexed private journal.",
                    )
                    cur.execute(
                        """
                        INSERT INTO world_events (
                            event_type, tick_chunk_id, actor_entity_id,
                            world_layer, source, changed_fields, payload
                        ) VALUES (
                            'slept', %s, %s, 'primary', 'resolver', '{}', '{}'::jsonb
                        ) RETURNING id
                        """,
                        (chunk_id, entity_id),
                    )
                    incident_id = int(cur.fetchone()[0])
                    cur.execute(
                        """
                        INSERT INTO claims (
                            world_event_id, summary, scope, source_chunk_id,
                            account_label
                        ) VALUES (%s, %s, 'bounded', %s, 'reported')
                        RETURNING id
                        """,
                        (incident_id, "The north gate was opened.", chunk_id),
                    )
                    claim_id = int(cur.fetchone()[0])
                    cur.execute(
                        """
                        INSERT INTO claim_awareness (
                            claim_id, knower_entity_id, source_tier,
                            immediate_source_entity_id, source_chunk_id
                        ) VALUES (%s, %s, 'told', %s, %s)
                        RETURNING id
                        """,
                        (claim_id, entity_id, entity_id, chunk_id),
                    )
                    awareness_id = int(cur.fetchone()[0])
                assert (
                    seed_character_experiences_sync(
                        conn,
                        anchor_chunk_id=chunk_id,
                        settings=settings,
                    )
                    == 1
                )
                with conn.cursor() as cur:
                    boundary_chunk_id = _insert_chunk(cur, "Acquisition boundary")
                assert enqueue_scene_experience_job_sync(
                    conn,
                    boundary_chunk_id=boundary_chunk_id,
                    scene_end_chunk_id=chunk_id,
                    world_layer="primary",
                    slot=677,
                    settings=settings,
                )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT basis::text AS basis, claim_id, claim_awareness_id,
                           world_event_ids, seed_summary
                    FROM character_experiences
                    """
                )
                row = dict(cur.fetchone())
            assert row["basis"] == "acquisition"
            assert row["claim_id"] == claim_id
            assert row["claim_awareness_id"] == awareness_id
            assert row["world_event_ids"] == [incident_id]
            assert "by being told" in row["seed_summary"]
            rendered, failed = drain_experience_render_jobs_sync(
                slot=677,
                settings=settings,
                conn=conn,
                provider=_FailingSceneProvider(),
            )
            assert (rendered, failed) == (0, 1)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT experience_text FROM character_experiences "
                    "WHERE claim_awareness_id = %s",
                    (awareness_id,),
                )
                assert cur.fetchone()["experience_text"] is None
                cur.execute(
                    "SELECT state::text AS state, attempts, last_error "
                    "FROM character_experience_jobs"
                )
                failed_job = dict(cur.fetchone())
            assert failed_job["state"] == "queued"
            assert failed_job["attempts"] == 1
            assert failed_job["last_error"] == "synthetic experience render failure"
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE character_experience_jobs "
                        "SET available_at = clock_timestamp()"
                    )
            rendered, failed = drain_experience_render_jobs_sync(
                slot=677,
                settings=settings,
                conn=conn,
                provider=_LeaseStealingProvider(dbname),
            )
            assert (rendered, failed) == (0, 1)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT experience_text FROM character_experiences "
                    "WHERE claim_awareness_id = %s",
                    (awareness_id,),
                )
                assert cur.fetchone()["experience_text"] is None
                cur.execute(
                    "SELECT state::text AS state, locked_by "
                    "FROM character_experience_jobs"
                )
                stolen_job = dict(cur.fetchone())
            assert stolen_job == {
                "state": "leased",
                "locked_by": "replacement-worker",
            }
        finally:
            conn.close()
