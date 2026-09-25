"""Pydantic-AI wiring regressions."""

from pathlib import Path

import pytest
import tomlkit
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.profiles.anthropic import anthropic_model_profile

from nexus.api import pydantic_ai_utils
from nexus.api.native_structured_output import AnthropicJsonSchemaTransformer
from nexus.config import resolve_model_ref
from tests.model_registry_helpers import registry_model


class _LegacyAnthropicProviderStub:
    """Avoid Keychain access while preserving the provider's API-key contract."""

    def __init__(self, model):
        self.api_key = "test-api-key"

    def credential(self):
        return self.api_key


def test_build_pydantic_ai_model_requires_base_url_for_non_native(monkeypatch):
    """Non-native providers must resolve to an OpenAI-compatible endpoint."""

    monkeypatch.setattr(
        pydantic_ai_utils, "get_provider_for_model", lambda model: "local"
    )
    monkeypatch.setattr(
        pydantic_ai_utils, "get_openai_compatible_endpoint", lambda model: None
    )

    with pytest.raises(ValueError, match="No base_url registry entry"):
        pydantic_ai_utils.build_pydantic_ai_model(registry_model("test"))


def test_build_anthropic_model_applies_native_structured_output_override(monkeypatch):
    """An explicit registry flag replaces only upstream capability detection."""
    model_name = "claude-opus-4-8"
    upstream_profile = anthropic_model_profile(model_name)
    monkeypatch.setattr(
        pydantic_ai_utils,
        "LegacyAnthropicProvider",
        _LegacyAnthropicProviderStub,
    )

    model = pydantic_ai_utils.build_pydantic_ai_model(model_name)

    assert isinstance(model, AnthropicModel)
    assert model.profile.supports_json_schema_output is True
    assert model.profile.json_schema_transformer is AnthropicJsonSchemaTransformer
    assert model.profile.thinking_tags == upstream_profile.thinking_tags


def test_build_anthropic_model_without_override_omits_profile(monkeypatch):
    """A flag-less entry keeps the existing upstream construction path exactly."""
    captured = {}

    class RecordingAnthropicModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        pydantic_ai_utils, "get_provider_for_model", lambda model: "anthropic"
    )
    monkeypatch.setattr(
        pydantic_ai_utils,
        "get_native_structured_output_override",
        lambda model: None,
    )
    monkeypatch.setattr(
        pydantic_ai_utils,
        "LegacyAnthropicProvider",
        _LegacyAnthropicProviderStub,
    )
    monkeypatch.setattr(pydantic_ai_utils, "AnthropicModel", RecordingAnthropicModel)

    pydantic_ai_utils.build_pydantic_ai_model(registry_model("anthropic"))

    assert set(captured) == {"model_name", "provider"}


@pytest.fixture
def test_model_with_local_transport(tmp_path, monkeypatch):
    """Exercise local registry capabilities without creating a non-TEST client."""
    doc = tomlkit.parse(Path("nexus.toml").read_text())
    providers = doc["global"]["model"]["api_models"]
    for field in ("structured_transport", "request_timeout_seconds"):
        providers["test"][field] = providers["local"][field]
    path = tmp_path / "test-local-transport.toml"
    path.write_text(tomlkit.dumps(doc))
    monkeypatch.setenv("NEXUS_RUNTIME_CONFIG", str(path))
    return registry_model("test")


def test_build_pydantic_ai_model_uses_chat_model_for_local(
    test_model_with_local_transport,
):
    """Chat-transport endpoints use pydantic-ai's Chat Completions model."""
    model = pydantic_ai_utils.build_pydantic_ai_model(
        resolve_model_ref(test_model_with_local_transport)
    )

    assert isinstance(model, OpenAIChatModel)


def test_build_pydantic_ai_model_applies_registry_timeout_for_local(
    test_model_with_local_transport,
):
    """The registry request_timeout_seconds reaches the pydantic-ai client.

    The wizard chat flow builds its model here; without this, picking the
    local model for the wizard would inherit the OpenAI SDK's 600s default
    and time out on the ~17-min local grammar compile.
    """
    model = pydantic_ai_utils.build_pydantic_ai_model(
        resolve_model_ref(test_model_with_local_transport)
    )

    expected = pydantic_ai_utils.get_openai_compatible_endpoint(
        resolve_model_ref(test_model_with_local_transport)
    )["request_timeout_seconds"]
    assert expected is not None
    assert model.client.timeout == expected


def test_build_pydantic_ai_model_keeps_test_on_responses():
    """The TEST mock retains the default pydantic-ai Responses model."""
    model = pydantic_ai_utils.build_pydantic_ai_model(
        resolve_model_ref(registry_model("test"))
    )

    assert isinstance(model, OpenAIResponsesModel)
