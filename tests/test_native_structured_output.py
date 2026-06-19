"""Tests for provider-native structured output request construction."""

from __future__ import annotations

from types import SimpleNamespace

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
)
from nexus.api.native_structured_output import (
    anthropic_output_config,
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
    assert "authorial_directives" not in schema["required"]
    assert "authorial_directives" not in schema["properties"]


def test_anthropic_output_format_uses_native_json_schema_shape() -> None:
    """Anthropic receives a schema format and leaves validation to Pydantic."""

    output_format = anthropic_output_format(StorytellerResponseExtended)

    assert output_format["type"] == "json_schema"
    schema = output_format["schema"]
    assert schema["additionalProperties"] is False
    assert "state_updates" in schema["required"]
    assert not _contains_key(schema, "minLength")
    assert not _contains_key(schema, "maximum")


def test_anthropic_output_config_wraps_native_schema_format() -> None:
    """Anthropic Messages receives structured output through output_config.format."""

    output_config = anthropic_output_config(StorytellerResponseBootstrap)

    assert output_config["format"]["type"] == "json_schema"
    assert output_config["format"]["schema"]["additionalProperties"] is False


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


def test_openai_provider_accepts_native_text_format_override() -> None:
    """Runtime-mutated schemas ride text.format and still parse to Pydantic."""

    expected = _bootstrap_response()
    captured = {}
    text_format = {
        "type": "json_schema",
        "name": "RuntimeBootstrap",
        "strict": True,
        "schema": StorytellerResponseBootstrap.model_json_schema(),
    }

    class FakeResponses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_parsed=None,
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

    parsed, _llm_response = provider.get_structured_completion(
        "Prompt", StorytellerResponseBootstrap, text_format=text_format
    )

    assert parsed == expected
    assert captured["text"]["format"] is text_format
    assert "text_format" not in captured


def test_openai_base_url_falls_back_to_chat_response_format() -> None:
    """Local OpenAI-compatible servers may reject Responses json_schema format."""

    expected = _bootstrap_response()
    captured = {"responses_called": False}
    text_format = openai_response_text_format(StorytellerResponseBootstrap)

    class UnsupportedJsonSchema(Exception):
        status_code = 422

        def __str__(self) -> str:
            return "Input should be 'text' or 'json_object'; " "input: 'json_schema'"

    class FakeResponses:
        def parse(self, **kwargs):
            captured["responses_called"] = True
            captured["responses_kwargs"] = kwargs
            raise UnsupportedJsonSchema()

    class FakeChatCompletions:
        def create(self, **kwargs):
            captured["chat_kwargs"] = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=expected.model_dump_json())
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=55, completion_tokens=66),
            )

    provider = OpenAIProvider(
        model="local-test-model",
        api_key="test-key",
        base_url="http://127.0.0.1:8012/v1",
        system_prompt="System prompt",
        max_output_tokens=1234,
    )
    provider.client = SimpleNamespace(
        responses=FakeResponses(),
        chat=SimpleNamespace(completions=FakeChatCompletions()),
    )

    parsed, llm_response = provider.get_structured_completion(
        "Prompt", StorytellerResponseBootstrap, text_format=text_format
    )

    assert captured["responses_called"] is True
    assert parsed == expected
    assert llm_response.input_tokens == 55
    assert llm_response.output_tokens == 66
    chat_kwargs = captured["chat_kwargs"]
    assert chat_kwargs["messages"][0] == {"role": "system", "content": "System prompt"}
    assert chat_kwargs["max_tokens"] == 1234
    assert chat_kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": text_format["name"],
            "schema": text_format["schema"],
            "strict": True,
        },
    }


def test_anthropic_provider_uses_native_output_format() -> None:
    """Anthropic provider should call beta Messages with output_config.format."""

    expected = _bootstrap_response()
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=expected.model_dump_json())],
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
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert (
        captured["output_config"]["format"]["schema"]["additionalProperties"] is False
    )
    assert "output_format" not in captured
    assert "tools" not in captured
    assert captured["system"] == "System prompt"
    assert captured["max_tokens"] == 5678


def test_anthropic_provider_accepts_native_output_config_override() -> None:
    expected = _bootstrap_response()
    captured = {}
    output_config = {
        "format": {
            "type": "json_schema",
            "schema": StorytellerResponseBootstrap.model_json_schema(),
        }
    }

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=expected.model_dump_json())],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        system_prompt="System prompt",
        max_tokens=5678,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, _llm_response = provider.get_structured_completion(
        "Prompt", StorytellerResponseBootstrap, output_config=output_config
    )

    assert parsed == expected
    assert captured["output_config"] is output_config
    assert "output_format" not in captured


def test_anthropic_provider_wraps_legacy_output_format_override() -> None:
    expected = _bootstrap_response()
    captured = {}
    output_format = {
        "type": "json_schema",
        "schema": StorytellerResponseBootstrap.model_json_schema(),
    }

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=expected.model_dump_json())],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        system_prompt="System prompt",
        max_tokens=5678,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, _llm_response = provider.get_structured_completion(
        "Prompt", StorytellerResponseBootstrap, output_format=output_format
    )

    assert parsed == expected
    assert captured["output_config"] == {"format": output_format}
    assert "output_format" not in captured
