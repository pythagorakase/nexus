"""Rollback-only PostgreSQL contract for migration 094."""

from pathlib import Path
import uuid

import psycopg2
import pytest

from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


def test_scene_weather_check_rejects_unknown_value() -> None:
    conn = psycopg2.connect(get_slot_db_url(slot=5))
    schema = f"weather_migration_{uuid.uuid4().hex}"
    migration = (
        Path(__file__).parents[2] / "migrations" / "094_scene_weather_override.sql"
    ).read_text()
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}"')
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
    finally:
        conn.rollback()
        conn.close()
