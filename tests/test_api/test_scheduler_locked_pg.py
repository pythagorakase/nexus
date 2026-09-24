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
    """Lock polling is quiet and unlocking waits the configured observer hold."""
    settings = scheduler_settings()
    settings["runtime"]["scheduler"]["poll_interval_seconds"] = 1.0
    settings["runtime"]["scheduler"]["unlock_hold_seconds"] = 1.0
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
        wait_until(lambda: scheduler.state == "owner", timeout=3.0)
        assert monotonic() - started >= 1.0
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


def test_brief_unlock_does_not_admit_scheduler(offline_gate_db, caplog) -> None:
    """An observed unlock shorter than the hold never creates an ownership row."""
    settings = scheduler_settings()
    settings["runtime"]["scheduler"]["unlock_hold_seconds"] = 0.5
    scheduler = SlotScheduler(4, dbname=offline_gate_db, settings=settings)
    caplog.set_level(logging.INFO, logger="nexus.jobs.scheduler")
    set_locked(offline_gate_db, True)
    try:
        scheduler.start()
        assert scheduler.reason == "slot locked"
        set_locked(offline_gate_db, False)
        wait_until(lambda: scheduler._unlock_observed_at is not None)
        sleep(0.1)
        assert scheduler.state == "observer"
        set_locked(offline_gate_db, True)
        wait_until(lambda: scheduler._unlock_observed_at is None)
        sleep(0.6)
        assert scheduler.state == "observer"
        with closing(connect(offline_gate_db)) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM deferred_work_scheduler")
            assert cur.fetchone() == (0,)
        assert sum("slot lock cleared" in r.message for r in caplog.records) == 1
        # A second unlock starts a fresh hold and eventually admits ownership.
        set_locked(offline_gate_db, False)
        wait_until(lambda: scheduler._unlock_observed_at is not None)
        started = scheduler._unlock_observed_at
        wait_until(lambda: scheduler.state == "owner")
        assert monotonic() - started >= 0.5
    finally:
        scheduler.stop()
        set_locked(offline_gate_db, False)


def test_lock_hold_survives_database_error(offline_gate_db) -> None:
    """A real SQL failure between lock observations cannot erase lock memory."""
    import psycopg2

    settings = scheduler_settings()
    settings["runtime"]["scheduler"]["unlock_hold_seconds"] = 0.2
    scheduler = SlotScheduler(4, dbname=offline_gate_db, settings=settings)
    set_locked(offline_gate_db, True)
    try:
        assert not scheduler.acquire()
        try:
            with closing(scheduler.connect()) as conn, conn.cursor() as cur:
                cur.execute("SELECT 1 / 0")
        except psycopg2.errors.DivisionByZero as exc:
            scheduler._recover(exc)
        assert scheduler.state == "recovering"
        set_locked(offline_gate_db, False)
        assert not scheduler.acquire()
        assert scheduler.state == "observer"
        assert scheduler.reason == "slot locked"
        sleep(0.25)
        assert scheduler.acquire()
    finally:
        set_locked(offline_gate_db, False)
        scheduler.release()
