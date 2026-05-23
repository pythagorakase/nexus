"""Tests for Orrery configuration loading."""

import pytest
from pydantic import ValidationError

from nexus.config import load_settings
from nexus.api.new_story_schemas import Genre
from nexus.config.settings_models import (
    OrreryBleedSettings,
    OrreryPromoteSettings,
    OrreryRetrogradeWeirdGenreBands,
    OrreryRetrogradeWeirdSettings,
)


def test_orrery_settings_resolve_model_reference() -> None:
    """Orrery narration config resolves provider role references at load time."""

    settings = load_settings("nexus.toml")

    assert settings.orrery is not None
    assert settings.orrery.enabled is False
    assert settings.orrery.binding.window_chunks == 30
    expected_model = settings.global_.model.api_models["anthropic"].roles["default"]
    assert settings.orrery.narration.model_ref == expected_model
    assert settings.orrery.promote.provider is None
    assert settings.orrery.promote.priority_threshold == 50.0
    assert settings.orrery.promote.magnitude_threshold == 0.5
    assert settings.orrery.promote.perceptual_summary_max_chars == 240
    assert settings.orrery.sunhelm.accrual_rates == {
        "sleep": 1.0,
        "hunger": 1.0,
        "thirst": 1.0,
        "socialize": 1.0,
        "intimacy": 1.0,
    }
    assert settings.orrery.sunhelm.severity_thresholds["sleep"].moderate == 30.0
    assert settings.orrery.sunhelm.severity_thresholds["socialize"].severe == 168.0
    assert settings.orrery.sunhelm.severity_thresholds["intimacy"].critical == 720.0
    assert settings.orrery.sunhelm.priorities == {
        "sleep": 25,
        "thirst": 24,
        "hunger": 22,
        "socialize": 18,
        "intimacy": 16,
    }
    assert settings.orrery.sunhelm.pressure.min_severity_level == 2
    weird = settings.orrery.retrograde.weird
    assert weird.default_level == "medium"
    assert weird.dev.cli_flag == "--weird"
    assert weird.dev.min == 0.0
    assert weird.dev.max == 1.0
    assert set(weird.bands_by_genre) == {genre.value for genre in Genre}
    assert weird.bands_by_genre["cyberpunk"].medium.min == 0.36
    assert weird.bands_by_genre["historical"].medium.min == 0.12


def test_orrery_bleed_accepts_deprecated_selection_keys() -> None:
    """Old Bleed config keys should still validate but stay out of dumps."""

    settings = OrreryBleedSettings(
        latency_budget_ms=2000,
        candidate_pool_multiplier=4,
    )

    assert settings.max_candidates == 3
    dumped = settings.model_dump()
    assert "latency_budget_ms" not in dumped
    assert "candidate_pool_multiplier" not in dumped


def test_orrery_promote_accepts_deprecated_provider_key() -> None:
    """Old promotion config should validate but stay out of dumps."""

    settings = OrreryPromoteSettings(provider="local")

    assert settings.provider == "local"
    dumped = settings.model_dump()
    assert dumped["priority_threshold"] == 50.0
    assert dumped["magnitude_threshold"] == 0.5
    assert dumped["perceptual_summary_max_chars"] == 240
    assert "provider" not in dumped


def test_orrery_retrograde_weird_rejects_overlapping_bands() -> None:
    """Genre remaps must preserve low -> medium -> high ordering."""

    with pytest.raises(ValidationError, match="low <= medium <= high"):
        OrreryRetrogradeWeirdGenreBands(
            low={"min": 0.0, "max": 0.5},
            medium={"min": 0.4, "max": 0.7},
            high={"min": 0.7, "max": 1.0},
        )


def test_orrery_retrograde_weird_rejects_bands_outside_dev_range() -> None:
    """Per-genre raw bands must stay within the configured dev float surface."""

    with pytest.raises(ValidationError, match="within the dev raw range"):
        OrreryRetrogradeWeirdSettings(
            dev={"cli_flag": "--weird", "min": 0.2, "max": 0.8, "default": 0.5},
            bands_by_genre={
                "fantasy": {
                    "low": {"min": 0.1, "max": 0.2},
                    "medium": {"min": 0.2, "max": 0.5},
                    "high": {"min": 0.5, "max": 0.8},
                }
            },
        )
