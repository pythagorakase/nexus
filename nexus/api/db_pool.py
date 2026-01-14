"""
Centralized database connection pooling for NEXUS API.

This module provides thread-safe connection pooling to prevent
database connection exhaustion and improve performance.

Database connections are made to slot databases (save_01 through save_05).
The active slot is determined by the NEXUS_SLOT environment variable,
or can be explicitly passed to connection functions.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Optional, Dict, Any

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from nexus.api.slot_utils import require_slot_dbname

logger = logging.getLogger("nexus.api.db_pool")

# Global pool instances per database
_pools: Dict[str, pool.ThreadedConnectionPool] = {}

# Pool configuration
MIN_CONNECTIONS = 1
MAX_CONNECTIONS = 10


def _get_connection_params(dbname: Optional[str] = None) -> Dict[str, Any]:
    """
    Get database connection parameters.

    Args:
        dbname: Explicit database name (save_01 through save_05).
                If not provided, uses NEXUS_SLOT env var.

    Returns:
        Connection parameters dict for psycopg2

    Raises:
        ValueError: If dbname is not a valid slot database
        RuntimeError: If no slot can be determined
    """
    # Use require_slot_dbname to validate and resolve the database name
    # This ensures we never accidentally connect to NEXUS
    resolved_dbname = require_slot_dbname(dbname=dbname)

    return {
        "dbname": resolved_dbname,
        "user": os.environ.get("PGUSER", "pythagor"),
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
    }


def _get_pool(dbname: Optional[str] = None) -> pool.ThreadedConnectionPool:
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

    if db_key not in _pools:
        params = _get_connection_params(dbname)
        try:
            _pools[db_key] = pool.ThreadedConnectionPool(
                MIN_CONNECTIONS,
                MAX_CONNECTIONS,
                **params
            )
            logger.info("Created connection pool for database: %s", db_key)
        except psycopg2.Error as e:
            logger.error("Failed to create connection pool for %s: %s", db_key, e)
            raise

    return _pools[db_key]


@contextmanager
def get_connection(dbname: Optional[str] = None, dict_cursor: bool = False):
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
                cur.execute("SELECT * FROM assets.save_slots")
                results = cur.fetchall()
    """
    conn_pool = _get_pool(dbname)
    conn = None

    try:
        conn = conn_pool.getconn()
        if dict_cursor:
            # Replace the connection's cursor factory
            orig_cursor_factory = conn.cursor_factory
            conn.cursor_factory = RealDictCursor

        yield conn

        # Commit if no exception occurred
        conn.commit()

    except (psycopg2.Error, psycopg2.Warning) as e:
        # Rollback on database errors
        if conn:
            conn.rollback()
        logger.error("Database operation failed: %s", e)
        raise
    except Exception as e:
        # Rollback on any other exception
        if conn:
            conn.rollback()
        logger.error("Unexpected error during database operation: %s", e)
        raise

    finally:
        # Return connection to pool
        if conn:
            if dict_cursor and 'orig_cursor_factory' in locals():
                conn.cursor_factory = orig_cursor_factory
            conn_pool.putconn(conn)


def close_all_pools():
    """Close all connection pools. Call this on application shutdown."""
    for db_key, conn_pool in _pools.items():
        try:
            conn_pool.closeall()
            logger.info("Closed connection pool for database: %s", db_key)
        except Exception as e:
            logger.error("Error closing pool for %s: %s", db_key, e)

    _pools.clear()


def close_pool(dbname: Optional[str] = None) -> None:
    """
    Close and remove the connection pool for a specific database.

    Args:
        dbname: Database name (save_01 through save_05).
                If not provided, uses NEXUS_SLOT env var.
    """
    db_key = require_slot_dbname(dbname=dbname)
    conn_pool = _pools.pop(db_key, None)
    if not conn_pool:
        return
    try:
        conn_pool.closeall()
        logger.info("Closed connection pool for database: %s", db_key)
    except Exception as e:
        logger.error("Error closing pool for %s: %s", db_key, e)


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
    logger.warning("Using deprecated _connect() function. Please migrate to get_connection()")
    params = _get_connection_params(dbname)
    return psycopg2.connect(**params)
