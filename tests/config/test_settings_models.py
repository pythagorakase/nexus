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
