"""Shared helpers for Pydantic AI model wiring and message conversion."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.profiles.anthropic import anthropic_model_profile
from pydantic_ai.providers.anthropic import (
    AnthropicProvider as PydanticAnthropicProvider,
)
from pydantic_ai.providers.openai import OpenAIProvider as PydanticOpenAIProvider

from nexus.api.native_structured_output import AnthropicJsonSchemaTransformer
from nexus.config import get_openai_compatible_endpoint
from nexus.config.loader import (
    get_native_structured_output_override,
    get_provider_for_model,
)
from scripts.api_anthropic import AnthropicProvider as LegacyAnthropicProvider
from scripts.api_openai import OpenAIProvider as LegacyOpenAIProvider


def get_base_url_for_model(model: str) -> Optional[str]:
    """Return the registry base_url for the model (None for native providers)."""
    endpoint = get_openai_compatible_endpoint(model)
    return endpoint["base_url"] if endpoint else None


def build_pydantic_ai_model(model: str) -> Model:
    """Create a Pydantic AI model with the correct provider and credentials."""
    provider = get_provider_for_model(model)
    if provider is None:
        raise ValueError(f"Unknown provider for model {model!r}")
    if provider == "openai":
        legacy_provider = LegacyOpenAIProvider(model=model)
        pyd_provider = PydanticOpenAIProvider(api_key=legacy_provider.api_key)
        return OpenAIResponsesModel(model_name=model, provider=pyd_provider)
    if provider == "anthropic":
        legacy_provider = LegacyAnthropicProvider(model=model)
        pyd_provider = PydanticAnthropicProvider(api_key=legacy_provider.api_key)
        override = get_native_structured_output_override(model)
        if override is not None:
            profile = replace(
                anthropic_model_profile(model),
                json_schema_transformer=AnthropicJsonSchemaTransformer,
                supports_json_schema_output=override,
            )
            return AnthropicModel(
                model_name=model, provider=pyd_provider, profile=profile
            )
        return AnthropicModel(model_name=model, provider=pyd_provider)
    # Any other provider is an OpenAI-compatible server registered via
    # base_url in [global.model.api_models] (mock TEST server, Ollama, vLLM).
    endpoint = get_openai_compatible_endpoint(model)
    if endpoint is None:
        raise ValueError(f"No base_url registry entry for model {model!r}")
    pyd_provider = PydanticOpenAIProvider(
        api_key=endpoint["api_key"], base_url=endpoint["base_url"]
    )
    if endpoint["structured_transport"] == "chat_completions":
        return OpenAIChatModel(model_name=model, provider=pyd_provider)
    return OpenAIResponsesModel(model_name=model, provider=pyd_provider)


def build_message_history(
    messages: Sequence[Dict[str, Any]],
) -> List[ModelMessage]:
    """
    Convert stored chat history into Pydantic AI message objects.

    Empty or non-string content is skipped to avoid emitting blank parts in the
    model history; tool-only turns should be represented explicitly elsewhere.
    """
    history: List[ModelMessage] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "system":
            history.append(ModelRequest(parts=[SystemPromptPart(content=content)]))
        elif role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=content)]))
    return history
