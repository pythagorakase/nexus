"""Real-PostgreSQL contract coverage for migration 092."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from nexus.agents.orrery.epistemics import mint_account_variant_sync
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres
MIGRATION_SQL = Path("migrations/092_claim_distortion_depth.sql").read_text()


@pytest.fixture()
def migration_091_schema() -> Iterator[Any]:
    """Build a rolled-back schema with the exact claims shape before 092."""

    conn = psycopg2.connect(get_slot_db_url(slot=2), cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            schema = f"migration_092_{uuid4().hex[:12]}"
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(
                """
                CREATE TABLE world_events (id bigserial PRIMARY KEY);
                CREATE TABLE narrative_chunks (id bigserial PRIMARY KEY);
                CREATE TABLE orrery_resolutions (id bigserial PRIMARY KEY);
                CREATE TABLE claims (
                    id bigserial PRIMARY KEY,
                    world_event_id bigint NOT NULL
                        REFERENCES world_events(id),
                    summary text NOT NULL,
                    scope text NOT NULL CHECK (
                        scope IN ('common', 'bounded', 'private')
                    ),
                    source_chunk_id bigint REFERENCES narrative_chunks(id),
                    source_resolution_id bigint
                        REFERENCES orrery_resolutions(id),
                    created_at timestamptz NOT NULL DEFAULT now(),
                    account_label text NOT NULL DEFAULT 'canonical',
                    account_payload jsonb,
                    distorted_from_claim_id bigint REFERENCES claims(id),
                    CHECK (distorted_from_claim_id <> id)
                );
                CREATE UNIQUE INDEX ux_claims_world_event_account_v1
                    ON claims (world_event_id, account_label)
                    WHERE world_event_id IS NOT NULL;
                INSERT INTO world_events DEFAULT VALUES;
                INSERT INTO claims (world_event_id, summary, scope)
                VALUES (1, 'Canonical account.', 'bounded');
                """
            )
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_migration_092_adds_nullable_positive_documented_depth(
    migration_091_schema: Any,
) -> None:
    """Existing accounts stay manual-only and invalid thresholds fail loudly."""

    with migration_091_schema.cursor() as cur:
        cur.execute(MIGRATION_SQL)
        cur.execute(
            """
            SELECT distortion_min_depth
            FROM claims
            WHERE id = 1
            """
        )
        assert cur.fetchone() == {"distortion_min_depth": None}
        cur.execute(
            """
            SELECT is_nullable, data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'claims'
              AND column_name = 'distortion_min_depth'
            """
        )
        assert cur.fetchone() == {
            "is_nullable": "YES",
            "data_type": "integer",
        }
        cur.execute(
            """
            SELECT pg_get_constraintdef(oid) AS definition,
                   obj_description(oid, 'pg_constraint') AS comment
            FROM pg_constraint
            WHERE conrelid = 'claims'::regclass
              AND conname = 'claims_distortion_min_depth_check'
            """
        )
        constraint = cur.fetchone()
        assert constraint["definition"] == "CHECK ((distortion_min_depth >= 1))"
        assert "begin at hop depth 1" in constraint["comment"]
        cur.execute(
            """
            SELECT col_description(
                'claims'::regclass,
                attnum
            ) AS comment
            FROM pg_attribute
            WHERE attrelid = 'claims'::regclass
              AND attname = 'distortion_min_depth'
            """
        )
        comment = cur.fetchone()["comment"]
        assert "never auto-selected" in comment
        assert "largest distortion_min_depth wins" in comment
        assert "lowest claim id" in comment
        cur.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'claims'
              AND indexdef ILIKE '%distortion_min_depth%'
            """
        )
        assert cur.fetchall() == []

        first_variant = mint_account_variant_sync(
            cur,
            source_claim_id=1,
            account_label="first-depth-two",
            summary="First depth-two account.",
            source_chunk_id=None,
            distortion_min_depth=2,
        )
        second_variant = mint_account_variant_sync(
            cur,
            source_claim_id=1,
            account_label="second-depth-two",
            summary="Second depth-two account.",
            source_chunk_id=None,
            distortion_min_depth=2,
        )
        cur.execute(
            """
            SELECT id, distortion_min_depth
            FROM claims
            WHERE id = ANY(%s)
            ORDER BY id
            """,
            ([first_variant, second_variant],),
        )
        assert cur.fetchall() == [
            {"id": first_variant, "distortion_min_depth": 2},
            {"id": second_variant, "distortion_min_depth": 2},
        ]

        cur.execute("SAVEPOINT invalid_depth")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                UPDATE claims
                SET distortion_min_depth = 0
                WHERE id = %s
                """,
                (first_variant,),
            )
        cur.execute("ROLLBACK TO SAVEPOINT invalid_depth")


def test_migration_092_rejects_canonical_account_with_depth(
    migration_091_schema: Any,
) -> None:
    """A direct update cannot turn the canonical account into a variant."""

    with migration_091_schema.cursor() as cur:
        cur.execute(MIGRATION_SQL)
        cur.execute("SAVEPOINT canonical_depth")
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                UPDATE claims
                SET distortion_min_depth = 1
                WHERE id = 1
                """
            )
        cur.execute("ROLLBACK TO SAVEPOINT canonical_depth")


@pytest.mark.parametrize("invalid_depth", [0, -1, True, 1.5])
def test_variant_mint_rejects_invalid_distortion_depth_before_sql(
    migration_091_schema: Any,
    invalid_depth: Any,
) -> None:
    """Both type and lower-bound validation precede the INSERT."""

    with migration_091_schema.cursor() as cur:
        cur.execute(MIGRATION_SQL)
        with pytest.raises(
            ValueError,
            match="distortion_min_depth must be an integer >= 1",
        ):
            mint_account_variant_sync(
                cur,
                source_claim_id=1,
                account_label=f"invalid-{invalid_depth!r}",
                summary="This variant must not be inserted.",
                source_chunk_id=None,
                distortion_min_depth=invalid_depth,
            )
