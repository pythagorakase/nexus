"""
Save slot metadata helpers.

Lock mechanism uses PostgreSQL's default_transaction_read_only setting
for database-level write protection.
"""

from __future__ import annotations

import logging
import os
import psycopg2
from typing import Dict, List, Optional

from nexus.api.db_pool import get_connection
from nexus.api.slot_utils import slot_dbname

logger = logging.getLogger("nexus.api.save_slots")


def _get_admin_connection():
    """Get connection to postgres admin database for ALTER DATABASE commands."""
    return psycopg2.connect(
        dbname="postgres",
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


def is_slot_locked(slot_number: int, dbname: Optional[str] = None) -> bool:
    """
    Check if a slot database is locked (read-only).

    Uses PostgreSQL's default_transaction_read_only setting.

    Args:
        slot_number: Slot number (1-5)
        dbname: Optional database name (defaults to slot_dbname(slot_number))

    Returns:
        True if the database is read-only, False otherwise
    """
    db = dbname or slot_dbname(slot_number)

    # Query pg_db_role_setting for the database's read-only setting
    conn = _get_admin_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT setconfig
                FROM pg_db_role_setting s
                JOIN pg_database d ON d.oid = s.setdatabase
                WHERE d.datname = %s AND s.setrole = 0
            """, (db,))
            row = cur.fetchone()
            if row and row[0]:
                # setconfig is an array like ['default_transaction_read_only=on']
                return 'default_transaction_read_only=on' in row[0]
            return False
    finally:
        conn.close()


def lock_slot(slot_number: int, dbname: Optional[str] = None) -> None:
    """
    Lock a save slot database to prevent all write operations.

    Uses PostgreSQL's default_transaction_read_only = on setting,
    which blocks INSERT, UPDATE, DELETE, DROP, etc. while still
    allowing SELECT queries.

    Args:
        slot_number: Slot number (1-5)
        dbname: Optional database name (defaults to slot_dbname(slot_number))

    Raises:
        ValueError: If slot_number is not between 1 and 5
    """
    if slot_number < 1 or slot_number > 5:
        raise ValueError("slot_number must be between 1 and 5")

    db = dbname or slot_dbname(slot_number)

    conn = _get_admin_connection()
    try:
        conn.autocommit = True  # ALTER DATABASE cannot run in a transaction
        with conn.cursor() as cur:
            # Use format string for database name (can't parameterize identifiers)
            # Safe because slot_dbname() only returns save_01 through save_05
            cur.execute(f"ALTER DATABASE {db} SET default_transaction_read_only = on")
    finally:
        conn.close()

    logger.info("Locked slot %s (%s) - database is now read-only", slot_number, db)


def unlock_slot(slot_number: int, dbname: Optional[str] = None) -> None:
    """
    Unlock a save slot database to allow write operations.

    Removes the default_transaction_read_only setting.

    Args:
        slot_number: Slot number (1-5)
        dbname: Optional database name (defaults to slot_dbname(slot_number))

    Raises:
        ValueError: If slot_number is not between 1 and 5
    """
    if slot_number < 1 or slot_number > 5:
        raise ValueError("slot_number must be between 1 and 5")

    db = dbname or slot_dbname(slot_number)

    conn = _get_admin_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"ALTER DATABASE {db} SET default_transaction_read_only = off")
    finally:
        conn.close()

    logger.info("Unlocked slot %s (%s) - database is now writable", slot_number, db)


def clear_active(dbname: Optional[str] = None) -> None:
    """
    Clear the active flag on all save slots.

    Note: This is a no-op now that we use database-level locking.
    Kept for API compatibility.

    Args:
        dbname: Optional database name (defaults to PGDATABASE env var)
    """
    # Previously updated assets.save_slots.is_active
    # Now a no-op - active state tracked externally or not at all
    logger.debug("clear_active called for %s (no-op)", dbname or "(default slot)")


def get_slot_model(slot_number: int, dbname: Optional[str] = None) -> Optional[str]:
    """
    Get the model configured for a slot.

    Args:
        slot_number: Slot number (1-5)
        dbname: Optional database name (defaults to slot_dbname(slot_number))

    Returns:
        Model name (e.g., 'gpt-5.1', 'TEST', 'claude') or None
    """
    db = dbname or slot_dbname(slot_number)
    with get_connection(db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT model FROM global_variables WHERE id = TRUE")
            row = cur.fetchone()
            return row[0] if row else None


def set_slot_model(slot_number: int, model: str, dbname: Optional[str] = None) -> None:
    """
    Set the model for a slot.

    Args:
        slot_number: Slot number (1-5)
        model: Model name (e.g., 'gpt-5.1', 'TEST', 'claude')
        dbname: Optional database name (defaults to slot_dbname(slot_number))
    """
    db = dbname or slot_dbname(slot_number)
    with get_connection(db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE global_variables SET model = %s WHERE id = TRUE",
                (model,)
            )
    logger.info("Set model for slot %s to %s", slot_number, model)


def upsert_slot(
    slot_number: int,
    is_active: Optional[bool] = None,
    model: Optional[str] = None,
    dbname: Optional[str] = None,
    **kwargs,  # Absorb deprecated kwargs like character_name
) -> None:
    """
    Update slot metadata.

    Currently only handles model storage in global_variables.
    Other parameters are deprecated/ignored.

    Args:
        slot_number: Slot number (1-5)
        is_active: Deprecated, ignored
        model: Optional model name to set
        dbname: Optional database name
    """
    if model:
        set_slot_model(slot_number, model, dbname)
    # is_active and character_name are deprecated - no-op
    if kwargs:
        logger.debug("upsert_slot ignoring deprecated kwargs: %s", list(kwargs.keys()))
