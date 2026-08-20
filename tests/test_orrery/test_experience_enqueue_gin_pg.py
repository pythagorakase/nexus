"""PostgreSQL proofs for the experience-job enqueue containment fence."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
import pytest

from nexus.agents.orrery.experiences import (
    _ENQUEUE_CANDIDATES_SQL,
    enqueue_scene_experience_job_sync,
)
from nexus.config import load_settings_as_dict
from scripts import new_story_setup


pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "migrations" / "111_experience_job_enqueue_gin_fence.sql"
INDEX_NAME = "ix_character_experience_jobs_pending_experience_ids"
BLOCKING_STATES = ("queued", "leased", "failed")
TERMINAL_STATES = ("succeeded", "stale_rejected")


def _connect(dbname: str) -> Any:
    """Open a direct PostgreSQL connection to the disposable database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


@pytest.fixture(scope="module")
def experience_enqueue_database() -> Iterator[str]:
    """Yield a dump-initialized database with migration 111 applied twice."""

    dbname = f"qa_wt720_{uuid4().hex[:12]}"
    admin: Any = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        new_story_setup.initialize_slot_database(
            dbname,
            source_db="NEXUS_template",
        )
        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                migration_sql = MIGRATION.read_text()
                cur.execute(migration_sql)
                cur.execute(migration_sql)
        yield dbname
    finally:
        new_story_setup.USE_POOL = original_use_pool
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


@pytest.fixture()
def conn(experience_enqueue_database: str) -> Iterator[Any]:
    """Run each enqueue proof in a rollback-only transaction."""

    connection = _connect(experience_enqueue_database)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _insert_chunk(cur: Any, label: str, *, scene: int) -> int:
    cur.execute(
        "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
        "VALUES (%s, %s) RETURNING id",
        (label, label),
    )
    chunk_id = int(cur.fetchone()[0])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, slug, world_time
        ) VALUES (%s, 1, 1, %s, 'primary', %s, %s)
        """,
        (
            chunk_id,
            scene,
            f"q{chunk_id}",
            datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc),
        ),
    )
    return chunk_id


def _insert_character(cur: Any, name: str) -> tuple[int, int]:
    cur.execute("INSERT INTO entities (kind) VALUES ('character') RETURNING id")
    entity_id = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO characters (name, entity_id) VALUES (%s, %s) RETURNING id",
        (name, entity_id),
    )
    return int(cur.fetchone()[0]), entity_id


def _set_player(cur: Any) -> None:
    base_timestamp = datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc)
    cur.execute(
        """
        INSERT INTO global_variables (id, base_timestamp)
        VALUES (true, %s)
        ON CONFLICT (id) DO UPDATE
        SET base_timestamp = EXCLUDED.base_timestamp
        """,
        (base_timestamp,),
    )
    player_character_id, _player_entity_id = _insert_character(
        cur, f"Fence Player {uuid4().hex}"
    )
    cur.execute(
        """
        INSERT INTO global_variables (id, user_character, base_timestamp)
        VALUES (true, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET user_character = EXCLUDED.user_character,
            base_timestamp = EXCLUDED.base_timestamp
        """,
        (player_character_id, base_timestamp),
    )


def _insert_experiences(cur: Any, anchor_chunk_id: int, count: int) -> list[int]:
    ids: list[int] = []
    for ordinal in range(count):
        cur.execute("INSERT INTO entities (kind) VALUES ('character') RETURNING id")
        owner_id = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO character_experiences (
                character_entity_id, anchor_chunk_id, world_event_ids,
                basis, world_time, seed_summary, salience, source_digest,
                world_layer
            ) VALUES (
                %s, %s, %s, 'participant', %s, %s, 0.5, %s, 'primary'
            )
            RETURNING id
            """,
            (
                owner_id,
                anchor_chunk_id,
                [ordinal + 1],
                datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc),
                f"Fence seed {ordinal}",
                f"qa-wt720-{uuid4().hex}",
            ),
        )
        ids.append(int(cur.fetchone()[0]))
    return ids


def _insert_job(
    cur: Any,
    *,
    boundary_chunk_id: int,
    scene_end_chunk_id: int,
    batch_ordinal: int,
    experience_ids: list[int],
    state: str,
) -> None:
    cur.execute(
        """
        INSERT INTO character_experience_jobs (
            boundary_chunk_id, scene_end_chunk_id, world_layer,
            boundary_season, boundary_episode, boundary_scene,
            scene_end_season, scene_end_episode, scene_end_scene,
            batch_ordinal, experience_ids, slot, state, requested_model,
            source_digest
        ) VALUES (
            %s, %s, 'primary', 1, 1, 2, 1, 1, 1,
            %s, %s, 'qa_wt720', %s::orrery_job_state, '@openai.gaia', %s
        )
        """,
        (
            boundary_chunk_id,
            scene_end_chunk_id,
            batch_ordinal,
            experience_ids,
            state,
            f"qa-wt720-job-{uuid4().hex}",
        ),
    )


def _setup_enqueue_case(cur: Any, experience_count: int) -> tuple[int, int, list[int]]:
    _set_player(cur)
    scene_end_chunk_id = _insert_chunk(cur, "Fence scene end", scene=1)
    prior_boundary_chunk_id = _insert_chunk(cur, "Prior fence boundary", scene=2)
    enqueue_boundary_chunk_id = _insert_chunk(cur, "New fence boundary", scene=3)
    experience_ids = _insert_experiences(cur, scene_end_chunk_id, experience_count)
    return (
        scene_end_chunk_id,
        prior_boundary_chunk_id,
        experience_ids + [enqueue_boundary_chunk_id],
    )


def _enqueue_and_read_ids(
    conn: Any,
    *,
    scene_end_chunk_id: int,
    boundary_chunk_id: int,
) -> list[int]:
    inserted = enqueue_scene_experience_job_sync(
        conn,
        boundary_chunk_id=boundary_chunk_id,
        scene_end_chunk_id=scene_end_chunk_id,
        world_layer="primary",
        slot=720,
        settings=load_settings_as_dict(),
    )
    assert inserted == 1
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT experience_ids
            FROM character_experience_jobs
            WHERE boundary_chunk_id = %s
            """,
            (boundary_chunk_id,),
        )
        return [int(value) for value in cur.fetchone()["experience_ids"]]


@pytest.mark.parametrize("state", BLOCKING_STATES)
def test_each_pending_state_blocks_its_experience_and_absent_id_enqueues(
    conn: Any,
    state: str,
) -> None:
    """Each pending state blocks its id while an absent id still enqueues."""

    with conn.cursor() as cur:
        scene_end_chunk_id, prior_boundary_chunk_id, values = _setup_enqueue_case(
            cur, 2
        )
        blocked_id, absent_id, enqueue_boundary_chunk_id = values
        _insert_job(
            cur,
            boundary_chunk_id=prior_boundary_chunk_id,
            scene_end_chunk_id=scene_end_chunk_id,
            batch_ordinal=0,
            experience_ids=[blocked_id],
            state=state,
        )

    assert _enqueue_and_read_ids(
        conn,
        scene_end_chunk_id=scene_end_chunk_id,
        boundary_chunk_id=enqueue_boundary_chunk_id,
    ) == [absent_id]


@pytest.mark.parametrize("state", TERMINAL_STATES)
def test_terminal_states_do_not_block_enqueue(conn: Any, state: str) -> None:
    """Succeeded and stale-rejected jobs do not own the enqueue fence."""

    with conn.cursor() as cur:
        scene_end_chunk_id, prior_boundary_chunk_id, values = _setup_enqueue_case(
            cur, 2
        )
        terminal_id, absent_id, enqueue_boundary_chunk_id = values
        _insert_job(
            cur,
            boundary_chunk_id=prior_boundary_chunk_id,
            scene_end_chunk_id=scene_end_chunk_id,
            batch_ordinal=0,
            experience_ids=[terminal_id],
            state=state,
        )

    assert _enqueue_and_read_ids(
        conn,
        scene_end_chunk_id=scene_end_chunk_id,
        boundary_chunk_id=enqueue_boundary_chunk_id,
    ) == [terminal_id, absent_id]


def test_overlapping_pending_arrays_block_every_owned_id(conn: Any) -> None:
    """Overlapping pending arrays exclude shared and singly owned ids."""

    with conn.cursor() as cur:
        scene_end_chunk_id, prior_boundary_chunk_id, values = _setup_enqueue_case(
            cur, 4
        )
        shared_id, queued_only_id, failed_only_id, absent_id, boundary_id = values
        _insert_job(
            cur,
            boundary_chunk_id=prior_boundary_chunk_id,
            scene_end_chunk_id=scene_end_chunk_id,
            batch_ordinal=0,
            experience_ids=[shared_id, queued_only_id],
            state="queued",
        )
        _insert_job(
            cur,
            boundary_chunk_id=prior_boundary_chunk_id,
            scene_end_chunk_id=scene_end_chunk_id,
            batch_ordinal=1,
            experience_ids=[shared_id, failed_only_id],
            state="failed",
        )

    assert _enqueue_and_read_ids(
        conn,
        scene_end_chunk_id=scene_end_chunk_id,
        boundary_chunk_id=boundary_id,
    ) == [absent_id]


def _plan_index_names(node: dict[str, Any]) -> set[str]:
    names = {str(node["Index Name"])} if "Index Name" in node else set()
    for child in node.get("Plans", []):
        names.update(_plan_index_names(child))
    return names


def test_enqueue_select_uses_pending_experience_gin_index(conn: Any) -> None:
    """The real enqueue SELECT uses the partial GIN at the 5k/500/10 shape."""

    with conn.cursor() as cur:
        _set_player(cur)
        scene_end_chunk_id = _insert_chunk(cur, "Benchmark scene end", scene=1)
        boundary_chunk_id = _insert_chunk(cur, "Benchmark boundary", scene=2)
        cur.execute(
            """
            WITH owners AS (
                INSERT INTO entities (kind)
                SELECT 'character'
                FROM generate_series(1, 5000)
                RETURNING id
            )
            INSERT INTO character_experiences (
                character_entity_id, anchor_chunk_id, world_event_ids,
                basis, world_time, seed_summary, salience, source_digest,
                world_layer
            )
            SELECT id, %s, ARRAY[id], 'participant', %s,
                   'Benchmark fence seed ' || id::text, 0.5,
                   'qa-wt720-benchmark-' || id::text, 'primary'
            FROM owners
            """,
            (
                scene_end_chunk_id,
                datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc),
            ),
        )
        cur.execute(
            """
            INSERT INTO character_experience_jobs (
                boundary_chunk_id, scene_end_chunk_id, world_layer,
                boundary_season, boundary_episode, boundary_scene,
                scene_end_season, scene_end_episode, scene_end_scene,
                batch_ordinal, experience_ids, slot, state, requested_model,
                source_digest
            )
            SELECT %s, %s, 'primary', 1, 1, 2, 1, 1, 1,
                   grouped.batch_ordinal, grouped.experience_ids,
                   'qa_wt720', 'queued', '@openai.gaia',
                   'qa-wt720-benchmark-job-' || grouped.batch_ordinal::text
            FROM (
                SELECT ((numbered.ordinal - 1) / 10)::integer AS batch_ordinal,
                       array_agg(numbered.id ORDER BY numbered.id)
                           AS experience_ids
                FROM (
                    SELECT id, row_number() OVER (ORDER BY id) AS ordinal
                    FROM character_experiences
                    WHERE source_digest LIKE 'qa-wt720-benchmark-%%'
                ) numbered
                GROUP BY ((numbered.ordinal - 1) / 10)::integer
            ) grouped
            """,
            (boundary_chunk_id, scene_end_chunk_id),
        )
        cur.execute("ANALYZE character_experiences")
        cur.execute("ANALYZE character_experience_jobs")
        cur.execute(
            "EXPLAIN (FORMAT JSON) " + _ENQUEUE_CANDIDATES_SQL,
            (scene_end_chunk_id, "primary", None, None),
        )
        plan = cur.fetchone()[0][0]["Plan"]

    assert INDEX_NAME in _plan_index_names(plan)


def test_migration_index_is_partial_bigint_array_gin(conn: Any) -> None:
    """Migration 111 retains the exact partial GIN definition and comment."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT pg_get_indexdef(indexrelid),
                   obj_description(indexrelid, 'pg_class')
            FROM pg_index
            WHERE indexrelid = %s::regclass
            """,
            (INDEX_NAME,),
        )
        definition, comment = cur.fetchone()

    assert "USING gin (experience_ids)" in definition
    assert "'queued'::orrery_job_state" in definition
    assert "'leased'::orrery_job_state" in definition
    assert "'failed'::orrery_job_state" in definition
    assert "enqueue fence" in comment
