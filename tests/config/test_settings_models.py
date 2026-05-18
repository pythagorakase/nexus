"""Tests for configuration schema validation."""

import pytest
from pydantic import ValidationError

from nexus.config.settings_models import APIModelEntry, ModelConfig, ProviderModels


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
