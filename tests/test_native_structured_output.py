"""Tests for provider-native structured output request construction."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
)
from nexus.api.new_story_schemas import SettingCard, StorySeedSubmission, WizardResponse
from nexus.api.native_structured_output import (
    ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS,
    AnthropicJsonSchemaTransformer,
    anthropic_output_config,
    anthropic_output_format,
    anthropic_strict_tool,
    build_native_structured_provider,
    openai_response_text_format,
    strict_json_schema,
)
from nexus.config import resolve_model_ref
from scripts import api_openai
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


def _assert_object_schemas_closed(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            assert value.get("additionalProperties") is False
        for item in value.values():
            _assert_object_schemas_closed(item)
    elif isinstance(value, list):
        for item in value:
            _assert_object_schemas_closed(item)


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


def test_anthropic_json_schema_transformer_strips_constraints_recursively() -> None:
    """Constraints are stripped and objects closed through every nested shape."""
    schema = {
        "type": "object",
        "description": "Root survives",
        "properties": {
            "metadata": {
                "type": "object",
                "description": "Object property survives",
                "properties": {"enabled": {"type": "boolean"}},
            },
            "codes": {
                "type": "array",
                "minItems": 2,
                "maxItems": 5,
                "description": "Array survives",
                "items": {
                    "type": "object",
                    "description": "Item object survives",
                    "properties": {
                        "code": {
                            "type": "string",
                            "pattern": "^[A-Z]+$",
                        }
                    },
                },
            },
        },
        "$defs": {
            "Nested": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "minLength": 3,
                        "pattern": "^[a-z]+$",
                        "description": "Definition survives",
                    }
                },
            }
        },
    }

    transformed = AnthropicJsonSchemaTransformer(schema, strict=True).walk()

    assert all(
        not _contains_key(transformed, key) for key in ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS
    )
    _assert_object_schemas_closed(transformed)
    assert transformed["description"] == "Root survives"
    assert (
        transformed["properties"]["metadata"]["description"]
        == "Object property survives"
    )
    assert transformed["properties"]["codes"]["description"] == "Array survives"
    assert (
        transformed["properties"]["codes"]["items"]["description"]
        == "Item object survives"
    )
    assert (
        transformed["$defs"]["Nested"]["properties"]["name"]["description"]
        == "Definition survives"
    )


def test_anthropic_json_schema_transformer_accepts_wizard_response_schema() -> None:
    """WizardResponse's strict schema is reduced to Anthropic's supported subset."""
    schema = strict_json_schema(WizardResponse)
    assert _contains_key(schema, "minItems")
    assert _contains_key(schema, "maxItems")

    transformed = AnthropicJsonSchemaTransformer(schema, strict=True).walk()

    assert all(
        not _contains_key(transformed, key) for key in ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS
    )
    assert transformed["properties"]["choices"]["type"] == "array"
    assert transformed["properties"]["message"]["type"] == "string"


def test_anthropic_json_schema_transformer_closes_wizard_tool_schemas() -> None:
    """Setting and seed tool schemas meet Anthropic strict object requirements."""
    for schema_model in (SettingCard, StorySeedSubmission):
        transformed = AnthropicJsonSchemaTransformer(
            strict_json_schema(schema_model), strict=True
        ).walk()

        assert all(
            not _contains_key(transformed, key)
            for key in ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS
        )
        _assert_object_schemas_closed(transformed)


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


@pytest.mark.parametrize(
    ("request_timeout", "expected_timeout"),
    [(1800.0, 1800.0), (None, None)],
)
def test_openai_provider_forwards_only_configured_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
    request_timeout: float | None,
    expected_timeout: float | None,
) -> None:
    """Client construction overrides timeout only when explicitly configured."""
    captured: dict[str, object] = {}
    fake_client = SimpleNamespace()

    def fake_openai(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return fake_client

    monkeypatch.setattr(api_openai.openai, "OpenAI", fake_openai)

    provider = OpenAIProvider(
        model="local-test-model",
        api_key="test-key",
        base_url="http://127.0.0.1:1234/v1",
        request_timeout=request_timeout,
    )

    assert provider.client is fake_client
    if expected_timeout is None:
        assert "timeout" not in captured
    else:
        assert captured["timeout"] == expected_timeout


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


def test_openai_chat_transport_dispatches_without_responses_attempt() -> None:
    """Configured Chat transport bypasses Responses at method dispatch."""
    expected = (_bootstrap_response(), Mock())
    provider = build_native_structured_provider(
        model=resolve_model_ref("@lmstudio.default"),
        max_tokens=600,
        system_prompt="System prompt",
        structured_output_retries=0,
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider.structured_transport == "chat_completions"
    provider._get_structured_completion_chat_completions_sync = Mock(
        return_value=expected
    )
    provider.client.responses.parse = Mock(
        side_effect=AssertionError("Responses must not be called")
    )

    result = provider._get_structured_completion_native_sync(
        "Prompt", StorytellerResponseBootstrap
    )

    assert result == expected
    provider._get_structured_completion_chat_completions_sync.assert_called_once_with(
        "Prompt", StorytellerResponseBootstrap, text_format=None
    )
    provider.client.responses.parse.assert_not_called()


@pytest.mark.asyncio
async def test_openai_chat_transport_dispatches_async_without_responses_attempt() -> (
    None
):
    """Configured Chat transport also bypasses Responses on the async path."""
    expected = (_bootstrap_response(), Mock())
    provider = build_native_structured_provider(
        model=resolve_model_ref("@lmstudio.default"),
        max_tokens=600,
        system_prompt="System prompt",
        structured_output_retries=0,
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider.structured_transport == "chat_completions"
    provider._get_structured_completion_chat_completions_async = AsyncMock(
        return_value=expected
    )
    provider.client.responses.parse = Mock(
        side_effect=AssertionError("Responses must not be called")
    )

    result = await provider._get_structured_completion_native_async(
        "Prompt", StorytellerResponseBootstrap
    )

    assert result == expected
    provider._get_structured_completion_chat_completions_async.assert_awaited_once_with(
        "Prompt", StorytellerResponseBootstrap, text_format=None
    )
    provider.client.responses.parse.assert_not_called()


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
