"""Tests for Orrery configuration loading."""

from nexus.config import load_settings
from nexus.config.settings_models import OrreryBleedSettings


def test_orrery_settings_resolve_model_reference() -> None:
    """Orrery narration config resolves provider role references at load time."""

    settings = load_settings("nexus.toml")

    assert settings.orrery is not None
    assert settings.orrery.enabled is False
    assert settings.orrery.binding.window_chunks == 30
    expected_model = settings.global_.model.api_models["anthropic"].roles["default"]
    assert settings.orrery.narration.model_ref == expected_model
    assert settings.orrery.promote.provider == "local"
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
