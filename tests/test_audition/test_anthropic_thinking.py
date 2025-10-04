"""Tests for Anthropic extended thinking plumbing."""

import types

import pytest

from scripts.api_anthropic import AnthropicProvider, LLMResponse


class _FakeMessages:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        usage = types.SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        content = [types.SimpleNamespace(text="ok")]
        return types.SimpleNamespace(content=content, usage=usage)


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


@pytest.fixture(autouse=True)
def patch_initialize(monkeypatch):
    monkeypatch.setattr(AnthropicProvider, "initialize", lambda self: None)
    yield


def _make_provider(**kwargs) -> AnthropicProvider:
    provider = AnthropicProvider(
        api_key="test",
        model="claude-sonnet-4-5-20250929",
        temperature=0.8,
        max_tokens=4000,
        system_prompt="system",
        **kwargs,
    )
    provider.client = _FakeClient()
    return provider


def test_thinking_enabled_uses_extra_body():
    provider = _make_provider(thinking_enabled=True, thinking_budget_tokens=32000)

    response = provider.get_completion("hello", enable_cache=False)

    assert isinstance(response, LLMResponse)
    kwargs = provider.client.messages.kwargs
    assert kwargs is not None
    assert kwargs["extra_body"] == {
        "thinking": {"type": "enabled", "budget_tokens": 32000}
    }


def test_thinking_disabled_omits_extra_body():
    provider = _make_provider(thinking_enabled=False)

    provider.get_completion("hello", enable_cache=False)

    kwargs = provider.client.messages.kwargs
    assert kwargs is not None
    assert "extra_body" not in kwargs
