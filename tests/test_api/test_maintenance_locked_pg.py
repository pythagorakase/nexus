"""Maintenance CLI writes use isolated sessions on real locked disposable slots.

The template supplies schema_migrations, narrative_chunks, lore_pass_baselines,
incubator, story settings, and scheduler tables. Fixture cleanup drops the clone.
"""

from contextlib import closing
import subprocess
import sys

import pytest

from nexus.config import load_settings_as_dict
from nexus.config.story_model import read_story_settings, story_context_settings
from nexus.memory.manager import pass2_baseline_config_fingerprint
from scripts.migrate import is_db_locked
from tests.pg_fixtures import connect
from tests.test_api.test_scheduler_locked_pg import set_locked

pytestmark = pytest.mark.requires_postgres


def run_script(script: str, dbname: str, *args: str) -> subprocess.CompletedProcess:
    """Run the real maintenance CLI against only the disposable database."""
    result = subprocess.run(
        [sys.executable, f"scripts/{script}.py", "--dbname", dbname, *args],
        capture_output=True,
        text=True,
    )
    print(result.stdout + result.stderr)
    return result


def assert_still_locked(dbname: str, observer) -> None:
    """Verify persistent policy and that an existing backend survives maintenance."""
    assert is_db_locked(dbname)
    with observer.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SHOW default_transaction_read_only")
        assert cur.fetchone() == ("on",)


def test_migrate_locked_cli(offline_gate_db: str) -> None:
    """Reapply the real scheduler migration while preserving the database lock."""
    dbname = offline_gate_db
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "DROP TABLE correspondence_compaction_jobs, deferred_work_scheduler"
        )
        cur.execute(
            "ALTER TABLE orrery_maturation_jobs DROP COLUMN locked_by, "
            "DROP COLUMN lease_nonce"
        )
        cur.execute("DELETE FROM schema_migrations WHERE version = '120'")
    set_locked(dbname, True)
    try:
        with closing(connect(dbname)) as observer:
            refused = run_script("migrate", dbname)
            assert refused.returncode != 0
            assert "read-only" in refused.stderr
            with observer.cursor() as cur:
                cur.execute("SELECT 1 FROM schema_migrations WHERE version = '120'")
                assert cur.fetchone() is None
            result = run_script("migrate", dbname, "--write-locked-slot")
            assert result.returncode == 0, result.stderr
            assert f"{dbname}: session write override for migrate" in result.stderr
            assert "Applied: 120_deferred_work_owner" in result.stderr
            assert_still_locked(dbname, observer)
            with observer.cursor() as cur:
                cur.execute("SELECT 1 FROM schema_migrations WHERE version = '120'")
                assert cur.fetchone() == (1,)
                cur.execute("SELECT count(*) FROM deferred_work_scheduler")
                assert cur.fetchone() == (0,)
    finally:
        set_locked(dbname, False)


def test_stamp_and_refresh_locked_cli(offline_gate_db: str) -> None:
    """Both modes refuse normally and write with an explicitly logged override."""
    dbname = offline_gate_db
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
            "VALUES ('Maintenance tail', 'Maintenance tail') RETURNING id"
        )
        tail = cur.fetchone()[0]
    set_locked(dbname, True)
    try:
        with closing(connect(dbname)) as observer:
            for mode, operation in (
                ([], "stamp Pass-2 baseline"),
                (["--refresh-fingerprint"], "refresh Pass-2 fingerprint"),
            ):
                refused = run_script("stamp_lore_pass_baseline", dbname, *mode)
                assert refused.returncode != 0
                assert "read-only transaction" in refused.stderr
                result = run_script(
                    "stamp_lore_pass_baseline", dbname, *mode, "--write-locked-slot"
                )
                assert result.returncode == 0, result.stderr
                assert (
                    f"{dbname}: session write override for {operation}" in result.stderr
                )
                assert_still_locked(dbname, observer)
                # Change the stored fingerprint only through an authorized session
                # so refresh proves a persisted change, not a no-op update.
                if not mode:
                    from nexus.database import maintenance_connection

                    with (
                        closing(
                            maintenance_connection(
                                dbname,
                                write_locked_slot=True,
                                operation="seed stale fingerprint",
                            )
                        ) as conn,
                        conn,
                        conn.cursor() as cur,
                    ):
                        cur.execute(
                            "UPDATE lore_pass_baselines SET payload = "
                            "jsonb_set(payload, '{config_fingerprint}', '\"0000000000000000000000000000000000000000000000000000000000000000\"') "
                            "WHERE chunk_id = %s",
                            (tail,),
                        )
            expected = pass2_baseline_config_fingerprint(
                story_context_settings(
                    load_settings_as_dict(), read_story_settings(dbname)
                )
            )
            with observer.cursor() as cur:
                cur.execute(
                    "SELECT payload->>'config_fingerprint' FROM lore_pass_baselines "
                    "WHERE chunk_id = %s",
                    (tail,),
                )
                assert cur.fetchone() == (expected,)
    finally:
        set_locked(dbname, False)
