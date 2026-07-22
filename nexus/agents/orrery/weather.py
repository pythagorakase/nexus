"""Deterministic per-region weather derived from the story clock.

For a configured climate rotation, the weather at ``zone_id`` and
``world_time`` is::

    sequence[(hours_since_epoch // period_hours + zone_id) % len(sequence)]

``hours_since_epoch`` is the floor of the UTC timestamp divided by 3,600.
The implementation uses integer arithmetic only.  The zone-id phase offset
allows neighboring regions to differ without storing mutable weather state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


WEATHER_VALUES = frozenset({"clear", "rain", "fog", "snow", "warm"})


@dataclass(frozen=True, slots=True)
class WeatherContext:
    """Runtime inputs needed to resolve one slot's local weather."""

    settings: Any
    climate_name: str
    location_zones: Mapping[int, int]
    anchor_place_id: Optional[int]
    scene_weather: Optional[str]


def _setting(settings: Any, name: str) -> Any:
    if isinstance(settings, Mapping):
        return settings[name]
    return getattr(settings, name)


def classify_weather(raw_weather: str) -> str:
    """Bucket a story-seed weather description into the closed vocabulary."""

    weather = raw_weather.lower()
    # Snow compounds must win before the generic storm/thunder tokens so
    # ``snowstorm`` and ``thundersnow`` select the cold climate.
    if "snow" in weather:
        return "snow"
    if any(token in weather for token in ("rain", "sleet", "storm", "thunder")):
        return "rain"
    if "fog" in weather:
        return "fog"
    return "clear"


def climate_for_seed(raw_weather: str, settings: Any) -> str:
    """Return the configured climate selected by the classified story seed."""

    classification = classify_weather(raw_weather)
    seed_climates = _setting(settings, "seed_climates")
    return str(seed_climates[classification])


def derive_weather(zone_id: int, world_time: datetime, settings: Any) -> str:
    """Derive one zone's weather from its climate rotation and world time.

    ``settings`` is a :class:`WeatherContext`, or a mapping/object containing
    ``period_hours``, ``climates``, and ``climate_name``.
    """

    source = settings.settings if isinstance(settings, WeatherContext) else settings
    climate_name = (
        settings.climate_name
        if isinstance(settings, WeatherContext)
        else _setting(settings, "climate_name")
    )
    period_hours = int(_setting(source, "period_hours"))
    climates = _setting(source, "climates")
    sequence = climates[climate_name]

    if world_time.tzinfo is None:
        normalized = world_time.replace(tzinfo=timezone.utc)
    else:
        normalized = world_time.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elapsed = normalized - epoch
    elapsed_microseconds = (
        elapsed.days * 86_400_000_000
        + elapsed.seconds * 1_000_000
        + elapsed.microseconds
    )
    hours_since_epoch = elapsed_microseconds // 3_600_000_000
    position = (hours_since_epoch // period_hours + int(zone_id)) % len(sequence)
    return str(sequence[position])


def weather_at(
    place_id: int,
    world_time: datetime,
    state: WeatherContext,
) -> Optional[str]:
    """Resolve local weather, honoring an anchor-scene override first."""

    if place_id == state.anchor_place_id and state.scene_weather is not None:
        return state.scene_weather
    zone_id = state.location_zones.get(place_id)
    if zone_id is None:
        return None
    return derive_weather(zone_id, world_time, state)
