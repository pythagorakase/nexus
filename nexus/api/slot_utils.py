"""
Utilities for selecting the active save slot (per-slot database).
"""

from __future__ import annotations

import os
from typing import Optional

VALID_SLOTS = {1, 2, 3, 4, 5}


def slot_dbname(slot_number: int) -> str:
    if slot_number not in VALID_SLOTS:
        raise ValueError("slot_number must be between 1 and 5")
    return f"save_{slot_number:02d}"


def set_slot_env(slot_number: int) -> None:
    """
    Set environment variables (PGDATABASE) to point to the slot DB.
    Use in subprocesses or one-shot scripts that rely on PGDATABASE.
    """
    os.environ["PGDATABASE"] = slot_dbname(slot_number)


def get_slot_env(slot_number: int) -> dict:
    """Return environment overrides for running commands against a slot DB."""
    env = os.environ.copy()
    env["PGDATABASE"] = slot_dbname(slot_number)
    return env


def all_slots():
    """Iterator over valid slot numbers."""
    return sorted(list(VALID_SLOTS))
