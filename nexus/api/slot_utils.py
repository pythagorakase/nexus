"""
Utilities for selecting the active save slot (per-slot database).

Each save slot corresponds to a separate database:
- Slot 1 -> save_01
- Slot 2 -> save_02
- Slot 3 -> save_03
- Slot 4 -> save_04
- Slot 5 -> save_05

The active slot is determined by the NEXUS_SLOT environment variable.
NEXUS is no longer a valid target database for gameplay.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

VALID_SLOTS = {1, 2, 3, 4, 5}
VALID_DBNAMES = {"save_01", "save_02", "save_03", "save_04", "save_05"}


def slot_dbname(slot_number: int) -> str:
    """Convert a slot number (1-5) to its database name (save_01 - save_05)."""
    if slot_number not in VALID_SLOTS:
        raise ValueError("slot_number must be between 1 and 5")
    return f"save_{slot_number:02d}"


def set_slot_env(slot_number: int) -> None:
    """
    Set environment variables (PGDATABASE) to point to the slot DB.
    Use in subprocesses or one-shot scripts that rely on PGDATABASE.
    """
    os.environ["PGDATABASE"] = slot_dbname(slot_number)


def get_slot_env(slot_number: int) -> Dict[str, str]:
    """Return environment overrides for running commands against a slot DB."""
    env = os.environ.copy()
    env["PGDATABASE"] = slot_dbname(slot_number)
    return env


def all_slots() -> list[int]:
    """Iterator over valid slot numbers."""
    return sorted(list(VALID_SLOTS))


def get_active_slot() -> int:
    """
    Get the currently active slot from the NEXUS_SLOT environment variable.

    Returns:
        The active slot number (1-5)

    Raises:
        RuntimeError: If NEXUS_SLOT is not set
        ValueError: If NEXUS_SLOT is not a valid slot number (1-5)
    """
    slot_str = os.environ.get("NEXUS_SLOT")
    if slot_str is None:
        raise RuntimeError(
            "No active slot configured. Set NEXUS_SLOT environment variable (1-5) "
            "or explicitly pass slot_number/dbname to database functions."
        )
    try:
        slot = int(slot_str)
    except ValueError:
        raise ValueError(f"NEXUS_SLOT must be an integer, got: {slot_str!r}")

    if slot not in VALID_SLOTS:
        raise ValueError(f"NEXUS_SLOT must be between 1 and 5, got {slot}")
    return slot


def get_active_slot_dbname() -> str:
    """
    Get the database name for the currently active slot.

    Returns:
        Database name (e.g., "save_01")

    Raises:
        RuntimeError: If NEXUS_SLOT is not set
        ValueError: If NEXUS_SLOT is not valid
    """
    return slot_dbname(get_active_slot())


def require_slot_dbname(
    dbname: Optional[str] = None,
    slot: Optional[int] = None,
) -> str:
    """
    Require an explicit slot database name. Never defaults to NEXUS.

    Resolution priority:
    1. Explicit dbname parameter (validated against VALID_DBNAMES)
    2. Explicit slot number (converted via slot_dbname)
    3. NEXUS_SLOT environment variable
    4. Raise RuntimeError

    Args:
        dbname: Explicit database name (save_01 through save_05)
        slot: Explicit slot number (1-5)

    Returns:
        A valid slot database name

    Raises:
        ValueError: If dbname is invalid or slot is out of range
        RuntimeError: If no slot can be determined
    """
    if dbname is not None:
        if dbname not in VALID_DBNAMES:
            raise ValueError(
                f"Invalid database name: {dbname!r}. "
                f"Must be one of: {', '.join(sorted(VALID_DBNAMES))}"
            )
        return dbname

    if slot is not None:
        return slot_dbname(slot)

    # Fall back to environment variable
    return get_active_slot_dbname()


def get_slot_db_url(
    dbname: Optional[str] = None,
    slot: Optional[int] = None,
    user: str = "pythagor",
    host: str = "localhost",
    port: int = 5432,
) -> str:
    """
    Build a PostgreSQL connection URL for a slot database.

    Args:
        dbname: Explicit database name (save_01 through save_05)
        slot: Explicit slot number (1-5)
        user: Database user (default: pythagor)
        host: Database host (default: localhost)
        port: Database port (default: 5432)

    Returns:
        PostgreSQL connection URL

    Raises:
        ValueError: If dbname is invalid or slot is out of range
        RuntimeError: If no slot can be determined
    """
    db = require_slot_dbname(dbname=dbname, slot=slot)
    return f"postgresql://{user}@{host}:{port}/{db}"
