"""Provider-native structured-output helpers.

Pydantic models remain the NEXUS app contract, but provider requests should
use native strict schema controls where available. This module keeps the wire
schema and the boundary validation helpers in one place.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Type, cast

from pydantic import BaseModel
from pydantic_ai import JsonSchemaTransformer


ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS = {
    "default",
    "discriminator",
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

    return cast(Dict[str, Any], type_to_text_format_param(schema_model))


def de_null_schema(value: Any) -> Any:
    """Collapse omittable nullable unions without changing non-schema values.

    Lenient provider schemas express optional fields as non-required properties,
    so their explicit ``null`` alternative is redundant. Sibling keys survive
    the collapse, while keys from the non-null member take precedence.
    """

    if isinstance(value, list):
        return [de_null_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    transformed = {key: de_null_schema(item) for key, item in value.items()}
    any_of = transformed.get("anyOf")
    if not isinstance(any_of, list) or len(any_of) != 2:
        return transformed

    null_indexes = [
        index
        for index, member in enumerate(any_of)
        if isinstance(member, dict) and member.get("type") == "null"
    ]
    if len(null_indexes) != 1:
        return transformed

    non_null_member = any_of[1 - null_indexes[0]]
    if not isinstance(non_null_member, dict):
        return transformed

    siblings = {key: item for key, item in transformed.items() if key != "anyOf"}
    return {**siblings, **non_null_member}


def _rewrite_anthropic_schema(value: Any) -> Any:
    """Recursively remove or rewrite schema features Anthropic rejects."""

    if isinstance(value, list):
        return [_rewrite_anthropic_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        # Anthropic's native format rejects oneOf (Pydantic emits it for
        # discriminated unions, e.g. SkaldTurnWire.updates). anyOf is the
        # accepted, semantically-wider spelling; app-side Pydantic still
        # enforces the discriminator after parse. Found live on the first
        # universal-wire Anthropic turn (measurement stage).
        ("anyOf" if key == "oneOf" else key): _rewrite_anthropic_schema(item)
        for key, item in value.items()
        if key not in ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS
    }


def _strip_anthropic_unsupported_schema_keys(value: Any) -> Any:
    """Build Anthropic's rewritten supported JSON Schema subset."""

    return _rewrite_anthropic_schema(value)


class AnthropicJsonSchemaTransformer(JsonSchemaTransformer):
    """Close object schemas and strip unsupported Anthropic constraints.

    Pydantic-ai still parses and validates the returned object against the
    original Pydantic model, including retries after validation failures.
    These changes are therefore limited to grammar-level enforcement, the same
    tradeoff made by the legacy Anthropic storyteller path.
    """

    def transform(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Remove unsupported keys and forbid extras on each object schema."""
        transformed = cast(
            Dict[str, Any], _strip_anthropic_unsupported_schema_keys(schema)
        )
        if transformed.get("type") == "object":
            transformed["additionalProperties"] = False
        return transformed


def anthropic_json_schema(schema_model: Type[BaseModel]) -> Dict[str, Any]:
    """Return a schema suitable for Anthropic native JSON output."""

    return _strip_anthropic_unsupported_schema_keys(strict_json_schema(schema_model))


def anthropic_output_format(
    schema_model: Type[BaseModel], *, schema: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build the Anthropic native JSON schema format payload."""

    schema_payload = (
        _strip_anthropic_unsupported_schema_keys(schema)
        if schema is not None
        else anthropic_json_schema(schema_model)
    )
    return {"type": "json_schema", "schema": schema_payload}


def anthropic_output_config(
    schema_model: Type[BaseModel], *, schema: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build the Anthropic Messages output_config wrapper for native JSON output."""

    return {"format": anthropic_output_format(schema_model, schema=schema)}


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
    temperature: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
) -> Any:
    """Build the repo's native strict structured-output provider wrapper.

    ``temperature`` and ``reasoning_effort`` are optional so existing callers
    retain each provider wrapper's defaults. Consumers that expose sampling
    controls can pass them without reimplementing provider routing.
    """

    from nexus.config import get_openai_compatible_endpoint
    from nexus.config.loader import get_provider_for_model
    from scripts.api_anthropic import AnthropicProvider
    from scripts.api_openai import OpenAIProvider

    endpoint = get_openai_compatible_endpoint(model)
    provider_type = get_provider_for_model(model)
    if provider_type == "anthropic" and endpoint is None:
        anthropic_kwargs: Dict[str, Any] = {}
        if temperature is not None:
            anthropic_kwargs["temperature"] = temperature
        if reasoning_effort is not None:
            anthropic_kwargs["reasoning_effort"] = reasoning_effort
        return AnthropicProvider(
            model=model,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            structured_output_retries=structured_output_retries,
            output_validator=output_validator,
            **anthropic_kwargs,
        )
    if provider_type == "openai" or endpoint is not None:
        openai_kwargs: Dict[str, Any] = {}
        if temperature is not None:
            openai_kwargs["temperature"] = temperature
        if reasoning_effort is not None:
            openai_kwargs["reasoning_effort"] = reasoning_effort
        return OpenAIProvider(
            model=model,
            max_output_tokens=max_tokens,
            system_prompt=system_prompt,
            base_url=endpoint["base_url"] if endpoint else None,
            api_key=endpoint["api_key"] if endpoint else None,
            structured_transport=(
                endpoint["structured_transport"] if endpoint else "responses"
            ),
            request_timeout=(endpoint["request_timeout_seconds"] if endpoint else None),
            structured_output_retries=structured_output_retries,
            output_validator=output_validator,
            **openai_kwargs,
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
