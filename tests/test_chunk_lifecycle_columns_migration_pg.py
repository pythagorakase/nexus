"""Migration 134 drops the ChunkWorkflow lifecycle columns on real PostgreSQL.

Every database here is a disposable ``qa640_*`` clone of ``NEXUS_template``
made through ``tests/pg_fixtures.py``; the clone runs pending migrations, so
134 has already applied when the test body starts. Each case removes the
clone's 134 stamp, restores the pre-134 columns, and reruns the real
``scripts/migrate.py`` runner. No save slot or template is written.
"""

from __future__ import annotations

import logging
import re
from contextlib import closing
from typing import Any

import psycopg2
import pytest

from scripts import migrate
from tests.pg_fixtures import connect, disposable_slot_database

pytestmark = pytest.mark.requires_postgres

LIFECYCLE_COLUMNS = ["finalized_at", "regeneration_count", "state"]

# A BEFORE INSERT trigger whose function writes a lifecycle column. PostgreSQL
# records no dependency for a column named in a function body, so only the
# function scan in migration 134 can see this one.
STATE_WRITER_DDL = (
    """
    CREATE FUNCTION qa_default_chunk_state() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        NEW.state := 'draft';
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER qa_default_chunk_state
    BEFORE INSERT ON narrative_chunks
    FOR EACH ROW EXECUTE FUNCTION qa_default_chunk_state()
    """,
)

# Near misses the scan must not refuse: a job table's own state column, set
# through NEW in that table's trigger and by a narrative_chunks trigger in a
# statement that does not name narrative_chunks; and longer identifiers that
# contain a lifecycle column name, in a statement that names narrative_chunks.
DECOY_DDL = (
    "CREATE TABLE qa_decoy_jobs (chunk_id bigint NOT NULL, state text)",
    """
    CREATE FUNCTION qa_decoy_job_default_state() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        NEW.state := 'queued';
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER qa_decoy_job_default_state
    BEFORE INSERT ON qa_decoy_jobs
    FOR EACH ROW EXECUTE FUNCTION qa_decoy_job_default_state()
    """,
    """
    CREATE FUNCTION qa_decoy_enqueue_chunk_job() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        INSERT INTO qa_decoy_jobs (chunk_id, state) VALUES (NEW.id, 'new');
        RETURN NULL;
    END
    $$
    """,
    """
    CREATE TRIGGER qa_decoy_enqueue_chunk_job
    AFTER INSERT ON narrative_chunks
    FOR EACH ROW EXECUTE FUNCTION qa_decoy_enqueue_chunk_job()
    """,
    """
    CREATE FUNCTION qa_decoy_longer_names() RETURNS void
    LANGUAGE plpgsql AS $$
    BEGIN
        PERFORM chunk_state, state_updates, finalized_at_utc,
                regeneration_count_total
        FROM narrative_chunks;
    END
    $$
    """,
)


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


def _insert_chunk(cur: Any) -> int:
    cur.execute(
        "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
        "VALUES ('Lifecycle probe.', 'Lifecycle probe.') RETURNING id"
    )
    return int(cur.fetchone()[0])


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


def test_migration_134_refuses_a_trigger_function_that_writes_a_lifecycle_column(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A BEFORE INSERT trigger that assigns NEW.state blocks the drop by name.

    The decoys stay in place for the whole case, so the run that finally
    applies 134 also proves the scan does not refuse them.
    """

    with disposable_slot_database("qa640_807_lifecycle_trigger") as dbname:
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            _rewind_to_pre_134(cur)
            for ddl in (*STATE_WRITER_DDL, *DECOY_DDL):
                cur.execute(ddl)

        # Without the guard the drop succeeds, and the next insert fails
        # inside the trigger. Rolled back.
        with closing(connect(dbname)) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE narrative_chunks DROP COLUMN state, "
                    "DROP COLUMN finalized_at, DROP COLUMN regeneration_count"
                )
                with pytest.raises(
                    psycopg2.errors.UndefinedColumn,
                    match='record "new" has no field "state"',
                ):
                    _insert_chunk(cur)
            conn.rollback()
        assert _lifecycle_columns(dbname) == LIFECYCLE_COLUMNS

        with caplog.at_level(logging.ERROR, logger="nexus.migrate"):
            assert migrate.migrate_database(dbname, skip_locked=False) == (0, 1)
        failure = caplog.text
        assert "FAILED: 134_drop_chunk_lifecycle_columns" in failure
        named = re.search(r"functions reference them: (.+)", failure)
        assert named is not None, failure
        assert named.group(1) == "public.qa_default_chunk_state() (state)"
        assert _lifecycle_columns(dbname) == LIFECYCLE_COLUMNS
        assert not _is_stamped(dbname)

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DROP TRIGGER qa_default_chunk_state ON narrative_chunks")
            cur.execute("DROP FUNCTION qa_default_chunk_state()")

        assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)
        assert _lifecycle_columns(dbname) == []
        assert _is_stamped(dbname)

        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            chunk_id = _insert_chunk(cur)
            # Both decoy triggers fired: the chunk trigger queued a job row,
            # and the job table's trigger set that row's own state.
            cur.execute(
                "SELECT state FROM qa_decoy_jobs WHERE chunk_id = %s", (chunk_id,)
            )
            assert cur.fetchall() == [("queued",)]


def test_migration_134_passes_the_template_trigger_functions() -> None:
    """The template's own narrative_chunks trigger functions pass the scan.

    Migration 114's IDF trigger functions fire on narrative_chunks, and the
    function they call (sync_memory_idf_document, as migration 133 rewrote it)
    reads narrative_chunks, so the scan has real narrative_chunks triggers and
    statements to read on a plain template clone.
    """

    with disposable_slot_database("qa640_807_lifecycle_template") as dbname:
        assert _is_stamped(dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT p.proname
                FROM pg_trigger AS t
                JOIN pg_proc AS p ON p.oid = t.tgfoid
                WHERE t.tgrelid = 'public.narrative_chunks'::regclass
                  AND NOT t.tgisinternal
                """
            )
            trigger_functions = {str(row[0]) for row in cur.fetchall()}
            cur.execute(
                """
                SELECT p.prosrc
                FROM pg_proc AS p
                JOIN pg_namespace AS n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'
                  AND p.proname = 'sync_memory_idf_document'
                """
            )
            idf_bodies = [str(row[0]) for row in cur.fetchall()]
            _rewind_to_pre_134(cur)

        assert {"lock_memory_idf_corpora", "maintain_memory_idf"} <= trigger_functions
        assert len(idf_bodies) == 1
        assert re.search(r"\bnarrative_chunks\b", idf_bodies[0])

        assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)
        assert _lifecycle_columns(dbname) == []
        assert _is_stamped(dbname)
