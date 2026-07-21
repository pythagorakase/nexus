"""Real-PostgreSQL contract coverage for migration 091."""

from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres
MIGRATION_SQL = Path("migrations/091_backstory_secrets.sql").read_text()


@pytest.fixture()
def migration_090_schema() -> Iterator[Any]:
    """Build the exact migration dependencies in a rolled-back schema."""

    conn = psycopg2.connect(get_slot_db_url(slot=2), cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            schema = f"migration_091_{uuid4().hex[:12]}"
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(
                """
                CREATE TABLE entities (id bigserial PRIMARY KEY);
                CREATE TABLE narrative_chunks (id bigserial PRIMARY KEY);
                CREATE TABLE claims (
                    id bigserial PRIMARY KEY,
                    scope text NOT NULL CHECK (
                        scope IN ('common', 'bounded', 'private')
                    )
                );
                CREATE TABLE event_types (
                    type text PRIMARY KEY,
                    category text NOT NULL,
                    severity text,
                    description text
                );
                INSERT INTO entities DEFAULT VALUES;
                INSERT INTO narrative_chunks DEFAULT VALUES;
                INSERT INTO claims (scope) VALUES ('private'), ('private');
                """
            )
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_migration_091_installs_secret_contract_and_comments(
    migration_090_schema: Any,
) -> None:
    with migration_090_schema.cursor() as cur:
        cur.execute(MIGRATION_SQL)
        cur.execute(
            """
            SELECT column_name, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'backstory_secrets'
            ORDER BY ordinal_position
            """
        )
        columns = {row["column_name"]: row for row in cur.fetchall()}
        assert list(columns) == [
            "id",
            "claim_id",
            "gate_template_id",
            "status",
            "holder_entity_id",
            "source_chunk_id",
            "revealed_at_world_time",
            "revealed_by_chunk_id",
            "created_at",
        ]
        assert columns["claim_id"]["is_nullable"] == "NO"
        assert columns["status"]["column_default"] == "'latent'::text"
        cur.execute(
            """
            SELECT obj_description('backstory_secrets'::regclass) AS comment,
                   col_description(
                       'backstory_secrets'::regclass,
                       (
                           SELECT ordinal_position
                           FROM information_schema.columns
                           WHERE table_schema = current_schema()
                             AND table_name = 'backstory_secrets'
                             AND column_name = 'gate_template_id'
                       )
                   ) AS gate_comment
            """
        )
        comments = cur.fetchone()
        assert "latent -> gate fires at commit -> revealed" in comments["comment"]
        assert "never a serialized predicate" in comments["gate_comment"]


def test_migration_091_enforces_checks_uniqueness_and_foreign_keys(
    migration_090_schema: Any,
) -> None:
    with migration_090_schema.cursor() as cur:
        cur.execute(MIGRATION_SQL)
        cur.execute(
            """
            INSERT INTO backstory_secrets (
                claim_id, gate_template_id, holder_entity_id, source_chunk_id
            ) VALUES (1, 'holder_death', 1, 1)
            RETURNING status
            """
        )
        assert cur.fetchone()["status"] == "latent"

        cur.execute("SAVEPOINT invalid_status")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO backstory_secrets (
                    claim_id, gate_template_id, status, holder_entity_id
                ) VALUES (2, 'holder_death', 'forgotten', 1)
                """
            )
        cur.execute("ROLLBACK TO SAVEPOINT invalid_status")

        cur.execute("SAVEPOINT duplicate_claim")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                """
                INSERT INTO backstory_secrets (
                    claim_id, gate_template_id, holder_entity_id
                ) VALUES (1, 'trust_earned', 1)
                """
            )
        cur.execute("ROLLBACK TO SAVEPOINT duplicate_claim")


def test_migration_091_seeds_both_revelation_events(
    migration_090_schema: Any,
) -> None:
    with migration_090_schema.cursor() as cur:
        cur.execute(MIGRATION_SQL)
        cur.execute(
            """
            SELECT type, category, severity
            FROM event_types
            WHERE type IN (
                'backstory_secret_authored', 'backstory_revealed'
            )
            ORDER BY type
            """
        )
        assert cur.fetchall() == [
            {
                "type": "backstory_revealed",
                "category": "revelation",
                "severity": "moderate",
            },
            {
                "type": "backstory_secret_authored",
                "category": "revelation",
                "severity": "minor",
            },
        ]
