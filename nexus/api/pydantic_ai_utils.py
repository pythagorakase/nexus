"""Shared helpers for Pydantic AI model wiring and message conversion."""

from __future__ import annotations

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
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.anthropic import AnthropicProvider as PydanticAnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider as PydanticOpenAIProvider

from nexus.config import load_settings
from nexus.config.loader import get_provider_for_model
from scripts.api_anthropic import AnthropicProvider as LegacyAnthropicProvider
from scripts.api_openai import OpenAIProvider as LegacyOpenAIProvider


def get_base_url_for_model(model: str) -> Optional[str]:
    """Return a base URL override for the model, if configured."""
    provider = get_provider_for_model(model)
    if provider == "test":
        settings = load_settings()
        if settings.global_.api:
            return settings.global_.api.test_mock_server_url
        return "http://localhost:5102/v1"
    if provider in {"openai", "anthropic"}:
        return None
    raise ValueError(f"Unknown provider for model {model!r}")


def build_pydantic_ai_model(model: str) -> Model:
    """Create a Pydantic AI model with the correct provider and credentials."""
    provider = get_provider_for_model(model)
    if provider == "openai":
        legacy_provider = LegacyOpenAIProvider(model=model)
        pyd_provider = PydanticOpenAIProvider(api_key=legacy_provider.api_key)
        return OpenAIResponsesModel(model_name=model, provider=pyd_provider)
    if provider == "anthropic":
        legacy_provider = LegacyAnthropicProvider(model=model)
        pyd_provider = PydanticAnthropicProvider(api_key=legacy_provider.api_key)
        return AnthropicModel(model_name=model, provider=pyd_provider)
    if provider == "test":
        base_url = get_base_url_for_model(model)
        pyd_provider = PydanticOpenAIProvider(
            api_key="test-dummy-key", base_url=base_url
        )
        return OpenAIResponsesModel(model_name=model, provider=pyd_provider)
    raise ValueError(f"Unknown provider for model {model!r}")


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
