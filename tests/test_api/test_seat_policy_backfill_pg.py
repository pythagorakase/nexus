"""Migration 126 proof on an explicit pre-126 schema, with no provider construction.

A latest-schema clone has no migration 126 left to apply, so the backfill
under test would never run on one. The test takes a disposable template
clone, rolls it back to the pre-126 shape (the inverse of 126's DDL: the
eight ``resolved_model``/``resolved_source`` columns dropped and the ``126``
stamp removed, which the runner's pending set then reports), writes legacy
jobs in the pre-126 insert shape of each production enqueuer, and runs the
runner, which applies exactly migration 126 to the clone.
"""

from contextlib import closing
import json

from psycopg2 import sql
import pytest

from nexus.config import load_settings
from nexus.config.story_model import StorySettings, resolve_seat
from scripts import migrate
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_committed_chunk,
    seed_protagonist,
)

pytestmark = pytest.mark.requires_postgres

MIGRATION = "126"
RESOLVED_COLUMNS = ("resolved_model", "resolved_source")


def _migration_126():
    """Load migration 126 through the runner's own discovery and loader."""
    path = next(row for row in migrate.discover_migrations() if row[0] == MIGRATION)
    return migrate._load_python_migration(path[2])


def _roll_back_to_pre_126(dbname: str, tables: list[str]) -> None:
    """Drop the columns migration 126 adds and remove its stamp."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        for table in tables:
            cur.execute(
                sql.SQL("ALTER TABLE {} {}").format(
                    sql.Identifier(table),
                    sql.SQL(", ").join(
                        sql.SQL("DROP COLUMN {}").format(sql.Identifier(column))
                        for column in RESOLVED_COLUMNS
                    ),
                )
            )
        cur.execute("DELETE FROM schema_migrations WHERE version = %s", (MIGRATION,))
        assert cur.rowcount == 1, "the template clone carries no 126 stamp"


def _seed_legacy_jobs(
    dbname: str, chunks: list[int], entity_id: int, character_id: int
):
    """Write active and terminal legacy jobs in each enqueuer's pre-126 shape.

    Each statement is the production enqueuer's insert without the two
    columns migration 126 introduced (``experiences.py``,
    ``retrograde_maturation._enqueue_job``, ``compaction.enqueue_compaction``,
    ``summary_triggers.schedule_summary_generation``), followed by the state a
    job reaches in the queue. Returns ``{table: {"active": [...], "terminal":
    [...]}}``.
    """
    jobs: dict[str, dict[str, list[int]]] = {}
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:

        def insert(table: str, statement: str, params: tuple, state: str) -> None:
            cur.execute(statement + " RETURNING id", params)
            job_id = cur.fetchone()[0]
            if state != "queued":
                cur.execute(
                    sql.SQL(
                        "UPDATE {} SET state = %s::orrery_job_state WHERE id = %s"
                    ).format(sql.Identifier(table)),
                    (state, job_id),
                )
                assert cur.rowcount == 1
            bucket = "active" if state in ("queued", "leased") else "terminal"
            jobs.setdefault(table, {"active": [], "terminal": []})[bucket].append(
                job_id
            )

        for ordinal, (chunk, state) in enumerate(
            ((chunks[0], "succeeded"), (chunks[1], "queued"), (chunks[1], "leased"))
        ):
            insert(
                "character_experience_jobs",
                """INSERT INTO character_experience_jobs (
                    boundary_chunk_id, scene_end_chunk_id, world_layer,
                    boundary_season, boundary_episode, boundary_scene,
                    scene_end_season, scene_end_episode, scene_end_scene,
                    batch_ordinal, experience_ids, slot, requested_model,
                    source_digest
                ) VALUES (%s, %s, 'primary', 1, 1, 1, 1, 1, 1, %s, %s, '4',
                    'legacy', %s)""",
                (chunk, chunk, ordinal, [ordinal + 1], f"legacy-{ordinal}"),
                state,
            )
        insert(
            "orrery_maturation_jobs",
            """INSERT INTO orrery_maturation_jobs (
                entity_id, entity_kind, entity_subtype_id, entity_name,
                slot, requesting_chunk_id, declaration
            ) VALUES (%s, 'character', %s, 'Fixture Player', '4', %s, '{}'::jsonb)""",
            (entity_id, character_id, chunks[0]),
            "queued",
        )
        cur.execute(
            "INSERT INTO entities (kind, is_active) VALUES ('character', true) "
            "RETURNING id"
        )
        terminal_entity = cur.fetchone()[0]
        insert(
            "orrery_maturation_jobs",
            """INSERT INTO orrery_maturation_jobs (
                entity_id, entity_kind, entity_subtype_id, entity_name,
                slot, requesting_chunk_id, declaration
            ) VALUES (%s, 'character', %s, 'Retired Declaration', '4', %s,
                '{}'::jsonb)""",
            (terminal_entity, character_id, chunks[0]),
            "failed",
        )
        for chunk, state in ((chunks[0], "succeeded"), (chunks[1], "queued")):
            insert(
                "correspondence_compaction_jobs",
                "INSERT INTO correspondence_compaction_jobs (accepting_chunk_id) "
                "VALUES (%s)",
                (chunk,),
                state,
            )
        for kind, episode, state in (
            ("episode", 1, "succeeded"),
            ("episode", 2, "leased"),
            ("season", None, "queued"),
        ):
            insert(
                "narrative_summary_jobs",
                "INSERT INTO narrative_summary_jobs (kind, season, episode) "
                "VALUES (%s, 1, %s)",
                (kind, episode),
                state,
            )
    return jobs


def test_seat_policy_migration_backfills_legacy_active_jobs():
    """Run managed 126 on a pre-126 clone and preserve terminal NULL rows."""
    module = _migration_126()
    tables = list(module.JOB_SEATS)
    with disposable_slot_database("qa640_814_backfill") as dbname:
        character_id, entity_id = seed_protagonist(dbname)
        chunks = [
            seed_committed_chunk(dbname, raw_text="Legacy work anchor one.", scene=1),
            seed_committed_chunk(dbname, raw_text="Legacy work anchor two.", scene=2),
        ]
        _roll_back_to_pre_126(dbname, tables)
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = ANY(%s) "
                "AND column_name = ANY(%s)",
                (tables, list(RESOLVED_COLUMNS)),
            )
            assert cur.fetchone() == (0,), "the clone still has 126's columns"
            pending = [
                version
                for version, _, _ in migrate.discover_migrations()
                if version not in migrate.get_applied_migrations(conn)
            ]
        assert pending == [MIGRATION], pending
        jobs = _seed_legacy_jobs(dbname, chunks, entity_id, character_id)
        assert set(jobs) == set(tables)
        assert all(
            entry["active"] and entry["terminal"] for entry in jobs.values()
        ), jobs
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT model, gaia_model, apex_context_window FROM global_variables WHERE id=TRUE"
            )
            row = cur.fetchone()
        story = StorySettings(
            skald_model=row[0],
            gaia_model=row[1],
            apex_context_window=row[2],
            dbname=dbname,
        )

        applied, failed = migrate.migrate_database(dbname, skip_locked=False)
        assert (applied, failed) == (1, 0)

        proof = {}
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            for table, seat in module.JOB_SEATS.items():
                expected = resolve_seat(
                    seat, settings=load_settings(), story=story
                ).model
                cur.execute(
                    sql.SQL(
                        "SELECT id, resolved_model, resolved_source FROM {} WHERE state IN ('queued','leased') ORDER BY id"
                    ).format(sql.Identifier(table))
                )
                rows = cur.fetchall()
                assert [row[0] for row in rows] == jobs[table]["active"]
                assert all(row[1:] == (expected, "migration_backfill") for row in rows)
                proof[table] = rows
                cur.execute(
                    sql.SQL(
                        "SELECT id FROM {} WHERE state NOT IN ('queued','leased') AND resolved_model IS NULL AND resolved_source IS NULL ORDER BY id"
                    ).format(sql.Identifier(table))
                )
                assert [row[0] for row in cur.fetchall()] == jobs[table]["terminal"]
                cur.execute(
                    sql.SQL(
                        "SELECT count(*) FROM {} WHERE state NOT IN ('queued','leased') AND (resolved_model IS NOT NULL OR resolved_source IS NOT NULL)"
                    ).format(sql.Identifier(table))
                )
                assert cur.fetchone() == (0,)
            cur.execute("SELECT version FROM schema_migrations WHERE version='126'")
            assert cur.fetchone() == ("126",)
        print(f"Migration 126 applied only to {dbname}; source pin={story.skald_model}")
        print("Backfilled jobs: " + json.dumps(proof))
