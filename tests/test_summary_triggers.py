from __future__ import annotations


from typing import Optional

import pytest

from nexus.api.summary_triggers import (
    SummaryTask,
    plan_summary_tasks,
)
from tests.model_registry_helpers import registry_model


def incomplete_summary_response(reason="max_output_tokens"):
    """Build the SDK response shape seen in the paid truncation proof."""
    from openai.types.responses import Response

    return Response.model_validate(
        {
            "id": "resp-summary-truncated",
            "object": "response",
            "created_at": 0,
            "model": "TEST",
            "status": "incomplete",
            "incomplete_details": {"reason": reason},
            "error": None,
            "instructions": None,
            "metadata": {},
            "parallel_tool_calls": False,
            "tools": [],
            "tool_choice": "auto",
            "temperature": None,
            "top_p": None,
            "output": [
                {
                    "id": "msg-summary-truncated",
                    "type": "message",
                    "role": "assistant",
                    "status": "incomplete",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"summary": "unfinished',
                            "annotations": [],
                        }
                    ],
                }
            ],
            "usage": {
                "input_tokens": 44386,
                "input_tokens_details": {"cached_tokens": 44383},
                "output_tokens": 2500,
                "output_tokens_details": {"reasoning_tokens": 264},
                "total_tokens": 46886,
            },
        }
    )


@pytest.mark.parametrize("mode", ["episode", "season"])
@pytest.mark.parametrize("reason", ["max_output_tokens", "content_filter"])
def test_summary_incomplete_response_is_terminal_before_parsing(mode, reason):
    """TEST has no incomplete mode; classify an actual SDK response shape."""
    from nexus.api.summary_errors import SummaryOutputTruncated
    from nexus.config import load_settings
    from scripts.summarize_narrative import SummaryGenerator

    generator = SummaryGenerator(model="TEST", db_manager=_FakeDB())
    provider = generator._provider_for_mode(mode)
    response = incomplete_summary_response(reason)
    allowance = getattr(load_settings().summaries, f"{mode}_max_output_tokens")
    try:
        with pytest.raises(SummaryOutputTruncated) as caught:
            provider.response_check(response)
        message = str(caught.value)
        assert f"{mode} summary incomplete" in message
        assert f"configured allowance={allowance}" in message
        assert f"incomplete_details.reason={reason}" in message
        for count in (44386, 44383, 2500, 264, 46886):
            assert str(count) in message
        # The checker permits completed responses; parsing remains downstream.
        response.status = "completed"
        provider.response_check(response)
    finally:
        provider.client.close()


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


def test_summary_token_check_uses_registry_window():
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


def truncated_chat_summary_response(content='{"summary": "unfinished'):
    """Build a validated SDK Chat result; TEST cannot emit finish_reason=length."""
    from openai.types.chat import ChatCompletion

    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-summary-truncated",
            "object": "chat.completion",
            "created": 0,
            "model": "TEST",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 80,
                "total_tokens": 180,
                "prompt_tokens_details": {"cached_tokens": 20},
                "completion_tokens_details": {"reasoning_tokens": 10},
            },
        }
    )


@pytest.mark.parametrize("mode", ["episode", "season"])
@pytest.mark.parametrize(
    "content", ['{"summary": "unfinished', '{"summary": "valid JSON"}']
)
def test_summary_chat_length_is_terminal_before_parsing(mode, content):
    """Even syntactically valid truncated JSON must never be accepted."""
    from nexus.api.summary_errors import SummaryOutputTruncated
    from scripts.summarize_narrative import SummaryGenerator

    generator = SummaryGenerator(model="TEST", db_manager=_FakeDB())
    provider = generator._provider_for_mode(mode)
    response = truncated_chat_summary_response(content)
    try:
        with pytest.raises(SummaryOutputTruncated) as caught:
            provider.response_check(response)
        message = str(caught.value)
        assert f"{mode} summary incomplete" in message
        assert f"configured allowance={provider.max_output_tokens}" in message
        assert "finish_reason=length" in message
        for count in (100, 80, 180, 20, 10):
            assert str(count) in message
        response.choices[0].finish_reason = "stop"
        provider.response_check(response)
    finally:
        provider.client.close()
