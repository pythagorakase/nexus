"""
Centralized database connection pooling for NEXUS API.

This module provides thread-safe connection pooling to prevent
database connection exhaustion and improve performance.

Database connections are made to slot databases (save_01 through save_05).
The active slot is determined by the NEXUS_SLOT environment variable,
or can be explicitly passed to connection functions.
"""

from __future__ import annotations

import functools
import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

import psycopg2
from psycopg2 import pool
from psycopg2.extensions import TRANSACTION_STATUS_IDLE
from psycopg2.extras import RealDictCursor

from nexus.api.slot_utils import require_slot_dbname
from nexus.config import load_settings
from nexus.database import (
    AmbiguousCommit,
    commit_transaction,
    connection_kwargs,
    database_url,
    dispose_database_engines,
)

logger = logging.getLogger("nexus.api.db_pool")

# Global pool instances per database
_pools: Dict[str, pool.ThreadedConnectionPool] = {}

# Registry and last-return times are shared by checkout threads.
_pool_lock = threading.RLock()
_idle_since: dict[Any, float] = {}


@functools.lru_cache(maxsize=None)
def get_connect_timeout_seconds() -> int:
    """Read the configured Postgres connect timeout from nexus.toml.

    Loaded lazily on first connection (never at import) so that importing
    this module stays free of configuration and database side effects. The
    value is static config, so it is cached after the first read; call
    ``get_connect_timeout_seconds.cache_clear()`` to force a re-read.
    """
    from nexus.config import load_settings

    settings = load_settings()
    if settings.api is None:
        raise RuntimeError(
            "nexus.toml is missing the [api] section; "
            "[api.database] connect_timeout_seconds is required"
        )
    return settings.api.database.connect_timeout_seconds


def _get_connection_params(
    dbname: Optional[str] = None, **overrides: Any
) -> Dict[str, Any]:
    """Resolve a validated slot through the shared connection contract."""
    return connection_kwargs(require_slot_dbname(dbname=dbname), **overrides)


def _get_pool(
    dbname: Optional[str] = None, **overrides: Any
) -> pool.ThreadedConnectionPool:
    """
    Get or create a connection pool for the specified database.

    Args:
        dbname: Explicit database name (save_01 through save_05).
                If not provided, uses NEXUS_SLOT env var.

    Returns:
        A ThreadedConnectionPool for the database

    Raises:
        ValueError: If dbname is not a valid slot database
        RuntimeError: If no slot can be determined
    """
    # Resolve and validate the database name
    db_key = require_slot_dbname(dbname=dbname)

    params = _get_connection_params(dbname, **overrides)
    config = load_settings().api.database
    with _pool_lock:
        existing = _pools.get(db_key)
        if existing is not None and existing._kwargs != params:
            raise RuntimeError(
                "PostgreSQL pool target changed; close the pool before reconfiguration"
            )
        if existing is None:
            existing = pool.ThreadedConnectionPool(
                config.pool_min_connections, config.pool_max_connections, **params
            )
            _pools[db_key] = existing
            logger.info("Created connection pool for database: %s", db_key)
        return existing


def _preflight(conn: Any, idle_seconds: float) -> None:
    """Reject unusable sessions before handing them to transaction code."""
    if conn.closed:
        raise psycopg2.InterfaceError("connection is closed")
    if conn.get_transaction_status() != TRANSACTION_STATUS_IDLE:
        raise psycopg2.InterfaceError("connection transaction is not idle")
    last_return = _idle_since.pop(conn, None)
    if last_return is None or time.monotonic() - last_return >= idle_seconds:
        # Autocommit prevents the ping from opening a caller-visible transaction.
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            if not conn.closed:
                conn.autocommit = False


@contextmanager
def get_connection(
    dbname: Optional[str] = None, dict_cursor: bool = False, **overrides: Any
) -> Iterator[Any]:
    """
    Get a database connection from the pool.

    Args:
        dbname: Database name (save_01 through save_05).
                If not provided, uses NEXUS_SLOT env var.
        dict_cursor: If True, use RealDictCursor for dictionary results

    Yields:
        A database connection object

    Raises:
        ValueError: If dbname is not a valid slot database
        RuntimeError: If no slot can be determined (NEXUS_SLOT not set)

    Example:
        with get_connection("save_01", dict_cursor=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM global_variables WHERE id = TRUE")
                results = cur.fetchall()
    """
    db_key = require_slot_dbname(dbname=dbname)
    conn_pool = _get_pool(db_key, **overrides)
    idle_seconds = load_settings().api.database.preflight_idle_seconds
    conn = conn_pool.getconn()
    try:
        _preflight(conn, idle_seconds)
    except psycopg2.Error as exc:
        _idle_since.pop(conn, None)
        conn_pool.putconn(conn, close=True)
        logger.info("Replacing connection for database %s: %s", db_key, exc)
        conn = conn_pool.getconn()
        try:
            _preflight(conn, idle_seconds)
        except BaseException:
            _idle_since.pop(conn, None)
            conn_pool.putconn(conn, close=True)
            raise

    discard = False
    orig_cursor_factory = conn.cursor_factory
    if dict_cursor:
        conn.cursor_factory = RealDictCursor
    try:
        try:
            yield conn
        except BaseException as exc:
            discard = isinstance(
                exc,
                (AmbiguousCommit, psycopg2.OperationalError, psycopg2.InterfaceError),
            )
            try:
                conn.rollback()
            except Exception:
                discard = True
                logger.exception("Rollback failed for database %s", db_key)
            raise
        else:
            try:
                commit_transaction(conn)
            except AmbiguousCommit:
                discard = True
                raise
            except BaseException:
                try:
                    conn.rollback()
                except Exception:
                    discard = True
                    logger.exception("Rollback failed for database %s", db_key)
                raise
    finally:
        conn.cursor_factory = orig_cursor_factory
        with _pool_lock:
            if conn_pool.closed:
                conn.close()
            else:
                conn_pool.putconn(conn, close=discard)
                if not discard and not conn.closed:
                    _idle_since[conn] = time.monotonic()


def close_all_pools() -> None:
    """Close all pools and engines and clear cached connection configuration."""
    with _pool_lock:
        for dbname in list(_pools):
            dispose_database(dbname)
        dispose_database_engines()
        _idle_since.clear()
        get_connect_timeout_seconds.cache_clear()


def dispose_database(dbname: str) -> None:
    """Invalidate this database's pool and registered engines before replacement."""
    with _pool_lock:
        conn_pool = _pools.pop(dbname, None)
        if conn_pool is not None:
            conn_pool.closeall()
            logger.info("Closed connection pool for database: %s", dbname)
        for conn in list(_idle_since):
            if conn.closed or conn.info.dbname == dbname:
                _idle_since.pop(conn, None)
        dispose_database_engines(dbname)


def close_pool(dbname: Optional[str] = None) -> None:
    """Invalidate a validated slot's pooled connections and engines."""
    dispose_database(require_slot_dbname(dbname=dbname))


# Compatibility function for gradual migration
def _connect(dbname: Optional[str] = None):
    """
    Legacy connection function for backward compatibility.

    DEPRECATED: Use get_connection() context manager instead.

    Args:
        dbname: Database name (save_01 through save_05).
                If not provided, uses NEXUS_SLOT env var.

    Returns:
        A database connection (must be manually closed!)

    Raises:
        ValueError: If dbname is not a valid slot database
        RuntimeError: If no slot can be determined
    """
    logger.warning(
        "Using deprecated _connect() function. Please migrate to get_connection()"
    )
    params = _get_connection_params(dbname)
    return psycopg2.connect(**params)
