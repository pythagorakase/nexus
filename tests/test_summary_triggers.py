from __future__ import annotations


from typing import Optional

import pytest

from nexus.api.summary_triggers import (
    SummaryTask,
    plan_summary_tasks,
)
from tests.model_registry_helpers import registry_model


def test_plan_summary_tasks():
    assert plan_summary_tasks("continue", 5, 1) == []

    new_ep = plan_summary_tasks("new_episode", 5, 1)
    assert new_ep == [SummaryTask(kind="episode", season=5, episode=1)]

    new_season = plan_summary_tasks("new_season", 5, 13)
    assert new_season == [
        SummaryTask(kind="episode", season=5, episode=13),
        SummaryTask(kind="season", season=5),
    ]


class _FakeDB:
    """Legacy constructor-only fixture for provider configuration contracts."""

    def __init__(self, *args):
        pass


def test_summary_generator_routes_test_model_to_registry_base_url():
    """The TEST provider's Responses client uses its registered endpoint."""
    from nexus.config import load_settings
    from scripts.summarize_narrative import SummaryGenerator

    generator = SummaryGenerator(model="TEST", db_manager=_FakeDB({}, {}))
    expected = load_settings().global_.model.api_models["test"].base_url
    provider = generator._provider_for_mode("episode")

    assert str(provider.client.base_url).rstrip("/") == expected


def test_summary_token_check_uses_configured_request_budget():
    """The retired legacy TPM dictionary is not a prerequisite for summaries."""
    from scripts.summarize_narrative import SummaryGenerator

    generator = SummaryGenerator(model="TEST", db_manager=_FakeDB({}, {}))

    assert generator._token_check("A short narrative interval.", "episode") is True


@pytest.mark.parametrize(
    "model_ref,expected_provider,expected_transport",
    [
        (registry_model("openai"), "openai", "responses"),
        (registry_model("anthropic"), "anthropic", None),
        (registry_model("local"), "openai", "chat_completions"),
    ],
)
def test_summary_generator_uses_registry_native_provider_contract(
    monkeypatch,
    model_ref: str,
    expected_provider: str,
    expected_transport: Optional[str],
):
    """OpenAI, Anthropic, and local summaries use their real provider wrappers."""
    from nexus.config import load_settings, resolve_model_ref
    from scripts.api_anthropic import AnthropicProvider
    from scripts.api_openai import OpenAIProvider
    from scripts.summarize_narrative import SummaryGenerator

    monkeypatch.setattr(OpenAIProvider, "_get_api_key", lambda self: "test-openai")
    monkeypatch.setattr(
        AnthropicProvider,
        "_get_api_key",
        lambda self: "test-anthropic",
    )

    generator = SummaryGenerator(
        model=resolve_model_ref(model_ref),
        db_manager=_FakeDB({}, {}),
    )
    provider = generator._provider_for_mode("season")
    settings = load_settings().summaries

    assert provider.provider_name == expected_provider
    assert provider.system_prompt.startswith("You are a narrative continuity AI")
    assert generator._provider_for_mode("season") is provider
    if isinstance(provider, OpenAIProvider):
        assert provider.structured_transport == expected_transport
        assert provider.max_output_tokens == settings.season_max_output_tokens
    else:
        assert isinstance(provider, AnthropicProvider)
        assert expected_transport is None
        assert provider.max_tokens == settings.season_max_output_tokens
        if generator.is_reasoning_model:
            assert provider.reasoning_effort == settings.reasoning_effort
        else:
            assert provider.reasoning_effort is None
            assert provider.temperature == settings.temperature
