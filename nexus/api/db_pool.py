"""
Centralized database connection pooling for NEXUS API.

This module provides thread-safe connection pooling to prevent
database connection exhaustion and improve performance.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Optional, Dict, Any

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("nexus.api.db_pool")

# Global pool instances per database
_pools: Dict[str, pool.ThreadedConnectionPool] = {}

# Pool configuration
MIN_CONNECTIONS = 1
MAX_CONNECTIONS = 10


def _get_connection_params(dbname: Optional[str] = None) -> Dict[str, Any]:
    """Get database connection parameters from environment."""
    return {
        "dbname": dbname or os.environ.get("PGDATABASE", "NEXUS"),
        "user": os.environ.get("PGUSER", "pythagor"),
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
    }


def _get_pool(dbname: Optional[str] = None) -> pool.ThreadedConnectionPool:
    """Get or create a connection pool for the specified database."""
    db_key = dbname or os.environ.get("PGDATABASE", "NEXUS")

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
        dbname: Database name (defaults to PGDATABASE env var or "NEXUS")
        dict_cursor: If True, use RealDictCursor for dictionary results

    Yields:
        A database connection object

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


# Compatibility function for gradual migration
def _connect(dbname: Optional[str] = None):
    """
    Legacy connection function for backward compatibility.

    DEPRECATED: Use get_connection() context manager instead.

    Note: This returns a connection that must be manually closed!
    """
    logger.warning("Using deprecated _connect() function. Please migrate to get_connection()")
    params = _get_connection_params(dbname)
    return psycopg2.connect(**params)