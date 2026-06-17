"""Tests for provider-native structured output request construction."""

from __future__ import annotations

from types import SimpleNamespace

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
)
from nexus.api.native_structured_output import (
    anthropic_output_format,
    anthropic_strict_tool,
    openai_response_text_format,
)
from scripts.api_anthropic import AnthropicProvider
from scripts.api_openai import OpenAIProvider


def _bootstrap_response() -> StorytellerResponseBootstrap:
    return StorytellerResponseBootstrap(
        narrative="[TEST MODE] Native structured output.",
        choices=["Continue", "Wait"],
        authorial_directives=["Retrieve recent context."],
    )


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def test_openai_response_text_format_is_native_strict_json_schema() -> None:
    """OpenAI schema payload uses native strict text.format, not a tool."""

    text_format = openai_response_text_format(StorytellerResponseExtended)

    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True
    assert text_format["name"] == "StorytellerResponseExtended"
    schema = text_format["schema"]
    assert schema["additionalProperties"] is False
    assert "state_updates" in schema["required"]
    assert "state_updates" in schema["properties"]


def test_anthropic_output_format_uses_native_json_schema_shape() -> None:
    """Anthropic receives schema output_format and leaves validation to Pydantic."""

    output_format = anthropic_output_format(StorytellerResponseExtended)

    assert output_format["type"] == "json_schema"
    schema = output_format["schema"]
    assert schema["additionalProperties"] is False
    assert "state_updates" in schema["required"]
    assert not _contains_key(schema, "minLength")
    assert not _contains_key(schema, "maximum")


def test_anthropic_strict_tool_helper_sets_strict_true() -> None:
    """The helper can produce strict Anthropic tool schemas when needed."""

    tool = anthropic_strict_tool(StorytellerResponseBootstrap)

    assert tool["name"] == "submit_structured_response"
    assert tool["strict"] is True
    assert tool["input_schema"]["additionalProperties"] is False


def test_openai_provider_uses_responses_parse_text_format() -> None:
    """OpenAI provider should call native parse with the Pydantic model."""

    expected = _bootstrap_response()
    captured = {}

    class FakeResponses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_parsed=expected,
                output_text=expected.model_dump_json(),
                usage=SimpleNamespace(input_tokens=11, output_tokens=22),
            )

    provider = OpenAIProvider(
        model="gpt-4.1",
        api_key="test-key",
        system_prompt="System prompt",
        max_output_tokens=1234,
    )
    provider.client = SimpleNamespace(responses=FakeResponses())

    parsed, llm_response = provider.get_structured_completion(
        "Prompt", StorytellerResponseBootstrap
    )

    assert parsed == expected
    assert llm_response.input_tokens == 11
    assert llm_response.output_tokens == 22
    assert captured["text_format"] is StorytellerResponseBootstrap
    assert "tools" not in captured
    assert captured["input"][0] == {"role": "system", "content": "System prompt"}
    assert captured["max_output_tokens"] == 1234


def test_anthropic_provider_uses_native_output_format() -> None:
    """Anthropic provider should call beta Messages with JSON schema output."""

    expected = _bootstrap_response()
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="text", text=expected.model_dump_json())
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        system_prompt="System prompt",
        max_tokens=5678,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, llm_response = provider.get_structured_completion(
        "Prompt", StorytellerResponseBootstrap
    )

    assert parsed == expected
    assert llm_response.input_tokens == 33
    assert llm_response.output_tokens == 44
    assert captured["output_format"]["type"] == "json_schema"
    assert captured["output_format"]["schema"]["additionalProperties"] is False
    assert "tools" not in captured
    assert captured["system"] == "System prompt"
    assert captured["max_tokens"] == 5678
