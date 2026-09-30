"""PostgreSQL contract for migration 094 on a disposable empty database."""

from contextlib import closing
from pathlib import Path

import psycopg2
import pytest

from tests.pg_fixtures import connect, disposable_database


pytestmark = pytest.mark.requires_postgres


def test_scene_weather_check_rejects_unknown_value() -> None:
    migration = (
        Path(__file__).parents[2] / "migrations" / "094_scene_weather_override.sql"
    ).read_text()
    with disposable_database("qa640_weather_migration") as dbname:
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE chunk_metadata (
                    chunk_id bigint PRIMARY KEY
                )
                """
            )
            cur.execute(migration)
            cur.execute(
                "INSERT INTO chunk_metadata (chunk_id, scene_weather) "
                "VALUES (1, 'warm')"
            )
            cur.execute("SAVEPOINT before_bad_weather")
            with pytest.raises(psycopg2.errors.CheckViolation):
                cur.execute(
                    "INSERT INTO chunk_metadata (chunk_id, scene_weather) "
                    "VALUES (2, 'hail')"
                )
            cur.execute("ROLLBACK TO SAVEPOINT before_bad_weather")
            cur.execute("SELECT chunk_id, scene_weather FROM chunk_metadata")
            assert cur.fetchall() == [(1, "warm")]
