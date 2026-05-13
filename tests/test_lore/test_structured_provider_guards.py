"""Tests for sync structured provider guardrails."""

import pytest

from scripts.api_anthropic import AnthropicProvider
from scripts.api_openai import OpenAIProvider


@pytest.mark.asyncio
async def test_openai_sync_structured_completion_rejects_running_loop() -> None:
    """The sync OpenAI structured API should point async callers to its async twin."""

    provider = OpenAIProvider.__new__(OpenAIProvider)

    with pytest.raises(RuntimeError, match="get_structured_completion_async"):
        provider.get_structured_completion("prompt", object)


@pytest.mark.asyncio
async def test_anthropic_sync_structured_completion_rejects_running_loop() -> None:
    """The sync Anthropic structured API should point async callers to its async twin."""

    provider = AnthropicProvider.__new__(AnthropicProvider)

    with pytest.raises(RuntimeError, match="get_structured_completion_async"):
        provider.get_structured_completion("prompt", object)
