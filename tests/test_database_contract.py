"""Real parameter adapters and isolated PostgreSQL routing for #880."""

from __future__ import annotations

import asyncio
import getpass
import os
from pathlib import Path
import socket
import shutil
import subprocess
from typing import Iterator

import asyncpg
import psycopg2
from psycopg2 import sql
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from nexus.api import db_pool, slot_utils
from nexus.config.settings_models import APIDatabaseSettings
from nexus.database import (
    asyncpg_kwargs,
    connection_kwargs,
    connection_target,
    database_url,
    resolved_database_url,
    subprocess_env,
    url_connection_kwargs,
    verify_database_url,
)


@pytest.fixture
def contract_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Use a real isolated TOML file and remove ambient connection overrides."""
    for key in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGCONNECT_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "nexus.toml"
    path.write_text(Path("nexus.toml").read_text())
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(path))
    return path


def test_connection_environment_and_url_escaping(contract_config, monkeypatch):
    monkeypatch.setenv("PGHOST", "127.0.0.2")
    monkeypatch.setenv("PGPORT", "55437")
    monkeypatch.setenv("PGUSER", "role@:/% space")
    monkeypatch.setenv("PGPASSWORD", "p@ss:/?#% word")
    params = db_pool._get_connection_params("save_04")
    url = slot_utils.get_slot_db_url(slot=4)
    assert url_connection_kwargs(url) == params
    parsed = make_url(url)
    assert parsed.username == "role@:/% space"
    assert parsed.password == "p@ss:/?#% word"
    assert params["host"] == "127.0.0.2"
    assert params["port"] == 55437
    assert params["options"] == "-c TimeZone=UTC"
    assert resolved_database_url(resolved_database_url(url)) == url
    assert (
        connection_kwargs(
            "save_04", options="-c statement_timeout=1000 -c TimeZone=Europe/London"
        )["options"]
        == "-c statement_timeout=1000 -c TimeZone=UTC"
    )
    timed_url = str(make_url(url).set(query={"connect_timeout": "7"}))
    assert url_connection_kwargs(timed_url)["connect_timeout"] == 7
    assert "password" not in connection_target(params)


def test_connection_config_and_explicit_override(contract_config, monkeypatch):
    contract_config.write_text(
        contract_config.read_text()
        .replace('host = ""', 'host = "configured.example"', 1)
        .replace('user = ""', 'user = "configured_role"\nport = 55438', 1)
    )
    monkeypatch.setenv("PGHOST", "environment.example")
    monkeypatch.setenv("PGPORT", "55439")
    monkeypatch.setenv("PGUSER", "environment_role")
    params = connection_kwargs("save_04")
    assert connection_target(params) == {
        "host": "configured.example",
        "port": 55438,
        "user": "configured_role",
        "dbname": "save_04",
    }
    overrides = dict(
        host="explicit.example", port=55440, user="explicit_role", password="a/b@c"
    )
    params = db_pool._get_connection_params("save_04", **overrides)
    assert all(params[key] == value for key, value in overrides.items())
    assert params == url_connection_kwargs(
        slot_utils.get_slot_db_url(slot=4, **overrides)
    )
    assert subprocess_env()["PGHOST"] == "configured.example"
    assert subprocess_env()["PGOPTIONS"] == "-c TimeZone=UTC"


def test_connection_libpq_defaults_and_socket_url(contract_config):
    params = connection_kwargs("save_04")
    assert params["user"] == getpass.getuser()
    assert params["host"] == ""
    url = database_url("save_04", host="/tmp/private postgres", port=55441)
    assert url_connection_kwargs(url)["host"] == "/tmp/private postgres"
    assert url_connection_kwargs(url)["port"] == 55441


@pytest.mark.parametrize("timezone", ["", "Invalid/Zone", "UTC -c role=other"])
def test_connection_timezone_rejects_invalid_values(timezone):
    with pytest.raises(ValueError, match="IANA time zone"):
        APIDatabaseSettings(connect_timeout_seconds=5, session_timezone=timezone)


def test_connection_guard_rejects_foreign_target_before_connect(contract_config):
    from nexus.agents.memnon.utils.db_access import setup_database_indexes
    from nexus.agents.memnon.utils.db_schema import DatabaseManager

    foreign = database_url("save_04", host="foreign.example", port=55442)
    with pytest.raises(ValueError, match="target mismatch"):
        setup_database_indexes(foreign)
    with pytest.raises(ConnectionError, match="target mismatch"):
        DatabaseManager(foreign)
    with pytest.raises(ValueError, match="target mismatch"):
        verify_database_url(database_url("save_04"), dbname="save_05")


@pytest.fixture
def two_clusters(tmp_path: Path) -> Iterator[list[dict]]:
    """Start two disposable servers; never use the owner's default server."""
    from scripts.new_story_setup import _postgres_tools

    binaries = _postgres_tools("initdb", "pg_ctl")
    clusters = []
    try:
        for index in range(2):
            root = tmp_path / f"cluster{index}"
            root.mkdir()
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            data = root / "data"
            log = root / "server.log"
            subprocess.run(
                [
                    binaries["initdb"],
                    "-D",
                    str(data),
                    "-A",
                    "trust",
                    "-U",
                    "contract_role",
                    "--no-locale",
                    "-E",
                    "UTF8",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    binaries["pg_ctl"],
                    "-D",
                    str(data),
                    "-l",
                    str(log),
                    "-o",
                    f"-h 127.0.0.1 -k /tmp -p {port} -c log_statement=all -c log_connections=on",
                    "-w",
                    "start",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            clusters.append(
                dict(
                    data=data,
                    log=log,
                    host="127.0.0.1",
                    port=port,
                    user="contract_role",
                )
            )
        yield clusters
    finally:
        db_pool.close_all_pools()
        for cluster in reversed(clusters):
            subprocess.run(
                [
                    binaries["pg_ctl"],
                    "-D",
                    str(cluster["data"]),
                    "-m",
                    "immediate",
                    "-w",
                    "stop",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            shutil.rmtree(cluster["data"].parent)


@pytest.mark.requires_postgres
def test_connection_two_clusters_pool_url_async_timezone_and_guard(
    two_clusters,
    contract_config,
    monkeypatch,
):
    """Inspect both live activity and catalogs, with logs covering short connections."""
    private, other = two_clusters
    dbname = "qa640_connection_contract"
    for cluster in two_clusters:
        conn = psycopg2.connect(
            dbname="postgres", **{k: cluster[k] for k in ("host", "port", "user")}
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        conn.close()
    config = contract_config.read_text().replace(
        'host = ""', f'host = "{private["host"]}"', 1
    )
    config = config.replace(
        'user = ""', f'user = "{private["user"]}"\nport = {private["port"]}', 1
    )
    contract_config.write_text(config)
    # A conflicting environment reproduces the original split-server hazard.
    monkeypatch.setenv("PGPORT", str(other["port"]))
    monkeypatch.setenv("PGHOST", other["host"])
    monkeypatch.setenv("PGUSER", other["user"])
    monkeypatch.setattr(
        slot_utils, "VALID_DBNAMES", slot_utils.VALID_DBNAMES | {dbname}
    )
    observer = psycopg2.connect(
        dbname=dbname, **{k: other[k] for k in ("host", "port", "user")}
    )
    observer.autocommit = True
    try:
        with observer.cursor() as cur:
            cur.execute("SELECT oid, relname FROM pg_class ORDER BY oid")
            before = cur.fetchall()
        log_offset = other["log"].stat().st_size
        with db_pool.get_connection(dbname) as pooled:
            with pooled.cursor() as cur:
                cur.execute("SHOW TimeZone")
                assert cur.fetchone() == ("UTC",)
                cur.execute("SELECT inet_server_port()")
                assert cur.fetchone() == (private["port"],)
            engine = create_engine(database_url(dbname))
            try:
                with engine.connect() as url_conn:
                    assert url_conn.execute(text("SHOW TimeZone")).scalar() == "UTC"
                    assert (
                        url_conn.execute(text("SELECT inet_server_port()")).scalar()
                        == private["port"]
                    )
            finally:
                engine.dispose()

        async def check_async():
            conn = await asyncpg.connect(**asyncpg_kwargs(dbname))
            try:
                assert await conn.fetchval("SHOW TimeZone") == "UTC"
                assert (
                    await conn.fetchval("SELECT inet_server_port()") == private["port"]
                )
            finally:
                await conn.close()

        asyncio.run(check_async())
        from nexus.agents.memnon.utils.db_access import setup_database_indexes

        with pytest.raises(ValueError, match="target mismatch"):
            setup_database_indexes(database_url(dbname, port=other["port"]))
        with observer.cursor() as cur:
            cur.execute("SELECT oid, relname FROM pg_class ORDER BY oid")
            assert cur.fetchall() == before
            cur.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                (dbname,),
            )
            assert cur.fetchone() == (0,)
        unseen = other["log"].read_text()[log_offset:]
        assert "connection received" not in unseen
        assert "CREATE " not in unseen
    finally:
        observer.close()
