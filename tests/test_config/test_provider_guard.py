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


@pytest.fixture(autouse=True)
def isolated_secret_cache():
    """Environment credential cases must not share the process secret cache."""
    from nexus.util.secret_manager import get_secret

    get_secret.cache_clear()
    try:
        yield
    finally:
        get_secret.cache_clear()


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


@pytest.mark.parametrize(
    "parameter,value",
    [
        ("reasoning_effort", "low"),
        ("thinking_budget_tokens", 1024),
        ("min_p", 0.1),
        ("repetition_penalty", 1.1),
    ],
)
def test_openrouter_direct_http_is_guarded(monkeypatch, parameter, value):
    """Every non-SDK route stops before credentials or requests.post."""
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    model = load_settings().global_.model.api_models["openrouter"].models[0].id
    instance = OpenRouterProvider(model=model, **{parameter: value})
    with pytest.raises(ProviderForbiddenInTests, match=model):
        instance.get_completion("guard proof")
    assert instance._client is None
    assert instance.api_key is None


@pytest.mark.parametrize(
    "wrapper,registry_provider",
    [
        (OpenAIProvider, "openai"),
        (AnthropicProvider, "anthropic"),
        (OpenRouterProvider, "openrouter"),
    ],
)
def test_guarded_credential_loads_once_and_rechecks_guard(
    monkeypatch, wrapper, registry_provider
):
    """Credential consumers load the real env path once and cannot bypass guard."""
    monkeypatch.delenv("NEXUS_TEST_PROVIDER_ONLY", raising=False)
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    env_name = f"{registry_provider.upper()}_API_KEY"
    monkeypatch.setenv(env_name, "dummy-first")
    model = load_settings().global_.model.api_models[registry_provider].models[0].id
    instance = wrapper(model=model)
    assert instance.credential() == "dummy-first"
    from nexus.util.secret_manager import get_secret

    get_secret.cache_clear()
    monkeypatch.setenv(env_name, "dummy-second")
    assert instance.credential() == "dummy-first"
    assert instance._client is None
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    with pytest.raises(ProviderForbiddenInTests):
        instance.credential()
    assert instance._client is None


@pytest.mark.parametrize(
    "wrapper,registry_provider",
    [
        (OpenAIProvider, "openai"),
        (AnthropicProvider, "anthropic"),
        (OpenRouterProvider, "openrouter"),
    ],
)
def test_missing_credential_remains_loud(monkeypatch, wrapper, registry_provider):
    """No credential source raises the existing error before SDK creation."""
    from nexus.util.secret_manager import MissingSecretError

    monkeypatch.delenv("NEXUS_TEST_PROVIDER_ONLY", raising=False)
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    monkeypatch.delenv(f"{registry_provider.upper()}_API_KEY", raising=False)
    model = load_settings().global_.model.api_models[registry_provider].models[0].id
    instance = wrapper(model=model)
    with pytest.raises(MissingSecretError, match="is not set"):
        _ = instance.client
    assert instance._client is None
    assert instance.api_key is None


@pytest.mark.parametrize(
    "consumer",
    [
        "conversations",
        "pydantic_openai",
        "pydantic_anthropic",
        "pydantic_local",
        "pydantic_openrouter",
    ],
)
def test_consumer_client_construction_is_guarded(monkeypatch, consumer):
    """Dummy credentials cannot authorize an independent consumer SDK client."""
    from nexus.api.conversations import ConversationsClient
    from nexus.api.pydantic_ai_utils import build_pydantic_ai_model_with_provider

    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    monkeypatch.setenv("NEXUS_KEYRING_DISABLE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-anthropic")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-openrouter")
    registry_provider = (
        "openai" if consumer == "conversations" else consumer.removeprefix("pydantic_")
    )
    model = load_settings().global_.model.api_models[registry_provider].models[0].id
    build = (
        ConversationsClient
        if consumer == "conversations"
        else build_pydantic_ai_model_with_provider
    )
    with pytest.raises(ProviderForbiddenInTests, match="NEXUS_TEST_PROVIDER_ONLY=1"):
        build(model)


def test_anthropic_token_counter_cannot_swallow_guard(monkeypatch):
    """Token counting must not downgrade a forbidden network call to estimation."""
    monkeypatch.setenv("NEXUS_TEST_PROVIDER_ONLY", "1")
    model = load_settings().global_.model.api_models["anthropic"].models[0].id
    instance = AnthropicProvider(model=model)
    with pytest.raises(ProviderForbiddenInTests):
        instance.count_tokens("guard proof")
    assert instance._client is None
