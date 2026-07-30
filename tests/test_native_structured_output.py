"""Tests for provider-native structured output request construction."""

from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any, Callable, cast, Literal
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelRetry

from nexus.agents.logon.apex_schema import (
    StorytellerResponseBootstrap,
    StorytellerResponseExtended,
)
from nexus.agents.logon.skald_wire import (
    SkaldGaiaWire,
    SkaldTurnWire,
    SkaldWriterWire,
    skald_gaia_lenient_schema,
    skald_wire_lenient_schema,
    skald_writer_lenient_schema,
)
from nexus.agents.lore.logon_utility import LogonUtility
from nexus.api.new_story_schemas import SettingCard, StorySeedSubmission, WizardResponse
from nexus.api.native_structured_output import (
    ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS,
    AnthropicJsonSchemaTransformer,
    anthropic_json_schema,
    anthropic_output_config,
    anthropic_output_format,
    anthropic_strict_tool,
    build_native_structured_provider,
    de_null_schema,
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


def _wire_response() -> SkaldTurnWire:
    return SkaldTurnWire(
        narrative="[TEST MODE] Tool-envelope structured output.",
        choices=["Continue", "Wait"],
        letter="Keep the next beat private.",
    )


def _writer_response() -> SkaldWriterWire:
    return SkaldWriterWire(
        narrative="[TEST MODE] Writer structured output.",
        choices=["Continue", "Wait"],
        letter="Keep the next beat private.",
    )


def _gaia_response() -> SkaldGaiaWire:
    return SkaldGaiaWire(letter="I will make room for it.")


def _reject_first_structured_output(
    rejection_kind: Literal["model_retry", "validation_error"],
) -> tuple[
    Callable[[Any, SkaldWriterWire], SkaldWriterWire],
    str,
    str,
    str,
]:
    """Build a one-shot validator rejection, including a private-input error."""

    sentinel = "PRIVATE-LETTER-637"
    try:
        SkaldWriterWire.model_validate(
            {
                "narrative": "N",
                "letter": sentinel,
            }
        )
    except ValidationError as exc:
        validation_error = exc
    else:
        raise AssertionError("The deliberately incomplete writer payload was valid")

    assert sentinel in str(validation_error)
    model_retry_message = "writer registry validator rejected the response"

    def validator(ctx: Any, output: SkaldWriterWire) -> SkaldWriterWire:
        if ctx.retry == 0:
            if rejection_kind == "model_retry":
                raise ModelRetry(model_retry_message)
            raise validation_error
        return output

    if rejection_kind == "model_retry":
        return validator, sentinel, "ModelRetry", model_retry_message
    return (
        validator,
        sentinel,
        "ValidationError",
        "choices: Field required (missing)",
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


def _contains_nullable_any_of(value: object) -> bool:
    if isinstance(value, dict):
        any_of = value.get("anyOf")
        if isinstance(any_of, list) and any(
            isinstance(member, dict) and member.get("type") == "null"
            for member in any_of
        ):
            return True
        return any(_contains_nullable_any_of(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_nullable_any_of(item) for item in value)
    return False


def _count_union_typed_nodes(value: object) -> int:
    if isinstance(value, dict):
        is_union = "anyOf" in value or isinstance(value.get("type"), list)
        return int(is_union) + sum(
            _count_union_typed_nodes(item) for item in value.values()
        )
    if isinstance(value, list):
        return sum(_count_union_typed_nodes(item) for item in value)
    return 0


def _assert_property_maps_are_consistent(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            assert "anyOf" not in properties, path
        required = value.get("required")
        if isinstance(required, list):
            assert isinstance(properties, dict), path
            assert set(required) <= set(properties), path
        for key, item in value.items():
            _assert_property_maps_are_consistent(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_property_maps_are_consistent(item, f"{path}[{index}]")


@pytest.mark.parametrize(
    "any_of",
    [
        [{"type": "string"}, {"type": "null"}],
        [{"type": "null"}, {"type": "string"}],
    ],
)
def test_de_null_schema_collapses_two_member_null_unions(
    any_of: list[dict[str, str]],
) -> None:
    assert de_null_schema({"anyOf": any_of}) == {"type": "string"}


def test_de_null_schema_preserves_siblings_with_member_precedence() -> None:
    schema = {
        "anyOf": [
            {
                "type": "string",
                "description": "Member description wins.",
                "title": "Member title",
            },
            {"type": "null"},
        ],
        "description": "Sibling description",
        "title": "Sibling title",
        "examples": ["kept"],
    }

    assert de_null_schema(schema) == {
        "type": "string",
        "description": "Member description wins.",
        "title": "Member title",
        "examples": ["kept"],
    }


@pytest.mark.parametrize(
    "any_of",
    [
        [{"type": "string"}, {"type": "integer"}, {"type": "null"}],
        [{"type": "string"}, {"type": "integer"}],
    ],
)
def test_de_null_schema_leaves_other_unions_intact(
    any_of: list[dict[str, str]],
) -> None:
    assert de_null_schema({"anyOf": any_of}) == {"anyOf": any_of}


def test_de_null_schema_recurses_through_nested_lists_and_dicts() -> None:
    schema = {
        "properties": {
            "entries": {
                "type": "array",
                "items": [
                    {
                        "metadata": {
                            "anyOf": [
                                {"type": "object", "additionalProperties": False},
                                {"type": "null"},
                            ]
                        }
                    }
                ],
            }
        }
    }

    transformed = de_null_schema(schema)

    assert transformed["properties"]["entries"]["items"][0]["metadata"] == {
        "type": "object",
        "additionalProperties": False,
    }


@pytest.mark.parametrize(
    "value",
    [
        None,
        3,
        "schema",
        ["mixed", None, 4],
        {"anyOf": None},
        {"anyOf": [False, {"type": "null"}], "description": "malformed"},
    ],
)
def test_de_null_schema_is_total_for_arbitrary_json_shapes(value: object) -> None:
    de_null_schema(value)


def test_anthropic_preserves_wire_updates_namespace_after_lenient_transform() -> None:
    raw_schema = SkaldTurnWire.model_json_schema()
    assert raw_schema["properties"]["updates"]["anyOf"] == [
        {"$ref": "#/$defs/UpdatesBlock"},
        {"type": "null"},
    ]

    lenient_schema = skald_wire_lenient_schema()
    transformed = anthropic_output_format(
        SkaldTurnWire,
        schema=lenient_schema,
    )["schema"]
    assert transformed["properties"]["updates"] == {
        "$ref": "#/$defs/UpdatesBlock",
        "description": "Durable semantic state changes.",
    }
    assert transformed["$defs"]["UpdatesBlock"]["required"] == [
        "characters",
        "places",
        "factions",
        "relationships",
    ]
    assert not _contains_key(transformed, "oneOf")
    assert not _contains_key(transformed, "discriminator")
    assert not _contains_key(transformed, "anyOf")


@pytest.mark.parametrize(
    ("reasoning_effort", "expected_effort"),
    [
        ("high", "high"),
        (None, None),
    ],
)
def test_two_pass_writer_native_config_reaches_shipped_anthropic_request(
    reasoning_effort: str | None,
    expected_effort: str | None,
) -> None:
    utility = LogonUtility({})
    utility._provider_wire_type = "anthropic"
    schema_kwargs = utility._two_pass_schema_format_kwargs(SkaldWriterWire)
    writer = SkaldWriterWire.model_validate(
        {
            "narrative": "The archive door opens.",
            "choices": ["Enter.", "Wait."],
            "letter": "Keep the bell unresolved.",
        }
    )
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="text", text=writer.model_dump_json()),
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        reasoning_effort=reasoning_effort,
        structured_output_retries=0,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, _llm_response = provider.get_structured_completion(
        "Write the next beat.",
        SkaldWriterWire,
        **schema_kwargs,
    )

    request_output_config = captured["output_config"]
    request_schema = request_output_config["format"]["schema"]
    expected_schema = anthropic_output_format(
        SkaldWriterWire,
        schema=skald_writer_lenient_schema(),
    )["schema"]
    assert parsed == writer
    assert request_schema == expected_schema
    assert _count_union_typed_nodes(request_schema) == 0
    if expected_effort is None:
        assert "effort" not in request_output_config
    else:
        assert request_output_config["effort"] == expected_effort


def test_two_pass_gaia_tool_envelope_reaches_forced_non_strict_tool() -> None:
    utility = LogonUtility({})
    utility._provider_wire_type = "anthropic"
    utility.provider = SimpleNamespace(structured_transport="tool_envelope")
    schema_kwargs = utility._two_pass_schema_format_kwargs(SkaldGaiaWire)
    gaia = _gaia_response()
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        name="submit_structured_response",
                        input=gaia.model_dump(mode="json"),
                    ),
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        structured_transport="tool_envelope",
        structured_output_retries=0,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, _llm_response = provider.get_structured_completion(
        "Record the durable state.",
        SkaldGaiaWire,
        **schema_kwargs,
    )

    assert parsed == gaia
    assert captured["tools"][0]["name"] == "submit_structured_response"
    assert captured["tools"][0]["input_schema"] == skald_gaia_lenient_schema()
    assert "strict" not in captured["tools"][0]
    assert captured["tool_choice"] == {
        "type": "tool",
        "name": "submit_structured_response",
    }
    assert "output_config" not in captured


@pytest.mark.asyncio
async def test_two_pass_gaia_tool_envelope_async_uses_effort_only_config() -> None:
    utility = LogonUtility({})
    utility._provider_wire_type = "anthropic"
    utility.provider = SimpleNamespace(structured_transport="tool_envelope")
    schema_kwargs = utility._two_pass_schema_format_kwargs(SkaldGaiaWire)
    gaia = _gaia_response()
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        name="submit_structured_response",
                        input=gaia.model_dump(mode="json"),
                    ),
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        reasoning_effort="medium",
        structured_transport="tool_envelope",
        structured_output_retries=0,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, _llm_response = await provider.get_structured_completion_async(
        "Record the durable state.",
        SkaldGaiaWire,
        **schema_kwargs,
    )

    assert parsed == gaia
    assert captured["tools"][0]["name"] == "submit_structured_response"
    assert captured["tools"][0]["input_schema"] == skald_gaia_lenient_schema()
    assert "strict" not in captured["tools"][0]
    assert captured["tool_choice"] == {
        "type": "tool",
        "name": "submit_structured_response",
    }
    assert captured["output_config"] == {"effort": "medium"}
    assert "format" not in captured["output_config"]


def test_anthropic_one_of_rewrite_recurses_through_lists_and_dicts() -> None:
    schema = {
        "type": "object",
        "properties": {
            "values": {
                "type": "array",
                "items": {
                    "oneOf": [{"type": "string"}, {"type": "integer"}],
                    "discriminator": {"propertyName": "kind"},
                },
            }
        },
        "$defs": {
            "Nested": {
                "oneOf": [{"type": "boolean"}, {"type": "number"}],
            }
        },
    }

    transformed = anthropic_output_format(
        StorytellerResponseBootstrap,
        schema=schema,
    )["schema"]

    assert transformed["properties"]["values"]["items"] == {
        "anyOf": [{"type": "string"}, {"type": "integer"}],
    }
    assert transformed["$defs"]["Nested"] == {
        "anyOf": [{"type": "boolean"}, {"type": "number"}],
    }


def test_anthropic_setting_schema_retains_required_nullable_default_field() -> None:
    schema = anthropic_json_schema(SettingCard)
    magic_description = schema["properties"]["magic_description"]

    assert "magic_description" in schema["required"]
    assert set(schema["required"]) == set(schema["properties"])
    assert _contains_nullable_any_of(magic_description)


def test_real_anthropic_schema_transforms_keep_property_maps_consistent() -> None:
    schemas = {
        "storyteller": anthropic_output_config(
            SkaldTurnWire,
            schema=skald_wire_lenient_schema(),
        )["format"]["schema"],
        "setting": anthropic_json_schema(SettingCard),
    }

    for name, schema in schemas.items():
        _assert_property_maps_are_consistent(schema, name)


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


def test_extended_wire_schema_excludes_inline_dossiers() -> None:
    """The strict contract stays below the post-dossier size ceiling."""

    schema = strict_json_schema(StorytellerResponseExtended)
    encoded = json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode()

    assert len(encoded) < 30_000
    assert {
        "NewCharacter",
        "CharacterTraits",
        "NewPlace",
        "PlaceDetails",
        "NewFaction",
        "FactionDetails",
    }.isdisjoint(schema.get("$defs", {}))


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


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["responses", "chat_completions"])
@pytest.mark.parametrize("call_style", ["sync", "async"])
@pytest.mark.parametrize("rejection_kind", ["model_retry", "validation_error"])
async def test_openai_rejection_logs_cover_every_transport_branch_without_input_leaks(
    caplog: pytest.LogCaptureFixture,
    transport: Literal["responses", "chat_completions"],
    call_style: Literal["sync", "async"],
    rejection_kind: Literal["model_retry", "validation_error"],
) -> None:
    """OpenAI sync/async transports log every rejected branch without letters."""

    expected = _writer_response()
    validator, sentinel, exception_name, error_text = _reject_first_structured_output(
        rejection_kind
    )
    prompts: list[str] = []

    class FakeResponses:
        def parse(self, **kwargs: Any) -> Any:
            prompts.append(kwargs["input"][-1]["content"])
            return SimpleNamespace(
                output_parsed=expected,
                output_text=expected.model_dump_json(),
                usage=SimpleNamespace(input_tokens=11, output_tokens=22),
            )

    class FakeChatCompletions:
        def create(self, **kwargs: Any) -> Any:
            prompts.append(kwargs["messages"][-1]["content"])
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=expected.model_dump_json())
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=22),
            )

    provider = OpenAIProvider(
        model="openai-log-test-model",
        api_key="test-key",
        base_url=(
            "https://structured-output.invalid/v1"
            if transport == "chat_completions"
            else None
        ),
        structured_transport=transport,
        structured_output_retries=1,
        output_validator=validator,
        usage_seat="writer",
    )
    provider.client = cast(
        Any,
        SimpleNamespace(
            responses=FakeResponses(),
            chat=SimpleNamespace(completions=FakeChatCompletions()),
        ),
    )

    with caplog.at_level(logging.WARNING, logger="nexus.metadata"):
        if call_style == "sync":
            parsed, _llm_response = await asyncio.to_thread(
                provider.get_structured_completion,
                "Write the next beat.",
                SkaldWriterWire,
            )
        else:
            parsed, _llm_response = await provider.get_structured_completion_async(
                "Write the next beat.",
                SkaldWriterWire,
            )

    assert parsed == expected
    assert len(prompts) == 2
    rejection_logs = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("structured-output rejected")
    ]
    assert len(rejection_logs) == 1
    rejection_log = rejection_logs[0]
    assert f"transport={transport}" in rejection_log
    assert "model=openai-log-test-model" in rejection_log
    assert "seat=writer" in rejection_log
    assert "attempt=1" in rejection_log
    assert f"exception={exception_name}" in rejection_log
    assert f"error={error_text}" in rejection_log
    assert sentinel not in caplog.text
    assert not any(
        record.getMessage().startswith("structured-output retries exhausted")
        for record in caplog.records
    )
    if rejection_kind == "validation_error":
        assert sentinel in prompts[1]
    else:
        assert error_text in prompts[1]


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
        model=resolve_model_ref("@local.default"),
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
        model=resolve_model_ref("@local.default"),
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
        reasoning_effort="high",
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, llm_response = provider.get_structured_completion(
        "Prompt", StorytellerResponseBootstrap
    )

    assert parsed == expected
    assert llm_response.input_tokens == 33
    assert llm_response.output_tokens == 44
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert captured["output_config"]["effort"] == "high"
    assert (
        captured["output_config"]["format"]["schema"]["additionalProperties"] is False
    )
    assert "output_format" not in captured
    assert "tools" not in captured
    assert captured["system"] == "System prompt"
    assert captured["max_tokens"] == 5678


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["native", "prompted", "tool_envelope"])
@pytest.mark.parametrize("call_style", ["sync", "async"])
@pytest.mark.parametrize("rejection_kind", ["model_retry", "validation_error"])
async def test_anthropic_rejection_logs_cover_every_transport_branch_without_input_leaks(
    caplog: pytest.LogCaptureFixture,
    transport: Literal["native", "prompted", "tool_envelope"],
    call_style: Literal["sync", "async"],
    rejection_kind: Literal["model_retry", "validation_error"],
) -> None:
    """Anthropic sync/async transports log rejected branches without letters."""

    expected = _writer_response()
    validator, sentinel, exception_name, error_text = _reject_first_structured_output(
        rejection_kind
    )
    prompts: list[str] = []

    class FakeMessages:
        def create(self, **kwargs: Any) -> Any:
            prompts.append(kwargs["messages"][-1]["content"])
            if transport == "tool_envelope":
                content = [
                    SimpleNamespace(
                        type="tool_use",
                        name="submit_structured_response",
                        input=expected.model_dump(mode="json"),
                    )
                ]
            else:
                content = [
                    SimpleNamespace(type="text", text=expected.model_dump_json())
                ]
            return SimpleNamespace(
                content=content,
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="anthropic-log-test-model",
        api_key="test-key",
        structured_transport=transport,
        structured_output_retries=1,
        output_validator=validator,
        usage_seat="writer",
    )
    provider.client = cast(
        Any,
        SimpleNamespace(
            beta=SimpleNamespace(messages=FakeMessages()),
        ),
    )

    with caplog.at_level(logging.WARNING, logger="nexus.metadata"):
        if call_style == "sync":
            parsed, _llm_response = await asyncio.to_thread(
                provider.get_structured_completion,
                "Write the next beat.",
                SkaldWriterWire,
            )
        else:
            parsed, _llm_response = await provider.get_structured_completion_async(
                "Write the next beat.",
                SkaldWriterWire,
            )

    assert parsed == expected
    assert len(prompts) == 2
    rejection_logs = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("structured-output rejected")
    ]
    assert len(rejection_logs) == 1
    rejection_log = rejection_logs[0]
    assert f"transport={transport}" in rejection_log
    assert "model=anthropic-log-test-model" in rejection_log
    assert "seat=writer" in rejection_log
    assert "attempt=1" in rejection_log
    assert f"exception={exception_name}" in rejection_log
    assert f"error={error_text}" in rejection_log
    assert sentinel not in caplog.text
    assert not any(
        record.getMessage().startswith("structured-output retries exhausted")
        for record in caplog.records
    )
    if rejection_kind == "validation_error":
        assert sentinel in prompts[1]
    else:
        assert error_text in prompts[1]


def test_anthropic_provider_rejects_unknown_structured_transport() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "structured_transport must be 'native', 'prompted', or " "'tool_envelope'"
        ),
    ):
        AnthropicProvider(
            model="claude-sonnet-4-5",
            api_key="test-key",
            structured_transport="unknown",  # type: ignore[arg-type]
        )


def test_anthropic_tool_envelope_forces_non_strict_tool_and_validates_input() -> None:
    expected = _wire_response()
    captured = {}
    input_schema = skald_wire_lenient_schema()

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text=expected.model_dump_json(),
                    ),
                    SimpleNamespace(
                        type="tool_use",
                        name="submit_structured_response",
                        input=expected.model_dump(mode="json"),
                    ),
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        system_prompt="System prompt",
        temperature=0.2,
        top_p=0.8,
        top_k=40,
        max_tokens=5678,
        thinking_enabled=True,
        thinking_budget_tokens=1024,
        structured_transport="tool_envelope",
        structured_output_retries=0,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, llm_response = provider.get_structured_completion(
        "Prompt",
        SkaldTurnWire,
        input_schema=input_schema,
    )

    assert parsed == expected
    assert llm_response.input_tokens == 33
    assert llm_response.output_tokens == 44
    assert captured["tools"] == [
        {
            "name": "submit_structured_response",
            "description": (
                "Return the complete structured response for the current NEXUS "
                "generation request."
            ),
            "input_schema": input_schema,
        }
    ]
    assert "strict" not in captured["tools"][0]
    assert captured["tool_choice"] == {
        "type": "tool",
        "name": "submit_structured_response",
    }
    assert "output_config" not in captured
    assert "output_format" not in captured
    assert captured["system"] == "System prompt"
    assert captured["temperature"] == 0.2
    assert captured["top_p"] == 0.8
    assert captured["top_k"] == 40
    assert captured["thinking"] == {
        "type": "enabled",
        "budget_tokens": 1024,
    }


@pytest.mark.asyncio
async def test_anthropic_tool_envelope_async_carries_effort_without_format() -> None:
    expected = _wire_response()
    calls = []
    input_schema = skald_wire_lenient_schema()

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        name="submit_structured_response",
                        input=expected.model_dump(mode="json"),
                    )
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        reasoning_effort="low",
        structured_transport="tool_envelope",
        structured_output_retries=0,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, _llm_response = await provider.get_structured_completion_async(
        "Prompt",
        SkaldTurnWire,
        input_schema=input_schema,
    )

    assert parsed == expected
    assert len(calls) == 1
    assert calls[0]["tools"][0]["input_schema"] == input_schema
    assert "strict" not in calls[0]["tools"][0]
    assert calls[0]["tool_choice"] == {
        "type": "tool",
        "name": "submit_structured_response",
    }
    assert calls[0]["output_config"] == {"effort": "low"}
    assert "format" not in calls[0]["output_config"]
    assert "output_format" not in calls[0]


def test_anthropic_tool_envelope_repairs_text_only_then_raises() -> None:
    expected = _wire_response()
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text=expected.model_dump_json(),
                    )
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        structured_transport="tool_envelope",
        structured_output_retries=1,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    with pytest.raises(
        ValueError,
        match="did not include the submit_structured_response tool_use block",
    ):
        provider.get_structured_completion(
            "Prompt",
            SkaldTurnWire,
            input_schema=skald_wire_lenient_schema(),
        )

    assert len(calls) == 2
    assert calls[0]["messages"][0]["content"] == "Prompt"
    assert "=== STRUCTURED OUTPUT RETRY ===" in calls[1]["messages"][0]["content"]
    assert all("output_config" not in request for request in calls)
    assert all("strict" not in request["tools"][0] for request in calls)


@pytest.mark.asyncio
async def test_anthropic_tool_envelope_async_repairs_text_only_then_raises() -> None:
    expected = _wire_response()
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text=expected.model_dump_json(),
                    )
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        structured_transport="tool_envelope",
        structured_output_retries=1,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    with pytest.raises(
        ValueError,
        match="did not include the submit_structured_response tool_use block",
    ):
        await provider.get_structured_completion_async(
            "Prompt",
            SkaldTurnWire,
            input_schema=skald_wire_lenient_schema(),
        )

    assert len(calls) == 2
    assert "=== STRUCTURED OUTPUT RETRY ===" in calls[1]["messages"][0]["content"]
    assert all("output_config" not in request for request in calls)
    assert all("strict" not in request["tools"][0] for request in calls)


def test_anthropic_prompted_transport_omits_schema_and_parses_json_fence() -> None:
    expected = _bootstrap_response()
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text=f"```json\n{expected.model_dump_json()}\n```",
                    )
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        system_prompt="System prompt",
        temperature=0.2,
        top_p=0.8,
        top_k=40,
        max_tokens=5678,
        thinking_enabled=True,
        thinking_budget_tokens=1024,
        structured_transport="prompted",
        structured_output_retries=0,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, llm_response = provider.get_structured_completion(
        "Prompt",
        StorytellerResponseBootstrap,
    )

    assert parsed == expected
    assert llm_response.input_tokens == 33
    assert llm_response.output_tokens == 44
    assert captured == {
        "model": "claude-sonnet-4-5",
        "messages": [{"role": "user", "content": "Prompt"}],
        "max_tokens": 5678,
        "system": "System prompt",
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 40,
        "thinking": {"type": "enabled", "budget_tokens": 1024},
    }


@pytest.mark.asyncio
async def test_anthropic_prompted_transport_async_parses_bare_fence() -> None:
    expected = _bootstrap_response()
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text=f"```\n{expected.model_dump_json()}\n```",
                    )
                ],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        structured_transport="prompted",
        structured_output_retries=0,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, _llm_response = await provider.get_structured_completion_async(
        "Prompt",
        StorytellerResponseBootstrap,
    )

    assert parsed == expected
    assert len(calls) == 1
    assert "output_config" not in calls[0]
    assert "output_format" not in calls[0]


def test_anthropic_prompted_transport_repairs_then_raises_on_garbage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="persistent garbage")],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        structured_transport="prompted",
        structured_output_retries=1,
        usage_seat="storyteller",
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    with caplog.at_level(logging.WARNING, logger="nexus.metadata"):
        with pytest.raises(ValidationError, match="Invalid JSON"):
            provider.get_structured_completion("Prompt", StorytellerResponseBootstrap)

    assert len(calls) == 2
    assert calls[0]["messages"][0]["content"] == "Prompt"
    assert "=== STRUCTURED OUTPUT RETRY ===" in calls[1]["messages"][0]["content"]
    assert all("output_config" not in request for request in calls)
    rejection_logs = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("structured-output rejected")
    ]
    assert len(rejection_logs) == 2
    assert "attempt=1" in rejection_logs[0]
    assert "attempt=2" in rejection_logs[1]
    exhaustion_logs = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("structured-output retries exhausted")
    ]
    assert len(exhaustion_logs) == 1
    assert "transport=prompted" in exhaustion_logs[0]
    assert "model=claude-sonnet-4-5" in exhaustion_logs[0]
    assert "seat=storyteller" in exhaustion_logs[0]
    assert "attempt=2" in exhaustion_logs[0]
    assert "exception=ValidationError" in exhaustion_logs[0]
    assert "action=propagate" in exhaustion_logs[0]
    assert "persistent garbage" not in caplog.text


@pytest.mark.asyncio
async def test_anthropic_prompted_transport_async_repairs_then_raises() -> None:
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="persistent garbage")],
                usage=SimpleNamespace(input_tokens=33, output_tokens=44),
            )

    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        structured_transport="prompted",
        structured_output_retries=1,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    with pytest.raises(ValidationError, match="Invalid JSON"):
        await provider.get_structured_completion_async(
            "Prompt",
            StorytellerResponseBootstrap,
        )

    assert len(calls) == 2
    assert "=== STRUCTURED OUTPUT RETRY ===" in calls[1]["messages"][0]["content"]
    assert all("output_config" not in request for request in calls)


def test_anthropic_prompted_transport_carries_effort_without_format() -> None:
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
        reasoning_effort="medium",
        structured_transport="prompted",
        structured_output_retries=0,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, _llm_response = provider.get_structured_completion(
        "Prompt",
        StorytellerResponseBootstrap,
    )

    assert parsed == expected
    assert captured["output_config"] == {"effort": "medium"}
    assert "format" not in captured["output_config"]


@pytest.mark.asyncio
async def test_anthropic_prompted_transport_async_carries_effort_without_format() -> (
    None
):
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
        reasoning_effort="low",
        structured_transport="prompted",
        structured_output_retries=0,
    )
    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))

    parsed, _llm_response = await provider.get_structured_completion_async(
        "Prompt",
        StorytellerResponseBootstrap,
    )

    assert parsed == expected
    assert captured["output_config"] == {"effort": "low"}
    assert "format" not in captured["output_config"]


@pytest.mark.parametrize(
    "structured_transport",
    ["prompted", "tool_envelope"],
)
@pytest.mark.parametrize("schema_argument", ["output_config", "output_format"])
def test_anthropic_non_native_transport_rejects_caller_schema_arguments(
    structured_transport: str,
    schema_argument: str,
) -> None:
    create = Mock(side_effect=AssertionError("request must not be sent"))
    provider = AnthropicProvider(
        model="claude-sonnet-4-5",
        api_key="test-key",
        structured_transport=structured_transport,  # type: ignore[arg-type]
    )
    provider.client = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(create=create))
    )

    with pytest.raises(
        ValueError,
        match="does not accept output_config or output_format",
    ):
        provider.get_structured_completion(
            "Prompt",
            StorytellerResponseBootstrap,
            **{schema_argument: {}},
        )

    create.assert_not_called()


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


def test_chat_request_params_ride_extra_body() -> None:
    """Registry request_params merge into chat-completions via extra_body (#580)."""

    provider = OpenAIProvider(
        model="moonshotai/kimi-k3",
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        structured_transport="chat_completions",
        request_params={"reasoning": {"effort": "low"}},
    )

    params = provider._build_chat_structured_request_params(
        "Prompt", StorytellerResponseBootstrap
    )

    assert params["extra_body"] == {"reasoning": {"effort": "low"}}
    assert params["model"] == "moonshotai/kimi-k3"
    # A mutation of the built dict must not leak back into provider state.
    params["extra_body"]["reasoning"]["effort"] = "high"
    assert provider.request_params == {"reasoning": {"effort": "low"}}


def test_chat_request_without_request_params_omits_extra_body() -> None:
    """Models without registry params keep the pre-#580 request shape."""

    provider = OpenAIProvider(
        model="local-model",
        api_key="test-key",
        base_url="http://127.0.0.1:1234/v1",
        structured_transport="chat_completions",
    )

    params = provider._build_chat_structured_request_params(
        "Prompt", StorytellerResponseBootstrap
    )

    assert "extra_body" not in params


def test_build_native_structured_provider_threads_request_params(
    monkeypatch,
) -> None:
    """The shared factory must not drop registry request_params (#583 review)."""
    from nexus.api import native_structured_output as nso

    endpoint = {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "test-key",
        "structured_transport": "chat_completions",
        "request_timeout_seconds": None,
        "request_params": {"reasoning": {"effort": "low"}},
    }
    monkeypatch.setattr(
        "nexus.config.get_openai_compatible_endpoint", lambda _model: endpoint
    )
    monkeypatch.setattr(
        "nexus.config.loader.get_provider_for_model", lambda _model: "openrouter"
    )

    provider = nso.build_native_structured_provider(
        model="moonshotai/kimi-k3",
        max_tokens=1000,
        system_prompt="s",
        structured_output_retries=1,
    )

    assert provider.request_params == {"reasoning": {"effort": "low"}}


def test_plain_chat_completion_merges_request_params() -> None:
    """Orrery narration's plain-completion path must apply the damping too."""

    provider = OpenAIProvider(
        model="moonshotai/kimi-k3",
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        structured_transport="chat_completions",
        request_params={"reasoning": {"effort": "low"}},
    )
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[], usage=None)

    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )

    provider._get_completion_chat_completions("Prompt")

    assert captured["extra_body"] == {"reasoning": {"effort": "low"}}
