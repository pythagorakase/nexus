"""
Database Conversion Utilities
==============================

Converts between Pydantic models (LLM-friendly) and PostgreSQL types.
Handles time conversion and episode/season calculation.
"""

import logging
from datetime import timedelta
from typing import Optional, Tuple

from nexus.agents.logon.apex_schema import ChronologyUpdate


logger = logging.getLogger("nexus.api.db_converters")


# ============================================================================
# Time Conversion Functions
# ============================================================================


def time_fields_to_interval(
    minutes: Optional[int] = None,
    hours: Optional[int] = None,
    days: Optional[int] = None,
) -> Optional[timedelta]:
    """
    Convert LLM-friendly time fields to PostgreSQL interval.

    Args:
        minutes: Minutes component (0-59)
        hours: Hours component (0-23)
        days: Days component (0+)

    Returns:
        timedelta object or None if all inputs are None
    """
    if all(f is None for f in [minutes, hours, days]):
        return None

    return timedelta(days=days or 0, hours=hours or 0, minutes=minutes or 0)


def interval_to_time_fields(interval: timedelta) -> Tuple[int, int, int]:
    """
    Convert PostgreSQL interval to LLM-friendly time fields.

    Args:
        interval: timedelta from database

    Returns:
        Tuple of (minutes, hours, days)
    """
    total_seconds = int(interval.total_seconds())

    days = total_seconds // 86400
    remaining = total_seconds % 86400

    hours = remaining // 3600
    remaining = remaining % 3600

    minutes = remaining // 60

    return (minutes, hours, days)


# ============================================================================
# Episode/Season Conversion
# ============================================================================


def chronology_for_commit(
    chronology: ChronologyUpdate, *, parent_chunk_id: int
) -> ChronologyUpdate:
    """Keep bootstrap in its initial episode without closing an empty span.

    A parentless opening establishes S1E1; its transition does not advance an
    existing episode or season. Apply this same chronology to both numbering
    and summary planning, preserving elapsed time and the staged draft.
    """
    if parent_chunk_id == 0:
        return chronology.model_copy(update={"episode_transition": "continue"})
    return chronology


def chronology_to_db_values(
    chronology: ChronologyUpdate, current_season: int, current_episode: int
) -> dict:
    """
    Convert ChronologyUpdate (transitions) to absolute DB values.

    Args:
        chronology: Pydantic chronology update with transitions
        current_season: Current season number from parent chunk
        current_episode: Current episode number from parent chunk

    Returns:
        Dict with season, episode, time_delta for database insertion
    """
    # Calculate new season/episode based on transition
    if chronology.episode_transition == "new_season":
        new_season = current_season + 1
        new_episode = 1  # Seasons always start at episode 1
    elif chronology.episode_transition == "new_episode":
        new_season = current_season
        new_episode = current_episode + 1
    else:  # continue
        new_season = current_season
        new_episode = current_episode

    # Convert time fields to interval
    time_delta = time_fields_to_interval(
        minutes=chronology.time_delta_minutes,
        hours=chronology.time_delta_hours,
        days=chronology.time_delta_days,
    )

    return {"season": new_season, "episode": new_episode, "time_delta": time_delta}
