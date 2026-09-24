"""Real network clients are guarded; offline request construction remains usable."""

import os
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

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
        (OpenRouterProvider, "openrouter"),
        (OpenAIProvider, "local"),
    ],
)
def test_non_test_provider_is_forbidden(monkeypatch, wrapper, registry_provider):
    """Paid and local clients are blocked even with an explicit API key."""
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    settings = load_settings()
    model = settings.global_.model.api_models[registry_provider].models[0].id
    instance = wrapper(model=model, api_key="unused-offline")
    assert instance._client is None
    with pytest.raises(
        ProviderForbiddenInTests, match="NEXUS_TEST_PROVIDER_ONLY=1"
    ) as exc:
        _ = instance.client
    assert model in str(exc.value)
    assert instance._client is None


@pytest.mark.parametrize(
    "wrapper", [OpenAIProvider, AnthropicProvider, OpenRouterProvider]
)
@pytest.mark.parametrize("guard", ["0", "1"])
def test_unregistered_model_keeps_registry_error(monkeypatch, wrapper, guard):
    """Registry validation precedes client creation with or without the toggle."""
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", guard)
    with pytest.raises(ValueError, match=r"global.model.api_models"):
        wrapper(model="unregistered-814", api_key="unused-offline")


@pytest.mark.parametrize(
    "wrapper,registry_provider",
    [(OpenAIProvider, "openai"), (AnthropicProvider, "anthropic")],
)
def test_fake_client_allows_request_construction(
    monkeypatch, wrapper, registry_provider
):
    """Supplying an offline client does not attempt guarded SDK creation."""
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    settings = load_settings()
    model = settings.global_.model.api_models[registry_provider].models[0].id
    instance = wrapper(model=model)
    assert instance._client is None
    assert instance.api_key is None
    fake = SimpleNamespace()
    instance.client = fake

    class Output(BaseModel):
        text: str

    params = instance._build_native_structured_request_params("test", Output)
    assert params["model"] == model
    assert instance.client is fake
    assert instance.api_key is None


def test_openrouter_accepts_supplied_client(monkeypatch):
    """The legacy router wrapper also leaves explicitly supplied clients alone."""
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    model = load_settings().global_.model.api_models["openrouter"].models[0].id
    instance = OpenRouterProvider(model=model)
    fake = SimpleNamespace()
    instance.client = fake
    assert instance.client is fake
    assert instance.api_key is None


def test_test_provider_initializes_under_guard(monkeypatch):
    """The real TEST provider client can be constructed without a network call."""
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    provider = OpenAIProvider(
        model="TEST", api_key="unused-offline", base_url="http://127.0.0.1:1"
    )
    assert provider.model == "TEST"
    assert provider._client is None
    client = provider.client
    assert provider.client is client
    client.close()


def test_session_defaults_to_test_provider_only():
    """The session guard is inherited by all test children unless opted into live."""
    if os.environ.get("NEXUS_RUN_LIVE_LLM") != "1":
        assert os.environ["NEXUS_TEST_PROVIDER_ONLY"] == "1"
