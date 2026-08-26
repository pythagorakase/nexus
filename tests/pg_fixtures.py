"""Shared PostgreSQL helpers for disposable integration-test databases."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import URL

from nexus.api import db_pool
from scripts import new_story_setup


def connection_parameters() -> dict[str, str]:
    """Return the PG* environment as keyword parameters, never a hand-built URI.

    Keyword parameters survive Unix-socket directories (`PGHOST=/var/run/...`)
    and IPv6 hosts (`::1`) that break naive URI interpolation.
    """

    return {
        "user": os.environ.get("PGUSER", "pythagor"),
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
    }


def connect(dbname: str, *, cursor_factory: Any = None) -> Any:
    """Open a direct psycopg2 connection to ``dbname``."""

    kwargs: dict[str, Any] = {"dbname": dbname, **connection_parameters()}
    if cursor_factory is not None:
        kwargs["cursor_factory"] = cursor_factory
    return psycopg2.connect(**kwargs)


def asyncpg_kwargs(dbname: str) -> dict[str, Any]:
    """Return keyword arguments for ``asyncpg.connect`` targeting ``dbname``."""

    params = connection_parameters()
    return {
        "database": dbname,
        "user": params["user"],
        "host": params["host"],
        "port": int(params["port"]),
    }


def sqlalchemy_url(dbname: str) -> URL:
    """Return a SQLAlchemy URL for ``dbname`` built through ``URL.create``."""

    params = connection_parameters()
    return URL.create(
        "postgresql",
        username=params["user"],
        host=params["host"],
        port=int(params["port"]),
        database=dbname,
    )


_connect = connect


@contextmanager
def disposable_slot_database(
    prefix: str,
    *,
    source_db: str = "NEXUS_template",
) -> Iterator[str]:
    """Yield a uniquely named template clone and always remove it afterward.

    Fails loudly when the admin connection is unavailable; opting into the
    PostgreSQL gate means PostgreSQL is required.
    """

    dbname = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin: Any = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        # NEXUS_RUN_POSTGRES=1 asserts PostgreSQL is required: an unreachable
        # or misconfigured server is a failure, never a skip (a skipped gate is
        # how issue #735's debt hid for two months). The requires_postgres
        # marker already skips when the gate is not opted in.
        admin = _connect("postgres")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        new_story_setup.initialize_slot_database(dbname, source_db=source_db)
        yield dbname
    finally:
        new_story_setup.USE_POOL = original_use_pool
        pool = db_pool._pools.pop(dbname, None)
        try:
            if pool is not None:
                pool.closeall()
        finally:
            if admin is not None:
                try:
                    with admin.cursor() as cur:
                        try:
                            cur.execute(
                                "SELECT pg_terminate_backend(pid) "
                                "FROM pg_stat_activity "
                                "WHERE datname = %s AND pid <> pg_backend_pid()",
                                (dbname,),
                            )
                        finally:
                            cur.execute(
                                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                                    sql.Identifier(dbname)
                                )
                            )
                finally:
                    admin.close()


def seed_protagonist(
    dbname: str,
    *,
    name: str = "Fixture Player",
    summary: str = "Canonical player for PostgreSQL coverage.",
    base_timestamp: str = "2100-01-01T00:00:00+00:00",
) -> tuple[int, int]:
    """Bind a fixture-owned player to the save and return character/entity IDs."""

    with _connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE global_variables SET base_timestamp = %s WHERE id = true",
                (base_timestamp,),
            )
            assert cur.rowcount == 1
            cur.execute(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('character', true) RETURNING id"
            )
            entity_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO characters (name, summary, entity_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (name, summary, entity_id),
            )
            character_id = int(cur.fetchone()[0])
            cur.execute(
                "UPDATE global_variables SET user_character = %s WHERE id = true",
                (character_id,),
            )
            assert cur.rowcount == 1
    return character_id, entity_id
