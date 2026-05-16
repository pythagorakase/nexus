"""Tests for Orrery configuration loading."""

from nexus.config import load_settings


def test_orrery_settings_resolve_model_reference() -> None:
    """Orrery narration config resolves provider role references at load time."""

    settings = load_settings("nexus.toml")

    assert settings.orrery is not None
    assert settings.orrery.enabled is False
    assert settings.orrery.binding.window_chunks == 30
    assert settings.orrery.narration.model_ref == "claude-sonnet-4-6"
    assert settings.orrery.bleed.latency_budget_ms == 2000
    assert settings.orrery.promote.provider == "local"
