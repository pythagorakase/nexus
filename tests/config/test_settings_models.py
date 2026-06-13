"""Tests for configuration schema validation."""

import tomllib

import pytest
from pydantic import ValidationError

from nexus.config import load_settings, resolve_model_ref
from nexus.config.settings_models import (
    APIModelEntry,
    ModelConfig,
    ProviderModels,
    Settings,
)


def _nexus_toml_dict() -> dict:
    with open("nexus.toml", "rb") as handle:
        return tomllib.load(handle)


def test_model_config_rejects_unknown_default_model():
    """Legacy display defaults must stay anchored to registered model IDs."""
    with pytest.raises(ValidationError, match="default_model references unknown"):
        ModelConfig(
            default_model="missing-model",
            default_slot_model="TEST",
            api_models={
                "test": ProviderModels(
                    roles={"default": "TEST"},
                    models=[APIModelEntry(id="TEST", label="TEST")],
                    base_url="http://127.0.0.1:5102/v1",
                )
            },
        )


def test_model_config_defers_role_references_to_settings_resolution():
    """ "@provider.role" defaults pass ModelConfig and resolve on the root model."""
    config = ModelConfig(
        default_model="@test.default",
        default_slot_model="TEST",
        api_models={
            "test": ProviderModels(
                roles={"default": "TEST"},
                models=[APIModelEntry(id="TEST", label="TEST")],
                base_url="http://127.0.0.1:5102/v1",
            )
        },
    )
    assert config.default_model == "@test.default"


def test_global_default_model_resolves_at_load():
    """nexus.toml's display default is a role reference resolved at load."""
    raw = _nexus_toml_dict()
    raw_default = raw["global"]["model"]["default_model"]
    assert raw_default.startswith("@"), (
        "global.model.default_model should be an @provider.role reference in "
        f"nexus.toml, found literal '{raw_default}'"
    )

    settings = load_settings("nexus.toml")
    openai_default = settings.global_.model.api_models["openai"].roles["default"]
    assert settings.global_.model.default_model == openai_default


def test_global_default_model_unknown_role_rejected():
    """An unknown role in the global display default fails Settings validation."""
    raw = _nexus_toml_dict()
    raw["global"]["model"]["default_model"] = "@openai.nonexistent_role"
    with pytest.raises(ValidationError, match="no role 'nonexistent_role'"):
        Settings(**raw)


def test_global_default_slot_model_unknown_role_rejected():
    """An unknown role in the slot default fails Settings validation too."""
    raw = _nexus_toml_dict()
    raw["global"]["model"]["default_slot_model"] = "@test.nonexistent_role"
    with pytest.raises(ValidationError, match="no role 'nonexistent_role'"):
        Settings(**raw)


def test_global_default_slot_model_role_ref_resolves_at_load():
    """A valid role ref in default_slot_model resolves to the concrete ID."""
    raw = _nexus_toml_dict()
    raw["global"]["model"]["default_slot_model"] = "@test.default"
    settings = Settings(**raw)
    test_default = settings.global_.model.api_models["test"].roles["default"]
    assert settings.global_.model.default_slot_model == test_default


def test_resolve_model_ref_resolves_roles_and_validates_literals():
    """The public resolver maps roles to concrete IDs and validates literals."""
    settings = load_settings("nexus.toml")
    anthropic_default = settings.global_.model.api_models["anthropic"].roles["default"]

    assert resolve_model_ref("@anthropic.default") == anthropic_default
    assert settings.resolve_model_ref("@anthropic.default") == anthropic_default
    # Literal registry IDs pass through unchanged.
    assert resolve_model_ref(anthropic_default) == anthropic_default

    with pytest.raises(ValueError, match="no role 'bogus'"):
        resolve_model_ref("@anthropic.bogus")
    with pytest.raises(ValueError, match="not declared"):
        resolve_model_ref("model-that-does-not-exist")


def test_ui_visible_filters_ui_model_lists_but_not_registry():
    """ui_visible = false hides a provider from UI lists, not the registry.

    The TEST mock server stays fully functional for backend/CLI callers
    (unfiltered loader calls, role resolution) while every UI-facing model
    list - /api/config/models and the settings pane metadata - omits it.
    """
    from nexus.config.loader import get_all_api_models, get_api_models_by_provider

    settings = load_settings("nexus.toml")
    assert settings.global_.model.api_models["test"].ui_visible is False
    assert settings.global_.model.api_models["anthropic"].ui_visible is True

    all_ids = {m["id"] for m in get_all_api_models()}
    ui_ids = {m["id"] for m in get_all_api_models(ui_only=True)}
    assert "TEST" in all_ids
    assert "TEST" not in ui_ids
    assert ui_ids == all_ids - {"TEST"}

    assert "test" not in get_api_models_by_provider(ui_only=True)
    assert "test" in get_api_models_by_provider()

    # Backend role resolution is untouched by UI visibility.
    assert resolve_model_ref("@test.default") == "TEST"


# =============================================================================
# Registry base_url + per-model parameter capability (#401)
# =============================================================================


def test_non_native_provider_requires_base_url():
    """Providers outside the native SDK set must declare an endpoint."""
    raw = _nexus_toml_dict()
    del raw["global"]["model"]["api_models"]["test"]["base_url"]
    with pytest.raises(ValidationError, match="must declare a base_url"):
        Settings(**raw)


def test_native_provider_rejects_base_url():
    """Native SDK providers use their own endpoints; base_url is a config error."""
    raw = _nexus_toml_dict()
    raw["global"]["model"]["api_models"]["openai"]["base_url"] = "http://x/v1"
    with pytest.raises(ValidationError, match="base_url is not allowed"):
        Settings(**raw)


def test_configured_param_rejected_when_model_declares_it_unsupported():
    """[orrery.narration] temperature on a temperature-rejecting model fails load.

    This is the #401 proving instance: the narration model resolves to a model
    whose registry entry lists 'temperature' in unsupported_params, so setting
    temperature in nexus.toml must be refused at config load, not at request
    time.
    """
    raw = _nexus_toml_dict()
    narration_model = Settings(**raw).orrery.narration.model_ref
    assert "temperature" in {
        p
        for provider in Settings(**raw).global_.model.api_models.values()
        for entry in provider.models
        if entry.id == narration_model
        for p in entry.unsupported_params
    }, f"expected nexus.toml to declare temperature unsupported for {narration_model}"

    raw["orrery"]["narration"]["temperature"] = 0.4
    with pytest.raises(ValidationError, match="declares 'temperature' unsupported"):
        Settings(**raw)


def test_configured_param_allowed_when_model_supports_it():
    """A supporting model (Sonnet 4.6) accepts a configured temperature."""
    raw = _nexus_toml_dict()
    raw["orrery"]["narration"]["model_ref"] = "claude-sonnet-4-6"
    raw["orrery"]["narration"]["temperature"] = 0.4
    settings = Settings(**raw)
    assert settings.orrery.narration.temperature == 0.4


def test_narration_temperature_unset_by_default():
    """Shipped config omits narration temperature so the param is never sent."""
    settings = load_settings("nexus.toml")
    assert settings.orrery.narration.temperature is None


def test_get_openai_compatible_endpoint_routing():
    """Registry base_url providers resolve to an endpoint; native ones do not."""
    from nexus.config import get_openai_compatible_endpoint

    settings = load_settings("nexus.toml")
    endpoint = get_openai_compatible_endpoint("TEST")
    assert endpoint == {
        "base_url": settings.global_.model.api_models["test"].base_url,
        "api_key": "nexus-local-no-key",
    }
    assert get_openai_compatible_endpoint("gpt-5.5") is None
    assert get_openai_compatible_endpoint("claude-opus-4-8") is None
    # Models absent from the registry are treated as native/legacy overrides.
    assert get_openai_compatible_endpoint("unregistered-model") is None
