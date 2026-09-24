"""Real backend-termination proofs; only qa640 databases and lane 8017 are used."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import pytest
from sqlalchemy import text

from nexus.api import db_pool, slot_utils
from nexus.api.retry_handler import retry_with_backoff
from nexus.database import AmbiguousCommit, connection_kwargs, create_slot_engine

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[str]:
    """Create an empty disposable database; no save or template is changed."""
    monkeypatch.setenv("NEXUS_GATEWAY_PORT", "8017")
    config = tmp_path / "nexus.toml"
    config.write_text(Path("nexus.toml").read_text())
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(config))
    name = f"qa640_804_{uuid4().hex[:12]}"
    monkeypatch.setattr(slot_utils, "VALID_DBNAMES", {*slot_utils.VALID_DBNAMES, name})
    admin = psycopg2.connect(**connection_kwargs("postgres"))
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(name)
                )
            )
        with db_pool.get_connection(name) as conn, conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE writes (id serial PRIMARY KEY, value text UNIQUE)"
            )
            cur.execute(
                "COMMENT ON TABLE writes IS 'Disposable connection proof writes'"
            )
            cur.execute(
                "COMMENT ON COLUMN writes.id IS 'Nontransactional sequence witnesses replay'"
            )
            cur.execute("COMMENT ON COLUMN writes.value IS 'Proof value'")
        yield name
    finally:
        db_pool.dispose_database(name)
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name))
            )
        admin.close()


def terminate(conn: Any) -> int:
    """Terminate exactly the caller's backend, guarded by database and lane label."""
    pid = conn.get_backend_pid()
    dbname = conn.info.dbname
    app = conn.info.parameter_status("application_name")
    assert dbname.startswith("qa640_")
    assert app.endswith(":8017"), app
    admin = psycopg2.connect(**connection_kwargs("postgres"))
    try:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE pid = %s AND datname = %s AND application_name = %s",
                (pid, dbname, app),
            )
            assert cur.fetchall() == [(True,)]
    finally:
        admin.close()
    print(f"terminated database={dbname} pid={pid} application_name={app}")
    return pid


def test_checkout_replaces_terminated_backend_once(database: str, caplog: Any) -> None:
    with db_pool.get_connection(database) as conn:
        original = conn
    old_pid = terminate(original)
    with caplog.at_level(logging.INFO, logger="nexus.api.db_pool"):
        with db_pool.get_connection(database) as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_backend_pid(), 1")
            pid, value = cur.fetchone()
            assert pid != old_pid and value == 1
    replacements = [
        r.message for r in caplog.records if "Replacing connection" in r.message
    ]
    assert len(replacements) == 1
    print(f"replacement_count={len(replacements)} new_pid={pid}")


def test_body_connection_error_discards(database: str) -> None:
    with pytest.raises(psycopg2.OperationalError):
        with db_pool.get_connection(database) as conn:
            old_pid = terminate(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    assert conn.closed
    with db_pool.get_connection(database) as fresh:
        assert fresh.get_backend_pid() != old_pid
        print(f"body_failure_discarded=True new_pid={fresh.get_backend_pid()}")


def test_ambiguous_commit_is_never_replayed(database: str) -> None:
    attempts = []

    @retry_with_backoff()
    def mutation() -> None:
        attempts.append(1)
        with db_pool.get_connection(database) as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO writes(value) VALUES ('once')")
            terminate(conn)

    with pytest.raises(AmbiguousCommit, match=database) as caught:
        mutation()
    assert isinstance(caught.value.__cause__, psycopg2.OperationalError)
    assert len(attempts) == 1
    with db_pool.get_connection(database) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM writes")
        assert cur.fetchone() == (0,)
        cur.execute("SELECT last_value, is_called FROM writes_id_seq")
        assert cur.fetchone() == (1, True)
    print(f"{caught.value}; mutation_attempts=1 sequence_last_value=1 committed_rows=0")


def test_engine_pre_ping_replaces_backend(database: str) -> None:
    engine = create_slot_engine(database)
    with engine.connect() as conn:
        raw = conn.connection.driver_connection
        old_pid = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
    terminate(raw)
    with engine.connect() as conn:
        new_pid = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert new_pid != old_pid
    print(f"sqlalchemy_pre_ping=True old_pid={old_pid} new_pid={new_pid}")


def test_dispose_after_clone_replacement(database: str) -> None:
    engine = create_slot_engine(database)
    with engine.connect() as conn:
        old_oid = conn.execute(
            text("SELECT oid FROM pg_database WHERE datname = current_database()")
        ).scalar_one()
    with db_pool.get_connection(database) as conn:
        old_pid = conn.get_backend_pid()
    # Clone template0 into the same name; all clients must see the new identity.
    db_pool.dispose_database(database)
    admin = psycopg2.connect(**connection_kwargs("postgres"))
    try:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(database)
                )
            )
        db_pool.dispose_database(database)
        with db_pool.get_connection(database) as conn, conn.cursor() as cur:
            assert conn.get_backend_pid() != old_pid
            cur.execute(
                "SELECT oid FROM pg_database WHERE datname = current_database()"
            )
            new_oid = cur.fetchone()[0]
            assert new_oid != old_oid
            cur.execute("SELECT to_regclass('public.writes')")
            assert cur.fetchone() == (None,)
        with engine.connect() as conn:
            assert (
                conn.execute(
                    text(
                        "SELECT oid FROM pg_database WHERE datname = current_database()"
                    )
                ).scalar_one()
                == new_oid
            )
        print(f"clone_disposed=True old_oid={old_oid} new_oid={new_oid}")
    finally:
        admin.close()


def test_constraint_violation_reuses_connection(database: str) -> None:
    with db_pool.get_connection(database) as conn, conn.cursor() as cur:
        pid = conn.get_backend_pid()
        cur.execute("INSERT INTO writes(value) VALUES ('unique')")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        with db_pool.get_connection(database) as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO writes(value) VALUES ('unique')")
    with db_pool.get_connection(database) as conn:
        assert conn.get_backend_pid() == pid


@pytest.mark.parametrize("unusable", ["closed", "transaction"])
def test_preflight_rejects_unusable_connection(
    database: str, unusable: str, caplog: Any
) -> None:
    with db_pool.get_connection(database) as conn:
        pid = conn.get_backend_pid()
    if unusable == "closed":
        conn.close()
    else:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    with caplog.at_level(logging.INFO, logger="nexus.api.db_pool"):
        with db_pool.get_connection(database) as fresh:
            assert fresh.get_backend_pid() != pid
    assert sum("Replacing connection" in r.message for r in caplog.records) == 1


def test_rollback_failure_preserves_body_error_and_discards(database: str) -> None:
    with pytest.raises(ValueError, match="body failure"):
        with db_pool.get_connection(database) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            old_pid = terminate(conn)
            raise ValueError("body failure")
    assert conn.closed
    with db_pool.get_connection(database) as conn:
        assert conn.get_backend_pid() != old_pid


@pytest.mark.parametrize("raw_commit", [False, True])
@pytest.mark.parametrize("async_fallback", [False, True])
def test_fallback_and_scheduler_do_not_replay(
    database: str, raw_commit: bool, async_fallback: bool
) -> None:
    import asyncio

    from nexus.api.retry_handler import FallbackChain
    from nexus.jobs.scheduler import SlotScheduler

    attempts = []

    def first() -> None:
        attempts.append("first")
        try:
            with db_pool.get_connection(database) as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO writes(value) VALUES ('first')")
                terminate(conn)
                if raw_commit:
                    conn.commit()
        except Exception as exc:
            raise RuntimeError("domain wrapper") from exc

    def second() -> None:
        attempts.append("second")

    async def async_first() -> None:
        first()

    async def async_second() -> None:
        second()

    with pytest.raises(RuntimeError, match="domain wrapper") as caught:
        if async_fallback:
            asyncio.run(FallbackChain([async_first, async_second]).async_execute())
        else:
            FallbackChain([first, second]).execute()
    assert attempts == ["first"]
    scheduler = SlotScheduler(4, dbname=database)
    scheduler._recover(caught.value)
    assert scheduler.stopping.is_set()
    assert scheduler._lost.is_set()
    assert scheduler.state == "failed"
    print(
        f"fallback_async={async_fallback} raw_commit={raw_commit} attempts=1 scheduler=failed"
    )


def test_replacement_failure_surfaces_without_loop(database: str, caplog: Any) -> None:
    with db_pool.get_connection(database) as conn:
        original = conn
    admin = psycopg2.connect(**connection_kwargs("postgres"))
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(
                    sql.Identifier(database)
                )
            )
        terminate(original)
        with caplog.at_level(logging.INFO, logger="nexus.api.db_pool"):
            with pytest.raises(
                psycopg2.OperationalError, match="not currently accepting connections"
            ):
                with db_pool.get_connection(database):
                    pytest.fail("An unavailable replacement must not yield")
        assert sum("Replacing connection" in r.message for r in caplog.records) == 1
    finally:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(
                    sql.Identifier(database)
                )
            )
        admin.close()
