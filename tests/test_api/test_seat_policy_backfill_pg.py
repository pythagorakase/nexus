"""Migration proof using the unchanged paid pin, with no provider construction."""

from contextlib import closing
import json
import subprocess
from uuid import uuid4

from psycopg2 import sql
from psycopg2.extensions import make_dsn
import pytest

from nexus.config import load_settings
from nexus.config.story_model import StorySettings, resolve_seat
from scripts import migrate
from tests.pg_fixtures import connect, connection_parameters

pytestmark = pytest.mark.requires_postgres


def test_seat_policy_migration_backfills_save04_active_jobs(tmp_path):
    """Run managed 126 on a corpus snapshot and preserve terminal NULL rows."""
    dbname = f"qa640_814_backfill_{uuid4().hex[:12]}"
    archive = tmp_path / "save04.dump"
    subprocess.run(
        [
            "pg_dump",
            "--format=custom",
            "--file",
            str(archive),
            "--dbname",
            make_dsn(dbname="save_04", **connection_parameters()),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    with closing(connect("postgres")) as admin:
        admin.autocommit = True
        try:
            with admin.cursor() as cur:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                        sql.Identifier(dbname)
                    )
                )
            subprocess.run(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--dbname",
                    make_dsn(dbname=dbname, **connection_parameters()),
                    str(archive),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            migration = next(
                row for row in migrate.discover_migrations() if row[0] == "126"
            )
            module = migrate._load_python_migration(migration[2])
            with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
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
                active = {}
                for table in module.JOB_SEATS:
                    cur.execute(
                        sql.SQL(
                            "SELECT id FROM {} WHERE state IN ('queued','leased') ORDER BY id"
                        ).format(sql.Identifier(table))
                    )
                    active[table] = [row[0] for row in cur.fetchall()]
                assert active[
                    "character_experience_jobs"
                ], "Source must contain legacy queued experiences"
            applied, failed = migrate.migrate_database(dbname, skip_locked=False)
            assert failed == 0 and applied >= 1
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
                    assert [row[0] for row in rows] == active[table]
                    assert all(
                        row[1:] == (expected, "migration_backfill") for row in rows
                    )
                    proof[table] = rows
                    cur.execute(
                        sql.SQL(
                            "SELECT count(*) FROM {} WHERE state NOT IN ('queued','leased') AND (resolved_model IS NOT NULL OR resolved_source IS NOT NULL)"
                        ).format(sql.Identifier(table))
                    )
                    assert cur.fetchone() == (0,)
                cur.execute("SELECT version FROM schema_migrations WHERE version='126'")
                assert cur.fetchone() == ("126",)
            print(
                f"Migration 126 applied only to {dbname}; source pin={story.skald_model}"
            )
            print("Backfilled jobs: " + json.dumps(proof))
        finally:
            with admin.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()",
                    (dbname,),
                )
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
