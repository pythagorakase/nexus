"""Tests for Orrery configuration loading."""

from nexus.config import load_settings


def test_orrery_settings_resolve_model_reference() -> None:
    """Orrery narration config resolves provider role references at load time."""

    settings = load_settings("nexus.toml")

    assert settings.orrery is not None
    assert settings.orrery.enabled is False
    assert settings.orrery.binding.window_chunks == 30
    expected_model = settings.global_.model.api_models["anthropic"].roles["default"]
    assert settings.orrery.narration.model_ref == expected_model
    assert settings.orrery.bleed.latency_budget_ms == 2000
    assert settings.orrery.bleed.candidate_pool_multiplier == 4
    assert settings.orrery.promote.provider == "local"
