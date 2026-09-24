"""Real provider construction must fail before network client initialization."""

import os

import pytest

from nexus.config import load_settings
from nexus.config.provider_guard import ProviderForbiddenInTests
from scripts.api_anthropic import AnthropicProvider
from scripts.api_openai import OpenAIProvider
from scripts.api_openrouter import OpenRouterProvider


@pytest.mark.parametrize(
    "wrapper,registry_provider",
    [
        (OpenAIProvider, "openai"),
        (AnthropicProvider, "anthropic"),
        (OpenRouterProvider, "openai"),
        (OpenAIProvider, "local"),
    ],
)
def test_non_test_provider_is_forbidden(monkeypatch, wrapper, registry_provider):
    """Paid and local registry models are blocked even with an explicit API key."""
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    settings = load_settings()
    if registry_provider == "local":
        model = settings.local_models.model
    else:
        model = settings.global_.model.api_models[registry_provider].models[0].id
    instance = wrapper.__new__(wrapper)
    with pytest.raises(
        ProviderForbiddenInTests, match="NEXUS_TEST_PROVIDER_ONLY=1"
    ) as exc:
        instance.__init__(model=model, api_key="unused-offline")
    assert model in str(exc.value)
    assert not hasattr(instance, "client")


def test_test_provider_initializes_under_guard(monkeypatch):
    """The real TEST provider client can be constructed without a network call."""
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    provider = OpenAIProvider(
        model="TEST", api_key="unused-offline", base_url="http://127.0.0.1:1"
    )
    assert provider.model == "TEST"
    provider.client.close()


def test_session_defaults_to_test_provider_only():
    """The session guard is inherited by all test children unless opted into live."""
    if os.environ.get("NEXUS_RUN_LIVE_LLM") != "1":
        assert os.environ["NEXUS_TEST_PROVIDER_ONLY"] == "1"
