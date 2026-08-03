"""PostgreSQL regressions for accepted-chunk Orrery configuration reuse."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Iterator

import asyncpg  # type: ignore[import-untyped]
import psycopg2
import pytest
from psycopg2 import sql

import nexus.config as config_module
from nexus.api import commit_handler, commit_handler_sync


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    """Open a direct psycopg2 connection to a disposable database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@pytest.fixture()
def qa654_db() -> Iterator[str]:
    """Clone NEXUS_template into a qa654 database and drop it after the test."""

    dbname = f"qa654_{uuid.uuid4().hex[:12]}"
    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )
        yield dbname
    finally:
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


def _seed_commit(dbname: str, session_id: str) -> int:
    """Seed one parent and proposal-free incubator turn; return the parent id."""

    with _connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE incubator, narrative_chunks RESTART IDENTITY CASCADE")
            cur.execute(
                """
                INSERT INTO narrative_chunks (raw_text, storyteller_text, state)
                VALUES ('Parent scene.', 'Parent scene.', 'finalized')
                RETURNING id
                """
            )
            parent_chunk_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO chunk_metadata (
                    chunk_id, season, episode, scene, world_layer, slug
                ) VALUES (%s, 1, 1, 1, 'primary', 'S01E01_001')
                """,
                (parent_chunk_id,),
            )
            cur.execute(
                """
                INSERT INTO incubator (
                    id, chunk_id, parent_chunk_id, user_text, storyteller_text,
                    generation_model, metadata_updates, entity_updates,
                    reference_updates, orrery_proposal, orrery_adjudications,
                    new_entities, session_id, llm_response_id, status
                ) VALUES (
                    TRUE, 2, %s, 'continue', 'Accepted scene.', 'TEST',
                    '{}'::jsonb, NULL, '{}'::jsonb, NULL, '[]'::jsonb,
                    '[]'::jsonb, %s, 'qa654-response', 'provisional'
                )
                """,
                (parent_chunk_id, session_id),
            )
    return parent_chunk_id


def _disable_presence_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the regression scoped to the accepted-chunk transaction."""

    monkeypatch.setattr(
        "nexus.api.presence_audit.presence_audit_enabled",
        lambda: False,
    )


def test_sync_commit_loads_application_config_once(
    qa654_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The genuine sync commit reuses one Orrery settings mapping."""

    session_id = "00000000-0000-0000-0000-000000000654"
    parent_chunk_id = _seed_commit(qa654_db, session_id)
    _disable_presence_audit(monkeypatch)

    original_loader = config_module.load_settings_as_dict
    original_tick = commit_handler_sync.commit_orrery_tick_sync
    original_checkpoint = commit_handler_sync._orrery_checkpoint_interval
    loaded_settings: list[dict[str, Any]] = []
    tick_kwargs: list[dict[str, Any]] = []
    checkpoint_settings: list[Any] = []

    def counted_loader() -> dict[str, Any]:
        settings = original_loader()
        loaded_settings.append(settings)
        return settings

    def recording_tick(conn: Any, proposal: Any, **kwargs: Any) -> Any:
        tick_kwargs.append(kwargs)
        return original_tick(conn, proposal, **kwargs)

    def recording_checkpoint(settings: Any) -> int:
        checkpoint_settings.append(settings)
        return original_checkpoint(settings)

    monkeypatch.setattr(config_module, "load_settings_as_dict", counted_loader)
    monkeypatch.setattr(commit_handler_sync, "commit_orrery_tick_sync", recording_tick)
    monkeypatch.setattr(
        commit_handler_sync,
        "_orrery_checkpoint_interval",
        recording_checkpoint,
    )

    conn = _connect(qa654_db)
    try:
        committed_chunk_id = commit_handler_sync.commit_incubator_to_database_sync(
            conn, session_id
        )
    finally:
        conn.close()

    assert committed_chunk_id > parent_chunk_id
    assert len(loaded_settings) == 1
    orrery = loaded_settings[0]["orrery"]
    assert checkpoint_settings == [orrery]
    assert tick_kwargs == [
        {
            "tick_chunk_id": committed_chunk_id,
            "slot": None,
            "world_layer": "primary",
            "adjudications": [],
            "storyteller_state_updates": None,
            "prompt_settings": orrery.get("prompt"),
            "ecology_settings": orrery.get("ecology"),
            "project_settings": orrery.get("projects"),
            "mood_settings": orrery.get("mood"),
            "epistemics_settings": orrery.get("epistemics"),
            "contagion_settings": orrery.get("contagion"),
            "distortion_settings": orrery.get("distortion"),
            "drift_settings": orrery.get("drift"),
            "reveal_settings": orrery.get("reveal"),
        }
    ]


@pytest.mark.asyncio
async def test_async_commit_loads_application_config_once(
    qa654_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The genuine async commit reuses one Orrery settings mapping."""

    session_id = "00000000-0000-0000-0000-000000006540"
    parent_chunk_id = _seed_commit(qa654_db, session_id)
    _disable_presence_audit(monkeypatch)

    original_loader = config_module.load_settings_as_dict
    original_tick = commit_handler.commit_orrery_tick_async
    original_checkpoint = commit_handler._orrery_checkpoint_interval
    loaded_settings: list[dict[str, Any]] = []
    tick_kwargs: list[dict[str, Any]] = []
    checkpoint_settings: list[Any] = []

    def counted_loader() -> dict[str, Any]:
        settings = original_loader()
        loaded_settings.append(settings)
        return settings

    async def recording_tick(conn: Any, proposal: Any, **kwargs: Any) -> Any:
        tick_kwargs.append(kwargs)
        return await original_tick(conn, proposal, **kwargs)

    def recording_checkpoint(settings: Any) -> int:
        checkpoint_settings.append(settings)
        return original_checkpoint(settings)

    monkeypatch.setattr(config_module, "load_settings_as_dict", counted_loader)
    monkeypatch.setattr(commit_handler, "commit_orrery_tick_async", recording_tick)
    monkeypatch.setattr(
        commit_handler,
        "_orrery_checkpoint_interval",
        recording_checkpoint,
    )

    conn = await asyncpg.connect(
        database=qa654_db,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )
    for type_name in ("json", "jsonb"):
        await conn.set_type_codec(
            type_name,
            schema="pg_catalog",
            encoder=json.dumps,
            decoder=json.loads,
        )
    try:
        committed_chunk_id = await commit_handler.commit_incubator_to_database(
            conn, session_id
        )
    finally:
        await conn.close()

    assert committed_chunk_id > parent_chunk_id
    assert len(loaded_settings) == 1
    orrery = loaded_settings[0]["orrery"]
    assert checkpoint_settings == [orrery]
    assert tick_kwargs == [
        {
            "tick_chunk_id": committed_chunk_id,
            "slot": None,
            "world_layer": "primary",
            "adjudications": [],
            "storyteller_state_updates": None,
            "prompt_settings": orrery.get("prompt"),
            "ecology_settings": orrery.get("ecology"),
            "project_settings": orrery.get("projects"),
            "mood_settings": orrery.get("mood"),
            "epistemics_settings": orrery.get("epistemics"),
            "contagion_settings": orrery.get("contagion"),
            "distortion_settings": orrery.get("distortion"),
            "drift_settings": orrery.get("drift"),
            "reveal_settings": orrery.get("reveal"),
        }
    ]
