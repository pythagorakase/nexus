"""Locked disposable slots remain observable without acquiring or writing leases."""

from contextlib import closing
import logging
from time import monotonic, sleep

import pytest
from psycopg2 import sql

from nexus.agents.orrery import worker
from nexus.jobs.scheduler import SlotScheduler
from tests.pg_fixtures import connect
from tests.test_api.test_scheduler_pg import scheduler_settings, wait_until

pytestmark = pytest.mark.requires_postgres


def set_locked(dbname: str, locked: bool) -> None:
    """Use the same database setting as the operator's slot lock."""
    assert dbname.startswith("qa640_")
    with closing(connect("postgres")) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "ALTER DATABASE {} SET default_transaction_read_only = {}"
                ).format(sql.Identifier(dbname), sql.SQL("on" if locked else "off"))
            )


def test_locked_scheduler_observes_then_acquires(
    offline_gate_db, caplog, monkeypatch, capsys
) -> None:
    """Lock polling is quiet and unlocking does not use fault backoff."""
    settings = scheduler_settings()
    settings["runtime"]["scheduler"]["poll_interval_seconds"] = 1.0
    scheduler = SlotScheduler(4, dbname=offline_gate_db, settings=settings)
    caplog.set_level(logging.INFO, logger="nexus.jobs.scheduler")
    set_locked(offline_gate_db, True)
    try:
        scheduler.start()
        sleep(2.3)  # Observe more than one poll, including transition-only logging.
        assert scheduler.state == "observer"
        assert scheduler.reason == "slot locked"
        assert scheduler.last_error is None
        with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM deferred_work_scheduler")
            assert cur.fetchone()[0] == 0
        assert sum("slot locked" in r.message for r in caplog.records) == 1
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from nexus.api.runtime_status import register_runtime_status
        from nexus.cli import _print_jobs

        monkeypatch.setenv("NEXUS_SLOT", "4")
        app = FastAPI()
        app.state.scheduler = scheduler
        register_runtime_status(app)
        with TestClient(app) as client:
            jobs = client.get("/runtime/status").json()["jobs"]
        assert jobs["scheduler"]["state"] == "observer"
        assert jobs["scheduler"]["reason"] == "slot locked"
        assert jobs["scheduler"]["last_error"] is None
        _print_jobs(jobs)
        lines = capsys.readouterr().out.splitlines()
        scheduler_lines = [line for line in lines if line.startswith("scheduler:")]
        assert len(scheduler_lines) == 1
        assert "state=observer" in scheduler_lines[0]
        assert "reason=slot locked" in scheduler_lines[0]
        assert "error=" not in scheduler_lines[0]
        # Leave headroom for SQL execution within the next poll interval.
        sleep(0.3)
        started = monotonic()
        set_locked(offline_gate_db, False)
        wait_until(lambda: scheduler.state == "owner", timeout=1.0)
        assert monotonic() - started < 1.0
        assert scheduler.reason is None
        assert scheduler.last_error is None
        assert sum("slot lock cleared" in r.message for r in caplog.records) == 1
    finally:
        scheduler.stop()
        set_locked(offline_gate_db, False)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_locked_operator_exits_without_lease(offline_gate_db, capsys) -> None:
    """The real worker parser and pass reject the lock before lease SQL."""
    set_locked(offline_gate_db, True)
    try:
        assert worker.main(["--slot", "4"]) == 1
        assert "slot locked" in capsys.readouterr().out
        with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM deferred_work_scheduler")
            assert cur.fetchone()[0] == 0
    finally:
        set_locked(offline_gate_db, False)


def test_read_only_pass_becomes_observer(offline_gate_db, caplog) -> None:
    """A database-enforced read-only failure uses the same observer transition."""
    scheduler = SlotScheduler(4, dbname=offline_gate_db, settings=scheduler_settings())
    scheduler.start()
    try:
        wait_until(lambda: scheduler.state == "owner")
        set_locked(offline_gate_db, True)
        wait_until(lambda: scheduler.reason == "slot locked")
        assert scheduler.state == "observer"
        assert scheduler.last_error is None
        scheduler.stop()
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    finally:
        scheduler.stop()
        set_locked(offline_gate_db, False)
        scheduler.release()
