"""Real accepted-commit and queue proofs for character experiences."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import TRANSACTION_STATUS_IDLE
from psycopg2.extras import Json, RealDictCursor
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from nexus.agents.logon.skald_wire import (
    CharacterRef,
    PlaceRef,
    PresenceBaseline,
    PresenceDelta,
    SceneReset,
    SkaldTurnWire,
    hydrate_skald_turn,
)
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.experiences import (
    ExperienceRecollection,
    ExperienceRenderBatch,
    _known_and_allowed_names,
    drain_experience_render_jobs_sync,
    enqueue_scene_experience_job_sync,
    seed_character_experiences_sync,
    validate_render_batch,
)
from nexus.agents.orrery.resolver import resolve_dry_run
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.api.lore_adapter import response_to_incubator
from nexus.config import load_settings_as_dict
from nexus.memory.manager import empty_pass2_baseline


pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).parents[2]
MIGRATION_SQL = "\n".join(
    (ROOT / "migrations" / name).read_text()
    for name in (
        "104_character_experiences.sql",
        "110_experience_formation_sweep.sql",
    )
)


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
                    cur.execute(
                        """
                        INSERT INTO global_variables (id, base_timestamp)
                        VALUES (true, %s)
                        ON CONFLICT (id) DO UPDATE
                        SET base_timestamp = EXCLUDED.base_timestamp
                        """,
                        (datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc),),
                    )
                    fixture_character_id, _fixture_entity_id = _insert_character(
                        cur,
                        "Fixture Player",
                        summary="The canonical test-only player identity.",
                        background="Exists so default exclusion never guesses.",
                    )
                    _set_player_character(cur, fixture_character_id)
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


def _set_player_character(cur: Any, character_id: int) -> None:
    base_timestamp = datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc)
    cur.execute(
        """
        INSERT INTO global_variables (id, user_character, base_timestamp)
        VALUES (true, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET user_character = EXCLUDED.user_character,
            base_timestamp = EXCLUDED.base_timestamp
        """,
        (character_id, base_timestamp),
    )
    assert cur.rowcount == 1


def _set_only_need_due(
    cur: Any,
    *,
    character_entity_id: int,
    need_type: str,
) -> None:
    evaluated_at = datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc)
    cur.execute(
        """
        UPDATE character_need_states
        SET debt_score = CASE WHEN need_type = %s THEN 60 ELSE 0 END,
            last_evaluated_at = %s
        WHERE character_entity_id = %s
        """,
        (need_type, evaluated_at, character_entity_id),
    )
    assert cur.rowcount > 0


def _insert_place(cur: Any, name: str) -> int:
    cur.execute("INSERT INTO entities (kind) VALUES ('place') RETURNING id")
    entity_id = int(cur.fetchone()[0])
    cur.execute(
        """
        INSERT INTO places (name, type, entity_id)
        VALUES (%s, 'fixed_location', %s)
        RETURNING id
        """,
        (name, entity_id),
    )
    return int(cur.fetchone()[0])


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
    characters: list[tuple[int, str]],
    scene_boundary: bool,
    place: tuple[int, str] | None = None,
) -> None:
    refs = [
        CharacterRef(kind="character", id=character_id, name=name)
        for character_id, name in characters
    ]
    if scene_boundary:
        assert place is not None
        presence = PresenceDelta(
            scene_reset=SceneReset(
                place=PlaceRef(kind="place", id=place[0], name=place[1]),
                present=refs,
            )
        )
    else:
        presence = PresenceDelta(enter=refs)
    wire = SkaldTurnWire(
        narrative="The accepted scene advances.",
        choices=["Continue.", "Wait."],
        presence=presence,
        letter="Record the accepted scene.",
    )
    hydrated = hydrate_skald_turn(wire, presence_baseline=PresenceBaseline())
    staged = response_to_incubator(
        hydrated,
        parent_chunk_id=parent_chunk_id,
        user_text="Continue.",
        session_id=session_id,
        orrery_proposal=proposal,
        lore_pass_baseline=empty_pass2_baseline({}),
    )
    staged["generation_model"] = "TEST"
    staged["llm_response_id"] = f"response-{session_id}"
    cur.execute(
        """
        INSERT INTO incubator (
            id, chunk_id, parent_chunk_id, user_text, storyteller_text,
            generation_model, choice_object, choice_text,
            metadata_updates, entity_updates, reference_updates,
            orrery_proposal, orrery_adjudications, new_entities,
            correspondence_writer_letter, correspondence_gaia_letter,
            session_id, llm_response_id, status, lore_pass_baseline
        ) VALUES (
            TRUE, %s, %s, 'Continue.', 'The accepted scene advances.',
            'TEST', NULL, NULL, %s, %s, %s, %s, %s, %s,
            NULL, NULL, %s, %s, 'provisional', %s
        )
        """,
        (
            staged["chunk_id"],
            staged["parent_chunk_id"],
            Json(staged["metadata_updates"]),
            Json(staged["entity_updates"]),
            Json(staged["reference_updates"]),
            Json(staged["orrery_proposal"]),
            Json(staged["orrery_adjudications"]),
            Json(staged["new_entities"]),
            staged["session_id"],
            staged["llm_response_id"],
            Json(staged["lore_pass_baseline"]),
        ),
    )


def _accept_turn(
    conn: Any,
    *,
    parent_chunk_id: int,
    proposal: Any,
    characters: list[tuple[int, str]],
) -> int:
    session_id = str(uuid4())
    with conn:
        with conn.cursor() as cur:
            _stage_incubator(
                cur,
                session_id=session_id,
                parent_chunk_id=parent_chunk_id,
                proposal=proposal,
                characters=characters,
                scene_boundary=False,
            )
    return commit_incubator_to_database_sync(conn, session_id, slot=708)


def _setup_due_actor(conn: Any) -> tuple[int, int, int]:
    with conn:
        with conn.cursor() as cur:
            parent_chunk_id = _insert_chunk(cur, "Issue 708 historical anchor")
            player_character_id, _player_entity_id = _insert_character(
                cur,
                "Player Observer",
                summary="The player character remains outside this receipt.",
                background="A complete but uninvolved player dossier.",
            )
            actor_character_id, actor_entity_id = _insert_character(
                cur,
                "Aster Vale",
                summary="A courier who keeps moving.",
                background="Raised among the night trains.",
            )
            _set_player_character(cur, player_character_id)
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
            _set_only_need_due(
                cur,
                character_entity_id=actor_entity_id,
                need_type="sleep",
            )
    return parent_chunk_id, actor_character_id, actor_entity_id


def _seed_bytes_for_event(conn: Any, event_id: int) -> bytes:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT character_entity_id, anchor_chunk_id, world_event_ids,
                   claim_id, claim_awareness_id, basis::text AS basis,
                   location_id, world_time, seed_summary, emotion, salience,
                   source_digest, world_layer::text AS world_layer
            FROM character_experiences
            WHERE %s = ANY(world_event_ids)
              AND claim_awareness_id IS NULL
            """,
            (event_id,),
        )
        rows = [dict(row) for row in cur.fetchall()]
    assert len(rows) == 1
    return json.dumps(
        rows[0],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _pin_next_world_event_id(conn: Any, event_id: int) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT setval(
                    pg_get_serial_sequence('world_events', 'id'),
                    %s,
                    false
                )
                """,
                (event_id,),
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


class _ForbiddenSceneProvider:
    """Record an invariant violation if an excluded job reaches the provider."""

    def __init__(self) -> None:
        self.calls = 0

    def get_structured_completion(self, *_args: Any) -> Any:
        self.calls += 1
        raise AssertionError("excluded player experience reached the provider")


class _IdleTransactionProvider(_SceneProvider):
    """Assert that the queue connection is idle during the provider call."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def get_structured_completion(
        self, prompt: str, schema: type[ExperienceRenderBatch]
    ) -> tuple[ExperienceRenderBatch, None]:
        assert self.conn.get_transaction_status() == TRANSACTION_STATUS_IDLE
        return super().get_structured_completion(prompt, schema)


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


class _TimelineDriftingProvider(_SceneProvider):
    """Mutate the frozen boundary timeline while the provider call is active."""

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
                        UPDATE chunk_metadata
                        SET scene = scene + 1
                        WHERE chunk_id = (
                            SELECT boundary_chunk_id
                            FROM character_experience_jobs
                            WHERE state = 'leased'
                            ORDER BY id
                            LIMIT 1
                        )
                        """
                    )
                    assert cur.rowcount == 1
        finally:
            conn.close()
        return super().get_structured_completion(prompt, schema)


def test_genesis_events_form_on_the_next_genuine_accept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A chunk-1 event survives the wizard-shaped gap and forms at chunk 2."""

    monkeypatch.setattr(
        "nexus.api.presence_audit.presence_audit_enabled", lambda: False
    )
    with _disposable_database() as dbname:
        conn = _connect(dbname)
        try:
            parent_chunk_id, actor_character_id, actor_entity_id = _setup_due_actor(
                conn
            )
            proposal = _resolve_sleep(dbname, parent_chunk_id)
            assert any(draft.template_id == "sleep" for draft in proposal.resolutions)
            with conn:
                result = commit_orrery_tick_sync(
                    conn,
                    proposal,
                    tick_chunk_id=parent_chunk_id,
                )
            assert result.event_count == 1
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, experiences_formed_at
                    FROM world_events
                    WHERE tick_chunk_id = %s AND resolution_id IS NOT NULL
                    """,
                    (parent_chunk_id,),
                )
                genesis_event = dict(cur.fetchone())
            assert genesis_event["experiences_formed_at"] is None

            accepted_chunk_id = _accept_turn(
                conn,
                parent_chunk_id=parent_chunk_id,
                proposal=None,
                characters=[],
            )
            assert accepted_chunk_id > parent_chunk_id
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT character_entity_id, anchor_chunk_id, world_event_ids
                    FROM character_experiences
                    WHERE %s = ANY(world_event_ids)
                    """,
                    (genesis_event["id"],),
                )
                seed = dict(cur.fetchone())
                cur.execute(
                    "SELECT experiences_formed_at FROM world_events WHERE id = %s",
                    (genesis_event["id"],),
                )
                formed_at = cur.fetchone()["experiences_formed_at"]
            assert seed == {
                "character_entity_id": actor_entity_id,
                "anchor_chunk_id": parent_chunk_id,
                "world_event_ids": [genesis_event["id"]],
            }
            assert formed_at is not None
        finally:
            conn.close()


def test_late_same_owner_event_forms_once_at_its_past_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A late event forms once and remains renderable after an old boundary."""

    monkeypatch.setattr(
        "nexus.api.presence_audit.presence_audit_enabled", lambda: False
    )
    settings = load_settings_as_dict()
    with _disposable_database() as dbname:
        conn = _connect(dbname)
        try:
            parent_chunk_id, actor_character_id, actor_entity_id = _setup_due_actor(
                conn
            )
            sleep_proposal = _resolve_sleep(dbname, parent_chunk_id)
            accepted_chunk_id = _accept_turn(
                conn,
                parent_chunk_id=parent_chunk_id,
                proposal=sleep_proposal,
                characters=[],
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, world_event_ids
                    FROM character_experiences
                    WHERE character_entity_id = %s
                      AND anchor_chunk_id = %s
                      AND claim_awareness_id IS NULL
                    """,
                    (actor_entity_id, accepted_chunk_id),
                )
                first_seed = dict(cur.fetchone())

            with conn:
                with conn.cursor() as cur:
                    _set_only_need_due(
                        cur,
                        character_entity_id=actor_entity_id,
                        need_type="thirst",
                    )
            drink_proposal = _resolve_sleep(dbname, accepted_chunk_id)
            assert any(
                draft.template_id == "drink" for draft in drink_proposal.resolutions
            )
            with conn:
                late_result = commit_orrery_tick_sync(
                    conn,
                    drink_proposal,
                    tick_chunk_id=accepted_chunk_id,
                )
            assert late_result.event_count == 1
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id
                    FROM world_events
                    WHERE tick_chunk_id = %s
                      AND experiences_formed_at IS NULL
                    ORDER BY id
                    """,
                    (accepted_chunk_id,),
                )
                late_event_ids = [int(row["id"]) for row in cur.fetchall()]
            assert len(late_event_ids) == 1

            with conn:
                with conn.cursor() as cur:
                    first_boundary_id = _insert_chunk(
                        cur, "Boundary before late formation"
                    )
                assert (
                    enqueue_scene_experience_job_sync(
                        conn,
                        boundary_chunk_id=first_boundary_id,
                        scene_end_chunk_id=accepted_chunk_id,
                        world_layer="primary",
                        slot=708,
                        settings=settings,
                    )
                    == 1
                )

            next_chunk_id = _accept_turn(
                conn,
                parent_chunk_id=first_boundary_id,
                proposal=None,
                characters=[],
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, anchor_chunk_id, world_event_ids
                    FROM character_experiences
                    WHERE character_entity_id = %s
                      AND anchor_chunk_id = %s
                      AND claim_awareness_id IS NULL
                    ORDER BY id
                    """,
                    (actor_entity_id, accepted_chunk_id),
                )
                seeds_after_sweep = [dict(row) for row in cur.fetchall()]
            assert [
                (seed["anchor_chunk_id"], seed["world_event_ids"])
                for seed in seeds_after_sweep
            ] == [
                (accepted_chunk_id, first_seed["world_event_ids"]),
                (accepted_chunk_id, late_event_ids),
            ]
            late_seed_id = int(seeds_after_sweep[1]["id"])

            with conn:
                with conn.cursor() as cur:
                    second_boundary_id = _insert_chunk(
                        cur, "Boundary after late formation"
                    )
                assert (
                    enqueue_scene_experience_job_sync(
                        conn,
                        boundary_chunk_id=second_boundary_id,
                        scene_end_chunk_id=next_chunk_id,
                        world_layer="primary",
                        slot=708,
                        settings=settings,
                    )
                    == 1
                )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT experience_ids
                    FROM character_experience_jobs
                    WHERE boundary_chunk_id = %s
                    """,
                    (second_boundary_id,),
                )
                assert cur.fetchone()["experience_ids"] == [late_seed_id]

            final_chunk_id = _accept_turn(
                conn,
                parent_chunk_id=second_boundary_id,
                proposal=None,
                characters=[],
            )
            assert final_chunk_id > second_boundary_id
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT count(*) AS count FROM character_experiences")
                final_count = int(cur.fetchone()["count"])
                cur.execute(
                    """
                    SELECT count(*) AS count
                    FROM world_events
                    WHERE id = ANY(%s) AND experiences_formed_at IS NOT NULL
                    """,
                    (first_seed["world_event_ids"] + late_event_ids,),
                )
                stamped_count = int(cur.fetchone()["count"])
            assert final_count == 2
            assert stamped_count == 2
        finally:
            conn.close()


def _form_sleep_seed(*, late: bool) -> bytes:
    with _disposable_database() as dbname:
        conn = _connect(dbname)
        try:
            parent_chunk_id, actor_character_id, _actor_entity_id = _setup_due_actor(
                conn
            )
            proposal = _resolve_sleep(dbname, parent_chunk_id)
            if late:
                event_anchor = _accept_turn(
                    conn,
                    parent_chunk_id=parent_chunk_id,
                    proposal=None,
                    characters=[],
                )
                _pin_next_world_event_id(conn, 708000001)
                with conn:
                    result = commit_orrery_tick_sync(
                        conn,
                        proposal,
                        tick_chunk_id=event_anchor,
                    )
                assert result.event_count == 1
                _accept_turn(
                    conn,
                    parent_chunk_id=event_anchor,
                    proposal=None,
                    characters=[],
                )
            else:
                _pin_next_world_event_id(conn, 708000001)
                event_anchor = _accept_turn(
                    conn,
                    parent_chunk_id=parent_chunk_id,
                    proposal=proposal,
                    characters=[],
                )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id
                    FROM world_events
                    WHERE tick_chunk_id = %s AND event_type = 'slept'
                    ORDER BY id
                    """,
                    (event_anchor,),
                )
                event_ids = [int(row["id"]) for row in cur.fetchall()]
            assert len(event_ids) == 1
            return _seed_bytes_for_event(conn, event_ids[0])
        finally:
            conn.close()


def test_late_seed_bytes_equal_commit_time_seed_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seed content and identity derive from event rows, never sweep timing."""

    monkeypatch.setattr(
        "nexus.api.presence_audit.presence_audit_enabled", lambda: False
    )
    assert _form_sleep_seed(late=True) == _form_sleep_seed(late=False)


@pytest.mark.parametrize(
    ("include_player_character", "expected_count"),
    [(False, 0), (True, 1)],
)
def test_player_experience_ownership_follows_config(
    monkeypatch: pytest.MonkeyPatch,
    include_player_character: bool,
    expected_count: int,
) -> None:
    """The canonical player owns no seed by default and can be opted in."""

    monkeypatch.setattr(
        "nexus.api.presence_audit.presence_audit_enabled", lambda: False
    )
    settings = load_settings_as_dict()
    settings["orrery"]["experiences"][
        "include_player_character"
    ] = include_player_character
    monkeypatch.setattr(
        "nexus.api.commit_handler_sync._load_orrery_settings",
        lambda: settings["orrery"],
    )
    with _disposable_database() as dbname:
        conn = _connect(dbname)
        try:
            parent_chunk_id, actor_character_id, actor_entity_id = _setup_due_actor(
                conn
            )
            with conn:
                with conn.cursor() as cur:
                    _set_player_character(cur, actor_character_id)
            proposal = _resolve_sleep(dbname, parent_chunk_id)
            accepted_chunk_id = _accept_turn(
                conn,
                parent_chunk_id=parent_chunk_id,
                proposal=proposal,
                characters=[],
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT count(*) AS count
                    FROM character_experiences
                    WHERE character_entity_id = %s
                    """,
                    (actor_entity_id,),
                )
                owned_count = int(cur.fetchone()["count"])
                cur.execute(
                    """
                    SELECT count(*) AS count
                    FROM world_events
                    WHERE tick_chunk_id = %s
                      AND event_type = 'slept'
                      AND resolution_id IS NOT NULL
                      AND experiences_formed_at IS NOT NULL
                    """,
                    (accepted_chunk_id,),
                )
                stamped_count = int(cur.fetchone()["count"])
            assert owned_count == expected_count
            assert stamped_count == 1
        finally:
            conn.close()


def test_default_config_rejects_an_existing_player_render_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default exclusion stale-rejects queued player work before rendering."""

    monkeypatch.setattr(
        "nexus.api.presence_audit.presence_audit_enabled", lambda: False
    )
    opt_in_settings = load_settings_as_dict()
    opt_in_settings["orrery"]["experiences"]["include_player_character"] = True
    monkeypatch.setattr(
        "nexus.api.commit_handler_sync._load_orrery_settings",
        lambda: opt_in_settings["orrery"],
    )
    with _disposable_database() as dbname:
        conn = _connect(dbname)
        try:
            parent_chunk_id, actor_character_id, actor_entity_id = _setup_due_actor(
                conn
            )
            with conn:
                with conn.cursor() as cur:
                    _set_player_character(cur, actor_character_id)
            proposal = _resolve_sleep(dbname, parent_chunk_id)
            accepted_chunk_id = _accept_turn(
                conn,
                parent_chunk_id=parent_chunk_id,
                proposal=proposal,
                characters=[],
            )
            with conn:
                with conn.cursor() as cur:
                    boundary_chunk_id = _insert_chunk(cur, "Player render boundary")
                assert (
                    enqueue_scene_experience_job_sync(
                        conn,
                        boundary_chunk_id=boundary_chunk_id,
                        scene_end_chunk_id=accepted_chunk_id,
                        world_layer="primary",
                        slot=708,
                        settings=opt_in_settings,
                    )
                    == 1
                )
            forbidden_provider = _ForbiddenSceneProvider()
            rendered, failed = drain_experience_render_jobs_sync(
                slot=708,
                settings=load_settings_as_dict(),
                conn=conn,
                provider=forbidden_provider,
            )
            assert (rendered, failed) == (0, 1)
            assert forbidden_provider.calls == 0
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT character_entity_id FROM character_experiences")
                assert [int(row["character_entity_id"]) for row in cur.fetchall()] == [
                    actor_entity_id
                ]
                cur.execute(
                    """
                    SELECT state::text AS state, last_error
                    FROM character_experience_jobs
                    """
                )
                job = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT experience_text
                    FROM character_experiences
                    WHERE character_entity_id = %s
                    """,
                    (actor_entity_id,),
                )
                assert cur.fetchone()["experience_text"] is None
            assert job["state"] == "stale_rejected"
            assert "player-owned seed" in job["last_error"]
        finally:
            conn.close()


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
                    boundary_place_id = _insert_place(cur, "Departure Platform")
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
                        characters=[
                            (actor_character_id, "Aster Vale"),
                            (witness_character_id, "Beren Quill"),
                            (extra_character_id, "Passing Extra"),
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
            ] == [(actor_entity_id, "participant")]
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
            assert witness_entity_id not in {
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
                        characters=[(actor_character_id, "Aster Vale")],
                        scene_boundary=True,
                        place=(boundary_place_id, "Departure Platform"),
                    )
            boundary_chunk_id = commit_incubator_to_database_sync(
                conn, boundary_session, slot=677
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT state::text AS state, experience_ids,
                           boundary_chunk_id, lease_nonce, requested_model
                    FROM character_experience_jobs
                    """
                )
                job = dict(cur.fetchone())
            assert job["state"] == "queued"
            assert job["boundary_chunk_id"] == boundary_chunk_id
            assert len(job["experience_ids"]) == 1
            assert job["lease_nonce"] is None
            assert job["requested_model"] == settings["orrery"]["experiences"]["model"]

            render_settings = deepcopy(settings)
            render_settings["orrery"]["experiences"]["model"] = "render-time-model"
            rendered, failed = drain_experience_render_jobs_sync(
                slot=677,
                settings=render_settings,
                conn=conn,
                provider=_IdleTransactionProvider(conn),
            )
            assert (rendered, failed) == (1, 0)
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
                row["render_model"] == "render-time-model" for row in rendered_rows
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


def test_private_hunt_seeds_only_verified_actor_receipt() -> None:
    """Present bystanders and a hidden target do not witness a private hunt."""
    settings = load_settings_as_dict()
    with _disposable_database() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                with conn.cursor() as cur:
                    chunk_id = _insert_chunk(cur, "Issue 677 private hunt")
                    actor_character_id, actor_entity_id = _insert_character(
                        cur,
                        "Hidden Hunter",
                        summary="A patient tracker.",
                        background="Trained beyond the city walls.",
                    )
                    target_character_id, target_entity_id = _insert_character(
                        cur,
                        "Unaware Quarry",
                        summary="A guarded traveler.",
                        background="Knows the old roads.",
                    )
                    bystander_character_id, bystander_entity_id = _insert_character(
                        cur,
                        "Nearby Bystander",
                        summary="A diligent clerk.",
                        background="Works beside the square.",
                    )
                    cur.executemany(
                        """
                        INSERT INTO chunk_character_references (
                            chunk_id, character_id, reference
                        ) VALUES (%s, %s, 'present')
                        """,
                        [
                            (chunk_id, actor_character_id),
                            (chunk_id, target_character_id),
                            (chunk_id, bystander_character_id),
                        ],
                    )
                    cur.execute(
                        """
                        INSERT INTO world_events (
                            event_type, tick_chunk_id, actor_entity_id,
                            target_entity_id, world_layer, source,
                            changed_fields, payload
                        ) VALUES (
                            'hunt_declared', %s, %s, %s, 'primary', 'resolver',
                            '{}', '{"hidden": true}'::jsonb
                        ) RETURNING id
                        """,
                        (chunk_id, actor_entity_id, target_entity_id),
                    )
                    event_id = int(cur.fetchone()[0])
                    cur.executemany(
                        """
                        INSERT INTO world_event_entities (event_id, entity_id, role)
                        VALUES (%s, %s, %s)
                        """,
                        [
                            (event_id, actor_entity_id, "actor"),
                            (event_id, target_entity_id, "target"),
                        ],
                    )
                assert (
                    seed_character_experiences_sync(
                        conn,
                        anchor_chunk_id=chunk_id,
                        settings=settings,
                    )
                    == 1
                )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT character_entity_id, basis::text AS basis,
                           world_event_ids, seed_summary
                    FROM character_experiences
                    ORDER BY id
                    """
                )
                rows = [dict(row) for row in cur.fetchall()]
            assert len(rows) == 1
            assert rows[0]["character_entity_id"] == actor_entity_id
            assert rows[0]["basis"] == "participant"
            assert rows[0]["world_event_ids"] == [event_id]
            assert "hunt_declared" in rows[0]["seed_summary"]
            assert target_entity_id not in {row["character_entity_id"] for row in rows}
            assert bystander_entity_id not in {
                row["character_entity_id"] for row in rows
            }
        finally:
            conn.close()


def test_boundary_batches_are_bounded_and_timeline_drift_is_rejected() -> None:
    """Boundary overflow splits, and locked completion rejects timeline drift."""
    settings = load_settings_as_dict()
    settings["orrery"]["experiences"]["max_seeds_per_render"] = 2
    with _disposable_database() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                with conn.cursor() as cur:
                    scene_end_chunk_id = _insert_chunk(cur, "Bounded scene")
                    for ordinal in range(3):
                        _character_id, entity_id = _insert_character(
                            cur,
                            f"Batch Actor {ordinal}",
                            summary=f"Actor {ordinal} has a complete dossier.",
                            background="Present for a verified event role.",
                        )
                        cur.execute(
                            """
                            INSERT INTO world_events (
                                event_type, tick_chunk_id, actor_entity_id,
                                world_layer, source, changed_fields, payload
                            ) VALUES (
                                'slept', %s, %s, 'primary', 'resolver',
                                '{}', '{}'::jsonb
                            ) RETURNING id
                            """,
                            (scene_end_chunk_id, entity_id),
                        )
                        event_id = int(cur.fetchone()[0])
                        cur.execute(
                            """
                            INSERT INTO world_event_entities (
                                event_id, entity_id, role
                            ) VALUES (%s, %s, 'actor')
                            """,
                            (event_id, entity_id),
                        )
                assert (
                    seed_character_experiences_sync(
                        conn,
                        anchor_chunk_id=scene_end_chunk_id,
                        settings=settings,
                    )
                    == 3
                )
                with conn.cursor() as cur:
                    boundary_chunk_id = _insert_chunk(cur, "Bounded boundary")
                assert (
                    enqueue_scene_experience_job_sync(
                        conn,
                        boundary_chunk_id=boundary_chunk_id,
                        scene_end_chunk_id=scene_end_chunk_id,
                        world_layer="primary",
                        slot=677,
                        settings=settings,
                    )
                    == 2
                )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT batch_ordinal, cardinality(experience_ids) AS seed_count
                    FROM character_experience_jobs
                    ORDER BY batch_ordinal
                    """
                )
                assert [dict(row) for row in cur.fetchall()] == [
                    {"batch_ordinal": 0, "seed_count": 2},
                    {"batch_ordinal": 1, "seed_count": 1},
                ]
            rendered, failed = drain_experience_render_jobs_sync(
                slot=677,
                settings=settings,
                conn=conn,
                provider=_TimelineDriftingProvider(dbname),
                limit=1,
            )
            assert (rendered, failed) == (0, 1)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT state::text AS state, last_error
                    FROM character_experience_jobs
                    ORDER BY id
                    """
                )
                jobs = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """
                    SELECT count(*) FILTER (WHERE experience_text IS NOT NULL)
                           AS rendered_count
                    FROM character_experiences
                    """
                )
                rendered_count = int(cur.fetchone()["rendered_count"])
            assert jobs[0]["state"] == "stale_rejected"
            assert "boundary timeline is stale" in jobs[0]["last_error"]
            assert jobs[1]["state"] == "queued"
            assert rendered_count == 0
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
                    _incident_character_id, incident_actor_id = _insert_character(
                        cur,
                        "Dorian Pike",
                        summary=None,
                        background=None,
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
                        (chunk_id, incident_actor_id),
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
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT id, character_entity_id, world_event_ids,
                               claim_id, claim_awareness_id,
                               basis::text AS basis, location_id
                        FROM character_experiences
                        WHERE claim_awareness_id = %s
                        """,
                        (awareness_id,),
                    )
                    acquisition_scope_row = dict(cur.fetchone())
                    known, allowed = _known_and_allowed_names(
                        cur, acquisition_scope_row
                    )
                assert "Dorian Pike" in known
                assert "Dorian Pike" not in allowed
                invented_incident_witnessing = ExperienceRenderBatch(
                    recollections=[
                        ExperienceRecollection(
                            experience_id=int(acquisition_scope_row["id"]),
                            experience_text=(
                                "I heard the account from Cora Flint. "
                                "Dorian Pike opened the gate before me."
                            ),
                        )
                    ]
                )
                with pytest.raises(
                    ValueError, match="absent from its source scene.*Dorian Pike"
                ):
                    validate_render_batch(
                        [acquisition_scope_row],
                        invented_incident_witnessing,
                        names_by_experience={
                            int(acquisition_scope_row["id"]): (known, allowed)
                        },
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
