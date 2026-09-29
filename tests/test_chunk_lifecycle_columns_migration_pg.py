"""Migration 134 drops the ChunkWorkflow lifecycle columns on real PostgreSQL.

Every database here is a disposable ``qa640_*`` clone of ``NEXUS_template``
made through ``tests/pg_fixtures.py``; the clone runs pending migrations, so
134 has already applied when the test body starts. The guard case removes the
clone's 134 stamp, restores the pre-134 columns, and reruns the real
``scripts/migrate.py`` runner. No save slot or template is written.
"""

from __future__ import annotations

import logging
from contextlib import closing
from typing import Any

import pytest

from scripts import migrate
from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres

LIFECYCLE_COLUMNS = ["finalized_at", "regeneration_count", "state"]


def _lifecycle_columns(dbname: str) -> list[str]:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'narrative_chunks'
              AND column_name = ANY(%s)
            ORDER BY column_name
            """,
            (LIFECYCLE_COLUMNS,),
        )
        return [str(row[0]) for row in cur.fetchall()]


def _is_stamped(dbname: str) -> bool:
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM schema_migrations WHERE version = '134'")
        return cur.fetchone() is not None


def _rewind_to_pre_134(cur: Any) -> None:
    """Restore the columns as migrations 018/021 left them and unstamp 134."""

    cur.execute("DELETE FROM schema_migrations WHERE version = '134'")
    cur.execute(
        """
        ALTER TABLE narrative_chunks
            ADD COLUMN state varchar(20) DEFAULT 'draft',
            ADD COLUMN finalized_at timestamptz,
            ADD COLUMN regeneration_count integer DEFAULT 0
        """
    )


def test_migration_134_drops_lifecycle_columns_and_refuses_dependent_views(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A clone ends without the columns; a hand-made view blocks the drop by name."""

    with disposable_slot_database("qa640_807_lifecycle_drop") as dbname:
        assert _lifecycle_columns(dbname) == []
        assert _is_stamped(dbname)

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            _rewind_to_pre_134(cur)
            cur.execute(
                "CREATE VIEW qa_hand_made_state_view AS "
                "SELECT id, state FROM narrative_chunks"
            )
            cur.execute(
                "CREATE MATERIALIZED VIEW qa_hand_made_regen_matview AS "
                "SELECT id, regeneration_count FROM narrative_chunks"
            )

        with caplog.at_level(logging.ERROR, logger="nexus.migrate"):
            assert migrate.migrate_database(dbname, skip_locked=False) == (0, 1)
        failure = caplog.text
        assert "FAILED: 134_drop_chunk_lifecycle_columns" in failure
        assert "public.qa_hand_made_state_view (state)" in failure
        assert "public.qa_hand_made_regen_matview (regeneration_count)" in failure
        assert _lifecycle_columns(dbname) == LIFECYCLE_COLUMNS
        assert not _is_stamped(dbname)

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DROP VIEW qa_hand_made_state_view")
            cur.execute("DROP MATERIALIZED VIEW qa_hand_made_regen_matview")

        assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)
        assert _lifecycle_columns(dbname) == []
        assert _is_stamped(dbname)
