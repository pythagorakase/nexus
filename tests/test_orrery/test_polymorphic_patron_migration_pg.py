"""Rollback-only PostgreSQL contract coverage for migration 096."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
import pytest

from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres


@pytest.fixture()
def polymorphic_patron_schema() -> Iterator[Any]:
    conn = psycopg2.connect(get_slot_db_url(slot=5))
    try:
        with conn.cursor() as cur:
            schema = f"migration_096_{uuid4().hex[:12]}"
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(
                """
                CREATE TABLE character_project_states (
                    id bigserial PRIMARY KEY,
                    character_entity_id bigint NOT NULL,
                    project_type text NOT NULL,
                    status text NOT NULL,
                    stage text NOT NULL,
                    target_place_id bigint,
                    target_character_entity_id bigint,
                    target_faction_entity_id bigint,
                    CONSTRAINT character_project_states_project_type_check
                        CHECK (true),
                    CONSTRAINT character_project_states_stage_by_type_check
                        CHECK (true),
                    CONSTRAINT character_project_states_target_by_type_check
                        CHECK (true),
                    CONSTRAINT character_project_states_completed_target_check
                        CHECK (true)
                )
                """
            )
            cur.execute(
                (
                    Path(__file__).parents[2] / "migrations/096_polymorphic_patron.sql"
                ).read_text()
            )
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_polymorphic_patron_constraints_accept_xor_and_reject_other_shapes(
    polymorphic_patron_schema: Any,
) -> None:
    """Character XOR faction is accepted for active and completed patrons."""

    with polymorphic_patron_schema.cursor() as cur:
        cur.execute(
            """
            INSERT INTO character_project_states (
                character_entity_id, project_type, status, stage,
                target_character_entity_id, target_faction_entity_id
            ) VALUES
                (1, 'court_patron', 'active', 'gaining_notice', 10, NULL),
                (2, 'court_patron', 'active', 'gaining_notice', NULL, 20),
                (3, 'court_patron', 'completed', 'securing_favor', 11, NULL),
                (4, 'court_patron', 'completed', 'securing_favor', NULL, 21)
            """
        )
        for actor_id, character_id, faction_id in (
            (5, None, None),
            (6, 12, 22),
        ):
            cur.execute("SAVEPOINT invalid_patron_shape")
            with pytest.raises(psycopg2.errors.CheckViolation):
                cur.execute(
                    """
                    INSERT INTO character_project_states (
                        character_entity_id, project_type, status, stage,
                        target_character_entity_id, target_faction_entity_id
                    ) VALUES (%s, 'court_patron', 'active', 'gaining_notice',
                              %s, %s)
                    """,
                    (actor_id, character_id, faction_id),
                )
            cur.execute("ROLLBACK TO SAVEPOINT invalid_patron_shape")
        cur.execute(
            """
            SELECT obj_description(oid)
            FROM pg_constraint
            WHERE conrelid = 'character_project_states'::regclass
              AND conname IN (
                  'character_project_states_target_by_type_check',
                  'character_project_states_completed_target_check'
              )
            ORDER BY conname
            """
        )
        comments = [row[0] for row in cur.fetchall()]
        assert len(comments) == 2
        assert all("character or faction" in comment for comment in comments)
        cur.execute(
            """
            SELECT a.attname, col_description(a.attrelid, a.attnum)
            FROM pg_attribute a
            WHERE a.attrelid = 'character_project_states'::regclass
              AND a.attname IN (
                  'target_character_entity_id',
                  'target_faction_entity_id'
              )
            ORDER BY a.attname
            """
        )
        column_comments = dict(cur.fetchall())
        assert (
            "target_faction_entity_id is NULL"
            in column_comments["target_character_entity_id"]
        )
        assert (
            "target_character_entity_id is NULL"
            in column_comments["target_faction_entity_id"]
        )
