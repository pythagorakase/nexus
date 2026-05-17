"""Shared helpers for Orrery basic-need state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Any, Mapping, Optional


class NeedType(str, Enum):
    """Basic physiological needs tracked by the Sunhelm substrate."""

    SLEEP = "sleep"
    HUNGER = "hunger"
    THIRST = "thirst"


NEED_TYPES: tuple[str, ...] = tuple(item.value for item in NeedType)
NEED_SEVERITY_PREFIX: Mapping[str, str] = {
    NeedType.SLEEP.value: "sleep_deprived",
    NeedType.HUNGER.value: "hungry",
    NeedType.THIRST.value: "thirsty",
}
NEED_SEVERITY_LEVELS: tuple[tuple[int, str], ...] = (
    (4, "critical"),
    (3, "severe"),
    (2, "moderate"),
    (1, "mild"),
)
DEFAULT_NEED_ACCRUAL_RATES: Mapping[str, float] = {
    NeedType.SLEEP.value: 1.0,
    NeedType.HUNGER.value: 1.0,
    NeedType.THIRST.value: 1.0,
}
DEFAULT_NEED_SEVERITY_THRESHOLDS: Mapping[str, Mapping[str, float]] = {
    NeedType.SLEEP.value: {
        "mild": 16.0,
        "moderate": 30.0,
        "severe": 48.0,
        "critical": 72.0,
    },
    NeedType.HUNGER.value: {
        "mild": 8.0,
        "moderate": 16.0,
        "severe": 30.0,
        "critical": 48.0,
    },
    NeedType.THIRST.value: {
        "mild": 4.0,
        "moderate": 8.0,
        "severe": 16.0,
        "critical": 24.0,
    },
}
DEFAULT_NEED_PRIORITIES: Mapping[str, int] = {
    NeedType.SLEEP.value: 25,
    NeedType.THIRST.value: 24,
    NeedType.HUNGER.value: 22,
}


@dataclass(frozen=True, slots=True)
class NeedPressureTuning:
    """Configurable prompt-pressure behavior for present-character needs."""

    min_severity_level: int = 2
    magnitude_base: float = 0.35
    magnitude_per_level: float = 0.10
    magnitude_cap: float = 0.85

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "NeedPressureTuning":
        """Build tuning from a settings mapping, preserving defaults."""

        if raw is None:
            return cls()
        return cls(
            min_severity_level=int(raw.get("min_severity_level", 2)),
            magnitude_base=float(raw.get("magnitude_base", 0.35)),
            magnitude_per_level=float(raw.get("magnitude_per_level", 0.10)),
            magnitude_cap=float(raw.get("magnitude_cap", 0.85)),
        )

    def magnitude_for_level(self, level: int) -> float:
        """Return a bounded scene-pressure magnitude for a severity level."""

        return min(
            self.magnitude_cap,
            self.magnitude_base + float(level) * self.magnitude_per_level,
        )


@dataclass(frozen=True, slots=True)
class NeedTuning:
    """Configurable Sunhelm need tuning loaded from ``nexus.toml``."""

    accrual_rates: Mapping[str, float]
    severity_thresholds: Mapping[str, Mapping[str, float]]
    priorities: Mapping[str, int]
    pressure: NeedPressureTuning

    @classmethod
    def default(cls) -> "NeedTuning":
        """Return default tuning matching the committed ``nexus.toml`` values."""

        return cls(
            accrual_rates=dict(DEFAULT_NEED_ACCRUAL_RATES),
            severity_thresholds={
                need_type: dict(thresholds)
                for need_type, thresholds in DEFAULT_NEED_SEVERITY_THRESHOLDS.items()
            },
            priorities=dict(DEFAULT_NEED_PRIORITIES),
            pressure=NeedPressureTuning(),
        )

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "NeedTuning":
        """Build tuning from a Sunhelm settings mapping."""

        if raw is None:
            return cls.default()

        accrual_rates = _coerce_need_mapping(
            raw.get("accrual_rates"),
            defaults=DEFAULT_NEED_ACCRUAL_RATES,
            cast=float,
        )
        priorities = _coerce_need_mapping(
            raw.get("priorities"),
            defaults=DEFAULT_NEED_PRIORITIES,
            cast=int,
        )
        raw_thresholds = raw.get("severity_thresholds") or {}
        severity_thresholds: dict[str, dict[str, float]] = {}
        for need_type in NEED_TYPES:
            configured = raw_thresholds.get(need_type) or {}
            defaults = DEFAULT_NEED_SEVERITY_THRESHOLDS[need_type]
            severity_thresholds[need_type] = {
                name: float(configured.get(name, defaults[name]))
                for _level, name in NEED_SEVERITY_LEVELS
            }

        return cls(
            accrual_rates=accrual_rates,
            severity_thresholds=severity_thresholds,
            priorities=priorities,
            pressure=NeedPressureTuning.from_mapping(raw.get("pressure")),
        )


def _coerce_need_mapping(
    raw: Any,
    *,
    defaults: Mapping[str, Any],
    cast: type,
) -> dict[str, Any]:
    values = dict(defaults)
    if raw:
        for need_type, value in dict(raw).items():
            values[normalize_need_type(str(need_type))] = cast(value)
    return values


def coerce_need_tuning(raw: Optional[Any] = None) -> NeedTuning:
    """Return need tuning from settings, a ``NeedTuning``, or ``nexus.toml``."""

    if isinstance(raw, NeedTuning):
        return raw
    if raw is None:
        return load_need_tuning()
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    if isinstance(raw, Mapping):
        if "orrery" in raw:
            raw = (raw.get("orrery") or {}).get("sunhelm")
        elif "sunhelm" in raw:
            raw = raw.get("sunhelm")
        return NeedTuning.from_mapping(raw)
    raise TypeError(f"Unsupported Sunhelm tuning payload: {type(raw).__name__}")


@lru_cache(maxsize=1)
def load_need_tuning() -> NeedTuning:
    """Load Sunhelm tuning from ``nexus.toml`` through the validated config."""

    from nexus.config import load_settings

    settings = load_settings()
    if settings.orrery is None:
        return NeedTuning.default()
    return NeedTuning.from_mapping(settings.orrery.sunhelm.model_dump())


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
    tuning: Optional[NeedTuning] = None,
) -> float:
    """Return debt after accruing elapsed world time without mutating state."""

    tuning = tuning or load_need_tuning()
    normalized = normalize_need_type(need_type)
    if last_evaluated_at is None or current_world_time is None:
        return max(0.0, float(debt_score))

    elapsed_seconds = (current_world_time - last_evaluated_at).total_seconds()
    if elapsed_seconds <= 0:
        return max(0.0, float(debt_score))

    elapsed_hours = elapsed_seconds / 3600.0
    accrued = elapsed_hours * tuning.accrual_rates[normalized]
    return max(0.0, float(debt_score) + accrued)


def severity_for_debt(
    need_type: str,
    debt_score: float,
    *,
    tuning: Optional[NeedTuning] = None,
) -> Optional[tuple[int, str]]:
    """Return the severity level/name for a need debt score, if any."""

    tuning = tuning or load_need_tuning()
    normalized = normalize_need_type(need_type)
    thresholds = tuning.severity_thresholds[normalized]
    for level, name in NEED_SEVERITY_LEVELS:
        if debt_score >= thresholds[name]:
            return level, name
    return None


def severity_tag_for_debt(
    need_type: str,
    debt_score: float,
    *,
    tuning: Optional[NeedTuning] = None,
) -> Optional[str]:
    """Return the registered severity tag for a need debt score, if any."""

    normalized = normalize_need_type(need_type)
    severity = severity_for_debt(normalized, debt_score, tuning=tuning)
    if severity is None:
        return None
    level, name = severity
    return f"{NEED_SEVERITY_PREFIX[normalized]}_{level}_{name}"


def severity_tags_for_need(need_type: str) -> tuple[str, ...]:
    """Return all severity tags in the mutex track for a need."""

    normalized = normalize_need_type(need_type)
    prefix = NEED_SEVERITY_PREFIX[normalized]
    return tuple(
        f"{prefix}_{level}_{name}" for level, name in reversed(NEED_SEVERITY_LEVELS)
    )
