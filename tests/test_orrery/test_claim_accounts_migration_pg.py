"""Real-PostgreSQL contract coverage for migration 090."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from nexus.agents.orrery.epistemics import (
    mint_account_variant_sync,
    mint_claim_for_event,
)
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres
MIGRATION_SQL = Path("migrations/090_claim_accounts.sql").read_text()
EPISTEMICS = {
    "enabled": True,
    "claim_event_types": ["threat_issued"],
    "aware_roles": [],
}


@pytest.fixture()
def migration_089_schema() -> Iterator[Any]:
    """Build the exact pre-090 claim contract in a rolled-back schema."""

    conn = psycopg2.connect(get_slot_db_url(slot=2), cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            schema = f"migration_090_{uuid4().hex[:12]}"
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(
                """
                CREATE TABLE world_events (id bigserial PRIMARY KEY);
                CREATE TABLE narrative_chunks (id bigserial PRIMARY KEY);
                CREATE TABLE orrery_resolutions (id bigserial PRIMARY KEY);
                CREATE TABLE claims (
                    id bigserial PRIMARY KEY,
                    world_event_id bigint NOT NULL REFERENCES world_events(id),
                    summary text NOT NULL,
                    scope text NOT NULL CHECK (
                        scope IN ('common', 'bounded', 'private')
                    ),
                    source_chunk_id bigint REFERENCES narrative_chunks(id),
                    source_resolution_id bigint
                        REFERENCES orrery_resolutions(id),
                    created_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE UNIQUE INDEX ux_claims_world_event_v1
                    ON claims (world_event_id)
                    WHERE world_event_id IS NOT NULL;
                INSERT INTO world_events DEFAULT VALUES;
                INSERT INTO claims (world_event_id, summary, scope)
                VALUES (1, 'Legacy canonical account.', 'bounded');
                """
            )
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_migration_090_swaps_index_and_preserves_existing_rows(
    migration_089_schema: Any,
) -> None:
    """Existing claims become canonical and the account contract is documented."""

    with migration_089_schema.cursor() as cur:
        cur.execute(MIGRATION_SQL)
        cur.execute(
            """
            SELECT account_label, account_payload, distorted_from_claim_id
            FROM claims WHERE id = 1
            """
        )
        assert cur.fetchone() == {
            "account_label": "canonical",
            "account_payload": None,
            "distorted_from_claim_id": None,
        }
        cur.execute(
            """
            SELECT column_default, is_nullable
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'claims'
              AND column_name = 'account_label'
            """
        )
        assert cur.fetchone() == {
            "column_default": "'canonical'::text",
            "is_nullable": "NO",
        }
        cur.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'claims'
              AND indexname LIKE 'ux_claims_world_event%'
            """
        )
        indexes = cur.fetchall()
        assert [row["indexname"] for row in indexes] == [
            "ux_claims_world_event_account_v1"
        ]
        assert "UNIQUE INDEX" in indexes[0]["indexdef"]
        assert "(world_event_id, account_label)" in indexes[0]["indexdef"]
        assert "WHERE (world_event_id IS NOT NULL)" in indexes[0]["indexdef"]


def test_migration_090_mints_canonical_idempotently_and_variants_loudly(
    migration_089_schema: Any,
) -> None:
    """Canonical recovery is unchanged while sibling collisions reach PostgreSQL."""

    with migration_089_schema.cursor() as cur:
        cur.execute(MIGRATION_SQL)
        first = mint_claim_for_event(
            cur,
            world_event_id=1,
            event_type="threat_issued",
            summary="A replacement summary must not overwrite legacy prose.",
            participants=(),
            source_chunk_id=None,
            source_resolution_id=None,
            settings=EPISTEMICS,
        )
        second = mint_claim_for_event(
            cur,
            world_event_id=1,
            event_type="threat_issued",
            summary="Still idempotent.",
            participants=(),
            source_chunk_id=None,
            source_resolution_id=None,
            settings=EPISTEMICS,
        )
        assert first is not None
        assert second is not None
        assert first.claim_id == second.claim_id == 1

        variant_id = mint_account_variant_sync(
            cur,
            source_claim_id=first.claim_id,
            account_label="alibi",
            summary="The witness insists the accused was elsewhere.",
            account_payload={"truth_marker": False, "place": "harbor"},
            source_chunk_id=None,
        )
        cur.execute(
            """
            SELECT world_event_id, account_label, account_payload, scope,
                   distorted_from_claim_id
            FROM claims WHERE id = %s
            """,
            (variant_id,),
        )
        assert cur.fetchone() == {
            "world_event_id": 1,
            "account_label": "alibi",
            "account_payload": {"truth_marker": False, "place": "harbor"},
            "scope": "bounded",
            "distorted_from_claim_id": 1,
        }

        cur.execute("SAVEPOINT duplicate_label")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            mint_account_variant_sync(
                cur,
                source_claim_id=first.claim_id,
                account_label="alibi",
                summary="A caller bug must not be hidden.",
                source_chunk_id=None,
            )
        cur.execute("ROLLBACK TO SAVEPOINT duplicate_label")

        with pytest.raises(ValueError, match="Source claim 999999 does not exist"):
            mint_account_variant_sync(
                cur,
                source_claim_id=999999,
                account_label="missing-source",
                summary="This cannot be anchored.",
                source_chunk_id=None,
            )


def test_migration_090_rejects_self_ancestor(
    migration_089_schema: Any,
) -> None:
    """The lineage hook cannot point at the row being inserted."""

    with migration_089_schema.cursor() as cur:
        cur.execute(MIGRATION_SQL)
        cur.execute("SAVEPOINT self_ancestor")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO claims (
                    id, world_event_id, account_label, summary, scope,
                    distorted_from_claim_id
                ) VALUES (90090, 1, 'self-ancestor', 'Impossible.',
                          'bounded', 90090)
                """
            )
        cur.execute("ROLLBACK TO SAVEPOINT self_ancestor")
