"""Pure derivation and configuration contracts for localized weather."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nexus.agents.orrery.weather import (
    climate_for_seed,
    derive_weather,
)
from nexus.config.settings_models import OrreryWeatherSettings


def _runtime(climate_name: str = "temperate") -> dict:
    settings = OrreryWeatherSettings().model_dump()
    settings["climate_name"] = climate_name
    return settings


def _alternating_runtime() -> dict:
    settings = _runtime()
    settings["climates"] = {"temperate": ["clear", "rain"]}
    return settings


def test_derivation_is_deterministic_and_adjacent_zones_can_diverge() -> None:
    instant = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    settings = _alternating_runtime()

    first = derive_weather(1, instant, settings)
    second = derive_weather(1, instant, settings)

    assert first == second
    assert derive_weather(2, instant, settings) != derive_weather(3, instant, settings)


def test_derivation_changes_only_at_period_boundaries() -> None:
    settings = _alternating_runtime()
    boundary = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)

    before = derive_weather(0, boundary - timedelta(microseconds=1), settings)
    at_boundary = derive_weather(0, boundary, settings)
    within_period = derive_weather(0, boundary + timedelta(hours=5), settings)

    assert at_boundary == within_period
    assert before != at_boundary


@pytest.mark.parametrize(
    ("seed", "expected"),
    [
        ("Hard rain over the lagoon", "lagoon_wet"),
        ("Snow under a white sky", "cold"),
        ("Dense fog at dawn", "temperate"),
        ("Clear and dry", "temperate"),
    ],
)
def test_story_seed_classification_selects_climate(seed: str, expected: str) -> None:
    assert climate_for_seed(seed, OrreryWeatherSettings()) == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"climates": {"empty": []}},
        {"climates": {"bad": ["hail"]}},
        {
            "climates": {"temperate": ["clear"]},
            "seed_climates": {
                "clear": "unknown",
                "rain": "temperate",
                "fog": "temperate",
                "snow": "temperate",
            },
        },
    ],
)
def test_invalid_weather_config_is_rejected(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        OrreryWeatherSettings(**kwargs)
