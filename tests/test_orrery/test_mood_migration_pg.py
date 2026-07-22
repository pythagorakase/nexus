"""Rollback-only PostgreSQL contract for migration 095."""

from pathlib import Path
import uuid

import psycopg2
import pytest

from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


def test_mood_vocabulary_contract() -> None:
    conn = psycopg2.connect(get_slot_db_url(slot=5))
    schema = f"mood_migration_{uuid.uuid4().hex}"
    migration = (
        Path(__file__).parents[2] / "migrations" / "095_mood_vocabulary.sql"
    ).read_text()
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(
                """
                CREATE TABLE tag_category_registry (
                    category text NOT NULL,
                    entity_kind entity_kind NOT NULL,
                    prompt_order integer NOT NULL,
                    description text,
                    deprecated boolean NOT NULL DEFAULT false,
                    replacement_categories text[],
                    PRIMARY KEY (category, entity_kind)
                );
                CREATE TABLE tags (
                    id bigserial PRIMARY KEY,
                    tag text UNIQUE NOT NULL,
                    category text NOT NULL,
                    is_ephemeral boolean NOT NULL DEFAULT false,
                    clearance_kind entity_tag_clearance_kind,
                    reapplication_policy entity_tag_reapplication_policy,
                    clear_on jsonb,
                    synonym_for bigint,
                    deprecated boolean NOT NULL DEFAULT false,
                    description text,
                    CHECK (is_ephemeral = (clearance_kind IS NOT NULL))
                );
                """
            )
            cur.execute(migration)
            cur.execute(migration)
            cur.execute(
                """
                SELECT entity_kind::text, description
                FROM tag_category_registry
                WHERE category = 'mood'
                """
            )
            kind, description = cur.fetchone()
            assert kind == "character"
            assert "mechanical" in description.lower()
            assert "emotional_state" in description
            cur.execute(
                """
                SELECT tag, is_ephemeral, clearance_kind::text,
                       reapplication_policy::text, description
                FROM tags
                WHERE category = 'mood'
                ORDER BY tag
                """
            )
            rows = cur.fetchall()
            assert [row[0] for row in rows] == [
                "elated",
                "grim",
                "restless",
                "sour",
            ]
            assert all(row[1:4] == (True, "time", "replace") for row in rows)
            assert all(row[4] and "\n" not in row[4] for row in rows)
    finally:
        conn.rollback()
        conn.close()
