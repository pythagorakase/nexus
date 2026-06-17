"""Provider-native structured-output helpers.

Pydantic models remain the NEXUS app contract, but provider requests should
use native strict schema controls where available. This module keeps the wire
schema and the boundary validation helpers in one place.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Type

from pydantic import BaseModel


ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS = {
    "default",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "format",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "multipleOf",
    "pattern",
}


@dataclass
class NativeValidationContext:
    """Small context object for validators that were written for Pydantic AI."""

    retry: int = 0


def strict_json_schema(schema_model: Type[BaseModel]) -> Dict[str, Any]:
    """Return the strict JSON schema OpenAI's native parser sends on the wire."""

    try:
        from openai.lib._pydantic import to_strict_json_schema
    except ImportError:
        return schema_model.model_json_schema()

    return to_strict_json_schema(schema_model)


def openai_response_text_format(
    schema_model: Type[BaseModel], *, schema: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build the OpenAI Responses API native strict text format payload."""

    if schema is not None:
        return {
            "type": "json_schema",
            "strict": True,
            "name": schema_model.__name__,
            "schema": schema,
        }

    try:
        from openai.lib._parsing._responses import type_to_text_format_param
    except ImportError:
        schema = strict_json_schema(schema_model)
        return {
            "type": "json_schema",
            "strict": True,
            "name": schema_model.__name__,
            "schema": schema,
        }

    return type_to_text_format_param(schema_model)


def _strip_anthropic_unsupported_schema_keys(value: Any) -> Any:
    """Remove JSON Schema constraints not accepted by Anthropic structured output."""

    if isinstance(value, list):
        return [_strip_anthropic_unsupported_schema_keys(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _strip_anthropic_unsupported_schema_keys(item)
        for key, item in value.items()
        if key not in ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS
    }


def anthropic_json_schema(schema_model: Type[BaseModel]) -> Dict[str, Any]:
    """Return a schema suitable for Anthropic native JSON output."""

    return _strip_anthropic_unsupported_schema_keys(strict_json_schema(schema_model))


def anthropic_output_format(
    schema_model: Type[BaseModel], *, schema: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build the Anthropic beta Messages native JSON schema output format."""

    schema_payload = (
        _strip_anthropic_unsupported_schema_keys(schema)
        if schema is not None
        else anthropic_json_schema(schema_model)
    )
    return {"type": "json_schema", "schema": schema_payload}


def anthropic_strict_tool(
    schema_model: Type[BaseModel], *, name: str = "submit_structured_response"
) -> Dict[str, Any]:
    """Build an Anthropic strict tool definition for schema-constrained calls."""

    return {
        "name": name,
        "description": (
            "Return the complete structured response for the current NEXUS "
            "generation request."
        ),
        "input_schema": anthropic_json_schema(schema_model),
        "strict": True,
    }


def build_native_structured_provider(
    *,
    model: str,
    max_tokens: int,
    system_prompt: str,
    structured_output_retries: int,
    output_validator: Optional[Callable[..., Any]] = None,
) -> Any:
    """Build the repo's native strict structured-output provider wrapper."""

    from nexus.config import get_openai_compatible_endpoint
    from nexus.config.loader import get_provider_for_model
    from scripts.api_anthropic import AnthropicProvider
    from scripts.api_openai import OpenAIProvider

    endpoint = get_openai_compatible_endpoint(model)
    provider_type = get_provider_for_model(model)
    if provider_type == "anthropic" and endpoint is None:
        return AnthropicProvider(
            model=model,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            structured_output_retries=structured_output_retries,
            output_validator=output_validator,
        )
    if provider_type == "openai" or endpoint is not None:
        return OpenAIProvider(
            model=model,
            max_output_tokens=max_tokens,
            system_prompt=system_prompt,
            base_url=endpoint["base_url"] if endpoint else None,
            api_key=endpoint["api_key"] if endpoint else None,
            structured_output_retries=structured_output_retries,
            output_validator=output_validator,
        )
    raise ValueError(f"Unsupported provider type for model {model!r}: {provider_type}")


def retry_prompt(prompt: str, message: str) -> str:
    """Append a bounded repair instruction for semantic validation retries."""

    return (
        f"{prompt}\n\n"
        "=== STRUCTURED OUTPUT RETRY ===\n"
        "Your previous structured response failed validation before commit.\n"
        f"{message}\n"
        "Return a complete response satisfying the same schema. Use null or "
        "empty arrays for absent optional values instead of omitting required "
        "strict-schema keys."
    )


async def run_output_validator(
    validator: Optional[Callable[..., Any]],
    output: Any,
    *,
    retry: int = 0,
) -> Any:
    """Run an optional Pydantic-AI-style output validator."""

    if validator is None:
        return output

    result = validator(NativeValidationContext(retry=retry), output)
    if inspect.isawaitable(result):
        result = await result
    return output if result is None else result
