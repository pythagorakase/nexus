"""Shared helpers for Orrery basic-need state."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Mapping, Optional, Sequence


class NeedType(str, Enum):
    """Basic physiological needs tracked by the Sunhelm substrate."""

    SLEEP = "sleep"
    HUNGER = "hunger"
    THIRST = "thirst"


NEED_TYPES: tuple[str, ...] = tuple(item.value for item in NeedType)
NEED_ACCRUAL_RATES: Mapping[str, float] = {
    NeedType.SLEEP.value: 1.0,
    NeedType.HUNGER.value: 1.0,
    NeedType.THIRST.value: 1.0,
}
NEED_SEVERITY_PREFIX: Mapping[str, str] = {
    NeedType.SLEEP.value: "sleep_deprived",
    NeedType.HUNGER.value: "hungry",
    NeedType.THIRST.value: "thirsty",
}

NEED_SEVERITY_THRESHOLDS: Mapping[str, Sequence[tuple[float, int, str]]] = {
    NeedType.SLEEP.value: (
        (72.0, 4, "critical"),
        (48.0, 3, "severe"),
        (30.0, 2, "moderate"),
        (16.0, 1, "mild"),
    ),
    NeedType.HUNGER.value: (
        (48.0, 4, "critical"),
        (30.0, 3, "severe"),
        (16.0, 2, "moderate"),
        (8.0, 1, "mild"),
    ),
    NeedType.THIRST.value: (
        (24.0, 4, "critical"),
        (16.0, 3, "severe"),
        (8.0, 2, "moderate"),
        (4.0, 1, "mild"),
    ),
}


def normalize_need_type(need_type: str) -> str:
    """Return a canonical need type or raise for unsupported input."""

    normalized = str(need_type).lower()
    if normalized not in NEED_TYPES:
        raise ValueError(f"Unsupported Orrery need type: {need_type!r}")
    return normalized


def effective_debt_score(
    need_type: str,
    debt_score: float,
    *,
    last_evaluated_at: Optional[datetime],
    current_world_time: Optional[datetime],
) -> float:
    """Return debt after accruing elapsed world time without mutating state."""

    normalized = normalize_need_type(need_type)
    if last_evaluated_at is None or current_world_time is None:
        return max(0.0, float(debt_score))

    elapsed_seconds = (current_world_time - last_evaluated_at).total_seconds()
    if elapsed_seconds <= 0:
        return max(0.0, float(debt_score))

    elapsed_hours = elapsed_seconds / 3600.0
    accrued = elapsed_hours * NEED_ACCRUAL_RATES[normalized]
    return max(0.0, float(debt_score) + accrued)


def severity_for_debt(need_type: str, debt_score: float) -> Optional[tuple[int, str]]:
    """Return the severity level/name for a need debt score, if any."""

    normalized = normalize_need_type(need_type)
    for threshold, level, name in NEED_SEVERITY_THRESHOLDS[normalized]:
        if debt_score >= threshold:
            return level, name
    return None


def severity_tag_for_debt(need_type: str, debt_score: float) -> Optional[str]:
    """Return the registered severity tag for a need debt score, if any."""

    normalized = normalize_need_type(need_type)
    severity = severity_for_debt(normalized, debt_score)
    if severity is None:
        return None
    level, name = severity
    return f"{NEED_SEVERITY_PREFIX[normalized]}_{level}_{name}"


def severity_tags_for_need(need_type: str) -> tuple[str, ...]:
    """Return all severity tags in the mutex track for a need."""

    normalized = normalize_need_type(need_type)
    prefix = NEED_SEVERITY_PREFIX[normalized]
    return tuple(
        f"{prefix}_{level}_{name}"
        for _threshold, level, name in reversed(NEED_SEVERITY_THRESHOLDS[normalized])
    )
