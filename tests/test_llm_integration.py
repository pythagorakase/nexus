"""Integration tests for LLM backends (requires real services).

CI Configuration
----------------
These tests require actual LLM services to be running. In CI environments,
set the following environment variables as needed:

    NEXUS_REMOTE_BASE_URL   URL for remote LM Studio (e.g., http://host:1234/v1)
    NEXUS_REMOTE_MODEL      Model name on remote server (optional; uses server default)
    NEXUS_LLM_MODE          Force router mode (e.g., "remote" to skip local probes)
    NEXUS_ALLOW_CLOUD       Set to "1" to allow cloud fallback in auto mode

For deterministic CI runs, prefer setting NEXUS_LLM_MODE to a specific backend
rather than relying on auto mode, which can mask failures or incur cloud costs.
"""

import os

import pytest

from nexus.llm import LLMRouter
from nexus.llm.remote import RemoteLMStudioBackend

# Remote backend configuration from environment
REMOTE_BASE_URL = os.environ.get("NEXUS_REMOTE_BASE_URL")
REMOTE_MODEL = os.environ.get("NEXUS_REMOTE_MODEL")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_remote_lmstudio_completion():
    """Test actual completion via remote LM Studio."""
    if not REMOTE_BASE_URL:
        pytest.skip("NEXUS_REMOTE_BASE_URL not set")

    backend = RemoteLMStudioBackend(
        base_url=REMOTE_BASE_URL,
        model=REMOTE_MODEL,  # None uses server default
    )

    if not backend.is_available():
        pytest.skip("Remote LM Studio not available")

    response = await backend.complete("Say 'hello' and nothing else.")

    assert response.content
    assert "hello" in response.content.lower()
    print(f"Response: {response.content}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_router_with_real_backends():
    """Test router fallback with real backend configuration."""
    router = LLMRouter(settings_path="nexus.toml")

    if not router.is_available():
        pytest.skip("No LLM backends available")

    response = await router.complete("What is 2+2? Answer with just the number.")

    assert response.content
    assert "4" in response.content
    print(f"Router response: {response.content}")
